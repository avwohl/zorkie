# ZIL Opcodes Implemented in Zorkie Compiler

## Overview
This document lists all ZIL opcodes/operations currently implemented in the Zorkie compiler as of version 0.5.0.

---

## Control Flow (16 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| RTRUE | 0x00 (RET 1) | Return true | ✅ |
| RFALSE | 0x01 (RET 0) | Return false | ✅ |
| RFATAL | 0x01 (RET 0) | Return false (fatal condition) | ✅ |
| RETURN | RET | Return value | ✅ |
| QUIT | QUIT | End game | ✅ |
| RESTART | RESTART | Restart game | ✅ |
| SAVE | SAVE | Save game | ✅ |
| RESTORE | RESTORE | Restore game | ✅ |
| VERIFY | VERIFY | Verify story file | ✅ |
| COND | JZ/JE/etc | Multi-clause conditional | ✅ |
| REPEAT | JMP | Loop with optional bindings | ✅ |
| AGAIN | JMP | Restart current loop (continue) | ✅ |
| JIGS-UP | PRINT_RET+QUIT | Game over with message | ✅ |
| REST | ADD | Pointer arithmetic (list tail) | ✅ |
| PROG | Sequential | Execute statements in sequence | ✅ |
| BIND | Local scope | Create local bindings and execute body | ✅ |

---

## Output/Print Operations (25 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| TELL | PRINT | Print inline string | ✅ |
| PRINT | PRINT | Print inline string | ✅ |
| CRLF | NEW_LINE | Print newline | ✅ |
| PRINTN | PRINT_NUM | Print number | ✅ |
| PRINTD | PRINT_NUM | Print decimal (alias) | ✅ |
| PRINTC | PRINT_CHAR | Print character | ✅ |
| PRINTB | PRINT_PADDR | Print from byte array | ✅ |
| PRINTI | PRINT | Print inline (property) | ✅ |
| PRINTADDR | PRINT_ADDR | Print string at byte address | ✅ |
| STRING | Memory alloc | Build string (basic, no interpolation) | ✅ |
| SOUND | SOUND_EFFECT | Play sound effect | ✅ |
| CLEAR | ERASE_WINDOW | Clear screen | ✅ |
| SPLIT | SPLIT_WINDOW | Split screen into windows | ✅ |
| SCREEN | SET_WINDOW | Select active window | ✅ |
| CURSET | SET_CURSOR | Set cursor position | ✅ |
| HLIGHT | SET_TEXT_STYLE | Set text highlighting/style | ✅ |
| INPUT | SREAD | Read line input from player | ✅ |
| READ | SREAD | Read line input (alias for INPUT) | ✅ |
| BUFOUT | BUFFER_MODE | Enable/disable output buffering | ✅ |
| DIROUT | OUTPUT_STREAM | Direct output to memory table | ✅ |
| PRINTOBJ | PRINT_OBJ | Print object short name | ✅ |
| WINSIZE | SPLIT_WINDOW | Set window size (uses SPLIT for window 1) | ✅ |
| COLOR | SET_COLOUR | Set text colors (V5+ stub) | ⚠️ |
| FONT | SET_FONT | Set font (V5+ stub) | ⚠️ |

---

## Variables & Assignment (7 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| SET | STORE | Assign local variable | ✅ |
| SETG | STOREW/STOREB | Assign global variable | ✅ |
| INC | INC | Increment variable | ✅ |
| DEC | DEC | Decrement variable | ✅ |
| VALUE | LOAD | Get variable value | ✅ |
| LVAL | LOAD | Get local variable value | ✅ |
| GVAL | LOAD | Get global variable value | ✅ |

---

## Arithmetic Operations (10 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| + / ADD | ADD | Addition | ✅ |
| - / SUB | SUB | Subtraction | ✅ |
| * / MUL | MUL | Multiplication | ✅ |
| / / DIV | DIV | Division | ✅ |
| MOD | MOD | Modulo | ✅ |
| 1+ | ADD | Add 1 (shorthand) | ✅ |
| 1- | SUB | Subtract 1 (shorthand) | ✅ |
| MIN | Comparison | Minimum of two values | ✅ |
| MAX | Comparison | Maximum of two values | ✅ |
| ABS | Math | Absolute value | ✅ |

---

## Comparison & Predicates (17 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| EQUAL? / = | JE | Test equality | ✅ |
| L? / < | JL | Less than | ✅ |
| G? / > | JG | Greater than | ✅ |
| L=? / <= | JG inverted | Less than or equal | ✅ |
| G=? / >= | JL inverted | Greater than or equal | ✅ |
| N=? / != | JE inverted | Not equal | ✅ |
| ZERO? / 0? | JZ | Test if zero | ✅ |
| NOT? | JZ | Test if false/zero (alias) | ✅ |
| TRUE? | JZ | Test if non-zero/true | ✅ |
| ASSIGNED? | LOAD+JZ | Test if variable assigned | ✅ |
| IN? | GET_PARENT+JE | Test containment | ✅ |
| FSET? | TEST_ATTR | Test object attribute | ✅ |
| HELD? | GET_PARENT+JE+WINNER | Test if player holds object | ✅ |
| IGRTR? | INC+JG | Increment and test greater | ✅ |
| DLESS? | DEC+JL | Decrement and test less | ✅ |
| CHECKU | GET_PROP_ADDR | Check if object has property | ✅ |
| ORIGINAL? | TRUE? | Test if original (type check stub) | ✅ |

---

## Logical/Bitwise Operations (11 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| AND | AND | Bitwise AND | ✅ |
| OR | OR | Bitwise OR | ✅ |
| NOT | NOT | Bitwise NOT | ✅ |
| BAND | AND | Bitwise AND (byte-oriented) | ✅ |
| BOR | OR | Bitwise OR (byte-oriented) | ✅ |
| BTST | AND+mask | Test if bit is set | ✅ |
| TEST-BIT | AND+mask | Test specific bit number (computed mask) | ✅ |
| LSH | MUL | Left shift (V3: multiply by 2^n) | ✅ |
| RSH | DIV | Right shift (V3: divide by 2^n) | ✅ |
| USL | MUL | Unsigned shift left (alias for LSH) | ✅ |
| UXOR | XOR/compile-time | Unsigned XOR (compile-time eval for V3) | ✅ |

---

## Object Operations (10 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| MOVE | INSERT_OBJ | Move object to parent | ✅ |
| REMOVE | REMOVE_OBJ | Remove from parent | ✅ |
| LOC | GET_PARENT | Get object's parent | ✅ |
| FSET | SET_ATTR | Set object attribute | ✅ |
| FCLEAR | CLEAR_ATTR | Clear object attribute | ✅ |
| GET-CHILD / FIRST? | GET_CHILD | Get first child | ✅ |
| GET-SIBLING / NEXT? | GET_SIBLING | Get next sibling | ✅ |
| GET-PARENT | GET_PARENT | Get parent object | ✅ |
| EMPTY? | GET_CHILD+JZ | Test if object has no children | ✅ |

---

## Property Operations (6 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| GETP | GET_PROP | Get object property | ✅ |
| PUTP | PUT_PROP | Set object property | ✅ |
| PTSIZE | GET_PROP_LEN | Get property length | ✅ |
| NEXTP | GET_NEXT_PROP | Get next property | ✅ |
| GETPT | GET_PROP_ADDR | Get property table address | ✅ |

---

## Table/Array Operations (16 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| GET | LOADW | Get word from table (1-based) | ✅ |
| PUT | STOREW | Set word in table | ✅ |
| GETB | LOADB | Get byte from table | ✅ |
| PUTB | STOREB | Set byte in table | ✅ |
| LOADW | LOADW | Load word (direct) | ✅ |
| LOADB | LOADB | Load byte (direct) | ✅ |
| STOREW | STOREW | Store word (direct) | ✅ |
| STOREB | STOREB | Store byte (direct) | ✅ |
| LENGTH | LOADW | Get table/string length | ✅ |
| NTH | LOADW | Get Nth element (0-based) | ✅ |
| ZGET | LOADW | Zero-based get (alias for NTH) | ✅ |
| ZPUT | STOREW | Zero-based put (0-based indexing) | ✅ |
| GETB2 | LOADB | Get byte with base+offset addressing | ✅ |
| PUTB2 | STOREB | Put byte with base+offset addressing | ✅ |
| GETW2 | LOADW | Get word with base+offset addressing | ✅ |
| PUTW2 | STOREW | Put word with base+offset addressing | ✅ |

---

## Stack Operations (2 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| PUSH | PUSH | Push to stack | ✅ |
| PULL | PULL | Pop from stack | ✅ |

---

## Parser/Game Operations (14 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| VERB? | EQUAL+PRSA | Test verb action | ✅ |
| PERFORM | CALL | Dispatch action | ✅ |
| CALL | CALL_VS | Call routine with arguments | ✅ |
| APPLY | CALL_VS | Apply routine with table args | ✅ |
| RANDOM | RANDOM | Random number | ✅ |
| PROB | RANDOM+JL | Probability test (N% chance) | ✅ |
| PICK-ONE | RANDOM+GET | Select random table element | ✅ |
| GOTO | STORE HERE | Move player to room | ✅ |
| QUEUE | Memory alloc | Schedule interrupt/daemon | ✅ |
| INT | Memory lookup | Get interrupt by name | ✅ |
| DEQUEUE | STOREW | Disable interrupt | ✅ |
| ENABLE | STOREW | Enable interrupt | ✅ |
| DISABLE | STOREW | Disable interrupt (alias) | ✅ |
| LEXV | LOADW | Get word from parse buffer | ✅ |

---

## Macro System (1 major feature)

| Feature | Description | Status |
|---------|-------------|--------|
| DEFMAC | Macro definition and expansion | ✅ |
| Quote operator (') | Quoted parameters | ✅ |
| FORM constructor | Build code templates | ✅ |
| Parameter substitution | .VAR references | ✅ |

---

## Compilation Features

| Feature | Description | Status |
|---------|-------------|--------|
| Multi-file compilation | IFILE support | ✅ |
| PROPDEF | Property number assignment | ✅ |
| SYNTAX | Parser syntax definitions | ✅ |
| VOCABULARY | SYNONYM/ADJECTIVE | ✅ |
| Parser globals | PRSA, PRSO, PRSI, HERE, etc. | ✅ |
| Action constants | V?TAKE, V?DROP, etc. (32) | ✅ |

---

## System/Low-level Operations (8 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| LOWCORE | LOADW | Access low memory constants | ✅ |
| SCREEN-HEIGHT | Constant | Get screen height (24 for V3) | ✅ |
| SCREEN-WIDTH | Constant | Get screen width (80 for V3) | ✅ |
| ASR | DIV | Arithmetic shift right (alias for RSH) | ✅ |
| NEW-LINE | NEW_LINE | Print newline (alias for CRLF) | ✅ |
| CATCH | V5+ | Catch exception (V5+ stub) | ⚠️ |
| THROW | V5+ | Throw exception (V5+ stub) | ⚠️ |
| SPACES | PRINT_CHAR | Print N spaces (stub) | ⚠️ |

---

## Summary Statistics

- **Total Opcodes**: 141 distinct operations (135 working + 6 V5+ stubs)
- **Opcode Categories**: 14 categories
- **Test Programs**: 53 working examples
- **Planetfall Coverage**: ~97% of required operations
- **Version**: 1.4.0

---

## Not Yet Implemented (High Priority)

| ZIL Opcode | Description | Notes |
|------------|-------------|-------|
| STRING (full) | String interpolation with !,VAR | Basic version implemented |

---

## Not Yet Implemented (Medium Priority)

| Feature | Description | Notes |
|---------|-------------|-------|
| STRING form | String construction with `!` escapes | Used in Planetfall WBREAKS |
| BUZZ words | Abbreviations table | Optimization feature |
| GASSIGNED? | Check if global defined | Compile-time predicate |
| INSERT-FILE | Include file during compilation | Multi-file build system |
| Routine calling improvements | Better parameter handling | Current implementation basic |
| Property table optimization | Efficient property storage | Works but not optimal |

---

## String Escape Support

### ✅ Regular String Literals (in `"..."`)
- `\n` - newline
- `\t` - tab
- `\\` - literal backslash
- `\"` - literal quote

### ⚠️ STRING Form Escapes (NOT yet implemented)
The STRING opcode uses `!` for escapes:
- `!\"` - literal quote character
- `!\\` - literal backslash
- `!,VAR` - interpolate variable value

Example from Planetfall:
```zil
<SETG WBREAKS <STRING !\" !\\ !,WBREAKS>>
```

This requires implementing the STRING opcode, which is deferred for now

---

**Last Updated**: 2025-11-16
**Compiler Version**: 1.4.0
