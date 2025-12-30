# ZILF Object Tests for Zorkie
# ============================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests.Integration/ObjectTests.cs
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
Tests for ZIL object system.

These tests verify that the zorkie compiler correctly handles:
- Object numbering and tree ordering
- Attribute (flag) numbering and limits
- Property definitions (PROPDEF/PROPSPEC)
- Object properties and flags
- Direction properties
"""

import pytest
from .conftest import AssertRoutine, AssertGlobals


def tree_implications(numbering, *contents_specs):
    """
    Generate implications for object tree structure.

    Args:
        numbering: List of object names in expected number order (low to high)
        contents_specs: Lists of [container, child1, child2, ...] specs
    """
    implications = []

    # Check numbering order
    for i in range(len(numbering) - 1):
        implications.append(f"<L? ,{numbering[i]} ,{numbering[i+1]}>")

    # Check contents
    for spec in contents_specs:
        container = spec[0]
        children = spec[1:]
        if children:
            # First child
            implications.append(f"<==? <FIRST? ,{container}> ,{children[0]}>")
            # Sibling chain
            for i in range(len(children) - 1):
                implications.append(f"<==? <NEXT? ,{children[i]}> ,{children[i+1]}>")
            # Last child has no sibling
            implications.append(f"<0? <NEXT? ,{children[-1]}>>")

    return implications


class TestObjectNumberingAndOrdering:
    """Tests for object numbering and tree ordering."""

    def test_contents_default_order(self):
        """Test default object ordering with contents."""
        AssertGlobals(
            "<OBJECT RAINBOW>",
            "<OBJECT RED (IN RAINBOW)>",
            "<OBJECT YELLOW (IN RAINBOW)>",
            "<OBJECT GREEN (IN RAINBOW)>",
            "<OBJECT BLUE (IN RAINBOW)>"
        ).implies(*tree_implications(
            ["BLUE", "GREEN", "YELLOW", "RED", "RAINBOW"],
            ["RAINBOW", "RED", "BLUE", "GREEN", "YELLOW"]
        ))

    def test_house_default_order(self):
        """Test default object ordering with house example."""
        AssertGlobals(
            "<OBJECT FRIDGE (IN KITCHEN)>",
            "<OBJECT SINK (IN KITCHEN)>",
            "<OBJECT MICROWAVE (IN KITCHEN)>",
            "<ROOM KITCHEN (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT FLOOR (IN LOCAL-GLOBALS)>",
            "<ROOM BEDROOM (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT BED (IN BEDROOM)>",
            "<OBJECT ROOMS>",
            "<OBJECT LOCAL-GLOBALS>",
            "<OBJECT CEILING (IN LOCAL-GLOBALS)>"
        ).implies(*tree_implications(
            ["BED", "BEDROOM", "LOCAL-GLOBALS", "CEILING", "FLOOR", "ROOMS",
             "MICROWAVE", "SINK", "KITCHEN", "FRIDGE"],
            ["KITCHEN", "FRIDGE", "MICROWAVE", "SINK"],
            ["BEDROOM", "BED"],
            ["ROOMS", "KITCHEN", "BEDROOM"],
            ["LOCAL-GLOBALS", "FLOOR", "CEILING"]
        ))

    def test_house_objects_rooms_first(self):
        """Test object ordering with ROOMS-FIRST."""
        AssertGlobals(
            "<ORDER-OBJECTS? ROOMS-FIRST>",
            "<OBJECT FRIDGE (IN KITCHEN)>",
            "<OBJECT SINK (IN KITCHEN)>",
            "<OBJECT MICROWAVE (IN KITCHEN)>",
            "<ROOM KITCHEN (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT FLOOR (IN LOCAL-GLOBALS)>",
            "<ROOM BEDROOM (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT BED (IN BEDROOM)>",
            "<OBJECT ROOMS>",
            "<OBJECT LOCAL-GLOBALS>",
            "<OBJECT CEILING (IN LOCAL-GLOBALS)>"
        ).implies(*tree_implications(
            ["KITCHEN", "BEDROOM", "FRIDGE", "SINK", "MICROWAVE", "ROOMS",
             "FLOOR", "CEILING", "LOCAL-GLOBALS", "BED"],
            ["KITCHEN", "FRIDGE", "MICROWAVE", "SINK"],
            ["BEDROOM", "BED"],
            ["ROOMS", "KITCHEN", "BEDROOM"],
            ["LOCAL-GLOBALS", "FLOOR", "CEILING"]
        ))

    def test_house_objects_rooms_and_lgs_first(self):
        """Test object ordering with ROOMS-AND-LGS-FIRST."""
        AssertGlobals(
            "<ORDER-OBJECTS? ROOMS-AND-LGS-FIRST>",
            "<OBJECT FRIDGE (IN KITCHEN)>",
            "<OBJECT SINK (IN KITCHEN)>",
            "<OBJECT MICROWAVE (IN KITCHEN)>",
            "<ROOM KITCHEN (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT FLOOR (IN LOCAL-GLOBALS)>",
            "<ROOM BEDROOM (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT BED (IN BEDROOM)>",
            "<OBJECT ROOMS>",
            "<OBJECT LOCAL-GLOBALS>",
            "<OBJECT CEILING (IN LOCAL-GLOBALS)>"
        ).implies(*tree_implications(
            ["KITCHEN", "FLOOR", "CEILING", "BEDROOM", "FRIDGE", "SINK",
             "MICROWAVE", "ROOMS", "LOCAL-GLOBALS", "BED"],
            ["KITCHEN", "FRIDGE", "MICROWAVE", "SINK"],
            ["BEDROOM", "BED"],
            ["ROOMS", "KITCHEN", "BEDROOM"],
            ["LOCAL-GLOBALS", "FLOOR", "CEILING"]
        ))

    def test_house_objects_rooms_last(self):
        """Test object ordering with ROOMS-LAST."""
        AssertGlobals(
            "<ORDER-OBJECTS? ROOMS-LAST>",
            "<OBJECT FRIDGE (IN KITCHEN)>",
            "<OBJECT SINK (IN KITCHEN)>",
            "<OBJECT MICROWAVE (IN KITCHEN)>",
            "<ROOM KITCHEN (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT FLOOR (IN LOCAL-GLOBALS)>",
            "<ROOM BEDROOM (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT BED (IN BEDROOM)>",
            "<OBJECT ROOMS>",
            "<OBJECT LOCAL-GLOBALS>",
            "<OBJECT CEILING (IN LOCAL-GLOBALS)>"
        ).implies(*tree_implications(
            ["FRIDGE", "SINK", "MICROWAVE", "ROOMS", "FLOOR", "CEILING",
             "LOCAL-GLOBALS", "BED", "KITCHEN", "BEDROOM"],
            ["KITCHEN", "FRIDGE", "MICROWAVE", "SINK"],
            ["BEDROOM", "BED"],
            ["ROOMS", "KITCHEN", "BEDROOM"],
            ["LOCAL-GLOBALS", "FLOOR", "CEILING"]
        ))

    def test_house_objects_defined(self):
        """Test object ordering with DEFINED (definition order)."""
        AssertGlobals(
            "<ORDER-OBJECTS? DEFINED>",
            "<OBJECT FRIDGE (IN KITCHEN)>",
            "<OBJECT SINK (IN KITCHEN)>",
            "<OBJECT MICROWAVE (IN KITCHEN)>",
            "<ROOM KITCHEN (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT FLOOR (IN LOCAL-GLOBALS)>",
            "<ROOM BEDROOM (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT BED (IN BEDROOM)>",
            "<OBJECT ROOMS>",
            "<OBJECT LOCAL-GLOBALS>",
            "<OBJECT CEILING (IN LOCAL-GLOBALS)>"
        ).implies(*tree_implications(
            ["FRIDGE", "SINK", "MICROWAVE", "KITCHEN", "FLOOR", "BEDROOM",
             "BED", "ROOMS", "LOCAL-GLOBALS", "CEILING"],
            ["KITCHEN", "FRIDGE", "MICROWAVE", "SINK"],
            ["BEDROOM", "BED"],
            ["ROOMS", "KITCHEN", "BEDROOM"],
            ["LOCAL-GLOBALS", "FLOOR", "CEILING"]
        ))

    def test_house_tree_reverse_defined(self):
        """Test tree ordering with REVERSE-DEFINED for house example."""
        AssertGlobals(
            "<ORDER-TREE? REVERSE-DEFINED>",
            "<OBJECT FRIDGE (IN KITCHEN)>",
            "<OBJECT SINK (IN KITCHEN)>",
            "<OBJECT MICROWAVE (IN KITCHEN)>",
            "<ROOM KITCHEN (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<ROOM BEDROOM (IN ROOMS) (GLOBAL FLOOR CEILING)>",
            "<OBJECT BED (IN BEDROOM)>",
            "<OBJECT ROOMS>",
            "<OBJECT LOCAL-GLOBALS>",
            "<OBJECT FLOOR (IN LOCAL-GLOBALS)>",
            "<OBJECT CEILING (IN LOCAL-GLOBALS)>"
        ).implies(*tree_implications(
            ["LOCAL-GLOBALS", "BED", "BEDROOM", "CEILING", "FLOOR", "ROOMS",
             "MICROWAVE", "SINK", "KITCHEN", "FRIDGE"],
            ["KITCHEN", "MICROWAVE", "SINK", "FRIDGE"],
            ["BEDROOM", "BED"],
            ["ROOMS", "BEDROOM", "KITCHEN"],
            ["LOCAL-GLOBALS", "CEILING", "FLOOR"]
        ))

    def test_contents_tree_reverse_defined(self):
        """Test tree ordering with REVERSE-DEFINED."""
        AssertGlobals(
            "<ORDER-TREE? REVERSE-DEFINED>",
            "<OBJECT RAINBOW>",
            "<OBJECT RED (IN RAINBOW)>",
            "<OBJECT YELLOW (IN RAINBOW)>",
            "<OBJECT GREEN (IN RAINBOW)>",
            "<OBJECT BLUE (IN RAINBOW)>"
        ).implies(*tree_implications(
            ["BLUE", "GREEN", "YELLOW", "RED", "RAINBOW"],
            ["RAINBOW", "BLUE", "GREEN", "YELLOW", "RED"]
        ))


class TestAttributeNumbering:
    """Tests for attribute (flag) numbering."""

    def test_bits_mentioned_in_find_must_be_nonzero(self):
        """Test that bits used in FIND must be non-zero."""
        AssertGlobals(
            "<OBJECT FOO (FLAGS F1BIT F2BIT F3BIT F4BIT F5BIT F6BIT F7BIT F8BIT "
            "F9BIT F10BIT F11BIT F12BIT F13BIT F14BIT F15BIT F16BIT "
            "F17BIT F18BIT F19BIT F20BIT F21BIT F22BIT F23BIT F24BIT "
            "F25BIT F26BIT F27BIT F28BIT F29BIT F30BIT F31BIT F32BIT)>",
            "<SYNTAX BAR OBJECT (FIND F1BIT) WITH OBJECT (FIND F2BIT) = V-BAR>",
            "<SYNTAX BAZ OBJECT (FIND F31BIT) WITH OBJECT (FIND F32BIT) = V-BAZ>",
            "<ROUTINE V-BAR () <>>",
            "<ROUTINE V-BAZ () <>>"
        ).implies(
            "<NOT <0? ,F1BIT>>",
            "<NOT <0? ,F2BIT>>",
            "<NOT <0? ,F31BIT>>",
            "<NOT <0? ,F32BIT>>"
        )

    def test_bit_synonym_should_work_in_flags(self):
        """Test that bit synonyms work in FLAGS."""
        AssertRoutine(
            "",
            "<AND <==? ,MAINBIT ,ALIASBIT> <FSET? ,FOO ,MAINBIT> <FSET? ,BAR ,ALIASBIT>>"
        ).with_global("<BIT-SYNONYM MAINBIT ALIASBIT>") \
            .with_global("<OBJECT FOO (FLAGS MAINBIT)>") \
            .with_global("<OBJECT BAR (FLAGS ALIASBIT)>") \
            .gives_number("1")

    def test_bit_synonym_should_not_be_clobbered_by_find(self):
        """Test that bit synonyms aren't clobbered by FIND."""
        AssertRoutine("", "<==? ,MAINBIT ,ALIASBIT>") \
            .with_global("<BIT-SYNONYM MAINBIT ALIASBIT>") \
            .with_global("<OBJECT FOO (FLAGS MAINBIT)>") \
            .with_global("<OBJECT BAR (FLAGS ALIASBIT)>") \
            .with_global("<SYNTAX FOO OBJECT (FIND ALIASBIT) = V-FOO>") \
            .with_global("<ROUTINE V-FOO () <>>") \
            .gives_number("1")

    def test_bit_synonym_should_work_even_if_original_never_set(self):
        """Test that bit synonyms work even if original is never set."""
        AssertGlobals(
            "<BIT-SYNONYM MAINBIT ALIASBIT>",
            "<OBJECT FOO (FLAGS ALIASBIT)>"
        ).compiles()

    def test_too_many_bits_should_fail(self):
        """Test that too many bits causes compilation failure."""
        # V3 limit: 32 flags
        bits_v3 = " ".join(f"TESTBIT{i}" for i in range(33))
        AssertGlobals(f"<OBJECT FOO (FLAGS {bits_v3})>") \
            .in_v3() \
            .does_not_compile("ZIL0404")

        # V4+ limit: 48 flags
        bits_v4 = " ".join(f"TESTBIT{i}" for i in range(49))
        AssertGlobals(f"<OBJECT FOO (FLAGS {bits_v4})>") \
            .in_v4() \
            .does_not_compile()

    def test_too_many_properties_should_fail(self):
        """Test that too many properties causes compilation failure."""
        # V3 limit
        propdefs = "\n".join(f"<PROPDEF P{i} <>>" for i in range(32))
        AssertGlobals(propdefs) \
            .in_v3() \
            .does_not_compile("ZIL0404")

        # V4+ limit: 63
        propdefs = "\n".join(f"<PROPDEF P{i} <>>" for i in range(64))
        AssertGlobals(propdefs) \
            .in_v4() \
            .does_not_compile("ZIL0404")


class TestPropdef:
    """Tests for PROPDEF and PROPSPEC."""

    def test_propdef_basic_pattern(self):
        """Test basic PROPDEF pattern matching."""
        AssertGlobals(
            "<PROPDEF HEIGHT <> "
            " (HEIGHT FEET:FIX FOOT INCHES:FIX = 2 <WORD .FEET> <BYTE .INCHES>)"
            " (HEIGHT FEET:FIX FT INCHES:FIX = 2 <WORD .FEET> <BYTE .INCHES>)>",
            "<OBJECT GIANT (HEIGHT 10 FT 8)>"
        ).implies(
            "<=? <GET <GETPT ,GIANT ,P?HEIGHT> 0> 10>",
            "<=? <GETB <GETPT ,GIANT ,P?HEIGHT> 2> 8>"
        )

    def test_propdef_opt(self):
        """Test PROPDEF with optional elements."""
        AssertGlobals(
            '<PROPDEF HEIGHT <> '
            ' (HEIGHT FEET:FIX FT "OPT" INCHES:FIX = <WORD .FEET> <BYTE .INCHES>)>',
            "<OBJECT GIANT1 (HEIGHT 100 FT)>",
            "<OBJECT GIANT2 (HEIGHT 50 FT 11)>"
        ).implies(
            "<=? <PTSIZE <GETPT ,GIANT1 ,P?HEIGHT>> 3>",
            "<=? <GET <GETPT ,GIANT1 ,P?HEIGHT> 0> 100>",
            "<=? <GETB <GETPT ,GIANT1 ,P?HEIGHT> 2> 0>",
            "<=? <PTSIZE <GETPT ,GIANT2 ,P?HEIGHT>> 3>",
            "<=? <GET <GETPT ,GIANT2 ,P?HEIGHT> 0> 50>",
            "<=? <GETB <GETPT ,GIANT2 ,P?HEIGHT> 2> 11>"
        )

    def test_propdef_many(self):
        """Test PROPDEF with MANY modifier."""
        AssertGlobals(
            '<PROPDEF TRANSLATE <> '
            ' (TRANSLATE "MANY" A:ATOM N:FIX = "MANY" <VOC .A BUZZ> <WORD .N>)>',
            "<OBJECT NUMBERS (TRANSLATE ONE 1 TWO 2)>"
        ).implies(
            "<=? <PTSIZE <GETPT ,NUMBERS ,P?TRANSLATE>> 8>",
            "<=? <GET <GETPT ,NUMBERS ,P?TRANSLATE> 0> ,W?ONE>",
            "<=? <GET <GETPT ,NUMBERS ,P?TRANSLATE> 1> 1>",
            "<=? <GET <GETPT ,NUMBERS ,P?TRANSLATE> 2> ,W?TWO>",
            "<=? <GET <GETPT ,NUMBERS ,P?TRANSLATE> 3> 2>"
        )

    def test_propdef_constants(self):
        """Test PROPDEF with constant definitions."""
        AssertGlobals(
            "<PROPDEF HEIGHT <> "
            " (HEIGHT FEET:FIX FT INCHES:FIX = (HEIGHTSIZE 3) (H-FEET <WORD .FEET>) (H-INCHES <BYTE .INCHES>))>"
        ).implies(
            "<=? ,HEIGHTSIZE 3>",
            "<=? ,H-FEET 0>",
            "<=? ,H-INCHES 2>"
        )

    def test_propdef_with_empty_form_for_length(self):
        """Test PROPDEF with empty form for length."""
        AssertGlobals(
            "<PROPDEF HEIGHT <> "
            " (HEIGHT FEET:FIX FT INCHES:FIX = <> (H-FEET <WORD .FEET>) (H-INCHES <BYTE .INCHES>))>"
        ).compiles()

    def test_propdef_for_directions_used_for_all_directions(self):
        """Test that PROPDEF for DIRECTIONS applies to all directions."""
        AssertGlobals(
            "<PROPDEF DIRECTIONS <> "
            " (DIR GOES TO R:ROOM = (MY-UEXIT 3) <WORD 0> (MY-REXIT <ROOM .R>))>",
            "<DIRECTIONS NORTH SOUTH>",
            "<OBJECT HOUSE (SOUTH GOES TO WOODS)>",
            "<OBJECT WOODS (NORTH GOES TO HOUSE)>"
        ).implies(
            "<=? <PTSIZE <GETPT ,HOUSE ,P?SOUTH>> ,MY-UEXIT>",
            "<=? <GETB <GETPT ,HOUSE ,P?SOUTH> ,MY-REXIT> ,WOODS>"
        )

    def test_clearing_propspec_for_directions_overrides_default(self):
        """Test that clearing PROPSPEC overrides default patterns."""
        AssertGlobals(
            "<PUTPROP DIRECTIONS PROPSPEC>",
            "<DIRECTIONS NORTH SOUTH>",
            "<OBJECT HOUSE (SOUTH TO WOODS)>",
            "<OBJECT WOODS (NORTH TO HOUSE)>"
        ).does_not_compile()

    @pytest.mark.xfail(reason="PROPDEF for implicit directions not implemented")
    def test_propdef_for_directions_can_be_used_for_implicit_directions(self):
        """Test that PROPDEF for DIRECTIONS can be used for implicit directions."""
        AssertGlobals(
            "<PROPDEF DIRECTIONS <> "
            " (DIR GOES TO R:ROOM = (MY-UEXIT 3) <WORD 0> (MY-REXIT <ROOM .R>))>",
            "<DIRECTIONS NORTH SOUTH>",
            "<OBJECT HOUSE (EAST GOES TO WOODS)>",
            "<OBJECT WOODS (WEST GOES TO HOUSE)>"
        ).implies(
            "<=? <PTSIZE <GETPT ,HOUSE ,P?EAST>> ,MY-UEXIT>",
            "<=? <GETB <GETPT ,HOUSE ,P?EAST> ,MY-REXIT> ,WOODS>",
            "<BAND <GETB ,W?EAST 4> ,PS?DIRECTION>"
        )

    @pytest.mark.xfail(reason="PROPDEF DIRECTIONS property name suppression not implemented")
    def test_propdef_for_directions_should_not_create_directions_property(self):
        """Test that PROPDEF for DIRECTIONS doesn't create a DIRECTIONS property."""
        # When using PROPDEF for DIRECTIONS, P?DIRECTIONS should not exist
        AssertGlobals(
            "<FILE-FLAGS KEEP-ROUTINES?>",
            "<PROPDEF DIRECTIONS <> "
            " (DIR GOES TO R:ROOM = (MY-UEXIT 3) <WORD 0> (MY-REXIT <ROOM .R>))>",
            "<DIRECTIONS NORTH SOUTH>",
            "<OBJECT HOUSE (SOUTH GOES TO WOODS)>",
            "<OBJECT WOODS (NORTH GOES TO HOUSE)>",
            "<ROUTINE FOO () ,P?DIRECTIONS>"
        ).does_not_compile()

        AssertGlobals(
            "<PROPDEF DIRECTIONS <> "
            " (DIR GOES TO R:ROOM = (MY-UEXIT 3) <WORD 0> (MY-REXIT <ROOM .R>))>",
            "<DIRECTIONS NORTH SOUTH>",
            "<OBJECT HOUSE (SOUTH GOES TO WOODS)>",
            "<OBJECT WOODS (NORTH GOES TO HOUSE)>"
        ).generates_code_not_matching(r"P\?DIRECTIONS")

    @pytest.mark.xfail(reason="VOC in PROPDEF not implemented")
    def test_vocab_created_by_propdef_should_work_correctly(self):
        """Test that vocab created by PROPDEF works correctly."""
        AssertGlobals(
            "<PROPDEF FOO <> (FOO A:ATOM = <VOC .A PREP>)>",
            "<OBJECT BAR (FOO FOO)>"
        ).implies(
            "<=? <GETP ,BAR ,P?FOO> ,W?FOO>"
        )

    @pytest.mark.xfail(reason="PROPSPEC not implemented")
    def test_vocab_created_by_propspec_should_work_correctly(self):
        """Test that vocab created by PROPSPEC works correctly."""
        AssertGlobals(
            "<PUTPROP FOO PROPSPEC FOO-PROP>",
            '<DEFINE FOO-PROP (L) (<> <EVAL <CHTYPE (TABLE <VOC "FOO" PREP>) FORM>>)>',
            "<OBJECT BAR (FOO FOO)>"
        ).implies(
            "<=? <GET <GETP ,BAR ,P?FOO> 0> ,W?FOO>"
        )

    @pytest.mark.xfail(reason="Routine creation via PROPSPEC not implemented")
    def test_routines_created_by_propspec_should_work_correctly(self):
        """Test that routines created by PROPSPEC work correctly."""
        AssertGlobals(
            "<FILE-FLAGS KEEP-ROUTINES?>",
            "<PUTPROP FOO PROPSPEC FOO-PROP>",
            "<DEFINE FOO-PROP (L) <ROUTINE PROP-ROUTINE () 123> (<> PROP-ROUTINE)>",
            "<OBJECT BAR (FOO FOO)>"
        ).implies(
            "<=? <APPLY <GETP ,BAR ,P?FOO>> 123>"
        )

    @pytest.mark.xfail(reason="ROOM type in PROPDEF not optimized for ROOMS-FIRST")
    def test_room_in_propdef_one_byte_when_rooms_first(self):
        """Test that ROOM in PROPDEF is one byte when ORDER-OBJECTS? is ROOMS-FIRST."""
        AssertGlobals(
            "<ORDER-OBJECTS? ROOMS-FIRST>",
            "<DIRECTIONS NORTH>",
            "<PROPDEF DIRECTIONS <> (DIR TO R:ROOM = (UEXIT 1) (REXIT <ROOM .R>))>",
            "<OBJECT FOO (NORTH TO BAR)>",
            "<OBJECT BAR>"
        ).in_v5() \
            .implies(
                "<=? <PTSIZE <GETPT ,FOO ,P?NORTH>> 1>"
            )


class TestObjectProperties:
    """Tests for object property constraints."""

    def test_non_constants_as_property_values_rejected(self):
        """Test that non-constants as property values are rejected."""
        AssertGlobals(
            "<GLOBAL FOO 123>",
            "<OBJECT BAR (BAZ FOO)>"
        ).does_not_compile()

    def test_non_constants_in_property_initializers_rejected(self):
        """Test that non-constants in property initializers are rejected."""
        AssertGlobals(
            "<GLOBAL FOO 123>",
            "<OBJECT BAR (BAZ 4 5 FOO)>"
        ).does_not_compile()

    def test_nonexistent_object_in_direction_property_warns(self):
        """Test that nonexistent object in direction property compiles with warning.

        ZILCH behavior: warn but don't fail on undefined objects.
        """
        # Should compile (with warnings) - matches ZILCH behavior
        AssertGlobals(
            "<DIRECTIONS NORTH>",
            "<OBJECT FOO (NORTH TO BAR)>"
        ).compiles()

    def test_nonexistent_global_in_direction_property_warns(self):
        """Test that nonexistent global in direction property compiles with warning.

        ZILCH behavior: warn but don't fail on undefined globals.
        """
        # Should compile (with warnings) - matches ZILCH behavior
        AssertGlobals(
            "<DIRECTIONS NORTH>",
            "<OBJECT FOO>",
            "<OBJECT BAR (NORTH TO FOO IF NO-SUCH-GLOBAL)>"
        ).compiles()

    def test_direction_synonyms_work_identically(self):
        """Test that direction synonyms work identically."""
        AssertGlobals(
            "<DIRECTIONS SOUTHWEST>",
            "<SYNONYM SOUTHWEST SW>",
            "<OBJECT FOO (SW TO FOO)>"
        ).in_v3() \
            .implies(
                "<=? ,P?SOUTHWEST ,P?SW>",
                "<=? <GETB ,W?SW 5> ,P?SOUTHWEST>",
                "<=? <GETB ,W?SOUTHWEST 5> ,P?SOUTHWEST>"
            )

    def test_direction_properties_not_merged_with_words(self):
        """Test that direction properties aren't merged with words."""
        AssertGlobals(
            "<DIRECTIONS NORTHNORTHEAST NORTHNORTHWEST>",
            "<OBJECT FOO (NORTHNORTHEAST TO FOO) (NORTHNORTHWEST TO BAR)>",
            "<OBJECT BAR>"
        ).in_v3() \
            .implies(
                "<=? ,W?NORTHNORTHEAST ,W?NORTHNORTHWEST>",
                "<N=? ,P?NORTHNORTHEAST ,P?NORTHNORTHWEST>",
                "<=? <GETP ,FOO ,P?NORTHNORTHEAST> ,FOO>",
                "<=? <GETP ,FOO ,P?NORTHNORTHWEST> ,BAR>"
            )

    def test_duplicate_property_definitions_allowed(self):
        """Test that duplicate property definitions are allowed (ZILCH behavior).

        ZILCH allows duplicate properties - the later value overwrites.
        This is used in some Infocom games (e.g., suspended).
        """
        # user-defined property - second value wins
        AssertGlobals("<OBJECT FOO (MYPROP 1) (MYPROP 2)>") \
            .compiles()

        # standard pseudo-properties - second value wins
        AssertGlobals('<OBJECT FOO (DESC "foo") (DESC "bar")>') \
            .compiles()

        # IN + LOC (same location property) - later value wins (ZILCH behavior)
        AssertGlobals(
            "<OBJECT ROOM1>",
            "<OBJECT ROOM2>",
            "<OBJECT FOO (IN ROOM1) (LOC ROOM2)>"
        ).compiles()

    def test_in_pseudo_property_not_conflict_with_in_string_nexit(self):
        """Test that IN pseudo-property doesn't conflict with IN string NEXIT."""
        AssertGlobals(
            "<DIRECTIONS IN>",
            "<OBJECT ROOMS>",
            '<OBJECT FOO (IN ROOMS) (IN "You can\'t go in.")>'
        ).compiles()

        # even if IN isn't defined as a direction!
        AssertGlobals(
            "<OBJECT ROOMS>",
            '<OBJECT FOO (IN ROOMS) (IN "You can\'t go in.")>'
        ).compiles()

    def test_multiple_flags_definitions_combine(self):
        """Test that multiple FLAGS definitions combine."""
        AssertGlobals("<OBJECT FOO (FLAGS FOOBIT) (FLAGS BARBIT)>") \
            .implies(
                "<FSET? ,FOO ,FOOBIT>",
                "<FSET? ,FOO ,BARBIT>"
            )

    def test_mentioning_routine_as_object_does_not_throw(self):
        """Test that mentioning routine as object doesn't throw."""
        AssertGlobals(
            "<FILE-FLAGS UNUSED-ROUTINES?>",
            '<ROOM WEST-SIDE-OF-FISSURE (DESC "West Side of Fissure")>',
            "<ROUTINE WEST-SIDE-OF-FISSURE-F (RARG) <>>",
            '<OBJECT DIAMONDS (DESC "diamonds") (IN WEST-SIDE-OF-FISSURE-F)>'
        ).without_warnings() \
            .does_not_compile()

    def test_desc_pseudo_property_strips_newlines(self):
        """Test that DESC pseudo-property strips newlines."""
        AssertRoutine("", "<PRINTD ,FOO>") \
            .with_global('<OBJECT FOO (DESC "first\nsecond\r\nthird")>') \
            .outputs("first second third")


class TestUnusedWarnings:
    """Tests for warnings about unused flags/properties."""

    def test_unused_flags_should_warn(self):
        """Test that unused flags generate warnings."""
        # only referenced in one object definition - warning
        AssertGlobals("<OBJECT FOO (FLAGS MYBIT)>") \
            .with_warnings("ZIL0211") \
            .compiles()

        # referenced in two object definitions - warning
        AssertGlobals(
            "<OBJECT FOO (FLAGS MYBIT)>",
            "<OBJECT BAR (FLAGS MYBIT)>"
        ).with_warnings("ZIL0211") \
            .compiles()

        # referenced in a routine - no warning
        AssertRoutine("", "<FCLEAR ,FOO ,MYBIT>") \
            .with_global("<OBJECT FOO (FLAGS MYBIT)>") \
            .without_warnings() \
            .compiles()

        # referenced in syntax - no warning
        AssertGlobals(
            "<OBJECT FOO (FLAGS MYBIT MYBIT2)>",
            "<SYNTAX BLAH OBJECT (FIND MYBIT) WITH OBJECT (FIND MYBIT2) = V-BLAH>",
            "<ROUTINE V-BLAH () <>>"
        ).without_warnings() \
            .compiles()

    def test_unused_properties_should_warn(self):
        """Test that unused properties generate warnings."""
        # only referenced in one object definition - warning
        AssertGlobals("<OBJECT FOO (MYPROP 123)>") \
            .with_warnings("ZIL0212") \
            .compiles()

        # referenced in two object definitions - warning
        AssertGlobals(
            "<OBJECT FOO (MYPROP 123)>",
            "<OBJECT BAR (MYPROP 456)>"
        ).with_warnings("ZIL0212") \
            .compiles()

        # referenced in a routine - no warning
        AssertRoutine("", "<GETP ,FOO ,P?MYPROP>") \
            .with_global("<OBJECT FOO (MYPROP 123)>") \
            .without_warnings() \
            .compiles()

    def test_vocab_properties_with_apostrophes_should_warn(self):
        """Test that vocab properties with apostrophes warn."""
        AssertGlobals("<OBJECT CATS-PAJAMAS (SYNONYM PAJAMAS) (ADJECTIVE CAT'S)>") \
            .with_warnings("MDL0429") \
            .compiles()
