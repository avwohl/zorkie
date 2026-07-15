# Regression tests: ordered comparisons (G? / L?) must EVALUATE a nested-form
# operand, not treat it as constant 0.
#
# The classic ZIL loop-counter idiom <G? <SET C <+ .C 1>> N> put a form (the SET)
# as the first operand of G?. The branch-context G?/L? codegen called
# _get_operand_type_and_value directly, which returns (0, 0) for a form -- so the
# comparison used 0, the SET/increment was never emitted, and the loop spun
# forever (seen as zork1 hanging in V-VERSION's serial-number loop).

from .conftest import AssertRoutine


class TestComparisonNestedOperand:
    def test_g_with_set_increment_terminates(self):
        AssertRoutine(
            '"AUX" (C 0)',
            "<REPEAT () <COND (<G? <SET C <+ .C 1>> 3> <RETURN>)>> .C",
        ).gives_number("4")

    def test_l_with_set_decrement_terminates(self):
        AssertRoutine(
            '"AUX" (C 5)',
            "<REPEAT () <COND (<L? <SET C <- .C 1>> 1> <RETURN>)>> .C",
        ).gives_number("0")

    def test_g_nested_form_first_operand(self):
        # <G? <+ .A .B> 10> : first operand is an arithmetic form.
        AssertRoutine('"AUX" (A 7) (B 8)',
                      "<COND (<G? <+ .A .B> 10> 1) (T 0)>").gives_number("1")
