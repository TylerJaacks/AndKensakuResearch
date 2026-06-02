"""
tr2.py - Parser + byte-exact rebuilder/editor for And-Kensaku (アンド検索, Wii)
.tr2 word-data files.  LITTLE-ENDIAN throughout.

Design for safe editing: each section keeps its ORIGINAL raw bytes. build()
re-emits unmodified sections verbatim and only re-serializes sections you edit.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, TypeAlias

FILE_HEADER_SIZE = 0x40
SECTION_HEADER_SIZE = 0x80
SECTION_TABLE_ENTRY_SIZE = 20
SECTION_TABLE_HEADER_SIZE = 0x14
SECTION_COUNT_OFFSET = 0x3C
SECTION_TABLE_OFFSET = 0x38
VERSION_OFFSET = 0x06
FILE_NAME_OFFSET = 0x08
FILE_NAME_SIZE = 32
SECTION_NAME_SIZE = 32
SECTION_TYPE_OFFSET = 0x40
SECTION_TYPE_SIZE = 16
SECTION_ENTRY_COUNT_OFFSET = 0x7C
SECTION_INDEX_ENTRY_SIZE = 12

TR2_MAGIC = b".tr2"
ASCII_ENCODING = "ascii"
UTF8_TYPE = "UTF-8"
UTF16LE_TYPE = "UTF-16LE"
UTF16LE_ENCODING = "utf-16-le"
DECODE_ERRORS = "replace"

Entry: TypeAlias = list[Any]
SectionMeta: TypeAlias = tuple[int, int, int, int, int]
ScalarSpec: TypeAlias = tuple[int, str]

_SCALAR_TYPES: dict[str, ScalarSpec] = {
    "INT8": (1, "<b"),
    "UINT8": (1, "<B"),
    "INT16": (2, "<h"),
    "UINT16": (2, "<H"),
    "INT32": (4, "<i"),
    "UINT32": (4, "<I"),
    "FLOAT": (4, "<f"),
    "INT": (4, "<i"),
}
DEFAULT_SCALAR: ScalarSpec = (4, "<i")

WORD_RANK_LABELS = {
    0: "S",
    1: "A",
    2: "B",
    3: "C",
    4: "D",
    5: "E",
}


def _u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _decode_c_string(
        data: bytes | bytearray,
        offset: int,
        size: int,
        encoding: str = ASCII_ENCODING,
) -> str:
    raw_value = data[offset: offset + size].split(b"\0", 1)[0]
    return raw_value.decode(encoding, DECODE_ERRORS)


def _read_file(path: str | Path) -> bytes:
    with open(path, "rb") as file:
        return file.read()


def _write_file(path: str | Path, data: bytes) -> None:
    with open(path, "wb") as file:
        file.write(data)


class Section:
    def __init__(self, name: str, element_type: str):
        self.name = name
        self.etype = element_type
        self.entries: list[Entry] = []
        self._raw_header: bytes | None = None
        self._raw_body: bytes | None = None
        self.dirty = False

    def is_str(self) -> bool:
        return self.etype.startswith("UTF")

    def set_value(self, entry_id: int, value: Any) -> None:
        for entry in self.entries:
            if entry[0] == entry_id:
                entry[1] = value
                self.dirty = True
                return

        self.entries.append([entry_id, value])
        self.entries.sort(key=lambda e: e[0])
        self.dirty = True

    def delete(self, entry_id: int) -> None:
        self.entries = [entry for entry in self.entries if entry[0] != entry_id]
        self.dirty = True

    @property
    def raw_header(self):
        return self._raw_header

    @property
    def raw_body(self):
        return self._raw_body


def _write_section_table(
        output: bytearray,
        table_position: int,
        section_meta: list[SectionMeta],
) -> None:
    offset = table_position

    for section_index, section_offset, header_size, size, size2 in section_meta:
        struct.pack_into(
            "<IIIII",
            output,
            offset,
            section_index,
            section_offset,
            header_size,
            size,
            size2,
        )
        offset += SECTION_TABLE_ENTRY_SIZE


def _encode_value(element_type: str, value: Any) -> tuple[bytes, int]:
    if element_type == UTF8_TYPE:
        encoded = value.encode("utf-8")
        return encoded + b"\x00", len(encoded)

    if element_type == UTF16LE_TYPE:
        encoded = value.encode(UTF16LE_ENCODING)
        return encoded + b"\x00", len(encoded)

    scalar_width, scalar_format = _SCALAR_TYPES.get(element_type, DEFAULT_SCALAR)
    return struct.pack(scalar_format, value), scalar_width


# noinspection PyTypeChecker
def _section_bytes(section: Section) -> bytes:
    if not section.dirty and section._raw_body is not None:
        return bytes(section.raw_header) + bytes(section.raw_body)

    if section.raw_header is None:
        raise ValueError(f"Section {section.name!r} has no raw header to rebuild from.")

    section.entries.sort(key=lambda entry: entry[0])

    header = bytearray(section.raw_header)
    struct.pack_into("<I", header, SECTION_ENTRY_COUNT_OFFSET, len(section.entries))

    index = bytearray()
    value_pool = bytearray()
    value_pool_base = SECTION_HEADER_SIZE + SECTION_INDEX_ENTRY_SIZE * len(section.entries)

    for entry_id, value in section.entries:
        value_offset = value_pool_base + len(value_pool)
        encoded_value, value_length = _encode_value(section.etype, value)
        value_pool += encoded_value
        index += struct.pack("<III", entry_id, value_offset, value_length)

    return bytes(header) + bytes(index) + bytes(value_pool)


class Tr2:
    def __init__(self, path: str | Path | None = None, data: bytes | None = None):
        if data is None:
            if path is None:
                raise ValueError("Either path or data must be provided.")
            data = _read_file(path)

        self.path = path
        self.d = data

        if self.d[:4] != TR2_MAGIC:
            raise ValueError("bad magic")

        self.version = _u16(self.d, VERSION_OFFSET)
        self.name = _decode_c_string(self.d, FILE_NAME_OFFSET, FILE_NAME_SIZE)
        self._sec_off = _u32(self.d, SECTION_TABLE_OFFSET)
        self._sec_count = _u32(self.d, SECTION_COUNT_OFFSET)
        self._file_header = self.d[:FILE_HEADER_SIZE]
        self.sections: list[Section] = []
        self._sec_meta: list[SectionMeta] = []

        self._parse()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tr2):
            return NotImplemented

        return self.build() == other.build()

    def _parse(self) -> None:
        self._sec_meta = self._parse_section_table()

        for section_meta in self._sec_meta:
            section = self._parse_section(section_meta)
            self.sections.append(section)

    def _parse_section_table(self) -> list[SectionMeta]:
        section_table: list[SectionMeta] = []
        offset = self._sec_off

        for _ in range(self._sec_count):
            section_table.append(
                (
                    _u32(self.d, offset),
                    _u32(self.d, offset + 4),
                    _u32(self.d, offset + 8),
                    _u32(self.d, offset + 12),
                    _u32(self.d, offset + 16),
                )
            )
            offset += SECTION_TABLE_ENTRY_SIZE

        return section_table

    def _parse_section(self, section_meta: SectionMeta) -> Section:
        _, section_offset, _, section_size, _ = section_meta

        section_name = _decode_c_string(
            self.d,
            section_offset,
            SECTION_NAME_SIZE,
        )
        element_type = _decode_c_string(
            self.d,
            section_offset + SECTION_TYPE_OFFSET,
            SECTION_TYPE_SIZE,
        )

        section = Section(section_name, element_type)
        section._raw_header = self.d[section_offset: section_offset + SECTION_HEADER_SIZE]
        section._raw_body = self.d[section_offset + SECTION_HEADER_SIZE: section_offset + section_size]

        entry_count = _u32(self.d, section_offset + SECTION_ENTRY_COUNT_OFFSET)
        index_offset = section_offset + SECTION_HEADER_SIZE

        for _ in range(entry_count):
            entry_id = _u32(self.d, index_offset)
            value_offset = _u32(self.d, index_offset + 4)
            value_length = _u32(self.d, index_offset + 8)
            index_offset += SECTION_INDEX_ENTRY_SIZE

            value = self._decode_value(
                element_type,
                section_offset + value_offset,
                value_length,
            )
            section.entries.append([entry_id, value])

        return section

    def _decode_value(self, element_type: str, value_offset: int, value_length: int) -> Any:
        if element_type == UTF8_TYPE:
            return self.d[value_offset: value_offset + value_length].decode(
                "utf-8",
                DECODE_ERRORS,
            )

        if element_type == UTF16LE_TYPE:
            return self.d[value_offset: value_offset + value_length].decode(
                UTF16LE_ENCODING,
                DECODE_ERRORS,
            )

        _, scalar_format = _SCALAR_TYPES.get(element_type, DEFAULT_SCALAR)
        return struct.unpack_from(scalar_format, self.d, value_offset)[0]

    @staticmethod
    def _pad_to_offset(output: bytearray, target_offset: int) -> None:
        if len(output) < target_offset:
            output += b"\x00" * (target_offset - len(output))

    def get(self, name: str) -> Section:
        for section in self.sections:
            if section.name == name:
                return section

        raise KeyError(name)

    def read(self, name: str) -> dict[int, Any]:
        return {entry_id: value for entry_id, value in self.get(name).entries}

    def build(self) -> bytes:
        output = bytearray(self._file_header)

        self._pad_to_offset(output, self._sec_off)

        section_table_position = len(output)
        output += b"\x00" * (SECTION_TABLE_ENTRY_SIZE * len(self.sections))

        rebuilt_meta = []

        for section_index, section in enumerate(self.sections):
            original_section_offset = self._sec_meta[section_index][1]
            self._pad_to_offset(output, original_section_offset)

            section_offset = len(output)
            section_block = _section_bytes(section)
            output += section_block

            original_section_index = self._sec_meta[section_index][0]
            rebuilt_meta.append(
                (
                    original_section_index,
                    section_offset,
                    SECTION_TABLE_HEADER_SIZE,
                    len(section_block),
                    len(section_block),
                )
            )

        _write_section_table(output, section_table_position, rebuilt_meta)

        if self.path:
            self._pad_to_offset(output, len(self.d))

        return bytes(output)

    def save(self, path: str | Path) -> None:
        _write_file(path, self.build())

    def summary(self) -> None:
        print(f"== {self.path} name={self.name!r} sections={len(self.sections)} ==")

        for section in self.sections:
            print(f"  {section.name:34s} {section.etype:9s} entries={len(section.entries)}")


# noinspection PyTypeChecker
def load_words(path: str | Path = "Misc.tr2") -> list[dict[str, Any]]:
    tr2_file = Tr2(path)

    words = tr2_file.read("WordList")
    yomi = tr2_file.read("YOMI")
    hits = tr2_file.read("SINGLEHITS")
    ranks: dict[int, Any] = tr2_file.read("WORD_RANK")

    return [
        {
            "id": word_id,
            "term": words[word_id],
            "yomi": yomi.get(word_id, ""),
            "single_hits": hits.get(word_id),
            "rank": WORD_RANK_LABELS.get(ranks.get(word_id), ranks.get(word_id)),
        }
        for word_id in sorted(words)
    ]

def dump_words(path: str | Path = "Misc.tr2") -> None:
    import json

    words = load_words(path)
    with open("words.json", "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

def TR2(path: str | Path) -> Tr2:
    return Tr2(path)