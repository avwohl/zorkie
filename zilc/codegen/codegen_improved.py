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

        # Code generation
        self.code = bytearray()
        self.next_global = 0x10
        self.next_object = 1

        # Labels for branching
        self.labels: Dict[str, int] = {}
        self.label_counter = 0

        # Built-in constants
        self.constants['T'] = 1
        self.constants['<>'] = 0
        self.constants['FALSE'] = 0
        self.constants['TRUE'] = 1

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
        elif op_name == 'RETURN':
            return self.gen_return(form.operands)
        elif op_name == 'QUIT':
            return self.gen_quit()

        # Output
        elif op_name == 'TELL':
            return self.gen_tell(form.operands)
        elif op_name == 'PRINT':
            return self.gen_tell(form.operands)
        elif op_name == 'CRLF':
            return self.gen_newline()
        elif op_name == 'PRINTN' or op_name == 'PRINT-NUM':
            return self.gen_print_num(form.operands)
        elif op_name == 'PRINTC' or op_name == 'PRINT-CHAR':
            return self.gen_print_char(form.operands)

        # Variables
        elif op_name == 'SET':
            return self.gen_set(form.operands, is_global=False)
        elif op_name == 'SETG':
            return self.gen_set(form.operands, is_global=True)
        elif op_name == 'INC':
            return self.gen_inc(form.operands)
        elif op_name == 'DEC':
            return self.gen_dec(form.operands)

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

        # Comparison
        elif op_name in ('=', 'EQUAL?', '==?'):
            return self.gen_equal(form.operands)
        elif op_name in ('L?', '<'):
            return self.gen_less(form.operands)
        elif op_name in ('G?', '>'):
            return self.gen_greater(form.operands)

        # Logical
        elif op_name == 'AND':
            return self.gen_and(form.operands)
        elif op_name == 'OR':
            return self.gen_or(form.operands)
        elif op_name == 'NOT':
            return self.gen_not(form.operands)

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

        # Random and utilities
        elif op_name == 'RANDOM':
            return self.gen_random(form.operands)
        elif op_name == 'RESTART':
            return self.gen_restart()
        elif op_name == 'SAVE':
            return self.gen_save()
        elif op_name == 'RESTORE':
            return self.gen_restore()
        elif op_name == 'VERIFY':
            return self.gen_verify()

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
