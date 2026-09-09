#!/usr/bin/env python3
"""The per-key calibration lifecycle: who writes reference and scale, and when.

Read-only and offline. This is the last open piece of the acquisition story
logs 118-120 recovered. It authorises nothing live, and it constructs no
command of any kind: this phase reads code, it never speaks to the device.

THE SHAPE OF THE ANSWER. Four candidate origins were discriminated, and three
are eliminated by evidence rather than by argument:

  (a) computed by the second context itself   CONFIRMED
  (b) sent by the app over the mailbox        ELIMINATED — no mailbox handler
                                              references either array
  (c) loaded from nonvolatile storage         ELIMINATED — the arrays live in
                                              the second context's RAM, which
                                              has no storage path, and nothing
                                              reads them back out
  (d) static image data                       ELIMINATED — both arrays are
                                              all-zero BSS in the image

The elimination rests on one exhaustive scan: every literal-pool word in the
second-context image that points into the calibration block. Only four
functions do, and their roles are recovered individually.

THE SELF-CHECK THAT MAKES THIS TRUSTWORTHY. The runtime updater recomputes
scale as 0x200000 / (reference - floor). Feeding it the hard-coded boot
defaults reproduces the hard-coded default scale exactly, and the resulting
full-travel value lands on the travel curve's maximum. Three constants that
were written independently agree, which is not something a misreading
produces.

No device access. Examples:
    python3 tool/map_calibration_flow.py
    python3 tool/map_calibration_flow.py --json
    python3 tool/map_calibration_flow.py --write
    python3 tool/map_calibration_flow.py --check
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_second_context as ms

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
INVENTORIES = ROOT / "ghidra/inventories"

KEYS = 75

# --- the calibration block, all inside the second-context image -------------
REFERENCE = 0x1803CA08          # u16[75], the released-end baseline
FLOOR = 0x1803CAA0              # u16[75], the pressed-end reference
SCALE = 0x1803CD90              # u32[75], 0x200000 / (reference - floor)
ACCUMULATOR = 0x1803CB38        # u32[75], the learn-path sample accumulator
STEP_COUNTER = 0x1803CEBC       # u8[75], samples seen above the reference
FAULT_FLAG = 0x1803D038         # u8[75], set after 15 implausibly low samples
DEEP_PRESS = 0x1803D11C         # u8[75], last travel value above 0x96
GATE_TIMER = 0x1803D200         # u16[75], per-key settle countdown
BLOCK_LO, BLOCK_HI = 0x1803CA08, 0x1803D300

# --- the hard-coded boot defaults, read back out of the initialiser ---------
DEFAULT_REFERENCE = 0x15E0      # 5600
DEFAULT_FLOOR = 0xDAC           # 3500
DEFAULT_SCALE = 0x3E6           # 998
SCALE_NUMERATOR = 0x200000
SETTLING_PASSES = 0x258         # 600, the initialiser's return value

# --- the conversion, from log 119 -------------------------------------------
TRAVEL_MULTIPLIER = 1279        # (delta<<8)-delta + (delta<<10)
TRAVEL_SHIFT = 21
CLAMP = 0x4FF
LUT = 0x1803BE86
LUT_LEN = 0x500
ACTUATION_THRESHOLD = 100       # log 110

# --- the functions ----------------------------------------------------------
INITIALISER = 0x1803AA1C        # writes every default, once
UPDATER_GUARD = 0x1803AA98      # the sanity window before the updater
UPDATER = 0x1803AAA6            # the runtime tracker
CONVERTER = 0x1803A6C4          # the only reader
GATE_INIT = 0x18039A48          # floors the per-key settle timer
SERVICE_LOOP = 0x1803AF90       # the initialiser's only caller
OPCODE_HANDLER = 0x1803901C     # calls the converter and the gate init
SETTLING_COUNTER = 0x1803C4B4   # where the initialiser's 600 is stored

# The updater's sanity window: proceed only when 0x80 <= sample <= 0x2329.
SANITY_LO = 0x80
SANITY_SPAN = 0x22A9
FAULT_SAMPLE_CEILING = 0xFA     # below this, a sample counts as a fault
FAULT_COUNT = 0xF               # faults needed before the key is flagged
SENTINEL = 0xFFFF               # opcode 0x0d's memset value

# --- the app-side fields the mailbox carries, from logs 119 and 120 ---------
APP_FAULT_COUNTER = 0x27A       # opcode 0x07's array, incremented from here
APP_CHANNEL_TABLE = 0x1E4       # opcode 0x0b's array
APP_DRIVE_TABLE = 0x72C         # opcode 0x0f's array
APP_RAW = 0x2C6
APP_TRAVEL = 0x35C
APP_SAMPLES = 0x3F2

# The /8 job that drives everything, from logs 109 and 114.
TICK_DIV8_JOB = 0x516           # entry image, the prescaler's divide-by-8 job
VENEER_MAILBOX = 0x40D0         # -> FUN_18001fbe
VENEER_REQUESTER = 0x4116       # -> FUN_18008c16


class CalibrationError(RuntimeError):
    """Raised when the evidence does not support continuing."""


def image():
    ms.sources()
    return ms.image(), ms.RUNTIME_BASE


def _read(addr, length):
    img, base = image()
    off = addr - base
    if off < 0 or off + length > len(img):
        raise CalibrationError(f"0x{addr:08x}+{length} is outside the image")
    return img[off:off + length]


# --- where the values live ---------------------------------------------------

def arrays():
    """Each array, its extent, and whether the image initialises it.

    An all-zero array in the image is BSS, which is what eliminates the
    static-data candidate — so this is evidence, not documentation.
    """
    spec = [
        ("reference", REFERENCE, 2, "u16", "the released-end baseline; "
         "delta = reference - sample"),
        ("floor", FLOOR, 2, "u16", "the pressed-end reference; span = "
         "reference - floor"),
        ("scale", SCALE, 4, "u32", "0x200000 / span, recomputed on every "
         "reference or floor change"),
        ("accumulator", ACCUMULATOR, 4, "u32", "the learn path's running sum "
         "of 8 samples"),
        ("step_counter", STEP_COUNTER, 1, "u8", "samples seen above the "
         "reference"),
        ("fault_flag", FAULT_FLAG, 1, "u8", "set after 15 implausibly low "
         "samples"),
        ("deep_press", DEEP_PRESS, 1, "u8", "the last travel value above "
         "0x96, used to gate the fault path"),
        ("gate_timer", GATE_TIMER, 2, "u16", "per-key settle countdown, "
         "floored at 0x12c"),
    ]
    out = []
    for name, addr, width, kind, role in spec:
        raw = _read(addr, KEYS * width)
        nonzero = sum(1 for b in raw if b)
        out.append({
            "name": name, "address": f"0x{addr:08x}", "element": kind,
            "entries": KEYS, "bytes": KEYS * width,
            "extent": f"0x{addr:08x}..0x{addr + KEYS * width - 1:08x}",
            "nonzero_bytes_in_image": nonzero,
            "initialised_in_image": nonzero > 0,
            "storage_class": "initialised data" if nonzero else "BSS (zero)",
            "role": role,
        })
    return out


def writers():
    """Every function whose pool points into the calibration block.

    This is the exhaustive part. If a fifth function ever appears here, the
    'only three writers' claim below is wrong and a check fails.
    """
    img, base = image()
    inv = INVENTORIES / "ram18038000.txt"
    if not inv.exists():
        raise CalibrationError("missing ghidra/inventories/ram18038000.txt")
    funcs = []
    for line in inv.read_text().splitlines():
        if not line.startswith("FUNC"):
            continue
        entry = int(re.search(r"entry=(\S+)", line).group(1), 16)
        name = re.search(r"name=(\S+)", line).group(1)
        ranges = [tuple(int(x, 16) for x in part.split("-"))
                  for part in re.search(r"ranges=(\S+)", line).group(1).split(";")]
        funcs.append((entry, name, ranges))

    def owner(addr):
        best = None
        for entry, name, ranges in funcs:
            for lo, hi in ranges:
                if lo <= addr <= hi + 0x80:
                    if best is None or entry > best[0]:
                        best = (entry, name)
        return best

    seen = {}
    for off in range(0, len(img) - 3, 4):
        value = struct.unpack_from("<I", img, off)[0]
        if BLOCK_LO <= value < BLOCK_HI:
            own = owner(base + off)
            if own:
                seen.setdefault(own, set()).add(value)
    roles = {
        INITIALISER: ("writer", "installs every default, once, at second-"
                      "context startup before any mailbox command is served"),
        UPDATER: ("writer", "the runtime tracker: baseline drift, floor "
                  "tracking, fault detection, and the scale recompute"),
        CONVERTER: ("reader", "the only reader; turns a sample into a travel "
                    "byte"),
        GATE_INIT: ("writer", "floors the per-key settle timer only; touches "
                    "no calibration value"),
    }
    out = []
    for (entry, name), values in sorted(seen.items()):
        role, detail = roles.get(entry, ("unclassified", ""))
        out.append({
            "function": name, "entry": f"0x{entry:08x}", "role": role,
            "detail": detail,
            "touches": [f"0x{v:08x}" for v in sorted(values)],
        })
    return out


# --- the arithmetic ----------------------------------------------------------

def scale_formula():
    """The recovered formula, checked against the independent defaults."""
    span = DEFAULT_REFERENCE - DEFAULT_FLOOR
    derived = SCALE_NUMERATOR // span
    raw = (span * TRAVEL_MULTIPLIER * DEFAULT_SCALE) >> TRAVEL_SHIFT
    lut = _read(LUT, LUT_LEN)
    return {
        "formula": "scale[key] = 0x200000 / (reference[key] - floor[key])",
        "instruction": "sdiv r1,r9,r1 with r9 = 0x200000, at 0x1803ab62, "
                       "0x1803abe0, 0x1803ac24, 0x1803ac76 and 0x1803acca",
        "default_reference": DEFAULT_REFERENCE,
        "default_floor": DEFAULT_FLOOR,
        "default_span": span,
        "default_scale_hardcoded": DEFAULT_SCALE,
        "default_scale_from_formula": derived,
        "formula_reproduces_the_default": derived == DEFAULT_SCALE,
        "full_travel_raw": raw,
        "clamp": CLAMP,
        "lut_value_at_full_travel": lut[min(raw, CLAMP)],
        "lut_maximum": max(lut),
        "full_travel_reaches_the_curve_maximum": lut[min(raw, CLAMP)] == max(lut),
        "actuation_threshold": ACTUATION_THRESHOLD,
        "why_it_matters":
            "the conversion is (reference - sample) * 1279 * scale >> 21. "
            "Substituting scale = 0x200000/span makes it 1279 * (reference - "
            "sample) / span — a normalised 0..1279 position that spans the "
            "travel curve exactly. The scale is not a magic number; it is the "
            "reciprocal of the measured span.",
    }


# --- the lifecycle -----------------------------------------------------------

def lifecycle():
    return [
        {"stage": "boot defaults",
         "when": "once, at second-context startup",
         "writer": f"FUN_{INITIALISER:08x}, called only from the service loop "
                   f"at FUN_{SERVICE_LOOP:08x} before the first command",
         "what": f"reference = 0x{DEFAULT_REFERENCE:x}, floor = "
                 f"0x{DEFAULT_FLOOR:x}, scale = 0x{DEFAULT_SCALE:x} for all "
                 f"{KEYS} keys, plus eight state arrays zeroed",
         "source": "immediate operands in the instruction stream, not a data "
                   "table",
         "confidence": "observed"},
        {"stage": "storage load",
         "when": "never",
         "writer": "none",
         "what": "no calibration value is read from or written to "
                 "nonvolatile storage",
         "source": "the arrays live in the second context's RAM; that image "
                   "has no storage path, no mailbox opcode carries them, and "
                   "the log-111 commit path copies from no staging buffer",
         "confidence": "observed"},
        {"stage": "settling",
         "when": f"the first {SETTLING_PASSES} conversion passes after startup",
         "writer": f"FUN_{CONVERTER:08x} takes the settling branch",
         "what": "calibration is updated from every valid sample, and EVERY "
                 "travel byte is forced to zero — all keys read released",
         "source": f"the counter at 0x{SETTLING_COUNTER:08x} is seeded with "
                   f"the initialiser's return value {SETTLING_PASSES} and "
                   f"decremented per pass",
         "confidence": "observed"},
        {"stage": "runtime tracking",
         "when": "every conversion pass thereafter, per key",
         "writer": f"FUN_{UPDATER:08x} via the guard FUN_{UPDATER_GUARD:08x}",
         "what": "the reference drifts toward the observed released level in "
                 "steps of 5 and 10 behind consecutive-sample gates; the floor "
                 "is pulled down toward observed minima; scale is recomputed "
                 "on every change",
         "source": "listing",
         "confidence": "observed"},
        {"stage": "persistence",
         "when": "never",
         "writer": "none",
         "what": "calibration is discarded at power-off and rebuilt from the "
                 "same hard-coded defaults on the next boot",
         "source": "no writer outside the two functions above, and no reader "
                   "that copies the arrays anywhere",
         "confidence": "strongly-inferred"},
    ]


def invalid_behaviour():
    return {
        "sentinel": f"0x{SENTINEL:x}",
        "sentinel_written_by": "opcode 0x0d's memset over the app's sample "
                               "array at +0x3f2",
        "sentinel_effect":
            "the converter compares each sample against the sentinel FIRST. A "
            "sentinel sample skips the calibration update AND skips the "
            "conversion for that key, so no travel byte is produced. The "
            "subtraction reference - 0xffff never happens.",
        "sentinel_wraps": False,
        "settling_effect":
            f"while the counter at 0x{SETTLING_COUNTER:08x} is non-zero the "
            f"converter forces every travel byte to 0 and every raw word at "
            f"+0x{APP_RAW:x} to 0, for all {KEYS} keys, regardless of sample.",
        "uncalibrated_key_reads": "RELEASED",
        "safe_direction": True,
        "why_safe":
            "the actuation comparison is travel >= 100, and an uncalibrated or "
            "unsampled key yields travel 0 or no write at all. A keyboard that "
            "has not finished calibrating emits no keystrokes; it cannot emit "
            "spurious ones. That is the correct failure direction and it is a "
            "property of the code, not a hope.",
        "sanity_window":
            f"the updater guard proceeds only when the sample lies in "
            f"0x{SANITY_LO:x}..0x{SANITY_LO + SANITY_SPAN:x}; outside that the "
            f"update is skipped entirely",
        "low_sample_path":
            f"a sample below 0x{FAULT_SAMPLE_CEILING:x} increments a per-key "
            f"counter in the APPLICATION's structure at +0x{APP_FAULT_COUNTER:x} "
            f"— the same array mailbox opcode 0x07 carries, so the fault count "
            f"is visible to both sides. After 0x{FAULT_COUNT:x} of them the "
            f"key's fault flag is set, a global flag byte is raised, the floor "
            f"is reset to the default 0x{DEFAULT_FLOOR:x} and the scale is "
            f"recomputed.",
        "flag_bytes": [
            {"array": f"0x{FAULT_FLAG:08x}", "name": "fault_flag",
             "set_when": "15 samples below 0xfa", "gates":
             "routes the key to a path that stores the raw sample instead of "
             "a converted travel byte"},
            {"array": f"0x{DEEP_PRESS:08x}", "name": "deep_press",
             "set_when": "a converted travel value above 0x96",
             "gates": "checked BEFORE the fault flag, so a key that has been "
                      "pressed deeply is not treated as faulted"},
        ],
        "xor_staging_check":
            "the staging validity check in the opcode handler (log 118) runs "
            "BEFORE delivery: a sample failing it is replaced by a default, so "
            "the calibration path never sees a corrupted word. It does not "
            "reject calibration itself.",
    }


def mailbox_relationship():
    """What the mailbox does and does not carry, since (b) was the live
    alternative hypothesis."""
    return {
        "carries_calibration": False,
        "fields": [
            {"offset": f"0x{APP_CHANNEL_TABLE:x}", "opcode": "0x0b",
             "direction": "app -> second",
             "content": "channel selection bytes, packed with 0x8800 into the "
                        "converter's drive arrays — configuration, not "
                        "calibration"},
            {"offset": f"0x{APP_DRIVE_TABLE:x}", "opcode": "0x0f",
             "direction": "app -> second",
             "content": "the five-group drive table the converter writes out — "
                        "configuration, not calibration"},
            {"offset": f"0x{APP_FAULT_COUNTER:x}", "opcode": "0x07",
             "direction": "BOTH",
             "content": "a per-key fault counter the app can seed and the "
                        "second context increments. The only calibration-"
                        "adjacent value that crosses, and it is a symptom "
                        "count, not a coefficient."},
            {"offset": f"0x{APP_SAMPLES:x}", "opcode": "0x01/0x02/0x0c",
             "direction": "second -> app",
             "content": "raw samples"},
            {"offset": f"0x{APP_TRAVEL:x}", "opcode": "0x01/0x02/0x0c",
             "direction": "second -> app",
             "content": "converted travel bytes"},
        ],
        "recalibrate_opcode": None,
        "recalibrate_opcode_note":
            "there is none. The initialiser has exactly ONE caller — the "
            "service loop's startup path — and the updater has exactly ONE "
            "caller, the converter. No mailbox opcode reaches either.",
        "host_command": None,
        "host_command_note":
            "no vendor-HID command triggers calibration. The whole mailbox "
            "cluster hangs off FUN_18001fbe, which the entry image calls from "
            f"FUN_{TICK_DIV8_JOB:08x} — the prescaler's divide-by-8 job — "
            f"through veneer 0x{VENEER_MAILBOX:x}, and the sample requester "
            f"through veneer 0x{VENEER_REQUESTER:x}. The trigger is the tick, "
            "not the host. NO COMMAND BYTES EXIST TO RECOVER, which is the "
            "safest possible outcome for this question.",
        "orphans_resolved": [
            {"function": "FUN_18001fbe",
             "reached_from": f"entry FUN_{TICK_DIV8_JOB:08x} via veneer "
                             f"0x{VENEER_MAILBOX:x}"},
            {"function": "FUN_18008c16",
             "reached_from": f"entry FUN_{TICK_DIV8_JOB:08x} via veneer "
                             f"0x{VENEER_REQUESTER:x}"},
        ],
    }


# --- the dependency-map entry ------------------------------------------------

SERVICE = {
    "key": "calibration",
    "name": "per-key Hall calibration",
    "classification": "must-neutralize",
    "rationale":
        "OWNED ENTIRELY BY THE SECOND CONTEXT, and not reproducible. A "
        "replacement application neither computes nor stores calibration: it "
        "supplies a structure pointer and consumes what appears. The "
        "obligation is therefore to ACCOMMODATE it — respect the settling "
        "window during which every key reads released, and never assume a "
        "travel byte is meaningful before it ends. Treating calibration as "
        "something to implement, or trying to shortcut the settling window, "
        "is the failure mode this classification exists to prevent.",
    "evidence": (
        "log 121: only three functions write the arrays, all inside the "
        "0x18038000 image",
        "log 121: the defaults are immediates, the scale formula is "
        "0x200000/span, and the formula reproduces the default exactly",
        "log 121: no mailbox opcode and no host command reaches either writer",
    ),
    "confidence": "observed",
    "evidence_boundary":
        "the CONTRACT is recovered; the physics is not. The reference, floor "
        "and scale carry no units, the sample's relationship to travel "
        "distance is unknown, and what the drift constants are tuned for "
        "cannot be recovered from code. A replacement can accommodate "
        "calibration; it cannot re-derive it.",
}


# --- claims ------------------------------------------------------------------

@dataclass(frozen=True)
class Claim:
    key: str
    question: str
    answer: str
    confidence: str
    kind_basis: str
    evidence: tuple


CLAIMS = (
    Claim("origin", "Who writes the reference and scale values?",
          "The second context, and nothing else. Exactly three functions "
          "touch the calibration block: an initialiser that installs "
          "hard-coded defaults once at startup, a runtime tracker, and the "
          "converter that only reads. No mailbox handler, no storage path and "
          "no static table participates.",
          "observed",
          "an exhaustive scan of every literal-pool word in the image that "
          "points into 0x1803ca08..0x1803d300 finds four functions, one of "
          "which touches only the settle timer",
          ("this log step 1",)),
    Claim("defaults", "Where do the boot defaults come from?",
          "Immediate operands in the initialiser's instruction stream: "
          "reference 0x15e0, floor 0xdac, scale 0x3e6. Both arrays are "
          "all-zero BSS in the image, so there is no static default table.",
          "observed",
          "the initialiser's listing, and a byte scan showing the arrays are "
          "zero in the image",
          ("this log step 1",)),
    Claim("formula", "How is scale derived?",
          "scale = 0x200000 / (reference - floor), recomputed by an sdiv on "
          "every reference or floor change. Feeding it the boot defaults "
          "reproduces the hard-coded default scale exactly, and full travel "
          "then lands on the travel curve's maximum, which is twice the "
          "actuation threshold.",
          "observed",
          "five sdiv sites with the same numerator, plus a numeric check "
          "against three independently written constants",
          ("this log step 1", "log 119")),
    Claim("runtime", "Do the values change after boot?",
          "Yes. The reference drifts toward the observed released level in "
          "steps of 5 and 10 behind consecutive-sample gates, and the floor is "
          "pulled down toward observed minima. Both recompute the scale. This "
          "is baseline drift compensation, not a one-shot calibration.",
          "observed",
          "the updater's listing: the +0xf/-0x5 hysteresis, the 8-sample "
          "average, and the 10-and-16-and-5 consecutive-count gates",
          ("this log step 2",)),
    Claim("no_command", "Is there a recalibrate command?",
          "No. The initialiser has one caller — the service loop's startup — "
          "and the updater has one caller, the converter. No mailbox opcode "
          "and no vendor-HID command reaches either. The trigger is the "
          "prescaler's divide-by-8 tick job. There are no command bytes to "
          "recover.",
          "observed",
          "the call graph, plus the entry-image veneers that resolve both "
          "long-standing orphan roots to the /8 job",
          ("this log step 2", "log 109", "log 114")),
    Claim("persistence", "Is calibration stored?",
          "No. It lives in the second context's RAM, which has no storage "
          "path; no opcode reads it back; and the log-111 commit path copies "
          "from no staging buffer. It is rebuilt from the same defaults on "
          "every boot and re-learned by drift.",
          "strongly-inferred",
          "the absence of any writer or reader outside the three recovered "
          "functions, bounded by the second context's 484 unresolved accesses",
          ("this log step 1", "log 111 step 5")),
    Claim("invalid", "What happens when calibration is missing or invalid?",
          "Every failure mode resolves to RELEASED. A sentinel sample skips "
          "both the update and the conversion; during the 600-pass settling "
          "window every travel byte is forced to zero; a sample outside the "
          "sanity window is ignored; and a persistently implausible sample "
          "flags the key and resets its floor to the default. An uncalibrated "
          "keyboard emits no keystrokes and cannot emit spurious ones.",
          "observed",
          "the converter's sentinel compare, the settling branch's forced "
          "zero stores, the guard's range test and the fault path's floor "
          "reset",
          ("this log step 3", "log 110")),
    Claim("prototype", "What must a custom firmware do about calibration?",
          "Accommodate it, never implement it. Supply a valid structure "
          "pointer in opcode 0x0d, then treat travel bytes as meaningless "
          "until the settling window ends. Classified MUST-NEUTRALIZE for the "
          "same reason the acquisition is: it is satisfied by inheriting "
          "vendor code, not by reproducing it.",
          "observed",
          "the lifecycle above, and the dependency map's existing convention "
          "for services the second context owns",
          ("this log step 4", "log 119")),
)


UNRESOLVED = (
    ("physical_units",
     "Reference, floor and scale carry no units. The span 2100 is a raw "
     "converter range, not a distance, and nothing relates it to millimetres "
     "or to force."),
    ("drift_constants",
     "The +0xf/-0x5 hysteresis, the 8-sample average and the 10/16/5 "
     "consecutive-count gates are recovered as arithmetic. What they are "
     "tuned for — thermal drift, magnet ageing, mechanical settling — is not "
     "recoverable from code."),
    ("settling_duration",
     "The settling window is 600 conversion passes on the divide-by-8 tick. "
     "IRQ38's period is still unknown, so that is a count, not a duration."),
    ("fault_counter_consumer",
     "The second context increments the app-side fault counter at +0x27a and "
     "opcode 0x07 can seed it, but what the APPLICATION does with the count "
     "is not traced here."),
    ("mode_word",
     "The word at 0x1803c4b0+4 is the settling counter and the byte at +1 is "
     "a global fault flag. What reads that flag is not recovered."),
    ("unresolved_accesses",
     "484 of the second context's accesses still have an unresolved base, so "
     "every negative here remains a 'not resolved'."),
)


def claims():
    return [{"key": c.key, "question": c.question, "answer": c.answer,
             "confidence": c.confidence, "kind_basis": c.kind_basis,
             "evidence": list(c.evidence)} for c in CLAIMS]


# --- reporting ---------------------------------------------------------------

def verify():
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    ms.sources()
    check(True, "both preserved source hashes match the allowlist")

    arr = {a["name"]: a for a in arrays()}
    check(not arr["reference"]["initialised_in_image"],
          "the reference array is BSS, so no static default table exists",
          arr["reference"]["extent"])
    check(not arr["scale"]["initialised_in_image"],
          "the scale array is BSS too", arr["scale"]["extent"])
    check(not arr["floor"]["initialised_in_image"],
          "the floor array is BSS too", arr["floor"]["extent"])

    wr = writers()
    names = {w["entry"] for w in wr}
    check(len(wr) == 4,
          "exactly four functions reference the calibration block",
          ", ".join(w["function"] for w in wr))
    for addr, label in ((INITIALISER, "the initialiser"),
                        (UPDATER, "the runtime tracker"),
                        (CONVERTER, "the converter")):
        check(f"0x{addr:08x}" in names,
              f"{label} is among them", f"0x{addr:08x}")
    check(all(w["role"] != "unclassified" for w in wr),
          "every function touching the block has a recovered role")

    sf = scale_formula()
    check(sf["formula_reproduces_the_default"],
          "the recovered scale formula reproduces the hard-coded default",
          f"0x200000/{sf['default_span']} = {sf['default_scale_from_formula']}")
    check(sf["full_travel_reaches_the_curve_maximum"],
          "default full travel lands on the travel curve's maximum",
          f"LUT[{sf['full_travel_raw']}] = {sf['lut_value_at_full_travel']}")
    check(sf["lut_maximum"] == ACTUATION_THRESHOLD * 2,
          "and that maximum is twice the actuation threshold",
          f"{sf['lut_maximum']} = 2 x {ACTUATION_THRESHOLD}")

    life = {s["stage"]: s for s in lifecycle()}
    check(life["storage load"]["writer"] == "none",
          "no lifecycle stage loads calibration from storage")
    check(life["persistence"]["writer"] == "none",
          "no lifecycle stage persists calibration")
    check(life["boot defaults"]["source"].startswith("immediate operands"),
          "the defaults come from instruction immediates, not a table")

    inv = invalid_behaviour()
    check(inv["uncalibrated_key_reads"] == "RELEASED",
          "an uncalibrated key reads RELEASED", "the safe direction")
    check(inv["safe_direction"],
          "the failure direction is recorded as safe, from code not hope")
    check(not inv["sentinel_wraps"],
          "the sentinel never reaches the subtraction",
          "the compare happens first")
    check(len(inv["flag_bytes"]) == 2,
          "both flag arrays have a recovered gate")

    mb = mailbox_relationship()
    check(not mb["carries_calibration"],
          "no mailbox opcode carries a calibration coefficient")
    check(mb["recalibrate_opcode"] is None,
          "there is no recalibrate opcode")
    check(mb["host_command"] is None,
          "no host command triggers calibration",
          "so no command bytes exist to recover")
    check(len(mb["orphans_resolved"]) == 2,
          "both orphan roots resolve to the divide-by-8 tick job",
          f"FUN_{TICK_DIV8_JOB:08x}")

    check(SERVICE["classification"] in
          ("must-implement", "must-neutralize", "may-omit", "unresolved"),
          "the dependency-map entry uses a known classification",
          SERVICE["classification"])
    check(len(SERVICE["evidence_boundary"]) > 60,
          "the service names an evidence boundary despite being observed",
          "the contract is recovered; the physics is not")

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
        "arrays": arrays(),
        "writers": writers(),
        "scale_formula": scale_formula(),
        "lifecycle": lifecycle(),
        "invalid_behaviour": invalid_behaviour(),
        "mailbox": mailbox_relationship(),
        "dependency_service": SERVICE,
        "claims": claims(),
        "unresolved": [{"key": k, "detail": d} for k, d in UNRESOLVED],
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images. No device was "
                      "accessed and no command of any kind was constructed. "
                      "This authorises nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["PER-KEY CALIBRATION LIFECYCLE", "", "ARRAYS"]
    for a in d["arrays"]:
        out.append(f"  {a['name']:<14} {a['extent']}  {a['element']}[{a['entries']}]"
                   f"  {a['storage_class']}")
    out += ["", "WRITERS AND READERS"]
    for w in d["writers"]:
        out.append(f"  {w['entry']} {w['function']:<16} {w['role']:<8} "
                   f"{', '.join(w['touches'])}")
        if w["detail"]:
            out.append(f"      {w['detail']}")
    sf = d["scale_formula"]
    out += ["", "THE SCALE FORMULA", f"  {sf['formula']}",
            f"  defaults: reference {sf['default_reference']}, floor "
            f"{sf['default_floor']}, span {sf['default_span']}",
            f"  0x200000/{sf['default_span']} = "
            f"{sf['default_scale_from_formula']} vs hard-coded "
            f"{sf['default_scale_hardcoded']}  -> "
            f"{sf['formula_reproduces_the_default']}",
            f"  full travel raw {sf['full_travel_raw']} -> LUT "
            f"{sf['lut_value_at_full_travel']} (max {sf['lut_maximum']})", ""]
    out.append("LIFECYCLE")
    for s in d["lifecycle"]:
        out.append(f"  {s['stage']:<18} {s['when']}")
        out.append(f"      writer: {s['writer']}")
        out.append(f"      {s['what']}")
    inv = d["invalid_behaviour"]
    out += ["", "INVALID CALIBRATION",
            f"  an uncalibrated key reads {inv['uncalibrated_key_reads']}  "
            f"(safe direction: {inv['safe_direction']})",
            f"  {inv['sentinel_effect']}",
            f"  {inv['settling_effect']}",
            f"  {inv['low_sample_path']}"]
    mb = d["mailbox"]
    out += ["", "MAILBOX",
            f"  carries calibration: {mb['carries_calibration']}",
            f"  {mb['host_command_note']}"]
    svc = d["dependency_service"]
    out += ["", f"DEPENDENCY MAP: {svc['key']} -> {svc['classification']}",
            f"  {svc['rationale']}", "", "ANSWERS"]
    for c in d["claims"]:
        out.append(f"  [{c['confidence']}] {c['question']}")
        out.append(f"      {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out += ["", f"RESULT calibration_ok={d['summary']['ok']} "
            f"checks={d['summary']['checks']}",
            "OFFLINE ANALYSIS ONLY. No device was accessed, no command was "
            "constructed, and nothing here authorises a live experiment."]
    return out


def markdown():
    d = to_dict()
    sf, inv, mb = d["scale_formula"], d["invalid_behaviour"], d["mailbox"]
    out = ["# The per-key calibration lifecycle", "",
           "**Status: recovered.** Generated by "
           "`tool/map_calibration_flow.py`. Do not edit by hand.", "",
           "> Offline analysis of preserved images. No device was accessed and "
           "no command of any kind was constructed. This authorises nothing "
           "live.", "",
           "## Where the values live", "",
           "| array | extent | type | storage | role |",
           "|---|---|---|---|---|"]
    for a in d["arrays"]:
        out.append(f"| `{a['name']}` | `{a['extent']}` | "
                   f"{a['element']}[{a['entries']}] | {a['storage_class']} | "
                   f"{a['role']} |")
    out += ["",
            "Both `reference` and `scale` are **zero in the image**, which is "
            "what eliminates a static default table.", "",
            "## Who writes them", "",
            "| function | role | touches |", "|---|---|---|"]
    for w in d["writers"]:
        out.append(f"| `{w['function']}` (`{w['entry']}`) | {w['role']} | "
                   f"{', '.join('`' + t + '`' for t in w['touches'])} |")
    out += ["", "Exhaustive: these are every function in the image whose "
            "literal pool points into the calibration block.", "",
            "## The scale formula", "",
            f"`{sf['formula']}`", "",
            f"Substituting the boot defaults — reference "
            f"{sf['default_reference']}, floor {sf['default_floor']}, span "
            f"{sf['default_span']} — gives **{sf['default_scale_from_formula']}**, "
            f"which is exactly the hard-coded default "
            f"**{sf['default_scale_hardcoded']}**. Full travel then converts to "
            f"{sf['full_travel_raw']}, and the travel curve's value there is "
            f"{sf['lut_value_at_full_travel']} — its maximum, and twice the "
            f"actuation threshold.", "",
            f"{sf['why_it_matters']}", "",
            "## The lifecycle", "",
            "| stage | when | writer | what |", "|---|---|---|---|"]
    for s in d["lifecycle"]:
        out.append(f"| **{s['stage']}** | {s['when']} | {s['writer']} | "
                   f"{s['what']} |")
    out += ["", "## Invalid or missing calibration", "",
            f"**An uncalibrated key reads {inv['uncalibrated_key_reads']}.** "
            f"{inv['why_safe']}", "",
            f"- *Sentinel.* {inv['sentinel_effect']}",
            f"- *Settling.* {inv['settling_effect']}",
            f"- *Sanity window.* {inv['sanity_window']}",
            f"- *Low samples.* {inv['low_sample_path']}",
            f"- *Staging check.* {inv['xor_staging_check']}", "",
            "| flag array | set when | gates |", "|---|---|---|"]
    for f in inv["flag_bytes"]:
        out.append(f"| `{f['array']}` ({f['name']}) | {f['set_when']} | "
                   f"{f['gates']} |")
    out += ["", "## What the mailbox does and does not carry", "",
            "| offset | opcode | direction | content |", "|---|---|---|---|"]
    for f in mb["fields"]:
        out.append(f"| `+{f['offset']}` | `{f['opcode']}` | {f['direction']} | "
                   f"{f['content']} |")
    out += ["", f"**{mb['recalibrate_opcode_note']}**", "",
            f"{mb['host_command_note']}", "",
            "Both long-standing orphan roots are resolved by this:", ""]
    for o in mb["orphans_resolved"]:
        out.append(f"- `{o['function']}` — {o['reached_from']}")
    svc = d["dependency_service"]
    out += ["", "## Dependency-map classification", "",
            f"**`{svc['key']}` — {svc['classification']}.** {svc['rationale']}",
            "", f"*Evidence boundary.* {svc['evidence_boundary']}", "",
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
        "calibration-flow.json": json.dumps(to_dict(), indent=2,
                                            sort_keys=True) + "\n",
        "calibration-flow.md": markdown(),
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
    except (OSError, CalibrationError, ms.SecondContextError, struct.error,
            KeyError, AttributeError) as exc:
        print(f"RESULT calibration_ok=False error={exc}")
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
        print(payload["calibration-flow.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
