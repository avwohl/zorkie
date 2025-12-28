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
            self.error(f"Expected {token_type.name}, got {self.current_token.type.name} ({repr(self.current_token.value)})")
        return self.advance()

    def parse(self) -> Program:
        """Parse the entire program."""
        program = Program()
        self._extra_forms = []  # For forms extracted from parenthesized groups

        while self.current_token.type != TokenType.EOF:
            node = self.parse_top_level()

            # Skip None nodes (comments, standalone strings, etc.)
            if node is None:
                continue

            # Handle lists of nodes (from VERSION? expansion)
            if isinstance(node, list):
                for n in node:
                    self._add_node_to_program(program, n)
            else:
                self._add_node_to_program(program, node)

            # Process any extra forms from parenthesized groups
            while self._extra_forms:
                extra = self._extra_forms.pop(0)
                if extra:
                    self._add_node_to_program(program, extra)

        return program

    def _add_node_to_program(self, program, node):
        """Helper to add a single node to the program."""
        if node is None:
            return

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
        elif isinstance(node, MacroNode):
            program.macros.append(node)
        elif isinstance(node, VersionNode):
            program.version = node.version
        elif isinstance(node, TableNode):
            program.tables.append(node)
        elif isinstance(node, BuzzNode):
            # Add all buzz words to program's buzz_words list
            program.buzz_words.extend(node.words)
        elif isinstance(node, SynonymNode):
            # Add all synonym words to program's synonym_words list
            program.synonym_words.extend(node.words)
        elif isinstance(node, DirectionsNode):
            # Add all direction names to program's directions list
            program.directions.extend(node.names)
        elif isinstance(node, BitSynonymNode):
            # Add bit synonym to program's bit_synonyms list
            program.bit_synonyms.append(node)
        elif isinstance(node, RemoveSynonymNode):
            # Add to removed synonyms list
            program.removed_synonyms.append(node.word)

    def parse_top_level(self) -> ASTNode:
        """Parse a top-level form."""
        if self.current_token.type == TokenType.LANGLE:
            return self.parse_form()
        elif self.current_token.type == TokenType.STRING:
            # Skip standalone strings (comments/documentation)
            self.advance()
            return None
        elif self.current_token.type == TokenType.ATOM and self.current_token.value in ('\\', '\\\\'):
            # Skip standalone backslash (page break marker)
            self.advance()
            return None
        elif self.current_token.type == TokenType.ATOM:
            # MDL compilation switches and other bare atoms at top level
            # Examples: ON!-INITIAL, OFF!-INITIAL
            # These are compile-time directives that we can ignore
            self.advance()
            return None
        elif self.current_token.type == TokenType.RANGLE:
            # Skip stray closing brackets (may result from complex macro expansions)
            self.advance()
            return None
        elif self.current_token.type == TokenType.RPAREN:
            # Skip stray closing parens (may result from complex macro/preprocessing)
            self.advance()
            return None
        elif self.current_token.type == TokenType.LPAREN:
            # Parenthesized forms at top level (result from %<COND> splicing)
            # These are like: (<GLOBAL NAME VALUE> <GLOBAL NAME2 VALUE2>)
            # Parse the contents as if they were top-level forms
            self.advance()  # skip (
            results = []
            while self.current_token.type != TokenType.RPAREN and self.current_token.type != TokenType.EOF:
                if self.current_token.type == TokenType.LANGLE:
                    form = self.parse_form()
                    if form:
                        results.append(form)
                else:
                    # Skip unexpected tokens inside parens
                    self.advance()
            if self.current_token.type == TokenType.RPAREN:
                self.advance()  # skip )
            # Return forms to be added to program - but parse_top_level expects single result
            # Store extra forms for later processing
            if results:
                if len(results) == 1:
                    return results[0]
                else:
                    # Multiple forms - store extras for processing
                    self._extra_forms = getattr(self, '_extra_forms', [])
                    self._extra_forms.extend(results[1:])
                    return results[0]
            return None
        elif self.current_token.type == TokenType.LBRACKET:
            # Skip bracket forms at top level - these are visual separators or MDL comments
            # In ZILCH source, [ on its own line is a page/section break
            self.advance()
            # If followed by content and closing bracket, skip the whole thing
            depth = 1
            while depth > 0 and self.current_token.type != TokenType.EOF:
                if self.current_token.type == TokenType.LBRACKET:
                    depth += 1
                elif self.current_token.type == TokenType.RBRACKET:
                    depth -= 1
                self.advance()
            return None
        elif self.current_token.type == TokenType.RBRACKET:
            # Skip stray closing bracket
            self.advance()
            return None
        elif self.current_token.type == TokenType.QUOTE:
            # Quoted form at top level: '< ... > or '(...)
            # This is MDL data that we can skip
            self.advance()  # skip '
            if self.current_token.type == TokenType.LANGLE:
                # Skip the quoted angle form
                depth = 1
                self.advance()  # skip <
                while depth > 0 and self.current_token.type != TokenType.EOF:
                    if self.current_token.type == TokenType.LANGLE:
                        depth += 1
                    elif self.current_token.type == TokenType.RANGLE:
                        depth -= 1
                    self.advance()
            elif self.current_token.type == TokenType.LPAREN:
                # Skip the quoted paren form
                depth = 1
                self.advance()  # skip (
                while depth > 0 and self.current_token.type != TokenType.EOF:
                    if self.current_token.type == TokenType.LPAREN:
                        depth += 1
                    elif self.current_token.type == TokenType.RPAREN:
                        depth -= 1
                    self.advance()
            return None
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
                # Handle VERSION ZIP (Z-code Interpreter Program) = version 3
                if isinstance(version_num, AtomNode):
                    if version_num.value.upper() == "ZIP":
                        version_value = 3
                    elif version_num.value.upper() == "EZIP":
                        version_value = 4
                    elif version_num.value.upper() == "XZIP":
                        version_value = 5
                    elif version_num.value.upper() == "YZIP":
                        version_value = 6
                    else:
                        self.error(f"Unknown version name: {version_num.value}")
                elif isinstance(version_num, NumberNode):
                    version_value = version_num.value
                else:
                    self.error("VERSION requires a number or version name (ZIP/EZIP/XZIP/YZIP)")
                # Skip any additional arguments (e.g., TIME in <VERSION ZIP TIME>)
                while self.current_token.type != TokenType.RANGLE:
                    self.advance()
                self.expect(TokenType.RANGLE)
                return VersionNode(version_value, line, col)

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

            elif op_name == "DEFMAC":
                node = self.parse_defmac(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "DEFINE":
                # DEFINE is like DEFMAC but for compile-time only
                # Parse it the same way but mark as compile-time
                node = self.parse_defmac(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "EVAL":
                # EVAL is compile-time evaluation - parse but don't generate code
                expr = self.parse_expression()
                self.expect(TokenType.RANGLE)
                # Return None to skip this at top level
                return None

            elif op_name == "DEFAULT-DEFINITION":
                # DEFAULT-DEFINITION contains default macro definitions
                # Parse name and body expressions but don't generate code
                if self.current_token.type == TokenType.ATOM:
                    self.advance()  # Skip name
                # Parse all expressions until closing >
                while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
                    self.parse_expression()
                self.expect(TokenType.RANGLE)
                return None

            elif op_name == "VERSION?":
                # VERSION? conditional compilation
                # Syntax: <VERSION? (ZIP body...) (EZIP body...) (ELSE body...)>
                # Parse each clause and only return the matching one for our version
                from .ast_nodes import Program


                # Get version from parent or default to 3
                version = 3  # Default
                # Try to get from program globals if available

                selected_bodies = []
                found_match = False

                while self.current_token.type == TokenType.LPAREN:
                    self.advance()  # Skip (

                    # Parse condition name (ZIP, EZIP, XZIP, ELSE, etc.)
                    clause_type = None
                    if self.current_token.type == TokenType.ATOM:
                        clause_type = self.current_token.value.upper()
                        self.advance()

                    # Parse body expressions for this clause
                    clause_bodies = []
                    while self.current_token.type not in (TokenType.RPAREN, TokenType.EOF):
                        clause_bodies.append(self.parse_expression())

                    self.expect(TokenType.RPAREN)

                    # Check if this clause matches our version
                    if not found_match:
                        if clause_type == "ZIP" and version == 3:
                            selected_bodies = clause_bodies
                            found_match = True
                        elif clause_type == "EZIP" and version == 4:
                            selected_bodies = clause_bodies
                            found_match = True
                        elif clause_type == "XZIP" and version == 5:
                            selected_bodies = clause_bodies
                            found_match = True
                        elif clause_type == "ELSE" and not found_match:
                            selected_bodies = clause_bodies
                            found_match = True

                self.expect(TokenType.RANGLE)


                # Return the selected bodies as a list of nodes
                # These will be added to the program as if they were top-level
                return selected_bodies if selected_bodies else None

            elif op_name == "NEWTYPE":
                # NEWTYPE type-name base-type type-spec
                # Example: <NEWTYPE RSEC VECTOR '!<VECTOR ATOM ...>>
                # This is a compile-time type definition - we store it but don't generate code
                node = self.parse_newtype(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "OFFSET":
                # OFFSET index type-name field-type
                # Example: <OFFSET 1 RSEC ATOM>
                # Returns the index as a compile-time constant
                node = self.parse_offset(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name in ("PACKAGE", "ENDPACKAGE"):
                # MDL module system - skip these directives
                # Parse any arguments and discard
                while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
                    self.parse_expression()
                self.expect(TokenType.RANGLE)
                return None

            elif op_name == "ENTRY":
                # ENTRY symbol1 symbol2 ... - module exports
                # Parse and discard
                while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
                    self.parse_expression()
                self.expect(TokenType.RANGLE)
                return None

            elif op_name == "USE":
                # USE "module-name" - module import
                # Parse and discard
                while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
                    self.parse_expression()
                self.expect(TokenType.RANGLE)
                return None

            elif op_name == "BUZZ":
                node = self.parse_buzz(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "DIRECTIONS":
                # <DIRECTIONS NORTH SOUTH EAST WEST>
                # Parse all direction names
                names = []
                while self.current_token.type == TokenType.ATOM:
                    names.append(self.current_token.value.upper())
                    self.advance()
                self.expect(TokenType.RANGLE)
                return DirectionsNode(names, line, col)

            elif op_name == "SYNONYM":
                # Standalone SYNONYM declaration (not in an object)
                node = self.parse_synonym_declaration(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "BIT-SYNONYM":
                # BIT-SYNONYM flag alias declaration
                node = self.parse_bit_synonym(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "REMOVE-SYNONYM":
                # REMOVE-SYNONYM word declaration
                node = self.parse_remove_synonym(line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name in ("TABLE", "ITABLE", "LTABLE"):
                node = self.parse_table(op_name, line, col)
                self.expect(TokenType.RANGLE)
                return node

            elif op_name == "COND":
                # Only use special COND parsing if followed by LPAREN
                # (allows quasiquote templates like `<COND ~!.CLAUSES>)
                if self.current_token.type == TokenType.LPAREN:
                    node = self.parse_cond(line, col)
                    self.expect(TokenType.RANGLE)
                    return node
                # Fall through to generic form handling

            elif op_name == "REPEAT":
                # Only use special REPEAT parsing if followed by LPAREN
                # (allows quasiquote templates like `<REPEAT ~!.STUFF>)
                if self.current_token.type == TokenType.LPAREN:
                    node = self.parse_repeat(line, col)
                    self.expect(TokenType.RANGLE)
                    return node
                # Fall through to generic form handling

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

        # Handle quote operator: 'EXPR becomes <QUOTE EXPR>
        if token.type == TokenType.QUOTE:
            self.advance()
            quoted_expr = self.parse_expression()
            # Create a QUOTE form
            quote_atom = AtomNode("QUOTE", line, col)
            return FormNode(quote_atom, [quoted_expr], line, col)

        # Handle quasiquote operator: `EXPR becomes QuasiquoteNode
        if token.type == TokenType.ATOM and token.value == '`':
            self.advance()
            quoted_expr = self.parse_expression()
            return QuasiquoteNode(quoted_expr, line, col)

        # Handle unquote operator: ~EXPR becomes UnquoteNode
        if token.type == TokenType.ATOM and token.value == '~':
            self.advance()
            unquoted_expr = self.parse_expression()
            return UnquoteNode(unquoted_expr, line, col)

        # Handle splice-unquote operator: ~!EXPR becomes SpliceUnquoteNode
        if token.type == TokenType.ATOM and token.value == '~!':
            self.advance()
            spliced_expr = self.parse_expression()
            return SpliceUnquoteNode(spliced_expr, line, col)

        # Handle MDL splice operator: !EXPR becomes SpliceUnquoteNode
        # This is the MDL syntax for splicing (equivalent to ~! in ZILF)
        # Used in macro bodies like <FORM PROG () !<MAPF ...>>
        if token.type == TokenType.ATOM and token.value == '!':
            self.advance()
            spliced_expr = self.parse_expression()
            return SpliceUnquoteNode(spliced_expr, line, col)

        # Handle bare comma: ,EXPR becomes <GVAL EXPR> (computed global reference)
        # This is for cases like ,~<PARSE ...> where the global name is computed
        if token.type == TokenType.COMMA:
            self.advance()
            # Parse the expression that follows
            computed_expr = self.parse_expression()
            # Wrap in a GVAL form (get global value)
            gval_atom = AtomNode("GVAL", line, col)
            return FormNode(gval_atom, [computed_expr], line, col)

        # Handle bare period: .EXPR becomes <LVAL EXPR> (computed local reference)
        # This is for cases like .~.VAR where the local name is computed
        if token.type == TokenType.PERIOD:
            self.advance()
            # Parse the expression that follows
            computed_expr = self.parse_expression()
            # Wrap in a LVAL form (get local value)
            lval_atom = AtomNode("LVAL", line, col)
            return FormNode(lval_atom, [computed_expr], line, col)

        if token.type == TokenType.LANGLE:
            # Check for empty form <>
            # peek(1) looks at the NEXT token after current
            next_tok = self.peek(1)
            if next_tok and next_tok.type == TokenType.RANGLE:
                self.advance()  # Skip <
                self.advance()  # Skip >
                return FormNode(AtomNode("<>", line, col), [], line, col)
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

        elif token.type == TokenType.LBRACKET:
            # Parse vector literal [item1 item2 ...]
            return self.parse_vector()

        elif token.type == TokenType.RPAREN:
            # This shouldn't happen - probably a parse error earlier
            self.error(f"Unexpected closing parenthesis - may indicate parsing error in enclosing form")

        elif token.type == TokenType.RANGLE:
            # Stray > - skip it and return None
            # This happens with source files like Beyond Zork that have bracket imbalances
            self.advance()
            return None

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

    def parse_vector(self) -> List[Any]:
        """Parse a vector literal [item1 item2 ...]."""
        line = self.current_token.line
        col = self.current_token.column
        self.expect(TokenType.LBRACKET)
        items = []

        while self.current_token.type != TokenType.RBRACKET:
            if self.current_token.type == TokenType.EOF:
                self.error("Unclosed vector")

            items.append(self.parse_expression())

        self.expect(TokenType.RBRACKET)
        # For now, treat vectors the same as lists
        # In a full implementation, we'd have a VectorNode type
        return items

    def parse_routine(self, line: int, col: int) -> RoutineNode:
        """Parse ROUTINE definition."""
        # <ROUTINE name (params "AUX" aux-vars) body...>
        # or <ROUTINE name activation-name (params "AUX" aux-vars) body...>

        # Get routine name
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected routine name")
        name = self.current_token.value
        self.advance()

        # Check for optional activation name (e.g., FOO-ACT in <ROUTINE FOO FOO-ACT (...)>)
        activation_name = None
        if self.current_token.type == TokenType.ATOM:
            # This is an activation name, add it as first aux variable
            activation_name = self.current_token.value
            self.advance()

        # Parse parameter list
        params = []
        aux_vars = []
        local_defaults = {}  # Map from variable name to default value

        # If activation name was present, add it as first aux variable
        if activation_name:
            aux_vars.append(activation_name)

        opt_params = []  # Track optional params separately for MDL0417 warning
        if self.current_token.type == TokenType.LPAREN:
            self.advance()
            in_aux = False
            in_optional = False

            while self.current_token.type != TokenType.RPAREN:
                # Handle parameter modifiers: "OPTIONAL", "OPT", "AUX", "ARGS", "TUPLE", etc.
                if self.current_token.type == TokenType.STRING:
                    modifier = self.current_token.value
                    if modifier == "AUX":
                        in_aux = True
                        in_optional = False
                    elif modifier in ("OPTIONAL", "OPT"):
                        in_optional = True
                        in_aux = False
                    elif modifier == "ARGS":
                        # Variadic arguments - treat like normal params for now
                        pass
                    # Skip other modifiers like "TUPLE", "NAME", etc.
                    self.advance()
                    continue

                # Handle parameter with default value: (name default-value)
                if self.current_token.type == TokenType.LPAREN:
                    self.advance()
                    if self.current_token.type != TokenType.ATOM:
                        self.error("Expected parameter name in default value form")
                    param_name = self.current_token.value
                    self.advance()
                    # Parse the default value expression
                    default_value = self.parse_expression()
                    self.expect(TokenType.RPAREN)
                    if in_aux:
                        aux_vars.append(param_name)
                    elif in_optional:
                        opt_params.append(param_name)
                        aux_vars.append(param_name)  # Also add to aux_vars for local slot
                    else:
                        params.append(param_name)
                    # Store the default value
                    local_defaults[param_name] = default_value
                    continue

                # Handle simple parameter name
                if self.current_token.type == TokenType.ATOM:
                    if in_aux:
                        aux_vars.append(self.current_token.value)
                    elif in_optional:
                        opt_params.append(self.current_token.value)
                        aux_vars.append(self.current_token.value)  # Also add to aux_vars for local slot
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

        return RoutineNode(name, params, aux_vars, body, line, col, local_defaults, activation_name, opt_params)

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
        """Parse object/room properties.

        Supports two syntaxes:
        - (property value...)  - standard syntax
        - <LIST property value...>  - ZILF shorthand
        """
        properties = {}
        # Track property aliases (IN and LOC are the same, etc.)
        location_props = {'IN', 'LOC'}

        while self.current_token.type in (TokenType.LPAREN, TokenType.LANGLE, TokenType.QUOTE):
            # Handle quoted properties: '(PROP value)
            if self.current_token.type == TokenType.QUOTE:
                self.advance()  # Skip quote
                # Now expect a property definition
                if self.current_token.type != TokenType.LPAREN:
                    self.error("Expected property after quote")
                # Continue to parse the property normally
                # (the quote is just for metaprogramming, we can ignore it during parsing)

            if self.current_token.type == TokenType.LANGLE:
                # Could be <LIST property value...> or a computed property like %<VERSION? ...>
                # Save position before advancing, in case we need to backtrack
                start_pos = self.pos
                self.advance()  # <

                # Check for LIST
                if self.current_token.type == TokenType.ATOM and self.current_token.value == "LIST":
                    # <LIST property value...> syntax
                    self.advance()  # LIST

                    # Get property name
                    if self.current_token.type != TokenType.ATOM:
                        self.error("Expected property name in LIST")
                    prop_name = self.current_token.value
                    self.advance()

                    # Get property value(s)
                    values = []
                    while self.current_token.type != TokenType.RANGLE:
                        if self.current_token.type == TokenType.EOF:
                            self.error("Unclosed LIST property")
                        values.append(self.parse_expression())

                    self.expect(TokenType.RANGLE)

                    # Check for duplicate property (but FLAGS can be combined)
                    # Also, IN can appear twice: (IN OBJECT) for location, (IN "string") for NEXIT
                    # Also, IN can be a direction if declared in <DIRECTIONS>, in which case
                    # (IN TO ROOM) or (IN PER ROUTINE) is a direction exit, not a location
                    is_nexit_string = (prop_name in location_props and len(values) == 1 and
                                       isinstance(values[0], StringNode))
                    # Check if this looks like a direction exit syntax: TO, PER, SORRY, NEXIT, UEXIT, etc.
                    is_direction_exit = False
                    if values and isinstance(values[0], AtomNode):
                        first_val = values[0].value.upper()
                        if first_val in ('TO', 'PER', 'SORRY', 'NEXIT', 'UEXIT', 'NE-EXIT', 'CEXIT', 'FEXIT',
                                         'DEXIT', 'DOOR', 'SETG', 'NONE', 'IF'):
                            is_direction_exit = True
                    if prop_name in properties and prop_name != 'FLAGS' and not is_nexit_string and not is_direction_exit:
                        self.error(f"Duplicate property '{prop_name}' in object definition")
                    # Check for location property conflicts (IN and LOC are the same)
                    # Only check when the value is not a NEXIT string and not a direction exit
                    if prop_name in location_props and not is_nexit_string and not is_direction_exit:
                        for loc_prop in location_props:
                            if loc_prop in properties and loc_prop != prop_name:
                                self.error(f"Duplicate location property: '{prop_name}' conflicts with '{loc_prop}'")
                    # Store property (combine FLAGS if already present)
                    if prop_name == 'FLAGS' and prop_name in properties:
                        # Combine FLAGS values
                        existing = properties[prop_name]
                        if not isinstance(existing, list):
                            existing = [existing]
                        existing.extend(values)
                        properties[prop_name] = existing
                    elif len(values) == 1:
                        properties[prop_name] = values[0]
                    else:
                        properties[prop_name] = values
                else:
                    # Not a LIST form - could be a computed property like %<VERSION? ...>
                    # Parse it as a form and store it as a computed property
                    # Reset position to reparse the form
                    self.pos = start_pos
                    self.current_token = self.tokens[self.pos]

                    # Parse the entire form as an expression
                    form_value = self.parse_expression()

                    # Store it with a generated property name
                    # In a real compiler, this would be evaluated at compile time
                    prop_name = f"__computed_prop_{len(properties)}"
                    properties[prop_name] = form_value
            else:
                # Standard (property value...) syntax
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
                    # Skip semicolons (ZILF separator syntax)
                    if self.current_token.type == TokenType.SEMICOLON:
                        self.advance()
                        continue
                    values.append(self.parse_expression())

                self.expect(TokenType.RPAREN)

                # Check for duplicate property (but FLAGS can be combined)
                # Also, IN can appear twice: (IN OBJECT) for location, (IN "string") for NEXIT
                # Also, IN can be a direction if declared in <DIRECTIONS>, in which case
                # (IN TO ROOM) or (IN PER ROUTINE) is a direction exit, not a location
                is_nexit_string = (prop_name in location_props and len(values) == 1 and
                                   isinstance(values[0], StringNode))
                # Check if this looks like a direction exit syntax: TO, PER, SORRY, NEXIT, UEXIT, etc.
                is_direction_exit = False
                if values and isinstance(values[0], AtomNode):
                    first_val = values[0].value.upper()
                    if first_val in ('TO', 'PER', 'SORRY', 'NEXIT', 'UEXIT', 'NE-EXIT', 'CEXIT', 'FEXIT',
                                     'DEXIT', 'DOOR', 'SETG', 'NONE', 'IF'):
                        is_direction_exit = True
                if prop_name in properties and prop_name != 'FLAGS' and not is_nexit_string and not is_direction_exit:
                    self.error(f"Duplicate property '{prop_name}' in object definition")
                # Check for location property conflicts (IN and LOC are the same)
                # Only check when the value is not a NEXIT string and not a direction exit
                if prop_name in location_props and not is_nexit_string and not is_direction_exit:
                    for loc_prop in location_props:
                        if loc_prop in properties and loc_prop != prop_name:
                            self.error(f"Duplicate location property: '{prop_name}' conflicts with '{loc_prop}'")
                # Store property (combine FLAGS if already present)
                if prop_name == 'FLAGS' and prop_name in properties:
                    # Combine FLAGS values
                    existing = properties[prop_name]
                    if not isinstance(existing, list):
                        existing = [existing]
                    existing.extend(values)
                    properties[prop_name] = existing
                elif len(values) == 1:
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
            elif self.current_token.type == TokenType.LPAREN:
                # Skip object specification forms like (FIND ACTORBIT) (HAVE)
                paren_depth = 0
                while True:
                    if self.current_token.type == TokenType.LPAREN:
                        paren_depth += 1
                    elif self.current_token.type == TokenType.RPAREN:
                        paren_depth -= 1
                        if paren_depth == 0:
                            self.advance()
                            break
                    elif self.current_token.type == TokenType.EOF:
                        self.error("Unclosed parenthesis in SYNTAX")
                    self.advance()
            else:
                self.error("Expected atom or form in SYNTAX pattern")

        # Skip =
        self.advance()

        # Get routine name(s) - can have main action and optional pre-action
        # Example: = V-PUT PRE-PUT
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected routine name after =")
        routine = self.current_token.value
        self.advance()

        # Skip optional additional routines (pre-action handlers, etc.)
        # Syntax can have multiple routines: = ACTION PRE1 PRE2 ...
        # Also handle empty forms <> (used for "no preaction") and action names
        # For now, we just ignore them
        while self.current_token.type != TokenType.RANGLE:
            if self.current_token.type == TokenType.ATOM:
                self.advance()  # Skip additional routines/action names
            elif self.current_token.type == TokenType.LANGLE:
                # Skip form like <> or <expr>
                depth = 0
                while True:
                    if self.current_token.type == TokenType.LANGLE:
                        depth += 1
                    elif self.current_token.type == TokenType.RANGLE:
                        depth -= 1
                        if depth == 0:
                            self.advance()
                            break
                    elif self.current_token.type == TokenType.EOF:
                        self.error("Unclosed form in SYNTAX")
                    self.advance()
            else:
                break  # Unexpected token, let caller handle it

        return SyntaxNode(pattern, routine, line, col)

    def parse_global(self, line: int, col: int) -> GlobalNode:
        """Parse GLOBAL definition."""
        # <GLOBAL name initial-value>
        # ZILF format: <GLOBAL name:TYPE initial-value> - strip :TYPE annotation

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected global variable name")
        name = self.current_token.value
        # Strip ZILF type annotation (e.g., NAME:OBJECT -> NAME)
        if ':' in name:
            name = name.split(':')[0]
        self.advance()

        initial_value = None
        if self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            initial_value = self.parse_expression()

        # ZILF extended format: <GLOBAL name:TYPE initial-value <> <> type-flags>
        # Skip any additional parameters after the initial value
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            if self.current_token.type == TokenType.LANGLE:
                # Skip empty forms <> or other forms
                self.parse_expression()
            else:
                self.advance()  # Skip atoms like BYTE

        return GlobalNode(name, initial_value, line, col)

    def parse_constant(self, line: int, col: int) -> ConstantNode:
        """Parse CONSTANT definition."""
        # <CONSTANT name value>
        # Name can be an atom, or a variable reference for computed names

        if self.current_token.type == TokenType.ATOM:
            name = self.current_token.value
            self.advance()
        elif self.current_token.type in (TokenType.LOCAL_VAR, TokenType.GLOBAL_VAR):
            # Computed constant name (compile-time metaprogramming)
            # Store as special marker for now
            name = f"<computed:{self.current_token.value}>"
            self.advance()
        elif self.current_token.type == TokenType.LANGLE:
            # Computed constant name as a form: <PARSE ...>, etc.
            name_expr = self.parse_expression()
            # Store the form expression as the name
            name = f"<computed-form>"
            # Note: in a real compiler, we'd evaluate name_expr at compile time
        else:
            self.error("Expected constant name")

        value = self.parse_expression()

        return ConstantNode(name, value, line, col)

    def parse_propdef(self, line: int, col: int):
        """Parse PROPDEF property definition.

        Simple format: <PROPDEF name default-value>
        Complex format: <PROPDEF name <> (PATTERN1) (PATTERN2) ...>
        """
        from .ast_nodes import PropdefNode

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected property name")
        name = self.current_token.value
        self.advance()

        # Default value (usually a number)
        default_value = None
        patterns = []

        if self.current_token.type != TokenType.RANGLE:
            # Check for complex PROPDEF with parenthesized pattern definitions
            # Format: <PROPDEF NAME <> (PATTERN1) (PATTERN2) ...>
            if self.current_token.type == TokenType.LANGLE:
                # Could be <> (empty) or a complex form
                self.advance()  # skip <
                if self.current_token.type == TokenType.RANGLE:
                    self.advance()  # skip > - this is <> for default value
                    default_value = None
                    # Now check for pattern definitions
                    while self.current_token.type == TokenType.LPAREN:
                        pattern = self._parse_propdef_pattern()
                        if pattern:
                            patterns.append(pattern)
                else:
                    # It's something else - parse as a form expression
                    # We've already consumed <, so parse the rest of the form
                    default_value = self.parse_form(line, col)
            else:
                default_value = self.parse_expression()

        return PropdefNode(name, default_value, patterns, line, col)

    def _parse_propdef_pattern(self):
        """Parse a single PROPDEF pattern specification.

        Format: (PROP_NAME INPUT... = OUTPUT...)

        Returns a tuple (input_elements, output_elements) where:
        - input_elements: list of (type, value, var_type) tuples
        - output_elements: list of AST nodes representing output encoding
        """
        if self.current_token.type != TokenType.LPAREN:
            return None

        self.advance()  # skip (

        input_elements = []
        output_elements = []
        in_output = False

        while self.current_token.type != TokenType.RPAREN and self.current_token.type != TokenType.EOF:
            if self.current_token.type == TokenType.ATOM:
                atom_val = self.current_token.value
                if atom_val == '=':
                    # Switch to output parsing
                    in_output = True
                    self.advance()
                    continue

                if in_output:
                    # In output section, atoms are typically numbers or constants
                    # Try to parse as integer
                    try:
                        output_elements.append(('LENGTH', int(atom_val)))
                    except ValueError:
                        # It's a constant reference or something else
                        output_elements.append(('ATOM', atom_val))
                    self.advance()
                else:
                    # In input section
                    # Check for VAR:TYPE pattern (like FEET:FIX)
                    if ':' in atom_val:
                        parts = atom_val.split(':', 1)
                        var_name = parts[0]
                        var_type = parts[1] if len(parts) > 1 else 'FIX'
                        input_elements.append(('CAPTURE', var_name, var_type))
                    else:
                        # Literal atom
                        input_elements.append(('LITERAL', atom_val, None))
                    self.advance()

            elif self.current_token.type == TokenType.STRING:
                str_val = self.current_token.value
                if not in_output:
                    # In input section, strings are modifiers like "OPT" or "MANY"
                    input_elements.append(('MODIFIER', str_val, None))
                else:
                    # In output section, strings like "MANY" indicate repeated output
                    output_elements.append(('MODIFIER', str_val))
                self.advance()

            elif self.current_token.type == TokenType.NUMBER:
                if in_output:
                    output_elements.append(('LENGTH', self.current_token.value))
                else:
                    input_elements.append(('LITERAL', self.current_token.value, None))
                self.advance()

            elif self.current_token.type == TokenType.LANGLE:
                # Parse a form like <WORD .FEET> or <BYTE .INCHES> or <>
                self.advance()  # skip <
                if self.current_token.type == TokenType.RANGLE:
                    # Empty form <> - means auto-calculate length
                    output_elements.append(('AUTO_LENGTH', None))
                    self.advance()  # skip >
                elif self.current_token.type == TokenType.ATOM:
                    form_type = self.current_token.value
                    self.advance()
                    form_args = []
                    while self.current_token.type != TokenType.RANGLE and self.current_token.type != TokenType.EOF:
                        if self.current_token.type == TokenType.LOCAL_VAR:
                            # Local variable reference like .FEET
                            form_args.append(('VAR', self.current_token.value))
                            self.advance()
                        elif self.current_token.type == TokenType.PERIOD:
                            # Standalone period followed by atom
                            self.advance()
                            if self.current_token.type == TokenType.ATOM:
                                form_args.append(('VAR', self.current_token.value))
                                self.advance()
                        elif self.current_token.type == TokenType.ATOM:
                            form_args.append(('ATOM', self.current_token.value))
                            self.advance()
                        elif self.current_token.type == TokenType.NUMBER:
                            form_args.append(('NUMBER', self.current_token.value))
                            self.advance()
                        else:
                            self.advance()  # skip unknown tokens
                    if self.current_token.type == TokenType.RANGLE:
                        self.advance()  # skip >
                    output_elements.append(('FORM', form_type, form_args))
                else:
                    # Skip malformed form
                    while self.current_token.type != TokenType.RANGLE and self.current_token.type != TokenType.EOF:
                        self.advance()
                    if self.current_token.type == TokenType.RANGLE:
                        self.advance()

            elif self.current_token.type == TokenType.LPAREN:
                # Nested parentheses in output - constant definition like (HEIGHTSIZE 3)
                self.advance()  # skip (
                const_name = None
                const_value = None
                if self.current_token.type == TokenType.ATOM:
                    const_name = self.current_token.value
                    self.advance()
                    # The value can be a number or a form like <WORD .FEET>
                    if self.current_token.type == TokenType.NUMBER:
                        const_value = ('NUMBER', self.current_token.value)
                        self.advance()
                    elif self.current_token.type == TokenType.LANGLE:
                        # Parse form for constant value
                        self.advance()  # skip <
                        if self.current_token.type == TokenType.ATOM:
                            form_type = self.current_token.value
                            self.advance()
                            form_args = []
                            while self.current_token.type != TokenType.RANGLE and self.current_token.type != TokenType.EOF:
                                if self.current_token.type == TokenType.LOCAL_VAR:
                                    form_args.append(('VAR', self.current_token.value))
                                    self.advance()
                                elif self.current_token.type == TokenType.PERIOD:
                                    self.advance()
                                    if self.current_token.type == TokenType.ATOM:
                                        form_args.append(('VAR', self.current_token.value))
                                        self.advance()
                                elif self.current_token.type == TokenType.ATOM:
                                    form_args.append(('ATOM', self.current_token.value))
                                    self.advance()
                                else:
                                    self.advance()
                            if self.current_token.type == TokenType.RANGLE:
                                self.advance()
                            const_value = ('FORM', form_type, form_args)
                        else:
                            while self.current_token.type != TokenType.RANGLE and self.current_token.type != TokenType.EOF:
                                self.advance()
                            if self.current_token.type == TokenType.RANGLE:
                                self.advance()
                # Skip to closing paren
                while self.current_token.type != TokenType.RPAREN and self.current_token.type != TokenType.EOF:
                    self.advance()
                if self.current_token.type == TokenType.RPAREN:
                    self.advance()
                if const_name:
                    output_elements.append(('CONSTANT', const_name, const_value))

            else:
                # Skip unknown token types
                self.advance()

        if self.current_token.type == TokenType.RPAREN:
            self.advance()  # skip )

        return (input_elements, output_elements)

    def parse_defmac(self, line: int, col: int):
        """Parse DEFMAC macro definition.

        Syntax: <DEFMAC name (params...) body>

        Parameter types:
        - 'PARAM  - quoted parameter (evaluated at macro definition time)
        - PARAM   - unquoted parameter (evaluated at expansion time)
        - "TUPLE" - variable-length parameter list
        - "AUX"   - auxiliary variables

        Examples:
        <DEFMAC ENABLE ('INT) <FORM PUT .INT ,C-ENABLED? 1>>
        <DEFMAC VERB? ("TUPLE" ATMS "AUX" (O ()) (L ())) ...>
        """
        from .ast_nodes import MacroNode

        # Parse macro name
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected macro name")
        name = self.current_token.value
        self.advance()

        # Parse parameter list
        params = []
        if self.current_token.type == TokenType.LPAREN:
            self.advance()  # (

            aux_mode = False
            tuple_mode = False
            optional_mode = False

            while self.current_token.type != TokenType.RPAREN:
                if self.current_token.type == TokenType.EOF:
                    self.error("Unclosed parameter list in DEFMAC")

                # Check for special keywords
                if self.current_token.type == TokenType.STRING:
                    keyword = self.current_token.value
                    if keyword == "AUX":
                        aux_mode = True
                        tuple_mode = False
                        optional_mode = False  # AUX overrides OPTIONAL
                        self.advance()
                        continue
                    elif keyword in ("OPTIONAL", "OPT"):
                        # Optional parameters - mark subsequent params as optional
                        optional_mode = True
                        self.advance()
                        continue
                    elif keyword in ("TUPLE", "ARGS"):
                        # TUPLE and ARGS both mean variadic parameters
                        tuple_mode = True
                        self.advance()
                        # Next token should be the tuple variable name
                        if self.current_token.type != TokenType.ATOM:
                            self.error(f"Expected variable name after \"{keyword}\"")
                        param_name = self.current_token.value
                        # TUPLE params: (name, is_quoted, is_tuple, is_aux, is_optional)
                        params.append((param_name, False, True, False, False))
                        self.advance()
                        continue

                # Check for quoted parameter
                is_quoted = False
                if self.current_token.type == TokenType.QUOTE:
                    # Quote prefix for parameter: 'PARAM
                    is_quoted = True
                    self.advance()

                # Parse parameter (can be simple atom or with default value)
                if self.current_token.type == TokenType.ATOM:
                    param_name = self.current_token.value
                    # Params: (name, is_quoted, is_tuple, is_aux, is_optional)
                    params.append((param_name, is_quoted, False, aux_mode, optional_mode))
                    self.advance()
                elif self.current_token.type == TokenType.LPAREN:
                    # Variable with default value: (VAR default) or ('VAR default)
                    self.advance()  # (

                    # Check for quoted parameter name inside parens
                    param_is_quoted = False
                    if self.current_token.type == TokenType.QUOTE:
                        param_is_quoted = True
                        self.advance()

                    if self.current_token.type != TokenType.ATOM:
                        self.error("Expected variable name in binding")
                    param_name = self.current_token.value
                    self.advance()

                    # Parse default value (we'll store it but won't use it yet)
                    default_val = self.parse_expression()

                    # Params with defaults are treated as AUX-like (optional)
                    # (name, is_quoted, is_tuple, is_aux, is_optional)
                    params.append((param_name, param_is_quoted, False, True, True))
                    self.expect(TokenType.RPAREN)
                else:
                    self.error(f"Unexpected token in parameter list: {self.current_token.type}")

            self.expect(TokenType.RPAREN)

        # Parse macro body (one or more expressions until >)
        body = []
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            body.append(self.parse_expression())

        # If only one expression, unwrap it for backwards compatibility
        if len(body) == 1:
            body = body[0]

        return MacroNode(name, params, body, line, col)

    def parse_buzz(self, line: int, col: int):
        """Parse BUZZ noise word declaration.

        Syntax: <BUZZ word1 word2 word3 ...>

        Example: <BUZZ A AN THE IS ARE AND OF THEN>
        """
        from .ast_nodes import BuzzNode

        words = []
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            if self.current_token.type == TokenType.ATOM:
                word = self.current_token.value
                # Handle escape sequences like \. and \,
                if word.startswith('\\'):
                    word = word[1:]  # Remove backslash
                words.append(word)
                self.advance()
            else:
                self.error(f"Expected word in BUZZ declaration, got {self.current_token.type}")

        return BuzzNode(words, line, col)

    def parse_synonym_declaration(self, line: int, col: int):
        """Parse standalone SYNONYM declaration (not in an object).

        Syntax: <SYNONYM word1 word2 word3 ...>

        Example: <SYNONYM NORTH N FORE FORWARD F>
        """
        from .ast_nodes import SynonymNode

        words = []
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            if self.current_token.type == TokenType.ATOM:
                word = self.current_token.value
                # Handle escape sequences like \. and \,
                if word.startswith('\\'):
                    word = word[1:]
                words.append(word)
                self.advance()
            else:
                self.error(f"Expected word in SYNONYM declaration, got {self.current_token.type}")

        return SynonymNode(words, line, col)

    def parse_bit_synonym(self, line: int, col: int):
        """Parse BIT-SYNONYM flag alias declaration.

        Syntax: <BIT-SYNONYM original-flag alias-flag>

        Example: <BIT-SYNONYM TOUCHBIT TOUCHEDBIT>
        This makes TOUCHEDBIT an alias for TOUCHBIT.
        """
        from .ast_nodes import BitSynonymNode

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected original flag name in BIT-SYNONYM")
        original = self.current_token.value
        self.advance()

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected alias flag name in BIT-SYNONYM")
        alias = self.current_token.value
        self.advance()

        return BitSynonymNode(original, alias, line, col)

    def parse_remove_synonym(self, line: int, col: int):
        """Parse REMOVE-SYNONYM declaration.

        Syntax: <REMOVE-SYNONYM word>

        Example: <REMOVE-SYNONYM GET>
        This removes GET from being a synonym so it can be used independently.
        """
        from .ast_nodes import RemoveSynonymNode

        if self.current_token.type != TokenType.ATOM:
            self.error("Expected word in REMOVE-SYNONYM")
        word = self.current_token.value
        self.advance()

        return RemoveSynonymNode(word, line, col)

    def parse_table(self, table_type: str, line: int, col: int) -> TableNode:
        """Parse TABLE/ITABLE/LTABLE definition."""
        flags = []
        size = None
        values = []

        # Check for size or bare flags (ITABLE/LTABLE)
        # BYTE/WORD can appear as bare atoms before size: <ITABLE BYTE 2500>
        if table_type in ("ITABLE", "LTABLE"):
            # Handle bare BYTE/WORD flags before size
            while self.current_token.type == TokenType.ATOM and \
                  self.current_token.value in ('BYTE', 'WORD', 'PURE', 'LENGTH'):
                flags.append(self.current_token.value)
                self.advance()
            if self.current_token.type == TokenType.NUMBER:
                size = self.current_token.value
                self.advance()

        # Check for flags (BYTE), (PURE), (PATTERN (BYTE WORD)), etc.
        # Flags can be simple atoms or nested patterns like (PATTERN (BYTE [REST WORD]))
        if self.current_token.type == TokenType.LPAREN:
            self.advance()
            paren_depth = 1
            while paren_depth > 0 and self.current_token.type != TokenType.EOF:
                if self.current_token.type == TokenType.RPAREN:
                    paren_depth -= 1
                    if paren_depth > 0:
                        self.advance()
                elif self.current_token.type == TokenType.LPAREN:
                    paren_depth += 1
                    self.advance()
                elif self.current_token.type == TokenType.ATOM:
                    # Only collect top-level atoms as flags (BYTE, PURE, PATTERN, etc.)
                    if paren_depth == 1:
                        flags.append(self.current_token.value)
                    self.advance()
                elif self.current_token.type == TokenType.LBRACKET:
                    # Skip bracketed patterns like [REST WORD]
                    self.advance()
                    while self.current_token.type not in (TokenType.RBRACKET, TokenType.EOF):
                        self.advance()
                    if self.current_token.type == TokenType.RBRACKET:
                        self.advance()
                else:
                    # Skip other tokens inside nested patterns
                    self.advance()
            if self.current_token.type == TokenType.RPAREN:
                self.advance()  # consume final )

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
            if condition is None:
                # Skip None results (from stray brackets)
                continue

            # Parse actions
            actions = []
            while self.current_token.type not in (TokenType.RPAREN, TokenType.RANGLE, TokenType.EOF):
                expr = self.parse_expression()
                if expr is not None:  # Skip None results (from stray brackets)
                    actions.append(expr)

            if self.current_token.type == TokenType.RPAREN:
                self.advance()
            # Tolerate EOF or RANGLE instead of RPAREN for broken source
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
        # Syntax: ((var init) (var init) ...) or ((var init) var var ...)
        bindings = []
        if self.current_token.type == TokenType.LPAREN:
            self.advance()  # (

            # Parse variable bindings - can be (var init), just var, or expressions
            # In quasiquote contexts, bindings can be unquote expressions like ~.VAR
            while self.current_token.type != TokenType.RPAREN:
                if self.current_token.type == TokenType.LPAREN:
                    # (var init) form or (unquote-expr) for quasiquote
                    self.advance()  # (

                    # Check for unquote expression like (~.VAR)
                    if self.current_token.type == TokenType.ATOM and self.current_token.value in ('~', '~!'):
                        # This is an unquote expression in the binding
                        # Parse it as an expression and use it as the binding
                        self.pos -= 1  # Back up to re-parse with (
                        self.current_token = self.tokens[self.pos - 1] if self.pos > 0 else None
                        self.advance()  # Get back to (
                        binding_expr = self.parse_expression()
                        bindings.append((binding_expr, None))  # Store expr instead of name
                    elif self.current_token.type == TokenType.ATOM:
                        # Normal (var init) form
                        var_name = self.current_token.value
                        self.advance()

                        # Parse initial value
                        init_value = self.parse_expression()

                        self.expect(TokenType.RPAREN)
                        bindings.append((var_name, init_value))
                    else:
                        # Could be a complex expression binding
                        binding_expr = self.parse_expression()
                        self.expect(TokenType.RPAREN)
                        bindings.append((binding_expr, None))
                elif self.current_token.type == TokenType.ATOM:
                    atom_val = self.current_token.value
                    # Check for unquote: ~EXPR
                    if atom_val in ('~', '~!'):
                        binding_expr = self.parse_expression()
                        bindings.append((binding_expr, None))
                    else:
                        # Plain var form (no initialization)
                        var_name = self.current_token.value
                        self.advance()
                        bindings.append((var_name, None))
                elif self.current_token.type == TokenType.LOCAL_VAR:
                    # Local variable reference in binding (.VAR) - for quasiquote expansion
                    binding_expr = self.parse_expression()
                    bindings.append((binding_expr, None))
                else:
                    self.error(f"Expected variable binding in REPEAT, got {self.current_token.type}")

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

    def parse_newtype(self, line: int, col: int):
        """Parse NEWTYPE type definition.

        Syntax: <NEWTYPE type-name base-type type-spec>

        Example: <NEWTYPE RSEC VECTOR '!<VECTOR ATOM <OR '* FIX> ...>>

        This is a compile-time MDL construct. We parse and store it but
        it doesn't generate runtime code. It defines a new type based on
        a primitive type (usually VECTOR) with specific field types.
        """
        from .ast_nodes import ConstantNode, NumberNode

        # Parse type name
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected type name in NEWTYPE")
        type_name = self.current_token.value
        self.advance()

        # Parse base type (usually VECTOR, LIST, etc.)
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected base type in NEWTYPE")
        base_type = self.current_token.value
        self.advance()

        # Skip the type specification - it's MDL type info we don't use
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            self.parse_expression()

        # Return as a constant that represents the type
        # Value 0 is used as a placeholder - real MDL would track type info
        return ConstantNode(type_name, NumberNode(0, line, col), line, col)

    def parse_offset(self, line: int, col: int):
        """Parse OFFSET structure field accessor.

        Syntax: <OFFSET index type-name field-type>

        Example: <SETG RSEC-RTN <OFFSET 1 RSEC ATOM>>

        Returns the index as a number - used to access fields in typed structures.
        In Z-machine terms, this is just a constant index into a table/vector.
        """
        from .ast_nodes import NumberNode

        # Parse index
        if self.current_token.type != TokenType.NUMBER:
            self.error("Expected index number in OFFSET")
        index = self.current_token.value
        self.advance()

        # Parse type name (we track but don't use for code generation)
        if self.current_token.type != TokenType.ATOM:
            self.error("Expected type name in OFFSET")
        # type_name = self.current_token.value  # Not used in Z-machine code
        self.advance()

        # Skip field type specification
        while self.current_token.type not in (TokenType.RANGLE, TokenType.EOF):
            self.parse_expression()

        # Return the index as a number node - this is what gets used at runtime
        return NumberNode(index, line, col)


def parse(tokens: List[Token], filename: str = "<input>") -> Program:
    """Convenience function to parse tokens into AST."""
    parser = Parser(tokens, filename)
    return parser.parse()
