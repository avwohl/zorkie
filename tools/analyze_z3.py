#!/usr/bin/env python3
"""
Analyze Z-machine story file structure.
Extracts and displays header information.
"""

import sys
import struct


def analyze_header(data):
    """Analyze Z-machine header."""
    print("Z-Machine Header Analysis")
    print("=" * 60)

    # Byte 0: Version
    version = data[0]
    print(f"Version: {version}")

    # Byte 1: Flags 1
    flags1 = data[1]
    print(f"Flags 1: 0x{flags1:02x}")

    # Bytes 2-3: Release number
    release = struct.unpack('>H', data[2:4])[0]
    print(f"Release: {release}")

    # Bytes 4-5: High memory base
    high_mem = struct.unpack('>H', data[4:6])[0]
    print(f"High memory base: 0x{high_mem:04x}")

    # Bytes 6-7: Initial PC
    initial_pc = struct.unpack('>H', data[6:8])[0]
    print(f"Initial PC: 0x{initial_pc:04x}")

    # Bytes 8-9: Dictionary location
    dict_loc = struct.unpack('>H', data[8:10])[0]
    print(f"Dictionary: 0x{dict_loc:04x}")

    # Bytes 0xA-0xB: Object table location
    obj_table = struct.unpack('>H', data[0xA:0xC])[0]
    print(f"Object table: 0x{obj_table:04x}")

    # Bytes 0xC-0xD: Global variables table
    globals_table = struct.unpack('>H', data[0xC:0xE])[0]
    print(f"Globals table: 0x{globals_table:04x}")

    # Bytes 0xE-0xF: Static memory base
    static_mem = struct.unpack('>H', data[0xE:0x10])[0]
    print(f"Static memory base: 0x{static_mem:04x}")

    # Bytes 0x10-0x11: Flags 2
    flags2 = struct.unpack('>H', data[0x10:0x12])[0]
    print(f"Flags 2: 0x{flags2:04x}")

    # Bytes 0x12-0x17: Serial number
    serial = data[0x12:0x18].decode('ascii', errors='ignore')
    print(f"Serial: {serial}")

    # Bytes 0x18-0x19: Abbreviations table
    abbrev = struct.unpack('>H', data[0x18:0x1A])[0]
    print(f"Abbreviations: 0x{abbrev:04x}" if abbrev else "Abbreviations: None")

    # Bytes 0x1A-0x1B: File length
    file_len_div = struct.unpack('>H', data[0x1A:0x1C])[0]
    divisor = 2 if version <= 3 else (8 if version == 8 else 4)
    file_len = file_len_div * divisor
    print(f"File length: {file_len} bytes (0x{file_len:04x})")

    # Bytes 0x1C-0x1D: Checksum
    checksum = struct.unpack('>H', data[0x1C:0x1E])[0]
    print(f"Checksum: 0x{checksum:04x}")

    print("\nMemory Layout:")
    print(f"  Dynamic memory: 0x0000 - 0x{static_mem:04x} ({static_mem} bytes)")
    print(f"  Static memory:  0x{static_mem:04x} - 0x{high_mem:04x}")
    print(f"  High memory:    0x{high_mem:04x} - 0x{file_len:04x}")

    return {
        'version': version,
        'release': release,
        'high_mem': high_mem,
        'initial_pc': initial_pc,
        'dict': dict_loc,
        'objects': obj_table,
        'globals': globals_table,
        'static_mem': static_mem,
        'abbrev': abbrev,
        'file_len': file_len,
        'checksum': checksum,
        'serial': serial
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_z3.py <story_file.z3>")
        sys.exit(1)

    filename = sys.argv[1]

    with open(filename, 'rb') as f:
        data = f.read()

    print(f"File: {filename}")
    print(f"Size: {len(data)} bytes\n")

    header = analyze_header(data)

    print("\n" + "=" * 60)
    print(f"First instruction should be at: 0x{header['initial_pc']:04x}")
    print(f"Byte at initial PC: 0x{data[header['initial_pc']]:02x}")


if __name__ == '__main__':
    main()
