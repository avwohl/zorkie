# Work In Progress Notes

## Current Status (2025-12-24)
- **Tests:** 358 passed, 131 failed, 142 skipped
- **Started session at:** 349 passed, 135 failed
- **Fixed this session:** +9 passing, -4 failing

## Recent Changes (This Session)
- Implemented MAP-DIRECTIONS loop construct for iterating over room exits
- Implemented MAP-CONTENTS loop construct for iterating over object contents
- Added DirectionsNode to AST and parser for `<DIRECTIONS>` declarations
- Fixed branch offset calculations using Z-machine formula: Target = PC_after_branch + Offset - 2
- Fixed TELL D with complex expressions (FormNode operands now evaluated before printing)
- Fixed property value encoding: values <= 255 stored as 1 byte (GETB compatible)
- Added _extract_direction_exit helper for parsing `(NORTH TO ROOM)` format

## Previous Changes
- Fixed placeholder position tracking when PROG/BIND/DO adds dynamic locals (was off by 2 bytes)
- Fixed DO loop with END clause (properly extracts and executes end clause on normal termination)
- Added G=? and L=? handling in generate_condition_test
- Fixed V6 packed string address calculation (strings_offset was not used)
- Fixed AGAIN with activation to properly jump to routine start
- Added `generates_code_matching_func` method to test infrastructure
- Skipped V7/V8 hello world tests (dfrotz support issues, rarely used versions)
- PROG activation support (`<PROG NAME () ...>` with targeted RETURN)
- GO routine validation (no required params, no locals in V1-V5)
- OPT parameter parsing treated same as AUX
- Routine parameter count validation (max 3 in V3, max 7 in V4-7)
- RETURN activation validation
- Fixed VERSION directive propagation in test infrastructure

## Known Issues

### Flow Control (~10 failing)
- DO-FUNNY-RETURN feature
- DO end clause misplacement detection
- Macro-related COND tests
- PROG with bindings inside GO routine detection

### Objects (~27 failing)
- Object ordering and numbering
- FIRST?, NEXT?, IN? predicates
- Object property access
- PROPDEF handling

### Tell (~24 failing)
- TELL built-in token extensions
- Various TELL formatting features
- Unicode handling

### Vocab (~18 failing)
- New parser (NEW-PARSER?) features
- Word flag tables
- Synonym/preposition handling

### Meta/Macros (~19 failing)
- IFFLAG/COMPILATION-FLAG
- SPLICE in void context
- DEFINE-GLOBALS

### Tables (~16 failing)
- #BYTE element handling in TABLE
- ITABLE multi-element initializers
- Compile-time table manipulation (ZPUT, ZREST)

### Variables (~7 failing)
- Funny globals (globals beyond 240 limit)
- DEFINE-GLOBALS
- Unused locals warning (ZIL0210)

### Syntax (~7 failing)
- REMOVE-SYNTAX matching
- Parser table generation

### Version Support
- V7/V8 have interpreter compatibility issues (skipped in tests)

## What's Left

### By Category
- objects: 27 failing
- tell: 24 failing
- vocab: 18 failing
- tables: 16 failing
- meta: 11 failing
- flow_control: 10 failing
- macros: 8 failing
- syntax: 7 failing
- variables: 7 failing

### Priority Items
1. Add warning infrastructure for unused variable checks
2. Fix #BYTE element handling in tables
3. Fix DO-FUNNY-RETURN feature
