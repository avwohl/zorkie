# ZILF Opcode Tests for Zorkie
# ============================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/OpcodeTests.cs
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
Tests for Z-machine opcode compilation and execution.

These tests verify that the zorkie compiler correctly handles Z-machine
opcodes across different versions (V3-V6), including:
- Arithmetic operations (ADD, SUB, MUL, DIV, MOD)
- Bitwise operations (BAND, BOR, BCOM, BTST)
- Comparison operations (EQUAL?, LESS?, GRTR?)
- Object operations (FIRST?, NEXT?, IN?, FSET?, etc.)
- Control flow (RETURN, RFALSE, RTRUE, CATCH, THROW)
- I/O operations (PRINT, READ, INPUT)
- Memory operations (GET, GETB, PUT, PUTB)
"""

import pytest
from .conftest import AssertExpr, AssertRoutine, AssertGlobals


class TestArithmetic:
    """Tests for arithmetic opcodes."""

    def test_add(self):
        """Test ADD opcode."""
        AssertExpr("<+ 1 2>").gives_number("3")
        AssertExpr("<+ 1 -2>").gives_number("-1")
        AssertExpr("<+ 32767 1>").gives_number("-32768")  # overflow
        AssertExpr("<+ -32768 -1>").gives_number("32767")  # underflow
        AssertExpr("<+>").gives_number("0")  # identity
        AssertExpr("<+ 5>").gives_number("5")
        AssertExpr("<+ 1 2 3>").gives_number("6")
        AssertExpr("<+ 1 2 3 4>").gives_number("10")
        AssertExpr("<+ 1 2 3 4 5>").gives_number("15")

        # alias
        AssertExpr("<ADD 1 2>").gives_number("3")

    def test_add_rest_alias(self):
        """Test REST alias for ADD (where 2nd operand defaults to 1)."""
        AssertExpr("<REST 1>").gives_number("2")
        AssertExpr("<REST 1 2>").gives_number("3")

    def test_sub(self):
        """Test SUB opcode."""
        AssertExpr("<- 1 2>").gives_number("-1")
        AssertExpr("<- 1 -2>").gives_number("3")
        AssertExpr("<- -32768 1>").gives_number("32767")
        AssertExpr("<- 32767 -1>").gives_number("-32768")

        # unary negation
        AssertExpr("<- 123>").gives_number("-123")
        AssertExpr("<- -200>").gives_number("200")
        AssertExpr("<- 0>").gives_number("0")

        AssertExpr("<->").gives_number("0")
        AssertExpr("<- 5>").gives_number("-5")
        AssertExpr("<- 1 2 3>").gives_number("-4")
        AssertExpr("<- 1 2 3 4>").gives_number("-8")
        AssertExpr("<- 1 2 3 4 5>").gives_number("-13")

        # alias
        AssertExpr("<SUB 1 2>").gives_number("-1")

    def test_sub_back_alias(self):
        """Test BACK alias for SUB (where 2nd operand defaults to 1)."""
        AssertExpr("<BACK 1>").gives_number("0")
        AssertExpr("<BACK 1 2>").gives_number("-1")

    def test_mul(self):
        """Test MUL opcode."""
        AssertExpr("<* 6 7>").gives_number("42")
        AssertExpr("<* -4 100>").gives_number("-400")
        AssertExpr("<* -4 -100>").gives_number("400")
        AssertExpr("<*>").gives_number("1")  # identity
        AssertExpr("<* 7>").gives_number("7")
        AssertExpr("<* 2 3 4>").gives_number("24")
        AssertExpr("<* 2 3 4 5>").gives_number("120")

        # alias
        AssertExpr("<MUL 6 7>").gives_number("42")

    def test_div(self):
        """Test DIV opcode."""
        AssertExpr("<DIV 360 90>").gives_number("4")
        AssertExpr("<DIV 100 -2>").gives_number("-50")
        AssertExpr("<DIV -100 -2>").gives_number("50")
        AssertExpr("<DIV -17 2>").gives_number("-8")  # truncation toward zero
        AssertExpr("<DIV>").gives_number("1")
        AssertExpr("<DIV 1>").gives_number("1")
        AssertExpr("<DIV 2>").gives_number("0")
        AssertExpr("<DIV 1 1>").gives_number("1")
        AssertExpr("<DIV 1 1 1>").gives_number("1")

    def test_mod(self):
        """Test MOD opcode."""
        AssertExpr("<MOD 13 4>").gives_number("1")
        AssertExpr("<MOD -13 4>").gives_number("-1")  # sign follows dividend
        AssertExpr("<MOD 13 -4>").gives_number("1")
        AssertExpr("<MOD -13 -4>").gives_number("-1")

    def test_mod_error(self):
        """Test MOD error cases."""
        AssertExpr("<MOD>").does_not_compile()
        AssertExpr("<MOD 0>").does_not_compile()
        AssertExpr("<MOD 0 0 0>").does_not_compile()


class TestBitwise:
    """Tests for bitwise opcodes."""

    def test_band(self):
        """Test BAND opcode."""
        AssertExpr("<BAND>").gives_number("-1")  # identity (all bits set)
        AssertExpr("<BAND 33>").gives_number("33")
        AssertExpr("<BAND 33 96>").gives_number("32")
        AssertExpr("<BAND 33 96 64>").gives_number("0")

        # alias
        AssertExpr("<ANDB 33 96>").gives_number("32")

    def test_bor(self):
        """Test BOR opcode."""
        AssertExpr("<BOR>").gives_number("0")  # identity
        AssertExpr("<BOR 33>").gives_number("33")
        AssertExpr("<BOR 33 96>").gives_number("97")
        AssertExpr("<BOR 33 96 64>").gives_number("97")

        # alias
        AssertExpr("<ORB 33 96>").gives_number("97")

    def test_bcom(self):
        """Test BCOM opcode."""
        AssertExpr("<BCOM 32767>").gives_number("-32768")
        # opcode changes in V5
        AssertExpr("<BCOM 32767>").in_v5().gives_number("-32768")

    def test_bcom_error(self):
        """Test BCOM error cases."""
        AssertExpr("<BCOM>").does_not_compile()
        AssertExpr("<BCOM 33 96>").does_not_compile()

    def test_btst(self):
        """Test BTST opcode."""
        AssertExpr("<BTST 64 64>").gives_number("1")
        AssertExpr("<BTST 64 63>").gives_number("0")
        AssertExpr("<BTST 97 33>").gives_number("1")

    def test_btst_error(self):
        """Test BTST error cases."""
        AssertExpr("<BTST>").does_not_compile()
        AssertExpr("<BTST 97>").does_not_compile()
        AssertExpr("<BTST 97 31 29>").does_not_compile()

    def test_xorb(self):
        """Test XORB opcode."""
        AssertRoutine("X", "<XORB .X -1>").when_called_with("12345").gives_number("-12346")
        AssertRoutine("X", "<XORB -1 .X>").when_called_with("32767").gives_number("-32768")


class TestShift:
    """Tests for shift opcodes."""

    def test_ash(self):
        """Test ASH (arithmetic shift) opcode - V5+ only."""
        AssertExpr("<ASH 4 0>").in_v5().gives_number("4")
        AssertExpr("<ASH 4 1>").in_v5().gives_number("8")
        AssertExpr("<ASH 4 -2>").in_v5().gives_number("1")

        # alias
        AssertExpr("<ASHIFT 4 0>").in_v5().gives_number("4")

    def test_ash_error(self):
        """Test ASH error cases."""
        # Not available in V3/V4
        AssertExpr("<ASH 4 0>").in_v3().does_not_compile()
        AssertExpr("<ASH 4 0>").in_v4().does_not_compile()

        # Wrong number of arguments
        AssertExpr("<ASH>").in_v5().does_not_compile()
        AssertExpr("<ASH 4>").in_v5().does_not_compile()
        AssertExpr("<ASH 4 1 9>").in_v5().does_not_compile()

    def test_shift(self):
        """Test SHIFT (logical shift) opcode - V5+ only."""
        AssertExpr("<SHIFT 1 3>").in_v5().gives_number("8")
        AssertExpr("<SHIFT 16 -3>").in_v5().gives_number("2")
        AssertExpr("<SHIFT 1 16>").in_v5().gives_number("0")
        AssertExpr("<SHIFT 1 15>").in_v5().gives_number("-32768")
        AssertExpr("<SHIFT 16384 -14>").in_v5().gives_number("1")

    def test_shift_error(self):
        """Test SHIFT error cases."""
        # Not available in V4 and below
        AssertExpr("<SHIFT>").in_v4().does_not_compile()

        # Wrong number of arguments
        AssertExpr("<SHIFT 0>").in_v5().does_not_compile()
        AssertExpr("<SHIFT 0 0 0>").in_v5().does_not_compile()


class TestComparison:
    """Tests for comparison opcodes."""

    def test_equal_p(self):
        """Test EQUAL? opcode."""
        AssertExpr("<EQUAL? 1 1>").gives_number("1")
        AssertExpr("<EQUAL? 1 2>").gives_number("0")
        AssertExpr("<EQUAL? 1 2 1>").gives_number("1")  # any match
        AssertExpr("<EQUAL? 1 2 3 4>").gives_number("0")
        AssertExpr("<EQUAL? 1 2 3 4 5 6 7 8 9 0 1>").gives_number("1")

        AssertExpr("<COND (<EQUAL? 1 2 3 4 5 6 1> 99) (T 0)>").gives_number("99")
        AssertRoutine("X", "<COND (<EQUAL? <+ .X 1> 2 4 6 8> 99) (T 0)>") \
            .when_called_with("7").gives_number("99")

        # aliases
        AssertExpr("<=? 1 1>").gives_number("1")
        AssertExpr("<==? 1 1>").gives_number("1")

    def test_equal_p_error(self):
        """Test EQUAL? error cases."""
        AssertExpr("<EQUAL?>").does_not_compile()

    def test_zero_p(self):
        """Test ZERO? opcode."""
        AssertExpr("<ZERO? 0>").in_v3().gives_number("1")
        AssertExpr("<ZERO? -5>").in_v3().gives_number("0")

        # alias
        AssertExpr("<0? 0>").in_v3().gives_number("1")

    def test_zero_p_error(self):
        """Test ZERO? error cases."""
        AssertExpr("<ZERO?>").in_v3().does_not_compile()
        AssertExpr("<ZERO? 0 0>").in_v3().does_not_compile()

    def test_less_p(self):
        """Test LESS? opcode."""
        AssertExpr("<LESS? 1 3>").in_v3().gives_number("1")
        AssertExpr("<LESS? 3 1>").in_v3().gives_number("0")
        AssertExpr("<LESS? 37 37>").in_v3().gives_number("0")

        # alias
        AssertExpr("<L? 1 3>").in_v3().gives_number("1")

    def test_less_p_error(self):
        """Test LESS? error cases."""
        AssertExpr("<LESS?>").in_v3().does_not_compile()
        AssertExpr("<LESS? 0>").in_v3().does_not_compile()
        AssertExpr("<LESS? 0 0 0>").in_v3().does_not_compile()

    def test_leq_p(self):
        """Test L=? opcode."""
        AssertExpr("<L=? -1 3>").in_v3().gives_number("1")
        AssertExpr("<L=? 3 -1>").in_v3().gives_number("0")
        AssertExpr("<L=? 37 37>").in_v3().gives_number("1")

    def test_leq_p_error(self):
        """Test L=? error cases."""
        AssertExpr("<L=?>").in_v3().does_not_compile()
        AssertExpr("<L=? 0>").in_v3().does_not_compile()
        AssertExpr("<L=? 0 0 0>").in_v3().does_not_compile()

    def test_grtr_p(self):
        """Test GRTR? opcode."""
        AssertExpr("<GRTR? -1 3>").in_v3().gives_number("0")
        AssertExpr("<GRTR? 3 -1>").in_v3().gives_number("1")
        AssertExpr("<GRTR? 37 37>").in_v3().gives_number("0")

        # alias
        AssertExpr("<G? 3 -1>").in_v3().gives_number("1")

    def test_grtr_p_error(self):
        """Test GRTR? error cases."""
        AssertExpr("<GRTR?>").in_v3().does_not_compile()
        AssertExpr("<GRTR? 0>").in_v3().does_not_compile()
        AssertExpr("<GRTR? 0 0 0>").in_v3().does_not_compile()

    def test_geq_p(self):
        """Test G=? opcode."""
        AssertExpr("<G=? -1 3>").in_v3().gives_number("0")
        AssertExpr("<G=? 3 -1>").in_v3().gives_number("1")
        AssertExpr("<G=? 37 37>").in_v3().gives_number("1")

    def test_geq_p_error(self):
        """Test G=? error cases."""
        AssertExpr("<G=?>").in_v3().does_not_compile()
        AssertExpr("<G=? 0>").in_v3().does_not_compile()
        AssertExpr("<G=? 0 0 0>").in_v3().does_not_compile()


class TestIncDec:
    """Tests for increment/decrement opcodes."""

    def test_inc(self):
        """Test INC opcode."""
        AssertRoutine("FOO", "<INC FOO> .FOO").when_called_with("200").gives_number("201")

    def test_inc_quirks(self):
        """Test INC with variable references."""
        AssertRoutine("FOO", "<INC .FOO> .FOO").when_called_with("200").gives_number("201")
        AssertRoutine("", "<INC ,FOO> ,FOO").with_global("<GLOBAL FOO 5>").gives_number("6")

    def test_inc_error(self):
        """Test INC error cases."""
        AssertExpr("<INC>").does_not_compile()
        AssertExpr("<INC 1>").does_not_compile()
        AssertRoutine("FOO", "<INC BAR>").does_not_compile()

    def test_dec(self):
        """Test DEC opcode."""
        AssertRoutine("FOO", "<DEC FOO> .FOO").when_called_with("200").gives_number("199")

    def test_dec_quirks(self):
        """Test DEC with variable references."""
        AssertRoutine("FOO", "<DEC .FOO> .FOO").when_called_with("200").gives_number("199")
        AssertRoutine("", "<DEC ,FOO> ,FOO").with_global("<GLOBAL FOO 5>").gives_number("4")

    def test_dec_error(self):
        """Test DEC error cases."""
        AssertExpr("<DEC>").does_not_compile()
        AssertExpr("<DEC 1>").does_not_compile()
        AssertRoutine("FOO", "<DEC BAR>").does_not_compile()

    def test_igrtr_p(self):
        """Test IGRTR? opcode."""
        AssertRoutine("FOO", "<PRINTN <IGRTR? FOO 100>> <CRLF> <PRINTN .FOO>") \
            .when_called_with("100").outputs("1\n101")
        AssertRoutine("FOO", "<PRINTN <IGRTR? FOO 100>> <CRLF> <PRINTN .FOO>") \
            .when_called_with("99").outputs("0\n100")

    def test_igrtr_p_error(self):
        """Test IGRTR? error cases."""
        AssertExpr("<IGRTR?>").does_not_compile()
        AssertRoutine("FOO", "<IGRTR? FOO>").does_not_compile()
        AssertExpr("<IGRTR? 11 22>").does_not_compile()
        AssertRoutine("FOO", "<IGRTR? BAR 100>").does_not_compile()
        AssertRoutine("FOO BAR", "<IGRTR? FOO BAR>").does_not_compile()

    def test_dless_p(self):
        """Test DLESS? opcode."""
        AssertRoutine("FOO", "<PRINTN <DLESS? FOO 100>> <CRLF> <PRINTN .FOO>") \
            .when_called_with("100").outputs("1\n99")
        AssertRoutine("FOO", "<PRINTN <DLESS? FOO 100>> <CRLF> <PRINTN .FOO>") \
            .when_called_with("101").outputs("0\n100")

    def test_dless_p_error(self):
        """Test DLESS? error cases."""
        AssertExpr("<DLESS?>").does_not_compile()
        AssertRoutine("FOO", "<DLESS? FOO>").does_not_compile()
        AssertExpr("<DLESS? 11 22>").does_not_compile()
        AssertRoutine("FOO", "<DLESS? BAR 100>").does_not_compile()
        AssertRoutine("FOO BAR", "<DLESS? FOO BAR>").does_not_compile()


class TestApply:
    """Tests for APPLY opcode."""

    def test_apply(self):
        """Test APPLY opcode."""
        AssertExpr("<APPLY 0>").gives_number("0")
        AssertExpr("<APPLY 0 1 2 3>").gives_number("0")
        AssertExpr("<APPLY 0 1 2 3 4 5 6 7>").in_v5().gives_number("0")

        AssertRoutine('"AUX" X', "<SET X ,OTHER-ROUTINE> <APPLY .X 12>") \
            .with_global("<ROUTINE OTHER-ROUTINE (N) <* .N 2>>") \
            .gives_number("24")

    def test_apply_chooses_value_call_for_pred(self):
        """Test that APPLY uses value-context version in predicate context (V5)."""
        # V5 has void-context and value-context versions of APPLY.
        # The void-context version is always true in predicate context,
        # so we need to prefer the value-context version.
        AssertRoutine('"AUX" X', "<SET X ,FALSE-ROUTINE> <COND (<APPLY .X> 123) (T 456)>") \
            .in_v5() \
            .with_global("<ROUTINE FALSE-ROUTINE () 0>") \
            .gives_number("456")

        AssertRoutine('"AUX" X', "<SET X ,FALSE-ROUTINE> <COND (<NOT <APPLY .X>> 123) (T 456)>") \
            .in_v5() \
            .with_global("<ROUTINE FALSE-ROUTINE () 0>") \
            .gives_number("123")

    def test_apply_error(self):
        """Test APPLY error cases."""
        AssertExpr("<APPLY>").does_not_compile()
        AssertExpr("<APPLY 0 1 2 3 4>").in_v3().does_not_compile()
        AssertExpr("<APPLY 0 1 2 3 4 5 6 7 8>").in_v5().does_not_compile()


class TestReturn:
    """Tests for return opcodes."""

    def test_return(self):
        """Test RETURN opcode."""
        AssertRoutine("", "<RETURN 123>").gives_number("123")

    def test_return_error(self):
        """Test RETURN error cases."""
        AssertExpr("<RETURN 0 0>").in_v3().does_not_compile()

    def test_rfalse(self):
        """Test RFALSE opcode."""
        AssertRoutine("", "<RFALSE>").gives_number("0")

    def test_rfalse_error(self):
        """Test RFALSE error cases."""
        AssertExpr("<RFALSE 0>").in_v3().does_not_compile()
        AssertExpr("<RFALSE 0 0>").in_v3().does_not_compile()

    def test_rtrue(self):
        """Test RTRUE opcode."""
        AssertRoutine("", "<RTRUE>").gives_number("1")

    def test_rtrue_error(self):
        """Test RTRUE error cases."""
        AssertExpr("<RTRUE 0>").in_v3().does_not_compile()

    def test_rstack(self):
        """Test RSTACK opcode."""
        AssertRoutine("", "<PUSH 1234> <RSTACK>").gives_number("1234")

    def test_rstack_error(self):
        """Test RSTACK error cases."""
        AssertExpr("<RSTACK 0>").in_v3().does_not_compile()


class TestStack:
    """Tests for stack opcodes."""

    def test_push(self):
        """Test PUSH opcode."""
        AssertRoutine("", "<PUSH 123> <POP>").gives_number("123")

    def test_push_error(self):
        """Test PUSH error cases."""
        AssertExpr("<PUSH>").does_not_compile()
        AssertExpr("<PUSH 0 0>").does_not_compile()

    def test_pop(self):
        """Test POP opcode."""
        AssertRoutine("", "<PUSH 456> <POP>").gives_number("456")

    def test_pop_error(self):
        """Test POP error cases."""
        AssertExpr("<POP 0>").does_not_compile()


class TestCatchThrow:
    """Tests for CATCH/THROW opcodes (V5+)."""

    def test_catch(self):
        """Test CATCH opcode - V5+ only."""
        # The return value is unpredictable, just test it compiles
        AssertExpr("<CATCH>").in_v5().compiles()

    def test_catch_error(self):
        """Test CATCH error cases."""
        AssertExpr("<CATCH>").in_v3().does_not_compile()
        AssertExpr("<CATCH>").in_v4().does_not_compile()
        AssertExpr("<CATCH 123>").in_v5().does_not_compile()

    def test_throw(self):
        """Test THROW opcode - V5+ only."""
        AssertRoutine('"AUX" X', "<SET X <CATCH>> <THROWER .X> 123") \
            .in_v5() \
            .with_global("<ROUTINE THROWER (F) <THROW 456 .F>>") \
            .gives_number("456")

    def test_throw_error(self):
        """Test THROW error cases."""
        # Not available in V4 and below
        AssertExpr("<THROW 0 0>").in_v4().does_not_compile()

        # Wrong number of arguments
        AssertExpr("<THROW>").in_v5().does_not_compile()
        AssertExpr("<THROW 0>").in_v5().does_not_compile()
        AssertExpr("<THROW 0 0 0>").in_v5().does_not_compile()


class TestAssigned:
    """Tests for ASSIGNED? opcode (V5+)."""

    def test_assigned_p(self):
        """Test ASSIGNED? opcode."""
        AssertRoutine("X", "<ASSIGNED? X>").in_v5() \
            .when_called_with("999").gives_number("1")
        AssertRoutine('"OPT" X', "<ASSIGNED? X>").in_v5() \
            .when_called_with("0").gives_number("1")
        AssertRoutine('"OPT" X', "<ASSIGNED? X>").in_v5() \
            .when_called_with("").gives_number("0")

    def test_assigned_p_error(self):
        """Test ASSIGNED? error cases."""
        AssertRoutine("X", "<ASSIGNED? Y>").in_v5().does_not_compile()
        AssertRoutine("X", "<ASSIGNED? 1>").in_v5().does_not_compile()
        AssertRoutine("X", "<ASSIGNED?>").in_v5().does_not_compile()
        AssertRoutine("X", "<ASSIGNED? X X>").in_v5().does_not_compile()


class TestObjects:
    """Tests for object opcodes."""

    def test_first_p(self):
        """Test FIRST? opcode."""
        AssertExpr("<FIRST? ,MYOBJECT>") \
            .with_global("<OBJECT MYOBJECT>") \
            .gives_number("0")

        AssertExpr("<==? <FIRST? ,MYOBJECT> ,INNEROBJECT>") \
            .with_global("<OBJECT MYOBJECT>") \
            .with_global("<OBJECT INNEROBJECT (LOC MYOBJECT)>") \
            .gives_number("1")

        AssertExpr('<COND (<FIRST? ,MYOBJECT> <PRINTI "yes">)>') \
            .with_global("<OBJECT MYOBJECT>") \
            .with_global("<OBJECT INNEROBJECT (LOC MYOBJECT)>") \
            .outputs("yes")

        AssertExpr('<COND (<FIRST? ,INNEROBJECT> <PRINTI "yes">) (T <PRINTI "no">)>') \
            .with_global("<OBJECT MYOBJECT>") \
            .with_global("<OBJECT INNEROBJECT (LOC MYOBJECT)>") \
            .outputs("no")

    def test_first_p_error(self):
        """Test FIRST? error cases."""
        AssertExpr("<FIRST?>").does_not_compile()
        AssertExpr("<FIRST? 0 0>").does_not_compile()

    def test_next_p(self):
        """Test NEXT? opcode."""
        AssertExpr("<NEXT? ,MYOBJECT>") \
            .with_global("<OBJECT MYOBJECT>") \
            .gives_number("0")

    def test_next_p_error(self):
        """Test NEXT? error cases."""
        AssertExpr("<NEXT?>").does_not_compile()
        AssertExpr("<NEXT? 0 0>").does_not_compile()

    def test_in_p(self):
        """Test IN? opcode."""
        AssertExpr("<COND (<IN? ,CAT ,HAT> 123) (T 456)>") \
            .with_global("<OBJECT HAT>") \
            .with_global("<OBJECT CAT (LOC HAT)>") \
            .gives_number("123")

        AssertExpr("<COND (<IN? ,CAT ,HAT> 123) (T 456)>") \
            .with_global("<OBJECT HAT (LOC CAT)>") \
            .with_global("<OBJECT CAT>") \
            .gives_number("456")

    def test_in_p_error(self):
        """Test IN? error cases."""
        AssertExpr("<IN?>").in_v3().does_not_compile()
        AssertExpr("<IN? 0>").in_v3().does_not_compile()
        AssertExpr("<IN? 0 0 0>").in_v3().does_not_compile()

    def test_loc(self):
        """Test LOC opcode."""
        AssertExpr("<==? <LOC ,CAT> ,HAT>") \
            .with_global("<OBJECT HAT>") \
            .with_global("<OBJECT CAT (LOC HAT)>") \
            .gives_number("1")

    def test_loc_error(self):
        """Test LOC error cases."""
        AssertExpr("<LOC>").does_not_compile()
        AssertExpr("<LOC 0 0>").does_not_compile()

    def test_move(self):
        """Test MOVE opcode."""
        AssertExpr("<MOVE ,CAT ,BOX> <IN? ,CAT ,BOX>") \
            .with_global("<OBJECT HAT>") \
            .with_global("<OBJECT BOX>") \
            .with_global("<OBJECT CAT (LOC HAT)>") \
            .gives_number("1")

    def test_move_error(self):
        """Test MOVE error cases."""
        AssertExpr("<MOVE>").does_not_compile()
        AssertExpr("<MOVE 0>").does_not_compile()
        AssertExpr("<MOVE 0 0 0>").does_not_compile()

    def test_remove(self):
        """Test REMOVE opcode."""
        AssertExpr("<REMOVE ,CAT> <LOC ,CAT>") \
            .with_global("<OBJECT HAT>") \
            .with_global("<OBJECT CAT (LOC HAT)>") \
            .gives_number("0")

    def test_remove_error(self):
        """Test REMOVE error cases."""
        AssertExpr("<REMOVE>").does_not_compile()
        AssertExpr("<REMOVE 0 0>").does_not_compile()

    def test_fset(self):
        """Test FSET opcode."""
        AssertExpr("<FSET ,MYOBJECT ,FOOBIT>") \
            .with_global("<OBJECT MYOBJECT (FLAGS FOOBIT)>") \
            .gives_number("1")

    def test_fset_error(self):
        """Test FSET error cases."""
        AssertExpr("<FSET>").does_not_compile()
        AssertExpr("<FSET 0>").does_not_compile()
        AssertExpr("<FSET 0 1 2>").does_not_compile()

    def test_fset_p(self):
        """Test FSET? opcode."""
        AssertRoutine("", "<PRINTN <FSET? ,OBJECT1 FOOBIT>> <CRLF> <PRINTN <FSET? ,OBJECT2 FOOBIT>>") \
            .with_global("<OBJECT OBJECT1 (FLAGS FOOBIT)>") \
            .with_global("<OBJECT OBJECT2>") \
            .outputs("1\n0")

    def test_fset_p_error(self):
        """Test FSET? error cases."""
        AssertExpr("<FSET?>").does_not_compile()
        AssertExpr("<FSET? 0>").does_not_compile()
        AssertExpr("<FSET? 0 1 2>").does_not_compile()

    def test_fclear(self):
        """Test FCLEAR opcode."""
        AssertExpr("<FCLEAR ,MYOBJECT ,FOOBIT>") \
            .with_global("<OBJECT MYOBJECT (FLAGS FOOBIT)>") \
            .gives_number("1")

    def test_fclear_error(self):
        """Test FCLEAR error cases."""
        AssertExpr("<FCLEAR>").does_not_compile()
        AssertExpr("<FCLEAR 1>").does_not_compile()
        AssertExpr("<FCLEAR 1 2 3>").does_not_compile()


class TestProperties:
    """Tests for property opcodes."""

    def test_getp(self):
        """Test GETP opcode."""
        AssertExpr("<GETP ,MYOBJECT ,P?MYPROP>") \
            .with_global("<OBJECT MYOBJECT (MYPROP 123)>") \
            .gives_number("123")

        AssertExpr("<GETP ,OBJECT2 ,P?MYPROP>") \
            .with_global("<OBJECT OBJECT1 (MYPROP 1)>") \
            .with_global("<OBJECT OBJECT2>") \
            .gives_number("0")

    def test_getp_error(self):
        """Test GETP error cases."""
        AssertExpr("<GETP>").in_v3().does_not_compile()
        AssertExpr("<GETP 0>").in_v3().does_not_compile()
        AssertExpr("<GETP 0 0 0>").in_v3().does_not_compile()

    def test_getpt(self):
        """Test GETPT opcode."""
        AssertExpr("<GET <GETPT ,MYOBJECT ,P?MYPROP> 0>") \
            .with_global("<OBJECT MYOBJECT (MYPROP 123)>") \
            .gives_number("123")

        AssertExpr("<GETPT ,OBJECT2 ,P?MYPROP>") \
            .with_global("<OBJECT OBJECT1 (MYPROP 1)>") \
            .with_global("<OBJECT OBJECT2>") \
            .gives_number("0")

    def test_getpt_error(self):
        """Test GETPT error cases."""
        AssertExpr("<GETPT>").in_v3().does_not_compile()
        AssertExpr("<GETPT 0>").in_v3().does_not_compile()
        AssertExpr("<GETPT 0 0 0>").in_v3().does_not_compile()

    def test_putp(self):
        """Test PUTP opcode."""
        AssertExpr("<PUTP ,MYOBJECT ,P?MYPROP 456> <GETP ,MYOBJECT ,P?MYPROP>") \
            .with_global("<OBJECT MYOBJECT (MYPROP 123)>") \
            .gives_number("456")

    def test_putp_error(self):
        """Test PUTP error cases."""
        AssertExpr("<PUTP>").in_v3().does_not_compile()
        AssertExpr("<PUTP 0>").in_v3().does_not_compile()
        AssertExpr("<PUTP 0 0>").in_v3().does_not_compile()
        AssertExpr("<PUTP 0 0 0 0>").in_v3().does_not_compile()

    def test_nextp(self):
        """Test NEXTP opcode."""
        AssertExpr("<NEXTP ,MYOBJECT 0>") \
            .with_global("<OBJECT MYOBJECT (MYPROP 123)>") \
            .compiles()

    def test_nextp_error(self):
        """Test NEXTP error cases."""
        AssertExpr("<NEXTP>").in_v3().does_not_compile()
        AssertExpr("<NEXTP 0>").in_v3().does_not_compile()
        AssertExpr("<NEXTP 0 0 0>").in_v3().does_not_compile()

    def test_ptsize(self):
        """Test PTSIZE opcode."""
        AssertExpr("<PTSIZE <GETPT ,MYOBJECT ,P?MYPROP>>") \
            .with_global("<OBJECT MYOBJECT (MYPROP 123)>") \
            .gives_number("2")

    def test_ptsize_error(self):
        """Test PTSIZE error cases."""
        AssertExpr("<PTSIZE>").in_v3().does_not_compile()
        AssertExpr("<PTSIZE 0 0>").in_v3().does_not_compile()


class TestMemory:
    """Tests for memory opcodes."""

    def test_get(self):
        """Test GET opcode."""
        AssertExpr("<GET 0 0>").in_v3().compiles()

    def test_get_error(self):
        """Test GET error cases."""
        AssertExpr("<GET>").in_v3().does_not_compile()
        AssertExpr("<GET 0>").in_v3().does_not_compile()
        AssertExpr("<GET 0 0 0>").in_v3().does_not_compile()

    def test_getb(self):
        """Test GETB opcode."""
        AssertExpr("<GETB 0 0>").in_v3().gives_number("3")  # Version byte

    def test_getb_error(self):
        """Test GETB error cases."""
        AssertExpr("<GETB>").in_v3().does_not_compile()
        AssertExpr("<GETB 0>").in_v3().does_not_compile()
        AssertExpr("<GETB 0 0 0>").in_v3().does_not_compile()

    def test_put(self):
        """Test PUT opcode."""
        AssertRoutine("", "<PUT ,TABLE1 0 999> <GET ,TABLE1 0>") \
            .with_global("<GLOBAL TABLE1 <TABLE 0 0 0>>") \
            .gives_number("999")

    def test_put_error(self):
        """Test PUT error cases."""
        AssertExpr("<PUT>").in_v3().does_not_compile()
        AssertExpr("<PUT 0>").in_v3().does_not_compile()
        AssertExpr("<PUT 0 0>").in_v3().does_not_compile()
        AssertExpr("<PUT 0 0 0 0>").in_v3().does_not_compile()

    def test_putb(self):
        """Test PUTB opcode."""
        AssertRoutine("", "<PUTB ,TABLE1 0 99> <GETB ,TABLE1 0>") \
            .with_global("<GLOBAL TABLE1 <TABLE (BYTE) 0 0 0>>") \
            .gives_number("99")

    def test_putb_error(self):
        """Test PUTB error cases."""
        AssertExpr("<PUTB>").in_v3().does_not_compile()
        AssertExpr("<PUTB 0>").in_v3().does_not_compile()
        AssertExpr("<PUTB 0 0>").in_v3().does_not_compile()
        AssertExpr("<PUTB 0 0 0 0>").in_v3().does_not_compile()

    def test_copyt(self):
        """Test COPYT opcode - V5+ only."""
        AssertRoutine("", "<COPYT ,TABLE1 ,TABLE2 6> <GET ,TABLE2 2>") \
            .in_v5() \
            .with_global("<GLOBAL TABLE1 <TABLE 1 2 3>>") \
            .with_global("<GLOBAL TABLE2 <TABLE 0 0 0>>") \
            .gives_number("3")

    def test_copyt_error(self):
        """Test COPYT error cases."""
        # Not available in V3/V4
        AssertExpr("<COPYT 0 0 0>").in_v3().does_not_compile()
        AssertExpr("<COPYT 0 0 0>").in_v4().does_not_compile()

        # Wrong number of arguments
        AssertExpr("<COPYT>").in_v5().does_not_compile()
        AssertExpr("<COPYT 0>").in_v5().does_not_compile()
        AssertExpr("<COPYT 0 0>").in_v5().does_not_compile()
        AssertExpr("<COPYT 0 0 0 0>").in_v5().does_not_compile()


class TestVariables:
    """Tests for variable opcodes."""

    def test_set(self):
        """Test SET opcode."""
        AssertRoutine('"AUX" FOO', "<SET FOO 111> .FOO").gives_number("111")
        AssertRoutine("", "<SET FOO 111> ,FOO") \
            .with_global("<GLOBAL FOO 0>") \
            .gives_number("111")

        # value version
        AssertRoutine('"AUX" FOO', "<PRINTN <SET FOO 111>>").outputs("111")

        # void version
        AssertRoutine('"AUX" FOO', "<SET 1 111> <PRINTN .FOO>").outputs("111")

        # alias: SETG
        AssertRoutine('"AUX" FOO', "<SETG FOO 111> .FOO").gives_number("111")
        AssertRoutine("", "<SETG FOO 111> ,FOO") \
            .with_global("<GLOBAL FOO 0>") \
            .gives_number("111")

    def test_set_error(self):
        """Test SET error cases."""
        AssertExpr("<SET>").does_not_compile()
        AssertRoutine("X", "<SET X>").does_not_compile()
        AssertExpr("<SET 1 2>").does_not_compile()
        AssertRoutine("X", "<SET Y 1>").does_not_compile()

    def test_value(self):
        """Test VALUE opcode."""
        AssertRoutine('"AUX" (X 123)', "<VALUE X>").gives_number("123")
        AssertExpr("<VALUE G>") \
            .with_global("<GLOBAL G 123>") \
            .gives_number("123")
        AssertRoutine("", "<PUSH 1234> <VALUE 0>").gives_number("1234")

    def test_value_error(self):
        """Test VALUE error cases."""
        AssertExpr("<VALUE>").does_not_compile()
        AssertExpr("<VALUE 0 0>").does_not_compile()
        AssertExpr("<VALUE ASDF>").does_not_compile()


class TestPrint:
    """Tests for print opcodes."""

    def test_print(self):
        """Test PRINT opcode."""
        AssertExpr('<PRINT "hello">').outputs("hello")

    def test_print_error(self):
        """Test PRINT error cases."""
        AssertExpr("<PRINT>").does_not_compile()

    def test_printi(self):
        """Test PRINTI opcode."""
        AssertExpr('<PRINTI "hello">').outputs("hello")

    def test_printi_error(self):
        """Test PRINTI error cases."""
        AssertExpr("<PRINTI>").does_not_compile()

    def test_printn(self):
        """Test PRINTN opcode."""
        AssertExpr("<PRINTN 42>").outputs("42")
        AssertExpr("<PRINTN -1>").outputs("-1")

    def test_printn_error(self):
        """Test PRINTN error cases."""
        AssertExpr("<PRINTN>").does_not_compile()
        AssertExpr("<PRINTN 0 0>").does_not_compile()

    def test_printc(self):
        """Test PRINTC opcode."""
        AssertExpr("<PRINTC 65>").outputs("A")

    def test_printc_error(self):
        """Test PRINTC error cases."""
        AssertExpr("<PRINTC>").does_not_compile()
        AssertExpr("<PRINTC 0 0>").does_not_compile()

    def test_printd(self):
        """Test PRINTD opcode."""
        AssertExpr("<PRINTD ,MYOBJECT>") \
            .with_global('<OBJECT MYOBJECT (DESC "my object")>') \
            .outputs("my object")

    def test_printd_error(self):
        """Test PRINTD error cases."""
        AssertExpr("<PRINTD>").does_not_compile()
        AssertExpr("<PRINTD 0 0>").does_not_compile()

    def test_printr(self):
        """Test PRINTR opcode."""
        AssertRoutine("", '<PRINTR "hi"> 456').gives_number("1")

    def test_crlf(self):
        """Test CRLF opcode."""
        AssertExpr("<CRLF>").outputs("\n")

    def test_crlf_error(self):
        """Test CRLF error cases."""
        AssertExpr("<CRLF 1>").does_not_compile()


class TestIO:
    """Tests for I/O opcodes."""

    def test_dirin(self):
        """Test DIRIN opcode."""
        AssertExpr("<DIRIN 0>").gives_number("1")

    def test_dirin_error(self):
        """Test DIRIN error cases."""
        AssertExpr("<DIRIN>").does_not_compile()
        AssertExpr("<DIRIN 0 0>").does_not_compile()

    def test_dirout(self):
        """Test DIROUT opcode."""
        AssertExpr("<DIROUT 1>").gives_number("1")

        # output stream 3 needs a table
        AssertRoutine("", '<DIROUT 3 ,OUTTABLE> <PRINTI "A"> <DIROUT -3> <GETB ,OUTTABLE 2>') \
            .with_global("<GLOBAL OUTTABLE <LTABLE (BYTE) 0 0 0 0 0 0 0 0>>") \
            .gives_number("65")

    def test_dirout_v6(self):
        """Test DIROUT with third operand (V6)."""
        AssertExpr("<DIROUT 3 0 0>").in_v6().compiles()

    def test_dirout_error(self):
        """Test DIROUT error cases."""
        AssertExpr("<DIROUT>").does_not_compile()
        AssertExpr("<DIROUT 3 0 0>").in_v5().does_not_compile()

    def test_bufout(self):
        """Test BUFOUT opcode - V4+ only."""
        # We can't really test its side-effect here
        AssertExpr("<BUFOUT 0>").in_v4().gives_number("1")

    def test_bufout_error(self):
        """Test BUFOUT error cases."""
        AssertExpr("<BUFOUT 0>").in_v3().does_not_compile()
        AssertExpr("<BUFOUT>").in_v4().does_not_compile()
        AssertExpr("<BUFOUT 0 1>").in_v4().does_not_compile()


class TestScreen:
    """Tests for screen opcodes."""

    def test_screen(self):
        """Test SCREEN opcode."""
        AssertExpr("<SCREEN 0>").in_v3().compiles()

    def test_screen_error(self):
        """Test SCREEN error cases."""
        AssertExpr("<SCREEN>").in_v3().does_not_compile()
        AssertExpr("<SCREEN 0 0>").in_v3().does_not_compile()

    def test_split(self):
        """Test SPLIT opcode."""
        AssertExpr("<SPLIT 1>").in_v3().compiles()

    def test_split_error(self):
        """Test SPLIT error cases."""
        AssertExpr("<SPLIT>").in_v3().does_not_compile()
        AssertExpr("<SPLIT 0 0>").in_v3().does_not_compile()

    def test_clear(self):
        """Test CLEAR opcode - V4+ only."""
        # We can't really test its side-effect here
        AssertExpr("<CLEAR 0>").in_v4().gives_number("1")

    def test_clear_error(self):
        """Test CLEAR error cases."""
        AssertExpr("<CLEAR 0>").in_v3().does_not_compile()
        AssertExpr("<CLEAR>").in_v4().does_not_compile()
        AssertExpr("<CLEAR 0 1>").in_v4().does_not_compile()

    def test_erase(self):
        """Test ERASE opcode - V4+ only."""
        # We can't really test its side-effect here
        AssertExpr("<ERASE 1>").in_v4().gives_number("1")

    def test_erase_error(self):
        """Test ERASE error cases."""
        AssertExpr("<ERASE 1>").in_v3().does_not_compile()
        AssertExpr("<ERASE>").in_v4().does_not_compile()
        AssertExpr("<ERASE 1 2>").in_v4().does_not_compile()

    def test_curset(self):
        """Test CURSET opcode - V4+ only."""
        # We can't really test its side-effect here
        AssertExpr("<CURSET 1 1>").in_v4().gives_number("1")

    def test_curset_error(self):
        """Test CURSET error cases."""
        AssertExpr("<CURSET 1 1>").in_v3().does_not_compile()
        AssertExpr("<CURSET>").in_v4().does_not_compile()
        AssertExpr("<CURSET 1>").in_v4().does_not_compile()
        AssertExpr("<CURSET 1 1 1>").in_v4().does_not_compile()

    def test_curget(self):
        """Test CURGET opcode - V4+ only."""
        # Needs a table
        AssertExpr("<CURGET ,CURTABLE>") \
            .in_v4() \
            .with_global("<GLOBAL CURTABLE <TABLE 0 0>>") \
            .compiles()

    def test_curget_error(self):
        """Test CURGET error cases."""
        AssertExpr("<CURGET 0>").in_v3().does_not_compile()
        AssertExpr("<CURGET>").in_v4().does_not_compile()
        AssertExpr("<CURGET 0 0>").in_v4().does_not_compile()

    def test_hlight(self):
        """Test HLIGHT opcode - V4+ only."""
        AssertExpr("<HLIGHT 4>").in_v4().compiles()

    def test_hlight_error(self):
        """Test HLIGHT error cases."""
        AssertExpr("<HLIGHT>").in_v3().does_not_compile()
        AssertExpr("<HLIGHT>").in_v4().does_not_compile()
        AssertExpr("<HLIGHT 0 0>").in_v4().does_not_compile()

    def test_color(self):
        """Test COLOR opcode - V5+ only."""
        # We can't really test its side-effect here
        AssertExpr("<COLOR 5 5>").in_v5().gives_number("1")

    def test_color_error(self):
        """Test COLOR error cases."""
        AssertExpr("<COLOR 5 5>").in_v3().does_not_compile()
        AssertExpr("<COLOR 5 5>").in_v4().does_not_compile()
        AssertExpr("<COLOR 5 5 1>").in_v5().does_not_compile()
        AssertExpr("<COLOR>").in_v5().does_not_compile()
        AssertExpr("<COLOR 5>").in_v5().does_not_compile()

    def test_font(self):
        """Test FONT opcode - V5+ only."""
        AssertExpr("<FONT 1>").in_v5().compiles()

    def test_font_error(self):
        """Test FONT error cases."""
        AssertExpr("<FONT 1>").in_v3().does_not_compile()
        AssertExpr("<FONT 1>").in_v4().does_not_compile()
        AssertExpr("<FONT>").in_v5().does_not_compile()
        AssertExpr("<FONT 1 2>").in_v5().does_not_compile()


class TestMisc:
    """Tests for miscellaneous opcodes."""

    def test_random(self):
        """Test RANDOM opcode."""
        # Just test it compiles; output is unpredictable
        AssertExpr("<RANDOM 100>").compiles()

    def test_random_error(self):
        """Test RANDOM error cases."""
        AssertExpr("<RANDOM>").does_not_compile()
        AssertExpr("<RANDOM 0 0>").does_not_compile()

    def test_verify(self):
        """Test VERIFY opcode."""
        AssertExpr("<VERIFY>").in_v3().gives_number("1")

    def test_verify_error(self):
        """Test VERIFY error cases."""
        AssertExpr("<VERIFY 0>").in_v3().does_not_compile()

    def test_save(self):
        """Test SAVE opcode."""
        AssertExpr("<SAVE>").in_v3().compiles()
        AssertExpr("<SAVE>").in_v4().compiles()
        AssertExpr("<SAVE>").in_v5().compiles()
        AssertExpr("<SAVE 0 0 0>").in_v5().compiles()

    def test_save_error(self):
        """Test SAVE error cases."""
        AssertExpr("<SAVE 0>").in_v3().does_not_compile()
        AssertExpr("<SAVE 0>").in_v4().does_not_compile()
        AssertExpr("<SAVE 0>").in_v5().does_not_compile()
        AssertExpr("<SAVE 0 0>").in_v5().does_not_compile()
        AssertExpr("<SAVE 0 0 0 0>").in_v5().does_not_compile()

    def test_restore(self):
        """Test RESTORE opcode."""
        AssertExpr("<RESTORE>").in_v3().compiles()
        AssertExpr("<RESTORE>").in_v4().compiles()
        AssertExpr("<RESTORE>").in_v5().compiles()
        AssertExpr("<RESTORE 0 0 0>").in_v5().compiles()

    def test_restore_error(self):
        """Test RESTORE error cases."""
        AssertExpr("<RESTORE 0>").in_v3().does_not_compile()
        AssertExpr("<RESTORE 0>").in_v4().does_not_compile()
        AssertExpr("<RESTORE 0>").in_v5().does_not_compile()
        AssertExpr("<RESTORE 0 0>").in_v5().does_not_compile()
        AssertExpr("<RESTORE 0 0 0 0>").in_v5().does_not_compile()

    def test_restart(self):
        """Test RESTART opcode."""
        AssertExpr("<RESTART>").compiles()

    def test_restart_error(self):
        """Test RESTART error cases."""
        AssertExpr("<RESTART 0>").does_not_compile()

    def test_quit(self):
        """Test QUIT opcode."""
        AssertExpr("<QUIT>").compiles()

    def test_quit_error(self):
        """Test QUIT error cases."""
        AssertExpr("<QUIT 0>").does_not_compile()

    def test_checku(self):
        """Test CHECKU opcode - V5+ only."""
        # Only the lower 2 bits of the return value are defined
        AssertExpr("<BAND 3 <CHECKU 65>>").in_v5().gives_number("3")

    def test_checku_error(self):
        """Test CHECKU error cases."""
        AssertExpr("<CHECKU 65>").in_v3().does_not_compile()
        AssertExpr("<CHECKU 65>").in_v4().does_not_compile()
        AssertExpr("<CHECKU>").in_v5().does_not_compile()
        AssertExpr("<CHECKU 65 66>").in_v5().does_not_compile()

    def test_sound(self):
        """Test SOUND opcode."""
        AssertExpr("<SOUND 0>").in_v3().compiles()
        AssertExpr("<SOUND 0 0>").in_v3().compiles()
        AssertExpr("<SOUND 0 0 0>").in_v3().compiles()
        AssertExpr("<SOUND 0>").in_v5().compiles()
        AssertExpr("<SOUND 0 0>").in_v5().compiles()
        AssertExpr("<SOUND 0 0 0>").in_v5().compiles()
        AssertExpr("<SOUND 0 0 0 0>").in_v5().compiles()

    def test_sound_error(self):
        """Test SOUND error cases."""
        AssertExpr("<SOUND>").in_v3().does_not_compile()
        AssertExpr("<SOUND 0 0 0 0>").in_v3().does_not_compile()
        AssertExpr("<SOUND>").in_v5().does_not_compile()
        AssertExpr("<SOUND 0 0 0 0 0>").in_v5().does_not_compile()

    def test_usl(self):
        """Test USL opcode - V3 only."""
        AssertExpr("<USL>").in_v3().compiles()

    def test_usl_error(self):
        """Test USL error cases."""
        AssertExpr("<USL 0>").in_v3().does_not_compile()
        AssertExpr("<USL>").in_v4().does_not_compile()


class TestInput:
    """Tests for input opcodes."""

    def test_input(self):
        """Test INPUT opcode - V4+ only."""
        AssertExpr("<INPUT 1 0>").in_v4().compiles()
        AssertExpr("<INPUT 1 0 0>").in_v4().compiles()

    def test_input_error(self):
        """Test INPUT error cases."""
        AssertExpr("<INPUT 1>").in_v3().does_not_compile()
        AssertExpr("<INPUT>").in_v4().does_not_compile()
        AssertExpr("<INPUT 0 0 0 0>").in_v4().does_not_compile()


class TestLowcore:
    """Tests for LOWCORE pseudo-opcode."""

    def test_lowcore(self):
        """Test LOWCORE pseudo-opcode."""
        AssertRoutine("", "<LOWCORE FLAGS>") \
            .generates_code_matching(r"^\s*GET 0,8 >STACK\s*$")
        AssertRoutine("", "<LOWCORE FLAGS 123>") \
            .generates_code_matching(r"^\s*PUT 0,8,123")

    def test_lowcore_extension(self):
        """Test LOWCORE with extension table."""
        AssertRoutine('"AUX" X', "<SET X <LOWCORE MSLOCY>> <LOWCORE MSETBL 12345>") \
            .in_v5() \
            .implies(
                "<T? <LOWCORE EXTAB>>",
                "<G=? <GET <LOWCORE EXTAB> 0> 2>"
            )

    def test_lowcore_subfield(self):
        """Test LOWCORE with subfield access."""
        AssertRoutine('"AUX" X', "<SET X <LOWCORE (ZVERSION 1)>>").compiles()
        AssertRoutine("", "<LOWCORE (FLAGS 1) 123>").compiles()
