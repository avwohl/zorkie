# Improved String Collection Results

## Summary

Enhanced string collection to capture all strings from AST, increasing collection from 1,093 to 15,566 strings (14x improvement). However, file size increased slightly due to abbreviations table overhead exceeding compression savings.

## Implementation Changes

### Enhanced `collect_strings_from_node()` Function

**Before:** Only collected StringNode objects from FormNode operands
**After:** Recursively traverses all AST node types:

```python
def collect_strings_from_node(node):
    if node is None:
        return
    elif isinstance(node, StringNode):
        all_strings.append(node.value)
    elif isinstance(node, FormNode):
        # Recurse into all operands
        for operand in node.operands:
            collect_strings_from_node(operand)
    elif isinstance(node, CondNode):
        # Handle COND clauses: (condition, actions) tuples
        for clause in node.clauses:
            if isinstance(clause, (list, tuple)):
                for item in clause:
                    collect_strings_from_node(item)
    elif isinstance(node, RepeatNode):
        # Handle REPEAT body
        for statement in node.body:
            collect_strings_from_node(statement)
    elif isinstance(node, (list, tuple)):
        # Recurse into lists/tuples
        for item in node:
            collect_strings_from_node(item)
```

### String Sources Now Captured

1. ✅ **Object/Room properties** - DESC, LDESC, etc.
2. ✅ **TELL/PRINT statements** - All inline strings
3. ✅ **COND branches** - Strings in conditional actions
4. ✅ **REPEAT loops** - Strings in loop bodies
5. ✅ **Nested forms** - Strings in deeply nested expressions

## Results

### String Collection Comparison

| Version | Strings Collected | Source |
|---------|------------------|---------|
| Original | 1,093 | FormNode operands only |
| Improved | 15,566 | Full AST traversal |
| Increase | **14.2x** | All node types |

### Compilation Results

| Metric | No Abbrev | With Abbrev (Improved) | Change |
|--------|-----------|----------------------|---------|
| **File Size** | 32,278 bytes | 33,046 bytes | +768 bytes (+2.4%) |
| **Routine Code** | 17,584 bytes | 17,492 bytes | -92 bytes (-0.5%) |
| **Abbreviations** | None | 96 at 0x0220 | +1KB overhead |
| **Strings Collected** | N/A | 15,566 | Full coverage |

### Analysis

**Why Size Increased:**
- Abbreviations table: ~1KB overhead (192 bytes + encoded strings)
- Routine savings: only 92 bytes (0.5%)
- **Net result: +768 bytes**

**Why Savings Are Low:**

1. **Suboptimal Abbreviation Selection**
   - Algorithm selects overlapping substrings
   - Example: "there is a lamp here" (20 chars) AND "there is a lamp her" (19 chars)
   - These overlap significantly and fragment savings

2. **Frequency vs Length Trade-off**
   - Current algorithm prioritizes: `savings = (length * 0.6 - 1.33) * count`
   - Favors long strings with moderate frequency
   - Better: Prioritize high-frequency short strings

3. **Z-character Encoding Efficiency**
   - Abbreviations cost 2 Z-characters (1.33 bytes)
   - Short strings (2-3 chars) cost 2-3 Z-characters (~1.3-2 bytes)
   - Savings for short strings: minimal
   - Need 4+ character strings with high frequency

4. **First-Match Greedy Algorithm**
   - `find_abbreviation()` uses first match
   - Doesn't optimize for best match
   - May miss better abbreviation opportunities

## Official Zork1 Comparison

Official Zork1: 86,838 bytes with abbreviations
Our Zork1: 33,046 bytes with abbreviations

**Why Official is Larger:**
- Much more game content and text
- Optimized abbreviations (hand-selected)
- Static memory properly separated
- Additional game logic and features

**Why Our Abbreviations Underperform:**
- Automatic selection not optimal
- No frequency testing during development
- Simple greedy matching algorithm
- No overlap detection

## Recommendations

### Short Term: Disable Abbreviations

Since abbreviations currently increase file size, consider:
- Making abbreviations optional (--abbreviations flag)
- Default: OFF for now
- Enable when algorithm improves

### Medium Term: Algorithm Improvements

1. **Eliminate Overlapping Abbreviations**
   ```python
   # Check if candidate overlaps with already-selected abbreviations
   def has_overlap(new_abbrev, existing_abbrevs):
       for existing in existing_abbrevs:
           if new_abbrev in existing or existing in new_abbrev:
               return True
       return False
   ```

2. **Prioritize High-Frequency Short Strings**
   ```python
   # Weight frequency more heavily
   savings = (length * 0.6 - 1.33) * (count ** 1.5)
   ```

3. **Minimum String Length**
   ```python
   # Only abbreviate strings 4+ characters
   if len(substr) < 4:
       continue
   ```

4. **Best-Match Selection**
   ```python
   # In find_abbreviation(), try all matches and pick best
   best_savings = 0
   for abbrev_index, abbrev in enumerate(self.abbreviations):
       if matches:
           savings = calculate_savings(abbrev, 1)
           if savings > best_savings:
               best_match = abbrev_index
   ```

### Long Term: ML-Based Optimization

- Train on official Infocom story files
- Learn optimal abbreviation patterns
- Use compression ratios as fitness function
- Genetic algorithm for abbreviation selection

## Conclusion

String collection is now **complete** - capturing 15,566 strings from full AST traversal. However, abbreviations currently increase file size by 768 bytes due to suboptimal selection algorithm.

**Current Status:**
- ✅ String collection: Working (15,566 strings)
- ⚠️ Abbreviation selection: Needs optimization
- ⚠️ Net file size: Increases (not decreases)

**Recommendation:** Commit improved string collection, but consider making abbreviations optional until selection algorithm is improved.

## Test Results

```bash
# Without abbreviations (baseline)
./zorkie test-games/zork1/zork1.zil -o zork1-full.z3
# Result: 32,278 bytes

# With abbreviations (improved collection)
./zorkie test-games/zork1/zork1.zil -o zork1-improved-abbrev.z3
# Result: 33,046 bytes (+768 bytes)

# Routine code comparison
# Before: 17,584 bytes
# After:  17,492 bytes (-92 bytes, 0.5% savings)
```

## Next Steps

1. ✅ Commit improved string collection
2. ⏸️ Pause abbreviations (optional feature)
3. 📋 TODO: Fix abbreviation selection algorithm
4. 📋 TODO: Add overlap detection
5. 📋 TODO: Benchmark against official files
