#!/usr/bin/env python3
"""The guard rules the Windows capture and trace scripts must obey.

Read-only and offline. NO DEVICE IS ACCESSED and nothing here captures
anything: this module holds the *decision logic* of `tools/capture.ps1` and
`tools/haltrace.ps1` — refuse a colliding output, reject an interface that was
never enumerated, believe the native exit status, and only call a run
successful when the file it produced is a real, non-empty capture — in a form
the offline suite can execute, plus a structural check that the PowerShell
scripts still implement it in the right order.

WHY IT IS SPLIT THIS WAY. PowerShell cannot be run in this repository's
environment, so "the script refuses a collision" was previously unprovable and,
as log 131 found, untrue: `capture.ps1` overwrote an existing `-Out`, ignored
tshark's exit status, and printed `saved:` unconditionally — which is how the
original first-launch capture was lost. The rules below are executable and
tested. WHAT IS STILL NOT PROVEN HERE is the PowerShell *runtime* behaviour:
that requires a Windows host, and `notes/windows-behavior-capture-plan.md`
records it as an open validation step.

Examples:
    python3 tool/windows_tools.py --check
"""
import argparse
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
CAPTURE_PS1 = ROOT / "tools/capture.ps1"
HALTRACE_PS1 = ROOT / "tools/haltrace.ps1"

# libpcap and pcapng file magic, in the byte order they appear on disk.
PCAP_MAGICS = ("a1b2c3d4", "d4c3b2a1", "a1b23c4d", "4d3cb2a1", "0a0d0d0a")
ERROR_ALREADY_EXISTS = 183


class GuardError(Exception):
    """A run must not proceed, or must not be called a success."""


def looks_like_capture(head):
    """Does this start with a pcap or pcapng magic number, either endianness?"""
    if len(head) < 4:
        return False
    first = head[:4].hex()
    return first in PCAP_MAGICS or bytes(reversed(head[:4])).hex() in PCAP_MAGICS


def unique_name(path, stamp):
    """`a/b.pcapng` + `20260920-101500` -> `a/b-20260920-101500.pcapng`."""
    target = Path(path)
    return str(target.with_name(f"{target.stem}-{stamp}{target.suffix}"))


def refuse_collision(path, exists):
    """An existing evidence file is refused. There is no override switch."""
    if exists:
        raise GuardError(
            f"REFUSING: {path} already exists. Captures and traces are "
            "evidence and are never overwritten. Choose another name, or "
            "re-run with -Unique.")
    return str(path)


def validate_interfaces(requested, enumerated):
    """Requested interfaces must all be on the enumerated list."""
    if not enumerated:
        raise GuardError("no USBPcap interface is present")
    if not requested:
        return tuple(enumerated)
    unknown = tuple(name for name in requested if name not in enumerated)
    if unknown:
        raise GuardError(
            "NOT AN ENUMERATED INTERFACE: " + ", ".join(unknown)
            + "; available: " + ", ".join(enumerated))
    return tuple(requested)


def capture_outcome(exit_code, exists, size, head):
    """(ok, reason). `saved:` may only be printed when ok is True."""
    if exit_code != 0:
        return False, f"tshark exited {exit_code}"
    if not exists:
        return False, "no output file"
    if size == 0:
        return False, "output is zero bytes"
    if not looks_like_capture(head):
        return False, "output does not start with a pcap or pcapng magic number"
    return True, "ok"


def should_remove_stub(ok, exists, size):
    """A failed run must not leave a zero-byte file that looks like evidence."""
    return bool(not ok and exists and size == 0)


def completion(path):
    """The size and sha256 every finished run has to print."""
    data = Path(path).read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def dbwin_conflict(handle, last_error):
    """CreateFileMapping/CreateEvent succeed on an existing object.

    The only signal that another listener already owns DBWIN is
    ERROR_ALREADY_EXISTS from GetLastError, which the previous script never
    read — so it raced DebugView for messages and reported success.
    """
    if not handle:
        raise GuardError(f"handle creation failed, error {last_error}")
    return last_error == ERROR_ALREADY_EXISTS


# ------------------------------------------------- PowerShell drift guard

def _body(path):
    """PowerShell source with only the `<# .. #>` block help removed.

    Line comments are kept here on purpose: `#` also starts a comment *inside*
    a here-string line, and haltrace.ps1's session header is written as
    literal strings that begin with `#`. Stripping them would hide the very
    text a check is looking for.
    """
    return re.sub(r"<#.*?#>", "",
                  Path(path).read_text(encoding="utf-8"), flags=re.S)


def _code(path):
    """PowerShell source with its block help and `#` comments removed.

    Use this only for "must NOT appear" checks, where a comment mentioning the
    thing would be a false positive.
    """
    return "\n".join(re.sub(r"#.*$", "", line)
                      for line in _body(path).splitlines())


def _ordered(code, problems, earlier, later, message):
    """Both must be present, and `earlier` must come first."""
    first, second = code.find(earlier), code.find(later)
    if first < 0:
        problems.append(f"missing {earlier!r}")
    elif second < 0:
        problems.append(f"missing {later!r}")
    elif first > second:
        problems.append(message)


def capture_drift(path=CAPTURE_PS1):
    code = _code(path)
    problems = []
    if re.search(r"\[switch\]\$Force", code):
        problems.append("capture.ps1 has a -Force overwrite escape")
    for magic in PCAP_MAGICS:
        if magic.upper() not in code:
            problems.append(f"capture.ps1 does not know the {magic} magic")
    for needed in ("-Unique", "$LASTEXITCODE", "Get-FileHash",
                   "NOT AN ENUMERATED INTERFACE", "REFUSING"):
        if needed not in code:
            problems.append(f"capture.ps1 no longer mentions {needed}")
    _ordered(code, problems, "REFUSING", "& $tshark @a",
             "capture.ps1 launches tshark before refusing a collision")
    # The only deletion allowed is the zero-byte stub of a failed run, which
    # happens after tshark has returned. Nothing may delete the operator's
    # existing file on the way in.
    _ordered(code, problems, "& $tshark @a", "Remove-Item",
             "capture.ps1 deletes a file before it has even run tshark")
    _ordered(code, problems, "$code = $LASTEXITCODE", "saved: $Out",
             "capture.ps1 prints `saved:` before checking the exit status")
    _ordered(code, problems, "Fail \"output is zero bytes\"", "saved: $Out",
             "capture.ps1 prints `saved:` before checking for an empty file")
    return problems


def haltrace_drift(path=HALTRACE_PS1):
    code = _body(path)
    problems = []
    for needed in ("REFUSING", "$ERROR_ALREADY_EXISTS", "GetLastWin32Error",
                   "Close-All", "Get-FileHash", "-Unique", "start_utc",
                   "end_utc", "frame.time_epoch"):
        if needed not in code:
            problems.append(f"haltrace.ps1 no longer mentions {needed}")
    if str(ERROR_ALREADY_EXISTS) not in code:
        problems.append("haltrace.ps1 does not carry ERROR_ALREADY_EXISTS "
                        f"({ERROR_ALREADY_EXISTS})")
    if "Write-Warning" in code and "Not elevated" in code:
        problems.append("haltrace.ps1 still only warns about elevation")
    if re.search(r"\$prefixes\s*=", code):
        problems.append("haltrace.ps1 still falls back to a local DBWIN name, "
                        "which captures none of the session-0 service output")
    _ordered(code, problems, "REFUSING", "Add-Type",
             "haltrace.ps1 initialises DBWIN before refusing a collision")
    _ordered(code, problems, "IsInRole", "Add-Type",
             "haltrace.ps1 initialises DBWIN before checking elevation")
    # The session artifact must exist before the listen loop, so a run that
    # records nothing still leaves something to hash.
    _ordered(code, problems, "start_utc", "$w = [Dbwin]::WaitForSingleObject",
             "haltrace.ps1 writes its session header only after listening, so "
             "a zero-event run would leave no artifact at all")
    if "no output file was created" in code:
        problems.append("haltrace.ps1 still has a no-artifact path")
    return problems


def drift():
    return ([f"capture.ps1: {item}" for item in capture_drift()]
            + [f"haltrace.ps1: {item}" for item in haltrace_drift()])


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="prove the PowerShell scripts still implement "
                             "these rules, in the right order")
    return parser.parse_args(argv)


def main(argv=None):
    parse_args(argv)
    problems = drift()
    for problem in problems:
        print(f"DRIFT {problem}")
    print(f"RESULT in_sync={not problems} drift={len(problems)}")
    print("LIMITATION these are the rules and the scripts' structure. The "
          "PowerShell runtime behaviour still requires a Windows host; see "
          "notes/windows-behavior-capture-plan.md.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
