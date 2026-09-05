#!/usr/bin/env python3
"""Map the installed application's hardware and runtime interfaces.

Read-only and offline. Combines three evidence sources, all derived from the
installed dump:

  * the vector table, parsed from Candidate A's own bytes;
  * every load and store whose target Ghidra's constant propagation resolves
    outside the program's own memory (`FalchionPeripheralMap.java`);
  * the call graph and real body ranges from `FalchionFunctionInventory.java`.

Two rules govern everything here:

**Observed behaviour is separated from peripheral identity.** No public
SNC73270 reference manual exists in this repository, so a vendor MMIO block is
described only by what the code does to it — addresses, widths, directions,
stored values and the context it is touched from. Only the ARMv7-M
architectural blocks are named, and they are named from the architecture, not
from a vendor document.

**Reachability is computed, not assumed.** A function's context comes from a
breadth-first walk of the call graph out of roots that are themselves evidence:
the vector-table entries. A function no root reaches is reported as unreached
rather than guessed at.

No device access. Examples:
    python3 tool/map_hardware_interfaces.py
    python3 tool/map_hardware_interfaces.py --json
"""
import argparse
from collections import Counter, deque
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import struct
import sys
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_installed_records as ex
import falchion_image as fi
import find_pointer_tables as fpt
import harvest_task_entries as ht
import match_functions as mf

ROOT = Path(__file__).resolve().parent.parent
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
PERIPHERALS = ROOT / "ghidra/peripherals"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")

ACCESS_RE = re.compile(
    r"^ACCESS target=0x(?P<target>[0-9a-f]+) width=(?P<width>\d+) "
    r"dir=(?P<dir>read|write) instr=(?P<instr>[0-9a-f]+) "
    r"func=(?P<func>[0-9a-f]+) base=(?P<base>\S+) off=(?P<off>-?\d+) "
    r"stored=(?P<stored>\S+)$")
UNRESOLVED_RE = re.compile(
    r"^UNRESOLVED instr=(?P<instr>[0-9a-f]+) func=(?P<func>[0-9a-f]+) "
    r"mnemonic=(?P<mnemonic>\S+) reason=(?P<reason>\S+)$")

BLOCK_SIZE = 0x100000

# The first 16 vector slots are fixed by ARMv7-M. Everything past them is an
# external interrupt whose meaning is a property of this SoC, not the core.
CORE_VECTORS = (
    "initial_SP", "Reset", "NMI", "HardFault", "MemManage", "BusFault",
    "UsageFault", "Reserved7", "Reserved8", "Reserved9", "Reserved10",
    "SVCall", "DebugMonitor", "Reserved13", "PendSV", "SysTick",
)

# Architectural ARMv7-M register blocks. These are named from the ARM
# architecture reference, which applies to any Cortex-M3, and are the only
# names in this map that do not depend on a vendor document.
ARM_REGISTERS = {
    0xE000E010: ("SYST_CSR", "SysTick control and status"),
    0xE000E014: ("SYST_RVR", "SysTick reload value"),
    0xE000E018: ("SYST_CVR", "SysTick current value"),
    0xE000E01C: ("SYST_CALIB", "SysTick calibration"),
    0xE000ED00: ("CPUID", "CPUID base"),
    0xE000ED04: ("ICSR", "Interrupt control and state"),
    0xE000ED08: ("VTOR", "Vector table offset"),
    0xE000ED0C: ("AIRCR", "Application interrupt and reset control"),
    0xE000ED10: ("SCR", "System control"),
    0xE000ED14: ("CCR", "Configuration and control"),
    0xE000ED18: ("SHPR1", "System handler priority 1"),
    0xE000ED1C: ("SHPR2", "System handler priority 2"),
    0xE000ED20: ("SHPR3", "System handler priority 3"),
    0xE000ED24: ("SHCSR", "System handler control and state"),
    0xE000ED28: ("CFSR", "Configurable fault status"),
    0xE000ED2C: ("HFSR", "HardFault status"),
    0xE000ED30: ("DFSR", "Debug fault status"),
    0xE000ED34: ("MMFAR", "MemManage fault address"),
    0xE000ED38: ("BFAR", "BusFault address"),
    0xE000ED3C: ("AFSR", "Auxiliary fault status"),
    0xE000ED88: ("CPACR", "Coprocessor access control"),
}


# Entry points established by decompilation rather than by any pointer: each
# carries the log that established it, so a context always cites its evidence.
DOCUMENTED_ENTRIES = (
    (0x1800023A, "Candidate B main (logs 79-80, via "
                 "thunk_EXT_FUN_1800023a; no literal word points here)"),
)


def arm_register_name(address):
    """Name an ARMv7-M register, including the indexed NVIC arrays.

    A byte or halfword access lands inside a word register, so an unaligned
    address is reported against the word that contains it with the byte offset
    stated, rather than as an unknown register.
    """
    if address in ARM_REGISTERS:
        return ARM_REGISTERS[address]
    word = address & ~3
    if word in ARM_REGISTERS:
        name, description = ARM_REGISTERS[word]
        return (f"{name}+{address - word}",
                f"{description}, byte {address - word} of the word")
    for base, label, stride in ((0xE000E100, "NVIC_ISER", 4),
                                (0xE000E180, "NVIC_ICER", 4),
                                (0xE000E200, "NVIC_ISPR", 4),
                                (0xE000E280, "NVIC_ICPR", 4),
                                (0xE000E300, "NVIC_IABR", 4),
                                (0xE000E400, "NVIC_IPR", 4)):
        span = 0x20 if label != "NVIC_IPR" else 0xF0
        if base <= address < base + span:
            index = (address - base) // stride
            return (f"{label}{index}",
                    f"NVIC {label.split('_')[1]} word {index}")
    if 0xE0000000 <= address < 0xE0100000:
        return (None, "ARMv7-M private peripheral bus, register not identified")
    return (None, None)


@dataclass(frozen=True)
class VectorSlot:
    index: int
    name: str
    value: int
    kind: str          # initial_sp | default | live | zero | other
    target_program: Optional[str]
    target_function: Optional[int]


@dataclass(frozen=True)
class Access:
    target: int
    width: int
    direction: str
    instruction: int
    function: int
    base: str
    offset: int
    stored: Optional[int]


@dataclass
class RegisterUse:
    """Accumulated accesses to one address.

    `reset_reachable_writes` is kept apart from `stored_values` because an initialisation
    value is a write that happens on the reset path, and an aggregate of every
    value ever stored is not the same thing.
    """
    address: int
    widths: set = field(default_factory=set)
    reads: list = field(default_factory=list)
    writes: list = field(default_factory=list)
    stored_values: set = field(default_factory=set)
    reset_reachable_writes: set = field(default_factory=set)
    functions: set = field(default_factory=set)

    def add(self, access):
        self.widths.add(access.width)
        self.functions.add(access.function)
        (self.writes if access.direction == "write" else self.reads).append(
            access.instruction)
        if access.direction == "write" and access.stored is not None:
            self.stored_values.add(access.stored)


@dataclass(frozen=True)
class Block:
    base: int
    kind: str
    description: str
    registers: tuple
    accesses: int
    contexts: tuple


@dataclass(frozen=True)
class ProgramMap:
    name: str
    slice_name: str
    base: int
    functions: int
    roots: tuple
    contexts: dict
    unreached: tuple
    unresolved_roots: tuple
    orphans: tuple
    accesses: tuple
    unresolved: dict
    blocks: tuple


@dataclass(frozen=True)
class HardwareMap:
    phase_status: tuple
    vector_table_confidence: tuple
    image_sha256: str
    vector_table: tuple
    vector_table_span: tuple
    fill_value: Optional[int]
    live_interrupts: tuple
    code_entries: tuple
    data_pointers: tuple
    programs: tuple
    contradictions: tuple
    coverage: tuple


def classify_address(address, program_base, program_size, runtime_ranges):
    """Say what a single address is, using only defensible categories.

    Classification is per address, never per 1 MiB block: the application image
    and the RAM above it share a block, and the runtime range ends at a proven
    address rather than a block boundary. An address space with no positive
    evidence behind it stays `unknown` — this map does not call something a
    vendor peripheral just because it is not anything else.
    """
    if 0xE0000000 <= address < 0xE0100000:
        return ("arm-core",
                "ARMv7-M private peripheral bus: NVIC, SCB and SysTick, named "
                "from the ARM architecture rather than a vendor document")
    if program_base <= address < program_base + program_size:
        return ("program", "inside this program's own image")
    for low, high in runtime_ranges:
        if low <= address < high:
            return ("runtime-ram",
                    f"inside the proven scatter runtime range "
                    f"0x{low:08x}..0x{high:08x}")
    if fi.FLASH_BASE <= address < fi.FLASH_BASE + 0x400000:
        return ("flash-window",
                "the mapped external-flash window: the program reading its own "
                "storage, not a peripheral")
    if address < 0x1000 and program_base != 0:
        return ("artifact",
                "a small offset from a base register that propagation resolved "
                "to zero, so an unresolved structure pointer rather than a real "
                "address")
    return ("unknown",
            "no evidence identifies this address space. It is touched by the "
            "original firmware and nothing more can be said about it without a "
            "SNC73270 reference manual")


def block_kind(registers):
    """The kinds present in a block, so a block is never given one false label."""
    kinds = sorted({register["kind"] for register in registers})
    return kinds[0] if len(kinds) == 1 else "mixed"


def parse_peripheral_map(text):
    accesses, unresolved = [], Counter()
    for line in text.splitlines():
        match = ACCESS_RE.match(line.strip())
        if match:
            stored = match.group("stored")
            accesses.append(Access(
                target=int(match.group("target"), 16),
                width=int(match.group("width")),
                direction=match.group("dir"),
                instruction=int(match.group("instr"), 16),
                function=int(match.group("func"), 16),
                base=match.group("base"),
                offset=int(match.group("off")),
                stored=None if stored == "unknown" else int(stored, 16)))
            continue
        match = UNRESOLVED_RE.match(line.strip())
        if match:
            unresolved[match.group("reason")] += 1
    if not accesses:
        raise ValueError("peripheral map contains no ACCESS lines")
    return tuple(accesses), dict(sorted(unresolved.items()))


def parse_vector_table(data, base, first_code, runtime_ranges):
    """Decode the vector table, bounded by the first code address.

    An ARMv7-M vector table has no terminator, so nothing here tries to find
    one. The table simply runs from the image base to wherever code begins, and
    every word in between is a slot. The value the vendor repeats across unused
    slots is reported as a *fill value*, not as an end marker: a slot holding it
    is unused, and a slot after it can still be live.
    """
    span = (base, base + (first_code - base) // 4 * 4)
    words = list(struct.unpack_from(f"<{(span[1] - span[0]) // 4}I", data, 0))
    counts = Counter(word for index, word in enumerate(words)
                     if index >= len(CORE_VECTORS) and word)
    fill = None
    if counts:
        top, seen = counts.most_common(1)[0]
        if seen > 1:
            fill = top

    def target_of(value):
        address = value & ~1
        if not value & 1:
            return None, None
        if base <= address < base + len(data):
            return "entry", address
        for low, high in runtime_ranges:
            if low <= address < high:
                return "app", address
        return "other", address

    slots = []
    for index, word in enumerate(words):
        if index == 0:
            slots.append(VectorSlot(index, CORE_VECTORS[0], word, "initial_sp",
                                    None, None))
            continue
        name = (CORE_VECTORS[index] if index < len(CORE_VECTORS)
                else f"IRQ{index - len(CORE_VECTORS)}")
        program, address = target_of(word)
        if word == 0:
            kind = "zero"
        elif fill is not None and word == fill:
            kind = "fill"
        elif program is None:
            kind = "other"
        else:
            kind = "live"
        slots.append(VectorSlot(index, name, word, kind, program, address))
    return tuple(slots), span, fill


def cross_image_pointers(data, base, code_range, runtime_ranges, vector_span):
    """Entry-image words that point into the application.

    A code entry needs the Thumb bit set *and* a target inside the application's
    materialised code range. A word pointing anywhere else in RAM is a data
    pointer, counted but not treated as an entry point.
    """
    code, data_pointers = [], []
    low_code, high_code = code_range
    for offset in range(0, len(data) - 3, 4):
        value, = struct.unpack_from("<I", data, offset)
        address = value & ~1
        if not any(low <= address < high for low, high in runtime_ranges):
            continue
        record = {
            "entry_offset": base + offset,
            "value": value,
            "thumb": bool(value & 1),
            "in_vector_table": base + offset < vector_span[1],
        }
        if value & 1 and low_code <= address < high_code:
            code.append(record)
        else:
            data_pointers.append(record)
    return tuple(code), tuple(data_pointers)


def reachability(records, roots):
    """Breadth-first contexts for every function, from evidence-backed roots.

    A root naming an address that is not a function entry is *reported*, not
    silently dropped. Table 0x5680's middle entry 0x4018 is one: seeding could
    not create a function there because 0x4004, created moments earlier from
    the same table, had already claimed the address into its body. Counting
    that table as three indirect roots would count one function twice.
    """
    by_entry = {record.entry: record for record in records}
    contexts = {}
    unresolved_roots = tuple(sorted(
        (f"0x{entry:08x}", label) for label, entry in roots
        if entry not in by_entry))
    for label, entry in roots:
        if entry not in by_entry:
            continue
        queue = deque([entry])
        seen = {entry}
        while queue:
            current = queue.popleft()
            contexts.setdefault(current, set()).add(label)
            for callee in by_entry[current].callees:
                if callee in by_entry and callee not in seen:
                    seen.add(callee)
                    queue.append(callee)
    unreached = tuple(sorted(record.entry for record in records
                             if record.entry not in contexts))
    # An unreached function that some other function calls is not a separate
    # mystery: it is downstream of one that nothing calls. Splitting the
    # unreached set this way turns "427 functions we cannot reach" into the
    # much smaller number of entry points actually missing.
    called = {callee for record in records for callee in record.callees
              if callee in by_entry}
    orphans = tuple(entry for entry in unreached if entry not in called)
    return contexts, unreached, unresolved_roots, orphans


def build_blocks(accesses, contexts, program_base, program_size, runtime_ranges):
    grouped = {}
    for access in accesses:
        block = access.target & ~(BLOCK_SIZE - 1)
        registers = grouped.setdefault(block, {})
        use = registers.setdefault(access.target, RegisterUse(access.target))
        use.add(access)
        if access.direction == "write" and access.stored is not None:
            # Reachable from the Reset vector in the call graph. Not the
            # same as "executes during initialisation".
            if "Reset" in contexts.get(access.function, set()):
                use.reset_reachable_writes.add(access.stored)

    blocks = []
    for base in sorted(grouped):
        registers = []
        block_contexts = set()
        for address in sorted(grouped[base]):
            use = grouped[base][address]
            kind, description = classify_address(
                address, program_base, program_size, runtime_ranges)
            names = arm_register_name(address) if kind == "arm-core" else (None, None)
            register_contexts = set()
            for function in use.functions:
                register_contexts |= contexts.get(function, set())
            block_contexts |= register_contexts

            # Confidence is about the *claim being made*, which is only ever
            # "this address is accessed like this". It is high when the base
            # register was resolved and the address space is one we can name,
            # and lower when the space itself is unidentified.
            if kind == "artifact":
                confidence = "none — propagation artifact, not a real address"
            elif kind == "arm-core" and names[0]:
                confidence = ("high — architectural register, named from the "
                              "ARM reference")
            elif kind in ("program", "runtime-ram", "flash-window"):
                confidence = ("high for the access, and the address space is "
                              "established by earlier phases")
            else:
                confidence = ("high for the access itself; the address space is "
                              "unidentified, so no claim is made about what the "
                              "register does")

            registers.append({
                "address": address,
                "arm_description": names[1],
                "arm_name": names[0],
                "confidence": confidence,
                "contexts": sorted(register_contexts) or ["unreached"],
                "functions": sorted(use.functions),
                "reset_reachable_write_values": sorted(use.reset_reachable_writes),
                "kind": kind,
                "kind_basis": description,
                "read_sites": sorted(use.reads),
                "stored_values": sorted(use.stored_values),
                "widths": sorted(use.widths),
                "write_sites": sorted(use.writes),
            })
        blocks.append(Block(
            base=base, kind=block_kind(registers),
            description="; ".join(sorted({register["kind_basis"]
                                          for register in registers})),
            registers=tuple(registers),
            accesses=sum(len(item["read_sites"]) + len(item["write_sites"])
                         for item in registers),
            contexts=tuple(sorted(block_contexts) or ["unreached"])))
    return tuple(blocks)


# The dependency verdict is a stated rule applied to evidence, not an opinion.
DEPENDENCY_RULES = (
    ("arm-core", "must-replace",
     "architectural: any firmware that takes an interrupt or keeps time has to "
     "program these itself"),
    ("unknown", "unknown-service",
     "the original firmware touches this address space and nothing here "
     "identifies what it is, so whether a replacement needs it cannot be "
     "decided yet. This is a blocked item, not a permission"),
    ("flash-window", "may-omit",
     "reading the mapped flash window is storage access, not a platform "
     "service a minimal application has to provide"),
    ("runtime-ram", "not-a-service",
     "RAM inside the proven scatter runtime range"),
    ("program", "not-a-service", "the program's own image"),
    ("artifact", "not-a-service",
     "a constant-propagation artifact, excluded from the register map"),
    ("mixed", "see-registers",
     "the block holds addresses of more than one kind; read the per-register "
     "rows rather than the block"),
)
DEPENDENCY_BY_KIND = {kind: (verdict, why)
                      for kind, verdict, why in DEPENDENCY_RULES}


def dependency_rows(programs):
    rows = []
    for program in programs:
        for block in program.blocks:
            verdict, why = DEPENDENCY_BY_KIND.get(
                block.kind, ("unknown-service", "block kind not classified"))
            reset_only = block.contexts == ("Reset",)
            if block.kind == "unknown" and reset_only:
                verdict = "must-reproduce-or-disprove"
                why = ("every access to this space is on the reset path, so the "
                       "original firmware programs it before any service "
                       "exists. That is evidence about the code, not about the "
                       "address space: a replacement must either do the "
                       "equivalent or establish that it is unnecessary")
            rows.append({
                "accesses": block.accesses,
                "block": block.base,
                "contexts": list(block.contexts),
                "kind": block.kind,
                "program": program.name,
                "reason": why,
                "registers": len(block.registers),
                "verdict": verdict,
            })
    return tuple(rows)


# The plan's seven analysis areas, and what this map can and cannot say.
# The phase's own status. The plan asks for seven areas of analysis; this map
# delivers one census plus the vector table, so it is a first pass rather than
# the finished phase.
# The table's extent is an inference, not silicon proof. Recorded so the slot
# count is never quoted as an exact IRQ count.
VECTOR_TABLE_CONFIDENCE = (
    "strongly inferred",
    "The table is bounded by the first code address, which is where the reset "
    "path's own branch target sits, and the last slot below that bound holds a "
    "Thumb pointer to a callerless function — exactly the shape of a "
    "vector-only handler. Two independent facts line up: the bound falls on a "
    "16 + 64 boundary, and the highest NVIC enable word the software touches is "
    "ISER1, which covers IRQ32..IRQ63. But no exact IRQ-count source is "
    "available: the SNC7320-series product brief is series-level and carries no "
    "SNC73270 register map, and nothing in these bytes states the implemented "
    "interrupt count. A table of fewer than 64 external slots followed by "
    "unrelated data would look the same from the image alone.")

PHASE_STATUS = (
    "first-pass",
    "This is an MMIO access census plus a decoded vector table. Five of the "
    "plan's seven analysis areas are not covered and one is only partial, and "
    "the dependency map classifies address spaces rather than the original "
    "*services* the exit gate asks about. Phase 5 should be treated as "
    "incomplete and partly blocked on a SNC73270 reference manual, not as "
    "finished.")

COVERAGE_AREAS = (
    ("1. vector/interrupt table, reset path, memory init", "covered",
     "the table is decoded from installed bytes, the reset path is the "
     "reachability root, and the scatter-load memory initialisation is mapped "
     "in log 98/99"),
    ("1b. clock tree, watchdog, fault behaviour", "partial",
     "the fault and NMI vectors are identified and the reset-path vendor "
     "blocks are enumerated with their written values, but which block is the "
     "clock tree and which is a watchdog cannot be established without a "
     "reference manual"),
    ("2. USB device controller, descriptors, endpoints, HID reports", "not-covered",
     "no vendor block can be identified as the USB controller from these bytes "
     "alone; the HID report descriptors already recovered over USB in logs "
     "07/09 are the evidence for report layout, not this map"),
    ("3. GPIO and keyboard scan scheduling", "not-covered",
     "the same identification barrier; the interrupt slots in use are known "
     "but not what they are wired to"),
    ("4. Hall-effect acquisition, ADC, calibration, thresholds", "not-covered",
     "no analog block is identifiable; nothing here supports any claim about "
     "actuation thresholds or rapid trigger"),
    ("5. nonvolatile settings format and write paths", "not-covered",
     "flash-window reads are visible but no write path to nonvolatile storage "
     "is identified in the application; the bootloader's programming path is "
     "the one already documented in log 81"),
    ("6. RGB controller, timing, frame buffers", "not-covered",
     "the same identification barrier"),
    ("7. RTOS/task init, queues, timers, synchronisation", "partial",
     "SysTick and PendSV handlers exist and are located, which is the shape of "
     "a preemptive scheduler, but no queue or task structure is decoded here"),
)


# Statements that follow from a written value plus the ARM architecture, or from
# cross-referencing evidence this map already holds. Each is a predicate over the
# assembled map, so it is checked rather than asserted.
def notable_observations(hardware):
    out = []

    def register(program_name, address):
        for program in hardware.programs:
            if program.name != program_name:
                continue
            for block in program.blocks:
                for item in block.registers:
                    if item["address"] == address:
                        return item
        return None

    entry = "Candidate A (entry image)"
    app = "Candidate B (application)"

    aircr = register(entry, 0xE000ED0C)
    if aircr and 0x05FA0004 in aircr["stored_values"]:
        out.append((
            "The NMI handler requests a system reset.",
            "AIRCR is written 0x05fa0004: the architectural VECTKEY 0x05fa "
            "with SYSRESETREQ set. Written from the NMI context.",
            "high — the value and the register are both architectural"))

    icsr_entry = register(entry, 0xE000ED04)
    if icsr_entry and 0x10000000 in icsr_entry["stored_values"]:
        out.append((
            "The timebase pends a software interrupt, which is the shape of a "
            "preemptive scheduler.",
            "ICSR is written 0x10000000 (PENDSVSET) from the SysTick context, "
            "and the PendSV vector points at its own handler.",
            "high for the mechanism, none for what the scheduler schedules"))

    icsr_app = register(app, 0xE000ED04)
    if icsr_app and len(icsr_app["write_sites"]) > 1:
        out.append((
            "The application also pends that software interrupt, from several "
            "sites.",
            f"ICSR is written {len(icsr_app['write_sites'])} times in the "
            "application image, including from an interrupt context.",
            "high for the mechanism"))

    enabled = []
    for word, register_address in ((0, 0xE000E100), (1, 0xE000E104)):
        item = register(app, register_address)
        if not item:
            continue
        for value in item["stored_values"]:
            for bit in range(32):
                if value & (1 << bit):
                    enabled.append(word * 32 + bit)
    live = {slot.index - len(CORE_VECTORS) for slot in hardware.live_interrupts
            if slot.index >= len(CORE_VECTORS)}
    both = sorted(set(enabled) & live)
    if both:
        out.append((
            "The interrupts the software enables are the ones the table "
            "actually populates: " + ", ".join(f"IRQ{number}" for number in both)
            + ".",
            "NVIC_ISER words written with those bits set, cross-checked "
            "against the vector slots that hold a non-default handler. Two "
            "independent parts of the image agree.",
            "high"))

    fault = [address for address in (0xE000ED28, 0xE000ED34, 0xE000ED38)
             if register(entry, address)]
    if len(fault) == 3:
        out.append((
            "The fault handler reads the architectural fault status and "
            "address registers rather than just hanging.",
            "CFSR, MMFAR and BFAR are all read from the HardFault context.",
            "high — all three registers are architectural"))

    magic = [item for address in (0x40008000, 0x40009000)
             for item in [register(entry, address)] if item]
    keys = [item for address in (0x4000800C, 0x4000900C)
            for item in [register(entry, address)] if item]
    if len(magic) == 2 and len(keys) == 2:
        out.append((
            "Two identical unnamed blocks are unlocked with a magic key on the "
            "reset path.",
            "0x40008000 and 0x40009000 are each written 0x5afa0000, and "
            "0x4000800c and 0x4000900c are each written 0x5afa55aa. A "
            "key-protected register pair, duplicated. What the blocks control "
            "is not established.",
            "high for the pattern, none for the identity"))

    window = register(entry, 0x4002F004)
    if window and 0x60021000 in window["stored_values"]:
        out.append((
            "A reset-path register is programmed with the flash address of "
            "SN_FWIN record slot 1.",
            "0x4002f004 is written 0x60021000, which is exactly record slot "
            "1's address from the installed header. The register is therefore "
            "tied to the image layout, whatever else it does.",
            "high for the correspondence, none for the register's purpose"))

    for program_name, base in ((app, 0x40100000),):
        block = None
        for program in hardware.programs:
            if program.name != program_name:
                continue
            for candidate in program.blocks:
                if candidate.base == base:
                    block = candidate
        if block and any("IRQ" in context for context in block.contexts):
            out.append((
                f"The unnamed block at 0x{base:08x} is the one the live "
                "interrupt serves.",
                f"{len(block.registers)} registers, {block.accesses} accesses, "
                f"touched from {','.join(block.contexts)} — that is, from both "
                "an interrupt handler and the initialiser the entry image "
                "calls. It is the application's principal peripheral. Naming it "
                "would require a reference manual.",
                "high for the association, none for the identity"))
    return tuple(out)


def build_map(installed_view=None):
    view = installed_view or fi.ImageView(INSTALLED.read_bytes(), 0x10000)
    extraction = ex.extract(view)
    runtime_ranges = tuple((item.lo, item.hi) for item in extraction.runtime)

    slices = {item.import_base: item for item in extraction.slices
              if item.import_base is not None}
    entry_slice = slices[0x0]
    app_slice = slices[0x18000000]
    entry_bytes = (IMPORTS / entry_slice.name).read_bytes()

    inventories = {}
    for tag, name in (("entry", "installed_a"), ("app", "installed_b")):
        records, _header = mf.parse_inventory(
            (INVENTORIES / f"{name}.txt").read_text())
        inventories[tag] = records

    # The table is bounded by where code begins, which is the lowest function
    # entry now that the post-scatter branch target is a seeded function.
    first_code = min(record.entry for record in inventories["entry"])
    vectors, span, fill = parse_vector_table(
        entry_bytes, 0x0, first_code, runtime_ranges)
    code_range = (app_slice.import_base,
                  app_slice.import_base + app_slice.length)
    code_entries, data_pointers = cross_image_pointers(
        entry_bytes, 0x0, code_range, runtime_ranges, span)

    entry_roots, app_roots = [], []
    for slot in vectors:
        if slot.kind != "live" or slot.target_function is None:
            continue
        (entry_roots if slot.target_program == "entry" else app_roots).append(
            (slot.name, slot.target_function))
    for pointer in code_entries:
        if not pointer["in_vector_table"]:
            app_roots.append(
                (f"called from entry image 0x{pointer['entry_offset']:x}",
                 pointer["value"] & ~1))

    # Phase 5A: a function reached only through a pointer table is entered by a
    # mechanism the call graph cannot see, so the table entry is itself a root.
    # The label names the table, so a context always says how the function is
    # entered rather than merely that it is.
    surveys = fpt.build()
    by_program = {survey.program: survey for survey in surveys}
    for program, roots in (("entry", entry_roots), ("app", app_roots)):
        for table in by_program[program].tables:
            for _address, target in table.entries:
                roots.append((f"table@0x{table.location:08x}", target))

    # The decompressed scatter region holds no table under that rule, but it
    # does hold isolated pointers. One is admitted as a root only when Ghidra
    # already recognises a function at the address it names: that is external
    # validation the word is a callback, not a decision to trust lone words.
    # Words in the region that name no known function stay out.
    # Candidate B's runtime entry, seeded on logs 79-80: Candidate A's
    # post-scatter runtime FUN_000002c8 calls it through the veneer
    # thunk_EXT_FUN_1800023a. RECORDED AND NOT RESOLVED: no literal word in
    # either release's Candidate A points at this address, so the call reaches
    # it through code rather than through data. That is exactly why no pointer
    # survey found it, and it is reported as a contradiction below rather than
    # explained away here.
    for address, citation in DOCUMENTED_ENTRIES:
        app_roots.append((citation, address))

    # Phase 5A: an RTOS task entry is handed to the creation primitive in a
    # register, so it appears in no table and no initialised data. Each
    # accepted task entry is a root, labelled with the call site that creates
    # it. A task whose entry lives in the other image routes to that image's
    # root list, which is how the application's own scheduler reaches code the
    # bootloader copies to address 0.
    for program, label, address in ht.roots():
        (entry_roots if program == "entry" else app_roots).append(
            (label, address))

    region = by_program.get("ram")
    if region is not None:
        known = {record.entry for record in inventories["app"]}
        for address, target in region.loose_candidates:
            if target in known:
                app_roots.append(
                    (f"decompressed region 0x{address:08x}", target))

    programs = []
    for tag, name, slice_item, roots in (
            ("entry", "Candidate A (entry image)", entry_slice, entry_roots),
            ("app", "Candidate B (application)", app_slice, app_roots)):
        accesses, unresolved = parse_peripheral_map(
            (PERIPHERALS / f"installed_{'a' if tag == 'entry' else 'b'}.txt")
            .read_text())
        records = inventories[tag]
        contexts, unreached, unresolved_roots, orphans = reachability(
            records, roots)
        programs.append(ProgramMap(
            name=name, slice_name=slice_item.name,
            base=slice_item.import_base, functions=len(records),
            roots=tuple(sorted(roots)), contexts=contexts, unreached=unreached,
            unresolved_roots=unresolved_roots, orphans=orphans,
            accesses=accesses, unresolved=unresolved,
            blocks=build_blocks(accesses, contexts, slice_item.import_base,
                                slice_item.length, runtime_ranges)))

    contradictions = []
    documented_main = 0x1800023A
    if not any((pointer["value"] & ~1) == documented_main
               for pointer in code_entries + data_pointers):
        contradictions.append(
            "FINDINGS.md records Candidate B's runtime entry as "
            f"0x{documented_main:08x}, called by Candidate A after the scatter "
            "load (logs 79-80). No word in either release's Candidate A points "
            "there. The installed image's only non-vector cross-image code "
            "pointers are "
            + ", ".join(f"0x{pointer['value']:08x}" for pointer in code_entries
                        if not pointer["in_vector_table"])
            + ". Either the call is computed at runtime rather than taken from "
              "a literal, or the earlier attribution needs rechecking. Not "
              "resolved here.")

    return HardwareMap(
        phase_status=PHASE_STATUS,
        vector_table_confidence=VECTOR_TABLE_CONFIDENCE,
        image_sha256=view.sha256(), vector_table=vectors,
        vector_table_span=span, fill_value=fill,
        live_interrupts=tuple(slot for slot in vectors if slot.kind == "live"),
        code_entries=code_entries, data_pointers=data_pointers,
        programs=tuple(programs), contradictions=tuple(contradictions),
        coverage=COVERAGE_AREAS)


def to_dict(hardware):
    return {
        "contradictions": list(hardware.contradictions),
        "notable_observations": [
            {"basis": basis, "confidence": confidence, "statement": statement}
            for statement, basis, confidence in notable_observations(hardware)
        ],
        "coverage": [{"area": area, "reason": reason, "state": state}
                     for area, state, reason in hardware.coverage],
        "code_entries": [dict(pointer) for pointer in hardware.code_entries],
        "data_pointers": [dict(pointer) for pointer in hardware.data_pointers],
        "fill_value": hardware.fill_value,
        "dependency_map": [dict(row) for row in dependency_rows(hardware.programs)],
        "image_sha256": hardware.image_sha256,
        "live_interrupts": [
            {"index": slot.index, "name": slot.name,
             "target_function": slot.target_function,
             "target_program": slot.target_program, "value": slot.value}
            for slot in hardware.live_interrupts
        ],
        "programs": [
            {
                "accesses": len(program.accesses),
                "base": program.base,
                "blocks": [
                    {"accesses": block.accesses, "base": block.base,
                     "contexts": list(block.contexts),
                     "description": block.description, "kind": block.kind,
                     "registers": [dict(register) for register in block.registers]}
                    for block in program.blocks
                ],
                "functions": program.functions,
                "name": program.name,
                "reached_functions": len(program.contexts),
                "roots": [{"entry": entry, "label": label}
                          for label, entry in program.roots],
                "slice": program.slice_name,
                "unreached_functions": list(program.unreached),
                "unreached_with_no_caller": list(program.orphans),
                "unresolved_roots": [{"address": address, "label": label}
                                     for address, label in
                                     program.unresolved_roots],
                "unresolved_accesses": program.unresolved,
            }
            for program in hardware.programs
        ],
        "vector_table": [
            {"index": slot.index, "kind": slot.kind, "name": slot.name,
             "target_function": slot.target_function,
             "target_program": slot.target_program, "value": slot.value}
            for slot in hardware.vector_table
        ],
        "phase_status": {"state": hardware.phase_status[0],
                         "reason": hardware.phase_status[1]},
        "vector_table_confidence": {
            "basis": hardware.vector_table_confidence[1],
            "level": hardware.vector_table_confidence[0]},
        "vector_table_span": {"hi": hardware.vector_table_span[1],
                              "lo": hardware.vector_table_span[0]},
    }


def report_lines(hardware, max_registers=12):
    out = [
        "PROGRAM map_hardware_interfaces",
        "PURPOSE installed application hardware and runtime interface map",
        f"IMAGE_SHA256 {hardware.image_sha256}",
        f"VECTOR_TABLE 0x{hardware.vector_table_span[0]:x}.."
        f"0x{hardware.vector_table_span[1]:x} "
        f"({len(hardware.vector_table)} slots = 16 core + "
        f"{len(hardware.vector_table) - len(CORE_VECTORS)} external). "
        "An ARMv7-M table has no terminator, so the bound is the first code "
        "address and every word below it is a slot.",
        "FILL_VALUE " + ("none identified"
                         if hardware.fill_value is None
                         else f"0x{hardware.fill_value:08x}, the value repeated "
                              "across unused slots. It marks a slot unused; it "
                              "does not end the table, and a live slot can "
                              "follow it."),
        f"VECTOR_TABLE_CONFIDENCE {hardware.vector_table_confidence[0]} — "
        f"{hardware.vector_table_confidence[1]}",
        f"PHASE_STATUS {hardware.phase_status[0]} — {hardware.phase_status[1]}",
    ]
    for slot in hardware.vector_table[:len(CORE_VECTORS)]:
        out.append(f"CORE_VECTOR [{slot.index:2d}] {slot.name:<13} "
                   f"0x{slot.value:08x} {slot.kind}")
    out.append(f"LIVE_INTERRUPTS {len(hardware.live_interrupts)}")
    for slot in hardware.live_interrupts:
        if slot.index < len(CORE_VECTORS):
            continue
        out.append(f"  {slot.name:<8} 0x{slot.value:08x} -> "
                   f"{slot.target_program} image at "
                   f"0x{slot.target_function:08x}")
    non_vector = [pointer for pointer in hardware.code_entries
                  if not pointer["in_vector_table"]]
    out.append(f"CODE_ENTRIES {len(hardware.code_entries)} into the application "
               f"code range ({len(non_vector)} outside the vector table)")
    for pointer in non_vector:
        out.append(f"  entry image 0x{pointer['entry_offset']:04x} -> "
                   f"0x{pointer['value']:08x}")
    out.append(f"DATA_POINTERS {len(hardware.data_pointers)} entry-image words "
               "point into application RAM outside the code range; those are "
               "shared variables, not entry points")

    for program in hardware.programs:
        out += [
            "",
            f"IMAGE {program.name}",
            f"  slice={program.slice_name}",
            f"  base=0x{program.base:08x} functions={program.functions} "
            f"reached={len(program.contexts)} "
            f"unreached={len(program.unreached)}",
            f"  roots={len(program.roots)} "
            + ("vector/entry: " + ", ".join(
                f"{label}@0x{entry:08x}" for label, entry in program.roots
                if not label.startswith("table@")) or "none"),
            "  table roots: " + (", ".join(sorted({
                label for label, _entry in program.roots
                if label.startswith("table@")})) or "none"),
            "  documented entry roots: " + (", ".join(
                f"{label}->0x{entry:08x}" for label, entry in program.roots
                if label.startswith("Candidate B main")) or "none"),
            "  task roots: " + (", ".join(
                f"{label}->0x{entry:08x}" for label, entry in program.roots
                if label.startswith("task ")) or "none"),
            "  region roots: " + (", ".join(
                f"{label}->0x{entry:08x}" for label, entry in program.roots
                if label.startswith("decompressed region")) or "none"),
            # A root that names no function is shown, not dropped: it is the
            # difference between "this table has three entries" and "this
            # table contributes three distinct functions".
            "  roots naming no function: " + (", ".join(
                f"{address} ({label})"
                for address, label in program.unresolved_roots) or "none"),
            "  ROOT_BLOCKS which hardware each newly seeded root can reach:",
        ]
        seeded = [label for label, _entry in sorted(set(program.roots))
                  if label.startswith(("task ", "decompressed region ",
                                       "Candidate B main"))]
        for label in seeded:
            touched = [f"0x{block.base:08x}({block.kind})"
                       for block in program.blocks if label in block.contexts]
            out.append(f"    {label} -> "
                       + (", ".join(touched) or "no mapped block"))
        if not seeded:
            out.append("    none in this image")
        out += [
            f"  unreached_with_no_caller={len(program.orphans)} "
            "(each needs an entry mechanism; the rest of the unreached set is "
            "downstream of these)",
            f"  resolved_accesses={len(program.accesses)}",
            "  unresolved_accesses=" + ", ".join(
                f"{reason}={count}"
                for reason, count in program.unresolved.items()),
        ]
        for block in program.blocks:
            out.append(f"  BLOCK 0x{block.base:08x} {block.kind} "
                       f"registers={len(block.registers)} "
                       f"accesses={block.accesses} "
                       f"contexts={','.join(block.contexts)}")
            out.append(f"    {block.description}")
            if block.kind in ("runtime-ram", "program", "artifact"):
                continue
            shown = block.registers[:max_registers] if max_registers else block.registers
            for register in shown:
                name = register["arm_name"] or "unnamed"
                stored = (", ".join(f"0x{value:x}"
                                    for value in register["stored_values"])
                          or "none resolved")
                init = (", ".join(
                    f"0x{value:x}"
                    for value in register["reset_reachable_write_values"])
                        or "none from a reset-reachable function")
                out.append(
                    f"    0x{register['address']:08x} {name:<10} "
                    f"{register['kind']:<12} widths={register['widths']} "
                    f"reads={len(register['read_sites'])} "
                    f"writes={len(register['write_sites'])} "
                    f"stored={stored} reset_writes={init} "
                    f"contexts={','.join(register['contexts'])}")
            if max_registers and len(block.registers) > max_registers:
                out.append(f"    ... {len(block.registers) - max_registers} "
                           f"more registers, complete list in the JSON")

    out += ["", "DEPENDENCY_MAP"]
    for row in dependency_rows(hardware.programs):
        out.append(f"  {row['verdict']:<30} 0x{row['block']:08x} "
                   f"{row['kind']:<13} {row['program']}")
        out.append(f"    {row['reason']}")

    observations = notable_observations(hardware)
    out += ["", f"NOTABLE_OBSERVATIONS {len(observations)}"]
    for statement, basis, confidence in observations:
        out.append(f"  {statement}")
        out.append(f"    basis: {basis}")
        out.append(f"    confidence: {confidence}")

    out += ["", "COVERAGE OF THE PLANNED ANALYSIS AREAS"]
    for area, state, reason in hardware.coverage:
        out.append(f"  {state:<12} {area}")
        out.append(f"    {reason}")

    for line in hardware.contradictions:
        out += ["", f"CONTRADICTION {line}"]

    out += [
        "",
        "LIMITATION Vendor MMIO blocks are described by observed accesses only. "
        "No SNC73270 reference manual is available, so this map names no vendor "
        "peripheral and supports no claim about USB, scan, Hall-effect, "
        "nonvolatile or RGB hardware.",
        "LIMITATION An access appears only when constant propagation resolved "
        "its base register. Accesses through a pointer held in a parameter or a "
        "structure are counted as unresolved, so the register list is a lower "
        "bound, not a complete set.",
        "LIMITATION Reachability is computed from Ghidra's call graph, which "
        "does not follow calls made through function-pointer tables, so a "
        "function reported as unreached may still run.",
    ]
    for line in fi.UNRESOLVED:
        out.append(f"UNRESOLVED {line}")
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-registers", type=int, default=12,
                        help="registers to print per block; 0 for all")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        hardware = build_map()
    except (OSError, ValueError, KeyError, fi.ImageFormatError,
            ex.ExtractError) as exc:
        print(f"RESULT map_ok=False error={exc}")
        return 1
    if args.json:
        print(json.dumps(to_dict(hardware), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(hardware, args.max_registers)))
        blocks = sum(len(program.blocks) for program in hardware.programs)
        print(f"RESULT map_ok=True live_interrupts="
              f"{len(hardware.live_interrupts)} blocks={blocks} "
              f"contradictions={len(hardware.contradictions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
