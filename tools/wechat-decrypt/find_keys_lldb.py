#!/usr/bin/env python3
"""
find_keys_lldb.py — Extract WeChat SQLCipher keys via lldb Python API.

Scans WeChat's process memory for x'<hex>' patterns containing encryption keys.
Uses lldb's Python API — no SIP disable or codesign needed, just DevToolsSecurity enabled.

Usage:
    PYTHONPATH=$(lldb -P) python3 find_keys_lldb.py
    PYTHONPATH=$(lldb -P) python3 find_keys_lldb.py --pid 12345
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

def get_lldb():
    """Import lldb module."""
    try:
        import lldb
        return lldb
    except ImportError:
        print("[-] Cannot import lldb. Run with:", file=sys.stderr)
        print(f'    PYTHONPATH=$(lldb -P) python3 {sys.argv[0]}', file=sys.stderr)
        sys.exit(1)


def find_wechat_pid():
    """Find WeChat main process PID."""
    result = subprocess.run(
        ["pgrep", "-f", r"/Applications/WeChat.app/Contents/MacOS/WeChat$"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().split("\n")[0])

    # Fallback: any WeChat process
    result = subprocess.run(["pgrep", "WeChat"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        pids = result.stdout.strip().split("\n")
        return int(pids[0])
    return None


def find_wechat_dbs():
    """Find all WeChat .db files and read their salts (first 16 bytes)."""
    base = Path.home() / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
    if not base.exists():
        return {}

    db_salts = {}
    for db_path in base.rglob("*.db"):
        try:
            with open(db_path, "rb") as f:
                header = f.read(16)
            if len(header) == 16:
                # Skip if it starts with "SQLite format 3" (unencrypted)
                if header[:15] == b"SQLite format 3":
                    continue
                db_salts[db_path] = header
        except Exception:
            pass

    return db_salts


def verify_key_against_db(enc_key_bytes, db_path):
    """Verify a candidate key against a DB's first page via HMAC-SHA512."""
    try:
        with open(db_path, "rb") as f:
            page1 = f.read(4096)
    except Exception:
        return False

    if len(page1) < 4096:
        return False

    salt = page1[:16]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key_bytes, mac_salt, 2, dklen=32)

    hmac_data = page1[16 : 4096 - 64]  # encrypted content + IV
    stored_hmac = page1[4096 - 64 : 4096]

    h = hmac.new(mac_key, hmac_data, hashlib.sha512)
    h.update(struct.pack("<I", 1))
    return hmac.compare_digest(h.digest(), stored_hmac)


def scan_memory(pid, db_salts):
    """Scan WeChat process memory for encryption keys using lldb."""
    lldb = get_lldb()

    print(f"[*] Attaching to WeChat PID {pid}...")

    debugger = lldb.SBDebugger.Create()
    debugger.SetAsync(False)

    target = debugger.CreateTarget("")
    if not target:
        print("[-] Failed to create target", file=sys.stderr)
        return []

    error = lldb.SBError()
    process = target.AttachToProcessWithID(debugger.GetListener(), pid, error)

    if not process or error.Fail():
        print(f"[-] Failed to attach: {error.GetCString()}", file=sys.stderr)
        print("    Make sure DevToolsSecurity is enabled and you have access.", file=sys.stderr)
        return []

    print(f"[*] Attached. Scanning memory regions...")

    # Pattern: x'<64-192 hex chars>'
    pattern = re.compile(rb"x'([0-9a-fA-F]{64,192})'")

    found_keys = {}  # hex_string -> set of matching db paths
    regions_scanned = 0
    bytes_scanned = 0

    # Iterate memory regions
    for region in process:
        # region is an SBMemoryRegionInfo — but iteration gives SBThread
        pass

    # Use GetMemoryRegionInfo instead
    addr = 0
    region_info = lldb.SBMemoryRegionInfo()

    while True:
        err = process.GetMemoryRegionInfo(addr, region_info)
        if err.Fail():
            break

        start = region_info.GetRegionBase()
        end = region_info.GetRegionEnd()
        size = end - start

        if end <= start:
            break

        # Only scan readable, writable, non-executable regions < 500MB
        readable = region_info.IsReadable()
        writable = region_info.IsWritable()
        executable = region_info.IsExecutable()

        if readable and writable and not executable and size < 500 * 1024 * 1024:
            # Read in 8MB chunks
            chunk_size = 8 * 1024 * 1024
            offset = 0

            while offset < size:
                to_read = min(chunk_size, size - offset)
                read_err = lldb.SBError()
                data = process.ReadMemory(start + offset, to_read, read_err)

                if read_err.Success() and data:
                    # Search for pattern
                    for match in pattern.finditer(data):
                        hex_str = match.group(1).decode("ascii")

                        if hex_str not in found_keys:
                            found_keys[hex_str] = set()
                            key_bytes = bytes.fromhex(hex_str[:64])

                            # Try to match against known DBs
                            for db_path, salt in db_salts.items():
                                if verify_key_against_db(key_bytes, db_path):
                                    found_keys[hex_str].add(str(db_path))

                            matched = len(found_keys[hex_str])
                            region_addr = start + offset + match.start()
                            print(f"  [+] Key at 0x{region_addr:x} ({len(hex_str)} hex chars, {matched} DB match(es))")

                    bytes_scanned += len(data)

                offset += chunk_size

            regions_scanned += 1

        # Move to next region
        addr = end
        if addr == 0:  # wrapped around
            break

    # Detach (don't kill WeChat!)
    process.Detach()
    lldb.SBDebugger.Destroy(debugger)

    print(f"[*] Scanned {regions_scanned} regions, {bytes_scanned / (1024*1024):.1f} MB")
    print(f"[*] Found {len(found_keys)} unique key candidate(s)")

    return found_keys


def main():
    parser = argparse.ArgumentParser(description="Extract WeChat encryption keys via lldb")
    parser.add_argument("--pid", type=int, help="WeChat PID (auto-detected if omitted)")
    parser.add_argument("--output", default="wechat_keys.json", help="Output file")
    args = parser.parse_args()

    pid = args.pid or find_wechat_pid()
    if not pid:
        print("[-] WeChat not running. Launch it first.", file=sys.stderr)
        return 1

    # Find DB files and their salts
    db_salts = find_wechat_dbs()
    print(f"[*] Found {len(db_salts)} encrypted WeChat DB(s)")

    # Scan memory
    found_keys = scan_memory(pid, db_salts)

    if not found_keys:
        print("[-] No keys found.", file=sys.stderr)
        return 1

    # Build output
    results = []
    all_matched_dbs = set()

    for hex_str, matched_dbs in found_keys.items():
        entry = {
            "key": hex_str[:64],
            "salt": hex_str[64:96] if len(hex_str) >= 96 else "",
            "full": hex_str,
            "matched_dbs": sorted(matched_dbs),
        }
        results.append(entry)
        all_matched_dbs.update(matched_dbs)

    # Cross-verify: try all keys against unmatched DBs
    unmatched_dbs = {p: s for p, s in db_salts.items() if str(p) not in all_matched_dbs}
    if unmatched_dbs:
        print(f"[*] Cross-verifying {len(unmatched_dbs)} unmatched DB(s)...")
        for entry in results:
            key_bytes = bytes.fromhex(entry["key"])
            for db_path in list(unmatched_dbs.keys()):
                if verify_key_against_db(key_bytes, db_path):
                    entry["matched_dbs"].append(str(db_path))
                    del unmatched_dbs[db_path]
                    print(f"  [+] Cross-matched: {db_path.name}")

    # Write output
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total_matched = sum(len(e["matched_dbs"]) for e in results)
    print(f"\n[+] {len(results)} key(s) matching {total_matched} DB(s) written to {output_path}")

    if unmatched_dbs:
        print(f"[!] {len(unmatched_dbs)} DB(s) still unmatched (may use different keys or be unencrypted)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
