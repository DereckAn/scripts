#!/usr/bin/env python3
"""Offline tests for the hardware and runtime interface map.

Reads the preserved evidence binary plus the Ghidra-derived inventories and
peripheral maps under `ghidra/`. No device access, no writes.
"""
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_hardware_interfaces as mh
import report_phase5 as rp

INVENTORIES = Path(mh.INVENTORIES)
PERIPHERALS = Path(mh.PERIPHERALS)
READY = ((INVENTORIES / "installed_a.txt").exists()
         and (PERIPHERALS / "installed_a.txt").exists())


class ArmNames(unittest.TestCase):
    """Only architectural registers get names, and they get the right ones."""

    def test_known_registers(self):
        self.assertEqual(mh.arm_register_name(0xE000ED0C)[0], "AIRCR")
        self.assertEqual(mh.arm_register_name(0xE000ED04)[0], "ICSR")
        self.assertEqual(mh.arm_register_name(0xE000E010)[0], "SYST_CSR")

    def test_indexed_nvic_arrays(self):
        self.assertEqual(mh.arm_register_name(0xE000E100)[0], "NVIC_ISER0")
        self.assertEqual(mh.arm_register_name(0xE000E104)[0], "NVIC_ISER1")
        self.assertEqual(mh.arm_register_name(0xE000E180)[0], "NVIC_ICER0")

    def test_a_byte_access_names_the_containing_word(self):
        name, description = mh.arm_register_name(0xE000ED1A)
        self.assertEqual(name, "SHPR1+2")
        self.assertIn("byte 2", description)

    def test_an_unknown_ppb_address_is_not_named(self):
        name, description = mh.arm_register_name(0xE000EF00)
        self.assertIsNone(name)
        self.assertIn("not identified", description)

    def test_a_vendor_address_is_never_named(self):
        self.assertEqual(mh.arm_register_name(0x40100000), (None, None))
        self.assertEqual(mh.arm_register_name(0x45000000), (None, None))


class AddressClassification(unittest.TestCase):
    """Classification is per address, and an unknown space stays unknown."""

    def setUp(self):
        self.runtime = ((0x18000000, 0x1801E380), (0x1801E380, 0x18036168))

    def classify(self, address, program_base=0x18000000, size=0x1E380):
        return mh.classify_address(address, program_base, size, self.runtime)

    def test_arm_core_is_named_from_the_architecture(self):
        kind, description = self.classify(0xE000ED0C)
        self.assertEqual(kind, "arm-core")
        self.assertIn("ARM architecture", description)

    def test_the_program_image_and_the_ram_above_it_are_distinguished(self):
        """The old per-block rule labelled a whole 1 MiB span with one kind."""
        self.assertEqual(self.classify(0x18000010)[0], "program")
        self.assertEqual(self.classify(0x1801F000)[0], "runtime-ram")

    def test_an_address_past_the_proven_runtime_end_is_not_called_ram(self):
        self.assertLess(0x18036168, 0x18037224)
        self.assertEqual(self.classify(0x18037224)[0], "unknown")

    def test_the_flash_window_is_storage(self):
        self.assertEqual(self.classify(0x60021000)[0], "flash-window")

    def test_a_null_relative_address_is_an_artifact(self):
        kind, description = self.classify(0x4)
        self.assertEqual(kind, "artifact")
        self.assertIn("resolved to zero", description)

    def test_an_unidentified_space_stays_unknown_not_vendor_mmio(self):
        for address in (0x40100000, 0x45000000, 0x08000000, 0x10000000,
                        0x20000000):
            kind, description = self.classify(address)
            self.assertEqual(kind, "unknown", hex(address))
            self.assertIn("no evidence identifies", description)

    def test_a_block_with_two_kinds_is_reported_as_mixed(self):
        registers = [{"kind": "runtime-ram"}, {"kind": "unknown"}]
        self.assertEqual(mh.block_kind(registers), "mixed")
        self.assertEqual(mh.block_kind([{"kind": "arm-core"}]), "arm-core")


class PeripheralMapParsing(unittest.TestCase):

    def test_access_and_unresolved_lines(self):
        text = (
            "PROGRAM x\n"
            "ACCESS target=0x40100014 width=4 dir=write instr=18001234 "
            "func=18001200 base=r3@0x40100000 off=20 stored=0xf370800\n"
            "ACCESS target=0xe000ed04 width=4 dir=read instr=18001240 "
            "func=18001200 base=r3@0xe000ed04 off=0 stored=unknown\n"
            "UNRESOLVED instr=18001250 func=18001200 mnemonic=ldr "
            "reason=base_r0_unknown\n"
            "RESULT accesses=2 unresolved=1 functions=1\n")
        accesses, unresolved = mh.parse_peripheral_map(text)
        self.assertEqual(len(accesses), 2)
        self.assertEqual(accesses[0].target, 0x40100014)
        self.assertEqual(accesses[0].stored, 0xF370800)
        self.assertEqual(accesses[0].direction, "write")
        self.assertIsNone(accesses[1].stored)
        self.assertEqual(unresolved, {"base_r0_unknown": 1})

    def test_a_map_without_accesses_is_refused(self):
        with self.assertRaises(ValueError):
            mh.parse_peripheral_map("PROGRAM x\nRESULT accesses=0\n")


class Reachability(unittest.TestCase):

    def records(self, *lines):
        import match_functions as mf
        header = "PROGRAM x\nIMAGE_BASE 00000000\n"
        return mf.parse_inventory(header + "\n".join(lines) + "\n")[0]

    def func(self, entry, callees=""):
        return (f"FUNC entry={entry:08x} name=F size=0x10 "
                f"ranges={entry:08x}-{entry + 0x10:08x} insns=4 blocks=1 "
                f"bytes_sha={'a' * 64} shape_sha={'b' * 64} callers=0 "
                f"callees={callees} consts= strings=")

    def test_contexts_propagate_along_the_call_graph(self):
        records = self.records(
            self.func(0x100, "00000200"),
            self.func(0x200, "00000300"),
            self.func(0x300),
            self.func(0x900))
        contexts, unreached = mh.reachability(records, [("Reset", 0x100)])
        self.assertEqual(contexts[0x300], {"Reset"})
        self.assertEqual(unreached, (0x900,))

    def test_a_function_can_carry_two_contexts(self):
        records = self.records(
            self.func(0x100, "00000300"),
            self.func(0x200, "00000300"),
            self.func(0x300))
        contexts, _unreached = mh.reachability(
            records, [("Reset", 0x100), ("IRQ6", 0x200)])
        self.assertEqual(contexts[0x300], {"Reset", "IRQ6"})

    def test_a_root_that_is_not_a_function_is_skipped(self):
        records = self.records(self.func(0x100))
        contexts, unreached = mh.reachability(records, [("Reset", 0x999)])
        self.assertEqual(contexts, {})
        self.assertEqual(unreached, (0x100,))


@unittest.skipUnless(READY, "run the Ghidra inventory and peripheral steps first")
class RealImage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.map = mh.build_map()
        cls.payload = mh.to_dict(cls.map)

    def test_the_vector_table_runs_to_the_first_code_address(self):
        """An ARMv7-M table has no terminator, so nothing looks for one."""
        span = self.payload["vector_table_span"]
        self.assertEqual((span["lo"], span["hi"]), (0x0, 0x140))
        self.assertEqual(len(self.payload["vector_table"]), 80)
        self.assertEqual(
            len(self.payload["vector_table"]) - len(mh.CORE_VECTORS), 64)
        self.assertEqual(self.payload["fill_value"], 0x14DF)

    def test_a_live_slot_after_the_fill_value_is_not_lost(self):
        """IRQ63 at 0x13c sits past the last fill slot and is still a vector."""
        slots = {slot["name"]: slot for slot in self.payload["vector_table"]}
        self.assertEqual(slots["IRQ63"]["kind"], "live")
        self.assertEqual(slots["IRQ63"]["value"], 0x00000AD1)
        self.assertEqual(slots["IRQ63"]["target_function"], 0x00000AD0)
        fill_indexes = [slot["index"] for slot in self.payload["vector_table"]
                        if slot["kind"] == "fill"]
        self.assertLess(max(fill_indexes), slots["IRQ63"]["index"])

    def test_the_core_vectors_are_all_populated(self):
        core = self.payload["vector_table"][:len(mh.CORE_VECTORS)]
        self.assertEqual(core[0]["kind"], "initial_sp")
        self.assertEqual(core[0]["value"], 0x18036168)
        live = [slot["name"] for slot in core if slot["kind"] == "live"]
        for name in ("Reset", "NMI", "HardFault", "PendSV", "SysTick", "SVCall"):
            self.assertIn(name, live)

    def test_the_live_interrupts_are_the_ones_software_enables(self):
        names = {slot["name"] for slot in self.payload["live_interrupts"]}
        for name in ("IRQ6", "IRQ38"):
            self.assertIn(name, names)
        statements = " ".join(item["statement"]
                              for item in self.payload["notable_observations"])
        self.assertIn("IRQ6, IRQ38", statements)

    def test_two_cross_image_code_entries_outside_the_vector_table(self):
        outside = [pointer for pointer in self.payload["code_entries"]
                   if not pointer["in_vector_table"]]
        self.assertEqual([pointer["value"] for pointer in outside],
                         [0x18016E69, 0x18016F2D])

    def test_no_unidentified_register_is_ever_named(self):
        for program in self.payload["programs"]:
            for block in program["blocks"]:
                for register in block["registers"]:
                    if register["kind"] == "arm-core":
                        continue
                    self.assertIsNone(register["arm_name"],
                                      f"0x{register['address']:08x} must not "
                                      "carry a name")

    def test_the_vector_table_extent_is_labelled_an_inference(self):
        confidence = self.payload["vector_table_confidence"]
        self.assertEqual(confidence["level"], "strongly inferred")
        self.assertIn("no exact IRQ-count source", confidence["basis"])
        self.assertIn("product brief is series-level", confidence["basis"])

    def test_every_register_carries_a_confidence_and_an_init_field(self):
        for program in self.payload["programs"]:
            for block in program["blocks"]:
                for register in block["registers"]:
                    self.assertTrue(register["confidence"],
                                    hex(register["address"]))
                    self.assertIn("reset_reachable_write_values", register)
                    self.assertTrue(register["kind_basis"])

    def test_reset_reachable_write_values_are_reset_path_writes_only(self):
        entry, = [program for program in self.payload["programs"]
                  if "entry" in program["name"]]
        found = {register["address"]: register
                 for block in entry["blocks"]
                 for register in block["registers"]}
        # Written 0x5afa0000 from a function the call graph reaches from the
        # Reset vector. That is reachability, not proof of execution.
        self.assertIn(0x5AFA0000, found[0x40008000]["reset_reachable_write_values"])
        # AIRCR is written from NMI, not from anything reset-reachable, so it
        # has no reset-reachable write even though it has a stored value.
        aircr = found[0xE000ED0C]
        self.assertEqual(aircr["reset_reachable_write_values"], [])
        self.assertIn(0x05FA0004, aircr["stored_values"])

    def test_the_phase_is_declared_a_first_pass(self):
        self.assertEqual(self.payload["phase_status"]["state"], "first-pass")
        self.assertIn("incomplete", self.payload["phase_status"]["reason"])

    def test_the_arm_core_registers_carry_the_expected_values(self):
        found = {}
        for program in self.payload["programs"]:
            for block in program["blocks"]:
                if block["kind"] != "arm-core":
                    continue
                for register in block["registers"]:
                    found.setdefault(register["address"], set()).update(
                        register["stored_values"])
        self.assertIn(0x05FA0004, found[0xE000ED0C])   # VECTKEY | SYSRESETREQ
        self.assertIn(0x10000000, found[0xE000ED04])   # PENDSVSET
        self.assertIn(0x40, found[0xE000E100])         # IRQ6 enabled

    def test_the_dependency_map_states_what_is_blocked(self):
        verdicts = {row["verdict"] for row in self.payload["dependency_map"]}
        self.assertIn("must-replace", verdicts)
        self.assertIn("may-omit", verdicts)
        # An unidentified space must be reported as blocked, not as a
        # conditional permission.
        self.assertTrue({"unknown-service", "must-reproduce-or-disprove"}
                        & verdicts, verdicts)
        arm = [row for row in self.payload["dependency_map"]
               if row["kind"] == "arm-core"]
        self.assertTrue(arm)
        for row in arm:
            self.assertEqual(row["verdict"], "must-replace")

    def test_unidentifiable_areas_are_declared_not_covered(self):
        states = {item["area"]: item["state"]
                  for item in self.payload["coverage"]}
        for area, state in states.items():
            if any(word in area for word in ("USB", "Hall", "RGB",
                                             "nonvolatile", "GPIO")):
                self.assertEqual(state, "not-covered", area)

    def test_the_documented_app_entry_contradiction_is_recorded(self):
        joined = " ".join(self.payload["contradictions"])
        self.assertIn("0x1800023a", joined)
        self.assertIn("needs rechecking", joined)

    def test_json_is_deterministic(self):
        again = mh.to_dict(mh.build_map())
        self.assertEqual(json.dumps(self.payload, sort_keys=True),
                         json.dumps(again, sort_keys=True))


@unittest.skipUnless(READY, "run the Ghidra inventory and peripheral steps first")
class Artifacts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rendered = rp.render()

    def test_every_declared_artifact_is_rendered(self):
        self.assertEqual(sorted(self.rendered), sorted(rp.ARTIFACTS))

    def test_the_artifacts_on_disk_are_current(self):
        stale = [name for name, text in self.rendered.items()
                 if not (rp.NOTES / name).exists()
                 or (rp.NOTES / name).read_text() != text]
        self.assertEqual(stale, [],
                         "run python3 tool/report_phase5.py to refresh these")

    def test_check_mode_reports_current(self):
        buffer = io.StringIO()
        stdout, sys.stdout = sys.stdout, buffer
        try:
            code = rp.main(["--check"])
        finally:
            sys.stdout = stdout
        self.assertEqual(code, 0)
        self.assertIn("RESULT reports_current=True", buffer.getvalue())

    def test_the_markdown_states_the_identification_barrier(self):
        text = self.rendered["installed-hardware-interfaces.md"]
        self.assertIn("SNC73270 reference manual", text)
        self.assertIn("names no vendor peripheral", text)
        self.assertIn("Dependency map", text)
        self.assertIn("must-replace", text)
        self.assertIn("lower bound", text)


if __name__ == "__main__":
    unittest.main()
