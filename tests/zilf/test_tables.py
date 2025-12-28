# ZILF Table Tests for Zorkie
# ===========================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/TableTests.cs
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
Tests for ZIL table constructs.

These tests verify that the zorkie compiler correctly handles:
- TABLE with various element types (BYTE, WORD)
- ITABLE initialization
- LTABLE (length-prefixed tables)
- Table patterns and flags (PURE, PARSER-TABLE)
- Compile-time table manipulation (ZPUT, ZREST)
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals


class TestTableElements:
    """Tests for table element types."""

    def test_byte_elements_compile_as_bytes(self):
        """Test that BYTE elements compile as bytes."""
        AssertGlobals("<GLOBAL TBL <TABLE 12345 #BYTE 123 #BYTE 45>>") \
            .implies(
                "<==? <GET ,TBL 0> 12345>",
                "<==? <GETB ,TBL 2> 123>",
                "<==? <GETB ,TBL 3> 45>"
            )

    def test_word_elements_compile_as_words(self):
        """Test that WORD elements compile as words."""
        AssertGlobals("<GLOBAL TBL <TABLE (BYTE) #WORD (12345) 123 45>>") \
            .implies(
                "<==? <GET ,TBL 0> 12345>",
                "<==? <GETB ,TBL 2> 123>",
                "<==? <GETB ,TBL 3> 45>"
            )


class TestITABLE:
    """Tests for ITABLE construct."""

    def test_itable_multi_element_initializers_repeat_n_times(self):
        """Test that ITABLE multi-element initializers repeat."""
        AssertGlobals(
            "<GLOBAL TBL1 <ITABLE 2 1 2 3>>",
            "<GLOBAL TBL2 <ITABLE 3 9 8 7 6>>"
        ).implies(
            "<==? <GET ,TBL1 0> 1>",
            "<==? <GET ,TBL1 1> 2>",
            "<==? <GET ,TBL1 2> 3>",
            "<==? <GET ,TBL1 3> 1>",
            "<==? <GET ,TBL1 4> 2>",
            "<==? <GET ,TBL1 5> 3>"
        )

    def test_itable_lexv_warns_if_not_multiple_of_3(self):
        """Test that ITABLE LEXV warns if not multiple of 3 elements."""
        AssertGlobals("<CONSTANT LEXBUF <ITABLE 1 (LEXV) 0 0>>") \
            .with_warnings("MDL0428") \
            .compiles()

        AssertGlobals("<CONSTANT LEXBUF <ITABLE 1 (LEXV)>>") \
            .with_warnings("MDL0428") \
            .compiles()

        AssertGlobals("<CONSTANT LEXBUF <ITABLE 3 (LEXV)>>") \
            .without_warnings() \
            .compiles()


class TestTablePatterns:
    """Tests for table patterns."""

    @pytest.mark.xfail(reason="Table PATTERN not implemented")
    def test_table_pattern_affects_element_sizes(self):
        """Test that PATTERN affects element sizes."""
        AssertGlobals(
            "<GLOBAL TBL <TABLE (PATTERN (BYTE WORD BYTE BYTE [REST WORD])) 1 2 3 4 5 6>>"
        ).implies(
            "<==? <GETB ,TBL 0> 1>",
            "<==? <GET <REST ,TBL 1> 0> 2>",
            "<==? <GETB ,TBL 3> 3>",
            "<==? <GETB ,TBL 4> 4>",
            "<==? <GET <REST ,TBL 5> 0> 5>",
            "<==? <GET <REST ,TBL 5> 1> 6>"
        )


class TestPureTable:
    """Tests for pure (read-only) tables."""

    def test_pure_itable_in_pure_memory(self):
        """Test that PURE ITABLE is in pure memory."""
        AssertGlobals("<GLOBAL TBL <ITABLE 10 (PURE)>>") \
            .implies("<G=? ,TBL <LOWCORE PURBOT>>")


class TestCompileTimeTableManipulation:
    """Tests for compile-time table manipulation."""

    @pytest.mark.xfail(reason="ZPUT compile-time table manipulation not implemented")
    def test_table_mutable_at_compile_time(self):
        """Test that TABLE is mutable at compile time."""
        AssertGlobals(
            "<SETG MY-TBL <TABLE 0 <BYTE 0>>>",
            "<ZPUT ,MY-TBL 0 1>",
            "<PUTB ,MY-TBL 2 2>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies(
            "<==? <GET ,TBL 0> 1>",
            "<==? <GETB ,TBL 2> 2>"
        )

        AssertGlobals(
            "<SETG MY-TBL <ITABLE 3 <>>>",
            "<ZPUT ,MY-TBL 1 1>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies("<==? <GET ,TBL 1> 1>")

    @pytest.mark.xfail(reason="ZGET compile-time table access not implemented")
    def test_table_length_words_accessible_at_compile_time(self):
        """Test that table length words are accessible at compile time."""
        AssertGlobals(
            "<SETG MY-TBL <LTABLE 100 200 300 400>>",
            "<GLOBAL ORIG-LENGTH <ZGET ,MY-TBL 0>>",
            "<ZPUT ,MY-TBL 0 -1>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies(
            "<=? ,ORIG-LENGTH 4>",
            "<=? <GET ,TBL 0> -1>",
            "<=? <GET ,TBL 4> 400>"
        )

    @pytest.mark.xfail(reason="Compile-time ZPUT not implemented")
    def test_table_with_adjacent_bytes_can_be_overwritten_with_words(self):
        """Test that adjacent bytes can be overwritten with words."""
        AssertGlobals(
            "<SETG MY-TBL <TABLE (BYTE) 0 0 67 0>>",
            "<ZPUT ,MY-TBL 0 12345>",
            "<PUTB ,MY-TBL 3 89>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies(
            "<==? <GET ,TBL 0> 12345>",
            "<==? <GETB ,TBL 2> 67>",
            "<==? <GETB ,TBL 3> 89>"
        )

    @pytest.mark.xfail(reason="Compile-time PUTB not implemented")
    def test_table_with_words_can_be_overwritten_with_bytes(self):
        """Test that words can be overwritten with bytes."""
        AssertGlobals(
            "<SETG MY-TBL <TABLE 12345 6789>>",
            "<PUTB ,MY-TBL 0 123>",
            "<PUTB ,MY-TBL 1 45>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies(
            "<==? <GETB ,TBL 0> 123>",
            "<==? <GETB ,TBL 1> 45>",
            "<==? <GET ,TBL 1> 6789>"
        )

    @pytest.mark.xfail(reason="Compile-time table element preservation not implemented")
    def test_round_tripping_table_elements_preserves_widths(self):
        """Test that round-tripping table elements preserves widths."""
        AssertGlobals(
            "<SETG MY-TBL <LTABLE 1 2 3>>",
            "<PUTB ,MY-TBL 2 100>",
            "<ZPUT ,MY-TBL 1 1>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies(
            "<==? <GET ,TBL 0> 3>",
            "<==? <GET ,TBL 1> 1>",
            "<==? <GET ,TBL 2> 2>",
            "<==? <GET ,TBL 3> 3>"
        )

        AssertGlobals(
            "<SETG MY-TBL <LTABLE (BYTE) 1 2 3>>",
            "<ZPUT ,MY-TBL 1 2>",
            "<PUTB ,MY-TBL 2 2>",
            "<PUTB ,MY-TBL 3 3>",
            "<GLOBAL TBL ,MY-TBL>"
        ).implies(
            "<==? <GETB ,TBL 0> 3>",
            "<==? <GETB ,TBL 1> 1>",
            "<==? <GETB ,TBL 2> 2>",
            "<==? <GETB ,TBL 3> 3>"
        )


class TestParserTables:
    """Tests for parser tables."""

    @pytest.mark.xfail(reason="PARSER-TABLE memory ordering not implemented")
    def test_parser_tables_come_before_other_pure_tables(self):
        """Test that PARSER-TABLEs come before other pure tables."""
        AssertGlobals(
            "<CONSTANT PURE-TBL <TABLE (PURE) 1 2 3>>",
            "<CONSTANT PARSER-TBL <TABLE (PARSER-TABLE) 1 2 3>>",
            "<CONSTANT IMPURE-TBL <TABLE 1 2 3>>"
        ).implies(
            "<L? ,IMPURE-TBL ,PARSER-TBL>",
            "<L=? <LOWCORE PURBOT> ,PARSER-TBL>",
            "<L? ,PARSER-TBL ,PURE-TBL>"
        )

    @pytest.mark.xfail(reason="PARSER-TABLE / PRSTBL not implemented")
    def test_parser_tables_start_at_prstbl(self):
        """Test that PARSER-TABLEs start at PRSTBL."""
        AssertGlobals("<CONSTANT PARSER-TBL <TABLE (PARSER-TABLE) 1 2 3>>") \
            .implies("<=? ,PARSER-TBL ,PRSTBL>")


class TestZREST:
    """Tests for ZREST (compile-time table offset)."""

    @pytest.mark.xfail(reason="ZREST compile-time offset tables not implemented")
    def test_zrest_creates_compile_time_offset_table(self):
        """Test that ZREST creates compile-time offset table."""
        AssertGlobals(
            "<SETG MY-TBL <TABLE 100 200 300>>",
            "<GLOBAL TBL ,MY-TBL>",
            "<SETG RESTED <ZREST ,MY-TBL 2>>",
            "<CONSTANT RESTED-OLD-0 <ZGET ,RESTED 0>>",
            "<ZPUT ,RESTED 1 345>"
        ).implies(
            "<=? ,RESTED-OLD-0 200>",
            "<=? <GET ,TBL 2> 345>"
        )

    @pytest.mark.xfail(reason="ZREST with 2OP instruction format not implemented")
    def test_zrest_works_with_2op_instruction(self):
        """Test that ZREST works with 2OP instruction."""
        AssertGlobals(
            "<CONSTANT PADDING-TBL <ITABLE 500>>",
            "<CONSTANT TBL <TABLE 100 200 300>>"
        ).implies("<=? <GET <ZREST ,TBL 4> 0> 300>")


class TestTableWarnings:
    """Tests for table warnings."""

    def test_table_with_length_prefix_warns_if_overflowing(self):
        """Test that length-prefixed table warns on overflow."""
        AssertGlobals("<CONSTANT FIELD <ITABLE BYTE 2500>>") \
            .with_warnings("MDL0430") \
            .compiles()

        AssertGlobals("<CONSTANT FIELD <ITABLE WORD 70000>>") \
            .with_warnings("MDL0430") \
            .compiles()

        # String longer than 256 characters
        long_string = "x" * 300
        AssertGlobals(f'<CONSTANT FIELD <TABLE (STRING LENGTH) "{long_string}">>') \
            .with_warnings("MDL0430") \
            .compiles()


class TestTableInRoutine:
    """Tests for tables defined in routines."""

    def test_table_in_routine_cannot_reference_locals(self):
        """Test that tables in routines can't reference locals."""
        AssertRoutine(
            '"AUX" (X 123) Y',
            "<SET Y <LTABLE .X <* .X 2>>>"
        ).does_not_compile()

    def test_table_in_routine_can_be_initialized_with_macro(self):
        """Test that tables in routines can use macros."""
        AssertRoutine(
            '"AUX" (X 123) Y',
            "<SET Y <LTABLE <MYMACRO 123>>>"
        ).with_global("<DEFMAC MYMACRO (X) <FORM * .X 10>>") \
            .compiles()

    def test_table_in_routine_can_be_initialized_with_segment(self):
        """Test that tables in routines can use segments."""
        AssertRoutine(
            '"AUX" X',
            "<SET X <LTABLE !,VALS>>"
        ).with_global("<SETG VALS '(1 2 3)>") \
            .compiles()

    def test_table_in_routine_can_be_initialized_with_splice(self):
        """Test that tables in routines can use splices."""
        AssertRoutine(
            '"AUX" X',
            "<SET X <LTABLE <MYMACRO>>>"
        ).with_global("<DEFMAC MYMACRO () #SPLICE (1 2 3)>") \
            .compiles()

    def test_table_at_top_level_can_be_initialized_with_macro(self):
        """Test that top-level tables can use macros."""
        AssertRoutine("", ",FOO") \
            .with_global("<DEFMAC MYMACRO (X) <FORM * .X 10>>") \
            .with_global("<GLOBAL FOO <LTABLE <MYMACRO 123>>>") \
            .compiles()
