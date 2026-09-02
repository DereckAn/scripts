#!/usr/bin/env python3
"""Offline integrity analysis for full or application-only Falchion images.

The bootloader stores a sum of independent IEEE CRC-32 values, one per
0x10000-byte chunk, in each SN_FWIN record. The final word of the primary
bootloader region and application region is an additive 32-bit word sum.

No device access. Examples:
    python3 tool/analyze_candidate_integrity.py
    python3 tool/analyze_candidate_integrity.py installed-app.bin --base 0x10000
"""
import argparse
import binascii
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BIN = ROOT / "dumps/vendor/M605_V01_00_58.bin"

M = 0xFFFFFFFF
FLASH_BASE = 0x60000000
FWIN_OFF = 0x10000
REC0 = FWIN_OFF + 0x24
REC_STRIDE = 0x10
MAX_RECORDS = 8
CHUNK = 0x10000
WORD_SUM_REGIONS = {
    "bootloader": (0x00000, 0x10000),
    "application": (0x10000, 0x7C000),
}


def crc32(data, init=0):
    return binascii.crc32(data, init) & M


def chunked_crc_sum(data, off, length, chunk=CHUNK):
    """Reproduce FUN_00005028 using indices into *data*."""
    if off < 0 or length <= 0 or off + length > len(data):
        raise ValueError("CRC range is outside the supplied image")
    acc, pos, rem = 0, off, length
    while rem:
        size = min(rem, chunk)
        acc = (acc + crc32(data[pos:pos + size])) & M
        pos += size & 0xFFFFFFFC
        rem -= size
    return acc


def word_sum_last(data, lo, hi):
    """Return (stored last word, sum of preceding words) for data indices."""
    if lo < 0 or hi > len(data) or hi <= lo or (hi - lo) % 4:
        raise ValueError("invalid word-sum range")
    words = struct.unpack(f"<{(hi - lo) // 4}I", data[lo:hi])
    return words[-1], sum(words[:-1]) & M


def image_index(flash_offset, image_base, size=1, image_len=None):
    index = flash_offset - image_base
    if index < 0 or (image_len is not None and index + size > image_len):
        raise ValueError(
            f"flash range 0x{flash_offset:x}..0x{flash_offset + size:x} "
            f"is absent from image base 0x{image_base:x}")
    return index


def parse_records(data, image_base):
    table = image_index(REC0, image_base, 0x10, len(data))
    records = []
    terminated = False
    for index in range(MAX_RECORDS):
        off = table + index * REC_STRIDE
        if off + REC_STRIDE > len(data):
            break
        addr, length, checksum, dst = struct.unpack_from("<4I", data, off)
        if addr == 0 or length == 0:
            terminated = True
            break
        records.append((index, addr, length, checksum, dst))
    if not records or not terminated:
        raise ValueError("SN_FWIN record table is missing or unterminated")
    return records


def analyze(data, image_base=0):
    checks = {}
    header = image_index(FWIN_OFF, image_base, 0x34, len(data))
    checks["SN_FWIN magic"] = data[header:header + 8] == b"SN_FWIN\x00"
    records = parse_records(data, image_base)

    for index, addr, length, stored, _dst in records:
        flash_off = addr - FLASH_BASE
        pos = image_index(flash_off, image_base, length, len(data))
        calc = chunked_crc_sum(data, pos, length)
        checks[f"record[{index}] checksum"] = calc == stored

    available_word_sums = {}
    for name, (lo, hi) in WORD_SUM_REGIONS.items():
        try:
            pos = image_index(lo, image_base, hi - lo, len(data))
        except ValueError:
            available_word_sums[name] = None
            continue
        stored, calc = word_sum_last(data, pos, pos + (hi - lo))
        available_word_sums[name] = (stored, calc)
        checks[f"{name} word-sum"] = stored == calc
    return records, available_word_sums, checks


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
    print("PROGRAM analyze_candidate_integrity")
    print("PURPOSE offline SN_FWIN integrity analysis")
    print(f"IMAGE {args.image}")
    print(f"IMAGE_BASE 0x{args.base:x}")
    print(f"IMAGE_SIZE 0x{len(data):x}")

    try:
        records, word_sums, checks = analyze(data, args.base)
    except (ValueError, struct.error) as exc:
        print(f"RESULT valid=False error={exc}")
        return 1

    print("\nRECORDS")
    for index, addr, length, stored, dst in records:
        pos = image_index(addr - FLASH_BASE, args.base, length, len(data))
        calc = chunked_crc_sum(data, pos, length)
        print(f"  [{index}] addr=0x{addr:08x} len=0x{length:x} dst=0x{dst:08x} "
              f"stored=0x{stored:08x} calc=0x{calc:08x} match={stored == calc}")

    print("\nWORD_SUMS")
    for name, result in word_sums.items():
        if result is None:
            print(f"  {name}: SKIP (region absent from this partial image)")
        else:
            stored, calc = result
            print(f"  {name}: stored=0x{stored:08x} calc=0x{calc:08x} "
                  f"match={stored == calc}")

    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    ok = all(checks.values())
    print(f"\nRESULT integrity_checks_ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
