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
    SEMICOLON = auto()   # ; (when used as separator, not comment)

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
        self.paren_depth = 0  # Track parenthesis depth for context-aware semicolon handling
        self.angle_depth = 0  # Track angle bracket depth for context-aware semicolon handling

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
        while self.peek() and self.peek() in ' \t\n\r\f':
            self.advance()

    def skip_comment(self):
        """Skip ZIL comments: ;\"comment\", ;< form>, ;(...), or ; line comment"""
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
        elif self.peek(pos) == '<':
            # Form comment: ;< form > - skip entire form including nested brackets
            self.advance()  # ;
            # Skip whitespace
            while self.peek() and self.peek() in ' \t':
                self.advance()
            # Now skip the form
            self.skip_angle_form_comment()
        elif self.peek(pos) == '(':
            # Form comment: ;(...) - skip entire form including nested parens
            self.advance()  # ;
            # Skip whitespace
            while self.peek() and self.peek() in ' \t':
                self.advance()
            # Now skip the form
            self.skip_paren_form_comment()
        else:
            # Inline comment: ; comments out next token/word, stops at delimiters or whitespace
            # Skip the semicolon
            self.advance()
            # Skip whitespace after semicolon
            while self.peek() and self.peek() in ' \t':
                self.advance()
            # Skip until delimiter or whitespace (comments out one token)
            while self.peek() and self.peek() not in ' \t\n><()':
                self.advance()

    def skip_angle_form_comment(self):
        """Skip an angle-bracket form comment: < ... > with nested angle brackets"""
        if self.peek() != '<':
            return

        self.advance()  # <
        depth = 1

        while depth > 0 and self.peek():
            ch = self.peek()
            if ch == '<':
                depth += 1
            elif ch == '>':
                depth -= 1
            self.advance()

        if depth != 0:
            self.error("Unterminated form comment")

    def skip_paren_form_comment(self):
        """Skip a parenthesis form comment: (...) with nested parentheses"""
        if self.peek() != '(':
            return

        self.advance()  # (
        depth = 1

        while depth > 0 and self.peek():
            ch = self.peek()
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            self.advance()

        if depth != 0:
            self.error("Unterminated form comment")

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
                ch in '-_?+*/=$#;.')

    def tokenize(self) -> List[Token]:
        """Tokenize the entire source code."""
        while self.pos < len(self.source):
            self.skip_whitespace()

            if self.pos >= len(self.source):
                break

            # Check for comment (both ;" and ; styles)
            # Special case: ;= is an atom (used in BUZZ words)
            # Special case: ; inside parentheses followed by non-comment char is a separator (ZILF SYNONYM/ADJECTIVE)
            # But ;" ;< ;( are always comments
            if self.peek() == ';':
                next_ch = self.peek(1)
                # Only treat as atom if followed by = (for ;=)
                if next_ch == '=':
                    # Fall through to atom handling below
                    pass
                # Check if this could be a ZILF separator:
                # Inside parentheses (but not angle brackets) AND not followed by comment indicators (" < ()
                # Skip whitespace to check what comes after
                elif self.paren_depth > 0 and self.angle_depth == 0:
                    pos = 1
                    while self.peek(pos) and self.peek(pos) in ' \t':
                        pos += 1
                    peek_after = self.peek(pos)
                    # If followed by comment indicators, treat as comment
                    if peek_after in ('"', '<', '(', None, '\n'):
                        self.skip_comment()
                        continue
                    # Otherwise, it's a ZILF separator
                    else:
                        line = self.line
                        col = self.column
                        self.advance()  # Skip the semicolon
                        self.tokens.append(Token(TokenType.SEMICOLON, ';', line, col))
                        continue
                # Otherwise it's a comment
                else:
                    self.skip_comment()
                    continue

            ch = self.peek()
            line = self.line
            col = self.column

            # Compile-time evaluation: %<...>, %,VAR, %.VAR - skip the %
            if ch == '%':
                next_ch = self.peek(1)
                if next_ch in ('<', ',', '.'):
                    self.advance()  # Skip %
                    # Fall through to handle the next character
                    ch = self.peek()
                    line = self.line
                    col = self.column

            # Delimiters
            if ch == '<':
                self.advance()
                self.angle_depth += 1
                self.tokens.append(Token(TokenType.LANGLE, '<', line, col))
            elif ch == '>':
                self.advance()
                self.angle_depth -= 1
                self.tokens.append(Token(TokenType.RANGLE, '>', line, col))
            elif ch == '(':
                self.advance()
                self.paren_depth += 1
                self.tokens.append(Token(TokenType.LPAREN, '(', line, col))
            elif ch == ')':
                self.advance()
                self.paren_depth -= 1
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

            # Local variable reference (allow whitespace after period)
            elif ch == '.':
                # Look ahead to see if this is a local var or just a period
                pos = 1
                while self.peek(pos) and self.peek(pos) in ' \t':
                    pos += 1
                # If followed by alphanumeric (after optional whitespace), it's a local var
                # Allow digits too, for vars like .1ST?
                # Allow ? for vars like .?RESULT
                next_ch = self.peek(pos)
                if next_ch and (next_ch.isalnum() or next_ch in '-_?'):
                    self.advance()  # .
                    # Skip whitespace
                    while self.peek() and self.peek() in ' \t':
                        self.advance()
                    name = self.read_atom()
                    self.tokens.append(Token(TokenType.LOCAL_VAR, name, line, col))
                else:
                    # Just a period token
                    self.advance()
                    self.tokens.append(Token(TokenType.PERIOD, '.', line, col))

            # Global variable reference (allow whitespace after comma)
            elif ch == ',':
                # Look ahead to see if this is a global var or just a comma
                pos = 1
                while self.peek(pos) and self.peek(pos) in ' \t':
                    pos += 1
                # If followed by alphanumeric (after optional whitespace), it's a global var
                # Allow digits too for consistency
                # Allow ? for vars like ,?RESULT
                next_ch = self.peek(pos)
                if next_ch and (next_ch.isalnum() or next_ch in '-_?'):
                    self.advance()  # ,
                    # Skip whitespace
                    while self.peek() and self.peek() in ' \t':
                        self.advance()
                    name = self.read_atom()
                    self.tokens.append(Token(TokenType.GLOBAL_VAR, name, line, col))
                else:
                    # Just a comma token
                    self.advance()
                    self.tokens.append(Token(TokenType.COMMA, ',', line, col))

            # Number (but not if it's part of an atom like 1ST?)
            elif ch.isdigit():
                # Look ahead to see if this is a pure number or starts an atom
                # Atoms can start with digits: 1ST?, 2ND, etc.
                pos = 1
                while self.peek(pos) and (self.peek(pos).isdigit() or self.peek(pos) in 'ABCDEFabcdef'):
                    pos += 1
                # If followed by atom characters after the digits, it's an atom
                next_ch = self.peek(pos)
                if next_ch and self.is_atom_char(next_ch) and not next_ch.isdigit():
                    # It's an atom like 1ST?
                    value = self.read_atom()
                    self.tokens.append(Token(TokenType.ATOM, value, line, col))
                else:
                    # It's a number
                    value = self.read_number()
                    self.tokens.append(Token(TokenType.NUMBER, value, line, col))
            # Negative number
            elif ch == '-' and self.peek(1) and self.peek(1).isdigit():
                value = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, value, line, col))

            # Hex number ($1A3F) - only if $ is followed by hex digit
            elif ch == '$' and self.peek(1) and self.peek(1) in '0123456789ABCDEFabcdef':
                value = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, value, line, col))

            # Special case: ! escapes for STRING form (!\", !\\, !=, !\`, etc.)
            elif ch == '!':
                chars = [self.advance()]  # Read !
                # Check for escape patterns: !\X where X is any char
                if self.peek() == '\\':
                    # Read backslash
                    chars.append(self.advance())
                    # Read the escaped character (could be anything)
                    if self.peek():
                        chars.append(self.advance())
                elif self.peek() == ',':
                    # !,VAR pattern - just the ! (VAR will be read separately)
                    pass
                elif self.peek():
                    # Any other character after !
                    chars.append(self.advance())
                value = ''.join(chars)
                self.tokens.append(Token(TokenType.ATOM, value, line, col))

            # Backslash (character constant or escape)
            elif ch == '\\':
                chars = [self.advance()]  # Read \
                # If followed by another character, include it as part of the atom
                # This handles \. \, \" \\ etc. as complete atoms
                if self.peek() and self.peek() not in ' \t\n\r\f':
                    chars.append(self.advance())
                value = ''.join(chars)
                self.tokens.append(Token(TokenType.ATOM, value, line, col))

            # Atom/Identifier
            elif ch.isalpha() or ch in '-_?+*/<>=$#;':
                value = self.read_atom()
                self.tokens.append(Token(TokenType.ATOM, value, line, col))

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
