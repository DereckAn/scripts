#!/usr/bin/env python3
"""Read exactly one 48-byte block at flash address 0x10000.

This is an intermediate validation probe, not a firmware backup. It sends one
and only one execute-READ. The surrounding data/status/data handshake proves the
returned buffer is complete despite the bootloader's deferred scheduling.
Default mode is a dry run.
"""

import argparse
import hashlib
import struct
import sys
import time

import backup_firmware as bf


ADDRESS = bf.REGION_LO
LENGTH = bf.CHUNK_MAX
EXPECTED_MAGIC = b"SN_FWIN\x00"

REPORTS = {
    "set_len": bf.build_report(bf.SET_LEN, struct.pack("<H", LENGTH)),
    "set_addr": bf.build_report(bf.SET_ADDR, struct.pack("<I", ADDRESS)),
    "exec_read": bf.build_report(bf.EXEC, bytes([bf.OP_READ])),
    "status": bf.build_report(bf.Q_STATUS),
    "data": bf.build_report(bf.Q_READDATA),
}

LIMITS = {
    "set_len": 2,                 # bootstrap, then the one READ
    "set_addr": 1,
    "exec_read": 1,
    "status": 1 + bf.FRESH_ATTEMPTS,
    "data": 2 + bf.FRESH_ATTEMPTS,
}


class ExactOneBlockError(Exception):
    pass


class ExactOneBlockTransport:
    """Allow only exact reports for one fixed address and one execute-READ."""

    def __init__(self, inner):
        self.inner = inner
        self.counts = {name: 0 for name in REPORTS}

    def write(self, report):
        raw = bytes(report)
        names = [name for name, expected in REPORTS.items() if raw == expected]
        if len(names) != 1:
            raise ExactOneBlockError("report is outside the one-block allowlist")
        name = names[0]
        if self.counts[name] >= LIMITS[name]:
            raise ExactOneBlockError(f"too many {name} reports")
        self.inner.write(REPORTS[name])
        self.counts[name] += 1

    def read(self, timeout):
        return self.inner.read(timeout)

    def close(self):
        self.inner.close()

    def require_complete(self):
        required = {"set_len": 2, "set_addr": 1, "exec_read": 1}
        for name, count in required.items():
            if self.counts[name] != count:
                raise ExactOneBlockError(
                    f"probe used {self.counts[name]} {name} reports; need {count}")
        if self.counts["status"] < 2 or self.counts["data"] < 3:
            raise ExactOneBlockError("freshness handshake did not complete")


def read_once_fresh(transport, baseline):
    """Queue exactly one READ and return a complete post-READ buffer."""
    bf.exec_read(transport, ADDRESS, LENGTH)
    for _ in range(bf.FRESH_ATTEMPTS):
        sample = bf.fetch(transport, LENGTH)
        flags = bf.check_status(transport)
        if sample != baseline and not flags & bf.BUSY_READ:
            confirmed = bf.fetch(transport, LENGTH)
            if confirmed == baseline:
                raise bf.ProtocolError(
                    "confirming fetch returned the pre-READ baseline")
            return confirmed
        time.sleep(bf.POLL_INTERVAL)
    raise bf.ProtocolError(
        "the one READ did not produce a provably fresh buffer within the bound")


def run_probe(transport):
    baseline = bf.bootstrap_baseline(transport, LENGTH)
    data = read_once_fresh(transport, baseline)
    transport.require_complete()
    if data[:len(EXPECTED_MAGIC)] != EXPECTED_MAGIC:
        raise bf.ProtocolError(
            "fresh block lacks expected SN_FWIN header: " + data.hex())
    return data


def dry_run():
    print("MODE=dry-run; no device enumerated or opened")
    print(f"TARGET address=0x{ADDRESS:x} length=0x{LENGTH:x}")
    for name in ("set_len", "status", "data", "set_len", "set_addr",
                 "exec_read", "data", "status", "data"):
        report = REPORTS[name]
        print(f"  {name:10s} {report[:8].hex(' ')} ...")
    print("EXECUTE_READ_COUNT=exactly_one")
    print("FORBIDDEN=other-address, unlock, erase, program, reset, update")
    return 0


def live_probe(open_transport=bf.SplitHidrawTransport,
               select_channels=bf.select_bootloader_channels):
    command_node, response_node, command_rejected, response_rejected, app_nodes = (
        select_channels())
    print(f"validated_command_node={command_node} usage_page=0x{bf.COMMAND_USAGE_PAGE:04x}")
    print(f"validated_response_node={response_node} usage_page=0x{bf.RESPONSE_USAGE_PAGE:04x}")
    print(f"command_selector_rejections={len(command_rejected)}")
    print(f"response_selector_rejections={len(response_rejected)}")
    print(f"application_nodes={app_nodes}")
    print(f"target=0x{ADDRESS:x}+0x{LENGTH:x}; execute_read_count=1")
    sys.stdout.flush()

    transport = ExactOneBlockTransport(open_transport(command_node, response_node))
    try:
        data = run_probe(transport)
    finally:
        transport.close()
    printable = "".join(chr(value) if 32 <= value < 127 else "." for value in data)
    print(f"data={data.hex(' ')}")
    print(f"ascii={printable}")
    print(f"sha256={hashlib.sha256(data).hexdigest()}")
    print("RESULT=PASS fresh_complete=true magic=SN_FWIN")
    print("FLASH_ACCESS=one execute-READ of 48 bytes at 0x10000")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="perform the exact one-block read")
    parser.add_argument("--acknowledge-one-read", action="store_true",
                        help="acknowledge one execute-READ at 0x10000")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.run:
        return dry_run()
    if not args.acknowledge_one_read:
        print("REFUSED: --run also requires --acknowledge-one-read",
              file=sys.stderr)
        return 2
    try:
        return live_probe()
    except (bf.SelectionError, bf.ProtocolError, ExactOneBlockError, OSError) as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
