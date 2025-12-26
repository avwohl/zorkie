"""
Z-machine text encoding (ZSCII and Z-characters).

Converts strings to Z-machine compressed text format using 5-bit Z-characters
packed into 16-bit words.
"""

from typing import List, Tuple


# Default alphabet tables
# Z-chars 0-5 are special, z-chars 6-31 map to alphabet characters
# The string index should equal the z-char number
#
# We use \x00 for positions that are special codes (not direct characters)

# A0 and A1 are the same across all versions
ALPHABET_A0 = " \x00\x00\x00\x00\x00abcdefghijklmnopqrstuvwxyz"
ALPHABET_A1 = " \x00\x00\x00\x00\x00ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# A2 differs between versions:
# V1: position 7 is '0' (digit zero) - no newline needed since z-char 1 is newline
#     The '<' character is at position 21 (after the main punctuation)
# V2+: position 7 is newline
# Position 6 is always the ZSCII escape marker (not a printable character)
ALPHABET_A2_V1 = " \x00\x00\x00\x00\x00\x000123456789.,!?_#'\"/\\<-:()"
ALPHABET_A2_V2 = " \x00\x00\x00\x00\x00\x00\n0123456789.,!?_#'\"/\\-:()"


class ZTextEncoder:
    """Encodes text to Z-machine format."""

    def __init__(self, version: int = 3, abbreviations_table=None, crlf_character: str = '|',
                 preserve_spaces: bool = False):
        self.version = version
        self.alphabet_a0 = ALPHABET_A0
        self.alphabet_a1 = ALPHABET_A1
        # V1 has different A2 (< instead of newline at position 7)
        self.alphabet_a2 = ALPHABET_A2_V1 if version == 1 else ALPHABET_A2_V2
        self.abbreviations_table = abbreviations_table
        # Character that gets translated to newline in strings (default |)
        self.crlf_character = crlf_character
        # Whether to preserve multiple spaces (default: collapse after periods)
        self.preserve_spaces = preserve_spaces

    def char_to_zchar(self, ch: str, current_alphabet: int = 0) -> Tuple[List[int], int]:
        """
        Convert a character to Z-characters.

        Returns: (list of z-characters, new alphabet after encoding)

        Shift codes differ by version:
        - V1-2: z-chars 2-3 are temporary shifts, 4-5 are shift locks
          - 2 = shift up (A0->A1, A1->A2, A2->A0)
          - 3 = shift down (A0->A2, A1->A0, A2->A1)
          - 4 = shift lock up
          - 5 = shift lock down
        - V3+: z-chars 4-5 are temporary shifts only
          - 4 = shift to A1 (for next char only)
          - 5 = shift to A2 (for next char only)
          - Current alphabet always resets to A0 after each character
        """
        # V1 special: z-char 1 is newline
        if self.version == 1 and ch == '\n':
            return ([1], current_alphabet)

        # z-char 0 is always space (in any alphabet)
        if ch == ' ':
            return ([0], current_alphabet)

        # Try current alphabet first
        if current_alphabet == 0 and ch in self.alphabet_a0:
            idx = self.alphabet_a0.index(ch)
            if idx >= 6:  # Positions 0-5 are special
                return ([idx], current_alphabet)
        elif current_alphabet == 1 and ch in self.alphabet_a1:
            idx = self.alphabet_a1.index(ch)
            if idx >= 6:
                return ([idx], current_alphabet)
        elif current_alphabet == 2 and ch in self.alphabet_a2:
            idx = self.alphabet_a2.index(ch)
            if idx >= 6:
                return ([idx], current_alphabet)

        # Need to shift to a different alphabet
        if self.version <= 2:
            # V1-2: Use shift lock codes (4-5) for simplicity
            # This always shifts and stays in the new alphabet
            return self._char_to_zchar_v1v2(ch, current_alphabet)
        else:
            # V3+: Use temporary shift codes (4-5)
            # Current alphabet always returns to A0 conceptually
            return self._char_to_zchar_v3plus(ch, current_alphabet)

    def _char_to_zchar_v1v2(self, ch: str, current_alphabet: int) -> Tuple[List[int], int]:
        """Handle character encoding for V1-2 with temporary shifts.

        V1-2 shift codes:
        - z-char 2 = temp shift up (A0->A1, A1->A2, A2->A0) for next char only
        - z-char 3 = temp shift down (A0->A2, A1->A0, A2->A1) for next char only
        - z-char 4 = shift lock up (permanent)
        - z-char 5 = shift lock down (permanent)

        We use temporary shifts for simple strings - the alphabet returns to
        current after each shifted character.
        """
        # Find which alphabet contains the character and what shift is needed
        if ch in self.alphabet_a0:
            idx = self.alphabet_a0.index(ch)
            if idx >= 6:
                if current_alphabet == 0:
                    return ([idx], 0)
                elif current_alphabet == 1:
                    # A1 -> A0: shift down (3)
                    return ([3, idx], 1)
                else:  # current_alphabet == 2
                    # A2 -> A0: shift up (2)
                    return ([2, idx], 2)

        if ch in self.alphabet_a1:
            idx = self.alphabet_a1.index(ch)
            if idx >= 6:
                if current_alphabet == 1:
                    return ([idx], 1)
                elif current_alphabet == 0:
                    # A0 -> A1: shift up (2)
                    return ([2, idx], 0)
                else:  # current_alphabet == 2
                    # A2 -> A1: shift down (3)
                    return ([3, idx], 2)

        if ch in self.alphabet_a2:
            idx = self.alphabet_a2.index(ch)
            if idx >= 6:
                if current_alphabet == 2:
                    return ([idx], 2)
                elif current_alphabet == 0:
                    # A0 -> A2: shift down (3)
                    return ([3, idx], 0)
                else:  # current_alphabet == 1
                    # A1 -> A2: shift up (2)
                    return ([2, idx], 1)

        # Character not in any alphabet - use ZSCII escape
        # Need to temporarily shift to A2 for escape sequence
        zscii_code = ord(ch)
        high = (zscii_code >> 5) & 0x1F
        low = zscii_code & 0x1F

        if current_alphabet == 2:
            return ([6, high, low], 2)
        elif current_alphabet == 0:
            # A0 -> A2: shift down (3)
            return ([3, 6, high, low], 0)
        else:  # current_alphabet == 1
            # A1 -> A2: shift up (2)
            return ([2, 6, high, low], 1)

    def _char_to_zchar_v3plus(self, ch: str, current_alphabet: int) -> Tuple[List[int], int]:
        """Handle character encoding for V3+ with temporary shifts."""
        # In V3+, we're conceptually always in A0, shifts are temporary
        # z-char 4 = temporary shift to A1
        # z-char 5 = temporary shift to A2

        # Check A0 (no shift needed)
        if ch in self.alphabet_a0:
            idx = self.alphabet_a0.index(ch)
            if idx >= 6:
                return ([idx], 0)

        # Check A1 (need shift 4)
        if ch in self.alphabet_a1:
            idx = self.alphabet_a1.index(ch)
            if idx >= 6:
                return ([4, idx], 0)

        # Check A2 (need shift 5)
        if ch in self.alphabet_a2:
            idx = self.alphabet_a2.index(ch)
            if idx >= 6:
                return ([5, idx], 0)

        # Character not in any alphabet - use ZSCII escape
        # Shift to A2 (z-char 5), then z-char 6 (escape), then two 5-bit values
        zscii_code = ord(ch)
        high = (zscii_code >> 5) & 0x1F
        low = zscii_code & 0x1F
        return ([5, 6, high, low], 0)

    def encode_string(self, text: str, max_words: int = None, use_abbreviations: bool = True,
                       literal: bool = False) -> List[int]:
        """
        Encode a string to Z-characters packed into 16-bit words.

        Args:
            text: The string to encode
            max_words: Maximum number of 16-bit words (for dictionary entries)
            use_abbreviations: Whether to use abbreviations table (default True)
            literal: If True, skip all text transformations (for abbreviation strings)

        Returns:
            List of 16-bit words with Z-characters packed in
        """
        # ZIL string translation (skipped if literal=True):
        # - CRLF character (default |) becomes newline in output
        # - Literal newlines immediately after CRLF character are absorbed (ignored)
        # - Other literal newlines (CRLF, CR, LF) become spaces
        # - Unless PRESERVE-SPACES? is set, collapse 2+ spaces after periods to 1 space
        if not literal:
            import re
            crlf = self.crlf_character
            # Escape the character for regex use
            crlf_escaped = re.escape(crlf)
            # Step 1: Absorb newlines immediately after CRLF character
            text = re.sub(crlf_escaped + r'(?:\r\n|\r|\n)', crlf, text)
            # Step 2: Replace remaining literal newlines with space
            text = re.sub(r'\r\n|\r|\n', ' ', text)
            # Step 3: Replace CRLF character with newline
            text = text.replace(crlf, '\n')
            # Step 4: Collapse multiple spaces after periods (and after newlines from CRLF)
            # unless PRESERVE-SPACES? is set
            # The rule is: reduce runs of 2+ spaces after periods/newlines by 1
            # e.g., 2 spaces → 1, 3 spaces → 2
            if not self.preserve_spaces:
                # After period followed by 2+ spaces, reduce by removing one space
                def reduce_period_spaces(m):
                    spaces = m.group(1)
                    return '.' + spaces[:-1]  # Remove one space
                text = re.sub(r'\.( {2,})', reduce_period_spaces, text)
                # After newline followed by 2+ spaces, reduce by removing one space
                def reduce_newline_spaces(m):
                    spaces = m.group(1)
                    return '\n' + spaces[:-1]  # Remove one space
                text = re.sub(r'\n( {2,})', reduce_newline_spaces, text)

        # Convert string to Z-characters
        zchars = []
        current_alphabet = 0

        # Process text with abbreviation support
        i = 0
        while i < len(text):
            # Try to find abbreviation match if enabled
            if use_abbreviations and self.abbreviations_table and len(self.abbreviations_table) > 0:
                match = self.abbreviations_table.find_abbreviation(text, i)
                if match:
                    abbrev_index, abbrev_length = match
                    # Encode abbreviation reference
                    # Z-char 1-3 followed by index within that table (0-31)
                    table_num = abbrev_index // 32  # 0, 1, or 2
                    table_index = abbrev_index % 32
                    abbrev_zchar = 1 + table_num  # Z-char 1, 2, or 3
                    zchars.extend([abbrev_zchar, table_index])
                    i += abbrev_length
                    continue

            # No abbreviation match - encode character normally
            ch = text[i]
            ch_zchars, current_alphabet = self.char_to_zchar(ch, current_alphabet)
            zchars.extend(ch_zchars)
            i += 1

        # Pad to multiple of 3
        while len(zchars) % 3 != 0:
            zchars.append(5)  # Padding character

        # If max_words specified, truncate or pad
        if max_words:
            max_zchars = max_words * 3
            if len(zchars) > max_zchars:
                zchars = zchars[:max_zchars]
            while len(zchars) < max_zchars:
                zchars.append(5)

        # Pack into 16-bit words (3 z-chars per word)
        words = []
        for i in range(0, len(zchars), 3):
            z0 = zchars[i] if i < len(zchars) else 5
            z1 = zchars[i+1] if i+1 < len(zchars) else 5
            z2 = zchars[i+2] if i+2 < len(zchars) else 5

            # Pack: bit 15 = end marker, bits 14-10 = z0, bits 9-5 = z1, bits 4-0 = z2
            word = (z0 << 10) | (z1 << 5) | z2

            # Set end marker on last word
            if i + 3 >= len(zchars):
                word |= 0x8000

            words.append(word)

        return words

    def encode_dictionary_word(self, word: str) -> List[int]:
        """
        Encode a word for dictionary storage.

        V1-3: 2 words (6 Z-characters)
        V4+: 3 words (9 Z-characters)
        """
        max_words = 2 if self.version <= 3 else 3
        return self.encode_string(word, max_words)

    def encode_text_zchars(self, text: str, use_abbreviations: bool = False,
                            literal: bool = False) -> bytes:
        """
        Encode text to Z-character bytes (for abbreviation strings).

        Args:
            text: Text to encode
            use_abbreviations: Whether to use abbreviations (False for encoding abbreviations themselves)
            literal: If True, skip all text transformations (for abbreviation strings)

        Returns:
            Bytes of encoded text
        """
        words = self.encode_string(text, use_abbreviations=use_abbreviations, literal=literal)
        return words_to_bytes(words)


def encode_string(text: str, version: int = 3) -> List[int]:
    """Convenience function to encode a string."""
    encoder = ZTextEncoder(version)
    return encoder.encode_string(text)


def encode_dictionary_word(word: str, version: int = 3) -> List[int]:
    """Convenience function to encode a dictionary word."""
    encoder = ZTextEncoder(version)
    return encoder.encode_dictionary_word(word)


def words_to_bytes(words: List[int]) -> bytes:
    """Convert list of 16-bit words to bytes (big-endian)."""
    result = bytearray()
    for word in words:
        result.append((word >> 8) & 0xFF)
        result.append(word & 0xFF)
    return bytes(result)


def decode_string(words: List[int], version: int = 3) -> str:
    """
    Decode Z-character words back to string (for testing/debugging).

    This is a simplified decoder for testing purposes.
    """
    encoder = ZTextEncoder(version)
    zchars = []

    for word in words:
        z0 = (word >> 10) & 0x1F
        z1 = (word >> 5) & 0x1F
        z2 = word & 0x1F

        zchars.extend([z0, z1, z2])

        # Check end marker
        if word & 0x8000:
            break

    # Decode Z-characters to string
    result = []
    current_alphabet = 0
    i = 0

    while i < len(zchars):
        zc = zchars[i]

        if zc == 0:
            result.append(' ')
            i += 1
        elif version == 1 and zc == 1:
            # V1: z-char 1 is newline
            result.append('\n')
            i += 1
        elif version <= 2 and zc == 2:
            # V1-2: z-char 2 = temp shift up (A0->A1, A1->A2, A2->A0)
            i += 1
            if i < len(zchars):
                next_zc = zchars[i]
                next_alpha = (current_alphabet + 1) % 3
                alphabet = [encoder.alphabet_a0, encoder.alphabet_a1, encoder.alphabet_a2][next_alpha]
                if next_alpha == 2 and next_zc == 6:
                    # ZSCII escape
                    if i + 2 < len(zchars):
                        high = zchars[i+1]
                        low = zchars[i+2]
                        zscii = (high << 5) | low
                        if 32 <= zscii < 127:
                            result.append(chr(zscii))
                        i += 3
                    else:
                        i += 1
                elif next_zc < len(alphabet):
                    result.append(alphabet[next_zc])
                    i += 1
                else:
                    i += 1
        elif version <= 2 and zc == 3:
            # V1-2: z-char 3 = temp shift down (A0->A2, A1->A0, A2->A1)
            i += 1
            if i < len(zchars):
                next_zc = zchars[i]
                next_alpha = (current_alphabet + 2) % 3
                alphabet = [encoder.alphabet_a0, encoder.alphabet_a1, encoder.alphabet_a2][next_alpha]
                if next_alpha == 2 and next_zc == 6:
                    # ZSCII escape
                    if i + 2 < len(zchars):
                        high = zchars[i+1]
                        low = zchars[i+2]
                        zscii = (high << 5) | low
                        if 32 <= zscii < 127:
                            result.append(chr(zscii))
                        i += 3
                    else:
                        i += 1
                elif next_zc < len(alphabet):
                    result.append(alphabet[next_zc])
                    i += 1
                else:
                    i += 1
        elif version <= 2 and zc == 4:
            # V1-2: z-char 4 = shift lock up (A0->A1, A1->A2, A2->A0)
            current_alphabet = (current_alphabet + 1) % 3
            i += 1
        elif version <= 2 and zc == 5:
            # V1-2: z-char 5 = shift lock down (A0->A2, A1->A0, A2->A1)
            current_alphabet = (current_alphabet + 2) % 3
            i += 1
        elif zc == 4:
            # V3+: temporary shift to A1 for next char only
            i += 1
            if i < len(zchars):
                next_zc = zchars[i]
                if next_zc < len(encoder.alphabet_a1):
                    result.append(encoder.alphabet_a1[next_zc])
                i += 1
        elif zc == 5:
            # V3+: temporary shift to A2 for next char only
            i += 1
            if i < len(zchars):
                next_zc = zchars[i]
                if next_zc == 6:
                    # ZSCII escape in A2
                    if i + 2 < len(zchars):
                        high = zchars[i+1]
                        low = zchars[i+2]
                        zscii = (high << 5) | low
                        if 32 <= zscii < 127:
                            result.append(chr(zscii))
                        i += 3
                    else:
                        i += 1
                elif next_zc < len(encoder.alphabet_a2):
                    result.append(encoder.alphabet_a2[next_zc])
                    i += 1
                else:
                    i += 1
        else:
            # Regular character lookup in current alphabet
            alphabet = [encoder.alphabet_a0, encoder.alphabet_a1, encoder.alphabet_a2][current_alphabet]
            if zc < len(alphabet):
                result.append(alphabet[zc])
            i += 1

    return ''.join(result).rstrip('\x05 ')  # Remove padding
