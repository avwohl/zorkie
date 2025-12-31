"""
Abstract Syntax Tree node definitions for ZIL.

Each node represents a ZIL construct.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Set
from enum import Enum, auto


class NodeType(Enum):
    """AST node types."""
    # Literals
    ATOM = auto()
    NUMBER = auto()
    STRING = auto()
    LOCAL_VAR = auto()
    GLOBAL_VAR = auto()
    CHAR_LOCAL_VAR = auto()   # %.VAR (print as character in TELL)
    CHAR_GLOBAL_VAR = auto()  # %,VAR (print as character in TELL)

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
    PREP_SYNONYM = auto()  # <PREP-SYNONYM prep1 prep2> (preposition synonym)
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
    TELL_TOKENS = auto()   # <TELL-TOKENS token1 pattern1 token2 pattern2 ...>
    ORDER_OBJECTS = auto() # <ORDER-OBJECTS? ROOMS-FIRST>
    ORDER_TREE = auto()    # <ORDER-TREE? REVERSE-DEFINED>
    LONG_WORDS = auto()    # <LONG-WORDS?>
    DEFINE_GLOBALS = auto() # <DEFINE-GLOBALS table-name (name val) (name BYTE val) ...>


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


class CharLocalVarNode(ASTNode):
    """Local variable reference for character printing (%.VAR)."""
    def __init__(self, name: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.CHAR_LOCAL_VAR, line, column)
        self.name = name

    def __repr__(self):
        return f"CharLocalVar(%.{self.name})"


class CharGlobalVarNode(ASTNode):
    """Global variable reference for character printing (%,VAR)."""
    def __init__(self, name: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.CHAR_GLOBAL_VAR, line, column)
        self.name = name

    def __repr__(self):
        return f"CharGlobalVar(%,{self.name})"


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
        object_flags: List of scope flag lists for each OBJECT in pattern
                      e.g., [['HAVE'], ['MANY']] for two OBJECTs with different flags
    """
    def __init__(self, pattern: List[Any] = None, routine: str = "",
                 verb_synonyms: List[str] = None,
                 object_flags: List[List[str]] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.SYNTAX, line, column)
        self.pattern = pattern or []
        self.routine = routine
        self.verb_synonyms = verb_synonyms or []
        self.object_flags = object_flags or []

    def __repr__(self):
        syns = f" ({', '.join(self.verb_synonyms)})" if self.verb_synonyms else ""
        flags = f" flags={self.object_flags}" if self.object_flags else ""
        return f"Syntax({self.pattern}{syns} = {self.routine}{flags})"


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
                 values: List[ASTNode] = None, line: int = 0, column: int = 0,
                 pattern_spec: List[Any] = None):
        super().__init__(NodeType.TABLE, line, column)
        self.table_type = table_type
        self.flags = flags or []
        self.size = size
        self.values = values or []
        # PATTERN specification: list of (type_name, is_rest) tuples
        # e.g., [('BYTE', False), ('WORD', False), ('WORD', True)]
        self.pattern_spec = pattern_spec or []

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


class PrepSynonymNode(ASTNode):
    """PREP-SYNONYM preposition synonym declaration.

    Makes one or more prepositions synonyms of a canonical preposition.
    Syntax: <PREP-SYNONYM canonical-prep synonym-prep...>
    Example: <PREP-SYNONYM TO TOWARD TOWARDS>
    """
    def __init__(self, canonical: str, synonyms: list, line: int = 0, column: int = 0):
        super().__init__(NodeType.PREP_SYNONYM, line, column)
        self.canonical = canonical  # The canonical preposition
        # Support both single synonym (string) and multiple synonyms (list)
        if isinstance(synonyms, str):
            self.synonyms = [synonyms]
        else:
            self.synonyms = list(synonyms)

    # Backwards compatibility property
    @property
    def synonym(self):
        return self.synonyms[0] if self.synonyms else None

    def __repr__(self):
        return f"PrepSynonym({self.canonical} -> {', '.join(self.synonyms)})"


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


class OrderObjectsNode(ASTNode):
    """ORDER-OBJECTS? directive: <ORDER-OBJECTS? ROOMS-FIRST>

    Controls how objects are numbered:
    - ROOMS-FIRST: Rooms are numbered before other objects
    - DEFINED: Objects numbered in definition order
    - REVERSE-DEFINED: Objects numbered in reverse definition order
    """
    def __init__(self, ordering: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.ORDER_OBJECTS, line, column)
        self.ordering = ordering

    def __repr__(self):
        return f"OrderObjects({self.ordering})"


class OrderTreeNode(ASTNode):
    """ORDER-TREE? directive: <ORDER-TREE? REVERSE-DEFINED>

    Controls how object tree children are ordered:
    - DEFINED: Children in definition order
    - REVERSE-DEFINED: Children in reverse definition order (default)
    """
    def __init__(self, ordering: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.ORDER_TREE, line, column)
        self.ordering = ordering

    def __repr__(self):
        return f"OrderTree({self.ordering})"


class LongWordsNode(ASTNode):
    """LONG-WORDS? directive: <LONG-WORDS?>

    Enables long word table generation. When enabled, words longer than the
    dictionary limit (6 chars in V1-3, 9 chars in V4+) are tracked and a
    LONG-WORD-TABLE is generated containing the full text of these words.
    """
    def __init__(self, line: int = 0, column: int = 0):
        super().__init__(NodeType.LONG_WORDS, line, column)

    def __repr__(self):
        return "LongWords()"


@dataclass
class DefineGlobalEntry:
    """A single entry in a DEFINE-GLOBALS declaration."""
    name: str           # Global name (e.g., MY-WORD)
    value: int          # Initial value
    is_byte: bool       # True if BYTE, False if WORD (default)
    adecl: str = None   # Optional ADECL annotation (e.g., :FIX)


class DefineGlobalsNode(ASTNode):
    """DEFINE-GLOBALS declaration: <DEFINE-GLOBALS table-name (name val) ...>

    Creates a table of "soft" globals stored in memory rather than Z-machine
    global variables. Each entry can be a word (default) or byte.

    Syntax:
        <DEFINE-GLOBALS TABLE-NAME
            (NAME1 value1)           ; word-sized, initial value
            (NAME2 BYTE value2)      ; byte-sized, initial value
            (NAME3:ADECL value3)     ; word-sized with ADECL annotation
        >

    Creates:
        - TABLE-NAME constant pointing to the table
        - NAME1, NAME2, etc. as accessor routines/macros
    """
    def __init__(self, table_name: str, entries: List[DefineGlobalEntry],
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.DEFINE_GLOBALS, line, column)
        self.table_name = table_name
        self.entries = entries

    def __repr__(self):
        return f"DefineGlobals({self.table_name}, {len(self.entries)} entries)"


@dataclass
class TellTokenDef:
    """Definition of a single TELL token.

    A token can be:
    - No arguments: <TELL-TOKENS FOO <SOME-ROUTINE>>
    - With arguments: <TELL-TOKENS DBL * <PRINT-DBL .X>>
                      <TELL-TOKENS PAIR * * <PRINT-PAIR .X .Y>>
    - Pattern match: <TELL-TOKENS D ,PRSO <DPRINT-PRSO>>  ; specific arg pattern
                     <TELL-TOKENS D * <DPRINT .X>>        ; wildcard fallback
    """
    name: str                        # Token name (e.g., "DBL")
    arg_count: int                   # Number of * arguments (0, 1, 2, etc.)
    expansion: Any                   # The form to expand to (e.g., <PRINT-DBL .X>)
    pattern: Any = None              # Optional specific pattern to match (e.g., ,PRSO)


class TellTokensNode(ASTNode):
    """TELL-TOKENS declaration: <TELL-TOKENS token1 pattern1 token2 pattern2 ...>

    Defines custom tokens for use in TELL statements.
    Format: TOKEN [* [* ...]] <EXPANSION>
    - TOKEN: Name of the custom token
    - *: Each * indicates an argument capture
    - EXPANSION: A form using .X, .Y, .Z, .W for captured args
    """
    def __init__(self, tokens: List[TellTokenDef], line: int = 0, column: int = 0):
        super().__init__(NodeType.TELL_TOKENS, line, column)
        self.tokens = tokens  # List of TellTokenDef

    def __repr__(self):
        return f"TellTokens({[t.name for t in self.tokens]})"


@dataclass
class Program:
    """Top-level program node containing all definitions."""
    version: int = 3
    version_explicit: bool = False  # True if version was explicitly set via VERSION directive
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
    verb_synonym_groups: List[List[str]] = field(default_factory=list)  # Verb synonym groups [[main, syn1, syn2], ...]
    removed_synonyms: List[str] = field(default_factory=list)  # Words removed from synonyms
    directions: List[str] = field(default_factory=list)  # Direction names
    bit_synonyms: List['BitSynonymNode'] = field(default_factory=list)  # Flag aliases
    prep_synonyms: List['PrepSynonymNode'] = field(default_factory=list)  # Preposition synonyms
    tell_tokens: Dict[str, 'TellTokenDef'] = field(default_factory=dict)  # Custom TELL tokens
    order_objects: Optional[str] = None  # ORDER-OBJECTS? setting (e.g., ROOMS-FIRST)
    order_tree: Optional[str] = None  # ORDER-TREE? setting (e.g., REVERSE-DEFINED)
    long_words: bool = False  # LONG-WORDS? enabled
    define_globals: List['DefineGlobalsNode'] = field(default_factory=list)  # DEFINE-GLOBALS declarations
    compile_time_ops: List['FormNode'] = field(default_factory=list)  # Compile-time ops: ZPUT, PUTB, ZGET, ZREST
    cleared_propspecs: Set[str] = field(default_factory=set)  # PROPSPEC cleared for atoms (e.g., DIRECTIONS)

    def __repr__(self):
        return (f"Program(v{self.version}, {len(self.routines)} routines, "
                f"{len(self.objects)} objects, {len(self.rooms)} rooms)")
