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

        # Bytes 0x12-0x17: Serial number (YYMMDD) - V2+ only
        if self.version >= 2:
            from datetime import date
            today = date.today()
            serial = f"{today.year % 100:02d}{today.month:02d}{today.day:02d}"
            header[0x12:0x18] = serial.encode('ascii')
        # V1: leave as zeros (no serial number field)

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
                                       table_offsets: dict,
                                       dict_addr: int = None) -> bytes:
        """
        Resolve table address placeholders in data.

        Scans for 16-bit values in range 0xFF00-0xFFFF which represent table
        indices, and replaces them with actual table addresses.
        Also resolves VOCAB placeholder (0xFA00) with dictionary address.

        Args:
            data: Bytes to scan (typically globals_data)
            table_base_addr: Base address where tables are placed in memory
            table_offsets: Dict mapping table index to offset within table data
            dict_addr: Dictionary address for resolving VOCAB placeholder

        Returns:
            Modified data with actual table addresses
        """
        result = bytearray(data)

        # Scan for 16-bit placeholders
        # Globals are stored as big-endian 16-bit words
        for i in range(0, len(result) - 1, 2):
            word = (result[i] << 8) | result[i + 1]
            # Check if this is a VOCAB placeholder (0xFA00)
            if word == 0xFA00 and dict_addr is not None:
                # Replace with dictionary address
                result[i] = (dict_addr >> 8) & 0xFF
                result[i + 1] = dict_addr & 0xFF
            # Check if this is a table placeholder (0xFF00-0xFFFF)
            elif word >= 0xFF00 and word <= 0xFFFF and table_offsets:
                table_index = word & 0x00FF
                if table_index in table_offsets:
                    # Calculate actual table address
                    actual_addr = table_base_addr + table_offsets[table_index]
                    # Write back as big-endian
                    result[i] = (actual_addr >> 8) & 0xFF
                    result[i + 1] = actual_addr & 0xFF

        return bytes(result)

    def _resolve_string_markers(self, routines: bytes, string_table,
                                   string_placeholders: dict = None,
                                   placeholder_positions: list = None) -> bytes:
        """
        Resolve string table markers in routine bytecode.

        Uses position-based resolution when placeholder_positions is provided,
        avoiding false matches when 0x8D appears as operand data (e.g., global var 141).

        Handles two formats:
        1. Old format: (0x8D 0xFF 0xFE <length> <text>) - variable size, uses scanning
        2. New format: (0x8D <hi> <lo>) where value 0xE000-0xFFFD - uses position-based resolution

        Both are replaced with PRINT_PADDR instructions:
        (0x8D <packed_addr_hi> <packed_addr_lo>)

        Args:
            routines: Original routine bytecode with markers
            string_table: StringTable instance with resolved addresses
            string_placeholders: Dict mapping placeholder index to string text
            placeholder_positions: List of (byte_offset, placeholder_idx) for position-based resolution

        Returns:
            Modified routine bytecode with markers resolved
        """
        # Use position-based resolution if positions are provided
        if placeholder_positions:
            result = bytearray(routines)
            for byte_offset, placeholder_idx in placeholder_positions:
                if byte_offset + 2 >= len(result):
                    continue  # Invalid offset, skip
                # Verify this looks like a placeholder (0x8D followed by placeholder value)
                if result[byte_offset] != 0x8D:
                    continue  # Not a PRINT_PADDR opcode, skip
                # Get the string text for this placeholder
                if string_placeholders and placeholder_idx in string_placeholders:
                    text = string_placeholders[placeholder_idx]
                    # Get packed address from string table
                    packed_addr = string_table.get_packed_address(text, self.version)
                    if packed_addr is not None:
                        # Patch in place: keep 0x8D, update the address bytes
                        result[byte_offset + 1] = (packed_addr >> 8) & 0xFF
                        result[byte_offset + 2] = packed_addr & 0xFF
            return bytes(result)

        # Fallback: scan-based resolution (for old format or when positions not available)
        result = bytearray()
        i = 0

        while i < len(routines):
            # Check for PRINT_PADDR opcode (0x8D) which might contain placeholders
            if routines[i] == 0x8D and i + 2 < len(routines):
                high_byte = routines[i+1]
                low_byte = routines[i+2]
                placeholder_val = (high_byte << 8) | low_byte

                # Check for old string table marker: 0x8D 0xFF 0xFE <len> <text>
                if (high_byte == 0xFF and low_byte == 0xFE and
                    i + 4 < len(routines)):

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
                            continue
                    else:
                        # Incomplete marker, keep byte
                        result.append(routines[i])
                        i += 1
                        continue

                # Regular PRINT_PADDR instruction (not a placeholder), copy as-is
                # NOTE: We no longer scan for new format (0xE000-0xFFFD) to avoid false matches
                # New format should use position-based resolution via placeholder_positions
                else:
                    result.append(routines[i])
                    i += 1
                    continue

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
                # V6-7 use routines_offset, with 4-byte padding before first routine
                # packed = (4 + routine_offset) / 4
                packed_addr = (4 + routine_offset) // 4
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

    def _resolve_string_placeholders_in_story(self, story: bytearray,
                                               string_placeholders: dict,
                                               string_table,
                                               start_offset: int,
                                               length: int) -> None:
        """
        Resolve string operand placeholders in a section of the story file.

        Scans the specified range for 0xFC00 | index values and replaces them
        with actual packed string addresses. Modifies story in place.

        Args:
            story: Story bytearray to modify in place
            string_placeholders: Dict mapping placeholder index to string text
            string_table: StringTable instance with resolved addresses
            start_offset: Start offset in story to scan
            length: Number of bytes to scan
        """
        if not string_placeholders or not string_table or length == 0:
            return

        # Scan for 0xFC00 | index patterns (16-bit values)
        end_offset = min(start_offset + length, len(story) - 1)
        i = start_offset
        while i < end_offset:
            # Check for 0xFC high byte
            if story[i] == 0xFC:
                placeholder_idx = story[i + 1]
                if placeholder_idx in string_placeholders:
                    text = string_placeholders[placeholder_idx]
                    # Get packed address from string table
                    packed_addr = string_table.get_packed_address(text, self.version)
                    if packed_addr is not None:
                        # Patch the 16-bit address
                        story[i] = (packed_addr >> 8) & 0xFF
                        story[i + 1] = packed_addr & 0xFF
            i += 1

    def _resolve_vocab_placeholders(self, routines: bytes, vocab_fixups: list,
                                       dict_addr: int) -> bytes:
        """
        Resolve vocabulary word placeholders (W?*) in routine bytecode.

        Scans bytecode for 0xFB00 | index values and replaces them with actual
        dictionary word addresses.

        Args:
            routines: Routine bytecode with vocab placeholders
            vocab_fixups: List of (placeholder_idx, word_offset) tuples
            dict_addr: Base address of dictionary in story file

        Returns:
            Patched routine bytecode
        """
        if not vocab_fixups:
            return routines

        result = bytearray(routines)

        # Build a map from placeholder_idx to word address
        fixup_map = {}
        for placeholder_idx, word_offset in vocab_fixups:
            # Word offset is relative to dictionary data start
            # Final address is dict_addr + word_offset
            word_addr = dict_addr + word_offset
            fixup_map[placeholder_idx] = word_addr

        # Scan for 0xFB00 | index patterns (16-bit values)
        i = 0
        while i < len(result) - 1:
            # Check for 0xFB high byte
            if result[i] == 0xFB:
                placeholder_idx = result[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    # Patch the 16-bit address
                    result[i] = (word_addr >> 8) & 0xFF
                    result[i + 1] = word_addr & 0xFF
            i += 1

        return bytes(result)

    def _resolve_table_vocab_placeholders(self, table_data: bytes,
                                           vocab_fixups: list,
                                           dict_addr: int) -> bytes:
        """
        Resolve vocabulary word placeholders in table data.

        Scans table data for 0xFB00 | index values and replaces them with
        actual dictionary word addresses.

        Args:
            table_data: Table data with vocab placeholders
            vocab_fixups: List of (placeholder_idx, word_offset) tuples
            dict_addr: Base address of dictionary in story file

        Returns:
            Patched table data
        """
        if not vocab_fixups or not table_data:
            return table_data

        result = bytearray(table_data)

        # Build a map from placeholder_idx to word address
        fixup_map = {}
        for placeholder_idx, word_offset in vocab_fixups:
            word_addr = dict_addr + word_offset
            fixup_map[placeholder_idx] = word_addr

        # Scan for 0xFB00 | index patterns (16-bit values, word-aligned)
        i = 0
        while i < len(result) - 1:
            if result[i] == 0xFB:
                placeholder_idx = result[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    result[i] = (word_addr >> 8) & 0xFF
                    result[i + 1] = word_addr & 0xFF
            i += 1

        return bytes(result)

    def _resolve_vocab_placeholders_in_story(self, story: bytearray,
                                              vocab_fixups: list,
                                              dict_addr: int,
                                              start_offset: int,
                                              length: int) -> None:
        """
        Resolve vocabulary word placeholders in a section of the story file.

        Scans the specified range for 0xFB00 | index values and replaces them
        with actual dictionary word addresses. Modifies story in place.

        Args:
            story: Story bytearray to modify in place
            vocab_fixups: List of (placeholder_idx, word_offset) tuples
            dict_addr: Base address of dictionary in story file
            start_offset: Start offset in story to scan
            length: Number of bytes to scan
        """
        if not vocab_fixups:
            return

        # Build a map from placeholder_idx to word address
        fixup_map = {}
        for placeholder_idx, word_offset in vocab_fixups:
            word_addr = dict_addr + word_offset
            fixup_map[placeholder_idx] = word_addr

        # Scan for 0xFB00 | index patterns (16-bit values)
        end_offset = min(start_offset + length, len(story) - 1)
        i = start_offset
        while i < end_offset:
            if story[i] == 0xFB:
                placeholder_idx = story[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    story[i] = (word_addr >> 8) & 0xFF
                    story[i + 1] = word_addr & 0xFF
            i += 1

    def _resolve_dict_placeholders(self, objects_data: bytes, dict_addr: int,
                                     prop_defaults_size: int,
                                     vocab_fixups: list = None) -> bytes:
        """
        Resolve dictionary word placeholders in object property tables.

        Scans property DATA (not names) for values marked with 0x8000 (SYNONYM),
        0xFE00 (ADJECTIVE), or 0xFB00 (VOC from PROPDEF) high bits and replaces
        them with dictionary addresses.

        Args:
            objects_data: Object table data with property tables
            dict_addr: Base address of dictionary in story file
            prop_defaults_size: Size of property defaults table in bytes
            vocab_fixups: List of (placeholder_idx, word_offset) for VOC placeholders

        Returns:
            Modified object data with dictionary addresses resolved
        """
        result = bytearray(objects_data)

        # Build lookup for vocab fixups: idx -> word_offset
        vocab_lookup = {}
        if vocab_fixups:
            for idx, word_offset in vocab_fixups:
                vocab_lookup[idx] = word_offset

        # Property tables start after property defaults and object entries
        if self.version <= 3:
            obj_entry_size = 9
        else:
            obj_entry_size = 14

        if len(result) <= prop_defaults_size + obj_entry_size:
            return bytes(result)

        # Get first property table address
        prop_addr_offset = prop_defaults_size + obj_entry_size - 2
        first_prop_offset = struct.unpack('>H', result[prop_addr_offset:prop_addr_offset+2])[0]

        # Process each property table by properly parsing its structure
        i = first_prop_offset
        while i < len(result):
            if i >= len(result):
                break

            # Read name length (in words)
            name_len = result[i]
            i += 1

            # Skip over the name bytes (name_len * 2 bytes for 16-bit words)
            i += name_len * 2

            # Now process properties until terminator (0x00)
            while i < len(result) and result[i] != 0x00:
                size_byte = result[i]
                i += 1

                if self.version <= 3:
                    # V1-3: size byte = 32 * (len - 1) + prop_num
                    data_len = (size_byte >> 5) + 1
                else:
                    # V4+: more complex encoding
                    if size_byte & 0x80:
                        # Two size bytes
                        if i >= len(result):
                            break
                        size_byte2 = result[i]
                        i += 1
                        data_len = size_byte2 & 0x3F
                        if data_len == 0:
                            data_len = 64  # Special case
                    else:
                        # Single size byte
                        data_len = 2 if (size_byte & 0x40) else 1

                # Scan property DATA for placeholders (aligned to 2-byte boundaries)
                prop_end = i + data_len
                j = i
                while j + 1 < prop_end and j + 1 < len(result):
                    word = (result[j] << 8) | result[j + 1]

                    # Check for SYNONYM placeholder: 0x8000 | word_offset
                    if (word & 0xF000) == 0x8000:
                        word_offset = word & 0x0FFF
                        actual_addr = dict_addr + word_offset
                        result[j] = (actual_addr >> 8) & 0xFF
                        result[j + 1] = actual_addr & 0xFF
                        j += 2
                    # Check for ADJECTIVE placeholder: 0xFE00 | word_offset
                    elif (word & 0xFF00) == 0xFE00:
                        word_offset = word & 0x00FF
                        actual_addr = dict_addr + word_offset
                        result[j] = (actual_addr >> 8) & 0xFF
                        result[j + 1] = actual_addr & 0xFF
                        j += 2
                    # Check for VOC placeholder from PROPDEF: 0xFB00 | placeholder_idx
                    elif (word & 0xFF00) == 0xFB00:
                        placeholder_idx = word & 0x00FF
                        if placeholder_idx in vocab_lookup:
                            word_offset = vocab_lookup[placeholder_idx]
                            actual_addr = dict_addr + word_offset
                            result[j] = (actual_addr >> 8) & 0xFF
                            result[j + 1] = actual_addr & 0xFF
                        j += 2
                    else:
                        j += 2  # Move by words in property data

                i = prop_end

            # Skip terminator
            if i < len(result) and result[i] == 0x00:
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
                        string_placeholders: dict = None,
                        tell_string_placeholders: dict = None,
                        tell_placeholder_positions: list = None,
                        vocab_fixups: list = None,
                        tchars_table_idx: int = None) -> bytes:
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
            string_placeholders: Dict mapping placeholder index to string text for operand resolution (0xFC format)
            tell_string_placeholders: Dict mapping placeholder index to string text for TELL resolution (0x8D format)
            tell_placeholder_positions: List of (byte_offset, placeholder_idx) for position-based TELL resolution
            vocab_fixups: List of (placeholder_idx, word_offset) for W?* vocabulary word resolution
            tchars_table_idx: Table index for TCHARS constant (terminating characters, header 0x2E)

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

        # NOW we know where tables will be placed
        table_base_addr = calc_addr

        # Pre-calculate dictionary address for VOCAB global resolution
        # Dictionary comes after: tables, extension table (V5+)
        dict_addr_precalc = table_base_addr
        if table_data:
            dict_addr_precalc += len(table_data)
            if dict_addr_precalc % 2 != 0:
                dict_addr_precalc += 1  # Account for alignment
        if extension_table and self.version >= 5:
            dict_addr_precalc += len(extension_table)
            if dict_addr_precalc % 2 != 0:
                dict_addr_precalc += 1

        # Patch globals_data with actual table addresses and VOCAB
        globals_data = self._resolve_table_placeholders(
            globals_data, table_base_addr, table_offsets, dict_addr_precalc
        )

        globals_addr = current_addr
        globals_len = len(globals_data)
        story.extend(globals_data)
        current_addr += globals_len

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
            # Dictionary is in static memory: after objects, tables, and extension table
            objects_end = current_addr + len(objects_fixed)
            if objects_end % 2 != 0:
                objects_end += 1  # Account for padding
            # Add table_data size
            dict_addr_calc = objects_end
            if table_data:
                dict_addr_calc += len(table_data)
                if dict_addr_calc % 2 != 0:
                    dict_addr_calc += 1
            # Add extension_table size (V5+)
            if extension_table and self.version >= 5:
                dict_addr_calc += len(extension_table)
                if dict_addr_calc % 2 != 0:
                    dict_addr_calc += 1

            # Resolve dictionary word placeholders in property tables BEFORE
            # fixing up property table addresses (since the resolver uses relative offsets)
            # Placeholders are marked with 0x8000 bit set (SYNONYM), 0xFE00 (ADJECTIVE),
            # or 0xFB00 (VOC from PROPDEF) - the low bits contain word offset or index
            objects_fixed = bytearray(self._resolve_dict_placeholders(
                bytes(objects_fixed), dict_addr_calc, prop_defaults_size, vocab_fixups
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

        # Add table data in dynamic memory (before static memory)
        # Tables need to be writable, so they go in dynamic memory
        table_base_addr = current_addr
        table_data_start = 0  # Track position for later string placeholder resolution
        table_data_len = 0

        if table_data:
            # Calculate dictionary address for resolving vocab placeholders in tables
            dict_addr_for_tables = current_addr + len(table_data)
            if dict_addr_for_tables % 2 != 0:
                dict_addr_for_tables += 1  # Account for alignment
            # Add extension table size (V5+)
            if extension_table and self.version >= 5:
                dict_addr_for_tables += len(extension_table)
                if dict_addr_for_tables % 2 != 0:
                    dict_addr_for_tables += 1

            # Resolve vocabulary word placeholders in table data
            if vocab_fixups:
                table_data = self._resolve_table_vocab_placeholders(
                    table_data, vocab_fixups, dict_addr_for_tables
                )

            # Track table data position for later string placeholder resolution
            table_data_start = len(story)
            table_data_len = len(table_data)
            story.extend(table_data)
            current_addr += len(table_data)

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Add extension table (V5+) in dynamic memory
        extension_table_addr = 0
        if self.version >= 5:
            extension_table_addr = current_addr
            if extension_table:
                story.extend(extension_table)
                current_addr += len(extension_table)
            else:
                # Minimal extension table: 2 bytes with 0 entries
                # (needed for bocfel which reads entry count even when addr=0)
                story.extend([0, 0])
                current_addr += 2

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Static memory starts after tables and extension table (in dynamic memory)
        self.static_mem_base = current_addr

        # Add dictionary in static memory (read-only)
        dict_addr = current_addr
        if dictionary:
            story.extend(dictionary)
            current_addr += len(dictionary)

        # Resolve vocab placeholders in globals data now that dict_addr is known
        # (vocab placeholders are 0xFB00 | index, need to be patched to actual addresses)
        if vocab_fixups and globals_len > 0:
            self._resolve_vocab_placeholders_in_story(
                story, vocab_fixups, dict_addr, globals_addr, globals_len
            )

        # Align to even boundary
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

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

        # For V6-7, add padding so first routine is at packed address 1, not 0
        # (some interpreters like bocfel reject packed address 0 as invalid)
        # The padding goes AFTER high_mem_base, so routines_offset calculation stays correct
        if self.version in (6, 7):
            for _ in range(4):  # 4 bytes = packed address offset of 1
                story.append(0)
            # Don't update high_mem_base - routines_offset needs the original value

        # Resolve table routine fixups (for ACTIONS table packed addresses)
        # Now that we know high_mem_base, patch table data with routine addresses
        if table_routine_fixups and table_data:
            for table_offset, routine_offset in table_routine_fixups:
                # Calculate actual byte address of routine
                actual_addr = self.high_mem_base + routine_offset

                # Convert to packed address based on version
                if self.version <= 3:
                    packed_addr = actual_addr // 2
                elif self.version <= 5:
                    packed_addr = actual_addr // 4
                elif self.version <= 7:
                    # V6-7 use routines_offset, with 4-byte padding before first routine
                    packed_addr = (4 + routine_offset) // 4
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
            # For V6-7, add 4 bytes for padding before routines
            padding = 4 if self.version in (6, 7) else 0
            string_table_base = self.high_mem_base + padding + final_routines_len

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

            # For V6-7, also set the strings_offset for packed address calculation
            if self.version in (6, 7):
                strings_offset = self.high_mem_base // 8
                string_table.set_strings_offset(strings_offset)

            # Now resolve string table markers with correct addresses
            # Pass tell_string_placeholders and positions to handle the 0x8D format (TELL strings)
            # Using position-based resolution to avoid false matches when 0x8D appears as operand data
            routines = self._resolve_string_markers(
                routines, string_table, tell_string_placeholders, tell_placeholder_positions
            )

            # Resolve string operand placeholders (0xFC00 | index -> packed address)
            if string_placeholders:
                routines = self._resolve_string_placeholders(
                    routines, string_placeholders, string_table
                )

            # Also resolve string placeholders in table data (for LONG-WORD-TABLE)
            if string_placeholders and table_data_len > 0:
                self._resolve_string_placeholders_in_story(
                    story, string_placeholders, string_table,
                    table_data_start, table_data_len
                )

        # Resolve routine call fixups (patch call addresses)
        if routine_fixups:
            routines = self._resolve_routine_fixups(routines, routine_fixups)

        # Resolve vocabulary word placeholders (W?* -> dictionary addresses)
        if vocab_fixups:
            routines = self._resolve_vocab_placeholders(routines, vocab_fixups, dict_addr)

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

        # Calculate Initial PC - points to first instruction to execute, not routine header
        # Per Z-machine spec: "Byte address of first instruction to execute" (V1-5)
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
            initial_pc = 1  # Packed address of first routine (after 4-byte padding)

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

        # V5+ TCHARS (terminating characters table) address at 0x2E
        if self.version >= 5 and tchars_table_idx is not None and tchars_table_idx in table_offsets:
            tchars_addr = table_base_addr + table_offsets[tchars_table_idx]
            struct.pack_into('>H', story, 0x2E, tchars_addr)

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
