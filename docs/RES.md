# RES format overview
A documenation of the the game's archive/container.
This uses [GEBCS](https://github.com/gil-unx/GEBCS) tool for documenation. use that want to know about RES file.

This document covers
1. [What RES files are](#1-what-res-files-are)
2. [Container Format](#2-container-format)
3. [File Struction Information](#3-file-structure-information)
4. [Data Example & Possible Custom Content](#4-data-structure-example-0xx_gameresrz)

## 1. What RES files are
Shift's proprietary format on some games, but this is commonly seen in GOD EATER games that they made (before GOD EATER 3).
What And-Kensaku (*.res) file uses is related to the an earlier version of GOD EATER *(mix of GOD EATER BURST and early GOD EATER 2 `*.res` format)* but without package.rdp or another separate containers, and all are stored in the res file itself. Despite the game targeting big-endian PowerPC hardware, all values/data are still little-endian. Note that the res files compressed in LZ11 `(0x11)`, decompress the res file first to make it understandable.


## 2. Container format
```
+-----------------------------+
|       File header (0x20)    |
+-----------------------------+
|       Group Data area       |   8 bytes each per group count
+-----------------------------+
|  TOC (fixed start at 0x60)  |   32 bytes per TOC count
+-----------------------------+
```

## 3. File Structure Information
### Header
| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 4 | Magic | header is always `Pres`  or `0x73657250`.|
| 0x04 | 4 | GroupOffset | where the Group is is located.|
| 0x08 | 4 | GroupCount | how many groups are available/present.|
| 0x0C | 4 | Checksum | checksum of the RES file. always required.|
| 0x10 | 16 | Padding | Not used here, only used by the game to fill that area for other purposes or purposely empty.|
### Group 
| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 4 | Offset | location of a specfic TOC is located.|
| 0x04 | 4 | Count | how may TOC is in that offset `(count * 32)`.|

*Notes: you can get each Group by 8 bytes since they start at 0x20*

### TOC 
| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| 0x00 | 4 | Offset | location of that data.|
| 0x04 | 4 | Size | size of that data.|
| 0x08 | 4 | OffsetName | location of one/multiple offset that also redirects to the name set to that data (UTF-8), **GEBCS** refer to this as ElementName.|
| 0x0C | 4 | Chunkname | how many offsets present in *OffsetName*.|
| 0x10 | 16 | Padding | Not used here, only used by the game to fill that area for other purposes.|


## 4. Data Structure Example (0xx_game.res.rz)
```
0x00: 50 72 65 73 20 00 00 00 07 00 00 00 81 57 06 00 // Magic + GroupOffset GroupCount + Checksum
0x10: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 // Group Area (8 bytes per pair/count. note that some area have empty groups)
0x20: 00 00 00 00 00 00 00 00 00 01 00 00 01 00 00 00 
0x30: 60 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 
0x40: 00 00 00 00 00 00 00 00 80 00 00 00 02 00 00 00 
0x50: C0 00 00 00 02 00 00 00 00 00 00 00 00 00 00 00 
0x60: 20 01 00 00 60 05 00 00 80 06 00 00 03 00 00 00 // TOC Area + TOC Structure
0x70: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 
0x80: C0 06 00 00 00 00 00 00 C0 06 00 00 01 00 00 00 
0x90: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 
0xA0: E0 06 00 00 10 00 00 00 20 07 00 00 01 00 00 00 
0xB0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 
0xC0: 40 07 00 00 14 00 00 00 60 07 00 00 01 00 00 00 
0xD0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 
0xE0: 80 07 00 00 15 00 00 00 A0 07 00 00 01 00 00 00 
0xF0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 
0x100: C0 07 00 00 00 00 00 00 E0 07 00 00 03 00 00 00 
0x110: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
// after TOC, it'll be chunk of data's and ElementName

//Example ElementName
0x680: 8C 06 00 00 9C 06 00 00 A0 06 00 00 49 44 30 78
0x690: 78 5F 67 61 6D 65 5F 74 65 78 74 00 74 72 32 00
```

## Possible Custom Content
- If you think you can add a file(s) in a RES file. Yes, you can add files if you want to create your own custom content or any kind of modding. but it'll take lots of time if you don't have an automation tool for that to sort out, and you'll need to do manual HEX editing for that.
- Some files within RES file usually have some specific calling module by mentioning the modules in a specific plain text and showing the directory path of that module.


## Status of the documentation
Overall, everything is okay. the tool is already out there and the source code only needs a few minor edits and it will support the `*.res` file And-Kensaku uses.
