# Test Output Examples

What to expect when running the test tools.

## Example 1: Perfect Match (Unlikely but Possible)

```bash
$ ./compare-zcode.sh -c mycompiler -t hello

Testing: hello
Source: zilf/sample/hello/hello.zil
Reference: zilf/test/Dezapf.Tests/Resources/hello.z3
Compiling with mycompiler...
Reference size: 512 bytes
Output size: 512 bytes
✓ Perfect match! Files are identical.

======== SUMMARY ========
Passed: 1
Failed: 0
Passed tests:
  ✓ hello
```

This means your compiler produced byte-identical output. Rare, but great!

---

## Example 2: Files Differ (Normal)

```bash
$ ./compare-zcode.sh -c mycompiler -t hello

Testing: hello
Source: zilf/sample/hello/hello.zil
Reference: zilf/test/Dezapf.Tests/Resources/hello.z3
Compiling with mycompiler...
Reference size: 512 bytes
Output size: 520 bytes
✗ Files differ

First difference at:
Byte 18 (0x12): reference=0x30 output=0x32

Total differences: 247 bytes
Output file saved: output_hello.z3

======== SUMMARY ========
Passed: 0
Failed: 1
Failed tests:
  ✗ hello
```

This is normal! Now use inspect-zcode.sh to see what's different.

---

## Example 3: Inspecting Differences

```bash
$ ./inspect-zcode.sh output_hello.z3 examples/hello-reference.z3

===================================
File: output_hello.z3
Size: 520 bytes
===================================

--- HEADER (first 64 bytes) ---
Version:           03 (3)
Flags 1:           0x00
Release:           0x0001 (1)
High memory:       0x00a8 (168)
Initial PC:        0x00a9 (169)
Dictionary:        0x008a (138)
Object table:      0x0048 (72)
Global vars:       0x0040 (64)
Static memory:     0x008a (138)
Flags 2:           0x0000
Serial:            '250117'
Abbreviations:     0x0040 (64)
File length (hdr): 0x0104 (*2 = 520 bytes)
Checksum:          0x1234

--- MEMORY LAYOUT ---
Dynamic:   0x0000 - 0x0089 (138 bytes)
Static:    0x008a - 0x00a7 (30 bytes)
High:      0x00a8 - 0x0207 (352 bytes)

===================================
File: examples/hello-reference.z3
Size: 512 bytes
===================================

--- HEADER (first 64 bytes) ---
Version:           03 (3)
Flags 1:           0x00
Release:           0x0000 (0)
High memory:       0x00a4 (164)
Initial PC:        0x00a5 (165)
Dictionary:        0x0086 (134)
Object table:      0x0048 (72)
Global vars:       0x0040 (64)
Static memory:     0x0086 (134)
Flags 2:           0x0000
Serial:            '090708'
Abbreviations:     0x0040 (64)
File length (hdr): 0x0100 (*2 = 512 bytes)
Checksum:          0x0e88

=========================================
COMPARISON
=========================================

--- SIZE COMPARISON ---
File 1: 520 bytes
File 2: 512 bytes
Difference: 8 bytes (slightly larger)

--- BINARY DIFFERENCES ---
Total differences: 247 bytes
```

**Analysis:**
- Version correct ✓
- Size slightly larger (8 bytes) - minor issue
- High memory base different (168 vs 164) - layout difference
- PC different (169 vs 165) - layout difference
- Serial different (date stamps) - expected
- Checksum different - expected if anything else differs

**Verdict:** Probably OK! Layout differences are normal.

---

## Example 4: Critical Error - Wrong Version

```bash
$ ./verify-zfiles.sh

Verifying Z-machine files...

Checking: my-output.z3
  Size: 512 bytes
  ✗ Unknown version: 0x00
  Initial PC: 0x0000
  High mem: 0x0000
```

**Problem:** Version byte is 0x00 instead of 0x03
**Fix:** Write 0x03 as first byte

---

## Example 5: Critical Error - Invalid PC

```bash
$ ./inspect-zcode.sh my-output.z3

===================================
File: my-output.z3
Size: 512 bytes
===================================

--- HEADER (first 64 bytes) ---
Version:           03 (3)
High memory:       0x00a4 (164)
Initial PC:        0x0042 (66)  ← ERROR!
...

--- MEMORY LAYOUT ---
Dynamic:   0x0000 - 0x00a3 (164 bytes)
Static:    0x00a4 - ...
High:      0x00a4 - ...  ← PC should be here!
```

**Problem:** PC (0x0042) is in dynamic memory, should be in high memory (>= 0x00a4)
**Fix:** Set PC to point to your GO routine in high memory

---

## Example 6: Game Crashes When Running

```bash
$ frotz my-output.z3
Fatal error: Invalid opcode 0xff at address 0x00a5
```

**Problem:** Generated invalid opcode
**Check:**
```bash
$ xxd -s 0x00a5 -l 16 my-output.z3
000000a5: ff00 0000 0000 0000 0000 0000 0000 0000
```

**Analysis:** 0xff at PC - either didn't write code, or wrote wrong opcode
**Fix:** Verify code generation writes valid opcodes

---

## Example 7: Functional Test - It Works!

```bash
$ frotz my-output.z3
Hello, world!

$ echo $?
0
```

**Success!** Even if binary differs from reference, it works correctly.

---

## Example 8: Functional Test - Wrong Output

```bash
$ frotz my-output.z3
Hellod!

```

**Problem:** String encoding wrong (extra 'd', missing characters)
**Check:** Verify Z-character encoding implementation

---

## Example 9: Comparing Two Files

```bash
$ ./inspect-zcode.sh my-output.z3 examples/hello-reference.z3

...

--- HEADER DIFFERENCES ---
2,3c2,3
< 00000000: 0300 0001 00a8 00a9 008a 0048 0040 008a  ...........H.@..
< 00000010: 0000 3235 3031 3137 0040 0104 1234 0000  ..250117.@...4..
---
> 00000000: 0300 0000 00a4 00a5 0086 0048 0040 0086  ...........H.@..
> 00000010: 0000 3039 3037 3038 0040 0100 0e88 0000  ..090708.@......

--- FIRST 10 BINARY DIFFERENCES ---
Byte 3 (0x0003): 0 vs 1 (release number)
Byte 5 (0x0005): 168 vs 164 (high memory base)
Byte 7 (0x0007): 169 vs 165 (initial PC)
Byte 9 (0x0009): 138 vs 134 (dictionary addr)
...
```

**Analysis:**
- Minor differences in addresses (layout)
- Different release number (fine)
- Different serial (fine)

**Verdict:** Looks OK, test if it runs

---

## Example 10: Verbose Mode

```bash
$ ./compare-zcode.sh -c mycompiler -t hello -v

Testing: hello
Source: zilf/sample/hello/hello.zil
Reference: zilf/test/Dezapf.Tests/Resources/hello.z3
Compiling with mycompiler...
Reference size: 512 bytes
Output size: 512 bytes
✗ Files differ

Generating hex dumps...
Reference hex: hello_reference.hex
Output hex: hello_output.hex
To compare: diff hello_reference.hex hello_output.hex | less

Output file saved: output_hello.z3
```

Now you can do detailed hex comparison:
```bash
$ diff hello_reference.hex hello_output.hex | head -20
2,3c2,3
< 00000010: 0000 3039 3037 3038 0040 0100 0e88 0000  ..090708.@......
---
> 00000010: 0000 3235 3031 3137 0040 0100 1234 0000  ..250117.@...4..
```

---

## What to Look For

### Good Signs ✓
- Version is 0x03
- File size reasonable (within 20% of reference)
- PC is in high memory
- All addresses are within file bounds
- Game runs without crashing
- Output is correct

### Warning Signs (Maybe OK)
- Different file size (10-20% difference)
- Different memory layout
- Different checksums
- Different serials
- Different release numbers

### Bad Signs ✗
- Version not 0x03
- File much too large (>2x reference)
- File much too small (<50% reference)
- PC not in high memory
- Addresses out of bounds
- Game crashes immediately
- Wrong output

## Quick Diagnosis Flow

```
1. Does verify-zfiles.sh pass?
   NO → Fix header format
   YES → Continue

2. Does frotz load it?
   NO → Check PC, addresses
   YES → Continue

3. Does it produce output?
   NO → Check code generation
   YES → Continue

4. Is output correct?
   NO → Check string encoding, logic
   YES → SUCCESS!

5. Is file size reasonable?
   NO → Check for inefficiencies
   YES → SUCCESS!
```

## When to Worry vs When Not To

### Don't Worry About:
- Serial numbers differing
- Checksums differing
- Release numbers
- Exact addresses (if game works)
- Minor file size differences (<10%)
- String/routine ordering

### Do Worry About:
- Version wrong
- PC in wrong memory region
- File size radically different (>50%)
- Game crashes
- Wrong output
- Invalid opcodes

## Summary

Most compilers will NOT produce byte-identical output to the reference.
That's OK! Focus on:

1. Valid format (verify-zfiles.sh passes)
2. Runs without crashing
3. Produces correct output

Binary differences in layout, ordering, optimization are expected and fine.
