"""
Z-machine dictionary builder.

Builds the dictionary table with word separators and encoded words.
"""

from typing import List, Set, Dict
import struct
import sys
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

        # Track verb synonyms: synonym_word -> main_verb_word
        # Verb synonyms share the same data bytes as their main verb
        self.verb_synonyms: Dict[str, str] = {}

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

    def add_verb_synonym(self, synonym: str, main_verb: str):
        """Add a verb synonym that shares data bytes with its main verb.

        In ZILF, verb synonyms defined in SYNTAX like:
        <SYNTAX TOSS (CHUCK) OBJECT AT OBJECT = V-TOSS>
        cause CHUCK to be a synonym of TOSS - both words have identical
        dictionary data bytes (bytes after the encoded text).

        Args:
            synonym: The synonym word (e.g., 'CHUCK')
            main_verb: The main verb word (e.g., 'TOSS')
        """
        synonym_lower = synonym.lower()
        main_lower = main_verb.lower()

        # Add the synonym as a verb
        self.add_word(synonym_lower, 'verb')

        # Track the synonym relationship
        self.verb_synonyms[synonym_lower] = main_lower

    def build(self) -> bytes:
        """Build dictionary bytes."""
        result = bytearray()

        # Number of word separators
        result.append(len(self.separators))

        # Word separator ZSCII codes
        for sep in self.separators:
            result.append(sep)

        # Entry length
        # V1-3: 4 bytes text + 3 bytes data = 7 bytes total
        # V4+: 6 bytes text + 3 bytes data = 9 bytes total
        text_bytes = 4 if self.version <= 3 else 6
        data_bytes = 3  # Standard data bytes for parser info
        entry_length = text_bytes + data_bytes
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

            # Add 3 data bytes for each entry
            # Byte 1: lexical type flags
            # Bytes 2-3: parser info (verb number, etc.)
            word_type = self.word_types.get(word, 'unknown')

            # Set type flags (ZILF PartOfSpeech format)
            # Main flags: Object=128, Verb=64, Adjective=32, Direction=16, Preposition=8, Buzzword=4
            # First flags (bits 0-1): VerbFirst=1, AdjectiveFirst=2, DirectionFirst=3
            type_byte = 0
            if word_type == 'noun':
                type_byte |= 0x80  # Object = 128
            elif word_type == 'verb':
                type_byte |= 0x40  # Verb = 64
                type_byte |= 0x01  # VerbFirst = 1
            elif word_type in ('adjective', 'adj'):
                type_byte |= 0x20  # Adjective = 32
                type_byte |= 0x02  # AdjectiveFirst = 2
            elif word_type in ('direction', 'dir'):
                type_byte |= 0x10  # Direction = 16
                type_byte |= 0x03  # DirectionFirst = 3
            elif word_type in ('preposition', 'prep'):
                type_byte |= 0x08  # Preposition = 8
            elif word_type == 'buzz':
                type_byte |= 0x04  # Buzzword = 4
            elif word_type == 'synonym':
                type_byte |= 0x80  # Synonym words act as nouns (Object)
            elif word_type != 'unknown':
                # Warn about unrecognized word types (but not 'unknown' which is the default)
                print(f"[dictionary] Warning: Unrecognized word type '{word_type}' for word '{word}' - using no flags",
                      file=sys.stderr)

            result.append(type_byte)

            # Bytes 2-3: additional parser data
            # For nouns, this could be the object number
            # For verbs, this could be the verb number
            # For now, use 0 (parser will rely on SYNTAX tables)
            obj_num = self.word_objects.get(word, 0)
            result.extend(struct.pack('>H', obj_num & 0xFFFF))

        return bytes(result)

    def get_word_offset(self, word: str) -> int:
        """Get the byte offset of a word within the dictionary data.

        This offset can be added to the dictionary base address to get the
        actual word address in the story file.

        Args:
            word: The word to find (case-insensitive)

        Returns:
            Byte offset within dictionary data, or -1 if word not found
        """
        word_lower = word.lower()
        if word_lower not in self.words:
            return -1

        # Calculate header size
        # 1 byte: number of separators
        # N bytes: separator characters
        # 1 byte: entry length
        # 2 bytes: word count
        header_size = 1 + len(self.separators) + 1 + 2

        # Entry length
        text_bytes = 4 if self.version <= 3 else 6
        data_bytes = 3
        entry_length = text_bytes + data_bytes

        # Get sorted unique words (same as in build())
        seen_encoded = {}
        unique_words = []
        for w in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(w))
            if encoded not in seen_encoded:
                seen_encoded[encoded] = w
                unique_words.append(w)

        # Find word index
        try:
            word_index = unique_words.index(word_lower)
        except ValueError:
            # Word might have same encoding as another word
            for idx, w in enumerate(unique_words):
                if w == word_lower:
                    word_index = idx
                    break
            else:
                return -1

        return header_size + word_index * entry_length

    def get_word_offsets(self) -> Dict[str, int]:
        """Get byte offsets for all words in the dictionary.

        Returns:
            Dict mapping word (lowercase) to byte offset within dictionary data
        """
        offsets = {}

        # Calculate header size
        header_size = 1 + len(self.separators) + 1 + 2

        # Entry length
        text_bytes = 4 if self.version <= 3 else 6
        data_bytes = 3
        entry_length = text_bytes + data_bytes

        # Get sorted unique words (same as in build())
        seen_encoded = {}
        unique_words = []
        for w in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(w))
            if encoded not in seen_encoded:
                seen_encoded[encoded] = w
                unique_words.append(w)

        for idx, word in enumerate(unique_words):
            offsets[word] = header_size + idx * entry_length

        return offsets
