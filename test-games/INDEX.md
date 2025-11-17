# Test Games Directory - Complete Index

## Start Here

**New to this test suite?** Read these in order:
1. **FINAL-SUMMARY.txt** - 2 minute overview
2. **QUICK-START.md** - How to run your first test
3. **TESTING-GUIDE.md** - Complete workflow

**Ready to test?** Use the `examples/` directory:
```bash
# Quick access to test files
ls examples/

# hello.zil + hello-reference.z3
# zork1.zil + zork1-reference.z3
# planetfall.zil + planetfall-reference.z3
```

## Documentation (Read These)

### Getting Started
- **FINAL-SUMMARY.txt** (5.6K) - Overview of everything
- **QUICK-START.md** (3.4K) - How to begin testing
- **README.md** (2.1K) - General information

### Testing & Debugging
- **TESTING-GUIDE.md** (8.1K) - Complete testing workflow
- **COMMON-BUGS.md** (10K) - Recognize bugs by their signatures
- **Z-MACHINE-HEADER-REF.md** (8K) - Header format reference

### Reference
- **TEST-INVENTORY.md** (4.1K) - Catalog of all test cases
- **SUMMARY.txt** (1.8K) - Quick reference card

## Tools (Run These)

### Automated Testing
```bash
./compare-zcode.sh -c /path/to/compiler -t <test>
```
- Compiles your code
- Compares against reference
- Shows differences
- Tests: hello, zork1, zork3, enchanter, planetfall

### Bytecode Analysis
```bash
./inspect-zcode.sh <file1.z3> [file2.z3]
```
- Deep header analysis
- Memory layout inspection
- Binary comparison
- Hex dump first 128 bytes

### Format Validation
```bash
./verify-zfiles.sh
```
- Validates all .z3 files
- Checks version, PC, memory layout
- Quick sanity check

## Test Cases

### Minimal (Start Here)
**hello.zil** → **hello.z3** (512 bytes)
- Source: `zilf/sample/hello/hello.zil` (86 bytes)
- Reference: `zilf/test/Dezapf.Tests/Resources/hello.z3`
- Also: `examples/hello.zil`, `examples/hello-reference.z3`
- Use for: Initial smoke test

### Full Games (Validate Completeness)

**Zork I** → **zork1.z3** (86,838 bytes)
- Source: `zork1/*.zil` (14 files)
- Reference: `zork1/COMPILED/zork1.z3`
- Also: `examples/zork1.zil`, `examples/zork1-reference.z3`
- V3, Release 119, Serial 880429
- Use for: Complex multi-file test

**Zork III** → **zork3.z3** (87,984 bytes)
- Source: `zork3/*.zil`
- Reference: `zork3/COMPILED/zork3.z3`
- Use for: Another large test case

**Enchanter** → **enchanter.z3** (111,126 bytes)
- Source: `enchanter/*.zil`
- Reference: `enchanter/COMPILED/enchanter.z3`
- V3, Release 29, Serial 860820
- Use for: Different game structure

**Planetfall** → **planetfall.z3** (107,520 bytes)
- Source: `../games/planetfall/source/*.zil`
- Reference: `../games/planetfall/source/COMPILED/planetfall.z3`
- Also: `examples/planetfall.zil`, `examples/planetfall-reference.z3`
- Use for: Your target game

## Additional Resources

### ZILF Sample Games (source only, no .z3)
Located in `zilf/sample/`:
- **beer.zil** (692 bytes) - 99 Bottles loop
- **cloak.zil** (3.2K) - Complete minimal game
- **dragon.zil** (8.4K) - Simple adventure
- **advent/** (182K) - Colossal Cave port
- **mandelbrot.zil** (2.6K) - Math demo

### ZILF Compiler Source
Located in `zilf/`:
- Full ZILF compiler source code (C#/.NET)
- Reference implementation
- Documentation in `zilf/doc/`
- Libraries in `zilf/zillib/`

## Quick Commands Reference

### Test Your Compiler
```bash
# Single test
./compare-zcode.sh -c your-compiler -t hello

# All tests
./compare-zcode.sh -c your-compiler -a

# With verbose output
./compare-zcode.sh -c your-compiler -t zork1 -v
```

### Inspect Output
```bash
# View header
xxd -l 64 yourfile.z3

# Detailed analysis
./inspect-zcode.sh yourfile.z3

# Compare with reference
./inspect-zcode.sh yourfile.z3 reference.z3

# Validate format
./verify-zfiles.sh
```

### Debug Differences
```bash
# Find first difference
cmp -l yourfile.z3 reference.z3 | head -1

# Full hex diff
diff <(xxd yourfile.z3) <(xxd reference.z3) | less

# Test functionally
frotz yourfile.z3
```

## Directory Structure

```
test-games/
│
├── Documentation (Read)
│   ├── INDEX.md (this file)
│   ├── FINAL-SUMMARY.txt - Start here
│   ├── QUICK-START.md - How to test
│   ├── TESTING-GUIDE.md - Complete workflow
│   ├── COMMON-BUGS.md - Debug guide
│   ├── Z-MACHINE-HEADER-REF.md - Header reference
│   ├── TEST-INVENTORY.md - Test catalog
│   ├── README.md - Overview
│   └── SUMMARY.txt - Quick ref
│
├── Tools (Run)
│   ├── compare-zcode.sh - Automated testing
│   ├── inspect-zcode.sh - Bytecode analysis
│   └── verify-zfiles.sh - Format validation
│
├── Quick Access
│   └── examples/
│       ├── hello.zil + hello-reference.z3
│       ├── zork1.zil + zork1-reference.z3
│       └── planetfall.zil + planetfall-reference.z3
│
├── Test Cases (Full)
│   ├── zork1/ - Zork I (86KB)
│   │   ├── *.zil (14 source files)
│   │   └── COMPILED/zork1.z3
│   │
│   ├── zork3/ - Zork III (88KB)
│   │   ├── *.zil
│   │   └── COMPILED/zork3.z3
│   │
│   ├── enchanter/ - Enchanter (111KB)
│   │   ├── *.zil
│   │   └── COMPILED/enchanter.z3
│   │
│   └── zilf/ - ZILF source + samples
│       ├── sample/hello/hello.zil (86 bytes)
│       ├── sample/cloak/cloak.zil (3.2K)
│       ├── sample/beer/beer.zil
│       ├── sample/dragon/dragon.zil
│       ├── sample/advent/advent.zil (182K)
│       └── test/Dezapf.Tests/Resources/
│           ├── hello.z3 (512 bytes)
│           └── name.z3 (1KB)
│
└── Planetfall (Your Project)
    Location: ../games/planetfall/source/
    ├── planetfall.zil + other .zil files
    └── COMPILED/planetfall.z3 (107KB)
```

## Recommended Learning Path

### Day 1: Setup & First Test
1. Read FINAL-SUMMARY.txt (5 min)
2. Read QUICK-START.md (10 min)
3. Run verify-zfiles.sh to check test suite (1 min)
4. Try inspect-zcode.sh on hello.z3 (5 min)
5. Read Z-MACHINE-HEADER-REF.md (20 min)

**Goal:** Understand what a valid .z3 file looks like

### Day 2: First Compilation
1. Get your compiler to generate *something*
2. Run: `./verify-zfiles.sh your-output.z3`
3. Run: `./inspect-zcode.sh your-output.z3`
4. Compare: `./inspect-zcode.sh your-output.z3 examples/hello-reference.z3`
5. Read COMMON-BUGS.md relevant sections

**Goal:** Valid header and file structure

### Day 3: Hello World Works
1. Debug until hello.z3 runs: `frotz your-hello.z3`
2. Compare outputs with reference
3. Run: `./compare-zcode.sh -c your-compiler -t hello`

**Goal:** Functional hello world

### Day 4-7: Larger Tests
1. Try Zork I or Planetfall
2. Use tools to debug differences
3. Iterate until functionally equivalent

**Goal:** Full game compilation

## Success Criteria

### Phase 1: Valid Format
- [ ] verify-zfiles.sh shows valid header
- [ ] File size is reasonable
- [ ] All addresses in bounds

### Phase 2: Runs Without Crashing
- [ ] frotz loads the file
- [ ] Game starts
- [ ] Doesn't crash immediately

### Phase 3: Functionally Correct
- [ ] Game behaves like reference
- [ ] Commands work
- [ ] Text displays correctly

### Phase 4: Optimized
- [ ] File size similar to reference
- [ ] Memory layout efficient
- [ ] Code generation clean

Don't expect to achieve Phase 4 immediately! Phase 3 is success.

## Getting Help

1. Check COMMON-BUGS.md for your symptoms
2. Use inspect-zcode.sh to find differences
3. Compare hex dumps of problem areas
4. Test incrementally (hello → zork → planetfall)

## All Files at a Glance

**Documentation:**
- INDEX.md (this file)
- FINAL-SUMMARY.txt
- QUICK-START.md
- TESTING-GUIDE.md
- COMMON-BUGS.md
- Z-MACHINE-HEADER-REF.md
- TEST-INVENTORY.md
- README.md
- SUMMARY.txt

**Tools:**
- compare-zcode.sh
- inspect-zcode.sh
- verify-zfiles.sh

**Test References:**
- examples/hello-reference.z3 (512 B)
- examples/zork1-reference.z3 (86 KB)
- examples/planetfall-reference.z3 (107 KB)
- zork3/COMPILED/zork3.z3 (88 KB)
- enchanter/COMPILED/enchanter.z3 (111 KB)

**Sources:**
- examples/hello.zil (86 B)
- examples/zork1.zil (→ 14 files)
- examples/planetfall.zil (→ multiple files)
- zilf/sample/*.zil (11 sample games)
- All game source directories

---

**You're all set!** Start with FINAL-SUMMARY.txt and work your way through.
