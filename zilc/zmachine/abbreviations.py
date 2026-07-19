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


def _frequent_substrings(corpus):
    """Count occurrences of every substring (length 2.._MAXL) that appears at
    least twice, using an Apriori sweep by length to bound memory."""
    counts = collections.Counter()
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
    return counts


def _dp_zchars(s, by_first):
    """Minimum z-chars to encode `s` given abbreviations grouped by first
    character in `by_first` (each reference costs 2 z-chars).  Mirrors the
    encoder's DP-optimal application."""
    n = len(s)
    dp = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        best = dp[i + 1] + _zl(s[i])
        for a in by_first.get(s[i], ()):
            L = len(a)
            if i + L <= n and s.startswith(a, i):
                c = dp[i + L] + 2
                if c < best:
                    best = c
        dp[i] = best
    return dp[0]



class AbbreviationsTable:
    """Manages abbreviation selection and encoding for Z-machine."""

    def __init__(self):
        self.abbreviations: List[str] = []  # The 96 abbreviation strings
        self.lookup: Dict[str, int] = {}  # Maps string -> abbreviation index
        self.encoded_strings: List[bytes] = []  # Encoded abbreviation strings

    def analyze_strings(self, strings, max_abbrevs=96):
        # Deduplicate: each unique string is stored (and encoded) once.
        corpus = [s for s in dict.fromkeys(strings) if isinstance(s, str) and len(s) >= 2]

        # Compute candidate abbreviation sets and keep whichever encodes the
        # whole corpus smallest.  A precomputed ZILCH freq.xzap list (if any)
        # and a fresh greedy/iterative pass frequently disagree on which is
        # best per game, so both are scored against the real encoded-word cost
        # (DP-optimal application, per-string padding to a word boundary) and
        # the cheaper one wins.  Abbreviations are transparent to runtime
        # behaviour, so any valid set is correct -- only size differs.  The
        # selection is fully deterministic (no dependence on hash-seed / dict
        # ordering), so a given source always yields byte-identical output.
        candidates = []
        greedy = self._greedy_select(corpus, max_abbrevs)
        if greedy:
            candidates.append(greedy)
        freq = self._freq_select(max_abbrevs)
        if freq:
            candidates.append(freq)
        celf = self._celf_select(corpus, max_abbrevs)
        if celf:
            candidates.append(celf)
        if not candidates:
            self.abbreviations = []
            self.lookup = {}
            return
        best = min(candidates, key=lambda ab: self._corpus_cost(corpus, ab))
        self.abbreviations = list(best)
        self.lookup = {w: i for i, w in enumerate(best)}
        return

    def _freq_select(self, max_abbrevs):
        """ZILCH-precomputed freq.xzap .FSTR abbreviation list, if present."""
        _p = getattr(self, 'freq_xzap', None)
        if _p is None:
            return None
        try:
            import re as _re
            _words = [m.group(1) for m in
                      _re.finditer(r'\.FSTR\s+FSTR\?\d+,"((?:[^"\\]|\\.)*)"',
                                   open(_p).read())]
            _words = [w for w in _words if w][:max_abbrevs]
            if len(_words) >= 8:
                return _words
        except Exception:
            pass
        return None

    def _corpus_cost(self, corpus, abbrevs):
        """Total encoded size of `corpus` under `abbrevs`, in z-chars, with
        each string padded to a 3-z-char word boundary, plus the cost of
        storing the abbreviation strings themselves (also padded).  Mirrors the
        encoder's DP-optimal abbreviation application, so a smaller cost here
        corresponds to fewer bytes emitted."""
        by_first = {}
        for a in abbrevs:
            if a:
                by_first.setdefault(a[0], []).append(a)
        total = 0
        for s in corpus:
            z = _dp_zchars(s, by_first)
            total += z + (-z) % 3
        for a in abbrevs:
            z = _zlen(a)
            total += z + (-z) % 3
        return total

    def _celf_select(self, corpus, max_abbrevs):
        """CELF-style lazy-greedy abbreviation pass ranked by TRUE marginal
        gain.

        Unlike `_greedy_select` (which scores candidates with the closed-form
        `cnt * (z - 2) - stored` estimate over sentinel-collapsed text), this
        pass evaluates each candidate's actual reduction of the same cost that
        `_corpus_cost` measures: DP-optimal abbreviation application per
        string, per-string padding to a 3-z-char word boundary, minus the
        padded storage cost of the abbreviation string itself.  The closed-form
        estimate is only used as an optimistic upper bound to order the lazy
        re-evaluations (CELF): a candidate is accepted only when its freshly
        computed true gain still tops every other candidate's bound.

        Fully deterministic: heap entries are (-gain, text) so ties break on
        the candidate text, never on dict/set iteration order.
        """
        import heapq

        counts = _frequent_substrings(corpus)
        if not counts:
            return []

        def _pad(z):
            return z + (-z) % 3

        # Optimistic initial bounds (an upper bound on the true gain: every
        # counted -- possibly overlapping -- occurrence saving the full z - 2,
        # with no padding loss).
        heap = []
        for sub, cnt in counts.items():
            z = _zlen(sub)
            if z <= 2 or cnt < 2:
                continue
            bound = cnt * (z - 2) - _pad(z)
            if bound > 0:
                heap.append((-bound, sub))
        heapq.heapify(heap)

        # Per-string current encoded cost under the chosen-so-far set.  With
        # no abbreviations the DP degenerates to the plain z-char length.
        cost = [_pad(_zlen(s)) for s in corpus]
        by_first = {}
        occurrences = {}   # sub -> indices of corpus strings containing it
        fresh_at = {}      # sub -> version its heap gain was evaluated at
        chosen = set()
        version = 0
        abbreviations = []

        def _true_gain(sub):
            idxs = occurrences.get(sub)
            if idxs is None:
                idxs = [i for i, s in enumerate(corpus) if sub in s]
                occurrences[sub] = idxs
            trial = dict(by_first)
            trial[sub[0]] = trial.get(sub[0], []) + [sub]
            gain = 0
            for i in idxs:
                gain += cost[i] - _pad(_dp_zchars(corpus[i], trial))
            return gain - _pad(_zlen(sub))

        while heap and len(abbreviations) < max_abbrevs:
            neg, sub = heapq.heappop(heap)
            if sub in chosen:
                continue
            if fresh_at.get(sub) == version:
                if -neg <= 0:
                    break
                abbreviations.append(sub)
                chosen.add(sub)
                by_first.setdefault(sub[0], []).append(sub)
                for i in occurrences[sub]:
                    cost[i] = _pad(_dp_zchars(corpus[i], by_first))
                version += 1
            else:
                gain = _true_gain(sub)
                if gain > 0:
                    fresh_at[sub] = version
                    heapq.heappush(heap, (-gain, sub))

        # Polish: swap the weakest chosen abbreviation for the best remaining
        # candidate while that strictly lowers the true cost.  Marginal gains
        # are not perfectly submodular here (per-string word padding), so the
        # lazy pass above can strand a slightly better candidate; a few
        # bounded exchange rounds recover it.  Fully deterministic (ties break
        # on the candidate text).
        for _round in range(24):
            if not abbreviations:
                break
            contrib = {}
            for a in abbreviations:
                bf2 = {k: [x for x in v if x != a] for k, v in by_first.items()}
                loss = 0
                for i in occurrences[a]:
                    loss += _pad(_dp_zchars(corpus[i], bf2)) - cost[i]
                contrib[a] = loss - _pad(_zlen(a))
            worst = min(abbreviations, key=lambda a: (contrib[a], a))
            floor = contrib[worst]
            cand_heap = []
            for sub, cnt in counts.items():
                if sub in chosen:
                    continue
                z = _zlen(sub)
                if z <= 2:
                    continue
                b = cnt * (z - 2) - _pad(z)
                if b > floor:
                    cand_heap.append((-b, sub))
            heapq.heapify(cand_heap)
            evaluated = set()
            best_add = None
            while cand_heap:
                nb, sub = heapq.heappop(cand_heap)
                if sub in evaluated:
                    best_add = (sub, -nb)
                    break
                gain = _true_gain(sub)
                if gain > floor:
                    evaluated.add(sub)
                    heapq.heappush(cand_heap, (-gain, sub))
            if best_add is None or best_add[1] <= floor:
                break
            sub = best_add[0]
            abbreviations.remove(worst)
            chosen.discard(worst)
            by_first[worst[0]].remove(worst)
            for i in occurrences[worst]:
                cost[i] = _pad(_dp_zchars(corpus[i], by_first))
            abbreviations.append(sub)
            chosen.add(sub)
            by_first.setdefault(sub[0], []).append(sub)
            for i in occurrences[sub]:
                cost[i] = _pad(_dp_zchars(corpus[i], by_first))

        return abbreviations

    def _greedy_select(self, corpus, max_abbrevs):
        """Fresh greedy/iterative abbreviation pass.  Returns a list of
        abbreviation strings (does not mutate self)."""
        counts = _frequent_substrings(corpus)

        def score(sub, cnt):
            z = _zlen(sub)
            if z <= 2:
                return -1
            stored = z + (-z) % 3          # abbrev string padded to a full word
            return cnt * (z - 2) - stored - 3   # z-char units; 3 ~ table entry

        work = list(corpus)
        abbreviations = []

        for _pick in range(max_abbrevs):
            best = None
            best_key = None
            for sub, cnt in counts.items():
                if cnt < 2:
                    continue
                sc = score(sub, cnt)
                if sc <= 0:                 # only positive net savings (as before)
                    continue
                # Deterministic selection: rank by (score, count, length,
                # text).  The final text key gives a total order, so the pick
                # never depends on dict/set iteration order (hash seed) -- the
                # output is byte-stable across runs.
                key = (sc, cnt, len(sub), sub)
                if best_key is None or key > best_key:
                    best_key = key
                    best = sub
            if best is None:
                break
            abbreviations.append(best)
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

        return abbreviations

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
