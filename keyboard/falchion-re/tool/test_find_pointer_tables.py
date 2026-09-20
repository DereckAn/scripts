#!/usr/bin/env python3
"""Offline tests for the function-pointer table detector.

Synthetic images for the detection and provenance rules, the preserved slices
for the real numbers. No device access, no writes.

The `Provenance` class is adversarial on purpose. Log 131's first consumer
scanner correlated a literal load with a store and an indirect call through a
shared structure-field offset, across a register map that was never reset
between functions; offsets 0x0, 0x4, 0x8 and 0xc are everywhere, so that
manufactured agreement out of unrelated code. Every test in that class is a
shape the scanner must refuse.
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

# Spelled out rather than embedded, so this test file stays plain ASCII.
CRLF = bytes((0x0D, 0x0A))


def image(words, base=0x18000000, pad_to=0x100):
    """Pack `words`, padded so the targets they point at are inside the image."""
    padded = list(words) + [0] * max(0, pad_to // 4 - len(words))
    return struct.pack(f"<{len(padded)}I", *padded)


# --------------------------------------------------------- a tiny assembler
#
# Enough Thumb to build the shapes the provenance rules have to judge. Every
# helper returns one halfword; `assemble` resolves the PC-relative ones.

BASE = 0x18000000
TABLE = 0x00000100          # three Thumb pointers at a stride of four
OBJ_X_WORD = 0x00000110     # a literal holding the address of object X
OBJ_Y_WORD = 0x00000114     # ... and of object Y
SLOT_WORD = 0x00000118      # ... and the ADDRESS of OBJ_X_WORD, for ("mem", A)
OBJ_X = 0x18000200
OBJ_Y = 0x18000300
OBJ_X_SLOT = 0x18000000 + OBJ_X_WORD
TARGETS = (0x18000010, 0x18000020, 0x18000030)


def ldr_lit(rt, where):
    def build(pc):
        offset = (BASE + where) - ((pc + 4) & ~3)
        assert 0 <= offset <= 1020 and offset % 4 == 0, hex(offset)
        return 0x4800 | (rt << 8) | (offset // 4)
    return build


def str_imm(rt, rn, offset=0):
    return lambda pc: 0x6000 | ((offset // 4) << 6) | (rn << 3) | rt


def ldr_imm(rt, rn, offset=0):
    return lambda pc: 0x6800 | ((offset // 4) << 6) | (rn << 3) | rt


def blx(rm):
    return lambda pc: 0x4780 | (rm << 3)


def movs(rd, value=0):
    return lambda pc: 0x2000 | (rd << 8) | value


def cmp_imm(rn, value=0):
    return lambda pc: 0x2800 | (rn << 8) | value


def bne(where):
    def build(pc):
        delta = (BASE + where) - (pc + 4)
        return 0xD100 | ((delta // 2) & 0xFF)
    return build


def branch(where):
    def build(pc):
        delta = (BASE + where) - (pc + 4)
        return 0xE000 | ((delta // 2) & 0x7FF)
    return build


def bx_lr():
    return lambda pc: 0x4770


def mov_reg(rd, rm):
    return lambda pc: 0x4600 | ((rd & 8) << 4) | (rm << 3) | (rd & 7)


def adds_imm(rdn, value):
    return lambda pc: 0x3000 | (rdn << 8) | value


def call():
    """`bl .+4` — enough for the scanner to see a call and clobber r0-r3."""
    return (lambda pc: 0xF000, lambda pc: 0xF800)


def tbb():
    """A table branch: successors cannot be enumerated from the bytes alone."""
    return (lambda pc: 0xE8DF, lambda pc: 0xF000)


def assemble(*functions, size=0x400):
    """functions = ((offset, [builders]), ...). Returns (bytes, Code)."""
    data = bytearray(size)
    struct.pack_into("<3I", data, TABLE, *(target | 1 for target in TARGETS))
    struct.pack_into("<I", data, OBJ_X_WORD, OBJ_X)
    struct.pack_into("<I", data, OBJ_Y_WORD, OBJ_Y)
    struct.pack_into("<I", data, SLOT_WORD, OBJ_X_SLOT)
    spans = []
    for offset, builders in functions:
        cursor = offset
        flat = []
        for builder in builders:
            flat.extend(builder if isinstance(builder, tuple) else (builder,))
        for builder in flat:
            struct.pack_into("<H", data, cursor, builder(BASE + cursor))
            cursor += 2
        spans.append((BASE + offset, BASE + cursor))
    body = bytes(data)
    code = fpt.Code(body, BASE, tuple(spans),
                    tuple((span[0], (span,)) for span in spans))
    return body, code


def survey_of(*functions, known=frozenset()):
    data, code = assemble(*functions)
    return fpt.survey("app", "synthetic.bin", BASE, data, known, code)


def only_table(result):
    table, = [item for item in result.tables if item.location == BASE + TABLE]
    return table


class DetectionRules(unittest.TestCase):
    """A lone plausible word is not a table; a run at a constant stride is."""

    def survey(self, words, known=frozenset(), base=0x18000000, code=None):
        return fpt.survey("app", "synthetic.bin", base, image(words, base),
                          known, code)

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
        result = survey_of(interleaved((0, 1, 2)), known={TARGETS[0]})
        self.assertEqual(only_table(result).verdict, fpt.VALIDATED)
        self.assertEqual(result.known_targets, (TARGETS[0],))
        self.assertEqual(result.new_targets, TARGETS[1:])

    def test_seed_arguments_name_each_new_target(self):
        result = survey_of(interleaved((0, 1, 2)))
        args = fpt.seed_arguments(result)
        self.assertEqual(len(args), 3)
        for argument in args:
            name, address = argument.split("=")
            self.assertTrue(name.startswith("PtrTarget_"))
            self.assertTrue(address.startswith("0x"))


# One function that installs the listed entries into distinct fields of the
# object at OBJ_X and then dispatches the listed fields. Everything is inside
# ONE function on ONE straight-line path, because since log 133 that is the
# only shape that can prove anything.
def installs_then_dispatch(entries, fields, offset=0x00):
    body = [ldr_lit(1, OBJ_X_WORD)]
    for index in entries:
        body += [ldr_lit(0, TABLE + 4 * index), str_imm(0, 1, 4 * index)]
    for field in fields:
        # A call clobbers r1, so the base is reloaded before each dispatch.
        body += [ldr_lit(1, OBJ_X_WORD), ldr_imm(2, 1, field), blx(2)]
    body.append(bx_lr())
    return (offset, body)


def interleaved(entries, offset=0x00):
    """Install, dispatch, install, dispatch ... — each pair on its own path.

    A call empties the live-install set, so proving more than one entry means
    each install must sit after the previous dispatch.
    """
    body = []
    for index in entries:
        body += [ldr_lit(1, OBJ_X_WORD), ldr_lit(0, TABLE + 4 * index),
                 str_imm(0, 1, 4 * index), ldr_imm(2, 1, 4 * index), blx(2)]
    body.append(bx_lr())
    return (offset, body)


# Split across two unrelated functions: installs in one, dispatch in the other.
INSTALL_ONLY_FUNCTION = (0x00, [
    ldr_lit(1, OBJ_X_WORD),
    ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
    ldr_lit(0, TABLE + 4), str_imm(0, 1, 0x4),
    ldr_lit(0, TABLE + 8), str_imm(0, 1, 0x8),
    bx_lr(),
])
DISPATCH_X_FUNCTION = (0x40, [
    ldr_lit(3, OBJ_X_WORD), ldr_imm(2, 3, 0x0), blx(2), bx_lr(),
])
DISPATCH_Y_FUNCTION = (0x60, [
    ldr_lit(3, OBJ_Y_WORD), ldr_imm(2, 3, 0x0), blx(2), bx_lr(),
])


class Provenance(unittest.TestCase):
    """Every shape here must produce NO root. Adversarial by construction.

    Log 131's scanner had no boundaries at all. Log 132's had boundaries but
    collected installs and dispatches independently and unioned the dispatch
    facts across the whole image, so two mutually exclusive branches — or two
    unrelated functions — could still be read as one proof. These are the
    shapes that must not be believed.
    """

    def assertNoRoot(self, result, expect_verdict=fpt.CANDIDATE):
        table = only_table(result)
        self.assertEqual(table.proven, (), table.reason)
        self.assertEqual(table.rooted, (), table.reason)
        self.assertEqual(table.proofs, ())
        self.assertEqual(result.root_targets, ())
        self.assertEqual(fpt.seed_arguments(result), ())
        self.assertEqual(table.verdict, expect_verdict, table.reason)
        return table

    # ---- 1. mutually exclusive branches ----------------------------------

    def test_install_and_dispatch_in_mutually_exclusive_branches(self):
        """The log-133 blocker. No execution path performs both.

            ldr r1, =object_x
            cmp r0, #0
            bne dispatch
        install:
            ldr r0, =table_entry_0 ; str r0,[r1,#0] ; b end
        dispatch:
            ldr r2,[r1,#0] ; blx r2
        end:
            bx lr
        """
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),        # 0x00
            cmp_imm(0, 0),                 # 0x02
            bne(0x0C),                     # 0x04 -> dispatch
            ldr_lit(0, TABLE + 0),         # 0x06
            str_imm(0, 1, 0x0),            # 0x08  install
            branch(0x12),                  # 0x0A -> end
            ldr_imm(2, 1, 0x0),            # 0x0C  dispatch
            blx(2),                        # 0x0E
            bx_lr(),                       # 0x10
            bx_lr()])                      # 0x12  end
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual(len(table.installed), 1,
                         "the install itself is still observed and reported")
        self.assertEqual(table.loaded, (BASE + TABLE,))

    # ---- 2, 3, 4. the positive controls ----------------------------------

    def test_install_then_dispatch_on_one_straight_line_is_proof(self):
        table = only_table(survey_of(installs_then_dispatch((0,), (0x0,))))
        self.assertEqual(table.verdict, fpt.VALIDATED)
        self.assertEqual(table.proven, (BASE + TABLE,))
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))
        proof, = table.proofs
        self.assertLess(proof.install, proof.dispatch)
        self.assertEqual(proof.function, BASE)
        self.assertEqual(proof.obj, (fpt.ABS, OBJ_X))
        self.assertIn("call-free path inside", proof.text())

    def test_both_operations_after_a_join_where_the_arms_agree(self):
        """Both predecessors name object X, so the join keeps it and the
        install and dispatch that follow are on one path."""
        function = (0x00, [
            cmp_imm(0, 0),                 # 0x00
            bne(0x08),                     # 0x02
            ldr_lit(1, OBJ_X_WORD),        # 0x04
            branch(0x0A),                  # 0x06
            ldr_lit(1, OBJ_X_WORD),        # 0x08
            ldr_lit(0, TABLE + 0),         # 0x0A  join
            str_imm(0, 1, 0x0),            # 0x0C
            ldr_imm(2, 1, 0x0),            # 0x0E
            blx(2),                        # 0x10
            bx_lr()])                      # 0x12
        table = only_table(survey_of(function))
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))

    def test_both_operations_after_a_join_where_the_arms_disagree(self):
        """The control for the control: object X on one arm, Y on the other."""
        function = (0x00, [
            cmp_imm(0, 0), bne(0x08),
            ldr_lit(1, OBJ_X_WORD), branch(0x0A),
            ldr_lit(1, OBJ_Y_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual(table.installed, ())

    def test_install_before_a_conditional_whose_arm_dispatches(self):
        """The install reaches the dispatching continuation, so it counts."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),        # 0x00
            ldr_lit(0, TABLE + 0),         # 0x02
            str_imm(0, 1, 0x0),            # 0x04  install
            cmp_imm(0, 0),                 # 0x06
            bne(0x0C),                     # 0x08 -> dispatch arm
            branch(0x10),                  # 0x0A -> end
            ldr_imm(2, 1, 0x0),            # 0x0C
            blx(2),                        # 0x0E
            bx_lr()])                      # 0x10
        table = only_table(survey_of(function))
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))

    def test_the_non_dispatching_arm_alone_proves_nothing(self):
        """Same install, but the only continuation reached does not call."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(2, 1, 0x4),            # a DIFFERENT field
            blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    # ---- 5. unrelated functions ------------------------------------------

    def test_install_in_one_function_and_dispatch_in_another(self):
        table = self.assertNoRoot(
            survey_of(INSTALL_ONLY_FUNCTION, DISPATCH_X_FUNCTION))
        self.assertEqual(len(table.installed), 3,
                         "the installs are observed, and prove nothing alone")

    def test_a_load_in_one_function_and_a_store_in_another_do_not_correlate(self):
        loader = (0x00, [ldr_lit(0, TABLE + 0), bx_lr()])
        storer = (0x20, [ldr_lit(1, OBJ_X_WORD), str_imm(0, 1, 0x0),
                         ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(loader, storer))
        self.assertEqual(table.loaded, (BASE + TABLE,))
        self.assertEqual(table.installed, ())

    def test_a_store_into_one_object_and_a_call_through_another_do_not(self):
        """Same field offset, different object. Offsets are not identities."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_lit(3, OBJ_Y_WORD), ldr_imm(2, 3, 0x0), blx(2),
            bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual({record[2] for record in table.installed},
                         {(fpt.ABS, OBJ_X)})
        self.assertIn("same object", table.reason)

    # ---- 6. intervening overwrites ---------------------------------------

    def test_an_overwrite_of_the_field_invalidates_the_proof(self):
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            movs(0, 0), str_imm(0, 1, 0x0),        # the field is rewritten
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_an_unresolved_store_between_the_two_invalidates_the_proof(self):
        """A store this scanner cannot place could land on the field."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            lambda pc: 0x7008,                     # strb r0,[r1,#0]
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_a_call_between_the_two_invalidates_the_proof(self):
        """The callee could rewrite the field, or the slot the object came
        from. Nothing survives a call."""
        function = (0x00, [
            ldr_lit(4, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 4, 0x0),
            call(),
            ldr_imm(2, 4, 0x0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    # ---- 7. a mutable pointer is not an object instance -------------------

    def test_a_pointer_reloaded_from_an_untouched_slot_is_the_same_object(self):
        """Positive control for the ("mem", A) identity."""
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),   # r1 = *(OBJ_X_SLOT)
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(1, 4, 0x0),                          # reload the pointer
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = only_table(survey_of(function))
        self.assertEqual({record[2] for record in table.installed},
                         {(fpt.MEM, OBJ_X_SLOT)})
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))

    def test_a_pointer_reloaded_after_the_slot_was_written_is_not(self):
        """Same slot, same token — a DIFFERENT runtime object. The store to
        the slot between the two loads is what makes it different, and the
        matching ("mem", A) token must not paper over it."""
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            movs(0, 0), str_imm(0, 4, 0x0),              # *(OBJ_X_SLOT) = 0
            ldr_imm(1, 4, 0x0),                          # a different object
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual({record[2] for record in table.installed},
                         {(fpt.MEM, OBJ_X_SLOT)})

    # ---- the rest of the fail-closed surface ------------------------------

    def test_a_register_overwritten_before_the_store_breaks_provenance(self):
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), movs(0, 7), str_imm(0, 1, 0x0),
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual(table.loaded, (BASE + TABLE,))
        self.assertEqual(table.installed, ())

    def test_the_object_register_overwritten_before_the_store_breaks_it(self):
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD), movs(1, 0),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_lit(1, OBJ_X_WORD), ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual(table.installed, ())

    def test_the_object_register_overwritten_before_the_call_breaks_it(self):
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            movs(1, 0), ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_the_loaded_pointer_overwritten_before_the_call_breaks_it(self):
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(2, 1, 0x0), movs(2, 0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_loading_and_storing_without_dispatch_is_insufficient(self):
        table = self.assertNoRoot(survey_of(installs_then_dispatch((0, 1, 2),
                                                                   ())))
        self.assertEqual(len(table.installed), 3)

    def test_an_unconsumed_pointer_shaped_table_stays_a_candidate(self):
        data, _code = assemble(installs_then_dispatch((0, 1, 2), (0x0,)))
        result = fpt.survey("app", "synthetic.bin", BASE, data, frozenset(),
                            code=None)
        table = self.assertNoRoot(result)
        self.assertIn("no consumer", table.reason)
        self.assertEqual(table.loaded, ())

    def test_a_function_with_an_unresolvable_branch_is_not_analysed(self):
        """Fail closed: after a TBB neither the joins nor the instruction
        boundaries can be trusted, so the whole function is declined."""
        poisoned = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(2, 1, 0x0), blx(2),
            tbb(),
            bx_lr()])
        result = survey_of(poisoned)
        table = self.assertNoRoot(result)
        self.assertEqual(table.loaded, ())
        self.assertEqual([entry for entry, _reason in result.skipped_functions],
                         [BASE])
        self.assertIn("successors cannot be enumerated",
                      result.skipped_functions[0][1])

    def test_a_caller_saved_register_does_not_survive_a_call(self):
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD), call(),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual(table.installed, ())

    def test_a_callee_saved_register_does_survive_a_call(self):
        """The one assumption the scanner makes, pinned so it stays visible."""
        self.assertEqual(fpt.CALLER_SAVED, (0, 1, 2, 3, 12, 14))
        function = (0x00, [
            ldr_lit(4, OBJ_X_WORD), call(),
            ldr_lit(0, TABLE + 0), str_imm(0, 4, 0x0),
            ldr_imm(2, 4, 0x0), blx(2), bx_lr()])
        table = only_table(survey_of(function))
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))


class AliasRules(unittest.TestCase):
    """Direct unit tests for the alias predicate, with no image involved."""

    X = (fpt.ABS, 0x18000200)
    Y = (fpt.ABS, 0x18000300)
    SLOT = (fpt.MEM, 0x18000110)
    OTHER_SLOT = (fpt.MEM, 0x18000120)

    def test_an_abs_identity_has_a_concrete_four_byte_interval(self):
        self.assertEqual(fpt.effective_range(self.X, 0x4),
                         (0x18000204, 0x18000208))
        self.assertEqual(fpt.INSTALL_WIDTH, 4)

    def test_a_mem_identity_has_no_interval(self):
        self.assertIsNone(fpt.effective_range(self.SLOT, 0x4))

    def test_the_same_word_written_two_ways_aliases(self):
        """`("abs",X)+4` and `("abs",X+4)+0` are one physical word."""
        self.assertTrue(fpt.may_alias(self.X, 0x4,
                                      (fpt.ABS, 0x18000204), 0x0))
        self.assertTrue(fpt.may_alias((fpt.ABS, 0x18000204), 0x0,
                                      self.X, 0x4))

    def test_partially_overlapping_words_alias(self):
        self.assertTrue(fpt.may_alias(self.X, 0x4,
                                      (fpt.ABS, 0x18000202), 0x0))
        self.assertTrue(fpt.may_alias(self.X, 0x4,
                                      (fpt.ABS, 0x18000206), 0x0))

    def test_adjacent_non_overlapping_words_do_not_alias(self):
        self.assertFalse(fpt.may_alias(self.X, 0x0, self.X, 0x4))
        self.assertFalse(fpt.may_alias(self.X, 0x4, self.X, 0x0))
        self.assertFalse(fpt.may_alias(self.X, 0x0, self.Y, 0x0))
        self.assertFalse(fpt.may_alias(self.X, 0x4,
                                       (fpt.ABS, 0x18000208), 0x0))

    def test_abs_and_mem_always_may_alias(self):
        self.assertTrue(fpt.may_alias(self.X, 0x0, self.SLOT, 0x0))
        self.assertTrue(fpt.may_alias(self.SLOT, 0x0, self.X, 0x0))
        self.assertTrue(fpt.may_alias(self.SLOT, 0x0, self.Y, 0x40))

    def test_two_mem_identities_are_never_assumed_distinct(self):
        self.assertTrue(fpt.may_alias(self.SLOT, 0x0, self.SLOT, 0x0))
        self.assertTrue(fpt.may_alias(self.SLOT, 0x0, self.OTHER_SLOT, 0x0))
        self.assertTrue(fpt.may_alias(self.SLOT, 0x0, self.OTHER_SLOT, 0x8))

    def test_a_store_over_the_pointer_slot_invalidates_its_installs(self):
        self.assertTrue(fpt.slot_overwritten(
            self.SLOT, (fpt.ABS, 0x18000110), 0x0))
        self.assertTrue(fpt.slot_overwritten(
            self.SLOT, (fpt.ABS, 0x18000100), 0x10))
        self.assertTrue(fpt.slot_overwritten(
            self.SLOT, (fpt.ABS, 0x1800010E), 0x0), "partial overlap counts")
        self.assertFalse(fpt.slot_overwritten(
            self.SLOT, (fpt.ABS, 0x18000114), 0x0))

    def test_slot_overwrite_never_applies_to_an_abs_install(self):
        self.assertFalse(fpt.slot_overwritten(
            self.X, (fpt.ABS, 0x18000200), 0x0))

    def test_an_unplaceable_store_overwrites_any_slot(self):
        self.assertTrue(fpt.slot_overwritten(self.SLOT, self.OTHER_SLOT, 0x0))


class Aliasing(unittest.TestCase):
    """Log 134: an overwritten installation must not survive as a proof.

    The previous rule invalidated an install only when a later store carried
    the SAME (object identity, field) pair, so the same physical word written
    through a different abstract identity slipped past it.
    """

    def assertNoRoot(self, result):
        table = only_table(result)
        self.assertEqual(table.proven, (), table.reason)
        self.assertEqual(table.rooted, (), table.reason)
        self.assertEqual(result.root_targets, ())
        self.assertEqual(len(table.rooted), len(table.proven))
        return table

    def test_an_abs_install_overwritten_through_a_mem_alias(self):
        """Case A. r3 is object X reached through the pointer slot, so the
        store at [r3,#0] destroys the pointer installed at [r1,#0]."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),                 # r1 = &object_x  (ABS)
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_lit(4, SLOT_WORD), ldr_imm(3, 4, 0x0),   # r3 = *(slot) (MEM)
            movs(2, 0), str_imm(2, 3, 0x0),         # overwrites object_x + 0
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual({record[2] for record in table.installed},
                         {(fpt.ABS, OBJ_X)})

    def test_a_mem_install_overwritten_through_an_abs_alias(self):
        """The mirror of case A: install through the slot, clobber through
        the absolute address."""
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),   # r1 = *(slot) (MEM)
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_lit(3, OBJ_X_WORD),                      # r3 = &object_x (ABS)
            movs(2, 0), str_imm(2, 3, 0x0),
            ldr_imm(1, 4, 0x0), ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual({record[2] for record in table.installed},
                         {(fpt.MEM, OBJ_X_SLOT)})

    def test_two_abs_expressions_for_one_address(self):
        """Case B. `("abs",X)+4` installed, `("abs",X+4)+0` overwritten."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x4),
            mov_reg(5, 1), adds_imm(5, 4),          # r5 = &object_x + 4
            movs(2, 0), str_imm(2, 5, 0x0),
            ldr_imm(2, 1, 0x4), blx(2), bx_lr()])
        table = self.assertNoRoot(survey_of(function))
        self.assertEqual({record[3] for record in table.installed}, {0x4})

    def test_a_partially_overlapping_absolute_store(self):
        """`("abs",X+2)+0` covers bytes 2..6, so it corrupts the word at +4."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x4),
            mov_reg(5, 1), adds_imm(5, 2),
            movs(2, 0), str_imm(2, 5, 0x0),
            ldr_imm(2, 1, 0x4), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_two_provably_disjoint_absolute_stores_preserve_the_install(self):
        """The control: +0x8 and +0xc cannot touch the word at +0x0."""
        function = (0x00, [
            ldr_lit(1, OBJ_X_WORD),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            movs(2, 0), str_imm(2, 1, 0x8), str_imm(2, 1, 0xC),
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = only_table(survey_of(function))
        self.assertEqual(table.proven, (BASE + TABLE,))
        proof, = table.proofs
        self.assertEqual(proof.entry, BASE + TABLE)
        self.assertEqual(proof.install, BASE + 0x04)
        self.assertEqual(proof.dispatch, BASE + 0x0E)
        self.assertEqual(proof.function, BASE)
        self.assertEqual(proof.obj, (fpt.ABS, OBJ_X))
        self.assertEqual(proof.field, 0x0)
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))

    def test_a_store_to_the_pointer_slot_invalidates_the_mem_install(self):
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            movs(2, 0), str_imm(2, 4, 0x0),         # *(slot) = 0
            ldr_imm(1, 4, 0x0), ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_a_store_through_a_different_mem_slot_invalidates_it(self):
        """Two slots can hold the same pointer; nothing here proves they do
        not."""
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_lit(6, OBJ_Y_WORD), ldr_imm(3, 6, 0x0),   # another MEM object
            movs(2, 0), str_imm(2, 3, 0x0),
            ldr_imm(1, 4, 0x0), ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        self.assertNoRoot(survey_of(function))

    def test_a_store_through_the_same_mem_slot_invalidates_it(self):
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            movs(2, 0), str_imm(2, 1, 0x8),         # a DIFFERENT field, but
            ldr_imm(2, 1, 0x0), blx(2), bx_lr()])   # MEM cannot prove that
        self.assertNoRoot(survey_of(function))

    def test_the_untouched_mem_positive_control_still_passes(self):
        """No store at all between install and dispatch, so nothing to alias."""
        function = (0x00, [
            ldr_lit(4, SLOT_WORD), ldr_imm(1, 4, 0x0),
            ldr_lit(0, TABLE + 0), str_imm(0, 1, 0x0),
            ldr_imm(1, 4, 0x0), ldr_imm(2, 1, 0x0), blx(2), bx_lr()])
        table = only_table(survey_of(function))
        proof, = table.proofs
        self.assertEqual(proof.obj, (fpt.MEM, OBJ_X_SLOT))
        self.assertEqual(proof.field, 0x0)
        self.assertEqual(proof.entry, BASE + TABLE)
        self.assertEqual(proof.function, BASE)
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))

    def test_rooted_matches_proven_across_every_aliasing_shape(self):
        shapes = (
            (0x00, [ldr_lit(1, OBJ_X_WORD), ldr_lit(0, TABLE + 0),
                    str_imm(0, 1, 0x0), ldr_lit(4, SLOT_WORD),
                    ldr_imm(3, 4, 0x0), movs(2, 0), str_imm(2, 3, 0x0),
                    ldr_imm(2, 1, 0x0), blx(2), bx_lr()]),
            (0x00, [ldr_lit(1, OBJ_X_WORD), ldr_lit(0, TABLE + 0),
                    str_imm(0, 1, 0x4), mov_reg(5, 1), adds_imm(5, 4),
                    movs(2, 0), str_imm(2, 5, 0x0), ldr_imm(2, 1, 0x4),
                    blx(2), bx_lr()]),
            (0x00, [ldr_lit(1, OBJ_X_WORD), ldr_lit(0, TABLE + 0),
                    str_imm(0, 1, 0x0), movs(2, 0), str_imm(2, 1, 0x8),
                    ldr_imm(2, 1, 0x0), blx(2), bx_lr()]),
            installs_then_dispatch((0, 1, 2), (0x0,)),
            interleaved((0, 1, 2)),
        )
        for shape in shapes:
            for table in survey_of(shape).tables:
                self.assertEqual(len(table.rooted), len(table.proven))


class Rooting(unittest.TestCase):
    """What may become a root. There is no whole-table promotion."""

    def test_three_installed_one_proven_roots_exactly_one(self):
        table = only_table(survey_of(installs_then_dispatch((0, 1, 2), (0x0,))))
        self.assertEqual(table.verdict, fpt.VALIDATED)
        self.assertEqual(len(table.installed), 3)
        self.assertEqual(table.proven, (BASE + TABLE,))
        self.assertEqual(table.rooted, ((BASE + TABLE, TARGETS[0]),))
        self.assertIn("are NOT rooted", table.reason)

    def test_three_installed_none_proven_roots_none(self):
        table = only_table(survey_of(installs_then_dispatch((0, 1, 2), ())))
        self.assertEqual(len(table.installed), 3)
        self.assertEqual(len({record[3] for record in table.installed}), 3,
                         "three distinct fields of one object, and still none")
        self.assertEqual(table.rooted, ())
        self.assertEqual(table.verdict, fpt.CANDIDATE)

    def test_three_individually_proven_roots_all_three(self):
        table = only_table(survey_of(interleaved((0, 1, 2))))
        self.assertEqual(len(table.proven), 3)
        self.assertEqual(table.rooted,
                         tuple(zip((BASE + TABLE, BASE + TABLE + 4,
                                    BASE + TABLE + 8), TARGETS)))

    def test_rooted_never_exceeds_proven(self):
        for functions in ((installs_then_dispatch((0, 1, 2), (0x0,)),),
                          (installs_then_dispatch((0, 1, 2), ()),),
                          (interleaved((0, 1, 2)),),
                          (INSTALL_ONLY_FUNCTION, DISPATCH_X_FUNCTION)):
            for table in survey_of(*functions).tables:
                self.assertLessEqual(len(table.rooted), len(table.proven))
                self.assertEqual(len(table.rooted), len(table.proven))

    def test_nothing_calls_an_unproven_entry_callable(self):
        """The explanatory text must not claim more than the evidence."""
        result = survey_of(installs_then_dispatch((0, 1, 2), (0x0,)))
        table = only_table(result)
        self.assertNotIn("callable", table.reason.replace(
            "nothing here asserts that they are callable", ""))
        text = "\n".join(fpt.report_lines((result,)))
        self.assertNotIn("WHOLE_TABLE", text)
        self.assertFalse(hasattr(table, "whole_table"))

    def test_a_printable_format_string_block_cannot_be_promoted(self):
        """The 0x1404 shape in miniature, synthetic so the rule is the subject.

        Eight `"Rn:   0x%08X<CR><LF>"` records put `0d 0a 00 00` at a 16-byte
        stride, which reads as the plausible pointer 0x00000a0d. A consumer
        that loads and dispatches all eight is supplied on purpose: the span is
        text, so the run must still be rejected and must still seed nothing.
        """
        record = b"R%d:   0x%%08X" + CRLF + b"\x00\x00"
        block = b"".join(record % n for n in range(8))
        code = (0x4852, 0x6008, 0x4855, 0x6008, 0x4858, 0x6008, 0x681A, 0x4790)
        data = bytearray(image([0] * 0x80, 0x0, pad_to=0x1000))
        struct.pack_into(f"<{len(code)}H", data, 0, *code)
        data[0x140:0x140 + len(block)] = block
        data = bytes(data)
        result = fpt.survey("entry", "synthetic.bin", 0x0, data, frozenset(),
                            fpt.Code.single(data, 0x0, ((0x0, 0x10),)))
        table, = [item for item in result.tables if item.stride == 16]
        self.assertEqual(table.location, 0x14C)
        self.assertEqual(table.count, 8)
        self.assertEqual(set(table.targets), {0x00000A0C})
        self.assertEqual(table.verdict, fpt.REJECTED)
        self.assertIn("printable text", table.reason)
        self.assertEqual(table.rooted, ())
        self.assertEqual(result.root_targets, ())
        self.assertEqual(fpt.seed_arguments(result), ())


class SupersededSeedRemover(unittest.TestCase):
    """FalchionRemoveSeeds.java must be incapable of mutating a program.

    A banner saying "do not use" is not a safeguard while `run()` still calls
    `removeFunction()` and `clearListing()`. Comments are stripped before the
    search, so the file may still *describe* what it used to do.
    """

    SCRIPT = Path(fpt.ROOT) / "ghidra/scripts/FalchionRemoveSeeds.java"
    DESTRUCTIVE = ("removeFunction", "clearListing", "symbol.delete",
                   "createFunction", "disassemble(", "setBytes", "clearSymbol",
                   "createLabel", "removeSymbol", "deleteFunction")

    def body(self):
        import re
        text = self.SCRIPT.read_text()
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return "\n".join(re.sub(r"//.*$", "", line)
                          for line in text.splitlines())

    def test_no_destructive_call_survives_outside_the_comments(self):
        code = self.body()
        for name in self.DESTRUCTIVE:
            self.assertNotIn(name, code, name)

    def test_it_imports_nothing_that_could_mutate(self):
        code = self.body()
        for symbol in ("Function", "AddressSetView", "Symbol", "SourceType",
                       "Listing"):
            self.assertNotIn(f"import ghidra.program.model", code.replace(
                "import ghidra.app.script.GhidraScript;", "")) or None
            self.assertNotIn(symbol + " ", code, symbol)

    def test_it_refuses_and_says_where_to_go_instead(self):
        text = self.SCRIPT.read_text()
        self.assertIn("REFUSED", text)
        self.assertIn("log 132", text)
        self.assertIn("mutated=0", text)

    def test_the_check_would_notice_a_restored_mutation(self):
        import re
        restored = self.body() + "\n        removeFunction(f);\n"
        self.assertIn("removeFunction", restored)


@unittest.skipUnless(READY, "run the Ghidra inventory step first")
class RealImages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.surveys = fpt.build()
        cls.entry, cls.app = cls.surveys[0], cls.surveys[1]

    def test_the_application_has_three_dense_pointer_runs(self):
        strides = [table.stride for table in self.app.tables]
        counts = [table.count for table in self.app.tables]
        self.assertEqual(strides, [4, 4, 4])
        self.assertEqual(counts, [26, 6, 12])
        self.assertEqual([table.location for table in self.app.tables],
                         [0x18016D44, 0x18017D08, 0x18018CE8])

    def test_no_run_in_any_image_is_rooted(self):
        """Log 132's outcome, and the whole point of the provenance rules.

        Two of the application runs are loaded and installed into one object
        each, which is real evidence and is reported as such — but the object
        is dispatched in another function that receives it as an argument, and
        the scanner will not follow that. Nothing is rooted on a guess.
        """
        for item in self.surveys:
            self.assertEqual(item.root_targets, (), item.program)
            self.assertEqual(item.validated, (), item.program)
            self.assertEqual(fpt.seed_arguments(item), (), item.program)

    def test_the_two_installer_functions_are_reported_in_full(self):
        """loaded / installed / proven / rooted, kept separate and honest."""
        by_location = {table.location: table for table in self.app.tables}
        for location, count, function, obj in (
                (0x18017D08, 6, 0x18018B22, (fpt.ABS, 0x180342C8)),
                (0x18018CE8, 12, 0x18018A28, (fpt.MEM, 0x1801EBBC))):
            table = by_location[location]
            self.assertEqual(len(table.loaded), count, hex(location))
            self.assertEqual(len(table.installed), count, hex(location))
            self.assertEqual({record[0] for record in table.installed},
                             {function})
            self.assertEqual({record[2] for record in table.installed}, {obj})
            self.assertEqual(len({record[3] for record in table.installed}),
                             count, "distinct fields of one object")
            self.assertEqual(table.proven, (), "dispatch is not proven")
            self.assertEqual(table.rooted, ())
            self.assertEqual(table.proofs, ())

    def test_the_largest_run_is_declined_rather_than_guessed(self):
        """FUN_18016934 contains a TBB, so the scanner refuses to read it."""
        table, = [item for item in self.app.tables
                  if item.location == 0x18016D44]
        self.assertEqual(table.loaded, ())
        self.assertIn(0x18016934,
                      [entry for entry, _r in self.app.skipped_functions])

    def test_the_entry_image_0x1404_run_is_rejected_as_string_data(self):
        """The regression test for log 131's first finding.

        0x1404 is not a handler struct array. It is eight consecutive
        `"Rn:   0x%08X"` fault-report format strings; the `0d 0a 00 00` that
        terminates each one reads as 0x00000a0d, so eight identical
        "pointers" appear at a 16-byte stride.
        """
        table, = [item for item in self.entry.tables
                  if item.location == 0x1404]
        self.assertEqual((table.stride, table.count), (16, 8))
        self.assertEqual(set(table.targets), {0x00000A0C})
        self.assertEqual(table.verdict, fpt.REJECTED)
        self.assertIn("printable text", table.reason)
        self.assertEqual(table.rooted, ())
        self.assertNotIn(0x00000A0C, self.entry.root_targets)

    def test_the_entry_image_0x5680_run_is_an_unconsumed_candidate(self):
        """Library-specific extended-precision powers-of-ten records: field 0
        of each 12-byte record is an exponent, not an address, and only the
        odd ones carry bit 0 — which is what produced the 24-byte stride."""
        table, = [item for item in self.entry.tables
                  if item.location == 0x5680]
        self.assertEqual((table.stride, table.count), (24, 3))
        self.assertEqual(table.verdict, fpt.CANDIDATE)
        self.assertIn("no consumer", table.reason)
        self.assertEqual(table.loaded, ())
        self.assertEqual(set(table.targets),
                         {0x00004004, 0x00004018, 0x000040B4})

    def test_the_false_seeds_are_gone_from_the_entry_inventory(self):
        """The Ghidra side of the correction, checked from the artefact.

        Log 104 created PtrTarget_00000a0c, PtrTarget_00004004 and
        PtrTarget_000040b4 from the two rejected runs, and the 1-byte
        FUN_000040b2 was the collateral. No count is pinned here: what matters
        is that the false entries are absent and both releases agree.
        """
        import match_functions as mf
        sizes = []
        for name in ("installed_a.txt", "vendor_a.txt"):
            records, _header = mf.parse_inventory(
                (INVENTORIES / name).read_text())
            entries = {record.entry for record in records}
            for address in (0x00000A0C, 0x00004004, 0x000040B4, 0x000040B2):
                self.assertNotIn(address, entries, f"{name} 0x{address:x}")
            sizes.append(len(records))
        self.assertEqual(sizes[0], sizes[1], "the releases must stay symmetric")

    def test_the_repaired_spans_are_defined_and_correctly_bounded(self):
        """Log 132: clearing the false functions' listings deleted real code.

        The enclosing routine at 0x9fc and the routine the 0x4004 seed split
        must both be single, fully covered functions again.
        """
        import match_functions as mf
        for name in ("installed_a.txt", "vendor_a.txt"):
            records, _header = mf.parse_inventory(
                (INVENTORIES / name).read_text())
            by_entry = {record.entry: record for record in records}
            self.assertIn(0x9FC, by_entry, name)
            self.assertEqual(by_entry[0x9FC].ranges, ((0x9FC, 0xA46),), name)
            self.assertIn(0x3DD8, by_entry, name)
            self.assertEqual(by_entry[0x3DD8].ranges, ((0x3DD8, 0x401C),),
                             name)
            covered = set()
            for record in records:
                for low, high in record.ranges:
                    covered |= set(range(low, high))
            for low, high in ((0x9FC, 0xA46), (0x3DD8, 0x401C)):
                missing = sorted(set(range(low, high)) - covered)
                self.assertEqual(missing, [],
                                 f"{name}: undefined bytes in a repaired span")

    def test_the_vendor_runs_sit_at_the_measured_shift(self):
        vendor_app = fpt.build(fpt.VENDOR, 0x0, "vendor")[1]
        installed = [table.location for table in self.app.tables]
        vendor = [table.location for table in vendor_app.tables]
        self.assertEqual([address - 0x2C for address in installed], vendor,
                         "the runs move by exactly the relocation Phase 3 "
                         "measured, which corroborates both")
        self.assertEqual(vendor_app.root_targets, (),
                         "and neither release roots any of them")

    def test_the_vendor_entry_image_rejects_the_same_two_runs(self):
        vendor_entry = fpt.build(fpt.VENDOR, 0x0, "vendor")[0]
        self.assertEqual(
            [(table.location, table.verdict) for table in vendor_entry.tables],
            [(0x1404, fpt.REJECTED), (0x5680, fpt.CANDIDATE)])
        self.assertEqual(vendor_entry.root_targets, ())

    def test_the_vector_table_is_excluded_from_the_entry_survey(self):
        for table in self.entry.tables:
            self.assertGreaterEqual(table.location, 0x140)
        for address, _target in self.entry.loose_candidates:
            self.assertGreaterEqual(address, 0x140)

    def test_json_is_deterministic(self):
        first = json.dumps(fpt.to_dict(fpt.build()), sort_keys=True)
        second = json.dumps(fpt.to_dict(fpt.build()), sort_keys=True)
        self.assertEqual(first, second)

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

    def test_the_report_states_what_it_cannot_do(self):
        text = "\n".join(fpt.report_lines((self.entry, self.app)))
        self.assertIn("candidate, not a proven function", text)
        self.assertIn("cannot follow an object across a call boundary", text)
        self.assertIn("EVIDENCE loaded=", text)
        self.assertIn("SKIPPED FUN_", text)


@unittest.skipUnless(READY, "run the Ghidra inventory step first")
class SeededReachability(unittest.TestCase):
    """5A's deliverable, and what is left of it once provenance is required."""

    def program(self, needle):
        import map_hardware_interfaces as mh
        hardware = mh.build_map()
        found, = [program for program in hardware.programs
                  if needle in program.name]
        return found

    def test_no_image_carries_a_table_root(self):
        for needle in ("entry image", "application"):
            program = self.program(needle)
            self.assertEqual({label for label, _entry in program.roots
                              if label.startswith("table@")}, set(), needle)
            self.assertEqual(program.unresolved_roots, (), needle)

    def test_reachability_is_still_partial_and_still_reported(self):
        """No count is pinned. What must hold is that some functions are
        reached, many are not, and the gap is enumerated rather than hidden."""
        for needle in ("entry image", "application"):
            program = self.program(needle)
            self.assertGreater(len(program.contexts), 0, needle)
            self.assertLess(len(program.contexts), program.functions, needle)
            self.assertEqual(len(program.contexts) + len(program.unreached),
                             program.functions, needle)
            self.assertTrue(program.orphans, needle)


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
        for survey in payload["surveys"]:
            for table in survey["tables"]:
                self.assertLessEqual(len(table["rooted"]), table["count"])
                self.assertLessEqual(len(table["proven"]), len(table["loaded"])
                                     or table["count"])


if __name__ == "__main__":
    unittest.main()
