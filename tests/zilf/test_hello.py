# ZILF Hello World Tests for Zorkie
# ==================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/HelloTests.cs
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
Tests for basic ZIL compilation across Z-machine versions.

These tests verify that the zorkie compiler correctly handles:
- Basic compilation for all Z-machine versions (V3-V8)
- Simple ROUTINE definitions
- Basic output functions (PRINTI, PRINT, PRINTC, CRLF)
"""

import pytest
from .conftest import AssertRaw


class TestHelloWorld:
    """Tests for Hello World compilation across versions."""

    @pytest.mark.parametrize("zversion,version_name", [
        ("ZIP", "V3"),
        ("EZIP", "V4"),
        ("XZIP", "V5"),
        ("YZIP", "V6"),
        pytest.param("7", "V7", marks=pytest.mark.xfail(reason="V7 has interpreter bugs (bocfel/dfrotz)")),
        ("8", "V8"),
    ])
    def test_hello_world(self, zversion, version_name):
        """Test Hello World compiles and runs for each Z-machine version."""
        code = f"""
<VERSION {zversion}>

<ROUTINE GREET (WHOM)
    <PRINTI "Hello, ">
    <PRINT .WHOM>
    <PRINTC !\\!>
    <CRLF>>

<ROUTINE GO ()
    <GREET "world">
    <QUIT>>"""

        expected_output = "Hello, world!\n"
        AssertRaw(code).outputs(expected_output)
