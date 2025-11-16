# Z-Machine Games Organized by Version

## Overview

This document lists notable Z-machine games organized by version, with download information and technical details.

## Version 1 (.z1) - 1979-1981

**Created**: Infocom
**Max Size**: 128KB
**Packed Address**: 2P
**Status**: Extremely rare

### Known V1 Games
- **Zork I** (early TRS-80 releases)
  - Original "Zork" before trilogy split
  - Released by Personal Software (1980)
  - Recovered from TRS-80 disk images

### Where to Find
- **eblong.com/infocom/** - Obsessively Complete Infocom Catalog
  - Has recovered .z1 files from TRS-80 disks
  - Very few known .z1 files exist
- **github.com/jeffnyman/zifmia** - Contains `zork.z1`

### Technical Notes
- Only 2-3 V1 files known to exist
- Early Z-machine, permanent alphabet shifts
- Historical interest only

---

## Version 2 (.z2) - 1980-1981

**Created**: Infocom
**Max Size**: 128KB
**Packed Address**: 2P
**Status**: Very rare

### Known V2 Games
- Early Zork releases
- Some early Infocom games

### Where to Find
- **eblong.com/infocom/** - Has some recovered .z2 files

### Technical Notes
- Added abbreviations table
- Still rare, mostly historical

---

## Version 3 (.z3) - 1982-1988

**Created**: Infocom
**Max Size**: 128KB
**Packed Address**: 2P
**Status**: Most common classic format

### Notable V3 Games

#### Classic Infocom Games
- **Zork I, II, III** - The Zork trilogy
- **Planetfall** - Science fiction comedy
- **Hitchhiker's Guide to the Galaxy** - Douglas Adams collaboration
- **Deadline** - Mystery game
- **Starcross** - Science fiction
- **Enchanter** - Magic-based adventure
- **Sorcerer** - Enchanter sequel
- **Spellbreaker** - Enchanter trilogy finale
- **Suspended** - Control robots
- **Infidel** - Egyptian pyramid exploration
- **Cutthroats** - Undersea treasure hunting
- **The Witness** - Murder mystery
- **Moonmist** - Gothic mystery

#### Modern V3 Games (IF Archive)
- **advent.z3** - Colossal Cave Adventure port
- **catseye.z3** - Cat's Eye, Miniventure #2
- **buccaneers_cache.z3** - Buccaneer's Cache
- **DuckMe.z3** - Fowl Play Adventure 1
- **minizork.z3** - Mini Zork demo

### Where to Download

#### IF Archive
```
https://www.ifarchive.org/if-archive/games/zcode/*.z3
```

#### Infocom Catalog
```
https://eblong.com/infocom/gamefiles/
```
Examples:
- `zork1-r88-s840726.z3` - Zork I Release 88
- `hhgg-r59-s860921.z3` - Hitchhiker's Guide
- `planet-r37-s851003.z3` - Planetfall Release 37

### Technical Features
- 255 objects maximum
- 32 attributes
- Temporary alphabet shifts
- Standard Infocom feature set
- Most compatible version

---

## Version 4 (.z4) - 1984-1988

**Created**: Infocom
**Max Size**: 256KB
**Packed Address**: 4P
**Status**: Less common than V3/V5

### Notable V4 Games
- **Trinity** - Post-nuclear war adventure
- **A Mind Forever Voyaging** - Dystopian simulation
- **Bureaucracy** - Douglas Adams satire
- **Nord and Bert** - Wordplay puzzles

### Where to Download

#### IF Archive
```
https://www.ifarchive.org/if-archive/infocom/gamefiles/
```
Examples:
- `trinity-r11-s860509.z4`
- `amfv-r77-s851202.z4` - A Mind Forever Voyaging
- `bureaucracy-r116-s870602.z4`

### Technical Features
- 65,535 objects maximum
- 48 attributes
- Timed input
- Fixed-pitch font control
- Enhanced status line

---

## Version 5 (.z5) - 1986-1988

**Created**: Infocom
**Max Size**: 256KB
**Packed Address**: 4P
**Status**: Very common, modern IF standard

### Notable V5 Games

#### Infocom Games
- **Beyond Zork** - RPG elements
- **Border Zone** - Real-time espionage
- **Sherlock** - Sherlock Holmes mystery
- **Zork: The Undiscovered Underground** - Free Zork game

#### Modern IF Games (IF Archive)
- **Aisle.z5** - Sam Barlow's one-room game
- **AllRoads.z5** - 2001 IF Competition winner
- **Balances.z5** - Graham Nelson
- **Curses.z5** - Graham Nelson (large, 253KB)
- **Edifice.z5** - 1997 IF Competition winner
- **booth.z5** - Pick Up the Phone Booth and Die
- **jigsaw.z5** - Graham Nelson
- **advent.z5** - Adventure port

### Where to Download

#### IF Archive (Hundreds of V5 games)
```
https://www.ifarchive.org/if-archive/games/zcode/*.z5
```

Popular downloads:
- `Aisle.z5` - Innovative one-room game
- `curses.z5` - Classic large adventure
- `photopia.z5` - Award winner
- `Slouching.z5` - Modern IF

### Technical Features
- Color support
- Sound effects
- Undo capability
- Custom alphabet tables
- Extended character set
- Mouse support (V5+)

---

## Version 6 (.z6) - 1988-1989

**Created**: Infocom
**Max Size**: 256KB
**Packed Address**: 4P + offset
**Status**: Rare, requires graphics

### Notable V6 Games
- **Zork Zero** - Prequel with graphics
- **Journey** - Graphics adventure
- **Shogun** - Japanese historical adventure
- **Arthur** - King Arthur legend

### Where to Download

#### Infocom Catalog
```
https://eblong.com/infocom/gamefiles/
```
Examples:
- `zork0-r393-s881019.z6` - Zork Zero
- `arthur-r74-s890714.z6` - Arthur

**IMPORTANT**: V6 files do NOT include graphics data
- Requires separate .mg1 or .blb files
- Graphics must be extracted from original disks
- Few interpreters fully support V6 graphics

### Technical Features
- Graphics support (draw_picture, etc.)
- Mouse input
- Proportional fonts
- Multiple windows
- Advanced display control
- Pictures and complex layouts

### Technical Challenges
- Packed addressing uses offsets (4P + 8×R_O)
- Requires routines offset (header $28)
- Requires strings offset (header $2A)
- Graphics handling complex

---

## Version 7 (.z7) - 1995

**Created**: Graham Nelson (not Infocom)
**Max Size**: 512KB
**Packed Address**: 4P + offset
**Status**: Almost never used

### Known V7 Games
- **Almost none exist**
- Version was quickly superseded by V8

### Why V7 Failed
- More complex than V8 (offset-based addressing)
- Poor interpreter support
- V8 released shortly after with simpler design
- No compelling reason to use V7 over V8

### Recommendation
**Skip V7 entirely** - Not worth implementing or testing

---

## Version 8 (.z8) - 1995

**Created**: Graham Nelson (not Infocom)
**Max Size**: 512KB
**Packed Address**: 8P
**Status**: Modern standard for large games

### Notable V8 Games

#### Popular V8 Games
- **Anchorhead.z8** - Michael S. Gentry (508KB)
- **Acheton.z8** - Cambridge adventure
- **advent.z8** - Adventure (Knuth CWEB version)
- **castle.z8** - Castle Adventure
- **dracula.z8** - Dracula: Prince of Darkness
- **dreamhold.z8** - Andrew Plotkin
- **LostPig.z8** - Admiral Jota (IF Competition winner)
- **Photopia.z8** - Adam Cadre
- **varicella.z8** - Adam Cadre

### Where to Download

#### IF Archive (Many V8 games)
```
https://www.ifarchive.org/if-archive/games/zcode/*.z8
```

Popular large games:
- `anchor.z8` - Anchorhead (520KB)
- `Christminster.z8` - Gareth Rees
- `mulldoon.z8` - Mulldon Legacy

### Technical Features
- Functionally identical to V5
- Same opcodes as V5
- Simpler packed addressing (8P)
- Simpler file length calculation (÷8)
- No offset headers needed
- Better interpreter support than V7

### Why V8 Succeeded
- **Simplicity**: Just multiply packed address by 8
- **Compatibility**: All V5 interpreters can support V8 easily
- **Size**: Allows games up to 512KB
- **Modern standard**: Used by Inform for large games

---

## Summary Table

| Version | Years | Creator | Max Size | Games | Availability | Status |
|---------|-------|---------|----------|-------|--------------|--------|
| V1 | 1979-81 | Infocom | 128KB | ~2-3 | Extremely rare | Historical |
| V2 | 1980-81 | Infocom | 128KB | ~5 | Very rare | Historical |
| **V3** | 1982-88 | Infocom | 128KB | **100+** | **Excellent** | **Standard** |
| V4 | 1984-88 | Infocom | 256KB | ~10 | Good | Uncommon |
| **V5** | 1986-88+ | Infocom | 256KB | **500+** | **Excellent** | **Standard** |
| V6 | 1988-89 | Infocom | 256KB | ~5 | Rare | Graphics |
| V7 | 1995 | G. Nelson | 512KB | ~0 | None | Obsolete |
| **V8** | 1995+ | G. Nelson | 512KB | **300+** | **Excellent** | **Modern** |

## Recommended Test Games

### For V3 Testing
1. **advent.z3** - Small (65KB), simple, good baseline
2. **minizork.z3** - Infocom demo, authentic
3. **hhgg.z3** - Classic Infocom, complex parser

### For V5 Testing
1. **Aisle.z5** - Small (120KB), modern, innovative
2. **curses.z5** - Large (253KB), tests size limits
3. **photopia.z5** - Award-winning, good feature coverage

### For V8 Testing
1. **anchor.z8** - Large (508KB), tests V8 addressing
2. **dreamhold.z8** - Modern, tutorial elements
3. **LostPig.z8** - Award winner, good example

## Download Commands

### Quick Download Set
```bash
# V3 examples
curl -L -O https://www.ifarchive.org/if-archive/games/zcode/advent.z3
curl -L -O https://www.ifarchive.org/if-archive/infocom/demos/minizork.z3

# V5 examples
curl -L -O https://www.ifarchive.org/if-archive/games/zcode/Aisle.z5
curl -L -O https://www.ifarchive.org/if-archive/games/zcode/curses.z5

# V8 examples
curl -L -O https://www.ifarchive.org/if-archive/games/zcode/anchor.z8
curl -L -O https://www.ifarchive.org/if-archive/games/zcode/dreamhold.z8
```

### Bulk Downloads
```bash
# Download Infocom catalog (all official games)
curl -L https://eblong.com/infocom/allgamefiles.zip -o infocom_games.zip

# Download all IF Archive zcode
# (Warning: Large - 801 files)
wget -r -np -nd -A "*.z*" https://www.ifarchive.org/if-archive/games/zcode/
```

## Resources

### Game Archives
- **IF Archive**: https://www.ifarchive.org/indexes/if-archive/games/zcode/
- **Infocom Catalog**: https://eblong.com/infocom/
- **IFDB**: https://ifdb.org/ (searchable database)

### Interpreters
- **Frotz**: Most popular, V1-V8 support
- **Gargoyle**: Multi-format, nice UI
- **Parchment**: Browser-based
- **Lectrote**: Electron-based, modern

### Tools
- **Infodump**: Analyze story files
- **Txd**: Disassembler
- **ZTools**: Suite of utilities

---
**Last Updated**: 2025-11-16
**Test Files**: See `/games/test_games/` for downloaded examples
