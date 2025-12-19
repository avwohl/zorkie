# ZILF Interpreter Tests for Zorkie
# ==================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original directory: test/Zilf.Tests/Interpreter/
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
Tests for the MDL/ZIL interpreter.

These tests verify that the zorkie interpreter correctly handles:
- Arithmetic operations (+, -, *, /, LSH, ORB, ANDB, XORB, etc.)
- Atom operations (SPNAME, PARSE, LPARSE, SETG, SET, GVAL, LVAL, etc.)
- Type system operations (TYPE, PRIMTYPE, CHTYPE, NEWTYPE, etc.)
- Structure operations (LIST, VECTOR, TABLE, MEMQ, MEMBER, REST, etc.)
- Flow control (COND, PROG, RETURN, AGAIN, etc.)
- Function definitions (DEFINE, DEFMAC, FUNCTION, APPLY, etc.)
- Output operations (PRINC, PRIN1, PRINT, etc.)
"""
