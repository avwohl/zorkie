#!/bin/bash
# Z-machine Bytecode Inspector
# Analyzes Z-machine header and structure

if [ $# -lt 1 ]; then
    echo "Usage: $0 <file.z3> [file2.z3]"
    echo
    echo "Inspect Z-machine file header and structure."
    echo "If two files provided, shows comparison."
    exit 1
fi

FILE1="$1"
FILE2="$2"

inspect_file() {
    local file="$1"
    local size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file")

    echo "==================================="
    echo "File: $file"
    echo "Size: $size bytes"
    echo "==================================="

    # Header analysis (first 64 bytes)
    echo
    echo "--- HEADER (first 64 bytes) ---"

    # Byte 0: Version
    local ver=$(xxd -s 0 -l 1 -p "$file")
    echo "Version:           $ver ($(printf '%d' 0x$ver))"

    # Byte 1: Flags 1
    local flags1=$(xxd -s 1 -l 1 -p "$file")
    echo "Flags 1:           0x$flags1"

    # Bytes 2-3: Release number
    local release=$(xxd -s 2 -l 2 -p "$file")
    echo "Release:           0x$release ($(printf '%d' 0x$release))"

    # Bytes 4-5: High memory base
    local himem=$(xxd -s 4 -l 2 -p "$file")
    echo "High memory:       0x$himem ($(printf '%d' 0x$himem))"

    # Bytes 6-7: Initial PC
    local pc=$(xxd -s 6 -l 2 -p "$file")
    echo "Initial PC:        0x$pc ($(printf '%d' 0x$pc))"

    # Bytes 8-9: Dictionary address
    local dict=$(xxd -s 8 -l 2 -p "$file")
    echo "Dictionary:        0x$dict ($(printf '%d' 0x$dict))"

    # Bytes 10-11: Object table
    local objtab=$(xxd -s 10 -l 2 -p "$file")
    echo "Object table:      0x$objtab ($(printf '%d' 0x$objtab))"

    # Bytes 12-13: Global variables
    local globals=$(xxd -s 12 -l 2 -p "$file")
    echo "Global vars:       0x$globals ($(printf '%d' 0x$globals))"

    # Bytes 14-15: Static memory base
    local static=$(xxd -s 14 -l 2 -p "$file")
    echo "Static memory:     0x$static ($(printf '%d' 0x$static))"

    # Bytes 16-17: Flags 2
    local flags2=$(xxd -s 16 -l 2 -p "$file")
    echo "Flags 2:           0x$flags2"

    # Bytes 18-23: Serial number (6 ASCII chars)
    local serial=$(xxd -s 18 -l 6 -p "$file" | xxd -r -p)
    echo "Serial:            '$serial'"

    # Bytes 24-25: Abbreviations table
    local abbrev=$(xxd -s 24 -l 2 -p "$file")
    echo "Abbreviations:     0x$abbrev ($(printf '%d' 0x$abbrev))"

    # Bytes 26-27: File length
    local length=$(xxd -s 26 -l 2 -p "$file")
    local actual_length=$((0x$length * 2))
    echo "File length (hdr): 0x$length (*2 = $actual_length bytes)"

    # Bytes 28-29: Checksum
    local checksum=$(xxd -s 28 -l 2 -p "$file")
    echo "Checksum:          0x$checksum"

    echo
    echo "--- MEMORY LAYOUT ---"
    printf "Dynamic:   0x0000 - 0x%04x (%d bytes)\n" $((0x$static - 1)) $((0x$static))
    printf "Static:    0x%04x - 0x%04x (%d bytes)\n" $((0x$static)) $((0x$himem - 1)) $((0x$himem - 0x$static))
    printf "High:      0x%04x - 0x%04x (%d bytes)\n" $((0x$himem)) $((size - 1)) $((size - 0x$himem))

    echo
    echo "--- KEY ADDRESSES ---"
    printf "Object table starts at: 0x%04x (byte %d)\n" $((0x$objtab)) $((0x$objtab))
    printf "Dictionary starts at:   0x%04x (byte %d)\n" $((0x$dict)) $((0x$dict))
    printf "Globals start at:       0x%04x (byte %d)\n" $((0x$globals)) $((0x$globals))
    printf "Abbrev table at:        0x%04x (byte %d)\n" $((0x$abbrev)) $((0x$abbrev))
    printf "Code starts at:         0x%04x (byte %d)\n" $((0x$pc)) $((0x$pc))

    echo
    echo "--- FIRST 128 BYTES (HEX) ---"
    xxd -l 128 "$file"
}

# Inspect first file
inspect_file "$FILE1"

# If second file provided, compare
if [ -n "$FILE2" ]; then
    echo
    echo
    inspect_file "$FILE2"

    echo
    echo
    echo "========================================="
    echo "COMPARISON"
    echo "========================================="

    # Compare headers
    echo
    echo "--- HEADER DIFFERENCES ---"
    diff <(xxd -l 64 "$FILE1") <(xxd -l 64 "$FILE2") || echo "(Files have identical headers)"

    # Compare sizes
    size1=$(stat -f%z "$FILE1" 2>/dev/null || stat -c%s "$FILE1")
    size2=$(stat -f%z "$FILE2" 2>/dev/null || stat -c%s "$FILE2")
    echo
    echo "--- SIZE COMPARISON ---"
    echo "File 1: $size1 bytes"
    echo "File 2: $size2 bytes"
    echo "Difference: $((size2 - size1)) bytes"

    # Full binary comparison
    echo
    echo "--- BINARY DIFFERENCES ---"
    if cmp -s "$FILE1" "$FILE2"; then
        echo "Files are IDENTICAL!"
    else
        echo "First 10 differences:"
        cmp -l "$FILE1" "$FILE2" | head -10 | while read pos val1 val2; do
            printf "Byte %d (0x%04x): %s (%d) vs %s (%d)\n" \
                "$pos" "$pos" "$val1" "$((8#$val1))" "$val2" "$((8#$val2))"
        done

        total=$(cmp -l "$FILE1" "$FILE2" | wc -l)
        echo
        echo "Total differences: $total bytes"
        if command -v bc &> /dev/null; then
            echo "Percentage different: $(echo "scale=2; $total * 100 / $size1" | bc)%"
        fi
    fi
fi

echo
echo "Done."
