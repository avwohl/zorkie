# ZILF Arithmetic Interpreter Tests for Zorkie
# =============================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/ArithmeticTests.cs
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
Tests for MDL/ZIL arithmetic operations.

These tests verify that the zorkie interpreter correctly handles:
- Addition (+)
- Subtraction (-)
- Multiplication (*)
- Division (/)
- Bit shift (LSH)
- Bitwise OR (ORB)
- Bitwise AND (ANDB)
- Bitwise XOR (XORB)
- Bitwise EQV (EQVB)
- Comparisons (L?, L=?, G?, G=?)
- MIN and MAX
"""

import pytest
from .conftest import (
    Context, ZilFix, InterpreterError,
    eval_and_assert, eval_and_catch,
    INT_MAX, INT_MIN
)


class TestAddition:
    """Tests for addition (+)."""

    def test_no_numbers_returns_zero(self):
        """<+> with no arguments returns 0."""
        eval_and_assert("<+>", ZilFix(0))

    def test_one_number_returns_identity(self):
        """<+ 7> returns 7."""
        eval_and_assert("<+ 7>", ZilFix(7))

    def test_two_or_more_numbers_returns_sum(self):
        """<+ 1 2> returns 3, etc."""
        eval_and_assert("<+ 1 2>", ZilFix(3))
        eval_and_assert("<+ 1 2 3>", ZilFix(6))
        eval_and_assert("<+ -6 -6 10 1 -2>", ZilFix(-3))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<+ "foo" 1>', InterpreterError)
        eval_and_catch("<+ 0 ATOM>", InterpreterError)
        eval_and_catch("<+ (1 2 3)>", InterpreterError)


class TestSubtraction:
    """Tests for subtraction (-)."""

    def test_no_numbers_returns_zero(self):
        """<-> with no arguments returns 0."""
        eval_and_assert("<->", ZilFix(0))

    def test_one_number_returns_negation(self):
        """<- 7> returns -7."""
        eval_and_assert("<- 7>", ZilFix(-7))

    def test_two_or_more_numbers_returns_difference(self):
        """<- 1 2> returns -1, etc."""
        eval_and_assert("<- 1 2>", ZilFix(-1))
        eval_and_assert("<- 1 2 3>", ZilFix(-4))
        eval_and_assert("<- -6 -6 10 1 -2>", ZilFix(-9))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<- "foo" 1>', InterpreterError)
        eval_and_catch("<- 0 ATOM>", InterpreterError)
        eval_and_catch("<- (1 2 3)>", InterpreterError)


class TestMultiplication:
    """Tests for multiplication (*)."""

    def test_no_numbers_returns_one(self):
        """<*> with no arguments returns 1."""
        eval_and_assert("<*>", ZilFix(1))

    def test_one_number_returns_identity(self):
        """<* 7> returns 7."""
        eval_and_assert("<* 7>", ZilFix(7))
        eval_and_assert("<* -7>", ZilFix(-7))

    def test_two_or_more_numbers_returns_product(self):
        """<* 1 2> returns 2, etc."""
        eval_and_assert("<* 1 2>", ZilFix(2))
        eval_and_assert("<* 1 2 3>", ZilFix(6))
        eval_and_assert("<* -6 -6 10 1 -2>", ZilFix(-720))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<* "foo" 1>', InterpreterError)
        eval_and_catch("<* 0 ATOM>", InterpreterError)
        eval_and_catch("<* (1 2 3)>", InterpreterError)


class TestDivision:
    """Tests for division (/)."""

    def test_no_numbers_returns_one(self):
        """</> with no arguments returns 1."""
        eval_and_assert("</>", ZilFix(1))

    def test_one_number_returns_integer_reciprocal(self):
        """</ 1> returns 1, </ 2> returns 0, etc."""
        eval_and_assert("</ 1>", ZilFix(1))
        eval_and_assert("</ -1>", ZilFix(-1))
        eval_and_assert("</ 2>", ZilFix(0))
        eval_and_assert("</ -2>", ZilFix(0))
        eval_and_assert("</ 7>", ZilFix(0))

    def test_two_or_more_numbers_returns_quotient(self):
        """</ 10 2> returns 5, etc."""
        eval_and_assert("</ 10 2>", ZilFix(5))
        eval_and_assert("</ 100 2 5>", ZilFix(10))
        eval_and_assert("</ 360 -4 3 15>", ZilFix(-2))

    def test_division_by_zero_error(self):
        """Division by zero should raise error."""
        eval_and_catch("</ 0>", InterpreterError)
        eval_and_catch("</ 0 0>", InterpreterError)
        eval_and_catch("</ 1 0>", InterpreterError)

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('</ "foo" 1>', InterpreterError)
        eval_and_catch("</ 0 ATOM>", InterpreterError)
        eval_and_catch("</ (1 2 3)>", InterpreterError)


class TestLSH:
    """Tests for logical shift (LSH)."""

    def test_zero_offset_no_change(self):
        """<LSH 12345 0> returns 12345."""
        eval_and_assert("<LSH 12345 0>", ZilFix(12345))

    def test_positive_offset_left_shift(self):
        """Positive offset means left shift."""
        eval_and_assert("<LSH 1 1>", ZilFix(2))
        eval_and_assert("<LSH 3 2>", ZilFix(12))
        eval_and_assert("<LSH *20000000000* 5>", ZilFix(0))

    def test_negative_offset_right_shift(self):
        """Negative offset means right shift."""
        eval_and_assert("<LSH 8 -3>", ZilFix(1))
        eval_and_assert("<LSH 1 -1>", ZilFix(0))
        eval_and_assert("<LSH *37777777777* -32>", ZilFix(0))

    def test_must_have_exactly_2_arguments(self):
        """LSH requires exactly 2 arguments."""
        eval_and_catch("<LSH>", InterpreterError)
        eval_and_catch("<LSH 1>", InterpreterError)
        eval_and_catch("<LSH 1 2 3>", InterpreterError)

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<LSH "foo" 1>', InterpreterError)
        eval_and_catch("<LSH 0 ATOM>", InterpreterError)
        eval_and_catch("<LSH (1 2 3) (4 5 6)>", InterpreterError)


class TestORB:
    """Tests for bitwise OR (ORB)."""

    def test_no_numbers_returns_zero(self):
        """<ORB> returns 0."""
        eval_and_assert("<ORB>", ZilFix(0))

    def test_one_number_returns_identity(self):
        """<ORB 0> returns 0, <ORB 1> returns 1."""
        eval_and_assert("<ORB 0>", ZilFix(0))
        eval_and_assert("<ORB 1>", ZilFix(1))

    def test_two_or_more_numbers_returns_bitwise_or(self):
        """Bitwise OR of multiple numbers."""
        eval_and_assert("<ORB 0 16>", ZilFix(16))
        eval_and_assert("<ORB 64 96>", ZilFix(96))
        eval_and_assert("<ORB *05777777776* *32107654321*>", ZilFix(-1))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<ORB "foo" 1>', InterpreterError)
        eval_and_catch("<ORB 0 ATOM>", InterpreterError)
        eval_and_catch("<ORB (1 2 3)>", InterpreterError)


class TestANDB:
    """Tests for bitwise AND (ANDB)."""

    def test_no_numbers_returns_all_bits_set(self):
        """<ANDB> returns -1 (all bits set)."""
        eval_and_assert("<ANDB>", ZilFix(-1))

    def test_one_number_returns_identity(self):
        """<ANDB 0> returns 0, <ANDB 1> returns 1."""
        eval_and_assert("<ANDB 0>", ZilFix(0))
        eval_and_assert("<ANDB 1>", ZilFix(1))

    def test_two_or_more_numbers_returns_bitwise_and(self):
        """Bitwise AND of multiple numbers."""
        eval_and_assert("<ANDB 0 16>", ZilFix(0))
        eval_and_assert("<ANDB 64 96>", ZilFix(64))
        eval_and_assert("<ANDB *05777777776* *32107654321*>", ZilFix(0x11f58d0))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<ANDB "foo" 1>', InterpreterError)
        eval_and_catch("<ANDB 0 ATOM>", InterpreterError)
        eval_and_catch("<ANDB (1 2 3)>", InterpreterError)


class TestXORB:
    """Tests for bitwise XOR (XORB)."""

    def test_no_numbers_returns_zero(self):
        """<XORB> returns 0."""
        eval_and_assert("<XORB>", ZilFix(0))

    def test_one_number_returns_identity(self):
        """<XORB 0> returns 0, <XORB 1> returns 1."""
        eval_and_assert("<XORB 0>", ZilFix(0))
        eval_and_assert("<XORB 1>", ZilFix(1))

    def test_two_or_more_numbers_returns_bitwise_xor(self):
        """Bitwise XOR of multiple numbers."""
        eval_and_assert("<XORB 0 16>", ZilFix(16))
        eval_and_assert("<XORB 64 96>", ZilFix(32))
        # Note: 0xfee0a72f is the expected value (signed)
        eval_and_assert("<XORB *05777777776* *32107654321*>", ZilFix(-18024657))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<XORB "foo" 1>', InterpreterError)
        eval_and_catch("<XORB 0 ATOM>", InterpreterError)
        eval_and_catch("<XORB (1 2 3)>", InterpreterError)


class TestEQVB:
    """Tests for bitwise EQV (EQVB) - inverted XOR."""

    def test_no_numbers_returns_all_bits_set(self):
        """<EQVB> returns -1 (all bits set)."""
        eval_and_assert("<EQVB>", ZilFix(-1))

    def test_one_number_returns_identity(self):
        """<EQVB 0> returns 0, <EQVB 1> returns 1."""
        eval_and_assert("<EQVB 0>", ZilFix(0))
        eval_and_assert("<EQVB 1>", ZilFix(1))

    def test_two_or_more_numbers_returns_bitwise_eqv(self):
        """Bitwise EQV (inverted XOR) of multiple numbers."""
        eval_and_assert("<EQVB 0 16>", ZilFix(-17))
        eval_and_assert("<EQVB 64 96>", ZilFix(-33))
        eval_and_assert("<EQVB *05777777776* *32107654321*>", ZilFix(0x11f58d0))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch('<EQVB "foo" 1>', InterpreterError)
        eval_and_catch("<EQVB 0 ATOM>", InterpreterError)
        eval_and_catch("<EQVB (1 2 3)>", InterpreterError)


class TestComparisons:
    """Tests for numeric comparisons (L?, L=?, G?, G=?)."""

    def test_less_than(self):
        """L? compares less than."""
        ctx = Context()
        eval_and_assert("<L? 4 5>", ctx.TRUE, ctx)
        eval_and_assert("<L? 4 4>", ctx.FALSE, ctx)
        eval_and_assert("<L? 4 3>", ctx.FALSE, ctx)

    def test_less_than_or_equal(self):
        """L=? compares less than or equal."""
        ctx = Context()
        eval_and_assert("<L=? 4 5>", ctx.TRUE, ctx)
        eval_and_assert("<L=? 4 4>", ctx.TRUE, ctx)
        eval_and_assert("<L=? 4 3>", ctx.FALSE, ctx)

    def test_greater_than(self):
        """G? compares greater than."""
        ctx = Context()
        eval_and_assert("<G? 4 5>", ctx.FALSE, ctx)
        eval_and_assert("<G? 4 4>", ctx.FALSE, ctx)
        eval_and_assert("<G? 4 3>", ctx.TRUE, ctx)

    def test_greater_than_or_equal(self):
        """G=? compares greater than or equal."""
        ctx = Context()
        eval_and_assert("<G=? 4 5>", ctx.FALSE, ctx)
        eval_and_assert("<G=? 4 4>", ctx.TRUE, ctx)
        eval_and_assert("<G=? 4 3>", ctx.TRUE, ctx)


class TestMinMax:
    """Tests for MIN and MAX."""

    def test_no_arguments(self):
        """MIN with no args returns INT_MAX, MAX returns INT_MIN."""
        eval_and_assert("<MIN>", ZilFix(INT_MAX))
        eval_and_assert("<MAX>", ZilFix(INT_MIN))

    def test_one_argument(self):
        """MIN/MAX of one number returns that number."""
        eval_and_assert("<MIN 1>", ZilFix(1))
        eval_and_assert("<MAX 4>", ZilFix(4))

    def test_multiple_arguments(self):
        """MIN/MAX of multiple numbers returns smallest/largest."""
        eval_and_assert("<MIN -5 2 0 12>", ZilFix(-5))
        eval_and_assert("<MAX -5 2 0 12>", ZilFix(12))

    def test_arguments_must_be_numbers(self):
        """Non-numeric arguments should raise error."""
        eval_and_catch("<MIN APPLE>", InterpreterError)
        eval_and_catch("<MIN '(1 2 3)>", InterpreterError)
