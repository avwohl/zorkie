"""
ZIL Parser - Builds Abstract Syntax Tree from tokens.

Parses ZIL forms and creates appropriate AST nodes.
"""

from typing import List, Optional, Any
from ..lexer import Token, TokenType
from .ast_nodes import *


class Parser:
    """Parses ZIL tokens into an Abstract Syntax Tree."""

    def __init__(self, tokens: List[Token], filename: str = "<input>"):
        self.tokens = tokens
        self.filename = filename
        self.pos = 0
        self.current_token = self.tokens[0] if tokens else None

    def error(self, message: str):
        """Raise a parser error with location information."""
        if self.current_token:
            raise SyntaxError(
                f"{self.filename}:{self.current_token.line}:{self.current_token.column}: {message}"
            )
        else:
            raise SyntaxError(f"{self.filename}: {message}")

    def peek(self, offset: int = 0) -> Optional[Token]:
        """Peek at token at current position + offset."""
        pos = self.pos + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return None

    def advance(self) -> Token:
        """Consume and return current token."""
        token = self.current_token
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
            self.current_token = self.tokens[self.pos]
        return token

    def expect(self, token_type: TokenType) -> Token:
        """Consume token of expected type or raise error."""
        if self.current_token.type != token_type:
            self.error(f"Expected {token_type.name}, got {self.current_token.type.name}")
        return self.advance()

    def parse(self) -> Program:
        """Parse the entire program."""
        program = Program()

        while self.current_token.type != TokenType.EOF:
            node = self.parse_top_level()

            if isinstance(node, RoutineNode):
                program.routines.append(node)
            elif isinstance(node, ObjectNode):
                program.objects.append(node)
            elif isinstance(node, RoomNode):
                program.rooms.append(node)
            elif isinstance(node, GlobalNode):
                program.globals.append(node)
            elif isinstance(node, ConstantNode):
                program.constants.append(node)
            elif isinstance(node, PropdefNode):
                program.propdefs.append(node)
            elif isinstance(node, SyntaxNode):
                program.syntax.append(node)
            elif isinstance(node, VersionNode):
                program.version = node.version
            elif isinstance(node, TableNode):
                program.tables.append(node)

        return program

    def parse_top_level(self) -> ASTNode:
        """Parse a top-level form."""
        if self.current_token.type == TokenType.LANGLE:
            return self.parse_form()
        else:
            self.error(f"Unexpected token at top level: {self.current_token.type.name}")

    def parse_form(self) -> ASTNode:
        """Parse a form: <operator operand1 operand2 ...>"""
        line = self.current_token.line
        col = self.current_token.column

        self.expect(TokenType.LANGLE)

        if self.current_token.type == TokenType.RANGLE:
            # Empty form <>
            self.advance()
            return FormNode(AtomNode("<>", line, col), [], line, col)

        # Parse operator
        operator = self.parse_expression()

        # Check for special forms
        if isinstance(operator, AtomNode):
            op_name = operator.value.upper()

            if op_name == "ROUTINE":
                node = self.parse_routine(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "OBJECT":
                node = self.parse_object(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "ROOM":
                node = self.parse_room(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "SYNTAX":
                node = self.parse_syntax(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "VERSION":
                version_num = self.parse_expression()
                if not isinstance(version_num, NumberNode):
                    self.error("VERSION requires a number")
                self.expect(TokenType.RANGLE)
                return VersionNode(version_num.value, line, col)

            elif op_name == "GLOBAL":
                node = self.parse_global(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "CONSTANT":
                node = self.parse_constant(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "PROPDEF":
                node = self.parse_propdef(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name in ("TABLE", "ITABLE", "LTABLE"):
                node = self.parse_table(op_name, line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "COND":
                node = self.parse_cond(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "REPEAT":
                node = self.parse_repeat(line, col)
                self.expect(TokenType.RANGLE)
                return node

        # Parse operands for generic form
        operands = []
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            operands.append(self.parse_expression())

        self.expect(TokenType.RANGLE)
        return FormNode(operator, operands, line, col)

    def parse_expression(self) -> ASTNode:
        """Parse a single expression (atom, number, string, form, etc.)."""
        token = self.current_token
        line = token.line
        col = token.column

        if token.type == TokenType.LANGLE:
            return self.parse_form()

        elif token.type == TokenType.ATOM:
            self.advance()
            return AtomNode(token.value, line, col)

        elif token.type == TokenType.NUMBER:
            self.advance()
            return NumberNode(token.value, line, col)

        elif token.type == TokenType.STRING:
            self.advance()
            return StringNode(token.value, line, col)

        elif token.type == TokenType.LOCAL_VAR:
            self.advance()
            return LocalVarNode(token.value, line, col)

        elif token.type == TokenType.GLOBAL_VAR:
            self.advance()
            return GlobalVarNode(token.value, line, col)

        elif token.type == TokenType.LPAREN:
            # Parse list literal (parameters, etc.)
            return self.parse_list()

        else:
            self.error(f"Unexpected token in expression: {token.type.name}")

    def parse_list(self) -> List[Any]:
        """Parse a parenthesized list."""
        self.expect(TokenType.LPAREN)
        items = []

        while self.current_token.type != TokenType.RPAREN:
            if self.current_token.type == TokenType.EOF:
                self.error("Unclosed list")

            items.append(self.parse_expression())

        self.expect(TokenType.RPAREN)
        return items

    def parse_routine(self, line: int, col: int) -> RoutineNode:
        """Parse ROUTINE definition."""
        # <ROUTINE name (params "AUX" aux-vars) body...>

        # Get routine name
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected routine name")
        name = self.current_token.value
        self.advance()

        # Parse parameter list
        params = []
        aux_vars = []

        if self.current_token.type == TokenType.LPAREN:
            self.advance()
            in_aux = False

            while self.current_token.type != TokenType.RPAREN:
                if self.current_token.type == TokenType.STRING:
                    if self.current_token.value == "AUX":
                        in_aux = True
                        self.advance()
                        continue

                if self.current_token.type == TokenType.ATOM:
                    if in_aux:
                        aux_vars.append(self.current_token.value)
                    else:
                        params.append(self.current_token.value)
                    self.advance()
                else:
                    self.error("Expected parameter name")

            self.expect(TokenType.RPAREN)

        # Parse routine body
        body = []
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            body.append(self.parse_expression())

        return RoutineNode(name, params, aux_vars, body, line, col)

    def parse_object(self, line: int, col: int) -> ObjectNode:
        """Parse OBJECT definition."""
        # <OBJECT name (property value) (property value) ...>

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected object name")
        name = self.current_token.value
        self.advance()

        properties = self.parse_properties()

        return ObjectNode(name, properties, line, col)

    def parse_room(self, line: int, col: int) -> RoomNode:
        """Parse ROOM definition."""
        # <ROOM name (property value) (property value) ...>

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected room name")
        name = self.current_token.value
        self.advance()

        properties = self.parse_properties()

        return RoomNode(name, properties, line, col)

    def parse_properties(self) -> dict:
        """Parse object/room properties."""
        properties = {}

        while self.current_token.type == TokenType.LPAREN:
            self.advance()  # (

            # Get property name
            if self.current_token.type != TokenType.ATOM:
                self.error("Expected property name")
            prop_name = self.current_token.value
            self.advance()

            # Get property value(s)
            values = []
            while self.current_token.type != TokenType.RPAREN:
                if self.current_token.type == TokenType.EOF:
                    self.error("Unclosed property")
                values.append(self.parse_expression())

            self.expect(TokenType.RPAREN)

            # Store property
            if len(values) == 1:
                properties[prop_name] = values[0]
            else:
                properties[prop_name] = values

        return properties

    def parse_syntax(self, line: int, col: int) -> SyntaxNode:
        """Parse SYNTAX definition."""
        # <SYNTAX verb object-type ... = V-ROUTINE>

        pattern = []

        # Parse pattern until =
        while self.current_token.type != TokenType.ATOM or self.current_token.value != "=":
            if self.current_token.type == TokenType.EOF:
                self.error("Expected = in SYNTAX")

            if self.current_token.type == TokenType.ATOM:
                pattern.append(self.current_token.value)
                self.advance()
            else:
                self.error("Expected atom in SYNTAX pattern")

        # Skip =
        self.advance()

        # Get routine name
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected routine name after =")
        routine = self.current_token.value
        self.advance()

        return SyntaxNode(pattern, routine, line, col)

    def parse_global(self, line: int, col: int) -> GlobalNode:
        """Parse GLOBAL definition."""
        # <GLOBAL name initial-value>

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected global variable name")
        name = self.current_token.value
        self.advance()

        initial_value = None
        if self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            initial_value = self.parse_expression()

        return GlobalNode(name, initial_value, line, col)

    def parse_constant(self, line: int, col: int) -> ConstantNode:
        """Parse CONSTANT definition."""
        # <CONSTANT name value>

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected constant name")
        name = self.current_token.value
        self.advance()

        value = self.parse_expression()

        return ConstantNode(name, value, line, col)

    def parse_propdef(self, line: int, col: int):
        """Parse PROPDEF property definition."""
        # <PROPDEF name default-value>
        from .ast_nodes import PropdefNode

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected property name")
        name = self.current_token.value
        self.advance()

        # Default value (usually a number)
        default_value = None
        if self.current_token.type != TokenType.RANGLE:
            default_value = self.parse_expression()

        return PropdefNode(name, default_value, line, col)

    def parse_table(self, table_type: str, line: int, col: int) -> TableNode:
        """Parse TABLE/ITABLE/LTABLE definition."""
        flags = []
        size = None
        values = []

        # Check for size (ITABLE/LTABLE)
        if table_type in ("ITABLE", "LTABLE"):
            if self.current_token.type == TokenType.NUMBER:
                size = self.current_token.value
                self.advance()

        # Check for flags (BYTE), (PURE), etc.
        if self.current_token.type == TokenType.LPAREN:
            self.advance()
            while self.current_token.type != TokenType.RPAREN:
                if self.current_token.type == TokenType.ATOM:
                    flags.append(self.current_token.value)
                    self.advance()
                else:
                    self.error("Expected flag name")
            self.expect(TokenType.RPAREN)

        # Parse table values
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            values.append(self.parse_expression())

        return TableNode(table_type, flags, size, values, line, col)

    def parse_cond(self, line: int, col: int) -> CondNode:
        """Parse COND statement."""
        # <COND (condition action1 action2 ...) (condition action ...) ...>

        clauses = []

        while self.current_token.type == TokenType.LPAREN:
            self.advance()  # (

            # Parse condition
            condition = self.parse_expression()

            # Parse actions
            actions = []
            while self.current_token.type != TokenType.RPAREN:
                if self.current_token.type == TokenType.EOF:
                    self.error("Unclosed COND clause")
                actions.append(self.parse_expression())

            self.expect(TokenType.RPAREN)
            clauses.append((condition, actions))

        return CondNode(clauses, line, col)

    def parse_repeat(self, line: int, col: int) -> 'RepeatNode':
        """Parse REPEAT statement.

        Syntax:
        <REPEAT () body...>
        <REPEAT ((var init)...) body...>
        <REPEAT ((var init)...) (condition) body...>

        Common ZIL loop patterns:
        - Infinite loop: <REPEAT () ...>
        - Loop with exit via RETURN
        - Loop with bindings for loop variables
        """
        from .ast_nodes import RepeatNode

        # Parse bindings list (required, can be empty)
        bindings = []
        if self.current_token.type == TokenType.LPAREN:
            self.advance()  # (

            # Parse variable bindings
            while self.current_token.type == TokenType.LPAREN:
                self.advance()  # (

                # Expect variable name
                if self.current_token.type != TokenType.ATOM:
                    self.error(f"Expected variable name in REPEAT binding, got {self.current_token.type}")

                var_name = self.current_token.value
                self.advance()

                # Parse initial value
                init_value = self.parse_expression()

                self.expect(TokenType.RPAREN)
                bindings.append((var_name, init_value))

            self.expect(TokenType.RPAREN)

        # Check if there's an optional condition clause
        condition = None
        if self.current_token.type == TokenType.LPAREN:
            # Peek ahead to see if this looks like a condition
            # For now, assume first ( after bindings could be condition
            # This is a simplification - full ZIL is more complex
            saved_pos = self.pos
            saved_token = self.current_token

            self.advance()  # (
            potential_condition = self.parse_expression()
            self.expect(TokenType.RPAREN)

            # If there are more expressions, treat as condition
            # Otherwise, this was the first body expression
            if self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
                condition = potential_condition
            else:
                # Restore - this was actually the body
                self.pos = saved_pos
                self.current_token = saved_token

        # Parse body
        body = []
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            body.append(self.parse_expression())

        return RepeatNode(bindings, condition, body, line, col)


def parse(tokens: List[Token], filename: str = "<input>") -> Program:
    """Convenience function to parse tokens into AST."""
    parser = Parser(tokens, filename)
    return parser.parse()
