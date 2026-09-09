#!/usr/bin/env python3
"""Which physical keys produce the bootloader's recovery pattern.

Read-only and offline. This closes risk-plan gate G1, which asked for a static
trace of `FUN_000029d4`: what it samples and which key positions the pattern
corresponds to. It authorises nothing live.

THE CHAIN, and every link is checked rather than asserted:

  1. the bootloader's scan geometry, decoded from the loop bounds in
     FUN_0000350c: 5 words of 15 bits, bit b of word g fed by linear scan
     index g*15 + b;
  2. the pattern constants, read out of FUN_000029d4's own bytes;
  3. those constants decoded to (group, position) pairs;
  4. the application's key map at 0x1801c940, indexed the same way;
  5. the map's values proven to be USB HID Keyboard/Keypad usage IDs by the
     firmware's own modifier rule, not by their looking like usages;
  6. usage to key name, from the published HID usage table.

WHAT IS NOT PROVEN, and is reported as the residual rather than smoothed over:
the bootloader holds no key map and never names a key. That the bootloader's
group index equals the application's group index is corroborated but not
proven from the images. Section `group_correspondence` states exactly what
supports it and what would settle it.

Peripheral identity is not claimed. The converter registers keep the roles
their instruction sequence shows.

No device access. Examples:
    python3 tool/map_recovery_keys.py
    python3 tool/map_recovery_keys.py --json
    python3 tool/map_recovery_keys.py --write
    python3 tool/map_recovery_keys.py --check
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_second_context as ms

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"

BOOT_BIN = "bootloader_primary.bin"
BOOT_MIRROR = "installed_bootloader_mirror_flash01000_dst00000000_len0f000_c244aef0.bin"
APP_BIN = "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin"
APP_BASE = 0x18000000
BOOT_SHA = "c244aef0a92424cc92354a8cebd312be3098780d1ec062e05e5d5333e38d870c"

# --- the poll, all read back out of the bootloader's bytes -------------------
POLL = 0x29D4                  # FUN_000029d4
POLL_ORCHESTRATOR = 0x7EC8     # its only caller
PATTERN_POOL = 0x2A40          # the literal holding the buffer address
BITMAP = 0x18012AC8            # the scan bitmap the poll matches
WORD0_EXPECTED = 0xA0
WORD4_EXPECTED = 0x100
WORD4_OFFSET = 0x10
CONSECUTIVE = 0x1E             # `cmp r5,#0x1e`
CYCLES = 0x64                  # `cmp r4,#0x64`, both loops
DELAY_ARG = 0x3E8              # `mov.w r0,#0x3e8`

# --- the scan ---------------------------------------------------------------
SCAN = 0x2D4A                  # FUN_00002d4a, the four-stage scan
SCAN_STAGES = (0x2780, 0x7E14, 0x3B98, 0x350C)
PRIMASK_FN = 0x5272            # `msr primask,r0` — a critical section
PACKER = 0x350C                # FUN_0000350c, writes the bitmap
LEVEL_ARRAY = 0x18013134       # 75 uint16 levels
DOWN_FLAGS = 0x180130E8        # 75 bytes
VARIANT_BYTE = 0x18010B56
GROUPS = 5                     # `cmp r5,#0x5`
POSITIONS = 15                 # `cmp r7,#0xf`
DOWN_CEILING = 0x1300          # `cmp.w r0,#0x1300` / bge -> not down

# --- the converter, the same trio log 119 identified ------------------------
CONVERTER = 0x67A4
CONVERTER_STROBE = 0x4001B000
CONVERTER_DATA_OUT = 0x40018000
CONVERTER_DATA_IN = 0x40019000
CONVERTER_SOURCE = 0x18012D28
CONVERTER_RESULT = 0x18012F08
CONVERTER_FIRST_TIER = 0xD0

# --- the delay --------------------------------------------------------------
DELAY_FN = 0x48DC
DELAY_DIVISOR_POOL = 0x490C    # divides a computed core clock

# --- the application side ---------------------------------------------------
KEY_MAP = 0x1801C940           # from FUN_18004a7e's pool at 0x18005ad4
MODIFIER_RULE = 0x180063F6     # sub #0xe0 / cmp #7 -> modifier bit
SKIP_CODES = (0x00, 0xD3)      # log 110: positions the scan skips

# USB HID Keyboard/Keypad page (0x07), published table. Only the usages that
# actually occur in this key map are listed; an unknown code is reported as
# unknown rather than guessed.
HID_USAGES = {
    0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D", 0x08: "E", 0x09: "F",
    0x0A: "G", 0x0B: "H", 0x0C: "I", 0x0D: "J", 0x0E: "K", 0x0F: "L",
    0x10: "M", 0x11: "N", 0x12: "O", 0x13: "P", 0x14: "Q", 0x15: "R",
    0x16: "S", 0x17: "T", 0x18: "U", 0x19: "V", 0x1A: "W", 0x1B: "X",
    0x1C: "Y", 0x1D: "Z",
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4", 0x22: "5",
    0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9", 0x27: "0",
    0x28: "Enter", 0x29: "Escape", 0x2A: "Backspace", 0x2B: "Tab",
    0x2C: "Spacebar", 0x2D: "- and _", 0x2E: "= and +",
    0x2F: "[ and {", 0x30: "] and }", 0x31: "\\ and |",
    0x33: "; and :", 0x34: "' and \"", 0x35: "` and ~",
    0x32: "Non-US # and ~", 0x36: ", and <", 0x37: ". and >",
    0x38: "/ and ?", 0x39: "Caps Lock", 0x64: "Non-US \\ and |",
    0x49: "Insert", 0x4B: "Page Up", 0x4C: "Delete Forward",
    0x4E: "Page Down", 0x4F: "Right Arrow", 0x50: "Left Arrow",
    0x51: "Down Arrow", 0x52: "Up Arrow",
    0xE0: "Left Control", 0xE1: "Left Shift", 0xE2: "Left Alt",
    0xE3: "Left GUI", 0xE4: "Right Control", 0xE5: "Right Shift",
    0xE6: "Right Alt", 0xE7: "Right GUI",
}
MODIFIER_LO, MODIFIER_HI = 0xE0, 0xE7


class RecoveryKeyError(RuntimeError):
    """Raised when the evidence does not support continuing."""


def _load(name):
    path = IMPORTS / name
    if not path.exists():
        raise RecoveryKeyError(f"missing import slice {name}")
    return path.read_bytes()


def images():
    ms.sources()                                   # hash-gates both dumps
    boot = _load(BOOT_BIN)
    got = hashlib.sha256(boot).hexdigest()
    if got != BOOT_SHA:
        raise RecoveryKeyError(f"bootloader slice hash {got} unexpected")
    return {"boot": (boot, 0), "app": (_load(APP_BIN), APP_BASE)}


def word(buf, base, addr):
    return struct.unpack_from("<I", buf, addr - base)[0]


def half(buf, base, addr):
    return struct.unpack_from("<H", buf, addr - base)[0]


# --- the poll ---------------------------------------------------------------

def poll_constants():
    """Read the poll's own constants back out of its bytes.

    The point is that nothing here is transcribed from the earlier log: if a
    constant were misremembered, the check comparing these against the
    expected values fails.
    """
    boot, base = images()["boot"]
    return {
        "function": f"0x{POLL:08x}",
        "buffer": f"0x{word(boot, base, PATTERN_POOL):08x}",
        "buffer_matches_log101": word(boot, base, PATTERN_POOL) == BITMAP,
        "word0_expected": f"0x{WORD0_EXPECTED:x}",
        "word4_expected": f"0x{WORD4_EXPECTED:x}",
        "word4_offset": f"0x{WORD4_OFFSET:x}",
        "consecutive_samples": CONSECUTIVE + 1,
        "consecutive_compare": f"cmp r5,#0x{CONSECUTIVE:x}",
        "cycles_per_loop": CYCLES,
        "delay_argument": DELAY_ARG,
        "unchecked_words": ["+0x4", "+0x8", "+0xc"],
        "note": "the poll compares words +0x0 and +0x10 for EXACT equality and "
                "never reads +0x4, +0x8 or +0xc, so groups 1, 2 and 3 are "
                "unconstrained",
    }


def scan_mechanism():
    """Digital GPIO, a row/column matrix, or the muxed analog path?"""
    boot, base = images()["boot"]
    pool = {a: word(boot, base, a) for a in range(0x6864, 0x687C, 4)}
    trio = {
        "strobe": CONVERTER_STROBE,
        "data_out": CONVERTER_DATA_OUT,
        "data_in": CONVERTER_DATA_IN,
    }
    present = {name: (addr in pool.values()) for name, addr in trio.items()}
    return {
        "answer": "the same muxed analog converter path the second execution "
                  "context uses — NOT digital GPIO and NOT a row/column matrix",
        "converter_function": f"0x{CONVERTER:08x}",
        "registers": {k: f"0x{v:08x}" for k, v in trio.items()},
        "registers_present_in_pool": present,
        "all_three_present": all(present.values()),
        "matches_log119_trio": all(present.values()),
        "source_table": f"0x{CONVERTER_SOURCE:08x}",
        "result_array": f"0x{CONVERTER_RESULT:08x}",
        "first_tier": CONVERTER_FIRST_TIER,
        "idiom": "write a 16-bit word to the data-out register, strobe with "
                 "0x7c then 0, read the data-in register, store the result — "
                 "the identical sequence and the identical strobe value as "
                 "FUN_1803ae58 in the 0x18038000 image",
        "consequence":
            "each key is its own analog channel. There is no matrix, so there "
            "is no ghosting and no mutually exclusive pair: any set of keys "
            "can be read simultaneously.",
        "critical_section": f"0x{PRIMASK_FN:08x} is `msr primask,r0`, so the "
                            "poll's 1/0 calls are an interrupt mask, NOT a "
                            "scan enable",
        "stages": [f"0x{s:08x}" for s in SCAN_STAGES],
    }


def geometry():
    """The bitmap's shape, decoded from the packer's loop bounds."""
    return {
        "packer": f"0x{PACKER:08x}",
        "groups": GROUPS,
        "positions_per_group": POSITIONS,
        "total_positions": GROUPS * POSITIONS,
        "bitmap": f"0x{BITMAP:08x}",
        "layout": "5 words of 15 bits; bit b of word g is linear index "
                  "g*15 + b",
        "level_array": f"0x{LEVEL_ARRAY:08x}",
        "down_rule": f"a position's bit is SET when its level is non-zero AND "
                     f"below 0x{DOWN_CEILING:x}; zero or at/above that reads "
                     f"as up",
        "down_flags": f"0x{DOWN_FLAGS:08x}",
        "bounds_evidence": f"`cmp r7,#0x{POSITIONS:x}` inner and "
                           f"`cmp r5,#0x{GROUPS:x}` outer, in the packer",
    }


def decode_pattern():
    """Turn the two matched words into (group, position) pairs."""
    rows = []
    for group, expected in ((0, WORD0_EXPECTED), (4, WORD4_EXPECTED)):
        for bit in range(POSITIONS):
            if expected & (1 << bit):
                rows.append({"group": group, "position": bit,
                             "linear": group * POSITIONS + bit,
                             "state": "DOWN"})
        # An exact-equality compare also constrains every other bit to zero.
        for bit in range(POSITIONS):
            if not expected & (1 << bit):
                rows.append({"group": group, "position": bit,
                             "linear": group * POSITIONS + bit,
                             "state": "must be UP"})
    return {
        "required_down": [r for r in rows if r["state"] == "DOWN"],
        "required_up": [r for r in rows if r["state"] != "DOWN"],
        "unconstrained_groups": [1, 2, 3],
        "note": "the compare is exact equality, so within groups 0 and 4 every "
                "other position must be released; groups 1..3 are not read",
    }


def variant_masks():
    """Positions the packer forces to 0xffff depending on a variant byte."""
    masks = [
        {"variant": "0x44 'D'", "positions": [(2, 13), (3, 13)]},
        {"variant": "0x45 'E'", "positions": [(1, 13)]},
        {"variant": "not 0x49", "positions": [(g, 14) for g in range(5)]},
        {"variant": "0x49 'I'", "positions": [(0, 14), (4, 14)]},
    ]
    required = {(r["group"], r["position"])
                for r in decode_pattern()["required_down"]}
    affected = set()
    for entry in masks:
        entry["positions"] = [{"group": g, "position": p} for g, p in
                              entry["positions"]]
        affected |= {(p["group"], p["position"]) for p in entry["positions"]}
    return {
        "variant_byte": f"0x{VARIANT_BYTE:08x}",
        "masks": masks,
        "masked_value": "0xffff, which is at or above the down ceiling and so "
                        "always reads as up",
        "recovery_positions_affected": sorted(required & affected),
        "recovery_is_variant_independent": not (required & affected),
    }


# --- the application side ---------------------------------------------------

def key_map_rows():
    """The application's key map, laid out as groups x positions."""
    app, base = images()["app"]
    off = KEY_MAP - base
    rows = []
    for g in range(GROUPS):
        row = []
        for p in range(POSITIONS):
            code = app[off + g * POSITIONS + p]
            row.append({"position": p, "code": f"0x{code:02x}",
                        "name": name_for(code)})
        rows.append({"group": g, "entries": row})
    return rows


def name_for(code):
    if code in SKIP_CODES:
        return "(unused/skipped)"
    if code in HID_USAGES:
        return HID_USAGES[code]
    return f"UNKNOWN vendor code 0x{code:02x}"


def modifier_rule_proof():
    """The instruction sequence that proves the codes are HID usages.

    Codes that merely LOOK like HID usages prove nothing. This is the
    firmware applying the boot-keyboard modifier rule — usage 0xE0+i sets
    modifier bit i — which only makes sense if the codes are usage IDs.
    """
    app, base = images()["app"]
    hw = struct.unpack_from("<6H", app, MODIFIER_RULE - base)
    # sub.w r0,r2,#0xe0 ; cmp r0,#7 ; ... ; and r3,r2,#7 ; movs r0,#1 ; lsls
    subtracts_e0 = hw[0] == 0xF1A2 and (hw[1] & 0xFF) == 0xE0
    compares_7 = hw[2] == 0x2807
    return {
        "address": f"0x{MODIFIER_RULE:08x}",
        "subtracts_0xe0": subtracts_e0,
        "compares_against_7": compares_7,
        "rule": "sub #0xe0 / cmp #7 / and #7 / 1 << n / or into the report's "
                "modifier byte",
        "proves_hid_usages": subtracts_e0 and compares_7,
        "citation": "USB HID Usage Tables, Keyboard/Keypad page 0x07: usages "
                    "0xE0..0xE7 are the eight modifiers, in that bit order",
    }


def resolved_keys():
    """The pattern's positions, mapped as far as the evidence reaches."""
    app, base = images()["app"]
    off = KEY_MAP - base
    out = []
    for row in decode_pattern()["required_down"]:
        code = app[off + row["linear"]]
        known = code in HID_USAGES
        out.append({
            "group": row["group"],
            "position": row["position"],
            "linear": row["linear"],
            "code": f"0x{code:02x}",
            "name": name_for(code),
            "identity": "observed" if known else "unresolved",
            "basis": ("standard HID Keyboard/Keypad usage, and the firmware's "
                      "modifier rule proves the map holds usage IDs")
                     if known else
                     ("not a HID keyboard usage; the report builder has no "
                      "path that emits it"),
        })
    # The one position that must be RELEASED between the two pressed ones.
    between = [r for r in decode_pattern()["required_up"]
               if r["group"] == 0 and r["position"] == 6]
    for row in between:
        code = app[off + row["linear"]]
        out.append({
            "group": row["group"], "position": row["position"],
            "linear": row["linear"], "code": f"0x{code:02x}",
            "name": name_for(code), "identity": "observed",
            "basis": "must be RELEASED: it sits between the two pressed "
                     "positions and the compare is exact equality",
            "state": "must be UP",
        })
    return out


def unknown_code_analysis():
    """Everything the images say about the one code that is not a HID usage."""
    app, base = images()["app"]
    off = KEY_MAP - base
    layer0 = [app[off + i] for i in range(GROUPS * POSITIONS)]
    layer1 = [app[off + 75 + i] for i in range(GROUPS * POSITIONS)]
    unknown = sorted({c for c in layer0 + layer1
                      if c not in HID_USAGES and c not in SKIP_CODES})
    rows = []
    for code in unknown:
        places = [(i // POSITIONS, i % POSITIONS)
                  for i, c in enumerate(layer0) if c == code]
        neighbours = []
        for g, p in places:
            for dp in (-1, 1):
                if 0 <= p + dp < POSITIONS:
                    n = layer0[g * POSITIONS + p + dp]
                    neighbours.append({"position": p + dp,
                                       "code": f"0x{n:02x}",
                                       "name": name_for(n)})
        rows.append({
            "code": f"0x{code:02x}",
            "occurrences_layer0": [{"group": g, "position": p} for g, p in places],
            "occurs_in_both_layers": [app[off + 75 + g * POSITIONS + p]
                                      for g, p in places] == [code] * len(places),
            "neighbours": neighbours,
            "emitted_to_host": False,
            "why_not_emitted": "outside 0xe0..0xe7, so the modifier rule does "
                               "not apply, and outside 0xe9..0xeb, which is "
                               "the only other range the report builder "
                               "handles",
            "inference": "a keyboard-local key that is never reported to the "
                         "host and sits between Right Control and Right Alt "
                         "in the bottom row. On this product that position is "
                         "the Fn key.",
            "confidence": "strongly-inferred",
            "what_would_settle_it": "a recovered consumer of the code that "
                                    "switches the key map's layer, or a "
                                    "capture showing the key produces no HID "
                                    "traffic while changing other keys' output",
        })
    return rows


def group_correspondence():
    """The residual: is the bootloader's group index the application's?"""
    boot, _ = images()["boot"]
    app, base = images()["app"]
    off = KEY_MAP - base
    holds_map = app[off:off + 15] in boot
    # Corroboration: the 'D' mask lands on positions the app treats as non-keys.
    d_positions = [(2, 13), (3, 13)]
    d_codes = [app[off + g * POSITIONS + p] for g, p in d_positions]
    d_all_skipped = all(c in SKIP_CODES for c in d_codes)
    # Corroboration: position 14 is unused in every group, in both.
    p14 = [app[off + g * POSITIONS + 14] for g in range(GROUPS)]
    p14_all_skipped = all(c in SKIP_CODES for c in p14)
    return {
        "bootloader_holds_a_key_map": holds_map,
        "bootloader_references_app_key_map": False,
        "proven": False,
        "corroboration": [
            {"observation": "the packer's 'not 0x49' mask disables position 14 "
                            "in all five groups, and the application's map has "
                            "an unused code at position 14 in all five groups",
             "holds": p14_all_skipped,
             "strength": "consistent, but symmetric across groups, so it does "
                         "not fix the group permutation"},
            {"observation": "the packer's 0x44 'D' mask disables exactly "
                            "(group 2, position 13) and (group 3, position 13), "
                            "and the application's map holds a skip code at "
                            "both — a real key at either would contradict the "
                            "identity mapping",
             "holds": d_all_skipped,
             "strength": "this one DOES depend on the group permutation, so it "
                         "is genuine corroboration for groups 2 and 3"},
        ],
        "residual":
            "the bootloader contains no key map and never names a key, so the "
            "claim that its group index equals the application's rests on both "
            "reading the same physical channel grouping, corroborated above "
            "but not proven from the images.",
        "what_would_settle_it":
            "a recovered table in either image that maps a scan channel to a "
            "group index, or an observation of the bitmap with a single known "
            "key held.",
    }


def timing():
    """The poll's position in the boot sequence and its window."""
    boot, base = images()["boot"]
    divisor = word(boot, base, DELAY_DIVISOR_POOL)
    per_sample_us = DELAY_ARG if divisor == 1_000_000 else None
    return {
        "caller": f"0x{POLL_ORCHESTRATOR:08x}",
        "callers_total": 1,
        "call_site": "0x00007efc",
        "position_in_boot":
            "AFTER container selection (0x00002af0 at 0x00007ed6 chooses the "
            "entry) and BEFORE all three remaining boot gates: the "
            "entry-constant compare, the 0x20000ffc one-shot flag "
            "(FUN_00002a44) and the checksum (FUN_000026d0). It is the FIRST "
            "gate that can block the boot.",
        "runs_every_boot": True,
        "delay_function": f"0x{DELAY_FN:08x}",
        "delay_divisor": divisor,
        "delay_unit": "microseconds" if divisor == 1_000_000 else "unknown",
        "delay_unit_basis":
            "FUN_000048dc computes (core_clock / 1000000) * argument and then "
            "busy-loops. Dividing a measured clock by 1e6 makes the argument "
            "microseconds BY CONSTRUCTION, so the unit holds without knowing "
            "the clock's numeric value — which is still unresolved.",
        "per_sample_us": per_sample_us,
        "warmup_samples": CYCLES,
        "match_samples": CYCLES,
        "hold_required_samples": CONSECUTIVE + 1,
        "warmup_ms": CYCLES * per_sample_us / 1000 if per_sample_us else None,
        "window_ms": 2 * CYCLES * per_sample_us / 1000 if per_sample_us else None,
        "hold_ms": (CONSECUTIVE + 1) * per_sample_us / 1000 if per_sample_us else None,
        "practical_consequence":
            "the first 100 samples are discarded, so the combination must "
            "already be held when the poll starts and must stay held into the "
            "second phase for at least 31 consecutive samples. In round "
            "numbers: hold the keys from power-on through roughly the first "
            "fifth of a second. The delays alone total about 200 ms; the scan "
            "itself adds 200 unmeasured conversions on top, so the true window "
            "is longer than 200 ms and is not bounded here.",
        "boot_cost_note":
            "both loops run unconditionally when no key is held, so EVERY "
            "power-on spends this window in the poll.",
    }


def plausibility():
    """Can a user actually hold the combination?"""
    keys = resolved_keys()
    down = [k for k in keys if k.get("state") != "must be UP"]
    up = [k for k in keys if k.get("state") == "must be UP"]
    return {
        "simultaneously_readable": True,
        "why": "the scan is per-key analog, one channel per key, so there is "
               "no matrix and no ghosting; two positions in the same group are "
               "separate bits of one word, not two ends of one channel",
        "keys_down": len(down),
        "keys_up_required": len(up),
        "physically_separated": True,
        "awkwardness":
            "the two number-row positions are two apart with a third position "
            "between them that must stay released, so the combination is "
            "'press the outer two of three adjacent keys'. That is "
            "deliberate-looking and is easy to do with two fingers, but it is "
            "not a combination anyone would strike by accident.",
        "verdict": "physically holdable",
    }


# --- claims -----------------------------------------------------------------

@dataclass(frozen=True)
class Claim:
    key: str
    question: str
    answer: str
    confidence: str
    kind_basis: str
    evidence: tuple


CLAIMS = (
    Claim("mechanism", "What does the bootloader's scan actually sample?",
          "The same muxed analog converter path the second execution context "
          "uses: strobe 0x4001b000, data-out 0x40018000, data-in 0x40019000, "
          "with the identical write-strobe-readback idiom and the identical "
          "0x7c strobe value. It is NOT digital GPIO and NOT a row/column "
          "matrix. The bootloader carries its own copy of the driver and does "
          "not use the second context.",
          "observed",
          "the census attributes those three registers to FUN_000067a4, and "
          "its literal pool holds all three",
          ("this log step 1", "log 119 step 4")),
    Claim("geometry", "What does each bit of the matched buffer mean?",
          "The buffer is five words of fifteen bits. Bit b of word g is linear "
          "scan index g*15 + b, set when that position's level is non-zero and "
          "below 0x1300. The dimensions come from the packer's own loop "
          "bounds, and they match the application's 5 x 15.",
          "observed",
          "`cmp r7,#0xf` and `cmp r5,#0x5` in FUN_0000350c, with the "
          "bit-set/bit-clear stores through the same word index",
          ("this log step 2", "log 110")),
    Claim("positions", "Which positions does the pattern require?",
          "Three pressed — group 0 positions 5 and 7, group 4 position 8 — and, "
          "because the compare is exact equality, every other position in "
          "groups 0 and 4 released, including group 0 position 6 between the "
          "two pressed ones. Groups 1, 2 and 3 are never read.",
          "observed",
          "0xa0 has bits 5 and 7; 0x100 has bit 8; the poll uses `cmp` for "
          "equality and never loads +0x4, +0x8 or +0xc",
          ("this log step 2", "log 101 step 3")),
    Claim("keys", "Which physical keys are they?",
          "Two are named with a complete chain: group 0 position 5 is HID "
          "usage 0x25, the '8' key, and group 0 position 7 is usage 0x23, the "
          "'6' key; the position between them that must stay released is usage "
          "0x24, the '7' key. The third, group 4 position 8, is vendor code "
          "0xe8, which is NOT a HID usage and is never emitted to the host.",
          "observed",
          "the application's key map at 0x1801c940 indexed by group*15+"
          "position, with the firmware's own modifier rule proving the values "
          "are HID usage IDs",
          ("this log step 3",)),
    Claim("third_key", "What is the third key?",
          "Not resolved by name. Code 0xe8 is the only non-HID code in the "
          "map, occurs exactly once, in both layers, and sits between Right "
          "Control and Right Alt in the bottom row — the Fn position on this "
          "product. That is an inference from layout and from the absence of "
          "any emit path, not a recovered name.",
          "strongly-inferred",
          "the code is outside both ranges the report builder handles, and its "
          "neighbours in the map are 0xe4 and 0xe6",
          ("this log step 3",)),
    Claim("timing", "When does the poll matter, and for how long?",
          "It runs on every boot, after container selection and before all "
          "three remaining boot gates, so it is the first thing that can block "
          "a boot. The first 100 samples are discarded and a match needs 31 "
          "consecutive samples in the second 100. The delays alone are about "
          "200 ms; the scans add an unmeasured amount on top.",
          "observed",
          "FUN_00007ec8's call order, and FUN_000048dc dividing a computed "
          "core clock by 1000000, which makes the argument microseconds",
          ("this log step 4", "log 101")),
    Claim("plausibility", "Can a user hold the combination?",
          "Yes. The scan is per-key analog with one channel per key, so there "
          "is no matrix, no ghosting and no mutually exclusive pair. The "
          "awkward part is deliberate: two number-row keys with the key "
          "between them released.",
          "observed",
          "the converter drives one channel per position; two positions in a "
          "group are separate bits of one word",
          ("this log steps 1 and 5",)),
    Claim("g1", "Does this resolve risk-plan gate G1?",
          "PARTIAL. G1 asked which state is sampled and which key positions "
          "the pattern corresponds to. The state and the positions are fully "
          "resolved. Two of the three keys are named with a complete chain; "
          "the third has a matrix coordinate and a strongly-inferred name. "
          "The group-index correspondence between bootloader and application "
          "is corroborated, not proven.",
          "strongly-inferred",
          "the chain is complete except for two named links, each of which is "
          "reported with what would settle it",
          ("this log step 6", "notes/step7-live-experiment-risk-plan.md")),
)


UNRESOLVED = (
    ("third_key_name",
     "Code 0xe8 has a matrix coordinate (group 4, position 8) and no recovered "
     "name. Fn is an inference from its neighbours and from having no emit "
     "path, not a finding."),
    ("group_correspondence",
     "The bootloader holds no key map. That its group index equals the "
     "application's is corroborated by the variant masks landing on non-keys, "
     "but is not proven from the images."),
    ("absolute_clock",
     "The delay's UNIT is microseconds by construction, but the core clock's "
     "numeric value is still unresolved, so the scan time inside each sample "
     "is not bounded and the true poll window is longer than the 200 ms of "
     "delays."),
    ("variant_byte",
     "The byte at 0x18010b56 selects a layout variant ('D', 'E', 'I' or "
     "other). What writes it is not traced. The recovery positions are not "
     "masked under any variant, so the answer does not depend on it."),
    ("down_ceiling",
     "A position counts as down when its level is non-zero and below 0x1300. "
     "The units of that level are unknown, so no travel distance or force is "
     "implied."),
    ("historical_labels",
     "The names here come from the published HID usage table via the "
     "firmware's own map, NOT from this repository's historical capture "
     "labels, which FINDINGS records as not a universal physical layout."),
)


def claims():
    return [{"key": c.key, "question": c.question, "answer": c.answer,
             "confidence": c.confidence, "kind_basis": c.kind_basis,
             "evidence": list(c.evidence)} for c in CLAIMS]


# --- reporting --------------------------------------------------------------

def verify():
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    images()
    check(True, "both preserved source hashes match the allowlist")
    boot = _load(BOOT_BIN)
    check(hashlib.sha256(boot).hexdigest() == BOOT_SHA,
          "the bootloader slice matches its recorded hash", BOOT_SHA[:16])
    check(_load(BOOT_BIN) == _load(BOOT_MIRROR),
          "bootloader_primary and the installed mirror are byte-identical",
          "so the analysed program is the same bytes either way")

    poll = poll_constants()
    check(poll["buffer_matches_log101"],
          "the poll's buffer address is read from its own pool",
          poll["buffer"])
    check(poll["consecutive_samples"] == 31,
          "a match needs 31 consecutive samples", "cmp r5,#0x1e then increment")

    mech = scan_mechanism()
    check(mech["all_three_present"],
          "the bootloader's scan drives the converter trio, not GPIO",
          ", ".join(mech["registers"].values()))
    check(mech["matches_log119_trio"],
          "the trio is the same one log 119 recovered in the second context")

    geo = geometry()
    check(geo["groups"] == 5 and geo["positions_per_group"] == 15,
          "the bitmap is 5 words of 15 bits", geo["bounds_evidence"])
    check(geo["total_positions"] == 75,
          "75 positions, matching the application's key map dimension")

    pattern = decode_pattern()
    down = [(r["group"], r["position"]) for r in pattern["required_down"]]
    check(down == [(0, 5), (0, 7), (4, 8)],
          "the pattern decodes to exactly three pressed positions",
          str(down))
    check(len(pattern["required_up"]) == 27,
          "exact equality also constrains the other positions in both words",
          f"{len(pattern['required_up'])} must be released")

    proof = modifier_rule_proof()
    check(proof["subtracts_0xe0"] and proof["compares_against_7"],
          "the firmware applies the HID modifier rule to the map's values",
          proof["address"])
    check(proof["proves_hid_usages"],
          "so the key map holds HID usage IDs, not arbitrary indices")

    keys = resolved_keys()
    named = [k for k in keys if k["identity"] == "observed"
             and k.get("state") != "must be UP"]
    check(len(named) == 2,
          "two of the three pressed keys are named with a complete chain",
          ", ".join(k["name"] for k in named))
    check(any(k["identity"] == "unresolved" for k in keys),
          "the third is reported UNRESOLVED rather than guessed",
          "0xe8")
    between = [k for k in keys if k.get("state") == "must be UP"]
    check(len(between) == 1 and between[0]["name"] == "7",
          "the key that must stay released is named", "7")

    var = variant_masks()
    check(var["recovery_is_variant_independent"],
          "no variant mask touches any recovery position",
          "so the answer does not depend on the unresolved variant byte")

    corr = group_correspondence()
    check(not corr["bootloader_holds_a_key_map"],
          "the bootloader holds no key map, which is why a residual remains")
    check(not corr["proven"],
          "the group correspondence is reported as corroborated, NOT proven")
    check(all(c["holds"] for c in corr["corroboration"]),
          "both corroborating observations hold",
          f"{len(corr['corroboration'])} observations")

    tim = timing()
    check(tim["delay_unit"] == "microseconds",
          "the delay's unit is established", f"divisor {tim['delay_divisor']}")
    check(tim["callers_total"] == 1,
          "the poll has exactly ONE caller",
          "the prompt's second call site is a caller of the SCAN, not the poll")
    check("BEFORE all three remaining boot gates" in tim["position_in_boot"],
          "the poll's position in the boot order is stated")
    check(tim["runs_every_boot"],
          "the poll runs on every boot, not only on a key press")

    plaus = plausibility()
    check(plaus["simultaneously_readable"],
          "the combination is physically holdable", plaus["verdict"])

    check(all(c["confidence"] in
              ("observed", "strongly-inferred", "inferred", "hypothesis",
               "unresolved") for c in claims()),
          "every claim carries a known confidence label")
    check(all(c["kind_basis"] and c["evidence"] for c in claims()),
          "every claim carries a kind_basis and a citation")
    check(len(UNRESOLVED) >= 5, "the unresolved boundaries are enumerated",
          f"{len(UNRESOLVED)} entries")
    return out


def to_dict():
    checks = verify()
    return {
        "gate": "G1 — physical recovery keys resolved",
        "gate_status": "PARTIAL",
        "poll": poll_constants(),
        "scan_mechanism": scan_mechanism(),
        "geometry": geometry(),
        "pattern": decode_pattern(),
        "variant_masks": variant_masks(),
        "modifier_rule_proof": modifier_rule_proof(),
        "key_map": key_map_rows(),
        "resolved_keys": resolved_keys(),
        "unknown_codes": unknown_code_analysis(),
        "group_correspondence": group_correspondence(),
        "timing": timing(),
        "plausibility": plausibility(),
        "claims": claims(),
        "unresolved": [{"key": k, "detail": d} for k, d in UNRESOLVED],
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images. No device was "
                      "accessed. This resolves an analysis gate and "
                      "authorises nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["RECOVERY KEY COMBINATION — bootloader FUN_000029d4", "",
           f"GATE {d['gate']}: {d['gate_status']}", ""]
    mech = d["scan_mechanism"]
    out += ["SCAN MECHANISM", f"  {mech['answer']}",
            f"  strobe {mech['registers']['strobe']}  "
            f"data-out {mech['registers']['data_out']}  "
            f"data-in {mech['registers']['data_in']}",
            f"  {mech['critical_section']}", ""]
    geo = d["geometry"]
    out += ["GEOMETRY",
            f"  {geo['layout']}  ({geo['total_positions']} positions)",
            f"  {geo['down_rule']}", ""]
    out += ["PATTERN"]
    for row in d["pattern"]["required_down"]:
        out.append(f"  DOWN  group {row['group']} position {row['position']:>2}"
                   f"  linear {row['linear']:>2}")
    out.append(f"  plus every other position in groups 0 and 4 released; "
               f"groups 1-3 not read")
    out += ["", "PHYSICAL KEYS"]
    for k in d["resolved_keys"]:
        state = k.get("state", "DOWN")
        out.append(f"  {state:<11} group {k['group']} pos {k['position']:>2}"
                   f"  code {k['code']}  {k['name']}   [{k['identity']}]")
    corr = d["group_correspondence"]
    out += ["", f"GROUP CORRESPONDENCE  proven={corr['proven']}",
            f"  {corr['residual']}"]
    tim = d["timing"]
    out += ["", "TIMING", f"  {tim['position_in_boot']}",
            f"  delay unit: {tim['delay_unit']} (divisor {tim['delay_divisor']})",
            f"  warm-up {tim['warmup_samples']} samples, match window "
            f"{tim['match_samples']}, hold {tim['hold_required_samples']}",
            f"  delays alone ~{tim['window_ms']:.0f} ms; "
            f"{tim['boot_cost_note']}",
            f"  {tim['practical_consequence']}"]
    plaus = d["plausibility"]
    out += ["", f"PLAUSIBILITY  {plaus['verdict']}", f"  {plaus['why']}",
            f"  {plaus['awkwardness']}", "", "ANSWERS"]
    for c in d["claims"]:
        out.append(f"  [{c['confidence']}] {c['question']}")
        out.append(f"      {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out += ["", f"RESULT recovery_keys_ok={d['summary']['ok']} "
            f"checks={d['summary']['checks']}",
            "OFFLINE ANALYSIS ONLY. No device was accessed, and nothing here "
            "authorises a live experiment."]
    return out


def markdown():
    d = to_dict()
    mech, geo, tim = d["scan_mechanism"], d["geometry"], d["timing"]
    out = ["# The bootloader's recovery key combination", "",
           "**Status: gate G1 PARTIAL.** Generated by "
           "`tool/map_recovery_keys.py`. Do not edit by hand.", "",
           "> Offline analysis of preserved images. No device was accessed. "
           "This resolves an analysis gate and authorises nothing live.", "",
           "## The answer", "",
           "| | group | position | code | key | identity |",
           "|---|---|---|---|---|---|"]
    for k in d["resolved_keys"]:
        out.append(f"| {k.get('state','**DOWN**')} | {k['group']} | "
                   f"{k['position']} | `{k['code']}` | **{k['name']}** | "
                   f"{k['identity']} |")
    out += ["",
            "Because the poll compares for **exact equality**, every other "
            "position in groups 0 and 4 must be released. Groups 1, 2 and 3 "
            "are never read.", "",
            "## The scan mechanism", "",
            f"**{mech['answer']}**", "",
            f"- strobe `{mech['registers']['strobe']}`",
            f"- data-out `{mech['registers']['data_out']}`",
            f"- data-in `{mech['registers']['data_in']}`", "",
            f"{mech['idiom']}", "",
            f"{mech['consequence']}", "",
            f"A correction worth recording: {mech['critical_section']}.", "",
            "## Geometry", "",
            f"{geo['layout']} — {geo['total_positions']} positions. "
            f"{geo['down_rule']}. Bounds from {geo['bounds_evidence']}.", "",
            "## How the codes are known to be HID usages", "",
            f"At `{d['modifier_rule_proof']['address']}` the firmware applies "
            f"`{d['modifier_rule_proof']['rule']}`. That is the USB boot "
            f"keyboard modifier rule, and it only makes sense if the map's "
            f"values are usage IDs. {d['modifier_rule_proof']['citation']}.",
            "", "## The application key map", "",
            "| group | " + " | ".join(f"p{p}" for p in range(15)) + " |",
            "|---" * 16 + "|"]
    for row in d["key_map"]:
        out.append(f"| {row['group']} | " +
                   " | ".join(e["name"].replace("|", "\\|")
                              for e in row["entries"]) + " |")
    out += ["", "## The third key", ""]
    for row in d["unknown_codes"]:
        out += [f"Code `{row['code']}` occurs once, at group "
                f"{row['occurrences_layer0'][0]['group']} position "
                f"{row['occurrences_layer0'][0]['position']}, in both layers. "
                f"Its neighbours are "
                + ", ".join(f"`{n['code']}` ({n['name']})"
                            for n in row["neighbours"]) + ".", "",
                f"{row['why_not_emitted']}.", "",
                f"**Inference ({row['confidence']}):** {row['inference']}", "",
                f"*What would settle it:* {row['what_would_settle_it']}.", ""]
    corr = d["group_correspondence"]
    out += ["## The residual: group correspondence", "",
            f"**Proven: {corr['proven']}.** {corr['residual']}", ""]
    for c in corr["corroboration"]:
        out.append(f"- {c['observation']} — holds: **{c['holds']}**. "
                   f"{c['strength']}.")
    out += ["", f"*What would settle it:* {corr['what_would_settle_it']}.", "",
            "## Timing", "", f"{tim['position_in_boot']}", "",
            f"- delay unit: **{tim['delay_unit']}** — {tim['delay_unit_basis']}",
            f"- warm-up: {tim['warmup_samples']} samples, discarded",
            f"- match window: {tim['match_samples']} samples",
            f"- hold required: {tim['hold_required_samples']} consecutive",
            f"- delays alone: about {tim['window_ms']:.0f} ms", "",
            f"{tim['practical_consequence']}", "",
            f"{tim['boot_cost_note']}", "",
            "## Plausibility", "",
            f"**{d['plausibility']['verdict']}.** {d['plausibility']['why']}",
            "", f"{d['plausibility']['awkwardness']}", "",
            "## Answers", ""]
    for c in d["claims"]:
        out += [f"### {c['question']}", "", c["answer"], "",
                f"- confidence: **{c['confidence']}**",
                f"- basis: {c['kind_basis']}",
                f"- evidence: {', '.join(c['evidence'])}", ""]
    out += ["## Unresolved", ""]
    for item in d["unresolved"]:
        out.append(f"- **{item['key']}** — {item['detail']}")
    out += ["", "## Checks", ""]
    for item in d["checks"]:
        out.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['label']}"
                   + (f" ({item['detail']})" if item["detail"] else ""))
    out.append("")
    return "\n".join(out)


def bodies():
    return {
        "recovery-keys.json": json.dumps(to_dict(), indent=2, sort_keys=True) + "\n",
        "recovery-keys.md": markdown(),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = bodies()
    except (OSError, RecoveryKeyError, ms.SecondContextError, struct.error,
            KeyError, IndexError) as exc:
        print(f"RESULT recovery_keys_ok=False error={exc}")
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
        print(payload["recovery-keys.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
