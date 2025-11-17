# Z-Machine Format Specification

## 1. Introduction

### 1.1 Overview
The Z-machine is a virtual machine designed by Infocom in the late 1970s to enable cross-platform interactive fiction games. It executes compiled bytecode called Z-code, stored in story files with extensions .z1 through .z8 (corresponding to Z-machine versions 1-8).

### 1.2 Historical Context
- **Developed**: Late 1970s at Infocom
- **Purpose**: Platform-independent game distribution
- **Original Name**: ZIP (Zork Interpreter Program)
- **Legacy**: Over 100 commercial games, modern interpreters still active

### 1.3 Version History
- **Version 1-2**: Early Zork games (rare, 1979-1981)
- **Version 3**: Most Infocom games, 128KB limit (1982-1988)
- **Version 4**: Extended features, 256KB limit (1984-1988)
- **Version 5**: Color, sound, undo support, 256KB limit (1986-1988)
- **Version 6**: Advanced graphics, mouse input, proportional fonts, 256KB limit (1988-1989)
- **Version 7**: Created 1995 by Graham Nelson, never widely used, 512KB limit
- **Version 8**: Created 1995 by Graham Nelson, modern standard for large games, 512KB limit

### 1.4 Standards Document
The authoritative specification is "The Z-Machine Standards Document" by Graham Nelson (v1.1, February 24, 2014), available at inform-fiction.org.

## 2. Memory Architecture

### 2.1 Memory Organization

The Z-machine memory consists of a linear array of bytes from address $00000 upward, divided into three regions:

```
+------------------+  $00000
| Dynamic Memory   |  Read/Write
|   (includes      |  Minimum 64 bytes
|    header)       |  Max size in header $0E
+------------------+  Header word $0E
| Static Memory    |  Read-only
|                  |  Ends at $0FFFF or file end
+------------------+  Header word $04 or $0FFFF
| High Memory      |  Routines and strings
|                  |  Not directly accessible
|                  |  (call/print only)
+------------------+  End of file
```

### 2.2 Memory Regions

#### 2.2.1 Dynamic Memory
- **Start**: $00000
- **End**: Address specified in header word at $0E
- **Access**: Read and write
- **Contents**: Header (first 64 bytes), objects, globals, writable data
- **Minimum Size**: 64 bytes

#### 2.2.2 Static Memory
- **Start**: Immediately after dynamic memory
- **End**: Lesser of story file end or $0FFFF
- **Access**: Read-only (via `loadb` and `loadw` opcodes)
- **Contents**: Dictionary, property tables, static strings

#### 2.2.3 High Memory
- **Start**: Address in header word at $04
- **End**: Story file end
- **Access**: Indirect only (packed addresses for routines/strings)
- **Contents**: Compiled routines, compressed strings

### 2.3 Address Types

#### 2.3.1 Byte Addresses
- Standard linear addresses
- Range: 0 to end of static memory
- Used for: Direct memory access

#### 2.3.2 Word Addresses
- Reference even addresses in bottom 128KB
- Calculation: word address × 2 = byte address
- Used for: Abbreviation tables, certain tables

#### 2.3.3 Packed Addresses
Version-specific encoding for high memory:

| Version | Routine Formula | String Formula |
|---------|----------------|----------------|
| 1-3     | packed × 2     | packed × 2     |
| 4-5     | packed × 4     | packed × 4     |
| 6-7     | packed × 4 + R_O | packed × 4 + S_O |
| 8       | packed × 8     | packed × 8     |

Where R_O and S_O are offsets from header words $28 and $2A (V6-7 only).

### 2.4 Size Limitations
- **Critical**: Dynamic + Static memory ≤ 64KB - 2 bytes
- **Story File**: Version-dependent maximum (128KB to 512KB)

## 3. Header Format

### 3.1 Header Structure

The header occupies the first 64 bytes of dynamic memory ($00000 to $003F). All multi-byte values are big-endian (most significant byte first).

### 3.2 Header Map

| Offset | Size | Dynamic? | Description |
|--------|------|----------|-------------|
| $00    | 1    | No       | Version number (1-8) |
| $01    | 1    | Varies   | Flags 1 |
| $02-03 | 2    | No       | Release number |
| $04-05 | 2    | No       | High memory base address |
| $06-07 | 2    | No       | Initial program counter (V1-5) / Main routine (V6+) |
| $08-09 | 2    | No       | Dictionary location |
| $0A-0B | 2    | No       | Object table location |
| $0C-0D | 2    | No       | Global variables table location |
| $0E-0F | 2    | No       | Static memory base address |
| $10-11 | 2    | Varies   | Flags 2 |
| $12-17 | 6    | No       | Serial number (ASCII YYMMDD) |
| $18-19 | 2    | No       | Abbreviations table location (V2+) |
| $1A-1B | 2    | No       | File length ÷ (2/4/8 by version) |
| $1C-1D | 2    | No       | File checksum (sum of all bytes except header) |
| $1E    | 1    | Yes      | Interpreter number |
| $1F    | 1    | Yes      | Interpreter version |
| $20    | 1    | Yes      | Screen height (lines) (V4+) |
| $21    | 1    | Yes      | Screen width (characters) (V4+) |
| $22-23 | 2    | Yes      | Screen width (units) (V5+) |
| $24-25 | 2    | Yes      | Screen height (units) (V5+) |
| $26    | 1    | Yes      | Font width/height (V5) / Font height (V6) |
| $27    | 1    | Yes      | Font height (V5) / Font width (V6) |
| $28-29 | 2    | No       | Routines offset ÷ 8 (V6+) |
| $2A-2B | 2    | No       | Static strings offset ÷ 8 (V6+) |
| $2C    | 1    | Yes      | Default background color (V5+) |
| $2D    | 1    | Yes      | Default foreground color (V5+) |
| $2E-2F | 2    | No       | Terminating characters table (V5+) |
| $30-31 | 2    | Yes      | Total width sent to output stream 3 (V6+) |
| $32    | 1    | No       | Standard revision number (V1+) |
| $33    | 1    | No       | Alphabet table address (V5+) |
| $34-35 | 2    | No       | Header extension table (V5+) |

### 3.3 Flags 1 (Byte $01)

Bit meanings vary by version:

#### Versions 1-3:
- Bit 1: Status line type (0=score/turns, 1=hours:minutes)
- Bit 4: Status line not available
- Bit 5: Screen splitting available
- Bit 6: Variable-pitch font default

#### Versions 4+:
- Bit 0: Colors available
- Bit 1: Picture displaying available
- Bit 2: Boldface available
- Bit 3: Italic available
- Bit 4: Fixed-space font available
- Bit 5: Sound effects available
- Bit 7: Timed input available

### 3.4 Flags 2 (Bytes $10-11)

- Bit 0: Transcripting on
- Bit 1: Fixed-pitch font requested
- Bit 2: Request screen redraw (V6)
- Bit 3: Pictures available
- Bit 4: Undo available
- Bit 5: Mouse available
- Bit 6: Colors available
- Bit 7: Sound available
- Bit 8: Menu available

## 4. Object Table

### 4.1 Object Table Structure

Located at the address specified in header $0A, the object table contains:
1. Property defaults table
2. Object tree
3. Property tables (one per object)

### 4.2 Property Defaults Table

**Versions 1-3**: 31 words (62 bytes)
**Versions 4+**: 63 words (126 bytes)

Provides default values for properties not explicitly defined on objects.

### 4.3 Object Tree Format

#### 4.3.1 Versions 1-3 (9 bytes per object)

Maximum 255 objects:

```
Offset  Size  Description
+0      4     Attributes (32 flags, bits 0-31)
+4      1     Parent object number
+5      1     Sibling object number
+6      1     Child object number
+7      2     Property table address
```

#### 4.3.2 Versions 4+ (14 bytes per object)

Maximum 65,535 objects:

```
Offset  Size  Description
+0      6     Attributes (48 flags, bits 0-47)
+6      2     Parent object number
+8      2     Sibling object number
+10     2     Child object number
+12     2     Property table address
```

### 4.4 Object Attributes

Boolean flags (0-31 in V1-3, 0-47 in V4+):
- Bit 0 = attribute 0
- Bit 31/47 = attribute 31/47

Common attributes (by convention):
- Attribute 0-15: Often user-defined
- Others vary by game

### 4.5 Object Tree Relationships

Objects form a parent-child-sibling tree structure:
- **Parent**: Container of this object (0 = no parent)
- **Sibling**: Next object at same level (0 = last sibling)
- **Child**: First child object (0 = no children)

### 4.6 Property Tables

Each object has a property table at the address specified in its object entry.

#### 4.6.1 Property Table Header

```
Byte 0: Text length (number of 2-byte words in object name)
Bytes 1+: Object name (ZSCII encoded text)
```

#### 4.6.2 Property List (Versions 1-3)

Follows object name, terminated by a zero byte:

```
Size byte: 32 × (data_length - 1) + property_number
Data: 1-8 bytes of property data
```

Property number: 0-31 (1-31 valid, 0 = terminator)
Data length: Derived from size byte

#### 4.6.3 Property List (Versions 4+)

More complex encoding:

**Single size byte** (bit 7 = 0):
```
Bit 7: 0
Bit 6: 0=1 byte data, 1=2 bytes data
Bits 5-0: Property number
```

**Double size bytes** (bit 7 = 1):
```
First byte:
  Bit 7: 1
  Bit 6: Reserved (must be 0)
  Bits 5-0: Property number

Second byte:
  Bit 7: Must be 0
  Bits 5-0: Data length (0 means 64 bytes)
```

Properties must appear in descending numerical order.

## 5. Instruction Format

### 5.1 Instruction Structure

```
[Opcode: 1-2 bytes]
[Operand types: 0-2 bytes]
[Operands: 0-8 operands, 1-2 bytes each]
[Store variable: 1 byte, if store instruction]
[Branch offset: 1-2 bytes, if branch instruction]
[Text: variable length, if text instruction]
```

### 5.2 Operand Types

Encoded as 2-bit values:

| Code | Type           | Size    | Range     |
|------|----------------|---------|-----------|
| 00   | Large constant | 2 bytes | 0-65535   |
| 01   | Small constant | 1 byte  | 0-255     |
| 10   | Variable       | 1 byte  | Variable# |
| 11   | Omitted        | 0 bytes | N/A       |

### 5.3 Variable References

Variable operands specify:
- $00: Top of stack (pop)
- $01-$0F: Local variables 1-15
- $10-$FF: Global variables 0-239

### 5.4 Instruction Forms

Determined by opcode byte's top bits:

#### 5.4.1 Long Form ($$00 or $$01 in top 2 bits, except $BE)

```
Bits 7-6: 00 or 01
Bit 5: Opcode number (bottom 5 bits)
Bit 6: First operand type (0=small const, 1=variable)
Bit 5: Second operand type (0=small const, 1=variable)
```

Always 2OP operand count.

#### 5.4.2 Short Form ($$10 in top 2 bits)

```
Bits 7-6: 10
Bits 5-4: Operand type
  00: Large constant (1OP)
  01: Small constant (1OP)
  10: Variable (1OP)
  11: Omitted (0OP)
Bits 3-0: Opcode number
```

#### 5.4.3 Variable Form ($$11 in top 2 bits)

```
Bits 7-6: 11
Bit 5: 0=2OP, 1=VAR
Bits 4-0: Opcode number

Followed by 1-2 type bytes:
  4 operands: 1 type byte (4 × 2-bit type codes)
  5-8 operands: 2 type bytes
```

#### 5.4.4 Extended Form ($BE opcode in V5+)

```
Byte 1: $BE
Byte 2: Opcode number
Bytes 3+: Type bytes and operands (as variable form)
```

### 5.5 Branch Instructions

Many instructions include a conditional branch:

```
Bit 7: Branch polarity (1=branch on true, 0=branch on false)
Bit 6: Branch offset size (1=1 byte, 0=2 bytes)

1-byte offset (bit 6 = 1):
  Bits 5-0: Offset (0-63)

2-byte offset (bit 6 = 0):
  Bits 5-0 of first byte + 8 bits of second byte = 14-bit signed offset
```

Special offsets:
- 0: Return false
- 1: Return true
- Other: Offset from branch instruction end

### 5.6 Store Instructions

Instructions that produce a result include a store variable byte:
- $00: Push to stack
- $01-$0F: Local variable
- $10-$FF: Global variable

## 6. Text Encoding

### 6.1 ZSCII Character Set

ZSCII (Zork Standard Code for Information Interchange) extends ASCII:

- **0**: Null
- **8**: Delete/backspace
- **9-12**: Cursor movement (up, down, left, right)
- **13**: Newline
- **27**: Escape
- **32-126**: Standard ASCII printable characters
- **129-154**: Function keys, keypad (input only)
- **155-251**: Extended characters (via Unicode translation table V5+)
- **252-254**: Mouse/menu events (input only)

### 6.2 Z-Character Encoding

Text is compressed as sequences of 5-bit Z-characters packed into 16-bit words:

```
Word format (big-endian):
Bit 15: End marker (1 = last word of string)
Bits 14-10: First Z-character
Bits 9-5: Second Z-character
Bits 4-0: Third Z-character
```

### 6.3 Alphabet Tables

Three alphabets (A0, A1, A2) provide character mappings:

#### Default Alphabet (Versions 1-4):

**A0** (0-25): ` abcdefghijklmnopqrstuvwxyz`
**A1** (0-25): ` ABCDEFGHIJKLMNOPQRSTUVWXYZ`
**A2** (0-25): ` ^0123456789.,!?_#'"/\-:()`

Z-character 0 = space, 1-5 = special codes, 6-31 = alphabet characters 0-25.

#### Custom Alphabet Table (V5+)

Header word $34 can specify a custom alphabet table address (78 bytes, 3 × 26 characters).

### 6.4 Alphabet Shifts

**Z-characters 4-5**: Shift to next alphabet
- **Versions 1-2**: Permanent shift until another shift character
- **Versions 3+**: Temporary shift (next character only)

**Z-characters 2-3** (V3+): Abbreviations
- Trigger lookup in abbreviations table

### 6.5 Special Encodings

#### ZSCII Escape Sequence

Z-character 6 from A2 followed by two Z-characters:
```
10-bit ZSCII code = (first Z-char << 5) | second Z-char
```

#### Abbreviations (V2+)

Z-characters 1-3 trigger abbreviation expansion:
```
Table index = 32 × (Z-char - 1) + next Z-character
```

Abbreviations table (at header $18) contains word addresses of abbreviated strings.

### 6.6 String Padding

Since the end bit falls every 3 Z-characters, strings are padded (conventionally with Z-character 5) to align with word boundaries.

## 7. Dictionary Format

### 7.1 Dictionary Structure

Located at header word $08:

```
Offset  Size  Description
+0      1     Number of word separators (n)
+1      n     Word separator ZSCII codes
+n+1    1     Entry length (bytes per word)
+n+2    2     Number of entries (signed: positive=search, negative=no search)
+n+4    ...   Dictionary entries
```

### 7.2 Word Separators

Characters that divide words (typically: . , " ? ! ; : ( ))
Space (32) should never be a separator.

### 7.3 Dictionary Entry Format

**Versions 1-3**:
- 4 bytes: Encoded text (6 Z-characters)
- n bytes: Additional data

**Versions 4+**:
- 6 bytes: Encoded text (9 Z-characters)
- n bytes: Additional data

### 7.4 Dictionary Ordering

Entries must be sorted in ascending order of encoded text (treated as a 32-bit or 48-bit number, big-endian). No duplicate encoded texts allowed.

### 7.5 Dictionary Encoding

Words are encoded using standard Z-character encoding, padded with Z-character 5 to fill the entry.

## 8. Routine Format

### 8.1 Routine Header

```
Byte 0: Number of local variables (0-15)

Versions 1-4:
  Bytes 1+: Initial values for locals (2 bytes × local count)

Versions 5+:
  (Locals initialized to 0)
```

### 8.2 Routine Body

Instructions begin immediately after the header. No explicit end marker; routines terminate via return instructions.

### 8.3 Call Stack

Each routine call creates a stack frame containing:
- Return address
- Local variables
- Stack for evaluation
- Result storage location

### 8.4 Entry Points

**Versions 1-5**: Header word $06 contains byte address of first instruction

**Version 6+**: Header word $06 contains packed address of main routine

## 9. Opcode Reference

### 9.1 Opcode Categories

**0OP** (no operands): rtrue, rfalse, print, quit, etc.
**1OP** (1 operand): jz, get_sibling, inc, dec, etc.
**2OP** (2 operands): add, sub, mul, div, je, jl, jg, etc.
**VAR** (variable operands): call, storew, storeb, print_addr, etc.
**EXT** (extended, V5+): Extended opcodes for advanced features

### 9.2 Instruction Types

- **Branch**: Conditional jump (je, jz, jl, jg, test, etc.)
- **Store**: Result to variable (add, sub, loadw, get_prop, etc.)
- **Text**: Print text (print, print_addr, print_paddr, etc.)
- **Call**: Routine invocation (call, call_vs, call_vn, etc.)
- **Return**: Exit routine (ret, rtrue, rfalse)

### 9.3 Common Opcodes

#### Arithmetic (2OP, store)
- `add a b → result`: a + b
- `sub a b → result`: a - b
- `mul a b → result`: a × b
- `div a b → result`: a ÷ b (signed)
- `mod a b → result`: a % b (signed)

#### Comparison (2OP, branch)
- `je a b c d...`: Jump if a equals any of b, c, d...
- `jl a b`: Jump if a < b (signed)
- `jg a b`: Jump if a > b (signed)

#### Logical (2OP/1OP)
- `and a b → result`: Bitwise AND
- `or a b → result`: Bitwise OR
- `not a → result`: Bitwise NOT

#### Memory (VAR/2OP, store)
- `loadw array index → result`: Read word at array[index]
- `loadb array index → result`: Read byte at array[index]
- `storew array index value`: Write word
- `storeb array index value`: Write byte

#### Objects (1OP/2OP)
- `get_child obj → child` (branch): Get first child
- `get_sibling obj → sibling` (branch): Get next sibling
- `get_parent obj → parent` (store): Get parent
- `insert_obj obj dest`: Move obj into dest
- `remove_obj obj`: Remove obj from tree
- `get_prop obj prop → result`: Read property
- `put_prop obj prop value`: Write property
- `set_attr obj attr`: Set attribute flag
- `clear_attr obj attr`: Clear attribute flag
- `test_attr obj attr` (branch): Test attribute

#### Control Flow
- `jump offset`: Unconditional jump (signed offset)
- `jz a` (branch): Jump if a = 0
- `ret value`: Return value
- `rtrue`: Return true (1)
- `rfalse`: Return false (0)
- `quit`: Terminate program

#### Calls (VAR)
- `call routine arg1 arg2... → result`: Call routine
- `call_vs routine arg1... → result` (V4+)
- `call_vn routine arg1...` (no result, V5+)

#### I/O
- `print "text"`: Print inline text
- `print_addr addr`: Print text at address
- `print_paddr paddr`: Print text at packed address
- `print_char zscii`: Print character
- `print_num value`: Print signed number
- `read text parse`: Read input
- `read_char → result` (V4+): Read single character

#### Screen (V4+)
- `split_window lines`: Split screen
- `set_window window`: Select window
- `erase_window window`: Clear window
- `set_cursor line col`: Position cursor

#### Sound/Graphics (V5+/V6)
- `sound_effect number effect`: Play sound
- `draw_picture picture_num`: Display picture (V6)

## 10. Version Differences

### 10.1 Version 1-2 (Rare)
- Early Zork games
- Limited features
- Permanent alphabet shifts

### 10.2 Version 3 (Most Common)
- 128KB story file limit
- 255 objects max
- Temporary alphabet shifts
- Standard Infocom feature set

### 10.3 Version 4
- 256KB story file limit
- Timed input
- Fixed-pitch font control
- Enhanced status line

### 10.4 Version 5
- 256KB story file limit
- Color support
- Sound effects
- Undo capability
- Custom alphabet tables
- Extended character set

### 10.5 Version 6
- Graphics support
- Mouse input
- Proportional fonts
- Multiple windows
- Advanced display control
- Pictures and complex layouts

### 10.6 Version 7
- **Created**: 1995 by Graham Nelson (not Infocom)
- **Purpose**: Support large Inform games exceeding V5's 256KB limit
- **File size**: 512KB maximum
- **Functionally identical to V5** except:
  - Packed address calculation: `4P + 8×R_O` for routines, `4P + 8×S_O` for strings
  - Uses header fields $28 (routines offset ÷ 8) and $2A (strings offset ÷ 8)
- **Usage**: Almost never used, poor interpreter support
- **Reason for disuse**: V8's simpler addressing made it obsolete

### 10.7 Version 8
- **Created**: 1995 by Graham Nelson (not Infocom)
- **Purpose**: Support large Inform games, became the standard over V7
- **File size**: 512KB maximum
- **Functionally identical to V5** except:
  - Packed address calculation: `8P` (simpler than V7)
  - File length divisor: 8 (header $1A × 8 = file size)
- **Usage**: Widely supported, standard for modern large IF games
- **Advantages over V7**:
  - Simpler packed addressing formula
  - No need for offset header fields
  - Better interpreter compatibility

## 11. File Structure

### 11.1 Story File Layout

```
+-----------------------+
| Header (64 bytes)     | Dynamic memory
+-----------------------+
| Dynamic data          |
|  - Objects            |
|  - Globals            |
|  - Writable tables    |
+-----------------------+ Header $0E
| Static data           | Read-only
|  - Dictionary         |
|  - Property tables    |
|  - Const tables       |
+-----------------------+ Header $04
| High memory           | Packed addresses
|  - Routines           |
|  - Compressed strings |
+-----------------------+ End of file
```

### 11.2 File Size Calculation

Header word $1A contains file length divided by a constant:

| Version | Divisor | Max Size | Notes |
|---------|---------|----------|-------|
| 1-3     | 2       | 128 KB   | Infocom standard |
| 4-5     | 4       | 256 KB   | Infocom extended |
| 6       | 4       | 256 KB   | Infocom graphics |
| 7       | 4       | 512 KB   | Graham Nelson 1995, rarely used |
| 8       | 8       | 512 KB   | Graham Nelson 1995, modern standard |

Actual file length = header[$1A] × divisor

### 11.3 Checksum

Header word $1C contains the sum of all bytes in the file except the header bytes (bytes $00-$3F), truncated to 16 bits.

## 12. Interpreter Behavior

### 12.1 Initialization

1. Load story file into memory
2. Set header fields (interpreter number/version, screen size, etc.)
3. Set capability flags in Flags 1 and 2
4. Initialize stack
5. Begin execution at initial PC (V1-5) or main routine (V6+)

### 12.2 Execution Model

- Fetch-decode-execute cycle
- Stack-based expression evaluation
- Call stack for routine invocation
- No direct high memory access

### 12.3 Undefined Behavior

The specification notes that behavior is undefined for:
- Invalid operand values
- Illegal memory access
- Malformed instructions
- Out-of-range values

Interpreters may crash rather than handle errors gracefully.

## 13. Save/Restore Format

### 13.1 Save Game Data

Contains:
- Dynamic memory (all writable data)
- Stack contents
- Program counter
- Return addresses

### 13.2 Undo (V5+)

Similar to save but stored in interpreter memory for quick restore.

### 13.3 Quetzal Format

Standard save file format (.qzl) defined separately, uses IFF structure.

## 14. Best Practices for Implementation

### 14.1 Compiler Output
- Place frequently accessed data in low memory
- Optimize string storage with abbreviations
- Use appropriate Z-machine version for features needed
- Minimize dynamic memory footprint

### 14.2 Interpreter Implementation
- Validate story file structure
- Implement all required opcodes for target versions
- Handle text encoding correctly
- Respect memory access restrictions

### 14.3 Debugging
- Check file checksum
- Verify header fields
- Trace instruction execution
- Monitor stack depth

## 15. Extensions and Modern Usage

### 15.1 Modern Interpreters
- Frotz (cross-platform)
- Zoom (macOS)
- Windows Frotz
- Gargoyle
- Browser-based (Parchment, Quixe)

### 15.2 Inform Compiler
Modern IF development typically uses Inform 7 or 6, which compile to Z-machine (or Glulx for larger games).

### 15.3 Testing Tools
- Txd: Disassembler
- Infodump: Story file analyzer
- ZTools: Various utilities

## 16. References

### 16.1 Primary Specification
"The Z-Machine Standards Document" Version 1.1 by Graham Nelson
https://inform-fiction.org/zmachine/standards/z1point1/

### 16.2 Historical Documents
- "Z-machine spec V3" (ZIP) - Dec 13, 1982
- "Z-machine spec V4" (EZIP) - Oct 26, 1984
- "Z-machine spec V5" (XZIP) - Oct 22, 1986
- "Z-machine spec V6" (YZIP) - Nov 30, 1988

Available at: https://eblong.com/infocom/

### 16.3 Additional Resources
- Inform Designer's Manual by Graham Nelson
- ZAP Assembler Specification
- Quetzal Save Format Specification
- IF Archive: https://ifarchive.org/

## 17. Implementation Checklist

### 17.1 For Z-code Compiler Writers
- [ ] Parse ZIL/Inform source correctly
- [ ] Generate valid header with correct version
- [ ] Encode text using Z-character compression
- [ ] Build object tree and property tables
- [ ] Create dictionary with proper sorting
- [ ] Compile routines to valid instruction sequences
- [ ] Use packed addresses correctly
- [ ] Calculate and store file checksum
- [ ] Optimize abbreviations for common text
- [ ] Stay within memory limits

### 17.2 For Z-machine Interpreter Writers
- [ ] Load and validate story file
- [ ] Parse header and set dynamic fields
- [ ] Implement all opcodes for target version(s)
- [ ] Handle text encoding/decoding
- [ ] Manage call stack correctly
- [ ] Implement object tree operations
- [ ] Support property access
- [ ] Handle memory access restrictions
- [ ] Implement save/restore
- [ ] Support undo (V5+)
- [ ] Implement screen model (windowing, colors, etc.)
- [ ] Handle input correctly

### 17.3 For Decompiler Writers
- [ ] Parse header
- [ ] Disassemble instructions
- [ ] Decode packed addresses
- [ ] Extract text strings
- [ ] Rebuild object tree
- [ ] Extract dictionary
- [ ] Identify routine boundaries
- [ ] Handle version differences
- [ ] Generate readable output (ZIL or assembly)

## Appendix A: Opcode Quick Reference

### A.1 Format Legend
- **Form**: Long/Short/Var/Ext
- **Type**: 0OP/1OP/2OP/VAR
- **Flags**: B=Branch, S=Store, T=Text

### A.2 Complete Opcode Table

(Selected essential opcodes - see Standards Document for complete list)

| Hex | Name | Form | Type | Flags | Description |
|-----|------|------|------|-------|-------------|
| 01  | je | Long/Var | 2OP/VAR | B | Jump if equal |
| 02  | jl | Long | 2OP | B | Jump if less |
| 03  | jg | Long | 2OP | B | Jump if greater |
| 04  | dec_chk | Long | 2OP | B | Decrement and check |
| 05  | inc_chk | Long | 2OP | B | Increment and check |
| 06  | jin | Long | 2OP | B | Jump if object in |
| 07  | test | Long | 2OP | B | Test bitmap |
| 08  | or | Long | 2OP | S | Bitwise OR |
| 09  | and | Long | 2OP | S | Bitwise AND |
| 0A  | test_attr | Long | 2OP | B | Test object attribute |
| 0B  | set_attr | Long | 2OP | - | Set object attribute |
| 0C  | clear_attr | Long | 2OP | - | Clear object attribute |
| 0D  | store | Long | 2OP | - | Store value to variable |
| 0E  | insert_obj | Long | 2OP | - | Insert object |
| 0F  | loadw | Long | 2OP | S | Load word from array |
| 10  | loadb | Long | 2OP | S | Load byte from array |
| 11  | get_prop | Long | 2OP | S | Get object property |
| 12  | get_prop_addr | Long | 2OP | S | Get property address |
| 13  | get_next_prop | Long | 2OP | S | Get next property number |
| 14  | add | Long | 2OP | S | Addition |
| 15  | sub | Long | 2OP | S | Subtraction |
| 16  | mul | Long | 2OP | S | Multiplication |
| 17  | div | Long | 2OP | S | Division (signed) |
| 18  | mod | Long | 2OP | S | Modulo (signed) |
| 81  | jz | Short | 1OP | B | Jump if zero |
| 82  | get_sibling | Short | 1OP | BS | Get object sibling |
| 83  | get_child | Short | 1OP | BS | Get object child |
| 84  | get_parent | Short | 1OP | S | Get object parent |
| 8B  | ret | Short | 1OP | - | Return value |
| 8C  | jump | Short | 1OP | - | Unconditional jump |
| B0  | rtrue | Short | 0OP | - | Return true |
| B1  | rfalse | Short | 0OP | - | Return false |
| B2  | print | Short | 0OP | T | Print inline text |
| B3  | print_ret | Short | 0OP | T | Print inline text and return |
| BA  | quit | Short | 0OP | - | Quit game |
| E0  | call | Var | VAR | S | Call routine |
| E1  | storew | Var | VAR | - | Store word to array |
| E2  | storeb | Var | VAR | - | Store byte to array |
| E3  | put_prop | Var | VAR | - | Set object property |
| E4  | read | Var | VAR | - | Read player input |
| E7  | print_addr | Var | VAR | T | Print string at address |

## Appendix B: ZSCII Character Reference

### B.1 Standard ASCII Range (32-126)
Same as ASCII.

### B.2 Special Characters (0-31, 127+)

| Code | Input | Output | Description |
|------|-------|--------|-------------|
| 0    | ✓     | ✓      | Null |
| 8    | ✓     | ✓      | Delete/backspace |
| 9    | ✓     | -      | Tab |
| 13   | ✓     | ✓      | Newline |
| 27   | ✓     | -      | Escape |
| 129-132 | ✓  | -      | Cursor keys |
| 133-144 | ✓  | -      | Function keys F1-F12 |
| 145-154 | ✓  | -      | Keypad 0-9 |
| 155-251 | ✓  | ✓      | Extra characters (V5+ via Unicode table) |
| 252-254 | ✓  | -      | Menu/mouse events |

## Appendix C: Understanding Version 7 vs Version 8

### C.1 Why Two 512KB Versions?

In 1995, Graham Nelson created both V7 and V8 to support Inform games larger than V5's 256KB limit. The existence of two versions addressing the same problem is historical:

1. **V7 was created first** as a natural extension of V6's packed addressing scheme
2. **V8 was created shortly after** with a simpler addressing formula
3. **V8 became the standard** due to its simplicity and better interpreter support

### C.2 Technical Differences

The **only** differences between V7 and V8 are:

| Aspect | Version 7 | Version 8 |
|--------|-----------|-----------|
| **Routine packed address** | `4P + 8×R_O` | `8P` |
| **String packed address** | `4P + 8×S_O` | `8P` |
| **Header $28-29** | Routines offset ÷ 8 | Not used |
| **Header $2A-2B** | Strings offset ÷ 8 | Not used |
| **File length divisor** | 4 | 8 |

Where:
- `P` = packed address value
- `R_O` = routines offset from header $28 (V7 only)
- `S_O` = strings offset from header $2A (V7 only)

### C.3 Why V8 Won

**Simplicity**: V8's formula (`8P`) is trivial to implement compared to V7's (`4P + 8×offset`)

**Compatibility**: Fewer interpreters properly implement the V7 offset mechanism

**No Advantage**: V7 offers no benefits over V8, only additional complexity

### C.4 Recommendation for Implementation

- **Support V8**: It's the modern standard for large games
- **Skip V7**: Almost no games use it, interpreter support is poor
- **Functionally identical to V5**: V8 uses the same opcodes, just different addressing

## Appendix D: Version Summary Table

| Feature | V1-2 | V3 | V4 | V5 | V6 | V7 | V8 |
|---------|------|----|----|----|----|-----|-----|
| **Created by** | Infocom | Infocom | Infocom | Infocom | Infocom | G. Nelson | G. Nelson |
| **Year** | 1979-81 | 1982 | 1984 | 1986 | 1988 | 1995 | 1995 |
| **Max file size** | 128K | 128K | 256K | 256K | 256K | 512K | 512K |
| **Packed addr** | 2P | 2P | 4P | 4P | 4P+offset | 4P+offset | 8P |
| **Max objects** | 255 | 255 | 65535 | 65535 | 65535 | 65535 | 65535 |
| **Attributes** | 32 | 32 | 48 | 48 | 48 | 48 | 48 |
| **Alphabet shift** | Perm | Temp | Temp | Temp | Temp | Temp | Temp |
| **Abbreviations** | V2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Timed input** | - | - | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Colors** | - | - | - | ✓ | ✓ | ✓ | ✓ |
| **Sound** | - | - | - | ✓ | ✓ | ✓ | ✓ |
| **Undo** | - | - | - | ✓ | ✓ | ✓ | ✓ |
| **Graphics** | - | - | - | - | ✓ | ✓ | ✓ |
| **Mouse** | - | - | - | - | ✓ | ✓ | ✓ |
| **Custom alphabet** | - | - | - | ✓ | ✓ | ✓ | ✓ |
| **Interpreter support** | Rare | Excellent | Excellent | Excellent | Good | Poor | Excellent |
| **Usage** | Historical | Common | Common | Common | Rare | Almost none | Modern IF |

---

**Document Version**: 1.0
**Based on**: Z-Machine Standards Document v1.1 (Graham Nelson, 2014)
**Date**: 2025
**License**: Documentation for educational and development purposes
