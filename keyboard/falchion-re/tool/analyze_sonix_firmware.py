#!/usr/bin/env python3
"""Read-only structural inspection for the preserved SNC7320 firmware image.

This tool never writes to the input image.  Field names that are not backed by
public format documentation are intentionally described as candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import zlib
from pathlib import Path


EXPECTED_SIZE = 0x7C000
EXPECTED_SHA256 = "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d"
FLASH_BASE = 0x60000000


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def offsets(data: bytes, marker: bytes) -> list[int]:
    found: list[int] = []
    start = 0
    while True:
        start = data.find(marker, start)
        if start < 0:
            return found
        found.append(start)
        start += 1


def page_kind(page: bytes) -> str:
    if page == b"\x00" * len(page):
        return "all-00"
    if page == b"\xff" * len(page):
        return "all-FF"
    return "content"


def grouped_pages(data: bytes, page_size: int = 0x1000) -> list[tuple[int, int, str]]:
    groups: list[tuple[int, int, str]] = []
    for start in range(0, len(data), page_size):
        kind = page_kind(data[start : start + page_size])
        if groups and groups[-1][2] == kind:
            previous = groups[-1]
            groups[-1] = (previous[0], start + page_size, kind)
        else:
            groups.append((start, min(start + page_size, len(data)), kind))
    return groups


def print_vector(data: bytes, offset: int, name: str) -> None:
    stack = u32(data, offset)
    reset = u32(data, offset + 4)
    plausible = 0x18000000 <= stack < 0x18100000 and bool(reset & 1)
    print(
        f"{name}: file=0x{offset:05x} initial_sp=0x{stack:08x} "
        f"reset=0x{reset:08x} plausible_cortex_m={plausible}"
    )


def main() -> int:
    default_image = Path(__file__).resolve().parents[1] / "dumps/vendor/M605_V01_00_58.bin"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=default_image)
    args = parser.parse_args()

    data = args.image.read_bytes()
    digest = hashlib.sha256(data).hexdigest()

    print(f"path={args.image}")
    print(f"size={len(data)} (0x{len(data):x}) expected=0x{EXPECTED_SIZE:x} match={len(data) == EXPECTED_SIZE}")
    print(f"sha256={digest} expected_match={digest == EXPECTED_SHA256}")

    print("\nmarkers:")
    for marker in (b"SNC7320A", b"SN_BCFG", b"SN_FWIN"):
        values = ", ".join(f"0x{x:05x}" for x in offsets(data, marker))
        print(f"  {marker.decode()}: {values}")

    print("\nSNC7320A header candidates:")
    for header in offsets(data, b"SNC7320A"):
        target = u32(data, header + 0x10)
        size = u32(data, header + 0x14)
        mapped = target - FLASH_BASE if FLASH_BASE <= target < FLASH_BASE + len(data) else None
        mapped_text = f"0x{mapped:05x}" if mapped is not None else "outside-file"
        print(
            f"  header=0x{header:05x} target_field=0x{target:08x} "
            f"size_field=0x{size:x} target_as_file_offset={mapped_text}"
        )

    print("\nSN_FWIN header at 0x10000:")
    version = data[0x10008 : 0x10010].split(b"\0", 1)[0].decode("ascii", "replace")
    print(f"  embedded_format_version={version!r}")
    print("  raw words +0x10..+0x4c:")
    for relative in range(0x10, 0x50, 4):
        print(f"    +0x{relative:02x}: 0x{u32(data, 0x10000 + relative):08x}")

    payloads = (
        ("candidate-A", 0x10024, 0x10028, 0x1002C),
        ("candidate-B", 0x10034, 0x10038, 0x1003C),
    )
    print("\ncandidate payload records (format interpretation remains provisional):")
    for name, address_offset, length_offset, crc_offset in payloads:
        address = u32(data, address_offset)
        length = u32(data, length_offset)
        stored_crc = u32(data, crc_offset)
        file_offset = address - FLASH_BASE
        end = file_offset + length
        in_file = 0 <= file_offset <= end <= len(data)
        actual_crc = zlib.crc32(data[file_offset:end]) if in_file else None
        actual_text = f"0x{actual_crc:08x}" if actual_crc is not None else "n/a"
        print(
            f"  {name}: address=0x{address:08x} file=0x{file_offset:05x} "
            f"length=0x{length:x} end=0x{end:05x} stored=0x{stored_crc:08x} "
            f"crc32={actual_text} match={actual_crc == stored_crc if actual_crc is not None else False}"
        )

    print("\nverified vector-table candidates:")
    print_vector(data, 0x01000, "primary bootloader")
    print_vector(data, 0x11000, "application candidate-A")
    print_vector(data, 0x62000, "embedded bootloader code")
    print_vector(data, 0x74000, "RAM-resident image (runtime base 0x18038000)")

    print("\nexact repetition checks:")
    comparisons = (
        (0x00000, 0x61000, 0x10000, "complete first 64 KiB vs embedded copy"),
        (0x01000, 0x62000, 0x0F000, "bootloader code/data after first header page"),
    )
    for left, right, length, description in comparisons:
        print(
            f"  {description}: 0x{left:05x}-0x{left + length:05x} == "
            f"0x{right:05x}-0x{right + length:05x}: "
            f"{data[left:left + length] == data[right:right + length]}"
        )

    print("\n4 KiB page groups:")
    for start, end, kind in grouped_pages(data):
        print(f"  0x{start:05x}-0x{end:05x}: {kind}")

    print("\nterminal words (integrity meaning unresolved):")
    for offset in (0x0FFFC, 0x70FFC, 0x7BFFC):
        print(f"  file=0x{offset:05x} value=0x{u32(data, offset):08x}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
