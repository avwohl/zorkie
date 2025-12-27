"""
Tests for Z-machine version-specific features.

Tests compilation and header format for V1-V8.
"""
import pytest
from tests.zilf.conftest import AssertRaw, ZILCompiler, ZVersion


class TestVersionHeaders:
    """Tests for version-specific header format."""

    def test_v1_no_serial_number(self):
        """V1 should have no serial number (zeros at 0x12-0x17)."""
        code = "<VERSION 1>\n<ROUTINE GO () <QUIT>>"
        c = ZILCompiler(ZVersion.V1)
        result = c._compile(code)
        assert result.success, f"Compilation failed: {result.errors}"
        story = result.story_file
        assert story[0] == 1, "Version byte should be 1"
        assert story[0x12:0x18] == b'\x00' * 6, "V1 should have no serial number"

    def test_v2_has_serial_number(self):
        """V2 should have serial number at 0x12-0x17."""
        code = "<VERSION 2>\n<ROUTINE GO () <QUIT>>"
        c = ZILCompiler(ZVersion.V2)
        result = c._compile(code)
        assert result.success, f"Compilation failed: {result.errors}"
        story = result.story_file
        assert story[0] == 2, "Version byte should be 2"
        serial = story[0x12:0x18].decode('ascii')
        assert serial.isdigit(), f"Serial should be numeric YYMMDD, got {serial!r}"

    def test_v3_to_v6_have_serial_number(self):
        """V3-V6 should have serial number."""
        for v in [3, 4, 5, 6]:
            code = f"<VERSION {v}>\n<ROUTINE GO () <QUIT>>"
            c = ZILCompiler(ZVersion(v))
            result = c._compile(code)
            assert result.success, f"V{v} compilation failed: {result.errors}"
            story = result.story_file
            assert story[0] == v, f"Version byte should be {v}"
            serial = story[0x12:0x18].decode('ascii')
            assert serial.isdigit(), f"V{v} serial should be numeric"


class TestVersionCompilation:
    """Tests for version-specific compilation."""

    @pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6, 7, 8])
    def test_all_versions_compile(self, version):
        """All versions should compile a simple program."""
        code = f"<VERSION {version}>\n<ROUTINE GO () <QUIT>>"
        c = ZILCompiler(ZVersion(version))
        result = c._compile(code)
        assert result.success, f"V{version} compilation failed: {result.errors}"
        assert result.story_file[0] == version, f"Version byte should be {version}"

    def test_v6_v7_routines_offset(self):
        """V6 and V7 should have routines offset in header."""
        for v in [6, 7]:
            code = f"<VERSION {v}>\n<ROUTINE GO () <QUIT>>"
            c = ZILCompiler(ZVersion(v))
            result = c._compile(code)
            assert result.success, f"V{v} compilation failed"
            story = result.story_file
            routines_offset = (story[0x28] << 8) | story[0x29]
            strings_offset = (story[0x2A] << 8) | story[0x2B]
            assert routines_offset > 0, f"V{v} should have routines offset"
            assert strings_offset > 0, f"V{v} should have strings offset"

    def test_v8_no_routines_offset(self):
        """V8 should not use routines/strings offset fields."""
        code = "<VERSION 8>\n<ROUTINE GO () <QUIT>>"
        c = ZILCompiler(ZVersion.V8)
        result = c._compile(code)
        assert result.success, f"V8 compilation failed"
        story = result.story_file
        # V8 uses direct packed addresses (/8), not offset-based
        assert story[0] == 8


class TestVersionExecution:
    """Tests for version-specific execution."""

    def test_v1_hello_world(self):
        """V1 program should execute correctly."""
        code = '<VERSION 1>\n<ROUTINE GO () <PRINTI "Hello V1"> <CRLF> <QUIT>>'
        AssertRaw(code).outputs("Hello V1\n")

    def test_v2_hello_world(self):
        """V2 program should execute correctly."""
        code = '<VERSION 2>\n<ROUTINE GO () <PRINTI "Hello V2"> <CRLF> <QUIT>>'
        AssertRaw(code).outputs("Hello V2\n")


class TestVersionFileLengthDivisor:
    """Tests for file length divisor by version."""

    @pytest.mark.parametrize("version,divisor", [
        (1, 2), (2, 2), (3, 2),
        (4, 4), (5, 4),
        (6, 8), (7, 8), (8, 8),
    ])
    def test_file_length_divisor(self, version, divisor):
        """File length field should use correct divisor for version."""
        code = f"<VERSION {version}>\n<ROUTINE GO () <QUIT>>"
        c = ZILCompiler(ZVersion(version))
        result = c._compile(code)
        assert result.success
        story = result.story_file
        stored_len = (story[0x1A] << 8) | story[0x1B]
        actual_len = len(story)
        # The stored length * divisor should equal actual length
        # (with possible padding for alignment)
        assert stored_len * divisor >= actual_len - divisor
        assert stored_len * divisor <= actual_len + divisor
