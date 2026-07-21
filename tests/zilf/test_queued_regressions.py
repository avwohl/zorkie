r"""Regression tests for a batch of codegen/parser fixes found via
dfrotz-vs-zwalker lockstep diffing on the ZILF-library games.

1. Bare char literals as general operands: `<PRINTN !\n>` / `<- !\9 !\0>`
   compiled the literal to 0 because _get_operand_type_and_value_ext's
   AtomNode branch lacked the char-literal check the 2OP resolver has.

2. Quoted table flag lists: advent's
   `<TABLE %<VERSION? (ZIP '(BYTE)) (ELSE #SPLICE ())> ...>` preprocesses to
   `<TABLE '(BYTE) ...>`; the parser treated the QUOTEd flag list as a DATA
   element (value 0), shifting every entry and word-typing the table -- so
   advent's ALL-TREASURES scan read zeros and no treasure ever scored.

3. <CONSTANT X <STRING "a" "b">>: the STRING-of-literals value never
   registered X at all ("Unknown global/object" + print at illegal address --
   advent's GAME-BANNER printed dictionary garbage). Folded at preprocess
   time into a single literal.

4. <SPACES n>: the bare builtin was multiply-broken (4-operand PRINT_CHAR
   type byte, DEC_CHK popping its compare value off the stack, off-by-2
   branch offsets). Rewritten with a scratch-global loop.
"""
from .conftest import AssertExpr, AssertRoutine


# --- 1. bare char-literal operands ---------------------------------------

def test_bare_char_literal_as_printn_operand():
    AssertRoutine("", r"<PRINTN !\n>").outputs("110")
    AssertRoutine("", r"<PRINTN !\0>").outputs("48")


def test_bare_char_literal_arithmetic():
    AssertExpr(r"<- !\9 !\0>").gives_number("9")


# --- 2. quoted (BYTE) table flag ------------------------------------------

def test_quoted_byte_flag_table_is_byte_typed():
    # '(BYTE) (as produced by a %<VERSION? ...> splice) must behave exactly
    # like (BYTE): elements are bytes, no shift. GETB 0 is the first element.
    AssertRoutine(
        "",
        '<PRINTN <GETB ,QT 0>> <PRINTI " "> <PRINTN <GETB ,QT 1>>'
    ).with_global("<CONSTANT QT <TABLE '(BYTE) 7 9>>").outputs("7 9")


def test_plain_byte_flag_table_still_works():
    AssertRoutine(
        "",
        '<PRINTN <GETB ,PT 0>> <PRINTI " "> <PRINTN <GETB ,PT 1>>'
    ).with_global("<CONSTANT PT <TABLE (BYTE) 7 9>>").outputs("7 9")


# --- 3. <CONSTANT X <STRING literals...>> ---------------------------------

def test_constant_string_fold_prints():
    AssertRoutine(
        "",
        "<TELL ,GB>"
    ).with_global('<CONSTANT GB <STRING "Hello " "World">>').outputs("Hello World")


# --- 4. <SPACES n> ---------------------------------------------------------

def test_spaces_small_constant():
    AssertRoutine("", '<PRINTI "["> <SPACES 3> <PRINTI "]">').outputs("[   ]")


def test_spaces_large_constant_loop_terminates_exactly():
    # The >80-constant path uses the scratch-global loop. The dumb-terminal
    # harness wraps at 80 columns and strips trailing spaces, so the exact
    # width for 90 is asserted out-of-band (verified byte-exact under
    # `dfrotz -w 200`); here we pin the loop's INIT (large-constant store) and
    # that it terminates with control continuing -- the old emitter never
    # decremented its counter, so termination depended on stack garbage.
    # (The harness's screen model swallows space-only wrapped lines entirely,
    # so only the terminator is observable here; exact widths are pinned by
    # the in-line variable tests below.)
    AssertRoutine("N", '<SPACES 90> <PRINTN 7>') \
        .when_called_with("0").outputs("7")


def test_spaces_variable_count():
    AssertRoutine("N", '<PRINTI "["> <SPACES .N> <PRINTI "]">') \
        .when_called_with("4").outputs("[    ]")


def test_spaces_zero_variable_prints_nothing():
    AssertRoutine("N", '<PRINTI "["> <SPACES .N> <PRINTI "]">') \
        .when_called_with("0").outputs("[]")
