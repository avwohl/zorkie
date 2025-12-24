"""
Z-machine assembler - assembles bytecode and builds story file.

This is a simplified assembler for the initial implementation.
"""

from typing import List, Dict, Optional
import struct


class ZAssembler:
    """Assembles Z-machine bytecode into a story file."""

    def __init__(self, version: int = 3):
        self.version = version
        self.memory = bytearray()
        self.dynamic_mem_size = 0
        self.static_mem_base = 0
        self.high_mem_base = 0

    def create_header(self) -> bytearray:
        """Create Z-machine header (64 bytes)."""
        header = bytearray(64)

        # Byte 0: Version
        header[0] = self.version

        # Bytes 1: Flags 1 (will be set by interpreter)
        header[1] = 0x00

        # Bytes 4-5: High memory base (placeholder)
        header[4:6] = struct.pack('>H', self.high_mem_base or 0x0400)

        # Bytes 6-7: Initial PC / Main routine (placeholder)
        header[6:8] = struct.pack('>H', 0x0400)

        # Bytes 8-9: Dictionary location (placeholder)
        header[8:10] = struct.pack('>H', 0x0200)

        # Bytes 0xA-0xB: Object table location
        header[0xA:0xC] = struct.pack('>H', 0x0100)

        # Bytes 0xC-0xD: Globals table location
        header[0xC:0xE] = struct.pack('>H', 0x0080)

        # Bytes 0xE-0xF: Static memory base
        header[0xE:0x10] = struct.pack('>H', self.static_mem_base or 0x0400)

        # Bytes 0x10-0x11: Flags 2
        header[0x10:0x12] = struct.pack('>H', 0x0000)

        # Bytes 0x12-0x17: Serial number (YYMMDD)
        header[0x12:0x18] = b'250115'  # Today's date

        # Bytes 0x18-0x19: Abbreviations table (0 = none)
        header[0x18:0x1A] = struct.pack('>H', 0x0000)

        # Bytes 0x1A-0x1B: File length / divisor
        # V1-3: divisor 2, V4-5: divisor 4, V6+: divisor 8
        divisor = 2 if self.version <= 3 else (4 if self.version <= 5 else 8)
        file_length = len(self.memory) // divisor if self.memory else 1
        header[0x1A:0x1C] = struct.pack('>H', file_length)

        # Bytes 0x1C-0x1D: Checksum (calculated later)
        header[0x1C:0x1E] = struct.pack('>H', 0x0000)

        return header

    def calculate_checksum(self, data: bytes) -> int:
        """Calculate story file checksum (sum of all bytes except header)."""
        return sum(data[0x40:]) & 0xFFFF

    def _resolve_table_placeholders(self, data: bytes, table_base_addr: int,
                                       table_offsets: dict) -> bytes:
        """
        Resolve table address placeholders in data.

        Scans for 16-bit values in range 0xFF00-0xFFFF which represent table
        indices, and replaces them with actual table addresses.

        Args:
            data: Bytes to scan (typically globals_data)
            table_base_addr: Base address where tables are placed in memory
            table_offsets: Dict mapping table index to offset within table data

        Returns:
            Modified data with actual table addresses
        """
        if not table_offsets:
            return data

        result = bytearray(data)

        # Scan for 16-bit table placeholders (0xFF00 | table_index)
        # Globals are stored as big-endian 16-bit words
        for i in range(0, len(result) - 1, 2):
            word = (result[i] << 8) | result[i + 1]
            # Check if this is a table placeholder (0xFF00-0xFFFF)
            if word >= 0xFF00 and word <= 0xFFFF:
                table_index = word & 0x00FF
                if table_index in table_offsets:
                    # Calculate actual table address
                    actual_addr = table_base_addr + table_offsets[table_index]
                    # Write back as big-endian
                    result[i] = (actual_addr >> 8) & 0xFF
                    result[i + 1] = actual_addr & 0xFF

        return bytes(result)

    def _resolve_string_markers(self, routines: bytes, string_table) -> bytes:
        """
        Resolve string table markers in routine bytecode.

        Replaces markers (0x8D 0xFF 0xFE <length> <text>) with actual
        PRINT_PADDR instructions (0x8D <packed_addr_hi> <packed_addr_lo>).

        Args:
            routines: Original routine bytecode with markers
            string_table: StringTable instance with resolved addresses

        Returns:
            Modified routine bytecode with markers resolved
        """
        result = bytearray()
        i = 0

        while i < len(routines):
            # Check for string table marker: 0x8D 0xFF 0xFE
            if (i + 4 < len(routines) and
                routines[i] == 0x8D and
                routines[i+1] == 0xFF and
                routines[i+2] == 0xFE):

                # Read string length (2 bytes, little-endian)
                text_len = routines[i+3] | (routines[i+4] << 8)

                # Read string text
                if i + 5 + text_len <= len(routines):
                    text_bytes = routines[i+5:i+5+text_len]
                    text = text_bytes.decode('utf-8')

                    # Get packed address from string table
                    packed_addr = string_table.get_packed_address(text, self.version)

                    if packed_addr is not None:
                        # Emit PRINT_PADDR with actual packed address
                        result.append(0x8D)  # SHORT PRINT_PADDR
                        result.append((packed_addr >> 8) & 0xFF)  # High byte
                        result.append(packed_addr & 0xFF)  # Low byte

                        # Skip past the marker and text
                        i += 5 + text_len
                        continue
                    else:
                        # String not in table (shouldn't happen), keep marker
                        result.append(routines[i])
                        i += 1
                else:
                    # Incomplete marker, keep byte
                    result.append(routines[i])
                    i += 1
            else:
                # Normal bytecode, copy as-is
                result.append(routines[i])
                i += 1

        return bytes(result)

    def _resolve_routine_fixups(self, routines: bytes, routine_fixups: list) -> bytes:
        """
        Resolve routine call fixups by patching addresses.

        Each fixup is (code_offset, routine_offset) where:
        - code_offset: Position in routines to patch (2 bytes)
        - routine_offset: Byte offset of target routine within routines

        Args:
            routines: Routine bytecode with placeholder addresses
            routine_fixups: List of fixup tuples

        Returns:
            Patched routine bytecode
        """
        if not routine_fixups:
            return routines

        result = bytearray(routines)

        for code_offset, routine_offset in routine_fixups:
            # Calculate actual byte address of routine
            actual_addr = self.high_mem_base + routine_offset

            # Convert to packed address based on version
            # V1-3: packed = byte_addr / 2
            # V4-5: packed = byte_addr / 4
            # V6-7: packed = (byte_addr - 8*routines_offset) / 4 = routine_offset / 4
            # V8:   packed = byte_addr / 8
            if self.version <= 3:
                packed_addr = actual_addr // 2
            elif self.version <= 5:
                packed_addr = actual_addr // 4
            elif self.version <= 7:
                # V6-7 use routines_offset, so packed = routine_offset / 4
                packed_addr = routine_offset // 4
            else:
                packed_addr = actual_addr // 8

            # Patch the 16-bit address
            if code_offset + 1 < len(result):
                result[code_offset] = (packed_addr >> 8) & 0xFF
                result[code_offset + 1] = packed_addr & 0xFF

        return bytes(result)

    def _resolve_string_placeholders(self, routines: bytes, string_placeholders: dict,
                                       string_table) -> bytes:
        """
        Resolve string operand placeholders in routine bytecode.

        Scans bytecode for 0xFC00 | index values and replaces them with actual
        packed string addresses.

        Args:
            routines: Routine bytecode with string placeholders
            string_placeholders: Dict mapping placeholder index to string text
            string_table: StringTable instance with resolved addresses

        Returns:
            Patched routine bytecode
        """
        if not string_placeholders or not string_table:
            return routines

        result = bytearray(routines)

        # Scan for 0xFC00 | index patterns (16-bit values)
        i = 0
        while i < len(result) - 1:
            # Check for 0xFC high byte
            if result[i] == 0xFC:
                placeholder_idx = result[i + 1]
                if placeholder_idx in string_placeholders:
                    text = string_placeholders[placeholder_idx]
                    # Get packed address from string table
                    packed_addr = string_table.get_packed_address(text, self.version)
                    if packed_addr is not None:
                        # Patch the 16-bit address
                        result[i] = (packed_addr >> 8) & 0xFF
                        result[i + 1] = packed_addr & 0xFF
            i += 1

        return bytes(result)

    def _resolve_dict_placeholders(self, objects_data: bytes, dict_addr: int,
                                     prop_defaults_size: int) -> bytes:
        """
        Resolve dictionary word placeholders in object property tables.

        Scans property tables for values marked with 0x8000 (SYNONYM) or 0xFE00
        (ADJECTIVE) high bits and replaces them with actual dictionary addresses.

        Args:
            objects_data: Object table data with property tables
            dict_addr: Base address of dictionary in story file
            prop_defaults_size: Size of property defaults table in bytes

        Returns:
            Modified object data with dictionary addresses resolved
        """
        result = bytearray(objects_data)

        # Property tables start after property defaults and object entries
        # We need to scan the property tables for placeholder values
        # Property table format:
        #   - Text length byte + encoded name
        #   - Property entries: size byte + data bytes
        #   - Terminator (0x00)

        # Start scanning after property defaults table
        i = prop_defaults_size

        # Skip object entries (we don't modify those)
        # Find where property tables start by reading first object's prop table addr
        if self.version <= 3:
            obj_entry_size = 9
        else:
            obj_entry_size = 14

        if len(result) > prop_defaults_size + obj_entry_size:
            # Get first property table address
            prop_addr_offset = prop_defaults_size + obj_entry_size - 2
            first_prop_offset = struct.unpack('>H', result[prop_addr_offset:prop_addr_offset+2])[0]
            # Start scanning from first property table
            i = first_prop_offset

        # Scan through data looking for placeholder patterns
        # Placeholders are 2-byte words with high byte 0x80 (SYNONYM) or 0xFE (ADJ)
        while i < len(result) - 1:
            word = (result[i] << 8) | result[i + 1]

            # Check for SYNONYM placeholder: 0x8000 | word_offset
            # word_offset is typically small (< 0x1000)
            if (word & 0xF000) == 0x8000:
                word_offset = word & 0x0FFF
                actual_addr = dict_addr + word_offset
                result[i] = (actual_addr >> 8) & 0xFF
                result[i + 1] = actual_addr & 0xFF
                i += 2
            # Check for ADJECTIVE placeholder: 0xFE00 | word_offset
            elif (word & 0xFF00) == 0xFE00:
                word_offset = word & 0x00FF
                actual_addr = dict_addr + word_offset
                result[i] = (actual_addr >> 8) & 0xFF
                result[i + 1] = actual_addr & 0xFF
                i += 2
            else:
                i += 1

        return bytes(result)

    def build_story_file(self, routines: bytes, objects: bytes = b'',
                        dictionary: bytes = b'', globals_data: bytes = b'',
                        abbreviations_table=None, string_table=None,
                        table_data: bytes = b'',
                        table_offsets: dict = None,
                        routine_fixups: list = None,
                        table_routine_fixups: list = None,
                        extension_table: bytes = b'',
                        string_placeholders: dict = None) -> bytes:
        """
        Build complete story file.

        Args:
            routines: Compiled routine bytecode
            objects: Object table data
            dictionary: Dictionary data
            globals_data: Global variables data
            abbreviations_table: AbbreviationsTable instance (optional)
            string_table: StringTable instance (optional, for deduplication)
            table_data: TABLE/LTABLE/ITABLE data (optional)
            table_offsets: Dict mapping table index to offset within table_data
            routine_fixups: List of (code_offset, routine_offset) for call address patching
            table_routine_fixups: List of (table_offset, routine_offset) for table routine addresses
            extension_table: Header extension table bytes (V5+)
            string_placeholders: Dict mapping placeholder index to string text for operand resolution

        Returns:
            Complete story file as bytes
        """
        # Initialize table_offsets if not provided
        if table_offsets is None:
            table_offsets = {}

        # Start with header
        story = self.create_header()

        # Track addresses as we build
        current_addr = 0x40  # After 64-byte header

        # Add globals (after header, starting at 0x40 typically)
        if not globals_data:
            # Default: 240 globals initialized to 0
            globals_data = bytes(480)  # 240 * 2 bytes

        # First, calculate where tables will be placed so we can resolve addresses.
        # We need to do a "dry run" to calculate table_base_addr before patching globals.
        # Calculate sizes of: globals, abbreviations, objects, dictionary
        calc_addr = 0x40  # After header
        calc_addr += len(globals_data)  # globals
        calc_addr = (calc_addr + 1) // 2 * 2  # pad to word boundary

        # Abbreviations size (if present)
        abbrev_encoded = False
        if abbreviations_table and self.version >= 2 and len(abbreviations_table) > 0:
            from .text_encoding import ZTextEncoder
            text_encoder = ZTextEncoder(self.version)
            abbreviations_table.encode_abbreviations(text_encoder)
            abbrev_encoded = True
            calc_addr += 192  # 96 word addresses table
            for encoded_string in abbreviations_table.encoded_strings:
                calc_addr += len(encoded_string)
            calc_addr = (calc_addr + 1) // 2 * 2  # pad

        calc_addr = (calc_addr + 1) // 2 * 2  # pad
        calc_addr += len(objects) if objects else 0  # objects
        calc_addr = (calc_addr + 1) // 2 * 2  # pad
        calc_addr += len(dictionary) if dictionary else 0  # dictionary
        calc_addr = (calc_addr + 1) // 2 * 2  # pad

        # NOW we know where tables will be placed
        table_base_addr = calc_addr

        # Patch globals_data with actual table addresses
        if table_data and table_offsets:
            globals_data = self._resolve_table_placeholders(
                globals_data, table_base_addr, table_offsets
            )

        globals_addr = current_addr
        story.extend(globals_data)
        current_addr += len(globals_data)

        # Pad to word boundary
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

        # Add abbreviations table (V2+) if present
        abbrev_addr = 0
        abbrev_strings_addr = 0
        if abbreviations_table and self.version >= 2 and len(abbreviations_table) > 0:
            # Encode abbreviation strings if not already done in calculation pass
            if not abbrev_encoded:
                from .text_encoding import ZTextEncoder
                text_encoder = ZTextEncoder(self.version)
                abbreviations_table.encode_abbreviations(text_encoder)

            # Abbreviations table comes first (96 word addresses)
            abbrev_addr = current_addr
            abbrev_strings_addr = abbrev_addr + 192  # After the 96-entry table

            # Generate the abbreviations table
            abbrev_table_bytes = abbreviations_table.get_abbreviation_table_bytes(abbrev_strings_addr)
            story.extend(abbrev_table_bytes)
            current_addr += len(abbrev_table_bytes)

            # Add the encoded abbreviation strings
            for encoded_string in abbreviations_table.encoded_strings:
                story.extend(encoded_string)
                current_addr += len(encoded_string)

            # Pad to word boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Pad to next boundary if needed
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

        # Add objects
        objects_addr = current_addr
        if objects:
            # Need to fix up property table addresses in object table
            # Property table addresses are relative to start of object data (0),
            # but need to be absolute addresses in the story file
            objects_fixed = bytearray(objects)

            # Property defaults: 31 words for V3, 63 for V4+
            prop_defaults_size = (31 if self.version <= 3 else 63) * 2
            obj_entry_size = 9 if self.version <= 3 else 14

            # Calculate dictionary address ahead of time to resolve property placeholders
            # Dictionary comes right after objects (with padding)
            objects_end = current_addr + len(objects_fixed)
            if objects_end % 2 != 0:
                objects_end += 1  # Account for padding
            dict_addr_calc = objects_end

            # Resolve dictionary word placeholders in property tables BEFORE
            # fixing up property table addresses (since the resolver uses relative offsets)
            # Placeholders are marked with 0x8000 bit set (SYNONYM) or 0xFE00 (ADJECTIVE)
            # The low bits contain the word offset within dictionary data
            objects_fixed = bytearray(self._resolve_dict_placeholders(
                bytes(objects_fixed), dict_addr_calc, prop_defaults_size
            ))

            # Calculate number of objects
            # Find first property table address to determine where object entries end
            if len(objects_fixed) > prop_defaults_size + 7:
                first_obj_offset = prop_defaults_size
                # Property table address is last 2 bytes of object entry
                prop_addr_offset = first_obj_offset + obj_entry_size - 2
                if prop_addr_offset + 2 <= len(objects_fixed):
                    first_prop_addr = struct.unpack('>H', objects_fixed[prop_addr_offset:prop_addr_offset+2])[0]

                    # Calculate number of objects
                    obj_entries_size = first_prop_addr - prop_defaults_size
                    num_objects = obj_entries_size // obj_entry_size

                    # Fix up all object property table addresses
                    for i in range(num_objects):
                        obj_offset = prop_defaults_size + (i * obj_entry_size)
                        prop_addr_offset = obj_offset + obj_entry_size - 2

                        if prop_addr_offset + 2 <= len(objects_fixed):
                            # Read relative address
                            rel_addr = struct.unpack('>H', objects_fixed[prop_addr_offset:prop_addr_offset+2])[0]
                            # Convert to absolute address
                            abs_addr = objects_addr + rel_addr
                            # Write back
                            struct.pack_into('>H', objects_fixed, prop_addr_offset, abs_addr)

            story.extend(objects_fixed)
            current_addr += len(objects_fixed)

        # Pad to next boundary
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

        # Add dictionary
        dict_addr = current_addr
        if dictionary:
            story.extend(dictionary)
            current_addr += len(dictionary)

        # Align to even boundary
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

        # Add table data in dynamic memory (before static memory)
        # Tables need to be writable, so they go in dynamic memory
        table_base_addr = current_addr

        if table_data:
            story.extend(table_data)
            current_addr += len(table_data)

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Add extension table (V5+) in dynamic memory
        extension_table_addr = 0
        if extension_table and self.version >= 5:
            extension_table_addr = current_addr
            story.extend(extension_table)
            current_addr += len(extension_table)

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Static memory starts after tables and extension table (in dynamic memory)
        self.static_mem_base = current_addr

        # Mark start of high memory (where code begins)
        self.high_mem_base = len(story)

        # High memory must be aligned for packed addresses:
        # V1-3: 2-byte alignment (packed = byte / 2)
        # V4-7: 4-byte alignment (packed = byte / 4)
        # V8: 8-byte alignment (packed = byte / 8)
        if self.version >= 8:
            alignment = 8
        elif self.version >= 4:
            alignment = 4
        else:
            alignment = 2

        while self.high_mem_base % alignment != 0:
            story.append(0)
            self.high_mem_base = len(story)

        # Resolve table routine fixups (for ACTIONS table packed addresses)
        # Now that we know high_mem_base, patch table data with routine addresses
        if table_routine_fixups and table_data:
            for table_offset, routine_offset in table_routine_fixups:
                # Calculate actual byte address of routine
                actual_addr = self.high_mem_base + routine_offset

                # Convert to packed address based on version
                if self.version <= 3:
                    packed_addr = actual_addr // 2
                elif self.version <= 7:
                    packed_addr = actual_addr // 4
                else:
                    packed_addr = actual_addr // 8

                # Patch the table data in the story (at table_base_addr + table_offset)
                story_offset = table_base_addr + table_offset
                if story_offset + 1 < len(story):
                    story[story_offset] = (packed_addr >> 8) & 0xFF
                    story[story_offset + 1] = packed_addr & 0xFF

        # If string table is present, add string table after routines and resolve markers
        if string_table is not None:
            # Calculate final routine length AFTER marker resolution
            # Each marker (0x8D 0xFF 0xFE <len16> <text>) becomes 3 bytes (0x8D <addr16>)
            # So we shrink by (5 + text_len - 3) = (2 + text_len) per marker
            final_routines_len = len(routines)
            i = 0
            while i < len(routines):
                if (i + 4 < len(routines) and
                    routines[i] == 0x8D and
                    routines[i+1] == 0xFF and
                    routines[i+2] == 0xFE):
                    text_len = routines[i+3] | (routines[i+4] << 8)
                    # This marker will shrink from (5 + text_len) to 3 bytes
                    final_routines_len -= (2 + text_len)
                    i += 5 + text_len
                else:
                    i += 1

            # Now calculate where string table will be located
            string_table_base = self.high_mem_base + final_routines_len

            # Align based on version (packed address requirements)
            # V1-3: 2-byte alignment
            # V4-7: 4-byte alignment
            # V8:   8-byte alignment
            if self.version >= 8:
                alignment = 8
            elif self.version >= 4:
                alignment = 4
            else:
                alignment = 2
            while string_table_base % alignment != 0:
                string_table_base += 1

            # Set the base address in string table
            string_table.set_base_address(string_table_base)

            # Now resolve string table markers with correct addresses
            routines = self._resolve_string_markers(routines, string_table)

            # Resolve string operand placeholders (0xFC00 | index -> packed address)
            if string_placeholders:
                routines = self._resolve_string_placeholders(
                    routines, string_placeholders, string_table
                )

        # Resolve routine call fixups (patch call addresses)
        if routine_fixups:
            routines = self._resolve_routine_fixups(routines, routine_fixups)

        # Add routines
        story.extend(routines)

        # Add string table data if present
        if string_table is not None:
            # Align based on version (must match the string_table_base calculation)
            if self.version >= 8:
                alignment = 8
            elif self.version >= 4:
                alignment = 4
            else:
                alignment = 2
            while len(story) % alignment != 0:
                story.append(0)

            # Add all encoded strings
            story.extend(string_table.get_encoded_data())

        # Calculate Initial PC - must point to first instruction, not routine header
        # Routine header format:
        #   V1-4: 1 byte (local count) + N words (local defaults)
        #   V5+: 1 byte (local count) only
        initial_pc = self.high_mem_base
        if routines:
            num_locals = routines[0] & 0x0F  # Local count is in low nibble
            if self.version <= 4:
                # Skip: 1 byte header + num_locals * 2 bytes for defaults
                initial_pc = self.high_mem_base + 1 + (num_locals * 2)
            else:
                # Skip: 1 byte header only
                initial_pc = self.high_mem_base + 1

        # For V6-7, the Initial PC field stores a packed routine address
        # The packed address calculation depends on version:
        #   V6-7: packed_address = (byte_address - routines_offset * 8) / 4
        # For simplicity with routines_offset = high_mem_base / 8:
        #   V6-7: packed_address = (addr - high_mem_base) / 4 = offset / 4
        # Since the routine starts at high_mem_base, and we want to skip
        # to the first instruction (which is 1 byte after for V5+),
        # we need to calculate the packed address of the routine itself.
        #
        # Actually for V6-7, Initial PC points to the ROUTINE (packed),
        # and the interpreter handles finding the first instruction.
        # V8 uses direct byte addresses like V5.
        if self.version in (6, 7):
            # Packed routine address = (routine_byte_addr - 8 * routines_offset) / 4
            # With routines_offset = high_mem_base / 8:
            # packed = (high_mem_base - high_mem_base) / 4 = 0
            # So the first routine is always at packed address 0 relative to routines_offset
            initial_pc = 0  # Packed address of first routine

        # Update header with correct addresses
        struct.pack_into('>H', story, 0x04, self.high_mem_base)  # High memory base
        struct.pack_into('>H', story, 0x06, initial_pc)  # Initial PC (or packed routine for V6+)
        struct.pack_into('>H', story, 0x08, dict_addr)  # Dictionary address
        struct.pack_into('>H', story, 0x0A, objects_addr)  # Object table address
        struct.pack_into('>H', story, 0x0C, globals_addr)  # Globals address
        struct.pack_into('>H', story, 0x0E, self.static_mem_base)  # Static memory base
        if abbrev_addr > 0:
            struct.pack_into('>H', story, 0x18, abbrev_addr)  # Abbreviations table address

        # V5+ extension table address
        if extension_table_addr > 0:
            struct.pack_into('>H', story, 0x36, extension_table_addr)  # Extension table address

        # V6-7 specific header fields (V8 doesn't use these)
        if self.version in (6, 7):
            # 0x28-0x29: Routines offset / 8
            # For V6-7, routines are addressed as packed addresses with offset
            # We store high_mem_base / 8 as the routines offset
            routines_offset = self.high_mem_base // 8
            struct.pack_into('>H', story, 0x28, routines_offset)

            # 0x2A-0x2B: Strings offset / 8 (same as routines for simple case)
            # In a full implementation, strings would be in a separate area
            strings_offset = self.high_mem_base // 8
            struct.pack_into('>H', story, 0x2A, strings_offset)

        # Pad file to proper boundary for file length calculation
        # V1-3: divisor 2 (must be even)
        # V4-5: divisor 4
        # V6+: divisor 8
        divisor = 2 if self.version <= 3 else (4 if self.version <= 5 else 8)
        while len(story) % divisor != 0:
            story.append(0)

        # Calculate and store checksum
        checksum = self.calculate_checksum(story)
        struct.pack_into('>H', story, 0x1C, checksum)

        # Update file length
        file_length = len(story) // divisor
        if file_length > 65535:
            max_size = 65535 * divisor
            raise ValueError(
                f"Story file too large for Z-machine version {self.version}. "
                f"File is {len(story)} bytes, maximum is {max_size} bytes ({max_size // 1024}KB). "
                f"Try compiling with a higher version (--version 6 allows up to 512KB)."
            )
        struct.pack_into('>H', story, 0x1A, file_length)

        self.memory = bytearray(story)
        return bytes(story)

    def write_story_file(self, filename: str, story: bytes):
        """Write story file to disk."""
        with open(filename, 'wb') as f:
            f.write(story)


def build_minimal_story(version: int = 3) -> bytes:
    """
    Build a minimal working story file that immediately quits.

    Useful for testing the basic file structure.
    """
    assembler = ZAssembler(version)

    # Minimal routine that just quits
    # QUIT opcode is 0x0A (0OP short form)
    routines = bytes([0xBA])  # Short form 0OP, opcode 0x0A (quit)

    return assembler.build_story_file(routines)
