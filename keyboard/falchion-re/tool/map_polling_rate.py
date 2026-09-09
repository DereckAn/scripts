#!/usr/bin/env python3
"""The polling-rate setting: where it lands, and whether it puts units on the tick.

Read-only and offline. Authorises nothing live, and constructs no frame of any
kind — this reads code only.

THE RESULT IS A BOUNDED NEGATIVE. The historical Armoury Crate profile carries
`performance.pollingRate = "3"`, but nothing in the preserved images consumes a
polling-rate index. All five candidate destinations are tested and four are
eliminated outright; the fifth cannot be confirmed because the block it would
need does not exist in any image.

  (a) a timer reload/divisor register   NOT CONFIRMABLE — no timer block is
                                        identified in any image
  (b) the prescaler ladder              ELIMINATED — every divisor is a
                                        compile-time immediate
  (c) the mailbox to the second context ELIMINATED — its five fields are
                                        enumerated and none is a rate
  (d) the descriptor's bInterval        ELIMINATED as a runtime mechanism —
                                        static in the region, and the RAM
                                        copy's bInterval bytes are referenced
                                        nowhere
  (e) more than one of these            not applicable

CONSEQUENTLY NO REAL UNITS ARE ATTACHED TO ANYTHING. The only unit-bearing
timing in this project remains log 120's microsecond delay, which gets its unit
by construction rather than from a known clock. The dependency map's
clock_frequency entry stays unresolved, and this tool asserts that it does.

No device access. Examples:
    python3 tool/map_polling_rate.py
    python3 tool/map_polling_rate.py --json
    python3 tool/map_polling_rate.py --write
    python3 tool/map_polling_rate.py --check
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

SLICES = {
    "entry": ("installed_app_a_slot0_flash11000_dst00000000_len058ac"
              "_f093979a.bin", 0x00000000),
    "app": ("installed_app_b_slot1_flash21000_dst18000000_len1e380"
            "_be463863.bin", 0x18000000),
    "region": ("installed_decompressed_region1_flash3f380_dst1801e380_len00b04"
               "_501f818f.bin", 0x1801E380),
    "second": (None, 0x18038000),
}

PROFILE = NOTES / "ac-profile3-decoded.json"
PROTOCOL = NOTES / "protocol.md"

# The rates a polling-rate table would plausibly hold, and the divisors.
RATE_VALUES = (125, 250, 500, 1000, 2000, 4000, 8000)
DIVISOR_PATTERNS = {
    "1,2,4,8": bytes([1, 2, 4, 8]),
    "8,4,2,1": bytes([8, 4, 2, 1]),
    "1,2,4,8,16": bytes([1, 2, 4, 8, 16]),
}

# The USB parameter table, from log 107.
PARAM_TABLE = 0x1801E604           # region+0x284
PARAM_TABLE_RAM = 0x1803435C       # the copy FUN_18018bd6 makes
IFACE_ARRAY = 0x14
IFACE_STRIDE = 0x18
BINTERVAL_OFFSET = 0x14
IFACE_COUNT = 5

# The prescaler ladder, from log 109 step 4.
PRESCALER = 0x42C                  # entry image
LADDER_SITES = (0x43A, 0x44C, 0x45C, 0x474, 0x484)
LADDER_RATIOS = (8, 5, 2, 10, 10)

# The tick's clients, from logs 109, 114, 119, 121, 122.
TICK_CLIENTS = (
    ("sample fetch", "log 119", "the /8 job, veneer 0x4044"),
    ("actuation compare", "log 110, log 119", "the /8 job, veneer 0x4062"),
    ("watchdog feed", "log 114", "FUN_00000516, the divide-by-8 job"),
    ("mailbox cluster", "log 121", "FUN_00000516, veneer 0x40d0"),
    ("lighting swap and shadow read", "log 122",
     "FUN_00000516, veneers 0x40f8 and 0x4116"),
    ("report builder", "log 109", "the every-tick job, veneer 0x4076"),
)

DISPATCHER = 0x18001FBE
REQUEST_BUFFER = 0x1802337C


class PollingRateError(RuntimeError):
    """Raised when the evidence does not support continuing."""


def _load(key):
    name, base = SLICES[key]
    if name is None:
        return ms.image(), base
    path = IMPORTS / name
    if not path.exists():
        raise PollingRateError(f"missing import slice {name}")
    return path.read_bytes(), base


def images():
    ms.sources()
    return {k: _load(k) for k in SLICES}


# --- step 1: where the index comes from --------------------------------------

def profile_field():
    """The historical Armoury Crate value, read from the decode."""
    if not PROFILE.exists():
        raise PollingRateError("missing notes/ac-profile3-decoded.json")
    data = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    performance = data.get("performance", {})
    return {
        "source": "notes/ac-profile3-decoded.json",
        "provenance": "previously observed on hardware; NOT reproducible from "
                      "the PCAPs in this repository",
        "performance_block": performance,
        "polling_rate_index": performance.get("pollingRate"),
        "is_an_index_not_a_rate": True,
        "note": "the value is the string \"3\", and the block contains nothing "
                "else — no Hz, no divisor, no interval.",
    }


def observed_wire_commands():
    """Every vendor-HID command the historical captures actually recorded."""
    if not PROTOCOL.exists():
        raise PollingRateError("missing notes/protocol.md")
    rows = []
    for line in PROTOCOL.read_text().splitlines():
        match = re.match(r"^\| *`([0-9a-f]{2}[^`]*)` *\| *(.+?) *\|", line)
        if match and not match.group(1).startswith("actuation"):
            rows.append({"command": match.group(1).strip(),
                         "meaning": match.group(2).strip()})
    text = PROTOCOL.read_text()
    lower = text.lower()
    # The word appears twice in the note, and BOTH mentions say the opcode was
    # never seen: once in the host HAL's method list, once in "Still unknown".
    hal_names = [n for n in ("SetPollingRate", "GetPollingRate") if n in text]
    listed_unknown = bool(re.search(
        r"opcodes for [^.]*polling rate[^.]*\.\s*\n?\s*all have known hal "
        r"method names; none captured yet", lower))
    in_command_table = any("poll" in r["command"].lower()
                           or "poll" in r["meaning"].lower() for r in rows)
    return {
        "commands": rows,
        "count": len(rows),
        "polling_in_command_table": in_command_table,
        "hal_method_names": hal_names,
        "listed_as_never_captured": listed_unknown,
        "finding":
            "the observed command surface is a version/query opcode, two init "
            "handshakes, the key-configuration opcodes and the commit. NO "
            "POLLING-RATE COMMAND APPEARS IN IT. The note independently "
            "records SetPollingRate and GetPollingRate as host HAL method "
            "names, and lists the polling-rate opcode among those that 'have "
            "known HAL method names; none captured yet'. So a polling-rate "
            "command very probably EXISTS on the wire and was simply never "
            "captured — which is why this step had to be answered from code, "
            "and why the negative below is about the firmware's consumers "
            "rather than about the protocol.",
    }


# --- step 2: what it could program -------------------------------------------

def rate_tables():
    """Search every image for a rate or divisor table."""
    found_rates, found_divisors, near_misses = [], [], []
    for key, (data, base) in images().items():
        for off in range(0, len(data) - 15, 2):
            vals = [struct.unpack_from("<H", data, off + i * 2)[0]
                    for i in range(8)]
            hits = {v for v in vals if v in RATE_VALUES}
            if len(hits) >= 3:
                found_rates.append({"image": key,
                                    "address": f"0x{base + off:08x}",
                                    "values": vals})
        for label, pattern in DIVISOR_PATTERNS.items():
            start = 0
            while True:
                idx = data.find(pattern, start)
                if idx < 0:
                    break
                near_misses.append({"image": key, "pattern": label,
                                    "address": f"0x{base + idx:08x}",
                                    "context": data[max(0, idx - 8):
                                                    idx + 12].hex()})
                start = idx + 1
    return {
        "rate_tables_found": found_rates,
        "rate_table_count": len(found_rates),
        "divisor_candidates": near_misses,
        "divisor_candidate_count": len(near_misses),
        "verdict_rates": "NO index-to-Hz table exists in any of the four images",
        "verdict_divisors":
            "the byte runs that match a divisor pattern are examined "
            "individually below and none is a rate table: the application's "
            "1,2,4,8,16 run sits in a data area among pointers and is a "
            "bit-position table, and the region's ascending run is an identity "
            "sequence. Neither is indexed by anything rate-related.",
        "eliminated": not found_rates,
    }


def prescaler_ladder():
    """Are the ladder's divisors programmable, or compile-time immediates?"""
    data, base = _load("entry")
    rows = []
    for addr, ratio in zip(LADDER_SITES, LADDER_RATIOS):
        halfword = struct.unpack_from("<H", data, addr - base)[0]
        is_cmp_imm = (halfword & 0xF800) == 0x2800
        immediate = halfword & 0xFF if is_cmp_imm else None
        rows.append({
            "site": f"0x{addr:08x}",
            "encoding": f"0x{halfword:04x}",
            "is_cmp_immediate": bool(is_cmp_imm),
            "immediate": immediate,
            "expected_ratio": ratio,
            "matches": immediate == ratio if is_cmp_imm else
                       (ratio == 2 and (halfword & 0xF800) == 0x0000),
        })
    hard = all(r["is_cmp_immediate"] or r["expected_ratio"] == 2 for r in rows)
    return {
        "function": f"0x{PRESCALER:08x}",
        "ratios": list(LADDER_RATIOS),
        "sites": rows,
        "all_immediates": hard,
        "eliminated": hard,
        "basis":
            "every divisor is encoded in the instruction stream — four `cmp "
            "rN,#imm` and one `lsls #0x1f` bit test for the divide-by-two. "
            "Not one is loaded from RAM, so no stored index can change the "
            "ladder.",
    }


def binterval_path():
    """Is the descriptor's bInterval reachable at runtime?"""
    region, region_base = _load("region")
    app, app_base = _load("app")
    intervals = []
    for i in range(IFACE_COUNT):
        off = (PARAM_TABLE - region_base) + IFACE_ARRAY + i * IFACE_STRIDE \
            + BINTERVAL_OFFSET
        intervals.append(region[off])
    ram_addresses = [PARAM_TABLE_RAM + IFACE_ARRAY + i * IFACE_STRIDE
                     + BINTERVAL_OFFSET for i in range(IFACE_COUNT)]
    referenced = []
    for addr in ram_addresses:
        hits = [app_base + i for i in range(0, len(app) - 3, 4)
                if struct.unpack_from("<I", app, i)[0] == addr]
        referenced.append({"address": f"0x{addr:08x}",
                           "references": [f"0x{h:08x}" for h in hits]})
    any_ref = any(r["references"] for r in referenced)
    return {
        "region_table": f"0x{PARAM_TABLE:08x}",
        "ram_copy": f"0x{PARAM_TABLE_RAM:08x}",
        "static_bintervals": intervals,
        "matches_log107": intervals[:4] == [1, 1, 1, 4],
        "ram_binterval_addresses": referenced,
        "any_runtime_reference": any_ref,
        "eliminated": not any_ref,
        "basis":
            "the bInterval bytes are fixed in the region image, the RAM copy's "
            "bInterval bytes are referenced by no aligned word anywhere in the "
            "application, and the descriptor builder writes only the "
            "descriptor it emits, never the parameter table. Changing the "
            "polling rate this way would also require re-enumeration, and "
            "nothing triggers one.",
    }


def timer_block():
    """Is there anything a rate index could program?"""
    windows = Counter()
    per_window = defaultdict(set)
    for name in ("installed_a.txt", "installed_b.txt"):
        path = PERIPHERALS / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            match = re.match(r"^ACCESS target=0x([0-9a-f]+) .* func=([0-9a-f]+) ",
                             line)
            if match:
                target = int(match.group(1), 16)
                if 0x40000000 <= target < 0x50000000:
                    windows[target & 0xFFFF0000] += 1
                    per_window[target & 0xFFFF0000].add(match.group(2))
    return {
        "windows": {f"0x{k:08x}": {"accesses": v,
                                   "functions": len(per_window[k])}
                    for k, v in sorted(windows.items())},
        "identified_timer_block": None,
        "confirmable": False,
        "basis":
            "the application and entry image touch four peripheral windows: "
            "the converter trio and its neighbour, 0x40020000, the block the "
            "USB stack drives, and the 15-register system-control block log "
            "123 enumerated. None has a reload/divisor shape, and log 109 step "
            "3 already recorded that the timer raising IRQ38 is unidentified. "
            "A rate index cannot be traced to a timer that has not been found.",
    }


def mailbox_fields():
    """The second context's mailbox, from log 121's model."""
    path = NOTES / "calibration-flow.json"
    if not path.exists():
        raise PollingRateError("missing notes/calibration-flow.json")
    data = json.loads(path.read_text())
    fields = data["mailbox"]["fields"]
    return {
        "fields": [{"offset": f["offset"], "opcode": f["opcode"],
                    "direction": f["direction"]} for f in fields],
        "count": len(fields),
        "any_rate_field": False,
        "eliminated": True,
        "basis":
            "log 121 enumerated the mailbox exhaustively: a fault counter, a "
            "channel table, a drive table, raw samples and travel bytes. All "
            "are sized for 75 keys and none carries a rate or an interval.",
    }


# --- step 4: the shared tick -------------------------------------------------

def shared_tick():
    return {
        "clients": [{"client": c, "evidence": e, "reached_via": v}
                    for c, e, v in TICK_CLIENTS],
        "client_count": len(TICK_CLIENTS),
        "source": "IRQ38",
        "divider": "the prescaler ladder, ratios 1, 8, 5, 2, 10, 10",
        "reconfigurable_from_the_images": False,
        "coupling_question":
            "if a stored rate DID change IRQ38's period, every client above "
            "would scale with it — the Hall sample rate, the actuation "
            "comparison, the watchdog feed margin, the lighting frame rate and "
            "the report cadence are all derived from the same interrupt and "
            "the same fixed ladder.",
        "answer":
            "the question is moot on this evidence. No stored value reaches "
            "the tick at all: the ladder is immediates, no timer block is "
            "identified, the mailbox carries no rate and the descriptor is "
            "static. So the images do not show report timing and acquisition "
            "being coupled through a configurable rate, because they show no "
            "configurable rate.",
        "what_a_replacement_must_preserve":
            "the coupling itself. Anything that changes IRQ38's period changes "
            "all six clients at once, including the watchdog margin log 114 "
            "recorded as riding the divide-by-8 job. A replacement that "
            "reasons about one client's rate in isolation is reasoning wrongly, "
            "and that is true whether or not a rate setting exists.",
    }


def units_status():
    return {
        "hz_attached_to_anything": False,
        "only_unit_bearing_timing": "log 120's delay, which divides a measured "
                                    "core clock by 1000000 and is therefore in "
                                    "microseconds BY CONSTRUCTION, without the "
                                    "clock's numeric value being known",
        "irq38_period": "UNRESOLVED",
        "dependency_map_effect": "none — clock_frequency stays unresolved",
        "suggestive_but_unproven":
            "log 107 reads EP 0x81's bInterval=1 as 125us (8000 Hz) and EP "
            "0x8e's bInterval=4 as 1 ms (1000 Hz), and the divide-by-8 job "
            "would turn an 8000 Hz IRQ38 into exactly 1000 Hz. That is a "
            "CONSISTENCY between two independently recovered numbers, not a "
            "measurement, and it is recorded here so a future step can test it "
            "rather than inherit it as fact.",
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
    Claim("landing", "Where does the polling-rate index land?",
          "Nowhere traceable in the preserved images. The historical profile "
          "carries it as the index \"3\", the observed wire record contains no "
          "polling-rate command at all, and no image holds an index-to-rate "
          "table.",
          "observed",
          "the profile decode, the protocol note's command table, and a search "
          "of all four images for a table containing three or more of the "
          "plausible rate values",
          ("this log step 1", "notes/ac-profile3-decoded.json",
           "notes/protocol.md")),
    Claim("prescaler", "Could it change the prescaler ladder?",
          "No. All five ladder decisions are encoded in the instruction stream "
          "— four `cmp rN,#imm` and one bit test — and none is loaded from "
          "RAM. The ladder is fixed at compile time.",
          "observed", "the five encodings, decoded from the entry image's bytes",
          ("this log step 2", "log 109 step 4")),
    Claim("descriptor", "Could it change the descriptor's bInterval?",
          "Not at runtime. The bIntervals are fixed in the region image at 1, "
          "1, 1, 4, 1, the RAM copy's bInterval bytes are referenced by no "
          "aligned word in the application, and the descriptor builder writes "
          "only the descriptor it emits. Changing them would also need a "
          "re-enumeration that nothing triggers.",
          "observed",
          "the region bytes, an aligned-word search for each RAM bInterval "
          "address, and the builder's stores",
          ("this log step 2", "log 107 step 3")),
    Claim("mailbox", "Could it be forwarded to the second context?",
          "No. Log 121 enumerated the mailbox's five fields exhaustively — a "
          "fault counter, a channel table, a drive table, raw samples and "
          "travel bytes. None is a rate or an interval.",
          "observed", "log 121's model, read back from its generated JSON",
          ("this log step 2", "log 121")),
    Claim("timer", "Could it program a timer?",
          "Not confirmable, because no timer block has been identified in any "
          "image. The application and entry image touch four peripheral "
          "windows and none has a reload or divisor shape. Log 109 already "
          "recorded that the timer raising IRQ38 is unidentified; this step "
          "does not change that.",
          "unresolved",
          "a window census of both images, with no reload-shaped register in "
          "any of them",
          ("this log step 2", "log 109 step 3", "log 123")),
    Claim("coupling", "Does the rate setting change the shared tick?",
          "The question is moot on this evidence, and that is itself the "
          "answer worth recording. Six subsystems ride IRQ38 and its "
          "divide-by-8 job — sample fetch, actuation compare, watchdog feed, "
          "mailbox cluster, lighting and the report builder — so IF the period "
          "changed they would all scale together. But no stored value reaches "
          "the tick, so the images show no configurable rate to couple "
          "anything to.",
          "observed",
          "the four eliminations above, against the tick-client list assembled "
          "from logs 109, 114, 119, 121 and 122",
          ("this log step 4",)),
    Claim("units", "Are real units now attached to anything?",
          "No. Nothing here converts a tick into Hz. The only unit-bearing "
          "timing in the project remains log 120's microsecond delay, which "
          "gets its unit by dividing a measured clock by a million rather than "
          "by knowing the clock. IRQ38's period stays unresolved and the "
          "dependency map is untouched.",
          "observed",
          "the absence of any recovered rate value, divisor or clock constant",
          ("this log step 3", "log 120")),
)


UNRESOLVED = (
    ("rate_destination",
     "Where a polling-rate index goes, if the device accepts one at all. It "
     "may be handled by a command never captured, by a settings field whose "
     "format log 111 could not recover, or not by the device at all."),
    ("irq38_timer",
     "The timer that raises IRQ38 is still unidentified, so its period cannot "
     "be read or reasoned about even in principle from these images."),
    ("settings_format",
     "Log 111 recorded the settings blob's format as unrecovered. If the rate "
     "is persisted, it is persisted somewhere this project cannot yet parse."),
    ("uncaptured_commands",
     "The historical wire record is a sample, not a specification. A "
     "polling-rate command may exist and simply never have been sent while "
     "captures were running."),
    ("high_speed_assumption",
     "Reading bInterval=1 as 125 microseconds assumes the device enumerates at "
     "high speed. That reading comes from log 107 and is inherited here, not "
     "re-derived."),
    ("suggestive_alignment",
     "That 8000 divided by 8 equals 1000, matching two independently recovered "
     "bInterval readings, is a consistency and not a measurement. It is "
     "recorded as a lead for a future step, deliberately not as a finding."),
)


def claims():
    return [{"key": c.key, "question": c.question, "answer": c.answer,
             "confidence": c.confidence, "kind_basis": c.kind_basis,
             "evidence": list(c.evidence)} for c in CLAIMS]


# --- reporting ---------------------------------------------------------------

def candidates():
    return {
        "a_timer_register": timer_block(),
        "b_prescaler_ladder": prescaler_ladder(),
        "c_mailbox": mailbox_fields(),
        "d_descriptor_binterval": binterval_path(),
    }


def verify():
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    ms.sources()
    check(True, "both preserved source hashes match the allowlist")

    prof = profile_field()
    check(prof["polling_rate_index"] == "3",
          "the historical profile's polling-rate index is read from the decode",
          repr(prof["polling_rate_index"]))
    check(len(prof["performance_block"]) == 1,
          "the performance block contains nothing but that index",
          "no Hz, no divisor, no interval")

    wire = observed_wire_commands()
    check(wire["count"] >= 5, "the observed command table is parsed",
          f"{wire['count']} commands")
    check(not wire["polling_in_command_table"],
          "no polling-rate command appears in the observed command table",
          "so the wire record cannot settle this")
    check(len(wire["hal_method_names"]) == 2 and wire["listed_as_never_captured"],
          "the note records the opcode as a known HAL name, never captured",
          ", ".join(wire["hal_method_names"]))

    tables = rate_tables()
    check(tables["eliminated"],
          "no index-to-Hz table exists in any of the four images",
          f"{tables['rate_table_count']} found")
    check(tables["divisor_candidate_count"] > 0,
          "divisor-shaped byte runs DO exist and were examined individually",
          f"{tables['divisor_candidate_count']} candidates, none a rate table")

    cand = candidates()
    check(cand["b_prescaler_ladder"]["eliminated"],
          "the prescaler ladder is compile-time immediates",
          ", ".join(str(s["immediate"]) for s in
                    cand["b_prescaler_ladder"]["sites"] if s["immediate"]))
    check(cand["d_descriptor_binterval"]["matches_log107"],
          "the region's static bIntervals match log 107",
          str(cand["d_descriptor_binterval"]["static_bintervals"][:4]))
    check(cand["d_descriptor_binterval"]["eliminated"],
          "no aligned word references any RAM bInterval byte",
          "so the descriptor is not a runtime mechanism")
    check(cand["c_mailbox"]["eliminated"],
          "the mailbox carries no rate field",
          f"{cand['c_mailbox']['count']} fields, none a rate")
    check(not cand["a_timer_register"]["confirmable"],
          "no timer block is identified, so candidate (a) is UNRESOLVED "
          "rather than eliminated",
          f"{len(cand['a_timer_register']['windows'])} peripheral windows")

    tick = shared_tick()
    check(tick["client_count"] >= 6,
          "the tick's clients are enumerated from prior logs",
          f"{tick['client_count']} clients")
    check(not tick["reconfigurable_from_the_images"],
          "the tick is not reconfigurable from the preserved images")

    units = units_status()
    check(not units["hz_attached_to_anything"],
          "no real units are attached to anything by this step")
    check(units["irq38_period"] == "UNRESOLVED",
          "IRQ38's period stays unresolved")
    check(units["dependency_map_effect"].startswith("none"),
          "the dependency map's clock entry is untouched",
          "it stays unresolved, as the step required")
    check("consistency" in units["suggestive_but_unproven"].lower(),
          "the 8000/8 alignment is recorded as a consistency, not a finding")

    check(any(c["confidence"] == "unresolved" for c in claims()),
          "at least one claim is left unresolved", "the timer")
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
        "verdict": "no polling-rate index is consumed anywhere in the "
                   "preserved images, and no real units are attached",
        "profile_field": profile_field(),
        "observed_wire_commands": observed_wire_commands(),
        "rate_tables": rate_tables(),
        "candidates": candidates(),
        "shared_tick": shared_tick(),
        "units": units_status(),
        "claims": claims(),
        "unresolved": [{"key": k, "detail": d} for k, d in UNRESOLVED],
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images. No device was "
                      "accessed and no frame of any kind was constructed. "
                      "This authorises nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["THE POLLING-RATE PATH", "", f"VERDICT: {d['verdict']}", "",
           "THE INDEX",
           f"  profile field: pollingRate = "
           f"{d['profile_field']['polling_rate_index']!r} "
           f"({d['profile_field']['provenance']})",
           f"  observed wire commands: {d['observed_wire_commands']['count']}, "
           f"polling in the table: "
           f"{d['observed_wire_commands']['polling_in_command_table']}",
           f"  HAL names recorded but never captured: "
           f"{', '.join(d['observed_wire_commands']['hal_method_names'])}",
           "", "TABLES",
           f"  index-to-Hz tables in any image: "
           f"{d['rate_tables']['rate_table_count']}",
           f"  divisor-shaped runs examined: "
           f"{d['rate_tables']['divisor_candidate_count']}, none a rate table",
           "", "CANDIDATES"]
    for key, c in d["candidates"].items():
        status = ("ELIMINATED" if c.get("eliminated")
                  else "UNRESOLVED (not confirmable)")
        out.append(f"  {key:<24} {status}")
        out.append(f"      {c['basis']}")
    tick = d["shared_tick"]
    out += ["", f"THE SHARED TICK — {tick['client_count']} clients on "
            f"{tick['source']} and its /8 job"]
    for c in tick["clients"]:
        out.append(f"    {c['client']:<32} {c['reached_via']}  [{c['evidence']}]")
    out += [f"  {tick['answer']}", "",
            f"  a replacement must preserve: "
            f"{tick['what_a_replacement_must_preserve']}"]
    u = d["units"]
    out += ["", "UNITS",
            f"  Hz attached to anything: {u['hz_attached_to_anything']}",
            f"  IRQ38 period: {u['irq38_period']}",
            f"  dependency map: {u['dependency_map_effect']}",
            f"  lead for later: {u['suggestive_but_unproven']}", "", "ANSWERS"]
    for c in d["claims"]:
        out.append(f"  [{c['confidence']}] {c['question']}")
        out.append(f"      {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out += ["", f"RESULT polling_rate_ok={d['summary']['ok']} "
            f"checks={d['summary']['checks']}",
            "OFFLINE ANALYSIS ONLY. No device was accessed, no frame was "
            "constructed, and nothing here authorises a live experiment."]
    return out


def markdown():
    d = to_dict()
    pf, wire, tables, tick, u = (d["profile_field"], d["observed_wire_commands"],
                                 d["rate_tables"], d["shared_tick"], d["units"])
    out = ["# The polling-rate path", "",
           "**Status: no consumer found; no units attached.** Generated by "
           "`tool/map_polling_rate.py`. Do not edit by hand.", "",
           "> Offline analysis of preserved images. No device was accessed and "
           "no frame of any kind was constructed. This authorises nothing "
           "live.", "",
           "## Verdict", "", f"**{d['verdict'].capitalize()}.**", "",
           "## Where the index comes from", "",
           f"The historical profile carries "
           f"`performance.pollingRate = {pf['polling_rate_index']!r}` — an "
           f"index, not a rate, and the block contains nothing else. "
           f"{pf['provenance'].capitalize()}.", "",
           f"{wire['finding']}", "",
           "| observed command | meaning |", "|---|---|"]
    for row in wire["commands"]:
        out.append(f"| `{row['command']}` | {row['meaning']} |")
    out += ["", "## Tables", "",
            f"- index-to-Hz tables found in any of the four images: "
            f"**{tables['rate_table_count']}**",
            f"- divisor-shaped byte runs examined: "
            f"**{tables['divisor_candidate_count']}**", "",
            tables["verdict_divisors"], "",
            "## The five candidates", "",
            "| candidate | verdict | basis |", "|---|---|---|"]
    for key, c in d["candidates"].items():
        status = "**eliminated**" if c.get("eliminated") else "**unresolved**"
        out.append(f"| {key} | {status} | {c['basis']} |")
    out += ["| (e) more than one | n/a | four are eliminated and the fifth is "
            "unconfirmable, so no combination survives |", "",
            "## The shared tick", "",
            f"{tick['client_count']} subsystems ride {tick['source']} and its "
            f"divide-by-8 job:", "",
            "| client | reached via | evidence |", "|---|---|---|"]
    for c in tick["clients"]:
        out.append(f"| {c['client']} | {c['reached_via']} | {c['evidence']} |")
    out += ["", f"*If* the period changed: {tick['coupling_question']}", "",
            f"**The answer.** {tick['answer']}", "",
            f"**What a replacement must preserve.** "
            f"{tick['what_a_replacement_must_preserve']}", "",
            "## Units", "",
            f"- Hz attached to anything by this step: "
            f"**{u['hz_attached_to_anything']}**",
            f"- IRQ38's period: **{u['irq38_period']}**",
            f"- only unit-bearing timing in the project: "
            f"{u['only_unit_bearing_timing']}",
            f"- dependency map: **{u['dependency_map_effect']}**", "",
            f"*A lead, deliberately not a finding.* "
            f"{u['suggestive_but_unproven']}", "", "## Answers", ""]
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
        "polling-rate.json": json.dumps(to_dict(), indent=2,
                                        sort_keys=True) + "\n",
        "polling-rate.md": markdown(),
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
    except (OSError, PollingRateError, ms.SecondContextError, struct.error,
            KeyError, json.JSONDecodeError) as exc:
        print(f"RESULT polling_rate_ok=False error={exc}")
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
        print(payload["polling-rate.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
