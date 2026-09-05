#!/usr/bin/env python3
"""Offline tests for the function-pointer table detector.

Synthetic images for the detection rules, the preserved slices for the real
numbers. No device access, no writes.
"""
import io
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import find_pointer_tables as fpt

INVENTORIES = Path(fpt.INVENTORIES)
READY = (INVENTORIES / "installed_b.txt").exists()


def image(words, base=0x18000000, pad_to=0x100):
    """Pack `words`, padded so the targets they point at are inside the image."""
    padded = list(words) + [0] * max(0, pad_to // 4 - len(words))
    return struct.pack(f"<{len(padded)}I", *padded)


class DetectionRules(unittest.TestCase):
    """A lone plausible word is not a table; a run at a constant stride is."""

    def survey(self, words, known=frozenset(), base=0x18000000):
        return fpt.survey("app", "synthetic.bin", base, image(words, base), known)

    def test_the_fixture_is_large_enough_for_its_targets(self):
        """Guards the fixture itself: a short image silently drops targets."""
        data = image([0x18000011])
        self.assertGreaterEqual(len(data), 0x100)

    def test_a_run_of_three_is_a_table(self):
        result = self.survey([0x18000011, 0x18000021, 0x18000031, 0, 0, 0])
        table, = result.tables
        self.assertEqual((table.location, table.stride, table.count),
                         (0x18000000, 4, 3))
        self.assertEqual([target for _address, target in table.entries],
                         [0x18000010, 0x18000020, 0x18000030])

    def test_a_run_of_two_is_not_a_table(self):
        result = self.survey([0x18000011, 0x18000021, 0, 0, 0, 0])
        self.assertEqual(result.tables, ())
        self.assertEqual(len(result.loose_candidates), 2)

    def test_a_strided_structure_array_is_found(self):
        words = []
        for index in range(4):
            words += [0x18000011 + index * 0x10, 0, 0, 0]
        result = self.survey(words)
        table, = result.tables
        self.assertEqual((table.stride, table.count), (16, 4))

    def test_a_word_without_the_thumb_bit_is_not_a_candidate(self):
        result = self.survey([0x18000010, 0x18000020, 0x18000030, 0, 0, 0])
        self.assertEqual(result.tables, ())
        self.assertEqual(result.loose_candidates, ())

    def test_a_target_outside_the_image_is_not_a_candidate(self):
        result = self.survey([0x19000011, 0x19000021, 0x19000031, 0, 0, 0])
        self.assertEqual(result.tables, ())

    def test_every_accepted_target_is_even(self):
        """Clearing bit 0 always yields an even address, so there is no odd
        case to reject — the detector must not pretend otherwise."""
        found = fpt.candidates(image([0x18000013, 0x18000015, 0x18000019]),
                               0x18000000, (), 0x18000000)
        self.assertEqual(len(found), 3)
        for target in found.values():
            self.assertEqual(target % 2, 0)
        self.assertEqual(sorted(found.values()),
                         [0x18000012, 0x18000014, 0x18000018])

    def test_the_code_floor_rejects_low_targets(self):
        """Without it, structure words carrying bit 0 look like pointers."""
        words = [0x00000005, 0x00000009, 0x0000000d]
        without = fpt.candidates(image(words, 0x0), 0x0, (), 0x0)
        self.assertEqual(len(without), 3)
        with_floor = fpt.candidates(image(words, 0x0), 0x0, (), 0x140)
        self.assertEqual(with_floor, {})

    def test_an_excluded_span_is_not_scanned(self):
        words = [0x00000141, 0x00000145, 0x00000149]
        data = image(words, 0x0, pad_to=0x200)
        self.assertEqual(len(fpt.candidates(data, 0x0, (), 0x140)), 3)
        self.assertEqual(fpt.candidates(data, 0x0, ((0x0, 0x140),), 0x140), {})

    def test_known_and_new_targets_are_separated(self):
        result = self.survey([0x18000011, 0x18000021, 0x18000031, 0, 0, 0],
                             known={0x18000010})
        self.assertEqual(result.known_targets, (0x18000010,))
        self.assertEqual(result.new_targets, (0x18000020, 0x18000030))

    def test_seed_arguments_name_each_new_target(self):
        result = self.survey([0x18000011, 0x18000021, 0x18000031, 0, 0, 0])
        args = fpt.seed_arguments(result)
        self.assertEqual(len(args), 3)
        for argument in args:
            name, address = argument.split("=")
            self.assertTrue(name.startswith("PtrTarget_"))
            self.assertTrue(address.startswith("0x"))


@unittest.skipUnless(READY, "run the Ghidra inventory step first")
class RealImages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.surveys = fpt.build()
        cls.entry, cls.app = cls.surveys[0], cls.surveys[1]

    def test_the_application_has_three_dense_dispatch_tables(self):
        strides = [table.stride for table in self.app.tables]
        counts = [table.count for table in self.app.tables]
        self.assertEqual(strides, [4, 4, 4])
        self.assertEqual(counts, [26, 6, 12])
        self.assertEqual([table.location for table in self.app.tables],
                         [0x18016D44, 0x18017D08, 0x18018CE8])

    def test_most_application_table_targets_were_already_functions(self):
        """Which is why these tables are real and not a byte coincidence."""
        self.assertGreaterEqual(len(self.app.known_targets), 20)
        self.assertGreater(len(self.app.known_targets),
                           len(self.app.new_targets) // 2)

    def test_the_entry_image_has_a_shared_handler_struct_array(self):
        table, = [item for item in self.entry.tables
                  if item.location == 0x1404]
        self.assertEqual((table.stride, table.count), (16, 8))
        targets = {target for _address, target in table.entries}
        self.assertEqual(targets, {0x00000A0C},
                         "all eight slots carry the same handler")

    def test_the_vendor_tables_sit_at_the_measured_shift(self):
        vendor_app = fpt.build(fpt.VENDOR, 0x0, "vendor")[1]
        installed = [table.location for table in self.app.tables]
        vendor = [table.location for table in vendor_app.tables]
        self.assertEqual([address - 0x2C for address in installed], vendor,
                         "the tables move by exactly the relocation Phase 3 "
                         "measured, which corroborates both")

    def test_the_vector_table_is_excluded_from_the_entry_survey(self):
        for table in self.entry.tables:
            self.assertGreaterEqual(table.location, 0x140)
        for address, _target in self.entry.loose_candidates:
            self.assertGreaterEqual(address, 0x140)

    def test_json_is_deterministic(self):
        first = json.dumps(fpt.to_dict(fpt.build()), sort_keys=True)
        second = json.dumps(fpt.to_dict(fpt.build()), sort_keys=True)
        self.assertEqual(first, second)

    def test_the_flash_surveys_are_unchanged_by_the_region_extension(self):
        """Regression pin: surveying the reconstructed region must not perturb
        a single number in the two flash surveys it was added alongside."""
        self.assertEqual(
            [(item.program, len(item.tables), len(item.known_targets),
              len(item.new_targets), len(item.loose_candidates),
              tuple(table.location for table in item.tables))
             for item in (self.entry, self.app)],
            [("entry", 2, 3, 1, 15, (0x1404, 0x5680)),
             ("app", 3, 44, 0, 9, (0x18016D44, 0x18017D08, 0x18018CE8))])

    def test_the_reconstructed_region_holds_no_table(self):
        """5A's rule applied honestly: the region has isolated pointers, not a
        run of three at a constant stride, so it contributes no table."""
        region, = [item for item in self.surveys if item.program == "ram"]
        self.assertEqual(region.tables, ())
        self.assertEqual(region.base, 0x1801E380)
        targets = {target for _address, target in region.loose_candidates}
        self.assertTrue({0x18018AFC, 0x18018AF0, 0x18018A28} <= targets)

    def test_the_region_survey_accepts_targets_below_its_own_base(self):
        """Without CODE_CEIL the region points only at code beneath itself, so
        every candidate would be rejected and the survey would be empty."""
        self.assertEqual(fpt.CODE_CEIL["ram"], 0x1801EE84)
        self.assertLess(fpt.CODE_FLOOR["ram"], 0x1801E380)

    def test_the_report_states_what_a_target_is_not(self):
        text = "\n".join(fpt.report_lines((self.entry, self.app)))
        self.assertIn("candidate, not a proven function", text)
        self.assertIn("still\ncannot appear here.".replace("\n", " "), text)


@unittest.skipUnless(READY, "run the Ghidra inventory step first")
class SeededReachability(unittest.TestCase):
    """5A's actual deliverable: the tables must move the reachability number."""

    def test_the_table_targets_are_reachability_roots(self):
        import map_hardware_interfaces as mh
        hardware = mh.build_map()
        app, = [program for program in hardware.programs
                if "application" in program.name]
        table_roots = {label for label, _entry in app.roots
                       if label.startswith("table@")}
        self.assertEqual(table_roots, {"table@0x18016d44", "table@0x18017d08",
                                       "table@0x18018ce8"})

    def test_reachability_is_far_better_than_before_seeding(self):
        import map_hardware_interfaces as mh
        hardware = mh.build_map()
        app, = [program for program in hardware.programs
                if "application" in program.name]
        # Before 5A this was 51 of 530. The count must have risen materially,
        # and it must still be short of the total: 5A is progress, not closure.
        self.assertGreater(len(app.contexts), 100)
        self.assertLess(len(app.contexts), app.functions)


class Cli(unittest.TestCase):

    def run_main(self, argv):
        buffer = io.StringIO()
        stdout, sys.stdout = sys.stdout, buffer
        try:
            code = fpt.main(argv)
        finally:
            sys.stdout = stdout
        return code, buffer.getvalue()

    @unittest.skipUnless(READY, "run the Ghidra inventory step first")
    def test_seed_args_mode_prints_only_pairs(self):
        code, out = self.run_main(["--seed-args", "app"])
        self.assertEqual(code, 0)
        for token in out.split():
            self.assertIn("=0x", token)

    @unittest.skipUnless(READY, "run the Ghidra inventory step first")
    def test_json_mode_is_parseable(self):
        code, out = self.run_main(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["min_entries"], 3)
        self.assertEqual(len(payload["surveys"]), 3)


if __name__ == "__main__":
    unittest.main()
