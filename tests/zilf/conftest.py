# ZILF Test Suite for Zorkie - Test Configuration
# ================================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Primary author: Tara McGrew
# Adapted for zorkie by automated translation
#
# Original files:
#   - test/Zilf.Tests.Integration/AssertionHelper.cs
#   - test/Zilf.Tests.Integration/ZlrHelper.cs
#   - test/Zilf.Tests.Integration/IntegrationTestClass.cs

"""
Test fixtures and helpers for ZILF integration tests.

This module provides a pytest-based testing framework that mirrors the
patterns used in the original ZILF C# test suite. The key abstractions are:

- ZILCompiler: Compiles ZIL source code to Z-machine story files
- ZMachine: Executes Z-machine story files and captures output
- Assertion helpers: Fluent API for testing compilation and execution results
"""

import pytest
import re
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List, Callable, Any
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class ZVersion(IntEnum):
    """Z-machine version numbers."""
    V1 = 1
    V2 = 2
    V3 = 3  # ZIP - classic Infocom
    V4 = 4  # EZIP - expanded
    V5 = 5  # XZIP - extended
    V6 = 6  # YZIP - graphics
    V7 = 7
    V8 = 8
    GLULX = 256  # Glulx VM (32-bit, Unicode)


@dataclass
class CompilationResult:
    """Result of compiling ZIL source code."""
    success: bool
    story_file: Optional[bytes] = None
    zap_output: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_codes: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of executing a Z-machine story file."""
    output: str = ""
    return_value: Optional[int] = None
    success: bool = True
    error: Optional[str] = None


class ZILCompiler:
    """
    Compiles ZIL source code to Z-machine format.

    This is a wrapper around zorkie's compiler that provides the same
    interface as ZILF's ZlrHelper for testing purposes.
    """

    def __init__(self, version: ZVersion = ZVersion.V3):
        self.version = version
        self.globals: List[str] = []
        self.debug_info = False
        self.version_directive: Optional[str] = None

    def add_global(self, code: str) -> 'ZILCompiler':
        """Add a global definition."""
        self.globals.append(code)
        return self

    def with_debug_info(self) -> 'ZILCompiler':
        """Enable debug info generation."""
        self.debug_info = True
        return self

    def with_version_directive(self, directive: str) -> 'ZILCompiler':
        """Set a version directive."""
        self.version_directive = directive
        return self

    def compile_routine(self, args: str, body: str, call_args: Optional[List[str]] = None,
                         print_return: bool = True) -> CompilationResult:
        """
        Compile a test routine.

        Args:
            args: Routine arguments (e.g., '"AUX" X Y')
            body: Routine body
            call_args: Optional arguments to pass when calling the routine
            print_return: If True, GO prints the return value; if False, just calls the routine

        Returns:
            CompilationResult with compilation status and artifacts
        """
        # Build the full source
        source_parts = []

        # Add version directive if specified
        if self.version_directive:
            source_parts.append(self.version_directive)
        else:
            # Default version directive based on self.version
            version_names = {
                ZVersion.V3: "ZIP",
                ZVersion.V4: "EZIP",
                ZVersion.V5: "XZIP",
                ZVersion.V6: "YZIP",
                ZVersion.GLULX: "GLULX",
            }
            if self.version in version_names:
                source_parts.append(f"<VERSION {version_names[self.version]}>")

        # Add globals
        source_parts.extend(self.globals)

        # Add test routine
        if args:
            source_parts.append(f'<ROUTINE TEST?ROUTINE ({args}) {body}>')
        else:
            source_parts.append(f'<ROUTINE TEST?ROUTINE () {body}>')

        # Add GO routine that calls test routine with optional arguments
        if call_args:
            call_str = ' '.join(call_args)
            if print_return:
                source_parts.append(f'<ROUTINE GO () <PRINTN <TEST?ROUTINE {call_str}>> <QUIT>>')
            else:
                source_parts.append(f'<ROUTINE GO () <TEST?ROUTINE {call_str}> <QUIT>>')
        else:
            if print_return:
                source_parts.append('<ROUTINE GO () <PRINTN <TEST?ROUTINE>> <QUIT>>')
            else:
                source_parts.append('<ROUTINE GO () <TEST?ROUTINE> <QUIT>>')

        source = "\n".join(source_parts)
        return self._compile(source)

    def compile_globals(self, *globals_code: str) -> CompilationResult:
        """
        Compile global definitions.

        Args:
            globals_code: Global definition code strings

        Returns:
            CompilationResult
        """
        source_parts = []

        # Add version directive based on self.version
        version_names = {
            ZVersion.V3: "ZIP",
            ZVersion.V4: "EZIP",
            ZVersion.V5: "XZIP",
            ZVersion.V6: "YZIP",
            ZVersion.GLULX: "GLULX",
        }
        if self.version in version_names:
            source_parts.append(f"<VERSION {version_names[self.version]}>")

        source_parts.extend(globals_code)
        source_parts.extend(self.globals)

        # Add minimal GO routine
        source_parts.append('<ROUTINE GO () <QUIT>>')

        source = "\n".join(source_parts)
        return self._compile(source)

    def compile_entry_point(self, args: str, body: str) -> CompilationResult:
        """
        Compile a GO routine directly (for testing entry point constraints).

        Args:
            args: GO routine arguments
            body: GO routine body

        Returns:
            CompilationResult
        """
        source_parts = []

        # Add version directive based on self.version
        version_names = {
            ZVersion.V3: "ZIP",
            ZVersion.V4: "EZIP",
            ZVersion.V5: "XZIP",
            ZVersion.V6: "YZIP",
            ZVersion.GLULX: "GLULX",
        }
        if self.version in version_names:
            source_parts.append(f"<VERSION {version_names[self.version]}>")

        source_parts.extend(self.globals)

        if args:
            source_parts.append(f'<ROUTINE GO ({args}) {body}>')
        else:
            source_parts.append(f'<ROUTINE GO () {body}>')

        source = "\n".join(source_parts)
        return self._compile(source)

    def _compile(self, source: str) -> CompilationResult:
        """
        Internal compilation method.

        Uses zorkie's actual compiler.
        """
        try:
            from zilc.compiler import ZILCompiler as ActualCompiler

            # Create compiler with appropriate version
            compiler = ActualCompiler(version=int(self.version), verbose=False)

            # Compile the source
            story_data = compiler.compile_string(source, "<test>")

            # Get warnings from compiler
            warnings = compiler.get_warnings() if hasattr(compiler, 'get_warnings') else []

            return CompilationResult(
                success=True,
                story_file=story_data,
                zap_output=None,  # zorkie doesn't produce ZAP assembly output yet
                errors=[],
                warnings=warnings,
                error_codes=[],
            )
        except ImportError as e:
            # Compiler module not available
            return CompilationResult(
                success=False,
                errors=[f"Compiler import failed: {e}"],
            )
        except SyntaxError as e:
            # Parse/syntax errors
            error_msg = str(e)
            # Extract error codes like ZIL0404, MDL0417, etc.
            error_codes = re.findall(r'([A-Z]{2,}[0-9]{3,})', error_msg)
            return CompilationResult(
                success=False,
                errors=[error_msg],
                error_codes=error_codes,
            )
        except Exception as e:
            # Other compilation errors
            error_msg = str(e)
            # Extract error codes like ZIL0404, MDL0417, etc.
            error_codes = re.findall(r'([A-Z]{2,}[0-9]{3,})', error_msg)
            return CompilationResult(
                success=False,
                errors=[error_msg],
                error_codes=error_codes,
            )


class ZMachine:
    """
    Z-machine interpreter for test execution.

    This executes compiled Z-machine story files and captures output.
    """

    def __init__(self, story_file: bytes, version: ZVersion = ZVersion.V3):
        self.story_file = story_file
        self.version = version
        self.input_queue: List[str] = []

    def provide_input(self, *inputs: str) -> 'ZMachine':
        """Queue input for the game."""
        self.input_queue.extend(inputs)
        return self

    def _get_interpreter(self) -> tuple:
        """
        Get the interpreter path and flags based on Z-machine version.

        Returns:
            Tuple of (interpreter_path, flags_list, interpreter_name)
        """
        import os

        # Check for environment variable override
        override = os.environ.get("ZORKIE_INTERPRETER")
        if override:
            # User override - assume dfrotz-compatible flags
            return (override, ["-q", "-m", "-p"], "custom")

        # Glulx: Use glulxe
        if self.version == ZVersion.GLULX:
            glulxe_paths = [
                "/usr/games/glulxe",
                "/usr/local/bin/glulxe",
            ]
            for path in glulxe_paths:
                if os.path.exists(path):
                    return (path, [], "glulxe")
            return (None, [], None)

        # Try bocfel first for V5+ (better spec compliance, supports V8)
        # Note: bocfel has a bug with V7 (treats it as V5 incorrectly)
        bocfel_path = "/tmp/bocfel-2.4/bocfel"
        if os.path.exists(bocfel_path) and self.version >= 5 and self.version != 7:
            return (bocfel_path, [], "bocfel")

        # V1-V6: Use dfrotz
        dfrotz_paths = [
            os.path.expanduser("~/esrc/frotz-src/dfrotz"),
            "/usr/games/dfrotz",
            "/usr/local/bin/dfrotz",
        ]
        for path in dfrotz_paths:
            if os.path.exists(path):
                # -h 1000 sets screen height to 1000 to avoid pagination blank lines
                return (path, ["-q", "-m", "-p", "-h", "1000"], "dfrotz")

        return (None, [], None)

    def execute(self, routine: str = "GO", args: List[int] = None) -> ExecutionResult:
        """
        Execute the story file using an appropriate Z-machine interpreter.

        Args:
            routine: Routine to call (default: GO)
            args: Arguments to pass to the routine

        Returns:
            ExecutionResult with output and return value
        """
        import subprocess
        import tempfile
        import os

        # Get interpreter based on version
        interpreter_path, flags, interpreter_name = self._get_interpreter()
        if not interpreter_path:
            return ExecutionResult(
                success=False,
                error=f"No Z-machine interpreter found for version {self.version}",
            )

        try:
            # Write story file to temp file
            suffix = ".ulx" if self.version == ZVersion.GLULX else f".z{self.version}"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(self.story_file)
                story_path = f.name

            try:
                # Prepare input
                input_text = "\n".join(self.input_queue) + "\n" if self.input_queue else ""

                # Run interpreter with appropriate flags
                result = subprocess.run(
                    [interpreter_path] + flags + [story_path],
                    input=input_text,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # Filter out [STEP ...] debug lines from output
                output_lines = [
                    line for line in result.stdout.split("\n")
                    if not line.startswith("[STEP")
                ]
                output = "\n".join(output_lines)

                # Strip ANSI escape codes (bocfel outputs these)
                import re
                output = re.sub(r'\x1b\[[0-9;]*m', '', output)

                # Filter out bocfel warning messages (e.g., V6 support warning)
                output_lines = [
                    line for line in output.split("\n")
                    if not line.startswith("[Version") and not line.startswith("[Fatal")
                ]
                output = "\n".join(output_lines)

                # dfrotz inserts blank lines for pagination even with -m flag
                # Filter out isolated blank lines that appear far into the output
                # (pagination artifacts typically appear every ~200+ lines)
                # Keep early blank lines as they're likely intentional output
                if interpreter_name == "dfrotz":
                    lines = output.split("\n")
                    filtered = []
                    for i, line in enumerate(lines):
                        if line.strip() == '':
                            # Keep blank line if it's near the start (first 100 lines)
                            if i < 100:
                                filtered.append(line)
                            # Keep blank line if adjacent to another blank line
                            elif (i > 0 and lines[i-1].strip() == '') or \
                                 (i < len(lines)-1 and lines[i+1].strip() == ''):
                                filtered.append(line)
                            # Otherwise, skip this isolated blank line (likely pagination)
                        else:
                            filtered.append(line)
                    output = "\n".join(filtered)

                # Strip leading/trailing whitespace (bocfel adds extra newlines)
                output = output.strip()
                # Re-add trailing newline if there was content
                if output:
                    output = output + "\n"

                # Also check stderr for errors
                if result.returncode != 0 and result.stderr:
                    return ExecutionResult(
                        success=False,
                        error=result.stderr,
                    )

                return ExecutionResult(
                    output=output,
                    return_value=None,  # dfrotz doesn't easily expose return values
                    success=True,
                )
            finally:
                # Clean up temp file
                os.unlink(story_path)

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error="Execution timed out",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
            )


class ExprAssertion:
    """
    Fluent assertion helper for testing ZIL expressions.

    Mirrors the ZILF ExprAssertionHelper pattern.

    Usage:
        await AssertExpr("<+ 1 2>").gives_number("3")
        await AssertExpr("<SOUND 0>").in_v3().compiles()
        await AssertExpr("<SAVE>").in_v3().does_not_compile()
    """

    def __init__(self, expr: str):
        self.expr = expr
        self.version = ZVersion.V3
        self.globals: List[str] = []
        self.expected_warnings: Optional[List[str]] = None
        self.expect_no_warnings: bool = False
        self.debug_info = False
        self.version_directive: Optional[str] = None
        self.call_args: Optional[List[str]] = None

    def in_v3(self) -> 'ExprAssertion':
        self.version = ZVersion.V3
        return self

    def in_v4(self) -> 'ExprAssertion':
        self.version = ZVersion.V4
        return self

    def in_v5(self) -> 'ExprAssertion':
        self.version = ZVersion.V5
        return self

    def in_v6(self) -> 'ExprAssertion':
        self.version = ZVersion.V6
        return self

    def with_global(self, code: str) -> 'ExprAssertion':
        self.globals.append(code)
        return self

    def with_warnings(self, *codes: str) -> 'ExprAssertion':
        self.expected_warnings = list(codes) if codes else None
        return self

    def without_warnings(self, *codes: str) -> 'ExprAssertion':
        if codes:
            self.expected_warnings = []  # Will check these are NOT present
        else:
            self.expect_no_warnings = True
        return self

    def with_debug_info(self) -> 'ExprAssertion':
        self.debug_info = True
        return self

    def with_version_directive(self, directive: str) -> 'ExprAssertion':
        self.version_directive = directive
        return self

    def _get_compiler(self) -> ZILCompiler:
        compiler = ZILCompiler(self.version)
        for g in self.globals:
            compiler.add_global(g)
        if self.debug_info:
            compiler.with_debug_info()
        if self.version_directive:
            compiler.with_version_directive(self.version_directive)
        return compiler

    def compiles(self) -> None:
        """Assert that the expression compiles successfully."""
        compiler = self._get_compiler()
        result = compiler.compile_routine("", self.expr)
        assert result.success, f"Expected compilation to succeed, but got errors: {result.errors}"
        self._check_warnings(result)

    def does_not_compile(self, *error_codes: str) -> None:
        """Assert that the expression fails to compile."""
        compiler = self._get_compiler()
        result = compiler.compile_routine("", self.expr)
        assert not result.success, f"Expected compilation to fail, but it succeeded"
        if error_codes:
            for code in error_codes:
                assert code in result.error_codes, f"Expected error code {code}, got {result.error_codes}"

    def gives_number(self, expected: str) -> None:
        """Assert that the expression evaluates to a specific number."""
        compiler = self._get_compiler()
        result = compiler.compile_routine("", self.expr)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            # The GO routine prints the return value, so extract it from output
            actual = exec_result.output.strip()
            assert actual == expected, \
                f"Expected {expected}, got {actual}"

    def outputs(self, expected: str) -> None:
        """Assert that the expression produces specific output."""
        compiler = self._get_compiler()
        # Use print_return=False so GO doesn't print the return value
        result = compiler.compile_routine("", self.expr, print_return=False)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            # Only strip trailing whitespace if expected doesn't end with whitespace
            # This preserves newlines for CRLF testing
            actual = exec_result.output
            if not expected.endswith(('\n', '\r', ' ', '\t')):
                actual = actual.rstrip()
            assert actual == expected, \
                f"Expected output '{expected}', got '{actual}'"

    def generates_code_matching(self, pattern: str) -> 'ExprAssertion':
        """Assert that the generated code matches a regex pattern."""
        compiler = self._get_compiler()
        result = compiler.compile_routine("", self.expr)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.zap_output:
            assert re.search(pattern, result.zap_output, re.MULTILINE), \
                f"Generated code does not match pattern '{pattern}'\nCode:\n{result.zap_output}"
        return self

    def generates_code_not_matching(self, pattern: str) -> 'ExprAssertion':
        """Assert that the generated code does NOT match a regex pattern."""
        compiler = self._get_compiler()
        result = compiler.compile_routine("", self.expr)
        assert result.success, f"Compilation failed: {result.errors}"

        if result.zap_output:
            assert not re.search(pattern, result.zap_output, re.MULTILINE), \
                f"Generated code should not match pattern '{pattern}'\nCode:\n{result.zap_output}"
        return self

    def _check_warnings(self, result: CompilationResult) -> None:
        """Check warning expectations."""
        if self.expect_no_warnings:
            assert not result.warnings, f"Expected no warnings, got: {result.warnings}"
        elif self.expected_warnings is not None:
            for code in self.expected_warnings:
                assert any(code in w for w in result.warnings), \
                    f"Expected warning {code}, got {result.warnings}"


class RoutineAssertion:
    """
    Fluent assertion helper for testing ZIL routines.

    Usage:
        await AssertRoutine('"AUX" X', '<SET X 123> .X').gives_number("123")
        await AssertRoutine('', '<PRINTI "hello">').outputs("hello")
    """

    def __init__(self, args: str, body: str):
        self.args = args
        self.body = body
        self.version = ZVersion.V3
        self.globals: List[str] = []
        self.expected_warnings: Optional[List[str]] = None
        self.expect_no_warnings: bool = False
        self.debug_info = False
        self.version_directive: Optional[str] = None
        self.call_args: Optional[List[str]] = None
        self.input_queue: List[str] = []

    def in_v3(self) -> 'RoutineAssertion':
        self.version = ZVersion.V3
        return self

    def in_v4(self) -> 'RoutineAssertion':
        self.version = ZVersion.V4
        return self

    def in_v5(self) -> 'RoutineAssertion':
        self.version = ZVersion.V5
        return self

    def in_v6(self) -> 'RoutineAssertion':
        self.version = ZVersion.V6
        return self

    def in_glulx(self) -> 'RoutineAssertion':
        """Set target to Glulx."""
        self.version = ZVersion.GLULX
        return self

    def with_global(self, code: str) -> 'RoutineAssertion':
        self.globals.append(code)
        return self

    def with_warnings(self, *codes: str) -> 'RoutineAssertion':
        self.expected_warnings = list(codes) if codes else None
        return self

    def without_warnings(self, *codes: str) -> 'RoutineAssertion':
        if codes:
            self.expected_warnings = []
        else:
            self.expect_no_warnings = True
        return self

    def without_unsuppressed_warnings(self) -> 'RoutineAssertion':
        """Assert that no unsuppressed warnings are emitted.

        This checks that any warnings that should have been suppressed
        via SUPPRESS-WARNINGS? are not present in the output.
        """
        self.expect_no_warnings = True
        return self

    def with_debug_info(self) -> 'RoutineAssertion':
        self.debug_info = True
        return self

    def with_version_directive(self, directive: str) -> 'RoutineAssertion':
        self.version_directive = directive
        return self

    def when_called_with(self, *args: str) -> 'RoutineAssertion':
        """Specify arguments to pass when calling the routine."""
        self.call_args = list(args)
        return self

    def with_input(self, *inputs: str) -> 'RoutineAssertion':
        """Queue input for the test execution."""
        self.input_queue.extend(inputs)
        return self

    def _get_compiler(self) -> ZILCompiler:
        compiler = ZILCompiler(self.version)
        for g in self.globals:
            compiler.add_global(g)
        if self.debug_info:
            compiler.with_debug_info()
        if self.version_directive:
            compiler.with_version_directive(self.version_directive)
        return compiler

    def compiles(self) -> None:
        """Assert that the routine compiles successfully."""
        compiler = self._get_compiler()
        result = compiler.compile_routine(self.args, self.body)
        assert result.success, f"Expected compilation to succeed, but got errors: {result.errors}"
        self._check_warnings(result)

    def does_not_compile(self, *error_codes: str) -> None:
        """Assert that the routine fails to compile."""
        compiler = self._get_compiler()
        result = compiler.compile_routine(self.args, self.body)
        assert not result.success, f"Expected compilation to fail, but it succeeded"
        if error_codes:
            for code in error_codes:
                assert code in result.error_codes, f"Expected error code {code}, got {result.error_codes}"

    def does_not_compile_with_error_count(self, expected_count: int) -> None:
        """Assert that the routine fails to compile with a specific number of errors."""
        compiler = self._get_compiler()
        result = compiler.compile_routine(self.args, self.body)
        assert not result.success, f"Expected compilation to fail, but it succeeded"
        actual_count = len(result.errors)
        assert actual_count == expected_count, \
            f"Expected {expected_count} errors, got {actual_count}"

    def does_not_throw(self) -> None:
        """Assert that compilation doesn't throw an exception (may still fail)."""
        compiler = self._get_compiler()
        try:
            compiler.compile_routine(self.args, self.body)
        except Exception as e:
            pytest.fail(f"Compilation threw an exception: {e}")

    def gives_number(self, expected: str) -> None:
        """Assert that the routine returns a specific number."""
        compiler = self._get_compiler()
        result = compiler.compile_routine(self.args, self.body, self.call_args)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            # The GO routine prints the return value as the last line
            # Extract just the last line to get the return value
            lines = exec_result.output.strip().split('\n')
            actual = lines[-1] if lines else ""
            assert actual == expected, \
                f"Expected {expected}, got {actual}"

    def outputs(self, expected: str) -> None:
        """Assert that the routine produces specific output."""
        compiler = self._get_compiler()
        # Use print_return=False so GO doesn't print the return value
        result = compiler.compile_routine(self.args, self.body, self.call_args, print_return=False)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            # Provide any queued input
            for inp in self.input_queue:
                zm.provide_input(inp)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            # Only strip trailing whitespace if expected doesn't end with whitespace
            # This preserves newlines for CRLF testing
            actual = exec_result.output
            if not expected.endswith(('\n', '\r', ' ', '\t')):
                actual = actual.rstrip()
            assert actual == expected, \
                f"Expected output '{expected}', got '{actual}'"

    def implies(self, *conditions: str) -> None:
        """Assert that all given conditions are true after execution."""
        compiler = self._get_compiler()
        # Build test that checks all conditions
        checks = " ".join(f"<COND (<NOT {c}> <RFALSE>)>" for c in conditions)
        test_body = f"{self.body} {checks} <RTRUE>"
        result = compiler.compile_routine(self.args, test_body)
        assert result.success, f"Compilation failed: {result.errors}"

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            # The GO routine does <PRINTN <TEST?ROUTINE>>, so check output
            # If TEST?ROUTINE returns 1 (true), output will be "1\n"
            # If it returns 0 (false), output will be "0\n"
            output_value = exec_result.output.strip()
            assert output_value == "1", \
                f"Condition check failed - one or more conditions were false (output={output_value})"

    def generates_code_matching(self, pattern: str) -> 'RoutineAssertion':
        """Assert that generated code matches a regex pattern."""
        compiler = self._get_compiler()
        result = compiler.compile_routine(self.args, self.body)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.zap_output:
            assert re.search(pattern, result.zap_output, re.MULTILINE), \
                f"Generated code does not match pattern '{pattern}'\nCode:\n{result.zap_output}"
        return self

    def and_matching(self, pattern: str) -> 'RoutineAssertion':
        """Chain another pattern match."""
        return self.generates_code_matching(pattern)

    def and_not_matching(self, pattern: str) -> 'RoutineAssertion':
        """Chain a negative pattern match."""
        return self.generates_code_not_matching(pattern)

    def generates_code_not_matching(self, pattern: str) -> 'RoutineAssertion':
        """Assert that generated code does NOT match a regex pattern."""
        compiler = self._get_compiler()
        result = compiler.compile_routine(self.args, self.body)
        assert result.success, f"Compilation failed: {result.errors}"

        if result.zap_output:
            assert not re.search(pattern, result.zap_output, re.MULTILINE), \
                f"Generated code should not match pattern '{pattern}'\nCode:\n{result.zap_output}"
        return self

    def _check_warnings(self, result: CompilationResult) -> None:
        """Check warning expectations."""
        if self.expect_no_warnings:
            assert not result.warnings, f"Expected no warnings, got: {result.warnings}"
        elif self.expected_warnings is not None:
            for code in self.expected_warnings:
                assert any(code in w for w in result.warnings), \
                    f"Expected warning {code}, got {result.warnings}"


class GlobalsAssertion:
    """
    Fluent assertion helper for testing global definitions.

    Usage:
        await AssertGlobals('<OBJECT FOO>', '<OBJECT BAR>').compiles()
        await AssertGlobals('<OBJECT FOO (IN BAR)>').implies('<IN? ,FOO ,BAR>')
    """

    def __init__(self, *globals_code: str):
        self.globals_code = list(globals_code)
        self.version = ZVersion.V3
        self.additional_globals: List[str] = []
        self.expected_warnings: Optional[List[str]] = None
        self.expect_no_warnings: bool = False

    def in_v3(self) -> 'GlobalsAssertion':
        self.version = ZVersion.V3
        return self

    def in_v4(self) -> 'GlobalsAssertion':
        self.version = ZVersion.V4
        return self

    def in_v5(self) -> 'GlobalsAssertion':
        self.version = ZVersion.V5
        return self

    def in_v6(self) -> 'GlobalsAssertion':
        self.version = ZVersion.V6
        return self

    def with_warnings(self, *codes: str) -> 'GlobalsAssertion':
        self.expected_warnings = list(codes) if codes else None
        return self

    def without_warnings(self, *codes: str) -> 'GlobalsAssertion':
        if codes:
            self.expected_warnings = []
        else:
            self.expect_no_warnings = True
        return self

    def with_global(self, code: str) -> 'GlobalsAssertion':
        """Add an additional global definition."""
        self.additional_globals.append(code)
        return self

    def _get_compiler(self) -> ZILCompiler:
        compiler = ZILCompiler(self.version)
        for g in self.additional_globals:
            compiler.add_global(g)
        return compiler

    def compiles(self) -> None:
        """Assert that the globals compile successfully."""
        compiler = self._get_compiler()
        result = compiler.compile_globals(*self.globals_code)
        assert result.success, f"Expected compilation to succeed, but got errors: {result.errors}"
        self._check_warnings(result)

    def does_not_compile(self, *error_codes: str, **kwargs) -> None:
        """Assert that the globals fail to compile."""
        compiler = self._get_compiler()
        result = compiler.compile_globals(*self.globals_code)
        assert not result.success, f"Expected compilation to fail, but it succeeded"
        if error_codes:
            for code in error_codes:
                assert code in result.error_codes, f"Expected error code {code}, got {result.error_codes}"

    def implies(self, *conditions: str) -> None:
        """Assert that conditions are true after the globals are defined."""
        compiler = self._get_compiler()

        # Build source with globals and a test routine
        source_parts = []

        # Add version directive based on self.version
        version_names = {
            ZVersion.V3: "ZIP",
            ZVersion.V4: "EZIP",
            ZVersion.V5: "XZIP",
            ZVersion.V6: "YZIP",
            ZVersion.GLULX: "GLULX",
        }
        if self.version in version_names:
            source_parts.append(f"<VERSION {version_names[self.version]}>")

        source_parts.extend(self.globals_code)
        source_parts.extend(self.additional_globals)

        checks = " ".join(f"<COND (<NOT {c}> <RFALSE>)>" for c in conditions)
        # Create test routine that returns true/false based on conditions
        source_parts.append(f'<ROUTINE TEST?ROUTINE () {checks} <RTRUE>>')
        # GO routine prints the return value so we can check it
        source_parts.append('<ROUTINE GO () <PRINTN <TEST?ROUTINE>> <QUIT>>')

        result = compiler._compile("\n".join(source_parts))
        assert result.success, f"Compilation failed: {result.errors}"

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            # Check output instead of return_value since dfrotz doesn't capture it
            output_value = exec_result.output.strip()
            assert output_value == "1", \
                f"Condition check failed - one or more conditions were false (output={output_value})"

    def generates_code_matching(self, pattern: str) -> 'GlobalsAssertion':
        """Assert that generated code matches a regex pattern."""
        compiler = self._get_compiler()
        result = compiler.compile_globals(*self.globals_code)
        assert result.success, f"Compilation failed: {result.errors}"

        if result.zap_output:
            assert re.search(pattern, result.zap_output, re.MULTILINE), \
                f"Generated code does not match pattern '{pattern}'"
        return self

    def generates_code_not_matching(self, pattern: str) -> 'GlobalsAssertion':
        """Assert that generated code does NOT match a regex pattern."""
        compiler = self._get_compiler()
        result = compiler.compile_globals(*self.globals_code)
        assert result.success, f"Compilation failed: {result.errors}"

        if result.zap_output:
            assert not re.search(pattern, result.zap_output, re.MULTILINE), \
                f"Generated code should not match pattern '{pattern}'"
        return self

    def generates_code_matching_func(self, func: callable) -> 'GlobalsAssertion':
        """Assert that generated code matches a custom function.

        Args:
            func: A function that takes the code string and returns True if it matches.
        """
        compiler = self._get_compiler()
        result = compiler.compile_globals(*self.globals_code)
        assert result.success, f"Compilation failed: {result.errors}"

        if result.zap_output:
            assert func(result.zap_output), \
                f"Generated code does not match custom function"
        return self

    def _check_warnings(self, result: CompilationResult) -> None:
        """Check warning expectations."""
        if self.expect_no_warnings:
            assert not result.warnings, f"Expected no warnings, got: {result.warnings}"
        elif self.expected_warnings is not None:
            for code in self.expected_warnings:
                assert any(code in w for w in result.warnings), \
                    f"Expected warning {code}, got {result.warnings}"


class EntryPointAssertion:
    """
    Fluent assertion helper for testing GO routine constraints.
    """

    def __init__(self, args: str, body: str):
        self.args = args
        self.body = body
        self.version = ZVersion.V3
        self.globals: List[str] = []

    def in_v3(self) -> 'EntryPointAssertion':
        self.version = ZVersion.V3
        return self

    def in_v6(self) -> 'EntryPointAssertion':
        self.version = ZVersion.V6
        return self

    def with_global(self, code: str) -> 'EntryPointAssertion':
        self.globals.append(code)
        return self

    def _get_compiler(self) -> ZILCompiler:
        compiler = ZILCompiler(self.version)
        for g in self.globals:
            compiler.add_global(g)
        return compiler

    def compiles(self) -> None:
        """Assert that the entry point compiles successfully."""
        compiler = self._get_compiler()
        result = compiler.compile_entry_point(self.args, self.body)
        assert result.success, f"Expected compilation to succeed, but got errors: {result.errors}"

    def does_not_compile(self) -> None:
        """Assert that the entry point fails to compile."""
        compiler = self._get_compiler()
        result = compiler.compile_entry_point(self.args, self.body)
        assert not result.success, f"Expected compilation to fail, but it succeeded"

    def does_not_throw(self) -> None:
        """Assert that compilation doesn't throw an exception."""
        compiler = self._get_compiler()
        try:
            compiler.compile_entry_point(self.args, self.body)
        except Exception as e:
            pytest.fail(f"Compilation threw an exception: {e}")


# Convenience functions matching ZILF's IntegrationTestClass
def AssertExpr(expr: str) -> ExprAssertion:
    """Create an expression assertion."""
    return ExprAssertion(expr)


def AssertRoutine(args: str, body: str) -> RoutineAssertion:
    """Create a routine assertion."""
    return RoutineAssertion(args, body)


def AssertGlobals(*globals_code: str) -> GlobalsAssertion:
    """Create a globals assertion."""
    return GlobalsAssertion(*globals_code)


def AssertEntryPoint(args: str, body: str) -> EntryPointAssertion:
    """Create an entry point assertion."""
    return EntryPointAssertion(args, body)


class RawAssertion:
    """
    Fluent assertion helper for testing raw ZIL source code.

    Usage:
        AssertRaw('<VERSION ZIP>\\n<ROUTINE GO () <QUIT>>').compiles()
        AssertRaw(code).outputs("Hello, world!\\n")
    """

    def __init__(self, source: str):
        self.source = source
        self.version = ZVersion.V3
        self.expected_warnings: Optional[List[str]] = None
        self.expect_no_warnings: bool = False

    def in_v3(self) -> 'RawAssertion':
        self.version = ZVersion.V3
        return self

    def in_v4(self) -> 'RawAssertion':
        self.version = ZVersion.V4
        return self

    def in_v5(self) -> 'RawAssertion':
        self.version = ZVersion.V5
        return self

    def in_v6(self) -> 'RawAssertion':
        self.version = ZVersion.V6
        return self

    def in_v7(self) -> 'RawAssertion':
        self.version = ZVersion.V7
        return self

    def in_v8(self) -> 'RawAssertion':
        self.version = ZVersion.V8
        return self

    def _detect_version_from_source(self) -> None:
        """Detect Z-machine version from VERSION directive in source."""
        import re
        match = re.search(r'<VERSION\s+(\w+)\s*>', self.source)
        if match:
            version_str = match.group(1).upper()
            version_map = {
                'ZIP': ZVersion.V3,
                'EZIP': ZVersion.V4,
                'XZIP': ZVersion.V5,
                'YZIP': ZVersion.V6,
                '3': ZVersion.V3,
                '4': ZVersion.V4,
                '5': ZVersion.V5,
                '6': ZVersion.V6,
                '7': ZVersion.V7,
                '8': ZVersion.V8,
            }
            if version_str in version_map:
                self.version = version_map[version_str]

    def with_warnings(self, *codes: str) -> 'RawAssertion':
        self.expected_warnings = list(codes) if codes else None
        return self

    def without_warnings(self) -> 'RawAssertion':
        self.expect_no_warnings = True
        return self

    def _get_compiler(self) -> ZILCompiler:
        self._detect_version_from_source()
        return ZILCompiler(self.version)

    def compiles(self) -> None:
        """Assert that the source compiles successfully."""
        compiler = self._get_compiler()
        result = compiler._compile(self.source)
        assert result.success, f"Expected compilation to succeed, but got errors: {result.errors}"
        self._check_warnings(result)

    def does_not_compile(self, *error_codes: str) -> None:
        """Assert that the source fails to compile."""
        compiler = self._get_compiler()
        result = compiler._compile(self.source)
        assert not result.success, f"Expected compilation to fail, but it succeeded"
        if error_codes:
            for code in error_codes:
                assert code in result.error_codes, f"Expected error code {code}, got {result.error_codes}"

    def outputs(self, expected: str) -> None:
        """Assert that the source produces specific output."""
        compiler = self._get_compiler()
        result = compiler._compile(self.source)
        assert result.success, f"Compilation failed: {result.errors}"
        self._check_warnings(result)

        if result.story_file:
            zm = ZMachine(result.story_file, self.version)
            exec_result = zm.execute()
            assert exec_result.success, f"Execution failed: {exec_result.error}"
            assert exec_result.output == expected, \
                f"Expected output '{expected}', got '{exec_result.output}'"

    def _check_warnings(self, result: CompilationResult) -> None:
        """Check warning expectations."""
        if self.expect_no_warnings:
            assert not result.warnings, f"Expected no warnings, got: {result.warnings}"
        elif self.expected_warnings is not None:
            for code in self.expected_warnings:
                assert any(code in w for w in result.warnings), \
                    f"Expected warning {code}, got {result.warnings}"


def AssertRaw(source: str) -> RawAssertion:
    """Create a raw source assertion."""
    return RawAssertion(source)


# Pytest fixtures
@pytest.fixture
def compiler_v3():
    """Fixture for V3 compiler."""
    return ZILCompiler(ZVersion.V3)


@pytest.fixture
def compiler_v4():
    """Fixture for V4 compiler."""
    return ZILCompiler(ZVersion.V4)


@pytest.fixture
def compiler_v5():
    """Fixture for V5 compiler."""
    return ZILCompiler(ZVersion.V5)


@pytest.fixture
def compiler_v6():
    """Fixture for V6 compiler."""
    return ZILCompiler(ZVersion.V6)
