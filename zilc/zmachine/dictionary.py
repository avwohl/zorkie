"""
Z-machine dictionary builder.

Builds the dictionary table with word separators and encoded words.
"""

from typing import List, Set, Dict
import re
import struct
import sys
from .text_encoding import ZTextEncoder


class Dictionary:
    """Builds Z-machine dictionary."""

    def __init__(self, version: int = 3, new_parser: bool = False,
                 word_flags_in_table: bool = False, one_byte_parts_of_speech: bool = False,
                 sibreaks: str = '', custom_alphabets: dict = None, language: str = None):
        self.version = version
        self.encoder = ZTextEncoder(version, custom_alphabets=custom_alphabets, language=language)
        # Default separators plus SIBREAKS (self-inserting breaks)
        # SIBREAKS characters both act as separators AND become words themselves
        default_separators = '.,"'
        seps = []
        for c in default_separators + (sibreaks or ''):
            if c != '\\' and c not in seps:
                seps.append(c)
        self.separators = [ord(c) for c in seps]
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

        # Track preposition numbers: prep_word -> preposition_number (1, 2, ...)
        # Preposition number is stored in dictionary byte 5 for parser lookups
        self.preposition_numbers: Dict[str, int] = {}

        # Collision warnings generated during build
        self.collision_warnings: List[tuple] = []  # List of (code, message)

    def _norm(self, word: str) -> str:
        """Normalize a vocabulary word to its canonical dictionary spelling.

        In ZIL a backslash quotes the next character inside an atom, so
        FROG\\'S names the word FROG'S. Callers reach the dictionary with a
        MIX of escaped and unescaped spellings (SYNONYM lists, THINGS/PSEUDO
        <VOC ...> prescans, W?* code references), and keying them differently
        split one word into two entries: LGOP's THINGS adjective FROG\\'S was
        stored (and z-encoded!) WITH the backslash, then the W?FROG'S fixup
        pass could not find the unescaped spelling and late-added "frog's"
        AFTER the word-offset snapshot used for SYNONYM property fixups --
        the insertion re-sorted the dictionary and shifted every entry after
        it by one, so nouns resolved to the alphabetically preceding word
        ("take stool" -> W?STONE: "You can't see any stool here!").
        Unescaping at this single choke point makes every spelling of a word
        land on one entry, and emits the real character (the typed input
        "frog's" can actually match its entry).
        """
        if '\\' in word:
            word = re.sub(r'\\(.)', r'\1', word)
        return word.lower()

    def add_word(self, word: str, word_type: str = 'unknown', obj_num: int = None):
        """Add a word to the dictionary with optional type and object reference.

        Args:
            word: The word to add
            word_type: Type of word (noun, verb, adjective, etc.)
            obj_num: Object number this word refers to (for SYNONYM)
        """
        word_lower = self._norm(word)
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
        """Add an ADJECTIVE word. Keep the adjective value in its own
        slot (adjective_values); word_objects is the NOUN value slot and the
        old shared write let a later add_synonym clobber the A?-number
        (zork3 'stone': A?STONE=26 lost to ROCK's object number 138, so
        THIS-IT? never matched "stone door")."""
        wl = self._norm(adjective)
        self.add_word(wl, 'adjective', None)
        if not hasattr(self, 'adjective_values'):
            self.adjective_values = {}
        self.adjective_values[wl] = obj_num

    def add_verb(self, word: str, verb_number: int):
        """Add a verb word with its verb number.

        The verb number is stored in dictionary byte 5 and is used by the
        parser to look up syntax entries via VTBL.

        Args:
            word: The verb word (e.g., 'TAKE')
            verb_number: The verb number (255, 254, 253, ...)
        """
        word_lower = self._norm(word)
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
        synonym_lower = self._norm(synonym)
        main_lower = self._norm(main_verb)

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
        word_lower = self._norm(word)
        self.words.add(word_lower)
        if word_lower not in self.word_types:
            self.word_types[word_lower] = set()
        self.word_types[word_lower].add('direction')
        self.word_objects[word_lower] = prop_num
        # A word can be BOTH a direction and an adjective/synonym of an object
        # (minizork: WEST is a direction AND an object adjective in
        # `(ADJECTIVE WOODEN GOTHIC STRANGE WEST)`). Those registrations share
        # word_objects and the last write wins, clobbering the direction property
        # number -- byte 5 then held the adjective id, so <WT? WRD PS?DIRECTION>
        # returned garbage and westward movement failed. Keep the direction value
        # separately; it is DirectionFirst, so it owns byte 5.
        if not hasattr(self, 'direction_values'):
            self.direction_values = {}
        self.direction_values[word_lower] = prop_num

    def add_preposition(self, word: str, prep_number: int):
        """Add a preposition word with its preposition number (PR? value).

        The preposition number is stored in dictionary byte 5 and is used
        by the parser to match syntax patterns.

        Args:
            word: The preposition word (e.g., 'ON', 'IN', 'WITH')
            prep_number: The preposition number (1, 2, 3, ...)
        """
        word_lower = self._norm(word)
        self.add_word(word_lower, 'preposition')
        self.preposition_numbers[word_lower] = prep_number

    def _compute_type_byte(self, word_types: Set[str]) -> int:
        """Compute the type byte for a set of word types.

        Args:
            word_types: Set of word types (noun, verb, adjective, etc.)

        Returns:
            The type byte with all applicable flags set
        """
        type_byte = 0

        # Set every present part-of-speech flag.
        has_noun = 'noun' in word_types or 'synonym' in word_types
        has_verb = 'verb' in word_types
        has_adj = 'adjective' in word_types or 'adj' in word_types
        has_dir = 'direction' in word_types or 'dir' in word_types
        if has_noun:
            type_byte |= 0x80  # Object = 128
        if has_verb:
            type_byte |= 0x40  # Verb = 64
        if has_adj:
            type_byte |= 0x20  # Adjective = 32
        if has_dir:
            type_byte |= 0x10  # Direction = 16
        for word_type in word_types:
            if word_type in ('preposition', 'prep'):
                type_byte |= 0x08  # Preposition = 8
            elif word_type == 'buzz':
                type_byte |= 0x04  # Buzzword = 4
            elif word_type not in ('unknown', 'noun', 'synonym', 'verb',
                                    'adjective', 'adj', 'direction', 'dir'):
                print(f"[dictionary] Warning: Unrecognized word type '{word_type}' - using no flags",
                      file=sys.stderr)

        # The "first" (primary) flag in bits 0-1 decides which value the parser
        # reads from byte 5 (P1) vs byte 6 (P2). It MUST be deterministic and match
        # the byte-5 two-slot encoding in build(): preposition (P1 code 0) >
        # direction (3) > verb (1) > adjective (2) > object (0). Official Infocom
        # dicts confirm: "in" (dir+prep) is prep-first with P?IN in byte 6;
        # "west" (dir+adj) is DirectionFirst with the adjective id in byte 6.
        # (Iterating the word_types SET previously picked a hash-order-dependent
        # primary, so WEST sometimes encoded AdjectiveFirst and westward movement
        # silently failed.)
        has_prep = 'preposition' in word_types or 'prep' in word_types
        if has_prep:
            pass  # PrepositionFirst shares P1 code 0 -- low bits stay 0
        elif has_dir:
            type_byte |= 0x03  # DirectionFirst = 3
        elif has_verb:
            type_byte |= 0x01  # VerbFirst = 1
        elif has_adj:
            type_byte |= 0x02  # AdjectiveFirst = 2

        return type_byte

    def build(self) -> bytes:
        """Build dictionary bytes."""
        # Alias words from top-level <SYNONYM HEAD alias...> that ended up
        # with NO part of speech inherit the head word's types and values
        # (zork3 "master, go ..." needed 'go' to stay a pure verb alias;
        # starcross's <SYNONYM WITH USING THROUGH> shares WITH's prep number).
        for _grp in getattr(self, 'synonym_alias_groups', []) or []:
            _head = _grp[0]
            _htypes = self.word_types.get(_head, set()) - {'unknown'}
            if not _htypes:
                continue
            for _al in _grp[1:]:
                _atypes = self.word_types.get(_al, set()) - {'unknown'}
                if _atypes:
                    continue
                self.word_types[_al] = set(_htypes)
                if _head in self.word_objects and _al not in self.word_objects:
                    self.word_objects[_al] = self.word_objects[_head]
                _av = getattr(self, 'adjective_values', {})
                if _head in _av and _al not in _av:
                    _av[_al] = _av[_head]
                if _head in self.verb_numbers and _al not in self.verb_numbers:
                    self.verb_numbers[_al] = self.verb_numbers[_head]
                if _head in self.preposition_numbers and _al not in self.preposition_numbers:
                    self.preposition_numbers[_al] = self.preposition_numbers[_head]
                _dv = getattr(self, 'direction_values', {})
                if _head in _dv and _al not in _dv:
                    _dv[_al] = _dv[_head]
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
        # Sort by the ENCODED z-char bytes (the tuple key), not the source string.
        # A positive entry count tells the interpreter to binary-search, which
        # requires entries ascending by encoded-text prefix (big-endian). The
        # encoded tuple is a sequence of 16-bit words in order, so tuple
        # comparison is equivalent to big-endian byte comparison.
        for encoded, words in sorted(encoded_groups.items(), key=lambda x: x[0]):
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

            # Find preposition number from colliding words
            prep_num = 0
            for w in encoded_words:
                if w in self.preposition_numbers:
                    prep_num = self.preposition_numbers[w]
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

                # Bytes 2-3 (dict bytes 5-6): the classic TWO-SLOT value scheme.
                # A word can carry values for several parts of speech at once; byte 5
                # holds the value of the "first" PoS (whose P1? code is stored in the
                # type byte's low 2 bits) and byte 6 holds the value of ONE other PoS.
                # WT? (parser.zil) reads byte 5 when the requested P1? code equals the
                # first-code, byte 6 otherwise. The old single-value encoding dropped
                # the second value: "in" (direction+preposition) had its PR?IN lost,
                # so <PUT X IN Y> died with [You used the word "in" in a way...], and
                # official builds confirm the scheme (minizork.z3 "in": b5=prep,
                # b6=P?IN; "west": b5=P?WEST, b6=adjective; "light": obj + verb).
                #
                # First-slot priority (must match _compute_type_byte): preposition
                # (P1 code 0) > direction (3) > verb (1) > adjective (2) > object (0).
                dvals = getattr(self, 'direction_values', {})
                dir_val = None
                if 'direction' in word_types or 'dir' in word_types:
                    dir_val = obj_num
                    for w in encoded_words:
                        if w in dvals:
                            dir_val = dvals[w]
                            break
                has_prep = ('preposition' in word_types or 'prep' in word_types) and prep_num > 0
                has_verb = 'verb' in word_types and verb_num > 0
                has_adj = 'adjective' in word_types or 'adj' in word_types
                has_obj = 'noun' in word_types or 'synonym' in word_types
                # Adjective value has its own slot (adjective_values),
                # separate from the noun value (word_objects) -- a word that is
                # BOTH (zork3 'stone', starcross 'computer') keeps the A?-id in
                # the primary slot and the noun value in the second.
                avals = getattr(self, 'adjective_values', {})
                adj_val = obj_num
                for w in encoded_words:
                    if w in avals:
                        adj_val = avals[w]
                        break
                slots = []
                if has_prep:
                    slots.append(('prep', prep_num))
                if dir_val is not None:
                    slots.append(('dir', dir_val))
                if has_verb:
                    slots.append(('verb', verb_num))
                if has_adj:
                    slots.append(('adj', adj_val))
                if has_obj:
                    # The classic parser's object P1 value must be NONZERO.
                    # GET-OBJECT promotes an adjective to a noun only when
                    # <WT? word PS?OBJECT P1?OBJECT> -- the object VALUE byte --
                    # is nonzero (parser.zil), and other paths test it inside
                    # <NOT <ZERO? ...>>. A PSEUDO noun carries no object number
                    # (word_objects == 0), so its object slot came out 0 and
                    # "answer dimithio" (a THINGS pseudo word that is BOTH a noun
                    # and an adjective, entered alone) could not be promoted --
                    # "There seems to be a noun missing in that sentence."
                    # Every official Infocom dict stores the constant 1 for an
                    # object word's value byte; mirror that when there is no
                    # object number to place.
                    slots.append(('obj', obj_num or 1))
                if not slots:
                    slots.append(('obj', obj_num))
                first = slots[0]
                # Second slot: highest-priority OTHER value, preferring
                # dir > verb > adj > obj (matches what the official dicts keep).
                second_val = 0
                for kind in ('dir', 'verb', 'adj', 'obj', 'prep'):
                    for k, v in slots[1:]:
                        if k == kind:
                            second_val = v
                            break
                    if second_val:
                        break
                result.append(first[1] & 0xFF)
                result.append(second_val & 0xFF)

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
        word_lower = self._norm(word)
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

        # Get unique words in EMITTED order (same as in build()): grouped by
        # encoded form, then ordered by the encoded z-char bytes (the tuple key).
        groups = {}
        for w in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(w))
            if encoded not in groups:
                groups[encoded] = w  # first source word of the group
        unique_words = [w for _enc, w in sorted(groups.items(), key=lambda kv: kv[0])]

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

        # Get unique words in EMITTED order (same as in build()): group words
        # by encoded form, then order the groups by their encoded z-char bytes
        # (the tuple key) so the offsets match the binary-search layout.
        groups = {}  # encoded tuple -> first source word of the group
        for w in sorted(self.words):
            encoded = tuple(self.encoder.encode_dictionary_word(w))
            if encoded not in groups:
                groups[encoded] = w
        unique_words = []
        seen_encoded = {}  # encoded tuple -> (first_word, offset_idx)
        for encoded, w in sorted(groups.items(), key=lambda kv: kv[0]):
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
