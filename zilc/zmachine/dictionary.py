"""
Z-machine dictionary builder.

Builds the dictionary table with word separators and encoded words.
"""

from typing import List, Set
import struct
from .text_encoding import ZTextEncoder


class Dictionary:
    """Builds Z-machine dictionary."""

    def __init__(self, version: int = 3):
        self.version = version
        self.encoder = ZTextEncoder(version)
        self.separators = [ord(c) for c in '.,;:?!()[]{}']  # Default separators
        self.words: Set[str] = set()

    def add_word(self, word: str):
        """Add a word to the dictionary."""
        self.words.add(word.lower())

    def add_words(self, words: List[str]):
        """Add multiple words to the dictionary."""
        for word in words:
            self.add_word(word)

    def build(self) -> bytes:
        """Build dictionary bytes."""
        result = bytearray()

        # Number of word separators
        result.append(len(self.separators))

        # Word separator ZSCII codes
        for sep in self.separators:
            result.append(sep)

        # Entry length
        # V1-3: 4 bytes text + n bytes data (we use 4 total)
        # V4+: 6 bytes text + n bytes data (we use 6 total)
        entry_length = 4 if self.version <= 3 else 6
        result.append(entry_length)

        # Number of entries
        word_list = sorted(self.words)
        result.extend(struct.pack('>H', len(word_list)))

        # Encode and add words
        for word in word_list:
            encoded = self.encoder.encode_dictionary_word(word)
            for w in encoded:
                result.extend(struct.pack('>H', w))

        return bytes(result)
