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
earlier analysis history. Candidate B still has no vector or verified true entry
path; `CandidateB_Start_Function` is intentionally not named as an entry/reset.

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
