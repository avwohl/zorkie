"""
ZIL Lexer - Tokenizes ZIL source code into tokens.

Handles:
- Angle brackets <> (primary delimiters)
- Atoms and symbols
- Strings
- Numbers
- Comments
- Variable prefixes (. for local, , for global)
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, List


class TokenType(Enum):
    """ZIL token types."""
    # Delimiters
    LANGLE = auto()      # <
    RANGLE = auto()      # >
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]

    # Literals
    ATOM = auto()        # identifier/symbol
    STRING = auto()      # "text"
    NUMBER = auto()      # 123, -456

    # Variable prefixes
    LOCAL_VAR = auto()   # .VAR
    GLOBAL_VAR = auto()  # ,VAR

    # Special
    COMMA = auto()       # ,
    PERIOD = auto()      # .
    QUOTE = auto()       # ' (quote operator)

    # End of file
    EOF = auto()

    # Newline (for tracking line numbers)
    NEWLINE = auto()


@dataclass
class Token:
    """Represents a single token."""
    type: TokenType
    value: any
    line: int
    column: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"


class Lexer:
    """Tokenizes ZIL source code."""

    def __init__(self, source: str, filename: str = "<input>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []

    def error(self, message: str):
        """Raise a lexer error with location information."""
        raise SyntaxError(f"{self.filename}:{self.line}:{self.column}: {message}")

    def peek(self, offset: int = 0) -> Optional[str]:
        """Peek at character at current position + offset."""
        pos = self.pos + offset
        if pos < len(self.source):
            return self.source[pos]
        return None

    def advance(self) -> Optional[str]:
        """Consume and return current character."""
        if self.pos >= len(self.source):
            return None

        ch = self.source[self.pos]
        self.pos += 1

        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1

        return ch

    def skip_whitespace(self):
        """Skip whitespace characters."""
        while self.peek() and self.peek() in ' \t\n\r':
            self.advance()

    def skip_comment(self):
        """Skip ZIL comments: ;\"comment\" or ; comment to end of line"""
        if self.peek() != ';':
            return

        # Check for block comment: ;" ... "
        # Need to skip whitespace between ; and "
        pos = 1
        while self.peek(pos) and self.peek(pos) in ' \t':
            pos += 1

        if self.peek(pos) == '"':
            # Block comment: ; "comment"
            self.advance()  # ;
            # Skip whitespace
            while self.peek() and self.peek() in ' \t':
                self.advance()
            self.advance()  # "

            # Read until closing "
            while self.peek() and self.peek() != '"':
                self.advance()

            if self.peek() == '"':
                self.advance()
            else:
                self.error("Unterminated comment")
        else:
            # Line comment: ; comment to end of line
            while self.peek() and self.peek() != '\n':
                self.advance()

    def read_string(self) -> str:
        """Read a string literal."""
        start_line = self.line
        start_col = self.column

        self.advance()  # opening "
        chars = []

        while self.peek() and self.peek() != '"':
            ch = self.peek()

            # Handle escape sequences
            if ch == '\\':
                self.advance()
                next_ch = self.peek()
                if next_ch == 'n':
                    chars.append('\n')
                    self.advance()
                elif next_ch == 't':
                    chars.append('\t')
                    self.advance()
                elif next_ch == '\\':
                    chars.append('\\')
                    self.advance()
                elif next_ch == '"':
                    chars.append('"')
                    self.advance()
                else:
                    chars.append(next_ch)
                    self.advance()
            else:
                chars.append(ch)
                self.advance()

        if self.peek() != '"':
            self.error(f"Unterminated string starting at {start_line}:{start_col}")

        self.advance()  # closing "
        return ''.join(chars)

    def read_number(self) -> int:
        """Read a number (decimal or hex)."""
        chars = []

        # Handle negative numbers
        if self.peek() == '-':
            chars.append(self.advance())

        # Check for hex prefix
        if self.peek() == '$':
            chars.append(self.advance())
            # Read hex digits
            while self.peek() and self.peek() in '0123456789ABCDEFabcdef':
                chars.append(self.advance())

            num_str = ''.join(chars)
            try:
                return int(num_str[1:], 16) if num_str[0] != '-' else -int(num_str[2:], 16)
            except ValueError:
                self.error(f"Invalid hex number: {num_str}")
        else:
            # Read decimal digits
            while self.peek() and self.peek().isdigit():
                chars.append(self.advance())

            num_str = ''.join(chars)
            try:
                return int(num_str)
            except ValueError:
                self.error(f"Invalid number: {num_str}")

    def read_atom(self) -> str:
        """Read an atom/identifier."""
        chars = []

        # Atoms can contain letters, digits, hyphens, underscores, and some special chars
        # First character must be letter or special
        while self.peek() and self.is_atom_char(self.peek()):
            chars.append(self.advance())

        return ''.join(chars)

    def is_atom_char(self, ch: str) -> bool:
        """Check if character is valid in an atom."""
        return (ch.isalnum() or
                ch in '-_?!+*/=\\')

    def tokenize(self) -> List[Token]:
        """Tokenize the entire source code."""
        while self.pos < len(self.source):
            self.skip_whitespace()

            if self.pos >= len(self.source):
                break

            # Check for comment (both ;" and ; styles)
            if self.peek() == ';':
                self.skip_comment()
                continue

            ch = self.peek()
            line = self.line
            col = self.column

            # Delimiters
            if ch == '<':
                self.advance()
                self.tokens.append(Token(TokenType.LANGLE, '<', line, col))
            elif ch == '>':
                self.advance()
                self.tokens.append(Token(TokenType.RANGLE, '>', line, col))
            elif ch == '(':
                self.advance()
                self.tokens.append(Token(TokenType.LPAREN, '(', line, col))
            elif ch == ')':
                self.advance()
                self.tokens.append(Token(TokenType.RPAREN, ')', line, col))
            elif ch == '[':
                self.advance()
                self.tokens.append(Token(TokenType.LBRACKET, '[', line, col))
            elif ch == ']':
                self.advance()
                self.tokens.append(Token(TokenType.RBRACKET, ']', line, col))

            # String
            elif ch == '"':
                value = self.read_string()
                self.tokens.append(Token(TokenType.STRING, value, line, col))

            # Local variable reference
            elif ch == '.' and self.peek(1) and self.peek(1).isalpha():
                self.advance()  # .
                name = self.read_atom()
                self.tokens.append(Token(TokenType.LOCAL_VAR, name, line, col))

            # Global variable reference
            elif ch == ',' and self.peek(1) and self.peek(1).isalpha():
                self.advance()  # ,
                name = self.read_atom()
                self.tokens.append(Token(TokenType.GLOBAL_VAR, name, line, col))

            # Number
            elif ch.isdigit() or (ch == '-' and self.peek(1) and self.peek(1).isdigit()):
                value = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, value, line, col))

            # Hex number
            elif ch == '$':
                value = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, value, line, col))

            # Atom/Identifier
            elif ch.isalpha() or ch in '-_?!+*/<>=':
                value = self.read_atom()
                self.tokens.append(Token(TokenType.ATOM, value, line, col))

            # Period (when not followed by alpha)
            elif ch == '.':
                self.advance()
                self.tokens.append(Token(TokenType.PERIOD, '.', line, col))

            # Comma (when not followed by alpha)
            elif ch == ',':
                self.advance()
                self.tokens.append(Token(TokenType.COMMA, ',', line, col))

            # Quote operator
            elif ch == "'":
                self.advance()
                self.tokens.append(Token(TokenType.QUOTE, "'", line, col))

            else:
                self.error(f"Unexpected character: {ch!r}")

        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, None, self.line, self.column))
        return self.tokens


def tokenize(source: str, filename: str = "<input>") -> List[Token]:
    """Convenience function to tokenize ZIL source code."""
    lexer = Lexer(source, filename)
    return lexer.tokenize()
