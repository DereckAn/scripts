#!/usr/bin/env python3
"""Decode known Falchion boot structures without claiming boot sufficiency.

Supports a full vendor image (base 0) and the application-only region produced
by the USB backup tool (base 0x10000). Passing these checks means that the known
container constraints are internally consistent; it does not prove an edited
image will execute correctly or that every ROM/bootloader condition is known.

No device access. Examples:
    python3 tool/analyze_boot_structures.py
    python3 tool/analyze_boot_structures.py installed-app.bin --base 0x10000
"""
import argparse
from pathlib import Path
import struct

from analyze_candidate_integrity import (
    DEFAULT_BIN, FLASH_BASE, FWIN_OFF, image_index, parse_records,
)

SNC_MAGIC = b"SNC7320A"
BCFG_MAGIC = b"SN_BCFG\x00"
FWIN_MAGIC = b"SN_FWIN\x00"
BCFG_OFF = 0x200
SLOTS_OFF = 0x208
GATE_OFF = 0x18
ENTRY_PTR_OFF = 0x10
CONTAINERS = {
    "primary": (0x00000, 0x60001000),
    "backup": (0x60000, 0x60062000),
}
EXPECTED_CONTAINER_SIZE = 0x10000
SP_RANGES = ((0x18000000, 0x18040000), (0x20000000, 0x20001000))

# Recorded so a passing run is never read as "this image boots".
UNRESOLVED = (
    "FUN_000029d4 is not decompiled; its role in the boot path is unknown.",
    "The top-level comparison applied to the selected entry value before the "
    "jump is not recovered, so the caller's accept/reject rule is unknown.",
    "Any ROM/first-stage conditions ahead of the bootloader are unexamined.",
)


def available(data, image_base, flash_off, size):
    index = flash_off - image_base
    return 0 <= index and index + size <= len(data)


def read_u32(data, image_base, flash_off):
    pos = image_index(flash_off, image_base, 4, len(data))
    return struct.unpack_from("<I", data, pos)[0]


def known_boot_checks(data, image_base=0):
    """Return (present, skipped, records, checks) for the static constraints
    that are observable in this image.

    Containers absent from a partial image are reported as skipped rather than
    silently dropped, so a passing app-only run is never mistaken for a full one.
    """
    checks = {}
    present_containers, skipped_containers = [], []
    for name, (off, expected_ptr) in CONTAINERS.items():
        if not available(data, image_base, off, SLOTS_OFF + 8):
            skipped_containers.append(name)
            continue
        present_containers.append(name)
        pos = image_index(off, image_base, SLOTS_OFF + 8, len(data))
        boot_ptr, size = struct.unpack_from("<2I", data, pos + 0x10)
        slot0, slot1 = struct.unpack_from("<2I", data, pos + SLOTS_OFF)
        checks[f"{name} SNC7320A magic"] = data[pos:pos + 8] == SNC_MAGIC
        checks[f"{name} SN_BCFG magic"] = (
            data[pos + BCFG_OFF:pos + BCFG_OFF + 8] == BCFG_MAGIC)
        checks[f"{name} bootloader pointer"] = boot_ptr == expected_ptr
        checks[f"{name} declared size"] = size == EXPECTED_CONTAINER_SIZE
        checks[f"{name} slot0 -> SN_FWIN"] = slot0 == FLASH_BASE + FWIN_OFF
        checks[f"{name} slot1 empty"] = slot1 == 0

    header = image_index(FWIN_OFF, image_base, 0x34, len(data))
    checks["SN_FWIN magic"] = data[header:header + 8] == FWIN_MAGIC
    checks["SN_FWIN CRC-enable gate nonzero"] = (
        struct.unpack_from("<I", data, header + GATE_OFF)[0] != 0)

    records = parse_records(data, image_base)
    entry = struct.unpack_from("<I", data, header + ENTRY_PTR_OFF)[0]
    checks["entry equals record[0] address"] = entry == records[0][1]
    checks["record ranges inside application region"] = all(
        0x60010000 <= addr and length > 0 and addr + length <= 0x6007C000
        for _idx, addr, length, _checksum, _dst in records)

    entry_off = entry - FLASH_BASE
    entry_pos = image_index(entry_off, image_base, 8, len(data))
    sp, reset = struct.unpack_from("<2I", data, entry_pos)
    checks["entry initial-SP in observed RAM ranges"] = any(
        lo < sp <= hi for lo, hi in SP_RANGES)
    checks["entry reset vector is Thumb and within record[0] length"] = (
        bool(reset & 1) and (reset & ~1) < records[0][2])
    return present_containers, skipped_containers, records, checks


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_BIN)
    parser.add_argument(
        "--base", type=lambda value: int(value, 0), default=0,
        help="flash offset represented by image byte zero (USB app dump: 0x10000)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    data = args.image.read_bytes()
    print("PROGRAM analyze_boot_structures")
    print("PURPOSE offline known boot-container checks")
    print(f"IMAGE {args.image}")
    print(f"IMAGE_BASE 0x{args.base:x}")
    print(f"IMAGE_SIZE 0x{len(data):x}")
    try:
        containers, skipped, records, checks = known_boot_checks(data, args.base)
    except (ValueError, struct.error) as exc:
        print(f"RESULT known_checks_ok=False error={exc}")
        return 1

    print(f"PRESENT_CONTAINERS {','.join(containers) if containers else 'none'}")
    for name in skipped:
        print(f"  SKIP {name} container: absent from this image "
              f"(base 0x{args.base:x}, size 0x{len(data):x})")
    for index, addr, length, checksum, dst in records:
        print(f"RECORD {index} addr=0x{addr:08x} len=0x{length:x} "
              f"checksum=0x{checksum:08x} dst=0x{dst:08x}")
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    ok = all(checks.values())
    print(f"RESULT known_checks_ok={ok} checks_run={len(checks)} "
          f"containers_skipped={len(skipped)}")
    for line in UNRESOLVED:
        print(f"UNRESOLVED {line}")
    print("LIMITATION Passing means the known container constraints are "
          "internally consistent. It does not prove an edited image boots.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
