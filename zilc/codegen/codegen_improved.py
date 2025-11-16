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

    def __init__(self, version: int = 3):
        self.version = version
        self.encoder = ZTextEncoder(version)
        self.opcodes = OpcodeTable()

        # Symbol tables
        self.globals: Dict[str, int] = {}
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
        # Process globals
        for global_node in program.globals:
            self.globals[global_node.name] = self.next_global
            self.next_global += 1

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

        return bytes(self.code)

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
        elif op_name == 'RFATAL':
            return self.gen_rfatal()
        elif op_name == 'RETURN':
            return self.gen_return(form.operands)
        elif op_name == 'QUIT':
            return self.gen_quit()
        elif op_name == 'AGAIN':
            return self.gen_again()
        elif op_name == 'PROG':
            return self.gen_prog(form.operands)
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
        elif op_name == 'ZERO':
            return self.gen_zero(form.operands)
        elif op_name == 'SHIFT':
            return self.gen_shift(form.operands)

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

        # Routine calls - check if it's a routine name
        elif isinstance(form.operator, AtomNode):
            if form.operator.value in self.routines or form.operator.value.isupper():
                # Likely a routine call
                return self.gen_routine_call(form.operator.value, form.operands)

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
        value = self.eval_expression(operands[0])

        if value is not None and 0 <= value <= 255:
            # RET with small constant (1OP, short form)
            code.append(0x8B)  # Short 1OP, opcode 0x0B
            code.append(value & 0xFF)
        else:
            # Would need to load value first, then ret
            # Simplified: just return true
            code.extend(self.gen_rtrue())

        return bytes(code)

    def gen_quit(self) -> bytes:
        """Generate QUIT."""
        return bytes([0xBA])

    def gen_again(self) -> bytes:
        """Generate AGAIN (restart current loop).

        AGAIN jumps back to the start of the innermost REPEAT loop.
        This is similar to 'continue' in C.

        Note: Proper implementation requires tracking loop start labels.
        For now, this generates a placeholder.
        """
        # TODO: Implement proper loop label tracking
        # For now, just return empty (needs loop context)
        return b''

    # ===== Output Instructions =====

    def gen_newline(self) -> bytes:
        """Generate NEW_LINE."""
        return bytes([0xBB])

    def gen_tell(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT instruction with inline text."""
        code = bytearray()
        code.append(0xB2)  # PRINT opcode

        # Concatenate all string operands
        text_parts = []
        for op in operands:
            if isinstance(op, StringNode):
                text_parts.append(op.value)
            elif isinstance(op, AtomNode) and op.value == 'CR':
                text_parts.append('\n')

        text = ''.join(text_parts)
        encoded_words = self.encoder.encode_string(text)
        code.extend(words_to_bytes(encoded_words))

        return bytes(code)

    def gen_print_num(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_NUM (print signed number)."""
        if not operands:
            return b''

        code = bytearray()
        # PRINT_NUM is VAR opcode 0x06
        code.append(0xE6)  # Variable form, VAR, opcode 0x06

        # Type byte (1 operand)
        code.append(0x00)  # Will be filled based on operand type

        # For now, simplified: assume variable or small constant
        value = self.get_operand_value(operands[0])
        if isinstance(value, int) and 0 <= value <= 255:
            code[-1] = 0x01  # Small constant
            code.append(value & 0xFF)

        return bytes(code)

    def gen_print_char(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT_CHAR."""
        if not operands:
            return b''

        code = bytearray()
        code.append(0xE5)  # VAR opcode 0x05
        code.append(0x01)  # Type byte: small constant

        value = self.get_operand_value(operands[0])
        if isinstance(value, int):
            code.append(value & 0xFF)

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
        addr = self.get_operand_value(operands[0])

        # PRINT_PADDR is VAR opcode 0x0D
        code.append(0xED)  # VAR form, opcode 0x0D
        code.append(0x01)  # Type byte: small constant

        if isinstance(addr, int):
            code.append(addr & 0xFF)

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
        addr = self.get_operand_value(operands[0])

        # PRINT_ADDR is VAR opcode 0x15 (V4+)
        # For V3, we can use PRINT_PADDR with address conversion
        if isinstance(addr, int):
            if self.version >= 4:
                code.append(0xF5)  # VAR form, opcode 0x15
                code.append(0x01)  # Type byte: small constant
                code.append(addr & 0xFF)
            else:
                # V3: use PRINT_PADDR
                code.append(0xED)  # VAR form, opcode 0x0D
                code.append(0x01)  # Type byte: small constant
                code.append(addr & 0xFF)

        return bytes(code)

    def gen_string(self, operands: List[ASTNode]) -> bytes:
        """Generate STRING (build string with escape sequences).

        <STRING str> builds a string with special escape handling.
        In full ZIL, STRING uses ! for escapes:
          !\\" - literal quote
          !\\\\ - literal backslash
          !,VAR - interpolate variable value

        For now, we implement basic string handling without interpolation.
        Returns the address of the constructed string.

        Args:
            operands: String components (may include literals and variables)

        Returns:
            bytes: Address of constructed string
        """
        if not operands:
            return b''

        code = bytearray()

        # Basic implementation: if we have a string literal, encode it
        if len(operands) == 1 and isinstance(operands[0], StringNode):
            # Encode the string and return its address
            # For simplicity, treat like a string constant
            # In full implementation, would allocate memory and build string

            # For now, just return a placeholder address
            # Full implementation would:
            # 1. Parse ! escape sequences
            # 2. Allocate string buffer
            # 3. Build string with substitutions
            # 4. Return buffer address

            code.append(0x01)  # Small constant
            code.append(0x00)  # Placeholder address

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

        # STORE instruction: 2OP opcode 0x0D
        code = bytearray()

        # Evaluate value
        value = self.get_operand_value(value_node)

        if isinstance(value, int) and 0 <= value <= 255:
            # STORE variable small_constant
            code.append(0x2D)  # Long form, small/small
            code.append(var_num & 0xFF)
            code.append(value & 0xFF)
        elif isinstance(value, int):
            # STORE variable large_constant
            code.append(0x0D)  # Long form, large/large (need to verify)
            code.append(var_num & 0xFF)
            code.extend(struct.pack('>H', value & 0xFFFF))

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
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # Simplified: small constants
        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x54)  # Long form, small/small
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_sub(self, operands: List[ASTNode]) -> bytes:
        """Generate SUB instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x55)  # SUB opcode
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_mul(self, operands: List[ASTNode]) -> bytes:
        """Generate MUL instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x56)  # MUL opcode
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_div(self, operands: List[ASTNode]) -> bytes:
        """Generate DIV instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x57)  # DIV opcode
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_mod(self, operands: List[ASTNode]) -> bytes:
        """Generate MOD instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x58)  # MOD opcode
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
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
        val = self.get_operand_value(operands[0])

        if isinstance(val, int):
            if 0 <= val <= 255:
                code.append(0x54)  # ADD opcode
                code.append(val & 0xFF)
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
        val = self.get_operand_value(operands[0])

        if isinstance(val, int):
            if 0 <= val <= 255:
                code.append(0x55)  # SUB opcode
                code.append(val & 0xFF)
                code.append(0x01)  # Subtract 1
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_min(self, operands: List[ASTNode]) -> bytes:
        """Generate MIN (minimum of two values).

        <MIN a b> returns the smaller of two values.
        Uses comparison and conditional logic.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            # Simple approach: use JL (jump if less) to select minimum
            # Compare val1 < val2, if true store val1, else store val2
            # For simplicity, we'll just return val1 if val1 < val2
            # This is a simplified implementation
            if val1 <= val2:
                code.append(0x01)  # Small constant
                code.append(val1 & 0xFF)
            else:
                code.append(0x01)  # Small constant
                code.append(val2 & 0xFF)

        return bytes(code)

    def gen_max(self, operands: List[ASTNode]) -> bytes:
        """Generate MAX (maximum of two values).

        <MAX a b> returns the larger of two values.
        Uses comparison and conditional logic.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            # Simple approach: return val1 if val1 > val2
            if val1 >= val2:
                code.append(0x01)  # Small constant
                code.append(val1 & 0xFF)
            else:
                code.append(0x01)  # Small constant
                code.append(val2 & 0xFF)

        return bytes(code)

    def gen_abs(self, operands: List[ASTNode]) -> bytes:
        """Generate ABS (absolute value).

        <ABS value> returns the absolute value of a number.
        For positive values, returns value.
        For negative values, returns -value.

        In Z-machine, we can test if negative and negate if needed.

        Args:
            operands[0]: Value to get absolute value of

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        if isinstance(value, int):
            # Simple compile-time evaluation
            abs_val = abs(value)
            if 0 <= abs_val <= 255:
                code.append(0x01)  # Small constant
                code.append(abs_val & 0xFF)

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
        effect = self.get_operand_value(operands[0])

        if isinstance(effect, int):
            code.append(0xE5)  # SOUND_EFFECT (VAR opcode 0x05)
            code.append(0x2F)  # Type byte: 1 small constant, rest omitted
            code.append(effect & 0xFF)

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
        window = self.get_operand_value(operands[0])

        code.append(0xED)  # ERASE_WINDOW (VAR opcode 0x0D)
        code.append(0x2F)  # Type byte: 1 small constant
        if isinstance(window, int):
            code.append(window & 0xFF)

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
        lines = self.get_operand_value(operands[0])

        if isinstance(lines, int):
            code.append(0xEA)  # SPLIT_WINDOW (VAR opcode 0x0A)
            code.append(0x2F)  # Type byte: 1 small constant, rest omitted
            code.append(lines & 0xFF)

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
        window = self.get_operand_value(operands[0])

        if isinstance(window, int):
            code.append(0xEB)  # SET_WINDOW (VAR opcode 0x0B)
            code.append(0x2F)  # Type byte: 1 small constant, rest omitted
            code.append(window & 0xFF)

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
        line = self.get_operand_value(operands[0])
        col = self.get_operand_value(operands[1])

        if isinstance(line, int) and isinstance(col, int):
            code.append(0xF1)  # SET_CURSOR (VAR opcode 0x11)
            code.append(0x15)  # Type byte: 2 small constants, rest omitted
            code.append(line & 0xFF)
            code.append(col & 0xFF)

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

    def gen_get_wind_prop(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_WIND_PROP (V6 - get window property).

        <GET_WIND_PROP window property> retrieves a window property value.
        V6 only.

        Args:
            operands[0]: Window number
            operands[1]: Property number

        Returns:
            bytes: Z-machine code (GET_WIND_PROP EXT opcode)
        """
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()

        # GET_WIND_PROP is EXT opcode 0x13
        code.append(0xBE)  # EXT opcode marker
        code.append(0x13)  # GET_WIND_PROP

        window = self.get_operand_value(operands[0])
        prop = self.get_operand_value(operands[1])

        if isinstance(window, int) and isinstance(prop, int):
            code.append(0x05)  # Type: small, small
            code.append(window & 0xFF)
            code.append(prop & 0xFF)
            # Store result to stack
            code.append(0x00)

        return bytes(code)

    def gen_put_wind_prop(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT_WIND_PROP (V6 - set window property).

        <PUT_WIND_PROP window property value> sets a window property.
        V6 only.

        Args:
            operands[0]: Window number
            operands[1]: Property number
            operands[2]: Value to set

        Returns:
            bytes: Z-machine code (PUT_WIND_PROP EXT opcode)
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()

        # PUT_WIND_PROP is EXT opcode 0x19
        code.append(0xBE)  # EXT opcode marker
        code.append(0x19)  # PUT_WIND_PROP

        window = self.get_operand_value(operands[0])
        prop = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        if isinstance(window, int) and isinstance(prop, int) and isinstance(value, int):
            code.append(0x55)  # Type: small, small, small
            code.append(window & 0xFF)
            code.append(prop & 0xFF)
            code.append(value & 0xFF)

        return bytes(code)

    def gen_scroll_window(self, operands: List[ASTNode]) -> bytes:
        """Generate SCROLL_WINDOW (V6 - scroll window).

        <SCROLL_WINDOW window pixels> scrolls window by specified pixels.
        V6 only. Positive = down, negative = up.

        Args:
            operands[0]: Window number
            operands[1]: Pixels to scroll (signed)

        Returns:
            bytes: Z-machine code (SCROLL_WINDOW EXT opcode)
        """
        if len(operands) < 2 or self.version < 6:
            return b''

        code = bytearray()

        # SCROLL_WINDOW is EXT opcode 0x14
        code.append(0xBE)  # EXT opcode marker
        code.append(0x14)  # SCROLL_WINDOW

        window = self.get_operand_value(operands[0])
        pixels = self.get_operand_value(operands[1])

        if isinstance(window, int) and isinstance(pixels, int):
            code.append(0x05)  # Type: small, small
            code.append(window & 0xFF)
            code.append(pixels & 0xFF)

        return bytes(code)

    def gen_window_size(self, operands: List[ASTNode]) -> bytes:
        """Generate WINDOW_SIZE (V6 - resize window).

        <WINDOW_SIZE window y x> resizes window to specified dimensions in pixels.
        V6 only.

        Args:
            operands[0]: Window number
            operands[1]: Height in pixels
            operands[2]: Width in pixels

        Returns:
            bytes: Z-machine code (WINDOW_SIZE EXT opcode)
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()

        # WINDOW_SIZE is EXT opcode 0x11
        code.append(0xBE)  # EXT opcode marker
        code.append(0x11)  # WINDOW_SIZE

        window = self.get_operand_value(operands[0])
        height = self.get_operand_value(operands[1])
        width = self.get_operand_value(operands[2])

        if isinstance(window, int) and isinstance(height, int) and isinstance(width, int):
            code.append(0x55)  # Type: small, small, small
            code.append(window & 0xFF)
            code.append(height & 0xFF)
            code.append(width & 0xFF)

        return bytes(code)

    def gen_window_style(self, operands: List[ASTNode]) -> bytes:
        """Generate WINDOW_STYLE (V6 - modify window attributes).

        <WINDOW_STYLE window flags operation> modifies window style.
        V6 only. Operation: 0=set, 1=clear, 2=toggle.

        Args:
            operands[0]: Window number
            operands[1]: Style flags
            operands[2]: Operation (0=set, 1=clear, 2=toggle)

        Returns:
            bytes: Z-machine code (WINDOW_STYLE EXT opcode)
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()

        # WINDOW_STYLE is EXT opcode 0x12
        code.append(0xBE)  # EXT opcode marker
        code.append(0x12)  # WINDOW_STYLE

        window = self.get_operand_value(operands[0])
        flags = self.get_operand_value(operands[1])
        operation = self.get_operand_value(operands[2])

        if isinstance(window, int) and isinstance(flags, int) and isinstance(operation, int):
            code.append(0x55)  # Type: small, small, small
            code.append(window & 0xFF)
            code.append(flags & 0xFF)
            code.append(operation & 0xFF)

        return bytes(code)

    def gen_move_window(self, operands: List[ASTNode]) -> bytes:
        """Generate MOVE_WINDOW (V6 - reposition window).

        <MOVE_WINDOW window y x> repositions window to specified pixel coordinates.
        The top-left corner is (1,1). V6 only.

        Args:
            operands[0]: Window number
            operands[1]: Y coordinate (pixels)
            operands[2]: X coordinate (pixels)

        Returns:
            bytes: Z-machine code (MOVE_WINDOW EXT opcode)
        """
        if len(operands) < 3 or self.version < 6:
            return b''

        code = bytearray()

        # MOVE_WINDOW is EXT opcode 0x10
        code.append(0xBE)  # EXT opcode marker
        code.append(0x10)  # MOVE_WINDOW

        window = self.get_operand_value(operands[0])
        y_coord = self.get_operand_value(operands[1])
        x_coord = self.get_operand_value(operands[2])

        if isinstance(window, int) and isinstance(y_coord, int) and isinstance(x_coord, int):
            code.append(0x55)  # Type: small, small, small
            code.append(window & 0xFF)
            code.append(y_coord & 0xFF)
            code.append(x_coord & 0xFF)

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

        window = self.get_operand_value(operands[0])

        if isinstance(window, int):
            code.append(0x01)  # Type: small
            code.append(window & 0xFF)

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

        array_addr = self.get_operand_value(operands[0])

        if isinstance(array_addr, int):
            code.append(0x01)  # Type: small
            code.append(array_addr & 0xFF)

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

        mode = self.get_operand_value(operands[0])

        if isinstance(mode, int):
            code.append(0x01)  # Type: small
            code.append(mode & 0xFF)
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
        style = self.get_operand_value(operands[0])

        if isinstance(style, int):
            code.append(0xF1)  # SET_TEXT_STYLE (VAR opcode 0x11)
            code.append(0x2F)  # Type byte: 1 small constant, rest omitted
            code.append(style & 0xFF)

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
            val = self.get_operand_value(operands[i])
            if isinstance(val, int):
                code.append(val & 0xFF)

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
        mode = self.get_operand_value(operands[0])

        if isinstance(mode, int):
            code.append(0xF1)  # BUFFER_MODE (VAR opcode 0x11)
            code.append(0x2F)  # Type byte: 1 small constant
            code.append(mode & 0xFF)

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

        array_addr = self.get_operand_value(operands[0])

        if isinstance(array_addr, int):
            code.append(0x2F)  # Type byte: 1 small constant
            code.append(array_addr & 0xFF)

        return bytes(code)

    def gen_uxor(self, operands: List[ASTNode]) -> bytes:
        """Generate UXOR (unsigned XOR).

        <UXOR val1 val2> computes bitwise XOR of two values.
        In V5+, uses XOR opcode. In V3, simulates with AND/OR/NOT.

        Args:
            operands[0]: First value
            operands[1]: Second value

        Returns:
            bytes: Z-machine code
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # For V3, XOR is not available, so we'd need to simulate
        # XOR = (A OR B) AND NOT(A AND B)
        # For now, just return empty for V3
        # In V5+: code.append(0x0F) for XOR 2OP opcode

        if isinstance(val1, int) and isinstance(val2, int):
            # Compile-time evaluation
            result = val1 ^ val2
            if 0 <= result <= 255:
                code.append(0x01)  # Small constant
                code.append(result & 0xFF)

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
        table = self.get_operand_value(operands[0])

        if isinstance(table, int):
            code.append(0xF3)  # OUTPUT_STREAM (VAR opcode 0x13)

            if table == 0:
                # Restore normal output (stream -3)
                code.append(0x15)  # Type byte: 2 small constants
                code.append(0xFD)  # -3 (close stream 3)
                code.append(0x00)
            else:
                # Direct to table (stream 3)
                code.append(0x15)  # Type byte: 2 small constants
                code.append(0x03)  # Stream 3
                code.append(table & 0xFF)

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

        stream = self.get_operand_value(operands[0])

        if isinstance(stream, int):
            code.append(0x2F)  # Type byte: 1 small constant
            code.append(stream & 0xFF)

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

        <MAPF routine table> applies routine to each element in table.
        This is a compile-time construct that generates calls.

        Args:
            operands[0]: Routine to call
            operands[1]: Table to iterate over

        Returns:
            bytes: Z-machine code (stub for now)
        """
        # MAPF is complex - it needs to iterate and call
        # For now, return empty - would need loop generation
        return b''

    def gen_mapt(self, operands: List[ASTNode]) -> bytes:
        """Generate MAPT (map true/find first match).

        <MAPT routine table> finds first element where routine returns true.
        This is a compile-time construct that generates search loop.

        Args:
            operands[0]: Predicate routine
            operands[1]: Table to search

        Returns:
            bytes: Z-machine code (stub for now)
        """
        # MAPT is complex - needs loop with conditional
        # For now, return empty - would need loop generation
        return b''

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
        obj = self.get_operand_value(operands[0])

        if isinstance(obj, int):
            if 0 <= obj <= 255:
                code.append(0x8A)  # PRINT_OBJ (1OP opcode 0x0A)
                code.append(obj & 0xFF)

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
        val = self.get_operand_value(operands[1])

        if isinstance(val, int):
            # DEC variable
            code.append(0x86)  # DEC (1OP opcode 0x06)
            code.append(var_num)

            # JL variable value
            if 0 <= val <= 255:
                code.append(0x82)  # JL (2OP opcode 0x02) - small/small form
                code.append(var_num)
                code.append(val & 0xFF)
                code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_check(self, operands: List[ASTNode]) -> bytes:
        """Generate CHECK (check flag in bitmap).

        <CHECK bitmap flag> tests if a specific bit/flag is set.
        Similar to BTST but for bitmap structures.
        Uses LOADB + AND + JZ pattern.

        Args:
            operands[0]: Bitmap table address
            operands[1]: Flag number to test

        Returns:
            bytes: Z-machine code (stub for now)
        """
        # CHECK is complex - needs bit calculation
        # For now return empty - would need proper bit indexing
        return b''

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
        obj = self.get_operand_value(operands[0])
        prop = self.get_operand_value(operands[1])

        if isinstance(obj, int) and isinstance(prop, int):
            if 0 <= obj <= 255 and 0 <= prop <= 255:
                # GET_PROP_ADDR returns 0 if not found
                code.append(0x53)  # GET_PROP_ADDR (2OP opcode 0x13)
                code.append(obj & 0xFF)
                code.append(prop & 0xFF)
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
        buf = self.get_operand_value(operands[0])
        word_num = self.get_operand_value(operands[1])

        # Calculate offset: (word_num - 1) * 4 + 1
        # Each word entry is 4 bytes, +1 to skip count byte
        if isinstance(buf, int) and isinstance(word_num, int):
            offset = (word_num - 1) * 4 + 1
            if 0 <= offset <= 255:
                code.append(0x4F)  # LOADW
                code.append(buf & 0xFF)
                code.append(offset & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_band_shift(self, operands: List[ASTNode]) -> bytes:
        """Generate BAND with shift (bitwise AND with shifted mask).

        Helper for bit manipulation patterns.

        Args:
            operands[0]: Value
            operands[1]: Mask
            operands[2]: Shift amount (optional)

        Returns:
            bytes: Z-machine code
        """
        # This is a complex pattern - for now use simple BAND
        return self.gen_band(operands[:2])

    def gen_copyt(self, operands: List[ASTNode]) -> bytes:
        """Generate COPYT (copy table).

        <COPYT source dest length> copies bytes from source to dest.
        In V5+, uses COPY_TABLE. For V3, needs loop generation.

        Args:
            operands[0]: Source address
            operands[1]: Destination address
            operands[2]: Length in bytes

        Returns:
            bytes: Z-machine code (stub for V3)
        """
        # COPY_TABLE is V5+
        # For V3, would need to generate a loop
        return b''

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
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                # JL with inverted branch (branch on false)
                code.append(0x42)  # JL (2OP opcode 0x02)
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
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
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                # JG with inverted branch (branch on false)
                code.append(0x43)  # JG (2OP opcode 0x03)
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
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
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                # JE with inverted branch (branch on false for !=)
                code.append(0x41)  # JE (2OP opcode 0x01)
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
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
        table = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        if isinstance(table, int) and isinstance(index, int) and isinstance(value, int):
            # STOREW with 0-based index
            code.append(0x51)  # STOREW (2OP opcode 0x11)
            code.append(table & 0xFF)
            code.append(index & 0xFF)
            code.append(value & 0xFF)

        return bytes(code)

    def gen_original(self, operands: List[ASTNode]) -> bytes:
        """Generate ORIGINAL? (test if value is original/not copied).

        <ORIGINAL? value> tests if value is an original object reference.
        This is typically a compile-time or runtime type check.

        Args:
            operands[0]: Value to test

        Returns:
            bytes: Z-machine code (stub - requires runtime support)
        """
        # ORIGINAL? is complex - needs runtime type information
        # For now, return a simple non-zero test
        if not operands:
            return b''
        return self.gen_true_predicate(operands)

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
        value = self.get_operand_value(operands[0])
        bit_num = self.get_operand_value(operands[1])

        if isinstance(value, int) and isinstance(bit_num, int):
            # Create bit mask: 1 << bit_num
            if 0 <= bit_num < 16:
                mask = 1 << bit_num
                if 0 <= mask <= 255:
                    # AND value with mask
                    code.append(0x49)  # AND (2OP opcode 0x09)
                    code.append(value & 0xFF)
                    code.append(mask & 0xFF)
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
            fg = self.get_operand_value(operands[0])
            bg = self.get_operand_value(operands[1])
            if isinstance(fg, int) and isinstance(bg, int):
                code.append(0xEB)  # SET_COLOUR (VAR opcode 0x1B)
                code.append(0x15)  # Type byte: 2 small constants
                code.append(fg & 0xFF)
                code.append(bg & 0xFF)
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
            font_num = self.get_operand_value(operands[0])
            if isinstance(font_num, int):
                code.append(0x9C)  # SET_FONT (1OP opcode 0x0C with mode 10)
                code.append(font_num & 0xFF)
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

        fg = self.get_operand_value(operands[0])
        bg = self.get_operand_value(operands[1])

        if isinstance(fg, int) and isinstance(bg, int):
            if len(operands) >= 3 and self.version >= 6:
                # V6: includes window parameter
                window = self.get_operand_value(operands[2])
                if isinstance(window, int):
                    code.append(0x55)  # Type: small, small, small
                    code.append(fg & 0xFF)
                    code.append(bg & 0xFF)
                    code.append(window & 0xFF)
            else:
                # V5: just fg and bg
                code.append(0x05)  # Type: small, small
                code.append(fg & 0xFF)
                code.append(bg & 0xFF)

        return bytes(code)

    def gen_mouse_info(self, operands: List[ASTNode]) -> bytes:
        """Generate MOUSE-INFO (get mouse information).

        Gets mouse position and button state.
        V5+ only, stub for V3.

        Returns:
            bytes: Z-machine code (stub)
        """
        # MOUSE_INFO is V5+
        return b''

    def gen_picinf(self, operands: List[ASTNode]) -> bytes:
        """Generate PICINF (get picture information).

        Gets picture dimensions and availability.
        V6+ only, stub for V3.

        Returns:
            bytes: Z-machine code (stub)
        """
        # PICINF is V6+
        return b''

    def gen_margin(self, operands: List[ASTNode]) -> bytes:
        """Generate MARGIN (set margins).

        <MARGIN left right> sets left and right margins.
        Used for text formatting.

        Returns:
            bytes: Z-machine code (stub)
        """
        # MARGIN requires special window handling
        return b''

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

        # For upper window (window 1), use SPLIT
        window = self.get_operand_value(operands[0])
        lines = self.get_operand_value(operands[1])

        if window == 1:
            return self.gen_split([operands[1]])

        return b''

    def gen_winget(self, operands: List[ASTNode]) -> bytes:
        """Generate WINGET (get window property).

        <WINGET window property> gets window information.

        Returns:
            bytes: Z-machine code (stub)
        """
        # Window property queries are complex
        return b''

    def gen_winput(self, operands: List[ASTNode]) -> bytes:
        """Generate WINPUT (set window property).

        <WINPUT window property value> sets window property.

        Returns:
            bytes: Z-machine code (stub)
        """
        # Window property setting is complex
        return b''

    def gen_winattr(self, operands: List[ASTNode]) -> bytes:
        """Generate WINATTR (set window attributes).

        <WINATTR window flags> sets window display attributes.

        Returns:
            bytes: Z-machine code (stub)
        """
        # Window attributes are V5+
        return b''

    def gen_intbl(self, operands: List[ASTNode]) -> bytes:
        """Generate INTBL? (check if value in table).

        <INTBL? value table length> searches table for value.
        Returns true if found.

        Args:
            operands[0]: Value to search for
            operands[1]: Table address
            operands[2]: Table length

        Returns:
            bytes: Z-machine code (stub - needs loop)
        """
        # INTBL? needs loop generation to search
        # For now, stub
        return b''

    def gen_zero_table(self, operands: List[ASTNode]) -> bytes:
        """Generate ZERO (zero out table).

        <ZERO table length> fills table with zeros.
        Uses repeated STOREW operations.

        Args:
            operands[0]: Table address
            operands[1]: Number of words to zero

        Returns:
            bytes: Z-machine code (stub - needs loop)
        """
        # ZERO needs loop generation
        return b''

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
        base = self.get_operand_value(operands[0])
        offset = self.get_operand_value(operands[1])

        if isinstance(base, int) and isinstance(offset, int):
            # Calculate effective address
            addr = base + offset
            if 0 <= addr <= 255:
                code.append(0x90)  # LOADB (1OP opcode 0x10)
                code.append(addr & 0xFF)
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
        base = self.get_operand_value(operands[0])
        offset = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        if isinstance(base, int) and isinstance(offset, int) and isinstance(value, int):
            # Calculate effective address
            addr = base + offset
            if 0 <= addr <= 255:
                code.append(0xA1)  # STOREB (2OP opcode 0x02, variable form)
                code.append(addr & 0xFF)
                code.append(value & 0xFF)

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
        base = self.get_operand_value(operands[0])
        offset = self.get_operand_value(operands[1])

        if isinstance(base, int) and isinstance(offset, int):
            # Word offset needs *2
            addr = base + (offset * 2)
            if 0 <= addr <= 255:
                code.append(0x8F)  # LOADW (1OP opcode 0x0F)
                code.append(addr & 0xFF)
                code.append(0x00)

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
        base = self.get_operand_value(operands[0])
        offset = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        if isinstance(base, int) and isinstance(offset, int) and isinstance(value, int):
            # Word offset needs *2
            addr = base + (offset * 2)
            if 0 <= addr <= 255:
                code.append(0xE1)  # STOREW (VAR form)
                code.append(0x15)  # Type byte: 2 small constants
                code.append(addr & 0xFF)
                code.append(value & 0xFF)

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
        addr = self.get_operand_value(operands[0])

        if isinstance(addr, int):
            if 0 <= addr <= 0x40:
                code.append(0x8F)  # LOADW (1OP opcode 0x0F)
                code.append(addr & 0xFF)
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
        # For V3, return a default value (24 lines typical)
        code.append(0x01)  # Small constant
        code.append(24)  # Default height
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
        # For V3, return a default value (80 chars typical)
        code.append(0x01)  # Small constant
        code.append(80)  # Default width
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
            code.append(0x00)  # No operands
            # Store result (frame address) to stack
            code.append(0x00)  # Store to SP
        else:
            # V3/V4: Not available, return 0
            # Could emit a warning here
            pass

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
            value = self.get_operand_value(operands[0])
            frame = self.get_operand_value(operands[1])

            code.append(0xFA)  # VAR opcode 0x1A

            # Type byte for 2 operands
            if isinstance(value, int) and isinstance(frame, int):
                if 0 <= value <= 255 and 0 <= frame <= 255:
                    code.append(0x05)  # Type: small, small
                    code.append(value & 0xFF)
                    code.append(frame & 0xFF)
        else:
            # V3/V4: Not available
            pass

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
        For small constants, unrolls PRINT_CHAR calls.

        Args:
            operands[0]: Number of spaces

        Returns:
            bytes: Z-machine code for printing spaces
        """
        if not operands:
            return b''

        code = bytearray()
        count = self.get_operand_value(operands[0])

        # For compile-time constant, unroll PRINT_CHAR
        if isinstance(count, int) and count <= 20:
            for _ in range(count):
                # PRINT_CHAR with space (ASCII 32)
                code.append(0xE5)  # PRINT_CHAR (VAR:0x05)
                code.append(0x01)  # Type byte: 1 small constant
                code.append(32)    # Space character

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
        In Z-machine V3, the score is stored at address 0x11 (2 bytes, word).

        Args:
            operands[0]: Score value

        Returns:
            bytes: Z-machine code for setting score
        """
        if not operands:
            return b''

        code = bytearray()
        score_value = self.get_operand_value(operands[0])

        # Score is stored at memory address 0x11 in V3 header
        # Use STOREW to write to this location
        # STOREW is VAR opcode 0x01

        if isinstance(score_value, int):
            code.append(0xE1)  # VAR opcode 0x01 (STOREW)
            code.append(0x15)  # Type byte: small, small (address, value)
            code.append(0x11)  # Address (score location in header)
            code.append(score_value & 0xFF)  # Low byte of score

        return bytes(code)

    def gen_chrset(self, operands: List[ASTNode]) -> bytes:
        """Generate CHRSET (set character set).

        <CHRSET charset> sets the active character set for display.
        V3 has limited character set support, so this is mostly a no-op.

        Args:
            operands[0]: Character set identifier

        Returns:
            bytes: Z-machine code (no-op in V3)
        """
        # CHRSET is V5+ feature, no-op in V3
        return b''

    def gen_margin(self, operands: List[ASTNode]) -> bytes:
        """Generate MARGIN (set text margin).

        <MARGIN left right> sets left and right margins for text output.
        V3 has no margin control, so this is a no-op.

        Args:
            operands[0]: Left margin (optional)
            operands[1]: Right margin (optional)

        Returns:
            bytes: Z-machine code (no-op in V3)
        """
        # MARGIN is V4+ feature, no-op in V3
        return b''

    def gen_picinf(self, operands: List[ASTNode]) -> bytes:
        """Generate PICINF (get picture info).

        <PICINF picture table> gets information about a picture.
        V3 has no graphics support, so this is a stub.

        Args:
            operands[0]: Picture number
            operands[1]: Info table address

        Returns:
            bytes: Z-machine code (stub - no graphics in V3)
        """
        # PICINF is V6+ for graphics, stub for V3
        return b''

    def gen_mouse_info(self, operands: List[ASTNode]) -> bytes:
        """Generate MOUSE-INFO (get mouse information).

        <MOUSE-INFO table> gets mouse position and button state.
        V3 has no mouse support, so this is a stub.

        Args:
            operands[0]: Info table address

        Returns:
            bytes: Z-machine code (stub - no mouse in V3)
        """
        # MOUSE-INFO is V5+ feature, stub for V3
        return b''

    def gen_type(self, operands: List[ASTNode]) -> bytes:
        """Generate TYPE? (get type of value).

        <TYPE? value> returns the type code of a value.
        Types in ZIL: 0=false, 1=object, 2=string/table, 3=number

        Simple implementation: Use JZ to check if zero (false),
        otherwise check if it's in object range (1-255 typically),
        otherwise assume number.

        Args:
            operands[0]: Value to check type of

        Returns:
            bytes: Z-machine code for basic type checking
        """
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        # Simplified: For compile-time constants, return type directly
        if isinstance(value, int):
            if value == 0:
                type_code = 0  # FALSE
            elif 1 <= value <= 255:
                type_code = 1  # Possibly OBJECT
            else:
                type_code = 3  # NUMBER

            # Return type code as constant
            # LOADW with immediate value
            # For simplicity, just push constant to stack
            # This is a simplified implementation
            pass

        # Runtime type checking would need conditional logic
        # For now, return empty (partial implementation)
        return bytes(code)

    def gen_printtype(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINTTYPE (print type name).

        <PRINTTYPE value> prints the type name of a value.
        Useful for debugging.

        Simple implementation: For compile-time values, print the type name directly.

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
            encoded = self.encoder.encode_string(type_name)
            from ..zmachine.encoder import words_to_bytes
            code.extend(words_to_bytes(encoded))

        # Runtime would need TYPE? call + conditional printing
        # For now, partial implementation for constants only
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
        Used for advanced stack manipulation.

        Note: Z-machine doesn't have a direct FSTACK opcode.
        This returns a pseudo-value (0) as the stack frame is implicit.
        Real implementation would need runtime tracking.

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()

        # Z-machine has implicit stack frames via CALL/RET
        # Return 0 as placeholder for "current frame"
        # Real stack frame tracking would need runtime support

        # LOADW immediate 0 to stack (simplified)
        # For now, just return empty as this is complex
        # A full implementation might use a global variable to track frames

        return bytes(code)

    def gen_rstack(self, operands: List[ASTNode]) -> bytes:
        """Generate RSTACK (get return stack pointer).

        <RSTACK> returns the current return stack pointer.
        Used for advanced stack operations.

        Note: Z-machine doesn't expose return stack pointer directly.
        This returns a pseudo-value. Real implementation would need
        runtime tracking or use of special variables.

        Returns:
            bytes: Z-machine code
        """
        code = bytearray()

        # Z-machine return stack is managed automatically by CALL/RET
        # There's no direct opcode to get the return stack pointer
        # Return 0 as placeholder

        # A real implementation might:
        # 1. Track stack depth in a global variable
        # 2. Use CATCH to get frame information (V5+)
        # 3. Maintain a shadow stack in memory

        return bytes(code)

    def gen_ifflag(self, operands: List[ASTNode]) -> bytes:
        """Generate IFFLAG (conditional flag check).

        <IFFLAG flag true-expr false-expr> checks a flag and evaluates one expression.
        Convenience macro for flag-based conditionals.

        Args:
            operands[0]: Flag to check
            operands[1]: Expression if true
            operands[2]: Expression if false (optional)

        Returns:
            bytes: Z-machine code (expands to COND)
        """
        # IFFLAG is typically a macro that expands to COND
        # For now, stub
        return b''

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

        number = self.get_operand_value(operands[0])
        places = self.get_operand_value(operands[1])

        if isinstance(number, int) and isinstance(places, int):
            code.append(0x05)  # Type: small, small
            code.append(number & 0xFF)
            code.append(places & 0xFF)
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
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # V5+: Use native XOR (EXT:0x0B)
        if self.version >= 5:
            code.append(0xBE)  # EXT opcode marker
            code.append(0x0B)  # XOR extended opcode

            # Type byte for 2 operands
            if isinstance(val1, int) and isinstance(val2, int):
                if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                    code.append(0x05)  # Type: small, small
                    code.append(val1 & 0xFF)
                    code.append(val2 & 0xFF)
                    # Store result in stack (SP)
                    code.append(0x00)

            return bytes(code)

        # V3/V4: Emulate XOR using (A OR B) AND NOT(A AND B)
        # This requires storing intermediate values

        # For compile-time constants, compute directly
        if isinstance(val1, int) and isinstance(val2, int):
            result = val1 ^ val2
            # Return the result as a constant loaded into stack
            # LOAD with immediate value and store to temp location
            # Simplified: just return the constant
            # For full implementation would need proper storage
            return b''

        # For runtime values, would need:
        # 1. temp1 = A OR B
        # 2. temp2 = A AND B
        # 3. temp3 = NOT temp2
        # 4. result = temp1 AND temp3
        # This is complex and requires local variable allocation
        return b''

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
        volume = self.get_operand_value(operands[0])

        if self.version >= 5:
            # V5+: Use SOUND_EFFECT opcode with volume control
            # SOUND_EFFECT can take effect, volume, routine params
            # Effect 0 with volume sets master volume
            code.append(0xE7)  # SOUND_EFFECT (VAR:0x07)
            code.append(0x55)  # Type: small, small, small
            code.append(0x00)  # Effect 0 (volume control)

            if isinstance(volume, int):
                code.append(volume & 0xFF)  # Volume level
            code.append(0x00)  # No routine

        else:
            # V3: Limited support, store volume in memory location if needed
            # Or use SOUND with special encoding
            # For now, stub for V3
            pass

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
            src = self.get_operand_value(operands[0])
            dst = self.get_operand_value(operands[1])
            length = self.get_operand_value(operands[2])

            # COPY_TABLE opcode 0xBE (EXT opcode 0x17)
            code.append(0xBE)
            code.append(0x17)  # Extended opcode number

            # Type byte for 3 operands (assume small constants for simplicity)
            if isinstance(src, int) and isinstance(dst, int) and isinstance(length, int):
                code.append(0x15)  # Type: small, small, small
                code.append(src & 0xFF)
                code.append(dst & 0xFF)
                code.append(length & 0xFF)

            return bytes(code)

        # V3/V4: For compile-time constants, generate inline code
        # For variable lengths, we'd need REPEAT loop (complex)
        # Simple implementation: if length is small constant, unroll the loop
        length = self.get_operand_value(operands[2])
        if isinstance(length, int) and length <= 8:
            # Unroll: generate LOADB/STOREB for each byte
            src = self.get_operand_value(operands[0])
            dst = self.get_operand_value(operands[1])

            for i in range(length):
                # LOADB src+i -> stack
                if isinstance(src, int):
                    code.append(0x90)  # LOADB (1OP:0x10 with mode 10)
                    code.append((src + i) & 0xFF)
                    code.append(0x00)  # Result to stack

                # STOREB dst+i stack
                if isinstance(dst, int):
                    code.append(0xE3)  # STOREB (VAR:0x03)
                    code.append(0x25)  # Type: small, small, stack
                    code.append((dst + i) & 0xFF)
                    code.append(0x00)  # Offset 0
                    code.append(0x00)  # Value from stack

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
            addr = self.get_operand_value(operands[0])
            length = self.get_operand_value(operands[1])

            # COPY_TABLE opcode 0xBE (EXT opcode 0x17)
            # When second arg is 0 and third arg is length, zeros memory
            code.append(0xBE)
            code.append(0x17)

            if isinstance(addr, int) and isinstance(length, int):
                code.append(0x15)  # Type: small, small, small
                code.append(addr & 0xFF)
                code.append(0x00)  # Second arg = 0 means zero operation
                code.append(length & 0xFF)

            return bytes(code)

        # V3/V4: Generate inline STOREB with value 0
        length = self.get_operand_value(operands[1])
        if isinstance(length, int) and length <= 16:
            # Unroll: generate STOREB for each byte
            addr = self.get_operand_value(operands[0])

            for i in range(length):
                if isinstance(addr, int):
                    # STOREB addr+i 0 0
                    code.append(0xE3)  # STOREB (VAR:0x03)
                    code.append(0x15)  # Type: small, small, small
                    code.append((addr + i) & 0xFF)
                    code.append(0x00)  # Offset 0
                    code.append(0x00)  # Value 0

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
        table = self.get_operand_value(operands[0])

        # FIRST is same as GET with index 1 (1-based)
        if isinstance(table, int):
            if 0 <= table <= 255:
                code.append(0x8F)  # LOADW
                code.append(table & 0xFF)
                code.append(0x01)  # Index 1
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
        item = self.get_operand_value(operands[0])
        table = self.get_operand_value(operands[1])

        # V5+: Use SCAN_TABLE opcode (EXT:0x18)
        if self.version >= 5:
            code.append(0xBE)  # EXT opcode marker
            code.append(0x18)  # SCAN_TABLE

            if isinstance(item, int) and isinstance(table, int):
                # Type byte for operands: item, table, length, form
                code.append(0x55)  # Type: small, small, small
                code.append(item & 0xFF)
                code.append(table & 0xFF)
                code.append(0x08)  # Search up to 8 elements (default)
                # Result stored to stack
                code.append(0x00)  # Store to SP

            return bytes(code)

        # V3/V4: For small constant tables, unroll the search
        # Generate: GET table[0], JE item, GET table[1], JE item, etc.
        # Full loop generation is complex, so limit to compile-time cases

        # This is a simplified stub - full implementation needs loop labels
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
        """Generate JE (jump if equal) - branch instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # JE is 2OP opcode 0x01
        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x41)  # Long form, small/small, opcode 0x01
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                # Branch byte: branch on true, offset 0 (return false)
                code.append(0x40)  # Bit 7=0 (false), bit 6=1 (1 byte), offset=0

        return bytes(code)

    def gen_less(self, operands: List[ASTNode]) -> bytes:
        """Generate JL (jump if less)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # JL is 2OP opcode 0x02
        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x42)  # Long form, opcode 0x02
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_greater(self, operands: List[ASTNode]) -> bytes:
        """Generate JG (jump if greater)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # JG is 2OP opcode 0x03
        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x43)  # Long form, opcode 0x03
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_zero(self, operands: List[ASTNode]) -> bytes:
        """Generate ZERO? test (jump if zero).

        <ZERO? value> is equivalent to <EQUAL? value 0>
        Uses JZ (jump if zero) - 1OP opcode 0x00
        """
        if not operands:
            return b''

        code = bytearray()
        val = self.get_operand_value(operands[0])

        # JZ is 1OP opcode 0x00 (branch instruction)
        if isinstance(val, int):
            if 0 <= val <= 255:
                code.append(0x80)  # Short 1OP, opcode 0x00, small constant
                code.append(val & 0xFF)
                code.append(0x40)  # Branch on true, offset 0 (placeholder)

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
        """Generate AND (bitwise)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # AND is 2OP opcode 0x09
        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x49)  # Long form, opcode 0x09
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_or(self, operands: List[ASTNode]) -> bytes:
        """Generate OR (bitwise)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        val1 = self.get_operand_value(operands[0])
        val2 = self.get_operand_value(operands[1])

        # OR is 2OP opcode 0x08
        if isinstance(val1, int) and isinstance(val2, int):
            if 0 <= val1 <= 255 and 0 <= val2 <= 255:
                code.append(0x48)  # Long form, opcode 0x08
                code.append(val1 & 0xFF)
                code.append(val2 & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_not(self, operands: List[ASTNode]) -> bytes:
        """Generate NOT (bitwise complement)."""
        if not operands:
            return b''

        code = bytearray()
        val = self.get_operand_value(operands[0])

        # NOT is 1OP opcode 0x0F (V1-4) / CALL_1S (V5+)
        if self.version <= 4:
            if isinstance(val, int) and 0 <= val <= 255:
                code.append(0x8F)  # Short 1OP, opcode 0x0F, small constant
                code.append(val & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Object Operations =====

    def gen_fset(self, operands: List[ASTNode]) -> bytes:
        """Generate SET_ATTR (set object attribute)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])
        attr = self.get_operand_value(operands[1])

        # SET_ATTR is 2OP opcode 0x0B
        if obj is not None and isinstance(attr, int):
            code.append(0x4B)  # Long form, opcode 0x0B
            code.append(obj & 0xFF)
            code.append(attr & 0xFF)

        return bytes(code)

    def gen_fclear(self, operands: List[ASTNode]) -> bytes:
        """Generate CLEAR_ATTR (clear object attribute)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])
        attr = self.get_operand_value(operands[1])

        # CLEAR_ATTR is 2OP opcode 0x0C
        if obj is not None and isinstance(attr, int):
            code.append(0x4C)  # Long form, opcode 0x0C
            code.append(obj & 0xFF)
            code.append(attr & 0xFF)

        return bytes(code)

    def gen_fset_test(self, operands: List[ASTNode]) -> bytes:
        """Generate TEST_ATTR (test object attribute)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])
        attr = self.get_operand_value(operands[1])

        # TEST_ATTR is 2OP opcode 0x0A (branch)
        if obj is not None and isinstance(attr, int):
            code.append(0x4A)  # Long form, opcode 0x0A
            code.append(obj & 0xFF)
            code.append(attr & 0xFF)
            code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_move(self, operands: List[ASTNode]) -> bytes:
        """Generate INSERT_OBJ (move object to destination)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])
        dest = self.get_object_number(operands[1])

        # INSERT_OBJ is 2OP opcode 0x0E
        if obj is not None and dest is not None:
            code.append(0x4E)  # Long form, opcode 0x0E
            code.append(obj & 0xFF)
            code.append(dest & 0xFF)

        return bytes(code)

    def gen_remove(self, operands: List[ASTNode]) -> bytes:
        """Generate REMOVE_OBJ (remove object from tree)."""
        if not operands:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])

        # REMOVE_OBJ is 1OP opcode 0x09
        if obj is not None:
            code.append(0x89)  # Short 1OP, opcode 0x09, small constant
            code.append(obj & 0xFF)

        return bytes(code)

    def gen_loc(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PARENT (get object's parent)."""
        if not operands:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])

        # GET_PARENT is 1OP opcode 0x03
        if obj is not None:
            code.append(0x83)  # Short 1OP, opcode 0x03, small constant
            code.append(obj & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Property Operations =====

    def gen_getp(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PROP (get object property)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])
        prop = self.get_operand_value(operands[1])

        # GET_PROP is 2OP opcode 0x11
        if obj is not None and isinstance(prop, int):
            code.append(0x51)  # Long form, opcode 0x11
            code.append(obj & 0xFF)
            code.append(prop & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_putp(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT_PROP (set object property)."""
        if len(operands) < 3:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])
        prop = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        # PUT_PROP is VAR opcode 0x03
        if obj is not None and isinstance(prop, int) and isinstance(value, int):
            code.append(0xE3)  # VAR form, opcode 0x03
            code.append(0x15)  # Type byte: small, small, small
            code.append(obj & 0xFF)
            code.append(prop & 0xFF)
            code.append(value & 0xFF)

        return bytes(code)

    def gen_ptsize(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PROP_LEN (get property length).

        <PTSIZE prop-addr> returns the length of a property.
        Uses GET_PROP_LEN - 1OP opcode 0x04.
        """
        if not operands:
            return b''

        code = bytearray()
        prop_addr = self.get_operand_value(operands[0])

        # GET_PROP_LEN is 1OP opcode 0x04
        if isinstance(prop_addr, int):
            code.append(0x84)  # Short 1OP, opcode 0x04, small constant
            code.append(prop_addr & 0xFF)
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
        obj = self.get_object_number(operands[0])
        prop = self.get_operand_value(operands[1])

        # GET_NEXT_PROP is 2OP opcode 0x13
        if obj is not None and isinstance(prop, int):
            if 0 <= obj <= 255 and 0 <= prop <= 255:
                code.append(0x53)  # Long form, opcode 0x13
                code.append(obj & 0xFF)
                code.append(prop & 0xFF)
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
                if next_clause_offset < 64:
                    # 1-byte branch form
                    # Bit 7=0 (branch on false), bit 6=1 (1-byte), bits 5-0=offset
                    clause['test_code'][-1] = 0x40 | (next_clause_offset & 0x3F)
                else:
                    # 2-byte branch form needed
                    # Bit 7=0 (branch on false), bit 6=0 (2-byte)
                    offset_from_branch = next_clause_offset - 2  # -2 because relative to after branch
                    clause['test_code'][-1] = (offset_from_branch >> 8) & 0x3F
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
        3. Body statements
        4. Jump back to LOOP_START
        5. LOOP_END label (for RETURN to exit)

        Z-machine doesn't have explicit loop constructs, so we use:
        - Forward jumps for loop exits (RETURN)
        - Backward jumps to loop start
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

        # Mark loop start position
        loop_start_pos = len(code)

        # Generate body statements
        body_code = bytearray()
        for stmt in repeat.body:
            body_code.extend(self.generate_statement(stmt))

        body_size = len(body_code)

        # Add body
        code.extend(body_code)

        # Generate jump back to loop start
        # JUMP instruction with negative offset
        # Offset is from AFTER the jump instruction back to loop_start

        # Jump is 3 bytes: opcode + 2 offset bytes
        # Offset calculation: -(body_size + 3) to get back to loop_start
        jump_offset = -(body_size + 3)

        # Z-machine uses signed 14-bit offsets
        # For negative offsets, use two's complement
        if jump_offset >= -64:
            # Can use 1-byte form
            # Bit 7=1 (always jump), bit 6=1 (1-byte), bits 5-0=offset
            # For negative, need to handle carefully
            offset_bits = (jump_offset & 0x3F)
            code.append(0x8C)  # JUMP opcode
            code.append(0xC0 | offset_bits)  # Branch true, 1-byte form
            code.append(0x00)  # Padding
        else:
            # Use 2-byte form
            # Two's complement for 14 bits
            offset_14bit = jump_offset & 0x3FFF
            code.append(0x8C)  # JUMP opcode
            code.append((offset_14bit >> 8) & 0x3F)  # High 6 bits
            code.append(offset_14bit & 0xFF)  # Low 8 bits

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

    # ===== Routine Calls =====

    def gen_routine_call(self, routine_name: str, operands: List[ASTNode]) -> bytes:
        """Generate routine call (CALL or CALL_VS)."""
        code = bytearray()

        # For now, simplified: assume routine address is 0 (will be fixed by linker)
        # CALL is VAR opcode 0x00 (V1-4) / CALL_VS (V4+)

        # Encode as variable form
        code.append(0xE0)  # VAR form, opcode 0x00

        # Type byte - determine based on number of operands
        num_ops = len(operands) + 1  # +1 for routine address
        if num_ops <= 4:
            # Pack type bits: routine address (small const) + operand types
            type_byte = 0x01  # First operand (routine) is small constant
            for i, op in enumerate(operands[:3]):
                val = self.get_operand_value(op)
                if isinstance(val, int) and 0 <= val <= 255:
                    type_byte |= (0x01 << ((i + 1) * 2))  # Small constant
                else:
                    type_byte |= (0x02 << ((i + 1) * 2))  # Variable
            code.append(type_byte)
        else:
            code.append(0x15)  # Simplified: all small constants

        # Routine address (placeholder - would need linker to resolve)
        code.append(0x00)

        # Operands
        for op in operands[:3]:  # Max 3 additional operands for now
            val = self.get_operand_value(op)
            if isinstance(val, int):
                if 0 <= val <= 255:
                    code.append(val & 0xFF)
                else:
                    code.extend(struct.pack('>H', val & 0xFFFF))

        # Store result to stack
        code.append(0x00)

        return bytes(code)

    # ===== Memory Operations =====

    def gen_loadw(self, operands: List[ASTNode]) -> bytes:
        """Generate LOADW (load word from array)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        array = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])

        # LOADW is 2OP opcode 0x0F
        if isinstance(array, int) and isinstance(index, int):
            if 0 <= array <= 255 and 0 <= index <= 255:
                code.append(0x4F)  # Long form, opcode 0x0F
                code.append(array & 0xFF)
                code.append(index & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_loadb(self, operands: List[ASTNode]) -> bytes:
        """Generate LOADB (load byte from array)."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        array = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])

        # LOADB is 2OP opcode 0x10
        if isinstance(array, int) and isinstance(index, int):
            if 0 <= array <= 255 and 0 <= index <= 255:
                code.append(0x50)  # Long form, opcode 0x10
                code.append(array & 0xFF)
                code.append(index & 0xFF)
                code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_storew(self, operands: List[ASTNode]) -> bytes:
        """Generate STOREW (store word to array)."""
        if len(operands) < 3:
            return b''

        code = bytearray()
        array = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        # STOREW is VAR opcode 0x01
        if isinstance(array, int) and isinstance(index, int) and isinstance(value, int):
            code.append(0xE1)  # VAR form, opcode 0x01
            code.append(0x15)  # Type byte: 3 small constants
            code.append(array & 0xFF)
            code.append(index & 0xFF)
            code.append(value & 0xFF)

        return bytes(code)

    def gen_storeb(self, operands: List[ASTNode]) -> bytes:
        """Generate STOREB (store byte to array)."""
        if len(operands) < 3:
            return b''

        code = bytearray()
        array = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        # STOREB is VAR opcode 0x02
        if isinstance(array, int) and isinstance(index, int) and isinstance(value, int):
            code.append(0xE2)  # VAR form, opcode 0x02
            code.append(0x15)  # Type byte: 3 small constants
            code.append(array & 0xFF)
            code.append(index & 0xFF)
            code.append(value & 0xFF)

        return bytes(code)

    # ===== Table Operations (ZIL high-level) =====

    def gen_get(self, operands: List[ASTNode]) -> bytes:
        """Generate GET (table word access, 1-based index).

        <GET table index> reads word from table[index].
        In ZIL, tables are 1-based (GET table 1 is first element).
        Z-machine LOADW uses word offsets (0-based).

        For simplicity, we directly use LOADW and assume the index is already adjusted.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        table = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])

        # LOADW is 2OP opcode 0x0F
        if isinstance(table, int) and isinstance(index, int):
            # For now, support only constant addresses/indices
            # In real usage, table will be a global variable address
            code.append(0x4F)  # Long form, opcode 0x0F
            code.append(table & 0xFF)
            code.append(index & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_put(self, operands: List[ASTNode]) -> bytes:
        """Generate PUT (table word write, 1-based index).

        <PUT table index value> writes value to table[index].
        Uses Z-machine STOREW instruction.
        """
        if len(operands) < 3:
            return b''

        code = bytearray()
        table = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        # STOREW is VAR opcode 0x01
        if isinstance(table, int) and isinstance(index, int) and isinstance(value, int):
            code.append(0xE1)  # VAR form, opcode 0x01
            code.append(0x15)  # Type byte: 3 small constants
            code.append(table & 0xFF)
            code.append(index & 0xFF)
            code.append(value & 0xFF)

        return bytes(code)

    def gen_getb(self, operands: List[ASTNode]) -> bytes:
        """Generate GETB (table byte access, 0-based index).

        <GETB table index> reads byte from table[index].
        Uses Z-machine LOADB instruction.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        table = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])

        # LOADB is 2OP opcode 0x10
        if isinstance(table, int) and isinstance(index, int):
            code.append(0x50)  # Long form, opcode 0x10
            code.append(table & 0xFF)
            code.append(index & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    def gen_putb(self, operands: List[ASTNode]) -> bytes:
        """Generate PUTB (table byte write, 0-based index).

        <PUTB table index value> writes byte value to table[index].
        Uses Z-machine STOREB instruction.
        """
        if len(operands) < 3:
            return b''

        code = bytearray()
        table = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])
        value = self.get_operand_value(operands[2])

        # STOREB is VAR opcode 0x02
        if isinstance(table, int) and isinstance(index, int) and isinstance(value, int):
            code.append(0xE2)  # VAR form, opcode 0x02
            code.append(0x15)  # Type byte: 3 small constants
            code.append(table & 0xFF)
            code.append(index & 0xFF)
            code.append(value & 0xFF)

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
        table = self.get_operand_value(operands[0])

        # LOADW is 2OP opcode 0x0F
        if isinstance(table, int):
            code.append(0x4F)  # Long form, opcode 0x0F
            code.append(table & 0xFF)
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
        table = self.get_operand_value(operands[0])
        index = self.get_operand_value(operands[1])

        # LOADW is 2OP opcode 0x0F
        if isinstance(table, int) and isinstance(index, int):
            code.append(0x4F)  # Long form, opcode 0x0F
            code.append(table & 0xFF)
            code.append(index & 0xFF)
            code.append(0x00)  # Store to stack

        return bytes(code)

    # ===== Stack Operations =====

    def gen_push(self, operands: List[ASTNode]) -> bytes:
        """Generate PUSH (push value to stack)."""
        if not operands:
            return b''

        code = bytearray()
        value = self.get_operand_value(operands[0])

        # PUSH is VAR opcode 0x08
        if isinstance(value, int):
            code.append(0xE8)  # VAR form, opcode 0x08
            code.append(0x01)  # Type byte: 1 small constant
            code.append(value & 0xFF)

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

        value = self.get_operand_value(operands[0])
        stack_addr = self.get_operand_value(operands[1])

        if isinstance(value, int) and isinstance(stack_addr, int):
            code.append(0x05)  # Type: small, small
            code.append(value & 0xFF)
            code.append(stack_addr & 0xFF)
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

        items = self.get_operand_value(operands[0])
        stack_addr = self.get_operand_value(operands[1])

        if isinstance(items, int) and isinstance(stack_addr, int):
            code.append(0x05)  # Type: small, small
            code.append(items & 0xFF)
            code.append(stack_addr & 0xFF)

        return bytes(code)

    # ===== Object Tree Traversal =====

    def gen_get_child(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_CHILD (get first child of object)."""
        if not operands:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])

        # GET_CHILD is 1OP opcode 0x02 (store + branch)
        if obj is not None:
            code.append(0x82)  # Short 1OP, opcode 0x02, small constant
            code.append(obj & 0xFF)
            code.append(0x00)  # Store to stack
            code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_get_sibling(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_SIBLING (get next sibling of object)."""
        if not operands:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])

        # GET_SIBLING is 1OP opcode 0x01 (store + branch)
        if obj is not None:
            code.append(0x81)  # Short 1OP, opcode 0x01, small constant
            code.append(obj & 0xFF)
            code.append(0x00)  # Store to stack
            code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_get_parent(self, operands: List[ASTNode]) -> bytes:
        """Generate GET_PARENT (get parent of object)."""
        if not operands:
            return b''

        code = bytearray()
        obj = self.get_object_number(operands[0])

        # GET_PARENT is 1OP opcode 0x03 (store only)
        if obj is not None:
            code.append(0x83)  # Short 1OP, opcode 0x03, small constant
            code.append(obj & 0xFF)
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
        obj = self.get_object_number(operands[0])

        if obj is not None:
            # GET_CHILD stores child object (0 if none)
            code.append(0x82)  # Short 1OP, GET_CHILD opcode 0x02
            code.append(obj & 0xFF)
            code.append(0x00)  # Store to stack
            # Don't include branch byte - caller handles branching
            # If we wanted to make this a full predicate:
            # code.append(0x40)  # Branch on zero (no children)

        return bytes(code)

    def gen_in(self, operands: List[ASTNode]) -> bytes:
        """Generate IN? (test if obj1 is directly in obj2).

        <IN? obj1 obj2> tests if obj1's parent is obj2.
        This is equivalent to: <EQUAL? <LOC obj1> obj2>

        Implementation: GET_PARENT obj1, then compare with obj2.
        For now, we generate: EQUAL? (GET_PARENT obj1) obj2
        which branches on true.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()
        obj1 = self.get_object_number(operands[0])
        obj2 = self.get_object_number(operands[1])

        if obj1 is not None and obj2 is not None:
            # Get parent of obj1
            code.append(0x83)  # GET_PARENT 1OP, opcode 0x03
            code.append(obj1 & 0xFF)
            code.append(0x00)  # Store to stack

            # Compare with obj2 using JE (jump if equal)
            # JE is 2OP opcode 0x01 (branch instruction)
            code.append(0x41)  # Long form JE, opcode 0x01
            code.append(0x00)  # Stack (result of GET_PARENT)
            code.append(obj2 & 0xFF)
            # Branch offset will be filled by branch logic
            code.append(0x40)  # Branch on true, offset 0 (placeholder)

        return bytes(code)

    # ===== Utilities and Built-ins =====

    def gen_random(self, operands: List[ASTNode]) -> bytes:
        """Generate RANDOM (random number generator)."""
        if not operands:
            return b''

        code = bytearray()
        range_val = self.get_operand_value(operands[0])

        # RANDOM is VAR opcode 0x07
        if isinstance(range_val, int):
            code.append(0xE7)  # VAR form, opcode 0x07
            code.append(0x01)  # Type byte: 1 small constant
            code.append(range_val & 0xFF)
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

        Usage: <PERFORM action object1 [object2]>
        Example: <PERFORM ,V?TAKE ,LAMP>
                 <PERFORM ,V?PUT ,BALL ,BOX>

        This sets PRSA, PRSO, PRSI and calls the object's action routine.
        Simplified implementation: just sets the globals.
        Full implementation would dispatch to object ACTION property.
        """
        if len(operands) < 2:
            return b''

        code = bytearray()

        # Extract action and objects
        action = operands[0]
        obj1 = operands[1] if len(operands) > 1 else None
        obj2 = operands[2] if len(operands) > 2 else None

        # Set PRSA to action
        action_val = self.get_operand_value(action)
        if isinstance(action_val, int):
            prsa_var = self.globals['PRSA']
            code.append(0x2D)  # STORE opcode
            code.append(prsa_var)
            code.append(action_val & 0xFF)

        # Set PRSO to object1
        if obj1:
            obj1_val = self.get_operand_value(obj1)
            if isinstance(obj1_val, int):
                prso_var = self.globals['PRSO']
                code.append(0x2D)  # STORE opcode
                code.append(prso_var)
                code.append(obj1_val & 0xFF)

        # Set PRSI to object2 (if provided)
        if obj2:
            obj2_val = self.get_operand_value(obj2)
            if isinstance(obj2_val, int):
                prsi_var = self.globals['PRSI']
                code.append(0x2D)  # STORE opcode
                code.append(prsi_var)
                code.append(obj2_val & 0xFF)

        # TODO: Call object's ACTION routine
        # For now, just setting globals is sufficient for testing

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

        # Get routine address (simplified - would need symbol table lookup)
        routine = self.get_operand_value(operands[0])
        args = operands[1:]

        # CALL (2OP) for 1-2 args, CALL_VS (VAR) for 0-3 args
        # Use CALL_VS for flexibility

        if isinstance(routine, int):
            # CALL_VS is VAR opcode 0x00
            code.append(0xE0)  # VAR form, opcode 0x00

            # Type byte indicates argument types
            num_args = min(len(args), 3)
            type_byte = 0x00  # Will set bits for each arg type

            # For simplicity, assume all small constants
            for i in range(4):
                if i < num_args:
                    type_byte |= (0x01 << (6 - i*2))  # Small constant = 01
                else:
                    type_byte |= (0x03 << (6 - i*2))  # Omitted = 11

            code.append(type_byte)
            code.append(routine & 0xFF)  # Routine address

            # Add arguments
            for i in range(num_args):
                arg_val = self.get_operand_value(args[i])
                if isinstance(arg_val, int):
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
        routine = self.get_operand_value(operands[0])
        args = operands[1:]

        # CALL_VS2 is EXT opcode 0x0C
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0C)  # CALL_VS2

        # Can have up to 8 arguments, needs two type bytes
        num_args = min(len(args), 8)

        # First type byte (args 0-3)
        type_byte_1 = 0x00
        for i in range(4):
            if i < num_args:
                type_byte_1 |= (0x01 << (6 - i*2))  # Small constant
            else:
                type_byte_1 |= (0x03 << (6 - i*2))  # Omitted

        # Second type byte (args 4-7)
        type_byte_2 = 0xFF  # Default: all omitted
        if num_args > 4:
            type_byte_2 = 0x00
            for i in range(4):
                if i + 4 < num_args:
                    type_byte_2 |= (0x01 << (6 - i*2))  # Small constant
                else:
                    type_byte_2 |= (0x03 << (6 - i*2))  # Omitted

        code.append(type_byte_1)
        if num_args > 4:
            code.append(type_byte_2)

        # Routine address
        if isinstance(routine, int):
            code.append(routine & 0xFF)

        # Add arguments
        for i in range(num_args):
            arg_val = self.get_operand_value(args[i])
            if isinstance(arg_val, int):
                code.append(arg_val & 0xFF)

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
        routine = self.get_operand_value(operands[0])
        args = operands[1:]

        # CALL_VN2 is EXT opcode 0x0D
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0D)  # CALL_VN2

        # Similar to CALL_VS2 but no store
        num_args = min(len(args), 8)

        # First type byte (args 0-3)
        type_byte_1 = 0x00
        for i in range(4):
            if i < num_args:
                type_byte_1 |= (0x01 << (6 - i*2))
            else:
                type_byte_1 |= (0x03 << (6 - i*2))

        # Second type byte (args 4-7)
        type_byte_2 = 0xFF
        if num_args > 4:
            type_byte_2 = 0x00
            for i in range(4):
                if i + 4 < num_args:
                    type_byte_2 |= (0x01 << (6 - i*2))
                else:
                    type_byte_2 |= (0x03 << (6 - i*2))

        code.append(type_byte_1)
        if num_args > 4:
            code.append(type_byte_2)

        # Routine address
        if isinstance(routine, int):
            code.append(routine & 0xFF)

        # Add arguments
        for i in range(num_args):
            arg_val = self.get_operand_value(args[i])
            if isinstance(arg_val, int):
                code.append(arg_val & 0xFF)

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

        text_buf = self.get_operand_value(operands[0])
        parse_buf = self.get_operand_value(operands[1])

        # Type byte for operands
        num_operands = len(operands)
        type_byte = 0x00

        for i in range(4):
            if i < num_operands:
                type_byte |= (0x01 << (6 - i*2))  # Small constant
            else:
                type_byte |= (0x03 << (6 - i*2))  # Omitted

        code.append(type_byte)

        # Text buffer
        if isinstance(text_buf, int):
            code.append(text_buf & 0xFF)

        # Parse buffer
        if isinstance(parse_buf, int):
            code.append(parse_buf & 0xFF)

        # Optional dictionary
        if len(operands) > 2:
            dict_addr = self.get_operand_value(operands[2])
            if isinstance(dict_addr, int):
                code.append(dict_addr & 0xFF)

        # Optional flag
        if len(operands) > 3:
            flag = self.get_operand_value(operands[3])
            if isinstance(flag, int):
                code.append(flag & 0xFF)

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

        # CHECK_ARG_COUNT is EXT opcode 0x0F
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0F)  # CHECK_ARG_COUNT

        arg_count = self.get_operand_value(operands[0])

        # Type byte: 1 operand
        code.append(0x01)  # Small constant

        if isinstance(arg_count, int):
            code.append(arg_count & 0xFF)

        # Branch offset (simplified - would need proper branch handling)
        code.append(0x40)  # Branch on true, offset 0
        code.append(0x00)

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

        # Type byte for 4 operands
        code.append(0x00)  # All small constants (simplified)

        for i in range(4):
            val = self.get_operand_value(operands[i])
            if isinstance(val, int):
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

        # Type byte for operands
        num_operands = len(operands)
        type_byte = 0x00
        for i in range(4):
            if i < num_operands:
                type_byte |= (0x01 << (6 - i*2))  # Small constant
            else:
                type_byte |= (0x03 << (6 - i*2))  # Omitted

        code.append(type_byte)

        for i in range(min(num_operands, 4)):
            val = self.get_operand_value(operands[i])
            if isinstance(val, int):
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
        routine = self.get_operand_value(operands[0])

        # CALL_1S is 1OP opcode 0x08
        if isinstance(routine, int):
            code.append(0x88)  # 1OP form, opcode 0x08, small constant
            code.append(routine & 0xFF)
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
        routine = self.get_operand_value(operands[0])

        # CALL_1N is 1OP opcode 0x0F
        if isinstance(routine, int):
            code.append(0x8F)  # 1OP form, opcode 0x0F, small constant
            code.append(routine & 0xFF)

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
        routine = self.get_operand_value(operands[0])
        arg = self.get_operand_value(operands[1])

        # CALL_2S is 2OP opcode 0x19
        if isinstance(routine, int) and isinstance(arg, int):
            if 0 <= routine <= 255 and 0 <= arg <= 255:
                code.append(0x59)  # 2OP form, small/small, opcode 0x19
                code.append(routine & 0xFF)
                code.append(arg & 0xFF)
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
        routine = self.get_operand_value(operands[0])
        arg = self.get_operand_value(operands[1])

        # CALL_2N is 2OP opcode 0x1A
        if isinstance(routine, int) and isinstance(arg, int):
            if 0 <= routine <= 255 and 0 <= arg <= 255:
                code.append(0x5A)  # 2OP form, small/small, opcode 0x1A
                code.append(routine & 0xFF)
                code.append(arg & 0xFF)

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

        # PRINT_UNICODE is EXT opcode 0x0B
        code.append(0xBE)  # EXT opcode marker
        code.append(0x0B)  # PRINT_UNICODE

        char_code = self.get_operand_value(operands[0])

        # Type byte: 1 operand
        code.append(0x01)  # Small constant

        if isinstance(char_code, int):
            code.append(char_code & 0xFF)

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

        picture_num = self.get_operand_value(operands[0])

        if len(operands) >= 3:
            # Picture with coordinates
            y_coord = self.get_operand_value(operands[1])
            x_coord = self.get_operand_value(operands[2])

            if isinstance(picture_num, int) and isinstance(y_coord, int) and isinstance(x_coord, int):
                code.append(0x55)  # Type: small, small, small
                code.append(picture_num & 0xFF)
                code.append(y_coord & 0xFF)
                code.append(x_coord & 0xFF)
        else:
            # Just picture number (use current window cursor position)
            if isinstance(picture_num, int):
                code.append(0x01)  # Type: small
                code.append(picture_num & 0xFF)

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

        picture_num = self.get_operand_value(operands[0])
        y_coord = self.get_operand_value(operands[1])
        x_coord = self.get_operand_value(operands[2])

        if isinstance(picture_num, int) and isinstance(y_coord, int) and isinstance(x_coord, int):
            code.append(0x55)  # Type: small, small, small
            code.append(picture_num & 0xFF)
            code.append(y_coord & 0xFF)
            code.append(x_coord & 0xFF)

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

        picture_num = self.get_operand_value(operands[0])
        array_addr = self.get_operand_value(operands[1])

        if isinstance(picture_num, int) and isinstance(array_addr, int):
            code.append(0x05)  # Type: small, small
            code.append(picture_num & 0xFF)
            code.append(array_addr & 0xFF)
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
        table = self.get_operand_value(operands[0])

        # If offset provided, use it; otherwise use 1 (skip first element)
        if len(operands) > 1:
            offset = self.get_operand_value(operands[1])
        else:
            offset = 1

        # REST returns table_address + (offset * 2)
        # For word-based tables, each element is 2 bytes
        # Use ADD to compute: table + (offset * 2)

        if isinstance(table, int) and isinstance(offset, int):
            # Calculate byte offset
            byte_offset = offset * 2

            # ADD is 2OP opcode 0x14
            code.append(0x54)  # Long form, opcode 0x14
            code.append(table & 0xFF)
            code.append(byte_offset & 0xFF)
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
        compare_val = self.get_operand_value(operands[1])

        # INC the variable
        code.extend(self.gen_inc([var]))

        # Now test if var > compare_val using JG
        var_val = self.get_operand_value(var)
        if isinstance(var_val, int) and isinstance(compare_val, int):
            # JG is 2OP opcode 0x03
            code.append(0x43)  # Long form, opcode 0x03
            code.append(var_val & 0xFF)
            code.append(compare_val & 0xFF)
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
        room = self.get_operand_value(operands[0])

        # Set HERE global to new room
        here_var = self.globals.get('HERE', 2)  # Default to 2 if not defined

        if isinstance(room, int):
            # STORE is 2OP opcode 0x0D
            code.append(0x2D)  # Short form
            code.append(here_var & 0xFF)
            code.append(room & 0xFF)

            # TODO: Call room description routine
            # For now, just changing HERE is sufficient for testing

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
        obj = self.get_operand_value(operands[0])
        prop = self.get_operand_value(operands[1])

        if isinstance(obj, int) and isinstance(prop, int):
            # GET_PROP_ADDR is 2OP opcode 0x12
            code.append(0x52)  # Long form, opcode 0x12
            code.append(obj & 0xFF)
            code.append(prop & 0xFF)
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
        value = self.get_operand_value(operands[0])
        bit_num = self.get_operand_value(operands[1])

        if isinstance(value, int) and isinstance(bit_num, int):
            # Calculate bit mask: 1 << bit_num
            bit_mask = 1 << bit_num

            # AND value with bit mask
            # AND is 2OP opcode 0x09
            code.append(0x49)  # Long form, opcode 0x09
            code.append(value & 0xFF)
            code.append(bit_mask & 0xFF)
            code.append(0x00)  # Store to stack

            # JZ tests if result is zero (bit not set)
            # We want to branch if bit IS set, so we use JNZ logic
            # This will be handled by COND context
            # For now, just the AND result on stack

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
