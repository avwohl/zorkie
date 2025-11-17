# Complete Testing Guide for Your ZIL Compiler

## Overview

This directory contains everything you need to test your ZIL compiler against known-good reference implementations. You have access to 5 complete test cases with both source ZIL and compiled .z3 files.

## Available Test Cases

### 1. hello.zil (86 bytes) - Minimal Test
- **Source**: `zilf/sample/hello/hello.zil`
- **Reference**: `zilf/test/Dezapf.Tests/Resources/hello.z3` (512 bytes)
- **Complexity**: Minimal - just prints "Hello, world!"
- **Use for**: Basic compiler smoke test
- **Code**:
```zil
<ROUTINE GO ()
    <PRINTI "Hello, world!">
    <CRLF>>
```

### 2. Zork I (14 files) - Large Classic Game
- **Source**: `zork1/*.zil` (multiple files, main: `zork1/zork1.zil`)
- **Reference**: `zork1/COMPILED/zork1.z3` (86,838 bytes)
- **Version**: Z3, Release 119, Serial 880429
- **Complexity**: High - full commercial game
- **Use for**: Comprehensive validation

### 3. Zork III - Another Classic
- **Source**: `zork3/*.zil`
- **Reference**: `zork3/COMPILED/zork3.z3` (87,984 bytes)
- **Complexity**: High

### 4. Enchanter - Different Style
- **Source**: `enchanter/*.zil`
- **Reference**: `enchanter/COMPILED/enchanter.z3` (111,126 bytes)
- **Version**: Z3, Release 29, Serial 860820
- **Complexity**: High

### 5. Planetfall - Your Project
- **Source**: `../games/planetfall/source/*.zil`
- **Reference**: `../games/planetfall/source/COMPILED/planetfall.z3` (107KB)
- **Complexity**: High
- **Use for**: Testing your specific compiler against the game you're working on

## Testing Tools

### 1. verify-zfiles.sh - Validate Z-machine Format
Checks that .z3 files are valid Z-machine files.

```bash
./verify-zfiles.sh
```

Output shows version, PC address, memory layout for each file.

### 2. inspect-zcode.sh - Detailed Bytecode Analysis
Analyzes Z-machine header and structure in detail.

```bash
# Inspect single file
./inspect-zcode.sh zork1/COMPILED/zork1.z3

# Compare two files
./inspect-zcode.sh your-output.z3 zork1/COMPILED/zork1.z3
```

Output includes:
- Header analysis (version, flags, addresses)
- Memory layout (dynamic, static, high)
- Key addresses (object table, dictionary, globals)
- Hex dump of first 128 bytes
- Binary comparison (if two files)

### 3. compare-zcode.sh - Automated Test Suite
Compiles your code and compares against reference.

```bash
# Test single game
./compare-zcode.sh -c /path/to/your-compiler -t zork1

# Test specific cases
./compare-zcode.sh -c /path/to/your-compiler -t hello
./compare-zcode.sh -c /path/to/your-compiler -t planetfall

# Test all games
./compare-zcode.sh -c /path/to/your-compiler -a

# Verbose mode (generates hex dumps)
./compare-zcode.sh -c /path/to/your-compiler -t zork1 -v
```

Available tests: `hello`, `zork1`, `zork3`, `enchanter`, `planetfall`

## Testing Workflow

### Phase 1: Basic Compilation
Start with the simplest test to verify your compiler works at all.

```bash
# Try to compile hello.zil
your-compiler zilf/sample/hello/hello.zil -o my-hello.z3

# Check if it's valid Z-machine format
./verify-zfiles.sh my-hello.z3

# Play it
frotz my-hello.z3
```

### Phase 2: Binary Comparison
Compare your output against the reference.

```bash
# Inspect the reference
./inspect-zcode.sh zilf/test/Dezapf.Tests/Resources/hello.z3

# Inspect yours
./inspect-zcode.sh my-hello.z3

# Compare both
./inspect-zcode.sh my-hello.z3 zilf/test/Dezapf.Tests/Resources/hello.z3
```

Look for:
- **Header differences**: Are version, addresses correct?
- **Size differences**: How much larger/smaller is yours?
- **Byte-level differences**: Where do they diverge?

### Phase 3: Functional Testing
Even if binary differs, does it work?

```bash
# Play both versions
frotz zilf/test/Dezapf.Tests/Resources/hello.z3
frotz my-hello.z3

# Do they behave the same?
```

### Phase 4: Larger Tests
Graduate to full games.

```bash
# Test Zork I
./compare-zcode.sh -c your-compiler -t zork1 -v

# Check what's different
./inspect-zcode.sh output_zork1.z3 zork1/COMPILED/zork1.z3
```

### Phase 5: Planetfall Validation
Test against your actual target game.

```bash
./compare-zcode.sh -c your-compiler -t planetfall -v
```

## Understanding Differences

### Types of Differences

1. **Header Differences**
   - Serial number (date stamp) - expected
   - Release number - may differ
   - Checksum - will differ if anything differs
   - Addresses - serious if different

2. **Layout Differences**
   - Strings in different order - ok, just optimization
   - Routines in different order - ok
   - Different memory sizes - check if valid

3. **Code Differences**
   - Different opcodes - likely bug
   - Different operands - likely bug
   - Different branch targets - could be layout related

4. **Data Differences**
   - Dictionary order - usually ok
   - Object table structure - must match exactly
   - Abbreviations - order may vary

### What to Check First

When your output differs from reference:

1. **Check file size**
   - Much larger? May have inefficient string storage or code gen
   - Much smaller? May be missing data

2. **Check header addresses**
   ```bash
   ./inspect-zcode.sh your-output.z3 reference.z3 | grep "HEADER DIFFERENCES"
   ```
   - Dictionary, object table, globals must be valid addresses
   - PC (initial address) must point to valid code

3. **Check if it runs**
   ```bash
   frotz your-output.z3
   ```
   - Does it start?
   - Does it crash?
   - Does it behave correctly?

4. **Compare hex dumps**
   ```bash
   xxd reference.z3 > ref.hex
   xxd your-output.z3 > yours.hex
   diff ref.hex yours.hex | less
   ```
   - Look for patterns in differences
   - Are they concentrated in specific areas?

## Example Testing Session

```bash
# 1. Verify test suite is ready
./verify-zfiles.sh

# 2. Test hello world
./compare-zcode.sh -c ../build/zilc -t hello -v

# 3. If differences found, inspect
./inspect-zcode.sh output_hello.z3 zilf/test/Dezapf.Tests/Resources/hello.z3

# 4. Check header in detail
xxd -l 64 output_hello.z3 > my-header.hex
xxd -l 64 zilf/test/Dezapf.Tests/Resources/hello.z3 > ref-header.hex
diff my-header.hex ref-header.hex

# 5. Play both to see functional difference
echo "Reference:"
frotz zilf/test/Dezapf.Tests/Resources/hello.z3
echo "Yours:"
frotz output_hello.z3

# 6. If hello works, try full game
./compare-zcode.sh -c ../build/zilc -t zork1 -v
```

## Debugging Tips

### My compiler crashes
1. Check ZIL syntax is valid: look at working examples
2. Check lexer handles all tokens
3. Add debug output to see where it fails

### Output file is empty or invalid
1. Check file write permissions
2. Verify header generation code
3. Make sure all sections are written (header, dict, code, etc.)

### Output is much larger than reference
1. Check string storage - duplicates?
2. Check code generation - inefficient opcodes?
3. Check dictionary - too many entries?

### Output is much smaller
1. Missing abbreviations table?
2. Missing object table?
3. Missing dictionary entries?

### Game crashes on start
1. Check initial PC points to valid routine
2. Check stack setup
3. Check global variable initialization

### Game crashes during play
1. Check branch offsets are correct
2. Check call addresses are correct
3. Check store operations are valid

## Expected Results

Don't expect perfect byte-for-byte matches initially. Even different versions of ZILF produce different output. Focus on:

### Must Have
- Valid Z-machine format
- Correct header structure
- Game runs without crashing
- Game behaves correctly

### Nice to Have
- Similar file size to reference
- Similar memory layout
- Similar code structure

### Don't Worry About
- Exact byte matches
- String/routine ordering
- Minor optimization differences
- Serial numbers/checksums

## Next Steps

1. Start with `hello.zil` - get this working first
2. Debug any differences using the inspect tools
3. Graduate to Zork I or Planetfall
4. Iterate until you get functional equivalence
5. Refine for better optimization/matching

## Resources

- Z-machine spec: https://www.inform-fiction.org/zmachine/standards/
- ZILF documentation: https://foss.heptapod.net/zilf/zilf/-/wikis/home
- Play games: `frotz` Z-machine interpreter
- Hex editor: `xxd` for viewing binary files
- Disassembly: `txd` (if available) for viewing Z-code

Good luck!
