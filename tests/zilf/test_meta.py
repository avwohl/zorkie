# ZILF Meta Tests for Zorkie
# ==========================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/MetaTests.cs
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
Tests for ZIL meta-compilation features.

These tests verify that the zorkie compiler correctly handles:
- IFFLAG conditional compilation
- Package DEFINITIONS and name sharing
- IN-ZILCH flag for macro expansion context
- ROUTINE-REWRITER hooks
- PRE-COMPILE hooks
- RELEASEID handling
- Error limits and diagnostics
- Warning conversion and suppression
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals, AssertRaw


class TestIFFLAG:
    """Tests for IFFLAG conditional compilation."""

    def test_ifflag_with_true_flag(self):
        """Test IFFLAG with true flag."""
        AssertRoutine("", "<IFFLAG (FOO 123) (ELSE 456)>") \
            .with_global("<COMPILATION-FLAG FOO T>") \
            .gives_number("123")

    def test_ifflag_with_false_flag(self):
        """Test IFFLAG with false flag."""
        AssertRoutine("", "<IFFLAG (FOO 123) (ELSE 456)>") \
            .with_global("<COMPILATION-FLAG FOO <>>") \
            .gives_number("456")

    def test_ifflag_with_string_flag_name(self):
        """Test IFFLAG with string flag name."""
        AssertRoutine("", '<IFFLAG ("FOO" 123) (ELSE 456)>') \
            .with_global("<COMPILATION-FLAG FOO <>>") \
            .gives_number("456")


class TestPackageDefinitions:
    """Tests for package DEFINITIONS and name sharing."""

    def test_property_names_are_shared_across_packages(self):
        """Test property names are shared across packages."""
        AssertGlobals(
            '<DEFINITIONS "FOO"> <OBJECT FOO-OBJ (MY-PROP 123)> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <OBJECT BAR-OBJ (MY-PROP 456)> <END-DEFINITIONS>',
            "<ROUTINE FOO () <GETP <> ,P?MY-PROP>>"
        ).compiles()

    def test_object_names_are_shared_across_packages(self):
        """Test object names are shared across packages."""
        AssertGlobals(
            "<FILE-FLAGS UNUSED-ROUTINES?>",
            '<DEFINITIONS "FOO"> <OBJECT FOO-OBJ> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <OBJECT BAR-OBJ (LOC FOO-OBJ)> <END-DEFINITIONS>',
            "<ROUTINE FOO () <REMOVE ,FOO-OBJ>>"
        ).without_warnings() \
            .compiles()

        AssertGlobals(
            "<SET REDEFINE T>",
            '<DEFINITIONS "FOO"> <OBJECT MY-OBJ> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <OBJECT MY-OBJ> <END-DEFINITIONS>',
            '<DEFINITIONS "BAZ"> <OBJECT MY-OBJ> <END-DEFINITIONS>'
        ).without_warnings() \
            .compiles()

    def test_constant_names_are_shared_across_packages(self):
        """Test constant names are shared across packages."""
        # Same value is OK
        AssertGlobals(
            '<DEFINITIONS "FOO"> <CONSTANT MY-CONST 1> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <CONSTANT MY-CONST 1> <END-DEFINITIONS>',
            "<ROUTINE FOO () <PRINT ,MY-CONST>>"
        ).compiles()

        # Different values fail
        AssertGlobals(
            '<DEFINITIONS "FOO"> <CONSTANT MY-CONST 1> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <CONSTANT MY-CONST 2> <END-DEFINITIONS>',
            "<ROUTINE FOO () <PRINT ,MY-CONST>>"
        ).does_not_compile()

    def test_global_names_are_shared_across_packages(self):
        """Test global names are shared across packages."""
        # With REDEFINE is OK
        AssertGlobals(
            "<SET REDEFINE T>",
            '<DEFINITIONS "FOO"> <GLOBAL MY-GLOBAL <TABLE 1 2 3>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <GLOBAL MY-GLOBAL <TABLE 1 2 3>> <END-DEFINITIONS>',
            "<ROUTINE FOO () <PRINT ,MY-GLOBAL>>"
        ).compiles()

        # Without REDEFINE fails
        AssertGlobals(
            '<DEFINITIONS "FOO"> <GLOBAL MY-GLOBAL <TABLE 1 2 3>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <GLOBAL MY-GLOBAL <TABLE 1 2 3>> <END-DEFINITIONS>',
            "<ROUTINE FOO () <PRINT ,MY-GLOBAL>>"
        ).does_not_compile()

    def test_routine_names_are_shared_across_packages(self):
        """Test routine names are shared across packages."""
        # Cross-package calls work
        AssertGlobals(
            '<DEFINITIONS "FOO"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            "<ROUTINE BAR () <FOO>>"
        ).compiles()

        # With REDEFINE, multiple definitions work
        AssertGlobals(
            "<SET REDEFINE T>",
            '<DEFINITIONS "FOO"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            "<ROUTINE BAR () <FOO>>"
        ).compiles()

        AssertGlobals(
            "<SET REDEFINE T>",
            '<DEFINITIONS "FOO"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAZ"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            "<ROUTINE BAR () <FOO>>"
        ).compiles()

        AssertGlobals(
            "<SET REDEFINE T>",
            '<DEFINITIONS "FOO"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAZ"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "QUUX"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            "<ROUTINE BAR () <FOO>>"
        ).compiles()

        # Without REDEFINE, duplicate definitions fail
        AssertGlobals(
            '<DEFINITIONS "FOO"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            '<DEFINITIONS "BAR"> <ROUTINE FOO () <BAR>> <END-DEFINITIONS>',
            "<ROUTINE BAR () <FOO>>"
        ).does_not_compile()


class TestInZilch:
    """Tests for IN-ZILCH flag."""

    def test_in_zilch_indicates_macro_expansion_context(self):
        """Test IN-ZILCH indicates what macro expansions will be used for."""
        MY_MACRO = """
<DEFMAC HELLO (WHENCE)
    <FORM BIND '()
        <FORM <IFFLAG (IN-ZILCH PRINTI) (T PRINC)>
              <STRING "Hello from " .WHENCE>>
        <FORM CRLF>>>"""

        AssertRoutine("", '<HELLO "Z-machine">') \
            .with_global(MY_MACRO) \
            .with_global('<HELLO "MDL">') \
            .capturing_compile_output() \
            .outputs("Hello from MDL\nHello from Z-machine\n")


class TestRoutineRewriter:
    """Tests for ROUTINE-REWRITER hook."""

    MY_REWRITER = """
<DEFINE MY-REWRITER (NAME ARGS BODY)
    <COND (<N==? .NAME GO>
           <SET BODY
              (<FORM TELL "Arg: " <FORM LVAL <1 .ARGS>> CR>
               <FORM BIND ((RES <FORM PROG '() !.BODY>)) <FORM TELL "Return: " N '.RES CR> '.RES>)>
           <LIST .ARGS !.BODY>)>>"""

    def test_routine_rewriter_can_rewrite_routines(self):
        """Test ROUTINE-REWRITER can rewrite routines."""
        AssertRoutine("NAME", '<TELL "Hello, " .NAME "." CR>') \
            .with_global(self.MY_REWRITER) \
            .with_global("<SETG REWRITE-ROUTINE!-HOOKS!-ZILF ,MY-REWRITER>") \
            .when_called_with('"world"') \
            .outputs("Arg: world\nHello, world.\nReturn: 1\n")


class TestPreCompileHook:
    """Tests for PRE-COMPILE hook."""

    MY_HOOK = """
<DEFINE MY-PRE-COMPILE ("AUX" ROUTINES)
    <SET ROUTINES
        <PROG ((A <ASSOCIATIONS>))
            <MAPF ,VECTOR
                  <FUNCTION ("AUX" (L <CHTYPE .A LIST>) ITEM IND VAL)
                      <OR .A <MAPSTOP>>
                      <SET ITEM <1 .L>>
                      <SET IND <2 .L>>
                      <SET VAL <3 .L>>
                      <SET A <NEXT .A>>
                      <COND (<AND <TYPE? .ITEM ATOM>
                                  <==? .IND ZVAL>
                                  <TYPE? .VAL ROUTINE>>
                             .ITEM)
                            (ELSE <MAPRET>)>>>>>
    <EVAL <FORM ROUTINE LIST-ROUTINES '()
              !<MAPF ,LIST
                     <FUNCTION (A) <FORM TELL <SPNAME .A> CR>>
                     <SORT <> .ROUTINES>>>>>"""

    @pytest.mark.xfail(reason="PRE-COMPILE hook not implemented")
    def test_pre_compile_hook_can_add_to_compilation_environment(self):
        """Test PRE-COMPILE hook can add to compilation environment."""
        AssertRoutine("", "<LIST-ROUTINES>") \
            .with_global(self.MY_HOOK) \
            .with_global("<SETG PRE-COMPILE!-HOOKS!-ZILF ,MY-PRE-COMPILE>") \
            .outputs("GO\nTEST?ROUTINE\n")


class TestReleaseid:
    """Tests for RELEASEID handling."""

    @pytest.mark.parametrize("zversion", [3, 4, 5, 6, 7, 8])
    def test_releaseid_is_optional(self, zversion):
        """Test RELEASEID is optional for all versions."""
        code = f"<VERSION {zversion}>\n<ROUTINE GO () <PRINTN <GET 2 0>> <CRLF> <QUIT>>"
        AssertRaw(code).outputs("0\n")


class TestErrorLimits:
    """Tests for error limits."""

    def test_compilation_stops_after_100_errors(self):
        """Test compilation stops after 100 errors."""
        builder = AssertRoutine("", "T")
        builder = builder.with_global("<FILE-FLAGS KEEP-ROUTINES?>")

        for i in range(1, 151):
            builder = builder.with_global(f"<ROUTINE DUMMY-{i} () <THIS-IS-INVALID>>")

        builder.does_not_compile_with_error_count(101)


class TestWarningConversion:
    """Tests for warning conversion and suppression."""

    def test_warnings_can_be_converted_to_errors(self):
        """Test warnings can be converted to errors."""
        # Without WARN-AS-ERROR?, compiles with warnings
        AssertRoutine("", ".X") \
            .with_global("<GLOBAL X 5>") \
            .with_warnings() \
            .gives_number("5")

        # With WARN-AS-ERROR?, fails to compile
        AssertRoutine("", ".X") \
            .with_global("<WARN-AS-ERROR? T>") \
            .with_global("<GLOBAL X 5>") \
            .without_warnings() \
            .does_not_compile("ZIL0204")

    def test_warnings_can_be_suppressed(self):
        """Test warnings can be suppressed."""
        # Suppress specific warning
        AssertRoutine("", ".X") \
            .with_global("<GLOBAL X 5>") \
            .with_global('<SUPPRESS-WARNINGS? "ZIL0204">') \
            .without_unsuppressed_warnings() \
            .gives_number("5")

        # Suppress all warnings
        AssertRoutine("", ".X") \
            .with_global("<GLOBAL X 5>") \
            .with_global("<SUPPRESS-WARNINGS? ALL>") \
            .without_unsuppressed_warnings() \
            .gives_number("5")

        # Unsuppress warnings
        AssertRoutine("", ".X") \
            .with_global("<GLOBAL X 5>") \
            .with_global('<SUPPRESS-WARNINGS? "ZIL0204">') \
            .with_global("<SUPPRESS-WARNINGS? NONE>") \
            .with_warnings("ZIL0204") \
            .gives_number("5")
