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

        # Logical
        elif op_name == 'AND':
            return self.gen_and(form.operands)
        elif op_name == 'OR':
            return self.gen_or(form.operands)
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
                return self.gen_call(form.operator.value, form.operands)

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

    def gen_hlight(self, operands: List[ASTNode]) -> bytes:
        """Generate HLIGHT (set text style/highlighting).

        <HLIGHT style> sets text style (bold, italic, reverse, etc).
        In V3+, this is the SET_TEXT_STYLE opcode (VAR opcode 0x11).

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

    def gen_input(self, operands: List[ASTNode]) -> bytes:
        """Generate INPUT (read text input).

        <INPUT buffer parse> reads a line of text from the player.
        In V3, this is the SREAD opcode (VAR opcode 0x01).

        Args:
            operands[0]: Text buffer address
            operands[1]: Parse buffer address (optional)

        Returns:
            bytes: Z-machine code
        """
        if not operands:
            return b''

        code = bytearray()
        text_buf = self.get_operand_value(operands[0])

        if isinstance(text_buf, int):
            code.append(0xE1)  # SREAD/READ (VAR opcode 0x01)

            if len(operands) >= 2:
                parse_buf = self.get_operand_value(operands[1])
                if isinstance(parse_buf, int):
                    code.append(0x15)  # Type byte: 2 small constants
                    code.append(text_buf & 0xFF)
                    code.append(parse_buf & 0xFF)
            else:
                code.append(0x2F)  # Type byte: 1 small constant
                code.append(text_buf & 0xFF)

        return bytes(code)

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
            bytes: Z-machine code (stub for V3)
        """
        # SET_COLOUR is V5+, V3 doesn't support it
        return b''

    def gen_font(self, operands: List[ASTNode]) -> bytes:
        """Generate FONT (set font).

        <FONT font-number> sets the current font.
        In V5+, uses SET_FONT. For V3, this is a stub.

        Args:
            operands[0]: Font number

        Returns:
            bytes: Z-machine code (stub for V3)
        """
        # SET_FONT is V5+
        return b''

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

    def gen_set_margins(self, operands: List[ASTNode]) -> bytes:
        """Generate SET-MARGINS (set text margins).

        <SET-MARGINS left right> sets margins in characters.

        Returns:
            bytes: Z-machine code (stub)
        """
        return b''

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

    def gen_call(self, routine_name: str, operands: List[ASTNode]) -> bytes:
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
        """Generate SAVE (save game) - branch instruction in V1-4."""
        code = bytearray()
        code.append(0xB5)  # Short 0OP, opcode 0x05

        if self.version <= 4:
            # Branch instruction in V1-4
            code.append(0x40)  # Branch byte

        return bytes(code)

    def gen_restore(self) -> bytes:
        """Generate RESTORE (restore game) - branch instruction in V1-4."""
        code = bytearray()
        code.append(0xB6)  # Short 0OP, opcode 0x06

        if self.version <= 4:
            # Branch instruction in V1-4
            code.append(0x40)  # Branch byte

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
