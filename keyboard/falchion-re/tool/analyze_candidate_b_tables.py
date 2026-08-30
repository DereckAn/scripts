#!/usr/bin/env python3
"""Decode Candidate B key translation and unsupported-key policy tables.

This is an offline, read-only analyzer for the preserved ASUS firmware image.
It does not access USB or execute firmware.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXPECTED_FIRMWARE_SHA256 = (
    "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d"
)
CANDIDATE_B_FILE_OFFSET = 0x21000
CANDIDATE_B_LENGTH = 0x1E754
CANDIDATE_B_RUNTIME_BASE = 0x18000000
KEY_TRANSLATION_ADDRESS = 0x1801BFF6
KEY_TRANSLATION_LENGTH = 0xBD
KEY_INDEX_MAP_ADDRESS = 0x1801C37C
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
        f"candidate_offset=0x{candidate_offset(KEY_INDEX_MAP_ADDRESS):x} "
        f"file_offset=0x{full_file_offset(KEY_INDEX_MAP_ADDRESS):x}"
    )
    print(
        "unsupported_lists="
        f"runtime=0x{UNSUPPORTED_LIST_ADDRESS:08x} "
        f"candidate_offset=0x{policy_offset:x} "
        f"file_offset=0x{full_file_offset(UNSUPPORTED_LIST_ADDRESS):x} "
        f"base_count={len(base_policy)} fn_count={len(fn_policy)}"
    )

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
