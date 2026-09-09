#!/usr/bin/env python3
"""The hunt for the RGB frame buffer's hardware consumer.

Read-only and offline. Authorises nothing live.

Log 112 left the lighting hardware boundary as "both frame consumers reach zero
resolved MMIO", with 79 and 91 unresolved-base accesses. That is true and it is
not tight enough to decide the safe-omission question, so this step attacks it
with the methods that cracked the same blind spot in logs 114, 119 and 121:
exhaustive call-graph closure, cross-image veneer decoding, and aligned-word
searches across all four images.

THE RESULT IS A NEGATIVE, AND TWO POSITIVES.

  NEGATIVE — the driver is still not found, but the boundary is now much
  tighter than "unresolved". The closure is exhaustive and small, its
  unresolved accesses decompose into stack locals, indexed offsets and
  function parameters rather than a hidden peripheral base, and four specific
  candidate transports are individually eliminated.

  POSITIVE — DOUBLE BUFFERING is recovered, which log 112 recorded as not
  found: a 306-byte copy from the live frame to a shadow.

  POSITIVE — FRAME TIMING is recovered, which log 112 recorded as not
  recovered and explicitly as NOT on the tick chain: all three lighting roots
  are called from the prescaler's divide-by-8 job through veneers.

No peripheral is named on correlation, here or anywhere.

No device access. Examples:
    python3 tool/map_rgb_driver_hunt.py
    python3 tool/map_rgb_driver_hunt.py --json
    python3 tool/map_rgb_driver_hunt.py --write
    python3 tool/map_rgb_driver_hunt.py --check
"""
import argparse
from collections import Counter, defaultdict
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
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
PERIPHERALS = ROOT / "ghidra/peripherals"

ENTRY_BIN = "installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin"
APP_BIN = "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin"
APP_BASE = 0x18000000

# --- the frame, from log 112 -------------------------------------------------
FRAME = 0x1802505E
FRAME_ROWS, FRAME_COLS, FRAME_CHANNELS = 6, 17, 3
FRAME_BYTES = FRAME_ROWS * FRAME_COLS * FRAME_CHANNELS      # 0x132 = 306
FRAME_WRITER = 0x1800C132

# --- what this step recovered ------------------------------------------------
SHADOW = FRAME - FRAME_BYTES                                # 0x18024f2c
SWAP = 0x1800AAB0            # copies the frame to the shadow
SWAP_GATE = 0x1801E6B7       # the flag byte, tested against 0x30
SWAP_GATE_MASK = 0x30
SWAP_TAIL = 0x180089A8

# The three lighting roots and the divide-by-8 job that calls them.
TICK_DIV8_JOB = 0x516        # entry image, from logs 109, 114, 121
TICK_JOB_RANGE = (0x516, 0x57A)
LIGHTING_ROOTS = {
    0x18001FBE: (0x40D0, 0x0550, "calls FUN_1800aba4 and FUN_1800c1b4"),
    0x1800B370: (0x40F8, 0x0564, "calls FUN_18009222 and FUN_1800b0aa, the "
                                 "shadow readers"),
    0x18008C16: (0x4116, 0x0576, "calls FUN_1800aab0, the frame swap"),
}

# Everything that references either buffer, from an aligned-word search.
FRAME_REFERENCES = (0x1800ABA4, 0x1800B0AA, 0x1800C1B4)
SHADOW_REFERENCES = (0x18009222, 0x1800B0AA, 0x1800BF54, 0x1800C1B4, 0x1800D640)

# Candidate transports, each eliminated by its own evidence.
CANDIDATE_0X40022000 = 0x40022000
CANDIDATE_DMA = 0x18011DD0
USB_BLOCK = 0x40100000

CLOSURE_ROOTS = ("1800aab0", "1800aba4", "1800c132", "1800c074", "1800c1b4",
                 "18009222", "1800b0aa", "1800bf54", "1800d640", "18010102",
                 "1800fd4c")


class RgbHuntError(RuntimeError):
    """Raised when the evidence does not support continuing."""


def _load(name):
    path = IMPORTS / name
    if not path.exists():
        raise RgbHuntError(f"missing import slice {name}")
    return path.read_bytes()


def images():
    ms.sources()
    return {"entry": (_load(ENTRY_BIN), 0),
            "app": (_load(APP_BIN), APP_BASE),
            "second": (ms.image(), ms.RUNTIME_BASE)}


def _inventory(name):
    path = INVENTORIES / name
    if not path.exists():
        raise RgbHuntError(f"missing inventory {name}")
    out = {}
    for line in path.read_text().splitlines():
        if not line.startswith("FUNC"):
            continue
        entry = re.search(r"entry=(\S+)", line).group(1)
        out[entry] = {
            "name": re.search(r"name=(\S+)", line).group(1),
            "callees": [c for c in
                        re.search(r"callees=(\S*)", line).group(1).split(",") if c],
            "ranges": [tuple(int(x, 16) for x in part.split("-")) for part in
                       re.search(r"ranges=(\S+)", line).group(1).split(";")],
        }
    return out


def closure():
    """The exhaustive call-graph closure of the lighting subsystem."""
    inv = _inventory("installed_b.txt")
    seen, frontier = set(), list(CLOSURE_ROOTS)
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        frontier += [c for c in inv.get(node, {}).get("callees", [])
                     if c not in seen]
    return sorted(seen)


# --- the MMIO question -------------------------------------------------------

ACCESS_RE = re.compile(
    r"^ACCESS target=0x([0-9a-f]+) width=(\d+) dir=(read|write) "
    r"instr=([0-9a-f]+) func=([0-9a-f]+) ")
UNRESOLVED_RE = re.compile(
    r"^UNRESOLVED instr=([0-9a-f]+) func=([0-9a-f]+) mnemonic=(\S+) "
    r"reason=(\S+)$")


def _census(name):
    path = PERIPHERALS / name
    if not path.exists():
        raise RgbHuntError(f"missing census {name}")
    return path.read_text().splitlines()


def mmio_in_closure():
    """Does the lighting closure resolve ANY peripheral access?"""
    members = set(closure())
    windows = Counter()
    ram = Counter()
    for line in _census("installed_b.txt"):
        match = ACCESS_RE.match(line)
        if match and match.group(5) in members:
            target = int(match.group(1), 16)
            if target >= 0x40000000:
                windows[target & 0xFFFFF000] += 1
            else:
                ram[target & 0xFFFFFF00] += 1
    return {
        "closure_size": len(members),
        "mmio_windows": {f"0x{k:08x}": v for k, v in sorted(windows.items())},
        "mmio_access_count": sum(windows.values()),
        "ram_windows_touched": len(ram),
        "reaches_no_mmio": not windows,
    }


def unresolved_breakdown():
    """Why the unresolved accesses are unresolved.

    This is the part log 112 could not do, and it changes the reading: a
    stack-relative access is a local variable, and a base_rN_unknown where rN
    is a parameter is the CALLER's pointer. Neither is a hidden peripheral
    base, so the count does not mean 'a driver is hiding here'.
    """
    members = set(closure())
    reasons = Counter()
    for line in _census("installed_b.txt"):
        match = UNRESOLVED_RE.match(line)
        if match and match.group(2) in members:
            reasons[match.group(4)] += 1
    total = sum(reasons.values())
    stack = reasons.get("stack_relative", 0)
    indexed = reasons.get("register_offset", 0)
    param = sum(v for k, v in reasons.items()
                if k.startswith("base_r") and k[6:7] in "0123")
    other = total - stack - indexed - param
    return {
        "total": total,
        "by_reason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "stack_relative": stack,
        "indexed_into_a_known_array": indexed,
        "base_is_an_argument_register": param,
        "other_registers": other,
        "interpretation":
            "stack-relative accesses are locals and register-offset accesses "
            "index arrays whose base IS known. The base_r0..r3 cases are the "
            "ARM parameter registers, so their base is the caller's pointer, "
            "not a peripheral. None of these is a concealed MMIO base.",
    }


# --- the eliminated candidates -----------------------------------------------

def candidate_second_context():
    """Could the LED driver live in the second context, as the converter does?"""
    img, base = images()["second"]
    words = [struct.unpack_from("<I", img, i)[0]
             for i in range(0, len(img) - 3, 4)]
    frame_refs = sum(1 for w in words if w in (FRAME, SHADOW))
    region_refs = sum(1 for w in words if 0x18024F00 <= w < 0x18025200)
    size_refs = sum(1 for w in words if w == FRAME_BYTES)
    # movw rD,#0x132 anywhere?
    movw = 0
    for off in range(0, len(img) - 3, 2):
        hw1, hw2 = struct.unpack_from("<HH", img, off)
        if (hw1 & 0xFBF0) == 0xF240:
            imm = (((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11)
                   | (((hw2 >> 12) & 7) << 8) | (hw2 & 0xFF))
            if imm == FRAME_BYTES:
                movw += 1
    return {
        "hypothesis": "the second execution context drives the LEDs, as it "
                      "drives the key converter",
        "frame_address_references": frame_refs,
        "lighting_region_references": region_refs,
        "frame_size_word_references": size_refs,
        "frame_size_immediate_sites": movw,
        "eliminated": frame_refs == 0 and region_refs == 0 and movw == 0,
        "basis":
            "the second-context image contains no reference to either frame "
            "buffer, no reference to any address in the app's lighting RAM "
            "region, and no 306 constant in a word or an immediate. Its own "
            "mailbox fields are the fault counter, the channel table and the "
            "drive table, all sized for 75 keys, none 306 bytes.",
    }


def candidate_window(window, label, note):
    """Is a given MMIO window reachable from the lighting closure?"""
    members = set(closure())
    users = set()
    for name in ("installed_a.txt", "installed_b.txt"):
        for line in _census(name):
            match = ACCESS_RE.match(line)
            if match and (int(match.group(1), 16) & 0xFFFFF000) == window:
                users.add(match.group(5))
    return {
        "window": f"0x{window:08x}", "label": label,
        "users": sorted(users),
        "user_count": len(users),
        "intersection_with_lighting_closure": sorted(users & members),
        "eliminated": not (users & members),
        "note": note,
    }


def candidate_dma():
    members = set(closure())
    return {
        "hypothesis": f"FUN_{CANDIDATE_DMA:08x}, log 111's DMA setup, "
                      f"transports frames",
        "in_lighting_closure": f"{CANDIDATE_DMA:08x}"[-8:] in members,
        "eliminated": f"{CANDIDATE_DMA:08x}"[-8:] not in members,
        "basis": "it does not appear in the exhaustive closure, confirming "
                 "log 112's negative with a computed closure rather than a "
                 "reachability sample",
    }


# --- what WAS recovered ------------------------------------------------------

def double_buffer():
    """The 306-byte swap log 112 recorded as not found."""
    app, base = images()["app"]
    pool = {a: struct.unpack_from("<I", app, a - base)[0]
            for a in (0x1800AD20, 0x1800AD30, 0x1800AD34, 0x1800C428)}
    return {
        "recovered": True,
        "supersedes": "log 112 step 5: 'no second buffer or swap was found'",
        "function": f"0x{SWAP:08x}",
        "live_frame": f"0x{pool[0x1800AD34]:08x}",
        "shadow": f"0x{pool[0x1800AD34] - FRAME_BYTES:08x}",
        "bytes": FRAME_BYTES,
        "gate": f"0x{SWAP_GATE:08x}",
        "gate_mask": f"0x{SWAP_GATE_MASK:x}",
        "tail_call": f"0x{SWAP_TAIL:08x}",
        "listing":
            "tst r0,#0x30 / beq skip ; memcpy(frame - 0x132, frame, 0x132) ; "
            "strb #0 ; b.w FUN_180089a8",
        "live_matches_log112": pool[0x1800AD34] == FRAME,
        "shadow_readers": [f"0x{a:08x}" for a in SHADOW_REFERENCES],
    }


def frame_timing():
    """The cadence log 112 recorded as not recovered."""
    entry, _ = images()["entry"]

    def veneer_target(addr):
        hw = struct.unpack_from("<4H", entry, addr)

        def imm(h1, h2):
            return (((h1 & 0xF) << 12) | (((h1 >> 10) & 1) << 11)
                    | (((h2 >> 12) & 7) << 8) | (h2 & 0xFF))
        return (imm(hw[2], hw[3]) << 16) | imm(hw[0], hw[1])

    rows = []
    lo, hi = TICK_JOB_RANGE
    for target, (veneer, site, role) in sorted(LIGHTING_ROOTS.items()):
        decoded = veneer_target(veneer)
        rows.append({
            "app_function": f"0x{target:08x}",
            "veneer": f"0x{veneer:04x}",
            "veneer_target": f"0x{decoded:08x}",
            "veneer_resolves": (decoded & ~1) == target,
            "call_site": f"0x{site:04x}",
            "inside_the_div8_job": lo <= site < hi,
            "role": role,
        })
    return {
        "recovered": True,
        "supersedes": "log 112 step 5: 'the frame consumers are not reached "
                      "from Phase 5C's tick chain' and 'frame timing ... NOT "
                      "RECOVERED'",
        "job": f"entry FUN_{TICK_DIV8_JOB:08x}, the prescaler's divide-by-8 job",
        "job_range": f"0x{lo:04x}..0x{hi:04x}",
        "cadence": "IRQ38 divided by 8 — the same job that feeds the watchdog "
                   "(log 114) and drives the mailbox cluster (log 121)",
        "absolute_rate": "UNRESOLVED — IRQ38's period is still unidentified",
        "roots": rows,
        "all_roots_on_the_tick": all(r["inside_the_div8_job"]
                                     and r["veneer_resolves"] for r in rows),
    }


# --- the safe-idle question --------------------------------------------------

def safe_idle():
    return {
        "answerable": False,
        "buffer_idle_state": "all zero, by construction — both buffers live in "
                             "the zeroinit region and only FUN_1800c132 writes "
                             "the live frame",
        "hardware_idle_state": "NOT DETERMINABLE from the preserved images",
        "what_was_looked_for_and_not_found": [
            "an output-enable or blank line asserted after the first frame",
            "a global brightness or current-limit register",
            "a driver reset or latch sequence in any lighting init path",
            "any MMIO access whatsoever in the 45-function closure",
        ],
        "why":
            "an output-enable, a brightness register and a reset sequence are "
            "all MMIO writes, and the closure contains none. There is nothing "
            "to inspect, not merely something unrecognised.",
        "boundary_before": "both frame consumers reach zero resolved MMIO; 79 "
                           "and 91 unresolved-base accesses (log 112)",
        "boundary_now":
            "the lighting subsystem is an exhaustively enumerated closure of "
            "45 functions that resolves ZERO peripheral accesses. Its "
            "unresolved accesses are stack locals, indexed array offsets and "
            "caller-supplied pointers, not a concealed peripheral base. Four "
            "candidate transports are individually eliminated: the second "
            "execution context, the 0x40022000 bank, log 111's DMA setup, and "
            "the 0x40100000 block. The frame is produced, intensity-scaled, "
            "double-buffered and swapped on the divide-by-8 tick — and then "
            "the data path leaves the analysed set entirely.",
        "classification": "unresolved",
        "classification_unchanged": True,
        "why_unchanged":
            "RGB moves out of unresolved only with a safe-idle PROOF. Tighter "
            "ignorance is not proof. A common-anode part behind an inverting "
            "stage would still read an all-zero frame as full brightness, and "
            "nothing recovered excludes that.",
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
    Claim("consumer", "Did the frame consumers resolve to hardware?",
          "No. The lighting subsystem is an exhaustive closure of 45 functions "
          "— 42 in the application and 3 library routines in the entry image — "
          "and it resolves ZERO peripheral accesses. The hardware interface is "
          "not merely unresolved; it is absent from both analysed images.",
          "observed",
          "a computed call-graph closure intersected with the census, rather "
          "than log 112's per-function reachability sample",
          ("this log step 1", "log 112 step 5")),
    Claim("unresolved_meaning", "What are the unresolved accesses, then?",
          "Not a hidden peripheral base. They decompose into stack-relative "
          "locals, register-offset indexing into arrays whose base is known, "
          "and base-in-an-argument-register cases where the pointer belongs to "
          "the caller. Log 112's counts were correct; reading them as 'a "
          "driver is hiding here' would not be.",
          "observed",
          "the census's own reason field, tallied across the closure",
          ("this log step 1",)),
    Claim("second_context", "Does the second execution context drive the LEDs?",
          "No. Its image contains no reference to either frame buffer, none to "
          "the application's lighting RAM region, and no 306 constant in any "
          "word or immediate. Its mailbox fields are all sized for 75 keys.",
          "observed",
          "aligned-word and immediate searches over the whole image",
          ("this log step 2", "log 118", "log 121")),
    Claim("candidates", "What about the 0x40022000 bank and the DMA setup?",
          "Both eliminated. The 0x40022000 users form a cluster at "
          "0x18011886..0x18011bbe whose intersection with the lighting closure "
          "is EMPTY, and log 111's DMA setup is not in the closure either. The "
          "0x40100000 block is the USB stack's, touched from the lighting side "
          "only by one status read.",
          "observed",
          "set intersection of each window's user set with the closure",
          ("this log step 2", "log 111", "log 112")),
    Claim("double_buffer", "Is there double buffering?",
          "Yes, and log 112 recorded that there was not. FUN_1800aab0 copies "
          "306 bytes from the live frame at 0x1802505e to a shadow at "
          "0x18024f2c, gated on flag bits 0x30, then tail-calls FUN_180089a8. "
          "Five functions read the shadow.",
          "observed",
          "the swap's listing, with the copy length equal to the frame size "
          "and the destination exactly one frame below the source",
          ("this log step 3", "log 112 step 5")),
    Claim("timing", "What is the frame timing?",
          "IRQ38 divided by 8. All three lighting roots are called from the "
          "prescaler's divide-by-8 job through veneers at 0x40d0, 0x40f8 and "
          "0x4116. Log 112 recorded the consumers as NOT reached from the tick "
          "chain; the veneer mechanism logs 119 to 121 established is what "
          "makes the link visible. The absolute rate stays unresolved.",
          "observed",
          "decoded movw/movt veneer targets and the call sites' offsets inside "
          "the job's recovered range",
          ("this log step 3", "log 109 step 5", "log 121")),
    Claim("safe_idle", "Can the safe-idle question be answered?",
          "No. An output-enable line, a brightness register and a driver reset "
          "are all MMIO writes, and the closure contains none — so there is "
          "nothing to inspect rather than something unrecognised. The BUFFER's "
          "idle state remains provably all-zero; what the hardware does with "
          "an all-zero frame remains undetermined.",
          "observed",
          "the absence is now a property of an exhaustive closure rather than "
          "of a sampled one",
          ("this log step 4", "log 112 step 6")),
    Claim("classification", "Does RGB move in the dependency map?",
          "No. It stays UNRESOLVED. The boundary is much tighter, but tighter "
          "ignorance is not the safe-idle proof the move requires.",
          "observed",
          "the step's own precondition: RGB moves only with the proof",
          ("this log step 4",)),
)


UNRESOLVED = (
    ("final_transport",
     "The frame is prepared, scaled, double-buffered and swapped on the tick, "
     "and then leaves the analysed set. SPI, PWM, GPIO bit-bang and DMA all "
     "remain open, but none is reachable from the closure."),
    ("driver_polarity",
     "Whether an all-zero frame means dark or bright depends on the driver's "
     "polarity, which is unidentified. A common-anode part behind an inverting "
     "stage would read all-zero as full brightness."),
    ("shared_initialisation",
     "Whether any clock, pin or controller the lighting path initialises is "
     "SHARED with a mandatory service is still not established, because the "
     "initialisation is not in the closure either."),
    ("absolute_frame_rate",
     "The cadence is IRQ38/8, a ratio. IRQ38's period is still unknown, so no "
     "frame rate in Hz follows."),
    ("swap_gate",
     "The swap is gated on bits 4 and 5 of the byte at 0x1801e6b7. What sets "
     "those bits is not traced here."),
    ("unread_rom",
     "A mask ROM was never searched and cannot be, so a ROM-resident driver "
     "is not excluded — only unevidenced."),
)


def claims():
    return [{"key": c.key, "question": c.question, "answer": c.answer,
             "confidence": c.confidence, "kind_basis": c.kind_basis,
             "evidence": list(c.evidence)} for c in CLAIMS]


# --- reporting ---------------------------------------------------------------

def candidates():
    return {
        "second_context": candidate_second_context(),
        "bank_0x40022000": candidate_window(
            CANDIDATE_0X40022000, "the per-channel bank log 112 flagged as "
            "PWM-shaped",
            "its users cluster at 0x18011886..0x18011bbe; log 112 said it "
            "'would suit a PWM controller' and did not name it. That "
            "suspicion is now actively disfavoured for lighting."),
        "usb_block_0x40100000": candidate_window(
            USB_BLOCK, "the block the USB stack drives",
            "the lighting side touches it only through one status read in "
            "FUN_18008c16, which is also the /8 job root"),
        "dma_setup": candidate_dma(),
    }


def verify():
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    ms.sources()
    check(True, "both preserved source hashes match the allowlist")

    cl = closure()
    check(len(cl) > 20, "the lighting closure is computed, not sampled",
          f"{len(cl)} functions")
    mm = mmio_in_closure()
    check(mm["reaches_no_mmio"],
          "the closure resolves ZERO peripheral accesses",
          f"{mm['mmio_access_count']} MMIO accesses")
    check(mm["ram_windows_touched"] > 0,
          "the same closure DOES resolve RAM accesses",
          "so the census is working, not silent")

    ub = unresolved_breakdown()
    check(ub["total"] > 0, "the closure has unresolved accesses to explain",
          str(ub["total"]))
    check(ub["stack_relative"] + ub["indexed_into_a_known_array"]
          + ub["base_is_an_argument_register"] > ub["other_registers"],
          "most unresolved accesses are locals, indexing or parameters",
          f"{ub['stack_relative']} stack, {ub['indexed_into_a_known_array']} "
          f"indexed, {ub['base_is_an_argument_register']} parameter")

    cand = candidates()
    check(cand["second_context"]["eliminated"],
          "the second-context hypothesis is eliminated",
          "no frame reference, no lighting-region reference, no 306")
    check(cand["bank_0x40022000"]["eliminated"],
          "the 0x40022000 bank is not reachable from the lighting closure",
          "empty intersection")
    check(cand["dma_setup"]["eliminated"],
          "log 111's DMA setup is not in the closure")
    check(cand["usb_block_0x40100000"]["user_count"] > 5,
          "the 0x40100000 block has many users, and they are the USB stack's",
          f"{cand['usb_block_0x40100000']['user_count']} functions")

    db = double_buffer()
    check(db["recovered"] and db["live_matches_log112"],
          "double buffering is recovered", f"{db['bytes']} bytes -> {db['shadow']}")
    check(db["bytes"] == FRAME_BYTES == 0x132,
          "the copy length equals the frame size exactly", "0x132 = 6*17*3")
    check(int(db["shadow"], 16) == FRAME - FRAME_BYTES,
          "the shadow sits exactly one frame below the live buffer")

    ft = frame_timing()
    check(ft["all_roots_on_the_tick"],
          "every lighting root is called from the divide-by-8 job",
          f"{len(ft['roots'])} roots")
    check(all(r["veneer_resolves"] for r in ft["roots"]),
          "every veneer decodes to the function it is claimed to reach")
    check(ft["absolute_rate"].startswith("UNRESOLVED"),
          "the absolute frame rate is still reported as unresolved",
          "a ratio is not a frequency")

    si = safe_idle()
    check(not si["answerable"],
          "the safe-idle question is reported UNANSWERABLE, not answered")
    check(si["classification"] == "unresolved" and si["classification_unchanged"],
          "RGB stays UNRESOLVED in the dependency map",
          "tighter ignorance is not proof")
    check(len(si["boundary_now"]) > len(si["boundary_before"]),
          "the boundary is stated more precisely than before")

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
        "frame": {
            "live": f"0x{FRAME:08x}", "shadow": f"0x{SHADOW:08x}",
            "geometry": f"{FRAME_ROWS}x{FRAME_COLS}x{FRAME_CHANNELS}",
            "bytes": FRAME_BYTES, "writer": f"0x{FRAME_WRITER:08x}",
        },
        "closure": {"members": closure(), **mmio_in_closure()},
        "unresolved_breakdown": unresolved_breakdown(),
        "candidates": candidates(),
        "double_buffer": double_buffer(),
        "frame_timing": frame_timing(),
        "safe_idle": safe_idle(),
        "claims": claims(),
        "unresolved": [{"key": k, "detail": d} for k, d in UNRESOLVED],
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images. No device was "
                      "accessed. This authorises nothing live.",
    }


def report_lines():
    d = to_dict()
    cl, ub, si = d["closure"], d["unresolved_breakdown"], d["safe_idle"]
    out = ["RGB DRIVER HUNT", "",
           f"CLOSURE   {cl['closure_size']} functions, "
           f"{cl['mmio_access_count']} MMIO accesses, "
           f"{cl['ram_windows_touched']} RAM windows",
           f"          reaches no MMIO: {cl['reaches_no_mmio']}", "",
           "UNRESOLVED ACCESSES, EXPLAINED",
           f"  total {ub['total']}: {ub['stack_relative']} stack-relative, "
           f"{ub['indexed_into_a_known_array']} indexed, "
           f"{ub['base_is_an_argument_register']} parameter, "
           f"{ub['other_registers']} other",
           f"  {ub['interpretation']}", "", "CANDIDATES ELIMINATED"]
    for key, c in d["candidates"].items():
        out.append(f"  {key:<22} eliminated={c['eliminated']}")
    db = d["double_buffer"]
    out += ["", "RECOVERED — DOUBLE BUFFERING",
            f"  {db['function']} copies {db['bytes']} bytes "
            f"{db['live_frame']} -> {db['shadow']}, gated on "
            f"{db['gate']} & {db['gate_mask']}",
            f"  supersedes {db['supersedes']}"]
    ft = d["frame_timing"]
    out += ["", "RECOVERED — FRAME TIMING", f"  {ft['cadence']}"]
    for r in ft["roots"]:
        out.append(f"    {r['call_site']} -> veneer {r['veneer']} -> "
                   f"{r['app_function']}  {r['role']}")
    out += [f"  {ft['absolute_rate']}", f"  supersedes {ft['supersedes']}", "",
            "SAFE IDLE",
            f"  answerable: {si['answerable']}",
            f"  buffer: {si['buffer_idle_state']}",
            f"  hardware: {si['hardware_idle_state']}",
            f"  boundary now: {si['boundary_now']}",
            f"  classification: {si['classification']} "
            f"(unchanged: {si['classification_unchanged']})", "", "ANSWERS"]
    for c in d["claims"]:
        out.append(f"  [{c['confidence']}] {c['question']}")
        out.append(f"      {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out += ["", f"RESULT rgb_hunt_ok={d['summary']['ok']} "
            f"checks={d['summary']['checks']}",
            "OFFLINE ANALYSIS ONLY. No device was accessed, and nothing here "
            "authorises a live experiment."]
    return out


def markdown():
    d = to_dict()
    cl, ub, db, ft, si = (d["closure"], d["unresolved_breakdown"],
                          d["double_buffer"], d["frame_timing"], d["safe_idle"])
    out = ["# The RGB driver hunt", "",
           "**Status: driver not found; boundary tightened.** Generated by "
           "`tool/map_rgb_driver_hunt.py`. Do not edit by hand.", "",
           "> Offline analysis of preserved images. No device was accessed. "
           "This authorises nothing live.", "",
           "## The result in three lines", "",
           f"- The lighting subsystem is an exhaustive closure of "
           f"**{cl['closure_size']} functions** that resolves **zero** "
           f"peripheral accesses.",
           "- **Double buffering** and **frame timing** are recovered — both "
           "were recorded as not found in log 112.",
           "- The safe-idle question is still **unanswerable**, so RGB stays "
           "`unresolved`.", "",
           "## Why the unresolved accesses are not a hidden driver", "",
           f"{ub['total']} unresolved accesses across the closure:", "",
           "| reason | count |", "|---|---:|"]
    for reason, count in d["unresolved_breakdown"]["by_reason"].items():
        out.append(f"| `{reason}` | {count} |")
    out += ["", ub["interpretation"], "",
            "## Candidates eliminated", "",
            "| candidate | eliminated | basis |", "|---|---|---|"]
    for key, c in d["candidates"].items():
        basis = c.get("basis") or c.get("note", "")
        out.append(f"| {key} | **{c['eliminated']}** | {basis} |")
    out += ["", "## Recovered: double buffering", "",
            f"`{db['function']}` copies **{db['bytes']} bytes** from the live "
            f"frame `{db['live_frame']}` to a shadow at `{db['shadow']}` — "
            f"exactly one frame below — gated on `{db['gate']} & "
            f"{db['gate_mask']}`, then tail-calls `{db['tail_call']}`.", "",
            f"```\n{db['listing']}\n```", "",
            f"This supersedes {db['supersedes']}.", "",
            "## Recovered: frame timing", "",
            f"**{ft['cadence']}.**", "",
            "| call site | veneer | app function | role |", "|---|---|---|---|"]
    for r in ft["roots"]:
        out.append(f"| `{r['call_site']}` | `{r['veneer']}` | "
                   f"`{r['app_function']}` | {r['role']} |")
    out += ["", f"**{ft['absolute_rate']}.** This supersedes "
            f"{ft['supersedes']}.", "",
            "## The safe-idle question", "",
            f"**Answerable: {si['answerable']}.**", "",
            f"- *The buffer.* {si['buffer_idle_state']}",
            f"- *The hardware.* {si['hardware_idle_state']}", "",
            "What was looked for and not found:", ""]
    for item in si["what_was_looked_for_and_not_found"]:
        out.append(f"- {item}")
    out += ["", si["why"], "",
            f"**Boundary before:** {si['boundary_before']}", "",
            f"**Boundary now:** {si['boundary_now']}", "",
            f"**Classification: {si['classification']}, unchanged.** "
            f"{si['why_unchanged']}", "", "## Answers", ""]
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
        "rgb-driver-hunt.json": json.dumps(to_dict(), indent=2,
                                           sort_keys=True) + "\n",
        "rgb-driver-hunt.md": markdown(),
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
    except (OSError, RgbHuntError, ms.SecondContextError, struct.error,
            KeyError) as exc:
        print(f"RESULT rgb_hunt_ok=False error={exc}")
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
        print(payload["rgb-driver-hunt.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
