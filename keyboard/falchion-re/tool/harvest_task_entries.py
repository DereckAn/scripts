#!/usr/bin/env python3
"""Turn harvested RTOS task-creation call sites into validated entry roots.

Read-only and offline. Phase 5A: a task entry point is handed to the creation
primitive in a register. It is stored in no pointer table and no initialised
data, so every byte survey run so far is blind to it — which is why 5A's
reachability stalled with the whole scheduler unreached.

`ghidra/scripts/FalchionTaskCreation.java` resolves each call site's arguments
by constant propagation over the *calling* function. This module parses that
output, applies the recovered call shape, and refuses anything it cannot back
with evidence.

THE CALL SHAPE, recovered from the primitive's own code rather than assumed
(vendor `FUN_18012fa4`, installed `FUN_18012fd0`, byte-identical bodies):

    create(entry, name, stack_words, argument, priority, out_handle)

    a0  entry     task entry pointer, Thumb bit set
    a1  name      pointer to a NUL-terminated name; the initialiser copies at
                  most 0x10 bytes of it to TCB+0x34
    a2  stack     size in 32-BIT WORDS: the primitive allocates `stack << 2`
    a3  argument  passed through to the entry point
    a4  priority  clamped to 0..0xe; the ready-list index is 0xf - priority
    a5  out       optional pointer that receives the TCB, or 0

Those roles are read off `FUN_18013ea0`, the initialiser the primitive calls:
it copies a1 bytewise into the control block, fills `a2 << 2` stack bytes,
clamps a4 and derives `0xf - a4`, and hands (stack_top, a0, a3) to the frame
builder. No role is inferred from a name string.

ACCEPTANCE IS CONSERVATIVE. A call site contributes a root only when every
argument resolved, the entry has the Thumb bit set, and the target decoded as
Thumb where it lives. Anything else is recorded unresolved and reported, never
guessed and never dropped.

No device access. Examples:
    python3 tool/harvest_task_entries.py
    python3 tool/harvest_task_entries.py --json
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "ghidra/tasks"

# The primitive, per release. Byte-identical bodies; the installed copy sits at
# the +0x2c relocation Phase 3 measured.
PRIMITIVE = {"installed": 0x18012FD0, "vendor": 0x18012FA4}
# The initialiser the roles were read from.
INITIALISER = {"installed": 0x18013ECC, "vendor": 0x18013EA0}
# A task entry may live in either image: the application creates one whose code
# is in the entry image, which the bootloader copies to address 0 at runtime.
PROGRAM_WINDOWS = {"entry": (0x0, 0x58AC), "app": (0x18000000, 0x1801E380)}
# The initialiser copies at most this many name bytes into the control block.
NAME_LIMIT = 0x10
# It also clamps the priority to this value.
PRIORITY_MAX = 0xE

ARG_NAMES = ("entry", "name_pointer", "stack_words", "argument", "priority",
             "out_handle")

CALLSITE = re.compile(
    r"^CALLSITE primitive=(?P<primitive>[0-9a-f]+) instr=(?P<instr>[0-9a-f]+) "
    r"func=(?P<func>\S+) order=(?P<order>\d+) "
    r"a0=(?P<a0>\S+) a1=(?P<a1>\S+) a2=(?P<a2>\S+) a3=(?P<a3>\S+) "
    r"a4=(?P<a4>\S+) a5=(?P<a5>\S+) str=(?P<name>.*?)"
    r"(?: reason=(?P<reason>\S+))?$")
TARGET = re.compile(
    r"^TARGET addr=0x(?P<addr>[0-9a-f]+) thumb=(?P<thumb>\w+) "
    r"mapped=(?P<mapped>\w+) valid_subroutine=(?P<valid>\w+) "
    r"decoded=(?P<decoded>\d+) prologue=(?P<prologue>\S+) "
    r"defined=(?P<defined>\w+) at=(?P<at>\S+)$")
PRIMITIVE_LINE = re.compile(
    r"^PRIMITIVE entry=(?P<entry>[0-9a-f]+) name=(?P<name>\S+) "
    r"params=(?P<params>\d+) body=(?P<body>\S+) callers=(?P<callers>\d+)")


INDIRECT = re.compile(
    r"^INDIRECT instr=(?P<instr>[0-9a-f]+) func=(?P<func>[0-9a-f]+) "
    r"mnemonic=(?P<mnemonic>\S+) register=(?P<register>\S+) "
    r"target=(?P<target>\S+)$")
INDIRECT_RESULT = re.compile(
    r"^INDIRECT_RESULT sites=(?P<sites>\d+) resolved=(?P<resolved>\d+) "
    r"unresolved=(?P<unresolved>\d+)$")


class HarvestError(ValueError):
    """The harvest output does not support the conclusion asked of it."""


@dataclass(frozen=True)
class Target:
    address: int
    thumb: bool
    mapped: bool
    valid_subroutine: bool
    decoded: int
    prologue: str
    defined: bool
    at: str

    @property
    def decodes_as_thumb(self):
        """Ghidra decoded a full run of Thumb instructions from the address.

        `valid_subroutine` is deliberately NOT required. It is a heuristic that
        returns false for any span still stored as undefined data, which every
        unseeded target is, so requiring it would reject every real find. What
        is required is that the bytes actually decode.
        """
        return self.mapped and self.decoded >= 8


@dataclass(frozen=True)
class Task:
    release: str
    call_site: int
    creator: int
    entry: int
    name: str
    stack_words: int
    argument: int
    priority: int
    out_handle: int
    program: str
    target: object
    unresolved: tuple

    @property
    def stack_bytes(self):
        return None if self.stack_words is None else self.stack_words * 4

    @property
    def effective_priority(self):
        return None if self.priority is None else min(self.priority,
                                                      PRIORITY_MAX)

    @property
    def ready_index(self):
        """The initialiser stores 0xf - priority as the ready-list index."""
        effective = self.effective_priority
        return None if effective is None else 0xF - effective

    @property
    def accepted(self):
        return (not self.unresolved and self.program is not None
                and self.target is not None and self.target.decodes_as_thumb)


def window_of(address):
    for program, (low, high) in PROGRAM_WINDOWS.items():
        if low <= address < high:
            return program
    return None


def parse_value(text):
    if text == "unknown":
        return None
    return int(text, 16)


def parse(text, release):
    """Parse one release's harvest output into targets, tasks and the primitive."""
    targets = {}
    tasks = []
    primitives = []
    for line in text.splitlines():
        match = TARGET.match(line)
        if match:
            target = Target(
                address=int(match["addr"], 16),
                thumb=match["thumb"] == "true",
                mapped=match["mapped"] == "true",
                valid_subroutine=match["valid"] == "true",
                decoded=int(match["decoded"]),
                prologue=match["prologue"],
                defined=match["defined"] == "true",
                at=match["at"])
            targets[target.address] = target
            continue
        match = PRIMITIVE_LINE.match(line)
        if match:
            primitives.append({"entry": int(match["entry"], 16),
                               "name": match["name"],
                               "params": int(match["params"]),
                               "body": match["body"],
                               "callers": int(match["callers"])})
            continue
        match = CALLSITE.match(line)
        if not match:
            continue
        values = [parse_value(match[f"a{index}"]) for index in range(6)]
        unresolved = tuple(ARG_NAMES[index] for index, value
                           in enumerate(values) if value is None)
        entry = values[0]
        program = None
        if entry is not None:
            if not entry & 1:
                # The frame builder takes this straight as the task PC. Without
                # the Thumb bit it would fault on the first instruction, so a
                # even value is not a code pointer we are willing to seed.
                unresolved += ("entry_not_thumb",)
            else:
                program = window_of(entry & ~1)
                if program is None:
                    unresolved += ("entry_outside_every_image",)
        tasks.append(Task(
            release=release,
            call_site=int(match["instr"], 16),
            creator=int(match["func"], 16) if match["func"] != "none" else 0,
            entry=entry, name=match["name"].strip(),
            stack_words=values[2], argument=values[3], priority=values[4],
            out_handle=values[5], program=program,
            target=targets.get((entry & ~1) if entry else -1),
            unresolved=unresolved))
    # Targets are emitted before call sites in a combined run, but a task whose
    # entry lives in the other image has its target line in that image's file.
    return targets, tuple(tasks), tuple(primitives)


def creation_order(tasks):
    """Order tasks by who creates whom, not by call-site address.

    The address order is an artefact of the linker. The real order is the
    chain: whoever runs first creates the next. A task created by a function
    that is not itself a task entry has no predecessor and comes first.
    """
    by_entry = {task.entry & ~1: task for task in tasks if task.entry}
    order = []
    seen = set()

    def visit(task):
        if task.call_site in seen:
            return
        seen.add(task.call_site)
        parent = by_entry.get(task.creator)
        if parent is not None and parent.call_site not in seen:
            visit(parent)
        order.append(task)

    for task in sorted(tasks, key=lambda item: item.call_site):
        visit(task)
    return tuple(order)


def load(release):
    parts = {}
    for suffix in ("a", "b"):
        path = TASKS / f"{release}_{suffix}.txt"
        parts[suffix] = path.read_text() if path.exists() else ""
    targets_b, tasks, primitives = parse(parts["b"], release)
    targets_a, _tasks_a, _primitives_a = parse(parts["a"], release)
    targets = dict(targets_a)
    targets.update(targets_b)
    # Re-attach each task to whichever image's file carries its target line.
    tasks = tuple(
        Task(**{**task.__dict__,
                "target": targets.get((task.entry & ~1) if task.entry else -1)})
        for task in tasks)
    return targets, creation_order(tasks), primitives


def indirect_calls(release="installed"):
    """Register-target branches per image, with what propagation resolved.

    5A's exit gate asks for the remaining unresolved indirect calls to be
    enumerated. This is that enumeration: a count and an address list per
    image, so the residue has a size instead of a hand-wave. `bx lr` is
    excluded because it is a return, not a call.
    """
    out = {}
    for suffix, program in (("a", "entry"), ("b", "app")):
        path = TASKS / f"{release}_{suffix}.txt"
        if not path.exists():
            continue
        sites = []
        totals = None
        for line in path.read_text().splitlines():
            match = INDIRECT.match(line)
            if match:
                sites.append({
                    "function": int(match["func"], 16),
                    "instruction": int(match["instr"], 16),
                    "mnemonic": match["mnemonic"],
                    "register": match["register"],
                    "target": (None if match["target"] == "unknown"
                               else int(match["target"], 16)),
                })
                continue
            match = INDIRECT_RESULT.match(line)
            if match:
                totals = {key: int(match[key])
                          for key in ("sites", "resolved", "unresolved")}
        if totals is None:
            continue
        if totals["sites"] != len(sites):
            raise HarvestError(
                f"{path.name} reports {totals['sites']} indirect sites but "
                f"lists {len(sites)}; refusing to report a count the file "
                "does not support")
        out[program] = {"sites": tuple(sites), "total": totals["sites"],
                        "resolved": totals["resolved"],
                        "unresolved": totals["unresolved"]}
    return out


def roots(release="installed"):
    """(program, label, address) for every accepted task entry."""
    _targets, tasks, _primitives = load(release)
    return tuple((task.program,
                  f"task {task.name} created at 0x{task.call_site:08x}",
                  task.entry & ~1)
                 for task in tasks if task.accepted)


def to_dict(release="installed"):
    targets, tasks, primitives = load(release)
    return {
        "acceptance": (
            "a call site becomes a root only when every argument resolved, the "
            "entry carries the Thumb bit, it lies inside one of the two "
            "images, and its bytes decoded as Thumb"),
        "call_shape": list(ARG_NAMES),
        "initialiser": INITIALISER.get(release),
        "name_limit": NAME_LIMIT,
        "primitive": PRIMITIVE.get(release),
        "indirect_calls": {
            program: {"resolved": item["resolved"],
                      "sites": [dict(site) for site in item["sites"]],
                      "total": item["total"],
                      "unresolved": item["unresolved"]}
            for program, item in indirect_calls(release).items()},
        "primitives_seen": list(primitives),
        "priority_max": PRIORITY_MAX,
        "release": release,
        "targets": [
            {"address": target.address, "at": target.at,
             "decoded": target.decoded, "defined": target.defined,
             "mapped": target.mapped, "prologue": target.prologue,
             "thumb": target.thumb,
             "valid_subroutine": target.valid_subroutine}
            for target in sorted(targets.values(), key=lambda t: t.address)],
        "tasks": [
            {"accepted": task.accepted, "argument": task.argument,
             "call_site": task.call_site, "creation_index": index,
             "creator": task.creator, "entry": task.entry,
             "effective_priority": task.effective_priority,
             "name": task.name, "priority": task.priority,
             "program": task.program, "ready_index": task.ready_index,
             "stack_bytes": task.stack_bytes, "stack_words": task.stack_words,
             "unresolved": list(task.unresolved)}
            for index, task in enumerate(tasks)],
    }


def report_lines(releases=("installed", "vendor")):
    out = [
        "PROGRAM harvest_task_entries",
        "PURPOSE recover task entry points passed to the RTOS creation call in "
        "a register, which no pointer-table survey can see",
        "CALL_SHAPE create(entry, name, stack_words, argument, priority, "
        "out_handle) — read off the initialiser's own code, not assumed",
        f"RULE the initialiser copies at most 0x{NAME_LIMIT:x} name bytes, "
        f"allocates stack_words<<2 bytes, clamps priority to "
        f"0x{PRIORITY_MAX:x}, and uses 0xf-priority as the ready-list index",
        "RULE a call site becomes a root only when every argument resolved, "
        "the entry carries the Thumb bit, it lies inside one of the two "
        "images, and its bytes decoded as Thumb. Nothing else is seeded.",
    ]
    for release in releases:
        targets, tasks, primitives = load(release)
        out += ["", f"RELEASE {release}"]
        for item in primitives:
            out.append(f"  PRIMITIVE 0x{item['entry']:08x} {item['name']} "
                       f"body={item['body']} callers={item['callers']}")
        for index, task in enumerate(tasks):
            entry = f"0x{task.entry:08x}" if task.entry is not None else "unknown"
            clamped = ("" if task.priority is None
                       or task.priority <= PRIORITY_MAX
                       else f"->{task.effective_priority}(clamped)")
            stack = ("unknown" if task.stack_words is None
                     else f"{task.stack_words}w/{task.stack_bytes}B")
            argument = ("unknown" if task.argument is None
                        else f"0x{task.argument:x}")
            out.append(
                f"  TASK #{index} {task.name!r} entry={entry} "
                f"program={task.program or 'none'} stack={stack} "
                f"priority={task.priority}{clamped} "
                f"ready_index={task.ready_index} arg={argument}")
            out.append(f"      created at 0x{task.call_site:08x} by "
                       f"0x{task.creator:08x}"
                       + (f", handle -> 0x{task.out_handle:08x}"
                          if task.out_handle else ", no handle stored"))
            if task.target is not None:
                out.append(f"      target decoded={task.target.decoded} "
                           f"prologue={task.target.prologue} "
                           f"defined={task.target.defined} "
                           f"as={task.target.at}")
            else:
                out.append("      target NOT VALIDATED — no TARGET line for "
                           "this address in either image")
            out.append(f"      ACCEPTED={task.accepted}"
                       + (" unresolved=" + ",".join(task.unresolved)
                          if task.unresolved else ""))
        accepted = sum(1 for task in tasks if task.accepted)
        out.append(f"  RESULT tasks={len(tasks)} accepted={accepted} "
                   f"rejected={len(tasks) - accepted}")
    for release in releases:
        counts = indirect_calls(release)
        out.append("")
        out.append(f"INDIRECT_CALLS {release} — register-target branches, "
                   "excluding `bx lr` returns")
        for program in sorted(counts):
            item = counts[program]
            out.append(f"  {program}: sites={item['total']} "
                       f"resolved={item['resolved']} "
                       f"unresolved={item['unresolved']}")
    out += [
        "",
        "EXIT_GATE The unresolved indirect calls above are enumerated, not "
        "eliminated. Each is a branch whose destination register constant "
        "propagation could not resolve at that instruction; every one is "
        "listed by address in ghidra/tasks/<release>_<image>.txt.",
        "LIMITATION Only tasks created through this one primitive are here. A "
        "callback registered with a timer, a queue, or an interrupt service "
        "registration is a different primitive and is not covered.",
        "LIMITATION The creation order is the static chain of who creates "
        "whom. It is not a runtime schedule: nothing here observed execution.",
    ]
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--release", default="installed",
                        choices=("installed", "vendor"))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.json:
            print(json.dumps(to_dict(args.release), indent=2, sort_keys=True))
        else:
            print("\n".join(report_lines()))
    except (OSError, HarvestError) as exc:
        print(f"RESULT tasks=0 error={exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
