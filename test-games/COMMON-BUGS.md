# Common ZIL Compiler Bugs and Their Signatures

This guide helps you recognize common compiler bugs by looking at the output .z3 file.

## Header Bugs

### Bug: Zero or Invalid Version Number
**Symptom:**
```
00000000: 0000 0077 4b54 50d5 ...
          ^^^^
```
**Cause:** Forgot to write version byte, or wrote 0 instead of 3

**Fix:** Ensure first byte is `0x03` for Z-machine V3

**Detection:**
```bash
xxd -l 1 -p yourfile.z3
# Should output: 03
```

---

### Bug: File Length Mismatch
**Symptom:**
```
File size: 86838 bytes
Header bytes 26-27: 0x0001 (means 2 bytes)
```

**Cause:**
- Wrote actual length instead of (length / 2)
- Didn't update header after writing file
- Off-by-one in calculation

**Fix:** Byte 26-27 should be (file_size / 2) as big-endian uint16

**Detection:**
```bash
./verify-zfiles.sh yourfile.z3
# Will show mismatch
```

---

### Bug: Invalid Initial PC
**Symptom:**
```
Initial PC: 0x0042 (byte 66)
High memory base: 0x4b54 (byte 19284)
```

**Cause:** PC points to dynamic/static memory instead of high memory

**Fix:** PC must be >= high memory base, and point to a valid routine

**Result:** Game crashes immediately on start

---

### Bug: Overlapping Memory Regions
**Symptom:**
```
Globals at: 0x0100 (size: 480 bytes, ends at 0x02e0)
Object table at: 0x0200
```

**Cause:** Tables placed without considering their sizes

**Fix:** Each table must start after previous one ends
- Globals need 480 bytes (240 * 2)
- Object table size depends on number of objects
- Dictionary size depends on vocabulary

---

## Code Generation Bugs

### Bug: Wrong Opcode Count
**Symptom:** Game crashes on certain commands

**Cause:**
- Generated 1OP opcode but should be 2OP
- Wrong opcode number entirely

**Detection:** Disassemble and compare with reference
```bash
# If you have txd or similar disassembler
txd yourfile.z3 > yours.asm
txd reference.z3 > ref.asm
diff yours.asm ref.asm
```

---

### Bug: Branch Offset Wrong
**Symptom:**
- Game crashes during conditionals
- Infinite loops
- Skipping code incorrectly

**Cause:**
- Calculated offset from wrong position
- Forgot that offset is from *after* branch instruction
- Wrong offset encoding (1-byte vs 2-byte)

**Example of correct branch:**
```
Address 0x5000: je a b ?label
Branch offset: 0x20 (32 bytes forward)
Target: 0x5000 + instruction_length + 32
```

---

### Bug: Call Address Wrong
**Symptom:** Game crashes when calling routines

**Cause:**
- Routine address not packed (should be byte_addr / 2 in V3)
- Called absolute address instead of packed address
- Typo in routine table

**Fix:** For V3, routine addresses are stored as (byte_address / 2)
```
Routine at byte 0x5000 → store as 0x2800 in call instruction
```

---

### Bug: String References Wrong
**Symptom:**
- Garbage text printed
- Crash when printing

**Cause:**
- String address not packed correctly
- String not null-terminated properly
- Wrong ZSCII encoding

**Fix:** String addresses are packed (byte_addr / 2) in V3

---

## Data Structure Bugs

### Bug: Object Table Malformed
**Symptom:**
- "get" command doesn't work
- Room descriptions missing
- Objects not visible

**Cause:**
- Property defaults not 31 entries
- Object entries wrong size
- Parent/sibling/child pointers wrong

**Object table format (V3):**
```
Offset  Content
------  --------------------------------
0-61    Property defaults (31 * 2 bytes)
62+     Object entries (9 bytes each)
        - 4 bytes: attributes (32 flags)
        - 1 byte: parent object number
        - 1 byte: sibling object number
        - 1 byte: child object number
        - 2 bytes: property table address
```

**Detection:**
```bash
./inspect-zcode.sh yourfile.z3
# Check "Object table starts at" address
xxd -s <address> -l 100 yourfile.z3
# Should see property defaults, then object entries
```

---

### Bug: Dictionary Malformed
**Symptom:**
- Parser doesn't recognize words
- "I don't understand" for everything
- Crash on parsing

**Cause:**
- Wrong word separator count
- Wrong entry length
- Words not sorted alphabetically
- Wrong number of entries

**Dictionary format (V3):**
```
Offset  Content
------  --------------------------------
0       Number of word separators
1-n     Word separator characters
n+1     Entry length (bytes per word)
n+2-3   Number of entries (signed 16-bit)
        If positive: entries are sorted
        If negative: |value| entries, not sorted
n+4+    Dictionary entries
```

**Each entry (V3):**
```
Bytes 0-3: Encoded word (6 ZSCII chars in 4 bytes)
Bytes 4+:  User data (entry_length - 4 bytes)
```

---

### Bug: Abbreviations Wrong
**Symptom:**
- Frequent words cause crashes
- Garbage in common phrases

**Cause:**
- Wrong number of abbreviation tables (should be 3 in V3)
- Entries not packed addresses
- Pointing to non-string data

**Format:**
```
32 entries × 3 tables = 96 entries total
Each entry: 2 bytes (packed string address)
Total size: 192 bytes minimum
```

---

### Bug: Global Variables Wrong
**Symptom:**
- Game state corrupted
- Variables have wrong values
- Crashes during gameplay

**Cause:**
- Not allocated 480 bytes (240 globals × 2 bytes)
- Initial values wrong
- Address misaligned

---

## String Encoding Bugs

### Bug: Wrong ZSCII Encoding
**Symptom:** Text displays incorrectly

**Cause:**
- Didn't convert to ZSCII alphabet
- Wrong alphabet table
- Forgot special characters

**V3 Alphabets:**
```
A0: abcdefghijklmnopqrstuvwxyz
A1: ABCDEFGHIJKLMNOPQRSTUVWXYZ
A2: <newline>0123456789.,!?_#'"/\-:()
```

---

### Bug: String Not Terminated
**Symptom:** String continues with garbage

**Cause:** Didn't set bit 15 of last 2-byte word

**Format:**
```
Each string is sequence of 2-byte words
Last word has bit 15 set:
  Normal word: 0x1234
  Last word:   0x9234 (bit 15 = 1)
```

---

### Bug: Packed String Address Wrong
**Symptom:** Wrong text or crash

**Cause:** Not dividing byte address by 2

**Fix:**
```
String at byte 0x6000 in file
→ Store as 0x3000 in instruction
```

---

## Testing Each Component

### Test Header
```bash
./inspect-zcode.sh yourfile.z3
# Look for:
# - Version = 3
# - All addresses in bounds
# - File length matches
# - Memory regions don't overlap
```

### Test Strings
```bash
# Extract a string and decode it
xxd -s <address> -l 20 yourfile.z3
# Should see ZSCII encoded text
```

### Test Objects
```bash
# Go to object table address
xxd -s <obj_table> -l 100 yourfile.z3
# First 62 bytes: property defaults
# Then 9 bytes per object
```

### Test Dictionary
```bash
# Go to dictionary address
xxd -s <dict> -l 200 yourfile.z3
# Check format matches spec
```

### Test Code
```bash
# Go to initial PC
xxd -s <PC> -l 50 yourfile.z3
# Should see valid Z-machine opcodes
```

## Size Heuristics

If your output size is way off from reference:

**Much larger (>20% bigger):**
- Duplicate strings not deduplicated
- Inefficient opcode choices
- Not using abbreviations
- Padding waste

**Much smaller (<20% smaller):**
- Missing abbreviations table
- Missing dictionary entries
- Missing object properties
- Incomplete code generation

**Example sizes (V3):**
- hello.zil: ~512 bytes (minimal)
- cloak.zil: ~4-8 KB (small game)
- Zork I: ~87 KB (full game)
- Planetfall: ~107 KB (full game)

## Debugging Workflow

1. **Compare file sizes**
   ```bash
   ls -lh yourfile.z3 reference.z3
   ```

2. **Check header**
   ```bash
   ./inspect-zcode.sh yourfile.z3 reference.z3
   ```

3. **Find first difference**
   ```bash
   cmp -l yourfile.z3 reference.z3 | head -1
   ```

4. **Examine that area**
   ```bash
   # If difference at byte 100
   xxd -s 96 -l 32 yourfile.z3
   xxd -s 96 -l 32 reference.z3
   ```

5. **Identify what's there**
   - In header (0-63)? Header bug
   - In abbreviations? Abbrev table bug
   - In globals? Initial values wrong
   - In object table? Object structure bug
   - In dictionary? Dictionary bug
   - In code? Code generation bug

6. **Test functionally**
   ```bash
   frotz yourfile.z3
   # Does it start? Where does it crash?
   ```

## Common Crash Points and Causes

**Crash on start:**
- Invalid PC
- First routine malformed
- Stack setup wrong

**Crash on first command:**
- Dictionary broken
- Parser routine wrong
- String decoding broken

**Crash on "look":**
- Object table wrong
- Room description string bad
- Property lookup broken

**Crash on "take":**
- Object manipulation wrong
- Parent/child pointers bad
- Inventory code broken

**Crash randomly:**
- Memory corruption
- Branch offsets wrong
- Call addresses wrong
- Stack operations wrong

## Quick Diagnosis Commands

```bash
# Is it valid Z-machine?
./verify-zfiles.sh yourfile.z3

# What's in the header?
xxd -l 64 yourfile.z3

# Does it match reference header?
diff <(xxd -l 64 yourfile.z3) <(xxd -l 64 reference.z3)

# Where's the first difference?
cmp -l yourfile.z3 reference.z3 | head -1

# Full comparison
./inspect-zcode.sh yourfile.z3 reference.z3

# Try to run it
frotz yourfile.z3
```

## Good Luck!

Use these patterns to quickly identify where your compiler is going wrong.
