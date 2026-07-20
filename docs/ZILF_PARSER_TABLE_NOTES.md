# P4 — ZILF-library VERBS/syntax-table + downstream parser blockers

## TL;DR
- The stated core gap (ZILF syntax-table byte layout for MATCH-SYNTAX) is **fixed and
  verified**: cloak's `MATCH-SYNTAX` now finds the right syntax line and sets `PRSA`
  correctly (e.g. `hang cloak on hook` → matches `PUT OBJECT ON OBJECT`, `read message`
  → matches `READ OBJECT`). Directions dispatch too.
- cloak still **won=False**. It no longer crashes and runs all 5 route commands, but
  produces no command output because of the *next* pre-existing blocker (bug #8 below):
  `SAVE-PARSER-RESULT` copies over the parser globals (zeroing `PRSA`/`PRSO`/`PRSI`)
  before `PERFORM` runs, so `PERFORM` is always called `(0 0 0)`.
- **No regression.** pytest 696 passed / 3 pre-existing failed; all 5 classic canaries
  and all 3 ZILF toys still WIN (lines below).

## The ZILF syntax-table byte layout — what MATCH-SYNTAX reads vs what we now emit
Authoritative sources: `tests/test-pairs/parser.zil` (`MATCH-SYNTAX` /
`MATCH-SYNTAX-LINE?`, the `SYN-*` constants) and the real ZILF compiler
`tests/test-games/zilf/src/Zilf/Compiler/Compilation.Syntax.cs`
(`BuildOldFormatSyntaxTables`, non-compact branch).

`MATCH-SYNTAX` does:
```
PTR = <GET ,VERBS <- 255 ,P-V>>      ; P-V = the verb's DICTIONARY value (byte 5)
CNT = <GETB PTR 0>                    ; number of syntax lines
first line at PTR+1; each line SYN-REC-SIZE = 8 bytes:
  byte 0 SYN-NOBJ    object count (0/1/2)
  byte 1 SYN-PREP1   preposition value before object 1 (dict prep value; 0 if none)
  byte 2 SYN-PREP2   preposition value before object 2
  byte 3 SYN-FIND1   GWIM FIND attribute number for object 1 (0 if none)
  byte 4 SYN-FIND2   GWIM FIND attribute number for object 2
  byte 5 SYN-OPTS1   scope search bits for object 1
  byte 6 SYN-OPTS2   scope search bits for object 2
  byte 7 SYN-ACTION  action number -> PRSA (indexes ,ACTIONS)
```
Scope bits (parser.zil `SF-*` / ZILF `ScopeFlags.Original`): HAVE=2 MANY=4 TAKE=8
ON-GROUND=16 IN-ROOM=32 CARRIED=64 HELD=128 (default 0). If the game defines
`NEW-SFLAGS`, ZILF's custom map + SEARCH-STANDARD(8) default is used instead.

This is now emitted verbatim by `_generate_verbs_table_zilf` (records in **reverse**
definition order, mirroring ZILF's `verb.Reverse()`).

### The two things the previous ZILF path got wrong (both fixed)
1. **Record format.** The old path emitted an 8-byte `[verbptr, obj1, obj2, opts, pad]`
   layout with no count byte and indexed by *action* number. Nothing in parser.zil reads
   that. Replaced with the count-byte + 8-byte `SYN-*` records above.
2. **VERBS index key.** VERBS must be indexed by `255 - <the verb's DICTIONARY byte-5
   value>`. The dictionary stores each verb word's per-verb `V?/ACT?` constant
   (`verb_action_num`, e.g. `ACT?PUT=20`), **not** the count-down `verb_numbers`
   (`PUT=246`). My first rewrite indexed by `verb_numbers` and every PUT/READ/EXAMINE
   lookup missed; now keyed by `verb_action_num`, matching `compiler._dict_verb_num`.

## Files / functions changed (patch: `p4.patch`, 3 files)
- `zilc/codegen/codegen_improved.py` — `_generate_verbs_table_zilf` rewritten to the
  layout above; `encode_obj` supports both the default SF-* scheme and NEW-SFLAGS;
  `generate_repeat` now emits FORM/var/large-const loop-var initializers (was silently
  dropped); `gen_set` materializes reserved-marker-band constants via `<BOR (v&0x7FFF)
  0x8000>`.
- `zilc/parser/macro_expander.py` — `MacroExpander._expand_quasiquote` now evaluates
  `~<PARSE/STRING/SPNAME/...>` name-builders, guarded by new `_all_locals_bound` so
  nested macros (WITH-HOOK) whose locals aren't yet bound fall back to substitution.
- `zilc/compiler.py` — `_toplevel_cond_pass` now skips a bare backslash the same way
  `_extract_balanced_content` does.

## The cascade uncovered (each was masking the next; #1–#6 fixed, #7 open)
cloak was the first `_is_classic_parser=False` game to actually *run* commands, so it
exposed a stack of pre-existing bugs. In order of discovery:

1. **Syntax-table byte layout** (the stated gap) — fixed (above).
2. **`~<PARSE <STRING ...>>` in DEFMACs not evaluated.** `COPY-TO-BUFS`/`ACTIVATE-BUFS`/
   `WORD?`/`VERB?` expanded to `<GVAL <PARSE ...>>` instead of `<GVAL EDIT-READBUF>`; the
   garbage operand made `COPY-TABLE` scribble over low memory and crash the first command.
   Fixed in `_expand_quasiquote` (+ `_all_locals_bound` guard so WITH-HOOK doesn't emit
   undefined `HOOK-BEFORE-`/`HOOK-AFTER-` routines).
3. **REPEAT loop-var FORM initializer dropped.** `<REPEAT ((I <OR ,P-CONT 1>) W V) ...>`
   left `I=0`, so `GETWORD? 0` → "I don't know the word 'west'". Fixed in `generate_repeat`.
4. **`_toplevel_cond_pass` deleted the bare-direction movement clause.** A bare `\"`
   buzzword outside a string desynced its string parity, so `<GET ,VERBS <- 255 ,P-V>>`'s
   enclosing routine-internal `<COND (<AND .DIR ...> <SETG PRSA ,V?WALK> ...)>` was seen at
   depth 0 and compile-time "folded" to nothing (PRSA/PRSI SETGs vanished). Fixed the
   backslash handling; movement clause restored.
5. **VERBS indexed by the wrong verb number** (verb_numbers vs verb_action_num) — fixed
   (above).
6. **`-999` sentinel corrupted.** `<SET BEST-SCORE -999>` in `MATCH-SYNTAX` emitted 0xFC19,
   which collides with the string-operand placeholder band `0xFC00|25`; the position-blind
   string scan rewrote it to a string address (12813), so `<G? .S .BEST-SCORE>` never fired
   and every line "scored 0". Fixed by materializing reserved-band SET constants via BOR.

## #7 — THE CURRENT STALL (precise, for the next pass)
After #1–#6, the parser is correct: for `west` the movement clause runs `PRSA<-2` (=V?WALK)
at PARSER+0x2452; for `read message`/`hang cloak on hook` MATCH-SYNTAX matches the right
line and sets PRSA. **But** just before returning, the parser saves state for AGAIN via
`SAVE-PARSER-RESULT ,AGAIN-STORAGE`, which calls
`<COPY-READBUF ,READBUF <PST-READBUF .DEST>>` and `<COPY-LEXBUF ,LEXBUF <PST-LEXBUF .DEST>>`.

Root cause: `AGAIN-STORAGE = <PARSER-RESULT>` is `<MAKE-PARSER-RESULT 'PARSER-RESULT
<ITABLE 26 (BYTE)> 'PST-PRSOS <PRSTBL> 'PST-PRSIS <PRSTBL> 'PST-READBUF <MAKE-READBUF>
'PST-LEXBUF <MAKE-LEXBUF>>`. In `compiler._build_struct_table`, a MAKE-<STRUCT> whose base
is an **`<ITABLE ...>`** (as opposed to an explicit `<TABLE ...>`) **keeps the base and
DROPS the field initializers** (see the comment at compiler.py ~line 1631). So the struct's
`PST-PRSOS/PST-PRSIS/PST-READBUF/PST-LEXBUF` word fields stay 0. At runtime:
```
AGAIN-STORAGE = 0x0C12, and its 26 bytes are all 0
<PST-READBUF AGAIN-STORAGE> = 0   ->   COPY-READBUF(,READBUF, 0)
   -> COPY-TABLE(src=0x863, DEST=0,   len=0x32)   ; copies 50 bytes to addr 0..0x31
<PST-LEXBUF  AGAIN-STORAGE> = 0(+2) ->  COPY-LEXBUF(...) -> COPY-TABLE(DEST=0x02, ...)
```
Those copies overwrite the header/low-memory + the global block, zeroing `PRSA`/`PRSO`/
`PRSI` (traced: `PRSA<-2` at PARSER+0x2452, then `PRSA<-0` inside COPY-TABLE at 0x2A5E).
By the time `MAIN-LOOP` calls `<PERFORM ,PRSA ,PRSO ,PRSI>` it is `PERFORM(0 0 0)` → the
action routine (V-WALK, V-READ, MESSAGE-R) never runs and no output is printed.

**Exact fix target for the next pass:** make `compiler._build_struct_table`
(`_process_defstruct`) honor field initializers for an `<ITABLE ...>` base — allocate the
`'PST-*` sub-tables (`<PRSTBL>`, `<MAKE-READBUF>`, `<MAKE-LEXBUF>`) and write their
addresses into the base struct's word fields at their `'OFFSET`s (compile-time for the
CONSTANT `AGAIN-STORAGE`/`P-OOPS-DATA`, or runtime `PUT`s at GO). Until then, ANY
`<SETG PRSx>` the parser does is destroyed by SAVE-PARSER-RESULT. There may be further
layers after this (action output / room-description on movement were not reachable yet).

## Gate results (final code)
pytest: **3 failed, 696 passed** (pre-existing: test_color, test_read_v5, TELL two-space).

Classic-parser canaries (classic path, untouched by the VERBS change) — all WIN:
```
minizork_verified_350.txt: VERIFIED 350/350 seed1 | died=False | won=True
zork1_zorkie_350.txt:      VERIFIED 350/350 seed3 | died=False | won=True
hhgg_verified_400.txt:     VERIFIED 400      seed1 | died=False | won=True
suspect_zorkie_win.txt:    VERIFIED 23       seed1 | died=False | won=True
trinity_zorkie_100.txt:    VERIFIED 0/100    seed1 | died=False | won=True
```
ZILF toys (ZILF path; no `<SYNTAX>` so they emit no VERBS table — verified unaffected):
```
microquest_zorkie_win.txt: VERIFIED 10  seed1 | died=False | won=True
mazekey_zorkie_win.txt:    VERIFIED 0   seed1 | died=False | won=True
reactor_zorkie_win.txt:    VERIFIED 862 seed1 | died=False | won=True
```
cloak: `VERIFIED 0/None seed1 | 5 cmds | died=False | won=False` (stalls at #7).
advent: compiles (`-v 3`) but only to a 614-byte stub; same ZILF library, so it hits the
same #7 (and later) blockers — not a win.
