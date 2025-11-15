"""
Main ZIL Compiler.

Coordinates lexing, parsing, code generation, and assembly.
"""

import sys
from typing import Optional
from pathlib import Path

from .lexer import Lexer
from .parser import Parser
from .codegen.codegen_improved import ImprovedCodeGenerator
from .zmachine import ZAssembler, ObjectTable, Dictionary


class ZILCompiler:
    """Main ZIL compiler class."""

    def __init__(self, version: int = 3, verbose: bool = False):
        self.version = version
        self.verbose = verbose

    def log(self, message: str):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[zilc] {message}", file=sys.stderr)

    def compile_file(self, input_path: str, output_path: Optional[str] = None) -> bool:
        """
        Compile a ZIL source file to Z-machine bytecode.

        Args:
            input_path: Path to .zil source file
            output_path: Path to output .z3/.z5/etc file (auto-generated if None)

        Returns:
            True if compilation succeeded, False otherwise
        """
        # Determine output path
        if output_path is None:
            input_file = Path(input_path)
            ext = f".z{self.version}"
            output_path = str(input_file.with_suffix(ext))

        try:
            # Read source file
            self.log(f"Reading {input_path}...")
            with open(input_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # Compile
            story_data = self.compile_string(source, str(input_path))

            # Write output
            self.log(f"Writing {output_path}...")
            with open(output_path, 'wb') as f:
                f.write(story_data)

            self.log(f"Compilation successful: {len(story_data)} bytes")
            return True

        except FileNotFoundError:
            print(f"Error: File not found: {input_path}", file=sys.stderr)
            return False
        except SyntaxError as e:
            print(f"Syntax error: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Compilation error: {e}", file=sys.stderr)
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

    def compile_string(self, source: str, filename: str = "<input>") -> bytes:
        """
        Compile ZIL source code to Z-machine bytecode.

        Args:
            source: ZIL source code as string
            filename: Filename for error messages

        Returns:
            Z-machine story file as bytes
        """
        # Lexical analysis
        self.log("Lexing...")
        lexer = Lexer(source, filename)
        tokens = lexer.tokenize()
        self.log(f"  {len(tokens)} tokens")

        # Parsing
        self.log("Parsing...")
        parser = Parser(tokens, filename)
        program = parser.parse()
        self.log(f"  {len(program.routines)} routines")
        self.log(f"  {len(program.objects)} objects")
        self.log(f"  {len(program.rooms)} rooms")
        self.log(f"  {len(program.globals)} globals")

        # Use program version if specified
        if program.version:
            self.version = program.version
            self.log(f"  Target version: {self.version}")

        # Code generation
        self.log("Generating code...")
        codegen = ImprovedCodeGenerator(self.version)
        routines_code = codegen.generate(program)
        self.log(f"  {len(routines_code)} bytes of routines")

        # Build object table
        self.log("Building object table...")
        obj_table = ObjectTable(self.version)
        for obj in program.objects:
            obj_table.add_object(obj.name)
        for room in program.rooms:
            obj_table.add_object(room.name)
        objects_data = obj_table.build()

        # Build dictionary
        self.log("Building dictionary...")
        dictionary = Dictionary(self.version)
        # TODO: Extract words from SYNTAX definitions
        dictionary.add_words(['take', 'drop', 'quit', 'look', 'inventory'])
        dict_data = dictionary.build()

        # Assemble story file
        self.log("Assembling story file...")
        assembler = ZAssembler(self.version)
        story = assembler.build_story_file(
            routines_code,
            objects_data,
            dict_data
        )

        return story


def main():
    """Command-line interface for the compiler."""
    import argparse

    parser = argparse.ArgumentParser(
        description='ZIL Compiler - Compile ZIL source code to Z-machine bytecode'
    )
    parser.add_argument('input', help='Input .zil source file')
    parser.add_argument('-o', '--output', help='Output story file (.z3, .z5, etc.)')
    parser.add_argument('-v', '--version', type=int, default=3,
                       choices=[3, 4, 5, 8],
                       help='Target Z-machine version (default: 3)')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    compiler = ZILCompiler(version=args.version, verbose=args.verbose)
    success = compiler.compile_file(args.input, args.output)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
