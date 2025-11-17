# Z-machine V3 Opcode Quick Reference

Essential opcodes for ZIL compilation. For complete spec, see: https://www.inform-fiction.org/zmachine/standards/

## Opcode Format

Z-machine instructions have variable length:
```
[opcode byte] [operand types] [operands...] [store] [branch]
```

### Opcode Types (by operand count)

- **0OP**: No operands (opcodes 0xB0-0xBF)
- **1OP**: One operand (opcodes 0x80-0x8F when ≥128, 0x90-0x9F when ≥64)
- **2OP**: Two operands (opcodes 0x00-0x1F when <128)
- **VAR**: Variable operands (opcodes 0xC0-0xFF for VAR, 0x20-0x3F for 2OP-like)

### Operand Types
- `Small constant`: 0-255 (1 byte)
- `Large constant`: 0-65535 (2 bytes)
- `Variable`: global or local variable reference

## Essential Opcodes for Hello World

### Output Opcodes

| Hex  | Name       | Operands | Description |
|------|------------|----------|-------------|
| 0xB2 | PRINTI     | (text)   | Print immediate string (packed in instruction) |
| 0xBB | NEW_LINE   | -        | Print newline (CR + LF) |
| 0xE1 | PRINT      | str      | Print string at packed address |
| 0xE5 | PRINT_ADDR | addr     | Print string at byte address |
| 0xE9 | PRINT_PADDR| paddr    | Print string at packed address |
| 0xAD | PRINT_CHAR | c        | Print single character |
| 0xAE | PRINT_NUM  | n        | Print signed number |

**Example: Hello World**
```
b2 [encoded "Hello, world!"]   PRINTI
bb                             NEW_LINE
```

### Return Opcodes

| Hex  | Name    | Operands | Description |
|------|---------|----------|-------------|
| 0xB0 | RTRUE   | -        | Return TRUE (1) |
| 0xB1 | RFALSE  | -        | Return FALSE (0) |
| 0xBE | RET     | value    | Return value |
| 0xB3 | PRINT_RET | (text) | Print text, newline, then return TRUE |

**Example:**
```
b0         RTRUE          ; Return 1
b1         RFALSE         ; Return 0
be 05      RET 5          ; Return 5
```

## Flow Control

### Branch Opcodes

| Hex  | Name       | Operands  | Description |
|------|------------|-----------|-------------|
| 0x00 | JE         | a b ?lab  | Jump if equal |
| 0x01 | JL         | a b ?lab  | Jump if a < b (signed) |
| 0x02 | JG         | a b ?lab  | Jump if a > b (signed) |
| 0x0C | JUMP       | offset    | Unconditional jump |
| 0xA7 | JZ         | a ?lab    | Jump if a is zero |

Branch format: `?label` means if condition true, branch to label

**Example:**
```
a7 01 [branch]     JZ g01 ?label    ; If g01 is 0, jump
00 03 04 [branch]  JE 3 4 ?label    ; If 3 == 4, jump
```

### Call Opcodes

| Hex  | Name    | Operands       | Description |
|------|---------|----------------|-------------|
| 0xE0 | CALL    | routine [args] → result | Call routine |
| 0x19 | CALL_VS | routine [args] → result | Call routine (VAR store) |

**Example:**
```
e0 [addr] 01 02 → 10   CALL routine(1,2) → local10
```

## Arithmetic

| Hex  | Name | Operands | Description |
|------|------|----------|-------------|
| 0x14 | ADD  | a b → r  | r = a + b |
| 0x15 | SUB  | a b → r  | r = a - b |
| 0x16 | MUL  | a b → r  | r = a * b |
| 0x17 | DIV  | a b → r  | r = a / b (signed) |
| 0x18 | MOD  | a b → r  | r = a % b (signed) |

**Example:**
```
14 05 03 → 10      ADD 5 3 → local10      ; local10 = 8
15 0a 02 → 10      SUB 10 2 → local10     ; local10 = 8
```

## Logic

| Hex  | Name | Operands | Description |
|------|------|----------|-------------|
| 0x09 | AND  | a b → r  | Bitwise AND |
| 0x0A | OR   | a b → r  | Bitwise OR |
| 0x08 | NOT  | a → r    | Bitwise NOT |

## Variables

### Load/Store

| Hex  | Name       | Operands | Description |
|------|------------|----------|-------------|
| 0x0D | STORE      | var val  | var = val |
| 0x8D | LOAD       | var → r  | r = var |
| 0xB4 | POP        | -        | Discard top of stack |
| 0xB9 | PUSH       | value    | Push value to stack |

**Variables:**
- 0x00: Top of stack
- 0x01-0x0F: Local variables (L00-L14)
- 0x10+: Global variables (G00+)

**Example:**
```
0d 01 05       STORE local01 5        ; local01 = 5
8d 01 → 02     LOAD local01 → local02 ; local02 = local01
```

### Increment/Decrement

| Hex  | Name | Operands | Description |
|------|------|----------|-------------|
| 0x85 | INC  | var      | var++ |
| 0x86 | DEC  | var      | var-- |

## Objects & Properties

| Hex  | Name          | Operands      | Description |
|------|---------------|---------------|-------------|
| 0x8B | GET_PROP      | obj prop → r  | Get property value |
| 0x93 | PUT_PROP      | obj prop val  | Set property value |
| 0x82 | GET_PARENT    | obj → r       | Get parent object |
| 0x83 | GET_SIBLING   | obj → r ?lab  | Get sibling, branch if exists |
| 0x84 | GET_CHILD     | obj → r ?lab  | Get child, branch if exists |
| 0x8E | INSERT_OBJ    | obj dest      | Move obj to dest |
| 0x89 | REMOVE_OBJ    | obj           | Remove obj from tree |

## Text & Input

| Hex  | Name       | Operands       | Description |
|------|------------|----------------|-------------|
| 0xE4 | READ       | text parse     | Read input from keyboard |
| 0xE9 | TOKENISE   | text parse     | Tokenize text |

## Testing & Attributes

| Hex  | Name          | Operands      | Description |
|------|---------------|---------------|-------------|
| 0x8A | GET_ATTR      | obj attr ?lab | Test if obj has attribute |
| 0x8B | SET_ATTR      | obj attr      | Set attribute |
| 0x8C | CLEAR_ATTR    | obj attr      | Clear attribute |

## Memory

| Hex  | Name       | Operands    | Description |
|------|------------|-------------|-------------|
| 0x90 | LOADW      | arr idx → r | r = word_array[idx] |
| 0x91 | LOADB      | arr idx → r | r = byte_array[idx] |
| 0xA0 | STOREW     | arr idx val | word_array[idx] = val |
| 0xA1 | STOREB     | arr idx val | byte_array[idx] = val |

## Random & Misc

| Hex  | Name       | Operands | Description |
|------|------------|----------|-------------|
| 0xE7 | RANDOM     | range → r| Random number 1-range (if range>0) |
| 0xBA | QUIT       | -        | Exit game |
| 0xBD | VERIFY     | ?lab     | Verify game file checksum |
| 0xB8 | RESTART    | -        | Restart game |
| 0xB5 | SAVE       | ?lab     | Save game (branch if success) |
| 0xB6 | RESTORE    | ?lab     | Restore game (branch if success) |

## Operand Type Encoding

For 2OP and VAR opcodes, operand types are encoded in a byte:
```
Bits:  7-6  5-4  3-2  1-0
       OP1  OP2  OP3  OP4

Values:
  00 = Large constant (2 bytes)
  01 = Small constant (1 byte)
  10 = Variable
  11 = Omitted (for VAR opcodes)
```

**Example:**
```
14 45 03 05 → 10       ; Operand types: 01 00 01 (small, large, small)
               ; ADD small(3) large(5) → var(10)
```

## Common Patterns

### Print and Return
```
b3 [text]      PRINT_RET "text"   ; Print text + newline + return TRUE
```

### Conditional Store
```
85 01          INC local01         ; local01++
a7 01 [branch] JZ local01 ?done    ; If local01 == 0, jump
b2 [text]      PRINTI "Not zero"
bb             NEW_LINE
[done:]
```

### Loop
```
[loop:]
0d 01 0a       STORE local01 10    ; counter = 10
[top:]
b2 [text]      PRINTI "Looping"
bb             NEW_LINE
86 01          DEC local01          ; counter--
a7 01 [top]    JZ local01 [top]    ; If counter != 0, loop
```

### Function Call
```
e0 [addr] 01 02 → 10   CALL myfunc(1, 2) → local10
```

## Most Common Opcodes for Basic Games

For a minimal text adventure:
1. **PRINTI** (0xB2) - Print strings
2. **NEW_LINE** (0xBB) - Newlines
3. **RTRUE** (0xB0) - Return from routines
4. **JE** (0x00) - Compare values
5. **JZ** (0xA7) - Test zero
6. **STORE** (0x0D) - Set variables
7. **LOAD** (0x8D) - Get variables
8. **CALL** (0xE0) - Call routines
9. **GET_PROP** (0x8B) - Get object properties
10. **INSERT_OBJ** (0x8E) - Move objects

## References

- Full spec: https://www.inform-fiction.org/zmachine/standards/z1point1/
- Opcode table: Section 14
- Operand encoding: Section 4
- Instruction format: Section 4.3

## For Your Compiler

Start by implementing these for hello world:
- PRINTI (0xB2)
- NEW_LINE (0xBB)
- RTRUE (0xB0)

Then add for basic text adventures:
- JE, JZ (conditionals)
- STORE, LOAD (variables)
- CALL (function calls)
- Object/property opcodes

Build up gradually!
