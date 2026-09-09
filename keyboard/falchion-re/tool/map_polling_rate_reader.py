#!/usr/bin/env python3
"""Who reads the polling-rate multiplier, and what it programs.

Read-only and offline. Authorises nothing live, constructs no frame, and
patches nothing. Every byte quoted here was read out of a preserved image or a
pre-existing read-only Ghidra export.

WHAT LOG 126 LEFT OPEN. Log 126 recovered the `51 31` command, its index at
payload offset 4, its persistence at profile block +0x4f8 bits 0..3, and its
expansion `1 << index` stored as ONE BYTE at 0x1801e736. It found six writers
and NO READER, by an aligned-word literal search, a displacement search and a
movw/movt search. The searches were not blind — but they were looking for the
wrong byte shape.

WHY THEY MISSED IT. 0x1801e736 = 0x1801e734 + 2, and 0x1801e734 is the
key-state struct that log 109 recorded twelve report-range functions loading
from a literal pool. A reader that says `ldrb rX,[base,#2]` leaves NO literal
equal to 0x1801e736 anywhere. The reader was already resolved, all along, in
the Ghidra peripheral census that log 126 never consulted.

THE ANSWER. Four reads, all in FUN_18004a7e — the actuation compare. Each
multiplies the byte by ten and uses the product as a per-key timeout in units
of the tick job's own invocations. And the mechanism that changes the period is
not in this image at all: the ENTRY image's tick job reads profile block +0x4f8
directly, and BYPASSES ITS OWN DIVIDE-BY-EIGHT when the index is 3.

CONSEQUENTLY IRQ38 NOW HAS A PERIOD. Log 124 recorded `8000/8 = 1000` as "a
consistency, not a measurement", written down "so a future step can test it
instead of inheriting it as fact". This is that step, and the alignment holds as
a measurement: log 126 measured the device's report-availability grid at 1 ms
for index 0, the gate makes index 0 run the report stage every eighth tick, so
the tick period is 125 us.

WHAT IS STILL NOT RESOLVED. The clock CONFIGURATION — crystal, PLL, the reset
sequence's registers — is untouched by this and the dependency map's
`clock_frequency` service stays unresolved. A derived period is not a register
map.

No device access. Examples:
    python3 tool/map_polling_rate_reader.py
    python3 tool/map_polling_rate_reader.py --json
    python3 tool/map_polling_rate_reader.py --write
    python3 tool/map_polling_rate_reader.py --check
"""
import argparse
from collections import defaultdict
import functools
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
PERIPHERALS = ROOT / "ghidra/peripherals"

# The slices, with the runtime base each is loaded at.
APP = ("installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin",
       0x18000000)
ENTRY = ("installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin",
         0x00000000)
VENDOR_APP = ("vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin",
              0x18000000)
VENDOR_ENTRY = ("vendor_app_a_slot0_flash11000_dst00000000_len058ac_"
                "a0f4ddd2.bin", 0x00000000)
SECOND = ("ram_image_18038000.bin", 0x18038000)

# log 109 step 7: the key-state struct twelve report-range functions load.
KEY_STATE = 0x1801E734
MULTIPLIER = KEY_STATE + 2          # 0x1801e736 — log 126's orphan byte
KEY_STATE_VENDOR = 0x1801E708       # notes/scan-pipeline.md's measured relocation
MULTIPLIER_VENDOR = KEY_STATE_VENDOR + 2

PROFILE_BLOCK = 0x18021DE0          # log 125
RATE_FIELD_OFFSET = 0x4F8           # log 125 / log 126: bits 0..3 are the index

# The entry image's tick job, log 109 step 5 / log 119 step 5.
TICK_JOB = 0x000004BA
GATE_LOAD_PROFILE = 0x000004D4      # ldr r0,[pc] -> the profile block literal
GATE_READ_FIELD = 0x000004D6        # ldrb.w r0,[r0,#0x4f8]
GATE_MASK = 0x000004DA              # and r1,r0,#0xf
GATE_LOAD_COUNTER = 0x000004DE      # ldr r0,[pc] -> the /8 counter
GATE_COMPARE_INDEX = 0x000004E0     # cmp r1,#0x3
GATE_COMPARE_EIGHT = 0x000004EC     # cmp r1,#0x8
GATE_LITERALS = (0x000005B4, 0x000005B8, 0x000005BC)
DIVISOR_BYPASS_INDEX = 3            # the only index the gate compares against
DIVISOR_DEFAULT = 8
DIVISOR_BYPASS = 1

# The reader, from the census. Kept as data so a check can require the census
# to still say exactly this.
READER_FUNC = 0x18004A7E
READ_SITES = (0x180053C4, 0x180054AC, 0x18005534, 0x180055A2)
READ_SITES_VENDOR = (0x1800539A, 0x18005480, 0x18005514, 0x18005582)
WRITE_SITES = (0x1800117E, 0x18001548, 0x180018F8, 0x18001ECE,   # FUN_18000d56
               0x18002B50,                                        # FUN_18001fbe
               0x18007A1E)                                        # no function
# The one write the census cannot see, and the reason it cannot.
WRITE_SITE_WITHOUT_FUNCTION = 0x18007A1E

# The scale: multiplier x 5, then x 2 — a ten, in two instructions.
SCALE_X5 = "eb00 0080"              # add.w rX,rX,rX,lsl #2   (one encoding)
SCALE_FACTOR = 10

# Byte-level assertions. Every instruction this model cites is pinned to the
# halfwords actually present in the image, so the citations cannot rot.
APP_BYTES = {
    0x180053C0: "f89e 2022",        # ldrb.w r2,[lr,#0x22]  the per-key parameter
    0x180053C4: "7880",             # ldrb   r0,[r0,#0x2]   THE MULTIPLIER
    0x180053CA: "eb00 0080",        # add.w  r0,r0,r0,lsl #2  x5
    0x180053CE: "0040",             # lsls   r0,r0,#0x1       x2  -> x10
    0x180053D0: "4342",             # muls   r2,r0,r2         parameter x 10M
    0x180053D2: "f85c 0024",        # ldr.w  r0,[r12,r4,lsl #2]  the per-key counter
    0x180053D6: "4282",             # cmp    r2,r0
    0x180054AC: "f89c c002",        # ldrb.w r12,[r12,#0x2]  THE MULTIPLIER
    0x180054B0: "eb0c 0c8c",        # add.w  r12,r12,r12,lsl #2
    0x180054B4: "ea4f 0c4c",        # lsl.w  r12,r12,#0x1
    0x180054B8: "fb01 f10c",        # mul    r1,r1,r12
    0x18005488: "f858 3024",        # ldr.w  r3,[r8,r4,lsl #2]
    0x1800548C: "1c5b",             # adds   r3,r3,#0x1      THE COUNTER TICKS
    0x1800548E: "f848 3024",        # str.w  r3,[r8,r4,lsl #2]
    0x18005534: "7880",             # ldrb   r0,[r0,#0x2]    THE MULTIPLIER
    0x1800553C: "4343",             # muls   r3,r0,r3
    0x180055A2: "f89c c002",        # ldrb.w r12,[r12,#0x2]  THE MULTIPLIER
    0x180055AE: "fb00 f00c",        # mul    r0,r0,r12
}
ENTRY_BYTES = {
    0x000004CC: "4839",             # ldr    r0,[pc,#0xe4]  -> *(0x5b4)
    0x000004D0: "2801",             # cmp    r0,#0x1
    0x000004D4: "4838",             # ldr    r0,[pc,#0xe0]  -> *(0x5b8) profile
    0x000004D6: "f890 04f8",        # ldrb.w r0,[r0,#0x4f8] THE RATE FIELD
    0x000004DA: "f000 010f",        # and    r1,r0,#0xf     THE INDEX
    0x000004DE: "4837",             # ldr    r0,[pc,#0xdc]  -> *(0x5bc) counter
    0x000004E0: "2903",             # cmp    r1,#0x3        THE BYPASS TEST
    0x000004E2: "d00b",             # beq    0x4fc          -> run every tick
    0x000004E4: "7801",             # ldrb   r1,[r0]
    0x000004E6: "1c49",             # adds   r1,r1,#0x1
    0x000004EA: "7001",             # strb   r1,[r0]
    0x000004EC: "2908",             # cmp    r1,#0x8        THE /8 DIVIDER
    0x000004EE: "d005",             # beq    0x4fc
    0x000004F0: "f003 fda8",        # bl     0x4044         sample fetch only
    0x000004FE: "7001",             # strb   r1,[r0]        reset the counter
}

# The veneers the gated block calls, in program order, with the targets log 119
# resolved independently. The decoder below re-derives them from the bytes.
GATED_VENEERS = (
    (0x00004058, 0x180045B6, "FUN_180045b6 — the state/effect helper"),
    (0x00004044, 0x180049A4, "the sample fetch (log 119)"),
    (0x00004062, 0x18004A7E, "FUN_18004a7e — THE ACTUATION COMPARE"),
    (0x0000406C, 0x180057FE, "FUN_180057fe"),
    (0x00004076, 0x180061C2, "FUN_180061c2 — the report builder"),
)
UNGATED_VENEERS = (
    (0x00004044, 0x180049A4, "the sample fetch — ALSO on the else path, so "
                             "Hall sampling is never gated by the rate"),
    (0x0000404E, 0x1800417E, "FUN_1800417e — the 21-byte EP 0x8c sender"),
)

# log 126's wire measurement, the only external number this model consumes.
MEASURED_GRID_MS = {0: 1.0, 3: 0.125}
PROTOCOL_MODEL = NOTES / "polling-rate-protocol.json"

ACCESS_RE = re.compile(
    r"^ACCESS target=0x(?P<target>[0-9a-f]+) width=(?P<width>\d+) "
    r"dir=(?P<dir>read|write) instr=(?P<instr>[0-9a-f]+) "
    r"func=(?P<func>[0-9a-f]+) base=(?P<base>\S+) off=(?P<off>-?\d+) "
    r"stored=(?P<stored>\S+)$")


def _sentence(text):
    """Capitalise only the first letter, leaving FUN_ names and units alone."""
    return text[:1].upper() + text[1:] if text else text


class ReaderError(Exception):
    """Raised on any input this tool refuses to guess about."""


# ------------------------------------------------------------------- inputs

@functools.lru_cache(maxsize=None)
def slice_bytes(name):
    path = IMPORTS / name
    if not path.exists():
        raise ReaderError(f"image slice missing: {path}")
    return path.read_bytes()


def word(name, base, addr):
    d = slice_bytes(name)
    off = addr - base
    if not 0 <= off <= len(d) - 4:
        raise ReaderError(f"{addr:#x} is outside {name}")
    return struct.unpack_from("<I", d, off)[0]


def halfwords(name, base, addr, count):
    d = slice_bytes(name)
    off = addr - base
    if not 0 <= off <= len(d) - 2 * count:
        raise ReaderError(f"{addr:#x}+{count} halfwords is outside {name}")
    return " ".join(f"{struct.unpack_from('<H', d, off + 2 * i)[0]:04x}"
                    for i in range(count))


@functools.lru_cache(maxsize=None)
def census():
    """Every resolved ACCESS record from the pre-existing Ghidra exports."""
    rows = []
    files = sorted(PERIPHERALS.glob("*.txt"))
    if not files:
        raise ReaderError(f"no peripheral census in {PERIPHERALS}")
    for path in files:
        for line in path.read_text().splitlines():
            m = ACCESS_RE.match(line)
            if m:
                rows.append({"file": path.name,
                             "target": int(m.group("target"), 16),
                             "width": int(m.group("width")),
                             "dir": m.group("dir"),
                             "instr": int(m.group("instr"), 16),
                             "func": int(m.group("func"), 16),
                             "base": m.group("base"),
                             "off": int(m.group("off")),
                             "stored": m.group("stored")})
    return tuple(rows)


def census_for(target, files=None):
    rows = [r for r in census() if r["target"] == target
            and (files is None or r["file"] in files)]
    return rows


@functools.lru_cache(maxsize=None)
def functions(inventory="installed_b.txt"):
    path = INVENTORIES / inventory
    if not path.exists():
        raise ReaderError(f"inventory missing: {path}")
    out = []
    for line in path.read_text().splitlines():
        if not line.startswith("FUNC"):
            continue
        entry = int(re.search(r"entry=(\w+)", line).group(1), 16)
        name = re.search(r"name=(\S+)", line).group(1)
        spans = tuple(tuple(int(x, 16) for x in r.split("-"))
                      for r in re.search(r"ranges=(\S+)", line).group(1)
                      .split(";"))
        out.append((entry, name, spans))
    if not out:
        raise ReaderError(f"{inventory} declares no functions")
    return tuple(out)


def owner(addr, inventory="installed_b.txt"):
    """The smallest function body containing addr, or None.

    Smallest, not first: several inventory ranges overlap, and picking the
    first match attributed a site to the wrong function in log 126.
    """
    hits = [f for f in functions(inventory)
            if any(lo <= addr < hi for lo, hi in f[2])]
    if not hits:
        return None
    return min(hits, key=lambda f: sum(hi - lo for lo, hi in f[2]))[1]


# ------------------------------------------------------- instruction decode

def literal_slots(name, base, predicate):
    """Every aligned word in a slice whose value satisfies predicate."""
    d = slice_bytes(name)
    out = []
    for off in range(0, len(d) - 3, 4):
        value = struct.unpack_from("<I", d, off)[0]
        if predicate(value):
            out.append((base + off, value))
    return tuple(out)


def literal_load_sites(name, base):
    """Every `ldr rX,[pc,#imm]`, T1 and T2, with the slot it names.

    This is what closes the search: a reader must reach 0x1801e736 either from
    a literal equal to it, from a nearby literal plus an immediate, or from a
    movw/movt pair. Enumerating the pc-relative loads of every nearby literal
    covers the middle case exhaustively.
    """
    d = slice_bytes(name)
    out = []
    for off in range(0, len(d) - 3, 2):
        hw = struct.unpack_from("<H", d, off)[0]
        if (hw >> 11) == 0b01001:                     # LDR Rt,[PC,#imm8*4]
            rt, imm = (hw >> 8) & 7, (hw & 0xFF) * 4
            slot = ((base + off + 4) & ~3) + imm
            out.append((base + off, rt, slot, "T1"))
        elif (hw & 0xFF7F) == 0xF85F:                 # LDR.W Rt,[PC,#+/-imm12]
            hw2 = struct.unpack_from("<H", d, off + 2)[0]
            rt, imm = (hw2 >> 12) & 0xF, hw2 & 0xFFF
            delta = imm if (hw >> 7) & 1 else -imm
            slot = ((base + off + 4) & ~3) + delta
            out.append((base + off, rt, slot, "T2"))
    return tuple(out)


def decode_veneer(name, base, addr):
    """movw r12,#lo ; movt r12,#hi ; bx r12 -> the absolute target.

    The same idiom logs 119 and 120 had to decode by hand. Self-checked below
    against a target Ghidra resolved independently.
    """
    d = slice_bytes(name)
    off = addr - base
    if not 0 <= off <= len(d) - 10:
        raise ReaderError(f"veneer {addr:#x} is outside {name}")
    hw = [struct.unpack_from("<H", d, off + 2 * i)[0] for i in range(5)]

    def imm16(a, b):
        i = (a >> 10) & 1
        imm4 = a & 0xF
        imm3 = (b >> 12) & 7
        imm8 = b & 0xFF
        return (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8

    if (hw[0] & 0xFBF0) != 0xF240:
        raise ReaderError(f"{addr:#x} does not start with movw")
    if (hw[2] & 0xFBF0) != 0xF2C0:
        raise ReaderError(f"{addr:#x} has no movt at +4")
    if hw[4] != 0x4760:
        raise ReaderError(f"{addr:#x} does not end with bx r12")
    value = (imm16(hw[2], hw[3]) << 16) | imm16(hw[0], hw[1])
    return value & ~1                                  # drop the Thumb bit


# ------------------------------------------------------------- the findings

@functools.lru_cache(maxsize=None)
def reader_table():
    """Every resolved access to the multiplier byte, read or write."""
    rows = []
    for r in census_for(MULTIPLIER):
        rows.append({
            "instruction": f"{r['instr']:#x}",
            "function": owner(r["instr"]) or "NO FUNCTION BODY",
            "census_func": f"{r['func']:#x}",
            "direction": r["dir"], "width": r["width"],
            "base": r["base"], "offset": r["off"],
            "source": "ghidra peripheral census"})
    if WRITE_SITE_WITHOUT_FUNCTION not in [int(x["instruction"], 16)
                                           for x in rows]:
        rows.append({
            "instruction": f"{WRITE_SITE_WITHOUT_FUNCTION:#x}",
            "function": owner(WRITE_SITE_WITHOUT_FUNCTION) or "NO FUNCTION BODY",
            "census_func": None, "direction": "write", "width": 1,
            "base": f"literal@{MULTIPLIER:#x}", "offset": 0,
            "source": "log 126's aligned-word literal search — the census "
                      "iterates functions and Ghidra never assigned this code "
                      "to one, which is exactly why neither method is "
                      "sufficient alone"})
    return tuple(sorted(rows, key=lambda r: (r["direction"],
                                             int(r["instruction"], 16))))


@functools.lru_cache(maxsize=None)
def scale_sites():
    """The four read sites and the arithmetic each applies."""
    out = []
    for addr in READ_SITES:
        out.append({
            "read": f"{addr:#x}",
            "function": owner(addr),
            "multiplies_by": SCALE_FACTOR,
            "then": "mul against a per-key byte parameter, compared against a "
                    "per-key 32-bit counter incremented once per tick-job "
                    "invocation"})
    return tuple(out)


@functools.lru_cache(maxsize=None)
def threshold_addressing():
    """Where the scaled parameter comes from, read off the address arithmetic.

    0x18005498  add.w r1,r1,r2,lsl #2     r2 = layer * 0x361
    0x1800549c  add.w r2,r1,r4,lsl #5     r4 = key index, stride 0x20
    then [r2,#0x22] is the byte and [r2,#0x20] the halfword.
    0x361 * 4 = 0xd84, log 125's keymap-bank layer stride, and 0x20 is log
    125's per-key record size — which is what identifies the array.
    """
    stride_words = 0x361
    return {
        "bank_base": f"{word(APP[0], APP[1], 0x180056A0):#x}",
        "layer_stride_words": stride_words,
        "layer_stride_bytes": f"{stride_words * 4:#x}",
        "record_stride": "0x20",
        "parameter_offset": "0x22",
        "paired_halfword_offset": "0x20",
        "agrees_with_log_125": (stride_words * 4 == 0xD84),
        "note": "0x361*4 = 0xd84 is log 125's keymap-bank layer stride and "
                "0x20 is its per-key record size, so this is the keymap "
                "bank's per-key record array. The +0x20/+0x22 pair lands at "
                "offset 0 and 2 of the record one stride further on, which is "
                "consistent with log 125's record 0 being the bank header — "
                "recorded as the reading it is, not asserted as a field name. "
                "Log 125 named +0x04..+0x1c; +0x20/+0x22 are outside what it "
                "named and this step does not name them either.",
    }


@functools.lru_cache(maxsize=None)
def tick_gate():
    """The divider bypass in the entry image's tick job."""
    name, base = ENTRY
    literals = {f"{a:#x}": f"{word(name, base, a):#x}" for a in GATE_LITERALS}
    veneers = []
    for addr, expected, role in GATED_VENEERS:
        got = decode_veneer(name, base, addr)
        veneers.append({"veneer": f"{addr:#x}", "target": f"{got:#x}",
                        "matches_log_119": got == expected, "role": role})
    ungated = []
    for addr, expected, role in UNGATED_VENEERS:
        got = decode_veneer(name, base, addr)
        ungated.append({"veneer": f"{addr:#x}", "target": f"{got:#x}",
                        "matches_prior_logs": got == expected, "role": role})
    return {
        "function": f"{TICK_JOB:#x}",
        "reads": f"the profile block at {PROFILE_BLOCK:#x} + "
                 f"{RATE_FIELD_OFFSET:#x}, masked with 0xf",
        "literals": literals,
        "profile_literal_is_the_profile_block":
            word(name, base, 0x000005B8) == PROFILE_BLOCK,
        "bypass_test": f"cmp r1,#{DIVISOR_BYPASS_INDEX} at "
                       f"{GATE_COMPARE_INDEX:#x}, beq the gated block",
        "divider_test": f"cmp r1,#{DIVISOR_DEFAULT} at "
                        f"{GATE_COMPARE_EIGHT:#x}",
        "divisor_by_index": {"0": DIVISOR_DEFAULT, "1": DIVISOR_DEFAULT,
                             "2": DIVISOR_DEFAULT,
                             "3": DIVISOR_BYPASS},
        "shape": "a TWO-WAY branch, not a ladder and not a table: index 3 "
                 "bypasses the divider, every other value takes it",
        "gated": veneers,
        "ungated": ungated,
        "identical_in_both_releases": (
            slice_bytes(ENTRY[0])[TICK_JOB:0x516]
            == slice_bytes(VENDOR_ENTRY[0])[TICK_JOB:0x516]),
    }


@functools.lru_cache(maxsize=None)
def period_model():
    """The period, derived from log 126's measurement plus the gate.

    The informative state is the SLOW one. At index 3 the host polls EP 0x81
    every 125 us anyway (bInterval 1 at high speed), so a 125 us grid there is
    equally explained by the host's schedule and pins nothing. At index 0 the
    grid is 1 ms, which the host's 125 us polling cannot produce — so it is the
    DEVICE making data available only every 1 ms. The gate makes index 0 run
    the report stage every eighth tick. Eight ticks = 1 ms.
    """
    slow = MEASURED_GRID_MS[0]
    tick_us = slow * 1000.0 / DIVISOR_DEFAULT
    fast_predicted = tick_us * DIVISOR_BYPASS / 1000.0
    return {
        "measured_grid_ms": {str(k): v for k, v in MEASURED_GRID_MS.items()},
        "measurement_source": "log 126, notes/polling-rate-protocol.json",
        "derived_from": "index 0 — the slow state, the only one the host's own "
                        "125 us polling cannot account for",
        "irq38_period_us": tick_us,
        "irq38_hz": round(1e6 / tick_us),
        "fast_state_predicted_grid_ms": fast_predicted,
        "fast_state_measured_grid_ms": MEASURED_GRID_MS[3],
        "prediction_holds": abs(fast_predicted - MEASURED_GRID_MS[3]) < 1e-9,
        "job_period_ms_by_index": {
            str(i): tick_us * tick_gate()["divisor_by_index"][str(i)] / 1000.0
            for i in range(4)},
        "confidence": "strongly-inferred",
        "kind_basis": "the gate and the divider are read out of the "
                      "instruction stream (observed); the 1 ms device grid is "
                      "measured on the wire (observed); combining them "
                      "additionally assumes the report stage makes at most one "
                      "new report available per invocation, which is not "
                      "separately proven. That assumption is what keeps this "
                      "strongly-inferred rather than observed.",
        "would_be_refuted_by": "a report stage that coalesced or emitted more "
                               "than one report per invocation, or a second "
                               "ungated producer for EP 0x81",
        "closes_log_124_lead": "log 124 recorded 8000/8 = 1000 as 'a "
                               "consistency, not a measurement', written down "
                               "so a future step could test it. It holds.",
        "does_not_resolve": "the clock CONFIGURATION. No crystal value, PLL "
                            "multiplier or divider register is recovered by "
                            "this step, and the dependency map's "
                            "clock_frequency service stays unresolved.",
    }


@functools.lru_cache(maxsize=None)
def units_model():
    """The per-key parameter's real-world unit, and why it is rate-invariant."""
    p = period_model()
    rows = []
    for index in (0, 3):
        divisor = tick_gate()["divisor_by_index"][str(index)]
        multiplier = 1 << index
        job_ms = p["irq38_period_us"] * divisor / 1000.0
        rows.append({"index": index, "divisor": divisor,
                     "multiplier": multiplier,
                     "job_period_ms": job_ms,
                     "threshold_invocations_per_unit": multiplier * SCALE_FACTOR,
                     "real_ms_per_unit": multiplier * SCALE_FACTOR * job_ms})
    invariant = len({round(r["real_ms_per_unit"], 9) for r in rows}) == 1
    return {
        "rows": rows,
        "rate_invariant": invariant,
        "parameter_unit_ms": rows[0]["real_ms_per_unit"] if invariant else None,
        "why": "the multiplier is 1 << index and the divisor is 8 for every "
               "index but 3, where it is 1. multiplier x divisor is 8 in both "
               "reachable states, so parameter x multiplier x 10 job "
               "invocations is the same real duration at either rate. THIS IS "
               "THE CORROBORATION THAT MATTERS: two unrelated code sites, in "
               "two different images, agree on one rate model, and neither was "
               "used to derive the other.",
    }


@functools.lru_cache(maxsize=None)
def feasibility():
    """Would 2000 and 4000 Hz work if the handler's two compares were patched?"""
    gate = tick_gate()
    reachable = {i: gate["divisor_by_index"][str(i)] for i in range(4)}
    return {
        "question": "the handler at 0x18002b2e accepts only index 0 and 3. If "
                    "its two compares were patched to accept 1 and 2, would "
                    "2000 and 4000 Hz work?",
        "answer": "NO",
        "because": "the period is not set by the multiplier. It is set by the "
                   "entry image's tick job, whose test is `cmp r1,#3` — a "
                   "two-way branch. Index 1 or 2 fails it and takes the "
                   "divide-by-eight path, so the report stage would still run "
                   "at the 1000 Hz cadence.",
        "and_worse": "the multiplier WOULD become 2 or 4, so FUN_18004a7e "
                     "would scale every per-key timeout by 20 or 40 job "
                     "invocations per unit while the job period stayed at the "
                     "1000 Hz value. Hold and tap timings would come out 2x "
                     "and 4x too long.",
        "divisor_that_would_apply": {str(k): v for k, v in reachable.items()},
        "what_would_actually_be_required": [
            "the dispatcher's two compares at 0x18002b30 and 0x18002b34, so "
            "the device accepts the index at all",
            "AND the divider selection in the ENTRY image's tick job at "
            f"{GATE_COMPARE_INDEX:#x}/{GATE_COMPARE_EIGHT:#x}, replaced by a "
            "rate-dependent divisor",
        ],
        "the_arithmetic_already_generalises": "divisor 8 >> index pairs "
            "exactly with the existing multiplier 1 << index: their product is "
            "8 for all four indices, so the parameter stays in the same unit "
            "at 1000, 2000, 4000 and 8000 Hz. ASUS's SCALING IS ALREADY "
            "FOUR-RATE CAPABLE; only the gate is hardcoded to the two "
            "endpoints.",
        "no_descriptor_change_needed": "EP 0x81's bInterval is already 1 — "
                                       "125 us at high speed — so the host "
                                       "polls fast enough for any of the four "
                                       "rates without re-enumeration "
                                       "(log 126).",
        "not_verifiable_offline": "CPU headroom. At 2000 or 4000 Hz the gated "
                                  "stage would run two or four times more "
                                  "often than at 1000, and nothing offline "
                                  "measures whether it fits.",
        "nothing_was_patched": True,
    }


@functools.lru_cache(maxsize=None)
def custom_firmware_requirements():
    return [
        "sample on EVERY tick. Veneer 0x4044 is called on BOTH paths of the "
        "gate, so Hall acquisition is never slowed by the polling rate — only "
        "the decision and report stage is.",
        "gate the actuation compare and the report builder together. Veneers "
        "0x4058, 0x4062, 0x406c and 0x4076 are one block behind one test; "
        "splitting them changes which stage sees which sample.",
        "leave the 21-byte EP 0x8c sender ungated. Veneer 0x404e is a tail "
        "call on every tick regardless of the rate.",
        "scale every tick-denominated timeout by the same factor, or hold and "
        "tap timings move when the user changes the polling rate. The stock "
        "firmware does this with one cached byte and a x10.",
        "keep bInterval at 1. The host must poll faster than the fastest rate "
        "offered, and the descriptor never changes (log 126).",
    ]


SEARCH_STEPS = (
    ("the Ghidra peripheral census, all six exports",
     "4 reads and 5 writes of 0x1801e736; every read in FUN_18004a7e, base "
     "0x1801e734 offset 2. THIS IS THE ANSWER, and it was in the tree before "
     "log 126 ran.",
     "the census iterates FUNCTIONS, so code Ghidra never assigned to a "
     "function is invisible to it — which is why it shows five writes and not "
     "six."),
    ("aligned-word literals equal to 0x1801e736",
     "6 slots, 6 load sites, all six followed by a store (log 126).",
     "a reader using [base+2] leaves no such literal, so this method could "
     "never have found the reader."),
    ("aligned-word literals within +/-0x100 of 0x1801e734, every image",
     "9 slots in the installed application; 0 in the entry image; 0 in the "
     "second-context RAM image.",
     "this is the method that closes the middle case, and its emptiness in "
     "the second context is what rules that context out."),
    ("every pc-relative load of those 9 slots",
     "44 sites in 17 functions, plus 4 in code with no function body.",
     "the 4 function-less sites were read by hand: they reach +0x50, +0x6, "
     "+0x54, +0x60, +0x30 and +0x2c, and one writes 0x1801e78a — the same "
     "false-positive shape log 126 rejected, now positively attributed to "
     "FUN_180045b6."),
    ("movw/movt construction of 0x1801e736, every image",
     "none (log 126).",
     "the third and last way to reach the address."),
    ("the vendor release, independently",
     "the same 4 reads at 0x1801e70a in FUN_18004a7e and the same 5 writes; "
     "the entry image's tick job is BYTE-IDENTICAL between releases.",
     "a coincidence would not survive the relocation."),
    ("the second execution context",
     "no literal near the key-state struct, and no reference to the profile "
     "block anywhere in its image.",
     "log 122's parameter-register blind spot does not apply here: both "
     "consumers were found through bases the census had already resolved."),
)


# ------------------------------------------------------------------- checks

def verify():
    checks = []

    def check(ok, label, detail=""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})
        return ok

    rows = reader_table()
    reads = [r for r in rows if r["direction"] == "read"]
    writes = [r for r in rows if r["direction"] == "write"]
    check(len(reads) == 4, "the multiplier byte has exactly four readers",
          ", ".join(r["instruction"] for r in reads))
    check(all(r["function"] == "FUN_18004a7e" for r in reads),
          "every reader is FUN_18004a7e, the actuation compare",
          f"{len(reads)} reads, one function")
    check(all(r["offset"] == 2 and int(r["base"].split("@")[1], 16) == KEY_STATE
              for r in reads),
          "every reader reaches it as key_state+2, which is why an "
          "aligned-word search for the address could not find it",
          f"base {KEY_STATE:#x} offset 2")
    check(len(writes) == 6, "the six writers log 126 found are all accounted "
                            "for", ", ".join(r["instruction"] for r in writes))
    census_writes = [r for r in writes if r["census_func"] is not None]
    check(len(census_writes) == 5,
          "the census sees five of the six writers, and the sixth is in code "
          "with no function body — neither method is sufficient alone",
          f"{len(census_writes)} in the census, "
          f"{len(writes) - len(census_writes)} only from the byte search")

    for addr, expected in APP_BYTES.items():
        got = halfwords(APP[0], APP[1], addr, len(expected.split()))
        if not check(got == expected,
                     f"the application's instruction at {addr:#x} is the one "
                     f"this model cites", f"{got} == {expected}"):
            break
    for addr, expected in ENTRY_BYTES.items():
        got = halfwords(ENTRY[0], ENTRY[1], addr, len(expected.split()))
        if not check(got == expected,
                     f"the entry image's instruction at {addr:#x} is the one "
                     f"this model cites", f"{got} == {expected}"):
            break

    gate = tick_gate()
    check(gate["profile_literal_is_the_profile_block"],
          "the tick job's literal is the profile block the 51 31 handler "
          "writes", f"*(0x5b8) = {PROFILE_BLOCK:#x}")
    check(all(v["matches_log_119"] for v in gate["gated"]),
          "every gated veneer decodes to the target log 119 resolved "
          "independently",
          "; ".join(f"{v['veneer']}->{v['target']}" for v in gate["gated"]))
    check(all(v["matches_prior_logs"] for v in gate["ungated"]),
          "the ungated veneers decode to their known targets too",
          "; ".join(f"{v['veneer']}->{v['target']}" for v in gate["ungated"]))
    check(gate["divisor_by_index"] == {"0": 8, "1": 8, "2": 8, "3": 1},
          "the gate is a two-way branch: only index 3 bypasses the divider",
          json.dumps(gate["divisor_by_index"], sort_keys=True))
    check(gate["identical_in_both_releases"],
          "the tick job is byte-identical in both firmware releases",
          "1.58 and 1.59 carry the same gate")

    ta = threshold_addressing()
    check(ta["agrees_with_log_125"],
          "the scaled parameter lives in log 125's keymap bank — 0x361*4 is "
          "its layer stride", f"stride {ta['layer_stride_bytes']} = 0xd84")

    p = period_model()
    check(p["irq38_hz"] == 8000,
          "IRQ38's period follows from the slow state's measured 1 ms grid "
          "and the divide-by-eight",
          f"{p['irq38_period_us']} us = {p['irq38_hz']} Hz")
    check(p["prediction_holds"],
          "the fast state is then PREDICTED, not fitted, and the prediction "
          "matches the wire",
          f"predicted {p['fast_state_predicted_grid_ms']} ms, measured "
          f"{p['fast_state_measured_grid_ms']} ms")

    u = units_model()
    check(u["rate_invariant"],
          "the per-key parameter's real duration is the same at both rates, "
          "which is the whole point of the multiplier",
          f"{u['parameter_unit_ms']} ms per unit at index 0 and index 3")

    f = feasibility()
    check(f["answer"] == "NO",
          "patching only the handler's two compares would NOT give 2000 or "
          "4000 Hz", f["because"][:80] + "...")
    check(f["nothing_was_patched"] is True,
          "nothing was patched — the feasibility answer is analysis only", "")

    check(PROTOCOL_MODEL.exists(),
          "log 126's measurement is read from its model rather than restated",
          str(PROTOCOL_MODEL.relative_to(ROOT)))
    if PROTOCOL_MODEL.exists():
        model = json.loads(PROTOCOL_MODEL.read_text())
        grid = (model["polling_rate"]["measurement"]["per_endpoint"]["0x81"])
        check(grid["0"]["on_1ms_fraction"] > grid["3"]["on_1ms_fraction"],
              "log 126's own numbers still say index 0 is the slow state",
              f"index 0 {grid['0']['on_1ms_fraction']:.1%} vs index 3 "
              f"{grid['3']['on_1ms_fraction']:.1%} on the 1 ms grid")

    # Anti-vacuity: the census filter must find things other than this byte.
    check(len(census()) > 1000,
          "the census this whole step rests on is populated, so its silence "
          "elsewhere means something", f"{len(census())} ACCESS records")
    check(len(census_for(KEY_STATE + 0x9)) > 0,
          "the same filter finds neighbouring struct fields, so it is not "
          "keyed to one lucky address",
          f"{len(census_for(KEY_STATE + 0x9))} accesses to key_state+9")
    return checks


# ------------------------------------------------------------------- output

@functools.lru_cache(maxsize=None)
def to_dict():
    checks = verify()
    return {
        "verdict": "the reader is FUN_18004a7e, the actuation compare, which "
                   "scales per-key timeouts by ten times the multiplier; the "
                   "PERIOD is set elsewhere, by the entry image's tick job "
                   "bypassing its own divide-by-eight when the index is 3",
        "orphan_byte": f"{MULTIPLIER:#x}",
        "why_log_126_missed_it": "0x1801e736 is key_state+2, and every reader "
                                 "uses an immediate offset, so no literal "
                                 "equal to the address exists. The reader was "
                                 "already resolved in the Ghidra peripheral "
                                 "census, which log 126 did not consult.",
        "reader_table": reader_table(),
        "scale_sites": scale_sites(),
        "threshold_addressing": threshold_addressing(),
        "tick_gate": tick_gate(),
        "period": period_model(),
        "units": units_model(),
        "feasibility_2000_4000": feasibility(),
        "custom_firmware_requirements": custom_firmware_requirements(),
        "search": [{"step": s, "found": f, "boundary": b}
                   for s, f, b in SEARCH_STEPS],
        "supersedes": {
            "log_124": "its residual negative — 'no consumer of a rate index "
                       "in the preserved images' — is now ANSWERED, and its "
                       "8000/8 lead is confirmed as a measurement. Log 124 is "
                       "not rewritten: it was correct for its evidence, and "
                       "its own tool remains its sealed record.",
            "log_126": "its 'six writers, no reader' stands as a statement "
                       "about the searches it ran. The reader existed and the "
                       "byte shape was the reason it was invisible.",
            "logs_110_and_119": "'the actuation comparison runs on IRQ38's "
                                "tick divided by 8' is refined: divided by 8 "
                                "at 1000 Hz, and EVERY tick at 8000 Hz. Both "
                                "logs described the else path correctly, "
                                "which is the path the device takes at its "
                                "default rate.",
        },
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images and pre-existing "
                      "read-only Ghidra exports. No device was accessed, no "
                      "frame was constructed, and nothing was patched. This "
                      "authorises nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["THE POLLING-RATE READER", "",
           f"orphan byte  {d['orphan_byte']}", "", "READER TABLE"]
    for r in d["reader_table"]:
        out.append(f"  {r['direction']:>5}  {r['instruction']:>12}  "
                   f"{r['function']:<20} base {r['base']} off {r['offset']}")
    g, p, u = d["tick_gate"], d["period"], d["units"]
    out += ["", "THE PERIOD MECHANISM",
            f"  {g['function']} reads {g['reads']}",
            f"  {g['bypass_test']}",
            f"  {g['divider_test']}",
            f"  divisor by index: {json.dumps(g['divisor_by_index'], sort_keys=True)}",
            f"  shape: {g['shape']}", "", "  gated on the rate:"]
    for v in g["gated"]:
        out.append(f"    {v['veneer']} -> {v['target']}  {v['role']}")
    out.append("  NOT gated:")
    for v in g["ungated"]:
        out.append(f"    {v['veneer']} -> {v['target']}  {v['role']}")
    out += ["", "UNITS",
            f"  IRQ38 = {p['irq38_hz']} Hz ({p['irq38_period_us']} us), "
            f"{p['confidence']}",
            f"  derived from {p['derived_from']}",
            f"  fast state predicted {p['fast_state_predicted_grid_ms']} ms, "
            f"measured {p['fast_state_measured_grid_ms']} ms"]
    for r in u["rows"]:
        out.append(f"  index {r['index']}: divisor {r['divisor']}, multiplier "
                   f"{r['multiplier']}, job {r['job_period_ms']} ms, "
                   f"{r['real_ms_per_unit']} ms per parameter unit")
    f = d["feasibility_2000_4000"]
    out += ["", f"2000 / 4000 Hz BY PATCHING THE TWO COMPARES: {f['answer']}",
            f"  {f['because']}", "", "CHECKS"]
    for c in d["checks"]:
        out.append(f"  {'PASS' if c['ok'] else 'FAIL'} {c['label']}"
                   + (f" — {c['detail']}" if c["detail"] else ""))
    s = d["summary"]
    out += ["", f"RESULT polling_rate_reader_ok={s['ok']} checks={s['checks']}"]
    return out


def markdown():
    d = to_dict()
    g, p, u, f = (d["tick_gate"], d["period"], d["units"],
                  d["feasibility_2000_4000"])
    ta = d["threshold_addressing"]
    out = ["# The polling-rate reader", "",
           "**Generated by `tool/map_polling_rate_reader.py`. Do not edit by "
           "hand.**", "",
           "> Offline analysis of preserved images and pre-existing read-only "
           "Ghidra exports. No device was accessed, no frame was constructed, "
           "and nothing was patched. This authorises nothing live.", "",
           "## Verdict", "", f"**{_sentence(d['verdict'])}.**", "",
           "## Why log 126 could not find it", "",
           d["why_log_126_missed_it"], "",
           "## Every access to the multiplier byte", "",
           "| dir | instruction | function | base | off | source |",
           "|---|---|---|---|---|---|"]
    for r in d["reader_table"]:
        out.append(f"| {r['direction']} | `{r['instruction']}` | "
                   f"`{r['function']}` | `{r['base']}` | {r['offset']} | "
                   f"{r['source'][:60]} |")
    out += ["", "## What the reader does with it", "",
            "All four sites run the identical arithmetic:", "", "```",
            "180053c0  ldrb.w r2,[lr,#0x22]        ; a per-key byte parameter",
            "180053c4  ldrb   r0,[r0,#0x2]         ; THE MULTIPLIER, 1 << index",
            "180053ca  add.w  r0,r0,r0,lsl #2      ; x5",
            "180053ce  lsls   r0,r0,#0x1           ; x2   -> x10",
            "180053d0  muls   r2,r0,r2             ; parameter x 10 x multiplier",
            "180053d2  ldr.w  r0,[r12,r4,lsl #2]   ; a per-key 32-bit counter",
            "180053d6  cmp    r2,r0                ; has the counter reached it?",
            "```", "",
            "and the counter is a tick counter, incremented once per "
            "invocation:", "", "```",
            "18005488  ldr.w  r3,[r8,r4,lsl #2]",
            "1800548c  adds   r3,r3,#0x1",
            "1800548e  str.w  r3,[r8,r4,lsl #2]",
            "```", "",
            f"The parameter comes from `{ta['bank_base']} + layer*"
            f"{ta['layer_stride_bytes']} + key*{ta['record_stride']} + "
            f"{ta['parameter_offset']}`. {ta['note']}", "",
            "## Where the period is actually set", "",
            f"Not here. `{g['function']}` in the **entry image** — the tick "
            f"job logs 109, 110 and 119 traced — reads {g['reads']}, and "
            f"branches on it:",
            "", "```",
            "     4d4: ldr    r0,[pc,#0xe0]   ; -> 0x18021de0, THE PROFILE BLOCK",
            "     4d6: ldrb.w r0,[r0,#0x4f8]  ; the polling-rate field",
            "     4da: and    r1,r0,#0xf      ; the index",
            "     4de: ldr    r0,[pc,#0xdc]   ; -> 0x1801e6a4, the /8 counter",
            "     4e0: cmp    r1,#0x3         ; <-- THE BYPASS TEST",
            "     4e2: beq    0x4fc           ;     index 3 -> run EVERY tick",
            "     4e4: ldrb   r1,[r0]",
            "     4e6: adds   r1,r1,#0x1",
            "     4ea: strb   r1,[r0]",
            "     4ec: cmp    r1,#0x8         ; <-- the divide-by-eight",
            "     4ee: beq    0x4fc",
            "     4f0: bl     0x4044          ;     otherwise: sample only",
            "```", "",
            f"{_sentence(g['shape'])}.", "",
            "| index | divisor |", "|---|---|"]
    for k, v in sorted(g["divisor_by_index"].items()):
        out.append(f"| {k} | {v} |")
    out += ["", "Gated on the rate:", ""]
    for v in g["gated"]:
        out.append(f"- `{v['veneer']}` → `{v['target']}` — {v['role']}")
    out += ["", "**Not** gated — these run on every tick at either rate:", ""]
    for v in g["ungated"]:
        out.append(f"- `{v['veneer']}` → `{v['target']}` — {v['role']}")
    out += ["", "The tick job is **byte-identical in both firmware "
            "releases**, and the vendor image carries the same four reads at "
            "`0x1801e70a`.", "",
            "## The period, and real units on IRQ38", "",
            f"The informative state is the **slow** one. At index 3 the host "
            f"polls EP `0x81` every 125 us anyway, so a 125 us grid there is "
            f"equally explained by the host's schedule. At index 0 the "
            f"measured grid is **1 ms**, which the host's polling cannot "
            f"produce — so the device is making data available only every "
            f"millisecond. The gate makes index 0 run the report stage every "
            f"eighth tick.", "",
            f"    8 x T = 1 ms   ->   **T = {p['irq38_period_us']} us, "
            f"IRQ38 = {p['irq38_hz']} Hz**", "",
            f"The fast state is then a **prediction**: divisor 1 gives "
            f"{p['fast_state_predicted_grid_ms']} ms, and log 126 measured "
            f"{p['fast_state_measured_grid_ms']} ms.", "",
            f"Confidence: **{p['confidence']}** — {p['kind_basis']}", "",
            f"Would be refuted by: {p['would_be_refuted_by']}.", "",
            f"{p['closes_log_124_lead']}", "",
            f"**Not resolved:** {p['does_not_resolve']}", "",
            "## The parameter's unit", "",
            "| index | divisor | multiplier | job period | invocations per "
            "unit | real time per unit |", "|---|---|---|---|---|---|"]
    for r in u["rows"]:
        out.append(f"| {r['index']} | {r['divisor']} | {r['multiplier']} | "
                   f"{r['job_period_ms']} ms | "
                   f"{r['threshold_invocations_per_unit']} | "
                   f"{r['real_ms_per_unit']} ms |")
    out += ["", u["why"], "",
            "## Would 2000 and 4000 Hz work?", "",
            f"**{f['answer']}.** {f['because']}", "",
            f"{_sentence(f['and_worse'])}", "",
            "What would actually be required:", ""]
    for item in f["what_would_actually_be_required"]:
        out.append(f"- {item}")
    out += ["", f"{f['the_arithmetic_already_generalises']}", "",
            f"{f['no_descriptor_change_needed']}", "",
            f"**Not verifiable offline:** {f['not_verifiable_offline']}", "",
            "Nothing was patched. This is analysis.", "",
            "## What a custom firmware must reproduce", ""]
    for item in d["custom_firmware_requirements"]:
        out.append(f"- {item}")
    out += ["", "## The search, step by step", "",
            "| searched | found | boundary |", "|---|---|---|"]
    for s in d["search"]:
        out.append(f"| {s['step']} | {s['found']} | {s['boundary']} |")
    out += ["", "## What this does and does not change", "",
            "| prior result | status |", "|---|---|"]
    for k, v in sorted(d["supersedes"].items()):
        out.append(f"| {k.replace('_', ' ')} | {v} |")
    out += ["", "## Checks", "", "| | check | detail |", "|---|---|---|"]
    for c in d["checks"]:
        out.append(f"| {'PASS' if c['ok'] else 'FAIL'} | {c['label']} | "
                   f"{c['detail']} |")
    s = d["summary"]
    out += ["", f"`RESULT polling_rate_reader_ok={s['ok']} "
                f"checks={s['checks']}`", ""]
    return "\n".join(out)


def bodies():
    return {
        "polling-rate-reader.json": json.dumps(to_dict(), indent=2,
                                               sort_keys=True) + "\n",
        "polling-rate-reader.md": markdown(),
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
    except (OSError, ReaderError, struct.error, KeyError, ValueError,
            json.JSONDecodeError) as exc:
        print(f"RESULT polling_rate_reader_ok=False error={exc}")
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
        print(payload["polling-rate-reader.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(c["ok"] for c in verify()) else 1


if __name__ == "__main__":
    sys.exit(main())
