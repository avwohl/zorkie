# ZILF Interpreter Test Infrastructure for Zorkie
# ================================================
#
# Derived from ZILF test suite (GPL-3.0)
# Original: https://foss.heptapod.net/zilf/zilf
# Original file: test/Zilf.Tests/Interpreter/TestHelpers.cs
# Copyright 2010-2023 Tara McGrew
# Adapted for zorkie by automated translation
#
# This file is part of zorkie.
#
# zorkie is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Test infrastructure for MDL/ZIL interpreter tests.

This module provides:
- Context: MDL interpreter context
- ZilObject hierarchy: ZilFix, ZilString, ZilAtom, ZilList, ZilVector, ZilForm, etc.
- eval_and_assert(): Evaluate expression and check result
- eval_and_catch(): Evaluate expression and expect exception
- evaluate(): Evaluate expression and return result
"""

import pytest
import re
from typing import Any, Callable, Optional, Type, List, Tuple
from abc import ABC, abstractmethod


class InterpreterError(Exception):
    """Base exception for interpreter errors."""
    pass


class ArgumentCountError(InterpreterError):
    """Wrong number of arguments."""
    pass


class ArgumentTypeError(InterpreterError):
    """Wrong type of argument."""
    pass


class DeclCheckError(InterpreterError):
    """DECL check failed."""
    pass


class ArgumentDecodingError(InterpreterError):
    """Argument decoding failed."""
    pass


class ZilObject(ABC):
    """Base class for all ZIL objects."""

    @abstractmethod
    def structurally_equals(self, other: 'ZilObject') -> bool:
        """Check if two objects are structurally equal."""
        pass


class ZilFix(ZilObject):
    """ZIL integer (FIX) type."""

    def __init__(self, value: int):
        self.value = value

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilFix):
            return self.value == other.value
        return False

    def __repr__(self):
        return f"ZilFix({self.value})"

    def __eq__(self, other):
        if isinstance(other, ZilFix):
            return self.value == other.value
        return False


class ZilString(ZilObject):
    """ZIL string type."""

    def __init__(self, value: str):
        self.value = value

    @classmethod
    def from_string(cls, s: str) -> 'ZilString':
        return cls(s)

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilString):
            return self.value == other.value
        return False

    def __repr__(self):
        return f'ZilString("{self.value}")'


class ZilAtom(ZilObject):
    """ZIL atom type."""

    _counter = 0  # For generating unique IDs for uninterned atoms

    def __init__(self, name: str, oblist=None, uninterned=False):
        self.name = name
        self.oblist = oblist
        self.uninterned = uninterned
        # Uninterned atoms get a unique ID
        if uninterned:
            ZilAtom._counter += 1
            self._id = ZilAtom._counter
        else:
            self._id = None

    @classmethod
    def parse(cls, name: str, ctx=None) -> 'ZilAtom':
        return cls(name)

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilAtom):
            # Uninterned atoms (created by ATOM builtin) are only equal to themselves
            if self.uninterned or other.uninterned:
                return self is other
            # Normal atoms compare by name
            return self.name == other.name
        return False

    def __repr__(self):
        return f"ZilAtom({self.name})"


class ZilList(ZilObject):
    """ZIL list type."""

    def __init__(self, elements: Optional[list] = None):
        self.elements = elements if elements is not None else []

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilList):
            if len(self.elements) != len(other.elements):
                return False
            return all(
                a.structurally_equals(b)
                for a, b in zip(self.elements, other.elements)
            )
        return False

    def is_empty(self) -> bool:
        return len(self.elements) == 0

    def __repr__(self):
        return f"ZilList({self.elements})"


class ZilVector(ZilObject):
    """ZIL vector type."""

    def __init__(self, *elements):
        self.elements = list(elements)

    def __getitem__(self, index: int) -> ZilObject:
        return self.elements[index]

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilVector):
            if len(self.elements) != len(other.elements):
                return False
            return all(
                a.structurally_equals(b)
                for a, b in zip(self.elements, other.elements)
            )
        return False

    def __repr__(self):
        return f"ZilVector({self.elements})"


class ZilForm(ZilObject):
    """ZIL form (executable expression) type."""

    def __init__(self, elements: Optional[list] = None):
        self.elements = elements if elements is not None else []

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilForm):
            if len(self.elements) != len(other.elements):
                return False
            return all(
                a.structurally_equals(b)
                for a, b in zip(self.elements, other.elements)
            )
        return False

    def __repr__(self):
        return f"ZilForm({self.elements})"


class ZilSegment(ZilObject):
    """ZIL segment type."""

    def __init__(self, form: ZilForm):
        self.form = form

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilSegment):
            return self.form.structurally_equals(other.form)
        return False

    def __repr__(self):
        return f"ZilSegment({self.form})"


class ZilOffset(ZilObject):
    """ZIL offset type for DEFSTRUCT."""

    def __init__(self, index: int, decl: ZilObject, element_type: ZilObject):
        self.index = index
        self.decl = decl
        self.element_type = element_type

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilOffset):
            return (self.index == other.index and
                    self.decl.structurally_equals(other.decl) and
                    self.element_type.structurally_equals(other.element_type))
        return False

    def __repr__(self):
        return f"ZilOffset({self.index}, {self.decl}, {self.element_type})"


class ZilTable(ZilObject):
    """ZIL table type."""

    def __init__(self, elements: Optional[list] = None, flags: int = 0):
        self.elements = elements if elements is not None else []
        self.flags = flags

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilTable):
            if len(self.elements) != len(other.elements):
                return False
            return all(
                a.structurally_equals(b)
                for a, b in zip(self.elements, other.elements)
            )
        return False

    def __repr__(self):
        return f"ZilTable({self.elements})"


class ZilStructuredHash(ZilObject):
    """ZIL structured hash (user-defined structure) type."""

    def __init__(self, type_atom: ZilAtom, primtype, primitive: ZilObject):
        self.type_atom = type_atom
        self.primtype = primtype
        self.primitive = primitive

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilStructuredHash):
            return (self.type_atom.structurally_equals(other.type_atom) and
                    self.primitive.structurally_equals(other.primitive))
        return False

    def __repr__(self):
        return f"ZilStructuredHash({self.type_atom}, {self.primitive})"


class ZilFunction(ZilObject):
    """ZIL function type."""

    def __init__(self, name: str, args: list, body: list):
        self.name = name
        self.args = args
        self.body = body

    def structurally_equals(self, other: ZilObject) -> bool:
        return self is other

    def __repr__(self):
        return f"ZilFunction({self.name})"


class ZilEvalMacro(ZilObject):
    """ZIL macro type."""

    def __init__(self, name: str, args: list, body: list):
        self.name = name
        self.args = args
        self.body = body

    def structurally_equals(self, other: ZilObject) -> bool:
        return self is other

    def __repr__(self):
        return f"ZilEvalMacro({self.name})"


class ObList(ZilObject):
    """ZIL oblist (symbol table) type."""

    def __init__(self, name: str = "ROOT"):
        self.name = name
        self.atoms = {}

    def __getitem__(self, key: str) -> ZilAtom:
        if key not in self.atoms:
            self.atoms[key] = ZilAtom(key, self)
        return self.atoms[key]

    def __setitem__(self, key: str, value: ZilAtom):
        self.atoms[key] = value

    def structurally_equals(self, other: ZilObject) -> bool:
        return self is other

    def __repr__(self):
        return f"ObList({self.name})"


class TableFormat:
    """Table format flags."""
    Pure = 1


class PrimType:
    """Primitive types."""
    VECTOR = "VECTOR"
    LIST = "LIST"
    STRING = "STRING"


class Context:
    """MDL interpreter context."""

    def __init__(self):
        self._globals = {}
        self._locals = {}
        self._local_stack = []  # Stack of local scopes
        self._root_oblist = ObList("ROOT")
        self._package_oblist = ObList("PACKAGE")
        self._true = ZilAtom("T")
        self._false = ZilList([])  # #FALSE () is an empty list
        self._functions = {}  # User-defined functions
        self._macros = {}  # User-defined macros
        self._defstructs = {}  # DEFSTRUCT definitions

    @property
    def TRUE(self) -> ZilAtom:
        return self._true

    @property
    def FALSE(self) -> ZilList:
        return self._false

    @property
    def RootObList(self) -> ObList:
        return self._root_oblist

    @property
    def PackageObList(self) -> ObList:
        return self._package_oblist

    def get_global_val(self, atom: ZilAtom) -> Optional[ZilObject]:
        return self._globals.get(atom.name)

    def set_global_val(self, atom: ZilAtom, value: Optional[ZilObject]):
        if value is None:
            self._globals.pop(atom.name, None)
        else:
            self._globals[atom.name] = value

    def get_local_val(self, atom: ZilAtom) -> Optional[ZilObject]:
        # Check current locals first
        if atom.name in self._locals:
            return self._locals[atom.name]
        # Check stack frames
        for frame in reversed(self._local_stack):
            if atom.name in frame:
                return frame[atom.name]
        return None

    def set_local_val(self, atom: ZilAtom, value: Optional[ZilObject]):
        if value is None:
            self._locals.pop(atom.name, None)
        else:
            self._locals[atom.name] = value

    def push_locals(self):
        """Push a new local scope."""
        self._local_stack.append(self._locals.copy())
        self._locals = {}

    def pop_locals(self):
        """Pop a local scope."""
        if self._local_stack:
            self._locals = self._local_stack.pop()

    def get_std_atom(self, name: str) -> ZilAtom:
        return self._root_oblist[name]

    def register_type(self, type_atom: ZilAtom, primtype):
        pass  # Stub for type registration

    def define_function(self, name: str, func: ZilFunction):
        self._functions[name] = func

    def get_function(self, name: str) -> Optional[ZilFunction]:
        return self._functions.get(name)

    def define_macro(self, name: str, macro: ZilEvalMacro):
        self._macros[name] = macro

    def get_macro(self, name: str) -> Optional[ZilEvalMacro]:
        return self._macros.get(name)


class StdAtom:
    """Standard atom names."""
    NONE = "NONE"
    Plus = "+"
    LVAL = "LVAL"
    GVAL = "GVAL"
    T = "T"
    REDEFINE = "REDEFINE"
    OBLIST = "OBLIST"
    ATOM = "ATOM"
    SORRY = "SORRY"
    FIX = "FIX"
    ANY = "ANY"
    LIST = "LIST"


# Python int limits for MIN/MAX tests
INT_MAX = 2147483647
INT_MIN = -2147483648


# =============================================================================
# MDL Parser
# =============================================================================

class MDLParser:
    """Parser for MDL expressions."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse(self) -> ZilObject:
        """Parse and return a single expression."""
        self.skip_whitespace()
        result = self.parse_expr()
        return result

    def parse_all(self) -> List[ZilObject]:
        """Parse all expressions in the text."""
        results = []
        while self.pos < len(self.text):
            self.skip_whitespace()
            if self.pos >= len(self.text):
                break
            results.append(self.parse_expr())
        return results

    def skip_whitespace(self):
        """Skip whitespace and comments."""
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text[self.pos] == ';':
                # Skip comment to end of line
                while self.pos < len(self.text) and self.text[self.pos] != '\n':
                    self.pos += 1
            else:
                break

    def peek(self) -> str:
        """Peek at current character."""
        if self.pos >= len(self.text):
            return ''
        return self.text[self.pos]

    def parse_expr(self) -> ZilObject:
        """Parse a single expression."""
        self.skip_whitespace()
        if self.pos >= len(self.text):
            raise InterpreterError("Unexpected end of input")

        ch = self.peek()

        # Form: <...>
        if ch == '<':
            return self.parse_form()
        # List: (...)
        elif ch == '(':
            return self.parse_list()
        # Vector: [...]
        elif ch == '[':
            return self.parse_vector()
        # Quote: '
        elif ch == "'":
            self.pos += 1
            expr = self.parse_expr()
            # Return quoted form
            return ('QUOTE', expr)
        # Segment: !
        elif ch == '!':
            self.pos += 1
            expr = self.parse_expr()
            return ZilSegment(expr if isinstance(expr, ZilForm) else ZilForm([expr]))
        # LVAL: .name
        elif ch == '.':
            self.pos += 1
            name = self.parse_atom_name()
            return ('LVAL', name)
        # GVAL: ,name
        elif ch == ',':
            self.pos += 1
            name = self.parse_atom_name()
            return ('GVAL', name)
        # String
        elif ch == '"':
            return self.parse_string()
        # Type indicator: #TYPE value
        elif ch == '#':
            return self.parse_typed_value()
        # Octal number: *...* - only if followed by a digit
        elif ch == '*' and self.pos + 1 < len(self.text) and self.text[self.pos + 1].isdigit():
            return self.parse_octal()
        # % - read-time evaluation
        elif ch == '%':
            self.pos += 1
            expr = self.parse_expr()
            # Evaluate immediately
            if isinstance(expr, ZilForm):
                ctx = Context()
                evaluator = MDLEvaluator(ctx)
                return evaluator.eval(expr)
            return expr
        # Number or negative number
        elif ch.isdigit() or (ch == '-' and self.pos + 1 < len(self.text) and
                              self.text[self.pos + 1].isdigit()):
            return self.parse_number()
        # Atom
        else:
            return self.parse_atom()

    def parse_form(self) -> ZilForm:
        """Parse a form <...>."""
        assert self.peek() == '<'
        self.pos += 1
        elements = []
        while True:
            self.skip_whitespace()
            if self.peek() == '>':
                self.pos += 1
                return ZilForm(elements)
            if self.pos >= len(self.text):
                raise InterpreterError("Unterminated form")
            elements.append(self.parse_expr())

    def parse_list(self) -> ZilList:
        """Parse a list (...)."""
        assert self.peek() == '('
        self.pos += 1
        elements = []
        while True:
            self.skip_whitespace()
            if self.peek() == ')':
                self.pos += 1
                return ZilList(elements)
            if self.pos >= len(self.text):
                raise InterpreterError("Unterminated list")
            elements.append(self.parse_expr())

    def parse_vector(self) -> ZilVector:
        """Parse a vector [...]."""
        assert self.peek() == '['
        self.pos += 1
        elements = []
        while True:
            self.skip_whitespace()
            if self.peek() == ']':
                self.pos += 1
                return ZilVector(*elements)
            if self.pos >= len(self.text):
                raise InterpreterError("Unterminated vector")
            elements.append(self.parse_expr())

    def parse_string(self) -> ZilString:
        """Parse a string "..."."""
        assert self.peek() == '"'
        self.pos += 1
        result = []
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == '"':
                self.pos += 1
                return ZilString(''.join(result))
            elif ch == '\\':
                self.pos += 1
                if self.pos < len(self.text):
                    result.append(self.text[self.pos])
                    self.pos += 1
            else:
                result.append(ch)
                self.pos += 1
        raise InterpreterError("Unterminated string")

    def parse_number(self) -> ZilFix:
        """Parse a decimal number."""
        start = self.pos
        if self.peek() == '-':
            self.pos += 1
        while self.pos < len(self.text) and self.text[self.pos].isdigit():
            self.pos += 1
        return ZilFix(int(self.text[start:self.pos]))

    def parse_octal(self) -> ZilFix:
        """Parse an octal number *...*."""
        assert self.peek() == '*'
        self.pos += 1
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] != '*':
            self.pos += 1
        octal_str = self.text[start:self.pos]
        self.pos += 1  # Skip closing *
        # Parse as octal and convert to signed 32-bit
        value = int(octal_str, 8)
        if value > 0x7FFFFFFF:
            value -= 0x100000000
        return ZilFix(value)

    def parse_typed_value(self) -> ZilObject:
        """Parse a typed value #TYPE value."""
        assert self.peek() == '#'
        self.pos += 1
        type_name = self.parse_atom_name()
        self.skip_whitespace()
        value = self.parse_expr()
        return ('TYPED', type_name, value)

    def parse_atom_name(self) -> str:
        """Parse an atom name."""
        start = self.pos
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            # Valid atom characters - exclude > ( ) [ ] < which are structure delimiters
            if ch.isalnum() or ch in '?!-_+*/=':
                self.pos += 1
            else:
                break
        if start == self.pos:
            raise InterpreterError(f"Expected atom name at position {self.pos}")
        return self.text[start:self.pos]

    def parse_atom(self) -> ZilAtom:
        """Parse an atom."""
        name = self.parse_atom_name()
        return ZilAtom(name)


# =============================================================================
# MDL Evaluator
# =============================================================================

class MDLEvaluator:
    """Evaluator for MDL expressions."""

    def __init__(self, ctx: Context):
        self.ctx = ctx

    def eval(self, expr) -> ZilObject:
        """Evaluate an expression."""
        # Handle parsed tuples (special forms from parser)
        if isinstance(expr, tuple):
            if expr[0] == 'QUOTE':
                return self.quote(expr[1])
            elif expr[0] == 'LVAL':
                return self.lval(expr[1])
            elif expr[0] == 'GVAL':
                return self.gval(expr[1])
            elif expr[0] == 'TYPED':
                return self.eval_typed(expr[1], expr[2])

        # Already a value - return as is
        if isinstance(expr, (ZilFix, ZilString)):
            return expr

        # Atom - evaluate to its value
        if isinstance(expr, ZilAtom):
            return expr  # Atoms evaluate to themselves

        # List - quoted, return as is
        if isinstance(expr, ZilList):
            return expr

        # Vector - quoted, return as is
        if isinstance(expr, ZilVector):
            return expr

        # Form - evaluate
        if isinstance(expr, ZilForm):
            return self.eval_form(expr)

        raise InterpreterError(f"Cannot evaluate: {expr}")

    def quote(self, expr) -> ZilObject:
        """Handle quoted expression - don't evaluate."""
        if isinstance(expr, tuple):
            if expr[0] == 'LVAL':
                return ZilForm([self.ctx.get_std_atom('LVAL'), ZilAtom(expr[1])])
            elif expr[0] == 'GVAL':
                return ZilForm([self.ctx.get_std_atom('GVAL'), ZilAtom(expr[1])])
            elif expr[0] == 'QUOTE':
                return self.quote(expr[1])
        # Recursively quote elements in structures
        if isinstance(expr, ZilList):
            return ZilList([self.quote(e) for e in expr.elements])
        if isinstance(expr, ZilVector):
            return ZilVector(*[self.quote(e) for e in expr.elements])
        if isinstance(expr, ZilForm):
            return ZilForm([self.quote(e) for e in expr.elements])
        return expr

    def lval(self, name: str) -> ZilObject:
        """Get local value."""
        val = self.ctx.get_local_val(ZilAtom(name))
        if val is None:
            raise InterpreterError(f"Unbound local variable: {name}")
        return val

    def gval(self, name: str) -> ZilObject:
        """Get global value."""
        val = self.ctx.get_global_val(ZilAtom(name))
        if val is None:
            raise InterpreterError(f"Unbound global variable: {name}")
        return val

    def eval_typed(self, type_name: str, value) -> ZilObject:
        """Evaluate a typed value #TYPE value."""
        val = self.eval(value)
        # For now, just return the value with type info stored
        if type_name == 'FALSE':
            return self.ctx.FALSE
        # Check for DEFSTRUCT types
        if type_name in self.ctx._defstructs:
            struct_info = self.ctx._defstructs[type_name]
            return ZilStructuredHash(ZilAtom(type_name), struct_info['primtype'], val)
        return val

    def eval_form(self, form: ZilForm) -> ZilObject:
        """Evaluate a form."""
        if not form.elements:
            return form  # Empty form

        # Get the function/operator
        first = form.elements[0]
        args = form.elements[1:]

        # If first is an atom, look up the function
        if isinstance(first, ZilAtom):
            name = first.name
            return self.apply_builtin(name, args)
        elif isinstance(first, tuple) and first[0] == 'GVAL':
            # ,FUNC form
            name = first[1]
            return self.apply_builtin(name, args)

        raise InterpreterError(f"Cannot apply: {first}")

    def apply_builtin(self, name: str, args: list) -> ZilObject:
        """Apply a built-in function."""
        # Arithmetic
        if name == '+':
            return self.builtin_add(args)
        elif name == '-':
            return self.builtin_sub(args)
        elif name == '*':
            return self.builtin_mul(args)
        elif name == '/':
            return self.builtin_div(args)
        elif name == 'MOD':
            return self.builtin_mod(args)
        elif name == 'LSH':
            return self.builtin_lsh(args)
        elif name == 'ORB':
            return self.builtin_orb(args)
        elif name == 'ANDB':
            return self.builtin_andb(args)
        elif name == 'XORB':
            return self.builtin_xorb(args)
        elif name == 'EQVB':
            return self.builtin_eqvb(args)
        elif name == 'MIN':
            return self.builtin_min(args)
        elif name == 'MAX':
            return self.builtin_max(args)
        elif name == 'ABS':
            return self.builtin_abs(args)
        elif name == 'RANDOM':
            return self.builtin_random(args)

        # Comparisons
        elif name == 'L?':
            return self.builtin_less(args)
        elif name == 'L=?':
            return self.builtin_less_eq(args)
        elif name == 'G?':
            return self.builtin_greater(args)
        elif name == 'G=?':
            return self.builtin_greater_eq(args)
        elif name == '=?':
            return self.builtin_num_eq(args)
        elif name == '==?':
            return self.builtin_eq(args)
        elif name == 'N==?':
            return self.builtin_neq(args)

        # Variables
        elif name == 'SET':
            return self.builtin_set(args)
        elif name == 'SETG':
            return self.builtin_setg(args)
        elif name == 'LVAL':
            return self.builtin_lval(args)
        elif name == 'GVAL':
            return self.builtin_gval(args)
        elif name == 'BOUND?':
            return self.builtin_bound(args)
        elif name == 'ASSIGNED?':
            return self.builtin_assigned(args)
        elif name == 'GASSIGNED?':
            return self.builtin_gassigned(args)
        elif name == 'GUNASSIGN':
            return self.builtin_gunassign(args)

        # List/structure operations
        elif name == 'LIST':
            return self.builtin_list(args)
        elif name == 'VECTOR':
            return self.builtin_vector(args)
        elif name == 'FORM':
            return self.builtin_form(args)
        elif name == 'NTH':
            return self.builtin_nth(args)
        elif name == 'REST':
            return self.builtin_rest(args)
        elif name == 'BACK':
            return self.builtin_back(args)
        elif name == 'TOP':
            return self.builtin_top(args)
        elif name == 'LENGTH':
            return self.builtin_length(args)
        elif name == 'EMPTY?':
            return self.builtin_empty(args)
        elif name == 'MEMQ':
            return self.builtin_memq(args)
        elif name == 'MEMBER':
            return self.builtin_member(args)
        elif name == 'ILIST':
            return self.builtin_ilist(args)
        elif name == 'IVECTOR':
            return self.builtin_ivector(args)
        elif name == 'ISTRING':
            return self.builtin_istring(args)
        elif name == 'SUBSTRUC':
            return self.builtin_substruc(args)
        elif name == 'PUTREST':
            return self.builtin_putrest(args)
        elif name == 'SORT':
            return self.builtin_sort(args)
        elif name == 'PUT':
            return self.builtin_put(args)
        elif name == 'GET':
            return self.builtin_get(args)

        # Type operations
        elif name == 'TYPE':
            return self.builtin_type(args)
        elif name == 'PRIMTYPE':
            return self.builtin_primtype(args)
        elif name == 'CHTYPE':
            return self.builtin_chtype(args)
        elif name == 'TYPE?':
            return self.builtin_type_check(args)
        elif name == 'APPLICABLE?':
            return self.builtin_applicable(args)
        elif name == 'STRUCTURED?':
            return self.builtin_structured(args)

        # Flow control
        elif name == 'COND':
            return self.builtin_cond(args)
        elif name == 'VERSION?':
            return self.builtin_version_p(args)
        elif name == 'AGAIN':
            return self.builtin_again(args)
        elif name == 'QUOTE':
            return self.builtin_quote(args)
        elif name == 'EVAL':
            return self.builtin_eval(args)
        elif name == 'APPLY':
            return self.builtin_apply(args)
        elif name == 'AND':
            return self.builtin_and(args)
        elif name == 'OR':
            return self.builtin_or(args)
        elif name == 'NOT':
            return self.builtin_not(args)
        elif name == 'PROG':
            return self.builtin_prog(args)
        elif name == 'REPEAT':
            return self.builtin_repeat(args)
        elif name == 'RETURN':
            return self.builtin_return(args)
        elif name == 'MAPF':
            return self.builtin_mapf(args)
        elif name == 'MAPR':
            return self.builtin_mapr(args)

        # Functions/macros
        elif name == 'DEFINE':
            return self.builtin_define(args)
        elif name == 'DEFMAC':
            return self.builtin_defmac(args)
        elif name == 'FUNCTION':
            return self.builtin_function(args)
        elif name == 'DEFSTRUCT':
            return self.builtin_defstruct(args)

        # String/character operations
        elif name == 'ASCII':
            return self.builtin_ascii(args)
        elif name == 'STRING':
            return self.builtin_string(args)
        elif name == 'SPNAME':
            return self.builtin_spname(args)

        # Atom operations
        elif name == 'ATOM':
            return self.builtin_atom(args)
        elif name == 'PARSE':
            return self.builtin_parse(args)
        elif name == 'LPARSE':
            return self.builtin_lparse(args)
        elif name == 'VALUE':
            return self.builtin_value(args)
        elif name == 'GDECL':
            return self.builtin_gdecl(args)

        # Table operations
        elif name == 'TABLE':
            return self.builtin_table(args)
        elif name == 'ITABLE':
            return self.builtin_itable(args)
        elif name == 'ZGET':
            return self.builtin_zget(args)
        elif name == 'ZPUT':
            return self.builtin_zput(args)
        elif name == 'ZREST':
            return self.builtin_zrest(args)
        elif name == 'GETB':
            return self.builtin_getb(args)
        elif name == 'PUTB':
            return self.builtin_putb(args)

        # Output (just return false for now)
        elif name in ('PRINC', 'PRIN1', 'PRINT', 'CRLF'):
            return self.ctx.FALSE

        # Check for user-defined function
        func = self.ctx.get_function(name)
        if func:
            return self.apply_function(func, args)

        # Check for macro
        macro = self.ctx.get_macro(name)
        if macro:
            return self.apply_macro(macro, args)

        # Check for DEFSTRUCT accessor
        if name.startswith('MAKE-'):
            struct_name = name[5:]
            if struct_name in self.ctx._defstructs:
                return self.make_struct(struct_name, args)

        for struct_name, struct_info in self.ctx._defstructs.items():
            for field_name, field_idx in struct_info.get('fields', {}).items():
                if name == field_name:
                    return self.access_struct_field(struct_info, field_idx, args)

        raise InterpreterError(f"Unknown function: {name}")

    # =========================================================================
    # Arithmetic builtins
    # =========================================================================

    def require_fix(self, val: ZilObject, op: str) -> int:
        """Require value to be a FIX."""
        if not isinstance(val, ZilFix):
            raise ArgumentTypeError(f"{op} requires FIX arguments, got {type(val).__name__}")
        return val.value

    def builtin_add(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(0)
        result = 0
        for arg in args:
            val = self.eval(arg)
            result += self.require_fix(val, '+')
        return ZilFix(result)

    def builtin_sub(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(0)
        if len(args) == 1:
            val = self.eval(args[0])
            return ZilFix(-self.require_fix(val, '-'))
        result = None
        for arg in args:
            val = self.eval(arg)
            n = self.require_fix(val, '-')
            if result is None:
                result = n
            else:
                result -= n
        return ZilFix(result)

    def builtin_mul(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(1)
        result = 1
        for arg in args:
            val = self.eval(arg)
            result *= self.require_fix(val, '*')
        return ZilFix(result)

    def builtin_div(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(1)
        if len(args) == 1:
            val = self.eval(args[0])
            n = self.require_fix(val, '/')
            if n == 0:
                raise InterpreterError("Division by zero")
            # Truncate towards zero
            result = 1 / n
            return ZilFix(int(result))
        result = None
        for arg in args:
            val = self.eval(arg)
            n = self.require_fix(val, '/')
            if result is None:
                result = n
            else:
                if n == 0:
                    raise InterpreterError("Division by zero")
                # Integer division towards zero
                if (result < 0) != (n < 0):
                    result = -(-result // n)
                else:
                    result = result // n
        return ZilFix(result)

    def builtin_mod(self, args: list) -> ZilFix:
        if len(args) != 2:
            raise ArgumentCountError("MOD requires exactly 2 arguments")
        a = self.require_fix(self.eval(args[0]), 'MOD')
        b = self.require_fix(self.eval(args[1]), 'MOD')
        if b == 0:
            raise InterpreterError("Division by zero")
        return ZilFix(a % b)

    def builtin_lsh(self, args: list) -> ZilFix:
        if len(args) != 2:
            raise ArgumentCountError("LSH requires exactly 2 arguments")
        val = self.require_fix(self.eval(args[0]), 'LSH')
        shift = self.require_fix(self.eval(args[1]), 'LSH')

        # Convert to unsigned 32-bit
        if val < 0:
            val = val & 0xFFFFFFFF

        if shift >= 0:
            result = val << shift
        else:
            # Logical right shift (unsigned)
            result = val >> (-shift)

        # Mask to 32-bit
        result &= 0xFFFFFFFF
        # Convert back to signed
        if result > 0x7FFFFFFF:
            result -= 0x100000000
        return ZilFix(result)

    def builtin_orb(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(0)
        result = 0
        for arg in args:
            val = self.eval(arg)
            result |= self.require_fix(val, 'ORB')
        return ZilFix(result)

    def builtin_andb(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(-1)
        result = -1
        for arg in args:
            val = self.eval(arg)
            result &= self.require_fix(val, 'ANDB')
        return ZilFix(result)

    def builtin_xorb(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(0)
        result = 0
        for arg in args:
            val = self.eval(arg)
            result ^= self.require_fix(val, 'XORB')
        return ZilFix(result)

    def builtin_eqvb(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(-1)
        if len(args) == 1:
            val = self.eval(args[0])
            return ZilFix(self.require_fix(val, 'EQVB'))
        # EQVB = ~XOR (bitwise equivalence)
        result = self.require_fix(self.eval(args[0]), 'EQVB')
        for arg in args[1:]:
            val = self.eval(arg)
            n = self.require_fix(val, 'EQVB')
            result = ~(result ^ n)
        return ZilFix(result)

    def builtin_min(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(INT_MAX)
        result = INT_MAX
        for arg in args:
            val = self.eval(arg)
            n = self.require_fix(val, 'MIN')
            if n < result:
                result = n
        return ZilFix(result)

    def builtin_max(self, args: list) -> ZilFix:
        if not args:
            return ZilFix(INT_MIN)
        result = INT_MIN
        for arg in args:
            val = self.eval(arg)
            n = self.require_fix(val, 'MAX')
            if n > result:
                result = n
        return ZilFix(result)

    def builtin_abs(self, args: list) -> ZilFix:
        if len(args) != 1:
            raise ArgumentCountError("ABS requires exactly 1 argument")
        val = self.require_fix(self.eval(args[0]), 'ABS')
        return ZilFix(abs(val))

    def builtin_random(self, args: list) -> ZilFix:
        import random
        if len(args) != 1:
            raise ArgumentCountError("RANDOM requires exactly 1 argument")
        val = self.require_fix(self.eval(args[0]), 'RANDOM')
        if val <= 0:
            return ZilFix(0)
        return ZilFix(random.randint(1, val))

    # =========================================================================
    # Comparison builtins
    # =========================================================================

    def builtin_less(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("L? requires exactly 2 arguments")
        a = self.require_fix(self.eval(args[0]), 'L?')
        b = self.require_fix(self.eval(args[1]), 'L?')
        return self.ctx.TRUE if a < b else self.ctx.FALSE

    def builtin_less_eq(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("L=? requires exactly 2 arguments")
        a = self.require_fix(self.eval(args[0]), 'L=?')
        b = self.require_fix(self.eval(args[1]), 'L=?')
        return self.ctx.TRUE if a <= b else self.ctx.FALSE

    def builtin_greater(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("G? requires exactly 2 arguments")
        a = self.require_fix(self.eval(args[0]), 'G?')
        b = self.require_fix(self.eval(args[1]), 'G?')
        return self.ctx.TRUE if a > b else self.ctx.FALSE

    def builtin_greater_eq(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("G=? requires exactly 2 arguments")
        a = self.require_fix(self.eval(args[0]), 'G=?')
        b = self.require_fix(self.eval(args[1]), 'G=?')
        return self.ctx.TRUE if a >= b else self.ctx.FALSE

    def builtin_num_eq(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("=? requires exactly 2 arguments")
        a = self.require_fix(self.eval(args[0]), '=?')
        b = self.require_fix(self.eval(args[1]), '=?')
        return self.ctx.TRUE if a == b else self.ctx.FALSE

    def builtin_eq(self, args: list) -> ZilObject:
        """==? structural equality."""
        if len(args) != 2:
            raise ArgumentCountError("==? requires exactly 2 arguments")
        a = self.eval(args[0])
        b = self.eval(args[1])
        return self.ctx.TRUE if a.structurally_equals(b) else self.ctx.FALSE

    def builtin_neq(self, args: list) -> ZilObject:
        """N==? structural inequality."""
        if len(args) != 2:
            raise ArgumentCountError("N==? requires exactly 2 arguments")
        a = self.eval(args[0])
        b = self.eval(args[1])
        return self.ctx.FALSE if a.structurally_equals(b) else self.ctx.TRUE

    # =========================================================================
    # Variable builtins
    # =========================================================================

    def builtin_set(self, args: list) -> ZilObject:
        if len(args) < 2 or len(args) > 3:
            raise ArgumentCountError("SET requires 2 to 3 arguments")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("SET first argument must be an atom")
        value = self.eval(args[1])
        self.ctx.set_local_val(ZilAtom(name), value)
        return value

    def builtin_setg(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("SETG requires exactly 2 arguments")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("SETG first argument must be an atom")
        value = self.eval(args[1])

        # Check GDECL type constraint if any
        if hasattr(self.ctx, '_gdecls') and name in self.ctx._gdecls:
            decl = self.ctx._gdecls[name]
            if isinstance(decl, ZilAtom):
                decl_name = decl.name
                # Check type
                if decl_name == 'FIX' and not isinstance(value, ZilFix):
                    raise DeclCheckError(f"SETG {name}: expected FIX, got {type(value).__name__}")
                elif decl_name == 'STRING' and not isinstance(value, ZilString):
                    raise DeclCheckError(f"SETG {name}: expected STRING, got {type(value).__name__}")
                elif decl_name == 'LIST' and not isinstance(value, ZilList):
                    raise DeclCheckError(f"SETG {name}: expected LIST, got {type(value).__name__}")
                elif decl_name == 'VECTOR' and not isinstance(value, ZilVector):
                    raise DeclCheckError(f"SETG {name}: expected VECTOR, got {type(value).__name__}")
                # ANY accepts anything

        self.ctx.set_global_val(ZilAtom(name), value)
        return value

    def builtin_lval(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("LVAL requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("LVAL argument must be an atom")
        val = self.ctx.get_local_val(ZilAtom(name))
        if val is None:
            raise InterpreterError(f"Unbound local variable: {name}")
        return val

    def builtin_gval(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("GVAL requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("GVAL argument must be an atom")
        val = self.ctx.get_global_val(ZilAtom(name))
        if val is None:
            raise InterpreterError(f"Unbound global variable: {name}")
        return val

    def builtin_bound(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("BOUND? requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("BOUND? argument must be an atom")
        val = self.ctx.get_local_val(ZilAtom(name))
        return self.ctx.TRUE if val is not None else self.ctx.FALSE

    def builtin_assigned(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("ASSIGNED? requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("ASSIGNED? argument must be an atom")
        val = self.ctx.get_local_val(ZilAtom(name))
        return self.ctx.TRUE if val is not None else self.ctx.FALSE

    def builtin_gassigned(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("GASSIGNED? requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("GASSIGNED? argument must be an atom")
        val = self.ctx.get_global_val(ZilAtom(name))
        return self.ctx.TRUE if val is not None else self.ctx.FALSE

    def builtin_gunassign(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("GUNASSIGN requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("GUNASSIGN argument must be an atom")
        self.ctx.set_global_val(ZilAtom(name), None)
        return ZilAtom(name)

    # =========================================================================
    # List/structure builtins
    # =========================================================================

    def builtin_list(self, args: list) -> ZilList:
        elements = [self.eval(arg) for arg in args]
        return ZilList(elements)

    def builtin_vector(self, args: list) -> ZilVector:
        elements = [self.eval(arg) for arg in args]
        return ZilVector(*elements)

    def builtin_form(self, args: list) -> ZilForm:
        elements = [self.eval(arg) for arg in args]
        return ZilForm(elements)

    def builtin_nth(self, args: list) -> ZilObject:
        if len(args) < 1 or len(args) > 2:
            raise ArgumentCountError("NTH requires 1 or 2 arguments")
        struct = self.eval(args[0])
        n = self.require_fix(self.eval(args[1]), 'NTH') if len(args) > 1 else 1
        if isinstance(struct, (ZilList, ZilForm)):
            if n < 1 or n > len(struct.elements):
                raise InterpreterError("NTH index out of bounds")
            return struct.elements[n - 1]
        elif isinstance(struct, ZilVector):
            if n < 1 or n > len(struct.elements):
                raise InterpreterError("NTH index out of bounds")
            return struct.elements[n - 1]
        elif isinstance(struct, ZilString):
            if n < 1 or n > len(struct.value):
                raise InterpreterError("NTH index out of bounds")
            return ZilFix(ord(struct.value[n - 1]))
        raise ArgumentTypeError("NTH requires a structured type")

    def builtin_rest(self, args: list) -> ZilObject:
        if len(args) < 1 or len(args) > 2:
            raise ArgumentCountError("REST requires 1 or 2 arguments")
        struct = self.eval(args[0])
        n = self.require_fix(self.eval(args[1]), 'REST') if len(args) > 1 else 1
        if isinstance(struct, ZilList):
            return ZilList(struct.elements[n:])
        elif isinstance(struct, ZilVector):
            return ZilVector(*struct.elements[n:])
        elif isinstance(struct, ZilString):
            return ZilString(struct.value[n:])
        elif isinstance(struct, ZilForm):
            return ZilForm(struct.elements[n:])
        raise ArgumentTypeError("REST requires a structured type")

    def builtin_back(self, args: list) -> ZilObject:
        if len(args) < 1 or len(args) > 2:
            raise ArgumentCountError("BACK requires 1 or 2 arguments")
        # BACK reverses REST - needs to know original structure
        raise InterpreterError("BACK not fully implemented")

    def builtin_top(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("TOP requires 1 argument")
        # TOP returns the original structure
        raise InterpreterError("TOP not fully implemented")

    def builtin_length(self, args: list) -> ZilFix:
        if len(args) != 1:
            raise ArgumentCountError("LENGTH requires 1 argument")
        struct = self.eval(args[0])
        if isinstance(struct, (ZilList, ZilVector, ZilForm)):
            return ZilFix(len(struct.elements))
        elif isinstance(struct, ZilString):
            return ZilFix(len(struct.value))
        raise ArgumentTypeError("LENGTH requires a structured type")

    def builtin_empty(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("EMPTY? requires 1 argument")
        struct = self.eval(args[0])
        if isinstance(struct, (ZilList, ZilVector, ZilForm)):
            return self.ctx.TRUE if len(struct.elements) == 0 else self.ctx.FALSE
        elif isinstance(struct, ZilString):
            return self.ctx.TRUE if len(struct.value) == 0 else self.ctx.FALSE
        raise ArgumentTypeError("EMPTY? requires a structured type")

    def builtin_memq(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("MEMQ requires 2 arguments")
        needle = self.eval(args[0])
        haystack = self.eval(args[1])

        if isinstance(haystack, ZilList):
            for i, elem in enumerate(haystack.elements):
                if self._memq_match(needle, elem):
                    return ZilList(haystack.elements[i:])
            return self.ctx.FALSE
        elif isinstance(haystack, ZilVector):
            for i, elem in enumerate(haystack.elements):
                if self._memq_match(needle, elem):
                    return ZilVector(*haystack.elements[i:])
            return self.ctx.FALSE
        raise ArgumentTypeError("MEMQ requires a list or vector")

    def _memq_match(self, a: ZilObject, b: ZilObject) -> bool:
        """MEMQ uses value equality for LVAL/GVAL forms, identity otherwise."""
        if isinstance(a, ZilFix) and isinstance(b, ZilFix):
            return a.value == b.value
        if isinstance(a, ZilAtom) and isinstance(b, ZilAtom):
            return a.name == b.name
        if isinstance(a, ZilForm) and isinstance(b, ZilForm):
            # Check if both are LVAL or GVAL forms
            if len(a.elements) == 2 and len(b.elements) == 2:
                if (isinstance(a.elements[0], ZilAtom) and isinstance(b.elements[0], ZilAtom)):
                    if a.elements[0].name in ('LVAL', 'GVAL') and a.elements[0].name == b.elements[0].name:
                        if isinstance(a.elements[1], ZilAtom) and isinstance(b.elements[1], ZilAtom):
                            return a.elements[1].name == b.elements[1].name
        return a is b

    def builtin_member(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("MEMBER requires 2 arguments")
        needle = self.eval(args[0])
        haystack = self.eval(args[1])

        # String substring search
        if isinstance(needle, ZilString) and isinstance(haystack, ZilString):
            if not needle.value:
                return self.ctx.FALSE
            idx = haystack.value.find(needle.value)
            if idx >= 0:
                return ZilString(haystack.value[idx:])
            return self.ctx.FALSE

        if isinstance(haystack, ZilList):
            for i, elem in enumerate(haystack.elements):
                if needle.structurally_equals(elem):
                    return ZilList(haystack.elements[i:])
            return self.ctx.FALSE
        elif isinstance(haystack, ZilVector):
            for i, elem in enumerate(haystack.elements):
                if needle.structurally_equals(elem):
                    return ZilVector(*haystack.elements[i:])
            return self.ctx.FALSE
        raise ArgumentTypeError("MEMBER requires a list, vector, or string")

    def builtin_ilist(self, args: list) -> ZilList:
        if len(args) != 2:
            raise ArgumentCountError("ILIST requires 2 arguments")
        count = self.require_fix(self.eval(args[0]), 'ILIST')
        initializer = args[1]

        # If initializer is quoted, extract the inner expression to evaluate each time
        if isinstance(initializer, tuple) and initializer[0] == 'QUOTE':
            initializer = initializer[1]

        elements = []
        for _ in range(count):
            elements.append(self.eval(initializer))
        return ZilList(elements)

    def builtin_ivector(self, args: list) -> ZilVector:
        if len(args) != 2:
            raise ArgumentCountError("IVECTOR requires 2 arguments")
        count = self.require_fix(self.eval(args[0]), 'IVECTOR')
        initializer = args[1]

        # If initializer is quoted, extract the inner expression to evaluate each time
        if isinstance(initializer, tuple) and initializer[0] == 'QUOTE':
            initializer = initializer[1]

        elements = []
        for _ in range(count):
            elements.append(self.eval(initializer))
        return ZilVector(*elements)

    def builtin_istring(self, args: list) -> ZilString:
        if len(args) != 2:
            raise ArgumentCountError("ISTRING requires 2 arguments")
        count = self.require_fix(self.eval(args[0]), 'ISTRING')
        initializer = args[1]

        # If initializer is quoted, extract the inner expression to evaluate each time
        if isinstance(initializer, tuple) and initializer[0] == 'QUOTE':
            initializer = initializer[1]

        chars = []
        for _ in range(count):
            val = self.eval(initializer)
            if isinstance(val, ZilFix):
                chars.append(chr(val.value))
            elif isinstance(val, ZilString) and len(val.value) == 1:
                chars.append(val.value)
            else:
                raise ArgumentTypeError("ISTRING initializer must return FIX or single-char STRING")
        return ZilString(''.join(chars))

    def builtin_substruc(self, args: list) -> ZilObject:
        if len(args) < 1 or len(args) > 3:
            raise ArgumentCountError("SUBSTRUC requires 1-3 arguments")
        struct = self.eval(args[0])
        rest_by = self.require_fix(self.eval(args[1]), 'SUBSTRUC') if len(args) > 1 else 0
        length = self.require_fix(self.eval(args[2]), 'SUBSTRUC') if len(args) > 2 else None

        if isinstance(struct, ZilList):
            elems = struct.elements[rest_by:]
            if length is not None:
                elems = elems[:length]
            return ZilList(elems)
        elif isinstance(struct, ZilVector):
            elems = struct.elements[rest_by:]
            if length is not None:
                elems = elems[:length]
            return ZilVector(*elems)
        elif isinstance(struct, ZilString):
            s = struct.value[rest_by:]
            if length is not None:
                s = s[:length]
            return ZilString(s)
        raise ArgumentTypeError("SUBSTRUC requires a structured type")

    def builtin_putrest(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("PUTREST requires 2 arguments")
        struct = self.eval(args[0])
        new_rest = self.eval(args[1])

        if isinstance(struct, ZilList):
            if not struct.elements:
                raise InterpreterError("Cannot PUTREST on empty list")
            first = struct.elements[0]
            if isinstance(new_rest, ZilList):
                return ZilList([first] + new_rest.elements)
            raise ArgumentTypeError("PUTREST second argument must be a list")
        elif isinstance(struct, ZilForm):
            if not struct.elements:
                raise InterpreterError("Cannot PUTREST on empty form")
            first = struct.elements[0]
            if isinstance(new_rest, ZilList):
                return ZilForm([first] + new_rest.elements)
            raise ArgumentTypeError("PUTREST second argument must be a list")
        raise ArgumentTypeError("PUTREST requires a list or form")

    def builtin_sort(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("SORT requires 2 arguments")
        # First arg is comparison function (or <> for default)
        # Second arg is the structure to sort
        struct = self.eval(args[1])
        if isinstance(struct, ZilVector):
            # Default sort for numbers
            elems = sorted(struct.elements, key=lambda x: x.value if isinstance(x, ZilFix) else 0)
            return ZilVector(*elems)
        raise ArgumentTypeError("SORT requires a vector")

    def builtin_put(self, args: list) -> ZilObject:
        if len(args) < 2:
            raise ArgumentCountError("PUT requires at least 2 arguments")
        struct = self.eval(args[0])
        idx = self.require_fix(self.eval(args[1]), 'PUT')
        value = self.eval(args[2]) if len(args) > 2 else None
        if isinstance(struct, (ZilList, ZilVector, ZilForm)):
            if idx < 1 or idx > len(struct.elements):
                raise InterpreterError("PUT index out of bounds")
            struct.elements[idx - 1] = value
            return struct
        raise ArgumentTypeError("PUT requires a structured type")

    def builtin_get(self, args: list) -> ZilObject:
        if len(args) < 1 or len(args) > 2:
            raise ArgumentCountError("GET requires 1 or 2 arguments")
        struct = self.eval(args[0])
        idx = self.require_fix(self.eval(args[1]), 'GET') if len(args) > 1 else 1
        if isinstance(struct, (ZilList, ZilVector, ZilForm)):
            if idx < 1 or idx > len(struct.elements):
                raise InterpreterError("GET index out of bounds")
            return struct.elements[idx - 1]
        raise ArgumentTypeError("GET requires a structured type")

    # =========================================================================
    # Type builtins
    # =========================================================================

    def builtin_type(self, args: list) -> ZilAtom:
        if len(args) != 1:
            raise ArgumentCountError("TYPE requires 1 argument")
        val = self.eval(args[0])
        if isinstance(val, ZilFix):
            return ZilAtom('FIX')
        elif isinstance(val, ZilString):
            return ZilAtom('STRING')
        elif isinstance(val, ZilAtom):
            return ZilAtom('ATOM')
        elif isinstance(val, ZilList):
            return ZilAtom('LIST')
        elif isinstance(val, ZilVector):
            return ZilAtom('VECTOR')
        elif isinstance(val, ZilForm):
            return ZilAtom('FORM')
        elif isinstance(val, ZilStructuredHash):
            return val.type_atom
        return ZilAtom('UNKNOWN')

    def builtin_primtype(self, args: list) -> ZilAtom:
        if len(args) != 1:
            raise ArgumentCountError("PRIMTYPE requires 1 argument")
        val = self.eval(args[0])
        if isinstance(val, ZilFix):
            return ZilAtom('WORD')
        elif isinstance(val, ZilString):
            return ZilAtom('STRING')
        elif isinstance(val, (ZilList, ZilForm)):
            return ZilAtom('LIST')
        elif isinstance(val, ZilVector):
            return ZilAtom('VECTOR')
        elif isinstance(val, ZilStructuredHash):
            return ZilAtom(val.primtype)
        return ZilAtom('ATOM')

    def builtin_chtype(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("CHTYPE requires 2 arguments")
        val = self.eval(args[0])
        type_name = args[1]
        if isinstance(type_name, ZilAtom):
            type_str = type_name.name
        else:
            raise ArgumentTypeError("CHTYPE second argument must be an atom")

        # Check for DEFSTRUCT type
        if type_str in self.ctx._defstructs:
            struct_info = self.ctx._defstructs[type_str]
            if 'notype' in struct_info and struct_info['notype']:
                raise InterpreterError(f"Cannot CHTYPE to NOTYPE struct {type_str}")
            return ZilStructuredHash(ZilAtom(type_str), struct_info['primtype'], val)

        # Basic type conversions
        if type_str == 'LIST' and isinstance(val, ZilVector):
            return ZilList(val.elements)
        elif type_str == 'VECTOR' and isinstance(val, ZilList):
            return ZilVector(*val.elements)
        elif type_str == 'FORM' and isinstance(val, ZilList):
            return ZilForm(val.elements)
        return val

    def builtin_type_check(self, args: list) -> ZilObject:
        if len(args) < 2:
            raise ArgumentCountError("TYPE? requires at least 2 arguments")
        val = self.eval(args[0])
        for type_arg in args[1:]:
            if isinstance(type_arg, ZilAtom):
                type_name = type_arg.name
                actual_type = self.builtin_type([val])
                if actual_type.name == type_name:
                    return actual_type
        return self.ctx.FALSE

    def builtin_applicable(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("APPLICABLE? requires 1 argument")
        val = self.eval(args[0])
        if isinstance(val, (ZilFunction, ZilEvalMacro)):
            return self.ctx.TRUE
        if isinstance(val, ZilAtom):
            # Check if it's a known function
            if val.name in ('+', '-', '*', '/', 'LSH', 'ORB', 'ANDB', 'XORB'):
                return self.ctx.TRUE
        return self.ctx.FALSE

    def builtin_structured(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("STRUCTURED? requires 1 argument")
        val = self.eval(args[0])
        if isinstance(val, (ZilList, ZilVector, ZilForm, ZilString)):
            return self.ctx.TRUE
        return self.ctx.FALSE

    # =========================================================================
    # Flow control builtins
    # =========================================================================

    def builtin_cond(self, args: list) -> ZilObject:
        if not args:
            raise InterpreterError("COND requires 1 or more args")

        for clause in args:
            if isinstance(clause, ZilList):
                if not clause.elements:
                    raise InterpreterError("COND clause cannot be empty")
                condition = self.eval(clause.elements[0])
                if not self.is_false(condition):
                    # Execute body, return last value
                    result = condition
                    for expr in clause.elements[1:]:
                        result = self.eval(expr)
                    return result
        return self.ctx.FALSE

    def builtin_version_p(self, args: list) -> ZilObject:
        """VERSION? - similar to COND but version-specific."""
        for clause in args:
            if isinstance(clause, ZilList):
                if not clause.elements:
                    raise InterpreterError("VERSION? clause cannot be empty")
                # For now, just evaluate like COND
                condition = self.eval(clause.elements[0])
                if not self.is_false(condition):
                    result = condition
                    for expr in clause.elements[1:]:
                        result = self.eval(expr)
                    return result
        return self.ctx.FALSE

    def builtin_again(self, args: list) -> ZilObject:
        """AGAIN - restart the current PROG/REPEAT."""
        raise AgainException()

    def builtin_quote(self, args: list) -> ZilObject:
        """QUOTE - return argument unevaluated."""
        if len(args) != 1:
            raise ArgumentCountError("QUOTE requires exactly 1 argument")
        # Return the argument unevaluated
        arg = args[0]
        if isinstance(arg, tuple):
            if arg[0] == 'QUOTE':
                return self.quote(arg[1])
            elif arg[0] == 'LVAL':
                return ZilForm([self.ctx.get_std_atom('LVAL'), ZilAtom(arg[1])])
            elif arg[0] == 'GVAL':
                return ZilForm([self.ctx.get_std_atom('GVAL'), ZilAtom(arg[1])])
        return arg

    def builtin_eval(self, args: list) -> ZilObject:
        """EVAL - evaluate an expression."""
        if len(args) < 1 or len(args) > 2:
            raise ArgumentCountError("EVAL requires 1 or 2 arguments")
        if len(args) == 2:
            # Second arg should be an environment - validate it
            env = self.eval(args[1])
            if not isinstance(env, (ZilList, ZilVector)):
                raise ArgumentTypeError("EVAL second argument must be an environment")
        expr = args[0]
        # If it's already evaluated, evaluate again
        if isinstance(expr, tuple):
            return self.eval(expr)
        elif isinstance(expr, ZilList):
            # Evaluate elements of the list
            return ZilList([self.eval(e) for e in expr.elements])
        elif isinstance(expr, ZilForm):
            return self.eval_form(expr)
        return expr

    def builtin_apply(self, args: list) -> ZilObject:
        """APPLY - apply a function to arguments."""
        if len(args) < 2:
            raise ArgumentCountError("APPLY requires at least 2 arguments")
        func = self.eval(args[0])
        arg_list = self.eval(args[1])

        if not isinstance(arg_list, ZilList):
            raise ArgumentTypeError("APPLY second argument must be a list")

        if isinstance(func, ZilFunction):
            return self.apply_function(func, arg_list.elements)
        elif isinstance(func, ZilAtom):
            return self.apply_builtin(func.name, arg_list.elements)

        raise InterpreterError(f"Cannot apply: {func}")

    def builtin_and(self, args: list) -> ZilObject:
        result = self.ctx.TRUE
        for arg in args:
            result = self.eval(arg)
            if self.is_false(result):
                return self.ctx.FALSE
        return result

    def builtin_or(self, args: list) -> ZilObject:
        for arg in args:
            result = self.eval(arg)
            if not self.is_false(result):
                return result
        return self.ctx.FALSE

    def builtin_not(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("NOT requires 1 argument")
        val = self.eval(args[0])
        return self.ctx.TRUE if self.is_false(val) else self.ctx.FALSE

    def is_false(self, val: ZilObject) -> bool:
        """Check if value is false (#FALSE () or empty list)."""
        if isinstance(val, ZilList) and len(val.elements) == 0:
            return True
        return False

    def builtin_prog(self, args: list) -> ZilObject:
        if not args:
            return self.ctx.FALSE
        # First arg is bindings
        bindings = args[0]
        body = args[1:]

        self.ctx.push_locals()
        try:
            if isinstance(bindings, ZilList):
                for binding in bindings.elements:
                    if isinstance(binding, ZilAtom):
                        self.ctx.set_local_val(binding, self.ctx.FALSE)
                    elif isinstance(binding, ZilList) and len(binding.elements) >= 1:
                        name = binding.elements[0]
                        val = self.eval(binding.elements[1]) if len(binding.elements) > 1 else self.ctx.FALSE
                        if isinstance(name, ZilAtom):
                            self.ctx.set_local_val(name, val)

            result = self.ctx.FALSE
            for expr in body:
                result = self.eval(expr)
            return result
        except ReturnException as ret:
            return ret.value
        finally:
            self.ctx.pop_locals()

    def builtin_repeat(self, args: list) -> ZilObject:
        if not args:
            return self.ctx.FALSE
        bindings = args[0]
        body = args[1:]

        self.ctx.push_locals()
        try:
            if isinstance(bindings, ZilList):
                for binding in bindings.elements:
                    if isinstance(binding, ZilAtom):
                        self.ctx.set_local_val(binding, self.ctx.FALSE)
                    elif isinstance(binding, ZilList) and len(binding.elements) >= 1:
                        name = binding.elements[0]
                        val = self.eval(binding.elements[1]) if len(binding.elements) > 1 else self.ctx.FALSE
                        if isinstance(name, ZilAtom):
                            self.ctx.set_local_val(name, val)

            while True:
                for expr in body:
                    self.eval(expr)
        except ReturnException as ret:
            return ret.value
        finally:
            self.ctx.pop_locals()

    def builtin_return(self, args: list) -> ZilObject:
        val = self.eval(args[0]) if args else self.ctx.TRUE
        raise ReturnException(val)

    def builtin_mapf(self, args: list) -> ZilObject:
        if len(args) < 2:
            raise ArgumentCountError("MAPF requires at least 2 arguments")
        finisher = args[0]
        func = args[1]
        structs = [self.eval(arg) for arg in args[2:]]

        results = []
        while all(not self.is_empty_struct(s) for s in structs):
            # Get first element of each struct
            firsts = [self.first_of(s) for s in structs]
            # Apply function
            if isinstance(func, ZilAtom):
                result = self.apply_builtin(func.name, firsts)
            else:
                result = self.eval(ZilForm([func] + firsts))
            results.append(result)
            # REST each struct
            structs = [self.rest_of(s) for s in structs]

        # Apply finisher
        if isinstance(finisher, ZilForm) and not finisher.elements:
            return self.ctx.FALSE
        elif isinstance(finisher, ZilAtom):
            if finisher.name == 'LIST':
                return ZilList(results)
            elif finisher.name == 'VECTOR':
                return ZilVector(*results)
        return self.ctx.FALSE

    def builtin_mapr(self, args: list) -> ZilObject:
        if len(args) < 2:
            raise ArgumentCountError("MAPR requires at least 2 arguments")
        finisher = args[0]
        func = args[1]
        structs = [self.eval(arg) for arg in args[2:]]

        results = []
        while all(not self.is_empty_struct(s) for s in structs):
            # Apply function to current structures (not first elements)
            if isinstance(func, ZilAtom):
                result = self.apply_builtin(func.name, structs)
            else:
                result = self.eval(ZilForm([func] + structs))
            results.append(result)
            # REST each struct
            structs = [self.rest_of(s) for s in structs]

        # Apply finisher
        if isinstance(finisher, ZilForm) and not finisher.elements:
            return self.ctx.FALSE
        elif isinstance(finisher, ZilAtom):
            if finisher.name == 'LIST':
                return ZilList(results)
        return self.ctx.FALSE

    def is_empty_struct(self, s: ZilObject) -> bool:
        if isinstance(s, (ZilList, ZilVector, ZilForm)):
            return len(s.elements) == 0
        if isinstance(s, ZilString):
            return len(s.value) == 0
        return True

    def first_of(self, s: ZilObject) -> ZilObject:
        if isinstance(s, (ZilList, ZilVector, ZilForm)):
            return s.elements[0] if s.elements else self.ctx.FALSE
        if isinstance(s, ZilString):
            return ZilFix(ord(s.value[0])) if s.value else self.ctx.FALSE
        return self.ctx.FALSE

    def rest_of(self, s: ZilObject) -> ZilObject:
        if isinstance(s, ZilList):
            return ZilList(s.elements[1:])
        if isinstance(s, ZilVector):
            return ZilVector(*s.elements[1:])
        if isinstance(s, ZilForm):
            return ZilForm(s.elements[1:])
        if isinstance(s, ZilString):
            return ZilString(s.value[1:])
        return s

    # =========================================================================
    # Function/macro builtins
    # =========================================================================

    def builtin_define(self, args: list) -> ZilAtom:
        if len(args) < 2:
            raise ArgumentCountError("DEFINE requires at least 2 arguments")
        name = args[0]
        if not isinstance(name, ZilAtom):
            raise ArgumentTypeError("DEFINE name must be an atom")
        params_form = args[1]
        if not isinstance(params_form, ZilList):
            raise ArgumentTypeError("DEFINE params must be a list")
        body = args[2:]
        func = ZilFunction(name.name, params_form.elements, body)
        self.ctx.define_function(name.name, func)
        self.ctx.set_global_val(name, func)
        return name

    def builtin_defmac(self, args: list) -> ZilAtom:
        if len(args) < 2:
            raise ArgumentCountError("DEFMAC requires at least 2 arguments")
        name = args[0]
        if not isinstance(name, ZilAtom):
            raise ArgumentTypeError("DEFMAC name must be an atom")
        params_form = args[1]
        if not isinstance(params_form, ZilList):
            raise ArgumentTypeError("DEFMAC params must be a list")
        body = args[2:]
        macro = ZilEvalMacro(name.name, params_form.elements, body)
        self.ctx.define_macro(name.name, macro)
        return name

    def builtin_function(self, args: list) -> ZilFunction:
        if len(args) < 1:
            raise ArgumentCountError("FUNCTION requires at least 1 argument")
        params_form = args[0]
        if not isinstance(params_form, ZilList):
            raise ArgumentTypeError("FUNCTION params must be a list")
        body = args[1:]
        return ZilFunction('ANONYMOUS', params_form.elements, body)

    def builtin_defstruct(self, args: list) -> ZilAtom:
        if len(args) < 2:
            raise ArgumentCountError("DEFSTRUCT requires at least 2 arguments")
        name = args[0]
        if not isinstance(name, ZilAtom):
            raise ArgumentTypeError("DEFSTRUCT name must be an atom")

        # Parse primtype and options
        primtype_spec = args[1]
        if isinstance(primtype_spec, ZilAtom):
            primtype = primtype_spec.name
            options = []
        elif isinstance(primtype_spec, ZilList):
            primtype = primtype_spec.elements[0].name if primtype_spec.elements else 'VECTOR'
            options = primtype_spec.elements[1:]
        else:
            primtype = 'VECTOR'
            options = []

        notype = False
        suppress_constructor = False
        for opt in options:
            if isinstance(opt, tuple) and opt[0] == 'QUOTE':
                opt_val = opt[1]
                if isinstance(opt_val, ZilAtom):
                    if opt_val.name == 'NOTYPE':
                        notype = True
                    elif opt_val.name == 'CONSTRUCTOR':
                        suppress_constructor = True

        # Parse fields
        fields = {}
        for i, field_spec in enumerate(args[2:]):
            if isinstance(field_spec, ZilList) and field_spec.elements:
                field_name = field_spec.elements[0]
                if isinstance(field_name, ZilAtom):
                    fields[field_name.name] = i

        struct_info = {
            'primtype': primtype,
            'notype': notype,
            'suppress_constructor': suppress_constructor,
            'fields': fields,
        }
        self.ctx._defstructs[name.name] = struct_info

        # Create accessors
        for field_name, field_idx in fields.items():
            # The accessor function will be looked up by name in apply_builtin
            pass

        return name

    def apply_function(self, func: ZilFunction, args: list) -> ZilObject:
        """Apply a user-defined function."""
        self.ctx.push_locals()
        try:
            # Bind parameters
            for i, param in enumerate(func.args):
                if isinstance(param, ZilAtom):
                    val = self.eval(args[i]) if i < len(args) else self.ctx.FALSE
                    self.ctx.set_local_val(param, val)

            # Execute body
            result = self.ctx.FALSE
            for expr in func.body:
                result = self.eval(expr)
            return result
        except ReturnException as ret:
            return ret.value
        finally:
            self.ctx.pop_locals()

    def apply_macro(self, macro: ZilEvalMacro, args: list) -> ZilObject:
        """Apply a macro (expand and evaluate)."""
        self.ctx.push_locals()
        try:
            # Bind parameters (unevaluated)
            for i, param in enumerate(macro.args):
                if isinstance(param, ZilAtom):
                    val = args[i] if i < len(args) else self.ctx.FALSE
                    self.ctx.set_local_val(param, val)

            # Execute body to get expansion
            result = self.ctx.FALSE
            for expr in macro.body:
                result = self.eval(expr)

            # Evaluate the expansion
            return self.eval(result)
        finally:
            self.ctx.pop_locals()

    def make_struct(self, struct_name: str, args: list) -> ZilStructuredHash:
        """Create a new DEFSTRUCT instance."""
        struct_info = self.ctx._defstructs[struct_name]
        num_fields = len(struct_info['fields'])
        values = [self.ctx.FALSE] * num_fields

        # Parse keyword arguments
        i = 0
        while i < len(args):
            arg = args[i]
            if isinstance(arg, tuple) and arg[0] == 'QUOTE':
                field_name = arg[1]
                if isinstance(field_name, ZilAtom) and field_name.name in struct_info['fields']:
                    field_idx = struct_info['fields'][field_name.name]
                    if i + 1 < len(args):
                        values[field_idx] = self.eval(args[i + 1])
                        i += 2
                        continue
            i += 1

        return ZilStructuredHash(
            ZilAtom(struct_name),
            struct_info['primtype'],
            ZilVector(*values)
        )

    def access_struct_field(self, struct_info: dict, field_idx: int, args: list) -> ZilObject:
        """Access a field of a DEFSTRUCT instance."""
        if len(args) != 1:
            raise ArgumentCountError("Struct accessor requires 1 argument")
        val = self.eval(args[0])
        if isinstance(val, ZilStructuredHash):
            if isinstance(val.primitive, ZilVector):
                return val.primitive.elements[field_idx]
        elif isinstance(val, ZilVector):
            return val.elements[field_idx]
        raise ArgumentTypeError("Struct accessor requires struct or vector")

    # =========================================================================
    # String/character builtins
    # =========================================================================

    def builtin_ascii(self, args: list) -> ZilObject:
        if len(args) != 1:
            raise ArgumentCountError("ASCII requires 1 argument")
        val = self.eval(args[0])
        if isinstance(val, ZilFix):
            return ZilString(chr(val.value))
        elif isinstance(val, ZilString) and val.value:
            return ZilFix(ord(val.value[0]))
        raise ArgumentTypeError("ASCII requires FIX or STRING")

    def builtin_string(self, args: list) -> ZilString:
        result = []
        for arg in args:
            val = self.eval(arg)
            if isinstance(val, ZilString):
                result.append(val.value)
            elif isinstance(val, ZilFix):
                result.append(chr(val.value))
        return ZilString(''.join(result))

    def builtin_spname(self, args: list) -> ZilString:
        if len(args) != 1:
            raise ArgumentCountError("SPNAME requires exactly 1 argument")
        val = self.eval(args[0])
        if isinstance(val, ZilAtom):
            return ZilString(val.name)
        raise ArgumentTypeError("SPNAME argument must be an atom")

    def builtin_atom(self, args: list) -> ZilAtom:
        """Create a new uninterned atom."""
        if len(args) != 1:
            raise ArgumentCountError("ATOM requires exactly 1 argument")
        val = self.eval(args[0])
        if isinstance(val, ZilString):
            # Create a new uninterned atom - each call creates a distinct atom
            return ZilAtom(val.value, oblist=None, uninterned=True)
        raise ArgumentTypeError("ATOM argument must be a string")

    def builtin_parse(self, args: list) -> ZilObject:
        """Parse a string into an MDL expression."""
        if len(args) < 1 or len(args) > 3:
            raise ArgumentCountError("PARSE requires 1 to 3 arguments")
        val = self.eval(args[0])
        if not isinstance(val, ZilString):
            raise ArgumentTypeError("PARSE argument must be a string")

        text = val.value.strip()
        if not text:
            raise InterpreterError("PARSE: string must contain an expression")

        parser = MDLParser(text)
        try:
            expr = parser.parse()
            # If it's a tuple (like QUOTE, LVAL, GVAL), convert appropriately
            if isinstance(expr, tuple):
                return self.eval(expr)
            # If it's an atom, look it up in the oblist
            if isinstance(expr, ZilAtom):
                # Return the interned atom from the root oblist
                return self.ctx._root_oblist[expr.name]
            return expr
        except InterpreterError:
            raise InterpreterError("PARSE: string must contain an expression")

    def builtin_lparse(self, args: list) -> ZilList:
        """Parse a string into a list of MDL expressions."""
        if len(args) < 1 or len(args) > 3:
            raise ArgumentCountError("LPARSE requires 1 to 3 arguments")
        val = self.eval(args[0])
        if not isinstance(val, ZilString):
            raise ArgumentTypeError("LPARSE argument must be a string")

        text = val.value.strip()
        if not text:
            return ZilList([])

        parser = MDLParser(text)
        results = []
        try:
            while parser.pos < len(parser.text):
                parser.skip_whitespace()
                if parser.pos >= len(parser.text):
                    break
                expr = parser.parse_expr()
                # If it's an atom, look it up in the oblist
                if isinstance(expr, ZilAtom):
                    expr = self.ctx._root_oblist[expr.name]
                results.append(expr)
        except InterpreterError:
            pass

        return ZilList(results)

    def builtin_value(self, args: list) -> ZilObject:
        """Get local or global value - prefers local."""
        if len(args) != 1:
            raise ArgumentCountError("VALUE requires exactly 1 argument")
        name_expr = args[0]
        if isinstance(name_expr, ZilAtom):
            name = name_expr.name
        else:
            raise ArgumentTypeError("VALUE argument must be an atom")

        # Check local first
        val = self.ctx.get_local_val(ZilAtom(name))
        if val is not None:
            return val

        # Then check global
        val = self.ctx.get_global_val(ZilAtom(name))
        if val is not None:
            return val

        raise InterpreterError(f"Unbound variable: {name}")

    def builtin_gdecl(self, args: list) -> ZilObject:
        """Set global declarations."""
        # GDECL (atoms...) decl-type (more-atoms...) decl-type ...
        # For now, just store the declarations in the context
        i = 0
        while i < len(args):
            if isinstance(args[i], ZilList):
                atoms = args[i].elements
                if i + 1 < len(args):
                    decl_type = args[i + 1]
                    for atom in atoms:
                        if isinstance(atom, ZilAtom):
                            # Store the declaration
                            if not hasattr(self.ctx, '_gdecls'):
                                self.ctx._gdecls = {}
                            self.ctx._gdecls[atom.name] = decl_type
                    i += 2
                else:
                    i += 1
            else:
                i += 1
        return self.ctx.TRUE

    # =========================================================================
    # Table builtins
    # =========================================================================

    def builtin_table(self, args: list) -> ZilTable:
        elements = [self.eval(arg) for arg in args]
        return ZilTable(elements)

    def builtin_itable(self, args: list) -> ZilTable:
        if len(args) < 1:
            raise ArgumentCountError("ITABLE requires at least 1 argument")
        count = self.require_fix(self.eval(args[0]), 'ITABLE')
        init_val = self.eval(args[1]) if len(args) > 1 else ZilFix(0)
        elements = [init_val] * count
        return ZilTable(elements)

    def builtin_zget(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("ZGET requires 2 arguments")
        table = self.eval(args[0])
        idx = self.require_fix(self.eval(args[1]), 'ZGET')
        if isinstance(table, ZilTable):
            if idx < 0 or idx >= len(table.elements):
                raise InterpreterError("ZGET index out of bounds")
            return table.elements[idx]
        raise ArgumentTypeError("ZGET requires a TABLE")

    def builtin_zput(self, args: list) -> ZilObject:
        if len(args) != 3:
            raise ArgumentCountError("ZPUT requires 3 arguments")
        table = self.eval(args[0])
        idx = self.require_fix(self.eval(args[1]), 'ZPUT')
        val = self.eval(args[2])
        if isinstance(table, ZilTable):
            if idx < 0 or idx >= len(table.elements):
                raise InterpreterError("ZPUT index out of bounds")
            table.elements[idx] = val
            return val
        raise ArgumentTypeError("ZPUT requires a TABLE")

    def builtin_zrest(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("ZREST requires 2 arguments")
        table = self.eval(args[0])
        offset = self.require_fix(self.eval(args[1]), 'ZREST')
        if isinstance(table, ZilTable):
            if offset < 0 or offset >= len(table.elements) * 2:  # byte offset
                raise InterpreterError("ZREST offset out of bounds")
            return ZilTable(table.elements[offset // 2:])
        raise ArgumentTypeError("ZREST requires a TABLE")

    def builtin_getb(self, args: list) -> ZilObject:
        if len(args) != 2:
            raise ArgumentCountError("GETB requires 2 arguments")
        table = self.eval(args[0])
        idx = self.require_fix(self.eval(args[1]), 'GETB')
        if isinstance(table, ZilTable):
            # Byte access - for now treat as word access
            if idx < 0 or idx >= len(table.elements) * 2:
                raise InterpreterError("GETB index out of bounds")
            return table.elements[idx // 2]
        raise ArgumentTypeError("GETB requires a TABLE")

    def builtin_putb(self, args: list) -> ZilObject:
        if len(args) != 3:
            raise ArgumentCountError("PUTB requires 3 arguments")
        table = self.eval(args[0])
        idx = self.require_fix(self.eval(args[1]), 'PUTB')
        val = self.eval(args[2])
        if isinstance(table, ZilTable):
            if idx < 0 or idx >= len(table.elements) * 2:
                raise InterpreterError("PUTB index out of bounds")
            table.elements[idx // 2] = val
            return val
        raise ArgumentTypeError("PUTB requires a TABLE")


class ReturnException(Exception):
    """Exception used to implement RETURN."""
    def __init__(self, value: ZilObject, activation=None):
        self.value = value
        self.activation = activation


class AgainException(Exception):
    """Exception used to implement AGAIN."""
    def __init__(self, activation=None):
        self.activation = activation


# =============================================================================
# Test helper functions
# =============================================================================

def evaluate(expression: str, ctx: Optional[Context] = None) -> ZilObject:
    """
    Evaluate an MDL expression.
    """
    if ctx is None:
        ctx = Context()

    parser = MDLParser(expression)
    exprs = parser.parse_all()
    evaluator = MDLEvaluator(ctx)

    result = ctx.FALSE
    for expr in exprs:
        result = evaluator.eval(expr)
    return result


def eval_and_assert(expression: str, expected: ZilObject, ctx: Optional[Context] = None):
    """
    Evaluate an expression and assert the result equals expected.
    """
    actual = evaluate(expression, ctx)
    if not actual.structurally_equals(expected):
        raise AssertionError(
            f"EvalAndAssert failed. Expected: {expected}. Actual: {actual}. "
            f"Expression was: {expression}"
        )


def eval_and_catch(
    expression: str,
    exception_type: Type[Exception],
    predicate: Optional[Callable[[Exception], bool]] = None,
    ctx: Optional[Context] = None
):
    """
    Evaluate an expression and expect it to raise an exception.
    """
    try:
        result = evaluate(expression, ctx)
        raise AssertionError(
            f"EvalAndCatch failed. Expected exception: {exception_type.__name__}. "
            f"Actual: no exception, returned {result}. Expression was: {expression}"
        )
    except exception_type as ex:
        if predicate is not None and not predicate(ex):
            raise AssertionError(
                f"EvalAndCatch failed. Predicate returned false. Exception: {ex}"
            )
    except AssertionError:
        raise
    except Exception as ex:
        if isinstance(ex, exception_type):
            return
        raise AssertionError(
            f"EvalAndCatch failed. Expected exception: {exception_type.__name__}. "
            f"Actual exception: {type(ex).__name__} ({ex}). Expression was: {expression}"
        )


def assert_structurally_equal(expected: ZilObject, actual: ZilObject, message: str = None):
    """
    Assert two ZilObjects are structurally equal.
    """
    if expected is None and actual is None:
        return
    if expected is None or actual is None:
        msg = message or "AssertStructurallyEqual failed"
        raise AssertionError(f"{msg}. Expected: {expected}. Actual: {actual}.")
    if not expected.structurally_equals(actual):
        msg = message or "AssertStructurallyEqual failed"
        raise AssertionError(f"{msg}. Expected: {expected}. Actual: {actual}.")


def assert_not_structurally_equal(not_expected: ZilObject, actual: ZilObject):
    """
    Assert two ZilObjects are NOT structurally equal.
    """
    if not_expected is None and actual is None:
        raise AssertionError(
            f"AssertNotStructurallyEqual failed. "
            f"Not expected: {not_expected}. Actual: {actual}."
        )
    if not_expected is not None and actual is not None:
        if not_expected.structurally_equals(actual):
            raise AssertionError(
                f"AssertNotStructurallyEqual failed. "
                f"Not expected: {not_expected}. Actual: {actual}."
            )


# Pytest fixtures

@pytest.fixture
def ctx():
    """Create a fresh interpreter context."""
    return Context()
