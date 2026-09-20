#!/usr/bin/env python3
"""The Armoury Crate profile model and its deterministic recursive diff.

Read-only and offline. NO DEVICE IS ACCESSED: this reads files Armoury Crate
already wrote, or snapshots of them.

WHY THIS MODULE EXISTS. `tools/snap-config.ps1` saved the whole decoded
configuration but compared only `button.keyboardButton`, so a run could print
"NO CHANGE" after a global rapid-trigger, polling-rate, dead-zone, Speed Tap,
lighting or lever change (log 131, finding 4). The fix is a diff over the
*complete* model rather than a hand-maintained field list, and a complete diff
has to be tested against a real profile — which is what this module is for.
PowerShell cannot be run in this repository's environment; this is the same
algorithm in a form the offline suite can exercise against
`notes/ac-profile3-decoded.json`.

THE RULE. Flatten both sides to `path -> scalar` and compare every path. A
category is covered because the paths under it exist and differ, never because
someone remembered to add it to a list. `REQUIRED_CATEGORIES` therefore does
not drive the diff: it is an assertion *about* the diff, checked against the
preserved profile so a model that silently loses a field fails the suite.

Examples:
    python3 tool/profile_diff.py --categories
    python3 tool/profile_diff.py before.json after.json
    python3 tool/profile_diff.py --check
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "notes/ac-profile3-decoded.json"
POWERSHELL = ROOT / "tools/snap-config.ps1"

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"

# Every category finding 4 requires the diff to detect, with the path prefix
# that proves it. A prefix is matched against the flattened paths, so a
# per-key field matches through the `keyfunction_<col>_<row>` level.
REQUIRED_CATEGORIES = {
    "all-key actuation": ".button.analogTrigger.actuation",
    "rapid trigger separate mode":
        ".button.analogTrigger.rapidTriggerSeparateMode",
    "rapid trigger continue status":
        ".button.analogTrigger.rapidTriggerContinueStatue",
    "all-key rapid trigger": ".button.analogTrigger.rapidTrigger",
    "rapid trigger press distance": ".button.analogTrigger.rapidTriggerPress",
    "rapid trigger release distance":
        ".button.analogTrigger.rapidTriggerRelease",
    "per-key rapid trigger list":
        ".button.analogTrigger.preKeyRapidTriggerList",
    "per-key actuation": ".button.keyboardButton.*.button.normal.actuation",
    "per-key trigger type": ".button.keyboardButton.*.button.trigger_type",
    "polling rate": ".performance.pollingRate",
    "speed tap": ".button.speedTap",
    "dead zone": ".button.deadZone",
    "lighting": ".lighting",
    "lever": ".lever",
}

# The block tools/snap-config.ps1 must carry, so the two cannot drift apart.
PS_BLOCK_BEGIN = "# CANONICAL-BEGIN profile_diff.py owns this contract"
PS_BLOCK_END = "# CANONICAL-END"


class ProfileError(Exception):
    """The snapshot cannot be compared, and guessing is not an option."""


def load(path):
    """Read a JSON file Armoury Crate or PowerShell wrote, BOM and all."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{path}: {exc}") from exc


def flatten(value, prefix=""):
    """`path -> scalar` for every leaf, deterministically ordered.

    A list index is part of the path, so reordering `preKeyRapidTriggerList`
    or a lighting colour array is a change and is reported as one.
    """
    out = {}
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            out.update(flatten(value[key], f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out.update(flatten(item, f"{prefix}[{index}]"))
    else:
        out[prefix or "."] = value
    return out


def canonical(value):
    """A comparison key that carries the JSON TYPE as well as the value.

    Without this, the number `1` and the string `"1"` compare equal after
    either side stringifies, and in Python `True == 1` as well — so a Boolean
    turning into a number would read as no change. The tag is the comparison
    representation; it is never display formatting, and both this module and
    `tools/snap-config.ps1` are specified to produce exactly these strings.

    Non-integral numbers use the shortest round-trip form. The preserved
    profile holds only integers and strings, so that path is specified and
    tested rather than exercised by the real data.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool:true" if value else "bool:false"
    if isinstance(value, int):
        return f"num:{value}"
    if isinstance(value, float):
        if value.is_integer():
            return f"num:{int(value)}"
        return f"num:{value!r}"
    return f"str:{value}"


def diff(old, new):
    """Every path whose value differs, added or removed. Sorted, so stable.

    Comparison is on `canonical()`; the reported values stay raw, so the
    output reads naturally while `1` and `"1"` still count as a change.
    """
    left, right = flatten(old), flatten(new)
    changes = []
    for path in sorted(set(left) | set(right)):
        if path not in left:
            changes.append((path, ADDED, None, right[path]))
        elif path not in right:
            changes.append((path, REMOVED, left[path], None))
        elif canonical(left[path]) != canonical(right[path]):
            changes.append((path, CHANGED, left[path], right[path]))
    return changes


def matches(path, prefix):
    """Does a flattened path sit under a required category's prefix?

    `*` stands for one path component, which is how a per-key field names
    every `keyfunction_<col>_<row>` at once.
    """
    pattern = "^" + re.escape(prefix).replace(r"\*", r"[^.\[]+")
    return re.match(pattern + r"($|[.\[])", path) is not None


def categories_touched(changes):
    """Which required categories a change list covers."""
    return {name for name, prefix in REQUIRED_CATEGORIES.items()
            if any(matches(path, prefix) for path, *_rest in changes)}


def category_coverage(config):
    """name -> how many flattened paths the reference profile has there.

    A zero here means the model lost a field and the diff can no longer see
    that category at all, whatever the comparison code claims.
    """
    paths = flatten(config)
    return {name: sum(1 for path in paths if matches(path, prefix))
            for name, prefix in sorted(REQUIRED_CATEGORIES.items())}


# --------------------------------------------------------- snapshot format

SNAPSHOT_KEYS = ("capturedUtc", "profiles", "tool")
PROFILE_KEYS = ("config", "file", "mtime", "path", "sha256")


def check_snapshot(payload):
    """Complain about anything that makes a snapshot unattributable."""
    problems = []
    if not isinstance(payload, dict):
        return ["snapshot is not an object"]
    for key in SNAPSHOT_KEYS:
        if key not in payload:
            problems.append(f"snapshot has no {key!r}")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        problems.append("snapshot has no profiles")
        return problems
    for index, entry in enumerate(profiles):
        for key in PROFILE_KEYS:
            if not isinstance(entry, dict) or key not in entry:
                problems.append(f"profiles[{index}] has no {key!r}")
    return problems


def profile_map(payload):
    """file name -> decoded configuration, for a snapshot of any age."""
    problems = check_snapshot(payload)
    if problems:
        raise ProfileError("; ".join(problems))
    return {entry["file"]: entry["config"] for entry in payload["profiles"]}


def snapshot_diff(old, new):
    """Per-file changes between two -AllProfiles snapshots.

    The output names the file, so "which profile changed" is answered by the
    diff itself rather than by the operator remembering which one they had
    open.
    """
    left, right = profile_map(old), profile_map(new)
    out = {}
    for name in sorted(set(left) | set(right)):
        if name not in left:
            # Present only in the NEW snapshot: the profile file was added.
            out[name] = [("", ADDED, None, name)]
        elif name not in right:
            # Present only in the OLD snapshot: the profile file was removed.
            out[name] = [("", REMOVED, name, None)]
        else:
            changes = diff(left[name], right[name])
            if changes:
                out[name] = changes
    return out


# ------------------------------------------------- PowerShell drift guard

def powershell_drift(path=POWERSHELL):
    """What stops tools/snap-config.ps1 matching this contract."""
    text = Path(path).read_text(encoding="utf-8")
    problems = []
    start = text.find(PS_BLOCK_BEGIN)
    end = text.find(PS_BLOCK_END, start + 1)
    if start < 0 or end < 0:
        return ["snap-config.ps1 has no canonical contract block"]
    block = text[start:end]
    for key in SNAPSHOT_KEYS + PROFILE_KEYS:
        if key not in block:
            problems.append(f"snap-config.ps1 contract omits {key!r}")
    code = re.sub(r"<#.*?#>", "", text, flags=re.S)
    if "keyboardButton.PSObject.Properties" in code:
        problems.append("snap-config.ps1 still flattens only "
                        "button.keyboardButton")
    for needed in ("AllProfiles", "Get-Flat", "Get-Canonical", "Get-FileHash"):
        if needed not in code:
            problems.append(f"snap-config.ps1 no longer mentions {needed}")
    for tag in ("'null'", "bool:true", "bool:false", "num:", "str:"):
        if tag not in code:
            problems.append(f"snap-config.ps1 no longer emits the {tag} tag")
    if re.search(r"\$acc\[[^]]*\]\s*=\s*\"\$value\"", code):
        problems.append("snap-config.ps1 stringifies scalars again, which "
                        "makes the number 1 and the string \"1\" equal")
    return problems


# ------------------------------------------------------------------ output

def format_changes(changes, indent="  "):
    return [f"{indent}{kind:<7} {path}: {old!r} -> {new!r}"
            for path, kind, old, new in changes]


def report_lines(old_payload, new_payload):
    per_file = snapshot_diff(old_payload, new_payload)
    out = [f"PROFILES {len(profile_map(new_payload))}"]
    if not per_file:
        out.append("RESULT changed_files=0 changes=0 NO CHANGE — every "
                   "compared path in every profile is equal")
        return out
    total = 0
    for name, changes in per_file.items():
        out.append(f"FILE {name}  {len(changes)} change(s)")
        out += format_changes(changes)
        total += len(changes)
    out.append(f"RESULT changed_files={len(per_file)} changes={total}")
    covered = categories_touched(
        [change for changes in per_file.values() for change in changes])
    if covered:
        out.append("CATEGORIES " + ", ".join(sorted(covered)))
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", nargs="?", help="baseline snapshot JSON")
    parser.add_argument("new", nargs="?", help="later snapshot JSON")
    parser.add_argument("--categories", action="store_true",
                        help="show required-category coverage of the "
                             "preserved reference profile")
    parser.add_argument("--check", action="store_true",
                        help="prove the model and snap-config.ps1 agree")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.categories or args.check:
        coverage = category_coverage(load(REFERENCE))
        missing = [name for name, count in coverage.items() if not count]
        if args.categories:
            for name, count in coverage.items():
                print(f"CATEGORY {name}: {count} path(s)")
        problems = list(powershell_drift()) if args.check else []
        for problem in problems:
            print(f"DRIFT {problem}")
        for name in missing:
            print(f"MISSING {name} has no path in {REFERENCE.name}")
        drift = f" drift={len(problems)}" if args.check else ""
        print(f"RESULT categories={len(coverage)} "
              f"missing={len(missing)}{drift}")
        return 1 if (missing or problems) else 0
    if not (args.old and args.new):
        print("RESULT error=give two snapshots, or --categories / --check")
        return 1
    try:
        print("\n".join(report_lines(load(args.old), load(args.new))))
    except ProfileError as exc:
        print(f"RESULT error={exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
