"""
Macro expansion engine for ZIL DEFMAC.

Handles macro definition storage and expansion during compilation.
Includes support for quasiquote (`) and unquote (~, ~!) operators.
Also includes MDL compile-time evaluation for MAPF/FUNCTION constructs.
"""

from typing import Dict, List, Optional, Any, Union, Tuple
from .ast_nodes import *
import copy


class MapStop(Exception):
    """Signal to stop MAPF/MAPR iteration."""
    pass


class MapRet(Exception):
    """Signal to return value(s) from MAPF/MAPR iteration."""
    def __init__(self, values: List[Any]):
        self.values = values


class MDLEvaluator:
    """
    Compile-time MDL evaluator for macro expansion.

    Handles FUNCTION, MAPF, MAPR and related MDL constructs
    that need to be evaluated at compile time during macro expansion.
    """

    def __init__(self, macro_expander: 'MacroExpander'):
        self.macro_expander = macro_expander
        self.env: Dict[str, Any] = {}  # Current evaluation environment

    def evaluate(self, node: ASTNode, env: Dict[str, Any] = None) -> Any:
        """Evaluate an MDL expression at compile time."""
        if env is None:
            env = self.env

        # Handle atoms
        if isinstance(node, AtomNode):
            name = node.value.upper()
            # Check for special atoms
            if name == 'T':
                return True
            elif name == '<>' or name == 'FALSE':
                return False
            # Look up in environment
            if name in env:
                return env[name]
            return node  # Return as-is if not found

        # Handle local variable references (.VAR)
        if isinstance(node, LocalVarNode):
            name = node.name.upper()
            if name in env:
                return env[name]
            return None

        # Handle global variable references (,VAR)
        if isinstance(node, GlobalVarNode):
            name = node.name.upper()
            if name in env:
                return env[name]
            # Return as GlobalVarNode - will be resolved at runtime
            return node

        # Handle numbers
        if isinstance(node, NumberNode):
            return node.value

        # Handle strings
        if isinstance(node, StringNode):
            return node.value

        # Handle quasiquoted expressions
        if isinstance(node, QuasiquoteNode):
            return self._expand_quasiquote(node.expr, env)

        # Handle forms (function calls)
        if isinstance(node, FormNode):
            return self._evaluate_form(node, env)

        # Handle COND nodes (parsed specially by the parser)
        if isinstance(node, CondNode):
            return self._eval_cond_node(node, env)

        # Handle lists
        if isinstance(node, list):
            return [self.evaluate(item, env) for item in node]

        # Return other nodes as-is
        return node

    def _evaluate_form(self, form: FormNode, env: Dict[str, Any]) -> Any:
        """Evaluate a form (function call)."""
        if not isinstance(form.operator, AtomNode):
            return form

        op_name = form.operator.value.upper()
        operands = form.operands

        # MDL primitives
        if op_name == 'QUOTE':
            # Quote returns the unevaluated expression
            if operands:
                return operands[0]
            return None
        elif op_name == 'MAPF':
            return self._eval_mapf(operands, env)
        elif op_name == 'MAPR':
            return self._eval_mapr(operands, env)
        elif op_name == 'FUNCTION':
            return self._make_function(operands, env)
        elif op_name == 'COND':
            return self._eval_cond(operands, env)
        elif op_name == 'SET':
            return self._eval_set(operands, env)
        elif op_name == 'SETG':
            return self._eval_setg(operands, env)
        elif op_name == 'NTH':
            return self._eval_nth(operands, env)
        elif op_name == 'REST':
            return self._eval_rest(operands, env)
        elif op_name == 'EMPTY?':
            return self._eval_empty(operands, env)
        elif op_name == 'LENGTH':
            return self._eval_length(operands, env)
        elif op_name == 'TYPE?':
            return self._eval_type(operands, env)
        elif op_name == 'SPNAME':
            return self._eval_spname(operands, env)
        elif op_name == '=?' or op_name == 'EQUAL?':
            return self._eval_equal(operands, env)
        elif op_name == '==?':
            return self._eval_eq(operands, env)
        elif op_name == 'N==?':
            return not self._eval_eq(operands, env)
        elif op_name == 'OR':
            return self._eval_or(operands, env)
        elif op_name == 'AND':
            return self._eval_and(operands, env)
        elif op_name == 'NOT':
            return self._eval_not(operands, env)
        elif op_name == 'MAPRET':
            raise MapRet([self.evaluate(op, env) for op in operands])
        elif op_name == 'MAPSTOP':
            raise MapStop()
        elif op_name == 'FORM':
            return self._eval_form_constructor(operands, env)
        elif op_name == 'LIST':
            return [self.evaluate(op, env) for op in operands]
        elif op_name == 'GVAL':
            return self._eval_gval(operands, env)
        elif op_name == 'LVAL':
            return self._eval_lval(operands, env)
        elif op_name == 'PARSE':
            return self._eval_parse(operands, env)
        elif op_name == 'STRING':
            return self._eval_string(operands, env)
        elif op_name == 'ERROR':
            # Compile-time error - ignore for now
            return None
        elif op_name == 'ASSIGNED?':
            return self._eval_assigned(operands, env)
        elif op_name == 'EVAL':
            return self._eval_eval(operands, env)
        elif op_name == 'IFFLAG':
            return self._eval_ifflag(operands, env)

        # Unknown form - return as-is (will be processed at runtime)
        return form

    def _eval_mapf(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """
        Evaluate MAPF (map and collect results).

        <MAPF collector function arg1 arg2 ...>

        Applies function to successive elements and collects results.
        """
        if len(operands) < 2:
            return []

        collector = self.evaluate(operands[0], env)
        func = self.evaluate(operands[1], env)

        # Get iteration source(s)
        sources = [self.evaluate(op, env) for op in operands[2:]]

        # If no sources, the function generates its own data (like TELL macro)
        results = []

        if not sources:
            # Function is called repeatedly until MAPSTOP
            if callable(func):
                while True:
                    try:
                        result = func(env)
                        if result is not None:
                            if isinstance(result, list):
                                results.extend(result)
                            else:
                                results.append(result)
                    except MapStop:
                        break
                    except MapRet as mr:
                        results.extend(mr.values)
        else:
            # Iterate over sources
            source = sources[0] if sources else []
            if isinstance(source, list):
                for item in source:
                    try:
                        if callable(func):
                            result = func(env, item)
                        else:
                            result = item
                        if result is not None:
                            if isinstance(result, list):
                                results.extend(result)
                            else:
                                results.append(result)
                    except MapStop:
                        break
                    except MapRet as mr:
                        results.extend(mr.values)

        return results

    def _eval_mapr(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate MAPR (map and return last non-false result)."""
        if len(operands) < 2:
            return None

        collector = self.evaluate(operands[0], env)
        func = self.evaluate(operands[1], env)
        sources = [self.evaluate(op, env) for op in operands[2:]]

        result = None
        source = sources[0] if sources else []

        if isinstance(source, list):
            for item in source:
                try:
                    if callable(func):
                        r = func(env, item)
                    else:
                        r = item
                    if r:
                        result = r
                except MapStop:
                    break
                except MapRet as mr:
                    if mr.values:
                        result = mr.values[-1]

        return result

    def _make_function(self, operands: List[ASTNode], env: Dict[str, Any]) -> callable:
        """
        Create a callable from a FUNCTION form.

        <FUNCTION (params...) body...>
        or
        <FUNCTION ("AUX" var1 var2...) body...>
        """
        if not operands:
            return lambda e, *args: None

        # Parse parameter list
        param_spec = operands[0]
        body = operands[1:]

        params = []
        aux_vars = []
        in_aux = False

        if isinstance(param_spec, FormNode):
            # Parameter list as form (params...)
            for p in [param_spec.operator] + param_spec.operands:
                if isinstance(p, AtomNode):
                    name = p.value.upper()
                    if name == '"AUX"' or name == 'AUX':
                        in_aux = True
                    elif in_aux:
                        aux_vars.append(name)
                    else:
                        params.append(name)
                elif isinstance(p, StringNode):
                    if p.value.upper() == 'AUX':
                        in_aux = True

        evaluator = self

        def mdl_function(call_env: Dict[str, Any], *args) -> Any:
            """Execute the MDL function.

            Note: We use call_env directly (not a copy) so that modifications
            to captured variables (like .A in TELL macro) persist across
            iterations when used with MAPF.
            """
            # Bind parameters directly in call_env
            for i, param in enumerate(params):
                if i < len(args):
                    call_env[param] = args[i]
                else:
                    call_env[param] = None

            # Initialize AUX variables (fresh each call)
            for var in aux_vars:
                if var not in call_env:
                    call_env[var] = None

            # Execute body
            result = None
            for stmt in body:
                result = evaluator.evaluate(stmt, call_env)

            return result

        return mdl_function

    def _eval_cond(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate COND (conditional)."""
        for clause in operands:
            if isinstance(clause, FormNode):
                # Clause is (test result...)
                all_parts = [clause.operator] + clause.operands
                if not all_parts:
                    continue

                test = self.evaluate(all_parts[0], env)

                # Check if test is truthy
                if self._is_truthy(test):
                    # Evaluate and return results
                    result = None
                    for expr in all_parts[1:]:
                        result = self.evaluate(expr, env)
                    return result

        return None

    def _eval_cond_node(self, node: CondNode, env: Dict[str, Any]) -> Any:
        """Evaluate a CondNode (parsed COND form)."""
        for condition, actions in node.clauses:
            # Evaluate the condition
            test = self.evaluate(condition, env)

            # Check for ELSE/T/OTHERWISE as always-true
            if isinstance(condition, AtomNode):
                cond_name = condition.value.upper()
                if cond_name in ('T', 'ELSE', 'OTHERWISE'):
                    test = True

            # Check if test is truthy
            if self._is_truthy(test):
                # Evaluate and return results
                result = None
                for expr in actions:
                    result = self.evaluate(expr, env)
                return result

        return None

    def _eval_set(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate SET (set local variable)."""
        if len(operands) < 2:
            return None

        var_name = operands[0]
        if isinstance(var_name, AtomNode):
            name = var_name.value.upper()
        elif isinstance(var_name, LocalVarNode):
            name = var_name.name.upper()
        else:
            return None

        value = self.evaluate(operands[1], env)
        env[name] = value
        return value

    def _eval_setg(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate SETG (set global variable)."""
        if len(operands) < 2:
            return None

        var_name = operands[0]
        if isinstance(var_name, AtomNode):
            name = var_name.value.upper()
        else:
            return None

        value = self.evaluate(operands[1], env)
        env[name] = value
        return value

    def _eval_nth(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate NTH (get nth element, 1-indexed)."""
        if len(operands) < 2:
            return None

        lst = self.evaluate(operands[0], env)
        n = self.evaluate(operands[1], env)

        if isinstance(lst, list) and isinstance(n, int):
            idx = n - 1  # MDL is 1-indexed
            if 0 <= idx < len(lst):
                return lst[idx]

        return None

    def _eval_rest(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate REST (get tail of list)."""
        if not operands:
            return []

        lst = self.evaluate(operands[0], env)
        n = 1
        if len(operands) > 1:
            n = self.evaluate(operands[1], env)
            if not isinstance(n, int):
                n = 1

        if isinstance(lst, list):
            return lst[n:]

        return []

    def _eval_empty(self, operands: List[ASTNode], env: Dict[str, Any]) -> bool:
        """Evaluate EMPTY? (check if list is empty)."""
        if not operands:
            return True

        val = self.evaluate(operands[0], env)

        if isinstance(val, list):
            return len(val) == 0
        if val is None:
            return True

        return False

    def _eval_length(self, operands: List[ASTNode], env: Dict[str, Any]) -> int:
        """Evaluate LENGTH (get length of list/string)."""
        if not operands:
            return 0

        val = self.evaluate(operands[0], env)

        if isinstance(val, (list, str)):
            return len(val)

        return 0

    def _eval_type(self, operands: List[ASTNode], env: Dict[str, Any]) -> bool:
        """Evaluate TYPE? (check type of value)."""
        if len(operands) < 2:
            return False

        val = self.evaluate(operands[0], env)

        for type_op in operands[1:]:
            type_name = None
            if isinstance(type_op, AtomNode):
                type_name = type_op.value.upper()

            if type_name:
                if type_name == 'ATOM' and isinstance(val, AtomNode):
                    return True
                if type_name == 'STRING' and isinstance(val, (str, StringNode)):
                    return True
                if type_name == 'ZSTRING' and isinstance(val, StringNode):
                    return True
                if type_name == 'FIX' and isinstance(val, (int, NumberNode)):
                    return True
                if type_name == 'LIST' and isinstance(val, list):
                    return True
                if type_name == 'FORM' and isinstance(val, FormNode):
                    return True
                if type_name == 'LVAL' and isinstance(val, LocalVarNode):
                    return True
                if type_name == 'GVAL' and isinstance(val, GlobalVarNode):
                    return True

        return False

    def _eval_spname(self, operands: List[ASTNode], env: Dict[str, Any]) -> str:
        """Evaluate SPNAME (get print name of atom)."""
        if not operands:
            return ""

        val = self.evaluate(operands[0], env)

        if isinstance(val, AtomNode):
            return val.value.upper()
        if isinstance(val, str):
            return val.upper()

        return ""

    def _eval_equal(self, operands: List[ASTNode], env: Dict[str, Any]) -> bool:
        """Evaluate =? (string equality)."""
        if len(operands) < 2:
            return False

        val1 = self.evaluate(operands[0], env)
        val2 = self.evaluate(operands[1], env)

        # Convert to strings for comparison
        str1 = val1 if isinstance(val1, str) else (val1.value if hasattr(val1, 'value') else str(val1))
        str2 = val2 if isinstance(val2, str) else (val2.value if hasattr(val2, 'value') else str(val2))

        return str(str1).upper() == str(str2).upper()

    def _eval_eq(self, operands: List[ASTNode], env: Dict[str, Any]) -> bool:
        """Evaluate ==? (identity/numeric equality)."""
        if len(operands) < 2:
            return False

        val1 = self.evaluate(operands[0], env)
        val2 = self.evaluate(operands[1], env)

        # Numeric comparison
        if isinstance(val1, (int, NumberNode)) and isinstance(val2, (int, NumberNode)):
            n1 = val1 if isinstance(val1, int) else val1.value
            n2 = val2 if isinstance(val2, int) else val2.value
            return n1 == n2

        return val1 == val2

    def _eval_or(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate OR (logical or, returns first truthy value)."""
        for op in operands:
            val = self.evaluate(op, env)
            if self._is_truthy(val):
                return val
        return False

    def _eval_and(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate AND (logical and, returns last truthy value or first falsy)."""
        result = True
        for op in operands:
            val = self.evaluate(op, env)
            if not self._is_truthy(val):
                return False
            result = val
        return result

    def _eval_not(self, operands: List[ASTNode], env: Dict[str, Any]) -> bool:
        """Evaluate NOT (logical negation)."""
        if not operands:
            return True
        val = self.evaluate(operands[0], env)
        return not self._is_truthy(val)

    def _eval_form_constructor(self, operands: List[ASTNode], env: Dict[str, Any]) -> FormNode:
        """Evaluate FORM (construct a new form)."""
        if not operands:
            return FormNode(AtomNode("NOOP"), [], 0, 0)

        # Evaluate all operands
        evaluated = [self.evaluate(op, env) for op in operands]

        # First element is operator, rest are operands
        operator = evaluated[0]
        if not isinstance(operator, ASTNode):
            if isinstance(operator, str):
                operator = AtomNode(operator)
            else:
                operator = AtomNode(str(operator))

        form_operands = []
        for item in evaluated[1:]:
            if isinstance(item, ASTNode):
                form_operands.append(item)
            elif isinstance(item, str):
                form_operands.append(StringNode(item))
            elif isinstance(item, int):
                form_operands.append(NumberNode(item))
            elif isinstance(item, list):
                # Convert list to nested structure
                for sub in item:
                    if isinstance(sub, ASTNode):
                        form_operands.append(sub)

        return FormNode(operator, form_operands, 0, 0)

    def _eval_gval(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate GVAL (get global value)."""
        if not operands:
            return None

        name_node = operands[0]
        if isinstance(name_node, AtomNode):
            name = name_node.value.upper()
            if name in env:
                return env[name]
            # Return as GlobalVarNode for runtime resolution
            return GlobalVarNode(name, 0, 0)

        return None

    def _eval_lval(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate LVAL (get local value)."""
        if not operands:
            return None

        name_node = operands[0]
        if isinstance(name_node, AtomNode):
            name = name_node.value.upper()
            if name in env:
                return env[name]

        return None

    def _eval_parse(self, operands: List[ASTNode], env: Dict[str, Any]) -> AtomNode:
        """Evaluate PARSE (parse string into atom)."""
        if not operands:
            return AtomNode("")

        val = self.evaluate(operands[0], env)

        if isinstance(val, str):
            return AtomNode(val)
        if isinstance(val, StringNode):
            return AtomNode(val.value)

        return AtomNode(str(val))

    def _eval_string(self, operands: List[ASTNode], env: Dict[str, Any]) -> str:
        """Evaluate STRING (concatenate into string)."""
        parts = []
        for op in operands:
            val = self.evaluate(op, env)
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, StringNode):
                parts.append(val.value)
            elif isinstance(val, AtomNode):
                parts.append(val.value)
            else:
                parts.append(str(val))
        return ''.join(parts)

    def _eval_assigned(self, operands: List[ASTNode], env: Dict[str, Any]) -> bool:
        """Evaluate ASSIGNED? (check if variable has a value).

        In macro context, this checks if an OPTIONAL parameter was provided.
        Returns True if the variable exists in the environment and has a non-None value.
        """
        if not operands:
            return False

        var_name = operands[0]
        if isinstance(var_name, AtomNode):
            name = var_name.value.upper()
        elif isinstance(var_name, LocalVarNode):
            name = var_name.name.upper()
        else:
            return False

        # Check if the variable exists in the environment and is not None
        if name in env:
            return env[name] is not None
        return False

    def _eval_eval(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate EVAL (compile-time evaluation).

        EVAL evaluates its argument at compile time. This is used in macros
        to create side effects like defining globals or constants.

        Example: <EVAL <FORM GLOBAL NEW-GLOBAL 123>>
        This creates a new global variable NEW-GLOBAL with value 123.
        """
        if not operands:
            return None

        # First, evaluate the argument to get the form to execute
        arg = self.evaluate(operands[0], env)

        # If the result is a FormNode, check if it's a definition form
        if isinstance(arg, FormNode) and isinstance(arg.operator, AtomNode):
            op_name = arg.operator.value.upper()

            if op_name == 'GLOBAL':
                # Create a global variable
                # <GLOBAL name value>
                if len(arg.operands) >= 1:
                    name_node = arg.operands[0]
                    if isinstance(name_node, AtomNode):
                        name = name_node.value.upper()
                        value = arg.operands[1] if len(arg.operands) > 1 else None
                        # Evaluate the value if it's an expression
                        if value is not None:
                            eval_value = self.evaluate(value, env)
                            if isinstance(eval_value, int):
                                value = NumberNode(eval_value)
                            elif isinstance(eval_value, ASTNode):
                                value = eval_value
                        # Create GlobalNode and add to pending list
                        global_node = GlobalNode(name, value)
                        self.macro_expander.pending_globals.append(global_node)
                        return None  # EVAL returns no value, side effect only

            elif op_name == 'CONSTANT':
                # Create a constant
                # <CONSTANT name value>
                if len(arg.operands) >= 2:
                    name_node = arg.operands[0]
                    if isinstance(name_node, AtomNode):
                        name = name_node.value.upper()
                        value = arg.operands[1]
                        # Evaluate the value
                        eval_value = self.evaluate(value, env)
                        if isinstance(eval_value, int):
                            value = NumberNode(eval_value)
                        elif isinstance(eval_value, ASTNode):
                            value = eval_value
                        # Create ConstantNode and add to pending list
                        const_node = ConstantNode(name, value)
                        self.macro_expander.pending_constants.append(const_node)
                        return None

        # For other forms, just evaluate and return result
        return arg

    def _eval_ifflag(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate IFFLAG (compile-time conditional based on flags).

        <IFFLAG (FLAG1 expr1) (FLAG2 expr2) ... (T default)>

        Checks each flag in order and returns the expression for the first
        truthy flag. Supports special flags like IN-ZILCH.

        Example: <IFFLAG (IN-ZILCH PRINTI) (T PRINC)>
        Returns PRINTI if in Z-machine context, PRINC otherwise.
        """
        for clause in operands:
            # Handle both FormNode and list representations
            # (FLAG EXPR) can be parsed as either a FormNode or a list [FLAG, EXPR]
            if isinstance(clause, FormNode):
                if len(clause.operands) < 1:
                    continue
                flag_node = clause.operator
                expr = clause.operands[0] if clause.operands else None
            elif isinstance(clause, list) and len(clause) >= 2:
                flag_node = clause[0]
                expr = clause[1]
            else:
                continue

            # Evaluate the flag
            flag_value = False
            if isinstance(flag_node, AtomNode):
                flag_name = flag_node.value.upper()
                if flag_name == 'T':
                    flag_value = True
                elif flag_name == 'ELSE':
                    flag_value = True
                elif flag_name == 'IN-ZILCH':
                    # Check the macro expander's in_zilch flag
                    flag_value = self.macro_expander.in_zilch
                elif flag_name in self.macro_expander.compilation_flags:
                    flag_value = self.macro_expander.compilation_flags[flag_name]
                else:
                    # Unknown flag - treat as false
                    flag_value = False

            if flag_value:
                # Return the expression for this clause
                if expr is not None:
                    return self.evaluate(expr, env)
                return None

        # No matching clause
        return None

    def _expand_quasiquote(self, node: ASTNode, env: Dict[str, Any]) -> Any:
        """Expand quasiquoted expression."""
        if isinstance(node, UnquoteNode):
            return self.evaluate(node.expr, env)

        if isinstance(node, FormNode):
            new_operands = []
            for op in [node.operator] + node.operands:
                if isinstance(op, SpliceUnquoteNode):
                    val = self.evaluate(op.expr, env)
                    if isinstance(val, list):
                        new_operands.extend(val)
                    else:
                        new_operands.append(val)
                else:
                    new_operands.append(self._expand_quasiquote(op, env))

            if new_operands:
                return FormNode(new_operands[0], new_operands[1:], node.line, node.column)
            return node

        return node

    def _is_truthy(self, val: Any) -> bool:
        """Check if a value is truthy in MDL terms."""
        if val is None:
            return False
        if val is False:
            return False
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return val != 0
        if isinstance(val, list):
            return len(val) > 0
        if isinstance(val, str):
            return len(val) > 0
        if isinstance(val, AtomNode):
            return val.value.upper() not in ('FALSE', '<>')
        return True


class MacroExpander:
    """Handles macro storage and expansion."""

    def __init__(self):
        self.macros: Dict[str, MacroNode] = {}
        self.mdl_evaluator = MDLEvaluator(self)
        # Globals created by EVAL during macro expansion
        self.pending_globals: List[GlobalNode] = []
        # Constants created by EVAL during macro expansion
        self.pending_constants: List[ConstantNode] = []
        # IN-ZILCH flag: True when expanding macros for Z-machine code generation,
        # False when expanding for compile-time execution
        self.in_zilch: bool = False
        # Compilation flags for IFFLAG evaluation
        self.compilation_flags: Dict[str, bool] = {}

    def define_macro(self, macro: MacroNode):
        """Store a macro definition."""
        self.macros[macro.name.upper()] = macro

    def is_macro(self, name: str) -> bool:
        """Check if a name is a defined macro."""
        return name.upper() in self.macros

    def _unwrap_quote(self, node: ASTNode) -> ASTNode:
        """Unwrap QUOTE forms - when a macro returns '<FORM>, the result is <FORM>.

        The quote means "return this form unevaluated", not "return a QUOTE form".
        """
        if isinstance(node, FormNode):
            if isinstance(node.operator, AtomNode) and node.operator.value.upper() == 'QUOTE':
                if node.operands:
                    return node.operands[0]
        return node

    def expand(self, form: FormNode) -> Optional[ASTNode]:
        """
        Expand a form if it's a macro call.

        Returns the expanded form, or None if not a macro.
        """
        # Check if the form operator is a macro
        if not isinstance(form.operator, AtomNode):
            return None

        macro_name = form.operator.value.upper()

        # Handle built-in conditional compilation macros
        if macro_name == 'IF-IN-ZILCH':
            # We're in a ZILF-compatible compiler, so return the argument
            if form.operands:
                return form.operands[0]
            return AtomNode("<>", form.line, form.column)

        if macro_name == 'IFN-IN-ZILCH':
            # We're in a ZILF-compatible compiler, so return empty
            return AtomNode("<>", form.line, form.column)

        if macro_name not in self.macros:
            return None

        macro = self.macros[macro_name]

        # Validate argument count
        num_args = len(form.operands)
        num_required = 0
        has_tuple = False
        for param in macro.params:
            # Handle both old 4-tuple and new 5-tuple formats
            if len(param) == 5:
                param_name, is_quoted, is_tuple, is_aux, is_optional = param
            else:
                param_name, is_quoted, is_tuple, is_aux = param
                is_optional = False
            if is_tuple:
                has_tuple = True
            elif not is_aux and not is_optional:
                num_required += 1

        if num_args < num_required:
            raise ValueError(
                f"Macro {macro_name} requires {num_required} argument(s), but got {num_args}"
            )

        # Build parameter bindings
        bindings = self._bind_parameters(macro, form.operands)

        # Expand the macro body with parameter substitution
        expanded = self._substitute(macro.body, bindings)

        # Evaluate MDL constructs (MAPF/FUNCTION, etc.) at compile time
        expanded = self._evaluate_mdl(expanded, bindings)

        # Handle list macro bodies (e.g., "(QUOTE <PRINT 'macro'>)")
        # In MDL, a list (FN arg1 arg2) is evaluated by applying FN to [arg1, arg2]
        # Common case: (QUOTE X) returns X unevaluated
        if isinstance(expanded, list) and len(expanded) >= 1:
            first = expanded[0]
            if isinstance(first, AtomNode):
                fn_name = first.value.upper()
                if fn_name == 'QUOTE' and len(expanded) >= 2:
                    # (QUOTE X) -> return X
                    return expanded[1]
                elif fn_name == 'CHTYPE' and len(expanded) >= 3:
                    # (CHTYPE value type) - handle SPLICE
                    value_node = expanded[1]
                    type_node = expanded[2]
                    if isinstance(type_node, AtomNode) and type_node.value.upper() == 'SPLICE':
                        # Return items for splicing
                        if isinstance(value_node, list):
                            items = [item for item in value_node if isinstance(item, ASTNode)]
                            return SpliceResultNode(items, 0, 0)
            # If first element is None or not a function, return last non-None value
            # This handles macro bodies with multiple expressions like:
            # <EVAL <FORM GLOBAL ...>> ',NEW-GLOBAL
            # where EVAL returns None and the quasiquote returns the value
            elif first is None or not isinstance(first, AtomNode):
                # Find last non-None expression value
                for item in reversed(expanded):
                    if item is not None:
                        # Unwrap QUOTE if needed
                        return self._unwrap_quote(item)
                return None

        # Unwrap QUOTE forms - when a macro returns '<FORM>, the result is <FORM>
        # The quote means "return this form unevaluated", not "return a QUOTE form"
        if isinstance(expanded, FormNode):
            if isinstance(expanded.operator, AtomNode) and expanded.operator.value.upper() == 'QUOTE':
                if expanded.operands:
                    return expanded.operands[0]

            # Handle CHTYPE ... SPLICE - returns a list to be spliced inline
            if isinstance(expanded.operator, AtomNode) and expanded.operator.value.upper() == 'CHTYPE':
                if len(expanded.operands) >= 2:
                    value_node = expanded.operands[0]
                    type_node = expanded.operands[1]
                    if isinstance(type_node, AtomNode) and type_node.value.upper() == 'SPLICE':
                        # Return the contents as a SpliceResultNode for inline expansion
                        # Value can be:
                        # - A quoted list '(<A> <B> <C>) -> QUOTE form
                        # - A raw list [<A>, <B>, <C>] -> from #SPLICE (...) syntax
                        if isinstance(value_node, list):
                            # Raw list from #SPLICE (...) syntax - filter for AST nodes
                            items = [item for item in value_node if isinstance(item, ASTNode)]
                            return SpliceResultNode(items, expanded.line, expanded.column)
                        elif isinstance(value_node, FormNode):
                            if isinstance(value_node.operator, AtomNode) and value_node.operator.value.upper() == 'QUOTE':
                                # Extract the list contents from the quoted form
                                if value_node.operands:
                                    quoted_content = value_node.operands[0]
                                    if isinstance(quoted_content, list):
                                        # Content is already a list of forms
                                        return SpliceResultNode(quoted_content, expanded.line, expanded.column)
                                    elif isinstance(quoted_content, FormNode):
                                        # Return a SpliceResultNode containing the list items
                                        items = [quoted_content.operator] + quoted_content.operands if quoted_content.operator else quoted_content.operands
                                        return SpliceResultNode(items, expanded.line, expanded.column)

        return expanded

    def _convert_result_to_ast(self, value: Any) -> ASTNode:
        """Convert a Python value to an AST node."""
        if isinstance(value, ASTNode):
            return value
        if isinstance(value, str):
            return StringNode(value, 0, 0)
        if isinstance(value, int):
            return NumberNode(value, 0, 0)
        if isinstance(value, bool):
            return AtomNode("T" if value else "<>", 0, 0)
        if value is None:
            return AtomNode("<>", 0, 0)
        # Fallback
        return AtomNode(str(value), 0, 0)

    def _bind_parameters(self, macro: MacroNode, args: List[ASTNode]) -> Dict[str, Any]:
        """
        Bind macro arguments to parameters.

        Returns a dictionary mapping parameter names to their values.
        """
        bindings = {}
        arg_index = 0

        for param in macro.params:
            # Handle both old 4-tuple and new 5-tuple formats
            if len(param) == 5:
                param_name, is_quoted, is_tuple, is_aux, is_optional = param
            else:
                param_name, is_quoted, is_tuple, is_aux = param
                is_optional = False

            if is_tuple:
                # Collect all remaining arguments
                bindings[param_name] = args[arg_index:]
                arg_index = len(args)
            elif is_aux:
                # AUX variables get default values (empty list for now)
                bindings[param_name] = FormNode(AtomNode("()"), [])
            elif is_optional:
                # Optional parameter
                if arg_index < len(args):
                    bindings[param_name] = args[arg_index]
                    arg_index += 1
                else:
                    # Missing optional argument - bind to None (unassigned)
                    bindings[param_name] = None
            else:
                # Regular required parameter
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

    def _evaluate_mdl(self, node: ASTNode, bindings: Dict[str, Any]) -> ASTNode:
        """
        Evaluate MDL constructs at compile time.

        Detects MAPF/MAPR with FUNCTION forms and evaluates them
        using the MDLEvaluator, converting the results back to AST nodes.
        Also handles COND with compile-time predicates like ASSIGNED?.
        """
        if isinstance(node, CondNode):
            # Evaluate COND at compile time if it contains ASSIGNED? or other
            # compile-time predicates
            result = self.mdl_evaluator.evaluate(node, bindings)
            if isinstance(result, ASTNode):
                return self._evaluate_mdl(result, bindings)
            return self._convert_to_ast(result)

        # Handle list of expressions (macro body with multiple statements)
        if isinstance(node, list):
            return [self._evaluate_mdl(item, bindings) for item in node]

        if not isinstance(node, FormNode):
            return node

        if not isinstance(node.operator, AtomNode):
            return node

        op_name = node.operator.value.upper()

        # Check for COND that might need compile-time evaluation
        if op_name == 'COND':
            # Evaluate COND at compile time using MDL evaluator
            result = self.mdl_evaluator.evaluate(node, bindings)
            if isinstance(result, ASTNode):
                return self._evaluate_mdl(result, bindings)
            return self._convert_to_ast(result)

        # Check for EVAL that needs compile-time evaluation
        if op_name == 'EVAL':
            # Evaluate EVAL at compile time using MDL evaluator
            result = self.mdl_evaluator.evaluate(node, bindings)
            if result is None:
                # EVAL returned None (side effect only, like defining a global)
                return None
            if isinstance(result, ASTNode):
                return self._evaluate_mdl(result, bindings)
            return self._convert_to_ast(result)

        # Check for IFFLAG that needs compile-time evaluation
        if op_name == 'IFFLAG':
            # Evaluate IFFLAG at compile time using MDL evaluator
            result = self.mdl_evaluator.evaluate(node, bindings)
            if result is None:
                return None
            if isinstance(result, ASTNode):
                return self._evaluate_mdl(result, bindings)
            return self._convert_to_ast(result)

        # Check for MAPF/MAPR that need compile-time evaluation
        if op_name in ('MAPF', 'MAPR'):
            # Check if there's a FUNCTION in the operands
            has_function = False
            for operand in node.operands:
                if isinstance(operand, FormNode):
                    if isinstance(operand.operator, AtomNode):
                        if operand.operator.value.upper() == 'FUNCTION':
                            has_function = True
                            break

            if has_function:
                # Evaluate with MDL evaluator
                result = self.mdl_evaluator.evaluate(node, bindings)
                return self._convert_to_ast(result)

        # Recursively process operands
        new_operands = []
        for operand in node.operands:
            new_operands.append(self._evaluate_mdl(operand, bindings))

        return FormNode(node.operator, new_operands, node.line, node.column)

    def _convert_to_ast(self, value: Any) -> ASTNode:
        """Convert MDL evaluation result back to AST nodes."""
        if isinstance(value, ASTNode):
            return value

        if isinstance(value, str):
            return StringNode(value, 0, 0)

        if isinstance(value, int):
            return NumberNode(value, 0, 0)

        if isinstance(value, bool):
            if value:
                return AtomNode("T", 0, 0)
            else:
                return AtomNode("<>", 0, 0)

        if isinstance(value, list):
            if not value:
                return FormNode(AtomNode("()", 0, 0), [], 0, 0)

            # Convert list to a PROG or sequence of statements
            # For MAPF ,LIST results, we want to construct a FORM
            converted = [self._convert_to_ast(item) for item in value]

            # If first element is an atom, treat as a form
            if converted and isinstance(converted[0], AtomNode):
                return FormNode(converted[0], converted[1:], 0, 0)

            # Otherwise return as a list-like structure
            # Wrap in PROGN to sequence multiple statements
            if len(converted) == 1:
                return converted[0]
            else:
                return FormNode(AtomNode("PROG", 0, 0), [
                    FormNode(AtomNode("()", 0, 0), [], 0, 0)  # Empty binding list
                ] + converted, 0, 0)

        if value is None:
            return AtomNode("<>", 0, 0)

        # Fallback
        return AtomNode(str(value), 0, 0)

    def _substitute(self, node: ASTNode, bindings: Dict[str, Any]) -> ASTNode:
        """
        Recursively substitute parameters in the macro body.

        Handles:
        - .VAR - parameter reference
        - !.VAR - splicing parameter (for lists)
        - <FORM ...> - construct new forms
        - `EXPR - quasiquote (template)
        - ~EXPR - unquote (evaluate and insert)
        - ~!EXPR - splice-unquote (evaluate and splice)
        """
        # Handle quasiquote: process as template
        if isinstance(node, QuasiquoteNode):
            return self._expand_quasiquote(node.expr, bindings)

        # Handle unquote outside of quasiquote: just substitute the expression
        if isinstance(node, UnquoteNode):
            return self._substitute(node.expr, bindings)

        # Handle splice-unquote outside of quasiquote: treat as regular substitution
        if isinstance(node, SpliceUnquoteNode):
            return self._substitute(node.expr, bindings)

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

                    # Handle SpliceUnquoteNode - evaluate and splice results
                    if isinstance(operand, SpliceUnquoteNode):
                        # Evaluate the inner expression using MDL evaluator
                        inner_form = operand.expr
                        result = self.mdl_evaluator.evaluate(inner_form, bindings)
                        # Splice the results
                        if isinstance(result, list):
                            for item in result:
                                if isinstance(item, ASTNode):
                                    new_operands.append(item)
                                else:
                                    # Convert non-AST results to nodes
                                    new_operands.append(self._convert_result_to_ast(item))
                        elif result is not None:
                            if isinstance(result, ASTNode):
                                new_operands.append(result)
                            else:
                                new_operands.append(self._convert_result_to_ast(result))
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

    def _expand_quasiquote(self, node: ASTNode, bindings: Dict[str, Any]) -> ASTNode:
        """
        Expand a quasiquoted expression.

        In a quasiquote context:
        - Most expressions are kept as literals (not substituted)
        - ~EXPR (UnquoteNode) - evaluate EXPR and insert its value
        - ~!EXPR (SpliceUnquoteNode) - evaluate EXPR and splice its elements

        This implements MDL/ZILF quasiquote semantics used for macro templates.
        """
        # Handle unquote: evaluate the expression with current bindings
        if isinstance(node, UnquoteNode):
            return self._substitute(node.expr, bindings)

        # Handle splice-unquote: this should be handled by the parent
        # Return a marker that the parent can detect and splice
        if isinstance(node, SpliceUnquoteNode):
            # Evaluate the expression
            result = self._substitute(node.expr, bindings)
            # Wrap in SpliceUnquoteNode so parent knows to splice
            return SpliceUnquoteNode(result, node.line, node.column)

        # Handle nested quasiquote: increment quoting depth
        if isinstance(node, QuasiquoteNode):
            # For now, just recursively process (simplified - full MDL has nested qq)
            inner = self._expand_quasiquote(node.expr, bindings)
            return QuasiquoteNode(inner, node.line, node.column)

        # Handle forms: recursively process operands, handling splicing
        if isinstance(node, FormNode):
            new_operator = self._expand_quasiquote(node.operator, bindings)
            new_operands = []

            for operand in node.operands:
                expanded = self._expand_quasiquote(operand, bindings)

                # Check if this is a splice-unquote result that needs splicing
                if isinstance(expanded, SpliceUnquoteNode):
                    # The inner expr has been evaluated, splice it
                    inner = expanded.expr
                    if isinstance(inner, list):
                        new_operands.extend([copy.deepcopy(v) for v in inner])
                    elif isinstance(inner, FormNode) and inner.operands:
                        # If result is a form, splice its operands
                        new_operands.extend([copy.deepcopy(v) for v in inner.operands])
                    else:
                        # Single value - just append
                        new_operands.append(copy.deepcopy(inner))
                else:
                    new_operands.append(expanded)

            return FormNode(new_operator, new_operands, node.line, node.column)

        # Handle lists (e.g., from parsing parenthesized expressions)
        if isinstance(node, list):
            new_items = []
            for item in node:
                expanded = self._expand_quasiquote(item, bindings)
                if isinstance(expanded, SpliceUnquoteNode):
                    inner = expanded.expr
                    if isinstance(inner, list):
                        new_items.extend([copy.deepcopy(v) for v in inner])
                    else:
                        new_items.append(copy.deepcopy(inner))
                else:
                    new_items.append(expanded)
            return new_items

        # Handle local variable references inside quasiquote
        # In quasiquote, .VAR is kept as-is (literal) unless unquoted
        if isinstance(node, LocalVarNode):
            return copy.deepcopy(node)

        # All other node types: keep as literals
        # (atoms, numbers, strings, global vars, etc.)
        return copy.deepcopy(node)

    def expand_all(self, program: Program) -> Program:
        """
        Expand all macros in a program.

        First, collect all macro definitions.
        Then, recursively expand all forms in routines, objects, etc.
        """
        # Register all macros
        for macro in program.macros:
            self.define_macro(macro)

        # Expand macros in routines (IN-ZILCH = true, generating Z-machine code)
        self.in_zilch = True
        for routine in program.routines:
            # Expand and flatten SpliceResultNodes
            new_body = []
            for stmt in routine.body:
                expanded = self._expand_recursive(stmt)
                if isinstance(expanded, SpliceResultNode):
                    # Inline the splice items
                    new_body.extend(expanded.items)
                else:
                    new_body.append(expanded)
            routine.body = new_body
            # Expand macros in local variable initializers
            for var_name, default_val in list(routine.local_defaults.items()):
                routine.local_defaults[var_name] = self._expand_recursive(default_val)

        # Expand macros in objects (IN-ZILCH = true, generating Z-machine code)
        for obj in program.objects:
            for key, value in obj.properties.items():
                if isinstance(value, ASTNode):
                    obj.properties[key] = self._expand_recursive(value)
                elif isinstance(value, list):
                    obj.properties[key] = [
                        self._expand_recursive(v) if isinstance(v, ASTNode) else v
                        for v in value
                    ]

        # Expand macros in rooms (IN-ZILCH = true, generating Z-machine code)
        for room in program.rooms:
            for key, value in room.properties.items():
                if isinstance(value, ASTNode):
                    room.properties[key] = self._expand_recursive(value)
                elif isinstance(value, list):
                    room.properties[key] = [
                        self._expand_recursive(v) if isinstance(v, ASTNode) else v
                        for v in value
                    ]

        # Expand macros in globals (IN-ZILCH = true, generating Z-machine code)
        for global_node in program.globals:
            if global_node.initial_value:
                global_node.initial_value = self._expand_recursive(global_node.initial_value)

        # Expand macros in constants (IN-ZILCH = true, generating Z-machine code)
        for const in program.constants:
            if const.value:
                const.value = self._expand_recursive(const.value)

        # Expand macros in TELL-TOKENS expansion bodies
        # This allows TELL tokens like MAC1 <PRINT-MAC-1> to work
        # where PRINT-MAC-1 is a macro that expands to <PRINT "macro">
        for token_name, token_def in program.tell_tokens.items():
            if token_def.expansion:
                # ASTNode is already imported at module level
                if isinstance(token_def.expansion, ASTNode):
                    token_def.expansion = self._expand_recursive(token_def.expansion)

        # Merge globals created by EVAL during macro expansion
        if self.pending_globals:
            # Check for duplicates and add new globals
            existing_names = {g.name for g in program.globals}
            for global_node in self.pending_globals:
                if global_node.name not in existing_names:
                    program.globals.append(global_node)
                    existing_names.add(global_node.name)

        # Merge constants created by EVAL during macro expansion
        if self.pending_constants:
            existing_names = {c.name for c in program.constants}
            for const_node in self.pending_constants:
                if const_node.name not in existing_names:
                    program.constants.append(const_node)
                    existing_names.add(const_node.name)

        return program

    # Operations handled natively by the code generator - don't expand these macros
    # These macros use MDL compile-time operations (MAPF, FUNCTION, etc.) that
    # we can't execute, so we rely on the code generator's built-in support
    # NOTE: TELL is now handled via MDL evaluation during macro expansion
    # NOTE: ASSIGNED? is now evaluated in macros to support OPTIONAL parameters
    NATIVE_OPERATIONS = frozenset({
        'PRINT', 'PRINTI', 'CRLF', 'PRINTN', 'PRINTD', 'PRINTC',
        'COND', 'REPEAT', 'PROG', 'BIND', 'DO', 'MAP', 'MAPF', 'MAPR',
        'VERB?', 'DLESS?', 'IGRTR?', 'EQUAL?', 'FSET?', 'IN?',
        'OBJECT', 'ROOM',  # Object/room definitions are handled by compiler
    })

    def _expand_recursive(self, node: ASTNode) -> ASTNode:
        """Recursively expand macros in an AST node."""
        if isinstance(node, FormNode):
            # Check if this is a native operation that we should NOT expand
            if isinstance(node.operator, AtomNode):
                op_name = node.operator.value.upper()
                if op_name in self.NATIVE_OPERATIONS:
                    # Don't expand this macro - just recursively process operands
                    new_operands = [self._expand_recursive(op) for op in node.operands]
                    return FormNode(node.operator, new_operands, node.line, node.column)

            # First, try to expand this form if it's a macro
            expanded = self.expand(node)
            if expanded is not None:
                # Macro was expanded, continue expanding recursively
                return self._expand_recursive(expanded)

            # Not a macro, recursively expand operands
            # Handle SpliceResultNode in operands by inlining their items
            new_operator = self._expand_recursive(node.operator)
            new_operands = []
            for op in node.operands:
                expanded = self._expand_recursive(op)
                if isinstance(expanded, SpliceResultNode):
                    # Inline the splice items as operands
                    new_operands.extend(expanded.items)
                else:
                    new_operands.append(expanded)
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

        elif isinstance(node, QuasiquoteNode):
            # Expand quasiquote contents
            new_expr = self._expand_recursive(node.expr)
            return QuasiquoteNode(new_expr, node.line, node.column)

        elif isinstance(node, UnquoteNode):
            # Expand unquote contents
            new_expr = self._expand_recursive(node.expr)
            return UnquoteNode(new_expr, node.line, node.column)

        elif isinstance(node, SpliceUnquoteNode):
            # Expand splice-unquote contents
            new_expr = self._expand_recursive(node.expr)
            return SpliceUnquoteNode(new_expr, node.line, node.column)

        # For other node types, return as-is
        return node
