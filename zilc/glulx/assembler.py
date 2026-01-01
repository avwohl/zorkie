"""
Glulx assembler - assembles bytecode and builds Glulx story file.

Glulx is a 32-bit virtual machine specification for text adventures,
designed as a more capable successor to the Z-machine.

Key differences from Z-machine:
- 32-bit addressing (4GB address space)
- Native Unicode support
- No artificial limits on objects, attributes, etc.
- Different opcode encoding
"""

import struct
from typing import List, Dict, Optional, Tuple


class GlulxAssembler:
    """Assembles Glulx bytecode into a story file."""

    # Magic number for Glulx files
    MAGIC = b'Glul'

    # Glulx version (3.1.2 = 0x00030102)
    GLULX_VERSION = 0x00030102

    # Default stack size (64KB)
    DEFAULT_STACK_SIZE = 0x10000

    # Opcode constants
    OP_NOP = 0x00
    OP_ADD = 0x10
    OP_SUB = 0x11
    OP_MUL = 0x12
    OP_DIV = 0x13
    OP_COPY = 0x40
    OP_RETURN = 0x31
    OP_STREAMCHAR = 0x70
    OP_STREAMNUM = 0x71
    OP_STREAMSTR = 0x72
    OP_STREAMUNICHAR = 0x73
    OP_QUIT = 0x120
    OP_GESTALT = 0x100
    OP_GLK = 0x130
    OP_SETIOSYS = 0x149  # Set I/O system mode

    # Glk function selectors (for use with OP_GLK)
    GLK_WINDOW_OPEN = 0x0023      # glk_window_open(split, method, size, wintype, rock) -> window
    GLK_SET_WINDOW = 0x002F       # glk_set_window(window) - sets current stream
    GLK_EXIT = 0x0001             # glk_exit()

    # Glk window types
    GLK_WINTYPE_TEXTBUFFER = 3

    # I/O system modes for setiosys
    IOSYS_NULL = 0   # No output
    IOSYS_FILTER = 1  # Filter to string
    IOSYS_GLK = 2    # Output via Glk

    # Operand modes (encoded in opcode bytes)
    MODE_CONST_ZERO = 0x0  # Constant 0
    MODE_CONST_BYTE = 0x1  # 1-byte constant (-128 to 127)
    MODE_CONST_SHORT = 0x2  # 2-byte constant
    MODE_CONST_WORD = 0x3  # 4-byte constant
    MODE_STACK = 0x8  # Stack pop (for loads) or push (for stores)
    MODE_LOCAL_BYTE = 0x9  # Local variable, 1-byte offset
    MODE_LOCAL_SHORT = 0xA  # Local variable, 2-byte offset
    MODE_RAM_BYTE = 0xD  # RAM address, 1-byte offset
    MODE_RAM_SHORT = 0xE  # RAM address, 2-byte offset
    MODE_RAM_WORD = 0xF  # RAM address, 4-byte offset

    # Function types
    FUNC_STACK_ARGS = 0xC0
    FUNC_LOCAL_ARGS = 0xC1

    def __init__(self):
        self.code = bytearray()
        self.functions: Dict[str, int] = {}  # function name -> address
        self.strings: List[Tuple[int, str]] = []  # (address, text)
        self.ram_start = 0
        self.start_func = 0

    def create_header(self, rom_size: int, ram_size: int = 256) -> bytearray:
        """
        Create Glulx header (36 bytes).

        Args:
            rom_size: Size of ROM (read-only) section
            ram_size: Size of RAM (writable) section

        Returns:
            36-byte header
        """
        header = bytearray(36)

        # Bytes 0-3: Magic number "Glul"
        header[0:4] = self.MAGIC

        # Bytes 4-7: Glulx version
        struct.pack_into('>I', header, 4, self.GLULX_VERSION)

        # Bytes 8-11: RAMSTART - where RAM begins (must be 256-byte aligned)
        ramstart = (rom_size + 255) & ~255
        struct.pack_into('>I', header, 8, ramstart)
        self.ram_start = ramstart

        # Bytes 12-15: EXTSTART - where file ends (also end of initial RAM)
        extstart = ramstart + ram_size
        struct.pack_into('>I', header, 12, extstart)

        # Bytes 16-19: ENDMEM - end of memory space
        endmem = extstart
        struct.pack_into('>I', header, 16, endmem)

        # Bytes 20-23: Stack size
        struct.pack_into('>I', header, 20, self.DEFAULT_STACK_SIZE)

        # Bytes 24-27: Start function address (will be set later)
        struct.pack_into('>I', header, 24, 0)  # placeholder

        # Bytes 28-31: Decoding table (0 = no string decoding table)
        struct.pack_into('>I', header, 28, 0)

        # Bytes 32-35: Checksum (calculated later)
        struct.pack_into('>I', header, 32, 0)

        return header

    def encode_operand_mode(self, mode: int, value: int) -> Tuple[int, bytes]:
        """
        Encode an operand with its mode and value.

        Args:
            mode: Operand mode (MODE_* constant)
            value: Operand value

        Returns:
            Tuple of (mode_nibble, value_bytes)
        """
        if mode == self.MODE_CONST_ZERO:
            return (mode, b'')
        elif mode == self.MODE_CONST_BYTE:
            return (mode, struct.pack('b', value))
        elif mode == self.MODE_CONST_SHORT:
            return (mode, struct.pack('>h', value))
        elif mode == self.MODE_CONST_WORD:
            return (mode, struct.pack('>i', value))
        elif mode == self.MODE_STACK:
            return (mode, b'')
        elif mode == self.MODE_LOCAL_BYTE:
            return (mode, struct.pack('B', value))
        elif mode == self.MODE_LOCAL_SHORT:
            return (mode, struct.pack('>H', value))
        else:
            return (mode, struct.pack('>I', value))

    def encode_const(self, value: int) -> Tuple[int, bytes]:
        """Encode a constant value with optimal size."""
        if value == 0:
            return (self.MODE_CONST_ZERO, b'')
        elif -128 <= value <= 127:
            return (self.MODE_CONST_BYTE, struct.pack('b', value))
        elif -32768 <= value <= 32767:
            return (self.MODE_CONST_SHORT, struct.pack('>h', value))
        else:
            return (self.MODE_CONST_WORD, struct.pack('>i', value))

    def emit_opcode(self, opcode: int, operands: List[Tuple[int, bytes]] = None) -> bytes:
        """
        Emit an opcode with operands.

        Args:
            opcode: Opcode number
            operands: List of (mode, value_bytes) tuples

        Returns:
            Encoded instruction bytes
        """
        result = bytearray()
        operands = operands or []

        # Encode opcode (variable length)
        if opcode <= 0x7F:
            # 1-byte opcode: 2 operands max, modes in high bits
            if len(operands) <= 2:
                mode_byte = opcode
                if len(operands) >= 1:
                    mode_byte |= (operands[0][0] & 0xF) << 4
                if len(operands) >= 2:
                    mode_byte |= (operands[1][0] & 0xF) << 0
                    # Wait, for 2-operand the layout is different
                    # Actually for 1-byte opcodes: opcode in low 7 bits
                    # Let me check the spec...
                pass
            # Actually, let's use 2-byte encoding for simplicity

        # 2-byte opcode encoding (0x80-0x3FFF mapped to 0x8000-0xBFFF)
        if opcode <= 0x7F:
            # Single byte opcode, operand modes follow
            result.append(opcode)
            # Add mode bytes
            if operands:
                # Modes are packed 2 per byte
                mode_bytes = []
                for i in range(0, len(operands), 2):
                    mode = operands[i][0]
                    if i + 1 < len(operands):
                        mode |= operands[i + 1][0] << 4
                    mode_bytes.append(mode)
                result.extend(mode_bytes)
        elif opcode <= 0x3FFF:
            # 2-byte opcode
            result.append(0x80 | ((opcode >> 8) & 0x3F))
            result.append(opcode & 0xFF)
            # Add mode bytes
            if operands:
                mode_bytes = []
                for i in range(0, len(operands), 2):
                    mode = operands[i][0]
                    if i + 1 < len(operands):
                        mode |= operands[i + 1][0] << 4
                    mode_bytes.append(mode)
                result.extend(mode_bytes)
        else:
            # 4-byte opcode
            result.append(0xC0 | ((opcode >> 24) & 0x0F))
            result.append((opcode >> 16) & 0xFF)
            result.append((opcode >> 8) & 0xFF)
            result.append(opcode & 0xFF)
            if operands:
                mode_bytes = []
                for i in range(0, len(operands), 2):
                    mode = operands[i][0]
                    if i + 1 < len(operands):
                        mode |= operands[i + 1][0] << 4
                    mode_bytes.append(mode)
                result.extend(mode_bytes)

        # Add operand values
        for _, value_bytes in operands:
            result.extend(value_bytes)

        return bytes(result)

    def emit_streamchar(self, char: int) -> bytes:
        """Emit streamchar instruction to print a character."""
        # streamchar opcode = 0x70 (1 byte)
        # Format: opcode, mode_byte, value
        mode, value_bytes = self.encode_const(char)
        result = bytearray([0x70, mode])
        result.extend(value_bytes)
        return bytes(result)

    def emit_streamunichar(self, char: int) -> bytes:
        """Emit streamunichar instruction to print a Unicode character."""
        # streamunichar opcode = 0x73 (1 byte)
        mode, value_bytes = self.encode_const(char)
        result = bytearray([0x73, mode])
        result.extend(value_bytes)
        return bytes(result)

    def emit_quit(self) -> bytes:
        """Emit quit instruction."""
        # quit opcode = 0x120 (2-byte encoding: 0x81 0x20)
        # No operands, so no mode byte needed
        return bytes([0x81, 0x20])

    def emit_return(self, value: int = 0) -> bytes:
        """Emit return instruction."""
        # return opcode = 0x31 (1 byte)
        mode, value_bytes = self.encode_const(value)
        result = bytearray([0x31, mode])
        result.extend(value_bytes)
        return bytes(result)

    def emit_setiosys(self, mode: int, rock: int = 0) -> bytes:
        """
        Emit setiosys instruction to set the I/O system mode.

        This MUST be called before streamchar/streamunichar will produce output.

        Args:
            mode: I/O mode (IOSYS_GLK = 2 for Glk output)
            rock: Rock value (usually 0)

        Returns:
            Encoded setiosys instruction bytes
        """
        result = bytearray()

        # setiosys opcode = 0x149 (2-byte encoding: 0x81 0x49)
        result.append(0x81)
        result.append(0x49)

        # Mode byte: L1 mode (low nibble), L2 mode (high nibble)
        mode_enc, mode_bytes = self.encode_const(mode)
        rock_enc, rock_bytes = self.encode_const(rock)
        mode_byte = (rock_enc << 4) | mode_enc
        result.append(mode_byte)

        # Operand values
        result.extend(mode_bytes)
        result.extend(rock_bytes)

        return bytes(result)

    def emit_glk(self, selector: int, num_args: int, store_mode: int = None) -> bytes:
        """
        Emit a Glk function call.

        The GLK opcode (0x130) takes:
        - L1: Glk function selector
        - L2: Number of arguments (args are on stack)
        - S1: Store destination for result (0 to discard)

        Args:
            selector: Glk function selector (e.g., GLK_WINDOW_OPEN)
            num_args: Number of arguments on the stack
            store_mode: Where to store result (None = stack, 0 = discard)

        Returns:
            Encoded GLK instruction bytes
        """
        result = bytearray()

        # GLK opcode 0x130 = 2-byte encoding: 0x81 0x30
        result.append(0x81)
        result.append(0x30)

        # Mode byte: L1 mode, L2 mode, S1 mode packed
        # We use 2-byte constants for selector/args for simplicity
        selector_mode, selector_bytes = self.encode_const(selector)
        args_mode, args_bytes = self.encode_const(num_args)

        if store_mode is None:
            # Store to stack
            s1_mode = self.MODE_STACK
        else:
            s1_mode = self.MODE_CONST_ZERO  # Discard result

        # Pack modes: L1 in low nibble, L2 in high nibble of byte 1
        # S1 in low nibble of byte 2
        mode_byte1 = (args_mode << 4) | selector_mode
        mode_byte2 = s1_mode
        result.append(mode_byte1)
        result.append(mode_byte2)

        # Add operand values
        result.extend(selector_bytes)
        result.extend(args_bytes)

        return bytes(result)

    def emit_copy(self, value: int, dest_mode: int = None) -> bytes:
        """
        Emit a copy instruction to push a value onto the stack.

        Args:
            value: Value to copy
            dest_mode: Destination mode (default: stack)

        Returns:
            Encoded COPY instruction bytes
        """
        result = bytearray()

        # COPY opcode = 0x40 (1 byte)
        result.append(0x40)

        # Get source operand encoding
        src_mode, src_bytes = self.encode_const(value)

        # Destination is stack
        dst_mode = self.MODE_STACK if dest_mode is None else dest_mode

        # Mode byte: src in low nibble, dst in high nibble
        mode_byte = (dst_mode << 4) | src_mode
        result.append(mode_byte)

        # Add source value bytes
        result.extend(src_bytes)

        return bytes(result)

    def emit_glk_init(self) -> bytes:
        """
        Emit Glk initialization code to open a text buffer window.

        This sequence:
        1. Set I/O system to Glk mode
        2. Pushes args for glk_window_open(0, 0, 0, wintype_TextBuffer, 0)
        3. Calls glk_window_open, result on stack
        4. Calls glk_set_window with the window reference

        After this, streamchar/streamunichar will work.
        """
        result = bytearray()

        # First, set the I/O system to Glk mode - this is REQUIRED
        result.extend(self.emit_setiosys(self.IOSYS_GLK, 0))

        # Push args for glk_window_open(split=0, method=0, size=0, wintype=3, rock=0)
        # Glulx spec: "pushed on the stack, in forward order"
        # First arg pushed first (ends up at bottom), last arg pushed last (on top)
        result.extend(self.emit_copy(0))  # split (arg 1 - pushed first)
        result.extend(self.emit_copy(0))  # method (arg 2)
        result.extend(self.emit_copy(0))  # size (arg 3)
        result.extend(self.emit_copy(self.GLK_WINTYPE_TEXTBUFFER))  # wintype=3 (arg 4)
        result.extend(self.emit_copy(0))  # rock (arg 5 - pushed last, on top)

        # Call glk_window_open - result (window ref) goes on stack
        result.extend(self.emit_glk(self.GLK_WINDOW_OPEN, 5))

        # Now call glk_set_window with the window ref on stack
        result.extend(self.emit_glk(self.GLK_SET_WINDOW, 1, store_mode=0))

        return bytes(result)

    def create_function(self, code: bytes, num_locals: int = 0) -> bytes:
        """
        Create a Glulx function.

        Args:
            code: Function body bytecode
            num_locals: Number of local variables

        Returns:
            Complete function bytes
        """
        result = bytearray()

        # Function type (stack-args for now)
        result.append(self.FUNC_STACK_ARGS)

        # Local variable format (pairs of: type, count)
        # Type 4 = 32-bit locals
        if num_locals > 0:
            result.append(4)  # type = 32-bit
            result.append(num_locals)  # count
        # End of locals format: (type=0, count=0) pair
        result.append(0)  # type = 0 (end marker)
        result.append(0)  # count = 0

        # Function body
        result.extend(code)

        return bytes(result)

    def emit_string_print(self, text: str) -> bytes:
        """
        Emit code to print a string using streamchar/streamunichar.

        For ASCII chars, uses streamchar. For Unicode, uses streamunichar.
        """
        result = bytearray()
        for char in text:
            code = ord(char)
            if code < 128:
                result.extend(self.emit_streamchar(code))
            else:
                result.extend(self.emit_streamunichar(code))
        return bytes(result)

    def build_story_file(self, routines_code: bytes = None,
                        main_string: str = None,
                        objects_data: bytes = None,
                        dict_data: bytes = None,
                        **kwargs) -> bytes:
        """
        Build a complete Glulx story file.

        For the simple Unicode test, we just need to print a string and quit.

        Args:
            routines_code: Pre-compiled routine bytecode (optional)
            main_string: String to print in main function (optional)
            objects_data: Object table data (ignored for now)
            dict_data: Dictionary data (ignored for now)
            **kwargs: Additional parameters (ignored for compatibility)

        Returns:
            Complete Glulx story file bytes
        """
        # Build the main function code
        func_code = bytearray()

        # Always start with Glk initialization to set up I/O
        func_code.extend(self.emit_glk_init())

        if main_string:
            func_code.extend(self.emit_string_print(main_string))
            func_code.extend(self.emit_quit())
        elif routines_code:
            func_code.extend(routines_code)
        else:
            # Default: just quit
            func_code.extend(self.emit_quit())

        # Create the main function
        main_func = self.create_function(bytes(func_code))

        # Build ROM section (header + code)
        # Header is 36 bytes, function starts at offset 36
        header_size = 36
        func_addr = header_size

        # Calculate total ROM size (must be 256-byte aligned for RAMSTART)
        rom_content = main_func
        rom_size = header_size + len(rom_content)

        # Create header with correct addresses
        header = self.create_header(rom_size)

        # Set start function address
        struct.pack_into('>I', header, 24, func_addr)

        # Build complete ROM
        rom = bytearray(header)
        rom.extend(rom_content)

        # Pad to RAMSTART alignment (256 bytes)
        ramstart = struct.unpack('>I', header[8:12])[0]
        while len(rom) < ramstart:
            rom.append(0)

        # Add minimal RAM section (just zeros)
        extstart = struct.unpack('>I', header[12:16])[0]
        while len(rom) < extstart:
            rom.append(0)

        # Calculate and set checksum
        checksum = self.calculate_checksum(rom)
        struct.pack_into('>I', rom, 32, checksum)

        return bytes(rom)

    def calculate_checksum(self, data: bytes) -> int:
        """
        Calculate Glulx checksum.

        The checksum is the sum of all bytes in the file,
        with the checksum field itself treated as zeros.
        """
        total = 0
        for i, byte in enumerate(data):
            if 32 <= i < 36:
                # Skip checksum field
                continue
            total = (total + byte) & 0xFFFFFFFF
        return total
