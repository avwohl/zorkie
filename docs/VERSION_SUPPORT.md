# Z-Machine Version Support Status

## Current Implementation Status

### Versions Listed in CLI
The compiler CLI (`zilc/compiler.py:425`) advertises support for versions: **3, 4, 5, 8**

### Actual Implementation Status

| Version | Status | Opcodes | Testing | Notes |
|---------|--------|---------|---------|-------|
| **V3** | ✅ Implemented | 100% | Tested with Planetfall | Fully working |
| **V4** | 🟡 Partial | ~95% | Not tested | Listed in CLI but untested |
| **V5** | ✅ Implemented | 100% | Partial testing | All opcodes implemented |
| **V6** | ❌ Not implemented | 0% | None | Not in CLI, not implemented |
| **V7** | ❌ Not implemented | 0% | None | Not in CLI, not implemented |
| **V8** | ❌ Not implemented | 0% | None | In CLI but NOT implemented |

## What's Missing for Each Version

### V4 (Listed but Untested)
- [ ] Timed input opcodes (V4+)
- [ ] Testing with actual V4 story files
- [ ] Validation of 256KB file size handling
- [ ] Header flag handling for V4 features

### V6 (Not Advertised, Not Implemented)
- [ ] Graphics opcodes (draw_picture, etc.)
- [ ] Mouse input handling
- [ ] Window management extensions
- [ ] Packed addressing with offsets (4P + 8×offset)
- [ ] Header fields $28/$2A (routines/strings offset)

### V7 (Not Advertised, Not Implemented)
**Recommendation**: Skip V7 implementation entirely
- Almost no games use V7
- Poor interpreter support
- V8 is superior in every way
- Not worth the implementation effort

### V8 (Advertised but NOT Implemented)
**Priority**: Should implement since it's listed in CLI

Missing features:
- [ ] Packed address calculation: `8P` instead of `4P`
- [ ] File length divisor: 8 instead of 4
- [ ] File size validation: 512KB max
- [ ] Testing with actual V8 story files

**Implementation effort**: LOW - V8 is functionally identical to V5
- Same opcodes as V5
- Same memory architecture as V5
- Only differences: packed addressing and file size

## Recommendations

### Immediate Actions
1. **Remove V8 from CLI** or **implement V8 support** (misleading users currently)
2. **Test V4** with actual V4 story files to verify it works
3. **Document V5 limitations** if any exist

### Future Implementation Priority
1. **V8 support** (easy, widely used)
2. **V4 testing** (verify existing code works)
3. **V6 support** (harder, less common)
4. **V7 support** (skip entirely)

### CLI Truth
Current CLI: `choices=[3, 4, 5, 8]`

Should be one of:
- Conservative: `choices=[3, 5]` (only fully tested versions)
- Honest: `choices=[3, 4, 5]` (remove V8 until implemented)
- Aspirational: Keep `[3, 4, 5, 8]` but implement V8

## Implementation Notes for V8

V8 is the easiest version to add after V5:

### Required Changes

**1. Packed Address Calculation** (zilc/zmachine/assembler.py)
```python
def unpack_address(packed_addr: int, version: int, is_string: bool = False) -> int:
    if version <= 3:
        return packed_addr * 2
    elif version <= 5:
        return packed_addr * 4
    elif version == 6 or version == 7:
        # Would need offset from header (not implemented)
        raise NotImplementedError("V6/V7 not supported")
    elif version == 8:
        return packed_addr * 8  # ADD THIS
    else:
        raise ValueError(f"Unknown version: {version}")
```

**2. File Length Divisor** (zilc/zmachine/assembler.py)
```python
def get_file_length_divisor(version: int) -> int:
    if version <= 3:
        return 2
    elif version <= 7:
        return 4
    elif version == 8:
        return 8  # ADD THIS
    else:
        raise ValueError(f"Unknown version: {version}")
```

**3. Header Validation**
- Ensure header $1A is calculated correctly for V8
- Validate file size doesn't exceed 512KB

**4. Testing**
- Create or find a V8 test story file
- Verify compilation succeeds
- Test with V8-compatible interpreter

## Testing Status

### V3 Testing
- ✅ Planetfall source compilation
- ✅ Dictionary building (630/631 words = 99.8%)
- ✅ Object table generation
- ✅ Text encoding
- ✅ Opcode generation

### V5 Testing
- 🟡 Partial opcode testing
- ❌ No full game compilation
- ❌ No interpreter testing

### V4, V8 Testing
- ❌ None

## Conclusion

**Current state**: Misleading users about V8 support

**Quick fix**: Update CLI to `choices=[3, 5]` or `choices=[3, 4, 5]`

**Better fix**: Implement V8 (low effort, high value)

---
**Last Updated**: 2025-11-16
