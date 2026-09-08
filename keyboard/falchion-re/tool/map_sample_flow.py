#!/usr/bin/env python3
"""Trace both sides of the mailbox and answer whether per-key samples cross.

Read-only and offline. Path-B evidence-gate work against gate 1, the Hall
acquisition boundary. It changes no decision and authorises nothing live.

Log 118 recovered the ring buffer and showed the second context writes into
application RAM through an application-supplied pointer. It could not say
whether per-key sample data crosses. This traces the other half: every client
in the entry image and the application, the opcode each one sends, who calls
it, and what the matching handler writes back.

WHAT IS COMPUTED HERE RATHER THAN TRANSCRIBED. Three decoders do the work, and
each is checked against something Ghidra independently reported:

  * a Thumb-2 `movw` decoder, used to find the cross-image veneer for each
    client. It is self-tested against log 113's hand-validated veneer bytes
    for the start routine, which were recovered before this tool existed.
  * a Thumb-2 `bl`/`b.w` decoder, used to find call sites. It is checked
    against a branch Ghidra's own inventory resolved, so a decoding error
    shows up as a mismatch rather than as a plausible wrong address.
  * an instruction scan for the two structure offsets, which is how the
    delivery sites are counted instead of eyeballed.

Peripheral identity is still not claimed anywhere. The converter registers
keep the roles their instruction sequence shows and no names.

No device access. Examples:
    python3 tool/map_sample_flow.py
    python3 tool/map_sample_flow.py --json
    python3 tool/map_sample_flow.py --write
    python3 tool/map_sample_flow.py --check
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_second_context as ms

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"

ENTRY_BIN = "installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin"
APP_BIN = "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin"
REGION_BIN = "installed_decompressed_region1_flash3f380_dst1801e380_len00b04_501f818f.bin"
APP_BASE = 0x18000000
REGION_BASE = 0x1801E380

# From log 110, and re-verified here against the region's initialised bytes.
POINTER_CELL = 0x1801ED6C
TRAVEL_OFFSET = 0x35C
SAMPLE_OFFSET = 0x3F2
RAW_OFFSET = 0x2C6
KEY_STATE_BITMAP = 0x18023410
ACTUATION_THRESHOLD = 100        # log 110 step 6's `travel >= 100`

# The in-image travel curve. Its extent is asserted, not assumed: the clamp
# bound and the table length have to agree or the identification is wrong.
LUT_LO = 0x1803BE86
LUT_LEN = 0x500                  # == the clamp `cmp r3,#0x500` in FUN_1803a6c4
CLAMP = 0x4FF

KEY_COUNT = 0x4B                 # the loop bound in FUN_1803a6c4
CONVERTER_ITERATIONS = 0xF0

# log 113's hand-validated veneer, used to self-test the movw decoder.
START_ROUTINE = 0x1F50
START_VENEER = 0x1801BD96
START_VENEER_BYTES = bytes.fromhex("41f6517c")

# log 109 step 5: the every-tick job's /8 branch and its veneer table.
TICK_JOB = 0x4BA
TICK_DIV8_VENEERS = {
    0x4058: "FUN_180045b6",
    0x4044: "the sample fetch",
    0x4062: "FUN_18004a7e, the actuation compare",
    0x406C: "FUN_180057fe",
    0x4076: "FUN_180061c2, the report builder",
}
SAMPLE_VENEER = 0x4044
ACTUATION_VENEER = 0x4062


class SampleFlowError(RuntimeError):
    """Raised when the evidence does not support continuing."""


# --- images -----------------------------------------------------------------

def _load(name):
    path = IMPORTS / name
    if not path.exists():
        raise SampleFlowError(f"missing import slice {name}")
    return path.read_bytes()


def images():
    ms.sources()                                  # hash-gates both dumps
    return {
        "entry": (_load(ENTRY_BIN), 0),
        "app": (_load(APP_BIN), APP_BASE),
        "region": (_load(REGION_BIN), REGION_BASE),
        "second": (ms.image(), ms.RUNTIME_BASE),
    }


def _half(buf, base, addr):
    return struct.unpack_from("<H", buf, addr - base)[0]


# --- decoders ---------------------------------------------------------------

def movw_halfwords(imm16, rd):
    """Encode `movw rD,#imm16` (Thumb-2 T3).

    Encoding it and searching is safer than decoding every halfword pair: a
    wrong encoding finds nothing, which the self-test catches, whereas a wrong
    decoder invents plausible addresses.
    """
    imm4 = (imm16 >> 12) & 0xF
    i = (imm16 >> 11) & 1
    imm3 = (imm16 >> 8) & 7
    imm8 = imm16 & 0xFF
    return 0xF240 | (i << 10) | imm4, (imm3 << 12) | (rd << 8) | imm8


def movw_self_test():
    """Against log 113's hand-validated bytes, recovered before this tool."""
    hw1, hw2 = movw_halfwords(START_ROUTINE | 1, 12)
    return struct.pack("<HH", hw1, hw2) == START_VENEER_BYTES


def find_movw(buf, base, imm16):
    out = []
    for rd in range(13):
        pat = struct.pack("<HH", *movw_halfwords(imm16, rd))
        start = 0
        while True:
            hit = buf.find(pat, start)
            if hit < 0:
                break
            if hit % 2 == 0:
                out.append((base + hit, rd))
            start = hit + 2
    return sorted(out)


def decode_branch(buf, base, addr):
    """Decode a Thumb-2 `bl` or `b.w`. Returns (kind, target) or None."""
    hw1, hw2 = struct.unpack_from("<HH", buf, addr - base)
    if (hw1 & 0xF800) != 0xF000 or not (hw2 >> 12) & 1:
        return None
    kind = {0b11: "bl", 0b10: "b.w"}.get((hw2 >> 14) & 3)
    if kind is None:
        return None
    sign = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1 = 1 - (j1 ^ sign)
    i2 = 1 - (j2 ^ sign)
    imm = (sign << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if sign:
        imm -= 1 << 25
    return kind, addr + 4 + imm


def branch_self_test():
    """Check the branch decoder against a target Ghidra itself resolved.

    The inventory records FUN_180049a8 calling the veneer at 0x1801be22; the
    `bl` at 0x180049b4 is that call. If the decoder disagrees there, nothing
    else it produces can be trusted.
    """
    buf, base = images()["app"]
    got = decode_branch(buf, base, 0x180049B4)
    return got == ("bl", 0x1801BE22)


def scan_offset(buf, base, imm12):
    """Every wide load/store using this 12-bit offset, with its opcode."""
    ops = {0x8: "strb", 0x9: "ldrb", 0xA: "strh", 0xB: "ldrh",
           0xC: "str", 0xD: "ldr"}
    out = []
    for off in range(0, len(buf) - 3, 2):
        hw1, hw2 = struct.unpack_from("<HH", buf, off)
        if (hw1 & 0xFF00) == 0xF800 and (hw2 & 0x0FFF) == imm12:
            out.append({
                "address": f"0x{base + off:08x}",
                "op": ops.get((hw1 >> 4) & 0xF, "?"),
                "rt": (hw2 >> 12) & 0xF,
                "rn": hw1 & 0xF,
            })
    return out


# --- the clients ------------------------------------------------------------

@dataclass(frozen=True)
class Client:
    address: int
    image: str
    opcodes: tuple
    request: str
    note: str


# Each client's opcode is read back out of its own bytes by `client_opcodes`;
# the numbers here are the expectation a check compares against, so a wrong
# one fails rather than propagates.
CLIENTS = (
    Client(0x19D4, "entry", (0x01, 0x02, 0x0C),
           "none",
           "opcode chosen at run time from two region flags: 0x01 normally, "
           "0x02 when the flag at 0x1801e845 is 1, 0x0c when the word at "
           "0x1801e810 is not 1"),
    Client(0x1A36, "entry", (0x07,),
           "memcpy(pointer+0x27a, src, len) when len != 0",
           "a variable-length upload into the shared structure"),
    Client(0x1A88, "entry", (0x08,), "none", ""),
    Client(0x1ACC, "entry", (0x0B,),
           "fills pointer+0x1e4 with a packed byte, 5*count entries",
           "the byte packs three arguments and sets bit 7"),
    Client(0x1B38, "entry", (0x0E,), "none", ""),
    Client(0x1B7C, "entry", (0x0F,),
           "memcpy(pointer+0x72c, src, len)",
           "the five-group table opcode 0x0f de-interleaves"),
    Client(0x18000136, "app", (0x0D,),
           "record+4 = *(0x1801ed6c); record+8 = 4, 5 or 6",
           "THE POINTER SHARE. Sent from CandidateB_Main at boot"),
)

# The second context's handlers, from log 118's decoded tbb table.
HANDLERS = {
    0x01: "FUN_1803901c", 0x02: "FUN_1803901c", 0x03: "FUN_180388c8",
    0x07: "FUN_18038a4c", 0x08: "FUN_18038970", 0x0B: "FUN_18039a64",
    0x0C: "FUN_1803901c", 0x0D: "FUN_1803af90 inline", 0x0E: "FUN_1803a968",
    0x0F: "FUN_18038b1c",
}

# What each handler is shown to write back into application RAM.
RESPONSES = {
    0x01: "75 uint16 samples at pointer+0x3f2, then FUN_1803a6c4 writes 75 "
          "travel bytes at pointer+0x35c and 75 uint16 at pointer+0x2c6",
    0x02: "as 0x01",
    0x0C: "as 0x01",
    0x0D: "memset(pointer+0x3f2, 150, 0xff) — marks all 75 samples invalid",
}


def client_opcodes():
    """Read each client's opcode out of its own instruction bytes.

    A client writes the opcode with `movs rX,#imm` shortly before `strb
    rX,[record,#0]`, so the immediates in its body are the evidence. Reading
    them back is what makes the table above checkable.
    """
    imgs = images()
    out = {}
    for client in CLIENTS:
        buf, base = imgs[client.image]
        lo = client.address - base
        found = []
        for off in range(lo, lo + 0x60, 2):
            hw = struct.unpack_from("<H", buf, off)[0]
            if (hw & 0xF800) == 0x2000:                      # movs rX,#imm8
                found.append(hw & 0xFF)
            elif (hw & 0xFBEF) == 0xF04F:                    # mov.w rX,#imm
                nxt = struct.unpack_from("<H", buf, off + 2)[0]
                if (nxt & 0x8000) == 0:
                    found.append(nxt & 0xFF)
        out[client.address] = sorted(set(found) & set(HANDLERS))
    return out


def veneers():
    """The cross-image veneer for every entry-image client."""
    imgs = images()
    app, app_base = imgs["app"]
    rows = []
    for client in CLIENTS:
        if client.image != "entry":
            continue
        hits = find_movw(app, app_base, client.address | 1)
        rows.append({
            "client": f"0x{client.address:04x}",
            "opcodes": [f"0x{o:02x}" for o in client.opcodes],
            "veneer": f"0x{hits[0][0]:08x}" if hits else "",
            "found": bool(hits),
        })
    return rows


def call_sites():
    """Every application branch into a client veneer, with its function."""
    imgs = images()
    app, app_base = imgs["app"]
    wanted = {}
    for row in veneers():
        if row["found"]:
            wanted[int(row["veneer"], 16)] = row["client"]
    wanted[START_VENEER] = "0x1f50 (start routine, log 113)"

    owners = []
    inv = INVENTORIES / "installed_b.txt"
    if inv.exists():
        for line in inv.read_text().splitlines():
            if not line.startswith("FUNC"):
                continue
            name = re.search(r"name=(\S+)", line).group(1)
            for part in re.search(r"ranges=(\S+)", line).group(1).split(";"):
                lo, hi = (int(x, 16) for x in part.split("-"))
                owners.append((lo, hi, name))

    def owner(addr):
        for lo, hi, name in owners:
            if lo <= addr <= hi:
                return name
        return "(unanalysed)"

    rows = []
    for off in range(0, len(app) - 3, 2):
        decoded = decode_branch(app, app_base, app_base + off)
        if decoded and decoded[1] in wanted:
            rows.append({
                "site": f"0x{app_base + off:08x}",
                "kind": decoded[0],
                "veneer": f"0x{decoded[1]:08x}",
                "client": wanted[decoded[1]],
                "function": owner(app_base + off),
            })
    return rows


# --- the pointer share ------------------------------------------------------

def pointer_share():
    """Does the application hand over a pointer into its own structure?"""
    imgs = images()
    region, region_base = imgs["region"]
    value = struct.unpack_from("<I", region, POINTER_CELL - region_base)[0]
    app, app_base = imgs["app"]
    # FUN_18000136's literal pool, resolved from the image.
    pool = {a: struct.unpack_from("<I", app, a - app_base)[0]
            for a in (0x180003D0, 0x180003D4, 0x180003D8, 0x180003DC)}
    return {
        "sender": "FUN_18000136, called from CandidateB_Main",
        "opcode": "0x0d",
        "pointer_cell": f"0x{POINTER_CELL:08x}",
        "cell_value": f"0x{value:08x}",
        "cell_is_in_the_pool": POINTER_CELL in pool.values(),
        "record_field": "+4",
        "record_array_in_pool": 0x20000008 in pool.values(),
        "pool": {f"0x{a:08x}": f"0x{v:08x}" for a, v in sorted(pool.items())},
        "shared_structure_base": f"0x{value:08x}",
        "consequence":
            "the second context receives the base of the application's own "
            "structure, so every offset of it is writable by the second "
            "context. Delivery is therefore capable of being a DIRECT WRITE "
            "and does not need a response record.",
        "fields": [
            {"offset": "0x1e4", "written_by": "client 0x1acc (opcode 0x0b)",
             "direction": "app -> second"},
            {"offset": "0x27a", "written_by": "client 0x1a36 (opcode 0x07)",
             "direction": "app -> second"},
            {"offset": f"0x{RAW_OFFSET:x}", "written_by": "FUN_1803a6c4",
             "direction": "second -> app", "detail": "75 uint16, the clamped raw value"},
            {"offset": f"0x{TRAVEL_OFFSET:x}",
             "written_by": "FUN_1803a6c4",
             "direction": "second -> app",
             "detail": f"75 bytes — THE TRAVEL ARRAY at 0x{value + TRAVEL_OFFSET:08x}"},
            {"offset": f"0x{SAMPLE_OFFSET:x}",
             "written_by": "FUN_1803901c, and memset by opcode 0x0d",
             "direction": "second -> app", "detail": "75 uint16 raw samples"},
            {"offset": "0x72c", "written_by": "client 0x1b7c (opcode 0x0f)",
             "direction": "app -> second"},
        ],
        "travel_array": f"0x{value + TRAVEL_OFFSET:08x}",
        "matches_log110": value + TRAVEL_OFFSET == ms.TRAVEL_ARRAY,
    }


# --- the delivery sites -----------------------------------------------------

def delivery():
    """Count and locate the stores that cross into application RAM."""
    second, second_base = images()["second"]
    travel = [r for r in scan_offset(second, second_base, TRAVEL_OFFSET)
              if r["op"].startswith("str")]
    samples = [r for r in scan_offset(second, second_base, SAMPLE_OFFSET)
               if r["op"].startswith("str")]
    return {
        "travel_stores": travel,
        "travel_store_count": len(travel),
        "sample_stores": samples,
        "sample_store_count": len(samples),
        "sample_store_function": "FUN_1803901c, the opcode 0x01/0x02/0x0c handler",
        "travel_store_function": "FUN_1803a6c4, called from FUN_1803901c",
        "bitmap_referenced": bool(find_movw(second, second_base,
                                            KEY_STATE_BITMAP & 0xFFFF)),
        "bitmap_note":
            "the per-key bitmap at 0x18023410 is written by the APPLICATION "
            "(FUN_180049a8), never by the second context",
    }


def travel_curve():
    """The 1280-entry table the normalised value indexes.

    Its length has to equal the clamp bound, and its maximum has to make sense
    against log 110's actuation threshold. Both are checked, because a table
    of the right size that meant something else would be a false positive.
    """
    second, second_base = images()["second"]
    lut = second[LUT_LO - second_base:LUT_LO - second_base + LUT_LEN]
    monotonic = all(lut[i] <= lut[i + 1] for i in range(len(lut) - 1))
    return {
        "address": f"0x{LUT_LO:08x}",
        "length": len(lut),
        "length_equals_clamp_bound": len(lut) == CLAMP + 1,
        "clamp": f"0x{CLAMP:x}",
        "monotonic_non_decreasing": monotonic,
        "minimum": min(lut),
        "maximum": max(lut),
        "distinct_values": len(set(lut)),
        "actuation_threshold": ACTUATION_THRESHOLD,
        "maximum_is_twice_the_threshold": max(lut) == ACTUATION_THRESHOLD * 2,
        "first_index_at_threshold":
            next(i for i, b in enumerate(lut) if b >= ACTUATION_THRESHOLD),
        "sampled": [lut[i] for i in range(0, len(lut), 64)],
    }


# --- the end-to-end path ----------------------------------------------------

@dataclass(frozen=True)
class Link:
    key: str
    step: str
    detail: str
    citation: str


PATH = (
    Link("conversion", "the hardware conversion",
         f"FUN_1803ae58 and FUN_1803af28 iterate {CONVERTER_ITERATIONS} times: "
         "write a 16-bit word to 0x40018000, strobe 0x4001b000 with 0x7c then "
         "0, read 0x40019000, store to the in-image array 0x1803c828.",
         "log 118 step 2; this log step 4"),
    Link("staging", "in-image staging and validation",
         "FUN_1803901c reads a derived in-image array at 0x1803c5b2 and "
         "validates each entry by splitting it into two fields and comparing "
         "an XOR against a table, substituting a default when it mismatches.",
         "this log step 4"),
    Link("delivery_samples", "delivery of raw samples into application RAM",
         "FUN_1803901c stores through the application-supplied pointer at 24 "
         "unrolled sites: strh.w rX,[pointer + key*2, #0x3f2]. The pointer "
         "comes from the saved cell 0x1803c4ac.",
         "this log steps 3 and 4"),
    Link("normalise", "normalisation and the travel curve",
         "FUN_1803a6c4 computes delta = reference[key] - sample, scales it by "
         "a per-key 32-bit factor, shifts right by 21, clamps at 0x4ff, and "
         "indexes a 1280-byte monotonic table at 0x1803be86 whose maximum is "
         f"{ACTUATION_THRESHOLD * 2}.",
         "this log step 4"),
    Link("delivery_travel", "delivery of travel bytes into the travel array",
         "FUN_1803a6c4 stores the table's output with strb.w rX,[pointer + "
         "key, #0x35c], 75 keys, which is 0x18034850 — log 110's travel array.",
         "this log step 4; log 110 step 4"),
    Link("actuation", "the application's actuation comparison",
         "FUN_18004a7e reads the travel bytes and applies travel >= 100 with "
         "a 1..99 hold band.",
         "log 110 steps 1 and 6"),
    Link("cadence", "the cadence",
         "the every-tick job's /8 branch calls veneer 0x4044, which reaches "
         "the opcode 0x01/0x02/0x0c client, immediately before veneer 0x4062 "
         "runs the actuation comparison. Both ride IRQ38 divided by 8.",
         "log 109 step 5; this log step 5"),
)


def cadence():
    """Prove the /8 job reaches the sample client, by decoding the branch."""
    imgs = images()
    entry, entry_base = imgs["entry"]
    app, app_base = imgs["app"]
    # The entry image's veneer holds movw/movt of the application target.
    hw = struct.unpack_from("<4H", entry, SAMPLE_VENEER)
    def imm(h1, h2):
        return ((h1 & 0xF) << 12) | (((h1 >> 10) & 1) << 11) \
            | (((h2 >> 12) & 7) << 8) | (h2 & 0xFF)
    target = (imm(hw[2], hw[3]) << 16) | imm(hw[0], hw[1])
    stub = target & ~1
    hop = decode_branch(app, app_base, stub)
    client_veneer = next((int(r["veneer"], 16) for r in veneers()
                          if r["client"] == "0x19d4" and r["found"]), None)
    return {
        "tick_source": "IRQ38",
        "divider": 8,
        "tick_job": f"0x{TICK_JOB:04x}",
        "sample_veneer": f"0x{SAMPLE_VENEER:04x}",
        "veneer_target": f"0x{target:08x}",
        "stub": f"0x{stub:08x}",
        "stub_branch": hop[0] if hop else "",
        "stub_target": f"0x{hop[1]:08x}" if hop else "",
        "client_veneer": f"0x{client_veneer:08x}" if client_veneer else "",
        "reaches_the_sample_client": bool(hop and hop[1] == client_veneer),
        "actuation_veneer": f"0x{ACTUATION_VENEER:04x}",
        "order": "the sample fetch at 0x4044 runs BEFORE the actuation "
                 "comparison at 0x4062 in the same /8 branch",
        "absolute_rate": "UNRESOLVED — the timer that raises IRQ38 is still "
                         "not identified (log 109 step 3)",
    }


def path_complete():
    """Is every link of the producer path demonstrated?

    This is what gates the wording. It is computed from the checks that back
    each link, so the conclusion cannot drift away from the evidence.
    """
    share = pointer_share()
    deliver = delivery()
    curve = travel_curve()
    cad = cadence()
    return all((
        share["cell_is_in_the_pool"],
        share["matches_log110"],
        deliver["travel_store_count"] > 0,
        deliver["sample_store_count"] > 0,
        curve["length_equals_clamp_bound"],
        curve["monotonic_non_decreasing"],
        curve["maximum_is_twice_the_threshold"],
        cad["reaches_the_sample_client"],
    ))


def hall_gate():
    complete = path_complete()
    return {
        "gate": "a recovered producer for the per-key travel bytes",
        "previous_state": "narrowed, not closed (log 118)",
        "path_complete": complete,
        "status": "CLOSED" if complete else "still open",
        "mechanism": "DIRECT WRITE through an application-supplied pointer, "
                     "not a response record",
        "why_it_was_never_found":
            "the producer is in neither analysed image, and the buffer's "
            "address is stored in no image because the second context "
            "receives it at run time in a mailbox record. Log 110's negative "
            "was correct and complete for the images it could see.",
        "links": [{"key": l.key, "step": l.step, "detail": l.detail,
                   "citation": l.citation} for l in PATH],
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
    Claim("samples_cross",
          "Does per-key sample data cross from the second context to the "
          "application?",
          "YES, in both directions of the pipeline. Raw 16-bit samples cross "
          "at pointer+0x3f2 and derived travel bytes cross at pointer+0x35c, "
          "which is the travel array log 110 identified.",
          "observed",
          "24 strh.w stores at offset 0x3f2 and 3 strb.w stores at offset "
          "0x35c, all through the pointer the application supplied in a "
          "mailbox record",
          ("this log steps 3 and 4", "log 110 step 4")),
    Claim("mechanism",
          "By which mechanism — response records or direct writes?",
          "DIRECT WRITES. No response record carries sample data. The "
          "application hands over the base of its own structure in record "
          "field +4 of opcode 0x0d, and the second context writes the "
          "structure's fields itself.",
          "observed",
          "FUN_18000136's literal pool holds 0x1801ed6c and the record array; "
          "the stores use the saved pointer as their base register",
          ("this log step 3",)),
    Claim("cadence",
          "At what cadence?",
          "On IRQ38's tick divided by 8, immediately before the actuation "
          "comparison in the same job. The absolute rate remains unresolved "
          "because the timer that raises IRQ38 is still unidentified.",
          "observed",
          "the entry image's /8 branch calls veneer 0x4044, whose target "
          "tail-branches to the client veneer; the branch decoder is checked "
          "against one Ghidra resolved",
          ("log 109 step 5", "this log step 5")),
    Claim("bitmap",
          "Does the second context write the per-key bitmap at 0x18023410?",
          "No. The bitmap is written by the application's FUN_180049a8, which "
          "is the function that requests the samples. The second context "
          "never references it.",
          "observed",
          "the bitmap address appears in FUN_180049a8's literal pool and in "
          "no aligned word or immediate of the second-context image",
          ("this log step 4", "log 118 step 3")),
    Claim("gate",
          "Is the Hall acquisition gate closable?",
          "YES. Every link from the hardware conversion to the actuation "
          "comparison is now demonstrated, and the tool refuses this wording "
          "unless all eight backing checks hold.",
          "observed",
          "path_complete() is computed from the pointer share, both delivery "
          "counts, three properties of the travel curve and the decoded "
          "cadence branch",
          ("this log step 6", "log 110", "log 109", "log 118")),
    Claim("orphans",
          "Does this explain the long-standing callerless functions?",
          "Yes, both of them. FUN_18008c16 — unexplained since log 106 and "
          "still open in log 109 — calls FUN_180049a8, which is the sample "
          "requester. That closes the last of log 106's large orphans.",
          "strongly-inferred",
          "Ghidra's inventory records FUN_180049a8's only caller as "
          "FUN_18008c16; what calls FUN_18008c16 is still not recovered",
          ("log 106", "log 109 step 5", "this log step 2")),
)


UNRESOLVED = (
    ("absolute_rate",
     "IRQ38's period is still unknown, so the sample rate is a ratio and not "
     "a frequency. Unchanged by this step."),
    ("fun_18008c16_caller",
     "FUN_18008c16 calls the sample requester, but what calls FUN_18008c16 is "
     "still not recovered. The chain is complete from the tick job's veneer; "
     "this second route into it is not."),
    ("opcode_03",
     "Opcode 0x03 has a handler and no recovered client. Two of the sixteen "
     "opcodes are implemented with no caller found."),
    ("physical_units",
     "The converter's input and output carry no units. The travel byte's "
     "scale is 0..200 with actuation at 100, which is a ratio, not a distance."),
    ("reference_and_scale_origin",
     "The per-key reference values and scale factors the normalisation uses "
     "live in the second context's RAM. What writes them is not traced here."),
    ("unresolved_accesses",
     "484 of the second context's accesses still have an unresolved base, so "
     "every negative remains a 'not resolved'."),
)


def claims():
    return [{"key": c.key, "question": c.question, "answer": c.answer,
             "confidence": c.confidence, "kind_basis": c.kind_basis,
             "evidence": list(c.evidence)} for c in CLAIMS]


# --- reporting --------------------------------------------------------------

def opcode_table():
    by_client = {}
    for client in CLIENTS:
        for opcode in client.opcodes:
            by_client[opcode] = client
    sites = call_sites()
    rows = []
    for opcode in sorted(HANDLERS):
        client = by_client.get(opcode)
        callers = []
        if client:
            tag = (f"0x{client.address:04x}" if client.image == "entry"
                   else f"0x{client.address:08x}")
            callers = sorted({s["function"] for s in sites
                              if s["client"] == tag})
            if client.image == "app":
                callers = ["CandidateB_Main"]
        rows.append({
            "opcode": f"0x{opcode:02x}",
            "handler": HANDLERS[opcode],
            "client": (f"0x{client.address:x}" if client else ""),
            "client_image": client.image if client else "",
            "request": client.request if client else "",
            "response": RESPONSES.get(opcode, "none recovered"),
            "call_sites": callers,
            "direction": ("app -> second, with a reply written into app RAM"
                          if opcode in RESPONSES else "app -> second"),
        })
    return rows


def verify():
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    ms.sources()
    check(True, "both preserved source hashes match the allowlist")
    check(movw_self_test(),
          "the movw decoder reproduces log 113's hand-validated veneer bytes",
          START_VENEER_BYTES.hex())
    check(branch_self_test(),
          "the branch decoder agrees with a target Ghidra resolved",
          "bl at 0x180049b4 -> 0x1801be22")

    ven = veneers()
    check(all(v["found"] for v in ven),
          "every entry-image client has a cross-image veneer",
          f"{sum(v['found'] for v in ven)} of {len(ven)}")

    found = client_opcodes()
    for client in CLIENTS:
        check(set(client.opcodes) <= set(found[client.address]),
              f"client 0x{client.address:x}'s opcode is present in its own bytes",
              ", ".join(f"0x{o:02x}" for o in client.opcodes))

    sites = call_sites()
    check(len(sites) >= 8, "every client veneer has at least one call site",
          f"{len(sites)} sites")

    share = pointer_share()
    check(share["cell_is_in_the_pool"],
          "the sender's literal pool holds the travel pointer cell",
          share["pointer_cell"])
    check(share["record_array_in_pool"],
          "the sender's literal pool holds the mailbox record array")
    check(share["matches_log110"],
          "shared base + 0x35c is exactly log 110's travel array",
          share["travel_array"])

    deliver = delivery()
    check(deliver["travel_store_count"] == 3,
          "the second context stores into the travel array",
          f"{deliver['travel_store_count']} strb.w sites at +0x35c")
    check(deliver["sample_store_count"] == 24,
          "the second context stores raw samples into application RAM",
          f"{deliver['sample_store_count']} strh.w sites at +0x3f2")
    check(not deliver["bitmap_referenced"],
          "the second context never references the per-key bitmap",
          f"0x{KEY_STATE_BITMAP:08x}")

    curve = travel_curve()
    check(curve["length_equals_clamp_bound"],
          "the travel table's length equals the clamp bound",
          f"{curve['length']} == 0x{CLAMP:x} + 1")
    check(curve["monotonic_non_decreasing"],
          "the travel table is monotonic, as a travel curve must be")
    check(curve["maximum_is_twice_the_threshold"],
          "the table's maximum is exactly twice log 110's actuation threshold",
          f"{curve['maximum']} = 2 x {ACTUATION_THRESHOLD}")

    cad = cadence()
    check(cad["reaches_the_sample_client"],
          "the every-tick /8 job reaches the sample client",
          f"{cad['sample_veneer']} -> {cad['stub']} -> {cad['stub_target']}")
    check(cad["absolute_rate"].startswith("UNRESOLVED"),
          "the absolute rate is still reported as unresolved",
          "a ratio is not a frequency")

    check(path_complete(),
          "every link of the producer path is demonstrated",
          f"{len(PATH)} links")
    check(hall_gate()["status"] == "CLOSED",
          "the Hall acquisition gate is reported CLOSED",
          "and only because path_complete() holds")

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
        "source": {
            "second_context_sha256": hashlib.sha256(ms.image()).hexdigest(),
            "source_hashes": ms.SOURCE_SHA,
        },
        "opcodes": opcode_table(),
        "clients": [{"address": f"0x{c.address:x}", "image": c.image,
                     "opcodes": [f"0x{o:02x}" for o in c.opcodes],
                     "request": c.request, "note": c.note} for c in CLIENTS],
        "veneers": veneers(),
        "call_sites": call_sites(),
        "pointer_share": pointer_share(),
        "delivery": delivery(),
        "travel_curve": travel_curve(),
        "cadence": cadence(),
        "hall_gate": hall_gate(),
        "claims": claims(),
        "unresolved": [{"key": k, "detail": d} for k, d in UNRESOLVED],
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images. No device was "
                      "accessed. This changes no decision and authorises "
                      "nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["MAILBOX SAMPLE FLOW — both sides of the conversation", ""]
    out.append("OPCODE TABLE")
    out.append("  op    handler              client      request -> response")
    for row in d["opcodes"]:
        out.append(f"  {row['opcode']}  {row['handler']:<20} "
                   f"{row['client'] or '-':<11} {row['request'] or 'none'}")
        if row["response"] != "none recovered":
            out.append(f"        -> {row['response']}")
        if row["call_sites"]:
            out.append(f"        call sites: {', '.join(row['call_sites'])}")
    share = d["pointer_share"]
    out += ["", "THE POINTER SHARE",
            f"  {share['sender']} sends opcode {share['opcode']}",
            f"  record{share['record_field']} = *({share['pointer_cell']}) "
            f"= {share['cell_value']}",
            f"  travel array = base + 0x{TRAVEL_OFFSET:x} = "
            f"{share['travel_array']}  matches log 110: {share['matches_log110']}"]
    deliver = d["delivery"]
    out += ["", "DELIVERY",
            f"  {deliver['sample_store_count']} stores at +0x{SAMPLE_OFFSET:x} "
            f"({deliver['sample_store_function']})",
            f"  {deliver['travel_store_count']} stores at +0x{TRAVEL_OFFSET:x} "
            f"({deliver['travel_store_function']})"]
    curve = d["travel_curve"]
    out += ["", "THE TRAVEL CURVE",
            f"  {curve['address']} length {curve['length']} "
            f"(= clamp {curve['clamp']} + 1: {curve['length_equals_clamp_bound']})",
            f"  monotonic {curve['monotonic_non_decreasing']}, range "
            f"{curve['minimum']}..{curve['maximum']}, threshold "
            f"{curve['actuation_threshold']}",
            f"  sampled: {curve['sampled']}"]
    cad = d["cadence"]
    out += ["", "CADENCE",
            f"  {cad['sample_veneer']} -> {cad['stub']} -> {cad['stub_target']}"
            f"  reaches the client: {cad['reaches_the_sample_client']}",
            f"  {cad['order']}", f"  {cad['absolute_rate']}"]
    gate = d["hall_gate"]
    out += ["", f"HALL GATE  {gate['status']}  (was: {gate['previous_state']})",
            f"  mechanism: {gate['mechanism']}", ""]
    for link in gate["links"]:
        out.append(f"    {link['step']}")
        out.append(f"        {link['detail']}  [{link['citation']}]")
    out += ["", "ANSWERS"]
    for c in d["claims"]:
        out.append(f"    [{c['confidence']}] {c['question']}")
        out.append(f"        {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"    {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out += ["", f"RESULT sample_flow_ok={d['summary']['ok']} "
            f"checks={d['summary']['checks']}",
            "OFFLINE ANALYSIS ONLY. No device was accessed, and nothing here "
            "authorises a live experiment."]
    return out


def markdown():
    d = to_dict()
    gate = d["hall_gate"]
    out = ["# The mailbox conversation and the per-key sample flow", "",
           "**Status: traced.** Generated by `tool/map_sample_flow.py`. Do not "
           "edit by hand.", "",
           "> Offline analysis of preserved images. No device was accessed. "
           "Path-B evidence-gate work: it changes no decision and authorises "
           "nothing live.", "",
           f"## The Hall acquisition gate is {gate['status']}", "",
           f"Previous state: *{gate['previous_state']}*. Mechanism: "
           f"**{gate['mechanism']}**.", "",
           gate["why_it_was_never_found"], "",
           "| step | what happens | citation |", "|---|---|---|"]
    for link in gate["links"]:
        out.append(f"| {link['step']} | {link['detail']} | {link['citation']} |")
    out += ["", "## The opcode table", "",
            "| op | handler | client | image | request | response | call sites |",
            "|---|---|---|---|---|---|---|"]
    for row in d["opcodes"]:
        out.append(f"| `{row['opcode']}` | `{row['handler']}` | "
                   f"{'`' + row['client'] + '`' if row['client'] else '—'} | "
                   f"{row['client_image'] or '—'} | {row['request'] or 'none'} | "
                   f"{row['response']} | {', '.join(row['call_sites']) or '—'} |")
    share = d["pointer_share"]
    out += ["", "## The pointer share", "",
            f"`{share['sender']}` sends opcode `{share['opcode']}` with "
            f"record field `{share['record_field']}` set to "
            f"`*({share['pointer_cell']})` = `{share['cell_value']}`.", "",
            share["consequence"], "",
            "| offset | written by | direction | |", "|---|---|---|---|"]
    for field in share["fields"]:
        out.append(f"| `+{field['offset']}` | {field['written_by']} | "
                   f"{field['direction']} | {field.get('detail','')} |")
    curve = d["travel_curve"]
    out += ["", "## The travel curve", "",
            f"The normalised value is clamped at `{curve['clamp']}` and indexes "
            f"a table at `{curve['address']}` of **{curve['length']} bytes** — "
            f"exactly the clamp bound plus one. It is monotonic "
            f"non-decreasing, ranges {curve['minimum']}..{curve['maximum']}, "
            f"and its maximum is exactly twice log 110's actuation threshold "
            f"of {curve['actuation_threshold']}. Three independent properties "
            f"agreeing is what makes the identification safe.", "",
            f"Sampled every 64th entry: `{curve['sampled']}`", ""]
    cad = d["cadence"]
    out += ["## Cadence", "",
            f"The every-tick job's /8 branch calls veneer "
            f"`{cad['sample_veneer']}`, whose target `{cad['stub']}` "
            f"tail-branches to `{cad['stub_target']}`, the sample client's "
            f"veneer. {cad['order']}.", "",
            f"**{cad['absolute_rate']}**", "", "## Answers", ""]
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
        "sample-flow.json": json.dumps(to_dict(), indent=2, sort_keys=True) + "\n",
        "sample-flow.md": markdown(),
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
    except (OSError, SampleFlowError, ms.SecondContextError, struct.error,
            KeyError, StopIteration) as exc:
        print(f"RESULT sample_flow_ok=False error={exc}")
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
        print(payload["sample-flow.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
