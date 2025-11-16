"""
Z-machine dictionary builder.

Builds the dictionary table with word separators and encoded words.
"""

from typing import List, Set, Dict
import struct
from .text_encoding import ZTextEncoder


class Dictionary:
    """Builds Z-machine dictionary."""

    def __init__(self, version: int = 3):
        self.version = version
        self.encoder = ZTextEncoder(version)
        self.separators = [ord(c) for c in '.,;:?!()[]{}']  # Default separators
        self.words: Set[str] = set()

        # Track word types (for parser)
        self.word_types: Dict[str, str] = {}  # word -> type (noun, verb, adj, etc.)
        self.word_objects: Dict[str, int] = {}  # word -> object number (for nouns)

    def add_word(self, word: str, word_type: str = 'unknown', obj_num: int = None):
        """Add a word to the dictionary with optional type and object reference.

        Args:
            word: The word to add
            word_type: Type of word (noun, verb, adjective, etc.)
            obj_num: Object number this word refers to (for SYNONYM)
        """
        word_lower = word.lower()
        self.words.add(word_lower)

        if word_type:
            self.word_types[word_lower] = word_type

        if obj_num is not None:
            self.word_objects[word_lower] = obj_num

    def add_words(self, words: List[str], word_type: str = 'unknown'):
        """Add multiple words to the dictionary."""
        for word in words:
            self.add_word(word, word_type)

    def add_synonym(self, synonym: str, obj_num: int):
        """Add a SYNONYM word that refers to an object.

        Args:
            synonym: The synonym word
            obj_num: The object number this word refers to
        """
        self.add_word(synonym, 'noun', obj_num)

    def add_adjective(self, adjective: str, obj_num: int):
        """Add an ADJECTIVE word that can describe an object.

        Args:
            adjective: The adjective word
            obj_num: The object number this adjective can describe
        """
        self.add_word(adjective, 'adjective', obj_num)

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

        # Deduplicate by encoded form (not just string form)
        # In V3, "bench" and "bench-pseudo" encode to same 6 z-characters
        seen_encoded = {}
        unique_words = []
        for word in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(word))
            if encoded not in seen_encoded:
                seen_encoded[encoded] = word
                unique_words.append(word)

        result.extend(struct.pack('>H', len(unique_words)))

        # Encode and add words
        for word in unique_words:
            encoded = self.encoder.encode_dictionary_word(word)
            for w in encoded:
                result.extend(struct.pack('>H', w))

        return bytes(result)
