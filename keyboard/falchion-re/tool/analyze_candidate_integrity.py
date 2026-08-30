#!/usr/bin/env python3
"""Offline, read-only analysis of the Falchion SN_FWIN integrity records.

Decodes the SN_FWIN header record table, reproduces Candidate A's known-good
IEEE CRC-32 (hard self-check), and demonstrates that Candidate B's stored value
0x1a76c116 matches no CRC-32 interpretation of the container's B bytes.

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
BOOT = os.path.join(ROOT, "ghidra/imports/bootloader_primary.bin")

M = 0xFFFFFFFF
crc32 = lambda b, init=0: binascii.crc32(b, init) & M

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

    # --- reproduce A (self-check locks the algorithm + file mapping) ---
    a_off = A_ADDR - FLASH_BASE
    a_bytes = data[a_off:a_off + A_LEN]
    a_calc = crc32(a_bytes)
    print(f"\nA_RANGE file 0x{a_off:x}..0x{a_off + A_LEN:x}")
    print(f"A_CRC32 calc=0x{a_calc:08x} stored=0x{A_CRC:08x} "
          f"match={a_calc == A_CRC}")

    # --- B: show mismatch and rule out common interpretations ---
    b_off = B_ADDR - FLASH_BASE
    b_bytes = data[b_off:b_off + B_LEN]
    print(f"\nB_RANGE file 0x{b_off:x}..0x{b_off + B_LEN:x}  "
          f"(0x1e754 = copy 0x1e354 + compressed-source 0x400)")
    hyps = {
        "ieee_crc32(B)": crc32(b_bytes),
        "crc32(B, init=A_crc)": crc32(b_bytes, A_CRC),
        "crc32(A+B)": crc32(a_bytes + b_bytes),
        "crc32(recB + B)": crc32(data[0x10034:0x10044] + b_bytes),
        "crc32(B, init=len)": crc32(b_bytes, B_LEN),
        "crc32(copy-region 0x1e354)": crc32(data[b_off:b_off + 0x1e354]),
    }
    print(f"B_STORED 0x{B_CRC:08x}")
    any_match = False
    for name, val in hyps.items():
        hit = val == B_CRC
        any_match |= hit
        print(f"  B {name:32s} 0x{val:08x}{'  <<< MATCH' if hit else ''}")

    # bounded sweeps: fixed start vary end, fixed len vary start (step 4)
    sweep_hits = []
    S = b_off
    for end in range(S + 0x100, len(data) + 1, 4):
        if crc32(data[S:end]) == B_CRC:
            sweep_hits.append(("end", S, end))
    L = B_LEN
    for s in range(0, len(data) - L + 1, 4):
        if crc32(data[s:s + L]) == B_CRC:
            sweep_hits.append(("start", s, s + L))
    print(f"B_RANGE_SWEEP ieee-crc32 hits over whole file: {len(sweep_hits)} "
          f"{sweep_hits}")

    # --- bootloader CRC algorithm evidence ---
    boot = load(BOOT)
    poly_refl = boot.find(struct.pack("<I", 0xEDB88320))
    print(f"\nBOOTLOADER reflected-CRC32 constant 0xedb88320 at "
          f"{'0x%x' % poly_refl if poly_refl >= 0 else 'not found'}")

    print(f"\nRESULT A_reproduces={a_calc == A_CRC} B_matches_any_file_crc="
          f"{any_match or bool(sweep_hits)}")
    print("CONCLUSION Candidate B's stored 0x1a76c116 is not an IEEE CRC-32 "
          "(or tested variant/seed/range) of the container's B bytes; the "
          "verified byte-source for B differs and must be read from the "
          "bootloader verify routine.")

    # Hard self-check: if A stops reproducing, the mapping/algorithm assumption
    # underpinning every claim here is wrong.
    assert a_calc == A_CRC, "Candidate A CRC-32 no longer reproduces"


if __name__ == "__main__":
    main()
