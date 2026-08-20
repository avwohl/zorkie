# Changelog

All notable changes to zorkie land here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for the public
surface (the `zorkie` CLI, the accepted ZIL/ZILF dialect, and the bytes of the
generated story file).

## 0.2.0

246 commits, 202 files, +68,242 / −11,428 lines, spanning 2025-12-06 to
2026-08-05. The 0.1.0 tree's own status file answered the question "Can compile
real games" with "No"; this is the release where it can. Twenty-six historical
Infocom ZIL sources, three purpose-built test games, and the two ZILF
sample games (Cloak of Darkness and the ZILF port of Colossal Cave) now compile
from source and play their walkthroughs to their real endings — Zork I to
350/350, Starcross to 400/400, Trinity and A Mind Forever Voyaging as the first
V4 games, and Border Zone compiling, booting and parsing as the first V5.

Two caveats on those numbers before the entries below. First, the end-to-end
"compile, play, win" harness lives in a separate repository (zwalker) and cannot
be run from this checkout; the per-game results quoted here are the ones the
landing commits record, not something this tree reproduces. Second, the game
sources themselves are 51 git submodules, so a plain `git clone` has none of
them.

Two changes can turn source that 0.1.0 accepted into a failed build or a
different story file. See **Migration notes** at the end of this section.

### Added

- **The classic MDL/ZILCH dialect that historical Infocom sources are
  written in.** 0.1.0 could emit opcodes but had no model of what a real
  1980s ZIL tree contains. This release adds the compact `VERBS` and
  syntax-line tables, `PREACTIONS` and `PREPOSITIONS` table generation from
  `SYNTAX` definitions, `ACT?<verb>` / `V?<name>` / `A?<adjective>` /
  `W?<word>` constant families, `PSEUDO` objects and room `THINGS` tables,
  room `GLOBAL` byte arrays, the full `UEXIT` / `NEXIT` / `FEXIT` / `CEXIT` /
  `DEXIT` exit encodings, two-slot dictionary part-of-speech values,
  `PROPDEF` pattern matching with `MANY` and `:GLOBAL` types, `BIT-SYNONYM`
  flag aliasing, `DEFINE-GLOBALS`, `ORDER-OBJECTS` / `ORDER-TREE`,
  `LONG-WORDS?`, `COMPACT-VOCABULARY?`, `PREP-SYNONYM`, `SIBREAKS`,
  `LOWCORE-TABLE`, `FUNNY-GLOBALS` for programs with more than 240 globals,
  and the `<FILE-FLAGS MDL-ZIL?>` sub-dialect (`MSETG`, `SETG20`, `DEFINE20`,
  `Z`-prefixed opcode spellings, ADECL stripping).

- **The ZILF dialect and its standard library.** `ZIP-OPTIONS` tracking with
  `IF-UNDO` / `IF-COLOR` / `IF-MOUSE` / `IF-SOUND` / `IF-DISPLAY` / `IF-DEBUG` /
  `IF-BETA` expansion, the `LIBRARY-MESSAGE` system with
  `DEFAULT-LIBRARY-MESSAGES` / `REPLACE-LIBRARY-MESSAGES` alias chains,
  `DEFAULT-DEFINITION` and `REPLACE-DEFINITION`, `DEFSTRUCT` with constructors
  and field accessors, the pronoun subsystem (`FINISH-PRONOUNS` emitting
  `SET-PRONOUNS` / `EXPAND-PRONOUN` / `V-PRONOUNS` plus their tables), and the
  new-parser vocabulary format (`NEW-PARSER?`, `VWORD` tables, `NEW-ADD-WORD`,
  `WORD-FLAG-TABLE`, `NEW-SFLAGS`). `_generate_verbs_table_zilf` emits the
  byte layout the library's `MATCH-SYNTAX` actually reads — a `VERBS` word
  array indexed by `255 - <verb's dictionary byte-5 value>`, each block a count
  byte followed by 8-byte records in reverse order. Before that layout existed,
  `MATCH-SYNTAX` never set `PRSA` and every command in a library game
  mis-dispatched.

- **A compile-time MDL evaluator, used as one.** `DEFMAC` / `DEFINE`
  expansion with quasiquote, unquote and splice (`` ` ``, `~`, `!.X`, `!,X`),
  `MAPF` / `MAPRET`, `NTH` / `REST` / `LENGTH` over `FORM`s as MDL primtype
  `LIST`, `PARSE` / `UNPARSE`, `TYPE?` including `CHARACTER` and `VECTOR`,
  `GASSIGNED?`, `CONS`, arithmetic, `EVAL`, top-level list threading across
  forms, and `<EVAL <FORM ROUTINE …>>` / `<EVAL <FORM ROOM …>>` emission. This
  is what lets a game *generate* code at compile time: Colossal Cave's
  `MAZE-ROOM` / `DIFFMAZE-ROOM` / `DEAD-END-ROOM` constructors materialise
  roughly 37 maze and dead-end rooms that previously produced nothing
  ("undefined object ALIKE-MAZE-6"), its `FINISH-HINTS` emits eight real
  `HINT-*-TBL` constants instead of leaving a queued interrupt to `APPLY` a
  garbage address, and the ZILF library's `SCOPE-STAGE` list-building generates
  its six scope-stage routines instead of leaving object scope empty.

- **Core ZIL control flow that 0.1.0 did not have.** `DO` loops with their
  `END` clause, the `MAP-CONTENTS` and `MAP-DIRECTIONS` iteration forms,
  activation names on `PROG` and `REPEAT` with `RETURN` and `AGAIN` targeting a
  named activation, and `TELL-TOKENS` pattern matching.

- **ZIL character literals (`!\X`).** The backslash is ZIL read syntax meaning
  "the next character literally", not a C escape: `!\n` is the letter `n` (110)
  and `!\0` is the digit `0` (48). That reading is what every digit parser's
  `<- .CHR !\0>` and the standard "type y or n" test `<EQUAL? .CHR !\N !\n>`
  depend on. Codegen and the macro expander parse them in lock-step. (0.1.0
  had no character-literal support at all; an escape-mapping reading of `!\X`
  existed only inside this development window and never shipped.)

- **V4 and V5 targets.** V4 (`EZIP`) reached working output for Trinity and A
  Mind Forever Voyaging; V5 (`XZIP`) for Border Zone, which compiles to a
  172,672-byte image, boots to its chapter menu and parses commands. Supporting
  work: the header extension table, the V5+ Unicode table, `CHRSET` custom
  alphabets, the `LANGUAGE` directive for German text encoding, `call_vs2` for
  wide calls, and V1–V8 header/serial-number handling.

- **Story-file size reduction, on by default for V1–V4.** Nine games code-
  generated correctly but overflowed their version's cap. Three levers close
  the gap. Abbreviation selection (`zilc/zmachine/abbreviations.py`) now
  computes three candidate sets — a greedy/iterative pass, the original ZILCH
  `freq.xzap` listing when the source ships one, and a CELF marginal-gain
  selector — scores each against a DP-optimal encoded-word cost model, and
  keeps the cheapest. A routine-local peephole
  (`_routine_peephole`) with full branch- and jump-offset repair drops
  unreachable code after an unconditional transfer, folds `push #c` +
  `ret_popped` into `ret #c`, fuses a store-to-stack with the following `pull`,
  narrows `add v,#1` to `inc v`, folds constant-condition `jz`, drops jumps to
  the next instruction, re-encodes VAR-form 2OPs into the long form, and
  inverts a branch-over-jump into a direct branch. Codegen additionally inlines
  `PRINT` for single-use literals (ZILCH's `PRINTI`), eliminates dead AUX
  stores, folds byte-identical routines (gated by an address-taken analysis so
  routines referenced as data are never folded), trims unread AUX locals, and
  sizes the `VERBS` pointer table to real entries instead of a fixed 256.
  Measured effects recorded in the landing commits: zork1 114,564 → 85,762
  bytes; Trinity 263,760 → 246,316. The whole peephole is gated to version ≤ 4,
  so V5+ builds get none of it.

- **A diagnostic code system.** 0.1.0 had none. Errors and warnings now carry
  ZILF-style identifiers — `ZIL0415` undefined routine, `ZIL0112` routine call
  with too many arguments, `ZIL0402` version-specific call-argument limits,
  `ZIL0210` unused local, `ZIL0211` unused flag, `ZIL0200` bare atom used as a
  global index, `MDL0426` verb/action limits, `MDL0429` vocabulary word with an
  apostrophe, two dozen codes in all — and compilation stops after 100 errors
  with `ZIL0500` rather than printing an unbounded wall.

- **`--allow-undefined-routines`.** Downgrades `ZIL0415` from fatal to a loud
  per-routine warning and compiles each call to a missing routine as `call 0`,
  a no-op returning false. It exists for provenance-incomplete historical
  sources whose missing routines sit off the boot path (minizork2's `V-SKIP`,
  the Infocom sampler's `DO-RESTART`). Off by default.

- **A real test suite.** 0.1.0 shipped one test file with five test
  functions. This tree has 32 test files and roughly 707 test functions, most
  of them under `tests/zilf/` — opcodes, codegen, flow control, objects,
  tables, `TELL`, vocabulary, syntax, macros, quirks, versions — plus
  `tests/zilf/interpreter/` covering the compile-time MDL evaluator on its own.
  Much of it is converted from ZILF's own integration and interpreter suites,
  which is why the project now states GPL v3 in its README and docs.

- **Inspection tools.** `tools/analyze_zmachine.py` dumps a compiled image;
  `tools/measure_string_orphans.py` instruments `StringTable` registration
  against use and reports orphaned entries. The latter exists to record a
  negative result worth not re-chasing: a hypothesised string-table GC worth
  several KB measures 6 orphans totalling 66 bytes of 12,964 on Trinity and 0
  of 436 on zork1. Mark Howell's ztools 7/3.1 (`txd`, `infodump`, `showverb`,
  …) is vendored under `tools/ztools/` as the disassembly oracle.

- **PyPI trusted publishing.** `.github/workflows/publish.yml` builds and
  publishes on a published GitHub release, using OIDC rather than a stored
  token.

- **An experimental Glulx path.** `<VERSION GLULX>` in source selects version
  256 and routes through `zilc/glulx/assembler.py`. Treat it as unfinished: the
  CLI's `-v` accepts only 1–8, so the target is reachable from source alone,
  and nothing executes the output — the single Glulx test asserts only that the
  source compiles, because glulxe drives GlkTerm and writes nothing the harness
  can capture.

### Changed

- **A call to an undefined routine is now a fatal error.** 0.1.0 reported
  nothing at all, so a typo in a routine name produced a story file that jumped
  somewhere arbitrary at run time. It is now `ZIL0415`, one error per call
  site, with `--allow-undefined-routines` as the deliberate escape hatch.
  Source that built under 0.1.0 can now fail to build.

- **`PROPDEF` defaults populate the property-defaults table.** Per Z-Machine
  Standard 12.2, `<PROPDEF NAME default>` gives every object that lacks `NAME`
  that value; zorkie previously left the table zero, so `GETP` on a missing
  property returned 0 (Stationfall's Thermos read `CAPACITY` 0). Correcting it
  changes generated output for any source using `PROPDEF` defaults — minizork
  and zork2 stopped matching their old zorkie-specific walkthroughs and started
  matching the official binaries instead.

- **Placeholders are resolved structurally and positionally, not by scanning
  for magic bytes.** The placeholder bands (`0xF0`, `0xFA`–`0xFC` high bytes)
  that let codegen defer vocabulary, routine, table and string addresses are
  themselves new here — 0.1.0's 388-line assembler had no such mechanism, only
  a byte-stepped scan for `0x8D 0xFF 0xFE` string markers. Earlier revisions of
  the band scheme within this window found unresolved references by sweeping
  the image for those byte patterns and rewriting whatever matched. Legal data
  matches those patterns, so the sweeps corrupted resolved code: a
  `jump #02fc` in zork1's `MAIN-LOOP-1` became a string address, the
  dictionary's `"` byte at 0x3EFB was re-read as a
  placeholder and clobbered a `je` branch, and a branch byte `0xF0` followed by
  opcode `0x2E` was read as placeholder `0xF02E`. Discovery now walks
  instruction boundaries, scans are word-aligned or replaced entirely by
  positions recorded at emission time, patched positions are shared between
  passes, and code and data string markers live in separate bands. The same
  rework removed the 8-bit index ceilings: vocabulary words, property routines,
  tables and string data were addressed as `<band>|idx` with the index in the
  low byte, so the 257th distinct item aliased the first (Trinity has 374
  distinct vocabulary words; zork3 has more than 256 property-routine
  references).

- **Abbreviation selection is deterministic.** It previously depended on dict
  ordering and therefore on `PYTHONHASHSEED`, so two builds of one source could
  differ. Selection now has an explicit total-order tie-break, and a given
  source yields byte-identical output.

- **README rewritten**, with the architecture, the two-tier testing story, and
  a GNU GPL v3.0 statement (the packaging metadata already declared
  `GPL-3.0-or-later`).

- **Size levers and the test harness's interpreter choice are overridable from
  the environment**:
  `MP_SZ3_LEVERS`, `MP_SZ3_PEEP` and `MP_SZ3_RULES` select which levers and
  peephole rules run, `ZORKIE_NO_FREQ` suppresses the `freq.xzap` abbreviation
  candidate, and `ZORKIE_INTERPRETER` overrides the interpreter the test
  harness drives.

### Fixed

Far too many individual miscompiles landed here to list one by one. They fall
into six families; each entry below names one representative with its observable
consequence.

- **Branch offsets computed from size estimates instead of from emitted
  bytes.** A branch-context `<EQUAL? x a b c d e f>` compiles to a chain of
  `JE` instructions, each non-final one branching past the rest of the chain.
  The skip offset was precomputed assuming every comparand encodes in one byte;
  dictionary words encode in two and force VAR form, so the branch landed
  inside the next `JE`'s operands and the routine executed garbage. The ZILF
  library's `PARSE-NOUN-PHRASE` contains exactly that shape —
  `<EQUAL? .W ,W?ALL ,W?EVERY ,W?EVERYTHING ,W?BOTH ,W?ANY ,W?ONE>` — so
  `take all` and `drop all` printed nothing at all in every library game.
  `generate_condition_test` now emits 2-byte placeholders and backpatches them
  once the chain's real size is known. Same family: a `DO` loop whose body
  exceeded 63 bytes branched two bytes short into its own backward `JUMP` and
  executed data (Spellbreaker's cube vault crashed), and `MAP-DIRECTIONS`
  emitted a truncated exit branch.

- **Stack discipline that only survived a lenient interpreter.** Several
  generators pushed nothing where their callers expected a value, or used
  variable operand 0 as if it pushed and popped. `gen_voc` returned empty bytes,
  so `<=? .W <VOC "it" OBJECT>>` — what the library's macro-generated
  `EXPAND-PRONOUN` emits per pronoun — compiled to `je x,(sp)` over stale
  stack. `gen_lowcore_table` bracketed an already-unrolled loop with
  `STORE 0x00` and `INC 0x00`, which are *indirect* references that read and
  write the top of stack in place rather than pushing or popping, so every
  ZILF-library game died with "Fatal error: Stack underflow" at turn 1 under
  dfrotz; the same routine's unrolled handlers emitted zero bytes because a
  `FormNode` was constructed with its operand list passed as the operator.
  `gen_spaces` had the same `var-0` antipattern in a `DEC_CHK` plus a
  `PRINT_CHAR` type byte that decoded as four operands. A routine whose last
  form was `<MAP-CONTENTS>` or `<MAP-DIRECTIONS>` fell through to the implicit-
  return `RET_POPPED` and popped the *caller's* frame, and a bodyless test
  clause in a tail `COND` did the same. `gen_split` consumed a `FORM` operand
  from the stack without generating it. The practical consequence: builds that
  appeared to work under a forgiving interpreter now also run under a
  spec-strict one.

- **V4-specific encoding.** Sixteen-bit constants were truncated in long-form
  2OP and short-form 1OP operands across roughly 30 emission sites, so
  `insert_obj #418` became `insert_obj #162` and teleported the player on turn
  1 in any game with more than 255 objects; new `_asm_2op` / `_asm_1op` helpers
  switch to the wide forms and leave V3 output byte-identical. `INTBL?`
  compiled to a bare `RFALSE` stub in V4 because `scan_table` was gated V5+,
  and that stub returned from the *containing* routine. The V4 property header's
  second size byte was missing bit 7 (Standard 12.4.2.1.1), so every long
  property read as length 1 or 2 — no noun matched and movement failed. Calls
  with four to seven arguments were silently truncated to three because only
  `call_vs` was ever emitted; A Mind Forever Voyaging's parser passes its noun
  match table as the fourth argument, which arrived as 0, and `OBJ-FOUND` then
  wrote matches over the story header. Scratch-global allocation collided with
  the `SOFT-GLOBALS` table pointer at variable 240, so every funny-global read
  returned wild memory.

- **Dictionary and vocabulary identity.** A backslash-escaped spelling
  (`FROG\'S`) was stored and z-encoded *with* the backslash, so the `W?FROG'S`
  fixup pass could not find it and late-added the unescaped word after the
  word-offset snapshot. The insertion re-sorted the dictionary and shifted every
  entry after it by one, staling 43 objects' `SYNONYM` fixups, so nouns
  resolved to the alphabetically preceding word — `take stool` answered "You
  can't see any stool here!". `Dictionary._norm` now unescapes at one choke
  point so every spelling of a word lands on one entry. Separately, vocabulary
  placeholders were minted per occurrence rather than per word (294 of them in
  Hollywood Hijinx), so the 257th overflowed its 8-bit index and aliased `hole`
  to `all`.

- **Data that looked like a marker.** The table-data string scan stepped byte
  by byte and treated any `0xFC` as a code-string placeholder's high byte. It
  false-matched the *low* byte of a legal literal: Suspect's `COCHRANE-LOOP`
  stores −4 as `0xFFFC`, the straddling `FC 00` was overwritten with string #0's
  packed address, corrupting the party-clock daemon tick — which flipped the
  trial verdict at the end of the game. The scan is gone; every table string
  marker is now resolved point-wise at offsets recorded at emission.

- **Macro expansion that quietly dropped code.** `DEFMAC` `OPT` parameter
  defaults were discarded at parse time, so the `P?` / `PE` / `MULTIFROB`
  family expanded wrong and 135 Lurking Horror routines — around 50 KB of the
  game — compiled to garbage. `%<NAME …>` calls of a user-defined compile-time
  selector were stripped to zero placeholders, deleting every release-arm
  `<APPLY …>` in Suspect's dispatch so that all commands became silent no-ops.
  MDL `NTH` / `REST` treated a `FORM` as opaque instead of as primtype `LIST`,
  so quoted-atom clauses never matched and character names decoded as
  abbreviation-table garbage. `<FORM GVAL obj>` from a `DEFMAC` emitted
  nothing, so Witness's `DOBJ?` / `IOBJ?` compared against stale stack and
  nobody answered any question. `MAP-SCOPE`, which computes into its own AUX
  variables, was inlined instead of evaluated, leaking 19 locals into
  `MATCH-NOUN-PHRASE` and masking its header nibble to a zero-body stub.

Beyond those: value-context predicates (`L?`, `G?`, `ZERO?`, `T?`, `F?`,
`BTST`, `PROB`, `VERB?`) used a branch-to-`RTRUE` idiom that returned from the
enclosing routine when used outside tail position — and `VERB?` emitted
`inc_chk`, incrementing `PRSA`; nested-form operands are now evaluated and
spilled in roughly 40 two- and three-operand generators that previously read
whatever was on the stack; `<>` resolves to constant 0 everywhere including
call arguments; `SYNTAX` object-flag groups merge instead of last-one-wins;
and `<SYNTAX … = V-ROUTINE PRE-X X>` attaches the preaction to the named
action as well as the routine, so `<VERB? WATER>` fires for `water plant`.

### Removed

- **Nineteen stale documents under `docs/`** (`COMPLETION_STATUS.md`,
  `ACTUAL_MISSING_5_PERCENT.md`, `PROGRESS_REPORT.md`, `OPCODES_IMPLEMENTED.md`,
  `ZORK1_COMPILATION_STATUS.md`, and similar) **and seven under
  `tests/test-games/`.** They recorded percentage-complete claims from a period
  when the compiler could not build a real game, and every one of them
  contradicted the measured state. `STATUS.md` is now the single status
  document and says so in its first paragraph.

- **`tests/test-pairs/LIBMSG.zil`, `LIBMSG-DEFAULTS.zil` and `QQ.zil`.**
  Uppercase duplicates of the lowercase files beside them; on a
  case-insensitive filesystem the pair collided and the checkout was dirty on
  arrival.

### Test surface

32 test files, roughly 707 test functions. The last measured run recorded in
a landing commit is 728 passed, 3 failed. Those three — `test_color`,
`test_read_v5`, and a `TELL` two-space test — have been failing for the whole
window and are carried as a known baseline rather than fixed or marked
`xfail`; anyone running `pytest` after installing will see them. Game-level
verification (compile a real ZIL source, replay a walkthrough, check the
ending) runs from the separate zwalker repository against 31 games and is not
reproducible from this checkout.

### Known limitations

- V6, V7 and V8 output is not verified against real games; V5 has one game
  compiling, booting and parsing, not winning.
- The Glulx path is experimental and has no execution test at all; its one
  test asserts only that the source compiles.
- The size levers and peephole are gated to version ≤ 4, so V5+ output gets
  none of them.
- The README's status section describes an earlier state of the project than
  `STATUS.md` does; `STATUS.md` is the one that is kept current.

### Migration notes

- Calls to undefined routines now fail the build. Either define the routine or
  pass `--allow-undefined-routines`, which stubs each call as `call 0` and
  warns per routine.
- `PROPDEF` defaults now reach the property-defaults table, so `GETP` on an
  object lacking that property returns the declared default instead of 0. Any
  behaviour tuned around the old zero is affected.
- The size levers and the peephole are on by default for V1–V4 output. If you
  need to compare against an older build byte for byte, set `MP_SZ3_LEVERS` to
  a value naming none of them (`MP_SZ3_LEVERS=none`); an empty value is falsy
  and restores the `inline,tail,peep` default rather than clearing it.

---

Releases before 0.2.0 are not documented here; see the git log.
