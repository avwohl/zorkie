#!/bin/bash
# Verify that .z3 files are valid Z-machine format

echo "Verifying Z-machine files..."
echo

for zfile in $(find . -name "*.z3" | sort); do
    echo "Checking: $zfile"

    # Check file exists and is readable
    if [ ! -r "$zfile" ]; then
        echo "  ✗ Cannot read file"
        continue
    fi

    # Get file size
    size=$(stat -f%z "$zfile" 2>/dev/null || stat -c%s "$zfile")
    echo "  Size: $size bytes"

    # Read first byte (Z-machine version)
    version=$(xxd -l 1 -p "$zfile")
    case $version in
        03) echo "  ✓ Version 3" ;;
        04) echo "  ✓ Version 4" ;;
        05) echo "  ✓ Version 5" ;;
        06) echo "  ✓ Version 6" ;;
        07) echo "  ✓ Version 7" ;;
        08) echo "  ✓ Version 8" ;;
        *) echo "  ✗ Unknown version: 0x$version" ;;
    esac

    # Read bytes 6-7 (initial PC address)
    pc=$(xxd -s 6 -l 2 -p "$zfile")
    echo "  Initial PC: 0x$pc"

    # Read bytes 4-5 (high memory base)
    himem=$(xxd -s 4 -l 2 -p "$zfile")
    echo "  High mem: 0x$himem"

    echo
done

echo "To play any of these files, use: frotz <filename.z3>"
