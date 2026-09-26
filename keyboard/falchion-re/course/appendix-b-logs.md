# Appendix B: Every log, grouped by lesson

The numbered files in [`logs/`](../logs/) are the investigation's **lab notebook**. Each one records the exact commands run and their output. [`logs/COMMANDS.md`](../logs/COMMANDS.md) is the official command-to-log index, and [`logs/SHA256SUMS`](../logs/SHA256SUMS) lets you check that none of them was altered (`cd logs && sha256sum -c SHA256SUMS`).

Logs are never edited after the fact. When a log turned out to be wrong, a **later** log corrected it, and both are kept. There is no log 129.

[Course home](README.md)

---

## Lesson 4: USB and HID (2026-08-29, read-only Linux inspection)
| Log | What it shows |
|---|---|
| [00](../logs/00-host-context.txt) | Host context: date, kernel, OS |
| [01](../logs/01-lsusb.txt) | `lsusb` **failed in the sandbox**. This was an environment problem, not a device result. |
| [02](../logs/02-lsusb-tree.txt) | USB topology and driver bindings |
| [03](../logs/03-tool-availability.txt) | Which USB/HID/fwupd tools exist (fwupd is absent) |
| [04](../logs/04-usb-sysfs-devices.txt) | The keyboard found at `6-2`, `0b05:1b7e`, bcdDevice 1.59 |
| [05](../logs/05-usb-sysfs-interfaces.txt) | Five HID interfaces, with interface 4 unbound |
| [06](../logs/06-hidraw-sysfs.txt) | hidraw0–3 mapped to interfaces 0–3 |
| [07](../logs/07-falchion-usb-descriptors-sysfs-xxd.txt) | Raw cached USB descriptors (159 bytes) |
| [08](../logs/08-falchion-endpoints-sysfs.txt) | Endpoint layout |
| [09](../logs/09-falchion-hid-report-descriptors-xxd.txt) | Raw HID report descriptors for interfaces 0–3 |
| [10](../logs/10-falchion-udev-properties.txt) | udev properties |
| [11](../logs/11-dfu-util-list.txt) | `dfu-util` failed in the sandbox. This was not a DFU result. |
| [12](../logs/12-fwupd-availability.txt) | fwupd not installed |
| [13](../logs/13-interface-4-and-kernel-log.txt) | Why interface 4 is unbound: it has no input interrupt endpoint |
| [14](../logs/14-usbhid-dump-help.txt) | usbhid-dump help only |
| [15](../logs/15-lsusb-falchion-verbose.txt) | Full `lsusb -v`, the authoritative descriptor listing |
| [16](../logs/16-dfu-util-list-direct.txt) | Direct `dfu-util -l`: **no DFU target** |
| [17](../logs/17-prior-report-descriptor-comparison.txt) | Comparison with the older repository captures |
| [18](../logs/18-device-node-metadata.txt) | `/dev` nodes hidden by the sandbox |
| [19](../logs/19-port-retry-sysfs-devices.txt)–[24](../logs/24-port-retry-cached-descriptors.txt) | The same inspection repeated through the **other connector** |
| [25](../logs/25-port-retry-comparison.txt) | A false "DIFFERENT" caused by parsing xxd's ASCII column (superseded) |
| [26](../logs/26-port-retry-corrected-comparison.txt) | The corrected comparison: identical apart from the device address |

## Lessons 3 and 5: auditing earlier work
| Log | What it shows |
|---|---|
| [27](../logs/27-claude-notes-report-desc-provenance.txt) | The old `report-desc-0.txt` matches no current descriptor, so its interface-4 attribution is unsupported |
| [28](../logs/28-claude-progress-audit.txt) | An inventory of earlier progress and missing work |

## Lesson 6: the ASUS package and the firmware file
| Log | What it shows |
|---|---|
| [29](../logs/29-asus-package-original-metadata.txt) | The ZIP's SHA-256 matches ASUS's published hash |
| [30](../logs/30-asus-package-archive-list.txt) / [31](../logs/31-asus-package-extracted-inventory.txt) / [32](../logs/32-asus-package-firmware-focused-inventory.txt) | Package inventory. Found the 1.00.58 BIN and bootloader PID `1b7f`. |
| [33](../logs/33-asus-firmware-image-static-analysis.txt) | Strings, byte histogram, and entropy: the image isn't encrypted |
| [34](../logs/34-asus-updater-and-container-static-analysis.txt) | The updater is a proprietary HID erase/program tool |
| [35](../logs/35-official-artifact-preservation.txt) | ZIP and BIN copied into the repo and verified byte for byte |
| [36](../logs/36-firmware-layout-analyzer.txt) | First run of `analyze_sonix_firmware.py`: the layout map |
| [37](../logs/37-firmware-modification-feasibility.txt) | Dual Cortex-M3, plain USB identity tables, patchability |
| [43](../logs/43-firmware-layout-with-ram-image.txt) | Layout rerun with the `0x74000` RAM image added |
| [46](../logs/46-documentation-synchronization-audit.txt) | Documentation sync audit |

## Lesson 8: Ghidra
| Log | What it shows |
|---|---|
| [38](../logs/38-ghidra-preinstall-check.txt) / [39](../logs/39-ghidra-install-verification.txt) | Installing and verifying Ghidra 12.1.2 and JDK 21 |
| [40](../logs/40-ghidra-seed-entries.txt) / [41](../logs/41-ghidra-entry-reanalysis.txt) / [42](../logs/42-ghidra-project-report.txt) | First import, entry labels, and a project report |
| [44](../logs/44-ghidra-candidate-b-label-correction.txt) | `CandidateB_Entry` renamed to the evidence-bounded `CandidateB_Start_Function` |
| [45](../logs/45-ghidra-synchronized-project-report.txt) | Read-only confirmation |
| [47](../logs/47-ghidra-candidate-b-opcode-search.txt) / [48](../logs/48-ghidra-candidate-b-dispatcher-report.txt) / [49](../logs/49-ghidra-candidate-b-key-remap-report.txt) | Finding the vendor-HID dispatcher and the `51 21`/`51 22` handler |
| [50](../logs/50-firmware-pointer-byte-search.txt) | Binary pointer search (regenerated after a shell-escaping bug) |
| [51](../logs/51-ghidra-key-ram-reference-report.txt)–[53](../logs/53-ghidra-candidate-b-reserved-key-gate-report.txt) | Key-config RAM, the `R_NSK_M` skip, and the 6-vs-57 unsupported-key predicate |
| [54](../logs/54-ghidra-protocol-labels.txt) / [55](../logs/55-offline-protocol-analysis-audit.txt) / [56](../logs/56-timeline-document-audit.txt) | Labels and audits |
| [57](../logs/57-ghidra-runtime-key-table-reference-scan.txt)–[61](../logs/61-candidate-b-table-analysis.txt) | Recovering the 189-byte translation table and the 6+57 policy words |
| [62](../logs/62-ghidra-candidate-b-runtime-base-import.txt)–[66](../logs/66-candidate-b-runtime-mapping-audit.txt) | **Re-importing Candidate B at `0x18000000`**, after which the pointers make sense |
| [67](../logs/67-ghidra-candidate-b-kbid-map-report.txt)–[71](../logs/71-kbid-layout-analysis-audit.txt) | KBID windows. The "eight rows" reading was corrected to three overlapping windows. |

## Lessons 9 and 10: checksums and boot
| Log | What it shows |
|---|---|
| [72](../logs/72-ghidra-candidate-a-loader-report.txt) / [73](../logs/73-ghidra-candidate-a-scatter-handler-report.txt) | Candidate A reset handler and the scatter-load table |
| [74](../logs/74-candidate-integrity-crc-analysis.txt) | Record A = plain CRC-32. Record B matches nothing tried. |
| [75](../logs/75-ghidra-bootloader-verify-report.txt) / [76](../logs/76-candidate-integrity-resolved.txt) | The bootloader's verify code read; **all four integrity fields reproduced** |
| [77](../logs/77-image-builder-roundtrip.txt) | First builder round trip (its wording was later narrowed) |
| [78](../logs/78-boot-structures.txt) | Boot container structures decoded |
| [79](../logs/79-ghidra-candidate-a-handoff.txt) / [80](../logs/80-ghidra-candidate-b-entry.txt) | Candidate B's entry `0x1800023a`, "welcome to main" |
| [101](../logs/101-boot-acceptance-resolved.txt)–[103](../logs/103-phase4-prose-and-policy-corrections.txt) | All boot-acceptance gates enumerated, then corrected after review |
| [120](../logs/120-recovery-key-combination.txt) | Which keys trigger recovery |
| [123](../logs/123-address-zero-remap.txt) | Address 0: there is no remap |

## Lessons 11 and 12: the bootloader and the backup
| Log | What it shows |
|---|---|
| [81](../logs/81-ghidra-bootloader-write-protocol.txt) | Erase/read/program commands, statically |
| [82](../logs/82-ghidra-bootloader-framing.txt) | The 64-byte wire framing (its single-channel assumption was later corrected) |
| [83](../logs/83-backup-tool-dryrun.txt) | Backup tool dry run |
| [84](../logs/84-correction-audit.txt) | Correction pass: batched queries were fatal |
| [85](../logs/85-bootloader-read-scheduling-analysis.txt) | The READ race is **proven possible**, and busy polling can't sequence it |
| [86](../logs/86-bootloader-read-handshake-correction.txt) | The first fix was also wrong. The sample→status→confirm handshake closes the gap. |
| [87](../logs/87-bootloader-entry-recovery-and-preflight.txt) | The exact bootloader-entry report recovered offline |
| [88](../logs/88-live-bootloader-entry-and-passive-validation.txt) | **Live** (owner approved): the keyboard became `1b7f` |
| [89](../logs/89-bootloader-split-channel-correction.txt) | The first probe timed out. Commands go on FF01 and replies come on FF00. |
| [90](../logs/90-live-split-channel-status-buffer-probe.txt) | **Live**: the corrected split-channel probe passed |
| [91](../logs/91-one-block-read-validation.txt) | **Live**: one 48-byte READ at `0x10000` |
| [92](../logs/92-full-app-region-backup.txt) | **Live**: three identical full application-region reads, the verified backup |

## Lesson 13: installed vs vendor
| Log | What it shows |
|---|---|
| [93](../logs/93-step6-offline-custom-firmware-plan.txt) | The Step 6 phase plan written |
| [94](../logs/94-version-aware-image-format-library.txt) / [95](../logs/95-phase1-record-scan-correction.txt) | The shared parser, and its record-scan correction (a hole is not a terminator) |
| [96](../logs/96-installed-vs-vendor-comparison.txt) / [97](../logs/97-phase2-review-corrections.txt) | Byte-exact comparison, plus five review fixes |
| [98](../logs/98-installed-code-map-and-function-matching.txt) / [99](../logs/99-phase3-review-corrections.txt) | Function matching with the `+0x2c` shift, and discontiguous bodies |

## Lesson 14: tasks and USB inside
| Log | What it shows |
|---|---|
| [100](../logs/100-installed-hardware-interface-map.txt) | Vector table, MMIO census, and reachability |
| [104](../logs/104-phase5a-pointer-tables-and-reachability.txt) | Pointer tables (two were later shown to be false) |
| [105](../logs/105-decompressed-region-reconstruction.txt) | The decompressed region is the USB descriptor set |
| [106](../logs/106-phase5a-task-entries-and-new-baseline.txt) | Five RTOS tasks, and a new reachability baseline |
| [107](../logs/107-phase5b-usb-routing.txt) / [108](../logs/108-phase5b-prose-correction.txt) | USB routing, and the interface-4 byte-identity wording corrected |

## Lesson 15: keys, magnets, second core
| Log | What it shows |
|---|---|
| [109](../logs/109-phase5c-scan-scheduling.txt) | IRQ38 → service task → report buffers |
| [110](../logs/110-phase5d-hall-acquisition.txt) | Actuation `>=100` recovered, acquisition not |
| [113](../logs/113-phase5g-and-final-dependency-map.txt) / [114](../logs/114-phase5g-watchdog-correction.txt) | Watchdogs, multicore token, the dependency gate, and the watchdog correction |
| [118](../logs/118-second-context-image-analysis.txt) | The second execution context and its mailbox |
| [119](../logs/119-mailbox-client-and-sample-flow.txt) | Samples cross the mailbox: **the Hall gate closes** |
| [121](../logs/121-calibration-lifecycle.txt) | Calibration: defaults, drift tracking, nothing persisted |

## Lesson 16: settings, lights, saving
| Log | What it shows |
|---|---|
| [111](../logs/111-phase5e-nonvolatile-settings.txt) | `50 55` only queues. The erase path and the omission proof. |
| [112](../logs/112-phase5f-rgb-lamparray.txt) | LampArray feature reports → 6×17×3 frame |
| [122](../logs/122-rgb-driver-hunt.txt) | Driver still not found. Double buffering and frame timing recovered. |
| [125](../logs/125-profile-format.txt) | The full profile format, matched against Armoury Crate |

## Lesson 17: polling rate
| Log | What it shows |
|---|---|
| [124](../logs/124-polling-rate-path.txt) | No consumer found (a bounded negative) |
| [126](../logs/126-polling-rate-capture-analysis.txt) | `51 31` on the wire, and the rate measured from report timing |
| [127](../logs/127-polling-rate-reader.txt) | The reader was `key_state+2`, and IRQ38 gets a period |

## Lesson 18: command map and building
| Log | What it shows |
|---|---|
| [115](../logs/115-phase6-development-strategy.txt) | Strategy decided: Path A first |
| [116](../logs/116-phase7-offline-builder.txt) | The offline builder and fourteen refusals |
| [117](../logs/117-phase8-first-experimental-artefact.txt) | The first UNTESTED artefact (product string) |
| [128](../logs/128-vendor-command-map.txt) / [130](../logs/130-command-map-completion.txt) | The complete vendor command surface |

## Lesson 19: the correction logs
| Log | What it shows |
|---|---|
| [131](../logs/131-pointer-root-and-windows-capture-tooling-corrections.txt) | False tables (format strings, a powers-of-ten table) and the Windows tool bugs |
| [132](../logs/132-provenance-boundary-repair-and-bus-scoped-decode.txt) | Provenance, the code the last fix deleted, and bus-scoped USB identity |
| [133](../logs/133-path-correlated-proof-and-inert-seed-remover.txt) | Path-correlated proof, and the seed remover made inert |
| [134](../logs/134-pointer-alias-invalidation.txt) | Alias invalidation: "an identity is a name, not an address" |
