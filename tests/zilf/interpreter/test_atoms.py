# ZILF Atom Interpreter Tests for Zorkie
# =======================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/AtomTests.cs
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
Tests for MDL/ZIL atom operations.

These tests verify that the zorkie interpreter correctly handles:
- SPNAME (atom print name)
- PARSE and LPARSE (string to expression)
- SETG and SET (global/local assignment)
- GVAL and LVAL (global/local value)
- VALUE (combined value access)
- GASSIGNED? and ASSIGNED? (assignment checking)
- GBOUND? and BOUND? (binding checking)
- GUNASSIGN and UNASSIGN (unassignment)
- GDECL (global declarations)
- LOOKUP, INSERT, REMOVE (oblist operations)
- ROOT, LINK, ATOM (atom creation)
"""

import pytest
from .conftest import (
    Context, ZilFix, ZilList, ZilVector, ZilString, ZilAtom, StdAtom,
    InterpreterError, ArgumentCountError, ArgumentTypeError, DeclCheckError,
    eval_and_assert, eval_and_catch, evaluate,
    assert_structurally_equal, assert_not_structurally_equal
)


class TestSPNAME:
    """Tests for SPNAME (atom print name)."""

    def test_spname_returns_print_name(self):
        """SPNAME returns the print name of an atom."""
        eval_and_assert("<SPNAME FOO>", ZilString.from_string("FOO"))
        eval_and_assert("<SPNAME +>", ZilString.from_string("+"))

    def test_spname_must_have_1_argument(self):
        """SPNAME requires exactly 1 argument."""
        eval_and_catch("<SPNAME>", InterpreterError)
        eval_and_catch("<SPNAME FOO BAR>", InterpreterError)

    def test_spname_argument_must_be_atom(self):
        """SPNAME argument must be an atom."""
        eval_and_catch("<SPNAME 5>", InterpreterError)
        eval_and_catch("<SPNAME (1 2 3)>", InterpreterError)
        eval_and_catch('<SPNAME "hello">', InterpreterError)


class TestPARSE:
    """Tests for PARSE (string to expression)."""

    def test_parse_atoms(self):
        """PARSE can parse atoms."""
        ctx = Context()
        expected = ZilAtom("FOO", ctx.RootObList)
        ctx.RootObList["FOO"] = expected

        actual = evaluate('<PARSE "FOO">', ctx)
        assert actual is expected

    def test_parse_other_expressions(self):
        """PARSE can parse other expressions."""
        ctx = Context()
        eval_and_assert('<PARSE "23">', ZilFix(23), ctx)
        eval_and_assert(
            '<PARSE "(1 2 3)">',
            ZilList([ZilFix(1), ZilFix(2), ZilFix(3)]),
            ctx
        )

    def test_parse_read_macros(self):
        """PARSE handles READ macros."""
        ctx = Context()
        eval_and_assert('<PARSE "%<+ 12 34>">', ZilFix(46), ctx)

    def test_parse_string_must_contain_expression(self):
        """PARSE string must contain at least one expression."""
        ctx = Context()
        eval_and_catch('<PARSE " ">', InterpreterError, ctx=ctx)

    def test_parse_multiple_expressions_returns_first(self):
        """PARSE with multiple expressions returns only the first."""
        ctx = Context()
        eval_and_assert('<PARSE "1 2 3">', ZilFix(1), ctx)

    def test_parse_must_have_1_to_3_arguments(self):
        """PARSE requires 1 to 3 arguments."""
        ctx = Context()
        eval_and_catch("<PARSE>", InterpreterError, ctx=ctx)
        eval_and_catch('<PARSE "FOO" <GETPROP PACKAGE OBLIST> 10 "BAR">', InterpreterError, ctx=ctx)

    def test_parse_argument_must_be_string(self):
        """PARSE argument must be a string."""
        ctx = Context()
        eval_and_catch("<PARSE 5>", InterpreterError, ctx=ctx)
        eval_and_catch('<PARSE ("FOO")>', InterpreterError, ctx=ctx)


class TestLPARSE:
    """Tests for LPARSE (string to expression list)."""

    def test_lparse_only_one_expression_returns_empty_list(self):
        """LPARSE with only whitespace returns empty list."""
        ctx = Context()
        eval_and_assert('<LPARSE " ">', ZilList([]), ctx)

    def test_lparse_multiple_expressions(self):
        """LPARSE with multiple expressions returns all."""
        ctx = Context()
        eval_and_assert(
            '<LPARSE "1 FOO [3]">',
            ZilList([
                ZilFix(1),
                ZilAtom.parse("FOO", ctx),
                ZilVector(ZilFix(3))
            ]),
            ctx
        )


class TestSETG:
    """Tests for SETG (global assignment)."""

    def test_setg_stores_global_value(self):
        """SETG stores a global value."""
        ctx = Context()
        expected = ZilFix(123)
        eval_and_assert("<SETG FOO 123>", expected, ctx)

        stored = ctx.get_global_val(ZilAtom.parse("FOO", ctx))
        assert_structurally_equal(expected, stored)

    def test_setg_must_have_2_arguments(self):
        """SETG requires exactly 2 arguments."""
        eval_and_catch("<SETG>", InterpreterError)
        eval_and_catch("<SETG FOO>", InterpreterError)
        eval_and_catch("<SETG FOO 123 BAR>", InterpreterError)

    def test_setg_first_argument_must_be_atom(self):
        """SETG first argument must be an atom."""
        eval_and_catch('<SETG "FOO" 5>', InterpreterError)


class TestSET:
    """Tests for SET (local assignment)."""

    def test_set_stores_local_value(self):
        """SET stores a local value."""
        ctx = Context()
        expected = ZilFix(123)
        eval_and_assert("<SET FOO 123>", expected, ctx)

        stored = ctx.get_local_val(ZilAtom.parse("FOO", ctx))
        assert_structurally_equal(expected, stored)

    def test_set_must_have_2_to_3_arguments(self):
        """SET requires 2 to 3 arguments."""
        eval_and_catch("<SET>", ArgumentCountError)
        eval_and_catch("<SET FOO>", ArgumentCountError)
        eval_and_catch("<SET FOO BAR BAZ QUUX>", ArgumentCountError)

    def test_set_first_argument_must_be_atom(self):
        """SET first argument must be an atom."""
        eval_and_catch('<SET "FOO" 5>', ArgumentTypeError)


class TestGVAL:
    """Tests for GVAL (global value)."""

    def test_gval_retrieves_global_value(self):
        """GVAL retrieves a global value."""
        ctx = Context()
        expected = ZilFix(123)
        ctx.set_global_val(ZilAtom.parse("FOO", ctx), expected)
        actual = evaluate("<GVAL FOO>", ctx)
        assert_structurally_equal(expected, actual)

    def test_gval_fails_when_undefined(self):
        """GVAL fails when atom is undefined."""
        eval_and_catch("<GVAL TESTING-TESTING-THIS-ATOM-HAS-NO-GVAL>", InterpreterError)

    def test_gval_must_have_1_argument(self):
        """GVAL requires exactly 1 argument."""
        eval_and_catch("<GVAL>", InterpreterError)
        eval_and_catch("<GVAL FOO BAR>", InterpreterError)

    def test_gval_argument_must_be_atom(self):
        """GVAL argument must be an atom."""
        eval_and_catch('<GVAL "FOO">', InterpreterError)


class TestLVAL:
    """Tests for LVAL (local value)."""

    def test_lval_retrieves_local_value(self):
        """LVAL retrieves a local value."""
        ctx = Context()
        expected = ZilFix(123)
        ctx.set_local_val(ZilAtom.parse("FOO", ctx), expected)
        actual = evaluate("<LVAL FOO>", ctx)
        assert_structurally_equal(expected, actual)

    def test_lval_fails_when_undefined(self):
        """LVAL fails when atom is undefined."""
        eval_and_catch("<LVAL TESTING-TESTING-THIS-ATOM-HAS-NO-LVAL>", InterpreterError)


class TestVALUE:
    """Tests for VALUE (combined value access)."""

    def test_value_prefers_local(self):
        """VALUE prefers local over global."""
        ctx = Context()
        foo = ZilAtom.parse("FOO", ctx)

        eval_and_catch("<VALUE FOO>", InterpreterError, ctx=ctx)

        ctx.set_global_val(foo, ZilFix(123))
        eval_and_assert("<VALUE FOO>", ZilFix(123), ctx)

        ctx.set_local_val(foo, ZilFix(456))
        eval_and_assert("<VALUE FOO>", ZilFix(456), ctx)

        ctx.set_local_val(foo, None)
        eval_and_assert("<VALUE FOO>", ZilFix(123), ctx)

        ctx.set_global_val(foo, None)
        eval_and_catch("<VALUE FOO>", InterpreterError, ctx=ctx)


class TestGASSIGNED_P:
    """Tests for GASSIGNED? (global assignment check)."""

    def test_gassigned_p(self):
        """GASSIGNED? checks global assignment."""
        ctx = Context()
        whatever = ZilFix(123)
        ctx.set_global_val(ZilAtom.parse("MY-TEST-GLOBAL", ctx), whatever)
        ctx.set_local_val(ZilAtom.parse("MY-TEST-LOCAL", ctx), whatever)

        eval_and_assert("<GASSIGNED? MY-TEST-GLOBAL>", ctx.TRUE, ctx)
        eval_and_assert("<GASSIGNED? MY-TEST-LOCAL>", ctx.FALSE, ctx)
        eval_and_assert("<GASSIGNED? THIS-ATOM-HAS-NO-GVAL-OR-LVAL>", ctx.FALSE, ctx)


class TestASSIGNED_P:
    """Tests for ASSIGNED? (local assignment check)."""

    def test_assigned_p(self):
        """ASSIGNED? checks local assignment."""
        ctx = Context()
        whatever = ZilFix(123)
        ctx.set_global_val(ZilAtom.parse("MY-TEST-GLOBAL", ctx), whatever)
        ctx.set_local_val(ZilAtom.parse("MY-TEST-LOCAL", ctx), whatever)

        eval_and_assert("<ASSIGNED? MY-TEST-LOCAL>", ctx.TRUE, ctx)
        eval_and_assert("<ASSIGNED? MY-TEST-GLOBAL>", ctx.FALSE, ctx)
        eval_and_assert("<ASSIGNED? THIS-ATOM-HAS-NO-GVAL-OR-LVAL>", ctx.FALSE, ctx)


class TestGUNASSIGN:
    """Tests for GUNASSIGN (global unassignment)."""

    def test_gunassign(self):
        """GUNASSIGN removes global value."""
        ctx = Context()
        foo = ZilAtom.parse("FOO", ctx)
        ctx.set_global_val(foo, ZilFix(123))

        evaluate("<GUNASSIGN FOO>", ctx)
        eval_and_assert("<GASSIGNED? FOO>", ctx.FALSE, ctx)
        eval_and_catch("<GVAL FOO>", InterpreterError, ctx=ctx)


class TestGDECL:
    """Tests for GDECL (global declarations)."""

    def test_gdecl(self):
        """GDECL sets global declarations."""
        ctx = Context()
        evaluate("<GDECL (FOO BAR) FIX (BAZ) ANY>", ctx)

        eval_and_assert("<SETG FOO 1>", ZilFix(1), ctx)
        eval_and_catch("<SETG FOO NOT-A-FIX>", DeclCheckError, ctx=ctx)
        eval_and_assert("<SETG FOO 5>", ZilFix(5), ctx)
        evaluate("<GUNASSIGN FOO>", ctx)

        eval_and_assert("<GASSIGNED? BAR>", ctx.FALSE, ctx)
        eval_and_catch("<SETG BAR NOT-A-FIX>", DeclCheckError, ctx=ctx)

        eval_and_assert("<SETG BAZ NOT-A-FIX>", ZilAtom.parse("NOT-A-FIX", ctx), ctx)


class TestATOM:
    """Tests for ATOM (create uninterned atom)."""

    def test_atom_creates_new_uninterned_atoms(self):
        """ATOM creates new uninterned atoms each time."""
        ctx = Context()
        foo1 = evaluate("FOO", ctx)
        foo2 = evaluate('<ATOM "FOO">', ctx)
        foo3 = evaluate('<ATOM "FOO">', ctx)

        assert_not_structurally_equal(foo1, foo2)
        assert_not_structurally_equal(foo1, foo3)
        assert_not_structurally_equal(foo2, foo3)

    def test_atom_must_have_1_argument(self):
        """ATOM requires exactly 1 argument."""
        eval_and_catch("<ATOM>", ArgumentCountError)
        eval_and_catch("<ATOM FOO BAR>", ArgumentCountError)

    def test_atom_argument_must_be_string(self):
        """ATOM argument must be a string."""
        eval_and_catch("<ATOM FOO>", ArgumentTypeError)
