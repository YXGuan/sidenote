#!/usr/bin/env python3
"""Check tracked and new non-ignored publication files for private paths and common credential shapes.

This is a narrow regression check, not a complete secret or dependency audit.
Values are never printed in diagnostics.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = {".local", ".local-tools", "node_modules", ".hallmark", "vault", ".demo-vault", "upstream", "__pycache__"}
SECRET = re.compile(rb"(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)")


def main():
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    errors = []
    for name in filter(None, files):
        path = Path(name)
        if PRIVATE & set(path.parts) or path.name == ".DS_Store" or (path.name.startswith(".env") and path.name != ".env.example"):
            errors.append(f"Private/generated path tracked: {name}")
        if path.parts[:2] in (("hypothesis", "client"), ("hypothesis", "browser-extension")):
            errors.append(f"Nested upstream source tracked instead of a patch: {name}")
        if path.suffix.lower() in (".png", ".jpg", ".ttf", ".woff2"):
            continue
        source = ROOT / path
        if source.is_file():
            for number, line in enumerate(source.read_bytes().splitlines(), 1):
                if SECRET.search(line):
                    errors.append(f"Potential credential at {name}:{number} (value withheld)")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Publication path/credential-pattern checks passed (not an exhaustive audit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
