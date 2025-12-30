# ZILF Pruning Tests for Zorkie
# ==============================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/PruningTests.cs
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
Tests for dead code pruning and unused routine warnings.

These tests verify that the zorkie compiler correctly:
- Warns about unused routines
- Prunes unreferenced code from output
- Respects flags that suppress warnings or keep unused code
"""

import pytest
from .conftest import AssertRoutine


class TestUnusedRoutines:
    """Tests for unused routine detection and pruning."""

    def test_unused_routines_should_warn_and_be_pruned(self):
        """Test that unused routines generate warnings and are pruned."""
        # Define an extra routine FOO that is never referenced; it should
        # be warned and not emitted.
        AssertRoutine("", '<PRINTI "hi">') \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .with_warnings("ZIL0213") \
            .generates_code_not_matching(r"\.FUNCT\s+FOO\b")

    def test_unused_routines_should_not_warn_when_flagged(self):
        """Test that unused routines don't warn with UNUSED-ROUTINES? flag."""
        # ...but they should still be pruned
        AssertRoutine("", '<PRINTI "hi">') \
            .with_global("<FILE-FLAGS UNUSED-ROUTINES?>") \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .without_warnings() \
            .generates_code_not_matching(r"\.FUNCT\s+FOO\b")

        AssertRoutine("", '<PRINTI "hi">') \
            .with_global("<ROUTINE-FLAGS UNUSED?>") \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .without_warnings() \
            .generates_code_not_matching(r"\.FUNCT\s+FOO\b")

    def test_unused_routines_should_not_be_pruned_when_flagged(self):
        """Test that unused routines are kept with KEEP-ROUTINES? flag."""
        # ...but they should still warn
        AssertRoutine("", '<PRINTI "hi">') \
            .with_global("<FILE-FLAGS KEEP-ROUTINES?>") \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .without_warnings("ZIL0213") \
            .generates_code_matching(r"\.FUNCT\s+FOO\b")

        AssertRoutine("", '<PRINTI "hi">') \
            .with_global("<ROUTINE-FLAGS KEEP?>") \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .without_warnings("ZIL0213") \
            .generates_code_matching(r"\.FUNCT\s+FOO\b")

    def test_unused_routines_should_not_warn_or_be_pruned_when_flagged(self):
        """Test that both flags together suppress warning and pruning."""
        AssertRoutine("", '<PRINTI "hi">') \
            .with_global("<FILE-FLAGS KEEP-ROUTINES? UNUSED-ROUTINES?>") \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .without_warnings("ZIL0213") \
            .generates_code_matching(r"\.FUNCT\s+FOO\b")

        AssertRoutine("", '<PRINTI "hi">') \
            .with_global("<ROUTINE-FLAGS KEEP? UNUSED?>") \
            .with_global('<ROUTINE FOO () <PRINTI "never">>') \
            .without_warnings("ZIL0213") \
            .generates_code_matching(r"\.FUNCT\s+FOO\b")


class TestMacroReferencing:
    """Tests for macro reference tracking."""

    def test_macro_referenced_routines_should_be_counted_as_used(self):
        """Test that routines referenced via macro expansion are kept."""
        # FOO is only referenced via macro expansion inside BAR; it should
        # be kept and no warning produced.
        AssertRoutine("", "<BAR>") \
            .with_global("<DEFMAC CALL-FOO () <FORM FOO>>") \
            .with_global("<ROUTINE FOO () <RTRUE>>") \
            .with_global("<ROUTINE BAR () <CALL-FOO>>") \
            .without_warnings() \
            .generates_code_matching(r"\.FUNCT\s+FOO\b")
