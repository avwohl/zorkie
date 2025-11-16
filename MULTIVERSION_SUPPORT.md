# Multi-Version Z-Machine Support in Zorkie

## Overview

The Zorkie compiler now supports targeting multiple Z-machine versions (V3, V4, V5, V6), allowing you to compile ZIL source code for different interpreter capabilities.

## Z-Machine Version Differences

### Version 3 (Default)
- **Story File Size**: Up to 128KB
- **Max Objects**: 255
- **Max Properties**: 31
- **Features**: Basic text adventures, sound effects
- **Games**: Zork I-III, Planetfall, Infidel

### Version 4
- **Story File Size**: Up to 256KB
- **Max Objects**: 65535
- **Max Properties**: 31
- **Features**: Enhanced text handling
- **Games**: A Mind Forever Voyaging, Trinity

### Version 5
- **Story File Size**: Up to 256KB
- **Max Objects**: 65535
- **Max Properties**: 63
- **Features**: Colors, fonts, mouse support, extended opcodes
- **Games**: Leather Goddesses, Wishbringer (later editions)

### Version 6
- **Story File Size**: Up to 512KB
- **Max Objects**: 65535
- **Max Properties**: 63
- **Features**: Graphics, pictures, full mouse support
- **Games**: Zork Zero, Arthur, Shogun

## Specifying Target Version

Use the `<VERSION n>` directive at the start of your ZIL file:

```zil
<VERSION 3>  ; Target V3 (default)
<VERSION 4>  ; Target V4
<VERSION 5>  ; Target V5
<VERSION 6>  ; Target V6
```

## Version-Specific Opcodes

### V3 Opcodes (All Versions)
All basic opcodes work in V3 and higher:
- TELL, PRINT, CRLF, PRINTN, etc.
- COND, REPEAT, AGAIN
- FSET, FCLEAR, FSET?
- GET, PUT, GETB, PUTB
- And 140+ more...

### V5+ Opcodes
These opcodes only work when targeting V5 or higher:
- **COLOR**: Set text colors (foreground/background)
- **FONT**: Set font style
- **MOUSE-INFO**: Get mouse position and button state
- Extended character set support

### V6+ Opcodes
These opcodes only work when targeting V6:
- **PICINF**: Get picture/graphics information
- Graphics display opcodes
- Enhanced window management

## Compatibility Strategy

### Downward Compatibility (V5 → V3)
When you use V5+ opcodes in V3 code, they become **no-ops** (do nothing):

```zil
<VERSION 3>
<ROUTINE GO ()
    <COLOR 2 9>    ; This is a no-op in V3
    <TELL "Text">  ; This works fine
    <QUIT>>
```

This allows you to write V5 source code that compiles for V3 targets, with graceful feature degradation.

### Upward Compatibility (V3 → V5)
All V3 opcodes work perfectly in V5/V6. You can always compile V3 code for higher versions.

## Feature Detection at Runtime

The compiler sets version-specific flags:

```python
self.has_colors = self.version >= 5      # True for V5+
self.has_sound = self.version >= 3       # True for V3+
self.has_mouse = self.version >= 5       # True for V5+
self.has_graphics = self.version >= 6    # True for V6
self.max_objects = 255 (V3) or 65535 (V4+)
self.max_properties = 31 (V3) or 63 (V5+)
```

## Example: Multi-Version Game

```zil
<VERSION 5>

<ROUTINE GO ()
    <TELL "Welcome!" CR>

    ; V5+ only - colors
    <COLOR 2 9>  ; Green on white
    <TELL "This text is colored in V5+" CR>
    <COLOR 1 1>  ; Reset

    ; Works in all versions
    <TELL "This works everywhere" CR>

    <QUIT>>
```

## Current Implementation Status

### V3 Support: ✅ 100% Complete
- All 166 opcodes implemented
- Full Planetfall compatibility
- Production ready

### V4 Support: 🟡 Partial
- Core opcodes working
- Extended memory support ready
- Header generation updated

### V5 Support: 🟡 Partial
- COLOR, FONT now working
- Extended opcodes being added
- Most V3 opcodes work unchanged

### V6 Support: 🔴 Stub Only
- Graphics opcodes stubbed
- PICINF placeholder
- Requires graphics system implementation

## Compilation Examples

```bash
# Compile for V3 (default)
python3 zilc.py game.zil -o game.z3

# Compile for V5 with colors
python3 zilc.py game_v5.zil -o game.z5

# The <VERSION> directive in the .zil file
# determines the target version
```

## Benefits of Multi-Version Support

1. **Forward Compatibility**: V3 games can use V5+ features when available
2. **Graceful Degradation**: V5 code compiles for V3 with features disabled
3. **Single Source**: Write once, target multiple versions
4. **Feature Detection**: Compiler knows what's available per version
5. **Modern Development**: Use latest features while maintaining compatibility

## Future Enhancements

- [ ] Full V4 extended memory support
- [ ] Complete V5 opcode set (~120 opcodes)
- [ ] V6 graphics subsystem
- [ ] V7/V8 support for modern interpreters
- [ ] Automatic version detection from features used
- [ ] Version-specific optimizations

---

**Version**: 2.0.0
**Status**: Multi-Version Support Active
**Last Updated**: 2025-11-16
