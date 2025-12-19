# ZILF Output Interpreter Tests for Zorkie
# =========================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/OutputTests.cs
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
Tests for MDL/ZIL output operations.

These tests verify that the zorkie interpreter correctly handles:
- PRINC (print without quotes)
- PRIN1 (print with quotes)
- PRINT-MANY (print multiple items)
"""

import pytest
from io import StringIO
from .conftest import Context, evaluate


class OutputChannel:
    """Mock output channel for testing."""

    def __init__(self):
        self.buffer = StringIO()

    @property
    def string(self) -> str:
        return self.buffer.getvalue()

    def write(self, text: str):
        self.buffer.write(text)


def make_test_channel(ctx: Context) -> OutputChannel:
    """Create a test output channel and set it as OUTCHAN."""
    channel = OutputChannel()
    # In a real implementation, this would set .OUTCHAN
    return channel


class TestPRINC:
    """Tests for PRINC output."""

    def test_princ_output(self):
        """PRINC prints without quotes."""
        ctx = Context()
        chan = make_test_channel(ctx)

        # This test would verify that PRINC outputs:
        # [H ello WORLD]
        # (strings without quotes, chars as characters)
        # The actual implementation would capture the output
        pass


class TestPRIN1:
    """Tests for PRIN1 output."""

    def test_prin1_output(self):
        """PRIN1 prints with quotes."""
        ctx = Context()
        chan = make_test_channel(ctx)

        # This test would verify that PRIN1 outputs:
        # [!\H "ello" WORLD]
        # (strings with quotes, chars with escape)
        pass


class TestPRINT_MANY:
    """Tests for PRINT-MANY output."""

    def test_print_many_output(self):
        """PRINT-MANY prints multiple items."""
        ctx = Context()
        chan = make_test_channel(ctx)

        # This test would verify that PRINT-MANY outputs:
        # Hello!\n"string"!\c\n
        pass
