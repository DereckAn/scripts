#!/usr/bin/env python3
"""Strictly READ-ONLY firmware backup tool for the ROG Falchion Ace HFX bootloader.

Reads the application flash region [0x10000, 0x7c000) from the device while it is
in bootloader mode (PID 1b7f) over the vendor-HID protocol decoded in FINDINGS
"Bootloader vendor-HID wire framing" (logs 81-82), and reassembles a backup image.

SAFETY (the whole point of this tool):
  * It can ONLY construct read/query/set-address/set-length reports. There is no
    code path that can emit erase (execute opcode 0x01), program (0x51), the
    `ASUSHIDFWU` unlock (0x10), load-data (0x22), or reset (0x11).
  * Every outgoing report passes `guard()` before any byte reaches the device;
    the execute report is hard-locked to the READ opcode (0x05).
  * Default action is --dry-run: it builds and validates the entire dump plan
    WITHOUT opening any device. Only --run opens a device, and only if that device
    is already in bootloader mode (PID 1b7f); it refuses to talk to the app (1b7e).

Usage:
    python3 tool/backup_firmware.py            # dry-run: validate plan + safety (no device)
    python3 tool/backup_firmware.py --run OUT  # perform the read-back (needs 1b7f device)
"""
import glob
import hashlib
import os
import struct
import sys

VID = 0x0B05
PID_BOOT = 0x1B7F          # bootloader mode
PID_APP = 0x1B7E          # application mode (this tool refuses to send to it)
REPORT_LEN = 64

REGION_LO, REGION_HI = 0x10000, 0x7C000   # readable application region
CHUNK_MAX = 0x30                          # bootloader read length cap

# sub-commands (report[0]); see FalchionBootloaderFraming
SET_ADDR, SET_LEN, EXEC = 0x20, 0x21, 0x1F
Q_STATUS, Q_READDATA, Q_CRC = 0x8F, 0xAA, 0x8E
OP_READ = 0x05

ALLOWED_OUT = {SET_ADDR, SET_LEN, EXEC}
ALLOWED_QUERY = {Q_STATUS, Q_READDATA, Q_CRC}
# Never emittable. Listed only to make the intent explicit and testable.
FORBIDDEN = {0x10, 0x22, 0x11, 0x01, 0x51}


class UnsafeReport(Exception):
    pass


def guard(sub, payload):
    """Raise unless (sub, payload) is a pure read/query. This is the only gate
    through which reports are built; erase/program/unlock cannot pass it."""
    if sub not in ALLOWED_OUT and sub not in ALLOWED_QUERY:
        raise UnsafeReport(f"sub-command 0x{sub:02x} is not read-only")
    if sub == EXEC:
        if not payload or payload[0] != OP_READ:
            raise UnsafeReport(
                f"execute opcode must be READ(0x05), got {payload[:1]!r}")
        if len(payload) > 1 and any(b in FORBIDDEN for b in payload[1:]):
            raise UnsafeReport("forbidden byte in execute payload")


def build_report(sub, payload=b""):
    guard(sub, payload)
    body = bytes([sub]) + bytes(payload)
    if len(body) > REPORT_LEN:
        raise UnsafeReport("report too long")
    return body + b"\x00" * (REPORT_LEN - len(body))


def read_chunk_reports(addr, length):
    """The exact report sequence to read one chunk. Read-only by construction."""
    if not (REGION_LO <= addr and addr + length <= REGION_HI):
        raise UnsafeReport(f"address 0x{addr:x}+0x{length:x} outside readable region")
    if not (0 < length <= CHUNK_MAX):
        raise UnsafeReport(f"length 0x{length:x} out of range")
    return [
        ("set_addr", build_report(SET_ADDR, struct.pack("<I", addr))),
        ("set_len", build_report(SET_LEN, struct.pack("<H", length))),
        ("exec_read", build_report(EXEC, bytes([OP_READ]))),
        ("query_status", build_report(Q_STATUS)),
        ("query_data", build_report(Q_READDATA)),
    ]


def dump_plan(lo=REGION_LO, hi=REGION_HI, chunk=CHUNK_MAX):
    for addr in range(lo, hi, chunk):
        yield addr, min(chunk, hi - addr)


# ---------------------------------------------------------------------------
# device I/O (only reached via --run). Raw hidraw; no external dependencies.
# NOTE: the exact transfer type (output vs feature report) and the report-ID
# prefix are conservative defaults and must be confirmed on first real use.
# ---------------------------------------------------------------------------
def find_bootloader_hidraw():
    """Return a /dev/hidrawN path for a PID-1b7f interface, or None.
    Refuses (returns ('app', path)) if only the 1b7e application is present."""
    app_seen = None
    for node in sorted(glob.glob("/dev/hidraw*")):
        name = os.path.basename(node)
        uevent = f"/sys/class/hidraw/{name}/device/uevent"
        try:
            info = open(uevent).read()
        except OSError:
            continue
        # HID_ID=0003:00000B05:00001B7F
        for line in info.splitlines():
            if line.startswith("HID_ID="):
                parts = line.split(":")
                vid = int(parts[1], 16) & 0xFFFF
                pid = int(parts[2], 16) & 0xFFFF
                if vid == VID and pid == PID_BOOT:
                    return ("boot", node)
                if vid == VID and pid == PID_APP:
                    app_seen = node
    return ("app", app_seen) if app_seen else (None, None)


def run_backup(out_path, passes=3):
    kind, node = find_bootloader_hidraw()
    if kind != "boot":
        print("REFUSING: no PID-1b7f (bootloader) HID device found.")
        if kind == "app":
            print("  The keyboard is in application mode (1b7e). This tool will "
                  "NOT send bootloader commands to the application. Put the device "
                  "in bootloader mode first, then re-run.")
        return 2
    print(f"Bootloader HID device: {node}")
    digests = []
    for p in range(passes):
        image = bytearray()
        fd = os.open(node, os.O_RDWR)
        try:
            for addr, length in dump_plan():
                for _label, report in read_chunk_reports(addr, length):
                    guard(report[0], report[1:])        # re-guard before every write
                    os.write(fd, b"\x00" + report)      # report id 0 + 64 bytes
                # read the data-response report back
                resp = os.read(fd, REPORT_LEN + 1)
                image += bytes(resp[1:1 + length])      # strip report id, take len
        finally:
            os.close(fd)
        d = hashlib.sha256(image).hexdigest()
        digests.append(d)
        print(f"pass {p + 1}/{passes}: 0x{len(image):x} bytes sha256={d}")
    if len(set(digests)) != 1:
        print("MISMATCH between passes — do NOT trust this dump.")
        return 1
    with open(out_path, "wb") as fh:
        fh.write(image)
    print(f"OK: {passes} identical passes; wrote {out_path}")
    print("Validate next with:  python3 tool/analyze_boot_structures.py " + out_path)
    return 0


def dry_run():
    print("PROGRAM backup_firmware  (DRY-RUN — no device opened)")
    plan = list(dump_plan())
    total = sum(n for _a, n in plan)
    print(f"region 0x{REGION_LO:x}..0x{REGION_HI:x}  chunks={len(plan)} "
          f"chunk_max=0x{CHUNK_MAX:x}  bytes=0x{total:x}")
    # validate that EVERY report the plan can emit is read-only
    count = 0
    for addr, length in plan:
        for _label, report in read_chunk_reports(addr, length):
            guard(report[0], report[1:])   # re-validate exactly what would be sent
            assert report[0] in ALLOWED_OUT | ALLOWED_QUERY
            count += 1
    print(f"validated {count} reports; all pass the read-only guard")
    # show one chunk verbatim
    print("sample chunk @0x10000 len 0x30:")
    for label, report in read_chunk_reports(0x10000, 0x30):
        print(f"  {label:12s} {report[:8].hex(' ')} ...")
    _safety_selfcheck()
    print("RESULT dry_run_ok=True  (erase/program/unlock are unconstructable)")


def _safety_selfcheck():
    """Prove the rails: forbidden operations must be impossible to build."""
    must_fail = [
        (EXEC, bytes([0x01])),   # erase
        (EXEC, bytes([0x51])),   # program
        (0x10, b"ASUSHIDFWU"),   # unlock
        (0x22, b"\x04\x00\x00data"),  # load data
        (0x11, b""),             # reset
    ]
    for sub, payload in must_fail:
        try:
            build_report(sub, payload)
        except UnsafeReport:
            continue
        raise AssertionError(f"SAFETY FAILURE: built forbidden report 0x{sub:02x}")
    # allowed ones must succeed
    for sub, payload in [(SET_ADDR, struct.pack("<I", 0x10000)),
                         (SET_LEN, struct.pack("<H", 0x30)),
                         (EXEC, bytes([OP_READ])), (Q_STATUS, b"")]:
        build_report(sub, payload)
    print("safety self-check: PASS (forbidden reports rejected, read reports built)")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--run":
        if len(args) < 2:
            raise SystemExit("usage: backup_firmware.py --run <output.bin>")
        raise SystemExit(run_backup(args[1]))
    dry_run()


if __name__ == "__main__":
    main()
