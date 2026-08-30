#!/usr/bin/env python3
"""Decode Candidate B key translation, layout, and unsupported-key tables.

This is an offline, read-only analyzer for the preserved ASUS firmware image.
It does not access USB or execute firmware.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import struct
from pathlib import Path


EXPECTED_FIRMWARE_SHA256 = (
    "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d"
)
CANDIDATE_B_FILE_OFFSET = 0x21000
CANDIDATE_B_LENGTH = 0x1E754
CANDIDATE_B_RUNTIME_BASE = 0x18000000
CANDIDATE_A_FILE_OFFSET = 0x11000
KBID_LOOKUP_ADDRESS = 0x00004FCD
KBID_LOOKUP_LENGTH = 0x1A
KEY_TRANSLATION_ADDRESS = 0x1801BFF6
KEY_TRANSLATION_LENGTH = 0xBD
KEY_INDEX_MAP_ADDRESS = 0x1801C37C
KEY_INDEX_MAP_STRIDE = 0x86
KEY_INDEX_MAP_COUNT = 3
KEY_INDEX_LOGICAL_LENGTH = KEY_TRANSLATION_LENGTH
SCAN_POSITION_MAP_ADDRESS = 0x1801C50E
SCAN_POSITION_MAP_STRIDE = 0x100
SCAN_POSITION_MAP_COUNT = 3
REMAP_RECORD_BASE = 0x180202AC
REMAP_LAYER_STRIDE = 0xD84
REMAP_RECORD_STRIDE = 0x20
FALLBACK_RECORD_CANDIDATE = 0x4B
UNSUPPORTED_LIST_ADDRESS = 0x1801C810
BASE_UNSUPPORTED_COUNT = 6
FN_UNSUPPORTED_COUNT = 57


PHYSICAL_KEYS = [
    "Esc", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace", "Insert",
    "Tab", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "Backslash", "Delete",
    "CapsLock", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "Apostrophe", "Enter", "PageUp",
    "LeftShift", "Z", "X", "C", "V", "B", "N", "M", "Comma", "Period", "Slash", "RightShift", "Up", "PageDown",
    "LeftCtrl", "LeftGUI", "LeftAlt", "Space", "RightAlt", "Fn", "ROG", "Left", "Down", "Right",
]


def hid_usage_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for value, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=0x04):
        names[value] = letter
    for value, label in zip(range(0x1E, 0x28), "1234567890"):
        names[value] = label
    names.update(
        {
            0x28: "Enter",
            0x29: "Escape",
            0x2A: "Backspace",
            0x2B: "Tab",
            0x2C: "Space",
            0x2D: "Minus",
            0x2E: "Equal",
            0x2F: "LeftBracket",
            0x30: "RightBracket",
            0x31: "Backslash",
            0x32: "NonUSHash",
            0x33: "Semicolon",
            0x34: "Apostrophe",
            0x35: "Grave",
            0x36: "Comma",
            0x37: "Period",
            0x38: "Slash",
            0x39: "CapsLock",
            0x46: "PrintScreen",
            0x47: "ScrollLock",
            0x48: "Pause",
            0x49: "Insert",
            0x4A: "Home",
            0x4B: "PageUp",
            0x4C: "Delete",
            0x4D: "End",
            0x4E: "PageDown",
            0x4F: "Right",
            0x50: "Left",
            0x51: "Down",
            0x52: "Up",
            0x53: "NumLock",
            0x64: "NonUSBackslash",
            0x65: "Application",
            0xE0: "LeftCtrl",
            0xE1: "LeftShift",
            0xE2: "LeftAlt",
            0xE3: "LeftGUI",
            0xE4: "RightCtrl",
            0xE5: "RightShift",
            0xE6: "RightAlt",
            0xE7: "RightGUI",
            0xE8: "VendorOrCustom_E8",
        }
    )
    for value in range(0x3A, 0x46):
        names[value] = f"F{value - 0x39}"
    return names


def candidate_offset(runtime_address: int) -> int:
    return runtime_address - CANDIDATE_B_RUNTIME_BASE


def full_file_offset(runtime_address: int) -> int:
    return CANDIDATE_B_FILE_OFFSET + candidate_offset(runtime_address)


def record_address(layer: int, record_index: int) -> int:
    return (
        REMAP_RECORD_BASE
        + layer * REMAP_LAYER_STRIDE
        + record_index * REMAP_RECORD_STRIDE
    )


def format_sources(code: int, translation: bytes) -> str:
    sources = [
        f"{index}:{PHYSICAL_KEYS[index - 1]}"
        for index in range(1, len(PHYSICAL_KEYS) + 1)
        if translation[index] == code
    ]
    return ",".join(sources) if sources else "-"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "firmware",
        nargs="?",
        type=Path,
        default=Path("dumps/vendor/M605_V01_00_58.bin"),
    )
    args = parser.parse_args()

    firmware = args.firmware.read_bytes()
    digest = hashlib.sha256(firmware).hexdigest()
    candidate = firmware[
        CANDIDATE_B_FILE_OFFSET : CANDIDATE_B_FILE_OFFSET + CANDIDATE_B_LENGTH
    ]
    usage_names = hid_usage_names()

    translation_offset = candidate_offset(KEY_TRANSLATION_ADDRESS)
    translation = candidate[
        translation_offset : translation_offset + KEY_TRANSLATION_LENGTH
    ]
    kbid_lookup = firmware[
        CANDIDATE_A_FILE_OFFSET + KBID_LOOKUP_ADDRESS :
        CANDIDATE_A_FILE_OFFSET + KBID_LOOKUP_ADDRESS + KBID_LOOKUP_LENGTH
    ]
    effective_kbid_lookup = bytes(2 if value == 4 else value for value in kbid_lookup)

    map_offset = candidate_offset(KEY_INDEX_MAP_ADDRESS)
    layout_maps = tuple(
        candidate[
            map_offset + selector * KEY_INDEX_MAP_STRIDE :
            map_offset + selector * KEY_INDEX_MAP_STRIDE + KEY_INDEX_LOGICAL_LENGTH
        ]
        for selector in range(KEY_INDEX_MAP_COUNT)
    )
    scan_map_offset = candidate_offset(SCAN_POSITION_MAP_ADDRESS)
    scan_position_maps = tuple(
        candidate[
            scan_map_offset + selector * SCAN_POSITION_MAP_STRIDE :
            scan_map_offset + (selector + 1) * SCAN_POSITION_MAP_STRIDE
        ]
        for selector in range(SCAN_POSITION_MAP_COUNT)
    )
    policy_offset = candidate_offset(UNSUPPORTED_LIST_ADDRESS)
    policy_bytes = candidate[
        policy_offset : policy_offset + (BASE_UNSUPPORTED_COUNT + FN_UNSUPPORTED_COUNT) * 4
    ]
    policy = struct.unpack("<63I", policy_bytes)
    base_policy = policy[:BASE_UNSUPPORTED_COUNT]
    fn_policy = policy[BASE_UNSUPPORTED_COUNT:]

    header_words = struct.unpack_from("<8I", firmware, 0x10030)

    print(f"firmware={args.firmware}")
    print(f"size={len(firmware)}")
    print(f"sha256={digest}")
    print(f"expected_sha256_match={digest == EXPECTED_FIRMWARE_SHA256}")
    print(f"candidate_b_file_offset=0x{CANDIDATE_B_FILE_OFFSET:05x}")
    print(f"candidate_b_length=0x{len(candidate):x}")
    print(f"candidate_b_runtime_base=0x{CANDIDATE_B_RUNTIME_BASE:08x}")
    print("header_words_0x10030=" + ",".join(f"0x{x:08x}" for x in header_words))
    print(
        "key_translation="
        f"runtime=0x{KEY_TRANSLATION_ADDRESS:08x} "
        f"candidate_offset=0x{translation_offset:x} "
        f"file_offset=0x{full_file_offset(KEY_TRANSLATION_ADDRESS):x} "
        f"length={len(translation)}"
    )
    print(
        "key_index_map="
        f"runtime=0x{KEY_INDEX_MAP_ADDRESS:08x} "
        f"candidate_offset=0x{map_offset:x} "
        f"file_offset=0x{full_file_offset(KEY_INDEX_MAP_ADDRESS):x} "
        f"selector_count={KEY_INDEX_MAP_COUNT} "
        f"selector_stride=0x{KEY_INDEX_MAP_STRIDE:x} "
        f"logical_window_length=0x{KEY_INDEX_LOGICAL_LENGTH:x}"
    )
    print(
        "scan_position_map="
        f"runtime=0x{SCAN_POSITION_MAP_ADDRESS:08x} "
        f"candidate_offset=0x{scan_map_offset:x} "
        f"file_offset=0x{full_file_offset(SCAN_POSITION_MAP_ADDRESS):x} "
        f"selector_count={SCAN_POSITION_MAP_COUNT} "
        f"selector_stride=0x{SCAN_POSITION_MAP_STRIDE:x}"
    )
    print(
        "remap_records="
        f"runtime_base=0x{REMAP_RECORD_BASE:08x} "
        f"layer_stride=0x{REMAP_LAYER_STRIDE:x} "
        f"record_stride=0x{REMAP_RECORD_STRIDE:x} "
        "contents_not_embedded_in_candidate_b=true"
    )
    print(
        "unsupported_lists="
        f"runtime=0x{UNSUPPORTED_LIST_ADDRESS:08x} "
        f"candidate_offset=0x{policy_offset:x} "
        f"file_offset=0x{full_file_offset(UNSUPPORTED_LIST_ADDRESS):x} "
        f"base_count={len(base_policy)} fn_count={len(fn_policy)}"
    )

    print("\nKBID_LOOKUP_FROM_CANDIDATE_A")
    print(
        f"runtime=0x{KBID_LOOKUP_ADDRESS:08x} "
        f"file_offset=0x{CANDIDATE_A_FILE_OFFSET + KBID_LOOKUP_ADDRESS:x} "
        f"length={len(kbid_lookup)}"
    )
    print("input_id raw_selector effective_selector")
    for input_id, (raw_selector, effective_selector) in enumerate(
        zip(kbid_lookup, effective_kbid_lookup)
    ):
        print(f"{input_id:02d} 0x{raw_selector:02x} {effective_selector}")
    print("raw_selector_values=" + ",".join(str(x) for x in sorted(set(kbid_lookup))))
    print(
        "effective_selector_values="
        + ",".join(str(x) for x in sorted(set(effective_kbid_lookup)))
    )
    print("normalization_rule=raw_selector_4_becomes_effective_selector_2")

    print("\nKEY_INDEX_LOGICAL_WINDOWS")
    print("selector start end overlap_with_next fallback_0x4b_count unique_indices")
    for selector, layout_map in enumerate(layout_maps):
        start = KEY_INDEX_MAP_ADDRESS + selector * KEY_INDEX_MAP_STRIDE
        end = start + len(layout_map) - 1
        overlap = max(0, len(layout_map) - KEY_INDEX_MAP_STRIDE)
        counts = Counter(layout_map)
        unique = ",".join(f"0x{x:02x}" for x in sorted(counts))
        print(
            f"{selector} 0x{start:08x} 0x{end:08x} "
            f"{overlap if selector + 1 < len(layout_maps) else 0} "
            f"{counts[FALLBACK_RECORD_CANDIDATE]} {unique}"
        )
    print(
        "window_note=each selector accepts wire IDs 0x00..0xbc; "
        "the 0x86 selector stride makes adjacent 0xbd-byte windows overlap by 0x37 bytes"
    )
    print(
        "selector_2_tail_note=wire IDs 0x86..0xbc overlap the first 0x37 bytes "
        "of the separate scan-position table at 0x1801c50e"
    )
    print(
        "fallback_note=record index 0x4b is frequent and is a fallback/dummy candidate; "
        "its runtime semantics are not yet statically proven"
    )

    print("\nALL_WIRE_IDS_SOURCE_MAP_AND_TARGET_TRANSLATION")
    print(
        "wire_id target_internal_code usage "
        "layout0_record layout1_record layout2_record "
        "layout0_base_addr layout1_base_addr layout2_base_addr"
    )
    for wire_id, internal_code in enumerate(translation):
        records = tuple(layout_map[wire_id] for layout_map in layout_maps)
        addresses = tuple(record_address(0, index) for index in records)
        print(
            f"0x{wire_id:02x} 0x{internal_code:02x} "
            f"{usage_names.get(internal_code, 'UnknownOrVendor'):18s} "
            f"0x{records[0]:02x} 0x{records[1]:02x} 0x{records[2]:02x} "
            f"0x{addresses[0]:08x} 0x{addresses[1]:08x} 0x{addresses[2]:08x}"
        )

    print("\nHISTORICAL_WIRE_SOURCES_1_TO_68_WITH_LAYOUT_RECORDS")
    print(
        "source historical_physical_key target_internal_code usage "
        "layout0_record layout1_record layout2_record "
        "layout0_fn_addr layout1_fn_addr layout2_fn_addr"
    )
    for source, physical_key in enumerate(PHYSICAL_KEYS, start=1):
        internal_code = translation[source]
        records = tuple(layout_map[source] for layout_map in layout_maps)
        fn_addresses = tuple(record_address(1, index) for index in records)
        print(
            f"{source:02d} {physical_key:12s} 0x{internal_code:02x} "
            f"{usage_names.get(internal_code, 'UnknownOrVendor'):18s} "
            f"0x{records[0]:02x} 0x{records[1]:02x} 0x{records[2]:02x} "
            f"0x{fn_addresses[0]:08x} 0x{fn_addresses[1]:08x} "
            f"0x{fn_addresses[2]:08x}"
        )

    print("\nTARGET_ENCODING_RULES_FROM_DISPATCHER")
    print("wire_target_0x00_to_0xbc=translation_table[wire_target]")
    print("wire_target_0xff=reuse_source_translation")
    print("wire_targets_0xc7_0xc8_0xd3=wire_target_or_0xa000")
    print("other_target_values=command_specific_or_rejected; do_not_generalize")

    print("\nSCAN_POSITION_MAPS_SEPARATE_FROM_WIRE_ID_WINDOWS")
    print("selector start end sha256 fallback_0x4b_count unique_indices")
    for selector, scan_map in enumerate(scan_position_maps):
        start = SCAN_POSITION_MAP_ADDRESS + selector * SCAN_POSITION_MAP_STRIDE
        end = start + len(scan_map) - 1
        counts = Counter(scan_map)
        unique = ",".join(f"0x{x:02x}" for x in sorted(counts))
        print(
            f"{selector} 0x{start:08x} 0x{end:08x} "
            f"{hashlib.sha256(scan_map).hexdigest()} "
            f"{counts[FALLBACK_RECORD_CANDIDATE]} {unique}"
        )
        print(f"selector_{selector}_hex={scan_map.hex()}")

    print("\nWIRE_SOURCE_TRANSLATION_1_TO_68")
    print("source physical_key internal_code usage")
    for source, physical_key in enumerate(PHYSICAL_KEYS, start=1):
        code = translation[source]
        print(
            f"{source:02d} {physical_key:12s} 0x{code:02x} "
            f"{usage_names.get(code, 'UnknownOrVendor') }"
        )

    def print_policy(name: str, values: tuple[int, ...]) -> None:
        print(f"\n{name}")
        print("index internal_code usage matching_wire_sources")
        for index, value in enumerate(values):
            print(
                f"{index:02d} 0x{value:08x} "
                f"{usage_names.get(value, 'UnknownOrVendor'):18s} "
                f"{format_sources(value, translation)}"
            )

    print_policy("BASE_UNSUPPORTED_POLICY", base_policy)
    print_policy("FN_UNSUPPORTED_POLICY", fn_policy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
