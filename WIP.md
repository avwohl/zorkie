# Work In Progress Notes

## Current Status (2025-12-24)
- **Tests:** 348 passed, 143 failed, 140 skipped
- **Started session at:** 150 failed
- **Fixed this session:** 7 tests

## Recent Changes
- PROG activation support (`<PROG NAME () ...>` with targeted RETURN)
- GO routine validation (no required params, no locals in V1-V5)
- OPT parameter parsing treated same as AUX
- Routine parameter count validation (max 3 in V3, max 7 in V4-7)
- RETURN activation validation
- Fixed VERSION directive propagation in test infrastructure

## Known Issues

### Flow Control (~20 failing)
- DO with form bounds/end clauses
- MAP-CONTENTS and MAP-DIRECTIONS constructs
- AGAIN with activation
- DO-FUNNY-RETURN feature
- Macro-related COND tests
- PROG with bindings inside GO routine detection

### Objects (~27 failing)
- Object ordering and numbering
- FIRST?, NEXT?, IN? predicates
- Object property access

### Tell (~24 failing)
- TELL built-in token extensions
- Various TELL formatting features

### Vocab (~18 failing)
- New parser (NEW-PARSER?) features
- Word flag tables
- Synonym/preposition handling

### Meta/Macros (~19 failing)
- IFFLAG/COMPILATION-FLAG
- SPLICE in void context

### Tables (~16 failing)
- #BYTE element handling
- Table initialization

### Version Support
- V6 has string address calculation issues
- V7/V8 have initial PC setup issues

## Next Steps
1. Fix DO with form bounds (generates illegal opcodes)
2. Implement MAP-CONTENTS/MAP-DIRECTIONS
3. Add warning infrastructure for optional parameter checks
4. Fix V6 packed address calculations
