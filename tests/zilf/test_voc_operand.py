r"""Regression tests for <VOC "word" pos> in expression position.

gen_voc used to return b'' ("VOC as a statement is a no-op"), so every
comparison site that routed a VOC FormNode through generate_form (gen_equal,
the COND condition-test EQUAL? arms, _resolve_two_cmp_operands) pushed NOTHING
and then emitted `je x,(sp)` -- popping stale stack garbage. The ZILF standard
library's macro-generated EXPAND-PRONOUN does exactly `<=? .W <VOC "it"
OBJECT>>` per pronoun, so pronoun matching returned interpreter-dependent
nonsense (dfrotz read its own local slots and garbled cloak's "read message"
turn; zwalker popped the caller's values). gen_voc now PUSHES the dictionary
word's address via the in-code vocab marker.
"""
from .conftest import AssertRoutine


def test_voc_as_equal_comparand_is_word_address_not_stack_garbage():
    # The word address is a real nonzero dictionary address; comparing it to 0
    # must be false. Under the old bug the comparand was whatever a stack pop
    # yielded (0 on an empty lenient stack), so EQUAL? 0 ... came out "true".
    AssertRoutine(
        "",
        '<COND (<EQUAL? 0 <VOC "xyzzy" OBJECT>> <PRINTI "broken">)'
        '      (T <PRINTI "ok">)>'
    ).outputs("ok")


def test_voc_comparand_matches_itself():
    # Two references to the same word must resolve to the same address.
    AssertRoutine(
        "",
        '<COND (<EQUAL? <VOC "plugh" OBJECT> <VOC "plugh" OBJECT>>'
        '       <PRINTI "same">)'
        '      (T <PRINTI "diff">)>'
    ).outputs("same")
