# Work In Progress Notes

## How to Resume

All ZILF integration tests are now either passing, skipped, or marked xfail for
unimplemented ZILF-specific features.

Focus areas for next session:
1. **Object ordering (complex)** - Investigate ZILF algorithm for mixed object/room ordering
2. **NEW-PARSER?** - Extended vocabulary format (8 tests)
3. **PROPSPEC clearing** - Override default PROPDEF patterns

## Current Status (2025-12-31)
- **Tests:** 656 passed, 0 failed, 17 xfailed
- **Interpreter tests:** 143 passed (100%)
- **Hello world works** in V1, V2, V3, V4, V5, V6, V8 (V7 xfail due to interpreter bugs)
- **Full V1-V8 support** with bocfel interpreter for V5+ (stricter Z-machine compliance)
- All tests passing (excluding xfails for unimplemented ZILF features)

## Recent Changes (2025-12-31)
- **NEW-PARSER? VWORD table generation** - W?* vocabulary word resolution:
  - Fixed gen_get to handle 16-bit W?* vocab placeholders (was truncating to 8 bits)
  - Generate VWORD tables (7 words, 14 bytes) for verbs, NEW-ADD-WORD words, synonyms
  - VWORD fields: lexical-word, classification, flags, semantic-stuff, verb-stuff, adj-id, dir-id
  - Generate VERB-DATA tables (4 words) for verbs with syntax definitions
  - Synonyms get VWORD tables with field 3 pointing to main word's VWORD
  - Added _resolve_vword_placeholders for routine bytecode
  - Added _resolve_table_vword_placeholders for table data
  - 4 NEW-PARSER? tests now pass (was 2 xfailed)
- **NEW-ADD-WORD and WORD-FLAG-TABLE** - NEW-PARSER? vocabulary support:
  - Added NewAddWordNode AST node for `<NEW-ADD-WORD name type value flags>`
  - Generates WORD-FLAG-TABLE containing word addresses and flags
  - Pre-registers WORD-FLAG-TABLE global before code generation
  - 1 test now passes (test_word_flag_table_should_list_words_and_flags)
- **Error limits implementation** - Compilation stops after 100 errors:
  - Per-call-site error tracking for undefined routines
  - 101st error is "too many errors" message
  - `compiler.get_errors()` returns all collected errors
- **PROPDEF DIRECTIONS fixes** (4 tests now pass):
  - Skip P?DIRECTIONS creation when PROPDEF DIRECTIONS is defined
  - Implicit direction detection for PROPDEF patterns (EAST/WEST via GOES TO syntax)
  - ROOM type optimization for ROOMS-FIRST mode (1 byte vs 2 bytes)
  - VOC form handling in PROPDEF patterns (extract part-of-speech, register with codegen)
  - Single-value PROPDEF matching (wrap non-list values for pattern matching)
- **TABLE PATTERN** - Affects element sizes in table generation (1 test passes)
- **PARSER-TABLE ordering** - Parser tables come before other pure tables (1 test passes)

## Remaining xfailed tests (17)
All remaining xfails require substantial work or depend on external factors:
- **Interpreter issues (6)**: V7 bugs (2), dfrotz trailing spaces (2), Unicode/Glk (2)
- **Meta-programming (5)**: PROPSPEC (2), IN-ZILCH, ROUTINE-REWRITER, PRE-COMPILE
- **Custom encodings (4)**: CHRSET (2), LANGUAGE (2)
- **Reader macros (1)**: MAKE-PREFIX-MACRO
- **LANGUAGE lexing (1)**: German character handling

## Recent Changes (2025-12-30)
- **LOWCORE-TABLE builtin** - Iterate over header bytes calling a handler:
  - `<LOWCORE-TABLE field length handler>` generates unrolled loop
  - Handler can be opcode (like PRINTN) or routine
  - Fixed test_macros_returning_constants_can_be_used_in_lowcore_table
- **F?/FALSE? predicate** - Added opposite of T?/TRUE?:
  - `<F? value>` returns true if value is zero (false), false otherwise
  - Fixes test_constant_comparisons_folded test
- **Undefined routine errors** - Changed from warning to error (ZIL0415):
  - `<THIS-IS-UNDEFINED>` now fails compilation instead of silently using null address
- **PRINTD with nested expressions** - `<PRINTD <FIRST? obj>>` now works correctly:
  - gen_printobj now evaluates FormNode operands before printing
  - Fixes garbage output when using FIRST?/NEXT?/LOC as PRINTD argument
- **GVAL/LVAL quirk handling** - Using ,X with local or .X with global now works:
  - Falls back to correct scope with warning (ZIL0205/ZIL0204)
  - 2 more tests pass (648 -> 650)
- **Added 6 PROPDEF/PROPSPEC tests** from ZILF (all xfailed):
  - PROPDEF for implicit directions, DIRECTIONS property suppression
  - VOC in PROPDEF, PROPSPEC with vocab/routines, ROOM type optimization
- **Property routine placeholder fixups** - Object properties referencing routines now work:
  - Compiler detects routine names in `resolve_atom_value()`
  - Creates 0xFA00 | idx placeholders in property data
  - Assembler resolves to packed routine addresses after high_mem_base known
  - Fixed 5 tests (643 -> 648 passing)
- Added ZILF-derived tests for codegen, pruning, and quirks:
  - TestSimpleOR_2 (OR with FIRST? temp vars)
  - test_properties_containing_backslash
  - test_branch_to_same_condition
  - 5 routine pruning tests (all passing)
  - 2 GVAL/LVAL quirk tests (xfailed - need compiler work)
  - test_map_contents_with_next_and_end_empty
- Test count improved from 630 to 648 passing tests
- Test coverage vs ZILF now at 93-100% for most test files

## Zork1 Compilation Status
- **Zork1 compiles** to a 103KB story file
- **Runtime status**: Still hangs (may need parser/SYNTAX features)
- **Property routine fixups** (FIXED): ACTION properties now properly resolve routine addresses
- **Remaining warnings**: ON-LAKE, IN-LAKE only (missing room definitions in source)
- **Previous issues (FIXED)**: Illegal opcode, backward branch offsets, ACT? constants, PREPOSITIONS, property routines

## Recent Changes (2025-12-27)
- **Verb/action limit checking (MDL0426)** - Old parser now validates syntax definitions
  - Raises error if more than 255 unique verbs in SYNTAX definitions
  - Raises error if more than 255 unique actions in SYNTAX definitions
  - NEW-PARSER? flag bypasses these limits (no limit in new parser mode)
  - 2 tests now pass (was xfailed)
- **PREPOSITIONS table generation** - Added automatic table from SYNTAX definitions
  - Extracts prepositions from SYNTAX patterns (words between OBJECT slots)
  - Generates PR?PREP constants for each unique preposition
  - Creates PREPOSITIONS table for parser PREP-FIND routine
- **ACT? constant generation** - Added automatic ACT?ACTION constants from SYNTAX definitions
  - E.g., V-WALK action creates ACT?WALK constant
  - Eliminates unknown constant warnings for ACT?WALK, ACT?FIND, etc.
- **Full V1-V8 Z-machine support**
  - Fixed memory layout: dictionary now in static memory (bocfel requirement)
  - Added 4-byte padding before routines for V6-7 (bocfel rejects packed addr 0)
  - Added version-aware string alignment (V8 requires 8-byte alignment)
  - Test infrastructure uses bocfel for V5+ (except V7), dfrotz for V1-V6
  - Fixed COLOR opcode encoding (EXT:27 = 0xBE 0x1B, not VAR:27)
  - V8 now fully working; V7 xfail due to interpreter bugs in bocfel/dfrotz
- Completed PROPDEF implementation (6/7 tests pass, 1 xfail for PROPSPEC clearing)
  - Added MANY modifier for repeating pattern elements
  - Export PROPDEF constants (HEIGHTSIZE, H-FEET, etc.) to codegen
  - Apply PROPDEF DIRECTIONS pattern to all direction properties
  - Fixed constant form encoding to output embedded FORM data
  - Added VOC placeholder (0xFB00) resolution in assembler
  - All pattern types working: WORD, BYTE, ROOM, OBJECT, VOC
- Implemented BIT-SYNONYM flag alias support (2 tests pass)
  - Parser collects BitSynonymNode instances
  - Compiler resolves synonyms to original attribute numbers
  - `<BIT-SYNONYM NEWNAME ORIGINALBIT>` creates alias

## Previous Changes (2025-12-26)
- Implemented ZILF-compatible object numbering (reverse definition order)
  - Objects now numbered in reverse source order (last defined = lowest number)
  - Combines objects and rooms, sorts by source line, then reverses
  - `_build_symbol_tables` and `_build_object_table` both use interleaved order
  - Fixed codegen to use pre-assigned object numbers from symbol_tables
  - Simple object ordering tests pass (test_contents_default_order)
  - Complex ordering (with rooms interleaved) marked xfail pending further investigation
- Added lexer apostrophe support for vocabulary words like `CAT'S`
  - Added `'` to valid atom characters in `is_atom_char()`
  - MDL0429 warning already implemented for apostrophes in vocab words
- Fixed MAP-CONTENTS/MAP-DIRECTIONS routine call placeholder corruption
  - Body statements in loops weren't using `_generate_nested_and_adjust`
  - Placeholder offsets were recorded relative to nested call, not outer loop code
  - Fixed by using `_generate_nested_and_adjust` for body and END clause statements
- Fixed SHIFT opcode stack underflow with negative arguments
  - Routine placeholder scanning was incorrectly matching data bytes
  - E.g., -3 (0xFFFD) followed by store=0x00 looked like placeholder 0xFD00
  - Added direct tracking for gen_routine_call placeholders
  - Added `_generate_nested_and_adjust` helper for proper offset tracking in nested calls
  - Scanning fallback now skips positions preceded by 0xFE/0xFF (likely large constants)
- Fixed backward branch offset calculation bugs
  - DEC_CHK backward branches in MAPR, MAPT, MEMBER used incorrect formula
  - Short-form branches cannot encode negative offsets; always use long form for backward jumps
  - Fixed 4 locations in gen_mapr, gen_mapt_fallback, gen_mapr_fallback, gen_member
- Fixed REPEAT/generate_repeat JUMP offset formula
  - Changed from `loop_start_pos - (current_pos + 3)` to `loop_start_pos - (current_pos + 1)`
  - The +2 from Z-machine formula was missing, causing off-by-2 error in backward jumps
- Extended TELL string placeholder range from 766 to 8190 slots
  - Changed from 0xFD00-0xFFFD to 0xE000-0xFFFD range
  - Allows Zork1's 2000+ unique strings to compile
- Separated TELL and string operand placeholder tracking
  - TELL strings: 0xE000-0xFFFD (8190 slots via `_tell_string_placeholders`)
  - String operands: 0xFC00-0xFCFF (256 slots via `_string_operand_placeholders`)
  - Prevents index collision between the two systems
- Fixed routine placeholder overflow (earlier session)
  - Changed from 8-bit indices to 16-bit placeholder values
  - Added deduplication via `_routine_to_placeholder` mapping

## Previous Changes (2025-12-26)
- Fixed IGRTR? and DLESS? to support variable second operands
  - Z-machine inc_chk/dec_chk can compare against variables, not just constants
  - Added tests for variable comparison values
- Fixed macro OPTIONAL parameter handling
  - Parser now tracks "OPTIONAL"/"OPT" keyword in macro param definitions
  - Uses 5-tuple format: (name, is_quoted, is_tuple, is_aux, is_optional)
  - macro_expander handles new format, counts only required params
- Fixed VALUE with FormNode operand (indirect variable access)
  - `<VALUE <GETB table index>>` now generates proper LOAD with indirect reference
  - Previously caused "can't extend bytearray with NoneType" crash
- Fixed direction exit condition validation
  - IF conditions can reference objects (not just globals)
  - `(WEST TO KITCHEN IF KITCHEN-WINDOW IS OPEN)` now works
- Fixed GO routine termination
  - GO routine now uses QUIT (0xBA) instead of RET
  - Z-machine behavior is undefined for returning from GO routine
- Fixed IN direction vs location property conflict
  - IN can be both a direction (DIRECTIONS declaration) and a location property
  - Parser now recognizes direction exit syntax (TO, PER, SORRY, etc.) to disambiguate

## Previous Changes (2025-12-26)
- Added MDL0429 warning infrastructure for vocab words with apostrophes
  - Warning is implemented but requires lexer support for `'` in atoms
  - Currently lexer treats all `'` as QUOTE tokens
- Marked 80 tests as xfail for unimplemented ZILF-specific features
  - All tests now pass, skip, or xfail (no failures)
- Fixed abbreviation encoding to preserve literal text
  - Abbreviation strings now encoded with `literal=True` to skip transformations
  - Added `literal` parameter to `encode_string` and `encode_text_zchars`
  - Space collapsing was incorrectly affecting abbreviation strings
- Investigated space collapsing feature
  - Space collapsing logic works correctly (reduces 2+ spaces after periods by 1)
  - PRESERVE-SPACES? global correctly controls behavior
  - **Limitation**: dfrotz strips trailing spaces from output lines
  - Tests expecting trailing spaces before newlines cannot pass with dfrotz
  - The encoding is correct but dfrotz's output buffering removes trailing spaces
- Added direction exit object validation
  - Rejects `(NORTH TO BAR)` when BAR object doesn't exist
  - Applies to TO, UEXIT, and direct object references
- Added property value validation for non-constants
  - Global variables cannot be used as property values
  - Only constants, objects, and literals allowed
  - Catches `<OBJECT FOO (BAZ GLOBAL-VAR)>` errors
- Added does_not_compile_with_error_count helper for tests
- Added ZIL0410 warning for unprintable characters in strings
  - Tab (0x09) only legal in V6, warns in V5 and earlier
  - Backspace, Ctrl-Z, and other control chars always warn
  - Newline (0x0A) and CR (0x0D) always allowed
- Added CRLF-CHARACTER support
  - `<SETG CRLF-CHARACTER !\^>` now sets custom newline character
  - Text encoder respects CRLF-CHARACTER (default: |)
  - Passed to ZTextEncoder via compile_globals
- Added warning control directives
  - `<SUPPRESS-WARNINGS? "ZIL0204">` suppresses specific warning
  - `<SUPPRESS-WARNINGS? ALL>` suppresses all warnings
  - `<SUPPRESS-WARNINGS? NONE>` unsuppresses all warnings
  - `<WARN-AS-ERROR? T>` converts warnings to errors
- Added ZIL0204 warning for LocalVarNode fallback
  - Warns when .X uses global instead of local
  - Codegen warnings now captured in CompilationResult
- Fixed error code extraction in test harness
  - SyntaxError exceptions now also extract error codes

## Previous Changes (2025-12-26)
- Fixed MAP-DIRECTIONS tests
  - Added ByteValue wrapper for direction exits (stored as single bytes)
  - GETB can now correctly read destination object from property table
  - Both MAP-DIRECTIONS tests now pass
- Fixed `.X` global fallback
  - LocalVarNode now falls back to checking globals if no local exists
  - `.X` syntax works for both local and global variables
  - Also fixed implicit return when routine ends with `.X` referencing a global
- Fixed LOADB opcode (2OP:0x10, not 0x11 which is GET_PROP)

## Previous Changes (2025-12-26)
- Fixed SPLICE macro support
  - `<CHTYPE '(...) SPLICE>` now correctly expands inline
  - Handles both list and FormNode quoted content
  - Fixes 4 macro tests for void/value context and arguments
- Fixed DO-FUNNY-RETURN? flag handling
  - When `<SETG DO-FUNNY-RETURN? T>` is set, RETURN exits routine not block
  - V5+ defaults to routine return unless explicitly set to false
  - V3/V4 defaults to block return (original ZILF behavior)
- Fixed AtomNode implicit return in routines
  - When a routine ends with an atom like `T`, it now correctly returns that value
  - Previously atoms fell through to default return 0
  - Added handling for constants, objects, and globals as final statements
- Fixed macro QUOTE unwrapping
  - Macros returning `'<FORM>` now correctly expand to `<FORM>`
  - Previously the QUOTE wrapper was kept, breaking macro expansion
  - This fixed the AND-with-macro test

## Previous Session Changes (2025-12-25)
- Added DO misplaced END clause detection
  - DO END clause must appear immediately after loop spec
  - `<DO (CNT 0 25) body (END ...)>` now correctly fails
  - Validates that END clauses don't appear after body statements
- Implemented short-circuit logical AND/OR
  - gen_and now evaluates left-to-right, returning false early if any operand is false
  - gen_or now evaluates left-to-right, returning first truthy value
  - BAND/BOR remain as bitwise operations using Z-machine AND/OR opcodes

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

### Version Support
- V7 has interpreter compatibility issues (xfailed in tests)
- V8 fully working with bocfel interpreter

### Remaining Work
See "What's Left" section for categorized xfailed tests.
All 656 passing tests cover basic ZILF functionality.

## What's Left

### XFailed Tests (17 remaining)

All remaining xfails are for advanced ZILF features not yet implemented:

**Interpreter Limitations (4 tests)** - Cannot fix in compiler:
- `test_two_spaces_after_period_*` (2) - dfrotz strips trailing spaces
- `test_unicode_characters_*` (2) - dfrotz/Glulx unicode handling

**CHRSET/LANGUAGE Encoding (4 tests)** - Custom character set support:
- `test_chrset_should_affect_text_*` (2) - Custom CHRSET encoding
- `test_language_should_affect_*` (2) - LANGUAGE directive for non-English

**LANGUAGE Lexing (1 test)**:
- `test_language_should_affect_lexing` - German character handling (ß → ss)

**PROPSPEC Features (2 tests)** - Property specification clearing:
- `test_vocab_created_by_propspec_should_work_correctly`
- `test_routines_created_by_propspec_should_work_correctly`

**Meta/Hooks (3 tests)**:
- `test_in_zilch_indicates_macro_expansion_context` - IN-ZILCH flag
- `test_routine_rewriter_can_rewrite_routines` - ROUTINE-REWRITER
- `test_pre_compile_hook_can_add_to_compilation_environment` - PRE-COMPILE

**V7 Interpreter (2 tests)**:
- V7 hello world tests - bocfel/dfrotz interpreter bugs

**Reader Macros (1 test)**:
- `test_make_prefix_macro_should_work` - MAKE-PREFIX-MACRO

### Priority Items for Future Work
1. PROPSPEC clearing support (override default PROPDEF patterns)
2. CHRSET/LANGUAGE encoding support
3. Meta/hooks (IN-ZILCH, ROUTINE-REWRITER, PRE-COMPILE)
4. Object ordering for complex mixed object/room definitions
