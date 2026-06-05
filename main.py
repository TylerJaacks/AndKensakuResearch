#!/usr/bin/env python3
"""
build_markers.py — Test harness that reproduces the visibility-test .tr2 files.

This is the script that generates the two files we verified in-game:

  Misc_marked.tr2 Every WordList entry replaced with a marker. YOMI is
                     rewritten to per-entry unique hiragana so the IME
                     dictionary (TVMPutUdicWord) accepts every reading
                     without collisions.

  Phrase_marked.tr2 Minimal-risk edit for the どっち (DOTCH) mode: only the
                     three sections that actually render on the answer screen
                     are touched (QUESTION, SELECT1, SELECT2). Intentionally-
                     empty entries are preserved as empty. All 130 other
                     sections — including 502_DOTCH_SET_NAME and every
                     structural SET_* array — are byte-identical to the
                     original, which is what got us past the
                     ``dotTr2GetSetTr2ID`` assert at ``mod_tr2.c:603``.

Usage
-----
    python3 build_markers.py                      # uses Misc.tr2 / Phrase.tr2 in cwd
    python3 build_markers.py --marker "ねこ"      # change the visible marker
    python3 build_markers.py --misc path/to/Misc.tr2 --phrase path/to/Phrase.tr2

After running, drop the two _marked files into ``files/upd/`` on the extracted
disc, rename them back to ``Misc.tr2`` / ``Phrase.tr2``, rebuild the disc (or
point Dolphin at the extracted dir), and **delete the NAND upd/ folder** so the
game re-seeds from disc rather than using cached old data.

Constraints this script enforces, and why
-----------------------------------------
1. **Unique YOMI per WordList entry.** The IME's UDIC rejects duplicate
   reading->surface pairs. With ~3249 WordList entries we need ~3249 distinct
   hiragana readings; a base-45 encoding over a curated safe-hiragana set
   gives unambiguously-unique 1–3 char readings.

2. **Skip empty entries in Phrase.** Several DOTCH set entries are
   intentionally empty in the original. Filling them changes the "active set"
   count the game derives, which is what broke our first attempt. The fix is
   to leave empties empty.

3. **Touch only display sections in Phrase.** Every structural section
   (SET_NAME, SET_ID, SET_PRIO, the GAYA arrays, COMMENT/ROBOT auxiliaries)
   stays byte-identical to the original.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tr2 import Tr2

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# The marker text rendered on-screen. "もうそ" is what we used in the verified
# in-game test; any short Japanese string works.
DEFAULT_MARKER = "もうそ"

# A curated set of hiragana known to be accepted as legal yomi by the game's
# IME dictionary. 45 characters → 45^3 = 91,125 unique 3-char strings, more
# than enough headroom for any single section in Misc.tr2.
SAFE_HIRAGANA = (
    "あいうえお"
    "かきくけこ"
    "さしすせそ"
    "たちつてと"
    "なにぬねの"
    "はひふへほ"
    "まみむめも"
    "やゆよ"
    "らりるれろ"
    "わ"
)

# The exact three sections that render on the DOTCH answer screen.
# Anything else in Phrase.tr2 is structural or auxiliary — leave it alone.
PHRASE_DISPLAY_SECTIONS = (
    "502_DOTCH_QUESTION",
    "502_DOTCH_SELECT1",
    "502_DOTCH_SELECT2",
)


# ---------------------------------------------------------------------------
# Unique-YOMI generator
# ---------------------------------------------------------------------------
def unique_yomi(entry_id: int, alphabet: str = SAFE_HIRAGANA) -> str:
    """Deterministic, collision-free hiragana reading for a given entry id.

    Base-N encoding over ``alphabet``. We use ``id + 1`` so id 0 doesn't map
    to the empty string. Result length grows logarithmically:
      ids 0..44      → 1 char
      ids 45..2069   → 2 chars
      ids 2070..91k  → 3 chars
    """
    n = len(alphabet)
    v = entry_id + 1
    out = []
    while v > 0:
        out.append(alphabet[v % n])
        v //= n
    return "".join(reversed(out))


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def build_misc(src: Path, dst: Path, marker: str) -> dict:
    t = Tr2(src)
    wl = t.get("WordList")
    yomi = t.get("YOMI")

    word_ids = set(wl.ids())
    yomi_ids = set(yomi.ids())
    if word_ids != yomi_ids:
        missing = word_ids ^ yomi_ids
        raise RuntimeError(
            f"WordList and YOMI have mismatched id sets (diff size={len(missing)}); "
            "the original Misc.tr2 has parallel arrays — refusing to write."
        )

    seen_yomi: set[str] = set()
    for entry_id in sorted(word_ids):
        wl.set_value(entry_id, marker)
        y = unique_yomi(entry_id)
        if y in seen_yomi:
            raise RuntimeError(f"yomi collision generating id {entry_id} -> {y!r}")
        seen_yomi.add(y)
        yomi.set_value(entry_id, y)

    t.save(dst)
    return {
        "path": dst,
        "words_marked": len(word_ids),
        "yomi_collisions": 0,
        "size": dst.stat().st_size,
    }


def build_phrase(src: Path, dst: Path, marker: str) -> dict:
    t = Tr2(src)
    touched = 0
    empty_preserved = 0
    sections_changed = 0
    untouched_section_count = 0

    target = set(PHRASE_DISPLAY_SECTIONS)
    for sec in t.sections:
        if sec.name not in target:
            untouched_section_count += 1
            continue
        sections_changed += 1
        for entry in sec.entries:
            entry_id, value = entry
            if not value:                  # intentionally-empty slot — leave it
                empty_preserved += 1
                continue
            sec.set_value(entry_id, marker)
            touched += 1

    t.save(dst)
    return {
        "path": dst,
        "entries_marked": touched,
        "empties_preserved": empty_preserved,
        "sections_changed": sections_changed,
        "sections_untouched": untouched_section_count,
        "size": dst.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Verification — make sure we only changed what we meant to
# ---------------------------------------------------------------------------
def verify_phrase(src: Path, dst: Path) -> None:
    """Confirm only the three display sections differ vs. the original."""
    orig = Tr2(src)
    new = Tr2(dst)
    orig_names = orig.section_names()
    new_names = new.section_names()
    assert orig_names == new_names, "section order/names changed (would break offsets)"
    target = set(PHRASE_DISPLAY_SECTIONS)
    for name in orig_names:
        o = orig.get(name).as_dict()
        n = new.get(name).as_dict()
        if name in target:
            continue                       # expected to differ
        if o != n:
            raise AssertionError(
                f"Phrase verification failed: untouched section {name!r} changed"
            )


def verify_misc(src: Path, dst: Path, marker: str) -> None:
    orig = Tr2(src)
    new = Tr2(dst)
    # every WordList value should be the marker; every YOMI should be unique
    for sec in (new.get("WordList"),):
        for _id, v in sec.entries:
            assert v == marker, f"WordList id {_id} not marked"
    yomis = [v for _id, v in new.get("YOMI").entries]
    assert len(yomis) == len(set(yomis)), "duplicate YOMI generated"
    # everything else identical to original
    target = {"WordList", "YOMI"}
    for name in orig.section_names():
        if name in target:
            continue
        if orig.get(name).as_dict() != new.get(name).as_dict():
            raise AssertionError(
                f"Misc verification failed: untouched section {name!r} changed"
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--misc", default="Misc.tr2", help="source Misc.tr2 (default: cwd)")
    ap.add_argument("--phrase", default="Phrase.tr2", help="source Phrase.tr2 (default: cwd)")
    ap.add_argument("--marker", default=DEFAULT_MARKER, help=f"marker text (default: {DEFAULT_MARKER!r})")
    ap.add_argument("--outdir", default=".", help="output directory (default: cwd)")
    ap.add_argument("--no-verify", action="store_true", help="skip post-build verification")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    misc_src = Path(args.misc)
    phrase_src = Path(args.phrase)
    misc_dst = outdir / "Misc_marked.tr2"
    phrase_dst = outdir / "Phrase_marked.tr2"

    m = build_misc(misc_src, misc_dst, args.marker)
    print(f"Misc:   wrote {m['path']}  marked={m['words_marked']}  size={m['size']}")

    p = build_phrase(phrase_src, phrase_dst, args.marker)
    print(f"Phrase: wrote {p['path']}  marked={p['entries_marked']}  "
          f"empties_preserved={p['empties_preserved']}  "
          f"changed={p['sections_changed']}/{p['sections_changed']+p['sections_untouched']} sections")

    if not args.no_verify:
        verify_misc(misc_src, misc_dst, args.marker)
        verify_phrase(phrase_src, phrase_dst)
        print("verification: OK (untouched sections byte-identical to originals)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())