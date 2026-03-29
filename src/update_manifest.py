#!/usr/bin/env python3
"""
update_manifest.py  —  eNDinomics manifest maintenance tool
Run from: /Users/satish/ws/c-eNDinomics/src/

Usage:
  python3 update_manifest.py              # verify all hashes, report mismatches
  python3 update_manifest.py --fix        # auto-update hashes for changed files
  python3 update_manifest.py --fix file1 file2  # update only specific files
  python3 update_manifest.py --add path  # add a new file to tracking
  python3 update_manifest.py --remove path  # remove a file from tracking
  python3 update_manifest.py --show      # print current manifest table
"""

import hashlib, json, os, sys
from pathlib import Path

MANIFEST_PATH = "manifest.lock"
SCRIPT_DIR    = Path(__file__).parent

def sha256_short(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]

def load_manifest() -> dict:
    with open(MANIFEST_PATH) as f:
        return json.load(f)

def save_manifest(m: dict) -> None:
    tracked = sorted(m["hashes"].keys())
    m["tracked"] = tracked
    m["_self_crc"] = hashlib.sha256(
        json.dumps(tracked, sort_keys=True).encode()
    ).hexdigest()[:16]
    with open(MANIFEST_PATH, "w") as f:
        json.dump(m, f, indent=2)

def normalize_path(p: str) -> str:
    """Convert absolute or repo-relative path to manifest key (relative to src/)."""
    p = str(p).replace("\\", "/")
    # Strip leading src/ if present
    if p.startswith("src/"):
        p = p[4:]
    # Strip absolute prefix up to /src/
    if "/src/" in p:
        p = p.split("/src/", 1)[1]
    return p.lstrip("./")

def check(m: dict) -> list[tuple[str, str, str, bool]]:
    """Return list of (key, manifest_hash, file_hash, matches) for all tracked files."""
    results = []
    for key, mhash in sorted(m["hashes"].items()):
        fpath = SCRIPT_DIR / key
        if not fpath.exists():
            results.append((key, mhash, "MISSING", False))
        else:
            fhash = sha256_short(str(fpath))
            results.append((key, mhash, fhash, mhash == fhash))
    return results

def cmd_show(m: dict) -> None:
    results = check(m)
    print(f"\n{'File':<50} {'Hash':>16}")
    print("-" * 68)
    for key, mhash, _, _ in results:
        print(f"  {key:<48} {mhash}")
    print(f"\n{len(results)} tracked files  ·  _self_crc: {m.get('_self_crc','?')}\n")

def cmd_verify(m: dict) -> int:
    results = check(m)
    ok = sum(1 for *_, match in results if match)
    fail = len(results) - ok
    print(f"\n{'File':<48} {'Manifest':>16}  {'On disk':>16}  Status")
    print("-" * 95)
    for key, mhash, fhash, match in results:
        status = "✅ match" if match else ("❌ MISMATCH" if fhash != "MISSING" else "❌ MISSING")
        line = f"  {key:<46} {mhash:>16}  {fhash:>16}  {status}"
        print(line)
    print()
    if fail == 0:
        print(f"✅ ALL {ok} FILES MATCH\n")
    else:
        print(f"❌ {fail} mismatch(es), {ok} matched\n")
    return fail

def cmd_fix(m: dict, targets: list[str] | None = None) -> None:
    results = check(m)
    updated = []
    for key, mhash, fhash, match in results:
        if fhash == "MISSING":
            print(f"  ⚠  SKIP  {key}  (file not found on disk)")
            continue
        if targets and key not in targets:
            continue
        if not match:
            m["hashes"][key] = fhash
            updated.append((key, mhash, fhash))
    if not updated:
        print("\n✅ Nothing to update — all hashes already match.\n")
        return
    save_manifest(m)
    print(f"\n  Updated {len(updated)} hash(es):")
    for key, old, new in updated:
        print(f"    {key}")
        print(f"      {old}  →  {new}")
    n = len(m["hashes"])
    print(f"\n  manifest.lock saved  ·  {n} tracked files  ·  _self_crc: {m['_self_crc']}\n")
    assert n == 34, f"⚠  WARNING: expected 34 files, got {n}"

def cmd_add(m: dict, raw_path: str) -> None:
    key = normalize_path(raw_path)
    fpath = SCRIPT_DIR / key
    if not fpath.exists():
        print(f"❌ File not found: {fpath}")
        sys.exit(1)
    if key in m["hashes"]:
        print(f"⚠  Already tracked: {key}  (use --fix to refresh hash)")
        return
    fhash = sha256_short(str(fpath))
    m["hashes"][key] = fhash
    save_manifest(m)
    n = len(m["hashes"])
    print(f"\n  ✅ Added  {key}  {fhash}")
    print(f"  manifest.lock saved  ·  {n} tracked files\n")

def cmd_remove(m: dict, raw_path: str) -> None:
    key = normalize_path(raw_path)
    if key not in m["hashes"]:
        print(f"⚠  Not tracked: {key}")
        return
    del m["hashes"][key]
    save_manifest(m)
    n = len(m["hashes"])
    print(f"\n  ✅ Removed  {key}")
    print(f"  manifest.lock saved  ·  {n} tracked files\n")

def main() -> None:
    os.chdir(SCRIPT_DIR)
    args = sys.argv[1:]
    m = load_manifest()

    if not args or args[0] == "--verify":
        sys.exit(cmd_verify(m))

    elif args[0] == "--show":
        cmd_show(m)

    elif args[0] == "--fix":
        targets = None
        if len(args) > 1:
            targets = [normalize_path(a) for a in args[1:]]
        cmd_fix(m, targets)

    elif args[0] == "--add":
        if len(args) < 2:
            print("Usage: update_manifest.py --add <path>")
            sys.exit(1)
        cmd_add(m, args[1])

    elif args[0] == "--remove":
        if len(args) < 2:
            print("Usage: update_manifest.py --remove <path>")
            sys.exit(1)
        cmd_remove(m, args[1])

    else:
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
