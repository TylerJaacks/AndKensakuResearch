# TR2 Files

There are 6 total TR2 files on the And-Kensaku disc and  are all located in the upd/ folder on the root of the DVD.

I have provded the default TR2 files in the tr2/ directory in this repository.

## Double00.tr2

## Double01.tr2

## Double02.tr2

## Misc.tr2

### Physical File Structure

The TR2 format is a sectioned container with the following byte-level layout:

```cpp
// Physical layout of Misc.tr2 (1,572,864 bytes / 0x180000)
struct TR2File
{
  // ===== File Header (64 bytes @ 0x00) =====
  char     magic[4];                    // 0x00: ".tr2"
  uint16_t version;                     // 0x04: Format version
  char     name[32];                    // 0x06: Null-terminated filename
  uint32_t section_table_offset;        // 0x38: Always 0x40 (64)
  uint32_t section_count;               // 0x3C: 41 for Misc.tr2
  // Padding to 64 bytes
  
  // ===== Section Table (820 bytes @ 0x40) =====
  struct SectionTableEntry {
    uint32_t section_index;             // Original section index
    uint32_t section_offset;            // Absolute offset to section
    uint32_t header_size;               // Always 0x14 (20)
    uint32_t section_size;              // Total section size
    uint32_t section_size2;             // Duplicate of section_size
  } section_table[41];                  // 20 bytes × 41 = 820 bytes
  
  // Padding (12 bytes @ 0x364)
  
  // ===== Section Data (starts @ 0x380 / 896) =====
  // Each section follows this structure:
  struct Section {
    // --- Section Header (128 bytes / 0x80) ---
    char     section_name[32];          // 0x00: Null-terminated name
    char     padding1[32];              // 0x20: Reserved/padding
    char     element_type[16];          // 0x40: "INT32", "UTF-8", etc.
    char     padding2[44];              // 0x50: Reserved/padding
    uint32_t entry_count;               // 0x7C: Number of entries
    
    // --- Entry Index (12 bytes per entry) ---
    struct IndexEntry {
      uint32_t entry_id;                // Unique entry identifier
      uint32_t value_offset;            // Offset to value (from section start)
      uint32_t value_length;            // Length of value in bytes
    } index[entry_count];
    
    // --- Data Pool (variable length) ---
    // Raw value data (scalars or null-terminated strings)
    uint8_t data_pool[...];
  } sections[41];
  
  // ===== Padding (284,208 bytes) =====
  // Zero-filled padding from end of last section (0x13A7F0) to 0x180000
};
```

### Logical Section Schema

The 41 sections in `Misc.tr2` contain the following data:

```cpp
// Logical view (what data exists, not how it's stored)
struct MiscData
{
  int32_t  KAKUNOU_STAGE                      entries=120
  int32_t  KAKUNOU_TEHUDA                     entries=120
  int32_t  KAKUNOU_MOKUHYOU                   entries=120
  int32_t  KAKUNOU_MOKUHYOU_REV               entries=120
  char16_t KAKUNOU_SUBJECT                    entries=120  // UTF-16LE
  int8_t   KAKUNOU_STARTPOS                   entries=120
  char     KAKUNOU_MAXHITS                    entries=120  // UTF-8
  char     KAKUNOU_SUCCESSHITS                entries=120  // UTF-8
  char     KAKUNOU_SUCCESSHITS_REV            entries=120  // UTF-8
  char     KAKUNOU_MINHITS                    entries=120  // UTF-8
  int8_t   KAKUNOU_KEYPOS                     entries=120
  int8_t   KAKUNOU_STAGE_ATTR                 entries=120
  uint16_t STEP_WORDS                         entries=18
  uint16_t PAIRHITS_DIST                      entries=2
  char     SHOOTING_STAGE_THEME               entries=6    // UTF-8
  char     SHOOTING_STAGE_WORDS_1             entries=6    // UTF-8
  char     SHOOTING_STAGE_WORDS_2             entries=6    // UTF-8
  char     SHOOTING_STAGE_WORDS_3             entries=6    // UTF-8
  char     SHOOTING_STAGE_WORDS_4             entries=6    // UTF-8
  char     SHOOTING_STAGE_WORDS_5             entries=6    // UTF-8
  char     SHOOTING_STAGE_WORDS_6             entries=6    // UTF-8
  uint16_t SHOOTING_STAGE_HITS                entries=6
  char     WordList                           entries=3249 // UTF-8
  char     YOMI                               entries=3249 // UTF-8
  char     MainGenreList                      entries=16   // UTF-8
  char     SubGenreList                       entries=39   // UTF-8
  uint8_t  SUBGENRE_ATTR                      entries=39
  uint8_t  GenreTable                         entries=14
  uint32_t Serial                             entries=1
  char     QUEST_MAXHP                        entries=1    // UTF-8
  uint8_t  NEW_THEME_WORD_RATE                entries=1
  uint32_t SUB_GENRE_A                        entries=3249
  uint32_t SUB_GENRE_B                        entries=3249
  uint32_t SUB_GENRE_C                        entries=3249
  uint32_t SUB_GENRE_D                        entries=3249
  uint8_t  WORD_RANK                          entries=3249
  uint8_t  ATTR_FLAG                          entries=3249
  int16_t  DR_INDEX                           entries=3249
  int16_t  DR_AVERAGE                         entries=3249
  uint16_t SINGLEHITS                         entries=3249
  uint16_t COUPLEWORDS                        entries=3249
};
```

**Note**: Entries within each section are stored as key-value pairs (entry_id → value), not as sequential arrays. String types (UTF-8, UTF-16LE) are variable-length and null-terminated.

## Phrases.tr2

## Puzzle.tr2