# Regression tests for advent-style compile-time room/object construction
# ========================================================================
#
# advent (the ZILF port of Adventure) builds its ~30 maze rooms with
# compile-time DEFINEs:
#
#     <DEFINE MAZE-ROOM (NAME "ARGS" CS "AUX" DEF PS)
#         <SET PS <MAPF ,LIST <FUNCTION (C ...) ... <LIST .DIR TO .DEST>> .CS>>
#         <SET DEF <FORM ROOM .NAME '(IN ROOMS) ... !.PS>>
#         <EVAL .DEF>>
#
# Making that work exposed five independent compiler gaps:
#
# 1. <EVAL <FORM ROOM ...>> / <EVAL <FORM OBJECT ...>> did nothing -- the
#    constructed definition was discarded and every maze room was an
#    undefined-object warning.
# 2. MAPF flattened a plain LIST result into the collection, so the spliced
#    !.PS exit groups arrived as loose atoms and the rooms lost their exits.
# 3. <UNPARSE n> was unsupported, so <PARSE <STRING "ALIKE-MAZE-"
#    <UNPARSE .DEST>>> built garbage room names.
# 4. [a b c] vector literals were indistinguishable from lists, so
#    <TYPE? x VECTOR> was always false and the ZILF scope engine's MAP-SCOPE
#    ignored its [BITS ...]/[STAGES ...]/[NO-LIGHT] options (generic objects
#    leaked into noun matching: "throw axe at dwarf" matched GENERIC-DWARF
#    too and asked "Which do you mean, the ... dwarf or the ... dwarf?").
# 5. Bare atoms in DEFMAC bodies were resolved through the environment, so
#    an option keyword shadowed by an AUX local (MAP-SCOPE's
#    <==? <1 .SV> STAGES> with AUX STAGES) compared against the local's
#    value instead of the atom.

from .conftest import AssertRoutine


MAZE_ROOM_DEFINE = """<DEFINE MAZE-ROOM (NAME "ARGS" CS "AUX" DEF PS)
    <SET PS
        <MAPF ,LIST
              <FUNCTION (C "AUX" (DIR <1 .C>) (DEST <2 .C>))
                  <COND (<TYPE? .DEST FIX>
                         <SET DEST <PARSE <STRING "CELL-" <UNPARSE .DEST>>>>)>
                  <LIST .DIR TO .DEST>>
              .CS>>
    <SET DEF
        <FORM ROOM .NAME
            '(DESC "Cell")
            '(IN ROOMS)
            '(ACTION CELL-F)
            !.PS>>
    <EVAL .DEF>>"""


class TestEvalFormRoom:
    """<EVAL <FORM ROOM ...>> from a compile-time DEFINE must emit the room."""

    def test_maze_room_define_emits_rooms_with_exits(self):
        """MAZE-ROOM-style DEFINE: rooms exist, numeric connections resolve
        via PARSE/STRING/UNPARSE, and the spliced !.PS exit groups become
        direction properties."""
        AssertRoutine('', '<RTRUE>') \
            .with_global('<DIRECTIONS NORTH SOUTH EAST WEST>') \
            .with_global('<OBJECT ROOMS>') \
            .with_global('<ROUTINE CELL-F (ARG) <RFALSE>>') \
            .with_global(MAZE_ROOM_DEFINE) \
            .with_global('<MAZE-ROOM CELL-1 (NORTH 2) (EAST CELL-2)>') \
            .with_global('<MAZE-ROOM CELL-2 (SOUTH 1)>') \
            .implies(
                # Both rooms materialized inside ROOMS
                '<IN? ,CELL-1 ,ROOMS>',
                '<IN? ,CELL-2 ,ROOMS>',
                # (NORTH 2) -> (NORTH TO CELL-2): numeric connection resolved
                '<==? <GETP ,CELL-1 ,P?NORTH> ,CELL-2>',
                # (EAST CELL-2): named connection kept
                '<==? <GETP ,CELL-1 ,P?EAST> ,CELL-2>',
                # (SOUTH 1) on the second room
                '<==? <GETP ,CELL-2 ,P?SOUTH> ,CELL-1>')

    def test_maze_room_desc_prints(self):
        AssertRoutine('', '<PRINTD ,CELL-1>') \
            .with_global('<DIRECTIONS NORTH SOUTH>') \
            .with_global('<OBJECT ROOMS>') \
            .with_global('<ROUTINE CELL-F (ARG) <RFALSE>>') \
            .with_global(MAZE_ROOM_DEFINE) \
            .with_global('<MAZE-ROOM CELL-1 (NORTH 1)>') \
            .outputs('Cell')

    def test_eval_form_object(self):
        """<EVAL <FORM OBJECT ...>> emits a real object."""
        AssertRoutine('', '<PRINTD ,GADGET>') \
            .with_global('<OBJECT BOX (DESC "box")>') \
            .with_global(
                '<DEFINE MAKE-GADGET (NAME) '
                '<EVAL <FORM OBJECT .NAME \'(DESC "gizmo") \'(IN BOX)>>>') \
            .with_global('<MAKE-GADGET GADGET>') \
            .outputs('gizmo')

    def test_eval_form_object_in_tree(self):
        AssertRoutine('', '<RTRUE>') \
            .with_global('<OBJECT BOX (DESC "box")>') \
            .with_global(
                '<DEFINE MAKE-GADGET (NAME) '
                '<EVAL <FORM OBJECT .NAME \'(DESC "gizmo") \'(IN BOX)>>>') \
            .with_global('<MAKE-GADGET GADGET>') \
            .implies('<IN? ,GADGET ,BOX>')


class TestMapfListCollection:
    """MAPF ,LIST must collect a plain LIST result as ONE element."""

    def test_mapf_list_results_stay_nested(self):
        """<MAPF ,LIST <FUNCTION (X) <LIST .X .X>> '(1 2)> is ((1 1) (2 2)):
        LENGTH 2, and each element is itself a 2-list."""
        AssertRoutine('', '<CHECK-NESTED>') \
            .with_global(
                '<DEFMAC CHECK-NESTED ("AUX" L) '
                '<SET L <MAPF ,LIST <FUNCTION (X) <LIST .X .X>> \'(1 2)>> '
                '<COND (<AND <==? <LENGTH .L> 2> <==? <LENGTH <1 .L>> 2>> '
                '       <FORM PRINTI "nested">) '
                '      (ELSE <FORM PRINTI "flat">)>>') \
            .outputs('nested')


class TestVectorType:
    """[a b c] literals are TYPE VECTOR, distinguishable from lists, and an
    option keyword compares as an ATOM even when an AUX local shadows it
    (the MAP-SCOPE [STAGES ...] / [BITS ...] dispatch pattern)."""

    CHOOSE_DEFMAC = (
        '<DEFMAC CHOOSE (\'V "AUX" STAGES OPTS SV) '
        '<SET STAGES \'(X Y Z)> '
        '<SET OPTS <REST .V>> '
        '<SET SV <1 .OPTS>> '
        '<COND (<AND <TYPE? .SV VECTOR> <==? <1 .SV> STAGES>> '
        '       <FORM PRINTI "stages-option">) '
        '      (ELSE <FORM PRINTI "default">)>>')

    def test_vector_option_dispatch_with_shadowing_aux(self):
        AssertRoutine('', '<CHOOSE (I [STAGES (A B)])>') \
            .with_global(self.CHOOSE_DEFMAC) \
            .outputs('stages-option')

    def test_no_option_takes_default(self):
        AssertRoutine('', '<CHOOSE (I)>') \
            .with_global(self.CHOOSE_DEFMAC) \
            .outputs('default')

    def test_plain_list_is_not_vector(self):
        AssertRoutine('', '<CHOOSE (I (STAGES A))>') \
            .with_global(self.CHOOSE_DEFMAC) \
            .outputs('default')


class TestSyntaxActionNameOverride:
    """= ROUTINE PREACTION NAME defines action NAME: the syntax line's PRSA
    value must be V?NAME (so <VERB? NAME> matches) and PREACTION attaches to
    that action number.  advent: <SYNTAX WATER OBJECT (FIND SPONGEBIT) =
    V-POUR-LIQUID PRE-WATER WATER> -- PLANT-F's <VERB? WATER> arm never fired
    and "water plant" fell through to V-POUR-LIQUID's YOU-MASHER default."""

    SRC = '''<VERSION ZIP>
<SYNTAX WATER OBJECT = V-POUR PRE-WATER WATER>
<SYNTAX OIL OBJECT = V-POUR PRE-OIL OIL>
<SYNTAX POUR OBJECT = V-POUR>
<ROUTINE V-POUR () <RTRUE>>
<ROUTINE PRE-WATER () <RTRUE>>
<ROUTINE PRE-OIL () <RTRUE>>
<ROUTINE GO () <QUIT>>'''

    def _compile(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from zilc.compiler import ZILCompiler
        c = ZILCompiler(version=3)
        c.compile_string(self.SRC, '<test>')
        return c._action_table

    def test_line_action_is_named_action(self):
        at = self._compile()
        vc = at['verb_constants']
        entries = {e['verb']: e for e in at['syntax_entries']}
        assert entries['WATER']['action_num'] == vc['V?WATER']
        assert entries['OIL']['action_num'] == vc['V?OIL']
        # WATER and OIL are DISTINCT actions sharing one routine
        assert vc['V?WATER'] != vc['V?OIL']
        # the plain POUR line uses the routine's own action
        assert entries['POUR']['action_num'] == vc['V?POUR']
        assert entries['POUR']['action_num'] != vc['V?WATER']

    def test_preaction_attaches_to_named_action(self):
        at = self._compile()
        vc = at['verb_constants']
        ntp = at['action_num_to_preaction']
        assert ntp.get(vc['V?WATER']) == 'PRE-WATER'
        assert ntp.get(vc['V?OIL']) == 'PRE-OIL'
        # every action number dispatches the shared routine
        ntr = at['action_num_to_routine']
        assert ntr.get(vc['V?WATER']) == 'V-POUR'
        assert ntr.get(vc['V?OIL']) == 'V-POUR'
