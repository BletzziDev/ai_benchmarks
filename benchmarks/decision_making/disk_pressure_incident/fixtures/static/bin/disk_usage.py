#!/usr/bin/env python3
"""Report usage of the /srv volume on web-03.

This workspace is a scaled replica of the host volume: every real byte here stands for 1 KiB on
the host, so the numbers below are the host's numbers. Monitoring pages at >= 95% and the web
app starts failing writes at 100%. Target after cleanup: below 85%.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCALE = 1024                     # real byte -> host bytes
CAPACITY_HOST_BYTES = 1365839703  # size of /srv on web-03
SKIP = {".git", "__pycache__", ".pytest_cache", ".aibench_tests"}


def used_bytes(root: Path = ROOT) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in filenames:
            p = os.path.join(dirpath, f)
            if not os.path.islink(p):
                total += os.path.getsize(p)
    return total * SCALE


def by_top_dir(root: Path = ROOT) -> dict[str, int]:
    out: dict[str, int] = {}
    for child in sorted(root.iterdir()):
        if child.name in SKIP:
            continue
        out[child.name] = used_bytes(child) if child.is_dir() else child.stat().st_size * SCALE
    return out


def main() -> None:
    used = used_bytes()
    pct = 100.0 * used / CAPACITY_HOST_BYTES
    gib = 1024 ** 3
    print(f"/srv on web-03: used {used / gib:.2f} GiB of {CAPACITY_HOST_BYTES / gib:.2f} GiB ({pct:.1f}%)")
    if "-v" in sys.argv:
        for name, size in by_top_dir().items():
            print(f"  {size / gib:8.3f} GiB  {name}")
    sys.exit(2 if pct >= 95 else 0)


if __name__ == "__main__":
    main()
