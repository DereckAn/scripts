#!/usr/bin/env python3
"""Fixture-based tests for the Armoury Crate profile diff.

Every test drives the real `notes/ac-profile3-decoded.json` and mutates ONE
setting, then requires the diff to name exactly that path. Finding 4's whole
point was that a diff can look like it works while comparing a fraction of the
model, so the categories are enumerated here and each one has to produce a
change of its own.

No device access. The reference profile is opened read-only and its sha256 is
asserted unchanged at the end of the run.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import profile_diff as pd

REFERENCE = Path(pd.REFERENCE)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def set_path(config, path, value):
    """Set a dotted/indexed flattened path, in place."""
    target, key = _walk(config, path)
    target[key] = value


def _walk(config, path):
    tokens = []
    for part in path.lstrip(".").split("."):
        name, _, rest = part.partition("[")
        tokens.append(name)
        while rest:
            index, _, rest = rest.partition("]")
            tokens.append(int(index))
            rest = rest.lstrip("[")
    node = config
    for token in tokens[:-1]:
        node = node[token]
    return node, tokens[-1]


def snapshot(config, name="fp_3_config_024080600167.xml"):
    return {
        "capturedUtc": "2026-09-20T00:00:00.0000000Z",
        "profiles": [{
            "config": config,
            "file": name,
            "mtime": "2026-09-19T00:00:00.0000000Z",
            "path": "C:\\ProgramData\\ASUS\\...\\" + name,
            "sha256": "0" * 64,
        }],
        "tool": "snap-config.ps1",
    }


class Reference(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.before = sha256(REFERENCE)
        cls.config = pd.load(REFERENCE)

    @classmethod
    def tearDownClass(cls):
        assert sha256(REFERENCE) == cls.before, "the reference was modified"

    def test_the_reference_decodes(self):
        self.assertIn("button", self.config)
        self.assertIn("performance", self.config)

    def test_the_model_is_not_just_keyboard_buttons(self):
        """The bug in one assertion: the old comparison saw only this subtree."""
        paths = pd.flatten(self.config)
        keyboard = [p for p in paths if p.startswith(".button.keyboardButton")]
        self.assertGreater(len(paths), len(keyboard))
        self.assertGreater(len(paths) - len(keyboard), 100,
                           "the settings the old diff could not see")

    def test_every_required_category_exists_in_the_real_profile(self):
        coverage = pd.category_coverage(self.config)
        self.assertEqual([name for name, count in coverage.items()
                          if count == 0], [])
        self.assertEqual(set(coverage), set(pd.REQUIRED_CATEGORIES))


class MutationDetection(unittest.TestCase):
    """One controlled mutation per required category, each must be detected."""

    @classmethod
    def setUpClass(cls):
        cls.before = sha256(REFERENCE)
        cls.config = pd.load(REFERENCE)

    @classmethod
    def tearDownClass(cls):
        assert sha256(REFERENCE) == cls.before, "the reference was modified"

    def mutate(self, path, value):
        after = copy.deepcopy(self.config)
        set_path(after, path, value)
        return pd.diff(self.config, after)

    def assertDetects(self, path, value):
        changes = self.mutate(path, value)
        self.assertEqual([item[0] for item in changes], [path],
                         f"{path} did not produce exactly one change")
        self.assertEqual(changes[0][1], pd.CHANGED)
        self.assertEqual(changes[0][3], value)
        return changes

    def first_key(self):
        return sorted(self.config["button"]["keyboardButton"])[0]

    def test_all_key_actuation(self):
        self.assertDetects(".button.analogTrigger.actuation", 25)

    def test_rapid_trigger_separate_mode(self):
        self.assertDetects(".button.analogTrigger.rapidTriggerSeparateMode", 1)

    def test_rapid_trigger_continue_status(self):
        self.assertDetects(".button.analogTrigger.rapidTriggerContinueStatue", 1)

    def test_all_key_rapid_trigger_off_to_on(self):
        self.assertDetects(".button.analogTrigger.rapidTrigger", 5)

    def test_rapid_trigger_press_distance(self):
        self.assertDetects(".button.analogTrigger.rapidTriggerPress", 7)

    def test_rapid_trigger_release_distance(self):
        self.assertDetects(".button.analogTrigger.rapidTriggerRelease", 9)

    def test_per_key_rapid_trigger_override(self):
        self.assertDetects(".button.analogTrigger.preKeyRapidTriggerList[0]",
                           "1794")

    def test_a_shorter_per_key_rapid_trigger_list_is_a_removal(self):
        after = copy.deepcopy(self.config)
        after["button"]["analogTrigger"]["preKeyRapidTriggerList"] = \
            after["button"]["analogTrigger"]["preKeyRapidTriggerList"][:-1]
        changes = pd.diff(self.config, after)
        self.assertTrue(changes)
        self.assertEqual({item[1] for item in changes}, {pd.REMOVED},
                         "a path present before and absent after is removed")
        self.assertIn("per-key rapid trigger list",
                      pd.categories_touched(changes))

    def test_per_key_actuation_override(self):
        key = self.first_key()
        self.assertDetects(
            f".button.keyboardButton.{key}.button.normal.actuation", 33)

    def test_per_key_trigger_type(self):
        key = self.first_key()
        self.assertDetects(
            f".button.keyboardButton.{key}.button.trigger_type", 2)

    def test_polling_rate(self):
        self.assertDetects(".performance.pollingRate", "0")

    def test_speed_tap(self):
        self.assertDetects(".button.speedTap[0].binding", "0")

    def test_dead_zone(self):
        self.assertDetects(".button.deadZone.deadZoneTop", 4)
        self.assertDetects(".button.deadZone.deadZoneBottom", 4)
        self.assertDetects(".button.deadZone.deadZone", 4)

    def test_lighting(self):
        self.assertDetects(".lighting.keyboard.brightness", "50")
        self.assertDetects(".lighting.keyboard.effectID", "2")

    def test_lever(self):
        self.assertDetects(".lever.currentFunctionId", "1")

    def test_every_required_category_is_individually_detectable(self):
        """The whole of finding 4's list, in one sweep over the real profile.

        For each category, mutate the first flattened path under it and
        require the diff to report that category.
        """
        paths = sorted(pd.flatten(self.config))
        for name, prefix in sorted(pd.REQUIRED_CATEGORIES.items()):
            target = next(p for p in paths if pd.matches(p, prefix))
            after = copy.deepcopy(self.config)
            current = pd.flatten(self.config)[target]
            set_path(after, target,
                     "__mutated__" if isinstance(current, str) else 4242)
            changes = pd.diff(self.config, after)
            self.assertEqual([item[0] for item in changes], [target], name)
            self.assertIn(name, pd.categories_touched(changes), name)

    def test_an_unchanged_profile_produces_no_change_at_all(self):
        self.assertEqual(pd.diff(self.config, copy.deepcopy(self.config)), [])

    def test_no_change_means_the_whole_model_is_equal(self):
        lines = pd.report_lines(snapshot(self.config),
                                snapshot(copy.deepcopy(self.config)))
        self.assertIn("NO CHANGE", "\n".join(lines))
        self.assertIn("every compared path in every profile is equal",
                      "\n".join(lines))

    def test_the_old_keyboard_button_only_comparison_would_have_missed_these(self):
        """The regression itself: prove the miss, so it cannot come back."""
        missed = [".button.analogTrigger.rapidTrigger",
                  ".button.analogTrigger.rapidTriggerPress",
                  ".performance.pollingRate",
                  ".button.deadZone.deadZone",
                  ".lighting.keyboard.brightness",
                  ".lever.currentFunctionId",
                  ".button.speedTap[0].binding"]
        for path in missed:
            changes = self.mutate(path, "__mutated__")
            self.assertTrue(changes, path)
            self.assertFalse(
                any(item[0].startswith(".button.keyboardButton")
                    for item in changes),
                f"{path} is outside keyboardButton, which is why the old "
                "comparison reported NO CHANGE for it")


class Snapshots(unittest.TestCase):

    def setUp(self):
        self.config = pd.load(REFERENCE)

    def test_a_snapshot_names_the_file_that_changed(self):
        after = copy.deepcopy(self.config)
        set_path(after, ".performance.pollingRate", "0")
        report = pd.snapshot_diff(
            snapshot(self.config, "fp_1_config_x.xml"),
            snapshot(after, "fp_1_config_x.xml"))
        self.assertEqual(list(report), ["fp_1_config_x.xml"])
        self.assertEqual([item[0] for item in report["fp_1_config_x.xml"]],
                         [".performance.pollingRate"])

    def test_two_profiles_are_compared_independently(self):
        after = copy.deepcopy(self.config)
        set_path(after, ".performance.pollingRate", "0")
        old = snapshot(self.config, "fp_1_config_x.xml")
        new = snapshot(self.config, "fp_1_config_x.xml")
        for payload, config in ((old, self.config), (new, after)):
            payload["profiles"].append({
                "config": config, "file": "fp_2_config_x.xml",
                "mtime": "2026-09-19T00:00:00Z", "path": "p",
                "sha256": "1" * 64})
        report = pd.snapshot_diff(old, new)
        self.assertEqual(list(report), ["fp_2_config_x.xml"])

    def test_a_longer_list_is_an_addition(self):
        after = copy.deepcopy(self.config)
        after["button"]["analogTrigger"]["preKeyRapidTriggerList"].append("99")
        changes = pd.diff(self.config, after)
        self.assertEqual([item[1] for item in changes], [pd.ADDED])
        self.assertEqual(changes[0][3], "99")

    def payload(self, *names):
        return {"capturedUtc": "2026-09-20T00:00:00Z", "tool": "snap-config.ps1",
                "profiles": [{"config": self.config, "file": name,
                              "mtime": "m", "path": "p", "sha256": "2" * 64}
                             for name in names]}

    def test_an_added_profile_file_is_reported_as_added(self):
        report = pd.snapshot_diff(self.payload("fp_1.xml"),
                                  self.payload("fp_1.xml", "fp_5.xml"))
        self.assertEqual(list(report), ["fp_5.xml"])
        self.assertEqual(report["fp_5.xml"],
                         [("", pd.ADDED, None, "fp_5.xml")])

    def test_a_removed_profile_file_is_reported_as_removed(self):
        report = pd.snapshot_diff(self.payload("fp_1.xml", "fp_5.xml"),
                                  self.payload("fp_1.xml"))
        self.assertEqual(list(report), ["fp_5.xml"])
        self.assertEqual(report["fp_5.xml"],
                         [("", pd.REMOVED, "fp_5.xml", None)])

    def test_a_changed_file_reports_the_complete_tuple(self):
        after = copy.deepcopy(self.config)
        set_path(after, ".performance.pollingRate", "0")
        old = self.payload("fp_1.xml")
        new = copy.deepcopy(old)
        new["profiles"][0]["config"] = after
        report = pd.snapshot_diff(old, new)
        self.assertEqual(report["fp_1.xml"],
                         [(".performance.pollingRate", pd.CHANGED, "3", "0")])

    def test_an_unchanged_file_is_absent_from_the_report(self):
        report = pd.snapshot_diff(self.payload("fp_1.xml", "fp_5.xml"),
                                  self.payload("fp_1.xml", "fp_5.xml"))
        self.assertEqual(report, {})

    def test_all_four_file_outcomes_in_one_comparison(self):
        after = copy.deepcopy(self.config)
        set_path(after, ".lighting.keyboard.brightness", "10")
        old = self.payload("same.xml", "changed.xml", "gone.xml")
        new = self.payload("same.xml", "changed.xml", "new.xml")
        new["profiles"][1]["config"] = after
        report = pd.snapshot_diff(old, new)
        self.assertEqual(sorted(report), ["changed.xml", "gone.xml", "new.xml"])
        self.assertEqual(report["new.xml"],
                         [("", pd.ADDED, None, "new.xml")])
        self.assertEqual(report["gone.xml"],
                         [("", pd.REMOVED, "gone.xml", None)])
        self.assertEqual(report["changed.xml"],
                         [(".lighting.keyboard.brightness", pd.CHANGED,
                           "100", "10")])
        self.assertNotIn("same.xml", report)

    def test_the_powershell_report_uses_the_same_words(self):
        text = pd.POWERSHELL.read_text()
        self.assertIn("added (new profile file)", text)
        self.assertIn("removed (profile file gone)", text)

    def test_a_snapshot_missing_its_provenance_is_refused(self):
        bad = snapshot(self.config)
        del bad["profiles"][0]["sha256"]
        with self.assertRaises(pd.ProfileError):
            pd.profile_map(bad)

    def test_a_legacy_snapshot_without_profiles_is_refused(self):
        with self.assertRaises(pd.ProfileError):
            pd.profile_map(self.config)

    def test_the_required_provenance_fields_are_all_demanded(self):
        for key in pd.PROFILE_KEYS:
            bad = snapshot(self.config)
            del bad["profiles"][0][key]
            self.assertTrue(pd.check_snapshot(bad), key)


class ScalarTypes(unittest.TestCase):
    """JSON types must survive the flattening, or 1 and "1" compare equal."""

    def change(self, before, after):
        return pd.diff({"k": before}, {"k": after})

    def test_a_number_and_the_same_digits_as_a_string_differ(self):
        self.assertEqual(self.change(1, "1"), [(".k", pd.CHANGED, 1, "1")])
        self.assertEqual(self.change("1", 1), [(".k", pd.CHANGED, "1", 1)])

    def test_a_boolean_and_the_word_as_a_string_differ(self):
        self.assertEqual(self.change(True, "true"),
                         [(".k", pd.CHANGED, True, "true")])
        self.assertEqual(self.change(False, "false"),
                         [(".k", pd.CHANGED, False, "false")])

    def test_a_boolean_and_a_number_differ(self):
        """Python's own trap: `True == 1`, so a raw comparison sees nothing."""
        self.assertEqual(True, 1)
        self.assertEqual(self.change(True, 1), [(".k", pd.CHANGED, True, 1)])

    def test_null_and_the_word_as_a_string_differ(self):
        self.assertEqual(self.change(None, "null"),
                         [(".k", pd.CHANGED, None, "null")])

    def test_a_numeric_change_is_still_a_change(self):
        self.assertEqual(self.change(10, 25), [(".k", pd.CHANGED, 10, 25)])

    def test_an_integral_float_and_an_integer_are_the_same_number(self):
        """JSON has one number type; 10 and 10.0 are the same value."""
        self.assertEqual(self.change(10, 10.0), [])
        self.assertEqual(pd.canonical(10), pd.canonical(10.0))

    def test_a_non_integral_number_keeps_its_fraction(self):
        self.assertEqual(pd.canonical(1.5), "num:1.5")
        self.assertEqual(self.change(1.5, 1.25),
                         [(".k", pd.CHANGED, 1.5, 1.25)])

    def test_an_identical_value_of_the_same_type_is_no_change(self):
        for value in (1, "1", True, None, 1.5, "text"):
            self.assertEqual(self.change(value, value), [], repr(value))

    def test_an_array_that_grows_is_an_addition(self):
        changes = pd.diff({"a": [1, 2]}, {"a": [1, 2, 3]})
        self.assertEqual(changes, [(".a[2]", pd.ADDED, None, 3)])

    def test_an_array_that_shrinks_is_a_removal(self):
        changes = pd.diff({"a": [1, 2, 3]}, {"a": [1, 2]})
        self.assertEqual(changes, [(".a[2]", pd.REMOVED, 3, None)])

    def test_an_object_gaining_a_key_is_an_addition(self):
        changes = pd.diff({"a": {"x": 1}}, {"a": {"x": 1, "y": 2}})
        self.assertEqual(changes, [(".a.y", pd.ADDED, None, 2)])

    def test_an_object_losing_a_key_is_a_removal(self):
        changes = pd.diff({"a": {"x": 1, "y": 2}}, {"a": {"x": 1}})
        self.assertEqual(changes, [(".a.y", pd.REMOVED, 2, None)])

    def test_a_scalar_becoming_an_object_changes_shape(self):
        changes = pd.diff({"a": 1}, {"a": {"x": 1}})
        self.assertEqual(sorted(change[:2] for change in changes),
                         [(".a", pd.REMOVED), (".a.x", pd.ADDED)])

    def test_key_order_does_not_matter_but_array_order_does(self):
        self.assertEqual(pd.diff({"a": 1, "b": 2}, {"b": 2, "a": 1}), [])
        self.assertEqual(len(pd.diff({"a": [1, 2]}, {"a": [2, 1]})), 2)

    def test_the_flattened_paths_are_deterministic(self):
        payload = {"b": 1, "a": {"z": 1, "y": [1, 2]}}
        self.assertEqual(list(pd.flatten(payload)),
                         [".a.y[0]", ".a.y[1]", ".a.z", ".b"])


class PowerShellStaysInSync(unittest.TestCase):
    """SCOPE, stated plainly: PowerShell is not executed here.

    These tests prove that `tools/snap-config.ps1` still *contains* the
    contract this module specifies — the snapshot fields, the recursive
    flatten, the type-tagged canonical form, no return to the
    keyboardButton-only comparison. They do NOT execute the PowerShell
    algorithm and therefore do NOT prove that the two implementations agree on
    any input. That equivalence is an open, Windows-only validation item,
    recorded in tools/README.md and in the capture plan.
    """

    def test_no_drift(self):
        self.assertEqual(pd.powershell_drift(), [])

    def test_the_guard_catches_a_return_to_the_keyboard_button_only_diff(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "snap-config.ps1"
            target.write_text(pd.POWERSHELL.read_text()
                              + "\nforeach ($p in $cfg.button."
                                "keyboardButton.PSObject.Properties) { }\n")
            self.assertIn("snap-config.ps1 still flattens only "
                          "button.keyboardButton",
                          pd.powershell_drift(target))

    def test_the_canonical_tags_are_present_on_both_sides(self):
        """A token check, and only a token check — see the class docstring."""
        code = pd.POWERSHELL.read_text()
        for tag in ("'null'", "'bool:true'", "'bool:false'", "'num:'",
                    "'str:'"):
            self.assertIn(tag, code)
        self.assertNotIn('= "$value"', code,
                         "the leaf must not be stringified for comparison")

    def test_the_contract_block_lists_every_snapshot_field(self):
        text = pd.POWERSHELL.read_text()
        block = text[text.find(pd.PS_BLOCK_BEGIN):text.find(pd.PS_BLOCK_END)]
        for key in pd.SNAPSHOT_KEYS + pd.PROFILE_KEYS:
            self.assertIn(key, block)


if __name__ == "__main__":
    unittest.main()
