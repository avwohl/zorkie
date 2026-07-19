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
            elif ((0xFF00 <= word <= 0xFFFF) or (0xF800 <= word <= 0xF8FF)) and table_offsets:
                # 0xF800|(idx-256): ext band for table indexes 256..511
                table_index = (word & 0x00FF) + (0x100 if (word & 0xFF00) == 0xF800 else 0)
                if table_index in table_offsets:
                    # Calculate actual table address
                    actual_addr = table_base_addr + table_offsets[table_index]
                    # Write back as big-endian
                    result[i] = (actual_addr >> 8) & 0xFF
                    result[i + 1] = actual_addr & 0xFF

        return bytes(result)

    def _resolve_table_placeholders_split(self, data: bytes,
                                           impure_base_addr: int,
                                           pure_base_addr: int,
                                           table_offsets: dict,
                                           impure_tables_size: int,
                                           dict_addr: int = None) -> bytes:
        """
        Resolve table address placeholders with split impure/pure table bases.

        Like _resolve_table_placeholders but handles the case where impure tables
        are at a different base address than pure tables.

        Args:
            data: Bytes to scan (typically globals_data)
            impure_base_addr: Base address for impure tables (dynamic memory)
            pure_base_addr: Base address for pure tables (static memory)
            table_offsets: Dict mapping table index to offset within sorted table data
            impure_tables_size: Byte offset where pure tables start in the sorted data
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
            elif ((0xFF00 <= word <= 0xFFFF) or (0xF800 <= word <= 0xF8FF)) and table_offsets:
                # 0xF800|(idx-256): ext band for table indexes 256..511
                table_index = (word & 0x00FF) + (0x100 if (word & 0xFF00) == 0xF800 else 0)
                if table_index in table_offsets:
                    offset = table_offsets[table_index]
                    # Determine which section this table is in
                    if offset < impure_tables_size:
                        # Impure table: in dynamic memory
                        actual_addr = impure_base_addr + offset
                    else:
                        # Pure table: in static memory
                        actual_addr = pure_base_addr + (offset - impure_tables_size)
                    # Write back as big-endian
                    result[i] = (actual_addr >> 8) & 0xFF
                    result[i + 1] = actual_addr & 0xFF

        return bytes(result)

    def _resolve_string_markers(self, routines: bytes, string_table,
                                   string_placeholders: dict = None,
                                   placeholder_positions: list = None,
                                   patched_positions: set = None) -> bytes:
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
                        if patched_positions is not None:
                            patched_positions.add(byte_offset + 1)
                            patched_positions.add(byte_offset + 2)
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
                                       string_table,
                                       code_index_max: int = None,
                                       patched_positions: set = None) -> bytes:
        """
        Resolve string operand placeholders in routine bytecode.

        Scans bytecode for 0xFC00 | index values and replaces them with actual
        packed string addresses.

        This scan is position-blind, and 0xFC is a common HIGH byte of backward
        JUMP offsets (-769..-1024). Two guards keep it from rewriting real code:
        * code_index_max: only indices in the ROUTINE-code namespace (an
          ascending prefix; data-region markers allocate from 255 down) are
          accepted. A jump offset byte pairing with a data index (e.g. 0xFC9D
          in minizork's CLAUSE loop) is rejected outright.
        * a match immediately preceded by the JUMP opcode 0x8C is skipped --
          that byte is a jump offset, never a string operand.

        Args:
            routines: Routine bytecode with string placeholders
            string_placeholders: Dict mapping placeholder index to string text
            string_table: StringTable instance with resolved addresses
            code_index_max: exclusive upper bound of routine-code marker indices

        Returns:
            Patched routine bytecode
        """
        if not string_placeholders or string_table is None:
            return routines

        result = bytearray(routines)

        # Scan for 0xFC00 | index patterns (16-bit values). Match against the
        # PRISTINE input and skip bytes earlier passes already wrote (a resolved
        # marker address from _resolve_string_markers can contain 0xFC).
        protected = patched_positions if patched_positions is not None else set()
        i = 0
        while i < len(result) - 1:
            # Check for 0xFC high byte
            if routines[i] == 0xFC and i not in protected:
                placeholder_idx = routines[i + 1]
                # A JUMP (0x8C) offset can contain 0xFC in either byte: as the
                # HIGH byte of a backward jump (0x8C directly before the match)
                # or as the LOW byte of a forward jump (0x8C two bytes back,
                # e.g. zork1's `jump #02fc` in MAIN-LOOP-1) -- skip both.
                if ((placeholder_idx in string_placeholders)
                        and (code_index_max is None or placeholder_idx < code_index_max)
                        and not (i >= 1 and routines[i - 1] == 0x8C)
                        and not (i >= 2 and routines[i - 2] == 0x8C)):
                    text = string_placeholders[placeholder_idx]
                    # Get packed address from string table
                    packed_addr = string_table.get_packed_address(text, self.version)
                    if packed_addr is not None:
                        # Patch the 16-bit address
                        result[i] = (packed_addr >> 8) & 0xFF
                        result[i + 1] = packed_addr & 0xFF
                        protected.add(i)
                        protected.add(i + 1)
                        i += 2
                        continue
            i += 1

        return bytes(result)

    def _resolve_string_placeholders_in_story(self, story: bytearray,
                                               string_placeholders: dict,
                                               string_table,
                                               start_offset: int,
                                               length: int,
                                               step: int = 2,
                                               data_placeholders: dict = None,
                                               skip_positions: set = None) -> None:
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
        if not string_placeholders or string_table is None or length == 0:
            return

        # Scan for 0xFC00 | index patterns (16-bit values).
        #
        # step=2 (globals table): slots are word-aligned from the even
        # start_offset, so a 0xFC00|idx marker's high byte is always at an EVEN
        # position. Scanning word-aligned avoids matching a 0xFC that is merely
        # the LOW byte of an already-resolved table address (P-OTBL legitimately
        # resolved to 0x20FC; a byte-blind scan misread it as a placeholder and
        # clobbered P-VTBL to 0xF010 -> "Store out of dynamic memory").
        #
        # step=1 (table data): tables of mixed byte/word layout make region-wide
        # word alignment meaningless, so scan byte-by-byte there and skip past
        # both bytes of each patched marker.
        end_offset = min(start_offset + length, len(story) - 1)
        data_ph = data_placeholders or {}
        _skip = skip_positions or set()
        i = start_offset
        while i < end_offset:
            if i in _skip:
                i += step
                continue
            hi = story[i]
            text = None
            # Code-namespace marker (0xFC00|idx) or data-namespace marker
            # (0xF400|id, high bytes 0xF4-0xF7 carrying the id's top 2 bits).
            # The data band is only matched in WORD-ALIGNED regions (globals):
            # a byte-stepped scan over table data rewrote packed routine
            # addresses whose LOW byte was 0xF4-0xF7 (ACTIONS[V?PRAY]=0x46F4).
            if hi == 0xFC:
                text = string_placeholders.get(story[i + 1])
            elif 0xF4 <= hi <= 0xF7 and step == 2:
                text = data_ph.get(((hi & 0x03) << 8) | story[i + 1])
            elif 0xF0 <= hi <= 0xF3 and step == 2:
                # ext data-string marker (band overflow); value-keyed dict,
                # cannot collide with routine placeholders (disjoint pools)
                text = (getattr(self, '_string_data_ext', {}) or {}).get(
                    (hi << 8) | story[i + 1])
            if text is not None:
                packed_addr = string_table.get_packed_address(text, self.version)
                if packed_addr is not None:
                    story[i] = (packed_addr >> 8) & 0xFF
                    story[i + 1] = packed_addr & 0xFF
                    i += 2
                    continue
            i += step

    def _structural_positions(self, blob):
        """(allowed_positions, fallback_ranges) for the routines blob via the
        codegen instruction walker, or (None, None) when structure is
        unavailable. Positions gate the 0xFB scans STRUCTURALLY: only a 2-byte
        large-constant operand may hold a vocab placeholder (an infidel call
        placeholder's argument bytes previously false-matched)."""
        offs_map = getattr(self, '_routine_offsets_map', None)
        code_len = getattr(self, '_codegen_code_len', None)
        if not offs_map or code_len is None or code_len != len(blob):
            return None, None
        from ..codegen.codegen_improved import (_walk_large_const_positions,
                                                _PlaceholderScanDesync)
        offs = sorted(set(offs_map.values()))
        if not offs:
            return None, None
        allowed = set()
        fallback = []
        n = len(blob)
        for idx, r in enumerate(offs):
            if r >= n:
                continue
            end = offs[idx + 1] if idx + 1 < len(offs) else n
            nl = blob[r]
            cs = r + 1 + (2 * nl if self.version <= 4 else 0)
            if nl > 15 or cs > end:
                fallback.append((r, end))
                continue
            chunk = bytes(blob[cs:end])
            try:
                pos = _walk_large_const_positions(chunk, self.version)
            except _PlaceholderScanDesync:
                try:
                    pos = _walk_large_const_positions(chunk.rstrip(b'\x00'), self.version)
                except _PlaceholderScanDesync:
                    fallback.append((cs, end))
                    continue
            for p in pos:
                allowed.add(cs + p)
        return allowed, fallback

    @staticmethod
    def _structural_pos_ok(i, allowed, fallback):
        if i in allowed:
            return True
        for a, b in fallback:
            if a <= i < b:
                return True
        return False

    def _resolve_vocab_placeholders(self, routines, vocab_fixups, dict_addr,
                                    protected_positions=None):
        if not vocab_fixups:
            return routines
        allowed, fallback = self._structural_positions(routines)
        if allowed is None:
            return self._resolve_vocab_placeholders_legacy(
                routines, vocab_fixups, dict_addr, protected_positions)
        result = bytearray(routines)
        protected = protected_positions if protected_positions is not None else set()
        fixup_map = {}
        for placeholder_idx, word_offset in vocab_fixups:
            fixup_map[placeholder_idx] = dict_addr + word_offset
        i = 0
        while i < len(result) - 1:
            if (routines[i] == 0xFB and i not in protected
                    and self._structural_pos_ok(i, allowed, fallback)
                    and not (i >= 1 and routines[i - 1] == 0x8C)
                    and not (i >= 2 and routines[i - 2] == 0x8C)):
                placeholder_idx = routines[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    result[i] = (word_addr >> 8) & 0xFF
                    result[i + 1] = word_addr & 0xFF
                    protected.add(i)
                    protected.add(i + 1)
                    i += 2
                    continue
            i += 1
        return bytes(result)

    def _resolve_vword_placeholders(self, routines, vword_fixups, table_base_addr,
                                    table_offsets, protected_positions=None):
        if not vword_fixups:
            return routines
        allowed, fallback = self._structural_positions(routines)
        if allowed is None:
            return self._resolve_vword_placeholders_legacy(
                routines, vword_fixups, table_base_addr, table_offsets,
                protected_positions)
        result = bytearray(routines)
        protected = protected_positions if protected_positions is not None else set()
        fixup_map = {}
        for placeholder_idx, table_index in vword_fixups:
            if table_index in table_offsets:
                fixup_map[placeholder_idx] = table_base_addr + table_offsets[table_index]
        i = 0
        while i < len(result) - 1:
            if (routines[i] == 0xFB and i not in protected
                    and self._structural_pos_ok(i, allowed, fallback)
                    and not (i >= 1 and routines[i - 1] == 0x8C)
                    and not (i >= 2 and routines[i - 2] == 0x8C)):
                placeholder_idx = routines[i + 1]
                if placeholder_idx in fixup_map:
                    table_addr = fixup_map[placeholder_idx]
                    result[i] = (table_addr >> 8) & 0xFF
                    result[i + 1] = table_addr & 0xFF
                    protected.add(i)
                    protected.add(i + 1)
                    i += 2
                    continue
            i += 1
        return bytes(result)

    def _resolve_vocab_placeholders_legacy(self, routines: bytes, vocab_fixups: list,
                                       dict_addr: int, protected_positions: set = None) -> bytes:
        """
        Resolve vocabulary word placeholders (W?*) in routine bytecode.

        Scans bytecode for 0xFB00 | index values and replaces them with actual
        dictionary word addresses.

        Args:
            routines: Routine bytecode with vocab placeholders
            vocab_fixups: List of (placeholder_idx, word_offset) tuples
            dict_addr: Base address of dictionary in story file
            protected_positions: Byte offsets already resolved as routine-call
                operands. This scan is position-BLIND, so a routine whose packed
                address happens to contain 0xFB (e.g. LIT? at packed 0x39FB) would
                otherwise have that byte misread as a vocab placeholder and
                clobbered, silently redirecting every call to it. Skipping the
                bytes routine fixups already wrote prevents that collision.

        Returns:
            Patched routine bytecode
        """
        if not vocab_fixups:
            return routines

        result = bytearray(routines)
        protected = protected_positions if protected_positions is not None else set()

        # Build a map from placeholder_idx to word address
        fixup_map = {}
        for placeholder_idx, word_offset in vocab_fixups:
            # Word offset is relative to dictionary data start
            # Final address is dict_addr + word_offset
            word_addr = dict_addr + word_offset
            fixup_map[placeholder_idx] = word_addr

        # Scan for 0xFB00 | index patterns (16-bit values). Match against the
        # PRISTINE input (routines), never the partially patched result: a
        # resolved word address can itself contain 0xFB as its LOW byte (zork1's
        # '"' entry landed at dict 0x3EFB), and rescanning our own write made
        # the scanner read that 0xFB plus the following je branch byte as a
        # fresh placeholder, corrupting both the operand and the branch.
        # Patched positions join `protected` so the vword pass below can't
        # misread the bytes this pass wrote.
        i = 0
        while i < len(result) - 1:
            # Skip 0xFB bytes that are JUMP (0x8C) offset bytes, not
            # placeholders (either byte of the 16-bit offset can be 0xFB).
            if (routines[i] == 0xFB and i not in protected
                    and not (i >= 1 and routines[i - 1] == 0x8C)
                    and not (i >= 2 and routines[i - 2] == 0x8C)):
                placeholder_idx = routines[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    result[i] = (word_addr >> 8) & 0xFF
                    result[i + 1] = word_addr & 0xFF
                    protected.add(i)
                    protected.add(i + 1)
                    i += 2
                    continue
            i += 1

        return bytes(result)

    def _resolve_vword_placeholders_legacy(self, routines: bytes, vword_fixups: list,
                                     table_base_addr: int, table_offsets: dict,
                                     protected_positions: set = None) -> bytes:
        """
        Resolve VWORD table placeholders (W?*) in routine bytecode.

        Similar to _resolve_vocab_placeholders, but resolves to table addresses
        instead of dictionary addresses. Used in NEW-PARSER? mode.

        Args:
            routines: Routine bytecode with vocab placeholders
            vword_fixups: List of (placeholder_idx, table_index) tuples
            table_base_addr: Base address where tables are placed in memory
            table_offsets: Dict mapping table index to offset within table data

        Returns:
            Patched routine bytecode
        """
        if not vword_fixups:
            return routines

        result = bytearray(routines)
        protected = protected_positions if protected_positions is not None else set()

        # Build a map from placeholder_idx to VWORD table address
        fixup_map = {}
        for placeholder_idx, table_index in vword_fixups:
            if table_index in table_offsets:
                table_addr = table_base_addr + table_offsets[table_index]
                fixup_map[placeholder_idx] = table_addr

        # Scan for 0xFB00 | index patterns (16-bit values). Skip bytes already
        # written as routine-call or vocab operands, match against the pristine
        # input, and never rescan a just-written low byte (see
        # _resolve_vocab_placeholders for the zork1 0x3EFB collision).
        i = 0
        while i < len(result) - 1:
            if (routines[i] == 0xFB and i not in protected
                    and not (i >= 1 and routines[i - 1] == 0x8C)
                    and not (i >= 2 and routines[i - 2] == 0x8C)):
                placeholder_idx = routines[i + 1]
                if placeholder_idx in fixup_map:
                    table_addr = fixup_map[placeholder_idx]
                    result[i] = (table_addr >> 8) & 0xFF
                    result[i + 1] = table_addr & 0xFF
                    protected.add(i)
                    protected.add(i + 1)
                    i += 2
                    continue
            i += 1

        return bytes(result)

    def _resolve_table_vocab_placeholders(self, table_data: bytes,
                                           vocab_fixups: list,
                                           dict_addr: int,
                                           protected_positions: set = None) -> bytes:
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
        protected = protected_positions if protected_positions is not None else set()

        # Build a map from placeholder_idx to word address
        fixup_map = {}
        for placeholder_idx, word_offset in vocab_fixups:
            word_addr = dict_addr + word_offset
            fixup_map[placeholder_idx] = word_addr

        # Only indices actually EMITTED into table data may match here.
        # Code-emitted indices are resolved by the code passes; letting them
        # match table bytes turned CPEXITS's '-5, P?NW' word pair into a
        # dictionary address (zork3 Royal Puzzle).
        _tv = getattr(self, '_table_vocab_indices', None)
        if _tv is not None:
            fixup_map = {k: v for k, v in fixup_map.items() if k in _tv}

        # Scan for 0xFB00 | index patterns against the PRISTINE input, skipping
        # positions the vword pass already patched, and never rescanning our own
        # writes (see _resolve_vocab_placeholders for the 0x3EFB collision).
        i = 0
        while i < len(result) - 1:
            if table_data[i] == 0xFB and i not in protected:
                placeholder_idx = table_data[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    result[i] = (word_addr >> 8) & 0xFF
                    result[i + 1] = word_addr & 0xFF
                    protected.add(i)
                    protected.add(i + 1)
                    i += 2
                    continue
            i += 1

        return bytes(result)

    def _resolve_table_vword_placeholders(self, table_data: bytes,
                                          vword_fixups: list,
                                          table_base_addr: int,
                                          table_offsets: dict,
                                          protected_positions: set = None) -> bytes:
        """
        Resolve VWORD table placeholders in table data.

        Similar to _resolve_table_vocab_placeholders, but resolves to VWORD
        table addresses instead of dictionary addresses. Used in NEW-PARSER? mode.

        Args:
            table_data: Table data with vocab placeholders
            vword_fixups: List of (placeholder_idx, table_index) tuples
            table_base_addr: Base address of tables in story file
            table_offsets: Dict of table_index -> offset from table_base_addr

        Returns:
            Patched table data
        """
        if not vword_fixups or not table_data:
            return table_data

        result = bytearray(table_data)
        protected = protected_positions if protected_positions is not None else set()

        # Build a map from placeholder_idx to VWORD table address
        fixup_map = {}
        for placeholder_idx, table_index in vword_fixups:
            if table_index in table_offsets:
                table_addr = table_base_addr + table_offsets[table_index]
                fixup_map[placeholder_idx] = table_addr

        # Scan for 0xFB00 | index patterns against the PRISTINE input and never
        # rescan our own writes (see _resolve_vocab_placeholders).
        i = 0
        while i < len(result) - 1:
            if table_data[i] == 0xFB and i not in protected:
                placeholder_idx = table_data[i + 1]
                if placeholder_idx in fixup_map:
                    table_addr = fixup_map[placeholder_idx]
                    result[i] = (table_addr >> 8) & 0xFF
                    result[i + 1] = table_addr & 0xFF
                    protected.add(i)
                    protected.add(i + 1)
                    i += 2
                    continue
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

        # Scan for 0xFB00 | index patterns. WORD-ALIGNED: the globals region is
        # 2-byte slots, and a byte-blind scan matched the LOW byte of an
        # already-resolved table address (OOPS-INBUF's 0x1FFB) and rewrote it to
        # a dictionary address, shrinking the OOPS buffer pointer so the input
        # buffer copy overran into P-INBUF and every 2nd command read empty.
        end_offset = min(start_offset + length, len(story) - 1)
        i = start_offset
        while i < end_offset:
            if story[i] == 0xFB:
                placeholder_idx = story[i + 1]
                if placeholder_idx in fixup_map:
                    word_addr = fixup_map[placeholder_idx]
                    story[i] = (word_addr >> 8) & 0xFF
                    story[i + 1] = word_addr & 0xFF
            i += 2

    def _resolve_vword_placeholders_in_story(self, story: bytearray,
                                              vword_fixups: list,
                                              table_base_addr: int,
                                              table_offsets: dict,
                                              start_offset: int,
                                              length: int) -> None:
        """
        Resolve VWORD table placeholders in a section of the story file.

        Similar to _resolve_vocab_placeholders_in_story, but resolves to
        table addresses instead of dictionary addresses. Used in NEW-PARSER? mode.

        Args:
            story: Story bytearray to modify in place
            vword_fixups: List of (placeholder_idx, table_index) tuples
            table_base_addr: Base address where tables are placed in memory
            table_offsets: Dict mapping table index to offset within table data
            start_offset: Start offset in story to scan
            length: Number of bytes to scan
        """
        if not vword_fixups:
            return

        # Build a map from placeholder_idx to VWORD table address
        fixup_map = {}
        for placeholder_idx, table_index in vword_fixups:
            if table_index in table_offsets:
                table_addr = table_base_addr + table_offsets[table_index]
                fixup_map[placeholder_idx] = table_addr

        # Scan for 0xFB00 | index patterns (16-bit values)
        end_offset = min(start_offset + length, len(story) - 1)
        i = start_offset
        while i < end_offset:
            if story[i] == 0xFB:
                placeholder_idx = story[i + 1]
                if placeholder_idx in fixup_map:
                    table_addr = fixup_map[placeholder_idx]
                    story[i] = (table_addr >> 8) & 0xFF
                    story[i + 1] = table_addr & 0xFF
            i += 1

    def _resolve_dict_placeholders(self, objects_data: bytes, dict_addr: int,
                                     prop_defaults_size: int,
                                     vocab_fixups: list = None,
                                     dir_prop_min: int = None,
                                     prop_dict_fixups: list = None) -> bytes:
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

        # POSITIONAL dict-word patches (obj_num, prop_num, byte_off,
        # word_offset), recorded at emission. These replace the SYNONYM marker
        # scan entirely: in-band 0x8000|offset markers both truncated large
        # dictionaries (zork1) and false-matched neighboring object-number
        # bytes (minizork's GLOBAL prop 9a 8f).
        if prop_dict_fixups:
            obj_entry_sz = 9 if self.version <= 3 else 14
            for obj_idx, prop_num, byte_off, word_offset in prop_dict_fixups:
                # obj_idx is the 0-based object index from the compiler's
                # emission loop (object number minus 1).
                entry = prop_defaults_size + obj_idx * obj_entry_sz
                ptr_at = entry + obj_entry_sz - 2
                if ptr_at + 1 >= len(result):
                    continue
                pt = (result[ptr_at] << 8) | result[ptr_at + 1]
                if pt >= len(result):
                    continue
                p = pt + 1 + 2 * result[pt]  # skip short-name
                while p < len(result) and result[p] != 0:
                    sz = result[p]
                    if self.version <= 3:
                        dlen = (sz >> 5) + 1
                        pn = sz & 0x1F
                        p += 1
                    else:
                        if sz & 0x80:
                            dlen = result[p + 1] & 0x3F or 64
                            pn = sz & 0x3F
                            p += 2
                        else:
                            dlen = 2 if (sz & 0x40) else 1
                            pn = sz & 0x3F
                            p += 1
                    if pn == prop_num:
                        j = p + byte_off
                        if j + 1 < len(result):
                            addr = dict_addr + word_offset
                            result[j] = (addr >> 8) & 0xFF
                            result[j + 1] = addr & 0xFF
                        break
                    p += dlen

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
                # Direction (exit) properties hold raw room/object/flag bytes, not
                # dict-word placeholders. A CEXIT like [room=0x8n, flag#] forms a
                # word that LOOKS like a 0x8000|offset SYNONYM marker and would be
                # rewritten to a dictionary address, corrupting the exit. Skip them.
                if (dir_prop_min is not None and self.version <= 3
                        and (size_byte & 0x1F) >= dir_prop_min):
                    i = prop_end
                    continue
                j = i
                while j + 1 < prop_end and j + 1 < len(result):
                    word = (result[j] << 8) | result[j + 1]

                    # Check for SYNONYM placeholder: 0x8000 | word_offset.
                    # Skipped when positional prop_dict_fixups were supplied --
                    # those patches are authoritative and scanning is both
                    # truncation-prone and false-positive-prone.
                    if (word & 0xF000) == 0x8000 and not prop_dict_fixups:
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

    def _resolve_string_placeholders_in_properties(self, story: bytearray,
                                                    objects_addr: int,
                                                    objects_len: int,
                                                    prop_defaults_size: int,
                                                    string_placeholders: dict,
                                                    string_table,
                                                    data_placeholders: dict = None) -> None:
        """Resolve 0xFC00|idx string markers inside object PROPERTY data.

        Classic direction exits (NEXIT/CEXIT/DEXIT) embed the packed address of
        their refusal message in the property; the marker can only be resolved
        after the string table is placed, so this walks the property tables in
        the assembled story (addresses already absolute) and patches in place.
        """
        if not string_placeholders or string_table is None:
            return

        data_ph = data_placeholders or {}

        def patch(j):
            hi = story[j]
            if hi == 0xFC:
                text = string_placeholders.get(story[j + 1])
            elif 0xF4 <= hi <= 0xF7:
                text = data_ph.get(((hi & 0x03) << 8) | story[j + 1])
            elif 0xF0 <= hi <= 0xF3:
                text = (getattr(self, '_string_data_ext', {}) or {}).get(
                    (hi << 8) | story[j + 1])
            else:
                return None
            if text is None:
                return None
            return string_table.get_packed_address(text, self.version)

        self._walk_property_data(story, objects_addr, objects_len,
                                 prop_defaults_size, patch)

    def _walk_property_data(self, story: bytearray, objects_addr: int,
                            objects_len: int, prop_defaults_size: int,
                            patch_fn) -> None:
        """Walk every object's property DATA (never names, entries, or defaults)
        and let patch_fn replace 16-bit marker words.

        patch_fn(j) inspects story[j], story[j+1] (a word-aligned position within
        one property's data) and returns a 16-bit value to write there, or None.
        Walking per-object via each entry's own table pointer is the ONLY safe
        iteration: sequential region scans desync on layout and byte-blind scans
        rewrite entry pointers / name z-text whose bytes look like markers.
        """
        obj_entry_size = 9 if self.version <= 3 else 14
        region_end = min(objects_addr + objects_len, len(story))
        entries_base = objects_addr + prop_defaults_size
        first_prop = entries_base + obj_entry_size - 2
        if first_prop + 2 > len(story):
            return
        lowest_table = (story[first_prop] << 8) | story[first_prop + 1]
        num_objects = max(0, (lowest_table - entries_base) // obj_entry_size)
        # Clamp: with no real objects the "first property pointer" is garbage.
        num_objects = min(num_objects, max(0, (region_end - entries_base) // obj_entry_size))
        for n in range(num_objects):
            pptr = entries_base + n * obj_entry_size + obj_entry_size - 2
            if pptr + 1 >= len(story):
                break
            i = (story[pptr] << 8) | story[pptr + 1]
            if not (objects_addr < i < region_end):
                continue
            name_len = story[i]
            i += 1 + name_len * 2
            while i < region_end and story[i] != 0x00:
                size_byte = story[i]
                i += 1
                if self.version <= 3:
                    data_len = (size_byte >> 5) + 1
                else:
                    if size_byte & 0x80:
                        data_len = story[i] & 0x3F or 64
                        i += 1
                    else:
                        data_len = 2 if (size_byte & 0x40) else 1
                j = i
                while j + 1 < i + data_len and j + 1 < region_end:
                    val = patch_fn(j)
                    if val is not None:
                        story[j] = (val >> 8) & 0xFF
                        story[j + 1] = val & 0xFF
                    j += 2
                i += data_len

    def _resolve_property_routine_placeholders(self, objects_data: bytes,
                                                property_routine_fixups: list,
                                                high_mem_base: int,
                                                prop_defaults_size: int) -> bytes:
        """
        Resolve routine address placeholders in object property tables.

        Scans property DATA for values marked with 0xFA00 prefix and replaces
        them with packed routine addresses.

        Args:
            objects_data: Object table data with property tables
            property_routine_fixups: List of (placeholder_idx, routine_byte_offset) tuples
            high_mem_base: Base address of high memory where routines start
            prop_defaults_size: Size of property defaults table in bytes

        Returns:
            Modified object data with routine addresses resolved
        """
        if not property_routine_fixups:
            return objects_data

        result = bytearray(objects_data)

        # Build lookup: placeholder_idx -> packed_routine_address
        fixup_map = {}
        for placeholder_idx, routine_offset in property_routine_fixups:
            # Calculate actual byte address of routine
            actual_addr = high_mem_base + routine_offset

            # Convert to packed address based on version
            if self.version <= 3:
                packed_addr = actual_addr // 2
            elif self.version <= 5:
                packed_addr = actual_addr // 4
            elif self.version <= 7:
                # V6-7 use routines_offset (assume 0 for now)
                packed_addr = actual_addr // 4
            else:
                packed_addr = actual_addr // 8

            fixup_map[placeholder_idx] = packed_addr

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

        # Scan property tables for 0xFA placeholders
        i = first_prop_offset
        while i < len(result) - 1:
            if i >= len(result):
                break

            # Check for property header (size/number byte)
            size_num = result[i]
            if size_num == 0x00:
                # End of properties for this object, move to next
                i += 1
                continue

            # Parse property header based on version
            if self.version <= 3:
                prop_size = ((size_num >> 5) & 0x07) + 1
                prop_start = i + 1
                prop_end = prop_start + prop_size
            else:
                if size_num & 0x80:
                    # Two-byte header
                    if i + 1 >= len(result):
                        break
                    size_byte = result[i + 1]
                    prop_size = size_byte & 0x3F
                    if prop_size == 0:
                        prop_size = 64
                    prop_start = i + 2
                else:
                    # One-byte header
                    prop_size = ((size_num >> 6) & 0x01) + 1
                    prop_start = i + 1
                prop_end = prop_start + prop_size

            # Scan property data for 0xFA placeholders (word-aligned)
            j = prop_start
            while j < prop_end - 1 and j < len(result) - 1:
                if result[j] == 0xFA:
                    placeholder_idx = result[j + 1]
                    if placeholder_idx in fixup_map:
                        packed_addr = fixup_map[placeholder_idx]
                        result[j] = (packed_addr >> 8) & 0xFF
                        result[j + 1] = packed_addr & 0xFF
                        j += 2  # Skip the word we just patched
                        continue
                j += 1

            i = prop_end

        return bytes(result)

    def _resolve_property_table_placeholders(self, objects_data: bytes,
                                              table_offsets: dict,
                                              tables_base: int,
                                              prop_defaults_size: int) -> bytes:
        """
        Resolve table address placeholders in object property tables.

        Scans property DATA for values marked with 0xFD00 prefix and replaces
        them with actual table addresses.

        Args:
            objects_data: Object table data with property tables
            table_offsets: Dict mapping table index to offset within table data
            tables_base: Base address of tables in story file
            prop_defaults_size: Size of property defaults table in bytes

        Returns:
            Modified object data with table addresses resolved
        """
        if not table_offsets:
            return objects_data

        result = bytearray(objects_data)

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

                # Scan property DATA for 0xFD00 table address placeholders
                prop_end = i + data_len
                j = i
                while j + 1 < prop_end and j + 1 < len(result):
                    word = (result[j] << 8) | result[j + 1]

                    # Check for table address placeholder: 0xFD00 | table_idx
                    # (0xF900|(idx-256) = ext band for prop-table idx 256..511)
                    if (word & 0xFF00) in (0xFD00, 0xF900):
                        table_idx = (word & 0x00FF) + (0x100 if (word & 0xFF00) == 0xF900 else 0)
                        if table_idx in table_offsets:
                            table_offset = table_offsets[table_idx]
                            actual_addr = tables_base + table_offset
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
                        tables_with_placeholders: list = None,
                        impure_tables_size: int = None,
                        routine_fixups: list = None,
                        table_routine_fixups: list = None,
                        property_routine_fixups: list = None,
                        extension_table: bytes = b'',
                        alphabet_table: bytes = b'',
                        string_placeholders: dict = None,
                        tell_string_placeholders: dict = None,
                        tell_placeholder_positions: list = None,
                        vocab_fixups: list = None,
                        vword_fixups: list = None,
                        tchars_table_idx: int = None,
                        dir_prop_min: int = None,
                        string_code_index_max: int = None,
                        string_data_placeholders: dict = None,
                        table_string_fixups: list = None,
                        table_addr_fixups: list = None,
                        prop_dict_fixups: list = None) -> bytes:
        """
        Build complete story file.

        Args:
            routines: Compiled routine bytecode
            objects: Object table data
            dictionary: Dictionary data
            globals_data: Global variables data
            abbreviations_table: AbbreviationsTable instance (optional)
            string_table: StringTable instance (optional, for deduplication)
            table_data: TABLE/LTABLE/ITABLE data (sorted: impure, parser, pure)
            table_offsets: Dict mapping table index to offset within table_data
            tables_with_placeholders: List of (start, end) byte ranges containing table address placeholders
            impure_tables_size: Size of impure tables section (dynamic memory).
                                Parser/pure tables start at this offset in static memory.
            routine_fixups: List of (code_offset, routine_offset) for call address patching
            table_routine_fixups: List of (table_offset, routine_offset) for table routine addresses
            property_routine_fixups: List of (placeholder_idx, routine_offset) for object property routine addresses
            extension_table: Header extension table bytes (V5+)
            string_placeholders: Dict mapping placeholder index to string text for operand resolution (0xFC format)
            tell_string_placeholders: Dict mapping placeholder index to string text for TELL resolution (0x8D format)
            tell_placeholder_positions: List of (byte_offset, placeholder_idx) for position-based TELL resolution
            vocab_fixups: List of (placeholder_idx, word_offset) for W?* vocabulary word resolution
            vword_fixups: List of (placeholder_idx, table_index) for NEW-PARSER? VWORD table resolution
            tchars_table_idx: Table index for TCHARS constant (terminating characters, header 0x2E)

        Returns:
            Complete story file as bytes
        """
        # Initialize table_offsets if not provided
        if table_offsets is None:
            table_offsets = {}

        # Initialize tables_with_placeholders if not provided
        if tables_with_placeholders is None:
            tables_with_placeholders = []

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

        # Calculate static memory base (where pure tables will be placed)
        # Layout: [impure tables] [extension table (V5+)] | STATIC_MEM_BASE | [pure tables] [dictionary]
        if impure_tables_size is None:
            impure_tables_size = len(table_data) if table_data else 0

        static_base_precalc = table_base_addr
        if table_data and impure_tables_size > 0:
            static_base_precalc += impure_tables_size
            if static_base_precalc % 2 != 0:
                static_base_precalc += 1  # Account for alignment
        if extension_table and self.version >= 5:
            static_base_precalc += len(extension_table)
            if static_base_precalc % 2 != 0:
                static_base_precalc += 1
        elif self.version >= 5:
            # Minimal extension table: 2 bytes
            static_base_precalc += 2
            if static_base_precalc % 2 != 0:
                static_base_precalc += 1

        # Pre-calculate dictionary address for VOCAB global resolution
        # Dictionary comes after: pure tables
        dict_addr_precalc = static_base_precalc
        pure_tables_size = len(table_data) - impure_tables_size if table_data else 0
        if pure_tables_size > 0:
            dict_addr_precalc += pure_tables_size
            if dict_addr_precalc % 2 != 0:
                dict_addr_precalc += 1

        # Patch globals_data with actual table addresses and VOCAB
        # For tables in the sorted data:
        # - Impure tables (offset < impure_tables_size): address = table_base_addr + offset
        # - Pure tables (offset >= impure_tables_size): address = static_base_precalc + (offset - impure_tables_size)
        globals_data = self._resolve_table_placeholders_split(
            globals_data, table_base_addr, static_base_precalc, table_offsets,
            impure_tables_size, dict_addr_precalc
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
                bytes(objects_fixed), dict_addr_calc, prop_defaults_size, vocab_fixups,
                dir_prop_min, prop_dict_fixups
            ))

            # Resolve table address placeholders (0xFD00 | table_idx) in property values
            if table_offsets:
                objects_fixed = bytearray(self._resolve_property_table_placeholders(
                    bytes(objects_fixed), table_offsets, table_base_addr, prop_defaults_size
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

        # Split table data into impure (dynamic memory) and pure (static memory)
        # Table layout: [impure tables] | STATIC_MEM_BASE | [parser tables] [pure tables] | [dictionary]
        if impure_tables_size is None:
            impure_tables_size = len(table_data) if table_data else 0

        impure_table_data = table_data[:impure_tables_size] if table_data else b''
        pure_table_data = table_data[impure_tables_size:] if table_data else b''

        # Add impure tables in dynamic memory (before static memory)
        table_base_addr = current_addr
        table_data_start = 0  # Track position for later string placeholder resolution
        table_data_len = 0
        impure_story_start = 0  # Story position where impure tables are added
        pure_story_start = 0    # Story position where pure tables are added

        if table_data:
            # Calculate dictionary address for resolving vocab placeholders in tables
            # Account for: impure tables + alignment + extension table + alignment + pure tables + alignment
            dict_addr_for_tables = current_addr + len(impure_table_data)
            if dict_addr_for_tables % 2 != 0:
                dict_addr_for_tables += 1  # Account for alignment
            # Add extension table size (V5+)
            if extension_table and self.version >= 5:
                dict_addr_for_tables += len(extension_table)
                if dict_addr_for_tables % 2 != 0:
                    dict_addr_for_tables += 1
            # Add pure tables size
            dict_addr_for_tables += len(pure_table_data)
            if pure_table_data and dict_addr_for_tables % 2 != 0:
                dict_addr_for_tables += 1

            # Resolve VWORD placeholders in table data first (NEW-PARSER? mode)
            # This must happen before vocab_fixups so vword placeholders get VWORD addresses
            # Positions either pass patches are shared so the second pass can't
            # misread a resolved address whose low byte is 0xFB.
            table_patched_positions = set()
            if vword_fixups and table_offsets:
                table_data = self._resolve_table_vword_placeholders(
                    table_data, vword_fixups, table_base_addr, table_offsets,
                    table_patched_positions
                )
                # Re-split after resolution
                impure_table_data = table_data[:impure_tables_size]
                pure_table_data = table_data[impure_tables_size:]

            # Resolve vocabulary word placeholders in table data (all tables)
            if vocab_fixups:
                table_data = self._resolve_table_vocab_placeholders(
                    table_data, vocab_fixups, dict_addr_for_tables,
                    table_patched_positions
                )
                # Re-split after resolution
                impure_table_data = table_data[:impure_tables_size]
                pure_table_data = table_data[impure_tables_size:]

            # Positional table-address fixups (VERBS -> syntax-entry blob):
            # patch the word at dst_table+dst_offset with the address of
            # src_table + addend. Positions recorded at encode time -- no
            # scanning, no 8-bit index limit.
            if table_addr_fixups and table_offsets:
                table_data = bytearray(table_data)
                for dst_idx, dst_off, src_idx, addend in table_addr_fixups:
                    if dst_idx not in table_offsets or src_idx not in table_offsets:
                        continue
                    pos = table_offsets[dst_idx] + dst_off
                    addr = table_base_addr + table_offsets[src_idx] + addend
                    if pos + 1 < len(table_data):
                        table_data[pos] = (addr >> 8) & 0xFF
                        table_data[pos + 1] = addr & 0xFF
                table_data = bytes(table_data)
                impure_table_data = table_data[:impure_tables_size]
                pure_table_data = table_data[impure_tables_size:]

            # Resolve table address placeholders within VERBS table data
            # (VERBS table contains pointers to syntax entry tables)
            # Only apply to tables known to contain placeholders to avoid corrupting
            # user data that happens to contain 0xFF bytes
            if table_offsets and tables_with_placeholders:
                # Only resolve for tables that explicitly contain placeholders
                for table_start, table_end in tables_with_placeholders:
                    if table_start < len(table_data):
                        segment = bytearray(table_data[table_start:table_end])
                        segment = self._resolve_table_placeholders(
                            segment, table_base_addr, table_offsets, dict_addr_for_tables
                        )
                        table_data = bytearray(table_data)
                        table_data[table_start:table_end] = segment
                        table_data = bytes(table_data)
                        # Re-split after resolution
                        impure_table_data = table_data[:impure_tables_size]
                        pure_table_data = table_data[impure_tables_size:]

            # Track table data position for later string placeholder resolution
            table_data_start = len(story)
            table_data_len = len(table_data)

            # Add impure tables to dynamic memory
            impure_story_start = len(story)
            if impure_table_data:
                story.extend(impure_table_data)
                current_addr += len(impure_table_data)

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Add alphabet table (V5+) in dynamic memory if custom alphabets are used
        alphabet_table_addr = 0
        if self.version >= 5 and alphabet_table:
            alphabet_table_addr = current_addr
            story.extend(alphabet_table)
            current_addr += len(alphabet_table)

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

                # Patch extension word 3 (Unicode table address) if present
                # Word 3 contains a relative offset that needs to be absolute
                if len(extension_table) >= 8:
                    # Get extension word count from word 0
                    ext_word_count = (extension_table[0] << 8) | extension_table[1]
                    if ext_word_count >= 3:
                        # Word 3 is at offset 6-7 (bytes 6-7)
                        rel_offset = (extension_table[6] << 8) | extension_table[7]
                        if rel_offset > 0:
                            # Convert relative offset to absolute address
                            abs_addr = extension_table_addr + rel_offset
                            story[extension_table_addr + 6] = (abs_addr >> 8) & 0xFF
                            story[extension_table_addr + 7] = abs_addr & 0xFF
            else:
                # Minimal extension table: 2 bytes with 0 entries
                # (needed for bocfel which reads entry count even when addr=0)
                story.extend([0, 0])
                current_addr += 2

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

        # Static memory starts after impure tables and extension table
        self.static_mem_base = current_addr

        # Add pure/parser tables in static memory (read-only)
        pure_story_start = len(story)
        if pure_table_data:
            story.extend(pure_table_data)
            current_addr += len(pure_table_data)

            # Align to even boundary
            while len(story) % 2 != 0:
                story.append(0)
                current_addr += 1

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

        # Resolve VWORD table placeholders in NEW-PARSER? mode
        # (same 0xFB00 format but resolves to table addresses instead of dictionary)
        if vword_fixups and globals_len > 0 and table_offsets:
            self._resolve_vword_placeholders_in_story(
                story, vword_fixups, table_base_addr, table_offsets, globals_addr, globals_len
            )

        # Align to even boundary
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

        # Mark start of high memory (where code begins)
        self.high_mem_base = len(story)

        # High memory must be aligned for packed addresses:
        # V1-3: 2-byte alignment (packed = byte / 2)
        # V4-5: 4-byte alignment (packed = byte / 4)
        # V6-7: 8-byte alignment (routines_offset = byte / 8)
        # V8: 8-byte alignment (packed = byte / 8)
        if self.version >= 6:
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
        table_routine_patched = set()
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

                # Determine story offset based on whether table is in impure or pure section
                if table_offset < impure_tables_size:
                    # Impure table: in dynamic memory section
                    story_offset = impure_story_start + table_offset
                else:
                    # Pure table: in static memory section
                    story_offset = pure_story_start + (table_offset - impure_tables_size)

                if story_offset + 1 < len(story):
                    story[story_offset] = (packed_addr >> 8) & 0xFF
                    story[story_offset + 1] = packed_addr & 0xFF
                    # These bytes are a RESOLVED packed routine address; the
                    # byte-stepped 0xFC string scan over table data must not
                    # rescan them (PRE-BOARD packed 0x4bfc: 'fc 00' was eaten
                    # as string placeholder 0 and PREACTIONS[30] broke).
                    table_routine_patched.add(story_offset)
                    table_routine_patched.add(story_offset + 1)

        # Resolve property routine placeholders in object data
        # Now that we know high_mem_base, we can patch 0xFA00 | idx values
        # with actual packed routine addresses
        if property_routine_fixups and objects:
            # Build lookup: placeholder_idx -> packed_routine_address
            fixup_map = {}
            for placeholder_idx, routine_offset in property_routine_fixups:
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

                fixup_map[placeholder_idx] = packed_addr

            # Patch 0xFA00|idx markers inside PROPERTY DATA only, by walking each
            # object's property table. The old byte-blind scan covered the WHOLE
            # objects region including the entry headers -- an object whose
            # property-table pointer low byte happened to be 0xFA (minizork's
            # CELLAR at 0x15FA) had its pointer rewritten to a routine address,
            # so the room printed a garbage name and its neighbor's description.
            self._walk_property_data(
                story, objects_addr, len(objects), prop_defaults_size,
                lambda j: (fixup_map.get(story[j + 1])
                           if story[j] == 0xFA else None))

        # Byte positions in `routines` that any resolution pass has already
        # written. Later scanners (vocab/vword) must skip them: resolved packed
        # string addresses can contain 0xFB/0xFC bytes that look like
        # placeholders (see _resolve_vocab_placeholders).
        code_patched_positions = set()

        # If string table is present, add string table after routines and resolve markers
        if string_table is not None:
            # Calculate final routine length AFTER marker resolution
            # Each marker (0x8D 0xFF 0xFE <len16> <text>) becomes 3 bytes (0x8D <addr16>)
            # So we shrink by (5 + text_len - 3) = (2 + text_len) per marker
            final_routines_len = len(routines)
            i = 0
            while (not tell_placeholder_positions) and i < len(routines):
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
            # Every byte these passes write is recorded in code_patched_positions:
            # a packed string address may legally contain 0xFB/0xFC bytes, and the
            # later vocab/vword scanners must not misread them as placeholders
            # (zork1's PARSER had a je branch clobbered exactly this way).
            routines = self._resolve_string_markers(
                routines, string_table, tell_string_placeholders, tell_placeholder_positions,
                patched_positions=code_patched_positions
            )

            # Resolve string operand placeholders (0xFC00 | index -> packed address)
            if string_placeholders:
                routines = self._resolve_string_placeholders(
                    routines, string_placeholders, string_table,
                    string_code_index_max,
                    patched_positions=code_patched_positions
                )

            # Point-wise OVERFLOW string markers in ROUTINE code (data band /
            # ext band, used once the 256-slot 0xFC00 band is full). Only
            # positions discovered structurally at generation time are
            # patched -- no byte scan can safely match these bands in code.
            _csm = getattr(self, '_code_string_marker_fixups', None)
            _sde = getattr(self, '_string_data_ext', {}) or {}
            if _csm and string_table is not None:
                _sdp = string_data_placeholders or {}
                _rba = bytearray(routines)
                for _off, _w in _csm:
                    if _off + 1 >= len(_rba) or _off in code_patched_positions:
                        continue
                    if ((_rba[_off] << 8) | _rba[_off + 1]) != _w:
                        continue
                    if 0xF400 <= _w <= 0xF7FF:
                        _text = _sdp.get(_w & 0x3FF)
                    else:
                        _text = _sde.get(_w)
                    if _text is None:
                        continue
                    _paddr = string_table.get_packed_address(_text, self.version)
                    if _paddr is None:
                        continue
                    _rba[_off] = (_paddr >> 8) & 0xFF
                    _rba[_off + 1] = _paddr & 0xFF
                    code_patched_positions.add(_off)
                    code_patched_positions.add(_off + 1)
                routines = bytes(_rba)

            # Also resolve string placeholders in table data (LONG-WORD-TABLE,
            # string elements of global tables like INDENTS). Byte-stepped: table
            # data has mixed byte/word layouts.
            if (string_placeholders or string_data_placeholders) and table_data_len > 0:
                self._resolve_string_placeholders_in_story(
                    story, string_placeholders or {}, string_table,
                    table_data_start, table_data_len, step=1,
                    data_placeholders=string_data_placeholders,
                    skip_positions=table_routine_patched
                )

            # Point-wise data-string markers inside tables (positions recorded at
            # encode time -- scanning can't distinguish a marker from a packed
            # routine address with an 0xF4-0xF7 low byte).
            if table_string_fixups and string_data_placeholders and table_offsets:
                for _tidx, _off in table_string_fixups:
                    if _tidx not in table_offsets:
                        continue
                    toff = table_offsets[_tidx] + _off
                    if toff < impure_tables_size:
                        pos = impure_story_start + toff
                    else:
                        pos = pure_story_start + (toff - impure_tables_size)
                    if pos + 1 >= len(story):
                        continue
                    w = (story[pos] << 8) | story[pos + 1]
                    _sde2 = getattr(self, '_string_data_ext', {}) or {}
                    if 0xF400 <= w <= 0xF7FF or w in _sde2:
                        text = (string_data_placeholders.get(w & 0x3FF)
                                if w >= 0xF400 else _sde2.get(w))
                        if text is not None:
                            paddr = string_table.get_packed_address(text, self.version)
                            if paddr is not None:
                                story[pos] = (paddr >> 8) & 0xFF
                                story[pos + 1] = paddr & 0xFF

            # Also resolve string placeholders in the globals table: a global
            # initialized to a string constant (<GLOBAL X "text">) holds a 0xFC00|idx
            # placeholder that must become the packed string address.
            if (string_placeholders or string_data_placeholders) and globals_len > 0:
                self._resolve_string_placeholders_in_story(
                    story, string_placeholders or {}, string_table,
                    globals_addr, globals_len,
                    data_placeholders=string_data_placeholders
                )

            # And in object property data: classic direction exits (NEXIT/CEXIT/
            # DEXIT) embed their refusal-message string address in the property.
            if (string_placeholders or string_data_placeholders) and objects:
                self._resolve_string_placeholders_in_properties(
                    story, objects_addr, len(objects), prop_defaults_size,
                    string_placeholders or {}, string_table,
                    data_placeholders=string_data_placeholders
                )

        # Resolve routine call fixups (patch call addresses)
        # Remember which byte positions now hold routine packed addresses -- the
        # position-blind vocab/vword scanners below must not touch them, or a
        # routine address containing 0xFB (a legal low byte, e.g. LIT? at 0x39FB)
        # gets misread as a W?* placeholder and every call to it is silently
        # redirected. Both bytes of each 2-byte operand are protected, as are
        # all bytes the string-resolution passes wrote (code_patched_positions).
        protected_positions = set(code_patched_positions)
        if routine_fixups:
            routines = self._resolve_routine_fixups(routines, routine_fixups)
            for code_offset, _routine_offset in routine_fixups:
                protected_positions.add(code_offset)
                protected_positions.add(code_offset + 1)

        # Resolve vocabulary word placeholders (W?* -> dictionary addresses)
        if vocab_fixups:
            routines = self._resolve_vocab_placeholders(routines, vocab_fixups, dict_addr,
                                                        protected_positions)

        # Resolve VWORD table placeholders (NEW-PARSER? mode: W?* -> table addresses)
        if vword_fixups and table_offsets:
            routines = self._resolve_vword_placeholders(routines, vword_fixups, table_base_addr,
                                                       table_offsets, protected_positions)

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
        # Note: For V6-7, there's 4 bytes of padding after high_mem_base before routines
        initial_pc = self.high_mem_base
        if routines:
            num_locals = routines[0] & 0x0F  # Local count is in low nibble
            if self.version <= 4:
                # Skip: 1 byte header + num_locals * 2 bytes for defaults
                initial_pc = self.high_mem_base + 1 + (num_locals * 2)
            elif self.version == 6:
                # V6: Uses packed routine address - interpreter calls the routine
                # Packed address = (byte_addr - routines_offset*8) / 4
                # With 4-byte padding, first routine is at packed address 1
                initial_pc = 1
            elif self.version == 7:
                # V7: Interpreters (dfrotz/bocfel) have bugs where they treat the
                # packed address as a direct byte address. As a workaround, store
                # the actual byte address of the first instruction.
                initial_pc = self.high_mem_base + 4 + 1
            else:
                # V5, V8: Skip 1 byte header only
                initial_pc = self.high_mem_base + 1

        # Update header with correct addresses
        struct.pack_into('>H', story, 0x04, self.high_mem_base)  # High memory base
        struct.pack_into('>H', story, 0x06, initial_pc)  # Initial PC (or packed routine for V6+)
        struct.pack_into('>H', story, 0x08, dict_addr)  # Dictionary address
        struct.pack_into('>H', story, 0x0A, objects_addr)  # Object table address
        struct.pack_into('>H', story, 0x0C, globals_addr)  # Globals address
        struct.pack_into('>H', story, 0x0E, self.static_mem_base)  # Static memory base
        if abbrev_addr > 0:
            struct.pack_into('>H', story, 0x18, abbrev_addr)  # Abbreviations table address

        # V5+ alphabet table address
        if alphabet_table_addr > 0:
            struct.pack_into('>H', story, 0x34, alphabet_table_addr)  # Alphabet table address

        # V5+ extension table address
        if extension_table_addr > 0:
            struct.pack_into('>H', story, 0x36, extension_table_addr)  # Extension table address

        # V5+ TCHARS (terminating characters table) address at 0x2E
        if self.version >= 5 and tchars_table_idx is not None and tchars_table_idx in table_offsets:
            tchars_offset = table_offsets[tchars_table_idx]
            if tchars_offset < impure_tables_size:
                tchars_addr = table_base_addr + tchars_offset
            else:
                tchars_addr = self.static_mem_base + (tchars_offset - impure_tables_size)
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
