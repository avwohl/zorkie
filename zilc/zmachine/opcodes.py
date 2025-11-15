"""
Z-machine opcode definitions and encoding.

Defines all Z-machine opcodes and their encoding formats.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional


class OpcodeForm(Enum):
    """Opcode form types."""
    LONG = auto()     # 2OP long form
    SHORT = auto()    # 0OP or 1OP short form
    VARIABLE = auto() # 2OP or VAR variable form
    EXTENDED = auto() # EXT extended form (V5+)


class OperandType(Enum):
    """Operand types."""
    LARGE_CONST = 0   # 00: Large constant (16-bit)
    SMALL_CONST = 1   # 01: Small constant (8-bit)
    VARIABLE = 2      # 10: Variable
    OMITTED = 3       # 11: Omitted


@dataclass
class Opcode:
    """Represents a Z-machine opcode."""
    name: str
    number: int
    form: OpcodeForm
    operand_count: str  # "0OP", "1OP", "2OP", "VAR"
    is_store: bool = False  # Result stored to variable
    is_branch: bool = False  # Conditional branch
    is_text: bool = False  # Prints text
    min_version: int = 1
    max_version: int = 8

    def __repr__(self):
        return f"Opcode({self.name}, {self.form.name}, {self.operand_count})"


class OpcodeTable:
    """Z-machine opcode table."""

    # Essential opcodes for basic functionality
    OPCODES = {
        # 2OP opcodes (long form)
        'je': Opcode('je', 0x01, OpcodeForm.LONG, '2OP', is_branch=True),
        'jl': Opcode('jl', 0x02, OpcodeForm.LONG, '2OP', is_branch=True),
        'jg': Opcode('jg', 0x03, OpcodeForm.LONG, '2OP', is_branch=True),
        'inc_chk': Opcode('inc_chk', 0x05, OpcodeForm.LONG, '2OP', is_branch=True),
        'test': Opcode('test', 0x07, OpcodeForm.LONG, '2OP', is_branch=True),
        'or': Opcode('or', 0x08, OpcodeForm.LONG, '2OP', is_store=True),
        'and': Opcode('and', 0x09, OpcodeForm.LONG, '2OP', is_store=True),
        'test_attr': Opcode('test_attr', 0x0A, OpcodeForm.LONG, '2OP', is_branch=True),
        'set_attr': Opcode('set_attr', 0x0B, OpcodeForm.LONG, '2OP'),
        'clear_attr': Opcode('clear_attr', 0x0C, OpcodeForm.LONG, '2OP'),
        'store': Opcode('store', 0x0D, OpcodeForm.LONG, '2OP'),
        'insert_obj': Opcode('insert_obj', 0x0E, OpcodeForm.LONG, '2OP'),
        'loadw': Opcode('loadw', 0x0F, OpcodeForm.LONG, '2OP', is_store=True),
        'loadb': Opcode('loadb', 0x10, OpcodeForm.LONG, '2OP', is_store=True),
        'get_prop': Opcode('get_prop', 0x11, OpcodeForm.LONG, '2OP', is_store=True),
        'get_prop_addr': Opcode('get_prop_addr', 0x12, OpcodeForm.LONG, '2OP', is_store=True),
        'get_next_prop': Opcode('get_next_prop', 0x13, OpcodeForm.LONG, '2OP', is_store=True),
        'add': Opcode('add', 0x14, OpcodeForm.LONG, '2OP', is_store=True),
        'sub': Opcode('sub', 0x15, OpcodeForm.LONG, '2OP', is_store=True),
        'mul': Opcode('mul', 0x16, OpcodeForm.LONG, '2OP', is_store=True),
        'div': Opcode('div', 0x17, OpcodeForm.LONG, '2OP', is_store=True),
        'mod': Opcode('mod', 0x18, OpcodeForm.LONG, '2OP', is_store=True),

        # 1OP opcodes (short form)
        'jz': Opcode('jz', 0x00, OpcodeForm.SHORT, '1OP', is_branch=True),
        'get_sibling': Opcode('get_sibling', 0x01, OpcodeForm.SHORT, '1OP', is_store=True, is_branch=True),
        'get_child': Opcode('get_child', 0x02, OpcodeForm.SHORT, '1OP', is_store=True, is_branch=True),
        'get_parent': Opcode('get_parent', 0x03, OpcodeForm.SHORT, '1OP', is_store=True),
        'get_prop_len': Opcode('get_prop_len', 0x04, OpcodeForm.SHORT, '1OP', is_store=True),
        'inc': Opcode('inc', 0x05, OpcodeForm.SHORT, '1OP'),
        'dec': Opcode('dec', 0x06, OpcodeForm.SHORT, '1OP'),
        'print_addr': Opcode('print_addr', 0x07, OpcodeForm.SHORT, '1OP', is_text=True),
        'remove_obj': Opcode('remove_obj', 0x09, OpcodeForm.SHORT, '1OP'),
        'print_obj': Opcode('print_obj', 0x0A, OpcodeForm.SHORT, '1OP', is_text=True),
        'ret': Opcode('ret', 0x0B, OpcodeForm.SHORT, '1OP'),
        'jump': Opcode('jump', 0x0C, OpcodeForm.SHORT, '1OP'),
        'print_paddr': Opcode('print_paddr', 0x0D, OpcodeForm.SHORT, '1OP', is_text=True),
        'load': Opcode('load', 0x0E, OpcodeForm.SHORT, '1OP', is_store=True),
        'not': Opcode('not', 0x0F, OpcodeForm.SHORT, '1OP', is_store=True),  # V1-4
        'call_1s': Opcode('call_1s', 0x0F, OpcodeForm.SHORT, '1OP', is_store=True, min_version=5),  # V5+

        # 0OP opcodes (short form)
        'rtrue': Opcode('rtrue', 0x00, OpcodeForm.SHORT, '0OP'),
        'rfalse': Opcode('rfalse', 0x01, OpcodeForm.SHORT, '0OP'),
        'print': Opcode('print', 0x02, OpcodeForm.SHORT, '0OP', is_text=True),
        'print_ret': Opcode('print_ret', 0x03, OpcodeForm.SHORT, '0OP', is_text=True),
        'nop': Opcode('nop', 0x04, OpcodeForm.SHORT, '0OP'),
        'save': Opcode('save', 0x05, OpcodeForm.SHORT, '0OP', is_branch=True, max_version=4),
        'restore': Opcode('restore', 0x06, OpcodeForm.SHORT, '0OP', is_branch=True, max_version=4),
        'restart': Opcode('restart', 0x07, OpcodeForm.SHORT, '0OP'),
        'ret_popped': Opcode('ret_popped', 0x08, OpcodeForm.SHORT, '0OP'),
        'pop': Opcode('pop', 0x09, OpcodeForm.SHORT, '0OP', max_version=4),
        'catch': Opcode('catch', 0x09, OpcodeForm.SHORT, '0OP', is_store=True, min_version=5),
        'quit': Opcode('quit', 0x0A, OpcodeForm.SHORT, '0OP'),
        'new_line': Opcode('new_line', 0x0B, OpcodeForm.SHORT, '0OP'),
        'verify': Opcode('verify', 0x0D, OpcodeForm.SHORT, '0OP', is_branch=True),

        # VAR opcodes (variable form)
        'call': Opcode('call', 0x00, OpcodeForm.VARIABLE, 'VAR', is_store=True, max_version=4),
        'call_vs': Opcode('call_vs', 0x00, OpcodeForm.VARIABLE, 'VAR', is_store=True, min_version=4),
        'storew': Opcode('storew', 0x01, OpcodeForm.VARIABLE, 'VAR'),
        'storeb': Opcode('storeb', 0x02, OpcodeForm.VARIABLE, 'VAR'),
        'put_prop': Opcode('put_prop', 0x03, OpcodeForm.VARIABLE, 'VAR'),
        'read': Opcode('read', 0x04, OpcodeForm.VARIABLE, 'VAR'),  # V1-4
        'sread': Opcode('sread', 0x04, OpcodeForm.VARIABLE, 'VAR', is_store=True, min_version=5),  # V5+
        'print_char': Opcode('print_char', 0x05, OpcodeForm.VARIABLE, 'VAR', is_text=True),
        'print_num': Opcode('print_num', 0x06, OpcodeForm.VARIABLE, 'VAR', is_text=True),
        'random': Opcode('random', 0x07, OpcodeForm.VARIABLE, 'VAR', is_store=True),
        'push': Opcode('push', 0x08, OpcodeForm.VARIABLE, 'VAR'),
        'pull': Opcode('pull', 0x09, OpcodeForm.VARIABLE, 'VAR'),  # V1-5
        'split_window': Opcode('split_window', 0x0A, OpcodeForm.VARIABLE, 'VAR', min_version=3),
        'set_window': Opcode('set_window', 0x0B, OpcodeForm.VARIABLE, 'VAR', min_version=3),
        'call_vs2': Opcode('call_vs2', 0x0C, OpcodeForm.VARIABLE, 'VAR', is_store=True, min_version=4),
        'erase_window': Opcode('erase_window', 0x0D, OpcodeForm.VARIABLE, 'VAR', min_version=4),
        'set_cursor': Opcode('set_cursor', 0x11, OpcodeForm.VARIABLE, 'VAR', min_version=4),
        'get_cursor': Opcode('get_cursor', 0x12, OpcodeForm.VARIABLE, 'VAR', min_version=4),
        'set_text_style': Opcode('set_text_style', 0x13, OpcodeForm.VARIABLE, 'VAR', min_version=4),
        'output_stream': Opcode('output_stream', 0x13, OpcodeForm.VARIABLE, 'VAR'),
        'input_stream': Opcode('input_stream', 0x14, OpcodeForm.VARIABLE, 'VAR', min_version=3),
        'sound_effect': Opcode('sound_effect', 0x15, OpcodeForm.VARIABLE, 'VAR', min_version=3),
    }

    @classmethod
    def get_opcode(cls, name: str) -> Optional[Opcode]:
        """Get opcode by name."""
        return cls.OPCODES.get(name.lower())

    @classmethod
    def encode_opcode_byte(cls, opcode: Opcode, operand_types: List[OperandType]) -> bytes:
        """
        Encode opcode byte(s) based on form and operand types.

        This is a simplified encoder - a full implementation would be more complex.
        """
        result = bytearray()

        if opcode.form == OpcodeForm.LONG:
            # Long form: bits 7-6 = operand count bits, bit 6 = first op type, bit 5 = second op type
            byte = opcode.number & 0x1F  # Opcode in bottom 5 bits

            # Set operand types
            if len(operand_types) >= 2:
                if operand_types[0] == OperandType.VARIABLE:
                    byte |= 0x40
                if operand_types[1] == OperandType.VARIABLE:
                    byte |= 0x20

            result.append(byte)

        elif opcode.form == OpcodeForm.SHORT:
            # Short form: bits 7-6 = 10 (short), bits 5-4 = operand type, bits 3-0 = opcode
            if opcode.operand_count == '0OP':
                byte = 0xB0 | (opcode.number & 0x0F)
            else:  # 1OP
                op_type = operand_types[0] if operand_types else OperandType.OMITTED
                type_bits = {
                    OperandType.LARGE_CONST: 0x00,
                    OperandType.SMALL_CONST: 0x01,
                    OperandType.VARIABLE: 0x02,
                    OperandType.OMITTED: 0x03
                }[op_type]

                byte = 0x80 | (type_bits << 4) | (opcode.number & 0x0F)

            result.append(byte)

        elif opcode.form == OpcodeForm.VARIABLE:
            # Variable form: bits 7-6 = 11 (variable), bit 5 = VAR/2OP, bits 4-0 = opcode
            byte = 0xC0 | (opcode.number & 0x1F)

            if opcode.operand_count == 'VAR':
                byte |= 0x20

            result.append(byte)

        return bytes(result)


def encode_operand(value: int, op_type: OperandType) -> bytes:
    """Encode an operand value based on its type."""
    if op_type == OperandType.LARGE_CONST:
        # 16-bit value (big-endian)
        return bytes([(value >> 8) & 0xFF, value & 0xFF])
    elif op_type == OperandType.SMALL_CONST:
        # 8-bit value
        return bytes([value & 0xFF])
    elif op_type == OperandType.VARIABLE:
        # Variable number (8-bit)
        return bytes([value & 0xFF])
    else:  # OMITTED
        return b''
