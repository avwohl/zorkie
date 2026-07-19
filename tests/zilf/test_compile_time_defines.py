# Regression tests for the three suspect miscompilation fixes
# ============================================================
#
# Suspect (Infocom, 1984) exposed three independent compiler gaps:
#
# 1. MDL NTH/REST treated a FORM as an opaque node instead of a
#    primtype-LIST value, so the mystery-trilogy TELL DEFMAC's
#    `<==? <NTH .E 1> QUOTE>` never matched and every 'OBJ token
#    printed stack garbage instead of the object's short name.
#
# 2. %<NAME ...> calls of user compile-time selector DEFINEs
#    (suspect's DEBUG-CODE) were stripped to 0 placeholders, wiping
#    out the release-arm <APPLY ...> dispatch in PERFORM/CLOCKER --
#    every command silently did nothing.
#
# 3. gen_call (the APPLY/CALL builtin) crashed on COND operands
#    (nonexistent self._generate_node) and popped multiple
#    stack-evaluated operands in the wrong order (GOAL-REACHED's
#    <APPLY <GET .GT ,GOAL-FUNCTION> <COND ...>>).

from .conftest import AssertRoutine


MYSTERY_TELL_DEFMAC = """<DEFMAC TELL ("ARGS" A)
    <FORM PROG ()
        !<MAPF ,LIST
            <FUNCTION ("AUX" E)
                <COND (<EMPTY? .A> <MAPSTOP>)
                      (<SET E <NTH .A 1>> <SET A <REST .A>>)>
                <COND (<TYPE? .E STRING> <MAPRET <FORM PRINTI .E>>)
                      (<AND <TYPE? .E FORM>
                            <==? <NTH .E 1> QUOTE>>
                       <MAPRET <FORM PRINTD <FORM GVAL <NTH .E 2>>>>)
                      (ELSE <MAPRET <FORM PRINT .E>>)>>>>>"""


class TestFormAsMdlList:
    """NTH/REST on a FORM must see [operator, operand...] (MDL primtype LIST)."""

    def test_tell_defmac_quoted_atom_prints_object_desc(self):
        """The mystery-trilogy TELL macro turns 'OBJ into <PRINTD ,OBJ>."""
        AssertRoutine('', '<TELL "I see " \'HAT " here.">') \
            .with_global('<OBJECT HAT (DESC "fancy hat")>') \
            .with_global(MYSTERY_TELL_DEFMAC) \
            .outputs('I see fancy hat here.')


class TestCompileTimeSelectorDefine:
    """%<NAME ...> calls of all-quoted-parameter DEFINEs must be evaluated."""

    DEBUG_CODE = ("<DEFINE DEBUG-CODE ('X \"OPTIONAL\" ('Y T))"
                  " <COND (,DEBUGGING? .X)(ELSE .Y)>>")

    def test_selector_define_picks_release_arm(self):
        AssertRoutine('', '%<DEBUG-CODE <PRINTI "debug"> <PRINTI "release">>') \
            .with_global('<SETG DEBUGGING? <>>') \
            .with_global(self.DEBUG_CODE) \
            .outputs('release')

    def test_selector_define_picks_debug_arm(self):
        AssertRoutine('', '%<DEBUG-CODE <PRINTI "debug"> <PRINTI "release">>') \
            .with_global('<SETG DEBUGGING? T>') \
            .with_global(self.DEBUG_CODE) \
            .outputs('debug')


class TestApplyComputedOperands:
    """APPLY with multiple stack-evaluated operands (routine from a table +
    a COND-valued argument) must call the right routine with the right arg."""

    def test_apply_get_routine_with_cond_argument(self):
        AssertRoutine('"AUX" X',
                      '<SET X <APPLY <GET ,RTNS 0> <COND (T 21)>>>'
                      ' <PRINTN .X>') \
            .with_global('<ROUTINE DOUBLER (N) <* .N 2>>') \
            .with_global('<GLOBAL RTNS <TABLE DOUBLER>>') \
            .outputs('42')
