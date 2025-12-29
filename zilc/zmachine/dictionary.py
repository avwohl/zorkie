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

    def __init__(self, version: int = 3, new_parser: bool = False,
                 word_flags_in_table: bool = False, one_byte_parts_of_speech: bool = False,
                 sibreaks: str = ''):
        self.version = version
        self.encoder = ZTextEncoder(version)
        # Default separators plus SIBREAKS (self-inserting breaks)
        # SIBREAKS characters both act as separators AND become words themselves
        default_separators = '.,;:?!()[]{}'
        all_separators = default_separators + sibreaks
        self.separators = [ord(c) for c in all_separators]
        self.words: Set[str] = set()

        # NEW-PARSER? mode changes vocabulary format
        self.new_parser = new_parser
        self.word_flags_in_table = word_flags_in_table
        self.one_byte_parts_of_speech = one_byte_parts_of_speech

        # Track word types (for parser)
        # Each word can have multiple types (e.g., both noun and adjective if they collide)
        self.word_types: Dict[str, Set[str]] = {}  # word -> set of types
        self.word_objects: Dict[str, int] = {}  # word -> object number (for nouns)

        # Track verb synonyms: synonym_word -> main_verb_word
        # Verb synonyms share the same data bytes as their main verb
        self.verb_synonyms: Dict[str, str] = {}

        # Track verb numbers: verb_word -> verb_number (255, 254, ...)
        # Verb number is stored in dictionary byte 5 for parser lookups
        self.verb_numbers: Dict[str, int] = {}

        # Collision warnings generated during build
        self.collision_warnings: List[tuple] = []  # List of (code, message)

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
            if word_lower not in self.word_types:
                self.word_types[word_lower] = set()
            self.word_types[word_lower].add(word_type)

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

    def add_verb(self, word: str, verb_number: int):
        """Add a verb word with its verb number.

        The verb number is stored in dictionary byte 5 and is used by the
        parser to look up syntax entries via VTBL.

        Args:
            word: The verb word (e.g., 'TAKE')
            verb_number: The verb number (255, 254, 253, ...)
        """
        word_lower = word.lower()
        self.add_word(word_lower, 'verb')
        self.verb_numbers[word_lower] = verb_number

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

        # Share verb number with main verb
        if main_lower in self.verb_numbers:
            self.verb_numbers[synonym_lower] = self.verb_numbers[main_lower]

    def add_direction(self, word: str, prop_num: int):
        """Add a direction word with its property number.

        Direction words store their property number in the data bytes
        so the parser can map directions to object properties.

        Args:
            word: The direction word (e.g., 'NORTH')
            prop_num: The property number for this direction
        """
        word_lower = word.lower()
        self.words.add(word_lower)
        if word_lower not in self.word_types:
            self.word_types[word_lower] = set()
        self.word_types[word_lower].add('direction')
        self.word_objects[word_lower] = prop_num

    def _compute_type_byte(self, word_types: Set[str]) -> int:
        """Compute the type byte for a set of word types.

        Args:
            word_types: Set of word types (noun, verb, adjective, etc.)

        Returns:
            The type byte with all applicable flags set
        """
        type_byte = 0
        first_set = False

        for word_type in word_types:
            if word_type in ('noun', 'synonym'):
                type_byte |= 0x80  # Object = 128
            elif word_type == 'verb':
                type_byte |= 0x40  # Verb = 64
                if not first_set:
                    type_byte |= 0x01  # VerbFirst = 1
                    first_set = True
            elif word_type in ('adjective', 'adj'):
                type_byte |= 0x20  # Adjective = 32
                if not first_set:
                    type_byte |= 0x02  # AdjectiveFirst = 2
                    first_set = True
            elif word_type in ('direction', 'dir'):
                type_byte |= 0x10  # Direction = 16
                if not first_set:
                    type_byte |= 0x03  # DirectionFirst = 3
                    first_set = True
            elif word_type in ('preposition', 'prep'):
                type_byte |= 0x08  # Preposition = 8
            elif word_type == 'buzz':
                type_byte |= 0x04  # Buzzword = 4
            elif word_type != 'unknown':
                print(f"[dictionary] Warning: Unrecognized word type '{word_type}' - using no flags",
                      file=sys.stderr)

        return type_byte

    def build(self) -> bytes:
        """Build dictionary bytes."""
        result = bytearray()
        self.collision_warnings = []  # Reset warnings

        # Number of word separators
        result.append(len(self.separators))

        # Word separator ZSCII codes
        for sep in self.separators:
            result.append(sep)

        # Entry length
        # V1-3: 4 bytes text, V4+: 6 bytes text
        text_bytes = 4 if self.version <= 3 else 6

        if self.new_parser:
            # NEW-PARSER? format has more data bytes:
            # - SemanticStuff or AdjId/DirId: 2 bytes
            # - VerbStuff: 2 bytes
            # - Flags: 2 bytes (if WORD-FLAGS-IN-TABLE is false, else 0)
            # - Classification: 2 bytes (if ONE-BYTE-PARTS-OF-SPEECH is false, else 1)
            data_bytes = 2 + 2  # SemanticStuff + VerbStuff
            if not self.word_flags_in_table:
                data_bytes += 2  # Flags
            if self.one_byte_parts_of_speech:
                data_bytes += 1  # Classification (1 byte)
            else:
                data_bytes += 2  # Classification (2 bytes)
        else:
            # Old parser: 3 data bytes
            data_bytes = 3

        entry_length = text_bytes + data_bytes
        result.append(entry_length)

        # Group words by encoded form (to detect collisions)
        # In V3, "bench" and "bench-pseudo" encode to same 6 z-characters
        encoded_groups: Dict[tuple, List[str]] = {}
        for word in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(word))
            if encoded not in encoded_groups:
                encoded_groups[encoded] = []
            encoded_groups[encoded].append(word)

        # Detect collisions and merge types
        merged_types: Dict[tuple, Set[str]] = {}
        unique_words = []  # First word of each encoded group
        for encoded, words in sorted(encoded_groups.items(), key=lambda x: x[1][0]):
            first_word = words[0]
            unique_words.append(first_word)

            # Merge types from all colliding words
            all_types: Set[str] = set()
            for word in words:
                word_types = self.word_types.get(word, set())
                all_types.update(word_types)
            merged_types[encoded] = all_types

            # Generate collision warnings if multiple words collide
            if len(words) > 1:
                colliding = ", ".join(words)
                self.collision_warnings.append(
                    ("ZIL0310", f"Words collide (encode to same dictionary entry): {colliding}")
                )
                # Check if they have different parts of speech
                type_sets = [self.word_types.get(w, set()) for w in words]
                if len(type_sets) > 1 and any(t != type_sets[0] for t in type_sets[1:]):
                    self.collision_warnings.append(
                        ("ZIL0311", f"Colliding words have different parts of speech: {colliding}")
                    )

        result.extend(struct.pack('>H', len(unique_words)))

        # Encode and add words
        for word in unique_words:
            encoded_tuple = tuple(self.encoder.encode_dictionary_word(word))
            encoded = self.encoder.encode_dictionary_word(word)
            for w in encoded:
                result.extend(struct.pack('>H', w))

            # Add data bytes for each entry
            word_types = merged_types.get(encoded_tuple, set())
            encoded_words = encoded_groups.get(encoded_tuple, [word])

            # Find verb number from colliding words
            verb_num = 0
            for w in encoded_words:
                if w in self.verb_numbers:
                    verb_num = self.verb_numbers[w]
                    break

            # Get object/property number
            obj_num = self.word_objects.get(word, 0)
            for w in encoded_words:
                if w in self.word_objects:
                    obj_num = self.word_objects[w]
                    break

            if self.new_parser:
                # NEW-PARSER? format:
                # - SemanticStuff or AdjId/DirId: 2 bytes
                # - VerbStuff: 2 bytes
                # - Flags: 2 bytes (if WORD-FLAGS-IN-TABLE is false)
                # - Classification: 2 or 1 bytes

                # SemanticStuff (or AdjId/DirId for directions)
                if 'direction' in word_types or 'dir' in word_types:
                    result.append(obj_num & 0xFF)  # DirId
                    result.append(0)
                else:
                    result.extend(struct.pack('>H', obj_num & 0xFFFF))  # SemanticStuff

                # VerbStuff (action table pointer for verbs, 0 for non-verbs)
                if 'verb' in word_types and verb_num > 0:
                    # TODO: Should be ACT?<verb> table address
                    result.extend(struct.pack('>H', verb_num & 0xFFFF))
                else:
                    result.extend(struct.pack('>H', 0))

                # Flags (if not in separate table)
                if not self.word_flags_in_table:
                    result.extend(struct.pack('>H', 0))  # TODO: word flags

                # Classification
                type_byte = self._compute_type_byte(word_types)
                if self.one_byte_parts_of_speech:
                    result.append(type_byte)
                else:
                    result.extend(struct.pack('>H', type_byte))
            else:
                # Old parser format: 3 data bytes
                # Byte 1: lexical type flags
                type_byte = self._compute_type_byte(word_types)
                result.append(type_byte)

                # Bytes 2-3: parser info
                if 'direction' in word_types or 'dir' in word_types:
                    result.append(obj_num & 0xFF)
                    result.append(0)
                elif 'verb' in word_types and verb_num > 0:
                    result.append(verb_num & 0xFF)
                    result.append(0)
                else:
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
            Dict mapping word (lowercase) to byte offset within dictionary data.
            Includes all words added, even those that encode to the same entry
            (words with the same encoding share the same offset).
        """
        offsets = {}

        # Calculate header size
        header_size = 1 + len(self.separators) + 1 + 2

        # Entry length
        text_bytes = 4 if self.version <= 3 else 6
        data_bytes = 3
        entry_length = text_bytes + data_bytes

        # Get sorted unique words (same as in build())
        # Track which words encode to the same entry
        seen_encoded = {}  # encoded tuple -> (first_word, offset_idx)
        unique_words = []
        for w in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(w))
            if encoded not in seen_encoded:
                seen_encoded[encoded] = (w, len(unique_words))
                unique_words.append(w)

        # First assign offsets to unique words
        for idx, word in enumerate(unique_words):
            offsets[word] = header_size + idx * entry_length

        # Then add all other words that map to the same encoded form
        for w in self.words:
            if w not in offsets:
                encoded = tuple(self.encoder.encode_dictionary_word(w))
                if encoded in seen_encoded:
                    _, offset_idx = seen_encoded[encoded]
                    offsets[w] = header_size + offset_idx * entry_length

        return offsets
