# Z-Machine Test Games

This directory contains example Z-machine story files for testing different versions.

## Downloaded Games

### Version 3 (V3) - 128KB limit
**File**: `advent.z3` (65KB)
- **Game**: Adventure (Colossal Cave)
- **Compiler**: ZAPF (ZIL Assembler/Parser/Formatter)
- **Release**: 1, Serial: 151001
- **Source**: https://www.ifarchive.org/if-archive/games/zcode/advent.z3
- **Use**: Testing V3 compilation and compatibility

### Version 5 (V5) - 256KB limit
**File**: `Aisle.z5` (120KB)
- **Game**: Aisle by Sam Barlow
- **Compiler**: Inform
- **Source**: https://www.ifarchive.org/if-archive/games/zcode/Aisle.z5
- **Use**: Testing V5 features (color, sound, undo)

**File**: `curses.z5` (253KB)
- **Game**: Curses by Graham Nelson
- **Release**: 16, Serial: 951024
- **Compiler**: Inform
- **Source**: https://www.ifarchive.org/if-archive/games/zcode/curses.z5
- **Use**: Testing V5 with larger file size (near 256KB limit)

### Version 8 (V8) - 512KB limit
**File**: `anchor.z8` (508KB)
- **Game**: Anchorhead by Michael S. Gentry
- **Release**: 5, Serial: 990206
- **Compiler**: Inform 6.15
- **File size**: 520,192 bytes (uses 512KB limit)
- **Source**: https://www.ifarchive.org/if-archive/games/zcode/anchor.z8
- **Features**: Supports undo, header extension
- **Use**: Testing V8 packed addressing and large file support

## Missing Versions

### Version 1 (V1)
- **Extremely rare**: Only early Zork I releases
- **Source**: `eblong.com/infocom/` has recovered .z1 files from TRS-80 disks
- **Status**: Not downloaded (hard to find working .z1 files)

### Version 2 (V2)
- **Very rare**: Early Infocom games
- **Status**: Not downloaded

### Version 4 (V4)
- **Games**: Trinity, A Mind Forever Voyaging, Bureaucracy
- **File extension**: .z4
- **Status**: Download attempts failed (redirects)
- **Note**: Can find at `eblong.com/infocom/gamefiles/`

### Version 6 (V6)
- **Games**: Zork Zero, Journey, Shogun, Arthur
- **Features**: Graphics, requires separate image files
- **Status**: Download attempts failed
- **Note**: .z6 files don't include image assets

### Version 7 (V7)
- **Status**: Almost no games exist
- **Reason**: V8 made V7 obsolete
- **Recommendation**: Skip testing V7

## Testing with Infodump

```bash
# Check version and header
./ztools731a/infodump games/test_games/advent.z3

# Dump dictionary
./ztools731a/infodump -d games/test_games/advent.z3

# Dump object tree
./ztools731a/infodump -o games/test_games/advent.z3
```

## Testing with Interpreters

### Frotz (Recommended)
```bash
frotz games/test_games/advent.z3
```

### Our Interpreter (Future)
```bash
# When implemented:
python3 -m zorkie.interpreter games/test_games/advent.z3
```

## Version Comparison

| Version | File | Size | Features | Packed Addr |
|---------|------|------|----------|-------------|
| V3 | advent.z3 | 65KB | Basic | 2P |
| V5 | Aisle.z5 | 120KB | Color, sound, undo | 4P |
| V5 | curses.z5 | 253KB | Near size limit | 4P |
| V8 | anchor.z8 | 508KB | Large games | 8P |

## File Size Limits by Version

- V1-V3: 128KB maximum
- V4-V5: 256KB maximum
- V6: 256KB maximum (graphics)
- V7: 512KB maximum (rarely used)
- V8: 512KB maximum (modern standard)

## Downloading More Games

### IF Archive (Main source)
```bash
# Browse available games
curl https://www.ifarchive.org/indexes/if-archive/games/zcode/

# Download specific game
curl -L -O https://www.ifarchive.org/if-archive/games/zcode/GAMENAME.zX
```

### Infocom Catalog
- URL: https://eblong.com/infocom/
- Contains official Infocom releases
- Has rare V1/V2 files
- Includes source code for some games

### IF Archive Categories
- V3 games: `if-archive/games/zcode/*.z3`
- V5 games: `if-archive/games/zcode/*.z5`
- V8 games: `if-archive/games/zcode/*.z8`
- Infocom games: `if-archive/infocom/gamefiles/`

## Playing Games

All files can be played with standard Z-machine interpreters:
- **Frotz**: Most popular, supports V1-V8
- **Nitfol**: Supports V1-V8
- **Gargoyle**: Multi-format interpreter
- **Parchment**: Browser-based (JavaScript)

## Using for Testing

### Test V3 Compatibility
```bash
python3 -m zilc.compiler test_v3_code.zil -v 3 -o test.z3
./ztools731a/infodump test.z3
frotz test.z3
```

### Test V5 Features
```bash
python3 -m zilc.compiler test_v5_code.zil -v 5 -o test.z5
./ztools731a/infodump test.z5
frotz test.z5
```

### Test V8 (When implemented)
```bash
python3 -m zilc.compiler test_v8_code.zil -v 8 -o test.z8
./ztools731a/infodump test.z8
frotz test.z8
```

## References

- IF Archive: https://www.ifarchive.org/
- Infocom Catalog: https://eblong.com/infocom/
- Z-Machine Spec: https://inform-fiction.org/zmachine/standards/z1point1/
- IFDB (game database): https://ifdb.org/

---
**Last Updated**: 2025-11-16
