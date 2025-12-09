#!/usr/bin/env python3
"""
Comprehensive Z-machine story file analyzer.
Supports V1-V8, analyzes header, objects, dictionary, routines.
"""

import sys
import struct
from pathlib import Path


def read_word(data, offset):
    """Read big-endian word."""
    return struct.unpack('>H', data[offset:offset+2])[0]


def read_byte(data, offset):
    """Read byte."""
    return data[offset]


def analyze_header(data):
    """Analyze Z-machine header (all versions)."""
    version = data[0]

    header = {
        'version': version,
        'flags1': data[1],
        'release': read_word(data, 0x02),
        'high_mem': read_word(data, 0x04),
        'initial_pc': read_word(data, 0x06),
        'dictionary': read_word(data, 0x08),
        'objects': read_word(data, 0x0A),
        'globals': read_word(data, 0x0C),
        'static_mem': read_word(data, 0x0E),
        'flags2': read_word(data, 0x10),
        'serial': data[0x12:0x18].decode('ascii', errors='replace'),
        'abbreviations': read_word(data, 0x18),
        'file_length_raw': read_word(data, 0x1A),
        'checksum': read_word(data, 0x1C),
    }

    # File length divisor depends on version
    if version <= 3:
        divisor = 2
    elif version <= 5:
        divisor = 4
    else:
        divisor = 8
    header['file_length'] = header['file_length_raw'] * divisor

    # V4+ fields
    if version >= 4:
        header['interpreter_number'] = data[0x1E]
        header['interpreter_version'] = data[0x1F]
        header['screen_height'] = data[0x20]
        header['screen_width'] = data[0x21]

    # V5+ fields
    if version >= 5:
        header['screen_width_units'] = read_word(data, 0x22)
        header['screen_height_units'] = read_word(data, 0x24)
        header['font_width'] = data[0x26] if version == 6 else data[0x27]
        header['font_height'] = data[0x27] if version == 6 else data[0x26]
        header['routines_offset'] = read_word(data, 0x28)
        header['strings_offset'] = read_word(data, 0x2A)
        header['default_bg'] = data[0x2C]
        header['default_fg'] = data[0x2D]
        header['terminating_chars'] = read_word(data, 0x2E)
        header['text_width'] = read_word(data, 0x30)
        header['standard_revision'] = read_word(data, 0x32)

    # V6 fields
    if version >= 6:
        header['alphabet_table'] = read_word(data, 0x34)
        header['header_extension'] = read_word(data, 0x36)

    return header


def print_header(header, data):
    """Print header analysis."""
    v = header['version']
    print(f"\n{'='*70}")
    print(f"Z-MACHINE HEADER ANALYSIS (Version {v})")
    print(f"{'='*70}")

    print(f"\nBasic Info:")
    print(f"  Version:        {v}")
    print(f"  Release:        {header['release']}")
    print(f"  Serial:         {header['serial']}")
    print(f"  File size:      {len(data):,} bytes (header says: {header['file_length']:,})")
    print(f"  Checksum:       0x{header['checksum']:04X}")

    print(f"\nMemory Map:")
    print(f"  Dynamic memory: 0x0000 - 0x{header['static_mem']-1:04X} ({header['static_mem']:,} bytes)")
    print(f"  Static memory:  0x{header['static_mem']:04X} - 0x{header['high_mem']-1:04X}")
    print(f"  High memory:    0x{header['high_mem']:04X} - end")

    print(f"\nTable Locations:")
    print(f"  Abbreviations:  0x{header['abbreviations']:04X}")
    print(f"  Objects:        0x{header['objects']:04X}")
    print(f"  Globals:        0x{header['globals']:04X}")
    print(f"  Dictionary:     0x{header['dictionary']:04X}")
    print(f"  Initial PC:     0x{header['initial_pc']:04X}")

    # V5+ specific
    if v >= 5:
        print(f"\nV5+ Extensions:")
        print(f"  Routines offset:  0x{header.get('routines_offset', 0):04X}")
        print(f"  Strings offset:   0x{header.get('strings_offset', 0):04X}")
        print(f"  Standard rev:     {header.get('standard_revision', 0)}")

    # V6 specific
    if v >= 6:
        print(f"\nV6 Graphics Extensions:")
        print(f"  Alphabet table:     0x{header.get('alphabet_table', 0):04X}")
        print(f"  Header extension:   0x{header.get('header_extension', 0):04X}")
        print(f"  Font width/height:  {header.get('font_width', 0)} x {header.get('font_height', 0)}")

    # Flags analysis
    print(f"\nFlags 1: 0x{header['flags1']:02X}")
    if v <= 3:
        if header['flags1'] & 0x02: print("    - Status line type: time")
        if header['flags1'] & 0x04: print("    - Story file split across disks")
        if header['flags1'] & 0x10: print("    - Status line not available")
        if header['flags1'] & 0x20: print("    - Screen-splitting available")
        if header['flags1'] & 0x40: print("    - Variable-pitch font default")
    else:
        if header['flags1'] & 0x01: print("    - Colors available")
        if header['flags1'] & 0x02: print("    - Picture display available")
        if header['flags1'] & 0x04: print("    - Bold available")
        if header['flags1'] & 0x08: print("    - Italic available")
        if header['flags1'] & 0x10: print("    - Fixed-space available")
        if header['flags1'] & 0x20: print("    - Sound effects available")
        if header['flags1'] & 0x80: print("    - Timed keyboard input available")


def analyze_objects(data, header):
    """Analyze object table."""
    v = header['version']
    obj_addr = header['objects']

    print(f"\n{'='*70}")
    print("OBJECT TABLE ANALYSIS")
    print(f"{'='*70}")

    # Property defaults (before object entries)
    if v <= 3:
        num_defaults = 31
        entry_size = 9  # 4 attrs + 3 relations + 2 props
    else:
        num_defaults = 63
        entry_size = 14  # 6 attrs + 6 relations + 2 props

    defaults_size = num_defaults * 2
    print(f"\nProperty defaults: {num_defaults} words ({defaults_size} bytes)")
    print(f"Object entry size: {entry_size} bytes")

    # First object starts after defaults
    first_obj = obj_addr + defaults_size
    print(f"First object at: 0x{first_obj:04X}")

    # Count objects (find first property table reference)
    obj_count = 0
    min_prop_addr = len(data)

    for i in range(255 if v <= 3 else 65535):
        obj_offset = first_obj + (i * entry_size)
        if obj_offset + entry_size > len(data):
            break

        if v <= 3:
            prop_addr = read_word(data, obj_offset + 7)
        else:
            prop_addr = read_word(data, obj_offset + 12)

        if prop_addr == 0 or prop_addr < obj_addr:
            break

        if prop_addr < min_prop_addr:
            min_prop_addr = prop_addr

        # Check if we've gone past where property tables start
        if obj_offset >= min_prop_addr:
            break

        obj_count += 1
        if obj_count >= 10 and obj_offset + entry_size >= min_prop_addr:
            break

    print(f"Estimated object count: {obj_count}")
    print(f"Property tables start around: 0x{min_prop_addr:04X}")

    # Show first few objects
    print(f"\nFirst 5 objects:")
    for i in range(min(5, obj_count)):
        obj_offset = first_obj + (i * entry_size)
        if v <= 3:
            attrs = struct.unpack('>I', data[obj_offset:obj_offset+4])[0]
            parent = data[obj_offset + 4]
            sibling = data[obj_offset + 5]
            child = data[obj_offset + 6]
            prop_addr = read_word(data, obj_offset + 7)
        else:
            attrs_hi = struct.unpack('>I', data[obj_offset:obj_offset+4])[0]
            attrs_lo = read_word(data, obj_offset + 4)
            attrs = (attrs_hi << 16) | attrs_lo
            parent = read_word(data, obj_offset + 6)
            sibling = read_word(data, obj_offset + 8)
            child = read_word(data, obj_offset + 10)
            prop_addr = read_word(data, obj_offset + 12)

        # Get object name
        name_len = data[prop_addr] if prop_addr < len(data) else 0
        name = decode_zstring(data, prop_addr + 1, header) if name_len > 0 else "(no name)"

        print(f"  Object {i+1}: parent={parent}, sibling={sibling}, child={child}, props=0x{prop_addr:04X}")
        print(f"           attrs=0x{attrs:08X}, name=\"{name[:40]}\"")


def decode_zstring(data, addr, header):
    """Decode a Z-string (simplified)."""
    v = header['version']
    result = []
    alphabet = 'abcdefghijklmnopqrstuvwxyz'

    while addr < len(data):
        word = read_word(data, addr)
        addr += 2

        # Extract 3 Z-characters
        zchars = [
            (word >> 10) & 0x1F,
            (word >> 5) & 0x1F,
            word & 0x1F
        ]

        for zc in zchars:
            if zc == 0:
                result.append(' ')
            elif 6 <= zc <= 31:
                result.append(alphabet[zc - 6])

        # End marker
        if word & 0x8000:
            break

    return ''.join(result)


def analyze_dictionary(data, header):
    """Analyze dictionary."""
    v = header['version']
    dict_addr = header['dictionary']

    print(f"\n{'='*70}")
    print("DICTIONARY ANALYSIS")
    print(f"{'='*70}")

    # Word separator count
    sep_count = data[dict_addr]
    print(f"\nSeparator count: {sep_count}")

    # Word separators
    seps = data[dict_addr + 1:dict_addr + 1 + sep_count]
    print(f"Separators: {[chr(s) for s in seps]}")

    # Entry length and count
    entry_len_offset = dict_addr + 1 + sep_count
    entry_len = data[entry_len_offset]
    entry_count = read_word(data, entry_len_offset + 1)

    print(f"Entry length: {entry_len} bytes")
    print(f"Entry count: {entry_count}")

    # First few entries
    entries_start = entry_len_offset + 3
    print(f"Entries start at: 0x{entries_start:04X}")

    print(f"\nFirst 10 dictionary entries:")
    word_len = 4 if v <= 3 else 6
    for i in range(min(10, entry_count)):
        entry_addr = entries_start + (i * entry_len)
        word_data = data[entry_addr:entry_addr + word_len]
        word = decode_zstring(data, entry_addr, header)
        flags = data[entry_addr + word_len:entry_addr + entry_len]
        print(f"  {i+1:3}. \"{word:12}\" flags: {flags.hex()}")


def analyze_routines(data, header):
    """Analyze routine area (starting from initial PC)."""
    v = header['version']
    pc = header['initial_pc']

    print(f"\n{'='*70}")
    print("ROUTINE/CODE ANALYSIS")
    print(f"{'='*70}")

    if v >= 6:
        # V6 initial PC is a packed routine address
        actual_pc = pc * 4 + header.get('routines_offset', 0) * 8
        print(f"\nV6 packed address: 0x{pc:04X} -> actual: 0x{actual_pc:04X}")
        pc = actual_pc

    print(f"\nFirst routine at: 0x{pc:04X}")

    # Routine header
    if pc < len(data):
        local_count = data[pc]
        print(f"Local variable count: {local_count}")

        # In V1-4, local defaults follow
        if v <= 4:
            print(f"Local defaults:")
            for i in range(local_count):
                default = read_word(data, pc + 1 + i*2)
                print(f"  L{i+1:02} = {default}")
            code_start = pc + 1 + local_count * 2
        else:
            code_start = pc + 1

        print(f"Code starts at: 0x{code_start:04X}")

        # Show first 32 bytes of code
        print(f"\nFirst 32 bytes of code:")
        for i in range(0, 32, 16):
            hex_bytes = ' '.join(f'{data[code_start+i+j]:02X}' for j in range(16) if code_start+i+j < len(data))
            print(f"  0x{code_start+i:04X}: {hex_bytes}")


def analyze_v6_graphics(data, header):
    """Analyze V6-specific graphics features."""
    if header['version'] < 6:
        return

    print(f"\n{'='*70}")
    print("V6 GRAPHICS ANALYSIS")
    print(f"{'='*70}")

    # Check header extension table
    ext_addr = header.get('header_extension', 0)
    if ext_addr > 0 and ext_addr < len(data):
        ext_len = read_word(data, ext_addr)
        print(f"\nHeader extension table at 0x{ext_addr:04X}")
        print(f"  Extension word count: {ext_len}")

        if ext_len >= 3:
            # Word 3: Unicode translation table
            unicode_table = read_word(data, ext_addr + 6)
            print(f"  Unicode table: 0x{unicode_table:04X}")

        if ext_len >= 4:
            # Word 4: Flags 3
            flags3 = read_word(data, ext_addr + 8)
            print(f"  Flags 3: 0x{flags3:04X}")

    # Look for Blorb resource markers or picture data
    print(f"\nScanning for graphics-related data...")

    # Check for FORM/IFRS markers (Blorb)
    for i in range(0, min(1000, len(data) - 4)):
        if data[i:i+4] == b'FORM':
            print(f"  Found FORM marker at 0x{i:04X}")
        if data[i:i+4] == b'IFRS':
            print(f"  Found IFRS marker at 0x{i:04X}")
        if data[i:i+4] == b'Pict':
            print(f"  Found Pict marker at 0x{i:04X}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_zmachine.py <story_file.z[3-8]>")
        print("\nAnalyzes Z-machine story files of any version.")
        sys.exit(1)

    filename = sys.argv[1]

    with open(filename, 'rb') as f:
        data = f.read()

    print(f"File: {filename}")
    print(f"Size: {len(data):,} bytes")

    header = analyze_header(data)
    print_header(header, data)
    analyze_objects(data, header)
    analyze_dictionary(data, header)
    analyze_routines(data, header)

    if header['version'] >= 6:
        analyze_v6_graphics(data, header)

    print(f"\n{'='*70}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
