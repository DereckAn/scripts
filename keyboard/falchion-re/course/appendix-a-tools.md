# Appendix A: Every tool explained

Each tool in this project is listed below with what it does, why it was written, which log first recorded its result, and the lesson that explains it. The descriptions summarize each script's own docstring (run `python3 -c "import ast;print(ast.get_docstring(ast.parse(open('tool/NAME.py').read())))"` to read one in full).

**Three kinds of tools.** The icons tell you how careful to be:

| Mark | Meaning |
|---|---|
| **offline** | Reads saved files only. Safe to run anytime. |
| **LIVE-capable** | Can talk to the real keyboard, but only with explicit flags. Its default is a dry run. **Don't use the live flags unless you mean to.** |
| **Windows** | A PowerShell script meant for the Windows/Armoury Crate machine. |

Almost every `tool/NAME.py` has a matching `tool/test_NAME.py`. Those tests are offline and use saved images or fakes. Running them (for example `python3 -m pytest tool/test_falchion_image.py`) is a good way to see what each tool promises.

[Course home](README.md)

---

## Firmware file and integrity (Lessons 6, 9, 10)

| Tool | Kind | What it does | Why it exists | First log | Lesson |
|---|---|---|---|---|---|
| [`analyze_sonix_firmware.py`](../tool/analyze_sonix_firmware.py) | offline | Structural inspection of the SNC7320 image: markers, vector-table candidates, regions. Unproven field names are labelled "candidates". | It was the first map of the 496 KiB file | 36 | [6](06-the-firmware-file.md) |
| [`analyze_candidate_integrity.py`](../tool/analyze_candidate_integrity.py) | offline | Recomputes both SN_FWIN record checksums (a sum of per-`0x10000`-chunk CRC-32s) and the additive word-sums, then asserts them against the stored values | It proved the integrity is recomputable, not a signature | 74–76 | [9](09-checksums-and-trust.md) |
| [`analyze_boot_structures.py`](../tool/analyze_boot_structures.py) | offline | Decodes SNC7320A / SN_BCFG / SN_FWIN and the known boot checks. Works on the full image (base 0) or the app-only dump (base `0x10000`). Passing does **not** prove the image boots. | It checked the boot constraints before any patch | 78 | [10](10-how-it-boots.md) |
| [`analyze_boot_acceptance.py`](../tool/analyze_boot_acceptance.py) | offline | Reproduces the bootloader's four accept gates from the bootloader copy inside the installed dump | It resolved `FUN_000029d4` and the `0x60011000` entry rule | 101 | [10](10-how-it-boots.md) |
| [`analyze_candidate_b_tables.py`](../tool/analyze_candidate_b_tables.py) | offline | Decodes Candidate B's key translation table, KBID windows, scan maps, and unsupported-key policy lists | It explained the "echoed but ignored" Fn remaps | 57–71 | [5](05-talking-to-the-keyboard.md), [8](08-ghidra.md) |
| [`build_modified_image.py`](../tool/build_modified_image.py) | offline | The first patch builder, locked to vendor 1.00.58. It recomputes checksums after a Candidate-B patch. Kept unchanged so log 77 can be reproduced. | Roadmap step 1 | 77 | [9](09-checksums-and-trust.md) |

## Bootloader and backup (Lessons 11, 12)

| Tool | Kind | What it does | Why it exists | First log | Lesson |
|---|---|---|---|---|---|
| [`enter_bootloader.py`](../tool/enter_bootloader.py) | **LIVE-capable** | Sends ASUS's exact reset-only report (`7b aa 41 53 55 53 aa` + zeros) so the keyboard re-enumerates as `1b7f`. Dry run by default. Live mode needs `--run` **and** `--acknowledge-reset`. | It entered bootloader mode without the ASUS updater | 87–88 | [11](11-the-bootloader-door.md) |
| [`probe_bootloader.py`](../tool/probe_bootloader.py) | **LIVE-capable** | A minimal status-and-length query probe in bootloader mode | It confirmed the split FF01/FF00 channel | 89–90 | [11](11-the-bootloader-door.md) |
| [`probe_flash_read.py`](../tool/probe_flash_read.py) | **LIVE-capable** | Reads exactly one 48-byte block at `0x10000` with the proven handshake | It validated one read before the full backup | 91 | [12](12-the-race-and-the-backup.md) |
| [`backup_firmware.py`](../tool/backup_firmware.py) | **LIVE-capable** | Reads the application region `[0x10000,0x7c000)` in 48-byte chunks using the sample→status→confirm handshake. Its tests use a `FakeBootloader`. | It made the verified backup | 83 (dry run), 92 (live) | [12](12-the-race-and-the-backup.md) |

## Comparing releases and mapping code (Lessons 13, 14)

| Tool | Kind | What it does | Why it exists | First log | Lesson |
|---|---|---|---|---|---|
| [`falchion_image.py`](../tool/falchion_image.py) | offline | **The** shared image parser. It keeps parsing, validation, and the source allowlist separate, and it translates offsets in exactly one place. | So no two tools disagree about the format | 94 | [13](13-installed-vs-vendor.md) |
| [`compare_firmware_images.py`](../tool/compare_firmware_images.py) | offline | Byte-exact diff of installed 1.59 against vendor 1.00.58 over the same logical range. It reports *what* changed, never *why*. | Phase 2 | 96 | [13](13-installed-vs-vendor.md) |
| [`extract_installed_records.py`](../tool/extract_installed_records.py) | offline | Slices the installed records into Ghidra imports and proves every byte round-trips | Phase 3 | 98 | [13](13-installed-vs-vendor.md) |
| [`match_functions.py`](../tool/match_functions.py) | offline | Pairs functions across releases by body bytes, shape, constants, and strings, **never an address alone** | Phase 3 | 98 | [13](13-installed-vs-vendor.md) |
| [`report_phase3.py`](../tool/report_phase3.py) / [`report_phase4.py`](../tool/report_phase4.py) / [`report_phase5.py`](../tool/report_phase5.py) | offline | Regenerate the phase notes byte-identically. `--check` fails if the notes have drifted. | Reproducible notes | 99 / 101 / 100 | [13](13-installed-vs-vendor.md) |
| [`map_hardware_interfaces.py`](../tool/map_hardware_interfaces.py) | offline | Vector table, MMIO census, and reachability from the vector entries | Phase 5 first pass | 100 | [14](14-inside-tasks-and-usb.md) |
| [`find_pointer_tables.py`](../tool/find_pointer_tables.py) | offline | Finds runs of function pointers the call graph can't follow. Later tightened so shape alone never makes a root (log 131). | Phase 5A | 104 | [14](14-inside-tasks-and-usb.md) |
| [`reconstruct_decompress.py`](../tool/reconstruct_decompress.py) | offline | Decodes the compressed scatter region using a translation of the firmware's own decompressor | It revealed the USB descriptor set | 105 | [14](14-inside-tasks-and-usb.md) |
| [`harvest_task_entries.py`](../tool/harvest_task_entries.py) | offline | Turns RTOS task-creation call sites into validated entry points | Task entries live in registers, not tables | 106 | [14](14-inside-tasks-and-usb.md) |
| [`map_usb_routing.py`](../tool/map_usb_routing.py) | offline | Links descriptors, endpoints, and report producers | Phase 5B | 107 | [14](14-inside-tasks-and-usb.md) |

## How it works inside (Lessons 10, 15, 16, 17)

| Tool | Kind | What it does | First log | Lesson |
|---|---|---|---|---|
| [`map_scan_pipeline.py`](../tool/map_scan_pipeline.py) | offline | IRQ38 tick → service task → report buffers, with a confidence on every link | 109 | [15](15-inside-keys-and-magnets.md) |
| [`model_hall_actuation.py`](../tool/model_hall_actuation.py) | offline | **Runs** the recovered actuation arithmetic (≥100 down, 0 up, hold band) | 110 | [15](15-inside-keys-and-magnets.md) |
| [`map_platform_dependencies.py`](../tool/map_platform_dependencies.py) | offline | Clocks, watchdogs, faults, multicore, and the services dependency gate | 113–114 | [15](15-inside-keys-and-magnets.md) |
| [`map_second_context.py`](../tool/map_second_context.py) | offline | Analyses the `0x18038000` second-context image and its mailbox | 118 | [15](15-inside-keys-and-magnets.md) |
| [`map_sample_flow.py`](../tool/map_sample_flow.py) | offline | Traces per-key samples across the mailbox into the travel array | 119 | [15](15-inside-keys-and-magnets.md) |
| [`map_recovery_keys.py`](../tool/map_recovery_keys.py) | offline | Decodes the bootloader's recovery key pattern to key positions | 120 | [10](10-how-it-boots.md) |
| [`map_calibration_flow.py`](../tool/map_calibration_flow.py) | offline | Per-key calibration defaults, drift tracking, and settling | 121 | [15](15-inside-keys-and-magnets.md) |
| [`map_address_zero.py`](../tool/map_address_zero.py) | offline | Shows there is no address-0 remap | 123 | [10](10-how-it-boots.md) |
| [`map_nonvolatile_writes.py`](../tool/map_nonvolatile_writes.py) | offline | The `50 55` commit path, traced as a byte pattern the firmware compares against (it constructs nothing) | 111 | [16](16-settings-lights-saving.md) |
| [`map_rgb_lamparray.py`](../tool/map_rgb_lamparray.py) | offline | LampArray feature reports → frame buffer | 112 | [16](16-settings-lights-saving.md) |
| [`map_rgb_driver_hunt.py`](../tool/map_rgb_driver_hunt.py) | offline | The search for the LED hardware driver: double buffering and frame timing | 122 | [16](16-settings-lights-saving.md) |
| [`map_profile_format.py`](../tool/map_profile_format.py) | offline | Profile/settings format and the 16-bit checksum, matched against the Armoury Crate decode | 125 | [16](16-settings-lights-saving.md) |
| [`map_polling_rate.py`](../tool/map_polling_rate.py) | offline | The first polling-rate search, which ended in a bounded negative | 124 | [17](17-polling-rate.md) |
| [`map_polling_rate_protocol.py`](../tool/map_polling_rate_protocol.py) | offline | Decodes `51 31` from the Armoury Crate capture after checking the capture's SHA-256 | 126 | [17](17-polling-rate.md) |
| [`map_polling_rate_reader.py`](../tool/map_polling_rate_reader.py) | offline | Finds the reader of the rate multiplier and the IRQ38 period | 127 | [17](17-polling-rate.md) |
| [`decode_capture.py`](../tool/decode_capture.py) | offline | Pulls the 64-byte vendor reports out of a USBPcap capture, scoped by bus. It's the offline twin of `decode.ps1`. | 131 | [5](05-talking-to-the-keyboard.md), [17](17-polling-rate.md) |

## Building firmware (Lesson 18)

| Tool | Kind | What it does | First log | Lesson |
|---|---|---|---|---|
| [`map_vendor_commands.py`](../tool/map_vendor_commands.py) | offline | The complete vendor-HID command surface, read from the dispatcher's own compare instructions. It constructs no frame. | 128, 130 | [18](18-commands-and-building.md) |
| [`report_development_strategy.py`](../tool/report_development_strategy.py) | offline | Generates the strategy decision record (Path A first) | 115 | [18](18-commands-and-building.md) |
| [`build_offline_image.py`](../tool/build_offline_image.py) | offline | The Phase 7 builder: two adapters, fourteen refusal classes, **no device code** (tested) | 116 | [18](18-commands-and-building.md) |
| [`verify_patched_region.py`](../tool/verify_patched_region.py) | offline | An independent validator that imports nothing from the builder and re-decodes and re-checks on its own | 117 | [18](18-commands-and-building.md) |

## Windows side (Lesson 5)

| Script | Kind | Writes to keyboard? | Purpose | Offline twin |
|---|---|---|---|---|
| [`tools/capture.ps1`](../tools/capture.ps1) | Windows (admin) | no | Starts a passive USBPcap capture. Log 131 fixed its overwrite and false-`saved:` bugs. | `tool/windows_tools.py` |
| [`tools/decode.ps1`](../tools/decode.ps1) | Windows | no | Pulls the vendor reports out of a capture. Before log 131 it decoded nothing. | `tool/decode_capture.py` |
| [`tools/snap-config.ps1`](../tools/snap-config.ps1) | Windows | no | Snapshots and diffs Armoury Crate profiles. It used to compare only 1,360 of 1,500 paths. | `tool/profile_diff.py` |
| [`tools/haltrace.ps1`](../tools/haltrace.ps1) | Windows (admin) | no | Captures the ASUS HAL debug log. It used to race DebugView without noticing. | `tool/windows_tools.py` |
| [`tools/keywatch.ps1`](../tools/keywatch.ps1) | Windows | no | Shows the real vk/scan code of a key press | none |
| [`tools/send.ps1`](../tools/send.ps1) | Windows | **YES** | Sends a raw 64-byte command. **Not approved** without a separate write-test plan. | none |

See [`tools/README.md`](../tools/README.md) for what the offline twins do and don't prove. In short, they prove the *rules*, not the PowerShell itself.

## Ghidra scripts

[`ghidra/scripts/`](../ghidra/scripts/) holds 37 Java scripts, run headless and mostly with `-readOnly -noanalysis`. Each one produced a report log. For example, `FalchionBootloaderVerifyReport.java` produced log 75, `FalchionCandidateALoaderReport.java` produced log 72, `FalchionFunctionInventory.java` fed `match_functions.py` (log 98), and `FalchionPeripheralMap.java` produced the MMIO census (log 100). **`FalchionRemoveSeeds.java` is deliberately disabled**: its destructive calls deleted real code in log 131, so log 133 made it refuse to run. [Lesson 8](08-ghidra.md) explains how the scripts are used.
