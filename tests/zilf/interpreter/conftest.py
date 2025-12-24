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
from typing import Any, Callable, Optional, Type
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

    def __init__(self, name: str, oblist=None):
        self.name = name
        self.oblist = oblist

    @classmethod
    def parse(cls, name: str, ctx=None) -> 'ZilAtom':
        return cls(name)

    def structurally_equals(self, other: ZilObject) -> bool:
        if isinstance(other, ZilAtom):
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
        self._root_oblist = ObList("ROOT")
        self._package_oblist = ObList("PACKAGE")
        self._true = ZilAtom("T")
        self._false = ZilList([])  # #FALSE () is an empty list

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
        return self._locals.get(atom.name)

    def set_local_val(self, atom: ZilAtom, value: Optional[ZilObject]):
        if value is None:
            self._locals.pop(atom.name, None)
        else:
            self._locals[atom.name] = value

    def get_std_atom(self, name: str) -> ZilAtom:
        return self._root_oblist[name]

    def register_type(self, type_atom: ZilAtom, primtype):
        pass  # Stub for type registration


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


# Test helper functions

def evaluate(expression: str, ctx: Optional[Context] = None) -> ZilObject:
    """
    Evaluate an MDL expression.

    This is a stub - the actual implementation would parse and evaluate
    the expression using the zorkie interpreter.
    """
    if ctx is None:
        ctx = Context()

    # Skip tests that require the MDL interpreter - zorkie is compiler-only
    pytest.skip("MDL interpreter not implemented - zorkie is compiler-only")


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
    except Exception as ex:
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


# Python int limits for MIN/MAX tests
INT_MAX = 2147483647
INT_MIN = -2147483648


# Pytest fixtures

@pytest.fixture
def ctx():
    """Create a fresh interpreter context."""
    return Context()
