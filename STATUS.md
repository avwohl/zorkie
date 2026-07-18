# Zorkie STATUS

Last measured: 2026-07-18 (session 5: **MINIZORK PLAYS TO A VERIFIED 350/350 WIN**
-- the first real Infocom game zorkie compiles that plays end to end). This file is
the single source of truth for project
status and overrides any status claim in older docs. Reference/spec docs (Z-machine
and ZIL specs, dialect notes, header/opcode references) live under docs/ and
tests/test-games/ and are not status reports.

zorkie = from-scratch ZIL -> Z-machine compiler in Python.
zwalker = independent Z-machine interpreter (../zwalker) used as the end-to-end
oracle: compile ZIL -> run the .z in zwalker -> replay a walkthrough to a verified win.

## Headline

- The Z-machine back end is broad (V3 is the only version that compiles real games):
  instruction set, headers, object/property tables, dictionary, ZSCII + abbreviations,
  routine/packed-address layout, multi-file compilation (INSERT-FILE/IFILE), COND
  branching, object manipulation, and daemons (QUEUE/INT via gen_queue/gen_int in
  zilc/codegen/codegen_improved.py).
- The ZILF standard library parses fully (parser.zil/verbs.zil via INSERT-FILE),
  including MDL quasiquote/unquote templates and %<...> compile-time forms.
- **MILESTONE: minizork (the real 1987 Release-0 mini.zil) compiles and PLAYS TO A
  VERIFIED 350/350 WIN in zwalker** -- the complete game, 420 commands, through the
  Stone Barrow victory, with room/score progression lockstep-identical to the
  official binary over the whole route. Verified replay:
  ../zwalker/walkthroughs/minizork_zorkie_350.txt (RNG seed 1); reference build
  kept locally at builds/minizork_zorkie.z3 (gitignored; reproducible from source).
- zwalker L2 harness (../zwalker/scripts/test_zorkie_game.py) is green on 4 games
  (microquest, mazekey, reactor, minizork): each is compiled with zorkie, run in
  zwalker, and replayed to its real win. minizork recompiles mini.zil on every run.
- Getting there took ~50 general codegen/assembler/dictionary fixes over 5 sessions
  (catalogs below). The same fix classes plus the lockstep-differ method are the
  roadmap for zork1, zork3 and starcross, which boot but do not yet win.

## Real Infocom games: measured status

Of zwalker's 50 verified solves, 26 are Infocom ZIL (the only zorkie candidates;
the rest are Inform). Compile results for those 26 (source in
tests/test-games/infocom-zil/<game>/):

COMPILES to a valid .z3 and RUNS under zwalker:
	minizork-1987	mini.zil	72KB	**WINS 350/350** -- the complete game plays to the Stone Barrow victory; verified replay ../zwalker/walkthroughs/minizork_zorkie_350.txt (420 cmds, seed 1), registered as a counted game in the zwalker L2 suite.
	zork1		zork1.zil	108KB	boots "West of House", reaches READ, dispatches commands. Same parser pipeline as minizork -- NEXT TARGET: run the minizork lockstep-differ method against the official binary and fix divergences one by one.
	starcross	starcross.zil	103KB	boots, reaches READ; vocabulary lookup fails -> every command "I beg your pardon?" (separate issue)
	zork3		zork3.zil	109KB	boots, renders room; then "write to static memory at 0x2826" (a separate bad-store bug)

CODE-GENERATES FULLY but EXCEEDS the story-file size limit (text-compression gap;
see bucket 2) -- 9 games, the single biggest bucket:
	V3 (>128KB): ballyhoo 198KB, moonmist 196KB, wishbringer 183KB,
	  leathergoddesses 176KB, plunderedhearts 173KB, stationfall 157KB,
	  hitchhikersguide 155KB
	V4 (>256KB): trinity 349KB, amfv 324KB

DOES NOT COMPILE yet (see buckets 3 and 4):
	lurkinghorror, spellbreaker, zork2, deadline, suspect, witness, sorcerer,
	planetfall, suspended, hollywoodhijinx, cutthroats, infidel, enchanter

## Blocker buckets

### 1a. FIXED: gen_or short-circuit branch-offset bug (was the shared derail)
The shared object-description derail (minizork/zork1/zork3 crashing right after the
first room) was a one-byte codegen bug in gen_or (short-circuit logical OR),
codegen_improved.py ~15053. After evaluating an OR operand it emits
`JZ stack ?skip` then a 3-byte `JUMP` to the success label. The JZ branch offset was
hardcoded 0xC3 (offset 3), but the Z-machine branch rule is
target = addr_after_branch + offset - 2, so offset 3 skips only ONE byte of the 3-byte
JUMP -- landing the branch one byte into the JUMP. Execution then decodes misaligned
bytes and eventually hits an illegal 2OP:0x00 and halts. Fix: offset must be 5 (0xC5)
to clear the whole JUMP. (gen_and, the sibling, was already correct -- it patches its
offsets with the proper formula.) This fix made minizork and zork1 run their main
loop instead of crashing on the opening LOOK -> DESCRIBE-OBJECTS -> PRINT-CONT path.
Minimal repro: `<COND (<OR .VAR <FSET? .Y ,F>> <TELL "x">)>` derailed before the fix.

### 1b. FIXED: minizork PARSER div-by-zero (routine-call fixup misplacement)
Was `div 109 P-AADJ` at PARSER+0x1ce: a nested routine-call fixup (the `<LIT? ,HERE>`
call in the READ COND) was applied 2 bytes early, overwriting the call opcode with the
resolved LIT? address (also written correctly at the real position by the backup
scan). See the fixup-validation fix in Landed. minizork now reaches READ.

### 1c. FIXED: minizork garbled banner (global-initialized-to-string)
`<GLOBAL GUE-NAME "The Great Underground Empire">` left GUE-NAME=0 -> garbage. Fixed
(see Landed). Banner and room text now render correctly.

### 1d. RESOLVED by sessions 3-5 (kept for history): post-dispatch verb logic + a take/read crash
Session 2 landed 13 general codegen fixes (below) that took minizork from "commands
do nothing" all the way through parsing, verb+object binding, and verb dispatch --
"examine mailbox" now prints "The small mailbox is closed." The parser subsystem is
essentially working. Two remaining issues (both past the parser, in verb logic /
object handling, so likely smaller):
  (a) "open mailbox" -> "It is already open." V-OPEN's <FSET? ,PRSO ,OPENBIT>
      returns true while the container description (examine) treats the mailbox as
      closed -- an FSET?/flag-read inconsistency to isolate (test FSET? in the exact
      V-OPEN context vs examine).
  (b) "take leaflet" / "read leaflet" crash on a write to static memory at 0x213A.
      The leaflet is inside the closed mailbox, so this is object scoping / a bad
      store, not the core parser.

## Landed sessions 3-5 (2026-07-15..18) -- from verb dispatch to the 350/350 WIN
~25 more fixes on top of session 2, every one keeping the suite at 692 pass / 3
pre-existing fails and the L2 suite green. Highlights by session (the full
narrative lives in the zwalker session memory "zorkie-parser-frontier"):

**Session 3 -- movement works end to end.** (1) THE root-cause scanner-corruption
class: assembler.py's position-blind vocab/vword placeholder scanners misread
already-resolved routine-address bytes 0xFA-0xFC as placeholders and clobbered
them (LIT?'s packed 0x39FB -> every call to it redirected). Fix: routine fixups
record protected_positions and the blind scanners skip them. (2) generate_cond
4th pass re-adjusts recorded placeholder positions after branch-size growth.
(3) value_context for a routine's tail COND (a clause ending <SETG X V> must
return V -- MAIN-LOOP-1 gates on <SETG P-WON <PARSER>>). (4) V?<name> constants
bind to the verb's OWN routine, not the verb word's first syntax line. (5)
builtin-shadow check consults the complete pre-codegen routine-name set, so a
user GOTO/PERFORM defined later beats the builtin. (6) A room's (GLOBAL obj...)
property resolves atoms to object numbers as a BYTE array (local-globals scope).
(7) _resolve_string_placeholders_in_story scans the globals table word-aligned
(P-OTBL's legit 0x20FC low byte was eaten -> the P-VTBL static-memory crash).

**Session 4 -- plays the full 405-command route crash-free.** (1) Negative SETG
constants encode as 2-byte words (<SETG P-SLOCBITS -1> stored 255). (2) REPEAT
loop-back JUMP appended after RETURN/AGAIN placeholder patching so the scans
can't misread it. (3) A word that is both direction and adjective keeps the
direction in dict byte 5 (WEST). (4) Dict "first part of speech" flag made
deterministic (direction > verb > adjective), was set-iteration hash order.
(5) gen_random evaluates nested-form operands (RANDOM <- .L .CNT> consumed a
stale stack value -> wild PUT -> "ring bell" crash).

**Session 5 -- the win.** Driven by lockstep.py: run the official binary and the
zorkie build side by side, compare ROOM-NAME + SCORE each step; the first
divergence IS the next bug. (1) Two-slot dictionary values matching the official
dict; prepositions re-based into the 192..249 band (250-255 are scanner magic).
(2) VERB? had emitted INC_CHK per verb -- incremented PRSA! Rewrote as chunked JE;
PRSO?/PRSI?/ROOM? builtins; macro expander skips those DEFMACs. (3) <ITABLE NONE
n> size specifier (all parser match tables had overlapped -- the "sand ghost").
(4) Nested-form operand evaluation wired into ~40 2-/3-operand generators
(getp/getpt/loadw/storew/putp/jin/...; PUTP had written a stale 0 into STRENGTH
via I-CURE); gen_random/gen_prob rewritten; empty <> = constant 0 everywhere
including call args. (5) Classic exit encodings UEXIT/NEXIT/FEXIT/CEXIT/DEXIT
with a per-object property-data WALKER replacing every byte-blind object scan
(one had rewritten CELLAR's property pointer 0x15FA). (6) String-placeholder
namespaces separated (code 0xFC00-band vs data 0xF400-band, positions recorded
at encode time -- point-wise resolution, no byte scans). (7) SYNTAX multi-flag
groups merge onto the same object (take all); classic TELL prints bare forms via
PRINT_PADDR; PSEUDO objects. Route adaptation: RNG streams differ from the
official recording, so the walkthrough heals in sacred rooms (wait-loops) and
never lingers in the Troll Room.

## Landed session 2 (2026-07-15) -- THIRTEEN codegen correctness fixes
All in zilc/codegen/codegen_improved.py unless noted. Each keeps the full test suite
at 692 pass / 3 pre-existing fails and the green L2 suite at 3/3. These are general
correctness fixes (not minizork hacks) and benefit every game. Combined effect:
minizork went from "commands do nothing" to fully parsing a command, binding both the
verb and the object, and executing the verb routine (e.g. "examine mailbox" ->
"The small mailbox is closed.").
1. **Comparison value forms materialize to the stack** (gen_less/gen_greater/
   gen_grtr_or_equal/gen_less_or_equal via new _compare_materialize_tail): `<L?/G?/
   G=?/L=?>` used the "branch to RTRUE / fall to RFALSE" idiom, which RETURNS from the
   whole routine. Correct only in tail position; inside <AND>/<OR>/args it returned
   early. This was THE thing blocking SYNTAX-CHECK from matching (a `<G=? .NUM 1>`
   inside an AND returned false from SYNTAX-CHECK).
2. **Predicate value forms materialize to the stack** (gen_zero_test, gen_one,
   gen_true_predicate, gen_false_predicate, gen_btst): same routine-return idiom;
   e.g. `<ZERO? x>` inside `<NOT <ZERO? x>>` inside `<AND>` returned from the routine.
3. **G=?/L=? condition-context handlers evaluate nested-form operands**
   (generate_condition_test now uses _resolve_two_cmp_operands): `<G=? <GET t i> 2>`
   treated the GET as constant 0.
4. **gen_put index/value operand swap** (gen_put): `<PUT tbl <+ .N 1> <REST ...>>`
   pushed index then value but STOREW pops index first (top = value) -> swapped ->
   a wild store. Now spills all but the last stack operand to a scratch global.
5. **REPEAT-as-routine-tail returns its value** (generate_routine): a RepeatNode last
   statement fell through to RET 0, discarding the value that `<RETURN v>` pushed.
   The classic parser's CLAUSE is one big REPEAT ending in <RETURN -1>/<RETURN .PTR>,
   so it always returned 0 -> PARSER RFALSE.
6. **gen_and/gen_or loaded variable VALUES indirectly** (0xAE -> 0x9E): `load` with a
   variable operand is an INDIRECT load (var[value-of-var]); `<OR .BUT .TBL>` loaded
   var[0x20d4] (garbage) instead of TBL. Small-const operand (the var number) is the
   direct load.
7. **gen_routine_call evaluates nested-form arguments** (gen_routine_call): it assumed
   FormNode args were already on the stack but never evaluated them; `<GET-OBJECT
   <OR .BUT .TBL>>` passed garbage. Now evaluates each, spilling all but the last to
   scratch globals for correct pop order.
8. **PERFORM standard-library fallback** (compiler.py _maybe_inject_perform + a
   dispatch check): real games define PERFORM inside an MDL `%<COND ...>` our front
   end drops, and zorkie's builtin <PERFORM> was a stub that never dispatched the
   verb's ACTIONS routine. We now inject a real PERFORM (WINNER/room/PREACTION/
   object/ACTIONS chain) when the game calls PERFORM but defines none.
9. **VERBS table dialect branching** (_generate_verbs_table -> _classic/_zilf): classic
   MDL games (parser.zil with SYNTAX-CHECK) need the compact syntax table (byte0=line
   count, per-line P-SPREP1/P-SACTION/P-SFWIM1/P-SLOC1 records, VERBS indexed by
   verb-number). ZILF/toy games keep the byte-6 options layout indexed by action.
   Detected by the presence of a SYNTAX-CHECK routine.
10. **Dictionary verb-byte dialect** (compiler.py _dict_verb_num) + per-line action
    numbers (verb_action_num): classic stores the verb-number in dict byte 5; ZILF
    stores the action number. syntax_entries now carry both action_num (routine's,
    for P-SACTION) and verb_action_num (V?/ACT? constant, for ZILF indexing).
11. **Branch bytes must not collide with placeholder high-bytes** (generate_cond third
    pass): a 1-byte COND branch byte >= 0xFA is misread by the vocab/routine
    placeholder scanners (they scan for 0xFB.. etc.) and silently rewritten to a
    dictionary/routine address. A 0xFB branch (on-true, offset 59) in GET-OBJECT got
    clobbered to a word address, sending execution backwards into the "How about the
    ?" disambiguation with a corrupt PRSO. Force the 2-byte branch form (first byte
    always <= 0xBF) when the 1-byte byte would be >= 0xFA. (The vocab scanner in
    zmachine/assembler.py is position-blind -- this sidesteps it; a proper fix would
    track vocab-placeholder positions like routine placeholders.)
12. **Bodyless (T) clause yields true** (generate_cond): the trailing (T) in
    <COND (.LOSS ... <RFALSE>) (T)> pushed nothing, so as a routine value RET_POPPED
    returned garbage -- MANY-CHECK reported failure and the parser dropped every
    resolved object. Push 1 for a bodyless T/ELSE clause only (a bodyless *test*
    clause used as a statement must not leak a value).
13. **COND value with a local/global-var body** (generate_cond last-action): emitted
    0x24 (dec_chk small,var) instead of 0x34 (add small,var) for "ADD 0 var -> stack",
    so <COND (.PTBL .OBJ1) (T .OBJ)> returned garbage -- MAIN-LOOP-1 passed PRSO=-1 to
    PERFORM. This was the last thing between a bound object and a dispatched verb.

### 1e. OLDER NEXT (pre-session-2 notes, now superseded by 1d)
minizork and zork1 DISPATCH commands but the deeper layers still needed work. Also:
minizork's later commands returned empty and dfrotz reported a stack underflow -- likely the verbose
add[0,0]/add[0,1] predicate-materialize pattern pushes booleans that aren't always
consumed, leaking the stack. zork3 still crashes earlier on a write to static memory
at 0x2826 (a separate bad STORE/PUT). starcross's vocabulary lookup is a separate
issue.

### 2. Too big for the story-file size limit (abbreviation/packing gap) -- BIGGEST BUCKET
The 9 games above code-generate fully but exceed the version size limit because text
compression is under-implemented (abbreviation selection is greedy/first-match; no
better packing). Infra exists (zilc/zmachine/abbreviations.py, text_encoding.py;
header field 0x18; --string-dedup flag) but selection is suboptimal. Better
abbreviation selection is now the highest-leverage compile-unblock: it would let up
to 9 games fit (7 V3 + 2 V4). Fixing INPUT (below) is what moved amfv/trinity into
this bucket -- they now generate all code and are blocked only on size.

### 3. Macro / builtin gaps
- PRSO?/PRSI?/PRSA? not expanded as macros: blocks lurkinghorror (call gets >3 args
  in V3), spellbreaker and zork2 (reported as undefined routine PRSO?/PRSI?).
- Undefined routines block deadline (THIS-IT?), suspect (ERROR, QUITTER),
  witness (PRINC), sorcerer (ADJ-CHECK, MOBY-FIND), zork2 (PUTREST, RETURN!-).
- The toy cloak (ZILF stdlib) is past its old LIBRARY-MESSAGE 4-args-in-V3
  blocker; current stop is the stdlib's ISAVE (a V5+ opcode) reached in a V3
  build. The full compile-time MDL/DEFMAC evaluator is still the deeper gap.

### 4. Single-game blockers
	planetfall	parse error: unclosed property (planetfall.zil:13177)
	suspended	CLEAR requires V4 or later (uses a V4+ opcode in a V3 build)
	hollywoodhijinx	too many attributes (got 51, V3 max 32) -- attribute over-count
	cutthroats / infidel	run a top-level compile-time PRINC then exit 1 with no error message
	enchanter	entry-file resolution picks a stub subfile; real master is z4.zil

## Landed this session (2026-07-15) -- FIVE codegen/assembler fixes
Combined effect: minizork and zork1 went from crashing right after the first room to
BOOTING CLEANLY, running the main loop, reaching the READ prompt, and DISPATCHING
commands with real game responses. (Next layer: verb/object syntax matching -- see
bucket 1.)
- **gen_or short-circuit branch offset** (codegen_improved.py ~15053): hardcoded JZ
  branch offset 0xC3 (offset 3) should be 0xC5 (offset 5) to skip the 3-byte success
  JUMP; off-by-2 misaligned execution and crashed every game using `<OR value ...>`
  right after the first room. THIS was the shared object-description derail.
- **Routine-call fixup misplacement** (get_routine_fixups, codegen_improved.py ~2092):
  a tracked routine-call fixup for a NESTED call could point a couple of bytes early
  (at the call opcode instead of its address operand) while the backup scan also
  recorded the real position -- so the resolved address was written twice, corrupting
  the call opcode and derailing execution (minizork's div-by-zero in PARSER). Fix:
  only apply a routine fixup where the bytes actually hold the placeholder value.
- **Global initialized to a string constant** (codegen_improved.py ~661 +
  assembler.py ~1547): `<GLOBAL X "text">` left the global 0 (no StringNode case), so
  `<TELL ,X>` printed garbage from address 0. Now the global holds a 0xFC00 string
  placeholder that the assembler resolves to the packed string address (in the globals
  table too, not just code). Fixed minizork's garbled banner (GUE-NAME).
- **Signed-constant call operand** (gen_routine_call, codegen_improved.py ~16877):
  negative call arguments (e.g. the -1 tick in <QUEUE I-THIEF -1>) were encoded as a
  1-byte small constant (0xFF = 255) instead of a 2-byte large constant (0xFFFF).
  Missing lower bound on the small-const test (op_val <= 255 -> 0 <= op_val <= 255).
- **INPUT was mis-compiled as sread** (new gen_input_readchar; dispatch ~3232):
  in ZIL, <INPUT 1> reads ONE keystroke = read_char (VAR:0x16, a store instruction),
  not line-input sread. zorkie routed INPUT to sread with a 2-3-operand V4 bound, so
  the real single-operand form <INPUT 1> (used by amfv, trinity, zorkzero) could not
  compile. New generator emits read_char with the correct 1-3-operand V4+ bound and a
  store byte. Effect: amfv and trinity now code-generate fully (they moved into the
  too-big bucket). The 4 existing INPUT opcode tests still pass; READ/sread and the
  green suite are untouched (READ routes through gen_read, not gen_input).
- Both fixes verified: green L2 suite still 3/3; INPUT unit tests 4/4.

## Version support reality
V3 is the only version that compiles real Infocom games. The CLI advertises
choices=[1..8] (compiler.py:4741) but V4 is only partial (trinity blocked on V4
INPUT operands; amfv/moonmist on bare-atom globals) and V5-V8 are unverified.

## Oracle / reference
- The test oracle is zwalker (play-and-win), not byte-diff against a reference .z3.
- Official Zork I reference binary (Release 119, serial 880429, 86,838 bytes) lives
  at tests/test-games/zork1/COMPILED/zork1.z3 and is still a valid behavioral oracle.

## Prioritized next steps
1. **zork1 via the lockstep-differ method** (the method that won minizork): run the
   official Release-119 binary and the zorkie build side by side through
   ../zwalker/walkthroughs' verified route, compare room+score per step, fix the
   first divergence, repeat. zork3 next (same family).
2. Fix starcross vocabulary lookup (wire up VERBS/PREACTIONS dispatch) so commands
   stop returning "I beg your pardon?".
3. Implement PRSO?/PRSI? macro expansion (bucket 3).
4. Improve abbreviation selection / add packing so the 9 too-big games fit (bucket 2).
5. Pick off the single-game parse blockers (bucket 4).
6. Compile-time MDL/DEFMAC evaluator (LIBRARY-MESSAGE) to unblock the full ZILF
   library path (cloak).
