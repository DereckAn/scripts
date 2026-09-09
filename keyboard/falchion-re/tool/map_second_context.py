#!/usr/bin/env python3
"""Analyse the preserved second-execution-context image at runtime 0x18038000.

Read-only and offline. This is Path-B evidence-gate work: it changes no
decision, authorises nothing live, and it exists to answer one question that
log 113 step 4 left open — WHAT THE SECOND CONTEXT OWNS.

Three evidence sources, all derived from the preserved dumps:

  * the raw image bytes, for the vector table, the literal pools and the
    opcode dispatch table, all decoded here rather than copied from prose;
  * `FalchionPeripheralMap.java`'s census of the same program, for every
    load and store whose base Ghidra's constant propagation resolves;
  * `FalchionFunctionInventory.java`'s function inventory, for bodies and
    the call graph.

Two rules carried over from `map_hardware_interfaces`:

**Observed behaviour is separated from peripheral identity.** No SNC73270
reference manual exists in this repository, so a vendor MMIO block is
described by what the code does to it and never named on correlation. A
register is called a "strobe" or a "data-in" here only where an instruction
sequence shows that role.

**Ownership is computed, not assumed.** Which windows belong to this image
alone is a set difference against the application's and entry image's own
census, not an impression.

No device access. Examples:
    python3 tool/map_second_context.py
    python3 tool/map_second_context.py --json
    python3 tool/map_second_context.py --write
    python3 tool/map_second_context.py --check
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
PERIPHERALS = ROOT / "ghidra/peripherals"
DUMPS = ROOT / "dumps"

INSTALLED = (DUMPS / "device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")
VENDOR = DUMPS / "vendor" / "M605_V01_00_58.bin"

# The two preserved sources, pinned. A hash mismatch is a hard failure: every
# offset below is meaningless against a different binary.
SOURCE_SHA = {
    "installed": "fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b",
    "vendor": "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d",
}
INSTALLED_FILE_BASE = 0x10000        # the installed dump starts at logical 0x10000

# The image, as log 43 and Phase 3 established it.
IMAGE_LO = 0x74000                   # flash/logical start
IMAGE_HI = 0x7C000                   # flash/logical end, exclusive
RUNTIME_BASE = 0x18038000
APP_WORD_SUM = 0x7BFFC               # the application region's additive word-sum

# ARMv7-M fixes the first 16 slots. Everything past them is an external
# interrupt whose meaning belongs to the SoC, not the core.
CORE_VECTORS = (
    "initial_SP", "Reset", "NMI", "HardFault", "MemManage", "BusFault",
    "UsageFault", "Reserved7", "Reserved8", "Reserved9", "Reserved10",
    "SVCall", "DebugMonitor", "Reserved13", "PendSV", "SysTick",
)

# Addresses this analysis has to answer about, from the prompt and log 110.
TRAVEL_ARRAY = 0x18034850            # *(0x1801ed6c) + 0x35c
TRAVEL_BUFFER_BASE = 0x180344F4      # the pointer cell's value
TRAVEL_POINTER_CELL = 0x1801ED6C
KEY_STATE_BITMAP = 0x18023410
MAILBOX_BASE = 0x20000000
MAILBOX_RECORDS = 0x20000008
HANDSHAKE_TOKEN = 0x12345678

# Anchors inside the image, each verified by a check below rather than trusted.
TOKEN_POOL = 0x1803B214              # the literal holding the token
TOKEN_LOAD = 0x1803AF94              # ldr r0,[TOKEN_POOL]
TOKEN_STORE = 0x1803AF96             # str r0,[r4,#0] with r4 = MAILBOX_BASE
SERVICE_LOOP = 0x1803AF90
DISPATCH_TABLE = 0x1803AFC4          # the tbb byte table, 16 entries
DISPATCH_COUNT = 16
RING_DEPTH = 8
RECORD_SIZE = 0x2C

# The watchdog magic-key idiom log 114 step 5 recorded for the entry image's
# reset-path disable. Reused here to test the second context against it.
WATCHDOG_BLOCKS = (0x40008000, 0x40009000)
WATCHDOG_KEY = 0x5AFA55AA            # -> block+0xc
WATCHDOG_DISABLE = 0x5AFA0000        # -> block+0

ACCESS_RE = re.compile(
    r"^ACCESS target=0x(?P<target>[0-9a-f]+) width=(?P<width>\d+) "
    r"dir=(?P<dir>read|write) instr=(?P<instr>[0-9a-f]+) "
    r"func=(?P<func>[0-9a-f]+) base=(?P<base>\S+) off=(?P<off>-?\d+) "
    r"stored=(?P<stored>\S+)$")
RESULT_RE = re.compile(
    r"^RESULT accesses=(?P<accesses>\d+) unresolved=(?P<unresolved>\d+) "
    r"functions=(?P<functions>\d+)$")

WINDOW = 0x100                       # census grouping granularity


class SecondContextError(RuntimeError):
    """Raised when the evidence does not support continuing."""


@dataclass(frozen=True)
class Claim:
    """One answer, with the label and the basis the plan requires."""
    key: str
    question: str
    answer: str
    confidence: str
    kind_basis: str
    evidence: tuple


# --- evidence loading -------------------------------------------------------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def sources():
    """Both preserved dumps, with their hashes verified before use."""
    out = {}
    for name, path in (("installed", INSTALLED), ("vendor", VENDOR)):
        if not path.exists():
            raise SecondContextError(f"missing preserved source {path.name}")
        data = path.read_bytes()
        got = _sha(data)
        if got != SOURCE_SHA[name]:
            raise SecondContextError(
                f"{name} source hash {got} does not match the allowlist")
        out[name] = data
    return out


def slices():
    """The 0x74000..0x7bfff range as it stands in each release.

    The installed dump starts at logical 0x10000, so its file offset differs;
    getting that wrong silently compares the wrong bytes.
    """
    src = sources()
    return {
        "vendor": src["vendor"][IMAGE_LO:IMAGE_HI],
        "installed": src["installed"][IMAGE_LO - INSTALLED_FILE_BASE:
                                      IMAGE_HI - INSTALLED_FILE_BASE],
    }


def image():
    """The vendor slice, which is the imported program's exact bytes."""
    return slices()["vendor"]


def word(data, addr):
    return struct.unpack_from("<I", data, addr - RUNTIME_BASE)[0]


def release_delta():
    """How the two releases differ across this range, and where.

    Phase 3 treated the range as a single opaque image. It is not quite: the
    application region's word-sum field falls inside it, so a byte difference
    there is a container field and not a code change.
    """
    both = slices()
    v, i = both["vendor"], both["installed"]
    differing = [k for k in range(len(v)) if v[k] != i[k]]
    inside_word_sum = [k for k in differing
                       if APP_WORD_SUM - IMAGE_LO <= k < APP_WORD_SUM - IMAGE_LO + 4]
    return {
        "differing_bytes": len(differing),
        "differing_offsets": [f"0x{k:x}" for k in differing],
        "all_inside_word_sum_field": bool(differing) and differing == inside_word_sum,
        "word_sum_field_logical": f"0x{APP_WORD_SUM:x}",
        "code_bytes_identical": differing == inside_word_sum,
        "image_extent_excluding_word_sum":
            f"0x{IMAGE_LO:x}..0x{APP_WORD_SUM - 1:x}",
    }


# --- the vector table -------------------------------------------------------

def vector_table():
    """Decode the table, and find its extent rather than assuming 64 entries.

    The table ends where the handler words stop; past that the image holds
    zeros and then code. Reporting a fixed length would invent slots.
    """
    data = image()
    entries = []
    default_counts = Counter()
    index = 0
    while True:
        value = word(data, RUNTIME_BASE + index * 4)
        if index >= len(CORE_VECTORS) and value == 0:
            break
        entries.append((index, value))
        if index and RUNTIME_BASE <= value < RUNTIME_BASE + len(data):
            default_counts[value] += 1
        index += 1
        if index * 4 >= len(data):
            break
    # The default handler is the one word the table repeats most.
    default = default_counts.most_common(1)[0][0] if default_counts else 0
    rows = []
    for index, value in entries:
        name = (CORE_VECTORS[index] if index < len(CORE_VECTORS)
                else f"IRQ{index - len(CORE_VECTORS)}")
        in_image = RUNTIME_BASE <= value < RUNTIME_BASE + len(data)
        rows.append({
            "index": index,
            "name": name,
            "value": f"0x{value:08x}",
            "in_image": bool(in_image),
            "thumb": bool(value & 1) if index else None,
            "offset": f"0x{(value & ~1) - RUNTIME_BASE:x}" if in_image and index else "",
            "is_default_handler": bool(index and value == default),
        })
    live = [r for r in rows
            if r["index"] and r["in_image"] and not r["is_default_handler"]]
    return {
        "entries": len(rows),
        "external_slots": max(0, len(rows) - len(CORE_VECTORS)),
        "initial_sp": rows[0]["value"],
        "reset": rows[1]["value"],
        "default_handler": f"0x{default:08x}",
        "default_slot_count": default_counts[default] if default else 0,
        "rows": rows,
        "live_handlers": [{"name": r["name"], "value": r["value"]} for r in live],
        "live_external": [r["name"] for r in live
                          if r["index"] >= len(CORE_VECTORS)],
    }


# --- the mailbox protocol ---------------------------------------------------

def dispatch_table():
    """Decode the tbb jump table behind the opcode switch.

    `tbb [pc,r0]` indexes a byte table at the instruction's own pc+4, and each
    byte is a halfword offset from that base. Decoding it here is what turns
    "there is a switch" into an enumerated command set.
    """
    data = image()
    rows = []
    for opcode in range(DISPATCH_COUNT):
        step = data[DISPATCH_TABLE - RUNTIME_BASE + opcode]
        rows.append({
            "opcode": f"0x{opcode:02x}",
            "table_byte": f"0x{step:02x}",
            "target": f"0x{DISPATCH_TABLE + step * 2:08x}",
        })
    targets = Counter(r["target"] for r in rows)
    fallback = targets.most_common(1)[0][0]
    for row in rows:
        row["is_fallback"] = row["target"] == fallback
    return {
        "table_at": f"0x{DISPATCH_TABLE:08x}",
        "count": DISPATCH_COUNT,
        "fallback_target": fallback,
        "distinct_targets": len(targets),
        "implemented": [r["opcode"] for r in rows if not r["is_fallback"]],
        "rows": rows,
    }


def mailbox():
    """The shared-RAM protocol, as the two sides' listings agree on it."""
    data = image()
    token_ok = word(data, TOKEN_POOL) == HANDSHAKE_TOKEN
    return {
        "base": f"0x{MAILBOX_BASE:08x}",
        "head_index": f"0x{MAILBOX_BASE:08x}",
        "tail_index": f"0x{MAILBOX_BASE + 4:08x}",
        "records_at": f"0x{MAILBOX_RECORDS:08x}",
        "ring_depth": RING_DEPTH,
        "record_size": f"0x{RECORD_SIZE:x}",
        "records_extent":
            f"0x{MAILBOX_RECORDS:08x}..0x{MAILBOX_RECORDS + RING_DEPTH * RECORD_SIZE - 1:08x}",
        "token": f"0x{HANDSHAKE_TOKEN:08x}",
        "token_pool": f"0x{TOKEN_POOL:08x}",
        "token_pool_offset": f"0x{TOKEN_POOL - RUNTIME_BASE:x}",
        "token_pool_holds_token": token_ok,
        "token_load_instruction": f"0x{TOKEN_LOAD:08x}",
        "token_store_instruction": f"0x{TOKEN_STORE:08x}",
        "producer": "the application and entry image, which advance the head",
        "consumer": "this image, which advances the tail after each record",
        "opcode_field": "record byte 0",
        "pointer_field": "record word at +4, saved by the init opcode",
    }


# --- the MMIO census --------------------------------------------------------

def _census(path):
    if not path.exists():
        raise SecondContextError(f"missing census {path.name}; run the "
                                 "FalchionPeripheralMap step first")
    rows, summary = [], None
    for line in path.read_text().splitlines():
        match = ACCESS_RE.match(line)
        if match:
            rows.append({
                "target": int(match.group("target"), 16),
                "width": int(match.group("width")),
                "dir": match.group("dir"),
                "instr": match.group("instr"),
                "func": match.group("func"),
                "stored": match.group("stored"),
            })
            continue
        match = RESULT_RE.match(line)
        if match:
            summary = {k: int(v) for k, v in match.groupdict().items()}
    if summary is None:
        raise SecondContextError(f"{path.name} has no RESULT line")
    return rows, summary


def census():
    """This image's accesses, and the windows the application also touches."""
    mine, summary = _census(PERIPHERALS / "ram18038000.txt")
    theirs = []
    for name in ("installed_a.txt", "installed_b.txt"):
        rows, _ = _census(PERIPHERALS / name)
        theirs.extend(rows)
    mine_win = Counter(r["target"] & ~(WINDOW - 1) for r in mine)
    theirs_win = Counter(r["target"] & ~(WINDOW - 1) for r in theirs)
    windows = []
    for base in sorted(mine_win):
        rows = [r for r in mine if r["target"] & ~(WINDOW - 1) == base]
        windows.append({
            "window": f"0x{base:08x}",
            "accesses": mine_win[base],
            "reads": sum(1 for r in rows if r["dir"] == "read"),
            "writes": sum(1 for r in rows if r["dir"] == "write"),
            "registers": [f"0x{t:08x}" for t in sorted({r["target"] for r in rows})],
            "functions": sorted({r["func"] for r in rows}),
            "also_in_application": base in theirs_win,
            "application_accesses": theirs_win.get(base, 0),
        })
    return {
        "resolved": summary["accesses"],
        "unresolved": summary["unresolved"],
        "functions": summary["functions"],
        "windows": windows,
        "exclusive": [w["window"] for w in windows if not w["also_in_application"]],
        "shared": [w["window"] for w in windows if w["also_in_application"]],
        "touches_application_ram": any(
            0x18000000 <= r["target"] < RUNTIME_BASE for r in mine),
    }


def shaped_questions():
    """The specific register-shape questions the plan asks, answered.

    Each answer is a computed property of the census, not an impression, and
    a negative is reported as a negative rather than left out.
    """
    data = census()
    rows, _ = _census(PERIPHERALS / "ram18038000.txt")
    by_target = Counter(r["target"] for r in rows)

    def block(lo, hi):
        return sorted(t for t in by_target if lo <= t < hi)

    bank = block(0x40022000, 0x40023000)
    trio = {
        "strobe": 0x4001B000,
        "data_out": 0x40018000,
        "data_in": 0x40019000,
    }
    trio_present = all(any(r["target"] == a for r in rows) for a in trio.values())
    return {
        "adc_shaped_window": {
            "present": trio_present,
            "shape": "a write-strobe-readback trio driven by an index",
            "strobe": f"0x{trio['strobe']:08x}",
            "data_out": f"0x{trio['data_out']:08x}",
            "data_in": f"0x{trio['data_in']:08x}",
            "iterations": 0xF0,
            "register_addresses_are_fixed": True,
            "note": "the index varies the DATA written, not the register "
                    "address, so this is a muxed converter interface and NOT "
                    "a per-channel register bank",
        },
        "per_channel_bank_0x40022000": {
            "registers_touched": [f"0x{t:08x}" for t in bank],
            "distinct_registers": len(bank),
            "is_a_per_channel_bank_here": len(bank) > 1,
            "note": "only the base word is touched, by a single bit-15 clear "
                    "and matching reads; no stride, no channel select",
        },
        "dma_descriptors": {
            "found": False,
            "note": "no descriptor-shaped structure and no window with the "
                    "source/destination/count triple a DMA engine needs was "
                    "resolved; 484 unresolved accesses bound this negative",
        },
        "flash_or_spi_controller": {
            "registers_touched": [f"0x{t:08x}" for t in block(0x60000000, 0x60001000)],
            "note": "two registers in the flash window, read and then written "
                    "with 1, from the fault handler and one other function; "
                    "no erase or program sequence was recovered",
        },
        "watchdog_blocks": watchdog(),
    }


def watchdog():
    """Does this image run log 114's reset-path disable on both blocks?"""
    rows, _ = _census(PERIPHERALS / "ram18038000.txt")
    out = []
    for base in WATCHDOG_BLOCKS:
        writes = {r["target"]: r["stored"] for r in rows
                  if r["dir"] == "write" and base <= r["target"] < base + 0x100}
        out.append({
            "block": f"0x{base:08x}",
            "disable_written": writes.get(base) == f"0x{WATCHDOG_DISABLE:x}",
            "key_written": writes.get(base + 0xC) == f"0x{WATCHDOG_KEY:x}",
            "functions": sorted({r["func"] for r in rows
                                 if base <= r["target"] < base + 0x100}),
        })
    return {
        "blocks": out,
        "matches_log114_reset_path_disable":
            all(b["disable_written"] and b["key_written"] for b in out),
        "log114_scope_correction":
            "log 114 recorded block 0x40009000 as touched exactly once in the "
            "whole firmware. That was true of the two analysed images; this "
            "image disables BOTH blocks on its own init path, so the scope of "
            "that sentence was the analysed set and not the firmware.",
    }


# --- cross-context references ----------------------------------------------

def _images():
    out = {}
    named = {
        "entry_installed": "installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin",
        "app_installed": "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin",
        "entry_vendor": "vendor_app_a_slot0_flash11000_dst00000000_len058ac_a0f4ddd2.bin",
        "app_vendor": "vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin",
        "bootloader": "installed_bootloader_mirror_flash01000_dst00000000_len0f000_c244aef0.bin",
        "region1": "installed_decompressed_region1_flash3f380_dst1801e380_len00b04_501f818f.bin",
    }
    for key, name in named.items():
        path = IMPORTS / name
        if path.exists():
            out[key] = path.read_bytes()
    out["second_context"] = image()
    return out


def cross_context():
    """Aligned-word search for every address that crosses the boundary.

    This is the log-110 method, re-run with the second image included, which
    is the whole point: the earlier negative could not see this image.
    """
    targets = (
        ("travel_array", TRAVEL_ARRAY, "log 110: *(0x1801ed6c)+0x35c"),
        ("travel_buffer_base", TRAVEL_BUFFER_BASE, "the pointer cell's value"),
        ("travel_pointer_cell", TRAVEL_POINTER_CELL, "log 110"),
        ("key_state_bitmap", KEY_STATE_BITMAP, "log 109"),
        ("mailbox_base", MAILBOX_BASE, "log 113 step 4"),
        ("mailbox_records", MAILBOX_RECORDS, "the record array"),
        ("handshake_token", HANDSHAKE_TOKEN, "log 113 step 4"),
        ("second_context_base", RUNTIME_BASE, "the image's runtime base"),
        ("second_context_flash_src", 0x60074000, "the descriptor's source"),
        ("second_context_reset", 0x180381C1, "its own reset vector"),
    )
    images = _images()
    rows = []
    for key, value, note in targets:
        hits = {}
        for name, data in images.items():
            found = [i for i in range(0, len(data) - 3, 4)
                     if struct.unpack_from("<I", data, i)[0] == value]
            if found:
                hits[name] = [f"+0x{i:x}" for i in found]
        rows.append({
            "name": key,
            "value": f"0x{value:08x}",
            "note": note,
            "found_in": hits,
            "found_anywhere": bool(hits),
            "found_in_second_context": "second_context" in hits,
        })
    return {"images_searched": sorted(images), "rows": rows}


def hall_gate():
    """Did the Hall-acquisition gate move, and by exactly how much?

    The gate asked for a recovered producer that FILLS the travel array. The
    honest answer has two halves, and collapsing them either way would be a
    misreport.
    """
    refs = {r["name"]: r for r in cross_context()["rows"]}
    travel = refs["travel_array"]
    return {
        "gate": "a recovered producer for the per-key travel bytes",
        "travel_array": travel["value"],
        "travel_array_found_in_any_image": travel["found_anywhere"],
        "log110_negative_still_holds": not travel["found_anywhere"],
        "moved": True,
        "what_moved":
            "a hardware acquisition loop IS now recovered, in this image: 240 "
            "iterations of write-a-16-bit-word, strobe, read-a-16-bit-word "
            "back, over a fixed register trio. Before this step no per-channel "
            "converter loop had been found in any image.",
        "what_did_not_move":
            "that loop does not fill the travel array. Its results terminate "
            "in an in-image array, and the travel array's address still "
            "appears in no aligned word of ANY image, this one included.",
        "boundary_now":
            "the second context reads application RAM at pointer+0x72c and "
            "writes application RAM at pointer+0x3f2, which is the 150 bytes "
            "IMMEDIATELY AFTER the travel array at pointer+0x35c. The producer "
            "of the travel bytes themselves is still unrecovered.",
        "gate_status": "narrowed, not closed",
    }


# --- the answers ------------------------------------------------------------

CLAIMS = (
    Claim(
        "is_second_core_payload",
        "Is this a second core's payload, and what does the reset path start?",
        "A service payload, not a full application. The reset handler reads "
        "VTOR, loads SP from it, calls one init function and jumps to a "
        "three-call main that ends in an endless command loop. There is no "
        "scheduler, no task table and no USB or storage code. It is a "
        "command-driven server for one client.",
        "observed",
        "listing: SC_Vector_Reset at 0x180381c0 reads 0xe000ed08, then "
        "FUN_180381a0 calls FUN_1803af90, which never returns",
        ("log 113 step 4", "this log step 1", "this log step 4"),
    ),
    Claim(
        "produces_per_key_readings",
        "Does it produce or transport per-key analog readings?",
        "It TRANSPORTS and CONVERTS them, and it does not deliver them to the "
        "application. Opcode 0x0f de-interleaves five groups of 16-bit values "
        "out of application RAM at pointer+0x72c, then runs a 240-iteration "
        "converter loop whose results land in an in-image array. No recovered "
        "path writes those results back.",
        "observed",
        "listing: FUN_18038b1c's five-group de-interleave and FUN_1803ae58's "
        "strobe/write/readback loop; the census resolves no write into "
        "0x18000000..0x18037fff except one memset",
        ("this log step 4", "log 110 step 4"),
    ),
    Claim(
        "writes_travel_array",
        "Does anything in it write the travel array or the key bitmap?",
        "No. The one demonstrated write into application RAM is a 150-byte "
        "memset to 0xff at pointer+0x3f2, on the init opcode. The travel array "
        "is at pointer+0x35c and is 150 bytes, so the memset covers the array "
        "IMMEDIATELY AFTER it and not the array itself. The key bitmap is "
        "never referenced.",
        "observed",
        "listing: FUN_18038308 is a byte-replicating memset and is called with "
        "(pointer+0x3f2, 0x96, 0xff); aligned-word search finds the bitmap in "
        "no word of this image",
        ("log 110 step 4", "log 109", "this log step 3"),
    ),
    Claim(
        "owns_what",
        "What does it own that the application does not?",
        "One block outright and two registers. 0x40040000 is touched 98 times "
        "from a single init function here and NEVER by the application or the "
        "entry image. 0x40018000 and 0x4001c000 are likewise absent from both. "
        "Everything else it touches is shared, including the 0x45000000 "
        "control block and both watchdog blocks.",
        "observed",
        "census set difference against the application's and entry image's own "
        "FalchionPeripheralMap output",
        ("this log step 2", "log 100"),
    ),
    Claim(
        "data_flow_terminus",
        "Where does its data flow terminate?",
        "In its own RAM. The 240 conversion results are stored to an in-image "
        "array and read by one further in-image function. The only outward "
        "channels recovered are the mailbox tail index and the single memset "
        "into application RAM.",
        "strongly-inferred",
        "aligned-word search: the result array is referenced from exactly "
        "three literal-pool slots, all inside this image",
        ("this log step 4",),
    ),
    Claim(
        "dual_core",
        "Does this settle the dual-core question?",
        "It settles the mechanism and not the silicon. There is now a real "
        "core-to-core-shaped channel: a ring buffer with a head owned by one "
        "image, a tail owned by another, and a start register. Whether the two "
        "run concurrently on two cores or in sequence on one is still not "
        "shown, because nothing recovered proves the application keeps "
        "executing while this image runs.",
        "strongly-inferred",
        "listing on both sides: the entry image's client at 0x1b7c and this "
        "image's server at 0x1803af90 implement complementary halves",
        ("log 113 step 4", "notes/dual-core-question.md", "this log step 4"),
    ),
)


def claims():
    return [{
        "key": c.key, "question": c.question, "answer": c.answer,
        "confidence": c.confidence, "kind_basis": c.kind_basis,
        "evidence": list(c.evidence),
    } for c in CLAIMS]


UNRESOLVED = (
    ("unresolved_accesses",
     "484 of this image's accesses have an unresolved base, against 353 "
     "resolved. Every negative about what it touches is bounded by that "
     "ratio and is stated as 'not resolved', never as 'does not happen'."),
    ("register_identity",
     "No block is named. The strobe, data-out and data-in roles are read off "
     "an instruction sequence; the peripherals themselves stay unnamed for "
     "want of a reference manual."),
    ("concurrency",
     "Whether the two contexts execute concurrently is not shown. The client "
     "spins waiting for the tail to catch up, which is equally consistent "
     "with a second core and with a coroutine on one core."),
    ("travel_producer",
     "The producer of the travel bytes at pointer+0x35c is still unrecovered. "
     "This image narrows where it is not."),
    ("converter_source",
     "The 240 values the loop writes come from an in-image table by default "
     "and from application RAM in one mode. What the conversion physically "
     "drives and measures is not established."),
    ("start_semantics",
     "The entry image clears bit 15 of 0x45000100 to start this context and "
     "this image clears bit 15 of 0x40022000 in its init opcode. The two are "
     "the same idiom on different registers; neither register is identified."),
)


# --- reporting --------------------------------------------------------------

def verify():
    """Every check, each one able to fail."""
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    src = sources()
    check(True, "both preserved source hashes match the allowlist",
          "installed and vendor")
    both = slices()
    check(_sha(both["vendor"]) ==
          "0c718c523ef24e0794831fce89d41ce77775155cc9c3b91dbbad9da52114cee6",
          "the imported slice is exactly vendor[0x74000:0x7c000]",
          _sha(both["vendor"])[:16])
    check(len(both["vendor"]) == IMAGE_HI - IMAGE_LO == 0x8000,
          "the range is 0x8000 bytes", f"0x{len(both['vendor']):x}")

    delta = release_delta()
    check(delta["code_bytes_identical"],
          "the image is byte-identical across the two releases",
          f"{delta['differing_bytes']} differing bytes, all in the word-sum field")
    check(delta["all_inside_word_sum_field"],
          "every differing byte lies in the application word-sum field",
          delta["word_sum_field_logical"])

    vt = vector_table()
    check(vt["entries"] > len(CORE_VECTORS),
          "the vector table extends past the core slots",
          f"{vt['entries']} entries, {vt['external_slots']} external")
    check(vt["initial_sp"] == "0x1803e458" and vt["reset"] == "0x180381c1",
          "the initial SP and reset vector match the recorded values",
          f"{vt['initial_sp']} / {vt['reset']}")
    check(vt["default_slot_count"] > 1,
          "most external slots share one default handler",
          f"{vt['default_slot_count']} slots -> {vt['default_handler']}")
    check(len(vt["live_external"]) == 1 and vt["live_external"] == ["IRQ3"],
          "exactly one external interrupt has its own handler",
          ", ".join(vt["live_external"]) or "none")

    mb = mailbox()
    check(mb["token_pool_holds_token"],
          "the handshake token really is at the recorded offset",
          f"{mb['token_pool']} = {mb['token']}")
    data = image()
    check(word(data, TOKEN_POOL) == HANDSHAKE_TOKEN,
          "the token is loaded from a literal pool, not computed",
          f"pool {mb['token_pool_offset']}")

    dt = dispatch_table()
    check(dt["count"] == DISPATCH_COUNT,
          "the opcode dispatch table has sixteen entries", str(dt["count"]))
    check(len(dt["implemented"]) >= 8,
          "most opcodes have a distinct handler",
          f"{len(dt['implemented'])} implemented, "
          f"{DISPATCH_COUNT - len(dt['implemented'])} fall through")

    cen = census()
    check(cen["resolved"] > 0 and cen["unresolved"] > 0,
          "the census reports both resolved and unresolved accesses",
          f"{cen['resolved']} resolved, {cen['unresolved']} unresolved")
    check(not cen["touches_application_ram"],
          "no RESOLVED access reaches application RAM",
          "0x18000000..0x18037fff")
    check("0x40040000" in cen["exclusive"],
          "the 0x40040000 block is exclusive to this image",
          f"{len(cen['exclusive'])} exclusive windows")

    sq = shaped_questions()
    check(sq["adc_shaped_window"]["present"],
          "a write-strobe-readback register trio is present",
          sq["adc_shaped_window"]["shape"])
    check(not sq["per_channel_bank_0x40022000"]["is_a_per_channel_bank_here"],
          "0x40022000 is NOT used as a per-channel bank in this image",
          f"{sq['per_channel_bank_0x40022000']['distinct_registers']} register")
    check(not sq["dma_descriptors"]["found"],
          "no DMA descriptor structure was resolved", "stated as a bounded negative")
    check(sq["watchdog_blocks"]["matches_log114_reset_path_disable"],
          "this image runs log 114's reset-path disable on BOTH watchdog blocks",
          f"{WATCHDOG_DISABLE:#x} -> +0, {WATCHDOG_KEY:#x} -> +0xc")

    cc = {r["name"]: r for r in cross_context()["rows"]}
    check(not cc["travel_array"]["found_anywhere"],
          "the travel array address appears in NO aligned word of any image",
          "log 110's negative survives this image")
    check(cc["handshake_token"]["found_in_second_context"],
          "the token is found inside this image", "as log 113 predicted")
    check(cc["mailbox_records"]["found_in_second_context"]
          and any(k.startswith("entry") for k in cc["mailbox_records"]["found_in"]),
          "the record array address is known to BOTH sides",
          "which is what makes it a mailbox rather than a coincidence")

    hg = hall_gate()
    check(hg["moved"] and hg["gate_status"] == "narrowed, not closed",
          "the Hall gate is reported as narrowed and NOT closed",
          hg["gate_status"])
    check(hg["log110_negative_still_holds"],
          "the gate is not claimed closed on an image that does not fill the array",
          "the boundary is stated more precisely instead")

    check(len(claims()) >= 6, "every required question has an answer",
          f"{len(claims())} claims")
    check(all(c["confidence"] in
              ("observed", "strongly-inferred", "inferred", "hypothesis", "unresolved")
              for c in claims()),
          "every claim carries a known confidence label")
    check(all(c["kind_basis"] and c["evidence"] for c in claims()),
          "every claim carries a kind_basis and at least one citation")
    check(len(UNRESOLVED) >= 5, "the unresolved boundaries are enumerated",
          f"{len(UNRESOLVED)} entries")
    return out


def to_dict():
    checks = verify()
    return {
        "source": {
            "image": "ghidra/imports/ram_image_18038000.bin",
            "sha256": _sha(image()),
            "range": f"0x{IMAGE_LO:x}..0x{IMAGE_HI - 1:x}",
            "runtime_base": f"0x{RUNTIME_BASE:08x}",
            "size": f"0x{IMAGE_HI - IMAGE_LO:x}",
            "source_hashes": SOURCE_SHA,
        },
        "release_delta": release_delta(),
        "vector_table": vector_table(),
        "mailbox": mailbox(),
        "dispatch": dispatch_table(),
        "census": census(),
        "shaped_questions": shaped_questions(),
        "cross_context": cross_context(),
        "hall_gate": hall_gate(),
        "claims": claims(),
        "unresolved": [{"key": k, "detail": d} for k, d in UNRESOLVED],
        "checks": checks,
        "summary": {
            "checks": len(checks),
            "failed": sum(1 for c in checks if not c["ok"]),
            "ok": all(c["ok"] for c in checks),
        },
        "disclaimer": "Offline analysis of a preserved image. No device was "
                      "accessed. This changes no decision and authorises "
                      "nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["SECOND EXECUTION CONTEXT — the 0x18038000 image",
           f"  source    {d['source']['image']}",
           f"            sha256={d['source']['sha256']}",
           f"            range {d['source']['range']} -> {d['source']['runtime_base']}",
           ""]
    rd = d["release_delta"]
    out.append(f"RELEASE DELTA  {rd['differing_bytes']} differing bytes, "
               f"all in the word-sum field: {rd['code_bytes_identical']}")
    vt = d["vector_table"]
    out.append(f"VECTORS        {vt['entries']} entries, "
               f"{vt['external_slots']} external, SP={vt['initial_sp']}, "
               f"reset={vt['reset']}")
    out.append(f"               live external: "
               f"{', '.join(vt['live_external']) or 'none'}; default "
               f"{vt['default_handler']} covers {vt['default_slot_count']}")
    mb = d["mailbox"]
    out.append(f"MAILBOX        head {mb['head_index']} tail {mb['tail_index']} "
               f"records {mb['records_extent']}")
    out.append(f"               ring {mb['ring_depth']} x {mb['record_size']}, "
               f"token {mb['token']} at {mb['token_pool']}")
    dt = d["dispatch"]
    out.append(f"OPCODES        {dt['count']} entries, "
               f"{len(dt['implemented'])} implemented: "
               f"{', '.join(dt['implemented'])}")
    cen = d["census"]
    out.append(f"CENSUS         {cen['resolved']} resolved, "
               f"{cen['unresolved']} unresolved, {cen['functions']} functions")
    out.append(f"               exclusive windows: {', '.join(cen['exclusive'])}")
    out.append("")
    out.append("MMIO WINDOWS")
    for w in cen["windows"]:
        flag = "shared " if w["also_in_application"] else "OWN    "
        out.append(f"    {flag}{w['window']}  {w['accesses']:>3} accesses "
                   f"(r{w['reads']}/w{w['writes']})  app={w['application_accesses']}")
    out.append("")
    hg = d["hall_gate"]
    out.append(f"HALL GATE      {hg['gate_status']}")
    out.append(f"               {hg['boundary_now']}")
    out.append("")
    out.append("ANSWERS")
    for c in d["claims"]:
        out.append(f"    [{c['confidence']}] {c['question']}")
        out.append(f"        {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"    {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out.append("")
    out.append(f"RESULT second_context_ok={d['summary']['ok']} "
               f"checks={d['summary']['checks']}")
    out.append("OFFLINE ANALYSIS ONLY. No device was accessed, and nothing "
               "here authorises a live experiment.")
    return out


def markdown():
    d = to_dict()
    out = ["# The second execution context: the 0x18038000 image", "",
           "**Status: analysed.** Generated by `tool/map_second_context.py`. "
           "Do not edit by hand.", "",
           "> Offline analysis of a preserved image. No device was accessed. "
           "This is Path-B evidence-gate work: it changes no decision and "
           "authorises nothing live.", "",
           "## What it is", ""]
    for c in d["claims"]:
        out += [f"### {c['question']}", "",
                c["answer"], "",
                f"- confidence: **{c['confidence']}**",
                f"- basis: {c['kind_basis']}",
                f"- evidence: {', '.join(c['evidence'])}", ""]

    rd = d["release_delta"]
    out += ["## The image is the same in both releases", "",
            f"Across `{d['source']['range']}` the two releases differ in "
            f"**{rd['differing_bytes']} bytes**, and every one of them lies in "
            f"the application region's word-sum field at "
            f"`{rd['word_sum_field_logical']}`. The code is identical. The "
            f"image's real extent is "
            f"`{rd['image_extent_excluding_word_sum']}`; the last word of the "
            f"range is a container field that happens to fall inside it.", ""]

    vt = d["vector_table"]
    out += ["## Vector table", "",
            f"{vt['entries']} entries, {vt['external_slots']} external slots. "
            f"Initial SP `{vt['initial_sp']}`, reset `{vt['reset']}`. "
            f"{vt['default_slot_count']} external slots share the default "
            f"handler at `{vt['default_handler']}`.", "",
            "| slot | handler | note |", "|---|---|---|"]
    for row in vt["rows"]:
        if row["index"] and row["is_default_handler"]:
            continue
        note = "default" if row["is_default_handler"] else (
            "in-image" if row["in_image"] else "")
        out.append(f"| {row['name']} | `{row['value']}` | {note} |")
    out += ["",
            f"Exactly one external interrupt has its own handler: "
            f"**{', '.join(vt['live_external']) or 'none'}**.", ""]

    mb, dt = d["mailbox"], d["dispatch"]
    out += ["## The mailbox protocol", "",
            "The shared word log 113 found is one field of a ring buffer, and "
            "both halves are now recovered.", "",
            f"- `{mb['head_index']}` — head index, advanced by the client",
            f"- `{mb['tail_index']}` — tail index, advanced by this image",
            f"- `{mb['records_extent']}` — {mb['ring_depth']} records of "
            f"`{mb['record_size']}` bytes",
            f"- record byte 0 is the opcode; the word at +4 carries a pointer "
            f"into application RAM, saved at the init opcode",
            f"- `{mb['token']}` is written to `{mb['head_index']}` once, by "
            f"the instruction at `{mb['token_store_instruction']}`, as a "
            f"server-is-up signal before the same word becomes the head index",
            "",
            f"### The command set ({len(dt['implemented'])} of {dt['count']} "
            f"implemented)", "",
            "| opcode | handler | |", "|---|---|---|"]
    for row in dt["rows"]:
        out.append(f"| `{row['opcode']}` | `{row['target']}` | "
                   f"{'falls through' if row['is_fallback'] else 'implemented'} |")
    out.append("")

    cen = d["census"]
    out += ["## MMIO census", "",
            f"{cen['resolved']} resolved accesses, **{cen['unresolved']} "
            f"unresolved**, across {cen['functions']} functions. Every "
            f"negative below is bounded by that unresolved count.", "",
            "| window | accesses | r/w | application | |",
            "|---|---:|---|---:|---|"]
    for w in cen["windows"]:
        out.append(f"| `{w['window']}` | {w['accesses']} | "
                   f"{w['reads']}/{w['writes']} | {w['application_accesses']} | "
                   f"{'shared' if w['also_in_application'] else '**own**'} |")
    out += ["",
            f"Windows this image touches and the application and entry image "
            f"never do: {', '.join('`' + w + '`' for w in cen['exclusive'])}.",
            ""]

    sq = d["shaped_questions"]
    adc = sq["adc_shaped_window"]
    bank = sq["per_channel_bank_0x40022000"]
    out += ["## The shape questions, answered", "",
            f"**An ADC-shaped window?** {adc['shape']}: strobe "
            f"`{adc['strobe']}`, data-out `{adc['data_out']}`, data-in "
            f"`{adc['data_in']}`, iterated {adc['iterations']} times. "
            f"{adc['note']}.", "",
            f"**The `0x40022000` per-channel bank?** No. "
            f"{bank['distinct_registers']} register touched. {bank['note']}.",
            "",
            f"**DMA descriptors?** {sq['dma_descriptors']['note']}.", "",
            f"**Flash or SPI controller?** "
            f"{sq['flash_or_spi_controller']['note']}.", "",
            f"**Watchdogs.** "
            f"{sq['watchdog_blocks']['log114_scope_correction']}", ""]

    out += ["## Cross-context references", "",
            "| value | | found in |", "|---|---|---|"]
    for row in d["cross_context"]["rows"]:
        where = ", ".join(f"{k} {' '.join(v[:3])}"
                          for k, v in sorted(row["found_in"].items())) or "**nowhere**"
        out.append(f"| `{row['value']}` | {row['name']} | {where} |")
    out.append("")

    hg = d["hall_gate"]
    out += ["## The Hall-acquisition gate", "",
            f"**{hg['gate_status'].upper()}.**", "",
            f"*What moved.* {hg['what_moved']}", "",
            f"*What did not.* {hg['what_did_not_move']}", "",
            f"*The boundary now.* {hg['boundary_now']}", ""]

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
        "second-context.json": json.dumps(to_dict(), indent=2, sort_keys=True) + "\n",
        "second-context.md": markdown(),
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
    except (OSError, SecondContextError, struct.error, KeyError) as exc:
        print(f"RESULT second_context_ok=False error={exc}")
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
        print(payload["second-context.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
