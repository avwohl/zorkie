# ZILF Variable Tests for Zorkie
# ==============================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/VariableTests.cs
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
Tests for ZIL variable handling.

These tests verify that the zorkie compiler correctly handles:
- Global variables and FUNNY-GLOBALS
- Local variables and scope
- DEFINE-GLOBALS
- Variable warnings
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals


def make_many_globals(count, prefix="MY-GLOBAL"):
    """Generate many global definitions."""
    return "\n".join(f"<GLOBAL {prefix}-{i} {i}>" for i in range(1, count + 1))


class TestFunnyGlobals:
    """Tests for FUNNY-GLOBALS (extended global support)."""

    def test_funny_globals_allows_lots_of_globals(self):
        """Test that FUNNY-GLOBALS allows more than 240 globals."""
        num_globals = 500
        globals_code = "<FUNNY-GLOBALS?>\n" + make_many_globals(num_globals)

        # Build routine body
        body_parts = []
        expected_parts = []
        for i in range(1, num_globals + 1):
            body_parts.append(
                f"<SETG MY-GLOBAL-{i} <+ ,MY-GLOBAL-{i} 1000>> <PRINTN ,MY-GLOBAL-{i}> <CRLF>"
            )
            expected_parts.append(str(i + 1000))

        AssertRoutine("", "\n".join(body_parts)) \
            .with_global(globals_code) \
            .outputs("\n".join(expected_parts) + "\n")

    def test_funny_globals_works_with_inc(self):
        """Test that FUNNY-GLOBALS works with INC."""
        num_globals = 500
        globals_code = "<FUNNY-GLOBALS?>\n" + make_many_globals(num_globals)

        body_parts = []
        expected_parts = []
        for i in range(1, num_globals + 1):
            body_parts.append(f"<INC MY-GLOBAL-{i}> <PRINTN <INC MY-GLOBAL-{i}>> <CRLF>")
            expected_parts.append(str(i + 2))

        AssertRoutine("", "\n".join(body_parts)) \
            .with_global(globals_code) \
            .outputs("\n".join(expected_parts) + "\n")

    def test_assigned_funny_globals_works_in_value_context(self):
        """Test that assigned FUNNY-GLOBALS works in value context."""
        num_globals = 500
        globals_code = ["<FUNNY-GLOBALS?>"]
        for i in range(1, num_globals + 1):
            globals_code.append(f"<GLOBAL MY-GLOBAL-{i} {i}>")
        globals_code.append("<GLOBAL VARIABLE 4>")

        AssertRoutine(
            "",
            '<COND (<==? <SETG VARIABLE <- ,VARIABLE 1>> 3> <TELL "Three." CR>)>'
        ).with_global("\n".join(globals_code)) \
            .outputs("Three.\n")

    def test_special_globals_always_hard_globals(self):
        """Test that special globals are always hard globals."""
        num_globals = 500
        globals_code = ["<FUNNY-GLOBALS?>"]
        for i in range(1, num_globals + 1):
            globals_code.append(f"<GLOBAL MY-GLOBAL-{i} {i}>")
        globals_code.append("<GLOBAL HERE <>>")
        globals_code.append("<GLOBAL SCORE <>>")
        globals_code.append("<GLOBAL MOVES <>>")

        AssertRoutine("", "<>") \
            .with_global("\n".join(globals_code)) \
            .in_v3() \
            .generates_code_matching(r"\.GVAR HERE=.*\.GVAR SCORE=.*\.GVAR MOVES=")

    def test_propdef_referenced_globals_always_hard_globals(self):
        """Test that PROPDEF-referenced globals are always hard globals."""
        num_globals = 500
        globals_code = ["<FUNNY-GLOBALS?>"]
        for i in range(1, num_globals + 1):
            globals_code.append(f"<GLOBAL MY-GLOBAL-{i} {i}>")
        globals_code.append("<PROPDEF GLOB <> (GLOB REF G:GLOBAL = 1 <GLOBAL .G>)>")
        globals_code.append("<OBJECT FOO (GLOB REF MY-GLOBAL-400)>")

        AssertRoutine("", "<>") \
            .with_global("\n".join(globals_code)) \
            .generates_code_matching(r"\.GVAR MY-GLOBAL-400=")

    def test_parameter_globals_always_hard_globals(self):
        """Test that parameter globals are always hard globals."""
        num_globals = 500
        globals_code = ["<FUNNY-GLOBALS?>"]
        for i in range(1, num_globals + 1):
            globals_code.append(f"<GLOBAL MY-GLOBAL-{i} {i}>")
        globals_code.append("<ROUTINE PRINTGN (GN) <PRINTN .GN>>")

        AssertRoutine("", "<PRINTGN MY-GLOBAL-400>") \
            .with_global("\n".join(globals_code)) \
            .with_warnings("ZIL0200") \
            .generates_code_matching(r"\.GVAR MY-GLOBAL-400=")


class TestDefineGlobals:
    """Tests for DEFINE-GLOBALS construct."""

    def test_define_globals_works(self):
        """Test that DEFINE-GLOBALS works correctly."""
        AssertRoutine(
            "",
            "<PRINTN <MY-WORD>> <CRLF> "
            "<PRINTN <MY-BYTE>> <CRLF> "
            "<MY-WORD 12345> "
            "<MY-BYTE 67> "
            "<PRINTN <MY-WORD>> <CRLF> "
            "<PRINTN <MY-BYTE>> <CRLF> "
        ).with_global(
            "<DEFINE-GLOBALS TEST-GLOBALS (MY-WORD 32767) (MY-BYTE BYTE 255) (HAS-ADECL:FIX 0)>"
        ).outputs("32767\n255\n12345\n67\n")


class TestGlobalAndConstantADECLs:
    """Tests for GLOBAL and CONSTANT with ADECLs."""

    def test_global_and_constant_work_with_adecls(self):
        """Test that GLOBAL and CONSTANT work with ADECLs."""
        AssertRoutine("", "<>") \
            .with_global("<GLOBAL FOO:FIX 12>") \
            .with_global("<CONSTANT BAR:FIX 34>") \
            .compiles()


class TestGlobalInitialization:
    """Tests for global initialization."""

    def test_global_can_be_initialized_to_global_index_with_warning(self):
        """Test that global can be initialized to global index with warning."""
        AssertRoutine("", "<PRINTN ,BAR>") \
            .with_global("<GLOBAL GLOBAL-16 <>>") \
            .with_global("<GLOBAL GLOBAL-17 <>>") \
            .with_global("<GLOBAL FOO <>>") \
            .with_global("<GLOBAL BAR FOO>") \
            .with_warnings() \
            .outputs("18")


class TestLocalVariables:
    """Tests for local variable handling."""

    def test_locals_can_have_same_names_as_globals(self):
        """Test that locals can shadow globals."""
        # global can be accessed with SETG and GVAL
        AssertRoutine("", "<BUMP-IT 111> ,FOO") \
            .with_global("<GLOBAL FOO 123>") \
            .with_global("<ROUTINE BUMP-IT (FOO) <SETG FOO <+ ,FOO .FOO>>>") \
            .gives_number("234")

        # PROG local shadows ROUTINE local
        AssertRoutine("", "<BUMP-IT 111> ,FOO") \
            .with_global("<GLOBAL FOO 123>") \
            .with_global("<ROUTINE BUMP-IT (FOO) <PROG ((FOO 1000)) <SETG FOO <+ ,FOO .FOO>>>>") \
            .gives_number("1123")


class TestUnusedLocalsWarnings:
    """Tests for unused local variable warnings."""

    def test_unused_locals_should_warn(self):
        """Test that unused locals generate warnings."""
        warning_code = "ZIL0210"

        # unreferenced, uninitialized routine local => warn
        AssertRoutine('"AUX" X', "<>") \
            .with_warnings(warning_code) \
            .compiles()

        # add a read => OK
        AssertRoutine('"AUX" X', ".X") \
            .without_warnings() \
            .compiles()

        # unreferenced routine local, initialized to routine call => OK
        AssertRoutine('"AUX" (X <FOO>)', "<>") \
            .with_global('<ROUTINE FOO () <TELL "hi"> 123>') \
            .without_warnings() \
            .compiles()

        # unreferenced, uninitialized BIND local => warn
        AssertRoutine("", "<BIND (X) <>>") \
            .with_warnings(warning_code) \
            .compiles()

        # add a read => OK
        AssertRoutine("", "<BIND (X) .X>") \
            .without_warnings() \
            .compiles()

        # unreferenced BIND local, initialized to routine call => OK
        AssertRoutine("", "<BIND ((X <FOO>)) <>>") \
            .with_global('<ROUTINE FOO () <TELL "hi"> 123>') \
            .without_warnings() \
            .compiles()


class TestComplexSetDestination:
    """Tests for SET with complex destinations."""

    def test_set_with_complex_destination_works_in_value_context(self):
        """Test that SET with complex destination works in value context."""
        AssertRoutine("", "<PRINTN <FANCY 1>>") \
            .with_global('<ROUTINE FANCY (A "AUX" B C) <+ <SET <+ .A 1> <+ .A 123>> .B>>') \
            .outputs("248")
