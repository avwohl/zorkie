#!/bin/bash
# Z-code Comparison Test Script
# Compares output from your ZIL compiler against reference .z files

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Usage: $0 [options]

Compare ZIL compiler output against reference z-machine files.

Options:
    -c COMPILER     Path to your ZIL compiler (required)
    -t TEST         Specific test to run (zork1, enchanter, hello, etc.)
    -a              Run all tests
    -v              Verbose output (show hex dumps)
    -h              Show this help

Examples:
    $0 -c ../build/zilc -t zork1
    $0 -c ../build/zilc -a
    $0 -c ../build/zilc -t zork1 -v
EOF
    exit 1
}

# Parse arguments
COMPILER=""
TEST=""
ALL_TESTS=false
VERBOSE=false

while getopts "c:t:avh" opt; do
    case $opt in
        c) COMPILER="$OPTARG" ;;
        t) TEST="$OPTARG" ;;
        a) ALL_TESTS=true ;;
        v) VERBOSE=true ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [ -z "$COMPILER" ]; then
    echo -e "${RED}Error: Compiler path required${NC}"
    usage
fi

if [ ! -x "$COMPILER" ]; then
    echo -e "${RED}Error: Compiler not found or not executable: $COMPILER${NC}"
    exit 1
fi

# Test definitions
declare -A TESTS
TESTS[zork1]="zork1/zork1.zil:zork1/COMPILED/zork1.z3"
TESTS[zork3]="zork3/zork3.zil:zork3/COMPILED/zork3.z3"
TESTS[enchanter]="enchanter/enchanter.zil:enchanter/COMPILED/enchanter.z3"
TESTS[planetfall]="../games/planetfall/source/planetfall.zil:../games/planetfall/source/COMPILED/planetfall.z3"
TESTS[hello]="zilf/sample/hello/hello.zil:zilf/test/Dezapf.Tests/Resources/hello.z3"

compare_files() {
    local name=$1
    local source=$2
    local reference=$3
    local output="output_${name}.z3"

    echo -e "\n${YELLOW}Testing: $name${NC}"
    echo "Source: $source"
    echo "Reference: $reference"

    # Check if files exist
    if [ ! -f "$source" ]; then
        echo -e "${RED}✗ Source file not found: $source${NC}"
        return 1
    fi

    if [ ! -f "$reference" ]; then
        echo -e "${RED}✗ Reference file not found: $reference${NC}"
        return 1
    fi

    # Compile with our compiler
    echo "Compiling with $COMPILER..."
    if ! "$COMPILER" "$source" -o "$output" 2>&1; then
        echo -e "${RED}✗ Compilation failed${NC}"
        return 1
    fi

    if [ ! -f "$output" ]; then
        echo -e "${RED}✗ Output file not created: $output${NC}"
        return 1
    fi

    # Get file sizes
    local ref_size=$(stat -f%z "$reference" 2>/dev/null || stat -c%s "$reference")
    local out_size=$(stat -f%z "$output" 2>/dev/null || stat -c%s "$output")

    echo "Reference size: $ref_size bytes"
    echo "Output size: $out_size bytes"

    # Binary comparison
    if cmp -s "$reference" "$output"; then
        echo -e "${GREEN}✓ Perfect match! Files are identical.${NC}"
        rm "$output"
        return 0
    else
        echo -e "${RED}✗ Files differ${NC}"

        # Show first difference
        echo -e "\nFirst difference at:"
        cmp -l "$reference" "$output" | head -1 | while read pos ref out; do
            printf "Byte %d (0x%x): reference=0x%02x output=0x%02x\n" "$pos" "$pos" "$((8#$ref))" "$((8#$out))"
        done

        # Count differences
        local diff_count=$(cmp -l "$reference" "$output" | wc -l)
        echo "Total differences: $diff_count bytes"

        if [ "$VERBOSE" = true ]; then
            echo -e "\n${YELLOW}Generating hex dumps...${NC}"
            xxd "$reference" > "${name}_reference.hex"
            xxd "$output" > "${name}_output.hex"
            echo "Reference hex: ${name}_reference.hex"
            echo "Output hex: ${name}_output.hex"
            echo "To compare: diff ${name}_reference.hex ${name}_output.hex | less"
        fi

        # Keep output for inspection
        echo "Output file saved: $output"
        return 1
    fi
}

# Run tests
FAILED_TESTS=()
PASSED_TESTS=()

if [ "$ALL_TESTS" = true ]; then
    for test_name in "${!TESTS[@]}"; do
        IFS=':' read -r source reference <<< "${TESTS[$test_name]}"
        if compare_files "$test_name" "$source" "$reference"; then
            PASSED_TESTS+=("$test_name")
        else
            FAILED_TESTS+=("$test_name")
        fi
    done
elif [ -n "$TEST" ]; then
    if [ -z "${TESTS[$TEST]}" ]; then
        echo -e "${RED}Error: Unknown test '$TEST'${NC}"
        echo "Available tests: ${!TESTS[@]}"
        exit 1
    fi
    IFS=':' read -r source reference <<< "${TESTS[$TEST]}"
    if compare_files "$TEST" "$source" "$reference"; then
        PASSED_TESTS+=("$TEST")
    else
        FAILED_TESTS+=("$TEST")
    fi
else
    echo -e "${RED}Error: Either -t TEST or -a required${NC}"
    usage
fi

# Summary
echo -e "\n${YELLOW}======== SUMMARY ========${NC}"
echo "Passed: ${#PASSED_TESTS[@]}"
echo "Failed: ${#FAILED_TESTS[@]}"

if [ ${#PASSED_TESTS[@]} -gt 0 ]; then
    echo -e "${GREEN}Passed tests:${NC}"
    for test in "${PASSED_TESTS[@]}"; do
        echo "  ✓ $test"
    done
fi

if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    echo -e "${RED}Failed tests:${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  ✗ $test"
    done
    exit 1
fi

exit 0
