"""
Z-machine object table builder.

Builds the object table with property defaults, object tree, and property tables.
"""

from typing import List, Dict, Any, Tuple
import struct


class ObjectTable:
    """Builds Z-machine object table."""

    def __init__(self, version: int = 3, text_encoder=None):
        self.version = version
        self.text_encoder = text_encoder
        self.objects: List[Dict[str, Any]] = []
        self.property_defaults = [0] * (31 if version <= 3 else 63)

    def add_object(self, name: str, parent: int = 0, sibling: int = 0,
                   child: int = 0, attributes: int = 0,
                   properties: Dict[int, Any] = None):
        """Add an object to the table."""
        self.objects.append({
            'name': name,
            'parent': parent,
            'sibling': sibling,
            'child': child,
            'attributes': attributes,
            'properties': properties or {}
        })

    def build(self) -> bytes:
        """Build object table bytes with property tables.

        Note: Property table addresses are initially relative to start of this data.
        The assembler will fix them up to absolute addresses when placing in story file.
        """
        result = bytearray()

        # Property defaults table (31 words for V1-3, 63 for V4+)
        for default in self.property_defaults:
            result.extend(struct.pack('>H', default))

        # Calculate where object entries start
        object_table_start = len(result)

        # Reserve space for object entries
        if self.version <= 3:
            object_entry_size = 9
        else:
            object_entry_size = 14

        num_objects = len(self.objects)
        object_entries_size = num_objects * object_entry_size

        # Build all property tables first to know their addresses
        property_tables = []
        for obj in self.objects:
            prop_table = self.build_property_table(obj)
            property_tables.append(prop_table)

        # Now build object entries with correct property table addresses
        # Property tables start after all object entries
        # Addresses are relative to start of object table data (will be fixed up by assembler)
        prop_table_base_addr = object_table_start + object_entries_size

        object_entries = bytearray()
        current_prop_addr = prop_table_base_addr

        for i, obj in enumerate(self.objects):
            if self.version <= 3:
                # V1-3: 9 bytes per object
                # 4 bytes attributes (32 bits)
                object_entries.extend(struct.pack('>I', obj['attributes']))
                # 1 byte parent, sibling, child
                object_entries.append(obj['parent'] & 0xFF)
                object_entries.append(obj['sibling'] & 0xFF)
                object_entries.append(obj['child'] & 0xFF)
                # 2 bytes property table address
                object_entries.extend(struct.pack('>H', current_prop_addr))
            else:
                # V4+: 14 bytes per object
                # 6 bytes attributes (48 bits)
                attr_bytes = struct.pack('>Q', obj['attributes'])[-6:]  # Last 6 bytes
                object_entries.extend(attr_bytes)
                # 2 bytes each: parent, sibling, child
                object_entries.extend(struct.pack('>H', obj['parent']))
                object_entries.extend(struct.pack('>H', obj['sibling']))
                object_entries.extend(struct.pack('>H', obj['child']))
                # 2 bytes property table address
                object_entries.extend(struct.pack('>H', current_prop_addr))

            # Advance to next property table
            current_prop_addr += len(property_tables[i])

        # Combine everything
        result.extend(object_entries)

        # Add all property tables
        for prop_table in property_tables:
            result.extend(prop_table)

        return bytes(result)

    def build_property_table(self, obj: Dict[str, Any]) -> bytes:
        """Build a property table for an object.

        Format (V1-3):
        - Byte 0: Text length (number of 2-byte words)
        - Bytes 1+: Object name (Z-encoded text)
        - Property list:
          - Size byte: 32 × (data_length - 1) + property_number
          - Data: 1-8 bytes
        - Terminator: 0x00
        """
        prop_table = bytearray()

        # Encode object description (from DESC property #1)
        # The property table header contains the short description shown in listings
        properties = obj.get('properties', {})
        obj_desc = properties.get(1, '')  # Property #1 is DESC

        # If DESC is not a string (e.g., it's an AST node), try to extract value
        if hasattr(obj_desc, 'value'):
            obj_desc = obj_desc.value
        if not isinstance(obj_desc, str):
            obj_desc = ''

        if self.text_encoder:
            # Encode the description
            encoded_words = self.text_encoder.encode_string(obj_desc)
            # Text length is number of words
            prop_table.append(len(encoded_words))
            # Add encoded text
            for word in encoded_words:
                prop_table.extend(struct.pack('>H', word))
        else:
            # No encoder - just add empty name
            prop_table.append(0)

        # Build property list from obj['properties']
        # Properties must be in descending numerical order
        properties = obj.get('properties', {})

        # Sort properties by number (descending)
        sorted_props = sorted(properties.items(), key=lambda x: x[0], reverse=True)

        for prop_num, prop_value in sorted_props:
            # Convert property value to bytes
            prop_data = self.encode_property_value(prop_value)
            data_length = len(prop_data)

            if data_length == 0:
                continue  # Skip empty properties

            if self.version <= 3:
                # V1-3: Size byte = 32 × (data_length - 1) + property_number
                if data_length > 8:
                    data_length = 8  # Max 8 bytes in V1-3

                size_byte = 32 * (data_length - 1) + prop_num
                prop_table.append(size_byte)
                prop_table.extend(prop_data[:data_length])
            else:
                # V4+: More complex encoding
                if data_length <= 2:
                    # Single size byte
                    size_byte = prop_num  # Bit 7 = 0
                    if data_length == 2:
                        size_byte |= 0x40  # Set bit 6 for 2-byte data
                    prop_table.append(size_byte)
                    prop_table.extend(prop_data[:data_length])
                else:
                    # Double size bytes
                    size_byte1 = 0x80 | prop_num  # Bit 7 = 1
                    size_byte2 = data_length & 0x3F  # Bits 5-0 = length
                    prop_table.append(size_byte1)
                    prop_table.append(size_byte2)
                    prop_table.extend(prop_data)

        # Terminator
        prop_table.append(0x00)

        return bytes(prop_table)

    def encode_property_value(self, value: Any) -> bytes:
        """Encode a property value to bytes.

        Property values can be:
        - Integers (stored as 2 bytes)
        - Strings (encoded and stored)
        - Lists of integers
        """
        if isinstance(value, int):
            # Single integer - store as 2 bytes
            return struct.pack('>H', value & 0xFFFF)
        elif isinstance(value, str):
            # String - encode and store
            if self.text_encoder:
                encoded = self.text_encoder.encode_string(value)
                result = bytearray()
                for word in encoded:
                    result.extend(struct.pack('>H', word))
                return bytes(result)
            else:
                return b''
        elif isinstance(value, (list, tuple)):
            # List of integers
            result = bytearray()
            for item in value:
                if isinstance(item, int):
                    result.extend(struct.pack('>H', item & 0xFFFF))
            return bytes(result)
        else:
            return b''
