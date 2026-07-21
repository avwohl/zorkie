r"""Regression tests for ZIL character-literal semantics.

In ZIL a character constant `!\X` is the character X taken LITERALLY -- the
backslash is read syntax, not a C-style escape. So `!\n` is the letter 'n'
(110), `!\0` is '0' (48), `!\t` is 't' (116), `!\r` is 'r' (114).

A prior bug applied C escapes (`{'n': 10, 't': 9, 'r': 13, '0': 0}`) in both
_parse_char_literal (codegen) and _char_literal_code (macro_expander). That
broke the standard-library YES? routine's `<EQUAL? .CHR !\N !\n>` test (an
infinite "type y or n" loop) and -- via the `%<ASCII !\0>` the library's digit
parsers fold at compile time -- the `<- .CHR %<ASCII !\0>>` "digit char minus
'0'" conversion. These guard the fix.

The exercised path is the compile-time `%<ASCII !\X>` fold, which is exactly
what the ZILF standard library uses (parser.zil / forms.zil digit parsing and
the YES?/menu char tests). Every assertion below returned the WRONG value under
the old escape-map bug.
"""
from .conftest import AssertExpr


def test_ascii_of_backslash_letters_is_the_letter_not_an_escape():
    AssertExpr(r"%<ASCII !\n>").gives_number("110")   # 'n', NOT newline (10)
    AssertExpr(r"%<ASCII !\t>").gives_number("116")   # 't', NOT tab (9)
    AssertExpr(r"%<ASCII !\r>").gives_number("114")   # 'r', NOT carriage return (13)
    AssertExpr(r"%<ASCII !\0>").gives_number("48")    # '0', NOT NUL (0)


def test_ascii_of_uppercase_and_symbols_is_literal():
    AssertExpr(r"%<ASCII !\N>").gives_number("78")
    AssertExpr(r"%<ASCII !\Y>").gives_number("89")
    AssertExpr(r"%<ASCII !\A>").gives_number("65")
    AssertExpr(r"%<ASCII !\!>").gives_number("33")


def test_digit_char_minus_zero_gives_digit_value():
    # `<- CHR %<ASCII !\0>>` is exactly how the ZILF library turns a digit
    # character into its numeric value: '9' (57) - '0' (48) = 9. Under the old
    # `!\0 == 0` bug this returned 57, silently corrupting every numeric-input
    # routine (safe combinations, phone numbers, ...).
    AssertExpr(r"<- 57 %<ASCII !\0>>").gives_number("9")
    AssertExpr(r"<- 55 %<ASCII !\0>>").gives_number("7")
