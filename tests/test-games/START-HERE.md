# START HERE - ZIL Compiler Test Suite

## You have a complete test suite for validating your ZIL compiler.

### What You Can Do Right Now

```bash
cd test-games

# See what's available
cat FINAL-SUMMARY.txt

# Test that everything works
./verify-zfiles.sh

# Look at a working .z3 file
./inspect-zcode.sh examples/hello-reference.z3

# See what the header should look like
xxd -l 64 examples/hello-reference.z3
```

### Three Ways to Use This Suite

#### 1. Quick Testing (Automated)
```bash
# Test your compiler against hello world
./compare-zcode.sh -c /path/to/your-compiler -t hello

# Test all games
./compare-zcode.sh -c /path/to/your-compiler -a
```

#### 2. Manual Inspection
```bash
# Compile manually
your-compiler examples/hello.zil -o my-hello.z3

# Inspect your output
./inspect-zcode.sh my-hello.z3

# Compare with reference
./inspect-zcode.sh my-hello.z3 examples/hello-reference.z3
```

#### 3. Functional Testing
```bash
# Play the reference
frotz examples/hello-reference.z3

# Play yours
frotz my-hello.z3

# Do they behave the same?
```

### Test Files Available

**Minimal Test (start here):**
- `examples/hello.zil` (86 bytes of source)
- `examples/hello-reference.z3` (512 bytes compiled)

**Full Games:**
- `examples/zork1.zil` → `examples/zork1-reference.z3` (86 KB)
- `examples/planetfall.zil` → `examples/planetfall-reference.z3` (107 KB)

Plus: Zork III and Enchanter in their respective directories.

### Documentation

**Start with these:**
1. `FINAL-SUMMARY.txt` - 2 minute overview
2. `QUICK-START.md` - First steps
3. `TESTING-GUIDE.md` - Complete workflow

**Reference materials:**
- `Z-MACHINE-HEADER-REF.md` - What the header should look like
- `COMMON-BUGS.md` - Recognize bugs by their signatures
- `INDEX.md` - Complete directory index

### Tools

Three bash scripts to help you:

1. **verify-zfiles.sh** - Is it valid Z-machine format?
2. **inspect-zcode.sh** - What's in the file?
3. **compare-zcode.sh** - How does it compare to reference?

### The Goal

Get your compiler to produce .z3 files that:
- ✓ Are valid Z-machine format
- ✓ Run without crashing (`frotz yourfile.z3`)
- ✓ Behave correctly

You don't need byte-for-byte matches! Functional equivalence is success.

### Next Steps

```bash
# 1. Read the summary
cat FINAL-SUMMARY.txt

# 2. Look at a working header
xxd -l 64 examples/hello-reference.z3

# 3. Read the header reference
cat Z-MACHINE-HEADER-REF.md

# 4. When you have a compiler, test it
./compare-zcode.sh -c your-compiler -t hello
```

### Questions?

- What should the header look like? → `Z-MACHINE-HEADER-REF.md`
- How do I test? → `QUICK-START.md`
- What's the workflow? → `TESTING-GUIDE.md`
- Why isn't it working? → `COMMON-BUGS.md`
- What files are available? → `INDEX.md`

Good luck!
