# Z-machine Header Reference

## Quick Reference for Z-machine V3 Header (64 bytes)

This is what your compiler must generate at the start of every .z3 file.

```
Offset  Size  Name                 Notes
------  ----  -------------------  -----------------------------------------
0       1     Version              Must be 0x03 for Z-machine V3
1       1     Flags 1              Bit flags for interpreter settings
2-3     2     Release number       Your game's release number (e.g., 119)
4-5     2     High memory base     Start of high memory (code/strings)
6-7     2     Initial PC           Where execution starts (routine address)
8-9     2     Dictionary address   Location of dictionary table
10-11   2     Object table addr    Location of object table
12-13   2     Global vars addr     Location of global variables (480 bytes)
14-15   2     Static memory base   Start of static memory
16-17   2     Flags 2              More interpreter flags
18-23   6     Serial number        Date: YYMMDD (ASCII, e.g., "880429")
24-25   2     Abbreviations addr   Location of abbreviations table
26-27   2     File length          Actual length / 2 (for V3)
28-29   2     Checksum             Sum of all bytes from 0x40 onwards
30-63   34    Reserved             Mostly zeros in V3
```

## Example: Zork I Header

```
Offset  Hex Value    Decimal    Meaning
------  ---------    -------    --------------------------------
0       03           3          Z-machine version 3
1       00           0          Flags 1: no special features
2-3     00 77        119        Release 119
4-5     4b 54        19284      High memory starts at byte 19284
6-7     50 d5        20693      Start execution at byte 20693
8-9     38 99        14489      Dictionary at byte 14489
10-11   03 e6        998        Object table at byte 998
12-13   02 b0        688        Globals at byte 688
14-15   2c 12        11282      Static memory starts at byte 11282
16-17   00 40        64         Flags 2
18-23   "880429"     -          April 29, 1988
24-25   01 f0        496        Abbreviations at byte 496
26-27   a9 9b        43419      File length = 43419 * 2 = 86838 bytes
28-29   bf 44        48964      Checksum
```

## Example: Planetfall Header

```
Offset  Hex Value    Decimal    Meaning
------  ---------    -------    --------------------------------
0       03           3          Z-machine version 3
2-3     00 25        37         Release 37
4-5     51 b8        20920      High memory starts at byte 20920
6-7     56 bb        22203      Start execution at byte 22203
8-9     3f 42        16194      Dictionary at byte 16194
10-11   02 b2        690        Object table at byte 690
12-13   22 4d        8781       Globals at byte 8781
14-15   31 6d        12653      Static memory starts at byte 12653
```

## Memory Layout

For a typical V3 game, memory is divided into:

```
0x0000 ┌─────────────────────┐
       │  Header (64 bytes)  │
       ├─────────────────────┤
       │  Abbreviations      │
       │  Global Variables   │
       │  Object Table       │
       │  Property Defaults  │
       │  Objects            │
       │     (Dynamic        │
       │      Memory)        │
0x????  ├─────────────────────┤ ← Static memory base
       │  Dictionary         │
       │  Preloaded Strings  │
       │  Initial States     │
       │     (Static         │
       │      Memory)        │
0x????  ├─────────────────────┤ ← High memory base
       │  Code (Routines)    │
       │  Packed Strings     │
       │     (High           │
       │      Memory)        │
0x????  └─────────────────────┘ End of file
```

## Critical Constraints

### Memory Regions
- **Dynamic memory**: 0x0000 to (static base - 1)
  - Must include header, abbreviations, globals, object table
  - Writable at runtime
  - Max ~16KB for V3

- **Static memory**: (static base) to (high memory - 1)
  - Read-only at runtime
  - Contains dictionary, initial values
  - Usually a few KB

- **High memory**: (high memory base) to end of file
  - Never directly writable
  - Contains routines and packed strings
  - Most of the file

### Addresses Must Be Valid
- All table addresses (dict, objects, globals, etc.) must point within file
- Initial PC must point to a valid routine in high memory
- Addresses must not overlap inappropriately

### File Length
- V3 has 128KB limit (0x20000 bytes)
- Header stores (actual length / 2)
- Example: 86838 bytes → store 0xa99b (43419)

### Checksum
- Sum of all bytes from offset 0x40 (byte 64) onwards
- Stored as 16-bit value at offset 28-29
- Overflow is normal (truncate to 16 bits)

## Flags

### Flags 1 (byte 1)
```
Bit  Meaning (V3)
---  ---------------
0    Not used
1    Status line: 0=score/turns, 1=hours/minutes
2    Story file split across disks
3    Tandy computer
4    Status line not available
5    Screen splitting available
6    Variable-pitch font default
7    Not used
```

Usually 0x00 for most games.

### Flags 2 (bytes 16-17)
```
Bit  Meaning (V3)
---  ---------------
0    Transcripting on
1    Force fixed-pitch printing
...
```

Usually 0x0040 or similar.

## Common Mistakes

### 1. Wrong Version
```
Error: 00 00 00 77 4b 54...
       ^^
Should be 03 for V3!
```

### 2. File Length Wrong
```
Error: File is 86838 bytes but header says:
       26-27: 00 01 (length = 1 * 2 = 2 bytes)

Should be: a9 9b (43419 * 2 = 86838 bytes)
```

### 3. Invalid PC
```
Error: Initial PC 0x50d5 (20693)
       But file is only 512 bytes!

PC must point to valid code in high memory.
```

### 4. Overlapping Tables
```
Error: Object table at 0x03e6
       But globals at 0x02b0 (size 480 bytes)
       Globals end at 0x0490

Object table should start after globals end.
```

### 5. High Memory Not High Enough
```
Error: High memory base: 0x0100
       But dictionary at 0x3899

Dictionary is in static memory, which must be
before high memory base.
```

## Validation Checklist

When generating a header:

- [ ] Version is 0x03
- [ ] All addresses are within file bounds
- [ ] High memory base > static base > dynamic structures
- [ ] File length = (header value * 2)
- [ ] Initial PC points to valid routine
- [ ] Global vars address has room for 480 bytes
- [ ] Object table doesn't overlap other structures
- [ ] Dictionary is in static memory region
- [ ] Checksum calculated correctly
- [ ] Serial number is 6 ASCII digits (YYMMDD)

## Tools to Check

```bash
# View header
xxd -l 64 your-game.z3

# Inspect with tool
./inspect-zcode.sh your-game.z3

# Compare with reference
./inspect-zcode.sh your-game.z3 reference.z3

# Verify it's valid
./verify-zfiles.sh
```

## Reference Headers (working examples)

See these files for known-good headers:
- `zork1/COMPILED/zork1.z3` - Classic example
- `enchanter/COMPILED/enchanter.z3` - Different layout
- `zilf/test/Dezapf.Tests/Resources/hello.z3` - Minimal example

Use `xxd -l 64 <file>` to examine them.
