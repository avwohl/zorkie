# Regression tests for MULTI-GROUP EQUAL? chains in branch (COND-test) context.
#
# A JE instruction compares op1 against at most 3 comparands, so
# <EQUAL? x a b c d e f> compiles to a CHAIN of JEs. In branch context each
# non-final JE branches on TRUE past the rest of the chain into the clause
# body. That skip offset used to be PRECOMPUTED from an estimate that assumed
# every comparand encodes as ONE byte; large-constant comparands (dictionary
# words, numbers > 255) encode as TWO, so the branch landed inside the next
# JE's operand bytes and executed garbage.
#
# This is exactly the ZILF standard library's PARSE-NOUN-PHRASE test
#   <EQUAL? .W ,W?ALL ,W?EVERY ,W?EVERYTHING ,W?BOTH ,W?ANY ,W?ONE>
# (dictionary-word comparands, split 3+3): with W = W?ALL the first JE matched
# and jumped mid-instruction, PARSE-NOUN-PHRASE silently returned 0, and
# "take all" / "drop all" became a silent parser no-op in every
# ZILF-standard-library game. The fix emits placeholder branches and
# backpatches them from the chain's ACTUAL encoded size.

from .conftest import AssertRoutine

# Six large comparands (dictionary-word-sized), split into JE groups of 3+3.
SIX_LARGE = "<COND (<EQUAL? .X 900 901 902 903 904 905> 1) (T 0)>"

# Seven comparands -> groups of 3+3+1; two internal skip branches, and the
# final group is a 2-operand JE (a shape the old estimator also mis-sized).
SEVEN_MIXED = "<COND (<EQUAL? .X 900 901 902 5 904 905 906> 1) (T 0)>"


class TestJEChainBranchOffsets:
    def test_match_in_first_group_large(self):
        # The take-all shape: match in group 1 takes the internal skip branch,
        # which must land exactly on the clause body.
        AssertRoutine('"AUX" (X 900)', SIX_LARGE).gives_number("1")
        AssertRoutine('"AUX" (X 902)', SIX_LARGE).gives_number("1")

    def test_match_in_second_group_large(self):
        AssertRoutine('"AUX" (X 903)', SIX_LARGE).gives_number("1")
        AssertRoutine('"AUX" (X 905)', SIX_LARGE).gives_number("1")

    def test_no_match_large(self):
        AssertRoutine('"AUX" (X 700)', SIX_LARGE).gives_number("0")

    def test_three_groups_with_mixed_sizes(self):
        AssertRoutine('"AUX" (X 900)', SEVEN_MIXED).gives_number("1")
        AssertRoutine('"AUX" (X 5)', SEVEN_MIXED).gives_number("1")
        AssertRoutine('"AUX" (X 906)', SEVEN_MIXED).gives_number("1")
        AssertRoutine('"AUX" (X 700)', SEVEN_MIXED).gives_number("0")

    def test_parse_noun_phrase_shape(self):
        # Miniature of PARSE-NOUN-PHRASE: the chain test guards a mode-setting
        # branch inside a REPEAT, and the routine's value is computed AFTER the
        # loop. Under the bug the mid-instruction jump desynced execution and
        # the routine returned 0.
        AssertRoutine(
            '"AUX" (W 902) (MODE 0)',
            """<REPEAT ()
                   <COND (<EQUAL? .W 900 901 902 903 904 905>
                          <SET MODE 1>
                          <RETURN>)
                         (T <RETURN>)>>
               <COND (<1? .MODE> <RTRUE>) (T <RFALSE>)>""").gives_number("1")


class TestJEChainBranchOnTrue:
    # <NOT <EQUAL? ...>> inverts the branch sense: the chain must branch on
    # TRUE to a shared target. The old code emitted 1-byte offset-0
    # placeholders ("branch never taken... actually RFALSE") for the internal
    # groups, so a match in group 1 returned from the whole routine.
    NOT_SIX = "<COND (<NOT <EQUAL? .X 900 901 902 903 904 905>> 1) (T 0)>"

    def test_not_equal_no_match_takes_clause(self):
        AssertRoutine('"AUX" (X 700)', self.NOT_SIX).gives_number("1")

    def test_not_equal_match_first_group_skips_clause(self):
        AssertRoutine('"AUX" (X 900)', self.NOT_SIX).gives_number("0")
        AssertRoutine('"AUX" (X 902)', self.NOT_SIX).gives_number("0")

    def test_not_equal_match_second_group_skips_clause(self):
        AssertRoutine('"AUX" (X 905)', self.NOT_SIX).gives_number("0")
