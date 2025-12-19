# ZILF Structure Interpreter Tests for Zorkie
# ============================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/StructureTests.cs
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
Tests for MDL/ZIL structure operations.

These tests verify that the zorkie interpreter correctly handles:
- FORM comparison
- MEMQ and MEMBER search
- ILIST, IVECTOR, ISTRING initialization
- DEFSTRUCT structure definitions
- REST, BACK, TOP structure navigation
- GROW, SORT, SUBSTRUC operations
- OFFSET for structure access
- PUTREST list manipulation
"""

import pytest
from .conftest import (
    Context, ZilFix, ZilList, ZilVector, ZilForm, ZilString, ZilAtom,
    ZilTable, ZilStructuredHash, ZilOffset, PrimType, StdAtom,
    InterpreterError, DeclCheckError,
    eval_and_assert, eval_and_catch, evaluate,
    assert_structurally_equal, assert_not_structurally_equal
)


class TestFormComparison:
    """Tests for FORM comparison."""

    def test_comparison_of_empty_form(self):
        """Empty FORM comparison works correctly."""
        ctx = Context()
        eval_and_assert("<==? <FORM> '<>>", ctx.TRUE, ctx)
        eval_and_assert("<==? '() '<>>", ctx.FALSE, ctx)
        eval_and_assert("<==? '<> '()>", ctx.FALSE, ctx)


class TestMEMQ:
    """Tests for MEMQ (value search)."""

    def test_memq_in_list(self):
        """MEMQ works in lists."""
        eval_and_assert(
            "<MEMQ 5 '(3 4 5 6 7)>",
            ZilList([ZilFix(5), ZilFix(6), ZilFix(7)])
        )

    def test_memq_in_vector(self):
        """MEMQ works in vectors."""
        eval_and_assert(
            "<MEMQ 5 '[3 4 5 6 7]>",
            ZilVector(ZilFix(5), ZilFix(6), ZilFix(7))
        )

    def test_memq_uses_value_comparison_for_lval_gval(self):
        """MEMQ uses value comparison for LVAL/GVAL, not other structures."""
        ctx = Context()
        eval_and_assert(
            "<MEMQ '.C '[.A .B .C .D]>",
            ZilVector(
                ZilForm([ctx.get_std_atom(StdAtom.LVAL), ZilAtom.parse("C", ctx)]),
                ZilForm([ctx.get_std_atom(StdAtom.LVAL), ZilAtom.parse("D", ctx)])
            ),
            ctx
        )

        eval_and_assert(
            "<MEMQ '<FOO C> '[<FOO A> <FOO B> <FOO C> <FOO D>]>",
            ctx.FALSE,
            ctx
        )


class TestMEMBER:
    """Tests for MEMBER (structural search)."""

    def test_member_in_list(self):
        """MEMBER works in lists."""
        eval_and_assert(
            "<MEMBER '(5) '(3 4 (5) 6 7)>",
            ZilList([
                ZilList([ZilFix(5)]),
                ZilFix(6),
                ZilFix(7)
            ])
        )

    def test_member_in_vector(self):
        """MEMBER works in vectors."""
        eval_and_assert(
            "<MEMBER '(5) '[3 4 (5) 6 7]>",
            ZilVector(ZilList([ZilFix(5)]), ZilFix(6), ZilFix(7))
        )

    def test_member_substring(self):
        """MEMBER does substring searches."""
        ctx = Context()
        eval_and_assert(
            '<MEMBER "PART" "SUM OF PARTS">',
            ZilString.from_string("PARTS"),
            ctx
        )
        eval_and_assert(
            '<MEMBER "Ham" "I am Hamster">',
            ZilString.from_string("Hamster"),
            ctx
        )
        eval_and_assert(
            '<MEMBER "" "Hamster">',
            ctx.FALSE,
            ctx
        )


class TestILIST:
    """Tests for ILIST (list initialization)."""

    def test_ilist_basic(self):
        """ILIST creates a list with repeated values."""
        eval_and_assert(
            "<ILIST 3 123>",
            ZilList([ZilFix(123), ZilFix(123), ZilFix(123)])
        )

    def test_ilist_should_evaluate_initializer_each_time(self):
        """ILIST evaluates initializer each time."""
        eval_and_assert(
            "<SET X 0> <ILIST 3 '<SET X <+ .X 1>>>",
            ZilList([ZilFix(1), ZilFix(2), ZilFix(3)])
        )


class TestIVECTOR:
    """Tests for IVECTOR (vector initialization)."""

    def test_ivector_basic(self):
        """IVECTOR creates a vector with repeated values."""
        eval_and_assert(
            "<IVECTOR 3 123>",
            ZilVector(ZilFix(123), ZilFix(123), ZilFix(123))
        )

    def test_ivector_should_evaluate_initializer_each_time(self):
        """IVECTOR evaluates initializer each time."""
        eval_and_assert(
            "<SET X 0> <IVECTOR 3 '<SET X <+ .X 1>>>",
            ZilVector(ZilFix(1), ZilFix(2), ZilFix(3))
        )


class TestISTRING:
    """Tests for ISTRING (string initialization)."""

    def test_istring_should_evaluate_initializer_each_time(self):
        """ISTRING evaluates initializer each time."""
        eval_and_assert(
            "<SET X 64> <ISTRING 3 '<ASCII <SET X <+ .X 1>>>>",
            ZilString.from_string("ABC")
        )


class TestDEFSTRUCT:
    """Tests for DEFSTRUCT structure definitions."""

    def test_defstruct_new_object(self):
        """DEFSTRUCT can create new objects."""
        ctx = Context()
        point_atom = ZilAtom.parse("POINT", ctx)

        eval_and_assert(
            "<DEFSTRUCT POINT VECTOR (POINT-X FIX) (POINT-Y FIX)>",
            point_atom,
            ctx
        )

        eval_and_assert(
            "<MAKE-POINT 'POINT-X 123 'POINT-Y 456>",
            ZilStructuredHash(point_atom, PrimType.VECTOR, ZilVector(ZilFix(123), ZilFix(456))),
            ctx
        )

        eval_and_assert(
            "<POINT-Y #POINT [234 567]>",
            ZilFix(567),
            ctx
        )

    def test_defstruct_notype(self):
        """DEFSTRUCT with NOTYPE works on raw structures."""
        ctx = Context()
        evaluate("<DEFSTRUCT POINT (VECTOR 'NOTYPE) (POINT-X FIX) (POINT-Y FIX)>", ctx)
        eval_and_assert("<POINT-X [123 456]>", ZilFix(123), ctx)
        eval_and_catch("<CHTYPE [123 456] POINT>", InterpreterError, ctx=ctx)

    def test_defstruct_suppress_constructor(self):
        """DEFSTRUCT 'CONSTRUCTOR suppresses constructor generation."""
        ctx = Context()
        evaluate("<DEFSTRUCT POINT (VECTOR 'CONSTRUCTOR) (POINT-X FIX) (POINT-Y FIX)>", ctx)
        eval_and_assert("<GASSIGNED? MAKE-POINT>", ctx.FALSE, ctx)
        eval_and_assert("<POINT-X <CHTYPE [123 456] POINT>>", ZilFix(123), ctx)


class TestREST:
    """Tests for REST operation."""

    def test_rest_of_one_character_string_should_be_empty_string(self):
        """REST of one-character string is empty string."""
        eval_and_assert('<REST "x">', ZilString.from_string(""))
        eval_and_assert('<REST <REST "xx">>', ZilString.from_string(""))


class TestSUBSTRUC:
    """Tests for SUBSTRUC operation."""

    def test_substruc_with_one_argument_returns_primitive_copy(self):
        """SUBSTRUC with one argument returns a primitive copy."""
        eval_and_assert(
            "<SUBSTRUC '(1 2 3)>",
            ZilList([ZilFix(1), ZilFix(2), ZilFix(3)])
        )
        eval_and_assert(
            '<SUBSTRUC "Hello">',
            ZilString.from_string("Hello")
        )

    def test_substruc_with_two_arguments_returns_rested_primitive_copy(self):
        """SUBSTRUC with two arguments returns a RESTed primitive copy."""
        eval_and_assert(
            "<SUBSTRUC '(1 2 3) 2>",
            ZilList([ZilFix(3)])
        )
        eval_and_assert(
            '<SUBSTRUC "Hello" 3>',
            ZilString.from_string("lo")
        )

    def test_substruc_with_three_arguments_limits_copying(self):
        """SUBSTRUC with three arguments limits copying."""
        eval_and_assert(
            "<SUBSTRUC '(1 2 3) 2 0>",
            ZilList([])
        )
        eval_and_assert(
            '<SUBSTRUC "Hello" 1 3>',
            ZilString.from_string("ell")
        )


class TestTableAccess:
    """Tests for table access operations."""

    def test_access_past_end_of_table_fails(self):
        """Access past end of table fails."""
        eval_and_catch("<ZREST <TABLE 1> 100>", InterpreterError)
        eval_and_catch("<ZGET <TABLE 1> 100>", InterpreterError)
        eval_and_catch("<ZPUT <TABLE 1> 100 0>", InterpreterError)
        eval_and_catch("<GETB <TABLE 1> 100>", InterpreterError)
        eval_and_catch("<PUTB <TABLE 1> 100 0>", InterpreterError)


class TestSORT:
    """Tests for SORT operation."""

    def test_sort_simple_form(self):
        """SORT in simple form works."""
        eval_and_assert(
            "<SORT <> '[1 9 3 5 6 2]>",
            ZilVector(ZilFix(1), ZilFix(2), ZilFix(3), ZilFix(5), ZilFix(6), ZilFix(9))
        )


class TestPUTREST:
    """Tests for PUTREST operation."""

    def test_putrest_on_list(self):
        """PUTREST replaces rest of list."""
        ctx = Context()
        eval_and_assert(
            "<PUTREST '(1 2 3) '(A B)>",
            ZilList([
                ZilFix(1),
                ZilAtom.parse("A", ctx),
                ZilAtom.parse("B", ctx)
            ]),
            ctx
        )

    def test_putrest_on_form(self):
        """PUTREST replaces rest of form."""
        ctx = Context()
        eval_and_assert(
            "<PUTREST '<1 2 3> '(A B)>",
            ZilForm([
                ZilFix(1),
                ZilAtom.parse("A", ctx),
                ZilAtom.parse("B", ctx)
            ]),
            ctx
        )

    def test_putrest_on_empty_list_fails(self):
        """PUTREST on empty list fails."""
        eval_and_catch("<PUTREST () (5)>", InterpreterError)
