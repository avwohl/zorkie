# Test Games for ZIL Compiler Comparison

This directory contains reference games with both ZIL source code and compiled .z files for testing compiler output.

## Available Test Games

### Infocom Games (with official compiled .z files)

1. **Zork I** - `zork1/`
   - Source: `zork1/*.zil`
   - Compiled: `zork1/COMPILED/zork1.z3`
   - Version: Z3
   - Notes: Classic text adventure, good comprehensive test

2. **Zork III** - `zork3/`
   - Source: `zork3/*.zil`
   - Compiled: `zork3/COMPILED/zork3.z3`
   - Version: Z3

3. **Enchanter** - `enchanter/`
   - Source: `enchanter/*.zil`
   - Compiled: `enchanter/COMPILED/enchanter.z3`
   - Version: Z3
   - Notes: Different style than Zork series

### ZILF Sample Games

4. **ZILF Samples** - `zilf/sample/`
   - hello - Simple hello world
   - cloak - Cloak of Darkness (minimal test game)
   - beer - 99 Bottles of Beer
   - dragon - Simple adventure
   - advent - Colossal Cave Adventure port
   - mandelbrot - Mathematical demo
   
   Note: ZILF samples don't include pre-compiled .z files - you need to build them with ZILF first.

### ZILF Test Suite

5. **ZILF Tests** - `zilf/test/Dezapf.Tests/Resources/`
   - hello.z3, name.z3 - Minimal test cases with compiled output

## Testing Strategy

1. Start with minimal tests (hello, name from ZILF tests)
2. Test simple games (cloak, beer)
3. Compare against full Infocom games (Zork I, Enchanter)
4. Use hexdiff to compare binary output
5. Use z-machine disassemblers to compare generated code

## Usage

To compare your compiler output:

```bash
# Compile with your compiler
./your-compiler test-games/zork1/zork1.zil -o output.z3

# Compare with reference
hexdump -C test-games/zork1/COMPILED/zork1.z3 > reference.hex
hexdump -C output.z3 > yours.hex
diff reference.hex yours.hex
```

## Notes

- All Infocom games were compiled with the original ZIL compiler (circa 1985-1989)
- These serve as "gold standard" reference implementations
- ZILF can also compile these with minor modifications
- Planetfall source is in `../games/planetfall/source/`
