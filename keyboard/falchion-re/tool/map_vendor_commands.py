#!/usr/bin/env python3
"""The complete vendor-HID command surface, recovered statically.

Read-only and offline. Authorises nothing live and CONSTRUCTS NO FRAME: every
byte string here is a field layout read out of the dispatcher's own compare and
store instructions, and every state-writing command carries
`owner_approval_required`.

WHAT THIS ADDS. notes/protocol.md's command table has six entries and its "still
unknown" list names actuation, rapid trigger, dead zone, speed tap, profile
switch and polling rate as HAL methods with no opcode. Log 126 decoded one of
them from a capture. This step enumerates the dispatcher's compare sites
directly, so the surface is bounded by the firmware rather than by what happened
to be captured: SEVENTEEN top-level opcodes and TWENTY-FOUR 0x51 subcommands,
every one of them located, and each labelled with what the evidence actually
supports.

THE CONFIDENCE SCHEME, which is the point of the exercise:
  wire-proven            observed on the wire AND decoded
                         from the handler
  static-handler-proven  the handler's reads, ranges and stores are read out of
                         the instruction stream; capture observations are
                         graded separately below
  static-located-only    the compare site and handler entry are proven; the
                         semantics are NOT established
  hal-name-only          notes/protocol.md names a HAL method; nothing here
                         attaches an opcode to it
No command is named for a feature on resemblance alone.

No device access. Examples:
    python3 tool/map_vendor_commands.py
    python3 tool/map_vendor_commands.py --json
    python3 tool/map_vendor_commands.py --write
    python3 tool/map_vendor_commands.py --check
"""
import argparse
from collections import Counter
import functools
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
PERIPHERALS = ROOT / "ghidra/peripherals"

APP = ("installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin",
       0x18000000)
VENDOR_APP = ("vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin",
              0x18000000)
ENTRY = ("installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin", 0)

DISPATCHER = 0x18001FBE          # VendorHID_CommandDispatcher (FINDINGS)
REQ_BUF = 0x180233A8             # log 107
SEND_RESPONSE_64 = 0x18000A70    # log 107
STORAGE_SM = 0x18000D56          # log 125's storage state machine

# The RAM blocks, from log 125 and log 127.
BLOCKS = {
    0x180202D8: "keymap bank (2 x 0xd84)",
    0x18021DE0: "profile block (0x81c)",
    0x180225FC: "macro block (0x664)",
    0x1801FEF8: "block D (0x3e0)",
    0x18024F0C: "global block (32 B)",
    0x1801E6D0: "device header (16 B)",
    0x18022C60: "storage request struct",
    0x1801E736: "polling-rate multiplier",
}
PROFILE_SELECT = 0x1801E6D6      # device header + 6, log 125

# Every compare site in the dispatcher's top-level opcode chain, with the byte
# it tests and the branch target. Pinned to the image; a test breaks if any
# instruction moves.
TOP_LEVEL_SITES = (
    (0x18001FF2, 0x52, "2a52", 0x180028E0),
    (0x18001FFC, 0x41, "2a41", 0x180028E2),
    (0x18002002, 0x04, "2a04", 0x18002052),
    (0x18002006, 0x12, "2a12", 0x18002066),
    (0x1800200A, 0x22, "2a22", 0x180020E4),
    (0x1800200E, 0x25, "2a25", 0x180022BE),
    (0x18002014, 0x43, "2a43", 0x180020E8),
    (0x18002018, 0x50, "2a50", 0x18002110),
    (0x1800201C, 0x51, "2a51", 0x1800248E),
    (0x18002022, 0xB0, "2ab0", 0x180039EA),
    (0x1800202A, 0x53, "2a53", 0x18002112),
    (0x1800202E, 0x54, "2a54", 0x18002114),
    (0x18002032, 0x71, "2a71", 0x18003954),
    (0x18002038, 0x73, "2a73", 0x18003A2E),
    (0x18002040, 0xC0, "2ac0", 0x18002116),
    (0x18002044, 0xFA, "2afa", 0x18003A70),
    (0x1800204A, 0xFD, "2afd", 0x180040A4),
)

# The 0x51 subcommand chain. Same discipline.
SUB_SITES = (
    (0x18002492, 0x4F, "2a4f", 0x18002B62),
    (0x18002498, 0x23, "2a23", 0x180027D6),
    (0x1800249E, 0x20, "2a20", 0x1800253E),
    (0x180024A4, 0x00, "b37a", 0x18002514),   # cbz r2 -> 0x18002506 -> 0x18002514
    (0x180024A6, 0x0C, "2a0c", 0x18002D8E),
    (0x180024AA, 0x18, "2a18", 0x18002C9A),
    (0x180024B0, 0x21, "2a21", 0x18002662),
    (0x180024B4, 0x22, "2a22", 0x18002662),
    (0x180024BE, 0x2D, "2a2d", 0x18002ACA),
    (0x180024C8, 0x24, "2a24", 0x1800289A),
    (0x180024CC, 0x2C, "2a2c", 0x18002970),
    (0x180024D2, 0x31, "2a31", 0x18002B2E),
    (0x180024D6, 0x42, "2a42", 0x18003310),
    (0x180024DC, 0x55, "2a55", 0x18002DC6),
    (0x180024F6, 0x58, "2a58", 0x18002DC8),
    (0x180024FC, 0x56, "2a56", 0x18002DCA),
    (0x18002500, 0x57, "2a57", 0x18002CDA),
    (0x1800250A, 0x59, "2a59", 0x18002DCC),
    (0x1800250E, 0x90, "2a90", 0x18002D0E),
)
# Subcommands 0x50..0x54 come from a byte table, decoded from the image.
SUB_TBB = (0x180024EC, 0x180024F0, 0x50, 5)

# The 0x12 query chain: a table branch for 0x00..0x08 plus explicit compares.
QUERY_TBH = (0x18002072, 0x18002076, 0x00, 9)
QUERY_SITES = (
    (0x18002068, 0x12, "2a12", 0x18002118),
    (0x18002088, 0x13, "2a13", 0x1800211A),
    (0x1800208C, 0x14, "2a14", 0x180021D4),
    (0x18002090, 0x15, "2a15", 0x18002254),
    (0x18002094, 0x16, "2a16", 0x1800226C),
)

# Instruction bytes this model cites. Anchors every claim below to the image.
CITED = {
    # Log 139: physical rapid-trigger switch, shared bit and input report.
    0x180068AE: "2047",            # GPIO identifier 0x47
    0x180068C4: "f3c0 1340",       # extract current-profile bit 5
    0x180068D0: "1c52",            # consecutive mismatch count +1
    0x180068D4: "42b2",            # compare count with caller threshold
    0x180068D6: "d91c",            # return while count <= threshold
    0x180068EA: "f020 0020",       # clear bit 5 on nonzero GPIO resample
    0x180068F6: "f845 0021",       # store current-profile global word
    0x180068FC: "2076",            # queue report opcode 0x76
    0x1800690A: "f040 0020",       # set bit 5 on zero GPIO resample
    0x180022D6: "f3c0 1040",       # 25 00 reads the same bit
    0x180022DA: "7118",            # reply byte 4
    0x180044B2: "7047 7086 70c5 7104", # queue bytes 1..4 = r7,r6,r5,r4
    0x18001D8E: "f843 0021",       # single-profile reset replaces whole word
    0x18001E24: "f843 2021",       # all-profile reset replaces whole word
    # dispatcher entry: r4 = the request buffer, r7 = the device header
    0x18001FC2: "4c6c",              # ldr r4,[pc] -> 0x180233a8
    0x18001FEE: "f109 071c",         # add.w r7,r9,#0x1c  -> 0x1801e6d0
    # 51 00 — the profile switch, posted into the storage request struct
    0x18002514: "7921",              # ldrb r1,[r4,#0x4]
    0x18002516: "2906",              # cmp  r1,#0x6
    0x1800251E: "2906",              # cmp  r1,#0x6   (reject >= 6)
    0x1800252C: "2202",              # movs r2,#0x2   the request opcode
    0x1800252E: "7002",              # strb r2,[r0]       REQSTRUCT+0x84
    0x18002530: "7041",              # strb r1,[r0,#0x1]  REQSTRUCT+0x85
    # FUN_18000d56 consumes it and writes the selection byte
    0x180011B8: "f898 0001",         # ldrb.w r0,[r8,#0x1]
    0x180011BC: "71a0",              # strb   r0,[r4,#0x6]   DEVHDR+6
    # 51 21 / 51 22 — the remap family
    0x18002662: "78a1",              # ldrb r1,[r4,#0x2]   source
    0x18002664: "29bc",              # cmp  r1,#0xbc
    0x1800266C: "289f",              # cmp  r0,#0x9f
    0x18002686: "2bbc",              # cmp  r3,#0xbc
    0x180026D2: "f8a2 30d4",         # strh.w r3,[r2,#0xd4]  profile key table
    # 51 50 — all-key actuation into the global block
    0x18002BE4: "79b9",              # ldrb r1,[r7,#0x6]   the profile index
    0x18002BE8: "7923",              # ldrb r3,[r4,#0x4]   the value
    0x18002BEE: "f363 224f",         # bfi  r2,r3,#9,#7    log 125's bits 9..15
    0x18002BFA: "f004 f89f",         # bl 0x18006d3c       the clamp
    # 51 42 — the global block's marker halfword
    0x18003316: "8308",
    # 12 00 — eight bytes of the device header
    0x180020A2: "e9d9 6007",         # ldrd r6,r0,[r9,#28]  -> 0x1801e6d0
    0x180020A6: "e9c1 600d",         # strd r6,r0,[r1,#52]  -> reply payload
    0x180020AE: "2006",              # movs r0,#0x6   0 is reported as 6
    # 12 15 — the polling-rate read-back (log 126)
    0x18002258: "f890 04f8",
    0x1800225C: "f000 000f",
    # the shared responder
    0x180030C4: "2051",              # movs r0,#0x51
    0x18002250: "2012",              # movs r0,#0x12
    0x180033A4: "f7fd fb64",         # bl 0x18000a70  SendResponse64
    # the +0x22 hold timer's expiry emit (log 127's site)
    0x180054C4: "8c13",              # ldrh r3,[r2,#0x20]
    0x180054DA: "f82c 3011",         # strh.w r3,[r12,r1,lsl #1]
    0x180054DE: "1c49",              # adds r1,r1,#0x1
    # the macro block's header write
    0x180035DC: "7008",
    0x180035E0: "71cd",
    0x180035E2: "f44f 71c8",         # mov.w r1,#0x190   400 bytes cleared
    # --- log 130: the located-only remainder ---
    0x18002BA4: "8910",          # 51 4f  ldrh r0,[r2,#0x8]   per-key record +0x08
    0x18002BA6: "f36c 0006",     # 51 4f  bfi  r0,r12,#0,#7   actuation, 1..40
    0x18002BBA: "f3c7 2746",     # 51 4f  ubfx r7,r7,#9,#7    the global all-key value
    0x18002BCC: "f440 4000",     # 51 4f  orr  r0,r0,#0x8000  the override bit
    0x18003332: "7923",          # 51 58  ldrb r3,[r4,#0x4]
    0x18003336: "2b05",          # 51 58  cmp  r3,#0x5
    0x1800334C: "f00c fafc",     # 51 58  bl   0x1800f948, mode 0 (all-key)
    0x18003364: "7960",          # 51 59  ldrb r0,[r4,#0x5]   the layer selector
    0x1800338C: "f00c fadc",     # 51 59  bl   0x1800f948, mode 1 (per-key)
    0x1800F972: "f1a2 0c01",     # f948   subs r12,r2,#0x1
    0x1800F976: "f1bc 0f06",     # f948   cmp  r12,#0x6       range 1..6
    0x1800F97C: "2202",          # f948   movs r2,#0x2        else the default
    0x1800F9A8: "f022 0280",     # f948   bic  r2,r2,#0x80    clear the override
    0x1800F9AC: "f368 0202",     # f948   bfi  r2,r8,#0,#3
    0x1800F9B0: "f88c 2006",     # f948   record +0x06, UI bottom dead zone
    0x1800F9CC: "f854 c025",     # f948   ldr  r12,[r4,r5,lsl #2]  the global word
    0x1800F9D0: "f362 5c16",     # f948   bfi  r12,r2,#20,#3  global bits 20..22
    0x1800F9FC: "f3c4 4442",     # f948   ubfx r4,r4,#17,#3   global bits 17..19
    0x1800FA0A: "79da",          # f948   record +0x07, UI top dead zone
    0x1800FA26: "71e2",          # f948   strb r2,[r4,#0x7]
    0x180031BC: "4843",          # 51 56  ldr  r0,[pc] -> block D
    0x180031D0: "7006",          # 51 56  strb r6,[r0]
    0x180031E2: "a03e",          # 51 56  adr  -> "S_ST_DEF"
    0x1800322A: "481d",          # 51 90
    0x1800325C: "a026",          # 51 90  adr  -> "SC_S_A"
    0x18003260: "4827",          # 51 18
    0x1800329A: "a01b",          # 51 18  adr  -> "=MS_A"
    0x180027D2: "a07e",          # 51 23  adr  -> "=KC_S,T_A"
    0x18002814: "f886 9004",     # 51 23  strb r9,[r6,#0x4]   record +0x04 = 1
    0x1800281A: "73b7",          # 51 23  strb r7,[r6,#0xe]
    0x1800281E: "73f7",          # 51 23  strb r7,[r6,#0xf]
    0x180028EC: "713a",          # 51 24  strb r2,[r7,#0x4]   record +0x04 = 2
    0x18003028: "f367 3c8f",     # 51 54  bfi  r12,r7,#14,#2
    0x1800302C: "f8a2 c00a",     # 51 54  strh.w r12,[r2,#0xa]
    0x180030F0: "a070",          # 51 55  adr  -> "=TEMP1_S_KC"
    0x18003112: "a06b",          # 51 55  adr  -> "=TEMP2_S_KC"
    0x1800311C: "298d",          # 51 55  cmp  r1,#0x8d       usage 0x04..0x91
    0x18003122: "2907",          # 51 55  cmp  r1,#0x7        or 0xe0..0xe7
    0x180033B2: "8862",          # 51 0c  ldrh r2,[r4,#0x2]
    0x180033C2: "6008",          # 51 0c  str  r0,[r1]        0x3e8 -> 0x1801e6c8
    0x180021B4: "2201",          # 12 13  movs r2,#0x1
    0x180021D0: "2113",          # 12 13  movs r1,#0x13
    # --- log 130: block D's entry array ---
    0x18005830: "eb0a 0741",     # add.w  r7,r10,r1,lsl #1    block D + i*2
    0x18005834: "797a",          # ldrb   r2,[r7,#0x5]        entry +1, the flags
    0x18005840: "f897 c004",     # ldrb.w r12,[r7,#0x4]       entry +0, the value
    0x1800585A: "29f7",          # cmp    r1,#0xf7            247 entries
    # --- log 130: the dual-role banks ---
    0x180054D0: "4974",          # the writer's literal -> 0x18024000
    0x18006094: "eb09 00c0",     # the consumer's add.w r0,r9,r0,lsl #3
    0x1800609C: "f830 0012",     # ldrh.w r0,[r0,r2,lsl #1]
    0x180060A4: "42a8",          # cmp    r0,r5   current vs previous bank
    # --- log 138: complete rapid-trigger fields and dead-zone argument order ---
    0x180026E4: "e3fe",          # table stub -> 0x18002ee4
    0x18002EE4: "e07e",          # second stub -> 0x18002fe4
    0x18002FE4: "7960",          # layer byte 5
    0x18002FEE: "7921",          # wire key byte 4
    0x18003008: "5c89",          # wire key -> record index
    0x1800300C: "7a1a",          # enable byte 8
    0x18003020: "79df",          # mode-control byte 7
    0x18003026: "1c7f",          # mode = byte 7 + 1, truncated to two bits
    0x18003030: "885a",          # selector is LE16 bytes 2-3
    0x18003050: "f427 4740",     # disabled: clear mode, still write sensitivity
    0x18003068: "799f",          # sensitivity byte 6
    0x1800306E: "f367 0106",     # combined: release bits 0..6
    0x18003072: "f367 11cd",     # combined: press bits 7..13
    0x1800308C: "799f",          # press sensitivity byte 6
    0x18003092: "f367 1ccd",     # selector 1: press bits 7..13
    0x180030AC: "f893 c006",     # release sensitivity byte 6
    0x180030B2: "f36c 0706",     # selector 2: release bits 0..6
    0x180030BC: "540e",          # mark keymap layer dirty at 0x1801e6b9
    0x1800333A: "7962",          # 51 58 byte 5 -> r2 -> bits 20..22
    0x1800336E: "79a3",          # 51 59 byte 6 -> r3 -> record +7
    0x18003376: "79e2",          # 51 59 byte 7 -> r2 -> record +6
    0x1800FA60: "f363 4253",     # r3 -> global bits 17..19
    0x1800FA74: "e6c3",          # tail -> cache builder 0x1800f7fe
    0x1800F83E: "1e6d",          # record +6 value minus 1
    0x1800F840: "f882 55b4",     # bottom-labelled value -> shared +0x5b4
    0x1800F850: "1e52",          # record +7 value minus 1
    0x1800F852: "f880 264a",     # top-labelled value -> shared +0x64a
    0x1800F8DE: "f88c 764a",     # all-key resolved top cache
    0x1800F916: "f887 45b4",     # all-key resolved bottom cache
    0x180055EE: "f8be 200a",     # rapid-trigger consumer reads record +0x0a
    0x180055F2: "0b91",          # test mode bits 14..15
    0x18005600: "0689",          # additionally test global bit 5
    0x1800563E: "f002 007f",     # release sensitivity
    0x1800564A: "f3c2 12c6",     # press sensitivity
    0x1800564E: "eb00 0080",     # release scale x5
    0x18005652: "eb02 0282",     # press scale x5
    0x180056EA: "2008",          # near-rest effective release floor
    0x180056F8: "da0c",          # strict delta comparison
    0x18001552: "79a1",          # profile completion reply reads CURRENT profile
    0x18001556: "2106",          # internal profile 0 reported as 6
}

ACCESS_RE = re.compile(
    r"^ACCESS target=0x(?P<target>[0-9a-f]+) width=(?P<width>\d+) "
    r"dir=(?P<dir>read|write) instr=(?P<instr>[0-9a-f]+) "
    r"func=(?P<func>[0-9a-f]+) base=(?P<base>\S+) off=(?P<off>-?\d+) "
    r"stored=(?P<stored>\S+)$")

WIRE_MODEL = NOTES / "polling-rate-protocol.json"
PROFILE_MODEL = NOTES / "profile-format.json"


class CommandError(Exception):
    """Raised on any input this tool refuses to guess about."""


# ------------------------------------------------------------------- inputs

@functools.lru_cache(maxsize=None)
def image(name):
    path = IMPORTS / name
    if not path.exists():
        raise CommandError(f"image slice missing: {path}")
    return path.read_bytes()


def halfwords(addr, count, slice_=APP):
    name, base = slice_
    d = image(name)
    off = addr - base
    if not 0 <= off <= len(d) - 2 * count:
        raise CommandError(f"{addr:#x}+{count}hw is outside {name}")
    return " ".join(f"{struct.unpack_from('<H', d, off + 2 * i)[0]:04x}"
                    for i in range(count))


def byte(addr, slice_=APP):
    name, base = slice_
    d = image(name)
    off = addr - base
    if not 0 <= off < len(d):
        raise CommandError(f"{addr:#x} is outside {name}")
    return d[off]


@functools.lru_cache(maxsize=None)
def census():
    rows = []
    files = sorted(PERIPHERALS.glob("*.txt"))
    if not files:
        raise CommandError(f"no peripheral census in {PERIPHERALS}")
    for path in files:
        for line in path.read_text().splitlines():
            m = ACCESS_RE.match(line)
            if m:
                rows.append({"file": path.name,
                             "target": int(m.group("target"), 16),
                             "dir": m.group("dir"),
                             "instr": int(m.group("instr"), 16),
                             "func": int(m.group("func"), 16),
                             "base": m.group("base"),
                             "off": int(m.group("off"))})
    return tuple(rows)


INSTALLED_EXPORT = "installed_b.txt"


def accesses(lo, hi=None, export=INSTALLED_EXPORT):
    """Resolved accesses in one export.

    Scoping to a single export matters: the vendor application is based at the
    same 0x18000000, so an unscoped range query silently merges two releases
    and turns a one-writer block into a five-writer one.
    """
    hi = lo + 1 if hi is None else hi
    return [r for r in census()
            if lo <= r["target"] < hi and r["file"] == export]


# --------------------------------------------------------- table decoding

def decode_tbb(instr_addr, table_addr, first, count):
    """A Thumb `tbb [pc,rN]` jump table, read out of the image."""
    pc = instr_addr + 4
    out = {}
    for i in range(count):
        out[first + i] = pc + 2 * byte(table_addr + i)
    return out


def decode_tbh(instr_addr, table_addr, first, count):
    """A Thumb `tbh [pc,rN,lsl #1]` jump table."""
    pc = instr_addr + 4
    name, base = APP
    d = image(name)
    out = {}
    for i in range(count):
        hw = struct.unpack_from("<H", d, table_addr - base + 2 * i)[0]
        out[first + i] = pc + 2 * hw
    return out


# -------------------------------------------------------- the command map

Q = "query"
W = "write"
H = "handshake"

# Curated semantics. Every row's `evidence` names the instruction it is read
# from, and `confidence` is from the four-value scheme in the module docstring.
SUBCOMMANDS = (
    (0x00, "static-handler-proven", W,
     "PROFILE SWITCH (indirect). Request byte 4 is the profile, accepted 0..5 "
     "with 6 folded to 0; anything else is refused at 0x1800251e. The handler "
     "does NOT write the selection byte — it posts opcode 2 into the storage "
     "request struct at +0x84 with the profile at +0x85 and returns.",
     "0x18002514 ldrb [r4,#4]; 0x18002516/0x1800251e cmp #6; "
     "0x1800252c movs r2,#2; 0x1800252e/0x18002530 strb into REQSTRUCT+0x84/85",
     "storage request struct -> device header +6"),
    (0x0C, "static-handler-proven", W,
     "request bytes 2-3 are a 16-bit selector: value 0 stores 1000 (0x3e8) into "
     "the word at 0x1801e6c8; either value then stores 1 and request byte 4 "
     "into 0x18025aa0 +1 and +2. Replies 51 0c with a ONE-byte payload. The "
     "consumers of 0x1801e6c8 and 0x18025aa0 are NOT identified, so what the "
     "1000 counts is unknown.",
     "0x180033b2 ldrh [r4,#2]; 0x180033c2 str 0x3e8 -> 0x1801e6c8; "
     "0x180033c6/0x180033ca strb into 0x18025aa0+1/+2",
     "0x1801e6c8 and 0x18025aa0 (RAM, consumers unknown)"),
    (0x18, "static-handler-proven", W,
     "the firmware names it =MS_A. Stores request byte 2 and request byte 4 "
     "into the runtime struct at 0x18022d44 at +0x05/+0x06 AND again at "
     "+0x19d/+0x19e — one live copy and one shadow 0x198 apart — and, when "
     "*(0x18024ebc+0x30) is 1, writes 5 to +0x38. Replies 51 18 with a TWO-byte "
     "payload. What MS_A stands for is NOT established.",
     "0x18003260..0x1800328a; 0x18003272/0x18003276 strb +5/+6; "
     "0x18003278/0x1800327c strb +0x19d/+0x19e; 0x1800329a adr '=MS_A'",
     "0x18022d44 +0x05/+0x06 and +0x19d/+0x19e (RAM)"),
    (0x20, "static-handler-proven", W,
     "the key-remap family's third entry: byte 2 is the source (<= 0xbc), byte "
     "3 must be 0x00 or 0x9f, bytes 4-5 are a 16-bit target. Writes the profile "
     "block's key table.",
     "0x1800253e ldrb [r4,#4]/[r4,#5]; 0x1800254e cmp #0xbc; 0x18002556 cmp "
     "#0x9f", "profile block +0xd4 (+ layer*0x1ee)"),
    (0x21, "wire-proven", W,
     "SET KEY BINDING (base or Fn layer). Byte 2 source <= 0xbc, byte "
     "3 in {0x00, 0x9f}, bytes 4-5 the 16-bit target; targets <= 0xbc go "
     "through the translation table, 0xff/0xc7/0xc8/0xd3 take separate paths. "
     "The store is a halfword into the profile block's key table.",
     "0x18002662 ldrb [r4,#2]; 0x18002664 cmp #0xbc; 0x1800266c cmp #0x9f; "
     "0x18002686 cmp #0xbc; 0x180026d2 strh.w [r2,#0xd4]",
     "profile block +0xd4 + layer*0x1ee + xlate[src]*2"),
    (0x22, "static-handler-proven", W,
     "shares 0x21's handler entry at 0x18002662 — the two compare sites both "
     "branch to it. FINDINGS records 0x22 as the variant that SETS the per-key "
     "mode byte and stores an actuation value, where 0x21 clears it.",
     "0x180024b0/0x180024b4 both -> 0x180024b8 -> 0x18002662",
     "profile block key table + keymap record"),
    (0x23, "static-handler-proven", W,
     "the firmware names it =KC_S,T_A — key code, source and target. Byte 2 is "
     "the source (<= 0xbc), byte 3 the layer (0x00 or 0x9f); the handler "
     "resolves the per-key record and writes THREE fields: record +0x04 = 1 "
     "(the mode byte 0x21 clears), +0x0e = request byte 4 and +0x0f = request "
     "byte 5, then a 16-bit target from bytes 6-7 through the same translation "
     "table and the same 0xff/0xc7/0xc8/0xd3 special cases as the remap family. "
     "Records +0x0e and +0x0f are OUTSIDE log 125's field map and are not "
     "named here.",
     "0x180027d8 cmp #0xbc; 0x180027e0 cmp #0x9f; 0x18002814 strb rec+0x04; "
     "0x1800281a strb rec+0x0e; 0x1800281e strb rec+0x0f; 0x180027d2 adr "
     "'=KC_S,T_A'",
     "keymap record +0x04, +0x0e, +0x0f and the remap target"),
    (0x24, "static-handler-proven", W,
     "the same source/layer guard as the remap family, then record +0x04 = 2 — "
     "a THIRD value of the mode byte, where 0x21 clears it and 0x23 writes 1 — "
     "followed by a 16-bit target from bytes 5-6 through the translation table "
     "with the 0xff/0xc7/0xc8/0xd3 special cases. So the mode byte is at least "
     "four-valued.",
     "0x1800289e cmp #0xbc; 0x180028a8 cmp #0x9f; 0x180028ec strb r2(=2) into "
     "rec+0x04; 0x18002908 the translation table",
     "keymap record +0x04 and the remap target"),
    (0x2C, "static-handler-proven", W,
     "byte 2 is compared against 4, 5 and 7; the handler calls a copy routine "
     "and the storage request primitive at 0x18000b28, and writes the device "
     "header +5 and the byte at 0x1801e6b7.",
     "0x18002972/0x18002976/0x1800297a cmp #4/#5/#7; 0x180029a0 strb [r7,#5]",
     "device header +5"),
    (0x2D, "static-handler-proven", W,
     "LIGHTING. Byte 2 is compared against 2 and 4; the handler reads and "
     "rewrites the profile block's flags halfword at +0x02 and calls the "
     "lighting default setter FUN_1800075a that log 125 recovered.",
     "0x18002ace cmp #2; 0x18002ad2 cmp #4; 0x18002af6 strh.w profile+0x2; "
     "bl 0x1800075a", "profile block +0x02 and the lighting slots at +0x04"),
    (0x31, "wire-proven", W,
     "SET POLLING RATE. Byte 4 is a 4-bit index, accepted only 0 and 3; writes "
     "profile block +0x4f8 bits 0..3 and caches 1 << index at 0x1801e736. "
     "Fully decoded in logs 126 and 127.",
     "0x18002b2e ldrb [r4,#4]; 0x18002b30 cmp #3; 0x18002b3e bfi #0,#4",
     "profile block +0x4f8 bits 0..3"),
    (0x42, "static-handler-proven", W,
     "writes the global block's halfword at +0x18 — the marker log 125 records "
     "the demo-mode check owning — from request byte 4, and calls the "
     "wear-levelled store's write primitive.",
     "0x18003310; 0x18003316/0x1800331c strh global+0x18; bl 0x1800e6d6",
     "global block +0x18, wear-levelled store"),
    (0x4F, "static-handler-proven", W,
     "PER-KEY ACTUATION, the exact counterpart of 0x50. Byte 5 is the layer "
     "(0x00 or 0x9f), byte 4 the key (<= 0xbc), byte 6 the value: the handler "
     "writes bits 0..6 of the per-key record's halfword at +0x08 — log 125's "
     "per-key actuation, range 1..40 — then compares it against the profile's "
     "ALL-KEY value in global bits 9..15 and CLEARS the +0x08 bit-15 override "
     "when they are equal, SETS it when they differ. Log 125 recovered that "
     "field and that override bit independently.",
     "0x18002b68 cmp #0x9f; 0x18002b76 cmp #0xbc; 0x18002ba4 ldrh rec+0x08; "
     "0x18002ba6 bfi #0,#7; 0x18002bba ubfx #9,#7; 0x18002bc6 bic #0x8000; "
     "0x18002bcc orr #0x8000",
     "keymap record +0x08 bits 0..6 plus the bit-15 override"),
    (0x50, "static-handler-proven", W,
     "ALL-KEY ACTUATION. Indexes the global block by the CURRENT PROFILE "
     "(device header +6) and inserts request byte 4 into bits 9..15 — log 125's "
     "actuation field, range 1..40 — then calls the clamp at 0x18006d3c that "
     "log 125 showed raising values below 0x28 and lowering above 1. This is "
     "the strongest match in the table to a HAL name (SetActuation_AllKey), and "
     "it is offered as a match, not as the command's name.",
     "0x18002be4 ldrb [r7,#6]; 0x18002be8 ldrb [r4,#4]; 0x18002bee bfi #9,#7; "
     "bl 0x18006d3c", "global block, bits 9..15 of the profile's word"),
    (0x51, "static-handler-proven", W,
     "stores the constant 0x3c into the word at 0x1801e7b8 and replies. The "
     "cell's consumer is NOT identified.",
     "0x18002c0a ldr r1,[pc] -> 0x1801e7b8; 0x18002c10 str r0,[r1]",
     "0x1801e7b8 (RAM, consumer unknown)"),
    (0x52, "static-located-only", W,
     "byte 2 selects one of five paths through a byte table at 0x18002c24 "
     "(targets 0x18002c2a, 0x18002c38, 0x18002c3e, 0x18002c4a and 0x18002c60), "
     "each loading a different set of small constants into r0 and the stack "
     "frame; the paths converge at 0x18002c6c, which reads request byte "
     "(4 + r0) and switches on 0, 1 and 2, calling the short responder on any "
     "other value. The constants are opaque and the store target is NOT "
     "established — this is the one subcommand this step could not decode.",
     "0x18002c1c cmp #0x5; 0x18002c20 tbb; the five targets above",
     "unestablished"),
    (0x53, "static-handler-proven", W,
     "byte 7 selects a layer (0 or 1, anything else rejected) and byte 6 gates "
     "a per-key record update at keymap + layer*0xd84 + key*0x20 + 0x0a.",
     "0x18002efa ldrb [r4,#7]; 0x18002f1a movw #0x361; 0x18002f36 bfi #14,#2",
     "keymap record +0x0a"),
    (0x54, "static-handler-proven", W,
     "PER-KEY RAPID TRIGGER. Byte 5 selects layer 00/9f; byte 4 <= bc is "
     "translated to a record index. At record +0x0a, LE16 bytes 2-3 select "
     "00 both sensitivities, 01 press bits 7..13, or 02 release bits 0..6. "
     "Byte 6 supplies the low seven bits without a handler range clamp. "
     "Byte 8 zero clears mode bits 14..15; otherwise the mode is "
     "(byte 7 + 1) & 3. Sensitivities are written even when disabled. The mode "
     "store precedes selector validation, so an invalid selector can change "
     "mode before a short rejection reply. Valid writes mark the layer dirty "
     "and echo 60 payload bytes. The consumer additionally requires global "
     "bit 5 and scales both sensitivity fields by five (log 138).",
     "0x180026e4 -> 0x18002ee4 -> 0x18002fe4; 0x18003028 bfi #14,#2; "
     "0x18003030 ldrh selector; 0x1800306e/72 bfi #0/#7; "
     "0x18003092 press; 0x180030b2 release; 0x180055ee..0x18005762 consumer",
     "keymap record +0x0a: release bits 0..6, press bits 7..13, mode bits 14..15"),
    (0x55, "static-handler-proven", W,
     "the firmware names its two halves =TEMP1_S_KC and =TEMP2_S_KC. Bytes 4-5 "
     "and bytes 6-7 are TWO 16-bit key codes, each bounded at 0xbc and passed "
     "through the translation table, and each result is then range-checked to "
     "HID usage 0x04..0x91 or 0xe0..0xe7 — the printable block and the eight "
     "modifiers — with byte 8 gating the write. So it configures a PAIR of key "
     "codes. Which feature consumes the pair is NOT established.",
     "0x180030e2/0x18003104 cmp #0xbc; 0x1800311c cmp #0x8d; 0x18003122 cmp "
     "#0x7; 0x180030f0 adr '=TEMP1_S_KC'; 0x18003112 adr '=TEMP2_S_KC'",
     "unestablished (a validated key-code pair)"),
    (0x56, "static-handler-proven", W,
     "SETTINGS FACTORY DEFAULT, and the firmware says so: the handler passes "
     "BLOCK D to 0x180005c6 and then to 0x1800aadc with r1 = 1, sets the byte "
     "at 0x1801e737 to 1, replies 51 56 with a 60-byte payload and logs "
     "S_ST_DEF. It is the only located command that reinitialises block D, "
     "which otherwise has no USB writer at all.",
     "0x180031bc ldr -> 0x1801fef8; bl 0x180005c6; bl 0x1800aadc; 0x180031d0 "
     "strb 1 -> 0x1801e737; 0x180031e2 adr 'S_ST_DEF'",
     "block D (0x1801fef8) via its initialisers"),
    (0x57, "static-handler-proven", W,
     "enters the shared per-key writer tail at 0x18002cdc, which updates keymap "
     "record +0x08 (bits 0..6, clearing bit 15) and +0x0a (two 7-bit fields, "
     "clearing bits 14-15) for BOTH layers under flag control.",
     "0x18002500 cmp #0x57 -> 0x180031e6; the tail at 0x18002cdc..0x18002dc0",
     "keymap records +0x06/+0x07/+0x08/+0x0a, both layers"),
    (0x58, "static-handler-proven", W,
     "GLOBAL DEAD ZONE (logs 136-137 correct the earlier rapid-trigger label). "
     "Bytes 4 and 5 are the top and bottom values in 0.1 mm, "
     "each accepted as 1..5 with 0 folded to 6 and anything above 5 refused; "
     "the handler calls 0x1800f948 with mode 0, which range-checks each value "
     "to 1..6 (substituting the default 2) and inserts them into the profile's "
     "global word: byte 4 (UI top) -> BITS 17..19; byte 5 (UI bottom) -> "
     "BITS 20..22. The r3/r2 argument order matters (log 138). Log 125 called these "
     "rapid-trigger fields; the captured single-step dead-zone changes correct "
     "that semantic label while retaining the instruction-derived stores.",
     "0x18003334/0x18003336 the 0-folds-to-6 and > 5 refusal; 0x1800334c bl "
     "0x1800f948; 0x1800f976 cmp #6; 0x1800f97c movs #2; 0x1800f9d0 bfi #20,#3; "
     "0x1800f9fc ubfx #17,#3",
     "global block: UI top bits 17..19, UI bottom bits 20..22"),
    (0x59, "static-handler-proven", W,
     "PER-KEY DEAD-ZONE OVERRIDES, the static counterpart of 0x58. Byte 5 is the layer "
     "(0x00 or 0x9f), byte 4 the key (<= 0xbc), bytes 6 and 7 wire values "
     "0..5 (0 folds to internal 6; 6 and greater are rejected); "
     "it calls 0x1800f948 with mode 1, "
     "which writes byte 7 (UI bottom counterpart) into record +0x06 and "
     "byte 6 (UI top counterpart) into +0x07, bits 0..2, and sets "
     "the 0x80 override bit when the value differs from the profile's all-key "
     "value, clearing it when they match — the same override discipline 0x4f "
     "uses for actuation. Both setters tail-call the same cache builder and "
     "feed the same raw-sample edge thresholds in the second context. No "
     "51 59 was sent in captures 03-03d: per-key UI availability and physical "
     "top/bottom interpretation remain unverified. The earlier per-key "
     "rapid-trigger label is withdrawn: that uses record +0x0a and 51 54.",
     "0x18003368 cmp #0x9f; 0x18003380 cmp #0xbc; 0x1800338c bl 0x1800f948; "
     "0x1800f9a8 bic #0x80; 0x1800f9b0 strb rec+0x06; 0x1800fa26 strb rec+0x07",
     "keymap records +0x06 and +0x07, bits 0..2 plus the 0x80 override"),
    (0x90, "static-handler-proven", W,
     "the firmware names it SC_S_A. Gated on bit 1 of the byte at 0x1801e6b7 — "
     "if clear the handler does nothing but reply — it passes request byte 4 to "
     "0x1800c184 and request byte 5 to 0x1800c1a0, then replies 51 90 with a "
     "60-byte payload and logs both bytes. The two callees are NOT traced, so "
     "what SC_S_A sets is NOT established.",
     "0x1800322a ldr -> 0x1801e6b9-2; 0x18003230 lsls #0x1e; 0x18003236 bl "
     "0x1800c184; 0x1800323c bl 0x1800c1a0; 0x1800325c adr 'SC_S_A'",
     "unestablished (two untraced setters)"),
)

QUERIES = (
    (0x00, "wire-proven", Q,
     "DEVICE HEADER READ. Requires bytes 2-3 to be zero, then copies EIGHT "
     "BYTES from the device header at 0x1801e6d0 into the reply payload. Reply "
     "byte 6 is the CURRENT PROFILE, with an internal 0 reported as 6. The "
     "capture's reply 59 00 01 00 06 00 03 00 therefore reads: firmware 1.59 in "
     "the first two bytes and PROFILE 3 in byte 6 — which independently agrees "
     "with notes/ac-profile3-decoded.json being profile 3.",
     "0x1800209a; 0x180020a2 ldrd from 0x1801e6d0; 0x180020a6 strd into the "
     "payload; 0x180020ae movs #6", None),
    (0x03, "wire-proven", Q,
     "echo only, one payload byte, unchanged from the request.",
     "0x180020be; movs r1,#3; length r6 = 1", None),
    (0x05, "static-handler-proven", Q,
     "returns one byte from 0x1801ee90+0xc and one constant 0xff. NEVER SENT by "
     "Armoury Crate in the capture.",
     "0x180020ca ldr [r0,#0xc]; 0x180020ce strb into the payload", None),
    (0x07, "wire-proven", Q,
     "returns the constant 1 in payload byte 0. The handler stores r6, which "
     "the dispatcher sets to 1 at entry and never reassigns on this path.",
     "0x180020ea strb r6,[r4,#4]; 0x18001fd6 movs r6,#1", None),
    (0x08, "wire-proven", Q,
     "returns 1 or 0 according to whether bits 0x30 of the byte at 0x1801e6b7 "
     "are set — a state flag, not a capability constant.",
     "0x180020f6; 0x180020fc tst #0x30; 0x18002104 strb into the payload",
     None),
    (0x12, "wire-proven", Q,
     "calls 0x1800ea36 with a pointer to payload byte 0. On the branch the "
     "capture took it replies 12 12 with 01 01; the other branch replies with "
     "SUBCOMMAND 0x13, so this query has two reply shapes.",
     "0x180021b4; bl 0x1800ea36; 0x180021d0 movs r1,#0x13", None),
    (0x13, "static-handler-proven", Q,
     "the SAME handler body as 12 12, entered two instructions earlier so that "
     "r2 is 1 instead of 0: both call 0x1800ea36 with a pointer to reply byte 0 "
     "and that mode flag, and both reply with subcommand 0x13 on the success "
     "path. So 12 12 and 12 13 are one query with two modes, and the 12 12 "
     "reply the capture observed is its FAILURE branch at 0x18003ff8.",
     "0x180021b4 movs r2,#1 for 12 13; 0x180021ba bl 0x1800ea36; 0x180021d0 "
     "movs r1,#0x13", None),
    (0x14, "wire-proven", Q,
     "MULTIPLEXED. Request byte 2 selects: 0 compares the global block's +0x18 "
     "marker against bytes 4-5; 1 takes a third path; 2 returns the ASCII model "
     "string 024080600167, which is the form the capture used.",
     "0x180021d4 cbz/cmp on byte 2; 0x180021e4 ldrh global+0x18", None),
    (0x15, "static-handler-proven", Q,
     "GET POLLING RATE. Reads profile block +0x4f8, masks 0xf, returns the "
     "index in reply byte 4. Recovered in log 126; Armoury Crate never sent it, "
     "so no reply was observed.",
     "0x18002254; 0x18002258 ldrb profile+0x4f8; 0x1800225c and #0xf", None),
    (0x16, "wire-proven", Q,
     "returns 1 if the device header's byte 7 equals 0xb5, else 0. The capture "
     "saw 0, so that byte was not 0xb5.",
     "0x1800226c ldrb [r7,#7]; 0x1800226e cmp #0xb5", None),
)

# HAL names without exact symbol attribution; behavioural candidate carriers
# below do not prove which named HAL method the application called.
HAL_UNMATCHED = (
    "SetRapidTrigger_AllKey", "SetRapidTrigger_PreKey",
    "SetDeadZone_AllKey", "SetDeadZone_PreKey",
    "SetSpeedTap", "SwitchSpeedTap", "ResetSpeedTap",
    "ChangeKey_DKS", "ChangeKey_ModTap", "ChangeKey_Toggle",
    "WriteMacroFlash", "WriteMacroFlash_SupportFn",
    "SetLeverMode", "SetLeverSwitch", "SetLeverChange", "GetLeverMode",
    "SetKeyLog", "GetKeyStats", "Reset", "IsDefaultProfile",
)

# Step 4: a disposition for every HAL name protocol.md lists without an opcode.
# A name with no plausible carrier is a finding, not a failure.
HAL_DISPOSITION = (
    ("SetActuation_AllKey", "51 50",
     "global bits 9..15 written from request byte 4 at 0x18002bee, with log "
     "125's clamp at 0x18006d3c", "strongly-inferred"),
    ("SetActuation_PreKey", "51 4f",
     "per-key record +0x08 bits 0..6 at 0x18002ba6 with the bit-15 override "
     "resolved against global bits 9..15 at 0x18002bba", "strongly-inferred"),
    ("SetRapidTrigger_AllKey", "51 54 (one frame per assigned key)",
     "log 136: AC sends press/release changes as 51 54 for each assigned key; "
     "there is no observed single global command. The former 51 58 match was "
     "dead zone. Exact HAL symbol attribution is unproven",
     "strongly-inferred"),
    ("SetRapidTrigger_PreKey", "51 54",
     "log 136: byte 2 selects combined/press/release, byte 4 the key, byte 6 "
     "the sensitivity in 0.1 mm and byte 8 on/off. Log 138 traces all fields "
     "to record +0x0a and its rapid-trigger delta consumer",
     "strongly-inferred"),
    ("Reset_Actuation_RapidTrigger", "51 52",
     "logs 136-137: byte 2 = 03 resets actuation and rapid trigger; byte 2 = "
     "01 resets actuation only. The selector table is at 0x18002c24",
     "strongly-inferred"),
    ("Reset", "51 52", "AC's Trigger-page Reset; a general factory reset is "
     "not established (logs 136-137)", "hypothesis"),
    ("SetProfile", "51 00",
     "posts storage opcode 2 with the profile at REQSTRUCT+0x85 at 0x18002530; "
     "the state machine stores it to the device header at 0x180011bc",
     "strongly-inferred"),
    ("IsDefaultProfile", None,
     "no located handler reads a default-profile flag. 12 16 returns a device "
     "header byte compared against 0xb5 and 12 08 a bit of 0x1801e6b7; neither "
     "is shown to mean this", "no plausible carrier found"),
    ("SetDeadZone_AllKey", "51 58",
     "log 136: independent top/bottom 0.2 -> 0.3 mm changes alter request "
     "bytes 4/5 respectively. Log 138 resolves the static argument order: "
     "top bits 17..19 at 0x1800fa60, bottom bits 20..22 at 0x1800f9d0, "
     "previously mislabelled rapid trigger",
     "strongly-inferred"),
    ("SetDeadZone_PreKey", "51 59",
     "log 138: per-key overrides feed the same cache arrays and raw-sample "
     "threshold tables as 51 58. No capture exercises it; per-key UI "
     "availability, physical effect and exact HAL symbol attribution remain unverified",
     "strongly-inferred"),
    ("SetSpeedTap", "51 55",
     "log 136: request bytes 4-5/6-7 carry A/D, matching the profile's speedTap "
     "binding. The static handler translates the pair and validates HID "
     "usages at 0x1800311c/0x18003122", "strongly-inferred"),
    ("SwitchSpeedTap", "51 55 (byte 8)",
     "log 136 captures byte 8 changing 00 -> 01 with the same A/D pair; "
     "static analysis identifies a write gate. An owner-driven on/off test "
     "and the exact HAL attribution are still missing",
     "hypothesis"),
    ("ResetSpeedTap", None, "no located handler clears such a pair",
     "no plausible carrier found"),
    ("ChangeKey_DKS", "51 23",
     "=KC_S,T_A writes record +0x04 = 1 plus TWO extra bytes at +0x0e and +0x0f "
     "alongside a translated target — more per-key state than a plain remap "
     "needs. DKS is the multi-code-per-key feature, so the shape fits; the "
     "field roles are not established", "hypothesis"),
    ("ChangeKey_ModTap", "51 23 or 51 24",
     "both write distinct values of the record +0x04 mode byte (1 and 2) that "
     "0x21 clears, so the mode byte is at least four-valued and mod-tap is one "
     "of the values it could select; which is not established", "hypothesis"),
    ("ChangeKey_Toggle", "51 24",
     "record +0x04 = 2, a second mode value; same caveat", "hypothesis"),
    ("ChangeKey_Normal", "51 21",
     "already wire-proven as the remap that clears the mode byte",
     "strongly-inferred"),
    ("WriteMacroFlash", "54",
     "logs 135-137: assigned macros are uploaded with opcode 54; record "
     "keys/actions/delays agree with preserved GMAC files. The full static "
     "handler remains untraced", "strongly-inferred"),
    ("WriteMacroFlash_SupportFn", None, "Fn-layer macro assignment was not "
     "captured; the support variant's carrier is unestablished",
     "no plausible carrier found"),
    ("SetLeverMode", None,
     "no located handler writes a lever field; log 125 matched the AC decode's "
     "lever.functionStatusList only structurally",
     "no plausible carrier found"),
    ("SetLeverSwitch", None, "same", "no plausible carrier found"),
    ("SetLeverChange", None, "same", "no plausible carrier found"),
    ("GetLeverMode", None,
     "none of the ten located queries returns a lever field",
     "no plausible carrier found"),
    ("SetKeyLog", None,
     "the dispatcher carries the strings KL_D_A and KL_E_A at 0x1800232e and "
     "0x1800234c — disable and enable, on the 0x12 opcode's side of the body — "
     "but this step did not attribute them to a located subcommand, so no "
     "carrier is named", "no plausible carrier found"),
    ("GetKeyStats", None,
     "none of the ten located queries returns a statistics payload",
     "no plausible carrier found"),
)

NEVER_SEND = (
    ("50 55", "the persistent commit (log 126)"),
    ("51 xx, every subcommand in this table", "the configuration write family; "
     "twenty-four subcommands, most with unestablished semantics"),
    ("52 / 41 / 43 / 53 / 54 / 71 / 73 / b0 / c0 / fa / fd",
     "write-capable top-level opcodes; 54 is macro upload on the wire, "
     "the other listed opcodes remain unestablished"),
    ("any erase / program / unlock / reset / SPI framing",
     "the bootloader protocol of logs 81/82/87/88"),
)


# ------------------------------------------------------------- the findings

# Independent wire evidence from the Windows feature sessions. Keep these
# observations separate from instruction-derived confidence: a captured UI
# effect does not prove that every field of its handler has been traced.
FEATURE_CAPTURES = (
    ("03-features", "bb4bf7cc7df317a69c858dc09481d4bf10fc5691dacf9c08b5fe05b9606cce06",
     "135-feature-capture-validation.txt"),
    ("03b-features", "522299eb340e576ad547c79c0f28815c2280044c1d23d16abd27d626c2dc15e8",
     "135-feature-capture-validation.txt"),
    ("03c-deep", "d9aa029d5531df00fba587e455b449c6ef704cc3812fadf17b9121c95fa2e029",
     "136-deep-capture-key-ids-and-corrections.txt"),
    ("03d-finish", "6c2abea3f6b60b5c7b1e1099333f32f09514f4d66e08e8aad482dfca83dace6e",
     "137-finish-capture-per-key-actuation-and-lever.txt"),
)
FEATURE_WIRE = {
    "25 00": ("Read current-profile rapid-trigger enable; response byte 4 is "
              "global word bit 5 (nine matched readbacks across 03-03d)",
              "log 139 traces 0x180022ce..0x180022e4 to the same bit that "
              "the physical GPIO poll writes and 03 76 reports", "135-137, 139"),
    "51 00": ("Profile switch; byte 4 is the requested profile.",
              "agrees", "135"),
    "51 50": ("Global actuation; byte 4 is mm x 10.", "agrees", "135"),
    "51 4f": ("Per-key actuation; byte 4 is the key, byte 6 is mm x 10. "
              "Two key writes can share one 50 55 commit.", "agrees", "137"),
    "51 21": ("Base-layer remap; byte 2 source, byte 3 = 00, bytes 4-5 target, "
              "00ff restores default, byte 6 current actuation. Fn-layer 9f "
              "remaps have historical evidence, not a new 03-03d observation.",
              "agrees for captured base-layer writes", "135-136"),
    "51 52": ("Trigger-page Reset; byte 2 = 01 actuation, 03 actuation and "
              "rapid trigger. Selectors 00/02/04 and the third reset field "
              "were not established.", "static selector agrees; stores untraced", "136-137"),
    "51 54": ("Per-key rapid trigger; byte 2 = 00 combined / 01 press / 02 "
              "release, byte 4 key, byte 6 mm x 10, byte 8 on/off. All captured "
              "writes use layer 00 and mode-control byte 7 = 00.",
              "reconciled with full handler and consumer in log 138; uncaptured modes remain open",
              "136, 138"),
    "51 58": ("Global dead zone; byte 4 top, byte 5 bottom, mm x 10. "
              "This corrects the earlier all-key rapid-trigger label.",
              "log 138 resolves argument order: top bits 17..19, bottom bits 20..22",
              "136, 138"),
    "51 55": ("Speed Tap pair A/D at bytes 4-5/6-7, matching the AC profile; "
              "byte 8 changed 00 -> 01. AC re-sent this without an owner "
              "Speed Tap action.", "pair agrees; switch semantics need a UI test", "136"),
    "51 56": ("Observed once before the Speed Tap pair. A Speed Tap-table "
              "reset is a hypothesis; a general settings reset was not observed.",
              "ordering only; user-visible scope remains open", "136"),
    "51 2c": ("Lighting; byte 5 brightness %, static bytes 9-11 RGB, "
              "animated byte 4 speed. Other animated fields remain open.",
              "partial", "135-136"),
    "51 2d": ("Lighting effect; byte 4 = 00 static / 01 breathing.",
              "partial", "135-136"),
    "54": ("Macro upload on assignment; byte 2 counts this frame's records "
           "including ff, byte 3 marks continuation, byte 4 assigned key; "
           "records start at byte 9 and encode key/action/u16 delay in ms.",
           "wire layout decoded; static handler untraced", "135-137"),
}


@functools.lru_cache(maxsize=None)
def feature_capture_evidence():
    rows = []
    for name, expected, log in FEATURE_CAPTURES:
        path = ROOT / "captures" / f"{name}.pcap"
        if not path.is_file() or not (ROOT / "logs" / log).is_file():
            raise CommandError(f"missing feature evidence for {name}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise CommandError(f"feature capture hash mismatch: {path.name}")
        rows.append({"capture": f"captures/{path.name}", "sha256": expected,
                     "log": f"logs/{log}", "hash_verified": True})
    return rows


def feature_wire_observations():
    return [{"command": command, "confidence": "wire-observed",
             "meaning": meaning, "static_agreement": agreement, "logs": logs}
            for command, (meaning, agreement, logs) in FEATURE_WIRE.items()]


@functools.lru_cache(maxsize=None)
def opcode_table():
    rows = []
    for addr, op, enc, target in TOP_LEVEL_SITES:
        rows.append({"opcode": f"{op:#04x}", "compare_at": f"{addr:#x}",
                     "handler": f"{target:#x}",
                     "decoded": op in (0x12, 0x51)})
    return tuple(rows)


@functools.lru_cache(maxsize=None)
def subcommand_table():
    tbb = decode_tbb(*SUB_TBB)
    located = {op: t for _, op, _, t in SUB_SITES}
    located.update(tbb)
    curated = {op: row for row in SUBCOMMANDS for op in (row[0],)}
    rows = []
    for op in sorted(located):
        c = curated.get(op)
        if c is None:
            raise CommandError(f"subcommand {op:#04x} is located at "
                               f"{located[op]:#x} but has no curated row; "
                               f"refusing to emit an incomplete table")
        _, conf, kind, meaning, evidence, storage = c
        observation = next((r for r in feature_wire_observations()
                            if r["command"] == f"51 {op:02x}"), None)
        rows.append({"subcommand": f"{op:#04x}", "handler": f"{located[op]:#x}",
                     "confidence": conf, "kind": kind, "meaning": meaning,
                     "evidence": evidence, "storage": storage,
                     "wire_observation": observation,
                     "writes_device_state": kind == W,
                     "owner_approval_required": kind == W})
    return tuple(rows)


@functools.lru_cache(maxsize=None)
def query_table():
    tbh = decode_tbh(*QUERY_TBH)
    located = {op: t for _, op, _, t in QUERY_SITES}
    # The table branch: entries that all land on the same address are the
    # "unknown subcommand" default and are not commands.
    counts = Counter(tbh.values())
    default = max(counts, key=counts.get)
    for op, t in tbh.items():
        if t != default:
            located[op] = t
    curated = {row[0]: row for row in QUERIES}
    rows = []
    for op in sorted(located):
        c = curated.get(op)
        if c is None:
            raise CommandError(f"query 12 {op:#04x} at {located[op]:#x} has no "
                               f"curated row")
        _, conf, kind, meaning, evidence, _ = c
        rows.append({"subcommand": f"{op:#04x}", "handler": f"{located[op]:#x}",
                     "confidence": conf, "kind": kind, "meaning": meaning,
                     "evidence": evidence, "writes_device_state": False,
                     "owner_approval_required": False})
    return tuple(rows)


@functools.lru_cache(maxsize=None)
def profile_switch():
    """Who writes the selection byte, and how a USB command reaches it."""
    rows = accesses(PROFILE_SELECT)
    writers = [r for r in rows if r["dir"] == "write"]
    readers = [r for r in rows if r["dir"] == "read"]
    disp_writes = [r for r in writers if r["func"] == DISPATCHER]
    return {
        "byte": f"{PROFILE_SELECT:#x}",
        "writers": [{"instr": f"{r['instr']:#x}", "func": f"{r['func']:#x}"}
                    for r in sorted(writers, key=lambda r: r["instr"])],
        "reader_count": len(readers),
        "dispatcher_writes": len(disp_writes),
        "answer": "THERE IS A USB COMMAND, AND IT IS INDIRECT. The selection "
                  "byte has exactly two writers, both in the storage state "
                  "machine FUN_18000d56; the vendor-HID dispatcher NEVER writes "
                  "it, in any of its 13 accesses. `51 00` posts opcode 2 and "
                  "the requested profile into the storage request struct at "
                  "+0x84/+0x85, and FUN_18000d56 reads that byte at 0x180011b8 "
                  "and stores it to the selection byte at 0x180011bc. So the "
                  "answer is neither 'a command writes it' nor 'Fn-key only' — "
                  "it is a queued request consumed by the state machine.",
        "sequence": [
            "host sends 51 00 xx xx <profile>, profile accepted 0..5 with 6 "
            "folded to 0",
            "handler 0x18002514 stores 2 at REQSTRUCT+0x84 and the profile at "
            "+0x85, and only when +0x84 is not already 2",
            "FUN_18000d56 consumes the request: 0x180011b8 reads +0x85, "
            "0x180011bc writes device header +6",
            "the same state machine holds the profile-apply writes of the "
            "polling-rate multiplier (0x1800117c, 0x18001548, 0x180018f8, "
            "0x18001ece — log 127), so a switch re-derives the cached rate",
        ],
        "not_established": "which branch of FUN_18000d56 a switch takes, and "
                           "therefore whether one switch invocation reaches "
                           "0x1800153a specifically. Only that both the write "
                           "and the reload live in that one function.",
        "wire_readback": "12 00 reply byte 6 returns the same byte, with an "
                         "internal 0 reported as 6.",
        "completion_reply": "51 00 is emitted by the storage state machine, "
                            "not as an immediate dispatcher echo. At "
                            "0x18001552 it reads current device-header +6, "
                            "normalises 0 to 6, and sends one payload byte at "
                            "0x18001566 when request flag bit 1 is set. "
                            "A request arriving while opcode 2 is already "
                            "pending does not replace the pending profile "
                            "(0x18002528..0x18002534). This supports state "
                            "reporting/asynchronous explanations for capture "
                            "03 frames 106237/106277, but does not prove which "
                            "runtime path caused their 01/02 disagreement.",
    }


def rapid_trigger_update(halfword, selector, value, mode_control, enabled):
    """Offline arithmetic model of 51 54 after the key/layer guards.

    Scalar inputs only; constructs no USB report. Preserve the handler's
    ordering, truncation and partial mutation on an invalid LE16 selector.
    """
    for name, number, limit in (("halfword", halfword, 0xffff),
                                ("selector", selector, 0xffff),
                                ("value", value, 0xff),
                                ("mode_control", mode_control, 0xff),
                                ("enabled", enabled, 0xff)):
        if not isinstance(number, int) or not 0 <= number <= limit:
            raise CommandError(f"{name} is outside its instruction operand width")
    mode = ((mode_control + 1) & 3) if enabled else 0
    halfword = (halfword & 0x3fff) | (mode << 14)
    if selector in (0, 2):
        halfword = (halfword & ~0x7f) | (value & 0x7f)
    if selector in (0, 1):
        halfword = (halfword & ~0x3f80) | ((value & 0x7f) << 7)
    return {"halfword": halfword, "selector_accepted": selector in (0, 1, 2),
            "layer_marked_dirty": selector in (0, 1, 2)}


def dead_zone_override(previous, value, global_value):
    """Scalar model of one +6/+7 override byte in helper 0x1800f948."""
    if not all(isinstance(x, int) and 0 <= x <= 255
               for x in (previous, value, global_value)):
        raise CommandError("dead-zone model expects byte operands")
    value = value if 1 <= value <= 6 else 2
    return (previous & 0x78) | value | (0x80 if value != global_value else 0)


def rapid_trigger_lever_poll(word, count, gpio, resampled_gpio, threshold=9):
    """Scalar offline model of FUN_180068aa; no report is constructed.

    The caller's mode guard and profile selection have already been applied.
    Both GPIO reads are binary. The second read is used only at acceptance.
    """
    for name, value in (("word", word), ("count", count), ("threshold", threshold)):
        if not isinstance(value, int) or not 0 <= value <= 0xffffffff:
            raise CommandError(f"{name} is outside its instruction operand width")
    if gpio not in (0, 1) or resampled_gpio not in (0, 1):
        raise CommandError("GPIO samples must be binary")
    state = None
    if (gpio ^ 1) == ((word >> 5) & 1):
        count = 0
    else:
        count = (count + 1) & 0xffffffff
        if count > threshold:
            count = 0
            word = (word & ~0x20) | ((resampled_gpio ^ 1) << 5)
            state = (word >> 5) & 1
    return {"word": word, "count": count, "report_state": state,
            "runtime_refresh": state is not None}


def _thumb_bl_target(address, slice_):
    """Decode only the immediate BL form used by the two cited switch calls."""
    first, last = (int(x, 16) for x in halfwords(address, 2, slice_).split())
    if first & 0xf800 != 0xf000 or last & 0xd000 != 0xd000:
        raise CommandError(f"{address:#x} is not a Thumb immediate BL")
    sign = (first >> 10) & 1
    i1, i2 = 1 ^ ((last >> 13) & 1) ^ sign, 1 ^ ((last >> 11) & 1) ^ sign
    displacement = ((sign << 24) | (i1 << 23) | (i2 << 22)
                    | ((first & 0x3ff) << 12) | ((last & 0x7ff) << 1))
    if sign:
        displacement -= 1 << 25
    return address + 4 + displacement


@functools.lru_cache(maxsize=None)
def rapid_trigger_lever():
    """Log 139: physical GPIO -> current-profile bit 5 -> 03 76 report."""
    import map_second_context as second
    sources = second.sources()
    entry = image(ENTRY[0])
    left = image(APP[0])[0x68aa:0x6914]
    right = image(VENDOR_APP[0])[0x687e:0x68e8]
    differences = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
    entry_sites = {0x43a: "2808", 0x442: "f000 f868", 0x536: "2009",
                   0x538: "f003 fdb1", 0x409e: "f646 0cab f6c1 0c00 4760",
                   0x5b4: "e810 1801"}
    return {
        "confidence": "static path proven, physical ON/OFF labels corroborated by log 137",
        "installed": {"poll": "0x180068aa", "gpio_reader": "0x18010a18",
                      "global_words": "0x18024f0c", "selection": "0x1801e6d6",
                      "counter": "0x1801e778", "runtime_refresh": "0x180089a8"},
        "vendor": {"poll": "0x1800687e", "gpio_reader": "0x180109ec",
                   "global_words": "0x18024ee0", "selection": "0x1801e6aa",
                   "counter": "0x1801e74c", "runtime_refresh": "0x1800897c"},
        "gpio": {"identifier": 0x47, "group": 4, "bit": 7,
                 "polarity": "sample zero sets enable bit 5; sample one clears it",
                 "basis": "FUN_18010850 splits identifier into high-nibble group "
                          "and low-nibble bit; FUN_18010a18 returns a binary MMIO read. "
                          "The PCB pad and port letter are not identified"},
        "debounce": {"threshold": 9, "accepted_mismatch_polls": 10,
                     "service_tick_divider": 8, "absolute_ms": None,
                     "caller": "entry FUN_00000516, 0x536..0x538 -> veneer "
                               "0x409e -> app 0x180068aa, only if *(0x1801e810)==1",
                     "rule": "equal inverted GPIO/bit resets count; mismatch "
                             "increments uint32 count; accept only when count >9, "
                             "reset count, resample GPIO, replace bit 5 preserving "
                             "other bits, queue state and refresh runtime settings. "
                             "A resample that bounced back can report the old state",
                     "counter_scope": "one shared counter; profile reload does not "
                                      "explicitly reset it in the inspected paths"},
        "report": {"endpoint": "0x8c", "size": 21, "prefix": "03 76 00 00",
                   "state_byte": 4, "on": 1, "off": 0,
                   "queue": "FUN_18004498(0x76,0,0,bit5) queues a 21-byte record; "
                            "FUN_1800417e adds report ID 3 and sends via FUN_18004164(2,...)",
                   "delivery": "queued input status, not a request/reply acknowledgement; "
                               "delivery depends on the queue and sender's runtime gates"},
        "readback": "25 00 reads current-profile global bit 5 into reply byte 4 "
                    "at 0x180022ce..0x180022e4. Nine matched readbacks in captures "
                    "03-03d corroborate binary states (five on, four off); "
                    "this analysis sent no live query",
        "lifecycle": "global storage read FUN_1800e64e can restore the block; "
                     "whole-word single/all-profile resets at 0x18001d8e/0x18001e24 "
                     "start with bit 5 clear. A selection change selects another "
                     "word, then the periodic physical poll reconciles it with GPIO. "
                     "This explains how a report can follow a profile switch without "
                     "a new lever motion; it is not an unconditional resend rule",
        "persistence": "the poll stores RAM and calls FUN_180089a8 (runtime refresh), "
                       "without a direct storage-dirty or persist call. Other whole-block "
                       "save paths can include this bit; persistence solely from moving "
                       "the lever is not established",
        "writer_scope": "GPIO mutation, full-block restore and factory reset paths "
                        "inspected; not a proof against every indirect writer or memory fault",
        "entry_instruction_checks": [{"address": hex(a),
                                      "ok": halfwords(a, len(enc.split()), ENTRY) == enc}
                                     for a, enc in entry_sites.items()],
        "entry_source_roundtrip": entry == sources["installed"][0x1000:0x1000 + len(entry)],
        "release_comparison": {"length": 106, "differing_offsets": differences,
                               "only_report_call_relocated": len(left) == len(right) == 106
                                   and differences == [0x56]
                                   and _thumb_bl_target(0x180068fe, APP) == 0x18004498
                                   and _thumb_bl_target(0x180068d2, VENDOR_APP) == 0x18004498},
        "unresolved": ["absolute debounce duration; IRQ38 period remains unresolved",
                       "PCB pin mapping and physical timing/scan-phase measurement",
                       "lever-only persistence across power loss; no direct save in poll",
                       "uncaptured per-key modes and Fn-layer physical behavior"],
    }


def trigger_configuration():
    """Log 138: exact stores, consumers, release comparison and limits."""
    # Import lazily to retain the command map's original offline dependencies.
    import map_second_context as second
    sources = second.sources()  # verify original full-source hashes
    slices = second.slices()
    ram = slices["installed"]
    def span(data, base, lo, hi):
        if not base <= lo < hi <= base + len(data):
            raise CommandError(f"trigger evidence span {lo:#x}..{hi:#x} is outside its image")
        return data[lo - base:hi - base]
    app, vendor = image(APP[0]), image(VENDOR_APP[0])
    comparisons = []
    for label, installed_lo, vendor_lo, length in (
            ("51 54 full handler and shared reply tail", 0x18002fe4, 0x18002fe4, 0xe4),
            ("dead-zone setter body, first range", 0x1800f948, 0x1800f91c, 0xe4),
            ("dead-zone setter body, second range", 0x1800fa5c, 0x1800fa30, 0x1a),
            ("dead-zone cache builder", 0x1800f7fe, 0x1800f7d2, 0x14a)):
        left = span(app, APP[1], installed_lo, installed_lo + length)
        right = span(vendor, VENDOR_APP[1], vendor_lo, vendor_lo + length)
        comparisons.append({"scope": label, "installed": hex(installed_lo),
                            "vendor": hex(vendor_lo), "length": length,
                            "identical": left == right,
                            "installed_sha256": hashlib.sha256(left).hexdigest()})
    secondary_sites = {
        0x1803a7b2: "93 f8 b4 c5",  # shared +5b4 index
        0x1803a7b8: "33 f8 1c 30",  # indexed halfword threshold
        0x1803a804: "91 f8 4a c6",  # shared +64a index
        0x1803a808: "3b f8 1c c0",  # indexed halfword threshold
    }
    secondary_checks = [{"address": hex(addr),
                         "ok": span(ram, second.RUNTIME_BASE, addr,
                                     addr + len(bytes.fromhex(enc))) == bytes.fromhex(enc)}
                        for addr, enc in secondary_sites.items()]
    roundtrips = [app == sources["installed"][0x11000:0x11000 + len(app)],
                  vendor == sources["vendor"][0x21000:0x21000 + len(vendor)]]
    tables = []
    for name, address in (("shared +5b4", 0x1803c386), ("shared +64a", 0x1803c392)):
        values = list(struct.unpack_from("<6H", ram, address - second.RUNTIME_BASE))
        tables.append({"array": name, "table": hex(address), "values": values})
    return {
        "source_hashes_verified": True, "application_slices_roundtrip": all(roundtrips),
        "release_comparisons": comparisons,
        "secondary_code_identical": slices["installed"][:-4] == slices["vendor"][:-4],
        "secondary_instruction_checks": secondary_checks,
        "record": "0x180202d8 + layer*0xd84 + translated_key*0x20",
        "translation": "0x1801c3a8 + KBID*0x86 + wire_key (both installed paths)",
        "rapid_trigger": {
            "entry_chain": ["0x180026e4", "0x18002ee4", "0x18002fe4"],
            "offset": 10,
            "fields": [{"name": "release", "shift": 0, "width": 7},
                       {"name": "press", "shift": 7, "width": 7},
                       {"name": "mode", "shift": 14, "width": 2}],
            "selectors": {"0": "both", "1": "press", "2": "release"},
            "handler_bounds": "layer 00/9f and wire key <= bc; no sensitivity "
                              "range clamp; low seven bits stored",
            "mode": "enable byte 8 == 0 -> 0; otherwise (byte 7 + 1) & 3; "
                    "captured byte 7 is always 0, hence active mode 1",
            "ordering": "mode is stored before selector validation; disabled "
                        "writes still update sensitivities; invalid selectors "
                        "can mutate mode without setting the layer dirty flag",
            "consumer": "0x180055ee..0x18005762 in installed FUN_18004a7e: "
                        "requires record type +4 == 0, alternate-path byte "
                        "+0xc == 0, nonzero mode and current-profile global "
                        "bit 5. Press/release sensitivities are each multiplied "
                        "by five in the 0..200 travel-byte scale. Directional "
                        "delta comparisons are strict. When travel <40, each "
                        "relevant delta threshold is floored at 8. Mode 1 "
                        "uses actuation-2 (floored at 0) for the initial release "
                        "threshold; other nonzero modes keep the earlier "
                        "actuation-derived lower threshold. The active/released "
                        "states maintain directional extrema.",
            "vendor_consumer": "FUN_18004a7e also contains the consumer in "
                               "vendor 1.00.58; addresses inside its body "
                               "differ. The full scan function differs between "
                               "releases; no blanket 0x2c shift is assumed.",
        },
        "dead_zone": {
            "global_51_58": [{"ui_label": "top", "request_byte": 4, "shift": 17},
                             {"ui_label": "bottom", "request_byte": 5, "shift": 20}],
            "per_key_51_59": [{"ui_counterpart": "top", "request_byte": 6, "record_offset": 7},
                              {"ui_counterpart": "bottom", "request_byte": 7, "record_offset": 6}],
            "encoding": "wire 1..5 accepted; 0 maps to internal 6; wire 6 "
                        "and greater rejected. Helper accepts internal 1..6 "
                        "and defaults other values to 2",
            "override": "bits 0..2 value, bit 7 override; other bits preserved. "
                        "Clear override if equal to current-profile global value",
            "cache": "0x1800f948 tail-calls 0x1800f7fe: +6/bits20..22 -> "
                     "shared+0x5b4, +7/bits17..19 -> shared+0x64a, value minus "
                     "one. Global refresh resolves inheritance for both layers; "
                     "per-key refresh targets the selected record",
            "consumer": "second-context FUN_1803a6c4: +5b4 chooses the "
                        "reference-minus-threshold branch that writes travel 0; "
                        "+64a chooses the other-reference-plus-threshold "
                        "branch that saturates the curve index to 0x4ff "
                        "(travel 200). Tables are raw-sample units, not mm",
            "tables": tables,
            "confidence": "static command/consumer relationship proven; "
                          "UI labels for 51 58 from capture log 136; 51 59 "
                          "UI and physical behavior unobserved",
        },
        "unresolved": [
            "51 59 UI availability and physical per-key effect; no captured use",
            "UI top/bottom labels map to the opposite-looking numeric travel "
            "edges (+64a/200 versus +5b4/0); physical interpretation needs a "
            "focused action or further UI/curve analysis, not relabelling on intuition",
            "51 54 mode-control byte 7 nonzero and Fn-layer behavior uncaptured",
            "Global bit 5's physical-lever path is traced in log 139; absolute "
            "timing and lever-only persistence remain unresolved",
            "Profile 01/02 mismatch: state-snapshot reply is proven, exact runtime cause is not",
        ],
    }


@functools.lru_cache(maxsize=None)
def macro_block():
    rows = accesses(0x180225FC, 0x18022C60)
    writers = sorted({r["func"] for r in rows if r["dir"] == "write"})
    readers = sorted({r["func"] for r in rows if r["dir"] == "read"})
    disp = [r for r in rows if r["func"] == DISPATCHER and r["dir"] == "write"]
    return {
        "base": "0x180225fc", "size": "0x664",
        "resolved_accesses": len(rows),
        "writer_functions": [f"{f:#x}" for f in writers],
        "reader_functions": [f"{f:#x}" for f in readers],
        "has_usb_writer": bool(disp),
        "usb_write_sites": [f"{r['instr']:#x}" for r in disp],
        "structure": "the dispatcher's write at 0x180035dc stores one byte at "
                     "+0 and one at +7, then clears 0x190 = 400 bytes from +8. "
                     "So the block opens with an eight-byte header and a "
                     "400-byte body. The code immediately above filters HID "
                     "usages 0x39, 0x47, 0x53, 0xe2 and 0xe8 — Caps Lock, "
                     "Scroll Lock, Num Lock, Left Alt and log 120's vendor "
                     "code — down a different path, which is a recording "
                     "filter rather than a playback one.",
        "entry_size": "NOT ESTABLISHED. 400 bytes is the cleared extent, not a "
                      "proven record count or stride.",
        "verdict": "MACROS ARE NOT DEVICE-ONLY. A USB path writes this block. "
                   "Which 0x51 subcommand reaches 0x180035dc is not "
                   "established — the site lies in the dispatcher body past "
                   "0x18003310, and this step did not resolve the branch.",
    }


@functools.lru_cache(maxsize=None)
def block_d():
    rows = accesses(0x1801FEF8, 0x180202D8)
    writers = sorted({r["func"] for r in rows if r["dir"] == "write"})
    readers = sorted({r["func"] for r in rows if r["dir"] == "read"})
    return {
        "base": "0x1801fef8", "size": "0x3e0",
        "flash_home": "0x340000 + profile*0x1000 (log 125)",
        "resolved_accesses": len(rows),
        "writer_functions": [f"{f:#x}" for f in writers],
        "reader_functions": [f"{f:#x}" for f in readers],
        "has_usb_writer": DISPATCHER in writers,
        "runtime_reader": "FUN_180057fe reads +0x4 and +0x5 — and FUN_180057fe "
                          "is veneer 0x406c, one of the four calls in the "
                          "rate-gated tick block log 127 mapped. So block D is "
                          "read on the report path, not just at load time.",
        "verdict": "BLOCK D IS A PER-KEY ENTRY ARRAY, and it still has no USB "
                   "writer except the factory-default command 51 56. Its only "
                   "direct writer is the storage state machine FUN_18000d56 at "
                   "0x18001be0.",
        "layout": [
            {"offset": "+0x000", "size": 2, "type": "u16",
             "role": "the block's own additive checksum, the shape log 125 "
                     "showed every stored block carrying in its first "
                     "halfword; read nine times and written once, all inside "
                     "FUN_18000d56",
             "confidence": "strongly-inferred"},
            {"offset": "+0x004", "size": "0x1ee", "type": "247 x 2-byte entry",
             "role": "entry i is {+0: a value byte, +1: a flags byte}, indexed "
                     "0..0xf6 by the reader's own loop bound. 247 is exactly "
                     "log 125's key-table entry count, and 4 + 247*2 = 0x1f2",
             "confidence": "observed"},
            {"offset": "+0x1f2", "size": "0x1ee", "type": "247 x 2-byte entry",
             "role": "the second table. 0x1f2 + 0x1ee = 0x3e0 EXACTLY, the "
                     "block's declared size, so the block closes on two "
                     "equal-sized per-key tables — the same two-table shape as "
                     "the profile block's key tables at +0xd4 and +0x2c2. Which "
                     "index selects which table is NOT established",
             "confidence": "strongly-inferred"},
        ],
        "arithmetic_closes": True,
        "reader_behaviour": "FUN_180057fe walks i = 0..0xf6. It tests bits 3..7 "
                            "of entry i's flags byte (lsrs #3), and when they "
                            "are non-zero it scans an existing byte list for "
                            "entry i's value byte, appending i and bumping a "
                            "count only if the value is not already present. So "
                            "the pass builds a DE-DUPLICATED list of the "
                            "currently active entries, once per divide-by-eight "
                            "tick.",
        "defaults": "NOT RECOVERED. The block is zero-initialised RAM in the "
                    "image, so no static default is readable; 51 56 restores it "
                    "through 0x180005c6 and 0x1800aadc, neither traced here.",
        "persistence_meaning": "log 125 gives it a flash home at 0x340000 + "
                               "profile*0x1000 — one 0x3e0 block per profile, "
                               "six profiles. Combined with the layout that "
                               "means a per-profile, per-key table of 247 "
                               "two-byte entries survives a power cycle and is "
                               "re-read into RAM on profile load, like the "
                               "keymap bank and the profile block.",
        "ac_profile_match": None,
        "ac_profile_match_note": "NO MATCH IS CLAIMED. Log 125's decode of "
                                 "notes/ac-profile3-decoded.json has no "
                                 "247-entry two-byte-per-key structure left "
                                 "unmatched, and matching on size alone is "
                                 "exactly the resemblance rule this project "
                                 "forbids.",
    }


@functools.lru_cache(maxsize=None)
def hold_timer():
    """Log 127's +0x22 site: what consumes the per-key timeout."""
    return {
        "threshold": "keymap bank + layer*0xd84 + key*0x20 + 0x22, one byte",
        "paired_value": "the halfword at the same record +0x20",
        "scaling": "threshold x 10 x (1 << rate index) tick-job invocations = "
                   "threshold x 10 ms, rate-invariant (log 127)",
        "on_expiry": "the halfword at +0x20 is APPENDED to a per-layer output "
                     "ring at 0x18024000 + layer*600, and the ring's index is "
                     "incremented",
        "evidence": "0x180054c4 ldrh r3,[r2,#0x20]; 0x180054d0 ldr -> "
                    "0x18024000; 0x180054da strh.w r3,[r12,r1,lsl #1]; "
                    "0x180054de adds r1,r1,#1",
        "behaviour": "a per-key PRESS-AND-HOLD timer that emits a stored 16-bit "
                     "code once the key has been held for the stored duration. "
                     "That is a dual-role key: one code on tap, another on "
                     "hold.",
        "behaviour_confidence": "strongly-inferred",
        "hal_match": None,
        "hal_candidates": ["ChangeKey_ModTap", "ChangeKey_Toggle",
                           "ChangeKey_DKS", "SetSpeedTap"],
        "hal_match_confidence": "hypothesis — the behaviour is a hold-to-emit "
                                "timer, which fits all four of those names. "
                                "Nothing here distinguishes them, so NO NAME IS "
                                "ASSIGNED.",
        "buffer": {
            "base": "0x18024000",
            "stride": 600,
            "stride_arithmetic": "k*15, then *5, then <<3 — the writer at "
                                 "0x180054c8..0x180054d2 and the consumer at "
                                 "0x18006084..0x18006094 compute it identically",
            "entry": "one halfword per slot; 600 bytes is 300 slots",
            "index": "a per-bank word counter, read and incremented in place by "
                     "the writer (0x180054d6 / 0x180054de / 0x180054e0)",
            "wrap": "NONE FOUND. The writer increments the counter with no "
                    "modulo and no bound test at the append site; the consumer "
                    "stops at 120 (cmp r1,#0x78). Whether anything resets the "
                    "counter each pass is NOT established, and no wrap "
                    "behaviour should be assumed.",
            "selector": "NOT the layer. Log 128 recorded 'a per-layer output "
                        "ring'; the consumer FUN_180061c2 computes the SAME "
                        "stride from two different indices — one at struct "
                        "+0x80 and one at +0x7c — and compares the two banks "
                        "entry by entry. That is a current/previous "
                        "double-buffer, so the multiplier is a BANK SELECTOR "
                        "and its identification as the layer is WITHDRAWN.",
            "consumer": "FUN_180061c2, the report builder — veneer 0x4076, the "
                        "last call in log 127's rate-gated tick block. It reads "
                        "bank[current][i] and bank[previous][i] and sets a "
                        "change flag when they differ.",
        },
        "release_before_expiry": "NOT ESTABLISHED. The append at 0x180054da is "
                                 "on the expiry branch only; no reset of the "
                                 "per-key counter on release was traced, and "
                                 "the tap-side path was not followed. What "
                                 "happens to a key released early is therefore "
                                 "an open question, not an inference.",
        "threshold_writer": "NOT ESTABLISHED. The threshold byte is at record "
                            "+0x22 of the key*0x20 array, i.e. offset +0x02 of "
                            "the record one stride on; the located 0x51 "
                            "subcommands write +0x04, +0x06, +0x07, +0x08, "
                            "+0x0a, +0x0e and +0x0f of a record, and NONE of "
                            "them was shown writing +0x00 or +0x02. Which "
                            "command sets the hold time is open.",
        "mechanism": "dual-role, hold-to-alternate, threshold in 10 ms units",
        "ring_capacity": "600 bytes per bank = 300 halfwords; the consumer "
                         "reads at most 120 of them.",
    }


@functools.lru_cache(maxsize=None)
def rapid_burst():
    """The nine rapid writes at capture t=314..318, against the decoded map."""
    if not WIRE_MODEL.exists():
        raise CommandError(f"log 126's model is missing: {WIRE_MODEL}")
    model = json.loads(WIRE_MODEL.read_text())
    writes = model["polling_rate"]["writes"]
    burst = [w for w in writes if 314.0 <= w["t"] <= 318.5]
    payloads = sorted({w["payload"] for w in burst})
    return {
        "count": len(burst),
        "window": "t = 314.2555 .. 318.198",
        "distinct_payloads": payloads,
        "indices": sorted({w["index"] for w in burst}),
        "answer": "NOTHING ELSE WAS BEING RE-APPLIED. With the subcommand map "
                  "in hand the question can be answered negatively and "
                  "precisely: all nine frames are 51 31 with index 0 and 59 "
                  "zero bytes, each followed by its own 50 55 commit, and log "
                  "126 established that the capture's ENTIRE host-to-device "
                  "vendor traffic is 74 frames of which these are the only ones "
                  "in the window. No 51 50, no 51 2d, no 51 00 — Armoury Crate "
                  "re-sent the polling rate alone, nine times.",
        "why_it_matters": "the burst is not a batched apply of several "
                          "settings, so it cannot be read as evidence that "
                          "other subcommands accompany a rate change.",
        "cause": "still undetermined. The map rules out a multi-setting batch; "
                 "it does not explain why one setting was written nine times.",
    }


@functools.lru_cache(maxsize=None)
def storage_map():
    """Where each writable field lands, and whether a checksum covers it."""
    return (
        {"field": "profile block key table",
         "ram": "0x18021de0 +0xd4 (+layer*0x1ee)",
         "flash": "0x2000 + profile*0x1000",
         "checksum": "A — sum16(blob+2, 0x4b0) & (profile | 0xfff0)",
         "covered": True, "written_by": ["51 20", "51 21", "51 22"]},
        {"field": "profile block flags", "ram": "0x18021de0 +0x02",
         "flash": "0x2000 + profile*0x1000", "checksum": "A",
         "covered": True, "written_by": ["51 2d"]},
        {"field": "polling-rate index", "ram": "0x18021de0 +0x4f8 bits 0..3",
         "flash": "0x2000 + profile*0x1000",
         "checksum": "NEITHER — A ends at +0x4b1 and B starts at +0x4fc",
         "covered": False, "written_by": ["51 31"]},
        {"field": "all-key actuation", "ram": "0x18024f0c bits 9..15",
         "flash": "the wear-levelled store at 0x1c000..0x20000",
         "checksum": "the store's own record checksum", "covered": True,
         "written_by": ["51 50"]},
        {"field": "global marker", "ram": "0x18024f0c +0x18",
         "flash": "the wear-levelled store", "checksum": "the store's own",
         "covered": True, "written_by": ["51 42"]},
        {"field": "per-key records", "ram": "0x180202d8 + layer*0xd84 + "
                                            "key*0x20, fields +0x06..+0x0a",
         "flash": "0x320000 + profile*0x4000 + layer*0x1000",
         "checksum": "the bank's own first halfword", "covered": True,
         "written_by": ["51 53", "51 57", "51 0c", "51 18"]},
        {"field": "profile selection", "ram": "0x1801e6d0 +6",
         "flash": "the wear-levelled store's 16-byte header",
         "checksum": "the store's own", "covered": True,
         "written_by": ["51 00 (indirectly, via the storage state machine)"]},
        {"field": "macro block", "ram": "0x180225fc",
         "flash": "0x20000 + profile*0x80000 + slot*0x1000",
         "checksum": "the block's own first halfword", "covered": True,
         "written_by": ["an unresolved dispatcher branch at 0x180035dc"]},
        {"field": "block D", "ram": "0x1801fef8",
         "flash": "0x340000 + profile*0x1000",
         "checksum": "the block's own first halfword", "covered": True,
         "written_by": []},
    )


# ------------------------------------------------------------------- checks

def verify():
    checks = []

    def check(ok, label, detail=""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})
        return ok

    for addr, expected in sorted(CITED.items()):
        got = halfwords(addr, len(expected.split()))
        if not check(got == expected,
                     f"the instruction at {addr:#x} is the one this model "
                     f"cites", f"{got} == {expected}"):
            break

    for addr, op, enc, _ in TOP_LEVEL_SITES:
        got = halfwords(addr, 1)
        if not check(got == enc,
                     f"the top-level compare for opcode {op:#04x} is at "
                     f"{addr:#x}", f"{got} == {enc}"):
            break
    for addr, op, enc, _ in SUB_SITES:
        got = halfwords(addr, 1)
        if not check(got == enc,
                     f"the 0x51 compare for subcommand {op:#04x} is at "
                     f"{addr:#x}", f"{got} == {enc}"):
            break

    subs = subcommand_table()
    check(len(subs) == 24, "the 0x51 family has twenty-four subcommands",
          ", ".join(r["subcommand"] for r in subs))
    check(all(r["owner_approval_required"] for r in subs),
          "every 0x51 subcommand is marked owner-approval-required",
          f"{len(subs)} write-capable")
    queries = query_table()
    check(not any(r["owner_approval_required"] for r in queries),
          "no 0x12 query is gated — the marking discriminates",
          f"{len(queries)} read-only queries")
    check(len(queries) == 10, "the 0x12 family has ten reachable subcommands",
          ", ".join(r["subcommand"] for r in queries))

    conf = Counter(r["confidence"] for r in subs + queries)
    check(conf["static-located-only"] > 0,
          "the table admits how much is NOT decoded",
          ", ".join(f"{k}={v}" for k, v in sorted(conf.items())))
    check(conf["wire-proven"] >= 2,
          "and the wire-proven rows are the ones a capture exercised",
          f"{conf['wire-proven']} rows")

    ps = profile_switch()
    check(len(ps["writers"]) == 2,
          "the profile selection byte has exactly two writers",
          ", ".join(w["instr"] for w in ps["writers"]))
    check(all(int(w["func"], 16) == STORAGE_SM for w in ps["writers"]),
          "both are in the storage state machine, not the dispatcher",
          f"func {STORAGE_SM:#x}")
    check(ps["dispatcher_writes"] == 0,
          "the vendor-HID dispatcher never writes it — the command path is "
          "indirect", f"{ps['reader_count']} reads, 0 writes")

    mb = macro_block()
    check(mb["has_usb_writer"],
          "the macro block DOES have a USB writer, so macros are not "
          "device-only", ", ".join(mb["usb_write_sites"]))
    bd = block_d()
    check(not bd["has_usb_writer"],
          "block D has NO USB writer — only the storage state machine",
          f"writers {bd['writer_functions']}")

    ht = hold_timer()
    check(ht["hal_match"] is None,
          "the hold timer is described by behaviour and NOT given a HAL name",
          f"{len(ht['hal_candidates'])} candidates, none asserted")

    rb = rapid_burst()
    check(rb["count"] == 9 and rb["indices"] == [0],
          "the rapid burst is nine 51 31 writes of index 0 and nothing else",
          f"{len(rb['distinct_payloads'])} distinct payload")

    check(WIRE_MODEL.exists() and PROFILE_MODEL.exists(),
          "the upstream models are read rather than restated",
          "polling-rate-protocol.json, profile-format.json")

    # Anti-vacuity: the census must find plenty, so its silences mean something.
    check(len(census()) > 1000, "the census is populated",
          f"{len(census())} records")
    check(len(accesses(0x180225FC, 0x18022C60)) > 10
          and len(accesses(0x1801FEF8, 0x180202D8)) > 10,
          "the block-range filter finds accesses in both blocks, so a 'no USB "
          "writer' answer is a real absence",
          f"macro {len(accesses(0x180225FC, 0x18022C60))}, "
          f"block D {len(accesses(0x1801FEF8, 0x180202D8))}")

    # The vendor release must carry the same dispatcher shape.
    same = sum(1 for addr, _, enc, _ in TOP_LEVEL_SITES
               if halfwords(addr, 1, VENDOR_APP) == enc)
    check(same == len(TOP_LEVEL_SITES),
          "the vendor release's dispatcher has the same top-level compares",
          f"{same}/{len(TOP_LEVEL_SITES)}")

    check(bool(HAL_UNMATCHED),
          "HAL names without exact symbol attribution remain listed",
          f"{len(HAL_UNMATCHED)} unmatched")

    # --- log 130 -----------------------------------------------------------
    cov = Counter(r["confidence"] for r in subs + queries)
    check(cov["static-located-only"] == 1,
          "only 0x52 is still located-only after this step",
          ", ".join(r["subcommand"] for r in subs + queries
                    if r["confidence"] == "static-located-only"))
    check(cov["static-handler-proven"] + cov["wire-proven"] == 33,
          "the other thirty-three commands carry decoded semantics",
          json.dumps(dict(cov), sort_keys=True))

    bd = block_d()
    check(bd["arithmetic_closes"],
          "block D's layout closes on its declared size — 4 + 2*0x1ee = 0x3e0",
          "two 247-entry tables plus a 2-byte checksum")
    check(len(bd["layout"]) == 3 and bd["ac_profile_match"] is None,
          "block D's fields are laid out and NO Armoury Crate field is matched "
          "to them", "3 regions, 0 matches")

    ht = hold_timer()
    check(ht["hal_match"] is None
          and ht["mechanism"] == "dual-role, hold-to-alternate, threshold in "
                                 "10 ms units",
          "the dual-role timer is recorded as a mechanism, not a HAL name",
          ht["mechanism"])
    check("WITHDRAWN" in ht["buffer"]["selector"],
          "log 128's 'per-layer ring' reading is withdrawn — the multiplier is "
          "a bank selector", "the consumer diffs two banks")
    check("NONE FOUND" in ht["buffer"]["wrap"]
          and "NOT ESTABLISHED" in ht["release_before_expiry"]
          and "NOT ESTABLISHED" in ht["threshold_writer"],
          "the three things the timer analysis could not settle say so",
          "wrap, release-before-expiry, threshold writer")

    disp = HAL_DISPOSITION
    named = [d for d in disp if d[1] is not None]
    none_found = [d for d in disp if d[1] is None]
    check(len(disp) >= len(HAL_UNMATCHED),
          "every HAL name protocol.md leaves without an opcode gets a "
          "disposition", f"{len(disp)} dispositions")
    check(any(d[0] == "GetKeyStats" for d in none_found),
          "and a name with no plausible carrier is recorded as a finding, not "
          "hidden", f"{len(none_found)} with no carrier found")
    check(all(d[3] in ("strongly-inferred", "hypothesis",
                       "no plausible carrier found") for d in disp),
          "every disposition carries one of three confidences",
          ", ".join(sorted({d[3] for d in disp})))
    check(all(d[2] for d in named),
          "every candidate carrier cites evidence", f"{len(named)} named")
    check(len(feature_capture_evidence()) == 4,
          "all four feature captures reproduce the hashes in logs 135-137")
    trigger = trigger_configuration()
    check(trigger["application_slices_roundtrip"],
          "both trigger analysis slices round-trip against their hash-verified full sources")
    check(all(r["identical"] for r in trigger["release_comparisons"]),
          "rapid-trigger handler and dead-zone helpers have matching bodies in both releases")
    check(trigger["secondary_code_identical"]
          and all(r["ok"] for r in trigger["secondary_instruction_checks"]),
          "the shared dead-zone consumer bytes match both releases and cited instructions")
    lever = rapid_trigger_lever()
    check(lever["entry_source_roundtrip"]
          and all(r["ok"] for r in lever["entry_instruction_checks"]),
          "the cross-image lever caller and threshold round-trip against the installed source")
    check(lever["release_comparison"]["only_report_call_relocated"],
          "both lever poll bodies agree except for their verified report-call relocation")
    return checks


# ------------------------------------------------------------------ output

@functools.lru_cache(maxsize=None)
def to_dict():
    checks = verify()
    subs, queries = subcommand_table(), query_table()
    return {
        "verdict": "the dispatcher accepts seventeen top-level opcodes, "
                   "twenty-four 0x51 subcommands and ten reachable 0x12 queries; "
                   "thirty-three family entries have instruction-derived "
                   "semantics. Logs 135-137 add independent feature observations; "
                   "log 138 reconciles the complete 51 54 handler and "
                   "identifies 51 59 as per-key dead-zone overrides; log 139 traces "
                   "the physical rapid-trigger switch to global bit 5 and 03 76",
        "transport": {"dispatcher": f"{DISPATCHER:#x}",
                      "request_buffer": f"{REQ_BUF:#x}",
                      "responder": f"{SEND_RESPONSE_64:#x}",
                      "report_size_bytes": 64,
                      "note": "see notes/polling-rate-protocol.json for the USB "
                              "transport; this model is the command layer"},
        "opcodes": opcode_table(),
        "subcommands_51": subs,
        "queries_12": queries,
        "feature_captures": feature_capture_evidence(),
        "feature_wire_observations": feature_wire_observations(),
        "profile_switch": profile_switch(),
        "trigger_configuration": trigger_configuration(),
        "rapid_trigger_lever": rapid_trigger_lever(),
        "macro_block": macro_block(),
        "block_d": block_d(),
        "hold_timer": hold_timer(),
        "rapid_burst": rapid_burst(),
        "storage_map": storage_map(),
        "hal_names_without_an_opcode": list(HAL_UNMATCHED),
        "hal_disposition": [{"hal_name": n, "candidate_carrier": c,
                             "evidence": e, "confidence": k}
                            for n, c, e, k in HAL_DISPOSITION],
        "never_send": [{"frame": f, "why": w} for f, w in NEVER_SEND],
        "coverage": dict(Counter(r["confidence"] for r in subs + queries)),
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of preserved images, captures and "
                      "pre-existing read-only Ghidra exports. No device was "
                      "accessed and NO FRAME WAS CONSTRUCTED — every byte "
                      "layout here comes from instructions or preserved wire "
                      "evidence, graded separately. This authorises nothing live.",
    }


def report_lines():
    d = to_dict()
    out = ["THE VENDOR COMMAND SURFACE", "",
           f"dispatcher {d['transport']['dispatcher']}   request buffer "
           f"{d['transport']['request_buffer']}", "",
           f"TOP-LEVEL OPCODES ({len(d['opcodes'])})"]
    out.append("  " + " ".join(r["opcode"] for r in d["opcodes"]))
    out += ["", f"0x51 SUBCOMMANDS ({len(d['subcommands_51'])})"]
    for r in d["subcommands_51"]:
        out.append(f"  {r['subcommand']}  {r['handler']:>12}  "
                   f"{r['confidence']:<22} {r['meaning'].split('.')[0][:64]}")
    out += ["", f"0x12 QUERIES ({len(d['queries_12'])}) — all read-only"]
    for r in d["queries_12"]:
        out.append(f"  {r['subcommand']}  {r['handler']:>12}  "
                   f"{r['confidence']:<22} {r['meaning'].split('.')[0][:64]}")
    ps = d["profile_switch"]
    out += ["", "PROFILE SWITCH", f"  {ps['answer'][:200]}...",
            "", "MACRO BLOCK", f"  {d['macro_block']['verdict'][:180]}",
            "", "BLOCK D", f"  {d['block_d']['verdict'][:180]}",
            "", "THE +0x22 HOLD TIMER",
            f"  {d['hold_timer']['behaviour']}",
            f"  HAL name: {d['hold_timer']['hal_match']} "
            f"({d['hold_timer']['hal_match_confidence'][:60]}...)",
            "", "THE RAPID BURST", f"  {d['rapid_burst']['answer'][:200]}...",
            "", "COVERAGE",
            "  " + ", ".join(f"{k}={v}" for k, v in
                             sorted(d["coverage"].items())), "", "CHECKS"]
    for c in d["checks"]:
        out.append(f"  {'PASS' if c['ok'] else 'FAIL'} {c['label']}"
                   + (f" — {c['detail']}" if c["detail"] else ""))
    s = d["summary"]
    out += ["", f"RESULT vendor_command_map_ok={s['ok']} checks={s['checks']}"]
    return out


def markdown():
    d = to_dict()
    out = ["# The vendor command map", "",
           "**Generated by `tool/map_vendor_commands.py`. Do not edit by "
           "hand.**", "",
           "> Offline analysis of preserved images, captures and pre-existing "
           "read-only Ghidra exports. No device was accessed and **no frame "
           "was constructed** — instruction-derived and captured byte layouts "
           "are graded separately. This authorises "
           "nothing live.", "",
           "## Verdict", "", f"**{d['verdict'][0].upper() + d['verdict'][1:]}.**", "",
           "## Confidence scheme", "",
           "| label | means |", "|---|---|",
           "| `wire-proven` | observed on the wire **and** decoded "
           "from the handler |",
           "| `static-handler-proven` | the handler's reads, ranges and stores "
           "are read out of the instruction stream; independent capture "
           "observations are listed separately |",
           "| `static-located-only` | the compare site and handler entry are "
           "proven; **the semantics are not established** |",
           "| `hal-name-only` | `notes/protocol.md` names a HAL method and "
           "nothing here proves the exact symbol attribution |",
           "| `wire-observed` | captured behavior correlated with owner actions "
           "or AC profile data; does not prove the full static handler |", "",
           "## Windows feature evidence (logs 135-137)", "",
           "Key numbers follow AT-101 positions for the observed keys. Fn, ROG "
           "and the physical backslash remap source remain unobserved. Macro "
           "Enter is 108 and backslash is 42; physical Enter's historical "
           "remap number is 43. Settings writes can share a single `50 55` commit.", "",
           "| capture | SHA-256 | source log |", "|---|---|---|"]
    for r in d["feature_captures"]:
        out.append(f"| `{r['capture']}` | `{r['sha256']}` | `{r['log']}` |")
    out += ["", "| command | captured behavior | static reconciliation | logs |",
            "|---|---|---|---|"]
    for r in d["feature_wire_observations"]:
        out.append(f"| `{r['command']}` | {r['meaning']} | "
                   f"{r['static_agreement']} | {r['logs']} |")
    out += ["",
           "## Top-level opcodes", "",
           f"The dispatcher at `{d['transport']['dispatcher']}` accepts "
           f"**{len(d['opcodes'])}** top-level opcodes. Only `0x12` and `0x51` "
           f"are statically opened below; opcode `54` also has a captured "
           f"macro layout in the wire table above.", "",
           "| opcode | compare at | handler | statically decoded here |",
           "|---|---|---|---|"]
    for r in d["opcodes"]:
        out.append(f"| `{r['opcode']}` | `{r['compare_at']}` | "
                   f"`{r['handler']}` | {'yes' if r['decoded'] else 'no'} |")
    out += ["", "## The `0x51` configuration family", "",
            f"**{len(d['subcommands_51'])} subcommands.** Every one writes "
            f"device state and every one is **owner-approval-required**.", "",
            "| sub | handler | static confidence | what it does | storage |",
            "|---|---|---|---|---|"]
    for r in d["subcommands_51"]:
        out.append(f"| `{r['subcommand']}` | `{r['handler']}` | "
                   f"`{r['confidence']}` | {r['meaning']} | "
                   f"{r['storage']} |")
    out += ["", "### Evidence for each row", "",
            "| sub | instructions |", "|---|---|"]
    for r in d["subcommands_51"]:
        out.append(f"| `{r['subcommand']}` | `{r['evidence']}` |")
    out += ["", "## The `0x12` query family — safe to issue", "",
            f"**{len(d['queries_12'])} reachable subcommands.** None writes "
            f"device state.", "",
            "| sub | handler | confidence | what it returns |",
            "|---|---|---|---|"]
    for r in d["queries_12"]:
        out.append(f"| `{r['subcommand']}` | `{r['handler']}` | "
                   f"`{r['confidence']}` | {r['meaning']} |")
    ps = d["profile_switch"]
    out += ["", "## Profile switching", "", ps["answer"], "",
            "| | |", "|---|---|"]
    for i, step in enumerate(ps["sequence"], 1):
        out.append(f"| {i} | {step} |")
    out += ["", f"**Writers of `{ps['byte']}`:** "
            + ", ".join(f"`{w['instr']}` (in `{w['func']}`)"
                        for w in ps["writers"])
            + f" — and {ps['reader_count']} readers, of which "
              f"{ps['dispatcher_writes']} dispatcher writes.", "",
            f"**Not established:** {ps['not_established']}", "",
            f"**Read-back:** {ps['wire_readback']}", "",
            f"**Completion reply:** {ps['completion_reply']}", "",
            "## Rapid trigger and dead-zone reconciliation (log 138)", ""]
    trigger = d["trigger_configuration"]
    rt, dz = trigger["rapid_trigger"], trigger["dead_zone"]
    out += [f"**Record:** `{trigger['record']}`; {trigger['translation']}.", "",
            "### Rapid trigger (`51 54`)", "",
            "| field at record +0x0a | bits |", "|---|---|"]
    for field in rt["fields"]:
        out.append(f"| {field['name']} | {field['shift']}.."
                   f"{field['shift'] + field['width'] - 1} |")
    out += ["", f"**Selectors (LE16 bytes 2–3):** {rt['selectors']}.", "",
            f"**Mode:** {rt['mode']}.", "",
            f"**Bounds:** {rt['handler_bounds']}.", "",
            f"**Ordering:** {rt['ordering']}.", "",
            f"**Consumer:** {rt['consumer']}", "", rt['vendor_consumer'], "",
            "### Dead zone (`51 58` / `51 59`)", "",
            "| UI label or counterpart | global request byte | global word bits | per-key request byte | record offset |",
            "|---|---:|---|---:|---|"]
    for global_field, per_key in zip(dz["global_51_58"], dz["per_key_51_59"]):
        out.append(f"| {global_field['ui_label']} | {global_field['request_byte']} | "
                   f"{global_field['shift']}..{global_field['shift'] + 2} | "
                   f"{per_key['request_byte']} | +0x{per_key['record_offset']:02x} |")
    out += ["", f"**Encoding:** {dz['encoding']}.", "",
            f"**Override:** {dz['override']}.", "",
            f"**Cache builder:** {dz['cache']}.", "",
            f"**Consumer:** {dz['consumer']}.", "",
            f"**Evidence:** {dz['confidence']}.", "",
            "| shared cache | raw-sample lookup table | six values |", "|---|---|---|"]
    for table in dz['tables']:
        out.append(f"| `{table['array']}` | `{table['table']}` | {table['values']} |")
    out += ["", "### Release comparison", "",
            "| scope | installed address | vendor address | bytes | identical |",
            "|---|---|---|---:|---|"]
    for row in trigger['release_comparisons']:
        out.append(f"| {row['scope']} | `{row['installed']}` | `{row['vendor']}` | "
                   f"{row['length']} | {row['identical']} |")
    out += ["", "Both source hashes and import round trips are checked. The "
            "secondary image is byte-identical except for its final checksum word.", "",
            "**Remaining questions:**", ""]
    out += [f"- {question}." for question in trigger['unresolved']]
    lever = d['rapid_trigger_lever']
    out += ["", "## Physical rapid-trigger switch (log 139)", "",
            lever['confidence'], "", "| component | installed 1.59 | vendor 1.00.58 |",
            "|---|---|---|"]
    for key, value in lever['installed'].items():
        out.append(f"| {key} | `{value}` | `{lever['vendor'][key]}` |")
    out += ["", f"**GPIO:** `{lever['gpio']['identifier']:#x}`, group 4 bit 7. "
            + lever['gpio']['polarity'] + ". " + lever['gpio']['basis'] + ".", "",
            f"**Caller:** {lever['debounce']['caller']}.", "",
            "**Debounce:** tenth consecutive mismatch at one poll per eight service "
            "ticks; milliseconds remain unresolved. " + lever['debounce']['rule'] + ".", "",
            lever['debounce']['counter_scope'] + ".", "",
            "**Input status:** `03 76 00 00 <state>` (21 bytes, EP `0x8c`), "
            "byte 4 = 1 on / 0 off. " + lever['report']['queue'] + ". "
            + lever['report']['delivery'] + ".", "",
            "**Readback:** " + lever['readback'] + ".", "",
            "**Lifecycle:** " + lever['lifecycle'] + ".", "",
            "**Persistence:** " + lever['persistence'] + ".", "",
            "**Writer scope:** " + lever['writer_scope'] + ".", "",
            "The 106-byte poll bodies differ only in one byte of the verified "
            "call to report builder `0x18004498`; they are not byte-identical.", "",
            "**Remaining boundaries:**", ""]
    out += [f"- {question}." for question in lever['unresolved']]
    out += ["", "## The macro block", ""]
    mb = d["macro_block"]
    out += [f"`{mb['base']}`, `{mb['size']}` bytes, "
            f"{mb['resolved_accesses']} resolved accesses.", "",
            f"**{mb['verdict']}**", "", mb["structure"], "",
            f"**Entry size:** {mb['entry_size']}", "",
            "## Block D", ""]
    bd = d["block_d"]
    out += [f"`{bd['base']}`, `{bd['size']}` bytes, flash home "
            f"`{bd['flash_home']}`, {bd['resolved_accesses']} resolved "
            f"accesses.", "", f"**{bd['verdict']}**", "",
            bd["runtime_reader"], "", "## The per-key hold timer", ""]
    ht = d["hold_timer"]
    out += [f"- **threshold:** {ht['threshold']}",
            f"- **paired value:** {ht['paired_value']}",
            f"- **scaling:** {ht['scaling']}",
            f"- **on expiry:** {ht['on_expiry']}",
            f"- **evidence:** `{ht['evidence']}`", "",
            f"**Behaviour ({ht['behaviour_confidence']}):** {ht['behaviour']}",
            "",
            f"**HAL name: none assigned.** {ht['hal_match_confidence']} "
            f"Candidates: "
            + ", ".join(f"`{c}`" for c in ht["hal_candidates"]) + ".", "",
            f"**Not established:** {ht['ring_capacity']}", "",
            "## The nine rapid writes at t = 314–318", ""]
    rb = d["rapid_burst"]
    out += [rb["answer"], "", rb["why_it_matters"], "",
            f"**Cause:** {rb['cause']}", "",
            "## Where each writable field lands", "",
            "| field | RAM | flash | checksum | covered | written by |",
            "|---|---|---|---|---|---|"]
    for f in d["storage_map"]:
        out.append(f"| {f['field']} | `{f['ram']}` | `{f['flash']}` | "
                   f"{f['checksum']} | {'yes' if f['covered'] else '**no**'} | "
                   + (", ".join(f"`{w}`" for w in f["written_by"]) or "—")
                   + " |")
    out += ["", "## Block D's layout", "",
            "| offset | size | type | role | confidence |",
            "|---|---|---|---|---|"]
    for r in d["block_d"]["layout"]:
        out.append(f"| `{r['offset']}` | `{r['size']}` | {r['type']} | "
                   f"{r['role']} | `{r['confidence']}` |")
    out += ["", f"**Reader.** {d['block_d']['reader_behaviour']}", "",
            f"**Defaults.** {d['block_d']['defaults']}", "",
            "**Persistence.** "
            + d["block_d"]["persistence_meaning"][:1].upper()
            + d["block_d"]["persistence_meaning"][1:], "",
            f"**Armoury Crate match.** {d['block_d']['ac_profile_match_note']}",
            "", "## The dual-role timer, mechanism complete", "",
            f"**{d['hold_timer']['mechanism'].capitalize()}.**", "",
            "| | |", "|---|---|"]
    b = d["hold_timer"]["buffer"]
    for k in ("base", "stride", "stride_arithmetic", "entry", "index", "wrap",
              "selector", "consumer"):
        out.append(f"| {k.replace('_', ' ')} | {b[k]} |")
    out += ["", f"**Release before expiry.** "
            f"{d['hold_timer']['release_before_expiry']}", "",
            f"**Which command sets the threshold.** "
            f"{d['hold_timer']['threshold_writer']}", "",
            f"**HAL name: none assigned.** "
            f"{d['hold_timer']['hal_match_confidence']} Candidates: "
            + ", ".join(f"`{c}`" for c in d["hold_timer"]["hal_candidates"])
            + ".", "",
            "## HAL disposition", "",
            "Every HAL method `notes/protocol.md` leaves without an opcode, "
            "with the located subcommand that could carry it — or the finding "
            "that none could.", "",
            "| HAL name | candidate carrier | evidence | confidence |",
            "|---|---|---|---|"]
    for r in d["hal_disposition"]:
        carrier = f"`{r['candidate_carrier']}`" if r["candidate_carrier"] \
            else "**none**"
        out.append(f"| `{r['hal_name']}` | {carrier} | {r['evidence']} | "
                   f"`{r['confidence']}` |")
    out += ["", "## HAL names without exact symbol attribution", "",
            ", ".join(f"`{n}`" for n in d["hal_names_without_an_opcode"]), "",
            "## NEVER SEND without explicit owner approval", "",
            "| frame | why |", "|---|---|"]
    for n in d["never_send"]:
        out.append(f"| `{n['frame']}` | {n['why']} |")
    out += ["", "## Coverage", "",
            ", ".join(f"**{k}**: {v}" for k, v in sorted(d["coverage"].items())),
            "", "## Checks", "", "| | check | detail |", "|---|---|---|"]
    for c in d["checks"]:
        out.append(f"| {'PASS' if c['ok'] else 'FAIL'} | {c['label']} | "
                   f"{c['detail']} |")
    s = d["summary"]
    out += ["", f"`RESULT vendor_command_map_ok={s['ok']} "
                f"checks={s['checks']}`", ""]
    return "\n".join(out)


def bodies():
    return {
        "vendor-command-map.json": json.dumps(to_dict(), indent=2,
                                              sort_keys=True) + "\n",
        "vendor-command-map.md": markdown(),
    }


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", action="store_true")
    p.add_argument("--write", action="store_true")
    p.add_argument("--check", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = bodies()
    except (OSError, CommandError, struct.error, KeyError, ValueError,
            json.JSONDecodeError) as exc:
        print(f"RESULT vendor_command_map_ok=False error={exc}")
        return 1
    if args.check:
        stale = [n for n, b in payload.items()
                 if not (NOTES / n).exists() or (NOTES / n).read_text() != b]
        print(f"RESULT reports_current={not stale} stale={len(stale)}"
              + ("" if not stale else " " + ", ".join(stale)))
        return 0 if not stale else 1
    if args.write:
        for n, b in payload.items():
            path = NOTES / n
            if not path.exists() or path.read_text() != b:
                path.write_text(b)
                print(f"WROTE notes/{n}")
        return 0
    if args.json:
        print(payload["vendor-command-map.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(c["ok"] for c in verify()) else 1


if __name__ == "__main__":
    sys.exit(main())
