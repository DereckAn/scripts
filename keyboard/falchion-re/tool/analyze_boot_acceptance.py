#!/usr/bin/env python3
"""Reproduce the bootloader's boot-acceptance conditions from installed bytes.

Read-only and offline. Every constant below is read out of the mirrored
bootloader copy inside the installed dump — logical `[0x61000,0x71000)`, which
Phase 5 proved byte-identical to the vendor 1.00.58 primary and backup
bootloader — so the rules are derived from bytes present on the device rather
than from the vendor file alone.

The orchestrator `FUN_00007ec8` jumps to the selected image only when all four
of its gates pass. Two of them are *environmental*, not properties of the image:

  FUN_000029d4 == 0    the recovery key combination is not being held
  FUN_00002a44 == 0    the software bootloader-entry magic is not set in RAM

The other two are image properties, and they are the ones a builder must obey:

  selected_entry == DAT_00007f98    a constant compiled into the bootloader
  FUN_000026d0(0x6c000) == 0        the additive word-sum over the application
                                    region, base taken from DAT_0000277c

The transfer of control is not a branch. `BootHandoff`, a routine the bootloader
scatter-loads to RAM, copies a fixed 0x10000 bytes from the selected entry to
address 0 and then requests a system reset, so the application runs from address
zero after the reset. That is why the entry image is linked at 0.

Evidence: logs 75 and 101, `ghidra/scripts/FalchionDecompileTargets.java`.

No device access. Examples:
    python3 tool/analyze_boot_acceptance.py
    python3 tool/analyze_boot_acceptance.py --json
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")

# The mirrored copy of flash [0,0x10000) inside the application region, and the
# offset of the bootloader code within it. The container's +0x10 pointer is
# 0x60001000, so program address 0 is flash 0x1000.
MIRROR_BASE = 0x61000
BOOTLOADER_CODE = 0x1000
BOOTLOADER_LENGTH = 0xF000
BOOTLOADER_SHA256 = "c244aef0a92424cc92354a8cebd312be3098780d1ec062e05e5d5333e38d870c"

# Literal-pool words the orchestrator and its gates load, by program address.
LITERALS = {
    "selected_entry_constant": (0x7F98, "DAT_00007f98, the value the selected "
                                        "entry must equal before the jump"),
    "word_sum_base": (0x277C, "DAT_0000277c, the base FUN_000026d0 sums from"),
    "ram_entry_magic": (0x2A64, "DAT_00002a64, the magic FUN_00002a44 looks "
                                "for in RAM"),
    "ram_entry_flag_pointer": (0x2A60, "DAT_00002a60, the RAM word "
                                       "FUN_00002a44 reads"),
    "recovery_scan_buffer": (0x2A40, "DAT_00002a40, the RAM scan buffer "
                                     "FUN_000029d4 polls"),
    "vtor_pointer": (0x7FB0, "DAT_00007fb0, the register FUN_00007fa8 writes "
                             "the entry into"),
    "backup_container": (0x2B0C, "DAT_00002b0c, the second container "
                                 "FUN_00002af0 falls back to"),
    "systick_reload": (0x7F9C, "DAT_00007f9c, the reload the service loop "
                               "programs when no image is booted"),
}

# The word-sum length the orchestrator passes to FUN_000026d0.
WORD_SUM_LENGTH = 0x6C000
# The byte count BootHandoff is asked to copy, from the orchestrator's call.
HANDOFF_COPY_LENGTH = 0x10000
# Where BootHandoff copies to, from the same call site.
HANDOFF_DESTINATION = 0x0
# BootHandoff itself: bootloader program offset, runtime address, length.
HANDOFF_SOURCE = (0xCDFC, 0x18010000, 0x50)
HANDOFF_SHA256 = "1e4183918235efcdd7a0ded8055742bc9e51015e8da874f4604dd6861df7dee8"


@dataclass(frozen=True)
class Gate:
    """One condition in the orchestrator's accept expression."""
    order: int
    name: str
    function: str
    kind: str            # image | environment
    requirement: str
    evidence: str
    blocks_boot_when: str


@dataclass(frozen=True)
class Rule:
    """An image-content rule a builder must satisfy, with its confidence."""
    name: str
    requirement: str
    evidence: str
    confidence: str


@dataclass(frozen=True)
class Acceptance:
    image_sha256: str
    bootloader_sha256: str
    bootloader_matches_expected: bool
    literals: dict
    gates: tuple
    rules: tuple
    negatives: tuple
    handoff: dict
    checks: tuple
    unresolved: tuple


def bootloader_view(view):
    """The mirrored bootloader code as its own base-0 program image."""
    data = view.read(MIRROR_BASE + BOOTLOADER_CODE, BOOTLOADER_LENGTH)
    return data, hashlib.sha256(data).hexdigest()


def literal(data, address):
    if address + 4 > len(data):
        raise fi.ImageFormatError(
            f"bootloader program address 0x{address:x} is outside the "
            f"0x{len(data):x}-byte code image")
    return struct.unpack_from("<I", data, address)[0]


def analyze(view):
    data, digest = bootloader_view(view)
    values = {name: {"program_address": address,
                     "value": literal(data, address),
                     "role": role}
              for name, (address, role) in sorted(LITERALS.items())}

    entry_constant = values["selected_entry_constant"]["value"]
    word_sum_base = values["word_sum_base"]["value"]
    magic = values["ram_entry_magic"]["value"]

    checks = []

    def check(name, ok, detail=""):
        checks.append(fi.Check(f"{name}{(' — ' + detail) if detail else ''}", ok))

    check("the mirrored bootloader copy is the analysed image",
          digest == BOOTLOADER_SHA256, digest)

    layout = fi.parse(view)
    check("the image's SN_FWIN entry pointer equals the bootloader's constant",
          layout.fwin.entry_ptr == entry_constant,
          f"0x{layout.fwin.entry_ptr:08x} vs 0x{entry_constant:08x}")

    lo, hi = fi.APPLICATION_REGION
    check("the word-sum region the bootloader checks is the application region",
          word_sum_base - fi.FLASH_BASE == lo
          and word_sum_base - fi.FLASH_BASE + WORD_SUM_LENGTH == hi,
          f"0x{word_sum_base - fi.FLASH_BASE:x}.."
          f"0x{word_sum_base - fi.FLASH_BASE + WORD_SUM_LENGTH:x} vs "
          f"0x{lo:x}..0x{hi:x}")

    copy_lo = entry_constant - fi.FLASH_BASE
    copy_hi = copy_lo + HANDOFF_COPY_LENGTH
    check("the fixed handoff copy window lies inside the application region",
          lo <= copy_lo and copy_hi <= hi,
          f"0x{copy_lo:x}..0x{copy_hi:x} inside 0x{lo:x}..0x{hi:x}")

    entry = layout.records[0]
    check("record slot 0 begins at the copy window's start",
          entry.flash_off == copy_lo,
          f"0x{entry.flash_off:x} vs 0x{copy_lo:x}")
    check("record slot 0 fits inside the copy window",
          entry.flash_end <= copy_hi,
          f"0x{entry.flash_end:x} <= 0x{copy_hi:x}")

    offset, _runtime, length = HANDOFF_SOURCE
    check("the handoff routine is the analysed 0x50-byte block",
          hashlib.sha256(data[offset:offset + length]).hexdigest()
          == HANDOFF_SHA256,
          hashlib.sha256(data[offset:offset + length]).hexdigest())

    check("the RAM bootloader-entry magic is printable ASCII",
          all(0x20 <= byte < 0x7F
              for byte in struct.pack("<I", magic)),
          repr(struct.pack("<I", magic)))

    # The layout checks above only establish that the constants line up. The
    # image rules this phase recovered are about integrity — record checksums,
    # the application word-sum, the entry SP and reset vector, the container
    # chain — and those live in falchion_image.validate. Folding every one of
    # them in is what makes the verdict mean something: without this, flipping a
    # single application byte left the verdict True.
    validation = fi.validate(view)
    for item in validation.checks:
        check(f"integrity: {item.name}", item.ok)
    for result in validation.word_sums:
        check(f"integrity: {result.name} word-sum recomputes",
              result.ok,
              f"stored 0x{result.stored:08x} vs computed 0x{result.computed:08x}")

    gates = (
        Gate(1, "recovery key combination", "FUN_000029d4", "environment",
             "must return 0",
             "polls the scan buffer at "
             f"0x{values['recovery_scan_buffer']['value']:08x} up to 100 times, "
             "enabling and disabling interrupts around a scan tick each time, "
             "and returns 1 once the pattern (+0x0 == 0xa0 and +0x10 == 0x100) "
             "has held for 31 consecutive samples: the counter starts at "
             "zero and the cmp r5,#0x1e at 0x2a20 is tested before the "
             "increment, so the return happens on the 31st match",
             "the combination is held at power-on"),
        Gate(2, "selected entry equals the bootloader's constant",
             f"iVar2 == DAT_00007f98 (0x{entry_constant:08x})", "image",
             f"the SN_FWIN entry pointer must be exactly 0x{entry_constant:08x}",
             "a literal-pool word in the orchestrator, compared with the value "
             "FUN_00002af0 returned from the container scan",
             "the image declares any other entry address"),
        Gate(3, "software bootloader-entry flag", "FUN_00002a44", "environment",
             "must return 0",
             f"reads 0x{values['ram_entry_flag_pointer']['value']:08x} and "
             f"compares it with 0x{magic:08x}; when equal it clears the word "
             "and returns 1, so the flag is one-shot",
             "the application set the magic and reset"),
        Gate(4, "application-region word-sum", "FUN_000026d0(0x6c000)", "image",
             "must return 0",
             f"sums every 32-bit word of "
             f"0x{word_sum_base - fi.FLASH_BASE:x}.."
             f"0x{word_sum_base - fi.FLASH_BASE + WORD_SUM_LENGTH:x} in "
             "0x1000-byte pages and requires the final word to equal the sum; "
             "an all-0xff first page also fails",
             "the stored guard word does not equal the sum"),
    )

    rules = (
        Rule("entry pointer is fixed",
             f"SN_FWIN +0x10 must be exactly 0x{entry_constant:08x}. The entry "
             "image cannot be relocated.",
             "orchestrator gate 2, a constant comparison against "
             "DAT_00007f98",
             "proven"),
        Rule("POLICY: keep the entry image inside the copied window",
             f"0x{HANDOFF_COPY_LENGTH:x} bytes are copied from the entry "
             f"address to 0x{HANDOFF_DESTINATION:x} regardless of the record "
             "length. No bootloader branch tests whether the record fits: a "
             "longer record would simply have its tail left uncopied. Keeping "
             "the image inside the window is therefore a conservative policy "
             "for a builder, not a recovered bootloader requirement.",
             "BootHandoff, scatter-loaded from bootloader program "
             f"0x{HANDOFF_SOURCE[0]:x} to 0x{HANDOFF_SOURCE[1]:08x}, called as "
             f"(0, entry, 0x{HANDOFF_COPY_LENGTH:x}). The absence of a length "
             "test is what makes this a policy rather than a rule.",
             "policy — no control-flow dependency demonstrated"),
        Rule("application word-sum must be correct",
             "the final word of the application region must equal the 32-bit "
             "sum of every preceding word in it.",
             "orchestrator gate 4; base and length both read from bootloader "
             "constants rather than assumed",
             "proven"),
        Rule("every active record's chunked-CRC sum must be correct",
             "FUN_0000511c scans all eight record slots and verifies each slot "
             "whose length is nonzero.",
             "log 75 decompile, confirmed by log 95",
             "proven"),
        Rule("the entry image's initial SP must be in RAM",
             "FUN_00005240 dereferences the entry pointer and requires the "
             "first word to fall in an observed RAM range.",
             "log 75 decompile",
             "proven"),
        Rule("SN_FWIN magic and the container chain must be intact",
             "FUN_00008000 walks the boot-priority table, checks the SN_FWIN "
             "magic and only then validates the entry and records.",
             "log 75 decompile",
             "proven"),
    )

    # These are search results, not proofs. A constant-and-string search cannot
    # establish the absence of a check: an implementation could compute its
    # constants, or gate on a value with no distinctive byte pattern. Each entry
    # states exactly what was searched and how far the result reaches.
    negatives = (
        ("no cryptographic constant found",
         "Searched the 0xf000-byte bootloader at every byte offset for the "
         "32-bit constants 0x428a2f98, 0x6a09e667, 0x67452301, 0xefcdab89, "
         "0xd76aa478, 0x5a827999, 0xedb88320, 0x04c11db7, 0x1021, 0x8408, "
         "0x63636363 and 0x9e3779b9. Only 0xedb88320 at program 0xc78c and "
         "0x8408 at 0xc76c are present, both accounted for by the CRC engine of "
         "log 75.",
         "a search over a fixed constant list. It does not exclude a check "
         "whose constants are computed rather than stored."),
        ("no version, signature, key, auth or rollback string found",
         "Extracted every ASCII run of five or more printable bytes and matched "
         "them against ver/sign/rsa/sha/key/auth/roll/devi case variants. The "
         "only hits are USB HID descriptor text and '[BLD] CRC Verify PASS!!'.",
         "a search over strings. A numeric version or rollback comparison "
         "would leave no string at all, so this says nothing about one."),
        ("no device-ID gate found in the accept expression",
         "The only USB identity words in the bootloader are 0x0b05 and 0x1b7f, "
         "its own vendor and bootloader product IDs, and none of the four gates "
         "decompiled for this phase reads an identity.",
         "complete for the four gates, which were read in full. Call paths "
         "elsewhere in the bootloader were not exhaustively traced."),
        ("no configuration-dependent gate found",
         "The accept expression in FUN_00007ec8 is the four gates listed above "
         "and nothing else, and none of the four reads stored configuration.",
         "complete for the accept expression, silent about the rest of the "
         "bootloader."),
    )

    handoff = {
        "copy_destination": HANDOFF_DESTINATION,
        "copy_length": HANDOFF_COPY_LENGTH,
        # FUN_00007fa8 is `ldr r1,[VTOR_ptr]; ldr r1,[r1];
        # str r0,[r1,#0x1c]`, so the entry lands at *(VTOR) + 0x1c, slot
        # 7 of whatever table VTOR points at. It is NOT written to
        # 0xe000ed08 + 0x1c, which would be SCB SHCSR. The concrete
        # address depends on VTOR at runtime and is not a static fact.
        "entry_parked_in": "*(uint32_t *)0xe000ed08 + 0x1c",
        "entry_parked_in_basis": (
            "vector slot 7, the first Reserved slot, of the table VTOR "
            "points at when FUN_00007fa8 runs. The runtime value of VTOR "
            "is not a static property of the image, so no fixed address "
            "is claimed."),
        "mechanism": "copy then system reset, not a branch",
        "reset_request": "AIRCR = (AIRCR & 0x700) | 0x05fa0000 + 4, i.e. "
                         "VECTKEY with SYSRESETREQ, preserving PRIGROUP",
        "routine_length": HANDOFF_SOURCE[2],
        "routine_program_offset": HANDOFF_SOURCE[0],
        "routine_runtime_address": HANDOFF_SOURCE[1],
    }

    unresolved = (
        "What makes address 0 writable is not established from these bytes. "
        "BootHandoff copies there and then resets, so a RAM or remap window "
        "must be aliased at 0, but the register that arranges it is not "
        "identified.",
        "The recovery scan pattern (+0x0 == 0xa0, +0x10 == 0x100) is read from "
        "a RAM buffer the bootloader's own scan tick fills. Which physical keys "
        "produce it is not established.",
        "Any ROM or first-stage condition ahead of this bootloader is still "
        "unexamined.",
    )

    return Acceptance(
        image_sha256=view.sha256(), bootloader_sha256=digest,
        bootloader_matches_expected=digest == BOOTLOADER_SHA256,
        literals=values, gates=gates, rules=rules, negatives=negatives,
        handoff=handoff, checks=tuple(checks), unresolved=unresolved)


def to_dict(acceptance):
    return {
        "bootloader_matches_expected": acceptance.bootloader_matches_expected,
        "bootloader_sha256": acceptance.bootloader_sha256,
        "checks": [{"name": check.name, "ok": check.ok}
                   for check in acceptance.checks],
        "gates": [
            {"blocks_boot_when": gate.blocks_boot_when,
             "evidence": gate.evidence, "function": gate.function,
             "kind": gate.kind, "name": gate.name, "order": gate.order,
             "requirement": gate.requirement}
            for gate in acceptance.gates
        ],
        "handoff": acceptance.handoff,
        "image_sha256": acceptance.image_sha256,
        "literals": acceptance.literals,
        "negatives": [{"basis": basis, "finding": finding,
                       "strength": strength}
                      for finding, basis, strength in acceptance.negatives],
        "ok": all(check.ok for check in acceptance.checks),
        "rules": [
            {"confidence": rule.confidence, "evidence": rule.evidence,
             "name": rule.name, "requirement": rule.requirement}
            for rule in acceptance.rules
        ],
        "unresolved": list(acceptance.unresolved),
    }


def report_lines(acceptance):
    out = [
        "PROGRAM analyze_boot_acceptance",
        "PURPOSE the bootloader's boot-acceptance conditions, from installed bytes",
        f"IMAGE_SHA256 {acceptance.image_sha256}",
        f"BOOTLOADER_SHA256 {acceptance.bootloader_sha256} "
        f"(mirrored copy at logical 0x{MIRROR_BASE + BOOTLOADER_CODE:x}, "
        f"0x{BOOTLOADER_LENGTH:x} bytes, program base 0)",
    ]
    for name, item in acceptance.literals.items():
        out.append(f"LITERAL {name} @prog 0x{item['program_address']:04x} = "
                   f"0x{item['value']:08x}  {item['role']}")
    out.append("")
    out.append("ACCEPT EXPRESSION — FUN_00007ec8 jumps only when all four pass")
    for gate in acceptance.gates:
        out += [
            f"  GATE {gate.order} [{gate.kind}] {gate.name}",
            f"    function: {gate.function}",
            f"    requirement: {gate.requirement}",
            f"    evidence: {gate.evidence}",
            f"    blocks boot when: {gate.blocks_boot_when}",
        ]
    out += ["", "TRANSFER OF CONTROL"]
    for key in sorted(acceptance.handoff):
        value = acceptance.handoff[key]
        rendered = f"0x{value:x}" if isinstance(value, int) else value
        out.append(f"  {key}: {rendered}")
    out += ["", "IMAGE RULES A BUILDER MUST SATISFY"]
    for rule in acceptance.rules:
        out += [f"  [{rule.confidence}] {rule.name}",
                f"    {rule.requirement}",
                f"    evidence: {rule.evidence}"]
    out += ["", "SEARCHES THAT RETURNED NOTHING",
            "  Search results, not proofs of absence."]
    for finding, basis, strength in acceptance.negatives:
        out += [f"  {finding}", f"    searched: {basis}",
                f"    reach: {strength}"]
    out.append("")
    for check in acceptance.checks:
        out.append(f"  {'PASS' if check.ok else 'FAIL'} {check.name}")
    ok = all(check.ok for check in acceptance.checks)
    out.append(f"RESULT image_rules_ok={ok} checks_run={len(acceptance.checks)} "
               f"gates={len(acceptance.gates)} rules={len(acceptance.rules)}")
    out.append("RESULT_MEANING image_rules_ok covers only the two IMAGE "
               "gates and the integrity checks they rest on. The two "
               "environmental gates cannot be evaluated from an image at "
               "all, so this is never a statement that the bootloader "
               "would accept this image, let alone that it would run.")
    for line in acceptance.unresolved:
        out.append(f"UNRESOLVED {line}")
    out.append("LIMITATION Two of the four gates are environmental, so an image "
               "that satisfies every rule here can still be refused because the "
               "recovery combination is held or the RAM entry flag is set. "
               "Passing the image rules is necessary, not sufficient, and says "
               "nothing about whether the image then runs correctly.")
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=INSTALLED)
    parser.add_argument("--base", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        view = fi.ImageView(args.image.read_bytes(), args.base)
        acceptance = analyze(view)
    except (OSError, fi.ImageFormatError) as exc:
        print(f"RESULT image_rules_ok=False error={exc}")
        return 1
    if args.json:
        print(json.dumps(to_dict(acceptance), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(acceptance)))
    return 0 if all(check.ok for check in acceptance.checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
