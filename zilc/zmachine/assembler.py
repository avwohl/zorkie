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
        divisor = 2 if self.version <= 3 else (8 if self.version == 8 else 4)
        file_length = len(self.memory) // divisor if self.memory else 1
        header[0x1A:0x1C] = struct.pack('>H', file_length)

        # Bytes 0x1C-0x1D: Checksum (calculated later)
        header[0x1C:0x1E] = struct.pack('>H', 0x0000)

        return header

    def calculate_checksum(self, data: bytes) -> int:
        """Calculate story file checksum (sum of all bytes except header)."""
        return sum(data[0x40:]) & 0xFFFF

    def build_story_file(self, routines: bytes, objects: bytes = b'',
                        dictionary: bytes = b'', globals_data: bytes = b'',
                        abbreviations_table=None) -> bytes:
        """
        Build complete story file.

        Args:
            routines: Compiled routine bytecode
            objects: Object table data
            dictionary: Dictionary data
            globals_data: Global variables data
            abbreviations_table: AbbreviationsTable instance (optional)

        Returns:
            Complete story file as bytes
        """
        # Start with header
        story = self.create_header()

        # Track addresses as we build
        current_addr = 0x40  # After 64-byte header

        # Add globals (after header, starting at 0x40 typically)
        if not globals_data:
            # Default: 240 globals initialized to 0
            globals_data = bytes(480)  # 240 * 2 bytes

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
            # Encode abbreviation strings first
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

        # Align to even boundary for high memory
        while len(story) % 2 != 0:
            story.append(0)
            current_addr += 1

        # Mark start of high memory
        self.high_mem_base = len(story)

        # Add routines
        story.extend(routines)

        # Update header with correct addresses
        struct.pack_into('>H', story, 0x04, self.high_mem_base)  # High memory base
        struct.pack_into('>H', story, 0x06, self.high_mem_base)  # Initial PC
        struct.pack_into('>H', story, 0x08, dict_addr)  # Dictionary address
        struct.pack_into('>H', story, 0x0A, objects_addr)  # Object table address
        struct.pack_into('>H', story, 0x0C, globals_addr)  # Globals address
        struct.pack_into('>H', story, 0x0E, current_addr)  # Static memory base
        if abbrev_addr > 0:
            struct.pack_into('>H', story, 0x18, abbrev_addr)  # Abbreviations table address

        # Calculate and store checksum
        checksum = self.calculate_checksum(story)
        struct.pack_into('>H', story, 0x1C, checksum)

        # Update file length
        divisor = 2 if self.version <= 3 else (8 if self.version == 8 else 4)
        file_length = len(story) // divisor
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
