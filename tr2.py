"""
tr2.py — Parser, editor, and writer for And-Kensaku (安藤ケンサク / アンド検索, Wii)
``.tr2`` word-data files.

The ``.tr2`` container is a flat collection of named *sections*. Every section
holds an array of ``(id, value)`` entries; ids are sparse 32-bit integers and
need not be contiguous. Values are either text (UTF-8 or UTF-16LE) or fixed
scalars (ints / floats). Despite the game targeting big-endian PowerPC, the
container's own integer fields are **little-endian**.

Layout
------
File header           0x00, 0x40 bytes
  +0x00  magic  ".tr2"
  +0x06  u16    version
  +0x08  char[32] file name (NUL-padded)
  +0x38  u32    section-table offset
  +0x3C  u32    section count

Section table         (at the offset above) — one 20-byte record per section:
  u32 index, u32 offset, u32 header_size, u32 size, u32 size2
  (header_size is always 0x14; size == size2 == the section's total byte length)

Section                (at each record's offset)
  +0x00  char[32] section name
  +0x40  char[16] element type ("UTF-8", "UTF-16LE", "INT32", "FLOAT", ...)
  +0x7C  u32      entry count
  0x80   index    entry_count * (u32 id, u32 value_offset, u32 value_length)
                  value_offset is relative to the section start; value_length
                  is the byte length of the value *excluding* its terminator.
  ...    value pool (the bytes the index points into)

Editing model
-------------
Parsing keeps each section's original raw bytes. :meth:`Tr2.build` re-emits any
section you did *not* touch verbatim, and only re-serialises the ones you edited
(``section.dirty``). An untouched file therefore rebuilds byte-for-byte
identically to the input. Edited sections are laid out as
``[header][index][value pool]`` with offsets/lengths/count recomputed.

Typical use
-----------
    t = Tr2("Misc.tr2")
    t.set("WordList", 29, "新しい単語")     # change one entry's text
    t.set("YOMI",     29, "あたらしいたんご")
    t.save("Misc_edited.tr2")

    # bulk edit
    wl = t.get("WordList")
    for entry_id in t.ids("WordList"):
        wl.set_value(entry_id, "test")

    # create a brand-new file from an existing template's structure
    t2 = Tr2.from_template("Misc.tr2")   # same sections/types, cleared entries
    t2.get("WordList").set_value(1, "hello")
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Container constants (all integer fields little-endian)
# ---------------------------------------------------------------------------
MAGIC = b".tr2"

FILE_HEADER_SIZE = 0x40
VERSION_OFFSET = 0x06
FILE_NAME_OFFSET = 0x08
FILE_NAME_SIZE = 32
SECTION_TABLE_OFFSET_FIELD = 0x38
SECTION_COUNT_FIELD = 0x3C

SECTION_TABLE_ENTRY_SIZE = 20
SECTION_TABLE_HEADER_SIZE = 0x14   # constant stored in field 3 of each record

SECTION_HEADER_SIZE = 0x80
SECTION_NAME_SIZE = 32
SECTION_TYPE_OFFSET = 0x40
SECTION_TYPE_SIZE = 16
SECTION_ENTRY_COUNT_OFFSET = 0x7C
SECTION_INDEX_ENTRY_SIZE = 12

UTF8_TYPE = "UTF-8"
UTF16LE_TYPE = "UTF-16LE"
_UTF16LE_ENCODING = "utf-16-le"
_DECODE_ERRORS = "replace"

# element type -> (byte width, struct format) for scalar sections
_SCALAR_TYPES: dict[str, tuple[int, str]] = {
    "INT8": (1, "<b"),
    "UINT8": (1, "<B"),
    "INT16": (2, "<h"),
    "UINT16": (2, "<H"),
    "INT32": (4, "<i"),
    "UINT32": (4, "<I"),
    "INT": (4, "<i"),
    "FLOAT": (4, "<f"),
}
_DEFAULT_SCALAR = (4, "<i")

# Convenience mapping seen in Misc.tr2's WORD_RANK section.
WORD_RANK_LABELS = {0: "S", 1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}


# ---------------------------------------------------------------------------
# Small byte helpers
# ---------------------------------------------------------------------------
def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _read_cstring(data: bytes, offset: int, size: int, encoding: str = "ascii") -> str:
    raw = data[offset:offset + size].split(b"\x00", 1)[0]
    return raw.decode(encoding, _DECODE_ERRORS)


def _is_text_type(element_type: str) -> bool:
    return element_type.startswith("UTF")


def _encode_value(element_type: str, value: Any) -> tuple[bytes, int]:
    """Return (bytes-including-terminator, content-length-without-terminator)."""
    if element_type == UTF8_TYPE:
        encoded = value.encode("utf-8")
        return encoded + b"\x00", len(encoded)
    if element_type == UTF16LE_TYPE:
        encoded = value.encode(_UTF16LE_ENCODING)
        # game stores a single trailing NUL byte after UTF-16LE values
        return encoded + b"\x00", len(encoded)
    width, fmt = _SCALAR_TYPES.get(element_type, _DEFAULT_SCALAR)
    return struct.pack(fmt, value), width


def _decode_value(data: bytes, element_type: str, value_offset: int, value_length: int) -> Any:
    if element_type == UTF8_TYPE:
        return data[value_offset:value_offset + value_length].decode("utf-8", _DECODE_ERRORS)
    if element_type == UTF16LE_TYPE:
        return data[value_offset:value_offset + value_length].decode(_UTF16LE_ENCODING, _DECODE_ERRORS)
    _, fmt = _SCALAR_TYPES.get(element_type, _DEFAULT_SCALAR)
    return struct.unpack_from(fmt, data, value_offset)[0]


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------
class Section:
    """One named array of ``(id, value)`` entries inside a :class:`Tr2`."""

    def __init__(self, name: str, element_type: str):
        self.name = name
        self.etype = element_type
        self.entries: list[list] = []          # list of [id, value]
        self._raw_header: bytes | None = None
        self._raw_body: bytes | None = None
        self.dirty = False

    # -- queries ----------------------------------------------------------
    def is_text(self) -> bool:
        return _is_text_type(self.etype)

    def ids(self) -> list[int]:
        return [e[0] for e in self.entries]

    def has(self, entry_id: int) -> bool:
        return any(e[0] == entry_id for e in self.entries)

    def value(self, entry_id: int, default: Any = None) -> Any:
        for e in self.entries:
            if e[0] == entry_id:
                return e[1]
        return default

    def as_dict(self) -> dict[int, Any]:
        return {e[0]: e[1] for e in self.entries}

    # -- mutation ---------------------------------------------------------
    def set_value(self, entry_id: int, value: Any) -> None:
        """Set (or insert) ``entry_id``'s value. Marks the section dirty."""
        for e in self.entries:
            if e[0] == entry_id:
                e[1] = value
                self.dirty = True
                return
        self.entries.append([entry_id, value])
        self.entries.sort(key=lambda e: e[0])
        self.dirty = True

    def delete(self, entry_id: int) -> None:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e[0] != entry_id]
        if len(self.entries) != before:
            self.dirty = True

    def map_values(self, func) -> None:
        """Apply ``func(id, value) -> new_value`` to every entry."""
        for e in self.entries:
            e[1] = func(e[0], e[1])
        self.dirty = True

    # -- serialisation ----------------------------------------------------
    def to_bytes(self) -> bytes:
        if not self.dirty and self._raw_body is not None and self._raw_header is not None:
            return self._raw_header + self._raw_body
        if self._raw_header is None:
            raise ValueError(f"section {self.name!r} has no header template to rebuild from")

        self.entries.sort(key=lambda e: e[0])

        header = bytearray(self._raw_header)
        struct.pack_into("<I", header, SECTION_ENTRY_COUNT_OFFSET, len(self.entries))

        index = bytearray()
        pool = bytearray()
        pool_base = SECTION_HEADER_SIZE + SECTION_INDEX_ENTRY_SIZE * len(self.entries)

        for entry_id, value in self.entries:
            value_offset = pool_base + len(pool)
            encoded, length = _encode_value(self.etype, value)
            pool += encoded
            index += struct.pack("<III", entry_id, value_offset, length)

        return bytes(header) + bytes(index) + bytes(pool)

    def __repr__(self) -> str:
        return f"<Section {self.name!r} {self.etype} entries={len(self.entries)}>"


# ---------------------------------------------------------------------------
# Tr2
# ---------------------------------------------------------------------------
class Tr2:
    """A parsed ``.tr2`` file you can read, edit, and write back."""

    def __init__(self, path: str | Path | None = None, *, data: bytes | None = None):
        if data is None:
            if path is None:
                raise ValueError("provide either path or data=")
            data = Path(path).read_bytes()
        if data[:4] != MAGIC:
            raise ValueError("not a .tr2 file (bad magic)")

        self.path = path
        self._original = data
        self.version = _u16(data, VERSION_OFFSET)
        self.name = _read_cstring(data, FILE_NAME_OFFSET, FILE_NAME_SIZE)
        self._file_header = data[:FILE_HEADER_SIZE]
        self._table_offset = _u32(data, SECTION_TABLE_OFFSET_FIELD)
        self._section_count = _u32(data, SECTION_COUNT_FIELD)
        self.sections: list[Section] = []
        # original (index, offset) per section, to preserve placement on rebuild
        self._orig_meta: list[tuple[int, int]] = []
        self._parse(data)

    # -- parsing ----------------------------------------------------------
    def _parse(self, data: bytes) -> None:
        offset = self._table_offset
        records = []
        for _ in range(self._section_count):
            index = _u32(data, offset)
            sec_off = _u32(data, offset + 4)
            size = _u32(data, offset + 12)
            records.append((index, sec_off, size))
            offset += SECTION_TABLE_ENTRY_SIZE

        for index, sec_off, size in records:
            name = _read_cstring(data, sec_off, SECTION_NAME_SIZE)
            etype = _read_cstring(data, sec_off + SECTION_TYPE_OFFSET, SECTION_TYPE_SIZE)
            sec = Section(name, etype)
            sec._raw_header = data[sec_off:sec_off + SECTION_HEADER_SIZE]
            sec._raw_body = data[sec_off + SECTION_HEADER_SIZE:sec_off + size]

            count = _u32(data, sec_off + SECTION_ENTRY_COUNT_OFFSET)
            idx = sec_off + SECTION_HEADER_SIZE
            for _ in range(count):
                entry_id = _u32(data, idx)
                value_offset = _u32(data, idx + 4)
                value_length = _u32(data, idx + 8)
                idx += SECTION_INDEX_ENTRY_SIZE
                value = _decode_value(data, etype, sec_off + value_offset, value_length)
                sec.entries.append([entry_id, value])

            self.sections.append(sec)
            self._orig_meta.append((index, sec_off))

    # -- lookup -----------------------------------------------------------
    def __contains__(self, name: str) -> bool:
        return any(s.name == name for s in self.sections)

    def get(self, name: str) -> Section:
        for s in self.sections:
            if s.name == name:
                return s
        raise KeyError(name)

    def section_names(self) -> list[str]:
        return [s.name for s in self.sections]

    def read(self, name: str) -> dict[int, Any]:
        """Return ``{id: value}`` for a section."""
        return self.get(name).as_dict()

    def ids(self, name: str) -> list[int]:
        return self.get(name).ids()

    def value(self, name: str, entry_id: int, default: Any = None) -> Any:
        return self.get(name).value(entry_id, default)

    # -- editing ----------------------------------------------------------
    def set(self, name: str, entry_id: int, value: Any) -> None:
        """Convenience: ``t.set("WordList", 29, "新語")``."""
        self.get(name).set_value(entry_id, value)

    # -- building / saving ------------------------------------------------
    def build(self) -> bytes:
        out = bytearray(self._file_header)

        # pad to the section table position, then reserve the table
        if len(out) < self._table_offset:
            out += b"\x00" * (self._table_offset - len(out))
        table_pos = len(out)
        out += b"\x00" * (SECTION_TABLE_ENTRY_SIZE * len(self.sections))

        rebuilt_meta: list[tuple[int, int, int]] = []   # (orig_index, offset, size)
        for i, sec in enumerate(self.sections):
            orig_index, orig_offset = self._orig_meta[i]
            # preserve each section's original start offset where possible
            if len(out) < orig_offset:
                out += b"\x00" * (orig_offset - len(out))
            sec_offset = len(out)
            block = sec.to_bytes()
            out += block
            rebuilt_meta.append((orig_index, sec_offset, len(block)))

        # write the section table
        pos = table_pos
        for orig_index, sec_offset, size in rebuilt_meta:
            struct.pack_into("<IIIII", out, pos,
                             orig_index, sec_offset, SECTION_TABLE_HEADER_SIZE, size, size)
            pos += SECTION_TABLE_ENTRY_SIZE

        # pad to the original total length (the game expects a fixed-size file)
        if len(out) < len(self._original):
            out += b"\x00" * (len(self._original) - len(out))
        return bytes(out)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.build())

    def round_trips(self) -> bool:
        """True if rebuilding an unmodified file reproduces the input byte-for-byte."""
        return self.build() == self._original

    # -- creation ---------------------------------------------------------
    @classmethod
    def from_template(cls, path: str | Path) -> "Tr2":
        """Load ``path`` but clear every section's entries, giving you an empty
        file with the exact same section names / types / placement to populate."""
        t = cls(path)
        for sec in t.sections:
            sec.entries = []
            sec.dirty = True
        return t

    # -- reporting --------------------------------------------------------
    def summary(self) -> None:
        print(f"== {self.name!r}  sections={len(self.sections)}  size={len(self._original)} ==")
        for s in self.sections:
            print(f"  {s.name:34s} {s.etype:9s} entries={len(s.entries)}")

    def __repr__(self) -> str:
        return f"<Tr2 {self.name!r} sections={len(self.sections)}>"


# ---------------------------------------------------------------------------
# Misc.tr2 word-list convenience layer
# ---------------------------------------------------------------------------
def load_words(path: str | Path = "Misc.tr2") -> list[dict[str, Any]]:
    """Join Misc.tr2's parallel sections into a list of word records."""
    t = Tr2(path)
    words = t.read("WordList")
    yomi = t.read("YOMI")
    hits = t.read("SINGLEHITS") if "SINGLEHITS" in t else {}
    ranks = t.read("WORD_RANK") if "WORD_RANK" in t else {}
    return [
        {
            "id": wid,
            "term": words[wid],
            "yomi": yomi.get(wid, ""),
            "single_hits": hits.get(wid),
            "rank": WORD_RANK_LABELS.get(ranks.get(wid), ranks.get(wid)),
        }
        for wid in sorted(words)
    ]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        Tr2(sys.argv[1]).summary()
    else:
        print(__doc__)
