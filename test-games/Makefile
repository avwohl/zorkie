# Makefile for ZIL Compiler Testing
# Makes it easy to run common testing tasks

# Configuration - set this to your compiler
COMPILER ?= ../build/zilc
TEST ?= hello

.PHONY: help verify inspect test test-all test-hello test-zork1 test-planetfall clean examples

help:
	@echo "ZIL Compiler Test Suite"
	@echo ""
	@echo "Usage:"
	@echo "  make verify         - Verify all reference .z3 files are valid"
	@echo "  make inspect        - Inspect hello.z3 reference file"
	@echo "  make examples       - List available test cases"
	@echo ""
	@echo "Testing (requires COMPILER=/path/to/compiler):"
	@echo "  make test           - Test hello world (or TEST=name)"
	@echo "  make test-all       - Test all games"
	@echo "  make test-hello     - Test hello.zil"
	@echo "  make test-zork1     - Test Zork I"
	@echo "  make test-planetfall- Test Planetfall"
	@echo ""
	@echo "Inspection:"
	@echo "  make inspect-hello  - Inspect hello world structure"
	@echo "  make inspect-zork1  - Inspect Zork I structure"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean          - Remove test outputs"
	@echo "  make help           - Show this help"
	@echo ""
	@echo "Configuration:"
	@echo "  COMPILER=${COMPILER}"
	@echo "  TEST=${TEST}"
	@echo ""
	@echo "Examples:"
	@echo "  make COMPILER=./mycompiler test"
	@echo "  make COMPILER=./mycompiler TEST=zork1 test"
	@echo "  make COMPILER=./mycompiler test-all"

verify:
	@echo "Verifying all reference .z3 files..."
	@./verify-zfiles.sh

inspect:
	@echo "Inspecting hello.z3 reference file..."
	@./inspect-zcode.sh examples/hello-reference.z3

examples:
	@echo "Available test cases:"
	@echo ""
	@echo "Minimal:"
	@ls -lh examples/hello* 2>/dev/null | awk '{print "  " $$9 " (" $$5 ")"}'
	@echo ""
	@echo "Full games:"
	@ls -lh examples/zork1* examples/planetfall* 2>/dev/null | awk '{print "  " $$9 " (" $$5 ")"}'
	@echo ""
	@echo "Also available: zork3, enchanter"

test:
	@if [ ! -f "$(COMPILER)" ]; then \
		echo "Error: Compiler not found: $(COMPILER)"; \
		echo "Set COMPILER=/path/to/your/compiler"; \
		exit 1; \
	fi
	@echo "Testing $(TEST) with $(COMPILER)..."
	@./compare-zcode.sh -c $(COMPILER) -t $(TEST)

test-all:
	@if [ ! -f "$(COMPILER)" ]; then \
		echo "Error: Compiler not found: $(COMPILER)"; \
		echo "Set COMPILER=/path/to/your/compiler"; \
		exit 1; \
	fi
	@echo "Testing all games with $(COMPILER)..."
	@./compare-zcode.sh -c $(COMPILER) -a

test-hello:
	@$(MAKE) TEST=hello test

test-zork1:
	@$(MAKE) TEST=zork1 test

test-planetfall:
	@$(MAKE) TEST=planetfall test

inspect-hello:
	@echo "Inspecting hello.z3..."
	@./inspect-zcode.sh examples/hello-reference.z3
	@echo ""
	@echo "Header hex:"
	@xxd -l 64 examples/hello-reference.z3

inspect-zork1:
	@echo "Inspecting zork1.z3..."
	@./inspect-zcode.sh examples/zork1-reference.z3
	@echo ""
	@echo "Header hex:"
	@xxd -l 64 examples/zork1-reference.z3

inspect-planetfall:
	@echo "Inspecting planetfall.z3..."
	@./inspect-zcode.sh examples/planetfall-reference.z3
	@echo ""
	@echo "Header hex:"
	@xxd -l 64 examples/planetfall-reference.z3

# Compare your output with reference
compare-hello:
	@if [ ! -f "output_hello.z3" ]; then \
		echo "Error: output_hello.z3 not found"; \
		echo "Run 'make test-hello' first"; \
		exit 1; \
	fi
	@echo "Comparing your output with reference..."
	@./inspect-zcode.sh output_hello.z3 examples/hello-reference.z3

# Play reference games
play-hello:
	@echo "Playing hello.z3 reference..."
	@frotz examples/hello-reference.z3

play-zork1:
	@echo "Playing zork1.z3 reference..."
	@frotz examples/zork1-reference.z3

play-planetfall:
	@echo "Playing planetfall.z3 reference..."
	@frotz examples/planetfall-reference.z3

# Clean up test outputs
clean:
	@echo "Cleaning test outputs..."
	@rm -f output_*.z3 my-*.z3 test-*.z3
	@rm -f *.hex
	@rm -f *.log test-results.txt
	@echo "Done."

# Quick start workflow
quickstart:
	@echo "=== ZIL Compiler Test Suite Quick Start ==="
	@echo ""
	@echo "Step 1: Verify test suite"
	@$(MAKE) verify
	@echo ""
	@echo "Step 2: Inspect reference file"
	@$(MAKE) inspect
	@echo ""
	@echo "Step 3: See available tests"
	@$(MAKE) examples
	@echo ""
	@echo "Next: Set COMPILER=/path/to/your/compiler and run 'make test'"

# Documentation
docs:
	@echo "Documentation files:"
	@ls -1 *.md *.txt | awk '{print "  " $$1}'
	@echo ""
	@echo "Start with: START-HERE.md or FINAL-SUMMARY.txt"

# Full workflow example
example-workflow:
	@echo "Example testing workflow:"
	@echo ""
	@echo "1. Verify reference files:"
	@echo "   make verify"
	@echo ""
	@echo "2. Inspect what a valid .z3 looks like:"
	@echo "   make inspect-hello"
	@echo ""
	@echo "3. Test your compiler:"
	@echo "   make COMPILER=./mycompiler test-hello"
	@echo ""
	@echo "4. If it fails, compare outputs:"
	@echo "   make compare-hello"
	@echo ""
	@echo "5. Try running it:"
	@echo "   frotz output_hello.z3"
	@echo ""
	@echo "6. When hello works, try larger games:"
	@echo "   make COMPILER=./mycompiler test-zork1"
	@echo ""
	@echo "7. Run full test suite:"
	@echo "   make COMPILER=./mycompiler test-all"
