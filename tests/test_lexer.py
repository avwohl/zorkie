"""Tests for the ZIL lexer."""

import sys
sys.path.insert(0, '..')

from zilc.lexer import Lexer, TokenType


def test_basic_form():
    """Test lexing a basic form."""
    source = "<ROUTINE GO () <QUIT>>"
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    assert tokens[0].type == TokenType.LANGLE
    assert tokens[1].type == TokenType.ATOM
    assert tokens[1].value == "ROUTINE"
    assert tokens[2].type == TokenType.ATOM
    assert tokens[2].value == "GO"
    print("✓ Basic form test passed")


def test_strings():
    """Test string literals."""
    source = '<TELL "Hello, World!">'
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    string_token = [t for t in tokens if t.type == TokenType.STRING][0]
    assert string_token.value == "Hello, World!"
    print("✓ String test passed")


def test_numbers():
    """Test number literals."""
    source = "<+ 1 2 3>"
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    numbers = [t.value for t in tokens if t.type == TokenType.NUMBER]
    assert numbers == [1, 2, 3]
    print("✓ Number test passed")


def test_variables():
    """Test variable references."""
    source = "<SETG GVAR 5>"
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    atoms = [t for t in tokens if t.type == TokenType.ATOM]
    assert "SETG" in [a.value for a in atoms]
    assert "GVAR" in [a.value for a in atoms]
    print("✓ Variable test passed")


def test_comments():
    """Test comment handling."""
    source = ';\"This is a comment\"\n<QUIT>'
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    atoms = [t for t in tokens if t.type == TokenType.ATOM]
    assert len(atoms) >= 1
    assert "QUIT" in [a.value for a in atoms]
    print("✓ Comment test passed")


if __name__ == '__main__':
    test_basic_form()
    test_strings()
    test_numbers()
    test_variables()
    test_comments()
    print("\nAll lexer tests passed!")
