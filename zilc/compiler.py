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

    def __init__(self, version: int = 3, verbose: bool = False, enable_string_dedup: bool = False,
                 include_paths: Optional[list] = None, lax_brackets: bool = False):
        self.version = version
        self.verbose = verbose
        self.enable_string_dedup = enable_string_dedup
        self.compilation_flags = {}  # ZILF compilation flags
        self.include_paths = include_paths or []  # Additional paths to search for includes
        self.lax_brackets = lax_brackets  # Allow unbalanced brackets (extra >) for source files like Beyond Zork

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

        # Pattern to match <IFILE "filename"> or <INSERT-FILE "filename" T>
        # Second parameter (T or other) is optional and ignored
        ifile_pattern = r'<\s*(?:IFILE|INSERT-FILE)\s+"([^"]+)"(?:\s+[^>]*)?\s*>'

        def replace_ifile(match):
            filename = match.group(1)
            # Try adding .zil extension if not present
            if not filename.endswith('.zil'):
                filename += '.zil'

            # Search for file in base_path and include_paths
            search_paths = [base_path] + [Path(p) for p in self.include_paths]
            file_path = None
            for search_path in search_paths:
                candidate = search_path / filename.lower()
                if candidate.exists():
                    file_path = candidate
                    break
                # Also try without lowercasing
                candidate = search_path / filename
                if candidate.exists():
                    file_path = candidate
                    break

            if file_path is None:
                raise FileNotFoundError(f"IFILE not found: {filename} (searched: {[str(p) for p in search_paths]})")

            try:
                self.log(f"  Including file: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Preprocess control characters in included file
                content = self.preprocess_control_characters(content)
                # Recursively process nested IFILE directives - use file's parent as new base
                return self.preprocess_ifiles(content, file_path.parent)
            except FileNotFoundError:
                raise FileNotFoundError(f"IFILE not found: {file_path}")

        return re.sub(ifile_pattern, replace_ifile, source, flags=re.IGNORECASE)

    def preprocess_control_characters(self, source: str) -> str:
        """
        Preprocess text representations of control characters.
        Converts ^L (form-feed marker) to actual whitespace.

        Args:
            source: Source code with potential control character markers

        Returns:
            Source code with control characters converted
        """
        import re
        # Replace /^L (form-feed marker with slash) with newlines
        # Must be done first to avoid leaving standalone /
        source = re.sub(r'/\^L', '\n', source)
        # Replace ^L (form-feed marker) with newlines
        source = source.replace('^L', '\n')
        return source

    def preprocess_zilf_directives(self, source: str) -> str:
        """
        Preprocess ZILF-specific directives:
        - COMPILATION-FLAG: Set compile-time flags
        - IFFLAG: Conditional compilation based on flags
        - VERSION?: Conditional compilation based on Z-machine version
        - SETG: Track global variable values for compile-time evaluation
        - %<COND>: Compile-time conditional evaluation

        Args:
            source: Source code with potential ZILF directives

        Returns:
            Source code with directives evaluated and conditionals resolved
        """
        import re

        # Track compile-time global values for %<COND> evaluation
        self.compile_globals = {}

        # Extract SETG directives to track compile-time values
        # <SETG VARNAME value>
        setg_pattern = r'<\s*SETG\s+([A-Z0-9\-?]+)\s+(\d+|T|<>)\s*>'
        def extract_setg(match):
            var_name = match.group(1)
            var_value = match.group(2)
            if var_value.isdigit():
                self.compile_globals[var_name] = int(var_value)
            elif var_value == 'T':
                self.compile_globals[var_name] = True
            elif var_value == '<>':
                self.compile_globals[var_name] = False
            self.log(f"  Global: {var_name} = {self.compile_globals.get(var_name)}")
            return match.group(0)  # Keep the SETG in source
        source = re.sub(setg_pattern, extract_setg, source, flags=re.IGNORECASE)

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

        # Fourth pass: Evaluate %<COND> compile-time conditionals
        source = self._process_compile_cond(source)

        # Fifth pass: Evaluate %<+>, %<->, %<*>, etc. compile-time arithmetic
        source = self._process_compile_arithmetic(source)

        # Sixth pass: Skip MDL macro definitions (DEFMAC, DEFINE) that we can't process
        source = self._skip_mdl_macros(source)

        # Seventh pass: If lax_brackets enabled, remove extraneous > brackets
        if self.lax_brackets:
            source = self._fix_lax_brackets(source)

        return source

    def _skip_mdl_macros(self, source: str) -> str:
        """
        Skip MDL macro definitions that we can't process.
        These include <DEFMAC ...> and <DEFINE ...> blocks.
        """
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for <DEFMAC or <DEFINE
            match = re.search(r'<\s*(DEFMAC|DEFINE)\s+', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            # Find the matching > for this <DEFMAC or <DEFINE
            start = pos + match.start()
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Skip the macro definition entirely
                pos = end
            else:
                # Can't find matching bracket, skip this character
                result.append(source[pos + match.start()])
                pos += match.start() + 1

        return ''.join(result)

    def _fix_lax_brackets(self, source: str) -> str:
        """
        Fix bracket imbalances in lax mode.
        This handles source files like Beyond Zork that have inherent
        bracket imbalances from historical editing.

        Strategy:
        1. Parse through tracking depth (ignoring strings)
        2. Remove any > that would make depth go negative
        3. Add closing > at end for any unclosed forms
        """
        result = []
        depth = 0
        i = 0
        removed_count = 0

        while i < len(source):
            ch = source[i]

            if ch == '"':
                # Skip strings entirely - brackets inside don't count
                result.append(ch)
                i += 1
                while i < len(source) and source[i] != '"':
                    if source[i] == '\\' and i + 1 < len(source):
                        result.append(source[i])
                        i += 1
                    result.append(source[i])
                    i += 1
                if i < len(source):
                    result.append(source[i])  # closing quote
                    i += 1
            elif ch == ';':
                # Check for form comments like ;<...> or ;[...] or ;"..."
                if i + 1 < len(source):
                    next_ch = source[i + 1]
                    if next_ch == '<':
                        # Skip ;<...> comment
                        result.append(ch)
                        i += 1
                        result.append(source[i])  # <
                        i += 1
                        comment_depth = 1
                        while i < len(source) and comment_depth > 0:
                            if source[i] == '<':
                                comment_depth += 1
                            elif source[i] == '>':
                                comment_depth -= 1
                            result.append(source[i])
                            i += 1
                        continue
                    elif next_ch == '[':
                        # Skip ;[...] comment
                        result.append(ch)
                        i += 1
                        result.append(source[i])  # [
                        i += 1
                        comment_depth = 1
                        while i < len(source) and comment_depth > 0:
                            if source[i] == '[':
                                comment_depth += 1
                            elif source[i] == ']':
                                comment_depth -= 1
                            result.append(source[i])
                            i += 1
                        continue
                    elif next_ch == '"':
                        # Skip ;"..." comment
                        result.append(ch)
                        i += 1
                        result.append(source[i])  # "
                        i += 1
                        while i < len(source) and source[i] != '"':
                            if source[i] == '\\' and i + 1 < len(source):
                                result.append(source[i])
                                i += 1
                            result.append(source[i])
                            i += 1
                        if i < len(source):
                            result.append(source[i])  # closing quote
                            i += 1
                        continue
                result.append(ch)
                i += 1
            elif ch == '<':
                depth += 1
                result.append(ch)
                i += 1
            elif ch == '>':
                if depth > 0:
                    depth -= 1
                    result.append(ch)
                else:
                    # Extraneous > - skip it
                    removed_count += 1
                i += 1
            else:
                result.append(ch)
                i += 1

        if removed_count > 0:
            self.log(f"  Lax mode: removed {removed_count} extraneous '>' brackets")

        # Add closing brackets for unclosed forms
        if depth > 0:
            self.log(f"  Lax mode: adding {depth} closing '>' brackets for unclosed forms")
            result.append('\n' + '>' * depth)

        return ''.join(result)

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
        Properly handles strings - doesn't count <> inside string literals.
        """
        if start_pos >= len(source) or source[start_pos] != '<':
            return None, start_pos

        depth = 1
        pos = start_pos + 1

        while pos < len(source) and depth > 0:
            ch = source[pos]
            if ch == '"':
                # Skip string content - don't count brackets inside strings
                pos += 1
                while pos < len(source) and source[pos] != '"':
                    if source[pos] == '\\' and pos + 1 < len(source):
                        pos += 1  # skip escape char
                    pos += 1
                if pos < len(source):
                    pos += 1  # skip closing "
            elif ch == '<':
                depth += 1
                pos += 1
            elif ch == '>':
                depth -= 1
                pos += 1
            else:
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

    def _process_compile_cond(self, source: str) -> str:
        """
        Process %<COND> compile-time conditionals.
        Example: %<COND (<==? ,ZORK-NUMBER 1> '(...)) (T '(...))>
        Evaluates at compile time and splices result into code.
        """
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for %<COND (note: % prefix is critical)
            match = re.search(r'%<\s*COND\s+', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            # Find the matching > for this %<COND
            # Skip the % and start from <
            start = pos + match.start() + 1  # +1 to skip %
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Evaluate the COND at compile time
                evaluated = self._evaluate_compile_cond(content)
                result.append(evaluated)
                pos = end
            else:
                # Can't find matching bracket, keep original
                result.append(match.group(0))
                pos += match.end()

        return ''.join(result)

    def _evaluate_compile_cond(self, content: str) -> str:
        """
        Evaluate a compile-time COND expression.
        Returns the selected branch as a string.
        """
        import re

        # content is like: <COND (test1 result1) (test2 result2) ...>
        # Extract just the COND body (remove <COND and final >)
        cond_match = re.match(r'<\s*COND\s+(.*)\s*>\s*$', content, re.DOTALL | re.IGNORECASE)
        if not cond_match:
            return content  # Can't parse, return as-is

        cond_body = cond_match.group(1).strip()

        # Parse clauses: each is a parenthesized (test result...) pair
        clauses = self._parse_cond_clauses(cond_body)

        # Evaluate each clause
        for test, result in clauses:
            if self._evaluate_compile_test(test):
                # This clause matches, return its result
                # Strip leading quote if present (quote means "literal")
                result = result.strip()
                if result.startswith("'"):
                    result = result[1:].strip()
                return result

        # No clause matched, return empty
        return ''

    def _parse_cond_clauses(self, body: str) -> list:
        """Parse COND clauses into (test, result) pairs."""
        clauses = []
        pos = 0

        while pos < len(body):
            # Skip whitespace
            while pos < len(body) and body[pos] in ' \t\n\r':
                pos += 1

            if pos >= len(body):
                break

            # Expect (test result...)
            if body[pos] != '(':
                break

            # Find matching )
            depth = 1
            start = pos + 1
            pos += 1

            while pos < len(body) and depth > 0:
                if body[pos] == '(':
                    depth += 1
                elif body[pos] == ')':
                    depth -= 1
                pos += 1

            if depth == 0:
                clause_content = body[start:pos-1].strip()
                # Split into test and result
                # The test is the first complete s-expression
                test, result = self._split_first_sexpr(clause_content)
                clauses.append((test.strip(), result.strip()))

        return clauses

    def _split_first_sexpr(self, text: str) -> tuple:
        """
        Split text into first s-expression and the rest.
        Returns (first_sexpr, rest)
        """
        text = text.strip()
        if not text:
            return ('', '')

        # If it starts with <, find matching >
        if text[0] == '<':
            depth = 1
            pos = 1
            while pos < len(text) and depth > 0:
                if text[pos] == '<':
                    depth += 1
                elif text[pos] == '>':
                    depth -= 1
                pos += 1
            if depth == 0:
                return (text[:pos], text[pos:].strip())
            else:
                # Unmatched, treat whole thing as test
                return (text, '')

        # If it starts with (, find matching )
        elif text[0] == '(':
            depth = 1
            pos = 1
            while pos < len(text) and depth > 0:
                if text[pos] == '(':
                    depth += 1
                elif text[pos] == ')':
                    depth -= 1
                pos += 1
            if depth == 0:
                return (text[:pos], text[pos:].strip())
            else:
                # Unmatched, treat whole thing as test
                return (text, '')

        # Otherwise, split on first whitespace
        else:
            parts = text.split(None, 1)
            if len(parts) == 2:
                return (parts[0], parts[1])
            else:
                return (parts[0], '')

    def _process_compile_arithmetic(self, source: str) -> str:
        """
        Process compile-time arithmetic expressions.
        Handles: %<+ x y>, %<- x y>, %<* x y>, %</ x y>, %<MOD x y>, %<ASCII ...>
        Also handles other compile-time forms like %<LENGTH table> that we can't evaluate.

        Note: %<" is MDL escape for literal quote, not a compile-time form!
        Similarly %<, %<. etc. are not compile-time forms.
        """
        import re
        result = []
        pos = 0

        # Valid compile-time operators that start a form
        # These must be followed by the operator name
        compile_ops = ('+', '-', '*', '/', 'MOD', 'BAND', 'BOR', 'LSH', 'ASCII', 'LENGTH',
                       'COND', 'OR', 'AND', 'NOT', 'EQUAL?', '==?', 'N==?', 'G?', 'L?',
                       'GASSIGNED?', 'ASSIGNED?', 'TYPE?', 'EMPTY?', 'NTH', 'REST',
                       'MAPF', 'MAPR', 'ILIST', 'IVECTOR', 'ITABLE', 'STRING', 'BYTE',
                       'FORM', 'CHTYPE', 'PARSE', 'UNPARSE', 'SPNAME', 'PNAME')

        while pos < len(source):
            # Look for %< (compile-time form)
            match = re.search(r'%<', source[pos:])
            if not match:
                result.append(source[pos:])
                break

            match_pos = pos + match.start()

            # Check if this is a valid compile-time form
            # Peek at what comes after %<
            after_pos = match_pos + 2  # Skip %<
            # Skip whitespace
            while after_pos < len(source) and source[after_pos] in ' \t':
                after_pos += 1

            # Check if what follows looks like a compile-time operator
            is_compile_form = False
            if after_pos < len(source):
                remaining = source[after_pos:after_pos + 20].upper()
                for op in compile_ops:
                    if remaining.startswith(op):
                        # Must be followed by whitespace or delimiter
                        if len(remaining) == len(op) or not remaining[len(op)].isalnum():
                            is_compile_form = True
                            break

            if not is_compile_form:
                # Not a compile-time form - keep the %< as-is
                result.append(source[pos:match_pos + 2])  # Include %<
                pos = match_pos + 2
                continue

            # Add text before match
            result.append(source[pos:match_pos])

            # Find the matching > for this %<
            # Skip the % and start from <
            start = match_pos + 1  # +1 to skip %
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Try to evaluate the expression
                evaluated = self._evaluate_compile_expr(content)
                if evaluated is not None:
                    result.append(str(evaluated))
                else:
                    # Can't evaluate - leave placeholder 0 to avoid parse errors
                    # This is not ideal but allows compilation to continue
                    result.append('0')
                pos = end
            else:
                # Can't find matching bracket, skip
                result.append('%')
                pos = match_pos + 1

        return ''.join(result)

    def _evaluate_compile_expr(self, content: str) -> object:
        """
        Evaluate a compile-time expression.
        Returns the result or None if can't evaluate.
        Content is like: <+ ,C-TABLE-LENGTH 1>
        """
        import re

        # Remove outer <...>
        content = content.strip()
        if content.startswith('<') and content.endswith('>'):
            content = content[1:-1].strip()
        else:
            return None

        # Parse operator and operands
        parts = content.split(None, 1)
        if not parts:
            return None

        op = parts[0].upper()
        args_str = parts[1] if len(parts) > 1 else ''

        # Handle arithmetic operators
        if op in ('+', '-', '*', '/', 'MOD'):
            args = self._parse_compile_args(args_str)
            if args is None:
                return None
            try:
                if op == '+':
                    return sum(args)
                elif op == '-':
                    return args[0] - sum(args[1:]) if len(args) > 1 else -args[0]
                elif op == '*':
                    result = 1
                    for a in args:
                        result *= a
                    return result
                elif op == '/':
                    return args[0] // args[1] if len(args) > 1 else 0
                elif op == 'MOD':
                    return args[0] % args[1] if len(args) > 1 else 0
            except (TypeError, ValueError, ZeroDivisionError):
                return None

        # Handle BAND, BOR, BNOT
        elif op == 'BAND':
            args = self._parse_compile_args(args_str)
            if args is None or len(args) < 2:
                return None
            result = args[0]
            for a in args[1:]:
                result &= a
            return result

        elif op == 'BOR':
            args = self._parse_compile_args(args_str)
            if args is None or len(args) < 2:
                return None
            result = args[0]
            for a in args[1:]:
                result |= a
            return result

        # Handle LSH (left shift)
        elif op == 'LSH':
            args = self._parse_compile_args(args_str)
            if args is None or len(args) < 2:
                return None
            return args[0] << args[1]

        # Handle LENGTH - we can't evaluate this without knowing the table
        # Return None to indicate we can't evaluate

        return None

    def _parse_compile_args(self, args_str: str) -> list:
        """
        Parse compile-time arguments like ",VAR 1 ,OTHER".
        Returns list of integers or None if can't parse.
        """
        args = []
        pos = 0

        while pos < len(args_str):
            # Skip whitespace
            while pos < len(args_str) and args_str[pos] in ' \t\n\r':
                pos += 1

            if pos >= len(args_str):
                break

            # Check for global variable reference ,VAR
            if args_str[pos] == ',':
                pos += 1  # skip comma
                # Read variable name
                start = pos
                while pos < len(args_str) and (args_str[pos].isalnum() or args_str[pos] in '-_?'):
                    pos += 1
                var_name = args_str[start:pos].upper()
                if var_name in self.compile_globals:
                    val = self.compile_globals[var_name]
                    if isinstance(val, (int, bool)):
                        args.append(int(val))
                    else:
                        return None  # Can't handle non-numeric
                else:
                    return None  # Unknown variable

            # Check for number
            elif args_str[pos].isdigit() or (args_str[pos] == '-' and pos + 1 < len(args_str) and args_str[pos + 1].isdigit()):
                start = pos
                if args_str[pos] == '-':
                    pos += 1
                while pos < len(args_str) and args_str[pos].isdigit():
                    pos += 1
                args.append(int(args_str[start:pos]))

            # Check for nested compile-time form %<...>
            elif args_str[pos] == '%' and pos + 1 < len(args_str) and args_str[pos + 1] == '<':
                # Skip % and find matching >
                pos += 1  # skip %
                depth = 1
                start = pos
                pos += 1  # skip <
                while pos < len(args_str) and depth > 0:
                    if args_str[pos] == '<':
                        depth += 1
                    elif args_str[pos] == '>':
                        depth -= 1
                    pos += 1
                if depth == 0:
                    nested_content = args_str[start:pos]
                    nested_val = self._evaluate_compile_expr(nested_content)
                    if nested_val is not None:
                        args.append(nested_val)
                    else:
                        return None
                else:
                    return None

            else:
                # Unknown token, can't parse
                return None

        return args if args else None

    def _evaluate_compile_test(self, test: str) -> bool:
        """Evaluate a compile-time test expression."""
        import re

        # Handle different test types:
        # - T (always true)
        # - <==? ,VAR value>
        # - <GASSIGNED? VAR>
        # - <EQUAL? ...>
        # - etc.

        if test.upper() == 'T':
            return True

        if test.upper() == '<>':
            return False

        # Match <GASSIGNED? VAR>
        gassigned_match = re.match(r'<\s*GASSIGNED\?\s+([A-Z0-9\-?]+)\s*>', test, re.IGNORECASE)
        if gassigned_match:
            var_name = gassigned_match.group(1)
            # Check if variable is in compile-time globals
            return var_name in self.compile_globals

        # Match <==? ,VAR value>
        eq_match = re.match(r'<\s*==\?\s+,([A-Z0-9\-?]+)\s+(\d+)\s*>', test, re.IGNORECASE)
        if eq_match:
            var_name = eq_match.group(1)
            var_value = int(eq_match.group(2))
            # Check compile-time globals
            if var_name in self.compile_globals:
                return self.compile_globals[var_name] == var_value
            return False

        # Default: can't evaluate, return False
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
        # Preprocess control characters (^L etc.)
        source = self.preprocess_control_characters(source)

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

        # Build abbreviations table (V2+)
        abbreviations_table = None
        if self.version >= 2:
            from .zmachine.abbreviations import AbbreviationsTable
            self.log("Building abbreviations table...")

            # Collect all strings from the program
            all_strings = []

            # Strings from object/room descriptions
            for obj in program.objects + program.rooms:
                for key, value in obj.properties.items():
                    if isinstance(value, str):
                        all_strings.append(value)
                    elif hasattr(value, 'value') and isinstance(value.value, str):
                        all_strings.append(value.value)

            # Strings from routines (TELL statements, inline strings)
            from .parser.ast_nodes import FormNode, StringNode, CondNode, RepeatNode
            def collect_strings_from_node(node):
                """Recursively collect strings from any AST node."""
                if node is None:
                    return
                elif isinstance(node, StringNode):
                    all_strings.append(node.value)
                elif isinstance(node, FormNode):
                    # Recurse into all operands
                    for operand in node.operands:
                        collect_strings_from_node(operand)
                elif isinstance(node, CondNode):
                    # CondNode has clauses: list of (condition, actions) tuples
                    for clause in node.clauses:
                        if isinstance(clause, (list, tuple)):
                            # clause is (condition, actions)
                            for item in clause:
                                collect_strings_from_node(item)
                        else:
                            collect_strings_from_node(clause)
                elif isinstance(node, RepeatNode):
                    # RepeatNode has bindings and body
                    for statement in node.body:
                        collect_strings_from_node(statement)
                elif isinstance(node, (list, tuple)):
                    # Recurse into lists/tuples
                    for item in node:
                        collect_strings_from_node(item)
                # AtomNode, NumberNode, etc. don't contain strings

            for routine in program.routines:
                for statement in routine.body:
                    collect_strings_from_node(statement)

            self.log(f"  Collected {len(all_strings)} strings")

            # Build abbreviations table
            # Generate more candidates than needed (1000) to allow overlap elimination
            abbreviations_table = AbbreviationsTable()
            abbreviations_table.analyze_strings(all_strings, max_abbrevs=1000)
            self.log(f"  Generated {len(abbreviations_table)} abbreviation candidates")

        # Create string table for deduplication (optional - controlled by flag)
        string_table = None
        if self.enable_string_dedup:
            from .zmachine.string_table import StringTable
            from .zmachine.text_encoding import ZTextEncoder
            text_encoder = ZTextEncoder(self.version, abbreviations_table=abbreviations_table)
            string_table = StringTable(text_encoder)
            self.log("String table deduplication enabled")

        # Code generation
        # NOTE: We don't pass abbreviations_table to code generator because
        # abbreviation encoding in strings requires the abbreviation table to be
        # properly positioned in the final file, which happens later during assembly.
        # For now, encode strings without abbreviations for correctness.
        self.log("Generating code...")
        codegen = ImprovedCodeGenerator(self.version, abbreviations_table=None,
                                       string_table=string_table)
        routines_code = codegen.generate(program)
        self.log(f"  {len(routines_code)} bytes of routines")

        # Build globals data with initial values
        globals_data = codegen.build_globals_data()
        if codegen.global_values:
            self.log(f"  {len(codegen.global_values)} globals with initial values")

        if string_table is not None:
            self.log(f"  String table: {len(string_table)} unique strings")

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
                            val = syn.value
                            # Convert to string if it's a number
                            if isinstance(val, (int, float)):
                                val = str(val)
                            dictionary.add_synonym(val, obj_num)
                        elif isinstance(syn, str):
                            dictionary.add_synonym(syn, obj_num)
                        elif isinstance(syn, (int, float)):
                            dictionary.add_synonym(str(syn), obj_num)
                elif hasattr(synonyms, 'value'):
                    val = synonyms.value
                    if isinstance(val, (int, float)):
                        val = str(val)
                    dictionary.add_synonym(val, obj_num)

            # Add adjectives
            if 'ADJECTIVE' in obj.properties:
                adjectives = obj.properties['ADJECTIVE']
                if hasattr(adjectives, '__iter__') and not isinstance(adjectives, str):
                    for adj in adjectives:
                        if hasattr(adj, 'value'):
                            val = adj.value
                            if isinstance(val, (int, float)):
                                val = str(val)
                            dictionary.add_adjective(val, obj_num)
                        elif isinstance(adj, str):
                            dictionary.add_adjective(adj, obj_num)
                        elif isinstance(adj, (int, float)):
                            dictionary.add_adjective(str(adj), obj_num)
                elif hasattr(adjectives, 'value'):
                    val = adjectives.value
                    if isinstance(val, (int, float)):
                        val = str(val)
                    dictionary.add_adjective(val, obj_num)

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

        # Run optimization passes before assembly
        self.log("Running optimization passes...")
        from .optimization.passes import OptimizationPipeline, StringDeduplicationPass, AbbreviationOptimizationPass

        compilation_data = {
            'routines_code': routines_code,
            'objects_data': objects_data,
            'dictionary_data': dict_data,
            'abbreviations_table': abbreviations_table,
            'program': program
        }

        pipeline = OptimizationPipeline(verbose=self.verbose)
        pipeline.add_pass(StringDeduplicationPass)
        pipeline.add_pass(AbbreviationOptimizationPass)

        compilation_data = pipeline.run(compilation_data)

        # Extract optimized data (may have been modified by optimization passes)
        routines_code = compilation_data['routines_code']
        objects_data = compilation_data['objects_data']
        dict_data = compilation_data['dictionary_data']
        abbreviations_table = compilation_data.get('abbreviations_table', abbreviations_table)

        # Log optimization statistics
        if 'optimization_stats' in compilation_data:
            for pass_name, stats in compilation_data['optimization_stats'].items():
                if stats:
                    self.log(f"  {pass_name}:")
                    for key, value in stats.items():
                        if key != 'most_common':  # Skip detailed list
                            self.log(f"    {key}: {value}")

        # Re-encode abbreviations if they were optimized
        if abbreviations_table and len(abbreviations_table) > 0:
            from .zmachine.text_encoding import ZTextEncoder
            text_encoder = ZTextEncoder(self.version)
            abbreviations_table.encode_abbreviations(text_encoder)
            self.log(f"  Encoded {len(abbreviations_table)} optimized abbreviations")

        # Assemble story file
        self.log("Assembling story file...")
        assembler = ZAssembler(self.version)
        story = assembler.build_story_file(
            routines_code,
            objects_data,
            dict_data,
            globals_data=globals_data,
            abbreviations_table=abbreviations_table,
            string_table=string_table
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
                       choices=[1, 2, 3, 4, 5, 6, 7, 8],
                       metavar='1-8',
                       help='Target Z-machine version (default: 3)')
    parser.add_argument('-i', '--include', action='append',
                       help='Include additional ZIL files (can be used multiple times)')
    parser.add_argument('--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('--string-dedup', action='store_true',
                       help='Enable string table deduplication (uses PRINT_PADDR)')

    args = parser.parse_args()

    compiler = ZILCompiler(version=args.version, verbose=args.verbose,
                          enable_string_dedup=args.string_dedup)

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
