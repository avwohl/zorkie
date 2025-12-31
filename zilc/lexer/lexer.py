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
    CHAR_GLOBAL_VAR = auto()  # %,VAR (print as character in TELL)
    CHAR_LOCAL_VAR = auto()   # %.VAR (print as character in TELL)

    # Special
    COMMA = auto()       # ,
    PERIOD = auto()      # .
    QUOTE = auto()       # ' (quote operator)
    SEMICOLON = auto()   # ; (when used as separator, not comment)
    PERCENT_LANGLE = auto()  # %< (compile-time evaluation)

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

        if self.peek(pos) == '%':
            # MDL conditional compilation: ;%<COND ...> - skip entire form
            # This is used for compile-time vs load-time conditional evaluation
            self.advance()  # ;
            self.advance()  # %
            # Skip whitespace
            while self.peek() and self.peek() in ' \t':
                self.advance()
            # Skip the following form
            if self.peek() == '<':
                self.skip_angle_form_comment()
            elif self.peek() == '(':
                self.skip_paren_form_comment()
            elif self.peek() == '[':
                self.skip_bracket_form_comment()
            # else: single token was already skipped
        elif self.peek(pos) == '"':
            # Block comment: ; "comment"
            self.advance()  # ;
            # Skip whitespace
            while self.peek() and self.peek() in ' \t':
                self.advance()
            self.advance()  # "

            # Read until closing " (handle escapes)
            while self.peek() and self.peek() != '"':
                if self.peek() == '\\' and self.peek(1):
                    self.advance()  # skip backslash
                    self.advance()  # skip escaped char
                else:
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
        elif self.peek(pos) == '[':
            # Bracket comment: ;[...] - skip entire bracketed form including nested brackets
            self.advance()  # ;
            # Skip whitespace
            while self.peek() and self.peek() in ' \t':
                self.advance()
            # Now skip the bracketed form
            self.skip_bracket_form_comment()
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
        """Skip an angle-bracket form comment: < ... > with nested angle brackets.

        Must handle strings properly - don't count <> inside strings.
        """
        if self.peek() != '<':
            return

        self.advance()  # <
        depth = 1

        while depth > 0 and self.peek():
            ch = self.peek()
            if ch == '"':
                # Skip string content - don't count brackets inside strings
                self.advance()  # opening "
                while self.peek() and self.peek() != '"':
                    if self.peek() == '\\' and self.peek(1):
                        self.advance()  # skip escape char
                    self.advance()
                if self.peek() == '"':
                    self.advance()  # closing "
            elif ch == '<':
                depth += 1
                self.advance()
            elif ch == '>':
                depth -= 1
                self.advance()
            else:
                self.advance()

        if depth != 0:
            self.error("Unterminated form comment")

    def skip_paren_form_comment(self):
        """Skip a parenthesis form comment: (...) with nested parentheses.

        Must handle strings properly - don't count () inside strings.
        """
        if self.peek() != '(':
            return

        self.advance()  # (
        depth = 1

        while depth > 0 and self.peek():
            ch = self.peek()
            if ch == '"':
                # Skip string content - don't count parens inside strings
                self.advance()  # opening "
                while self.peek() and self.peek() != '"':
                    if self.peek() == '\\' and self.peek(1):
                        self.advance()  # skip escape char
                    self.advance()
                if self.peek() == '"':
                    self.advance()  # closing "
            elif ch == '(':
                depth += 1
                self.advance()
            elif ch == ')':
                depth -= 1
                self.advance()
            else:
                self.advance()

        if depth != 0:
            self.error("Unterminated form comment")

    def skip_bracket_form_comment(self):
        """Skip a bracket form comment: [ ... ] with nested brackets.

        Must handle strings properly - don't count [] inside strings.
        """
        if self.peek() != '[':
            return

        self.advance()  # [
        depth = 1

        while depth > 0 and self.peek():
            ch = self.peek()
            if ch == '"':
                # Skip string content - don't count brackets inside strings
                self.advance()  # opening "
                while self.peek() and self.peek() != '"':
                    if self.peek() == '\\' and self.peek(1):
                        self.advance()  # skip escape char
                    self.advance()
                if self.peek() == '"':
                    self.advance()  # closing "
            elif ch == '[':
                depth += 1
                self.advance()
            elif ch == ']':
                depth -= 1
                self.advance()
            else:
                self.advance()

        if depth != 0:
            self.error("Unterminated bracket comment")

    def skip_compile_time_form(self):
        """Skip a compile-time evaluation form: %<...> with nested angle brackets.

        These forms are evaluated at compile-time by the original ZIL compiler.
        Since we don't support compile-time evaluation, we skip them entirely.
        Must handle strings and nested forms properly.
        """
        if self.peek() != '<':
            return

        self.advance()  # <
        depth = 1

        while depth > 0 and self.peek():
            ch = self.peek()
            if ch == '"':
                # Skip string content - don't count brackets inside strings
                self.advance()  # opening "
                while self.peek() and self.peek() != '"':
                    if self.peek() == '\\' and self.peek(1):
                        self.advance()  # skip escape char
                    self.advance()
                if self.peek() == '"':
                    self.advance()  # closing "
            elif ch == '<':
                depth += 1
                self.advance()
            elif ch == '>':
                depth -= 1
                self.advance()
            else:
                self.advance()

        if depth != 0:
            self.error("Unterminated compile-time form")

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
        # Also handle backslash escapes within atoms (e.g., A?G\'S for adjective G'S)
        while self.peek():
            if self.is_atom_char(self.peek()):
                chars.append(self.advance())
            elif self.peek() == '\\' and self.peek(1) and self.peek(1) not in ' \t\n\r\f':
                # Backslash escape within atom - include both backslash and escaped char
                chars.append(self.advance())  # backslash
                chars.append(self.advance())  # escaped char
            else:
                break

        return ''.join(chars)

    def is_atom_char(self, ch: str) -> bool:
        """Check if character is valid in an atom.

        Note: % is used in German Zork for umlaut encoding (e.g., SKARAB%AUS)
        Note: : is used in some MDL/ZIL constructs (type annotations)
        Note: & is used in bitwise operations (BAND, BOR)
        Note: ^ is used in some MDL constructs
        Note: ! is used in MDL atoms like ON!-INITIAL, OFF!-INITIAL
        Note: | is used in TELL-TOKENS and as a delimiter in some contexts
        Note: ' is used in vocabulary words like CAT'S (warns MDL0429)
        """
        return (ch.isalnum() or
                ch in "-_?+*/=$#;.%:&^!|'")

    def tokenize(self) -> List[Token]:
        """Tokenize the entire source code."""
        while self.pos < len(self.source):
            self.skip_whitespace()

            if self.pos >= len(self.source):
                break

            # Handle MDL control character sequences: ^/X (e.g., ^/L = form feed)
            # Also handle ^<ctrl-char> where the control char is literal (e.g., ^\x0c for form feed)
            # Also handle ^\X format where \X is a backslash-escaped letter (e.g., ^\L = form feed)
            # These are typically used as page breaks and should be treated as whitespace
            if self.peek() == '^':
                next_ch = self.peek(1)
                if next_ch == '/':
                    # ^/X format
                    self.advance()  # ^
                    self.advance()  # /
                    if self.peek():
                        self.advance()  # The control character letter
                    continue
                elif next_ch == '\\':
                    # ^\X format (backslash-escaped letter, e.g., ^\L for form feed)
                    self.advance()  # ^
                    self.advance()  # \
                    if self.peek():
                        self.advance()  # The control character letter
                    continue
                elif next_ch and ord(next_ch) < 32:
                    # ^<ctrl-char> format (literal control character)
                    self.advance()  # ^
                    self.advance()  # The control character
                    continue

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
                # Inside parentheses (but not angle brackets) AND immediately followed by identifier
                # ZILF separator is ;WORD (no space) - e.g., <SYNONYM FOO ;BAR BAZ>
                # If there's whitespace after ;, it's a comment, not a separator
                elif self.paren_depth > 0 and self.angle_depth == 0:
                    peek_after = self.peek(1)
                    # If immediately followed by alphanumeric (no whitespace), it's a ZILF separator
                    # e.g., ;INSIDE, ;INTO, ;AUF
                    if peek_after and peek_after.isalnum():
                        line = self.line
                        col = self.column
                        self.advance()  # Skip the semicolon
                        self.tokens.append(Token(TokenType.SEMICOLON, ';', line, col))
                        continue
                    # Otherwise (whitespace, quotes, etc.), it's a comment
                    else:
                        self.skip_comment()
                        continue
                # Otherwise it's a comment
                else:
                    self.skip_comment()
                    continue

            ch = self.peek()
            line = self.line
            col = self.column

            # Compile-time evaluation: %,VAR, %.VAR - these become CHAR_GLOBAL_VAR/CHAR_LOCAL_VAR
            # Note: %<...> forms are handled by compiler preprocessing, not lexer
            percent_prefix = False
            if ch == '%':
                next_ch = self.peek(1)
                if next_ch in (',', '.'):
                    percent_prefix = True
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
                    # Use CHAR_LOCAL_VAR if we had % prefix (for %.VAR in TELL)
                    token_type = TokenType.CHAR_LOCAL_VAR if percent_prefix else TokenType.LOCAL_VAR
                    self.tokens.append(Token(token_type, name, line, col))
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
                    # Use CHAR_GLOBAL_VAR if we had % prefix (for %,VAR in TELL)
                    token_type = TokenType.CHAR_GLOBAL_VAR if percent_prefix else TokenType.GLOBAL_VAR
                    self.tokens.append(Token(token_type, name, line, col))
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
                # Exception: ; after a number starts a comment, not an atom (17;comment = 17)
                next_ch = self.peek(pos)
                if next_ch and self.is_atom_char(next_ch) and not next_ch.isdigit() and next_ch != ';':
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

            # Hex number ($1A3F) - only if $ is followed by hex digits and nothing else
            # Check if it's truly a hex number vs an atom like $BUZZ
            elif ch == '$' and self.peek(1) and self.peek(1) in '0123456789ABCDEFabcdef':
                # Look ahead to see if this is a pure hex number or an atom
                pos = 1
                while self.peek(pos) and self.peek(pos) in '0123456789ABCDEFabcdef':
                    pos += 1
                # If followed by other atom characters (like 'Z' in $BUZZ), it's an atom
                if self.peek(pos) and self.is_atom_char(self.peek(pos)) and self.peek(pos) not in '0123456789ABCDEFabcdef':
                    # It's an atom starting with $
                    self.advance()  # $
                    name = '$' + self.read_atom()
                    self.tokens.append(Token(TokenType.ATOM, name, line, col))
                else:
                    # Pure hex number
                    value = self.read_number()
                    self.tokens.append(Token(TokenType.NUMBER, value, line, col))

            # Base-prefixed number (#2 binary, #8 octal, etc.) or MDL type specifier (#SEMI, etc.)
            elif ch == '#':
                self.advance()  # #
                # Check if followed by a digit (base specifier) or an atom (type specifier)
                if self.peek() and self.peek().isdigit():
                    base = 0
                    while self.peek() and self.peek().isdigit():
                        base = base * 10 + int(self.advance())
                    # Skip whitespace between base and number
                    while self.peek() and self.peek() in ' \t':
                        self.advance()
                    # Now read the number digits
                    num_str = ''
                    while self.peek() and (self.peek().isdigit() or self.peek().isalpha()):
                        num_str += self.advance()
                    try:
                        value = int(num_str, base) if num_str else 0
                        self.tokens.append(Token(TokenType.NUMBER, value, line, col))
                    except ValueError:
                        # If it's not a valid number in that base, treat as 0
                        self.tokens.append(Token(TokenType.NUMBER, 0, line, col))
                else:
                    # It's a type specifier like #SEMI - read as an atom with # prefix
                    name = '#'
                    if self.peek() and (self.peek().isalpha() or self.peek() in '-_'):
                        name += self.read_atom()
                    self.tokens.append(Token(TokenType.ATOM, name, line, col))

            # Special case: ! escapes for STRING form (!\", !\\, !=, !\`, etc.)
            # Also handles !< for MDL splice-form operator
            elif ch == '!':
                chars = [self.advance()]  # Read !
                # Check for escape patterns: !\X where X is any char
                if self.peek() == '\\':
                    # Read backslash
                    chars.append(self.advance())
                    # Read the escaped character (could be anything)
                    if self.peek():
                        chars.append(self.advance())
                    value = ''.join(chars)
                    self.tokens.append(Token(TokenType.ATOM, value, line, col))
                elif self.peek() == ',':
                    # !,VAR pattern - just the ! (VAR will be read separately)
                    self.tokens.append(Token(TokenType.ATOM, '!', line, col))
                elif self.peek() == '<':
                    # !< is MDL splice-form operator - emit ! and let < be read as LANGLE
                    # This allows !<MAPF ...> to be parsed as splice of a form
                    self.tokens.append(Token(TokenType.ATOM, '!', line, col))
                elif self.peek() == '.':
                    # !.VAR pattern - splice local variable - emit just !
                    self.tokens.append(Token(TokenType.ATOM, '!', line, col))
                elif self.peek():
                    # Any other character after !
                    chars.append(self.advance())
                    value = ''.join(chars)
                    self.tokens.append(Token(TokenType.ATOM, value, line, col))
                else:
                    self.tokens.append(Token(TokenType.ATOM, '!', line, col))

            # Backslash (character constant or escape prefix for identifiers)
            elif ch == '\\':
                chars = [self.advance()]  # Read \
                # If followed by another character, include it as part of the atom
                # This handles \. \, \" \\ etc. as complete atoms
                if self.peek() and self.peek() not in ' \t\n\r\f':
                    chars.append(self.advance())
                # Continue reading if more atom characters follow (e.g., \,TELL -> single atom)
                while self.peek() and self.is_atom_char(self.peek()):
                    chars.append(self.advance())
                value = ''.join(chars)
                self.tokens.append(Token(TokenType.ATOM, value, line, col))

            # Octal number: *digits* (e.g., *3777* = 2047 decimal)
            # Must be checked before general atom handling since * is a valid atom char
            elif ch == '*' and self.peek(1) and self.peek(1).isdigit():
                self.advance()  # Skip opening *
                num_str = ''
                while self.peek() and self.peek().isdigit():
                    num_str += self.advance()
                if self.peek() == '*':
                    self.advance()  # Skip closing *
                    try:
                        value = int(num_str, 8)  # Parse as octal
                        self.tokens.append(Token(TokenType.NUMBER, value, line, col))
                    except ValueError:
                        self.error(f"Invalid octal number: *{num_str}*")
                else:
                    # Not a valid *digits* pattern, treat as atom
                    value = '*' + num_str
                    while self.peek() and self.is_atom_char(self.peek()):
                        value += self.advance()
                    self.tokens.append(Token(TokenType.ATOM, value, line, col))

            # Atom/Identifier
            # Note: : can start atoms for type annotations (e.g., :FIX, :DECL)
            # Note: | is used in TELL-TOKENS and other MDL constructs
            elif ch.isalpha() or ch in '-_?+*/<>=$#;:|':
                value = self.read_atom()
                self.tokens.append(Token(TokenType.ATOM, value, line, col))

            # Quote operator
            elif ch == "'":
                self.advance()
                self.tokens.append(Token(TokenType.QUOTE, "'", line, col))

            # Quasi-quote operator (backtick) - used in ZILF macros
            elif ch == '`':
                self.advance()
                self.tokens.append(Token(TokenType.ATOM, '`', line, col))

            # Unquote operator (tilde) - used in ZILF macros with quasi-quote
            elif ch == '~':
                self.advance()
                # Check for ~! which is splice-unquote
                if self.peek() == '!':
                    self.advance()
                    self.tokens.append(Token(TokenType.ATOM, '~!', line, col))
                else:
                    self.tokens.append(Token(TokenType.ATOM, '~', line, col))

            # @ prefix - used for reader macros via MAKE-PREFIX-MACRO
            # Emit @ as a separate token so the parser/macro expander can handle it
            elif ch == '@':
                self.advance()
                self.tokens.append(Token(TokenType.ATOM, '@', line, col))

            # Compile-time conditional: %< ... > (reader macro)
            # This is used for DEBUG-CODE and similar conditionals
            # At top level (angle_depth=0), these conditionally include/exclude code, so skip entirely
            # Inside a form (angle_depth>0), these evaluate to a value, emit placeholder 0
            elif ch == '%' and self.peek(1) == '<':
                line = self.line
                col = self.column
                inside_form = self.angle_depth > 0 or self.paren_depth > 0
                self.advance()  # Skip %
                self.advance()  # Skip <
                # Skip the entire form including nested angle brackets
                # Must handle: strings with escapes, !\X character literals, nested () and <>
                depth = 1
                while depth > 0 and self.pos < len(self.source):
                    c = self.advance()
                    if c == '<':
                        depth += 1
                    elif c == '>':
                        depth -= 1
                    elif c == '!':
                        # Character literal: !\X or !<char> - skip the next character
                        # This handles !\> (literal >) which shouldn't close brackets
                        if self.peek() == '\\' and self.pos + 1 < len(self.source):
                            self.advance()  # skip \
                            self.advance()  # skip the escaped char
                        elif self.peek():
                            self.advance()  # skip any char after !
                    elif c == '"':
                        # Skip string contents
                        while self.pos < len(self.source):
                            sc = self.advance()
                            if sc == '"':
                                break
                            elif sc == '\\' and self.pos < len(self.source):
                                self.advance()
                # If inside a form, emit a placeholder value of 0
                # This allows constructs like <CONSTANT NAME %<COND ...>> to parse correctly
                # At top level, skip entirely (the conditional block is excluded)
                if inside_form:
                    self.tokens.append(Token(TokenType.NUMBER, 0, line, col))

            else:
                self.error(f"Unexpected character: {ch!r}")

        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, None, self.line, self.column))
        return self.tokens


def tokenize(source: str, filename: str = "<input>") -> List[Token]:
    """Convenience function to tokenize ZIL source code."""
    lexer = Lexer(source, filename)
    return lexer.tokenize()
