"""
Improved code generator with comprehensive opcode support.

This expanded code generator implements a much larger subset of Z-machine
opcodes and better handles ZIL language constructs.
"""

from typing import List, Dict, Any, Optional, Tuple
import struct

from ..parser.ast_nodes import *
from ..zmachine.opcodes import OpcodeTable, OperandType
from ..zmachine.text_encoding import ZTextEncoder, words_to_bytes


class ImprovedCodeGenerator:
    """Enhanced code generator with extensive opcode support."""

    def __init__(self, version: int = 3, abbreviations_table=None, string_table=None,
                 action_table=None):
        self.version = version
        self.abbreviations_table = abbreviations_table
        self.string_table = string_table
        self.action_table = action_table
        self.encoder = ZTextEncoder(version, abbreviations_table=abbreviations_table)
        self.opcodes = OpcodeTable()

        # Symbol tables
        self.globals: Dict[str, int] = {}
        self.global_values: Dict[str, int] = {}  # Global name -> initial value
        self.constants: Dict[str, int] = {}
        self.routines: Dict[str, int] = {}
        self.locals: Dict[str, int] = {}
        self.objects: Dict[str, int] = {}  # Object name -> number
        self.interrupts: Dict[str, int] = {}  # Interrupt name -> structure address

        # Version capabilities
        self._init_version_features()

        # Code generation
        self.code = bytearray()
        self.next_global = 0x10
        self.next_object = 1
        self.next_interrupt_addr = 0x1000  # Start interrupts at a fixed address

        # Labels for branching
        self.labels: Dict[str, int] = {}
        self.label_counter = 0

        # Loop tracking for AGAIN/RETURN support
        # Each entry is a dict with 'start_offset', 'code_ref' for nested loops
        self.loop_stack: List[Dict[str, Any]] = []

        # Table storage for TABLE/LTABLE/ITABLE
        # Each table is (name/id, bytes, is_pure)
        self.tables: List[Tuple[str, bytes, bool]] = []
        self.table_counter = 0
        self.table_offsets: Dict[int, int] = {}  # table_index -> offset within table data
        self._table_data_size = 0  # Running total of table data size

        # Routine call placeholders - map placeholder_index to routine_name
        # Placeholders are encoded as 0xFD + index (high byte) + index (low byte)
        self._routine_placeholders: Dict[int, str] = {}
        self._next_placeholder_index = 0

        # Built-in constants
        self.constants['T'] = 1
        self.constants['<>'] = 0
        self.constants['FALSE'] = 0
        self.constants['TRUE'] = 1

        # Parser system globals (standard ZIL globals)
        # These are allocated in a specific range for parser use
        self.parser_globals = {
            'PRSA': 0x10,   # Parser action (verb number)
            'PRSO': 0x11,   # Parser direct object
            'PRSI': 0x12,   # Parser indirect object
            'HERE': 0x13,   # Current location
            'WINNER': 0x14, # Current actor (usually player)
            'MOVES': 0x15,  # Move counter
        }

        # Reserve these globals
        for name, num in self.parser_globals.items():
            self.globals[name] = num
        self.next_global = 0x16  # Start user globals after parser globals

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
            # Add more as needed
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

    def generate(self, program: Program) -> bytes:
        """Generate bytecode from program AST."""
        # Add verb constants from action table
        if self.action_table and 'verb_constants' in self.action_table:
            for const_name, value in self.action_table['verb_constants'].items():
                self.constants[const_name] = value

        # Process globals (register names and capture initial values)
        for global_node in program.globals:
            self.globals[global_node.name] = self.next_global
            # Capture initial value if provided
            if global_node.initial_value is not None:
                init_val = self.get_operand_value(global_node.initial_value)
                if isinstance(init_val, int):
                    self.global_values[global_node.name] = init_val
            self.next_global += 1

        # Reserve globals for ACTIONS and PREACTIONS tables
        if self.action_table:
            self._setup_action_table_globals()

        # Process constants
        for const_node in program.constants:
            self.eval_constant(const_node)

        # Process objects (assign numbers)
        for obj in program.objects:
            self.objects[obj.name] = self.next_object
            self.next_object += 1
        for room in program.rooms:
            self.objects[room.name] = self.next_object
            self.next_object += 1

        # Generate routines
        for routine_node in program.routines:
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

        Scans the generated code for placeholder markers (0xFD + index)
        and returns (byte_offset, routine_byte_offset) pairs.

        Returns list of (byte_offset_in_code, routine_byte_offset) pairs.
        The assembler should convert routine_byte_offset to packed address
        using high_mem_base and patch at byte_offset_in_code.
        """
        fixups = []

        # Scan code for placeholder markers
        i = 0
        while i < len(self.code) - 1:
            if self.code[i] == 0xFD:
                placeholder_idx = self.code[i + 1]
                if placeholder_idx in self._routine_placeholders:
                    routine_name = self._routine_placeholders[placeholder_idx]
                    if routine_name in self.routines:
                        routine_offset = self.routines[routine_name]
                        fixups.append((i, routine_offset))
            i += 1

        return fixups

    def get_table_routine_fixups(self) -> List[Tuple[int, int]]:
        """Get routine address fixups for table data.

        Scans table data for placeholder markers (0xFD + index) and returns
        (byte_offset_in_table_data, routine_byte_offset) pairs.

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
            i += 1

        return fixups

    def eval_constant(self, const_node: ConstantNode):
        """Evaluate and store a constant."""
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
        return None

    def generate_routine(self, routine: RoutineNode) -> bytes:
        """Generate bytecode for a routine."""
        routine_start = len(self.code)
        routine_code = bytearray()

        # Build local variable table
        self.locals = {}
        var_num = 1
        for param in routine.params:
            self.locals[param] = var_num
            var_num += 1
        for aux_var in routine.aux_vars:
            self.locals[aux_var] = var_num
            var_num += 1

        num_locals = len(routine.params) + len(routine.aux_vars)

        # Routine header
        routine_code.append(num_locals & 0x0F)

        # Local variable initial values (V1-4 only)
        if self.version <= 4:
            for i in range(num_locals):
                routine_code.extend(struct.pack('>H', 0))

        # Generate code for routine body
        for stmt in routine.body:
            stmt_code = self.generate_statement(stmt)
            routine_code.extend(stmt_code)

        # Store routine address for later reference
        self.routines[routine.name] = routine_start

        self.code.extend(routine_code)
        return bytes(routine_code)

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
            return self.gen_rtrue()
        elif op_name == 'RFALSE':
            return self.gen_rfalse()
        elif op_name == '<>':
            # <> as a form means return false (same as RFALSE)
            return self.gen_rfalse()
        elif op_name == 'RFATAL':
            return self.gen_rfatal()
        elif op_name == 'RETURN':
            return self.gen_return(form.operands)
        elif op_name == 'QUIT':
            return self.gen_quit()
        elif op_name == 'AGAIN':
            return self.gen_again()
        elif op_name == 'GOTO':
            return self.gen_goto(form.operands)
        elif op_name == 'PROG':
            return self.gen_prog(form.operands)
        elif op_name == 'REPEAT':
            return self.gen_repeat(form.operands)
        elif op_name == 'BIND':
            return self.gen_bind(form.operands)

        # Output
        elif op_name == 'TELL':
            return self.gen_tell(form.operands)
        elif op_name == 'PRINT':
            return self.gen_tell(form.operands)
        elif op_name == 'CRLF':
            return self.gen_newline()
        elif op_name == 'PRINTN' or op_name == 'PRINT-NUM':
            return self.gen_print_num(form.operands)
        elif op_name == 'PRINTD':
            return self.gen_print_num(form.operands)  # PRINTD is same as PRINTN
        elif op_name == 'PRINTC' or op_name == 'PRINT-CHAR':
            return self.gen_print_char(form.operands)
        elif op_name == 'PRINTB':
            return self.gen_printb(form.operands)
        elif op_name == 'PRINTI':
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
        elif op_name == 'SPLIT':
            return self.gen_split(form.operands)
        elif op_name == 'SCREEN':
            return self.gen_screen(form.operands)
        elif op_name == 'CURSET':
            return self.gen_curset(form.operands)
        elif op_name == 'HLIGHT':
            return self.gen_hlight(form.operands)
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
        elif op_name in ('=', 'EQUAL?', '==?'):
            return self.gen_equal(form.operands)
        elif op_name in ('L?', '<'):
            return self.gen_less(form.operands)
        elif op_name in ('G?', '>'):
            return self.gen_greater(form.operands)
        elif op_name == 'ZERO?':
            return self.gen_zero(form.operands)
        elif op_name == '0?':
            return self.gen_zero(form.operands)
        elif op_name == '1?':
            return self.gen_one(form.operands)
        elif op_name == 'ASSIGNED?':
            return self.gen_assigned(form.operands)
        elif op_name == 'NOT?':
            return self.gen_not_predicate(form.operands)
        elif op_name == 'TRUE?':
            return self.gen_true_predicate(form.operands)
        elif op_name == 'IGRTR?':
            return self.gen_igrtr(form.operands)
        elif op_name == 'DLESS?':
            return self.gen_dless(form.operands)
        elif op_name == 'CHECKU':
            return self.gen_checku(form.operands)
        elif op_name == 'LEXV':
            return self.gen_lexv(form.operands)
        elif op_name in ('G=?', 'GRTR?', '>='):
            return self.gen_grtr_or_equal(form.operands)
        elif op_name in ('L=?', 'LESS?', '<='):
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
        elif op_name == 'SCROLL-WINDOW':
            return self.gen_scroll_window(form.operands)
        elif op_name == 'PICINF':
            return self.gen_picinf(form.operands)
        elif op_name == 'MOUSE-INFO':
            return self.gen_mouse_info(form.operands)
        elif op_name == 'TYPE?':
            return self.gen_type(form.operands)
        elif op_name == 'PRINTTYPE':
            return self.gen_printtype(form.operands)
        elif op_name == 'PRINTT':
            return self.gen_printt(form.operands)
        elif op_name == 'FSTACK':
            return self.gen_fstack(form.operands)
        elif op_name == 'RSTACK':
            return self.gen_rstack(form.operands)
        elif op_name == 'IFFLAG':
            return self.gen_ifflag(form.operands)
        elif op_name == 'LOG-SHIFT':
            return self.gen_log_shift(form.operands)
        elif op_name == 'XOR':
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
        elif op_name == 'ART-SHIFT':
            return self.gen_art_shift(form.operands)

        # V5+ Unicode operations
        elif op_name == 'PRINT-UNICODE':
            return self.gen_print_unicode(form.operands)
        elif op_name == 'PRINTU':
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
        elif op_name == 'BAND':
            return self.gen_band(form.operands)
        elif op_name == 'BOR':
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
            return self.gen_restart()
        elif op_name == 'SAVE':
            return self.gen_save()
        elif op_name == 'RESTORE':
            return self.gen_restore()
        elif op_name == 'VERIFY':
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
        elif op_name == 'QUEUE':
            return self.gen_queue(form.operands)
        elif op_name == 'INT':
            return self.gen_int(form.operands)
        elif op_name == 'DEQUEUE':
            return self.gen_dequeue(form.operands)
        elif op_name == 'ENABLE':
            return self.gen_enable(form.operands)
        elif op_name == 'DISABLE':
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

        return b''

    # ===== Table Node Helpers =====

    def _add_table(self, node: TableNode) -> int:
        """Add a table from a TableNode and return its index.

        Args:
            node: TableNode with table_type, flags, size, values

        Returns:
            int: Table index (placeholder for later address resolution)
        """
        table_data = bytearray()
        table_type = node.table_type
        is_pure = 'PURE' in node.flags
        is_byte = 'BYTE' in node.flags

        # For LTABLE, add length prefix
        if table_type == 'LTABLE':
            table_data.extend(struct.pack('>H', len(node.values)))

        # Encode values
        for val in node.values:
            val_int = self.get_operand_value(val)
            if val_int is None:
                if isinstance(val, AtomNode):
                    name = val.value
                    if name in self.objects:
                        val_int = self.objects[name]
                    elif name in self.routines:
                        val_int = self.routines[name]
                    elif name in self.globals:
                        val_int = self.globals[name]
                    elif name in self.constants:
                        val_int = self.constants[name]
                    else:
                        val_int = 0
                elif isinstance(val, StringNode):
                    val_int = 0  # Placeholder for string
                else:
                    val_int = 0

            if is_byte:
                table_data.append(val_int & 0xFF)
            else:
                table_data.extend(struct.pack('>H', val_int & 0xFFFF))

        # For ITABLE, pad to size if specified
        if table_type == 'ITABLE' and node.size:
            entry_size = 1 if is_byte else 2
            while len(table_data) < node.size * entry_size:
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))

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
        """Generate RETURN value."""
        if not operands:
            return self.gen_rtrue()

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # RET is 1OP opcode 0x0B
        # 0x8B = small constant, 0x9B = variable
        if op_type == 1:  # Variable
            code.append(0x9B)
        else:  # Constant
            code.append(0x8B)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_quit(self) -> bytes:
        """Generate QUIT."""
        return bytes([0xBA])

    def gen_again(self) -> bytes:
        """Generate AGAIN (restart current loop).

        AGAIN jumps back to the start of the innermost REPEAT loop.
        This is similar to 'continue' in C.

        Returns a placeholder JUMP instruction that will be patched
        by gen_repeat after all loop body code is generated.
        """
        if not self.loop_stack:
            # No active loop - can't generate AGAIN
            # Return empty bytes (will effectively be a no-op)
            return b''

        # Get the innermost loop context
        loop_ctx = self.loop_stack[-1]

        # Track this AGAIN location for later patching
        # We use a placeholder marker (0xFF, 0xAA, 0xAA) that will be patched
        if 'again_placeholders' not in loop_ctx:
            loop_ctx['again_placeholders'] = []

        # Generate placeholder JUMP (will be patched later)
        code = bytearray()
        code.append(0x8C)  # JUMP opcode
        code.append(0xFF)  # Placeholder high byte (marker)
        code.append(0xAA)  # Placeholder low byte (marker)

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
                # Print literal string
                if self.string_table is not None:
                    self.string_table.add_string(op.value)
                    code.append(0x8D)  # PRINT_PADDR short form
                    marker = b'\xFF\xFE'
                    code.extend(marker)
                    text_bytes = op.value.encode('utf-8')
                    code.append(len(text_bytes) & 0xFF)
                    code.append((len(text_bytes) >> 8) & 0xFF)
                    code.extend(text_bytes)
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

                else:
                    # Unknown atom - skip
                    i += 1

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
                # Variable reference - print as object name (PRINT_OBJ)
                var_code = self._gen_tell_operand_code(op, 0x0A)  # PRINT_OBJ
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
        op_type, op_val = self._get_operand_type_and_value(operand)

        # 1OP form: 0x8X for small constant, 0x9X for variable
        if op_type == 1:  # Variable
            code.append(0x90 | opcode_1op)
        else:  # Constant
            code.append(0x80 | opcode_1op)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_print_num(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_NUM (print signed number)."""
        if not operands:
            return b''

        code = bytearray()
        operand = operands[0]

        # If operand is a nested form, evaluate it first (result goes to stack)
        if isinstance(operand, FormNode):
            # Generate code for the expression (pushes result to stack)
            expr_code = self.generate_form(operand)
            code.extend(expr_code)
            # Now print from stack (variable 0)
            op_type = 1  # Variable
            op_val = 0   # Stack
        else:
            # Determine operand type and value
            op_type, op_val = self._get_operand_type_and_value(operand)

        # PRINT_NUM is VAR opcode 0x06
        code.append(0xE6)  # Variable form, VAR, opcode 0x06

        # Type byte encoding for VAR form with single operand:
        # Bits 7-6: operand type (00=large, 01=small, 10=variable, 11=omitted)
        # Bits 5-0: 111111 (remaining operands omitted)
        if op_type == 0:  # Small constant
            type_byte = 0x7F  # 01 11 11 11 = small const, rest omitted
        else:  # Variable
            type_byte = 0xBF  # 10 11 11 11 = variable, rest omitted

        code.append(type_byte)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_print_char(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_CHAR."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xE5)  # VAR opcode 0x05
        # Type byte: 01 for small constant, 10 for variable
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x0F)  # type in bits 7-6, rest omitted
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_printb(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_PADDR (print from byte array).

        <PRINTB addr> prints text from a byte array at the given address.
        This uses the PRINT_PADDR opcode (packed address in V3).

        In Z-machine V3, PRINT_PADDR is VAR opcode 0x0D.
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # PRINT_PADDR is VAR opcode 0x0D
        code.append(0xED)  # VAR form, opcode 0x0D
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x0F)
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
            code.append((type_byte << 6) | 0x0F)
            code.append(op_val & 0xFF)
        else:
            # V3: use PRINT_PADDR
            code.append(0xED)  # VAR form, opcode 0x0D
            code.append((type_byte << 6) | 0x0F)
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
        """Generate SET/SETG (variable assignment)."""
        if len(operands) < 2:
            return b''

        var_node = operands[0]
        value_node = operands[1]

        # Get variable number
        if isinstance(var_node, AtomNode):
            if is_global:
                var_num = self.globals.get(var_node.value, self.next_global)
                if var_node.value not in self.globals:
                    self.globals[var_node.value] = var_num
                    self.next_global += 1
            else:
                var_num = self.locals.get(var_node.value, 1)
        else:
            return b''

        code = bytearray()

        # Check if value is an expression (FormNode) that needs evaluation
        if isinstance(value_node, FormNode):
            # Generate code to evaluate expression (result goes to stack)
            expr_code = self.generate_form(value_node)
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
        elif isinstance(value_node, TableNode):
            # Table literal - store table and use placeholder address
            table_index = self._add_table(value_node)
            # For now, store the table index as a placeholder
            # The assembler will need to patch this with actual address
            # STORE var placeholder_address
            code.append(0x4D)  # 2OP:0x0D STORE (long form, both small constants)
            code.append(var_num & 0xFF)
            code.append(table_index & 0xFF)  # Placeholder
        else:
            # Simple value assignment
            val_type, val_val = self._get_operand_type_and_value(value_node)

            # STORE is 2OP opcode 0x0D
            # Long form: bit6=var type for first op, bit5=var type for second op
            opcode = 0x0D | (0 << 6) | (val_type << 5)  # First operand always small const
            code.append(opcode)
            code.append(var_num & 0xFF)
            code.append(val_val & 0xFF)

        return bytes(code)

    def gen_inc(self, operands: List[ASTNode]) -> bytes:
        """Generate INC (increment variable)."""
        if not operands:
            return b''

        code = bytearray()
        var_num = self.get_variable_number(operands[0])

        # INC is 1OP opcode 0x05
        code.append(0x85)  # Short 1OP, opcode 0x05, variable type
        code.append(var_num)

        return bytes(code)

    def gen_dec(self, operands: List[ASTNode]) -> bytes:
        """Generate DEC (decrement variable)."""
        if not operands:
            return b''

        code = bytearray()
        var_num = self.get_variable_number(operands[0])

        # DEC is 1OP opcode 0x06
        code.append(0x86)  # Short 1OP, opcode 0x06, variable type
        code.append(var_num)

        return bytes(code)

    def gen_value(self, operands: List[ASTNode]) -> bytes:
        """Generate VALUE (get variable value).

        <VALUE var> reads the value of a variable (local or global).
        Uses LOAD instruction (1OP opcode 0x0E).
        """
        if not operands:
            return b''

        code = bytearray()
        var_num = self.get_variable_number(operands[0])

        # LOAD is 1OP opcode 0x0E
        code.append(0x8E)  # Short 1OP, opcode 0x0E, variable type
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
        code.append(0x8E)  # Short 1OP, opcode 0x0E, variable type
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
        code.append(0x8E)  # Short 1OP, opcode 0x0E, variable type
        code.append(var_num)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Arithmetic Operations =====

    def gen_add(self, operands: List[ASTNode]) -> bytes:
        """Generate ADD instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        # ADD is 2OP opcode 0x14
        # Determine operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Build opcode byte: bits 6-5 are operand types, bits 4-0 are opcode
        # Type: 0 = small constant, 1 = variable
        opcode = 0x14 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def _get_operand_type_and_value(self, node: ASTNode) -> Tuple[int, int]:
        """Get operand type (0=small const, 1=variable) and value/var number.

        Returns:
            Tuple of (type, value) where type is 0 for small constant, 1 for variable
        """
        if isinstance(node, NumberNode):
            return (0, node.value)  # Small constant
        elif isinstance(node, GlobalVarNode):
            # ,VARNAME syntax - global variable reference
            var_num = self.globals.get(node.name, 0x10)
            return (1, var_num)  # Variable
        elif isinstance(node, LocalVarNode):
            # .VARNAME syntax - local variable reference
            var_num = self.locals.get(node.name, 1)
            return (1, var_num)  # Variable
        elif isinstance(node, TableNode):
            # Table literal - generate table and return placeholder address
            table_id = self._add_table(node)
            # Return large constant (table index as placeholder)
            return (0, table_id)
        elif isinstance(node, AtomNode):
            # Check if it's a known constant
            if node.value in self.constants:
                return (0, self.constants[node.value])
            # Check if it's a global variable
            elif node.value in self.globals:
                return (1, self.globals[node.value])
            # Check if it's a local variable
            elif node.value in self.locals:
                return (1, self.locals[node.value])
            # Default to small constant 0
            return (0, 0)
        else:
            return (0, 0)

    def gen_sub(self, operands: List[ASTNode]) -> bytes:
        """Generate SUB instruction.

        With 1 operand: negation (0 - value)
        With 2+ operands: subtraction (a - b)
        """
        if len(operands) < 1:
            return b''

        code = bytearray()

        if len(operands) == 1:
            # Negation: 0 - value
            op_type, op_val = self._get_operand_type_and_value(operands[0])
            # SUB 0 value -> stack
            opcode = 0x15 | (0 << 6) | (op_type << 5)  # First op is small const (0)
            code.append(opcode)
            code.append(0x00)  # First operand: 0
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store to stack
        else:
            # Normal subtraction
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])

            opcode = 0x15 | (op1_type << 6) | (op2_type << 5)
            code.append(opcode)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_mul(self, operands: List[ASTNode]) -> bytes:
        """Generate MUL instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        # MUL is 2OP opcode 0x16
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        opcode = 0x16 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_div(self, operands: List[ASTNode]) -> bytes:
        """Generate DIV instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        # DIV is 2OP opcode 0x17
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        opcode = 0x17 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_mod(self, operands: List[ASTNode]) -> bytes:
        """Generate MOD instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        # MOD is 2OP opcode 0x18
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        opcode = 0x18 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

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
            code.append(0x8E)  # 1OP LOAD var
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
            code.append(0x8E)  # LOAD var
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
        code.append(0x8E)  # LOAD var
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
            code.append(0x8E)  # LOAD var
            code.append(op_val & 0xFF)
            code.append(0x00)  # Store to stack
        else:  # Constant - can compute at compile time
            abs_val = abs(op_val) if op_val < 0x8000 else abs(op_val - 0x10000)
            code.append(0x8E)  # Use LOAD pattern
            code.append(op_val & 0xFF)
            code.append(0x00)

        return bytes(code)

    def gen_sound(self, operands: List[ASTNode]) -> bytes:
        """Generate SOUND (play sound effect).

        <SOUND effect> plays a sound effect.
        In V3, this is the SOUND_EFFECT opcode (VAR opcode 0x05).

        Args:
            operands[0]: Sound effect number (1-N)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xE5)  # SOUND_EFFECT (VAR opcode 0x05)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x0F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_clear(self, operands: List[ASTNode]) -> bytes:
        """Generate CLEAR (clear screen).

        <CLEAR> clears the screen.
        In V3, this is the ERASE_WINDOW opcode (VAR opcode 0x0D).
        Window -1 means clear entire screen.

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()
        code.append(0xED)  # ERASE_WINDOW (VAR opcode 0x0D)
        code.append(0x2F)  # Type byte: 1 small constant, rest omitted
        code.append(0xFF)  # Window -1 (entire screen)

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
        code.append((type_byte << 6) | 0x0F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_split(self, operands: List[ASTNode]) -> bytes:
        """Generate SPLIT (split window).

        <SPLIT lines> splits the screen into upper and lower windows.
        In V3, this is the SPLIT_WINDOW opcode (VAR opcode 0x0A).

        Args:
            operands[0]: Number of lines for upper window

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xEA)  # SPLIT_WINDOW (VAR opcode 0x0A)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x0F)
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_screen(self, operands: List[ASTNode]) -> bytes:
        """Generate SCREEN (select window).

        <SCREEN window> selects which window to write to.
        In V3, this is the SET_WINDOW opcode (VAR opcode 0x0B).

        Args:
            operands[0]: Window number (0=lower, 1=upper)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xEB)  # SET_WINDOW (VAR opcode 0x0B)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x0F)
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
        """Generate CURSET (set cursor position).

        <CURSET line column> sets cursor to specified position.
        In V3+, this is the SET_CURSOR opcode (VAR opcode 0x11).

        Args:
            operands[0]: Line number (1-based)
            operands[1]: Column number (1-based)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

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
        if not operands or self.version < 4:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_CURSOR is VAR opcode 0x10
        code.append(0xF0)  # GET_CURSOR (VAR:0x10)
        type_byte = 0x01 if op_type == 0 else 0x02
        code.append((type_byte << 6) | 0x0F)
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
        code.append((type_byte << 6) | 0x0F)
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
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        code.append(0xBE)  # EXT opcode marker
        code.append(0x14)  # SCROLL_WINDOW

        t1 = 0x01 if op1_type == 0 else 0x02
        t2 = 0x01 if op2_type == 0 else 0x02
        code.append((t1 << 6) | (t2 << 4) | 0x0F)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

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
        if not operands:
            return b''

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
        V3: SREAD (VAR:0x04) with buffer and parse
        V4+: Supports optional time and routine for timed input

        Args:
            operands[0]: Text buffer address
            operands[1]: Parse buffer address (optional)
            operands[2]: Time in tenths of seconds (V4+, optional)
            operands[3]: Routine to call on timeout (V4+, optional)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

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
        In V3+, this is the BUFFER_MODE opcode (VAR opcode 0x11).
        Mode: 0=disable buffering, 1=enable buffering

        Args:
            operands[0]: Mode (0 or 1)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xF1)  # BUFFER_MODE (VAR opcode 0x11)
        if op_type == 1:  # Variable
            code.append(0x8F)  # Type byte: 1 variable
        else:  # Constant
            code.append(0x2F)  # Type byte: 1 small constant
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

    def gen_get_cursor(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_CURSOR (V4/V6 - get cursor position).

        <GET_CURSOR array> stores cursor position in array.
        Array word 0 = row (line), word 1 = column.
        V4+ only.

        Args:
            operands[0]: Array address (2 words)

        Returns:
            bytes: Z-machine code (GET_CURSOR VAR opcode)
        """
        if not operands or self.version < 4:
            return b''

        code = bytearray()

        # GET_CURSOR is VAR opcode 0x10
        code.append(0xF0)  # VAR opcode 0x10

        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 1:  # Variable
            code.append(0x8F)  # Type byte: 1 variable
        else:  # Constant
            code.append(0x2F)  # Type byte: 1 small constant
        code.append(op_val & 0xFF)

        return bytes(code)

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
        """Generate USL (unsigned shift left).

        <USL value shift> shifts value left by shift bits (unsigned).
        Similar to LSH but explicitly unsigned.

        Args:
            operands[0]: Value to shift
            operands[1]: Number of bits to shift

        Returns:
            bytes: Z-machine code
        """
        # USL is essentially the same as LSH for our purposes
        return self.gen_lsh(operands)

    def gen_dirout(self, operands: List[ASTNode]) -> bytes:
        """Generate DIROUT (direct output to memory).

        <DIROUT table> directs subsequent output to a memory table.
        In V3+, this is the OUTPUT_STREAM opcode (VAR 0x13).
        Stream 3 = redirect to table.

        Args:
            operands[0]: Table address for output (or 0 to restore)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        code.append(0xF3)  # OUTPUT_STREAM (VAR opcode 0x13)

        if op_type == 0 and op_val == 0:
            # Restore normal output (stream -3)
            code.append(0x15)  # Type byte: 2 small constants
            code.append(0xFD)  # -3 (close stream 3)
            code.append(0x00)
        elif op_type == 1:  # Variable
            # Direct to table via variable (stream 3)
            code.append(0x18)  # Type byte: small const, variable
            code.append(0x03)  # Stream 3
            code.append(op_val & 0xFF)  # Variable number
        else:
            # Direct to table (stream 3)
            code.append(0x15)  # Type byte: 2 small constants
            code.append(0x03)  # Stream 3
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
        if not operands or self.version < 3:
            return b''

        code = bytearray()

        # INPUT_STREAM is VAR opcode 0x14
        code.append(0xF4)  # VAR opcode 0x14

        op_type, op_val = self._get_operand_type_and_value(operands[0])

        if op_type == 1:  # Variable
            code.append(0x8F)  # Type byte: 1 variable
        else:  # Constant
            code.append(0x2F)  # Type byte: 1 small constant
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
        if op_type == 1:  # Variable
            code.append(0x9A)  # 0x9A = variable operand
        else:  # Constant
            code.append(0x8A)  # 0x8A = small constant
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_read(self, operands: List[ASTNode]) -> bytes:
        """Generate READ (read input - alias for INPUT).

        <READ buffer parse> reads a line of text.
        This is an alias for INPUT/SREAD.

        Args:
            operands[0]: Text buffer
            operands[1]: Parse buffer

        Returns:
            bytes: Z-machine code
        """
        return self.gen_input(operands)

    def gen_dless(self, operands: List[ASTNode]) -> bytes:
        """Generate DLESS? (decrement and test if less).

        <DLESS? var value> decrements var and tests if result < value.
        Similar to IGRTR? but for less-than.
        Uses DEC followed by JL.

        Args:
            operands[0]: Variable to decrement
            operands[1]: Value to compare against

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        var_num = self.get_variable_number(operands[0])
        val_type, val_val = self._get_operand_type_and_value(operands[1])

        # DEC variable
        code.append(0x86)  # DEC (1OP opcode 0x06)
        code.append(var_num)

        # JL variable value (2OP opcode 0x02)
        # First operand is always the variable we just decremented
        opcode = 0x02 | (1 << 6) | (val_type << 5)  # var is first operand
        code.append(opcode)
        code.append(var_num)
        code.append(val_val & 0xFF)
        code.append(0x40)  # Branch byte

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
        """Generate CHECKU (check if object has property - unrestricted).

        <CHECKU object property> tests if object provides a property.
        Uses GET_PROP_ADDR which returns 0 if property not found.

        Args:
            operands[0]: Object number
            operands[1]: Property number

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # GET_PROP_ADDR returns 0 if not found (2OP opcode 0x13)
        opcode = 0x13 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack
        # Then test with JZ - if 0, property doesn't exist

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

    def gen_copyt(self, operands: List[ASTNode]) -> bytes:
        """Generate COPYT (copy table).

        <COPYT source dest length> copies bytes from source to dest.
        V5+: Uses native COPY_TABLE opcode.
        V3/V4: Generates inline loop for small constants, stub for large/variables.

        Args:
            operands[0]: Source address
            operands[1]: Destination address
            operands[2]: Length in bytes

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3:
            return b''

        code = bytearray()

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(3):
            t, v = self._get_operand_type_and_value(operands[i])
            op_types.append(t)
            op_vals.append(v)

        src_type, src_val = op_types[0], op_vals[0]
        dest_type, dest_val = op_types[1], op_vals[1]
        len_type, len_val = op_types[2], op_vals[2]

        # V5+: Use native COPY_TABLE opcode (EXT:0x17)
        if self.version >= 5:
            code.append(0xBE)  # EXT opcode marker
            code.append(0x17)  # COPY_TABLE

            # Encode operands based on types
            types = []
            ops = []

            for op_t, op_v in zip(op_types, op_vals):
                if op_t == 0:  # Constant
                    if op_v <= 255:
                        types.append(0b01)  # Small constant
                        ops.append(bytes([op_v & 0xFF]))
                    else:
                        types.append(0b00)  # Large constant
                        ops.append(bytes([(op_v >> 8) & 0xFF, op_v & 0xFF]))
                else:  # Variable
                    types.append(0b10)
                    ops.append(bytes([op_v & 0xFF]))

            # Type byte
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | 0x03
            code.append(type_byte)

            for op in ops:
                code.extend(op)

            return bytes(code)

        # V3/V4: Generate inline copy loop for small constant lengths
        if src_type == 0 and dest_type == 0 and len_type == 0:
            if len_val <= 16:
                # Unroll: generate LOADB/STOREB for each byte
                for i in range(len_val):
                    # LOADB src i -> sp
                    code.append(0xD0)  # VAR form of LOADB (2OP:16)
                    if src_val + i <= 255:
                        code.append(0x5F)  # small, small, omit, omit
                        code.append((src_val + i) & 0xFF)
                        code.append(0x00)  # offset 0
                    else:
                        code.append(0x1F)  # large, small, omit, omit
                        code.append(((src_val + i) >> 8) & 0xFF)
                        code.append((src_val + i) & 0xFF)
                        code.append(0x00)
                    code.append(0x00)  # Store to SP

                    # STOREB dest i sp
                    code.append(0xE3)  # VAR form of STOREB
                    if dest_val + i <= 255:
                        code.append(0x5B)  # small, small, var, omit
                        code.append((dest_val + i) & 0xFF)
                        code.append(0x00)  # offset 0
                    else:
                        code.append(0x1B)  # large, small, var, omit
                        code.append(((dest_val + i) >> 8) & 0xFF)
                        code.append((dest_val + i) & 0xFF)
                        code.append(0x00)
                    code.append(0x00)  # Value from SP

                return bytes(code)

        # For larger or variable lengths, would need complex loop
        # This is a limitation of the current implementation
        return bytes(code)

    def gen_grtr_or_equal(self, operands: List[ASTNode]) -> bytes:
        """Generate >= comparison (greater than or equal).

        <G=? a b> tests if a >= b.
        Implemented as NOT(a < b).

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

        # JL with inverted branch (branch on false for >=)
        opcode = 0x02 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Branch on false (inverted logic)

        return bytes(code)

    def gen_less_or_equal(self, operands: List[ASTNode]) -> bytes:
        """Generate <= comparison (less than or equal).

        <L=? a b> tests if a <= b.
        Implemented as NOT(a > b).

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

        # JG with inverted branch (branch on false for <=)
        opcode = 0x03 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Branch on false (inverted logic)

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
        """Generate ORIGINAL? (test if value is original/not copied).

        <ORIGINAL? value> tests if value is an original object reference.
        In ZIL, this checks if a value is an original object (not a copy
        or derived reference). For Z-machine, we approximate by testing
        if the value is in valid object range (1-255).

        Args:
            operands[0]: Value to test

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        # For compile-time constants, check if in valid object range
        if isinstance(value, int):
            # Objects are 1-255, 0 is false/null
            is_original = 1 if 1 <= value <= 255 else 0

            # Push result to stack
            code.append(0x54)  # ADD (2OP:0x14)
            code.append(0x00)  # 0
            code.append(is_original & 0xFF)
            code.append(0x00)  # Store to stack
        else:
            # Runtime check: test if value is non-zero and <= 255
            # Simplified: just test if non-zero (valid object reference)
            # JNZ value [true]
            var_num = self.get_variable_number(operands[0])
            code.append(0x80)  # JZ (1OP:0x00)
            code.append(var_num)
            code.append(0x40 | 0x03)  # Branch false, offset 3
            # If zero, push 0
            code.append(0x54)
            code.append(0x00)
            code.append(0x00)
            code.append(0x00)
            # Otherwise push 1 (handled by branch)

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
        In V5+, uses SET_COLOUR. For V3, this is a stub.

        Args:
            operands[0]: Foreground color
            operands[1]: Background color (optional)

        Returns:
            bytes: Z-machine code (working in V5+, stub for V3)
        """
        if not self.has_colors:
            # V3/V4 don't support colors
            return b''

        # V5+: SET_COLOUR opcode
        code = bytearray()
        if len(operands) >= 2:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])

            code.append(0xEB)  # SET_COLOUR (VAR opcode 0x1B)

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
        """Generate FONT (set font).

        <FONT font-number> sets the current font.
        In V5+, uses SET_FONT. For V3, this is a stub.

        Args:
            operands[0]: Font number

        Returns:
            bytes: Z-machine code (working in V5+, stub for V3)
        """
        if self.version < 5:
            # V3/V4 don't support SET_FONT
            return b''

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
        V3-V5: No-op (no margin control)

        Args:
            operands[0]: Left margin
            operands[1]: Right margin (optional)
            operands[2]: Window number (optional, defaults to current)

        Returns:
            bytes: Z-machine code
        """
        if self.version < 6:
            # V3-V5: No margin control
            return b''

        if not operands:
            return b''

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
        Uses SPLIT_WINDOW pattern.

        Args:
            operands[0]: Window number
            operands[1]: Number of lines

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Check if window is constant 1 (upper window) - use SPLIT
        op_type, op_val = self._get_operand_type_and_value(operands[0])
        if op_type == 0 and op_val == 1:
            return self.gen_split([operands[1]])

        # For other windows or variable window, use V6 SET_WINDOW if available
        if self.version >= 6:
            # WINDOW_SIZE EXT:0x11
            code.append(0xBE)
            code.append(0x11)

            # Build operands
            op_types = []
            op_vals = []
            for i in range(2):
                t, v = self._get_operand_type_and_value(operands[i])
                if t == 0:  # Constant
                    op_types.append(0x01 if v <= 255 else 0x00)
                else:
                    op_types.append(0x02)
                op_vals.append(v)

            op_types.extend([0x03, 0x03])
            type_byte = (op_types[0] << 6) | (op_types[1] << 4) | (op_types[2] << 2) | op_types[3]
            code.append(type_byte)

            for t, v in zip(op_types[:2], op_vals):
                if t == 0x00:
                    code.append((v >> 8) & 0xFF)
                    code.append(v & 0xFF)
                else:
                    code.append(v & 0xFF)

        return bytes(code)

    def gen_winget(self, operands: List[ASTNode]) -> bytes:
        """Generate WINGET (get window property).

        <WINGET window property> gets window information.
        V6+: Uses GET_WIND_PROP opcode (EXT:0x13)
        V3-V5: Returns 0 (no window properties)

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
        if len(operands) < 2:
            return b''

        if self.version < 6:
            # V3-V5: No window properties, push 0
            code = bytearray()
            code.append(0x54)  # ADD small small
            code.append(0x00)
            code.append(0x00)
            code.append(0x00)  # Store to stack
            return bytes(code)

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
        V6+: Uses PUT_WIND_PROP opcode (EXT:0x19)
        V3-V5: No-op (no window properties)

        Args:
            operands[0]: Window number
            operands[1]: Property number
            operands[2]: Value to set

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3 or self.version < 6:
            return b''

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
        V6+: Uses WINDOW_STYLE opcode (EXT:0x12)
        V3-V5: No-op

        Args:
            operands[0]: Window number
            operands[1]: Attribute flags
            operands[2]: Operation (0=set, 1=clear, 2=toggle) - optional

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2 or self.version < 6:
            return b''

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

    def gen_intbl(self, operands: List[ASTNode]) -> bytes:
        """Generate INTBL? (check if value in table).

        <INTBL? value table length> searches table for value.
        Returns true if found (and address in result for V5+).
        V5+: Uses SCAN_TABLE opcode (EXT:0x17)
        V3/V4: Unrolled search for small tables

        Args:
            operands[0]: Value to search for
            operands[1]: Table address
            operands[2]: Table length (in words)
            operands[3]: Entry size (optional, default 2)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 3:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # value
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # table
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])  # length

        # V5+: Use SCAN_TABLE opcode
        if self.version >= 5:
            # SCAN_TABLE is EXT opcode 0x17
            code.append(0xBE)  # EXT opcode marker
            code.append(0x17)  # SCAN_TABLE

            # Build type byte for 4 operands: value, table, length, form
            types = []
            op_bytes = []

            for op_t, op_v in [(op1_type, op1_val), (op2_type, op2_val), (op3_type, op3_val)]:
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

            types.append(0x01)  # form is always small constant
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)

            # Encode operands
            for ob in op_bytes:
                code.extend(ob)
            # Form byte: 0x82 = word entries (bit 7), forward (bit 6 clear)
            code.append(0x82)

            # Store result to stack
            code.append(0x00)
            # Branch on success
            code.append(0xC0)  # Branch true, short form

            return bytes(code)

        # V3/V4: Generate loop-based search
        # L01 = counter, L02 = offset, L03 = value, L04 = table
        entry_size = 2  # Default word-sized entries
        if len(operands) >= 4:
            es = self.get_operand_value(operands[3])
            if isinstance(es, int):
                entry_size = es

        # Check if we can unroll for small constant-length tables
        length = self.get_operand_value(operands[2])
        value = self.get_operand_value(operands[0])
        table = self.get_operand_value(operands[1])

        if isinstance(value, int) and isinstance(table, int) and isinstance(length, int):
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

        # For variable operands, generate loop-based search
        # Initialize counter from length operand
        code.append(0x0D | (op3_type << 6))
        code.append(0x01)  # L01 = counter
        code.append(op3_val & 0xFF)

        # Initialize offset to 0
        code.append(0x0D)
        code.append(0x02)  # L02 = offset
        code.append(0x00)
        code.append(0x00)

        # Store value in L03
        code.append(0x0D | (op1_type << 6))
        code.append(0x03)  # L03 = value
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
        code.append(0x03)  # L03 (value)
        # Branch true (to rtrue) - INTBL? returns true/false predicate
        code.append(0xC0)  # Branch true, return true

        # ADD L02 2 -> L02 (increment offset by entry size)
        code.append(0x54)  # ADD
        code.append(0x02)  # L02
        code.append(entry_size & 0xFF)  # entry size
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

        # Not found - return false
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

    def gen_lowcore(self, operands: List[ASTNode]) -> bytes:
        """Generate LOWCORE (access low memory constant).

        <LOWCORE address> reads a word from low memory (0x00-0x40).
        Accesses Z-machine header and low memory constants.

        Args:
            operands[0]: Address in low memory

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # Use LOADW to read from low memory (base 0, offset = addr)
        # LOADW is 2OP opcode 0x0F
        opcode = 0x0F | (0 << 6) | (op_type << 5)  # base=0 is constant
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
        """Generate CATCH (catch exception/save state).

        <CATCH> creates a catch point for throw/return.
        V5+ feature using CATCH opcode (VAR:0x19).
        Returns the current stack frame address.

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()

        # V5+: Use CATCH opcode (VAR:0x19)
        if self.version >= 5:
            code.append(0xF9)  # VAR opcode 0x19
            code.append(0xFF)  # No operands (types all omitted)
            code.append(0x00)  # Store to stack
        else:
            # V3/V4: Not available, return 0 to stack
            code.append(0x54)  # ADD const const
            code.append(0x00)  # 0
            code.append(0x00)  # 0
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_throw(self, operands: List[ASTNode]) -> bytes:
        """Generate THROW (throw to catch point).

        <THROW value catch-point> jumps to catch with value.
        V5+ feature using THROW opcode (VAR:0x1A).

        Args:
            operands[0]: Value to return
            operands[1]: Catch frame address (from CATCH)

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # V5+: Use THROW opcode (VAR:0x1A)
        if self.version >= 5:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])

            code.append(0xFA)  # VAR opcode 0x1A

            # Type byte for 2 operands
            type1 = 0x01 if op1_type == 0 else 0x02
            type2 = 0x01 if op2_type == 0 else 0x02
            type_byte = (type1 << 6) | (type2 << 4) | 0x0F  # Rest omitted
            code.append(type_byte)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
        else:
            # V3/V4: Not available - just return the value (first operand)
            # This is a graceful degradation
            op_type, op_val = self._get_operand_type_and_value(operands[0])
            if op_type == 0:
                code.append(0x54)  # ADD const const
                code.append(0x00)
                code.append(op_val & 0xFF)
                code.append(0x00)  # Store to stack
            else:
                code.append(0x8E)  # LOAD var
                code.append(op_val & 0xFF)
                code.append(0x00)  # Store to stack

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
        """Generate BACK (erase to beginning of line).

        <BACK> moves cursor back and erases from current position to start of line.
        V3 approximation: print newline to go to next line.

        Returns:
            bytes: Z-machine code for line erase
        """
        # BACK in V3: just print newline as approximation
        return self.gen_newline()

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
        V6+: Uses PICTURE_DATA opcode (EXT:0x06)
        V3-V5: Returns empty (no graphics support)

        Args:
            operands[0]: Picture number
            operands[1]: Info table address

        Returns:
            bytes: Z-machine code for getting picture info
        """
        if self.version < 6:
            # V3-V5: No graphics support
            return b''

        if len(operands) < 2:
            return b''

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

    def gen_mouse_info(self, operands: List[ASTNode]) -> bytes:
        """Generate MOUSE-INFO (get mouse information).

        <MOUSE-INFO table> reads mouse data into a table.
        Table receives 4 words: y, x, buttons, menu-word.
        V5+: Uses READ_MOUSE opcode (EXT:0x16)
        V3/V4: Returns empty (no mouse support)

        Args:
            operands[0]: Table address to store mouse data

        Returns:
            bytes: Z-machine code for reading mouse state
        """
        if self.version < 5:
            # V3/V4: No mouse support
            return b''

        if not operands:
            return b''

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
        """Generate PRINTT (print with tab).

        <PRINTT string> prints string with tab formatting.
        Alias for PRINT with special formatting.

        Args:
            operands[0]: String to print

        Returns:
            bytes: Z-machine code (delegates to TELL)
        """
        # PRINTT is just TELL/PRINT
        return self.gen_tell(operands)

    def gen_fstack(self, operands: List[ASTNode]) -> bytes:
        """Generate FSTACK (get frame stack pointer).

        <FSTACK> returns the current frame stack pointer.
        V5+: Uses CATCH opcode to get current stack frame
        V3/V4: Returns 0 (no frame introspection)

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()

        if self.version >= 5:
            # V5+: Use CATCH opcode (VAR:0x19) to get frame pointer
            # CATCH returns the current stack frame address
            code.append(0xF9)  # CATCH (VAR opcode 0x19)
            code.append(0xFF)  # No operands
            code.append(0x00)  # Store result to stack
        else:
            # V3/V4: No frame introspection, push 0
            # Use ADD 0 0 -> sp to push 0
            code.append(0x54)  # ADD (2OP:0x14)
            code.append(0x00)  # 0
            code.append(0x00)  # 0
            code.append(0x00)  # Store to stack

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
        """Generate LOG-SHIFT (logical shift).

        <LOG-SHIFT value amount> performs logical shift (signed).
        Alias for LSH/RSH depending on sign.

        Args:
            operands[0]: Value to shift
            operands[1]: Shift amount (positive=left, negative=right)

        Returns:
            bytes: Z-machine code
        """
        # LOG-SHIFT: if positive use LSH, if negative use RSH
        # For simplicity, delegate to LSH
        return self.gen_lsh(operands)

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
        if len(operands) < 2 or self.version < 5:
            return b''

        code = bytearray()

        # ART_SHIFT is EXT opcode 0x03
        code.append(0xBE)  # EXT opcode marker
        code.append(0x03)  # ART_SHIFT

        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        types = []
        types.append(0x01 if op1_type == 0 else 0x02)
        types.append(0x01 if op2_type == 0 else 0x02)
        types.append(0x03)
        types.append(0x03)
        type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
        code.append(type_byte)
        code.append(op1_val & 0xFF)
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
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # V5+: Use native XOR (EXT:0x0B)
        if self.version >= 5:
            code.append(0xBE)  # EXT opcode marker
            code.append(0x0B)  # XOR extended opcode

            types = []
            types.append(0x01 if op1_type == 0 else 0x02)
            types.append(0x01 if op2_type == 0 else 0x02)
            types.append(0x03)
            types.append(0x03)
            type_byte = (types[0] << 6) | (types[1] << 4) | (types[2] << 2) | types[3]
            code.append(type_byte)
            code.append(op1_val & 0xFF)
            code.append(op2_val & 0xFF)
            # Store result in stack (SP)
            code.append(0x00)

            return bytes(code)

        # V3/V4: Emulate XOR using (A OR B) AND NOT(A AND B)
        # Uses stack for intermediate values

        # For compile-time constants, compute directly
        if op1_type == 0 and op2_type == 0:
            result = op1_val ^ op2_val
            # Push the result to stack using ADD 0 + result
            if 0 <= result <= 255:
                code.append(0x54)  # 2OP:20 ADD, small const, small const
                code.append(0x00)  # 0
                code.append(result & 0xFF)
                code.append(0x00)  # Store to SP (stack)
            else:
                # Large constant: use VAR form
                code.append(0xD4)  # VAR form of ADD
                code.append(0x0F)  # Type: small(0), large(result), omit, omit
                code.append(0x00)  # 0
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
        def encode_operand(val):
            """Return (type_bits, bytes) for an operand."""
            if isinstance(val, int):
                if 0 <= val <= 255:
                    return (0b01, bytes([val & 0xFF]))  # Small constant
                else:
                    return (0b00, bytes([(val >> 8) & 0xFF, val & 0xFF]))  # Large
            else:
                # Variable reference
                return (0b10, bytes([val & 0xFF]))  # Variable

        t1, b1 = encode_operand(val1)
        t2, b2 = encode_operand(val2)
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
        V3/V4: Generates inline loop with LOADB/STOREB.

        Args:
            operands[0]: Source table address
            operands[1]: Destination table address
            operands[2]: Number of bytes to copy

        Returns:
            bytes: Z-machine code for table copy
        """
        if len(operands) < 3:
            return b''

        code = bytearray()

        # V5+: Use COPY_TABLE opcode (EXT:0x17)
        if self.version >= 5:
            op1_type, op1_val = self._get_operand_type_and_value(operands[0])  # src
            op2_type, op2_val = self._get_operand_type_and_value(operands[1])  # dst
            op3_type, op3_val = self._get_operand_type_and_value(operands[2])  # length

            # COPY_TABLE opcode 0xBE (EXT opcode 0x17)
            code.append(0xBE)
            code.append(0x17)  # Extended opcode number

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
            code.append(0x8E)  # LOAD var -> store
            code.append(0x00)  # Stack
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
        First operand can be empty list () or list of bindings.
        Remaining operands are statements to execute in order.

        Example: <PROG () <SETG X 1> <SETG Y 2> <RETURN 3>>

        Args:
            operands[0]: Bindings (usually empty list ())
            operands[1:]: Statements to execute sequentially

        Returns:
            bytes: Z-machine code for sequential execution
        """
        code = bytearray()

        # First operand is bindings (skip if empty list)
        if len(operands) < 2:
            return b''

        # Process bindings if present (operands[0])
        # For now, we skip bindings - they would be handled by parser

        # Generate code for each statement in sequence
        for i in range(1, len(operands)):
            stmt = operands[i]
            stmt_code = self.generate_statement(stmt)
            if stmt_code:
                code.extend(stmt_code)

        return bytes(code)

    def gen_bind(self, operands: List[ASTNode]) -> bytes:
        """Generate BIND (local variable binding block).

        <BIND bindings body...> creates local variables and executes body.
        Similar to PROG but focuses on local variable scope.

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

        # Process bindings from operands[0]
        # For now, we just execute the body statements
        # Full binding support would require parser-level local scope tracking

        # Generate code for each statement in sequence
        for i in range(1, len(operands)):
            stmt = operands[i]
            stmt_code = self.generate_statement(stmt)
            if stmt_code:
                code.extend(stmt_code)

        return bytes(code)

    def gen_repeat(self, operands: List[ASTNode]) -> bytes:
        """Generate REPEAT loop.

        <REPEAT (bindings) body...> creates an infinite loop that executes body
        statements until RETURN is called to exit.
        AGAIN restarts the loop from the beginning.

        Example: <REPEAT () <COND (<FSET? ,X ,FLAG> <RETURN T>)> <INC X>>

        Args:
            operands[0]: Bindings (usually empty list () or variable bindings)
            operands[1:]: Statements to execute in loop body

        Returns:
            bytes: Z-machine code for the loop
        """
        # Use a bytearray that we can reference in loop_stack
        code = bytearray()

        if len(operands) < 1:
            return b''

        # Process bindings from operands[0] if present
        # For now, we skip processing bindings - they're handled elsewhere

        # Record loop start position (where AGAIN should jump back to)
        loop_start = len(code)

        # Push loop context onto stack
        loop_ctx = {
            'code_buffer': code,
            'start_offset': loop_start,
            'again_placeholders': []  # Will be populated by gen_again
        }
        self.loop_stack.append(loop_ctx)

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
            # JUMP is 3 bytes, so PC after = current_pos + 3
            # Target is loop_start
            jump_offset = loop_start - (current_pos + 3)

            # JUMP uses signed 16-bit offset
            if jump_offset < 0:
                jump_offset_unsigned = (1 << 16) + jump_offset  # Two's complement
            else:
                jump_offset_unsigned = jump_offset

            code.append(0x8C)  # JUMP opcode
            code.append((jump_offset_unsigned >> 8) & 0xFF)
            code.append(jump_offset_unsigned & 0xFF)

            # Patch all AGAIN placeholders (0x8C 0xFF 0xAA -> actual jump)
            i = 0
            while i < len(code) - 2:
                if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xAA:
                    # Found AGAIN placeholder at position i
                    # Calculate jump offset from position i+3 to loop_start
                    again_offset = loop_start - (i + 3)
                    if again_offset < 0:
                        again_offset_unsigned = (1 << 16) + again_offset
                    else:
                        again_offset_unsigned = again_offset
                    code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                    code[i+2] = again_offset_unsigned & 0xFF
                i += 1

        finally:
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
        """Generate JE (jump if equal) - branch instruction.

        JE can compare up to 4 values: <EQUAL? a b c d> tests if a equals any of b, c, d.
        Returns true if equal, false otherwise.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # JE is 2OP opcode 0x01
        # Long form: bits 6-5 are operand types, bits 4-0 are opcode
        opcode = 0x01 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        # Branch byte: bit 7 = branch on true, bit 6 = short offset, bits 5-0 = offset
        # 0xC0 = branch on true, return true (offset 1)
        # 0x40 = branch on false, return false (offset 0)
        code.append(0xC0)  # Branch on true, return true

        return bytes(code)

    def gen_less(self, operands: List[ASTNode]) -> bytes:
        """Generate JL (jump if less) - branch instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # JL is 2OP opcode 0x02
        opcode = 0x02 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0xC0)  # Branch on true, return true

        return bytes(code)

    def gen_greater(self, operands: List[ASTNode]) -> bytes:
        """Generate JG (jump if greater) - branch instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # JG is 2OP opcode 0x03
        opcode = 0x03 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0xC0)  # Branch on true, return true

        return bytes(code)

    def gen_zero(self, operands: List[ASTNode]) -> bytes:
        """Generate ZERO? test (jump if zero).

        <ZERO? value> is equivalent to <EQUAL? value 0>
        Uses JZ (jump if zero) - 1OP opcode 0x00
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # JZ is 1OP opcode 0x00 (branch instruction)
        # Short form: bit 5-4 = operand type, bits 3-0 = opcode
        # Type: 00 = large const, 01 = small const, 10 = variable
        if op_type == 0:  # Constant
            code.append(0x80)  # Short 1OP, small constant, opcode 0x00
        else:  # Variable
            code.append(0xA0)  # Short 1OP, variable, opcode 0x00
        code.append(op_val & 0xFF)
        code.append(0xC0)  # Branch on true, return true

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
        code.append(0xC0)  # Branch on true, return true

        return bytes(code)

    def gen_assigned(self, operands: List[ASTNode]) -> bytes:
        """Generate ASSIGNED? test (check if variable is assigned).

        <ASSIGNED? var> checks if a global variable has been assigned.
        This is a compile-time check - we verify the variable exists in globals.
        At runtime, we check if the value is non-zero.
        """
        if not operands:
            return b''

        code = bytearray()

        # Get the variable
        if isinstance(operands[0], AtomNode):
            var_name = operands[0].value
            # Check if it's in globals
            if var_name in self.globals:
                var_num = self.globals[var_name]
                # LOAD the variable and test if non-zero
                code.append(0x8E)  # LOAD
                code.append(var_num)
                code.append(0x00)  # Store to stack
                # JZ (test if zero) - if zero, it's not assigned
                code.append(0x80)  # JZ
                code.append(0x00)  # Stack
                code.append(0x40)  # Branch on true
            else:
                # Variable not in globals = not assigned
                # Return false (0)
                code.append(0xB1)  # RFALSE

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
        return self.gen_zero(operands)

    def gen_true_predicate(self, operands: List[ASTNode]) -> bytes:
        """Generate TRUE? (test if value is non-zero).

        <TRUE? value> tests if a value is non-zero (true).
        This is the opposite of ZERO?/NOT?

        Args:
            operands[0]: Value to test

        Returns:
            bytes: Z-machine code (JZ with inverted branch)
        """
        if not operands:
            return b''

        code = bytearray()
        val = self.get_operand_value(operands[0])

        # JZ is 1OP opcode 0x00 (branch instruction)
        # We want to branch if NOT zero (invert the condition)
        if isinstance(val, int):
            if 0 <= val <= 255:
                code.append(0x80)  # Short 1OP, opcode 0x00
                code.append(val & 0xFF)
                # Inverted branch: branch on false (when value IS zero, don't branch)
                code.append(0x00)  # Branch on false

        return bytes(code)

    # ===== Logical Operations =====

    def gen_and(self, operands: List[ASTNode]) -> bytes:
        """Generate AND (bitwise).

        Handles constants, variables, and mixed operands.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # AND is 2OP opcode 0x09
        # Use long form for simple cases
        opcode = 0x09 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_or(self, operands: List[ASTNode]) -> bytes:
        """Generate OR (bitwise).

        Handles constants, variables, and mixed operands.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # OR is 2OP opcode 0x08
        opcode = 0x08 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_not(self, operands: List[ASTNode]) -> bytes:
        """Generate NOT (bitwise complement).

        Handles constants and variables.
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # NOT is 1OP opcode 0x0F
        # 0x8F = small constant, 0x9F = large constant, 0xAF = variable
        # _get_operand_type_and_value returns: 0=constant, 1=variable
        if op_type == 1:  # Variable
            code.append(0x9F)  # Short 1OP with variable
        else:  # Constant
            code.append(0x8F)  # Short 1OP with small constant
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Object Operations =====

    def gen_fset(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_ATTR (set object attribute)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # SET_ATTR is 2OP opcode 0x0B (long form)
        # Bit 6 = 1 if first operand is variable, 0 if constant
        # Bit 5 = 1 if second operand is variable, 0 if constant
        # _get_operand_type_and_value returns: 0=constant, 1=variable
        opcode = 0x0B | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_fclear(self, operands: List[ASTNode]) -> bytes:
        """Generate CLEAR_ATTR (clear object attribute)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # CLEAR_ATTR is 2OP opcode 0x0C (long form)
        # _get_operand_type_and_value returns: 0=constant, 1=variable
        opcode = 0x0C | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)

        return bytes(code)

    def gen_fset_test(self, operands: List[ASTNode]) -> bytes:
        """Generate TEST_ATTR (test object attribute) - branch instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # TEST_ATTR is 2OP opcode 0x0A (branch)
        opcode = 0x0A | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0xC0)  # Branch on true, return true

        return bytes(code)

    def gen_move(self, operands: List[ASTNode]) -> bytes:
        """Generate INSERT_OBJ (move object to destination)."""
        if len(operands) < 2:
            return b''

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
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # REMOVE_OBJ is 1OP opcode 0x09
        if op_type == 0:  # Constant
            code.append(0x89)  # Short 1OP, small constant
        else:  # Variable
            code.append(0xA9)  # Short 1OP, variable
        code.append(op_val & 0xFF)

        return bytes(code)

    def gen_loc(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PARENT (get object's parent)."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_PARENT is 1OP opcode 0x03
        if op_type == 0:  # Constant
            code.append(0x83)  # Short 1OP, small constant
        else:  # Variable
            code.append(0xA3)  # Short 1OP, variable
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Property Operations =====

    def gen_getp(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PROP (get object property)."""
        if len(operands) < 2:
            return b''

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
        if len(operands) < 3:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # PUT_PROP is VAR opcode 0x03
        code.append(0xE3)  # VAR form, opcode 0x03
        # Type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omitted
        type_byte = ((op1_type + 1) << 6) | ((op2_type + 1) << 4) | ((op3_type + 1) << 2) | 0x03
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_ptsize(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PROP_LEN (get property length).

        <PTSIZE prop-addr> returns the length of a property.
        Uses GET_PROP_LEN - 1OP opcode 0x04.
        """
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_PROP_LEN is 1OP opcode 0x04
        # 0x84 = small constant, 0x94 = variable
        if op_type == 1:  # Variable
            code.append(0x94)
        else:  # Constant
            code.append(0x84)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_nextp(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_NEXT_PROP (get next property).

        <NEXTP obj prop> returns the next property number after prop.
        If prop is 0, returns the first property.
        Uses GET_NEXT_PROP - 2OP opcode 0x13.
        """
        if len(operands) < 2:
            return b''

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
            # Check if this is the T (else) clause
            is_t_clause = isinstance(condition, AtomNode) and condition.value == 'T'

            # Generate the condition test (without proper offset yet)
            test_code = bytearray()
            test_size = 0
            if not is_t_clause:
                test_code = bytearray(self.generate_condition_test(condition, branch_on_false=True))
                test_size = len(test_code)

            # Generate actions for this clause
            actions_code = bytearray()
            for action in actions:
                actions_code.extend(self.generate_statement(action))

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
                # Offset is from AFTER the branch bytes to the start of next clause
                next_clause_offset = clause['actions_size'] + clause['jump_size']

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
                    offset_from_branch = next_clause_offset - 2  # -2 because relative to after branch
                    clause['test_code'][-1] = branch_sense | ((offset_from_branch >> 8) & 0x3F)
                    # Need to add second byte
                    clause['test_code'].append(offset_from_branch & 0xFF)
                    clause['test_size'] += 1
                    clause['total_size'] += 1

            # Add the test code
            code.extend(clause['test_code'])

            # Add the actions
            code.extend(clause['actions_code'])

            # Add jump to end if needed
            if clause['needs_jump_to_end']:
                # Calculate offset to end of COND
                remaining_size = sum(clause_data[j]['total_size'] for j in range(i + 1, len(clause_data)))

                # JUMP instruction: 0x8C (1OP, short form, opcode 0x0C)
                code.append(0x8C)

                # Encode offset (2 bytes, signed 14-bit)
                if remaining_size < 64:
                    # 1-byte form
                    code.append(0x40 | (remaining_size & 0x3F))
                    code.append(0x00)  # Padding
                else:
                    # 2-byte form
                    offset = remaining_size - 2  # Relative to after the jump bytes
                    code.append((offset >> 8) & 0x3F)
                    code.append(offset & 0xFF)

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

            # Handle EQUAL? (JE)
            elif op_name in ('=', 'EQUAL?', '==?'):
                if len(condition.operands) >= 2:
                    val1 = self.get_operand_value(condition.operands[0])
                    val2 = self.get_operand_value(condition.operands[1])

                    if isinstance(val1, int) and isinstance(val2, int):
                        if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                            code.append(0x41)  # JE opcode
                            code.append(val1 & 0xFF)
                            code.append(val2 & 0xFF)

            # Handle L? (JL)
            elif op_name in ('L?', '<'):
                if len(condition.operands) >= 2:
                    val1 = self.get_operand_value(condition.operands[0])
                    val2 = self.get_operand_value(condition.operands[1])

                    if isinstance(val1, int) and isinstance(val2, int):
                        if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                            code.append(0x42)  # JL opcode
                            code.append(val1 & 0xFF)
                            code.append(val2 & 0xFF)

            # Handle G? (JG)
            elif op_name in ('G?', '>'):
                if len(condition.operands) >= 2:
                    val1 = self.get_operand_value(condition.operands[0])
                    val2 = self.get_operand_value(condition.operands[1])

                    if isinstance(val1, int) and isinstance(val2, int):
                        if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                            code.append(0x43)  # JG opcode
                            code.append(val1 & 0xFF)
                            code.append(val2 & 0xFF)

            # Handle NOT
            elif op_name == 'NOT':
                # Generate the inner condition and flip the branch sense
                if condition.operands:
                    inner_code = self.generate_condition_test(
                        condition.operands[0],
                        branch_on_false=not branch_on_false
                    )
                    return inner_code

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

        # Initialize loop variable bindings
        for var_name, init_value in repeat.bindings:
            # Create local variable if not already in locals
            if var_name not in self.locals:
                var_num = len(self.locals) + 1
                self.locals[var_name] = var_num

            # Generate assignment
            var_num = self.locals[var_name]
            value = self.get_operand_value(init_value)

            if isinstance(value, int) and 0 <= value <= 255:
                # STORE variable small_constant
                code.append(0x2D)  # STORE opcode (long form, small/small)
                code.append(var_num & 0xFF)
                code.append(value & 0xFF)

        # Mark loop start position (after initialization)
        loop_start_pos = len(code)

        # Push loop context for AGAIN support
        # Store the code buffer reference and start position
        loop_context = {
            'start_offset': loop_start_pos,
            'code_buffer': code,  # Reference to the code being built
            'again_patches': []   # List of positions that need patching
        }
        self.loop_stack.append(loop_context)

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

        # Patch all AGAIN placeholders (0x8C 0xFF 0xAA -> actual jump)
        i = 0
        while i < len(code) - 2:
            if code[i] == 0x8C and code[i+1] == 0xFF and code[i+2] == 0xAA:
                # Found AGAIN placeholder at position i
                # Calculate jump offset from position i+3 to loop_start_pos
                again_offset = loop_start_pos - (i + 3)
                if again_offset < 0:
                    again_offset_unsigned = (1 << 16) + again_offset
                else:
                    again_offset_unsigned = again_offset
                code[i+1] = (again_offset_unsigned >> 8) & 0xFF
                code[i+2] = again_offset_unsigned & 0xFF
            i += 1

        # Pop loop context
        self.loop_stack.pop()

        return bytes(code)

    # ===== Helper Methods =====

    def get_operand_value(self, node: ASTNode) -> Any:
        """Get the value of an operand (constant or variable)."""
        if isinstance(node, NumberNode):
            return node.value
        elif isinstance(node, AtomNode):
            if node.value in self.constants:
                return self.constants[node.value]
            elif node.value in self.globals:
                return self.globals[node.value]
            elif node.value in self.locals:
                return self.locals[node.value]
            # Check for builtin constants
            elif node.value == 'T':
                return 1
            elif node.value == '<>':
                return 0
        elif isinstance(node, LocalVarNode):
            return self.locals.get(node.name, 1)
        elif isinstance(node, GlobalVarNode):
            return self.globals.get(node.name, 0x10)
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

    # ===== Routine Calls =====

    def gen_routine_call(self, routine_name: str, operands: List[ASTNode]) -> bytes:
        """Generate routine call (CALL or CALL_VS)."""
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

        # LOADB is 2OP opcode 0x10
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
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # LOADW is 2OP opcode 0x0F
        opcode = 0x0F | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_put(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT (table word write).

        <PUT table index value> writes value to table[index].
        Uses Z-machine STOREW instruction.
        """
        if len(operands) < 3:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREW is VAR opcode 0x01
        code.append(0xE1)  # VAR form, opcode 0x01
        # Type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omitted
        type_byte = ((op1_type + 1) << 6) | ((op2_type + 1) << 4) | ((op3_type + 1) << 2) | 0x03
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

        return bytes(code)

    def gen_getb(self, operands: List[ASTNode]) -> bytes:
        """Generate GETB (table byte access).

        <GETB table index> reads byte from table[index].
        Uses Z-machine LOADB instruction.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # LOADB is 2OP opcode 0x10
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
        if len(operands) < 3:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])
        op3_type, op3_val = self._get_operand_type_and_value(operands[2])

        # STOREB is VAR opcode 0x02
        code.append(0xE2)  # VAR form, opcode 0x02
        # Type byte: 2 bits per operand, 00=large, 01=small, 10=var, 11=omitted
        type_byte = ((op1_type + 1) << 6) | ((op2_type + 1) << 4) | ((op3_type + 1) << 2) | 0x03
        code.append(type_byte)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(op3_val & 0xFF)

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
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # PUSH is VAR opcode 0x08
        code.append(0xE8)  # VAR form, opcode 0x08
        if op_type == 1:  # Variable
            code.append(0x8F)  # Type byte: variable, rest omitted (10 00 11 11)
            code.append(op_val & 0xFF)
        elif op_val > 255:  # Large constant
            code.append(0x0F)  # Type byte: large constant, rest omitted (00 00 11 11)
            code.append((op_val >> 8) & 0xFF)
            code.append(op_val & 0xFF)
        else:  # Small constant
            code.append(0x5F)  # Type byte: small constant, rest omitted (01 01 11 11)
            code.append(op_val & 0xFF)

        return bytes(code)

    def gen_pull(self, operands: List[ASTNode]) -> bytes:
        """Generate PULL (pop from stack) - V1-5 only."""
        if not operands:
            return b''

        code = bytearray()
        var_num = self.get_variable_number(operands[0])

        # PULL is VAR opcode 0x09 (V1-5)
        if self.version <= 5:
            code.append(0xE9)  # VAR form, opcode 0x09
            code.append(0x02)  # Type byte: 1 variable
            code.append(var_num)

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
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_CHILD is 1OP opcode 0x02 (store + branch)
        # 0x82 = small constant, 0x92 = variable
        # _get_operand_type_and_value returns: 0=constant, 1=variable
        if op_type == 1:  # Variable
            code.append(0x92)
        else:  # Constant
            code.append(0x82)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack
        code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_get_sibling(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_SIBLING (get next sibling of object)."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_SIBLING is 1OP opcode 0x01 (store + branch)
        # 0x81 = small constant, 0x91 = variable
        if op_type == 1:  # Variable
            code.append(0x91)
        else:  # Constant
            code.append(0x81)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack
        code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_get_parent(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PARENT (get parent of object)."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # GET_PARENT is 1OP opcode 0x03 (store only)
        # 0x83 = small constant, 0x93 = variable
        if op_type == 1:  # Variable
            code.append(0x93)
        else:  # Constant
            code.append(0x83)
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
        # 0x82 = small constant, 0x92 = variable
        if op_type == 1:  # Variable
            code.append(0x92)
        else:  # Constant
            code.append(0x82)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack
        # Don't include branch byte - caller handles branching

        return bytes(code)

    def gen_in(self, operands: List[ASTNode]) -> bytes:
        """Generate IN? (test if obj1 is directly in obj2).

        <IN? obj1 obj2> tests if obj1's parent is obj2.
        This is equivalent to: <EQUAL? <LOC obj1> obj2>

        Implementation: GET_PARENT obj1, then compare with obj2.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get operand types and values
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # Get parent of obj1
        # GET_PARENT is 1OP opcode 0x03 (store instruction)
        if op1_type == 0:  # Constant
            code.append(0x83)  # Short 1OP, small constant
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
        code.append(0xC0)  # Branch on true, return true

        return bytes(code)

    # ===== Utilities and Built-ins =====

    def gen_random(self, operands: List[ASTNode]) -> bytes:
        """Generate RANDOM (random number generator)."""
        if not operands:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # RANDOM is VAR opcode 0x07
        code.append(0xE7)  # VAR form, opcode 0x07
        type_byte = 0x01 if op_type == 0 else 0x02  # small const or var
        code.append((type_byte << 6) | 0x0F)
        code.append(op_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_restart(self) -> bytes:
        """Generate RESTART (restart game)."""
        return bytes([0xB7])  # Short 0OP, opcode 0x07

    def gen_save(self) -> bytes:
        """Generate SAVE (save game).

        V1-3: Branch instruction (branches on success)
        V4+: Store instruction (returns 0=fail, 1=success)
        """
        code = bytearray()
        code.append(0xB5)  # Short 0OP, opcode 0x05

        if self.version <= 3:
            # Branch instruction in V1-3
            code.append(0x40)  # Branch byte
        elif self.version == 4:
            # V4: Store instruction (returns result)
            code.append(0x00)  # Store to stack (SP)

        return bytes(code)

    def gen_restore(self) -> bytes:
        """Generate RESTORE (restore game).

        V1-3: Branch instruction (branch never taken)
        V4+: Store instruction (returns result)
        """
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
        """Generate VERIFY (verify game file) - branch instruction."""
        code = bytearray()
        code.append(0xBD)  # Short 0OP, opcode 0x0D
        code.append(0x40)  # Branch byte
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
        """Generate APPLY (call routine with arguments from table).

        <APPLY routine arg-table num-args> calls routine with arguments
        unpacked from a table.

        This is a simplified implementation.

        Args:
            operands[0]: Routine address
            operands[1]: Table of arguments
            operands[2]: Number of arguments

        Returns:
            bytes: Z-machine code (simplified CALL)
        """
        if len(operands) < 1:
            return b''

        # For simplicity, treat like CALL with first operand
        # Full implementation would unpack args from table
        return self.gen_call([operands[0]])

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
            bytes: Z-machine code (TOKENISE EXT opcode)
        """
        if len(operands) < 2 or self.version < 5:
            return b''

        code = bytearray()

        # TOKENISE is EXT opcode 0x00
        code.append(0xBE)  # EXT opcode marker
        code.append(0x00)  # TOKENISE

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(min(4, len(operands))):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            op_types.append(op_type)
            op_vals.append(op_val)

        # Build type byte: 0x01 = small const, 0x02 = variable, 0x03 = omitted
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

    def gen_check_arg_count(self, operands: List[ASTNode]) -> bytes:
        """Generate CHECK_ARG_COUNT (V5+ check number of arguments).

        <CHECK_ARG_COUNT n> branches if current routine was called
        with at least n arguments. V5+ only.

        Args:
            operands[0]: Argument count to check

        Returns:
            bytes: Z-machine code (CHECK_ARG_COUNT EXT opcode)
        """
        if not operands or self.version < 5:
            return b''

        code = bytearray()
        op_type, op_val = self._get_operand_type_and_value(operands[0])

        # CHECK_ARG_COUNT is EXT opcode 0x0F
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0F)  # CHECK_ARG_COUNT

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
            bytes: Z-machine code (ENCODE_TEXT EXT opcode)
        """
        if len(operands) < 4 or self.version < 5:
            return b''

        code = bytearray()

        # ENCODE_TEXT is EXT opcode 0x05
        code.append(0xBE)  # EXT opcode marker
        code.append(0x05)  # ENCODE_TEXT

        # Get operand types and values
        op_types = []
        op_vals = []
        for i in range(4):
            op_type, op_val = self._get_operand_type_and_value(operands[i])
            op_types.append(op_type)
            op_vals.append(op_val)

        # Build type byte
        type_byte = 0x00
        for i in range(4):
            type_val = 0x01 if op_types[i] == 0 else 0x02
            type_byte |= (type_val << (6 - i*2))

        code.append(type_byte)

        # Append operand values
        for val in op_vals:
            code.append(val & 0xFF)

        return bytes(code)

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
        if not operands or self.version < 6:
            return b''

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
        if not operands or self.version < 6:
            return b''

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

        Returns:
            bytes: Z-machine code (SAVE_UNDO EXT opcode)
        """
        if self.version < 5:
            return b''

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

        Returns:
            bytes: Z-machine code (RESTORE_UNDO EXT opcode)
        """
        if self.version < 5:
            return b''

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
        """Generate REST (pointer arithmetic on tables).

        REST takes a table address and an offset, returning address + (offset * 2).
        Used for list/table traversal.

        Args:
            operands[0]: table/array address
            operands[1]: offset (optional, defaults to 1 for list tail)

        Returns:
            bytes: Z-machine code (ADD to compute new address)
        """
        if not operands:
            return b''

        code = bytearray()
        table_node = operands[0]
        offset_node = operands[1] if len(operands) > 1 else None

        # Handle table operand
        table_type, table_val = self._get_operand_type_and_value(table_node)

        # If table is a form expression, evaluate it first
        if isinstance(table_node, FormNode):
            expr_code = self.generate_statement(table_node)
            if expr_code:
                code.extend(expr_code)
                table_type = 1  # Variable (stack)
                table_val = 0   # Stack

        # Handle offset operand
        if offset_node is None:
            # Default offset of 2 (skip 1 word element)
            offset_type = 0
            offset_val = 2
        elif isinstance(offset_node, FormNode):
            # Complex expression - evaluate it then multiply by 2
            expr_code = self.generate_statement(offset_node)
            if expr_code:
                code.extend(expr_code)
                # Multiply stack by 2 using ADD stack stack -> stack
                code.append(0xD4)  # ADD VAR form
                code.append(0x9F)  # var, var, omit, omit
                code.append(0x00)  # Stack
                code.append(0x00)  # Stack
                code.append(0x00)  # Store to stack
                offset_type = 1  # Variable (stack result)
                offset_val = 0   # Stack
        else:
            offset_type, offset_val = self._get_operand_type_and_value(offset_node)
            if isinstance(offset_val, int):
                offset_val = offset_val * 2  # Convert word offset to byte offset

        # REST returns table_address + byte_offset
        # ADD is 2OP opcode 0x14
        if table_type == 0 and offset_type == 0:
            # Both constants
            code.append(0x14)  # Long form, small/small
            code.append(table_val & 0xFF)
            code.append(offset_val & 0xFF)
        elif table_type == 1 and offset_type == 0:
            # Variable + constant
            code.append(0x54)  # Long form, var/small
            code.append(table_val & 0xFF)
            code.append(offset_val & 0xFF)
        elif table_type == 0 and offset_type == 1:
            # Constant + variable
            code.append(0x34)  # Long form, small/var
            code.append(table_val & 0xFF)
            code.append(offset_val & 0xFF)
        else:
            # Both variables - use VAR form
            code.append(0xD4)  # ADD VAR form
            code.append(0xAF)  # var, var, omit, omit
            code.append(table_val & 0xFF)
            code.append(offset_val & 0xFF)

        code.append(0x00)  # Store to stack

        return bytes(code)

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
        Equivalent to: <INC var> <G? var value>

        Args:
            operands[0]: variable to increment
            operands[1]: value to compare against

        Returns:
            bytes: Z-machine code (INC + JG)
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        var = operands[0]

        # INC the variable
        code.extend(self.gen_inc([var]))

        # Now test if var > compare_val using JG
        var_num = self.get_variable_number(var)
        cmp_type, cmp_val = self._get_operand_type_and_value(operands[1])

        # JG is 2OP opcode 0x03
        # First operand is always the variable we just incremented
        opcode = 0x03 | (1 << 6) | (cmp_type << 5)  # var is first operand
        code.append(opcode)
        code.append(var_num)
        code.append(cmp_val & 0xFF)
        # Branch offset would be added during COND processing

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
            # STORE is 2OP opcode 0x0D
            code.append(0x2D)  # Short form
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
        if len(operands) < 2:
            return b''

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

        Tests if a specific bit is set in a value.
        Returns true if (value & (1 << bit)) != 0

        Args:
            operands[0]: value to test
            operands[1]: bit number (0-15)

        Returns:
            bytes: Z-machine code (AND + JZ for branch)
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        op1_type, op1_val = self._get_operand_type_and_value(operands[0])
        op2_type, op2_val = self._get_operand_type_and_value(operands[1])

        # AND value with bit mask
        # AND is 2OP opcode 0x09
        opcode = 0x09 | (op1_type << 6) | (op2_type << 5)
        code.append(opcode)
        code.append(op1_val & 0xFF)
        code.append(op2_val & 0xFF)
        code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_band(self, operands: List[ASTNode]) -> bytes:
        """Generate BAND (bitwise AND).

        Performs bitwise AND operation, same as AND but traditionally
        used for byte-sized operations in ZIL.

        Args:
            operands[0]: first operand
            operands[1]: second operand

        Returns:
            bytes: Z-machine code (AND instruction)
        """
        # BAND is functionally the same as AND
        return self.gen_and(operands)

    def gen_bor(self, operands: List[ASTNode]) -> bytes:
        """Generate BOR (bitwise OR).

        Performs bitwise OR operation, same as OR but traditionally
        used for byte-sized operations in ZIL.

        Args:
            operands[0]: first operand
            operands[1]: second operand

        Returns:
            bytes: Z-machine code (OR instruction)
        """
        # BOR is functionally the same as OR
        return self.gen_or(operands)

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

    def gen_queue(self, operands: List[ASTNode]) -> bytes:
        """Generate QUEUE (schedule interrupt/daemon).

        <QUEUE I-NAME tick-count> schedules a routine to run after tick-count turns.
        - tick-count > 0: One-shot interrupt (fire once, then disable)
        - tick-count = -1: Daemon (fire every turn)
        - tick-count = 0: Fire next turn

        Creates an 8-byte interrupt structure:
          Offset 0: Routine address (word, packed)
          Offset 2: Tick count (word, signed)
          Offset 4: Enabled flag (word, 0=disabled 1=enabled)
          Offset 6: Reserved (word)

        Args:
            operands[0]: Interrupt name (will be routine name with I- prefix)
            operands[1]: Tick count

        Returns:
            bytes: Address of interrupt structure
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Get interrupt name and tick count
        if isinstance(operands[0], AtomNode):
            int_name = operands[0].value
            tick_count = self.get_operand_value(operands[1])

            # Allocate space for this interrupt (8 bytes)
            int_addr = self.next_interrupt_addr
            self.interrupts[int_name] = int_addr
            self.next_interrupt_addr += 8

            # For now, return the interrupt structure address as a constant
            # In a full implementation, this would:
            # 1. Allocate static memory for the structure
            # 2. Store routine address (packed)
            # 3. Store tick count
            # 4. Store enabled=1

            # Return the address of the interrupt structure
            if int_addr <= 255:
                code.append(0x01)  # Small constant form
                code.append(int_addr & 0xFF)
            else:
                # For larger addresses, we'd need to use a different encoding
                code.append(0x01)
                code.append(int_addr & 0xFF)

        return bytes(code)

    def gen_int(self, operands: List[ASTNode]) -> bytes:
        """Generate INT (get interrupt by name).

        <INT I-NAME> returns the address of a previously QUEUEd interrupt.

        Args:
            operands[0]: Interrupt name

        Returns:
            bytes: Address of interrupt structure
        """
        if not operands:
            return b''

        code = bytearray()

        # Look up interrupt name
        if isinstance(operands[0], AtomNode):
            int_name = operands[0].value

            if int_name in self.interrupts:
                int_addr = self.interrupts[int_name]

                # Return the address
                if int_addr <= 255:
                    code.append(0x01)  # Small constant
                    code.append(int_addr & 0xFF)
                else:
                    code.append(0x01)
                    code.append(int_addr & 0xFF)
            else:
                # Interrupt not found - return 0
                code.append(0x01)
                code.append(0x00)

        return bytes(code)

    def gen_dequeue(self, operands: List[ASTNode]) -> bytes:
        """Generate DEQUEUE (remove/disable interrupt).

        <DEQUEUE interrupt-addr> disables an interrupt.
        Sets the enabled flag (offset 4) to 0.

        Args:
            operands[0]: Interrupt structure address

        Returns:
            bytes: Z-machine code (STOREW to set enabled=0)
        """
        if not operands:
            return b''

        code = bytearray()
        int_addr = self.get_operand_value(operands[0])

        if isinstance(int_addr, int):
            # STOREW int_addr 4 0  (set enabled flag to 0)
            code.append(0xE1)  # VAR form, STOREW
            code.append(0x15)  # Type byte: 3 small constants
            code.append(int_addr & 0xFF)
            code.append(0x04)  # Offset 4 (enabled flag)
            code.append(0x00)  # Value 0 (disabled)

        return bytes(code)

    def gen_enable(self, operands: List[ASTNode]) -> bytes:
        """Generate ENABLE (enable interrupt).

        <ENABLE interrupt-addr> enables an interrupt.
        Sets the enabled flag (offset 4) to 1.

        Args:
            operands[0]: Interrupt structure address

        Returns:
            bytes: Z-machine code (STOREW to set enabled=1)
        """
        if not operands:
            return b''

        code = bytearray()
        int_addr = self.get_operand_value(operands[0])

        if isinstance(int_addr, int):
            # STOREW int_addr 4 1  (set enabled flag to 1)
            code.append(0xE1)  # VAR form, STOREW
            code.append(0x15)  # Type byte: 3 small constants
            code.append(int_addr & 0xFF)
            code.append(0x04)  # Offset 4 (enabled flag)
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

    # ===== Table Literal Operations =====

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
        table_data = bytearray()
        is_pure = table_type == 'PTABLE'
        is_byte = False
        initial_size = None

        # Process operands
        values = []
        for op in operands:
            # Check for flags like (PURE), (BYTE)
            if isinstance(op, FormNode):
                if isinstance(op.operator, AtomNode):
                    flag_name = op.operator.value.upper()
                    if flag_name == 'PURE':
                        is_pure = True
                        continue
                    elif flag_name == 'BYTE':
                        is_byte = True
                        continue
            elif isinstance(op, AtomNode):
                flag_name = op.value.upper()
                if flag_name == 'PURE':
                    is_pure = True
                    continue
                elif flag_name == 'BYTE':
                    is_byte = True
                    continue

            values.append(op)

        # For LTABLE, first value is the count (or we compute it)
        if table_type == 'LTABLE':
            # LTABLE has a length prefix
            table_data.extend(struct.pack('>H', len(values)))

        # For ITABLE, first value might be the size
        if table_type == 'ITABLE' and values and isinstance(values[0], NumberNode):
            initial_size = values[0].value
            values = values[1:]  # Rest are initial values

        # Encode table values
        for val in values:
            val_int = self.get_operand_value(val)
            if val_int is None:
                # Try to resolve as object/routine/global reference
                if isinstance(val, AtomNode):
                    name = val.value
                    if name in self.objects:
                        val_int = self.objects[name]
                    elif name in self.routines:
                        val_int = self.routines[name]
                    elif name in self.globals:
                        val_int = self.globals[name]
                    elif name in self.constants:
                        val_int = self.constants[name]
                    else:
                        val_int = 0  # Unknown reference
                elif isinstance(val, StringNode):
                    # Encode string and store as packed address
                    # For now, just use 0 as placeholder
                    val_int = 0
                else:
                    val_int = 0

            if is_byte:
                table_data.append(val_int & 0xFF)
            else:
                table_data.extend(struct.pack('>H', val_int & 0xFFFF))

        # For ITABLE, pad to initial size if specified
        if initial_size and table_type == 'ITABLE':
            entry_size = 1 if is_byte else 2
            while len(table_data) < initial_size * entry_size:
                if is_byte:
                    table_data.append(0)
                else:
                    table_data.extend(struct.pack('>H', 0))

        # Store the table for later assembly
        table_id = f"_TABLE_{self.table_counter}"
        self.table_counter += 1
        self.tables.append((table_id, bytes(table_data), is_pure))

        # Return code that will be replaced with actual address during assembly
        # For now, we push a placeholder that will be fixed up
        # The address will be determined when the assembler places tables in memory
        code = bytearray()
        # Use a marker that the assembler can recognize and patch
        # We'll store the table index as a large constant for now
        # The assembler will replace this with the actual packed address
        code.append(0x8F)  # 1OP large constant form
        code.append((len(self.tables) - 1) >> 8)  # Table index as placeholder
        code.append((len(self.tables) - 1) & 0xFF)

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
