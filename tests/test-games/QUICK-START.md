# Quick Start: Testing Your ZIL Compiler

## What's Available

You now have test games with both ZIL source and compiled .z3 files:

### Smallest Tests (512 bytes)
- `zilf/test/Dezapf.Tests/Resources/hello.z3` (no source in repo, but see sample/hello/)
- `zilf/test/Dezapf.Tests/Resources/name.z3` (no source in repo)

### ZILF Samples (with source, no compiled)
- `zilf/sample/hello/hello.zil` - 5 lines of code
- `zilf/sample/cloak/cloak.zil` - Complete minimal game (~100 lines)
- `zilf/sample/beer/beer.zil` - 99 Bottles demo
- `zilf/sample/advent/` - Full Colossal Cave port

### Full Infocom Games (with source AND compiled .z3)
- `zork1/` - 14 .zil files → **zork1.z3** (86KB)
- `zork3/` - Complete game source → **zork3.z3**
- `enchanter/` - Complete game source → **enchanter.z3**

## How to Use

### Option 1: Manual Hex Comparison

```bash
# Compile with your compiler
your-compiler test-games/zork1/zork1.zil -o my-zork1.z3

# Compare hex dumps
xxd test-games/zork1/COMPILED/zork1.z3 > reference.hex
xxd my-zork1.z3 > mine.hex
diff reference.hex mine.hex | less
```

### Option 2: Use the Test Script

```bash
cd test-games

# Test single game
./compare-zcode.sh -c /path/to/your/compiler -t zork1

# Test all games
./compare-zcode.sh -c /path/to/your/compiler -a

# Verbose mode (generates hex dumps)
./compare-zcode.sh -c /path/to/your/compiler -t zork1 -v
```

### Option 3: Functional Testing

```bash
# Play the compiled game to see if it works
frotz my-zork1.z3

# Compare with reference
frotz test-games/zork1/COMPILED/zork1.z3
```

## What to Expect

### Perfect Match
If your compiler produces byte-identical output, the test script will show:
```
✓ Perfect match! Files are identical.
```

### Differences
More likely, you'll see:
```
✗ Files differ
First difference at:
Byte 64 (0x40): reference=0x1a output=0x1b
Total differences: 247 bytes
```

This is normal! Differences can be:
- **Header differences** - Compilation timestamps, version info
- **Layout differences** - Strings/routines in different order
- **Optimization differences** - Different but equivalent code
- **Bugs** - Your compiler generates wrong code

## Debugging Differences

1. **Check the header (first 64 bytes)**
   - Byte 0: Z-machine version (should be 3)
   - Bytes 4-5: High memory base
   - Bytes 6-7: Initial PC (program counter)
   - Use `infodump` or similar to decode

2. **Check memory layout**
   - Are strings in approximately the same place?
   - Are routines in a similar structure?
   
3. **Disassemble both files**
   - Use `txd` or Z-machine disassembler
   - Compare generated opcodes

4. **Play both versions**
   - Do they behave the same?
   - Functional equivalence > byte equivalence

## Recommended Order

1. Start with **hello.zil** from `zilf/sample/hello/` (5 lines)
2. Try **cloak.zil** (minimal complete game)
3. Attempt **zork1** (full game - 86KB)
4. Test **Planetfall** from `../games/planetfall/source/`

## See Also

- `README.md` - Overview of all test games
- `TEST-INVENTORY.md` - Detailed inventory and testing phases
- `compare-zcode.sh` - Automated comparison script

## Questions to Answer

- Does your compiler generate valid Z-machine format?
- Does the game run without crashing?
- Does it produce the same behavior as the reference?
- How close is the binary output to the reference?
- What optimizations cause differences?

Good luck!
