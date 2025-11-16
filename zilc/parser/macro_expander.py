"""
Macro expansion engine for ZIL DEFMAC.

Handles macro definition storage and expansion during compilation.
"""

from typing import Dict, List, Optional, Any
from .ast_nodes import *
import copy


class MacroExpander:
    """Handles macro storage and expansion."""

    def __init__(self):
        self.macros: Dict[str, MacroNode] = {}

    def define_macro(self, macro: MacroNode):
        """Store a macro definition."""
        self.macros[macro.name.upper()] = macro

    def is_macro(self, name: str) -> bool:
        """Check if a name is a defined macro."""
        return name.upper() in self.macros

    def expand(self, form: FormNode) -> Optional[ASTNode]:
        """
        Expand a form if it's a macro call.

        Returns the expanded form, or None if not a macro.
        """
        # Check if the form operator is a macro
        if not isinstance(form.operator, AtomNode):
            return None

        macro_name = form.operator.value.upper()
        if macro_name not in self.macros:
            return None

        macro = self.macros[macro_name]

        # Build parameter bindings
        bindings = self._bind_parameters(macro, form.operands)

        # Expand the macro body with parameter substitution
        expanded = self._substitute(macro.body, bindings)

        return expanded

    def _bind_parameters(self, macro: MacroNode, args: List[ASTNode]) -> Dict[str, Any]:
        """
        Bind macro arguments to parameters.

        Returns a dictionary mapping parameter names to their values.
        """
        bindings = {}
        arg_index = 0

        for param_name, is_quoted, is_tuple, is_aux in macro.params:
            if is_tuple:
                # Collect all remaining arguments
                bindings[param_name] = args[arg_index:]
                arg_index = len(args)
            elif is_aux:
                # AUX variables get default values (empty list for now)
                bindings[param_name] = FormNode(AtomNode("()"), [])
            else:
                # Regular parameter
                if arg_index < len(args):
                    if is_quoted:
                        # Quoted parameter: evaluate at definition time
                        # For now, just store as-is
                        bindings[param_name] = args[arg_index]
                    else:
                        # Unquoted parameter: store for later expansion
                        bindings[param_name] = args[arg_index]
                    arg_index += 1
                else:
                    # Missing argument
                    bindings[param_name] = None

        return bindings

    def _substitute(self, node: ASTNode, bindings: Dict[str, Any]) -> ASTNode:
        """
        Recursively substitute parameters in the macro body.

        Handles:
        - .VAR - parameter reference
        - !.VAR - splicing parameter (for lists)
        - <FORM ...> - construct new forms
        """
        # Handle local variable references (.VAR)
        if isinstance(node, LocalVarNode):
            var_name = node.name.upper()
            if var_name in bindings:
                value = bindings[var_name]
                if value is None:
                    return node
                # Return a copy of the bound value
                return copy.deepcopy(value)
            return node

        # Handle atoms (might be special keywords)
        if isinstance(node, AtomNode):
            # Check for splice operator: !
            # This is tricky - we'd need to handle this in the parent form
            return node

        # Handle forms
        if isinstance(node, FormNode):
            operator = node.operator

            # Special handling for FORM constructor
            if isinstance(operator, AtomNode) and operator.value.upper() == "FORM":
                # <FORM op arg1 arg2 ...>
                # Constructs a new form with evaluated arguments
                if len(node.operands) == 0:
                    return node

                new_operator = self._substitute(node.operands[0], bindings)
                new_operands = []

                for i, operand in enumerate(node.operands[1:], 1):
                    # Check for splice operator
                    if isinstance(operand, FormNode) and len(operand.operands) > 0:
                        # Check if it's a splice like !.VAR
                        if (isinstance(operand.operator, AtomNode) and
                            operand.operator.value == "!" and
                            len(operand.operands) == 1 and
                            isinstance(operand.operands[0], LocalVarNode)):
                            # Splice the list
                            var_name = operand.operands[0].name.upper()
                            if var_name in bindings:
                                value = bindings[var_name]
                                if isinstance(value, list):
                                    # Splice in all elements
                                    new_operands.extend([copy.deepcopy(v) for v in value])
                                else:
                                    new_operands.append(copy.deepcopy(value))
                            continue

                    substituted = self._substitute(operand, bindings)
                    new_operands.append(substituted)

                return FormNode(new_operator, new_operands, node.line, node.column)

            # Regular form - substitute recursively
            new_operator = self._substitute(operator, bindings)
            new_operands = []

            for operand in node.operands:
                # Check for splice operator in regular forms
                # In ZIL, !.VAR at the top level of a form splices the list
                if (isinstance(operand, FormNode) and
                    isinstance(operand.operator, AtomNode) and
                    operand.operator.value == "!" and
                    len(operand.operands) == 1 and
                    isinstance(operand.operands[0], LocalVarNode)):
                    # Splice the list
                    var_name = operand.operands[0].name.upper()
                    if var_name in bindings:
                        value = bindings[var_name]
                        if isinstance(value, list):
                            new_operands.extend([copy.deepcopy(v) for v in value])
                        else:
                            new_operands.append(copy.deepcopy(value))
                    continue

                substituted = self._substitute(operand, bindings)
                new_operands.append(substituted)

            return FormNode(new_operator, new_operands, node.line, node.column)

        # For other node types, return as-is
        return node

    def expand_all(self, program: Program) -> Program:
        """
        Expand all macros in a program.

        First, collect all macro definitions.
        Then, recursively expand all forms in routines, objects, etc.
        """
        # Register all macros
        for macro in program.macros:
            self.define_macro(macro)

        # Expand macros in routines
        for routine in program.routines:
            routine.body = [self._expand_recursive(stmt) for stmt in routine.body]

        # Expand macros in objects
        for obj in program.objects:
            for key, value in obj.properties.items():
                if isinstance(value, ASTNode):
                    obj.properties[key] = self._expand_recursive(value)
                elif isinstance(value, list):
                    obj.properties[key] = [
                        self._expand_recursive(v) if isinstance(v, ASTNode) else v
                        for v in value
                    ]

        # Expand macros in rooms
        for room in program.rooms:
            for key, value in room.properties.items():
                if isinstance(value, ASTNode):
                    room.properties[key] = self._expand_recursive(value)
                elif isinstance(value, list):
                    room.properties[key] = [
                        self._expand_recursive(v) if isinstance(v, ASTNode) else v
                        for v in value
                    ]

        # Expand macros in globals
        for global_node in program.globals:
            if global_node.initial_value:
                global_node.initial_value = self._expand_recursive(global_node.initial_value)

        # Expand macros in constants
        for const in program.constants:
            if const.value:
                const.value = self._expand_recursive(const.value)

        return program

    def _expand_recursive(self, node: ASTNode) -> ASTNode:
        """Recursively expand macros in an AST node."""
        if isinstance(node, FormNode):
            # First, try to expand this form if it's a macro
            expanded = self.expand(node)
            if expanded is not None:
                # Macro was expanded, continue expanding recursively
                return self._expand_recursive(expanded)

            # Not a macro, recursively expand operands
            new_operator = self._expand_recursive(node.operator)
            new_operands = [self._expand_recursive(op) for op in node.operands]
            return FormNode(new_operator, new_operands, node.line, node.column)

        elif isinstance(node, CondNode):
            # Expand COND clauses
            new_clauses = []
            for condition, actions in node.clauses:
                new_condition = self._expand_recursive(condition)
                new_actions = [self._expand_recursive(action) for action in actions]
                new_clauses.append((new_condition, new_actions))
            return CondNode(new_clauses, node.line, node.column)

        elif isinstance(node, RepeatNode):
            # Expand REPEAT body
            new_body = [self._expand_recursive(stmt) for stmt in node.body]
            new_condition = self._expand_recursive(node.condition) if node.condition else None
            return RepeatNode(node.bindings, new_condition, new_body, node.line, node.column)

        # For other node types, return as-is
        return node
