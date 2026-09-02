#!/usr/bin/env python3
"""Safely build checksum-correct Candidate-B patches for vendor image 1.00.58.

This is an offline construction/checking tool, not evidence that an image will
boot and not a flashing tool. It is intentionally locked to the preserved
1.00.58 artifact and accepts patches only inside its known Candidate-B region.

Examples:
    python3 tool/build_modified_image.py --demo
    python3 tool/build_modified_image.py --patch 0x3f66f=72 --out /tmp/mod.bin
"""
import argparse
import hashlib
from pathlib import Path
import struct

from analyze_boot_structures import known_boot_checks
from analyze_candidate_integrity import (
    DEFAULT_BIN, FLASH_BASE, M, REC0, WORD_SUM_REGIONS, analyze,
    chunked_crc_sum, parse_records,
)

EXPECTED_SOURCE_SHA256 = "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d"
EXPECTED_SIZE = 0x7C000
CRC_FIELD = 0x8

# Recovered from Candidate A's scatter table at full-image offset 0x16750.
CANDIDATE_B_LO = 0x21000
COPY_SIZE = 0x1E354
COMPRESSED_LO = CANDIDATE_B_LO + COPY_SIZE       # 0x3f354
COMPRESSED_SIZE = 0x400
DECOMPRESSED_SIZE = 0x0B04
CANDIDATE_B_HI = COMPRESSED_LO + COMPRESSED_SIZE  # 0x3f754

# Observed for the preserved 1.00.58 stream; asserted so a regression is loud.
EXPECTED_CONSUMED = 0x3FE
EXPECTED_TRAILING = 2

# The scatter copy lands Candidate B at RAM 0x18000000; the decompressed block
# follows the plain copy, so it starts at RUNTIME_BASE + COPY_SIZE.
RUNTIME_BASE = 0x18000000
DECOMPRESSED_RUNTIME_BASE = RUNTIME_BASE + COPY_SIZE   # 0x1801e354


def load_source(path):
    data = bytearray(path.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != EXPECTED_SIZE or digest != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            "source is not the preserved M605 1.00.58 image; offsets and "
            "scatter format have not been validated for this file")
    return data


def scatter_decompress(source, expected_size=DECOMPRESSED_SIZE):
    """Emulate Candidate A's handler at 0x17c with strict bounds.

    Returns (output, consumed, blocks, literals) where `literals` maps each
    literal byte's source index to its output index, so a patch offset can be
    resolved to the runtime address it will occupy.
    """
    source = bytes(source)
    pos = 0
    output = bytearray()
    blocks = 0
    literals = {}
    while len(output) < expected_size:
        if pos >= len(source):
            raise ValueError("compressed source exhausted")
        token = source[pos]
        pos += 1

        literal_field = token & 7
        if literal_field == 0:
            if pos >= len(source):
                raise ValueError("missing extended literal length")
            literal_field = source[pos]
            pos += 1
        run = token >> 4
        if run == 0:
            if pos >= len(source):
                raise ValueError("missing extended run length")
            run = source[pos]
            pos += 1

        literal_count = literal_field - 1
        if literal_count < 0 or pos + literal_count > len(source):
            raise ValueError("invalid literal length")
        for step in range(literal_count):
            literals[pos + step] = len(output) + step
        output.extend(source[pos:pos + literal_count])
        pos += literal_count

        if token & 8:
            if pos >= len(source):
                raise ValueError("missing back-reference offset")
            offset = source[pos]
            pos += 1
            if offset == 0 or offset > len(output):
                raise ValueError("invalid back-reference offset")
            for _ in range(run + 2):
                output.append(output[-offset])
        else:
            output.extend(b"\x00" * run)

        blocks += 1
        if len(output) > expected_size:
            raise ValueError("decompressed output overshoots scatter region")

    return bytes(output), pos, blocks, literals


def validate_scatter(img):
    """Decompress [0x3f354, 0x3f754) and require the observed shape."""
    source = img[COMPRESSED_LO:CANDIDATE_B_HI]
    try:
        output, consumed, _blocks, _literals = scatter_decompress(source)
    except ValueError as exc:
        return False, str(exc)
    trailing = source[consumed:]
    ok = (len(output) == DECOMPRESSED_SIZE
          and consumed == EXPECTED_CONSUMED
          and len(trailing) == EXPECTED_TRAILING
          and all(byte == 0 for byte in trailing))
    detail = (f"output=0x{len(output):x} consumed=0x{consumed:x} "
              f"trailing={len(trailing)} zero_padded={all(b == 0 for b in trailing)}")
    return ok, detail


def literal_runtime_address(img, file_off):
    """Map a file offset inside the compressed stream to the runtime address of
    the byte it emits. Raises if the offset is not a literal."""
    if not COMPRESSED_LO <= file_off < CANDIDATE_B_HI:
        raise ValueError(f"0x{file_off:x} is outside the compressed scatter stream")
    _output, _consumed, _blocks, literals = scatter_decompress(
        img[COMPRESSED_LO:CANDIDATE_B_HI])
    index = literals.get(file_off - COMPRESSED_LO)
    if index is None:
        raise ValueError(
            f"0x{file_off:x} is a control byte, not a literal; patching it would "
            "reshape the stream")
    return index, DECOMPRESSED_RUNTIME_BASE + index


def validate_patches(patches):
    spans = []
    for off, payload in patches:
        if not payload:
            raise ValueError("empty patch payload")
        end = off + len(payload)
        if not (CANDIDATE_B_LO <= off < end <= CANDIDATE_B_HI):
            raise ValueError(
                f"patch 0x{off:x}..0x{end:x} is outside Candidate B "
                f"0x{CANDIDATE_B_LO:x}..0x{CANDIDATE_B_HI:x}")
        if any(off < old_end and old_off < end for old_off, old_end in spans):
            raise ValueError("patch ranges overlap")
        spans.append((off, end))


def recompute_integrity(img):
    records = parse_records(img, 0)
    for index, addr, length, _stored, _dst in records:
        off = addr - FLASH_BASE
        checksum = chunked_crc_sum(img, off, length)
        struct.pack_into("<I", img, REC0 + index * 0x10 + CRC_FIELD, checksum)
    for lo, hi in WORD_SUM_REGIONS.values():
        words = struct.unpack(f"<{(hi - lo) // 4}I", img[lo:hi])
        struct.pack_into("<I", img, hi - 4, sum(words[:-1]) & M)
    return img


def verify(img):
    checks = {}
    try:
        _records, _word_sums, integrity = analyze(img, 0)
        checks.update(integrity)
        _containers, _skipped, _records, boot = known_boot_checks(img, 0)
        checks.update({f"known boot: {name}": ok for name, ok in boot.items()})
    except (ValueError, struct.error) as exc:
        checks[f"parse error: {exc}"] = False
    scatter_ok, scatter_detail = validate_scatter(img)
    checks[f"scatter stream ({scatter_detail})"] = scatter_ok
    return checks


def build(source, patches, out=None):
    validate_patches(patches)
    img = load_source(source)
    for off, payload in patches:
        img[off:off + len(payload)] = payload
    recompute_integrity(img)
    checks = verify(img)
    if not all(checks.values()):
        raise ValueError("rebuilt image failed offline checks")
    if out is not None:
        with out.open("xb") as fh:
            fh.write(img)
    return img, checks


def report(title, checks):
    print(title)
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    return all(checks.values())


def demo(source):
    original = load_source(source)
    rebuilt = recompute_integrity(load_source(source))
    idempotent = rebuilt == original
    patch_off = 0x3F66F
    patched, checks = build(source, [(patch_off, b"r")])
    changed = [i for i, (old, new) in enumerate(zip(original, patched)) if old != new]
    allowed_changes = {patch_off, REC0 + 0x10 + CRC_FIELD, REC0 + 0x10 + CRC_FIELD + 1,
                       REC0 + 0x10 + CRC_FIELD + 2, REC0 + 0x10 + CRC_FIELD + 3,
                       0x7BFFC, 0x7BFFD, 0x7BFFE, 0x7BFFF}
    changes_scoped = set(changed) <= allowed_changes and patch_off in changed
    index, runtime = literal_runtime_address(original, patch_off)
    print("PROGRAM build_modified_image")
    print("MODE offline demo; no output written")
    print(f"SOURCE {source}")
    print(f"SOURCE_SHA256 {hashlib.sha256(original).hexdigest()}")
    print(f"IDEMPOTENT {idempotent}")
    print(f"PATCH 0x{patch_off:x}: 0x{original[patch_off]:02x} -> 0x72")
    print(f"SCATTER_MAP 0x{patch_off:x} is a literal -> decompressed index "
          f"0x{index:x} -> runtime 0x{runtime:08x}")
    print(f"CHANGES_SCOPED {changes_scoped} changed_bytes={len(changed)}")
    ok = report("CHECKS", checks)
    print("LIMITATION Passing means the known integrity fields and the scatter "
          "structure are internally consistent; it does not prove the image boots.")
    return 0 if idempotent and changes_scoped and ok else 1


def patch_value(value):
    try:
        off_text, hex_text = value.split("=", 1)
        return int(off_text, 0), bytes.fromhex(hex_text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("expected OFFSET=HEXBYTES") from exc


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_BIN)
    parser.add_argument("--patch", action="append", type=patch_value, default=[])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--demo", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.demo or (not args.patch and args.out is None):
        return demo(args.source)
    if not args.patch:
        raise SystemExit("at least one --patch is required")
    try:
        _img, checks = build(args.source, args.patch, args.out)
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"REFUSING: {exc}")
        return 1
    ok = report(
        f"REBUILT {len(args.patch)} patch(es)" +
        (f" -> {args.out}" if args.out else " (not written)"), checks)
    print("LIMITATION No boot or device test was performed.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
