#!/usr/bin/env python3
"""Offline tests for Phase 5G and the Phase 5 final dependency gate.

These exist mostly to keep the GATE honest. Its whole purpose is to make
"five unanalysed service areas plus an MMIO census" impossible to mistake for
completion, so the tests enforce the rules that give it teeth: an unresolved
service must name its boundary, a may-omit service must have a proven safe idle
state, and the largest blocker must stay a blocker. No device access, no writes
outside a temporary directory.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_platform_dependencies as pd

READY = all((pd.NOTES / name).exists() for name in pd.UPSTREAM_MODELS)


class GateRules(unittest.TestCase):
    """The rules that stop this being a checklist of shrugs."""

    def test_every_unresolved_service_names_a_boundary(self):
        for service in pd.SERVICES:
            if service.classification == "unresolved":
                self.assertGreater(len(service.evidence_boundary), 60,
                                   service.key)

    def test_a_resolved_service_needs_no_boundary(self):
        """The boundary field is for what is missing, not decoration."""
        resolved = [s for s in pd.SERVICES
                    if s.classification != "unresolved"]
        self.assertTrue(resolved)
        for service in resolved:
            self.assertEqual(service.evidence_boundary, "", service.key)

    def test_may_omit_requires_a_proven_safe_idle_state(self):
        for service in pd.SERVICES:
            if service.classification == "may-omit":
                self.assertTrue(service.safe_idle_proven, service.key)

    def test_an_unproven_idle_state_forces_unresolved(self):
        """The contrapositive, which is the rule RGB actually exercises."""
        for service in pd.SERVICES:
            if not service.safe_idle_proven:
                self.assertNotEqual(service.classification, "may-omit",
                                    service.key)

    def test_rgb_is_the_service_that_rule_catches(self):
        rgb, = [s for s in pd.SERVICES if s.key == "rgb"]
        self.assertEqual(rgb.classification, "unresolved")
        self.assertFalse(rgb.safe_idle_proven)
        self.assertIn("polarity", rgb.evidence_boundary)

    def test_the_hall_acquisition_is_a_blocker(self):
        hall, = [s for s in pd.SERVICES if s.key == "hall_acquisition"]
        self.assertEqual(hall.classification, "unresolved")
        self.assertIn("BLOCKER", hall.rationale.upper())

    def test_every_service_cites_evidence(self):
        for service in pd.SERVICES:
            self.assertTrue(service.evidence, service.key)
            for citation in service.evidence:
                self.assertGreater(len(citation), 15, service.key)

    def test_every_class_is_populated(self):
        summary = pd.by_classification()
        for name in pd.CLASSES:
            self.assertTrue(summary[name], name)

    def test_the_classification_is_a_partition(self):
        keys = [service.key for service in pd.SERVICES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(sum(len(v) for v in pd.by_classification().values()),
                         len(pd.SERVICES))

    def test_blockers_are_exactly_the_unresolved_services(self):
        self.assertEqual({s.key for s in pd.blockers()},
                         {s.key for s in pd.SERVICES
                          if s.classification == "unresolved"})


class FiveGFindings(unittest.TestCase):

    def test_all_four_areas_are_covered(self):
        self.assertEqual({item.area for item in pd.FINDINGS},
                         {"clocks", "watchdogs", "faults", "multicore"})

    def test_no_frequency_is_claimed_anywhere(self):
        text = "\n".join(pd.report_lines()).lower()
        import re
        for unit in ("hz", "mhz", "khz"):
            self.assertIsNone(re.search(rf"\b\d+\s*{unit}\b", text), unit)
        finding, = [f for f in pd.FINDINGS if f.key == "no_frequency_claimed"]
        self.assertEqual(finding.confidence, "unresolved")

    def test_the_watchdog_claim_is_inference_not_identification(self):
        finding, = [f for f in pd.FINDINGS if f.key == "watchdog_disabled"]
        self.assertEqual(finding.confidence, "strongly-inferred")
        self.assertIn("not identification", finding.kind_basis)

    def test_the_model_names_all_three_watchdog_access_paths(self):
        """Log 114's correction. The original error was trusting a
        single-writer census, so the model must name every path — including
        the two the census cannot see."""
        paths = pd.to_dict()["watchdog"]["access_paths"]
        self.assertEqual(len(paths), 3)
        self.assertEqual({item["kind"] for item in paths},
                         {"reset-path disable", "periodic feed",
                          "NMI acknowledge and escalate"})

    def test_two_access_paths_are_recorded_census_invisible(self):
        paths = pd.to_dict()["watchdog"]["access_paths"]
        invisible = [item for item in paths if not item["census_visible"]]
        self.assertEqual(len(invisible), 2)
        for item in invisible:
            self.assertIn(item["kind"],
                          ("periodic feed", "NMI acknowledge and escalate"))

    def test_the_blocks_are_recorded_as_fed(self):
        """`nothing feeds them anywhere` was the falsified claim."""
        self.assertTrue(pd.to_dict()["watchdog"]["fed_anywhere"])

    def test_the_withdrawn_claims_are_kept_on_the_record(self):
        withdrawn = pd.to_dict()["watchdog"]["withdrawn_claims"]
        self.assertEqual(len(withdrawn), 2)
        joined = " ".join(withdrawn)
        self.assertIn("nothing feeds them", joined)
        self.assertIn("exactly one function", joined)

    def test_the_falsified_phrases_survive_only_as_withdrawals(self):
        """The phrases stay on the record — that is the immutable-log habit —
        but only next to the word WITHDRAWN. A bare restatement is the
        regression this catches."""
        for item in pd.FINDINGS:
            for phrase in ("nothing feeds them",
                           "exactly one function in either image touches"):
                if phrase in item.kind_basis.lower():
                    self.assertIn("WITHDRAWN", item.kind_basis,
                                  f"{item.key} restates {phrase!r} without "
                                  "marking it withdrawn")
                self.assertNotIn(phrase, item.statement.lower(), item.key)

    def test_both_falsified_phrases_are_actually_withdrawn_somewhere(self):
        """And the withdrawal must exist, or the test above passes vacuously."""
        basis = " ".join(item.kind_basis for item in pd.FINDINGS)
        self.assertIn("WITHDRAWN", basis)
        self.assertEqual(basis.count("WITHDRAWN"), 2)

    def test_the_second_block_is_recorded_untouched_after_reset(self):
        self.assertFalse(
            pd.to_dict()["watchdog"]["second_block_touched_after_reset"])
        finding, = [f for f in pd.FINDINGS
                    if f.key == "watchdog_second_block_untouched"]
        self.assertEqual(finding.confidence, "observed")

    def test_the_watchdog_service_cites_the_correction(self):
        service, = [s for s in pd.SERVICES if s.key == "watchdogs"]
        self.assertEqual(service.classification, "must-neutralize")
        self.assertIn("LOG 114", service.rationale.upper())
        self.assertEqual(len(service.evidence), 3)

    def test_the_prototype_watchdog_status_is_no_longer_just_a_disable(self):
        status = pd.to_dict()["prototype"]["status"]["watchdog policy"]
        self.assertIn("NOT just a disable", status)

    def test_the_usbd_wdt_lead_is_recorded_as_failing(self):
        finding, = [f for f in pd.FINDINGS
                    if f.key == "usbd_wdt_is_not_a_watchdog_feeder"]
        self.assertEqual(finding.confidence, "observed")
        self.assertIn("does not pan out", finding.kind_basis)

    def test_the_vector_extent_stays_inferred(self):
        finding, = [f for f in pd.FINDINGS if f.key == "vector_extent"]
        self.assertEqual(finding.confidence, "strongly-inferred")
        self.assertIn("DELIBERATELY", finding.kind_basis)

    def test_no_mmio_block_is_named(self):
        text = json.dumps(pd.to_dict())
        for phrase in ("is the watchdog", "is the PLL", "clock controller at",
                       "is the ADC"):
            self.assertNotIn(phrase, text)

    def test_second_context_ownership_stays_unresolved(self):
        """The 0x18038000 image is a CANDIDATE owner of the Hall acquisition.
        A candidate must not be promoted to a finding."""
        finding, = [f for f in pd.FINDINGS
                    if f.key == "second_context_ownership"]
        self.assertEqual(finding.confidence, "unresolved")
        self.assertIn("candidate is not a finding", finding.kind_basis)

    def test_every_finding_names_its_source(self):
        for item in pd.FINDINGS:
            self.assertIn(item.verified_against, pd.SOURCES, item.key)
            self.assertIn(item.confidence, pd.CONFIDENCES, item.key)
            self.assertGreater(len(item.kind_basis), 40, item.key)

    def test_the_multicore_constants_are_self_consistent(self):
        multicore = pd.to_dict()["multicore"]
        self.assertEqual(multicore["second_image_reset_vector"] & ~1,
                         pd.SECOND_IMAGE_DEST + 0x1C0)
        self.assertEqual(multicore["handshake_token"], 0x12345678)


class Prototype(unittest.TestCase):

    def test_every_plan_requirement_has_a_status(self):
        payload = pd.to_dict()["prototype"]
        self.assertEqual(len(payload["minimum_from_the_plan"]),
                         len(payload["status"]))

    def test_the_hall_requirement_is_reported_blocked(self):
        status = pd.to_dict()["prototype"]["status"]
        self.assertIn("BLOCKED", status["Hall acquisition"])

    def test_the_clock_requirement_reports_its_gap(self):
        status = pd.to_dict()["prototype"]["status"]
        self.assertIn("UNRESOLVED", status["reset/clock/RAM"])

    def test_the_recovered_requirements_do_not_claim_blockage(self):
        status = pd.to_dict()["prototype"]["status"]
        for key in ("key-state generation", "USB keyboard-IN"):
            self.assertNotIn("BLOCK", status[key].upper())


@unittest.skipUnless(READY, "upstream 5B-5F models not present")
class Upstream(unittest.TestCase):

    def test_all_five_models_load(self):
        self.assertEqual(sorted(pd.load_upstream()),
                         sorted(pd.UPSTREAM_MODELS))

    def test_a_missing_upstream_model_fails_closed(self):
        original = pd.NOTES
        with tempfile.TemporaryDirectory() as directory:
            pd.NOTES = Path(directory)
            try:
                with self.assertRaises(pd.PlatformError):
                    pd.load_upstream()
            finally:
                pd.NOTES = original

    def test_the_gate_agrees_with_the_upstream_rgb_model(self):
        """RGB is unresolved HERE because the upstream model says its
        hardware idle state is unprovable. The two must not drift."""
        upstream = pd.load_upstream()["rgb-lamparray.json"]
        self.assertFalse(
            upstream["safe_omission"]["hardware_idle_state_provable"])
        rgb, = [s for s in pd.SERVICES if s.key == "rgb"]
        self.assertEqual(rgb.classification, "unresolved")

    def test_the_gate_agrees_with_the_upstream_hall_model(self):
        upstream = pd.load_upstream()["hall-actuation.json"]
        self.assertEqual(upstream["pipeline"]["acquisition"], "unresolved")
        hall, = [s for s in pd.SERVICES if s.key == "hall_acquisition"]
        self.assertEqual(hall.classification, "unresolved")

    def test_the_gate_agrees_with_the_upstream_persistence_model(self):
        upstream = pd.load_upstream()["nonvolatile-writes.json"]
        self.assertEqual(upstream["exit_gate"]["branch"], "omit-all-writes")
        persistence, = [s for s in pd.SERVICES if s.key == "persistence"]
        self.assertEqual(persistence.classification, "may-omit")


@unittest.skipUnless(READY, "upstream 5B-5F models not present")
class Artifacts(unittest.TestCase):

    def test_every_check_passes(self):
        for item in pd.verify():
            self.assertTrue(item["ok"], item["name"])

    def test_json_is_deterministic(self):
        self.assertEqual(pd.bodies(), pd.bodies())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in pd.bodies().items()
                 if not (pd.NOTES / name).exists()
                 or (pd.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/map_platform_dependencies.py --write")

    def test_the_report_refuses_the_reachability_shortcut(self):
        text = "\n".join(pd.report_lines())
        self.assertIn("solely because of graph reachability", text)

    def test_the_report_says_unresolved_is_not_permission_to_omit(self):
        text = "\n".join(pd.report_lines())
        self.assertIn("not permission to omit", text)


if __name__ == "__main__":
    unittest.main()
