"""
Z-machine text encoding (ZSCII and Z-characters).

Converts strings to Z-machine compressed text format using 5-bit Z-characters
packed into 16-bit words.
"""

from typing import List, Tuple


# Default alphabet tables for versions 1-4
ALPHABET_A0 = " abcdefghijklmnopqrstuvwxyz"
ALPHABET_A1 = " ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHABET_A2 = " \n0123456789.,!?_#'\"/\\-:()"


class ZTextEncoder:
    """Encodes text to Z-machine format."""

    def __init__(self, version: int = 3):
        self.version = version
        self.alphabet_a0 = ALPHABET_A0
        self.alphabet_a1 = ALPHABET_A1
        self.alphabet_a2 = ALPHABET_A2

    def char_to_zchar(self, ch: str, current_alphabet: int = 0) -> Tuple[List[int], int]:
        """
        Convert a character to Z-characters.

        Returns: (list of z-characters, new alphabet)
        """
        # Try current alphabet first
        if current_alphabet == 0 and ch in self.alphabet_a0:
            return ([self.alphabet_a0.index(ch)], 0)
        elif current_alphabet == 1 and ch in self.alphabet_a1:
            return ([self.alphabet_a1.index(ch)], 1)
        elif current_alphabet == 2 and ch in self.alphabet_a2:
            return ([self.alphabet_a2.index(ch)], 2)

        # Try other alphabets with shift
        if ch in self.alphabet_a0:
            if self.version <= 2:
                # Permanent shift
                return ([4], 0)  # Shift to A0
            else:
                # Temporary shift (V3+)
                return ([4, self.alphabet_a0.index(ch)], current_alphabet)

        if ch in self.alphabet_a1:
            if self.version <= 2:
                return ([5], 1)  # Shift to A1
            else:
                return ([5, self.alphabet_a1.index(ch)], current_alphabet)

        if ch in self.alphabet_a2:
            if self.version <= 2:
                return ([4, 5], 2)  # Double shift to A2
            else:
                # For V3+, use alphabet 2 shift
                idx = self.alphabet_a2.index(ch)
                return ([4, 4 if current_alphabet == 0 else 5, idx], current_alphabet)

        # Character not in alphabets - use ZSCII escape
        zscii_code = ord(ch)
        high = (zscii_code >> 5) & 0x1F
        low = zscii_code & 0x1F

        # Shift to A2, then Z-char 6 (ZSCII escape), then two 5-bit values
        if current_alphabet != 2:
            return ([5, 6, high, low], current_alphabet)
        else:
            return ([6, high, low], current_alphabet)

    def encode_string(self, text: str, max_words: int = None) -> List[int]:
        """
        Encode a string to Z-characters packed into 16-bit words.

        Args:
            text: The string to encode
            max_words: Maximum number of 16-bit words (for dictionary entries)

        Returns:
            List of 16-bit words with Z-characters packed in
        """
        # Convert string to Z-characters
        zchars = []
        current_alphabet = 0

        for ch in text:
            ch_zchars, current_alphabet = self.char_to_zchar(ch.lower(), current_alphabet)
            zchars.extend(ch_zchars)

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
        elif zc == 4:
            # Shift to next alphabet (or A0)
            if version <= 2:
                current_alphabet = 0
            else:
                # Temporary shift - will be handled by next character
                pass
            i += 1
        elif zc == 5:
            # Shift to alphabet 1 (permanent in V1-2, temp in V3+)
            if version <= 2:
                current_alphabet = 1
            i += 1
        elif zc == 6 and current_alphabet == 2:
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
        else:
            # Regular character lookup
            alphabet = [encoder.alphabet_a0, encoder.alphabet_a1, encoder.alphabet_a2][current_alphabet]
            if zc < len(alphabet):
                result.append(alphabet[zc])
            i += 1

            # Reset to A0 for V3+ after temporary shift
            if version >= 3:
                current_alphabet = 0

    return ''.join(result).rstrip('\x05 ')  # Remove padding
