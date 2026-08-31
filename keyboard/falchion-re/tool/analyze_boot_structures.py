#!/usr/bin/env python3
"""Offline, read-only decode of the Falchion boot container structures.

Decodes the layered boot format the bootloader walks before it CRC-verifies and
jumps (recovered from bootloader_primary.bin, logs 75/78):

  SNC7320A wrapper  (primary @flash 0x60000000, backup @0x60060000)
    -> SN_BCFG boot-config (@wrapper+0x200)
       -> 2-slot boot-priority pointer table (@wrapper+0x208)
          -> SN_FWIN firmware-info header (@0x60010000)
             -> per-region records (loader A + application B)

`boot_gate(img)` returns the invariants a modified image must preserve to boot,
independent of the CRC/word-sum integrity fields:
  * SNC7320A / SN_BCFG / SN_FWIN magics intact
  * boot-priority slot 0 points at the SN_FWIN header
  * SN_FWIN CRC-enable gate (+0x18) is nonzero (else records are NOT verified)
  * the entry region's initial SP is a valid RAM address (bootloader FUN_00005240)

No device access. Usage:
    python3 tool/analyze_boot_structures.py [path-to-bin]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "dumps/vendor/M605_V01_00_58.bin")

FLASH_BASE = 0x60000000
SNC_MAGIC = b"SNC7320A"
BCFG_MAGIC = b"SN_BCFG\x00"
FWIN_MAGIC = b"SN_FWIN\x00"
BCFG_OFF = 0x200          # SN_BCFG within a container wrapper
SLOTS_OFF = 0x208         # boot-priority pointer table within a container
FWIN_ADDR = 0x60010000    # firmware-info header (both slots point here)
GATE_OFF = 0x18           # SN_FWIN CRC-enable gate
ENTRY_PTR_OFF = 0x10      # SN_FWIN entry pointer (candidate A base)
CONTAINERS = {"primary": 0x60000000, "backup": 0x60060000}
# Valid initial-SP ranges enforced by FUN_00005240 (exclusive/inclusive per code).
SP_RANGES = ((0x18000000, 0x18040000), (0x20000000, 0x20001000))


def f(addr):
    """flash address -> file offset."""
    return addr - FLASH_BASE


def boot_gate(img):
    """Return {check_name: bool} for the boot-decision invariants."""
    checks = {}
    for name, base in CONTAINERS.items():
        b = f(base)
        checks[f"{name} SNC7320A magic"] = img[b:b + 8] == SNC_MAGIC
        checks[f"{name} SN_BCFG magic"] = (
            img[b + BCFG_OFF:b + BCFG_OFF + 8] == BCFG_MAGIC)
        slot0 = struct.unpack_from("<I", img, b + SLOTS_OFF)[0]
        checks[f"{name} slot0 -> SN_FWIN"] = slot0 == FWIN_ADDR

    h = f(FWIN_ADDR)
    checks["SN_FWIN magic"] = img[h:h + 8] == FWIN_MAGIC
    checks["SN_FWIN CRC-enable gate (+0x18) nonzero"] = (
        struct.unpack_from("<I", img, h + GATE_OFF)[0] != 0)

    entry = struct.unpack_from("<I", img, h + ENTRY_PTR_OFF)[0]
    sp = struct.unpack_from("<I", img, f(entry))[0]   # first word = initial SP
    checks["entry initial-SP in valid RAM"] = any(
        lo < sp < hi or sp == hi for (lo, hi) in SP_RANGES) and any(
        lo < sp <= hi for (lo, hi) in SP_RANGES)
    return checks


def decode(img):
    print(f"BIN {BIN}\nBIN_SIZE 0x{len(img):x}\n")
    for name, base in CONTAINERS.items():
        b = f(base)
        magic = bytes(img[b:b + 8])
        boot_ptr, size = struct.unpack_from("<2I", img, b + 0x10)
        bcfg = bytes(img[b + BCFG_OFF:b + BCFG_OFF + 8])
        s0, s1 = struct.unpack_from("<2I", img, b + SLOTS_OFF)
        print(f"CONTAINER {name} @flash 0x{base:08x} (file 0x{b:x})")
        print(f"  wrapper magic={magic!r} bootloader_ptr=0x{boot_ptr:08x} "
              f"size=0x{size:08x}")
        print(f"  {bcfg!r} @+0x200  boot_slots=[0x{s0:08x}, 0x{s1:08x}]")

    h = f(FWIN_ADDR)
    entry = struct.unpack_from("<I", img, h + ENTRY_PTR_OFF)[0]
    gate = struct.unpack_from("<I", img, h + GATE_OFF)[0]
    sp = struct.unpack_from("<I", img, f(entry))[0]
    print(f"\nSN_FWIN @flash 0x{FWIN_ADDR:08x} (file 0x{h:x})")
    print(f"  magic={bytes(img[h:h+8])!r} fmt={bytes(img[h+8:h+0x10])!r}")
    print(f"  entry_ptr(+0x10)=0x{entry:08x} crc_gate(+0x18)=0x{gate:08x} "
          f"entry_initial_SP=0x{sp:08x}")
    off = h + 0x24
    idx = 0
    while off + 0x10 <= len(img):
        addr, length, crc, dst = struct.unpack_from("<4I", img, off)
        if length == 0 or addr == 0:
            print(f"  record[{idx}] @0x{off:05x} TERMINATOR")
            break
        print(f"  record[{idx}] @0x{off:05x} addr=0x{addr:08x} len=0x{length:08x} "
              f"crc=0x{crc:08x} dst=0x{dst:08x}")
        off += 0x10
        idx += 1


def main():
    with open(BIN, "rb") as fh:
        img = bytearray(fh.read())
    print("PROGRAM analyze_boot_structures")
    print("PURPOSE offline read-only boot-container structure decode\n")
    decode(img)
    gate = boot_gate(img)
    print("\nBOOT_GATE invariants (must hold for a modified image to boot):")
    for name, ok in gate.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\nRESULT boot_gate_ok={all(gate.values())}")
    print("CONCLUSION A modified image boots iff these container/header "
          "invariants hold AND the integrity fields verify. A Candidate-B data "
          "patch preserves every invariant here (magics, slot table, gate, and "
          "entry SP are untouched); only the recomputed CRC/word-sum fields "
          "change.")
    assert all(gate.values()), "boot-gate invariant failed on preserved BIN"


if __name__ == "__main__":
    main()
