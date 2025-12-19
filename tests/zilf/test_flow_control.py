# ZILF Flow Control Tests for Zorkie
# ===================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/FlowControlTests.cs
# Copyright 2010-2023 Tara McGrew
# Adapted for zorkie by automated translation
#
# This file is part of zorkie.
#
# zorkie is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Tests for ZIL flow control constructs.

These tests verify that the zorkie compiler correctly handles:
- RETURN with and without activation
- AGAIN (loop restart)
- DO loops
- MAP-CONTENTS and MAP-DIRECTIONS
- COND conditionals
- BIND/PROG blocks
- VERSION? conditionals
- Routine argument constraints
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals, AssertEntryPoint


class TestReturn:
    """Tests for RETURN opcode behavior."""

    def test_return_without_activation_should_return_from_block(self):
        """Test that RETURN without activation returns from block."""
        AssertRoutine("", "<FOO>") \
            .with_global('<ROUTINE FOO FOO-ACT ("AUX" X) <SET X <REPEAT () <RETURN 123>>> 456>') \
            .gives_number("456")

    def test_return_with_activation_should_return_from_routine(self):
        """Test that RETURN with activation returns from routine."""
        AssertRoutine("", "<FOO>") \
            .with_global('<ROUTINE FOO FOO-ACT ("AUX" X) <SET X <REPEAT () <RETURN 123 .FOO-ACT>>> 456>') \
            .gives_number("123")

    def test_return_with_activation_can_return_from_outer_block(self):
        """Test that RETURN with activation can exit outer block."""
        AssertRoutine(
            '"AUX" X',
            "<SET X <PROG OUTER () <PROG () <RETURN 123 .OUTER> 456> 789>> <PRINTN .X>"
        ).outputs("123")

    def test_return_inside_bind_should_return_from_outer_block(self):
        """Test that RETURN inside BIND returns from outer block."""
        AssertRoutine("", "<PROG () <+ 3 <PROG () <BIND () <RETURN 120>> 456>>>") \
            .gives_number("123")

    def test_return_with_activation_in_void_context_should_not_warn(self):
        """Test warning behavior for RETURN in void context."""
        # activation + simple value => no warning
        AssertRoutine("", "<PROG FOO () <RETURN <> .FOO> <QUIT>> 123") \
            .without_warnings() \
            .gives_number("123")

        # no activation + simple value => warning
        AssertRoutine("", "<PROG () <RETURN <>> <QUIT>> 123") \
            .with_warnings() \
            .gives_number("123")

        # activation + other value => warning
        AssertRoutine("", "<PROG FOO () <RETURN 9 .FOO> <QUIT>> 123") \
            .with_warnings() \
            .gives_number("123")

    def test_return_with_do_funny_return_true_or_high_version_exits_routine(self):
        """Test RETURN with DO-FUNNY-RETURN? or high version."""
        AssertRoutine('"AUX" X', "<SET X <PROG () <RETURN 123>>> <* .X 2>") \
            .with_global("<SETG DO-FUNNY-RETURN? T>") \
            .in_v3() \
            .gives_number("123")

        AssertRoutine('"AUX" X', "<SET X <PROG () <RETURN 123>>> <* .X 2>") \
            .in_v5() \
            .gives_number("123")

    def test_return_with_do_funny_return_false_or_low_version_exits_block(self):
        """Test RETURN with DO-FUNNY-RETURN? false or low version."""
        AssertRoutine('"AUX" X', "<SET X <PROG () <RETURN 123>>> <* .X 2>") \
            .with_global("<SETG DO-FUNNY-RETURN? <>>") \
            .in_v5() \
            .gives_number("246")

        AssertRoutine('"AUX" X', "<SET X <PROG () <RETURN 123>>> <* .X 2>") \
            .in_v3() \
            .gives_number("246")


class TestAgain:
    """Tests for AGAIN opcode behavior."""

    def test_again_should_reset_local_variable_defaults(self):
        """Test that AGAIN resets local variable defaults."""
        AssertRoutine(
            '"AUX" (FOO 1)',
            "<COND (,GLOB <RETURN .FOO>) (T <INC GLOB> <SET FOO 99> <AGAIN>)>"
        ).with_global("<GLOBAL GLOB 0>") \
            .in_v5() \
            .gives_number("1")

    def test_again_with_activation_should_repeat_routine(self):
        """Test that AGAIN with activation repeats routine."""
        AssertRoutine("", "<FOO>") \
            .with_global("<GLOBAL BAR 0>") \
            .with_global(
                '<ROUTINE FOO FOO-ACT () <PRINTI "Top"> <PROG () <PRINTN ,BAR> <COND (,BAR <RTRUE>)> <INC BAR> <AGAIN .FOO-ACT>>>'
            ) \
            .outputs("Top0Top1")

    def test_again_without_activation_should_repeat_block(self):
        """Test that AGAIN without activation repeats block."""
        AssertRoutine("", "<FOO>") \
            .with_global("<GLOBAL BAR 0>") \
            .with_global(
                '<ROUTINE FOO FOO-ACT () <PRINTI "Top"> <PROG () <PRINTN ,BAR> <COND (,BAR <RTRUE>)> <INC BAR> <AGAIN>>>'
            ) \
            .outputs("Top01")


class TestDO:
    """Tests for DO loop construct."""

    def test_do_up_fixes(self):
        """Test DO loop counting up with fixed bounds."""
        AssertRoutine("", "<DO (I 1 5) <PRINTN .I> <CRLF>>") \
            .outputs("1\n2\n3\n4\n5\n")

    def test_do_down_fixes(self):
        """Test DO loop counting down with fixed bounds."""
        AssertRoutine("", "<DO (I 5 1) <PRINTN .I> <CRLF>>") \
            .outputs("5\n4\n3\n2\n1\n")

    def test_do_up_fixes_by2(self):
        """Test DO loop counting up by 2."""
        AssertRoutine("", "<DO (I 1 5 2) <PRINTN .I> <CRLF>>") \
            .outputs("1\n3\n5\n")

    def test_do_down_fixes_by2(self):
        """Test DO loop counting down by 2."""
        AssertRoutine("", "<DO (I 5 1 -2) <PRINTN .I> <CRLF>>") \
            .outputs("5\n3\n1\n")

    def test_do_up_fixes_byn(self):
        """Test DO loop counting up with variable step."""
        AssertRoutine('"AUX" (N 2)', "<DO (I 1 5 .N) <PRINTN .I> <CRLF>>") \
            .outputs("1\n3\n5\n")

    def test_do_up_fixes_calculate_inc(self):
        """Test DO loop with calculated increment."""
        AssertRoutine("", "<DO (I 1 16 <* 2 .I>) <PRINTN .I> <CRLF>>") \
            .outputs("1\n2\n4\n8\n16\n")

    def test_do_up_forms(self):
        """Test DO loop with form bounds."""
        AssertRoutine("", "<DO (I <FOO> <BAR .I>) <PRINTN .I> <CRLF>>") \
            .with_global('<ROUTINE FOO () <PRINTI "FOO"> <CRLF> 7>') \
            .with_global('<ROUTINE BAR (I) <PRINTI "BAR"> <CRLF> <G? .I 9>>') \
            .outputs("FOO\nBAR\n7\nBAR\n8\nBAR\n9\nBAR\n")

    def test_do_result(self):
        """Test DO loop result value."""
        AssertRoutine("", "<DO (I 1 10) <>>") \
            .gives_number("1")

    def test_do_result_return(self):
        """Test DO loop with RETURN."""
        AssertRoutine("", "<DO (I 1 10) <COND (<==? .I 5> <RETURN <* .I 3>>)>>") \
            .gives_number("15")

        AssertRoutine(
            '"AUX" X',
            "<SET X <DO (I 1 10) <COND (<==? .I 5> <RETURN <* .I 3>>)>>> <* .X 10>"
        ).gives_number("150")

    def test_do_end_clause(self):
        """Test DO loop with end clause."""
        AssertRoutine(
            "",
            '''<DO (I 1 4) (<TELL "rock!">)
                           <TELL N .I>
                           <COND (<G=? .I 3> <TELL " o'clock">)>
                           <TELL ", ">>'''
        ).outputs("1, 2, 3 o'clock, 4 o'clock, rock!")

    def test_do_end_clause_misplaced(self):
        """Test that misplaced end clause is rejected."""
        AssertRoutine(
            "",
            '''<DO (CNT 0 25 5)
                           <TELL N .CNT CR>
                           (END <TELL "This message is never printed">)>'''
        ).does_not_compile()

    def test_unused_do_variables_should_not_warn(self):
        """Test that unused DO variables don't generate warnings."""
        AssertRoutine("", '<DO (I 1 10) <TELL "spam">>') \
            .without_warnings() \
            .compiles()


class TestMapContents:
    """Tests for MAP-CONTENTS construct."""

    def test_map_contents_basic(self):
        """Test basic MAP-CONTENTS iteration."""
        AssertRoutine("", "<MAP-CONTENTS (F ,TABLE) <PRINTD .F> <CRLF>>") \
            .with_global('<OBJECT TABLE (DESC "table")>') \
            .with_global('<OBJECT APPLE (IN TABLE) (DESC "apple")>') \
            .with_global('<OBJECT CHERRY (IN TABLE) (DESC "cherry")>') \
            .with_global('<OBJECT BANANA (IN TABLE) (DESC "banana")>') \
            .outputs("apple\nbanana\ncherry\n")

    def test_map_contents_with_next(self):
        """Test MAP-CONTENTS with NEXT variable."""
        AssertRoutine(
            "",
            '<MAP-CONTENTS (F N ,TABLE) <REMOVE .F> <PRINTD .F> <PRINTI ", "> <PRINTD? .N> <CRLF>>'
        ).with_global('<ROUTINE PRINTD? (OBJ) <COND (.OBJ <PRINTD .OBJ>) (ELSE <PRINTI "nothing">)>>') \
            .with_global('<OBJECT TABLE (DESC "table")>') \
            .with_global('<OBJECT APPLE (IN TABLE) (DESC "apple")>') \
            .with_global('<OBJECT CHERRY (IN TABLE) (DESC "cherry")>') \
            .with_global('<OBJECT BANANA (IN TABLE) (DESC "banana")>') \
            .outputs("apple, banana\nbanana, cherry\ncherry, nothing\n")

    def test_map_contents_with_end(self):
        """Test MAP-CONTENTS with end clause."""
        AssertRoutine(
            '"AUX" (SUM 0)',
            "<MAP-CONTENTS (F ,TABLE) (END <RETURN .SUM>) <SET SUM <+ .SUM <GETP .F ,P?PRICE>>>>"
        ).with_global('<OBJECT TABLE (DESC "table")>') \
            .with_global("<OBJECT APPLE (IN TABLE) (PRICE 1)>") \
            .with_global("<OBJECT CHERRY (IN TABLE) (PRICE 2)>") \
            .with_global("<OBJECT BANANA (IN TABLE) (PRICE 3)>") \
            .gives_number("6")

    def test_map_contents_with_end_empty(self):
        """Test MAP-CONTENTS with end clause on empty container."""
        AssertRoutine(
            '"AUX" (SUM 0)',
            "<MAP-CONTENTS (F ,TABLE) (END <RETURN 42>) <RFALSE>>"
        ).with_global('<OBJECT TABLE (DESC "table")>') \
            .gives_number("42")

    def test_map_contents_with_next_and_end(self):
        """Test MAP-CONTENTS with both NEXT and end clause."""
        AssertRoutine(
            '"AUX" (SUM 0)',
            "<MAP-CONTENTS (F N ,TABLE) (END <RETURN .SUM>) <REMOVE .F> <SET SUM <+ .SUM <GETP .F ,P?PRICE>>>>"
        ).with_global('<OBJECT TABLE (DESC "table")>') \
            .with_global("<OBJECT APPLE (IN TABLE) (PRICE 1)>") \
            .with_global("<OBJECT CHERRY (IN TABLE) (PRICE 2)>") \
            .with_global("<OBJECT BANANA (IN TABLE) (PRICE 3)>") \
            .gives_number("6")

    def test_unused_map_contents_variables_should_not_warn(self):
        """Test that unused MAP-CONTENTS variables don't warn."""
        AssertRoutine('"AUX" CNT', "<MAP-CONTENTS (I ,STARTROOM) <SET CNT <+ .CNT 1>>>") \
            .with_global("<ROOM STARTROOM>") \
            .with_global("<OBJECT CHIMP (IN STARTROOM)>") \
            .with_global("<OBJECT CHAMP (IN STARTROOM)>") \
            .with_global("<OBJECT CHUMP (IN STARTROOM)>") \
            .without_warnings() \
            .compiles()

        AssertRoutine("", "<MAP-CONTENTS (I N ,STARTROOM) <REMOVE .I>>") \
            .with_global("<ROOM STARTROOM>") \
            .with_global("<OBJECT CHIMP (IN STARTROOM)>") \
            .with_global("<OBJECT CHAMP (IN STARTROOM)>") \
            .with_global("<OBJECT CHUMP (IN STARTROOM)>") \
            .without_warnings() \
            .compiles()


class TestMapDirections:
    """Tests for MAP-DIRECTIONS construct."""

    def test_map_directions(self):
        """Test basic MAP-DIRECTIONS iteration."""
        AssertRoutine(
            "",
            '<MAP-DIRECTIONS (D P ,CENTER) <TELL N .D " " D <GETB .P ,REXIT> CR>>'
        ).with_global("<DIRECTIONS NORTH SOUTH EAST WEST>") \
            .with_global('<OBJECT CENTER (NORTH TO N-ROOM) (WEST TO W-ROOM)>') \
            .with_global('<OBJECT N-ROOM (DESC "north room")>') \
            .with_global('<OBJECT W-ROOM (DESC "west room")>') \
            .in_v3() \
            .outputs("31 north room\n28 west room\n")

    def test_map_directions_with_end(self):
        """Test MAP-DIRECTIONS with end clause."""
        AssertRoutine(
            "",
            '<MAP-DIRECTIONS (D P ,CENTER) (END <TELL "done" CR>) <TELL N .D " " D <GETB .P ,REXIT> CR>>'
        ).with_global("<DIRECTIONS NORTH SOUTH EAST WEST>") \
            .with_global('<OBJECT CENTER (NORTH TO N-ROOM) (WEST TO W-ROOM)>') \
            .with_global('<OBJECT N-ROOM (DESC "north room")>') \
            .with_global('<OBJECT W-ROOM (DESC "west room")>') \
            .in_v3() \
            .outputs("31 north room\n28 west room\ndone\n")


class TestCond:
    """Tests for COND conditional construct."""

    def test_cond_with_parts_after_t_should_warn(self):
        """Test that COND warns about clauses after T."""
        AssertRoutine(
            "",
            '<COND (<=? 0 1> <TELL "nope">) (T <TELL "ok">) (<=? 0 0> <TELL "too late">)>'
        ).with_warnings() \
            .compiles()

    def test_cond_with_false_condition_from_macro_should_not_warn(self):
        """Test that COND doesn't warn for macro-generated false conditions."""
        AssertRoutine(
            "",
            '<COND (<DO-IT?> <TELL "do it">) (,DO-OTHER? <TELL "do other">)>'
        ).with_global("<DEFMAC DO-IT? () <>>") \
            .with_global("<CONSTANT DO-OTHER? <>>") \
            .without_warnings() \
            .compiles()

        # ... but should still warn if the condition was a literal
        AssertRoutine("", '<COND (<> <TELL "done">)>') \
            .with_warnings() \
            .compiles()

    def test_and_in_void_context_with_macro_at_end_should_work(self):
        """Test AND in void context with macro at end."""
        AssertRoutine("", "<AND <FOO> <BAR>> <RETURN>") \
            .with_global("<ROUTINE FOO () T>") \
            .with_global("<DEFMAC BAR () '<PRINTN 42>>") \
            .outputs("42")

    def test_cond_should_allow_macro_clauses(self):
        """Test that COND allows macro-generated clauses."""
        AssertRoutine(
            "",
            '<COND <LIVE-CONDITION> <DEAD-CONDITION> <IF-IN-ZILCH (<=? 2 2> <TELL "2">)> <IFN-IN-ZILCH (<=? 3 3> <TELL "3">)> (T <TELL "end">)>'
        ).with_global("<DEFMAC LIVE-CONDITION () '(<=? 0 1> <TELL \"nope\">)>") \
            .with_global("<DEFMAC DEAD-CONDITION () '<>>") \
            .without_warnings() \
            .outputs("2")

    def test_cond_should_reject_non_macro_forms(self):
        """Test that COND rejects non-macro forms as clauses."""
        AssertRoutine(
            '"AUX" FOO',
            "<COND <SET FOO 123> (<=? .FOO 123> <PRINTN 456>)>"
        ).does_not_compile("ZIL0100")

    def test_constants_in_cond_clause_should_only_be_stored_if_at_end(self):
        """Test constant storage in COND clause."""
        AssertRoutine(
            '"AUX" (A 0)',
            "<SET A <COND (T 123 <PRINTN .A> 456)>>"
        ).outputs("0")


class TestBindProg:
    """Tests for BIND and PROG constructs."""

    def test_bind_deferred_return_pattern_in_void_context_no_variable(self):
        """Test BIND deferred return pattern in void context."""
        AssertRoutine(
            "",
            "<BIND (RESULT) <SET RESULT <FOO>> <PRINTN 1> .RESULT> <CRLF>"
        ).with_global("<ROUTINE FOO () 123>") \
            .generates_code_not_matching(r"RESULT")

    def test_prog_result_should_not_be_forced_onto_stack(self):
        """Test that PROG result isn't forced onto stack."""
        AssertRoutine('"AUX" X', "<SET X <PROG () <COND (.X 1) (ELSE 2)>>>") \
            .generates_code_matching("SET 'X,1")

        AssertRoutine('"AUX" X', "<SET X <PROG () <RETURN <COND (.X 1) (ELSE 2)>>>>") \
            .generates_code_matching("SET 'X,1")

        AssertRoutine('"AUX" X', "<COND (<PROG () .X> T)>") \
            .generates_code_not_matching(r"PUSH")

    def test_repeat_last_expression_should_not_clutter_stack(self):
        """Test that REPEAT last expression doesn't clutter stack."""
        AssertRoutine("", "<REPEAT () 123>") \
            .generates_code_not_matching(r"PUSH")

    def test_unused_prog_variables_should_warn(self):
        """Test that unused PROG variables generate warnings."""
        AssertRoutine("", '<PROG (X) <TELL "hi">>') \
            .with_warnings("ZIL0210") \
            .compiles()

        AssertRoutine("", '<BIND (X) <TELL "hi">>') \
            .with_warnings("ZIL0210") \
            .compiles()

        AssertRoutine("", '<REPEAT (X) <TELL "hi">>') \
            .with_warnings("ZIL0210") \
            .compiles()


class TestVersionP:
    """Tests for VERSION? conditional."""

    def test_version_p_with_parts_after_t_should_warn(self):
        """Test that VERSION? warns about clauses after T."""
        AssertRoutine(
            "",
            '<VERSION? (ZIP <TELL "classic">) (T <TELL "extended">) (XZIP <TELL "too late">)>'
        ).in_v5() \
            .with_warnings() \
            .compiles()


class TestRoutines:
    """Tests for routine definition constraints."""

    def test_routine_with_too_many_required_arguments_should_not_compile(self):
        """Test that too many required arguments is rejected."""
        AssertGlobals("<ROUTINE FOO (A B C D) <>>") \
            .in_v3() \
            .does_not_compile()

        AssertGlobals("<ROUTINE FOO (A B C D) <>>") \
            .in_v5() \
            .compiles()

        AssertGlobals("<ROUTINE FOO (A B C D E F G H) <>>") \
            .in_v5() \
            .does_not_compile()

    def test_routine_with_too_many_optional_arguments_should_warn(self):
        """Test that too many optional arguments generates warning."""
        AssertRoutine('"OPT" A B C D', "<>") \
            .in_v3() \
            .with_warnings("MDL0417") \
            .compiles()

        AssertRoutine('"OPT" A B C D', "<>") \
            .in_v5() \
            .without_warnings("MDL0417") \
            .compiles()

        AssertRoutine('"OPT" A B C D E F G H', "<>") \
            .in_v5() \
            .with_warnings("MDL0417") \
            .compiles()

    def test_call_with_too_many_arguments_should_not_compile(self):
        """Test that call with too many arguments is rejected."""
        AssertRoutine("", "<FOO 1 2 3>") \
            .with_global("<ROUTINE FOO () <>>") \
            .does_not_compile()

        AssertRoutine("", "<FOO 1 2 3>") \
            .with_global("<ROUTINE FOO (X) <>>") \
            .does_not_compile()

        AssertRoutine("", "<FOO 1 2 3>") \
            .with_global("<ROUTINE FOO (X Y Z) <>>") \
            .compiles()

    def test_apply_with_too_many_arguments_should_not_compile(self):
        """Test that APPLY with too many arguments is rejected."""
        AssertRoutine("", "<APPLY <> 1 2 3 4>") \
            .in_v3() \
            .does_not_compile()

        AssertRoutine("", "<APPLY <> 1 2 3 4>") \
            .in_v5() \
            .compiles()

        AssertRoutine("", "<APPLY <> 1 2 3 4 5 6 7 8>") \
            .in_v5() \
            .does_not_compile()

    def test_constant_false_can_be_called_like_routine(self):
        """Test that CONSTANT FALSE can be called like a routine."""
        AssertRoutine("", "<FOO 1 2 3 <INC G>> ,G") \
            .with_global("<GLOBAL G 100>") \
            .with_global("<CONSTANT FOO <>>") \
            .gives_number("101")


class TestGORoutine:
    """Tests for GO routine (entry point) constraints."""

    def test_go_routine_with_locals_should_give_error(self):
        """Test that GO routine with locals is rejected."""
        AssertEntryPoint("X Y Z", '<TELL "hi" CR>') \
            .does_not_compile()

        AssertEntryPoint('"OPT" X Y Z', '<TELL "hi" CR>') \
            .does_not_compile()

        AssertEntryPoint('"AUX" X Y Z', '<TELL "hi" CR>') \
            .does_not_compile()

    def test_go_routine_with_locals_in_v6_should_compile(self):
        """Test that GO routine with locals is allowed in V6."""
        AssertEntryPoint('"AUX" A', "<SET A 5>") \
            .in_v6() \
            .compiles()

        AssertEntryPoint('"OPT" A', "<SET A 5>") \
            .in_v6() \
            .compiles()

        # entry point still can't have required variables
        AssertEntryPoint("A", "<SET A 5>") \
            .in_v6() \
            .does_not_compile()

    def test_go_routine_with_locals_in_prog_should_give_error(self):
        """Test that GO routine with PROG locals is rejected."""
        AssertEntryPoint("", '<PROG (X Y Z) <TELL "hi" CR>>') \
            .does_not_compile()

    def test_go_routine_with_multi_equals_should_not_throw(self):
        """Test that GO routine with multi-arg EQUAL? doesn't throw."""
        AssertEntryPoint("", '<COND (<=? <FOO> 1 2 3 4> <TELL "equals">)>') \
            .with_global("<ROUTINE FOO () 5>") \
            .does_not_throw()

    def test_go_routine_with_setg_indirect_involving_stack_should_not_throw(self):
        """Test that GO routine with indirect SETG doesn't throw."""
        AssertEntryPoint("", "<SETG <+ ,VARNUM 1> <* ,VARVAL 2>>") \
            .with_global("<GLOBAL VARNUM 16>") \
            .with_global("<GLOBAL VARVAL 100>") \
            .does_not_throw()
