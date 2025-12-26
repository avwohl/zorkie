"""
Abbreviations table for Z-machine text compression.

The Z-machine supports 96 abbreviations (32 each for Z-characters 1, 2, 3)
that allow common strings to be compressed to 2 Z-characters instead of
their full encoding.

Abbreviation encoding:
- Z-char 1 (table 0): index = next Z-char (0-31)
- Z-char 2 (table 1): index = 32 + next Z-char (32-63)
- Z-char 3 (table 2): index = 64 + next Z-char (64-95)

The abbreviations table in the story file contains 96 word addresses
pointing to the encoded strings.
"""

from collections import Counter
from typing import List, Tuple, Dict, Optional


class AbbreviationsTable:
    """Manages abbreviation selection and encoding for Z-machine."""

    def __init__(self):
        self.abbreviations: List[str] = []  # The 96 abbreviation strings
        self.lookup: Dict[str, int] = {}  # Maps string -> abbreviation index
        self.encoded_strings: List[bytes] = []  # Encoded abbreviation strings

    def analyze_strings(self, strings: List[str], max_abbrevs: int = 96) -> None:
        """
        Analyze a collection of strings and select best non-overlapping abbreviations.

        Args:
            strings: List of all strings from the game
            max_abbrevs: Maximum number of abbreviations (default 96 for V3+)
        """
        # Find all substrings and count occurrences
        substring_counts = Counter()

        for string in strings:
            # Generate substrings of various lengths
            for length in range(2, min(21, len(string) + 1)):
                for i in range(len(string) - length + 1):
                    substr = string[i:i+length]
                    # Only meaningful substrings
                    if substr.strip() and not substr.isspace():
                        substring_counts[substr] += 1

        # Calculate savings for each substring
        candidates = []
        for substr, count in substring_counts.items():
            if count >= 2:  # Lower threshold for more candidates
                savings = self._calculate_savings(substr, count)
                if savings > 0:
                    candidates.append((savings, count, substr))

        # Sort by savings (best first)
        candidates.sort(reverse=True)

        # Select non-overlapping abbreviations using greedy strategy
        self.abbreviations = []
        self.lookup = {}

        for savings, count, substr in candidates:
            # Check if this candidate overlaps with any already-selected abbreviation
            overlaps = False
            for existing in self.abbreviations:
                if existing in substr or substr in existing:
                    overlaps = True
                    break

            if not overlaps:
                idx = len(self.abbreviations)
                self.abbreviations.append(substr)
                self.lookup[substr] = idx

                if len(self.abbreviations) >= max_abbrevs:
                    break

    def _calculate_savings(self, substr: str, count: int) -> float:
        """
        Calculate bytes saved by abbreviating a substring.

        Each character costs about 0.6 bytes in Z-char encoding (5 bits per Z-char).
        Abbreviation reference costs 2 Z-characters (1.33 bytes).
        """
        original_cost = len(substr) * 0.6
        abbreviated_cost = 1.33
        savings_per_use = original_cost - abbreviated_cost
        total_savings = savings_per_use * count
        # Subtract cost of storing the abbreviation itself once
        total_savings -= original_cost
        return total_savings

    def find_abbreviation(self, text: str, start_pos: int) -> Optional[Tuple[int, int]]:
        """
        Find the longest abbreviation that matches text starting at start_pos.

        Returns:
            (abbreviation_index, length) if found, None otherwise
        """
        best_match = None
        best_length = 0

        for abbrev_index, abbrev in enumerate(self.abbreviations):
            abbrev_len = len(abbrev)
            if (start_pos + abbrev_len <= len(text) and
                text[start_pos:start_pos + abbrev_len] == abbrev):
                # Prefer longer matches
                if abbrev_len > best_length:
                    best_match = abbrev_index
                    best_length = abbrev_len

        if best_match is not None:
            return (best_match, best_length)
        return None

    def encode_abbreviations(self, text_encoder) -> List[bytes]:
        """
        Encode all abbreviations using the provided text encoder.

        Args:
            text_encoder: TextEncoder instance with encode_text_zchars method

        Returns:
            List of encoded abbreviation strings
        """
        self.encoded_strings = []

        for abbrev in self.abbreviations:
            # Encode abbreviation as a standalone string
            # Use literal=True to skip text transformations (abbreviations are literal text)
            encoded = text_encoder.encode_text_zchars(abbrev, literal=True)
            self.encoded_strings.append(encoded)

        return self.encoded_strings

    def get_abbreviation_table_bytes(self, strings_base_address: int) -> bytes:
        """
        Generate the abbreviations table (96 word addresses).

        Args:
            strings_base_address: Address where abbreviation strings start

        Returns:
            192 bytes (96 × 2 bytes per word address)
        """
        table = bytearray()

        # Track current address as we add abbreviation strings
        current_addr = strings_base_address

        for i in range(96):
            if i < len(self.abbreviations):
                # Word address (divide by 2 for V3)
                word_addr = current_addr // 2
                table.append((word_addr >> 8) & 0xFF)
                table.append(word_addr & 0xFF)

                # Advance address by length of this abbreviation's encoding
                if i < len(self.encoded_strings):
                    current_addr += len(self.encoded_strings[i])
            else:
                # Empty slot - point to address 0
                table.append(0)
                table.append(0)

        return bytes(table)

    def get_total_encoded_size(self) -> int:
        """Get total size of all encoded abbreviation strings."""
        return sum(len(enc) for enc in self.encoded_strings)

    def get_statistics(self) -> Dict:
        """Get statistics about the abbreviations table."""
        return {
            'count': len(self.abbreviations),
            'table_size': 192,  # 96 × 2 bytes
            'strings_size': self.get_total_encoded_size(),
            'total_size': 192 + self.get_total_encoded_size(),
            'abbreviations': [
                {'index': i, 'text': abbr, 'encoded_size': len(self.encoded_strings[i])}
                for i, abbr in enumerate(self.abbreviations)
                if i < len(self.encoded_strings)
            ]
        }

    def __len__(self) -> int:
        """Return number of abbreviations."""
        return len(self.abbreviations)

    def __getitem__(self, index: int) -> str:
        """Get abbreviation by index."""
        return self.abbreviations[index]
