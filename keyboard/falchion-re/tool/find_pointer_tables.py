#!/usr/bin/env python3
"""Find function-pointer tables in an extracted image slice.

Read-only and offline. Phase 5A: Ghidra's call graph does not follow a call made
through a pointer held in a table, so most of the application's functions come
back unreached and every later subphase inherits that blindness. This tool finds
the tables in the flash bytes, so their targets can be seeded as functions and
reachability recomputed.

THREE THINGS ARE KEPT APART, because log 131 showed that collapsing them
manufactured a table out of printf format strings:

  1. **pointer-shaped run** — at least `MIN_ENTRIES` words with the Thumb bit
     set, at a constant stride, each naming an even address at or above the
     image's first code address. This is a *shape*, and shapes lie: eight
     consecutive `"Rn:   0x%08X\\r\\n"` format strings put `0d 0a 00 00` at a
     16-byte stride, which decodes as the plausible-looking word 0x00000a0d.
  2. **validated dispatch/callback table** — a run whose words are *consumed as
     pointers by code*, with provenance. Byte shape is not evidence; an
     instruction that reads the word is, and only when the object it writes the
     word into is the same object something indirect-calls.
  3. **eligible reachability root** — only a validated table. A run that no
     instruction reads stays a candidate forever, however code-like Ghidra
     finds its targets: seeding a function at an address and then citing that
     function as proof the address was a function is circular.

FOUR EVIDENCE BUCKETS, never conflated (log 132). Log 131's first attempt
matched a store to an indirect call by structure-field OFFSET, across a
register map no function boundary reset, and then rooted a whole table off one
matching entry. So the report now separates:

  LOADED    an instruction in an analysed function body performs a PC-relative
            literal load of the entry. A local fact about one instruction.
  INSTALLED that loaded value is stored into a field of a NAMED OBJECT.
  PROVEN    that same object's same field is the operand of an
            `ldr rX,[rY,#off]; blx rX`.
  ROOTED    dispatch-proven entries only — or every entry, when a documented
            WHOLE-TABLE PROOF holds: all entries installed, all naming one
            object, into distinct fields, from one function, with at least one
            of those fields indirect-called through that same object.

Targets of a validated table are still only *candidates for being code*.
Whether each one is really code is settled by whether Ghidra can disassemble a
function there, not by this tool — and that, on its own, never promotes a run.

No device access. Examples:
    python3 tool/find_pointer_tables.py
    python3 tool/find_pointer_tables.py --json
    python3 tool/find_pointer_tables.py --seed-args app
"""
import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_installed_records as ex
import falchion_image as fi
import match_functions as mf
import reconstruct_decompress as rd

ROOT = Path(__file__).resolve().parent.parent
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"

# A run shorter than this is not evidence of a table.
MIN_ENTRIES = 3
# Strides worth trying: a plain pointer array, then structures carrying one
# pointer per element.
STRIDES = (4, 8, 12, 16, 20, 24, 32)

# The entry image's vector table is a pointer array too, but it is decoded and
# seeded separately, so it is excluded here to avoid reporting it twice. The
# same span is also not code, so a "pointer" into it is not a function pointer:
# CODE_FLOOR is the first address in each image where code actually begins, and
# a target below it is rejected. Without that floor, structures whose words
# happen to carry the low bit produce targets like 0x00000004.
EXCLUDE = {"entry": ((0x0, 0x140),), "app": (), "ram": ()}
CODE_FLOOR = {"entry": 0x140, "app": 0x18000000, "ram": 0x18000000}
# The reconstructed decompress region sits *above* the code it points into, so
# for it the acceptance window cannot be "inside this slice". CODE_CEIL names
# the end of the runtime code the slice may legitimately point at; where it is
# absent the window ends at the slice itself, which is the original behaviour.
CODE_CEIL = {"ram": 0x1801EE84}

VALIDATED = "validated"
CANDIDATE = "candidate"
REJECTED = "rejected"

# A span this far into printable ASCII is text, not a pointer array. The bar is
# deliberately high: a real pointer table's words are addresses, and an address
# is printable only by accident.
PRINTABLE_FRACTION = 0.75
# Printable means text a human would read, not "not a control byte": NUL is
# excluded on purpose, or a zero-padded numeric table scores as prose.
_PRINTABLE = set(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}


# ------------------------------------------------------------------ Thumb-2
#
# A deliberately small, deliberately suspicious abstract interpreter.
#
# Log 131's first attempt correlated a literal load with a store and an indirect
# call by structure-field OFFSET alone, across a register map that was never
# reset between functions. Offsets 0x0, 0x4, 0x8 and 0xc occur everywhere, so
# that produced correlations between unrelated code. This version:
#
#   * analyses one function at a time and starts from an empty register map;
#   * starts from an empty map again at every body range and at every branch
#     target inside the function, so two arms of a branch are never joined;
#   * empties the map after every branch, every call, and every instruction it
#     does not recognise — an unrecognised encoding could write any register;
#   * refuses to analyse a function at all when it contains a flow instruction
#     whose successors cannot be enumerated (`TBB`, `TBH`, `BX <reg>`, `IT`),
#     because then neither the joins nor the instruction boundaries after it can
#     be trusted;
#   * tracks the IDENTITY of the object a field belongs to, not just the field
#     offset, and only calls an entry dispatch-proven when the store and the
#     indirect call name the SAME object.
#
# Everything it cannot establish, it declines. The intended failure direction is
# "no evidence", never "plausible evidence".
#
# WHAT IT STILL CANNOT DO, stated because it is the reason the three application
# tables are candidates and not roots: it cannot follow an object across a call
# boundary. An ops struct built in one function and dispatched in another, with
# the pointer passed as an argument, is invisible to it. Ghidra's decompiler
# P-code could follow that; this scanner is not a substitute for it, and the
# report says so rather than rounding the gap up to a root.

# Object identities. ("abs", A) is the object at absolute address A; ("mem", A)
# is the object whose pointer was read from absolute address A.
ABS = "abs"
MEM = "mem"


def _wide(first):
    return (first & 0xF800) in (0xE800, 0xF000, 0xF800)


def _decode(data, base, ranges):
    """Yield (address, first, second or None, width) over the given ranges."""
    for low, high in ranges:
        offset, end, address = low - base, high - base, low
        if offset < 0 or end > len(data):
            continue
        while offset + 1 < end:
            first, = struct.unpack_from("<H", data, offset)
            second = None
            if _wide(first):
                if offset + 3 >= end:
                    return
                second, = struct.unpack_from("<H", data, offset + 2)
            width = 4 if _wide(first) else 2
            yield address, first, second, width
            offset += width
            address += width


def _sign_extend(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def branch_target(address, first, second):
    """The address a recognised branch goes to, or None if it is not a branch.

    Returns the string "unresolvable" for a flow instruction whose successors
    cannot be enumerated. The caller refuses to analyse such a function.
    """
    if (first & 0xF000) == 0xD000:                         # B<cond> T1 / SVC
        condition = (first >> 8) & 0xF
        if condition >= 0xE:                               # UDF / SVC
            return "unresolvable"
        return address + 4 + _sign_extend(first & 0xFF, 8) * 2
    if (first & 0xF800) == 0xE000:                         # B T2
        return address + 4 + _sign_extend(first & 0x7FF, 11) * 2
    if (first & 0xF500) == 0xB100:                         # CBZ / CBNZ
        imm = ((first >> 3) & 0x1F) | ((first >> 4) & 0x20)
        return address + 4 + imm * 2
    if (first & 0xFF00) == 0x4700:                         # BX / BLX register
        register = (first >> 3) & 0xF
        if first & 0x80:                                   # BLX <reg>: a call
            return None
        return None if register == 14 else "unresolvable"  # BX LR is a return
    if (first & 0xFF00) == 0xBD00 or (first & 0xFF00) == 0xBF00:
        # POP {..,PC} is a return; IT makes the next instructions conditional
        # and this scanner does not model predication.
        return None if (first & 0xFF00) == 0xBD00 else (
            "unresolvable" if first & 0xF else None)       # 0xBF00 is NOP
    if second is not None:
        if (first & 0xFFF0) == 0xE8D0 and (second & 0xFFE0) == 0xF000:
            return "unresolvable"                          # TBB / TBH
        if (first & 0xF800) == 0xF000 and (second & 0x8000):
            return "taken"                                 # B.W / BL / BLX imm
        if (first & 0xF800) == 0xF000 and (second & 0xD000) == 0x8000:
            return "taken"                                 # B<cond>.W
    return None


def _literal(address, first, second):
    """(destination register, literal address) for a PC-relative LDR."""
    if (first & 0xF800) == 0x4800:                              # LDR (literal) T1
        return (first >> 8) & 7, ((address + 4) & ~3) + (first & 0xFF) * 4
    if second is not None and (first & 0xFF7F) == 0xF85F:       # LDR (literal) T2
        offset = second & 0xFFF
        signed = offset if (first >> 7) & 1 else -offset
        return (second >> 12) & 0xF, ((address + 4) & ~3) + signed
    return None, None


def _reg_memory(first, second):
    """(is_store, Rt, Rn, offset) for a register-based LDR/STR immediate."""
    if (first & 0xF800) == 0x6000:                              # STR (imm) T1
        return True, first & 7, (first >> 3) & 7, ((first >> 6) & 0x1F) * 4
    if (first & 0xF800) == 0x6800:                              # LDR (imm) T1
        return False, first & 7, (first >> 3) & 7, ((first >> 6) & 0x1F) * 4
    if second is None or (first & 0xF) == 0xF:
        return None, None, None, None
    if (first & 0xFFF0) == 0xF8C0:                              # STR.W (imm) T3
        return True, (second >> 12) & 0xF, first & 0xF, second & 0xFFF
    if (first & 0xFFF0) == 0xF8D0:                              # LDR.W (imm) T3
        return False, (second >> 12) & 0xF, first & 0xF, second & 0xFFF
    return None, None, None, None


def _add_sub_immediate(first, second):
    """(register, delta) for the constant adjustments this scanner models."""
    if (first & 0xF800) == 0x3000:                              # ADDS (imm) T2
        return (first >> 8) & 7, first & 0xFF
    if (first & 0xF800) == 0x3800:                              # SUBS (imm) T2
        return (first >> 8) & 7, -(first & 0xFF)
    if second is not None and (first & 0xFBF0) in (0xF200, 0xF2A0):
        if (first & 0xF) == 0xF:                                # ADR, not modelled
            return None, None
        value = ((first >> 10) & 1) << 11 | ((second >> 4) & 0x700) | (second & 0xFF)
        register = (second >> 8) & 0xF
        return register, value if (first & 0xFBF0) == 0xF200 else -value
    return None, None


@dataclass(frozen=True)
class Code:
    """The instruction stream a word must be read by to count as consumed."""
    data: bytes
    base: int
    ranges: tuple        # ((low, high), ...) grouped per function
    functions: tuple = ()  # ((entry, ((low, high), ...)), ...)

    @classmethod
    def from_records(cls, data, base, records):
        functions = tuple((record.entry, tuple(record.ranges))
                          for record in records)
        return cls(data, base,
                   tuple(span for _entry, spans in functions for span in spans),
                   functions)

    @classmethod
    def single(cls, data, base, ranges, entry=None):
        """One synthetic function, for tests."""
        ranges = tuple(ranges)
        return cls(data, base, ranges,
                   ((entry if entry is not None else ranges[0][0], ranges),))


@dataclass(frozen=True)
class Proof:
    """One entry, installed and then dispatched, on one path in one function.

    `install` and `dispatch` are instruction addresses in the SAME function, and
    the install reaches the dispatch along a CFG path on which nothing
    overwrote the field, nothing overwrote the slot the object's pointer came
    from, and no call intervened. That last clause matters: a callee could
    rewrite either.

    What this does NOT claim is that the path is feasible — branch conditions
    are not modelled — only that a path exists. That is the strongest statement
    the interpreter can make, and it is what "proven" means here.
    """
    entry: int
    install: int
    dispatch: int
    function: int
    obj: tuple
    field: int

    def text(self):
        kind, address = self.obj
        where = (f"the object at 0x{address:08x}" if kind == ABS
                 else f"the object whose pointer is held at 0x{address:08x}")
        return (f"installed at 0x{self.install:08x} into {where}"
                f"+0x{self.field:x}, reaching the indirect call at "
                f"0x{self.dispatch:08x} along a call-free path inside "
                f"FUN_{self.function:08x}")


@dataclass(frozen=True)
class Consumption:
    """What the scanner proved, kept in three separate buckets.

    `loads` is a local fact about one instruction. `installs` adds an object
    identity. `proofs` additionally requires that the install and the dispatch
    sit on one path in one function. There is deliberately NO global set of
    dispatched (object, field) pairs any more: unioning those across the image
    is what let one function's store and another function's call — or two
    mutually exclusive branches of the same function — be read as one proof.
    """
    loads: dict          # entry address -> ((function, instruction), ...)
    installs: dict       # entry address -> ((function, instruction, object, field), ...)
    proofs: dict         # entry address -> (Proof, ...)
    skipped: tuple       # ((function, reason), ...)

    @classmethod
    def empty(cls):
        return cls({}, {}, {}, ())

    def proven(self, address):
        return self.proofs.get(address, ())


def _as_object(value):
    """The object a register points at, or None when it cannot be named."""
    if value is None:
        return None
    kind = value[0]
    if kind == "const":
        # A small immediate is a number, not an object. `movs r1,#0` must not
        # turn the next store into an install "into the object at 0x0".
        return (ABS, value[1]) if value[1] else None
    if kind == "word":
        return None if value[2] is None else (ABS, value[2])
    if kind == "field" and value[1] is not None and value[1][0] == ABS:
        return (MEM, value[1][1] + value[2])
    return None


def _word_at(data, base, address):
    offset = address - base
    if 0 <= offset <= len(data) - 4:
        return struct.unpack_from("<I", data, offset)[0]
    return None


# AAPCS: a callee may clobber r0-r3, r12 and lr, and must preserve r4-r11.
# This is a stated ASSUMPTION about compiler-generated code, not a proof, and it
# is the only thing in this scanner that survives a call. Without it the base
# pointer of an operations struct is lost at the first `bl` and nothing can be
# reported as installed at all; with it, an install is still not a root until
# the same object's field is seen in an indirect call.
CALLER_SAVED = (0, 1, 2, 3, 12, 14)


def _after_call(registers):
    return {number: value for number, value in registers.items()
            if number not in CALLER_SAVED}


def _killed(first, second):
    """Registers an instruction definitely writes, or None if unknown.

    Precision, not licence: every encoding listed here has a destination the
    ARMv7-M manual fixes, so killing exactly that register loses nothing. An
    encoding not listed falls through to "this could have written anything",
    which drops the whole register map. Adding an encoding here can only make
    the scanner see more; it can never make it accept a wrong correlation,
    because acceptance still needs a matching object identity.
    """
    if second is None:
        if (first & 0xE000) == 0x0000 and (first & 0xF800) != 0x2800:
            return (first & 7,) if (first & 0xF800) != 0x2000 else ((first >> 8) & 7,)
        if (first & 0xFC00) == 0x4000:                       # data-processing reg
            if (first & 0xFFC0) in (0x4200, 0x4280, 0x42C0):
                return ()                                    # TST / CMP / CMN
            return (first & 7,)
        if (first & 0xFF00) == 0x4400:                       # ADD (reg) T2
            return ((first & 7) | ((first & 0x80) >> 4),)
        if (first & 0xFF00) == 0x4500:                       # CMP (reg) T2
            return ()
        if (first & 0xF800) == 0x9800:                       # LDR [SP,#imm]
            return ((first >> 8) & 7,)
        if (first & 0xF800) == 0x9000:                       # STR [SP,#imm]
            return ()
        if (first & 0xF800) == 0x5000:                       # load/store reg offset
            return (first & 7,) if first & 0x0800 else ()
        if (first & 0xFF00) == 0xB000:                       # ADD/SUB SP,#imm
            return (13,)
        if (first & 0xFE00) == 0xB400:                       # PUSH
            return ()
        if (first & 0xFE00) == 0xBC00:                       # POP
            return tuple(n for n in range(8) if first & (1 << n)) + (
                (15,) if first & 0x100 else ())
        if (first & 0xFF00) == 0xB200:                       # SXTH/SXTB/UXTH/UXTB
            return (first & 7,)
        if (first & 0xF800) == 0xC000:                       # STM
            return ((first >> 8) & 7,)
        if (first & 0xF800) == 0xC800:                       # LDM
            return tuple(n for n in range(8) if first & (1 << n)) + (
                ((first >> 8) & 7,))
        return None
    if (first & 0xFA00) == 0xF000 and not (second & 0x8000):
        register = (second >> 8) & 0xF                       # data-processing imm
        return () if register == 0xF else (register,)
    if (first & 0xFE00) == 0xEA00:                           # data-processing reg
        register = (second >> 8) & 0xF
        return () if register == 0xF else (register,)
    if (first & 0xFE00) == 0xFA00:                           # shift / extend / parallel
        return ((second >> 8) & 0xF,)
    if (first & 0xFF80) == 0xFB00:                           # multiply / divide
        return ((second >> 8) & 0xF,)
    return None


def _successors(address, first, second, width, inside):
    """Where control can go next, or None when that cannot be enumerated."""
    target = branch_target(address, first, second)
    if target == "unresolvable":
        return None
    following = address + width
    if target is None:
        if (first & 0xFF00) == 0xBD00:                       # POP {..,PC}
            return ()
        if (first & 0xFF87) == 0x4700:                       # BX LR
            return ()
        return (following,)
    if target == "taken":                                    # 32-bit B/BL/BLX
        if second is not None and (second & 0xD000) == 0xD000:
            return (following,)                              # BL / BLX imm
        offset = (((first & 0x400) << 14)
                  | ((second & 0x2000) << 4) | ((second & 0x0800) << 7)
                  | ((first & 0x3FF) << 11) | ((second & 0x7FF) << 0))
        value = _sign_extend(offset, 25) * 2
        if second is not None and (second & 0xD000) == 0x9000:
            return (address + 4 + value,)                    # B.W T4
        imm = (((first & 0x400) << 9) | ((second & 0x0800) << 7)
               | ((second & 0x2000) << 3) | ((first & 0x3F) << 11)
               | ((second & 0x7FF) << 0))
        return (address + 4 + _sign_extend(imm, 21) * 2, following)
    if (first & 0xF800) == 0xE000:                           # B T2, unconditional
        return (target,)
    return (target, following)


def _meet(left, right):
    """Keep only what both paths agree on. `None` means "no path yet"."""
    if left is None:
        return dict(right)
    if right is None:
        return dict(left)
    return {name: value for name, value in left.items()
            if right.get(name) == value}


def _transfer(state, code, address, first, second, sink):
    """Apply one instruction. `sink` collects facts on the recording pass."""
    registers = dict(state)

    register, literal = _literal(address, first, second)
    if register is not None:
        if sink is not None:
            sink["loads"].setdefault(literal, []).append(address)
        registers[register] = (
            "word", literal, _word_at(code.data, code.base, literal))
        return registers

    is_store, source, base_register, offset = _reg_memory(first, second)
    if is_store is not None:
        # Installs are NOT recorded here. `_scan_function` records them from
        # the settled register states, alongside the liveness that says which
        # of them can actually reach a dispatch.
        if not is_store:
            obj = _as_object(registers.get(base_register))
            registers.pop(source, None)
            if obj is not None:
                registers[source] = ("field", obj, offset)
        return registers

    register, delta = _add_sub_immediate(first, second)
    if register is not None:
        held = registers.pop(register, None)
        known = (held[1] if held is not None and held[0] == "const" else
                 held[2] if held is not None and held[0] == "word" else None)
        if known is not None:
            registers[register] = ("const", (known + delta) & 0xFFFFFFFF)
        return registers

    if (first & 0xFF00) == 0x4600:                           # MOV (register) T1
        destination = (first & 7) | ((first & 0x80) >> 4)
        held = registers.get((first >> 3) & 0xF)
        registers.pop(destination, None)
        if held is not None:
            registers[destination] = held
        return registers

    if (first & 0xF800) == 0xA000:                           # ADR (T1)
        registers[(first >> 8) & 7] = (
            "const", ((address + 4) & ~3) + (first & 0xFF) * 4)
        return registers

    if (first & 0xF800) == 0x2000:                           # MOVS (imm) T1
        # Tagged "imm", not "const": a materialised small integer is never an
        # object base, however much it looks like one after an add.
        registers[(first >> 8) & 7] = ("imm", first & 0xFF)
        return registers

    if second is not None and (first & 0xFBEF) == 0xF04F:    # MOV.W (imm) T2
        registers.pop((second >> 8) & 0xF, None)
        return registers

    if (first & 0xF800) in (0x7000, 0x8000):                 # STRB/LDRB/STRH/LDRH
        if first & 0x0800:
            registers.pop(first & 7, None)
        return registers

    if ((first & 0xF800) == 0x2800                           # CMP (imm) T1
            or (first & 0xFF00) in (0x4200, 0x4280, 0x42C0)):
        return registers                                     # flags only

    if (first & 0xFF87) == 0x4780:                           # BLX (register)
        # Likewise: a dispatch only becomes a proof in `_scan_function`, and
        # only against installs that are live at this instruction.
        return _after_call(registers)

    if second is not None and (first & 0xF800) == 0xF000 and (
            second & 0xD000) == 0xD000:                      # BL / BLX (imm)
        return _after_call(registers)

    if first == 0xBF00:                                      # NOP
        return registers

    # A branch writes nothing. Anything else is killed by register when the
    # encoding names one, and drops the whole map when it does not.
    if branch_target(address, first, second) is not None:
        return registers
    killed = _killed(first, second)
    if killed is None:
        return {}
    for register in killed:
        registers.pop(register, None)
    return registers


def _memory_write(first, second):
    """(resolved, Rt, Rn, offset). `resolved` False means "writes somewhere".

    Only `STR Rt,[Rn,#imm]` is resolvable here. Every other memory write —
    byte, halfword, register-offset, stack, multiple — could land on a tracked
    field, and the install set drops entirely rather than reason about it.
    """
    if (first & 0xF800) == 0x6000:                            # STR (imm) T1
        return True, first & 7, (first >> 3) & 7, ((first >> 6) & 0x1F) * 4
    if (second is not None and (first & 0xFFF0) == 0xF8C0
            and (first & 0xF) != 0xF):                        # STR.W (imm) T3
        return True, (second >> 12) & 0xF, first & 0xF, second & 0xFFF
    if second is None:
        if (first & 0xF800) in (0x7000, 0x8000) and not (first & 0x0800):
            return False, None, None, None                    # STRB / STRH
        if (first & 0xF800) == 0x9000:
            return False, None, None, None                    # STR [SP,#imm]
        if (first & 0xF800) == 0x5000 and not (first & 0x0800):
            return False, None, None, None                    # STR register offset
        if (first & 0xF800) == 0xC000 or (first & 0xFE00) == 0xB400:
            return False, None, None, None                    # STM / PUSH
        return None, None, None, None
    if (first & 0xFF00) in (0xE880, 0xE900, 0xF800, 0xF820, 0xF840):
        return False, None, None, None                        # STM.W / STR.W reg
    return None, None, None, None


def _is_call(first, second):
    if (first & 0xFF87) == 0x4780:                            # BLX (register)
        return True
    return (second is not None and (first & 0xF800) == 0xF000
            and (second & 0xD000) == 0xD000)                  # BL / BLX (imm)


def _understood(address, first, second):
    """True when `_transfer` fully models this instruction's register effect.

    The install-liveness pass needs its own predicate: `_killed` is only the
    *fallback* `_transfer` reaches for encodings it does not handle explicitly,
    so using it alone would treat a plain `ldr` or `mov` as unknown and throw
    every live install away.
    """
    if _literal(address, first, second)[0] is not None:
        return True
    if _reg_memory(first, second)[0] is not None:
        return True
    if _add_sub_immediate(first, second)[0] is not None:
        return True
    if (first & 0xFF00) == 0x4600:                            # MOV (register) T1
        return True
    if (first & 0xF800) == 0xA000:                            # ADR (T1)
        return True
    if (first & 0xF800) == 0x2000:                            # MOVS (imm) T1
        return True
    if second is not None and (first & 0xFBEF) == 0xF04F:     # MOV.W (imm) T2
        return True
    if (first & 0xF800) in (0x7000, 0x8000):                  # byte / halfword
        return True
    if ((first & 0xF800) == 0x2800
            or (first & 0xFF00) in (0x4200, 0x4280, 0x42C0)):
        return True                                           # flags only
    if first == 0xBF00:                                       # NOP
        return True
    return _killed(first, second) is not None


# A function pointer occupies one 32-bit word.
INSTALL_WIDTH = 4


def effective_range(obj, field, width=INSTALL_WIDTH):
    """The concrete byte interval an (object, field) pair names, or None.

    Only an ABS identity has one. A MEM identity is "whatever the pointer read
    from this slot happened to be", which is not a static address, so it has no
    interval and every alias question about it answers "maybe".
    """
    kind, address = obj
    if kind == ABS:
        return (address + field, address + field + width)
    return None


def may_alias(left, left_field, right, right_field, width=INSTALL_WIDTH):
    """Could a word store at (right, right_field) touch (left, left_field)?

    Log 134. The previous rule invalidated an installation only when a later
    store used the SAME (object identity, field) pair, and two different
    abstract identities can name one physical word. The rules now are:

      1. ABS vs ABS — both intervals are concrete, so they alias exactly when
         the byte ranges OVERLAP. Overlap, not equality: `("abs",X)+4` and
         `("abs",X+4)+0` are the same word written two ways, and a partially
         overlapping unaligned store still corrupts the pointer.
      2. ABS vs MEM, either way round — a pointer read from a slot can point
         anywhere, including at that absolute object. MAY ALIAS.
      3. MEM vs MEM — two different slots can hold the same pointer, and the
         same slot certainly does. MAY ALIAS whether the slots match or not.

    Rules 2 and 3 together mean a MEM-derived installation survives no resolved
    store at all. That is deliberate: this interpreter cannot prove two runtime
    pointers distinct, and a false root is worse than a false negative. The
    real images have zero proven entries either way.
    """
    left_range = effective_range(left, left_field, width)
    right_range = effective_range(right, right_field, width)
    if left_range is None or right_range is None:
        return True
    return left_range[0] < right_range[1] and right_range[0] < left_range[1]


def slot_overwritten(install_obj, store_obj, store_field,
                     width=INSTALL_WIDTH):
    """Does this store rewrite the pointer slot a MEM identity was read from?

    Kept as its own rule although `may_alias` already invalidates every MEM
    installation on any resolved store: it is a different reason for a
    different fact, it is directly testable, and it stays correct if the alias
    rules are ever tightened.
    """
    if install_obj[0] != MEM:
        return False
    store_range = effective_range(store_obj, store_field, width)
    if store_range is None:
        return True
    slot = install_obj[1]
    return store_range[0] < slot + width and slot < store_range[1]


def _install_transfer(live, code, address, first, second, registers):
    """How one instruction changes the set of installs still in force.

    Fail-closed by default: anything that might write a tracked field, and
    anything that might replace the object a `("mem", A)` identity names,
    empties the set. A call empties it because the callee can do either.

    A resolved store invalidates every installation it MAY ALIAS — see
    `may_alias` and `slot_overwritten` — not merely the one recorded under the
    same abstract (object, field) pair. Two identities can name one word.
    """
    resolved, source, base_register, offset = _memory_write(first, second)
    if resolved is False:
        return frozenset()
    if resolved is True:
        obj = _as_object(registers.get(base_register))
        if obj is None:
            return frozenset()                    # could alias anything
        out = {record for record in live
               if not may_alias(record.obj, record.field, obj, offset)
               and not slot_overwritten(record.obj, obj, offset)}
        held = registers.get(source)
        if held is not None and held[0] == "word":
            out.add(Proof(held[1], address, 0, 0, obj, offset))
        return frozenset(out)
    if _is_call(first, second):
        return frozenset()
    if branch_target(address, first, second) is not None:
        return live
    if not _understood(address, first, second):
        return frozenset()                        # unrecognised: could store
    return live


def _scan_function(code, ranges, function_entry, sink):
    """One function. Returns a refusal reason, or None.

    Two fixed points, in order:

      1. register state — a MUST analysis, so a join keeps only what every
         predecessor agrees on. This settles object identities.
      2. live installs — a MAY analysis over the SAME control-flow graph, so a
         join keeps the union: an install is live at an instruction when it
         reaches it along at least one path. Run second, against the finished
         register states, so a transiently richer register map cannot leave a
         stale install behind.

    A dispatch is credited only against installs live at that instruction. Two
    mutually exclusive branches therefore cannot combine into a proof, because
    the install never reaches the dispatch on any path.
    """
    stream = list(_decode(code.data, code.base, ranges))
    if not stream:
        return "has no decodable body"
    index = {address: position
             for position, (address, _f, _s, _w) in enumerate(stream)}
    successors = []
    for address, first, second, width in stream:
        following = _successors(address, first, second, width, index)
        if following is None:
            return (f"contains a flow instruction at 0x{address:08x} whose "
                    "successors cannot be enumerated")
        successors.append(tuple(index[target] for target in following
                                if target in index))

    entries = {index[low] for low, _high in ranges}

    registers = [None] * len(stream)
    for position in entries:
        registers[position] = {}
    pending = sorted(entries)
    guard = 0
    limit = 200 * len(stream) + 1000
    while pending:
        guard += 1
        if guard > limit:
            return "register states did not reach a fixed point"
        position = pending.pop()
        address, first, second, _width = stream[position]
        out = _transfer(registers[position] or {}, code, address, first,
                        second, None)
        for successor in successors[position]:
            merged = _meet(registers[successor], out)
            if registers[successor] is None or merged != registers[successor]:
                registers[successor] = merged
                pending.append(successor)

    live = [frozenset() for _ in stream]
    # Every instruction is queued once. The empty set is the initial value AND
    # a possible fixed point, so seeding only the entries would converge before
    # a single install had been propagated anywhere.
    pending = list(range(len(stream)))
    guard = 0
    while pending:
        guard += 1
        if guard > limit:
            return "install liveness did not reach a fixed point"
        position = pending.pop()
        address, first, second, _width = stream[position]
        out = _install_transfer(live[position], code, address, first, second,
                                registers[position] or {})
        for successor in successors[position]:
            merged = live[successor] | out
            if merged != live[successor]:
                live[successor] = merged
                pending.append(successor)

    for position, (address, first, second, _width) in enumerate(stream):
        state = registers[position] or {}
        _transfer(state, code, address, first, second, sink)
        resolved, source, base_register, offset = _memory_write(first, second)
        if resolved is True:
            obj = _as_object(state.get(base_register))
            held = state.get(source)
            if obj is not None and held is not None and held[0] == "word":
                sink["installs"].setdefault(held[1], []).append(
                    (address, obj, offset))
        if (first & 0xFF87) == 0x4780:                        # BLX (register)
            held = state.get((first >> 3) & 0xF)
            if held is None or held[0] != "field" or held[1] is None:
                continue
            obj, field = held[1], held[2]
            for record in sorted(live[position],
                                 key=lambda item: (item.entry, item.install)):
                if record.obj == obj and record.field == field:
                    sink["proofs"].setdefault(record.entry, []).append(
                        Proof(record.entry, record.install, address,
                              function_entry, obj, field))
    return None


def consumption(code):
    """Per-function data flow. Nothing crosses a function boundary."""
    if code is None:
        return Consumption.empty()
    loads, installs, proofs, skipped = {}, {}, {}, []
    for entry, ranges in code.functions:
        sink = {"loads": {}, "installs": {}, "proofs": {}}
        reason = _scan_function(code, ranges, entry, sink)
        if reason is not None:
            skipped.append((entry, reason))
            continue
        for literal, sites in sink["loads"].items():
            loads.setdefault(literal, []).extend(
                (entry, site) for site in sorted(set(sites)))
        for literal, records in sink["installs"].items():
            installs.setdefault(literal, []).extend(
                (entry, site, obj, field)
                for site, obj, field in sorted(set(records)))
        for literal, records in sink["proofs"].items():
            proofs.setdefault(literal, []).extend(sorted(set(records),
                                                        key=lambda r: r.install))
    return Consumption(
        {address: tuple(sites) for address, sites in loads.items()},
        {address: tuple(records) for address, records in installs.items()},
        {address: tuple(records) for address, records in proofs.items()},
        tuple(sorted(skipped)))


# ------------------------------------------------------------------- tables

@dataclass(frozen=True)
class Table:
    """A run of Thumb pointers at a constant stride, with its verdict.

    The four evidence buckets are kept apart on purpose. `loaded` is the
    weakest — an instruction reads the word. `installed` adds the identity of
    the object the word is written into. `proven` is the subset whose install
    reaches an indirect call on that same object's same field along a path
    inside one function, with nothing that may alias the field in between.
    `rooted` is exactly the (entry, target) pairs of `proven`: there is no
    whole-table promotion, because storing words together does not make them
    all callable.
    """
    location: int
    stride: int
    entries: tuple
    verdict: str = CANDIDATE
    reason: str = "not assessed"
    loaded: tuple = ()
    installed: tuple = ()
    proven: tuple = ()      # entry addresses with at least one Proof
    proofs: tuple = ()      # the Proof records themselves
    rooted: tuple = ()      # ((entry address, target), ...) — one per proven

    @property
    def count(self):
        return len(self.entries)

    @property
    def end(self):
        return self.location + self.stride * (self.count - 1) + 4

    @property
    def targets(self):
        return tuple(target for _address, target in self.entries)

    @property
    def rooted_targets(self):
        return tuple(target for _entry, target in self.rooted)

    def target_of(self, address):
        for entry, target in self.entries:
            if entry == address:
                return target
        return None


@dataclass(frozen=True)
class Survey:
    program: str
    slice_name: str
    base: int
    size: int
    sha256: str
    tables: tuple
    known_targets: tuple
    new_targets: tuple
    loose_candidates: tuple
    skipped_functions: tuple = ()

    @property
    def validated(self):
        return tuple(t for t in self.tables if t.verdict == VALIDATED)

    @property
    def root_targets(self):
        return tuple(sorted({target for table in self.tables
                             for target in table.rooted_targets}))


def candidates(data, base, excluded, code_floor, code_ceil=None):
    """Offsets holding a plausible Thumb pointer into this image's code."""
    if code_ceil is None:
        code_ceil = base + len(data)
    found = {}
    for offset in range(0, len(data) - 3, 4):
        address = base + offset
        if any(low <= address < high for low, high in excluded):
            continue
        word, = struct.unpack_from("<I", data, offset)
        target = word & ~1
        if not word & 1:
            continue
        # No alignment test here: clearing bit 0 always yields an even address,
        # so a "reject odd targets" branch would be dead code.
        if not code_floor <= target < code_ceil:
            continue
        found[address] = target
    return found


def find_tables(found):
    """Group candidates into constant-stride runs, longest stride-4 runs first."""
    tables = []
    claimed = set()
    for stride in STRIDES:
        for address in sorted(found):
            if address in claimed:
                continue
            run = []
            cursor = address
            while cursor in found and cursor not in claimed:
                run.append((cursor, found[cursor]))
                cursor += stride
            if len(run) < MIN_ENTRIES:
                continue
            tables.append(Table(address, stride, tuple(run)))
            claimed.update(item[0] for item in run)
    return tuple(sorted(tables, key=lambda table: table.location)), claimed


def printable_fraction(data, base, low, high):
    """How much of `low..high` is text. A format-string block scores ~1.0."""
    start, stop = low - base, high - base
    span = data[max(0, start):min(len(data), stop)]
    if not span:
        return 0.0
    return sum(1 for byte in span if byte in _PRINTABLE) / len(span)


def assess(table, data, base, consumed):
    """Give a run its verdict, and say exactly how much was proven.

    There is deliberately NO whole-table promotion. "All these words were
    stored into one object and one of its fields is called" does not make the
    other fields callable — they can be data, flags, counts or callbacks
    nothing ever dispatches. Only an entry with its own install-to-dispatch
    proof is rooted, so `len(rooted) == len(proven)` always.
    """
    text = printable_fraction(data, base, table.location, table.end)
    if text >= PRINTABLE_FRACTION:
        return replace(
            table, verdict=REJECTED,
            reason=(f"string/data: {text:.0%} of the span is printable text, "
                    "so the repeated word is a terminator inside a "
                    "format-string block, not a pointer"))
    loaded = tuple(address for address, _target in table.entries
                   if consumed.loads.get(address))
    installed = tuple(
        (function, instruction, obj, field)
        for address, _target in table.entries
        for function, instruction, obj, field
        in consumed.installs.get(address, ()))
    installed_entries = tuple(
        address for address, _target in table.entries
        if consumed.installs.get(address))
    proofs = tuple(proof for address, _target in table.entries
                   for proof in consumed.proven(address))
    proven = tuple(address for address, _target in table.entries
                   if consumed.proven(address))
    rooted = tuple((address, table.target_of(address)) for address in proven)
    if not loaded:
        return replace(table, verdict=CANDIDATE,
                       reason="no consumer: no instruction in any analysed "
                              "function body loads any entry of this run")
    if not proven:
        return replace(
            table, verdict=CANDIDATE, loaded=loaded, installed=installed,
            reason=(f"{len(loaded)} of {table.count} entries are loaded and "
                    f"{len(installed_entries)} are installed into an object "
                    "field, but no install reaches an indirect call through "
                    "the same object's same field on any path inside one "
                    "function, so nothing here is a root"))
    return replace(
        table, verdict=VALIDATED, loaded=loaded, installed=installed,
        proven=proven, proofs=proofs, rooted=rooted,
        reason=(f"{len(proven)} of {table.count} entries are individually "
                f"path-proven and are the only ones rooted; the other "
                f"{table.count - len(proven)} are NOT rooted and nothing here "
                "asserts that they are callable"))


def survey(program, slice_name, base, data, known, code=None):
    excluded = EXCLUDE.get(program, ())
    found = candidates(data, base, excluded, CODE_FLOOR[program],
                       CODE_CEIL.get(program))
    raw, claimed = find_tables(found)
    consumed = consumption(code)
    tables = tuple(assess(table, data, base, consumed) for table in raw)
    targets = {target for table in tables
               for target in table.rooted_targets}
    return Survey(
        program=program, slice_name=slice_name, base=base, size=len(data),
        sha256=ex.sha256(data), tables=tables,
        known_targets=tuple(sorted(targets & known)),
        new_targets=tuple(sorted(targets - known)),
        loose_candidates=tuple(sorted(
            (address, target) for address, target in found.items()
            if address not in claimed)),
        skipped_functions=consumed.skipped)


def load(view, inventory_name, program, import_base):
    extraction = ex.extract(view)
    item, = [entry for entry in extraction.slices
             if entry.import_base == import_base]
    data = (IMPORTS / item.name).read_bytes()
    records, _header = mf.parse_inventory(
        (INVENTORIES / inventory_name).read_text())
    known = {record.entry for record in records}
    return survey(program, item.name, import_base, data, known,
                  Code.from_records(data, import_base, records))


def reconstructed(view, inventory_name):
    """Survey the decompressed scatter region, if it has been reconstructed.

    Ghidra cannot see this region at all: it exists only after the boot-time
    decompress, so a callback stored in it is invisible to every flash-only
    survey. The instruction stream it is judged against is the *application's*,
    because the region holds no code of its own. Returns None when the region
    has not been written, so the two flash surveys behave exactly as they did
    before this was added.
    """
    result, payload = rd.reconstruct(view, "installed"
                                     if view.base == 0x10000 else "vendor")
    path = IMPORTS / result.name
    if not path.exists():
        return None
    records, _header = mf.parse_inventory(
        (INVENTORIES / inventory_name).read_text())
    known = {record.entry for record in records}
    application = next(
        entry for entry in ex.extract(view).slices
        if entry.import_base == 0x18000000)
    code_bytes = (IMPORTS / application.name).read_bytes()
    return survey("ram", result.name, result.destination, path.read_bytes(),
                  known, Code.from_records(code_bytes, 0x18000000, records))


def build(image=INSTALLED, base=0x10000, tag="installed"):
    view = fi.ImageView(Path(image).read_bytes(), base)
    surveys = [load(view, f"{tag}_a.txt", "entry", 0x0),
               load(view, f"{tag}_b.txt", "app", 0x18000000)]
    region = reconstructed(view, f"{tag}_b.txt")
    if region is not None:
        surveys.append(region)
    return tuple(surveys)


def seed_arguments(survey_result):
    """`Name=0xaddr` pairs for FalchionSeedVectors.java.

    Only targets of a VALIDATED table. Seeding a candidate would create the
    function that the next run would then cite as evidence the candidate was
    real — the exact circularity log 131 unwound.
    """
    return tuple(f"PtrTarget_{target:08x}=0x{target:x}"
                 for target in survey_result.new_targets)


def _object_text(obj):
    kind, address = obj
    return (f"object@0x{address:08x}" if kind == ABS
            else f"object*@0x{address:08x}")


def to_dict(surveys):
    return {
        "code_ceilings": {name: value for name, value in CODE_CEIL.items()},
        "code_floors": {name: value for name, value in CODE_FLOOR.items()},
        "min_entries": MIN_ENTRIES,
        "printable_fraction": PRINTABLE_FRACTION,
        "strides": list(STRIDES),
        "surveys": [
            {
                "base": item.base,
                "known_targets": list(item.known_targets),
                "loose_candidates": [{"address": address, "target": target}
                                     for address, target in item.loose_candidates],
                "new_targets": list(item.new_targets),
                "program": item.program,
                "root_targets": list(item.root_targets),
                "seed_arguments": list(seed_arguments(item)),
                "sha256": item.sha256,
                "size": item.size,
                "skipped_functions": [
                    {"function": entry, "reason": reason}
                    for entry, reason in item.skipped_functions],
                "slice": item.slice_name,
                "tables": [
                    {"count": table.count, "end": table.end,
                     "entries": [{"address": address, "target": target}
                                 for address, target in table.entries],
                     "installed": [
                         {"field": field, "function": function,
                          "instruction": instruction,
                          "object": _object_text(obj)}
                         for function, instruction, obj, field
                         in table.installed],
                     "loaded": list(table.loaded),
                     "location": table.location,
                     "proofs": [
                         {"dispatch": proof.dispatch, "entry": proof.entry,
                          "field": proof.field, "function": proof.function,
                          "install": proof.install,
                          "object": _object_text(proof.obj),
                          "path": proof.text()}
                         for proof in table.proofs],
                     "proven": list(table.proven),
                     "reason": table.reason,
                     "rooted": [{"entry": entry, "target": target}
                                for entry, target in table.rooted],
                     "stride": table.stride,
                     "verdict": table.verdict}
                    for table in item.tables
                ],
            }
            for item in surveys
        ],
    }


def report_lines(surveys):
    out = [
        "PROGRAM find_pointer_tables",
        "PURPOSE locate function-pointer tables so their targets can be seeded",
        f"RULE shape first: a run of at least {MIN_ENTRIES} Thumb pointers at a "
        f"constant stride from {STRIDES}, each targeting an even address at or "
        "above the image's first code address. A lone word that looks like a "
        "pointer is not reported as a table.",
        "RULE evidence second, in four separate buckets. LOADED: an instruction "
        "in an analysed function body performs a PC-relative literal load of "
        "the entry. INSTALLED: that value is stored into a named object's "
        "field. PROVEN: the install reaches an `ldr rX,[rY,#off]; blx rX` on "
        "that same object's same field along a CFG path inside the SAME "
        "function, with no intervening call and no overwrite of the field or "
        "of the slot the object's pointer came from. ROOTED: exactly the "
        "proven entries. There is no whole-table promotion: storing words "
        "together does not make them all callable.",
        "RULE a run that is mostly printable text is REJECTED as string/data "
        "before any of that is considered.",
        "RULE the scanner analyses one function at a time from an empty "
        "register map, restarts at every branch target, and drops everything at "
        "a branch, a call or an instruction it does not recognise. A function "
        "containing a flow instruction whose successors cannot be enumerated is "
        "not analysed at all and is listed as skipped. Offsets are never "
        "matched across different objects.",
    ]
    for item in surveys:
        out += [
            "",
            f"IMAGE {item.program} base=0x{item.base:08x} "
            f"size=0x{item.size:x} code_floor=0x{CODE_FLOOR[item.program]:x}",
            f"  slice={item.slice_name}",
            f"  sha256={item.sha256}",
            f"  runs={len(item.tables)} validated={len(item.validated)} "
            f"entries={sum(table.count for table in item.tables)} "
            f"known_targets={len(item.known_targets)} "
            f"new_targets={len(item.new_targets)} "
            f"loose_candidates={len(item.loose_candidates)} "
            f"skipped_functions={len(item.skipped_functions)}",
        ]
        if EXCLUDE.get(item.program):
            out.append("  excluded=" + ", ".join(
                f"0x{low:x}..0x{high:x}"
                for low, high in EXCLUDE[item.program])
                + " (decoded and seeded separately)")
        for table in item.tables:
            out.append(f"  {table.verdict.upper()} "
                       f"0x{table.location:08x}..0x{table.end:08x} "
                       f"stride={table.stride} entries={table.count}")
            out.append(f"    EVIDENCE loaded={len(table.loaded)}/{table.count} "
                       f"installed={len(set(record[1] for record in table.installed))}"
                       f"/{table.count} proven={len(table.proven)}/{table.count} "
                       f"rooted={len(table.rooted)}/{table.count}")
            out.append(f"    because {table.reason}")
            for address, target in table.entries:
                marker = " ROOTED" if any(entry == address
                                          for entry, _t in table.rooted) else ""
                out.append(f"    0x{address:08x} -> 0x{target:08x}{marker}")
            for function, instruction, obj, field in table.installed:
                out.append(f"    INSTALL 0x{instruction:08x} in "
                           f"FUN_{function:08x} -> {_object_text(obj)}"
                           f"+0x{field:x}")
            for proof in table.proofs:
                out.append(f"    PROOF 0x{proof.entry:08x} {proof.text()}")
        if item.new_targets:
            out.append("  NEW_TARGETS " + ", ".join(
                f"0x{target:08x}" for target in item.new_targets))
        for address, target in item.loose_candidates:
            out.append(f"  LOOSE 0x{address:08x} -> 0x{target:08x} "
                       "(not part of any run; not reported as a table entry)")
        for entry, reason in item.skipped_functions:
            out.append(f"  SKIPPED FUN_{entry:08x} {reason}")
    out += [
        "",
        f"RESULT runs={sum(len(item.tables) for item in surveys)} "
        f"validated={sum(len(item.validated) for item in surveys)} "
        f"rooted={sum(len(item.root_targets) for item in surveys)} "
        f"new_targets={sum(len(item.new_targets) for item in surveys)}",
        "LIMITATION A target here is a candidate, not a proven function. Whether "
        "it is code is settled by whether Ghidra disassembles a function at it.",
        "LIMITATION Only tables present in the surveyed slices are visible. The "
        "decompressed region is now surveyed as well, but a callback written "
        "into RAM at runtime, by code rather than by an initialiser, still "
        "cannot appear here.",
        "LIMITATION The scanner cannot follow an object across a call boundary. "
        "An operations struct built in one function and dispatched in another, "
        "with the pointer passed as an argument, reads here as installed but "
        "not proven — which keeps it a candidate. Ghidra decompiler P-code "
        "could follow that flow; this scanner is not a substitute for it, and "
        "no interprocedural proof is implemented or claimed.",
        "LIMITATION A proof says a CFG path exists from the install to the "
        "dispatch. Branch conditions are not modelled, so feasibility of that "
        "path is not established. It is also not proof that the dispatch "
        "always happens, only that it can.",
    ]
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--seed-args", choices=("entry", "app", "ram"),
                        help="print only the seed arguments for one image")
    parser.add_argument("--vendor", action="store_true",
                        help="survey the vendor image instead")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.vendor:
            surveys = build(VENDOR, 0x0, "vendor")
        else:
            surveys = build()
    except (OSError, ValueError, fi.ImageFormatError, ex.ExtractError) as exc:
        print(f"RESULT runs=0 error={exc}")
        return 1
    if args.seed_args:
        item, = [entry for entry in surveys if entry.program == args.seed_args]
        print(" ".join(seed_arguments(item)))
        return 0
    if args.json:
        print(json.dumps(to_dict(surveys), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(surveys)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
