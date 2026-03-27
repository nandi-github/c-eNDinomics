#!/usr/bin/env python3
"""
rebuild_manifest.py — verify disk files match Claude's expected hashes.

The manifest.lock is Claude's voucher: "I provided these files with these hashes."
checkupdates compares disk hashes against Claude's manifest to catch:
  - Files that weren't copied from Claude's outputs
  - Files that were accidentally modified
  - Version drift (running old code)

This script ONLY checks/updates files already in manifest["hashes"].
It NEVER adds files Claude hasn't explicitly provided.

Usage (from src/):
    python3 rebuild_manifest.py           # show current status (no changes)
    python3 rebuild_manifest.py --write   # update hashes for Claude-provided files
                                          # only use --write after copying Claude's outputs
"""

import argparse
import hashlib
import json
import os
import sys


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true",
                        help="Update manifest hashes from disk (run after copying Claude outputs)")
    parser.add_argument("--manifest", default="manifest.lock")
    args = parser.parse_args()

    src_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(src_dir, args.manifest)

    if not os.path.isfile(manifest_path):
        print(f"ERROR: {manifest_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        data = json.load(f)

    # Only check files Claude has explicitly provided
    claude_files = data.get("hashes", {})

    print(f"\n{'File':<50} {'Claude hash':18} {'Disk hash':18} Status")
    print("-" * 100)

    mismatches = []
    missing = []
    new_hashes = {}

    for rel_path, claude_hash in sorted(claude_files.items()):
        abs_path = os.path.join(src_dir, rel_path)
        if not os.path.isfile(abs_path):
            missing.append(rel_path)
            print(f"  {rel_path:<48} {claude_hash:<18} {'(missing)':18} ❌ NOT ON DISK")
            new_hashes[rel_path] = claude_hash  # preserve Claude's hash
            continue

        disk_hash = sha256_file(abs_path)
        new_hashes[rel_path] = disk_hash if args.write else claude_hash

        if disk_hash == claude_hash:
            status = "✅ match"
        else:
            mismatches.append(rel_path)
            status = "❌ MISMATCH"

        print(f"  {rel_path:<48} {claude_hash:<18} {disk_hash:<18} {status}")

    print()
    print(f"  Claude-provided files tracked: {len(claude_files)}")
    print(f"  Matches:    {len(claude_files) - len(mismatches) - len(missing)}")
    print(f"  Mismatches: {len(mismatches)}")
    print(f"  Missing:    {len(missing)}")

    if not args.write:
        if mismatches or missing:
            print("\n  ⚠  Disk differs from Claude's manifest — copy Claude's outputs and re-run --write")
        else:
            print("\n  ✅ All Claude-provided files match disk")
        return

    data["hashes"] = new_hashes
    data["_self_crc"] = hashlib.sha256(
        json.dumps(data["tracked"], sort_keys=True).encode()
    ).hexdigest()[:16]

    with open(manifest_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n  ✅ manifest.lock updated — {len(new_hashes)} Claude-provided entries")
    if mismatches:
        print(f"  ⚠  {len(mismatches)} file(s) had mismatches — hashes updated to disk values")
        print("     Make sure you intended to update these files.")


if __name__ == "__main__":
    main()
