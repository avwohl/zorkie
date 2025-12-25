# Work In Progress Notes

## How to Resume

The short-circuit AND/OR implementation is mostly complete but has an issue with void expressions. The failing test is:
```
tests/zilf/test_flow_control.py::TestCond::test_and_in_void_context_with_macro_at_end_should_work
```

The problem: When `<AND <FOO> <BAR>>` where BAR expands to `<PRINTN 42>` (a void operation), the AND correctly evaluates both expressions but the last operand doesn't push a value to the stack. The test expects "42" to be printed (which should happen) but currently outputs nothing.

To debug:
1. Check if `generate_form` for `<PRINTN 42>` is being called during AND evaluation
2. The issue may be in the JZ branch logic or offset calculations in `gen_and`
3. Look at codegen_improved.py lines 11486-11619 for the AND implementation

Other good next steps:
- SPLICE macro support (`<CHTYPE ... SPLICE>`) - needed for 6 macro tests
- Property value encoding (GETB reads wrong byte for 2-byte words) - affects MAP-DIRECTIONS tests
- Object ordering tests - many use FIRST?/NEXT? predicates that may have issues

## Current Status (2025-12-25)
- **Tests:** 381 passed, 102 failed, 143 skipped
- **Started session at:** 380 passed, 103 failed
- **Fixed this session:** +1 passing, -1 failing
- **Remaining by category:**
  - objects: 21 failing
  - tell: 20 failing
  - vocab: 18 failing
  - meta: 10 failing
  - tables: 10 failing
  - syntax: 7 failing
  - macros: 6 failing
  - variables: 6 failing
  - flow_control: 4 failing

## Recent Changes (This Session)
- Added DO misplaced END clause detection
  - DO END clause must appear immediately after loop spec
  - `<DO (CNT 0 25) body (END ...)>` now correctly fails
  - Validates that END clauses don't appear after body statements
- Implemented short-circuit logical AND/OR
  - gen_and now evaluates left-to-right, returning false early if any operand is false
  - gen_or now evaluates left-to-right, returning first truthy value
  - BAND/BOR remain as bitwise operations using Z-machine AND/OR opcodes
  - Note: Some edge cases with void expressions still need work

## Previous Session Changes (2025-12-25)
- Added COND support for macro-expanded clauses
  - COND now handles macros that expand to clause lists
  - Added _extract_cond_clause helper to process macro results
  - QUOTE FormNodes with clause lists are properly extracted
- Added IF-IN-ZILCH and IFN-IN-ZILCH built-in macros
  - IF-IN-ZILCH returns its argument (we're a ZILF-compatible compiler)
  - IFN-IN-ZILCH returns empty (opposite behavior)
- Fixed COMPILATION-FLAG to accept bare atom values
  - Now supports both `<COMPILATION-FLAG FOO T>` and `<COMPILATION-FLAG FOO <T>>`
- Fixed string translation for pipe and newlines
  - `|` becomes newline in output
  - Newlines immediately after `|` are absorbed
  - Other literal newlines become spaces
  - Matches ZILF behavior for multi-line strings
- Added macro argument count validation
  - Macros now check if they receive enough required arguments
  - Raises error if called with too few arguments
- Added macro expansion for local variable initializers
  - Macros in routine `AUX` variable defaults now expand correctly
  - `(X <MY-MACRO>)` in routine params now works
- Added `with_global` method to GlobalsAssertion test helper
- Added `in_glulx` method to RoutineAssertion (skips Glulx tests)

## Previous Session Changes (2025-12-25)
- Added DESC property newline stripping
  - Newlines in DESC property values are replaced with spaces
- Added duplicate property detection
  - Properties cannot be defined twice on same object (except FLAGS)
  - IN and LOC are treated as duplicates when setting location
  - Exception: (IN "string") for NEXIT doesn't conflict with (IN OBJECT)
- Added local variable validation for tables
  - Tables cannot reference local variables (.X)
  - Added _contains_local_var helper for recursive checks
  - Applies to both _add_table and gen_table methods
- Added MDL0430 warning for TABLE with LENGTH prefix overflow
  - Warns when STRING table length > 255 bytes
- Added COND validation (ZIL0100)
  - COND requires parenthesized clauses, not bare forms
  - `<COND <SET X 1>>` now fails with proper error
- Added character literal support in TELL
  - `<TELL !\A !\B !\C>` now prints "ABC"
  - Properly encoded PRINT_CHAR with correct type byte
- Added error for bare atoms in TELL
  - Unknown tokens now fail with helpful message
  - Suggests using ,ATOM or quoted string
- Added ZIL0404 error for too many attributes
  - V3 max 32, V4+ max 48 attributes
  - Check in _build_symbol_tables
- Added ZIL0404 error for too many properties
  - Checks at propdef and object property assignment
  - Properties can't overlap with direction properties
- Added ZIL0212 warning for unused properties
  - Tracks defined properties (P?* constants)
  - Tracks property usage in GETP, PUTP, GETPT
  - Warns for properties never accessed in code
- Added MDL0428 warning for LEXV table size not multiple of 3
- Added MDL0430 warning for ITABLE size overflow
  - Warns when BYTE table size > 255
  - Warns when WORD table size > 65535
  - Parser now recognizes bare BYTE/WORD/PURE/LENGTH flags in ITABLE
- Extended eval_constant to handle TableNode values (CONSTANT with ITABLE/TABLE)
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
