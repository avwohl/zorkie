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

        # Build object table with proper properties
        self.log("Building object table...")
        obj_table = ObjectTable(self.version, text_encoder=codegen.encoder)

        # Helper to convert FLAGS to attribute bitmask
        def flags_to_attributes(flags):
            """Convert FLAGS list to attribute bitmask."""
            attr_mask = 0

            # Handle single flag or list of flags
            if not flags:
                return 0

            # If it's an AST node, extract the value
            from .parser.ast_nodes import AtomNode, FormNode
            if isinstance(flags, AtomNode):
                flags = [flags.value]
            elif isinstance(flags, (list, tuple)):
                # Extract atom values from list
                flag_names = []
                for f in flags:
                    if isinstance(f, AtomNode):
                        flag_names.append(f.value)
                    elif isinstance(f, str):
                        flag_names.append(f)
                flags = flag_names
            else:
                return 0

            for flag in flags:
                # Try to get flag number from constants
                if flag in codegen.constants:
                    bit_num = codegen.constants[flag]
                    attr_mask |= (1 << bit_num)
            return attr_mask

        # Helper to extract property number and value
        def extract_properties(obj_node):
            """Extract properties from object node."""
            props = {}
            for key, value in obj_node.properties.items():
                # Map property name to number
                # For now, use simplified mapping
                # In full implementation, would need proper property number assignment
                prop_map = {
                    'DESC': 1,
                    'LDESC': 2,
                    'SIZE': 3,
                    'VALUE': 4,
                    'CAPACITY': 5,
                }

                if key in prop_map:
                    prop_num = prop_map[key]
                    # Extract value from AST node
                    if hasattr(value, 'value'):
                        props[prop_num] = value.value
                    else:
                        props[prop_num] = value

            return props

        # Add objects with properties
        for obj in program.objects:
            attributes = flags_to_attributes(obj.properties.get('FLAGS', []))
            properties = extract_properties(obj)
            obj_table.add_object(
                name=obj.name,
                attributes=attributes,
                properties=properties
            )

        # Add rooms (which are also objects)
        for room in program.rooms:
            attributes = flags_to_attributes(room.properties.get('FLAGS', []))
            properties = extract_properties(room)
            obj_table.add_object(
                name=room.name,
                attributes=attributes,
                properties=properties
            )

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
