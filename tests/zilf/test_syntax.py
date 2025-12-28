# ZILF Syntax Tests for Zorkie
# ============================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/SyntaxTests.cs
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
Tests for ZIL syntax definitions.

These tests verify that the zorkie compiler correctly handles:
- Preaction definitions and persistence
- Syntax line verb synonyms
- NEW-SFLAGS for scope flags
- Late syntax table references
- Verb and action limits (old parser vs NEW-PARSER?)
- COMPACT-PREACTIONS?
- REMOVE-SYNTAX for removing syntax entries
- REMOVE-SYNONYM for removing synonyms
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals
from .test_vocab import NEW_PARSER_BOOTSTRAP


class TestPreactions:
    """Tests for preaction definitions."""

    def test_first_preaction_definition_per_action_name_should_persist(self):
        """Test first preaction definition per action name persists."""
        AssertRoutine(
            "",
            "<TELL N <=? <GET ,ACTIONS ,V?FOO> ,V-FOO> CR"
            " N <=? <GET ,ACTIONS ,V?FOO-WITH> ,V-FOO> CR"
            " N <=? <GET ,ACTIONS ,V?BAR> ,V-BAR> CR"
            " N <=? <GET ,PREACTIONS ,V?FOO> ,PRE-FOO> CR"
            " N <=? <GET ,PREACTIONS ,V?FOO-WITH> 0> CR"
            " N <=? <GET ,PREACTIONS ,V?BAR> 0> CR>"
        ).with_global("<ROUTINE V-FOO () <>>") \
            .with_global("<ROUTINE V-BAR () <>>") \
            .with_global("<ROUTINE PRE-FOO () <>>") \
            .with_global("<ROUTINE PRE-FOO-2 () <>>") \
            .with_global("<ROUTINE PRE-BAR () <>>") \
            .with_global("<SYNTAX FOO = V-FOO PRE-FOO>") \
            .with_global("<SYNTAX FOO OBJECT = V-FOO PRE-FOO-2>") \
            .with_global("<SYNTAX FOO OBJECT AT OBJECT = V-FOO>") \
            .with_global("<SYNTAX FOO OBJECT WITH OBJECT = V-FOO <> FOO-WITH>") \
            .with_global("<SYNTAX BAR = V-BAR>") \
            .with_global("<SYNTAX BAR OBJECT = V-BAR PRE-BAR>") \
            .outputs("1\n1\n1\n1\n1\n1\n")


class TestSyntaxVerbSynonyms:
    """Tests for verb synonyms in syntax lines."""

    def test_syntax_lines_can_define_verb_synonyms(self):
        """Test syntax lines can define verb synonyms."""
        AssertRoutine(
            "",
            "<DO (I 4 6) <PRINTN <=? <GETB ,W?TOSS .I> <GETB ,W?CHUCK .I>>>>"
        ).with_global("<ROUTINE V-TOSS () <>>") \
            .with_global("<SYNTAX TOSS (CHUCK) OBJECT AT OBJECT = V-TOSS>") \
            .in_v3() \
            .outputs("111")


class TestNewSflags:
    """Tests for NEW-SFLAGS scope flags."""

    @pytest.mark.xfail(reason="NEW-SFLAGS not implemented")
    def test_new_sflags_defines_new_scope_flags(self):
        """Test NEW-SFLAGS defines new scope flags."""
        AssertGlobals(
            '<ROUTINE GET-OPTS1 (ACT "AUX" (ST <GET ,VERBS <- 255 .ACT>>)) <GETB .ST 6>>',
            "<CONSTANT SEARCH-DO-TAKE 1>",
            "<CONSTANT SEARCH-MUST-HAVE 2>",
            "<CONSTANT SEARCH-MANY 4>",
            "<CONSTANT SEARCH-STANDARD 8>",
            "<CONSTANT SEARCH-OPTIONAL 16>",
            "<CONSTANT SEARCH-ALL ,SEARCH-STANDARD>",
            '<SETG NEW-SFLAGS ["STANDARD" ,SEARCH-STANDARD "OPTIONAL" ,SEARCH-OPTIONAL]>',
            "<ROUTINE V-DUMMY () <>>",
            "<SYNTAX FOO OBJECT (OPTIONAL) = V-DUMMY>",
            "<SYNTAX BAR OBJECT (HAVE) = V-DUMMY>",
            "<SYNTAX BAZ OBJECT (HAVE OPTIONAL) = V-DUMMY>"
        ).implies(
            "<=? <GET-OPTS1 ,ACT?FOO> ,SEARCH-OPTIONAL>",
            "<=? <GET-OPTS1 ,ACT?BAR> <+ ,SEARCH-STANDARD ,SEARCH-MUST-HAVE>>",
            "<=? <GET-OPTS1 ,ACT?BAZ> <+ ,SEARCH-OPTIONAL ,SEARCH-MUST-HAVE>>"
        )


class TestLateSyntaxTables:
    """Tests for late syntax table references."""

    def test_late_syntax_tables_can_be_referenced_from_macros(self):
        """Test late syntax tables can be referenced from macros."""
        AssertRoutine("", "<PRINTN <FOO>>") \
            .with_global("<DEFMAC FOO () <FORM REST ,PRTBL 1>>") \
            .compiles()


class TestVerbLimits:
    """Tests for verb and action limits."""

    def test_old_parser_only_allows_255_verbs(self):
        """Test old parser only allows 255 verbs."""
        globals_code = [f"<SYNTAX VERB-{i} = V-FOO>" for i in range(256)]
        AssertGlobals(*globals_code) \
            .with_global("<ROUTINE V-FOO () <>>") \
            .does_not_compile("MDL0426")

    def test_old_parser_only_allows_255_actions(self):
        """Test old parser only allows 255 actions."""
        globals_code = [
            f"<SYNTAX VERB-{i // 100} PREP-{i % 100} OBJECT = V-FOO-{i}> <ROUTINE V-FOO-{i} () <>>"
            for i in range(256)
        ]
        AssertGlobals(*globals_code) \
            .does_not_compile("MDL0426")

    def test_new_parser_p_supports_more_than_255_verbs_and_actions(self):
        """Test NEW-PARSER? supports more than 255 verbs and actions."""
        globals_code = [NEW_PARSER_BOOTSTRAP]
        globals_code.extend(
            f"<SYNTAX VERB-{i} = V-VERB-{i}> <ROUTINE V-VERB-{i} () <>>"
            for i in range(257)
        )
        AssertGlobals(*globals_code) \
            .generates_code_matching(r"V\?VERB-256=256")


class TestCompactPreactions:
    """Tests for COMPACT-PREACTIONS? feature."""

    @pytest.mark.xfail(reason="COMPACT-PREACTIONS? not implemented")
    def test_compact_preactions_p_should_affect_preaction_table_format(self):
        """Test COMPACT-PREACTIONS? affects preaction table format."""
        AssertGlobals(
            "<SETG COMPACT-PREACTIONS? T>",
            "<SYNTAX FEE = V-FEE>",
            "<SYNTAX FIE = V-FIE>",
            "<SYNTAX FOE = V-FOE>",
            "<SYNTAX FOO = V-FOO PRE-FOO>",
            "<ROUTINE V-FEE () <>>",
            "<ROUTINE V-FIE () <>>",
            "<ROUTINE V-FOE () <>>",
            "<ROUTINE V-FOO () <>>",
            "<ROUTINE PRE-FOO () <>>"
        ).implies(
            "<=? <GET ,PREACTIONS 0> ,V?FOO>",
            "<=? <GET ,PREACTIONS 1> ,PRE-FOO>",
            "<=? <GET ,PREACTIONS 2> -1>",
            "<=? <GET ,PREACTIONS 3> 0>"
        )


class TestRemoveSyntax:
    """Tests for REMOVE-SYNTAX."""

    def test_remove_syntax_should_remove_matching_syntax_by_verb(self):
        """Test REMOVE-SYNTAX removes matching syntax by verb."""
        AssertGlobals(
            "<SYNTAX TAKE OBJECT = V-TAKE>",
            "<SYNTAX TAKE OBJECT FROM OBJECT = V-TAKE-FROM>",
            "<SYNTAX DROP OBJECT = V-DROP>",
            "<ROUTINE V-TAKE () <>>",
            "<ROUTINE V-TAKE-FROM () <>>",
            "<ROUTINE V-DROP () <>>",
            "<REMOVE-SYNTAX TAKE>"
        ).generates_code_not_matching("V-TAKE")

    def test_remove_syntax_should_remove_matching_syntax_by_action(self):
        """Test REMOVE-SYNTAX removes matching syntax by action."""
        AssertGlobals(
            "<SYNTAX TAKE OBJECT = V-TAKE>",
            "<SYNTAX GRAB OBJECT = V-TAKE>",
            "<SYNTAX DROP OBJECT = V-DROP>",
            "<ROUTINE V-TAKE () <>>",
            "<ROUTINE V-DROP () <>>",
            "<REMOVE-SYNTAX * = V-TAKE>"
        ).generates_code_not_matching("V-TAKE")

    def test_remove_syntax_should_remove_matching_syntax_by_preposition(self):
        """Test REMOVE-SYNTAX removes matching syntax by preposition."""
        AssertGlobals(
            "<SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN>",
            "<SYNTAX PUT OBJECT ON OBJECT = V-PUT-ON>",
            "<SYNTAX TAKE OBJECT = V-TAKE>",
            "<ROUTINE V-PUT-IN () <>>",
            "<ROUTINE V-PUT-ON () <>>",
            "<ROUTINE V-TAKE () <>>",
            "<REMOVE-SYNTAX PUT OBJECT IN>"
        ).generates_code_matching_func(
            lambda code: "V-PUT-ON" in code and "V-PUT-IN" not in code
        )

    def test_remove_syntax_should_match_wildcard_patterns(self):
        """Test REMOVE-SYNTAX matches wildcard patterns."""
        AssertGlobals(
            "<SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN>",
            "<SYNTAX PUT OBJECT ON OBJECT = V-PUT-ON>",
            "<SYNTAX TAKE OBJECT = V-TAKE>",
            "<ROUTINE V-PUT-IN () <>>",
            "<ROUTINE V-PUT-ON () <>>",
            "<ROUTINE V-TAKE () <>>",
            "<REMOVE-SYNTAX PUT * * OBJECT>"
        ).generates_code_not_matching("V-PUT")

    def test_remove_syntax_should_match_false_as_nothing(self):
        """Test REMOVE-SYNTAX matches FALSE as nothing."""
        # Test 1: <REMOVE-SYNTAX TAKE <>>
        AssertGlobals(
            "<SYNTAX TAKE INVENTORY OBJECT (FIND KLUDGEBIT) = V-INVENTORY>",
            "<SYNTAX TAKE OBJECT = V-YOINK>",
            "<SYNTAX TAKE = V-TAKE>",
            "<ROUTINE V-INVENTORY () <>>",
            "<ROUTINE V-TAKE () <>>",
            "<REMOVE-SYNTAX TAKE <>>"
        ).generates_code_matching_func(
            lambda code: "V-INVENTORY" in code and "V-YOINK" not in code and "V-TAKE" not in code
        )

        # Test 2: <REMOVE-SYNTAX TAKE <> * = *>
        AssertGlobals(
            "<SYNTAX TAKE INVENTORY OBJECT (FIND KLUDGEBIT) = V-INVENTORY>",
            "<SYNTAX TAKE OBJECT = V-YOINK>",
            "<SYNTAX TAKE = V-TAKE>",
            "<ROUTINE V-INVENTORY () <>>",
            "<ROUTINE V-TAKE () <>>",
            "<REMOVE-SYNTAX TAKE <> * = *>"
        ).generates_code_matching_func(
            lambda code: "V-INVENTORY" in code and "V-YOINK" not in code and "V-TAKE" not in code
        )

        # Test 3: <REMOVE-SYNTAX TAKE <> OBJECT>
        AssertGlobals(
            "<SYNTAX TAKE INVENTORY OBJECT (FIND KLUDGEBIT) = V-INVENTORY>",
            "<SYNTAX TAKE OBJECT = V-YOINK>",
            "<SYNTAX TAKE = V-TAKE>",
            "<ROUTINE V-INVENTORY () <>>",
            "<ROUTINE V-TAKE () <>>",
            "<REMOVE-SYNTAX TAKE <> OBJECT>"
        ).generates_code_matching_func(
            lambda code: "V-INVENTORY" in code and "V-YOINK" not in code and "V-TAKE" in code
        )


class TestRemoveSynonym:
    """Tests for REMOVE-SYNONYM."""

    @pytest.mark.xfail(reason="REMOVE-SYNONYM not implemented")
    def test_remove_synonym_should_remove_synonyms(self):
        """Test REMOVE-SYNONYM removes synonyms."""
        AssertGlobals(
            "<SYNTAX TAKE OBJECT = V-TAKE>",
            "<SYNONYM TAKE GET GRAB>",
            "<REMOVE-SYNONYM GET>",
            "<SYNTAX GET OBJECT = V-GET>",
            "<ROUTINE V-TAKE () <>>",
            "<ROUTINE V-GET () <>>",
            "<ROUTINE GET-SYNTAXES (WORD) <GET ,VTBL <- 255 <GETB .WORD 5>>>>"
        ).implies(
            "<=? <GET-SYNTAXES ,W?TAKE> <GET-SYNTAXES ,W?GRAB>>",
            "<N=? <GET-SYNTAXES ,W?TAKE> <GET-SYNTAXES ,W?GET>>"
        )
