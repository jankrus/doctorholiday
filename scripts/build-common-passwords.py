#!/usr/bin/env python3
"""Rebuild backend/src/doctorholiday/auth/common_passwords.txt.gz (BR-01, #14).

The blocklist of common passwords that registration rejects (NIST SP 800-63B, 3.1.1.2). Sources
are two SecLists lists (MIT licence) at a pinned commit, verified by SHA-256:

- the UK NCSC's 100,000 most used passwords from breaches,
- the top 1,000,000 of the xato.net "10 million passwords" set.

Only entries the policy would otherwise allow (12-128 characters) are kept, compared
case-insensitively (casefold), sorted and deduplicated. The output is gzipped without a timestamp,
so the same sources always give the same bytes. Compressed, it is also skipped by secret scanners,
which would flag random-looking entries of the list as leaked keys.

Usage (stdlib only, from the repo root): python3 -I scripts/build-common-passwords.py
"""

import gzip
import hashlib
import io
import sys
import urllib.request
from pathlib import Path

SECLISTS_COMMIT = "97f5398ef4ab2bc7d5961e6b1d3d7157830d86f2"
BASE_URL = (
    "https://raw.githubusercontent.com/danielmiessler/SecLists/"
    f"{SECLISTS_COMMIT}/Passwords/Common-Credentials/"
)
SOURCES = {
    "100k-most-used-passwords-NCSC.txt": (
        "c2e5696882c603b76bb67a47ee970897e5a76fc4c3f5547abe3d0ca340c576e0"
    ),
    "xato-net-10-million-passwords-1000000.txt": (
        "424a3e03a17df0a2bc2b3ca749d81b04e79d59cb7aeec8876a5a3f308d0caf51"
    ),
}
MIN_LENGTH, MAX_LENGTH = 12, 128  # BR-01; shorter or longer passwords are rejected anyway
OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "backend/src/doctorholiday/auth/common_passwords.txt.gz"
)


def _download(name: str, sha256: str) -> bytes:
    with urllib.request.urlopen(BASE_URL + name, timeout=60) as response:  # noqa: S310
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        sys.exit(f"{name}: SHA-256 does not match the pinned value")
    return data


def main() -> None:
    entries: set[str] = set()
    for name, sha256 in SOURCES.items():
        for raw in _download(name, sha256).splitlines():
            try:
                line = raw.decode("utf-8").strip("\r")
            except UnicodeDecodeError:
                continue
            if MIN_LENGTH <= len(line) <= MAX_LENGTH:
                entries.add(line.casefold())

    text = "".join(f"{entry}\n" for entry in sorted(entries)).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(text)
    OUTPUT.write_bytes(buffer.getvalue())
    print(f"{OUTPUT.name}: {len(entries)} entries, {len(buffer.getvalue())} bytes")


if __name__ == "__main__":
    main()
