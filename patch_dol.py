#!/usr/bin/env python3
"""
patch_dol.py — Disable the word-data signature check in And-Kensaku's main.dol.

Background
----------
On boot the game verifies each ``upd/*.tr2`` word file against a stored SHA-1
in ``Sign.dat`` (function ``wordUpdateChkTr2Signature`` at 0x80030d1c). On a
mismatch it logs ``Signature Error!!!``, sets ``gameSetUpdateDataBroken`` and
asserts (``word_update.c:80``), which then crashes. That blocks any edited
word file from loading.

The check has two verdict branches. Each calls the comparator at 0x80031668
(which returns *non-zero on MATCH*), then:

    80030e20  cmpwi r3, 0
    80030e24  bne   0x80030ea0   ; MATCH -> jump to clean exit
    80030e28  ...                ; MISMATCH -> falls through to error+assert

    80030e60  cmpwi r3, 0
    80030e64  bne   0x80030ea0   ; second verdict point, same shape

Forcing both branches to be *unconditional* (``b 0x80030ea0``) makes every file
take the clean-exit path regardless of its signature. Two 4-byte edits, three
bytes actually changed per site, file size unchanged.

    bne 0x80030ea0 : 40 82 00 7c        -> b 0x80030ea0 : 48 00 00 7c
    bne 0x80030ea0 : 40 82 00 3c        -> b 0x80030ea0 : 48 00 00 3c

Usage
-----
    python3 patch_dol.py main.dol -o main_patched.dol
    python3 patch_dol.py main.dol --verify        # report state, change nothing

The script is idempotent: running it on an already-patched DOL is a no-op.
It only writes if it finds the exact expected original bytes (or confirms the
patch is already applied), so it will refuse to corrupt an unexpected file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# (file_offset, original_bytes, patched_bytes, virtual_address)
PATCHES = [
    (0x01FF64, bytes.fromhex("4082007c"), bytes.fromhex("4800007c"), 0x80030E24),
    (0x01FFA4, bytes.fromhex("4082003c"), bytes.fromhex("4800003c"), 0x80030E64),
]


def classify(data: bytes, off: int, orig: bytes, patched: bytes) -> str:
    cur = data[off:off + 4]
    if cur == patched:
        return "already-patched"
    if cur == orig:
        return "original"
    return "unexpected"


def patch(data: bytearray, *, verify_only: bool) -> tuple[bool, list[str]]:
    notes = []
    states = []
    for off, orig, patched, va in PATCHES:
        state = classify(data, off, orig, patched)
        states.append(state)
        notes.append(f"  {va:#010x} (file {off:#08x}): {data[off:off+4].hex()}  [{state}]")

    if "unexpected" in states:
        return False, notes + ["ERROR: unexpected bytes at a patch site; refusing to write."]

    if verify_only:
        return True, notes

    changed = False
    for off, orig, patched, _ in PATCHES:
        if data[off:off + 4] != patched:
            data[off:off + 4] = patched
            changed = True
    notes.append("patched (changes written)" if changed else "no changes needed (already patched)")
    return True, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Disable And-Kensaku word-data signature check in main.dol")
    ap.add_argument("dol", help="path to main.dol")
    ap.add_argument("-o", "--output", help="output path (default: <input>_patched.dol)")
    ap.add_argument("--verify", action="store_true", help="report patch state without writing")
    args = ap.parse_args(argv)

    src = Path(args.dol)
    if not src.is_file():
        print(f"error: {src} not found", file=sys.stderr)
        return 2

    data = bytearray(src.read_bytes())
    ok, notes = patch(data, verify_only=args.verify)
    print("\n".join(notes))
    if not ok:
        return 1
    if args.verify:
        return 0

    out = Path(args.output) if args.output else src.with_name(src.stem + "_patched" + src.suffix)
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
