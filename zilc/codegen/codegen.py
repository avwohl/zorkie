"""
Code generator - converts ZIL AST to Z-machine bytecode.

This is a simplified code generator that handles basic ZIL constructs.
A full implementation would need to handle all ZIL features.
"""

from typing import List, Dict, Any, Optional
import struct

from ..parser.ast_nodes import *
from ..zmachine.opcodes import OpcodeTable, OperandType, encode_operand
from ..zmachine.text_encoding import ZTextEncoder, words_to_bytes


class CodeGenerator:
    """Generates Z-machine bytecode from ZIL AST."""

    def __init__(self, version: int = 3):
        self.version = version
        self.encoder = ZTextEncoder(version)
        self.opcodes = OpcodeTable()

        # Symbol tables
        self.globals: Dict[str, int] = {}  # Global name -> variable number
        self.constants: Dict[str, int] = {}  # Constant name -> value
        self.routines: Dict[str, int] = {}  # Routine name -> address (filled during assembly)
        self.locals: Dict[str, int] = {}  # Local name -> variable number (per routine)

        # Output
        self.code = bytearray()
        self.next_global = 0x10  # Globals start at variable $10

    def generate(self, program: Program) -> bytes:
        """Generate bytecode from program AST."""
        # Process globals
        for global_node in program.globals:
            self.globals[global_node.name] = self.next_global
            self.next_global += 1

        # Process constants
        for const_node in program.constants:
            if isinstance(const_node.value, NumberNode):
                self.constants[const_node.name] = const_node.value.value
            elif isinstance(const_node.value, AtomNode):
                # Handle atom constants (like T, <>)
                if const_node.value.value == 'T':
                    self.constants[const_node.name] = 1
                elif const_node.value.value == '<>':
                    self.constants[const_node.name] = 0

        # Process routines
        for routine_node in program.routines:
            self.generate_routine(routine_node)

        return bytes(self.code)

    def generate_routine(self, routine: RoutineNode) -> bytes:
        """Generate bytecode for a routine."""
        routine_code = bytearray()

        # Routine header
        num_locals = len(routine.params) + len(routine.aux_vars)
        routine_code.append(num_locals & 0x0F)

        # Local variable initial values (V1-4 only)
        if self.version <= 4:
            for i in range(num_locals):
                routine_code.extend(struct.pack('>H', 0))

        # Build local variable table
        self.locals = {}
        var_num = 1  # Locals start at 1 ($01-$0F)
        for param in routine.params:
            self.locals[param] = var_num
            var_num += 1
        for aux_var in routine.aux_vars:
            self.locals[aux_var] = var_num
            var_num += 1

        # Generate code for routine body
        for stmt in routine.body:
            stmt_code = self.generate_statement(stmt)
            routine_code.extend(stmt_code)

        # Append to main code
        self.code.extend(routine_code)
        return bytes(routine_code)

    def generate_statement(self, node: ASTNode) -> bytes:
        """Generate code for a statement."""
        if isinstance(node, FormNode):
            return self.generate_form(node)
        elif isinstance(node, AtomNode):
            # Standalone atom (like T, <>) - no code needed
            return b''
        elif isinstance(node, NumberNode):
            # Standalone number - no code needed
            return b''
        else:
            # Other node types
            return b''

    def generate_form(self, form: FormNode) -> bytes:
        """Generate code for a form (function call)."""
        if not isinstance(form.operator, AtomNode):
            return b''

        op_name = form.operator.value.upper()

        # Handle special forms
        if op_name == 'RTRUE':
            return self.generate_rtrue()
        elif op_name == 'RFALSE':
            return self.generate_rfalse()
        elif op_name == 'QUIT':
            return self.generate_quit()
        elif op_name == 'TELL':
            return self.generate_tell(form.operands)
        elif op_name == 'CRLF':
            return self.generate_newline()
        elif op_name == 'SET' or op_name == 'SETG':
            return self.generate_set(form.operands, is_global=(op_name == 'SETG'))
        elif op_name == 'COND':
            if isinstance(form.operands[0], CondNode):
                return self.generate_cond(form.operands[0])
        elif op_name == '+' or op_name == 'ADD':
            return self.generate_add(form.operands)
        elif op_name == '-' or op_name == 'SUB':
            return self.generate_sub(form.operands)
        elif op_name == 'PRINT':
            return self.generate_tell(form.operands)

        return b''

    def generate_rtrue(self) -> bytes:
        """Generate RTRUE instruction."""
        # RTRUE is 0OP opcode 0x00, encoded as 0xB0
        return bytes([0xB0])

    def generate_rfalse(self) -> bytes:
        """Generate RFALSE instruction."""
        # RFALSE is 0OP opcode 0x01, encoded as 0xB1
        return bytes([0xB1])

    def generate_quit(self) -> bytes:
        """Generate QUIT instruction."""
        # QUIT is 0OP opcode 0x0A, encoded as 0xBA
        return bytes([0xBA])

    def generate_newline(self) -> bytes:
        """Generate NEW_LINE instruction."""
        # NEW_LINE is 0OP opcode 0x0B, encoded as 0xBB
        return bytes([0xBB])

    def generate_tell(self, operands: List[ASTNode]) -> bytes:
        """Generate PRINT instruction with inline text."""
        code = bytearray()

        # PRINT is 0OP opcode 0x02, encoded as 0xB2
        code.append(0xB2)

        # Concatenate all string operands
        text_parts = []
        for op in operands:
            if isinstance(op, StringNode):
                text_parts.append(op.value)
            elif isinstance(op, AtomNode) and op.value == 'CR':
                text_parts.append('\n')

        text = ''.join(text_parts)

        # Encode text
        encoded_words = self.encoder.encode_string(text)
        code.extend(words_to_bytes(encoded_words))

        return bytes(code)

    def generate_set(self, operands: List[ASTNode], is_global: bool = False) -> bytes:
        """Generate SET/SETG (variable assignment)."""
        if len(operands) < 2:
            return b''

        var_node = operands[0]
        value_node = operands[1]

        # Get variable number
        if isinstance(var_node, AtomNode):
            if is_global:
                var_num = self.globals.get(var_node.value, self.next_global)
            else:
                var_num = self.locals.get(var_node.value, 1)
        else:
            return b''

        # STORE instruction: opcode 0x0D (2OP)
        code = bytearray()

        # For now, only handle constant values
        if isinstance(value_node, NumberNode):
            # STORE variable small_constant
            code.append(0x2D)  # Long form, small/small
            code.append(var_num)
            code.append(value_node.value & 0xFF)

        return bytes(code)

    def generate_add(self, operands: List[ASTNode]) -> bytes:
        """Generate ADD instruction."""
        if len(operands) < 2:
            return b''

        # Simplified: ADD two numbers, store to stack
        code = bytearray()
        code.append(0x54)  # ADD opcode (long form)

        # Operands (simplified - assume numbers)
        if isinstance(operands[0], NumberNode):
            code.append(operands[0].value & 0xFF)
        else:
            code.append(0)

        if isinstance(operands[1], NumberNode):
            code.append(operands[1].value & 0xFF)
        else:
            code.append(0)

        # Store to stack (variable 0)
        code.append(0x00)

        return bytes(code)

    def generate_sub(self, operands: List[ASTNode]) -> bytes:
        """Generate SUB instruction."""
        if len(operands) < 2:
            return b''

        code = bytearray()
        code.append(0x55)  # SUB opcode (long form)

        # Operands (simplified)
        if isinstance(operands[0], NumberNode):
            code.append(operands[0].value & 0xFF)
        else:
            code.append(0)

        if isinstance(operands[1], NumberNode):
            code.append(operands[1].value & 0xFF)
        else:
            code.append(0)

        # Store to stack
        code.append(0x00)

        return bytes(code)

    def generate_cond(self, cond: CondNode) -> bytes:
        """Generate COND statement (simplified)."""
        code = bytearray()

        # This is a simplified implementation
        # A full implementation would need proper branching logic

        for condition, actions in cond.clauses:
            # Generate code for actions
            for action in actions:
                code.extend(self.generate_statement(action))

        return bytes(code)
