# ZILF Quirks Tests for Zorkie
# ============================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/QuirksTests.cs
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
Tests for ZIL quirks and edge cases.

These tests verify behavior when using GVAL with locals or LVAL with globals,
which are technically incorrect but should work with warnings.
"""

import pytest
from .conftest import AssertRoutine


class TestGVALLVALQuirks:
    """Tests for GVAL/LVAL quirk handling."""

    def test_gval_with_local(self):
        """Test that GVAL with local variable produces correct result with warning.

        Using ,X when X is a local is a quirk that should work but warn.
        """
        AssertRoutine('"AUX" (X 5)', "<FOO ,X>") \
            .with_global("<ROUTINE FOO (A) .A>") \
            .with_warnings() \
            .gives_number(5)

    def test_lval_with_global(self):
        """Test that LVAL with global variable produces correct result with warning.

        Using .X when X is a global is a quirk that should work but warn.
        """
        AssertRoutine("", "<FOO .X>") \
            .with_global("<GLOBAL X 5>") \
            .with_global("<ROUTINE FOO (A) .A>") \
            .with_warnings() \
            .gives_number(5)
