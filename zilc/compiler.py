"""
Main ZIL Compiler.

Coordinates lexing, parsing, code generation, and assembly.
"""

import sys
from typing import List, Optional
from pathlib import Path

from .lexer import Lexer
from .parser import Parser
from .parser.macro_expander import MacroExpander
from .codegen.codegen_improved import ImprovedCodeGenerator
from .zmachine import ZAssembler, ObjectTable, Dictionary
from .zmachine.object_table import ByteValue


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
        self.warnings: List[str] = []  # Compilation warnings

    def log(self, message: str):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[zilc] {message}", file=sys.stderr)

    def warn(self, code: str, message: str):
        """Add a compilation warning with a code."""
        warning = f"{code}: {message}"
        self.warnings.append(warning)
        if self.verbose:
            print(f"[zilc] Warning: {warning}", file=sys.stderr)

    def get_warnings(self) -> List[str]:
        """Get all warnings generated during compilation."""
        return self.warnings.copy()

    def _check_vocab_word_apostrophe(self, word: str, prop_type: str, obj_name: str):
        """Warn if a vocab word contains an apostrophe."""
        if "'" in word:
            self.warn("MDL0429", f"{prop_type} word '{word}' in {obj_name} contains apostrophe")

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

        # Extract SET and SETG directives to track compile-time values
        # <SET VARNAME value> or <SETG VARNAME value>
        # Handles: integers, T, <>, and character literals (!\X)
        def extract_set_or_setg(match):
            var_name = match.group(1)
            var_value = match.group(2) or ''
            if var_value.isdigit():
                self.compile_globals[var_name] = int(var_value)
            elif var_value == 'T':
                self.compile_globals[var_name] = True
            elif var_value == '<>':
                self.compile_globals[var_name] = False
            elif var_value.startswith('!\\') and len(var_value) == 3:
                # Character literal: !\X -> the character X
                self.compile_globals[var_name] = var_value[2]
            self.log(f"  Global: {var_name} = {self.compile_globals.get(var_name)}")
            return match.group(0)  # Keep the SET/SETG in source

        # Handle SETG
        setg_pattern = r'<\s*SETG\s+([A-Z0-9\-?]+)\s+(\d+|T|<>|!\\.)?\s*>'
        source = re.sub(setg_pattern, extract_set_or_setg, source, flags=re.IGNORECASE)

        # Handle SET (compile-time settings like REDEFINE)
        set_pattern = r'<\s*SET\s+([A-Z0-9\-?]+)\s+(\d+|T|<>|!\\.)?\s*>'
        source = re.sub(set_pattern, extract_set_or_setg, source, flags=re.IGNORECASE)

        # First pass: Extract COMPILATION-FLAG directives
        # <COMPILATION-FLAG FLAGNAME <T>> or <COMPILATION-FLAG FLAGNAME T>
        # Supports: <T>, <TRUE>, <>, T, TRUE, <> (bare or in angle brackets)
        flag_pattern = r'<\s*COMPILATION-FLAG\s+(\w+)\s+(?:<([^>]*)>|(\w+))\s*>'

        def extract_flag(match):
            flag_name = match.group(1)
            # Value could be in group 2 (angle brackets) or group 3 (bare atom)
            flag_value = (match.group(2) or match.group(3) or '').strip()
            # <T> or <TRUE> or T means true, <> or <FALSE> or empty means false
            self.compilation_flags[flag_name] = flag_value.upper() in ('T', 'TRUE')
            self.log(f"  Flag: {flag_name} = {self.compilation_flags[flag_name]}")
            return ''  # Remove the directive from source

        source = re.sub(flag_pattern, extract_flag, source, flags=re.IGNORECASE)

        # Extract SUPPRESS-WARNINGS? directives
        # <SUPPRESS-WARNINGS? "ZIL0204"> - suppress specific warning
        # <SUPPRESS-WARNINGS? ALL> - suppress all warnings
        # <SUPPRESS-WARNINGS? NONE> - unsuppress all warnings
        self.suppressed_warnings = set()
        self.suppress_all_warnings = False
        suppress_pattern = r'<\s*SUPPRESS-WARNINGS\?\s+(?:"([^"]+)"|(ALL|NONE))\s*>'

        def extract_suppress(match):
            warning_code = match.group(1)  # Quoted code like "ZIL0204"
            keyword = match.group(2)  # ALL or NONE
            if keyword:
                if keyword.upper() == 'ALL':
                    self.suppress_all_warnings = True
                    self.log("  Suppressing all warnings")
                elif keyword.upper() == 'NONE':
                    self.suppress_all_warnings = False
                    self.suppressed_warnings.clear()
                    self.log("  Unsuppressing all warnings")
            elif warning_code:
                self.suppressed_warnings.add(warning_code)
                self.log(f"  Suppressing warning: {warning_code}")
            return ''  # Remove the directive from source

        source = re.sub(suppress_pattern, extract_suppress, source, flags=re.IGNORECASE)

        # Extract WARN-AS-ERROR? directive
        # <WARN-AS-ERROR? T> - treat warnings as errors
        self.warn_as_error = False
        warn_error_pattern = r'<\s*WARN-AS-ERROR\?\s+(T|<>)\s*>'

        def extract_warn_error(match):
            value = match.group(1)
            self.warn_as_error = value.upper() == 'T'
            self.log(f"  Warn as error: {self.warn_as_error}")
            return ''  # Remove the directive from source

        source = re.sub(warn_error_pattern, extract_warn_error, source, flags=re.IGNORECASE)

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

        # Strip any remaining %<...> forms (DEBUG-CODE, etc.) that we can't evaluate
        source = self._strip_compile_forms(source)

        # Sixth pass: Strip #DECL type declarations (MDL feature not needed for compilation)
        source = self._strip_decl(source)

        # Seventh pass: Process #SPLICE directives (MDL splicing)
        source = self._process_splice(source)

        # Eighth pass: Skip MDL macro definitions (DEFMAC, DEFINE) that we can't process
        source = self._skip_mdl_macros(source)

        # Seventh pass: If lax_brackets enabled, remove extraneous > brackets
        if self.lax_brackets:
            source = self._fix_lax_brackets(source)

        return source

    def _strip_decl(self, source: str) -> str:
        """
        Strip #DECL type declarations.

        #DECL is an MDL type annotation feature used by ZILF for type checking
        but not needed for Z-machine compilation. Format:
            #DECL ((VAR) TYPE ...)

        We remove entire #DECL blocks.
        """
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for #DECL
            match = re.search(r'#DECL\s*\(', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            # Find the matching ) for this #DECL (
            start = pos + match.start() + len('#DECL')
            # Skip whitespace to find the (
            while start < len(source) and source[start] in ' \t\n':
                start += 1

            if start < len(source) and source[start] == '(':
                # Find matching )
                depth = 1
                end = start + 1
                while end < len(source) and depth > 0:
                    if source[end] == '(':
                        depth += 1
                    elif source[end] == ')':
                        depth -= 1
                    end += 1
                pos = end
            else:
                # No opening paren found, skip just the #DECL
                result.append('#DECL')
                pos = pos + match.start() + len('#DECL')

        return ''.join(result)

    def _process_splice(self, source: str) -> str:
        """
        Process #SPLICE directives.

        #SPLICE is used in MDL/ZILF for splicing expressions into lists.
        - #SPLICE () - splices nothing (returns empty string)
        - #SPLICE (expr1 expr2 ...) - splices the expressions without surrounding parens

        Common usage in ZILF:
        <VERSION? (ZIP ...) (ELSE #SPLICE ())>  - include nothing in ELSE case

        Also handles: #SPLICE <expr> for single expressions
        """
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for #SPLICE
            match = re.search(r'#SPLICE\s*', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            splice_start = pos + match.start()
            after_splice = splice_start + match.end() - match.start()

            # Check what follows #SPLICE
            if after_splice < len(source):
                next_char = source[after_splice]

                if next_char == '(':
                    # #SPLICE (...) - extract content of parens
                    depth = 1
                    content_start = after_splice + 1
                    end = content_start

                    while end < len(source) and depth > 0:
                        if source[end] == '(':
                            depth += 1
                        elif source[end] == ')':
                            depth -= 1
                        end += 1

                    if depth == 0:
                        # Extract content (without parens)
                        content = source[content_start:end-1].strip()
                        # If empty, splice nothing; otherwise splice the content
                        result.append(content)
                        pos = end
                    else:
                        # Unbalanced - skip the #SPLICE and continue
                        result.append('#SPLICE')
                        pos = after_splice

                elif next_char == '<':
                    # #SPLICE <expr> - extract the angle-bracket form
                    content, end = self._extract_balanced_content(source, after_splice)
                    if content:
                        # Splice the form directly
                        result.append(content)
                        pos = end
                    else:
                        result.append('#SPLICE')
                        pos = after_splice
                else:
                    # Unknown format - keep as is
                    result.append('#SPLICE')
                    pos = after_splice
            else:
                # #SPLICE at end of file
                result.append('#SPLICE')
                pos = after_splice

        return ''.join(result)

    def _skip_mdl_macros(self, source: str) -> str:
        """
        Skip MDL compile-time definitions that we can't process.

        DEFMAC macros are now supported with quasiquote expansion, so we keep them.
        DEFINE forms are compile-time functions that we skip.

        Note: Quasiquote (`) and unquote (~, ~!) are now supported in DEFMAC
        macro expansion.
        """
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Only skip <DEFINE (not DEFMAC - we now support those)
            match = re.search(r'<\s*DEFINE\s+', source[pos:], re.IGNORECASE)
            if not match:
                result.append(source[pos:])
                break

            # Add text before match
            result.append(source[pos:pos + match.start()])

            # Find the matching > for this <DEFINE
            start = pos + match.start()
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Skip the DEFINE definition entirely
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
        Properly handles strings and character literals - doesn't count <> inside them.
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
            elif ch == '!':
                # Character literal: !\X or !<char> - skip the next character(s)
                # This handles !\> (literal >) which shouldn't close brackets
                pos += 1
                if pos < len(source) and source[pos] == '\\':
                    pos += 1  # skip \
                    if pos < len(source):
                        pos += 1  # skip the escaped char
                elif pos < len(source):
                    pos += 1  # skip any char after !
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

    def _strip_compile_forms(self, source: str) -> str:
        """
        Strip any remaining %<...> compile-time forms that we couldn't evaluate.
        These are forms like %<DEBUG-CODE ...> that the previous passes didn't handle.
        At the top level, we strip them entirely.
        Inside another form, we replace with 0 placeholder.
        """
        import re
        result = []
        pos = 0

        while pos < len(source):
            # Look for %<
            match = re.search(r'%<', source[pos:])
            if not match:
                result.append(source[pos:])
                break

            match_pos = pos + match.start()

            # Add text before match
            result.append(source[pos:match_pos])

            # Figure out if we're inside a form by checking for unclosed < before this position
            # Count angle brackets in what we've collected so far
            collected = ''.join(result)
            angle_depth = collected.count('<') - collected.count('>')

            # Skip the % and start from <
            start = match_pos + 1  # +1 to skip %
            content, end = self._extract_balanced_content(source, start)

            if content:
                # Strip the form - if at top level (angle_depth == 0), remove entirely
                # If inside a form (angle_depth > 0), replace with 0 placeholder
                if angle_depth > 0:
                    result.append('0')
                # else: discard entirely
                pos = end
            else:
                # Can't find matching bracket, keep the %
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

        if test.upper() in ('T', 'ELSE', 'OTHERWISE'):
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

    def _extract_direction_exit(self, value, obj_name_to_num) -> Optional[int]:
        """Extract destination object number from direction exit property.

        Handles formats like:
        - (NORTH TO LIVING-ROOM) -> value is [AtomNode('TO'), AtomNode('LIVING-ROOM')]
        - (NORTH PER EXIT-FUNC) -> value is [AtomNode('PER'), AtomNode('EXIT-FUNC')]
        - (NORTH SORRY "msg") -> value is [AtomNode('SORRY'), StringNode('msg')]

        Returns:
            Object number for TO exits, or special values for other exit types.
            None if the value format is not recognized.
        """
        from .parser.ast_nodes import AtomNode, StringNode

        # Simple object reference (just the room name)
        if isinstance(value, AtomNode):
            dest_name = value.value
            if dest_name not in obj_name_to_num:
                raise ValueError(f"Direction exit references nonexistent object '{dest_name}'")
            return obj_name_to_num[dest_name]

        # List format: [keyword, value] or [keyword, value, ...]
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            keyword = value[0]
            keyword_name = keyword.value if isinstance(keyword, AtomNode) else str(keyword)
            keyword_name = keyword_name.upper()

            if keyword_name == 'TO':
                # (NORTH TO DEST-ROOM) -> get object number
                # Also handles (NORTH TO DEST-ROOM IF CONDITION)
                dest = value[1]
                dest_num = None
                if isinstance(dest, AtomNode):
                    dest_name = dest.value
                    if dest_name not in obj_name_to_num:
                        raise ValueError(f"Direction exit references nonexistent object '{dest_name}'")
                    dest_num = obj_name_to_num[dest_name]
                elif isinstance(dest, str):
                    if dest not in obj_name_to_num:
                        raise ValueError(f"Direction exit references nonexistent object '{dest}'")
                    dest_num = obj_name_to_num[dest]

                # Check for conditional form: (TO DEST IF CONDITION [IS state])
                if len(value) >= 4:
                    if_keyword = value[2]
                    if_name = if_keyword.value if isinstance(if_keyword, AtomNode) else str(if_keyword)
                    if if_name.upper() == 'IF':
                        condition = value[3]
                        cond_name = condition.value if isinstance(condition, AtomNode) else str(condition)
                        # Condition can be:
                        # 1. A global variable (e.g., WON-FLAG)
                        # 2. An object name with "IS state" (e.g., KITCHEN-WINDOW IS OPEN)
                        # Check if it's a valid object or global
                        is_valid = cond_name in obj_name_to_num  # It's an object
                        if hasattr(self, '_current_globals_set') and self._current_globals_set is not None:
                            is_valid = is_valid or cond_name in self._current_globals_set
                        if not is_valid:
                            raise ValueError(f"ZIL0207: Direction exit references nonexistent object or global '{cond_name}'")

                return dest_num

            elif keyword_name == 'PER':
                # (NORTH PER ROUTINE) -> conditional exit
                # For now, return 0 (no exit) - PER exits need routine addresses
                # which are resolved later
                # TODO: Implement PER exit handling with routine address placeholders
                return 0

            elif keyword_name == 'SORRY':
                # (NORTH SORRY "message") -> blocked exit
                # Return 0 (no exit), the message is for display only
                return 0

            elif keyword_name in ('NEXIT', 'UEXIT', 'CEXIT', 'DEXIT', 'FEXIT'):
                # Various exit types from ZILF
                # NEXIT = no exit
                # UEXIT = unconditional exit (with room number)
                # CEXIT = conditional exit
                # DEXIT = door exit
                # FEXIT = function exit
                if keyword_name == 'NEXIT':
                    return 0
                elif keyword_name == 'UEXIT' and len(value) >= 2:
                    dest = value[1]
                    if isinstance(dest, AtomNode):
                        dest_name = dest.value
                        if dest_name not in obj_name_to_num:
                            raise ValueError(f"Direction exit references nonexistent object '{dest_name}'")
                        return obj_name_to_num[dest_name]
                # Other exit types need more complex handling
                return 0

        # Try to interpret as object name directly
        if isinstance(value, str):
            if value not in obj_name_to_num:
                raise ValueError(f"Direction exit references nonexistent object '{value}'")
            return obj_name_to_num[value]

        return None

    def _extract_syntax_find_flags(self, source: str) -> set:
        """Extract flag names used in SYNTAX FIND clauses.

        Scans source for patterns like (FIND FLAGNAME) in SYNTAX definitions.

        Args:
            source: Raw source code text

        Returns:
            Set of flag names used in FIND clauses
        """
        import re
        flags = set()
        # Match (FIND FLAGNAME) patterns - flag names are all caps
        for match in re.finditer(r'\(FIND\s+([A-Z][A-Z0-9_-]*)\)', source, re.IGNORECASE):
            flags.add(match.group(1).upper())
        return flags

    def _build_symbol_tables(self, program, source: str = "") -> dict:
        """Pre-scan program to build flag and property symbol tables.

        This must run before code generation so codegen has access to:
        - Flag bit assignments (TOUCHBIT, FIGHTBIT, etc.)
        - Property number assignments (P?LDESC, P?STRENGTH, etc.)
        - Parser constants (PS?OBJECT, PS?VERB, etc.)

        Returns dict with:
            'flags': dict of flag_name -> bit_number
            'properties': dict of P?name -> property_number
            'parser_constants': dict of PS?name -> bit_value
        """
        from .parser.ast_nodes import AtomNode

        # Standard flag assignments (matching common Infocom conventions)
        # Users can override via CONSTANT declarations
        flags = {}
        next_flag_bit = 0
        max_attributes = 32 if self.version <= 3 else 48

        # Build BIT-SYNONYM alias map: alias -> original
        bit_synonym_map = {}
        for bs in program.bit_synonyms:
            bit_synonym_map[bs.alias] = bs.original
            self.log(f"  BIT-SYNONYM: {bs.alias} -> {bs.original}")

        # Collect all flags from objects and rooms
        all_flags = set()
        for obj in program.objects + program.rooms:
            if 'FLAGS' in obj.properties:
                flags_prop = obj.properties['FLAGS']
                if isinstance(flags_prop, AtomNode):
                    all_flags.add(flags_prop.value)
                elif isinstance(flags_prop, (list, tuple)):
                    for f in flags_prop:
                        if isinstance(f, AtomNode):
                            all_flags.add(f.value)
                        elif isinstance(f, str):
                            all_flags.add(f)

        # Check if flags are already defined as constants
        defined_constants = {c.name: c.value for c in program.constants
                           if hasattr(c, 'value') and isinstance(c.value, int)}

        # Assign bit numbers to flags
        for flag in sorted(all_flags):
            # Resolve alias to original if this is a BIT-SYNONYM alias
            resolved_flag = bit_synonym_map.get(flag, flag)

            if flag in defined_constants:
                flags[flag] = defined_constants[flag]
            elif resolved_flag in flags:
                # Alias of already-assigned flag - use same bit number
                flags[flag] = flags[resolved_flag]
            else:
                if next_flag_bit >= max_attributes:
                    raise ValueError(
                        f"ZIL0404: too many attributes defined "
                        f"(max {max_attributes} in V{self.version}, got {len(all_flags)})"
                    )
                flags[flag] = next_flag_bit
                # Also assign to original if this is an alias
                if resolved_flag != flag:
                    flags[resolved_flag] = next_flag_bit
                next_flag_bit += 1

        # Ensure all BIT-SYNONYM pairs are in flags map with same bit number
        for alias, original in bit_synonym_map.items():
            if original in flags and alias not in flags:
                flags[alias] = flags[original]
            elif alias in flags and original not in flags:
                flags[original] = flags[alias]

        # Standard property assignments (must match _build_object_table prop_map)
        # Only DESC and LDESC are pre-defined; others are assigned dynamically
        properties = {
            'P?DESC': 1,
            'P?LDESC': 2,
        }
        next_prop = 3  # Custom properties start at 3

        # Check if SYNONYM or ADJECTIVE are used in any object - add P? constants
        uses_synonym = any('SYNONYM' in obj.properties for obj in program.objects + program.rooms)
        uses_adjective = any('ADJECTIVE' in obj.properties for obj in program.objects + program.rooms)

        if uses_synonym:
            properties['P?SYNONYM'] = next_prop
            next_prop += 1
        if uses_adjective:
            properties['P?ADJECTIVE'] = next_prop
            next_prop += 1

        # Collect custom properties from PROPDEF declarations
        # Also extract any constants defined in PROPDEF output patterns
        propdef_constants = {}
        for propdef in program.propdefs:
            prop_name = f'P?{propdef.name}'
            if prop_name not in properties:
                properties[prop_name] = next_prop
                next_prop += 1

            # Extract constants from PROPDEF output patterns
            # Pattern structure:
            #   ('CONSTANT', name, ('NUMBER', n)) - constant with fixed value n
            #   ('CONSTANT', name, ('FORM', type, args)) - constant for offset of this element
            #   ('FORM', type, args) - output element that takes space
            for input_pattern, output_pattern in propdef.patterns:
                current_offset = 0
                for elem in output_pattern:
                    elem_type = elem[0]

                    if elem_type == 'CONSTANT':
                        const_name = elem[1]
                        const_val = elem[2] if len(elem) > 2 else None
                        if const_val:
                            if const_val[0] == 'NUMBER':
                                propdef_constants[const_name] = const_val[1]
                            elif const_val[0] == 'FORM':
                                # This constant defines the offset of an embedded FORM
                                # Record current offset as the constant value
                                propdef_constants[const_name] = current_offset
                                # The embedded FORM also contributes to size
                                form_type = const_val[1]
                                if form_type in ('WORD', 'ROOM', 'OBJECT', 'VOC'):
                                    current_offset += 2
                                elif form_type == 'BYTE':
                                    current_offset += 1
                    elif elem_type == 'FORM':
                        # Track size of standalone output elements
                        form_type = elem[1]
                        if form_type in ('WORD', 'ROOM', 'OBJECT', 'VOC'):
                            current_offset += 2
                        elif form_type == 'BYTE':
                            current_offset += 1

        # Handle DIRECTIONS - assign property numbers from MaxProperties down
        # V3: max 31, V4+: max 63
        max_properties = 31 if self.version <= 3 else 63
        low_direction = max_properties + 1  # Will be set if directions exist

        if program.directions:
            # Assign property numbers for each direction (descending from max)
            for i, dir_name in enumerate(program.directions):
                prop_num = max_properties - i
                properties[f'P?{dir_name}'] = prop_num
            low_direction = max_properties - len(program.directions) + 1

        # Check if propdefs exceeded property limit
        # Properties can't overlap with direction properties
        if next_prop > low_direction:
            raise ValueError(
                f"ZIL0404: too many properties defined "
                f"(max {low_direction - 1} in V{self.version}, got {next_prop - 1})"
            )

        # Collect custom properties from object/room definitions
        # Properties like (MYPROP 123) need P?MYPROP constants
        # This must match the order and numbering in compile_string's object building
        # FLAGS, IN, LOC are structural - not actual properties
        # SYNONYM and ADJECTIVE ARE properties if P?SYNONYM/P?ADJECTIVE exist
        reserved_props = {'FLAGS', 'IN', 'LOC'}

        # Build object list in same order as compile_string's object building:
        # 1. Combine objects and rooms
        # 2. Sort by source line number
        # 3. Reverse for object numbering (last defined = lowest number)
        # 4. Then sort by object number for property extraction
        all_items = [(obj.name, obj, False, getattr(obj, 'line', 0)) for obj in program.objects]
        all_items.extend([(room.name, room, True, getattr(room, 'line', 0)) for room in program.rooms])
        all_items.sort(key=lambda x: x[3])

        # Assign object numbers (reverse order: last defined = lowest number)
        total_objects = len(all_items)
        obj_name_to_num = {}
        for i, (name, node, is_room, _) in enumerate(all_items):
            obj_num = total_objects - i
            obj_name_to_num[name] = obj_num

        # Sort by object number (same order as extract_properties is called)
        all_items_sorted = sorted(all_items, key=lambda x: obj_name_to_num[x[0]])

        # Now iterate in the same order as object building
        for name, obj, is_room, _ in all_items_sorted:
            for key in obj.properties.keys():
                if key not in reserved_props:
                    prop_name = f'P?{key}'
                    if prop_name not in properties:
                        if next_prop > low_direction:
                            raise ValueError(
                                f"ZIL0404: too many properties defined "
                                f"(max {low_direction - 1} in V{self.version})"
                            )
                        properties[prop_name] = next_prop
                        next_prop += 1

        # Parser part-of-speech constants (matching dictionary flag bits)
        parser_constants = {
            'PS?OBJECT': 0x80,      # Bit 7: noun/object
            'PS?VERB': 0x40,        # Bit 6: verb
            'PS?ADJECTIVE': 0x20,   # Bit 5: adjective
            'PS?DIRECTION': 0x10,   # Bit 4: direction
            'PS?PREPOSITION': 0x08, # Bit 3: preposition
            'PS?BUZZ-WORD': 0x04,   # Bit 2: buzz word
            # P1? constants for first/second part of speech slot
            'P1?OBJECT': 0,
            'P1?VERB': 0,
            'P1?ADJECTIVE': 1,
            'P1?DIRECTION': 2,
            'P1?PREPOSITION': 3,
            # W?* word constants - placeholders, should be dictionary addresses
            # TODO: These need to be resolved to actual dictionary word addresses
            # during assembly when the dictionary is built
            'W?QUOTE': 0,
            'W?THEN': 0,
            'W?THE': 0,
            'W?A': 0,
            'W?AN': 0,
            'W?PERIOD': 0,
            'W?COMMA': 0,
            'W?INTNUM': 0,  # Special token for integers in input
            # Action constants - placeholders
            'ACT?TELL': 0,
            # Global parser table references - placeholders
            'VERBS': 0,
        }

        # Add LOW-DIRECTION constant if directions are defined
        if program.directions:
            parser_constants['LOW-DIRECTION'] = low_direction

        # Add direction name constants (same as property numbers)
        for i, dir_name in enumerate(program.directions):
            parser_constants[dir_name] = max_properties - i

        # Extract flags used in SYNTAX FIND clauses
        syntax_flags = self._extract_syntax_find_flags(source) if source else set()

        # Pre-assign object numbers for code generation
        # This allows object references like ,FOO to be resolved during codegen
        # ZILF numbers objects in reverse definition order (last defined = lowest number)
        # Combine objects and rooms, sort by source line, then reverse
        objects = {}
        all_items = [(obj, getattr(obj, 'line', 0)) for obj in program.objects]
        all_items.extend([(room, getattr(room, 'line', 0)) for room in program.rooms])
        # Sort by line number to get original definition order
        all_items.sort(key=lambda x: x[1])
        # Assign numbers in reverse order (last defined = lowest number)
        total_objects = len(all_items)
        for i, (item, _) in enumerate(all_items):
            # Reverse: first defined (low line) gets high number, last defined gets low number
            objects[item.name] = total_objects - i

        return {
            'flags': flags,
            'properties': properties,
            'parser_constants': parser_constants,
            'propdef_constants': propdef_constants,  # Constants from PROPDEF output patterns
            'directions': program.directions,  # List of direction names
            'low_direction': low_direction if program.directions else None,
            'max_properties': max_properties,
            'syntax_flags': syntax_flags,  # Flags used in SYNTAX FIND clauses
            'objects': objects,  # Pre-assigned object numbers
        }

    def _build_action_tables(self, program) -> dict:
        """Build ACTIONS and PREACTIONS tables from SYNTAX definitions.

        Creates mappings from action numbers to routine names, which will
        be resolved to routine addresses during code generation.

        Returns dict with:
            'actions': list of (action_num, routine_name) pairs
            'preactions': list of (action_num, routine_name) pairs
            'verb_constants': dict of V?VERB -> action_num
        """
        if not program.syntax:
            return None

        actions = {}  # routine_name -> action_num (first action for each routine)
        preactions = {}  # routine_name -> action_num
        verb_constants = {}  # V?VERB -> action_num
        action_num_to_routine = {}  # action_num -> routine_name (all entries including action names)
        action_num_to_preaction = {}  # action_num -> preaction_routine (can be None for no preaction)

        action_num = 1  # Start from 1 (0 is often reserved)

        unique_verbs = set()  # Track unique verb words for limit checking

        for syntax_def in program.syntax:
            if not syntax_def.routine:
                continue

            # Parse routine field: "V-ACTION" or "V-ACTION PRE-ACTION" or "V-ACTION <> ACTION-NAME"
            # The third part can be an action name that overrides the verb word for V? constant
            parts = syntax_def.routine.split()
            action_routine = parts[0] if parts else None
            preaction_routine = parts[1] if len(parts) > 1 and parts[1] != '<>' else None
            action_name = parts[2] if len(parts) > 2 else None
            # Handle case where preaction is <> and action name is second element
            if len(parts) > 1 and parts[1] == '<>':
                action_name = parts[2] if len(parts) > 2 else None

            # Track unique verb words (first word in pattern) for limit checking
            if syntax_def.pattern:
                verb_word = syntax_def.pattern[0]
                if isinstance(verb_word, str):
                    unique_verbs.add(verb_word.upper())

            # If there's an action name override, it creates a NEW action entry
            # with the same routine but potentially different preaction
            if action_name:
                # Action name override creates a new action entry
                const_name = f'V?{action_name.upper()}'
                if const_name not in verb_constants:
                    # Create new action entry for this action name
                    verb_constants[const_name] = action_num
                    # Store the routine for this action number (same routine, new action number)
                    action_num_to_routine[action_num] = action_routine
                    # The preaction is 0 since action name override uses <> or no preaction
                    action_num_to_preaction[action_num] = None
                    action_num += 1

            if action_routine and action_routine not in actions:
                actions[action_routine] = action_num
                action_num_to_routine[action_num] = action_routine
                # Store first preaction for this action (may be None)
                action_num_to_preaction[action_num] = preaction_routine

                # Create V?VERB constant from verb pattern
                if syntax_def.pattern:
                    verb_word = syntax_def.pattern[0]
                    if isinstance(verb_word, str):
                        const_name = f'V?{verb_word.upper()}'
                        if const_name not in verb_constants:
                            verb_constants[const_name] = action_num

                # Create ACT?ACTION constant from action routine name
                # E.g., V-WALK -> ACT?WALK, V-FIND -> ACT?FIND
                if action_routine.startswith('V-'):
                    act_const_name = f'ACT?{action_routine[2:].upper()}'
                    if act_const_name not in verb_constants:
                        verb_constants[act_const_name] = action_num

                action_num += 1

            if preaction_routine and preaction_routine not in preactions:
                # Preactions share action numbers with their main action
                if action_routine in actions:
                    preactions[preaction_routine] = actions[action_routine]

        # Collect prepositions from SYNTAX patterns
        # Prepositions are non-verb words that appear in syntax patterns
        # They can be BEFORE the first OBJECT (e.g., LOOK THROUGH OBJECT)
        # or BETWEEN OBJECT slots (e.g., PUT OBJECT IN OBJECT)
        prepositions = {}  # word -> PR? number
        prep_num = 1  # Start from 1

        for syntax_def in program.syntax:
            if not syntax_def.pattern:
                continue

            # Find prepositions: all words except the verb (first word) and OBJECT
            # e.g., ["LOOK", "THROUGH", "OBJECT"] -> "THROUGH" is a preposition
            # e.g., ["PUT", "OBJECT", "IN", "OBJECT"] -> "IN" is a preposition
            # e.g., ["PICK", "UP", "OBJECT", "WITH", "OBJECT"] -> "UP" and "WITH" are prepositions
            first_word = True
            for word in syntax_def.pattern:
                if not isinstance(word, str):
                    continue
                word_upper = word.upper()
                if first_word:
                    # Skip the verb (first word)
                    first_word = False
                    continue
                if word_upper not in ('=', 'OBJECT'):
                    # This is a preposition (or particle, treated the same)
                    if word_upper not in prepositions:
                        prepositions[word_upper] = prep_num
                        prep_num += 1

        # Add PR? constants to verb_constants
        for prep_word, prep_number in prepositions.items():
            const_name = f'PR?{prep_word}'
            verb_constants[const_name] = prep_number

        # Check verb/action limits for old parser (limit 255)
        # NEW-PARSER? removes this limit
        new_parser = self.compile_globals.get('NEW-PARSER?', False)
        if not new_parser:
            # Count unique verbs (unique verb words in SYNTAX definitions)
            verb_count = len(unique_verbs)
            if verb_count > 255:
                raise SyntaxError(f"MDL0426: Too many verbs ({verb_count}) - old parser only allows 255 verbs. Use NEW-PARSER? for more.")

            # Count unique actions
            action_count = len(actions)
            if action_count > 255:
                raise SyntaxError(f"MDL0426: Too many actions ({action_count}) - old parser only allows 255 actions. Use NEW-PARSER? for more.")

        # Store for later use during code generation
        self._action_table = {
            'actions': [(num, name) for name, num in sorted(actions.items(), key=lambda x: x[1])],
            'preactions': [(num, name) for name, num in sorted(preactions.items(), key=lambda x: x[1])],
            'verb_constants': verb_constants,
            'action_to_routine': {v: k for k, v in actions.items()},
            'prepositions': prepositions,  # word -> number mapping
            # New mappings for action name overrides - maps action_num to routine/preaction
            'action_num_to_routine': action_num_to_routine,  # action_num -> routine_name
            'action_num_to_preaction': action_num_to_preaction,  # action_num -> preaction_routine (or None)
        }

        return self._action_table

    def compile_string(self, source: str, filename: str = "<input>") -> bytes:
        """
        Compile ZIL source code to Z-machine bytecode.

        Args:
            source: ZIL source code as string
            filename: Filename for error messages

        Returns:
            Z-machine story file as bytes
        """
        # Clear warnings from any previous compilation
        self.warnings = []

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

        # Build symbol tables (flags, properties, parser constants)
        symbol_tables = self._build_symbol_tables(program, source)
        self.log(f"  Pre-scanned {len(symbol_tables['flags'])} flags, {len(symbol_tables['properties'])} properties")

        # Build action tables from SYNTAX definitions
        action_table_info = self._build_action_tables(program)
        if action_table_info:
            self.log(f"  Built ACTIONS table with {len(action_table_info['actions'])} entries")

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

            # Build abbreviations table (now directly generates non-overlapping abbreviations)
            abbreviations_table = AbbreviationsTable()
            abbreviations_table.analyze_strings(all_strings, max_abbrevs=96)
            self.log(f"  Generated {len(abbreviations_table)} non-overlapping abbreviations")

        # Create string table for deduplication and string operand resolution
        # The string table is always needed for resolving string operand placeholders
        # (e.g., when passing strings to routines), so we always create it
        from .zmachine.string_table import StringTable
        from .zmachine.text_encoding import ZTextEncoder
        # Get CRLF-CHARACTER from compile_globals (defaults to '|')
        crlf_char = self.compile_globals.get('CRLF-CHARACTER', '|')
        # Get PRESERVE-SPACES? from compile_globals (defaults to False)
        preserve_spaces = self.compile_globals.get('PRESERVE-SPACES?', False)
        text_encoder = ZTextEncoder(self.version, abbreviations_table=abbreviations_table,
                                    crlf_character=crlf_char, preserve_spaces=preserve_spaces)
        string_table = StringTable(text_encoder, version=self.version)
        if self.enable_string_dedup:
            self.log("String table deduplication enabled")

        # Code generation
        # Pass abbreviations_table to enable string compression.
        # The abbreviation indices (Z-chars 1-3 + index) are stable after analyze_strings().
        # The assembler positions the actual abbreviation strings later.
        self.log("Generating code...")
        codegen = ImprovedCodeGenerator(self.version, abbreviations_table=abbreviations_table,
                                       string_table=string_table,
                                       action_table=action_table_info,
                                       symbol_tables=symbol_tables,
                                       compiler=self)
        routines_code = codegen.generate(program)
        self.log(f"  {len(routines_code)} bytes of routines")

        # Get routine call fixups for address resolution
        routine_fixups = codegen.get_routine_fixups()
        if routine_fixups:
            self.log(f"  {len(routine_fixups)} routine call fixups")

        # Get table routine fixups (for ACTIONS table, etc.)
        table_routine_fixups = codegen.get_table_routine_fixups()
        if table_routine_fixups:
            self.log(f"  {len(table_routine_fixups)} table routine fixups")

        # Report missing routines
        missing_routines = codegen.get_missing_routines()
        if missing_routines:
            self.log(f"  WARNING: {len(missing_routines)} missing routines (will use null address):")
            for routine_name in sorted(missing_routines):
                self.log(f"    - {routine_name}")

        # Report codegen warnings and add to compiler warnings
        codegen_warnings = codegen.get_warnings()
        if codegen_warnings:
            self.log(f"  {len(codegen_warnings)} code generation warnings (see stderr)")
            self.warnings.extend(codegen_warnings)

        # Check for unused flags (ZIL0211 warning)
        unused_flags = codegen.defined_flags - codegen.used_flags
        for flag_name in sorted(unused_flags):
            self.warn("ZIL0211", f"flag '{flag_name}' is never used in code")

        # Check for unused properties (ZIL0212 warning)
        unused_properties = codegen.defined_properties - codegen.used_properties
        for prop_name in sorted(unused_properties):
            # Convert P?MYPROP to user-friendly property name
            display_name = prop_name[2:] if prop_name.startswith('P?') else prop_name
            self.warn("ZIL0212", f"property '{display_name}' is never used in code")

        # Get table data and offsets
        table_data = codegen.get_table_data() if codegen.tables else b''
        table_offsets = codegen.get_table_offsets() if codegen.tables else {}
        if table_data:
            self.log(f"  {len(codegen.tables)} tables ({len(table_data)} bytes)")

        # Build globals data with initial values
        globals_data = codegen.build_globals_data()
        if codegen.global_values:
            self.log(f"  {len(codegen.global_values)} globals with initial values")

        if string_table is not None:
            self.log(f"  String table: {len(string_table)} unique strings")

        # Build dictionary first to get word offsets for SYNONYM properties
        self.log("Building dictionary vocabulary...")
        dictionary = Dictionary(self.version)

        # Add BUZZ words
        if program.buzz_words:
            dictionary.add_words(program.buzz_words, 'buzz')

        # Add standalone SYNONYM words (excluding removed ones)
        if program.synonym_words:
            # Filter out words that were removed via REMOVE-SYNONYM
            removed = set(w.upper() for w in program.removed_synonyms)
            filtered_synonyms = [w for w in program.synonym_words if w.upper() not in removed]
            if filtered_synonyms:
                dictionary.add_words(filtered_synonyms, 'synonym')

        # Extract SYNONYM and ADJECTIVE words from objects/rooms
        obj_num = 1
        for obj in program.objects:
            obj_name = obj.name if hasattr(obj, 'name') else f"object {obj_num}"
            if 'SYNONYM' in obj.properties:
                synonyms = obj.properties['SYNONYM']
                if hasattr(synonyms, '__iter__') and not isinstance(synonyms, str):
                    for syn in synonyms:
                        if hasattr(syn, 'value'):
                            val = syn.value
                            if isinstance(val, (int, float)):
                                val = str(val)
                            self._check_vocab_word_apostrophe(val, 'SYNONYM', obj_name)
                            dictionary.add_synonym(val, obj_num)
                        elif isinstance(syn, str):
                            self._check_vocab_word_apostrophe(syn, 'SYNONYM', obj_name)
                            dictionary.add_synonym(syn, obj_num)
                        elif isinstance(syn, (int, float)):
                            dictionary.add_synonym(str(syn), obj_num)
                elif hasattr(synonyms, 'value'):
                    val = synonyms.value
                    if isinstance(val, (int, float)):
                        val = str(val)
                    self._check_vocab_word_apostrophe(val, 'SYNONYM', obj_name)
                    dictionary.add_synonym(val, obj_num)

            if 'ADJECTIVE' in obj.properties:
                adjectives = obj.properties['ADJECTIVE']
                if hasattr(adjectives, '__iter__') and not isinstance(adjectives, str):
                    for adj in adjectives:
                        if hasattr(adj, 'value'):
                            val = adj.value
                            if isinstance(val, (int, float)):
                                val = str(val)
                            self._check_vocab_word_apostrophe(val, 'ADJECTIVE', obj_name)
                            dictionary.add_adjective(val, obj_num)
                        elif isinstance(adj, str):
                            self._check_vocab_word_apostrophe(adj, 'ADJECTIVE', obj_name)
                            dictionary.add_adjective(adj, obj_num)
                        elif isinstance(adj, (int, float)):
                            dictionary.add_adjective(str(adj), obj_num)
                elif hasattr(adjectives, 'value'):
                    val = adjectives.value
                    if isinstance(val, (int, float)):
                        val = str(val)
                    self._check_vocab_word_apostrophe(val, 'ADJECTIVE', obj_name)
                    dictionary.add_adjective(val, obj_num)
            obj_num += 1

        for room in program.rooms:
            room_name = room.name if hasattr(room, 'name') else f"room {obj_num}"
            if 'SYNONYM' in room.properties:
                synonyms = room.properties['SYNONYM']
                if hasattr(synonyms, '__iter__') and not isinstance(synonyms, str):
                    for syn in synonyms:
                        if hasattr(syn, 'value'):
                            self._check_vocab_word_apostrophe(syn.value, 'SYNONYM', room_name)
                            dictionary.add_synonym(syn.value, obj_num)
                        elif isinstance(syn, str):
                            self._check_vocab_word_apostrophe(syn, 'SYNONYM', room_name)
                            dictionary.add_synonym(syn, obj_num)
                elif hasattr(synonyms, 'value'):
                    self._check_vocab_word_apostrophe(synonyms.value, 'SYNONYM', room_name)
                    dictionary.add_synonym(synonyms.value, obj_num)
            obj_num += 1

        # Add words from SYNTAX definitions
        for syntax_def in program.syntax:
            if syntax_def.pattern:
                for word in syntax_def.pattern:
                    if word.upper() not in ('OBJECT', 'FIND', 'HAVE', 'HELD',
                                             'ON-GROUND', 'IN-ROOM', 'TAKE',
                                             'MANY', 'SEARCH'):
                        if not (isinstance(word, str) and
                                (word.startswith('(') or word.startswith('='))):
                            word_lower = word.lower()
                            word_type = 'verb' if syntax_def.pattern.index(word) == 0 else 'prep'
                            dictionary.add_word(word_lower, word_type)

            # Process verb synonyms from SYNTAX like <SYNTAX TOSS (CHUCK) ...>
            # Verb synonyms are words that share the same dictionary data as the main verb
            if syntax_def.pattern and syntax_def.verb_synonyms:
                main_verb = syntax_def.pattern[0]
                for synonym in syntax_def.verb_synonyms:
                    dictionary.add_verb_synonym(synonym, main_verb)

        # Get word offsets for SYNONYM property fixups
        dict_word_offsets = dictionary.get_word_offsets()
        self.log(f"  Dictionary contains {len(dictionary.words)} words")

        # Get initial vocab placeholders from codegen (will be updated during object table build)
        vocab_placeholders = codegen.get_vocab_placeholders()

        # Add VOC words with their part-of-speech to dictionary
        voc_words = codegen.get_voc_words()
        for word, pos_type in voc_words.items():
            # Map VOC part-of-speech to dictionary word type
            if pos_type == 'ADJ':
                # Adjective - set adjective flags
                dictionary.add_word(word, 'adjective')
            elif pos_type == 'VERB':
                dictionary.add_word(word, 'verb')
            elif pos_type == 'NOUN':
                dictionary.add_word(word, 'noun')
            elif pos_type == 'PREP':
                dictionary.add_word(word, 'preposition')
            elif pos_type == 'DIR':
                dictionary.add_word(word, 'direction')
            elif pos_type == 'BUZZ':
                dictionary.add_word(word, 'buzz')
            elif pos_type is None:
                # No part-of-speech specified - add with no flags
                dictionary.add_word(word, 'unknown')
            else:
                # Unknown part-of-speech - add with no flags
                dictionary.add_word(word, 'unknown')

        # Rebuild word offsets after adding VOC words
        dict_word_offsets = dictionary.get_word_offsets()
        self.log(f"  Dictionary contains {len(dictionary.words)} words (after VOC)")

        # Build object table with proper properties
        self.log("Building object table...")
        obj_table = ObjectTable(self.version, text_encoder=codegen.encoder)

        # Track flag bit assignments - auto-assign if not defined as constants
        flag_bit_map = {}  # flag name -> bit number
        next_flag_bit = 0
        max_attributes = 32 if self.version <= 3 else 48

        # Build BIT-SYNONYM alias map: alias -> original
        bit_synonym_map = {}
        for bs in program.bit_synonyms:
            bit_synonym_map[bs.alias] = bs.original

        # Helper to convert FLAGS to attribute bitmask
        def flags_to_attributes(flags):
            """Convert FLAGS list to attribute bitmask."""
            nonlocal next_flag_bit
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
                # Resolve alias to original if this is a BIT-SYNONYM alias
                resolved_flag = bit_synonym_map.get(flag, flag)

                # Try to get flag number from constants first
                if flag in codegen.constants:
                    bit_num = codegen.constants[flag]
                    attr_mask |= (1 << (31 - bit_num)) if self.version <= 3 else (1 << (47 - bit_num))
                elif resolved_flag in codegen.constants:
                    # Original flag is in constants - use its bit number
                    bit_num = codegen.constants[resolved_flag]
                    attr_mask |= (1 << (31 - bit_num)) if self.version <= 3 else (1 << (47 - bit_num))
                elif flag in flag_bit_map:
                    # Already auto-assigned
                    bit_num = flag_bit_map[flag]
                    attr_mask |= (1 << (31 - bit_num)) if self.version <= 3 else (1 << (47 - bit_num))
                elif resolved_flag in flag_bit_map:
                    # Original flag already assigned - use same bit
                    bit_num = flag_bit_map[resolved_flag]
                    flag_bit_map[flag] = bit_num
                    attr_mask |= (1 << (31 - bit_num)) if self.version <= 3 else (1 << (47 - bit_num))
                else:
                    # Auto-assign new bit number
                    if next_flag_bit < max_attributes:
                        flag_bit_map[flag] = next_flag_bit
                        # Also map original if this is an alias
                        if resolved_flag != flag:
                            flag_bit_map[resolved_flag] = next_flag_bit
                        self.log(f"  Auto-assigned FLAG {flag} -> bit {next_flag_bit}")
                        attr_mask |= (1 << (31 - next_flag_bit)) if self.version <= 3 else (1 << (47 - next_flag_bit))
                        next_flag_bit += 1
                    else:
                        self.log(f"  Warning: Too many flags, ignoring {flag}")
            return attr_mask

        # Build property mapping from PROPDEF declarations
        prop_map = {
            'DESC': 1,    # Standard property always #1
            'LDESC': 2,   # Standard property always #2
        }
        next_prop_num = 3

        # Handle DIRECTIONS - assign property numbers from MaxProperties down
        # V3: max 31, V4+: max 63
        max_properties = 31 if self.version <= 3 else 63
        low_direction = max_properties + 1  # Will be set if directions exist

        if program.directions:
            # Assign property numbers for each direction (descending from max)
            for i, dir_name in enumerate(program.directions):
                prop_num = max_properties - i
                prop_map[dir_name] = prop_num
                self.log(f"  Direction {dir_name} -> property #{prop_num}")
            low_direction = max_properties - len(program.directions) + 1
            self.log(f"  LOW-DIRECTION = {low_direction}")

        # Check if SYNONYM or ADJECTIVE are used - add to prop_map
        uses_synonym = any('SYNONYM' in obj.properties for obj in program.objects + program.rooms)
        uses_adjective = any('ADJECTIVE' in obj.properties for obj in program.objects + program.rooms)

        if uses_synonym:
            prop_map['SYNONYM'] = next_prop_num
            next_prop_num += 1
        if uses_adjective:
            prop_map['ADJECTIVE'] = next_prop_num
            next_prop_num += 1

        # Add user-defined properties from PROPDEF
        for propdef in program.propdefs:
            if propdef.name not in prop_map:
                prop_map[propdef.name] = next_prop_num
                next_prop_num += 1
                self.log(f"  PROPDEF {propdef.name} -> property #{prop_map[propdef.name]}")

        # Track dictionary word fixups for object properties
        # Each entry is (word, property_offset) - to be resolved during assembly
        dict_word_fixups = []

        # Build sets for property value validation
        global_names = {g.name for g in program.globals}
        constant_names = {c.name for c in program.constants}
        object_names = {o.name for o in program.objects + program.rooms}

        # Store for direction exit validation (IF CONDITION check)
        self._current_globals_set = global_names

        # Helper to validate property values are compile-time constants
        def validate_property_value(value, obj_name, prop_name):
            """Validate that a property value is a compile-time constant.

            Global variables are not allowed as property values since they
            are not known at compile time.
            """
            from .parser.ast_nodes import AtomNode
            if isinstance(value, AtomNode):
                atom_name = value.value
                # Global variables are not valid property values
                # (but objects and constants are fine)
                if atom_name in global_names and atom_name not in constant_names and atom_name not in object_names:
                    raise ValueError(f"Property '{prop_name}' in object '{obj_name}' references global variable '{atom_name}' - only constants are allowed")
            elif isinstance(value, (list, tuple)):
                # Check all elements in a list
                for v in value:
                    validate_property_value(v, obj_name, prop_name)

        # Build PROPDEF pattern lookup by property name
        propdef_patterns = {}
        for propdef in program.propdefs:
            if propdef.patterns:
                propdef_patterns[propdef.name] = propdef.patterns

        # Helper to match property value against PROPDEF input pattern
        def match_propdef_pattern(prop_values, input_pattern):
            """Try to match property values against a PROPDEF input pattern.

            Returns (captures_list, is_many) where captures_list is a list of
            capture dicts (one per MANY iteration, or single-element list if no MANY).
            Returns (None, False) if no match.
            """
            from .parser.ast_nodes import AtomNode, NumberNode

            captures_list = []
            current_captures = {}
            val_idx = 0
            pat_idx = 0
            in_opt = False
            in_many = False
            many_start_pat_idx = None

            while pat_idx < len(input_pattern):
                elem_type, elem_val, elem_extra = input_pattern[pat_idx]

                if elem_type == 'MODIFIER':
                    if elem_val == 'OPT':
                        in_opt = True
                    elif elem_val == 'MANY':
                        in_many = True
                        many_start_pat_idx = pat_idx + 1
                    pat_idx += 1
                    continue

                if val_idx >= len(prop_values):
                    if in_opt or in_many:
                        # Optional/MANY elements can be missing
                        pat_idx += 1
                        continue
                    return None, False  # No more values but pattern expects more

                val = prop_values[val_idx]

                if elem_type == 'LITERAL':
                    # Must match exactly
                    if isinstance(val, AtomNode):
                        if val.value != elem_val:
                            if in_opt:
                                pat_idx += 1
                                continue
                            return None, False
                    elif isinstance(val, NumberNode):
                        if val.value != elem_val:
                            if in_opt:
                                pat_idx += 1
                                continue
                            return None, False
                    else:
                        if in_opt:
                            pat_idx += 1
                            continue
                        return None, False
                    val_idx += 1

                elif elem_type == 'CAPTURE':
                    var_name = elem_val
                    var_type = elem_extra
                    # Capture the value
                    if isinstance(val, NumberNode):
                        current_captures[var_name] = val.value
                    elif isinstance(val, AtomNode):
                        current_captures[var_name] = val.value
                    else:
                        current_captures[var_name] = val
                    val_idx += 1

                pat_idx += 1

                # Handle MANY repetition
                if in_many and pat_idx >= len(input_pattern):
                    # Save current captures and start new iteration
                    captures_list.append(current_captures)
                    current_captures = {}
                    if val_idx < len(prop_values):
                        # More values to process, loop back to MANY start
                        pat_idx = many_start_pat_idx

            # All pattern elements matched, check if all values consumed
            if val_idx < len(prop_values) and not in_many:
                return None, False

            # Add final captures if not already added (non-MANY case or last MANY iteration)
            if not in_many:
                captures_list.append(current_captures)

            return captures_list, in_many

        # Helper to encode property using PROPDEF output pattern
        def encode_propdef_output(captures_list, output_pattern, obj_name_to_num, is_many=False):
            """Encode property value using PROPDEF output pattern.

            captures_list is a list of capture dicts (one per MANY iteration).
            Returns (bytes, defined_constants) tuple.
            """
            result = bytearray()
            defined_constants = {}  # Constants defined in this encoding
            length_placeholder_pos = None

            # Find MANY marker in output pattern - elements after it are repeated
            many_idx = None
            for i, elem in enumerate(output_pattern):
                if elem[0] == 'MODIFIER' and elem[1] == 'MANY':
                    many_idx = i
                    break

            # Split pattern into pre-MANY and post-MANY parts
            if many_idx is not None:
                pre_many_pattern = output_pattern[:many_idx]
                post_many_pattern = output_pattern[many_idx + 1:]
            else:
                pre_many_pattern = output_pattern
                post_many_pattern = []

            def encode_element(elem, captures):
                """Encode a single output element."""
                nonlocal defined_constants
                elem_type = elem[0]

                if elem_type == 'LENGTH':
                    # Fixed length indicator - skip for now, length is implicit
                    pass

                elif elem_type == 'AUTO_LENGTH':
                    # Auto-calculate length - position to patch later
                    pass

                elif elem_type == 'FORM':
                    form_type = elem[1]
                    form_args = elem[2]

                    if form_type == 'WORD':
                        # Encode as 2-byte word
                        for arg_type, arg_val in form_args:
                            if arg_type == 'VAR':
                                val = captures.get(arg_val, 0)
                                if isinstance(val, int):
                                    result.extend([(val >> 8) & 0xFF, val & 0xFF])
                                else:
                                    result.extend([0, 0])
                            elif arg_type == 'NUMBER':
                                result.extend([(arg_val >> 8) & 0xFF, arg_val & 0xFF])

                    elif form_type == 'BYTE':
                        # Encode as 1-byte
                        for arg_type, arg_val in form_args:
                            if arg_type == 'VAR':
                                val = captures.get(arg_val, 0)
                                if isinstance(val, int):
                                    result.append(val & 0xFF)
                                else:
                                    result.append(0)

                    elif form_type == 'ROOM':
                        # Encode as room number (byte for V3, word for V4+)
                        for arg_type, arg_val in form_args:
                            if arg_type == 'VAR':
                                room_name = captures.get(arg_val, '')
                                room_num = obj_name_to_num.get(room_name, 0)
                                if self.version <= 3:
                                    result.append(room_num & 0xFF)
                                else:
                                    result.extend([(room_num >> 8) & 0xFF, room_num & 0xFF])

                    elif form_type == 'OBJECT':
                        # Encode as object number (word)
                        for arg_type, arg_val in form_args:
                            if arg_type == 'VAR':
                                obj_name = captures.get(arg_val, '')
                                obj_num = obj_name_to_num.get(obj_name, 0)
                                result.extend([(obj_num >> 8) & 0xFF, obj_num & 0xFF])

                    elif form_type == 'VOC':
                        # Encode as vocabulary word (2-byte dictionary address placeholder)
                        for arg_type, arg_val in form_args:
                            if arg_type == 'VAR':
                                word = captures.get(arg_val, '')
                                if isinstance(word, str):
                                    # Use W?* placeholder system (dict: idx -> word)
                                    word_lower = word.lower()
                                    # Find next available index
                                    if vocab_placeholders:
                                        placeholder_idx = max(vocab_placeholders.keys()) + 1
                                    else:
                                        placeholder_idx = 0
                                    vocab_placeholders[placeholder_idx] = word_lower
                                    # Placeholder value that will be fixed up
                                    result.extend([(0xFB00 + placeholder_idx) >> 8,
                                                   (0xFB00 + placeholder_idx) & 0xFF])
                                else:
                                    result.extend([0, 0])

                    elif form_type == 'GLOBAL':
                        # Encode as global variable reference
                        for arg_type, arg_val in form_args:
                            if arg_type == 'VAR':
                                # This would need access to global table
                                result.extend([0, 0])

                elif elem_type == 'CONSTANT':
                    # Define a constant (for later use)
                    const_name = elem[1]
                    const_val = elem[2]
                    if const_val:
                        if const_val[0] == 'NUMBER':
                            defined_constants[const_name] = const_val[1]
                        elif const_val[0] == 'FORM':
                            # Constant offset - calculate based on current position
                            defined_constants[const_name] = len(result)
                            # Also encode the embedded FORM data
                            form_elem = const_val  # ('FORM', type, args)
                            encode_element(form_elem, captures)

            # Encode pre-MANY elements (using first capture set for any variables)
            first_captures = captures_list[0] if captures_list else {}
            for elem in pre_many_pattern:
                if elem[0] != 'MODIFIER':
                    encode_element(elem, first_captures)

            # Encode MANY repeated elements for each capture set
            if post_many_pattern:
                for captures in captures_list:
                    for elem in post_many_pattern:
                        if elem[0] != 'MODIFIER':
                            encode_element(elem, captures)
            elif not pre_many_pattern:
                # No MANY in output, just use first capture set
                for captures in captures_list[:1]:
                    for elem in output_pattern:
                        if elem[0] != 'MODIFIER':
                            encode_element(elem, captures)

            return bytes(result), defined_constants

        # Helper to apply PROPDEF pattern to property value
        def apply_propdef(prop_name, prop_values, obj_name_to_num):
            """Try to apply PROPDEF pattern to encode property value.

            Returns (encoded_bytes, constants) if matched, (None, None) otherwise.
            """
            if prop_name not in propdef_patterns:
                return None, None

            patterns = propdef_patterns[prop_name]
            for input_pattern, output_pattern in patterns:
                # Skip the first element of input_pattern if it's the property name
                # For DIRECTIONS PROPDEF, the first element (e.g., "DIR") is a placeholder
                # for the direction name and should always be skipped
                if input_pattern and input_pattern[0][0] == 'LITERAL':
                    first_elem = input_pattern[0][1]
                    if first_elem == prop_name or prop_name == 'DIRECTIONS':
                        input_pattern = input_pattern[1:]

                captures_list, is_many = match_propdef_pattern(prop_values, input_pattern)
                if captures_list is not None:
                    encoded, constants = encode_propdef_output(captures_list, output_pattern, obj_name_to_num, is_many)
                    return encoded, constants

            return None, None

        # Helper to resolve an atom value (flag, object, or constant name) to its numeric value
        def resolve_atom_value(atom_name):
            """Resolve an atom name to its numeric value.

            Checks in order:
            1. Flag bit assignments (NONLANDBIT, TOUCHBIT, etc.)
            2. Object/room names
            3. Constants

            Returns the numeric value or None if not found.
            """
            # Check if it's a flag name
            if atom_name in flag_bit_map:
                return flag_bit_map[atom_name]
            # Check if it's an object/room name
            if atom_name in obj_name_to_num:
                return obj_name_to_num[atom_name]
            # Check if it's a constant (from constants dict or codegen)
            if atom_name in codegen.constants:
                val = codegen.constants[atom_name]
                if isinstance(val, int):
                    return val
            # Not found
            return None

        # Helper to extract property number and value
        def extract_properties(obj_node, obj_idx):
            """Extract properties from object node."""
            nonlocal next_prop_num  # Allow modification of outer scope variable
            props = {}
            for key, value in obj_node.properties.items():
                # Skip validation for known special properties
                if key not in ['FLAGS', 'IN', 'LOC', 'SYNONYM', 'ADJECTIVE'] + list(program.directions):
                    validate_property_value(value, obj_node.name, key)
                if key == 'SYNONYM' and 'SYNONYM' in prop_map:
                    # Store dictionary word offset placeholder for first synonym
                    prop_num = prop_map['SYNONYM']
                    synonyms = value
                    first_word = None
                    if hasattr(synonyms, '__iter__') and not isinstance(synonyms, str):
                        for syn in synonyms:
                            if hasattr(syn, 'value'):
                                first_word = syn.value
                            elif isinstance(syn, str):
                                first_word = syn
                            break
                    elif hasattr(synonyms, 'value'):
                        first_word = synonyms.value

                    if first_word:
                        word_lower = str(first_word).lower()
                        if word_lower in dict_word_offsets:
                            # Store placeholder: word_offset | 0x8000 (high bit marks as fixup needed)
                            # The assembler will add dictionary base address
                            word_offset = dict_word_offsets[word_lower]
                            props[prop_num] = word_offset | 0x8000  # Mark for fixup
                            dict_word_fixups.append((word_lower, obj_idx, prop_num))
                        else:
                            props[prop_num] = 0  # Word not found
                elif key == 'ADJECTIVE' and 'ADJECTIVE' in prop_map:
                    # Store dictionary word offset placeholder for first adjective
                    prop_num = prop_map['ADJECTIVE']
                    adjectives = value
                    first_word = None
                    if hasattr(adjectives, '__iter__') and not isinstance(adjectives, str):
                        for adj in adjectives:
                            if hasattr(adj, 'value'):
                                first_word = adj.value
                            elif isinstance(adj, str):
                                first_word = adj
                            break
                    elif hasattr(adjectives, 'value'):
                        first_word = adjectives.value

                    if first_word:
                        word_lower = str(first_word).lower()
                        if word_lower in dict_word_offsets:
                            word_offset = dict_word_offsets[word_lower]
                            props[prop_num] = 0xFE00 | (word_offset & 0xFF)
                            dict_word_fixups.append((word_lower, obj_idx, prop_num))
                        else:
                            props[prop_num] = 0
                elif key in prop_map:
                    prop_num = prop_map[key]
                    # Check if this is a direction property (e.g., NORTH, SOUTH, etc.)
                    if key in program.directions:
                        # Check if there's a PROPDEF DIRECTIONS pattern to use
                        if 'DIRECTIONS' in propdef_patterns and isinstance(value, list):
                            # Apply DIRECTIONS PROPDEF pattern to this direction property
                            encoded, constants = apply_propdef('DIRECTIONS', value, obj_name_to_num)
                            if encoded is not None:
                                props[prop_num] = encoded
                                for const_name, const_val in constants.items():
                                    codegen.constants[const_name] = const_val
                            else:
                                # Pattern didn't match, use default handling
                                exit_value = self._extract_direction_exit(value, obj_name_to_num)
                                if exit_value is not None:
                                    props[prop_num] = ByteValue(exit_value)
                        else:
                            # Default: extract destination from (DIR TO DEST) or (DIR PER ROUTINE)
                            exit_value = self._extract_direction_exit(value, obj_name_to_num)
                            if exit_value is not None:
                                # Wrap in ByteValue so it's stored as single byte (for GETB access)
                                props[prop_num] = ByteValue(exit_value)
                    # Check if this property has a PROPDEF pattern
                    elif isinstance(value, list) and key in propdef_patterns:
                        # Try to apply PROPDEF pattern matching
                        encoded, constants = apply_propdef(key, value, obj_name_to_num)
                        if encoded is not None:
                            props[prop_num] = encoded
                            # Store any constants defined by the pattern
                            for const_name, const_val in constants.items():
                                codegen.constants[const_name] = const_val
                        else:
                            # Pattern didn't match, fall through to default handling
                            props[prop_num] = value
                    # Extract value from AST node
                    elif hasattr(value, 'value'):
                        # Try to resolve atom values (flags, objects, constants)
                        str_val = value.value
                        resolved = resolve_atom_value(str_val) if isinstance(str_val, str) else None
                        props[prop_num] = resolved if resolved is not None else str_val
                    else:
                        props[prop_num] = value
                elif key not in ['FLAGS', 'IN', 'LOC']:
                    # Unknown property, assign next number
                    if key not in prop_map:
                        prop_map[key] = next_prop_num
                        self.log(f"  Auto-assigned {key} -> property #{next_prop_num}")
                        next_prop_num += 1
                    prop_num = prop_map[key]
                    if hasattr(value, 'value'):
                        # Try to resolve atom values (flags, objects, constants)
                        str_val = value.value
                        resolved = resolve_atom_value(str_val) if isinstance(str_val, str) else None
                        props[prop_num] = resolved if resolved is not None else str_val
                    else:
                        props[prop_num] = value

            return props

        # Build object name -> number mapping first (objects are 1-indexed)
        # Rooms and objects share the same number space
        # ZILF numbers objects in reverse definition order (last defined = lowest number)
        # Combine objects and rooms, sort by source line to get original interleaved order
        all_items = [(obj.name, obj, False, getattr(obj, 'line', 0)) for obj in program.objects]
        all_items.extend([(room.name, room, True, getattr(room, 'line', 0)) for room in program.rooms])
        # Sort by line number to get original definition order
        all_items.sort(key=lambda x: x[3])

        all_objects = []  # List of (name, node, is_room)
        obj_name_to_num = {}
        total_objects = len(all_items)

        for i, (name, node, is_room, _) in enumerate(all_items):
            # Reverse: first defined (low line) gets high number, last defined gets low number
            obj_num = total_objects - i
            obj_name_to_num[name] = obj_num
            all_objects.append((name, node, is_room))

        self.log(f"  {len(all_objects)} objects/rooms total")

        # Build set of routine names for validation
        routine_names = {r.name for r in program.routines}

        # Helper to get object number from IN property value
        def get_parent_num(in_value, obj_name):
            """Extract parent object number from IN property value."""
            from .parser.ast_nodes import AtomNode, FormNode
            if in_value is None:
                return 0
            # Handle AtomNode
            if isinstance(in_value, AtomNode):
                parent_name = in_value.value
            elif isinstance(in_value, str):
                parent_name = in_value
            elif isinstance(in_value, list) and len(in_value) > 0:
                # Take first element if it's a list
                first = in_value[0]
                if isinstance(first, AtomNode):
                    parent_name = first.value
                elif isinstance(first, str):
                    parent_name = first
                else:
                    return 0
            else:
                return 0

            # Check if parent_name is a routine (not allowed as container)
            if parent_name in routine_names:
                raise ValueError(
                    f"Object '{obj_name}' has IN property referencing routine "
                    f"'{parent_name}' - only objects/rooms can contain other objects"
                )

            # Look up parent by name
            return obj_name_to_num.get(parent_name, 0)

        # Build parent relationships
        parent_of = {}  # obj_num -> parent_num
        for name, node, is_room in all_objects:
            obj_num = obj_name_to_num[name]
            # Check for IN or LOC property
            in_value = node.properties.get('IN') or node.properties.get('LOC')
            parent_num = get_parent_num(in_value, name)
            parent_of[obj_num] = parent_num

        # Build child lists (parent -> list of children in order)
        # ZILF inserts new children at position 1 (after first child), not at end
        children_of = {}  # parent_num -> [child_nums...]
        for obj_num, parent_num in parent_of.items():
            if parent_num not in children_of:
                children_of[parent_num] = []
            # Insert at position 1 to match ZILF's sibling ordering
            if len(children_of[parent_num]) > 0:
                children_of[parent_num].insert(1, obj_num)
            else:
                children_of[parent_num].append(obj_num)

        # Build sibling chains and first-child pointers
        sibling_of = {}  # obj_num -> next_sibling_num
        child_of = {}    # parent_num -> first_child_num

        for parent_num, child_list in children_of.items():
            if child_list:
                # First child
                child_of[parent_num] = child_list[0]
                # Build sibling chain
                for i in range(len(child_list) - 1):
                    sibling_of[child_list[i]] = child_list[i + 1]
                # Last child has no sibling
                sibling_of[child_list[-1]] = 0

        # Add objects with properties and tree structure
        # Sort by object number so objects are added in the correct order for the table
        sorted_objects = sorted(all_objects, key=lambda x: obj_name_to_num[x[0]])
        for obj_idx, (name, node, is_room) in enumerate(sorted_objects):
            obj_num = obj_name_to_num[name]
            attributes = flags_to_attributes(node.properties.get('FLAGS', []))
            properties = extract_properties(node, obj_idx)
            obj_table.add_object(
                name=name,
                parent=parent_of.get(obj_num, 0),
                sibling=sibling_of.get(obj_num, 0),
                child=child_of.get(obj_num, 0),
                attributes=attributes,
                properties=properties
            )

        objects_data = obj_table.build()

        # Register flag bit assignments with codegen for FSET/FCLEAR/FSET? opcodes
        for flag_name, bit_num in flag_bit_map.items():
            codegen.constants[flag_name] = bit_num

        # Register object numbers with codegen for object references in code
        for obj_name, obj_num in obj_name_to_num.items():
            codegen.objects[obj_name] = obj_num

        self.log(f"  Registered {len(flag_bit_map)} flags, {len(obj_name_to_num)} objects")

        # Now build vocab_fixups after object table (PROPDEF may have added vocab placeholders)
        vocab_fixups = []  # List of (placeholder_idx, word_offset)
        missing_vocab_words = []
        for placeholder_idx, word in vocab_placeholders.items():
            if word in dict_word_offsets:
                vocab_fixups.append((placeholder_idx, dict_word_offsets[word]))
            else:
                # Word not in dictionary - try to add it
                dictionary.add_word(word, 'buzz')  # PROPDEF VOC uses BUZZ type
                # Re-get offsets to include the new word
                dict_word_offsets = dictionary.get_word_offsets()
                if word in dict_word_offsets:
                    vocab_fixups.append((placeholder_idx, dict_word_offsets[word]))
                else:
                    missing_vocab_words.append(word)
                    vocab_fixups.append((placeholder_idx, 0))  # Default to 0

        if vocab_placeholders:
            self.log(f"  {len(vocab_placeholders)} vocabulary word references (W?*)")
        if missing_vocab_words:
            self.log(f"  WARNING: {len(missing_vocab_words)} missing vocab words: {missing_vocab_words[:5]}...")

        # Dictionary was already built earlier for SYNONYM property resolution
        # Just build the final dictionary data
        dict_data = dictionary.build()

        # Run optimization passes before assembly
        # Note: AbbreviationOptimizationPass is now run earlier, before code generation
        self.log("Running optimization passes...")
        from .optimization.passes import OptimizationPipeline, StringDeduplicationPass, PropertyOptimizationPass

        compilation_data = {
            'routines_code': routines_code,
            'objects_data': objects_data,
            'dictionary_data': dict_data,
            'abbreviations_table': abbreviations_table,
            'program': program,
            'table_data': table_data,
            'table_offsets': table_offsets
        }

        pipeline = OptimizationPipeline(verbose=self.verbose)
        pipeline.add_pass(StringDeduplicationPass)
        pipeline.add_pass(PropertyOptimizationPass)

        compilation_data = pipeline.run(compilation_data)

        # Extract optimized data (may have been modified by optimization passes)
        routines_code = compilation_data['routines_code']
        objects_data = compilation_data['objects_data']
        dict_data = compilation_data['dictionary_data']
        abbreviations_table = compilation_data.get('abbreviations_table', abbreviations_table)
        table_data = compilation_data.get('table_data', b'')
        table_offsets = compilation_data.get('table_offsets', {})

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
            crlf_char = self.compile_globals.get('CRLF-CHARACTER', '|')
            preserve_spaces = self.compile_globals.get('PRESERVE-SPACES?', False)
            text_encoder = ZTextEncoder(self.version, crlf_character=crlf_char,
                                        preserve_spaces=preserve_spaces)
            abbreviations_table.encode_abbreviations(text_encoder)
            self.log(f"  Encoded {len(abbreviations_table)} optimized abbreviations")

        # Build extension table if needed (V5+)
        extension_table = codegen.build_extension_table()
        if extension_table:
            self.log(f"  Built extension table: {len(extension_table)} bytes")

        # Get string placeholders for resolution
        string_placeholders = codegen.get_string_placeholders()  # For operand format (0xFC)
        tell_string_placeholders = codegen.get_tell_string_placeholders()  # For TELL format (0x8D)
        tell_placeholder_positions = codegen.get_tell_placeholder_positions()  # Exact byte offsets

        # Assemble story file
        self.log("Assembling story file...")
        assembler = ZAssembler(self.version)
        story = assembler.build_story_file(
            routines_code,
            objects_data,
            dict_data,
            globals_data=globals_data,
            abbreviations_table=abbreviations_table,
            string_table=string_table,
            table_data=table_data,
            table_offsets=table_offsets,
            routine_fixups=routine_fixups,
            table_routine_fixups=table_routine_fixups,
            extension_table=extension_table,
            string_placeholders=string_placeholders,
            tell_string_placeholders=tell_string_placeholders,
            tell_placeholder_positions=tell_placeholder_positions,
            vocab_fixups=vocab_fixups
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
