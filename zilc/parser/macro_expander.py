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


class MdlReturn(Exception):
    """Compile-time <RETURN ...> escaping to the nearest evaluated REPEAT."""
    def __init__(self, value: Any):
        self.value = value


class MdlAgain(Exception):
    """Compile-time <AGAIN> restarting the nearest evaluated REPEAT."""
    pass


# Predicates that are meaningful at COMPILE time inside a macro expansion.
# A COND built entirely from these may be folded by _evaluate_mdl; anything
# else (FSET?, GETP, ...) is runtime and must reach codegen intact.
_CT_COND_OPS = {'ASSIGNED?', 'GASSIGNED?', 'TYPE?', 'NOT', 'AND', 'OR', 'EMPTY?',
                'LENGTH?', 'LENGTH', '==?', '=?', 'N==?', 'N=?', 'G?', 'L?',
                'G=?', 'L=?', '0?', '1?', 'SPNAME'}


_ZILCH_ENV_ASSIGNED = {'ZILCH', 'PREDGEN'}


def _char_literal_code(node):
    r"""ASCII code of a ZIL character-literal atom, or None.

    The lexer emits ZIL character constants (!\X, !X, \X) as ATOM tokens
    (e.g. <TELL !\  LN> -> AtomNode "!\ "), but in MDL a character constant
    has TYPE CHARACTER, not ATOM.  A game's own TELL DEFMAC dispatches on
    <TYPE? .E CHARACTER> vs <TYPE? .E ATOM> and calls <ASCII .E>; without
    this distinction the CHARACTER arm is never taken and every !\X in TELL
    is misread as a bare atom (moonmist's <TELL !\  LN> became
    <PRINT <GETP LN !\ >>).  Kept in lock-step with codegen's
    _parse_char_literal so both stages agree on what a character literal is.
    """
    if not isinstance(node, AtomNode):
        return None
    v = node.value
    _esc = {'n': 10, 't': 9, 'r': 13, '0': 0}
    # !\X  -- backslash-escaped character after !
    if v.startswith('!\\') and len(v) == 3:
        return _esc.get(v[2], ord(v[2]))
    # \X   -- backslash-escaped character (len 2 only; \,TELL etc. are atoms)
    if v.startswith('\\') and len(v) == 2:
        return _esc.get(v[1], ord(v[1]))
    # !X   -- single character after ! (len 2; bare ! and !</!,/!. splices differ)
    if v.startswith('!') and len(v) == 2 and v[1] not in '<,.':
        return ord(v[1])
    return None


def _gassigned_guarded_names(test_node):
    names = set()
    def walk(n):
        if isinstance(n, FormNode):
            if isinstance(n.operator, AtomNode) and \
               n.operator.value.upper() in ('GASSIGNED?', 'ASSIGNED?'):
                for op in n.operands:
                    if isinstance(op, AtomNode):
                        names.add(op.value.upper())
                    elif isinstance(op, (GlobalVarNode, LocalVarNode)):
                        names.add(op.name.upper())
            for op in n.operands:
                walk(op)
    walk(test_node)
    return names


def _ct_bound_names(bindings):
    """Names bound at MACRO-expansion time (DEFMAC params and "AUX" vars)."""
    try:
        return {str(_k).upper() for _k in (bindings or {}).keys()}
    except Exception:
        return set()


def _cond_is_compile_time_mdl(node, bound=None, ops=None, allow_quote=False,
                              ct_globals=None):
    _ops = ops if ops is not None else _CT_COND_OPS
    _ctg = ct_globals or ()
    def ok(n, guarded):
        if isinstance(n, LocalVarNode):
            # .X is a compile-time test ONLY when X is a binding of the macro
            # being expanded.  When it names a ROUTINE local the COND is a
            # RUNTIME test and folding it silently picks a branch: witness
            # TIME-PRINT's <TELL <COND (.AM "a.m.") (T "p.m.")>> collapsed to
            # <PRINT "p.m."> and the game never printed a.m. again.
            return bound is None or n.name.upper() in bound
        if isinstance(n, (NumberNode, StringNode)):
            return True
        if isinstance(n, AtomNode):
            return True
        if isinstance(n, GlobalVarNode):
            # ,X is compile-time when the same test GASSIGNED?-guards X (the
            # classic <AND <GASSIGNED? X> ,X> ZILCH-switch idiom) OR when X is a
            # known compile-time global (MDL-ZIL SETG20 switch, e.g. DEBUGGING?).
            _nm = n.name.upper()
            return _nm in guarded or _nm in _ctg
        if isinstance(n, FormNode):
            if not isinstance(n.operator, AtomNode):
                return False
            _opn = n.operator.value.upper()
            if allow_quote and _opn == 'QUOTE':
                return True     # a quoted expression is a constant
            if _opn not in _ops:
                return False
            return all(ok(op, guarded) for op in n.operands)
        return False
    for _c, _a in getattr(node, 'clauses', []):
        if not ok(_c, _gassigned_guarded_names(_c)):
            return False
    return True


# Extended op set for STATEFUL all-COND macro bodies (see
# _body_is_ct_cond_mdl): list accessors are pure and compile-time safe there.
_CT_COND_EXT_OPS = _CT_COND_OPS | {'REST', 'NTH'}


def _body_is_ct_cond_mdl(body, bound, ct_globals=None):
    """True when EVERY top-level form of a DEFMAC body is a COND whose every
    clause test is compile-time MDL over the macro's own bindings (and any
    known compile-time globals passed in ct_globals).

    Such bodies (lurkinghorror/moonmist's P?) are stateful -- early conds SET
    an "AUX" list that later conds read -- so the legacy pre-substitution
    expansion can never work: the body must be EVALUATED with a live
    environment.  The predicate is deliberately narrow (all-COND bodies,
    binding-only variables, pure list-accessor tests) so ordinary macros keep
    the legacy path."""
    items = body if isinstance(body, list) else [body]
    if not items:
        return False
    for it in items:
        clauses = None
        if isinstance(it, CondNode):
            clauses = it.clauses
        elif (isinstance(it, FormNode) and isinstance(it.operator, AtomNode)
              and it.operator.value.upper() == 'COND'):
            clauses = []
            for _op in it.operands:
                if (isinstance(_op, FormNode)
                        and isinstance(_op.operator, AtomNode)
                        and _op.operator.value == '()' and _op.operands):
                    clauses.append((_op.operands[0], list(_op.operands[1:])))
                else:
                    return False
        else:
            return False
        _shim = type('_CondShim', (), {'clauses': clauses})
        if not _cond_is_compile_time_mdl(_shim, bound, ops=_CT_COND_EXT_OPS,
                                         allow_quote=True, ct_globals=ct_globals):
            return False
    return True


def _body_writes_names(node, names):
    """True if any <SET nm ...> in ``node`` targets a name in ``names``."""
    if isinstance(node, FormNode):
        if (isinstance(node.operator, AtomNode)
                and node.operator.value.upper() == 'SET' and node.operands):
            tgt = node.operands[0]
            tn = getattr(tgt, 'value', getattr(tgt, 'name', None))
            if tn is not None and str(tn).upper() in names:
                return True
        return any(_body_writes_names(o, names) for o in node.operands)
    if isinstance(node, CondNode):
        for cond, acts in node.clauses:
            if _body_writes_names(cond, names):
                return True
            if any(_body_writes_names(a, names) for a in acts):
                return True
        return False
    if isinstance(node, RepeatNode):
        return any(_body_writes_names(i, names) for i in node.body)
    if hasattr(node, 'body') and isinstance(getattr(node, 'body'), list):
        return any(_body_writes_names(i, names) for i in node.body)
    if isinstance(node, list):
        return any(_body_writes_names(i, names) for i in node)
    return False


def _macro_computes_on_aux(macro):
    """True when a DEFMAC keeps compile-time state in its own "AUX" variables --
    i.e. it declares AUX vars and its body <SET>s at least one of them (e.g.
    scope.zil's MAP-SCOPE building INIT-STAGES, or WITH-GLOBAL building its
    binding lists).  Such macros must be MDL-EVALUATED, not substituted: the
    legacy substitution path leaves those compile-time <SET>s in the emitted
    body, where they leak as bogus routine locals (MATCH-NOUN-PHRASE overflowed
    past the 15-local limit).  Ordinary template macros have no AUX writes and
    keep the legacy path."""
    aux = set()
    for param in getattr(macro, 'params', ()):
        try:
            is_aux = param[3]
            pname = param[0]
        except (IndexError, TypeError):
            continue
        if is_aux:
            aux.add(str(pname).upper())
    if not aux:
        return False
    return _body_writes_names(macro.body, aux)


def _body_is_ct_list_setg(macro, ct_globals):
    """True when a DEFINE's body is <SETG X ...> and X is a compile-time LIST
    accumulator (present in ct_globals with a list value) -- the ZILF scope
    engine's <DEFINE SCOPE-STAGE ...>, which appends a <VECTOR ...> of quoted
    code onto ,SCOPE-STAGES.  Such a DEFINE must be MDL-EVALUATED, not
    substituted: the legacy path INLINES the quoted INIT-CODE/NEXT-CODE and then
    re-evaluates it, collapsing the nested <COND ...>/<BIND ...> to their first
    branch (VEHICLE's stage then never cleared SCOPE-STATE and MAP-SCOPE looped
    forever).  Evaluating keeps quoted params as references."""
    if not ct_globals:
        return False
    body = macro.body
    if isinstance(body, list):
        body = body[0] if len(body) == 1 else None
    if not isinstance(body, FormNode) or not isinstance(body.operator, AtomNode):
        return False
    if body.operator.value.upper() not in ('SETG', 'SETG20'):
        return False
    if not body.operands or not isinstance(body.operands[0], AtomNode):
        return False
    nm = body.operands[0].value.upper()
    return nm in ct_globals and isinstance(ct_globals[nm], list)


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
            # Fall back to compile-time globals (MDL-ZIL SETG20 switches like
            # DEBUGGING?); these persist across the whole expansion.
            _ct = getattr(self.macro_expander, 'ct_globals', None)
            if _ct is not None and name in _ct:
                return _ct[name]
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

        # Handle REPEAT nodes: real compile-time MDL loops (moonmist DOBJ?)
        if isinstance(node, RepeatNode):
            return self._eval_repeat_node(node, env)

        # Handle splice-unquote (!.VAR) - evaluate inner expr and return as SpliceResultNode
        # This is used in FORM constructors like <FORM EQUAL? ,X !.L>
        if isinstance(node, SpliceUnquoteNode):
            result = self.evaluate(node.expr, env)
            # Wrap in SpliceResultNode so FORM constructor knows to inline it
            if isinstance(result, list):
                return SpliceResultNode(result, node.line, node.column)
            elif result is None:
                return SpliceResultNode([], node.line, node.column)
            else:
                # Single value - still wrap as SpliceResultNode for consistency
                return SpliceResultNode([result], node.line, node.column)

        # Handle lists - inline SpliceResultNode items
        if isinstance(node, list):
            result = []
            for item in node:
                evaluated = self.evaluate(item, env)
                if isinstance(evaluated, SpliceResultNode):
                    # Inline the splice items
                    result.extend(evaluated.items)
                else:
                    result.append(evaluated)
            return result

        # Return other nodes as-is
        return node

    def _evaluate_form(self, form: FormNode, env: Dict[str, Any]) -> Any:
        """Evaluate a form (function call)."""
        _op = getattr(form, 'operator', None)
        if isinstance(_op, AtomNode) and _op.value.upper() == 'GASSIGNED?':
            # ZILCH/PREDGEN are parts of the ZILCH compiler environment and
            # always GASSIGNED when compiling a real game.
            if not form.operands:
                return False
            _t = form.operands[0]
            if isinstance(_t, AtomNode):
                _nm = _t.value.upper()
            elif isinstance(_t, (GlobalVarNode, LocalVarNode)):
                _nm = _t.name.upper()
            else:
                return False
            if _nm in _ZILCH_ENV_ASSIGNED:
                return True
            return _nm in env and env[_nm] is not None
        # Handle numeric operators as NTH: <1 .ARGS> means <NTH .ARGS 1>
        if isinstance(form.operator, NumberNode):
            index = form.operator.value
            if form.operands:
                list_val = self._as_mdl_list(self.evaluate(form.operands[0], env))
                if list_val is not None and 1 <= index <= len(list_val):
                    return list_val[index - 1]  # 1-indexed
            return None

        if not isinstance(form.operator, AtomNode):
            return form

        op_name = form.operator.value.upper()
        operands = form.operands

        # Root-oblist qualification: FOO!- is the atom FOO on the root oblist
        # (moonmist's <RETURN!- ...>).  Normalize for dispatch.
        if op_name.endswith('!-'):
            op_name = op_name[:-2]

        # Compile-time loop control -- honored only while a REPEAT evaluation
        # is active; elsewhere a (runtime) RETURN/AGAIN form is left as-is,
        # matching the old unknown-form behavior.
        if op_name in ('RETURN', 'AGAIN') and getattr(self, '_repeat_depth', 0) > 0:
            if op_name == 'AGAIN':
                raise MdlAgain()
            raise MdlReturn(self.evaluate(operands[0], env) if operands else True)

        if op_name == 'LENGTH?':
            return self._eval_length_p(operands, env)

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
        elif op_name == 'SETG' or op_name == 'SETG20':
            # SETG20 is the MDL-ZIL compile-time SETG (the "20" package): it names
            # a compile-time global used by the form/menu builders, never a
            # runtime Z-machine global.
            return self._eval_setg(operands, env)
        elif op_name == 'NTH':
            return self._eval_nth(operands, env)
        elif op_name == 'REST':
            return self._eval_rest(operands, env)
        elif op_name == 'PUTREST':
            return self._eval_putrest(operands, env)
        elif op_name == 'EMPTY?':
            return self._eval_empty(operands, env)
        elif op_name == 'LENGTH':
            return self._eval_length(operands, env)
        elif op_name == 'TYPE?':
            return self._eval_type(operands, env)
        elif op_name == 'SPNAME':
            return self._eval_spname(operands, env)
        elif op_name == 'ASCII':
            return self._eval_ascii(operands, env)
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
            # Evaluate operands and flatten any SpliceResultNodes
            result = []
            for op in operands:
                evaluated = self.evaluate(op, env)
                if isinstance(evaluated, SpliceResultNode):
                    result.extend(evaluated.items)
                else:
                    result.append(evaluated)
            return result
        elif op_name == 'CONS':
            # <CONS x list> -> a new MDL list with x prepended to list.
            # (scope.zil's MAP-SCOPE prepends the count PUT onto INIT-STAGES.)
            head = self.evaluate(operands[0], env) if operands else None
            rest = (self._as_mdl_list(self.evaluate(operands[1], env))
                    if len(operands) > 1 else None)
            if rest is None:
                rest = []
            items = ([]
                     if head is None and not operands
                     else (list(head.items)
                           if isinstance(head, SpliceResultNode)
                           else [head]))
            return items + list(rest)
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
        elif op_name == 'PRINC':
            return self._eval_princ(operands, env)
        elif op_name == 'PRIN1':
            return self._eval_prin1(operands, env)
        elif op_name == 'PRINT':
            return self._eval_print(operands, env)
        elif op_name == 'TERPRI':
            return self._eval_terpri(operands, env)
        elif op_name == 'CRLF':
            # CRLF in compile context prints newline
            print()
            return True
        elif op_name == 'BIND':
            # BIND is a scoping construct: <BIND (bindings) body...>
            # Evaluate the body expressions in order and return the last value
            return self._eval_bind(operands, env)
        elif op_name == 'PROG':
            # PROG is similar to BIND but with different control flow semantics
            return self._eval_bind(operands, env)
        elif op_name == 'CHTYPE':
            return self._eval_chtype(operands, env)

        # Arithmetic operators
        elif op_name == '+':
            return self._eval_add(operands, env)
        elif op_name == '-':
            return self._eval_sub(operands, env)
        elif op_name == '*':
            return self._eval_mul(operands, env)
        elif op_name == '/':
            return self._eval_div(operands, env)
        elif op_name == 'MOD':
            return self._eval_mod(operands, env)

        # Symbol table introspection
        elif op_name == 'ASSOCIATIONS':
            return self._eval_associations(operands, env)
        elif op_name == 'NEXT':
            return self._eval_next(operands, env)
        elif op_name == 'SORT':
            return self._eval_sort(operands, env)
        elif op_name == 'VECTOR':
            # VECTOR creates a vector from arguments (same as LIST for our purposes)
            return [self.evaluate(op, env) for op in operands]

        # Reader macro support
        elif op_name == 'MAKE-PREFIX-MACRO':
            return self._eval_make_prefix_macro(operands, env)
        elif op_name == 'VOC':
            # VOC creates a vocabulary word reference - return a placeholder form
            return self._eval_voc(operands, env)

        # List literal (a b c) -- the parser represents it as a form whose
        # operator is the atom "()".  Evaluate the elements into a real MDL
        # list (inlining !-splices) so <SET L (<PE ...> !.L)> builds lists.
        if op_name == '()':
            result = []
            for op in operands:
                evaluated = self.evaluate(op, env)
                if isinstance(evaluated, SpliceResultNode):
                    result.extend(evaluated.items)
                else:
                    result.append(evaluated)
            return result

        # User DEFINE / DEFMAC application (e.g. lurkinghorror's PE helper
        # inside the P? macro).  Bind evaluated args (raw AST for quoted
        # params), then evaluate the body forms in order; the last value is
        # the result.  Recursion is depth-capped; anything that fails falls
        # through to the unknown-form behavior.
        _macros = getattr(self.macro_expander, 'macros', None) or {}
        if (op_name in _macros and getattr(self, '_apply_depth', 0) < 16
                # The classic parser predicates are handled as codegen
                # builtins (see expand()'s skip list); leave their FORMS
                # for codegen rather than applying MULTIFROB here.
                and op_name not in ('VERB?', 'PRSO?', 'PRSI?', 'ROOM?',
                                    'HERE?', 'WINNER?', 'RARG?', 'CONTEXT?')):
            macro = _macros[op_name]
            try:
                self._apply_depth = getattr(self, '_apply_depth', 0) + 1
                new_env = {}
                arg_i = 0
                for param in macro.params:
                    if len(param) == 5:
                        p_name, p_quoted, p_tuple, p_aux, p_opt = param
                    else:
                        p_name, p_quoted, p_tuple, p_aux = param
                        p_opt = False
                    _defaults = getattr(macro, 'param_defaults', None) or {}
                    if p_tuple:
                        vals = []
                        while arg_i < len(operands):
                            v = operands[arg_i] if p_quoted else self.evaluate(operands[arg_i], env)
                            vals.append(v)
                            arg_i += 1
                        new_env[p_name.upper()] = vals
                    elif p_aux or (p_opt and arg_i >= len(operands)):
                        if p_name in _defaults:
                            # Defaults are EVALUATED at bind time with earlier
                            # bindings visible (MULTIFROB's (OO (OR)) (O .OO)).
                            new_env[p_name.upper()] = self.evaluate(
                                copy.deepcopy(_defaults[p_name]), new_env)
                        else:
                            new_env[p_name.upper()] = []
                    else:
                        if arg_i < len(operands):
                            v = operands[arg_i] if p_quoted else self.evaluate(operands[arg_i], env)
                            new_env[p_name.upper()] = v
                            arg_i += 1
                        else:
                            new_env[p_name.upper()] = None
                body = macro.body if isinstance(macro.body, list) else [macro.body]
                result = None
                for b in body:
                    result = self.evaluate(copy.deepcopy(b), new_env)
                return result
            finally:
                self._apply_depth -= 1

        # Unknown form - return as-is (will be processed at runtime)
        return form

    def _eval_length_p(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """<LENGTH? obj max>: the length if length <= max, else false."""
        if len(operands) < 2:
            return False
        val = self.evaluate(operands[0], env)
        mx = self.evaluate(operands[1], env)
        if isinstance(val, (list, str)):
            ln = len(val)
        elif val is None or val is False:
            ln = 0
        else:
            return False
        if isinstance(mx, int) and ln <= mx:
            return ln
        return False

    def _eval_repeat_node(self, node: 'RepeatNode', env: Dict[str, Any]) -> Any:
        """Evaluate a compile-time <REPEAT (bindings) body...> loop.

        Loops the body until a <RETURN ...> (MdlReturn) fires.  SETs on
        outer variables deliberately share `env` (MDL scoping: only the
        REPEAT's own binding list introduces new variables).  If the loop
        does not terminate within the iteration cap it is not compile-time
        MDL: the node is returned unchanged (legacy behavior).
        """
        if getattr(node, 'condition', None) is not None:
            return node
        loop_env = env
        if node.bindings:
            loop_env = dict(env)
            for _b in node.bindings:
                if isinstance(_b, tuple) and len(_b) == 2:
                    _vn, _init = _b
                else:
                    _vn, _init = _b, None
                if not isinstance(_vn, str):
                    return node  # expression binding: not compile-time
                loop_env[_vn.upper()] = (self.evaluate(_init, loop_env)
                                         if _init is not None else None)
        self._repeat_depth = getattr(self, '_repeat_depth', 0) + 1
        try:
            for _ in range(2000):
                try:
                    for stmt in node.body:
                        self.evaluate(stmt, loop_env)
                except MdlAgain:
                    continue
                except MdlReturn as _r:
                    return _r.value
        finally:
            self._repeat_depth -= 1
        return node

    def _eval_mapf(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """
        Evaluate MAPF (map and collect results).

        <MAPF collector function arg1 arg2 ...>

        Applies function to successive elements and collects results.
        """
        if len(operands) < 2:
            return []

        # MDL MAPF is <MAPF finalization loop-function structure...>: the loop
        # function runs per element and the finalization function is applied to
        # ALL collected results.  Capture the finalization operator's NAME so a
        # reducing finalization (,MAX / ,MIN / ,+ / ,*) folds the results down
        # to a scalar -- the scope engine sizes SCOPE-STATE with
        # <MAPF ,MAX 2 ,SCOPE-STAGES>.
        final_name = self._callable_name(operands[0])
        collector = self.evaluate(operands[0], env)
        func = self.evaluate(operands[1], env)

        # A fixnum loop-function is an NTH selector: <MAPF ,MAX 2 ,SCOPE-STAGES>
        # applies <2 stage> = <NTH stage 2> to each stage.
        nth_index = func if isinstance(func, int) else None

        def _apply(*call_args):
            if nth_index is not None:
                lst = self._as_mdl_list(call_args[-1])
                if lst is not None and 1 <= nth_index <= len(lst):
                    return lst[nth_index - 1]
                return None
            if callable(func):
                return func(*call_args)
            return call_args[-1]

        # Get iteration source(s)
        sources = [self.evaluate(op, env) for op in operands[2:]]

        # If no sources, the function generates its own data (like TELL macro)
        results = []

        if not sources:
            # Function is called repeatedly until MAPSTOP
            if callable(func):
                while True:
                    try:
                        result = _apply(env)
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
                        result = _apply(env, item)
                        if result is not None:
                            if isinstance(result, list):
                                results.extend(result)
                            else:
                                results.append(result)
                    except MapStop:
                        break
                    except MapRet as mr:
                        results.extend(mr.values)

        # Apply a reducing finalization function (,MAX / ,MIN / ,+ / ,*) over
        # the collected results.  LIST/VECTOR/TABLE finalizations (and <>) just
        # return the collected list, which is the default.
        reduced = self._reduce_mapf(final_name, results)
        if reduced is not None:
            return reduced
        return results

    @staticmethod
    def _callable_name(node) -> Optional[str]:
        """The atom NAME of a MAPF finalization operand (,MAX, <GVAL MAX>, MAX)."""
        if isinstance(node, GlobalVarNode):
            return node.name.upper()
        if isinstance(node, AtomNode):
            return node.value.upper()
        if (isinstance(node, FormNode) and isinstance(node.operator, AtomNode)
                and node.operator.value.upper() == 'GVAL' and node.operands
                and isinstance(node.operands[0], AtomNode)):
            return node.operands[0].value.upper()
        return None

    @staticmethod
    def _reduce_mapf(final_name, results):
        """Fold MAPF results with a reducing finalization function; returns None
        when the finalization is not a reducer (the caller keeps the list)."""
        if not final_name:
            return None
        def _as_int(v):
            if isinstance(v, bool):
                return None
            if isinstance(v, int):
                return v
            if isinstance(v, NumberNode):   # STATE-WORDS may arrive as an AST node
                return v.value
            return None
        nums = [x for x in (_as_int(r) for r in results) if x is not None]
        if final_name == 'MAX':
            return max(nums) if nums else 0
        if final_name == 'MIN':
            return min(nums) if nums else 0
        if final_name == '+':
            return sum(nums)
        if final_name == '*':
            out = 1
            for n in nums:
                out *= n
            return out
        return None

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
        or
        <FUNCTION ("AUX" (var1 init1) var2...) body...>
        """
        if not operands:
            return lambda e, *args: None

        # Parse parameter list
        param_spec = operands[0]
        body = operands[1:]

        params = []
        aux_vars = []  # List of (name, initializer_or_None) tuples
        in_aux = False

        # Handle both FormNode and list representations of parameter list
        param_items = []
        if isinstance(param_spec, FormNode):
            param_items = [param_spec.operator] + list(param_spec.operands)
        elif isinstance(param_spec, list):
            param_items = param_spec

        for p in param_items:
            if isinstance(p, AtomNode):
                name = p.value.upper()
                # Strip type annotation (W:ATOM -> W)
                if ':' in name:
                    name = name.split(':')[0]
                if name == '"AUX"' or name == 'AUX':
                    in_aux = True
                elif in_aux:
                    aux_vars.append((name, None))
                else:
                    params.append(name)
            elif isinstance(p, StringNode):
                if p.value.upper() == 'AUX':
                    in_aux = True
            elif isinstance(p, FormNode) and in_aux:
                # AUX variable with initializer: (VAR init-expr)
                # The operator is the var name, operands[0] is the initializer
                if isinstance(p.operator, AtomNode):
                    var_name = p.operator.value.upper()
                    initializer = p.operands[0] if p.operands else None
                    aux_vars.append((var_name, initializer))
            elif isinstance(p, list) and len(p) >= 1:
                if isinstance(p[0], StringNode) and p[0].value.upper() == 'AUX':
                    # ["AUX", ...] - skip AUX, process rest
                    in_aux = True
                elif in_aux and isinstance(p[0], AtomNode):
                    # [VAR init-expr] - AUX variable with initializer
                    var_name = p[0].value.upper()
                    initializer = p[1] if len(p) > 1 else None
                    aux_vars.append((var_name, initializer))

        evaluator = self
        # Capture reference to the outer environment for closure behavior
        # Note: We use the same dict object, not a copy, so changes are visible to caller
        captured_env = env

        def mdl_function(call_env: Dict[str, Any], *args) -> Any:
            """Execute the MDL function.

            Note: We use call_env directly which is passed by MAPF. The caller
            (MAPF) uses the same environment that contains captured variables
            like A from an enclosing PROG.
            """
            # Bind parameters directly in call_env
            for i, param in enumerate(params):
                if i < len(args):
                    call_env[param] = args[i]
                else:
                    call_env[param] = None

            # Initialize AUX variables (evaluate initializers with call_env)
            for var_name, initializer in aux_vars:
                if initializer is not None:
                    call_env[var_name] = evaluator.evaluate(initializer, call_env)
                elif var_name not in call_env:
                    call_env[var_name] = None

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
        # Persist top-level (compile-time) SETGs into the macro expander's
        # ct_globals so their value THREADS across successive top-level forms.
        # The ZILF scope engine relies on this: <SETG SCOPE-STAGES ()> then a
        # sequence of <SCOPE-STAGE ...> DEFINE calls each do
        # <SETG SCOPE-STAGES <LIST !,SCOPE-STAGES <VECTOR ...>>>, accumulating
        # into the compile-time list read later by ,SCOPE-STAGES.  Only persist
        # while evaluating top-level forms (in_zilch False), never while
        # generating runtime code inside routines (in_zilch True), and only for
        # concrete compile-time values (lists/scalars) so a bare unresolved
        # GlobalVarNode never shadows a real runtime global.
        me = self.macro_expander
        if me is not None and not getattr(me, 'in_zilch', True):
            ct = getattr(me, 'ct_globals', None)
            if ct is not None and isinstance(value, (list, int, str, bool)):
                ct[name] = value
        return value

    @staticmethod
    def _as_mdl_list(val) -> Optional[list]:
        """View an MDL primtype-LIST value as a Python list of elements.

        In MDL a FORM is primtype LIST: <NTH form 1> is its operator atom and
        <REST form> its operand list.  The mystery-trilogy TELL DEFMAC relies
        on this (`<==? <NTH .E 1> QUOTE>` to detect 'OBJ tokens); returning
        None for FormNodes sent every quoted atom down the wrong clause and
        printed stack garbage instead of the object's short name.
        """
        if isinstance(val, list):
            return val
        if isinstance(val, FormNode):
            # The empty-list literal () is represented as FormNode(Atom('()'), [])
            # -- its operator is a placeholder, not an element.
            if isinstance(val.operator, AtomNode) and val.operator.value == '()':
                return list(val.operands)
            return [val.operator] + list(val.operands)
        return None

    def _eval_nth(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate NTH (get nth element, 1-indexed)."""
        if len(operands) < 2:
            return None

        lst = self._as_mdl_list(self.evaluate(operands[0], env))
        n = self.evaluate(operands[1], env)

        if lst is not None and isinstance(n, int):
            idx = n - 1  # MDL is 1-indexed
            if 0 <= idx < len(lst):
                return lst[idx]

        return None

    def _eval_rest(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate REST (get tail of list)."""
        if not operands:
            return []

        lst = self._as_mdl_list(self.evaluate(operands[0], env))
        n = 1
        if len(operands) > 1:
            n = self.evaluate(operands[1], env)
            if not isinstance(n, int):
                n = 1

        if lst is not None:
            return lst[n:]

        return []

    def _eval_putrest(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate PUTREST (set tail of list).

        <PUTREST list new-tail> sets the rest (cdr) of list to new-tail.
        Returns the modified list.
        Used by MULTIFROB to build up OR/EQUAL? forms.
        """
        if len(operands) < 2:
            return []

        lst = self.evaluate(operands[0], env)
        new_tail = self.evaluate(operands[1], env)

        if isinstance(lst, list) and len(lst) > 0:
            # In MDL, PUTREST modifies lst[1:] to be new_tail
            # <PUTREST (a) (b c)> -> (a b c)
            if isinstance(new_tail, list):
                return [lst[0]] + new_tail
            else:
                return [lst[0], new_tail]

        return lst if isinstance(lst, list) else []

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
                # A ZIL character literal (!\X, !X, \X) is TYPE CHARACTER in
                # MDL, not ATOM -- a game TELL DEFMAC branches on exactly this.
                if _char_literal_code(val) is not None:
                    if type_name == 'CHARACTER':
                        return True
                    # falls through -- never matches ATOM/STRING/etc.
                    continue
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
                # In MDL, .STR reads as <LVAL STR> and ,X as <GVAL X> -- both
                # TYPE FORM (and a COND is a FORM too). starcross's 1982 TELL
                # DEFMAC sent .STR to its (ELSE <ERROR ...>) arm otherwise and
                # dropped the operand (every LDESC printed blank).
                if type_name == 'FORM' and isinstance(val, (FormNode, CondNode, LocalVarNode, GlobalVarNode)):
                    return True
                if type_name == 'LVAL' and isinstance(val, LocalVarNode):
                    return True
                if type_name == 'GVAL' and isinstance(val, GlobalVarNode):
                    return True
                if type_name == 'ROUTINE' and isinstance(val, RoutineNode):
                    return True
                if type_name == 'MACRO' and isinstance(val, MacroNode):
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

    def _eval_ascii(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        r"""Evaluate <ASCII x> at compile time.

        MDL's ASCII is bidirectional: <ASCII !\A> -> 65 and <ASCII 65> -> the
        character A.  In a TELL DEFMAC's CHARACTER arm it is only ever applied
        to a character constant to get its code (<PRINTC <ASCII .E>>), so a
        character literal or an existing number both resolve to the numeric
        code here; anything else is returned unchanged for runtime handling.
        """
        if not operands:
            return None
        val = self.evaluate(operands[0], env)
        code = _char_literal_code(val)
        if code is not None:
            return code
        if isinstance(val, int):
            return val
        if isinstance(val, NumberNode):
            return val.value
        return val

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

        # Atom comparison - compare by value
        if isinstance(val1, AtomNode) and isinstance(val2, AtomNode):
            return val1.value.upper() == val2.value.upper()

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
            # Handle SpliceResultNode - inline its items
            if isinstance(item, SpliceResultNode):
                for sub in item.items:
                    if isinstance(sub, ASTNode):
                        form_operands.append(sub)
                    elif isinstance(sub, str):
                        form_operands.append(StringNode(sub))
                    elif isinstance(sub, int):
                        form_operands.append(NumberNode(sub))
            elif isinstance(item, ASTNode):
                form_operands.append(item)
            elif isinstance(item, str):
                form_operands.append(StringNode(item))
            elif isinstance(item, int):
                form_operands.append(NumberNode(item))
            elif isinstance(item, list):
                # Convert list to a parenthesized form (list structure)
                # In ZIL, ((A B)) becomes a form with () operator
                # Empty list () also needs to be preserved for PROG/BIND bindings
                list_items = []
                for sub in item:
                    if isinstance(sub, ASTNode):
                        list_items.append(sub)
                    elif isinstance(sub, list):
                        # Nested list - recursively convert
                        nested_items = self._convert_list_to_form(sub)
                        list_items.append(nested_items)
                    elif isinstance(sub, str):
                        list_items.append(StringNode(sub))
                    elif isinstance(sub, int):
                        list_items.append(NumberNode(sub))
                # Always create the form - even for empty lists (important for PROG/BIND)
                form_operands.append(FormNode(AtomNode("()", 0, 0), list_items, 0, 0))

        # <FORM GVAL FOO> IS ',FOO and <FORM LVAL FOO> IS '.FOO (MDL).
        # Leaving them as FormNodes made every consumer treat them as nested
        # expressions to evaluate onto the stack -- and gen_gval emits NO code
        # for a name that is an object rather than a global, so the stack
        # value never existed (witness: <DOBJ? MONICA> -> `je PRSO,sp`, every
        # ASK/CONFRONT test false).  Normalizing also yields compact operands.
        if isinstance(operator, AtomNode) and len(form_operands) == 1:
            _opn = str(operator.value).upper()
            _arg = form_operands[0]
            if isinstance(_arg, AtomNode):
                if _opn == 'GVAL':
                    return GlobalVarNode(_arg.value, 0, 0)
                if _opn == 'LVAL':
                    return LocalVarNode(_arg.value, 0, 0)

        return FormNode(operator, form_operands, 0, 0)

    def _convert_list_to_form(self, lst: list) -> FormNode:
        """Convert a Python list to a FormNode with () operator."""
        items = []
        for item in lst:
            if isinstance(item, ASTNode):
                items.append(item)
            elif isinstance(item, list):
                items.append(self._convert_list_to_form(item))
            elif isinstance(item, str):
                items.append(StringNode(item))
            elif isinstance(item, int):
                items.append(NumberNode(item))
        return FormNode(AtomNode("()", 0, 0), items, 0, 0)

    def _eval_gval(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate GVAL (get global value)."""
        if not operands:
            return None

        name_node = operands[0]
        if isinstance(name_node, AtomNode):
            name = name_node.value.upper()
            if name in env:
                return env[name]
            # Fall back to compile-time globals (the scope engine's SCOPE-STAGES
            # accumulator etc.) so <GVAL X> folds identically to ,X.
            _ct = getattr(self.macro_expander, 'ct_globals', None)
            if _ct is not None and name in _ct:
                return _ct[name]
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

    def _eval_chtype(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate CHTYPE (change type).

        CHTYPE converts a value to a different type.

        Examples:
        - <CHTYPE (TABLE <VOC "FOO" PREP>) FORM> - converts list to form
        - <CHTYPE '(<A> <B>) SPLICE> - converts list for splicing

        For FORM type: converts a list (FN arg1 arg2...) to <FN arg1 arg2...>
        For SPLICE type: marks value for inline expansion
        """
        if len(operands) < 2:
            return None

        value = self.evaluate(operands[0], env)
        type_node = operands[1]

        if isinstance(type_node, AtomNode):
            type_name = type_node.value.upper()

            if type_name == 'FORM':
                # Convert list to form: (FN arg1 arg2) -> <FN arg1 arg2>
                if isinstance(value, list) and len(value) >= 1:
                    # First element is the operator
                    op = value[0]
                    args = value[1:] if len(value) > 1 else []
                    # Convert operator to AtomNode if needed
                    if isinstance(op, str):
                        op = AtomNode(op, 0, 0)
                    elif isinstance(op, AtomNode):
                        pass
                    else:
                        # Evaluate the operator
                        op = self.evaluate(op, env) if isinstance(op, ASTNode) else op
                        if isinstance(op, str):
                            op = AtomNode(op, 0, 0)
                    # Convert args to ASTNodes
                    ast_args = []
                    for arg in args:
                        if isinstance(arg, ASTNode):
                            ast_args.append(arg)
                        elif isinstance(arg, int):
                            ast_args.append(NumberNode(arg, 0, 0))
                        elif isinstance(arg, str):
                            ast_args.append(StringNode(arg, 0, 0))
                        else:
                            ast_args.append(arg)
                    return FormNode(op, ast_args, 0, 0)
                elif isinstance(value, FormNode):
                    # Already a form
                    return value

            elif type_name == 'SPLICE':
                # Mark for splicing
                if isinstance(value, list):
                    items = [item for item in value if isinstance(item, ASTNode)]
                    return SpliceResultNode(items, 0, 0)

            elif type_name == 'LIST':
                # Convert AssociationIterator to list [item, indicator, value]
                if isinstance(value, AssociationIterator):
                    return value.to_list()
                # Already a list
                if isinstance(value, list):
                    return value

        return value  # Return unchanged if type not recognized

    def _eval_add(self, operands: List[ASTNode], env: Dict[str, Any]) -> int:
        """Evaluate + (addition)."""
        result = 0
        for op in operands:
            val = self.evaluate(op, env)
            if isinstance(val, int):
                result += val
            elif isinstance(val, NumberNode):
                result += val.value
        return result

    def _eval_sub(self, operands: List[ASTNode], env: Dict[str, Any]) -> int:
        """Evaluate - (subtraction)."""
        if not operands:
            return 0
        first = self.evaluate(operands[0], env)
        if isinstance(first, NumberNode):
            first = first.value
        if not isinstance(first, int):
            first = 0
        if len(operands) == 1:
            return -first  # Unary minus
        result = first
        for op in operands[1:]:
            val = self.evaluate(op, env)
            if isinstance(val, int):
                result -= val
            elif isinstance(val, NumberNode):
                result -= val.value
        return result

    def _eval_mul(self, operands: List[ASTNode], env: Dict[str, Any]) -> int:
        """Evaluate * (multiplication)."""
        result = 1
        for op in operands:
            val = self.evaluate(op, env)
            if isinstance(val, int):
                result *= val
            elif isinstance(val, NumberNode):
                result *= val.value
        return result

    def _eval_div(self, operands: List[ASTNode], env: Dict[str, Any]) -> int:
        """Evaluate / (integer division)."""
        if len(operands) < 2:
            return 0
        first = self.evaluate(operands[0], env)
        if isinstance(first, NumberNode):
            first = first.value
        if not isinstance(first, int):
            return 0
        result = first
        for op in operands[1:]:
            val = self.evaluate(op, env)
            if isinstance(val, NumberNode):
                val = val.value
            if isinstance(val, int) and val != 0:
                result //= val
        return result

    def _eval_mod(self, operands: List[ASTNode], env: Dict[str, Any]) -> int:
        """Evaluate MOD (modulo)."""
        if len(operands) < 2:
            return 0
        first = self.evaluate(operands[0], env)
        second = self.evaluate(operands[1], env)
        if isinstance(first, NumberNode):
            first = first.value
        if isinstance(second, NumberNode):
            second = second.value
        if isinstance(first, int) and isinstance(second, int) and second != 0:
            return first % second
        return 0

    def _eval_associations(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate ASSOCIATIONS - return iterator over symbol table.

        Returns an AssociationIterator containing all known symbols:
        - Routines with indicator ZVAL
        - Globals with indicator GVAL
        - Macros with indicator DECL

        Used by PRE-COMPILE hooks to introspect the compilation environment.
        """
        # Get the symbol table from the macro expander
        associations = []

        # Add routines (indicator = ZVAL, value = actual RoutineNode for TYPE? check)
        if hasattr(self.macro_expander, 'program') and self.macro_expander.program:
            program = self.macro_expander.program
            for routine in program.routines:
                # Create atom for routine name
                name_atom = AtomNode(routine.name, 0, 0)
                # Indicator is ZVAL for routine values
                indicator = AtomNode('ZVAL', 0, 0)
                # Value is the actual RoutineNode so TYPE? ROUTINE works
                associations.append((name_atom, indicator, routine))

            # Add macros (indicator = DECL)
            for macro_name in self.macro_expander.macros:
                name_atom = AtomNode(macro_name, 0, 0)
                indicator = AtomNode('DECL', 0, 0)
                value = AtomNode('MACRO', 0, 0)
                associations.append((name_atom, indicator, value))

        return AssociationIterator(associations)

    def _eval_next(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate NEXT - advance association iterator.

        <NEXT assoc> returns the next association or false if exhausted.
        """
        if not operands:
            return None

        val = self.evaluate(operands[0], env)
        if isinstance(val, AssociationIterator):
            return val.next()
        return None

    def _eval_sort(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate SORT - sort a list/vector.

        <SORT comparator sequence> sorts sequence.
        If comparator is <> (false), uses default alphabetic comparison.
        """
        if len(operands) < 2:
            return []

        comparator = self.evaluate(operands[0], env)
        sequence = self.evaluate(operands[1], env)

        if not isinstance(sequence, list):
            return sequence

        # Extract sortable values
        def get_sort_key(item):
            if isinstance(item, AtomNode):
                return item.value.upper()
            elif isinstance(item, str):
                return item.upper()
            elif isinstance(item, NumberNode):
                return item.value
            elif isinstance(item, int):
                return item
            return str(item)

        # Sort using default alphabetic comparison (comparator <> means default)
        try:
            return sorted(sequence, key=get_sort_key)
        except Exception:
            return sequence

    def _eval_make_prefix_macro(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        r"""Evaluate MAKE-PREFIX-MACRO - register a reader prefix macro.

        <MAKE-PREFIX-MACRO !\@ <FUNCTION (W:ATOM) <VOC <SPNAME .W> BUZZ>>>

        Registers a prefix character that transforms following atoms.
        """
        if len(operands) < 2:
            return None

        # Get the prefix character from the first operand
        # It should be an atom like !\@ (which is the @ character escaped)
        prefix_arg = operands[0]
        if isinstance(prefix_arg, AtomNode):
            # Handle escaped characters like !\@ -> @
            prefix_char = prefix_arg.value
            if prefix_char.startswith('!\\'):
                prefix_char = prefix_char[2:]  # Strip !\
            elif prefix_char.startswith('\\'):
                prefix_char = prefix_char[1:]  # Strip \
        else:
            return None

        # Get the handler function
        handler = self.evaluate(operands[1], env)

        # Store the prefix macro in the expander
        if self.macro_expander:
            self.macro_expander.prefix_macros[prefix_char] = handler

        return True

    def _eval_voc(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate VOC - create a vocabulary word reference.

        <VOC "HELLO" BUZZ> creates a reference to the vocabulary word "hello".
        This is used by prefix macros to create vocabulary references.
        Returns a FormNode that will be processed during compilation.
        """
        # Evaluate operands and convert results to ASTNodes
        evaluated_operands = []
        for op in operands:
            val = self.evaluate(op, env)
            if isinstance(val, str):
                # Convert string result (e.g., from SPNAME) to StringNode
                evaluated_operands.append(StringNode(val, 0, 0))
            elif isinstance(val, ASTNode):
                evaluated_operands.append(val)
            else:
                evaluated_operands.append(op)

        # Return as a form for later processing by compiler
        return FormNode(
            AtomNode('VOC', 0, 0),
            evaluated_operands,
            0, 0
        )

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

            elif op_name == 'ROUTINE':
                # Create a routine dynamically:
                # <ROUTINE name [activation] (params) body...>
                routine_node = self.macro_expander._routine_from_form_operands(
                    arg.operands, arg.line, arg.column)
                if routine_node is not None:
                    self.macro_expander.pending_routines.append(routine_node)
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

    def _eval_princ(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate PRINC - print without quotes at compile time."""
        if operands:
            val = self.evaluate(operands[0], env)
            if isinstance(val, str):
                print(val, end='')
            elif isinstance(val, StringNode):
                print(val.value, end='')
            elif val is not None:
                print(str(val), end='')
            return val
        return None

    def _eval_prin1(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate PRIN1 - print with quotes at compile time."""
        if operands:
            val = self.evaluate(operands[0], env)
            if isinstance(val, str):
                print(f'"{val}"', end='')
            elif isinstance(val, StringNode):
                print(f'"{val.value}"', end='')
            elif val is not None:
                print(repr(val), end='')
            return val
        return None

    def _eval_print(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate PRINT - print with newline at compile time."""
        if operands:
            val = self.evaluate(operands[0], env)
            if isinstance(val, str):
                print(val)
            elif isinstance(val, StringNode):
                print(val.value)
            elif val is not None:
                print(str(val))
            return val
        return None

    def _eval_terpri(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate TERPRI - print newline at compile time."""
        print()
        return True

    def _eval_bind(self, operands: List[ASTNode], env: Dict[str, Any]) -> Any:
        """Evaluate BIND/PROG - execute body in a new scope.

        <PROG ((VAR1 init1) (VAR2 init2) ...) body...>
        <BIND ((VAR1 init1) ...) body...>
        """
        if not operands:
            return None

        # First operand is the binding list (which can be empty)
        # Remaining operands are the body expressions
        binding_list = operands[0] if operands else None
        body = operands[1:] if len(operands) > 1 else []

        # BIND/PROG rebinds ONLY its declared atoms.  A <SET OTHER ...> in the
        # body must affect the ENCLOSING binding (MDL scoping).  The old code
        # ran the body in a COPY of env, so a nested <SET OUTER ...> was silently
        # dropped -- the scope engine's default-stages branch builds its
        # INIT-STAGES list inside <BIND ((I 0)) <SET INIT-STAGES <MAPF ...>>>,
        # and losing that SET left SCOPE-CURRENT-STAGES empty (every command
        # then said "You don't see that here").  Use the shared env and
        # save/restore just the declared vars around the body.
        declared_saved = []  # (name, had_before, old_value)

        def _bind_one(var_name, init_node, has_init):
            declared_saved.append((var_name, var_name in env, env.get(var_name)))
            env[var_name] = self.evaluate(init_node, env) if has_init else None

        if binding_list:
            bindings_to_process = []
            if isinstance(binding_list, FormNode):
                # Bindings are in the form: ((VAR1 init1) (VAR2 init2) ...)
                bindings_to_process = [binding_list.operator] + list(binding_list.operands)
            elif isinstance(binding_list, list):
                bindings_to_process = binding_list

            for binding in bindings_to_process:
                if isinstance(binding, FormNode):
                    # (VAR init-expr) - operator is var name, operand is initializer
                    if isinstance(binding.operator, AtomNode) and binding.operator.value != '()':
                        _bind_one(binding.operator.value.upper(),
                                  binding.operands[0] if binding.operands else None,
                                  bool(binding.operands))
                elif isinstance(binding, list) and len(binding) >= 1:
                    # [VAR init-expr] list form
                    if isinstance(binding[0], AtomNode):
                        _bind_one(binding[0].value.upper(),
                                  binding[1] if len(binding) > 1 else None,
                                  len(binding) > 1)
                elif isinstance(binding, AtomNode) and binding.value != '()':
                    # Just a variable name with no initializer
                    _bind_one(binding.value.upper(), None, False)

        # Execute body expressions in order, return last value
        try:
            result = None
            for expr in body:
                result = self.evaluate(expr, env)
            return result
        finally:
            # Restore the declared vars (unwind the BIND scope), preserving any
            # body mutation of enclosing variables.
            for var_name, had_before, old_value in reversed(declared_saved):
                if had_before:
                    env[var_name] = old_value
                else:
                    env.pop(var_name, None)

    @staticmethod
    def _qq_leaf(val):
        """A quasiquote form operand must be an AST node.  Raw Python scalars
        produced by unquote -- a fixnum counter ~.I, a <LENGTH ...> result --
        would otherwise reach codegen as a bare int and be mis-encoded (the
        scope engine's <PUT ,SCOPE-CURRENT-STAGES ~.I ...> all collapsed to
        index 0).  Only lift the scalar cases; leave AST/str/list untouched so
        no other quasiquote shifts."""
        if isinstance(val, bool):
            return AtomNode('T' if val else '<>', 0, 0)
        if isinstance(val, int):
            return NumberNode(val, 0, 0)
        return val

    def _expand_quasiquote_seq(self, items, env):
        """Expand a sequence of quasiquote items, splicing ~!.X (SpliceUnquote)
        elements.  Shared by the FormNode-operand and COND-clause-list paths."""
        out = []
        for op in items:
            if isinstance(op, SpliceUnquoteNode):
                val = self.evaluate(op.expr, env)
                if isinstance(val, list):
                    out.extend(self._qq_leaf(v) for v in val)
                else:
                    out.append(self._qq_leaf(val))
            else:
                out.append(self._qq_leaf(self._expand_quasiquote(op, env)))
        return out

    def _expand_quasiquote(self, node: ASTNode, env: Dict[str, Any]) -> Any:
        """Expand quasiquoted expression."""
        if isinstance(node, UnquoteNode):
            return self.evaluate(node.expr, env)

        if isinstance(node, FormNode):
            new_operands = self._expand_quasiquote_seq(
                [node.operator] + node.operands, env)
            if new_operands:
                return FormNode(new_operands[0], new_operands[1:], node.line, node.column)
            return node

        # A COND clause inside a quasiquoted <ROUTINE ...> template arrives as a
        # Python list [condition ~!.BODY]; without recursing here the ~!.BODY
        # SpliceUnquote never expanded and the scope-stage routines' clauses ran
        # empty (SCOPE-CRAWL was never emitted, so scope yielded no objects).
        if isinstance(node, list):
            return self._expand_quasiquote_seq(node, env)

        if isinstance(node, CondNode):
            new_clauses = []
            for cond, actions in node.clauses:
                new_cond = self._qq_leaf(self._expand_quasiquote(cond, env))
                new_actions = self._expand_quasiquote_seq(actions, env)
                new_clauses.append((new_cond, new_actions))
            return CondNode(new_clauses, node.line, node.column)

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
        if isinstance(val, FormNode):
            # A bare <> (or ()) literal is MDL FALSE. hollywood's PSEUDO
            # tuples use <> for "no adjective": <COND (<NTH .OBJ 1> ...)>
            # must NOT take the clause, else SPNAME of FALSE fabricates an
            # empty-string VOC entry instead of a 0 element.
            if (isinstance(val.operator, AtomNode)
                    and val.operator.value in ('<>', '()')
                    and not val.operands):
                return False
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
        # Routines created by EVAL during macro expansion (e.g., PRE-COMPILE hooks)
        self.pending_routines: List[RoutineNode] = []
        # IN-ZILCH flag: True when expanding macros for Z-machine code generation,
        # False when expanding for compile-time execution
        self.in_zilch: bool = False
        # Compilation flags for IFFLAG evaluation
        self.compilation_flags: Dict[str, bool] = {}
        # Reference to the program being expanded (for ASSOCIATIONS introspection)
        self.program: Optional['Program'] = None
        # Prefix macros registered via MAKE-PREFIX-MACRO (char -> function)
        self.prefix_macros: Dict[str, Any] = {}
        # Compile-time globals defined by the MDL-ZIL <SETG20 ...> idiom (e.g.
        # DEBUGGING?). Referenced as ,NAME inside macro CONDs; they let the
        # form/debug-gating macros fold at expansion time instead of leaking
        # compile-time-only ops (ASSIGNED?, EMPTY?) into Z-code.  name -> value.
        self.ct_globals: Dict[str, Any] = {}

    def define_macro(self, macro: MacroNode):
        """Store a macro definition."""
        self.macros[macro.name.upper()] = macro

    def is_macro(self, name: str) -> bool:
        """Check if a name is a defined macro."""
        return name.upper() in self.macros

    def _call_propspec_handler(self, handler_name: str, prop_value, program: 'Program'):
        """
        Call a PROPSPEC handler function with property values.

        PROPSPEC handlers are DEFINE functions that transform property values.
        They take a single argument (the property value list) and return a list:
        - Element 0: default value (often <>)
        - Element 1: actual property value (e.g., TABLE, routine reference)

        Returns the transformed property value, or None if handler failed.
        """
        handler = self.macros.get(handler_name.upper())
        if not handler:
            return None

        # Build the argument list for the handler
        # Wrap property value in a list if it's not already
        if isinstance(prop_value, list):
            value_list = prop_value
        elif isinstance(prop_value, ASTNode):
            value_list = [prop_value]
        else:
            value_list = [AtomNode(str(prop_value), 0, 0)]

        # Create a quoted list of property values for the L parameter
        # The handler receives the property values as a list
        value_nodes = []
        for v in value_list:
            if isinstance(v, ASTNode):
                value_nodes.append(v)
            else:
                value_nodes.append(AtomNode(str(v), 0, 0))

        # Build bindings for the handler parameter (typically "L")
        bindings = {}
        if handler.params:
            # Get the first parameter name (typically "L")
            param = handler.params[0]
            if len(param) >= 1:
                param_name = param[0].upper()
                bindings[param_name] = value_nodes

        # Expand the handler body with parameter substitution
        expanded = self._substitute(copy.deepcopy(handler.body), bindings)

        # Evaluate MDL constructs
        expanded = self._evaluate_mdl(expanded, bindings)

        # The handler should return a list where:
        # - Element 0 is the default value (often <>)
        # - Element 1+ is the actual property value
        #
        # The expanded result is the handler body, which may be:
        # - A list of statements (e.g., [ROUTINE-side-effect, return-value-list])
        # - The last statement is the actual return value (a list like (<> PROP-ROUTINE))

        # Find the last non-None element (the actual return value)
        return_value = None
        if isinstance(expanded, list):
            for item in reversed(expanded):
                if item is not None:
                    return_value = item
                    break
        else:
            return_value = expanded

        # The return value should be a list: (<> PROP-ROUTINE)
        # Extract element 1 (the actual property value)
        if isinstance(return_value, list) and len(return_value) >= 2:
            result = return_value[1]
            if isinstance(result, ASTNode):
                result = self._expand_recursive(result)
            return result
        elif isinstance(return_value, list) and len(return_value) == 1:
            result = return_value[0]
            if isinstance(result, ASTNode):
                result = self._expand_recursive(result)
            return result
        elif isinstance(return_value, ASTNode):
            return self._expand_recursive(return_value)

        return None

    def _execute_pre_compile_hook(self, hook: MacroNode, program: Program) -> None:
        """
        Execute PRE-COMPILE hook function.

        The PRE-COMPILE hook is called before macro expansion and can:
        - Introspect the compilation environment via ASSOCIATIONS
        - Create new routines, globals, or constants via EVAL
        - Perform compile-time side effects

        The hook takes no arguments (or has AUX parameters only).
        """
        # Build environment with no arguments (hook uses AUX for local vars)
        env = {}

        # Get AUX parameter defaults
        for param in hook.params:
            if len(param) >= 4:
                param_name = param[0].upper()
                is_aux = param[3]
                if is_aux:
                    # AUX parameter - check for default value
                    # Default value would be in a different format, skip for now
                    env[param_name] = None

        # Evaluate the hook body
        result = None
        if isinstance(hook.body, list):
            for stmt in hook.body:
                result = self.mdl_evaluator.evaluate(stmt, env)
        else:
            result = self.mdl_evaluator.evaluate(hook.body, env)

        # Note: side effects (routine creation via EVAL) are handled by
        # pending_routines, pending_globals, pending_constants

    def _apply_routine_rewriter(self, program: Program, rewriter: MacroNode) -> Program:
        """
        Apply ROUTINE-REWRITER hook to all routines in the program.

        The rewriter function is called with (NAME ARGS BODY) where:
        - NAME: routine name as an atom
        - ARGS: list of parameter names as atoms
        - BODY: list of body expressions

        If the rewriter returns a list, it's interpreted as [new_args, *new_body].
        If it returns FALSE/None, the routine is unchanged.
        """
        for routine in program.routines:
            # Create arguments for the rewriter: (NAME ARGS BODY)
            name_atom = AtomNode(routine.name, 0, 0)

            # Create a quoted list of parameter atoms
            param_atoms = [AtomNode(p, 0, 0) for p in routine.params]
            # In MDL, we represent this as a quoted form: '(arg1 arg2 ...)
            args_list = FormNode(
                AtomNode('QUOTE', 0, 0),
                [param_atoms] if param_atoms else [[]],
                0, 0
            )

            # Create a quoted list of body expressions
            # Use quasiquote-like representation: '(<expr1> <expr2> ...)
            body_list = FormNode(
                AtomNode('QUOTE', 0, 0),
                [routine.body] if routine.body else [[]],
                0, 0
            )

            # Build bindings for the rewriter parameters
            # Rewriter takes (NAME ARGS BODY) so bind these to first 3 params
            bindings = {}
            rewriter_params = []
            for param in rewriter.params:
                if len(param) >= 4:
                    param_name = param[0].upper()
                    is_aux = param[3]
                    if not is_aux:
                        rewriter_params.append(param_name)

            # Bind arguments to parameters
            if len(rewriter_params) > 0:
                bindings[rewriter_params[0]] = name_atom  # NAME
            if len(rewriter_params) > 1:
                bindings[rewriter_params[1]] = param_atoms  # ARGS (as list)
            if len(rewriter_params) > 2:
                bindings[rewriter_params[2]] = routine.body  # BODY (as list)

            # Expand the rewriter body with these bindings
            try:
                # Substitute parameters in rewriter body
                expanded = self._substitute(rewriter.body, bindings)

                # Call MDL evaluator directly to get raw result (not converted to AST)
                result = self.mdl_evaluator.evaluate(expanded, bindings)

                # Process the result
                if result and result is not False:
                    # Result should be a list: [new_args, *new_body]
                    if isinstance(result, list) and len(result) >= 1:
                        # First element is the new args list
                        new_args = result[0]
                        new_body = result[1:] if len(result) > 1 else []

                        # Extract parameter names from new_args
                        if isinstance(new_args, list):
                            new_params = []
                            for arg in new_args:
                                if isinstance(arg, AtomNode):
                                    new_params.append(arg.value)
                                elif isinstance(arg, str):
                                    new_params.append(arg)
                            routine.params = new_params

                        # Update body
                        if new_body:
                            routine.body = new_body
            except Exception:
                # If rewriter fails, keep original routine
                pass

        return program

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

        # The classic-game parser predicates are DEFMACs built on MULTIFROB, a
        # DEFINE that needs real MDL list evaluation (REPEAT/PUTREST/CHTYPE) this
        # expander doesn't have. Expanding them here produced empty/garbage forms
        # -- <PRSI? ,PRSO> in minizork's V-PUT compiled to a bare branch byte and
        # the instruction stream desynced. The code generator has exact builtin
        # equivalents (gen_verb_test / gen_parser_eq_test), so leave these
        # unexpanded for it.
        if macro_name in ('VERB?', 'PRSO?', 'PRSI?', 'ROOM?', 'HERE?',
                          'WINNER?', 'RARG?', 'CONTEXT?'):
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

        # A DEFMAC whose body is a top-level MDL loop (moonmist's DOBJ?/IOBJ?
        # <REPEAT () ...>) is real compile-time MDL: evaluate it directly with
        # the MDL evaluator (env = bindings).  The legacy path below would
        # pre-substitute .VARs with their initial values, so the loop body
        # could never observe its own SETs and the RepeatNode leaked into
        # codegen (FORM/LENGTH?/RETURN!- emitted as routine calls).
        if (isinstance(macro.body, RepeatNode)
                or _body_is_ct_cond_mdl(
                    macro.body, _ct_bound_names(bindings), self.ct_globals)
                or _macro_computes_on_aux(macro)
                or _body_is_ct_list_setg(macro, self.ct_globals)):
            _env = {}
            _defaulted = getattr(self, '_last_defaulted_params', set())
            for _k, _v in bindings.items():
                _ku = str(_k).upper()
                if isinstance(_v, FormNode) and isinstance(_v.operator, AtomNode) \
                        and _v.operator.value == '()' and not _v.operands:
                    # "AUX" defaults arrive as the empty-list form (); the MDL
                    # evaluator needs real lists to build on.
                    _env[_ku] = []
                elif _ku in _defaulted and _v is not None:
                    # Declared defaults are EVALUATED at bind time, in
                    # declaration order with earlier bindings visible --
                    # MULTIFROB's "AUX" (OO (OR)) (O .OO) needs OO to be a
                    # real one-element list and O to alias it.
                    try:
                        _env[_ku] = self.mdl_evaluator.evaluate(
                            copy.deepcopy(_v), _env)
                    except Exception:
                        _env[_ku] = _v
                else:
                    _env[_ku] = _v
            try:
                _body_items = (macro.body if isinstance(macro.body, list)
                               else [macro.body])
                _res = None
                for _b in _body_items:
                    # Sequential evaluation with a SHARED env: earlier conds'
                    # SETs (P?'s list-building) are visible to later forms,
                    # and the LAST form's value is the expansion.
                    _res = self.mdl_evaluator.evaluate(copy.deepcopy(_b), _env)
            except Exception:
                _res = None
            if _res is not None and not isinstance(_res, RepeatNode):
                _res = self._convert_result_to_ast(_res)
                return self._unwrap_quote(_res)
            # else: fall through to the legacy path

        # Expand the macro body with parameter substitution
        # IMPORTANT: Use a deep copy to avoid mutating the original macro body
        # (the macro may be expanded multiple times with different in_zilch values)
        expanded = self._substitute(copy.deepcopy(macro.body), bindings)

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
        if isinstance(value, list):
            # Convert list to a parenthesized form (list structure)
            # Empty list () is represented as a FormNode with () operator
            list_items = []
            for item in value:
                if isinstance(item, ASTNode):
                    list_items.append(item)
                else:
                    list_items.append(self._convert_result_to_ast(item))
            return FormNode(AtomNode("()", 0, 0), list_items, 0, 0)
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
        # Names bound to their DECLARED DEFAULT (not a caller argument) this
        # call -- the direct-eval path evaluates those defaults with the MDL
        # evaluator (e.g. MULTIFROB's "AUX" (OO (OR)) must become a real
        # list), while caller arguments stay raw ASTs.
        self._last_defaulted_params = set()

        for param in macro.params:
            # Handle both old 4-tuple and new 5-tuple formats
            if len(param) == 5:
                param_name, is_quoted, is_tuple, is_aux, is_optional = param
            else:
                param_name, is_quoted, is_tuple, is_aux = param
                is_optional = False

            _defaults = getattr(macro, 'param_defaults', None) or {}
            if is_tuple:
                # Collect all remaining arguments
                bindings[param_name] = args[arg_index:]
                arg_index = len(args)
            elif is_aux:
                # AUX variables get their declared default (empty list if none)
                if param_name in _defaults:
                    bindings[param_name] = self._unwrap_quote(
                        copy.deepcopy(_defaults[param_name]))
                else:
                    bindings[param_name] = FormNode(AtomNode("()"), [])
                self._last_defaulted_params.add(param_name.upper())
            elif is_optional:
                # Optional parameter
                if arg_index < len(args):
                    bindings[param_name] = args[arg_index]
                    arg_index += 1
                elif param_name in _defaults:
                    # Missing optional argument - bind the declared default,
                    # unquoted per MDL binding semantics (lurkinghorror's
                    # <DEFMAC P? ('V "OPT" ('O '*) ...)> binds O to the atom *
                    # so <N==? .O '*> folds correctly).
                    bindings[param_name] = self._unwrap_quote(
                        copy.deepcopy(_defaults[param_name]))
                    self._last_defaulted_params.add(param_name.upper())
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

    def _maybe_fold_ct_constant(self, value):
        """Fold a <CONSTANT NAME <expr>> value to an integer literal when the
        expression is a compile-time reduction over a ct-globals list.

        The ZILF scope engine sizes its tables this way:
            <CONSTANT SCOPE-STATE-SIZE          <MAPF ,MAX 2 ,SCOPE-STAGES>>
            <CONSTANT SCOPE-CURRENT-STAGES-SIZE <LENGTH ,SCOPE-STAGES>>
        Only fold when the top operator is a known compile-time reducer and the
        result is a concrete int, so table/ITABLE/runtime constant values are
        left untouched."""
        if not isinstance(value, FormNode) or not isinstance(value.operator, AtomNode):
            return value
        op = value.operator.value.upper()
        if op not in ('LENGTH', 'MAPF', 'MAPR', 'NTH', '+', '-', '*', '/', 'MOD'):
            return value
        try:
            result = self.mdl_evaluator.evaluate(value, {})
        except Exception:
            return value
        if isinstance(result, bool) or not isinstance(result, int):
            return value
        return NumberNode(result, value.line, value.column)

    def _cond_form_to_node(self, node):
        """Recursively convert <COND ...> FormNodes (as produced by quasiquote
        expansion of a ROUTINE template) into real CondNodes.

        Codegen only applies its routine-tail value-context handling to a
        CondNode: a stage routine whose tail clause ends in a void <PUT ...>
        must RETURN TRUE (that is what tells MAP-SCOPE-START the stage is
        active), but a FormNode(COND) tail fell through to RET_POPPED / RFALSE,
        so every scope stage's init returned false and scope found nothing."""
        if isinstance(node, list):
            return [self._cond_form_to_node(x) for x in node]
        if isinstance(node, CondNode):
            return CondNode(
                [(self._cond_form_to_node(c), self._cond_form_to_node(a))
                 for c, a in node.clauses], node.line, node.column)
        if not isinstance(node, FormNode):
            return node
        if (isinstance(node.operator, AtomNode)
                and node.operator.value.upper() == 'COND'):
            clauses = []
            for cl in node.operands:
                items = None
                if isinstance(cl, list):
                    items = cl
                elif (isinstance(cl, FormNode)
                      and isinstance(cl.operator, AtomNode)
                      and cl.operator.value == '()'):
                    items = list(cl.operands)
                if not items:
                    continue
                cond = self._cond_form_to_node(items[0])
                acts = [self._cond_form_to_node(a) for a in items[1:]]
                clauses.append((cond, acts))
            return CondNode(clauses, node.line, node.column)
        return FormNode(node.operator,
                        [self._cond_form_to_node(o) for o in node.operands],
                        node.line, node.column)

    @staticmethod
    def _collect_binding_vars(blist, acc):
        items = None
        if (isinstance(blist, FormNode) and isinstance(blist.operator, AtomNode)
                and blist.operator.value == '()'):
            items = list(blist.operands)
        elif isinstance(blist, list):
            items = blist
        if not items:
            return
        for b in items:
            if isinstance(b, AtomNode) and b.value != '()':
                acc.append(b.value.upper().split(':')[0])
            elif (isinstance(b, FormNode) and isinstance(b.operator, AtomNode)
                  and b.operator.value != '()'):
                acc.append(b.operator.value.upper().split(':')[0])
            elif isinstance(b, list) and b and isinstance(b[0], AtomNode):
                acc.append(b[0].value.upper().split(':')[0])

    def _collect_local_vars(self, node, acc):
        """Collect BIND/PROG/REPEAT-introduced local variable names anywhere in a
        routine body.  The Z-machine has no dynamic locals -- every BIND/PROG
        binding shares the routine's fixed local slots -- so a routine built from
        an <EVAL <ROUTINE ...>> must declare them up front or the block's <.O>
        reads resolve to garbage (VEHICLE-SCOPE-STAGE's <BIND ((O ...)) ... .O>
        returned the constant 3, so scope looped)."""
        if isinstance(node, list):
            for x in node:
                self._collect_local_vars(x, acc)
            return
        if isinstance(node, CondNode):
            for c, a in node.clauses:
                self._collect_local_vars(c, acc)
                self._collect_local_vars(a, acc)
            return
        if isinstance(node, RepeatNode):
            self._collect_binding_vars(getattr(node, 'bindings', None), acc)
            self._collect_local_vars(node.body, acc)
            return
        if isinstance(node, FormNode):
            op = (node.operator.value.upper()
                  if isinstance(node.operator, AtomNode) else '')
            if op in ('BIND', 'PROG', 'REPEAT') and node.operands:
                self._collect_binding_vars(node.operands[0], acc)
                for o in node.operands[1:]:
                    self._collect_local_vars(o, acc)
            else:
                for o in node.operands:
                    self._collect_local_vars(o, acc)

    def _routine_from_form_operands(self, operands, line=0, column=0):
        """Build a RoutineNode from the operands of a (quasiquote-expanded)
        <ROUTINE name [activation] (params) body...> form.

        Handles the optional activation name between the routine name and the
        parameter list, and an "AUX"/"OPT" parameter list -- the ZILF scope
        engine emits <ROUTINE NAME-SCOPE-STAGE SCOPE-STAGE-ACTIVATION (INIT)
        <COND ...>> routines this way via <EVAL <ROUTINE ...>>.  The earlier
        hand-rolled parsing treated the activation atom as the parameter list
        and folded it (and the real params) into the body, so the generated
        scope-stage routines were malformed."""
        if not operands or not isinstance(operands[0], AtomNode):
            return None
        name = operands[0].value.upper()
        idx = 1
        activation = None
        # Optional activation name: a bare atom between the name and () params.
        if idx < len(operands) and isinstance(operands[idx], AtomNode):
            activation = operands[idx].value
            idx += 1
        params, aux_vars, opt_params, local_defaults = [], [], [], {}
        if activation:
            aux_vars.append(activation)
        # Parameter list: FormNode('()' ...) or a Python list of param items.
        if idx < len(operands):
            pnode = operands[idx]
            param_items = None
            if (isinstance(pnode, FormNode)
                    and isinstance(pnode.operator, AtomNode)
                    and pnode.operator.value == '()'):
                param_items = list(pnode.operands)
                idx += 1
            elif isinstance(pnode, list):
                param_items = list(pnode)
                idx += 1
            if param_items is not None:
                mode = 'req'
                for p in param_items:
                    if isinstance(p, StringNode):
                        m = p.value.upper()
                        if m == 'AUX':
                            mode = 'aux'
                        elif m in ('OPT', 'OPTIONAL'):
                            mode = 'opt'
                        continue
                    nm_node = dflt = None
                    if isinstance(p, AtomNode):
                        nm_node = p
                    elif isinstance(p, FormNode):
                        nm_node = p.operator
                        dflt = p.operands[0] if p.operands else None
                    elif isinstance(p, list) and p:
                        nm_node = p[0]
                        dflt = p[1] if len(p) > 1 else None
                    if isinstance(nm_node, AtomNode):
                        nm = nm_node.value.upper().split(':')[0]
                        if mode == 'aux':
                            aux_vars.append(nm)
                        elif mode == 'opt':
                            opt_params.append(nm)
                            aux_vars.append(nm)
                        else:
                            params.append(nm)
                        if dflt is not None:
                            local_defaults[nm] = dflt
        body = [self._cond_form_to_node(b) for b in operands[idx:]]
        return RoutineNode(name, params, aux_vars, body, line, column,
                           local_defaults, activation, opt_params)

    def _evaluate_mdl(self, node: ASTNode, bindings: Dict[str, Any]) -> ASTNode:
        """
        Evaluate MDL constructs at compile time.

        Detects MAPF/MAPR with FUNCTION forms and evaluates them
        using the MDLEvaluator, converting the results back to AST nodes.
        Also handles COND with compile-time predicates like ASSIGNED?.
        """
        if isinstance(node, CondNode):
            # Only fold CONDs whose conditions are compile-time predicates
            # (ASSIGNED? etc.); a runtime COND (FSET?, GETP, ...) must survive
            # into the generated code -- starcross's TELL DEFMAC passes
            # runtime CONDs through, and folding baked "open." into BRIDGE-FCN.
            if _cond_is_compile_time_mdl(node, _ct_bound_names(bindings)):
                result = self.mdl_evaluator.evaluate(node, bindings)
                if isinstance(result, ASTNode):
                    return self._evaluate_mdl(result, bindings)
                return self._convert_to_ast(result)
            new_clauses = []
            for _c, _a in node.clauses:
                new_clauses.append((_c, [self._evaluate_mdl(s, bindings) for s in _a]))
            node.clauses = new_clauses
            return node

        # Handle list of expressions (macro body with multiple statements)
        if isinstance(node, list):
            return [self._evaluate_mdl(item, bindings) for item in node]

        # Handle RoutineNode directly (created by parser when ROUTINE appears in DEFINE body)
        if isinstance(node, RoutineNode):
            # Add to pending routines and return None (side effect only)
            self.pending_routines.append(node)
            return None

        if not isinstance(node, FormNode):
            return node

        if not isinstance(node.operator, AtomNode):
            return node

        op_name = node.operator.value.upper()

        # Check for COND that might need compile-time evaluation
        if op_name == 'COND':
            # Only fold when every clause condition is a compile-time
            # predicate -- the same _cond_is_compile_time_mdl guard the
            # CondNode branch above uses. FORM-constructed CONDs (e.g.
            # suspended's ABS DEFMAC body <FORM COND (<FORM L? .NUM 0> ...)>)
            # previously folded UNCONDITIONALLY, evaluating runtime tests
            # like <L? <- ,P2 ,P1> 0> at compile time and collapsing the
            # whole macro to a constant (ABS -> 0, so I-WEATHER's WINDS
            # stayed 0 and ADJUST-PRESSURE barely moved: 396,000 casualties
            # instead of 8,000 on the verified route).
            _shim_clauses = []
            for _op in node.operands:
                _items = None
                if (isinstance(_op, FormNode)
                        and isinstance(_op.operator, AtomNode)
                        and _op.operator.value == '()'):
                    _items = _op.operands
                elif isinstance(_op, list):
                    _items = _op
                if _items:
                    _shim_clauses.append((_items[0], list(_items[1:])))
            _shim = type('_CondShim', (), {'clauses': _shim_clauses})
            if _cond_is_compile_time_mdl(_shim, _ct_bound_names(bindings)):
                # Evaluate COND at compile time using MDL evaluator
                result = self.mdl_evaluator.evaluate(node, bindings)
                if isinstance(result, ASTNode):
                    return self._evaluate_mdl(result, bindings)
                return self._convert_to_ast(result)
            # Runtime COND: hand codegen a real CondNode (its normal COND
            # path; FormNode-with-'()'-clauses trips ZIL0100), still
            # expanding MDL constructs inside conditions and actions.
            if _shim_clauses:
                _rt_clauses = []
                for _c, _a in _shim_clauses:
                    _rt_clauses.append(
                        (self._evaluate_mdl(_c, bindings),
                         [self._evaluate_mdl(_s, bindings) for _s in _a]))
                return CondNode(_rt_clauses, node.line, node.column)
            new_operands = [self._evaluate_mdl(_op, bindings)
                            for _op in node.operands]
            return FormNode(node.operator, new_operands, node.line,
                            node.column)

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

        # Check for FORM that needs compile-time evaluation
        # FORM is an MDL function that constructs a new form from evaluated arguments
        if op_name == 'FORM':
            # Evaluate FORM at compile time using MDL evaluator
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
                # MAPF's COLLECTOR decides the result shape. A table-builder
                # collector (<MAPF ,PLTABLE ...>) yields a TABLE of the
                # collected elements: hollywood's <DEFINE PSEUDO ...> builds
                # each room's P?THINGS pseudo-object table that way. Dropping
                # the collector wrapped the elements in <PROG ()>, which is
                # not encodable as a property value, so the THINGS property
                # silently vanished and no pseudo ("hole", "cellar", ...)
                # was ever in scope. FALSE elements become 0 words (the
                # classic parser compares them against P-ADJN).
                coll = node.operands[0] if node.operands else None
                coll_name = None
                if isinstance(coll, GlobalVarNode):
                    coll_name = coll.name.upper()
                elif (isinstance(coll, FormNode)
                      and isinstance(coll.operator, AtomNode)
                      and coll.operator.value.upper() == 'GVAL'
                      and coll.operands
                      and isinstance(coll.operands[0], AtomNode)):
                    coll_name = coll.operands[0].value.upper()
                table_kinds = {
                    'TABLE': ('TABLE', []), 'PTABLE': ('TABLE', ['PURE']),
                    'LTABLE': ('LTABLE', []), 'PLTABLE': ('LTABLE', ['PURE']),
                }
                if coll_name in table_kinds and isinstance(result, list):
                    ttype, tflags = table_kinds[coll_name]
                    vals = []
                    for item in result:
                        if item is None or item is False:
                            vals.append(NumberNode(0, node.line, node.column))
                        else:
                            vals.append(self._convert_to_ast(item))
                    return TableNode(ttype, list(tflags), None, vals,
                                     node.line, node.column)
                return self._convert_to_ast(result)

        # Check for ROUTINE that creates a routine dynamically
        if op_name == 'ROUTINE':
            # <ROUTINE name [activation] (params) body...>
            routine_node = self._routine_from_form_operands(
                node.operands, node.line, node.column)
            if routine_node is not None:
                self.pending_routines.append(routine_node)
            return None

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

                # The first operand is the operator - it should be evaluated
                # For example: <FORM <IFFLAG (IN-ZILCH PRINTI) (T PRINC)> "hello">
                # The IFFLAG should evaluate to PRINTI or PRINC
                first_op = node.operands[0]
                if isinstance(first_op, FormNode):
                    # Evaluate the form to get the actual operator
                    new_operator = self.mdl_evaluator.evaluate(first_op, bindings)
                    if not isinstance(new_operator, ASTNode):
                        if isinstance(new_operator, str):
                            new_operator = AtomNode(new_operator, first_op.line, first_op.column)
                        else:
                            new_operator = AtomNode(str(new_operator), first_op.line, first_op.column)
                else:
                    new_operator = self._substitute(first_op, bindings)
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

                    # FORM evaluates all its arguments at macro expansion time
                    # This includes STRING, IFFLAG, etc. - they should be evaluated, not just substituted
                    result = self.mdl_evaluator.evaluate(operand, bindings)
                    if isinstance(result, ASTNode):
                        new_operands.append(result)
                    elif isinstance(result, str):
                        new_operands.append(StringNode(result, operand.line if hasattr(operand, 'line') else 0, operand.column if hasattr(operand, 'column') else 0))
                    elif isinstance(result, int):
                        new_operands.append(NumberNode(result, operand.line if hasattr(operand, 'line') else 0, operand.column if hasattr(operand, 'column') else 0))
                    elif result is None:
                        # Keep the substituted form for things that shouldn't be evaluated yet
                        substituted = self._substitute(operand, bindings)
                        new_operands.append(substituted)
                    else:
                        new_operands.append(self._convert_result_to_ast(result))

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

                # Splice-unquote operand (!,X outside a quasiquote): when X
                # evaluates to a compile-time LIST, splice its elements into the
                # enclosing form.  The ZILF scope engine's SCOPE-STAGE DEFINE
                # grows its list this way: <LIST !,SCOPE-STAGES <VECTOR ...>>.
                # Historically _substitute stripped the splice wrapper to a bare
                # reference (fine for a scalar, but it turned the accumulator
                # into a nested element instead of splicing).  Only the LIST
                # case changes behavior; anything else keeps the old strip so no
                # other macro shifts.
                if isinstance(operand, SpliceUnquoteNode):
                    spliced = self.mdl_evaluator.evaluate(operand.expr, bindings)
                    if isinstance(spliced, list):
                        for item in spliced:
                            new_operands.append(
                                item if isinstance(item, ASTNode)
                                else self._convert_result_to_ast(item))
                        continue

                substituted = self._substitute(operand, bindings)
                new_operands.append(substituted)

            return FormNode(new_operator, new_operands, node.line, node.column)

        # For other node types, return as-is
        return node

    def _all_locals_bound(self, node: ASTNode, bindings: Dict[str, Any]) -> bool:
        """True if every LocalVarNode referenced in `node` has a binding.

        Guards the eager evaluation of ~<PARSE/STRING/SPNAME ...> name-builders:
        those are only reduced when their inputs are actually available. Nested
        macros (e.g. WITH-HOOK's <~<PARSE <STRING "HOOK-BEFORE-" <SPNAME .NAME>>>>)
        can reach _expand_quasiquote before .NAME is bound; evaluating then would
        fabricate an empty "HOOK-BEFORE-" atom and reference an undefined routine.
        In that case we return False and let _substitute keep the old behavior.
        """
        if isinstance(node, LocalVarNode):
            return node.name.upper() in bindings
        for v in vars(node).values():
            if isinstance(v, ASTNode):
                if not self._all_locals_bound(v, bindings):
                    return False
            elif isinstance(v, (list, tuple)):
                for x in v:
                    if isinstance(x, ASTNode) and not self._all_locals_bound(x, bindings):
                        return False
        return True

    def _expand_quasiquote(self, node: ASTNode, bindings: Dict[str, Any]) -> ASTNode:
        """
        Expand a quasiquoted expression.

        In a quasiquote context:
        - Most expressions are kept as literals (not substituted)
        - ~EXPR (UnquoteNode) - evaluate EXPR and insert its value
        - ~!EXPR (SpliceUnquoteNode) - evaluate EXPR and splice its elements

        This implements MDL/ZILF quasiquote semantics used for macro templates.
        """
        # Handle unquote: evaluate the expression with current bindings.
        # (see _all_locals_bound guard note below)
        #
        # MDL/ZILF ~EXPR means "evaluate EXPR at expansion time and insert its
        # value". _substitute alone only substitutes bound .VARs; it leaves
        # compile-time NAME-constructing builtins un-reduced. That silently broke
        # the ZILF stdlib idiom  ,~<PARSE <STRING .PREFIX "-READBUF">>  (from
        # COPY-TO-BUFS / ACTIVATE-BUFS / WORD? / VERB?): it expanded to
        # <GVAL <PARSE <STRING ...>>> instead of <GVAL EDIT-READBUF>, so the
        # codegen emitted a garbage operand and COPY-TABLE scribbled over low
        # memory (corrupting parser globals and crashing the first command).
        # Evaluate those name-builders here; everything else keeps the previous
        # substitution behavior so no other macro shifts.
        if isinstance(node, UnquoteNode):
            expr = node.expr
            if (isinstance(expr, FormNode)
                    and isinstance(expr.operator, AtomNode)
                    and expr.operator.value.upper()
                    in ('PARSE', 'STRING', 'SPNAME', 'PNAME', 'UNPARSE')
                    and self._all_locals_bound(expr, bindings)):
                result = self.mdl_evaluator.evaluate(expr, bindings)
                if isinstance(result, ASTNode):
                    return result
                if isinstance(result, str):
                    return StringNode(result, node.line, node.column)
                if isinstance(result, bool):
                    return AtomNode('T' if result else '<>', node.line, node.column)
                if isinstance(result, int):
                    return NumberNode(result, node.line, node.column)
                if result is not None:
                    return self._convert_result_to_ast(result)
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
        # Store program reference for ASSOCIATIONS introspection
        self.program = program

        # Register all macros
        for macro in program.macros:
            self.define_macro(macro)

        # MDL macro ALIASING via <SETG NEW ,OLDMACRO> (monkeypatch fix E)
        _macro_names = {m.name for m in program.macros}
        _kept_globals = []
        for _g in program.globals:
            _iv = getattr(_g, 'initial_value', None)
            if (isinstance(_iv, GlobalVarNode) and _iv.name in _macro_names
                    and _g.name not in _macro_names
                    and '!-' not in _g.name and '!-' not in _iv.name):
                # (names with !- are MDL-namespaced, e.g. the ZILF
                # REWRITE-ROUTINE!-HOOKS!-ZILF hook global -- leave those)
                _src = next(_m for _m in program.macros if _m.name == _iv.name)
                _alias = copy.copy(_src)
                _alias.name = _g.name
                program.macros.append(_alias)
                self.define_macro(_alias)
                _macro_names.add(_g.name)
                continue
            _kept_globals.append(_g)
        program.globals = _kept_globals

        # Check for PRE-COMPILE hook
        pre_compile_hook = None
        for global_node in program.globals:
            if global_node.name.upper() == 'PRE-COMPILE!-HOOKS!-ZILF':
                # Value should be a GlobalVarNode pointing to the hook function
                if isinstance(global_node.initial_value, GlobalVarNode):
                    hook_name = global_node.initial_value.name.upper()
                    if hook_name in self.macros:
                        pre_compile_hook = self.macros[hook_name]
                break

        # Execute PRE-COMPILE hook if defined
        if pre_compile_hook:
            self._execute_pre_compile_hook(pre_compile_hook, program)

        # Check for ROUTINE-REWRITER hook
        routine_rewriter = None
        for global_node in program.globals:
            if global_node.name.upper() == 'REWRITE-ROUTINE!-HOOKS!-ZILF':
                # Value should be a GlobalVarNode pointing to the rewriter function
                if isinstance(global_node.initial_value, GlobalVarNode):
                    rewriter_name = global_node.initial_value.name.upper()
                    if rewriter_name in self.macros:
                        routine_rewriter = self.macros[rewriter_name]
                break

        # Apply ROUTINE-REWRITER hook to routines if defined
        if routine_rewriter:
            program = self._apply_routine_rewriter(program, routine_rewriter)

        # Seed ct_globals from top-level <SETG X ()>-style globals whose value is
        # a compile-time LIST.  These are compile-time metaprogramming
        # accumulators (the ZILF scope engine's SCOPE-STAGES) that later
        # top-level forms grow via <SETG X <LIST !,X ...>>; the value must be
        # visible as ,X (GlobalVarNode / GVAL) before the first such form runs.
        # Scalars are left alone -- only list-valued SETG globals are treated as
        # compile-time accumulators.
        for _g in program.globals:
            if (getattr(_g, 'from_setg', False)
                    and isinstance(getattr(_g, 'initial_value', None), list)):
                self.ct_globals.setdefault(_g.name.upper(), _g.initial_value)

        # Process top-level forms (macro calls) with IN-ZILCH = false
        # These are compile-time operations that should be evaluated, not compiled
        self.in_zilch = False
        for form in program.top_level_forms:
            # Expand the macro
            expanded = self._expand_recursive(form)
            # Evaluate the result (for compile-time operations like PRINC)
            if expanded:
                self.mdl_evaluator.evaluate(expanded, {})
        # Clear top-level forms after evaluation (they've been executed, not compiled)
        program.top_level_forms = []

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
                # Check for PROPSPEC handler
                handler_name = program.propspec_handlers.get(key.upper())
                if handler_name and handler_name.upper() in self.macros:
                    # Call PROPSPEC handler with property value list
                    new_value = self._call_propspec_handler(handler_name, value, program)
                    if new_value is not None:
                        obj.properties[key] = new_value
                        continue
                # Normal macro expansion
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
                const.value = self._maybe_fold_ct_constant(const.value)

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

        # Merge routines created by EVAL during macro expansion (e.g., from PRE-COMPILE hooks)
        if self.pending_routines:
            existing_names = {r.name for r in program.routines}
            for routine_node in self.pending_routines:
                if routine_node.name not in existing_names:
                    program.routines.append(routine_node)
                    existing_names.add(routine_node.name)

        return program

    def _apply_prefix_macro(self, handler: Any, atom: AtomNode) -> Optional[ASTNode]:
        """Apply a prefix macro handler to an atom.

        The handler is a FUNCTION that takes an atom and returns a form.
        Example: <FUNCTION (W:ATOM) <VOC <SPNAME .W> BUZZ>>
        When applied to HELLO, returns <VOC "HELLO" BUZZ>.
        """
        if handler is None:
            return None

        # Handler is a callable created by _make_function
        # It takes (env, *args) - we pass an empty env and the atom as the argument
        if callable(handler):
            try:
                env = {}
                result = handler(env, atom)
                return result
            except Exception:
                return None

        return None

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
            # Also apply prefix macro transformations
            new_operator = self._expand_recursive(node.operator)
            new_operands = []
            i = 0
            operands = list(node.operands)
            while i < len(operands):
                op = operands[i]
                # Check for prefix macro: @ followed by ATOM
                if isinstance(op, AtomNode) and op.value in self.prefix_macros:
                    prefix_char = op.value
                    if i + 1 < len(operands) and isinstance(operands[i + 1], AtomNode):
                        # Apply prefix macro transformation
                        next_atom = operands[i + 1]
                        handler = self.prefix_macros[prefix_char]
                        transformed = self._apply_prefix_macro(handler, next_atom)
                        if transformed is not None:
                            # Skip both prefix and atom, add transformed result
                            expanded = self._expand_recursive(transformed)
                            if isinstance(expanded, SpliceResultNode):
                                new_operands.extend(expanded.items)
                            else:
                                new_operands.append(expanded)
                            i += 2
                            continue
                # Normal operand processing
                expanded = self._expand_recursive(op)
                if isinstance(expanded, SpliceResultNode):
                    # Inline the splice items as operands
                    new_operands.extend(expanded.items)
                else:
                    new_operands.append(expanded)
                i += 1
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
