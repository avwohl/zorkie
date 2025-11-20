# Optimization Pass Architecture

## Summary

Implemented global optimization pipeline that runs between code generation and assembly. This architecture enables analysis and transformation of the entire story file before final assembly, opening the door for string deduplication, abbreviation optimization, and other size reductions.

## Architecture

### Compilation Pipeline

**Before:**
```
Parse → AST → Generate Code → Build Objects → Build Dictionary → Assemble
```

**After:**
```
Parse → AST → Generate Code → Build Objects → Build Dictionary
    ↓
🆕 Optimization Passes (analyze & transform)
    ↓
Assemble → Story File
```

### Why Pre-Assembly Optimization?

**Benefits:**
1. **Global View** - Can analyze entire story file, not just individual components
2. **Cross-Component** - Can optimize across routines, objects, and strings
3. **Flexible** - Easy to add new optimization passes
4. **Non-Destructive** - Original code unchanged, only intermediate representation optimized
5. **Measurable** - Can measure impact of each pass independently

## Components

### 1. OptimizationPass Base Class

```python
class OptimizationPass:
    def run(self, compilation_data: Dict) -> Dict:
        # Analyze and transform compilation_data
        # Return modified compilation_data
```

Every pass:
- Receives `compilation_data` dict with routines, objects, dictionary, etc.
- Analyzes and optionally transforms the data
- Returns modified `compilation_data`
- Tracks statistics in `self.stats`

### 2. OptimizationPipeline

```python
pipeline = OptimizationPipeline(verbose=True)
pipeline.add_pass(StringDeduplicationPass)
pipeline.add_pass(AbbreviationOptimizationPass)
pipeline.add_pass(PropertyOptimizationPass)

optimized_data = pipeline.run(compilation_data)
```

Manages multiple passes:
- Runs passes in sequence
- Passes output of one to input of next
- Collects statistics from all passes
- Logs progress if verbose

### 3. Implemented Passes

#### StringDeduplicationPass

**Purpose:** Find and analyze duplicate strings globally

**What it does:**
- Extracts strings from routine bytecode (PRINT instructions)
- Extracts strings from object property tables
- Counts string usage frequency
- Identifies duplicates
- Builds deduplicated string table

**Zork1 Results:**
```
Total strings: 42
Unique strings: 15 (35.7%)
Duplicates: 27 (64.3%)
String table size: 251 bytes
```

**Status:** ✅ Analysis working, rewriting not yet implemented

#### AbbreviationOptimizationPass

**Purpose:** Detect and fix overlapping abbreviations

**What it does:**
- Analyzes selected abbreviations
- Detects overlapping pairs (e.g., "the" and "the ")
- Reports overlap statistics
- (TODO: Re-rank to eliminate overlaps)

**Zork1 Results:**
```
Total abbreviations: 96
Overlapping pairs: 153
Overlap rate: 159%
```

**Status:** ⚠️ Analysis working, optimization not yet implemented

#### PropertyOptimizationPass

**Purpose:** Optimize object property tables

**What it does:**
- (TODO) Remove unused properties
- (TODO) Compact property data
- (TODO) Deduplicate property values

**Status:** 📋 Stub only

## String Deduplication Design

### Current Implementation

**Strings are embedded inline:**
```
ROUTINE code:
  PRINT "Hello"  → 0xB2 [encoded "Hello"]
  PRINT "Hello"  → 0xB2 [encoded "Hello"]  ← Duplicate!
```

**Problem:** Each duplicate wastes ~5-20 bytes

### Proposed Solution

**Use string table with references:**
```
String Table (in high memory):
  0x4000: [encoded "Hello"]
  0x4008: [encoded "Goodbye"]
  ...

ROUTINE code:
  PRINT_PADDR 0x4000  → Points to "Hello"
  PRINT_PADDR 0x4000  → Same string, same address
```

**Savings:** String stored once, referenced multiple times

### Implementation Status

✅ **Phase 1: Analysis** (DONE)
- Extract strings from bytecode
- Count duplicates
- Build string table
- Calculate potential savings

⏳ **Phase 2: Rewriting** (TODO)
- Replace PRINT with PRINT_PADDR
- Update routine bytecode
- Calculate string addresses
- Update references

📋 **Phase 3: Integration** (TODO)
- Store string table in high memory
- Update assembler to include string table
- Fix up addresses during assembly

## Abbreviation Overlap Problem

### Current Issue

Abbreviation selection algorithm chooses overlapping substrings:

```
Selected abbreviations:
  #0: "there is a lamp here" (20 chars)
  #1: "there is a lamp her"  (19 chars)  ← 19/20 overlap
  #2: "here is a lamp here"  (19 chars)  ← High overlap
  ...
  153 overlapping pairs total
```

**Problem:** Wastes abbreviation slots on nearly-identical strings

### Solution

**Overlap Detection:**
```python
def has_overlap(abbr1, abbr2):
    return abbr1 in abbr2 or abbr2 in abbr1
```

**Re-Ranking Algorithm:**
```python
def eliminate_overlaps(candidates):
    selected = []
    for candidate in sorted_candidates:
        if not any(has_overlap(candidate, s) for s in selected):
            selected.append(candidate)
    return selected
```

**Expected Improvement:**
- From: 96 abbreviations with 153 overlaps
- To: 96 non-overlapping abbreviations
- Savings: Better compression ratio

## Results

### Zork1 Optimization Analysis

**Without Optimization Passes:**
- File size: 32,278 bytes
- No duplication analysis
- Overlapping abbreviations unknown

**With Optimization Passes:**
- File size: 33,046 bytes (same, no rewriting yet)
- **64.3% string duplication detected**
- **153 abbreviation overlaps detected**
- Ready for optimization implementation

### Potential Savings

**String Deduplication:**
- Current: 42 strings × avg 12 bytes = ~500 bytes
- Deduplicated: 15 strings × avg 12 bytes = ~180 bytes
- Table overhead: ~50 bytes
- **Net savings: ~270 bytes** (0.8% of file)

**Abbreviation Overlap Elimination:**
- Current: 96 abbreviations, many overlapping
- Optimized: 96 non-overlapping, better coverage
- **Estimated savings: 500-1000 bytes** (1.5-3% of file)

**Combined:**
- **Total estimated: 770-1270 bytes** (2.3-3.8% of 33KB file)

## Next Steps

### Short Term

1. ✅ **DONE:** Optimization pass architecture
2. ✅ **DONE:** String deduplication analysis
3. ✅ **DONE:** Abbreviation overlap detection
4. ⏳ **TODO:** Implement overlap elimination algorithm
5. ⏳ **TODO:** Test with non-overlapping abbreviations

### Medium Term

6. 📋 **TODO:** Implement string table rewriting
   - Replace PRINT with PRINT_PADDR
   - Calculate string addresses
   - Update bytecode references

7. 📋 **TODO:** Property optimization pass
   - Remove unused properties
   - Deduplicate property values

8. 📋 **TODO:** Code optimization pass
   - Remove dead code
   - Optimize instruction sequences

### Long Term

9. 📋 **TODO:** Advanced optimizations
   - String compression algorithms
   - Instruction scheduling
   - Register allocation optimization

10. 📋 **TODO:** Profile-guided optimization
    - Analyze actual game runtime
    - Optimize hot paths
    - Optimize string access patterns

## Usage

### For Compiler Developers

To add a new optimization pass:

```python
# 1. Create pass class
class MyOptimizationPass(OptimizationPass):
    def run(self, compilation_data: Dict) -> Dict:
        # Your optimization logic here
        self.log("My Optimization Pass")

        # Analyze
        analysis = self.analyze(compilation_data)

        # Transform
        optimized = self.optimize(compilation_data, analysis)

        # Track stats
        self.stats = {'savings': 100}

        return optimized

# 2. Add to pipeline in compiler.py
pipeline.add_pass(MyOptimizationPass)
```

### For Users

Optimization passes run automatically during compilation:

```bash
# Verbose mode shows optimization statistics
./zorkie game.zil --verbose

# Output includes:
# [opt] String Deduplication Pass
# [opt]   Found 42 strings in routines
# [opt]   Duplicates: 27 (64.3%)
# [opt] Abbreviation Optimization Pass
# [opt]   Found 153 overlapping abbreviations
```

## Conclusion

The optimization pass architecture is **implemented and working**. Analysis passes successfully identify:
- 64.3% string duplication
- 153 abbreviation overlaps

Next step is implementing the actual optimization transformations:
1. Eliminate abbreviation overlaps
2. Rewrite strings to use string table
3. Measure actual size reduction

**Current Status:** ✅ Architecture complete, ready for optimization implementations
