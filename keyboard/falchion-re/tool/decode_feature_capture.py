#!/usr/bin/env python3
"""Reproduce the feature-capture decodes of logs 135-137 from the evidence.

Read-only and offline. Captures, profile copies and macro files are opened for
reading only. NO DEVICE IS ACCESSED and NO FRAME IS CONSTRUCTED FOR
TRANSMISSION -- every byte printed here was READ OUT of a capture.

This module is the analysis that logs 135-137 quote, moved out of throwaway
session scripts so that each quoted table can be regenerated:

  pairs     every vendor request with its reply, with wall-clock time
            (log 135 s1-s5, log 136 s2-s3, log 137 s1-s2)
  macro     the 54 upload(s) paired record by record with a .GMAC file
            (log 135 s6, log 136 s1.1, log 137 s4)
  lever     the keyboard's own 03 76 lever reports on endpoint 0x8c (log 137 s3)
  profiles  decode two raw copies of the AC profile folder and diff them
            (log 135 s2/s4/s5/s8, log 136 s3)

Vendor reports come from `decode_capture.reports()`, so the subject is found by
VID:PID and bus-scoped identity exactly as there. Profiles are compared with
`profile_diff.diff()`, the same canonical comparison the snapshot tool uses.

KEY NUMBERS are AT-101 key positions (log 136 s1). In a MACRO the number is the
key AC chose to type from the host key event, so "\\" appears as 42 and Enter
as 108 (log 137 s4).

Examples:
    python3 tool/decode_feature_capture.py pairs captures/03b-features.pcap --op 5150 --op 5121
    python3 tool/decode_feature_capture.py macro captures/03b-features.pcap snapshots/03b-features-macros/Macro03.GMAC
    python3 tool/decode_feature_capture.py lever captures/03d-finish.pcap
    python3 tool/decode_feature_capture.py profiles snapshots/03b-features-before-raw snapshots/03b-features-after-raw
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decode_capture as dc
import profile_diff as pd

LEVER_ENDPOINT = 0x8C
LEVER_REPORT = bytes.fromhex("0376")
MACRO_OPCODE = 0x54
MACRO_HEADER = 9           # 54 00 <count> <cont> <key> 00 00 00 00
MACRO_RECORD = 4           # <key> <02 press | 01 release> <delay u16 LE, ms>
MACRO_END = 0xFF
PRESS, RELEASE = 0x02, 0x01

# Key names for observed wire numbers (logs 136-137), plus conventional
# positions 1 and 29. Those two positions were not observed in these captures.
AT101 = {
    1: "`", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8",
    10: "9", 11: "0", 12: "-", 13: "=", 15: "Backspace", 16: "Tab",
    17: "Q", 18: "W", 19: "E", 20: "R", 21: "T", 22: "Y", 23: "U", 24: "I",
    25: "O", 26: "P", 27: "[", 28: "]", 29: "\\ (ANSI)", 30: "Caps",
    31: "A", 32: "S", 33: "D", 34: "F", 35: "G", 36: "H", 37: "J", 38: "K",
    39: "L", 40: ";", 41: "'", 42: "\\ (ISO 42)", 43: "Enter", 44: "LShift",
    46: "Z", 47: "X", 48: "C", 49: "V", 50: "B", 51: "N", 52: "M", 53: ",",
    54: ".", 55: "/", 57: "RShift", 58: "LCtrl", 59: "Win", 60: "LAlt",
    61: "Space", 62: "RAlt", 64: "RCtrl", 75: "Ins", 76: "Del", 79: "Left",
    83: "Up", 84: "Down", 85: "PgUp", 86: "PgDn", 89: "Right",
    108: "Enter (keypad 108)", 110: "Esc",
}

# GMAC names paired with captured macro events in logs 135-137. Do not infer
# unseen macro keys from physical-key positions: AC encodes Enter and backslash
# differently in macros. Mouse encodings are supported only for observed pairs.
MACRO_KEYS = {
    **{name: number for number, name in AT101.items()
       if len(name) == 1 and name != "`"},
    "\\": 42, "Comma": 53, "Backspace": 15, "Enter": 108,
    "Del": 76, "PageUp": 85, "PageDown": 86, "Up": 83,
    "CapsLock": 30, "Esc": 110,
}
MOUSE_EVENTS = {(0xF0, 0x12): ("Press", "Left Click")}


def key_name(number):
    return AT101.get(number, f"?{number}")


def clock(epoch, offset_hours=None):
    """Wall-clock time of a capture epoch; the logs quote local UTC-06:00."""
    if offset_hours is None:
        moment = datetime.fromtimestamp(epoch)
    else:
        moment = datetime.fromtimestamp(epoch, timezone(timedelta(hours=offset_hours)))
    return moment.strftime("%H:%M:%S.%f")[:-3]


def hexbytes(payload, keep=6):
    """Hex with the trailing zero padding of a 64-byte report dropped."""
    raw = bytes.fromhex(payload)
    used = len(raw.rstrip(b"\0"))
    return " ".join(f"{b:02x}" for b in raw[:max(used, keep)])


# --- pairs -------------------------------------------------------------------

def profile_selector(record):
    """Raw profile byte of a complete 51 00 report, otherwise None."""
    payload = record["payload"]
    if payload[:4].lower() == "5100" and len(payload) >= 10:
        return int(payload[8:10], 16)
    return None


def reply_warning(request, reply):
    """Report a raw profile disagreement without inferring its cause."""
    requested, reported = profile_selector(request), profile_selector(reply)
    if requested is not None and reported is not None and requested != reported:
        return f"profile differs: requested {requested:02x}, reply {reported:02x}"
    return None


def request_reply_results(records):
    """(request, reply, status), in request order, without reusing an IN.

    Match command headers within an interface/bus/device scope. 12 12 may
    reply as 12 13 (the statically recovered success branch). For competing
    51 00 requests, narrow ownership by the reply's profile byte when possible.
    Each reply closes that command's pending group: nonmatching profile
    requests remain unanswered, and identical retries remain ambiguous.
    This is a capture correlation heuristic, not a transaction identifier.
    A sole candidate can have a different profile; see reply_warning().
    """
    results, pending = [], {}
    for record in records:
        scope = tuple(record.get(k) for k in ("interface", "bus", "address"))
        command = record["payload"][:4].lower()
        if record["direction"] == "OUT":
            index = len(results)
            results.append((record, None, "unanswered"))
            pending.setdefault((scope, command), []).append(index)
            continue
        commands = (command, "1212") if command == "1213" else (command,)
        candidates = []
        for header in commands:
            candidates.extend(pending.pop((scope, header), []))
        profile = profile_selector(record)
        if len(candidates) > 1 and profile is not None:
            echoes = [index for index in candidates
                      if profile_selector(results[index][0]) == profile]
            if echoes:
                candidates = echoes
        if len(candidates) == 1:
            index = candidates[0]
            results[index] = (results[index][0], record, "matched")
        elif candidates:
            for index in candidates:
                results[index] = (results[index][0], None, "ambiguous")
    return results


def request_reply_pairs(records):
    """Compatibility view: unresolved requests have reply None."""
    return [(request, reply) for request, reply, _ in request_reply_results(records)]


# --- macro -------------------------------------------------------------------

def macro_frames(records):
    """Every 54 upload frame, in capture order."""
    return [r for r in records if r["direction"] == "OUT"
            and bytes.fromhex(r["payload"])[0] == MACRO_OPCODE]


def split_uploads(frames):
    """Group frames into uploads: byte 3 == 0 starts one, 1 continues it."""
    uploads = []
    for frame in frames:
        raw = bytes.fromhex(frame["payload"])
        if raw[3] == 0 or not uploads:
            uploads.append([])
        uploads[-1].append(frame)
    return uploads


def upload_records(frames):
    """(key, action, delay_ms) for every record of one upload, and its key.

    Byte 2 is the number of 4-byte records in THIS frame, terminator included
    (log 136 s3.4); byte 4 is the key the macro is assigned to.
    """
    records, assigned = [], None
    for frame in frames:
        raw = bytes.fromhex(frame["payload"])
        assigned = raw[4]
        body = raw[MACRO_HEADER:MACRO_HEADER + raw[2] * MACRO_RECORD]
        for i in range(0, len(body), MACRO_RECORD):
            rec = body[i:i + MACRO_RECORD]
            if rec[0] == MACRO_END:
                return records, assigned
            records.append((rec[0], rec[1], rec[2] | rec[3] << 8))
    return records, assigned


def parse_gmac(text):
    """AC's plain-text macro: [('Press'|'Release', name, delay_after_ms), ...]."""
    events = []
    for line in text.splitlines():
        parts = line.split(",")
        if parts[0] in ("Press", "Release"):
            events.append([parts[0], parts[1], None])
        elif parts[0] == "Delay" and events:
            events[-1][2] = int(parts[1])
    return [tuple(e) for e in events]


def compare_macro(records, events):
    """Row-by-row comparison. Returns (rows, all_matched).

    A row matches only when the observed key encoding, action and delay agree.
    A missing GMAC delay is 0 on the wire. Unknown encodings are unsupported
    (good=None), never a match. Missing/extra events also make the result false.
    """
    rows, ok = [], len(records) == len(events)
    for (key, action, delay), (kind, name, gdelay) in zip(records, events):
        mouse = MOUSE_EVENTS.get((key, action))
        wire_kind = (mouse[0] if mouse else
                     {PRESS: "Press", RELEASE: "Release"}.get(action, f"?{action:02x}"))
        expected = next((encoding for encoding, event in MOUSE_EVENTS.items()
                         if event == (kind, name)), None)
        if expected is None and name in MACRO_KEYS and kind in ("Press", "Release"):
            expected = (MACRO_KEYS[name], PRESS if kind == "Press" else RELEASE)
        supported = mouse is not None or (key in MACRO_KEYS.values()
                                         and action in (PRESS, RELEASE))
        good = (None if expected is None or not supported else
                (key, action) == expected and delay == (gdelay or 0))
        ok = ok and good is True
        rows.append((key, wire_kind, delay, kind, name, gdelay, good))
    return rows, ok


# --- lever -------------------------------------------------------------------

def lever_state(payload_hex):
    """01 = ON, 00 = OFF for a 03 76 report, else None (log 137 s3)."""
    raw = bytes.fromhex(payload_hex)
    if raw[:2] != LEVER_REPORT or len(raw) < 5:
        return None
    return raw[4]


def endpoint_reports(path, endpoint):
    """(epoch, payload_hex) of the subject's IN reports on one endpoint."""
    keys = dc.subject_keys(path)
    scope = " || ".join(dc.key_filter(k) for k in sorted(keys))
    text = dc._run(path, f"({scope}) && usb.endpoint_address==0x{endpoint:02x} && usb.data_len>0",
                   ["frame.time_epoch", dc.PAYLOAD_FIELD])
    out = []
    for line in text.splitlines():
        epoch, payload = (line.split("\t") + ["", ""])[:2]
        if epoch and payload:
            out.append((float(epoch), payload.replace(":", "")))
    return out


# --- profiles ----------------------------------------------------------------

def decode_profile_xml(text):
    """AC profile XML -> JSON: base64 -> percent-decode -> JSON (notes/key-matrix.md s3)."""
    root = ET.fromstring(text)
    data = root.find("./device_type/device/function/file_data").text
    return json.loads(urllib.parse.unquote(base64.b64decode(data).decode("utf-8")))


def profile_folder(path):
    """A raw copy is either flat (03b) or has a profiles/ subfolder (03c on)."""
    path = Path(path)
    return path / "profiles" if (path / "profiles").is_dir() else path


def profile_changes(before, after, skip_per_key_actuation=True):
    """{file: [changes]} over every fp_*_config_*.xml in either copy."""
    b, a = profile_folder(before), profile_folder(after)
    names = sorted({p.name for p in b.glob("fp_*_config_*.xml")} |
                   {p.name for p in a.glob("fp_*_config_*.xml")})
    out = {}
    for name in names:
        old = decode_profile_xml((b / name).read_text(encoding="utf-8")) if (b / name).exists() else {}
        new = decode_profile_xml((a / name).read_text(encoding="utf-8")) if (a / name).exists() else {}
        changes = pd.diff(old, new)
        if skip_per_key_actuation:
            changes = [c for c in changes
                       if not (".keyboardButton." in c[0] and c[0].endswith(".normal.actuation"))]
        out[name] = changes
    return out


# --- CLI ---------------------------------------------------------------------

def cmd_pairs(args):
    for request, reply, status in request_reply_results(dc.reports(args.capture)):
        if args.op and not any(request["payload"].startswith(op.lower()) for op in args.op):
            continue
        print(f"{clock(request['epoch'], args.utc_offset)}  OUT {hexbytes(request['payload'])}")
        if reply:
            warning = reply_warning(request, reply)
            suffix = f"  [WARNING: {warning}]" if warning else ""
            print(f"{'':12}  IN  {hexbytes(reply['payload'])}{suffix}")
        else:
            print(f"{'':12}  IN  [{status}]")
    return 0


def cmd_macro(args):
    events = parse_gmac(Path(args.gmac).read_text(encoding="utf-8", errors="replace"))
    uploads = split_uploads(macro_frames(dc.reports(args.capture)))
    if not uploads:
        print("no 54 upload in this capture")
        return 1
    best = 1
    for n, frames in enumerate(uploads, 1):
        records, assigned = upload_records(frames)
        rows, ok = compare_macro(records, events)
        outcome = ("MATCH" if ok else "unsupported encoding"
                   if any(row[6] is None for row in rows) else "no match")
        print(f"upload {n}: {clock(frames[0]['epoch'], args.utc_offset)}, {len(frames)} frame(s), "
              f"assigned to {assigned} ({key_name(assigned)}), {len(records)} records vs "
              f"{len(events)} GMAC events -> {outcome}")
        if ok or args.all:
            for record, row in zip(records, rows):
                key, wk, delay, kind, name, gdelay, good = row
                label = MOUSE_EVENTS.get(record[:2], (None, key_name(key)))[1]
                detail = ("" if good else "   <-- unsupported encoding"
                          if good is None else "   <-- differs")
                print(f"   {key:3d} {label:<18} {wk:<7} {delay:5d} ms   "
                      f"GMAC {kind:<7} {name:<12} {gdelay if gdelay is not None else '-':>5}"
                      f"{detail}")
        if ok:
            best = 0
    return best


def cmd_lever(args):
    found = 0
    for epoch, payload in endpoint_reports(args.capture, LEVER_ENDPOINT):
        state = lever_state(payload)
        if state is not None:
            found += 1
            print(f"{clock(epoch, args.utc_offset)}  03 76 00 00 {state:02x}  "
                  f"{ {1: 'ON', 0: 'OFF'}.get(state, '?') }")
    print(f"{found} lever report(s)")
    return 0


def cmd_profiles(args):
    for name, changes in profile_changes(args.before, args.after, not args.all).items():
        print(f"=== {name}: {len(changes)} change(s)")
        for line in pd.format_changes(changes):
            print(line)
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--utc-offset", type=float, default=None,
                   help="print times at this UTC offset (the logs use -6); default: this host's local time")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pairs"); s.add_argument("capture")
    s.add_argument("--op", action="append", help="only requests starting with these hex bytes, e.g. 5121")
    s.set_defaults(fn=cmd_pairs)
    s = sub.add_parser("macro"); s.add_argument("capture"); s.add_argument("gmac")
    s.add_argument("--all", action="store_true", help="print rows for non-matching uploads too")
    s.set_defaults(fn=cmd_macro)
    s = sub.add_parser("lever"); s.add_argument("capture"); s.set_defaults(fn=cmd_lever)
    s = sub.add_parser("profiles"); s.add_argument("before"); s.add_argument("after")
    s.add_argument("--all", action="store_true", help="include AC's per-key copies of the global actuation")
    s.set_defaults(fn=cmd_profiles)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return args.fn(args)
    except dc.DecodeError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
