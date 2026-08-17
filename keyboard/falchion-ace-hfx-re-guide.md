# ROG Falchion Ace HFX — Reverse Engineering Guide

**Goal:** Replace Armoury Crate with a cross-platform config tool, and unlock the Fn keys that ASUS won't let you remap.

**Device:** ROG Falchion Ace HFX 65% — USB VID `0x0B05`, PID `0x1B7E`

**Host:** CachyOS (Arch-based)

---

## Guiding principle

Do the **non-destructive** work first. Every step in Phase 1–3 is read-only or reversible. You don't touch firmware until you've proven you need to, and you don't touch firmware without a backup and a recovery path.

**Never flash anything before completing Phase 2.**

---

## Phase 0 — Setup

### 0.1 Install tools

```bash
# USB inspection + HID access
sudo pacman -S usbutils hidapi libusb dfu-util

# Packet capture
sudo pacman -S wireshark-qt
sudo usermod -aG wireshark $USER

# Rust HID work (you already have rustup presumably)
# cargo add hidapi  -- later, in the project

# Python for quick prototyping
sudo pacman -S python python-pip
pip install --user hidapi pyusb
```

Log out/in for the `wireshark` group to take effect.

### 0.2 Enable usbmon

```bash
sudo modprobe usbmon
# make it persistent
echo usbmon | sudo tee /etc/modules-load.d/usbmon.conf
```

### 0.3 udev rule for non-root HID access

Create `/etc/udev/rules.d/99-asus-keyboard.rules`:

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="0b05", ATTRS{idProduct}=="1b7e", MODE="0666"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0b05", ATTRS{idProduct}=="1b7e", MODE="0666"
```

Then:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Replug the keyboard.

### 0.4 Set up a project repo

```bash
mkdir -p ~/projects/falchion-re/{captures,dumps,notes,tool}
cd ~/projects/falchion-re
git init
echo "captures/*.pcapng" >> .gitignore  # these get large
```

Keep a `notes/findings.md` as you go. This work is slow and you WILL forget what byte 7 meant three days later.

---

## Phase 1 — Identify the hardware (non-destructive)

### 1.1 Enumerate the USB device

```bash
lsusb -d 0b05:1b7e -v > notes/usb-descriptors.txt
```

Look for and record in your notes:
- Number of interfaces (there will be several — keyboard, mouse-ish, vendor-specific)
- Which interface is **vendor-defined** (usually `bInterfaceClass: 3 (HID)` with a vendor usage page like `0xFF00`) — this is almost certainly the config channel Armoury Crate uses
- Endpoint addresses and max packet sizes (tells you report sizes, likely 64 bytes)
- `bcdDevice` — the firmware version

### 1.2 List HID report descriptors

```bash
ls -l /sys/class/hidraw/
# for each hidrawN that maps to your device:
sudo cat /sys/class/hidraw/hidraw0/device/report_descriptor | xxd > notes/report-desc-0.txt
```

Confirm which hidraw node is yours:

```bash
for d in /sys/class/hidraw/hidraw*; do
  echo "== $d"
  cat $d/device/uevent | grep HID_NAME
done
```

### 1.3 Check for DFU / bootloader mode

```bash
sudo dfu-util -l
```

Also check whether ASUS exposes a DFU interface only after a magic command, or via a physical key combo (check the manual — some ROG boards use a hold-key-while-plugging sequence).

### 1.4 Identify the MCU

Two routes:

**Software route (try first):**
- If a DFU interface appears, `dfu-util -l` will often print the chip/alt-settings which hint at the family
- Check ASUS's firmware updater package (Phase 2.2) — updater binaries often name the target chip

**Physical route:**
- Open the case (Falchion Ace HFX: remove keycaps, unscrew plate, watch for the touch panel ribbon cable — be gentle with it)
- Photograph the main IC markings, and any secondary ICs (the HE sensing ADC/multiplexers)
- Record: MCU part number, flash size, any SWD test pads (look for `SWDIO` / `SWCLK` / `RST` / `GND` labels or a 4–5 pad cluster near the MCU)

**Record findings before continuing.** The MCU family determines everything downstream.

---

## Phase 2 — Backup and recovery prep (DO THIS BEFORE ANY WRITE)

### 2.1 Attempt a firmware dump

If a DFU interface exists:

```bash
# Read-only attempt. This does NOT write anything.
sudo dfu-util -a 0 -U dumps/falchion-stock-$(date +%F).bin
```

Three possible outcomes — record which one:

| Outcome | Meaning | Implication |
|---|---|---|
| Full dump succeeds | No read-out protection | You have a golden backup. Best case. |
| Reads all `0x00`/`0xFF` | RDP Level 1 active | Flash reads are blocked. No stock backup from the chip. |
| Errors / no DFU iface | No exposed bootloader | May need SWD access to dump at all. |

If you get a dump: **verify it's real** (`xxd dumps/*.bin | head -50` — you should see a plausible vector table, not all zeros), then copy it to at least two other locations. This file is your entire safety net.

### 2.2 Get the official firmware as a secondary backup

Even if RDP blocked you, ASUS's own updater may contain the firmware image:

1. Download the Falchion Ace HFX firmware updater from ASUS support
2. Extract it:
   ```bash
   # try these in order
   7z x updater.exe -o./extracted
   binwalk -e updater.exe
   ```
3. Look for `.bin` / `.hex` / large blobs in the output
4. `binwalk` the candidates to check for ARM firmware signatures

Store anything you find in `dumps/`.

### 2.3 Get an SWD programmer (order it now, before you need it)

- **ST-Link V2 clone** (~$5–8) or a **Raspberry Pi Pico** flashed as a debug probe (you may already have one)
- This is your Tier-2 recovery path: if you ever corrupt the bootloader, USB flashing dies but SWD still works
- Software: `sudo pacman -S openocd`

Do not start Phase 4 without this in hand.

---

## Phase 3 — Protocol reverse engineering (this is the main event)

**This phase alone probably solves your problem.** No firmware changes, zero brick risk.

### 3.1 Set up capture on the Armoury Crate side

You need Armoury Crate running to observe what it sends. Options:

**Option A — Windows VM with USB passthrough (preferred, keeps you on Linux):**
- QEMU/virt-manager or VirtualBox with the keyboard passed through
- Capture on the **host** with usbmon/Wireshark — you see the real wire traffic
- Note: passthrough of composite HID devices can be finicky; you may need to pass the whole device, and your host will lose the keyboard while the VM has it (use a second keyboard)

**Option B — Dual boot Windows, capture with USBPcap + Wireshark on Windows**
- More reliable capture, less convenient workflow
- Export captures as `.pcapng` and analyze them back on Linux

**Option C — Native Linux capture of your own test packets (for Phase 3.5 verification)**

### 3.2 Capture a baseline

```bash
# find the bus number
lsusb -d 0b05:1b7e
# capture that bus (replace N)
sudo wireshark -i usbmonN
```

Filter in Wireshark:
```
usb.idVendor == 0x0b05 && usb.idProduct == 0x1b7e
```
or once you know the bus/device address:
```
usb.device_address == X
```

Capture 30s of idle — this is your noise baseline (polling, keepalives).

### 3.3 Capture single-variable changes

This is the methodical part. For each change:

1. Start capture
2. In Armoury Crate, change **exactly one thing**
3. Hit apply
4. Stop capture, save as `captures/<description>.pcapng`
5. Log in `notes/findings.md` what you changed

Changes to capture, in this order:

**Key remapping (your primary goal):**
- Remap a normal key (e.g. `F1`) to `A`
- Same key to `B` (one byte should differ — this identifies the keycode field)
- Same key to `Z`
- A *different* key to `A` (identifies the key-index field)
- Attempt to remap one of the **locked Fn keys** — capture whether Armoury Crate sends anything at all, or blocks it client-side

That last one is diagnostic gold: if Armoury Crate sends *nothing* when you try, the lock is pure UI. If it sends a packet and the keyboard ignores/reverts it, the lock is in firmware.

**Other settings (capture these too, you'll want them in your tool):**
- Actuation point: set to min, then max, then a middle value
- Rapid trigger: on/off, sensitivity min/max
- Per-key actuation if supported
- Profile switching
- Any lighting (even if you don't care, it helps map the command byte space)

### 3.4 Decode the packets

Export each capture's HID output reports:

```bash
tshark -r captures/remap-f1-to-a.pcapng -Y "usbhid" -T fields -e usb.capdata > notes/remap-f1-a.hex
```

Then diff systematically:

```bash
diff <(xxd -r -p notes/remap-f1-a.hex | xxd) <(xxd -r -p notes/remap-f1-b.hex | xxd)
```

Typical structure you're looking for (64-byte reports are common):

```
[0]     Report ID
[1]     Command / opcode      <- differs between "remap" vs "set actuation"
[2]     Sub-command or index
[3..]   Payload               <- key index, keycode, values
[n-2:]  Checksum (maybe)
```

Build up a table in `notes/protocol.md` as you identify fields. Watch for:
- A **checksum/CRC** at the end (if your replayed packets get rejected but captured ones work, this is why — sum the bytes, try simple additive/XOR/CRC8 first)
- A **"commit"/"save to EEPROM"** command sent after config changes
- Sequence numbers or handshake/init packets sent at app startup

### 3.5 Replay and verify

Once you think you understand a packet, send it yourself. Quick Python prototype:

```python
import hid

VID, PID = 0x0B05, 0x1B7E

d = hid.Device(VID, PID)   # may need to select the right usage page/interface
report = bytes([0x00, 0x51, 0x28, 0x00, 0x04] + [0x00]*59)  # example only
d.write(report)
print(d.read(64, timeout=1000))
```

If `hid.Device(VID, PID)` grabs the wrong interface, enumerate and pick by usage page:

```python
for i in hid.enumerate(VID, PID):
    print(i['path'], hex(i['usage_page']), hex(i['usage']), i['interface_number'])
```

The vendor interface is typically usage page `0xFF00`+.

**Verify by replaying a known-good capture first** (something you already made via Armoury Crate). If that works, your transport is correct and you can start experimenting.

### 3.6 THE KEY TEST — are the Fn keys really locked?

Once you can send working remap packets:

1. Send a remap targeting a locked Fn key, using the same packet structure that works for normal keys
2. Reboot the keyboard (unplug/replug) and test the key
3. Read back the config if the protocol supports it

**Outcomes:**
- **Works** → Lock was UI-only. **You're done.** Skip Phase 4 entirely, go build your tool.
- **Device ACKs but key doesn't change** → Firmware silently ignores it. Firmware-level lock.
- **Device NAKs / returns error** → Firmware actively rejects it. Firmware-level lock.

Record which. This decides whether you continue to Phase 4.

---

## Phase 4 — Firmware modification (ONLY if Phase 3.6 says the lock is in firmware)

⚠️ **Prerequisites before starting:** verified firmware backup (2.1 or 2.2), SWD programmer in hand, SWD pads located.

If you don't have a backup, seriously weigh whether unlockable Fn keys are worth a permanently altered keyboard.

### 4.1 Load firmware into Ghidra

```bash
# Ghidra from AUR
paru -S ghidra
```

- Import the `.bin` with the correct architecture (ARM Cortex-M, little endian, thumb)
- Set the load base address correctly (usually `0x08000000` for STM32; check your MCU's memory map)
- Let auto-analysis run

### 4.2 Find the USB report handler

Strategy:
- The vector table is at the base address; the reset handler is the second word
- Look for the USB interrupt handler and follow to where OUT reports are processed
- Search for the opcode byte you identified in Phase 3.4 — it'll appear as an immediate in a comparison instruction
- That comparison is your entry point into the remap handler

### 4.3 Find the lock check

- Inside the remap handler, look for a bounds check or a lookup table filtering key indices
- A locked-key list will often appear as a small table of key indices, or a range comparison
- The check will be a `CMP` + conditional branch that skips the write

### 4.4 Patch

- Simplest patch: NOP out the conditional branch, or invert it
- Note the exact file offset and original bytes in `notes/patches.md`
- Recompute any firmware checksum if the bootloader validates one (check for a length/CRC field near the vector table — if the bootloader rejects your patched image, this is why)

### 4.5 Flash carefully

```bash
# via DFU if available
sudo dfu-util -a 0 -s 0x08000000:leave -D dumps/patched.bin

# or via SWD (safer, and works even if you break the bootloader)
openocd -f interface/stlink.cfg -f target/stm32XXx.cfg \
  -c "program dumps/patched.bin 0x08000000 verify reset exit"
```

**Test recovery before you need it:** after your first successful flash, immediately practice restoring the stock backup. Knowing your recovery path works is worth the ten minutes.

---

## Phase 5 — Build the cross-platform tool

Once the protocol is understood, this is straightforward engineering.

### Suggested stack

- **Rust + `hidapi` crate** for the core library — cross-platform (Linux/Mac/Windows) out of the box
- **CLI first** (`falchionctl set-key F1 A`, `falchionctl rapid-trigger on --sensitivity 0.3`) — fastest path to actually using it
- **GUI later** via Tauri if you want it, reusing the same Rust core
- Config file format: TOML, so layouts are version-controllable

### Structure

```
tool/
  falchion-proto/     # protocol encoding/decoding, no I/O — unit testable
  falchion-hid/       # transport layer over hidapi
  falchion-cli/       # binary
  falchion-gui/       # optional, later
```

Keeping the protocol layer I/O-free means you can unit test packet construction against your captured `.pcapng` bytes without hardware attached.

### Ship it

Publish the repo and the protocol documentation. Every other Falchion Ace HFX owner who dislikes Armoury Crate — and there are certainly some — benefits, and you'll get bug reports from people with hardware variants you don't have.

---

## Quick reference — decision tree

```
Identify MCU + find vendor HID interface
  │
  ├─ Attempt firmware dump  ──► got backup?  ──► store in 3 places
  │                              no backup?  ──► try ASUS updater extraction
  │                                              still nothing? ──► Phase 4 is one-way. Decide carefully.
  │
  ├─ Capture Armoury Crate traffic
  ├─ Decode packet structure
  ├─ Replay verified packets
  │
  └─ Test locked Fn key remap
       ├─ WORKS       ──► Skip Phase 4. Build tool. Done.
       ├─ IGNORED     ──► Firmware lock. Phase 4 (needs backup + SWD).
       └─ REJECTED    ──► Firmware lock. Phase 4 (needs backup + SWD).
```

---

## Notes template

Keep `notes/findings.md` structured like this:

```markdown
## Hardware
- MCU:
- Flash size:
- SWD pads located: yes/no, where:
- HE sensing IC(s):

## USB
- Vendor HID interface: hidrawN, usage page 0x____
- Report size: __ bytes
- DFU available: yes/no

## Protocol
| Opcode | Meaning | Payload layout | Verified? |
|--------|---------|----------------|-----------|
| 0x__   |         |                |           |

## Open questions
-
```

---

## Realistic expectations

- **Phase 1–3 is a weekend or two** of methodical work if the protocol is simple, longer if there's a checksum or handshake to figure out.
- **Phase 4 is a different scale entirely** — ARM firmware RE is genuinely hard, and could be weeks. Given your low-level background it's tractable, but don't start it casually.
- **Good odds you never need Phase 4.** Manufacturer key-remap restrictions are frequently UI-side, because it's cheaper to enforce in an app than in firmware.
