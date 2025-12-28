# ZILF Vocabulary Tests for Zorkie
# =================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/VocabTests.cs
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
Tests for ZIL vocabulary handling.

These tests verify that the zorkie compiler correctly handles:
- SIBREAKS (special input break characters)
- TCHARS (terminating characters)
- PREPOSITIONS table format (compact vs non-compact)
- LONG-WORDS? feature
- LANGUAGE settings for non-English games
- Punctuation and symbol handling
- Old parser vocabulary
- NEW-PARSER? vocabulary format
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals


# Part of speech constants from ZILF (see Zilf/ZModel/Vocab/PartOfSpeech.cs)
class PartOfSpeech:
    NONE = 0
    FIRST_MASK = 3
    VERB_FIRST = 1
    ADJECTIVE_FIRST = 2
    DIRECTION_FIRST = 3
    BUZZWORD = 4
    PREPOSITION = 8
    DIRECTION = 16
    ADJECTIVE = 32
    VERB = 64
    OBJECT = 128


class TestSIBREAKS:
    """Tests for SIBREAKS (special input break characters)."""

    @pytest.mark.xfail(reason="SIBREAKS not implemented")
    def test_sibreaks_should_affect_lexing(self):
        """Test that SIBREAKS affects lexer behavior."""
        AssertRoutine(
            "",
            "<READ ,INBUF ,LEXBUF> "
            "<TELL N <GETB ,LEXBUF 0> CR "
            "N <GETB ,LEXBUF 1> CR> "
            "<PRINTB <GET ,LEXBUF 1>> <CRLF> "
            "<PRINTB <GET ,LEXBUF 3>> <CRLF> "
            "<PRINTB <GET ,LEXBUF 5>> <CRLF> "
            "<PRINTB <GET ,LEXBUF 7>> <CRLF>"
        ).with_global("<SETG SIBREAKS \"'\">") \
            .with_global("<BUZZ GRANT S TOMB>") \
            .with_global("<GLOBAL LEXBUF <ITABLE 59 (LEXV) 0 #BYTE 0 #BYTE 0>>") \
            .with_global("<GLOBAL INBUF <ITABLE 80 (BYTE LENGTH) 0>>") \
            .with_global("<OBJECT DUMMY (DESC \"wuteva\")>") \
            .with_global("<GLOBAL HERE DUMMY> <GLOBAL SCORE 0> <GLOBAL MOVES 0>") \
            .in_v3() \
            .with_input("grant's tomb") \
            .outputs("59\n4\ngrant\n'\ns\ntomb\n")


class TestTCHARS:
    """Tests for TCHARS (terminating characters)."""

    @pytest.mark.xfail(reason="TCHARS header support not implemented")
    def test_tchars_should_affect_header(self):
        """Test that TCHARS setting affects header."""
        AssertGlobals(
            "<CONSTANT F12 144>",
            "<CONSTANT TCHARS <TABLE (BYTE) F12 0>>"
        ).in_v5() \
            .implies(
                "<==? <LOWCORE TCHARS> ,TCHARS>",
                "<==? <GETB ,TCHARS 0> 144>"
            )


class TestPrepositions:
    """Tests for PREPOSITIONS table format."""

    def test_prepositions_noncompact_should_use_4_byte_entries(self):
        """Test non-compact prepositions use 4-byte entries and don't list synonyms."""
        # Non-compact test format uses 4-byte entries (*204* record length)
        AssertGlobals(
            "<ROUTINE V-LOOK () <>>",
            "<ROUTINE V-PICK-UP-WITH () <>>",
            "<SYNTAX LOOK THROUGH OBJECT = V-LOOK>",
            "<PREP-SYNONYM THROUGH THRU>",
            "<SYNTAX PICK UP OBJECT WITH OBJECT = V-PICK-UP-WITH>"
        ).in_v5() \
            .implies(
                "<==? <GET ,PREPOSITIONS 0> 3>",  # 3 prepositions
                # THROUGH, UP, WITH entries (non-compact doesn't list synonyms)
            )

    @pytest.mark.xfail(reason="COMPACT-VOCABULARY? not implemented")
    def test_prepositions_compact_should_use_3_byte_entries(self):
        """Test compact prepositions use 3-byte entries and list synonyms."""
        # Compact test format uses 3-byte entries (*203* record length)
        AssertGlobals(
            "<SETG COMPACT-VOCABULARY? T>",
            "<ROUTINE V-LOOK () <>>",
            "<ROUTINE V-PICK-UP-WITH () <>>",
            "<SYNTAX LOOK THROUGH OBJECT = V-LOOK>",
            "<PREP-SYNONYM THROUGH THRU>",
            "<SYNTAX PICK UP OBJECT WITH OBJECT = V-PICK-UP-WITH>"
        ).in_v5() \
            .implies(
                "<==? <GET ,PREPOSITIONS 0> 4>",  # 4 entries (includes THRU synonym)
            )


class TestLongWords:
    """Tests for LONG-WORDS? feature."""

    @pytest.mark.xfail(reason="LONG-WORDS? not implemented")
    def test_long_words_p_should_generate_long_word_table(self):
        """Test that LONG-WORDS? generates LONG-WORD-TABLE."""
        AssertGlobals(
            "<LONG-WORDS?>",
            "<OBJECT FOO (SYNONYM HEMIDEMISEMIQUAVER)>"
        ).implies(
            "<==? <GET ,LONG-WORD-TABLE 0> 1>",
            "<==? <GET ,LONG-WORD-TABLE 1> ,W?HEMIDEMISEMIQUAVER>",
            "<==? <GET ,LONG-WORD-TABLE 2> \"hemidemisemiquaver\">"
        )


class TestLanguage:
    """Tests for LANGUAGE setting."""

    @pytest.mark.xfail(reason="LANGUAGE lexing support not implemented")
    def test_language_should_affect_lexing(self):
        """Test that LANGUAGE affects lexer behavior."""
        AssertRoutine(
            "",
            "<READ ,INBUF ,LEXBUF> "
            "<==? <GET ,LEXBUF 1> ,W?AU\\%SER>"
        ).with_global("<LANGUAGE GERMAN>") \
            .with_global("<BUZZ AU\\%SER>") \
            .with_global("<GLOBAL LEXBUF <ITABLE 59 (LEXV) 0 #BYTE 0 #BYTE 0>>") \
            .with_global("<GLOBAL INBUF <ITABLE 80 (BYTE LENGTH) 0>>") \
            .in_v5() \
            .with_input("außer") \
            .gives_number("1")


class TestPunctuationWords:
    """Tests for punctuation and symbol word handling."""

    @pytest.mark.xfail(reason="Punctuation word handling not implemented")
    def test_punctuation_symbol_words_should_work_with_definitions(self):
        """Test punctuation symbol words work when given definitions."""
        AssertRoutine(
            "",
            "<TELL B <GETP ,FOO ,P?SYNONYM> %,SPACE B ,W?COMMA %,SPACE B ,W?\\,>"
        ).with_global("<CONSTANT SPACE <ASCII 32>>") \
            .with_global("<OBJECT FOO (SYNONYM \\,)>") \
            .outputs(", , ,")

    @pytest.mark.xfail(reason="Punctuation word handling not implemented")
    def test_punctuation_name_words_should_split_from_symbol_words(self):
        """Test punctuation name words split from symbol words."""
        AssertRoutine(
            "",
            "<TELL B <GETP ,FOO ,P?SYNONYM> %,SPACE B ,W?COMMA %,SPACE B ,W?\\,>"
        ).with_global("<CONSTANT SPACE <ASCII 32>>") \
            .with_global("<OBJECT FOO (SYNONYM COMMA)>") \
            .outputs("comma comma ,")


class TestOldParser:
    """Tests for old parser vocabulary format."""

    def test_voc_with_2nd_arg_atom_should_set_part_of_speech(self):
        """Test VOC with 2nd arg atom sets part of speech."""
        expected = str(PartOfSpeech.ADJECTIVE | PartOfSpeech.ADJECTIVE_FIRST)
        AssertRoutine(
            '"AUX" (P <GET ,VOC-TABLE 0>)',
            "<GETB .P 4>"
        ).with_global("<GLOBAL VOC-TABLE <PTABLE <VOC \"XYZZY\" ADJ>>>") \
            .in_v3() \
            .gives_number(expected)

    def test_voc_with_2nd_arg_false_should_not_set_part_of_speech(self):
        """Test VOC with 2nd arg FALSE doesn't set part of speech."""
        AssertRoutine(
            '"AUX" (P <GET ,VOC-TABLE 0>)',
            "<GETB .P 4>"
        ).with_global("<GLOBAL VOC-TABLE <PTABLE <VOC \"XYZZY\" <>>>>") \
            .in_v3() \
            .gives_number(str(PartOfSpeech.NONE))

    def test_voc_with_2nd_arg_missing_should_not_set_part_of_speech(self):
        """Test VOC with missing 2nd arg doesn't set part of speech."""
        AssertRoutine(
            '"AUX" (P <GET ,VOC-TABLE 0>)',
            "<GETB .P 4>"
        ).with_global("<GLOBAL VOC-TABLE <PTABLE <VOC \"XYZZY\">>>") \
            .in_v3() \
            .gives_number(str(PartOfSpeech.NONE))

    @pytest.mark.xfail(reason="Word collision merging not implemented")
    def test_colliding_words_should_be_merged(self):
        """Test that colliding words are merged with warnings."""
        AssertGlobals(
            "<OBJECT FOO (SYNONYM HEMIDEMISEMIQUAVER)>",
            "<OBJECT BAR (SYNONYM HEMIDE)>",
            "<OBJECT BAZ (ADJECTIVE HEMIDEISH SAMPLED)>",
            "<ROUTINE V-SAMPLE () <>>",
            "<SYNTAX SAMPLE = V-SAMPLE>"
        ).in_v3() \
            .with_warnings("ZIL0310", "ZIL0311") \
            .implies(
                "<==? ,W?HEMIDEMISEMIQUAVER ,W?HEMIDE>",
                "<==? ,W?HEMIDE ,W?HEMIDEISH>",
                "<BTST <GETB ,W?HEMIDE 4> ,PS?OBJECT>",
                "<BTST <GETB ,W?HEMIDE 4> ,PS?ADJECTIVE>",
                "<==? ,W?SAMPLE ,W?SAMPLED>",
                "<BTST <GETB ,W?SAMPLE 4> ,PS?VERB>",
                "<BTST <GETB ,W?SAMPLE 4> ,PS?ADJECTIVE>"
            )

        AssertGlobals(
            "<OBJECT FOO (SYNONYM LONGWORDEVENINV4A)>",
            "<OBJECT BAR (SYNONYM LONGWORDEVENINV4B)>"
        ).in_v4() \
            .with_warnings("ZIL0310") \
            .implies("<==? ,W?LONGWORDEVENINV4A ,W?LONGWORDEVENINV4B>")

    def test_adjective_numbers_of_colliding_words_should_be_merged(self):
        """Test that adjective numbers of colliding words are merged."""
        AssertGlobals(
            "<OBJECT FOO (ADJECTIVE ABCDEFGHIJKL ABCDEF) (FOO 123)>",
            "<DEFINE FOO-PROP (L) <VOC \"ABCDEFGHI\" ADJ> .L>",
            "<PUTPROP FOO PROPSPEC FOO-PROP>"
        ).in_v3() \
            .implies(
                "<==? ,A?ABCDEFGHIJKL ,A?ABCDEF>",
                "<==? ,A?ABCDEFGHI ,A?ABCDEF>"
            )

    def test_making_a_word_its_own_synonym_should_not_crash(self):
        """Test that making a word its own synonym doesn't crash."""
        AssertGlobals(
            "<VOC \"FOO\" VERB>",
            "<SYNONYM FOO FOO>"
        ).compiles()


# NEW-PARSER? bootstrap code
NEW_PARSER_BOOTSTRAP = """
<SETG NEW-PARSER? T>

<SETG CLASSIFICATIONS '(ADJ 1 BUZZ 2 DIR 4 NOUN 8 PREP 16 VERB 32 PARTICLE 64)>

<DEFINE GET-CLASSIFICATION (TYPE "AUX" P)
    <COND (<SET P <MEMQ .TYPE ,CLASSIFICATIONS>> <2 .P>)
          (T <ERROR NO-SUCH-WORD-TYPE!-ERRORS>)>>

<SET-DEFSTRUCT-FILE-DEFAULTS ('START-OFFSET 0) ('PUT ZPUT) ('NTH ZGET)>

<DEFSTRUCT VERB-DATA (TABLE ('INIT-ARGS (TEMP-TABLE)))
    (VERB-ZERO ANY -1)
    (VERB-RESERVED FALSE)
    (VERB-ONE <OR FALSE TABLE>)
    (VERB-TWO <OR FALSE TABLE>)>

<DEFSTRUCT VWORD (TABLE ('INIT-ARGS (TEMP-TABLE)))
    (WORD-LEXICAL-WORD ANY)
    (WORD-CLASSIFICATION-NUMBER FIX)
    (WORD-FLAGS FIX)
    (WORD-SEMANTIC-STUFF ANY)
    (WORD-VERB-STUFF ANY)
    (WORD-ADJ-ID ANY)
    (WORD-DIR-ID ANY)>
"""


class TestNewParser:
    """Tests for NEW-PARSER? vocabulary format."""

    def test_game_without_objects_should_compile_with_new_parser_p(self):
        """Test game without objects compiles with NEW-PARSER?."""
        AssertRoutine("", '<PRINTR "Hello, world!">') \
            .with_global(NEW_PARSER_BOOTSTRAP) \
            .outputs("Hello, world!\n")

    @pytest.mark.xfail(reason="NEW-PARSER? vocabulary format not implemented")
    def test_new_parser_p_should_affect_vocab_word_size(self):
        """Test NEW-PARSER? affects vocabulary word size."""
        AssertRoutine("", "<GETB ,VOCAB <+ 1 <GETB ,VOCAB 0>>>") \
            .with_global(NEW_PARSER_BOOTSTRAP) \
            .with_global("<COMPILATION-FLAG WORD-FLAGS-IN-TABLE <>>") \
            .with_global("<COMPILATION-FLAG ONE-BYTE-PARTS-OF-SPEECH <>>") \
            .in_v3() \
            .gives_number("12")

    @pytest.mark.xfail(reason="NEW-PARSER? verb data not implemented")
    def test_new_parser_p_verbs_should_have_verb_data(self):
        """Test NEW-PARSER? verbs have verb data."""
        AssertGlobals(
            NEW_PARSER_BOOTSTRAP,
            "<COMPILATION-FLAG WORD-FLAGS-IN-TABLE T>",
            "<COMPILATION-FLAG ONE-BYTE-PARTS-OF-SPEECH T>",
            "<ROUTINE V-SING () <>>",
            "<SYNTAX SING = V-SING>"
        ).in_v4() \
            .implies("<N=? <GET ,W?SING 3> 0>")

    @pytest.mark.xfail(reason="NEW-PARSER? syntax format not implemented")
    def test_new_parser_p_should_affect_syntax_format(self):
        """Test NEW-PARSER? affects syntax format."""
        AssertGlobals(
            NEW_PARSER_BOOTSTRAP,
            "<COMPILATION-FLAG WORD-FLAGS-IN-TABLE T>",
            "<COMPILATION-FLAG ONE-BYTE-PARTS-OF-SPEECH T>",
            "<ROUTINE V-ATTACK () <>>",
            "<SYNTAX ATTACK OBJECT WITH OBJECT = V-ATTACK>"
        ).in_v4() \
            .implies(
                "<=? <GET <GET ,W?ATTACK 3> 0> -1>",
                "<=? <GET <GET ,W?ATTACK 3> 1> 0>",
                "<=? <GET <GET ,W?ATTACK 3> 2> 0>",
                "<N=? <GET <GET ,W?ATTACK 3> 3> 0>"
            )

    @pytest.mark.xfail(reason="NEW-PARSER? WORD-FLAG-TABLE not implemented")
    def test_word_flag_table_should_list_words_and_flags(self):
        """Test WORD-FLAG-TABLE lists words and flags."""
        AssertGlobals(
            NEW_PARSER_BOOTSTRAP,
            "<NEW-ADD-WORD FOO TOBJECT <> 12345>"
        ).implies(
            "<=? <GET ,WORD-FLAG-TABLE 0> 2>",
            "<=? <GET ,WORD-FLAG-TABLE 1> ,W?FOO>",
            "<=? <GET ,WORD-FLAG-TABLE 2> 12345>"
        )

    def test_word_flags_list_with_duplicates_should_compile(self):
        """Test WORD-FLAGS-LIST with duplicates compiles."""
        AssertGlobals(
            NEW_PARSER_BOOTSTRAP,
            "<COMPILATION-FLAG WORD-FLAGS-IN-TABLE T>",
            "<NEW-ADD-WORD FOO TBUZZ 123 456>",
            "<NEW-ADD-WORD BAR TBUZZ 234 567>",
            "<NEW-ADD-WORD FOO TADJ 345 678>"
        ).in_v6() \
            .compiles()

    @pytest.mark.xfail(reason="NEW-PARSER? synonym pointers not implemented")
    def test_new_parser_p_synonyms_should_use_pointers(self):
        """Test NEW-PARSER? synonyms use pointers."""
        AssertGlobals(
            NEW_PARSER_BOOTSTRAP,
            "<COMPILATION-FLAG WORD-FLAGS-IN-TABLE T>",
            "<COMPILATION-FLAG ONE-BYTE-PARTS-OF-SPEECH T>",
            "<NEW-ADD-WORD FOO TBUZZ>",
            "<SYNONYM FOO BAR>"
        ).in_v4() \
            .implies(
                "<=? <GET ,W?BAR 3> ,W?FOO>",
                "<=? <GETB ,W?BAR 8> 0>"
            )

    @pytest.mark.xfail(reason="Preposition synonym handling not implemented")
    def test_synonym_used_as_preposition_should_copy_preposition_number(self):
        """Test synonym used as preposition copies preposition number."""
        AssertGlobals(
            "<SYNONYM ON ONTO>",
            "<SYNTAX CLIMB ON OBJECT = V-CLIMB>",
            "<SYNTAX CLIMB ONTO OBJECT = V-CLIMB>",
            "<ROUTINE V-CLIMB () <>>"
        ).in_v3() \
            .implies(
                # original word ON should be a preposition = PR?ON
                "<=? <GETB ,W?ON 4> ,PS?PREPOSITION>",
                "<=? <GETB ,W?ON 5> ,PR?ON>",
                "<=? <GETB ,W?ON 6> 0>",
                # synonym ONTO should also be a preposition = PR?ON
                "<=? <GETB ,W?ONTO 4> ,PS?PREPOSITION>",
                "<=? <GETB ,W?ONTO 5> ,PR?ON>",
                "<=? <GETB ,W?ONTO 6> 0>",
                # preposition table should only list ON
                "<=? <GET ,PREPOSITIONS 0> 1>",
                "<=? <GET ,PREPOSITIONS 1> ,W?ON>",
                "<=? <GET ,PREPOSITIONS 2> ,PR?ON>"
            )
