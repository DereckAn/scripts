#!/usr/bin/env python3
"""Offline, read-only analysis of the Falchion SN_FWIN integrity records.

Reproduces every integrity field in the container from the algorithms recovered
by reading the bootloader verifier (logs 75/76):

  * Per-record SN_FWIN checksum (bootloader FUN_00005028): the region is copied
    to RAM in 0x10000-byte chunks and an IEEE CRC-32 is taken of each chunk
    independently; the per-chunk CRC-32 results are SUMMED mod 2**32. Candidate A
    (0x58ac bytes) fits one chunk, so its value is a plain CRC-32; Candidate B
    (0x1e754 bytes) spans two chunks, so its value is CRC32(chunk0)+CRC32(chunk1).
  * Whole-region additive word-sum (bootloader FUN_000026d0): the last 32-bit
    word of a region equals the 32-bit sum of every preceding word. This covers
    the bootloader region and the whole application region (the "terminal
    values" 0xfb665ae3 and 0x5d27c5a9).

Every value below is asserted against the stored field, so this script fails
loudly if the firmware or the recovered algorithm assumptions change.

No device access. Reads only the preserved firmware BIN and the extracted
bootloader slice. Usage:
    python3 tool/analyze_candidate_integrity.py [path-to-bin]
"""
import binascii
import struct
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "dumps/vendor/M605_V01_00_58.bin")

M = 0xFFFFFFFF
crc32 = lambda b, init=0: binascii.crc32(b, init) & M
CHUNK = 0x10000                  # bootloader FUN_00005028 RAM chunk size


def chunked_crc_sum(data, off, length, chunk=CHUNK):
    """Sum of per-chunk IEEE CRC-32 (bootloader FUN_00005028)."""
    acc, pos, rem = 0, off, length
    while rem:
        n = min(rem, chunk)
        acc = (acc + crc32(data[pos:pos + n])) & M
        pos += n & 0xFFFFFFFC     # src advanced by word-aligned chunk length
        rem -= n
    return acc


def word_sum_last(data, lo, hi):
    """Return (stored_last_word, sum_of_preceding_words) for FUN_000026d0."""
    words = struct.unpack(f"<{(hi - lo) // 4}I", data[lo:hi])
    return words[-1], sum(words[:-1]) & M

# Verified record values (see FINDINGS.md "Integrity and authentication").
A_ADDR, A_LEN, A_CRC = 0x60011000, 0x000058AC, 0x5E75C17A
B_ADDR, B_LEN, B_CRC = 0x60021000, 0x0001E754, 0x1A76C116
FLASH_BASE = 0x60000000          # flash addr -> file offset (verified via A)


def load(path):
    with open(path, "rb") as fh:
        return fh.read()


def main():
    data = load(BIN)
    print("PROGRAM analyze_candidate_integrity")
    print("PURPOSE offline read-only SN_FWIN integrity-record analysis")
    print(f"BIN {BIN}")
    print(f"BIN_SIZE 0x{len(data):x}")

    # --- SN_FWIN header + record table ---
    magic = data[0x10000:0x10010]
    print(f"\nHEADER magic={magic!r}")
    print("RECORD_TABLE (4 words each: flash_addr length crc32 ram_dest)")
    for off in (0x10024, 0x10034, 0x10044):
        addr, length, crc, dst = struct.unpack_from("<4I", data, off)
        print(f"  @0x{off:05x}: addr=0x{addr:08x} len=0x{length:08x} "
              f"crc=0x{crc:08x} dst=0x{dst:08x}")

    # --- per-record chunked-CRC-sum (bootloader FUN_00005028) ---
    a_off, b_off = A_ADDR - FLASH_BASE, B_ADDR - FLASH_BASE
    a_calc = chunked_crc_sum(data, a_off, A_LEN)
    b_calc = chunked_crc_sum(data, b_off, B_LEN)
    print(f"\nCHUNK_SIZE 0x{CHUNK:x}")
    print(f"A_RANGE file 0x{a_off:x}..0x{a_off + A_LEN:x} (1 chunk => plain CRC-32)")
    print(f"A_CHECKSUM calc=0x{a_calc:08x} stored=0x{A_CRC:08x} "
          f"match={a_calc == A_CRC}")
    b_c0 = crc32(data[b_off:b_off + CHUNK])
    b_c1 = crc32(data[b_off + CHUNK:b_off + B_LEN])
    print(f"B_RANGE file 0x{b_off:x}..0x{b_off + B_LEN:x} (2 chunks => CRC sum)")
    print(f"  B chunk0 crc=0x{b_c0:08x} (file 0x{b_off:x}..0x{b_off + CHUNK:x})")
    print(f"  B chunk1 crc=0x{b_c1:08x} (file 0x{b_off + CHUNK:x}.."
          f"0x{b_off + B_LEN:x}, len 0x{B_LEN - CHUNK:x})")
    print(f"B_CHECKSUM calc=0x{b_calc:08x} stored=0x{B_CRC:08x} "
          f"match={b_calc == B_CRC}")

    # --- whole-region additive word-sum (bootloader FUN_000026d0) ---
    print("\nWORD_SUM regions (last word == sum of preceding words):")
    regions = {
        "bootloader 0x00000..0x10000": (0x00000, 0x10000),
        "application 0x10000..0x7c000": (0x10000, 0x7c000),
    }
    ws_ok = True
    for name, (lo, hi) in regions.items():
        stored, calc = word_sum_last(data, lo, hi)
        ws_ok &= stored == calc
        print(f"  {name:30s} stored=0x{stored:08x} calc=0x{calc:08x} "
              f"match={stored == calc}")

    print(f"\nRESULT A_ok={a_calc == A_CRC} B_ok={b_calc == B_CRC} "
          f"word_sums_ok={ws_ok}")
    print("CONCLUSION All container integrity fields reproduced offline: SN_FWIN "
          "per-record values are a sum of per-0x10000-chunk IEEE CRC-32 "
          "(FUN_00005028); the terminal values are additive 32-bit word-sums "
          "(FUN_000026d0).")

    # Hard self-checks: every recovered algorithm must reproduce its stored field.
    assert a_calc == A_CRC, "Candidate A checksum no longer reproduces"
    assert b_calc == B_CRC, "Candidate B checksum no longer reproduces"
    assert ws_ok, "Word-sum terminal values no longer reproduce"


if __name__ == "__main__":
    main()
