"""
Optimization passes for Z-machine compilation.

Passes run between code generation and assembly to optimize the story file.
Each pass transforms the compiled data to reduce size or improve performance.
"""

from typing import Dict, List, Tuple, Optional, Any
from collections import Counter
import struct


class OptimizationPass:
    """Base class for optimization passes."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.stats = {}

    def log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[opt] {message}")

    def run(self, compilation_data: Dict) -> Dict:
        """
        Run the optimization pass.

        Args:
            compilation_data: Dictionary containing:
                - routines_code: bytes
                - objects_data: bytes
                - dictionary_data: bytes
                - program: parsed AST

        Returns:
            Modified compilation_data dictionary
        """
        raise NotImplementedError


class StringDeduplicationPass(OptimizationPass):
    """
    Global string deduplication optimization.

    Collects all strings from:
    - Inline PRINT instructions in routines
    - Property values in objects
    - Any other string data

    Creates a deduplicated string table and rewrites references.
    """

    def __init__(self, verbose: bool = False):
        super().__init__(verbose)
        self.string_table: Dict[str, bytes] = {}  # string -> encoded bytes
        self.string_addresses: Dict[str, int] = {}  # string -> address
        self.string_usage: Counter = Counter()  # string -> usage count

    def run(self, compilation_data: Dict) -> Dict:
        """Run string deduplication pass."""
        self.log("String Deduplication Pass")

        routines_code = compilation_data.get('routines_code', b'')
        objects_data = compilation_data.get('objects_data', b'')

        # Phase 1: Extract all strings from routines
        routine_strings = self._extract_strings_from_routines(routines_code)
        self.log(f"  Found {len(routine_strings)} strings in routines")

        # Phase 2: Extract all strings from object properties
        object_strings = self._extract_strings_from_objects(objects_data)
        self.log(f"  Found {len(object_strings)} strings in object properties")

        # Phase 3: Count string usage
        all_strings = routine_strings + object_strings
        self.string_usage = Counter(all_strings)

        total_strings = len(all_strings)
        unique_strings = len(self.string_usage)
        duplicates = total_strings - unique_strings

        self.log(f"  Total strings: {total_strings}")
        self.log(f"  Unique strings: {unique_strings}")
        if total_strings > 0:
            self.log(f"  Duplicates: {duplicates} ({duplicates/total_strings*100:.1f}%)")
        else:
            self.log(f"  Duplicates: 0 (0.0%)")

        # Phase 4: Build deduplicated string table
        string_table_data = self._build_string_table()

        # Phase 5: Rewrite routines to use string table references
        # (This would require changing PRINT to PRINT_PADDR - complex)
        # For now, just track statistics

        self.stats = {
            'total_strings': total_strings,
            'unique_strings': unique_strings,
            'duplicates': duplicates,
            'string_table_size': len(string_table_data),
            'most_common': self.string_usage.most_common(10)
        }

        # Store string table in compilation data
        compilation_data['string_table'] = string_table_data
        compilation_data['string_addresses'] = self.string_addresses
        compilation_data['dedup_stats'] = self.stats

        return compilation_data

    def _extract_strings_from_routines(self, routines_code: bytes) -> List[str]:
        """
        Extract strings from routine bytecode.

        Looks for PRINT (0xB2) instructions followed by encoded text.
        """
        strings = []
        i = 0

        while i < len(routines_code):
            if routines_code[i] == 0xB2:  # PRINT opcode
                # Following bytes are encoded Z-string until we hit end-bit
                i += 1
                encoded_words = []

                while i + 1 < len(routines_code):
                    word = (routines_code[i] << 8) | routines_code[i + 1]
                    encoded_words.append(word)
                    i += 2

                    # Check for end-bit (bit 15)
                    if word & 0x8000:
                        break

                # Decode the string (simplified - just store raw for now)
                # In production, we'd decode Z-chars to text
                decoded = self._decode_zstring(encoded_words)
                if decoded:
                    strings.append(decoded)
            else:
                i += 1

        return strings

    def _decode_zstring(self, words: List[int]) -> Optional[str]:
        """
        Decode Z-character words to string.

        Simplified decoder - just extract printable characters.
        """
        # This is a simplified version - full decoder would handle:
        # - Alphabet shifting (A0/A1/A2)
        # - ZSCII escapes
        # - Abbreviations
        # For now, return a marker to track the string
        return f"<string:{len(words)}words>"

    def _extract_strings_from_objects(self, objects_data: bytes) -> List[str]:
        """
        Extract strings from object property tables.

        Property strings are embedded in property data.
        """
        # This would parse the object table structure
        # For now, return empty list as this is complex
        return []

    def _build_string_table(self) -> bytes:
        """Build deduplicated string table."""
        table = bytearray()
        offset = 0

        for string in self.string_usage:
            # For now, just track the string
            # In production, encode and store
            self.string_addresses[string] = offset
            # Placeholder: each string takes some bytes
            encoded = string.encode('utf-8')  # Placeholder
            table.extend(encoded)
            table.append(0)  # Null terminator
            offset = len(table)

        return bytes(table)


class PropertyOptimizationPass(OptimizationPass):
    """
    Optimize object property tables.

    - Remove unused properties
    - Compact property data
    - Deduplicate identical property values
    """

    def run(self, compilation_data: Dict) -> Dict:
        self.log("Property Optimization Pass")

        program = compilation_data.get('program')
        if not program:
            return compilation_data

        # Collect all property values from objects and rooms
        all_objects = list(program.objects) + list(program.rooms)

        # Track property values: (prop_name, value_repr) -> list of (obj_name, value)
        property_values: Dict[str, List[Tuple[str, Any]]] = {}
        # Track identical values: value_repr -> list of (obj_name, prop_name)
        value_usage: Dict[str, List[Tuple[str, str]]] = {}

        for obj in all_objects:
            for prop_name, prop_value in obj.properties.items():
                # Get a hashable representation of the value
                value_repr = self._value_repr(prop_value)

                if value_repr not in value_usage:
                    value_usage[value_repr] = []
                value_usage[value_repr].append((obj.name, prop_name))

        # Find duplicate values
        duplicates = {k: v for k, v in value_usage.items() if len(v) > 1}

        total_props = sum(len(obj.properties) for obj in all_objects)
        unique_values = len(value_usage)
        duplicate_count = sum(len(v) - 1 for v in duplicates.values())

        self.log(f"  Total properties: {total_props}")
        self.log(f"  Unique values: {unique_values}")
        self.log(f"  Duplicates: {duplicate_count}")

        if duplicates:
            self.log(f"  Top duplicated values:")
            sorted_dups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:5]
            for value_repr, usages in sorted_dups:
                # Truncate for display
                display = value_repr[:40] + '...' if len(value_repr) > 40 else value_repr
                self.log(f"    {display}: {len(usages)} uses")

        # Build deduplication map for property values
        # This would be used during object table building to share identical values
        dedup_map = {}
        for value_repr, usages in duplicates.items():
            if len(usages) >= 2:
                # Use the first occurrence as the canonical value
                canonical = usages[0]
                for usage in usages[1:]:
                    dedup_map[(usage[0], usage[1])] = canonical

        self.stats = {
            'total_properties': total_props,
            'unique_values': unique_values,
            'duplicates': duplicate_count,
            'dedup_candidates': len(dedup_map)
        }

        # Store dedup map for use during object table generation
        compilation_data['property_dedup_map'] = dedup_map

        return compilation_data

    def _value_repr(self, value: Any) -> str:
        """Get a hashable string representation of a property value."""
        if hasattr(value, 'value'):
            # AST node with value attribute
            return f"{type(value).__name__}:{value.value}"
        elif isinstance(value, (list, tuple)):
            # List of values
            return f"list:[{','.join(self._value_repr(v) for v in value)}]"
        elif isinstance(value, dict):
            # Dict (shouldn't happen often)
            return f"dict:{sorted(value.items())}"
        else:
            return str(value)


class AbbreviationOptimizationPass(OptimizationPass):
    """
    Optimize abbreviations table.

    - Remove overlapping abbreviations
    - Re-rank by actual savings
    - Adjust abbreviation table for better compression
    """

    def run(self, compilation_data: Dict) -> Dict:
        self.log("Abbreviation Optimization Pass")

        abbreviations_table = compilation_data.get('abbreviations_table')
        if not abbreviations_table or len(abbreviations_table) == 0:
            return compilation_data

        # Get original abbreviations
        original_abbrevs = abbreviations_table.abbreviations.copy()

        # Count original overlaps
        original_overlaps = self._count_overlaps(original_abbrevs)

        if original_overlaps > 0:
            self.log(f"  Found {original_overlaps} overlapping abbreviations")
            self.log(f"  Eliminating overlaps...")

            # Eliminate overlaps
            optimized_abbrevs = self._eliminate_overlaps(original_abbrevs)

            # Update abbreviations table
            abbreviations_table.abbreviations = optimized_abbrevs
            abbreviations_table.lookup = {s: i for i, s in enumerate(optimized_abbrevs)}

            new_overlaps = self._count_overlaps(optimized_abbrevs)
            eliminated = original_overlaps - new_overlaps

            self.log(f"  Eliminated {eliminated} overlaps")
            self.log(f"  Remaining overlaps: {new_overlaps}")
            self.log(f"  New abbreviation count: {len(optimized_abbrevs)}")
        else:
            optimized_abbrevs = original_abbrevs

        self.stats = {
            'original_count': len(original_abbrevs),
            'original_overlaps': original_overlaps,
            'optimized_count': len(optimized_abbrevs),
            'optimized_overlaps': self._count_overlaps(optimized_abbrevs),
            'overlaps_eliminated': original_overlaps - self._count_overlaps(optimized_abbrevs)
        }

        return compilation_data

    def _count_overlaps(self, abbrevs: List[str]) -> int:
        """Count overlapping abbreviation pairs."""
        overlaps = 0
        for i, abbr1 in enumerate(abbrevs):
            for abbr2 in abbrevs[i+1:]:
                if self._has_overlap(abbr1, abbr2):
                    overlaps += 1
        return overlaps

    def _has_overlap(self, abbr1: str, abbr2: str) -> bool:
        """Check if two abbreviations overlap."""
        return abbr1 in abbr2 or abbr2 in abbr1

    def _eliminate_overlaps(self, abbrevs: List[str]) -> List[str]:
        """
        Eliminate overlapping abbreviations using greedy selection.

        Strategy:
        1. Sort by savings (already done in original selection)
        2. Select abbreviations one by one
        3. Skip any that overlap with already-selected ones
        4. Continue until we have 96 or run out of candidates

        Note: If we can't reach 96 from the provided list, we try to
        select the best non-overlapping subset.
        """
        selected = []

        for abbr in abbrevs:
            # Check if this abbreviation overlaps with any already selected
            has_overlap = any(self._has_overlap(abbr, s) for s in selected)

            if not has_overlap:
                selected.append(abbr)

            # Stop when we have 96 abbreviations
            if len(selected) >= 96:
                break

        if len(selected) < 96:
            self.log(f"  Warning: Only {len(selected)} non-overlapping abbreviations available")
            self.log(f"  Need to expand candidate pool for better coverage")

        return selected


class OptimizationPipeline:
    """
    Run multiple optimization passes in sequence.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passes: List[OptimizationPass] = []

    def add_pass(self, pass_class: type, **kwargs):
        """Add an optimization pass to the pipeline."""
        pass_instance = pass_class(verbose=self.verbose, **kwargs)
        self.passes.append(pass_instance)

    def run(self, compilation_data: Dict) -> Dict:
        """Run all optimization passes in sequence."""
        if self.verbose:
            print(f"[opt] Running {len(self.passes)} optimization passes")

        for pass_instance in self.passes:
            compilation_data = pass_instance.run(compilation_data)

        # Collect statistics from all passes
        all_stats = {}
        for i, pass_instance in enumerate(self.passes):
            pass_name = pass_instance.__class__.__name__
            all_stats[pass_name] = pass_instance.stats

        compilation_data['optimization_stats'] = all_stats

        return compilation_data
