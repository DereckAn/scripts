#!/usr/bin/env python3
"""Offline firmware image builder + round-trip integrity verifier.

Applies byte patches to a COPY of the preserved BIN, recomputes every integrity
field the bootloader checks, and re-verifies that the rebuilt image would pass:

  * SN_FWIN per-record checksum (bootloader FUN_00005028): sum of per-0x10000
    -chunk IEEE CRC-32, stored at record+0x8.
  * Additive 32-bit word-sum guards (bootloader FUN_000026d0): last word of a
    region equals the sum of every preceding word (bootloader + application).

This never touches the device or the preserved BIN. An output image is written
only to an explicit --out path. Default action is --demo, a zero-risk self-check.

Usage:
    python3 tool/build_modified_image.py                 # demo / self-check
    python3 tool/build_modified_image.py --patch 0x3f66f=41 --out /tmp/mod.bin
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_candidate_integrity import (  # noqa: E402  (reuse verified primitives)
    BIN as PRESERVED, FLASH_BASE, M, chunked_crc_sum, word_sum_last,
)
from analyze_boot_structures import boot_gate  # noqa: E402

REC0 = 0x10024            # first SN_FWIN record (addr, len, crc, dst) 4 words
REC_STRIDE = 0x10
CRC_FIELD = 0x8           # record+0x8 holds the stored checksum
WORD_SUM_REGIONS = [(0x00000, 0x10000), (0x10000, 0x7c000)]


def load(path):
    with open(path, "rb") as fh:
        return bytearray(fh.read())


def parse_records(img):
    """Yield (record_offset, flash_addr, length) for each non-empty record."""
    off = REC0
    out = []
    while off + 0x10 <= len(img):
        addr, length, _crc, _dst = struct.unpack_from("<4I", img, off)
        if length == 0 or addr == 0:
            break
        out.append((off, addr, length))
        off += REC_STRIDE
    return out


def recompute_integrity(img):
    """Fix all integrity fields in place. Records first (they sit inside the
    application word-sum region), then the word-sums."""
    for off, addr, length in parse_records(img):
        val = chunked_crc_sum(img, addr - FLASH_BASE, length)
        struct.pack_into("<I", img, off + CRC_FIELD, val)
    for lo, hi in WORD_SUM_REGIONS:
        words = struct.unpack(f"<{(hi - lo) // 4}I", bytes(img[lo:hi]))
        struct.pack_into("<I", img, hi - 4, sum(words[:-1]) & M)
    return img


def verify(img):
    """Return {check_name: bool} for every integrity field and boot invariant."""
    checks = {}
    for off, addr, length in parse_records(img):
        stored = struct.unpack_from("<I", img, off + CRC_FIELD)[0]
        checks[f"record@0x{off:05x}(flash 0x{addr:08x})"] = (
            chunked_crc_sum(img, addr - FLASH_BASE, length) == stored)
    for lo, hi in WORD_SUM_REGIONS:
        stored, calc = word_sum_last(img, lo, hi)
        checks[f"wordsum@0x{hi - 4:05x}"] = (stored == calc)
    checks.update(boot_gate(img))     # container/header invariants (step 2)
    return checks


def build(patches, out=None):
    """patches: list of (file_offset, bytes). Returns (image, checks)."""
    img = load(PRESERVED)
    for off, payload in patches:
        img[off:off + len(payload)] = payload
    recompute_integrity(img)
    checks = verify(img)
    if out:
        with open(out, "wb") as fh:
            fh.write(img)
    return img, checks


def _report(title, checks):
    print(title)
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return all(checks.values())


def demo():
    print("PROGRAM build_modified_image")
    print("PURPOSE offline image builder + round-trip integrity verifier")
    print(f"PRESERVED {PRESERVED}\n")

    original = load(PRESERVED)

    # Self-check 1: recomputing an unmodified copy must reproduce it byte-for-byte
    # (proves our recompute exactly matches the vendor's integrity method).
    rebuilt = recompute_integrity(load(PRESERVED))
    idempotent = bytes(rebuilt) == bytes(original)
    print(f"IDEMPOTENT recompute(preserved) == preserved : {idempotent}")

    # Self-check 2: patch one byte inside Candidate B (the product-string region),
    # show a naive patch FAILS verification and the rebuilt image PASSES.
    patch_off = 0x3f66f                      # 'R' of "ROG FALCHION ACE HFX"
    new = bytes([original[patch_off] ^ 0x20])  # flip case, one byte
    print(f"\nPATCH file 0x{patch_off:x}: 0x{original[patch_off]:02x} -> "
          f"0x{new[0]:02x} (inside Candidate B)")

    naive = load(PRESERVED)
    naive[patch_off:patch_off + 1] = new     # patched, integrity NOT recomputed
    naive_ok = _report("\nNAIVE (no recompute):", verify(naive))

    built, checks = build([(patch_off, new)])
    built_ok = _report("\nREBUILT (integrity recomputed):", checks)

    print(f"\nRESULT idempotent={idempotent} naive_passes={naive_ok} "
          f"rebuilt_passes={built_ok}")
    print("CONCLUSION A patched image can be rebuilt offline to pass every "
          "integrity field the bootloader checks; a naive patch fails, proving "
          "the checks are live and the recompute is what makes it valid.")

    # Hard self-checks.
    assert idempotent, "recompute does not reproduce the vendor image"
    assert not naive_ok, "naive patch unexpectedly passed integrity"
    assert built_ok, "rebuilt image failed integrity"


def main():
    args = sys.argv[1:]
    if not args or "--demo" in args:
        demo()
        return
    patches, out = [], None
    i = 0
    while i < len(args):
        if args[i] == "--patch":
            off_s, hex_s = args[i + 1].split("=")
            patches.append((int(off_s, 0), bytes.fromhex(hex_s)))
            i += 2
        elif args[i] == "--out":
            out = args[i + 1]
            i += 2
        else:
            raise SystemExit(f"unknown arg: {args[i]}")
    _img, checks = build(patches, out)
    ok = _report(f"REBUILT with {len(patches)} patch(es)"
                 + (f" -> {out}" if out else " (not written)"), checks)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
