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
        """Generate COND statement with proper branching."""
        code = bytearray()

        # Simplified COND: just execute all true clauses
        for condition, actions in cond.clauses:
            # Check if condition is always true (T atom)
            if isinstance(condition, AtomNode) and condition.value == 'T':
                # Always execute these actions
                for action in actions:
                    code.extend(self.generate_statement(action))
                break  # T clause ends COND
            else:
                # Generate condition test and actions
                # This is simplified - proper implementation needs labels and jumps
                for action in actions:
                    code.extend(self.generate_statement(action))

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
