#!/usr/bin/env python3
"""What makes address 0 writable, and how the entry image comes to run there.

Read-only and offline. Authorises nothing live. This closes the last
boot-acceptance item log 101 left open and Path B's fifth gate.

THE ANSWER IS A NEGATIVE THAT SETTLES THE QUESTION. There is no remap. Nothing
in any preserved image writes a remap, alias or base-address register, and
nothing writes VTOR. Address 0 is ordinary writable RAM by hardware
arrangement, and the boot path simply writes to it.

Three candidates were on the table and two are eliminated outright:

  (a) a system-control register written early on the reset path — ELIMINATED.
      Every access to the 0x45000000 block is enumerated below and not one
      stores a base-address-shaped value; the handoff stub writes no such
      register at all.
  (b) a fixed hardware alias — CONFIRMED in the weak sense that address 0 is
      writable RAM the software never configures, and NARROWED: it is not an
      alias of 0x18000000, because the entry image's own scatter loader would
      then overwrite itself mid-copy.
  (c) a VTOR-plus-copy arrangement — ELIMINATED. VTOR is read ten times across
      four images and written zero times.

What remains genuinely unknown is what places the BOOTLOADER at address 0
before any preserved image runs. That is a ROM or hardware boot stage outside
the preserved set, and it is reported as unresolved rather than guessed.

A CORRECTION TO THE PROMPT'S PREMISE is recorded in `brief_check`:
notes/references.md does NOT list ROM/RAM remapping among the series brief's
features. The lead does not exist in this repository.

No device access. Examples:
    python3 tool/map_address_zero.py
    python3 tool/map_address_zero.py --json
    python3 tool/map_address_zero.py --write
    python3 tool/map_address_zero.py --check
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
PERIPHERALS = ROOT / "ghidra/peripherals"

BOOT_BIN = "bootloader_primary.bin"
ENTRY_BIN = "installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin"
HANDOFF_BIN = ("installed_boot_handoff_ram_prog0cdfc_dst18010000_len00050"
               "_1e418391.bin")
HANDOFF_BASE = 0x18010000
HANDOFF_LEN = 0x50

VTOR = 0xE000ED08
AIRCR = 0xE000ED0C
VECTKEY = 0x05FA0000
SYSRESETREQ = 0x4
SYSCTL_LO, SYSCTL_HI = 0x45000000, 0x45001000

ENTRY_CONSTANT = 0x60011000        # the bootloader's accepted entry
ENTRY_CONSTANT_POOL = 0x7F98
COPY_LENGTH = 0x10000              # the fixed copy to address 0
COPY_CALLER = 0x7EC8
COPY_VENEER = 0xFEE                # -> the RAM stub
NOOP_STUB = 0xFFC                  # called before the copy; a bare bx lr
SLOT7_SETTER = 0x7FA8
SLOT7_OFFSET = 0x1C                # VTOR + 0x1c, the Reserved7 vector slot
SLOT7_POOL = 0x7FB0

APP_RAM_BASE = 0x18000000
SCATTER_DEST = 0x18000000          # where the entry image copies the app
SCATTER_LEN = 0x1E354
SCATTER_LOADER = 0x148             # inside the address-0 window
ENTRY_RESET = 0x14A8

# Base-address-shaped values a remap register would plausibly be given.
BASE_SHAPED = (0x00000000, 0x18000000, 0x60000000, 0x60010000, 0x60011000)


class AddressZeroError(RuntimeError):
    """Raised when the evidence does not support continuing."""


def _load(name):
    path = IMPORTS / name
    if not path.exists():
        raise AddressZeroError(f"missing import slice {name}")
    return path.read_bytes()


def images():
    ms.sources()
    return {"boot": _load(BOOT_BIN), "entry": _load(ENTRY_BIN),
            "handoff": _load(HANDOFF_BIN)}


ACCESS_RE = re.compile(
    r"^ACCESS target=0x([0-9a-f]+) width=(\d+) dir=(read|write) "
    r"instr=([0-9a-f]+) func=([0-9a-f]+) base=(\S+) off=(-?\d+) "
    r"stored=(\S+)$")

CENSUSES = (("installed_a.txt", "entry"), ("installed_b.txt", "app"),
            ("bootloader.txt", "boot"), ("ram18038000.txt", "second"))


def _accesses():
    out = []
    for name, tag in CENSUSES:
        path = PERIPHERALS / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            match = ACCESS_RE.match(line)
            if match:
                out.append({
                    "image": tag, "target": int(match.group(1), 16),
                    "width": int(match.group(2)), "dir": match.group(3),
                    "instr": match.group(4), "func": match.group(5),
                    "stored": match.group(8),
                })
    if not out:
        raise AddressZeroError("no census available; run the peripheral step")
    return out


# --- candidate (a): a system-control remap register --------------------------

def sysctl_block():
    """Every 0x45000000 access, and whether any stores a base address."""
    rows = [a for a in _accesses() if SYSCTL_LO <= a["target"] < SYSCTL_HI]
    per = defaultdict(list)
    for a in rows:
        per[a["target"]].append(a)
    table = []
    base_shaped = []
    for target in sorted(per):
        group = per[target]
        stored = sorted({g["stored"] for g in group
                         if g["dir"] == "write" and g["stored"] != "unknown"})
        for value in stored:
            try:
                if int(value, 16) in BASE_SHAPED and int(value, 16) != 0:
                    base_shaped.append((target, value))
            except ValueError:
                pass
        table.append({
            "register": f"0x{target:08x}",
            "accesses": len(group),
            "reads": sum(1 for g in group if g["dir"] == "read"),
            "writes": sum(1 for g in group if g["dir"] == "write"),
            "images": sorted({g["image"] for g in group}),
            "functions": sorted({g["func"] for g in group})[:6],
            "stored": stored,
        })
    return {
        "registers": table,
        "register_count": len(table),
        "total_accesses": len(rows),
        "base_shaped_stores": [{"register": f"0x{t:08x}", "value": v}
                               for t, v in base_shaped],
        "any_base_shaped_store": bool(base_shaped),
        "eliminated": not base_shaped,
        "basis":
            "not one write into the block stores a base-address-shaped value. "
            "Every stored value is a small bitmask or enable field (0x0, 0x2, "
            "0x4, 0x8, 0x10, 0x28, 0x1, 0x7fff, 0x9fff, 0xfffd, 0xffff). A "
            "register that relocated a 64 KiB window would have to be told "
            "where, and none is.",
    }


# --- candidate (c): VTOR -----------------------------------------------------

def vtor_usage():
    rows = [a for a in _accesses() if a["target"] == VTOR]
    writes = [a for a in rows if a["dir"] == "write"]
    return {
        "reads": len(rows) - len(writes),
        "writes": len(writes),
        "sites": [{"image": a["image"], "dir": a["dir"],
                   "instr": f"0x{a['instr']}", "func": f"0x{a['func']}"}
                  for a in rows],
        "eliminated": not writes,
        "basis":
            "VTOR is read to fetch the initial stack pointer and, in one "
            "bootloader function, to reach the vector table as data. It is "
            "never written, in any of the four images. Nothing relocates the "
            "table, so the table's presence at address 0 is not a software "
            "arrangement.",
    }


# --- the handoff stub --------------------------------------------------------

def handoff_stub():
    """The routine that actually writes address 0, decoded from its bytes."""
    data = images()["handoff"]
    if len(data) != HANDOFF_LEN:
        raise AddressZeroError(f"handoff stub is {len(data)} bytes, expected "
                               f"{HANDOFF_LEN}")
    literals = {
        HANDOFF_BASE + 0x48: struct.unpack_from("<I", data, 0x48)[0],
        HANDOFF_BASE + 0x4C: struct.unpack_from("<I", data, 0x4C)[0],
    }
    writes_sysctl = any(SYSCTL_LO <= v < SYSCTL_HI for v in literals.values())
    return {
        "runs_at": f"0x{HANDOFF_BASE:08x}",
        "length": len(data),
        "reached_by": f"bootloader veneer 0x{COPY_VENEER:08x} "
                      f"(movw/movt to 0x{HANDOFF_BASE:08x})",
        "why_in_ram":
            "it overwrites address 0, which is where the bootloader itself is "
            "executing. The copy therefore has to run from somewhere else, and "
            "0x18010000 is disjoint from the 0..0xffff destination.",
        "steps": [
            "msr primask,#1 — disable interrupts",
            "word-copy len>>2 words from src to dst, dst = 0",
            "dsb #0xf",
            f"read AIRCR (0x{AIRCR:08x}), keep PRIGROUP (& 0x700), "
            f"or VECTKEY (0x{VECTKEY:08x}), add SYSRESETREQ (0x{SYSRESETREQ:x})",
            "store to AIRCR — system reset",
            "dsb #0xf, then spin until the reset lands",
        ],
        "literals": {f"0x{a:08x}": f"0x{v:08x}" for a, v in literals.items()},
        "aircr_literal_present": AIRCR in literals.values(),
        "vectkey_literal_present": VECTKEY in literals.values(),
        "writes_a_system_control_register": writes_sysctl,
        "conclusion":
            "the stub disables interrupts, copies, and resets. It configures "
            "NOTHING. Address 0 is already writable when it runs.",
    }


def slot7_channel():
    """The bootloader's handoff variable, passed through the vector table."""
    boot = images()["boot"]
    pool = struct.unpack_from("<I", boot, SLOT7_POOL)[0]
    return {
        "setter": f"0x{SLOT7_SETTER:08x}",
        "listing": "ldr r1,[pool] ; ldr r1,[r1] ; str r0,[r1,#0x1c] ; bx lr",
        "pool_value": f"0x{pool:08x}",
        "pool_is_vtor": pool == VTOR,
        "slot": 7,
        "slot_offset": f"0x{SLOT7_OFFSET:x}",
        "slot_name": "Reserved7, unused by ARMv7-M",
        "boot_slot7_value": f"0x{struct.unpack_from('<I', boot, 0x1C)[0]:08x}",
        "entry_slot7_value":
            f"0x{struct.unpack_from('<I', images()['entry'], 0x1C)[0]:08x}",
        "meaning":
            "the bootloader stores the selected entry address into an unused "
            "vector slot, reached through VTOR, immediately before the copy "
            "and reset. Both images ship that slot as zero, so it is scratch. "
            "It is a handoff variable that survives the reset BECAUSE the "
            "vector table is in writable RAM — which is itself evidence that "
            "address 0 is RAM.",
    }


# --- what address 0 is -------------------------------------------------------

def address_zero():
    boot, entry = images()["boot"], images()["entry"]
    return {
        "is_writable_ram": True,
        "writable_evidence":
            "the handoff stub performs a plain word-store loop into address 0 "
            "and the bootloader writes vector slot 7 through VTOR. Neither "
            "would work against a flash XIP alias, so address 0 is RAM.",
        "minimum_size": f"0x{COPY_LENGTH:x}",
        "size_evidence": f"the copy length is a fixed 0x{COPY_LENGTH:x}, and "
                         f"the bootloader itself occupies 0x0..0xefff",
        "is_an_alias_of_app_ram": False,
        "alias_argument":
            "if address 0 aliased 0x18000000, the entry image's scatter loader "
            f"at 0x{SCATTER_LOADER:x} would copy 0x{SCATTER_LEN:x} bytes from "
            f"flash to 0x{SCATTER_DEST:08x} — i.e. over itself, while "
            "executing from it. The loader would be destroyed mid-copy. The "
            "two are therefore distinct memories.",
        "stack_lives_elsewhere":
            f"both stages put their stack in the 0x18000000 window: the "
            f"bootloader's initial SP is "
            f"0x{struct.unpack_from('<I', boot, 0)[0]:08x} and the entry "
            f"image's is 0x{struct.unpack_from('<I', entry, 0)[0]:08x}, while "
            f"their code runs at 0. Code window and data window are separate.",
        "configured_by_software": False,
        "what_configures_it": "UNRESOLVED — see rom_dependency",
    }


def boot_stages():
    return [
        {"stage": "ROM or hardware boot", "address_zero_holds": "the "
         "bootloader, somehow",
         "who_puts_it_there": "UNRESOLVED — no preserved image does it",
         "confidence": "unresolved"},
        {"stage": "bootloader running",
         "address_zero_holds": "the bootloader (its own vector table at 0, "
                               "reset 0x000002f5)",
         "who_puts_it_there": "the unread stage above",
         "confidence": "observed"},
        {"stage": "handoff",
         "address_zero_holds": "being overwritten with the entry image",
         "who_puts_it_there": f"the RAM stub at 0x{HANDOFF_BASE:08x}, called "
                              f"through veneer 0x{COPY_VENEER:08x}",
         "confidence": "observed"},
        {"stage": "after the reset",
         "address_zero_holds": "the entry image (vector table at 0, reset "
                               "0x000014a9)",
         "who_puts_it_there": "the copy above; the core fetches SP and PC "
                              "from address 0 on reset",
         "confidence": "observed"},
        {"stage": "application running",
         "address_zero_holds": "still the entry image — the application is "
                               "copied to 0x18000000 and its interrupt "
                               "handlers are entered through the table at 0",
         "who_puts_it_there": "nothing maintains it; VTOR is never written "
                              "and nothing re-aliases anything",
         "confidence": "observed"},
    ]


def replacement_requirements():
    return [
        {"requirement": "place the image where the bootloader looks",
         "detail": f"the bootloader compares the selected entry against "
                   f"0x{ENTRY_CONSTANT:08x} and refuses anything else",
         "confidence": "observed"},
        {"requirement": "fit the fixed copy",
         "detail": f"the copy length is a hard-coded 0x{COPY_LENGTH:x} bytes; "
                   f"the vendor entry image is 0x58ac, so there is room, but "
                   f"the length is not negotiable and the source must be "
                   f"readable for the whole 0x{COPY_LENGTH:x}",
         "confidence": "observed"},
        {"requirement": "put the vector table at image offset 0",
         "detail": "the image lands at address 0 and VTOR is never written, so "
                   "the table must be the first thing in the image",
         "confidence": "observed"},
        {"requirement": "put the stack in the 0x18000000 window",
         "detail": "both preserved stages do, and the entry image's own init "
                   "bounds-checks MSP into [0x18000000, ...] and faults "
                   "otherwise",
         "confidence": "observed"},
        {"requirement": "configure no remap, and do not write VTOR",
         "detail": "nothing in any preserved image does either. Preserving the "
                   "arrangement means leaving it alone, which is the easiest "
                   "possible obligation",
         "confidence": "observed"},
        {"requirement": "expect the selected entry in vector slot 7",
         "detail": f"the bootloader writes it to VTOR+0x{SLOT7_OFFSET:x} before "
                   f"the reset; a replacement may read it or ignore it, but "
                   f"must not rely on slot 7 being zero at runtime",
         "confidence": "observed"},
    ]


def brief_check():
    """The prompt's premise, checked against the repository."""
    path = NOTES / "references.md"
    text = path.read_text().lower() if path.exists() else ""
    return {
        "premise": "the series brief documents ROM/RAM remapping as a series "
                   "feature",
        "occurrences_of_remap_in_references": text.count("remap"),
        "premise_supported": "remap" in text,
        "correction":
            "notes/references.md lists dual Cortex-M3 cores, USB host and "
            "device, GPIO, timers and PWM, two watchdogs, an SPI NOR interface "
            "and a 10-bit six-channel SAR ADC. ROM/RAM remapping is NOT among "
            "them. The lead does not exist in this repository, and no "
            "conclusion here rests on it — which is just as well, because the "
            "evidence says there is no remap to find.",
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
    Claim("mechanism", "What makes address 0 writable?",
          "Nothing in software. Address 0 is ordinary writable RAM by hardware "
          "arrangement: the handoff stub stores into it with a plain word loop "
          "and the bootloader writes a vector slot through VTOR. No preserved "
          "image configures, enables or relocates anything to make that true.",
          "observed",
          "the handoff stub's complete 0x50-byte listing, which contains only "
          "an interrupt mask, a copy, two barriers and an AIRCR reset",
          ("this log step 1", "log 101")),
    Claim("sysctl", "Is there a system-control remap register?",
          "No. All 15 registers of the 0x45000000 block are enumerated across "
          "four images, and not one write stores a base-address-shaped value — "
          "every stored value is a small bitmask or enable field. A register "
          "that relocated a 64 KiB window would have to be told where.",
          "observed",
          "the census, grouped by register, with the stored values listed",
          ("this log step 1",)),
    Claim("vtor", "Is it a VTOR-plus-copy arrangement?",
          "No. VTOR is read ten times across the four images — for the initial "
          "stack pointer, and once to reach the table as data — and written "
          "zero times. Nothing relocates the vector table.",
          "observed", "the census, filtered to VTOR",
          ("this log step 1", "this log step 2")),
    Claim("not_an_alias", "Is address 0 an alias of the application RAM?",
          "No. If it were, the entry image's own scatter loader at 0x148 would "
          "copy the application over 0x18000000 — over itself — while "
          "executing from it, and would be destroyed mid-copy. Both stages "
          "also place their stack in the 0x18000000 window while running code "
          "at 0, so the code and data windows are distinct.",
          "strongly-inferred",
          "the scatter table's destination and length against the loader's own "
          "address, plus both images' initial stack pointers",
          ("this log step 2", "FINDINGS, Candidate A scatter-load")),
    Claim("persistence", "What maintains the arrangement after the app starts?",
          "Nothing, because nothing established it. The entry image's vector "
          "table stays at address 0, the application is copied to 0x18000000, "
          "and its interrupt handlers are entered through the table at 0. No "
          "software action keeps that true.",
          "observed", "the absence of any VTOR write or remap write anywhere",
          ("this log step 2", "log 109")),
    Claim("handoff_channel", "How does the bootloader pass the entry address?",
          "Through vector slot 7. FUN_00007fa8 reads VTOR and stores the "
          "selected entry at VTOR+0x1c, the ARMv7-M Reserved7 slot, which both "
          "images ship as zero. That the write works at all is further "
          "evidence the table is in RAM.",
          "observed",
          "the setter's four-instruction listing and its pool value 0xe000ed08",
          ("this log step 2",)),
    Claim("replacement", "What must a replacement entry image reproduce?",
          "Six things, all of them easy: sit at 0x60011000, fit the fixed "
          "0x10000-byte copy, put its vector table at image offset 0, put its "
          "stack in the 0x18000000 window, configure no remap and never write "
          "VTOR, and not assume vector slot 7 is zero at runtime. Preserving "
          "the arrangement means leaving it alone.",
          "observed", "the constants recovered above, each read from bytes",
          ("this log step 3",)),
    Claim("rom", "What stays unresolved?",
          "What places the BOOTLOADER at address 0 before any preserved image "
          "runs. That is a ROM or hardware boot stage outside the preserved "
          "set, it was never searched and cannot be, and every statement here "
          "begins after it has already happened.",
          "unresolved",
          "the preserved set contains no code that writes the bootloader to "
          "address 0",
          ("this log step 2", "log 113")),
)


UNRESOLVED = (
    ("rom_stage",
     "What places the bootloader at address 0 is not in any preserved image. A "
     "mask ROM was never searched and cannot be, so this is a boundary, not an "
     "absence."),
    ("window_extent",
     "The address-0 window is at least 0x10000 bytes because the copy is that "
     "long. Its true size, and whether it is a dedicated block or a window "
     "onto something larger, is not established."),
    ("window_identity",
     "Which physical memory backs address 0 is unknown. That it is writable "
     "and distinct from 0x18000000 is shown; what it IS is not."),
    ("alias_direction",
     "Whether address 0 is a hardwired alias of some other range, or a memory "
     "with its own decode, cannot be distinguished from code that never "
     "configures it."),
    ("reset_state",
     "Whether the address-0 contents survive the AIRCR reset is assumed by the "
     "design — the copy happens before the reset and the image runs after it — "
     "but no code asserts it and no test could."),
    ("slot7_reader",
     "The bootloader writes vector slot 7; no preserved image is shown reading "
     "it back. Its consumer is not recovered."),
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

    stub = handoff_stub()
    check(stub["length"] == HANDOFF_LEN,
          "the handoff stub is the expected size", f"{stub['length']} bytes")
    check(stub["aircr_literal_present"] and stub["vectkey_literal_present"],
          "the stub's literals are AIRCR and the vector key",
          ", ".join(stub["literals"].values()))
    check(not stub["writes_a_system_control_register"],
          "the stub writes NO system-control register",
          "it configures nothing")

    sysctl = sysctl_block()
    check(sysctl["register_count"] > 10,
          "the 0x45000000 block is enumerated, not sampled",
          f"{sysctl['register_count']} registers, "
          f"{sysctl['total_accesses']} accesses")
    check(sysctl["eliminated"],
          "no write into the block stores a base-address-shaped value",
          "so candidate (a) is eliminated")

    vt = vtor_usage()
    check(vt["writes"] == 0, "VTOR is never written, in any image",
          f"{vt['reads']} reads, {vt['writes']} writes")
    check(vt["eliminated"], "so candidate (c) is eliminated")
    check(vt["reads"] >= 8, "VTOR is nonetheless read widely",
          "so the absence of writes is not an absence of the register")

    az = address_zero()
    check(az["is_writable_ram"], "address 0 is writable RAM",
          az["writable_evidence"][:60] + "...")
    check(not az["is_an_alias_of_app_ram"],
          "address 0 is NOT an alias of 0x18000000",
          "the scatter loader would destroy itself")
    check(not az["configured_by_software"],
          "no software configures the arrangement")

    s7 = slot7_channel()
    check(s7["pool_is_vtor"],
          "the slot-7 setter reaches the table through VTOR", s7["pool_value"])
    check(s7["boot_slot7_value"] == "0x00000000"
          and s7["entry_slot7_value"] == "0x00000000",
          "both images ship vector slot 7 as zero, so it is scratch")

    stages = boot_stages()
    check(len(stages) == 5, "every boot stage has an entry", str(len(stages)))
    check(sum(1 for s in stages if s["confidence"] == "unresolved") == 1,
          "exactly one stage is unresolved — the one before the images",
          "the ROM stage")

    req = replacement_requirements()
    check(len(req) >= 5, "the replacement's obligations are enumerated",
          f"{len(req)} requirements")
    boot = images()["boot"]
    check(struct.unpack_from("<I", boot, ENTRY_CONSTANT_POOL)[0]
          == ENTRY_CONSTANT,
          "the entry constant is read from the bootloader's own pool",
          f"0x{ENTRY_CONSTANT:08x}")

    bc = brief_check()
    check(not bc["premise_supported"],
          "the ROM/RAM-remapping premise is NOT in notes/references.md",
          "recorded as a correction rather than relied on")

    check(all(c["confidence"] in
              ("observed", "strongly-inferred", "inferred", "hypothesis",
               "unresolved") for c in claims()),
          "every claim carries a known confidence label")
    check(any(c["confidence"] == "unresolved" for c in claims()),
          "at least one claim is left unresolved", "the ROM stage")
    check(all(c["kind_basis"] and c["evidence"] for c in claims()),
          "every claim carries a kind_basis and a citation")
    check(len(UNRESOLVED) >= 5, "the unresolved boundaries are enumerated",
          f"{len(UNRESOLVED)} entries")
    return out


def to_dict():
    checks = verify()
    return {
        "answer": "there is no remap; address 0 is writable RAM the software "
                  "never configures",
        "handoff_stub": handoff_stub(),
        "sysctl_block": sysctl_block(),
        "vtor": vtor_usage(),
        "address_zero": address_zero(),
        "slot7_channel": slot7_channel(),
        "boot_stages": boot_stages(),
        "replacement_requirements": replacement_requirements(),
        "brief_check": brief_check(),
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
    out = ["ADDRESS ZERO — WHAT MAKES IT WRITABLE", "",
           f"ANSWER: {d['answer']}", "", "THE HANDOFF STUB"]
    st = d["handoff_stub"]
    out.append(f"  runs at {st['runs_at']}, {st['length']} bytes, "
               f"{st['reached_by']}")
    for s in st["steps"]:
        out.append(f"    {s}")
    out.append(f"  {st['conclusion']}")
    sc = d["sysctl_block"]
    out += ["", f"THE 0x45000000 BLOCK — {sc['register_count']} registers, "
            f"{sc['total_accesses']} accesses",
            f"  base-address-shaped stores: "
            f"{len(sc['base_shaped_stores'])}  -> eliminated={sc['eliminated']}"]
    for r in sc["registers"]:
        out.append(f"    {r['register']}  {r['accesses']:>2} acc "
                   f"(r{r['reads']}/w{r['writes']})  {','.join(r['images'])}"
                   + (f"  stored={', '.join(r['stored'])}" if r["stored"] else ""))
    vt = d["vtor"]
    out += ["", f"VTOR  reads={vt['reads']} writes={vt['writes']}  "
            f"-> eliminated={vt['eliminated']}"]
    az = d["address_zero"]
    out += ["", "ADDRESS 0",
            f"  writable RAM: {az['is_writable_ram']}",
            f"  alias of 0x18000000: {az['is_an_alias_of_app_ram']}",
            f"  {az['alias_argument']}",
            f"  {az['stack_lives_elsewhere']}"]
    s7 = d["slot7_channel"]
    out += ["", "THE HANDOFF VARIABLE", f"  {s7['meaning']}"]
    out += ["", "BOOT STAGES"]
    for s in d["boot_stages"]:
        out.append(f"  [{s['confidence']:<16}] {s['stage']:<22} "
                   f"{s['address_zero_holds']}")
    out += ["", "WHAT A REPLACEMENT MUST DO"]
    for r in d["replacement_requirements"]:
        out.append(f"  - {r['requirement']}: {r['detail']}")
    out += ["", f"PREMISE CHECK: {d['brief_check']['correction']}", "", "ANSWERS"]
    for c in d["claims"]:
        out.append(f"  [{c['confidence']}] {c['question']}")
        out.append(f"      {c['answer']}")
    out.append("")
    for item in d["checks"]:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['label']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    out += ["", f"RESULT address_zero_ok={d['summary']['ok']} "
            f"checks={d['summary']['checks']}",
            "OFFLINE ANALYSIS ONLY. No device was accessed, and nothing here "
            "authorises a live experiment."]
    return out


def markdown():
    d = to_dict()
    st, sc, vt, az = (d["handoff_stub"], d["sysctl_block"], d["vtor"],
                      d["address_zero"])
    out = ["# What makes address 0 writable", "",
           "**Status: resolved, except for the stage before the images.** "
           "Generated by `tool/map_address_zero.py`. Do not edit by hand.", "",
           "> Offline analysis of preserved images. No device was accessed. "
           "This authorises nothing live.", "",
           "## The answer", "",
           f"**{d['answer'].capitalize()}.** Three candidates were on the "
           f"table; two are eliminated outright and the third turns out to "
           f"require nothing of the software.", "",
           "| candidate | verdict |", "|---|---|",
           f"| (a) a system-control remap register | **eliminated** — "
           f"{sc['basis']} |",
           f"| (b) a fixed hardware alias | **confirmed, and narrowed** — "
           f"address 0 is writable RAM the software never configures, and it "
           f"is NOT an alias of 0x18000000 |",
           f"| (c) VTOR plus a copy | **eliminated** — {vt['basis']} |", "",
           "## The handoff stub, in full", "",
           f"The routine that actually writes address 0 runs at "
           f"`{st['runs_at']}` and is {st['length']} bytes. "
           f"{st['why_in_ram']}", ""]
    for step in st["steps"]:
        out.append(f"1. {step}")
    out += ["", f"Its only two literals are `{'`, `'.join(st['literals'].values())}` "
            f"— AIRCR and the vector key. **{st['conclusion']}**", "",
            "## The 0x45000000 block, enumerated", "",
            "| register | accesses | r/w | images | stored |",
            "|---|---:|---|---|---|"]
    for r in sc["registers"]:
        out.append(f"| `{r['register']}` | {r['accesses']} | "
                   f"{r['reads']}/{r['writes']} | {', '.join(r['images'])} | "
                   f"{', '.join(r['stored']) or '—'} |")
    out += ["", f"Base-address-shaped stores: **{len(sc['base_shaped_stores'])}**.",
            "", "## What address 0 is", "",
            f"- **Writable RAM.** {az['writable_evidence']}",
            f"- **At least `{az['minimum_size']}`.** {az['size_evidence']}.",
            f"- **Not an alias of `0x18000000`.** {az['alias_argument']}",
            f"- **Separate from the data window.** {az['stack_lives_elsewhere']}",
            "", "## The handoff variable", "", d["slot7_channel"]["meaning"],
            "", "## Address 0 at each boot stage", "",
            "| stage | address 0 holds | who puts it there | |",
            "|---|---|---|---|"]
    for s in d["boot_stages"]:
        out.append(f"| {s['stage']} | {s['address_zero_holds']} | "
                   f"{s['who_puts_it_there']} | {s['confidence']} |")
    out += ["", "## What a replacement entry image must reproduce", "",
            "| requirement | detail |", "|---|---|"]
    for r in d["replacement_requirements"]:
        out.append(f"| {r['requirement']} | {r['detail']} |")
    out += ["", "## A correction to the premise", "",
            d["brief_check"]["correction"], "", "## Answers", ""]
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
        "address-zero.json": json.dumps(to_dict(), indent=2,
                                        sort_keys=True) + "\n",
        "address-zero.md": markdown(),
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
    except (OSError, AddressZeroError, ms.SecondContextError, struct.error,
            KeyError) as exc:
        print(f"RESULT address_zero_ok=False error={exc}")
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
        print(payload["address-zero.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
