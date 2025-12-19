# ZILF Function Interpreter Tests for Zorkie
# ===========================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/FunctionTests.cs
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
Tests for MDL/ZIL function operations.

These tests verify that the zorkie interpreter correctly handles:
- DEFINE and DEFMAC definitions
- FUNCTION construction
- QUOTE and EVAL
- EXPAND macro expansion
- APPLY function application
- MAPF and MAPR mapping
- Argument handling (TUPLE, ARGS, segments)
- DECL checking in functions
"""

import pytest
from .conftest import (
    Context, ZilFix, ZilList, ZilVector, ZilAtom, ZilForm, ZilString,
    ZilFunction, ZilEvalMacro, ZilSegment, StdAtom,
    InterpreterError, ArgumentCountError, ArgumentTypeError, DeclCheckError,
    eval_and_assert, eval_and_catch, evaluate,
    assert_structurally_equal, assert_not_structurally_equal
)


class TestDEFINE:
    """Tests for DEFINE function definition."""

    def test_define_creates_function(self):
        """DEFINE creates a function and returns the function name."""
        ctx = Context()
        expected = ZilAtom.parse("FOO", ctx)
        eval_and_assert("<DEFINE FOO (BAR) <> <> <>>", expected, ctx)

        stored = ctx.get_global_val(expected)
        assert isinstance(stored, ZilFunction)

    def test_redefine_allowed_when_redefine_true(self):
        """Redefining is OK when .REDEFINE is true."""
        ctx = Context()
        ctx.set_local_val(ctx.get_std_atom(StdAtom.REDEFINE), ctx.TRUE)

        expected = ZilAtom.parse("FOO", ctx)
        evaluate("<DEFINE FOO (BAR) <>>", ctx)
        eval_and_assert("<DEFINE FOO (REDEF1) <>>", expected, ctx)

    def test_redefine_error_when_redefine_false(self):
        """Redefining raises error when .REDEFINE is false."""
        ctx = Context()
        evaluate("<DEFINE FOO (BAR) <>>", ctx)
        ctx.set_local_val(ctx.get_std_atom(StdAtom.REDEFINE), None)

        eval_and_catch("<DEFINE FOO (REDEF2) <>>", InterpreterError, ctx=ctx)

    def test_define_must_have_at_least_3_arguments(self):
        """DEFINE requires at least 3 arguments."""
        eval_and_catch("<DEFINE>", InterpreterError)
        eval_and_catch("<DEFINE FOO>", InterpreterError)
        eval_and_catch("<DEFINE FOO (BAR)>", InterpreterError)

    def test_define_segments_can_be_used_with_tuple_parameters(self):
        """Segments can be used with TUPLE parameters."""
        ctx = Context()
        evaluate("<SET L '(1 2 3)> <DEFINE FOO (\"TUPLE\" A) .A>", ctx)
        eval_and_assert(
            "<LIST !<FOO !.L>>",
            ZilList([ZilFix(1), ZilFix(2), ZilFix(3)]),
            ctx
        )

    def test_define_with_activation(self):
        """DEFINE with activation-atom syntax works."""
        ctx = Context()
        evaluate("""
<DEFINE FOO FOO-ACT ()
    <PROG () <RETURN 123 .FOO-ACT>>
    456>""", ctx)
        eval_and_assert("<FOO>", ZilFix(123), ctx)

    def test_define_requires_a_body(self):
        """DEFINE requires a body."""
        eval_and_catch("<DEFINE FOO ()>", InterpreterError)
        eval_and_catch("<DEFINE FOO A ()>", InterpreterError)


class TestDEFMAC:
    """Tests for DEFMAC macro definition."""

    def test_defmac_creates_macro(self):
        """DEFMAC creates a macro and returns the macro name."""
        ctx = Context()
        expected = ZilAtom.parse("FOO", ctx)
        eval_and_assert("<DEFMAC FOO (BAR) <> <> <>>", expected, ctx)

        stored = ctx.get_global_val(expected)
        assert isinstance(stored, ZilEvalMacro)

    def test_defmac_must_have_at_least_3_arguments(self):
        """DEFMAC requires at least 3 arguments."""
        eval_and_catch("<DEFMAC>", InterpreterError)
        eval_and_catch("<DEFMAC FOO>", InterpreterError)
        eval_and_catch("<DEFMAC FOO (BAR)>", InterpreterError)

    def test_defmac_requires_a_body(self):
        """DEFMAC requires a body."""
        eval_and_catch("<DEFMAC FOO ()>", InterpreterError)
        eval_and_catch("<DEFMAC FOO A ()>", InterpreterError)


class TestQUOTE:
    """Tests for QUOTE."""

    def test_quote_returns_argument_unevaluated(self):
        """QUOTE returns its argument unevaluated."""
        eval_and_assert("<QUOTE 123>", ZilFix(123))
        eval_and_assert("<QUOTE ()>", ZilList([]))

        ctx = Context()
        eval_and_assert(
            "<QUOTE <+>>",
            ZilForm([ctx.get_std_atom(StdAtom.Plus)]),
            ctx
        )

    def test_quote_must_have_1_argument(self):
        """QUOTE requires exactly 1 argument."""
        eval_and_catch("<QUOTE>", InterpreterError)
        eval_and_catch("<QUOTE FOO BAR>", InterpreterError)


class TestEVAL:
    """Tests for EVAL."""

    def test_eval_most_values_to_themselves(self):
        """Most values evaluate to themselves."""
        eval_and_assert("<EVAL 123>", ZilFix(123))
        eval_and_assert('<EVAL "hello">', ZilString.from_string("hello"))

        ctx = Context()
        eval_and_assert("<EVAL +>", ctx.get_std_atom(StdAtom.Plus), ctx)
        eval_and_assert("<EVAL <>>", ctx.FALSE, ctx)

    def test_eval_lists_evaluate_elements(self):
        """Lists evaluate to new lists with evaluated elements."""
        ctx = Context()
        ctx.set_local_val(ctx.get_std_atom(StdAtom.T), ZilList([
            ZilFix(1),
            ZilForm([ctx.get_std_atom(StdAtom.Plus), ZilFix(1), ZilFix(1)]),
            ZilFix(3)
        ]))
        expected = ZilList([ZilFix(1), ZilFix(2), ZilFix(3)])
        actual = evaluate("<EVAL .T>", ctx)
        assert_structurally_equal(expected, actual)

    def test_eval_forms_execute(self):
        """Forms execute when evaluated."""
        ctx = Context()
        form = ZilForm([ctx.get_std_atom(StdAtom.Plus), ZilFix(1), ZilFix(2)])
        ctx.set_local_val(ctx.get_std_atom(StdAtom.T), form)
        eval_and_assert("<EVAL .T>", ZilFix(3), ctx)

    def test_eval_must_have_1_or_2_arguments(self):
        """EVAL requires 1 or 2 arguments."""
        eval_and_catch("<EVAL>", ArgumentCountError)
        eval_and_catch("<EVAL FOO BAR BAZ>", ArgumentCountError)

    def test_eval_second_argument_must_be_environment(self):
        """EVAL second argument must be an ENVIRONMENT."""
        eval_and_catch("<EVAL FOO BAR>", ArgumentTypeError)


class TestAPPLY:
    """Tests for APPLY."""

    def test_apply_applies_function_to_arguments(self):
        """APPLY applies a function to arguments."""
        eval_and_assert("<APPLY ,+ 1 2>", ZilFix(3))
        eval_and_assert("<APPLY ,QUOTE 1>", ZilFix(1))
        eval_and_assert("<APPLY <FUNCTION () 3>>", ZilFix(3))
        eval_and_assert("<DEFMAC FOO () 3> <APPLY ,FOO>", ZilFix(3))
        eval_and_assert("<APPLY 2 (100 <+ 199 1> 300)>", ZilFix(200))

    def test_apply_rejects_non_applicable_types(self):
        """APPLY rejects non-applicable types."""
        eval_and_catch("<APPLY +>", InterpreterError)
        eval_and_catch('<APPLY "hello">', InterpreterError)
        eval_and_catch("<APPLY (+ 1 2)>", InterpreterError)
        eval_and_catch("<APPLY <>>", InterpreterError)
        eval_and_catch("<APPLY '<+ 1 2>>", InterpreterError)

    def test_apply_must_have_at_least_1_argument(self):
        """APPLY requires at least 1 argument."""
        eval_and_catch("<APPLY>", InterpreterError)


class TestMAPF:
    """Tests for MAPF."""

    def test_mapf_with_false_finisher(self):
        """MAPF with FALSE finisher returns last result."""
        eval_and_assert(
            "<MAPF <> <FUNCTION (N) <* .N 2>> '(1 2 3)>",
            ZilFix(6)
        )

    def test_mapf_with_vector_finisher(self):
        """MAPF with VECTOR finisher collects results."""
        eval_and_assert(
            "<MAPF ,VECTOR <FUNCTION (N) <* .N 2>> '(1 2 3)>",
            ZilVector(ZilFix(2), ZilFix(4), ZilFix(6))
        )

    def test_mapf_with_multiple_structures(self):
        """MAPF works with multiple input structures."""
        eval_and_assert(
            "<MAPF ,VECTOR <FUNCTION (N M) <* .N .M>> '(1 10 100 1000) '(2 3 4)>",
            ZilVector(ZilFix(2), ZilFix(30), ZilFix(400))
        )


class TestArgumentCounts:
    """Tests for function argument count checking."""

    def test_function_calls_should_check_argument_counts(self):
        """Function calls should check argument counts."""
        ctx = Context()
        evaluate("<DEFINE FOO (A B C) <+ .A .B .C>>", ctx)

        eval_and_catch("<FOO>", ArgumentCountError, ctx=ctx)
        eval_and_catch("<FOO 1>", ArgumentCountError, ctx=ctx)
        eval_and_catch("<FOO 1 2>", ArgumentCountError, ctx=ctx)
        eval_and_catch("<FOO 1 2 3 4>", ArgumentCountError, ctx=ctx)


class TestFunctionDECLs:
    """Tests for DECL checking in functions."""

    def test_function_adecl_parameters_should_set_binding_decls(self):
        """ADECL parameters set binding DECLs."""
        ctx = Context()

        evaluate('<DEFINE FOO (A:FIX "OPT" B:FIX "AUX" C:FIX) <SET A T>>', ctx)
        eval_and_catch("<FOO 1>", DeclCheckError, ctx=ctx)

    def test_function_calls_should_check_argument_decls(self):
        """Function calls should check argument DECLs."""
        ctx = Context()

        evaluate('<DEFINE FOO (A:FIX "OPT" B:FIX) <>>', ctx)
        eval_and_assert("<FOO 1>", ctx.FALSE, ctx)
        eval_and_assert("<FOO 1 2>", ctx.FALSE, ctx)
        eval_and_catch("<FOO X>", DeclCheckError, ctx=ctx)
        eval_and_catch("<FOO 1 X>", DeclCheckError, ctx=ctx)

    def test_function_default_values_should_be_checked(self):
        """Default values should be checked against DECLs."""
        ctx = Context()

        evaluate('<DEFINE FOO ("OPT" (A:FIX NOT-A-FIX)) <>>', ctx)
        eval_and_catch("<FOO>", DeclCheckError, ctx=ctx)

        evaluate('<DEFINE BAR ("AUX" (A:FIX NOT-A-FIX)) <>>', ctx)
        eval_and_catch("<BAR>", DeclCheckError, ctx=ctx)

    def test_function_rejects_conflicting_decls(self):
        """Function rejects conflicting DECLs."""
        eval_and_catch("<DEFINE FOO (A:FIX) #DECL ((A) LIST) <>>", InterpreterError)


class TestROUTINE:
    """Tests for ROUTINE (Z-machine specific)."""

    def test_routine_does_not_allow_tuple_or_args(self):
        """ROUTINE does not allow TUPLE or ARGS."""
        eval_and_catch('<ROUTINE FOO (X "TUPLE" REST) .REST>', InterpreterError)
        eval_and_catch('<ROUTINE BAR (Y "ARGS" REST) .REST>', InterpreterError)
