# Hello World - Complete Example

This is the simplest possible ZIL program and what your compiler should produce.

## Source Code

**File: hello.zil (5 lines, 86 bytes)**
```zil
"Hello World sample for ZILF"

<ROUTINE GO ()
    <PRINTI "Hello, world!">
    <CRLF>>
```

## What It Should Do

When you run `frotz hello.z3`, it should output:
```
Hello, world!
```

Then exit.

## Expected Binary Output

**File: hello.z3 (512 bytes)**

### Header (First 64 Bytes)

```
Offset  Hex Bytes            Decimal  Meaning
------  -------------------  -------  ------------------------------------
00-01   03 00                3, 0     Version 3, Flags 1
02-03   00 00                0        Release 0
04-05   00 a4                164      High memory base: 0x00a4 (164)
06-07   00 a5                165      Initial PC: 0x00a5 (165)
08-09   00 86                134      Dictionary: 0x0086 (134)
10-11   00 48                72       Object table: 0x0048 (72)
12-13   00 40                64       Global vars: 0x0040 (64)
14-15   00 86                134      Static memory: 0x0086 (134)
16-17   00 00                0        Flags 2
18-23   30 39 30 37 30 38    -        Serial: "090708" (Sept 7, 2008)
24-25   00 40                64       Abbreviations: 0x0040 (64)
26-27   01 00                256      File length: 256 * 2 = 512 bytes
28-29   0e 88                3720     Checksum
30-63   (zeros/padding)               Reserved
```

### Memory Layout

```
0x0000 (0)    ┌────────────────────┐
              │ Header (64 bytes)  │
0x0040 (64)   ├────────────────────┤
              │ Globals (480 bytes)│ ← Usually 240 globals * 2 bytes
              │ (mostly empty)     │
0x0048 (72)   ├────────────────────┤
              │ Object Table       │ ← Property defaults + objects
              │ (minimal)          │
0x0086 (134)  ├────────────────────┤
              │ Dictionary         │ ← Static memory starts here
              │ (minimal)          │
0x00a4 (164)  ├────────────────────┤
              │ High Memory/Code   │ ← Routine GO starts here
0x00a5 (165)  │ GO routine         │ ← PC starts here
              │   PRINTI "Hello"   │
              │   CRLF             │
              │   RTRUE            │
              └────────────────────┘
0x0200 (512)  End of file
```

### The Code Section

Starting at PC (0x00a5), the GO routine:

```
Address  Hex              Opcode       Description
-------  ---------------  -----------  -----------------------------------
0x00a5   b2 [string]      PRINTI       Print immediate string "Hello, world!"
         (string data)                 Encoded in Z-chars
0x00??   bb               NEW_LINE     Print newline
0x00??   b0               RTRUE        Return true (exit)
```

### Full Hex Dump (First 256 Bytes)

```
00000000: 0300 0000 00a4 00a5 0086 0048 0040 0086  ...........H.@..
00000010: 0000 3039 3037 3038 0040 0100 0e88 0000  ..090708.@......
00000020: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000030: 0000 0000 0000 0000 0000 0000 5a41 5046  ............ZAPF
00000040: 00a2 00a2 00a2 00a2 0000 0000 0000 0000  ................
00000050: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000060: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000070: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000080: 0000 0000 0000 0000 0002 0000 0000 0000  ................
00000090: 0000 0000 0000 0000 0000 0000 0000 0000  ................
000000a0: 0000 0000 00b2 2d15 460d 05f5 cb14 a54a  ......-.F......J
000000b0: 14a5 a000 bb00 b000 0000 0000 0000 0000  ................
000000c0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
...
```

## Key Points for Your Compiler

### 1. Version Byte
- **Must be 0x03** for Z-machine version 3

### 2. High Memory Base (0x00a4)
- Everything before this is dynamic/static memory
- Everything from here on is code and packed strings
- This is where routines live

### 3. Initial PC (0x00a5)
- Where execution starts
- Must point to the GO routine
- Must be in high memory (>= high mem base)

### 4. Memory Regions
- **Dynamic (0x00-0x86)**: Writable at runtime
  - Header
  - Globals (mostly zeros for hello world)
  - Object table (minimal - just property defaults)

- **Static (0x86-0xa4)**: Read-only
  - Dictionary (minimal - almost empty)

- **High (0xa4-0x200)**: Code
  - The GO routine

### 5. The GO Routine
Located at 0x00a5:
```
0x00a5: b2 [encoded string]   PRINTI "Hello, world!"
0x00??: bb                    NEW_LINE
0x00??: b0                    RTRUE
```

- **PRINTI** (opcode 0xb2): Print immediate string
- **NEW_LINE** (opcode 0xbb): Print newline (CRLF)
- **RTRUE** (opcode 0xb0): Return TRUE

### 6. String Encoding
"Hello, world!" is encoded using Z-character encoding:
- 3 Z-chars packed into each 2-byte word
- Uses alphabet tables (A0, A1, A2)
- Last word has bit 15 set

The hex `2d15 460d 05f5 cb14 a54a 14a5 a000` encodes "Hello, world!"

## Testing Your Output

```bash
# Compile your version
your-compiler hello.zil -o my-hello.z3

# Compare file sizes
ls -l my-hello.z3 examples/hello-reference.z3

# Check the header
xxd -l 64 my-hello.z3
xxd -l 64 examples/hello-reference.z3

# Deep inspection
./inspect-zcode.sh my-hello.z3 examples/hello-reference.z3

# Try to run it
frotz my-hello.z3
```

## Common Mistakes

### Mistake 1: Wrong Version
```
Error: 00 00 00 00 ...
Should be: 03 00 00 00 ...
```

### Mistake 2: PC Not in High Memory
```
Error: High mem: 0x00a4, PC: 0x0040
PC must be >= High memory base!
```

### Mistake 3: File Length Wrong
```
Error: File is 512 bytes but header says 1024 bytes
Bytes 26-27 should be: 0x0100 (256 * 2 = 512)
```

### Mistake 4: Missing Code
```
Error: File ends at 0x0080 but PC is 0x00a5
Need to write the actual routine code!
```

### Mistake 5: String Not Encoded
```
Error: Raw ASCII bytes instead of Z-char encoding
Must encode "Hello, world!" using Z-character format
```

## Minimal Compilation Steps

1. **Parse** hello.zil
   - Recognize ROUTINE GO
   - Recognize PRINTI and CRLF

2. **Generate code**
   - PRINTI → opcode 0xb2 + encoded string
   - CRLF → opcode 0xbb
   - Implicit RTRUE → opcode 0xb0

3. **Layout memory**
   - Header at 0x0000
   - Globals at 0x0040 (can be mostly zeros)
   - Object table at 0x0048 (minimal)
   - Dictionary at 0x0086 (minimal)
   - Code at 0x00a4+

4. **Write header**
   - Version: 3
   - High mem: where code starts
   - PC: where GO routine starts
   - All table addresses
   - File length / 2
   - Calculate checksum

5. **Write structures**
   - Globals (480 bytes, mostly zeros)
   - Object table (property defaults)
   - Dictionary (minimal)

6. **Write code**
   - GO routine with three instructions

7. **Pad to 512 bytes** (or whatever size)

## Success Criteria

✓ File is valid Z-machine format (./verify-zfiles.sh)
✓ File runs without crashing (frotz my-hello.z3)
✓ Outputs "Hello, world!" followed by newline
✓ Exits cleanly

You don't need to match the reference byte-for-byte!
Different string encoding, memory layout, etc. are fine as long as it works.

## Next Steps After Hello World

Once hello world works:
1. Try beer.zil (adds loops)
2. Try cloak.zil (adds parser, objects)
3. Try zork1.zil (full game)

But start here. Get this 5-line program working first!
