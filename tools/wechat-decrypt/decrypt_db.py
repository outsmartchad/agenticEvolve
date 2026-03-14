#!/usr/bin/env python3
"""
decrypt_db.py — Decrypt WeChat SQLCipher databases using extracted keys.

Usage:
    python3 decrypt_db.py                          # auto-find DBs + keys
    python3 decrypt_db.py --keys wechat_keys.json  # specify keys file
    python3 decrypt_db.py --db-dir /path/to/dbs    # specify DB directory
    python3 decrypt_db.py --output ./decrypted      # specify output dir

Prerequisites:
    pip install pycryptodome
    # Keys must be extracted first via find_keys (C tool)
"""

import argparse
import hashlib
import hmac
import json
import os
import shutil
import struct
import sys
from pathlib import Path

# WeChat SQLCipher 4 parameters
PAGE_SIZE = 4096
KEY_LEN = 32
SALT_LEN = 16
IV_LEN = 16
HMAC_LEN = 64
RESERVE_LEN = IV_LEN + HMAC_LEN  # 80 bytes
KDF_ITERATIONS = 256000
HMAC_SALT_MASK = 0x3A

def find_wechat_db_dir():
    """Find WeChat's database directory on macOS."""
    base = Path.home() / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
    if not base.exists():
        return None

    # Find the wxid directory (first subdirectory)
    for d in base.iterdir():
        if d.is_dir():
            db_dir = d / "db_storage"
            if db_dir.exists():
                return db_dir
    return None


def find_all_dbs(db_dir):
    """Recursively find all .db files."""
    return sorted(db_dir.rglob("*.db"))


def read_page1(db_path):
    """Read the first page (4096 bytes) of a DB file."""
    with open(db_path, "rb") as f:
        return f.read(PAGE_SIZE)


def get_salt_from_page1(page1):
    """Extract the 16-byte salt from page 1."""
    return page1[:SALT_LEN]


def verify_key(enc_key_bytes, page1):
    """Verify a candidate key against page 1 using HMAC-SHA512.

    Returns True if the key is valid for this database.
    """
    if len(page1) < PAGE_SIZE:
        return False

    salt = page1[:SALT_LEN]

    # Derive HMAC key: PBKDF2(key, salt XOR 0x3A, 2 iterations)
    mac_salt = bytes(b ^ HMAC_SALT_MASK for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key_bytes, mac_salt, 2, dklen=KEY_LEN)

    # HMAC covers: encrypted content (after salt) + IV
    # Page layout: [salt 16][encrypted 4000][IV 16][HMAC 64]
    hmac_data = page1[SALT_LEN : PAGE_SIZE - HMAC_LEN]  # encrypted + IV
    stored_hmac = page1[PAGE_SIZE - HMAC_LEN : PAGE_SIZE]

    h = hmac.new(mac_key, hmac_data, hashlib.sha512)
    h.update(struct.pack("<I", 1))  # page number, little-endian
    computed = h.digest()

    return hmac.compare_digest(computed, stored_hmac)


def decrypt_db(db_path, enc_key_hex, output_path):
    """Decrypt a SQLCipher DB using the raw hex key.

    Uses sqlcipher CLI if available, otherwise falls back to pycryptodome
    for page-by-page decryption.
    """
    # Try sqlcipher CLI first (much simpler)
    sqlcipher_path = shutil.which("sqlcipher")
    if sqlcipher_path:
        return _decrypt_with_sqlcipher(db_path, enc_key_hex, output_path, sqlcipher_path)
    else:
        return _decrypt_with_crypto(db_path, enc_key_hex, output_path)


def _decrypt_with_sqlcipher(db_path, enc_key_hex, output_path, sqlcipher_path):
    """Decrypt using sqlcipher CLI."""
    import subprocess

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing output
    if output_path.exists():
        output_path.unlink()

    sql = f"""
PRAGMA key = "x'{enc_key_hex}'";
PRAGMA cipher_page_size = {PAGE_SIZE};
PRAGMA kdf_iter = {KDF_ITERATIONS};
PRAGMA cipher_hmac_algorithm = HMAC_SHA512;
PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;
ATTACH DATABASE '{output_path}' AS plaintext KEY '';
SELECT sqlcipher_export('plaintext');
DETACH DATABASE plaintext;
"""
    result = subprocess.run(
        [sqlcipher_path, str(db_path)],
        input=sql,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"  [-] sqlcipher error: {result.stderr.strip()}", file=sys.stderr)
        return False

    return output_path.exists() and output_path.stat().st_size > 0


def _decrypt_with_crypto(db_path, enc_key_hex, output_path):
    """Decrypt page-by-page using pycryptodome (fallback if no sqlcipher CLI)."""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        print("[-] pycryptodome not installed. Run: pip install pycryptodome", file=sys.stderr)
        print("    Or install sqlcipher: brew install sqlcipher", file=sys.stderr)
        return False

    enc_key = bytes.fromhex(enc_key_hex)

    with open(db_path, "rb") as f:
        data = f.read()

    if len(data) < PAGE_SIZE:
        return False

    total_pages = len(data) // PAGE_SIZE
    salt = data[:SALT_LEN]

    # Derive the actual AES key via PBKDF2
    derived_key = hashlib.pbkdf2_hmac(
        "sha512", enc_key, salt, KDF_ITERATIONS, dklen=KEY_LEN
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    decrypted_pages = []

    for page_num in range(total_pages):
        offset = page_num * PAGE_SIZE
        page = data[offset : offset + PAGE_SIZE]

        if page_num == 0:
            # Page 1: [salt 16][encrypted 4000][IV 16][HMAC 64]
            encrypted = page[SALT_LEN : PAGE_SIZE - RESERVE_LEN]
            iv = page[PAGE_SIZE - RESERVE_LEN : PAGE_SIZE - HMAC_LEN]
        else:
            # Other pages: [encrypted 4016][IV 16][HMAC 64]
            encrypted = page[: PAGE_SIZE - RESERVE_LEN]
            iv = page[PAGE_SIZE - RESERVE_LEN : PAGE_SIZE - HMAC_LEN]

        try:
            cipher = AES.new(derived_key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(encrypted)
        except Exception:
            # If decryption fails, write zeros
            decrypted = b"\x00" * len(encrypted)

        if page_num == 0:
            # Reconstruct page 1 with SQLite header
            header = b"SQLite format 3\x00"
            decrypted_pages.append(header + decrypted[len(header):])
        else:
            decrypted_pages.append(decrypted)

    with open(output_path, "wb") as f:
        for page in decrypted_pages:
            f.write(page)

    return True


def match_keys_to_dbs(keys, db_files):
    """Match extracted keys to database files by verifying HMAC.

    Returns list of (db_path, key_hex) tuples.
    """
    matches = []
    unmatched_dbs = list(db_files)

    for key_entry in keys:
        hex_key = key_entry["key"]
        hex_salt = key_entry.get("salt", "")
        enc_key_bytes = bytes.fromhex(hex_key)

        matched_for_key = []
        still_unmatched = []

        for db_path in unmatched_dbs:
            page1 = read_page1(db_path)
            if len(page1) < PAGE_SIZE:
                still_unmatched.append(db_path)
                continue

            db_salt = get_salt_from_page1(page1).hex()

            # If key entry has salt, quick-match first
            if hex_salt and db_salt == hex_salt:
                if verify_key(enc_key_bytes, page1):
                    matched_for_key.append(db_path)
                    continue

            # Try HMAC verification regardless
            if verify_key(enc_key_bytes, page1):
                matched_for_key.append(db_path)
            else:
                still_unmatched.append(db_path)

        for db_path in matched_for_key:
            matches.append((db_path, hex_key))

        unmatched_dbs = still_unmatched

    return matches, unmatched_dbs


def main():
    parser = argparse.ArgumentParser(description="Decrypt WeChat SQLCipher databases")
    parser.add_argument("--keys", default="wechat_keys.json", help="Path to keys JSON")
    parser.add_argument("--db-dir", help="Path to WeChat db_storage directory")
    parser.add_argument("--output", default="./decrypted", help="Output directory")
    args = parser.parse_args()

    # Load keys
    keys_path = Path(args.keys)
    if not keys_path.exists():
        print(f"[-] Keys file not found: {keys_path}", file=sys.stderr)
        print("    Run find_keys first to extract keys from WeChat process memory.", file=sys.stderr)
        return 1

    with open(keys_path) as f:
        keys = json.load(f)

    print(f"[*] Loaded {len(keys)} key(s) from {keys_path}")

    # Find DB directory
    if args.db_dir:
        db_dir = Path(args.db_dir)
    else:
        db_dir = find_wechat_db_dir()
        if not db_dir:
            print("[-] WeChat db_storage not found. Specify --db-dir.", file=sys.stderr)
            return 1

    print(f"[*] DB directory: {db_dir}")

    # Find all .db files
    db_files = find_all_dbs(db_dir)
    print(f"[*] Found {len(db_files)} database file(s)")

    if not db_files:
        return 1

    # Match keys to databases
    print("[*] Matching keys to databases via HMAC verification...")
    matches, unmatched = match_keys_to_dbs(keys, db_files)
    print(f"[*] Matched {len(matches)} database(s), {len(unmatched)} unmatched")

    if not matches:
        print("[-] No keys matched any databases. Keys may be stale — re-extract.", file=sys.stderr)
        return 1

    # Decrypt matched databases
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    success = 0

    for db_path, hex_key in matches:
        # Preserve subdirectory structure
        rel = db_path.relative_to(db_dir)
        out_path = output_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"  [*] Decrypting {rel}...", end=" ")
        if decrypt_db(db_path, hex_key, out_path):
            print("OK")
            success += 1
        else:
            print("FAILED")

    print(f"\n[+] Decrypted {success}/{len(matches)} databases to {output_dir}")

    # Save match info
    match_info = [{"db": str(p.relative_to(db_dir)), "key": k} for p, k in matches]
    with open(output_dir / "match_info.json", "w") as f:
        json.dump(match_info, f, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
