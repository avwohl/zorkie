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
                 body: List[ASTNode] = None, line: int = 0, column: int = 0):
        super().__init__(NodeType.ROUTINE, line, column)
        self.name = name
        self.params = params or []
        self.aux_vars = aux_vars or []
        self.body = body or []
        self.declarations = {}

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
    """SYNTAX definition for parser."""
    def __init__(self, pattern: List[Any] = None, routine: str = "",
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.SYNTAX, line, column)
        self.pattern = pattern or []
        self.routine = routine

    def __repr__(self):
        return f"Syntax({self.pattern} = {self.routine})"


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
    """PROPDEF property definition."""
    def __init__(self, name: str, default_value: ASTNode = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.PROPDEF, line, column)
        self.name = name
        self.default_value = default_value

    def __repr__(self):
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

    def __repr__(self):
        return (f"Program(v{self.version}, {len(self.routines)} routines, "
                f"{len(self.objects)} objects, {len(self.rooms)} rooms)")
