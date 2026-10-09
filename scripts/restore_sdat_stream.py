#!/usr/bin/env python3
"""Restore the 'new' blocks of a full Android block OTA from stdin.

Only full-image transfer lists with new/zero/erase commands are supported.
The input is the *decompressed* system.new.dat stream.  The output file is a
sparse image; zero and erase ranges are represented by unwritten holes.

This deliberately refuses incremental operations (move, stash, bsdiff, etc.)
so an unsupported package cannot produce a misleading but corrupt image.
"""

import argparse
import os
import sys
from pathlib import Path

BLOCK_SIZE = 4096
COPY_CHUNK_BYTES = 8 * 1024 * 1024


def parse_ranges(raw: str, line_no: int):
    try:
        vals = [int(s) for s in raw.split(",")]
    except ValueError as exc:
        raise ValueError(f"line {line_no}: malformed block ranges") from exc
    if not vals or vals[0] <= 0 or vals[0] % 2 or len(vals) != vals[0] + 1:
        raise ValueError(f"line {line_no}: invalid range count")
    pairs = []
    for i in range(1, len(vals), 2):
        start, end = vals[i], vals[i + 1]
        if start < 0 or end <= start:
            raise ValueError(f"line {line_no}: invalid range ({start}, {end})")
        pairs.append((start, end))
    return pairs


def parse_transfer_list(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4:
        raise ValueError("transfer list is too short")
    version = int(lines[0].strip())
    if version not in (2, 3, 4):
        raise ValueError(f"unsupported transfer list version: {version}")
    expected_new_blocks = int(lines[1].strip())
    # Lines 3 and 4 describe stash capacity in Android transfer-list v2+.
    commands = []
    regions = []
    new_blocks = 0
    max_end = 0
    for idx, raw in enumerate(lines[4:], start=5):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split(None, 1)
        cmd = parts[0]
        if cmd not in ("new", "zero", "erase") or len(parts) != 2:
            raise ValueError(f"line {idx}: unsupported OTA command '{cmd}'; only FULL images supported")
        ranges = parse_ranges(parts[1].strip(), idx)
        for start, end in ranges:
            regions.append((start, end, idx))
            max_end = max(max_end, end)
            if cmd == "new":
                new_blocks += end - start
        commands.append((cmd, ranges))
    if new_blocks != expected_new_blocks:
        raise ValueError(f"new block total mismatch: {new_blocks} != {expected_new_blocks}")
    # No region may be written twice. This makes sparse zero/erase holes correct.
    regions.sort()
    for prev, cur in zip(regions, regions[1:]):
        if prev[1] > cur[0]:
            raise ValueError(f"overlapping OTA ranges on lines {prev[2]} and {cur[2]}")
    if not commands or not new_blocks:
        raise ValueError("empty full-image transfer list")
    return commands, max_end, new_blocks


def restore(transfer_list: Path, destination: Path):
    commands, max_end, new_blocks = parse_transfer_list(transfer_list)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    stream = sys.stdin.buffer
    restored = 0
    with destination.open("xb", buffering=0) as image:
        image.truncate(max_end * BLOCK_SIZE)
        for cmd, ranges in commands:
            if cmd != "new":
                continue  # zero/erase are sparse zero-filled holes in new file
            for start, end in ranges:
                image.seek(start * BLOCK_SIZE)
                to_copy = (end - start) * BLOCK_SIZE
                while to_copy:
                    segment = stream.read(min(to_copy, COPY_CHUNK_BYTES))
                    if not segment:
                        raise IOError("truncated system.new.dat stream")
                    image.write(segment)
                    restored += len(segment)
                    to_copy -= len(segment)
        if stream.read(1):
            raise IOError("unexpected trailing decompressed data")
    if restored != new_blocks * BLOCK_SIZE:
        raise IOError("restored block byte count mismatch")
    print(f"Recovered sparse image: {destination}")
    print(f"Restored bytes: {restored}; logical size: {max_end * BLOCK_SIZE}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transfer_list", type=Path)
    parser.add_argument("output_image", type=Path)
    args = parser.parse_args()
    try:
        restore(args.transfer_list, args.output_image)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
