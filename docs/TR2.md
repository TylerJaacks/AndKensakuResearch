# TR2 File Format Reference

A technical reference for the `.tr2` container format used by *安藤ケンサク* (And-Kensaku / Ando Kensaku, Wii, RK3J01, 2010).

This document covers:

1. [What .tr2 files are](#1-what-tr2-files-are)
2. [Container format (byte-level)](#2-container-format-byte-level)
3. [Element types](#3-element-types)
4. [The parallel-array data model](#4-the-parallel-array-data-model)
5. [The .tr2 files shipped with the game](#5-the-tr2-files-shipped-with-the-game)
6. [How the game loads them](#6-how-the-game-loads-them)
7. [The Sign.dat signature mechanism](#7-the-signdat-signature-mechanism)
8. [Editing constraints and gotchas](#8-editing-constraints-and-gotchas)
9. [Quick reference](#9-quick-reference)

Verification status is called out per claim: **(verified)** = checked against a real file or in-game test; **(inferred)** = consistent with evidence but not directly proven; **(unknown)** = honest gap in knowledge.

---

## 1. What .tr2 files are

A `.tr2` file is a flat container holding one or more named **sections**. Each section is an array of `(id, value)` entries. Ids are sparse 32-bit integers (no need to be contiguous or start from 0). Values are either text (UTF-8 or UTF-16LE) or fixed-width scalars (signed/unsigned 8/16/32-bit integers and floats).

Across the game, `.tr2` files store **all of the localised text and tunable numeric data**: word lists, hiragana readings, quiz prompts, answer text, hit counts, comments, category names, banter scripts, blog entries, calendar text, developer credits, etc. The game's executable overlays read from these by section name and id when they need any of it.

Despite the game targeting big-endian PowerPC hardware, **the container's own integer fields are little-endian**. Text payload encodings (UTF-8 / UTF-16LE) follow standard conventions. Numeric *values* inside scalar sections are little-endian too.

---

## 2. Container format (byte-level)

A `.tr2` file is three things in sequence:

```
+-----------------------------+
|       File header (0x40)    |
+-----------------------------+
|       Section table         |   (one 20-byte record per section)
+-----------------------------+
|       Section blobs         |   (each section's full bytes, back-to-back)
+-----------------------------+
```

### 2.1 File header (64 bytes / 0x40)

| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 6 | Magic | ASCII `.tr2` followed by `\x00\x00` (verified: literal bytes are `2E 74 72 32 00 00`) |
| 0x06 | 2 | Version (u16 LE) | Value `2011` (0x07DB) in both Misc.tr2 and Phrase.tr2 of the 2010-2011 build (verified). Probably the build year, not a format version. |
| 0x08 | 32 | File name | ASCII, NUL-padded. Holds the base filename — Misc.tr2 has `"Misc"`, Phrase.tr2 has `"Phrase"` (verified). |
| 0x38 | 4 | Section-table offset (u32 LE) | Byte offset from start of file where the section table begins. Typically `0x40`, immediately after the header. |
| 0x3C | 4 | Section count (u32 LE) | Number of sections. Misc.tr2 has 41; Phrase.tr2 has 133 (verified). |
| 0x28-0x37 | 16 | Unknown / padding | All-zero in observed files; never read by tr2.py. |

### 2.2 Section table

Immediately after the header (typically at offset `0x40`). One record per section, 20 bytes each:

| Offset within record | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 4 | Index (u32 LE) | Section's sequential index (0, 1, 2, …) |
| 0x04 | 4 | Offset (u32 LE) | Byte offset from start of file to this section's first byte |
| 0x08 | 4 | Header-size constant (u32 LE) | Always `0x14` (= the 20 bytes of this record itself). Stored but unused. |
| 0x0C | 4 | Size (u32 LE) | Total byte length of the section (including its own header + index + value pool) |
| 0x10 | 4 | Size again (u32 LE) | Identical to the previous field. Purpose unknown — possibly a checksum slot that ended up holding a duplicate of the size, or a reserved field. |

### 2.3 Section

Each section begins at the offset given in its table record and has three parts:

```
+-----------------------------+
| Section header (0x80)       |   name, element type, entry count
+-----------------------------+
| Entry index (12 * count)    |   one (id, value_offset, value_length) per entry
+-----------------------------+
| Value pool                  |   the actual bytes the index points into
+-----------------------------+
```

#### Section header (128 bytes / 0x80)

| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 32 | Section name | ASCII, NUL-padded. e.g. `"WordList"`, `"502_DOTCH_QUESTION"` |
| 0x40 | 16 | Element type | ASCII, NUL-padded. One of `"UTF-8"`, `"UTF-16LE"`, `"INT8"`, `"UINT8"`, `"INT16"`, `"UINT16"`, `"INT32"`, `"UINT32"`, `"INT"`, `"FLOAT"` |
| 0x7C | 4 | Entry count (u32 LE) | Number of `(id, value)` entries in this section |
| 0x50–0x7B | 44 | Unknown / padding | All-zero in observed files |

#### Entry index

Starts at offset `0x80` from the section start. One 12-byte record per entry:

| Offset within record | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 4 | Entry id (u32 LE) | The id used to address this entry |
| 0x04 | 4 | Value offset (u32 LE) | Byte offset of this entry's value, **relative to the section start** |
| 0x08 | 4 | Value length (u32 LE) | Length of the value in bytes, **excluding any terminator** |

#### Value pool

Comes immediately after the entry index. Each entry's bytes live at `<value_offset>` for `<value_length>` bytes:

- **Text values** (UTF-8 / UTF-16LE): the string bytes. A NUL terminator (`\x00` for UTF-8, `\x00\x00` for UTF-16LE) sits at `<value_offset + value_length>` but the length itself does not count the terminator.
- **Scalar values** (INT*, UINT*, FLOAT): the raw little-endian bytes of the number, sized per the element type (1/2/4 bytes).

Value-pool ordering is the same as the entry-index ordering by default, but the format permits arbitrary layout — the index says where each value is.

---

## 3. Element types

The 16-byte element-type string in each section header tells the reader how to decode every value in that section. All values within one section share a type.

### 3.1 Text types

| Type string | Encoding | Notes |
|---|---|---|
| `UTF-8` | UTF-8 | Variable-width. Most Japanese word/sentence data uses this. |
| `UTF-16LE` | UTF-16, little-endian | 2 or 4 bytes per character. Used for some longer or specially-handled text (e.g. KAKUNOU_SUBJECT in Misc.tr2, most BLOG sections in Phrase.tr2). |

Empty entries are real: a value of length 0 means "this slot exists but is empty," and is structurally distinct from "this slot doesn't exist." Many sections in the shipping game have empty slots interleaved with non-empty ones, and the game's code is sensitive to which is which (see §8).

### 3.2 Scalar types

| Type string | Width | Range |
|---|---:|---|
| `INT8` | 1 | -128..127 |
| `UINT8` | 1 | 0..255 |
| `INT16` | 2 | -32768..32767 |
| `UINT16` | 2 | 0..65535 |
| `INT32` | 4 | -2^31..2^31-1 |
| `UINT32` | 4 | 0..2^32-1 |
| `INT` | 4 | Same as INT32 (verified: appears once in Phrase.tr2, parses as a 32-bit signed integer) |
| `FLOAT` | 4 | IEEE 754 single-precision |

All scalar values are little-endian.

### 3.3 Type distribution observed

In **Misc.tr2** (41 sections total): 16 UTF-8, 1 UTF-16LE, and 24 sections across various integer types.

In **Phrase.tr2** (133 sections total): 67 UTF-16LE, 17 UTF-8, 21 UINT16, 19 INT8, 6 FLOAT, plus a handful of others.

---

## 4. The parallel-array data model

The key insight for working with `.tr2` files: **the game stores logically related data column-by-column, not row-by-row**.

What a player perceives as "a single quiz question" (its prompt, both answer tiles, both hit counts, both result comments, the category it belongs to, the robot's reactions, the banter scripts) is not stored as a single struct in one place. Instead, each piece of that information lives in its own section, and all those sections agree on the same id.

Example — どっち (mode 502) "question 1":

```
Section in Phrase.tr2          [1] →  Meaning
─────────────────────────────  ────────────────────────────
502_DOTCH_QUESTION             "どちらのヒット数が多い？"     (prompt)
502_DOTCH_SELECT1              "小学校時代に戻りたい"        (left answer)
502_DOTCH_SELECT2              "中学時代に戻りたい"          (right answer)
502_DOTCH_HIT1                 6284                       (left answer's hit count)
502_DOTCH_HIT2                 6604                       (right answer's hit count)
502_DOTCH_COMMENT1             "小学生に戻りたい…"           (blurb if left wins)
502_DOTCH_COMMENT2             "小学校時代と比べて…"          (blurb if right wins)
502_DOTCH_ROBOT1               "たのしい子ども時代を…"         (robot line if left wins)
502_DOTCH_ROBOT2               "ステキな青春時代を…"          (robot line if right wins)
502_DOTCH_SET_NAME             "あの頃に戻りたい"            (category heading)
502_DOTCH_SET_ID               10
502_DOTCH_SET_PRIO             12
502_DOTCH_SELECT_YOMI1         "しょうがっこうじだいに…"        (reading of left answer)
502_DOTCH_SELECT_YOMI2         "ちゅうがくじだいに…"            (reading of right answer)
502_DOTCH_SET_GAYA_QUIZ_ARRAY  <multi-line banter blob>   (side-character dialogue)
…etc, 18 sections total all keyed on id=1
```

Reading "question 1" means reading id `1` from each of those sections and assembling the row in memory. The on-disk file has no concept of a row; the row exists only when the engine reconstitutes it at display time.

### 4.1 Naming convention

Per-mode content uses the prefix `<mode_number>_<MODE_NAME>_<FIELD>`:

```
502_DOTCH_QUESTION             mode 502 = どっち,    field = QUESTION
109_SHIRITORI_TEFUDA081        mode 109 = しりとり,   field = TEFUDA081
504_CROSSWORD_STAGE81_ARRAY    mode 504 = クロスワード, field = STAGE81_ARRAY
503_BLOG_*                     mode 503 = blog/diary content
```

The mode number is the engine's internal id for the mode, not its menu position. Mode numbers are not sequential: known modes include 109, 502, 503, 504, and there are surely others we haven't catalogued.

Shared (non-per-mode) sections in `Misc.tr2` use bare names like `WordList`, `YOMI`, `SUB_GENRE_A`, `WORD_RANK`, etc. — no mode prefix.

### 4.2 Parallel-array invariants

When sections share an id space (like the 18 `502_DOTCH_*` sections above, or `WordList` + `YOMI` in Misc.tr2), they form a **parallel-array group**. The game iterates over the id set and assumes every section in the group has an entry for every id.

This implies hard invariants:

- **All sections in a parallel group must have the same set of ids**. If `502_DOTCH_QUESTION` has 523 ids but `502_DOTCH_SELECT1` has 522, the missing id is broken or out-of-bounds when the engine tries to assemble that row.
- **Empty/non-empty parity matters**. If `502_DOTCH_SET_NAME[2]` is the empty string in the original, the game treats id 2 as "no category heading" and groups it differently. Filling that empty creates a category the rest of the data doesn't know how to relate to (verified — this is the bug that initially crashed our first Phrase edit at `dotTr2GetSetTr2ID` in `mod_tr2.c:603`).
- **You can edit values in place, but you cannot add or remove ids** without testing. Engine overlays may be compiled with hard-coded bounds, and exceeding them is untested territory.

### 4.3 Hit counts and how the game decides winners

For どっち specifically: the engine compares `502_DOTCH_HIT1[id]` to `502_DOTCH_HIT2[id]` and announces the higher side as the winner. Margins range from 4 to 3068 in shipping data. There are **zero ties across all 523 entries** (verified) — the developers deliberately avoided ties, which suggests the engine's tie-handling is untested. Editing tools should reject ties by default.

---

## 5. The .tr2 files shipped with the game

The game ships with these `.tr2` files at `data/Locale/Text/Tr2/`:

| File | Role | Verified? |
|---|---|---|
| `Misc.tr2` | **Shared word dictionary.** Used by *every* mode that needs "a word" — typing input, random word display, dictionary lookups. ~3249 word/reading pairs plus genre/hit/category metadata. | verified |
| `Phrase.tr2` | **Per-mode phrase content** for phrase-shaped modes — どっち (502), the blog/diary mode (503), developer credits, calendar text, the PHRASENAME/YOMI extended dictionary. 133 sections total. | verified |
| `Puzzle.tr2` | **Per-mode puzzle content** for puzzle-shaped modes — しりとり (109), クロスワード (504), and presumably others. | inferred (from log mentions of `109_SHIRITORI_*` and `504_CROSSWORD_*` being "not found in Puzzle") |
| `Double00.tr2` | Unknown — loaded at boot. Likely additional content for some mode (the "Double" naming hints at the multiplayer or two-player modes, but unverified). | unknown |
| `Double01.tr2` | Unknown — same. | unknown |
| `Double02.tr2` | Unknown — same. | unknown |
| `Sign.dat` | **SHA-1 signatures** of all the above `.tr2` files. Verified at boot. See §7. | verified |

The boot order observed in logs is: `Sign.dat`, `Double00.tr2`, `Double01.tr2`, `Double02.tr2`, `Misc.tr2`, `Phrase.tr2`, `Puzzle.tr2`.

### 5.1 Misc.tr2 section inventory (41 sections)

Notable sections in Misc.tr2 (verified by parsing the shipping file):

| Section | Type | Count | Purpose |
|---|---|---:|---|
| `WordList` | UTF-8 | 3249 | Display spelling of each shared dictionary word (`アカデミー`, `アジア`, …) |
| `YOMI` | UTF-8 | 3249 | Hiragana reading of each word (`あかでみー`, `あじあ`, …). Parallel with `WordList`. |
| `SUB_GENRE_A` / `_B` / `_C` | UINT16 | 3249 each | Category tags per word (one word can belong to up to three sub-genres) |
| `WORD_RANK` | UINT8 | 3249 | Difficulty rank, mapped to letters: 0=S, 1=A, 2=B, 3=C, 4=D, 5=E |
| `SINGLEHITS` | INT32 | 3249 | Google hit count per word (used by modes that ask "how many hits does X have?") |
| `KAKUNOU_*` | various | 120 each | "Storage" / inventory metadata for the word-collection feature |
| `MainGenreList` / `SubGenreList` | UTF-8 | small | The genre tag dictionary (mapping the SUB_GENRE_* numbers to names) |
| `SHOOTING_STAGE_*` | UTF-8 | small | Word lists used by a shooter-style minigame |
| `QUEST_MAXHP` | INT32 | 1 | A single tuning constant |

### 5.2 Phrase.tr2 mode groups (133 sections)

By prefix:

| Prefix | Sections | What it is |
|---|---:|---|
| `503_BLOG_*` | 91 | Blog/diary mode content (the largest single mode in Phrase.tr2 by far) |
| `502_DOTCH_*` | 18 | どっち mode (covered exhaustively in §4) |
| `PHRASE*` | 10 | A separate ~4419-entry "phrase dictionary" — like Misc's WordList/YOMI but for phrases rather than single words |
| `CALENDAR_*` | 6 | Calendar/date-related text |
| `dev_list_*` | 5 | Developer credits (names, appearance times, logos, hit counts, display types) |
| `entry` / `readingPlusMark` | 2 | Locale config markers (`jajp`, `ja-JP` etc.) — not content |
| `502_DOCHI` | 1 | Single-section companion to the 18 `502_DOTCH_*` sections — purpose unclear, possibly a legacy/leftover |

### 5.3 Puzzle.tr2

Not directly inspected in this work, but inferred from log evidence:

- `109_SHIRITORI_*` — しりとり (Japanese word-chain) content. Stages are numbered (e.g. `109_SHIRITORI_TEFUDA081`) and contain the "hand" of available words plus presumably scoring/timing data.
- `504_CROSSWORD_*` — crossword puzzle content. Stages are numbered (`504_CROSSWORD_STAGE81_ARRAY`) and contain the grid layout, clues, and answers.

Other modes likely have content here too.

---

## 6. How the game loads them

```
Boot
 └─ wordLoadTask (in main.dol)
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Sign.dat
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Double00.tr2
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Double01.tr2
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Double02.tr2
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Misc.tr2
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Phrase.tr2
     ├─ Open path: upd/../../data/Locale/Text/Tr2/Puzzle.tr2
     │   (each load triggers wordUpdateChkTr2Signature against Sign.dat)
     ├─ Parse each container in RAM (the format described in §2)
     ├─ Register Misc.tr2's (YOMI → WordList) pairs into the IME UDIC
     │   via TVMPutUdicWord — this is what makes the keyboard work
     └─ "wordLoadTask : Word File load finish, from DVD"   (or "from NAND")
```

Once loaded, the parsed sections sit in RAM for the entire game session. Mode overlays (`502_dotch.res`, `504_crossword.res`, etc.) load and unload as the player switches modes, but they all read from the same in-memory `.tr2` images.

### 6.1 The disc/NAND duality

The path expression `upd/../../data/Locale/Text/Tr2/` is the game's way of asking "wherever the active source is, find the Tr2 directory." It resolves to disc on first boot but to **NAND `upd/`** once any web update has arrived. The game prefers NAND when both exist.

This matters for modding: if you put modified `.tr2` files on the disc but the NAND `upd/` folder has older copies, the NAND copies win. The fix is to **delete the NAND `upd/` folder** so the game re-seeds from disc.

The NAND location is:

```
<Wii NAND root>/title/00010000/524b334a/data/upd/
```

The `524b334a` is the ASCII-hex of the game code `RK3J` (R=0x52, K=0x4B, 3=0x33, J=0x4A). On Dolphin, the Wii NAND root is `<Dolphin User dir>/Wii/`.

### 6.2 The web update path (historical)

The game was designed to receive periodic data updates from Nintendo Wi-Fi Connection. Each `.tr2` file has a serial number (e.g. `2010040301`), and at boot the game would contact the server, send its current serial, and download newer payloads if available. The new files would land in NAND `upd/`.

**This path no longer works.** Nintendo WFC shut down in May 2014. The shipping disc's `.tr2` files (serial `2010040301` for regular data, `2010040601` for "P" data) are now the final-ever official version. Live updates from the original server are impossible.

A community-run replacement update server would be technically possible but is a separate reverse-engineering project — would require pulling apart the network code in main.dol, working out the URL pattern and payload format, and standing up a stub server.

---

## 7. The Sign.dat signature mechanism

`Sign.dat` is a small companion file that stores SHA-1 hashes of every `.tr2` file the game loads. At each `.tr2` load, the function `wordUpdateChkTr2Signature` (at virtual address `0x80030D1C` in main.dol) computes the SHA-1 of the freshly-loaded file's bytes and compares it against the matching hash in `Sign.dat`.

On mismatch:

1. The game logs `Signature Error!!!`.
2. Calls `gameSetUpdateDataBroken(1)`.
3. Asserts at `word_update.c:80`.
4. Hangs or crashes the boot.

This is what blocks any edited `.tr2` file from loading on an unmodified game.

### 7.1 Bypassing the check

The check has two verdict points in `wordUpdateChkTr2Signature`. Each calls the SHA-1 comparator at `0x80031668` (which returns *non-zero on MATCH*), then:

```
80030E20  cmpwi  r3, 0
80030E24  bne    0x80030EA0    ; MATCH → jump to clean exit
80030E28  ...                  ; MISMATCH → falls through to error+assert

80030E60  cmpwi  r3, 0
80030E64  bne    0x80030EA0    ; second verdict point, same shape
```

Turning both `bne` instructions into unconditional `b` (branch always) makes every file take the clean-exit path regardless of its actual hash. The byte-level edit is:

```
0x80030E24:  40 82 00 7C   →   48 00 00 7C    (bne +0x7C  →  b +0x7C)
0x80030E64:  40 82 00 3C   →   48 00 00 3C    (bne +0x3C  →  b +0x3C)
```

Two 32-bit writes. No length change. The same patch is expressible four ways:

- **Modified `main.dol`** (binary patch applied to disc)
- **Dolphin INI patch** (in `GameSettings/RK3J01.ini`, applied to memory at game startup)
- **Action Replay code**: `04030E24 4800007C` / `04030E64 4800003C`
- **Gecko code**: same bytes as AR (the 32-bit-write opcode happens to be identical)

For a permanent fix that doesn't require any cheat-loading infrastructure, use the modified DOL. For Dolphin convenience, use the INI patch. For real-Wii hardware via USB Loader GX / Riivolution etc., use the Gecko code in `.gct` form.

---

## 8. Editing constraints and gotchas

Lessons learned the hard way. Violating any of these has produced an in-game crash or visible bug during this project's verification work.

### 8.1 Parallel arrays must stay aligned

Every section in a parallel-array group must keep the same set of ids. Adding an id to one section without adding it to its peers, or removing an id from one but not all, breaks the row-assembly step in the engine. Practical implication: **edit in place; don't insert or delete entries**.

### 8.2 Empty/non-empty parity is structural

Several sections have intentionally-empty entries (`502_DOTCH_SET_NAME` has 308 of them, deliberately). The game derives counts and groupings from which slots are empty. Filling an empty slot or emptying a filled slot changes a count the rest of the data doesn't agree with, and the engine asserts.

**Rule:** if the original value is empty, keep the new value empty (or don't touch it). If the original is non-empty, the new one must also be non-empty.

### 8.3 YOMI dictionary rules (Misc.tr2 only)

The game registers `(YOMI, WordList)` pairs into the system IME UDIC at boot. Constraints we've verified:

- **YOMI must be hiragana-only.** The IME rejects entries with kanji or katakana in the yomi.
- **The legal-yomi character set is permissive.** It includes the basic 46-char hiragana, dakuten/handakuten (がぎぐ…ぱぴぷ), yōon (ゃゅょ), small っ, small vowels (ぁぃぅぇぉ), the long vowel mark ー, the modern hiragana variants ゔ and ゎ, and several punctuation characters used by the shipping game itself: `/` (alternation between alt readings, e.g. `にほん/にっぽん`), `・` (foreign-word separator), `＝` (compound name separator), `～` (casual emphasis).
- **No duplicate `(yomi, word)` pairs.** Homophones are fine — the shipping game has 40 groups where the same yomi maps to different words (`きたい` → 期待 / 機体 / 気体). What's not allowed is two entries with identical reading *and* identical surface form, because the UDIC has no way to disambiguate them.

### 8.4 Container-level invariants

The parser preserves byte-exact round-trips on untouched files. Section *order* and *original offsets* are preserved on rebuild — only sections you actually touch get re-serialized. This is why:

- A "minimal edit" that changes only 3 of 133 sections produces a file where the other 130 sections are byte-identical to the original.
- Editing one section can push later sections to later offsets (if the edited section grew), but never overlaps them. The section table's offset field gets updated automatically.

### 8.5 Tie behavior (DOTCH-specific)

Shipping data has **zero ties** across all 523 entries — the developers always made one side win. The engine's tie-handling code path is therefore untested. Editing tools should reject ties (`HIT1 == HIT2`) by default; if you want to experiment with one, do so deliberately and watch for unexpected behavior.

### 8.6 Caching: clear NAND `upd/` after editing

The game loads from NAND `upd/` if it exists, otherwise from disc. If you've edited disc-side files but the NAND cache holds older copies, the cache wins. Always delete the NAND `upd/` folder after pushing edited files to disc, or the game will silently keep using the old data.

---

## 9. Quick reference

### File layout
```
header (0x40) | section table (20 × N) | section blobs
```

### Section layout
```
header (0x80) | entry index (12 × M) | value pool
```

### Header field offsets (file)
```
0x00  magic       6   ".tr2\0\0"
0x06  version     u16 LE
0x08  filename    32  ASCII NUL-padded
0x38  table_off   u32 LE
0x3C  count       u32 LE
```

### Section table record
```
0x00  index       u32 LE
0x04  offset      u32 LE
0x08  hdr_size    u32 LE  (always 0x14)
0x0C  size        u32 LE
0x10  size2       u32 LE  (== size)
```

### Section header field offsets
```
0x00  name        32  ASCII NUL-padded
0x40  etype       16  ASCII NUL-padded
0x7C  entries     u32 LE
0x80  → entry index begins here
```

### Entry index record
```
0x00  id          u32 LE
0x04  voff        u32 LE  (relative to section start)
0x08  vlen        u32 LE  (bytes excluding terminator)
```

### Endianness summary
- Container fields: **little-endian**
- Text payloads: UTF-8 or UTF-16LE (encoding name in section header)
- Scalar payloads: **little-endian**
- Despite the game running on big-endian PowerPC

### Section-name conventions
- Per-mode: `<num>_<NAME>_<FIELD>` (e.g. `502_DOTCH_QUESTION`, `109_SHIRITORI_TEFUDA081`)
- Shared dictionary: bare names (`WordList`, `YOMI`, `SUB_GENRE_A`, …)

### Files and what they're for
| File | Role |
|---|---|
| `Misc.tr2` | Shared word dictionary (every mode reads this) |
| `Phrase.tr2` | Per-mode content for phrase-shaped modes (DOTCH, BLOG, …) |
| `Puzzle.tr2` | Per-mode content for puzzle-shaped modes (SHIRITORI, CROSSWORD, …) |
| `Double00/01/02.tr2` | Unknown; loaded at boot |
| `Sign.dat` | SHA-1 hashes of all the above |

### Signature bypass
```
0x80030E24:  4082007C → 4800007C
0x80030E64:  4082003C → 4800003C
```

As Gecko / AR code:
```
04030E24 4800007C
04030E64 4800003C
```

### NAND cache location (Dolphin / real Wii)
```
<NAND root>/title/00010000/524b334a/data/upd/
```
Delete this folder to force the game to re-seed from disc.

---

## Status of this document

Everything labeled "verified" has been confirmed by either reading the parser source against real game files (`tr2.py`'s round-trip property holds byte-exact on unmodified files) or by an in-game test on Dolphin with the bypass-patched DOL. "Inferred" claims are consistent with all the evidence we've collected but haven't been directly tested. "Unknown" gaps are flagged honestly — particularly the role of `Double00/01/02.tr2` and the full section inventory of `Puzzle.tr2`, neither of which we've enumerated in this work.

The accompanying tools (`tr2.py` for the format library, `tr2_edit.py` for the editing CLI, `patch_dol.py` for the signature bypass, and the cheat-code equivalents in `RK3J01.ini` / `RK3J01.gct`) are the practical companions to this reference.