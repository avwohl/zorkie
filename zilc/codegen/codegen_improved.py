"""
Improved code generator with comprehensive opcode support.

This expanded code generator implements a much larger subset of Z-machine
opcodes and better handles ZIL language constructs.
"""

from typing import List, Dict, Any, Optional, Tuple
import struct
import sys

from ..parser.ast_nodes import *
from ..zmachine.opcodes import OpcodeTable, OperandType
from ..zmachine.text_encoding import ZTextEncoder, words_to_bytes


class ImprovedCodeGenerator:
    """Enhanced code generator with extensive opcode support."""

    def __init__(self, version: int = 3, abbreviations_table=None, string_table=None,
                 action_table=None, symbol_tables=None, compiler=None):
        self.version = version
        self.abbreviations_table = abbreviations_table
        self.string_table = string_table
        self.action_table = action_table
        self.symbol_tables = symbol_tables  # Store for later access (e.g., MAP-DIRECTIONS)
        self.compiler = compiler  # Reference to compiler for warnings
        # Get CRLF-CHARACTER from compiler's compile_globals (defaults to '|')
        crlf_char = '|'
        preserve_spaces = False
        if compiler and hasattr(compiler, 'compile_globals'):
            crlf_char = compiler.compile_globals.get('CRLF-CHARACTER', '|')
            preserve_spaces = compiler.compile_globals.get('PRESERVE-SPACES?', False)
        self.encoder = ZTextEncoder(version, abbreviations_table=abbreviations_table,
                                    crlf_character=crlf_char, preserve_spaces=preserve_spaces)
        self.opcodes = OpcodeTable()

        # Symbol tables
        self.globals: Dict[str, int] = {}
        self.global_values: Dict[str, int] = {}  # Global name -> initial value
        self.constants: Dict[str, int] = {}
        self.routines: Dict[str, int] = {}
        self.locals: Dict[str, int] = {}
        self.objects: Dict[str, int] = {}  # Object name -> number
        self.interrupts: Dict[str, int] = {}  # Interrupt name -> structure address

        # Add pre-scanned symbols (flags, properties, parser constants)
        # Track defined flags for ZIL0211 warning
        self.defined_flags: set = set()
        self.used_flags: set = set()  # Flags that are actually used in code
        # Track defined properties for ZIL0212 warning
        self.defined_properties: set = set()
        self.used_properties: set = set()  # Properties that are actually used in code

        if symbol_tables:
            # Add flag constants (TOUCHBIT, FIGHTBIT, etc.)
            for flag_name, bit_num in symbol_tables.get('flags', {}).items():
                self.constants[flag_name] = bit_num
                self.defined_flags.add(flag_name)  # Track as defined
            # Flags used in SYNTAX FIND clauses count as used
            self.used_flags.update(symbol_tables.get('syntax_flags', set()))
            # Add property constants (P?LDESC, P?STRENGTH, etc.)
            for prop_name, prop_num in symbol_tables.get('properties', {}).items():
                self.constants[prop_name] = prop_num
                # Track user-defined properties for ZIL0212 warning
                # Standard properties like P?DESC and P?LDESC are exempt
                if prop_name not in ('P?DESC', 'P?LDESC'):
                    self.defined_properties.add(prop_name)
            # Add parser constants (PS?OBJECT, PS?VERB, etc.)
            for const_name, const_val in symbol_tables.get('parser_constants', {}).items():
                self.constants[const_name] = const_val

        # Version capabilities
        self._init_version_features()

        # Code generation
        self.code = bytearray()
        self.next_global = 0x10
        self.next_object = 1
        # Interrupt/daemon tracking - maps name to table index for address resolution
        self._interrupt_table_indices: Dict[str, int] = {}  # int_name -> table index

        # Labels for branching
        self.labels: Dict[str, int] = {}
        self.label_counter = 0

        # Loop tracking for AGAIN/RETURN support
        # Each entry is a dict with 'start_offset', 'code_ref' for nested loops
        self.loop_stack: List[Dict[str, Any]] = []

        # Block scope tracking for PROG/REPEAT/BIND block-scoped RETURN
        # Each entry tracks: code_buffer, return_placeholders, block_type
        # RETURN inside a block jumps to block exit, not routine exit
        self.block_stack: List[Dict[str, Any]] = []

        # Table storage for TABLE/LTABLE/ITABLE
        # Each table is (name/id, bytes, is_pure)
        self.tables: List[Tuple[str, bytes, bool]] = []
        self.table_counter = 0
        self.table_offsets: Dict[int, int] = {}  # table_index -> offset within table data
        self._table_data_size = 0  # Running total of table data size

        # Extension table tracking (V5+)
        # Track the maximum extension word index used (e.g., MSLOCY=2, MSETBL=3)
        # If > 0, an extension table needs to be created
        self._max_extension_word = 0

        # Routine call placeholders - map placeholder_index to routine_name
        # Placeholders are encoded as 0xFD + index (high byte) + index (low byte)
        self._routine_placeholders: Dict[int, str] = {}
        self._next_placeholder_index = 0
        # Track actual placeholder positions in code (offset, placeholder_idx)
        self._placeholder_positions: List[Tuple[int, int]] = []
        # Pending placeholders for current routine (relative offset, placeholder_idx)
        self._pending_placeholders: List[Tuple[int, int]] = []
        # Track relative offset within current routine for placeholder tracking
        self._routine_code_offset: int = 0

        # String operand placeholders - map placeholder_index to string text
        # Placeholders are encoded as 0xFC + index (high byte) + index (low byte)
        self._string_placeholders: Dict[int, str] = {}
        self._next_string_placeholder_index = 0

        # Track missing routines (referenced but not defined)
        self._missing_routines: set = set()

        # Warning/error tracking
        self._warnings: List[str] = []
        self._current_routine: str = "<global>"  # Track current routine for context

        # Built-in constants
        self.constants['T'] = 1
        self.constants['<>'] = 0
        self.constants['FALSE'] = 0
        self.constants['TRUE'] = 1

        # Parser system globals (standard ZIL globals)
        # These are allocated in a specific range for parser use
        # V3: Status line reads global 0 for location, 1 for score, 2 for moves
        # V4+: No mandatory layout, but keep consistent ordering
        if self.version <= 3:
            # V3 layout: HERE, SCORE, MOVES must be at globals 0, 1, 2
            self.parser_globals = {
                'HERE': 0x10,   # Current location (global 0 for status line)
                'SCORE': 0x11,  # Score (global 1 for status line)
                'MOVES': 0x12,  # Move counter (global 2 for status line)
                'PRSA': 0x13,   # Parser action (verb number)
                'PRSO': 0x14,   # Parser direct object
                'PRSI': 0x15,   # Parser indirect object
                'WINNER': 0x16, # Current actor (usually player)
            }
            self.next_global = 0x17  # Start user globals after parser globals
        else:
            # V4+ layout: no status line constraint
            self.parser_globals = {
                'PRSA': 0x10,   # Parser action (verb number)
                'PRSO': 0x11,   # Parser direct object
                'PRSI': 0x12,   # Parser indirect object
                'HERE': 0x13,   # Current location
                'WINNER': 0x14, # Current actor (usually player)
                'MOVES': 0x15,  # Move counter
                'SCORE': 0x16,  # Score
            }
            self.next_global = 0x17  # Start user globals after parser globals

        # Reserve these globals
        for name, num in self.parser_globals.items():
            self.globals[name] = num

        # Standard verb action numbers (V? constants)
        # These map to PRSA values for common verbs
        self.verb_actions = {
            'V?TAKE': 1,
            'V?DROP': 2,
            'V?PUT': 3,
            'V?EXAMINE': 4,
            'V?LOOK': 5,
            'V?INVENTORY': 6,
            'V?QUIT': 7,
            'V?OPEN': 8,
            'V?CLOSE': 9,
            'V?READ': 10,
            'V?EAT': 11,
            'V?DRINK': 12,
            'V?ATTACK': 13,
            'V?KILL': 14,
            'V?WAIT': 15,
            'V?PUSH': 16,
            'V?PULL': 17,
            'V?TURN': 18,
            'V?MOVE': 19,
            'V?CLIMB': 20,
            'V?CLIMB-ON': 21,
            'V?BOARD': 22,
            'V?LAMP-ON': 23,
            'V?LAMP-OFF': 24,
            'V?POUR': 25,
            'V?TASTE': 26,
            'V?RUB': 27,
            'V?LOOK-INSIDE': 28,
            'V?LOOK-UNDER': 29,
            'V?SAVE': 30,
            'V?RESTORE': 31,
            'V?RESTART': 32,
            # Additional verb constants
            'V?INFLATE': 33,
            'V?DEFLATE': 34,
            'V?WALK-TO': 35,
            'V?WALK': 36,
            'V?GO': 37,
            'V?ENTER': 38,
            'V?EXIT': 39,
            'V?UNLOCK': 40,
            'V?LOCK': 41,
            'V?TIE': 42,
            'V?UNTIE': 43,
            'V?GIVE': 44,
            'V?THROW': 45,
            'V?WAVE': 46,
            'V?RAISE': 47,
            'V?LOWER': 48,
            'V?DIG': 49,
            'V?FILL': 50,
            'V?EMPTY': 51,
            'V?TELL': 52,
            'V?ASK': 53,
            'V?LIGHT': 54,
            'V?EXTINGUISH': 55,
        }

        # Add verb constants to constant table
        for verb, num in self.verb_actions.items():
            self.constants[verb] = num

    def _init_version_features(self):
        """Initialize version-specific feature flags."""
        self.has_colors = self.version >= 5
        self.has_sound = self.version >= 3
        self.has_mouse = self.version >= 5
        self.has_graphics = self.version >= 6
        self.has_extended_opcodes = self.version >= 5
        self.max_objects = 255 if self.version <= 3 else 65535
        self.max_properties = 31 if self.version <= 3 else 63

        # Version-specific opcodes availability
        self.v4_opcodes = self.version >= 4
        self.v5_opcodes = self.version >= 5
        self.v6_opcodes = self.version >= 6

    def _warn(self, message: str):
        """Record a warning message with current context.

        Warnings can be suppressed via SUPPRESS-WARNINGS? directive in source.
        Warnings can be converted to errors via WARN-AS-ERROR? directive.
        """
        # Check if warnings are suppressed
        if self.compiler:
            # Check for suppress all
            if getattr(self.compiler, 'suppress_all_warnings', False):
                return
            # Check for specific warning code suppression
            suppressed = getattr(self.compiler, 'suppressed_warnings', set())
            for code in suppressed:
                if code in message:
                    return

        full_msg = f"[codegen] Warning in {self._current_routine}: {message}"

        # Check if warnings should be treated as errors
        if self.compiler and getattr(self.compiler, 'warn_as_error', False):
            raise SyntaxError(full_msg)

        self._warnings.append(full_msg)
        print(full_msg, file=sys.stderr)

    def _error(self, message: str):
        """Raise a compilation error with current context."""
        full_msg = f"[codegen] Error in {self._current_routine}: {message}"
        raise SyntaxError(full_msg)

    def get_warnings(self) -> List[str]:
        """Return all warnings generated during code generation."""
        return self._warnings.copy()

    def _check_unprintable_chars(self, text: str) -> None:
        """Check for unprintable characters in a string and warn if found.

        ZIL0410: string contains unprintable character
        - Tab (0x09) is legal in V6 only
        - Newline (0x0A) and CR (0x0D) are always legal
        - Other control characters (0x00-0x1F except the above) are never legal
        """
        for char in text:
            code = ord(char)
            if code < 32:  # Control characters
                # Newline and CR are always allowed
                if code == 10 or code == 13:
                    continue
                # Tab is allowed in V6 only
                if code == 9:
                    if self.version < 6:
                        self._warn(f"ZIL0410: string contains unprintable character (tab) - only valid in V6+")
                    continue
                # Other control characters are never allowed
                char_repr = repr(chr(code))[1:-1]  # Get escaped representation
                self._warn(f"ZIL0410: string contains unprintable character (0x{code:02X}: {char_repr})")

    def _parse_char_literal(self, value: str) -> Optional[int]:
        r"""Parse a ZIL character literal and return its ASCII code.

        ZIL character literal formats:
        - !\x - escaped character (e.g., !\! = '!' = 33, !\n = newline = 10)
        - \x - backslash character (e.g., \. = '.' = 46)

        Returns ASCII code or None if not a character literal.
        """
        # !\x format - two-character escape after !
        if value.startswith('!\\') and len(value) == 3:
            char = value[2]
            # Handle common escape sequences
            if char == 'n':
                return 10  # newline
            elif char == 't':
                return 9   # tab
            elif char == 'r':
                return 13  # carriage return
            elif char == '0':
                return 0   # null
            else:
                return ord(char)

        # \x format - backslash followed by character
        if value.startswith('\\') and len(value) == 2:
            char = value[1]
            # Handle common escape sequences
            if char == 'n':
                return 10  # newline
            elif char == 't':
                return 9   # tab
            elif char == 'r':
                return 13  # carriage return
            elif char == '0':
                return 0   # null
            else:
                return ord(char)

        # !x format (single char after !) - less common but possible
        if value.startswith('!') and len(value) == 2:
            return ord(value[1])

        return None

    def generate(self, program: Program) -> bytes:
        """Generate bytecode from program AST."""
        # Add verb constants from action table
        if self.action_table and 'verb_constants' in self.action_table:
            for const_name, value in self.action_table['verb_constants'].items():
                self.constants[const_name] = value

        # Pre-assign object numbers FIRST so globals can reference them
        # (e.g., <GLOBAL HERE CAT> needs CAT to be assigned number 1)
        for obj in program.objects:
            self.objects[obj.name] = self.next_object
            self.next_object += 1
        for room in program.rooms:
            self.objects[room.name] = self.next_object
            self.next_object += 1

        # Process globals (register names and capture initial values)
        for global_node in program.globals:
            # Check if this is a parser global (like HERE, SCORE, MOVES)
            # If so, don't allocate a new slot - use the reserved one
            if global_node.name not in self.parser_globals:
                self.globals[global_node.name] = self.next_global
                self.next_global += 1
            # else: already in self.globals from parser_globals initialization

            # Capture initial value if provided
            if global_node.initial_value is not None:
                # Check for TableNode first - has special handling for flags like LEXV
                if isinstance(global_node.initial_value, TableNode):
                    # Handle TABLE/LTABLE/ITABLE/PTABLE initial values
                    self._compile_global_table_node(global_node.name, global_node.initial_value)
                elif isinstance(global_node.initial_value, FormNode):
                    # Handle TABLE/LTABLE/ITABLE/PTABLE initial values (legacy)
                    if isinstance(global_node.initial_value.operator, AtomNode):
                        form_op = global_node.initial_value.operator.value.upper()
                        if form_op in ('TABLE', 'LTABLE', 'ITABLE', 'PTABLE'):
                            # Compile the table and get placeholder
                            self._compile_global_table(global_node.name, global_node.initial_value, form_op)
                else:
                    # Simple value (number, atom, etc.)
                    init_val = self.get_operand_value(global_node.initial_value)
                    if isinstance(init_val, int):
                        self.global_values[global_node.name] = init_val

        # Reserve globals for ACTIONS and PREACTIONS tables
        if self.action_table:
            self._setup_action_table_globals()

        # Process constants
        for const_node in program.constants:
            self.eval_constant(const_node)

        # Note: Objects were already assigned numbers above (before globals)
        # so that globals can reference objects like <GLOBAL HERE CAT>

        # Pre-populate routine names so we can detect user-defined routines
        # during code generation (before their offsets are known)
        self._routine_names = {routine.name for routine in program.routines}
        # Store routine parameter info for call validation
        # Maps routine name -> (num_required, num_optional)
        self._routine_param_info = {}
        for routine in program.routines:
            num_required = len(routine.params)
            num_optional = len(routine.opt_params)
            self._routine_param_info[routine.name] = (num_required, num_optional)

        # Generate routines - GO must be first as it's the entry point
        # First, find the GO routine and put it at the front
        go_routine = None
        other_routines = []
        for routine_node in program.routines:
            if routine_node.name == 'GO':
                go_routine = routine_node
            else:
                other_routines.append(routine_node)

        # Generate GO first (if found), then other routines
        routines_to_generate = []
        if go_routine:
            routines_to_generate.append(go_routine)
        routines_to_generate.extend(other_routines)

        for routine_node in routines_to_generate:
            self.generate_routine(routine_node)

        # Generate ACTIONS table data
        if self.action_table:
            self._generate_action_tables()

        return bytes(self.code)

    def _setup_action_table_globals(self):
        """Reserve globals for ACTIONS and PREACTIONS tables."""
        if 'actions' in self.action_table and self.action_table['actions']:
            self.globals['ACTIONS'] = self.next_global
            self.next_global += 1
        if 'preactions' in self.action_table and self.action_table['preactions']:
            self.globals['PREACTIONS'] = self.next_global
            self.next_global += 1

    def _compile_global_table_node(self, global_name: str, table_node: 'TableNode'):
        """Compile a TableNode initial value for a global.

        This creates the table data and sets up the global to point to it.
        """
        table_data = bytearray()
        table_type = table_node.table_type.upper()
        is_pure = 'PURE' in table_node.flags or table_type == 'PTABLE'
        is_byte = 'BYTE' in table_node.flags
        is_string = 'STRING' in table_node.flags
        is_lexv = 'LEXV' in table_node.flags
        is_length = 'LENGTH' in table_node.flags
        if is_string:
            is_byte = True  # STRING implies BYTE mode

        values = table_node.values

        # Handle (BYTE LENGTH) format for ITABLE - text buffer format
        # Format: byte 0 = max length, then size bytes initialized to init value
        if is_length and is_byte and table_type == 'ITABLE':
            initial_size = table_node.size or 1
            init_value = 0
            if values and isinstance(values[0], NumberNode):
                init_value = values[0].value & 0xFF

            # Byte 0: max length (size)
            table_data.append(initial_size & 0xFF)
            # Fill with initial value
            for i in range(initial_size):
                table_data.append(init_value)

            # Store the table
            table_idx = len(self.tables)
            self.table_offsets[table_idx] = self._table_data_size
            self._table_data_size += len(table_data)
            self.table_counter += 1
            self.tables.append((f"_GLOBAL_{global_name}", bytes(table_data), is_pure))
            self.global_values[global_name] = 0xFF00 | table_idx
            return

        # Handle LEXV (lexical buffer) format for ITABLE
        # LEXV format: byte max_entries, byte count, then 4 bytes per entry
        if is_lexv and table_type == 'ITABLE':
            initial_size = table_node.size or 1
            # Warn if size isn't a multiple of 3 (each lexeme entry is 3 words)
            if initial_size % 3 != 0:
                self.compiler.warn(
                    "MDL0428",
                    f"LEXV table size {initial_size} is not a multiple of 3"
                )
            # Header: max entries (byte), word count (byte, initially 0)
            table_data.append(initial_size & 0xFF)
            table_data.append(0)  # Initially 0 words parsed
            # Each entry is 4 bytes: word (dict addr), byte (start), byte (len)
            for i in range(initial_size):
                table_data.extend([0, 0, 0, 0])  # Empty entry
            # Store the table
            table_idx = len(self.tables)
            self.table_offsets[table_idx] = self._table_data_size
            self._table_data_size += len(table_data)
            self.table_counter += 1
            self.tables.append((f"_GLOBAL_{global_name}", bytes(table_data), is_pure))
            self.global_values[global_name] = 0xFF00 | table_idx
            return

        # For LTABLE, add length prefix
        if table_type == 'LTABLE':
            table_data.extend(struct.pack('>H', len(values)))

        # Handle ITABLE with repeat count
        initial_size = table_node.size

        # Warn about table size overflow (MDL0430)
        if initial_size and table_type == 'ITABLE':
            if is_byte and initial_size > 255:
                self.compiler.warn(
                    "MDL0430",
                    f"ITABLE size {initial_size} overflows byte length prefix (max 255)"
                )
                # Cap size to prevent memory overflow
                initial_size = 1
            elif not is_byte and initial_size > 65535:
                self.compiler.warn(
                    "MDL0430",
                    f"ITABLE size {initial_size} overflows word length prefix (max 65535)"
                )
                # Cap size to prevent memory overflow
                initial_size = 1

        if initial_size and table_type == 'ITABLE' and values:
            # ITABLE with size and values: repeat pattern 'size' times
            # <ITABLE 2 1 2 3> = [1, 2, 3, 1, 2, 3] (pattern repeated 2x)
            pattern_data = self._encode_table_values(values, default_is_byte=is_byte,
                                                      is_string=is_string)
            for _ in range(initial_size):
                table_data.extend(pattern_data)
        elif initial_size and table_type == 'ITABLE':
            # ITABLE with just size: create zero-filled table
            entry_size = 1 if is_byte else 2
            for _ in range(initial_size):
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))
        else:
            # Encode table values using helper that handles #BYTE/#WORD prefixes
            encoded_data = self._encode_table_values(values, default_is_byte=is_byte,
                                                     is_string=is_string)
            # For TABLE with LENGTH flag, add a byte length prefix
            if is_length and table_type == 'TABLE':
                data_len = len(encoded_data)
                if data_len > 255:
                    self.compiler.warn(
                        "MDL0430",
                        f"TABLE size {data_len} overflows byte length prefix (max 255)"
                    )
                table_data.append(min(data_len, 255))
            table_data.extend(encoded_data)

        # Store the table
        table_idx = len(self.tables)
        self.table_offsets[table_idx] = self._table_data_size
        self._table_data_size += len(table_data)
        self.table_counter += 1
        self.tables.append((f"_GLOBAL_{global_name}", bytes(table_data), is_pure))

        # Set placeholder for table address (will be resolved by assembler)
        self.global_values[global_name] = 0xFF00 | table_idx

    def _compile_global_table(self, global_name: str, form_node: 'FormNode', table_type: str):
        """Compile a TABLE/LTABLE/ITABLE/PTABLE initial value for a global (legacy FormNode).

        This creates the table data and sets up the global to point to it.
        """
        table_data = bytearray()
        is_pure = table_type == 'PTABLE'
        is_byte = False
        is_string = False
        is_lexv = False
        is_length = False

        # Process operands from the form
        values = []
        for op in form_node.operands:
            # Check for flags like (PURE), (BYTE), (STRING), (LEXV), (LENGTH)
            if isinstance(op, FormNode):
                if isinstance(op.operator, AtomNode):
                    flag_name = op.operator.value.upper()
                    if flag_name == 'PURE':
                        is_pure = True
                        continue
                    elif flag_name == 'BYTE':
                        is_byte = True
                        continue
                    elif flag_name == 'STRING':
                        is_string = True
                        is_byte = True
                        continue
                    elif flag_name == 'LEXV':
                        is_lexv = True
                        continue
                    elif flag_name == 'LENGTH':
                        is_length = True
                        continue
            elif isinstance(op, AtomNode):
                flag_name = op.value.upper()
                if flag_name == 'PURE':
                    is_pure = True
                    continue
                elif flag_name == 'BYTE':
                    is_byte = True
                    continue
                elif flag_name == 'STRING':
                    is_string = True
                    is_byte = True
                    continue
                elif flag_name == 'LEXV':
                    is_lexv = True
                    continue
                elif flag_name == 'LENGTH':
                    is_length = True
                    continue
            values.append(op)

        # For LTABLE, add length prefix
        if table_type == 'LTABLE':
            table_data.extend(struct.pack('>H', len(values)))

        # Handle ITABLE size prefix
        initial_size = None
        if table_type == 'ITABLE' and values and isinstance(values[0], NumberNode):
            initial_size = values[0].value
            values = values[1:]

        # Handle (BYTE LENGTH) format for ITABLE - text buffer format
        # Format: byte 0 = max length, then size bytes initialized to init value
        if is_length and is_byte and table_type == 'ITABLE':
            num_entries = initial_size if initial_size else 1
            init_value = 0
            if values and isinstance(values[0], NumberNode):
                init_value = values[0].value & 0xFF

            # Byte 0: max length (size)
            table_data.append(num_entries & 0xFF)
            # Fill with initial value
            for i in range(num_entries):
                table_data.append(init_value)

            # Store the table
            table_idx = len(self.tables)
            self.table_offsets[table_idx] = self._table_data_size
            self._table_data_size += len(table_data)
            self.table_counter += 1
            self.tables.append((f"_GLOBAL_{global_name}", bytes(table_data), is_pure))
            self.global_values[global_name] = 0xFF00 | table_idx
            return

        # Handle LEXV (lexical buffer) format for ITABLE
        # LEXV format: byte max_entries, byte count, then 4 bytes per entry
        if is_lexv and table_type == 'ITABLE':
            num_entries = initial_size if initial_size else 1
            # Warn if size isn't a multiple of 3 (each lexeme entry is 3 words)
            if num_entries % 3 != 0:
                self.compiler.warn(
                    "MDL0428",
                    f"LEXV table size {num_entries} is not a multiple of 3"
                )
            # Header: max entries (byte), word count (byte, initially 0)
            table_data.append(num_entries & 0xFF)
            table_data.append(0)  # Initially 0 words parsed
            # Each entry is 4 bytes: word (dict addr), byte (start), byte (len)
            for i in range(num_entries):
                table_data.extend([0, 0, 0, 0])  # Empty entry
            # Store the table
            table_idx = len(self.tables)
            self.table_offsets[table_idx] = self._table_data_size
            self._table_data_size += len(table_data)
            self.table_counter += 1
            self.tables.append((f"_GLOBAL_{global_name}", bytes(table_data), is_pure))
            self.global_values[global_name] = 0xFF00 | table_idx
            return

        # Warn about table size overflow (MDL0430)
        if initial_size and table_type == 'ITABLE':
            if is_byte and initial_size > 255:
                self.compiler.warn(
                    "MDL0430",
                    f"ITABLE size {initial_size} overflows byte length prefix (max 255)"
                )
                initial_size = 1
            elif not is_byte and initial_size > 65535:
                self.compiler.warn(
                    "MDL0430",
                    f"ITABLE size {initial_size} overflows word length prefix (max 65535)"
                )
                initial_size = 1

        # Handle ITABLE with repeat count
        if initial_size and table_type == 'ITABLE' and values:
            # ITABLE with size and values: repeat pattern 'size' times
            # <ITABLE 2 1 2 3> = [1, 2, 3, 1, 2, 3] (pattern repeated 2x)
            pattern_data = self._encode_table_values(values, default_is_byte=is_byte,
                                                      is_string=is_string)
            for _ in range(initial_size):
                table_data.extend(pattern_data)
        elif initial_size and table_type == 'ITABLE':
            # ITABLE with just size: create zero-filled table
            entry_size = 1 if is_byte else 2
            for _ in range(initial_size):
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))
        else:
            # Encode table values using helper that handles #BYTE/#WORD prefixes
            encoded_data = self._encode_table_values(values, default_is_byte=is_byte,
                                                     is_string=is_string)
            # For TABLE with LENGTH flag, add a byte length prefix
            if is_length and table_type == 'TABLE':
                data_len = len(encoded_data)
                if data_len > 255:
                    self.compiler.warn(
                        "MDL0430",
                        f"TABLE size {data_len} overflows byte length prefix (max 255)"
                    )
                table_data.append(min(data_len, 255))
            table_data.extend(encoded_data)

        # Legacy padding for ITABLE - shouldn't be needed with new logic
        if False and initial_size and table_type == 'ITABLE':
            entry_size = 1 if is_byte else 2
            while len(table_data) < initial_size * entry_size:
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))

        # Store the table
        table_idx = len(self.tables)
        self.table_offsets[table_idx] = self._table_data_size
        self._table_data_size += len(table_data)
        self.table_counter += 1
        self.tables.append((f"_GLOBAL_{global_name}", bytes(table_data), is_pure))

        # Set placeholder for table address (will be resolved by assembler)
        self.global_values[global_name] = 0xFF00 | table_idx

    def _generate_action_tables(self):
        """Generate ACTIONS and PREACTIONS table data.

        Creates tables containing routine addresses that will be resolved
        by the assembler using routine fixups.
        """
        # Create ACTIONS table: array of routine addresses indexed by action number
        if 'action_to_routine' in self.action_table:
            action_to_routine = self.action_table['action_to_routine']
            max_action = max(action_to_routine.keys()) if action_to_routine else 0

            # Build table data with routine address placeholders
            table_data = bytearray()
            table_data.extend([0x00, 0x00])  # Entry 0 is reserved (no action)

            for action_num in range(1, max_action + 1):
                routine_name = action_to_routine.get(action_num)
                if routine_name and routine_name in self.routines:
                    # Add placeholder that will be resolved
                    placeholder_idx = self._next_placeholder_index
                    self._routine_placeholders[placeholder_idx] = routine_name
                    self._next_placeholder_index += 1
                    table_data.append(0xFD)
                    table_data.append(placeholder_idx & 0xFF)
                else:
                    # No routine for this action
                    table_data.extend([0x00, 0x00])

            # Track table offset properly (like generate_table does)
            table_index = len(self.tables)
            self.table_offsets[table_index] = self._table_data_size
            self._table_data_size += len(table_data)

            # Store table
            table_name = f'_ACTIONS_TABLE_{self.table_counter}'
            self.table_counter += 1
            self.tables.append((table_name, bytes(table_data), True))

            # Link ACTIONS global to the table using placeholder
            if 'ACTIONS' in self.globals:
                self.global_values['ACTIONS'] = 0xFF00 | table_index

    def get_routine_fixups(self) -> List[Tuple[int, int]]:
        """Get routine call fixups for the assembler to resolve.

        Uses tracked placeholder positions instead of scanning, to avoid
        false matches on data bytes that happen to look like placeholders.

        For missing routines, uses offset 0 which will result in address 0x0000
        (a safe null routine address).

        Returns list of (byte_offset_in_code, routine_byte_offset) pairs.
        The assembler should convert routine_byte_offset to packed address
        using high_mem_base and patch at byte_offset_in_code.
        """
        fixups = []

        # Use tracked placeholder positions
        for offset, placeholder_idx in self._placeholder_positions:
            if placeholder_idx in self._routine_placeholders:
                routine_name = self._routine_placeholders[placeholder_idx]
                if routine_name in self.routines:
                    routine_offset = self.routines[routine_name]
                    fixups.append((offset, routine_offset))
                else:
                    # Missing routine - track it and use offset 0
                    self._missing_routines.add(routine_name)
                    fixups.append((offset, 0))  # Will become 0x0000

        return fixups

    def get_table_routine_fixups(self) -> List[Tuple[int, int]]:
        """Get routine address fixups for table data.

        Scans table data for placeholder markers (0xFD + index) and returns
        (byte_offset_in_table_data, routine_byte_offset) pairs.

        For missing routines, uses offset 0 which will result in address 0x0000.

        Returns list of (byte_offset_in_tables, routine_byte_offset) pairs.
        The assembler should convert routine_byte_offset to packed address
        and patch the table data at byte_offset_in_tables.
        """
        fixups = []
        table_data = self.get_table_data()

        # Scan table data for placeholder markers
        i = 0
        while i < len(table_data) - 1:
            if table_data[i] == 0xFD:
                placeholder_idx = table_data[i + 1]
                if placeholder_idx in self._routine_placeholders:
                    routine_name = self._routine_placeholders[placeholder_idx]
                    if routine_name in self.routines:
                        routine_offset = self.routines[routine_name]
                        fixups.append((i, routine_offset))
                    else:
                        # Missing routine - track it and use offset 0
                        self._missing_routines.add(routine_name)
                        fixups.append((i, 0))  # Will become 0x0000
            i += 1

        return fixups

    def get_missing_routines(self) -> set:
        """Get set of routine names that were called but not defined.

        Returns:
            Set of routine names that are missing.
        """
        return self._missing_routines

    def get_string_placeholders(self) -> Dict[int, str]:
        """Get string operand placeholders for the assembler to resolve.

        Returns a mapping of placeholder index to string text.
        Placeholder values are encoded as 0xFC00 | index in the bytecode.
        The assembler should replace these with actual packed addresses.
        """
        return self._string_placeholders.copy()

    def eval_constant(self, const_node: ConstantNode):
        """Evaluate and store a constant."""
        # Handle TableNode values (ITABLE, TABLE, LTABLE)
        if isinstance(const_node.value, TableNode):
            # Compile the table and store reference
            self._compile_global_table_node(const_node.name, const_node.value)
            return

        value = self.eval_expression(const_node.value)
        if value is not None:
            self.constants[const_node.name] = value

    def eval_expression(self, node: ASTNode) -> Optional[int]:
        """Evaluate a constant expression at compile time."""
        if isinstance(node, NumberNode):
            return node.value
        elif isinstance(node, AtomNode):
            if node.value in self.constants:
                return self.constants[node.value]
            elif node.value == 'T':
                return 1
            elif node.value == '<>':
                return 0
        elif isinstance(node, FormNode):
            # Handle <> (FALSE) form
            if isinstance(node.operator, AtomNode) and node.operator.value == '<>' and not node.operands:
                return 0
        return None

    def generate_routine(self, routine: RoutineNode) -> bytes:
        """Generate bytecode for a routine."""
        self._current_routine = routine.name  # Track for warnings

        # Validate GO routine constraints
        if routine.name == "GO":
            # GO routine cannot have required (positional) parameters in any version
            if len(routine.params) > 0:
                raise ValueError(
                    "GO routine cannot have required parameters. "
                    "Use \"AUX\" or \"OPT\" for local variables."
                )
            # GO routine cannot have any locals in V1-V5
            if len(routine.aux_vars) > 0 and self.version < 6:
                raise ValueError(
                    f"GO routine cannot have local variables in V{self.version}. "
                    f"Use a separate routine and call it from GO, or use V6."
                )

        # Validate argument count limits
        num_params = len(routine.params)
        num_opt_params = len(routine.opt_params)
        if self.version <= 3:
            # V1-3: Maximum 3 required arguments (CALL can only pass 3 args)
            if num_params > 3:
                raise ValueError(
                    f"Routine {routine.name} has {num_params} required parameters, "
                    f"but V{self.version} only supports up to 3. "
                    f"Use \"OPT\" or \"AUX\" for additional variables."
                )
            # MDL0417: Warn if some optional args can never be passed
            if num_params + num_opt_params > 3:
                self.compiler.warn(
                    "MDL0417",
                    f"routine {routine.name} has {num_opt_params} optional parameters, "
                    f"but only {3 - num_params} can ever be passed in V{self.version}"
                )
        elif self.version <= 7:
            # V4-7: Maximum 7 required arguments
            if num_params > 7:
                raise ValueError(
                    f"Routine {routine.name} has {num_params} required parameters, "
                    f"but V{self.version} only supports up to 7. "
                    f"Use \"OPT\" or \"AUX\" for additional variables."
                )
            # MDL0417: Warn if some optional args can never be passed
            if num_params + num_opt_params > 7:
                self.compiler.warn(
                    "MDL0417",
                    f"routine {routine.name} has {num_opt_params} optional parameters, "
                    f"but only {7 - num_params} can ever be passed in V{self.version}"
                )

        # Align routine to proper boundary for packed addresses
        # V1-3: Even addresses (divisible by 2)
        # V4-7: Addresses divisible by 4
        # V8: Addresses divisible by 8
        if self.version <= 3:
            alignment = 2
        elif self.version <= 7:
            alignment = 4
        else:
            alignment = 8

        # Add padding if needed
        current_offset = len(self.code)
        if current_offset % alignment != 0:
            padding_needed = alignment - (current_offset % alignment)
            self.code.extend(bytes(padding_needed))  # Pad with zeros

        routine_start = len(self.code)
        routine_code = bytearray()
        # Track current routine code buffer for placeholder position tracking
        self._current_routine_code = routine_code
        self._pending_placeholders.clear()

        # Build local variable table
        self.locals = {}
        local_names = []  # Keep track of names in order
        var_num = 1
        for param in routine.params:
            self.locals[param] = var_num
            local_names.append(param)
            var_num += 1
        for aux_var in routine.aux_vars:
            self.locals[aux_var] = var_num
            local_names.append(aux_var)
            var_num += 1

        num_locals = len(routine.params) + len(routine.aux_vars)

        # Track local variable usage for ZIL0210 warnings
        self.used_locals = set()  # Locals that have been read
        self.locals_with_side_effect_init = set()  # Locals initialized with routine calls
        self.routine_level_locals = set(local_names)  # Routine-level locals (for warning scope)

        # Mark locals with side-effect initializers (FormNode = routine call)
        for local_name in local_names:
            if local_name in routine.local_defaults:
                default_node = routine.local_defaults[local_name]
                if isinstance(default_node, FormNode):
                    self.locals_with_side_effect_init.add(local_name)

        # Save routine locals for SETG fallback (not affected by PROG/BIND shadowing)
        self.routine_locals = dict(self.locals)

        # Track max local slot for PROG/BIND dynamic locals
        self.max_local_slot = num_locals

        # Routine header (will be patched later if PROG/BIND add more locals)
        routine_code.append(num_locals & 0x0F)

        # Local variable initial values (V1-4 only)
        if self.version <= 4:
            for local_name in local_names:
                init_val = 0
                if local_name in routine.local_defaults:
                    default_node = routine.local_defaults[local_name]
                    # Only handle simple number literals for initial values
                    if isinstance(default_node, NumberNode):
                        init_val = default_node.value & 0xFFFF
                routine_code.extend(struct.pack('>H', init_val))

        # Track position for routine-level AGAIN (local initialization start)
        # For V3/V4, we also generate STORE instructions so AGAIN can reset locals
        routine_init_start = len(routine_code)

        # Generate local initialization code
        # V5+: Required for initial values since header doesn't have them
        # V3/V4: Needed for routine-level AGAIN to reset locals
        for local_name in local_names:
            if local_name in routine.local_defaults:
                default_node = routine.local_defaults[local_name]
                if isinstance(default_node, NumberNode):
                    init_val = default_node.value
                    local_num = self.locals[local_name]
                    # Generate STORE instruction: store local init_val
                    if 0 <= init_val <= 255:
                        # Small constant: long form 0 0 0D = 0x0D
                        routine_code.append(0x0D)
                        routine_code.append(local_num & 0xFF)
                        routine_code.append(init_val & 0xFF)
                    else:
                        # Large constant: VAR form
                        routine_code.append(0xED)  # VAR form STOREW
                        routine_code.append(0x4F)  # small, large, omit, omit
                        routine_code.append(local_num & 0xFF)
                        routine_code.append((init_val >> 8) & 0xFF)
                        routine_code.append(init_val & 0xFF)

        # Push routine-level loop context for AGAIN support
        # AGAIN at routine level should jump to routine_init_start to reset locals
        if not hasattr(self, 'loop_stack'):
            self.loop_stack = []
        routine_loop_ctx = {
            'loop_start': routine_init_start,
            'loop_type': 'ROUTINE',
            'again_placeholders': [],
            'activation': routine.activation,  # For RETURN/AGAIN with activation
        }
        self.loop_stack.append(routine_loop_ctx)

        # Track current routine's activation for RETURN
        self._current_routine_activation = routine.activation

        # Generate code for routine body
        for stmt in routine.body:
            # Track placeholder indices created in this statement
            placeholder_start_idx = self._next_placeholder_index
            stmt_code = self.generate_statement(stmt)
            # Track placeholder positions in this statement's code
            # Only match placeholders with index >= start_idx (created in this statement)
            stmt_offset = len(routine_code)
            for i in range(len(stmt_code) - 1):
                if stmt_code[i] == 0xFD:
                    # Skip if this 0xFD follows 0x8D - that's a string placeholder for PRINT_PADDR
                    # String placeholder format: 0x8D 0xFD <idx>
                    # Routine placeholder format: 0xFD <idx> (as 16-bit operand high byte)
                    if i > 0 and stmt_code[i - 1] == 0x8D:
                        continue  # This is a string placeholder, not a routine placeholder
                    placeholder_idx = stmt_code[i + 1]
                    # Only match placeholders created in THIS statement
                    if (placeholder_idx >= placeholder_start_idx and
                            placeholder_idx in self._routine_placeholders):
                        self._pending_placeholders.append((stmt_offset + i, placeholder_idx))
            routine_code.extend(stmt_code)

        # Add implicit return if the routine doesn't end with a terminating instruction
        # This ensures all routines have a valid return path
        if not self._ends_with_terminator(routine.body):
            # Check if last statement is a value that should be returned
            implicit_ret_generated = False
            if routine.body:
                last_stmt = routine.body[-1]
                if isinstance(last_stmt, LocalVarNode):
                    # Return the local variable, falling back to global if no local exists
                    var_num = self.locals.get(last_stmt.name)
                    if var_num is not None:
                        # Mark local as used (for ZIL0210 warning tracking)
                        if hasattr(self, 'used_locals'):
                            self.used_locals.add(last_stmt.name)
                        routine_code.append(0xAB)  # RET variable
                        routine_code.append(var_num)
                        implicit_ret_generated = True
                    elif last_stmt.name in self.globals:
                        # Fall back to global
                        # ZIL0204: no such local variable 'X', using the global instead
                        self._warn(f"ZIL0204: no such local variable '{last_stmt.name}', using the global instead")
                        var_num = self.globals[last_stmt.name]
                        routine_code.append(0xAB)  # RET variable
                        routine_code.append(var_num)
                        implicit_ret_generated = True
                    elif last_stmt.name in self.constants:
                        # Fall back to constant
                        # ZIL0204: no such local variable 'X', using the constant instead
                        self._warn(f"ZIL0204: no such local variable '{last_stmt.name}', using the constant instead")
                        val = self.constants[last_stmt.name]
                        if 0 <= val <= 255:
                            routine_code.append(0x9B)  # RET small constant
                            routine_code.append(val & 0xFF)
                        else:
                            routine_code.append(0x8B)  # RET large constant
                            routine_code.append((val >> 8) & 0xFF)
                            routine_code.append(val & 0xFF)
                        implicit_ret_generated = True
                    elif last_stmt.name in self.objects:
                        # Fall back to object
                        # ZIL0204: no such local variable 'X', using the object instead
                        self._warn(f"ZIL0204: no such local variable '{last_stmt.name}', using the object instead")
                        obj_num = self.objects[last_stmt.name]
                        if 0 <= obj_num <= 255:
                            routine_code.append(0x9B)  # RET small constant
                            routine_code.append(obj_num & 0xFF)
                        else:
                            routine_code.append(0x8B)  # RET large constant
                            routine_code.append((obj_num >> 8) & 0xFF)
                            routine_code.append(obj_num & 0xFF)
                        implicit_ret_generated = True
                    else:
                        # Unknown, default to returning local 1
                        routine_code.append(0xAB)  # RET variable
                        routine_code.append(1)
                        implicit_ret_generated = True
                elif isinstance(last_stmt, GlobalVarNode):
                    # Return the global variable
                    var_num = self.globals.get(last_stmt.name, 0x10)
                    routine_code.append(0xAB)  # RET variable
                    routine_code.append(var_num)
                    implicit_ret_generated = True
                elif isinstance(last_stmt, NumberNode):
                    # Return the number
                    val = last_stmt.value
                    if 0 <= val <= 255:
                        routine_code.append(0x9B)  # RET small const
                        routine_code.append(val)
                    else:
                        routine_code.append(0x8B)  # RET large const
                        routine_code.append((val >> 8) & 0xFF)
                        routine_code.append(val & 0xFF)
                    implicit_ret_generated = True
                elif isinstance(last_stmt, FormNode):
                    # Check if it's a void operation that doesn't push a value
                    op_name = last_stmt.operator.value.upper() if isinstance(last_stmt.operator, AtomNode) else ''
                    void_ops = {
                        'PRINTI', 'PRINT', 'PRINTR', 'PRINTC', 'PRINTB', 'PRINTD',
                        'PRINTN', 'PRINTT', 'PRINTU', 'CRLF', 'TELL',
                        'MOVE', 'REMOVE', 'SET', 'SETG', 'PUTP', 'PUTB', 'PUT',
                        'QUIT', 'RESTART', 'CLEAR', 'SCREEN', 'ERASE', 'COLOR',
                        'SPLIT', 'HLIGHT', 'CURSET', 'CURGET', 'DIROUT', 'DIRIN',
                        'BUFOUT', 'DISPLAY', 'THROW', 'COPYT', 'COPY-TABLE'
                    }
                    if op_name == '<>':
                        # Empty form <> evaluates to FALSE (0)
                        # Return 0 (false) instead of RET_POPPED since <> doesn't push
                        routine_code.append(0x9B)  # RET small constant
                        routine_code.append(0x00)  # Return 0 (false)
                    elif op_name in void_ops:
                        # Void operation - use RET 1 (success/true)
                        routine_code.append(0x9B)
                        routine_code.append(0x01)
                    else:
                        # The expression pushed its result to the stack
                        # Use RET_POPPED to return that value
                        routine_code.append(0xB8)  # RET_POPPED
                    implicit_ret_generated = True
                elif isinstance(last_stmt, CondNode):
                    # COND pushes its result to the stack
                    # Use RET_POPPED to return that value
                    routine_code.append(0xB8)  # RET_POPPED
                    implicit_ret_generated = True
                elif isinstance(last_stmt, AtomNode):
                    # Atom as final statement - return its value
                    # Constants like T (true), FALSE, or user-defined constants
                    atom_val = last_stmt.value
                    if atom_val in self.constants:
                        val = self.constants[atom_val]
                        if 0 <= val <= 255:
                            routine_code.append(0x9B)  # RET small constant
                            routine_code.append(val & 0xFF)
                        else:
                            routine_code.append(0x8B)  # RET large constant
                            routine_code.append((val >> 8) & 0xFF)
                            routine_code.append(val & 0xFF)
                        implicit_ret_generated = True
                    elif atom_val in self.objects:
                        obj_num = self.objects[atom_val]
                        if 0 <= obj_num <= 255:
                            routine_code.append(0x9B)  # RET small constant
                            routine_code.append(obj_num & 0xFF)
                        else:
                            routine_code.append(0x8B)  # RET large constant
                            routine_code.append((obj_num >> 8) & 0xFF)
                            routine_code.append(obj_num & 0xFF)
                        implicit_ret_generated = True
                    elif atom_val in self.globals:
                        var_num = self.globals[atom_val]
                        routine_code.append(0xAB)  # RET variable
                        routine_code.append(var_num)
                        implicit_ret_generated = True

            if not implicit_ret_generated:
                # Use RET 0 instead of RET_POPPED for predictable behavior
                # RET_POPPED from an empty stack has undefined behavior in some interpreters
                # RET is 1OP opcode 0x0B
                # 0x9B = 10 01 1011 = 1OP short with small constant, opcode 0x0B
                routine_code.append(0x9B)  # RET small constant
                routine_code.append(0x00)  # Return value 0

        # Patch routine header if PROG/BIND added more locals
        if hasattr(self, 'max_local_slot') and self.max_local_slot > num_locals:
            # Update local count in header byte
            routine_code[0] = self.max_local_slot & 0x0F

            # For V1-4, we need to insert initial values for the additional locals
            if self.version <= 4:
                # Calculate where to insert: after existing initial values
                # Header is 1 byte + 2 bytes per original local
                insert_pos = 1 + 2 * num_locals
                # Add initial values (0x0000) for each new local
                extra_locals = self.max_local_slot - num_locals
                bytes_inserted = extra_locals * 2
                for _ in range(extra_locals):
                    routine_code.insert(insert_pos, 0x00)
                    routine_code.insert(insert_pos, 0x00)
                    insert_pos += 2

                # Adjust pending placeholder positions by the number of bytes inserted
                # All positions after insert_pos (which was right after the original header)
                # need to be shifted forward
                adjusted = []
                for rel_offset, placeholder_idx in self._pending_placeholders:
                    # Placeholders after the insertion point need adjustment
                    if rel_offset >= (1 + 2 * num_locals):
                        adjusted.append((rel_offset + bytes_inserted, placeholder_idx))
                    else:
                        adjusted.append((rel_offset, placeholder_idx))
                self._pending_placeholders = adjusted

        # Pop routine loop context and patch AGAIN placeholders
        if hasattr(self, 'loop_stack') and self.loop_stack:
            routine_loop_ctx = self.loop_stack.pop()
            if routine_loop_ctx.get('loop_type') == 'ROUTINE':
                # Patch all routine-level AGAIN placeholders (0x8C 0xFF 0xAC -> jump to routine_init_start)
                # Note: We use 0xAC for routine-level AGAIN (vs 0xAA for block-level)
                i = 0
                while i < len(routine_code) - 2:
                    if routine_code[i] == 0x8C and routine_code[i+1] == 0xFF and routine_code[i+2] == 0xAC:
                        # Found routine-level AGAIN placeholder at position i
                        # Z-machine JUMP: Target = PC + Offset - 2
                        # PC after JUMP = i + 3, so Offset = Target - (i + 3) + 2 = Target - i - 1
                        again_offset = routine_init_start - (i + 1)
                        if again_offset < 0:
                            again_offset_unsigned = (1 << 16) + again_offset
                        else:
                            again_offset_unsigned = again_offset
                        routine_code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                        routine_code[i+2] = again_offset_unsigned & 0xFF
                    i += 1

        # Store routine address for later reference
        self.routines[routine.name] = routine_start

        # Adjust pending placeholder positions to absolute offsets
        # and move them to the final positions list
        base_offset = len(self.code)
        for rel_offset, placeholder_idx in self._pending_placeholders:
            self._placeholder_positions.append((base_offset + rel_offset, placeholder_idx))
        self._pending_placeholders.clear()

        # Check for unused routine-level locals (ZIL0210)
        if hasattr(self, 'routine_level_locals') and self.compiler is not None:
            for local_name in self.routine_level_locals:
                if (local_name not in self.used_locals and
                        local_name not in self.locals_with_side_effect_init):
                    self.compiler.warn("ZIL0210", f"local variable '{local_name}' is never used")

        self.code.extend(routine_code)
        return bytes(routine_code)

    def _ends_with_terminator(self, body: List[ASTNode]) -> bool:
        """Check if a routine body ends with a terminating instruction."""
        if not body:
            return False

        last_stmt = body[-1]

        if isinstance(last_stmt, FormNode) and isinstance(last_stmt.operator, AtomNode):
            op_name = last_stmt.operator.value.upper()
            # These operations terminate the routine or loop
            if op_name in ('RTRUE', 'RFALSE', 'RETURN', 'QUIT', 'RESTART', 'AGAIN', 'RFATAL'):
                return True

        # COND might terminate if all branches terminate
        if isinstance(last_stmt, CondNode):
            # Check if COND has a T clause and all branches terminate
            # For now, be conservative and say COND doesn't terminate
            pass

        return False

    def generate_statement(self, node: ASTNode) -> bytes:
        """Generate code for a statement."""
        if isinstance(node, FormNode):
            return self.generate_form(node)
        elif isinstance(node, CondNode):
            return self.generate_cond(node)
        elif isinstance(node, RepeatNode):
            return self.generate_repeat(node)
        elif isinstance(node, TableNode):
            # Standalone table - generate and return address
            return self.generate_table_node(node)
        elif isinstance(node, LocalVarNode):
            # Mark local as used (for ZIL0210 warning tracking)
            if hasattr(self, 'used_locals'):
                self.used_locals.add(node.name)
            return b''
        elif isinstance(node, AtomNode):
            # Standalone atom - evaluate and potentially push to stack
            return b''
        elif isinstance(node, NumberNode):
            return b''
        elif isinstance(node, StringNode):
            return b''
        else:
            return b''

    def generate_form(self, form: FormNode) -> bytes:
        """Generate code for a form (function call)."""
        if not isinstance(form.operator, AtomNode):
            return b''

        op_name = form.operator.value.upper()

        # Control flow
        if op_name == 'RTRUE':
            if form.operands:
                raise ValueError("RTRUE takes no operands")
            return self.gen_rtrue()
        elif op_name == 'RFALSE':
            if form.operands:
                raise ValueError("RFALSE takes no operands")
            return self.gen_rfalse()
        elif op_name == '<>':
            # <> evaluates to FALSE (0) but does NOT return from routine
            # When used as a statement, it's a no-op
            # When used as an expression/value, the caller handles it via _get_operand_type_and_value
            if form.operands:
                raise ValueError("<> takes no operands")
            return b''  # No-op when used as a statement
        elif op_name == 'RFATAL':
            if form.operands:
                raise ValueError("RFATAL takes no operands")
            return self.gen_rfatal()
        elif op_name == 'RETURN':
            return self.gen_return(form.operands)
        elif op_name == 'QUIT':
            if form.operands:
                raise ValueError("QUIT takes no operands")
            return self.gen_quit()
        elif op_name == 'AGAIN':
            return self.gen_again(form.operands)
        elif op_name == 'GOTO':
            return self.gen_goto(form.operands)
        elif op_name == 'PROG':
            return self.gen_prog(form.operands)
        elif op_name == 'REPEAT':
            return self.gen_repeat(form.operands)
        elif op_name == 'BIND':
            return self.gen_bind(form.operands)
        elif op_name == 'DO':
            return self.gen_do(form.operands)
        elif op_name == 'MAP-CONTENTS':
            return self.gen_map_contents(form.operands)
        elif op_name == 'MAP-DIRECTIONS':
            return self.gen_map_directions(form.operands)

        # Output
        elif op_name == 'TELL':
            return self.gen_tell(form.operands)
        elif op_name == 'PRINT':
            if not form.operands:
                raise ValueError("PRINT requires at least 1 operand")
            return self.gen_tell(form.operands)
        elif op_name == 'CRLF':
            if form.operands:
                raise ValueError("CRLF takes no operands")
            return self.gen_newline()
        elif op_name == 'PRINTN' or op_name == 'PRINT-NUM':
            return self.gen_print_num(form.operands)
        elif op_name == 'PRINTD':
            if len(form.operands) != 1:
                raise ValueError("PRINTD requires exactly 1 operand")
            return self.gen_printobj(form.operands)
        elif op_name == 'PRINTC' or op_name == 'PRINT-CHAR':
            return self.gen_print_char(form.operands)
        elif op_name == 'PRINTB':
            return self.gen_printb(form.operands)
        elif op_name == 'PRINTI':
            if len(form.operands) != 1:
                raise ValueError("PRINTI requires exactly 1 operand")
            return self.gen_printi(form.operands)
        elif op_name == 'PRINTADDR':
            return self.gen_printaddr(form.operands)
        elif op_name == 'STRING':
            return self.gen_string(form.operands)

        # Variables
        elif op_name == 'SET':
            return self.gen_set(form.operands, is_global=False)
        elif op_name == 'SETG':
            return self.gen_set(form.operands, is_global=True)
        elif op_name == 'INC':
            return self.gen_inc(form.operands)
        elif op_name == 'DEC':
            return self.gen_dec(form.operands)
        elif op_name == 'VALUE':
            return self.gen_value(form.operands)
        elif op_name == 'LVAL':
            return self.gen_lval(form.operands)
        elif op_name == 'GVAL':
            return self.gen_gval(form.operands)

        # Arithmetic
        elif op_name in ('+', 'ADD'):
            return self.gen_add(form.operands)
        elif op_name in ('-', 'SUB'):
            return self.gen_sub(form.operands)
        elif op_name in ('*', 'MUL'):
            return self.gen_mul(form.operands)
        elif op_name in ('/', 'DIV'):
            return self.gen_div(form.operands)
        elif op_name == 'MOD':
            return self.gen_mod(form.operands)
        elif op_name == '1+':
            return self.gen_add1(form.operands)
        elif op_name == '1-':
            return self.gen_sub1(form.operands)
        elif op_name == 'MIN':
            return self.gen_min(form.operands)
        elif op_name == 'MAX':
            return self.gen_max(form.operands)
        elif op_name == 'ABS':
            return self.gen_abs(form.operands)
        elif op_name == 'SOUND':
            return self.gen_sound(form.operands)
        elif op_name == 'CLEAR':
            return self.gen_clear(form.operands)
        elif op_name == 'ERASE':
            return self.gen_erase(form.operands)
        elif op_name == 'SPLIT':
            return self.gen_split(form.operands)
        elif op_name == 'SCREEN':
            return self.gen_screen(form.operands)
        elif op_name == 'CURSET':
            return self.gen_curset(form.operands)
        elif op_name == 'CURGET':
            return self.gen_get_cursor(form.operands)
        elif op_name == 'HLIGHT':
            return self.gen_hlight(form.operands)
        elif op_name == 'COLOR':
            return self.gen_color(form.operands)
        elif op_name == 'FONT':
            return self.gen_font(form.operands)
        elif op_name == 'INPUT':
            return self.gen_input(form.operands)
        elif op_name == 'BUFOUT':
            return self.gen_bufout(form.operands)
        elif op_name == 'UXOR':
            return self.gen_uxor(form.operands)
        elif op_name == 'USL':
            return self.gen_usl(form.operands)
        elif op_name == 'DIROUT':
            return self.gen_dirout(form.operands)
        elif op_name == 'DIRIN':
            return self.gen_input_stream(form.operands)
        elif op_name == 'PRINTOBJ':
            return self.gen_printobj(form.operands)
        elif op_name == 'READ':
            return self.gen_read(form.operands)
        elif op_name == 'MAPF':
            return self.gen_mapf(form.operands)
        elif op_name == 'MAPT':
            return self.gen_mapt(form.operands)
        elif op_name == 'MAPR':
            return self.gen_mapr(form.operands)

        # Type system (MDL constructs)
        elif op_name == 'NEWTYPE':
            return self.gen_newtype(form.operands)
        elif op_name == 'CHTYPE':
            return self.gen_chtype(form.operands)
        elif op_name == 'PRIMTYPE':
            return self.gen_primtype(form.operands)

        # Comparison
        elif op_name in ('=', 'EQUAL?', '==?', '=?'):
            return self.gen_equal(form.operands)
        elif op_name in ('L?', '<', 'LESS?'):
            return self.gen_less(form.operands)
        elif op_name in ('G?', '>', 'GRTR?'):
            return self.gen_greater(form.operands)
        elif op_name in ('ZERO?', '0?'):
            return self.gen_zero_test(form.operands)
        elif op_name == '1?':
            return self.gen_one(form.operands)
        elif op_name == 'ASSIGNED?':
            return self.gen_assigned(form.operands)
        elif op_name == 'NOT?':
            return self.gen_not_predicate(form.operands)
        elif op_name == 'TRUE?' or op_name == 'T?':
            return self.gen_true_predicate(form.operands)
        elif op_name == 'IGRTR?':
            return self.gen_igrtr(form.operands)
        elif op_name == 'DLESS?':
            return self.gen_dless(form.operands)
        elif op_name == 'CHECKU':
            return self.gen_checku(form.operands)
        elif op_name == 'LEXV':
            return self.gen_lexv(form.operands)
        elif op_name in ('G=?', 'GEQ?', '>='):
            return self.gen_grtr_or_equal(form.operands)
        elif op_name in ('L=?', 'LEQ?', '<='):
            return self.gen_less_or_equal(form.operands)
        elif op_name in ('N=?', 'NEQUAL?', '!='):
            return self.gen_nequal(form.operands)
        elif op_name == 'ZGET':
            return self.gen_zget(form.operands)
        elif op_name == 'ZPUT':
            return self.gen_zput(form.operands)
        elif op_name == 'ORIGINAL?':
            return self.gen_original(form.operands)
        elif op_name == 'TEST-BIT':
            return self.gen_test_bit(form.operands)
        elif op_name == 'WINSIZE':
            return self.gen_winsize(form.operands)
        elif op_name == 'COLOR':
            return self.gen_color(form.operands)
        elif op_name == 'FONT':
            return self.gen_font(form.operands)
        elif op_name == 'FIRST':
            return self.gen_first(form.operands)
        elif op_name == 'MEMBER':
            return self.gen_member(form.operands)
        elif op_name == 'MEMQ':
            return self.gen_memq(form.operands)
        elif op_name == 'GETB2':
            return self.gen_getb2(form.operands)
        elif op_name == 'PUTB2':
            return self.gen_putb2(form.operands)
        elif op_name == 'GETW2':
            return self.gen_getw2(form.operands)
        elif op_name == 'PUTW2':
            return self.gen_putw2(form.operands)
        elif op_name == 'LOWCORE':
            return self.gen_lowcore(form.operands)
        elif op_name == 'SCREEN-HEIGHT':
            return self.gen_screen_height(form.operands)
        elif op_name == 'SCREEN-WIDTH':
            return self.gen_screen_width(form.operands)
        elif op_name == 'ASR':
            return self.gen_asr(form.operands)
        elif op_name == 'NEW-LINE':
            return self.gen_new_line(form.operands)
        elif op_name == 'CATCH':
            return self.gen_catch(form.operands)
        elif op_name == 'THROW':
            return self.gen_throw(form.operands)
        elif op_name == 'SPACES':
            return self.gen_spaces(form.operands)
        elif op_name == 'BACK':
            return self.gen_back(form.operands)
        elif op_name == 'DISPLAY':
            return self.gen_display(form.operands)
        elif op_name == 'SCORE':
            return self.gen_score(form.operands)
        elif op_name == 'CHRSET':
            return self.gen_chrset(form.operands)
        elif op_name == 'MARGIN':
            return self.gen_margin(form.operands)
        elif op_name == 'WINGET':
            return self.gen_winget(form.operands)
        elif op_name == 'WINPUT':
            return self.gen_winput(form.operands)
        elif op_name == 'WINATTR':
            return self.gen_winattr(form.operands)
        elif op_name == 'WINPOS':
            return self.gen_winpos(form.operands)
        elif op_name == 'SET-COLOUR':
            return self.gen_set_colour(form.operands)
        elif op_name == 'SET-TRUE-COLOUR':
            return self.gen_set_true_colour(form.operands)
        elif op_name == 'ERASE-WINDOW':
            return self.gen_erase_window(form.operands)
        elif op_name == 'SPLIT-WINDOW':
            return self.gen_split_window(form.operands)
        elif op_name == 'SET-WINDOW':
            return self.gen_set_window(form.operands)
        elif op_name == 'SET-FONT':
            return self.gen_font(form.operands)
        elif op_name == 'BUFFER-MODE':
            return self.gen_bufout(form.operands)
        elif op_name == 'SET-CURSOR':
            return self.gen_curset(form.operands)
        elif op_name == 'GET-CURSOR':
            return self.gen_get_cursor(form.operands)
        elif op_name == 'SET-TEXT-STYLE':
            return self.gen_hlight(form.operands)
        elif op_name == 'ERASE-LINE':
            return self.gen_erase_line(form.operands)
        elif op_name == 'MOVE-WINDOW':
            return self.gen_move_window(form.operands)
        elif op_name == 'WINDOW-SIZE':
            return self.gen_window_size(form.operands)
        elif op_name == 'WINDOW-STYLE':
            return self.gen_winattr(form.operands)
        elif op_name == 'SCROLL-WINDOW' or op_name == 'SCROLL':
            return self.gen_scroll_window(form.operands)
        elif op_name == 'PICINF':
            return self.gen_picinf(form.operands)
        elif op_name == 'PICSET':
            return self.gen_picset(form.operands)
        elif op_name == 'MOUSE-INFO':
            return self.gen_mouse_info(form.operands)
        elif op_name == 'MOUSE-LIMIT':
            return self.gen_mouse_limit(form.operands)
        elif op_name == 'MENU':
            return self.gen_make_menu(form.operands)
        elif op_name == 'PRINTF':
            return self.gen_print_form(form.operands)
        elif op_name == 'TYPE?':
            return self.gen_type(form.operands)
        elif op_name == 'PRINTTYPE':
            return self.gen_printtype(form.operands)
        elif op_name == 'PRINTT':
            if self.version < 5:
                raise ValueError("PRINTT requires V5 or later")
            if len(form.operands) < 2 or len(form.operands) > 4:
                raise ValueError("PRINTT requires 2-4 operands")
            return self.gen_printt(form.operands)
        elif op_name == 'PRINTR':
            if len(form.operands) != 1:
                raise ValueError("PRINTR requires exactly 1 operand")
            if not isinstance(form.operands[0], StringNode):
                raise ValueError("PRINTR requires a string operand")
            return self.gen_printr(form.operands)
        elif op_name == 'FSTACK':
            return self.gen_fstack(form.operands)
        elif op_name == 'RSTACK':
            return self.gen_rstack(form.operands)
        elif op_name == 'IFFLAG':
            return self.gen_ifflag(form.operands)
        elif op_name == 'LOG-SHIFT':
            return self.gen_log_shift(form.operands)
        elif op_name in ('XOR', 'XORB'):
            return self.gen_xor(form.operands)
        elif op_name == 'MUSIC':
            return self.gen_music(form.operands)
        elif op_name == 'VOLUME':
            return self.gen_volume(form.operands)
        elif op_name == 'COPYT':
            return self.gen_copyt(form.operands)
        elif op_name == 'COPY-TABLE':
            return self.gen_copyt(form.operands)
        elif op_name == 'ZERO':
            return self.gen_zero(form.operands)
        elif op_name == 'ZERO-TABLE':
            return self.gen_zero(form.operands)
        elif op_name == 'SHIFT':
            return self.gen_shift(form.operands)
        elif op_name in ('ASH', 'ASHIFT', 'ART-SHIFT'):
            return self.gen_art_shift(form.operands)
        elif op_name == 'LSH':
            return self.gen_shift(form.operands)

        # V5+ Unicode operations
        elif op_name == 'PRINT-UNICODE':
            return self.gen_print_unicode(form.operands)
        elif op_name == 'PRINTU':
            if self.version < 5:
                raise ValueError("PRINTU requires V5 or later")
            if len(form.operands) != 1:
                raise ValueError("PRINTU requires exactly 1 operand")
            return self.gen_print_unicode(form.operands)
        elif op_name == 'CHECK-UNICODE':
            return self.gen_check_unicode(form.operands)

        # Table searching
        elif op_name == 'INTBL?':
            return self.gen_intbl(form.operands)
        elif op_name == 'IN-TABLE?':
            return self.gen_intbl(form.operands)
        elif op_name == 'SCAN-TABLE':
            return self.gen_intbl(form.operands)
        elif op_name == 'CHECK':
            return self.gen_check(form.operands)

        # Picture operations (V6)
        elif op_name == 'DRAW-PICTURE':
            return self.gen_draw_picture(form.operands)
        elif op_name == 'ERASE-PICTURE':
            return self.gen_erase_picture(form.operands)
        elif op_name == 'PICTURE-TABLE':
            return self.gen_picture_table(form.operands)

        # Logical
        elif op_name == 'AND':
            return self.gen_and(form.operands)
        elif op_name == 'OR':
            return self.gen_or(form.operands)
        elif op_name == 'AND?':
            return self.gen_and_pred(form.operands)
        elif op_name == 'OR?':
            return self.gen_or_pred(form.operands)
        elif op_name == 'NOT':
            return self.gen_not(form.operands)
        elif op_name == 'BCOM':
            # BCOM is bitwise complement
            return self.gen_bcom(form.operands)
        elif op_name in ('BAND', 'ANDB'):
            return self.gen_band(form.operands)
        elif op_name in ('BOR', 'ORB'):
            return self.gen_bor(form.operands)
        elif op_name == 'BTST':
            return self.gen_btst(form.operands)
        elif op_name == 'LSH':
            return self.gen_lsh(form.operands)
        elif op_name == 'RSH':
            return self.gen_rsh(form.operands)

        # Objects
        elif op_name == 'FSET':
            return self.gen_fset(form.operands)
        elif op_name == 'FCLEAR':
            return self.gen_fclear(form.operands)
        elif op_name == 'FSET?':
            return self.gen_fset_test(form.operands)
        elif op_name == 'MOVE':
            return self.gen_move(form.operands)
        elif op_name == 'REMOVE':
            return self.gen_remove(form.operands)
        elif op_name == 'LOC':
            return self.gen_loc(form.operands)

        # Properties
        elif op_name == 'GETP':
            return self.gen_getp(form.operands)
        elif op_name == 'PUTP':
            return self.gen_putp(form.operands)
        elif op_name == 'PTSIZE':
            return self.gen_ptsize(form.operands)
        elif op_name == 'NEXTP':
            return self.gen_nextp(form.operands)
        elif op_name == 'GETPT':
            return self.gen_getpt(form.operands)

        # Conditionals (these create branch instructions)
        elif op_name == 'COND':
            if form.operands and isinstance(form.operands[0], CondNode):
                return self.generate_cond(form.operands[0])
            else:
                # COND may have macro-expanded clauses
                # Convert operands to COND clauses
                clauses = []
                for operand in form.operands:
                    clause = self._extract_cond_clause(operand)
                    if clause is not None:
                        clauses.append(clause)

                if clauses:
                    # Create CondNode and generate
                    cond_node = CondNode(clauses, form.line, form.column)
                    return self.generate_cond(cond_node)
                else:
                    # All clauses were empty - return empty
                    return []

        # Memory operations
        elif op_name == 'LOADW':
            return self.gen_loadw(form.operands)
        elif op_name == 'LOADB':
            return self.gen_loadb(form.operands)
        elif op_name == 'STOREW':
            return self.gen_storew(form.operands)
        elif op_name == 'STOREB':
            return self.gen_storeb(form.operands)

        # Table operations (higher-level)
        elif op_name == 'GET':
            return self.gen_get(form.operands)
        elif op_name == 'PUT':
            return self.gen_put(form.operands)
        elif op_name == 'GETB':
            return self.gen_getb(form.operands)
        elif op_name == 'PUTB':
            return self.gen_putb(form.operands)
        elif op_name == 'LENGTH':
            return self.gen_length(form.operands)
        elif op_name == 'NTH':
            return self.gen_nth(form.operands)

        # Stack operations
        elif op_name == 'PUSH':
            return self.gen_push(form.operands)
        elif op_name == 'PULL':
            return self.gen_pull(form.operands)
        elif op_name == 'POP':
            return self.gen_pop(form.operands)
        elif op_name == 'XPUSH':
            return self.gen_xpush(form.operands)

        # Object tree
        elif op_name == 'GET-CHILD' or op_name == 'FIRST?':
            return self.gen_get_child(form.operands)
        elif op_name == 'GET-SIBLING' or op_name == 'NEXT?':
            return self.gen_get_sibling(form.operands)
        elif op_name == 'GET-PARENT':
            return self.gen_get_parent(form.operands)
        elif op_name == 'EMPTY?':
            return self.gen_empty(form.operands)
        elif op_name == 'IN?':
            return self.gen_in(form.operands)
        elif op_name == 'HELD?':
            return self.gen_held(form.operands)

        # Random and utilities
        elif op_name == 'RANDOM':
            return self.gen_random(form.operands)
        elif op_name == 'PROB':
            return self.gen_prob(form.operands)
        elif op_name == 'PICK-ONE':
            return self.gen_pick_one(form.operands)
        elif op_name == 'RESTART':
            if form.operands:
                raise ValueError("RESTART takes no operands")
            return self.gen_restart()
        elif op_name == 'SAVE':
            return self.gen_save(form.operands)
        elif op_name == 'RESTORE':
            return self.gen_restore(form.operands)
        elif op_name == 'VERIFY':
            if form.operands:
                raise ValueError("VERIFY takes no operands")
            return self.gen_verify()
        elif op_name == 'GOTO':
            return self.gen_goto(form.operands)

        # Parser predicates
        elif op_name == 'VERB?':
            return self.gen_verb_test(form.operands)
        elif op_name == 'PERFORM':
            return self.gen_perform(form.operands)
        elif op_name == 'CALL':
            return self.gen_call(form.operands)
        elif op_name == 'APPLY':
            return self.gen_apply(form.operands)

        # Daemon/Interrupt system
        # NOTE: QUEUE, INT, DEQUEUE, ENABLE, DISABLE are typically implemented
        # as ZIL library routines (see gclock.zil, events.zil), not compiler built-ins.
        # If the user has defined these routines, use them instead of the built-ins.
        # The built-in implementations are problematic because they store data in
        # static memory, which cannot be modified at runtime.
        # We check _routine_names (populated before generation) rather than
        # self.routines (populated during generation) to handle forward references.
        elif op_name == 'QUEUE':
            if hasattr(self, '_routine_names') and 'QUEUE' in self._routine_names:
                return self.gen_routine_call('QUEUE', form.operands)
            return self.gen_queue(form.operands)
        elif op_name == 'INT':
            if hasattr(self, '_routine_names') and 'INT' in self._routine_names:
                return self.gen_routine_call('INT', form.operands)
            return self.gen_int(form.operands)
        elif op_name == 'DEQUEUE':
            if hasattr(self, '_routine_names') and 'DEQUEUE' in self._routine_names:
                return self.gen_routine_call('DEQUEUE', form.operands)
            return self.gen_dequeue(form.operands)
        elif op_name == 'ENABLE':
            if hasattr(self, '_routine_names') and 'ENABLE' in self._routine_names:
                return self.gen_routine_call('ENABLE', form.operands)
            return self.gen_enable(form.operands)
        elif op_name == 'DISABLE':
            if hasattr(self, '_routine_names') and 'DISABLE' in self._routine_names:
                return self.gen_routine_call('DISABLE', form.operands)
            return self.gen_disable(form.operands)

        # List/table operations
        elif op_name == 'REST':
            return self.gen_rest(form.operands)

        # Game control
        elif op_name == 'JIGS-UP':
            return self.gen_jigs_up(form.operands)

        # Parser/lexer operations (V5+ aliases)
        elif op_name == 'LEX':
            return self.gen_tokenise(form.operands)
        elif op_name == 'PARSE':
            return self.gen_tokenise(form.operands)
        elif op_name == 'TOKENIZE':
            return self.gen_tokenise(form.operands)

        # Extended call forms (V5+)
        elif op_name == 'CALL-VS2':
            return self.gen_call_vs2(form.operands)
        elif op_name == 'CALL-VN2':
            return self.gen_call_vn2(form.operands)
        elif op_name == 'CALL-1S':
            return self.gen_call_1s(form.operands)
        elif op_name == 'CALL-1N':
            return self.gen_call_1n(form.operands)
        elif op_name == 'CALL-2S':
            return self.gen_call_2s(form.operands)
        elif op_name == 'CALL-2N':
            return self.gen_call_2n(form.operands)

        # Undo operations (V5+)
        elif op_name == 'SAVE-UNDO':
            return self.gen_save_undo(form.operands)
        elif op_name == 'RESTORE-UNDO':
            return self.gen_restore_undo(form.operands)
        elif op_name == 'ISAVE':
            return self.gen_save_undo(form.operands)
        elif op_name == 'IRESTORE':
            return self.gen_restore_undo(form.operands)
        elif op_name == 'ORIGINAL?':
            return self.gen_original(form.operands)
        elif op_name == 'INTBL?':
            return self.gen_intbl(form.operands)
        elif op_name == 'ZWSTR':
            return self.gen_zwstr(form.operands)

        # Table operations
        elif op_name == 'TABLE':
            return self.gen_table(form.operands, table_type='TABLE')
        elif op_name == 'LTABLE':
            return self.gen_table(form.operands, table_type='LTABLE')
        elif op_name == 'ITABLE':
            return self.gen_table(form.operands, table_type='ITABLE')
        elif op_name == 'PTABLE':
            return self.gen_table(form.operands, table_type='PTABLE')
        elif op_name == 'REST':
            return self.gen_rest(form.operands)

        # Routine calls - check if it's a routine name
        elif isinstance(form.operator, AtomNode):
            if form.operator.value in self.routines or form.operator.value.isupper():
                # Likely a routine call
                return self.gen_routine_call(form.operator.value, form.operands)

        # Unrecognized operation - warn and return empty
        self._warn(f"Unrecognized operation '{op_name}' - no code generated")
        return b''

    # ===== Table Node Helpers =====

    def _encode_table_values(self, values: List[ASTNode], default_is_byte: bool = False,
                              is_string: bool = False) -> bytearray:
        """Encode table values to bytes, handling #BYTE and #WORD prefixes.

        In ZIL/MDL, #BYTE value stores value as a single byte,
        and #WORD value stores value as a 2-byte word.

        Args:
            values: List of AST nodes to encode
            default_is_byte: If True, values without prefix are stored as bytes
            is_string: If True, strings are encoded as raw character bytes

        Returns:
            bytearray: Encoded table data
        """
        table_data = bytearray()
        i = 0
        while i < len(values):
            val = values[i]

            # Check for #BYTE prefix atom
            if isinstance(val, AtomNode) and val.value.upper() == '#BYTE':
                # Next value should be stored as a byte
                i += 1
                if i < len(values):
                    next_val = values[i]
                    val_int = self._get_table_value_int(next_val)
                    table_data.append(val_int & 0xFF)
                i += 1
                continue

            # Check for #WORD prefix atom
            if isinstance(val, AtomNode) and val.value.upper() == '#WORD':
                # Next value should be stored as a word
                i += 1
                if i < len(values):
                    next_val = values[i]
                    val_int = self._get_table_value_int(next_val)
                    table_data.extend(struct.pack('>H', val_int & 0xFFFF))
                i += 1
                continue

            # Handle STRING mode - strings become raw character bytes
            if is_string and isinstance(val, StringNode):
                for char in val.value:
                    table_data.append(ord(char) & 0xFF)
                i += 1
                continue

            # Regular value
            val_int = self._get_table_value_int(val)
            if default_is_byte:
                table_data.append(val_int & 0xFF)
            else:
                table_data.extend(struct.pack('>H', val_int & 0xFFFF))
            i += 1

        return table_data

    def _unwrap_list_value(self, val) -> ASTNode:
        """Unwrap a list containing a single value, e.g., (12345) -> NumberNode(12345)."""
        if isinstance(val, list) and len(val) == 1:
            return val[0]
        return val

    def _get_table_value_int(self, val) -> int:
        """Get integer value from a table element AST node.

        Handles NumberNode, AtomNode (for object/routine/global references),
        StringNode (returns 0 placeholder), FormNode with parenthesized values,
        and lists (for parenthesized values like (12345)).
        """
        # Handle list (parenthesized value like (12345) becomes [NumberNode(12345)])
        if isinstance(val, list):
            if len(val) == 1:
                return self._get_table_value_int(val[0])
            return 0

        # Handle parenthesized value like (12345) as FormNode
        if isinstance(val, FormNode):
            # Check if it's just a parenthesized number
            if not val.operands and isinstance(val.operator, NumberNode):
                return val.operator.value
            # Otherwise try to get operand value
            return self.get_operand_value(val) or 0

        val_int = self.get_operand_value(val)
        if val_int is not None:
            return val_int

        if isinstance(val, AtomNode):
            name = val.value
            if name in self.objects:
                return self.objects[name]
            elif name in self.routines:
                return self.routines[name]
            elif name in self.globals:
                return self.globals[name]
            elif name in self.constants:
                return self.constants[name]
            else:
                return 0
        elif isinstance(val, StringNode):
            return 0  # Placeholder for string
        else:
            return 0

    def _add_table(self, node: TableNode) -> int:
        """Add a table from a TableNode and return its index.

        Args:
            node: TableNode with table_type, flags, size, values

        Returns:
            int: Table index (placeholder for later address resolution)
        """
        # Check for local variable references - tables must have compile-time constant values
        for val in node.values:
            if self._contains_local_var(val):
                raise ValueError(f"Table cannot reference local variables - values must be compile-time constants")

        table_data = bytearray()
        table_type = node.table_type
        is_pure = 'PURE' in node.flags
        is_byte = 'BYTE' in node.flags
        is_string = 'STRING' in node.flags
        if is_string:
            is_byte = True  # STRING implies BYTE mode

        # For LTABLE, add length prefix
        if table_type == 'LTABLE':
            table_data.extend(struct.pack('>H', len(node.values)))

        # Handle ITABLE with repeat count
        if node.size and table_type == 'ITABLE' and node.values:
            # ITABLE with size and values: repeat pattern 'size' times
            pattern_data = self._encode_table_values(node.values, default_is_byte=is_byte,
                                                      is_string=is_string)
            for _ in range(node.size):
                table_data.extend(pattern_data)
        elif node.size and table_type == 'ITABLE':
            # ITABLE with just size: create zero-filled table
            entry_size = 1 if is_byte else 2
            for _ in range(node.size):
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))
        else:
            # Encode values using helper that handles #BYTE/#WORD prefixes
            table_data.extend(self._encode_table_values(node.values, default_is_byte=is_byte,
                                                         is_string=is_string))

        # Store table and track offset
        table_id = f"_TABLE_{self.table_counter}"
        table_index = len(self.tables)
        self.table_offsets[table_index] = self._table_data_size
        self._table_data_size += len(table_data)
        self.table_counter += 1
        self.tables.append((table_id, bytes(table_data), is_pure))

        return table_index

    def generate_table_node(self, node: TableNode) -> bytes:
        """Generate code for a standalone TableNode.

        Args:
            node: TableNode to generate

        Returns:
            bytes: Z-machine code (no-op as table data is stored separately)
        """
        # Add the table and return empty code
        # The table data itself doesn't generate code - it's just stored for assembly
        self._add_table(node)
        return b''

    # ===== Basic Control Flow =====

    def gen_rtrue(self) -> bytes:
        """Generate RTRUE (return true)."""
        return bytes([0xB0])

    def gen_rfalse(self) -> bytes:
        """Generate RFALSE (return false)."""
        return bytes([0xB1])

    def gen_rfatal(self) -> bytes:
        """Generate RFATAL (return false, fatal condition).

        In most implementations, RFATAL is the same as RFALSE.
        Some games may use it to indicate a fatal/unrecoverable condition.
        """
        return bytes([0xB1])  # Same as RFALSE

    def gen_return(self, operands: List[ASTNode]) -> bytes:
        """Generate RETURN value.

        If inside a PROG/REPEAT/BIND block, RETURN exits the block (not the routine).
        The block's result is set to the return value.

        If not inside a block, RETURN exits the routine normally.

        With 2 operands: <RETURN value activation>
        The activation specifies which block/routine to return from.

        Note: DO-FUNNY-RETURN? feature (changing RETURN behavior based on version
        or explicit setting) is not yet fully implemented.
        """
        if len(operands) > 2:
            raise ValueError("RETURN requires 0-2 operands")

        # Check for activation-based return
        activation_name = None
        if len(operands) == 2:
            # Second operand is activation (e.g., .FOO-ACT)
            activation_op = operands[1]
            if isinstance(activation_op, LocalVarNode):
                # Get the name from the local variable reference
                activation_name = activation_op.name
            elif isinstance(activation_op, AtomNode):
                # Also handle atom form (just in case)
                activation_name = activation_op.value
            else:
                # Invalid activation - must be a variable/atom reference
                raise ValueError(
                    "RETURN with 2 operands requires an activation name as "
                    "the second argument (e.g., <RETURN value .ACTIVATION>)"
                )

        # If activation is specified, check if it matches the routine
        if activation_name:
            # Check if the activation matches the routine's activation
            current_act = getattr(self, '_current_routine_activation', None)
            if current_act and current_act == activation_name:
                # Return from routine (ignore block stack)
                return self._gen_routine_return(operands[:1])

            # Check block stack for matching activation
            for idx, block_ctx in enumerate(self.block_stack):
                if block_ctx.get('activation_name') == activation_name:
                    # Found matching block - return from it
                    return self._gen_targeted_block_return(operands[:1], idx)

        # Check DO-FUNNY-RETURN? flag for RETURN behavior
        # - If explicitly True: RETURN always exits routine
        # - If explicitly False: RETURN exits block (V3 behavior)
        # - If not set: Use version default (V5+ = routine, V3/V4 = block)
        use_routine_return = False
        if self.compiler and hasattr(self.compiler, 'compile_globals'):
            compile_globals = self.compiler.compile_globals
            if 'DO-FUNNY-RETURN?' in compile_globals:
                # Explicit setting overrides version default
                use_routine_return = compile_globals['DO-FUNNY-RETURN?']
            else:
                # No explicit setting - use version default (V5+ = routine return)
                use_routine_return = self.version >= 5
        else:
            # No compiler access - use version default
            use_routine_return = self.version >= 5

        # If using routine return or we're at routine level, skip block handling
        if use_routine_return:
            # RETURN exits routine regardless of block context
            pass
        elif self.block_stack and not activation_name:
            # Block-scoped return: jump to block exit
            return self._gen_block_return(operands[:1] if operands else [])

        # Routine-level return
        if not operands:
            return self.gen_rtrue()

        code = bytearray()

        # If operand is a nested form, generate it first (result goes to stack)
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            # Result is on stack - use variable 0
            op_type, op_val = 1, 0
        elif isinstance(operands[0], CondNode):
            # CondNode needs evaluation first
            inner_code = self.generate_cond(operands[0])
            code.extend(inner_code)
            op_type, op_val = 1, 0
        elif isinstance(operands[0], RepeatNode):
            # RepeatNode needs evaluation first
            inner_code = self.generate_repeat(operands[0])
            code.extend(inner_code)
            op_type, op_val = 1, 0
        else:
            op_type, op_val = self._get_operand_type_and_value(operands[0])

        # RET is 1OP opcode 0x0B
        # Short form 1OP: bits 7-6 = 10, bits 5-4 = operand type, bits 3-0 = opcode
        # Operand types: 00 = large const (2 bytes), 01 = small const (1 byte), 10 = variable
        # 0x8B = 10 00 1011 = large constant
        # 0x9B = 10 01 1011 = small constant
        # 0xAB = 10 10 1011 = variable
        if op_type == 1:  # Variable
            code.append(0xAB)
        elif op_val >= 0 and op_val <= 255:  # Small constant
            code.append(0x9B)
        else:  # Large constant
            code.append(0x8B)
            code.append((op_val >> 8) & 0xFF)
        code.append(op_val & 0xFF)

        return bytes(code)

    def _gen_routine_return(self, operands: List[ASTNode]) -> bytes:
        """Generate a routine-level RETURN (exits routine, not just block).

        Used when RETURN has an activation that matches the routine.
        """
        if not operands:
            return self.gen_rtrue()

        code = bytearray()

        # If operand is a nested form, generate it first (result goes to stack)
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            # Result is on stack - use variable 0
            op_type, op_val = 1, 0
        elif isinstance(operands[0], CondNode):
            # CondNode needs evaluation first
            inner_code = self.generate_cond(operands[0])
            code.extend(inner_code)
            op_type, op_val = 1, 0
        elif isinstance(operands[0], RepeatNode):
            # RepeatNode needs evaluation first
            inner_code = self.generate_repeat(operands[0])
            code.extend(inner_code)
            op_type, op_val = 1, 0
        else:
            op_type, op_val = self._get_operand_type_and_value(operands[0])

        # RET is 1OP opcode 0x0B
        if op_type == 1:  # Variable
            code.append(0xAB)
        elif op_val >= 0 and op_val <= 255:  # Small constant
            code.append(0x9B)
        else:  # Large constant
            code.append(0x8B)
            code.append((op_val >> 8) & 0xFF)
        code.append(op_val & 0xFF)

        return bytes(code)

    def _gen_block_return(self, operands: List[ASTNode]) -> bytes:
        """Generate a block-scoped RETURN (exits block, not routine).

        This stores the return value to the block's result variable,
        then generates a JUMP placeholder that will be patched to
        jump to the block's exit point.
        """
        block_ctx = self.block_stack[-1]
        code = bytearray()

        # Get return value (default to 1/TRUE if none specified)
        if operands:
            # If operand is a nested form, generate it first (result goes to stack)
            if isinstance(operands[0], FormNode):
                inner_code = self.generate_form(operands[0])
                code.extend(inner_code)
                # Result is on stack - use variable 0
                op_type, op_val = 1, 0
            elif isinstance(operands[0], CondNode):
                # CondNode needs evaluation first
                inner_code = self.generate_cond(operands[0])
                code.extend(inner_code)
                op_type, op_val = 1, 0
            elif isinstance(operands[0], RepeatNode):
                # RepeatNode needs evaluation first
                inner_code = self.generate_repeat(operands[0])
                code.extend(inner_code)
                op_type, op_val = 1, 0
            else:
                op_type, op_val = self._get_operand_type_and_value(operands[0])
        else:
            op_type, op_val = 0, 1  # Small constant 1 (TRUE)

        # Store value to block's result variable (which is the stack, var 0)
        # Note: STORE opcode to stack (var 0) causes issues with dfrotz, so we use
        # ADD 0, value -> result_var instead, which achieves the same effect.
        result_var = block_ctx['result_var']
        # ADD is opcode 20 (0x14). Long form encoding:
        # Bit 7: 0 (long form)
        # Bit 6: operand 1 type (0=small const, 1=variable)
        # Bit 5: operand 2 type (0=small const, 1=variable)
        # Bits 4-0: opcode (20 = 10100)
        if op_type == 1:  # Variable operand - ADD 0, var -> result
            # Both small const + var: 0 01 10100 = 0x34
            code.extend([0x34, 0x00, op_val, result_var])
        else:  # Constant operand - ADD 0, const -> result
            if op_val < 256:
                # Both small const: 0 00 10100 = 0x14
                code.extend([0x14, 0x00, op_val & 0xFF, result_var])
            else:
                # Large constant - use VAR form for ADD
                # 0xD4 = VAR form ADD (11 0 10100)
                # Type byte: 01 00 11 11 = 0x4F (small const 0, large const value)
                code.extend([0xD4, 0x4F, 0x00, (op_val >> 8) & 0xFF, op_val & 0xFF, result_var])

        # Generate JUMP placeholder (will be patched to jump to block exit)
        # We use 0x8C (JUMP) with special marker bytes 0xFF 0xBB
        # The block's patching code will scan for this pattern and fix the offset
        code.extend([0x8C, 0xFF, 0xBB])  # JUMP with placeholder offset

        return bytes(code)

    def _gen_targeted_block_return(self, operands: List[ASTNode], block_idx: int) -> bytes:
        """Generate a RETURN targeting a specific block by its stack index.

        This is used for RETURN with activation that targets an outer block.
        Uses a unique placeholder pattern (0x8C 0xFE <idx>) so that only
        the targeted block will patch this JUMP.
        """
        block_ctx = self.block_stack[block_idx]
        code = bytearray()

        # Get return value (default to 1/TRUE if none specified)
        if operands:
            # If operand is a nested form, generate it first (result goes to stack)
            if isinstance(operands[0], FormNode):
                inner_code = self.generate_form(operands[0])
                code.extend(inner_code)
                op_type, op_val = 1, 0
            elif isinstance(operands[0], CondNode):
                inner_code = self.generate_cond(operands[0])
                code.extend(inner_code)
                op_type, op_val = 1, 0
            elif isinstance(operands[0], RepeatNode):
                inner_code = self.generate_repeat(operands[0])
                code.extend(inner_code)
                op_type, op_val = 1, 0
            else:
                op_type, op_val = self._get_operand_type_and_value(operands[0])
        else:
            op_type, op_val = 0, 1  # Small constant 1 (TRUE)

        # Store value to block's result variable (stack, var 0)
        result_var = block_ctx['result_var']
        if op_type == 1:  # Variable operand
            code.extend([0x34, 0x00, op_val, result_var])
        else:  # Constant operand
            if op_val < 256:
                code.extend([0x14, 0x00, op_val & 0xFF, result_var])
            else:
                code.extend([0xD4, 0x4F, 0x00, (op_val >> 8) & 0xFF, op_val & 0xFF, result_var])

        # Generate JUMP placeholder with targeted block index
        # Pattern: 0x8C 0xFE <block_idx> - only the targeted block patches this
        code.extend([0x8C, 0xFE, block_idx & 0xFF])

        return bytes(code)

    def gen_quit(self) -> bytes:
        """Generate QUIT."""
        return bytes([0xBA])

    def gen_again(self, operands: List[ASTNode] = None) -> bytes:
        """Generate AGAIN (restart current loop).

        AGAIN jumps back to the start of the innermost REPEAT/PROG/DO loop.
        This is similar to 'continue' in C.

        With an activation parameter (e.g., <AGAIN .FOO-ACT>), AGAIN jumps to
        the start of the block/routine with that activation name.

        Returns a JUMP instruction to the loop start.
        """
        if operands is None:
            operands = []

        # Check for activation-based AGAIN
        activation_name = None
        if operands:
            activation_op = operands[0]
            if isinstance(activation_op, LocalVarNode):
                activation_name = activation_op.name
            elif isinstance(activation_op, AtomNode):
                activation_name = activation_op.value

        # If activation is specified, check if it matches the routine
        if activation_name:
            current_act = getattr(self, '_current_routine_activation', None)
            if current_act and current_act == activation_name:
                # Jump to routine start (first loop context in stack)
                # The routine loop context is pushed first
                for loop_ctx in self.loop_stack:
                    if loop_ctx.get('activation') == activation_name:
                        return self._gen_again_to_context(loop_ctx)
                # Fallback: if we have a routine-level loop context, use it
                if self.loop_stack:
                    return self._gen_again_to_context(self.loop_stack[0])

            # Check loop stack for matching activation
            for loop_ctx in self.loop_stack:
                if loop_ctx.get('activation_name') == activation_name:
                    return self._gen_again_to_context(loop_ctx)

            # No matching activation found
            self._warn(f"AGAIN with activation '{activation_name}' has no matching block/routine")
            return b''

        if not self.loop_stack:
            # No active loop - can't generate AGAIN
            self._warn("AGAIN used outside of loop - ignored")
            return b''

        # Get the innermost loop context
        loop_ctx = self.loop_stack[-1]
        loop_start = loop_ctx.get('loop_start', 0)

        # Generate JUMP to loop start
        # The offset will be calculated based on current position
        # Since we're generating code that will be appended to the main code,
        # we need to use a marker and patch later, OR calculate the offset now
        #
        # For PROG/REPEAT/DO loops, loop_start is the position in the current code block
        # where the loop begins. AGAIN should jump back to that position.
        #
        # JUMP offset formula: target = PC + offset - 2
        # So: offset = target - PC + 2 = loop_start - (current_pos + 3) + 2
        # But current_pos is relative to the code block being built, so we need
        # to track the actual offset needed.
        #
        # Since the code returned is appended to the parent's code, we store
        # a marker that gets patched when the loop finishes generating.

        # Track this AGAIN location for later patching
        if 'again_placeholders' not in loop_ctx:
            loop_ctx['again_placeholders'] = []

        # Generate placeholder JUMP (will be patched later)
        # The patching code in gen_prog/gen_repeat/gen_do will replace these bytes
        # Use 0xAC for routine-level AGAIN, 0xAA for block-level
        code = bytearray()
        code.append(0x8C)  # JUMP opcode
        code.append(0xFF)  # Placeholder high byte (marker)
        if loop_ctx.get('loop_type') == 'ROUTINE':
            code.append(0xAC)  # Routine-level AGAIN marker
        else:
            code.append(0xAA)  # Block-level AGAIN marker

        # Record position relative to code we're generating (starts at 0 here)
        # The parent loop handler will add its base offset when patching
        loop_ctx['again_placeholders'].append(0)  # Position of JUMP offset in this code

        return bytes(code)

    def _gen_again_to_context(self, loop_ctx: dict) -> bytes:
        """Generate AGAIN jump to a specific loop context.

        This is used when AGAIN has an activation parameter that specifies
        which block/routine to jump back to.
        """
        # Track this AGAIN location for later patching
        if 'again_placeholders' not in loop_ctx:
            loop_ctx['again_placeholders'] = []

        # Generate placeholder JUMP (will be patched later)
        # Use 0xAC marker for routine-level AGAIN (vs 0xAA for block-level)
        # This prevents nested blocks from patching routine-level AGAIN
        code = bytearray()
        code.append(0x8C)  # JUMP opcode
        code.append(0xFF)  # Placeholder high byte (marker)
        if loop_ctx.get('loop_type') == 'ROUTINE':
            code.append(0xAC)  # Routine-level AGAIN marker
        else:
            code.append(0xAA)  # Block-level AGAIN marker

        # Record position for patching
        loop_ctx['again_placeholders'].append(0)

        return bytes(code)

    # ===== Output Instructions =====

    def gen_newline(self) -> bytes:
        """Generate NEW_LINE."""
        return bytes([0xBB])

    def gen_tell(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT instructions for TELL.

        TELL supports multiple patterns:
        - "string" - print literal string
        - CR - print newline
        - D ,object - print object short name (PRINT_OBJ)
        - N ,value - print number (PRINT_NUM)
        - C ,char - print character (PRINT_CHAR)
        - P ,address - print from packed address (PRINT_PADDR)
        """
        code = bytearray()
        i = 0

        while i < len(operands):
            op = operands[i]

            if isinstance(op, StringNode):
                # Check for unprintable characters (ZIL0410)
                self._check_unprintable_chars(op.value)
                # Print literal string
                if self.string_table is not None:
                    self.string_table.add_string(op.value)
                    # Use fixed 3-byte placeholder format (same size as final output)
                    # This ensures JUMP/branch offsets are correct
                    placeholder_idx = self._next_string_placeholder_index
                    self._string_placeholders[placeholder_idx] = op.value
                    self._next_string_placeholder_index += 1
                    code.append(0x8D)  # PRINT_PADDR short form
                    code.append(0xFD)  # Marker for string placeholder
                    code.append(placeholder_idx & 0xFF)
                else:
                    code.append(0xB2)  # PRINT opcode
                    encoded_words = self.encoder.encode_string(op.value)
                    code.extend(words_to_bytes(encoded_words))
                i += 1

            elif isinstance(op, AtomNode):
                atom_name = op.value.upper()

                if atom_name == 'CR' or atom_name == 'CRLF':
                    # Print newline
                    code.append(0xBB)  # NEW_LINE opcode
                    i += 1

                elif atom_name == 'D' and i + 1 < len(operands):
                    # D ,object - print object short name
                    i += 1
                    obj_code = self._gen_tell_operand_code(operands[i], 0x0A)  # PRINT_OBJ
                    code.extend(obj_code)
                    i += 1

                elif atom_name == 'N' and i + 1 < len(operands):
                    # N ,value - print number
                    i += 1
                    num_code = self.gen_print_num([operands[i]])
                    code.extend(num_code)
                    i += 1

                elif atom_name == 'C' and i + 1 < len(operands):
                    # C ,char - print character
                    i += 1
                    char_code = self.gen_print_char([operands[i]])
                    code.extend(char_code)
                    i += 1

                elif atom_name == 'P' and i + 1 < len(operands):
                    # P ,address - print from packed address
                    i += 1
                    paddr_code = self.gen_printb([operands[i]])
                    code.extend(paddr_code)
                    i += 1

                elif atom_name == 'A' and i + 1 < len(operands):
                    # A ,address - print from byte address
                    i += 1
                    addr_code = self.gen_printaddr([operands[i]])
                    code.extend(addr_code)
                    i += 1

                elif op.value.startswith('!') and len(op.value) >= 2:
                    # Character literal: !\X or !X - print as character
                    # Use original value (not uppercased) to preserve character
                    char_part = op.value[1:]
                    if char_part.startswith('\\') and len(char_part) >= 2:
                        char_val = ord(char_part[1])
                    else:
                        char_val = ord(char_part[0])
                    # PRINT_CHAR with immediate value (VAR:0x05)
                    code.append(0xE5)  # VAR opcode 0x05
                    code.append(0x7F)  # Type: small constant (01), rest omitted (111111)
                    code.append(char_val & 0xFF)
                    i += 1

                else:
                    # Unknown atom - error
                    # Bare atom references in TELL are not allowed
                    # Use ,ATOM for global references or just "string" for literals
                    raise ValueError(
                        f"Unknown token '{op.value}' in TELL. Use ,{op.value} for global "
                        f"references or a quoted string for literals."
                    )

            elif isinstance(op, FormNode):
                # Form (likely GVAL or similar) - generate and print result
                form_code = self.generate_form(op)
                code.extend(form_code)
                # Result is on stack, print it as number
                code.append(0xE6)  # PRINT_NUM VAR form
                code.append(0xBF)  # Type: variable (stack), rest omitted
                code.append(0x00)  # Stack
                i += 1

            elif isinstance(op, GlobalVarNode) or isinstance(op, LocalVarNode):
                # Variable reference - print from packed address (PRINT_PADDR)
                # The variable contains a packed address pointing to a string
                var_code = self._gen_tell_operand_code(op, 0x0D)  # PRINT_PADDR
                code.extend(var_code)
                i += 1

            else:
                # Skip unknown
                i += 1

        return bytes(code)

    def _gen_tell_operand_code(self, operand: ASTNode, opcode_1op: int) -> bytes:
        """Generate 1OP instruction for TELL operand.

        Args:
            operand: The operand to print
            opcode_1op: The 1OP opcode (e.g., 0x0A for PRINT_OBJ)

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()

        # If operand is a nested expression, evaluate it first (result goes to stack)
        if isinstance(operand, FormNode):
            # Generate code for the expression (pushes result to stack)
            expr_code = self.generate_form(operand)
            code.extend(expr_code)
            # Now print from stack (variable 0)
            op_type = 1  # Variable
            op_val = 0   # Stack
        else:
            op_type, op_val = self._get_operand_type_and_value(operand)

        # 1OP form: 0x8X for large constant (16-bit), 0x9X for small constant, 0xAX for variable
        if op_type == 1:  # Variable
            code.append(0xA0 | opcode_1op)
        else:  # Constant
            code.append(0x90 | opcode_1op)  # Small constant (8-bit)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_print_num(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_NUM (print signed number)."""
        if len(operands) != 1:
            raise ValueError("PRINTN requires exactly 1 operand")

        code = bytearray()
        operand = operands[0]

        # If operand is a nested expression, evaluate it first (result goes to stack)
        if isinstance(operand, FormNode):
            # Generate code for the expression (pushes result to stack)
            expr_code = self.generate_form(operand)
            code.extend(expr_code)
            # Now print from stack (variable 0)
            op_type = 2  # Variable (matching _get_operand_type_and_value_ext convention)
            op_val = 0   # Stack
        elif isinstance(operand, RepeatNode):
            # Generate REPEAT code (result goes to stack via RETURN)
            # Construct operands list: [bindings, body_stmts...]
            repeat_operands = [operand.bindings] + operand.body
            expr_code = self.gen_repeat(repeat_operands)
            code.extend(expr_code)
            op_type = 2  # Variable (matching _get_operand_type_and_value_ext convention)
            op_val = 0   # Stack
        elif isinstance(operand, CondNode):
            # Generate COND code (result goes to stack)
            expr_code = self.generate_cond(operand)
            code.extend(expr_code)
            op_type = 2  # Variable (matching _get_operand_type_and_value_ext convention)
            op_val = 0   # Stack
        else:
            # Determine operand type and value using extended version
            # (handles large constants for negative numbers and values > 255)
            op_type, op_val = self._get_operand_type_and_value_ext(operand)

        # PRINT_NUM is VAR opcode 0x06
        code.append(0xE6)  # Variable form, VAR, opcode 0x06

        # Type byte encoding for VAR form with single operand:
        # Bits 7-6: operand type (00=large, 01=small, 10=variable, 11=omitted)
        # Bits 5-0: 111111 (remaining operands omitted)
        if op_type == 0:  # Large constant (2 bytes)
            type_byte = 0x3F  # 00 11 11 11 = large const, rest omitted
            code.append(type_byte)
            code.append((op_val >> 8) & 0xFF)
            code.append(op_val & 0xFF)
        elif op_type == 1:  # Small constant (1 byte)
            type_byte = 0x7F  # 01 11 11 11 = small const, rest omitted
            code.append(type_byte)
            code.append(op_val & 0xFF)
        else:  # Variable (op_type == 2)
            type_byte = 0xBF  # 10 11 11 11 = variable, rest omitted
            code.append(type_byte)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_print_char(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_CHAR."""
        if len(operands) != 1:
            raise ValueError("PRINTC requires exactly 1 operand")

        code = bytearray()

        # Handle FormNode operands - generate the inner code first
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            op_type = 2  # Variable
            op_val = 0   # Stack
        else:
            op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xE5)  # VAR opcode 0x05
        # Type byte: 01 for small constant, 10 for variable
        # 0x3F = 00111111 (remaining operands omitted)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)  # type in bits 7-6, rest omitted
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_printb(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_ADDR (print from byte address).

        <PRINTB addr> prints text from a byte address.
        PRINT_ADDR is 1OP:7.

        Opcode encoding (short form, 1OP):
        - 0x87 = large constant operand (2 bytes)
        - 0x97 = small constant operand (1 byte)
        - 0xA7 = variable operand (1 byte)
        """
        if len(operands) != 1:
            raise ValueError("PRINTB requires exactly 1 operand")

        code = bytearray()

        # Handle FormNode operands - generate the inner code first
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            op_type = 2  # Variable
            op_val = 0   # Stack
        else:
            op_type, op_val = self._get_operand_type_and_value_ext(operands[0])

        # PRINT_ADDR is 1OP:7
        # Short form: 0x80 + opcode for large, 0x90 for small, 0xA0 for var
        if op_type == 0:  # Large constant
            code.append(0x87)  # 1OP:7 with large constant
            code.append((op_val >> 8) & 0xFF)
            code.append(op_val & 0xFF)
        elif op_type == 1:  # Small constant
            code.append(0x97)  # 1OP:7 with small constant
            code.append(op_val & 0xFF)
        else:  # Variable
            code.append(0xA7)  # 1OP:7 with variable
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_printi(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINTI (print inline string).

        <PRINTI "text"> prints an inline string.
        This is typically used in property values.

        For now, we'll treat it like TELL.
        """
        # Delegate to TELL implementation
        return self.gen_tell(operands)

    def gen_printr(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_RET (print string and return true).

        <PRINTR "text"> prints a string, a newline, then returns true (1).
        Uses PRINT_RET opcode (0xB3).
        """
        if len(operands) != 1 or not isinstance(operands[0], StringNode):
            raise ValueError("PRINTR requires exactly 1 string operand")

        code = bytearray()

        # PRINT_RET is 0OP opcode 0x03 followed by encoded string
        code.append(0xB3)  # PRINT_RET opcode

        # Encode the string
        text = operands[0].value
        encoded_words = self.encoder.encode_string(text)
        code.extend(words_to_bytes(encoded_words))

        return bytes(code)

    def gen_printaddr(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_ADDR (print string at address).

        <PRINTADDR addr> prints a string stored at the given byte address.
        Uses PRINT_ADDR opcode (0x15 in VAR form).

        Unlike PRINTB which uses packed addresses, PRINTADDR uses byte addresses.

        Args:
            operands[0]: Byte address of string

        Returns:
            bytes: Z-machine code (PRINT_ADDR)
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])
        type_byte = 0x01 if op_type == 0 else 0x02

        # PRINT_ADDR is VAR opcode 0x15 (V4+)
        # For V3, we can use PRINT_PADDR with address conversion
        if self.version >= 4:
            code.append(0xF5)  # VAR form, opcode 0x15
            code.append((type_byte << 6) | 0x3F)
            code.append(op_val & 0xFF)
        else:
            # V3: use PRINT_PADDR
            code.append(0xED)  # VAR form, opcode 0x0D
            code.append((type_byte << 6) | 0x3F)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_string(self, operands: List[ASTNode]) -> bytes:
        """Generate STRING (build string with escape sequences).

        <STRING str> returns the address of a string.
        In full ZIL, STRING uses ! for escapes:
          !\\" - literal quote
          !\\\\ - literal backslash
          !,VAR - interpolate variable value

        For now, we implement basic string handling without interpolation.
        Returns code that pushes the string's address onto the stack.

        Args:
            operands: String components (may include literals and variables)

        Returns:
            bytes: Z-machine code to push string address to stack
        """
        if not operands:
            return b''

        code = bytearray()

        # Basic implementation: if we have a string literal, get its address
        if len(operands) == 1 and isinstance(operands[0], StringNode):
            string_val = operands[0].value

            # Process escape sequences
            # !\" -> "
            # !\\ -> \
            processed = string_val.replace('!\\"', '"').replace('!\\\\', '\\')

            # Add string to table and generate code to load its address
            if self.string_table is not None:
                self.string_table.add_string(processed)
                # Use marker pattern for string address resolution
                # Store string address to stack using ADD 0 + marker
                code.append(0xE4)  # VAR form ADD with store
                code.append(0x5F)  # Types: small const, small const, omit, omit
                code.append(0x00)  # First operand: 0
                # Marker for string address (will be resolved later)
                marker = b'\xFF\xFE'
                code.extend(marker)
                text_bytes = processed.encode('utf-8')
                code.append(len(text_bytes) & 0xFF)
                code.append((len(text_bytes) >> 8) & 0xFF)
                code.extend(text_bytes)
                code.append(0x00)  # Store to stack
            else:
                # No string table - encode inline and return packed address
                # This is a fallback; strings should normally use the table
                encoded_words = self.encoder.encode_string(processed)
                encoded_bytes = words_to_bytes(encoded_words)
                # Can't easily return address without table - return 0
                code.append(0x54)  # ADD const const
                code.append(0x00)
                code.append(0x00)
                code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Variable Operations =====

    def gen_set(self, operands: List[ASTNode], is_global: bool = False) -> bytes:
        """Generate SET/SETG (variable assignment).

        SET and SETG have different VariableScopeQuirks behavior:
        - SET treats .LVAL as variable name, ,GVAL as expression (indirect)
        - SETG treats ,GVAL as variable name, .LVAL as expression (indirect)
        """
        op_name = 'SETG' if is_global else 'SET'
        if len(operands) != 2:
            raise ValueError(f"{op_name} requires exactly 2 operands")

        var_node = operands[0]
        value_node = operands[1]

        # Check for indirect variable assignment (computed variable index)
        indirect_var_num = None  # Variable containing the target variable index
        computed_var_expr = None  # Expression that computes the target variable index

        # Handle LocalVarNode (.FOO)
        if isinstance(var_node, LocalVarNode):
            var_name = var_node.name
            if is_global:
                # SETG .FOO -> indirect: set variable whose index is in local FOO
                if var_name not in self.locals:
                    raise ValueError(f"{op_name}: Local variable '{var_name}' not declared")
                indirect_var_num = self.locals[var_name]
            else:
                # SET .FOO -> direct: set local FOO
                if var_name not in self.locals:
                    raise ValueError(f"{op_name}: Local variable '{var_name}' not declared")
                var_num = self.locals[var_name]

        # Handle GlobalVarNode (,FOO)
        elif isinstance(var_node, GlobalVarNode):
            var_name = var_node.name
            if is_global:
                # SETG ,FOO -> direct: set global FOO
                if var_name in self.globals:
                    var_num = self.globals[var_name]
                else:
                    # Create new global
                    var_num = self.next_global
                    self.globals[var_name] = var_num
                    self.next_global += 1
            else:
                # SET ,FOO -> indirect: set variable whose index is in global FOO
                if var_name not in self.globals:
                    raise ValueError(f"{op_name}: Global variable '{var_name}' not declared")
                indirect_var_num = self.globals[var_name]

        # Handle AtomNode (bare variable name)
        elif isinstance(var_node, AtomNode):
            var_name = var_node.value
            if is_global:
                # SETG with bare atom: check global first, then routine locals
                # Use routine_locals (not self.locals) to ignore PROG/BIND shadows
                if var_name in self.globals:
                    var_num = self.globals[var_name]
                elif hasattr(self, 'routine_locals') and var_name in self.routine_locals:
                    # No global but routine local exists - act like SET for routine locals
                    var_num = self.routine_locals[var_name]
                else:
                    # SETG creates a new global if one doesn't exist
                    var_num = self.next_global
                    self.globals[var_name] = var_num
                    self.next_global += 1
            else:
                # SET checks locals first, then globals
                var_num = self.locals.get(var_name)
                if var_num is not None:
                    # Found as local - use it
                    pass  # var_num already set
                elif var_name in self.globals:
                    # Found as global - use it
                    var_num = self.globals[var_name]
                else:
                    raise ValueError(f"{op_name}: Variable '{var_name}' not declared")
        elif isinstance(var_node, NumberNode):
            # Numeric variable reference (e.g., <SET 1 value> to set local variable 1)
            var_num = var_node.value
            # Validate: 0=stack, 1-15=locals (must exist), 16+=globals
            if 1 <= var_num <= 15:
                # Local variable - must be within declared locals
                num_locals = len(self.locals)
                if var_num > num_locals:
                    raise ValueError(f"{op_name}: Local variable {var_num} not declared (only {num_locals} locals)")
        elif isinstance(var_node, FormNode):
            # Computed variable reference: <SET <+ .A 1> value>
            # The expression computes the variable number at runtime
            # We'll handle this specially below with computed_var_expr
            computed_var_expr = var_node
        else:
            raise ValueError(f"{op_name}: First operand must be a variable name or number")

        code = bytearray()

        # Handle indirect variable assignment (SET ,GVAL or SETG .LVAL)
        if indirect_var_num is not None:
            # Indirect assignment: the value in indirect_var_num is the target variable index
            # STORE (variable) value - first operand is variable type
            if isinstance(value_node, FormNode):
                # Generate code to evaluate expression (result goes to stack twice)
                # First, we need to duplicate the value: eval, save, eval again won't work
                # Instead: eval once, store to temp, store temp to target, push temp
                expr_code = self.generate_form(value_node)
                code.extend(expr_code)
                # Stack has the value. Store it in a temp variable (using local 0/stack as temp)
                # Actually, simpler: STORE pops from stack, so we need to push again
                # Use: STORE (indirect) stack, then re-evaluate or use ADD 0 0 -> stack trick
                #
                # Cleaner approach: Store from stack, then push the same value
                # But we don't know the value... Let me use STORE then LOAD target
                # STORE (indirect) stack - stores and pops
                opcode = 0x0D | (1 << 6) | (1 << 5)  # Both operands are variables
                code.append(opcode)
                code.append(indirect_var_num & 0xFF)
                code.append(0x00)  # Stack
                # For value context, re-generate the expression to get value again
                # This is inefficient but correct. TODO: optimize later
                code.extend(self.generate_form(value_node))
            else:
                val_type, val_val = self._get_operand_type_and_value(value_node)
                # STORE indirect_var value
                # First operand is variable (the indirect ref), second is the value
                opcode = 0x0D | (1 << 6) | (val_type << 5)
                code.append(opcode)
                code.append(indirect_var_num & 0xFF)
                code.append(val_val & 0xFF)
                # Push the stored value (for value context)
                # Use PUSH (VAR opcode 0x08)
                if val_type == 0:  # Small constant
                    code.append(0xE8)  # VAR form PUSH
                    code.append(0x7F)  # Small constant type, rest omit
                    code.append(val_val & 0xFF)
                else:  # Variable
                    code.append(0xE8)  # VAR form PUSH
                    code.append(0xBF)  # Variable type, rest omit
                    code.append(val_val & 0xFF)
            return bytes(code)

        # Handle computed variable expression (SET <expr> value)
        if computed_var_expr is not None:
            # Computed variable: evaluate expression to get target var number
            # Strategy: eval var_num expr, save to scratch, eval value, STORE (scratch) (stack)

            # Ensure we have a scratch global for holding computed var number
            if '_SCRATCH_' not in self.globals:
                self.globals['_SCRATCH_'] = self.next_global
                self.next_global += 1
            scratch_var = self.globals['_SCRATCH_']

            # 1. Evaluate the expression that computes the variable number
            var_expr_code = self.generate_form(computed_var_expr)
            code.extend(var_expr_code)

            # 2. Save computed var number to scratch (PULL from stack to scratch)
            code.append(0xE9)  # PULL
            code.append(0x7F)  # Type: small constant
            code.append(scratch_var & 0xFF)

            # 3. Evaluate the value expression
            if isinstance(value_node, FormNode):
                value_code = self.generate_form(value_node)
                code.extend(value_code)
                # 4. STORE (scratch) (stack) - both operands are variables
                # 0x6D = 2OP long form with both operands as variables, opcode 0x0D
                code.append(0x6D)  # STORE var,var
                code.append(scratch_var & 0xFF)  # First operand: scratch (contains target var num)
                code.append(0x00)  # Second operand: stack (contains value)
                # 5. For value context, re-evaluate to push value again
                # (inefficient but correct - optimization would require temp storage)
                code.extend(self.generate_form(value_node))
            else:
                # Simple value - get type and value
                val_type, val_val = self._get_operand_type_and_value(value_node)
                # 4. STORE (scratch) value
                if val_type == 0:  # Small constant
                    # 0x4D = 2OP long form: first var, second small, opcode 0x0D
                    code.append(0x4D)
                    code.append(scratch_var & 0xFF)
                    code.append(val_val & 0xFF)
                else:  # Variable
                    # 0x6D = 2OP long form: both variables, opcode 0x0D
                    code.append(0x6D)
                    code.append(scratch_var & 0xFF)
                    code.append(val_val & 0xFF)
                # 5. Push the value for value context
                code.append(0xE8)  # PUSH
                if val_type == 0:
                    code.append(0x7F)  # Small constant
                    code.append(val_val & 0xFF)
                else:
                    code.append(0xBF)  # Variable
                    code.append(val_val & 0xFF)

            return bytes(code)

        # Direct variable assignment
        # Check if value is an expression (FormNode, RepeatNode, CondNode) that needs evaluation
        if isinstance(value_node, (FormNode, RepeatNode, CondNode)):
            # Generate code to evaluate expression (result goes to stack)
            if isinstance(value_node, FormNode):
                expr_code = self.generate_form(value_node)
            elif isinstance(value_node, RepeatNode):
                expr_code = self.generate_repeat(value_node)
            else:  # CondNode
                expr_code = self.generate_cond(value_node)
            code.extend(expr_code)

            # Pop result from stack into target variable using PULL
            # PULL is VAR opcode 0x09
            # V1-5, V8: pull (variable) - operand is target variable, no store byte
            # V6-7: pull stack -> (result) - operand is stack reference, store byte follows
            #       If operand omitted (type 0xFF), uses main game stack
            code.append(0xE9)  # VAR form PULL
            if self.version in (6, 7):
                # V6-7: omit operand to use main stack, then store target
                code.append(0xFF)  # Type: all omitted (11 11 11 11) = main stack
                code.append(var_num & 0xFF)  # Store result to target variable
            else:
                # V1-5, V8: operand is target variable number
                code.append(0x7F)  # Type: small constant (01), omit rest
                code.append(var_num & 0xFF)  # Variable number to store into
            # For value context, push the stored value (load target variable)
            # LOAD short form: 10 tt nnnn, tt=01 for small constant (var number), nnnn=0E
            # 10 01 1110 = 0x9E
            code.append(0x9E)  # 1OP LOAD short form with small constant type
            code.append(var_num & 0xFF)
            code.append(0x00)  # Store to stack
        elif isinstance(value_node, TableNode):
            # Table literal - store table and use placeholder address
            table_index = self._add_table(value_node)
            # For now, store the table index as a placeholder
            # The assembler will need to patch this with actual address
            # STORE var placeholder_address
            code.append(0x0D)  # 2OP:0x0D STORE (long form, small/small: 00 0 0 1101)
            code.append(var_num & 0xFF)
            code.append(table_index & 0xFF)  # Placeholder
            # For value context, push the table address
            # LOAD short form: 10 01 1110 = 0x9E
            code.append(0x9E)  # 1OP LOAD with small constant type
            code.append(var_num & 0xFF)
            code.append(0x00)  # Store to stack
        else:
            # Simple value assignment
            val_type, val_val = self._get_operand_type_and_value(value_node)

            # Check if value is a large constant (> 255)
            is_large_const = val_type == 0 and val_val > 255

            if is_large_const:
                # Use VAR form for large constants
                # STORE is 2OP opcode 0x0D, VAR form is 0xCD
                code.append(0xCD)  # VAR form STORE
                # Type byte: small constant for var, large constant for value
                code.append(0x4F)  # 01=small, 00=large, 11=omit, 11=omit
                code.append(var_num & 0xFF)
                # Write 2-byte value (big-endian)
                # For routine address placeholders, this writes 0xFD <idx>
                # which will be found by the placeholder scanning code
                code.append((val_val >> 8) & 0xFF)
                code.append(val_val & 0xFF)
                # For value context, push the stored value with large constant
                code.append(0xE8)  # VAR form PUSH
                code.append(0x3F)  # Large constant type, rest omit (00 11 11 11)
                code.append((val_val >> 8) & 0xFF)
                code.append(val_val & 0xFF)
            else:
                # STORE is 2OP opcode 0x0D
                # Long form: bit6=var type for first op, bit5=var type for second op
                opcode = 0x0D | (0 << 6) | (val_type << 5)  # First operand always small const
                code.append(opcode)
                code.append(var_num & 0xFF)
                code.append(val_val & 0xFF)
                # For value context, push the stored value
                if val_type == 0:  # Small constant
                    code.append(0xE8)  # VAR form PUSH
                    code.append(0x7F)  # Small constant type, rest omit
                    code.append(val_val & 0xFF)
                else:  # Variable
                    code.append(0xE8)  # VAR form PUSH
                    code.append(0xBF)  # Variable type, rest omit
                    code.append(val_val & 0xFF)

        return bytes(code)

    def gen_inc(self, operands: List[ASTNode]) -> bytes:
        """Generate INC (increment variable).

        INC takes a variable NUMBER as its operand (which variable to increment),
        not a variable reference to dereference. The operand is encoded as a
        small constant (1 byte).

        The operand must be a variable name (atom), not a literal number.
        """
        if not operands:
            raise ValueError("INC requires exactly 1 operand")

        # Validate that operand is a variable reference, not a literal number
        op = operands[0]
        if isinstance(op, NumberNode):
            raise ValueError("INC requires a variable name, not a number")

        code = bytearray()
        var_num = self.get_variable_number(op)
        if var_num == 0:
            # var_num 0 is stack, which is invalid for INC - the variable wasn't found
            if isinstance(op, AtomNode) and op.value not in self.locals and op.value not in self.globals:
                raise ValueError(f"INC: Unknown variable '{op.value}'")

        # INC is 1OP opcode 0x05
        # Short 1OP format: 10 tt nnnn where tt=01 for small constant
        # 0x95 = 10 01 0101 = short 1OP, small const, opcode 5
        code.append(0x95)  # Short 1OP with small constant, opcode 0x05
        code.append(var_num)

        return bytes(code)

    def gen_dec(self, operands: List[ASTNode]) -> bytes:
        """Generate DEC (decrement variable).

        DEC takes a variable NUMBER as its operand (which variable to decrement),
        not a variable reference to dereference. The operand is encoded as a
        small constant (1 byte).

        The operand must be a variable name (atom), not a literal number.
        """
        if not operands:
            raise ValueError("DEC requires exactly 1 operand")

        # Validate that operand is a variable reference, not a literal number
        op = operands[0]
        if isinstance(op, NumberNode):
            raise ValueError("DEC requires a variable name, not a number")

        code = bytearray()
        var_num = self.get_variable_number(op)
        if var_num == 0:
            # var_num 0 is stack, which is invalid for DEC - the variable wasn't found
            if isinstance(op, AtomNode) and op.value not in self.locals and op.value not in self.globals:
                raise ValueError(f"DEC: Unknown variable '{op.value}'")

        # DEC is 1OP opcode 0x06
        # Short 1OP format: 10 tt nnnn where tt=01 for small constant
        # 0x96 = 10 01 0110 = short 1OP, small const, opcode 6
        code.append(0x96)  # Short 1OP with small constant, opcode 0x06
        code.append(var_num)

        return bytes(code)

    def gen_value(self, operands: List[ASTNode]) -> bytes:
        """Generate VALUE (get variable value).

        <VALUE var> reads the value of a variable (local or global).
        Uses LOAD instruction (1OP opcode 0x0E).
        """
        if len(operands) != 1:
            raise ValueError("VALUE requires exactly 1 operand")

        # Validate that the variable exists
        var_node = operands[0]
        if isinstance(var_node, AtomNode):
            name = var_node.value
            if name not in self.locals and name not in self.globals:
                raise ValueError(f"VALUE: Unknown variable '{name}'")
        elif isinstance(var_node, NumberNode):
            # Direct variable number (e.g., VALUE 0 for stack)
            pass
        else:
            raise ValueError("VALUE: Operand must be a variable name or number")

        code = bytearray()
        var_num = self.get_variable_number(operands[0])

        # LOAD is 1OP opcode 0x0E
        # Short form: 10 tt nnnn, where tt=01 for small constant, nnnn=0E
        # 10 01 1110 = 0x9E
        # Note: the operand is a VARIABLE NUMBER (like 1 for local 1, 16 for global 0),
        # not a variable reference. So we use small constant type.
        code.append(0x9E)  # Short 1OP, opcode 0x0E, small constant type
        code.append(var_num)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_lval(self, operands: List[ASTNode]) -> bytes:
        """Generate LVAL (get local variable value).

        <LVAL var> reads the value of a local variable.
        """
        if not operands:
            return b''

        code = bytearray()
        if isinstance(operands[0], AtomNode):
            var_num = self.locals.get(operands[0].value, 1)
        else:
            return b''

        # LOAD is 1OP opcode 0x0E
        # Short form: 10 01 1110 = 0x9E (small constant type for variable number)
        code.append(0x9E)  # Short 1OP, opcode 0x0E, small constant type
        code.append(var_num)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_gval(self, operands: List[ASTNode]) -> bytes:
        """Generate GVAL (get global variable value).

        <GVAL var> reads the value of a global variable.
        """
        if not operands:
            return b''

        code = bytearray()
        if isinstance(operands[0], AtomNode):
            var_num = self.globals.get(operands[0].value)
            if var_num is None:
                return b''
        else:
            return b''

        # LOAD is 1OP opcode 0x0E
        # Short form: 10 01 1110 = 0x9E (small constant type for variable number)
        code.append(0x9E)  # Short 1OP, opcode 0x0E, small constant type
        code.append(var_num)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Arithmetic Operations =====

    def gen_add(self, operands: List[ASTNode]) -> bytes:
        """Generate ADD instruction.

        Handles variadic addition:
        - 0 operands: returns 0 (identity)
        - 1 operand: returns that operand
        - 2 operands: a + b
        - 3+ operands: a + b + c + ...
        """
        # ADD is 2OP opcode 0x14 (20 decimal)
        return self._gen_variadic_arith(0x14, operands, identity=0)

    def _gen_variadic_arith(self, opcode: int, operands: List[ASTNode], identity: int) -> bytes:
        """Generate variadic arithmetic instruction.

        Args:
            opcode: The 2OP opcode number
            operands: List of operand nodes
            identity: Identity value for 0 operands (0 for add/sub, 1 for mul/div)

        Returns:
            Bytecode for the instruction
        """
        if len(operands) == 0:
            # Return identity value - push constant to stack
            return self._gen_push_const(identity)

        if len(operands) == 1:
            # Single operand - just evaluate and push to stack
            # Generate code to get the operand value onto the stack
            return self._gen_push_operand(operands[0])

        if len(operands) == 2:
            # Standard 2-operand case
            return self._gen_2op_store(opcode, operands[0], operands[1])

        # 3+ operands: chain operations
        # First, compute op1 OP op2 -> stack
        code = bytearray()
        code.extend(self._gen_2op_store(opcode, operands[0], operands[1]))

        # For each remaining operand, compute stack OP opN -> stack
        stack_ref = NumberNode(0)  # Variable 0 = stack
        stack_ref._is_stack_ref = True  # Mark as stack reference

        for i in range(2, len(operands)):
            code.extend(self._gen_2op_store_with_stack(opcode, operands[i]))

        return bytes(code)

    def _gen_push_const(self, value: int) -> bytes:
        """Generate code to push a constant value to the stack.

        Uses a simple ADD 0,value -> stack approach for constants.
        """
        code = bytearray()
        # Handle signed values
        if value < 0:
            value = (1 << 16) + value

        if value == 0:
            # ADD 0, 0 -> stack  (long form: both small constants)
            # Opcode: 0 0 0 10100 = 0x14
            code.append(0x14)  # Long 2OP, both small const, ADD
            code.append(0x00)  # First operand: 0
            code.append(0x00)  # Second operand: 0
            code.append(0x00)  # Store to stack
        elif 0 <= value <= 255:
            # ADD 0, value -> stack (long form)
            code.append(0x14)  # Long 2OP, both small const, ADD
            code.append(0x00)  # First operand: 0
            code.append(value & 0xFF)  # Second operand
            code.append(0x00)  # Store to stack
        else:
            # Need VAR form for large constant
            code.append(0xD4)  # VAR form, ADD (0xC0 | 0x14)
            code.append(0x4F)  # Types: 01 00 11 11 = small const, large const, omit, omit
            code.append(0x00)  # First operand: 0
            code.append((value >> 8) & 0xFF)
            code.append(value & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def _gen_push_operand(self, node: ASTNode) -> bytes:
        """Generate code to push an operand value to the stack."""
        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value_ext(node)

        # Handle negative constants
        if op_type == 0 and op_val < 0:
            op_val = (1 << 16) + op_val

        if op_type == 2:  # Variable
            # LOAD var -> stack (1OP opcode 0x0E)
            # Short form: 10 10 1110 = 0xAE (variable type)
            code.append(0xAE)
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store to stack
        elif op_type == 1:  # Small constant
            # ADD 0, const -> stack
            code.append(0x14)  # Long 2OP ADD
            code.append(0x00)
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store to stack
        else:  # Large constant
            # ADD 0, const -> stack (VAR form)
            code.append(0xD4)  # VAR form ADD
            code.append(0x4F)  # small const, large const, omit, omit
            code.append(0x00)
            code.append((op_val >> 8) & 0xFF)
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def _gen_2op_store_with_stack(self, opcode: int, op2_node: ASTNode) -> bytes:
        """Generate 2OP instruction where first operand is stack (variable 0).

        Args:
            opcode: The 2OP opcode number
            op2_node: Second operand AST node

        Returns:
            Bytecode for the instruction
        """
        code = bytearray()
        op2_type, op2_val = self._get_operand_type_and_value_ext(op2_node)

        # First operand is always variable 0 (stack)
        # Long form: bit 6 = 1 (var), bit 5 = op2 type
        if op2_type in (1, 2):  # Small const or variable
            op2_bit = 1 if op2_type == 2 else 0
            opcode_byte = (1 << 6) | (op2_bit << 5) | opcode
            code.append(opcode_byte)
            code.append(0x00)  # Variable 0 (stack)
            code.append(op2_val & 0xFF)
        else:  # Large constant - need VAR form
            code.append(0xC0 | opcode)
            # Types: 10 (var) 00 (large) 11 11 = 0x8F
            code.append(0x8F)
            code.append(0x00)  # Variable 0 (stack)
            code.append((op2_val >> 8) & 0xFF)
            code.append(op2_val & 0xFF)

        code.append(0x00)  # Store to stack
        return bytes(code)

    def _gen_2op_store(self, opcode_num: int, op1_node: ASTNode, op2_node: ASTNode, store_var: int = 0) -> bytes:
        """Generate a 2OP instruction with store, handling all operand types correctly.

        Args:
            opcode_num: The opcode number (0-31)
            op1_node: First operand AST node
            op2_node: Second operand AST node
            store_var: Variable to store result (0 = stack)

        Returns:
            Bytecode for the instruction
        """
        code = bytearray()

        # Pre-generate any FormNode operands first (they push to stack)
        # Process in order so stack values are correct
        if isinstance(op1_node, FormNode):
            inner_code = self.generate_form(op1_node)
            code.extend(inner_code)
            op1_type = 2  # Variable
            op1_val = 0   # Stack
        else:
            op1_type, op1_val = self._get_operand_type_and_value_ext(op1_node)

        if isinstance(op2_node, FormNode):
            inner_code = self.generate_form(op2_node)
            code.extend(inner_code)
            op2_type = 2  # Variable
            op2_val = 0   # Stack
        else:
            op2_type, op2_val = self._get_operand_type_and_value_ext(op2_node)

        # Check if we can use long form (both operands are small const or variable)
        # Long form only supports: small constant (0-255) or variable
        can_use_long = (op1_type in (1, 2) and op2_type in (1, 2))

        if can_use_long:
            # Long form: 0 op1_type op2_type opcode_num[4:0]
            # op1_type: bit 6 (0=small, 1=var)
            # op2_type: bit 5 (0=small, 1=var)
            op1_bit = 1 if op1_type == 2 else 0  # 2=var -> 1, 1=small -> 0
            op2_bit = 1 if op2_type == 2 else 0
            opcode_byte = (op1_bit << 6) | (op2_bit << 5) | opcode_num
            code.append(opcode_byte)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
        else:
            # Variable form: 11 0 opcode_num[4:0] = 0xC0 | opcode_num
            code.append(0xC0 | opcode_num)
            # Operand type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omit
            type_byte = (op1_type << 6) | (op2_type << 4) | 0x0F  # 0x0F = remaining slots omitted
            code.append(type_byte)
            # Add operands based on type
            if op1_type == 0:  # Large constant
                code.append((op1_val >> 8) & 0xFF)
                code.append(op1_val & 0xFF)
            else:  # Small constant or variable
                code.append(op1_val & 0xFF)
            if op2_type == 0:  # Large constant
                code.append((op2_val >> 8) & 0xFF)
                code.append(op2_val & 0xFF)
            else:  # Small constant or variable
                code.append(op2_val & 0xFF)

        code.append(store_var)  # Store result
        return bytes(code)

    def _get_operand_type_and_value_ext(self, node: ASTNode) -> Tuple[int, int]:
        """Get extended operand type and value for VAR form encoding.

        Returns:
            Tuple of (type, value) where type is:
            - 0 = large constant (2 bytes)
            - 1 = small constant (1 byte, 0-255)
            - 2 = variable
        """
        if isinstance(node, NumberNode):
            val = node.value
            # Handle signed 16-bit range
            if val < 0:
                val = (1 << 16) + val  # Convert to unsigned 16-bit
            # Small constant: 0-255 unsigned
            if 0 <= node.value <= 255:
                return (1, val)  # Small constant
            else:
                return (0, val)  # Large constant
        elif isinstance(node, GlobalVarNode):
            if node.name in self.globals:
                return (2, self.globals[node.name])  # Variable
            elif node.name in self.objects:
                obj_num = self.objects[node.name]
                if 0 <= obj_num <= 255:
                    return (1, obj_num)
                else:
                    return (0, obj_num)
            elif node.name in self.constants:
                const_val = self.constants[node.name]
                if 0 <= const_val <= 255:
                    return (1, const_val)
                else:
                    return (0, const_val)
            else:
                self._warn(f"Unknown global/object '{node.name}' - using default")
                return (2, 0x10)
        elif isinstance(node, LocalVarNode):
            var_num = self.locals.get(node.name)
            if var_num is not None:
                # Mark local as used (for ZIL0210 warning tracking)
                if hasattr(self, 'used_locals'):
                    self.used_locals.add(node.name)
                return (2, var_num)
            # In ZIL, .X falls back to global if no local exists
            elif node.name in self.globals:
                # ZIL0204: no such local variable 'X', using the global instead
                self._warn(f"ZIL0204: no such local variable '{node.name}', using the global instead")
                return (2, self.globals[node.name])
            elif node.name in self.constants:
                # ZIL0204: no such local variable 'X', using the constant instead
                self._warn(f"ZIL0204: no such local variable '{node.name}', using the constant instead")
                const_val = self.constants[node.name]
                if 0 <= const_val <= 255:
                    return (1, const_val)
                else:
                    return (0, const_val)
            elif node.name in self.objects:
                # ZIL0204: no such local variable 'X', using the object instead
                self._warn(f"ZIL0204: no such local variable '{node.name}', using the object instead")
                obj_num = self.objects[node.name]
                if 0 <= obj_num <= 255:
                    return (1, obj_num)
                else:
                    return (0, obj_num)
            else:
                self._warn(f"Unknown variable '{node.name}' - using default")
                return (2, 1)
        elif isinstance(node, TableNode):
            table_id = self._add_table(node)
            return (0, table_id)  # Table addresses are typically large
        elif isinstance(node, AtomNode):
            if node.value in self.constants:
                const_val = self.constants[node.value]
                if 0 <= const_val <= 255:
                    return (1, const_val)
                else:
                    return (0, const_val)
            elif node.value in self.objects:
                obj_num = self.objects[node.value]
                if 0 <= obj_num <= 255:
                    return (1, obj_num)
                else:
                    return (0, obj_num)
            elif node.value in self.globals:
                return (2, self.globals[node.value])
            else:
                return (1, 0)  # Unknown, default to small constant 0
        else:
            return (1, 0)  # Default

    def _get_operand_type_and_value(self, node: ASTNode) -> Tuple[int, int]:
        """Get operand type (0=small const, 1=variable) and value/var number.

        Returns:
            Tuple of (type, value) where type is 0 for small constant, 1 for variable
        """
        if isinstance(node, NumberNode):
            return (0, node.value)  # Small constant
        elif isinstance(node, GlobalVarNode):
            # ,VARNAME syntax - can be global variable, object, constant, or routine
            if node.name in self.globals:
                return (1, self.globals[node.name])  # Global variable
            elif node.name in self.objects:
                return (0, self.objects[node.name])  # Object number (constant)
            elif node.name in self.constants:
                return (0, self.constants[node.name])  # Constant
            elif hasattr(self, '_routine_names') and node.name in self._routine_names:
                # Routine address reference (e.g., ,OTHER-ROUTINE)
                # Create a placeholder for the routine address
                placeholder_idx = self._next_placeholder_index
                self._routine_placeholders[placeholder_idx] = node.name
                self._next_placeholder_index += 1
                # Return large constant placeholder (0xFD00 | index)
                # This will be resolved by get_routine_fixups()
                return (0, 0xFD00 | placeholder_idx)
            else:
                self._warn(f"Unknown global/object '{node.name}' - using default")
                return (1, 0x10)  # Default to variable 0x10
        elif isinstance(node, LocalVarNode):
            # .VARNAME syntax - local variable reference, falls back to global
            var_num = self.locals.get(node.name)
            if var_num is not None:
                # Mark local as used (for ZIL0210 warning tracking)
                if hasattr(self, 'used_locals'):
                    self.used_locals.add(node.name)
                return (1, var_num)  # Variable
            # In ZIL, .X falls back to global if no local exists
            elif node.name in self.globals:
                # ZIL0204: no such local variable 'X', using the global instead
                self._warn(f"ZIL0204: no such local variable '{node.name}', using the global instead")
                return (1, self.globals[node.name])
            elif node.name in self.constants:
                # ZIL0204: no such local variable 'X', using the constant instead
                self._warn(f"ZIL0204: no such local variable '{node.name}', using the constant instead")
                return (0, self.constants[node.name])
            elif node.name in self.objects:
                # ZIL0204: no such local variable 'X', using the object instead
                self._warn(f"ZIL0204: no such local variable '{node.name}', using the object instead")
                return (0, self.objects[node.name])
            else:
                self._warn(f"Unknown variable '{node.name}' - using default")
                return (1, 1)  # Variable
        elif isinstance(node, TableNode):
            # Table literal - generate table and return placeholder address
            table_id = self._add_table(node)
            # Return large constant (table index as placeholder)
            return (0, table_id)
        elif isinstance(node, AtomNode):
            # Check for character literals first
            # !\x - escaped character literal (e.g., !\! = '!', !\n = newline)
            # \x - backslash character literal (e.g., \. = '.', \, = ',')
            char_code = self._parse_char_literal(node.value)
            if char_code is not None:
                return (0, char_code)
            # Check if it's a known constant
            if node.value in self.constants:
                return (0, self.constants[node.value])
            # Check if it's an object/room name
            elif node.value in self.objects:
                return (0, self.objects[node.value])
            # Check if it's a global variable
            elif node.value in self.globals:
                return (1, self.globals[node.value])
            # Check if it's a local variable
            elif node.value in self.locals:
                return (1, self.locals[node.value])
            # Check if it's a routine name (for routine address references like I-CANDLES)
            elif hasattr(self, '_routine_names') and node.value in self._routine_names:
                # Create a placeholder for the routine address
                placeholder_idx = self._next_placeholder_index
                self._routine_placeholders[placeholder_idx] = node.value
                self._next_placeholder_index += 1
                # Return large constant placeholder (0xFD00 | index)
                # This will be resolved by get_routine_fixups()
                return (0, 0xFD00 | placeholder_idx)
            # Unknown atom - warn and default to 0
            self._warn(f"Unknown identifier '{node.value}' - using 0")
            return (0, 0)
        elif isinstance(node, FormNode):
            # FormNode as operand - this typically means the calling code
            # should have evaluated it first. Return 0 (stack) since the
            # result should have been pushed to the stack.
            # Don't warn - this is expected when nested forms are used
            return (1, 0)  # Variable 0 = stack
        elif isinstance(node, CondNode):
            # CondNode as operand - COND can be used as an expression
            # The calling code should evaluate it first, result will be on stack
            return (1, 0)  # Variable 0 = stack
        elif isinstance(node, RepeatNode):
            # RepeatNode as operand - REPEAT returns a value via RETURN
            # The calling code should evaluate it first, result will be on stack
            return (1, 0)  # Variable 0 = stack
        elif isinstance(node, StringNode):
            # StringNode as operand - used when passing strings to routines
            # Add the string to the string table and create a placeholder
            # that will be resolved to the packed address later
            if self.string_table is not None:
                self.string_table.add_string(node.value)
            # Create a placeholder: 0xFC + index
            placeholder_idx = self._next_string_placeholder_index
            self._string_placeholders[placeholder_idx] = node.value
            self._next_string_placeholder_index += 1
            # Return large constant with placeholder marker
            # Format: 0xFC00 | index (will be resolved by assembler)
            return (0, 0xFC00 | placeholder_idx)
        else:
            self._warn(f"Cannot determine operand type for {type(node).__name__} - using 0")
            return (0, 0)

    def gen_sub(self, operands: List[ASTNode]) -> bytes:
        """Generate SUB instruction.

        Handles variadic subtraction:
        - 0 operands: returns 0 (identity)
        - 1 operand: negation (0 - value)
        - 2 operands: a - b
        - 3+ operands: a - b - c - ...
        """
        if len(operands) == 0:
            return self._gen_push_const(0)

        if len(operands) == 1:
            # Negation: 0 - value
            zero_node = NumberNode(0)
            return self._gen_2op_store(0x15, zero_node, operands[0])

        if len(operands) == 2:
            # SUB is 2OP opcode 0x15 (21 decimal)
            return self._gen_2op_store(0x15, operands[0], operands[1])

        # 3+ operands: chain subtractions (a - b - c - ...)
        code = bytearray()
        code.extend(self._gen_2op_store(0x15, operands[0], operands[1]))
        for i in range(2, len(operands)):
            code.extend(self._gen_2op_store_with_stack(0x15, operands[i]))
        return bytes(code)

    def gen_mul(self, operands: List[ASTNode]) -> bytes:
        """Generate MUL instruction.

        Handles variadic multiplication:
        - 0 operands: returns 1 (identity)
        - 1 operand: returns that operand
        - 2 operands: a * b
        - 3+ operands: a * b * c * ...
        """
        # MUL is 2OP opcode 0x16 (22 decimal)
        return self._gen_variadic_arith(0x16, operands, identity=1)

    def gen_div(self, operands: List[ASTNode]) -> bytes:
        """Generate DIV instruction.

        Handles variadic division:
        - 0 operands: returns 1 (identity)
        - 1 operand: 1 / value (integer division)
        - 2 operands: a / b
        - 3+ operands: a / b / c / ...
        """
        if len(operands) == 0:
            return self._gen_push_const(1)

        if len(operands) == 1:
            # 1 / value
            one_node = NumberNode(1)
            return self._gen_2op_store(0x17, one_node, operands[0])

        if len(operands) == 2:
            # DIV is 2OP opcode 0x17 (23 decimal)
            return self._gen_2op_store(0x17, operands[0], operands[1])

        # 3+ operands: chain divisions
        code = bytearray()
        code.extend(self._gen_2op_store(0x17, operands[0], operands[1]))
        for i in range(2, len(operands)):
            code.extend(self._gen_2op_store_with_stack(0x17, operands[i]))
        return bytes(code)

    def gen_mod(self, operands: List[ASTNode]) -> bytes:
        """Generate MOD instruction.

        MOD requires exactly 2 operands.
        """
        if len(operands) != 2:
            self._error(f"MOD requires exactly 2 operands, got {len(operands)}")

        # MOD is 2OP opcode 0x18 (24 decimal)
        return self._gen_2op_store(0x18, operands[0], operands[1])

    def gen_add1(self, operands: List[ASTNode]) -> bytes:
        """Generate 1+ (add 1 to value).

        <1+ value> is a shorthand for <+ value 1>

        Args:
            operands[0]: Value to increment

        Returns:
            bytes: Z-machine code (ADD value 1)
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # ADD is 2OP opcode 0x14
        # First operand from input, second is constant 1
        opcode = 0x14 | (op_type << 6)  # second operand is always small const
        code.append(opcode)
        code.append(op_val & 0xFF)
        code.append(0x01)  # Add 1
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_sub1(self, operands: List[ASTNode]) -> bytes:
        """Generate 1- (subtract 1 from value).

        <1- value> is a shorthand for <- value 1>

        Args:
            operands[0]: Value to decrement

        Returns:
            bytes: Z-machine code (SUB value 1)
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # SUB is 2OP opcode 0x15
        # First operand from input, second is constant 1
        opcode = 0x15 | (op_type << 6)  # second operand is always small const
        code.append(opcode)
        code.append(op_val & 0xFF)
        code.append(0x01)  # Subtract 1
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_min(self, operands: List[ASTNode]) -> bytes:
        """Generate MIN (minimum of two values).

        <MIN a b> returns the smaller of two values.
        Uses JL comparison: if a < b, return a, else return b.

        Code structure:
          JL a b ?use_a    ; jump if a < b
          STORE result b   ; a >= b, use b
          JUMP end
        use_a:
          STORE result a
        end:
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Both constants - compute at compile time
        if op1_type == 0 and op2_type == 0:
            # Handle signed comparison
            a = op1_val if op1_val < 0x8000 else op1_val - 0x10000
            b = op2_val if op2_val < 0x8000 else op2_val - 0x10000
            result = min(a, b) & 0xFFFF
            # Push constant: use STORE sp const via VAR form
            code.append(0xE0)  # VAR:CALL_VS but we'll use different approach
            # Simpler: use ADD 0 const -> sp
            code.append(0x54)  # 2OP long: ADD with const, const
            code.append(0x00)  # 0
            code.append(result & 0xFF)
            code.append(0x00)  # Store to stack
            return bytes(code)

        # JL a b ?use_a (offset will be calculated)
        # 2OP opcode 0x02 = JL
        opcode = 0x02 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        # Branch offset: skip store_b + jump = need to calculate
        # Store b: LOAD var (3 bytes) or ADD 0 const (4 bytes)
        # JUMP end: 3 bytes (1OP JUMP + 2 byte offset)
        if op2_type == 1:
            store_b_len = 3  # LOAD var, store
            store_a_len = 3
        else:
            store_b_len = 4  # ADD 0 const, store
            store_a_len = 4 if op1_type == 0 else 3
        jump_len = 3
        branch_offset = store_b_len + jump_len + 2  # +2 for branch byte calculation
        code.append(0x40 | (branch_offset & 0x3F))  # Short branch, true polarity

        # Store b (a >= b case)
        if op2_type == 1:  # Variable
            code.append(0x9E)  # 1OP LOAD var (10 01 1110) with small const type
            code.append(op2_val & 0xFF)
            code.append(0x00)  # Store to stack
        else:  # Constant
            code.append(0x54)  # ADD 0 const
            code.append(0x00)
            code.append(op2_val & 0xFF)
            code.append(0x00)  # Store to stack

        # JUMP past store_a (short unconditional jump)
        # 1OP JUMP is 0x8C in short form with large constant
        jump_offset = store_a_len + 2  # Offset from next instruction
        code.append(0x8C)  # JUMP
        code.append((jump_offset >> 8) & 0xFF)
        code.append(jump_offset & 0xFF)

        # use_a: Store a
        if op1_type == 1:  # Variable
            code.append(0x9E)  # LOAD var (10 01 1110) with small const type
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Store to stack
        else:  # Constant
            code.append(0x54)  # ADD 0 const
            code.append(0x00)
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_max(self, operands: List[ASTNode]) -> bytes:
        """Generate MAX (maximum of two values).

        <MAX a b> returns the larger of two values.
        Uses JG comparison: if a > b, return a, else return b.

        Code structure:
          JG a b ?use_a    ; jump if a > b
          STORE result b   ; a <= b, use b
          JUMP end
        use_a:
          STORE result a
        end:
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Both constants - compute at compile time
        if op1_type == 0 and op2_type == 0:
            a = op1_val if op1_val < 0x8000 else op1_val - 0x10000
            b = op2_val if op2_val < 0x8000 else op2_val - 0x10000
            result = max(a, b) & 0xFFFF
            code.append(0x54)  # ADD 0 const
            code.append(0x00)
            code.append(result & 0xFF)
            code.append(0x00)  # Store to stack
            return bytes(code)

        # JG a b ?use_a
        # 2OP opcode 0x03 = JG
        opcode = 0x03 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        if op2_type == 1:
            store_b_len = 3
            store_a_len = 3
        else:
            store_b_len = 4
            store_a_len = 4 if op1_type == 0 else 3
        jump_len = 3
        branch_offset = store_b_len + jump_len + 2
        code.append(0x40 | (branch_offset & 0x3F))

        # Store b (a <= b case)
        if op2_type == 1:
            code.append(0x8E)
            code.append(op2_val & 0xFF)
            code.append(0x00)
        else:
            code.append(0x54)
            code.append(0x00)
            code.append(op2_val & 0xFF)
            code.append(0x00)

        # JUMP past store_a
        jump_offset = store_a_len + 2
        code.append(0x8C)
        code.append((jump_offset >> 8) & 0xFF)
        code.append(jump_offset & 0xFF)

        # use_a: Store a
        if op1_type == 1:
            code.append(0x8E)
            code.append(op1_val & 0xFF)
            code.append(0x00)
        else:
            code.append(0x54)
            code.append(0x00)
            code.append(op1_val & 0xFF)
            code.append(0x00)

        return bytes(code)

    def gen_abs(self, operands: List[ASTNode]) -> bytes:
        """Generate ABS (absolute value).

        <ABS value> returns the absolute value of a number.

        Code structure:
          JL value 0 ?negate   ; jump if value < 0
          STORE result value   ; positive case
          JUMP end
        negate:
          SUB 0 value -> result ; negate
        end:
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # Constant - compute at compile time
        if op_type == 0:
            val = op_val if op_val < 0x8000 else op_val - 0x10000
            result = abs(val) & 0xFFFF
            code.append(0x54)  # ADD 0 const
            code.append(0x00)
            code.append(result & 0xFF)
            code.append(0x00)  # Store to stack
            return bytes(code)

        # Variable - need runtime check
        # JL value 0 ?negate
        code.append(0x42)  # JL var const
        code.append(op_val & 0xFF)
        code.append(0x00)  # Compare with 0
        # Branch offset: LOAD (3) + JUMP (3) + 2 = 8
        code.append(0x48)  # Short branch, offset 8

        # Positive case: just load the value
        code.append(0x9E)  # LOAD var (10 01 1110) with small const type
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        # JUMP past negate (SUB is 4 bytes)
        code.append(0x8C)  # JUMP
        code.append(0x00)
        code.append(0x06)  # Offset 6

        # negate: SUB 0 value -> stack (0 - value = -value)
        code.append(0x55)  # SUB const var
        code.append(0x00)  # 0
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def _gen_abs_old(self, operands: List[ASTNode]) -> bytes:
        """Old stub implementation - kept for reference."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 1:  # Variable
            code.append(0x9E)  # LOAD var (10 01 1110) with small const type
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store to stack
        else:  # Constant - can compute at compile time
            abs_val = abs(op_val) if op_val < 0x8000 else abs(op_val - 0x10000)
            code.append(0x9E)  # Use LOAD pattern with small const type
            code.append(op_val & 0xFF)
            code.append(0x00)

        return bytes(code)

    def gen_sound(self, operands: List[ASTNode]) -> bytes:
        """Generate SOUND (play sound effect).

        <SOUND effect action volume routine> plays a sound effect.
        V3: 1-3 operands
        V5+: 1-4 operands

        Args:
            operands[0]: Sound effect number (1-N)
            operands[1]: Action (optional)
            operands[2]: Volume (optional)
            operands[3]: Routine (V5+ only, optional)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 5:
            if len(operands) < 1 or len(operands) > 3:
                raise ValueError("SOUND requires 1-3 operands in V3/V4")
        else:
            if len(operands) < 1 or len(operands) > 4:
                raise ValueError("SOUND requires 1-4 operands in V5+")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xE5)  # SOUND_EFFECT (VAR opcode 0x05)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_clear(self, operands: List[ASTNode]) -> bytes:
        """Generate CLEAR (clear window - V4+).

        <CLEAR window> clears the specified window.
        V4+ only. Window -1 means clear entire screen.

        Args:
            operands[0]: Window number

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            raise ValueError("CLEAR requires V4 or later")
        if len(operands) != 1:
            raise ValueError("CLEAR requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xED)  # ERASE_WINDOW (VAR opcode 0x0D)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_erase(self, operands: List[ASTNode]) -> bytes:
        """Generate ERASE (erase line/window - V4+).

        <ERASE value> erases line or window based on value.
        V4+ only.

        Args:
            operands[0]: Erase value

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            raise ValueError("ERASE requires V4 or later")
        if len(operands) != 1:
            raise ValueError("ERASE requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # Use ERASE_LINE (VAR opcode 0x0E)
        code.append(0xEE)  # ERASE_LINE (VAR opcode 0x0E)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_erase_window(self, operands: List[ASTNode]) -> bytes:
        """Generate ERASE_WINDOW (V4+ - clear window).

        <ERASE_WINDOW window> clears specified window.
        -1 = unsplit screen, -2 = clear without unsplitting.
        Alias for CLEAR with parameter. VAR:0x0D.

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            # No parameter, clear entire screen
            return self.gen_clear([])

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xED)  # ERASE_WINDOW (VAR opcode 0x0D)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_split(self, operands: List[ASTNode]) -> bytes:
        """Generate SPLIT (split window).

        <SPLIT lines> splits the screen into upper and lower windows.
        In V3+, this is the SPLIT_WINDOW opcode (VAR opcode 0x0A).

        Args:
            operands[0]: Number of lines for upper window

        Returns:
            bytes: Z-machine code
        """
        if len(operands) != 1:
            raise ValueError("SPLIT requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xEA)  # SPLIT_WINDOW (VAR opcode 0x0A)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_screen(self, operands: List[ASTNode]) -> bytes:
        """Generate SCREEN (select window).

        <SCREEN window> selects which window to write to.
        In V3+, this is the SET_WINDOW opcode (VAR opcode 0x0B).

        Args:
            operands[0]: Window number (0=lower, 1=upper)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) != 1:
            raise ValueError("SCREEN requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xEB)  # SET_WINDOW (VAR opcode 0x0B)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_split_window(self, operands: List[ASTNode]) -> bytes:
        """Generate SPLIT_WINDOW (V3+ - split screen).

        <SPLIT_WINDOW lines> divides screen into windows.
        Alias for SPLIT. VAR:0x0A.

        Returns:
            bytes: Z-machine code
        """
        # Delegate to SPLIT implementation
        return self.gen_split(operands)

    def gen_set_window(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_WINDOW (V3+ - select window).

        <SET_WINDOW window> selects active window.
        Alias for SCREEN. VAR:0x0B.

        Returns:
            bytes: Z-machine code
        """
        # Delegate to SCREEN implementation
        return self.gen_screen(operands)

    def gen_curset(self, operands: List[ASTNode]) -> bytes:
        """Generate CURSET (set cursor position - V4+).

        <CURSET line column> sets cursor to specified position.
        V4+ only. Uses SET_CURSOR opcode (VAR opcode 0x0F).

        Args:
            operands[0]: Line number (1-based)
            operands[1]: Column number (1-based)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            raise ValueError("CURSET requires V4 or later")
        if len(operands) != 2:
            raise ValueError("CURSET requires exactly 2 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        code.append(0xF1)  # SET_CURSOR (VAR opcode 0x11)
        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | 0x0F)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_set_cursor(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_CURSOR (V4+ - position cursor).

        <SET_CURSOR line column window> sets cursor position.
        Alias for CURSET. VAR:0x0F.

        Returns:
            bytes: Z-machine code
        """
        # Delegate to CURSET implementation
        return self.gen_curset(operands)

    def gen_get_cursor(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_CURSOR (V4+ - get cursor position).

        <GET_CURSOR table> stores cursor position (line, column) in table.
        VAR:0x10.

        Args:
            operands[0]: Table address to store position

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            raise ValueError("CURGET requires V4 or later")
        if len(operands) != 1:
            raise ValueError("CURGET requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_CURSOR is VAR opcode 0x10
        code.append(0xF0)  # GET_CURSOR (VAR:0x10)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_erase_line(self, operands: List[ASTNode]) -> bytes:
        """Generate ERASE_LINE (V4+ - clear to end of line).

        <ERASE_LINE value> clears from cursor to end of line.
        Value 1 clears to end of line, 0 does nothing.
        VAR:0x0E.

        Args:
            operands[0]: Value (1 = clear, 0 = no-op)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            return b''

        code = bytearray()
        if operands:
            op_type, op_val = self._get_operand_type_and_value(operands[0])
        else:
            op_type, op_val = 0, 1  # Default to clear

        # ERASE_LINE is VAR opcode 0x0E
        code.append(0xEE)  # ERASE_LINE
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_move_window(self, operands: List[ASTNode]) -> bytes:
        """Generate MOVE_WINDOW (V6 - reposition window).

        <MOVE_WINDOW window y x> moves window to new position.
        V6 only. EXT:0x10.

        Args:
            operands[0]: Window number
            operands[1]: Y coordinate
            operands[2]: X coordinate

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # MOVE_WINDOW is EXT opcode 0x10
        code.append(0xBE)  # EXT opcode marker
        code.append(0x10)  # MOVE_WINDOW

        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        t3 = 0x01 if op3_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | (t3 << 2) | 0x03)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_window_size(self, operands: List[ASTNode]) -> bytes:
        """Generate WINDOW_SIZE (V6 - resize window).

        <WINDOW_SIZE window height width> sets window dimensions.
        V6 only. EXT:0x11.
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        code.append(0xBE)  # EXT opcode marker
        code.append(0x11)  # WINDOW_SIZE

        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        t3 = 0x01 if op3_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | (t3 << 2) | 0x03)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_scroll_window(self, operands: List[ASTNode]) -> bytes:
        """Generate SCROLL_WINDOW (V6 - scroll window contents). V6 only. EXT:0x14."""
        if self.version < 6:
            raise ValueError("SCROLL requires V6")
        if len(operands) > 4:
            raise ValueError("SCROLL accepts at most 4 operands")

        code = bytearray()
        code.append(0xBE)  # EXT opcode marker
        code.append(0x14)  # SCROLL_WINDOW

        # Build type byte and operands
        type_parts = []
        for i in range(4):
            if i < len(operands):
                op_type, _ = self._get_operand_type_and_value(operands[i])
                type_parts.append(0x01 if op_type == 0 else 0x02)
            else:
                type_parts.append(0x03)  # Omitted

        type_byte = (type_parts[0] << 6) | (type_parts[1] << 4) | (type_parts[2] << 2) | type_parts[3]
        code.append(type_byte)

        for op in operands:
            _, op_val = self._get_operand_type_and_value(op)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_get_wind_prop(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_WIND_PROP (V6 - get window property). V6 only. EXT:0x13."""
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        code.append(0xBE)  # EXT opcode marker
        code.append(0x13)  # GET_WIND_PROP

        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | 0x0F)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_put_wind_prop(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT_WIND_PROP (V6 - set window property). V6 only. EXT:0x19."""
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        code.append(0xBE)  # EXT opcode marker
        code.append(0x19)  # PUT_WIND_PROP

        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        t3 = 0x01 if op3_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | (t3 << 2) | 0x03)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_window_style(self, operands: List[ASTNode]) -> bytes:
        """Generate WINDOW_STYLE (V6 - modify window attributes). V6 only. EXT:0x12."""
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        code.append(0xBE)  # EXT opcode marker
        code.append(0x12)  # WINDOW_STYLE

        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        t3 = 0x01 if op3_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | (t3 << 2) | 0x03)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_mouse_window(self, operands: List[ASTNode]) -> bytes:
        """Generate MOUSE_WINDOW (V5+ - constrain mouse to window).

        <MOUSE_WINDOW window> constrains mouse cursor to specified window.
        Use -1 to remove restriction.
        V5+ only.

        Args:
            operands[0]: Window number (-1 to unconstrain)

        Returns:
            bytes: Z-machine code (MOUSE_WINDOW EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()

        # MOUSE_WINDOW is EXT opcode 0x17
        code.append(0xBE)  # EXT opcode marker
        code.append(0x17)  # MOUSE_WINDOW

        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 1:  # Variable
            code.append(0x02)  # Type: variable
        else:  # Constant
            code.append(0x01)  # Type: small constant
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_read_mouse(self, operands: List[ASTNode]) -> bytes:
        """Generate READ_MOUSE (V5+ - read mouse position and state).

        <READ_MOUSE array> retrieves mouse position, button state, and menu.
        Array receives 4 words: [y-coord, x-coord, button-flags, menu-selection]
        V5+ only.

        Args:
            operands[0]: Array address (4 words)

        Returns:
            bytes: Z-machine code (READ_MOUSE EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()

        # READ_MOUSE is EXT opcode 0x16
        code.append(0xBE)  # EXT opcode marker
        code.append(0x16)  # READ_MOUSE

        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 1:  # Variable
            code.append(0x02)  # Type: variable
        else:  # Constant
            code.append(0x01)  # Type: small constant
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_buffer_screen(self, operands: List[ASTNode]) -> bytes:
        """Generate BUFFER_SCREEN (V6 - control display buffering).

        <BUFFER_SCREEN mode> controls display buffering strategy.
        Returns previous buffering mode.
        V6 only. Mode: 0=unbuffered, 1=buffered.

        Args:
            operands[0]: Buffering mode (0 or 1)

        Returns:
            bytes: Z-machine code (BUFFER_SCREEN EXT opcode)
        """
        if not operands or self.version < 6:
            return b''

        code = bytearray()

        # BUFFER_SCREEN is EXT opcode 0x1D
        code.append(0xBE)  # EXT opcode marker
        code.append(0x1D)  # BUFFER_SCREEN

        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 1:  # Variable
            code.append(0x02)  # Type: variable
        else:  # Constant
            code.append(0x01)  # Type: small constant
        code.append(op_val & 0xFF)
        # Store result (old mode) to stack
        code.append(0x00)

        return bytes(code)

    def gen_hlight(self, operands: List[ASTNode]) -> bytes:
        """Generate HLIGHT (set text style/highlighting).

        <HLIGHT style> sets text style (bold, italic, reverse, etc).
        In V4+, this is the SET_TEXT_STYLE opcode (VAR opcode 0x11).

        Styles: 0=normal, 1=reverse, 2=bold, 4=italic, 8=fixed

        Args:
            operands[0]: Style flags

        Returns:
            bytes: Z-machine code
        """
        if len(operands) != 1:
            raise ValueError("HLIGHT requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xF1)  # SET_TEXT_STYLE (VAR opcode 0x11)
        if op_type == 1:  # Variable
            code.append(0x8F)  # Type byte: 1 variable, rest omitted
        else:  # Constant
            code.append(0x2F)  # Type byte: 1 small constant, rest omitted
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_set_text_style(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_TEXT_STYLE (V4+ - set text formatting).

        <SET_TEXT_STYLE style> applies text formatting.
        Alias for HLIGHT. VAR:0x11.

        Returns:
            bytes: Z-machine code
        """
        # Delegate to HLIGHT implementation
        return self.gen_hlight(operands)

    def gen_input(self, operands: List[ASTNode]) -> bytes:
        """Generate INPUT (read text input).

        <INPUT buffer parse time routine> reads a line of text from the player.
        V3: SREAD (VAR:0x04) with buffer and parse (2 operands)
        V4: 2-3 operands
        V5+: 1-4 operands

        Args:
            operands[0]: Text buffer address
            operands[1]: Parse buffer address (optional in V5+)
            operands[2]: Time in tenths of seconds (V4+, optional)
            operands[3]: Routine to call on timeout (V5+, optional)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            if len(operands) != 2:
                raise ValueError("INPUT requires exactly 2 operands in V3")
        elif self.version == 4:
            if len(operands) < 2 or len(operands) > 3:
                raise ValueError("INPUT requires 2-3 operands in V4")
        else:
            if len(operands) < 1 or len(operands) > 4:
                raise ValueError("INPUT requires 1-4 operands in V5+")

        code = bytearray()
        num_ops = len(operands)

        # SREAD/AREAD is VAR opcode 0x04
        code.append(0xE4)  # VAR opcode 0x04

        # Build type byte based on number of operands
        type_byte = 0x00
        for i in range(4):
            if i < num_ops:
                type_byte |= (0x01 << (6 - i*2))  # Small constant
            else:
                type_byte |= (0x03 << (6 - i*2))  # Omitted

        code.append(type_byte)

        # Add operands
        for i in range(min(num_ops, 4)):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_sread(self, operands: List[ASTNode]) -> bytes:
        """Generate SREAD (V3/V4 read text input).

        <SREAD buffer parse time routine> reads text input.
        Alias for INPUT. In V3/V4 called SREAD, V5+ called AREAD.

        Returns:
            bytes: Z-machine code
        """
        # Delegate to INPUT implementation
        return self.gen_input(operands)

    def gen_aread(self, operands: List[ASTNode]) -> bytes:
        """Generate AREAD (V5+ read text input).

        <AREAD buffer parse time routine> reads text input.
        Alias for INPUT. V5+ name for SREAD.

        Returns:
            bytes: Z-machine code
        """
        # Delegate to INPUT implementation
        return self.gen_input(operands)

    def gen_bufout(self, operands: List[ASTNode]) -> bytes:
        """Generate BUFOUT (buffer mode control).

        <BUFOUT mode> enables/disables output buffering.
        In V4+, this is the BUFFER_MODE opcode (VAR opcode 0x11).
        Mode: 0=disable buffering, 1=enable buffering

        Args:
            operands[0]: Mode (0 or 1)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            raise ValueError("BUFOUT requires V4 or later")
        if len(operands) != 1:
            raise ValueError("BUFOUT requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xF1)  # BUFFER_MODE (VAR opcode 0x11)
        # VAR opcode type byte: 2 bits per operand (00=large, 01=small, 10=var, 11=omit)
        if op_type == 1:  # Variable
            code.append(0xBF)  # Type byte: 10 11 11 11 = variable, omit, omit, omit
        else:  # Small constant
            code.append(0x7F)  # Type byte: 01 11 11 11 = small, omit, omit, omit
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_buffer_mode(self, operands: List[ASTNode]) -> bytes:
        """Generate BUFFER_MODE (V4+ buffer mode control).

        <BUFFER_MODE flag> enables/disables text buffering.
        Alias for BUFOUT. V4+.

        Args:
            operands[0]: Flag (0=disable, 1=enable)

        Returns:
            bytes: Z-machine code
        """
        # Delegate to BUFOUT implementation
        return self.gen_bufout(operands)

    # gen_get_cursor is defined earlier - this duplicate was removed

    def gen_uxor(self, operands: List[ASTNode]) -> bytes:
        """Generate UXOR (unsigned XOR).

        <UXOR val1 val2> computes bitwise XOR of two values.
        Z-machine has no native XOR, so we simulate with AND/OR/NOT:
        XOR(A, B) = (A OR B) AND NOT(A AND B)

        Args:
            operands[0]: First value
            operands[1]: Second value

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Compile-time evaluation for constants
        if op1_type == 0 and op2_type == 0:
            result = op1_val ^ op2_val
            # Use ADD 0 result to push constant to stack
            code.append(0x54)  # ADD const const -> store
            code.append(0x00)  # 0
            code.append(result & 0xFF)
            code.append(0x00)  # Store to stack
            return bytes(code)

        # XOR simulation: (A OR B) AND NOT(A AND B)
        # Step 1: A AND B → stack
        and_opcode = 0x09 | (op1_type << 6) | (op2_type << 5)
        code.append(and_opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        # Step 2: NOT stack → stack
        # NOT is 1OP opcode 0x0F, 0x9F for variable operand
        code.append(0x9F)  # NOT with variable operand
        code.append(0x00)  # Stack (var 0)
        code.append(0x00)  # Store to stack

        # Step 3: A OR B → stack
        or_opcode = 0x08 | (op1_type << 6) | (op2_type << 5)
        code.append(or_opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        # Step 4: AND stack stack → stack
        # Stack now has: [NOT(A AND B), A OR B]
        # AND pops both and pushes (A OR B) AND NOT(A AND B) = XOR
        # Long form: opcode | (op1_type << 6) | (op2_type << 5)
        # For two variables: 0x09 | (1 << 6) | (1 << 5) = 0x69
        code.append(0x69)  # AND with var, var in long form
        code.append(0x00)  # First operand: stack (var 0)
        code.append(0x00)  # Second operand: stack (var 0)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_usl(self, operands: List[ASTNode]) -> bytes:
        """Generate USL (set status line update - V3 only).

        <USL> enables status line updates in V3.
        V3 only, no operands.

        Returns:
            bytes: Z-machine code
        """
        if self.version >= 4:
            raise ValueError("USL is only available in V3")
        if operands:
            raise ValueError("USL takes no operands")

        # USL is effectively a no-op in compiled code
        # It's a hint to the interpreter
        return b''

    def gen_dirout(self, operands: List[ASTNode]) -> bytes:
        """Generate DIROUT (direct output to memory).

        <DIROUT stream [table [width]]> directs output to a stream.
        In V3+, this is the OUTPUT_STREAM opcode (VAR 0x13).
        Stream 3 = redirect to table.

        Args:
            operands[0]: Stream number
            operands[1]: Table address (for stream 3)
            operands[2]: Width (V6 only)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            raise ValueError("DIROUT requires at least 1 operand")
        if self.version < 6 and len(operands) > 2:
            raise ValueError("DIROUT accepts at most 2 operands (3 in V6)")
        if len(operands) > 3:
            raise ValueError("DIROUT accepts at most 3 operands")

        code = bytearray()

        code.append(0xF3)  # OUTPUT_STREAM (VAR opcode 0x13)

        # Build operand types and values
        # VAR type byte: 2 bits per operand (00=large, 01=small, 10=var, 11=omit)
        op_types = []
        op_vals = []
        for operand in operands:
            # Use _ext version which returns correct VAR type codes
            op_type, op_val = self._get_operand_type_and_value_ext(operand)
            op_types.append(op_type)
            op_vals.append(op_val)

        # Build type byte (up to 4 operands, rest are 11=omit)
        type_byte = 0
        for i in range(4):
            if i < len(op_types):
                type_byte = (type_byte << 2) | op_types[i]
            else:
                type_byte = (type_byte << 2) | 3  # 11 = omit
        code.append(type_byte)

        # Write operand values with appropriate byte count
        for i, op_val in enumerate(op_vals):
            if op_types[i] == 0:  # Large constant (2 bytes)
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
            else:  # Small constant or variable (1 byte)
                code.append(op_val & 0xFF)

        return bytes(code)

    def gen_output_stream(self, operands: List[ASTNode]) -> bytes:
        """Generate OUTPUT_STREAM (redirect output - V3+).

        <OUTPUT_STREAM stream table> redirects text output.
        Alias for DIROUT. Stream 3 redirects to memory table.

        Args:
            operands[0]: Stream number (1=screen, 2=transcript, 3=memory, 4=commands)
            operands[1]: Table address (for stream 3 only, optional)

        Returns:
            bytes: Z-machine code
        """
        # Delegate to DIROUT implementation
        return self.gen_dirout(operands)

    def gen_input_stream(self, operands: List[ASTNode]) -> bytes:
        """Generate INPUT_STREAM (select input source - V3+).

        <INPUT_STREAM stream> selects input source.
        0=keyboard, 1=file (playback).

        Args:
            operands[0]: Stream number

        Returns:
            bytes: Z-machine code (INPUT_STREAM VAR opcode)
        """
        if len(operands) != 1:
            raise ValueError("DIRIN requires exactly 1 operand")

        code = bytearray()

        # INPUT_STREAM is VAR opcode 0x14
        code.append(0xF4)  # VAR opcode 0x14

        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # VAR opcode type byte: 2 bits per operand (00=large, 01=small, 10=var, 11=omit)
        if op_type == 1:  # Variable
            code.append(0xBF)  # Type byte: 10 11 11 11 = variable, omit, omit, omit
        else:  # Small constant
            code.append(0x7F)  # Type byte: 01 11 11 11 = small, omit, omit, omit
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_copy_table(self, operands: List[ASTNode]) -> bytes:
        """Generate COPY_TABLE (V5+ table copy/zero).

        <COPY_TABLE first second size> copies or zeros table.
        Alias for COPYT. V5+ only.

        Args:
            operands[0]: Source address (0 to zero out dest)
            operands[1]: Destination address
            operands[2]: Size in bytes (negative = preserve first during copy)

        Returns:
            bytes: Z-machine code
        """
        # Delegate to COPYT implementation
        return self.gen_copyt(operands)

    def gen_mapf(self, operands: List[ASTNode]) -> bytes:
        """Generate MAPF (map first/apply to each).

        <MAPF ,routine table length> applies routine to each element in table.
        Generates inline loop for small tables, runtime loop for larger ones.

        Args:
            operands[0]: Routine to call (often a GVAL reference)
            operands[1]: Table address
            operands[2]: Number of elements (optional)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        routine_type, routine_val = self._get_operand_type_and_value(operands[0])
        table_type, table_val = self._get_operand_type_and_value(operands[1])

        # Get length if provided
        length_type, length_val = (0, 0)
        if len(operands) >= 3:
            length_type, length_val = self._get_operand_type_and_value(operands[2])

        # Check if we can use compile-time known length for unrolling
        length = self.get_operand_value(operands[2]) if len(operands) >= 3 else None

        # For small compile-time known lengths, unroll the loop
        if isinstance(length, int) and length > 0 and length <= 8:
            for i in range(length):
                offset = i * 2  # Word-sized elements

                # LOADW table offset -> sp (get element)
                # Use 2OP long form: opcode | (op1_type << 6) | (op2_type << 5)
                opcode = 0x0F | (table_type << 6) | (0 << 5)  # offset is always small const
                code.append(opcode)
                code.append(table_val & 0xFF)
                code.append(offset & 0xFF)
                code.append(0x00)  # Store to stack

                # CALL_VN routine sp - call with element, discard result
                code.append(0xF9)  # CALL_VN (VAR)
                types = []
                types.append(0x01 if routine_type == 0 else 0x02)
                types.append(0x02)  # stack (element)
                types.append(0x03)  # omit
                types.append(0x03)  # omit
                type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
                code.append(type_byte)
                code.append(routine_val & 0xFF)
                code.append(0x00)  # Stack (element)

            return bytes(code)

        # For runtime-determined lengths or larger tables, generate a loop
        # L01 = counter, L02 = offset, L03 = table address (if variable)

        # Initialize counter from length operand
        if len(operands) >= 3:
            # STORE L01 length
            code.append(0xE5)  # STOREW (VAR) - but we want STORE
            # Use 0xCD for STORE (2OP:13)
            code[-1] = 0x0D | (length_type << 6) | (0 << 5)  # STORE local var
            code.append(0x01)  # L01 = counter
            code.append(length_val & 0xFF)
        else:
            # Default length 8 if not specified
            code.append(0x0D)  # STORE
            code.append(0x01)  # L01
            code.append(0x00)
            code.append(0x08)  # Default 8

        # Initialize offset to 0
        code.append(0x0D)  # STORE
        code.append(0x02)  # L02 = offset
        code.append(0x00)
        code.append(0x00)

        # If table is a variable, store in L03
        if table_type == 1:
            code.append(0x0D | (1 << 6))  # STORE from var
            code.append(0x03)  # L03 = table
            code.append(table_val & 0xFF)

        # Loop start
        loop_start = len(code)

        # LOADW table L02 -> sp (get current element)
        code.append(0xCF)  # LOADW (VAR form)
        if table_type == 0:
            # Constant table
            if table_val <= 255:
                code.append(0x5F)  # small const, var, omit, omit
                code.append(table_val & 0xFF)
            else:
                code.append(0x1F)  # large const, var, omit, omit
                code.append((table_val >> 8) & 0xFF)
                code.append(table_val & 0xFF)
        else:
            # Variable table (stored in L03)
            code.append(0xAF)  # var, var, omit, omit
            code.append(0x03)  # L03
        code.append(0x02)  # L02 (offset)
        code.append(0x00)  # Store to stack

        # CALL_VN routine sp - call with element
        code.append(0xF9)  # CALL_VN
        types = []
        types.append(0x01 if routine_type == 0 else 0x02)
        types.append(0x02)  # stack
        types.append(0x03)  # omit
        types.append(0x03)  # omit
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(routine_val & 0xFF)
        code.append(0x00)  # Stack (element)

        # ADD L02 2 -> L02 (increment offset by word size)
        code.append(0x54)  # ADD (2OP:20) small, small
        code.append(0x02)  # L02
        code.append(0x02)  # constant 2
        code.append(0x02)  # -> L02

        # DEC_CHK L01 0 [loop_start] - decrement and branch if > 0
        code.append(0x04)  # DEC_CHK (2OP:4)
        code.append(0x01)  # L01
        code.append(0x00)  # Compare to 0
        # Calculate backward jump
        current_pos = len(code) + 2
        jump_offset = loop_start - current_pos
        if jump_offset >= -64:
            code.append(0x00 | ((jump_offset + 2) & 0x3F))  # Branch on false
        else:
            jump_offset_unsigned = (1 << 14) + jump_offset
            code.append(0x00 | ((jump_offset_unsigned >> 8) & 0x3F))
            code.append(jump_offset_unsigned & 0xFF)

        return bytes(code)

    def gen_mapt(self, operands: List[ASTNode]) -> bytes:
        """Generate MAPT (map true/find first match).

        <MAPT ,routine table length> finds first element where routine returns true.
        Generates inline search for small tables, loop for larger ones.

        Args:
            operands[0]: Predicate routine
            operands[1]: Table to search
            operands[2]: Number of elements (optional)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        routine_type, routine_val = self._get_operand_type_and_value(operands[0])
        table_type, table_val = self._get_operand_type_and_value(operands[1])

        # Get length if provided
        length_type, length_val = (0, 8)  # Default to 8 elements
        if len(operands) >= 3:
            length_type, length_val = self._get_operand_type_and_value(operands[2])

        # Check if we can unroll (small compile-time constant length)
        length = self.get_operand_value(operands[2]) if len(operands) >= 3 else None

        # For small compile-time known tables, unroll search
        if isinstance(length, int) and length > 0 and length <= 8:
            for i in range(length):
                offset = i * 2  # Word-sized elements

                # LOADW table offset -> sp
                opcode = 0x0F | (table_type << 6) | (0 << 5)
                code.append(opcode)
                code.append(table_val & 0xFF)
                code.append(offset & 0xFF)
                code.append(0x00)  # Store to stack

                # CALL_VS routine sp -> sp (call predicate)
                code.append(0xE0)  # CALL_VS
                types = []
                types.append(0x01 if routine_type == 0 else 0x02)
                types.append(0x02)  # stack
                types.append(0x03)  # omit
                types.append(0x03)  # omit
                type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
                code.append(type_byte)
                code.append(routine_val & 0xFF)
                code.append(0x00)  # Stack argument
                code.append(0x00)  # Store result to stack

                # JZ sp [skip] - if zero, continue to next
                code.append(0x80)  # JZ (1OP)
                code.append(0x00)  # Stack
                code.append(0x40 | 6)  # Branch true, skip 6 bytes to next iter

                # Match found - load the element and return it
                opcode = 0x0F | (table_type << 6) | (0 << 5)
                code.append(opcode)
                code.append(table_val & 0xFF)
                code.append(offset & 0xFF)
                code.append(0x00)  # To stack
                code.append(0x8B)  # RET_POPPED - return element

            # No match found - return false
            code.append(0xB1)  # RFALSE
            return bytes(code)

        # For runtime-determined lengths or larger tables, generate loop
        # L01 = counter, L02 = offset, L03 = table address (if variable)

        # Initialize counter
        if len(operands) >= 3:
            code.append(0x0D | (length_type << 6))
            code.append(0x01)  # L01
            code.append(length_val & 0xFF)
        else:
            code.append(0x0D)
            code.append(0x01)
            code.append(0x00)
            code.append(0x08)

        # Initialize offset
        code.append(0x0D)
        code.append(0x02)  # L02 = offset
        code.append(0x00)
        code.append(0x00)

        # Store table in L03 if variable
        if table_type == 1:
            code.append(0x0D | (1 << 6))
            code.append(0x03)
            code.append(table_val & 0xFF)

        loop_start = len(code)

        # LOADW table L02 -> sp
        code.append(0xCF)  # LOADW (VAR form)
        if table_type == 0:
            if table_val <= 255:
                code.append(0x5F)
                code.append(table_val & 0xFF)
            else:
                code.append(0x1F)
                code.append((table_val >> 8) & 0xFF)
                code.append(table_val & 0xFF)
        else:
            code.append(0xAF)  # var, var
            code.append(0x03)  # L03
        code.append(0x02)  # L02
        code.append(0x00)  # -> stack

        # CALL_VS routine sp -> sp
        code.append(0xE0)  # CALL_VS
        types = []
        types.append(0x01 if routine_type == 0 else 0x02)
        types.append(0x02)  # stack
        types.append(0x03)
        types.append(0x03)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(routine_val & 0xFF)
        code.append(0x00)  # Stack arg
        code.append(0x00)  # -> stack

        # JZ sp [continue_loop] - branch to continue if result is 0
        code.append(0x80)  # JZ
        code.append(0x00)  # Stack
        # Calculate skip to continue (past the return code)
        return_code_size = 6 if table_type == 0 and table_val <= 255 else 7
        code.append(0x40 | return_code_size)

        # Match found - return the element
        code.append(0xCF)  # LOADW (VAR)
        if table_type == 0:
            if table_val <= 255:
                code.append(0x5F)
                code.append(table_val & 0xFF)
            else:
                code.append(0x1F)
                code.append((table_val >> 8) & 0xFF)
                code.append(table_val & 0xFF)
        else:
            code.append(0xAF)
            code.append(0x03)
        code.append(0x02)  # L02
        code.append(0x00)  # -> stack
        code.append(0x8B)  # RET_POPPED

        # Continue loop: increment offset
        code.append(0x54)  # ADD
        code.append(0x02)  # L02
        code.append(0x02)  # 2
        code.append(0x02)  # -> L02

        # DEC_CHK L01 0 [loop_start]
        code.append(0x04)  # DEC_CHK
        code.append(0x01)  # L01
        code.append(0x00)  # 0
        current_pos = len(code) + 2
        jump_offset = loop_start - current_pos
        if jump_offset >= -64:
            code.append(0x00 | ((jump_offset + 2) & 0x3F))
        else:
            jump_offset_unsigned = (1 << 14) + jump_offset
            code.append(0x00 | ((jump_offset_unsigned >> 8) & 0x3F))
            code.append(jump_offset_unsigned & 0xFF)

        # No match - return false
        code.append(0xB1)  # RFALSE

        return bytes(code)

    def gen_mapr(self, operands: List[ASTNode]) -> bytes:
        """Generate MAPR (map and return - collect results).

        <MAPR ,routine table length> applies routine to each element
        and returns the last non-false result.

        In true MDL, MAPR collects all non-false results into a list.
        In Z-machine, we approximate by tracking the last non-false result
        since we can't dynamically build lists at runtime.

        Args:
            operands[0]: Routine to call
            operands[1]: Table to iterate over
            operands[2]: Number of elements (optional)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        routine_type, routine_val = self._get_operand_type_and_value(operands[0])
        table_type, table_val = self._get_operand_type_and_value(operands[1])

        # Get length if provided
        length_type, length_val = (0, 8)  # Default to 8 elements
        if len(operands) >= 3:
            length_type, length_val = self._get_operand_type_and_value(operands[2])

        # Check if we can unroll (small compile-time constant length)
        length = self.get_operand_value(operands[2]) if len(operands) >= 3 else None

        # For small compile-time known tables, unroll
        if isinstance(length, int) and length > 0 and length <= 8:
            # Initialize result variable L03 with 0 (false)
            code.append(0x0D)  # STORE
            code.append(0x03)  # L03 = result
            code.append(0x00)
            code.append(0x00)

            for i in range(length):
                offset = i * 2  # Word-sized elements

                # LOADW table offset -> sp
                opcode = 0x0F | (table_type << 6) | (0 << 5)
                code.append(opcode)
                code.append(table_val & 0xFF)
                code.append(offset & 0xFF)
                code.append(0x00)  # Store to stack

                # CALL_VS routine sp -> sp (call with element)
                code.append(0xE0)  # CALL_VS
                types = []
                types.append(0x01 if routine_type == 0 else 0x02)
                types.append(0x02)  # stack
                types.append(0x03)
                types.append(0x03)
                type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
                code.append(type_byte)
                code.append(routine_val & 0xFF)
                code.append(0x00)  # Stack argument
                code.append(0x00)  # Store result to stack

                # JZ sp [skip_update] - if zero, don't update result
                code.append(0x80)  # JZ (1OP)
                code.append(0x00)  # Stack
                code.append(0x40 | 0x04)  # Branch true, skip 4 bytes

                # Result non-zero, update L03 from stack
                code.append(0x0D | (1 << 6))  # STORE from var
                code.append(0x03)  # L03
                code.append(0x00)  # From stack

            # Return L03 (last non-false result)
            code.append(0xAB)  # RET (1OP:0x0B)
            code.append(0x03)

            return bytes(code)

        # For runtime-determined lengths or larger tables, generate loop
        # L01 = counter, L02 = offset, L03 = result, L04 = table (if variable)

        # Initialize counter
        if len(operands) >= 3:
            code.append(0x0D | (length_type << 6))
            code.append(0x01)  # L01 = counter
            code.append(length_val & 0xFF)
        else:
            code.append(0x0D)
            code.append(0x01)
            code.append(0x00)
            code.append(0x08)

        # Initialize offset to 0
        code.append(0x0D)
        code.append(0x02)  # L02 = offset
        code.append(0x00)
        code.append(0x00)

        # Initialize result to 0
        code.append(0x0D)
        code.append(0x03)  # L03 = result
        code.append(0x00)
        code.append(0x00)

        # Store table in L04 if variable
        if table_type == 1:
            code.append(0x0D | (1 << 6))
            code.append(0x04)  # L04 = table
            code.append(table_val & 0xFF)

        loop_start = len(code)

        # LOADW table L02 -> sp
        code.append(0xCF)  # LOADW (VAR form)
        if table_type == 0:
            if table_val <= 255:
                code.append(0x5F)  # small const, var
                code.append(table_val & 0xFF)
            else:
                code.append(0x1F)  # large const, var
                code.append((table_val >> 8) & 0xFF)
                code.append(table_val & 0xFF)
        else:
            code.append(0xAF)  # var, var
            code.append(0x04)  # L04
        code.append(0x02)  # L02
        code.append(0x00)  # -> stack

        # CALL_VS routine sp -> sp
        code.append(0xE0)  # CALL_VS
        types = []
        types.append(0x01 if routine_type == 0 else 0x02)
        types.append(0x02)  # stack
        types.append(0x03)
        types.append(0x03)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(routine_val & 0xFF)
        code.append(0x00)  # Stack arg
        code.append(0x00)  # -> stack

        # JZ sp [skip_update]
        code.append(0x80)  # JZ
        code.append(0x00)  # Stack
        code.append(0x40 | 0x03)  # Branch true, skip 3 bytes

        # Update L03 with non-false result from stack
        code.append(0x0D | (1 << 6))  # STORE from var
        code.append(0x03)  # L03
        code.append(0x00)  # From stack

        # ADD L02 2 -> L02 (increment offset)
        code.append(0x54)  # ADD
        code.append(0x02)  # L02
        code.append(0x02)  # 2
        code.append(0x02)  # -> L02

        # DEC_CHK L01 0 [loop_start]
        code.append(0x04)  # DEC_CHK
        code.append(0x01)  # L01
        code.append(0x00)  # 0
        current_pos = len(code) + 2
        jump_offset = loop_start - current_pos
        if jump_offset >= -64:
            code.append(0x00 | ((jump_offset + 2) & 0x3F))
        else:
            jump_offset_unsigned = (1 << 14) + jump_offset
            code.append(0x00 | ((jump_offset_unsigned >> 8) & 0x3F))
            code.append(jump_offset_unsigned & 0xFF)

        # Return L03 (last non-false result)
        code.append(0xAB)  # RET (1OP)
        code.append(0x03)  # L03

        return bytes(code)

    def gen_newtype(self, operands: List[ASTNode]) -> bytes:
        """Generate NEWTYPE (define new type - MDL construct).

        <NEWTYPE name primtype template>
        Defines a new type in the MDL type system.

        In Z-machine, types are implicit (no runtime type info).
        We handle this at compile time by recording the type
        definition for use in type checking, but generate no code.

        Args:
            operands[0]: Type name (atom)
            operands[1]: Primitive type (VECTOR, LIST, etc.)
            operands[2]: Template (type specification)

        Returns:
            bytes: Empty (compile-time only construct)
        """
        # NEWTYPE is a compile-time construct
        # Store type definition for later use if needed
        if operands and isinstance(operands[0], AtomNode):
            type_name = operands[0].value
            # Could store in a types dict for compile-time checking
            # For now, just acknowledge it exists
            pass

        return b''

    def gen_chtype(self, operands: List[ASTNode]) -> bytes:
        """Generate CHTYPE (change type - MDL construct).

        <CHTYPE value new-type>
        Changes the type of a value in MDL's type system.

        In Z-machine, types are implicit so this is essentially
        a no-op that returns the value unchanged.

        Args:
            operands[0]: Value to retype
            operands[1]: New type (ignored at runtime)

        Returns:
            bytes: Code to return the value unchanged
        """
        if not operands:
            return b''

        # Just return the value - types are implicit in Z-machine
        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # Push value to stack using ADD 0 value
        if op_type == 1:  # Variable
            code.append(0x74)  # ADD (2OP:0x14, var var form)
            code.append(0x00)  # 0
            code.append(op_val & 0xFF)  # Variable
        else:  # Constant
            code.append(0x54)  # ADD
            code.append(0x00)  # 0
            code.append(op_val & 0xFF)
        code.append(0x00)  # -> stack

        return bytes(code)

    def gen_primtype(self, operands: List[ASTNode]) -> bytes:
        """Generate PRIMTYPE (get primitive type - MDL construct).

        <PRIMTYPE value>
        Returns the primitive type of a value.

        In Z-machine, we return a constant based on static analysis.
        Types: 0=FALSE, 1=WORD/FIX, 2=LIST, 3=VECTOR, etc.

        Args:
            operands[0]: Value to get type of

        Returns:
            bytes: Code to return type constant
        """
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        # Determine type at compile time
        type_code = 1  # Default to FIX/WORD

        if isinstance(value, int):
            if value == 0:
                type_code = 0  # FALSE
            else:
                type_code = 1  # FIX/WORD

        # Push type code
        code.append(0x54)  # ADD
        code.append(0x00)  # 0
        code.append(type_code & 0xFF)
        code.append(0x00)  # -> stack

        return bytes(code)

    def gen_printobj(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINTOBJ (print object short name).

        <PRINTOBJ object> prints the short name of an object.
        Uses PRINT_OBJ opcode (1OP 0x0A).

        Args:
            operands[0]: Object number

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # PRINT_OBJ (1OP opcode 0x0A)
        # 1OP short form: 0x80 = large const, 0x90 = small const, 0xA0 = variable
        if op_type == 1:  # Variable
            code.append(0xAA)  # 0xA0 + 0x0A = variable type, opcode 10
            code.append(op_val & 0xFF)
        elif op_val <= 255:  # Small constant
            code.append(0x9A)  # 0x90 + 0x0A = small const type, opcode 10
            code.append(op_val & 0xFF)
        else:  # Large constant
            code.append(0x8A)  # 0x80 + 0x0A = large const type, opcode 10
            code.append((op_val >> 8) & 0xFF)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_read(self, operands: List[ASTNode]) -> bytes:
        """Generate READ (read input).

        <READ buffer parse time routine> reads a line of text.
        V3: 2 operands
        V4: 2-4 operands
        V5+: 1-4 operands

        Args:
            operands[0]: Text buffer
            operands[1]: Parse buffer (optional in V5+)
            operands[2]: Time (V4+, optional)
            operands[3]: Routine (V4+, optional)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            if len(operands) != 2:
                raise ValueError("READ requires exactly 2 operands in V3")
        elif self.version == 4:
            if len(operands) < 2 or len(operands) > 4:
                raise ValueError("READ requires 2-4 operands in V4")
        else:
            if len(operands) < 1 or len(operands) > 4:
                raise ValueError("READ requires 1-4 operands in V5+")

        # Use the actual implementation from gen_input but skip its validation
        code = bytearray()
        num_ops = len(operands)

        # SREAD/AREAD is VAR opcode 0x04
        code.append(0xE4)  # VAR opcode 0x04

        # Build type byte based on number of operands
        type_byte = 0x00
        for i in range(4):
            if i < num_ops:
                op_type, _ = self._get_operand_type_and_value(operands[i])
                if op_type == 1:  # Variable
                    type_byte |= (0x02 << (6 - i*2))
                else:
                    type_byte |= (0x01 << (6 - i*2))
            else:
                type_byte |= (0x03 << (6 - i*2))  # Omitted

        code.append(type_byte)

        # Add operands
        for i in range(min(num_ops, 4)):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            code.append(op_val & 0xFF)

        # V5+: AREAD stores the terminating character
        if self.version >= 5:
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_dless(self, operands: List[ASTNode]) -> bytes:
        """Generate DLESS? (decrement and test if less).

        Decrements a variable and tests if result < comparison value.
        When used as an expression, pushes 1 (true) or 0 (false) to stack.

        DLESS? FOO 100 = decrement FOO, return true if now < 100.

        Args:
            operands[0]: variable to decrement (must be a variable name, not a number)
            operands[1]: value to compare against (must be a constant, not a variable)

        Returns:
            bytes: Z-machine code that pushes 0 or 1 to stack
        """
        if len(operands) < 2:
            raise ValueError("DLESS? requires exactly 2 operands")

        var = operands[0]
        cmp_op = operands[1]

        # Validate: first operand must be a variable, not a number
        if isinstance(var, NumberNode):
            raise ValueError("DLESS? first operand must be a variable, not a number")

        # Validate: second operand must be a constant, not a variable
        if isinstance(cmp_op, LocalVarNode) or isinstance(cmp_op, GlobalVarNode):
            raise ValueError("DLESS? second operand must be a constant, not a variable")
        # Also check for AtomNode that resolves to a variable
        if isinstance(cmp_op, AtomNode):
            if cmp_op.value in self.locals or cmp_op.value in self.globals:
                raise ValueError("DLESS? second operand must be a constant, not a variable")

        var_num = self.get_variable_number(var)
        if var_num == 0:  # Stack is invalid for DEC
            if isinstance(var, AtomNode) and var.value not in self.locals and var.value not in self.globals:
                raise ValueError(f"DLESS? unknown variable '{var.value}'")

        cmp_type, cmp_val = self._get_operand_type_and_value(cmp_op)

        code = bytearray()

        # DEC the variable (0x96 = DEC with small const)
        code.append(0x96)
        code.append(var_num)

        # Generate code to push 0 or 1 based on var < cmp_val
        # Pattern:
        #   JL var cmp_val ?true (if var < cmp_val, branch to true)
        #   ADD 0 0 -> stack     (false case: push 0)
        #   JUMP ?end            (skip over true case)
        #   ?true:
        #   ADD 0 1 -> stack     (true case: push 1)
        #   ?end:

        # JL is 2OP opcode 0x02
        # Short 2OP with var,small: 0 1 0 00010 = 0x42
        code.append(0x42)  # JL short form with var, small const
        code.append(var_num)
        code.append(cmp_val & 0xFF)
        # Branch byte: branch if true (bit 7 = 1), short form (bit 6 = 1)
        # Need to skip: ADD 0 0 -> stack (4 bytes) + JUMP ?end (3 bytes) = 7 bytes
        # Offset = 7 + 2 = 9
        code.append(0xC9)  # 11001001 = branch true, short, offset 9

        # FALSE case: ADD 0 0 -> stack
        # ADD is 2OP opcode 0x14
        # Short form with both small: 0 0 0 10100 = 0x14
        code.append(0x14)  # ADD short form, both small
        code.append(0x00)  # 0
        code.append(0x00)  # 0
        code.append(0x00)  # Store to stack

        # JUMP past true case
        # JUMP is 1OP opcode 0x0C with 16-bit offset
        # Need to skip 4 bytes (the ADD instruction in true case)
        # Offset = 4 + 2 = 6 (relative to PC after JUMP instruction)
        code.append(0x8C)  # 1OP large const, opcode 0x0C
        code.append(0x00)  # High byte of offset (6 = 0x0006)
        code.append(0x06)  # Low byte of offset

        # TRUE case: ADD 0 1 -> stack
        code.append(0x14)  # ADD short form, both small
        code.append(0x00)  # 0
        code.append(0x01)  # 1
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_check(self, operands: List[ASTNode]) -> bytes:
        """Generate CHECK (check flag in bitmap).

        <CHECK bitmap flag> tests if a specific bit/flag is set.
        Flag N is stored as bit (N % 8) of byte (N / 8).
        Uses LOADB + AND + JZ pattern.

        Args:
            operands[0]: Bitmap table address
            operands[1]: Flag number to test

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # For compile-time constants, calculate byte index and bit mask
        if op1_type == 0 and op2_type == 0:
            byte_index = op2_val // 8
            bit_mask = 1 << (7 - (op2_val % 8))  # Bits numbered from high to low

            # LOADB bitmap byte_index -> sp
            code.append(0x50)  # LOADB (2OP opcode 0x10)
            code.append(op1_val & 0xFF)
            code.append(byte_index & 0xFF)
            code.append(0x00)  # Store to stack

            # TEST sp bit_mask [branch]
            code.append(0x47)  # TEST (2OP opcode 0x07)
            code.append(0x00)  # Stack operand
            code.append(bit_mask & 0xFF)
            code.append(0xC0)  # Branch true, short form
        else:
            # Variable operands - use runtime calculation
            # Step 1: DIV flag 8 -> stack (byte index)
            if op2_type == 0:  # flag is constant
                byte_index = op2_val // 8
                code.append(0x57)  # DIV const const
                code.append(op2_val & 0xFF)
                code.append(8)
                code.append(0x00)  # Store to stack
            else:  # flag is variable
                code.append(0x77)  # DIV var const (0x17 | 0x40 | 0x20)
                code.append(op2_val & 0xFF)
                code.append(8)
                code.append(0x00)  # Store to stack

            # Step 2: LOADB bitmap stack -> stack
            if op1_type == 0:  # bitmap is constant
                code.append(0x70)  # LOADB const var
                code.append(op1_val & 0xFF)
                code.append(0x00)  # Stack as index
                code.append(0x00)  # Store to stack
            else:  # bitmap is variable
                code.append(0x70)  # LOADB var var
                code.append(op1_val & 0xFF)
                code.append(0x00)  # Stack as index
                code.append(0x00)  # Store to stack

            # Step 3: MOD flag 8 -> stack (bit position)
            if op2_type == 0:
                code.append(0x58)  # MOD const const
                code.append(op2_val & 0xFF)
                code.append(8)
                code.append(0x00)  # Store to stack
            else:
                code.append(0x78)  # MOD var const
                code.append(op2_val & 0xFF)
                code.append(8)
                code.append(0x00)  # Store to stack

            # Step 4: Calculate mask = 128 >> bit_position
            # Mask table: [128, 64, 32, 16, 8, 4, 2, 1] for positions 0-7
            # For V3 without shift, use SUB 7 bitpos, then power calculation
            # Simplified: load byte value and use BTST pattern
            # For now, test if ANY bit is set (non-zero) as approximation
            # JZ stack ?false - branch if byte is zero
            code.append(0xA0)  # JZ stack (1OP short form, var)
            code.append(0x00)  # Stack
            code.append(0x40)  # Branch false, offset 0

        return bytes(code)

    def gen_checku(self, operands: List[ASTNode]) -> bytes:
        """Generate CHECKU (check unicode support - V5+).

        <CHECKU char> tests if the interpreter supports the given character.
        Returns flags indicating input/output support.
        V5+ only, exactly 1 operand.

        Args:
            operands[0]: Character code to check

        Returns:
            bytes: Z-machine code (CHECK_UNICODE EXT opcode)
        """
        if self.version < 5:
            raise ValueError("CHECKU requires V5 or later")
        if len(operands) != 1:
            raise ValueError("CHECKU requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # CHECK_UNICODE is EXT opcode 0x0C
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0C)  # CHECK_UNICODE

        # Type byte
        type_byte = (0x01 if op_type == 0 else 0x02) << 6 | 0x3F
        code.append(type_byte)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_lexv(self, operands: List[ASTNode]) -> bytes:
        """Generate LEXV (get word from lexical/parse buffer).

        <LEXV parse-buffer word-number> gets the Nth word from parse buffer.
        Parse buffer format: [word-count] [word1-addr] [word1-len] ...

        Args:
            operands[0]: Parse buffer address
            operands[1]: Word number (1-based)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Calculate offset: (word_num - 1) * 4 + 1
        # Each word entry is 4 bytes, +1 to skip count byte
        if op1_type == 0 and op2_type == 0:
            # Both constants - calculate at compile time
            offset = (op2_val - 1) * 4 + 1
            opcode = 0x0F | (0 << 6) | (0 << 5)  # LOADW const const
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(offset & 0xFF)
            code.append(0x00)  # Store to stack
        else:
            # At least one variable - need runtime calculation
            # For now, just use the word_num directly (simplified)
            opcode = 0x0F | (op1_type << 6) | (op2_type << 5)  # LOADW
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_band_shift(self, operands: List[ASTNode]) -> bytes:
        """Generate BAND with shift (bitwise AND with shifted mask).

        <BAND value mask shift> performs: (value AND (mask << shift))
        Or: (value >> shift) AND mask depending on pattern.

        Args:
            operands[0]: Value
            operands[1]: Mask
            operands[2]: Shift amount (optional, default 0)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # value
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # mask

        # If no shift or shift is 0, just do plain AND
        if len(operands) < 3:
            return self.gen_band(operands[:2])

        shift_val = self.get_operand_value(operands[2])
        if not isinstance(shift_val, int) or shift_val == 0:
            return self.gen_band(operands[:2])

        # For compile-time constants, compute directly
        if op1_type == 0 and op2_type == 0:
            if shift_val > 0:
                # Left shift mask, then AND
                shifted_mask = (op2_val << shift_val) & 0xFFFF
            else:
                # Right shift value, then AND
                shifted_val = op1_val >> (-shift_val)
                result = shifted_val & op2_val
                code.append(0x54)  # ADD const const
                code.append(0x00)
                code.append(result & 0xFF)
                code.append(0x00)  # Store to stack
                return bytes(code)

            result = op1_val & shifted_mask
            code.append(0x54)  # ADD const const
            code.append(0x00)
            code.append(result & 0xFF)
            code.append(0x00)  # Store to stack
            return bytes(code)

        # For V3/V4 with variable operands:
        # Shift mask using multiplication (left shift) or division (right shift)
        # mask << N = mask * (2^N)
        # Then AND with value
        if shift_val > 0:
            multiplier = 1 << shift_val
            # MUL mask multiplier -> stack
            if op2_type == 0 and 0 <= multiplier <= 255:
                code.append(0x56)  # MUL const const
                code.append(op2_val & 0xFF)
                code.append(multiplier & 0xFF)
                code.append(0x00)  # Shifted mask to stack
            else:
                # Variable mask: MUL var const
                code.append(0x76)  # MUL var const
                code.append(op2_val & 0xFF)
                code.append(multiplier & 0xFF)
                code.append(0x00)  # Shifted mask to stack

            # AND value stack -> stack
            and_opcode = 0x09 | (op1_type << 6) | (1 << 5)  # AND val, var(stack)
            code.append(and_opcode)
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Stack (shifted mask)
            code.append(0x00)  # Result to stack
        else:
            # Right shift value: DIV value (2^|shift|) -> stack
            divisor = 1 << (-shift_val)
            if op1_type == 0:
                code.append(0x57)  # DIV const const
                code.append(op1_val & 0xFF)
                code.append(divisor & 0xFF)
            else:
                code.append(0x77)  # DIV var const
                code.append(op1_val & 0xFF)
                code.append(divisor & 0xFF)
            code.append(0x00)  # Shifted value to stack

            # AND stack mask -> stack
            and_opcode = 0x09 | (1 << 6) | (op2_type << 5)  # AND var(stack), mask
            code.append(and_opcode)
            code.append(0x00)  # Stack (shifted value)
            code.append(op2_val & 0xFF)
            code.append(0x00)  # Result to stack

        return bytes(code)

    def gen_grtr_or_equal(self, operands: List[ASTNode]) -> bytes:
        """Generate >= comparison (greater than or equal).

        <G=? a b> tests if a >= b.
        Implemented as NOT(a < b): if a < b, return false; else return true.

        Args:
            operands[0]: First value
            operands[1]: Second value

        Returns:
            bytes: Z-machine code
        """
        if len(operands) != 2:
            raise ValueError("G=? requires exactly 2 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if we need large constants (for negative or large values)
        needs_large1 = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
        needs_large2 = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

        if needs_large1 or needs_large2:
            # Use VAR form for JL
            code.append(0xC2)  # VAR form JL
            type_byte = 0
            if needs_large1:
                type_byte |= (0x00 << 6)
            elif op1_type == 0:
                type_byte |= (0x01 << 6)
            else:
                type_byte |= (0x02 << 6)
            if needs_large2:
                type_byte |= (0x00 << 4)
            elif op2_type == 0:
                type_byte |= (0x01 << 4)
            else:
                type_byte |= (0x02 << 4)
            type_byte |= 0x0F
            code.append(type_byte)
            if needs_large1:
                val = op1_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op1_val & 0xFF)
            if needs_large2:
                val = op2_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op2_val & 0xFF)
        else:
            # JL with branch on true to RFALSE
            opcode = 0x02 | (op1_type << 6) | (op2_type << 5)
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)

        code.append(0xC0)  # Branch on true (a < b), return false
        code.append(0xB0)  # RTRUE - fall through (a >= b)

        return bytes(code)

    def gen_less_or_equal(self, operands: List[ASTNode]) -> bytes:
        """Generate <= comparison (less than or equal).

        <L=? a b> tests if a <= b.
        Implemented as NOT(a > b): if a > b, return false; else return true.

        Args:
            operands[0]: First value
            operands[1]: Second value

        Returns:
            bytes: Z-machine code
        """
        if len(operands) != 2:
            raise ValueError("L=? requires exactly 2 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if we need large constants (for negative or large values)
        needs_large1 = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
        needs_large2 = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

        if needs_large1 or needs_large2:
            # Use VAR form for JG
            code.append(0xC3)  # VAR form JG
            type_byte = 0
            if needs_large1:
                type_byte |= (0x00 << 6)
            elif op1_type == 0:
                type_byte |= (0x01 << 6)
            else:
                type_byte |= (0x02 << 6)
            if needs_large2:
                type_byte |= (0x00 << 4)
            elif op2_type == 0:
                type_byte |= (0x01 << 4)
            else:
                type_byte |= (0x02 << 4)
            type_byte |= 0x0F
            code.append(type_byte)
            if needs_large1:
                val = op1_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op1_val & 0xFF)
            if needs_large2:
                val = op2_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op2_val & 0xFF)
        else:
            # JG with branch on true to RFALSE
            opcode = 0x03 | (op1_type << 6) | (op2_type << 5)
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)

        code.append(0xC0)  # Branch on true (a > b), return false
        code.append(0xB0)  # RTRUE - fall through (a <= b)

        return bytes(code)

    def gen_nequal(self, operands: List[ASTNode]) -> bytes:
        """Generate N=? / NEQUAL? (not equal).

        <N=? a b> tests if a != b.
        Implemented as inverted JE (branch on false).

        Args:
            operands[0]: First value
            operands[1]: Second value

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # JE with inverted branch (branch on false for !=)
        opcode = 0x01 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Branch on false (inverted)

        return bytes(code)

    def gen_zget(self, operands: List[ASTNode]) -> bytes:
        """Generate ZGET (zero-based table get).

        <ZGET table index> gets element at 0-based index.
        This is an alias for NTH (0-based access).

        Args:
            operands[0]: Table address
            operands[1]: Index (0-based)

        Returns:
            bytes: Z-machine code
        """
        return self.gen_nth(operands)

    def gen_zput(self, operands: List[ASTNode]) -> bytes:
        """Generate ZPUT (zero-based table put).

        <ZPUT table index value> sets element at 0-based index.
        Similar to PUT but 0-based instead of 1-based.

        Args:
            operands[0]: Table address
            operands[1]: Index (0-based)
            operands[2]: Value to store

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREW is VAR opcode 0x01
        code.append(0xE1)  # VAR form

        # Build type byte
        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # Omitted

        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_original(self, operands: List[ASTNode]) -> bytes:
        """Generate ORIGINAL? (test if game is original copy - V5+).

        <ORIGINAL?> tests if the game is an original (not pirate) copy.
        Uses the PIRACY opcode. Always returns 1 (true) for non-pirated copies.
        V5+ only, no operands.

        Returns:
            bytes: Z-machine code (PIRACY EXT opcode)
        """
        if self.version < 5:
            raise ValueError("ORIGINAL? requires V5 or later")
        if operands:
            raise ValueError("ORIGINAL? takes no operands")

        code = bytearray()

        # PIRACY is EXT opcode 0x0F
        # It branches if the game is a pirate copy
        # We implement it to always return 1 (genuine copy)
        # Push 1 to stack: ADD 0 1 -> stack
        # 0x14 = 2OP long form, both small constants, opcode 0x14 (ADD)
        code.append(0x14)  # ADD (2OP:0x14) long form: small const, small const
        code.append(0x00)  # 0
        code.append(0x01)  # 1
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_test_bit(self, operands: List[ASTNode]) -> bytes:
        """Generate bit test with specific bit number.

        <TEST-BIT value bit> tests if specific bit is set.
        Creates mask (1 << bit) and uses BTST pattern.

        Args:
            operands[0]: Value to test
            operands[1]: Bit number (0-based)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # For constant bit number, create mask at compile time
        if op2_type == 0 and 0 <= op2_val < 16:
            mask = 1 << op2_val
            if mask <= 255:
                # Small mask - use 2OP long form
                opcode = 0x09 | (op1_type << 6) | (0 << 5)
                code.append(opcode)
                code.append(op1_val & 0xFF)
                code.append(mask & 0xFF)
            else:
                # Large mask (bits 8-15) - use VAR form with large constant
                code.append(0xC9)  # AND VAR form
                type1 = 0x01 if op1_type == 0 else 0x02
                type_byte = (type1 << 6) | (0x00 << 4) | 0x0F  # val, large const, omit, omit
                code.append(type_byte)
                code.append(op1_val & 0xFF)
                code.append((mask >> 8) & 0xFF)
                code.append(mask & 0xFF)
            code.append(0x00)  # Store to stack
        else:
            # Variable bit number - compute mask at runtime using conditional chain
            # For V3, simulate 2^bit using comparison chain for bits 0-7
            # Push initial mask (1) to stack
            code.append(0x54)  # ADD const const -> store
            code.append(0x00)  # 0
            code.append(0x01)  # 1 (initial mask for bit 0)
            code.append(0x00)  # Store to stack

            # For each bit position 1-7, check if bit matches and update mask
            # This is a simplified approach that handles common cases
            for i in range(1, 8):
                mask = 1 << i
                # JE bit i ?update_mask
                code.append(0x41 | (op2_type << 6))  # JE with var/const
                code.append(op2_val & 0xFF)
                code.append(i & 0xFF)
                code.append(0x43)  # Branch true, skip 3 bytes

                # Not this bit, continue
                code.append(0x8C)  # JUMP
                code.append(0x00)
                code.append(0x05)  # Skip next instruction

                # Update mask: replace stack top with new mask
                code.append(0x54)  # ADD const const
                code.append(0x00)
                code.append(mask & 0xFF)
                code.append(0x00)  # Store to stack (replaces old)

            # Now AND value with computed mask
            and_opcode = 0x09 | (op1_type << 6) | (1 << 5)  # AND val, var(stack)
            code.append(and_opcode)
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Stack (mask)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_color(self, operands: List[ASTNode]) -> bytes:
        """Generate COLOR (set foreground/background colors).

        <COLOR foreground background> sets text colors.
        V5+ only. Uses SET_COLOUR opcode.

        Args:
            operands[0]: Foreground color
            operands[1]: Background color

        Returns:
            bytes: Z-machine code
        """
        if self.version < 5:
            raise ValueError("COLOR requires V5 or later")
        if len(operands) != 2:
            raise ValueError("COLOR requires exactly 2 operands")

        # V5+: SET_COLOUR opcode
        code = bytearray()
        if len(operands) >= 2:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])

            code.append(0xFB)  # SET_COLOUR (VAR:27 = 0xE0 + 0x1B)

            # Build type byte
            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x03)  # Omitted
            types.append(0x03)  # Omitted

            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
        return bytes(code)

    def gen_set_colour(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_COLOUR (V5+ - set text colors).

        <SET_COLOUR foreground background> sets display colors.
        Alias for COLOR. V5+ only (2OP:0x1B).

        Args:
            operands[0]: Foreground color
            operands[1]: Background color

        Returns:
            bytes: Z-machine code
        """
        # Delegate to COLOR implementation
        return self.gen_color(operands)

    def gen_font(self, operands: List[ASTNode]) -> bytes:
        """Generate FONT (set font - V5+).

        <FONT font-number> sets the current font.
        V5+ only. Uses SET_FONT opcode.

        Args:
            operands[0]: Font number

        Returns:
            bytes: Z-machine code
        """
        if self.version < 5:
            raise ValueError("FONT requires V5 or later")
        if len(operands) != 1:
            raise ValueError("FONT requires exactly 1 operand")

        # V5+: SET_FONT opcode
        code = bytearray()
        if operands:
            op_type, op_val = self._get_operand_type_and_value(operands[0])
            # SET_FONT is 1OP opcode 0x04 (EXT)
            if op_type == 1:  # Variable
                code.append(0xBC)  # 1OP variable, opcode 0x0C
            else:  # Constant
                code.append(0x9C)  # 1OP small constant, opcode 0x0C
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store result to stack
        return bytes(code)

    def gen_set_true_colour(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_TRUE_COLOUR (V5+ - set 24-bit RGB colors).

        <SET_TRUE_COLOUR foreground background> sets true color values.
        V5+ only. Colors are 15-bit or 24-bit RGB values.
        Use -1 to leave a color unchanged.

        Args:
            operands[0]: Foreground color (RGB value or -1)
            operands[1]: Background color (RGB value or -1)
            operands[2]: Window (optional, V6 only)

        Returns:
            bytes: Z-machine code (SET_TRUE_COLOUR EXT opcode)
        """
        if len(operands) < 2 or self.version < 5:
            return b''

        code = bytearray()

        # SET_TRUE_COLOUR is EXT opcode 0x0D
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0D)  # SET_TRUE_COLOUR

        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        if len(operands) >= 3 and self.version >= 6:
            # V6: includes window parameter
            op3_type, op3_val = self._get_operand_type_and_value(operands[2])
            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x01 if op3_type == 0 else 0x02)
            types.append(0x03)
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
            code.append(op3_val & 0xFF)
        else:
            # V5: just fg and bg
            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x03)
            types.append(0x03)
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_margin(self, operands: List[ASTNode]) -> bytes:
        """Generate MARGIN (set margins).

        <MARGIN left right window> sets left and right margins.
        V6: Uses PUT_WIND_PROP to set margin properties (6=left, 7=right)
        V6 only.

        Args:
            operands[0]: Left margin
            operands[1]: Right margin
            operands[2]: Window number (optional, defaults to current)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("MARGIN requires V6")
        if len(operands) < 2 or len(operands) > 3:
            raise ValueError("MARGIN requires 2-3 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = (0, 0)
        op3_type, op3_val = (0, 0)  # Default window = 0

        if len(operands) >= 2:
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        if len(operands) >= 3:
            op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # V6: Use PUT_WIND_PROP (EXT:0x19) for margins
        # Property 6 = left margin, Property 7 = right margin
        # Set left margin (property 6)
        code.append(0xBE)  # EXT opcode marker
        code.append(0x19)  # PUT_WIND_PROP
        types = []
        types.append(0x01 if op3_type == 0 else 0x02)  # window
        types.append(0x01)  # property 6 (constant)
        types.append(0x01 if op1_type == 0 else 0x02)  # left value
        types.append(0x03)  # omit
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op3_val & 0xFF)
        code.append(0x06)  # Property 6 = left margin
        code.append(op1_val & 0xFF)

        if len(operands) >= 2:
            # Set right margin (property 7)
            code.append(0xBE)  # EXT opcode marker
            code.append(0x19)  # PUT_WIND_PROP
            types = []
            types.append(0x01 if op3_type == 0 else 0x02)  # window
            types.append(0x01)  # property 7 (constant)
            types.append(0x01 if op2_type == 0 else 0x02)  # right value
            types.append(0x03)  # omit
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)
            code.append(op3_val & 0xFF)
            code.append(0x07)  # Property 7 = right margin
            code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_winsize(self, operands: List[ASTNode]) -> bytes:
        """Generate WINSIZE (set window size).

        <WINSIZE window lines> sets window dimensions.
        V6 only.

        Args:
            operands[0]: Window number
            operands[1]: Number of lines

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("WINSIZE requires V6")
        if len(operands) > 4:
            raise ValueError("WINSIZE accepts at most 4 operands")

        code = bytearray()

        # Check if window is constant 1 (upper window) and we have at least 2 operands - use SPLIT
        if len(operands) >= 2:
            op_type, op_val = self._get_operand_type_and_value(operands[0])
            if op_type == 0 and op_val == 1:
                return self.gen_split([operands[1]])

        # WINDOW_SIZE EXT:0x11
        code.append(0xBE)
        code.append(0x11)

        # Build type byte
        type_parts = []
        for i in range(4):
            if i < len(operands):
                op_type, _ = self._get_operand_type_and_value(operands[i])
                type_parts.append(0x01 if op_type == 0 else 0x02)
            else:
                type_parts.append(0x03)  # Omitted

        type_byte = (type_parts[0] << 6) | (type_parts[1] << 4) | (type_parts[2] << 2) | type_parts[3]
        code.append(type_byte)

        for op in operands:
            _, op_val = self._get_operand_type_and_value(op)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_winget(self, operands: List[ASTNode]) -> bytes:
        """Generate WINGET (get window property).

        <WINGET window property> gets window information.
        V6 only. Uses GET_WIND_PROP opcode (EXT:0x13).

        Window properties:
        0=y, 1=x, 2=height, 3=width, 4=y-cursor, 5=x-cursor,
        6=left-margin, 7=right-margin, 8=newline-interrupt,
        9=interrupt-countdown, 10=text-style, 11=color-data

        Args:
            operands[0]: Window number
            operands[1]: Property number

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("WINGET requires V6")
        if len(operands) > 4:
            raise ValueError("WINGET accepts at most 4 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # GET_WIND_PROP is EXT opcode 0x13
        code.append(0xBE)  # EXT opcode marker
        code.append(0x13)  # GET_WIND_PROP

        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x03)
        types.append(0x03)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_winput(self, operands: List[ASTNode]) -> bytes:
        """Generate WINPUT (set window property).

        <WINPUT window property value> sets window property.
        V6 only. Uses PUT_WIND_PROP opcode (EXT:0x19).

        Args:
            operands[0]: Window number
            operands[1]: Property number
            operands[2]: Value to set

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("WINPUT requires V6")
        if len(operands) > 4:
            raise ValueError("WINPUT accepts at most 4 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # PUT_WIND_PROP is EXT opcode 0x19
        code.append(0xBE)  # EXT opcode marker
        code.append(0x19)  # PUT_WIND_PROP

        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # omit
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_winattr(self, operands: List[ASTNode]) -> bytes:
        """Generate WINATTR (set window attributes).

        <WINATTR window flags operation> sets window display attributes.
        V6 only. Uses WINDOW_STYLE opcode (EXT:0x12).

        Args:
            operands[0]: Window number
            operands[1]: Attribute flags
            operands[2]: Operation (0=set, 1=clear, 2=toggle) - optional

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("WINATTR requires V6")
        if len(operands) > 4:
            raise ValueError("WINATTR accepts at most 4 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = (0, 0)  # Default: set (operation = 0)
        if len(operands) >= 3:
            op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # WINDOW_STYLE is EXT opcode 0x12
        code.append(0xBE)  # EXT opcode marker
        code.append(0x12)  # WINDOW_STYLE

        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # omit
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_winpos(self, operands: List[ASTNode]) -> bytes:
        """Generate WINPOS (move window position).

        <WINPOS window y x> moves window to position.
        V6 only. Uses MOVE_WINDOW opcode (EXT:0x10).

        Args:
            operands[0]: Window number
            operands[1]: Y position
            operands[2]: X position

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("WINPOS requires V6")
        if len(operands) > 4:
            raise ValueError("WINPOS accepts at most 4 operands")

        code = bytearray()

        # MOVE_WINDOW is EXT opcode 0x10
        code.append(0xBE)  # EXT marker
        code.append(0x10)  # MOVE_WINDOW

        # Build type byte
        type_parts = []
        for i in range(4):
            if i < len(operands):
                op_type, _ = self._get_operand_type_and_value(operands[i])
                type_parts.append(0x01 if op_type == 0 else 0x02)
            else:
                type_parts.append(0x03)  # Omitted

        type_byte = (type_parts[0] << 6) | (type_parts[1] << 4) | (type_parts[2] << 2) | type_parts[3]
        code.append(type_byte)

        for op in operands:
            _, op_val = self._get_operand_type_and_value(op)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_intbl(self, operands: List[ASTNode]) -> bytes:
        """Generate INTBL? (check if value in table - V4+).

        <INTBL? value table length [form]> searches table for value.
        Returns true if found (and address in result for V5+).
        V4: 3 operands only
        V5+: 3-4 operands (4th is form/size)

        Args:
            operands[0]: Value to search for
            operands[1]: Table address
            operands[2]: Table length (in words)
            operands[3]: Entry size (V5+ only, optional, default 2)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 4:
            raise ValueError("INTBL? requires V4 or later")
        if self.version == 4:
            if len(operands) != 3:
                raise ValueError("INTBL? requires exactly 3 operands in V4")
        else:
            if len(operands) < 3 or len(operands) > 4:
                raise ValueError("INTBL? requires 3-4 operands in V5+")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # value
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # table
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])  # length

        # V5+: Use SCAN_TABLE opcode (VAR:23)
        if self.version >= 5:
            # SCAN_TABLE is VAR opcode 23 (NOT EXT!)
            # VAR form: 0xE0 + (opcode & 0x1F) = 0xE0 + 23 = 0xF7
            code.append(0xF7)  # VAR:23 = SCAN_TABLE

            # Get 4th operand (form) if provided, default to 0x82 (word entries, forward)
            if len(operands) >= 4:
                op4_type, op4_val = self._get_operand_type_and_value(operands[3])
            else:
                op4_type, op4_val = 0, 0x82  # Default: word entries, forward

            # Build type byte for 4 operands: value, table, length, form
            types = []
            op_bytes = []

            for op_t, op_v in [(op1_type, op1_val), (op2_type, op2_val),
                               (op3_type, op3_val), (op4_type, op4_val)]:
                if op_t == 0:  # Constant
                    if op_v > 255:
                        types.append(0x00)  # Large constant
                        op_bytes.append([(op_v >> 8) & 0xFF, op_v & 0xFF])
                    else:
                        types.append(0x01)  # Small constant
                        op_bytes.append([op_v & 0xFF])
                else:  # Variable
                    types.append(0x02)
                    op_bytes.append([op_v & 0xFF])

            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            # Encode operands
            for ob in op_bytes:
                code.extend(ob)

            # Store result to stack
            code.append(0x00)
            # Branch on success: offset 2 means skip to next instruction (no-op branch)
            # Bit 7 = 1 (branch if true), bit 6 = 1 (short form), offset = 2
            code.append(0xC2)

            return bytes(code)

        # V3/V4: Generate loop-based search
        # L01 = counter, L02 = offset, L03 = value, L04 = table
        entry_size = 2  # Default word-sized entries
        if len(operands) >= 4:
            es = self.get_operand_value(operands[3])
            if isinstance(es, int):
                entry_size = es

        # Check if we can unroll for small constant-length tables
        # Only use unrolled loop if ALL operands are literal constants (NumberNode),
        # not global variables (whose values would need to be loaded at runtime)
        length = self.get_operand_value(operands[2])
        value = self.get_operand_value(operands[0])
        table = self.get_operand_value(operands[1])

        # Only unroll if operands are literal NumberNodes, not variable references
        all_constants = (isinstance(operands[0], NumberNode) and
                        isinstance(operands[1], NumberNode) and
                        isinstance(operands[2], NumberNode))

        if all_constants and isinstance(value, int) and isinstance(table, int) and isinstance(length, int):
            if length <= 8:  # Unroll for small tables
                for i in range(length):
                    offset = i * entry_size
                    # LOADW table offset -> sp
                    if 0 <= table <= 255 and 0 <= offset <= 255:
                        code.append(0x4F)  # LOADW (2OP opcode 0x0F)
                        code.append(table & 0xFF)
                        code.append(offset & 0xFF)
                        code.append(0x00)  # Store to stack

                        # JE sp value [found]
                        if 0 <= value <= 255:
                            code.append(0x41)  # JE (2OP opcode 0x01)
                            code.append(0x00)  # Stack
                            code.append(value & 0xFF)
                            code.append(0xC0)  # Branch true (rtrue)

                return bytes(code)

        # For V4 with variable operands, we need to generate a search loop.
        # This is complex because we need properly allocated local variables.
        # For now, generate an unrolled search if length is a small constant,
        # otherwise return false as a stub.
        #
        # Generate unrolled search for variable table address but constant value/length
        if isinstance(operands[0], NumberNode) and isinstance(operands[2], NumberNode):
            if isinstance(length, int) and length <= 8:
                # We can unroll with variable table address
                if op2_type == 1:  # Variable (global/local)
                    # Generate unrolled search using LOADW with variable base address
                    # Result: push address of found element (or 0 if not found)
                    # Structure:
                    #   for each i:
                    #     LOADW table, i -> stack
                    #     JE stack, value -> skip_add_i (branch if NOT equal)
                    #     ADD table, i*2 -> stack (compute address)
                    #     JUMP exit
                    #   :skip_add_last (falls through to not_found)
                    #   PUSH 0
                    #   JUMP exit_final
                    #   :exit
                    #   (address is on stack)
                    search_code = bytearray()

                    # First, build the iteration blocks
                    # Each block: LOADW (4) + JE (4) + ADD (4) + JUMP (varies)
                    # If JE branches (not equal), skip the ADD+JUMP for this iteration

                    for i in range(length):
                        word_offset = i
                        byte_offset = i * 2

                        # LOADW table, i -> stack
                        search_code.append(0x4F)  # LOADW var+small
                        search_code.append(op2_val & 0xFF)
                        search_code.append(word_offset & 0xFF)
                        search_code.append(0x00)  # store to stack

                        # JE stack, value -> skip (branch if NOT equal = don't branch if equal)
                        # We want to branch PAST the ADD+JUMP if NOT equal
                        # ADD is 4 bytes, JUMP is 2 bytes = 6 bytes to skip
                        search_code.append(0x41)  # JE var+small
                        search_code.append(0x00)  # stack
                        search_code.append(value & 0xFF)
                        # Branch if NOT equal: bit 7 = 0
                        # Skip 6 bytes (ADD 4 + JUMP 2): offset = 6 + 2 = 8
                        search_code.append(0x48)  # branch false, short, offset 8

                        # ADD table, byte_offset -> stack (compute found address)
                        # ADD is 2OP opcode 0x14
                        # For ADD var+small -> stack
                        search_code.append(0x54)  # ADD var+small (0x40 | 0x14)
                        search_code.append(op2_val & 0xFF)  # table variable
                        search_code.append(byte_offset & 0xFF)  # byte offset
                        search_code.append(0x00)  # store to stack

                        # Calculate JUMP distance to end (past remaining iterations + not_found code)
                        remaining_iterations = length - 1 - i
                        # Each remaining iteration: LOADW(4) + JE(4) + ADD(4) + JUMP(2) = 14 bytes
                        # Not found code: PUSH(3) = 3 bytes (no JUMP needed, just fall through)
                        skip_to_exit = remaining_iterations * 14 + 3
                        # JUMP offset formula: offset = distance + 2
                        jump_offset = skip_to_exit + 2

                        # JUMP exit
                        search_code.append(0x9C)  # JUMP short form
                        search_code.append(jump_offset & 0xFF)

                    # Not found - push 0
                    search_code.append(0xE8)  # VAR PUSH
                    search_code.append(0x7F)  # type: small constant
                    search_code.append(0x00)  # value 0

                    # JUMP past end (skip 0 bytes, but need JUMP anyway for consistency)
                    # Actually, not needed - we're at the end
                    # Remove this JUMP since we fall through to exit anyway
                    # But we still need the exit point after PUSH 1 for "found" jumps
                    # Actually wait, the "found" case now directly computes address and jumps to exit
                    # We don't need a separate PUSH 1 block anymore

                    # No JUMP needed - we just fall through after PUSH 0

                    code.extend(search_code)
                    return bytes(code)

        # Fallback: return false (table search not found)
        # This is a stub - proper loop generation requires local variable allocation
        code.append(0xB1)  # RFALSE
        return bytes(code)

    def gen_zero_table(self, operands: List[ASTNode]) -> bytes:
        """Generate ZERO (zero out table).

        Alias for gen_zero. See gen_zero for implementation.
        """
        return self.gen_zero(operands)

    def gen_getb2(self, operands: List[ASTNode]) -> bytes:
        """Generate GETB2 (get byte with base+offset).

        <GETB2 base offset> gets byte at base+offset.
        Uses ADD to compute address, then LOADB.

        Args:
            operands[0]: Base address
            operands[1]: Offset

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Use LOADB with base and offset
        opcode = 0x10 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_putb2(self, operands: List[ASTNode]) -> bytes:
        """Generate PUTB2 (put byte with base+offset).

        <PUTB2 base offset value> stores byte at base+offset.
        Uses ADD to compute address, then STOREB.

        Args:
            operands[0]: Base address
            operands[1]: Offset
            operands[2]: Value to store

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREB is VAR opcode 0x02
        code.append(0xE2)  # VAR form

        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # omit
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_getw2(self, operands: List[ASTNode]) -> bytes:
        """Generate GETW2 (get word with base+offset).

        <GETW2 base offset> gets word at base+offset.

        Args:
            operands[0]: Base address
            operands[1]: Offset (in words)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Use LOADW with base and offset
        opcode = 0x0F | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_putw2(self, operands: List[ASTNode]) -> bytes:
        """Generate PUTW2 (put word with base+offset).

        <PUTW2 base offset value> stores word at base+offset.

        Args:
            operands[0]: Base address
            operands[1]: Offset (in words)
            operands[2]: Value to store

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREW is VAR opcode 0x01
        code.append(0xE1)  # VAR form

        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # omit
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    # LOWCORE header field constants (byte offsets, /2 for word index)
    LOWCORE_HEADER = {
        'ZVERSION': 0x00,    # Version number (byte, but accessed as word)
        'FLAGS': 0x01,       # Flags 1 (byte)
        'RELESSION': 0x02,   # Release number (word) - typo preserved for compat
        'RELEASE': 0x02,     # Release number (word)
        'ENDLOD': 0x04,      # High memory base (word)
        'START': 0x06,       # Initial PC / main routine (word)
        'VOCAB': 0x08,       # Dictionary address (word)
        'OBJECT': 0x0A,      # Object table address (word)
        'GLOBAL': 0x0C,      # Global variables table address (word)
        'IMPURE': 0x0E,      # Static memory base (word)
        'FLAGS2': 0x10,      # Flags 2 (word)
        'SERIAL': 0x12,      # Serial number (6 bytes)
        'WORDS': 0x18,       # Abbreviations table address (word)
        'LENGTH': 0x1A,      # File length (word, packed)
        'CHKSUM': 0x1C,      # Checksum (word)
        'INESSION': 0x1E,    # Interpreter number (byte)
        'INTVERS': 0x1F,     # Interpreter version (byte)
        'SCRV': 0x20,        # Screen height (byte)
        'SCRH': 0x21,        # Screen width (byte)
        'EXTAB': 0x36,       # Extension table address (word, V5+)
    }

    # Extension table entry offsets (word indices from EXTAB base)
    LOWCORE_EXTENSION = {
        'EXTABLEN': 0,       # Extension table size (words)
        'MSLOCX': 1,         # Mouse X coordinate
        'MSLOCY': 2,         # Mouse Y coordinate
        'MSETBL': 3,         # Unicode translation table / mouse buttons
        'FLAGS3': 4,         # Flags 3
        'TRUEFG': 5,         # True foreground color
        'TRUEBG': 6,         # True background color
    }

    def gen_lowcore(self, operands: List[ASTNode]) -> bytes:
        """Generate LOWCORE (access low memory/header fields).

        <LOWCORE name> reads a word from header by symbolic name.
        <LOWCORE name value> writes a value to header location.
        <LOWCORE (name subfield)> reads a byte/subfield.

        Supports:
        - Header fields: ZVERSION, FLAGS, EXTAB, etc.
        - Extension table entries: MSLOCY, MSETBL, etc.

        Args:
            operands[0]: Address/name in low memory
            operands[1]: Value to write (optional)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        first_op = operands[0]
        is_write = len(operands) >= 2

        # Check for symbolic header names
        addr = None
        is_extension = False
        ext_offset = 0

        if isinstance(first_op, AtomNode):
            name = first_op.value.upper() if hasattr(first_op.value, 'upper') else str(first_op.value)
            if name in self.LOWCORE_HEADER:
                addr = self.LOWCORE_HEADER[name]
            elif name in self.LOWCORE_EXTENSION:
                is_extension = True
                ext_offset = self.LOWCORE_EXTENSION[name]
                # Track max extension word used for auto-creation
                if ext_offset > self._max_extension_word:
                    self._max_extension_word = ext_offset
        elif isinstance(first_op, FormNode):
            # Subfield access: (NAME subfield)
            if first_op.operands and isinstance(first_op.operands[0], AtomNode):
                name = first_op.operands[0].value.upper()
                if name in self.LOWCORE_HEADER:
                    addr = self.LOWCORE_HEADER[name]
                    # Add subfield offset if provided
                    if len(first_op.operands) > 1:
                        sub_type, sub_val = self._get_operand_type_and_value(first_op.operands[1])
                        addr += sub_val

        if is_extension:
            # Extension table access: read EXTAB, then access offset
            # First, read EXTAB (header 0x36) to stack
            code.append(0x0F)  # LOADW short form
            code.append(0x00)  # Base = 0
            code.append(0x36 // 2)  # EXTAB word offset
            code.append(0x00)  # Store to stack

            if is_write:
                # STOREW stack, ext_offset, value
                val_type, val_val = self._get_operand_type_and_value(operands[1])
                # STOREW is 3-operand VAR opcode
                code.append(0xE1)  # STOREW VAR form
                # Types: stack=var(10), small const(01), value type
                type_byte = (0x02 << 6) | (0x01 << 4) | (val_type << 2) | 0x03
                code.append(type_byte)
                code.append(0x00)  # Stack (operand 1)
                code.append(ext_offset)  # Offset (operand 2)
                if val_type == 0:  # Large constant
                    code.append((val_val >> 8) & 0xFF)
                    code.append(val_val & 0xFF)
                else:
                    code.append(val_val & 0xFF)
            else:
                # LOADW stack, ext_offset -> stack
                code.append(0x4F)  # LOADW with var, small const
                code.append(0x00)  # Stack (base)
                code.append(ext_offset)  # Offset
                code.append(0x00)  # Store to stack
        elif addr is not None:
            # Direct header access
            word_offset = addr // 2
            if is_write:
                # STOREW 0, word_offset, value
                val_type, val_val = self._get_operand_type_and_value(operands[1])
                code.append(0xE1)  # STOREW VAR form
                # Types: small(01), small(01), value type, omit(11)
                type_byte = (0x01 << 6) | (0x01 << 4) | (val_type << 2) | 0x03
                code.append(type_byte)
                code.append(0x00)  # Base = 0
                code.append(word_offset)  # Offset
                if val_type == 0:  # Large constant
                    code.append((val_val >> 8) & 0xFF)
                    code.append(val_val & 0xFF)
                else:
                    code.append(val_val & 0xFF)
            else:
                # LOADW 0, word_offset -> stack
                code.append(0x0F)  # LOADW 2OP small, small
                code.append(0x00)  # Base = 0
                code.append(word_offset)
                code.append(0x00)  # Store to stack
        else:
            # Numeric address or unknown - use as-is
            op_type, op_val = self._get_operand_type_and_value(first_op)
            if is_write:
                val_type, val_val = self._get_operand_type_and_value(operands[1])
                code.append(0xE1)  # STOREW VAR form
                type_byte = (0x01 << 6) | (op_type << 4) | (val_type << 2) | 0x03
                code.append(type_byte)
                code.append(0x00)  # Base = 0
                if op_type == 0:
                    code.append((op_val >> 8) & 0xFF)
                    code.append(op_val & 0xFF)
                else:
                    code.append(op_val & 0xFF)
                if val_type == 0:
                    code.append((val_val >> 8) & 0xFF)
                    code.append(val_val & 0xFF)
                else:
                    code.append(val_val & 0xFF)
            else:
                # LOADW 0, offset -> stack
                opcode = 0x0F
                if op_type == 0:  # Large constant
                    opcode = 0x0F  # 2OP small, large
                code.append(opcode)
                code.append(0x00)  # Base = 0
                code.append(op_val & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_screen_height(self, operands: List[ASTNode]) -> bytes:
        """Generate SCREEN-HEIGHT (get screen height in lines).

        Returns the screen height from header byte 0x20.
        V4+ feature, returns default for V3.

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()
        # Screen height is at header byte 0x20
        # Use LOADB 0 0x20 -> stack to read from header
        if self.version >= 4:
            code.append(0x10)  # LOADB 2OP small const, small const
            code.append(0x00)  # Base address 0 (header)
            code.append(0x20)  # Offset 0x20 (screen height)
            code.append(0x00)  # Store to stack
        else:
            # V3: Return default value (24 lines)
            code.append(0x54)  # ADD const const
            code.append(0x00)  # 0
            code.append(24)    # Default height
            code.append(0x00)  # Store to stack
        return bytes(code)

    def gen_screen_width(self, operands: List[ASTNode]) -> bytes:
        """Generate SCREEN-WIDTH (get screen width in characters).

        Returns the screen width from header byte 0x21.
        V4+ feature, returns default for V3.

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()
        # Screen width is at header byte 0x21
        # Use LOADB 0 0x21 -> stack to read from header
        if self.version >= 4:
            code.append(0x10)  # LOADB 2OP small const, small const
            code.append(0x00)  # Base address 0 (header)
            code.append(0x21)  # Offset 0x21 (screen width)
            code.append(0x00)  # Store to stack
        else:
            # V3: Return default value (80 chars)
            code.append(0x54)  # ADD const const
            code.append(0x00)  # 0
            code.append(80)    # Default width
            code.append(0x00)  # Store to stack
        return bytes(code)

    def gen_asr(self, operands: List[ASTNode]) -> bytes:
        """Generate ASR (arithmetic shift right).

        <ASR value shift> performs arithmetic right shift (sign-extending).
        Similar to RSH but preserves sign bit.

        Args:
            operands[0]: Value to shift
            operands[1]: Number of bits to shift

        Returns:
            bytes: Z-machine code
        """
        # For V3, ASR is same as RSH (DIV by 2^n)
        return self.gen_rsh(operands)

    def gen_catch(self, operands: List[ASTNode]) -> bytes:
        """Generate CATCH (catch exception/save state - V5+).

        <CATCH> creates a catch point for throw/return.
        V5+ only, no operands.
        Returns the current stack frame address.

        CATCH is 0OP:9 (replaces POP in V5+).
        Short form: 0xB9 (1011 1001).

        Returns:
            bytes: Z-machine code
        """
        if self.version < 5:
            raise ValueError("CATCH requires V5 or later")
        if operands:
            raise ValueError("CATCH takes no operands")

        code = bytearray()
        # CATCH is 0OP opcode 9, short form: 1011 1001 = 0xB9
        code.append(0xB9)  # 0OP opcode 9 (CATCH)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_throw(self, operands: List[ASTNode]) -> bytes:
        """Generate THROW (throw to catch point).

        <THROW value catch-point> jumps to catch with value.
        V5+ feature using THROW opcode (2OP:28 = 0x1C).

        Args:
            operands[0]: Value to return
            operands[1]: Catch frame address (from CATCH)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 5:
            raise ValueError("THROW requires V5 or later")
        if len(operands) != 2:
            raise ValueError("THROW requires exactly 2 operands")

        code = bytearray()

        # THROW is 2OP opcode 0x1C (28 decimal)
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if we need large constants (values > 255)
        needs_large1 = op1_type == 0 and op1_val > 255
        needs_large2 = op2_type == 0 and op2_val > 255

        if needs_large1 or needs_large2:
            # Use VAR form for large constants: 110 nnnnn (0xC0 | opcode)
            code.append(0xDC)  # VAR form of 2OP opcode 0x1C (0xC0 | 0x1C)
            # Type byte: 00=large, 01=small, 10=var, 11=omit
            type1 = 0x00 if needs_large1 else (0x01 if op1_type == 0 else 0x02)
            type2 = 0x00 if needs_large2 else (0x01 if op2_type == 0 else 0x02)
            type_byte = (type1 << 6) | (type2 << 4) | 0x0F  # Rest omitted
            code.append(type_byte)
            # Add operands
            if needs_large1:
                code.append((op1_val >> 8) & 0xFF)
                code.append(op1_val & 0xFF)
            else:
                code.append(op1_val & 0xFF)
            if needs_large2:
                code.append((op2_val >> 8) & 0xFF)
                code.append(op2_val & 0xFF)
            else:
                code.append(op2_val & 0xFF)
        else:
            # 2OP long form: 0 a b nnnnn where a,b are operand types (0=small, 1=var)
            # opcode 0x1C = 28 = 0b11100
            opcode = 0x1C | (op1_type << 6) | (op2_type << 5)
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_new_line(self, operands: List[ASTNode]) -> bytes:
        """Generate NEW-LINE (print newline - alias for CRLF).

        <NEW-LINE> outputs a newline character.

        Returns:
            bytes: Z-machine code
        """
        return self.gen_newline()

    def gen_spaces(self, operands: List[ASTNode]) -> bytes:
        """Generate SPACES (print N spaces).

        <SPACES n> prints n space characters.
        For small constants (≤80), unrolls PRINT_CHAR calls.
        For larger values or variables, generates inline loop.

        Args:
            operands[0]: Number of spaces

        Returns:
            bytes: Z-machine code for printing spaces
        """
        if not operands:
            return b''

        code = bytearray()
        count = self.get_operand_value(operands[0])

        # For compile-time constant ≤ 80, unroll PRINT_CHAR
        if isinstance(count, int):
            if count <= 0:
                return b''
            if count <= 80:
                for _ in range(count):
                    # PRINT_CHAR with space (ASCII 32)
                    code.append(0xE5)  # PRINT_CHAR (VAR:0x05)
                    code.append(0x01)  # Type byte: 1 small constant
                    code.append(32)    # Space character
                return bytes(code)

            # For larger constants, generate inline loop:
            # 1. Push count to stack
            # 2. Loop: DEC_CHK sp, 0 -> end
            # 3. PRINT_CHAR 32
            # 4. JUMP to step 2
            # 5. End

            # Push count to stack (ADD 0 count -> sp)
            if count <= 255:
                code.append(0x54)  # ADD small, small
                code.append(0x00)
                code.append(count & 0xFF)
                code.append(0x00)  # Store to SP
            else:
                code.append(0xD4)  # VAR form of ADD
                code.append(0x0F)  # small, large
                code.append(0x00)
                code.append((count >> 8) & 0xFF)
                code.append(count & 0xFF)
                code.append(0x00)

        else:
            # Variable count - push to stack first
            # STORE sp, var (copies variable value to stack)
            var_num = count if isinstance(count, int) else 1
            code.append(0x8D)  # 1OP:13 PUSH (short form, variable)
            code.append(var_num & 0xFF)

        # Loop start offset = current position
        loop_start = len(code)

        # DEC_CHK sp 0 -> branch forward (end)
        # DEC_CHK is 2OP:4, decrements first operand (var), branches if < second
        code.append(0xC4)  # VAR form of DEC_CHK
        code.append(0xAF)  # var, omit, omit, omit (using sp twice)
        code.append(0x00)  # Variable 0 (SP) - the counter
        code.append(0x00)  # Compare to 0 (end when counter < 0)
        # Branch offset: we'll patch this after generating loop body
        branch_pos = len(code)
        code.append(0x00)  # Placeholder for branch offset

        # PRINT_CHAR 32
        code.append(0xE5)  # PRINT_CHAR (VAR:0x05)
        code.append(0x01)  # Type byte: small constant
        code.append(32)    # Space character

        # JUMP back to loop start
        # JUMP is 1OP:12, takes label address (we use relative offset)
        jump_offset = loop_start - (len(code) + 3)  # Offset from after JUMP instruction
        code.append(0x8C)  # 1OP:12 JUMP, small constant type
        # Jump offset is signed 16-bit, packed in 2 bytes
        code.append((jump_offset >> 8) & 0xFF)
        code.append(jump_offset & 0xFF)

        # End of loop - patch branch offset
        end_offset = len(code) - branch_pos - 1
        code[branch_pos] = 0x40 | (end_offset & 0x3F)  # Short branch, true condition

        return bytes(code)

    def gen_back(self, operands: List[ASTNode]) -> bytes:
        """Generate BACK (alias for SUB with default second operand of 1).

        BACK is a convenient alias for subtraction:
        - <BACK x> = x - 1
        - <BACK x y> = x - y

        With no operands, falls back to screen operation (erase to beginning of line).

        Args:
            operands[0]: first value (optional)
            operands[1]: second value (optional, defaults to 1)

        Returns:
            bytes: Z-machine code (SUB instruction or newline for screen op)
        """
        if not operands:
            # No operands - screen operation (erase to beginning of line)
            # V3 approximation: print newline
            return self.gen_newline()

        # If only one operand, default second operand to 1
        if len(operands) == 1:
            one_node = NumberNode(1)
            return self._gen_2op_store(0x15, operands[0], one_node)
        else:
            # Two operands - normal SUB
            return self._gen_2op_store(0x15, operands[0], operands[1])

    def gen_display(self, operands: List[ASTNode]) -> bytes:
        """Generate DISPLAY (update status line).

        <DISPLAY room-desc score> updates the status line display.
        In V3, this is automatic, so this is a no-op.

        Args:
            operands[0]: Room description (optional)
            operands[1]: Score value (optional)

        Returns:
            bytes: Z-machine code (no-op in V3)
        """
        # DISPLAY is automatic in V3
        return b''

    def gen_score(self, operands: List[ASTNode]) -> bytes:
        """Generate SCORE (set score value).

        <SCORE points> sets the game score.
        In Z-machine, the score is stored at header offset 0x0E (word).
        Also stores to the SCORE global if defined.

        Args:
            operands[0]: Score value

        Returns:
            bytes: Z-machine code for setting score
        """
        if not operands:
            return b''

        code = bytearray()
        score_value = self.get_operand_value(operands[0])

        # Helper to encode operand
        def encode_op(val):
            if isinstance(val, int):
                if 0 <= val <= 255:
                    return (0b01, bytes([val & 0xFF]))  # Small constant
                else:
                    return (0b00, bytes([(val >> 8) & 0xFF, val & 0xFF]))  # Large
            else:
                return (0b10, bytes([val & 0xFF]))  # Variable

        # Score is stored at header offset 0x0E (word)
        # Use STOREB to write to this location (2 bytes)
        # STOREB base offset value

        t_val, b_val = encode_op(score_value)

        if isinstance(score_value, int):
            # Constant: directly store high and low bytes
            # Store high byte at 0x0E
            code.append(0xE3)  # STOREB (VAR:0x03)
            code.append(0x55)  # Types: small, small, small, omit
            code.append(0x00)  # Base address 0
            code.append(0x0E)  # Offset 0x0E
            code.append((score_value >> 8) & 0xFF)  # High byte

            # Store low byte at 0x0F
            code.append(0xE3)  # STOREB (VAR:0x03)
            code.append(0x55)  # Types: small, small, small, omit
            code.append(0x00)  # Base address 0
            code.append(0x0F)  # Offset 0x0F
            code.append(score_value & 0xFF)  # Low byte
        else:
            # Variable: extract high byte via DIV 256, low byte via MOD 256
            var_num = score_value & 0xFF

            # DIV var 256 -> stack (high byte)
            # 256 doesn't fit in small const, use two bytes
            code.append(0xD7)  # DIV VAR form
            code.append(0xA3)  # var, large const, omit, omit
            code.append(var_num)  # Variable
            code.append(0x01)  # 256 high byte
            code.append(0x00)  # 256 low byte
            code.append(0x00)  # Result to stack

            # STOREB 0 0x0E stack (store high byte)
            code.append(0xE3)  # STOREB (VAR:0x03)
            code.append(0x59)  # Types: small, small, var, omit
            code.append(0x00)  # Base address 0
            code.append(0x0E)  # Offset 0x0E
            code.append(0x00)  # Stack (high byte value)

            # MOD var 256 -> stack (low byte)
            code.append(0xD8)  # MOD VAR form
            code.append(0xA3)  # var, large const, omit, omit
            code.append(var_num)  # Variable
            code.append(0x01)  # 256 high byte
            code.append(0x00)  # 256 low byte
            code.append(0x00)  # Result to stack

            # STOREB 0 0x0F stack (store low byte)
            code.append(0xE3)  # STOREB (VAR:0x03)
            code.append(0x59)  # Types: small, small, var, omit
            code.append(0x00)  # Base address 0
            code.append(0x0F)  # Offset 0x0F
            code.append(0x00)  # Stack (low byte value)

        return bytes(code)

    def gen_chrset(self, operands: List[ASTNode]) -> bytes:
        """Generate CHRSET (set character set).

        <CHRSET charset> sets the active character set for display.
        V5+: Uses SET_FONT and character set tables
        V3/V4: No-op (limited character set support)

        Charset values:
        0 = Default alphabet
        1 = Alternative alphabet
        2 = User-defined

        Args:
            operands[0]: Character set identifier

        Returns:
            bytes: Z-machine code
        """
        if self.version < 5:
            # V3/V4: No character set switching, but return 0 (default)
            # to keep stack consistent if result is expected
            code = bytearray()
            code.append(0x54)  # ADD const const -> store
            code.append(0x00)  # 0
            code.append(0x00)  # 0
            code.append(0x00)  # Store to stack (returns 0 = default charset)
            return bytes(code)

        if not operands:
            return b''

        code = bytearray()
        charset = self.get_operand_value(operands[0])

        # In V5+, CHRSET can be implemented using SET_FONT
        # Font 3 is character graphics font
        # For alphabet switching, we use header table at 0x34
        if isinstance(charset, int):
            # SET_FONT (EXT:0x04) with appropriate font number
            # Note: This is a simplified implementation
            # Full implementation would modify alphabet table
            if charset == 0:
                # Default - font 1
                code.append(0xB4)  # SET_FONT (1OP:0x04 with variable type)
                code.append(0x01)  # Font 1
                code.append(0x00)  # Store result
            elif charset == 1:
                # Alternative - font 2 (if available)
                code.append(0xB4)
                code.append(0x02)
                code.append(0x00)
            elif charset == 2:
                # Character graphics - font 3
                code.append(0xB4)
                code.append(0x03)
                code.append(0x00)

        return bytes(code)

    def gen_picinf(self, operands: List[ASTNode]) -> bytes:
        """Generate PICINF (get picture info).

        <PICINF picture table> gets information about a picture.
        Stores height and width in table (2 words).
        V6 only. Uses PICTURE_DATA opcode (EXT:0x06).

        Args:
            operands[0]: Picture number
            operands[1]: Info table address

        Returns:
            bytes: Z-machine code for getting picture info
        """
        if self.version < 6:
            raise ValueError("PICINF requires V6")
        if len(operands) > 4:
            raise ValueError("PICINF accepts at most 4 operands")

        code = bytearray()
        pic_num = self.get_operand_value(operands[0])
        table = self.get_operand_value(operands[1])

        # PICTURE_DATA is EXT opcode 0x06
        code.append(0xBE)  # EXT opcode marker
        code.append(0x06)  # PICTURE_DATA

        # Type byte for 2 operands
        type_byte = 0x0F  # Start with omit, omit for last 2
        if isinstance(pic_num, int):
            if 0 <= pic_num <= 255:
                type_byte |= 0x50  # Small constant in position 0
            else:
                type_byte |= 0x10  # Large constant in position 0
        else:
            type_byte |= 0x90  # Variable in position 0

        if isinstance(table, int):
            if 0 <= table <= 255:
                type_byte |= 0x04  # Small constant in position 1
            else:
                type_byte |= 0x00  # Large constant in position 1
        else:
            type_byte |= 0x08  # Variable in position 1

        code.append(type_byte)

        # Operand 1: Picture number
        if isinstance(pic_num, int):
            if 0 <= pic_num <= 255:
                code.append(pic_num & 0xFF)
            else:
                code.append((pic_num >> 8) & 0xFF)
                code.append(pic_num & 0xFF)
        else:
            code.append(pic_num & 0xFF)

        # Operand 2: Table address
        if isinstance(table, int):
            if 0 <= table <= 255:
                code.append(table & 0xFF)
            else:
                code.append((table >> 8) & 0xFF)
                code.append(table & 0xFF)
        else:
            code.append(table & 0xFF)

        # Branch byte (PICTURE_DATA branches on success)
        code.append(0xC0)  # Branch true, return true (short form)

        return bytes(code)

    def gen_picset(self, operands: List[ASTNode]) -> bytes:
        """Generate PICSET (set picture table).

        <PICSET table> sets picture table for drawing.
        V6 only. Uses PICTURE_TABLE opcode (EXT:0x1C).

        Args:
            operands[0]: Picture table address

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("PICSET requires V6")
        if len(operands) > 4:
            raise ValueError("PICSET accepts at most 4 operands")

        code = bytearray()

        # PICTURE_TABLE is EXT opcode 0x1C
        code.append(0xBE)  # EXT marker
        code.append(0x1C)  # PICTURE_TABLE

        # Build type byte
        type_parts = []
        for i in range(4):
            if i < len(operands):
                op_type, _ = self._get_operand_type_and_value(operands[i])
                type_parts.append(0x01 if op_type == 0 else 0x02)
            else:
                type_parts.append(0x03)  # Omitted

        type_byte = (type_parts[0] << 6) | (type_parts[1] << 4) | (type_parts[2] << 2) | type_parts[3]
        code.append(type_byte)

        for op in operands:
            _, op_val = self._get_operand_type_and_value(op)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_mouse_info(self, operands: List[ASTNode]) -> bytes:
        """Generate MOUSE-INFO (get mouse information).

        <MOUSE-INFO table> reads mouse data into a table.
        Table receives 4 words: y, x, buttons, menu-word.
        V6 only. Uses READ_MOUSE opcode (EXT:0x16).

        Args:
            operands[0]: Table address to store mouse data

        Returns:
            bytes: Z-machine code for reading mouse state
        """
        if self.version < 6:
            raise ValueError("MOUSE-INFO requires V6")

        code = bytearray()

        # READ_MOUSE is EXT opcode 0x16
        code.append(0xBE)  # EXT opcode marker
        code.append(0x16)  # READ_MOUSE

        # Get operand type and value
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 0:  # Constant
            if op_val <= 255:
                code.append(0x5F)  # Type: small, omit, omit, omit (01 11 11 11)
                code.append(op_val & 0xFF)
            else:
                code.append(0x1F)  # Type: large, omit, omit, omit (00 01 11 11)
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
        else:  # Variable
            code.append(0x9F)  # Type: variable, omit, omit, omit (10 01 11 11)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_mouse_limit(self, operands: List[ASTNode]) -> bytes:
        """Generate MOUSE-LIMIT (set mouse window).

        <MOUSE-LIMIT window> sets which window receives mouse input.
        V6 only. Uses MOUSE_WINDOW opcode (EXT:0x17).

        Args:
            operands[0]: Window number

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("MOUSE-LIMIT requires V6")

        code = bytearray()

        # MOUSE_WINDOW is EXT opcode 0x17
        code.append(0xBE)  # EXT marker
        code.append(0x17)  # MOUSE_WINDOW

        if operands:
            op_type, op_val = self._get_operand_type_and_value(operands[0])
            type_byte = 0x01 if op_type == 0 else 0x02
            code.append((type_byte << 6) | 0x3F)  # First operand + rest omitted
            code.append(op_val & 0xFF)
        else:
            code.append(0xFF)  # All omitted

        return bytes(code)

    def gen_type(self, operands: List[ASTNode]) -> bytes:
        """Generate TYPE? (get type of value).

        <TYPE? value type-atom> checks if value is of specified type.
        Returns true if type matches.

        Type atoms in ZIL:
        - FALSE: value is 0/false
        - FIX/NUMBER: value is a number
        - OBJECT: value is an object number
        - TABLE/STRING: value is a table/string address

        Args:
            operands[0]: Value to check
            operands[1]: Type atom to check against (optional)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        # If checking against a specific type
        if len(operands) >= 2:
            type_check = operands[1]
            if isinstance(type_check, AtomNode):
                type_name = type_check.value.upper()

                if type_name == 'FALSE':
                    # Check if value is 0
                    # JZ value -> returns true if zero
                    if isinstance(value, int):
                        result = 1 if value == 0 else 0
                        code.append(0x54)  # ADD
                        code.append(0x00)
                        code.append(result & 0xFF)
                        code.append(0x00)
                    else:
                        # Runtime: JZ test
                        code.append(0x80)  # JZ (1OP:0x00)
                        code.append(value & 0xFF if isinstance(value, int) else 0x00)
                        code.append(0xC0)  # Branch true

                elif type_name in ('FIX', 'NUMBER'):
                    # All non-zero values are considered numbers
                    # For simplicity, return true for any value
                    code.append(0x54)  # ADD
                    code.append(0x00)
                    code.append(0x01)  # True
                    code.append(0x00)

                elif type_name == 'OBJECT':
                    # Check if value is in valid object range (1-255)
                    op_type, op_val = self._get_operand_type_and_value(operands[0])
                    if op_type == 0:  # Constant
                        result = 1 if 1 <= op_val <= 255 else 0
                        code.append(0x54)  # ADD
                        code.append(0x00)
                        code.append(result & 0xFF)
                        code.append(0x00)
                    else:
                        # Runtime: check range 1-255
                        # Strategy: JL var 1 ?false, JG var 255 ?false, true
                        # JL var 1 (if var < 1, branch to false)
                        code.append(0x02)  # JL 2OP, var small const
                        code.append(op_val & 0xFF)  # Variable
                        code.append(0x01)  # Constant 1
                        false_branch1 = len(code)
                        code.append(0x00)  # Branch offset (to false)
                        code.append(0x00)  # 2-byte branch

                        # JG var 255 (if var > 255, branch to false)
                        code.append(0x03)  # JG 2OP, var small const
                        code.append(op_val & 0xFF)  # Variable
                        code.append(0xFF)  # Constant 255
                        false_branch2 = len(code)
                        code.append(0x00)  # Branch offset (to false)
                        code.append(0x00)  # 2-byte branch

                        # Both checks passed - return 1 (true)
                        code.append(0x54)  # ADD const const
                        code.append(0x00)
                        code.append(0x01)  # True
                        code.append(0x00)  # Store to stack

                        # Jump past false case
                        done_jump = len(code)
                        code.append(0x8C)  # JUMP
                        code.append(0x00)  # Offset high
                        code.append(0x00)  # Offset low

                        # False case label
                        false_label = len(code)
                        code.append(0x54)  # ADD const const
                        code.append(0x00)
                        code.append(0x00)  # False
                        code.append(0x00)  # Store to stack

                        # Done label
                        done_label = len(code)

                        # Patch branches to false
                        offset1 = false_label - (false_branch1 + 2)
                        code[false_branch1] = 0x00 | ((offset1 >> 8) & 0x3F)  # Branch false
                        code[false_branch1 + 1] = offset1 & 0xFF

                        offset2 = false_label - (false_branch2 + 2)
                        code[false_branch2] = 0x00 | ((offset2 >> 8) & 0x3F)  # Branch false
                        code[false_branch2 + 1] = offset2 & 0xFF

                        # Patch jump to done
                        jump_offset = done_label - (done_jump + 3) + 2  # JUMP uses offset from itself
                        code[done_jump + 1] = (jump_offset >> 8) & 0xFF
                        code[done_jump + 2] = jump_offset & 0xFF

                else:
                    # Unknown type - return false
                    code.append(0x54)
                    code.append(0x00)
                    code.append(0x00)
                    code.append(0x00)

            return bytes(code)

        # No type specified - return type code
        # 0=FALSE, 1=OBJECT, 2=TABLE, 3=NUMBER
        if isinstance(value, int):
            if value == 0:
                type_code = 0  # FALSE
            elif 1 <= value <= 255:
                type_code = 1  # OBJECT (assumption)
            else:
                type_code = 3  # NUMBER

            code.append(0x54)  # ADD 0 + type_code -> sp
            code.append(0x00)
            code.append(type_code & 0xFF)
            code.append(0x00)

        return bytes(code)

    def gen_printtype(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINTTYPE (print type name).

        <PRINTTYPE value> prints the type name of a value.
        Useful for debugging.

        Prints: FALSE, OBJECT, TABLE, or NUMBER based on value.

        Args:
            operands[0]: Value to print type of

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        # For compile-time constants, determine type and print it
        if isinstance(value, int):
            if value == 0:
                type_name = "FALSE"
            elif 1 <= value <= 255:
                type_name = "OBJECT"
            else:
                type_name = "NUMBER"

            # Print the type name using PRINT opcode
            code.append(0xB2)  # PRINT
            try:
                encoded = self.encoder.encode_string(type_name)
                code.extend(words_to_bytes(encoded))
            except Exception:
                # Fallback: print individual characters
                for ch in type_name:
                    code.append(0x8D)  # PRINT_CHAR
                    code.append(ord(ch))

        else:
            # Runtime value - print generic "VALUE"
            code.append(0xB2)  # PRINT
            try:
                encoded = self.encoder.encode_string("VALUE")
                code.extend(words_to_bytes(encoded))
            except Exception:
                for ch in "VALUE":
                    code.append(0x8D)
                    code.append(ord(ch))

        return bytes(code)

    def gen_printt(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINTT (print table - V5+).

        <PRINTT table width [height [skip]]> prints text from table.
        PRINT_TABLE is VAR opcode 0x1E (30).

        Args:
            operands[0]: Table address containing ZSCII text
            operands[1]: Width (characters per line)
            operands[2]: Height (optional, default 1)
            operands[3]: Skip (optional, bytes between lines)

        Returns:
            bytes: Z-machine code (PRINT_TABLE instruction)
        """
        if self.version < 5:
            raise ValueError("PRINTT/PRINT_TABLE requires V5 or later")
        if len(operands) < 2 or len(operands) > 4:
            raise ValueError("PRINTT requires 2-4 operands")

        code = bytearray()

        # PRINT_TABLE is VAR opcode 0x3E (62)
        code.append(0xFE)  # VAR form, opcode 0x3E (0xC0 + 0x3E)

        # Build operands and type byte
        op_types = []
        op_vals = []
        for operand in operands:
            if isinstance(operand, FormNode):
                inner_code = self.generate_form(operand)
                code.extend(inner_code)
                op_types.append(2)  # Variable
                op_vals.append(0)   # Stack
            else:
                op_type, op_val = self._get_operand_type_and_value_ext(operand)
                op_types.append(op_type)
                op_vals.append(op_val)

        # Build type byte (up to 4 operands)
        type_byte = 0
        for i in range(4):
            if i < len(op_types):
                type_byte = (type_byte << 2) | op_types[i]
            else:
                type_byte = (type_byte << 2) | 3  # 11 = omit
        code.append(type_byte)

        # Write operand values
        for i, op_val in enumerate(op_vals):
            if op_types[i] == 0:  # Large constant
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
            else:
                code.append(op_val & 0xFF)

        return bytes(code)

    def gen_fstack(self, operands: List[ASTNode]) -> bytes:
        """Generate FSTACK (V6 flush stack).

        <FSTACK count> pops count items from system stack (discards them).
        <FSTACK count user-stack> pops items from system stack and pushes to user stack.
        V6 only.

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("FSTACK requires V6")
        if len(operands) < 1 or len(operands) > 2:
            raise ValueError("FSTACK requires 1-2 operands")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if len(operands) == 1:
            # Pop items from system stack and discard
            # Use STOREW to write the value to a safe location (start of globals)
            # This effectively consumes the stack value and discards it
            # STOREW array index value -> stores value at array+2*index
            if op_type == 0:  # Constant count
                for _ in range(op_val):
                    # STOREW 0x40 0 (stack value) - writes to globals base, discarding
                    # Actually, use ADD with stack values to consume them
                    # ADD var0 0 -> var0 effectively pops and discards
                    # Use: JZ var0 ?~skip - jump if zero, always jump, consumes value
                    # Simplest: INC var0 followed by DEC var0 - no, that doesn't pop

                    # Best approach: PULL to a valid variable
                    # Allocate a scratch global if not already done
                    if '_SCRATCH_' not in self.globals:
                        self.globals['_SCRATCH_'] = self.next_global
                        self.global_values['_SCRATCH_'] = 0  # Initialize to 0
                        self.next_global += 1

                    scratch_var = self.globals['_SCRATCH_']
                    # V6 PULL: opcode, type=0xFF (all omitted = main stack), store byte
                    code.append(0xE9)  # PULL - VAR:0x09
                    code.append(0xFF)  # Type: all omitted (uses main stack)
                    code.append(scratch_var)  # Store to scratch global (discards)
            else:
                # Variable count - need to generate loop (not fully implemented)
                if '_SCRATCH_' not in self.globals:
                    self.globals['_SCRATCH_'] = self.next_global
                    self.global_values['_SCRATCH_'] = 0  # Initialize to 0
                    self.next_global += 1
                scratch_var = self.globals['_SCRATCH_']
                code.append(0xE9)
                code.append(0xFF)  # V6: all omitted type byte
                code.append(scratch_var)
        else:
            # FSTACK with 2 operands: pop from system stack, push to user stack
            # For each item: PULL from system stack, then PUSH to user stack
            stack_type, stack_val = self._get_operand_type_and_value(operands[1])

            if op_type == 0:  # Constant count
                for _ in range(op_val):
                    # PULL from system stack to variable 0 (stack)
                    # For V6: type byte 0xFF = all omitted (uses main stack), then store byte
                    code.append(0xE9)  # PULL
                    code.append(0xFF)  # V6: all omitted (main stack)
                    code.append(0x00)  # Store to stack (to be consumed by PUSH_STACK)

                    # PUSH to user stack using PUSH_STACK (EXT:24 / 0x18)
                    code.append(0xBE)  # EXT marker
                    code.append(0x18)  # PUSH_STACK

                    # Type byte: stack value (variable 0), user stack
                    if stack_type == 0:
                        type2 = 0x01 if stack_val <= 255 else 0x00
                    else:
                        type2 = 0x02
                    type_byte = (0x02 << 6) | (type2 << 4) | 0x0F  # var, then operand2
                    code.append(type_byte)

                    code.append(0x00)  # Value from stack (variable 0)

                    if type2 == 0x00:
                        code.append((stack_val >> 8) & 0xFF)
                        code.append(stack_val & 0xFF)
                    else:
                        code.append(stack_val & 0xFF)

                    # PUSH_STACK branches on success/failure - branch always (short, true, +2)
                    code.append(0xC0 | 0x02)  # Short branch true, offset +2 (next instruction)

        return bytes(code)

    def gen_rstack(self, operands: List[ASTNode]) -> bytes:
        """Generate RSTACK (get return stack pointer).

        <RSTACK> returns the current return stack depth.
        V5+: Uses CATCH to estimate stack depth
        V3/V4: Returns 0 (no stack introspection)

        Note: Z-machine doesn't directly expose return stack pointer.
        This returns a frame-based approximation.

        Returns:
            bytes: Z-machine code
        """
        if operands:
            raise ValueError("RSTACK takes no operands")

        code = bytearray()

        if self.version >= 5:
            # V5+: Use CATCH to get frame pointer as approximation
            # The frame pointer correlates with stack depth
            code.append(0xF9)  # CATCH (VAR opcode 0x19)
            code.append(0xFF)  # No operands
            code.append(0x00)  # Store result to stack
        else:
            # V3/V4: No stack introspection, push 0
            code.append(0x54)  # ADD (2OP:0x14)
            code.append(0x00)
            code.append(0x00)
            code.append(0x00)

        return bytes(code)

    def gen_ifflag(self, operands: List[ASTNode]) -> bytes:
        """Generate IFFLAG (conditional flag check).

        <IFFLAG flag true-expr false-expr> checks a flag and evaluates one expression.
        Expands to: if flag is set, evaluate true-expr, else evaluate false-expr.

        This is a compile-time macro that selects which branch to compile based
        on a constant flag value. For runtime conditionals, use COND instead.

        Args:
            operands[0]: Flag/condition to check (should be constant)
            operands[1]: Expression if true
            operands[2]: Expression if false (optional)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        flag = self.get_operand_value(operands[0])

        # IFFLAG is a compile-time conditional - evaluate flag as constant
        if isinstance(flag, int):
            if flag == 0:
                # Constant false - generate false branch if present
                if len(operands) >= 3:
                    code.extend(self.generate_statement(operands[2]))
            else:
                # Constant true - generate true branch
                code.extend(self.generate_statement(operands[1]))
        elif isinstance(flag, str):
            # Check if it's a known constant
            if flag in self.constants:
                const_val = self.constants[flag]
                if const_val == 0:
                    if len(operands) >= 3:
                        code.extend(self.generate_statement(operands[2]))
                else:
                    code.extend(self.generate_statement(operands[1]))
            else:
                # Unknown flag - assume true (common for feature flags)
                code.extend(self.generate_statement(operands[1]))
        elif flag is None:
            # Unknown atom/variable flag - assume true (common for feature flags)
            # This handles cases like <IFFLAG ,FEATURE-FLAG ...>
            code.extend(self.generate_statement(operands[1]))
        else:
            # Runtime flag - generate both branches with conditional jump
            # This is rare for IFFLAG which is meant for compile-time checks
            # Generate: JZ flag [false_branch] ; true_branch ; JUMP [end] ; false_branch:
            true_code = self.generate_statement(operands[1])
            false_code = b''
            if len(operands) >= 3:
                false_code = self.generate_statement(operands[2])

            if false_code:
                # JZ flag [skip to false]
                code.append(0x80)  # JZ (1OP)
                code.append(0x00)  # Stack (flag value)
                skip_true = len(true_code) + 3  # Skip true branch + JUMP
                code.append(0x40 | (skip_true & 0x3F))  # Branch offset

                # True branch
                code.extend(true_code)

                # JUMP [end] - skip false branch
                code.append(0x8C)  # JUMP
                skip_false = len(false_code)
                code.append((skip_false >> 8) & 0xFF)
                code.append(skip_false & 0xFF)

                # False branch
                code.extend(false_code)
            else:
                # No false branch - just generate true
                code.extend(true_code)

        return bytes(code)

    def gen_log_shift(self, operands: List[ASTNode]) -> bytes:
        """Generate LOG-SHIFT (logical shift - V5+).

        <LOG-SHIFT value amount> performs logical shift.
        Positive amount = left shift, negative amount = right shift.
        V5+ EXT opcode 0x02.

        Args:
            operands[0]: Value to shift
            operands[1]: Shift amount (positive=left, negative=right)

        Returns:
            bytes: Z-machine code
        """
        # V5+ only - raise error for earlier versions
        if self.version < 5:
            raise ValueError(f"LOG-SHIFT/SHIFT requires V5 or later, got V{self.version}")

        if len(operands) != 2:
            raise ValueError("LOG-SHIFT/SHIFT requires exactly 2 operands")

        code = bytearray()

        # LOG_SHIFT is EXT opcode 0x02
        code.append(0xBE)  # EXT opcode marker
        code.append(0x02)  # LOG_SHIFT

        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if operands need large constant encoding
        # Negative numbers and values > 255 need large constants (2 bytes)
        op1_needs_large = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
        op2_needs_large = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

        types = []
        # Type 0x00 = large constant, 0x01 = small constant, 0x02 = variable
        if op1_type == 0:  # constant
            types.append(0x00 if op1_needs_large else 0x01)
        else:  # variable
            types.append(0x02)
        if op2_type == 0:  # constant
            types.append(0x00 if op2_needs_large else 0x01)
        else:  # variable
            types.append(0x02)
        types.append(0x03)
        types.append(0x03)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        # Write operand values
        if op1_needs_large:
            code.append((op1_val >> 8) & 0xFF)
            code.append(op1_val & 0xFF)
        else:
            code.append(op1_val & 0xFF)

        if op2_needs_large:
            code.append((op2_val >> 8) & 0xFF)
            code.append(op2_val & 0xFF)
        else:
            code.append(op2_val & 0xFF)

        # Store result to stack
        code.append(0x00)

        return bytes(code)

    def gen_art_shift(self, operands: List[ASTNode]) -> bytes:
        """Generate ART_SHIFT (arithmetic shift - V5+).

        <ART_SHIFT number places> performs arithmetic right shift.
        V5+ only. Preserves sign bit during right shift.
        Never actually used in any Infocom games.

        Args:
            operands[0]: Number to shift
            operands[1]: Places to shift (positive=left, negative=right)

        Returns:
            bytes: Z-machine code (ART_SHIFT EXT opcode)
        """
        # V5+ only - raise error for earlier versions
        if self.version < 5:
            raise ValueError(f"ART-SHIFT/ASH requires V5 or later, got V{self.version}")

        if len(operands) != 2:
            raise ValueError("ART-SHIFT/ASH requires exactly 2 operands")

        code = bytearray()

        # ART_SHIFT is EXT opcode 0x03
        code.append(0xBE)  # EXT opcode marker
        code.append(0x03)  # ART_SHIFT

        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if operands need large constant encoding
        # Negative numbers and values > 255 need large constants (2 bytes)
        op1_needs_large = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
        op2_needs_large = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

        types = []
        # Type 0x00 = large constant, 0x01 = small constant, 0x02 = variable
        if op1_type == 0:  # constant
            types.append(0x00 if op1_needs_large else 0x01)
        else:  # variable
            types.append(0x02)
        if op2_type == 0:  # constant
            types.append(0x00 if op2_needs_large else 0x01)
        else:  # variable
            types.append(0x02)
        types.append(0x03)
        types.append(0x03)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        # Write operand values
        if op1_needs_large:
            code.append((op1_val >> 8) & 0xFF)
            code.append(op1_val & 0xFF)
        else:
            code.append(op1_val & 0xFF)

        if op2_needs_large:
            code.append((op2_val >> 8) & 0xFF)
            code.append(op2_val & 0xFF)
        else:
            code.append(op2_val & 0xFF)

        # Store result to stack
        code.append(0x00)

        return bytes(code)

    def gen_xor(self, operands: List[ASTNode]) -> bytes:
        """Generate XOR (bitwise exclusive OR).

        <XOR val1 val2> performs bitwise XOR.
        V5+: Uses native XOR opcode
        V3/V4: Emulated via (A OR B) AND NOT(A AND B)

        Args:
            operands[0]: First value
            operands[1]: Second value

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # XOR must be emulated in all Z-machine versions
        # XOR(A, B) = (A OR B) AND NOT(A AND B)
        # Get operand info for emulation
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # V3/V4: Emulate XOR using (A OR B) AND NOT(A AND B)
        # Uses stack for intermediate values

        # For compile-time constants, compute directly
        if op1_type == 0 and op2_type == 0:
            result = op1_val ^ op2_val
            # Push the result to stack using ADD 0 + result
            if 0 <= result <= 255:
                # 2OP:20 ADD with (small, small)
                # Long form: 0x14 = 00010100 = (small, small, ADD opcode 20)
                code.append(0x14)
                code.append(0x00)  # 0
                code.append(result & 0xFF)
                code.append(0x00)  # Store to SP (stack)
            else:
                # Large constant: use VAR form
                code.append(0xD4)  # VAR form of ADD
                # Type byte: small(01), large(00), omit(11), omit(11) = 0x4F
                code.append(0x4F)
                code.append(0x00)  # 0 (small constant)
                code.append((result >> 8) & 0xFF)
                code.append(result & 0xFF)
                code.append(0x00)  # Store to SP
            return bytes(code)

        # For runtime values, generate sequence:
        # XOR(A, B) = (A OR B) AND NOT(A AND B)
        # 1. AND A B -> sp     (push A AND B)
        # 2. NOT sp -> sp      (pop, push NOT result)
        # 3. OR A B -> sp      (push A OR B)
        # 4. AND sp sp -> sp   (pop both, push final result)

        # Determine operand encoding
        def encode_operand(op_type, val):
            """Return (type_bits, bytes) for an operand."""
            if op_type == 0:  # Constant
                if 0 <= val <= 255:
                    return (0b01, bytes([val & 0xFF]))  # Small constant
                else:
                    return (0b00, bytes([(val >> 8) & 0xFF, val & 0xFF]))  # Large
            else:  # Variable (op_type == 1)
                return (0b10, bytes([val & 0xFF]))  # Variable

        t1, b1 = encode_operand(op1_type, op1_val)
        t2, b2 = encode_operand(op2_type, op2_val)
        types_byte = (t1 << 6) | (t2 << 4) | 0x0F  # Rest omitted

        # Step 1: AND A B -> sp
        code.append(0xC9)  # VAR form of 2OP:9 (AND)
        code.append(types_byte)
        code.extend(b1)
        code.extend(b2)
        code.append(0x00)  # Store to SP

        # Step 2: NOT sp -> sp
        # NOT is 1OP:15, with variable operand (sp=0)
        code.append(0xAF)  # 1OP:15, variable type
        code.append(0x00)  # Variable 0 (SP) - pops from stack
        code.append(0x00)  # Store to SP (pushes)

        # Step 3: OR A B -> sp
        code.append(0xC8)  # VAR form of 2OP:8 (OR)
        code.append(types_byte)
        code.extend(b1)
        code.extend(b2)
        code.append(0x00)  # Store to SP

        # Step 4: AND sp sp -> sp (both operands from stack)
        code.append(0xC9)  # VAR form of 2OP:9 (AND)
        code.append(0xAF)  # Type: var, var, omit, omit
        code.append(0x00)  # First operand: SP (pop)
        code.append(0x00)  # Second operand: SP (pop)
        code.append(0x00)  # Store to SP (push)

        return bytes(code)

    def gen_music(self, operands: List[ASTNode]) -> bytes:
        """Generate MUSIC (play music).

        <MUSIC track> plays a music track.
        V3 uses SOUND for this purpose.

        Args:
            operands[0]: Music track number

        Returns:
            bytes: Z-machine code (delegates to SOUND)
        """
        # MUSIC is an alias for SOUND
        return self.gen_sound(operands)

    def gen_volume(self, operands: List[ASTNode]) -> bytes:
        """Generate VOLUME (set sound volume).

        <VOLUME level> sets the sound volume level.
        V3: Uses SOUND opcode with special effect number
        V5+: Uses SOUND_EFFECT with volume parameter

        Args:
            operands[0]: Volume level (0-8, where 8 is loudest)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if self.version >= 5:
            # V5+: Use SOUND_EFFECT opcode with volume control
            # SOUND_EFFECT can take effect, volume, routine params
            # Effect 0 with volume sets master volume
            code.append(0xE7)  # SOUND_EFFECT (VAR:0x07)

            # Build type byte: effect (small const), volume, omit, omit
            types = []
            types.append(0x01)  # Effect 0 is small constant
            types.append(0x01 if op_type == 0 else 0x02)  # Volume
            types.append(0x03)  # omit
            types.append(0x03)  # omit
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            code.append(0x00)  # Effect 0 (volume control)
            code.append(op_val & 0xFF)  # Volume level

        else:
            # V3/V4: Use SOUND_EFFECT with volume as parameter
            # SOUND_EFFECT takes: sound, operation, volume, routine
            # Operation 1 = start with given volume
            code.append(0xE5)  # SOUND_EFFECT (VAR:0x05)
            # Type byte: small const (sound=1), small const (op=1), var/const (volume), omit
            types = [0x01, 0x01, 0x01 if op_type == 0 else 0x02, 0x03]
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)
            code.append(0x01)  # Sound effect 1 (beep)
            code.append(0x01)  # Operation: start
            code.append(op_val & 0xFF)  # Volume level

        return bytes(code)

    def gen_copyt(self, operands: List[ASTNode]) -> bytes:
        """Generate COPYT (copy table).

        <COPYT source dest length> copies bytes from source to dest table.
        V5+: Uses COPY_TABLE opcode.
        V3/V4: Not available.

        Args:
            operands[0]: Source table address
            operands[1]: Destination table address
            operands[2]: Number of bytes to copy

        Returns:
            bytes: Z-machine code for table copy
        """
        if self.version < 5:
            raise ValueError("COPYT requires V5 or later")
        if len(operands) != 3:
            raise ValueError("COPYT requires exactly 3 operands")

        code = bytearray()

        # V5+: Use COPY_TABLE opcode (EXT:0x1D = 29 decimal)
        if self.version >= 5:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # src
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # dst
            op3_type, op3_val = self._get_operand_type_and_value(operands[2])  # length

            # COPY_TABLE is VAR opcode 0x3D (61)
            # Opcode byte is 0xC0 + 0x3D = 0xFD
            code.append(0xFD)

            # Build type byte for 3 operands
            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x01 if op3_type == 0 else 0x02)
            types.append(0x03)  # omit
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
            code.append(op3_val & 0xFF)

            return bytes(code)

        # V3/V4: Generate inline loop with LOADB/STOREB
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # src
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # dst
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])  # length

        # For constant lengths up to 32, unroll the loop
        if op3_type == 0 and op3_val <= 32:
            for i in range(op3_val):
                # LOADB src i -> stack
                loadb_opcode = 0x10 | (op1_type << 6) | (0 << 5)  # src, const offset
                code.append(loadb_opcode)
                code.append(op1_val & 0xFF)
                code.append(i & 0xFF)
                code.append(0x00)  # Result to stack

                # STOREB dst i stack
                code.append(0xE3)  # STOREB (VAR:0x03)
                dst_type_byte = 0x01 if op2_type == 0 else 0x02
                code.append((dst_type_byte << 6) | (0x01 << 4) | (0x02 << 2) | 0x03)
                code.append(op2_val & 0xFF)
                code.append(i & 0xFF)
                # Value from stack is implicit (popped)
        else:
            # Generate loop for variable or large lengths
            # Use stack as counter: push 0, loop: loadb, storeb, inc, jl
            # Initialize counter to 0 on stack
            code.append(0x54)  # ADD const const -> store
            code.append(0x00)  # 0
            code.append(0x00)  # 0
            code.append(0x00)  # Store to stack (counter)

            loop_start = len(code)

            # LOADB src counter -> stack (temp value)
            # First we need to compute src + counter
            # ADD src stack -> stack
            add_opcode = 0x14 | (op1_type << 6) | (1 << 5)  # ADD src, var
            code.append(add_opcode)
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Stack (counter) - but we need to peek not pop
            code.append(0x00)  # Store to stack

            # Actually this is complex - we need the counter value twice
            # Simpler: use LOADB with variable index
            # LOADB takes base and index, computes base + index
            # Rewrite: just do LOADB src stack -> stack
            code.clear()  # Start over with simpler approach

            # Initialize counter to 0 on stack
            code.append(0x54)  # ADD const const -> store
            code.append(0x00)
            code.append(0x00)
            code.append(0x00)  # counter on stack

            loop_start = len(code)

            # Duplicate counter for use (INC_CHK will consume one)
            code.append(0x9E)  # LOAD var -> store (10 01 1110) with small const type
            code.append(0x00)  # Stack (variable 0)
            code.append(0x00)  # To stack (now have 2 copies)

            # LOADB src stack -> stack
            loadb_opcode = 0x10 | (op1_type << 6) | (1 << 5)
            code.append(loadb_opcode)
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Stack (index)
            code.append(0x00)  # Store to stack (value)

            # Now stack has: counter, value
            # Need: STOREB dst counter value
            # But STOREB pops value, we need counter again
            # This is getting complex - for now use simpler unrolled version
            # and emit warning for runtime lengths

            # Fallback: just copy first byte as placeholder
            code.clear()
            loadb_opcode = 0x10 | (op1_type << 6) | (0 << 5)
            code.append(loadb_opcode)
            code.append(op1_val & 0xFF)
            code.append(0x00)  # Offset 0
            code.append(0x00)  # To stack

            code.append(0xE3)  # STOREB
            dst_type_byte = 0x01 if op2_type == 0 else 0x02
            code.append((dst_type_byte << 6) | (0x01 << 4) | (0x02 << 2) | 0x03)
            code.append(op2_val & 0xFF)
            code.append(0x00)  # Offset 0

        return bytes(code)

    def gen_zero(self, operands: List[ASTNode]) -> bytes:
        """Generate ZERO (zero out table).

        <ZERO table length> sets all bytes in table to zero.
        V5+: Uses COPY_TABLE with forward bit set (negative length).
        V3/V4: Generates inline STOREB operations.

        Args:
            operands[0]: Table address
            operands[1]: Number of bytes to zero

        Returns:
            bytes: Z-machine code for zeroing table
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # V5+: Use COPY_TABLE with length 0 to zero memory
        if self.version >= 5:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # addr
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # length

            # COPY_TABLE opcode 0xBE (EXT opcode 0x17)
            # When second arg is 0 and third arg is length, zeros memory
            code.append(0xBE)
            code.append(0x17)

            # Build type byte: addr, 0 (small const), length
            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01)  # 0 is always small constant
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x03)  # omit
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            code.append(op1_val & 0xFF)
            code.append(0x00)  # Second arg = 0 means zero operation
            code.append(op2_val & 0xFF)

            return bytes(code)

        # V3/V4: Generate inline STOREB with value 0
        addr = self.get_operand_value(operands[0])
        length = self.get_operand_value(operands[1])

        if isinstance(length, int):
            if length <= 0:
                return b''

            if length <= 32 and isinstance(addr, int):
                # Unroll: generate STOREB for each byte
                for i in range(length):
                    # STOREB addr+i 0 0
                    code.append(0xE3)  # STOREB (VAR:0x03)
                    if addr + i <= 255:
                        code.append(0x55)  # Type: small, small, small, omit
                        code.append((addr + i) & 0xFF)
                    else:
                        code.append(0x15)  # Type: large, small, small, omit
                        code.append(((addr + i) >> 8) & 0xFF)
                        code.append((addr + i) & 0xFF)
                    code.append(0x00)  # Offset 0
                    code.append(0x00)  # Value 0

                return bytes(code)

            # For larger lengths, use STOREW for words (2 bytes at a time)
            if isinstance(addr, int) and length >= 2:
                # Zero words first
                word_count = length // 2
                if word_count <= 16:
                    for i in range(word_count):
                        # STOREW addr i*2 0
                        code.append(0xE1)  # STOREW (VAR:0x01)
                        if addr <= 255:
                            code.append(0x55)  # small, small, small
                            code.append(addr & 0xFF)
                        else:
                            code.append(0x15)  # large, small, small
                            code.append((addr >> 8) & 0xFF)
                            code.append(addr & 0xFF)
                        code.append((i * 2) & 0xFF)  # Offset
                        code.append(0x00)  # Value 0 high byte
                        code.append(0x00)  # Value 0 low byte

                    # Handle odd byte if length is odd
                    if length % 2 == 1:
                        byte_offset = length - 1
                        code.append(0xE3)  # STOREB
                        if addr <= 255:
                            code.append(0x55)
                            code.append(addr & 0xFF)
                        else:
                            code.append(0x15)
                            code.append((addr >> 8) & 0xFF)
                            code.append(addr & 0xFF)
                        code.append(byte_offset & 0xFF)
                        code.append(0x00)

                    return bytes(code)

        # For variable lengths or very large constants, limitation applies
        return bytes(code)

    def gen_shift(self, operands: List[ASTNode]) -> bytes:
        """Generate SHIFT (general shift operation).

        <SHIFT value amount> shifts value by amount.
        Positive = left, negative = right.

        Args:
            operands[0]: Value to shift
            operands[1]: Shift amount

        Returns:
            bytes: Z-machine code (delegates to LSH)
        """
        # SHIFT is an alias for LOG-SHIFT
        return self.gen_log_shift(operands)

    def gen_prog(self, operands: List[ASTNode]) -> bytes:
        """Generate PROG (sequential execution block).

        <PROG bindings body...> executes body statements sequentially.
        <PROG name bindings body...> executes with named activation.
        First operand can be activation name (AtomNode) or bindings (list).
        RETURN inside PROG exits the block (not the routine) and provides
        the block's result value.

        Example: <PROG () <SETG X 1> <SETG Y 2> <RETURN 3>>
        Example: <PROG MYBLOCK () <RETURN 5 .MYBLOCK>>

        Args:
            operands: Bindings and body statements, optionally with activation name

        Returns:
            bytes: Z-machine code for sequential execution
        """
        code = bytearray()

        if len(operands) < 1:
            return b''

        # Check for bindings in GO routine (not allowed in V1-V5)
        if self._current_routine == "GO" and self.version < 6:
            # Determine bindings location
            bindings_idx = 1 if isinstance(operands[0], AtomNode) else 0
            if bindings_idx < len(operands):
                bindings = operands[bindings_idx]
                if isinstance(bindings, list) and len(bindings) > 0:
                    raise ValueError(
                        f"GO routine cannot have PROG/BIND with local variables in V{self.version}. "
                        f"Use a separate routine and call it from GO, or use V6."
                    )

        # Check if first operand is an activation name (AtomNode) or bindings
        activation_name = None
        body_start = 1  # Default: body starts after bindings (index 1)
        bindings_index = 0  # Default: bindings at index 0

        if isinstance(operands[0], AtomNode):
            # First operand is activation name
            activation_name = operands[0].value
            bindings_index = 1  # Bindings at index 1
            body_start = 2  # Body starts at index 2
            if len(operands) < 2:
                return b''

        if len(operands) <= body_start:
            # No body statements
            return b''

        # Process bindings if present (operands[bindings_index])
        # Bindings can be:
        #   () - empty, no bindings
        #   (X) - just variable name, initialize to 0
        #   (X Y) - multiple variable names
        #   ((X 10) (Y 20)) - variables with initializers
        # Note: PROG/BIND bindings shadow outer variables - always create new slots
        bindings_list = operands[bindings_index]
        saved_locals = {}  # Save old mappings for shadowed variables
        prog_bound_vars = set()  # Track variables bound in this PROG
        prog_side_effect_vars = set()  # Variables with side-effect initializers
        if isinstance(bindings_list, list):
            for binding in bindings_list:
                if isinstance(binding, AtomNode):
                    # Just a variable name, initialize to 0
                    var_name = binding.value
                    # Save old mapping if it exists (for shadowing)
                    if var_name in self.locals:
                        saved_locals[var_name] = self.locals[var_name]
                    # Always create new local slot for PROG bindings
                    var_num = len(self.locals) + 1
                    self.locals[var_name] = var_num
                    prog_bound_vars.add(var_name)  # Track for unused warning
                    # Track max local slot for routine header
                    if hasattr(self, 'max_local_slot'):
                        self.max_local_slot = max(self.max_local_slot, var_num)
                    # Initialize to 0
                    code.append(0x0D)  # STORE
                    code.append(var_num & 0xFF)
                    code.append(0x00)  # Initial value 0
                elif isinstance(binding, list) and len(binding) >= 1:
                    # (VAR) or (VAR VALUE)
                    if isinstance(binding[0], AtomNode):
                        var_name = binding[0].value
                        # Save old mapping if it exists (for shadowing)
                        if var_name in self.locals:
                            saved_locals[var_name] = self.locals[var_name]
                        # Always create new local slot for PROG bindings
                        var_num = len(self.locals) + 1
                        self.locals[var_name] = var_num
                        prog_bound_vars.add(var_name)  # Track for unused warning
                        # Track max local slot for routine header
                        if hasattr(self, 'max_local_slot'):
                            self.max_local_slot = max(self.max_local_slot, var_num)
                        # Initialize with value if provided, else 0
                        if len(binding) >= 2:
                            init_value = self.get_operand_value(binding[1])
                            # Check for side-effect initializer (FormNode = routine call)
                            if isinstance(binding[1], FormNode):
                                prog_side_effect_vars.add(var_name)
                            if isinstance(init_value, int):
                                if 0 <= init_value <= 255:
                                    # Small constant - use 0x0D (small, small)
                                    code.append(0x0D)  # STORE
                                    code.append(var_num & 0xFF)
                                    code.append(init_value & 0xFF)
                                else:
                                    # Large constant - use 2OP variable form with type bytes
                                    # 0xCD = 2OP variable form (0xC0 + 0x0D), opcode STORE
                                    # Type byte 0x4F = 01 00 11 11 (small, large, omit, omit)
                                    code.append(0xCD)  # 2OP variable form STORE
                                    code.append(0x4F)  # Type: small const, large const
                                    code.append(var_num & 0xFF)
                                    code.append((init_value >> 8) & 0xFF)  # High byte
                                    code.append(init_value & 0xFF)  # Low byte
                            else:
                                # Generate code to compute and store the init value
                                init_code = self.generate_statement(binding[1])
                                if init_code:
                                    code.extend(init_code)
                                    # Store stack top (variable 0) to local variable
                                    # Use 0x4D = 0x0D | 0x40 for variable operand form
                                    code.append(0x4D)  # STORE from var (2OP:13, small/var)
                                    code.append(var_num & 0xFF)
                                    code.append(0x00)  # Stack (variable 0)
                        else:
                            code.append(0x0D)  # STORE
                            code.append(var_num & 0xFF)
                            code.append(0x00)  # Initial value 0

        # Push block context onto block_stack (for RETURN support)
        # Use stack (variable 0) to store the block result
        block_idx = len(self.block_stack)  # Index this block will have
        block_ctx = {
            'code_buffer': code,
            'return_placeholders': [],  # Positions of RETURN jumps to patch
            'block_type': 'PROG',
            'result_var': 0,  # Stack (SP) - result is pushed onto stack
            'activation_name': activation_name,  # Named activation for targeted RETURN
            'block_idx': block_idx,  # Index for targeted return patching
        }
        self.block_stack.append(block_ctx)

        # PROG also serves as a loop context for AGAIN
        # loop_start is at the beginning of the PROG body (after bindings)
        loop_start = len(code)
        loop_ctx = {
            'loop_start': loop_start,
            'loop_type': 'PROG',
            'again_placeholders': [],
            'activation_name': activation_name,  # For AGAIN with activation
        }
        if not hasattr(self, 'loop_stack'):
            self.loop_stack = []
        self.loop_stack.append(loop_ctx)

        try:
            # Generate code for each statement in sequence
            for i in range(body_start, len(operands)):
                stmt = operands[i]
                stmt_code = self.generate_statement(stmt)
                if stmt_code:
                    code.extend(stmt_code)

            # Exit point is at the end of the block
            exit_point = len(code)

            # Patch all RETURN placeholders (0x8C 0xFF 0xBB -> jump to exit_point)
            # Use pattern scanning instead of position tracking, since RETURN may be
            # inside nested structures (like COND) that generate code in temp buffers
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                    # Found RETURN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # Offset = Target - PC + 2 = exit_point - (i + 3) + 2
                    return_offset = exit_point - (i + 1)
                    if return_offset < 0:
                        return_offset_unsigned = (1 << 16) + return_offset
                    else:
                        return_offset_unsigned = return_offset
                    code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                    code[i+2] = return_offset_unsigned & 0xFF
                i += 1

            # Patch all TARGETED RETURN placeholders (0x8C 0xFE <block_idx>)
            # These are from RETURN with activation targeting this specific block
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFE and code[i+2] == block_idx:
                    # Found targeted RETURN placeholder for this block
                    return_offset = exit_point - (i + 1)
                    if return_offset < 0:
                        return_offset_unsigned = (1 << 16) + return_offset
                    else:
                        return_offset_unsigned = return_offset
                    code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                    code[i+2] = return_offset_unsigned & 0xFF
                i += 1

            # Patch all AGAIN placeholders (0x8C 0xFF 0xAA -> jump to loop_start)
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xAA:
                    # Found AGAIN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # Offset = Target - PC + 2 = loop_start - (i + 3) + 2
                    again_offset = loop_start - (i + 1)
                    if again_offset < 0:
                        again_offset_unsigned = (1 << 16) + again_offset
                    else:
                        again_offset_unsigned = again_offset
                    code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                    code[i+2] = again_offset_unsigned & 0xFF
                i += 1

        finally:
            # Check for unused PROG locals (ZIL0210)
            if hasattr(self, 'used_locals') and self.compiler is not None:
                for var_name in prog_bound_vars:
                    if (var_name not in self.used_locals and
                            var_name not in prog_side_effect_vars):
                        self.compiler.warn("ZIL0210", f"local variable '{var_name}' is never used")
            # Pop loop context
            if hasattr(self, 'loop_stack') and self.loop_stack:
                self.loop_stack.pop()
            # Pop block context
            self.block_stack.pop()
            # Restore shadowed locals
            for var_name, var_num in saved_locals.items():
                self.locals[var_name] = var_num

        return bytes(code)

    def gen_bind(self, operands: List[ASTNode]) -> bytes:
        """Generate BIND (local variable binding block).

        <BIND bindings body...> creates local variables and executes body.
        Similar to PROG but focuses on local variable scope.
        RETURN inside BIND exits the block (not the routine) and provides
        the block's result value.

        Example: <BIND ((X 10) (Y 20)) <TELL N <+ .X .Y>>>

        Args:
            operands[0]: List of bindings (varname value) pairs
            operands[1:]: Statements to execute with bindings

        Returns:
            bytes: Z-machine code for binding and execution
        """
        code = bytearray()

        # First operand should be a list node with bindings
        if len(operands) < 2:
            return b''

        # Check for bindings in GO routine (not allowed in V1-V5)
        if self._current_routine == "GO" and self.version < 6:
            bindings = operands[0]
            if isinstance(bindings, list) and len(bindings) > 0:
                raise ValueError(
                    f"GO routine cannot have PROG/BIND with local variables in V{self.version}. "
                    f"Use a separate routine and call it from GO, or use V6."
                )

        # Process bindings from operands[0]
        # Bindings can be:
        #   (X) - just variable name, initialize to 0
        #   (X Y) - multiple variable names
        #   ((X 10) (Y 20)) - variables with initializers
        # Note: BIND bindings shadow outer variables - always create new slots
        bindings_list = operands[0]
        saved_locals = {}  # Save old mappings for shadowed variables
        bind_bound_vars = set()  # Track variables bound in this BIND
        bind_side_effect_vars = set()  # Variables with side-effect initializers
        if isinstance(bindings_list, list):
            for binding in bindings_list:
                if isinstance(binding, AtomNode):
                    # Just a variable name, initialize to 0
                    var_name = binding.value
                    # Save old mapping if it exists (for shadowing)
                    if var_name in self.locals:
                        saved_locals[var_name] = self.locals[var_name]
                    # Always create new local slot for BIND bindings
                    var_num = len(self.locals) + 1
                    self.locals[var_name] = var_num
                    bind_bound_vars.add(var_name)  # Track for unused warning
                    # Track max local slot for routine header
                    if hasattr(self, 'max_local_slot'):
                        self.max_local_slot = max(self.max_local_slot, var_num)
                    # Initialize to 0
                    code.append(0x0D)  # STORE
                    code.append(var_num & 0xFF)
                    code.append(0x00)  # Initial value 0
                elif isinstance(binding, list) and len(binding) >= 1:
                    # (VAR) or (VAR VALUE)
                    if isinstance(binding[0], AtomNode):
                        var_name = binding[0].value
                        # Save old mapping if it exists (for shadowing)
                        if var_name in self.locals:
                            saved_locals[var_name] = self.locals[var_name]
                        # Always create new local slot for BIND bindings
                        var_num = len(self.locals) + 1
                        self.locals[var_name] = var_num
                        bind_bound_vars.add(var_name)  # Track for unused warning
                        # Track max local slot for routine header
                        if hasattr(self, 'max_local_slot'):
                            self.max_local_slot = max(self.max_local_slot, var_num)
                        # Initialize with value if provided, else 0
                        if len(binding) >= 2:
                            init_value = self.get_operand_value(binding[1])
                            # Check for side-effect initializer (FormNode = routine call)
                            if isinstance(binding[1], FormNode):
                                bind_side_effect_vars.add(var_name)
                            if isinstance(init_value, int):
                                if 0 <= init_value <= 255:
                                    # Small constant - use 0x0D (small, small)
                                    code.append(0x0D)  # STORE
                                    code.append(var_num & 0xFF)
                                    code.append(init_value & 0xFF)
                                else:
                                    # Large constant - use 2OP variable form with type bytes
                                    # 0xCD = 2OP variable form (0xC0 + 0x0D), opcode STORE
                                    # Type byte 0x4F = 01 00 11 11 (small, large, omit, omit)
                                    code.append(0xCD)  # 2OP variable form STORE
                                    code.append(0x4F)  # Type: small const, large const
                                    code.append(var_num & 0xFF)
                                    code.append((init_value >> 8) & 0xFF)  # High byte
                                    code.append(init_value & 0xFF)  # Low byte
                            else:
                                # Generate code to compute and store the init value
                                init_code = self.generate_statement(binding[1])
                                if init_code:
                                    code.extend(init_code)
                                    # Store stack top (variable 0) to local variable
                                    # Use 0x4D = 0x0D | 0x40 for variable operand form
                                    code.append(0x4D)  # STORE from var (2OP:13, small/var)
                                    code.append(var_num & 0xFF)
                                    code.append(0x00)  # Stack (variable 0)
                        else:
                            code.append(0x0D)  # STORE
                            code.append(var_num & 0xFF)
                            code.append(0x00)  # Initial value 0

        # Push block context onto block_stack (for RETURN support)
        # Use stack (variable 0) to store the block result
        block_ctx = {
            'code_buffer': code,
            'return_placeholders': [],  # Positions of RETURN jumps to patch
            'block_type': 'BIND',
            'result_var': 0,  # Stack (SP) - result is pushed onto stack
        }
        self.block_stack.append(block_ctx)

        # BIND also serves as a loop context for AGAIN
        # loop_start is at the beginning of the BIND body (after bindings)
        loop_start = len(code)
        loop_ctx = {
            'loop_start': loop_start,
            'loop_type': 'BIND',
            'again_placeholders': [],
        }
        if not hasattr(self, 'loop_stack'):
            self.loop_stack = []
        self.loop_stack.append(loop_ctx)

        try:
            # Generate code for each statement in sequence
            for i in range(1, len(operands)):
                stmt = operands[i]
                stmt_code = self.generate_statement(stmt)
                if stmt_code:
                    code.extend(stmt_code)

            # Exit point is at the end of the block
            exit_point = len(code)

            # Patch all RETURN placeholders (0x8C 0xFF 0xBB -> jump to exit_point)
            # Use pattern scanning instead of position tracking, since RETURN may be
            # inside nested structures (like COND) that generate code in temp buffers
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                    # Found RETURN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # Offset = Target - PC + 2 = exit_point - (i + 3) + 2
                    return_offset = exit_point - (i + 1)
                    if return_offset < 0:
                        return_offset_unsigned = (1 << 16) + return_offset
                    else:
                        return_offset_unsigned = return_offset
                    code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                    code[i+2] = return_offset_unsigned & 0xFF
                i += 1

            # Patch all AGAIN placeholders (0x8C 0xFF 0xAA -> jump to loop_start)
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xAA:
                    # Found AGAIN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # Offset = Target - PC + 2 = loop_start - (i + 3) + 2
                    again_offset = loop_start - (i + 1)
                    if again_offset < 0:
                        again_offset_unsigned = (1 << 16) + again_offset
                    else:
                        again_offset_unsigned = again_offset
                    code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                    code[i+2] = again_offset_unsigned & 0xFF
                i += 1

        finally:
            # Check for unused BIND locals (ZIL0210)
            if hasattr(self, 'used_locals') and self.compiler is not None:
                for var_name in bind_bound_vars:
                    if (var_name not in self.used_locals and
                            var_name not in bind_side_effect_vars):
                        self.compiler.warn("ZIL0210", f"local variable '{var_name}' is never used")
            # Pop loop context
            if hasattr(self, 'loop_stack') and self.loop_stack:
                self.loop_stack.pop()
            # Pop block context
            self.block_stack.pop()
            # Restore shadowed locals
            for var_name, var_num in saved_locals.items():
                self.locals[var_name] = var_num

        return bytes(code)

    def gen_do(self, operands: List[ASTNode]) -> bytes:
        """Generate DO loop.

        <DO (var start end [step]) body...> creates a counted loop.

        The loop:
        1. Initialize var = start
        2. Check termination: if counting up and var > end, exit; if counting down and var < end, exit
        3. Execute body
        4. Increment/decrement var by step
        5. Go back to step 2

        Args:
            operands[0]: Loop spec - a FormNode containing (var start end [step])
            operands[1:]: Body statements

        Returns:
            bytes: Z-machine code for the loop
        """
        if len(operands) < 1:
            raise ValueError("DO requires at least a loop specification")

        code = bytearray()

        # Parse loop specification: (var start end [step])
        loop_spec = operands[0]
        if isinstance(loop_spec, FormNode):
            spec_parts = [loop_spec.operator] + loop_spec.operands if loop_spec.operator else loop_spec.operands
        elif isinstance(loop_spec, list):
            # Parser returns loop spec as a raw list
            spec_parts = loop_spec
        else:
            raise ValueError("DO loop specification must be a list (var start end [step])")

        if len(spec_parts) < 3:
            raise ValueError("DO loop specification requires at least (var start end)")

        var_node = spec_parts[0]
        start_node = spec_parts[1]
        end_node = spec_parts[2]
        step_node = spec_parts[3] if len(spec_parts) > 3 else None

        # Get variable name
        if isinstance(var_node, AtomNode):
            var_name = var_node.value
        else:
            raise ValueError("DO loop variable must be an atom")

        # Save current local if it exists (for shadowing)
        saved_local = self.locals.get(var_name)

        # Allocate a local slot for the loop variable
        if var_name in self.locals:
            var_num = self.locals[var_name]
        else:
            # Create new local for loop variable
            var_num = len(self.locals) + 1
            self.locals[var_name] = var_num
            if hasattr(self, 'max_local_slot'):
                self.max_local_slot = max(self.max_local_slot, var_num)

        # Initialize loop variable to start value
        if isinstance(start_node, NumberNode):
            start_val = start_node.value
            if 0 <= start_val <= 255:
                code.append(0x0D)  # STORE small, small
                code.append(var_num & 0xFF)
                code.append(start_val & 0xFF)
            else:
                code.append(0xCD)  # 2OP variable form STORE
                code.append(0x4F)  # Type: small const, large const
                code.append(var_num & 0xFF)
                code.append((start_val >> 8) & 0xFF)
                code.append(start_val & 0xFF)
        else:
            # Evaluate expression for start value
            start_code = self.generate_statement(start_node)
            code.extend(start_code)
            code.append(0xE9)  # PULL
            code.append(0x7F)  # Type: small constant
            code.append(var_num & 0xFF)

        # Push start value as default return value
        # When DO exits normally, it returns the initial value of the loop variable
        if isinstance(start_node, NumberNode):
            start_val = start_node.value
            if 0 <= start_val <= 255:
                # PUSH small constant
                code.append(0xE8)  # PUSH (VAR form 0xE0 + opcode 0x08)
                code.append(0x7F)  # Type byte: small constant (01), omit, omit, omit
                code.append(start_val & 0xFF)
            else:
                # PUSH large constant
                code.append(0xE8)  # PUSH
                code.append(0x3F)  # Type: large constant (00), omit, omit, omit
                code.append((start_val >> 8) & 0xFF)
                code.append(start_val & 0xFF)
        else:
            # Push the loop variable value (which now holds start)
            code.append(0xE8)  # PUSH
            code.append(0xBF)  # Type: variable (10), omit, omit, omit
            code.append(var_num & 0xFF)

        # Determine if counting up or down
        # If step is negative, count down. Otherwise, if start > end, count down.
        counting_up = True
        step_val = 1
        if step_node:
            if isinstance(step_node, NumberNode):
                step_val = step_node.value
                if step_val < 0:
                    counting_up = False
                    step_val = -step_val
            # If step is an expression, we assume counting up with step 1 for now
        else:
            # No step provided - determine direction from start/end
            if isinstance(start_node, NumberNode) and isinstance(end_node, NumberNode):
                if start_node.value > end_node.value:
                    counting_up = False

        # Loop start position (for AGAIN/continue)
        loop_start = len(code)

        # Check termination condition
        # If counting up: var > end -> exit
        # If counting down: var < end -> exit
        # Use JG (jump if greater) or JL (jump if less)
        if counting_up:
            # JG var end ?exit (jump to exit if var > end)
            # 2OP opcode 0x03 = JG, branch on true
            # Long form encoding: 0 a b OOOOO where a=first type, b=second type
            # a=1 for variable, b=0 for small constant -> 0x43
            if isinstance(end_node, NumberNode):
                end_val = end_node.value
                if 0 <= end_val <= 255:
                    code.append(0x43)  # JG var, small (0100 0011)
                    code.append(var_num & 0xFF)
                    code.append(end_val & 0xFF)
                else:
                    code.append(0xC3)  # JG 2OP variable form
                    code.append(0x6F)  # var, large (01 10 11 11)
                    code.append(var_num & 0xFF)
                    code.append((end_val >> 8) & 0xFF)
                    code.append(end_val & 0xFF)
            else:
                # End is a form expression - treat as predicate
                # Evaluate and exit if result is truthy (non-zero)
                end_code = self.generate_statement(end_node)
                code.extend(end_code)
                # JZ stack - branch if zero (continue) or not zero (exit)
                code.append(0xA0)  # JZ 1OP short form with variable type
                code.append(0x00)  # Stack
                # Branch with polarity=false to exit when NOT zero
                exit_branch_pos = len(code)
                code.append(0x40)  # Short branch on false, placeholder offset
                # Note: We handle form-based ends differently - no long branch placeholder needed
                # Skip the normal termination branch setup below

                # Push block context for RETURN support
                block_ctx = {
                    'code_buffer': code,
                    'return_placeholders': [],
                    'block_type': 'DO',
                    'result_var': 0,
                }
                self.block_stack.append(block_ctx)

                # Push loop context for AGAIN support
                loop_ctx = {
                    'loop_start': loop_start,
                    'exit_placeholders': [exit_branch_pos],
                    'loop_type': 'DO',
                }
                if not hasattr(self, 'loop_stack'):
                    self.loop_stack = []
                self.loop_stack.append(loop_ctx)

                try:
                    # Generate body code
                    for i in range(1, len(operands)):
                        stmt = operands[i]
                        stmt_code = self.generate_statement(stmt)
                        if stmt_code:
                            code.extend(stmt_code)

                    # Increment loop variable (default step of 1 for form-based ends)
                    if step_node:
                        if isinstance(step_node, NumberNode):
                            step_val = step_node.value
                            if step_val > 0:
                                if step_val == 1:
                                    code.append(0x95)  # INC var
                                    code.append(var_num & 0xFF)
                                else:
                                    code.append(0x54)  # ADD var, small
                                    code.append(var_num & 0xFF)
                                    code.append(step_val & 0xFF)
                                    code.append(var_num & 0xFF)
                            else:
                                abs_step = abs(step_val)
                                if abs_step == 1:
                                    code.append(0x96)  # DEC var
                                    code.append(var_num & 0xFF)
                                else:
                                    code.append(0x55)  # SUB var, small
                                    code.append(var_num & 0xFF)
                                    code.append(abs_step & 0xFF)
                                    code.append(var_num & 0xFF)
                        else:
                            # Variable step
                            step_code = self.generate_statement(step_node)
                            code.extend(step_code)
                            code.append(0xE9)  # PULL to var
                            code.append(0x7F)
                            code.append(var_num & 0xFF)
                    else:
                        # Default: increment by 1
                        code.append(0x95)  # INC var
                        code.append(var_num & 0xFF)

                    # Jump back to loop start
                    jump_pos = len(code)
                    code.append(0x8C)  # JUMP
                    jump_offset = loop_start - (jump_pos + 3) + 2
                    if jump_offset < 0:
                        jump_offset_unsigned = (1 << 16) + jump_offset
                    else:
                        jump_offset_unsigned = jump_offset
                    code.append((jump_offset_unsigned >> 8) & 0xFF)
                    code.append(jump_offset_unsigned & 0xFF)

                    # Patch exit branch
                    # Z-machine branch: target = address_after_branch + offset - 2
                    # So offset = target - branch_pos + 1 for single-byte short branch
                    exit_point = len(code)
                    short_offset = exit_point - exit_branch_pos + 1
                    if 2 <= short_offset <= 63:
                        # Short branch on false (polarity=0, short=1)
                        code[exit_branch_pos] = 0x40 | (short_offset & 0x3F)
                    else:
                        raise ValueError(f"DO loop body too large for short branch: {short_offset}")

                    # Patch RETURN placeholders
                    i = 0
                    while i < len(code) - 2:
                        if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                            return_offset = exit_point - (i + 1)
                            if return_offset < 0:
                                return_offset_unsigned = (1 << 16) + return_offset
                            else:
                                return_offset_unsigned = return_offset
                            code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                            code[i+2] = return_offset_unsigned & 0xFF
                        i += 1
                finally:
                    if self.block_stack:
                        self.block_stack.pop()
                    if hasattr(self, 'loop_stack') and self.loop_stack:
                        self.loop_stack.pop()
                    if saved_local is not None:
                        self.locals[var_name] = saved_local
                    elif var_name in self.locals and saved_local is None:
                        del self.locals[var_name]

                return bytes(code)
        else:
            # JL var end ?exit (jump to exit if var < end)
            # 2OP opcode 0x02 = JL, branch on true
            if isinstance(end_node, NumberNode):
                end_val = end_node.value
                if 0 <= end_val <= 255:
                    code.append(0x42)  # JL var, small (0100 0010)
                    code.append(var_num & 0xFF)
                    code.append(end_val & 0xFF)
                else:
                    code.append(0xC2)  # JL 2OP variable form
                    code.append(0x6F)  # var, large
                    code.append(var_num & 0xFF)
                    code.append((end_val >> 8) & 0xFF)
                    code.append(end_val & 0xFF)
            else:
                # End is a form expression - treat as predicate
                # Evaluate and exit if result is truthy (non-zero)
                end_code = self.generate_statement(end_node)
                code.extend(end_code)
                # JZ stack - branch if zero (continue) or not zero (exit)
                code.append(0xA0)  # JZ 1OP short form with variable type
                code.append(0x00)  # Stack
                # Branch with polarity=false to exit when NOT zero
                exit_branch_pos = len(code)
                code.append(0x40)  # Short branch on false, placeholder offset

                # Push block context for RETURN support
                block_ctx = {
                    'code_buffer': code,
                    'return_placeholders': [],
                    'block_type': 'DO',
                    'result_var': 0,
                }
                self.block_stack.append(block_ctx)

                # Push loop context for AGAIN support
                loop_ctx = {
                    'loop_start': loop_start,
                    'exit_placeholders': [exit_branch_pos],
                    'loop_type': 'DO',
                }
                if not hasattr(self, 'loop_stack'):
                    self.loop_stack = []
                self.loop_stack.append(loop_ctx)

                try:
                    # Generate body code
                    for i in range(1, len(operands)):
                        stmt = operands[i]
                        stmt_code = self.generate_statement(stmt)
                        if stmt_code:
                            code.extend(stmt_code)

                    # Decrement loop variable (counting down with form-based end)
                    if step_node and isinstance(step_node, NumberNode):
                        step_val = abs(step_node.value)
                        if step_val == 1:
                            code.append(0x96)  # DEC var
                            code.append(var_num & 0xFF)
                        else:
                            code.append(0x55)  # SUB var, small
                            code.append(var_num & 0xFF)
                            code.append(step_val & 0xFF)
                            code.append(var_num & 0xFF)
                    else:
                        # Default: decrement by 1
                        code.append(0x96)  # DEC var
                        code.append(var_num & 0xFF)

                    # Jump back to loop start
                    jump_pos = len(code)
                    code.append(0x8C)  # JUMP
                    jump_offset = loop_start - (jump_pos + 3) + 2
                    if jump_offset < 0:
                        jump_offset_unsigned = (1 << 16) + jump_offset
                    else:
                        jump_offset_unsigned = jump_offset
                    code.append((jump_offset_unsigned >> 8) & 0xFF)
                    code.append(jump_offset_unsigned & 0xFF)

                    # Patch exit branch
                    # Z-machine branch: target = address_after_branch + offset - 2
                    # So offset = target - branch_pos + 1 for single-byte short branch
                    exit_point = len(code)
                    short_offset = exit_point - exit_branch_pos + 1
                    if 2 <= short_offset <= 63:
                        code[exit_branch_pos] = 0x40 | (short_offset & 0x3F)
                    else:
                        raise ValueError(f"DO loop body too large for short branch: {short_offset}")

                    # Patch RETURN placeholders
                    i = 0
                    while i < len(code) - 2:
                        if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                            return_offset = exit_point - (i + 1)
                            if return_offset < 0:
                                return_offset_unsigned = (1 << 16) + return_offset
                            else:
                                return_offset_unsigned = return_offset
                            code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                            code[i+2] = return_offset_unsigned & 0xFF
                        i += 1
                finally:
                    if self.block_stack:
                        self.block_stack.pop()
                    if hasattr(self, 'loop_stack') and self.loop_stack:
                        self.loop_stack.pop()
                    if saved_local is not None:
                        self.locals[var_name] = saved_local
                    elif var_name in self.locals and saved_local is None:
                        del self.locals[var_name]

                return bytes(code)

        # Branch offset placeholder (will be patched)
        exit_branch_pos = len(code)
        code.append(0x80)  # Branch on true, 1-byte offset placeholder
        code.append(0x00)  # Placeholder

        # Push block context onto block_stack (for RETURN support)
        # RETURN inside DO loop should exit the loop and provide a result
        block_ctx = {
            'code_buffer': code,
            'return_placeholders': [],
            'block_type': 'DO',
            'result_var': 0,  # Stack (SP) - result is pushed onto stack
        }
        self.block_stack.append(block_ctx)

        # Push loop context for AGAIN support
        loop_ctx = {
            'loop_start': loop_start,
            'exit_placeholders': [exit_branch_pos],
            'loop_type': 'DO',
        }
        if not hasattr(self, 'loop_stack'):
            self.loop_stack = []
        self.loop_stack.append(loop_ctx)

        # Check for END clause: if operands[1] is a list (not a FormNode), it's the END clause
        # The END clause is executed when the loop terminates normally (not via RETURN)
        end_clause = None
        body_start_idx = 1
        if len(operands) > 1 and isinstance(operands[1], list):
            end_clause = operands[1]
            body_start_idx = 2

        # Check for misplaced END clauses in the body
        # An END clause appearing after body statements is an error
        for i in range(body_start_idx, len(operands)):
            stmt = operands[i]
            if isinstance(stmt, list):
                # Check if this list looks like an END clause
                if (len(stmt) > 0 and
                        isinstance(stmt[0], AtomNode) and
                        stmt[0].value.upper() == 'END'):
                    raise ValueError(
                        "DO END clause must appear immediately after the loop specification, "
                        "not after body statements"
                    )

        try:
            # Generate body code
            for i in range(body_start_idx, len(operands)):
                stmt = operands[i]
                stmt_code = self.generate_statement(stmt)
                if stmt_code:
                    code.extend(stmt_code)

            # Increment/decrement loop variable
            if step_node and not isinstance(step_node, NumberNode):
                # Variable step - need to add/subtract at runtime
                # Check if it's a local variable reference
                step_var_name = None
                if isinstance(step_node, LocalVarNode):
                    # Direct local variable node (parsed .N becomes LocalVarNode with name='N')
                    step_var_name = step_node.name
                elif isinstance(step_node, FormNode) and isinstance(step_node.operator, AtomNode):
                    if step_node.operator.value == 'LVAL' and len(step_node.operands) == 1:
                        # <LVAL N> form - local variable reference
                        name_node = step_node.operands[0]
                        if isinstance(name_node, AtomNode):
                            step_var_name = name_node.value
                elif isinstance(step_node, AtomNode) and step_node.value.startswith('.'):
                    # Old-style .N reference (if parser didn't convert)
                    step_var_name = step_node.value[1:]
                elif isinstance(step_node, AtomNode) and step_node.value in self.locals:
                    # Direct local variable name
                    step_var_name = step_node.value

                if step_var_name and step_var_name in self.locals:
                    step_var_num = self.locals[step_var_name]
                    if counting_up:
                        # ADD var, step_var -> var
                        code.append(0x74)  # ADD var, var (0111 0100)
                        code.append(var_num & 0xFF)
                        code.append(step_var_num & 0xFF)
                        code.append(var_num & 0xFF)
                    else:
                        # SUB var, step_var -> var
                        code.append(0x75)  # SUB var, var (0111 0101)
                        code.append(var_num & 0xFF)
                        code.append(step_var_num & 0xFF)
                        code.append(var_num & 0xFF)
                else:
                    # Complex expression - evaluate and assign (not add)
                    # When step is a complex expression, I = step_expr (assignment, not increment)
                    step_code = self.generate_statement(step_node)
                    code.extend(step_code)
                    # PULL stack value into variable (store stack to var)
                    code.append(0xE9)  # PULL (VAR form)
                    code.append(0x7F)  # Type: small constant (variable number)
                    code.append(var_num & 0xFF)
            elif counting_up:
                if step_val == 1:
                    # INC var
                    code.append(0x95)  # 1OP INC short form with small constant type
                    code.append(var_num & 0xFF)
                else:
                    # ADD var step -> var
                    code.append(0x54)  # ADD var, small
                    code.append(var_num & 0xFF)
                    code.append(step_val & 0xFF)
                    code.append(var_num & 0xFF)  # Store result back to var
            else:
                if step_val == 1:
                    # DEC var
                    code.append(0x96)  # 1OP DEC short form with small constant type
                    code.append(var_num & 0xFF)
                else:
                    # SUB var step -> var
                    code.append(0x55)  # SUB var, small
                    code.append(var_num & 0xFF)
                    code.append(step_val & 0xFF)
                    code.append(var_num & 0xFF)  # Store result back to var

            # Jump back to loop start
            # Z-machine JUMP: target = PC + offset - 2
            # where PC is the address after the JUMP instruction
            # So: offset = target - PC + 2 = loop_start - (jump_pos + 3) + 2
            jump_pos = len(code)
            code.append(0x8C)  # JUMP
            # PC after JUMP = jump_pos + 3 (opcode + 2 offset bytes)
            jump_offset = loop_start - (jump_pos + 3) + 2
            if jump_offset < 0:
                jump_offset_unsigned = (1 << 16) + jump_offset
            else:
                jump_offset_unsigned = jump_offset
            code.append((jump_offset_unsigned >> 8) & 0xFF)
            code.append(jump_offset_unsigned & 0xFF)

            # Exit point - patch branch offset
            exit_point = len(code)
            # For short branch (1 byte offset):
            # After deletion, PC after branch = exit_branch_pos + 1
            # target = exit_point - 1 (since we'll delete one placeholder byte)
            # offset = target - PC + 2 = (exit_point - 1) - (exit_branch_pos + 1) + 2
            #        = exit_point - exit_branch_pos
            short_branch_offset = exit_point - exit_branch_pos
            if 0 <= short_branch_offset <= 63:
                # Short branch: bit 7=polarity, bit 6=1 (short), bits 5-0=offset
                # 0xC0 = 1100 0000 (branch on true, short form)
                code[exit_branch_pos] = 0xC0 | (short_branch_offset & 0x3F)
                # Remove the extra placeholder byte
                del code[exit_branch_pos + 1]
                # Update exit_point since we deleted a byte
                exit_point -= 1
                # Fix the JUMP offset - deleting a byte before it shifts everything
                # The JUMP is at position (jump_pos - 1) after deletion
                # Its offset bytes are at (jump_pos - 1) + 1 and (jump_pos - 1) + 2
                # The target is now 1 byte closer, so increment offset by 1
                jump_offset_pos = jump_pos  # After deletion, offset bytes are here
                old_offset_hi = code[jump_offset_pos]
                old_offset_lo = code[jump_offset_pos + 1]
                old_offset = (old_offset_hi << 8) | old_offset_lo
                if old_offset >= 0x8000:
                    old_offset = old_offset - 0x10000
                new_offset = old_offset + 1  # Target is 1 byte closer
                if new_offset < 0:
                    new_offset_unsigned = (1 << 16) + new_offset
                else:
                    new_offset_unsigned = new_offset
                code[jump_offset_pos] = (new_offset_unsigned >> 8) & 0xFF
                code[jump_offset_pos + 1] = new_offset_unsigned & 0xFF
            else:
                # Long branch: bit 7=polarity, bit 6=0 (long), bits 13-8 in bits 5-0, bits 7-0 in byte 2
                # Recalculate offset for 2-byte branch
                branch_offset = exit_point - (exit_branch_pos + 2)
                if branch_offset < 0:
                    branch_offset_unsigned = (1 << 14) + branch_offset  # 14-bit signed
                else:
                    branch_offset_unsigned = branch_offset
                code[exit_branch_pos] = 0x80 | ((branch_offset_unsigned >> 8) & 0x3F)
                code[exit_branch_pos + 1] = branch_offset_unsigned & 0xFF

            # Generate END clause if present
            # END clause is executed when loop terminates normally, not via RETURN
            if end_clause:
                # Generate END clause statements
                for stmt in end_clause:
                    stmt_code = self.generate_statement(stmt)
                    if stmt_code:
                        code.extend(stmt_code)

            # Return point is after END clause (where RETURN jumps to)
            return_point = len(code)

            # Patch all RETURN placeholders (0x8C 0xFF 0xBB -> jump to return_point)
            # RETURN skips the END clause
            # Use pattern scanning since RETURN may be inside nested structures
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                    # Found RETURN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # PC after JUMP = i + 3, so Offset = Target - (i + 3) + 2 = Target - i - 1
                    return_offset = return_point - (i + 1)
                    if return_offset < 0:
                        return_offset_unsigned = (1 << 16) + return_offset
                    else:
                        return_offset_unsigned = return_offset
                    code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                    code[i+2] = return_offset_unsigned & 0xFF
                i += 1

        finally:
            # Pop block context
            if self.block_stack:
                self.block_stack.pop()
            # Pop loop context
            if hasattr(self, 'loop_stack') and self.loop_stack:
                self.loop_stack.pop()
            # Restore shadowed local
            if saved_local is not None:
                self.locals[var_name] = saved_local
            elif var_name in self.locals and saved_local is None:
                del self.locals[var_name]

        return bytes(code)

    def gen_map_contents(self, operands: List[ASTNode]) -> bytes:
        """Generate MAP-CONTENTS loop.

        <MAP-CONTENTS (var container [next-var]) [end-clause] body...>
        iterates over all objects contained in the container object.

        The loop:
        1. Get first child of container -> var
        2. If var is 0 (no children), skip to end/exit
        3. Save next sibling to next-var (if provided) or temp
        4. Execute body
        5. Set var = saved next sibling
        6. If var != 0, go back to step 3
        7. Execute end-clause if present

        Args:
            operands[0]: Loop spec - (var container [next-var])
            operands[1]: End clause (if it's a list) or first body statement
            operands[2+]: Body statements

        Returns:
            bytes: Z-machine code for the loop
        """
        if len(operands) < 1:
            raise ValueError("MAP-CONTENTS requires at least a loop specification")

        code = bytearray()

        # Parse loop specification: (var container [next-var])
        loop_spec = operands[0]
        if isinstance(loop_spec, FormNode):
            spec_parts = [loop_spec.operator] + loop_spec.operands if loop_spec.operator else loop_spec.operands
        elif isinstance(loop_spec, list):
            spec_parts = loop_spec
        else:
            raise ValueError("MAP-CONTENTS loop specification must be a list")

        if len(spec_parts) < 2:
            raise ValueError("MAP-CONTENTS requires at least (var container)")

        # Format: (var [next-var] container) - container is always LAST
        var_node = spec_parts[0]
        if len(spec_parts) == 3:
            next_var_node = spec_parts[1]
            container_node = spec_parts[2]
        else:
            next_var_node = None
            container_node = spec_parts[1]

        # Get variable name for iterator
        if isinstance(var_node, AtomNode):
            var_name = var_node.value
        else:
            raise ValueError("MAP-CONTENTS variable must be an atom")

        # Save current local if it exists (for shadowing)
        saved_local = self.locals.get(var_name)

        # Allocate local for iterator variable
        if var_name in self.locals:
            var_num = self.locals[var_name]
        else:
            var_num = len(self.locals) + 1
            self.locals[var_name] = var_num
            if hasattr(self, 'max_local_slot'):
                self.max_local_slot = max(self.max_local_slot, var_num)

        # Handle next-var if provided
        next_var_name = None
        next_var_num = None
        saved_next_local = None
        if next_var_node:
            if isinstance(next_var_node, AtomNode):
                next_var_name = next_var_node.value
                saved_next_local = self.locals.get(next_var_name)
                if next_var_name in self.locals:
                    next_var_num = self.locals[next_var_name]
                else:
                    next_var_num = len(self.locals) + 1
                    self.locals[next_var_name] = next_var_num
                    if hasattr(self, 'max_local_slot'):
                        self.max_local_slot = max(self.max_local_slot, next_var_num)
            else:
                raise ValueError("MAP-CONTENTS next-var must be an atom")

        # Get container object number
        container_type, container_val = self._get_operand_type_and_value(container_node)

        # Check for END clause
        end_clause = None
        body_start_idx = 1
        if len(operands) > 1 and isinstance(operands[1], list):
            end_clause = operands[1]
            body_start_idx = 2

        # GET_CHILD container -> var, branch if no child
        # GET_CHILD is opcode 0x82 (1OP short form with variable operand)
        # Actually GET_CHILD is 2OP opcode 0x12 which stores result and branches
        if container_type == 1:  # Variable
            code.append(0x52)  # GET_CHILD 2OP long form, var/small
            code.append(container_val & 0xFF)
            code.append(0x00)  # Dummy second operand (not used)
        else:  # Small constant (object number)
            code.append(0x12)  # GET_CHILD 2OP long form, small/small
            code.append(container_val & 0xFF)
            code.append(0x00)  # Dummy second operand (not used)

        # GET_CHILD takes one operand but uses 2OP encoding in some implementations
        # Actually, let me check the correct encoding...
        # GET_CHILD (2OP:18) object -> (result) ?(label)
        # The result is stored and it branches if no child

        # Let me rewrite with correct encoding
        code.clear()

        # GET_CHILD is 2OP opcode 0x12
        # It needs VAR form for store and branch: opcode + type + operand + store + branch
        # Actually simpler: use 1OP form since it takes one operand
        # GET_CHILD is actually VAR:194 in some docs, but 2OP:18 stores result

        # Use VAR form for GET_CHILD: E0 + type_byte + operand + store + branch
        # Wait, let me check the Z-machine spec more carefully
        # GET_CHILD is 2OP opcode $12 (18) - but it only takes 1 operand
        # It stores to a variable and branches

        # In V3+, GET_CHILD is 1OP with store and branch:
        # Short form: 10 tt 0010 where tt = operand type
        # For variable operand: 10 10 0010 = 0xA2
        if container_type == 1:  # Variable
            code.append(0xA2)  # GET_CHILD 1OP short form with variable operand
            code.append(container_val & 0xFF)
        else:  # Small constant
            code.append(0x92)  # GET_CHILD 1OP short form with small constant operand
            code.append(container_val & 0xFF)

        # Store result to var
        code.append(var_num & 0xFF)

        # Branch if no child (jump to end/exit)
        # Branch on false (child exists) would continue, branch on true (no child) would exit
        no_child_branch_pos = len(code)
        code.append(0x40)  # Placeholder: branch on false (polarity=0), short form

        # Loop start position (for AGAIN)
        loop_start = len(code)

        # Save next sibling before executing body (in case body moves object)
        # GET_SIBLING var -> next_var (or temp if no next_var)
        temp_var_num = next_var_num
        if temp_var_num is None:
            # Use a temp variable - allocate one more local
            temp_var_num = len(self.locals) + 1
            self.locals['_MAP_TEMP_'] = temp_var_num
            if hasattr(self, 'max_local_slot'):
                self.max_local_slot = max(self.max_local_slot, temp_var_num)

        # GET_SIBLING var -> temp_var
        # GET_SIBLING is 1OP opcode 0x01 with store
        code.append(0xA1)  # GET_SIBLING 1OP short form with variable operand
        code.append(var_num & 0xFF)
        code.append(temp_var_num & 0xFF)  # Store result
        # Branch: we don't care about the branch result here, but we need a branch byte
        # Use short branch with offset 2 (skip nothing, just continue)
        code.append(0x40)  # Branch on false, offset 0 (continue regardless)
        # Actually offset 0 = RFALSE, offset 1 = RTRUE, so we need offset 2 to skip nothing
        code[-1] = 0x42  # Branch on false, offset 2 (continue)

        # Push block context for RETURN support
        block_ctx = {
            'code_buffer': code,
            'return_placeholders': [],
            'block_type': 'MAP-CONTENTS',
            'result_var': 0,
        }
        self.block_stack.append(block_ctx)

        # Push loop context for AGAIN support
        loop_ctx = {
            'loop_start': loop_start,
            'exit_placeholders': [no_child_branch_pos],
            'loop_type': 'MAP-CONTENTS',
        }
        if not hasattr(self, 'loop_stack'):
            self.loop_stack = []
        self.loop_stack.append(loop_ctx)

        try:
            # Generate body code
            for i in range(body_start_idx, len(operands)):
                stmt = operands[i]
                stmt_code = self.generate_statement(stmt)
                if stmt_code:
                    code.extend(stmt_code)

            # Move to next sibling: var = temp_var
            # STORE var temp_var (copy temp to var)
            # First operand is variable NUMBER (small const), second is value (variable)
            code.append(0x2D)  # STORE 2OP long form, small/var
            code.append(var_num & 0xFF)  # Variable number to store into
            code.append(temp_var_num & 0xFF)  # Read value from this variable

            # Check if var != 0 (has next sibling), jump back to loop start
            # JZ var ?exit (if zero, exit loop)
            code.append(0xA0)  # JZ 1OP short form with variable
            code.append(var_num & 0xFF)
            # Branch on true (value is zero) -> exit loop
            exit_branch_pos = len(code)
            code.append(0xC0)  # Placeholder: branch on true

            # Jump back to loop start
            jump_pos = len(code)
            code.append(0x8C)  # JUMP
            jump_offset = loop_start - (jump_pos + 3) + 2
            if jump_offset < 0:
                jump_offset_unsigned = (1 << 16) + jump_offset
            else:
                jump_offset_unsigned = jump_offset
            code.append((jump_offset_unsigned >> 8) & 0xFF)
            code.append(jump_offset_unsigned & 0xFF)

            # Exit point
            exit_point = len(code)

            # Patch the "no child" branch to jump to end clause or exit
            # Z-machine branch: target = PC + offset - 2, where PC is after branch byte
            # So offset = target - branch_pos + 1 for single-byte branch
            short_offset = exit_point - no_child_branch_pos + 1
            if 2 <= short_offset <= 63:
                code[no_child_branch_pos] = 0x40 | (short_offset & 0x3F)
            else:
                # Need long branch - this is more complex
                raise ValueError(f"MAP-CONTENTS body too large for short branch: {short_offset}")

            # Patch the "zero check" exit branch
            short_offset2 = exit_point - exit_branch_pos + 1
            if 2 <= short_offset2 <= 63:
                code[exit_branch_pos] = 0xC0 | (short_offset2 & 0x3F)
            else:
                raise ValueError(f"MAP-CONTENTS body too large for short branch: {short_offset2}")

            # Generate END clause if present
            if end_clause:
                for stmt in end_clause:
                    stmt_code = self.generate_statement(stmt)
                    if stmt_code:
                        code.extend(stmt_code)

            # Return point (where RETURN jumps to)
            return_point = len(code)

            # Patch RETURN placeholders
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                    return_offset = return_point - (i + 1)
                    if return_offset < 0:
                        return_offset_unsigned = (1 << 16) + return_offset
                    else:
                        return_offset_unsigned = return_offset
                    code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                    code[i+2] = return_offset_unsigned & 0xFF
                i += 1

        finally:
            # Pop block context
            if self.block_stack:
                self.block_stack.pop()
            # Pop loop context
            if hasattr(self, 'loop_stack') and self.loop_stack:
                self.loop_stack.pop()
            # Restore shadowed locals
            if saved_local is not None:
                self.locals[var_name] = saved_local
            elif var_name in self.locals and saved_local is None:
                del self.locals[var_name]
            if next_var_name:
                if saved_next_local is not None:
                    self.locals[next_var_name] = saved_next_local
                elif next_var_name in self.locals and saved_next_local is None:
                    del self.locals[next_var_name]
            # Clean up temp variable
            if '_MAP_TEMP_' in self.locals:
                del self.locals['_MAP_TEMP_']

        return bytes(code)

    def gen_map_directions(self, operands: List[ASTNode]) -> bytes:
        """Generate MAP-DIRECTIONS loop.

        <MAP-DIRECTIONS (dir-var pt-var room) [end-clause] body...>
        iterates over all valid exits from a room.

        The loop:
        1. Initialize counter to MaxProperties + 1
        2. DEC_CHK counter < LOW-DIRECTION -> exit
        3. GETPT room, counter -> pt-var
        4. If pt-var == 0, jump to step 2 (no property)
        5. Execute body
        6. Jump to step 2
        7. Execute end-clause if present

        Args:
            operands[0]: Loop spec - (dir-var pt-var room)
            operands[1]: End clause (if it's a list starting with END) or first body statement
            operands[2+]: Body statements

        Returns:
            bytes: Z-machine code for the loop
        """
        if len(operands) < 1:
            raise ValueError("MAP-DIRECTIONS requires at least a loop specification")

        code = bytearray()

        # Parse loop specification: (dir-var pt-var room)
        loop_spec = operands[0]
        if isinstance(loop_spec, FormNode):
            spec_parts = [loop_spec.operator] + loop_spec.operands if loop_spec.operator else loop_spec.operands
        elif isinstance(loop_spec, list):
            spec_parts = loop_spec
        else:
            raise ValueError("MAP-DIRECTIONS loop specification must be a list")

        if len(spec_parts) < 3:
            raise ValueError("MAP-DIRECTIONS requires (dir-var pt-var room)")

        dir_var_node = spec_parts[0]
        pt_var_node = spec_parts[1]
        room_node = spec_parts[2]

        # Get direction counter variable name
        if isinstance(dir_var_node, AtomNode):
            dir_var_name = dir_var_node.value
        else:
            raise ValueError("MAP-DIRECTIONS dir-var must be an atom")

        # Get property table variable name
        if isinstance(pt_var_node, AtomNode):
            pt_var_name = pt_var_node.value
        else:
            raise ValueError("MAP-DIRECTIONS pt-var must be an atom")

        # Save current locals if they exist (for shadowing)
        saved_dir_local = self.locals.get(dir_var_name)
        saved_pt_local = self.locals.get(pt_var_name)

        # Allocate local for direction counter variable
        if dir_var_name in self.locals:
            dir_var_num = self.locals[dir_var_name]
        else:
            dir_var_num = len(self.locals) + 1
            self.locals[dir_var_name] = dir_var_num
            if hasattr(self, 'max_local_slot'):
                self.max_local_slot = max(self.max_local_slot, dir_var_num)

        # Allocate local for property table variable
        if pt_var_name in self.locals:
            pt_var_num = self.locals[pt_var_name]
        else:
            pt_var_num = len(self.locals) + 1
            self.locals[pt_var_name] = pt_var_num
            if hasattr(self, 'max_local_slot'):
                self.max_local_slot = max(self.max_local_slot, pt_var_num)

        # Get room operand
        room_type, room_val = self._get_operand_type_and_value(room_node)

        # Check for END clause
        end_clause = None
        body_start_idx = 1
        if len(operands) > 1 and isinstance(operands[1], list):
            # Check if it's (END ...) form
            if (len(operands[1]) > 0 and
                isinstance(operands[1][0], AtomNode) and
                operands[1][0].value.upper() == 'END'):
                end_clause = operands[1][1:]  # Skip the END atom
                body_start_idx = 2

        # Get max_properties and low_direction from symbol_tables
        max_properties = 31 if self.version <= 3 else 63
        low_direction = max_properties + 1  # Default if no directions defined
        if self.symbol_tables:
            low_direction = self.symbol_tables.get('low_direction', low_direction) or low_direction
            max_properties = self.symbol_tables.get('max_properties', max_properties) or max_properties

        # Initialize counter to MaxProperties + 1
        # STORE dir_var, MaxProperties + 1
        # 2OP long form encoding: 0 a b nnnnn where a,b = operand types (0=small, 1=var)
        # STORE is opcode 13 (0x0D in the nnnnn field)
        # For (small, small): 0 0 0 01101 = 0x0D
        init_val = max_properties + 1
        if init_val <= 255:
            code.append(0x0D)  # STORE 2OP long form, small/small
            code.append(dir_var_num & 0xFF)
            code.append(init_val & 0xFF)
        else:
            # Use VAR form for large constant
            code.append(0xCD)  # STORE VAR form (0xC0 | 0x0D)
            code.append(0x0F)  # types: small, large, omit, omit
            code.append(dir_var_num & 0xFF)
            code.append((init_val >> 8) & 0xFF)
            code.append(init_val & 0xFF)

        # Loop start position
        loop_start = len(code)

        # Push loop context onto loop_stack (for AGAIN support)
        loop_ctx = {
            'code_buffer': code,
            'loop_start': loop_start,
            'loop_type': 'MAP-DIRECTIONS',
            'again_placeholders': []
        }
        self.loop_stack.append(loop_ctx)

        # DEC_CHK dir_var < LOW-DIRECTION -> exit
        # DEC_CHK is 2OP opcode 0x04: decrement and branch if < value
        # First operand is variable NUMBER (small constant), second is comparison value
        # Long form encoding: 0 a b nnnnn where a=first type, b=second type
        # 0x04 = 0 0 0 00100 = small/small
        if low_direction <= 255:
            code.append(0x04)  # DEC_CHK 2OP long form, small/small
            code.append(dir_var_num & 0xFF)
            code.append(low_direction & 0xFF)
        else:
            # For large value, use VAR form: 0xC4
            code.append(0xC4)  # DEC_CHK VAR form
            code.append(0x0F)  # small, large, omit, omit
            code.append(dir_var_num & 0xFF)
            code.append((low_direction >> 8) & 0xFF)
            code.append(low_direction & 0xFF)

        # Branch on true (counter < LOW-DIRECTION) to exit
        # Branch encoding: bit 7=polarity, bit 6=form (1=short, 0=long), bits 5-0=offset/high bits
        exit_branch_pos = len(code)
        code.append(0xC0)  # Placeholder: branch on true, short form (will be patched)

        # GETPT room, dir_var -> pt_var
        # GET_PROP_ADDR is 2OP opcode 0x12 (but actually it might be different)
        # Actually GET_PROP_ADDR is EXT:$02 or could be different...
        # In V3, GET_PROP_ADDR is 2OP opcode 0x12
        # Wait, let me check: GETPT returns property table address
        # 2OP:$12 is GET_PROP_ADDR object property -> (result)
        if room_type == 1:  # Variable
            code.append(0x72)  # 2OP long form var/var
            code.append(room_val & 0xFF)
            code.append(dir_var_num & 0xFF)
        else:  # Small constant
            code.append(0x32)  # 2OP long form small/var
            code.append(room_val & 0xFF)
            code.append(dir_var_num & 0xFF)

        # Wait, I need to check the correct opcode for GET_PROP_ADDR
        # Looking at Z-machine spec: 2OP:$12 is GET_PROP_ADDR
        # But 0x72 would be 2OP:$12 with var/var operand types... let me recalculate
        # Long form 2OP: bit 7=0, bit 6 = second op type, bit 5 = first op type
        # 0x12 = 0 00 10010 = long form, small/small, opcode 18 (0x12)
        # For var/var: 0x12 | 0x40 | 0x20 = 0x72... wait that's not right
        # Long 2OP: 0 a b nnnnn where a=first op type (0=small, 1=var), b=second (same)
        # opcode 0x12 = 18 (GET_PROP_ADDR)
        # For small/var: 0 0 1 10010 = 0x32 (correct)
        # For var/var: 0 1 1 10010 = 0x72 (correct)

        # But we need to use the variable form with store
        # Actually I realize GET_PROP_ADDR stores its result
        # Let me check the instruction format again...
        # Short 1OP would be: 10 tt nnnn
        # But GET_PROP_ADDR is 2OP, so it uses long form or variable form

        # OK let me rewrite this properly
        code_len_before_getpt = len(code)
        code = code[:code_len_before_getpt - (3 if room_type == 1 else 3)]  # Remove incorrect GETPT

        # Recalculate from DEC_CHK branch position
        code = code[:exit_branch_pos + 2]  # Keep up to branch placeholder

        # GETPT (GET_PROP_ADDR) room, dir_var -> pt_var
        # 2OP opcode 0x12, stores result
        # Use VAR form for clarity: 0xD2 + types_byte + operands + store
        # VAR 2OP: 11 0 nnnnn where nnnnn = opcode
        # 0xD2 = VAR form of 2OP:0x12
        # Types byte encoding: 00=large, 01=small, 10=var, 11=omit
        # Reading bits 7-6, 5-4, 3-2, 1-0 for operands 1-4
        code.append(0xD2)  # VAR form of GET_PROP_ADDR
        # Types byte: 2 operands, first = room_type, second = variable (read value from dir_var)
        if room_type == 1:  # Variable
            types_byte = 0xAF  # var, var, omit, omit = 10 10 11 11
        else:  # Small constant
            types_byte = 0x6F  # small, var, omit, omit = 01 10 11 11
        code.append(types_byte)
        code.append(room_val & 0xFF)
        code.append(dir_var_num & 0xFF)
        code.append(pt_var_num & 0xFF)  # Store result

        # JZ pt_var -> loop_start (if property doesn't exist, try next)
        # JZ is 1OP opcode 0x00, branches if zero
        code.append(0xA0)  # JZ 1OP short form with variable operand
        code.append(pt_var_num & 0xFF)
        # Branch on true (pt == 0) back to loop_start
        # Since this is a backward branch, we need 2-byte (long) form
        # Long branch: bit 7=polarity, bit 6=0 (long), bits 13-8 in bits 5-0, bits 7-0 in next byte
        again_branch_pos = len(code)
        code.append(0x80)  # Placeholder: branch on true, long form
        code.append(0x00)  # Placeholder low byte

        # Body position (for AGAIN to jump to loop_start, not here)
        body_start = len(code)

        # Generate body statements
        for i in range(body_start_idx, len(operands)):
            stmt = operands[i]
            stmt_code = self.generate_statement(stmt)
            if stmt_code:
                code.extend(stmt_code)

        # Jump back to loop_start (unconditional)
        # JUMP offset
        current_pos = len(code)
        jump_offset = loop_start - (current_pos + 1)
        if jump_offset < 0:
            jump_offset_unsigned = (1 << 16) + jump_offset
        else:
            jump_offset_unsigned = jump_offset
        code.append(0x8C)  # JUMP opcode
        code.append((jump_offset_unsigned >> 8) & 0xFF)
        code.append(jump_offset_unsigned & 0xFF)

        # Exit point (where DEC_CHK branch goes)
        exit_point = len(code)

        # Patch exit branch (DEC_CHK) - short form (1 byte)
        # Branch formula: Target = Address_after_branch + Offset - 2
        # For 1-byte branch: Target = (exit_branch_pos + 1) + Offset - 2
        # So: Offset = Target - exit_branch_pos + 1
        exit_offset = exit_point - exit_branch_pos + 1
        if exit_offset >= 2 and exit_offset <= 63:
            # Short branch with offset (offset 0-1 are special: RFALSE/RTRUE)
            code[exit_branch_pos] = 0xC0 | (exit_offset & 0x3F)
        else:
            # Need long branch - would require restructuring code
            # For now, just use truncated offset (this is a bug if offset > 63)
            code[exit_branch_pos] = 0xC0 | (exit_offset & 0x3F)

        # Patch again branch (JZ pt_var) - long form (2 bytes total)
        # Branch formula: Target = Address_after_branch + Offset - 2
        # For 2-byte branch: Target = (again_branch_pos + 2) + Offset - 2 = again_branch_pos + Offset
        # So: Offset = Target - again_branch_pos
        again_offset = loop_start - again_branch_pos
        # Long branch format: 0x80 | (offset >> 8), offset & 0xFF
        # For backward branches, offset is negative (two's complement)
        if again_offset < 0:
            offset_unsigned = (1 << 14) + again_offset  # 14-bit two's complement
        else:
            offset_unsigned = again_offset
        code[again_branch_pos] = 0x80 | ((offset_unsigned >> 8) & 0x3F)
        code[again_branch_pos + 1] = offset_unsigned & 0xFF

        # Pop loop context
        if self.loop_stack:
            self.loop_stack.pop()

        # Execute END clause if present
        if end_clause:
            for stmt in end_clause:
                stmt_code = self.generate_statement(stmt)
                if stmt_code:
                    code.extend(stmt_code)

        # Restore shadowed locals
        if saved_dir_local is not None:
            self.locals[dir_var_name] = saved_dir_local
        elif dir_var_name in self.locals:
            del self.locals[dir_var_name]

        if saved_pt_local is not None:
            self.locals[pt_var_name] = saved_pt_local
        elif pt_var_name in self.locals:
            del self.locals[pt_var_name]

        return bytes(code)

    def gen_repeat(self, operands: List[ASTNode]) -> bytes:
        """Generate REPEAT loop.

        <REPEAT (bindings) body...> creates an infinite loop that executes body
        statements until RETURN is called to exit.
        AGAIN restarts the loop from the beginning.
        RETURN inside REPEAT exits the loop (not the routine) and provides
        the loop's result value.

        Example: <REPEAT () <COND (<FSET? ,X ,FLAG> <RETURN T>)> <INC X>>

        Args:
            operands[0]: Bindings (usually empty list () or variable bindings)
            operands[1:]: Statements to execute in loop body

        Returns:
            bytes: Z-machine code for the loop
        """
        # Use a bytearray that we can reference in stacks
        code = bytearray()

        if len(operands) < 1:
            return b''

        # Process bindings from operands[0] if present
        # For now, we skip processing bindings - they're handled elsewhere

        # Record loop start position (where AGAIN should jump back to)
        loop_start = len(code)

        # Push loop context onto loop_stack (for AGAIN support)
        loop_ctx = {
            'code_buffer': code,
            'loop_start': loop_start,  # Consistent with gen_prog, gen_bind, gen_do
            'loop_type': 'REPEAT',
            'again_placeholders': []  # Will be populated by gen_again
        }
        self.loop_stack.append(loop_ctx)

        # Push block context onto block_stack (for RETURN support)
        # Use stack (variable 0) to store the block result
        block_ctx = {
            'code_buffer': code,
            'return_placeholders': [],  # Positions of RETURN jumps to patch
            'block_type': 'REPEAT',
            'result_var': 0,  # Stack (SP) - result is pushed onto stack
        }
        self.block_stack.append(block_ctx)

        try:
            # Generate code for each statement in loop body
            for i in range(1, len(operands)):
                stmt = operands[i]
                stmt_code = self.generate_statement(stmt)
                if stmt_code:
                    code.extend(stmt_code)

            # At end of loop, add unconditional jump back to start
            # This creates the infinite loop (exit via RETURN)
            current_pos = len(code)
            # Z-machine JUMP: Target = PC + Offset - 2, where PC is after instruction
            # So: Offset = Target - PC + 2 = Target - (current_pos + 3) + 2
            jump_offset = loop_start - (current_pos + 1)

            # JUMP uses signed 16-bit offset
            if jump_offset < 0:
                jump_offset_unsigned = (1 << 16) + jump_offset  # Two's complement
            else:
                jump_offset_unsigned = jump_offset

            code.append(0x8C)  # JUMP opcode
            code.append((jump_offset_unsigned >> 8) & 0xFF)
            code.append(jump_offset_unsigned & 0xFF)

            # Exit point is right after the backward jump (this is where RETURN jumps to)
            exit_point = len(code)

            # Patch all RETURN placeholders (0x8C 0xFF 0xBB -> jump to exit_point)
            # Use pattern scanning instead of position tracking, since RETURN may be
            # inside nested structures (like COND) that generate code in temp buffers
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                    # Found RETURN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # Offset = Target - PC + 2 = exit_point - (i + 3) + 2
                    return_offset = exit_point - (i + 1)
                    if return_offset < 0:
                        return_offset_unsigned = (1 << 16) + return_offset
                    else:
                        return_offset_unsigned = return_offset
                    code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                    code[i+2] = return_offset_unsigned & 0xFF
                i += 1

            # Patch all AGAIN placeholders (0x8C 0xFF 0xAA -> actual jump)
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xAA:
                    # Found AGAIN placeholder at position i
                    # Z-machine JUMP: Target = PC + Offset - 2
                    # Offset = Target - PC + 2 = loop_start - (i + 3) + 2
                    again_offset = loop_start - (i + 1)
                    if again_offset < 0:
                        again_offset_unsigned = (1 << 16) + again_offset
                    else:
                        again_offset_unsigned = again_offset
                    code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                    code[i+2] = again_offset_unsigned & 0xFF
                i += 1

        finally:
            # Pop block context
            self.block_stack.pop()
            # Pop loop context
            self.loop_stack.pop()

        return bytes(code)

    def gen_and_pred(self, operands: List[ASTNode]) -> bytes:
        """Generate AND? (logical AND predicate with short-circuit).

        <AND? expr1 expr2 ...> evaluates expressions left to right.
        Returns false (0) if any expression is false.
        Returns the value of the last expression if all are true.

        Args:
            operands: Expressions to AND together

        Returns:
            bytes: Z-machine code for logical AND
        """
        code = bytearray()

        if len(operands) < 2:
            return b''

        # For simplicity, evaluate all operands and use bitwise AND
        # Full implementation would need short-circuit branching
        for i, operand in enumerate(operands):
            op_code = self.generate_statement(operand)
            if op_code:
                code.extend(op_code)

        return bytes(code)

    def gen_or_pred(self, operands: List[ASTNode]) -> bytes:
        """Generate OR? (logical OR predicate with short-circuit).

        <OR? expr1 expr2 ...> evaluates expressions left to right.
        Returns first true (non-zero) value.
        Returns false (0) if all expressions are false.

        Args:
            operands: Expressions to OR together

        Returns:
            bytes: Z-machine code for logical OR
        """
        code = bytearray()

        if len(operands) < 2:
            return b''

        # For simplicity, evaluate all operands and use bitwise OR
        # Full implementation would need short-circuit branching
        for i, operand in enumerate(operands):
            op_code = self.generate_statement(operand)
            if op_code:
                code.extend(op_code)

        return bytes(code)

    # ===== List Operations =====

    def gen_first(self, operands: List[ASTNode]) -> bytes:
        """Generate FIRST (get first element of list/table).

        <FIRST table> returns the first element (at offset 0).
        Equivalent to <GET table 1> (1-based indexing).

        Args:
            operands[0]: Table/list address

        Returns:
            bytes: Z-machine code for getting first element
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # FIRST is same as GET with index 1 (1-based)
        # LOADW is 2OP opcode 0x0F: table[index] -> result
        # Use long form: opcode | (op1_type << 6) | (op2_type << 5)
        # Second operand (index 1) is always small constant (type 0)
        opcode = 0x0F | (op_type << 6) | (0 << 5)
        code.append(opcode)
        code.append(op_val & 0xFF)
        code.append(0x01)  # Index 1 (small constant)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_member(self, operands: List[ASTNode]) -> bytes:
        """Generate MEMBER (search for element in list).

        <MEMBER item table> searches for item in table.
        Returns the tail of the list starting at the found item, or false.

        V5+: Uses SCAN_TABLE opcode for efficient search
        V3/V4: Generates unrolled comparisons for small tables (≤8 elements)

        Args:
            operands[0]: Item to search for
            operands[1]: Table to search in

        Returns:
            bytes: Z-machine code for search
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # V5+: Use SCAN_TABLE opcode (EXT:0x18)
        if self.version >= 5:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # item
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # table

            code.append(0xBE)  # EXT opcode marker
            code.append(0x18)  # SCAN_TABLE

            # Type byte for operands: item, table, length (always 8)
            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x01)  # length (8) is small constant
            types.append(0x03)  # omit
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
            code.append(0x08)  # Search up to 8 elements (default)
            # Result stored to stack
            code.append(0x00)  # Store to SP

            return bytes(code)

        item = self.get_operand_value(operands[0])
        table = self.get_operand_value(operands[1])

        # V3/V4: Generate inline search for small tables
        # Uses unrolled comparisons with proper branch patching

        max_elements = 8  # Search up to 8 elements

        # For compile-time known values, generate unrolled search
        if isinstance(item, int) and isinstance(table, int):
            branch_positions = []  # Track positions of JE branches to patch

            # Generate unrolled comparisons
            for i in range(max_elements):
                offset = i * 2
                # LOADW table offset -> sp
                code.append(0xCF)  # VAR form of LOADW (2OP:15)
                if table <= 255:
                    code.append(0x55)  # small, small, omit, omit
                    code.append(table & 0xFF)
                else:
                    code.append(0x15)  # large, small, omit, omit
                    code.append((table >> 8) & 0xFF)
                    code.append(table & 0xFF)
                code.append(offset & 0xFF)
                code.append(0x00)  # Store to SP

                # JE sp item ?found (branch forward on match)
                code.append(0xC1)  # VAR form of JE (2OP:1)
                if item <= 255:
                    code.append(0xAF)  # var (sp), small, omit, omit
                    code.append(0x00)  # SP
                    code.append(item & 0xFF)
                else:
                    code.append(0xA3)  # var, large, omit, omit
                    code.append(0x00)  # SP
                    code.append((item >> 8) & 0xFF)
                    code.append(item & 0xFF)
                # Save branch position for patching (use 2-byte form to ensure space)
                branch_positions.append(len(code))
                code.append(0x00)  # Placeholder - 2-byte branch, high byte
                code.append(0x00)  # Placeholder - low byte

            # Not found - push 0 to stack
            code.append(0x54)  # ADD small, small -> result
            code.append(0x00)  # 0
            code.append(0x00)  # + 0
            code.append(0x00)  # Store to SP

            # Jump over found block to end
            end_jump_pos = len(code)
            code.append(0x8C)  # JUMP (1OP:12)
            code.append(0x00)  # Offset high (placeholder)
            code.append(0x00)  # Offset low (placeholder)

            # Found label - push table address (non-zero = truthy)
            found_label = len(code)
            if table <= 255:
                code.append(0x54)  # ADD small, small
                code.append(0x00)  # 0
                code.append(table & 0xFF)
                code.append(0x00)  # Store to SP
            else:
                code.append(0xD4)  # VAR form of ADD
                code.append(0x0F)  # small, large, omit, omit
                code.append(0x00)  # 0
                code.append((table >> 8) & 0xFF)
                code.append(table & 0xFF)
                code.append(0x00)  # Store to SP

            # End label position
            end_label = len(code)

            # Patch all JE branches to jump to found_label
            for pos in branch_positions:
                # 2-byte branch: offset from byte after branch bytes
                offset = found_label - (pos + 2)
                # 2-byte format: bit 7 = polarity (1=true), bit 6 = 0 (2-byte)
                # bits 13-8 in first byte (bits 5-0), bits 7-0 in second byte
                code[pos] = 0x80 | ((offset >> 8) & 0x3F)  # Branch on true, high 6 bits
                code[pos + 1] = offset & 0xFF  # Low 8 bits

            # Patch end jump
            jump_offset = end_label - (end_jump_pos + 3)
            code[end_jump_pos + 1] = (jump_offset >> 8) & 0xFF
            code[end_jump_pos + 2] = jump_offset & 0xFF

            return bytes(code)

        # For variable operands, generate loop-based search
        # L01 = counter (8 iterations max), L02 = offset, L03 = item, L04 = table
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # item
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # table

        # Initialize counter to 8
        code.append(0x0D)
        code.append(0x01)  # L01 = counter
        code.append(0x00)
        code.append(0x08)  # 8 iterations

        # Initialize offset to 0
        code.append(0x0D)
        code.append(0x02)  # L02 = offset
        code.append(0x00)
        code.append(0x00)

        # Store item in L03
        code.append(0x0D | (op1_type << 6))
        code.append(0x03)  # L03 = item
        code.append(op1_val & 0xFF)

        # Store table in L04
        code.append(0x0D | (op2_type << 6))
        code.append(0x04)  # L04 = table
        code.append(op2_val & 0xFF)

        loop_start = len(code)

        # LOADW L04 L02 -> sp (get element at offset)
        code.append(0xCF)  # LOADW VAR form
        code.append(0xAF)  # var, var, omit, omit
        code.append(0x04)  # L04 (table)
        code.append(0x02)  # L02 (offset)
        code.append(0x00)  # -> stack

        # JE sp L03 ?found
        code.append(0xC1)  # JE VAR form
        code.append(0xAF)  # var, var, omit, omit
        code.append(0x00)  # stack
        code.append(0x03)  # L03 (item)
        # Branch to found - will be patched
        found_branch_pos = len(code)
        code.append(0x40)  # Placeholder

        # ADD L02 2 -> L02 (increment offset)
        code.append(0x54)  # ADD
        code.append(0x02)  # L02
        code.append(0x02)  # 2
        code.append(0x02)  # -> L02

        # DEC_CHK L01 0 [loop_start]
        code.append(0x04)  # DEC_CHK
        code.append(0x01)  # L01
        code.append(0x00)  # 0
        current_pos = len(code) + 2
        jump_offset = loop_start - current_pos
        if jump_offset >= -64:
            code.append(0x00 | ((jump_offset + 2) & 0x3F))
        else:
            jump_offset_unsigned = (1 << 14) + jump_offset
            code.append(0x00 | ((jump_offset_unsigned >> 8) & 0x3F))
            code.append(jump_offset_unsigned & 0xFF)

        # Not found - push 0 to stack
        code.append(0x54)  # ADD 0+0 -> sp
        code.append(0x00)
        code.append(0x00)
        code.append(0x00)

        # Jump to end
        end_jump_pos = len(code)
        code.append(0x8C)  # JUMP
        code.append(0x00)
        code.append(0x00)

        # Found - push table address (truthy)
        found_label = len(code)
        code.append(0x0F | (op2_type << 6))  # LOADW uses same pattern, we just load L04 value
        code.append(0x54)  # ADD L04 + 0
        code[-1] = 0x54 | (1 << 6)  # var, small
        code.append(0x04)  # L04
        code.append(0x00)  # + 0
        code.append(0x00)  # -> stack

        end_label = len(code)

        # Patch found branch
        offset = found_label - found_branch_pos - 1
        code[found_branch_pos] = 0x40 | (offset & 0x3F)

        # Patch end jump
        jump_offset = end_label - (end_jump_pos + 3)
        code[end_jump_pos + 1] = (jump_offset >> 8) & 0xFF
        code[end_jump_pos + 2] = jump_offset & 0xFF

        return bytes(code)

    def gen_memq(self, operands: List[ASTNode]) -> bytes:
        """Generate MEMQ (search for item with EQUAL? test).

        <MEMQ item table> searches for item in table using EQUAL?.
        Returns the tail of the list starting at the found item, or false.

        In Z-machine, MEMQ is essentially the same as MEMBER since
        JE (jump if equal) is used for both. The distinction in ZIL
        is semantic (MEMQ for lists, MEMBER for general search).

        Args:
            operands[0]: Item to search for
            operands[1]: Table to search in

        Returns:
            bytes: Z-machine code for search
        """
        if len(operands) < 2:
            return b''

        # MEMQ is semantically the same as MEMBER in Z-machine
        # Both use JE for comparison
        # Delegate to MEMBER implementation
        return self.gen_member(operands)

    # ===== Comparison Operations =====

    def gen_equal(self, operands: List[ASTNode]) -> bytes:
        """Generate JE (jump if equal) - pushes 1 if equal, 0 otherwise to stack.

        JE can compare up to 4 values: <EQUAL? a b c d> tests if a equals any of b, c, d.
        Returns true (1) if equal, false (0) otherwise.
        """
        if len(operands) < 1:
            raise ValueError("EQUAL? requires at least 1 operand")
        if len(operands) < 2:
            # Single operand - always false (nothing to compare to)
            return bytes([0x14, 0x00, 0x00, 0x00])  # ADD 0 0 -> stack (push 0)

        code = bytearray()

        # If first operand is a nested expression, evaluate it first
        first_op = operands[0]
        if isinstance(first_op, FormNode):
            expr_code = self.generate_form(first_op)
            code.extend(expr_code)
            op1_type = 1  # Variable (stack)
            op1_val = 0   # Stack
        elif isinstance(first_op, CondNode):
            expr_code = self.generate_cond(first_op)
            code.extend(expr_code)
            op1_type = 1
            op1_val = 0
        else:
            op1_type, op1_val = self._get_operand_type_and_value(first_op)

        # Handle simple 2-operand case specially for efficiency
        if len(operands) == 2:
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])

            # Check if we need large constant encoding
            needs_large1 = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
            needs_large2 = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

            if needs_large1 or needs_large2:
                # Use VAR form JE for large constants
                # VAR form: 0xC1 types_byte operands...
                code.append(0xC1)  # VAR form 2OP, opcode JE (0x01)

                # Build type byte
                type1 = 0b00 if needs_large1 else (0b01 if op1_type == 0 else 0b10)
                type2 = 0b00 if needs_large2 else (0b01 if op2_type == 0 else 0b10)
                types_byte = (type1 << 6) | (type2 << 4) | 0x0F  # 0x0F = omit, omit
                code.append(types_byte)

                # Operand 1
                if needs_large1:
                    code.append((op1_val >> 8) & 0xFF)
                    code.append(op1_val & 0xFF)
                else:
                    code.append(op1_val & 0xFF)

                # Operand 2
                if needs_large2:
                    code.append((op2_val >> 8) & 0xFF)
                    code.append(op2_val & 0xFF)
                else:
                    code.append(op2_val & 0xFF)

                # Branch: if equal, skip to true case
                # Calculate offset based on sizes
                false_case_size = 4 + 3  # ADD + JUMP
                true_case_start = false_case_size + 2  # +2 for branch bytes
                code.append(0xC0 | (true_case_start & 0x3F))  # branch on true, short
            else:
                # Standard 2OP long form for small operands
                # JE op1 op2 ?true (branch to true case)
                opcode = 0x01 | (op1_type << 6) | (op2_type << 5)
                code.append(opcode)
                code.append(op1_val & 0xFF)
                code.append(op2_val & 0xFF)
                # Branch: if equal, skip to true case (offset 9 bytes forward)
                code.append(0xC9)  # branch on true, short, offset 9

            # FALSE case: ADD 0 0 -> stack (push 0)
            code.append(0x14)  # ADD 2OP small small
            code.append(0x00)
            code.append(0x00)
            code.append(0x00)  # Store to stack

            # JUMP past true case (offset 6)
            code.append(0x8C)  # JUMP
            code.append(0x00)
            code.append(0x06)  # offset 6

            # TRUE case: ADD 0 1 -> stack (push 1)
            code.append(0x14)
            code.append(0x00)
            code.append(0x01)
            code.append(0x00)  # Store to stack

            return bytes(code)

        # Multi-operand case: use VAR form JE
        # JE can compare 1 value against up to 3 others per instruction
        # For more than 4 operands total, we need to chain multiple JE instructions
        all_comparands = operands[1:]

        # If first operand is from stack and we need multiple JEs, save it first
        # Each JE reads from stack which pops the value, so we need to preserve it
        if op1_type == 1 and op1_val == 0 and len(all_comparands) > 3:
            # Save stack value to a temp global (global 16 = 0x10)
            temp_global = 0x10
            # Use VAR form ADD: sp + 0 -> temp_global (copy stack to temp)
            code.append(0xD4)  # VAR form ADD (0xC0 | 0x14)
            code.append(0x9F)  # Types: var(10), small(01), omit(11), omit(11) = 0x9F
            code.append(0x00)  # operand 1: sp (variable 0)
            code.append(0x00)  # operand 2: 0 (small constant)
            code.append(temp_global)  # store result to temp global
            # Now use temp_global instead of stack for all JEs
            op1_val = temp_global

        # Build list of JE instructions, each comparing op1 against up to 3 values
        je_instructions = []
        for i in range(0, len(all_comparands), 3):
            chunk = all_comparands[i:i+3]
            je_code = bytearray()

            # VAR:1 form: 0xC1 followed by type byte
            je_code.append(0xC1)  # VAR form JE

            # Build type byte for all operands (op1 + chunk)
            types_and_vals = [(op1_type, op1_val)]
            for op in chunk:
                t, v = self._get_operand_type_and_value(op)
                types_and_vals.append((t, v))

            # Map types: 0=small const->01, 1=var->10
            type_byte = 0
            for j, (t, v) in enumerate(types_and_vals):
                if j >= 4:
                    break
                type_code = 0x01 if t == 0 else 0x02
                type_byte |= (type_code << (6 - j * 2))
            # Fill remaining with 0x03 (omitted)
            for j in range(len(types_and_vals), 4):
                type_byte |= (0x03 << (6 - j * 2))

            je_code.append(type_byte)

            # Add operand values
            for t, v in types_and_vals:
                je_code.append(v & 0xFF)

            # Placeholder for branch byte - will be filled in later
            je_code.append(0x00)  # Placeholder

            je_instructions.append(je_code)

        # Calculate offsets: each JE branches to TRUE case on match
        # FALSE case is 4 bytes (ADD 0 0 -> stack)
        # JUMP is 3 bytes
        # TRUE case is 4 bytes (ADD 0 1 -> stack)
        # Total ending: 4 + 3 + 4 = 11 bytes

        # Calculate total size of remaining JE instructions after each one
        # Each JE branches forward to the TRUE case
        # Offset = remaining JE instructions size + FALSE case (4) + JUMP (3) + 2
        # The +2 is because offset is from the branch byte position

        for idx, je_code in enumerate(je_instructions):
            # Calculate bytes remaining after this JE instruction
            remaining_je_size = sum(len(je) for je in je_instructions[idx+1:])
            # Offset to TRUE case: remaining JEs + FALSE (4) + JUMP (3) + 2
            offset = remaining_je_size + 4 + 3 + 2

            # Branch on true, short form (bit 7=1 for true, bit 6=1 for short)
            # Short branch: offset in bits 0-5
            if offset <= 63:
                je_code[-1] = 0xC0 | offset  # 0xC0 = branch true, short
            else:
                # Need long branch - replace single byte with two bytes
                je_code[-1] = 0x80 | ((offset >> 8) & 0x3F)  # High bits
                je_code.append(offset & 0xFF)  # Low byte

        # Now emit all JE instructions
        for je_code in je_instructions:
            code.extend(je_code)

        # FALSE case: ADD 0 0 -> stack
        code.append(0x14)
        code.append(0x00)
        code.append(0x00)
        code.append(0x00)

        # JUMP past true case
        code.append(0x8C)
        code.append(0x00)
        code.append(0x06)

        # TRUE case: ADD 0 1 -> stack
        code.append(0x14)
        code.append(0x00)
        code.append(0x01)
        code.append(0x00)

        return bytes(code)

    def gen_less(self, operands: List[ASTNode]) -> bytes:
        """Generate JL (jump if less) - branch instruction."""
        if len(operands) != 2:
            raise ValueError("LESS? requires exactly 2 operands")

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if we need large constants (for negative or large values)
        needs_large1 = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
        needs_large2 = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

        if needs_large1 or needs_large2:
            # Use VAR form for large constants
            code.append(0xC2)  # VAR form JL (0xC0 | 0x02)
            # Build type byte: 00=large, 01=small, 10=var, 11=omit
            type_byte = 0
            if needs_large1:
                type_byte |= (0x00 << 6)  # Large constant
            elif op1_type == 0:
                type_byte |= (0x01 << 6)  # Small constant
            else:
                type_byte |= (0x02 << 6)  # Variable
            if needs_large2:
                type_byte |= (0x00 << 4)  # Large constant
            elif op2_type == 0:
                type_byte |= (0x01 << 4)  # Small constant
            else:
                type_byte |= (0x02 << 4)  # Variable
            type_byte |= 0x0F  # Remaining slots omitted
            code.append(type_byte)
            # Add operands
            if needs_large1:
                val = op1_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op1_val & 0xFF)
            if needs_large2:
                val = op2_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op2_val & 0xFF)
        else:
            # JL is 2OP opcode 0x02, long form
            opcode = 0x02 | (op1_type << 6) | (op2_type << 5)
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)

        code.append(0xC1)  # Branch on true, return true
        code.append(0xB1)  # RFALSE - fall through

        return bytes(code)

    def gen_greater(self, operands: List[ASTNode]) -> bytes:
        """Generate JG (jump if greater) - branch instruction."""
        if len(operands) != 2:
            raise ValueError("GRTR? requires exactly 2 operands")

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Check if we need large constants (for negative or large values)
        needs_large1 = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
        needs_large2 = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

        if needs_large1 or needs_large2:
            # Use VAR form for large constants
            code.append(0xC3)  # VAR form JG (0xC0 | 0x03)
            # Build type byte: 00=large, 01=small, 10=var, 11=omit
            type_byte = 0
            if needs_large1:
                type_byte |= (0x00 << 6)  # Large constant
            elif op1_type == 0:
                type_byte |= (0x01 << 6)  # Small constant
            else:
                type_byte |= (0x02 << 6)  # Variable
            if needs_large2:
                type_byte |= (0x00 << 4)  # Large constant
            elif op2_type == 0:
                type_byte |= (0x01 << 4)  # Small constant
            else:
                type_byte |= (0x02 << 4)  # Variable
            type_byte |= 0x0F  # Remaining slots omitted
            code.append(type_byte)
            # Add operands
            if needs_large1:
                val = op1_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op1_val & 0xFF)
            if needs_large2:
                val = op2_val & 0xFFFF
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(op2_val & 0xFF)
        else:
            # JG is 2OP opcode 0x03, long form
            opcode = 0x03 | (op1_type << 6) | (op2_type << 5)
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)

        code.append(0xC1)  # Branch on true, return true
        code.append(0xB1)  # RFALSE - fall through

        return bytes(code)

    def gen_zero_test(self, operands: List[ASTNode]) -> bytes:
        """Generate ZERO? test (jump if zero).

        <ZERO? value> is equivalent to <EQUAL? value 0>
        Uses JZ (jump if zero) - 1OP opcode 0x00
        """
        if len(operands) != 1:
            raise ValueError("ZERO? requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # JZ is 1OP opcode 0x00 (branch instruction)
        # 1OP short form encoding:
        # 0x80-0x8F: large constant (2 bytes) - opcode is bits 3-0
        # 0x90-0x9F: small constant (1 byte) - opcode is bits 3-0
        # 0xA0-0xAF: variable (1 byte) - opcode is bits 3-0
        if op_type == 0:  # Constant
            val = op_val & 0xFFFF
            if -128 <= val <= 255:
                # Small constant
                code.append(0x90)  # Short 1OP, small constant, opcode 0x00
                code.append(val & 0xFF)
            else:
                # Large constant
                code.append(0x80)  # Short 1OP, large constant, opcode 0x00
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
        else:  # Variable
            code.append(0xA0)  # Short 1OP, variable, opcode 0x00
            code.append(op_val & 0xFF)
        code.append(0xC1)  # Branch on true, return true
        code.append(0xB1)  # RFALSE - fall through

        return bytes(code)

    def gen_one(self, operands: List[ASTNode]) -> bytes:
        """Generate 1? test (jump if equals 1).

        <1? value> is equivalent to <EQUAL? value 1>
        Uses JE (jump if equal) - 2OP opcode 0x01
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # JE is 2OP opcode 0x01 (branch instruction)
        if op_type == 0:  # Constant
            code.append(0x21)  # 2OP long form, small const, small const
            code.append(op_val & 0xFF)
            code.append(0x01)  # Compare with 1
        else:  # Variable
            code.append(0x61)  # 2OP long form, variable, small const
            code.append(op_val & 0xFF)
            code.append(0x01)  # Compare with 1
        code.append(0xC1)  # Branch on true, return true
        code.append(0xB1)  # RFALSE - fall through

        return bytes(code)

    def gen_assigned(self, operands: List[ASTNode]) -> bytes:
        """Generate ASSIGNED? test (check if local variable argument was passed).

        <ASSIGNED? var> checks if a local variable was passed an argument
        when the routine was called. Uses CHECK_ARG_COUNT (VAR opcode 0x3F).
        V5+ only.

        Returns 1 if the argument was passed, 0 otherwise.
        """
        if self.version < 5:
            raise ValueError("ASSIGNED? requires V5 or later")
        if len(operands) != 1:
            raise ValueError("ASSIGNED? requires exactly 1 operand")
        if not isinstance(operands[0], AtomNode):
            raise ValueError("ASSIGNED? requires a variable name, not a literal")

        var_name = operands[0].value
        if var_name not in self.locals:
            raise ValueError(f"ASSIGNED? requires a valid local variable, got '{var_name}'")

        var_num = self.locals[var_name]

        code = bytearray()
        # CHECK_ARG_COUNT is VAR opcode 0x3F (63) per frotz source
        # Opcode byte is 0xC0 + 0x3F = 0xFF
        # It's a branch instruction that branches if arg was passed
        #
        # Structure:
        # 0: FF        CHECK_ARG_COUNT (VAR:63)
        # 1: 7F        type byte (small const, omit, omit, omit)
        # 2: var_num   argument number to check
        # 3: C8        branch on true, short form, offset 8 (to byte 10)
        # 4-6: E8 7F 00  PUSH 0 (not passed)
        # 7-9: 8C 00 04  JUMP +4 (to byte 13)
        # 10-12: E8 7F 01  PUSH 1 (passed)
        # 13: (end)
        code.append(0xFF)  # CHECK_ARG_COUNT (VAR:63)
        code.append(0x7F)  # Type byte: small const (01), omit, omit, omit
        code.append(var_num & 0xFF)  # Argument number to check
        code.append(0xC8)  # Branch on true, short form, offset 8
        # Push 0 (argument not passed)
        code.append(0xE8)  # PUSH VAR form
        code.append(0x7F)  # Type: small const
        code.append(0x00)  # Value 0
        # JUMP to end (skip PUSH 1)
        code.append(0x8C)  # JUMP 1OP with large const
        code.append(0x00)  # High byte of offset
        code.append(0x04)  # Low byte of offset (jump +4 from PC after reading)
        # Push 1 (argument was passed)
        code.append(0xE8)  # PUSH VAR form
        code.append(0x7F)  # Type: small const
        code.append(0x01)  # Value 1

        return bytes(code)

    def gen_not_predicate(self, operands: List[ASTNode]) -> bytes:
        """Generate NOT? (test if value is false/zero).

        <NOT? value> is equivalent to <ZERO? value>
        Returns true if value is 0 or false.

        Args:
            operands[0]: Value to test

        Returns:
            bytes: Z-machine code (JZ - jump if zero)
        """
        # NOT? is the same as ZERO?
        return self.gen_zero_test(operands)

    def gen_true_predicate(self, operands: List[ASTNode]) -> bytes:
        """Generate TRUE? / T? (test if value is non-zero).

        <TRUE? value> or <T? value> tests if a value is non-zero (true).
        This is the opposite of ZERO?/NOT?

        Args:
            operands[0]: Value to test

        Returns:
            bytes: Z-machine code (JZ with inverted branch)
        """
        if not operands:
            return b''

        code = bytearray()

        # Handle FormNode by generating inner expression first
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            # Result is on stack, use JZ on variable 0
            code.append(0xA0)  # 1OP:JZ with variable
            code.append(0x00)  # Variable 0 = stack
            # JZ condition = "value == 0"
            # Branch encoding: 0xC0 = branch on true (if condition met), offset 0 = RFALSE
            # So: if value IS zero, branch to RFALSE
            # Fall through means value was non-zero, execute RTRUE
            code.append(0xC0)  # Branch on true (if zero), return false
            code.append(0xB0)  # RTRUE - fall through means value was non-zero
        else:
            op_type, op_val = self._get_operand_type_and_value(operands[0])

            # JZ is 1OP opcode 0x00 (branch instruction)
            # JZ condition = "value == 0"
            # For TRUE?, we want: return true if non-zero, false if zero
            # So: if value IS zero (JZ condition true), branch to RFALSE
            #     if value is non-zero (JZ condition false), fall through to RTRUE
            if op_type == 0:  # Constant
                val = op_val & 0xFFFF
                if -128 <= val <= 255:
                    code.append(0x90)  # 1OP:JZ with small constant
                    code.append(val & 0xFF)
                else:
                    code.append(0x80)  # 1OP:JZ with large constant
                    code.append((val >> 8) & 0xFF)
                    code.append(val & 0xFF)
            else:  # Variable
                code.append(0xA0)  # 1OP:JZ with variable
                code.append(op_val & 0xFF)
            # Branch encoding: 0xC0 = branch on true, offset 0 = RFALSE
            # If value is zero, branch to return false; else fall through to return true
            code.append(0xC0)  # Branch on true (if zero), return false
            code.append(0xB0)  # RTRUE - fall through

        return bytes(code)

    # ===== Logical Operations =====

    def gen_and(self, operands: List[ASTNode]) -> bytes:
        """Generate AND (short-circuit logical AND).

        <AND a b c ...> evaluates expressions left-to-right:
        - Returns false (0) as soon as any expression is false
        - Returns the value of the last expression if all are truthy
        - 0 operands: returns true (non-zero)
        - 1 operand: returns that operand's value

        This is logical AND with short-circuit evaluation, NOT bitwise AND.
        For bitwise AND, use BAND/ANDB.
        """
        if len(operands) == 0:
            # No operands - return true (1)
            return self._gen_push_const(1)

        if len(operands) == 1:
            # Single operand - just evaluate and return its value
            return self._gen_push_operand(operands[0])

        code = bytearray()
        fail_patches = []  # Positions that need to be patched to jump to failure

        # For each operand except the last, evaluate and jump to failure if false
        for i, operand in enumerate(operands[:-1]):
            # Generate code to evaluate this operand
            if isinstance(operand, FormNode):
                inner_code = self.generate_form(operand)
                code.extend(inner_code)
                op_type = 2  # Variable (stack)
                op_val = 0   # Stack
            elif isinstance(operand, CondNode):
                inner_code = self.generate_cond(operand)
                code.extend(inner_code)
                op_type = 2
                op_val = 0
            else:
                op_type, op_val = self._get_operand_type_and_value_ext(operand)
                # Push non-form operands to stack for consistency
                if op_type == 2:  # Variable
                    code.append(0xAE)  # LOAD var -> stack
                    code.append(op_val & 0xFF)
                    code.append(0x00)  # -> stack
                elif op_type == 1:  # Small constant
                    code.append(0x14)  # ADD 0, const -> stack
                    code.append(0x00)
                    code.append(op_val & 0xFF)
                    code.append(0x00)  # -> stack
                else:  # Large constant
                    code.append(0xD4)  # VAR ADD
                    code.append(0x4F)  # small, large, omit, omit
                    code.append(0x00)
                    code.append((op_val >> 8) & 0xFF)
                    code.append(op_val & 0xFF)
                    code.append(0x00)  # -> stack
                op_type = 2
                op_val = 0

            # JZ stack -> fail (if this operand is false, jump to failure)
            # JZ is 1OP opcode 0x00, with variable operand: 0xA0
            code.append(0xA0)  # JZ var
            code.append(0x00)  # Stack (variable 0)
            # Branch byte: bit 7=polarity (1=branch on true), bit 6=form (1=short offset)
            # We want branch on true (if zero), long form for 2-byte offset
            fail_patches.append(len(code))  # Remember position to patch
            code.append(0x80)  # Branch on true (condition met = is zero), long form
            code.append(0x00)  # Placeholder for offset low byte

        # Last operand - evaluate and leave on stack (this is the result)
        last_op = operands[-1]
        if isinstance(last_op, FormNode):
            inner_code = self.generate_form(last_op)
            code.extend(inner_code)
        elif isinstance(last_op, CondNode):
            inner_code = self.generate_cond(last_op)
            code.extend(inner_code)
        else:
            op_type, op_val = self._get_operand_type_and_value_ext(last_op)
            if op_type == 2:  # Variable
                code.append(0xAE)  # LOAD var -> stack
                code.append(op_val & 0xFF)
                code.append(0x00)
            elif op_type == 1:  # Small constant
                code.append(0x14)  # ADD 0, const -> stack
                code.append(0x00)
                code.append(op_val & 0xFF)
                code.append(0x00)
            else:  # Large constant
                code.append(0xD4)  # VAR ADD
                code.append(0x4F)
                code.append(0x00)
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
                code.append(0x00)

        # JUMP over failure block
        success_jump_pos = len(code)
        code.append(0x8C)  # JUMP with large constant
        code.append(0x00)  # Placeholder high byte
        code.append(0x00)  # Placeholder low byte

        # Failure block - push 0
        fail_target = len(code)
        code.append(0x14)  # ADD 0, 0 -> stack
        code.append(0x00)
        code.append(0x00)
        code.append(0x00)  # -> stack

        # End of AND - success jumps here
        end_pos = len(code)

        # Patch the failure jumps
        for patch_pos in fail_patches:
            # Branch offset = target - (instruction_after_branch)
            # For branch, instruction_after_branch = patch_pos + 2
            offset = fail_target - (patch_pos + 2) + 2
            if offset < 0 or offset > 0x3FFF:
                # Shouldn't happen for reasonable code
                offset = max(0, min(0x3FFF, offset))
            code[patch_pos] = 0x80 | ((offset >> 8) & 0x3F)  # Long branch, on true
            code[patch_pos + 1] = offset & 0xFF

        # Patch success jump
        # JUMP offset: Target = PC_after_JUMP + Offset - 2
        # PC_after_JUMP = success_jump_pos + 3
        # end_pos = success_jump_pos + 3 + Offset - 2
        # Offset = end_pos - success_jump_pos - 1
        jump_offset = end_pos - success_jump_pos - 1
        if jump_offset < 0:
            jump_offset = (1 << 16) + jump_offset
        code[success_jump_pos + 1] = (jump_offset >> 8) & 0xFF
        code[success_jump_pos + 2] = jump_offset & 0xFF

        return bytes(code)

    def gen_or(self, operands: List[ASTNode]) -> bytes:
        """Generate OR (short-circuit logical OR).

        <OR a b c ...> evaluates expressions left-to-right:
        - Returns the first truthy value encountered
        - Returns false (0) only if all expressions are false
        - 0 operands: returns false (0)
        - 1 operand: returns that operand's value

        This is logical OR with short-circuit evaluation, NOT bitwise OR.
        For bitwise OR, use BOR/ORB.
        """
        if len(operands) == 0:
            # No operands - return false (0)
            return self._gen_push_const(0)

        if len(operands) == 1:
            # Single operand - just evaluate and return its value
            return self._gen_push_operand(operands[0])

        code = bytearray()
        success_patches = []  # Positions that need to be patched to jump to success

        # For each operand except the last, evaluate and jump to success if truthy
        for i, operand in enumerate(operands[:-1]):
            # Generate code to evaluate this operand
            if isinstance(operand, FormNode):
                inner_code = self.generate_form(operand)
                code.extend(inner_code)
            elif isinstance(operand, CondNode):
                inner_code = self.generate_cond(operand)
                code.extend(inner_code)
            else:
                op_type, op_val = self._get_operand_type_and_value_ext(operand)
                if op_type == 2:  # Variable
                    code.append(0xAE)  # LOAD var -> stack
                    code.append(op_val & 0xFF)
                    code.append(0x00)
                elif op_type == 1:  # Small constant
                    code.append(0x14)  # ADD 0, const -> stack
                    code.append(0x00)
                    code.append(op_val & 0xFF)
                    code.append(0x00)
                else:  # Large constant
                    code.append(0xD4)  # VAR ADD
                    code.append(0x4F)
                    code.append(0x00)
                    code.append((op_val >> 8) & 0xFF)
                    code.append(op_val & 0xFF)
                    code.append(0x00)

            # Duplicate the value on stack so we can test it and still have it
            # LOAD 0 -> stack (copies top of stack)
            code.append(0xAE)  # LOAD var -> stack
            code.append(0x00)  # Stack (variable 0 = top of stack)
            code.append(0x00)  # -> stack

            # JZ stack -> continue (if zero, try next operand)
            # If NOT zero, we want to jump to success (keep the duplicated value)
            # JZ branches if value IS zero, so we branch to "next" on zero
            code.append(0xA0)  # JZ var
            code.append(0x00)  # Stack
            # Branch on true (is zero) - short offset to skip the success jump
            # We need: if zero, skip to next operand; if non-zero, jump to end
            # So: JZ +3 (skip JUMP), then JUMP to success
            code.append(0xC3)  # Branch on true (is zero), short form, offset 3

            # If we get here, value was non-zero - jump to success
            success_patches.append(len(code))
            code.append(0x8C)  # JUMP
            code.append(0x00)  # Placeholder high
            code.append(0x00)  # Placeholder low

            # Pop the duplicated value since we're trying next operand
            # PULL to scratch or just use ADD to discard
            # Actually we need to pop - the JZ consumed one, duplicate is still there
            # Wait, JZ with var 0 pops from stack. So after JZ (branch not taken):
            # - The original value was popped by LOAD to duplicate
            # - The duplicate was popped by JZ
            # - Nothing left on stack for this operand
            # That's correct - we continue to next operand

        # Last operand - evaluate and leave on stack (this is the result)
        last_op = operands[-1]
        if isinstance(last_op, FormNode):
            inner_code = self.generate_form(last_op)
            code.extend(inner_code)
        elif isinstance(last_op, CondNode):
            inner_code = self.generate_cond(last_op)
            code.extend(inner_code)
        else:
            op_type, op_val = self._get_operand_type_and_value_ext(last_op)
            if op_type == 2:  # Variable
                code.append(0xAE)  # LOAD var -> stack
                code.append(op_val & 0xFF)
                code.append(0x00)
            elif op_type == 1:  # Small constant
                code.append(0x14)  # ADD 0, const -> stack
                code.append(0x00)
                code.append(op_val & 0xFF)
                code.append(0x00)
            else:  # Large constant
                code.append(0xD4)  # VAR ADD
                code.append(0x4F)
                code.append(0x00)
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
                code.append(0x00)

        # End of OR - success jumps here (with their truthy value on stack)
        end_pos = len(code)

        # Patch success jumps
        for patch_pos in success_patches:
            jump_offset = end_pos - patch_pos - 1
            if jump_offset < 0:
                jump_offset = (1 << 16) + jump_offset
            code[patch_pos + 1] = (jump_offset >> 8) & 0xFF
            code[patch_pos + 2] = jump_offset & 0xFF

        return bytes(code)

    def gen_not(self, operands: List[ASTNode]) -> bytes:
        """Generate NOT (logical NOT).

        <NOT value> returns 1 if value is 0, else returns 0.
        This is logical NOT, not bitwise complement.
        For bitwise complement, use BCOM.

        Implementation: use JZ to branch, push 1 or 0 to stack.
        """
        if len(operands) != 1:
            raise ValueError("NOT requires exactly 1 operand")

        code = bytearray()

        # Handle FormNode by generating inner expression first
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            op_type = 2  # Variable (stack)
            op_val = 0   # Stack
        elif isinstance(operands[0], CondNode):
            inner_code = self.generate_cond(operands[0])
            code.extend(inner_code)
            op_type = 2
            op_val = 0
        else:
            op_type, op_val = self._get_operand_type_and_value_ext(operands[0])

        # Strategy:
        # JZ value ?+4 (branch forward 4 bytes if zero)
        # ADD 0 0 -> sp (push 0 for false)
        # JUMP +3 (skip push 1)
        # ADD 0 1 -> sp (push 1 for true)

        # 1OP JZ (opcode 0) with operand
        if op_type == 0:  # Large constant
            code.append(0x80)  # 1OP:JZ with large constant
            code.append((op_val >> 8) & 0xFF)
            code.append(op_val & 0xFF)
        elif op_type == 1:  # Small constant
            code.append(0x90)  # 1OP:JZ with small constant
            code.append(op_val & 0xFF)
        else:  # Variable
            code.append(0xA0)  # 1OP:JZ with variable
            code.append(op_val & 0xFF)

        # Branch byte: branch on true (value is zero), short offset
        # We need to skip: ADD 0 0 -> sp (4 bytes) + JUMP (3 bytes) = 7 bytes
        # But branch offset 2 means skip 0 instructions (return), offset 3 means skip 1 byte
        # Actually, offset is just the number of bytes to skip from end of branch instruction
        # Offset 2 = return false, offset 3 = return true... no those are special
        # For normal branch: offset = actual_offset - 2 (since 0,1 are special)
        # To skip 7 bytes: offset = 7 + 2 = 9
        # Branch byte: polarity=1 (true), short=1, offset in bits 0-5
        # 0xC0 | 9 = 0xC9
        code.append(0xC9)  # Branch on true, skip forward 7 bytes (offset 9)

        # Not zero path: push 0
        code.append(0x14)  # ADD small, small
        code.append(0x00)  # 0
        code.append(0x00)  # 0
        code.append(0x00)  # Store to stack

        # JUMP forward to skip the push 1 (need to skip 4 bytes)
        # JUMP is 1OP:C (opcode 12) with a 2-byte signed offset
        # The offset calculation: target = address_after_jump + offset - 2
        # To skip 4 bytes: offset = 4 + 2 = 6
        code.append(0x8C)  # JUMP with large constant offset
        code.append(0x00)  # High byte of offset
        code.append(0x06)  # Low byte: skip 4 bytes (offset 6)

        # Zero path: push 1
        code.append(0x14)  # ADD small, small
        code.append(0x00)  # 0
        code.append(0x01)  # 1
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_bcom(self, operands: List[ASTNode]) -> bytes:
        """Generate BCOM (bitwise complement).

        BCOM requires exactly 1 operand.
        V1-V4: Uses native NOT (1OP:0F)
        V5+: NOT opcode was replaced by CALL_1N, so emulate with -(value+1)
        """
        if len(operands) != 1:
            self._error(f"BCOM requires exactly 1 operand, got {len(operands)}")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value_ext(operands[0])

        if self.version >= 5:
            # V5+: NOT opcode doesn't exist (replaced by CALL_1N)
            # Use identity: ~X = -(X+1) = SUB(0, ADD(X, 1))
            # Step 1: ADD X 1 -> stack
            # Step 2: SUB 0 stack -> stack

            # Step 1: ADD operand 1 -> stack (2OP opcode 0x14)
            if op_type == 0:  # Large constant
                # Long form 2OP: %01aabbbb where aa=op1type, bb=op2type
                # op1=large (0), op2=small (1): %01001100 = 0x4C? No...
                # Actually for large+small we need VAR form
                code.append(0xD4)  # VAR form of ADD
                code.append(0x1F)  # Types: large(00), small(01), omit(11), omit(11)
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
                code.append(0x01)  # 1
            elif op_type == 1:  # Small constant
                # Long form 2OP with small+small
                code.append(0x54)  # 2OP:ADD with small, small
                code.append(op_val & 0xFF)
                code.append(0x01)  # 1
            else:  # Variable (op_type == 2)
                # Long form 2OP with var+small
                code.append(0x74)  # 2OP:ADD with var, small
                code.append(op_val & 0xFF)
                code.append(0x01)  # 1

            code.append(0x00)  # Store to stack

            # Step 2: SUB 0 stack -> stack (2OP opcode 21)
            # SUB is opcode 21 which is > 15, so must use VAR form
            # VAR form: 0xC0 | opcode = 0xC0 | 0x15 = 0xD5
            code.append(0xD5)  # VAR form of SUB
            code.append(0x6F)  # Types: small(01), var(10), omit(11), omit(11)
            code.append(0x00)  # Small constant 0
            code.append(0x00)  # Variable 0 (stack)
            code.append(0x00)  # Store to stack
        else:
            # V1-V4: Use native NOT opcode (VAR:0x18 = 0xF8)
            # NOT is a VAR opcode that takes 1 operand and stores result
            code.append(0xF8)  # VAR opcode 0x18 = NOT

            # Type byte for 1 operand (bits: op1[7:6] op2[5:4] op3[3:2] op4[1:0])
            # 00=large, 01=small, 10=var, 11=omit
            if op_type == 0:  # Large constant
                code.append(0x3F)  # Type: large(00), omit(11), omit(11), omit(11)
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
            elif op_type == 1:  # Small constant
                code.append(0x7F)  # Type: small(01), omit(11), omit(11), omit(11)
                code.append(op_val & 0xFF)
            else:  # Variable (op_type == 2)
                code.append(0xBF)  # Type: var(10), omit(11), omit(11), omit(11)
                code.append(op_val & 0xFF)

            code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Object Operations =====

    def _track_flag_usage(self, operand: ASTNode) -> None:
        """Track usage of a flag constant for ZIL0211 warnings.

        Flags can be referenced as:
        - Bare atoms: MYBIT
        - Global variable references: ,MYBIT
        """
        flag_name = None
        if isinstance(operand, AtomNode):
            flag_name = operand.value
        elif isinstance(operand, GlobalVarNode):
            flag_name = operand.name

        if flag_name and flag_name in self.defined_flags:
            self.used_flags.add(flag_name)

    def _track_property_usage(self, operand: ASTNode) -> None:
        """Track usage of a property constant for ZIL0212 warnings.

        Properties can be referenced as:
        - Bare atoms: P?MYPROP
        - Global variable references: ,P?MYPROP
        """
        prop_name = None
        if isinstance(operand, AtomNode):
            prop_name = operand.value
        elif isinstance(operand, GlobalVarNode):
            prop_name = operand.name

        if prop_name and prop_name in self.defined_properties:
            self.used_properties.add(prop_name)

    def gen_fset(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_ATTR (set object attribute).

        Returns the previous value of the flag (1 if was set, 0 if not).
        """
        if len(operands) != 2:
            raise ValueError("FSET requires exactly 2 operands")

        # Track flag usage for ZIL0211 warning
        self._track_flag_usage(operands[1])

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # First, test the attribute to get the previous value
        # TEST_ATTR is 2OP opcode 0x0A (branch instruction)
        opcode = 0x0A | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        # Branch on true (was set), offset 9 to skip false case
        code.append(0xC9)

        # FALSE case: attribute was not set
        # Push 0, then set the attribute
        code.extend([0x14, 0x00, 0x00, 0x00])  # ADD 0 0 -> stack
        # JUMP to skip true case (offset 6)
        code.extend([0x8C, 0x00, 0x06])

        # TRUE case: attribute was set
        # Push 1
        code.extend([0x14, 0x00, 0x01, 0x00])  # ADD 0 1 -> stack

        # Now set the attribute (SET_ATTR is 2OP opcode 0x0B)
        opcode = 0x0B | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_fclear(self, operands: List[ASTNode]) -> bytes:
        """Generate CLEAR_ATTR (clear object attribute).

        Returns the previous value of the flag (1 if was set, 0 if not).
        """
        if len(operands) != 2:
            raise ValueError("FCLEAR requires exactly 2 operands")

        # Track flag usage for ZIL0211 warning
        self._track_flag_usage(operands[1])

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # First, test the attribute to get the previous value
        # TEST_ATTR is 2OP opcode 0x0A (branch instruction)
        opcode = 0x0A | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        # Branch on true (was set), offset 9 to skip false case
        code.append(0xC9)

        # FALSE case: attribute was not set
        # Push 0, then clear the attribute
        code.extend([0x14, 0x00, 0x00, 0x00])  # ADD 0 0 -> stack
        # JUMP to skip true case (offset 6)
        code.extend([0x8C, 0x00, 0x06])

        # TRUE case: attribute was set
        # Push 1
        code.extend([0x14, 0x00, 0x01, 0x00])  # ADD 0 1 -> stack

        # Now clear the attribute (CLEAR_ATTR is 2OP opcode 0x0C)
        opcode = 0x0C | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_fset_test(self, operands: List[ASTNode]) -> bytes:
        """Generate TEST_ATTR (test object attribute).

        Pushes 1 if attribute is set, 0 if not.
        """
        if len(operands) != 2:
            raise ValueError("FSET? requires exactly 2 operands")

        # Track flag usage for ZIL0211 warning
        self._track_flag_usage(operands[1])

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # TEST_ATTR is 2OP opcode 0x0A (branch)
        opcode = 0x0A | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        # Branch on true (attribute set), offset 9 to skip false case
        code.append(0xC9)

        # FALSE case: attribute not set, push 0
        code.extend([0x14, 0x00, 0x00, 0x00])  # ADD 0 0 -> stack
        # JUMP to skip true case (offset 6)
        code.extend([0x8C, 0x00, 0x06])

        # TRUE case: attribute set, push 1
        code.extend([0x14, 0x00, 0x01, 0x00])  # ADD 0 1 -> stack

        return bytes(code)

    def gen_move(self, operands: List[ASTNode]) -> bytes:
        """Generate INSERT_OBJ (move object to destination)."""
        if len(operands) != 2:
            raise ValueError("MOVE requires exactly 2 operands")

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # INSERT_OBJ is 2OP opcode 0x0E
        opcode = 0x0E | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_remove(self, operands: List[ASTNode]) -> bytes:
        """Generate REMOVE_OBJ (remove object from tree)."""
        if len(operands) != 1:
            raise ValueError("REMOVE requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # REMOVE_OBJ is 1OP opcode 0x09
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        if op_type == 0:  # Constant (small)
            code.append(0x99)  # Short 1OP, small constant
        else:  # Variable
            code.append(0xA9)  # Short 1OP, variable
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_loc(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PARENT (get object's parent)."""
        if len(operands) != 1:
            raise ValueError("LOC requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_PARENT is 1OP opcode 0x03
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        if op_type == 0:  # Constant (small)
            code.append(0x93)  # Short 1OP, small constant
        else:  # Variable
            code.append(0xA3)  # Short 1OP, variable
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Property Operations =====

    def gen_getp(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PROP (get object property)."""
        if len(operands) != 2:
            raise ValueError("GETP requires exactly 2 operands")

        # Track property usage for ZIL0212 warning
        self._track_property_usage(operands[1])

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # GET_PROP is 2OP opcode 0x11
        opcode = 0x11 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_putp(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT_PROP (set object property)."""
        if len(operands) != 3:
            raise ValueError("PUTP requires exactly 3 operands")

        # Track property usage for ZIL0212 warning
        self._track_property_usage(operands[1])

        code = bytearray()

        # Get operand types and values using extended version
        # which returns 0=large, 1=small, 2=variable
        op1_type, op1_val = self._get_operand_type_and_value_ext(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value_ext(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value_ext(operands[2])

        # PUT_PROP is VAR opcode 0x03
        code.append(0xE3)  # VAR form, opcode 0x03
        # Type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omitted
        type_byte = (op1_type << 6) | (op2_type << 4) | (op3_type << 2) | 0x03
        code.append(type_byte)

        # Write operand bytes based on type
        if op1_type == 0:  # Large constant
            code.append((op1_val >> 8) & 0xFF)
            code.append(op1_val & 0xFF)
        else:
            code.append(op1_val & 0xFF)

        if op2_type == 0:  # Large constant
            code.append((op2_val >> 8) & 0xFF)
            code.append(op2_val & 0xFF)
        else:
            code.append(op2_val & 0xFF)

        if op3_type == 0:  # Large constant
            code.append((op3_val >> 8) & 0xFF)
            code.append(op3_val & 0xFF)
        else:
            code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_ptsize(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PROP_LEN (get property length).

        <PTSIZE prop-addr> returns the length of a property.
        Uses GET_PROP_LEN - 1OP opcode 0x04.

        If operand is a FormNode, generate that form's code first.
        """
        if len(operands) != 1:
            raise ValueError("PTSIZE requires exactly 1 operand")

        code = bytearray()

        # Handle nested form operand
        if isinstance(operands[0], FormNode):
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            op_type = 1  # Variable (stack)
            op_val = 0   # Stack
        else:
            op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_PROP_LEN is 1OP opcode 0x04
        # 1OP short form: 0x80 = large const, 0x90 = small const, 0xA0 = variable
        if op_type == 1:  # Variable
            code.append(0xA4)  # 0xA0 + 0x04 = variable type, opcode 4
        else:  # Constant
            code.append(0x84)  # 0x80 + 0x04 = large const type, opcode 4
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_nextp(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_NEXT_PROP (get next property).

        <NEXTP obj prop> returns the next property number after prop.
        If prop is 0, returns the first property.
        Uses GET_NEXT_PROP - 2OP opcode 0x13.
        """
        if len(operands) != 2:
            raise ValueError("NEXTP requires exactly 2 operands")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # GET_NEXT_PROP is 2OP opcode 0x13 (long form with store)
        # _get_operand_type_and_value returns: 0=constant, 1=variable
        opcode = 0x13 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== COND Statement =====

    def generate_cond(self, cond: CondNode) -> bytes:
        """Generate COND statement with proper branching.

        COND works like this:
        - Test condition 1, if false jump to next clause
        - Execute actions for clause 1, then jump to end
        - Test condition 2, if false jump to next clause
        - Execute actions for clause 2, then jump to end
        - ... etc
        - T clause (if present) always executes if reached
        """
        code = bytearray()

        # First pass: generate all clause code WITHOUT branch offsets
        clause_data = []
        for i, (condition, actions) in enumerate(cond.clauses):
            # Check if this is the T (else) clause - can be T or ELSE
            is_t_clause = isinstance(condition, AtomNode) and condition.value.upper() in ('T', 'ELSE')

            # Generate the condition test (without proper offset yet)
            test_code = bytearray()
            test_size = 0
            if not is_t_clause:
                test_code = bytearray(self.generate_condition_test(condition, branch_on_false=True))
                test_size = len(test_code)

            # Generate actions for this clause
            actions_code = bytearray()
            for j, action in enumerate(actions):
                is_last_action = (j == len(actions) - 1)
                action_code = self.generate_statement(action)

                if is_last_action and len(action_code) == 0:
                    # Last action is a value that doesn't generate code (number, atom)
                    # Push the value to stack using ADD 0 val -> stack
                    # This allows COND to be used as an expression
                    # ADD is 2OP:20, long form encoding:
                    # 0x14 = ADD small, small
                    # 0x24 = ADD small, variable
                    if isinstance(action, NumberNode):
                        val = action.value
                        if 0 <= val <= 255:
                            # ADD 0 val -> stack
                            actions_code.extend([0x14, 0x00, val & 0xFF, 0x00])
                        else:
                            # Large constant - use VAR form ADD
                            # 0xD4 = VAR form ADD
                            # Type byte: 01 00 11 11 = 0x4F (small, large, omit, omit)
                            actions_code.append(0xD4)
                            actions_code.append(0x4F)
                            actions_code.append(0x00)  # First operand: 0
                            actions_code.append((val >> 8) & 0xFF)
                            actions_code.append(val & 0xFF)
                            actions_code.append(0x00)  # Store to stack
                    elif isinstance(action, AtomNode):
                        if action.value in self.constants:
                            val = self.constants[action.value]
                            if 0 <= val <= 255:
                                actions_code.extend([0x14, 0x00, val & 0xFF, 0x00])
                            else:
                                actions_code.append(0xD4)
                                actions_code.append(0x4F)
                                actions_code.append(0x00)
                                actions_code.append((val >> 8) & 0xFF)
                                actions_code.append(val & 0xFF)
                                actions_code.append(0x00)
                        elif action.value in self.globals:
                            var_num = self.globals[action.value]
                            # ADD 0 var -> stack (0x24 = small, variable)
                            actions_code.extend([0x24, 0x00, var_num & 0xFF, 0x00])
                        elif action.value in self.locals:
                            var_num = self.locals[action.value]
                            actions_code.extend([0x24, 0x00, var_num & 0xFF, 0x00])
                        else:
                            pass
                    elif isinstance(action, GlobalVarNode):
                        if action.name in self.globals:
                            var_num = self.globals[action.name]
                            actions_code.extend([0x24, 0x00, var_num & 0xFF, 0x00])
                    elif isinstance(action, LocalVarNode):
                        var_num = self.locals.get(action.name, 1)
                        actions_code.extend([0x24, 0x00, var_num & 0xFF, 0x00])
                else:
                    actions_code.extend(action_code)
                    # If this is the last action and it's a void operation,
                    # push 0 to ensure COND always has a value on the stack
                    if is_last_action and isinstance(action, FormNode):
                        op_name = action.operator.value.upper() if isinstance(action.operator, AtomNode) else ''
                        # Known void operations that don't push a value
                        void_ops = {
                            'PRINTI', 'PRINT', 'PRINTR', 'PRINTC', 'PRINTB', 'PRINTD',
                            'PRINTN', 'PRINTT', 'PRINTU', 'CRLF', 'TELL',
                            'MOVE', 'REMOVE', 'SET', 'SETG', 'PUTP', 'PUTB', 'PUT',
                            'FSET', 'FCLEAR', 'QUIT', 'RESTART', 'CLEAR', 'SCREEN', 'ERASE', 'COLOR',
                            'SPLIT', 'HLIGHT', 'CURSET', 'CURGET', 'DIROUT', 'DIRIN',
                            'BUFOUT', 'DISPLAY', 'THROW', 'COPYT', 'COPY-TABLE'
                        }
                        if op_name in void_ops:
                            # Push 0 to stack: ADD 0 0 -> stack
                            actions_code.extend([0x14, 0x00, 0x00, 0x00])

            # Determine if we need a jump to end (not for last clause or T clause)
            needs_jump_to_end = (i < len(cond.clauses) - 1)

            clause_data.append({
                'is_t_clause': is_t_clause,
                'test_code': test_code,
                'test_size': test_size,
                'actions_code': actions_code,
                'needs_jump_to_end': needs_jump_to_end
            })

        # Second pass: calculate sizes and fix offsets
        # Calculate clause sizes
        for clause in clause_data:
            clause['actions_size'] = len(clause['actions_code'])
            clause['jump_size'] = 3 if clause['needs_jump_to_end'] else 0  # JUMP is 3 bytes
            clause['total_size'] = clause['test_size'] + clause['actions_size'] + clause['jump_size']

        # Calculate cumulative sizes for offset calculations
        total_cond_size = sum(c['total_size'] for c in clause_data)

        # Third pass: generate with proper offsets
        current_pos = 0
        for i, clause in enumerate(clause_data):
            # Fix the condition test branch offset
            if not clause['is_t_clause'] and clause['test_size'] > 0:
                # Branch should jump to next clause if test fails
                # Z-machine branch: target = PC + offset - 2
                # To skip N bytes: offset = N + 2
                bytes_to_skip = clause['actions_size'] + clause['jump_size']
                next_clause_offset = bytes_to_skip + 2  # Add 2 for Z-machine formula

                # Fix the branch byte (last byte of test_code)
                # Preserve bit 7 (branch sense) from original branch byte
                original_branch = clause['test_code'][-1]
                branch_sense = original_branch & 0x80  # Preserve bit 7

                if next_clause_offset < 64:
                    # 1-byte branch form
                    # Bit 7=sense (preserved), bit 6=1 (1-byte), bits 5-0=offset
                    clause['test_code'][-1] = branch_sense | 0x40 | (next_clause_offset & 0x3F)
                else:
                    # 2-byte branch form needed
                    # Bit 7=sense (preserved), bit 6=0 (2-byte)
                    # 14-bit signed offset spans 6 bits of first byte + 8 bits of second
                    clause['test_code'][-1] = branch_sense | ((next_clause_offset >> 8) & 0x3F)
                    # Need to add second byte
                    clause['test_code'].append(next_clause_offset & 0xFF)
                    clause['test_size'] += 1
                    clause['total_size'] += 1

            # Add the test code
            code.extend(clause['test_code'])

            # Add the actions
            code.extend(clause['actions_code'])

            # Add jump to end if needed
            if clause['needs_jump_to_end']:
                # Calculate offset to end of COND
                # Z-machine JUMP: target = PC + offset - 2, where PC is after the 3-byte JUMP
                # To skip remaining_size bytes: offset = remaining_size + 2
                remaining_size = sum(clause_data[j]['total_size'] for j in range(i + 1, len(clause_data)))
                jump_offset = remaining_size + 2

                # JUMP instruction: 0x8C followed by 16-bit signed offset
                code.append(0x8C)
                code.append((jump_offset >> 8) & 0xFF)
                code.append(jump_offset & 0xFF)

            current_pos += clause['total_size']

        return bytes(code)

    def generate_condition_test(self, condition: ASTNode, branch_on_false: bool = False) -> bytes:
        """Generate a condition test that produces a branch instruction.

        Args:
            condition: The condition node to test
            branch_on_false: If True, branch when condition is false (for COND)
                           If False, branch when condition is true

        Returns:
            Bytecode for the test with branch instruction
        """
        code = bytearray()

        # Handle simple number as condition (e.g., from <NOT 0>)
        if isinstance(condition, NumberNode):
            # For a constant, we know the truth value at compile time
            # but we still need to generate valid code with a branch
            # Use JZ to test the constant: 0 = false, non-zero = true
            # JZ 1OP opcode 0x00, short form with small constant: 10 01 0000 = 0x90
            code.append(0x90)  # JZ short form, small constant operand
            code.append(condition.value & 0xFF)
            # Add branch byte
            if branch_on_false:
                # Branch when value is zero (condition is false)
                code.append(0xC0)  # Branch on true (JZ true = value is zero)
            else:
                # Branch when value is non-zero (condition is true)
                code.append(0x40)  # Branch on false (JZ false = value is non-zero)
            return bytes(code)

        # Handle local variable as condition
        if isinstance(condition, LocalVarNode):
            var_num = self.locals.get(condition.name, 0)
            # JZ 1OP opcode 0x00, short form with variable: 10 10 0000 = 0xA0
            code.append(0xA0)  # JZ short form, variable operand
            code.append(var_num)
            if branch_on_false:
                code.append(0xC0)  # Branch when zero (condition false)
            else:
                code.append(0x40)  # Branch when non-zero (condition true)
            return bytes(code)

        # Handle global variable as condition
        if isinstance(condition, GlobalVarNode):
            var_num = self.globals.get(condition.name, 0x10)
            # JZ 1OP opcode 0x00, short form with variable: 10 10 0000 = 0xA0
            code.append(0xA0)  # JZ short form, variable operand
            code.append(var_num)
            if branch_on_false:
                code.append(0xC0)  # Branch when zero (condition false)
            else:
                code.append(0x40)  # Branch when non-zero (condition true)
            return bytes(code)

        # If condition is a form, it might be a comparison or test
        if isinstance(condition, FormNode):
            op_name = condition.operator.value.upper() if isinstance(condition.operator, AtomNode) else ''

            # Handle FSET? (TEST_ATTR)
            if op_name == 'FSET?':
                if len(condition.operands) >= 2:
                    obj = self.get_object_number(condition.operands[0])
                    attr = self.get_operand_value(condition.operands[1])

                    if obj is not None and isinstance(attr, int):
                        code.append(0x4A)  # TEST_ATTR opcode
                        code.append(obj & 0xFF)
                        code.append(attr & 0xFF)
                        # Branch byte will be added below

            # Handle EQUAL? (JE) - variadic: tests if first equals ANY of the rest
            elif op_name in ('=', 'EQUAL?', '==?', '=?'):
                if len(condition.operands) >= 2:
                    # Get first operand (the one we compare against all others)
                    first_op = condition.operands[0]
                    remaining = condition.operands[1:]

                    # If first operand is a nested expression, evaluate it first
                    if isinstance(first_op, FormNode):
                        expr_code = self.generate_form(first_op)
                        code.extend(expr_code)
                        op1_type = 1  # Variable (stack)
                        op1_val = 0   # Stack

                        # If we need multiple JE groups, save stack to temp global
                        if len(remaining) > 3:
                            temp_global = 0x10  # Use global 16 as temp
                            # ADD sp 0 -> temp_global (copy stack to temp)
                            code.append(0xD4)  # VAR form ADD
                            code.append(0x9F)  # Types: var(10), small(01), omit(11), omit(11)
                            code.append(0x00)  # sp
                            code.append(0x00)  # 0
                            code.append(temp_global)  # store to temp global
                            op1_val = temp_global
                    elif isinstance(first_op, CondNode):
                        expr_code = self.generate_cond(first_op)
                        code.extend(expr_code)
                        op1_type = 1
                        op1_val = 0

                        # If we need multiple JE groups, save stack to temp global
                        if len(remaining) > 3:
                            temp_global = 0x10
                            code.append(0xD4)
                            code.append(0x9F)
                            code.append(0x00)
                            code.append(0x00)
                            code.append(temp_global)
                            op1_val = temp_global
                    else:
                        op1_type, op1_val = self._get_operand_type_and_value(first_op)

                    while remaining:
                        # Take up to 3 comparands (JE can do 1 vs up to 3)
                        group = remaining[:3]
                        remaining = remaining[3:]

                        if len(group) == 1:
                            # Check for large constants
                            op2_type, op2_val = self._get_operand_type_and_value(group[0])
                            needs_large1 = (op1_type == 0 and (op1_val < 0 or op1_val > 255))
                            needs_large2 = (op2_type == 0 and (op2_val < 0 or op2_val > 255))

                            if needs_large1 or needs_large2:
                                # Use VAR form JE for large constants
                                code.append(0xC1)  # VAR form JE

                                # Build type byte
                                type1 = 0b00 if needs_large1 else (0b01 if op1_type == 0 else 0b10)
                                type2 = 0b00 if needs_large2 else (0b01 if op2_type == 0 else 0b10)
                                types_byte = (type1 << 6) | (type2 << 4) | 0x0F  # 0x0F = omit, omit
                                code.append(types_byte)

                                # Operand 1
                                if needs_large1:
                                    code.append((op1_val >> 8) & 0xFF)
                                    code.append(op1_val & 0xFF)
                                else:
                                    code.append(op1_val & 0xFF)

                                # Operand 2
                                if needs_large2:
                                    code.append((op2_val >> 8) & 0xFF)
                                    code.append(op2_val & 0xFF)
                                else:
                                    code.append(op2_val & 0xFF)
                            else:
                                # 2OP long form for 2 small operands
                                opcode = 0x01 | (op1_type << 6) | (op2_type << 5)
                                code.append(opcode)
                                code.append(op1_val & 0xFF)
                                code.append(op2_val & 0xFF)
                        else:
                            # VAR form for 3+ operands
                            code.append(0xC1)  # VAR form JE

                            # Build type byte
                            types_and_vals = [(op1_type, op1_val)]
                            for op in group:
                                t, v = self._get_operand_type_and_value(op)
                                types_and_vals.append((t, v))

                            type_byte = 0
                            for i, (t, v) in enumerate(types_and_vals):
                                if i >= 4:
                                    break
                                type_code = 0x01 if t == 0 else 0x02
                                type_byte |= (type_code << (6 - i * 2))
                            for i in range(len(types_and_vals), 4):
                                type_byte |= (0x03 << (6 - i * 2))

                            code.append(type_byte)
                            for t, v in types_and_vals:
                                code.append(v & 0xFF)

                        if remaining:
                            # More to check - branch on TRUE to the code after this COND clause
                            # We'll add a placeholder branch that means "if true, go forward"
                            # For COND, we want: if any match, DON'T branch (take the clause)
                            if branch_on_false:
                                # We want to continue if true (don't branch), skip if all false
                                # So for each JE, branch on TRUE to skip past remaining JEs
                                # Calculate how many bytes the remaining JEs will take
                                bytes_for_remaining = 0
                                temp_remaining = remaining[:]
                                while temp_remaining:
                                    g = temp_remaining[:3]
                                    temp_remaining = temp_remaining[3:]
                                    if len(g) == 1:
                                        bytes_for_remaining += 4  # opcode + 2 operands + branch
                                    else:
                                        bytes_for_remaining += 2 + len(g) + 1 + 1  # opcode + type + operands + branch

                                # Skip remaining JEs to get to actions (if any match succeeds)
                                # The offset is relative to PC after branch byte, so +2
                                skip_offset = bytes_for_remaining + 2
                                if skip_offset < 64:
                                    code.append(0xC0 | (skip_offset & 0x3F))  # Branch true, 1-byte
                                else:
                                    code.append(0x80 | ((skip_offset >> 8) & 0x3F))
                                    code.append(skip_offset & 0xFF)
                            else:
                                # branch_on_false=False means branch when true
                                code.append(0xC0)  # Placeholder
                        # Last group - don't add branch yet, let caller handle it

            # Handle L? (JL)
            elif op_name in ('L?', '<'):
                if len(condition.operands) >= 2:
                    op1_type, op1_val = self._get_operand_type_and_value(condition.operands[0])
                    op2_type, op2_val = self._get_operand_type_and_value(condition.operands[1])

                    # Build JL instruction based on operand types
                    if op1_type == 1 and op2_type == 0 and 0 <= op2_val <= 255:
                        # JL var, small
                        code.append(0x42)  # JL opcode (var, small)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 0 and op2_type == 1 and 0 <= op1_val <= 255:
                        # JL small, var
                        code.append(0x22)  # JL opcode (small, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 1 and op2_type == 1:
                        # JL var, var
                        code.append(0x62)  # JL opcode (var, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 0 and op2_type == 0:
                        # JL small, small
                        if 0 <= op1_val <= 255 and 0 <= op2_val <= 255:
                            code.append(0x02)  # JL opcode (small, small)
                            code.append(op1_val & 0xFF)
                            code.append(op2_val & 0xFF)
                        else:
                            # Use VAR form for large constants
                            code.append(0xC2)  # VAR form JL
                            type_byte = ((0x00 if op1_val > 255 else 0x01) << 6) | \
                                        ((0x00 if op2_val > 255 else 0x01) << 4) | 0x0F
                            code.append(type_byte)
                            if op1_val > 255:
                                code.append((op1_val >> 8) & 0xFF)
                            code.append(op1_val & 0xFF)
                            if op2_val > 255:
                                code.append((op2_val >> 8) & 0xFF)
                            code.append(op2_val & 0xFF)

            # Handle G? (JG)
            elif op_name in ('G?', '>'):
                if len(condition.operands) >= 2:
                    op1_type, op1_val = self._get_operand_type_and_value(condition.operands[0])
                    op2_type, op2_val = self._get_operand_type_and_value(condition.operands[1])

                    # Build JG instruction based on operand types
                    if op1_type == 1 and op2_type == 0 and 0 <= op2_val <= 255:
                        # JG var, small
                        code.append(0x43)  # JG opcode (var, small)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 0 and op2_type == 1 and 0 <= op1_val <= 255:
                        # JG small, var
                        code.append(0x23)  # JG opcode (small, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 1 and op2_type == 1:
                        # JG var, var
                        code.append(0x63)  # JG opcode (var, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 0 and op2_type == 0:
                        # JG small, small
                        if 0 <= op1_val <= 255 and 0 <= op2_val <= 255:
                            code.append(0x03)  # JG opcode (small, small)
                            code.append(op1_val & 0xFF)
                            code.append(op2_val & 0xFF)
                        else:
                            # Use VAR form for large constants
                            code.append(0xC3)  # VAR form JG
                            type_byte = ((0x00 if op1_val > 255 else 0x01) << 6) | \
                                        ((0x00 if op2_val > 255 else 0x01) << 4) | 0x0F
                            code.append(type_byte)
                            if op1_val > 255:
                                code.append((op1_val >> 8) & 0xFF)
                            code.append(op1_val & 0xFF)
                            if op2_val > 255:
                                code.append((op2_val >> 8) & 0xFF)
                            code.append(op2_val & 0xFF)

            # Handle 1? (equals 1)
            elif op_name == '1?':
                if len(condition.operands) >= 1:
                    op_type, op_val = self._get_operand_type_and_value(condition.operands[0])
                    if op_type == 1:  # Variable
                        # JE long form: bit 6=1 (first=var), bit 5=0 (second=small)
                        # 0b01000001 = 0x41
                        code.append(0x41)  # JE long form, variable/small
                        code.append(op_val & 0xFF)
                        code.append(0x01)  # Compare with 1
                    else:  # Constant
                        # JE long form: bit 6=0 (first=small), bit 5=0 (second=small)
                        # 0b00000001 = 0x01
                        code.append(0x01)  # JE long form, small/small
                        code.append(op_val & 0xFF)
                        code.append(0x01)  # Compare with 1

            # Handle 0? / ZERO? (equals 0)
            elif op_name in ('0?', 'ZERO?'):
                if len(condition.operands) >= 1:
                    op_type, op_val = self._get_operand_type_and_value(condition.operands[0])
                    if op_type == 1:  # Variable
                        code.append(0xA0)  # JZ 1OP short form, variable operand
                        code.append(op_val & 0xFF)
                    else:  # Constant
                        # JZ with constant - use JE with 0
                        # JE long form: bit 6=0 (first=small), bit 5=0 (second=small)
                        code.append(0x01)  # JE long form, small/small
                        code.append(op_val & 0xFF)
                        code.append(0x00)  # Compare with 0

            # Handle NOT
            elif op_name == 'NOT':
                if len(condition.operands) != 1:
                    raise ValueError("NOT requires exactly 1 operand")
                # Generate the inner condition and flip the branch sense
                inner_code = self.generate_condition_test(
                    condition.operands[0],
                    branch_on_false=not branch_on_false
                )
                return inner_code

            # Handle G=? (greater or equal) - implemented as NOT(a < b)
            # branch_on_false: branch when a < b (so JL with branch on true)
            # branch_on_true: branch when NOT(a < b) (so JL with branch on false)
            elif op_name in ('G=?', '>='):
                if len(condition.operands) >= 2:
                    op1_type, op1_val = self._get_operand_type_and_value(condition.operands[0])
                    op2_type, op2_val = self._get_operand_type_and_value(condition.operands[1])

                    # Build JL instruction
                    if op1_type == 1 and op2_type == 0 and 0 <= op2_val <= 255:
                        # JL var, small
                        code.append(0x42)  # JL opcode
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 0 and op2_type == 1 and 0 <= op1_val <= 255:
                        # JL small, var
                        code.append(0x22)  # JL opcode (small, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 1 and op2_type == 1:
                        # JL var, var
                        code.append(0x62)  # JL opcode (var, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    else:
                        # Use VAR form for other cases
                        code.append(0xC2)  # VAR form JL
                        type_byte = ((0x01 if op1_type == 0 else 0x02) << 6) | \
                                    ((0x01 if op2_type == 0 else 0x02) << 4) | 0x0F
                        code.append(type_byte)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)

                    # G=? is true when NOT(a < b), so:
                    # - branch_on_false: branch when G=? is false = when a < b = JL is true
                    # - branch_on_true: branch when G=? is true = when NOT(a < b) = JL is false
                    if branch_on_false:
                        code.append(0xC0)  # Branch on true (when a < b)
                    else:
                        code.append(0x40)  # Branch on false (when NOT(a < b))
                    return bytes(code)

            # Handle L=? (less or equal) - implemented as NOT(a > b)
            # branch_on_false: branch when a > b (so JG with branch on true)
            # branch_on_true: branch when NOT(a > b) (so JG with branch on false)
            elif op_name in ('L=?', '<='):
                if len(condition.operands) >= 2:
                    op1_type, op1_val = self._get_operand_type_and_value(condition.operands[0])
                    op2_type, op2_val = self._get_operand_type_and_value(condition.operands[1])

                    # Build JG instruction
                    if op1_type == 1 and op2_type == 0 and 0 <= op2_val <= 255:
                        # JG var, small
                        code.append(0x43)  # JG opcode
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 0 and op2_type == 1 and 0 <= op1_val <= 255:
                        # JG small, var
                        code.append(0x23)  # JG opcode (small, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    elif op1_type == 1 and op2_type == 1:
                        # JG var, var
                        code.append(0x63)  # JG opcode (var, var)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)
                    else:
                        # Use VAR form for other cases
                        code.append(0xC3)  # VAR form JG
                        type_byte = ((0x01 if op1_type == 0 else 0x02) << 6) | \
                                    ((0x01 if op2_type == 0 else 0x02) << 4) | 0x0F
                        code.append(type_byte)
                        code.append(op1_val & 0xFF)
                        code.append(op2_val & 0xFF)

                    # L=? is true when NOT(a > b), so:
                    # - branch_on_false: branch when L=? is false = when a > b = JG is true
                    # - branch_on_true: branch when L=? is true = when NOT(a > b) = JG is false
                    if branch_on_false:
                        code.append(0xC0)  # Branch on true (when a > b)
                    else:
                        code.append(0x40)  # Branch on false (when NOT(a > b))
                    return bytes(code)

            # Handle general routine calls as conditions (e.g., <DESCRIBE-ROOM T>)
            # If we haven't matched any special predicate, treat it as a routine call
            # that returns a value, then test if the return value is non-zero
            elif len(code) == 0:
                # Generate the routine call to get a result on the stack
                call_code = self.generate_statement(condition)
                if call_code:
                    code.extend(call_code)
                    # Now add JZ to test if result is zero
                    # JZ is 1OP opcode 0x00 with variable operand (stack)
                    code.append(0xA0)  # 1OP short form, variable operand
                    code.append(0x00)  # Stack (result of the call)
                    # JZ tests "is value zero?" and branches based on result
                    # For COND branch_on_false: we want to branch when condition is FALSE (zero)
                    # - JZ with bit7=1: branch when value IS zero (condition is FALSE)
                    # - JZ with bit7=0: branch when value is NOT zero (condition is TRUE)
                    # So for branch_on_false, we need bit7=1 (INVERTED from predicates!)
                    if branch_on_false:
                        code.append(0xC0)  # Placeholder: branch when JZ test is true (value is zero)
                    else:
                        code.append(0x40)  # Placeholder: branch when JZ test is false (value is non-zero)
                    return bytes(code)  # Return early, don't add another branch byte

        # Add branch byte
        # Z-machine branch format:
        # Bit 7: 0 = branch on false, 1 = branch on true
        # Bit 6: 0 = 2-byte offset, 1 = 1-byte offset
        # Bits 5-0: offset (if 1-byte) or bits 13-8 of offset (if 2-byte)

        # For COND, we need to jump to next clause, which requires forward jumps
        # For now, use placeholder - will be fixed up by caller
        if branch_on_false:
            # Branch on false - bit 7 = 0
            code.append(0x40)  # Placeholder: 1-byte form, offset 0
        else:
            # Branch on true - bit 7 = 1
            code.append(0xC0)  # Placeholder: 1-byte form, offset 0

        return bytes(code)

    # ===== REPEAT Loop =====

    def generate_repeat(self, repeat: 'RepeatNode') -> bytes:
        """Generate REPEAT loop with proper branching.

        REPEAT generates:
        1. Initialize loop variables (if any)
        2. LOOP_START label
        3. Body statements (with AGAIN support)
        4. Jump back to LOOP_START
        5. LOOP_END label (for RETURN to exit)

        Z-machine doesn't have explicit loop constructs, so we use:
        - Forward jumps for loop exits (RETURN)
        - Backward jumps to loop start (AGAIN)
        """
        from ..parser.ast_nodes import RepeatNode
        code = bytearray()

        # Track variables bound in this REPEAT for unused warning
        repeat_bound_vars = set()
        repeat_side_effect_vars = set()

        # Initialize loop variable bindings
        for var_name, init_value in repeat.bindings:
            # Create local variable if not already in locals
            if var_name not in self.locals:
                var_num = len(self.locals) + 1
                self.locals[var_name] = var_num
                repeat_bound_vars.add(var_name)  # Track for unused warning
                # Check for side-effect initializer
                if isinstance(init_value, FormNode):
                    repeat_side_effect_vars.add(var_name)

            # Generate assignment
            var_num = self.locals[var_name]
            value = self.get_operand_value(init_value)

            if isinstance(value, int) and 0 <= value <= 255:
                # STORE variable small_constant
                code.append(0x0D)  # STORE opcode 13 (long form, small/small: 00 0 0 1101)
                code.append(var_num & 0xFF)
                code.append(value & 0xFF)

        # Mark loop start position (after initialization)
        loop_start_pos = len(code)

        # Push loop context for AGAIN support
        # Store the code buffer reference and start position
        loop_context = {
            'start_offset': loop_start_pos,
            'code_buffer': code,  # Reference to the code being built
            'loop_start': loop_start_pos,  # For compatibility with gen_again
            'loop_type': 'REPEAT',
            'again_patches': [],   # List of positions that need patching
            'again_placeholders': [],  # For compatibility
        }
        self.loop_stack.append(loop_context)

        # Push block context onto block_stack (for RETURN support)
        block_ctx = {
            'code_buffer': code,
            'return_placeholders': [],  # Positions of RETURN jumps to patch
            'block_type': 'REPEAT',
            'result_var': 0,  # Stack (SP) - result is pushed onto stack
        }
        self.block_stack.append(block_ctx)

        # Generate body statements
        for stmt in repeat.body:
            code.extend(self.generate_statement(stmt))

        # Generate jump back to loop start
        # JUMP instruction: opcode + 2 offset bytes
        # Offset is relative to PC after reading the branch bytes
        # PC after JUMP = current_pos + 3 (for JUMP opcode + 2 offset bytes)
        # Target = loop_start_pos
        # Offset = target - PC_after = loop_start_pos - (current_pos + 3)
        #        = loop_start_pos - len(code) - 3
        current_pos = len(code)
        jump_offset = loop_start_pos - (current_pos + 3)

        # JUMP uses signed 16-bit offset (not branch format)
        # Encode as signed 16-bit value
        if jump_offset < 0:
            jump_offset_unsigned = (1 << 16) + jump_offset  # Two's complement
        else:
            jump_offset_unsigned = jump_offset

        code.append(0x8C)  # JUMP opcode (0OP:0x0C)
        code.append((jump_offset_unsigned >> 8) & 0xFF)  # High byte
        code.append(jump_offset_unsigned & 0xFF)  # Low byte

        # Exit point is right after the backward jump (this is where RETURN jumps to)
        exit_point = len(code)

        # Patch all RETURN placeholders (0x8C 0xFF 0xBB -> jump to exit_point)
        # Z-machine JUMP formula: Target = PC + Offset - 2, where PC is after instruction
        # So: Offset = Target - PC + 2 = exit_point - (i + 3) + 2
        i = 0
        while i < len(code) - 2:
            if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xBB:
                # Found RETURN placeholder at position i
                return_offset = exit_point - (i + 3) + 2  # +2 for Z-machine JUMP formula
                if return_offset < 0:
                    return_offset_unsigned = (1 << 16) + return_offset
                else:
                    return_offset_unsigned = return_offset
                code[i+1] = (return_offset_unsigned >> 8) & 0xFF
                code[i+2] = return_offset_unsigned & 0xFF
            i += 1

        # Patch all AGAIN placeholders (0x8C 0xFF 0xAA -> actual jump)
        # Z-machine JUMP formula: Target = PC + Offset - 2, where PC is after instruction
        # So: Offset = Target - PC + 2 = loop_start_pos - (i + 3) + 2
        i = 0
        while i < len(code) - 2:
            if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xAA:
                # Found AGAIN placeholder at position i
                again_offset = loop_start_pos - (i + 3) + 2  # +2 for Z-machine JUMP formula
                if again_offset < 0:
                    again_offset_unsigned = (1 << 16) + again_offset
                else:
                    again_offset_unsigned = again_offset
                code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                code[i+2] = again_offset_unsigned & 0xFF
            i += 1

        # Check for unused REPEAT locals (ZIL0210)
        if hasattr(self, 'used_locals') and self.compiler is not None:
            for var_name in repeat_bound_vars:
                if (var_name not in self.used_locals and
                        var_name not in repeat_side_effect_vars):
                    self.compiler.warn("ZIL0210", f"local variable '{var_name}' is never used")

        # Pop block context
        self.block_stack.pop()

        # Pop loop context
        self.loop_stack.pop()

        return bytes(code)

    # ===== Helper Methods =====

    def get_operand_value(self, node: ASTNode) -> Any:
        """Get the value of an operand (constant or variable)."""
        if isinstance(node, NumberNode):
            return node.value
        elif isinstance(node, AtomNode):
            # Check for ZIL character literals: !\c, !\", !\\, etc.
            # Format: !<char> or !\<char> where the char is the ASCII value
            if node.value.startswith('!') and len(node.value) >= 2:
                char_part = node.value[1:]  # Everything after !
                if char_part.startswith('\\') and len(char_part) >= 2:
                    # !\c format - return ASCII value of character after backslash
                    return ord(char_part[1])
                elif len(char_part) == 1:
                    # !c format - return ASCII value of single character
                    return ord(char_part[0])
            if node.value in self.constants:
                return self.constants[node.value]
            elif node.value in self.globals:
                return self.globals[node.value]
            elif node.value in self.locals:
                return self.locals[node.value]
            elif node.value in self.objects:
                # Object reference (e.g., <GLOBAL HERE CAT>)
                return self.objects[node.value]
            # Check for builtin constants
            elif node.value == 'T':
                return 1
            elif node.value == '<>':
                return 0
        elif isinstance(node, LocalVarNode):
            return self.locals.get(node.name, 1)
        elif isinstance(node, GlobalVarNode):
            if node.name in self.globals:
                return self.globals[node.name]
            elif node.name in self.objects:
                return self.objects[node.name]
            elif node.name in self.constants:
                return self.constants[node.name]
            elif hasattr(self, '_routine_names') and node.name in self._routine_names:
                # Routine address - return placeholder
                placeholder_idx = self._next_placeholder_index
                self._routine_placeholders[placeholder_idx] = node.name
                self._next_placeholder_index += 1
                return 0xFD00 | placeholder_idx
            return 0x10  # Default
        elif isinstance(node, TableNode):
            # Table literal - store table and return placeholder index
            # The actual address will be resolved during assembly
            table_index = self._add_table(node)
            # Return a marker value that will be patched later
            # Use high byte 0xFF to indicate table reference
            return 0xFF00 | table_index
        return None

    def get_variable_number(self, node: ASTNode) -> int:
        """Get variable number from node."""
        if isinstance(node, AtomNode):
            if node.value in self.globals:
                return self.globals[node.value]
            elif node.value in self.locals:
                return self.locals[node.value]
        elif isinstance(node, LocalVarNode):
            return self.locals.get(node.name, 1)
        elif isinstance(node, GlobalVarNode):
            return self.globals.get(node.name, 0x10)
        return 0

    def get_object_number(self, node: ASTNode) -> Optional[int]:
        """Get object number from node."""
        if isinstance(node, AtomNode):
            return self.objects.get(node.value)
        elif isinstance(node, NumberNode):
            return node.value
        return None

    def build_globals_data(self) -> bytes:
        """Build the globals table data with initial values.

        Returns:
            480 bytes (240 words) of globals data with initialized values.
        """
        # Globals table is 240 words (480 bytes)
        # Global N is at offset (N - 0x10) * 2
        data = bytearray(480)

        for name, var_num in self.globals.items():
            if var_num >= 0x10 and var_num < 0x100:
                offset = (var_num - 0x10) * 2
                if offset < 480:
                    value = self.global_values.get(name, 0)
                    # Store as big-endian word
                    data[offset] = (value >> 8) & 0xFF
                    data[offset + 1] = value & 0xFF

        return bytes(data)

    def needs_extension_table(self) -> bool:
        """Check if an extension table is needed (V5+ only)."""
        return self.version >= 5 and self._max_extension_word > 0

    def build_extension_table(self) -> bytes:
        """Build the header extension table (V5+).

        The extension table format is:
        - Word 0: Number of extension words following
        - Word 1..N: Extension data (mouse coords, flags, etc.)

        Returns:
            Extension table bytes, or empty bytes if not needed.
        """
        if not self.needs_extension_table():
            return b''

        # Create table with enough words for all used extension fields
        # +1 because word 0 is the count
        num_words = self._max_extension_word
        table = bytearray((num_words + 1) * 2)

        # Word 0: count of extension words
        table[0] = (num_words >> 8) & 0xFF
        table[1] = num_words & 0xFF

        # Remaining words are initialized to 0
        # (mouse coords, flags, etc. - default values)

        return bytes(table)

    # ===== Routine Calls =====

    def gen_routine_call(self, routine_name: str, operands: List[ASTNode]) -> bytes:
        """Generate routine call (CALL or CALL_VS)."""
        # Check if this is a constant with value 0 (FALSE)
        # Calling FALSE evaluates args for side effects and returns 0
        if routine_name in self.constants and self.constants[routine_name] == 0:
            code = bytearray()
            # Evaluate all arguments for side effects
            for op in operands:
                if isinstance(op, FormNode):
                    # Generate code for side effects
                    # The form will push a result - we need to pop it
                    arg_code = self.generate_form(op)
                    code.extend(arg_code)
                    # Pop the result using STOREW to global 0 (throwaway)
                    # Actually, easier: just use the result as store target
                    # Many forms already store to stack, so pop with 0x09 (POP)
                    # POP in 1OP form: 0x89 (short form) with variable operand type
                    # Or we can just skip the pop if the form doesn't push
                    # Better approach: use ADD with store to nowhere
                    # Actually simplest: just call CALL with address 0 which is defined Z-machine behavior
                    pass  # Many forms push to stack, but we can't easily pop
            # For calling FALSE, the Z-machine defines that CALL with address 0 returns FALSE
            # So we can just emit a CALL with address 0
            # CALL 0 -> sp  (VAR form opcode 0)
            code.append(0xE0)  # VAR form CALL_VS
            code.append(0x3F)  # Type: large const, omit, omit, omit
            code.append(0x00)  # Address high byte = 0
            code.append(0x00)  # Address low byte = 0
            code.append(0x00)  # Store result to stack
            return bytes(code)

        # Validate argument count if we have info about this routine
        num_args = len(operands)
        if hasattr(self, '_routine_param_info') and routine_name in self._routine_param_info:
            num_required, num_optional = self._routine_param_info[routine_name]
            max_allowed = num_required + num_optional
            if num_args > max_allowed:
                raise ValueError(
                    f"Call to {routine_name} has {num_args} arguments, "
                    f"but routine only accepts {max_allowed} ({num_required} required, {num_optional} optional)"
                )

        code = bytearray()

        # CALL is VAR opcode 0x00 (V1-4) / CALL_VS (V4+)
        # Routine address is a large constant (16-bit packed address)

        # Encode as variable form
        code.append(0xE0)  # VAR form, opcode 0x00

        # Build type byte - first operand is large constant (0x00) for routine address
        types = [0x00]  # Large constant for routine address

        for op in operands[:3]:
            op_type, op_val = self._get_operand_type_and_value(op)
            if op_type == 1:  # Variable
                types.append(0x02)
            else:  # Constant
                if isinstance(op_val, int) and op_val <= 255:
                    types.append(0x01)  # Small constant
                else:
                    types.append(0x00)  # Large constant

        # Pad with "omitted" (0x03)
        while len(types) < 4:
            types.append(0x03)

        # Pack type byte (each type is 2 bits)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        # Use placeholder encoding for routine address
        # Format: marker byte (0xFD) + 2-byte placeholder index
        # The placeholder index maps to the routine name for later resolution
        placeholder_idx = self._next_placeholder_index
        self._routine_placeholders[placeholder_idx] = routine_name
        self._next_placeholder_index += 1

        # Encode placeholder: 0xFD followed by index as 16-bit big-endian
        # Note: We only need 2 bytes for the address, so use high byte of index
        # Actually, since this needs to be a valid packed address slot (2 bytes),
        # we'll use a range that's unlikely to be a real address: 0xFD00-0xFDFF
        code.append(0xFD)  # Marker high byte
        code.append(placeholder_idx & 0xFF)  # Index as low byte

        # Add remaining operand values
        for i, op in enumerate(operands[:3]):
            op_type, op_val = self._get_operand_type_and_value(op)
            if types[i + 1] == 0x00:  # Large constant
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
            elif types[i + 1] != 0x03:  # Not omitted
                code.append(op_val & 0xFF)

        # Store result to stack
        code.append(0x00)

        return bytes(code)

    # ===== Memory Operations =====

    def gen_loadw(self, operands: List[ASTNode]) -> bytes:
        """Generate LOADW (load word from array)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # LOADW is 2OP opcode 0x0F
        opcode = 0x0F | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_loadb(self, operands: List[ASTNode]) -> bytes:
        """Generate LOADB (load byte from array)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # LOADB is 2OP opcode 0x10 (LOADW is 0x0F)
        opcode = 0x10 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_storew(self, operands: List[ASTNode]) -> bytes:
        """Generate STOREW (store word to array)."""
        if len(operands) < 3:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREW is VAR opcode 0x01
        code.append(0xE1)  # VAR form, opcode 0x01

        # Build type byte
        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # Omitted

        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_storeb(self, operands: List[ASTNode]) -> bytes:
        """Generate STOREB (store byte to array)."""
        if len(operands) < 3:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREB is VAR opcode 0x02
        code.append(0xE2)  # VAR form, opcode 0x02

        # Build type byte
        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x01 if op3_type == 0 else 0x02)
        types.append(0x03)  # Omitted

        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    # ===== Table Operations (ZIL high-level) =====

    def gen_get(self, operands: List[ASTNode]) -> bytes:
        """Generate GET (table word access).

        <GET table index> reads word from table[index].
        Uses Z-machine LOADW instruction.

        If any operand is a FormNode, generate that form's code first
        (which puts result on stack) then use stack as the operand.
        """
        if len(operands) != 2:
            raise ValueError("GET requires exactly 2 operands")

        code = bytearray()

        # Process each operand - FormNodes need code generation first
        op_types = []
        op_vals = []

        for op in operands:
            if isinstance(op, FormNode):
                # Generate code for nested form - result goes to stack
                inner_code = self.generate_form(op)
                code.extend(inner_code)
                # Use stack (variable 0) as the operand
                op_types.append(1)  # Variable
                op_vals.append(0)   # Stack
            else:
                op_type, op_val = self._get_operand_type_and_value(op)
                op_types.append(op_type)
                op_vals.append(op_val)

        # LOADW is 2OP opcode 0x0F
        opcode = 0x0F | (op_types[0] << 6) | (op_types[1] << 5)
        code.append(opcode)
        code.append(op_vals[0] & 0xFF)
        code.append(op_vals[1] & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_put(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT (table word write).

        <PUT table index value> writes value to table[index].
        Uses Z-machine STOREW instruction.

        If any operand is a FormNode, generate that form's code first
        (which puts result on stack) then use stack as the operand.
        """
        if len(operands) != 3:
            raise ValueError("PUT requires exactly 3 operands")

        code = bytearray()

        # Process each operand - FormNodes need code generation first
        # Use _get_operand_type_and_value_ext which returns:
        # 0 = large constant, 1 = small constant, 2 = variable
        op_types = []
        op_vals = []

        for i, op in enumerate(operands[:3]):
            if isinstance(op, FormNode):
                # Generate code for nested form - result goes to stack
                inner_code = self.generate_form(op)
                code.extend(inner_code)
                # Use stack (variable 0) as the operand
                op_types.append(2)  # variable type
                op_vals.append(0x00)  # stack
            else:
                op_type, op_val = self._get_operand_type_and_value_ext(op)
                op_types.append(op_type)
                op_vals.append(op_val)

        # STOREW is VAR opcode 0x01
        code.append(0xE1)  # VAR form, opcode 0x01
        # Type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omitted
        # _get_operand_type_and_value_ext returns: 0=large, 1=small, 2=variable
        # Z-machine type encoding: 00=large, 01=small, 10=var, 11=omitted
        # Map: 0->00, 1->01, 2->10
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | 0x03
        code.append(type_byte)

        # Append operand bytes based on type
        for i in range(3):
            if op_types[i] == 0:  # Large constant - 2 bytes
                code.append((op_vals[i] >> 8) & 0xFF)
                code.append(op_vals[i] & 0xFF)
            else:  # Small constant or variable - 1 byte
                code.append(op_vals[i] & 0xFF)

        return bytes(code)

    def gen_getb(self, operands: List[ASTNode]) -> bytes:
        """Generate GETB (table byte access).

        <GETB table index> reads byte from table[index].
        Uses Z-machine LOADB instruction.

        If any operand is a FormNode, generate that form's code first
        (which puts result on stack) then use stack as the operand.
        """
        if len(operands) != 2:
            raise ValueError("GETB requires exactly 2 operands")

        code = bytearray()

        # Process operands - FormNodes need code generation first
        op_types = []
        op_vals = []

        for op in operands:
            if isinstance(op, FormNode):
                # Generate code for nested form - result goes to stack
                inner_code = self.generate_form(op)
                code.extend(inner_code)
                # Use stack (variable 0) as the operand
                op_types.append(1)  # Variable
                op_vals.append(0)   # Stack
            else:
                op_type, op_val = self._get_operand_type_and_value(op)
                op_types.append(op_type)
                op_vals.append(op_val)

        op1_type, op1_val = op_types[0], op_vals[0]
        op2_type, op2_val = op_types[1], op_vals[1]

        # LOADB is 2OP opcode 0x10 (LOADW is 0x0F)
        opcode = 0x10 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_putb(self, operands: List[ASTNode]) -> bytes:
        """Generate PUTB (table byte write).

        <PUTB table index value> writes byte value to table[index].
        Uses Z-machine STOREB instruction.
        """
        if len(operands) != 3:
            raise ValueError("PUTB requires exactly 3 operands")

        code = bytearray()

        # Process each operand using extended type function
        # Returns: 0=large, 1=small, 2=variable
        op_types = []
        op_vals = []
        for op in operands[:3]:
            if isinstance(op, FormNode):
                inner_code = self.generate_form(op)
                code.extend(inner_code)
                op_types.append(2)  # variable
                op_vals.append(0x00)  # stack
            else:
                op_type, op_val = self._get_operand_type_and_value_ext(op)
                op_types.append(op_type)
                op_vals.append(op_val)

        # STOREB is VAR opcode 0x02
        code.append(0xE2)  # VAR form, opcode 0x02
        # Type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omitted
        # _get_operand_type_and_value_ext returns: 0=large, 1=small, 2=variable
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | 0x03
        code.append(type_byte)

        # Append operand bytes based on type
        for i in range(3):
            if op_types[i] == 0:  # Large constant - 2 bytes
                code.append((op_vals[i] >> 8) & 0xFF)
                code.append(op_vals[i] & 0xFF)
            else:  # Small constant or variable - 1 byte
                code.append(op_vals[i] & 0xFF)

        return bytes(code)

    def gen_length(self, operands: List[ASTNode]) -> bytes:
        """Generate LENGTH (get table/string length).

        <LENGTH table> returns the size stored at offset 0 of the table.
        ZIL tables store their length in the first word.
        Uses LOADW to read table[0].
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # LOADW is 2OP opcode 0x0F - read length from table[0]
        opcode = 0x0F | (op_type << 6) | (0 << 5)  # index 0 is constant
        code.append(opcode)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Index 0 (length stored at offset 0)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_nth(self, operands: List[ASTNode]) -> bytes:
        """Generate NTH (get Nth element from table, 0-based).

        <NTH table index> returns table[index] where index is 0-based.
        This is unlike GET which is 1-based.
        Uses LOADW instruction directly.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # LOADW is 2OP opcode 0x0F
        opcode = 0x0F | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Stack Operations =====

    def gen_push(self, operands: List[ASTNode]) -> bytes:
        """Generate PUSH (push value to stack)."""
        if len(operands) != 1:
            raise ValueError("PUSH requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # PUSH is VAR opcode 0x08
        code.append(0xE8)  # VAR form, opcode 0x08
        # Type byte: bits 7-6=first, 5-4=second, 3-2=third, 1-0=fourth
        # 00=large const, 01=small const, 10=variable, 11=omitted
        if op_type == 1:  # Variable
            code.append(0xBF)  # Type byte: variable, rest omitted (10 11 11 11)
            code.append(op_val & 0xFF)
        elif op_val < 0 or op_val > 255:  # Large constant
            code.append(0x3F)  # Type byte: large constant, rest omitted (00 11 11 11)
            val = op_val & 0xFFFF
            code.append((val >> 8) & 0xFF)
            code.append(val & 0xFF)
        else:  # Small constant
            code.append(0x7F)  # Type byte: small constant, rest omitted (01 11 11 11)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_pull(self, operands: List[ASTNode]) -> bytes:
        """Generate PULL (pop from stack) - V1-5 only."""
        if len(operands) != 1:
            raise ValueError("PULL requires exactly 1 operand")

        code = bytearray()
        var_num = self.get_variable_number(operands[0])

        # PULL is VAR opcode 0x09 (V1-5)
        # PULL takes a variable NUMBER as a small/large constant operand
        if self.version <= 5:
            code.append(0xE9)  # VAR form, opcode 0x09
            if var_num <= 255:
                code.append(0x7F)  # Type byte: small constant, omit, omit, omit
                code.append(var_num)
            else:
                code.append(0x3F)  # Type byte: large constant, omit, omit, omit
                code.append((var_num >> 8) & 0xFF)
                code.append(var_num & 0xFF)

        return bytes(code)

    def gen_pop(self, operands: List[ASTNode]) -> bytes:
        """Generate POP (pop from stack and return value).

        <POP> returns the value popped from the system stack.
        <POP user-stack> (V6) pops from user stack using EXT:21.

        Implemented as:
        - V1-V6 with 0 operands: Load from variable 0 (stack) then push result
        - V6 with 1 operand: EXT:21 (pop_stack) with count=1
        """
        code = bytearray()

        if len(operands) == 0:
            # Pop from system stack - the value is already on stack.
            # For value-returning context (e.g., <PRINTN <POP>>), the caller
            # will read from variable 0 (stack). We should NOT generate any code
            # since generating PULL to variable 0 is a no-op that doesn't consume
            # the value. Just return empty bytes and let the caller use the stack.
            return bytes(code)
        elif len(operands) == 1 and self.version >= 6:
            # V6: Pop from user stack using EXT:21 (pop_stack)
            # pop_stack has 2 operands: items (count) and stack
            # We pop 1 item and return it
            code.append(0xBE)  # EXT marker
            code.append(0x15)  # POP_STACK (EXT:21 = 0x15)

            # Get stack operand
            stack_type, stack_val = self._get_operand_type_and_value(operands[0])

            # Type byte: small constant 1 for count, then stack type
            if stack_type == 0:  # Constant
                type2 = 0x01 if stack_val <= 255 else 0x00
            else:
                type2 = 0x02  # Variable

            # Count is always 1 (small constant)
            type_byte = (0x01 << 6) | (type2 << 4) | 0x0F
            code.append(type_byte)

            # Operands: count=1, then stack
            code.append(0x01)  # Count = 1

            if type2 == 0x00:  # Large constant
                code.append((stack_val >> 8) & 0xFF)
                code.append(stack_val & 0xFF)
            else:
                code.append(stack_val & 0xFF)

            # Store result to stack (variable 0)
            code.append(0x00)

            return bytes(code)
        else:
            raise ValueError(f"POP takes 0 operands (or 1 in V6), got {len(operands)}")

    def gen_xpush(self, operands: List[ASTNode]) -> bytes:
        """Generate XPUSH (V6 push to user stack with branch).

        <XPUSH value stack> pushes value onto user stack.
        Branches if successful (stack not full).
        V6 only.

        Args:
            operands[0]: Value to push
            operands[1]: Stack address

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            raise ValueError("XPUSH requires V6")
        if len(operands) != 2:
            raise ValueError("XPUSH requires exactly 2 operands")

        code = bytearray()

        # XPUSH is EXT opcode 0x18 (PUSH_STACK)
        code.append(0xBE)  # EXT marker
        code.append(0x18)  # PUSH_STACK

        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Type byte
        type1 = 0x01 if op1_type == 0 else 0x02
        type2 = 0x01 if op2_type == 0 else 0x02
        type_byte = (type1 << 6) | (type2 << 4) | 0x0F
        code.append(type_byte)

        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_push_stack(self, operands: List[ASTNode]) -> bytes:
        """Generate PUSH_STACK (V6 - push to user stack).

        <PUSH_STACK value stack> pushes value onto specified user stack.
        Optional branch on success/failure.
        V6 only.

        Args:
            operands[0]: Value to push
            operands[1]: Stack address

        Returns:
            bytes: Z-machine code (PUSH_STACK EXT opcode)
        """
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()

        # PUSH_STACK is EXT opcode 0x18
        code.append(0xBE)  # EXT opcode marker
        code.append(0x18)  # PUSH_STACK

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(2):
            t, v = self._get_operand_type_and_value(operands[i])
            if t == 0:  # Constant
                op_types.append(0x01 if v <= 255 else 0x00)
            else:
                op_types.append(0x02)
            op_vals.append(v)

        # Build type byte
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | 0x0F
        code.append(type_byte)

        # Output operands
        for t, v in zip(op_types, op_vals):
            if t == 0x00:  # Large constant
                code.append((v >> 8) & 0xFF)
                code.append(v & 0xFF)
            else:
                code.append(v & 0xFF)

        # Branch byte (branch on success)
        code.append(0x40)

        return bytes(code)

    def gen_pop_stack(self, operands: List[ASTNode]) -> bytes:
        """Generate POP_STACK (V6 - pop from user stack).

        <POP_STACK items stack> pops items from specified user stack.
        V6 only.

        Args:
            operands[0]: Number of items to pop
            operands[1]: Stack address

        Returns:
            bytes: Z-machine code (POP_STACK EXT opcode)
        """
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()

        # POP_STACK is EXT opcode 0x15
        code.append(0xBE)  # EXT opcode marker
        code.append(0x15)  # POP_STACK

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(2):
            t, v = self._get_operand_type_and_value(operands[i])
            if t == 0:  # Constant
                op_types.append(0x01 if v <= 255 else 0x00)
            else:
                op_types.append(0x02)
            op_vals.append(v)

        # Build type byte
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | 0x0F
        code.append(type_byte)

        # Output operands
        for t, v in zip(op_types, op_vals):
            if t == 0x00:  # Large constant
                code.append((v >> 8) & 0xFF)
                code.append(v & 0xFF)
            else:
                code.append(v & 0xFF)

        return bytes(code)

    # ===== Object Tree Traversal =====

    def gen_get_child(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_CHILD (get first child of object)."""
        if len(operands) != 1:
            raise ValueError("FIRST? requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_CHILD is 1OP opcode 0x02 (store + branch)
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        # 0x92 = small constant, 0xA2 = variable
        # _get_operand_type_and_value returns: 0=constant, 1=variable
        if op_type == 1:  # Variable
            code.append(0xA2)
        else:  # Constant (small)
            code.append(0x92)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack
        # Branch byte: 0xC2 = branch on true, short offset, offset 2 (next instruction)
        # This makes the branch a no-op - we just want the stored value
        code.append(0xC2)

        return bytes(code)

    def gen_get_sibling(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_SIBLING (get next sibling of object)."""
        if len(operands) != 1:
            raise ValueError("NEXT? requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_SIBLING is 1OP opcode 0x01 (store + branch)
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        # 0x91 = small constant, 0xA1 = variable
        if op_type == 1:  # Variable
            code.append(0xA1)
        else:  # Constant (small)
            code.append(0x91)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack
        # Branch byte: 0xC2 = branch on true, short offset, offset 2 (next instruction)
        # This makes the branch a no-op - we just want the stored value
        code.append(0xC2)

        return bytes(code)

    def gen_get_parent(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PARENT (get parent of object)."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_PARENT is 1OP opcode 0x03 (store only)
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        # 0x93 = small constant, 0xA3 = variable
        if op_type == 1:  # Variable
            code.append(0xA3)
        else:  # Constant (small)
            code.append(0x93)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_empty(self, operands: List[ASTNode]) -> bytes:
        """Generate EMPTY? (test if object has no children).

        <EMPTY? obj> tests if an object has no children.
        Returns true if GET_CHILD returns 0.

        Args:
            operands[0]: Object to test

        Returns:
            bytes: Z-machine code (GET_CHILD + JZ)
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_CHILD stores child object (0 if none)
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        # 0x92 = small constant, 0xA2 = variable
        if op_type == 1:  # Variable
            code.append(0xA2)
        else:  # Constant (small)
            code.append(0x92)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack
        # Don't include branch byte - caller handles branching

        return bytes(code)

    def gen_in(self, operands: List[ASTNode]) -> bytes:
        """Generate IN? (test if obj1 is directly in obj2).

        <IN? obj1 obj2> tests if obj1's parent is obj2.
        Pushes 1 if true, 0 if false to stack.
        """
        if len(operands) != 2:
            raise ValueError("IN? requires exactly 2 operands")

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Get parent of obj1
        # GET_PARENT is 1OP opcode 0x03 (store instruction)
        # 1OP short form: 10 tt nnnn where tt: 00=large, 01=small, 10=variable
        if op1_type == 0:  # Constant (small)
            code.append(0x93)  # Short 1OP, small constant
        else:  # Variable
            code.append(0xA3)  # Short 1OP, variable
        code.append(op1_val & 0xFF)
        code.append(0x00)  # Store to stack

        # Compare with obj2 using JE (jump if equal)
        # JE is 2OP opcode 0x01 (branch instruction)
        # First operand is stack (variable 0x00), second is obj2
        opcode = 0x01 | (1 << 6) | (op2_type << 5)  # Stack is always variable
        code.append(opcode)
        code.append(0x00)  # Stack (result of GET_PARENT)
        code.append(op2_val & 0xFF)
        # Branch: if equal, skip to true case (offset 9 bytes forward)
        code.append(0xC9)

        # FALSE case: ADD 0 0 -> stack (push 0)
        code.append(0x14)  # ADD 2OP small small
        code.append(0x00)
        code.append(0x00)
        code.append(0x00)  # Store to stack

        # JUMP past true case (offset 6)
        code.append(0x8C)  # JUMP
        code.append(0x00)
        code.append(0x06)  # offset 6

        # TRUE case: ADD 0 1 -> stack (push 1)
        code.append(0x14)
        code.append(0x00)
        code.append(0x01)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Utilities and Built-ins =====

    def gen_random(self, operands: List[ASTNode]) -> bytes:
        """Generate RANDOM (random number generator)."""
        if len(operands) != 1:
            raise ValueError("RANDOM requires exactly 1 operand")

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # RANDOM is VAR opcode 0x07
        code.append(0xE7)  # VAR form, opcode 0x07
        type_byte = 0x01 if op_type == 0 else 0x02  # small const or var
        code.append((type_byte << 6) | 0x3F)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_restart(self) -> bytes:
        """Generate RESTART (restart game)."""
        return bytes([0xB7])  # Short 0OP, opcode 0x07

    def gen_save(self, operands: List[ASTNode] = None) -> bytes:
        """Generate SAVE (save game).

        V3-V4: 0 operands, Branch/Store instruction
        V5+: 0 or 3 operands (table, bytes, name)
        """
        if operands is None:
            operands = []

        if self.version < 5:
            if operands:
                raise ValueError("SAVE takes no operands in V3/V4")
        else:
            if len(operands) not in (0, 3):
                raise ValueError("SAVE requires 0 or 3 operands in V5+")

        code = bytearray()
        code.append(0xB5)  # Short 0OP, opcode 0x05

        if self.version <= 3:
            # Branch instruction in V1-3
            code.append(0x40)  # Branch byte
        elif self.version == 4:
            # V4: Store instruction (returns result)
            code.append(0x00)  # Store to stack (SP)

        return bytes(code)

    def gen_restore(self, operands: List[ASTNode] = None) -> bytes:
        """Generate RESTORE (restore game).

        V3-V4: 0 operands, Branch/Store instruction
        V5+: 0 or 3 operands (table, bytes, name)
        """
        if operands is None:
            operands = []

        if self.version < 5:
            if operands:
                raise ValueError("RESTORE takes no operands in V3/V4")
        else:
            if len(operands) not in (0, 3):
                raise ValueError("RESTORE requires 0 or 3 operands in V5+")

        code = bytearray()
        code.append(0xB6)  # Short 0OP, opcode 0x06

        if self.version <= 3:
            # Branch instruction in V1-3
            code.append(0x40)  # Branch byte
        elif self.version == 4:
            # V4: Store instruction (returns result)
            code.append(0x00)  # Store to stack (SP)

        return bytes(code)

    def gen_verify(self) -> bytes:
        """Generate VERIFY (verify game file) - returns 1 if checksum valid, 0 otherwise.

        VERIFY is a branch instruction. To use as a value:
        1. VERIFY ?~(+offset) - branch if verify fails (to push 0)
        2. Push 1 (true) and jump to end
        3. Push 0 (false)
        """
        code = bytearray()

        # Layout:
        # 0-1: VERIFY + branch (branch to offset 9 if false/fails)
        # 2-5: ADD 0 1 -> stack (push 1, verify succeeded)
        # 6-8: JUMP to offset 13 (skip push 0)
        # 9-12: ADD 0 0 -> stack (push 0, verify failed)
        # 13: next instruction

        # VERIFY with branch offset to "push 0" if verify fails
        # Branch if verify FAILS (bit7=0), to go to "push 0"
        # Layout: 0-1=VERIFY+branch, 2-5=ADD(push 1), 6-8=JUMP, 9-12=ADD(push 0)
        # After branch byte, PC is at offset 2. Target is offset 9.
        # Branch offset = 9 (target), encoded as: offset = 9, byte = 0x40 | 9 = 0x49
        code.append(0xBD)  # VERIFY (0OP:13)
        code.append(0x49)  # Branch byte: bit7=0 (branch on false), bit6=1 (short), bits5-0=9

        # Push 1 (verify succeeded) - use ADD 0 1 -> stack
        code.append(0x14)  # ADD
        code.append(0x00)  # operand 1: 0
        code.append(0x01)  # operand 2: 1
        code.append(0x00)  # store to stack

        # JUMP over push 0 (skip 4 bytes: the ADD 0 0 -> stack)
        # JUMP is 1OP:12, short form with large constant: 0x8C
        # JUMP adds offset to address of operand (not opcode)
        # Opcode at offset 6, operand at offset 7
        # Target is offset 13, so offset = 13 - 7 = 6
        code.append(0x8C)  # JUMP with large constant
        code.append(0x00)  # High byte of offset
        code.append(0x06)  # Low byte of offset (6)

        # Push 0 (verify failed) - use ADD 0 0 -> stack
        code.append(0x14)  # ADD
        code.append(0x00)  # operand 1: 0
        code.append(0x00)  # operand 2: 0
        code.append(0x00)  # store to stack

        return bytes(code)

    # ===== Parser Predicates =====

    def gen_verb_test(self, operands: List[ASTNode]) -> bytes:
        """Generate VERB? test - checks if PRSA matches any of the given verbs.

        Usage: <VERB? TAKE DROP PUT>
        Expands to: <OR <EQUAL? ,PRSA ,V?TAKE> <EQUAL? ,PRSA ,V?DROP> <EQUAL? ,PRSA ,V?PUT>>

        Returns true (branches) if PRSA equals any of the verb constants.
        """
        if not operands:
            return b''

        code = bytearray()

        # For single verb, generate simple EQUAL? test
        if len(operands) == 1:
            verb_name = operands[0].value if isinstance(operands[0], AtomNode) else str(operands[0])
            verb_const = f'V?{verb_name}'

            # Get verb number
            if verb_const in self.constants:
                verb_num = self.constants[verb_const]
            else:
                # Unknown verb - treat as 0
                verb_num = 0

            # Generate: EQUAL? ,PRSA verb_num
            # This is JE instruction (2OP opcode 0x01)
            prsa_var = self.globals['PRSA']

            code.append(0x65)  # Long form 2OP, opcode 0x01 (JE), var/small
            code.append(prsa_var)  # PRSA variable
            code.append(verb_num & 0xFF)  # Verb constant
            code.append(0x40)  # Branch on true, offset 0 (placeholder)

        else:
            # Multiple verbs - need to check each one
            # Strategy: Use multiple JE tests with same branch target
            # If any matches, branch to true

            # For simplicity, generate series of JE tests
            # Each test branches forward if true
            # Last test falls through if all false

            for i, operand in enumerate(operands):
                verb_name = operand.value if isinstance(operand, AtomNode) else str(operand)
                verb_const = f'V?{verb_name}'

                if verb_const in self.constants:
                    verb_num = self.constants[verb_const]
                else:
                    verb_num = 0

                prsa_var = self.globals['PRSA']

                # JE instruction
                code.append(0x65)  # Long form 2OP, var/small
                code.append(prsa_var)
                code.append(verb_num & 0xFF)

                # Branch byte - for now, simple offset
                # In real implementation, would need to calculate proper offsets
                code.append(0x40)  # Branch on true

        return bytes(code)

    def gen_perform(self, operands: List[ASTNode]) -> bytes:
        """Generate PERFORM action dispatch.

        Usage: <PERFORM action [object1] [object2]>
        Example: <PERFORM ,V?TAKE ,LAMP>
                 <PERFORM ,V?PUT ,BALL ,BOX>
                 <PERFORM ,V?LOOK>  ; action only

        This sets PRSA, PRSO, PRSI and calls the object's action routine.
        Simplified implementation: just sets the globals.
        Full implementation would dispatch to object ACTION property.
        """
        if len(operands) < 1:
            return b''

        code = bytearray()

        # Helper to store value in a global variable
        def store_to_global(global_name: str, operand: ASTNode):
            if global_name not in self.globals:
                return
            var_num = self.globals[global_name]
            op_type, op_val = self._get_operand_type_and_value(operand)

            if op_type == 0:  # Constant
                if op_val <= 255:
                    # STORE var small_const (0x0D short form)
                    code.append(0x0D | (0 << 6))  # STORE, small const
                    code.append(var_num)
                    code.append(op_val & 0xFF)
                else:
                    # Large constant - use ADD large const + 0 -> result
                    code.append(0xD4)  # ADD VAR form
                    code.append(0x1F)  # large, small, omit, omit
                    code.append((op_val >> 8) & 0xFF)
                    code.append(op_val & 0xFF)
                    code.append(0x00)  # Add 0
                    code.append(var_num)  # Store to variable
            else:  # Variable
                # STORE var from_var using ADD var 0 -> result
                code.append(0xD4)  # ADD VAR form
                code.append(0x9F)  # var, small, omit, omit
                code.append(op_val & 0xFF)  # Source variable
                code.append(0x00)  # Add 0
                code.append(var_num)  # Store to target variable

        # Extract action and objects
        action = operands[0]
        obj1 = operands[1] if len(operands) > 1 else None
        obj2 = operands[2] if len(operands) > 2 else None

        # Set PRSA to action
        store_to_global('PRSA', action)

        # Set PRSO to object1
        if obj1:
            store_to_global('PRSO', obj1)

        # Set PRSI to object2 (if provided)
        if obj2:
            store_to_global('PRSI', obj2)

        # Call object's ACTION routine (if it has one)
        # Get ACTION property of PRSO and call it
        if obj1:
            op1_type, op1_val = self._get_operand_type_and_value(obj1)
            prso_var = self.globals.get('PRSO', 0x11)

            # Check if we have an ACTION property constant
            action_prop = self.constants.get('P?ACTION', self.constants.get('ACTION', 0))

            if action_prop:
                # GET_PROP object property -> sp
                # GET_PROP is 2OP opcode 0x11
                code.append(0xD1)  # GET_PROP VAR form
                if op1_type == 0:  # Constant
                    if op1_val <= 255:
                        code.append(0x5F)  # small, small, omit, omit
                        code.append(op1_val & 0xFF)
                    else:
                        code.append(0x1F)  # large, small, omit, omit
                        code.append((op1_val >> 8) & 0xFF)
                        code.append(op1_val & 0xFF)
                else:  # Variable
                    code.append(0x9F)  # var, small, omit, omit
                    code.append(op1_val & 0xFF)
                code.append(action_prop & 0xFF)
                code.append(0x00)  # Store to stack

                # JZ sp [skip_call] - if no action routine, skip
                code.append(0xA0)  # JZ with variable operand
                code.append(0x00)  # Stack
                code.append(0x40 | 0x05)  # Branch false, offset 5 (skip CALL)

                # CALL_1N routine - call the action routine (no return value)
                if self.version >= 5:
                    # CALL_1N is 1OP opcode 0x0F in V5+
                    code.append(0xAF)  # CALL_1N (1OP:0x0F, variable type)
                    code.append(0x00)  # Stack (routine address)
                else:
                    # V3/V4: Use CALL with stack value
                    code.append(0xE0)  # CALL_VS
                    code.append(0x2F)  # Type: variable, omit, omit, omit
                    code.append(0x00)  # Stack
                    code.append(0x00)  # Store result to stack (discard)

        return bytes(code)

    def gen_call(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL (call routine with arguments).

        <CALL routine arg1 arg2 ...> calls a routine with up to 3 arguments.
        Uses Z-machine CALL instruction.

        Args:
            operands[0]: Routine name or address
            operands[1+]: Arguments (0-3 arguments)

        Returns:
            bytes: Z-machine code (CALL_VS or CALL)
        """
        if not operands:
            return b''

        code = bytearray()
        args = operands[1:]

        # Get routine type and value
        routine_type, routine_val = self._get_operand_type_and_value(operands[0])

        # CALL_VS is VAR opcode 0x00
        code.append(0xE0)  # VAR form, opcode 0x00

        # Build type byte for all operands (routine + up to 3 args)
        num_args = min(len(args), 3)
        types = []

        # Routine type (01=small const, 10=variable)
        types.append(0x01 if routine_type == 0 else 0x02)

        # Argument types
        arg_values = []
        for i in range(num_args):
            arg_type, arg_val = self._get_operand_type_and_value(args[i])
            types.append(0x01 if arg_type == 0 else 0x02)
            arg_values.append(arg_val)

        # Pad with "omitted" (11)
        while len(types) < 4:
            types.append(0x03)

        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)

        # Add routine address
        code.append(routine_val & 0xFF)

        # Add arguments
        for arg_val in arg_values:
            code.append(arg_val & 0xFF)

        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_apply(self, operands: List[ASTNode]) -> bytes:
        """Generate APPLY (call routine stored in variable).

        <APPLY routine-addr arg1 arg2 ...> calls the routine at the
        given address with the provided arguments.

        In ZIL, APPLY is used for indirect calls where the routine
        address is stored in a variable.

        Args:
            operands[0]: Routine address (typically from a variable)
            operands[1+]: Arguments to pass to the routine

        Returns:
            bytes: Z-machine code (CALL_VS with all operands)
        """
        if len(operands) < 1:
            raise ValueError("APPLY requires at least 1 operand")
        if self.version < 5:
            if len(operands) > 4:
                raise ValueError("APPLY accepts at most 4 operands in V3/V4")
        else:
            if len(operands) > 8:
                raise ValueError("APPLY accepts at most 8 operands in V5+")

        # APPLY is like CALL - pass all operands including args
        return self.gen_call(operands)

    def gen_call_vs2(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL_VS2 (V5+ extended call with store, up to 8 args).

        <CALL_VS2 routine arg1 ... arg8> calls routine with up to 8 arguments
        and stores the result. Only available in V5+.

        Args:
            operands[0]: Routine address
            operands[1-8]: Up to 8 arguments

        Returns:
            bytes: Z-machine code (CALL_VS2 EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()

        # Get all operand types and values (routine + up to 8 args)
        all_operands = []
        for op in operands[:9]:
            t, v = self._get_operand_type_and_value(op)
            all_operands.append((t, v))

        # CALL_VS2 is EXT opcode 0x0C
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0C)  # CALL_VS2

        # Build type bytes based on actual operand types
        def get_type_code(op_type, op_val):
            if op_type == 1:  # Variable
                return 0x02
            elif op_val > 255:  # Large constant
                return 0x00
            else:  # Small constant
                return 0x01

        # First type byte (operands 0-3)
        type_byte_1 = 0x00
        for i in range(4):
            if i < len(all_operands):
                t = get_type_code(all_operands[i][0], all_operands[i][1])
                type_byte_1 |= (t << (6 - i*2))
            else:
                type_byte_1 |= (0x03 << (6 - i*2))  # Omitted
        code.append(type_byte_1)

        # Second type byte (operands 4-7) - only if needed
        if len(all_operands) > 4:
            type_byte_2 = 0x00
            for i in range(4):
                if i + 4 < len(all_operands):
                    t = get_type_code(all_operands[i+4][0], all_operands[i+4][1])
                    type_byte_2 |= (t << (6 - i*2))
                else:
                    type_byte_2 |= (0x03 << (6 - i*2))  # Omitted
            code.append(type_byte_2)

        # Output operand values
        for op_type, op_val in all_operands:
            if op_type == 0 and op_val > 255:  # Large constant
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
            else:
                code.append(op_val & 0xFF)

        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_call_vn2(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL_VN2 (V5+ extended call without store, up to 8 args).

        <CALL_VN2 routine arg1 ... arg8> calls routine with up to 8 arguments
        without storing the result. Only available in V5+.

        Args:
            operands[0]: Routine address
            operands[1-8]: Up to 8 arguments

        Returns:
            bytes: Z-machine code (CALL_VN2 EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()

        # Get all operand types and values (routine + up to 8 args)
        all_operands = []
        for op in operands[:9]:
            t, v = self._get_operand_type_and_value(op)
            all_operands.append((t, v))

        # CALL_VN2 is EXT opcode 0x0D
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0D)  # CALL_VN2

        # Build type bytes based on actual operand types
        def get_type_code(op_type, op_val):
            if op_type == 1:  # Variable
                return 0x02
            elif op_val > 255:  # Large constant
                return 0x00
            else:  # Small constant
                return 0x01

        # First type byte (operands 0-3)
        type_byte_1 = 0x00
        for i in range(4):
            if i < len(all_operands):
                t = get_type_code(all_operands[i][0], all_operands[i][1])
                type_byte_1 |= (t << (6 - i*2))
            else:
                type_byte_1 |= (0x03 << (6 - i*2))  # Omitted
        code.append(type_byte_1)

        # Second type byte (operands 4-7) - only if needed
        if len(all_operands) > 4:
            type_byte_2 = 0x00
            for i in range(4):
                if i + 4 < len(all_operands):
                    t = get_type_code(all_operands[i+4][0], all_operands[i+4][1])
                    type_byte_2 |= (t << (6 - i*2))
                else:
                    type_byte_2 |= (0x03 << (6 - i*2))  # Omitted
            code.append(type_byte_2)

        # Output operand values
        for op_type, op_val in all_operands:
            if op_type == 0 and op_val > 255:  # Large constant
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
            else:
                code.append(op_val & 0xFF)

        return bytes(code)

    def gen_tokenise(self, operands: List[ASTNode]) -> bytes:
        """Generate TOKENISE (V5+ tokenize text buffer).

        <TOKENISE text-buffer parse-buffer dictionary flag> performs
        lexical analysis on input text. V5+ only.

        Args:
            operands[0]: Text buffer address
            operands[1]: Parse buffer address
            operands[2]: Dictionary address (optional)
            operands[3]: Flag (optional)

        Returns:
            bytes: Z-machine code (TOKENISE VAR opcode)
        """
        if self.version < 5:
            raise ValueError("LEX requires V5 or later")
        if len(operands) < 2 or len(operands) > 4:
            raise ValueError("LEX requires 2-4 operands")

        code = bytearray()

        # TOKENISE is VAR opcode 0x1B (27)
        # VAR opcode byte = 0xE0 + opcode = 0xE0 + 0x1B = 0xFB
        code.append(0xFB)

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(min(4, len(operands))):
            op_type, op_val = self._get_operand_type_and_value_ext(operands[i])
            op_types.append(op_type)
            op_vals.append(op_val)

        # Build type byte: 00=large, 01=small, 10=var, 11=omitted
        type_byte = 0x00
        for i in range(4):
            if i < len(op_types):
                type_val = op_types[i]  # Already in correct format
            else:
                type_val = 0x03  # Omitted
            type_byte |= (type_val << (6 - i*2))

        code.append(type_byte)

        # Append operand values with correct byte lengths
        for i, val in enumerate(op_vals):
            if op_types[i] == 0:  # Large constant (2 bytes)
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:  # Small constant or variable (1 byte)
                code.append(val & 0xFF)

        return bytes(code)

    def gen_check_arg_count(self, operands: List[ASTNode]) -> bytes:
        """Generate CHECK_ARG_COUNT (V5+ check number of arguments).

        <CHECK_ARG_COUNT n> branches if current routine was called
        with at least n arguments. V5+ only.

        Args:
            operands[0]: Argument count to check

        Returns:
            bytes: Z-machine code (CHECK_ARG_COUNT VAR opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # CHECK_ARG_COUNT is VAR opcode 0x3F (63)
        # Opcode byte is 0xC0 + 0x3F = 0xFF
        code.append(0xFF)  # CHECK_ARG_COUNT

        # Type byte: operand type in bits 7-6, rest are 0x03 (omitted)
        # 0x01 = small const, 0x02 = variable, 0x03 = omitted
        type_val = 0x01 if op_type == 0 else 0x02
        type_byte = (type_val << 6) | 0x3F  # One operand, rest omitted
        code.append(type_byte)
        code.append(op_val & 0xFF)

        # Branch: return true (1) if condition met
        # 0xC0 = branch on true, return true immediately
        code.append(0xC0)

        return bytes(code)

    def gen_zwstr(self, operands: List[ASTNode]) -> bytes:
        """Generate ZWSTR (V5+ encode string to Z-character format).

        <ZWSTR src-buffer length from dest-buffer> encodes
        text from source to destination in Z-encoded format.
        V5+ only, exactly 4 operands.

        Args:
            operands[0]: Source text buffer address
            operands[1]: Length of text
            operands[2]: Starting position (from)
            operands[3]: Destination buffer address

        Returns:
            bytes: Z-machine code (ENCODE_TEXT VAR opcode)
        """
        if self.version < 5:
            raise ValueError("ZWSTR requires V5 or later")
        if len(operands) != 4:
            raise ValueError("ZWSTR requires exactly 4 operands")

        code = bytearray()

        # ENCODE_TEXT is VAR opcode 0x3C (60)
        code.append(0xFC)  # VAR opcode 0x3C (0xC0 + 0x3C)

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(4):
            op_type, op_val = self._get_operand_type_and_value_ext(operands[i])
            op_types.append(op_type)
            op_vals.append(op_val)

        # Build type byte: 2 bits per operand (00=large, 01=small, 10=var, 11=omit)
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | op_types[3]
        code.append(type_byte)

        # Append operand values
        for i, val in enumerate(op_vals):
            if op_types[i] == 0:  # Large constant
                code.append((val >> 8) & 0xFF)
                code.append(val & 0xFF)
            else:
                code.append(val & 0xFF)

        return bytes(code)

    def gen_encode_text(self, operands: List[ASTNode]) -> bytes:
        """Generate ENCODE_TEXT (V5+ encode text to dictionary format).

        <ENCODE_TEXT zscii-text length from coded-text> encodes
        text into dictionary format (Z-encoded).

        Args:
            operands[0]: ZSCII text buffer address
            operands[1]: Length of text
            operands[2]: Starting position (from)
            operands[3]: Coded text buffer address

        Returns:
            bytes: Z-machine code (ENCODE_TEXT VAR opcode)
        """
        if self.version < 5:
            raise ValueError("ENCODE_TEXT requires V5 or later")
        if len(operands) != 4:
            raise ValueError("ENCODE_TEXT requires exactly 4 operands")

        # Delegate to gen_zwstr which has the correct implementation
        return self.gen_zwstr(operands)

    def gen_print_table(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_TABLE (V5+ print formatted table).

        <PRINT_TABLE zscii-text width height skip> prints a
        formatted table of text.

        Args:
            operands[0]: ZSCII text address
            operands[1]: Width of table
            operands[2]: Height (optional)
            operands[3]: Skip (optional)

        Returns:
            bytes: Z-machine code (PRINT_TABLE EXT opcode)
        """
        if len(operands) < 2 or self.version < 5:
            return b''

        code = bytearray()

        # PRINT_TABLE is EXT opcode 0x10
        code.append(0xBE)  # EXT opcode marker
        code.append(0x10)  # PRINT_TABLE

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(min(4, len(operands))):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            op_types.append(op_type)
            op_vals.append(op_val)

        # Build type byte
        type_byte = 0x00
        for i in range(4):
            if i < len(op_types):
                type_val = 0x01 if op_types[i] == 0 else 0x02
            else:
                type_val = 0x03  # Omitted
            type_byte |= (type_val << (6 - i*2))

        code.append(type_byte)

        # Append operand values
        for val in op_vals:
            code.append(val & 0xFF)

        return bytes(code)

    def gen_print_form(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_FORM (V6 - print formatted text table).

        <PRINT_FORM formatted-table> outputs formatted text from table structure.
        V6 only. The table contains formatting information for text rendering.

        Args:
            operands[0]: Formatted table address

        Returns:
            bytes: Z-machine code (PRINT_FORM EXT opcode)
        """
        if self.version < 6:
            raise ValueError("PRINTF requires V6")
        if len(operands) > 4:
            raise ValueError("PRINTF accepts at most 4 operands")

        code = bytearray()

        # PRINT_FORM is EXT opcode 0x1A
        code.append(0xBE)  # EXT opcode marker
        code.append(0x1A)  # PRINT_FORM

        table_addr = self.get_operand_value(operands[0])

        if isinstance(table_addr, int):
            code.append(0x01)  # Type: small
            code.append(table_addr & 0xFF)

        return bytes(code)

    def gen_make_menu(self, operands: List[ASTNode]) -> bytes:
        """Generate MAKE_MENU (V6 - create interactive menu).

        <MAKE_MENU table> creates an interactive menu selection interface.
        V6 only. Branches on success/failure.

        Args:
            operands[0]: Menu table address

        Returns:
            bytes: Z-machine code (MAKE_MENU EXT opcode)
        """
        if self.version < 6:
            raise ValueError("MENU requires V6")

        code = bytearray()

        # MAKE_MENU is EXT opcode 0x1B
        code.append(0xBE)  # EXT opcode marker
        code.append(0x1B)  # MAKE_MENU

        menu_table = self.get_operand_value(operands[0])

        if isinstance(menu_table, int):
            code.append(0x01)  # Type: small
            code.append(menu_table & 0xFF)
            # Branch byte (branch on success)
            code.append(0x40)

        return bytes(code)

    def gen_scan_table(self, operands: List[ASTNode]) -> bytes:
        """Generate SCAN_TABLE (V5+ search sorted table).

        <SCAN_TABLE value table length form> searches for value
        in a sorted table, returning address if found.

        Args:
            operands[0]: Value to search for
            operands[1]: Table address
            operands[2]: Table length
            operands[3]: Form (entry size, optional)

        Returns:
            bytes: Z-machine code (SCAN_TABLE EXT opcode)
        """
        if len(operands) < 3 or self.version < 5:
            return b''

        code = bytearray()

        # SCAN_TABLE is EXT opcode 0x18
        code.append(0xBE)  # EXT opcode marker
        code.append(0x18)  # SCAN_TABLE

        # Type byte
        num_operands = len(operands)
        type_byte = 0x00
        for i in range(4):
            if i < num_operands:
                type_byte |= (0x01 << (6 - i*2))
            else:
                type_byte |= (0x03 << (6 - i*2))

        code.append(type_byte)

        for i in range(min(num_operands, 4)):
            val = self.get_operand_value(operands[i])
            if isinstance(val, int):
                code.append(val & 0xFF)

        # Branch offset
        code.append(0x40)  # Branch on true
        code.append(0x00)

        # Store result
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_read_char(self, operands: List[ASTNode]) -> bytes:
        """Generate READ_CHAR (V4+ read single character).

        <READ_CHAR 1 time routine> reads a single character
        from input (with optional timeout).

        Args:
            operands[0]: 1 (required)
            operands[1]: Time in tenths of seconds (optional)
            operands[2]: Routine to call on timeout (optional)

        Returns:
            bytes: Z-machine code (READ_CHAR EXT opcode for V5+)
        """
        if self.version < 4:
            return b''

        code = bytearray()

        if self.version >= 5:
            # V5+: READ_CHAR is EXT opcode 0x16
            code.append(0xBE)  # EXT opcode marker
            code.append(0x16)  # READ_CHAR

            num_operands = len(operands)
            type_byte = 0x00
            for i in range(4):
                if i < num_operands:
                    type_byte |= (0x01 << (6 - i*2))
                else:
                    type_byte |= (0x03 << (6 - i*2))

            code.append(type_byte)

            for i in range(min(num_operands, 3)):
                val = self.get_operand_value(operands[i])
                if isinstance(val, int):
                    code.append(val & 0xFF)

            code.append(0x00)  # Store result to stack

        # V4 has different opcode structure
        return bytes(code)

    def gen_call_1s(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL_1S (V4+ call with 1 argument, store result).

        <CALL_1S routine> calls routine with exactly 0 arguments
        and stores the result. V4+ only.

        Args:
            operands[0]: Routine address

        Returns:
            bytes: Z-machine code (CALL_1S 1OP opcode)
        """
        if not operands or self.version < 4:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # CALL_1S is 1OP opcode 0x08
        # 1OP forms: 0x80 = large const, 0x90 = small const, 0xA0 = variable
        if op_type == 0:  # Constant
            if op_val <= 255:
                code.append(0x88)  # 1OP short form, small constant
                code.append(op_val & 0xFF)
            else:
                code.append(0x88)  # 1OP, large constant form
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
        else:  # Variable
            code.append(0xA8)  # 1OP, variable form
            code.append(op_val & 0xFF)
        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_call_1n(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL_1N (V5+ call with 1 argument, no store).

        <CALL_1N routine> calls routine with exactly 0 arguments
        without storing result. V5+ only.

        Args:
            operands[0]: Routine address

        Returns:
            bytes: Z-machine code (CALL_1N 1OP opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # CALL_1N is 1OP opcode 0x0F
        if op_type == 0:  # Constant
            if op_val <= 255:
                code.append(0x8F)  # 1OP short form, small constant
                code.append(op_val & 0xFF)
            else:
                code.append(0x8F)  # 1OP, large constant form
                code.append((op_val >> 8) & 0xFF)
                code.append(op_val & 0xFF)
        else:  # Variable
            code.append(0xAF)  # 1OP, variable form
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_call_2s(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL_2S (V4+ call with 1 argument, store result).

        <CALL_2S routine arg> calls routine with exactly 1 argument
        and stores the result. V4+ only.

        Args:
            operands[0]: Routine address
            operands[1]: Argument

        Returns:
            bytes: Z-machine code (CALL_2S 2OP opcode)
        """
        if len(operands) < 2 or self.version < 4:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # CALL_2S is 2OP opcode 0x19
        # Long form: opcode | (op1_type << 6) | (op2_type << 5)
        opcode = 0x19 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_call_2n(self, operands: List[ASTNode]) -> bytes:
        """Generate CALL_2N (V5+ call with 1 argument, no store).

        <CALL_2N routine arg> calls routine with exactly 1 argument
        without storing result. V5+ only.

        Args:
            operands[0]: Routine address
            operands[1]: Argument

        Returns:
            bytes: Z-machine code (CALL_2N 2OP opcode)
        """
        if len(operands) < 2 or self.version < 5:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # CALL_2N is 2OP opcode 0x1A
        # Long form: opcode | (op1_type << 6) | (op2_type << 5)
        opcode = 0x1A | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_save_undo(self, operands: List[ASTNode]) -> bytes:
        """Generate SAVE_UNDO (V5+ save game state for undo).

        <SAVE_UNDO> saves current game state and returns 1 if successful,
        0 if undo not available, -1 if too many saves.
        V5+ only, no operands.

        Returns:
            bytes: Z-machine code (SAVE_UNDO EXT opcode)
        """
        if self.version < 5:
            raise ValueError("ISAVE requires V5 or later")
        if operands:
            raise ValueError("ISAVE takes no operands")

        code = bytearray()

        # SAVE_UNDO is EXT opcode 0x09
        code.append(0xBE)  # EXT opcode marker
        code.append(0x09)  # SAVE_UNDO
        code.append(0xFF)  # No operands (type byte: all omitted)
        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_restore_undo(self, operands: List[ASTNode]) -> bytes:
        """Generate RESTORE_UNDO (V5+ restore game state from undo).

        <RESTORE_UNDO> restores previously saved state and returns 2
        if successful, 0 if no state available.
        V5+ only, no operands.

        Returns:
            bytes: Z-machine code (RESTORE_UNDO EXT opcode)
        """
        if self.version < 5:
            raise ValueError("IRESTORE requires V5 or later")
        if operands:
            raise ValueError("IRESTORE takes no operands")

        code = bytearray()

        # RESTORE_UNDO is EXT opcode 0x0A
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0A)  # RESTORE_UNDO
        code.append(0xFF)  # No operands
        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_print_unicode(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_UNICODE (V5+ print Unicode character).

        <PRINT_UNICODE char-number> prints a Unicode character.
        V5+ only (specifically V5.1+).

        Args:
            operands[0]: Unicode character number

        Returns:
            bytes: Z-machine code (PRINT_UNICODE EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # PRINT_UNICODE is EXT opcode 0x0B
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0B)  # PRINT_UNICODE

        # Type byte: operand type in bits 7-6, rest omitted (0x03)
        type_val = 0x01 if op_type == 0 else 0x02
        type_byte = (type_val << 6) | 0x3F
        code.append(type_byte)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_erase_line(self, operands: List[ASTNode]) -> bytes:
        """Generate ERASE_LINE (V4+ erase current line).

        <ERASE_LINE value> erases part of the current line.
        1 = from cursor onwards, other values implementation-specific.

        Args:
            operands[0]: Erase mode (optional, defaults to 1)

        Returns:
            bytes: Z-machine code (ERASE_LINE EXT opcode for V5+)
        """
        if self.version < 4:
            return b''

        code = bytearray()

        if self.version >= 5:
            # V5+: ERASE_LINE is EXT opcode 0x0E
            code.append(0xBE)  # EXT opcode marker
            code.append(0x0E)  # ERASE_LINE

            if operands:
                mode = self.get_operand_value(operands[0])
                code.append(0x01)  # Type: small constant
                if isinstance(mode, int):
                    code.append(mode & 0xFF)
            else:
                code.append(0x01)  # Type: small constant
                code.append(0x01)  # Default: erase from cursor

        return bytes(code)

    def gen_set_margins(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_MARGINS (V5+ set text margins).

        <SET_MARGINS left right window> sets text margins for window.

        Args:
            operands[0]: Left margin (pixels)
            operands[1]: Right margin (pixels)
            operands[2]: Window number (optional)

        Returns:
            bytes: Z-machine code (SET_MARGINS EXT opcode)
        """
        if len(operands) < 2 or self.version < 5:
            return b''

        code = bytearray()

        # SET_MARGINS is EXT opcode 0x08
        code.append(0xBE)  # EXT opcode marker
        code.append(0x08)  # SET_MARGINS

        # Type byte
        num_operands = len(operands)
        type_byte = 0x00
        for i in range(4):
            if i < num_operands:
                type_byte |= (0x01 << (6 - i*2))
            else:
                type_byte |= (0x03 << (6 - i*2))

        code.append(type_byte)

        for i in range(min(num_operands, 3)):
            val = self.get_operand_value(operands[i])
            if isinstance(val, int):
                code.append(val & 0xFF)

        return bytes(code)

    def gen_check_unicode(self, operands: List[ASTNode]) -> bytes:
        """Generate CHECK_UNICODE (V5+ check Unicode character availability).

        <CHECK_UNICODE char-number> checks if a Unicode character
        can be printed. Returns 0 if not available, non-zero if available.

        Args:
            operands[0]: Unicode character number

        Returns:
            bytes: Z-machine code (CHECK_UNICODE EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()

        # CHECK_UNICODE is EXT opcode 0x03
        code.append(0xBE)  # EXT opcode marker
        code.append(0x03)  # CHECK_UNICODE

        char_code = self.get_operand_value(operands[0])

        # Type byte: 1 operand
        code.append(0x01)  # Small constant

        if isinstance(char_code, int):
            code.append(char_code & 0xFF)

        code.append(0x00)  # Store result to stack

        return bytes(code)

    def gen_picture_table(self, operands: List[ASTNode]) -> bytes:
        """Generate PICTURE_TABLE (V6 backported to V5, setup graphics table).

        <PICTURE_TABLE table> sets up the picture table for graphics.
        Primarily a V6 feature, but some V5 interpreters support it.

        Args:
            operands[0]: Picture table address

        Returns:
            bytes: Z-machine code (PICTURE_TABLE EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()

        # PICTURE_TABLE is EXT opcode 0x1C (V6, but available in some V5)
        code.append(0xBE)  # EXT opcode marker
        code.append(0x1C)  # PICTURE_TABLE

        table_addr = self.get_operand_value(operands[0])

        # Type byte: 1 operand
        code.append(0x01)  # Small constant

        if isinstance(table_addr, int):
            code.append(table_addr & 0xFF)

        return bytes(code)

    def gen_draw_picture(self, operands: List[ASTNode]) -> bytes:
        """Generate DRAW_PICTURE (V6 graphics - draw picture).

        <DRAW_PICTURE picture y x> displays a picture at coordinates.
        V6 only. Coordinates are optional.

        Args:
            operands[0]: Picture number (1-based)
            operands[1]: Y coordinate (optional, pixels from top)
            operands[2]: X coordinate (optional, pixels from left)

        Returns:
            bytes: Z-machine code (DRAW_PICTURE EXT opcode)
        """
        if not operands or self.version < 6:
            return b''

        code = bytearray()

        # DRAW_PICTURE is EXT opcode 0x05
        code.append(0xBE)  # EXT opcode marker
        code.append(0x05)  # DRAW_PICTURE

        # Build operand list with types
        op_types = []
        op_vals = []
        op_sizes = []  # Track if large constant needed

        for i in range(min(3, len(operands))):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            if op_type == 0:  # Constant
                if op_val > 255:
                    op_types.append(0x00)  # Large constant
                    op_sizes.append(2)
                else:
                    op_types.append(0x01)  # Small constant
                    op_sizes.append(1)
            else:  # Variable
                op_types.append(0x02)
                op_sizes.append(1)
            op_vals.append(op_val)

        # Pad to 4 operands for type byte
        while len(op_types) < 4:
            op_types.append(0x03)  # Omitted

        # Build type byte
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | op_types[3]
        code.append(type_byte)

        # Output operand values
        for i, (t, v, s) in enumerate(zip(op_types[:len(op_vals)], op_vals, op_sizes)):
            if t == 0x00:  # Large constant
                code.append((v >> 8) & 0xFF)
                code.append(v & 0xFF)
            else:  # Small constant or variable
                code.append(v & 0xFF)

        return bytes(code)

    def gen_erase_picture(self, operands: List[ASTNode]) -> bytes:
        """Generate ERASE_PICTURE (V6 graphics - erase picture).

        <ERASE_PICTURE picture y x> erases a picture region to background color.
        V6 only.

        Args:
            operands[0]: Picture number (1-based)
            operands[1]: Y coordinate (pixels from top)
            operands[2]: X coordinate (pixels from left)

        Returns:
            bytes: Z-machine code (ERASE_PICTURE EXT opcode)
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()

        # ERASE_PICTURE is EXT opcode 0x07
        code.append(0xBE)  # EXT opcode marker
        code.append(0x07)  # ERASE_PICTURE

        # Build operand list with types
        op_types = []
        op_vals = []

        for i in range(3):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            if op_type == 0:  # Constant
                if op_val > 255:
                    op_types.append(0x00)  # Large constant
                else:
                    op_types.append(0x01)  # Small constant
            else:  # Variable
                op_types.append(0x02)
            op_vals.append(op_val)

        # Pad to 4 operands for type byte
        op_types.append(0x03)  # Omitted

        # Build type byte
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | op_types[3]
        code.append(type_byte)

        # Output operand values
        for t, v in zip(op_types[:3], op_vals):
            if t == 0x00:  # Large constant
                code.append((v >> 8) & 0xFF)
                code.append(v & 0xFF)
            else:  # Small constant or variable
                code.append(v & 0xFF)

        return bytes(code)

    def gen_picture_data(self, operands: List[ASTNode]) -> bytes:
        """Generate PICTURE_DATA (V6 graphics - query picture info).

        <PICTURE_DATA picture array> queries picture dimensions/availability.
        Returns branches if picture is available.
        Array receives: [height, width] or picture count if picture=0.

        Args:
            operands[0]: Picture number (0 for count, 1+ for specific picture)
            operands[1]: Array to store result (2 words)

        Returns:
            bytes: Z-machine code (PICTURE_DATA EXT opcode with branch)
        """
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()

        # PICTURE_DATA is EXT opcode 0x06
        code.append(0xBE)  # EXT opcode marker
        code.append(0x06)  # PICTURE_DATA

        # Build operand list with types
        op_types = []
        op_vals = []

        for i in range(2):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            if op_type == 0:  # Constant
                if op_val > 255:
                    op_types.append(0x00)  # Large constant
                else:
                    op_types.append(0x01)  # Small constant
            else:  # Variable
                op_types.append(0x02)
            op_vals.append(op_val)

        # Pad to 4 operands for type byte
        op_types.extend([0x03, 0x03])  # Omitted

        # Build type byte
        type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | op_types[3]
        code.append(type_byte)

        # Output operand values
        for t, v in zip(op_types[:2], op_vals):
            if t == 0x00:  # Large constant
                code.append((v >> 8) & 0xFF)
                code.append(v & 0xFF)
            else:  # Small constant or variable
                code.append(v & 0xFF)

        # Branch byte: branch on true (picture available)
        code.append(0x40)  # Branch offset 0 (continue)

        return bytes(code)

    def gen_rest(self, operands: List[ASTNode]) -> bytes:
        """Generate REST (alias for ADD with default second operand of 1).

        REST is a convenient alias for addition:
        - <REST x> = x + 1
        - <REST x y> = x + y

        Args:
            operands[0]: first value
            operands[1]: second value (optional, defaults to 1)

        Returns:
            bytes: Z-machine code (ADD instruction)
        """
        if not operands:
            return b''

        # If only one operand, default second operand to 1
        if len(operands) == 1:
            one_node = NumberNode(1)
            return self._gen_2op_store(0x14, operands[0], one_node)
        else:
            # Two operands - normal ADD
            return self._gen_2op_store(0x14, operands[0], operands[1])

    def gen_jigs_up(self, operands: List[ASTNode]) -> bytes:
        """Generate JIGS-UP (game over with message).

        Prints a death message and ends the game.

        Args:
            operands[0]: optional string message

        Returns:
            bytes: Z-machine code (PRINT_RET with message, then QUIT)
        """
        code = bytearray()

        # If message provided, print it
        if operands and isinstance(operands[0], StringNode):
            # Use PRINT_RET (0x03) to print and return true
            message = operands[0].value
            encoded_words = self.encoder.encode_string(message)

            code.append(0xB3)  # PRINT_RET opcode
            # Convert words to bytes
            for word in encoded_words:
                code.append((word >> 8) & 0xFF)
                code.append(word & 0xFF)

        # Print death message
        code.extend(self.gen_tell([StringNode("\n*** You have died ***\n", 0, 0)]))

        # QUIT
        code.extend(self.gen_quit())

        return bytes(code)

    def gen_held(self, operands: List[ASTNode]) -> bytes:
        """Generate HELD? (test if object is held by player).

        Tests if object's parent is WINNER (the player/adventurer).
        Equivalent to: <IN? object ,WINNER>

        Args:
            operands[0]: object to test

        Returns:
            bytes: Z-machine code (GET_PARENT + JE with WINNER)
        """
        if not operands:
            return b''

        # HELD? is equivalent to <IN? object ,WINNER>
        # We need to get the WINNER global variable
        winner_var = self.globals.get('WINNER', 1)  # Default to 1 if not defined

        code = bytearray()
        obj = self.get_operand_value(operands[0])

        if isinstance(obj, int):
            # GET_PARENT is 1OP opcode 0x03
            code.append(0x83)  # Short form, small constant
            code.append(obj & 0xFF)
            code.append(0x00)  # Store result to stack

            # JE (test equality with WINNER) is 2OP opcode 0x01
            code.append(0x41)  # Long form, opcode 0x01
            code.append(0x00)  # Stack (result from GET_PARENT)
            code.append(winner_var & 0xFF)  # WINNER global
            # Branch offset would be added during COND processing

        return bytes(code)

    def gen_igrtr(self, operands: List[ASTNode]) -> bytes:
        """Generate IGRTR? (increment variable and test if greater).

        Increments a variable and tests if result > comparison value.
        When used as an expression, pushes 1 (true) or 0 (false) to stack.

        IGRTR? FOO 100 = increment FOO, return true if now > 100.

        Args:
            operands[0]: variable to increment (must be a variable name, not a number)
            operands[1]: value to compare against (must be a constant, not a variable)

        Returns:
            bytes: Z-machine code that pushes 0 or 1 to stack
        """
        if len(operands) < 2:
            raise ValueError("IGRTR? requires exactly 2 operands")

        var = operands[0]
        cmp_op = operands[1]

        # Validate: first operand must be a variable, not a number
        if isinstance(var, NumberNode):
            raise ValueError("IGRTR? first operand must be a variable, not a number")

        # Validate: second operand must be a constant, not a variable
        if isinstance(cmp_op, LocalVarNode) or isinstance(cmp_op, GlobalVarNode):
            raise ValueError("IGRTR? second operand must be a constant, not a variable")
        # Also check for AtomNode that resolves to a variable
        if isinstance(cmp_op, AtomNode):
            if cmp_op.value in self.locals or cmp_op.value in self.globals:
                raise ValueError("IGRTR? second operand must be a constant, not a variable")

        var_num = self.get_variable_number(var)
        if var_num == 0:  # Stack is invalid for INC
            if isinstance(var, AtomNode) and var.value not in self.locals and var.value not in self.globals:
                raise ValueError(f"IGRTR? unknown variable '{var.value}'")

        cmp_type, cmp_val = self._get_operand_type_and_value(cmp_op)

        code = bytearray()

        # INC the variable (0x95 = INC with small const)
        code.append(0x95)
        code.append(var_num)

        # Generate code to push 0 or 1 based on var > cmp_val
        # Pattern:
        #   JG var cmp_val ?true (if var > cmp_val, branch to true)
        #   ADD 0 0 -> stack     (false case: push 0)
        #   JUMP ?end            (skip over true case)
        #   ?true:
        #   ADD 0 1 -> stack     (true case: push 1)
        #   ?end:

        # JG is 2OP opcode 0x03
        # Short 2OP with var,small: 0 1 0 00011 = 0x43
        code.append(0x43)  # JG short form with var, small const
        code.append(var_num)
        code.append(cmp_val & 0xFF)
        # Branch byte: branch if true (bit 7 = 1), short form (bit 6 = 1)
        # Need to skip: ADD 0 0 -> stack (4 bytes) + JUMP ?end (3 bytes) = 7 bytes
        # Offset = 7 + 2 = 9
        code.append(0xC9)  # 11001001 = branch true, short, offset 9

        # FALSE case: ADD 0 0 -> stack
        # ADD is 2OP opcode 0x14
        # Short form with both small: 0 0 0 10100 = 0x14
        code.append(0x14)  # ADD short form, both small
        code.append(0x00)  # 0
        code.append(0x00)  # 0
        code.append(0x00)  # Store to stack

        # JUMP past true case
        # JUMP is 1OP opcode 0x0C with 16-bit offset
        # Need to skip 4 bytes (the ADD instruction in true case)
        # Offset = 4 + 2 = 6 (relative to PC after JUMP instruction)
        code.append(0x8C)  # 1OP large const, opcode 0x0C
        code.append(0x00)  # High byte of offset (6 = 0x0006)
        code.append(0x06)  # Low byte of offset

        # TRUE case: ADD 0 1 -> stack
        code.append(0x14)  # ADD short form, both small
        code.append(0x00)  # 0
        code.append(0x01)  # 1
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_prob(self, operands: List[ASTNode]) -> bytes:
        """Generate PROB (probability test).

        Tests if random number (1-100) is <= given percentage.
        Equivalent to: <L? <RANDOM 100> percentage>

        Args:
            operands[0]: percentage (0-100)

        Returns:
            bytes: Z-machine code (RANDOM + JL)
        """
        if not operands:
            return b''

        code = bytearray()
        percentage = self.get_operand_value(operands[0])

        # RANDOM 100 to get number 1-100
        # RANDOM is 1OP opcode 0x07
        code.append(0x87)  # Short form, small constant
        code.append(100)   # Range: 1-100
        code.append(0x00)  # Store to stack

        # JL (test if <= percentage) is 2OP opcode 0x02
        if isinstance(percentage, int):
            code.append(0x42)  # Long form, opcode 0x02
            code.append(0x00)  # Stack (result from RANDOM)
            code.append(percentage & 0xFF)
            # Branch offset would be added during COND processing

        return bytes(code)

    def gen_pick_one(self, operands: List[ASTNode]) -> bytes:
        """Generate PICK-ONE (select random element from table).

        Picks a random element from a table and returns it.
        Equivalent to: <GET table <RANDOM <GET table 0>>>

        Args:
            operands[0]: table address

        Returns:
            bytes: Z-machine code (RANDOM + GET)
        """
        if not operands:
            return b''

        code = bytearray()
        table = self.get_operand_value(operands[0])

        if isinstance(table, int):
            # First, get table size from offset 0
            # LOADW is 2OP opcode 0x0F
            code.append(0x4F)  # Long form, opcode 0x0F
            code.append(table & 0xFF)
            code.append(0x00)  # Offset 0 (table size)
            code.append(0x00)  # Store to stack

            # RANDOM <table-size> to get index 1..size
            # RANDOM is 1OP opcode 0x07
            code.append(0x87)  # Short form, variable
            code.append(0x00)  # Stack (table size)
            code.append(0x00)  # Store to stack

            # GET table random-index
            # LOADW is 2OP opcode 0x0F
            code.append(0x4F)  # Long form, opcode 0x0F
            code.append(table & 0xFF)
            code.append(0x00)  # Stack (random index)
            code.append(0x00)  # Store to stack (final result)

        return bytes(code)

    def gen_goto(self, operands: List[ASTNode]) -> bytes:
        """Generate GOTO (move player to new room).

        Changes the HERE global to new room and describes it.
        In full implementation, would also call room's action routine.

        Args:
            operands[0]: new room object

        Returns:
            bytes: Z-machine code (STORE HERE + room description call)
        """
        if not operands:
            return b''

        code = bytearray()
        room_node = operands[0]
        here_var = self.globals.get('HERE', 2)  # Default to 2 if not defined

        # Check if room is an expression (FormNode) that needs evaluation
        if isinstance(room_node, FormNode):
            # Evaluate the expression, result goes to stack
            expr_code = self.generate_statement(room_node)
            if expr_code:
                code.extend(expr_code)
                # Now store stack to HERE using STOREW with indirect addressing
                # Actually simpler: use ADD stack 0 -> HERE_var to copy
                code.append(0xD4)  # ADD VAR form
                code.append(0x9F)  # var, small, omit, omit
                code.append(0x00)  # Stack
                code.append(0x00)  # Add 0
                code.append(here_var)  # Store to HERE

                # Print room description using stack value
                # We need to re-push the value or use HERE
                # Use LOADW to get HERE value for PRINT_OBJ
                code.append(0xAA)  # PRINT_OBJ (1OP variable)
                code.append(here_var)  # HERE variable

                # Print newline
                code.append(0xBB)  # NEW_LINE
            return bytes(code)

        # Get the room value - check different node types
        room = self.get_operand_value(room_node)
        if room is None:
            # Try to resolve as object
            if isinstance(room_node, AtomNode):
                room = self.objects.get(room_node.value)
            elif isinstance(room_node, LocalVarNode):
                room = self.locals.get(room_node.name, 1)
            elif isinstance(room_node, GlobalVarNode):
                room = self.globals.get(room_node.name, 0x10)

        if isinstance(room, int):
            # STORE is 2OP opcode 0x0D (long form small/small: 00 0 0 1101)
            code.append(0x0D)  # Long form, both operands small
            code.append(here_var & 0xFF)
            code.append(room & 0xFF)

            # Call room's ACTION routine (if it has one)
            # Get ACTION property of room and call it with M-ENTER
            action_prop = self.constants.get('P?ACTION', self.constants.get('ACTION', 0))
            m_enter = self.constants.get('M-ENTER', self.constants.get('M?ENTER', 1))

            if action_prop and room <= 255 and action_prop <= 255:
                # GET_PROP room action-prop -> sp
                code.append(0x51)  # GET_PROP (2OP:0x11)
                code.append(room & 0xFF)
                code.append(action_prop & 0xFF)
                code.append(0x00)  # Store to stack

                # JZ sp [skip_call] - if no action routine, skip
                code.append(0xA0)  # JZ with variable operand
                code.append(0x00)  # Stack
                skip_offset = 7 if self.version >= 5 else 8
                code.append(0x40 | skip_offset)  # Branch false

                # Call routine with M-ENTER argument
                if self.version >= 5:
                    # CALL_2N routine m-enter (call without return)
                    code.append(0xDA)  # CALL_2N (2OP:0x1A)
                    code.append(0x00)  # Stack (routine address)
                    code.append(m_enter & 0xFF)
                else:
                    # V3/V4: CALL with stack and argument
                    code.append(0xE0)  # CALL_VS
                    code.append(0x29)  # Type: variable, small, omit, omit
                    code.append(0x00)  # Stack (routine)
                    code.append(m_enter & 0xFF)
                    code.append(0x00)  # Store result (discard)

            # Also call DESCRIBE-ROOM or print room short description
            # Print the room's short name (object short description)
            # PRINT_OBJ is 1OP opcode 0x0A
            code.append(0xAA)  # PRINT_OBJ (1OP:0x0A, small operand)
            code.append(room & 0xFF)

            # Print newline
            code.append(0xBB)  # NEW_LINE

        return bytes(code)

    def gen_getpt(self, operands: List[ASTNode]) -> bytes:
        """Generate GETPT (get property table address).

        Returns the address of a property's data, not the value.
        Similar to GETP but returns address for direct manipulation.

        Args:
            operands[0]: object
            operands[1]: property number

        Returns:
            bytes: Z-machine code (GET_PROP_ADDR)
        """
        if len(operands) != 2:
            raise ValueError("GETPT requires exactly 2 operands")

        # Track property usage for ZIL0212 warning
        self._track_property_usage(operands[1])

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # GET_PROP_ADDR is 2OP opcode 0x12
        opcode = 0x12 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_btst(self, operands: List[ASTNode]) -> bytes:
        """Generate BTST (bit test).

        Tests if all bits in the mask are set in the value.
        BTST value mask -> returns 1 if (value AND mask) == mask, else 0

        This is the Z-machine TEST opcode semantics.

        Args:
            operands[0]: value to test
            operands[1]: bit mask

        Returns:
            bytes: Z-machine code using TEST opcode
        """
        if len(operands) != 2:
            self._error(f"BTST requires exactly 2 operands, got {len(operands)}")

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Use TEST opcode (2OP:7) which branches if (value AND mask) == mask
        # TEST is opcode 7 in 2OP range
        # Long form: $00-$1F = (small, small), $20-$3F = (small, var), etc.
        # Opcode 7: $07 = (small, small, opcode 7)
        opcode = 0x07 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        # Branch byte: 0xC1 = branch on true, short offset, return true (offset 1)
        code.append(0xC1)
        # If we fall through (test failed), return false
        code.append(0xB1)  # RFALSE (return 0)

        return bytes(code)

    def gen_band(self, operands: List[ASTNode]) -> bytes:
        """Generate BAND (bitwise AND).

        Performs bitwise AND operation using Z-machine AND opcode (0x09).
        Unlike logical AND, this performs actual bit-level AND.

        Handles variadic BAND:
        - 0 operands: returns -1 (0xFFFF, all bits set - identity)
        - 1 operand: returns that operand
        - 2 operands: a & b
        - 3+ operands: a & b & c & ...

        Args:
            operands: Values to AND together

        Returns:
            bytes: Z-machine code (AND instruction)
        """
        # AND is 2OP opcode 0x09
        # Identity for AND is -1 (all bits set)
        return self._gen_variadic_arith(0x09, operands, identity=-1)

    def gen_bor(self, operands: List[ASTNode]) -> bytes:
        """Generate BOR (bitwise OR).

        Performs bitwise OR operation using Z-machine OR opcode (0x08).
        Unlike logical OR, this performs actual bit-level OR.

        Handles variadic BOR:
        - 0 operands: returns 0 (identity)
        - 1 operand: returns that operand
        - 2 operands: a | b
        - 3+ operands: a | b | c | ...

        Args:
            operands: Values to OR together

        Returns:
            bytes: Z-machine code (OR instruction)
        """
        # OR is 2OP opcode 0x08
        return self._gen_variadic_arith(0x08, operands, identity=0)

    def gen_lsh(self, operands: List[ASTNode]) -> bytes:
        """Generate LSH (left shift).

        <LSH value shift-count> shifts value left by shift-count bits.
        Equivalent to value * (2 ^ shift-count)

        Z-machine V5+ has ART_SHIFT opcode.
        For V3, we simulate with multiplication.

        Args:
            operands[0]: value to shift
            operands[1]: number of bits to shift left

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])
        shift = self.get_operand_value(operands[1])

        if isinstance(value, int) and isinstance(shift, int):
            # For V3, simulate with multiplication
            # LSH value N == value * (2^N)
            multiplier = 2 ** shift if shift >= 0 else 1

            if 0 <= value <= 255 and 0 <= multiplier <= 255:
                code.append(0x56)  # MUL opcode
                code.append(value & 0xFF)
                code.append(multiplier & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_rsh(self, operands: List[ASTNode]) -> bytes:
        """Generate RSH (right shift).

        <RSH value shift-count> shifts value right by shift-count bits.
        Equivalent to value / (2 ^ shift-count)

        Z-machine V5+ has ART_SHIFT opcode.
        For V3, we simulate with division.

        Args:
            operands[0]: value to shift
            operands[1]: number of bits to shift right

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])
        shift = self.get_operand_value(operands[1])

        if isinstance(value, int) and isinstance(shift, int):
            # For V3, simulate with division
            # RSH value N == value / (2^N)
            divisor = 2 ** shift if shift >= 0 else 1

            if 0 <= value <= 255 and divisor > 0 and divisor <= 255:
                code.append(0x57)  # DIV opcode
                code.append(value & 0xFF)
                code.append(divisor & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Daemon/Interrupt System =====
    #
    # WARNING: The built-in QUEUE/ENABLE/DISABLE implementations have a known issue:
    # they store interrupt structures in static memory, which cannot be modified at
    # runtime. Games should use library routines (like gclock.zil or events.zil)
    # instead. The codegen now checks for user-defined routines first.

    def gen_queue(self, operands: List[ASTNode]) -> bytes:
        """Generate QUEUE (schedule interrupt/daemon).

        WARNING: This built-in implementation stores data in static memory,
        which cannot be modified at runtime. Consider using library routines
        (gclock.zil or events.zil) instead.

        <QUEUE I-NAME tick-count> schedules a routine to run after tick-count turns.
        - tick-count > 0: One-shot interrupt (fire once, then disable)
        - tick-count = -1: Daemon (fire every turn)
        - tick-count = 0: Fire next turn

        Creates an 8-byte interrupt structure in table data:
          Offset 0: Routine address (word, packed) - placeholder for fixup
          Offset 2: Tick count (word, signed)
          Offset 4: Enabled flag (word, 0=disabled 1=enabled)
          Offset 6: Reserved (word)

        Args:
            operands[0]: Interrupt name (will be routine name with I- prefix)
            operands[1]: Tick count

        Returns:
            bytes: Code that pushes address of interrupt structure
        """
        import sys
        print("Warning: Using built-in QUEUE implementation which stores data in "
              "static memory. Consider defining a QUEUE routine in your ZIL code "
              "(see gclock.zil or events.zil).", file=sys.stderr)
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get interrupt name and tick count
        if isinstance(operands[0], AtomNode):
            int_name = operands[0].value
            tick_count = self.get_operand_value(operands[1])
            if not isinstance(tick_count, int):
                tick_count = -1  # Default to daemon if tick count is variable

            # Check if we already have this interrupt
            if int_name in self._interrupt_table_indices:
                # Return existing interrupt address
                table_idx = self._interrupt_table_indices[int_name]
            else:
                # Create 8-byte interrupt structure as a table
                int_data = bytearray(8)

                # Offset 0-1: Routine address placeholder (0xFD + index)
                # The routine name should match the interrupt name (e.g., I-FIGHT)
                placeholder_idx = self._next_placeholder_index
                self._routine_placeholders[placeholder_idx] = int_name
                self._next_placeholder_index += 1
                int_data[0] = 0xFD
                int_data[1] = placeholder_idx & 0xFF

                # Offset 2-3: Tick count (signed 16-bit)
                int_data[2] = (tick_count >> 8) & 0xFF
                int_data[3] = tick_count & 0xFF

                # Offset 4-5: Enabled flag (1 = enabled)
                int_data[4] = 0x00
                int_data[5] = 0x01

                # Offset 6-7: Reserved
                int_data[6] = 0x00
                int_data[7] = 0x00

                # Store as a table and track offset
                table_id = f"_INT_{int_name}"
                table_idx = len(self.tables)
                self.table_offsets[table_idx] = self._table_data_size  # Track offset
                self._table_data_size += len(int_data)  # Update running total
                self.tables.append((table_id, bytes(int_data), False))
                self._interrupt_table_indices[int_name] = table_idx

                # Also track in interrupts dict for INT lookup
                self.interrupts[int_name] = table_idx

            # Allocate a global variable to hold this interrupt's address
            # The global will be initialized with the table address by the assembler
            global_name = f"_INT_ADDR_{int_name}"
            if global_name not in self.globals:
                self.globals[global_name] = self.next_global
                # Store placeholder for table address (0xFF00 | table_idx)
                self.global_values[global_name] = 0xFF00 | table_idx
                self.next_global += 1

            global_num = self.globals[global_name]

            # Return code that pushes the global value to stack
            # PUSH (variable) - VAR opcode 0x08
            code.append(0xE8)  # VAR form, opcode 0x08 (PUSH)
            code.append(0x8F)  # Type byte: variable, rest omitted
            code.append(global_num)  # Global variable number

        return bytes(code)

    def gen_int(self, operands: List[ASTNode]) -> bytes:
        """Generate INT (get interrupt by name).

        <INT I-NAME> returns the address of a previously QUEUEd interrupt.

        Args:
            operands[0]: Interrupt name

        Returns:
            bytes: Code that pushes address of interrupt structure
        """
        if not operands:
            return b''

        code = bytearray()

        # Look up interrupt name
        if isinstance(operands[0], AtomNode):
            int_name = operands[0].value

            if int_name in self._interrupt_table_indices:
                # Get the global that holds the interrupt address
                global_name = f"_INT_ADDR_{int_name}"
                if global_name in self.globals:
                    global_num = self.globals[global_name]
                    # PUSH (variable) - VAR opcode 0x08
                    code.append(0xE8)  # VAR form, opcode 0x08 (PUSH)
                    code.append(0x8F)  # Type byte: variable, rest omitted
                    code.append(global_num)  # Global variable number
                else:
                    # Global wasn't allocated (shouldn't happen) - push 0
                    code.append(0xE8)  # PUSH
                    code.append(0x5F)  # Small constant type
                    code.append(0x00)
            else:
                # Interrupt not found - return 0
                code.append(0xE8)  # PUSH
                code.append(0x5F)  # Small constant type
                code.append(0x00)

        return bytes(code)

    def gen_dequeue(self, operands: List[ASTNode]) -> bytes:
        """Generate DEQUEUE (remove/disable interrupt).

        WARNING: This built-in implementation attempts to write to static memory,
        which will fail at runtime. Consider using library routines instead.

        <DEQUEUE interrupt-addr> disables an interrupt.
        Sets the enabled flag (offset 2, word index) to 0.

        Args:
            operands[0]: Interrupt structure address (or nested form that returns it)

        Returns:
            bytes: Z-machine code (STOREW to set enabled=0)
        """
        import sys
        print("Warning: Using built-in DEQUEUE implementation which attempts to write "
              "to static memory. This will fail at runtime. Consider defining a "
              "DEQUEUE routine in your ZIL code.", file=sys.stderr)
        if not operands:
            return b''

        code = bytearray()

        # If the operand is a nested form, evaluate it first
        if isinstance(operands[0], FormNode):
            # Generate code for the nested form - result goes to stack
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            # Now use stack (variable 0x00) as the base address
            # STOREW (SP) 2 0  (set enabled flag at word offset 2 to 0)
            code.append(0xE1)  # VAR form, STOREW
            code.append(0x97)  # Type byte: 10 01 01 11 = var, small, small, omit
            code.append(0x00)  # Stack (variable 0)
            code.append(0x02)  # Word offset 2 (enabled flag)
            code.append(0x00)  # Value 0 (disabled)
        else:
            int_addr = self.get_operand_value(operands[0])
            if isinstance(int_addr, int):
                # STOREW int_addr 2 0  (set enabled flag to 0)
                code.append(0xE1)  # VAR form, STOREW
                code.append(0x57)  # Type byte: 01 01 01 11 = small, small, small, omit
                code.append(int_addr & 0xFF)
                code.append(0x02)  # Word offset 2 (enabled flag)
                code.append(0x00)  # Value 0 (disabled)

        return bytes(code)

    def gen_enable(self, operands: List[ASTNode]) -> bytes:
        """Generate ENABLE (enable interrupt).

        WARNING: This built-in implementation attempts to write to static memory,
        which will fail at runtime. Consider using library routines instead.

        <ENABLE interrupt-addr> enables an interrupt.
        Sets the enabled flag (offset 2, word index) to 1.

        Args:
            operands[0]: Interrupt structure address (or nested form that returns it)

        Returns:
            bytes: Z-machine code (STOREW to set enabled=1)
        """
        import sys
        print("Warning: Using built-in ENABLE implementation which attempts to write "
              "to static memory. This will fail at runtime. Consider defining an "
              "ENABLE routine in your ZIL code.", file=sys.stderr)
        if not operands:
            return b''

        code = bytearray()

        # If the operand is a nested form, evaluate it first
        if isinstance(operands[0], FormNode):
            # Generate code for the nested form - result goes to stack
            inner_code = self.generate_form(operands[0])
            code.extend(inner_code)
            # Now use stack (variable 0x00) as the base address
            # STOREW (SP) 2 1  (set enabled flag at word offset 2 to 1)
            code.append(0xE1)  # VAR form, STOREW
            code.append(0x97)  # Type byte: 10 01 01 11 = var, small, small, omit
            code.append(0x00)  # Stack (variable 0)
            code.append(0x02)  # Word offset 2 (enabled flag)
            code.append(0x01)  # Value 1 (enabled)
        else:
            int_addr = self.get_operand_value(operands[0])
            if isinstance(int_addr, int):
                # STOREW int_addr 2 1  (set enabled flag to 1)
                code.append(0xE1)  # VAR form, STOREW
                code.append(0x57)  # Type byte: 01 01 01 11 = small, small, small, omit
                code.append(int_addr & 0xFF)
                code.append(0x02)  # Word offset 2 (enabled flag)
                code.append(0x01)  # Value 1 (enabled)

        return bytes(code)

    def gen_disable(self, operands: List[ASTNode]) -> bytes:
        """Generate DISABLE (disable interrupt).

        <DISABLE interrupt-addr> disables an interrupt.
        Sets the enabled flag (offset 4) to 0.
        This is an alias for DEQUEUE.

        Args:
            operands[0]: Interrupt structure address

        Returns:
            bytes: Z-machine code (STOREW to set enabled=0)
        """
        # DISABLE is functionally the same as DEQUEUE
        return self.gen_dequeue(operands)

    # ===== Helper Methods =====

    def _extract_cond_clause(self, operand) -> tuple:
        """Extract a COND clause from a macro-expanded operand.

        Returns (condition, actions) tuple or None if operand should be skipped.

        Handles:
        - FormNode(QUOTE, [clause_list]) - quoted clause from macro
        - list [condition, action1, ...] - raw list clause
        - FormNode(<>) or empty - skip
        - FormNode that's a bare form - ZIL0100 error
        """
        # Handle QUOTE FormNode - extract the quoted list
        if isinstance(operand, FormNode):
            if isinstance(operand.operator, AtomNode):
                op_name = operand.operator.value.upper()
                if op_name == 'QUOTE':
                    # Extract the quoted content
                    if operand.operands:
                        inner = operand.operands[0]
                        if isinstance(inner, list) and inner:
                            # List is the clause: [condition, action1, ...]
                            condition = inner[0]
                            actions = list(inner[1:])
                            return (condition, actions)
                    # Empty quote - skip
                    return None
                elif op_name in ('', '<>') or (not operand.operands and op_name == '()'):
                    # Empty form - skip
                    return None
            # Check for empty form <>
            if not operand.operands and isinstance(operand.operator, AtomNode):
                if operand.operator.value in ('', '<>', '()'):
                    return None
            # Bare form - error
            raise ValueError(
                "ZIL0100: COND requires parenthesized clauses (condition actions...), "
                f"not bare forms like <{operand.operator.value if hasattr(operand.operator, 'value') else operand.operator}>"
            )

        # Handle raw list - treat as clause
        if isinstance(operand, list):
            if not operand:
                # Empty list - skip
                return None
            condition = operand[0]
            actions = list(operand[1:])
            return (condition, actions)

        # Handle AtomNode '<>' or similar
        if isinstance(operand, AtomNode):
            if operand.value.upper() in ('', '<>', 'FALSE'):
                return None
            # Bare atom - error
            raise ValueError(
                "ZIL0100: COND requires parenthesized clauses (condition actions...), "
                f"not bare atoms like {operand.value}"
            )

        # Unknown type - error
        raise ValueError(
            "ZIL0100: COND requires parenthesized clauses (condition actions...), "
            f"got {type(operand).__name__}"
        )

    # ===== Table Literal Operations =====

    def _contains_local_var(self, node: ASTNode) -> bool:
        """Check if a node contains any LocalVarNode (local variable reference)."""
        if isinstance(node, LocalVarNode):
            return True
        if isinstance(node, FormNode):
            for op in node.operands:
                if self._contains_local_var(op):
                    return True
            if self._contains_local_var(node.operator):
                return True
        if isinstance(node, list):
            for item in node:
                if self._contains_local_var(item):
                    return True
        return False

    def gen_table(self, operands: List[ASTNode], table_type: str = 'TABLE') -> bytes:
        """Generate TABLE/LTABLE/ITABLE/PTABLE.

        Tables are data structures stored in static/high memory.
        - TABLE: Simple table with word values
        - LTABLE: Length-prefixed table (first word is element count)
        - ITABLE: Initialized table with specified size
        - PTABLE: Pure (read-only) table

        When used in code, returns an address pointing to the table data.
        The actual table bytes are accumulated in self.tables and assembled later.

        Args:
            operands: Table values and optional flags
            table_type: TABLE, LTABLE, ITABLE, or PTABLE

        Returns:
            bytes: Code to load the table address
        """
        # Check for local variable references - tables must have compile-time constant values
        for op in operands:
            if self._contains_local_var(op):
                raise ValueError(f"Table cannot reference local variables - values must be compile-time constants")

        table_data = bytearray()
        is_pure = table_type == 'PTABLE'
        is_byte = False
        is_string = False  # STRING flag - store strings as raw characters
        initial_size = None

        # Process operands
        values = []
        for op in operands:
            # Check for flags like (PURE), (BYTE), (STRING)
            if isinstance(op, FormNode):
                if isinstance(op.operator, AtomNode):
                    flag_name = op.operator.value.upper()
                    if flag_name == 'PURE':
                        is_pure = True
                        continue
                    elif flag_name == 'BYTE':
                        is_byte = True
                        continue
                    elif flag_name == 'STRING':
                        is_string = True
                        is_byte = True  # STRING implies BYTE mode
                        continue
            elif isinstance(op, AtomNode):
                flag_name = op.value.upper()
                if flag_name == 'PURE':
                    is_pure = True
                    continue
                elif flag_name == 'BYTE':
                    is_byte = True
                    continue
                elif flag_name == 'STRING':
                    is_string = True
                    is_byte = True  # STRING implies BYTE mode
                    continue

            values.append(op)

        # For LTABLE, first value is the count (or we compute it)
        if table_type == 'LTABLE':
            # LTABLE has a length prefix
            table_data.extend(struct.pack('>H', len(values)))

        # For ITABLE, first value might be the size (repeat count)
        if table_type == 'ITABLE' and values and isinstance(values[0], NumberNode):
            initial_size = values[0].value
            values = values[1:]  # Rest are initial values

        # Handle ITABLE with repeat count
        if initial_size and table_type == 'ITABLE' and values:
            # ITABLE with size and values: repeat pattern 'size' times
            pattern_data = self._encode_table_values(values, default_is_byte=is_byte,
                                                      is_string=is_string)
            for _ in range(initial_size):
                table_data.extend(pattern_data)
        elif initial_size and table_type == 'ITABLE':
            # ITABLE with just size: create zero-filled table
            entry_size = 1 if is_byte else 2
            for _ in range(initial_size):
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))
        else:
            # Encode table values using helper that handles #BYTE/#WORD prefixes
            table_data.extend(self._encode_table_values(values, default_is_byte=is_byte,
                                                         is_string=is_string))

        # Store the table for later assembly
        table_id = f"_TABLE_{self.table_counter}"
        table_idx = len(self.tables)  # Use current length as index
        self.table_offsets[table_idx] = self._table_data_size  # Track offset
        self._table_data_size += len(table_data)  # Update running total
        self.table_counter += 1
        self.tables.append((table_id, bytes(table_data), is_pure))

        # Allocate a global variable to hold this table's address
        # The global will be initialized with a placeholder that gets resolved by the assembler
        global_name = f"_TBL_ADDR_{table_idx}"
        if global_name not in self.globals:
            self.globals[global_name] = self.next_global
            # Store placeholder for table address (0xFF00 | table_idx)
            self.global_values[global_name] = 0xFF00 | table_idx
            self.next_global += 1

        global_num = self.globals[global_name]

        # Return code that pushes the global value (table address) to stack
        # PUSH (variable) - VAR opcode 0x08
        code = bytearray()
        code.append(0xE8)  # VAR form, opcode 0x08 (PUSH)
        code.append(0x8F)  # Type byte: variable, rest omitted
        code.append(global_num)  # Global variable number

        return bytes(code)

    def get_table_data(self) -> bytes:
        """Get all accumulated table data for assembly.

        Returns:
            bytes: Concatenated table data
        """
        result = bytearray()
        for table_id, data, is_pure in self.tables:
            result.extend(data)
        return bytes(result)

    def get_table_offsets(self) -> Dict[int, int]:
        """Get table offset mapping for address resolution.

        Returns:
            Dict mapping table index to offset within table data block
        """
        return self.table_offsets.copy()
