# ZILF Macro Tests for Zorkie
# ===========================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/MacroTests.cs
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
Tests for ZIL macro handling.

These tests verify that the zorkie compiler correctly handles:
- SPLICE results inside routines
- Macro argument count validation
- Globals defined inside routines via macros
- Macros in local initializers
- Macros returning constants as literal arguments
- Reader macros (MAKE-PREFIX-MACRO)
"""

import pytest
from .conftest import AssertExpr, AssertRoutine


class TestSplice:
    """Tests for SPLICE in macros."""

    def test_splices_should_work_inside_routines_void_context(self):
        """Test SPLICEs work in void context."""
        AssertRoutine("", "<VARIOUS-THINGS> T") \
            .with_global('<DEFMAC VARIOUS-THINGS () <CHTYPE \'(<TELL "hello"> <TELL CR> <TELL "world">) SPLICE>>') \
            .outputs("hello\nworld")

    def test_splices_should_work_inside_routines_value_context(self):
        """Test SPLICEs work in value context."""
        AssertRoutine("", "<VARIOUS-THINGS>") \
            .with_global("<DEFMAC VARIOUS-THINGS () <CHTYPE '(123 456) SPLICE>>") \
            .gives_number("456")

    def test_splices_should_work_as_builtin_arguments(self):
        """Test SPLICEs work as builtin arguments."""
        AssertRoutine("", "<+ <VARIOUS-THINGS>>") \
            .with_global("<DEFMAC VARIOUS-THINGS () <CHTYPE '(123 456) SPLICE>>") \
            .gives_number("579")

        AssertRoutine("", "<TELL <VARIOUS-THINGS>>") \
            .with_global("<DEFMAC VARIOUS-THINGS () <CHTYPE '(N 12345) SPLICE>>") \
            .outputs("12345")

    def test_splices_should_work_as_routine_arguments(self):
        """Test SPLICEs work as routine arguments."""
        AssertRoutine("", "<ADD-EM <VARIOUS-THINGS>>") \
            .with_global("<DEFMAC VARIOUS-THINGS () <CHTYPE '(123 456) SPLICE>>") \
            .with_global("<ROUTINE ADD-EM (X Y) <+ .X .Y>>") \
            .gives_number("579")


class TestMacroArgumentValidation:
    """Tests for macro argument count validation."""

    def test_macro_call_with_wrong_argument_count_should_raise_error(self):
        """Test macro with wrong argument count raises error."""
        AssertRoutine('"AUX" S', "<SET S <FOO A>>") \
            .with_global('<DEFMAC FOO (\'X \'Y \'Z) <FORM TELL "hello world" CR>>') \
            .does_not_compile()


class TestMacrosDefiningGlobals:
    """Tests for macros defining globals."""

    def test_macros_can_define_globals_inside_routines(self):
        """Test macros can define globals inside routines."""
        AssertRoutine("", "<PRINTN <MAKE-GLOBAL 123>>") \
            .with_global("<DEFMAC MAKE-GLOBAL (N) <EVAL <FORM GLOBAL NEW-GLOBAL .N>> ',NEW-GLOBAL>") \
            .outputs("123")


class TestMacrosInInitializers:
    """Tests for macros in local initializers."""

    def test_macros_can_be_used_in_local_initializers(self):
        """Test macros can be used in local initializers."""
        AssertRoutine('"AUX" (X <MY-VALUE>)', ".X") \
            .with_global("<DEFMAC MY-VALUE () 123>") \
            .gives_number("123")


class TestMacrosReturningConstants:
    """Tests for macros returning constants."""

    def test_macros_returning_string_constants_can_be_used_as_literal_arguments(self):
        """Test macros returning string constants work as literal arguments."""
        AssertExpr('<PRINTI <FOO>> <CRLF>') \
            .with_global('<DEFMAC FOO () "hello world">') \
            .outputs("hello world\n")

    def test_macros_returning_constants_can_be_used_in_lowcore_table(self):
        """Test macros returning numeric constants work in LOWCORE-TABLE."""
        AssertRoutine("", "<LOWCORE-TABLE ZVERSION <FOO> PRINTN>") \
            .with_global("<DEFMAC FOO () 2>") \
            .compiles()


class TestReaderMacros:
    """Tests for reader macros."""

    def test_make_prefix_macro_should_work(self):
        """Test MAKE-PREFIX-MACRO works."""
        AssertExpr('<TELL B @HELLO " " B @WORLD CR>') \
            .with_global('<USE "READER-MACROS">') \
            .with_global(r'<MAKE-PREFIX-MACRO !\@ <FUNCTION (W:ATOM) <VOC <SPNAME .W> BUZZ>>>') \
            .outputs("hello world\n")
