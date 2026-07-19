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


import collections

_A2_EXTRA = set('\n0123456789.,!?_#\'"/\\-:()')

def _zl(ch):
    if 'a' <= ch <= 'z' or ch == ' ':
        return 1
    if 'A' <= ch <= 'Z':
        return 2
    if ch in _A2_EXTRA or ch == '|':
        return 2
    return 4


def _zlen(s):
    return sum(_zl(c) for c in s)


_MAXL = 30
_SENT = '\x00'


def _add_string_counts(counts, s, sign=1):
    n = len(s)
    for i in range(n - 1):
        if s[i] == _SENT:
            continue
        maxj = min(n, i + _MAXL)
        for j in range(i + 2, maxj + 1):
            if s[j - 1] == _SENT:
                break
            if sign > 0:
                counts[s[i:j]] += 1
            else:
                counts[s[i:j]] -= 1



class AbbreviationsTable:
    """Manages abbreviation selection and encoding for Z-machine."""

    def __init__(self):
        self.abbreviations: List[str] = []  # The 96 abbreviation strings
        self.lookup: Dict[str, int] = {}  # Maps string -> abbreviation index
        self.encoded_strings: List[bytes] = []  # Encoded abbreviation strings

    def analyze_strings(self, strings, max_abbrevs=96):
        _p = getattr(self, 'freq_xzap', None)
        if _p is not None:
            # <FREQUENT-WORDS?>: use the game's ZILCH-precomputed freq.xzap
            # .FSTR abbreviation list (historically exact selection).
            try:
                import re as _re
                _words = [m.group(1) for m in
                          _re.finditer(r'\.FSTR\s+FSTR\?\d+,"((?:[^"\\]|\\.)*)"',
                                       open(_p).read())]
                _words = [w for w in _words if w][:max_abbrevs]
                if len(_words) >= 8:
                    self.abbreviations = list(_words)
                    self.lookup = {w: i for i, w in enumerate(_words)}
                    return
            except Exception:
                pass
        # Deduplicate: each unique string is stored (and encoded) once.
        corpus = [s for s in dict.fromkeys(strings) if isinstance(s, str) and len(s) >= 2]

        # ---- initial counts, Apriori by length to bound memory ----
        counts = collections.Counter()
        # length 2 level
        lvl_prev = collections.Counter()
        for s in corpus:
            for i in range(len(s) - 1):
                lvl_prev[s[i:i + 2]] += 1
        frequent_prev = {k for k, c in lvl_prev.items() if c >= 2}
        for k in frequent_prev:
            counts[k] = lvl_prev[k]
        for L in range(3, _MAXL + 1):
            lvl = collections.Counter()
            for s in corpus:
                n = len(s)
                for i in range(n - L + 1):
                    if s[i:i + L - 1] in frequent_prev:
                        lvl[s[i:i + L]] += 1
            frequent_prev = {k for k, c in lvl.items() if c >= 2}
            if not frequent_prev:
                break
            for k in frequent_prev:
                counts[k] = lvl[k]

        def score(sub, cnt):
            z = _zlen(sub)
            if z <= 2:
                return -1
            stored = z + (-z) % 3          # abbrev string padded to a full word
            return cnt * (z - 2) - stored - 3   # z-char units; 3 ~ table entry

        work = list(corpus)
        self.abbreviations = []
        self.lookup = {}

        for _pick in range(max_abbrevs):
            best = None
            best_score = 0
            for sub, cnt in counts.items():
                if cnt < 2:
                    continue
                sc = score(sub, cnt)
                if sc > best_score:
                    best_score = sc
                    best = sub
            if best is None:
                break
            idx = len(self.abbreviations)
            self.abbreviations.append(best)
            self.lookup[best] = idx
            # Re-count only affected strings: remove their contributions, apply
            # the abbreviation (non-overlapping, left-to-right, mirroring the
            # encoder's greedy application), re-add.
            for si, s in enumerate(work):
                if best in s:
                    _add_string_counts(counts, s, sign=-1)
                    s2 = s.replace(best, _SENT)
                    work[si] = s2
                    _add_string_counts(counts, s2, sign=1)
            counts.pop(best, None)

        return

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
