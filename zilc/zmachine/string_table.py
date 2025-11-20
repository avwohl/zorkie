"""
String table with deduplication for Z-machine story files.

Eliminates duplicate strings by storing each unique string once and
referencing it by address. This reduces story file size by 5-10KB
for typical games.
"""

from typing import Dict, Optional
from .text_encoding import ZTextEncoder


class StringTable:
    """Manages deduplicated string storage for Z-machine."""

    def __init__(self, text_encoder: ZTextEncoder):
        """
        Initialize string table.

        Args:
            text_encoder: ZTextEncoder instance for encoding strings
        """
        self.text_encoder = text_encoder
        self.strings: Dict[str, bytes] = {}  # text -> encoded bytes
        self.addresses: Dict[str, int] = {}  # text -> address in story file
        self.encoded_data = bytearray()  # All encoded strings concatenated
        self.base_address = 0  # Base address where strings start in story file

    def add_string(self, text: str) -> int:
        """
        Add a string to the table (or get existing address).

        Args:
            text: The string to add

        Returns:
            Offset in the string table (relative to base_address)
        """
        if text in self.addresses:
            # Already in table, return existing offset
            return self.addresses[text]

        # Encode the string
        encoded = self.text_encoder.encode_text_zchars(text, use_abbreviations=True)

        # Store in table
        offset = len(self.encoded_data)
        self.strings[text] = encoded
        self.addresses[text] = offset
        self.encoded_data.extend(encoded)

        return offset

    def get_address(self, text: str) -> Optional[int]:
        """
        Get the absolute address of a string in the story file.

        Args:
            text: The string to look up

        Returns:
            Absolute address, or None if string not in table
        """
        if text not in self.addresses:
            return None
        return self.base_address + self.addresses[text]

    def get_packed_address(self, text: str, version: int = 3) -> Optional[int]:
        """
        Get the packed address of a string for use with PRINT_PADDR.

        Args:
            text: The string to look up
            version: Z-machine version (affects packing)

        Returns:
            Packed address, or None if string not in table
        """
        addr = self.get_address(text)
        if addr is None:
            return None

        # Packed address formula depends on version
        if version <= 3:
            return addr // 2
        elif version <= 5:
            return addr // 4
        elif version <= 7:
            return addr // 4
        else:  # V8
            return addr // 8

    def get_offset(self, text: str) -> Optional[int]:
        """
        Get the offset of a string relative to base_address.

        Args:
            text: The string to look up

        Returns:
            Offset, or None if string not in table
        """
        return self.addresses.get(text)

    def set_base_address(self, address: int):
        """
        Set the base address where strings will be located in the story file.

        Args:
            address: Base address in story file
        """
        self.base_address = address

    def get_encoded_data(self) -> bytes:
        """
        Get all encoded strings concatenated.

        Returns:
            Bytes of all encoded strings
        """
        return bytes(self.encoded_data)

    def get_statistics(self) -> Dict:
        """
        Get statistics about string table.

        Returns:
            Dictionary with statistics
        """
        return {
            'unique_strings': len(self.strings),
            'total_size': len(self.encoded_data),
            'average_string_size': len(self.encoded_data) / len(self.strings) if self.strings else 0,
            'base_address': self.base_address,
        }

    def __len__(self) -> int:
        """Return number of unique strings."""
        return len(self.strings)

    def __contains__(self, text: str) -> bool:
        """Check if string is in table."""
        return text in self.strings
