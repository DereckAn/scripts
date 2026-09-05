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
# Log 114: the cluster the census could not attribute.
WATCHDOG_SELECTOR = 0x21FE          # returns a block base from a selector
WATCHDOG_FEED = 0x516               # the prescaler's /8 job
WATCHDOG_FEED_VALUE = 0x5AFA00FF    # (0x5afa0002 - 2) | 0xff, to base+8
WATCHDOG_ACK_VALUE = 0x5AFA0003     # 0x5afa0002 + 1, to base+0
WATCHDOG_ESCALATION_LIMIT = 1       # region+0xa85 byte 0, power-on value
WATCHDOG_COUNTER_PAIR = 0x1801EE05  # byte 0 = limit, byte 1 = counter
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
            "both magic-key blocks are written a cleared control word on the "
            "reset path",
            "strongly-inferred",
            "FUN_00001216 writes 0x5afa55aa to +0xc then 0x5afa0000 to +0 of "
            "both 0x40008000 and 0x40009000; the literals are at entry 0x1494, "
            "0x1498, 0x149c and 0x14a0 and were read from raw bytes. The "
            "control value's low half is ZERO, which is what a disable looks "
            "like — but no register map confirms the bit meanings, so this is "
            "inference from the write pattern, not identification. NOTE (log "
            "114): this is the reset-path behaviour only; it does NOT mean the "
            "blocks stay disabled, because two later paths write them",
            "bytes"),
    Finding("watchdog_census_blind_spot", "watchdogs",
            "the MMIO census sees ONE writer, and the census is wrong — a "
            "second cluster reaches the same blocks through a call-through "
            "base selector it cannot attribute",
            "observed",
            "log 114's correction. FUN_000021fe returns 0x40008000 for "
            "selector 0 and 0x40009000 for selector 1 from its own pool at "
            "0x2220/0x2224, so every caller's access has an unresolved base "
            "and is invisible to a per-function census. Five functions call "
            "it: 0x2148, 0x216c, 0x21b0, 0x21c8 and 0x21e2. The earlier claim "
            "that exactly one function touches these blocks is WITHDRAWN",
            "listing"),
    Finding("watchdog_periodic_feed", "watchdogs",
            "block 0x40008000 IS fed periodically, on the tick chain",
            "observed",
            "FUN_00000516 — the prescaler's divide-by-8 job from log 109 — "
            "calls FUN_00002148(0, 0xff) at 0x51c, resolved by constant "
            "propagation. That writes (0x5afa0002 - 2) | 0xff = 0x5afa00ff to "
            "base+8 and re-arms the key 0x5afa55aa at base+0xc. The claim "
            "\"nothing feeds them anywhere\" is WITHDRAWN: this is a periodic "
            "reload every eight ticks of IRQ38",
            "listing"),
    Finding("watchdog_nmi_acknowledge", "watchdogs",
            "the NMI handler conditionally acknowledges and re-arms block "
            "0x40008000, then escalates to a system reset",
            "strongly-inferred",
            "Vector_NMI's listing: FUN_000021b0(0) returns bit 2 of "
            "*(0x40008000) via `ubfx r0,r0,#0x2,#0x1`; when set it calls "
            "FUN_000021c8(0) (writes 0x5afa0003 to base+0) and "
            "FUN_000021e2(0) (re-arms the key at base+0xc), then increments a "
            "counter. It is an ACKNOWLEDGE-AND-RE-ARM rather than a feed — it "
            "is gated on a status bit and counted — and it is not itself the "
            "reset; the reset is a separate AIRCR write. The register bit "
            "meanings are still unmapped, so the role is inferred from "
            "control flow, not identified",
            "listing"),
    Finding("watchdog_escalation_limit", "watchdogs",
            "the escalation limit is ONE: the first acknowledged NMI also "
            "triggers SYSRESETREQ",
            "strongly-inferred",
            "Vector_NMI compares the incremented counter at *(0x1801ee05)+1 "
            "against the limit at +0 with `bcc`, and writes 0x05fa0004 to "
            "*(0x212c) = 0xe000ed0c (AIRCR) when the branch is not taken. The "
            "region's initialised bytes at that address are `01 00`, so the "
            "power-on limit is 1 and the counter 0. Nothing observed changes "
            "the limit at runtime, but nothing rules it out either",
            "bytes"),
    Finding("watchdog_second_block_untouched", "watchdogs",
            "selector 1, and therefore block 0x40009000, is never passed by "
            "any live path",
            "observed",
            "constant propagation resolves the selector at every call site: "
            "FUN_00002148 is called with 0, and all three NMI accessors with "
            "0. FUN_0000216c, the only function that could pass something "
            "else, has zero callers. So 0x40009000 is touched exactly once, "
            "by the reset-path disable",
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
            "CORRECTED BY LOG 114, and the correction STRENGTHENS this "
            "classification. There are THREE access paths, not one: the reset "
            "path writes a cleared control word to both blocks; the "
            "prescaler's divide-by-8 job feeds 0x40008000 every eight ticks; "
            "and the NMI handler acknowledges and re-arms it, escalating to "
            "SYSRESETREQ after one strike. A replacement therefore cannot "
            "ignore these blocks in either direction — omitting the periodic "
            "feed risks a reset if the block is live, and inheriting the NMI "
            "vector without the acknowledge means the first NMI resets the "
            "device. Both the feed and the NMI policy are deliberate choices "
            "a replacement must make.",
            ("log 114 step 1: FUN_000021fe is a call-through base selector, "
             "so the census cannot attribute the NMI cluster's accesses",
             "log 114 step 2: FUN_00000516 -> FUN_00002148(0, 0xff) feeds "
             "0x40008000 every eight ticks",
             "log 114 step 3: Vector_NMI acknowledges, counts, and writes "
             "AIRCR 0x05fa0004 once the limit of 1 is reached"),
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
                "watchdog policy": "known, and it is NOT just a disable: "
                                   "reset clears both, the /8 tick feeds "
                                   "0x40008000, and NMI acknowledges it and "
                                   "resets after one strike (log 114)",
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
            "access_paths": [
                {"kind": "reset-path disable", "function": RESET_INIT,
                 "blocks": list(WATCHDOG_BLOCKS), "trigger": "once, at reset",
                 "writes": [f"key 0x{WATCHDOG_UNLOCK_KEY:08x} -> +0xc",
                            f"0x{WATCHDOG_CONTROL_VALUE:08x} -> +0"],
                 "census_visible": True},
                {"kind": "periodic feed", "function": WATCHDOG_FEED,
                 "blocks": [WATCHDOG_BLOCKS[0]],
                 "trigger": "every 8 ticks, from the prescaler's /8 job "
                            "FUN_00000516",
                 "writes": [f"0x{WATCHDOG_FEED_VALUE:08x} -> +8",
                            f"key 0x{WATCHDOG_UNLOCK_KEY:08x} -> +0xc"],
                 "census_visible": False},
                {"kind": "NMI acknowledge and escalate",
                 "function": NMI_HANDLER,
                 "blocks": [WATCHDOG_BLOCKS[0]],
                 "trigger": "on NMI, only when bit 2 of +0 reads set",
                 "writes": [f"0x{WATCHDOG_ACK_VALUE:08x} -> +0",
                            f"key 0x{WATCHDOG_UNLOCK_KEY:08x} -> +0xc",
                            "counter++, then AIRCR 0x05fa0004 once the limit "
                            "is reached"],
                 "census_visible": False},
            ],
            "base_selector": WATCHDOG_SELECTOR,
            "blocks": list(WATCHDOG_BLOCKS),
            "control_value": WATCHDOG_CONTROL_VALUE,
            "escalation_limit_default": WATCHDOG_ESCALATION_LIMIT,
            "fed_anywhere": True,
            "key_offset": WATCHDOG_KEY_OFFSET,
            "second_block_touched_after_reset": False,
            "unlock_key": WATCHDOG_UNLOCK_KEY,
            "withdrawn_claims": [
                "exactly one function in either image touches these blocks",
                "nothing feeds them anywhere",
            ],
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
    # Log 114's correction, pinned. The model must name every access path,
    # because the whole error was believing a single-writer census.
    watchdog = payload["watchdog"]
    check("the model names all THREE watchdog access paths",
          len(watchdog["access_paths"]) == 3
          and {item["kind"] for item in watchdog["access_paths"]}
          == {"reset-path disable", "periodic feed",
              "NMI acknowledge and escalate"},
          ", ".join(item["kind"] for item in watchdog["access_paths"]))
    check("the model records that two of the three are census-invisible",
          sum(1 for item in watchdog["access_paths"]
              if not item["census_visible"]) == 2,
          "the base arrives from a call-through selector, so a per-function "
          "census cannot attribute them")
    check("the withdrawn claims are recorded, not silently dropped",
          len(watchdog["withdrawn_claims"]) == 2
          and any("nothing feeds them" in claim
                  for claim in watchdog["withdrawn_claims"]))
    check("the model states the blocks ARE fed",
          watchdog["fed_anywhere"] is True)
    check("the model records that only the first block is touched after reset",
          watchdog["second_block_touched_after_reset"] is False)
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
