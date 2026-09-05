#!/usr/bin/env python3
"""Offline tests for the boot-acceptance analyzer.

Reads the preserved installed dump and in-memory mutations of it. No device
access, no writes.
"""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_boot_acceptance as ba
import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"


def installed_view():
    return fi.ImageView(INSTALLED.read_bytes(), 0x10000)


def mutated(patch):
    view = installed_view()
    data = bytearray(view.data)
    patch(data, view.base)
    return fi.ImageView(bytes(data), view.base)


class Provenance(unittest.TestCase):
    """The rules must come from bytes that are on the device."""

    def test_the_bootloader_copy_is_read_from_the_installed_dump(self):
        result = ba.analyze(installed_view())
        self.assertTrue(result.bootloader_matches_expected)
        self.assertEqual(result.bootloader_sha256, ba.BOOTLOADER_SHA256)

    def test_the_copy_equals_the_vendor_primary_bootloader(self):
        vendor = fi.ImageView(VENDOR.read_bytes(), 0)
        primary = vendor.read(ba.BOOTLOADER_CODE, ba.BOOTLOADER_LENGTH)
        mirrored, digest = ba.bootloader_view(installed_view())
        self.assertEqual(mirrored, primary)
        self.assertEqual(digest, hashlib.sha256(primary).hexdigest())

    def test_a_changed_bootloader_copy_fails_the_provenance_check(self):
        def patch(data, base):
            data[ba.MIRROR_BASE + ba.BOOTLOADER_CODE + 0x100 - base] ^= 0xFF
        result = ba.analyze(mutated(patch))
        self.assertFalse(result.bootloader_matches_expected)
        failed = [check.name for check in result.checks if not check.ok]
        self.assertTrue(any("mirrored bootloader copy" in name
                            for name in failed), failed)


class Literals(unittest.TestCase):
    """Every gate constant must be read, not assumed."""

    @classmethod
    def setUpClass(cls):
        cls.result = ba.analyze(installed_view())
        cls.values = {name: item["value"]
                      for name, item in cls.result.literals.items()}

    def test_the_top_level_comparison_constant(self):
        self.assertEqual(self.values["selected_entry_constant"], 0x60011000)

    def test_the_word_sum_base_is_the_application_region_start(self):
        self.assertEqual(self.values["word_sum_base"], 0x60010000)
        self.assertEqual(
            self.values["word_sum_base"] - fi.FLASH_BASE
            + ba.WORD_SUM_LENGTH, fi.APPLICATION_REGION[1])

    def test_the_software_entry_flag(self):
        self.assertEqual(self.values["ram_entry_flag_pointer"], 0x20000FFC)
        self.assertEqual(self.values["ram_entry_magic"], 0x73207320)
        self.assertEqual(struct.pack("<I", self.values["ram_entry_magic"]),
                         b" s s")

    def test_the_recovery_scan_buffer_and_fallback_container(self):
        self.assertEqual(self.values["recovery_scan_buffer"], 0x18012AC8)
        self.assertEqual(self.values["backup_container"], 0x60060000)

    def test_the_entry_is_parked_in_a_reserved_vector_slot(self):
        """The write is *(VTOR) + 0x1c, not VTOR + 0x1c."""
        self.assertEqual(self.values["vtor_pointer"], 0xE000ED08)
        parked = self.result.handoff["entry_parked_in"]
        self.assertEqual(parked, "*(uint32_t *)0xe000ed08 + 0x1c")
        # 0xe000ed08 + 0x1c would be SCB SHCSR, which is not the destination.
        self.assertNotIn("0xe000ed24", str(parked))
        self.assertIn("slot 7", self.result.handoff["entry_parked_in_basis"])

    def test_a_literal_outside_the_code_image_is_refused(self):
        data, _digest = ba.bootloader_view(installed_view())
        with self.assertRaises(fi.ImageFormatError):
            ba.literal(data, len(data))


class Gates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = ba.analyze(installed_view())

    def test_there_are_exactly_four_gates(self):
        self.assertEqual(len(self.result.gates), 4)
        self.assertEqual([gate.order for gate in self.result.gates],
                         [1, 2, 3, 4])

    def test_two_gates_are_environmental_and_two_are_image_properties(self):
        kinds = [gate.kind for gate in self.result.gates]
        self.assertEqual(kinds.count("environment"), 2)
        self.assertEqual(kinds.count("image"), 2)

    def test_the_environmental_gates_are_the_two_former_unknowns(self):
        environment = [gate for gate in self.result.gates
                       if gate.kind == "environment"]
        functions = {gate.function for gate in environment}
        self.assertEqual(functions, {"FUN_000029d4", "FUN_00002a44"})

    def test_every_gate_says_what_blocks_the_boot(self):
        for gate in self.result.gates:
            self.assertTrue(gate.blocks_boot_when)
            self.assertTrue(gate.evidence)

    def test_the_recovery_gate_records_the_matched_pattern(self):
        gate, = [item for item in self.result.gates
                 if item.function == "FUN_000029d4"]
        self.assertIn("0xa0", gate.evidence)
        self.assertIn("0x100", gate.evidence)
        self.assertIn("31 consecutive", gate.evidence)
        self.assertIn("tested before the", gate.evidence)

    def test_the_flag_gate_records_that_it_is_one_shot(self):
        gate, = [item for item in self.result.gates
                 if item.function == "FUN_00002a44"]
        self.assertIn("clears the word", gate.evidence)


class Handoff(unittest.TestCase):
    """Control transfer is a copy plus a reset, not a branch."""

    @classmethod
    def setUpClass(cls):
        cls.result = ba.analyze(installed_view())

    def test_the_mechanism_is_recorded(self):
        handoff = self.result.handoff
        self.assertEqual(handoff["copy_destination"], 0x0)
        self.assertEqual(handoff["copy_length"], 0x10000)
        self.assertIn("system reset", handoff["mechanism"])
        self.assertIn("SYSRESETREQ", handoff["reset_request"])

    def test_the_routine_bytes_are_pinned(self):
        failed = [check.name for check in self.result.checks if not check.ok]
        self.assertEqual(failed, [])
        offset, runtime, length = ba.HANDOFF_SOURCE
        self.assertEqual((runtime, length), (0x18010000, 0x50))
        data, _digest = ba.bootloader_view(installed_view())
        self.assertEqual(
            hashlib.sha256(data[offset:offset + length]).hexdigest(),
            ba.HANDOFF_SHA256)

    def test_the_copy_destination_is_recorded_without_claiming_execution(self):
        """The copy is observed; what runs after the reset is not."""
        self.assertEqual(self.result.handoff["copy_destination"], 0)
        text = "\n".join(ba.report_lines(self.result))
        self.assertIn("address 0 writable is not established", text)


class Rules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = ba.analyze(installed_view())

    def test_every_rule_carries_a_confidence_and_cites_evidence(self):
        self.assertTrue(self.result.rules)
        for rule in self.result.rules:
            self.assertTrue(rule.confidence, rule.name)
            self.assertTrue(rule.evidence, rule.name)

    def test_the_copy_window_rule_is_a_policy_not_a_bootloader_rule(self):
        """No branch tests it: a longer record is simply truncated."""
        rule, = [item for item in self.result.rules
                 if item.name.startswith("POLICY:")]
        self.assertTrue(rule.confidence.startswith("policy"))
        self.assertIn("no control-flow dependency", rule.confidence)
        self.assertIn("left uncopied", rule.requirement)
        proven = [item for item in self.result.rules
                  if item.confidence == "proven"]
        self.assertEqual(len(proven), len(self.result.rules) - 1)

    def test_the_entry_pointer_rule_names_the_constant(self):
        rule, = [item for item in self.result.rules
                 if item.name == "entry pointer is fixed"]
        self.assertIn("0x60011000", rule.requirement)
        self.assertIn("cannot be relocated", rule.requirement)

    def test_the_negative_findings_cover_what_the_plan_asked_about(self):
        joined = " ".join(finding for finding, _basis, _reach
                          in self.result.negatives).lower()
        for word in ("cryptographic", "version", "rollback", "device-id",
                     "configuration"):
            self.assertIn(word, joined)

    def test_every_negative_states_how_far_it_reaches(self):
        """A constant-and-string search cannot prove an absence."""
        for finding, _basis, reach in self.result.negatives:
            self.assertTrue(reach, finding)
            self.assertTrue(finding.endswith("found")
                            or "found" in finding, finding)
        text = "\n".join(ba.report_lines(self.result))
        self.assertIn("Search results, not proofs of absence", text)
        self.assertNotIn("definitively", text)

    def test_no_rule_claims_the_image_will_boot(self):
        text = "\n".join(ba.report_lines(self.result)).lower()
        for phrase in ("will boot", "guarantees a boot", "if and only if"):
            self.assertNotIn(phrase, text)
        self.assertIn("necessary, not sufficient", text)


class Refusals(unittest.TestCase):

    def test_a_changed_entry_pointer_fails_the_gate_2_check(self):
        def patch(data, base):
            struct.pack_into("<I", data,
                             fi.FWIN_OFF + fi.FWIN_ENTRY_PTR_OFF - base,
                             0x60012000)
        result = ba.analyze(mutated(patch))
        failed = [check.name for check in result.checks if not check.ok]
        self.assertTrue(any("entry pointer equals" in name for name in failed),
                        failed)

    def test_a_truncated_image_fails_closed(self):
        view = fi.ImageView(INSTALLED.read_bytes()[:0x1000], 0x10000)
        with self.assertRaises(fi.ImageFormatError):
            ba.analyze(view)


class VerdictExecutesTheRules(unittest.TestCase):
    """The blocker this replaced: the verdict used to ignore integrity."""

    def flipped(self, logical_offset):
        raw = bytearray(INSTALLED.read_bytes())
        raw[logical_offset - 0x10000] ^= 0xFF
        return fi.ImageView(bytes(raw), 0x10000)

    def test_a_flip_inside_a_record_fails_the_verdict(self):
        view = self.flipped(0x21100)
        result = ba.analyze(view)
        failed = [check.name for check in result.checks if not check.ok]
        self.assertFalse(all(check.ok for check in result.checks))
        self.assertTrue(any("record[1] checksum" in name for name in failed),
                        failed)
        self.assertFalse(fi.validate(view).ok)

    def test_a_flip_outside_every_record_still_fails_the_word_sum(self):
        view = self.flipped(0x41000)
        result = ba.analyze(view)
        failed = [check.name for check in result.checks if not check.ok]
        self.assertTrue(any("application word-sum" in name for name in failed),
                        failed)

    def test_the_verdict_agrees_with_phase_one_validation(self):
        for offset in (0x21100, 0x35000, 0x41000):
            view = self.flipped(offset)
            mine = all(check.ok for check in ba.analyze(view).checks)
            theirs = fi.validate(view).ok
            self.assertEqual(mine, theirs, f"disagree at 0x{offset:x}")


class Output(unittest.TestCase):

    def run_cli(self, argv):
        buffer = io.StringIO()
        stdout, sys.stdout = sys.stdout, buffer
        try:
            code = ba.main(argv)
        finally:
            sys.stdout = stdout
        return code, buffer.getvalue()

    def test_the_default_run_passes(self):
        code, out = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("RESULT image_rules_ok=True", out)
        self.assertIn("RESULT_MEANING", out)
        self.assertIn("GATE 1 [environment]", out)
        self.assertIn("GATE 2 [image]", out)

    def test_json_is_deterministic(self):
        _code, first = self.run_cli(["--json"])
        _code, second = self.run_cli(["--json"])
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["gates"]), 4)
        self.assertEqual(len(payload["unresolved"]), 3)
        # The verdict must rest on the integrity rules, not just the layout.
        names = [check["name"] for check in payload["checks"]]
        self.assertTrue(any(name.startswith("integrity: ") for name in names))

    def test_a_missing_file_fails_closed_on_one_line(self):
        code, out = self.run_cli(["/nonexistent/image.bin"])
        self.assertEqual(code, 1)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("RESULT image_rules_ok=False error=", out)


class SharedConstants(unittest.TestCase):
    """The proven constants must reach the tools that gate on them."""

    def test_falchion_image_carries_them(self):
        self.assertEqual(fi.BOOT_ENTRY_CONSTANT, 0x60011000)
        self.assertEqual(fi.BOOT_HANDOFF_COPY_LENGTH, 0x10000)

    def test_validate_now_checks_them(self):
        names = {check.name for check in fi.validate(installed_view()).checks}
        self.assertIn("entry pointer equals the bootloader constant", names)
        self.assertIn(
            "policy: entry record lies inside the fixed handoff copy window",
            names)
        # The window's own bounds are two constants; checking them would be a
        # check that cannot fail on any image.
        self.assertNotIn("fixed handoff copy window inside application region",
                         names)
        # And the surviving check must not read as a bootloader requirement.
        self.assertNotIn("entry record fits inside the fixed handoff window",
                         names)

    def test_the_resolved_gates_left_the_unresolved_list(self):
        text = " ".join(fi.UNRESOLVED)
        self.assertNotIn("is not decompiled", text)
        self.assertNotIn("is not recovered", text)
        self.assertIn("ROM or first-stage", text)


class Artifacts(unittest.TestCase):
    """The note must be generated, current, and honest about what is open."""

    @classmethod
    def setUpClass(cls):
        import report_phase4 as rp
        cls.rp = rp
        cls.rendered = rp.render()

    def test_every_declared_artifact_is_rendered(self):
        self.assertEqual(sorted(self.rendered), sorted(self.rp.ARTIFACTS))

    def test_render_is_deterministic(self):
        self.assertEqual(self.rendered, self.rp.render())

    def test_the_artifacts_on_disk_are_current(self):
        stale = [name for name, text in self.rendered.items()
                 if not (self.rp.NOTES / name).exists()
                 or (self.rp.NOTES / name).read_text() != text]
        self.assertEqual(stale, [],
                         "run python3 tool/report_phase4.py to refresh these")

    def test_the_note_states_both_resolutions_and_the_remaining_gap(self):
        text = self.rendered["boot-acceptance-conditions.md"]
        self.assertIn("recovery key-combination poll", text)
        self.assertIn("`0x60011000`", text)
        self.assertIn("cannot be relocated", text)
        self.assertIn("copy and a reset, not a branch", text)
        self.assertIn("What makes address 0 writable", text)
        self.assertIn("no cryptographic constant", text)


if __name__ == "__main__":
    unittest.main()
