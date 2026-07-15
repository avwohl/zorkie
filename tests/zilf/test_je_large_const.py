# Regression tests for JE (EQUAL?) with large-constant comparands.
#
# A multi-operand <EQUAL? x a b ...> compiles to a VAR-form JE. The type byte
# and operands must encode each constant as large (2 bytes) when it exceeds 255,
# else it is truncated to its low byte. Dictionary word addresses (W?FOO) are
# routinely > 255, so before this fix `<EQUAL? PARSED-WORD ,W?TAKE ,W?GET>` never
# matched -- e.g. W?UNLOCK = 902 (0x386) was emitted as 0x86 = 134.

from .conftest import AssertRoutine


class TestJELargeConstants:
    def test_branch_context_match_first(self):
        # In a COND predicate (branch-context JE): X == first large comparand.
        AssertRoutine('"AUX" (X 902)',
                      "<COND (<EQUAL? .X 902 895> 1) (T 0)>").gives_number("1")

    def test_branch_context_match_second(self):
        AssertRoutine('"AUX" (X 895)',
                      "<COND (<EQUAL? .X 902 895> 1) (T 0)>").gives_number("1")

    def test_branch_context_no_match(self):
        AssertRoutine('"AUX" (X 700)',
                      "<COND (<EQUAL? .X 902 895> 1) (T 0)>").gives_number("0")

    def test_value_context_large(self):
        # Value-context JE (gen_equal) must also encode large constants.
        AssertRoutine('"AUX" (X 902)',
                      "<EQUAL? .X 902 895>").gives_number("1")

    def test_mixed_small_and_large(self):
        # Small (5) and large (902) comparands in the same JE.
        AssertRoutine('"AUX" (X 902)',
                      "<COND (<EQUAL? .X 5 902> 1) (T 0)>").gives_number("1")
        AssertRoutine('"AUX" (X 5)',
                      "<COND (<EQUAL? .X 5 902> 1) (T 0)>").gives_number("1")
