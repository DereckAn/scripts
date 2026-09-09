#!/usr/bin/env python3
"""Recover the settings/profile format, using the decoded Armoury Crate
profile as a Rosetta stone.

READ-ONLY AND STATIC. This module reads code and preserved bytes. It never
speaks to the device and it constructs no command. The vendor persistence
command's opcode and subcommand are deliberately not spelled out anywhere in
this module or its output; log 111 and `tool/map_nonvolatile_writes.py` already
record them as values the firmware compares against, and repeating them beside
a recovered payload format is exactly the combination this project avoids.

WHAT LOG 111 LEFT OPEN AND THIS CLOSES. Phase 5E traced the second half of the
chain (RAM state -> command byte -> erase) and recorded the format's magic,
version, length, checksum, defaults and migration as NOT RECOVERED, because the
commit branch it could see only passes ADDRESSES to erase primitives. The
missing half is a different state machine: FUN_18000d56's save states call a
WRITE request primitive, not an erase one, and they compute a checksum first.

  FUN_1800e368(addr, buf, len)   request opcode 3   READ
  FUN_1800e344(addr, buf, len)   request opcode 2   PROGRAM
  FUN_1800e2fc(addr, buf, len)   request opcode 0x22 WRITE
  FUN_1800e2e0(addr)             request opcode 0x20
  FUN_1800e2a8/2c4(addr)         request opcodes 0xd8 / 0x52   (log 111)

All six fill the same one-deep request struct at 0x18025ef4, so log 111's
struct map extends by two fields: +0x04 is the buffer and +0x10 the length.

THE MEDIUM IS STILL NOT IDENTIFIED, and nothing here names it. The opcode
values keep the "matches the JEDEC ..." wording log 111 chose; recovering the
data format does not identify the part the DMA path talks to.

No device access. Examples:
    python3 tool/map_profile_format.py
    python3 tool/map_profile_format.py --json
    python3 tool/map_profile_format.py --write
    python3 tool/map_profile_format.py --check
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_second_context as ms

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"

APP_BIN = "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin"
REGION_BIN = ("installed_decompressed_region1_flash3f380_dst1801e380"
              "_len00b04_501f818f.bin")
APP_BASE = 0x18000000
REGION_BASE = 0x1801E380

# --- the runtime blocks, all read off literal pools in the listings ----------
DEVICE_HEADER = 0x1801E6D0        # 0x10 bytes, item 0 of the small store
GLOBAL_BLOCK = 0x18024F0C         # 0x20 bytes, item 1 of the small store
KEYMAP_BANK = 0x180202D8          # layer * 0xd84
PROFILE_BLOCK = 0x18021DE0        # == KEYMAP_BANK + 2 * LAYER_STRIDE
MACRO_BLOCK = 0x180225FC          # == PROFILE_BLOCK + PROFILE_LEN
BLOCK_D = 0x1801FEF8
REQUEST_STRUCT = 0x18025EF4       # log 111's one-deep request slot

LAYER_STRIDE = 0xD84
PROFILE_LEN = 0x81C
MACRO_LEN = 0x664
MACRO_RECORD = 0x198
MACRO_RECORDS = 4
MACRO_CHECKSUM_AT = 0x19A          # relative to the record, so it lands in
                                   # the next record's header bytes 2..3
BLOCK_D_LEN = 0x3E0
PROFILES = 6
LAYERS = 2

# --- the stored address space, every base a literal in the listings ---------
PROFILE_STORE_BASE = 0x2000
PROFILE_STORE_STRIDE = 0x1000
SMALL_STORE_BANKS = (0x1C000, 0x1D000, 0x1E000, 0x1F000)
SMALL_BANK_LEN = 0x1000
MACRO_STORE_BASE = 0x20000
MACRO_PROFILE_STRIDE = 0x80000
MACRO_SLOT_STRIDE = 0x1000
KEYMAP_STORE_BASE = 0x320000
KEYMAP_PROFILE_STRIDE = 0x4000
KEYMAP_LAYER_STRIDE = 0x1000
BLOCK_D_STORE_BASE = 0x340000
BLOCK_D_STRIDE = 0x1000
BOOTLOADER_REGION = (0x10000, 0x7C000)     # log 81's application region

# --- the profile block's internal boundaries --------------------------------
CKA_OFFSET = 0x000
FLAGS_OFFSET = 0x002
LIGHT_OFFSET = 0x004
KEYTABLE_OFFSET = 0x0D4
KEYTABLE_STRIDE = 0x1EE                    # bytes per layer, 247 uint16
KEYTABLE_ENTRIES = 0xF7                    # the loop bound, 247
CKA_COVER = 0x4B0                          # sum over blob+2, this many bytes
PAIR_OFFSET = 0x4B0
LEVER_OFFSET = 0x4B2
LEVER_ROWS = 5
LEVER_ROW = 14
VERSION_OFFSET = 0x4F8
CKB_OFFSET = 0x4FA
REGION_B_OFFSET = 0x4FC
CKB_COVER = 0x2C0
SENTINEL = 0xA0D3                          # written at key-table entry 0xe4

# The ten lighting slots, in the order their default-setter's cases write them.
# Each pair is (slot id, size); the offsets are computed, never transcribed.
LIGHT_SLOTS = ((0, 15), (1, 15), (2, 15), (4, 38), (5, 38),
               (3, 15), (6, 15), (7, 27), (8, 15), (9, 15))

# --- the ROM default table, one contiguous run ------------------------------
ROM_VERSION_STAMP = 0x1801BFBC             # uint16, copied to blob+0x4f8
ROM_LIGHT_SLOT = 0x1801BFBE                # 6 bytes, one per profile
ROM_FUNCTION_INDEX = 0x1801BFC4            # 6 bytes, one per profile
ROM_LEVER_TABLE = 0x1801BFCA               # 0x46 bytes, copied to blob+0x4b2
ROM_COLOUR_TABLE = 0x1801C010              # 6 * 3 bytes, one RGB per profile

# --- the small wear-levelled store ------------------------------------------
GROUP_TABLE = 0x1801E980                   # 2 descriptors of 0x10 bytes
GROUP_COUNT = 2
ITEM_LEN = 0x14

# --- request primitives, each identified by the opcode byte it stores -------
PRIMITIVES = {
    0x1800E344: (0x02, "PROGRAM"),
    0x1800E368: (0x03, "READ"),
    0x1800E2FC: (0x22, "WRITE"),
    0x1800E2E0: (0x20, None),
    0x1800E2A8: (0xD8, None),
    0x1800E2C4: (0x52, None),
}
# Each primitive stores its opcode with a `movs rD,#imm8` immediately followed
# by `strb rD,[rB,#0]`. The pair is searched for rather than read at a fixed
# offset, because the six do not share one: three use r4 at +12 and three use
# r2 at +10.
PRIMITIVE_SCAN = 0x18

# The per-profile packed word in the global block, as its readers mask it.
GLOBAL_FIELDS = (
    ("function_index", 6, 3, 0, 4, 0,
     "cycled 0..4 by FUN_18007030, which then persists the whole block"),
    ("actuation", 9, 7, 1, 40, 10,
     "FUN_18006d3c raises while <0x28 and lowers while >1; the boot repair "
     "writes +0x1400, i.e. 10"),
    ("rapid_trigger_release", 17, 3, 1, 6, 2,
     "FUN_1800f7fe resets the field to 2 when (v)-1 > 5"),
    ("rapid_trigger_press", 20, 3, 1, 6, 2,
     "FUN_1800f7fe resets the field to 2 when (v)-1 > 5"),
)
GLOBAL_RESET_WORD = 0x241400 + 0x10        # the factory-reset value, |0x10
GLOBAL_MARKER_OFFSET = 0x18
GLOBAL_MARKER = 0xA9B8

# The per-key record inside a 0xd84 bank.
RECORD_LEN = 0x20
RECORD_KEYS = 75                           # 5 groups * 15, log 110
RECORD_FALLBACK_INDEX = 0x4B


class ProfileFormatError(RuntimeError):
    """The evidence does not support continuing."""


# --- evidence ---------------------------------------------------------------

def _load(name):
    path = IMPORTS / name
    if not path.exists():
        raise ProfileFormatError(f"missing import slice {name}")
    data = path.read_bytes()
    tag = name.rsplit("_", 1)[1].split(".")[0]
    got = hashlib.sha256(data).hexdigest()[:len(tag)]
    if got != tag:
        raise ProfileFormatError(
            f"{name} hashes to {got}, but its name claims {tag}")
    return data


def images():
    ms.sources()                                   # hash-gates both dumps
    return {"app": (_load(APP_BIN), APP_BASE),
            "region": (_load(REGION_BIN), REGION_BASE)}


def _b(img, addr, n=1):
    buf, base = img
    off = addr - base
    if off < 0 or off + n > len(buf):
        raise ProfileFormatError(f"{addr:#x} is outside the slice")
    return buf[off:off + n]


def _u8(img, addr):
    return _b(img, addr)[0]


def _u16(img, addr):
    return struct.unpack("<H", _b(img, addr, 2))[0]


def _u32(img, addr):
    return struct.unpack("<I", _b(img, addr, 4))[0]


# --- the checksum, implemented rather than described ------------------------

def sum16(data):
    """FUN_180088fe: a 16-bit additive sum of bytes. Not a CRC.

    The listing is twelve halfwords: `ldrb r4,[r3,r2]` / `add r0,r4` /
    `uxth r0,r0` in a loop bounded by r1. `uxth` is why it wraps at 16 bits.
    """
    return sum(data) & 0xFFFF


def checksum_a_stamp(raw, profile):
    """The stored value is the sum masked with the slot it belongs to.

    `*puVar17 = uVar9 & (profile | 0xfff0)` — so the low nibble of the sum
    survives only where the profile index has a bit set. A block written for
    one slot therefore fails validation in another unless the nibbles agree.
    """
    return raw & (profile | 0xFFF0)


# --- computed layouts -------------------------------------------------------

def light_slots():
    """Offset and size of each lighting slot, accumulated in write order."""
    out, cursor = [], LIGHT_OFFSET
    for slot, size in LIGHT_SLOTS:
        out.append({"slot": slot, "offset": cursor, "size": size})
        cursor += size
    return out, cursor


def profile_layout():
    slots, light_end = light_slots()
    return [
        {"offset": CKA_OFFSET, "size": 2, "name": "checksum_a",
         "detail": "sum16(blob+2, 0x4b0) masked with (profile | 0xfff0)",
         "confidence": "observed"},
        {"offset": FLAGS_OFFSET, "size": 2, "name": "flags",
         "detail": "bit 15 marks region B valid; the save path also sets "
                   "1 << lighting_slot for slots below 10",
         "confidence": "observed"},
        {"offset": LIGHT_OFFSET, "size": light_end - LIGHT_OFFSET,
         "name": "lighting_slots",
         "detail": f"{len(slots)} variable-length records; sizes "
                   f"{sorted({s['size'] for s in slots})}",
         "confidence": "observed"},
        {"offset": KEYTABLE_OFFSET, "size": KEYTABLE_STRIDE,
         "name": "key_table_layer0",
         "detail": f"{KEYTABLE_ENTRIES} uint16 plus padding; the initialiser "
                   f"writes the identity map and {SENTINEL:#x} at entry 0xe4",
         "confidence": "observed"},
        {"offset": KEYTABLE_OFFSET + KEYTABLE_STRIDE, "size": KEYTABLE_STRIDE,
         "name": "key_table_layer1",
         "detail": "the same shape; the initialiser leaves it zero",
         "confidence": "observed"},
        {"offset": PAIR_OFFSET, "size": 2, "name": "pair_4b0",
         "detail": "FUN_18000420 writes 0x14 and a bitfield here; role not "
                   "recovered",
         "confidence": "unresolved"},
        {"offset": LEVER_OFFSET, "size": LEVER_ROWS * LEVER_ROW,
         "name": "selectable_rows",
         "detail": f"{LEVER_ROWS} rows of {LEVER_ROW} bytes copied verbatim "
                   f"from ROM {ROM_LEVER_TABLE:#x}; FUN_18007030 treats a "
                   "non-zero first byte as selectable",
         "confidence": "observed"},
        {"offset": VERSION_OFFSET, "size": 2, "name": "version_stamp",
         "detail": f"copied from ROM {ROM_VERSION_STAMP:#x}; not covered by "
                   "either checksum",
         "confidence": "observed"},
        {"offset": CKB_OFFSET, "size": 2, "name": "checksum_b",
         "detail": "sum16(blob+0x4fc, 0x2c0), recomputed only when flags "
                   "bit 15 is set",
         "confidence": "observed"},
        {"offset": REGION_B_OFFSET, "size": CKB_COVER, "name": "region_b",
         "detail": "covered by checksum_b; contents not decoded",
         "confidence": "unresolved"},
        {"offset": REGION_B_OFFSET + CKB_COVER,
         "size": PROFILE_LEN - REGION_B_OFFSET - CKB_COVER, "name": "tail",
         "detail": "covered by NEITHER checksum; contents not decoded",
         "confidence": "unresolved"},
    ]


def stored_map():
    """Every stored region, with the literal that produces its address."""
    return [
        {"name": "profile_settings",
         "lo": PROFILE_STORE_BASE,
         "hi": PROFILE_STORE_BASE + PROFILES * PROFILE_STORE_STRIDE,
         "formula": "0x2000 + profile * 0x1000", "record_len": PROFILE_LEN,
         "ram": PROFILE_BLOCK,
         "evidence": "FUN_1800e368(profile*0x1000+0x2000, 0x18021de0, 0x81c) "
                     "on the load side and FUN_1800e2fc with the same address "
                     "on the save side"},
        {"name": "small_store",
         "lo": SMALL_STORE_BANKS[0],
         "hi": SMALL_STORE_BANKS[-1] + SMALL_BANK_LEN,
         "formula": "four fixed 4 KiB banks, two A/B pairs",
         "record_len": None, "ram": None,
         "evidence": f"the group descriptors at {GROUP_TABLE:#x} in the "
                     "region image"},
        {"name": "macros",
         "lo": MACRO_STORE_BASE,
         "hi": MACRO_STORE_BASE + PROFILES * MACRO_PROFILE_STRIDE,
         "formula": "0x20000 + profile * 0x80000 + slot * 0x1000",
         "record_len": MACRO_LEN, "ram": MACRO_BLOCK,
         "evidence": "FUN_18007e0c and FUN_18007da4, both with movw r2,#0x664"},
        {"name": "keymap_banks",
         "lo": KEYMAP_STORE_BASE,
         "hi": KEYMAP_STORE_BASE + PROFILES * KEYMAP_PROFILE_STRIDE,
         "formula": "0x320000 + profile * 0x4000 + layer * 0x1000",
         "record_len": LAYER_STRIDE, "ram": KEYMAP_BANK,
         "evidence": "FUN_1800e368(..., bank + layer*0xd84, 0xd84) and "
                     "FUN_1800e2fc with the same address"},
        {"name": "block_d",
         "lo": BLOCK_D_STORE_BASE,
         "hi": BLOCK_D_STORE_BASE + PROFILES * BLOCK_D_STRIDE,
         "formula": "0x340000 + profile * 0x1000", "record_len": BLOCK_D_LEN,
         "ram": BLOCK_D,
         "evidence": "FUN_1800e368(profile*0x1000+0x340000, 0x1801fef8, "
                     "0x3e0) and FUN_1800e2fc with the same address"},
    ]


def small_store():
    """The wear-levelled store's descriptors, read from the region image."""
    img = images()["region"]
    groups = []
    for g in range(GROUP_COUNT):
        d = GROUP_TABLE + g * 0x10
        items_ptr = _u32(img, d + 0xC)
        items = []
        for i in range(_u8(img, d + 9)):
            p = _u32(img, items_ptr + i * 4)
            items.append({
                "descriptor": p,
                "group": _u8(img, p + 0),
                "counter": _u16(img, p + 2),
                "record_len": _u16(img, p + 4),
                "bank_offset": _u16(img, p + 6),
                "region_len": _u32(img, p + 8),
                "ram_buffer": _u32(img, p + 0xC),
                "capacity": _u16(img, p + 0x10),
                "dirty": _u8(img, p + 0x12),
            })
        groups.append({
            "index": g, "bank_a": _u32(img, d), "bank_b": _u32(img, d + 4),
            "selector": _u8(img, d + 8), "item_count": _u8(img, d + 9),
            "items_ptr": items_ptr, "items": items})
    return groups


def rom_defaults():
    img = images()["app"]
    colours = [tuple(_b(img, ROM_COLOUR_TABLE + p * 3, 3))
               for p in range(PROFILES)]
    rows = [list(struct.unpack("<7H",
                               _b(img, ROM_LEVER_TABLE + r * LEVER_ROW,
                                  LEVER_ROW)))
            for r in range(LEVER_ROWS)]
    return {
        "version_stamp": _u16(img, ROM_VERSION_STAMP),
        "light_slot_per_profile": list(_b(img, ROM_LIGHT_SLOT, PROFILES)),
        "function_index_per_profile": list(_b(img, ROM_FUNCTION_INDEX,
                                              PROFILES)),
        "colour_per_profile": [list(c) for c in colours],
        "selectable_rows": rows,
    }


def opcode_store(body):
    """Find `movs rD,#imm8` / `strb rD,[rB,#0]` and return (offset, rD, imm8).

    Searching for the idiom is safer than reading a fixed offset: a wrong
    offset would silently report a neighbouring immediate, whereas a wrong
    idiom finds nothing at all, which the anti-vacuity check below catches.
    """
    for off in range(0, len(body) - 3, 2):
        h0, h1 = struct.unpack_from("<HH", body, off)
        if h0 & 0xF800 != 0x2000:
            continue
        rd, imm = (h0 >> 8) & 7, h0 & 0xFF
        if h1 & 0xF800 != 0x7000 or h1 & 7 != rd or (h1 >> 6) & 0x1F:
            continue
        if imm:
            return off, rd, imm
    return None


def primitives():
    """Each request primitive's opcode, decoded from its own instruction."""
    img = images()["app"]
    out = []
    for addr, (expected, role) in sorted(PRIMITIVES.items()):
        found = opcode_store(_b(img, addr, PRIMITIVE_SCAN))
        off, rd, imm = found if found else (None, None, None)
        out.append({"function": addr, "opcode": imm,
                    "opcode_matches_expected": imm == expected,
                    "role": role, "store_offset": off, "register": rd})
    return out


def global_word_fields():
    out = []
    for name, shift, width, lo, hi, default, note in GLOBAL_FIELDS:
        mask = ((1 << width) - 1) << shift
        out.append({"name": name, "shift": shift, "width": width,
                    "mask": mask, "min": lo, "max": hi, "default": default,
                    "reset_value": (GLOBAL_RESET_WORD & mask) >> shift,
                    "note": note})
    return out


# --- the Armoury Crate side -------------------------------------------------

def ac_profile():
    path = NOTES / "ac-profile3-decoded.json"
    if not path.exists():
        raise ProfileFormatError("missing notes/ac-profile3-decoded.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


AC_PROFILE_INDEX = 3        # the snapshot is fp_3_config_<model>.xml


@dataclass(frozen=True)
class Match:
    ac_field: str
    ac_value: str
    blob: str
    offset: str
    evidence: str
    confidence: str          # exact | structural | unmatched
    note: str = ""


def matches():
    """Field-by-field, computed against the decode rather than asserted."""
    ac = ac_profile()
    kb = ac["lighting"]["keyboard"]
    rom = rom_defaults()
    slots = {s["slot"]: s for s in light_slots()[0]}
    colour = rom["colour_per_profile"][AC_PROFILE_INDEX]
    single = kb["pattern"]["singleColor"][0]
    single_rgb = [int(single["r"]), int(single["g"]), int(single["b"])]
    default_slot = rom["light_slot_per_profile"][AC_PROFILE_INDEX]
    trig = ac["button"]["analogTrigger"]
    keyfns = ac["button"]["keyboardButton"]

    out = [
        Match("lighting.keyboard.effectID", kb["effectID"],
              "profile block", f"slot index -> +{slots[default_slot]['offset']:#05x}",
              f"the ROM per-profile default lighting slot for profile "
              f"{AC_PROFILE_INDEX} is {default_slot}, read from "
              f"{ROM_LIGHT_SLOT:#x}+{AC_PROFILE_INDEX}",
              "exact" if str(default_slot) == kb["effectID"] else "unmatched",
              "the decode's effectID is the firmware's slot index, not a "
              "field inside the record"),
        Match("lighting.keyboard.brightness", kb["brightness"],
              "lighting slot record", "+0x01",
              "every one of the ten default-setter cases writes 100 to the "
              "record's second byte",
              "exact" if kb["brightness"] == "100" else "unmatched",
              "range is not proven from the setter; only the default is"),
        Match("lighting.keyboard.pattern.singleColor",
              f"{single_rgb}", "lighting slot record", "+0x05..+0x07",
              f"the ROM per-profile colour for profile {AC_PROFILE_INDEX} is "
              f"{colour}, read from {ROM_COLOUR_TABLE:#x}+{AC_PROFILE_INDEX}*3;"
              " the 0xfa/1/0 handler writes request bytes 4,5,6 to the same "
              "three record bytes",
              "exact" if colour == single_rgb else "unmatched"),
        Match("lighting.keyboard.direction", kb["direction"],
              "lighting slot record", "+0x03",
              "the default-setter writes 0xff, the byte-width form of -1",
              "structural",
              "0xff is also written to +0x04, so which of the two is "
              "direction is not established"),
        Match("lighting.keyboard.random", kb["random"],
              "lighting slot record", "+0x04",
              "the default-setter writes 0xff, the byte-width form of -1",
              "structural", "same ambiguity as direction"),
        Match("lighting.keyboard.speed", kb["speed"],
              "lighting slot record", "+0x02",
              "the default-setter writes 0 for slots 0-2 and (profile == 0) "
              "for slots 3,6,8,9; the decode holds 1 for profile 3, which "
              "neither default produces",
              "unmatched"),
        Match("lighting.customPattern",
              f"{len(ac['lighting']['customPattern'])} entries",
              "lighting slot record", "slot 7, +0x05..+0x16",
              "slot 7's default-setter writes six RGB triples; the decode has "
              "seven entries",
              "unmatched", "six is not seven, so no correspondence is claimed"),
        Match("performance.pollingRate", ac["performance"]["pollingRate"],
              "-", "-",
              "no field in any block recovered here carries it, and log 124 "
              "searched from the other end and found no consumer either: no "
              "index-to-Hz table in any of the four images, a prescaler "
              "ladder built entirely from immediates, no rate in the mailbox "
              "and a static descriptor bInterval",
              "unmatched",
              "the two negatives are independent — this one is about the "
              "stored blocks, log 124's is about the consumers"),
        Match("button.analogTrigger.actuation", str(trig["actuation"]),
              "global block word", "bits 9..15",
              "the boot repair writes +0x1400, i.e. 10; FUN_18006d3c bounds "
              "the field to 1..40",
              "exact" if trig["actuation"] == 10 else "unmatched"),
        Match("button.analogTrigger.rapidTriggerPress",
              str(trig["rapidTriggerPress"]),
              "global block word / per-key record",
              "bits 20..22 / record +0x06",
              "FUN_1800f7fe resets both to 2 when the value minus one exceeds "
              "5, so the default is 2 and the range 1..6",
              "exact" if trig["rapidTriggerPress"] == 2 else "unmatched"),
        Match("button.analogTrigger.rapidTriggerRelease",
              str(trig["rapidTriggerRelease"]),
              "global block word / per-key record",
              "bits 17..19 / record +0x07",
              "the same reset, on the neighbouring field",
              "exact" if trig["rapidTriggerRelease"] == 2 else "unmatched"),
        Match("lever.currentFunctionId", ac["lever"]["currentFunctionId"],
              "global block word", "bits 6..8",
              f"the ROM per-profile default is "
              f"{rom['function_index_per_profile'][AC_PROFILE_INDEX]}; "
              "FUN_18007030 cycles the field 0..4",
              "structural"
              if str(rom["function_index_per_profile"][AC_PROFILE_INDEX])
              == ac["lever"]["currentFunctionId"] else "unmatched",
              "the values agree, but both are zero, which is weak evidence; "
              "and the same field could equally be a lighting-effect index. "
              "Both readings are recorded and neither is chosen"),
        Match("lever.functionStatusList",
              f"{len(ac['lever']['functionStatusList'])} entries",
              "profile block", f"+{LEVER_OFFSET:#05x}",
              f"{LEVER_ROWS} rows of {LEVER_ROW} bytes, each gated on a "
              "non-zero first byte; the counts and the 0..4 index agree",
              "structural",
              "row contents are not decoded, so the correspondence is on "
              "count and index range only"),
        Match("button.keyboardButton",
              f"{len(keyfns)} entries = 68 keys x 2 layers",
              "profile block key tables / keymap banks",
              f"+{KEYTABLE_OFFSET:#05x} and +{KEYTABLE_OFFSET+KEYTABLE_STRIDE:#05x}",
              f"the firmware keeps {LAYERS} layers, {KEYTABLE_ENTRIES} uint16 "
              f"per layer, and {RECORD_KEYS} per-key records per bank; none "
              "of 68, 136 or 189 equals any of those",
              "structural",
              "the layer count matches and the entry counts do not, so no "
              "per-key mapping is claimed"),
        Match("button.keyboardButton[*].actuation", "10",
              "per-key record", "+0x08 bits 0..6",
              "bit 15 selects the per-key value over the global one; the "
              "field is bounded to 1..40 by the same comparison",
              "exact"),
    ]
    return out


# --- the two chains ---------------------------------------------------------

LOAD_CHAIN = (
    ("boot", "CandidateB_Main calls FUN_1800e4ea, which mounts the "
             "wear-levelled store: for each of two groups it reads the first "
             "four bytes of both banks, picks the one that is neither "
             "0xffffffff nor 0, and scans that bank backwards for the newest "
             "record of each item.", "observed"),
    ("header", "FUN_18000d56's init state reads item 0 back and compares its "
               "first word against the firmware's own version word at "
               "0x1801e6d0. EQUAL -> adopt the stored header, including the "
               "current profile index at +6. DIFFERENT -> keep only what "
               "still agrees and re-stage both items, which is the migration "
               "step.", "observed"),
    ("global", "item 1 restores the 32-byte global block. The actuation field "
               "is then range-checked and repaired to 10 in place.",
     "observed"),
    ("profile", "a two-byte read of 0x2000 + profile*0x1000 tests for 0xffff; "
                "if it is erased the defaults path runs, otherwise the whole "
                "0x81c block is read and checksum A is recomputed and "
                "compared against the stored value masked with the profile "
                "index.", "observed"),
    ("keymaps", "for layer 0 then 1: a two-byte read tests for 0xffff, then "
                "0xd84 bytes are read and sum16(bank+2, 0xd82) is compared "
                "against the bank's first halfword.", "observed"),
    ("block_d", "the same shape at 0x340000 + profile*0x1000, 0x3e0 bytes, "
                "sum16(buf+2, 0x3de).", "observed"),
    ("failure", "every mismatch takes the same route as an erased block: the "
                "defaults are rebuilt in RAM (FUN_1800072c for the key "
                "tables, FUN_18000466/FUN_18000584 for the per-key records, "
                "FUN_180005c6 for block D, FUN_1800075a for the lighting "
                "slot) and a diagnostic string is logged. There is no factory "
                "image to fall back to and no second copy is consulted.",
     "observed"),
)

SAVE_CHAIN = (
    ("stage", "the device header and the global block are handed to "
              "FUN_1800e7ee, which copies them into the wear-levelled store's "
              "staging buffers and marks them dirty.", "observed"),
    ("profile", "checksum A is recomputed over blob+2 for 0x4b0 bytes and "
                "stored masked with (profile | 0xfff0); checksum B is "
                "recomputed over blob+0x4fc for 0x2c0 bytes only when flags "
                "bit 15 is set; then the WHOLE 0x81c block is written "
                "verbatim from 0x18021de0.", "observed"),
    ("macros", "FUN_18007da4 recomputes sum16(record+8, record[7]) for each "
               "of the four 0x198 records and stores it at record+0x19a — "
               "two bytes into the next record's header, and in the block's "
               "four-byte tail for the last — then writes all 0x664 bytes.",
     "observed"),
    ("keymaps", "for layer 0 then 1: sum16(bank + layer*0xd84 + 2, 0xd82) is "
                "stored in the bank's first halfword and the whole 0xd84 "
                "bytes are written.", "observed"),
    ("block_d", "sum16(buf+2, 0x3de) into the first halfword, then 0x3e0 "
                "bytes.", "observed"),
    ("retry", "each stage retries up to three times before giving up; the "
              "vendor response is sent only after the last stage completes, "
              "which is why the historical capture recorded the reply "
              "arriving about 220 ms late.", "observed"),
)


def unresolved():
    return [
        {"key": "storage_medium",
         "detail": "unchanged from log 111. The format is recovered; the part "
                   "the DMA path talks to is still not identified and is not "
                   "named here."},
        {"key": "region_b",
         "detail": f"{CKB_COVER:#x} bytes at +{REGION_B_OFFSET:#x} are "
                   "checksummed and never decoded."},
        {"key": "tail",
         "detail": f"{PROFILE_LEN - REGION_B_OFFSET - CKB_COVER:#x} bytes at "
                   f"+{REGION_B_OFFSET + CKB_COVER:#x} are covered by neither "
                   "checksum and never decoded."},
        {"key": "block_d_contents",
         "detail": "block D is proven persisted per profile and its default "
                   "setter is known; what it holds is not recovered."},
        {"key": "polling_rate",
         "detail": "no recovered field carries it, and log 124 found no "
                   "consumer for one anywhere in the preserved images."},
        {"key": "numeric_overlap",
         "detail": "the stored map's low regions numerically overlap the "
                   "bootloader's application region 0x10000..0x7c000. Log "
                   "111's 'disjoint address ranges' held for the three erase "
                   "targets it traced and does NOT generalise. Whether the "
                   "two are the same address space cannot be settled while "
                   "the medium is unidentified."},
    ]


def persistence():
    """What is proven persisted, and what is proven RAM-only."""
    return [
        {"section": "lighting", "verdict": "persisted",
         "detail": "the lighting slots live at +0x04..+0xd3 of the profile "
                   "block, inside checksum A's coverage, and the whole block "
                   "is written to 0x2000 + profile*0x1000 by the save path."},
        {"section": "key mappings", "verdict": "persisted",
         "detail": "two forms: the resolved per-layer uint16 tables inside "
                   "the profile block, and the 0x20-byte per-key records in "
                   "the two 0xd84 banks written to 0x320000 + profile*0x4000 "
                   "+ layer*0x1000."},
        {"section": "performance (actuation, rapid trigger)",
         "verdict": "persisted",
         "detail": "the global 32-byte block is staged into the wear-levelled "
                   "store on every save and restored at boot; the per-key "
                   "overrides ride in the keymap banks."},
        {"section": "current profile index", "verdict": "persisted",
         "detail": "byte +6 of the 16-byte device header, item 0 of the "
                   "wear-levelled store."},
        {"section": "macros", "verdict": "persisted",
         "detail": "four 0x198 records written to 0x20000 + profile*0x80000 "
                   "+ slot*0x1000."},
        {"section": "block D", "verdict": "persisted",
         "detail": "0x3e0 bytes per profile; contents not decoded."},
        {"section": "per-key Hall calibration", "verdict": "RAM-only",
         "detail": "log 121: rebuilt from the same defaults every boot, and "
                   "no storage path touches the calibration block."},
    ]


HOST_INDEPENDENCE = (
    "Lighting configuration persists across hosts because the whole 0x81c "
    "profile block, lighting slots included, is written to the external "
    "settings store by the vendor persistence path and read back at boot "
    "before any host has enumerated the device. The sentence is CORRECT in "
    "substance and imprecise in two places. First, the write is not part of "
    "the command handler: the handler only sets a command byte, and a state "
    "machine in another context performs the checksum, the write request and "
    "the retries. Second, 'the profile region' is five regions, not one, and "
    "lighting rides in the profile-settings region at 0x2000 + "
    "profile*0x1000, not in the 0x320000 keymap region. The reason the "
    "SELECTED profile also survives is separate: the current profile index is "
    "byte +6 of a 16-byte header kept in a wear-levelled A/B store at "
    "0x1c000..0x20000."
)


def verify():
    out = []

    def check(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    check(True, "both preserved dump hashes match the allowlist")

    slots, light_end = light_slots()
    check(light_end == KEYTABLE_OFFSET,
          "the ten lighting slots exactly fill the gap before the key tables",
          f"0x04 + {light_end - LIGHT_OFFSET:#x} == {KEYTABLE_OFFSET:#x}")
    check(KEYTABLE_OFFSET + LAYERS * KEYTABLE_STRIDE == PAIR_OFFSET,
          "two key-table layers end where checksum A's coverage ends",
          f"{KEYTABLE_OFFSET:#x} + 2*{KEYTABLE_STRIDE:#x} == {PAIR_OFFSET:#x}")
    check(FLAGS_OFFSET + CKA_COVER == LEVER_OFFSET,
          "checksum A covers exactly flags, lighting and the key tables",
          f"+2 .. +{FLAGS_OFFSET + CKA_COVER:#x}")
    check(LEVER_OFFSET + LEVER_ROWS * LEVER_ROW == VERSION_OFFSET,
          "the selectable rows end where the version stamp begins")
    check(VERSION_OFFSET + 2 == CKB_OFFSET
          and CKB_OFFSET + 2 == REGION_B_OFFSET,
          "the version stamp and checksum B sit between the two covered runs")
    check(REGION_B_OFFSET + CKB_COVER < PROFILE_LEN,
          "checksum B's run ends inside the block, leaving an uncovered tail",
          f"{PROFILE_LEN - REGION_B_OFFSET - CKB_COVER:#x} bytes uncovered")
    check(KEYTABLE_ENTRIES * 2 == KEYTABLE_STRIDE,
          "the key table's entry count and byte stride agree",
          f"{KEYTABLE_ENTRIES} uint16 == {KEYTABLE_STRIDE:#x} bytes")

    check(KEYMAP_BANK + LAYERS * LAYER_STRIDE == PROFILE_BLOCK,
          "the profile block begins exactly after the two keymap banks",
          f"{KEYMAP_BANK:#x} + 2*{LAYER_STRIDE:#x} == {PROFILE_BLOCK:#x}")
    check(PROFILE_BLOCK + PROFILE_LEN == MACRO_BLOCK,
          "the macro block begins exactly after the profile block")
    check(MACRO_RECORDS * MACRO_RECORD + 4 == MACRO_LEN,
          "four macro records plus a four-byte tail fill the macro block",
          f"4*{MACRO_RECORD:#x} + 4 == {MACRO_LEN:#x}")
    check(all((i * MACRO_RECORD + MACRO_CHECKSUM_AT) + 2 <= MACRO_LEN
              for i in range(MACRO_RECORDS)),
          "every macro checksum slot lies inside the block",
          f"record i's sum16 is stored at i*{MACRO_RECORD:#x}"
          f"+{MACRO_CHECKSUM_AT:#x}, which is two bytes into the NEXT "
          "record's header and, for the last record, in the four-byte tail")

    prims = primitives()
    check(all(p["opcode_matches_expected"] for p in prims),
          "every request primitive's opcode is decoded from its own "
          "instruction and matches",
          "offsets " + ", ".join(f"+{p['store_offset']}/r{p['register']}"
                                 for p in prims))
    check(len({p["opcode"] for p in prims}) == len(prims),
          "the six primitives carry six distinct opcodes")
    check(len({(p["store_offset"], p["register"]) for p in prims}) > 1,
          "the idiom is searched for, not read at one fixed offset",
          "the six do not share a single offset/register pair")
    check(opcode_store(b"\x00" * PRIMITIVE_SCAN) is None,
          "the opcode decoder finds nothing in bytes that do not carry the "
          "idiom",
          "anti-vacuity for the search")

    groups = small_store()
    check(all(g["bank_b"] - g["bank_a"] == SMALL_BANK_LEN for g in groups),
          "each wear-levelled group's two banks are one 4 KiB apart")
    check(all(sum(i["capacity"] * i["record_len"] for i in g["items"])
              <= SMALL_BANK_LEN for g in groups),
          "each group's items fit inside one bank")
    check(all(i["capacity"] * i["record_len"] == i["region_len"]
              for g in groups for i in g["items"]),
          "every item's declared region length is capacity x record length")
    check(all(i["group"] == g["index"] for g in groups for i in g["items"]),
          "every item names the group that lists it")
    ram = {i["ram_buffer"] for g in groups for i in g["items"]}
    check(DEVICE_HEADER not in ram and GLOBAL_BLOCK not in ram,
          "the two staged blocks are named by their callers, not by the "
          "descriptors",
          "the descriptors point at private staging buffers; FUN_1800e7ee "
          "copies the caller's block into them")

    rom = rom_defaults()
    ac = ac_profile()
    kb = ac["lighting"]["keyboard"]
    single = kb["pattern"]["singleColor"][0]
    check(rom["colour_per_profile"][AC_PROFILE_INDEX]
          == [int(single["r"]), int(single["g"]), int(single["b"])],
          "the ROM colour for profile 3 equals the decode's single colour",
          f"{rom['colour_per_profile'][AC_PROFILE_INDEX]} from "
          f"{ROM_COLOUR_TABLE:#x}")
    check(str(rom["light_slot_per_profile"][AC_PROFILE_INDEX])
          == kb["effectID"],
          "the ROM lighting slot for profile 3 equals the decode's effectID",
          f"slot {rom['light_slot_per_profile'][AC_PROFILE_INDEX]}")
    check(len(rom["light_slot_per_profile"]) == PROFILES
          and all(s in dict(LIGHT_SLOTS) for s in rom["light_slot_per_profile"]),
          "every per-profile default slot is one the setter implements",
          f"{rom['light_slot_per_profile']}")
    check(len(rom["selectable_rows"]) == LEVER_ROWS
          == len(ac["lever"]["functionStatusList"]),
          "the ROM row count equals the decode's function-list length",
          f"{LEVER_ROWS}")

    fields = global_word_fields()
    check(all(f["reset_value"] == f["default"] for f in fields),
          "the factory-reset word reproduces every field's default",
          f"{GLOBAL_RESET_WORD:#x}")
    overlap = [a for i, a in enumerate(fields)
               for b in fields[i + 1:] if a["mask"] & b["mask"]]
    check(not overlap, "no two global-word fields share a bit")

    check(sum16(b"\xff" * 0x1000) == 0xF000,
          "the checksum model wraps at 16 bits rather than saturating",
          "sum16(0xff * 0x1000) == 0xf000")
    check(checksum_a_stamp(0xFFFF, 3) == 0xFFF3
          and checksum_a_stamp(0xFFFF, 4) == 0xFFF4,
          "the stored checksum carries the profile index in its low nibble")
    check(checksum_a_stamp(0xFFF3, 4) != 0xFFF3,
          "a block stamped for one profile does not validate in another",
          "anti-vacuity for the stamp")

    regions = stored_map()
    pairs = [(a, b) for i, a in enumerate(regions) for b in regions[i + 1:]]
    check(all(a["hi"] <= b["lo"] or b["hi"] <= a["lo"] for a, b in pairs),
          "the five stored regions do not overlap each other")
    numeric = [r["name"] for r in regions
               if r["lo"] < BOOTLOADER_REGION[1]
               and BOOTLOADER_REGION[0] < r["hi"]]
    check(numeric,
          "the stored map DOES numerically overlap the bootloader's "
          "application region, so log 111's disjointness does not generalise",
          f"{numeric}")
    check(any(r["name"] == "keymap_banks" and r["lo"] >= BOOTLOADER_REGION[1]
              for r in regions),
          "log 111's own three erase targets remain above the application "
          "region, so its narrower claim still holds")

    ms_ = matches()
    check(any(m.confidence == "unmatched" for m in ms_),
          "at least one Armoury Crate field is left unmatched",
          "a table with no unmatched rows would mean fields were forced")
    check(all(m.evidence for m in ms_),
          "every match row cites evidence")
    check(any(m.ac_field.startswith("performance") and m.confidence
              == "unmatched" for m in ms_),
          "polling rate stays unmatched")

    check(any(p["verdict"] == "RAM-only" for p in persistence())
          and any(p["verdict"] == "persisted" for p in persistence()),
          "the persistence table records both verdicts")
    check("CORRECT in substance" in HOST_INDEPENDENCE
          and "imprecise" in HOST_INDEPENDENCE,
          "the host-independence answer both confirms and corrects the "
          "sentence it was asked about")
    check(any(u["key"] == "storage_medium" for u in unresolved()),
          "the storage medium stays unresolved")
    return out


def to_dict():
    slots, light_end = light_slots()
    return {
        "answer_to_the_host_question": HOST_INDEPENDENCE,
        "armoury_crate_matches": [
            {"ac_field": m.ac_field, "ac_value": m.ac_value, "blob": m.blob,
             "offset": m.offset, "evidence": m.evidence,
             "confidence": m.confidence, "note": m.note}
            for m in matches()],
        "checks": verify(),
        "checksum": {
            "function": 0x180088FE,
            "algorithm": "16-bit additive sum of bytes; not a CRC",
            "listing": "ldrb r4,[r3,r2] / add r0,r4 / uxth r0,r0, bounded by r1",
            "stamp": "the profile block's stored value is the sum ANDed with "
                     "(profile | 0xfff0)",
        },
        "global_block": {
            "address": GLOBAL_BLOCK, "size": 0x20, "profiles": PROFILES,
            "marker_offset": GLOBAL_MARKER_OFFSET, "marker": GLOBAL_MARKER,
            "reset_word": GLOBAL_RESET_WORD,
            "fields": global_word_fields(),
        },
        "keymap_bank": {
            "address": KEYMAP_BANK, "layers": LAYERS, "stride": LAYER_STRIDE,
            "checksum": "sum16(bank + layer*0xd84 + 2, 0xd82) in the bank's "
                        "first halfword, which lives in record 0's first four "
                        "bytes because the default setter never writes them",
            "record_len": RECORD_LEN, "initialised_records": RECORD_KEYS,
            "fallback_index": RECORD_FALLBACK_INDEX,
            "record_fields": [
                {"offset": 0x04, "detail": "0x00 on layer 0, 0xff on layer 1"},
                {"offset": 0x06, "detail": "bit 7 override, bits 0..2 rapid "
                                           "trigger press, 1..6, default 2"},
                {"offset": 0x07, "detail": "bit 7 override, bits 0..2 rapid "
                                           "trigger release, 1..6, default 2"},
                {"offset": 0x08, "detail": "uint16, bit 15 override, bits 0..6 "
                                           "actuation, 1..40, default 10"},
                {"offset": 0x0A, "detail": "uint16 remap target; the 0x51/0x21 "
                                           "handler writes it"},
            ],
        },
        "load_chain": [{"stage": k, "detail": d, "confidence": c}
                       for k, d, c in LOAD_CHAIN],
        "persistence": persistence(),
        "primitives": primitives(),
        "profile_block": {
            "address": PROFILE_BLOCK, "size": PROFILE_LEN,
            "layout": profile_layout(),
            "lighting_slots": slots,
            "lighting_record": [
                {"offset": 0x00, "name": "effect", "detail":
                 "0x0a, 0x0f, 0x14, 0x1e, 0x1f or 0x3c by default"},
                {"offset": 0x01, "name": "brightness", "detail": "default 100"},
                {"offset": 0x02, "name": "unnamed", "detail":
                 "0, or (profile == 0) for slots 3, 6, 8 and 9"},
                {"offset": 0x03, "name": "minus_one_a", "detail": "0xff"},
                {"offset": 0x04, "name": "minus_one_b", "detail": "0xff"},
                {"offset": 0x05, "name": "r", "detail": "request byte 4"},
                {"offset": 0x06, "name": "g", "detail": "request byte 5"},
                {"offset": 0x07, "name": "b", "detail": "request byte 6"},
            ],
        },
        "request_struct": {
            "address": REQUEST_STRUCT,
            "fields": {"0x00": "opcode", "0x04": "buffer", "0x08": "flag",
                       "0x0c": "address", "0x10": "length",
                       "0x18": "pending", "0x19": "cleared"},
            "note": "log 111 mapped +0, +8, +0xc, +0x18 and +0x19 from the two "
                    "erase primitives. The read and write primitives fill two "
                    "more fields, which is how the length and the source "
                    "buffer become visible.",
        },
        "rom_defaults": rom_defaults(),
        "runtime_blocks": [
            {"name": "device_header", "address": DEVICE_HEADER, "size": 0x10},
            {"name": "keymap_layer0", "address": KEYMAP_BANK,
             "size": LAYER_STRIDE},
            {"name": "keymap_layer1", "address": KEYMAP_BANK + LAYER_STRIDE,
             "size": LAYER_STRIDE},
            {"name": "profile_block", "address": PROFILE_BLOCK,
             "size": PROFILE_LEN},
            {"name": "macro_block", "address": MACRO_BLOCK, "size": MACRO_LEN},
            {"name": "global_block", "address": GLOBAL_BLOCK, "size": 0x20},
            {"name": "block_d", "address": BLOCK_D, "size": BLOCK_D_LEN},
        ],
        "save_chain": [{"stage": k, "detail": d, "confidence": c}
                       for k, d, c in SAVE_CHAIN],
        "small_store": {
            "groups": small_store(),
            "mount": "FUN_1800e4ea, from CandidateB_Main",
            "read": "FUN_1800e64e; on a never-written item it fills the "
                    "caller's buffer with 0xff and logs FR_fail",
            "write": "FUN_1800e6d6 synchronously, FUN_1800e7ee to stage",
            "compaction": "FUN_1800e3c8 copies each item's newest record to "
                          "the other bank, zeroes the old bank's first four "
                          "bytes and flips the selector",
            "validation": "a bank is live when its first four bytes are "
                          "neither 0xffffffff nor 0. There is no magic and no "
                          "checksum at this layer.",
        },
        "stored_map": stored_map(),
        "unresolved": unresolved(),
    }


def report_lines():
    d = to_dict()
    out = ["FALCHION ACE HFX — SETTINGS / PROFILE FORMAT",
           "Static and offline. This module never speaks to the device and "
           "constructs no command.", ""]
    out.append("RUNTIME BLOCKS")
    for b in d["runtime_blocks"]:
        out.append(f"  {b['address']:#010x}  {b['size']:#06x}  {b['name']}")
    out += ["", "STORED MAP"]
    for r in d["stored_map"]:
        out.append(f"  {r['lo']:#08x}..{r['hi']:#08x}  {r['name']:<17}"
                   f"{r['formula']}")
    out += ["", f"PROFILE BLOCK {PROFILE_BLOCK:#x}, {PROFILE_LEN:#x} bytes"]
    for f in d["profile_block"]["layout"]:
        out.append(f"  +{f['offset']:#05x}  {f['size']:#06x}  "
                   f"{f['name']:<18}{f['confidence']:<17}{f['detail']}")
    out += ["", "LIGHTING SLOTS"]
    for s in d["profile_block"]["lighting_slots"]:
        out.append(f"  slot {s['slot']}  +{s['offset']:#05x}  {s['size']} bytes")
    out += ["", "GLOBAL BLOCK WORD"]
    for f in d["global_block"]["fields"]:
        out.append(f"  bits {f['shift']:>2}..{f['shift'] + f['width'] - 1:<2} "
                   f"{f['name']:<24} {f['min']}..{f['max']}, default "
                   f"{f['default']}")
    out += ["", "LOAD"]
    for s in d["load_chain"]:
        out.append(f"  {s['stage']:<9}{s['detail']}")
    out += ["", "SAVE"]
    for s in d["save_chain"]:
        out.append(f"  {s['stage']:<9}{s['detail']}")
    out += ["", "ARMOURY CRATE MATCH TABLE"]
    for m in d["armoury_crate_matches"]:
        out.append(f"  {m['confidence']:<11}{m['ac_field']:<45}"
                   f"{m['blob']} {m['offset']}")
    out += ["", "PERSISTED VS RAM-ONLY"]
    for p in d["persistence"]:
        out.append(f"  {p['verdict']:<11}{p['section']}")
    out += ["", "UNRESOLVED"]
    for u in d["unresolved"]:
        out.append(f"  {u['key']:<18}{u['detail']}")
    out += ["", "CHECKS"]
    for c in d["checks"]:
        out.append(f"  {'PASS' if c['ok'] else 'FAIL'}  {c['label']}"
                   + (f" ({c['detail']})" if c["detail"] else ""))
    ok = all(c["ok"] for c in d["checks"])
    out += ["", f"RESULT profile_format_ok={ok} checks={len(d['checks'])}"]
    return out


def _cell(text):
    """Markdown tables end a cell at a bare pipe, and several details contain
    bitwise ORs. Escaping here keeps the generated tables parseable."""
    return str(text).replace("|", "\\|")


def markdown():
    d = to_dict()
    out = ["# Falchion Ace HFX — the settings / profile format", "",
           "Generated by `tool/map_profile_format.py`. Static and offline: no "
           "device was accessed and no command is constructed here.", "",
           "## The question that was asked", "", d["answer_to_the_host_question"],
           "", "## Runtime blocks", "",
           "| address | size | block |", "|---|---|---|"]
    for b in d["runtime_blocks"]:
        out.append(f"| `{b['address']:#010x}` | `{b['size']:#x}` | {b['name']} |")
    out += ["", "The four middle blocks are contiguous, which is why the "
            "profile block is sometimes reached as 'layer 2' of the keymap "
            "bank.", "",
            "## Stored map", "",
            "| region | range | formula | record |", "|---|---|---|---|"]
    for r in d["stored_map"]:
        rec = f"`{r['record_len']:#x}`" if r["record_len"] else "—"
        out.append(f"| {r['name']} | `{r['lo']:#x}`..`{r['hi']:#x}` | "
                   f"`{r['formula']}` | {rec} |")
    out += ["", "## The profile block", "",
            f"`{PROFILE_BLOCK:#x}`, `{PROFILE_LEN:#x}` bytes.", "",
            "| offset | size | field | confidence | detail |",
            "|---|---|---|---|---|"]
    for f in d["profile_block"]["layout"]:
        out.append(f"| `+{f['offset']:#05x}` | `{f['size']:#x}` | {f['name']} "
                   f"| {f['confidence']} | {_cell(f['detail'])} |")
    out += ["", "### The lighting record", "",
            "| offset | field | detail |", "|---|---|---|"]
    for f in d["profile_block"]["lighting_record"]:
        out.append(f"| `+{f['offset']:#04x}` | {f['name']} | {_cell(f['detail'])} |")
    out += ["", "Slots and their offsets:", "",
            "| slot | offset | size |", "|---|---|---|"]
    for s in d["profile_block"]["lighting_slots"]:
        out.append(f"| {s['slot']} | `+{s['offset']:#05x}` | {s['size']} |")
    out += ["", "## The keymap bank", "",
            f"`{KEYMAP_BANK:#x} + layer * {LAYER_STRIDE:#x}`, "
            f"{d['keymap_bank']['checksum']}", "",
            "| offset | detail |", "|---|---|"]
    for f in d["keymap_bank"]["record_fields"]:
        out.append(f"| `+{f['offset']:#04x}` | {_cell(f['detail'])} |")
    out += ["", "## The global block", "",
            f"`{GLOBAL_BLOCK:#x}`, 32 bytes: six packed 32-bit words, one per "
            f"profile, and a `{GLOBAL_MARKER:#x}` marker at "
            f"`+{GLOBAL_MARKER_OFFSET:#x}`.", "",
            "| bits | field | range | default | evidence |",
            "|---|---|---|---|---|"]
    for f in d["global_block"]["fields"]:
        out.append(f"| {f['shift']}..{f['shift'] + f['width'] - 1} | "
                   f"{f['name']} | {f['min']}..{f['max']} | {f['default']} | "
                   f"{_cell(f['note'])} |")
    out += ["", "## The wear-levelled store", "",
            f"- mount: {d['small_store']['mount']}",
            f"- read: {d['small_store']['read']}",
            f"- write: {d['small_store']['write']}",
            f"- compaction: {d['small_store']['compaction']}",
            f"- validation: {d['small_store']['validation']}", "",
            "| group | bank A | bank B | item | record | offset | capacity |",
            "|---|---|---|---|---|---|---|"]
    for g in d["small_store"]["groups"]:
        for i in g["items"]:
            out.append(f"| {g['index']} | `{g['bank_a']:#x}` | "
                       f"`{g['bank_b']:#x}` | `{i['descriptor']:#x}` | "
                       f"`{i['record_len']:#x}` | `{i['bank_offset']:#x}` | "
                       f"{i['capacity']} |")
    out += ["", "## Load", ""]
    for s in d["load_chain"]:
        out.append(f"- **{s['stage']}** — {s['detail']}")
    out += ["", "## Save", ""]
    for s in d["save_chain"]:
        out.append(f"- **{s['stage']}** — {s['detail']}")
    out += ["", "## The Armoury Crate decode, field by field", "",
            "The snapshot is profile 3, which is what makes it usable as a "
            "Rosetta stone: two of the firmware's per-profile ROM defaults "
            "are indexed by exactly that number.", "",
            "| Armoury Crate field | value | blob | offset | confidence | "
            "evidence |", "|---|---|---|---|---|---|"]
    for m in d["armoury_crate_matches"]:
        note = f" {m['note']}" if m["note"] else ""
        out.append(f"| `{m['ac_field']}` | {_cell(m['ac_value'])} | "
                   f"{m['blob']} | {m['offset']} | **{m['confidence']}** | "
                   f"{_cell(m['evidence'])}.{_cell(note)} |")
    out += ["", "## Persisted versus RAM-only", "",
            "| section | verdict | detail |", "|---|---|---|"]
    for p in d["persistence"]:
        out.append(f"| {p['section']} | **{p['verdict']}** | "
                   f"{_cell(p['detail'])} |")
    out += ["", "## Unresolved", ""]
    for u in d["unresolved"]:
        out.append(f"- **{u['key']}** — {u['detail']}")
    out += ["", "## Checks", ""]
    for c in d["checks"]:
        out.append(f"- {'PASS' if c['ok'] else 'FAIL'} — {c['label']}"
                   + (f" ({c['detail']})" if c["detail"] else ""))
    out.append("")
    return "\n".join(out)


def bodies():
    return {
        "profile-format.json": json.dumps(to_dict(), indent=2,
                                          sort_keys=True) + "\n",
        "profile-format.md": markdown(),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = bodies()
    except (OSError, ProfileFormatError, ms.SecondContextError, struct.error,
            KeyError, ValueError, IndexError) as exc:
        print(f"RESULT profile_format_ok=False error={exc}")
        return 1
    if args.check:
        stale = [name for name, body in payload.items()
                 if not (NOTES / name).exists()
                 or (NOTES / name).read_text() != body]
        print(f"RESULT reports_current={not stale} stale={len(stale)}"
              + ("" if not stale else " " + ", ".join(stale)))
        return 0 if not stale else 1
    if args.write:
        for name, body in payload.items():
            path = NOTES / name
            if not path.exists() or path.read_text() != body:
                path.write_text(body)
                print(f"WROTE notes/{name}")
        return 0
    if args.json:
        print(payload["profile-format.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(c["ok"] for c in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
