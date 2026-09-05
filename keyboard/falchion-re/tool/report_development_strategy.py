#!/usr/bin/env python3
"""Phase 6: the development-strategy architecture decision record.

Generates notes/development-strategy.md and .json from one data model, so the
ADR's structured claims can be checked rather than merely asserted.

THIS IS A DECISION DOCUMENT, NOT A RUNBOOK. It contains no flashing
instructions, no device command sequences and no updater invocation. A unit
test asserts that the generated Markdown contains no device-command framing,
because the difference between "the application region is writable over the
vendor-HID channel" and a sequence someone could paste is the whole safety
margin of this phase.

No device access. Examples:
    python3 tool/report_development_strategy.py
    python3 tool/report_development_strategy.py --json
    python3 tool/report_development_strategy.py --write
    python3 tool/report_development_strategy.py --check
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
LOGS = ROOT / "logs"

STATUS = "decided"
DECISION = "path-a-first"

# Logs the ADR cites. Every one is checked to exist and to match its recorded
# SHA-256 in logs/SHA256SUMS, so a citation cannot rot silently.
CITED_LOGS = (
    "77-image-builder-roundtrip.txt",
    "92-full-app-region-backup.txt",
    "95-phase1-record-scan-correction.txt",
    "101-boot-acceptance-resolved.txt",
    "105-decompressed-region-reconstruction.txt",
    "107-phase5b-usb-routing.txt",
    "109-phase5c-scan-scheduling.txt",
    "110-phase5d-hall-acquisition.txt",
    "111-phase5e-nonvolatile-settings.txt",
    "112-phase5f-rgb-lamparray.txt",
    "113-phase5g-and-final-dependency-map.txt",
    "114-phase5g-watchdog-correction.txt",
)

# Phase 8's criteria, verbatim in substance from the plan.
PHASE8_CRITERIA = (
    "a fully understood control/data path",
    "a small and precisely bounded change",
    "no clock, watchdog, flash-write, calibration, USB-boot, or recovery effect",
    "an observable result if a future live test is ever approved",
    "exact original-byte assertions and a clear rollback image",
)


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    verdict: str          # "passes" or "fails"
    failing_criteria: tuple
    reasoning: str
    evidence: tuple


CANDIDATE_TARGETS = (
    Target("product_string", "the USB product string in the application record",
           "passes", (),
           "The string is stored as plain ASCII in the decompressed region and "
           "is turned into a UTF-16 string descriptor at runtime, so a "
           "same-length byte replacement changes what a host displays and "
           "nothing else. The path from those bytes to the descriptor is "
           "traced end to end. It touches no clock, watchdog, flash-write, "
           "calibration or boot path, and the bootloader's own product "
           "identity is a separate value that this does not alter — so the "
           "recovery channel is unaffected. The existing builder already "
           "demonstrates the offline round trip for exactly this kind of "
           "byte, including decompressing the region to confirm where the "
           "patched byte lands.",
           ("log 105: the region holds the ASCII strings and the LANGID dword",
            "log 107 step 4: the descriptors are built at runtime from that "
            "region",
            "log 77: the builder's decompress round-trip for a patched byte")),
    Target("key_policy_table", "one ordinary entry in a key-policy table",
           "passes", (),
           "The translation and record-index tables live in the uncompressed "
           "copy region, so a patch is a direct byte change with no "
           "compression interaction. A single ordinary key's entry is a small "
           "bounded change with an observable result, and it touches no "
           "clock, watchdog, flash-write, calibration or boot path. RANKED "
           "BELOW the product string only because some historical KBID "
           "mappings in this repository are marked unverified, so the "
           "specific entry chosen would need its own citation.",
           ("log 109: the tables are read by the report pipeline every tick",
            "log 110: the key-id lookup's stride arithmetic is "
            "listing-verified")),
    Target("actuation_threshold", "the Hall actuation threshold constant",
           "fails",
           ("a fully understood control/data path",
            "no clock, watchdog, flash-write, calibration, USB-boot, or "
            "recovery effect"),
           "Tempting, because the comparison is recovered as executable "
           "arithmetic and the constant is a single byte. It fails on two "
           "criteria. The control/data path is NOT fully understood: Phase 5D "
           "recovered what happens to a travel byte but not what produces "
           "one, so the input scale the threshold divides is unknown. And "
           "changing when a key actuates is a calibration effect by any "
           "reasonable reading of the criterion.",
           ("log 110 step 4: the producer of the travel bytes is not "
            "recovered",
            "log 110 step 1: the threshold itself is listing-verified")),
    Target("usb_vid_pid", "the application's USB vendor and product IDs",
           "fails",
           ("no clock, watchdog, flash-write, calibration, USB-boot, or "
            "recovery effect",),
           "This is the target that looks safest and is not. The device's "
           "only non-physical route back to a recoverable state depends on "
           "addressing the application by its current identity; changing that "
           "identity is a recovery effect. The physical alternative is a "
           "recovery key combination whose PHYSICAL KEYS ARE NOT ESTABLISHED "
           "in this repository, so a mistake here could leave no documented "
           "way back.",
           ("log 101: the recovery gate is a key-combination poll whose "
            "physical keys are recorded as unresolved",
            "log 92: the verified backup covers the application region only")),
    Target("nmi_escalation_limit", "the NMI watchdog escalation limit",
           "fails",
           ("no clock, watchdog, flash-write, calibration, USB-boot, or "
            "recovery effect",),
           "A one-byte change in the region's initialised data that directly "
           "alters watchdog escalation. It is excluded by name.",
           ("log 114: the limit's power-on value is 1 and the NMI path ends "
            "in a system reset",)),
    Target("lamparray_behaviour", "the LampArray lighting behaviour",
           "fails",
           ("a fully understood control/data path",),
           "The host-facing protocol is fully recovered, but the driver that "
           "consumes the frame buffer is not identified, so the hardware "
           "consequence of any change is unknown. Phase 5F could not even "
           "prove that an all-zero frame means the LEDs are off.",
           ("log 112 step 5: both frame consumers reach zero resolved MMIO",
            "log 112 step 6: the hardware idle state is not provable")),
    Target("bootloader_region", "anything in the bootloader region",
           "fails",
           ("no clock, watchdog, flash-write, calibration, USB-boot, or "
            "recovery effect",
            "exact original-byte assertions and a clear rollback image"),
           "Outside the writable range the bootloader guards, absent from the "
           "verified backup, and the one component whose loss has no "
           "documented recovery. Excluded absolutely, and the builder already "
           "refuses it.",
           ("log 92: the backup covers the application region only",
            "log 101: the bootloader is the component that evaluates every "
            "boot gate")),
)


@dataclass(frozen=True)
class Gate:
    key: str
    name: str
    what_would_satisfy_it: str
    evidence: tuple


PATH_B_GATES = (
    Gate("hall_acquisition", "the Hall acquisition boundary",
         "A recovered producer for the per-key travel bytes: some function, in "
         "some image, that fills that array from hardware. Until then a "
         "replacement application cannot read a keypress at all, so it cannot "
         "be a keyboard. THIS IS THE LARGEST GATE.",
         ("log 110 step 4: the buffer's address appears in no aligned word of "
          "any image and is reached only through a runtime-filled pointer",
          "log 113: classified unresolved, a blocker rather than an omission")),
    Gate("second_context_ownership", "what the second execution context owns",
         "An analysis of the 0x18038000 image, which is preserved and has "
         "never been imported. It is started at boot and waited for, and it "
         "owns something the application does not — which makes it the "
         "leading candidate for the acquisition. Resolving it may close the "
         "gate above, or may prove it is somewhere else entirely.",
         ("log 113 step 4: the start mechanism and the token handshake",
          "log 113 step 4: ownership is explicitly recorded as unresolved")),
    Gate("clock_frequency", "the clock configuration",
         "Any unit-bearing evidence: a crystal value, a PLL multiplier, or a "
         "measured relationship. A replacement can copy the reset sequence "
         "without it, but it cannot reason about USB timing, scan rate or "
         "watchdog margin — and the watchdog margin now matters, because the "
         "block is fed on a divided tick.",
         ("log 113 step 1: no constant in the reset chain carries a unit",
          "log 114: the feed rides the prescaler's divide-by-8 job")),
    Gate("watchdog_policy", "a decided watchdog policy",
         "Not an evidence gate but a design one, listed because it is easy to "
         "miss: a replacement must decide, deliberately, whether to reproduce "
         "the periodic feed and the NMI acknowledge, or to disable the block "
         "and remove both. Inheriting half of the vendor's arrangement is the "
         "failure mode.",
         ("log 114: three access paths, two of them invisible to the MMIO "
          "census",)),
    Gate("address_zero_aliasing", "what makes address 0 writable",
         "The boot handoff copies the entry image to address 0 and then "
         "resets, so some remap or alias must exist. The register that "
         "arranges it is not identified, and a replacement's entry image has "
         "to live under the same arrangement.",
         ("log 101: recorded as an unresolved boot-acceptance item",)),
)


def cited_log_digests():
    """{log name: sha256}, read from the files themselves."""
    out = {}
    for name in CITED_LOGS:
        path = LOGS / name
        if not path.exists():
            raise StrategyError(f"cited log {name} is missing")
        out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def recorded_digests():
    """{log name: sha256} as logs/SHA256SUMS records them."""
    out = {}
    for line in (LOGS / "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        digest, _, path = line.partition("  ")
        out[Path(path.strip()).name] = digest.strip()
    return out


class StrategyError(ValueError):
    """A citation or an input does not hold up."""


def to_dict():
    return {
        "cited_logs": cited_log_digests(),
        "decision": DECISION,
        "decision_summary":
            "Path A first, for offline format validation only, and Path B not "
            "yet. The plan's default is CONFIRMED, and the evidence has "
            "hardened it rather than softened it: Path B is not merely "
            "premature, it currently cannot produce a typing keyboard.",
        "path_a": {
            "integrity_fields_a_patch_must_recompute": [
                "each affected SN_FWIN record's chunked-CRC sum at record+0x8",
                "the application-region additive word-sum at logical 0x7bffc, "
                "last, because it covers the record checksum fields too",
            ],
            "integrity_fields_that_must_not_be_touched": [
                "the primary bootloader word-sum at logical 0x0fffc — absent "
                "from an installed app-only source and outside the writable "
                "range",
                "the backup bootloader word-sum at logical 0x70ffc — only "
                "relevant if that region changed, and policy is that it does "
                "not",
            ],
            "layout_constraints": [
                "a patch must fit inside an existing record; the record table "
                "is a fixed eight slots and slot 2 is an inactive hole, not "
                "free space",
                "no new record may be added without proven layout rules, and "
                "those rules are not proven",
                "a patch inside the compressed scatter region must be "
                "validated by decompressing, because a byte there may be a "
                "literal or may be a back-reference source",
            ],
            "vendor_derived_code": "Nearly all of it. Path A changes a "
                                   "handful of bytes and inherits the entire "
                                   "vendor loader, RTOS, USB stack, scan "
                                   "pipeline and lighting code. This is worth "
                                   "stating plainly: Path A validates format "
                                   "knowledge, it does not produce our own "
                                   "firmware.",
        },
        "path_b": {
            "blocking_verdict":
                "Path B currently CANNOT produce a typing keyboard. With the "
                "Hall acquisition unrecovered, a replacement application "
                "could initialise, tick, enumerate, build reports and "
                "transmit them, and every key would read as released "
                "forever. That is a blocker, not a detail.",
            "known_services": 6,
            "must_neutralize_services": 3,
            "toolchain": [
                "a Cortex-M3 bare-metal toolchain (Thumb-2, soft-float)",
                "a linker script placing an entry image whose SN_FWIN entry "
                "pointer equals the bootloader's constant exactly, and an "
                "application image at its own load address",
                "an ARMv7-M vector table matching the recovered extent, with "
                "the fault and NMI vectors deliberately decided rather than "
                "left default",
                "a container writer for the SN_FWIN record table and the "
                "scatter-load descriptors, including whichever regions are "
                "copied or decompressed",
            ],
            "unresolved_blockers": 3,
        },
        "phase8_criteria": list(PHASE8_CRITERIA),
        "phase_b_gates": [
            {"evidence": list(gate.evidence), "key": gate.key,
             "name": gate.name,
             "what_would_satisfy_it": gate.what_would_satisfy_it}
            for gate in PATH_B_GATES],
        "recovery": {
            "backup_covers": "the application region only",
            "bootloader_self_protection":
                "the bootloader's write path guards its accepted address "
                "range, so it does not overwrite itself",
            "dangerous_case":
                "an image that is checksum-correct and still does not "
                "enumerate. It passes the boot gate, so the device may leave "
                "bootloader mode and become unreachable by the software "
                "route; the remaining documented route is a recovery key "
                "combination whose physical keys this repository does NOT "
                "establish.",
            "vendor_image_role":
                "the preserved 1.00.58 image is a restore SOURCE for the "
                "application region, and it is a different version from the "
                "installed 1.59 — restoring it is a downgrade, not a "
                "byte-for-byte return to the observed state",
        },
        "status": STATUS,
        "targets": [
            {"evidence": list(target.evidence),
             "failing_criteria": list(target.failing_criteria),
             "key": target.key, "name": target.name,
             "reasoning": target.reasoning, "verdict": target.verdict}
            for target in CANDIDATE_TARGETS],
    }


def verify():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    payload = to_dict()
    recorded = recorded_digests()
    missing = [name for name in CITED_LOGS if name not in recorded]
    check("every cited log is recorded in logs/SHA256SUMS",
          not missing, ", ".join(missing) or f"{len(CITED_LOGS)} logs")
    mismatched = [name for name, digest in payload["cited_logs"].items()
                  if recorded.get(name) != digest]
    check("every cited log's content matches its recorded hash",
          not mismatched, ", ".join(mismatched) or "all match")
    check("the decision is one of the two paths, taken",
          payload["decision"] == "path-a-first" and payload["status"]
          == "decided")
    check("Path B is recorded as unable to produce a typing keyboard",
          "CANNOT produce a typing keyboard"
          in payload["path_b"]["blocking_verdict"])
    check("Path A is recorded as leaving nearly all code vendor-derived",
          "Nearly all of it" in payload["path_a"]["vendor_derived_code"])
    check("every candidate target has a verdict and reasoning",
          all(target.verdict in ("passes", "fails")
              and len(target.reasoning) > 80
              for target in CANDIDATE_TARGETS))
    check("every FAILING target names which criteria it fails",
          all(target.failing_criteria for target in CANDIDATE_TARGETS
              if target.verdict == "fails"))
    check("every named failing criterion is one of Phase 8's",
          all(criterion in PHASE8_CRITERIA
              for target in CANDIDATE_TARGETS
              for criterion in target.failing_criteria),
          "a target cannot fail a criterion the plan does not state")
    check("at least one target passes and at least two fail",
          sum(1 for t in CANDIDATE_TARGETS if t.verdict == "passes") >= 1
          and sum(1 for t in CANDIDATE_TARGETS if t.verdict == "fails") >= 2,
          f"{sum(1 for t in CANDIDATE_TARGETS if t.verdict == 'passes')} pass, "
          f"{sum(1 for t in CANDIDATE_TARGETS if t.verdict == 'fails')} fail")
    check("every Path B gate says what would satisfy it",
          all(len(gate.what_would_satisfy_it) > 80 for gate in PATH_B_GATES))
    check("the Hall acquisition is named the largest gate",
          "LARGEST GATE" in next(
              gate for gate in PATH_B_GATES
              if gate.key == "hall_acquisition").what_would_satisfy_it)
    check("every target and gate cites at least one log",
          all(item.evidence for item in
              list(CANDIDATE_TARGETS) + list(PATH_B_GATES)))
    check("the recovery section names the dangerous case",
          "checksum-correct and still does not enumerate"
          in payload["recovery"]["dangerous_case"])
    return checks


# Command-shaped patterns the ADR must never contain. The point is not to ban
# the word "flash" — the document is about flash layout — but to ban anything
# a reader could paste or follow.
FORBIDDEN_PATTERNS = (
    r"(?m)^\s*\$\s",                 # a shell prompt
    r"/dev/hidraw",
    r"\bsudo\b",
    r"\bdfu-util\b",
    r"\bfwupd\b",
    r"--run\b",
    r"\bhid\.Device\b",
    r"\bd\.write\b",
    r"\bwrite_report\b",
    r"\bsend (?:the |this )?(?:report|packet|command)\b",
    r"\bflash (?:the|this|it) \b",
    r"\bthen (?:flash|program|erase|write) \b",
    r"\brun the following\b",
    r"\bplug (?:in|the)\b",
)


def command_framing_hits(text):
    """Every forbidden pattern that appears in `text`."""
    return tuple(pattern for pattern in FORBIDDEN_PATTERNS
                 if re.search(pattern, text, re.IGNORECASE))


def markdown():
    payload = to_dict()
    lines = [
        "# ADR: development strategy for a custom Falchion firmware",
        "",
        f"**Status: {STATUS}.** Generated by "
        "`tool/report_development_strategy.py`. Do not edit by hand.",
        "",
        "> This is a decision record. It contains no flashing instructions, no "
        "device command sequences and no updater invocation, and a test "
        "asserts it stays that way. Nothing here authorises touching the "
        "device.",
        "",
        "## Context",
        "",
        "Phases 1–5 produced a container parser, an installed-versus-vendor "
        "comparison, a code map, the boot-acceptance gates, and six service "
        "models covering USB routing, the scan pipeline, Hall actuation, the "
        "nonvolatile write path, lighting and the platform dependencies. The "
        "final gate classified seventeen services: six must-implement, three "
        "must-neutralize, five may-omit and **three unresolved**. Phase 6 "
        "chooses how to proceed on that evidence rather than on enthusiasm.",
        "",
        "## Options",
        "",
        "### Path A — controlled patching",
        "",
        "Keep the original loader and application; change a narrowly "
        "understood function or table.",
        "",
        "**What is understood well enough to patch.** The USB identity "
        "strings, because the path from stored ASCII to a runtime string "
        "descriptor is traced end to end (log 105, log 107). The key-policy "
        "tables, because the report pipeline reads them every tick and the "
        "index arithmetic is listing-verified (log 109, log 110). **Not** the "
        "Hall actuation constants, because Phase 5D recovered what happens to "
        "a travel byte and not what produces one (log 110). **Not** the "
        "LampArray behaviour, because the driver that consumes the frame "
        "buffer is unidentified (log 112).",
        "",
        "**Integrity fields a patch must recompute**, in dependency order:",
        "",
    ]
    for item in payload["path_a"]["integrity_fields_a_patch_must_recompute"]:
        lines.append(f"- {item}")
    lines += ["", "**Integrity fields that must not be touched:**", ""]
    for item in payload["path_a"]["integrity_fields_that_must_not_be_touched"]:
        lines.append(f"- {item}")
    lines += ["", "**Size and layout constraints:**", ""]
    for item in payload["path_a"]["layout_constraints"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "**What remains vendor-derived.** "
        + payload["path_a"]["vendor_derived_code"],
        "",
        "### Path B — clean-room application replacement",
        "",
        "Keep the device's existing immutable boot path; provide a newly built "
        "application record.",
        "",
        f"**{payload['path_b']['blocking_verdict']}**",
        "",
        "Against the dependency map: six services are must-implement and their "
        "evidence is in hand for five of them — reset/clock/RAM as a "
        "preserved sequence, the tick, key-state generation, USB enumeration "
        "and the boot-keyboard route. Three are must-neutralize and all three "
        "are now understood: the three-path watchdog arrangement (log 114), "
        "the NMI reset, and the second execution context with its token "
        "handshake (log 113). Three are unresolved, and those are the gates "
        "below.",
        "",
        "**Toolchain and linker support Path B concretely needs:**",
        "",
    ]
    for item in payload["path_b"]["toolchain"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "Path A needs none of that. It needs the offline builder that already "
        "exists.",
        "",
        "## Comparison",
        "",
        "| dimension | Path A | Path B |",
        "|---|---|---|",
        "| recovery risk | a rejected image leaves the device in bootloader "
        "mode; the dangerous case is a checksum-correct image that does not "
        "enumerate | identical mechanism, but far more ways to reach the "
        "dangerous case |",
        "| unknown hardware dependencies | inherits all of them, unchanged and "
        "working | must satisfy all of them from scratch, including three that "
        "are unresolved |",
        "| toolchain | none beyond the existing offline builder | a full "
        "bare-metal toolchain, linker script and container writer |",
        "| size and layout | must fit an existing record; no new records | "
        "free within the record, but the container rules must be reproduced |",
        "| debugging | none on the device | none on the device |",
        "| vendor-derived code | nearly all | none, by construction |",
        "",
        "**Debugging deserves its own sentence, because it applies equally to "
        "both and changes the calculus for both.** There is no on-device "
        "debugging available today — no trace, no console, no working "
        "breakpoint path. Every iteration is therefore blind: the only signal "
        "is whether the device enumerates afterwards. That makes a small "
        "reversible change enormously more attractive than a large one, and it "
        "is the single strongest argument for Path A first.",
        "",
        "## Recovery risk in detail",
        "",
        f"- The verified backup covers **{payload['recovery']['backup_covers']}**"
        " (log 92).",
        f"- {payload['recovery']['bootloader_self_protection']} (log 101).",
        f"- **The dangerous case:** {payload['recovery']['dangerous_case']} "
        "(log 101).",
        f"- {payload['recovery']['vendor_image_role']}.",
        "",
        "## Decision",
        "",
        f"**{payload['decision_summary']}**",
        "",
        "The plan's default was Path A for offline format validation, then "
        "Path B once the platform map is credible. That default is confirmed, "
        "and the reason to state it as *confirmed* rather than *inherited* is "
        "that the evidence gathered since could have overturned it and did "
        "not. The platform map is now substantially credible — six services "
        "understood, three neutralization policies recovered — and Path B is "
        "still blocked, because credibility of the map is not the binding "
        "constraint. The binding constraint is that nothing in either analysed "
        "image produces a key reading.",
        "",
        "## Evidence gates for Path B",
        "",
        "Path B becomes advisable when these pass. They are stated as evidence "
        "gates, not milestones.",
        "",
    ]
    for gate in PATH_B_GATES:
        lines.append(f"### {gate.name}")
        lines.append("")
        lines.append(gate.what_would_satisfy_it)
        lines.append("")
        for citation in gate.evidence:
            lines.append(f"- {citation}")
        lines.append("")
    lines += [
        "## Candidate first targets under Path A",
        "",
        "Assessed against Phase 8's criteria:",
        "",
    ]
    for criterion in PHASE8_CRITERIA:
        lines.append(f"- {criterion}")
    lines += ["", "### Targets that pass", ""]
    for target in CANDIDATE_TARGETS:
        if target.verdict != "passes":
            continue
        lines += [f"**{target.name}** — {target.reasoning}", ""]
        for citation in target.evidence:
            lines.append(f"- {citation}")
        lines.append("")
    lines += ["### Targets that fail, and why", ""]
    for target in CANDIDATE_TARGETS:
        if target.verdict != "fails":
            continue
        lines += [f"**{target.name}** — fails: "
                  + "; ".join(target.failing_criteria) + ".", "",
                  target.reasoning, ""]
        for citation in target.evidence:
            lines.append(f"- {citation}")
        lines.append("")
    lines += [
        "## Consequences",
        "",
        "- Phase 7 builds the offline builder against Path A's requirements: "
        "an installed-image adapter, allowlisted source hashes, original-byte "
        "assertions and the two recomputable integrity fields.",
        "- Phase 8's artefact is a byte-level patch to a passing target above, "
        "produced offline and named `UNTESTED`.",
        "- Path B is deferred, not abandoned. The gates above are the "
        "condition, and the most promising single action against them is "
        "analysing the second execution context's image, which is preserved "
        "and has never been imported.",
        "- Nothing in this decision authorises a live experiment. Phase 9's "
        "independent review remains between any artefact and any device.",
        "",
        "## Checks",
        "",
    ]
    for item in verify():
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def bodies():
    return {"development-strategy.json": json.dumps(to_dict(), indent=2,
                                                    sort_keys=True) + "\n",
            "development-strategy.md": markdown()}


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM report_development_strategy",
        "PURPOSE Phase 6 — the development-strategy decision record",
        "",
        f"STATUS {payload['status']}   DECISION {payload['decision']}",
        "  " + payload["decision_summary"],
        "",
        "PATH B BLOCKING VERDICT",
        "  " + payload["path_b"]["blocking_verdict"],
        "",
        "EVIDENCE GATES FOR PATH B",
    ]
    for gate in PATH_B_GATES:
        out.append(f"  - {gate.name}")
    out += ["", "PATH A CANDIDATE TARGETS"]
    for target in CANDIDATE_TARGETS:
        out.append(f"  [{target.verdict}] {target.name}")
        if target.failing_criteria:
            for criterion in target.failing_criteria:
                out.append(f"      fails: {criterion}")
    out += ["", "CHECKS"]
    for item in verify():
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in verify())
    out += [
        "",
        f"RESULT adr_ok={ok} checks={len(verify())}",
        "LIMITATION This is a decision record. It contains no flashing "
        "instructions and no device command sequences, and a test asserts it.",
    ]
    return out


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
    except (OSError, StrategyError) as exc:
        print(f"RESULT adr_ok=False error={exc}")
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
        print(payload["development-strategy.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
