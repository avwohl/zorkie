# ZILF Tell Tests for Zorkie
# ==========================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/TellTests.cs
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
Tests for ZIL TELL macro and string handling.

These tests verify that the zorkie compiler correctly handles:
- Custom TELL macro definitions
- Built-in TELL tokens
- Custom TELL-TOKENS
- String translation (newlines, spaces, CR)
- CRLF-CHARACTER setting
- Space preservation
- Sentence endings
- Unprintable character warnings
- Character set (CHRSET) handling
- LANGUAGE text encoding
- Unicode character support
"""

import pytest
from .conftest import AssertExpr, AssertRoutine


class TestTellMacro:
    """Tests for TELL macro."""

    def test_tell_macro_should_be_used_if_defined(self):
        """Test custom TELL macro is used when defined."""
        AssertRoutine("", "<TELL 21>") \
            .with_global("<DEFMAC TELL ('X) <FORM PRINTN <* .X 2>>>") \
            .outputs("42")


class TestTellBuiltin:
    """Tests for built-in TELL functionality."""

    def test_tell_builtin_should_support_basic_operations(self):
        """Test TELL supports basic operations."""
        AssertRoutine("", '<TELL "AB" C 67 CR N 123 CRLF D ,OBJ>') \
            .with_global('<OBJECT OBJ (DESC "obj")>') \
            .outputs("ABC\n123\nobj")


class TestTellTokens:
    """Tests for custom TELL-TOKENS."""

    TOKENS_CODE = """
<TELL-TOKENS
    (CR CRLF)        <CRLF>
    DBL *            <PRINT-DBL .X>
    DBL0             <PRINT-DBL <>>
    WUTEVA *:STRING  <PRINTI .X>
    WUTEVA *:FIX     <PRINTN .X>
    GLOB             <PRINTN ,GLOB>
    MAC1             <PRINT-MAC-1>
    MAC2             <PRINT-MAC-2>>

<ROUTINE PRINT-DBL (X) <PRINTN <* 2 .X>>>
<GLOBAL GLOB 123>
<DEFMAC PRINT-MAC-1 () '<PRINT "macro">>
<DEFMAC PRINT-MAC-2 () #SPLICE (<PRINT "mac"> <PRINT "ro">)>"""

    def test_tell_builtin_should_support_new_tokens_dbl(self):
        """Test TELL supports custom DBL token."""
        AssertRoutine("", "<TELL DBL 21 CRLF>") \
            .with_global(self.TOKENS_CODE) \
            .outputs("42\n")

    def test_tell_builtin_should_support_new_tokens_dbl0(self):
        """Test TELL supports custom DBL0 token."""
        AssertRoutine("", "<TELL DBL0>") \
            .with_global(self.TOKENS_CODE) \
            .outputs("0")

    def test_tell_builtin_should_support_new_tokens_wuteva_string(self):
        """Test TELL supports custom WUTEVA token with string."""
        AssertRoutine("", '<TELL WUTEVA "hello">') \
            .with_global(self.TOKENS_CODE) \
            .outputs("hello")

    def test_tell_builtin_should_support_new_tokens_glob_and_wuteva_fix(self):
        """Test TELL supports GLOB and WUTEVA with fix."""
        AssertRoutine("", "<TELL GLOB WUTEVA 45 CR>") \
            .with_global(self.TOKENS_CODE) \
            .outputs("12345\n")

    def test_tell_builtin_should_support_new_tokens_macros(self):
        """Test TELL supports macro tokens."""
        AssertRoutine("", "<TELL MAC1 MAC2>") \
            .with_global(self.TOKENS_CODE) \
            .outputs("macromacro")


class TestTellTokenErrors:
    """Tests for TELL token error handling."""

    @pytest.mark.xfail(reason="TELL-TOKENS not implemented")
    def test_tell_token_resulting_in_bad_call_should_not_compile(self):
        """Test TELL tokens with bad calls don't compile."""
        # Too many args for the routine
        AssertRoutine("", "<TELL FOO>") \
            .with_global("<TELL-TOKENS FOO <FOO 1 2 3>>") \
            .with_global("<ROUTINE FOO (A B) <PRINTN <+ .A .B>>>") \
            .does_not_compile("ZIL0112")

        AssertRoutine("", "<TELL FOO 1 2 3>") \
            .with_global("<TELL-TOKENS FOO * * * <FOO .X. .Y .Z>>") \
            .with_global("<ROUTINE FOO (A B) <PRINTN <+ .A .B>>>") \
            .does_not_compile("ZIL0112")

        # Too many args for the Z-machine version
        AssertRoutine("", "<TELL FOO>") \
            .in_v3() \
            .with_global("<TELL-TOKENS FOO <FOO 1 2 3 4>>") \
            .with_global('<ROUTINE FOO ("OPT" A B C D) <PRINTN <+ .A .B>>>') \
            .does_not_compile("ZIL0402")

        AssertRoutine("", "<TELL FOO 1 2 3 4>") \
            .in_v3() \
            .with_global("<TELL-TOKENS FOO * * * * <FOO .X. .Y .Z .W>>") \
            .with_global('<ROUTINE FOO ("OPT" A B C D) <PRINTN <+ .A .B>>>') \
            .does_not_compile("ZIL0402")

    def test_tell_builtin_should_reject_complex_outputs(self):
        """Test TELL rejects complex outputs."""
        AssertRoutine("", "<>") \
            .with_global("<TELL-TOKENS DBL * <PRINTN <* 2 .X>>>") \
            .does_not_compile()

    def test_tell_builtin_should_reject_bare_atoms_correctly(self):
        """Test TELL rejects bare atoms with proper error message."""
        AssertRoutine("", "<TELL SPACE-TEXT CR>") \
            .with_global('<CONSTANT SPACE-TEXT "Space. The final frontier.">') \
            .does_not_compile()

    def test_tell_builtin_should_reject_mismatched_captures(self):
        """Test TELL rejects using more captures than available."""
        # Unused captures are allowed (ZILCH behavior - e.g., CAO/CANO in beyondzork)
        # The callee function may use implicit context instead of .X
        AssertRoutine("", "<>") \
            .with_global("<TELL-TOKENS DBL * <PRINT-DBL>>") \
            .compiles()

        # But using more captures than available is an error
        AssertRoutine("", "<>") \
            .with_global("<TELL-TOKENS DBL * <PRINT-DBL .X .Y>>") \
            .does_not_compile()


class TestStringTranslation:
    """Tests for string translation in TELL."""

    def test_tell_builtin_should_translate_strings(self):
        """Test TELL translates strings correctly."""
        AssertRoutine("", '<TELL "foo|bar|\nbaz\nquux">') \
            .outputs("foo\nbar\nbaz quux")

    def test_tell_builtin_should_support_characters(self):
        """Test TELL supports character literals."""
        AssertRoutine("", r"<TELL !\A !\B !\C>") \
            .outputs("ABC")

    def test_cr_in_string_should_be_ignored(self):
        """Test CR in string is ignored."""
        AssertRoutine("", '<TELL "First line.\r\nSecond line.\r\nLast line.">') \
            .outputs("First line. Second line. Last line.")

    def test_crlf_character_should_affect_string_translation(self):
        """Test CRLF-CHARACTER affects string translation."""
        AssertRoutine("", '<TELL "foo^bar">') \
            .with_global(r"<SETG CRLF-CHARACTER !\^>") \
            .outputs("foo\nbar")


class TestSpaceHandling:
    """Tests for space handling in strings."""

    @pytest.mark.xfail(reason="dfrotz strips trailing spaces from output")
    def test_two_spaces_after_period_should_collapse_by_default(self):
        """Test two spaces after period collapse by default."""
        AssertRoutine("", '<TELL "Hi.  Hi.   Hi.|  Hi!  Hi?  " CR>') \
            .outputs("Hi. Hi.  Hi.\n Hi!  Hi?  \n")

    @pytest.mark.xfail(reason="dfrotz strips trailing spaces from output")
    def test_two_spaces_after_period_should_not_collapse_with_preserve_spaces(self):
        """Test two spaces don't collapse with PRESERVE-SPACES?."""
        AssertRoutine("", '<TELL "Hi.  Hi.   Hi.|  Hi!  Hi?  " CR>') \
            .with_global("<SETG PRESERVE-SPACES? T>") \
            .outputs("Hi.  Hi.   Hi.\n  Hi!  Hi?  \n")

    @pytest.mark.xfail(reason="SENTENCE-ENDS? not implemented")
    def test_two_spaces_after_period_bang_or_question_should_become_sentence_space(self):
        """Test sentence endings with SENTENCE-ENDS? flag."""
        # Note: a space followed by embedded newline will produce two spaces instead of collapsing.
        AssertRoutine("", '<TELL "Hi.  Hi.   Hi.|  Hi!  Hi?  Hi. \nHi." CR>') \
            .in_v6() \
            .with_global("<FILE-FLAGS SENTENCE-ENDS?>") \
            .outputs("Hi.\u000bHi.\u000b Hi.\n  Hi!\u000bHi?\u000bHi.  Hi.\n")


class TestUnprintableCharacters:
    """Tests for unprintable character warnings."""

    def test_unprintable_characters_in_strings_should_warn(self):
        """Test unprintable characters generate warnings."""
        CODE_WITH_TAB = '<TELL "foo\tbar" CR>'
        CODE_WITH_BACKSPACE = '<TELL "foo\x08bar" CR>'
        CODE_WITH_CTRL_Z = '<TELL "foo\x1abar" CR>'

        # Tab is legal in V6...
        AssertRoutine("", CODE_WITH_TAB) \
            .in_v6() \
            .without_warnings() \
            .compiles()

        # ...but not in V5
        AssertRoutine("", CODE_WITH_TAB) \
            .in_v5() \
            .with_warnings("ZIL0410") \
            .compiles()

        # Backspace is never legal
        AssertRoutine("", CODE_WITH_BACKSPACE) \
            .with_warnings("ZIL0410") \
            .compiles()

        # Nor is ^Z
        AssertRoutine("", CODE_WITH_CTRL_Z) \
            .with_warnings("ZIL0410") \
            .compiles()


class TestCHRSET:
    """Tests for CHRSET (character set) handling."""

    @pytest.mark.xfail(reason="Custom CHRSET encoding not implemented")
    def test_chrset_should_affect_text_decoding(self):
        """Test CHRSET affects text decoding."""
        #      1         2         3
        #  67890123456789012345678901
        #  zyxwvutsrqponmlkjihgfedcba
        #
        #    z=6   i=23  l=20
        #  1 00110 10111 10100
        AssertRoutine("", "<PRINTB ,MYTEXT>") \
            .with_global('<CHRSET 0 "zyxwvutsrqponmlkjihgfedcba">') \
            .with_global("<CONSTANT MYTEXT <TABLE #2 1001101011110100>>") \
            .in_v5() \
            .outputs("zil")

    @pytest.mark.xfail(reason="Custom CHRSET encoding not implemented")
    def test_chrset_should_affect_text_encoding(self):
        """Test CHRSET affects text encoding."""
        AssertRoutine(
            "",
            "<PRINT ,MYTEXT> <CRLF> "
            "<PRINTN <- <GET <* 4 ,MYTEXT> 0> ,ENCODED-TEXT>>"
        ).with_global('<CHRSET 0 "zyxwvutsrqponmlkjihgfedcba">') \
            .with_global('<CONSTANT MYTEXT "zil">') \
            .with_global("<CONSTANT ENCODED-TEXT #2 1001101011110100>") \
            .in_v5() \
            .outputs("zil\n0")


class TestLanguage:
    """Tests for LANGUAGE setting on text encoding."""

    @pytest.mark.xfail(reason="LANGUAGE directive not fully implemented")
    def test_language_should_affect_text_encoding(self):
        """Test LANGUAGE affects text encoding."""
        AssertRoutine("", '<TELL "%>M%obeltr%agerf%u%se%<">') \
            .with_global("<LANGUAGE GERMAN>") \
            .in_v5() \
            .outputs("\u00bbM\u00f6beltr\u00e4gerf\u00fc\u00dfe\u00ab")

    @pytest.mark.xfail(reason="LANGUAGE directive not fully implemented")
    def test_language_should_affect_vocabulary_encoding(self):
        """Test LANGUAGE affects vocabulary encoding."""
        AssertRoutine("", r"<PRINTB ,W?\%A\%S>") \
            .with_global("<LANGUAGE GERMAN>") \
            .with_global(r"<OBJECT FOO (SYNONYM \%A\%S)>") \
            .in_v5() \
            .outputs("\u00e4\u00df")


class TestStringOptimization:
    """Tests for string optimization."""

    def test_strings_used_in_tell_should_not_become_gstr(self):
        """Test strings in TELL don't become GSTR."""
        AssertRoutine("", '<TELL "hello world">') \
            .generates_code_not_matching(r"GSTR.*hello world")

    def test_strings_used_in_printi_should_not_become_gstr(self):
        """Test strings in PRINTI don't become GSTR."""
        AssertRoutine("", '<PRINTI "hello world">') \
            .generates_code_not_matching(r"GSTR.*hello world")


class TestUnicode:
    """Tests for Unicode character support."""

    @pytest.mark.xfail(reason="Unicode support in dfrotz not verified")
    def test_unicode_characters_should_work_in_tell_in_v5(self):
        """Test Unicode characters work in TELL in V5."""
        # U+2014: em dash, U+2019: right single quotation mark
        AssertRoutine("", '<TELL "the em dash\u2014nature\u2019s most dramatic symbol">') \
            .in_v5() \
            .without_warnings() \
            .outputs("the em dash\u2014nature\u2019s most dramatic symbol")

    @pytest.mark.xfail(reason="Glulx requires Glk library for I/O - basic assembler implemented but Glk integration pending")
    def test_unicode_characters_should_work_in_tell_in_glulx(self):
        """Test Unicode characters work in TELL in Glulx."""
        # U+2014: em dash, U+2019: right single quotation mark
        AssertRoutine("", '<TELL "the em dash\u2014nature\u2019s most dramatic symbol">') \
            .in_glulx() \
            .without_warnings() \
            .outputs("the em dash\u2014nature\u2019s most dramatic symbol")

    @pytest.mark.xfail(reason="Unicode error detection not implemented")
    def test_unicode_characters_outside_standard_should_error_in_v3(self):
        """Test Unicode characters outside standard error in V3."""
        AssertRoutine("", '<TELL "bad\u2014news">') \
            .in_v3() \
            .does_not_compile("ZIL0414")

    def test_unicode_table_should_be_emitted_in_v5(self):
        """Test Unicode table is emitted in V5."""
        AssertRoutine("", '<TELL "\u2014\u2019\u263a">') \
            .in_v5() \
            .without_warnings() \
            .generates_code_matching(r'\.UNICHR "U\+2014".*\.UNICHR "U\+263A"')

    @pytest.mark.xfail(reason="Unicode table overflow detection not implemented")
    def test_unicode_table_should_report_overflow_when_full(self):
        """Test Unicode table reports overflow when full."""
        chars = "".join(chr(0x0100 + i) for i in range(98))
        code = f'<TELL "{chars}">'

        AssertRoutine("", code) \
            .in_v5() \
            .does_not_compile("ZIL0415")
