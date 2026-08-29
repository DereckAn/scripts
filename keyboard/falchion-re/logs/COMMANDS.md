# Command-to-log manifest

All commands below were run on 2026-08-29. Device-facing access was read-only. Shell loops only aggregate kernel/sysfs metadata.

| Log | Command or command group | Result / note |
|---|---|---|
| `00-host-context.txt` | `date --iso-8601=seconds`; `uname -a`; `cat /etc/os-release` | Host context |
| `01-lsusb.txt` | `lsusb` | Failed in sandbox: `unable to initialize libusb: -99` |
| `02-lsusb-tree.txt` | `lsusb -t` | Kernel USB topology and bindings |
| `03-tool-availability.txt` | `command -v` for USB/HID/fwupd tools; `lsusb --version`; `dfu-util --version`; `fwupdmgr --version` | fwupd tools absent |
| `04-usb-sysfs-devices.txt` | Loop over `/sys/bus/usb/devices/*`, reading device attributes | Found Falchion at `6-2`, `0b05:1b7e` |
| `05-usb-sysfs-interfaces.txt` | Loop over USB interface sysfs attributes and driver symlinks | Five HID interfaces; interface 4 unbound |
| `06-hidraw-sysfs.txt` | Loop over `/sys/class/hidraw/hidraw*`, reading links and `uevent` | Maps hidraw0–3 to Falchion interfaces 0–3; exit 1 because sandbox hides `/dev` nodes |
| `07-falchion-usb-descriptors-sysfs-xxd.txt` | `xxd -g 1 /sys/bus/usb/devices/6-2/descriptors` | Kernel-cached raw USB descriptors |
| `08-falchion-endpoints-sysfs.txt` | Loop over `6-2:1.*/ep_*` endpoint attributes | Endpoint layout |
| `09-falchion-hid-report-descriptors-xxd.txt` | `xxd -g 1` on hidraw0–3 sysfs `report_descriptor` files | Cached report descriptors for bound interfaces |
| `10-falchion-udev-properties.txt` | `udevadm info --query=all` for hidraw0–3 and USB device 6-2 | Existing udev properties only |
| `11-dfu-util-list.txt` | `dfu-util -l` | Sandbox attempt failed at libusb initialization; not a detection result |
| `12-fwupd-availability.txt` | `command -v`; `pacman -Q fwupd`; `systemctl status fwupd.service` | Package/binaries absent; system bus restricted |
| `13-interface-4-and-kernel-log.txt` | Read interface 4 `uevent`; query relevant `journalctl -k -b` lines | Kernel rejected OUT-only HID interface for lack of input interrupt endpoint |
| `14-usbhid-dump-help.txt` | `usbhid-dump --help` | Help only; no device access |
| `15-lsusb-falchion-verbose.txt` | `lsusb -d 0b05:1b7e -v` | Approved direct read-only descriptor/status queries; success |
| `16-dfu-util-list-direct.txt` | `dfu-util -l` | Approved direct read-only enumeration; success, no DFU targets listed |
| `17-prior-report-descriptor-comparison.txt` | `sed`, `wc`, and `sha256sum` on prior repository captures | Historical descriptor comparison |
| `18-device-node-metadata.txt` | `ls -l` and `stat` on expected `/dev` nodes | Nodes hidden by sandbox; no permissions changed |
| `19-port-retry-sysfs-devices.txt` | Read ASUS USB device attributes from sysfs after reconnecting | Falchion re-enumerated as bus 006 device 008 |
| `20-port-retry-sysfs-interfaces.txt` | Read ASUS USB interface attributes and driver links from sysfs | Same five HID interfaces and bindings |
| `21-port-retry-lsusb-tree.txt` | `lsusb -t` | Same topology/interface layout; new transient address |
| `22-port-retry-lsusb-verbose.txt` | `lsusb -d 0b05:1b7e -v` | Approved direct read-only descriptor/status retry |
| `23-port-retry-dfu-util-list.txt` | `dfu-util -l` | Approved direct read-only retry; no DFU target |
| `24-port-retry-cached-descriptors.txt` | Hash/hex-dump cached USB and Falchion HID report descriptors | Fresh byte evidence |
| `25-port-retry-comparison.txt` | Initial text reconstruction and diff | USB `DIFFERENT` line is a parser false positive; superseded |
| `26-port-retry-corrected-comparison.txt` | Strict two-hex-digit extraction and comparison | USB and interfaces 0–3 report descriptors identical; verbose diff only address |
| `27-claude-notes-report-desc-provenance.txt` | Reconstruct old `report-desc-0.txt` bytes and compare against all current cached hidraw descriptors | No match; old interface-4 attribution is unsupported |
| `28-claude-progress-audit.txt` | Inventory Falchion files/commits/artifacts/tools and locate safety-sensitive guide lines | Earlier progress and missing work audit |
| `29-asus-package-original-metadata.txt` | `stat`, `file`, and `sha256sum` on the untouched ASUS ZIP | Hash exactly matches ASUS publication |
| `30-asus-package-archive-list.txt` | `7z l -slt` on the ASUS ZIP | Read-only archive inventory |
| `31-asus-package-extracted-inventory.txt` | `find`, `file`, and `sha256sum` over the extracted package | Full extracted-file inventory |
| `32-asus-package-firmware-focused-inventory.txt` | Inventory/hash firmware subtree and read INI/version metadata | Located 1.00.58 BIN and bootloader PID 1b7f |
| `33-asus-firmware-image-static-analysis.txt` | `xxd`, `strings`, signature search, byte histogram, entropy/compression estimates | Static firmware-format evidence; no execution |
| `34-asus-updater-and-container-static-analysis.txt` | Marker/offset mapping plus `objdump` and `strings` on updater components | Proprietary HID erase/program updater identified |
| `35-official-artifact-preservation.txt` | `mkdir -p`; non-overwriting `cp --preserve=timestamps`; `cmp --silent`; `stat`; `sha256sum` | Official ZIP and 1.00.58 BIN copied locally and verified byte-for-byte; no keyboard access |
| `36-firmware-layout-analyzer.txt` | `python3 keyboard/falchion-re/tool/analyze_sonix_firmware.py` | Reproducible read-only container, CRC, vector, duplicate-region, and fill map |
| `37-firmware-modification-feasibility.txt` | `xxd`, `strings`, `objdump`, `llvm-mc`, temporary `/tmp` ELF wrapping, Python CRC/pointer scans, and SONiX-domain web searches | Dual Cortex-M3 roles, plain USB identity tables, updater integrity behavior, and modification blockers |
| `38-ghidra-preinstall-check.txt` | `command -v`; `pacman -Si`; `pacman -Q`; `java -version`; `archlinux-java status`; official Ghidra/Arch documentation search | Ghidra and JDK package availability checked; nothing installed |
| `39-ghidra-install-verification.txt` | `pacman -Q`; `command -v`; `readlink -f`; JDK 21 `java -version` | Verified installed Ghidra 12.1.2-2.1, headless launcher, and JDK 21.0.11 |
| `40-ghidra-seed-entries.txt` | `ghidra-analyzeHeadless -process ... -noanalysis -postScript FalchionSeedEntries.java` for four derived programs | Added only verified entry/vector labels to the local project; created missing candidate A/B entry functions; source BIN and keyboard untouched |
| `41-ghidra-entry-reanalysis.txt` | `ghidra-analyzeHeadless -process ...` for candidates A and B | Reanalysis completed and saved; one isolated candidate-B decode warning recorded |
| `42-ghidra-project-report.txt` | `ghidra-analyzeHeadless -process ... -readOnly -noanalysis -postScript FalchionProjectReport.java` for four programs | Verified language, memory blocks, entry recognition, function/instruction counts, and relevant strings |
| `43-firmware-layout-with-ram-image.txt` | `python3 tool/analyze_sonix_firmware.py` | Read-only parser rerun after adding the verified `0x74000` RAM-image vector |
| `44-ghidra-candidate-b-label-correction.txt` | `ghidra-analyzeHeadless -process app_candidate_b.bin -noanalysis -postScript FalchionSeedEntries.java` | Renamed the provisional local Ghidra function from `CandidateB_Entry` to the evidence-bounded `CandidateB_Start_Function`; source BIN and keyboard untouched |
| `45-ghidra-synchronized-project-report.txt` | `ghidra-analyzeHeadless -process ... -readOnly -noanalysis -postScript FalchionProjectReport.java` for four programs | Confirmed synchronized analysis labels and memory mappings in explicit read-only mode |
| `46-documentation-synchronization-audit.txt` | `date`; `git status`; firmware SHA-256; read-only analyzer; active-document stale-claim scan; file-presence checks | Post-pull documentation/evidence synchronization audit; no keyboard access |

Repository/context commands also run: `pwd`, `rg --files -g AGENTS.md`, `rg --files`, `git status --short`, `sed` on existing Falchion notes, `mkdir -p logs`, `diff` on prior captures, and `sha256sum logs/*.txt`. Reading the newly created logs with `sed`, `wc`, and `tail` did not access the USB device.

Later offline-analysis setup also checked local tool availability and created raw
payload/ELF wrappers only under `/tmp`. One initial zsh loop passed an empty offset
to `xxd` and decoded the firmware header instead of the intended slices; it made
no changes and was immediately corrected with `name:offset` loop values.
