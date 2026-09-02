#!/usr/bin/env python3
"""Minimal read/query-only live probe for the Falchion Ace HFX bootloader.

The exact device-facing sequence is fixed:

  1. 0x8f status query
  2. 0x21 0x30 0x00 set volatile response length to 48
  3. 0xaa reset-initialised response-buffer query
  4. 0x8f final status query

Reports are written on the FF01/EP6 command node and replies are read on the
FF00/EP5 response node, as recovered from the bootloader endpoint tables. No
address or flash operation is selected or executed. Default mode is a dry run.
Live mode requires --run --acknowledge-volatile-length and normally needs
privilege because the bootloader's hidraw nodes are root-only.
"""

import argparse
import hashlib
import struct
import sys

import backup_firmware as bf


PROBE_LEN = 0x30
SEQUENCE = (
    ("status_before", bf.build_report(bf.Q_STATUS)),
    ("set_volatile_length", bf.build_report(bf.SET_LEN, struct.pack("<H", PROBE_LEN))),
    ("query_zero_buffer", bf.build_report(bf.Q_READDATA)),
    ("status_after", bf.build_report(bf.Q_STATUS)),
)


class ExactSequenceError(Exception):
    pass


class ExactSequenceTransport:
    """Permit only SEQUENCE, byte-for-byte, then delegate reads."""

    def __init__(self, inner):
        self.inner = inner
        self.index = 0

    def write(self, report):
        if self.index >= len(SEQUENCE):
            raise ExactSequenceError("refusing an extra report after the probe sequence")
        label, expected = SEQUENCE[self.index]
        if bytes(report) != expected:
            raise ExactSequenceError(
                f"report {self.index + 1} differs from required {label} bytes")
        self.inner.write(expected)
        self.index += 1

    def read(self, timeout):
        return self.inner.read(timeout)

    def close(self):
        self.inner.close()

    def require_complete(self):
        if self.index != len(SEQUENCE):
            raise ExactSequenceError(
                f"probe stopped after {self.index}/{len(SEQUENCE)} reports")


SplitHidrawTransport = bf.SplitHidrawTransport
select_bootloader_channels = bf.select_bootloader_channels


def validate_status(resp, label):
    resp = bytes(resp)
    if len(resp) != bf.REPORT_LEN:
        raise bf.ProtocolError(f"{label}: response length {len(resp)}, need 64")
    if resp[0] != bf.R_STATUS:
        raise bf.ProtocolError(
            f"{label}: response code 0x{resp[0]:02x}, need 0x{bf.R_STATUS:02x}")
    flags, error = resp[bf.STATUS_FLAGS], resp[bf.STATUS_ERROR]
    if flags != 0:
        raise bf.ProtocolError(
            f"{label}: flags 0x{flags:02x}, need locked+idle value 0x00")
    if error != 0:
        raise bf.ProtocolError(f"{label}: error 0x{error:02x}, need 0x00")
    return flags, error


def run_probe(transport):
    status_before = bf.query(transport, bf.Q_STATUS, bf.R_STATUS)
    validate_status(status_before, "status_before")

    bf.send(transport, bf.SET_LEN, struct.pack("<H", PROBE_LEN))
    buffer_reply = bf.query(transport, bf.Q_READDATA, bf.R_READDATA)
    zero_buffer = bytes(buffer_reply[1:1 + PROBE_LEN])
    if len(zero_buffer) != PROBE_LEN:
        raise bf.ProtocolError(
            f"buffer response carried {len(zero_buffer)}/{PROBE_LEN} bytes")
    if zero_buffer != bytes(PROBE_LEN):
        raise bf.ProtocolError(
            "reset-initialised buffer is not zero: " + zero_buffer.hex())

    status_after = bf.query(transport, bf.Q_STATUS, bf.R_STATUS)
    validate_status(status_after, "status_after")
    transport.require_complete()
    return status_before, buffer_reply, status_after


def dry_run():
    print("MODE=dry-run; no device enumerated or opened")
    print("ALLOWED_SEQUENCE")
    for number, (label, report) in enumerate(SEQUENCE, 1):
        framed = b"\x00" + report
        print(f"  {number}: {label} payload={report[:8].hex(' ')} ... "
              f"hidraw_len={len(framed)} sha256={hashlib.sha256(framed).hexdigest()}")
    print("FORBIDDEN=set-address, execute-READ, unlock, load-data, reset, erase, program")
    return 0


def live_probe(open_transport=SplitHidrawTransport,
               select_channels=select_bootloader_channels):
    command_node, response_node, command_rejected, response_rejected, app_nodes = (
        select_channels())
    print(f"validated_command_node={command_node} usage_page=0x{bf.COMMAND_USAGE_PAGE:04x}")
    print(f"validated_response_node={response_node} usage_page=0x{bf.RESPONSE_USAGE_PAGE:04x}")
    print(f"command_selector_rejections={len(command_rejected)}")
    print(f"response_selector_rejections={len(response_rejected)}")
    print(f"application_nodes={app_nodes}")
    print("routing=write FF01/EP6; read FF00/EP5")
    print("action=4 exact reports; 3 queries + volatile set-length; no flash access")
    sys.stdout.flush()

    transport = ExactSequenceTransport(open_transport(command_node, response_node))
    try:
        before, buffer_reply, after = run_probe(transport)
    finally:
        transport.close()

    print(f"status_before={before.hex(' ')}")
    print(f"buffer_reply={buffer_reply.hex(' ')}")
    print(f"status_after={after.hex(' ')}")
    print("RESULT=PASS locked=true idle=true error=0 zero_buffer_48=true")
    print("FLASH_ACCESS=none")
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true",
                   help="open the validated bootloader node and run the exact probe")
    p.add_argument("--acknowledge-volatile-length", action="store_true",
                   help="acknowledge that report 2 changes the RAM-only response length")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.run:
        return dry_run()
    if not args.acknowledge_volatile_length:
        print("REFUSED: --run also requires --acknowledge-volatile-length",
              file=sys.stderr)
        return 2
    try:
        return live_probe()
    except (bf.SelectionError, bf.ProtocolError, ExactSequenceError, OSError) as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
