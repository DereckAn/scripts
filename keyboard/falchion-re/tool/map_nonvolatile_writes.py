#!/usr/bin/env python3
"""Phase 5E: the nonvolatile settings write path, traced statically.

READ-ONLY AND STATIC. This module reads code. It never speaks to the device, and
it does not construct, encode or emit any command — least of all the `50 55`
persistent commit, which is traced here purely as a byte pattern the firmware
compares against.

THE ANSWER TO 5E's FIRST QUESTION is (b): the commit QUEUES work. The `0x50/0x55`
branch of the dispatcher contains no call instruction at all. It writes a command
byte and returns:

    18002428  ldr    r0,[0x180025a0]     ; the request state struct, 0x18022c60
    1800242a  adds   r0,#0x84
    1800242c  ldrb   r1,[r0,#0x0]
    1800242e  cmp    r1,#0x4
    18002430  beq    0x18002508          ; already 4 -> idempotent, skip
    18002432  strb.w r12,[r0,#0x0]       ; r12 = 4, set at 0x18001fea
    18002436  strb   r5,[r0,#0x8]        ; a sub-selector
    18002438  ldrb   r1,[r0,#0x9]
    1800243a  bic    r1,r1,#0xc          ; clear two flag bits

Everything downstream happens in another context, through TWO further queue hops:

    command byte 0x18022ce4 = 4
      -> FUN_18000d56 switches on it and on the sub-selector at +8
      -> FUN_1800e2a8 / FUN_1800e2c4 fill a request struct at 0x18025ef4 with an
         opcode byte and a 32-bit address, then set a pending flag
      -> FUN_1800dc92 drains that struct
      -> ... -> FUN_18011dd0, a DMA transfer setup that touches 0x40020000 and
         0x45000000

WHAT IS NOT PROVEN. The opcode bytes 0xd8 and 0x52 are the JEDEC SPI-NOR
block-erase opcodes for 64 KiB and 32 KiB. That is a RECOGNITION, not a proof:
what the code demonstrably does is place those bytes in a struct that a DMA path
consumes. No SPI controller register was identified, and no block is named on
that basis. The storage medium is therefore recorded as UNIDENTIFIED, with the
opcode correspondence stated as suggestive and nothing more.

No device access. Examples:
    python3 tool/map_nonvolatile_writes.py
    python3 tool/map_nonvolatile_writes.py --json
    python3 tool/map_nonvolatile_writes.py --write
    python3 tool/map_nonvolatile_writes.py --check
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
MATCH_APP = NOTES / "vendor-to-installed-functions-app-b.json"

CONFIDENCES = ("observed", "strongly-inferred", "hypothesis", "unresolved")
SOURCES = ("listing", "decompiler", "bytes", "xref")

RELOCATION_DELTA = 0x2C

# The command byte the commit sets, and the value it sets it to.
COMMAND_BYTE = 0x18022CE4
COMMIT_VALUE = 4
REQUEST_STRUCT = 0x18025EF4
# Offsets inside that struct, read off FUN_1800e2a8/FUN_1800e2c4's listings.
REQUEST_OPCODE = 0x00
REQUEST_FLAG = 0x08
REQUEST_ADDRESS = 0x0C
REQUEST_PENDING = 0x18
# Opcodes the two primitives place in it. NAMES ARE RECOGNITION, NOT PROOF.
OPCODES = {0xD8: "matches the JEDEC SPI-NOR 64 KiB block-erase opcode",
           0x52: "matches the JEDEC SPI-NOR 32 KiB block-erase opcode"}
# Target addresses the state machine passes, and the slot stride between them.
TARGET_ADDRESSES = (0x320000, 0x330000, 0x340000)
SLOT_STRIDE = 0x4000
SLOT_BASE = 0x320000
# The application region the bootloader programs (log 81), for contrast.
BOOTLOADER_REGION = (0x10000, 0x7C000)


class WriteMapError(ValueError):
    """The evidence does not support the structure being asked of it."""


@dataclass(frozen=True)
class Step:
    key: str
    name: str
    kind: str            # "function", "data" or "none"
    address: int
    detail: str
    confidence: str
    kind_basis: str
    verified_against: str


@dataclass(frozen=True)
class Hop:
    source: str
    target: str
    mechanism: str
    confidence: str
    kind_basis: str


STEPS = (
    Step("mailbox", "vendor OUT mailbox", 'data', 0x180233A8,
         "the 64-byte single-slot mailbox Phase 5B recovered. Byte 0 is both "
         "the opcode and the busy flag.",
         "observed",
         "log 107 step 7 traced FUN_18000aec filling it and the dispatcher "
         "reading byte 0 at 0x18001fc4",
         "listing"),
    Step("dispatcher", "VendorHID_CommandDispatcher", 'function', 0x18001FBE,
         "dispatches opcode 0x50 to the branch that contains subcommand 0x55.",
         "observed",
         "`cmp r2,#0x50` / `beq 0x18002110` at 0x18002018, and `ldrb r0,[r4,"
         "#0x1]` / `cmp r0,#0x55` / `beq 0x18002428` at 0x180023de",
         "listing"),
    Step("commit_request", "the 0x50/0x55 commit branch", 'code', 0x18002428,
         "sets the command byte to 4 and stores a sub-selector. IT CONTAINS "
         "NO CALL INSTRUCTION — it requests, it does not perform.",
         "observed",
         "the whole branch is nine instructions at 0x18002428..0x1800243e "
         "with no `bl` among them; contrast the 0x60 branch at 0x18002440, "
         "which does call",
         "listing"),
    Step("command_byte", "commit command byte", 'data', COMMAND_BYTE,
         f"one byte at request-state+0x84. The commit sets it to "
         f"{COMMIT_VALUE}; a guard skips when it already holds that value, so "
         "a repeated commit is idempotent.",
         "observed",
         "`strb.w r12,[r0,#0x0]` at 0x18002432 with `mov.w r12,#0x4` at "
         "0x18001fea, guarded by `cmp r1,#0x4` / `beq` at 0x1800242e",
         "listing"),
    Step("state_machine", "FUN_18000d56", 'function', 0x18000D56,
         "switches on the command byte and on the sub-selector, and calls the "
         "storage primitives with target addresses.",
         "observed",
         "`switch(*DAT_18000e7c)` where *(0x18000e7c) = 0x18022ce4, the "
         "command byte; the sub-switch is on the byte at +8 the commit stored",
         "decompiler"),
    Step("erase_64k", "FUN_1800e2a8", 'function', 0x1800E2A8,
         "fills the request struct with opcode 0xd8 and an address.",
         "observed",
         "`movs r2,#0xd8` / `strb r2,[r1,#0x0]` then `str r0,[r1,#0xc]` and "
         "`strb r0,[r1,#0x18]` at 0x1800e2b2..0x1800e2c0",
         "listing"),
    Step("erase_32k", "FUN_1800e2c4", 'function', 0x1800E2C4,
         "fills the request struct with opcode 0x52 and an address.",
         "observed",
         "`movs r2,#0x52` / `strb r2,[r1,#0x0]` at 0x1800e2ce..0x1800e2d0, "
         "otherwise identical to FUN_1800e2a8",
         "listing"),
    Step("busy_check", "FUN_1800e272", 'function', 0x1800E272,
         "the guard every primitive is called behind: returns whether the "
         "pending flag at request+0x18 equals 1.",
         "observed",
         "six instructions: `ldrb r0,[r0,#0x18]` / `cmp r0,#0x1` at "
         "0x1800e274",
         "listing"),
    Step("request_struct", "storage request struct", 'data', REQUEST_STRUCT,
         "opcode at +0, a flag at +8, a 32-bit address at +0xc, a pending "
         "flag at +0x18. The primitives refuse when byte 0 is non-zero, so "
         "one request is outstanding at a time.",
         "observed",
         "the offsets are the store displacements in FUN_1800e2a8's listing; "
         "the refusal is `cbz r2` / `movs r0,#0` / `bx lr` at 0x1800e2ac",
         "listing"),
    Step("drainer", "FUN_1800dc92", 'function', 0x1800DC92,
         "the only consumer of the request struct outside the primitives. "
         "Callerless in the application call graph, like the rest of this "
         "path.",
         "observed",
         "an exhaustive value cross-reference for 0x18025ef4 returns the nine "
         "primitives plus FUN_1800dc92 and nothing else",
         "xref"),
    Step("dma_setup", "FUN_18011dd0", 'function', 0x18011DD0,
         "a DMA transfer setup. Bounds-checks the source against 0x18000000 "
         "and a limit word, selects one of two channel bases, and polls a "
         "busy bit before starting.",
         "observed",
         "`cmp.w r0,#0x18000000` / `bcc` at 0x18011de2, `ldrd r0,r6,[r7,"
         "#0x14]` for address and length, `ldr r2,[r5,#0x8]` / `lsls r2,r2,"
         "#0x1f` for the busy bit, and `mov.w r2,#0x45000000` at 0x18011e10",
         "listing"),
    Step("medium", "the storage medium", 'none', 0,
         "UNIDENTIFIED. The path ends in a DMA engine and two unnamed "
         "register windows. No SPI controller was identified and no block is "
         "named here.",
         "unresolved",
         "no function in the whole 0x1800e2xx-0x1800efxx storage cluster "
         "touches MMIO at all; the hardware contact is only in the drainer's "
         "closure, at 0x40020008/0x40020010/0x40020014/0x40020018/"
         "0x4002001c and 0x45000000/0x4500000c/0x45000054",
         "xref"),
)

HOPS = (
    Hop("mailbox", "dispatcher", "the dispatcher reads mailbox byte 0",
        "observed", "`ldr r4,[0x18002174]` / `ldrb r0,[r4,#0x0]` at "
        "0x18001fc2 (log 107)"),
    Hop("dispatcher", "commit_request", "opcode 0x50 then subcommand 0x55",
        "observed", "two compare-and-branch pairs at 0x18002018 and "
        "0x180023e0"),
    Hop("commit_request", "command_byte", "a single byte store, no call",
        "observed", "`strb.w r12,[r0,#0x0]` at 0x18002432"),
    Hop("command_byte", "state_machine", "asynchronous: a switch in another "
        "context reads the byte",
        "strongly-inferred",
        "FUN_18000d56 switches on *(0x18022ce4); it is callerless in the "
        "application call graph, so the context that runs it is not "
        "established here"),
    Hop("state_machine", "erase_64k", "call with a target address",
        "observed", "`FUN_1800e2a8(0x320000)` in the sub-selector switch"),
    Hop("state_machine", "erase_32k", "call with a target address",
        "observed", "`FUN_1800e2c4(0x330000)` and `(0x340000)`, and a "
        "computed `slot * 0x4000 + 0x320000`"),
    Hop("erase_64k", "request_struct", "opcode and address stores",
        "observed", "`movs r2,#0xd8` then four stores at 0x1800e2b2"),
    Hop("erase_32k", "request_struct", "opcode and address stores",
        "observed", "`movs r2,#0x52` then four stores at 0x1800e2ce"),
    Hop("request_struct", "drainer", "the drainer loads the struct base",
        "observed", "`ldr` of the literal at 0x1800dcf8 = 0x18025ef4, loaded "
        "at 0x1800dc96"),
    Hop("drainer", "dma_setup", "a five-call chain",
        "observed",
        "0x1800dc92 -> 0x1800d9ce -> 0x1800d914 -> 0x1801ae04 -> 0x18011ece "
        "-> 0x18011dd0, from the inventory call graph"),
    Hop("dma_setup", "medium", "DMA to an unnamed register window",
        "unresolved",
        "the transfer reaches 0x40020000 and 0x45000000; neither is named, "
        "and no SPI controller was identified"),
)


@dataclass(frozen=True)
class Range:
    low: int
    high: int
    label: str
    confidence: str
    kind_basis: str


MODIFIABLE_RANGES = (
    Range(0x320000, 0x320000 + 0x10000, "the 64 KiB target of the 0xd8 erase",
          "observed",
          "`FUN_1800e2a8(0x320000)`; the extent assumes the opcode's nominal "
          "64 KiB, which is recognition and not proof, so the extent is the "
          "weakest part of this entry"),
    Range(0x330000, 0x330000 + 0x8000, "the 32 KiB target of one 0x52 erase",
          "observed", "`FUN_1800e2c4(0x330000)`, extent as above"),
    Range(0x340000, 0x340000 + 0x8000, "the 32 KiB target of another 0x52 "
          "erase",
          "observed", "`FUN_1800e2c4(0x340000)`, extent as above"),
    Range(SLOT_BASE, SLOT_BASE + 256 * SLOT_STRIDE,
          "a computed slot: base 0x320000 plus a byte-indexed 0x4000 stride",
          "strongly-inferred",
          "`(uint)*(byte *)(x + 0x1f) * 0x4000 + 0x320000` in the state "
          "machine; the index is a byte, so the reachable extent is bounded "
          "by 256 slots unless something narrower constrains it, which was "
          "not established"),
)


def measured_matches():
    """{installed: (vendor, confidence)} from Phase 3, for counterpart lookup.

    Phase 5D learned this the hard way: a relocation RULE is wrong, because
    functions on the same side of the insertion point relocate differently.
    Counterparts are looked up, never computed.
    """
    payload = json.loads(MATCH_APP.read_text())
    return {match["installed"]["entry"]:
            (match["vendor"]["entry"], match["confidence"])
            for match in payload.get("matches", ())
            if match.get("installed") and match.get("vendor")}


def vendor_of(address):
    """The vendor counterpart of an application address, or raise."""
    found = measured_matches().get(address)
    if found is None:
        raise WriteMapError(
            f"0x{address:08x} has no measured vendor counterpart; refusing to "
            "compute one")
    return found


def reaches_bootloader_region(low, high):
    """Whether a range overlaps the application region the bootloader writes."""
    return low < BOOTLOADER_REGION[1] and BOOTLOADER_REGION[0] < high


def counterpart(step):
    """(vendor address, how it was obtained) for one step.

    A FUNCTION entry is looked up in Phase 3's measured match table. A DATA
    address is not a function and has no match row, so it takes the flat
    region shift Phase 3 measured. A raw code address inside a function body
    is neither, and is reported as not separately measured rather than being
    given a number this repository cannot support.
    """
    if step.kind == "function":
        found = measured_matches().get(step.address)
        if found is None:
            return None, "no measured counterpart"
        return found[0], f"matched ({found[1]})"
    if step.kind == "data":
        return step.address - RELOCATION_DELTA, "flat region shift"
    return None, "not separately measured"


def to_dict():
    matches = measured_matches()
    return {
        "answer_to_the_dispatch_question": {
            "choice": "b",
            "detail": "the commit QUEUES work. The 0x50/0x55 branch contains "
                      "no call instruction; it sets a command byte that a "
                      "state machine in another context drains, through two "
                      "further hops.",
            "confidence": "observed",
        },
        "constants": {
            "command_byte": COMMAND_BYTE,
            "commit_value": COMMIT_VALUE,
            "opcodes": {f"0x{code:02x}": note
                        for code, note in sorted(OPCODES.items())},
            "request_struct": REQUEST_STRUCT,
            "request_offsets": {"address": REQUEST_ADDRESS,
                                "flag": REQUEST_FLAG,
                                "opcode": REQUEST_OPCODE,
                                "pending": REQUEST_PENDING},
            "slot_base": SLOT_BASE,
            "slot_stride": SLOT_STRIDE,
            "target_addresses": list(TARGET_ADDRESSES),
        },
        "exit_gate": {
            "branch": "omit-all-writes",
            "detail": "The evidence supports proving a prototype CANNOT "
                      "corrupt existing configuration, not implementing safe "
                      "persistence. The format's magic, version, length and "
                      "checksum were not recovered, and the storage medium is "
                      "unidentified, so safe persistence cannot be "
                      "implemented from this evidence. What CAN be shown is "
                      "the negative, and it is a short argument: every route "
                      "into the erase primitives runs through the command "
                      "byte at 0x18022ce4, and a firmware that never writes "
                      "that byte and never fills the request struct at "
                      "0x18025ef4 cannot reach FUN_1800e2a8 or FUN_1800e2c4.",
            "what_a_custom_firmware_must_never_do": [
                f"write 0x{COMMAND_BYTE:08x}",
                f"write the request struct at 0x{REQUEST_STRUCT:08x}",
                "call FUN_1800e2a8 or FUN_1800e2c4, or their vendor "
                "counterparts",
                "dispatch vendor opcode 0x50 subcommand 0x55",
            ],
        },
        "hops": [
            {"confidence": item.confidence, "kind_basis": item.kind_basis,
             "mechanism": item.mechanism, "source": item.source,
             "target": item.target}
            for item in HOPS],
        "modifiable_ranges": [
            {"confidence": item.confidence, "high": item.high,
             "kind_basis": item.kind_basis, "label": item.label,
             "low": item.low,
             "overlaps_bootloader_region":
                 reaches_bootloader_region(item.low, item.high)}
            for item in MODIFIABLE_RANGES],
        "settings_format": {
            "checksum": None,
            "defaults": None,
            "length": None,
            "magic": None,
            "migration": None,
            "note": "NOT RECOVERED. The commit path passes ADDRESSES to erase "
                    "primitives; no header, magic, version, length or "
                    "checksum is constructed or verified anywhere in the "
                    "traced chain. What the commit persists FROM was not "
                    "established either: no copy from the 0x180202d8 per-key "
                    "bank or the 0x18024f0c global table into a staging "
                    "buffer appears in the traced path.",
            "version": None,
        },
        "steps": [
            {"address": item.address, "confidence": item.confidence,
             "detail": item.detail, "key": item.key,
             "kind_basis": item.kind_basis, "name": item.name,
             "kind": item.kind,
             "vendor_address": counterpart(item)[0],
             "vendor_match_confidence": counterpart(item)[1],
             "verified_against": item.verified_against}
            for item in STEPS],
        "storage_medium": {
            "identified": False,
            "note": "UNIDENTIFIED. The opcodes 0xd8 and 0x52 match the JEDEC "
                    "SPI-NOR block-erase opcodes, which is recognition and "
                    "not proof. No SPI controller register was identified, "
                    "the whole storage cluster touches no MMIO, and the only "
                    "hardware contact is a DMA setup into two unnamed "
                    "windows. Internal MCU storage, external U5 SPI NOR and a "
                    "RAM mirror are all still consistent with the evidence.",
            "registers_touched": ["0x40020008", "0x40020010", "0x40020014",
                                  "0x40020018", "0x4002001c", "0x45000000",
                                  "0x4500000c", "0x45000054"],
        },
    }


def verify():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    payload = to_dict()
    keys = {step.key for step in STEPS}
    check("every hop joins two declared steps",
          all(hop.source in keys and hop.target in keys for hop in HOPS),
          f"{len(STEPS)} steps, {len(HOPS)} hops")
    check("every step and hop carries a confidence from the closed set",
          all(item.confidence in CONFIDENCES
              for item in list(STEPS) + list(HOPS) + list(MODIFIABLE_RANGES)))
    check("every step says what it was verified against",
          all(step.verified_against in SOURCES for step in STEPS))
    check("the load-bearing steps are listing-verified",
          all(step.verified_against == "listing" for step in STEPS
              if step.key in ("commit_request", "command_byte", "erase_64k",
                              "erase_32k", "busy_check", "dma_setup")))
    check("the commit is recorded as queueing, not as programming storage",
          payload["answer_to_the_dispatch_question"]["choice"] == "b")
    check("the storage medium is NOT identified",
          payload["storage_medium"]["identified"] is False
          and "recognition and not proof"
          in payload["storage_medium"]["note"])
    check("no settings-format field is claimed",
          all(payload["settings_format"][field] is None
              for field in ("magic", "version", "length", "checksum",
                            "defaults", "migration")))
    check("the exit gate is the omit-all-writes branch",
          payload["exit_gate"]["branch"] == "omit-all-writes")
    check("no modifiable range overlaps the bootloader's application region",
          not any(item["overlaps_bootloader_region"]
                  for item in payload["modifiable_ranges"]),
          f"the application region is "
          f"0x{BOOTLOADER_REGION[0]:x}..0x{BOOTLOADER_REGION[1]:x}; the "
          "targets start at 0x320000")
    check("both erase opcodes are recorded with a recognition caveat",
          all("matches the JEDEC" in note for note in OPCODES.values()))
    check("every FUNCTION step has a measured vendor counterpart",
          all(step["vendor_address"] is not None for step in payload["steps"]
              if step["kind"] == "function"),
          "function counterparts are looked up in Phase 3's match table, "
          "never computed from a relocation rule")
    check("data steps take the flat region shift and code steps claim nothing",
          all(step["vendor_match_confidence"] == "flat region shift"
              for step in payload["steps"] if step["kind"] == "data")
          and all(step["vendor_address"] is None
                  for step in payload["steps"] if step["kind"] == "code"),
          "a raw address inside a function body has no match row, so none is "
          "invented for it")
    check("this module constructs no command bytes for transmission",
          not any(name.startswith("build_") or name.startswith("send_")
                  for name in globals()),
          "the module exposes no encoder and no transmit helper")
    return checks


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM map_nonvolatile_writes",
        "PURPOSE Phase 5E — the nonvolatile settings write path, static only",
        "NOTE This module reads code. It never speaks to the device and emits "
        "no command.",
        "",
        f"DISPATCH ANSWER ({payload['answer_to_the_dispatch_question']['choice']}) "
        f"{payload['answer_to_the_dispatch_question']['detail']}",
        "",
        "THE CHAIN",
    ]
    for step in STEPS:
        where = "n/a" if not step.address else f"0x{step.address:08x}"
        out.append(f"  [{step.confidence}] ({step.verified_against}) "
                   f"{step.key}: {step.name} @ {where}")
        out.append(f"      {step.detail}")
    out += ["", "HOPS"]
    for hop in HOPS:
        out.append(f"  {hop.source} -> {hop.target}  [{hop.confidence}] "
                   f"{hop.mechanism}")
    out += ["", "RANGES THE PATH MAY MODIFY"]
    for item in payload["modifiable_ranges"]:
        out.append(f"  0x{item['low']:06x}..0x{item['high']:06x} "
                   f"[{item['confidence']}] {item['label']}")
        out.append(f"      overlaps the bootloader's application region: "
                   f"{item['overlaps_bootloader_region']}")
    out += ["", "SETTINGS FORMAT", "  " + payload["settings_format"]["note"],
            "", "STORAGE MEDIUM", "  " + payload["storage_medium"]["note"],
            "", f"EXIT GATE: {payload['exit_gate']['branch']}",
            "  " + payload["exit_gate"]["detail"],
            "", "A CUSTOM FIRMWARE MUST NEVER:"]
    for item in payload["exit_gate"]["what_a_custom_firmware_must_never_do"]:
        out.append(f"  - {item}")
    out += ["", "CHECKS"]
    for item in verify():
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in verify())
    out += [
        "",
        f"RESULT write_map_ok={ok} checks={len(verify())}",
        "LIMITATION The erase EXTENTS assume each opcode's nominal size. That "
        "is recognition, not proof, and it is the weakest claim here.",
        "LIMITATION The context that runs the state machine and the drainer "
        "is not established: both are callerless in the application call "
        "graph.",
    ]
    return out


def markdown():
    payload = to_dict()
    lines = [
        "# Nonvolatile write path (Phase 5E)",
        "",
        "Generated by `tool/map_nonvolatile_writes.py`. Do not edit by hand.",
        "",
        "**Static tracing only. No command was constructed and no device was "
        "accessed.**",
        "",
        "## Dispatch answer",
        "",
        f"**({payload['answer_to_the_dispatch_question']['choice']})** "
        f"{payload['answer_to_the_dispatch_question']['detail']}",
        "",
        "## The chain",
        "",
        "| step | address | confidence | verified against |",
        "|---|---|---|---|",
    ]
    for step in STEPS:
        where = "—" if not step.address else f"`0x{step.address:08x}`"
        lines.append(f"| {step.name} | {where} | {step.confidence} | "
                     f"{step.verified_against} |")
    lines += ["", "## Ranges the path may modify", "",
              "| range | label | confidence | overlaps app region |",
              "|---|---|---|---|"]
    for item in payload["modifiable_ranges"]:
        lines.append(f"| `0x{item['low']:06x}..0x{item['high']:06x}` | "
                     f"{item['label']} | {item['confidence']} | "
                     f"{item['overlaps_bootloader_region']} |")
    lines += ["", "## Settings format", "",
              payload["settings_format"]["note"],
              "", "## Storage medium", "",
              payload["storage_medium"]["note"],
              "", f"## Exit gate: {payload['exit_gate']['branch']}", "",
              payload["exit_gate"]["detail"], "",
              "A custom firmware must never:", ""]
    for item in payload["exit_gate"]["what_a_custom_firmware_must_never_do"]:
        lines.append(f"- {item}")
    lines += ["", "## Checks", ""]
    for item in verify():
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def bodies():
    return {"nonvolatile-writes.json": json.dumps(to_dict(), indent=2,
                                                  sort_keys=True) + "\n",
            "nonvolatile-writes.md": markdown()}


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
    except (OSError, WriteMapError, json.JSONDecodeError) as exc:
        print(f"RESULT write_map_ok=False error={exc}")
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
        print(payload["nonvolatile-writes.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
