# ZIL to Z-machine Compiler

A Python-based compiler that translates ZIL (Zork Implementation Language) source code to Z-machine bytecode.

## Overview

This compiler implements the complete pipeline from ZIL source code to executable Z-machine story files (.z3, .z4, .z5, .z8).

### Features

- **Lexical Analysis**: Tokenizes ZIL source code
- **Parsing**: Builds Abstract Syntax Tree (AST) from tokens
- **Code Generation**: Generates Z-machine bytecode from AST
- **Text Encoding**: ZSCII and Z-character compression
- **Z-machine Assembly**: Complete story file generation with headers, object tables, and dictionaries
- **Multiple Versions**: Supports Z-machine versions 3, 4, 5, and 8

## Installation

No external dependencies required - uses only Python 3 standard library.

```bash
cd zorkie
./zorkie --help
```

## Usage

### Basic Compilation

```bash
./zorkie input.zil
```

This will create `input.z3` in the same directory.

### Specify Output File

```bash
./zorkie input.zil -o game.z3
```

### Target Different Z-machine Version

```bash
./zorkie input.zil -v 5  # Creates .z5 file
```

### Verbose Output

```bash
./zorkie input.zil --verbose
```

## Architecture

### Directory Structure

```
zilc/
├── __init__.py
├── compiler.py         # Main compiler driver
├── lexer/
│   ├── __init__.py
│   └── lexer.py       # Tokenization
├── parser/
│   ├── __init__.py
│   ├── parser.py      # AST construction
│   └── ast_nodes.py   # AST node definitions
├── codegen/
│   ├── __init__.py
│   └── codegen.py     # Z-machine code generation
└── zmachine/
    ├── __init__.py
    ├── text_encoding.py   # ZSCII/Z-character encoding
    ├── opcodes.py         # Z-machine opcode definitions
    ├── assembler.py       # Story file assembly
    ├── object_table.py    # Object table builder
    └── dictionary.py      # Dictionary builder
```

### Compilation Pipeline

```
ZIL Source Code
      ↓
   [Lexer] → Tokens
      ↓
   [Parser] → Abstract Syntax Tree
      ↓
 [Code Generator] → Z-machine Bytecode
      ↓
  [Assembler] → Story File (.z3, .z5, etc.)
```

## Implementation Status

### ✅ Implemented Features

- **Lexer**: Complete tokenization of ZIL syntax
  - Angle brackets, parentheses, atoms, strings, numbers
  - Variable prefixes (., ,)
  - Comments (;"...")
  - Hex numbers ($FF)

- **Parser**: AST construction for core ZIL forms
  - ROUTINE definitions
  - OBJECT and ROOM definitions
  - SYNTAX definitions
  - VERSION directives
  - GLOBAL and CONSTANT declarations
  - TABLE/ITABLE/LTABLE
  - COND conditionals
  - Generic forms

- **Text Encoding**: Complete Z-character encoding
  - ZSCII character set
  - Alphabet tables (A0, A1, A2)
  - String compression (5-bit Z-characters packed into 16-bit words)
  - Dictionary word encoding

- **Assembler**: Story file generation
  - Z-machine header creation (64 bytes)
  - File structure assembly
  - Checksum calculation
  - Version-specific addressing

- **Code Generator**: Basic bytecode generation
  - RTRUE, RFALSE, QUIT
  - TELL (print text)
  - CRLF (newline)
  - SET/SETG (variable assignment)
  - Basic arithmetic (ADD, SUB)

### 🚧 Partial Implementation

- **Object System**: Object and room definitions parsed, basic table structure
- **Dictionary**: Word storage implemented, needs parser integration
- **Control Flow**: COND parsed, needs full branch generation
- **Expressions**: Basic forms, needs comprehensive operator support

### 📋 TODO

- **Complete Code Generation**:
  - All arithmetic and logical operators
  - Full control flow (COND with proper branching, REPEAT loops)
  - Object manipulation (MOVE, FSET, FCLEAR, GETP, PUTP)
  - Routine calls with parameters
  - Property and attribute access

- **Object System**:
  - Property table generation
  - Object tree construction
  - Attribute handling

- **Parser Features**:
  - Verb routines and action handling
  - Event system
  - Macros (DEFMAC)

- **Advanced Features**:
  - Abbreviations table
  - Packed addressing for routines/strings
  - Save/restore support
  - Multiple file compilation

## Example Programs

### Minimal Program

```zil
;"Minimal ZIL program"
<VERSION 3>

<ROUTINE GO ()
    <QUIT>>
```

### Hello World

```zil
;"Hello World in ZIL"
<VERSION 3>

<ROUTINE GO ()
    <CRLF>
    <TELL "Hello, World!" CR>
    <QUIT>>
```

### With Variables

```zil
<VERSION 3>

<GLOBAL SCORE 0>

<ROUTINE GO ()
    <SETG SCORE 10>
    <TELL "Your score is: ">
    <PRINT-NUM ,SCORE>
    <CRLF>
    <QUIT>>
```

## Testing

### Lexer Tests

```bash
python3 tests/test_lexer.py
```

### Compiler Tests

```bash
./zorkie examples/minimal.zil --verbose
./zorkie examples/hello.zil --verbose
```

### Running Compiled Games

Use a Z-machine interpreter like Frotz:

```bash
frotz examples/minimal.z3
```

## Technical Details

### Z-machine Versions Supported

- **Version 3**: 128KB max, 255 objects, standard features (default)
- **Version 4**: 256KB max, 65535 objects, timed input
- **Version 5**: 256KB max, colors, sound, undo
- **Version 8**: 512KB max, extended addressing

### Text Encoding

The compiler implements full Z-character encoding:

1. Characters are encoded using three alphabet tables (A0, A1, A2)
2. Each Z-character is 5 bits
3. Three Z-characters pack into one 16-bit word
4. Bit 15 of the final word is set as an end marker
5. ZSCII escape sequences for characters not in alphabets

### Memory Layout

Story files follow Z-machine specification:

```
$0000-$003F: Header (64 bytes)
$0040+:      Dynamic memory (globals, writable data)
---:         Object table
---:         Dictionary
---:         Static memory
---:         High memory (routines, strings)
```

## Contributing

This is an educational implementation. The compiler demonstrates:

- Compiler design principles (lexing, parsing, code generation)
- Virtual machine target code generation
- Text compression algorithms
- Binary file format handling

### Extending the Compiler

To add new ZIL features:

1. **Lexer**: Add token types in `lexer/lexer.py` if needed
2. **Parser**: Add AST nodes in `parser/ast_nodes.py`
3. **Parser**: Add parsing logic in `parser/parser.py`
4. **Code Generator**: Add bytecode generation in `codegen/codegen.py`
5. **Opcodes**: Add opcode definitions in `zmachine/opcodes.py` if needed

## References

- **ZIL_SPECIFICATION.md**: Complete ZIL language reference
- **ZMACHINE_SPECIFICATION.md**: Z-machine bytecode format reference
- **Z-Machine Standards Document** (Graham Nelson)
- **Learning ZIL** (Steve Meretzky)

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](../LICENSE) file for details.

## Known Limitations

1. **Code Generator**: Only basic instructions implemented
2. **Optimization**: No optimization pass
3. **Error Messages**: Basic error reporting
4. **Debugging**: No debug symbol generation
5. **Macros**: Not yet implemented
6. **Multiple Files**: Single file compilation only

This is a foundational implementation that can be extended to support the full ZIL language.
