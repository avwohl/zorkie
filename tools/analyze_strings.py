#!/usr/bin/env python3
"""
Analyze strings in ZIL source to find best abbreviation candidates.
This helps identify common substrings for the abbreviations table.
"""

import re
import sys
from collections import Counter
from pathlib import Path

def extract_strings_from_zil(filepath):
    """Extract all string literals from a ZIL file."""
    strings = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Match strings in quotes: "..."
    # Handle escaped quotes: \"
    string_pattern = r'"([^"\\]*(\\.[^"\\]*)*)"'

    for match in re.finditer(string_pattern, content):
        string = match.group(1)
        # Unescape
        string = string.replace('\\"', '"')
        string = string.replace('\\n', '\n')
        string = string.replace('\\t', '\t')
        strings.append(string)

    # Also extract strings from <TELL ...> and other inline text
    # TELL can have bare text: <TELL "Hello" " world">

    return strings

def find_substrings(strings, min_length=2, max_length=20):
    """Find all substrings of given lengths and count occurrences."""
    substring_counts = Counter()

    for string in strings:
        # Generate all substrings
        for length in range(min_length, min(max_length + 1, len(string) + 1)):
            for i in range(len(string) - length + 1):
                substr = string[i:i+length]
                # Only count if it contains meaningful characters
                if substr.strip() and not substr.isspace():
                    substring_counts[substr] += 1

    return substring_counts

def calculate_savings(substr, count, base_cost=2):
    """
    Calculate bytes saved by abbreviating a substring.

    base_cost: Cost of abbreviation reference (typically 2 Z-characters)
    Unabbreviated cost: depends on string encoding, roughly 0.6 bytes per char
    """
    # Rough estimate: each character costs about 0.6 bytes in Z-char encoding
    # (5 bits per Z-char, 3 Z-chars per 2 bytes)
    original_cost = len(substr) * 0.6
    # Abbreviation costs 2 Z-characters (1.33 bytes) per reference
    abbreviated_cost = 1.33

    savings_per_use = original_cost - abbreviated_cost
    total_savings = savings_per_use * count

    # Subtract the cost of storing the abbreviation itself once
    total_savings -= original_cost

    return total_savings

def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_strings.py <zil_file_or_directory>")
        sys.exit(1)

    path = Path(sys.argv[1])

    # Collect all strings
    all_strings = []

    if path.is_file():
        all_strings = extract_strings_from_zil(path)
    elif path.is_dir():
        for zil_file in path.glob("*.zil"):
            strings = extract_strings_from_zil(zil_file)
            all_strings.extend(strings)
            print(f"Processed {zil_file.name}: {len(strings)} strings")
    else:
        print(f"Error: {path} not found")
        sys.exit(1)

    print(f"\nTotal strings found: {len(all_strings)}")
    print(f"Total characters: {sum(len(s) for s in all_strings)}")

    # Find common substrings
    print("\nAnalyzing substrings...")
    substring_counts = find_substrings(all_strings, min_length=2, max_length=20)

    # Calculate savings for each substring
    candidates = []
    for substr, count in substring_counts.items():
        if count >= 3:  # Only consider substrings appearing 3+ times
            savings = calculate_savings(substr, count)
            if savings > 0:
                candidates.append((savings, count, len(substr), substr))

    # Sort by savings (descending)
    candidates.sort(reverse=True)

    # Show top candidates
    print("\nTop 100 abbreviation candidates (by estimated byte savings):\n")
    print(f"{'Rank':<6} {'Savings':<8} {'Count':<7} {'Length':<7} Substring")
    print("=" * 80)

    for i, (savings, count, length, substr) in enumerate(candidates[:100], 1):
        # Escape newlines and tabs for display
        display = repr(substr)[1:-1]  # Remove quotes
        if len(display) > 40:
            display = display[:37] + "..."
        print(f"{i:<6} {savings:>6.1f}  {count:>6}  {length:>6}  {display}")

    # Suggest top 96 for Z-machine (32 for each of 3 abbreviation tables)
    print(f"\n\nTop 96 suggestions for abbreviations table:")
    print("=" * 80)

    for i, (savings, count, length, substr) in enumerate(candidates[:96], 1):
        table = (i - 1) // 32
        index = (i - 1) % 32
        display = repr(substr)[1:-1]
        if len(display) > 30:
            display = display[:27] + "..."
        print(f"Table {table}, Index {index:2d}: (used {count:3d}x, saves {savings:5.1f}b) {display}")

if __name__ == '__main__':
    main()
