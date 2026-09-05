#!/usr/bin/env python3
"""Phase 5G plus the Phase 5 final dependency gate.

Read-only. Two jobs in one model:

  1. PHASE 5G — clocks, watchdogs, faults and multicore, revisited now that
     5B-5F have identified the downstream consumers.
  2. THE FINAL GATE — every SERVICE classified as must-implement,
     must-neutralize, may-omit or unresolved, with the evidence cited.

THE GATE IS DELIBERATELY HOSTILE TO ITSELF. The plan says "five unanalysed
service areas plus an MMIO census do not satisfy this gate", so every
`unresolved` service here carries an `evidence_boundary` naming the exact
thing that is missing, and a check refuses to let one be recorded without it.
`may-omit` is likewise gated: it requires a proven safe idle state, and a
service whose idle state is unproven is `unresolved`, not omittable.

WHAT 5G FOUND, in one paragraph each:

  WATCHDOGS. Two identical magic-key blocks at 0x40008000 and 0x40009000 are
  touched by exactly ONE function in either image — FUN_00001216, on the reset
  path. It writes the key 0x5afa55aa to +0xc and then 0x5afa0000 to +0, i.e.
  it clears the control word behind an unlock. Nothing anywhere re-enables or
  feeds them. The `usbd_wdt` task's name is a lead that does NOT pan out: its
  call-graph closure reaches only 0xe000ed04 and touches no watchdog block.

  CLOCKS. FUN_00001216 is the reset-path sequence. It reads 0x45000000 and
  0x4500000c to decide which block to unlock, sanity-checks MSP against
  0x18000000..0x18040000, and then runs a fixed five-call chain. No frequency
  is claimed anywhere: no constant in the recovered code carries a unit.

  MULTICORE. CandidateB_Main hands the flash address 0x60074000 to an
  entry-image routine through a veneer, then SPINS until 0x20000000 holds
  0x12345678. That token appears in exactly two places in the whole
  repository: the app's expected-value literal, and inside the 0x18038000 RAM
  image at +0x3214. The start routine manipulates 0x45000100. This is a second
  execution context with a mailbox handshake.

No device access. Examples:
    python3 tool/map_platform_dependencies.py
    python3 tool/map_platform_dependencies.py --json
    python3 tool/map_platform_dependencies.py --write
    python3 tool/map_platform_dependencies.py --check
"""
import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"

CONFIDENCES = ("observed", "strongly-inferred", "hypothesis", "unresolved")
SOURCES = ("listing", "decompiler", "bytes", "xref", "spec")
CLASSES = ("must-implement", "must-neutralize", "may-omit", "unresolved")

# The 5B-5F models this gate reads rather than restates.
UPSTREAM_MODELS = ("usb-routing.json", "scan-pipeline.json",
                   "hall-actuation.json", "nonvolatile-writes.json",
                   "rgb-lamparray.json")

RELOCATION_DELTA = 0x2C

# --- 5G constants, all read off listings or raw bytes ------------------------
WATCHDOG_BLOCKS = (0x40008000, 0x40009000)
WATCHDOG_UNLOCK_KEY = 0x5AFA55AA
WATCHDOG_CONTROL_VALUE = 0x5AFA0000
WATCHDOG_KEY_OFFSET = 0xC
RESET_INIT = 0x1216                 # entry image
STACK_LOW, STACK_HIGH = 0x18000000, 0x18040000
SECOND_IMAGE_SOURCE = 0x60074000
SECOND_IMAGE_DEST = 0x18038000
SECOND_IMAGE_RESET_VECTOR = 0x180381C1
HANDSHAKE_MAILBOX = 0x20000000
HANDSHAKE_TOKEN = 0x12345678
HANDSHAKE_TOKEN_IN_IMAGE = 0x3214   # offset inside the 0x18038000 image
START_ROUTINE = 0x1F50              # entry image
START_REGISTER = 0x45000100
NMI_HANDLER = 0x20BE                # entry image
VECTOR_TABLE_SLOTS = 80


@dataclass(frozen=True)
class Finding:
    key: str
    area: str          # clocks | watchdogs | faults | multicore
    statement: str
    confidence: str
    kind_basis: str
    verified_against: str


FINDINGS = (
    Finding("watchdog_disabled", "watchdogs",
            "both magic-key blocks are DISABLED on the reset path, not fed",
            "strongly-inferred",
            "FUN_00001216 writes 0x5afa55aa to +0xc then 0x5afa0000 to +0 of "
            "both 0x40008000 and 0x40009000; the literals are at entry 0x1494, "
            "0x1498, 0x149c and 0x14a0 and were read from raw bytes. The "
            "control value's low half is ZERO, which is what a disable looks "
            "like — but no register map confirms the bit meanings, so this is "
            "inference from the write pattern, not identification",
            "bytes"),
    Finding("watchdog_sole_user", "watchdogs",
            "exactly one function in either image touches those blocks",
            "observed",
            "a per-function MMIO census over both peripheral maps returns "
            "FUN_00001216 in the entry image and NOTHING in the application; "
            "so nothing re-enables or feeds them after reset",
            "xref"),
    Finding("usbd_wdt_is_not_a_watchdog_feeder", "watchdogs",
            "the usbd_wdt task does NOT service any hardware watchdog",
            "observed",
            "its body FUN_18015c84 is 37 instructions and its whole 12-function "
            "call-graph closure reaches only 0xe000ed04 (ICSR). The task name "
            "was a lead and it does not pan out: it is a USB-device software "
            "supervisor, not a watchdog feeder",
            "xref"),
    Finding("reset_sequence", "clocks",
            "the reset-path init reads 0x45000000 and 0x4500000c to choose a "
            "branch, validates the stack pointer, then runs a fixed five-call "
            "chain",
            "observed",
            "FUN_00001216, called by Vector_Reset, listing at 0x1216..0x1278: "
            "`ldr r3,[r4,#0x0]` / `cbnz` / `ldr r3,[r4,#0xc]` / `cbz`, then "
            "`mrs r0,msp` compared against 0x18000000 and 0x18040000, then "
            "bl to 0xd3e, 0xde8, 0xe68, 0xec4, 0xef6 and a tail branch to 0xf0a",
            "listing"),
    Finding("stack_window", "clocks",
            f"the reset path requires the stack pointer to lie in "
            f"0x{STACK_LOW:08x}..0x{STACK_HIGH:08x}, and faults out otherwise",
            "observed",
            "`mrs r0,msp` / `cmp.w r0,#0x18000000` / `bcc` then a compare "
            "against the literal at 0x14a4 = 0x18040000, with `movs r0,#0x7` "
            "and a call to FUN_00000dbc on failure",
            "listing"),
    Finding("no_frequency_claimed", "clocks",
            "no clock frequency is established anywhere",
            "unresolved",
            "no constant in the recovered reset chain carries a unit, and no "
            "timing relationship ties a divider to a rate. Phase 5C recovered "
            "the tick's RATIOS (1, 8, 5, 2, 10, 10) and explicitly not its "
            "period; nothing since has changed that",
            "listing"),
    Finding("boot_remap", "clocks",
            "the reset path writes 0x4002f000 = 3 and 0x4002f004 = 0x60021000",
            "observed",
            "FUN_00000ec4's census entries record both stores; log 100 "
            "identified 0x60021000 as record slot 1's address, so the pair "
            "looks like a boot-source remap. The block is NOT named",
            "xref"),
    Finding("nmi_resets", "faults",
            "the NMI handler requests a system reset",
            "observed",
            "log 100 recorded Vector_NMI at entry 0x20be writing AIRCR with "
            "0x05fa0004, which is VECTKEY | SYSRESETREQ. That is a hardware "
            "action, not a diagnostic",
            "listing"),
    Finding("fault_handlers_diagnostic", "faults",
            "the HardFault handler reads CFSR, MMFAR and BFAR — diagnostics, "
            "not a hardware requirement",
            "strongly-inferred",
            "log 100's peripheral census attributes those three ARM core "
            "registers to the HardFault vector and nothing else; reading a "
            "status register cannot itself be required for correct operation",
            "xref"),
    Finding("vector_extent", "faults",
            f"the vector table is {VECTOR_TABLE_SLOTS} slots and IRQ63 is live",
            "strongly-inferred",
            "log 102 established the extent by the first code address rather "
            "than a terminator, because ARMv7-M tables have none. THIS IS "
            "DELIBERATELY LEFT AS INFERENCE: no exact-device evidence proves "
            "the implemented interrupt count, and none has appeared since",
            "bytes"),
    Finding("second_context_exists", "multicore",
            "a second execution context is started and waited for at boot",
            "observed",
            "CandidateB_Main at 0x1800023a: `ldr r0,[0x180003f0]` loads "
            "0x60074000, `str r5,[r4,#0x0]` clears 0x20000000, a veneer call, "
            "then `ldr r0,[0x180003f4]` / `ldr r1,[r4,#0x0]` / `cmp` / `bne` "
            "spins until the mailbox holds 0x12345678",
            "listing"),
    Finding("handshake_token_location", "multicore",
            "the handshake token exists in exactly two places, one of them "
            "inside the 0x18038000 image",
            "observed",
            "an exhaustive aligned-word search of the entry slice, the "
            "application slice, the reconstructed region, the bootloader "
            "mirror and the 0x18038000 RAM image finds 0x12345678 only at "
            "app+0x3f4 (the expected value) and ram18038000+0x3214",
            "bytes"),
    Finding("start_mechanism", "multicore",
            "the start routine is entry-image 0x1f50, reached by a veneer, and "
            "it manipulates 0x45000100",
            "strongly-inferred",
            "the veneer at 0x1801bd96 encodes `movw r12,#0x1f51`; entry+0x1f50 "
            "is `70 b5` (push {r4,r5,r6,lr}), validates as a subroutine and "
            "decodes cleanly, and its first register work is a read-modify-"
            "write of [r4,#0x100] clearing bit 15. Ghidra had not disassembled "
            "it because it is unreached, so this rests on raw bytes plus the "
            "validator rather than on an analysed function",
            "bytes"),
    Finding("second_image_vector", "multicore",
            "the 0x18038000 image carries its own vector table with reset "
            f"0x{SECOND_IMAGE_RESET_VECTOR:08x}",
            "observed",
            "log 104 recorded it; re-verified here — the word at "
            "ram18038000+0x4 is 0x180381c1",
            "bytes"),
    Finding("second_context_ownership", "multicore",
            "what the second context OWNS is not established",
            "unresolved",
            "the start is recovered and the handshake is recovered, but no "
            "evidence assigns USB, the Hall acquisition or storage to it. It "
            "is a strong candidate for the Phase 5D acquisition boundary "
            "precisely because that producer was never found in either "
            "analysed image — but a candidate is not a finding",
            "xref"),
    Finding("no_rom_service_identified", "multicore",
            "no ROM call was identified",
            "unresolved",
            "every cross-image call recovered so far resolves into one of the "
            "preserved images. A mask ROM was not searched and cannot be, so "
            "its absence is unproven either way",
            "xref"),
)


@dataclass
class Service:
    key: str
    name: str
    classification: str
    rationale: str
    evidence: tuple
    confidence: str
    evidence_boundary: str = ""
    safe_idle_proven: bool = False


SERVICES = (
    Service("reset_clock_ram", "reset, clock and RAM bring-up",
            "must-implement",
            "the reset path validates the stack window and runs a fixed "
            "five-call init chain before anything else can run. A replacement "
            "must reproduce an equivalent, though it need not reproduce this "
            "one instruction for instruction.",
            ("log 113 step 1: FUN_00001216's listing",
             "log 113: the stack window 0x18000000..0x18040000"),
            "observed"),
    Service("watchdogs", "the two magic-key watchdog blocks",
            "must-neutralize",
            "the vendor firmware disables both on the reset path and never "
            "feeds them. A replacement that simply ignores them inherits "
            "whatever their reset default is, which is not established — so "
            "the safe policy is to perform the same disable, not to omit it.",
            ("log 113 step 2: FUN_00001216 writes the key then a zero control "
             "word to both blocks",
             "log 113 step 2: no other function in either image touches them"),
            "strongly-inferred"),
    Service("tick", "the periodic tick that drives everything",
            "must-implement",
            "IRQ38 is the sole writer of the service-task event word, and the "
            "entire scan-to-HID chain hangs off it. Without a tick there is no "
            "key state and no report.",
            ("log 109 step 3: Vector_IRQ38 is the only writer of 0x1801ee84",
             "log 109 step 4: the prescaler ladder"),
            "observed"),
    Service("hall_acquisition", "per-key Hall sample acquisition",
            "unresolved",
            "THE LARGEST BLOCKER. Phase 5D recovered the comparison that turns "
            "a travel byte into a key bit, but not the producer of those "
            "bytes. Without it a prototype has no input at all, so this is a "
            "blocker and not an omission.",
            ("log 110 step 4: the travel buffer's address appears in no "
             "aligned word of any image",
             "log 110 step 3: every 0x40000000 access is 32-bit; no converter "
             "shape exists in either census"),
            "unresolved",
            evidence_boundary="no function in either analysed image writes the "
            "per-key travel array from a hardware register, and the buffer is "
            "reachable only by dereferencing a pointer cell that something "
            "fills at runtime. The producer is outside the analysed set. The "
            "second execution context at 0x18038000 is a CANDIDATE owner and "
            "is not evidence."),
    Service("key_state", "key-state generation from travel bytes",
            "must-implement",
            "the comparison, the hold band and the bitmap update are recovered "
            "as executable arithmetic and are reproducible.",
            ("log 110 step 1: cmp r3,#0x64 and the surrounding control flow",
             "tool/model_hall_actuation.py implements and tests it"),
            "observed"),
    Service("usb_enumeration", "USB enumeration and the descriptor set",
            "must-implement",
            "the descriptor parameter table and the builder's own size "
            "arithmetic reproduce the host-observed wTotalLength exactly, so a "
            "replacement can enumerate compatibly.",
            ("log 107 step 4: the builder's arithmetic reproduces 0x008d",
             "log 107 step 5: 24 field checks against the host capture"),
            "observed"),
    Service("usb_boot_keyboard", "interface 0, the 8-byte boot report",
            "must-implement",
            "the chosen USB compatibility target. Its route from the report "
            "builder to the endpoint is fully traced.",
            ("log 109 step 1: interface 0, 8 bytes, buffer 0x1801e7c8",
             "log 107 step 8: EP 0x81 is one of the two required endpoints"),
            "observed"),
    Service("usb_control", "the control endpoint",
            "must-implement",
            "enumeration and every Feature report depend on it.",
            ("log 107 step 8: EP 0x00 is required",
             "log 112 step 2: the class handler's request codes"),
            "observed"),
    Service("second_context", "the second execution context at 0x18038000",
            "must-neutralize",
            "main SPINS forever until the mailbox token appears, so a "
            "replacement that neither starts the second context nor removes "
            "the wait will hang at boot. It must either reproduce the start or "
            "remove the handshake — it cannot ignore it.",
            ("log 113 step 4: the spin at 0x1800024c..0x18000250",
             "log 113 step 4: the token exists inside the 0x18038000 image"),
            "observed"),
    Service("vendor_channel", "the vendor 0xFF00 configuration channel",
            "may-omit",
            "the receive mailbox, the dispatcher and the transmit path are all "
            "traced, and omitting them removes only vendor-software support. "
            "The safe idle state is proven: the mailbox is a single RAM slot "
            "gated on its own byte 0, so a firmware that never fills it "
            "cannot dispatch anything.",
            ("log 107 step 7: the RX mailbox and its ownership rule",
             "log 111 step 7: the four-step never-do argument"),
            "observed", safe_idle_proven=True),
    Service("persistence", "nonvolatile settings and the commit path",
            "may-omit",
            "omission is provably safe: every route into an erase runs through "
            "one command byte and a one-deep request struct, and the target "
            "ranges are disjoint from the application region. A prototype that "
            "writes neither cannot corrupt existing configuration.",
            ("log 111 step 7: the omit-all-writes proof",
             "log 111 step 6: the ranges start at 0x320000, disjoint from "
             "0x10000..0x7c000"),
            "strongly-inferred", safe_idle_proven=True),
    Service("rgb", "RGB / LampArray lighting",
            "unresolved",
            "NOT safely omittable on current evidence. The protocol is fully "
            "recovered and the frame buffer's idle state is provable, but "
            "whether an all-zero frame means the LEDs are OFF depends on a "
            "driver polarity nobody has established. Omission could leave the "
            "array at full brightness.",
            ("log 112 step 5: both frame consumers reach zero resolved MMIO",
             "log 112 step 6: the buffer's idle state is provable, the "
             "hardware's is not"),
            "unresolved",
            evidence_boundary="the LED driver is unidentified, so its idle "
            "polarity is unknown and no shared clock, pin or controller "
            "initialisation could be inspected. Proving safe omission requires "
            "identifying the consumer of the 306-byte frame at 0x1802505e."),
    Service("media_nkro", "interface 2 and 3, media and NKRO reports",
            "may-omit",
            "both are built and sent by the same function as the boot report, "
            "from separate buffers. Omitting them means not calling those "
            "sends; nothing else depends on them, and the buffers are inert "
            "RAM.",
            ("log 109 step 1: the interface 2 and 3 send sites",
             "log 107 step 8: both are marked optional"),
            "strongly-inferred", safe_idle_proven=True),
    Service("diagnostics", "the fault logger and debug strings",
            "may-omit",
            "the fault handlers read status registers and the debug paths "
            "print strings. Neither is a hardware requirement; the NMI's reset "
            "request is classified separately.",
            ("log 113 step 3: the fault handlers read CFSR/MMFAR/BFAR only",),
            "strongly-inferred", safe_idle_proven=True),
    Service("nmi_reset", "the NMI handler's system reset",
            "must-neutralize",
            "the handler requests SYSRESETREQ. A replacement must decide "
            "deliberately whether an NMI resets the device; inheriting the "
            "vendor behaviour by accident is not acceptable, and neither is "
            "leaving the vector unpopulated.",
            ("log 113 step 3: AIRCR is written with VECTKEY|SYSRESETREQ",),
            "observed"),
    Service("rtos", "the vendor RTOS",
            "may-omit",
            "the plan says a replacement need not copy it. The scheduling the "
            "mandatory path depends on is a busy-spin event pump and a "
            "prescaler, both of which are reproducible without the RTOS; the "
            "RTOS's own tasks are the optional services.",
            ("log 109 step 2: the service task busy-spins rather than blocking",
             "log 106: the five tasks and their roles"),
            "strongly-inferred", safe_idle_proven=True),
    Service("clock_frequency", "the actual clock configuration",
            "unresolved",
            "the reset sequence is preserved as a call chain, but no frequency "
            "is established. A prototype can copy the sequence; it cannot "
            "reason about timing.",
            ("log 113 step 1: no constant in the chain carries a unit",
             "log 109: the tick's ratios are known, its period is not"),
            "unresolved",
            evidence_boundary="no crystal value, PLL multiplier or divider "
            "with a stated unit appears in the recovered code, and no register "
            "map exists for the blocks the sequence writes. Any Hz figure "
            "would have to come from the silicon or from measurement, neither "
            "of which this project has."),
)


def load_upstream():
    """The 5B-5F models, so the gate cites them instead of restating them."""
    found = {}
    for name in UPSTREAM_MODELS:
        path = NOTES / name
        if not path.exists():
            raise PlatformError(f"upstream model {name} is missing")
        found[name] = json.loads(path.read_text())
    return found


class PlatformError(ValueError):
    """The evidence does not support the structure being asked of it."""


def by_classification():
    out = {name: [] for name in CLASSES}
    for service in SERVICES:
        out[service.classification].append(service.key)
    return out


def blockers():
    """Services that block a first typing prototype."""
    return tuple(service for service in SERVICES
                 if service.classification == "unresolved")


def to_dict():
    upstream = load_upstream()
    return {
        "classes": list(CLASSES),
        "findings": [
            {"area": item.area, "confidence": item.confidence,
             "key": item.key, "kind_basis": item.kind_basis,
             "statement": item.statement,
             "verified_against": item.verified_against}
            for item in FINDINGS],
        "multicore": {
            "handshake_mailbox": HANDSHAKE_MAILBOX,
            "handshake_token": HANDSHAKE_TOKEN,
            "second_image_dest": SECOND_IMAGE_DEST,
            "second_image_reset_vector": SECOND_IMAGE_RESET_VECTOR,
            "second_image_source": SECOND_IMAGE_SOURCE,
            "start_register": START_REGISTER,
            "start_routine_entry_image": START_ROUTINE,
            "token_offset_in_second_image": HANDSHAKE_TOKEN_IN_IMAGE,
        },
        "prototype": {
            "blockers": [
                {"boundary": service.evidence_boundary, "key": service.key,
                 "name": service.name}
                for service in blockers()],
            "minimum_from_the_plan": [
                "understood reset/clock/RAM behaviour",
                "a safe watchdog policy",
                "GPIO plus Hall/sample acquisition",
                "calibrated key-state generation",
                "one USB keyboard-IN route",
            ],
            "status": {
                "reset/clock/RAM": "sequence preserved; FREQUENCY UNRESOLVED",
                "watchdog policy": "known: disable both, as the vendor does",
                "Hall acquisition": "BLOCKED — the producer is not recovered",
                "key-state generation": "recovered and executable",
                "USB keyboard-IN": "recovered end to end",
            },
        },
        "relocation": {"delta": RELOCATION_DELTA,
                       "note": "function counterparts are looked up in Phase "
                               "3's measured match table, never computed; see "
                               "log 110's correction"},
        "services": [
            {"classification": service.classification,
             "confidence": service.confidence,
             "evidence": list(service.evidence),
             "evidence_boundary": service.evidence_boundary,
             "key": service.key, "name": service.name,
             "rationale": service.rationale,
             "safe_idle_proven": service.safe_idle_proven}
            for service in SERVICES],
        "summary": by_classification(),
        "upstream_models": sorted(upstream),
        "watchdog": {
            "blocks": list(WATCHDOG_BLOCKS),
            "control_value": WATCHDOG_CONTROL_VALUE,
            "fed_anywhere": False,
            "key_offset": WATCHDOG_KEY_OFFSET,
            "sole_user": RESET_INIT,
            "unlock_key": WATCHDOG_UNLOCK_KEY,
        },
    }


def verify():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    payload = to_dict()
    check("every service has a classification from the closed set",
          all(service.classification in CLASSES for service in SERVICES),
          f"{len(SERVICES)} services")
    check("every service cites at least one piece of evidence",
          all(service.evidence for service in SERVICES))
    # The gate's own teeth: an unresolved service must name its boundary.
    check("every UNRESOLVED service names an exact evidence boundary",
          all(len(service.evidence_boundary) > 60 for service in SERVICES
              if service.classification == "unresolved"),
          ", ".join(service.key for service in blockers()))
    check("no service is classified may-omit without a proven safe idle state",
          all(service.safe_idle_proven for service in SERVICES
              if service.classification == "may-omit"),
          "omission requires proof, not silence")
    check("a service whose idle state is unproven is unresolved, not omittable",
          all(service.classification != "may-omit"
              for service in SERVICES if not service.safe_idle_proven),
          "RGB is the case this rule exists for")
    check("the Hall acquisition is recorded as a blocker, not an omission",
          next(service for service in SERVICES
               if service.key == "hall_acquisition").classification
          == "unresolved")
    check("the gate reads the five upstream models rather than restating them",
          len(payload["upstream_models"]) == len(UPSTREAM_MODELS),
          ", ".join(payload["upstream_models"]))
    check("every finding carries a confidence and a source",
          all(item.confidence in CONFIDENCES
              and item.verified_against in SOURCES for item in FINDINGS))
    check("all four areas are covered by findings",
          {item.area for item in FINDINGS}
          == {"clocks", "watchdogs", "faults", "multicore"})
    check("no clock frequency is claimed",
          next(item for item in FINDINGS
               if item.key == "no_frequency_claimed").confidence
          == "unresolved")
    check("the vector-table extent stays strongly-inferred",
          next(item for item in FINDINGS
               if item.key == "vector_extent").confidence
          == "strongly-inferred")
    check("the usbd_wdt lead is recorded as NOT panning out",
          "does not pan out" in next(
              item for item in FINDINGS
              if item.key == "usbd_wdt_is_not_a_watchdog_feeder").kind_basis)
    check("the watchdog conclusion is inference, not identification",
          next(item for item in FINDINGS
               if item.key == "watchdog_disabled").confidence
          == "strongly-inferred"
          and "not identification" in next(
              item for item in FINDINGS
              if item.key == "watchdog_disabled").kind_basis)
    check("the second context is must-neutralize, because main spins on it",
          next(service for service in SERVICES
               if service.key == "second_context").classification
          == "must-neutralize")
    check("every class is populated, so the gate is a real partition",
          all(payload["summary"][name] for name in CLASSES),
          "; ".join(f"{name}={len(payload['summary'][name])}"
                    for name in CLASSES))
    return checks


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM map_platform_dependencies",
        "PURPOSE Phase 5G plus the Phase 5 final dependency gate",
        "",
        "5G FINDINGS",
    ]
    for area in ("clocks", "watchdogs", "faults", "multicore"):
        out.append(f"  --- {area} ---")
        for item in FINDINGS:
            if item.area == area:
                out.append(f"    [{item.confidence}] ({item.verified_against}) "
                           f"{item.key}: {item.statement}")
    out += ["", "FINAL DEPENDENCY GATE"]
    for name in CLASSES:
        out.append(f"  === {name.upper()} ===")
        for service in SERVICES:
            if service.classification != name:
                continue
            out.append(f"    {service.key}: {service.name} "
                       f"[{service.confidence}]")
            out.append(f"        {service.rationale}")
            for citation in service.evidence:
                out.append(f"        cite: {citation}")
            if service.evidence_boundary:
                out.append(f"        BOUNDARY: {service.evidence_boundary}")
    out += ["", "FIRST TYPING PROTOTYPE"]
    for item, status in payload["prototype"]["status"].items():
        out.append(f"  {item:24s} {status}")
    out += ["", "BLOCKERS"]
    for item in payload["prototype"]["blockers"]:
        out.append(f"  {item['key']}: {item['name']}")
        out.append(f"      {item['boundary']}")
    out += ["", "CHECKS"]
    for item in verify():
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in verify())
    out += [
        "",
        f"RESULT gate_ok={ok} checks={len(verify())} "
        f"blockers={len(payload['prototype']['blockers'])}",
        "LIMITATION No reset-reachable write is called an initialisation "
        "requirement here solely because of graph reachability: each "
        "must-implement service names a consumer that fails without it.",
        "LIMITATION Three services are UNRESOLVED. That is a blocking state, "
        "not permission to omit them.",
    ]
    return out


def markdown():
    payload = to_dict()
    lines = [
        "# Platform dependencies and the final gate (Phase 5G)",
        "",
        "Generated by `tool/map_platform_dependencies.py`. Do not edit by hand.",
        "",
        "## 5G findings",
        "",
        "| area | finding | confidence | verified |",
        "|---|---|---|---|",
    ]
    for item in FINDINGS:
        lines.append(f"| {item.area} | {item.statement} | {item.confidence} | "
                     f"{item.verified_against} |")
    lines += ["", "## Service classification", "",
              "| service | class | confidence | safe idle proven |",
              "|---|---|---|---|"]
    for service in SERVICES:
        lines.append(f"| {service.name} | **{service.classification}** | "
                     f"{service.confidence} | "
                     f"{'yes' if service.safe_idle_proven else '—'} |")
    lines += ["", "## Blockers for a first typing prototype", ""]
    for item in payload["prototype"]["blockers"]:
        lines.append(f"- **{item['name']}** — {item['boundary']}")
    lines += ["", "## Prototype status", "",
              "| requirement | status |", "|---|---|"]
    for item, status in payload["prototype"]["status"].items():
        lines.append(f"| {item} | {status} |")
    lines += ["", "## Checks", ""]
    for item in verify():
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def bodies():
    return {"platform-dependencies.json": json.dumps(to_dict(), indent=2,
                                                     sort_keys=True) + "\n",
            "platform-dependencies.md": markdown()}


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
    except (OSError, PlatformError, json.JSONDecodeError) as exc:
        print(f"RESULT gate_ok=False error={exc}")
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
        print(payload["platform-dependencies.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
