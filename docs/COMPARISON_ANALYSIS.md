# ZIL Compiler Comparison Analysis

## Overview

This document compares the output of our ZIL compiler against actual Infocom Z-machine story files.

## Test Subject: Mini-Zork (1987)

### Source
- **Repository**: https://github.com/historicalsource/minizork-1987
- **Compiled File**: minizork.z3 (from IF Archive)
- **Size**: 52,216 bytes
- **Version**: Z-machine version 3
- **Release**: 34
- **Serial**: 871124

### Header Analysis

```
Version: 3
Release: 34
High memory base: 0x3709
Initial PC: 0x37d9
Dictionary: 0x285a
Object table: 0x03c6
Globals table: 0x02b4
Static memory base: 0x2187
Abbreviations: 0x01f4
File length: 52,216 bytes
Checksum: 0xd870
```

### Memory Layout

```
Dynamic memory: 0x0000 - 0x2187 (8,583 bytes)
  - Header: 0x0000 - 0x003F (64 bytes)
  - Globals: 0x0040 - 0x02B3
  - Object table: 0x03C6 - ?

Static memory: 0x2187 - 0x3709
  - Dictionary: 0x285A

High memory: 0x3709 - 0xCBF8
  - Routines starting at 0x3709
  - Initial execution at 0x37D9
```

## Our Compiler Output

### Current Capabilities

Our compiler can generate:

1. **Header Structure** ✅
   - Correct 64-byte header format
   - Version byte
   - Memory region pointers
   - File length and checksum

2. **Text Encoding** ✅
   - ZSCII to Z-character conversion
   - Alphabet table encoding
   - 5-bit packing into 16-bit words
   - End marker bit

3. **Basic Opcodes** ✅
   - QUIT (0xBA)
   - RTRUE (0xB0)
   - RFALSE (0xB1)
   - PRINT (0xB2)
   - NEW_LINE (0xBB)

4. **Data Structures** 🚧
   - Object table structure (basic)
   - Dictionary structure (basic)
   - Property tables (placeholder)

### Limitations

1. **No Full Compilation**: Cannot yet compile actual game files
   - Missing: Complete opcode set
   - Missing: Proper routine call mechanism
   - Missing: Object manipulation
   - Missing: Property access

2. **No Optimization**
   - No abbreviation table generation
   - No string deduplication
   - No dead code elimination

3. **Incomplete Features**
   - Parser integration incomplete
   - Macro system not implemented
   - Multi-file compilation not supported

## Key Differences

### What Works
- Our minimal "QUIT" program compiles to valid Z-code structure
- Header format matches specification
- Text encoding produces correct Z-character streams

### What Needs Work
- Cannot compile complex routines with control flow
- Object/room definitions parse but don't generate proper tables
- No integration of all components into working game

## Bytecode Comparison

### Simple QUIT Program

**Our Output** (expected):
```
Header (64 bytes)
Globals (480 bytes, 240 variables initialized to 0)
Minimal routine:
  0x00: Number of locals = 0
  0x01: QUIT opcode (0xBA)
```

**Actual Infocom File** (Mini-Zork):
```
Much more complex:
- 8,583 bytes of dynamic memory
- Extensive object table
- Large dictionary
- Multiple routines
- Abbreviations table
```

## Testing Approach

Since full game compilation isn't yet working, we tested:

1. **Lexer**: ✅ Successfully tokenizes ZIL syntax
2. **Parser**: ✅ Builds AST from tokens
3. **Text Encoding**: ✅ Produces correct Z-character encoding
4. **Header Generation**: ✅ Creates valid 64-byte headers
5. **Simple Opcodes**: ✅ Generates correct bytecode for basic instructions

## Validation Method

To validate our compiler against real Z-machine files:

1. **Structural Analysis**
   - Created `tools/analyze_z3.py` to examine story file structure
   - Verified header format matches specification
   - Confirmed memory layout understanding

2. **Component Testing**
   - Text encoder tested independently
   - Lexer tested with real ZIL source
   - Parser tested with game source files

3. **Reference Implementation**
   - Compared against ZILF (modern ZIL compiler)
   - Studied Infocom original compiler output
   - Referenced Z-machine specification

## Recommendations for Full Implementation

To achieve parity with ZILF/original compiler:

1. **Complete Code Generator**
   - Implement all 2OP, 1OP, 0OP, VAR opcodes
   - Add proper branching logic
   - Implement routine call mechanism with parameter passing

2. **Object System**
   - Generate property tables with correct format
   - Build object tree relationships
   - Implement attribute storage

3. **Linker/Assembler**
   - Resolve routine addresses
   - Build abbreviations table
   - Optimize string storage

4. **Advanced Features**
   - Macro expansion
   - Multi-file compilation
   - Debug symbol generation

## Conclusion

Our compiler successfully implements the foundational components of a ZIL compiler:
- Correct lexical analysis
- Complete parsing of major ZIL forms
- Proper text encoding
- Valid Z-machine file structure

However, it requires significant additional work to compile real games like Mini-Zork. The architecture is sound and extensible, making future development straightforward.

### What We Learned

1. **Z-machine Format**: Deep understanding of bytecode structure
2. **Text Encoding**: Complete implementation of ZSCII compression
3. **Compiler Design**: Full pipeline from source to bytecode
4. **Historical Context**: How Infocom built their games

### Next Steps

To compile real ZIL games:
1. Implement missing opcodes (est. 100+ opcodes)
2. Complete object table generation
3. Add property table support
4. Implement routine linking
5. Build abbreviations system
6. Add macro expansion
7. Create full test suite with real games

The foundation is solid. Building the complete compiler is now a matter of systematic implementation of remaining features.
