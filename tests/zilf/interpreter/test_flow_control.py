# ZILF Flow Control Interpreter Tests for Zorkie
# ===============================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/FlowControlTests.cs
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
Tests for MDL/ZIL flow control operations.

These tests verify that the zorkie interpreter correctly handles:
- COND conditional expressions
- VERSION? version checking
- RETURN and AGAIN activation handling
- PROG blocks with activations
- DECL checking in PROG
"""

import pytest
from .conftest import (
    Context, ZilFix, InterpreterError, DeclCheckError, ArgumentDecodingError,
    eval_and_assert, eval_and_catch, evaluate
)


class TestCOND:
    """Tests for COND conditional expression."""

    def test_cond_requires_at_least_one_clause(self):
        """COND requires at least one clause."""
        eval_and_catch(
            "<COND>",
            InterpreterError,
            lambda ex: "1 or more args" in str(ex)
        )

    def test_cond_should_reject_empty_clauses(self):
        """COND should reject empty clauses."""
        eval_and_catch(
            "<COND ()>",
            InterpreterError,
            lambda ex: "1 or more args" not in str(ex)
        )


class TestVERSION_P:
    """Tests for VERSION? version checking."""

    def test_version_p_should_reject_empty_clauses(self):
        """VERSION? should reject empty clauses."""
        eval_and_catch("<VERSION? ()>", InterpreterError)


class TestRETURN_And_AGAIN:
    """Tests for RETURN and AGAIN activation handling."""

    def test_return_and_again_require_an_activation(self):
        """RETURN and AGAIN require an activation to be in scope."""
        ctx = Context()

        # RETURN without activation should fail
        evaluate("<DEFINE FOO1 () <RETURN 123>>", ctx)
        eval_and_catch("<FOO1>", InterpreterError, ctx=ctx)

        # AGAIN without activation should fail
        evaluate('<DEFINE FOO2 ("AUX" (BLAH <>)) <COND (.BLAH <>) (T <SET BLAH T> <AGAIN>)>>', ctx)
        eval_and_catch("<FOO2>", InterpreterError, ctx=ctx)

        # OK with a PROG added
        evaluate("<DEFINE FOO3 () <PROG () <RETURN 123>>>", ctx)
        eval_and_assert("<FOO3>", ZilFix(123), ctx)

        evaluate('<DEFINE FOO4 ("AUX" (BLAH <>)) <PROG () <COND (.BLAH <>) (T <SET BLAH T> <AGAIN>)>>>', ctx)
        eval_and_assert("<FOO4>", ctx.FALSE, ctx)

        # But not if PROG is outside the function
        eval_and_catch("<PROG () <FOO1>>", InterpreterError, ctx=ctx)
        eval_and_catch("<PROG () <FOO2>>", InterpreterError, ctx=ctx)


class TestPROG:
    """Tests for PROG block."""

    def test_prog_can_bind_an_activation(self):
        """PROG can bind an activation atom for cross-function returns."""
        ctx = Context()

        evaluate("<DEFINE FOO () <* 10 <PROG P-ACT () <* 2 <BAR .P-ACT>>>>>", ctx)
        evaluate("<DEFINE BAR (A) <RETURN 123 .A>>", ctx)
        eval_and_assert("<FOO>", ZilFix(1230), ctx)

    def test_prog_requires_a_body(self):
        """PROG requires at least one body expression."""
        eval_and_catch(
            "<PROG ()>",
            ArgumentDecodingError,
            lambda ex: "???" not in str(ex)
        )
        eval_and_catch(
            "<PROG A ()>",
            ArgumentDecodingError,
            lambda ex: "???" not in str(ex)
        )
        eval_and_catch(
            "<PROG (A) #DECL ((A) FIX)>",
            ArgumentDecodingError,
            lambda ex: "???" not in str(ex)
        )

    def test_prog_sets_decls_from_adecls(self):
        """PROG sets DECLs from ADECLs in bindings."""
        eval_and_catch("<PROG ((A:FIX NOT-A-FIX)) <>>", DeclCheckError)
        eval_and_catch("<PROG (A:FIX) <SET A NOT-A-FIX>>", DeclCheckError)

    def test_prog_sets_decls_from_body_decls(self):
        """PROG sets DECLs from #DECL in body."""
        eval_and_catch("<PROG ((A NOT-A-FIX)) #DECL ((A) FIX) <>>", DeclCheckError)
        eval_and_catch("<PROG (A) #DECL ((A) FIX) <SET A NOT-A-FIX>>", DeclCheckError)

    def test_prog_rejects_conflicting_decls(self):
        """PROG rejects conflicting DECLs."""
        eval_and_catch("<PROG (A:FIX) #DECL ((A) LIST) <>>", InterpreterError)
        eval_and_catch("<PROG (A) #DECL ((A) FIX (A) LIST) <>>", InterpreterError)
