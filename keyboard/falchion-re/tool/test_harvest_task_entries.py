#!/usr/bin/env python3
"""Offline tests for RTOS task-entry harvesting.

Synthetic harvest output for the acceptance rules, the real captures for the
real numbers. Every rejection path is asserted to REJECT: a task entry that is
seeded on a mis-resolved argument puts a function at an address that is not
code, and everything downstream of it becomes false reachability. No device
access, no writes.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harvest_task_entries as ht

READY = (ht.TASKS / "installed_b.txt").exists()

TARGET_OK = ("TARGET addr=0x18001000 thumb=true mapped=true "
             "valid_subroutine=false decoded=8 prologue=push_{r4,lr} "
             "defined=true at=Task_X")


def callsite(a0="0x18001001", a1="0x18002000", a2="0x100", a3="0x0",
             a4="0x5", a5="0x0", name="X", instr="18000100", func="18000080"):
    return (f"CALLSITE primitive=18012fd0 instr={instr} func={func} order=0 "
            f"a0={a0} a1={a1} a2={a2} a3={a3} a4={a4} a5={a5} str={name}")


class Acceptance(unittest.TestCase):

    def parse(self, *lines):
        _targets, tasks, _primitives = ht.parse("\n".join(lines), "installed")
        return tasks

    def test_a_fully_resolved_thumb_entry_is_accepted(self):
        task, = self.parse(TARGET_OK, callsite())
        self.assertTrue(task.accepted)
        self.assertEqual((task.name, task.program), ("X", "app"))
        self.assertEqual((task.stack_words, task.stack_bytes), (0x100, 0x400))

    def test_the_stack_argument_is_words_not_bytes(self):
        """The primitive allocates `stack << 2`; reporting words as bytes
        would understate every task's stack by a factor of four."""
        task, = self.parse(TARGET_OK, callsite(a2="0x40"))
        self.assertEqual((task.stack_words, task.stack_bytes), (0x40, 0x100))

    def test_priority_is_clamped_and_the_ready_index_derived(self):
        task, = self.parse(TARGET_OK, callsite(a4="0x14"))
        self.assertEqual(task.priority, 0x14)
        self.assertEqual(task.effective_priority, ht.PRIORITY_MAX)
        self.assertEqual(task.ready_index, 0xF - ht.PRIORITY_MAX)

    def test_a_task_entry_in_the_other_image_is_placed_there(self):
        """The application creates one task whose code is in the entry image."""
        target = ("TARGET addr=0x498 thumb=true mapped=true "
                  "valid_subroutine=false decoded=8 prologue=push_{r1,lr} "
                  "defined=true at=Task_OEM")
        task, = self.parse(target, callsite(a0="0x499"))
        self.assertEqual(task.program, "entry")
        self.assertTrue(task.accepted)


class FailsClosed(unittest.TestCase):
    """Each of these must refuse to produce a root."""

    def parse(self, *lines):
        _targets, tasks, _primitives = ht.parse("\n".join(lines), "installed")
        return tasks

    def test_an_unresolvable_argument_rejects_the_call_site(self):
        task, = self.parse(TARGET_OK, callsite(a2="unknown"))
        self.assertFalse(task.accepted)
        self.assertIn("stack_words", task.unresolved)

    def test_an_unresolvable_entry_rejects_the_call_site(self):
        task, = self.parse(TARGET_OK, callsite(a0="unknown"))
        self.assertFalse(task.accepted)
        self.assertIn("entry", task.unresolved)
        self.assertIsNone(task.program)

    def test_an_entry_without_the_thumb_bit_is_rejected(self):
        """The frame builder takes this straight as the task PC, so an even
        value would fault on the first instruction."""
        task, = self.parse(TARGET_OK, callsite(a0="0x18001000"))
        self.assertFalse(task.accepted)
        self.assertIn("entry_not_thumb", task.unresolved)

    def test_an_entry_outside_every_image_is_rejected(self):
        task, = self.parse(TARGET_OK, callsite(a0="0x99999999"))
        self.assertFalse(task.accepted)
        self.assertIn("entry_outside_every_image", task.unresolved)

    def test_an_entry_with_no_target_line_is_rejected(self):
        """No validation line means nothing checked that the bytes decode."""
        task, = self.parse(callsite())
        self.assertFalse(task.accepted)
        self.assertIsNone(task.target)

    def test_a_target_that_did_not_decode_is_rejected(self):
        target = ("TARGET addr=0x18001000 thumb=true mapped=true "
                  "valid_subroutine=false decoded=2 prologue=movs_r0,#0x0 "
                  "defined=false at=none")
        task, = self.parse(target, callsite())
        self.assertFalse(task.accepted)
        self.assertFalse(task.target.decodes_as_thumb)

    def test_an_unmapped_target_is_rejected(self):
        target = ("TARGET addr=0x18001000 thumb=true mapped=false "
                  "valid_subroutine=false decoded=8 prologue=none "
                  "defined=false at=none")
        task, = self.parse(target, callsite())
        self.assertFalse(task.accepted)

    def test_a_call_site_in_no_function_resolves_nothing(self):
        """The harvester emits it rather than dropping it, and every argument
        comes back unknown, so it cannot become a root."""
        line = ("CALLSITE primitive=18012fd0 instr=18000100 func=none order=0 "
                "a0=unknown a1=unknown a2=unknown a3=unknown a4=unknown "
                "a5=unknown str=none reason=call_site_in_no_function")
        task, = self.parse(TARGET_OK, line)
        self.assertFalse(task.accepted)
        self.assertEqual(len(task.unresolved), 6)

    def test_a_wrong_arity_line_is_not_parsed_as_a_call_site(self):
        """A primitive with a different argument count must not be silently
        read as if it had this one's shape."""
        line = ("CALLSITE primitive=18012fd0 instr=18000100 func=18000080 "
                "order=0 a0=0x18001001 a1=0x18002000 a2=0x100 str=X")
        self.assertEqual(self.parse(TARGET_OK, line), ())


class CreationOrder(unittest.TestCase):

    def test_a_creator_that_is_itself_a_task_comes_first(self):
        target_a = ("TARGET addr=0x18001000 thumb=true mapped=true "
                    "valid_subroutine=false decoded=8 prologue=p defined=true "
                    "at=A")
        target_b = ("TARGET addr=0x18003000 thumb=true mapped=true "
                    "valid_subroutine=false decoded=8 prologue=p defined=true "
                    "at=B")
        # B is created at a LOWER address, by A, which is created later in the
        # listing. Address order would put B first; creation order must not.
        early = callsite(a0="0x18003001", name="B", instr="18001010",
                         func="18001000")
        late = callsite(a0="0x18001001", name="A", instr="18009000",
                        func="18008000")
        _targets, tasks, _primitives = ht.parse(
            "\n".join([target_a, target_b, early, late]), "installed")
        self.assertEqual([task.name for task in ht.creation_order(tasks)],
                         ["A", "B"])


@unittest.skipUnless(READY, "run the Ghidra harvest step first")
class RealCaptures(unittest.TestCase):

    def test_both_releases_find_the_same_five_tasks(self):
        names = {}
        for release in ("installed", "vendor"):
            _targets, tasks, _primitives = ht.load(release)
            names[release] = [task.name for task in tasks]
        self.assertEqual(names["installed"], names["vendor"])
        self.assertEqual(names["installed"],
                         ["INIT_TASK", "OEM_MAIN_SERVICE_TASK", "IDLE",
                          "Tmr Svc", "usbd_wdt"])

    def test_both_releases_agree_on_every_stack_and_priority(self):
        """The releases relocate but do not retune: a difference here would
        mean one of the two harvests resolved an argument wrongly."""
        shape = {}
        for release in ("installed", "vendor"):
            _targets, tasks, _primitives = ht.load(release)
            shape[release] = [(task.name, task.stack_words, task.priority,
                               task.argument, task.program)
                              for task in tasks]
        self.assertEqual(shape["installed"], shape["vendor"])

    def test_every_task_is_accepted_in_both_releases(self):
        for release in ("installed", "vendor"):
            _targets, tasks, _primitives = ht.load(release)
            for task in tasks:
                self.assertTrue(task.accepted,
                                f"{release} {task.name} {task.unresolved}")

    def test_the_app_entries_differ_by_the_measured_relocation(self):
        installed = {task.name: task for task in ht.load("installed")[1]}
        vendor = {task.name: task for task in ht.load("vendor")[1]}
        for name, task in installed.items():
            delta = task.entry - vendor[name].entry
            self.assertIn(delta, (0, 0x2C),
                          f"{name} moved by 0x{delta:x}, which is neither "
                          "unmoved nor the Phase 3 relocation")

    def test_the_roots_are_deterministic(self):
        self.assertEqual(ht.roots(), ht.roots())

    def test_the_indirect_call_counts_are_symmetric_and_enumerated(self):
        """5A's exit gate: the residue must have a number and an address list."""
        for release in ("installed", "vendor"):
            counts = ht.indirect_calls(release)
            self.assertEqual(set(counts), {"entry", "app"})
            for item in counts.values():
                self.assertEqual(len(item["sites"]), item["total"])
                self.assertEqual(item["resolved"] + item["unresolved"],
                                 item["total"])
                self.assertGreater(item["unresolved"], 0,
                                   "claiming zero unresolved indirect calls "
                                   "would be a stronger claim than 5A made")
        self.assertEqual(
            {p: (i["total"], i["unresolved"])
             for p, i in ht.indirect_calls("installed").items()},
            {p: (i["total"], i["unresolved"])
             for p, i in ht.indirect_calls("vendor").items()})

    def test_a_miscounted_indirect_block_is_refused(self):
        """A file whose total disagrees with its listed sites must raise, not
        report the smaller number as if it were complete."""
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            saved, ht.TASKS = ht.TASKS, Path(directory)
            try:
                (ht.TASKS / "installed_a.txt").write_text(
                    "INDIRECT instr=1000 func=900 mnemonic=blx register=r3 "
                    "target=unknown\n"
                    "INDIRECT_RESULT sites=9 resolved=0 unresolved=9\n")
                with self.assertRaises(ht.HarvestError):
                    ht.indirect_calls("installed")
            finally:
                ht.TASKS = saved

    def test_the_report_states_what_it_does_not_cover(self):
        text = "\n".join(ht.report_lines())
        self.assertIn("is a different primitive and is not covered", text)
        self.assertIn("It is not a runtime schedule", text)


if __name__ == "__main__":
    unittest.main()
