# Work In Progress Notes

## Current Status (2025-12-25)
- **Tests:** 363 passed, 121 failed, 142 skipped
- **Started session at:** 360 passed, 124 failed
- **Fixed this session:** +3 passing, -3 failing

## Recent Changes (This Session)
- Added MDL0417 warning for too many optional arguments
  - Tracks optional params separately in RoutineNode.opt_params
  - Warns when total params + opt_params exceeds CALL limit (3 in V3, 7 in V4+)
- Added call-site argument count validation
  - gen_routine_call now checks if call has too many arguments for target routine
  - Stores routine param info in _routine_param_info dict during code generation
  - Raises ValueError if call exceeds (num_required + num_optional) args
- Fixed CONSTANT FALSE call handling
  - eval_expression now handles FormNode for `<>` returning 0
  - Calling a constant with value 0 evaluates args for side effects then returns 0
  - Uses Z-machine CALL 0 behavior which returns FALSE per spec

## Previous Session Changes
- Fixed #BYTE and #WORD element handling in TABLE
  - Added `_encode_table_values()` helper with proper prefix parsing
  - Added `_get_table_value_int()` to handle lists (parenthesized values like `(12345)`)
  - Tables now correctly encode byte/word prefixed values: `<TABLE 1 #BYTE 2 #WORD 3>`
- Fixed property value encoding for GETPT/PUTP/PTSIZE
  - Single integer property values now stored as 2-byte words (was incorrectly using 1 byte)
  - This allows `<GET <GETPT obj prop> 0>` to read the full property value
  - PTSIZE now correctly returns 2 for word properties
- Added ZIL0211 warning for unused flags
  - Tracks which flags are defined in object FLAGS properties
  - Tracks which flags are used in FSET/FCLEAR/FSET? operations
  - Tracks flags used in SYNTAX FIND clauses (via regex scan)
  - Warns at end of compilation for flags never used in code
- Fixed ITABLE multi-element initializers
  - `<ITABLE 2 1 2 3>` now correctly creates [1,2,3,1,2,3] (pattern repeated 2x)
  - Updated _compile_global_table_node, _compile_global_table, _add_table, gen_table

- Added warning infrastructure for unused variable checks (ZIL0210)
  - Compiler now tracks local variable usage
  - Warns for unused routine-level locals, PROG/BIND/REPEAT bindings
  - Side-effect initializers (FormNode) exempt from warning
- Implemented MAP-DIRECTIONS loop construct for iterating over room exits
- Implemented MAP-CONTENTS loop construct for iterating over object contents
- Added DirectionsNode to AST and parser for `<DIRECTIONS>` declarations
- Fixed branch offset calculations using Z-machine formula: Target = PC_after_branch + Offset - 2
- Fixed TELL D with complex expressions (FormNode operands now evaluated before printing)
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

### Tables (~14 failing)
- ~~#BYTE element handling in TABLE~~ FIXED
- ITABLE multi-element initializers
- Compile-time table manipulation (ZPUT, ZREST)

### Variables (~6 failing)
- Funny globals (globals beyond 240 limit)
- DEFINE-GLOBALS
- Unused locals warning (ZIL0210) - PARTIALLY FIXED (basic case works)

### Syntax (~7 failing)
- REMOVE-SYNTAX matching
- Parser table generation

### Version Support
- V7/V8 have interpreter compatibility issues (skipped in tests)

## What's Left

### By Category (approximate)
- objects: ~26 failing
- tell: ~24 failing
- vocab: ~18 failing
- tables: ~13 failing
- meta: ~11 failing
- flow_control: ~8 failing
- macros: ~8 failing
- syntax: ~7 failing
- variables: ~6 failing

### Priority Items
1. ~~Add warning infrastructure for unused variable checks~~ DONE (ZIL0210 works)
2. ~~Fix #BYTE element handling in tables~~ DONE
3. Fix DO-FUNNY-RETURN feature
4. ~~Add ZIL0211 warning for unused flags~~ DONE
5. ~~Fix property value encoding (GETPT/PUTP/PTSIZE)~~ DONE
6. ~~Add MDL0417 warning for too many optional args~~ DONE
7. ~~Add call-site argument count validation~~ DONE
8. ~~Fix CONSTANT FALSE call handling~~ DONE
