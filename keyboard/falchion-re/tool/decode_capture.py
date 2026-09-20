#!/usr/bin/env python3
"""Decode the Falchion's 64-byte vendor-HID reports out of a USBPcap capture.

Read-only and offline. Captures are evidence: they are opened for reading only
and never modified. NO DEVICE IS ACCESSED and NO FRAME IS CONSTRUCTED FOR
TRANSMISSION — every byte string printed here was READ OUT of a capture.

WHY THIS MODULE EXISTS. `tools/decode.ps1` is the Windows-side decoder, and
PowerShell cannot be run in this repository's environment, so the decoder's
*rules* lived only in a script nobody could test. Log 131 found the script
extracting `usb.capdata`, which USBPcap leaves empty, and claiming a
0b05:1b7e restriction it never implemented. This module is the same decoder in
a form the offline suite can actually exercise against
`captures/02-polling-rate.pcap`, and it owns the constants the PowerShell
script must agree with. `--check` fails if the two drift apart.

THE RULES, stated once, here:

  * payloads come from `usbhid.data`; `usb.capdata` is empty for USBPcap
    (log 126 step 0, tools/README.md);
  * the subject is identified by VID:PID 0b05:1b7e read off the wire, never by
    a hard-coded bus or device address — the preserved capture holds the
    subject at address 6 and again at address 7 across a replug;
  * descriptor identity is (idVendor, idProduct, bcdDevice), the same three
    fields the PowerShell script uses. One interface/bus/address key reporting
    two different such tuples is a DESCRIPTOR-IDENTITY CONFLICT and the capture
    is refused. An address reused by a device with an IDENTICAL descriptor
    cannot be detected at all — see `conflicting_keys`;
  * only the vendor configuration pair counts: OUT endpoint 0x0d, IN endpoint
    0x85, payload exactly 64 bytes;
  * direction comes from the endpoint's direction bit, not from matching text
    in `usb.src`/`usb.dst`;
  * anything on a root hub that is not the subject is not decoded at all.

Examples:
    python3 tool/decode_capture.py captures/02-polling-rate.pcap
    python3 tool/decode_capture.py captures/02-polling-rate.pcap --json
    python3 tool/decode_capture.py --check
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "captures"
POWERSHELL = ROOT / "tools/decode.ps1"

FALCHION_VID = 0x0B05
FALCHION_PID = 0x1B7E
VENDOR_OUT = 0x0D          # interface 1, interrupt OUT
VENDOR_IN = 0x85           # interface 1, interrupt IN
REPORT_BYTES = 64

PAYLOAD_FIELD = "usbhid.data"
IDENTITY_FILTER = "usb.idVendor"

# A USB device address is scoped to a bus, and `capture.ps1` records every
# USBPcap interface into one file, so an address on its own is not an identity.
# `01-first-launch.pcapng` proves it: address 1 is an ASMedia hub on bus 2 and
# a Logitech receiver on bus 3. The scope is the capture interface and the bus
# together; `frame.interface_id` is empty in a single-interface .pcap, which is
# fine because it is then empty for every frame in that file.
SCOPE_FIELDS = ("frame.interface_id", "usb.bus_id")
IDENTITY_FIELDS = SCOPE_FIELDS + ("usb.device_address", "usb.idVendor",
                                  "usb.idProduct", "usb.bcdDevice")
REPORT_FIELDS = ("frame.number", "frame.time_relative", "frame.time_epoch"
                 ) + SCOPE_FIELDS + ("usb.device_address",
                                     "usb.endpoint_address", "usb.data_len",
                                     PAYLOAD_FIELD)

# The block tools/decode.ps1 must carry verbatim, so the two implementations
# cannot drift. `--check` parses it out of the script and compares values.
PS_BLOCK_BEGIN = "# CANONICAL-BEGIN decode_capture.py owns these values"
PS_BLOCK_END = "# CANONICAL-END"


class DecodeError(Exception):
    """The capture cannot be decoded, and guessing is not an option."""


def tshark_binary():
    path = shutil.which("tshark")
    if path is None:
        raise DecodeError("tshark is not installed; this tool parses captures "
                          "with tshark and installs nothing")
    return path


def _run(path, display_filter, fields):
    if not Path(path).is_file():
        raise DecodeError(f"not a file: {path}")
    command = [tshark_binary(), "-r", str(path), "-T", "fields",
               "-E", "separator=/t"]
    if display_filter:
        command += ["-Y", display_filter]
    for field in fields:
        command += ["-e", field]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise DecodeError(f"tshark failed on {path}: "
                          f"{result.stderr.strip() or result.returncode}")
    return result.stdout


def scope_key(interface, bus, address):
    """The identity a frame is attributed to: interface, bus and address."""
    return (interface.strip(), bus.strip(), int(address))


def parse_identities(text):
    """scope key -> tuple of (vid, pid, bcdDevice) seen for it, in order.

    Every observation is kept. The descriptor identity is the full
    (idVendor, idProduct, bcdDevice) triple — the same three fields
    `tools/decode.ps1` uses — so a key reporting two different triples is a
    DESCRIPTOR-IDENTITY CONFLICT and `select_subject` refuses the capture
    rather than silently picking the last owner. It is not, and is not called,
    complete address-reuse detection: see `conflicting_keys`.
    """
    found = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != len(IDENTITY_FIELDS) or not parts[2].strip():
            continue
        key = scope_key(parts[0], parts[1], parts[2])
        identity = tuple(int(value, 16) for value in parts[3:])
        found.setdefault(key, [])
        if identity not in found[key]:
            found[key].append(identity)
    return {key: tuple(values) for key, values in found.items()}


def identity_map(path):
    """scope key -> identities, read off the wire.

    USBPcap synthesises a descriptor exchange at t=0 for devices already
    enumerated when the capture began, so a device that re-enumerates at a new
    address appears under two keys; both are kept, because both carried
    traffic.
    """
    found = parse_identities(_run(path, IDENTITY_FILTER, IDENTITY_FIELDS))
    if not found:
        raise DecodeError(
            f"{path}: no device descriptor anywhere in this capture, so no "
            "frame can be attributed to a device; refusing to decode")
    return found


def conflicting_keys(identities):
    """Keys that reported more than one DESCRIPTOR IDENTITY during the capture.

    Named for what it measures, and no wider. It compares the
    (idVendor, idProduct, bcdDevice) tuples seen on one interface/bus/address
    key, which detects an address the host handed to a device with a DIFFERENT
    descriptor. It does NOT detect an address reused by a device with an
    IDENTICAL descriptor: two units of the same model and firmware revision are
    indistinguishable by this method, and USBPcap offers no reset or
    enumeration epoch that would separate them reliably. That gap is a stated
    limitation, not something the refusal covers.
    """
    return tuple(sorted(key for key, values in identities.items()
                        if len(values) > 1))


def select_subject(identities):
    """Every scope key the Falchion held, however many times it re-enumerated.

    Separated from the tshark call so both refusal paths are testable without
    a capture that exhibits them.
    """
    conflicting = conflicting_keys(identities)
    if conflicting:
        raise DecodeError(
            "descriptor-identity conflict on these interface/bus/address "
            "keys: more than one VID:PID:bcdDevice was reported for each, so "
            "a display filter cannot separate their traffic and nothing may "
            "be attributed to either owner: "
            + ", ".join(describe_key(key) for key in conflicting))
    found = tuple(sorted(
        key for key, values in identities.items()
        if values[0][:2] == (FALCHION_VID, FALCHION_PID)))
    if not found:
        raise DecodeError(
            f"no device identified itself as "
            f"{FALCHION_VID:04x}:{FALCHION_PID:04x}; this capture has no "
            "subject and nothing in it may be attributed to the keyboard")
    return found


def describe_key(key):
    interface, bus, address = key
    scope = f"interface {interface} " if interface else ""
    return f"{scope}bus {bus} address {address}"


def subject_keys(path):
    return select_subject(identity_map(path))


def subject_addresses(path):
    """The addresses only — kept for callers that just want the numbers."""
    return tuple(sorted({key[2] for key in subject_keys(path)}))


def key_filter(key):
    interface, bus, address = key
    parts = []
    if interface:
        parts.append(f"frame.interface_id=={interface}")
    if bus:
        parts.append(f"usb.bus_id=={bus}")
    parts.append(f"usb.device_address=={address}")
    return "(" + " && ".join(parts) + ")"


def report_filter(keys):
    """The one display filter that defines "a vendor configuration report".

    Scoped per key, never by address alone: `usb.device_address==2` would also
    match a different device holding address 2 on another bus in the same file.
    """
    if not keys:
        raise DecodeError("no subject scope key to filter on")
    return ("(" + " || ".join(key_filter(key) for key in sorted(keys)) + ")"
            f" && (usb.endpoint_address==0x{VENDOR_OUT:02x}"
            f" || usb.endpoint_address==0x{VENDOR_IN:02x})"
            f" && usb.data_len=={REPORT_BYTES}")


def direction(endpoint):
    """IN or OUT from bit 7 of the endpoint address. No text matching."""
    return "IN" if endpoint & 0x80 else "OUT"


def rows_to_reports(rows, keys, source="<rows>"):
    """Turn tshark field rows into reports, keeping only the subject's.

    Split out from the tshark call so the scoping can be tested with rows that
    put the same device address on two different buses — which is exactly the
    case a display filter alone is trusted to handle, and exactly the case
    worth not trusting.
    """
    wanted = set(keys)
    out = []
    for line in rows:
        parts = line.split("\t")
        if len(parts) != len(REPORT_FIELDS):
            continue
        (frame, relative, epoch, interface, bus, address, endpoint, length,
         payload) = parts
        if not payload:
            continue                # URB submit/complete carrying no data
        key = scope_key(interface, bus, address)
        if key not in wanted:
            continue                # another device, possibly the same address
        clean = payload.replace(":", "").replace(" ", "").lower()
        if len(clean) != REPORT_BYTES * 2:
            raise DecodeError(
                f"{source} frame {frame}: {PAYLOAD_FIELD} is "
                f"{len(clean) // 2} bytes, not {REPORT_BYTES}")
        try:
            bytes.fromhex(clean)
        except ValueError as exc:
            raise DecodeError(f"{source} frame {frame}: {exc}") from exc
        endpoint_value = int(endpoint, 16)
        if endpoint_value not in (VENDOR_OUT, VENDOR_IN):
            raise DecodeError(f"{source} frame {frame}: endpoint {endpoint} "
                              "passed the filter but is not a vendor endpoint")
        out.append({
            "address": key[2],
            "bus": key[1],
            "direction": direction(endpoint_value),
            "endpoint": endpoint_value,
            "epoch": float(epoch) if epoch else None,
            "frame": int(frame),
            "interface": key[0],
            "length": int(length),
            "opcode": clean[:4],
            "payload": clean,
            "time": float(relative),
        })
    return out


def reports(path):
    """Every 64-byte vendor report belonging to the subject, in order."""
    keys = subject_keys(path)
    rows = _run(path, report_filter(keys), REPORT_FIELDS).splitlines()
    out = rows_to_reports(rows, keys, path)
    if not out:
        raise DecodeError(
            f"{path}: the subject is present but sent no {REPORT_BYTES}-byte "
            f"report on endpoint 0x{VENDOR_OUT:02x} or 0x{VENDOR_IN:02x}; "
            "there is nothing to decode")
    return out


def identity(report):
    """What makes two reports "the same". Direction is part of it.

    An IN echo of an OUT request carries identical bytes, so collapsing on the
    payload alone silently merges a request with its reply and makes a -Diff
    show nothing where a whole transaction changed.
    """
    return report["direction"], report["payload"]


def unique(records):
    """First occurrence of each (direction, payload), order preserved."""
    seen, out = set(), []
    for record in records:
        key = identity(record)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def opcode_histogram(records, want="OUT"):
    return Counter(record["opcode"] for record in records
                   if record["direction"] == want)


def difference(left, right):
    """Reports present in `left` and absent from `right`, identity-aware."""
    other = {identity(record) for record in right}
    return [record for record in unique(left) if identity(record) not in other]


# ------------------------------------------------- PowerShell drift guard

def powershell_constants(text):
    """Parse the canonical block out of tools/decode.ps1."""
    start = text.find(PS_BLOCK_BEGIN)
    end = text.find(PS_BLOCK_END, start + 1)
    if start < 0 or end < 0:
        raise DecodeError("tools/decode.ps1 has no canonical constants block; "
                          "it can no longer be proved to match this module")
    block = text[start + len(PS_BLOCK_BEGIN):end]
    found = {}
    for name, value in re.findall(
            r"^\s*\$(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*$", block, re.M):
        found[name] = int(value, 0)
    return found


EXPECTED_PS = {
    "FalchionVid": FALCHION_VID,
    "FalchionPid": FALCHION_PID,
    "VendorOutEndpoint": VENDOR_OUT,
    "VendorInEndpoint": VENDOR_IN,
    "ReportBytes": REPORT_BYTES,
}


def powershell_drift(path=POWERSHELL):
    """Names and values that disagree between decode.ps1 and this module."""
    text = Path(path).read_text(encoding="utf-8")
    found = powershell_constants(text)
    problems = [f"{name}: decode.ps1 has "
                f"{found.get(name, 'nothing')!r}, expected {value!r}"
                for name, value in sorted(EXPECTED_PS.items())
                if found.get(name) != value]
    code = strip_comments(text)
    if PAYLOAD_FIELD not in code:
        problems.append(f"decode.ps1 does not extract {PAYLOAD_FIELD}")
    if "usb.capdata" in code:
        problems.append("decode.ps1 still reads usb.capdata, which USBPcap "
                        "leaves empty")
    for needle in ("usb.idVendor", "usb.idProduct", "usb.bcdDevice",
                   "usb.endpoint_address", "usb.data_len",
                   "usb.bus_id", "frame.interface_id", "frame.time_epoch"):
        if needle not in code:
            problems.append(f"decode.ps1 no longer filters on {needle}")
    if re.search(r"usb\.device_address==\$_", code):
        problems.append("decode.ps1 builds an address-only filter again")
    # The descriptor identity must be the same three fields on both sides.
    identity = re.search(r'[$]ident\s*=\s*"([^"]*)"', code)
    if identity is None or identity.group(1).count("$(") != 3:
        problems.append("decode.ps1's descriptor identity is not the three "
                        "fields idVendor, idProduct and bcdDevice")
    return problems


def strip_comments(text):
    """PowerShell source with its block help and `#` comments removed.

    The prose has to be free to explain why `usb.capdata` is the wrong field
    without that explanation reading as the bug it warns about.
    """
    text = re.sub(r"<#.*?#>", "", text, flags=re.S)
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


# ------------------------------------------------------------------ output

def to_dict(path, records):
    return {
        "capture": str(path),
        "endpoints": {"in": VENDOR_IN, "out": VENDOR_OUT},
        "out_opcodes": dict(sorted(opcode_histogram(records).items())),
        "report_bytes": REPORT_BYTES,
        "reports": records,
        "subject": f"{FALCHION_VID:04x}:{FALCHION_PID:04x}",
        "subject_keys": [describe_key(key) for key in subject_keys(path)],
        "totals": {
            "in": sum(1 for r in records if r["direction"] == "IN"),
            "out": sum(1 for r in records if r["direction"] == "OUT"),
            "reports": len(records),
            "unique": len(unique(records)),
        },
    }


def report_lines(path, records, diff_path=None, diff_records=None):
    keys = subject_keys(path)
    out = [f"CAPTURE {path}",
           f"SUBJECT {FALCHION_VID:04x}:{FALCHION_PID:04x} at "
           + "; ".join(describe_key(key) for key in keys),
           f"FILTER {report_filter(keys)}",
           f"REPORTS {len(records)} "
           f"out={sum(1 for r in records if r['direction'] == 'OUT')} "
           f"in={sum(1 for r in records if r['direction'] == 'IN')} "
           f"unique={len(unique(records))}"]
    if diff_records is None:
        out.append("")
        out.append(" frame      time  dir  len  first 16 bytes")
        for record in unique(records):
            out.append(_line(record))
        out.append("")
        out.append("OUT opcode histogram (first two bytes):")
        for opcode, count in sorted(opcode_histogram(records).items()):
            out.append(f"  {opcode[:2]} {opcode[2:]}  x{count}")
        return out
    out += [f"BASELINE {diff_path}",
            f"BASELINE_REPORTS {len(diff_records)}",
            "",
            f"ONLY in {Path(path).name}:"]
    out += [_line(record) for record in difference(records, diff_records)]
    out += ["", f"ONLY in {Path(diff_path).name}:"]
    out += [_line(record) for record in difference(diff_records, records)]
    return out


def _line(record):
    payload = record["payload"]
    head = " ".join(payload[i:i + 2] for i in range(0, 32, 2))
    tail = payload[32:]
    rest = "(rest zero)" if set(tail) <= {"0"} else "(rest nonzero)"
    return (f"{record['frame']:>6}  {record['time']:>9.3f}  "
            f"{record['direction']:<3}  {record['length']:>3}B  {head}  {rest}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="capture to decode")
    parser.add_argument("--diff", help="baseline capture to compare against")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="prove tools/decode.ps1 still matches this module")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.check:
        problems = powershell_drift()
        for problem in problems:
            print(f"DRIFT {problem}")
        print(f"RESULT in_sync={not problems} drift={len(problems)}")
        return 1 if problems else 0
    if not args.path:
        print("RESULT error=give a capture path, or --check")
        return 1
    try:
        records = reports(args.path)
        baseline = reports(args.diff) if args.diff else None
    except DecodeError as exc:
        print(f"RESULT reports=0 error={exc}")
        return 1
    if args.json:
        print(json.dumps(to_dict(args.path, records), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(args.path, records, args.diff, baseline)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
