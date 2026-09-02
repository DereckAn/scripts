#!/usr/bin/env python3
"""Enter the Falchion Ace HFX bootloader with ASUS's exact reset-only report.

Default mode is a dry run and never opens /dev/hidraw*. Live mode requires both
--run and --acknowledge-reset. The live path validates one application-mode
0b05:1b7e vendor interface (FF00, 64-byte IN/OUT, no Report ID), emits exactly
one allowlisted report, closes the node, and only then polls sysfs for 1b7f.

This report resets the MCU after writing the force-boot flag in RAM. It does not
unlock, erase, program, update, or send a bootloader flash command.
"""

import argparse
import hashlib
import os
import sys
import time


VID = 0x0B05
PID_APP = 0x1B7E
PID_BOOT = 0x1B7F
USAGE_PAGE = 0xFF00
REPORT_LEN = 64
SYSFS_HIDRAW = "/sys/class/hidraw"

# peripheral_fwu_pro.exe FUN_004054e0 case 4 in "m" mode, independently
# matched by Candidate B FUN_180160d8. Remaining payload bytes are zero because
# the updater zero-initialises the configured 64-byte application report first.
PAYLOAD = bytes.fromhex("7b aa 41 53 55 53 aa") + bytes(REPORT_LEN - 7)
HIDRAW_WRITE = b"\x00" + PAYLOAD  # report-number placeholder + payload


class SelectionError(Exception):
    pass


class UnsafeWrite(Exception):
    pass


def hid_id(uevent):
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            fields = line.split(":")
            if len(fields) != 3:
                return None
            try:
                return int(fields[1], 16) & 0xFFFF, int(fields[2], 16) & 0xFFFF
            except ValueError:
                return None
    return None


def descriptor_facts(desc):
    """Return (usage_pages, input sizes, output sizes, has_report_id)."""
    pos, page, size, count = 0, None, 0, 0
    pages, inputs, outputs, has_report_id = set(), [], [], False
    while pos < len(desc):
        prefix = desc[pos]
        pos += 1
        if prefix == 0xFE:
            if pos + 2 > len(desc):
                raise ValueError("truncated HID long item")
            body_len = desc[pos]
            pos += 2 + body_len
            if pos > len(desc):
                raise ValueError("truncated HID long item body")
            continue
        width = prefix & 3
        if width == 3:
            width = 4
        if pos + width > len(desc):
            raise ValueError("truncated HID short item")
        value = int.from_bytes(desc[pos:pos + width], "little") if width else 0
        pos += width
        tag = prefix & 0xFC
        if tag == 0x04:       # Usage Page
            page = value
            pages.add(value)
        elif tag == 0x74:     # Report Size
            size = value
        elif tag == 0x94:     # Report Count
            count = value
        elif tag == 0x84:     # Report ID
            has_report_id = True
        elif tag == 0x80:     # Input
            inputs.append((page, size * count // 8))
        elif tag == 0x90:     # Output
            outputs.append((page, size * count // 8))
    return pages, inputs, outputs, has_report_id


def descriptor_reasons(desc):
    pages, inputs, outputs, has_report_id = descriptor_facts(desc)
    reasons = []
    if USAGE_PAGE not in pages:
        reasons.append("usage page FF00 absent")
    if (USAGE_PAGE, REPORT_LEN) not in inputs:
        reasons.append("no FF00 64-byte Input report")
    if (USAGE_PAGE, REPORT_LEN) not in outputs:
        reasons.append("no FF00 64-byte Output report")
    if has_report_id:
        reasons.append("descriptor declares a Report ID")
    return reasons


def enumerate_nodes(sysfs_root=SYSFS_HIDRAW, dev_root="/dev"):
    app_candidates, boot_nodes, rejected = [], [], []
    try:
        names = sorted(os.listdir(sysfs_root))
    except OSError as exc:
        raise SelectionError(f"cannot enumerate {sysfs_root}: {exc}") from exc
    for name in names:
        base = os.path.join(sysfs_root, name, "device")
        try:
            with open(os.path.join(base, "uevent"), encoding="utf-8") as fh:
                ids = hid_id(fh.read())
        except OSError:
            continue
        if ids == (VID, PID_BOOT):
            boot_nodes.append(os.path.join(dev_root, name))
            continue
        if ids != (VID, PID_APP):
            continue
        try:
            with open(os.path.join(base, "report_descriptor"), "rb") as fh:
                desc = fh.read()
            reasons = descriptor_reasons(desc)
        except (OSError, ValueError) as exc:
            reasons = [str(exc)]
        node = os.path.join(dev_root, name)
        if reasons:
            rejected.append((node, reasons))
        else:
            app_candidates.append(node)
    return app_candidates, boot_nodes, rejected


def select_application_node(sysfs_root=SYSFS_HIDRAW, dev_root="/dev"):
    app, boot, rejected = enumerate_nodes(sysfs_root, dev_root)
    if boot:
        raise SelectionError(
            "keyboard already exposes bootloader PID 1b7f; refusing an app-mode write")
    if len(app) != 1:
        detail = "; ".join(
            f"{node}: {', '.join(reasons)}" for node, reasons in rejected)
        raise SelectionError(
            f"expected exactly one validated 0b05:1b7e FF00 node, found {len(app)}"
            + (f" ({detail})" if detail else ""))
    return app[0]


def guard_exact_write(raw):
    raw = bytes(raw)
    if raw != HIDRAW_WRITE:
        raise UnsafeWrite("outgoing bytes differ from the single reset-only allowlist entry")
    if len(raw) != REPORT_LEN + 1 or raw[0] != 0:
        raise UnsafeWrite("invalid hidraw report-number framing")


def emit_once(node, opener=os.open, writer=os.write, closer=os.close):
    guard_exact_write(HIDRAW_WRITE)
    fd = opener(node, os.O_WRONLY | os.O_NONBLOCK)
    try:
        # Re-check immediately before the only device mutation in this tool.
        guard_exact_write(HIDRAW_WRITE)
        written = writer(fd, HIDRAW_WRITE)
        if written != len(HIDRAW_WRITE):
            raise OSError(f"short hidraw write: {written}/{len(HIDRAW_WRITE)} bytes")
    finally:
        closer(fd)


def wait_for_bootloader(timeout, sysfs_root=SYSFS_HIDRAW, dev_root="/dev"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, boot, _ = enumerate_nodes(sysfs_root, dev_root)
        if boot:
            return boot
        time.sleep(0.1)
    return []


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true",
                   help="open the validated application hidraw node and send once")
    p.add_argument("--acknowledge-reset", action="store_true",
                   help="confirm the keyboard will reset and re-enumerate")
    p.add_argument("--timeout", type=float, default=10.0,
                   help="seconds to poll sysfs for PID 1b7f after the one write")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    guard_exact_write(HIDRAW_WRITE)
    print("payload_len=64")
    print(f"payload={PAYLOAD.hex(' ')}")
    print(f"hidraw_write_len={len(HIDRAW_WRITE)}")
    print(f"hidraw_write_sha256={hashlib.sha256(HIDRAW_WRITE).hexdigest()}")
    if not args.run:
        print("DRY RUN: no device enumerated or opened; no report sent")
        return 0
    if not args.acknowledge_reset:
        print("REFUSED: --run also requires --acknowledge-reset", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("REFUSED: --timeout must be positive", file=sys.stderr)
        return 2

    node = select_application_node()
    print(f"validated_node={node}")
    print("action=one reset-only hidraw write; no retry")
    sys.stdout.flush()
    emit_once(node)
    print("report_sent=yes")
    boot_nodes = wait_for_bootloader(args.timeout)
    if not boot_nodes:
        print("RESULT: report was sent, but PID 1b7f was not observed before timeout")
        return 3
    print("RESULT: bootloader PID 0b05:1b7f observed")
    for node in boot_nodes:
        print(f"boot_node={node}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
