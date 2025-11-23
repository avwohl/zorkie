# Test Game Inventory

## Summary

Downloaded test games with both ZIL source and compiled .z files for comparison testing.

## Files Available for Testing

### Small Test Cases (Start Here)

1. **hello.zil** → **hello.z3**
   - Location: `zilf/test/Dezapf.Tests/Resources/`
   - Size: ~hundreds of bytes
   - Complexity: Minimal
   - Good for: Basic compiler smoke test

2. **name.zil** → **name.z3**
   - Location: `zilf/test/Dezapf.Tests/Resources/`
   - Size: ~hundreds of bytes
   - Complexity: Minimal
   - Good for: Basic input/output test

### ZILF Sample Games (Need to Compile)

Located in `zilf/sample/`:
- **hello.zil** - Hello world
- **beer.zil** - 99 Bottles of Beer
- **cloak.zil** - Cloak of Darkness (minimal IF)
- **cloak_plus.zil** - Enhanced version
- **dragon.zil** - Simple adventure
- **advent/** - Colossal Cave Adventure (complex)
- **mandelbrot.zil** - Mathematical demo

Note: These don't have pre-compiled .z files - you'd need ZILF to create reference versions.

### Full Infocom Games (Large Tests)

1. **Zork I**
   - Source: `zork1/*.zil` (multiple files)
   - Main file: `zork1/gmain.zil`
   - Compiled: `zork1/COMPILED/zork1.z3`
   - Size: 86,838 bytes
   - Version: Z3
   - Files: 14 .zil files
   - Complexity: High - full commercial game

2. **Zork III**
   - Source: `zork3/*.zil`
   - Compiled: `zork3/COMPILED/zork3.z3`
   - Version: Z3
   - Complexity: High

3. **Enchanter**
   - Source: `enchanter/*.zil`
   - Compiled: `enchanter/COMPILED/enchanter.z3`
   - Also includes: `enchanter/COMPILED/z4.z3`
   - Version: Z3/Z4
   - Complexity: High
   - Good for: Different game style than Zork

### Your Game

4. **Planetfall**
   - Source: `../games/planetfall/source/*.zil`
   - Compiled: Need to find reference .z3
   - Version: Z3
   - Status: You've been working on this

## Recommended Testing Order

### Phase 1: Minimal Tests
Start with the smallest, simplest files to verify basic compilation:
```bash
cd test-games
./compare-zcode.sh -c ../your-compiler -t hello
./compare-zcode.sh -c ../your-compiler -t name
```

### Phase 2: ZILF Samples
Compile ZILF samples with ZILF first to create reference files, then test:
```bash
# First compile with ZILF to create reference
cd zilf/sample/cloak
zilf cloak.zil
# Then test your compiler against ZILF output
```

### Phase 3: Full Games
Test against complete Infocom games:
```bash
./compare-zcode.sh -c ../your-compiler -t zork1
./compare-zcode.sh -c ../your-compiler -t enchanter
```

### Phase 4: All Tests
```bash
./compare-zcode.sh -c ../your-compiler -a
```

## What to Check

### Header Comparison
The Z-machine header (first 64 bytes) contains:
- Version number (byte 0)
- High memory base (bytes 4-5)
- Initial PC (bytes 6-7)
- Dictionary location (bytes 8-9)
- Object table location (bytes 10-11)
- Global variables (bytes 12-13)
- Static memory base (bytes 14-15)
- etc.

### Memory Layout
Compare:
- Where routines are placed
- Where strings are placed
- Object table structure
- Dictionary structure
- Abbreviations table

### Code Generation
For identical source, check:
- Same opcodes generated
- Same operand types
- Same branch offsets
- Same string references

## Notes

- **Perfect match**: Your compiler generates byte-identical output
- **Partial match**: Functionally equivalent but different layout (strings in different order, etc.)
- **Semantic match**: Game plays the same but compiled differently

Don't expect perfect matches initially - even different versions of ZILF produce slightly different output. Focus on:
1. Valid Z-machine format
2. Game runs correctly
3. Gradually converge toward reference implementation

## Tools You Might Need

- **hexdump** / **xxd** - View binary files
- **cmp** - Compare binary files
- **diff** - Compare hex dumps
- **txd** - Z-machine disassembler (if available)
- **frotz** - Play/test .z files
- **infodump** - Dump Z-machine file structure

## Next Steps

1. Get your compiler to a point where it can output .z3 files
2. Start with `hello.z3` comparison
3. Use hex diff to see where your output diverges
4. Iterate until you get matches
5. Graduate to larger games
