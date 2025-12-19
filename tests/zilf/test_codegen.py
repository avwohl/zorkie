# ZILF Code Generation Tests for Zorkie
# ======================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/CodeGenTests.cs
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
Tests for Z-machine code generation optimizations.

These tests verify that the zorkie compiler generates efficient Z-code
by applying optimizations such as:
- Instruction combining (e.g., INC for add-1)
- Branch merging (e.g., PRINTR for print+crlf+rtrue)
- Constant folding
- Predicate context optimization
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals


class TestArithmeticOptimizations:
    """Tests for arithmetic instruction optimizations."""

    def test_add_to_variable(self):
        """Test that adding to a variable uses direct store."""
        AssertRoutine('"AUX" X Y', "<SET X <+ .X .Y>>") \
            .generates_code_matching(r"ADD X,Y >X\r?\n\s*RETURN X")

    def test_add_in_void_context_becomes_inc(self):
        """Test that add-1 in void context becomes INC."""
        AssertRoutine('"AUX" X', "<SET X <+ .X 1>> .X") \
            .generates_code_matching(r"INC 'X\r?\n\s*RETURN X")

    def test_add_in_value_context_becomes_inc(self):
        """Test that add-1 in value context becomes INC."""
        AssertRoutine('"AUX" X', "<SET X <+ .X 1>>") \
            .generates_code_matching(r"INC 'X\r?\n\s*RETURN X")

    def test_subtract_then_less_becomes_dless(self):
        """Test that subtract-1 followed by less-than becomes DLESS?."""
        AssertRoutine('"AUX" X', '<SET X <- .X 1>> <COND (<L? .X 0> <PRINTI "blah">)>') \
            .generates_code_matching(r"DLESS\? 'X,0")

    def test_subtract_in_value_context_then_less_becomes_dless(self):
        """Test that subtract-1 in value context becomes DLESS?."""
        AssertRoutine('"AUX" X', '<COND (<L? <SET X <- .X 1>> 0> <PRINTI "blah">)>') \
            .generates_code_matching(r"DLESS\? 'X,0")

    def test_add_or_sub_with_zero_optimized_away(self):
        """Test that adding/subtracting 0 is optimized away."""
        AssertRoutine('"AUX" X', "<SET X <+ <GETB 0 33> 0>>") \
            .generates_code_not_matching(r"ADD")

        AssertRoutine('"AUX" X', "<SET X <- <GETB 0 33> 0>>") \
            .generates_code_not_matching(r"SUB")

    def test_mul_or_div_with_one_optimized_away(self):
        """Test that multiplying/dividing by 1 is optimized away."""
        AssertRoutine('"AUX" X', "<SET X <* <GETB 0 33> 1>>") \
            .generates_code_not_matching(r"MUL")

        AssertRoutine('"AUX" X', "<SET X </ <GETB 0 33> 1>>") \
            .generates_code_not_matching(r"DIV")


class TestCallOptimizations:
    """Tests for routine call optimizations."""

    def test_routine_result_into_variable(self):
        """Test that routine result goes directly into variable."""
        AssertRoutine('"AUX" FOO', "<SET FOO <WHATEVER>>") \
            .with_global("<ROUTINE WHATEVER () 123>") \
            .in_v3() \
            .generates_code_matching("CALL WHATEVER >FOO")


class TestPrintOptimizations:
    """Tests for print instruction optimizations."""

    def test_printi_crlf_rtrue_becomes_printr(self):
        """Test that PRINTI+CRLF+RTRUE becomes PRINTR."""
        AssertRoutine("", '<PRINTI "hi"> <CRLF> <RTRUE>') \
            .generates_code_matching('PRINTR "hi"')

    def test_printr_over_branch_1(self):
        """Test PRINTR optimization over branches."""
        AssertRoutine('"AUX" X', '<COND (.X <PRINTI "foo">) (T <PRINTI "bar">)> <CRLF> <RTRUE>') \
            .generates_code_matching('PRINTR "foo".*PRINTR "bar"')

    def test_printr_over_branch_2(self):
        """Test PRINTR optimization over branches with explicit CRLF."""
        AssertRoutine('"AUX" X', '<COND (.X <PRINTI "foo"> <CRLF>) (T <PRINTI "bar"> <CRLF>)> <RTRUE>') \
            .generates_code_matching('PRINTR "foo".*PRINTR "bar"')


class TestEqualityOptimizations:
    """Tests for equality comparison optimizations."""

    def test_adjacent_equals_combine(self):
        """Test that adjacent EQUAL? calls are combined."""
        AssertRoutine('"AUX" X', "<COND (<OR <=? .X 1> <=? .X 2>> <RTRUE>)>") \
            .generates_code_matching(r"EQUAL\? X,1,2 /TRUE")

        AssertRoutine('"AUX" X', "<COND (<OR <EQUAL? .X 1 2> <EQUAL? .X 3 4>> <RTRUE>)>") \
            .generates_code_matching(r"EQUAL\? X,1,2,3 /TRUE")

        AssertRoutine('"AUX" X', "<COND (<OR <EQUAL? .X 1 2 3> <=? .X 4> <EQUAL? .X 5 6>> <RTRUE>)>") \
            .generates_code_matching(r"EQUAL\? X,1,2,3 /TRUE\r?\n\s*EQUAL\? X,4,5,6 /TRUE")

    def test_equal_zero_becomes_zero_p(self):
        """Test that comparing to 0 becomes ZERO?."""
        AssertRoutine('"AUX" X', "<COND (<=? .X 0> <RTRUE>)>") \
            .generates_code_matching(r"ZERO\? X /TRUE")

        AssertRoutine('"AUX" X', "<COND (<=? 0 .X> <RTRUE>)>") \
            .generates_code_matching(r"ZERO\? X /TRUE")

    def test_adjacent_equals_combine_even_if_zero(self):
        """Test that adjacent EQUAL? calls combine even with 0."""
        AssertRoutine('"AUX" X', "<COND (<OR <=? .X 0> <=? .X 2>> <RTRUE>)>") \
            .generates_code_matching(r"EQUAL\? X,0,2 /TRUE")


class TestPredicateContext:
    """Tests for predicate context optimizations."""

    def test_value_predicate_context(self):
        """Test value/predicate context handling."""
        AssertRoutine('"AUX" X Y', "<COND (<NOT <SET X <FIRST? .Y>>> <RTRUE>)>") \
            .generates_code_matching(r"FIRST\? Y >X \\TRUE")

    def test_value_predicate_context_calls(self):
        """Test value/predicate context with function calls."""
        AssertRoutine('"AUX" X', "<COND (<NOT <SET X <FOO>>> <RTRUE>)>") \
            .with_global("<ROUTINE FOO () <>>") \
            .generates_code_matching(r"CALL FOO >X\r?\n\s*ZERO\? X /TRUE")

    def test_value_predicate_context_constants(self):
        """Test value/predicate context with constants."""
        AssertRoutine('"AUX" X', "<COND (<NOT <SET X <>>> <RTRUE>)>") \
            .generates_code_matching(r"SET 'X,0\r?\n\s*RTRUE")

        AssertRoutine('"AUX" X', "<COND (<NOT <SET X 0>> <RTRUE>)>") \
            .generates_code_matching(r"SET 'X,0\r?\n\s*RTRUE")

        AssertRoutine('"AUX" X', "<COND (<NOT <SET X 100>> <RTRUE>)>") \
            .generates_code_matching(r"SET 'X,100\r?\n\s*RFALSE")

        AssertRoutine('"AUX" X', "<COND (<NOT <SET X T>> <RTRUE>)>") \
            .generates_code_matching(r"SET 'X,1\r?\n\s*RFALSE")


class TestBranchOptimizations:
    """Tests for branch/terminator optimizations."""

    def test_merge_adjacent_terminators(self):
        """Test that adjacent terminators are merged."""
        AssertRoutine(
            'OBJ "AUX" (CNT 0) X',
            """<COND (<SET X <FIRST? .OBJ>>
                <REPEAT ()
                    <SET CNT <+ .CNT 1>>
                    <COND (<NOT <SET X <NEXT? .X>>> <RETURN>)>>)>
            .CNT"""
        ).when_called_with("<>") \
            .generates_code_matching(r"NEXT\? X >X /\?L\d+\r?\n\s*\?L\d+:\s*RETURN CNT\r?\n\r?\n")

    def test_return_or_with_pred(self):
        """Test RETURN with OR and predicate optimization."""
        AssertRoutine('"AUX" X', "<OR <EQUAL? .X 123> <FOO>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .generates_code_not_matching(r"PUSH|ZERO\?")

    def test_set_or_with_pred(self):
        """Test SET with OR and predicate optimization."""
        AssertRoutine('"AUX" X Y', "<SET Y <OR <EQUAL? .X 123> <FOO>>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .generates_code_not_matching(r"ZERO\?")


class TestAndOrOptimizations:
    """Tests for AND/OR optimizations."""

    def test_simple_and_1(self):
        """Test simple AND optimization."""
        AssertRoutine('"AUX" A', "<AND .A <FOO>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .generates_code_not_matching(r"\?TMP")

    def test_simple_and_2(self):
        """Test nested AND optimization."""
        AssertRoutine('"AUX" A', "<AND <OR <0? .A> <FOO>> <BAR>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .with_global("<ROUTINE BAR () <>>") \
            .generates_code_not_matching(r"\?TMP")

    def test_simple_or_1(self):
        """Test simple OR optimization."""
        AssertRoutine('"AUX" A', "<OR .A <FOO>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .generates_code_not_matching(r"\?TMP")

    def test_simple_or_3(self):
        """Test OR with SET optimization."""
        AssertRoutine('"AUX" A', "<OR <SET A <FOO>> <BAR>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .with_global("<ROUTINE BAR () <>>") \
            .generates_code_not_matching(r"\?TMP")

    def test_or_in_value_context_avoids_unnecessary_preservation(self):
        """Test that OR in value context avoids unnecessary value preservation."""
        AssertRoutine(
            "OBJ",
            '''<OR ;"We can always see the contents of surfaces"
                    <FSET? .OBJ ,SURFACEBIT>
                    ;"We can see inside containers if they're open, transparent, or
                      unopenable (= always-open)"
                    <AND <FSET? .OBJ ,CONTBIT>
                         <OR <FSET? .OBJ ,OPENBIT>
                             <FSET? .OBJ ,TRANSBIT>
                             <NOT <FSET? .OBJ ,OPENABLEBIT>>>>>'''
        ).with_global("<CONSTANT SURFACEBIT 1>") \
            .with_global("<CONSTANT CONTBIT 2>") \
            .with_global("<CONSTANT OPENBIT 3>") \
            .with_global("<CONSTANT TRANSBIT 4>") \
            .with_global("<CONSTANT OPENABLEBIT 5>") \
            .when_called_with("<>") \
            .generates_code_not_matching(r"\?TMP")

    def test_and_in_value_context_avoids_unnecessary_preservation(self):
        """Test that AND in value context avoids unnecessary value preservation."""
        AssertRoutine(
            "OBJ",
            '''<AND ;"We can always see the contents of surfaces"
                    <FSET? .OBJ ,SURFACEBIT>
                    ;"We can see inside containers if they're open, transparent, or
                      unopenable (= always-open)"
                    <AND <FSET? .OBJ ,CONTBIT>
                         <OR <FSET? .OBJ ,OPENBIT>
                             <FSET? .OBJ ,TRANSBIT>
                             <NOT <FSET? .OBJ ,OPENABLEBIT>>>>>'''
        ).with_global("<CONSTANT SURFACEBIT 1>") \
            .with_global("<CONSTANT CONTBIT 2>") \
            .with_global("<CONSTANT OPENBIT 3>") \
            .with_global("<CONSTANT TRANSBIT 4>") \
            .with_global("<CONSTANT OPENABLEBIT 5>") \
            .when_called_with("<>") \
            .generates_code_not_matching(r"\?TMP")


class TestBitwiseOptimizations:
    """Tests for bitwise operation optimizations."""

    def test_band_in_predicate_with_power_of_two_optimized(self):
        """Test that BAND with power-of-2 in predicate uses BTST."""
        AssertRoutine('"AUX" X', "<COND (<BAND .X 4> <RTRUE>)>") \
            .generates_code_matching(r"BTST X,4 (/TRUE|\\FALSE)")

        AssertRoutine('"AUX" X', "<COND (<BAND 4 .X> <RTRUE>)>") \
            .generates_code_matching(r"BTST X,4 (/TRUE|\\FALSE)")

        # BAND with zero is never true
        AssertRoutine('"AUX" X', "<COND (<BAND 0 .X> <RTRUE>)>") \
            .generates_code_matching("RFALSE")

        AssertRoutine('"AUX" X', "<COND (<BAND .X 0> <RTRUE>)>") \
            .generates_code_matching("RFALSE")

        # Doesn't work with non-powers-of-two
        AssertRoutine('"AUX" X', "<COND (<BAND .X 6> <RTRUE>)>") \
            .generates_code_matching(r"BAND X,6 >STACK\r?\n\s*ZERO\? STACK (\\TRUE|/FALSE)")

    def test_stacked_band_or_bor_collapses(self):
        """Test that nested BAND/BOR collapses."""
        AssertRoutine('"AUX" X', "<BAND 48 <BAND .X 96>>") \
            .generates_code_matching("BAND X,32 >STACK")

        AssertRoutine('"AUX" X', "<BOR <BOR 96 .X> 48>") \
            .generates_code_matching("BOR X,112 >STACK")

        # Test with named constants
        AssertRoutine('"AUX" X', "<BOR <BOR .X ,FOO> ,BAR>") \
            .with_global("<CONSTANT FOO 96>") \
            .with_global("<CONSTANT BAR 48>") \
            .generates_code_matching("BOR X,112 >STACK")


class TestConstantFolding:
    """Tests for constant folding optimizations."""

    def test_constant_arithmetic_operations_folded(self):
        """Test that constant arithmetic is folded."""
        # Binary operators
        AssertRoutine("", "<+ 1 <* 2 3> <* 4 5>>") \
            .generates_code_matching("RETURN 27")

        AssertRoutine("", "<+ ,EIGHT ,SIXTEEN>") \
            .with_global("<CONSTANT EIGHT 8>") \
            .with_global("<CONSTANT SIXTEEN 16>") \
            .generates_code_matching("RETURN 24")

        AssertRoutine("", "<MOD 1000 16>") \
            .generates_code_matching("RETURN 8")

        AssertRoutine("", "<ASH -32768 -2>") \
            .in_v5() \
            .generates_code_matching("RETURN -8192")

        AssertRoutine("", "<LSH -32768 -2>") \
            .in_v5() \
            .generates_code_matching("RETURN 8192")

        AssertRoutine("", "<XORB 25 -1>") \
            .generates_code_matching("RETURN -26")

        # Unary operators
        AssertRoutine("", "<BCOM 123>") \
            .generates_code_matching("RETURN -124")

    def test_constant_comparisons_folded(self):
        """Test that constant comparisons are folded."""
        # Unary comparisons
        AssertRoutine("", "<0? ,FALSE-VALUE>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        AssertRoutine("", "<1? <- 6 5>>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        AssertRoutine("", "<T? <+ 1 2 3>>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        AssertRoutine("", "<F? <+ 1 2 3>>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RFALSE")

        AssertRoutine("", "<NOT <- 6 4 2>>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        # Binary comparisons
        AssertRoutine("", "<L? 1 10>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        AssertRoutine("", "<G=? ,FALSE-VALUE ,TRUE-VALUE>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RFALSE")

        AssertRoutine("", "<BTST <+ 64 32 8> <+ 32 8>>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        AssertRoutine("", "<BTST <+ 64 32 8> <+ 16 8>>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RFALSE")

        # Varargs equality comparisons
        AssertRoutine("", "<=? 50 10 <- 100 50> 100>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RTRUE")

        AssertRoutine("", "<=? 49 10 <- 100 50> 100>") \
            .generates_code_matching(r"\.FUNCT TEST\?ROUTINE\r?\n\s*RFALSE")


class TestTempVariables:
    """Tests for temporary variable handling."""

    def test_nested_temp_variables(self):
        """Test nested temp variable handling."""
        # This code should use 3 temp variables
        AssertRoutine('"AUX" X', "<PUT ,GLOB <FOO> <+ .X <GET ,GLOB <BAR>>>>") \
            .with_global("<GLOBAL GLOB <>>") \
            .with_global("<ROUTINE FOO () <>>") \
            .with_global("<ROUTINE BAR () <>>") \
            .generates_code_matching(r"\?TMP\?2")

    def test_nested_bind_variables(self):
        """Test nested BIND variable handling."""
        AssertRoutine(
            "",
            """<BIND (X)
                  <SET X 0>
                  <BIND (X)
                    <SET X 1>
                    <BIND (X)
                      <SET X 2>>>>"""
        ).generates_code_matching(r"X\?2")

    def test_reuse_temp(self):
        """Test that temp variables are reused properly."""
        # The first G? allocates one temp var, then releases it afterward
        # The BIND consumes the same temp var and binds it to a new atom
        # The second G? allocates a new temp var, which must not collide
        AssertRoutine(
            "",
            "<COND (<G? <FOO> <BAR>> <RTRUE>)> " +
            "<BIND ((Z 0)) <COND (<G? <BAR> <FOO>> <RFALSE>)>>"
        ).with_global("<ROUTINE FOO () 123>") \
            .with_global("<ROUTINE BAR () 456>") \
            .compiles()

    def test_no_temp_for_set(self):
        """Test that no temp vars are used when expressions go into named variables."""
        # This shouldn't use any temp vars
        AssertRoutine(
            '"AUX" X Y',
            "<COND (<G? <SET X <FOO>> <SET Y <BAR>>> <RTRUE>)> " +
            "<BIND ((Z 0)) <COND (<G? <SET X <BAR>> <SET Y <FOO>>> <RFALSE>)>>"
        ).with_global("<ROUTINE FOO () 123>") \
            .with_global("<ROUTINE BAR () 456>") \
            .generates_code_not_matching(r"\?TMP")

        # This one should, since X is modified in a subsequent arg
        AssertRoutine(
            '"AUX" X Y',
            "<COND (<G? <SET X <FOO>> <SET Y <SET X <BAR>>>> <RTRUE>)> " +
            "<BIND ((Z 0)) <COND (<G? <SET X <BAR>> <SET Y <SET X <FOO>>>> <RFALSE>)>>"
        ).with_global("<ROUTINE FOO () 123>") \
            .with_global("<ROUTINE BAR () 456>") \
            .generates_code_matching(r"\?TMP")


class TestHeaders:
    """Tests for header and directive generation."""

    def test_time_header_v3(self):
        """Test TIME directive in V3."""
        AssertRoutine("", "<>") \
            .with_version_directive("<VERSION ZIP TIME>") \
            .generates_code_matching(r"^\s*\.TIME\s*$")

    def test_sound_header_v3(self):
        """Test SOUND directive in V3."""
        AssertRoutine("", "<>") \
            .with_global("<SETG SOUND-EFFECTS? T>") \
            .in_v3() \
            .generates_code_matching(r"^\s*\.SOUND\s*$")


class TestCleanStack:
    """Tests for stack cleaning behavior."""

    def test_clean_stack_v3_no_clean(self):
        """Test V3 without CLEAN-STACK? flag."""
        AssertRoutine("", "<FOO> 456") \
            .with_global("<ROUTINE FOO () 123>") \
            .in_v3() \
            .generates_code_not_matching(r"FSTACK")

    def test_clean_stack_v3_clean(self):
        """Test V3 with CLEAN-STACK? flag."""
        AssertRoutine("", "<FOO> 456") \
            .with_global("<FILE-FLAGS CLEAN-STACK?>") \
            .with_global("<ROUTINE FOO () 123>") \
            .in_v3() \
            .generates_code_matching(r"FSTACK")

    def test_clean_stack_v4_no_clean(self):
        """Test V4 without CLEAN-STACK? flag."""
        AssertRoutine("", "<FOO> 456") \
            .with_global("<ROUTINE FOO () 123>") \
            .in_v4() \
            .generates_code_not_matching(r"FSTACK")

    def test_clean_stack_v4_clean(self):
        """Test V4 with CLEAN-STACK? flag."""
        AssertRoutine("", "<FOO> 456") \
            .with_global("<FILE-FLAGS CLEAN-STACK?>") \
            .with_global("<ROUTINE FOO () 123>") \
            .in_v4() \
            .generates_code_matching(r"FSTACK")


class TestZREST:
    """Tests for ZREST (table offset) handling."""

    def test_zrest_with_constant_table_uses_assembler_math(self):
        """Test that ZREST with constant table uses assembler math."""
        AssertRoutine("", "<REST ,MY-TABLE 2>") \
            .with_global("<CONSTANT MY-TABLE <TABLE 1 2 3 4>>") \
            .generates_code_matching(r"MY-TABLE\+2")


class TestValueVariableName:
    """Tests for VALUE with variable name."""

    def test_value_varname_does_not_use_instruction(self):
        """Test that VALUE with variable name doesn't generate instruction."""
        AssertRoutine("", "<VALUE MY-GLOBAL>") \
            .with_global("<GLOBAL MY-GLOBAL 123>") \
            .generates_code_matching("RETURN MY-GLOBAL")


class TestCHRSET:
    """Tests for CHRSET directive."""

    def test_chrset_generates_directive(self):
        """Test that CHRSET generates proper directive."""
        AssertGlobals('<CHRSET 0 "zyxwvutsrqponmlkjihgfedcba">') \
            .in_v5() \
            .generates_code_matching(
                r"\.CHRSET 0,122,121,120,119,118,117,116,115,114,113,112,111,110,109,108,107,106,105,104,103,102,101,100,99,98,97"
            )


class TestNameSanitization:
    """Tests for name sanitization in generated code."""

    def test_table_and_verb_names_sanitized(self):
        """Test that table and verb names are sanitized."""
        AssertGlobals(
            r"<SYNTAX \,TELL = V-TELL>",
            "<ROUTINE V-TELL () <>>",
            r"<CONSTANT \,TELLTAB1 <ITABLE 1>>",
            r"<GLOBAL \,TELLTAB2 <ITABLE 1>>"
        ).generates_code_not_matching(r",TELL")


class TestV6Specifics:
    """Tests for V6-specific code generation."""

    def test_pop_in_v6_stores(self):
        """Test that POP in V6 stores result."""
        AssertRoutine('"AUX" X', "<SET X <POP>>") \
            .in_v6() \
            .generates_code_matching(r"POP >X")

    def test_indirect_store_from_stack_in_v5_uses_pop(self):
        """Test that indirect store from stack in V5 uses POP."""
        AssertRoutine('"AUX" X', "<SETG .X <FOO>> <RTRUE>") \
            .with_global("<ROUTINE FOO () <>>") \
            .in_v5() \
            .generates_code_matching(r"POP X")

    def test_indirect_store_from_stack_in_v6_uses_set(self):
        """Test that indirect store from stack in V6 uses SET."""
        AssertRoutine('"AUX" X', "<SETG .X <FOO>> <RTRUE>") \
            .with_global("<ROUTINE FOO () <>>") \
            .in_v6() \
            .generates_code_matching(r"SET X,STACK")


class TestPredicateInBind:
    """Tests for predicate handling inside BIND."""

    def test_predicate_inside_bind_does_not_rely_on_push(self):
        """Test that predicate inside BIND doesn't rely on PUSH."""
        AssertRoutine('"AUX" X', "<COND (<BIND ((Y <* 2 .X>)) <G? .Y 123>> <RTRUE>)>") \
            .generates_code_matching(r"GRTR\? Y,123 (/TRUE|\\FALSE)")
