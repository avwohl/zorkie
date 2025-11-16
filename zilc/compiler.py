"""
Main ZIL Compiler.

Coordinates lexing, parsing, code generation, and assembly.
"""

import sys
from typing import Optional
from pathlib import Path

from .lexer import Lexer
from .parser import Parser
from .parser.macro_expander import MacroExpander
from .codegen.codegen_improved import ImprovedCodeGenerator
from .zmachine import ZAssembler, ObjectTable, Dictionary


class ZILCompiler:
    """Main ZIL compiler class."""

    def __init__(self, version: int = 3, verbose: bool = False):
        self.version = version
        self.verbose = verbose
        self.compilation_flags = {}  # ZILF compilation flags

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

    def compile_file_multi(self, main_file: str, included_files: list = None) -> bytes:
        """
        Compile multiple ZIL files together.

        Args:
            main_file: Path to main ZIL file
            included_files: List of additional files to include

        Returns:
            Combined compiled bytecode
        """
        # Read main file
        with open(main_file, 'r', encoding='utf-8') as f:
            main_source = f.read()

        # Combine with included files
        combined_source = main_source

        if included_files:
            for inc_file in included_files:
                self.log(f"  Including: {inc_file}")
                with open(inc_file, 'r', encoding='utf-8') as f:
                    combined_source += f"\n\n;\"=== Included from {inc_file} ===\" \n\n"
                    combined_source += f.read()

        return self.compile_string(combined_source, main_file)

    def preprocess_ifiles(self, source: str, base_path: Path) -> str:
        """
        Preprocess IFILE directives by expanding them inline.

        Handles: <IFILE "filename"> - includes content of filename.zil

        Args:
            source: Source code with potential IFILE directives
            base_path: Base directory for resolving relative file paths

        Returns:
            Source code with IFILE directives expanded
        """
        import re

        # Pattern to match <IFILE "filename"> or <INSERT-FILE "filename">
        ifile_pattern = r'<\s*(?:IFILE|INSERT-FILE)\s+"([^"]+)"\s*>'

        def replace_ifile(match):
            filename = match.group(1)
            # Try adding .zil extension if not present
            if not filename.endswith('.zil'):
                filename += '.zil'

            # Resolve path relative to base_path
            file_path = base_path / filename.lower()

            try:
                self.log(f"  Including file: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Recursively process nested IFILE directives
                return self.preprocess_ifiles(content, base_path)
            except FileNotFoundError:
                raise FileNotFoundError(f"IFILE not found: {file_path}")

        return re.sub(ifile_pattern, replace_ifile, source, flags=re.IGNORECASE)

    def preprocess_zilf_directives(self, source: str) -> str:
        """
        Preprocess ZILF-specific directives:
        - COMPILATION-FLAG: Set compile-time flags
        - IFFLAG: Conditional compilation based on flags
        - VERSION?: Conditional compilation based on Z-machine version

        Args:
            source: Source code with potential ZILF directives

        Returns:
            Source code with directives evaluated and conditionals resolved
        """
        import re

        # First pass: Extract COMPILATION-FLAG directives
        # <COMPILATION-FLAG FLAGNAME <T>> or <COMPILATION-FLAG FLAGNAME <>>
        flag_pattern = r'<\s*COMPILATION-FLAG\s+(\w+)\s+<([^>]*)>\s*>'

        def extract_flag(match):
            flag_name = match.group(1)
            flag_value = match.group(2).strip()
            # <T> or <TRUE> means true, <> or <FALSE> means false
            self.compilation_flags[flag_name] = flag_value.upper() in ('T', 'TRUE')
            self.log(f"  Flag: {flag_name} = {self.compilation_flags[flag_name]}")
            return ''  # Remove the directive from source

        source = re.sub(flag_pattern, extract_flag, source, flags=re.IGNORECASE)

        # Second pass: Evaluate IFFLAG conditionals
        # Process manually to handle nested brackets properly
        source = self._process_ifflag(source)

        # Third pass: Evaluate VERSION? conditionals
        # Process manually to handle nested brackets properly
        source = self._process_version(source)

        return source

    def _process_ifflag(self, source: str) -> str:
        """Process IFFLAG directives with proper bracket balancing."""
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for <IFFLAG
            match = re.search(r'<\s*IFFLAG\s+', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            # Find the matching > for this <IFFLAG
            start = pos + match.start()  # Start of <IFFLAG
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Extract just the part after <IFFLAG and before >
                # content is like: <IFFLAG (BETA "...") (ELSE "...")>
                # Find where IFFLAG ends within content
                ifflag_match = re.match(r'<\s*IFFLAG\s+', content, re.IGNORECASE)
                if ifflag_match:
                    ifflag_content = content[ifflag_match.end():-1].strip()
                else:
                    ifflag_content = content[1:-1].strip()  # Fallback

                # Parse and evaluate
                parts = self._parse_conditional_parts(ifflag_content)
                if parts and 'condition' in parts:
                    flag_name = parts['condition']
                    if flag_name in self.compilation_flags and self.compilation_flags[flag_name]:
                        result.append(parts.get('true_expr', ''))
                    else:
                        result.append(parts.get('false_expr', ''))
                else:
                    # Can't parse, keep original
                    result.append(content)

                pos = end
            else:
                # Can't find matching bracket, skip
                result.append(match.group(0))
                pos += match.end()

        return ''.join(result)

    def _process_version(self, source: str) -> str:
        """Process VERSION? directives with proper bracket balancing."""
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for %<VERSION? or <VERSION? (% is optional)
            match = re.search(r'%?<\s*VERSION\?\s+', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            # Find the matching > for this VERSION?
            # Check if % prefix was present
            has_percent = source[pos + match.start()] == '%'
            start = pos + match.start() + (1 if has_percent else 0)  # +1 to skip % if present
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Extract just the part after <VERSION?
                version_content = content[len('<VERSION?'):-1].strip()  # Remove <VERSION? prefix and >

                # Parse and evaluate
                parts = self._parse_conditional_parts(version_content)
                if parts and 'condition' in parts:
                    target_version = parts['condition']
                    version_matches = False
                    if target_version == 'ZIP':
                        version_matches = (self.version == 3)
                    elif target_version == 'EZIP':
                        version_matches = (self.version == 4)
                    elif target_version == 'XZIP':
                        version_matches = (self.version == 5)

                    if version_matches:
                        result.append(parts.get('true_expr', ''))
                    else:
                        result.append(parts.get('false_expr', ''))
                else:
                    # Can't parse, keep original
                    result.append(('%' if has_percent else '') + content)

                pos = end
            else:
                # Can't find matching bracket, skip
                result.append(match.group(0))
                pos += match.end()

        return ''.join(result)

    def _extract_balanced_content(self, source: str, start_pos: int) -> tuple:
        """
        Extract content with balanced angle brackets.
        Returns (content, end_position) or (None, start_pos) if not balanced.
        """
        if start_pos >= len(source) or source[start_pos] != '<':
            return None, start_pos

        depth = 1
        pos = start_pos + 1

        while pos < len(source) and depth > 0:
            if source[pos] == '<':
                depth += 1
            elif source[pos] == '>':
                depth -= 1
            pos += 1

        if depth == 0:
            return source[start_pos:pos], pos
        else:
            return None, start_pos

    def _parse_conditional_parts(self, content: str) -> dict:
        """
        Parse conditional content: (CONDITION expr) (ELSE expr)
        Returns dict with 'condition', 'true_expr', 'false_expr'
        """
        content = content.strip()

        # Find first balanced parenthesis group
        if not content.startswith('('):
            return {}

        # Extract first group (CONDITION expr)
        depth = 0
        pos = 0
        for i, ch in enumerate(content):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    pos = i + 1
                    break

        if depth != 0:
            return {}

        first_group = content[1:pos-1].strip()  # Remove outer parens

        # Split on first whitespace to get condition name
        parts = first_group.split(None, 1)
        if not parts:
            return {}

        condition = parts[0]
        true_expr = parts[1] if len(parts) > 1 else ''

        # Look for (ELSE ...) group
        false_expr = ''
        remaining = content[pos:].strip()
        if remaining.startswith('('):
            # Check if it's an ELSE clause
            import re
            else_match = re.match(r'\(\s*ELSE\s+(.*)\)\s*$', remaining, re.IGNORECASE | re.DOTALL)
            if else_match:
                false_expr = else_match.group(1).strip()

        return {
            'condition': condition,
            'true_expr': true_expr,
            'false_expr': false_expr
        }

    def compile_string(self, source: str, filename: str = "<input>") -> bytes:
        """
        Compile ZIL source code to Z-machine bytecode.

        Args:
            source: ZIL source code as string
            filename: Filename for error messages

        Returns:
            Z-machine story file as bytes
        """
        # Preprocess IFILE directives
        base_path = Path(filename).parent if filename != "<input>" else Path.cwd()
        self.log("Preprocessing IFILE directives...")
        source = self.preprocess_ifiles(source, base_path)

        # Preprocess ZILF directives (COMPILATION-FLAG, IFFLAG, VERSION?)
        self.log("Preprocessing ZILF directives...")
        source = self.preprocess_zilf_directives(source)

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
        self.log(f"  {len(program.propdefs)} property definitions")
        self.log(f"  {len(program.syntax)} syntax definitions")
        self.log(f"  {len(program.macros)} macro definitions")

        # Macro expansion
        if program.macros:
            self.log("Expanding macros...")
            expander = MacroExpander()
            program = expander.expand_all(program)
            self.log(f"  Macros expanded")

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

        # Build property mapping from PROPDEF declarations
        prop_map = {
            'DESC': 1,    # Standard property always #1
            'LDESC': 2,   # Standard property always #2
        }
        next_prop_num = 3

        # Add user-defined properties from PROPDEF
        for propdef in program.propdefs:
            if propdef.name not in prop_map:
                prop_map[propdef.name] = next_prop_num
                next_prop_num += 1
                self.log(f"  PROPDEF {propdef.name} -> property #{prop_map[propdef.name]}")

        # Helper to extract property number and value
        def extract_properties(obj_node):
            """Extract properties from object node."""
            nonlocal next_prop_num  # Allow modification of outer scope variable
            props = {}
            for key, value in obj_node.properties.items():
                if key in prop_map:
                    prop_num = prop_map[key]
                    # Extract value from AST node
                    if hasattr(value, 'value'):
                        props[prop_num] = value.value
                    else:
                        props[prop_num] = value
                elif key not in ['FLAGS', 'SYNONYM', 'ADJECTIVE']:
                    # Unknown property, assign next number
                    if key not in prop_map:
                        prop_map[key] = next_prop_num
                        self.log(f"  Auto-assigned {key} -> property #{next_prop_num}")
                        next_prop_num += 1
                    prop_num = prop_map[key]
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

        # Build dictionary with vocabulary from objects
        self.log("Building dictionary...")
        dictionary = Dictionary(self.version)

        # Add BUZZ words (noise words that parser recognizes but ignores)
        if program.buzz_words:
            self.log(f"  Adding {len(program.buzz_words)} BUZZ words")
            dictionary.add_words(program.buzz_words, 'buzz')

        # Add standalone SYNONYM words (directions, verb synonyms, etc.)
        if program.synonym_words:
            self.log(f"  Adding {len(program.synonym_words)} SYNONYM words")
            dictionary.add_words(program.synonym_words, 'synonym')

        # Don't add hardcoded standard verbs - only add words from source
        # The official compiler only includes words that appear in:
        #   - SYNTAX declarations
        #   - BUZZ words
        #   - Standalone SYNONYM declarations
        #   - Object/Room SYNONYM and ADJECTIVE properties
        #   - PSEUDO properties

        # Extract SYNONYM and ADJECTIVE from objects
        obj_num = 1
        for obj in program.objects:
            # Add synonyms (nouns that refer to this object)
            if 'SYNONYM' in obj.properties:
                synonyms = obj.properties['SYNONYM']
                # SYNONYM can be a list of atoms
                if hasattr(synonyms, '__iter__') and not isinstance(synonyms, str):
                    for syn in synonyms:
                        if hasattr(syn, 'value'):
                            dictionary.add_synonym(syn.value, obj_num)
                        elif isinstance(syn, str):
                            dictionary.add_synonym(syn, obj_num)
                elif hasattr(synonyms, 'value'):
                    dictionary.add_synonym(synonyms.value, obj_num)

            # Add adjectives
            if 'ADJECTIVE' in obj.properties:
                adjectives = obj.properties['ADJECTIVE']
                if hasattr(adjectives, '__iter__') and not isinstance(adjectives, str):
                    for adj in adjectives:
                        if hasattr(adj, 'value'):
                            dictionary.add_adjective(adj.value, obj_num)
                        elif isinstance(adj, str):
                            dictionary.add_adjective(adj, obj_num)
                elif hasattr(adjectives, 'value'):
                    dictionary.add_adjective(adjectives.value, obj_num)

            # DISABLED: Don't add PSEUDO words to dictionary
            # PSEUDO strings are handled internally by the game, not via dictionary lookup
            # if 'PSEUDO' in obj.properties:
            #     pseudo = obj.properties['PSEUDO']
            #     if hasattr(pseudo, '__iter__') and not isinstance(pseudo, str):
            #         # PSEUDO is list of string/routine pairs: "WORD" HANDLER "WORD2" HANDLER2
            #         for i, item in enumerate(pseudo):
            #             # Only take strings (odd indices are routines)
            #             if hasattr(item, 'value') and isinstance(item.value, str):
            #                 dictionary.add_word(item.value.lower(), 'pseudo')

            obj_num += 1

        # Extract from rooms too
        for room in program.rooms:
            if 'SYNONYM' in room.properties:
                synonyms = room.properties['SYNONYM']
                if hasattr(synonyms, '__iter__') and not isinstance(synonyms, str):
                    for syn in synonyms:
                        if hasattr(syn, 'value'):
                            dictionary.add_synonym(syn.value, obj_num)
                        elif isinstance(syn, str):
                            dictionary.add_synonym(syn, obj_num)
                elif hasattr(synonyms, 'value'):
                    dictionary.add_synonym(synonyms.value, obj_num)

            # DISABLED: Don't add PSEUDO words from rooms
            # if 'PSEUDO' in room.properties:
            #     pseudo = room.properties['PSEUDO']
            #     if hasattr(pseudo, '__iter__') and not isinstance(pseudo, str):
            #         for i, item in enumerate(pseudo):
            #             if hasattr(item, 'value') and isinstance(item.value, str):
            #                 dictionary.add_word(item.value.lower(), 'pseudo')

            obj_num += 1

        # Extract verbs and prepositions from SYNTAX definitions
        syntax_words = set()
        for syntax_def in program.syntax:
            if syntax_def.pattern:
                for word in syntax_def.pattern:
                    # Skip OBJECT and other placeholders
                    if word.upper() not in ('OBJECT', 'FIND', 'HAVE', 'HELD',
                                             'ON-GROUND', 'IN-ROOM', 'TAKE',
                                             'MANY', 'SEARCH'):
                        # Skip special markers like flags in parens
                        if not (isinstance(word, str) and
                                (word.startswith('(') or word.endswith('BIT'))):
                            word_lower = word.lower() if isinstance(word, str) else str(word).lower()
                            syntax_words.add(word_lower)
                            # First word is verb, others are prepositions
                            word_type = 'verb' if syntax_def.pattern.index(word) == 0 else 'prep'
                            dictionary.add_word(word_lower, word_type)

        if syntax_words:
            self.log(f"  Added {len(syntax_words)} words from SYNTAX definitions")

        self.log(f"  Dictionary contains {len(dictionary.words)} words")
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
    parser.add_argument('-i', '--include', action='append',
                       help='Include additional ZIL files (can be used multiple times)')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    compiler = ZILCompiler(version=args.version, verbose=args.verbose)

    # Use multi-file compilation if includes are specified
    if args.include:
        try:
            # Determine output path
            output_path = args.output
            if output_path is None:
                input_file = Path(args.input)
                ext = f".z{args.version}"
                output_path = str(input_file.with_suffix(ext))

            compiler.log(f"Compiling {args.input} with {len(args.include)} included files...")
            story_data = compiler.compile_file_multi(args.input, args.include)

            # Write output
            compiler.log(f"Writing {output_path}...")
            with open(output_path, 'wb') as f:
                f.write(story_data)

            compiler.log(f"Compilation successful: {len(story_data)} bytes")
            success = True
        except Exception as e:
            print(f"Compilation error: {e}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            success = False
    else:
        success = compiler.compile_file(args.input, args.output)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
