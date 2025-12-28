"""
Abstract Syntax Tree node definitions for ZIL.

Each node represents a ZIL construct.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from enum import Enum, auto


class NodeType(Enum):
    """AST node types."""
    # Literals
    ATOM = auto()
    NUMBER = auto()
    STRING = auto()
    LOCAL_VAR = auto()
    GLOBAL_VAR = auto()

    # Forms
    FORM = auto()          # <func arg1 arg2 ...>
    ROUTINE = auto()       # <ROUTINE name ...>
    OBJECT = auto()        # <OBJECT name ...>
    ROOM = auto()          # <ROOM name ...>
    SYNTAX = auto()        # <SYNTAX ...>
    VERSION = auto()       # <VERSION n>
    GLOBAL = auto()        # <GLOBAL ...>
    CONSTANT = auto()      # <CONSTANT ...>
    PROPDEF = auto()       # <PROPDEF name default>
    BUZZ = auto()          # <BUZZ word1 word2 ...>
    SYNONYM = auto()       # <SYNONYM word1 word2 ...> (standalone)
    BIT_SYNONYM = auto()   # <BIT-SYNONYM flag1 flag2> (flag alias)
    REMOVE_SYNONYM = auto() # <REMOVE-SYNONYM word> (remove from synonyms)

    # Table/Array
    TABLE = auto()         # <TABLE ...>
    ITABLE = auto()        # <ITABLE ...>
    LTABLE = auto()        # <LTABLE ...>

    # Control flow
    COND = auto()          # <COND ...>
    AND = auto()           # <AND ...>
    OR = auto()            # <OR ...>
    NOT = auto()           # <NOT ...>
    REPEAT = auto()        # <REPEAT ...>

    # Special
    PROPERTY_LIST = auto() # Object/room properties
    PARAM_LIST = auto()    # Routine parameters
    MACRO = auto()         # <DEFMAC ...>

    # Quasiquote (MDL/ZILF metaprogramming)
    QUASIQUOTE = auto()    # ` (backtick) - template expression
    UNQUOTE = auto()       # ~ (tilde) - evaluate and insert
    SPLICE_UNQUOTE = auto() # ~! - evaluate and splice list

    # Declarations
    DIRECTIONS = auto()    # <DIRECTIONS north south ...>


@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    node_type: NodeType
    line: int = 0
    column: int = 0

    def __repr__(self):
        return f"{self.__class__.__name__}(...)"


class AtomNode(ASTNode):
    """Atom/identifier node."""
    def __init__(self, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.ATOM, line, column)
        self.value = value

    def __repr__(self):
        return f"Atom({self.value})"


class NumberNode(ASTNode):
    """Number literal node."""
    def __init__(self, value: int, line: int = 0, column: int = 0):
        super().__init__(NodeType.NUMBER, line, column)
        self.value = value

    def __repr__(self):
        return f"Number({self.value})"


class StringNode(ASTNode):
    """String literal node."""
    def __init__(self, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.STRING, line, column)
        self.value = value

    def __repr__(self):
        return f"String({self.value!r})"


class LocalVarNode(ASTNode):
    """Local variable reference (.VAR)."""
    def __init__(self, name: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.LOCAL_VAR, line, column)
        self.name = name

    def __repr__(self):
        return f"LocalVar(.{self.name})"


class GlobalVarNode(ASTNode):
    """Global variable reference (,VAR)."""
    def __init__(self, name: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.GLOBAL_VAR, line, column)
        self.name = name

    def __repr__(self):
        return f"GlobalVar(,{self.name})"


class FormNode(ASTNode):
    """Generic form/S-expression node: <func arg1 arg2 ...>"""
    def __init__(self, operator: ASTNode, operands: List[ASTNode] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.FORM, line, column)
        self.operator = operator
        self.operands = operands or []

    def __repr__(self):
        return f"Form({self.operator}, {len(self.operands)} args)"


class RoutineNode(ASTNode):
    """ROUTINE definition node."""
    def __init__(self, name: str, params: List[str] = None, aux_vars: List[str] = None,
                 body: List[ASTNode] = None, line: int = 0, column: int = 0,
                 local_defaults: Dict[str, 'ASTNode'] = None, activation: str = None,
                 opt_params: List[str] = None):
        super().__init__(NodeType.ROUTINE, line, column)
        self.name = name
        self.params = params or []
        self.aux_vars = aux_vars or []
        self.opt_params = opt_params or []  # Optional parameters (OPT) that caller can provide
        self.body = body or []
        self.declarations = {}
        # Map from variable name to default value expression
        self.local_defaults = local_defaults or {}
        # Activation name for RETURN/AGAIN with activation support
        self.activation = activation

    def __repr__(self):
        return f"Routine({self.name}, {len(self.params)} params, {len(self.body)} stmts)"


class ObjectNode(ASTNode):
    """OBJECT definition node."""
    def __init__(self, name: str, properties: Dict[str, Any] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.OBJECT, line, column)
        self.name = name
        self.properties = properties or {}

    def __repr__(self):
        return f"Object({self.name}, {len(self.properties)} props)"


class RoomNode(ASTNode):
    """ROOM definition node."""
    def __init__(self, name: str, properties: Dict[str, Any] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.ROOM, line, column)
        self.name = name
        self.properties = properties or {}

    def __repr__(self):
        return f"Room({self.name}, {len(self.properties)} props)"


class SyntaxNode(ASTNode):
    """SYNTAX definition for parser.

    Attributes:
        pattern: List of words in the syntax pattern (e.g., ['TOSS', 'OBJECT', 'AT', 'OBJECT'])
        routine: Action routine specification (e.g., 'V-TOSS PRE-TOSS')
        verb_synonyms: List of verb synonyms (e.g., ['CHUCK'] for <SYNTAX TOSS (CHUCK) ...>)
    """
    def __init__(self, pattern: List[Any] = None, routine: str = "",
                 verb_synonyms: List[str] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.SYNTAX, line, column)
        self.pattern = pattern or []
        self.routine = routine
        self.verb_synonyms = verb_synonyms or []

    def __repr__(self):
        syns = f" ({', '.join(self.verb_synonyms)})" if self.verb_synonyms else ""
        return f"Syntax({self.pattern}{syns} = {self.routine})"


class CondNode(ASTNode):
    """COND conditional node."""
    def __init__(self, clauses: List[tuple] = None, line: int = 0, column: int = 0):
        super().__init__(NodeType.COND, line, column)
        self.clauses = clauses or []

    def __repr__(self):
        return f"Cond({len(self.clauses)} clauses)"


class RepeatNode(ASTNode):
    """REPEAT loop node.

    Syntax: <REPEAT ((var1 init1) (var2 init2) ...) (cond) body...>
    or simplified: <REPEAT () body...>
    """
    def __init__(self, bindings: List[tuple] = None, condition: ASTNode = None,
                 body: List[ASTNode] = None, line: int = 0, column: int = 0):
        super().__init__(NodeType.REPEAT, line, column)
        self.bindings = bindings or []  # List of (var_name, init_value) tuples
        self.condition = condition  # Exit condition (optional)
        self.body = body or []

    def __repr__(self):
        return f"Repeat({len(self.bindings)} bindings, {len(self.body)} stmts)"


class TableNode(ASTNode):
    """TABLE/ITABLE/LTABLE node."""
    def __init__(self, table_type: str, flags: List[str] = None, size: int = None,
                 values: List[ASTNode] = None, line: int = 0, column: int = 0):
        super().__init__(NodeType.TABLE, line, column)
        self.table_type = table_type
        self.flags = flags or []
        self.size = size
        self.values = values or []

    def __repr__(self):
        return f"{self.table_type}({len(self.values)} values)"


class VersionNode(ASTNode):
    """VERSION directive node."""
    def __init__(self, version: int, line: int = 0, column: int = 0):
        super().__init__(NodeType.VERSION, line, column)
        self.version = version

    def __repr__(self):
        return f"Version({self.version})"


class GlobalNode(ASTNode):
    """GLOBAL variable definition."""
    def __init__(self, name: str, initial_value: ASTNode = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.GLOBAL, line, column)
        self.name = name
        self.initial_value = initial_value

    def __repr__(self):
        return f"Global({self.name})"


class ConstantNode(ASTNode):
    """CONSTANT definition."""
    def __init__(self, name: str, value: ASTNode, line: int = 0, column: int = 0):
        super().__init__(NodeType.CONSTANT, line, column)
        self.name = name
        self.value = value

    def __repr__(self):
        return f"Constant({self.name})"


class PropdefNode(ASTNode):
    """PROPDEF property definition.

    Supports both simple and complex formats:
    - Simple: <PROPDEF NAME DEFAULT>
    - Complex: <PROPDEF NAME <> (PATTERN1) (PATTERN2) ...>

    Each pattern has the format:
        (PROP_NAME INPUT... = OUTPUT...)
    Where INPUT elements are:
        - Literal atoms (must match exactly)
        - VAR:TYPE captures (FIX, ATOM, ROOM, GLOBAL, etc.)
        - "OPT" modifier (following elements are optional)
        - "MANY" modifier (following elements can repeat)
    And OUTPUT elements are:
        - Number (property length in bytes)
        - <> (auto-calculate length)
        - <WORD .VAR> (encode as 2-byte word)
        - <BYTE .VAR> (encode as 1-byte)
        - <VOC .VAR TYPE> (encode as vocabulary word)
        - <ROOM .VAR> (encode as room number)
        - <GLOBAL .VAR> (encode as global variable reference)
        - (CONST_NAME VALUE) (define a constant)
    """
    def __init__(self, name: str, default_value: ASTNode = None,
                 patterns: list = None, line: int = 0, column: int = 0):
        super().__init__(NodeType.PROPDEF, line, column)
        self.name = name
        self.default_value = default_value
        self.patterns = patterns or []  # List of pattern tuples (input_elements, output_elements)

    def __repr__(self):
        if self.patterns:
            return f"Propdef({self.name}, patterns={len(self.patterns)})"
        return f"Propdef({self.name})"


class MacroNode(ASTNode):
    """DEFMAC macro definition."""
    def __init__(self, name: str, params: List[tuple] = None, body: ASTNode = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.MACRO, line, column)
        self.name = name
        # params is list of (param_name, is_quoted, is_tuple, is_aux) tuples
        self.params = params or []
        self.body = body

    def __repr__(self):
        return f"Macro({self.name}, {len(self.params)} params)"


class BuzzNode(ASTNode):
    """BUZZ noise word declaration."""
    def __init__(self, words: List[str], line: int = 0, column: int = 0):
        super().__init__(NodeType.BUZZ, line, column)
        self.words = words  # List of noise words

    def __repr__(self):
        return f"Buzz({len(self.words)} words)"


class SynonymNode(ASTNode):
    """Standalone SYNONYM declaration (not in an object)."""
    def __init__(self, words: List[str], line: int = 0, column: int = 0):
        super().__init__(NodeType.SYNONYM, line, column)
        self.words = words  # List of synonym words

    def __repr__(self):
        return f"Synonym({len(self.words)} words)"


class BitSynonymNode(ASTNode):
    """BIT-SYNONYM flag alias declaration.

    Makes one flag an alias for another, so both names refer to the same bit.
    Syntax: <BIT-SYNONYM original-flag alias-flag>
    """
    def __init__(self, original: str, alias: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.BIT_SYNONYM, line, column)
        self.original = original  # The original flag name
        self.alias = alias  # The alias flag name

    def __repr__(self):
        return f"BitSynonym({self.original} -> {self.alias})"


class RemoveSynonymNode(ASTNode):
    """REMOVE-SYNONYM declaration.

    Removes a word from being a synonym, allowing it to be used independently.
    Syntax: <REMOVE-SYNONYM word>
    """
    def __init__(self, word: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.REMOVE_SYNONYM, line, column)
        self.word = word  # The word to remove from synonyms

    def __repr__(self):
        return f"RemoveSynonym({self.word})"


class QuasiquoteNode(ASTNode):
    """Quasiquote (backtick) expression.

    Represents a template that can contain unquoted expressions.
    In MDL/ZILF: `<FORM A ~X B> creates a form where X is evaluated
    and its value inserted.
    """
    def __init__(self, expr: ASTNode, line: int = 0, column: int = 0):
        super().__init__(NodeType.QUASIQUOTE, line, column)
        self.expr = expr  # The quasiquoted expression

    def __repr__(self):
        return f"Quasiquote({self.expr})"


class UnquoteNode(ASTNode):
    """Unquote (tilde) expression.

    Represents an expression within a quasiquote that should be
    evaluated and its value inserted.
    In MDL/ZILF: ~X within a quasiquote evaluates X.
    """
    def __init__(self, expr: ASTNode, line: int = 0, column: int = 0):
        super().__init__(NodeType.UNQUOTE, line, column)
        self.expr = expr  # The expression to evaluate

    def __repr__(self):
        return f"Unquote({self.expr})"


class SpliceUnquoteNode(ASTNode):
    """Splice-unquote (~!) expression.

    Represents an expression within a quasiquote that should be
    evaluated and its elements spliced into the surrounding list.
    In MDL/ZILF: ~!X evaluates X and splices the result.
    """
    def __init__(self, expr: ASTNode, line: int = 0, column: int = 0):
        super().__init__(NodeType.SPLICE_UNQUOTE, line, column)
        self.expr = expr  # The expression to evaluate and splice

    def __repr__(self):
        return f"SpliceUnquote({self.expr})"


class SpliceResultNode(ASTNode):
    """Result of a macro expansion that should be spliced inline.

    Represents a list of statements/expressions that should be inlined
    into the surrounding context rather than treated as a single value.
    Created by macros returning <CHTYPE '(...) SPLICE>.
    """
    def __init__(self, items: List['ASTNode'], line: int = 0, column: int = 0):
        super().__init__(NodeType.SPLICE_UNQUOTE, line, column)  # Reuse type
        self.items = items  # List of items to splice inline

    def __repr__(self):
        return f"SpliceResult({self.items})"


class DirectionsNode(ASTNode):
    """Directions declaration: <DIRECTIONS NORTH SOUTH EAST WEST>

    Defines direction names and their property numbers.
    Directions are assigned property numbers from MaxProperties down.
    For V3 (max 31 properties): NORTH=31, SOUTH=30, EAST=29, WEST=28
    Also creates LOW-DIRECTION constant = lowest direction property.
    """
    def __init__(self, names: List[str], line: int = 0, column: int = 0):
        super().__init__(NodeType.DIRECTIONS, line, column)
        self.names = names  # List of direction names

    def __repr__(self):
        return f"Directions({self.names})"


@dataclass
class Program:
    """Top-level program node containing all definitions."""
    version: int = 3
    routines: List[RoutineNode] = field(default_factory=list)
    objects: List[ObjectNode] = field(default_factory=list)
    rooms: List[RoomNode] = field(default_factory=list)
    globals: List[GlobalNode] = field(default_factory=list)
    constants: List[ConstantNode] = field(default_factory=list)
    propdefs: List[PropdefNode] = field(default_factory=list)
    syntax: List[SyntaxNode] = field(default_factory=list)
    tables: List[TableNode] = field(default_factory=list)
    macros: List[MacroNode] = field(default_factory=list)
    buzz_words: List[str] = field(default_factory=list)
    synonym_words: List[str] = field(default_factory=list)
    removed_synonyms: List[str] = field(default_factory=list)  # Words removed from synonyms
    directions: List[str] = field(default_factory=list)  # Direction names
    bit_synonyms: List['BitSynonymNode'] = field(default_factory=list)  # Flag aliases

    def __repr__(self):
        return (f"Program(v{self.version}, {len(self.routines)} routines, "
                f"{len(self.objects)} objects, {len(self.rooms)} rooms)")
