# Ghidra workspace

This directory holds local Ghidra analysis for the ASUS/SONiX firmware. The
preserved vendor image is never modified. Generated slices and the Ghidra project
database are intentionally ignored from ordinary Git staging.

## Runtime environment

- Ghidra 12.1.2
- JDK 21
- Processor language: `ARM:LE:32:Cortex`
- Compiler specification: `default`

Headless commands use temporary XDG state so they do not modify the user's
normal Ghidra GUI preferences:

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk \
XDG_CONFIG_HOME=/tmp/falchion-ghidra-config \
XDG_CACHE_HOME=/tmp/falchion-ghidra-cache \
XDG_DATA_HOME=/tmp/falchion-ghidra-data \
ghidra-analyzeHeadless ...
```

To inspect the prepared project interactively, start `ghidra`, choose
**File > Open Project**, and select `ghidra/project/falchion-hfx.gpr`. Opening
the project is offline and does not communicate with the keyboard.

## Derived imports

All source offsets refer to `dumps/vendor/M605_V01_00_58.bin`.

| Program | Source range | Runtime base | Initial interpretation |
|---|---:|---:|---|
| `bootloader_primary.bin` | `0x01000-0x0ffff` | `0x00000000` | Primary bootloader code/data after its container page; vector at base, reset `0x000002f5` |
| `app_candidate_a.bin` | `0x11000-0x168ab` | `0x00000000` | Small application image; vector at base, reset `0x000014a9`; USB/system coordination |
| `app_candidate_b.bin` | `0x21000-0x3f753` | `0x00000000` (historical provisional import) | Original analysis retained for comparison |
| `app_candidate_b_18000000.bin` | `0x21000-0x3f753` | `0x18000000` | Byte-identical corrected mapping; keyboard behavior, configuration data, and USB identity |
| `ram_image_18038000.bin` | `0x74000-0x7bfff` | `0x18038000` | Independently executable RAM image; vector at base, reset `0x180381c1` |

Candidate B's runtime base is strongly supported as `0x18000000`. The firmware
header records that address beside flash source `0x60021000` and length
`0x1e754`; pointers such as `0x1801bff6` and `0x1801c810` then resolve to coherent
tables inside the slice. The base-zero program is retained only to preserve the
earlier analysis history. Candidate B has no vector table (it is not entered via
reset); its true runtime entry is the application `main` at `0x1800023a`, called
by Candidate A's post-scatter runtime `FUN_000002c8` after `__scatterload` copies
B to `0x18000000` (logs 79–80). `CandidateB_Start_Function` is a separate provisional
label, not the reset/entry.

## Step 6 Phase 3 project (`project-step6/`)

Phase 3 needed the *installed* 1.59 code images imported at their own bases
without disturbing the analysis history above, so it uses a separate local
project. Both `project-step6/` and the generated `inventories/` directory are
ignored; the pre-existing `project/falchion-hfx` was not opened, analyzed or
modified in that phase.

Slices are produced by `tool/extract_installed_records.py --write`, which names
each one for its record slot, logical flash source, runtime destination, length
and a short content hash, proves every output byte round-trips against the source
range it claims, and refuses to write anything unless every check passes. It
emits one complete slice per active SN_FWIN record plus the runtime image for
each scatter-copy region, so a record made of a copy source plus a compressed
tail is present in full. A complete-record slice that is not a single runtime
image is named `dstNA` and has no import base.

`tool/report_phase3.py` regenerates the Phase 3 notes and the complete mapping
JSON; `--check` fails if the committed artifacts drift from a fresh render.

| Program | Source range | Import base | Basis for that base |
|---|---:|---:|---|
| `vendor_app_a_slot0_…` | `0x11000-0x168ab` of the vendor BIN | `0x00000000` | reset vector `0x000014a9`, region table at image offset `0x5750` and its handler pointers are all base-0 offsets inside the image |
| `installed_app_a_slot0_…` | `0x11000-0x168ab` of the installed dump | `0x00000000` | same, read from the installed bytes |
| `vendor_app_b_slot1_…` | `0x21000-0x3f353` of the vendor BIN | `0x18000000` | Candidate A's scatter region 0 copies it there |
| `installed_app_b_slot1_…` | `0x21000-0x3f37f` of the installed dump | `0x18000000` | same, read from the installed region table |

Note that the Candidate B slices here are the **copy region only**, not the whole
SN_FWIN record: the record's trailing `0x400` bytes are the compressed input for
scatter region 1 and are not part of the image at `0x18000000`. That is the
difference from `app_candidate_b_18000000.bin` above, which spans the full
record.

Import (once per slice) and then report read-only:

```bash
ghidra-analyzeHeadless "$PWD/ghidra/project-step6" step6 \
  -import "$PWD/ghidra/imports/<slice>" \
  -processor ARM:LE:32:Cortex -loader BinaryLoader -loader-baseAddr <base>

ghidra-analyzeHeadless "$PWD/ghidra/project-step6" step6 \
  -process <slice> -readOnly -noanalysis \
  -scriptPath "$PWD/ghidra/scripts" -postScript FalchionFunctionInventory.java
```

`FalchionFunctionInventory.java` emits one line per function with its **real
ordered body ranges**, an exact-body hash over the concatenation of those ranges,
a masked-shape hash, constants, call degree and referenced strings. Ghidra
function bodies are not necessarily contiguous — 15 of 80 in Candidate A and 61
of 293 in Candidate B are not — so `entry..entry+size` is not the body and must
not be used as one (log 99).
`tool/match_functions.py` consumes two of those inventories and pairs functions
across releases; it reports address equality but never matches on it, so no
vendor symbol is transferred by address. Evidence:
`logs/98-installed-code-map-and-function-matching.txt`,
`notes/installed-record-load-map.md`,
`notes/vendor-to-installed-functions.md`.

## Recovered KBID maps

Candidate B uses an effective KBID selector at `0x1801ee6c`. Candidate A's
26-byte lookup at runtime `0x00004fcd` yields `0`, `1`, or `4`; Candidate B
normalizes `4` to `2`, leaving exactly three selectors.

- `0x1801c37c`: three 189-byte logical wire-ID windows, selector stride `0x86`;
  adjacent windows overlap by 55 bytes.
- `0x1801c50e`: three 256-byte scan-position rows, selector stride `0x100`.
- `0x1801c50e-0x1801c544`: storage shared by selector 2's wire-window tail and
  scan-position row 0.
- `0x180202ac + layer*0xd84 + record_index*0x20`: runtime record calculation
  used by the dispatcher; the record contents are outside the embedded
  Candidate B payload.

`tool/analyze_candidate_b_tables.py` reproduces the lookup, logical windows,
record addresses, translation rules, and scan-map hashes from the official BIN.
`FalchionKbidMapReport.java` preserves the corresponding corrected-base Ghidra
evidence.

## Evidence-supported Candidate B labels

The corrected-base program currently includes these conservative user labels:

- `0x18000a70` — `VendorHID_SendResponse64`
- `0x18001f6e` — `IsKeyUnsupportedForLayer`
- `0x18001fbe` — `VendorHID_CommandDispatcher`

The report and label scripts under `ghidra/scripts/` are reproducible. Report
scripts are intended for `-readOnly -noanalysis`; the label script changes only
the ignored local Ghidra project database.

## Safety

Opening or analyzing these files in Ghidra is host-only and read-only with
respect to the keyboard. Do not use the vendor updater, enter bootloader PID
`1b7f`, or flash any derived/modified binary during preservation work.
