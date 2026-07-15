# Regression tests for quasiquote-template parsing in zorkie.
#
# A quasiquote template `<...> is DATA, not definitions. Special-form dispatch
# (CONSTANT / ROUTINE / OBJECT / ...) must be suppressed inside it; otherwise
# library macros of the form `<CONSTANT ~.NAME <ITABLE ...>> -- pervasive in the
# ZILF standard library (e.g. FINISH-PRONOUNS in parser.zil) -- fail to parse
# with "Expected RANGLE, got LANGLE", because parse_constant reads the ~ as the
# constant's name and then meets the nested <ITABLE ...> where it wants >.
#
# The fix is Parser.quasiquote_depth: while inside a `template`, parse_form skips
# the special dispatch and parses generically (the operand loop handles ~ / ~!);
# unquote escapes one level and restores normal dispatch. At depth 0 nothing
# changes, so ordinary code is unaffected.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zilc.lexer.lexer import Lexer
from zilc.parser.parser import Parser
from zilc.parser.ast_nodes import QuasiquoteNode, FormNode, ConstantNode


def _expr(src):
    return Parser(Lexer(src).tokenize()).parse_expression()


def test_special_form_inside_quasiquote_parses():
    """The exact shape that blocked cloak.zil must parse without raising."""
    src = "<DEFINE FOO (L) `<CONSTANT ~.NAME <ITABLE .SZ .FL>>>"
    Parser(Lexer(src).tokenize()).parse()  # no SyntaxError


def test_quasiquoted_constant_is_a_template_not_a_definition():
    """`<CONSTANT ...> is a QuasiquoteNode wrapping a generic form, never a
    ConstantNode (which would try to define a real constant named '~')."""
    e = _expr("`<CONSTANT ~.NAME <ITABLE .SZ>>")
    assert isinstance(e, QuasiquoteNode)
    assert isinstance(e.expr, FormNode)
    assert not isinstance(e.expr, ConstantNode)


def test_depth0_constant_still_dispatches():
    """Outside a template, <CONSTANT NAME VALUE> is still a ConstantNode
    (the fix must not change depth-0 behavior)."""
    assert isinstance(_expr("<CONSTANT FOO 42>"), ConstantNode)


def test_quasiquoted_routine_and_object_also_templated():
    """Other special forms inside a template are generic forms too."""
    for src in ("`<ROUTINE ~.NAME () <RTRUE>>", "`<OBJECT ~.NAME (DESC \"x\")>"):
        e = _expr(src)
        assert isinstance(e, QuasiquoteNode)
        assert isinstance(e.expr, FormNode)
