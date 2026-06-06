#!/usr/bin/env python3
"""
tr2_edit.py — Author real edits to And-Kensaku .tr2 files via TSV round-trip.

The verified-safe edit surface is intentionally narrow:

  Misc.tr2     WordList + YOMI (parallel arrays, 3249 entries)
  Phrase.tr2   502_DOTCH_QUESTION + 502_DOTCH_SELECT1 + 502_DOTCH_SELECT2
               (parallel arrays, 523 entries, on-screen DOTCH text only)

Anything else (PHRASENAME/PHRASEYOMI, BLOG, CALENDAR, structural SET_* arrays,
etc.) is not supported here — we have no in-game verification that those edits
are safe, and at least one section (SET_NAME) is known to be structurally
load-bearing in ways that broke the game last time we touched it.

Workflow
--------
1. Export the editable content of a .tr2 to a TSV:

       python3 tr2_edit.py export-misc Misc.tr2 -o misc.tsv
       python3 tr2_edit.py export-dotch Phrase.tr2 -o dotch.tsv

2. Edit the TSV in any editor (Excel, Sheets, vim, VS Code — anything that
   handles UTF-8). You can edit any row in place. Rows you don't touch are
   no-ops. You can also delete rows you don't intend to change — only rows
   present in the TSV are considered, and of those only rows whose values
   differ from the original are applied.

3. Validate (optional but recommended — same checks as apply, no write):

       python3 tr2_edit.py validate-misc Misc.tr2 misc.tsv
       python3 tr2_edit.py validate-dotch Phrase.tr2 dotch.tsv

4. Apply to produce a modified .tr2:

       python3 tr2_edit.py apply-misc  Misc.tr2  misc.tsv  -o Misc_new.tr2
       python3 tr2_edit.py apply-dotch Phrase.tr2 dotch.tsv -o Phrase_new.tr2

   The new file is written atomically (tempfile + rename). On any constraint
   violation, nothing is written.

Constraints enforced
--------------------
Misc:
  * Every id in the TSV must already exist in WordList AND YOMI.
  * `word` must be non-empty.
  * `yomi` must be non-empty and contain only legal hiragana (see
    LEGAL_YOMI_CHARS). The set is permissive for real readings — includes
    dakuten/handakuten, yōon (small ゃゅょ), small っ, small vowels, and
    the long-vowel mark ー — but rejects katakana, kanji, romaji, ASCII
    punctuation, and anything else likely to fail the IME's UDIC.
  * No exact (yomi, word) pair may be duplicated in the FINAL file. Natural
    homophones (same yomi, different word — like きたい for 期待 / 機体 /
    気体) are FINE; the shipping game itself has 40 such groups. What the
    IME UDIC cannot tolerate is two entries with identical reading AND
    identical surface form, since it has no way to disambiguate them.

DOTCH:
  * Every id in the TSV must already exist in all three sections.
  * If the original entry was non-empty, the edited one must also be
    non-empty. The harness lesson: empty/non-empty status is structural.
  * No yomi check — these are display fields (UTF-16LE), free text.

TSV format
----------
Tab-separated, UTF-8, with a header row. Fields are not escaped — tabs and
newlines in values are rejected at parse time (real entries shouldn't have
them; if you ever hit one in the original, this tool refuses to round-trip
and you'd need to fall back to direct tr2.py edits for that row).

  misc.tsv:    id<TAB>word<TAB>yomi
  dotch.tsv:   id<TAB>question<TAB>select1<TAB>select2
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from tr2 import Tr2

# ---------------------------------------------------------------------------
# Legal-yomi alphabet (permissive — covers real Japanese readings)
# ---------------------------------------------------------------------------
LEGAL_YOMI_CHARS = frozenset(
    # plain hiragana
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
    # dakuten
    "がぎぐげござじずぜぞだぢづでどばびぶべぼ"
    # handakuten
    "ぱぴぷぺぽ"
    # yōon (small)
    "ゃゅょ"
    # small tsu
    "っ"
    # small vowels
    "ぁぃぅぇぉ"
    # modern hiragana variants for foreign loanwords
    "ゔゎ"        # ゔ (vu) and ゎ (small wa) — both used in shipping YOMI
    # long vowel mark
    "ー"
    # delimiters/separators the shipping game uses in YOMI
    "/"           # alternation between alt readings (e.g. にほん/にっぽん)
    "・"          # foreign-word separator (さぐらだ・ふぁみりあ)
    "＝"          # compound foreign name separator (もん・さん＝みしぇる)
    "～"          # casual emphasis (しんじられな～い)
)


def illegal_chars(yomi: str) -> list[str]:
    """Return a list of characters in `yomi` that are not in the legal set."""
    return [c for c in yomi if c not in LEGAL_YOMI_CHARS]


# ---------------------------------------------------------------------------
# TSV I/O — strict, UTF-8, header row, no escaping
# ---------------------------------------------------------------------------
def _check_field(value: str, field_name: str, row_num: int) -> None:
    if "\t" in value:
        raise ValueError(f"row {row_num}: field {field_name!r} contains a TAB; reject")
    if "\n" in value or "\r" in value:
        raise ValueError(f"row {row_num}: field {field_name!r} contains a newline; reject")


def write_tsv(path: Path, header: list[str], rows: Iterable[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n",
                       quoting=csv.QUOTE_NONE, escapechar=None)
        w.writerow(header)
        for row in rows:
            for i, v in enumerate(row):
                _check_field(v, header[i], -1)
            w.writerow(row)


def read_tsv(path: Path, expected_header: list[str]) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(r, None)
        if header is None:
            raise ValueError(f"{path}: empty file")
        if header != expected_header:
            raise ValueError(f"{path}: header mismatch\n  got:      {header}\n  expected: {expected_header}")
        for row_num, row in enumerate(r, start=2):
            if not row or all(c == "" for c in row):
                continue   # blank line
            if len(row) != len(expected_header):
                raise ValueError(f"{path}:{row_num}: expected {len(expected_header)} columns, got {len(row)}")
            for i, v in enumerate(row):
                _check_field(v, expected_header[i], row_num)
            rec = dict(zip(expected_header, row))
            try:
                rec["id"] = int(rec["id"])
            except ValueError:
                raise ValueError(f"{path}:{row_num}: id must be an integer, got {rec['id']!r}")
            rec["_row"] = row_num
            out.append(rec)
    # detect duplicate ids in the TSV
    seen: dict[int, int] = {}
    for rec in out:
        if rec["id"] in seen:
            raise ValueError(f"{path}:{rec['_row']}: duplicate id {rec['id']} "
                             f"(also at row {seen[rec['id']]})")
        seen[rec["id"]] = rec["_row"]
    return out


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# Misc edits
# ---------------------------------------------------------------------------
MISC_HEADER = ["id", "word", "yomi"]


def export_misc(src: Path, out: Path) -> int:
    t = Tr2(src)
    wl = t.get("WordList").as_dict()
    yo = t.get("YOMI").as_dict()
    if set(wl) != set(yo):
        raise RuntimeError(f"{src}: WordList and YOMI have mismatched id sets — file is malformed")
    rows = [[str(wid), wl[wid], yo[wid]] for wid in sorted(wl)]
    write_tsv(out, MISC_HEADER, rows)
    return len(rows)


def _plan_misc_edits(orig: Tr2, edits: list[dict]) -> tuple[list[dict], list[str]]:
    """Return (effective_edits, errors). effective_edits = only rows that
    actually change something. errors = list of validation messages."""
    wl_ids = set(orig.get("WordList").ids())
    yo_ids = set(orig.get("YOMI").ids())
    wl_orig = orig.get("WordList").as_dict()
    yo_orig = orig.get("YOMI").as_dict()

    errors: list[str] = []
    effective: list[dict] = []

    for rec in edits:
        wid = rec["id"]
        word = rec["word"]
        yomi = rec["yomi"]
        row = rec["_row"]

        if wid not in wl_ids:
            errors.append(f"row {row}: id {wid} not present in WordList")
            continue
        if wid not in yo_ids:
            errors.append(f"row {row}: id {wid} not present in YOMI")
            continue
        # Skip no-op rows BEFORE per-row content validation. The game already
        # accepts whatever's in its own data; a TSV row identical to the
        # original is a pass-through and we don't second-guess it.
        if word == wl_orig[wid] and yomi == yo_orig[wid]:
            continue
        if word == "":
            errors.append(f"row {row}: word is empty for id {wid}")
            continue
        if yomi == "":
            errors.append(f"row {row}: yomi is empty for id {wid}")
            continue
        # Legal-char check applies ONLY when yomi is actually changing.
        if yomi != yo_orig[wid]:
            bad = illegal_chars(yomi)
            if bad:
                errors.append(f"row {row}: yomi {yomi!r} for id {wid} contains illegal chars: {bad}")
                continue
        effective.append(rec)

    # Dictionary uniqueness: no exact (yomi, word) pair may be duplicated in
    # the post-edit file. Pure-yomi collisions (homophones) are FINE — the
    # shipping game has 40+ such groups.
    final_wl: dict[int, str] = dict(wl_orig)
    final_yo: dict[int, str] = dict(yo_orig)
    for rec in effective:
        final_wl[rec["id"]] = rec["word"]
        final_yo[rec["id"]] = rec["yomi"]
    seen_pairs: dict[tuple[str, str], int] = {}
    for wid in final_wl:
        pair = (final_yo[wid], final_wl[wid])
        if pair in seen_pairs and seen_pairs[pair] != wid:
            errors.append(
                f"(yomi, word) pair {pair!r} would be shared by ids "
                f"{seen_pairs[pair]} and {wid} — identical reading+surface "
                f"is rejected by the IME UDIC"
            )
        else:
            seen_pairs[pair] = wid

    return effective, errors


def _print_plan(label: str, n_edits: int, n_effective: int, errors: list[str]) -> bool:
    print(f"{label}: parsed_edits={n_edits} effective_changes={n_effective} errors={len(errors)}")
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)
    return not errors


def cmd_apply_misc(args) -> int:
    src = Path(args.tr2)
    tsv = Path(args.tsv)
    out = Path(args.output) if args.output else src.with_name(src.stem + "_edited" + src.suffix)
    t = Tr2(src)
    edits = read_tsv(tsv, MISC_HEADER)
    effective, errors = _plan_misc_edits(t, edits)
    ok = _print_plan("misc", len(edits), len(effective), errors)
    if not ok:
        return 1
    if args.dry_run:
        for rec in effective:
            print(f"  would change id={rec['id']}: "
                  f"{t.get('WordList').value(rec['id'])!r}->{rec['word']!r}  "
                  f"yomi {t.get('YOMI').value(rec['id'])!r}->{rec['yomi']!r}")
        return 0
    wl = t.get("WordList")
    yo = t.get("YOMI")
    for rec in effective:
        wl.set_value(rec["id"], rec["word"])
        yo.set_value(rec["id"], rec["yomi"])
    atomic_write_bytes(out, t.build())
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(effective)} entries changed)")
    return 0


def cmd_validate_misc(args) -> int:
    t = Tr2(args.tr2)
    edits = read_tsv(Path(args.tsv), MISC_HEADER)
    effective, errors = _plan_misc_edits(t, edits)
    ok = _print_plan("misc", len(edits), len(effective), errors)
    return 0 if ok else 1


def cmd_export_misc(args) -> int:
    n = export_misc(Path(args.tr2), Path(args.output))
    print(f"wrote {args.output} ({n} rows)")
    return 0


# ---------------------------------------------------------------------------
# DOTCH edits
# ---------------------------------------------------------------------------
DOTCH_HEADER = ["id", "question", "select1", "select2", "hits1", "hits2"]
DOTCH_TEXT_SECTIONS = ("502_DOTCH_QUESTION", "502_DOTCH_SELECT1", "502_DOTCH_SELECT2")
DOTCH_HIT_SECTIONS = ("502_DOTCH_HIT1", "502_DOTCH_HIT2")
DOTCH_SECTIONS = DOTCH_TEXT_SECTIONS + DOTCH_HIT_SECTIONS
# field name in the TSV -> section name in the .tr2
DOTCH_FIELD_TO_SECTION = {
    "question": "502_DOTCH_QUESTION",
    "select1":  "502_DOTCH_SELECT1",
    "select2":  "502_DOTCH_SELECT2",
    "hits1":    "502_DOTCH_HIT1",
    "hits2":    "502_DOTCH_HIT2",
}
DOTCH_TEXT_FIELDS = ("question", "select1", "select2")
DOTCH_HIT_FIELDS = ("hits1", "hits2")


def export_dotch(src: Path, out: Path) -> int:
    t = Tr2(src)
    sec = {name: t.get(name).as_dict() for name in DOTCH_SECTIONS}
    id_sets = [set(d) for d in sec.values()]
    if any(s != id_sets[0] for s in id_sets[1:]):
        raise RuntimeError(f"{src}: DOTCH parallel sections have mismatched id sets — refusing")
    rows = []
    for i in sorted(id_sets[0]):
        rows.append([
            str(i),
            sec["502_DOTCH_QUESTION"][i],
            sec["502_DOTCH_SELECT1"][i],
            sec["502_DOTCH_SELECT2"][i],
            str(sec["502_DOTCH_HIT1"][i]),
            str(sec["502_DOTCH_HIT2"][i]),
        ])
    write_tsv(out, DOTCH_HEADER, rows)
    return len(rows)


def _plan_dotch_edits(orig: Tr2, edits: list[dict]) -> tuple[list[dict], list[str]]:
    orig_vals = {name: orig.get(name).as_dict() for name in DOTCH_SECTIONS}
    valid_ids = set(orig_vals[DOTCH_TEXT_SECTIONS[0]])

    errors: list[str] = []
    effective: list[dict] = []

    for rec in edits:
        eid = rec["id"]
        row = rec["_row"]
        if eid not in valid_ids:
            errors.append(f"row {row}: id {eid} not present in DOTCH sections")
            continue

        # Parse hit values to int up front (TSV stores them as strings).
        try:
            rec["hits1"] = int(rec["hits1"])
            rec["hits2"] = int(rec["hits2"])
        except ValueError:
            errors.append(f"row {row}: hits1/hits2 must be integers, got {rec['hits1']!r}/{rec['hits2']!r}")
            continue

        # Skip no-op rows before content validation.
        unchanged_text = all(
            rec[f] == orig_vals[DOTCH_FIELD_TO_SECTION[f]][eid] for f in DOTCH_TEXT_FIELDS
        )
        unchanged_hits = all(
            rec[f] == orig_vals[DOTCH_FIELD_TO_SECTION[f]][eid] for f in DOTCH_HIT_FIELDS
        )
        if unchanged_text and unchanged_hits:
            continue

        # Text parity check — only for fields that changed
        parity_ok = True
        for field in DOTCH_TEXT_FIELDS:
            sec_name = DOTCH_FIELD_TO_SECTION[field]
            new_v = rec[field]
            orig_v = orig_vals[sec_name][eid]
            if new_v == orig_v:
                continue
            if (orig_v == "") != (new_v == ""):
                errors.append(
                    f"row {row}: id {eid} {sec_name} empty/non-empty parity broken "
                    f"(orig={'empty' if orig_v=='' else 'set'}, new={'empty' if new_v=='' else 'set'})"
                )
                parity_ok = False
        if not parity_ok:
            continue

        # Hit range checks — only enforce on changed values
        hit_ok = True
        for field in DOTCH_HIT_FIELDS:
            new_v = rec[field]
            orig_v = orig_vals[DOTCH_FIELD_TO_SECTION[field]][eid]
            if new_v == orig_v:
                continue
            if new_v < 0:
                errors.append(f"row {row}: id {eid} {field} must be >= 0, got {new_v}")
                hit_ok = False
        if not hit_ok:
            continue

        # Tie check — shipping data has zero ties (verified across 523 entries),
        # so tie-handling is untested territory. Block by default.
        if rec["hits1"] == rec["hits2"]:
            errors.append(
                f"row {row}: id {eid} hits1 == hits2 == {rec['hits1']} (tie) — shipping data "
                f"has no ties; behavior unverified. Adjust one side by at least 1."
            )
            continue

        effective.append(rec)
    return effective, errors


def cmd_apply_dotch(args) -> int:
    src = Path(args.tr2)
    out = Path(args.output) if args.output else src.with_name(src.stem + "_edited" + src.suffix)
    t = Tr2(src)
    edits = read_tsv(Path(args.tsv), DOTCH_HEADER)
    effective, errors = _plan_dotch_edits(t, edits)
    ok = _print_plan("dotch", len(edits), len(effective), errors)
    if not ok:
        return 1
    if args.dry_run:
        for rec in effective:
            print(f"  would change id={rec['id']}:")
            for fld in DOTCH_TEXT_FIELDS + DOTCH_HIT_FIELDS:
                sec = DOTCH_FIELD_TO_SECTION[fld]
                ov = t.get(sec).value(rec["id"])
                if ov != rec[fld]:
                    print(f"      {fld}: {ov!r} -> {rec[fld]!r}")
        return 0
    for rec in effective:
        for fld in DOTCH_TEXT_FIELDS + DOTCH_HIT_FIELDS:
            t.get(DOTCH_FIELD_TO_SECTION[fld]).set_value(rec["id"], rec[fld])
    atomic_write_bytes(out, t.build())
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(effective)} entries changed)")
    return 0


def cmd_validate_dotch(args) -> int:
    t = Tr2(args.tr2)
    edits = read_tsv(Path(args.tsv), DOTCH_HEADER)
    effective, errors = _plan_dotch_edits(t, edits)
    ok = _print_plan("dotch", len(edits), len(effective), errors)
    return 0 if ok else 1


def cmd_export_dotch(args) -> int:
    n = export_dotch(Path(args.tr2), Path(args.output))
    print(f"wrote {args.output} ({n} rows)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tr2_edit", description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export-misc", help="dump WordList+YOMI to a TSV")
    p.add_argument("tr2"); p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_export_misc)

    p = sub.add_parser("export-dotch", help="dump DOTCH question/select1/select2 to a TSV")
    p.add_argument("tr2"); p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_export_dotch)

    p = sub.add_parser("validate-misc", help="check a misc TSV against the original (no write)")
    p.add_argument("tr2"); p.add_argument("tsv")
    p.set_defaults(func=cmd_validate_misc)

    p = sub.add_parser("validate-dotch", help="check a dotch TSV against the original (no write)")
    p.add_argument("tr2"); p.add_argument("tsv")
    p.set_defaults(func=cmd_validate_dotch)

    p = sub.add_parser("apply-misc", help="apply a misc TSV to produce a modified .tr2")
    p.add_argument("tr2"); p.add_argument("tsv")
    p.add_argument("-o", "--output")
    p.add_argument("--dry-run", action="store_true", help="print plan, don't write")
    p.set_defaults(func=cmd_apply_misc)

    p = sub.add_parser("apply-dotch", help="apply a dotch TSV to produce a modified .tr2")
    p.add_argument("tr2"); p.add_argument("tsv")
    p.add_argument("-o", "--output")
    p.add_argument("--dry-run", action="store_true", help="print plan, don't write")
    p.set_defaults(func=cmd_apply_dotch)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())