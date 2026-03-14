#!/usr/bin/env python3
"""
extract_key.py — Combined WeChat macOS key extractor

Approach A: Scan for x'<hex>' PRAGMA key strings in RW memory (fast, reliable)
Approach B: Salt-proximity + codec_ctx pointer chasing (slower, fallback)

Adapted from:
  - ylytdeng/wechat-decrypt (string scan)
  - cocohahaha/wechat-decrypt-macos (codec_ctx pointer chasing)

Usage:
    sudo python3 extract_key.py                  # auto-detect PID + DB
    sudo python3 extract_key.py --pid 55797      # specify PID
    sudo python3 extract_key.py --verify          # verify keys with sqlcipher

Output: wechat_keys.json, all_keys.json
"""

import argparse
import ctypes
import ctypes.util
import glob
import hashlib
import hmac
import json
import math
import os
import struct
import subprocess
import sys
import re

# ── Mach VM API bindings ──

_libc = ctypes.CDLL(ctypes.util.find_library("c"))

_mach_task_self = _libc.mach_task_self
_mach_task_self.restype = ctypes.c_uint

_task_for_pid = _libc.task_for_pid
_task_for_pid.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
_task_for_pid.restype = ctypes.c_int

_mach_vm_read_overwrite = _libc.mach_vm_read_overwrite
_mach_vm_read_overwrite.argtypes = [
    ctypes.c_uint, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64),
]
_mach_vm_read_overwrite.restype = ctypes.c_int

_mach_vm_region = _libc.mach_vm_region
_mach_vm_region.argtypes = [
    ctypes.c_uint, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64), ctypes.c_int,
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
]
_mach_vm_region.restype = ctypes.c_int

VM_REGION_BASIC_INFO_64 = 9
VM_PROT_READ = 1
VM_PROT_WRITE = 2


class MachProcess:
    """Read memory from a macOS process."""

    def __init__(self, pid):
        self.pid = pid
        self._task = ctypes.c_uint()
        ret = _task_for_pid(_mach_task_self(), pid, ctypes.byref(self._task))
        if ret != 0:
            raise PermissionError(
                f"task_for_pid failed (ret={ret}).\n"
                "Ensure: (1) running as root, (2) WeChat ad-hoc signed"
            )

    @property
    def task(self):
        return self._task.value

    def read_memory(self, address, size):
        """Read process memory. Returns bytes or None on failure."""
        buf = ctypes.create_string_buffer(size)
        outsize = ctypes.c_uint64(0)
        ret = _mach_vm_read_overwrite(
            self.task, address, size,
            ctypes.cast(buf, ctypes.c_void_p).value,
            ctypes.byref(outsize),
        )
        if ret != 0:
            return None
        return buf.raw[:outsize.value]

    def get_regions(self, rw_only=True):
        """Enumerate memory regions."""
        regions = []
        address = ctypes.c_uint64(0)
        size = ctypes.c_uint64(0)
        info = (ctypes.c_uint * 12)()
        info_count = ctypes.c_uint(12)
        obj = ctypes.c_uint(0)

        while True:
            info_count.value = 12
            ret = _mach_vm_region(
                self.task, ctypes.byref(address), ctypes.byref(size),
                VM_REGION_BASIC_INFO_64,
                ctypes.cast(info, ctypes.c_void_p),
                ctypes.byref(info_count), ctypes.byref(obj),
            )
            if ret != 0:
                break
            prot = info[0]
            if rw_only:
                if (prot & (VM_PROT_READ | VM_PROT_WRITE)) == (VM_PROT_READ | VM_PROT_WRITE):
                    regions.append((address.value, size.value))
            else:
                if prot & VM_PROT_READ:
                    regions.append((address.value, size.value))
            address.value += size.value

        return regions


# ── Helpers ──

def entropy(data):
    if not data:
        return 0.0
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    ent = 0.0
    for count in freq.values():
        p = count / len(data)
        ent -= p * math.log2(p)
    return ent


def is_plausible_key(data):
    if not data or len(data) < 32:
        return False
    if entropy(data[:32]) < 3.5:
        return False
    ascii_count = sum(1 for b in data[:32] if 0x20 <= b <= 0x7E)
    return ascii_count <= 24


def get_wechat_pid():
    result = subprocess.run(["pgrep", "-x", "WeChat"], capture_output=True, text=True)
    pids = result.stdout.strip().split()
    if not pids:
        raise RuntimeError("WeChat not running")
    return int(pids[0])


def find_db_storage_dir():
    pattern = os.path.expanduser(
        "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/"
        "xwechat_files/*/db_storage"
    )
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(f"No WeChat db_storage found at {pattern}")
    return max(matches, key=os.path.getmtime)


def collect_db_salts(db_storage_dir):
    """Walk db_storage/ and return {name: (salt_bytes, salt_hex, full_path)}."""
    dbs = {}
    for root, dirs, files in os.walk(db_storage_dir):
        for f in files:
            if not f.endswith(".db"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "rb") as fh:
                    header = fh.read(16)
                if len(header) < 16:
                    continue
                if header[:15] == b"SQLite format 3":
                    continue  # unencrypted
                rel = os.path.relpath(path, db_storage_dir)
                dbs[rel] = (header, header.hex(), path)
            except Exception:
                continue
    return dbs


def verify_hmac(key_hex, salt_bytes):
    """HMAC-SHA512 verification of a key against a DB's first page.
    Returns True if key decrypts page 1 correctly."""
    # This needs the full DB file; we'll verify via salt matching instead
    # for speed. Full verification is done with sqlcipher.
    pass


# ── Approach A: PRAGMA key string scan ──

PRAGMA_RE = re.compile(rb"x'([0-9a-fA-F]{64,192})'")


def scan_pragma_keys(proc, regions, verbose=True):
    """Scan RW memory for x'<hex>' PRAGMA key strings."""
    if verbose:
        print(f"[A] Scanning {len(regions)} RW regions for x'<hex>' patterns...")

    keys = {}  # (key_hex, salt_hex) -> addr
    total_scanned = 0
    chunk_size = 2 * 1024 * 1024

    for base, size in regions:
        if size > 500 * 1024 * 1024:
            continue
        off = 0
        while off < size:
            read_size = min(chunk_size, size - off)
            data = proc.read_memory(base + off, read_size)
            if not data:
                off += read_size
                continue
            total_scanned += len(data)

            for m in PRAGMA_RE.finditer(data):
                hex_str = m.group(1).decode("ascii").lower()
                key_hex = hex_str[:64]
                salt_hex = ""
                if len(hex_str) >= 96:
                    salt_hex = hex_str[64:96]
                elif len(hex_str) > 64:
                    salt_hex = hex_str[-32:] if len(hex_str) >= 96 else ""

                pair = (key_hex, salt_hex)
                if pair not in keys:
                    keys[pair] = base + off + m.start()
                    if verbose:
                        print(f"  [+] Key found at 0x{base + off + m.start():x} "
                              f"({len(hex_str)} hex chars)")

            # Overlap for boundary matches
            overlap = 200
            off += max(read_size - overlap, read_size)

    if verbose:
        print(f"[A] Scanned {total_scanned / 1024 / 1024:.1f} MB, "
              f"found {len(keys)} unique keys")
    return keys


# ── Approach B: Salt-proximity + codec_ctx pointer chasing ──

def scan_salt_proximity(proc, regions, db_salts, verbose=True):
    """Find raw salt bytes in memory, then search nearby for keys."""
    if verbose:
        print(f"\n[B] Searching for raw DB salts in {len(regions)} regions...")

    keys = {}  # (key_hex, salt_hex) -> addr
    chunk_size = 16 * 1024 * 1024

    for db_name, (salt_bytes, salt_hex, _) in db_salts.items():
        salt_addrs = []

        # Find salt in memory
        for base, size in regions:
            if size > 200 * 1024 * 1024:
                continue
            for off in range(0, size, chunk_size):
                read_size = min(chunk_size, size - off)
                data = proc.read_memory(base + off, read_size)
                if not data:
                    continue
                pos = 0
                while True:
                    idx = data.find(salt_bytes, pos)
                    if idx == -1:
                        break
                    salt_addrs.append(base + off + idx)
                    pos = idx + 1

        if verbose and salt_addrs:
            print(f"  {db_name}: salt found {len(salt_addrs)} times")

        # Check fixed offsets near each salt
        for salt_addr in salt_addrs:
            for offset in (-256, -192, -128, -96, -64, -32, 32, 64, 96, 128, 192, 256):
                chunk = proc.read_memory(salt_addr + offset, 32)
                if chunk and is_plausible_key(chunk):
                    key_hex = chunk.hex()
                    pair = (key_hex, salt_hex)
                    if pair not in keys:
                        keys[pair] = salt_addr
                        if verbose:
                            print(f"  [+] Candidate key near salt at offset {offset}")

        # Codec_ctx pointer chasing
        for salt_addr in salt_addrs:
            ptr_bytes = struct.pack("<Q", salt_addr)
            for base, size in regions:
                if size > 200 * 1024 * 1024:
                    continue
                for off in range(0, size, chunk_size):
                    read_size = min(chunk_size, size - off)
                    data = proc.read_memory(base + off, read_size)
                    if not data:
                        continue
                    pos = 0
                    while True:
                        idx = data.find(ptr_bytes, pos)
                        if idx == -1:
                            break
                        ptr_loc = base + off + idx

                        # Read structure around the pointer
                        ctx = proc.read_memory(ptr_loc - 64, 256)
                        if not ctx:
                            pos = idx + 1
                            continue

                        # Follow pointer-like values
                        for p_off in range(0, 256, 8):
                            if p_off + 8 > len(ctx):
                                break
                            val = struct.unpack("<Q", ctx[p_off:p_off + 8])[0]
                            if not (0x100000000 < val < 0x800000000000):
                                continue
                            pointed = proc.read_memory(val, 64)
                            if not pointed:
                                continue

                            for key_off in (0, 32):
                                chunk = pointed[key_off:key_off + 32]
                                if is_plausible_key(chunk):
                                    pair = (chunk.hex(), salt_hex)
                                    if pair not in keys:
                                        keys[pair] = ptr_loc
                                        if verbose:
                                            print(f"  [+] Candidate via codec_ctx at 0x{ptr_loc:x}")

                            # One more level of indirection
                            for p2_off in range(0, min(64, len(pointed)), 8):
                                p2 = struct.unpack("<Q", pointed[p2_off:p2_off + 8])[0]
                                if not (0x100000000 < p2 < 0x800000000000):
                                    continue
                                deep = proc.read_memory(p2, 64)
                                if not deep:
                                    continue
                                for key_off in (0, 32):
                                    chunk = deep[key_off:key_off + 32]
                                    if is_plausible_key(chunk):
                                        pair = (chunk.hex(), salt_hex)
                                        if pair not in keys:
                                            keys[pair] = ptr_loc

                        pos = idx + 1

    if verbose:
        print(f"[B] Found {len(keys)} candidate keys")
    return keys


# ── Verification ──

def verify_with_sqlcipher(key_hex, db_path, verbose=False):
    """Try to decrypt a DB with sqlcipher to verify the key."""
    sqlcipher = None
    for path in ["/opt/homebrew/bin/sqlcipher", "/usr/local/bin/sqlcipher"]:
        if os.path.isfile(path):
            sqlcipher = path
            break
    if not sqlcipher:
        import shutil
        sqlcipher = shutil.which("sqlcipher")
    if not sqlcipher:
        return None  # can't verify

    configs = [(4, 4096), (4, 1024), (3, 4096), (3, 1024)]
    for compat, page_size in configs:
        cmd = (
            f"PRAGMA key = \"x'{key_hex}'\";\n"
            f"PRAGMA cipher_compatibility = {compat};\n"
            f"PRAGMA cipher_page_size = {page_size};\n"
            "SELECT 'OK:' || name FROM sqlite_master WHERE type='table' LIMIT 3;\n"
        )
        try:
            result = subprocess.run(
                [sqlcipher, db_path], input=cmd,
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip().startswith("OK:"):
                    return f"compat={compat},page={page_size}"
        except Exception:
            pass
    return None


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="WeChat macOS key extractor")
    parser.add_argument("--pid", type=int, help="WeChat PID (auto-detect if omitted)")
    parser.add_argument("--verify", action="store_true", help="Verify keys with sqlcipher")
    parser.add_argument("--approach", choices=["a", "b", "both"], default="both",
                        help="a=pragma scan, b=salt/codec_ctx, both=try both")
    args = parser.parse_args()

    print("=" * 60)
    print("  WeChat macOS Key Extractor (Python)")
    print("=" * 60)

    # Get PID
    pid = args.pid or get_wechat_pid()
    print(f"PID: {pid}")

    # Collect DB salts
    db_storage = find_db_storage_dir()
    db_salts = collect_db_salts(db_storage)
    print(f"Encrypted DBs: {len(db_salts)}")
    for name, (_, salt_hex, _) in sorted(db_salts.items()):
        print(f"  {name}: salt={salt_hex}")

    # Connect to process
    proc = MachProcess(pid)
    rw_regions = proc.get_regions(rw_only=True)
    all_regions = proc.get_regions(rw_only=False)
    print(f"RW regions: {len(rw_regions)}, All readable: {len(all_regions)}")

    all_keys = {}  # (key_hex, salt_hex) -> addr

    # Approach A
    if args.approach in ("a", "both"):
        keys_a = scan_pragma_keys(proc, rw_regions)
        all_keys.update(keys_a)

    # Approach B
    if args.approach in ("b", "both") and (not all_keys or args.approach == "both"):
        keys_b = scan_salt_proximity(proc, rw_regions, db_salts)
        all_keys.update(keys_b)

    print(f"\nTotal unique keys: {len(all_keys)}")

    # Match keys to DBs
    results = []
    for (key_hex, salt_hex), addr in all_keys.items():
        matched_db = None
        for db_name, (_, db_salt_hex, db_path) in db_salts.items():
            if salt_hex and salt_hex == db_salt_hex:
                matched_db = db_name
                break
        entry = {
            "key": key_hex,
            "salt": salt_hex,
            "pragma": f"x'{key_hex}{salt_hex}'",
            "db": matched_db or "(unknown)",
            "addr": f"0x{addr:x}",
        }

        # Verify if requested
        if args.verify and matched_db:
            db_path = db_salts[matched_db][2]
            info = verify_with_sqlcipher(key_hex, db_path)
            entry["verified"] = info or "failed"
            if info:
                print(f"  VERIFIED: {matched_db} -> {info}")

        results.append(entry)
        print(f"  {entry['db']:25s} {key_hex} {'pragma' if salt_hex else 'raw'}")

    # Write output files
    if results:
        with open("wechat_keys.json", "w") as f:
            json.dump(results, f, indent=2)

        # all_keys.json for decrypt_db.py compatibility
        db_keys = {}
        for entry in results:
            if entry["db"] != "(unknown)":
                db_keys[entry["db"]] = {"enc_key": entry["key"]}
        with open("all_keys.json", "w") as f:
            json.dump(db_keys, f, indent=2)

        print(f"\nWritten: wechat_keys.json, all_keys.json")
        matched = sum(1 for e in results if e["db"] != "(unknown)")
        print(f"Matched {matched}/{len(results)} keys to DBs")
    else:
        print("\nNo keys found. Ensure:")
        print("  1. WeChat is running and logged in")
        print("  2. Running as root (sudo)")
        print("  3. WeChat is ad-hoc signed")

    return 0 if results else 2


if __name__ == "__main__":
    sys.exit(main())
