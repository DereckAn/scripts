#!/usr/bin/env python3
"""Phase 5F: RGB / LampArray routing, recovered offline.

Read-only. Phase 5B routed endpoint 0x0f as "USB controller -> class ops;
lighting consumer not traced". That consumer is traced here, from the control
endpoint rather than from EP 0x0f — because interface 4's descriptor declares
NO Output report. Every one of its six reports is a FEATURE report, so the
LampArray protocol runs over control transfers and EP 0x0f carries none of it.

WHAT IS RECOVERED, end to end:

    SET_REPORT 0x2109 / GET_REPORT 0xa101, report type 3 (Feature)
      -> FUN_180184b6 calls a registered callback at *(0x1801ebb8)
      -> FUN_18008f12, registered by FUN_18008f4a during INIT_TASK
         bRequest 1 (GET)  -> FUN_1800ffaa   report IDs 1 and 3
         bRequest 9 (SET)  -> FUN_18010102   report IDs 2, 4, 5 and 6
      -> FUN_1800c132(row, col, channels) writes the frame buffer
      -> a 306-byte frame at 0x1802505e, 6 rows x 17 columns x 3 bytes

WHERE IT STOPS. The functions that CONSUME that frame reach no resolved MMIO.
The final hardware interface — SPI, PWM, GPIO or DMA — is NOT identified, and
no block is named on the strength of a plausible shape.

PROTOCOL KNOWLEDGE IS LABELLED. The HID usage page 0x59 report semantics
(LampCount, BoundingBox, LampId, the update channels) are fixed by the LampArray
specification. Everything this module asserts about SIZES and FIELD ORDER comes
from the descriptor's own items; the NAMES are spec-derived and are marked as
such, never as device-observed.

No device access. Examples:
    python3 tool/map_rgb_lamparray.py
    python3 tool/map_rgb_lamparray.py --json
    python3 tool/map_rgb_lamparray.py --write
    python3 tool/map_rgb_lamparray.py --check
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_usb_routing as ur

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"
MATCH_APP = NOTES / "vendor-to-installed-functions-app-b.json"

CONFIDENCES = ("observed", "strongly-inferred", "hypothesis", "unresolved")
SOURCES = ("listing", "decompiler", "bytes", "xref", "spec")

LAMPARRAY_INTERFACE = 4
RELOCATION_DELTA = 0x2C

# --- the frame buffer, read off FUN_1800c132's listing ------------------------
# `cmp r0,#0x6 / bcs` and `cmp r1,#0x11 / bcs` are the bounds; the address
# arithmetic is `row*17` then `*3`, and `col*3`.
FRAME_ROWS = 6
FRAME_COLUMNS = 0x11
FRAME_BYTES_PER_CELL = 3
FRAME_BUFFER = 0x1802505E
FRAME_ORDER = ("red", "green", "blue")
# `muls r3,r4` then `lsrs r3,r3,#0x8`: channel * intensity >> 8.
INTENSITY_SHIFT = 8

# --- the lamp-count table, in the ENTRY image --------------------------------
LAMP_TABLE = 0x500C
LAMP_TABLE_STRIDE = 8
LAMP_TABLE_RECORDS = 8
ENTRY_SLICE = ("installed_app_a_slot0_flash11000_dst00000000_len058ac"
               "_f093979a.bin")

# --- spec-derived usage names, page 0x59 -------------------------------------
# NAMES ONLY. Every size below is measured from the descriptor.
USAGE_NAMES = {
    0x03: "LampCount", 0x04: "BoundingBoxWidthInMicrometers",
    0x05: "BoundingBoxHeightInMicrometers",
    0x06: "BoundingBoxDepthInMicrometers", 0x07: "LampArrayKind",
    0x08: "MinUpdateIntervalInMicroseconds", 0x21: "LampId",
    0x23: "PositionXInMicrometers", 0x24: "PositionYInMicrometers",
    0x25: "PositionZInMicrometers", 0x26: "LampPurposes",
    0x27: "UpdateLatencyInMicroseconds", 0x28: "RedLevelCount",
    0x29: "GreenLevelCount", 0x2A: "BlueLevelCount",
    0x2B: "IntensityLevelCount", 0x2C: "IsProgrammable",
    0x2D: "InputBinding", 0x51: "RedUpdateChannel",
    0x52: "GreenUpdateChannel", 0x53: "BlueUpdateChannel",
    0x54: "IntensityUpdateChannel", 0x55: "LampUpdateFlags",
    0x61: "LampIdStart", 0x62: "LampIdEnd", 0x71: "AutonomousMode",
}
REPORT_NAMES = {
    1: "LampArrayAttributesReport", 2: "LampAttributesRequestReport",
    3: "LampAttributesResponseReport", 4: "LampMultiUpdateReport",
    5: "LampRangeUpdateReport", 6: "LampArrayControlReport",
}
# Which report IDs the firmware actually handles, and on which request.
HANDLED = {1: "GET", 2: "SET", 3: "GET", 4: "SET", 5: "SET", 6: "SET"}


class RgbError(ValueError):
    """The evidence does not support the structure being asked of it."""


@dataclass(frozen=True)
class Claim:
    key: str
    statement: str
    confidence: str
    kind_basis: str
    verified_against: str


CLAIMS = (
    Claim("no_output_report",
          "interface 4 declares no Output report; all six of its reports are "
          "Feature reports, so the LampArray runs over CONTROL transfers and "
          "endpoint 0x0f carries none of it",
          "observed",
          "walking the 327-byte descriptor's own items yields thirteen Main "
          "items, every one of them Feature and none Output",
          "bytes"),
    Claim("feature_callback",
          "both GET_REPORT and SET_REPORT for Feature reports route through "
          "one registered callback at *(0x1801ebb8)",
          "observed",
          "FUN_180184b6 dispatches 0xa101 and 0x2109 with report type 3 to "
          "`(*(code *)*piVar3)(...)`, and DAT_18018860 resolves to 0x1801ebb8",
          "decompiler"),
    Claim("callback_registration",
          "the callback is FUN_18008f12, installed during INIT_TASK",
          "observed",
          "FUN_18008f4a is five instructions: `adr.w r0,0x18008f13` then a "
          "tail branch to `str r0,[r1,#0x0]` through the core struct pointer; "
          "log 106 recorded INIT_TASK calling it first",
          "listing"),
    Claim("request_dispatch",
          "the callback dispatches on bRequest: 1 to the GET handler, 9 to "
          "the SET handler, 0xff to a debug print",
          "observed",
          "`cmp r1,#0x1` / `cmp r1,#0x9` / `cmp r1,#0xff` at 0x18008f16, "
          "0x18008f1a and 0x18008f1e, with `mvn r0,#0x15` for anything else",
          "listing"),
    Claim("get_lengths",
          "the GET handler returns 0x17 = 23 bytes for report ID 1, which is "
          "exactly the descriptor's 22 payload bytes plus the ID prefix",
          "observed",
          "`movs r0,#0x17` / `strh r0,[r4,#0x0]` at 0x1800ffd0 in "
          "FUN_1800ffaa, matched against the item walk's own total",
          "listing"),
    Claim("set_length_cap",
          "SET_REPORT is capped at 64 bytes before the callback is reached",
          "observed",
          "`if (0x3f < uVar14) return -0x5f;` in FUN_180184b6's type-3 branch",
          "decompiler"),
    Claim("lamp_addressing",
          "a lamp is addressed by LampId, translated to a (row, column) pair "
          "through a 2-byte-per-lamp table",
          "observed",
          "`FUN_1800c132(*(byte *)(base + lampId*2), *(byte *)(base + "
          "lampId*2 + 1), &channels[i*4])` in the report-4 loop",
          "decompiler"),
    Claim("multi_update_bounds",
          "every LampId in a multi-update is bounds-checked against the "
          "active configuration's lamp count before it is applied",
          "observed",
          "`if (local_4d[uVar8] <= (ushort)*(byte *)(DAT_18010140 + "
          "(uint)bVar2 * 8))` guards each iteration",
          "decompiler"),
    Claim("frame_geometry",
          f"the frame buffer is {FRAME_ROWS} rows x {FRAME_COLUMNS} columns x "
          f"{FRAME_BYTES_PER_CELL} bytes = "
          f"{FRAME_ROWS * FRAME_COLUMNS * FRAME_BYTES_PER_CELL} bytes",
          "observed",
          "`cmp r0,#0x6` / `bcs` and `cmp r1,#0x11` / `bcs` bound the two "
          "indices, and the address arithmetic is `add.w r0,r0,r0,lsl #0x4` "
          "(row*17) then `add.w r4,r0,r0,lsl #0x1` (*3) plus "
          "`add.w r1,r1,r1,lsl #0x1` (col*3)",
          "listing"),
    Claim("frame_order",
          "the channel order in the frame is red, green, blue at cell offsets "
          "0, 1 and 2, eight bits each",
          "observed",
          "three `strb` at [r0,r1], [r0,#0x1] and [r0,#0x2], sourced from "
          "param_3[0], [1] and [2] in that order",
          "listing"),
    Claim("intensity",
          f"intensity scales each channel as (channel * intensity) >> "
          f"{INTENSITY_SHIFT}",
          "observed",
          "`ldrb r4,[r2,#0x3]` then `muls r3,r4` then `lsrs r3,r3,#0x8`, "
          "repeated for all three channels",
          "listing"),
    Claim("out_of_range_dropped",
          "a lamp outside the frame's bounds is dropped silently, with no "
          "error path",
          "observed",
          "both `bcs` branches jump straight to `pop {r4,pc}` at 0x1800c16c",
          "listing"),
    Claim("autonomous_mode",
          "report ID 6 sets a pair of complementary flags and calls two "
          "further functions, one of them with the current mode",
          "strongly-inferred",
          "`*(bool *)(DAT_18010134 + 3) = bVar1; *(bool *)DAT_18010134 = "
          "!bVar1;` then FUN_1800fd4c() and FUN_18004498(0x81,5,0,...)",
          "decompiler"),
    Claim("hardware_boundary",
          "the final hardware interface is NOT identified",
          "unresolved",
          "the two functions that consume the frame buffer, FUN_1800aba4 and "
          "FUN_1800aab0, reach no resolved MMIO at all: their closures report "
          "79 and 91 unresolved-base accesses and zero resolved ones. No "
          "SPI, PWM, GPIO or DMA interface was reached, and no block is named",
          "xref"),
    Claim("frame_timing",
          "frame timing, double buffering and any interaction with the "
          "keyboard scan tick are NOT recovered",
          "unresolved",
          "the frame consumers are not reached from the Phase 5C tick chain, "
          "and no second buffer or swap was found",
          "xref"),
)


def descriptor_reports(release="installed"):
    """Every report in interface 4's descriptor, from its own items."""
    parsed, data = ur.parse_region(release)
    item = parsed.interfaces[LAMPARRAY_INTERFACE]
    chunk = data[item.report_offset:item.report_offset + item.report_length]
    reports = {}
    index = 0
    rid = size = count = None
    usages = []
    while index < len(chunk):
        prefix = chunk[index]
        width = prefix & 3
        width = 4 if width == 3 else width
        payload = chunk[index + 1:index + 1 + width]
        value = int.from_bytes(payload, "little") if payload else None
        kind, tag = (prefix >> 2) & 3, (prefix >> 4) & 0xF
        if kind == 1:
            if tag == 0x7:
                size = value
            elif tag == 0x9:
                count = value
            elif tag == 0x8:
                rid = value
        elif kind == 2 and tag == 0x0:
            usages.append(value)
        elif kind == 0 and tag in (0x8, 0x9, 0xB):
            entry = reports.setdefault(
                rid, {"bits": 0, "fields": [], "kinds": set()})
            entry["bits"] += (size or 0) * (count or 0)
            entry["kinds"].add({0x8: "Input", 0x9: "Output",
                                0xB: "Feature"}[tag])
            entry["fields"].append(
                {"count": count, "size": size,
                 "usages": [{"id": usage,
                             "spec_name": USAGE_NAMES.get(usage)}
                            for usage in usages]})
            usages = []
        elif kind == 0 and tag == 0xA:
            usages = []
        index += 1 + width
    for rid, entry in reports.items():
        entry["payload_bytes"] = (entry["bits"] + 7) // 8
        entry["wire_bytes"] = entry["payload_bytes"] + 1
        entry["kinds"] = sorted(entry["kinds"])
        entry["spec_name"] = REPORT_NAMES.get(rid)
        entry["firmware_handles"] = HANDLED.get(rid)
    return reports


def lamp_counts():
    """The per-configuration lamp counts, from the ENTRY image's own bytes."""
    data = (IMPORTS / ENTRY_SLICE).read_bytes()
    if LAMP_TABLE + LAMP_TABLE_RECORDS * LAMP_TABLE_STRIDE > len(data):
        raise RgbError("the lamp-count table does not fit the entry slice")
    return [data[LAMP_TABLE + index * LAMP_TABLE_STRIDE]
            for index in range(LAMP_TABLE_RECORDS)]


def frame_offset(row, column):
    """The cell offset, exactly as FUN_1800c132's shift-multiplies compute it."""
    if not 0 <= row < FRAME_ROWS:
        raise RgbError(f"row {row} outside 0..{FRAME_ROWS - 1}")
    if not 0 <= column < FRAME_COLUMNS:
        raise RgbError(f"column {column} outside 0..{FRAME_COLUMNS - 1}")
    return (row * FRAME_COLUMNS + column) * FRAME_BYTES_PER_CELL


def apply_intensity(channel, intensity):
    """(channel * intensity) >> 8, the recovered scaling."""
    if not 0 <= channel <= 0xFF or not 0 <= intensity <= 0xFF:
        raise RgbError("channel and intensity are byte values")
    return (channel * intensity) >> INTENSITY_SHIFT


def write_cell(frame, row, column, red, green, blue, intensity):
    """One lamp update, as FUN_1800c132 performs it.

    Out-of-range coordinates are DROPPED, matching the firmware's two `bcs`
    branches, rather than raising — the caller cannot tell either.
    """
    if not (0 <= row < FRAME_ROWS and 0 <= column < FRAME_COLUMNS):
        return frame
    base = frame_offset(row, column)
    for offset, channel in enumerate((red, green, blue)):
        frame[base + offset] = apply_intensity(channel, intensity)
    return frame


def blank_frame():
    return bytearray(FRAME_ROWS * FRAME_COLUMNS * FRAME_BYTES_PER_CELL)


def measured_matches():
    payload = json.loads(MATCH_APP.read_text())
    return {match["installed"]["entry"]:
            (match["vendor"]["entry"], match["confidence"])
            for match in payload.get("matches", ())
            if match.get("installed") and match.get("vendor")}


ROUTE_FUNCTIONS = {
    "control_handler": 0x180184B6,
    "feature_callback": 0x18008F12,
    "callback_registrar": 0x18008F4A,
    "get_handler": 0x1800FFAA,
    "set_handler": 0x18010102,
    "frame_write": 0x1800C132,
    "frame_consumer_a": 0x1800ABA4,
    "frame_consumer_b": 0x1800AAB0,
}


def to_dict():
    matches = measured_matches()
    reports = descriptor_reports("installed")
    return {
        "claims": [
            {"confidence": item.confidence, "key": item.key,
             "kind_basis": item.kind_basis, "statement": item.statement,
             "verified_against": item.verified_against}
            for item in CLAIMS],
        "classification": {
            "verdict": "implemented",
            "detail": "RGB is IMPLEMENTED in the recovered firmware: all six "
                      "LampArray reports are handled, lamps are addressed by "
                      "LampId through a coordinate table, and a 306-byte "
                      "frame buffer is written with intensity-scaled RGB. "
                      "What is NOT recovered is the final hardware "
                      "interface, so a replacement cannot yet drive the LEDs "
                      "even though it can reproduce the protocol.",
        },
        "frame_buffer": {
            "address": FRAME_BUFFER,
            "bytes_per_cell": FRAME_BYTES_PER_CELL,
            "cells": FRAME_ROWS * FRAME_COLUMNS,
            "channel_order": list(FRAME_ORDER),
            "channel_width_bits": 8,
            "columns": FRAME_COLUMNS,
            "intensity_shift": INTENSITY_SHIFT,
            "rows": FRAME_ROWS,
            "size": FRAME_ROWS * FRAME_COLUMNS * FRAME_BYTES_PER_CELL,
            "vendor_address": FRAME_BUFFER - RELOCATION_DELTA,
        },
        "hardware_boundary": {
            "identified": False,
            "note": "UNRESOLVED. The frame consumers reach no resolved MMIO: "
                    "79 and 91 unresolved-base accesses and zero resolved. "
                    "SPI, PWM, GPIO and DMA are all still open, and the "
                    "0x40022000 bank is NOT named on the strength of a "
                    "plausible per-channel shape.",
        },
        "lamp_counts": lamp_counts(),
        "reports": {str(rid): value for rid, value in sorted(reports.items())},
        "route": {
            name: {"installed": address,
                   "vendor": matches.get(address, (None, None))[0],
                   "vendor_match": matches.get(address, (None, None))[1]}
            for name, address in sorted(ROUTE_FUNCTIONS.items())},
        "safe_omission": {
            "buffer_idle_state_provable": True,
            "hardware_idle_state_provable": False,
            "note": "The BUFFER's idle state is provable: it lives at "
                    f"0x{FRAME_BUFFER:08x}, inside the zeroinit region Phase 3 "
                    "recovered, so it powers up all-zero and only "
                    "FUN_1800c132 ever writes it. A firmware that omits RGB "
                    "and never calls that function leaves an all-zero frame. "
                    "Whether all-zero means LEDS OFF is NOT provable here, "
                    "because the driver that consumes the frame is "
                    "unidentified and its polarity is unknown. No shared "
                    "clock, pin or controller initialisation could be "
                    "identified either, for the same reason.",
        },
    }


def verify():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    payload = to_dict()
    reports = descriptor_reports("installed")
    check("the descriptor declares six reports, all Feature",
          sorted(reports) == [1, 2, 3, 4, 5, 6]
          and all(value["kinds"] == ["Feature"] for value in reports.values()),
          ", ".join(f"ID {rid}: {value['kinds']}"
                    for rid, value in sorted(reports.items())))
    check("report ID 1's wire size is the 23 bytes the GET handler returns",
          reports[1]["wire_bytes"] == 0x17,
          f"{reports[1]['payload_bytes']} payload + 1 = "
          f"{reports[1]['wire_bytes']}")
    check("report ID 4 carries eight lamps",
          any(field["count"] == 8 and field["size"] == 16
              for field in reports[4]["fields"])
          and any(field["count"] == 32 and field["size"] == 8
                  for field in reports[4]["fields"]),
          "eight 16-bit LampIds and 32 = 8 x 4 channel bytes")
    check("every report the descriptor declares is handled by the firmware",
          all(HANDLED.get(rid) for rid in reports),
          ", ".join(f"{rid}:{HANDLED[rid]}" for rid in sorted(reports)))
    check("the frame is 6 x 17 x 3 = 306 bytes",
          payload["frame_buffer"]["size"] == 306)
    check("every lamp count fits the frame",
          all(count <= payload["frame_buffer"]["cells"]
              for count in payload["lamp_counts"]),
          f"counts {payload['lamp_counts']} against "
          f"{payload['frame_buffer']['cells']} cells")
    check("the hardware boundary is NOT identified",
          payload["hardware_boundary"]["identified"] is False)
    check("the buffer idle state is provable but the hardware's is not",
          payload["safe_omission"]["buffer_idle_state_provable"] is True
          and payload["safe_omission"]["hardware_idle_state_provable"]
          is False)
    check("every claim carries a confidence from the closed set",
          all(item.confidence in CONFIDENCES for item in CLAIMS))
    check("every claim says what it was verified against",
          all(item.verified_against in SOURCES for item in CLAIMS))
    check("the load-bearing frame claims are listing-verified",
          all(item.verified_against == "listing" for item in CLAIMS
              if item.key in ("frame_geometry", "frame_order", "intensity",
                              "out_of_range_dropped")))
    check("spec-derived names are separated from measured sizes",
          all(field["usages"][0]["spec_name"] is not None
              for value in reports.values() for field in value["fields"]
              if field["usages"]),
          "names come from the page 0x59 specification; every size in this "
          "model is measured from the descriptor")
    check("every route function has a measured vendor counterpart",
          all(item["vendor"] is not None
              for item in payload["route"].values()),
          "counterparts are looked up in Phase 3's match table, never "
          "computed")
    check("the arithmetic model reproduces the recovered scaling",
          apply_intensity(0xFF, 0xFF) == 0xFE
          and apply_intensity(0xFF, 0x80) == 0x7F
          and apply_intensity(0x00, 0xFF) == 0,
          "(255*255)>>8 = 254, (255*128)>>8 = 127")
    return checks


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM map_rgb_lamparray",
        "PURPOSE Phase 5F — RGB / LampArray routing",
        "",
        f"CLASSIFICATION: {payload['classification']['verdict'].upper()}",
        "  " + payload["classification"]["detail"],
        "",
        "REPORTS (sizes measured from the descriptor; names are spec-derived)",
    ]
    for rid, value in sorted(payload["reports"].items()):
        out.append(f"  ID {rid} {value['spec_name']:32s} "
                   f"{value['payload_bytes']:3d}+1 bytes  "
                   f"{','.join(value['kinds'])}  "
                   f"firmware handles: {value['firmware_handles']}")
    out += ["", "ROUTE"]
    for name, item in sorted(payload["route"].items()):
        out.append(f"  {name:20s} installed 0x{item['installed']:08x}  "
                   f"vendor 0x{item['vendor']:08x} ({item['vendor_match']})")
    frame = payload["frame_buffer"]
    out += [
        "",
        "FRAME BUFFER",
        f"  0x{frame['address']:08x}  {frame['rows']} rows x "
        f"{frame['columns']} columns x {frame['bytes_per_cell']} bytes = "
        f"{frame['size']} bytes ({frame['cells']} cells)",
        f"  channel order {', '.join(frame['channel_order'])}, "
        f"{frame['channel_width_bits']} bits each",
        f"  intensity applied as (channel * intensity) >> "
        f"{frame['intensity_shift']}",
        f"  lamp counts in the entry-image table: {payload['lamp_counts']}",
        "",
        "HARDWARE BOUNDARY",
        "  " + payload["hardware_boundary"]["note"],
        "",
        "SAFE OMISSION",
        "  " + payload["safe_omission"]["note"],
        "",
        "CLAIMS",
    ]
    for item in CLAIMS:
        out.append(f"  [{item.confidence}] ({item.verified_against}) "
                   f"{item.key}: {item.statement}")
    out += ["", "CHECKS"]
    for item in verify():
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in verify())
    out += [
        "",
        f"RESULT rgb_ok={ok} checks={len(verify())}",
        "LIMITATION The report SEMANTICS are fixed by the HID page 0x59 "
        "specification, not observed on this device. Every SIZE here is "
        "measured from the descriptor; the NAMES are spec-derived.",
        "LIMITATION The final hardware interface is not identified, so this "
        "model can reproduce the protocol but cannot drive an LED.",
    ]
    return out


def markdown():
    payload = to_dict()
    frame = payload["frame_buffer"]
    lines = [
        "# RGB / LampArray route (Phase 5F)",
        "",
        "Generated by `tool/map_rgb_lamparray.py`. Do not edit by hand.",
        "",
        f"**Classification: {payload['classification']['verdict']}.** "
        + payload["classification"]["detail"],
        "",
        "## Reports",
        "",
        "Sizes are measured from the descriptor's own items. Names are "
        "spec-derived from HID usage page `0x59`.",
        "",
        "| ID | spec name | payload+ID | kind | firmware |",
        "|---|---|---|---|---|",
    ]
    for rid, value in sorted(payload["reports"].items()):
        lines.append(f"| {rid} | {value['spec_name']} | "
                     f"{value['payload_bytes']}+1 | "
                     f"{','.join(value['kinds'])} | "
                     f"{value['firmware_handles']} |")
    lines += ["", "## Route", "",
              "| stage | installed | vendor | match |", "|---|---|---|---|"]
    for name, item in sorted(payload["route"].items()):
        lines.append(f"| {name} | `0x{item['installed']:08x}` | "
                     f"`0x{item['vendor']:08x}` | {item['vendor_match']} |")
    lines += [
        "", "## Frame buffer", "",
        f"- `0x{frame['address']:08x}`, **{frame['rows']} x "
        f"{frame['columns']} x {frame['bytes_per_cell']} = {frame['size']} "
        f"bytes**",
        f"- channel order **{', '.join(frame['channel_order'])}**, "
        f"{frame['channel_width_bits']} bits each",
        f"- intensity: `(channel * intensity) >> {frame['intensity_shift']}`",
        f"- lamp counts available: `{payload['lamp_counts']}`",
        "", "## Hardware boundary", "",
        payload["hardware_boundary"]["note"],
        "", "## Safe omission", "",
        payload["safe_omission"]["note"],
        "", "## Claims", "",
        "| claim | confidence | verified against |", "|---|---|---|",
    ]
    for item in CLAIMS:
        lines.append(f"| {item.statement} | {item.confidence} | "
                     f"{item.verified_against} |")
    lines += ["", "## Checks", ""]
    for item in verify():
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def bodies():
    return {"rgb-lamparray.json": json.dumps(to_dict(), indent=2,
                                             sort_keys=True) + "\n",
            "rgb-lamparray.md": markdown()}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = bodies()
    except (OSError, RgbError, ur.RoutingError, json.JSONDecodeError) as exc:
        print(f"RESULT rgb_ok=False error={exc}")
        return 1
    if args.check:
        stale = [name for name, body in payload.items()
                 if not (NOTES / name).exists()
                 or (NOTES / name).read_text() != body]
        print(f"RESULT reports_current={not stale} stale={len(stale)}"
              + ("" if not stale else " " + ", ".join(stale)))
        return 0 if not stale else 1
    if args.write:
        for name, body in payload.items():
            path = NOTES / name
            if not path.exists() or path.read_text() != body:
                path.write_text(body)
                print(f"WROTE notes/{name}")
        return 0
    if args.json:
        print(payload["rgb-lamparray.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
