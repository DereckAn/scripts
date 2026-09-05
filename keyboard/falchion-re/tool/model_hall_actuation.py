#!/usr/bin/env python3
"""Phase 5D: Hall-effect actuation behaviour, recovered offline.

Read-only. Phase 5C traced the scan cadence to the report buffers and stopped at
a per-key array with no recovered producer. This module carries that one stage
further: the ACTUATION COMPARISON is recovered as executable arithmetic, and the
ACQUISITION that produces its input is still not.

WHAT IS RECOVERED — the decision that turns a per-key travel byte into a key-down
bit, from FUN_18004a7e (installed 0x18004a7e), confirmed against the LISTING and
not only the decompiler:

    180057a8  ldrb r3,[r3,r2]        ; key_id = keymap[...]
    180057aa  cbz  r3,0x180057d0     ; key id 0 -> skip
    180057ac  cmp  r3,#0xd3
    180057ae  beq  0x180057d0        ; key id 0xd3 -> skip
    180057b2  ldrb r3,[r3,r4]        ; travel = travel_bytes[linear]
    180057b4  cmp  r3,#0x64          ; <-- the threshold is 100
    180057b6  bcc  0x180057c2        ; below -> the clear/hold branch
    180057ba  ldr.w r3,[r6,r0,lsl #0x2]
    180057be  orrs r3,r1             ; at or above -> SET the key's bit

`ACTUATE_AT` is therefore 100, and the band 1..99 leaves the previous bit
UNCHANGED — a hold band, recovered from control flow rather than from a feature
name. Only an exact 0 clears the bit.

THE GEOMETRY IS IN THE INSTRUCTION ENCODING, which is why it is trustworthy:

    18005798  rsb r3,r3,r3, lsl #0x4     ; x * 15
    1800579c  add.w r3,r3,r3, lsl #0x2   ; (x * 15) * 5  == x * 75 == x * 0x4b
    180057a2  rsb r6,r0,r0, lsl #0x4     ; outer * 15

so the key map is dimensioned 5 groups x 15 = 75 entries per layer, and the
outer loop bound is the literal 5 (`cmp r5,#0x5` at 0x18004bae). The INNER
bound is a runtime word at region+0x55c, which the region's initialised image
leaves zero — so 15 is the table stride, not a proven active count.

WHAT IS NOT RECOVERED. Nothing writes the travel bytes from a hardware register.
The buffer's address appears in no aligned word of any image; it is reached only
by dereferencing the pointer cell at 0x1801ed6c, which something fills at
runtime. No MMIO block in either image has an ADC shape: every access in the
0x40000000 block is 32 bits wide, and no repeated halfword read from a data
register exists anywhere. Calibration, filtering and any raw-to-travel
conversion are therefore NOT recovered — the bytes this module consumes are
already on a 0..100-ish scale by the time any traced code sees them.

RAW NUMERIC BEHAVIOUR IS KEPT SEPARATE FROM PHYSICAL INTERPRETATION. This module
recovers formulas and constants. It says nothing about sensor polarity, voltage
limits, noise margin, physical travel distance, or a safe scan rate, none of
which static analysis can establish. Completing it authorises NO custom-firmware
Hall drive and NO live experiment.

No device access. Examples:
    python3 tool/model_hall_actuation.py
    python3 tool/model_hall_actuation.py --json
    python3 tool/model_hall_actuation.py --write
    python3 tool/model_hall_actuation.py --check
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"

CONFIDENCES = ("observed", "strongly-inferred", "hypothesis", "unresolved")

# --- constants recovered from the listing ------------------------------------
# `cmp r3,#0x64` at 0x180057b4.
ACTUATE_AT = 100
# `cbz r3` and `cmp r3,#0xd3` at 0x180057aa / 0x180057ac: two key ids are skipped.
SKIP_KEY_IDS = (0x00, 0xD3)
# `cmp r5,#0x5` at 0x18004bae; the loop runs while the index is below it.
OUTER_GROUPS = 5
# `mov.w r12,#0xf` at 0x18004c12 and the `rsb ..., lsl #4` multiplies.
GROUP_STRIDE = 15
# `rsb`+`add` shift pair: x*15 then *5. Also spelled `adds r1,#0x4b` at 0x18004bd0.
LAYER_STRIDE = OUTER_GROUPS * GROUP_STRIDE          # 75 == 0x4b
# `and r0,r0,#0x7f` at 0x18004b34: the per-key actuation field is 7 bits.
ACTUATION_FIELD_MASK = 0x7F
# `cmp r0,#0x5` at 0x18004b38 and the branches after it.
ACTUATION_CLAMP_HIGH = 5
ACTUATION_CLAMP_LOW = 2
ACTUATION_CLAMP_MAX = 3
# `FUN_1800d640(key_id, travel / 5)` in the non-comparison branch.
TRAVEL_REPORT_DIVISOR = 5
# The vendor-HID command stores its actuation value divided by 10 (FINDINGS).
VENDOR_ACTUATION_DIVISOR = 10

# --- addresses ---------------------------------------------------------------
# Phase 3 measured this shift; log 98 located the insertion that causes it.
RELOCATION_DELTA = 0x2C
INSERTION_POINT = 0x180047FC

ADDRESSES = {
    "comparison_function": (0x18004A7E, "app"),
    "edge_detector": (0x18005A88, "app"),
    "travel_pointer_cell": (0x1801ED6C, "region"),
    "travel_bytes_offset": (0x35C, "offset"),
    "key_state_bitmap": (0x18023410, "ram"),
    "key_state_previous": (0x18023C0C, "ram"),
    "key_map_table": (0x1801C940, "flash"),
    "per_key_config_bank": (0x180202D8, "ram"),
    "global_actuation_table": (0x18024F0C, "ram"),
}
PER_KEY_RECORD_STRIDE = 0x20
PROFILE_BANK_STRIDE = 0xD84
ACTUATION_FIELD_OFFSET = 8


class ModelError(ValueError):
    """The evidence does not support the structure being asked of it."""


@dataclass(frozen=True)
class Finding:
    key: str
    statement: str
    confidence: str
    kind_basis: str
    verified_against: str      # "listing", "decompiler", "bytes", "xref"


FINDINGS = (
    Finding("threshold",
            f"a travel byte at or above {ACTUATE_AT} sets the key's bit",
            "observed",
            "`cmp r3,#0x64` then `bcc` at 0x180057b4/0x180057b6, with `orrs "
            "r3,r1` on the fall-through at 0x180057be",
            "listing"),
    Finding("hold_band",
            f"a travel byte in 1..{ACTUATE_AT - 1} leaves the bit UNCHANGED",
            "observed",
            "the sub-100 branch tests for zero first and jumps to the loop "
            "tail when the value is non-zero, so neither the set nor the "
            "clear store executes",
            "listing"),
    Finding("release",
            "only an exact 0 clears the key's bit",
            "observed",
            "the clear store is reached only after the non-zero test fails",
            "decompiler"),
    Finding("skipped_ids",
            f"key ids {SKIP_KEY_IDS[0]:#x} and {SKIP_KEY_IDS[1]:#x} are "
            "skipped before any comparison",
            "observed",
            "`cbz r3,0x180057d0` and `cmp r3,#0xd3` / `beq 0x180057d0` at "
            "0x180057aa and 0x180057ac",
            "listing"),
    Finding("geometry",
            f"the key map is {OUTER_GROUPS} groups x {GROUP_STRIDE} = "
            f"{LAYER_STRIDE} entries per layer",
            "observed",
            "`rsb r3,r3,r3,lsl #4` then `add.w r3,r3,r3,lsl #2` is x*15 then "
            "*5; the same stride appears as `adds r1,#0x4b` at 0x18004bd0 and "
            "`mov.w r12,#0xf` at 0x18004c12; the outer bound is `cmp r5,#0x5`",
            "listing"),
    Finding("active_count",
            "the ACTIVE inner count is a runtime word at region+0x55c, not a "
            "static constant",
            "observed",
            "the loop compares against `*(0x1801e8dc)`, and the region's "
            "initialised image has those four bytes zero",
            "bytes"),
    Finding("actuation_field",
            f"the per-key actuation setting is {ACTUATION_FIELD_MASK.bit_count()}"
            " bits at +8 of a 0x20-byte per-key record, with bit 15 selecting "
            "per-key over the global default",
            "strongly-inferred",
            "`and r0,r0,#0x7f` at 0x18004b34 follows a signed test of the "
            "halfword's top bit; the record address is "
            "0x180202d8 + profile*0xd84 + index*0x20",
            "decompiler"),
    Finding("actuation_clamp",
            "the setting is clamped: below 2 -> 0, 2..4 -> value-2, 5 or more "
            "-> 3",
            "observed",
            "`cmp r0,#0x5` at 0x18004b38 and the two-level branch after it",
            "listing"),
    Finding("travel_report",
            f"a second branch reports travel/{TRAVEL_REPORT_DIVISOR} with the "
            "key id rather than a binary state",
            "strongly-inferred",
            "`FUN_1800d640(key_id, travel / 5)` guarded by a mode word; the "
            "`udiv` is at 0x18004af6",
            "decompiler"),
    Finding("cadence",
            "the comparison runs on the every-eighth-tick branch of IRQ38's "
            "prescaler",
            "strongly-inferred",
            "log 109 traced FUN_18004a7e to the entry image's tick job at "
            "0x4062, inside the branch gated by that job's own /8 counter",
            "xref"),
    Finding("acquisition",
            "the producer of the travel bytes is NOT RECOVERED",
            "unresolved",
            "the buffer address 0x180344f4 appears in no aligned word of any "
            "image and in no register; it is reached only by dereferencing "
            "the pointer cell at 0x1801ed6c, and no traced function writes "
            "the bytes from a hardware register",
            "xref"),
    Finding("no_adc_block",
            "no MMIO block in either image has an ADC shape",
            "observed",
            "every access in the 0x40000000 block is 32 bits wide across all "
            "four sub-blocks, and no repeated halfword read from a fixed data "
            "register exists in either census",
            "xref"),
    Finding("no_calibration",
            "no calibration table, baseline/min/max array or filter is "
            "recovered",
            "unresolved",
            "the bytes the comparison consumes are already on a 0..100-ish "
            "scale; whatever produces that scale is outside the traced chain",
            "decompiler"),
    Finding("no_physical_units",
            "no raw-to-travel conversion, sensor polarity, voltage bound, "
            "noise margin or physical distance is claimed",
            "unresolved",
            "static analysis cannot establish any of them, and nothing in the "
            "recovered arithmetic carries a unit",
            "decompiler"),
)


MATCH_APP = NOTES / "vendor-to-installed-functions-app-b.json"


def measured_matches():
    """{installed entry: (vendor entry, confidence)} from Phase 3's output.

    A FUNCTION's counterpart is LOOKED UP, never computed. An earlier draft of
    this module derived it from "above the insertion point, subtract 0x2c" and
    that rule is WRONG: FUN_18004a7e sits above the insertion and does not
    move. The rule was an assumption; the match table is a measurement, so the
    measurement is used and the assumption is gone.
    """
    payload = json.loads(MATCH_APP.read_text())
    out = {}
    for match in payload.get("matches", ()):
        installed, vendor = match.get("installed"), match.get("vendor")
        if installed and vendor:
            out[installed["entry"]] = (vendor["entry"], match["confidence"])
    return out


def vendor_address(address, image):
    """The same address in the vendor release.

    Data addresses shift with their region, which Phase 3 measured as a flat
    0x2c. Function addresses are looked up in the match table instead.
    """
    if image == "offset":
        return address
    if image in ("region", "ram", "flash"):
        return address - RELOCATION_DELTA
    if image == "app":
        found = measured_matches().get(address)
        if found is None:
            raise ModelError(
                f"0x{address:08x} has no measured vendor counterpart; "
                "refusing to compute one from a relocation rule")
        return found[0]
    raise ModelError(f"no relocation rule for image {image!r}")


def key_index(group, position):
    """The linear key-map index, exactly as the shift-multiplies compute it."""
    if not 0 <= group < OUTER_GROUPS:
        raise ModelError(f"group {group} outside 0..{OUTER_GROUPS - 1}")
    if not 0 <= position < GROUP_STRIDE:
        raise ModelError(f"position {position} outside 0..{GROUP_STRIDE - 1}")
    return group * GROUP_STRIDE + position


def layer_offset(layer):
    """`x*15` then `*5`, the way the instructions spell it."""
    return (layer * GROUP_STRIDE) * OUTER_GROUPS


def clamp_actuation(raw):
    """The 0x7f field's clamp, from `cmp r0,#0x5` and its branches."""
    value = raw & ACTUATION_FIELD_MASK
    if value >= ACTUATION_CLAMP_HIGH:
        return ACTUATION_CLAMP_MAX
    if value < ACTUATION_CLAMP_LOW:
        return 0
    return value - ACTUATION_CLAMP_LOW


def actuate(travel, previous_down):
    """The recovered decision. Returns the new key-down state.

    travel >= 100      -> down
    travel == 0        -> up
    1 <= travel <= 99  -> UNCHANGED. This is the hold band, and it is why a
                          key does not chatter across the threshold.
    """
    if travel >= ACTUATE_AT:
        return True
    if travel == 0:
        return False
    return previous_down


def scan_pass(travel_bytes, key_map, previous_bits, active_positions,
              layer=0):
    """One comparison pass over the key map, as FUN_18004a7e performs it.

    `previous_bits` and the return value are a list of OUTER_GROUPS integers,
    each a bitmap over that group's positions — the same shape as the firmware's
    word array. `active_positions` is the runtime inner bound; the firmware
    reads it from region+0x55c and this model requires it rather than assuming
    GROUP_STRIDE, because the image does not fix it.
    """
    if len(previous_bits) != OUTER_GROUPS:
        raise ModelError(
            f"previous_bits must have {OUTER_GROUPS} words, got "
            f"{len(previous_bits)}")
    if not 0 <= active_positions <= GROUP_STRIDE:
        raise ModelError(
            f"active_positions {active_positions} outside 0..{GROUP_STRIDE}")
    bits = list(previous_bits)
    linear = 0
    for group in range(OUTER_GROUPS):
        for position in range(active_positions):
            index = layer_offset(layer) + key_index(group, position)
            if index >= len(key_map):
                raise ModelError(
                    f"key map index {index} past its {len(key_map)} entries")
            key_id = key_map[index]
            if key_id in SKIP_KEY_IDS:
                linear += 1
                continue
            if linear >= len(travel_bytes):
                raise ModelError(
                    f"travel index {linear} past its {len(travel_bytes)} bytes")
            mask = 1 << position
            down = actuate(travel_bytes[linear], bool(bits[group] & mask))
            bits[group] = (bits[group] | mask) if down else (
                bits[group] & ~mask)
            linear += 1
    return bits


def edge_words(current_bits, previous_bits):
    """The edge detector's XOR, from FUN_18005a88's `previous ^ current`."""
    if len(current_bits) != len(previous_bits):
        raise ModelError("bitmap lengths differ")
    return [a ^ b for a, b in zip(current_bits, previous_bits)]


def to_dict():
    return {
        "addresses": {
            name: {"image": image, "installed": address,
                   "vendor": vendor_address(address, image)}
            for name, (address, image) in sorted(ADDRESSES.items())},
        "authorisation": "This offline analysis authorises NO custom-firmware "
                         "Hall drive and NO live experiment.",
        "constants": {
            "actuate_at": ACTUATE_AT,
            "actuation_clamp": {"high": ACTUATION_CLAMP_HIGH,
                                "low": ACTUATION_CLAMP_LOW,
                                "max": ACTUATION_CLAMP_MAX},
            "actuation_field_mask": ACTUATION_FIELD_MASK,
            "group_stride": GROUP_STRIDE,
            "layer_stride": LAYER_STRIDE,
            "outer_groups": OUTER_GROUPS,
            "per_key_record_stride": PER_KEY_RECORD_STRIDE,
            "profile_bank_stride": PROFILE_BANK_STRIDE,
            "skip_key_ids": list(SKIP_KEY_IDS),
            "travel_report_divisor": TRAVEL_REPORT_DIVISOR,
            "vendor_actuation_divisor": VENDOR_ACTUATION_DIVISOR,
        },
        "findings": [
            {"confidence": item.confidence, "key": item.key,
             "kind_basis": item.kind_basis, "statement": item.statement,
             "verified_against": item.verified_against}
            for item in FINDINGS],
        "physical_interpretation": {
            "note": "NOT ESTABLISHED and not establishable from static code: "
                    "sensor polarity, voltage limits, noise margin, physical "
                    "travel distance, and any safe scan rate. The recovered "
                    "numbers carry no unit.",
            "recovered": None,
        },
        "pipeline": {
            "acquisition": "unresolved",
            "calibration": "unresolved",
            "filtering": "unresolved",
            "position_travel": "unresolved — the bytes are already scaled",
            "comparison": "observed",
            "per_key_state": "observed",
            "hid": "observed (log 109)",
        },
        "relocation": {"delta": RELOCATION_DELTA,
                       "insertion_point": INSERTION_POINT},
    }


def verify():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("the layer stride is the product of the two recovered strides",
          LAYER_STRIDE == OUTER_GROUPS * GROUP_STRIDE == 0x4B,
          f"{OUTER_GROUPS} x {GROUP_STRIDE} = {LAYER_STRIDE} = 0x4b")
    check("every finding carries a confidence from the closed set",
          all(item.confidence in CONFIDENCES for item in FINDINGS))
    check("every finding says what it was verified against",
          all(item.verified_against in
              ("listing", "decompiler", "bytes", "xref") for item in FINDINGS))
    check("the threshold and geometry claims are listing-verified",
          all(item.verified_against == "listing"
              for item in FINDINGS
              if item.key in ("threshold", "hold_band", "skipped_ids",
                              "geometry", "actuation_clamp")))
    check("acquisition, calibration and physical units stay unresolved",
          all(next(item for item in FINDINGS if item.key == key).confidence
              == "unresolved"
              for key in ("acquisition", "no_calibration",
                          "no_physical_units")))
    check("no physical interpretation is recorded",
          to_dict()["physical_interpretation"]["recovered"] is None)
    check("the model authorises no hardware action",
          "authorises NO custom-firmware Hall drive"
          in to_dict()["authorisation"])

    # The arithmetic itself, exercised here so the emitted model is checked and
    # not merely described.
    check("a travel byte at the threshold actuates",
          actuate(ACTUATE_AT, False) is True)
    check("a travel byte one below the threshold does NOT actuate a released "
          "key",
          actuate(ACTUATE_AT - 1, False) is False)
    check("the hold band keeps a pressed key pressed",
          actuate(ACTUATE_AT - 1, True) is True)
    check("only zero releases",
          actuate(0, True) is False and actuate(1, True) is True)
    check("the actuation clamp matches the recovered branches",
          [clamp_actuation(value) for value in range(8)]
          == [0, 0, 0, 1, 2, 3, 3, 3],
          str([clamp_actuation(value) for value in range(8)]))
    matches = measured_matches()
    check("every application address is looked up, not computed",
          all(address in matches for address, image in ADDRESSES.values()
              if image == "app"),
          "the comparison function and the edge detector both have measured "
          "counterparts")
    check("the two application functions relocate differently, which is why "
          "a rule would be wrong",
          matches[0x18004A7E][0] == 0x18004A7E
          and matches[0x18005A88][0] == 0x18005A88 - RELOCATION_DELTA,
          f"0x18004a7e -> 0x{matches[0x18004A7E][0]:08x} (delta 0) but "
          f"0x18005a88 -> 0x{matches[0x18005A88][0]:08x} (delta 0x2c), and "
          "both sit above the insertion point")
    check("the comparison function's cross-release match is only TENTATIVE, "
          "and that is recorded rather than smoothed over",
          matches[0x18004A7E][1] == "tentative",
          f"FUN_18004a7e match confidence = {matches[0x18004A7E][1]}")
    return checks


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM model_hall_actuation",
        "PURPOSE Phase 5D — Hall-effect actuation behaviour",
        "",
        "PIPELINE STATUS",
    ]
    for stage, status in payload["pipeline"].items():
        out.append(f"  {stage:18s} {status}")
    out += ["", "RECOVERED CONSTANTS"]
    for name, value in sorted(payload["constants"].items()):
        out.append(f"  {name:26s} {value}")
    out += ["", "THE DECISION, as recovered:",
            "  travel >= 100        -> key down",
            "  travel == 0          -> key up",
            "  1 <= travel <= 99    -> UNCHANGED (hold band)",
            "  key id 0x00 or 0xd3  -> skipped before any comparison",
            "", "FINDINGS"]
    for item in FINDINGS:
        out.append(f"  [{item.confidence}] ({item.verified_against}) "
                   f"{item.key}: {item.statement}")
        out.append(f"      {item.kind_basis}")
    out += ["", "CHECKS"]
    for item in verify():
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in verify())
    out += [
        "",
        f"RESULT model_ok={ok} checks={len(verify())}",
        "LIMITATION " + payload["physical_interpretation"]["note"],
        "AUTHORISATION " + payload["authorisation"],
    ]
    return out


def markdown():
    payload = to_dict()
    lines = [
        "# Hall-effect actuation model (Phase 5D)",
        "",
        "Generated by `tool/model_hall_actuation.py`. Do not edit by hand.",
        "",
        "## The decision",
        "",
        "```",
        "travel >= 100        -> key down",
        "travel == 0          -> key up",
        "1 <= travel <= 99    -> UNCHANGED (hold band)",
        "key id 0x00 or 0xd3  -> skipped before any comparison",
        "```",
        "",
        "## Pipeline status",
        "",
        "| stage | status |",
        "|---|---|",
    ]
    for stage, status in payload["pipeline"].items():
        lines.append(f"| {stage} | {status} |")
    lines += ["", "## Findings", "",
              "| finding | confidence | verified against |", "|---|---|---|"]
    for item in FINDINGS:
        lines.append(f"| {item.statement} | {item.confidence} | "
                     f"{item.verified_against} |")
    lines += ["", "## Constants", "", "| name | value |", "|---|---|"]
    for name, value in sorted(payload["constants"].items()):
        lines.append(f"| `{name}` | `{value}` |")
    lines += ["", "## Physical interpretation", "",
              payload["physical_interpretation"]["note"], "",
              f"**{payload['authorisation']}**", "", "## Checks", ""]
    for item in verify():
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def bodies():
    return {"hall-actuation.json": json.dumps(to_dict(), indent=2,
                                              sort_keys=True) + "\n",
            "hall-actuation.md": markdown()}


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
    except (OSError, ModelError) as exc:
        print(f"RESULT model_ok=False error={exc}")
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
        print(payload["hall-actuation.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
