# filename: verify_hash_pair.py

import sys
import os
import hashlib

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    if len(sys.argv) != 3:
        print("usage: python verify_hash_pair.py <filename> <hashfilename>")
        sys.exit(2)

    file_path = os.path.expanduser(sys.argv[1].strip())
    hash_path = os.path.expanduser(sys.argv[2].strip())

    if not os.path.isfile(file_path):
        print(f"corrupted (missing file): {file_path}")
        sys.exit(1)
    if not os.path.isfile(hash_path):
        print(f"corrupted (missing hash): {hash_path}")
        sys.exit(1)

    try:
        actual = sha256_file(file_path)
    except Exception as e:
        print(f"corrupted (read error): {e}")
        sys.exit(1)

    try:
        with open(hash_path, "r", encoding="utf-8") as f:
            expected = f.read().strip()
    except Exception as e:
        print(f"corrupted (hash read error): {e}")
        sys.exit(1)

    if actual == expected:
        print("good file")
        sys.exit(0)
    else:
        print("corrupted")
        sys.exit(1)

if __name__ == "__main__":
    main()
# --- End of file ---

