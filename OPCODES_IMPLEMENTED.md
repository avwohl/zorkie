# ZIL Opcodes Implemented in Zorkie Compiler

## Overview
This document lists all ZIL opcodes/operations currently implemented in the Zorkie compiler as of version 0.5.0.

---

## Control Flow (14 opcodes)

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

---

## Output/Print Operations (9 opcodes)

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

## Arithmetic Operations (5 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| + / ADD | ADD | Addition | ✅ |
| - / SUB | SUB | Subtraction | ✅ |
| * / MUL | MUL | Multiplication | ✅ |
| / / DIV | DIV | Division | ✅ |
| MOD | MOD | Modulo | ✅ |

---

## Comparison & Predicates (8 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| EQUAL? / = | JE | Test equality | ✅ |
| L? / < | JL | Less than | ✅ |
| G? / > | JG | Greater than | ✅ |
| ZERO? / 0? | JZ | Test if zero | ✅ |
| IN? | GET_PARENT+JE | Test containment | ✅ |
| FSET? | TEST_ATTR | Test object attribute | ✅ |
| HELD? | GET_PARENT+JE+WINNER | Test if player holds object | ✅ |
| IGRTR? | INC+JG | Increment and test greater | ✅ |

---

## Logical/Bitwise Operations (6 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| AND | AND | Bitwise AND | ✅ |
| OR | OR | Bitwise OR | ✅ |
| NOT | NOT | Bitwise NOT | ✅ |
| BAND | AND | Bitwise AND (byte-oriented) | ✅ |
| BOR | OR | Bitwise OR (byte-oriented) | ✅ |
| BTST | AND+mask | Test if bit is set | ✅ |

---

## Object Operations (9 opcodes)

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

## Table/Array Operations (10 opcodes)

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

---

## Stack Operations (2 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| PUSH | PUSH | Push to stack | ✅ |
| PULL | PULL | Pop from stack | ✅ |

---

## Parser/Game Operations (6 opcodes)

| ZIL Opcode | Z-machine | Description | Status |
|------------|-----------|-------------|--------|
| VERB? | EQUAL+PRSA | Test verb action | ✅ |
| PERFORM | CALL | Dispatch action | ✅ |
| RANDOM | RANDOM | Random number | ✅ |
| PROB | RANDOM+JL | Probability test (N% chance) | ✅ |
| PICK-ONE | RANDOM+GET | Select random table element | ✅ |
| GOTO | STORE HERE | Move player to room | ✅ |

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

## Summary Statistics

- **Total Opcodes**: 82 distinct operations
- **Opcode Categories**: 13 categories
- **Test Programs**: 37 working examples
- **Planetfall Coverage**: ~61% of required operations
- **Version**: 0.6.1

---

## Not Yet Implemented (High Priority)

| ZIL Opcode | Description | Planetfall Uses |
|------------|-------------|-----------------|
| QUEUE | Daemon scheduling | 78 |
| INT | Interrupt control | 45 |
| STRING | Build strings with escapes/interpolation | 15 |
| DEQUEUE | Remove daemon | - |

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
**Compiler Version**: 0.6.1
