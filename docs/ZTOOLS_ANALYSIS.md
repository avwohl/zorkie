# Z-Machine Output Analysis Using ztools

## Overview

This document describes issues found by analyzing the compiler's `.z3` output using the official ztools suite from the IF Archive. The analysis compared Infocom's Zork I (Release 119) with the zorkie compiler's output.

## Tools Used

- **txd**: Z-machine disassembler (V1-V8)
- **infodump**: Extracts header, objects, grammar, dictionary
- **check**: Verifies story file integrity

Source: https://ifarchive.org/indexes/if-archive/infocom/tools/ztools/

## Test Files

| File | Description | Size |
|------|-------------|------|
| `COMPILED/zork1.z3` | Original Infocom Release 119 | 86,838 bytes |
| `zork1.z3` | zorkie compiler output | 70,974 bytes |

## Header Comparison

| Field | Infocom | zorkie | Notes |
|-------|---------|--------|-------|
| Version | 3 | 3 | OK |
| High memory | 0x4B54 | 0x4820 | Different layout |
| Initial PC | 0x50D5 | 0x4823 | Different layout |
| Dictionary | 0x3899 | 0x2C82 | Different layout |
| Object table | 0x03E6 | 0x04EC | Different layout |
| Globals | 0x02B0 | 0x0040 | **Issue #4** |
| Static memory | 0x2C12 | 0x4820 | **Issue #2** |
| Abbreviations | 0x01F0 | 0x0220 | Different layout |
| Dict end | 0x4B54 | 0x3EF2 | **Issue #3** |
| Dict words | 684 | 672 | Minor difference |

## Issues Found

### Issue #1: Unresolved Routine Placeholders (Critical)

**Symptom**: txd fails with "game file read error"

**Location**: 0x46F8 - 0x481E (ACTIONS table area)

**Details**:
The ACTIONS table contains 149 unresolved `0xFD` + index placeholder pairs that were never converted to routine addresses:

```
0x46f8: 0xFD 8C (placeholder index 140)
0x46fa: 0xFD 8D (placeholder index 141)
0x46fc: 0xFD 8E (placeholder index 142)
... (149 total)
```

These get interpreted as word values like `0xFD8C`, which when treated as packed routine addresses point to byte address `0x1FB18` - far beyond the file size.

**Cause**: In `codegen_improved.py:280-287`, `get_table_routine_fixups()` only generates fixups when the routine name exists in `self.routines`. If the routine wasn't compiled or has a different name, the placeholder remains unresolved.

**Code location**: `zilc/codegen/codegen_improved.py:265-290`

```python
def get_table_routine_fixups(self) -> List[Tuple[int, int]]:
    for i in range(0x3EF2, 0x4820 - 1):
        if table_data[i] == 0xFD:
            placeholder_idx = table_data[i + 1]
            if placeholder_idx in self._routine_placeholders:
                routine_name = self._routine_placeholders[placeholder_idx]
                if routine_name in self.routines:  # <-- Missing routines skip fixup!
                    routine_offset = self.routines[routine_name]
                    fixups.append((i, routine_offset))
```

### Issue #2: static_mem == high_mem (Spec Violation)

**Symptom**: Violates Z-Machine specification

**Values**:
- zorkie: `static_mem = high_mem = 0x4820`
- Infocom: `static_mem = 0x2C12`, `high_mem = 0x4B54`

**Z-Machine Spec Requirement**: Static memory base must be less than high memory base. Memory layout should be:
1. Dynamic memory: 0x00 to static_mem-1 (read/write, saved in save files)
2. Static memory: static_mem to high_mem-1 (read-only strings/tables)
3. High memory: high_mem onward (code, read-only)

**Cause**: In `assembler.py:493`:
```python
struct.pack_into('>H', story, 0x0E, current_addr)  # Static memory base
```
At this point, `current_addr` equals `high_mem_base` because table_data was just added.

**Code location**: `zilc/zmachine/assembler.py:493`

### Issue #3: Gap Between Dictionary and Code

**Symptom**: Non-standard memory layout

**Details**:
- zorkie: Dictionary ends at 0x3EF2, code starts at 0x4820 (gap: 0x92E = 2,350 bytes)
- Infocom: Dictionary end = high_mem = 0x4B54 (no gap)

The gap contains:
- Sparse data at 0x3EF2-0x41CF (mostly zeros with few values)
- ACTIONS/PREACTIONS table data at 0x41D0-0x46F7
- Unresolved routine placeholders at 0x46F8-0x481E

**Impact**: txd assumes code starts at dictionary end, so it tries to disassemble table data as code.

### Issue #4: Globals at 0x40 (Unusual)

**Symptom**: Works but non-standard layout

**Values**:
- zorkie: Globals at 0x0040 (immediately after 64-byte header)
- Infocom: Globals at 0x02B0

**Notes**: Infocom's layout puts abbreviation strings first (0x40-0x1EF), then abbreviation pointers (0x1F0-0x2AF), then globals (0x2B0+). The zorkie layout may work but differs from standard.

### Issue #5: Dictionary Entry Data Format

**Symptom**: Different data byte format

**Infocom entry example** (word "about"):
```
18f4eb25 08ee00
         ^^ flags: 0x08
           ^^ data: 0xEE (verb index, etc.)
             ^^ reserved: 0x00
```

**zorkie entry example** (word "about"):
```
18f4eb25 000000
         ^^^^^^ all zeros - no flags/verb info
```

**Impact**: Parser won't recognize verbs properly.

## Memory Layout Comparison

### Infocom Layout
```
0x0000 - 0x003F  Header (64 bytes)
0x0040 - 0x01EF  Abbreviation strings
0x01F0 - 0x02AF  Abbreviation pointers (96 entries)
0x02B0 - 0x048F  Global variables (240 words)
0x03E6 - 0x0CED  Object table + property defaults
0x0CEE - 0x23AD  Property data
0x23AE - 0x2C11  (gap/padding)
0x2C12 - 0x3898  Grammar/action tables (static memory)
0x3899 - 0x4B53  Dictionary
0x4B54 - 0x15335 Code (high memory)
```

### zorkie Layout
```
0x0000 - 0x003F  Header (64 bytes)
0x0040 - 0x021F  Global variables (immediately after header!)
0x0220 - 0x02DF  Abbreviation pointers
0x02E0 - 0x04EB  Abbreviation strings
0x04EC - 0x0DF3  Object table
0x0DF4 - 0x2C81  Property data
0x2C82 - 0x3EF1  Dictionary
0x3EF2 - 0x481F  Tables/gap (contains unresolved placeholders)
0x4820 - 0x1153D Code (high memory = static memory!)
```

## Recommended Fixes

### Fix #1: Resolve or Zero Unresolved Placeholders

In `codegen_improved.py`, when a routine isn't found:
- Log a warning with the missing routine name
- Use 0x0000 as a safe fallback address

```python
def get_table_routine_fixups(self):
    # ... existing code ...
    if routine_name in self.routines:
        routine_offset = self.routines[routine_name]
        fixups.append((i, routine_offset))
    else:
        # Warn and add zero fixup
        print(f"Warning: Routine '{routine_name}' not found for ACTIONS table")
        fixups.append((i, 0))  # Will become 0x0000 after packing
```

### Fix #2: Correct static_mem Calculation

In `assembler.py`, track static memory start before adding tables:

```python
# Before adding table_data (around line 382):
static_mem_base = current_addr  # This is where static memory begins

# Add table data
if table_data:
    story.extend(table_data)
    current_addr += len(table_data)
    # ... alignment ...

# Mark start of high memory
self.high_mem_base = len(story)

# Later, when updating header (line 493):
struct.pack_into('>H', story, 0x0E, static_mem_base)  # Use saved value
```

### Fix #3: Investigate Missing Routines

The ACTIONS table references routines that don't exist in `self.routines`. Need to determine:
1. Are the routine names correct in the SYNTAX definitions?
2. Are all action routines being compiled?
3. Is there a naming mismatch (e.g., `V-TAKE` vs `TAKE-ACTION`)?

### Fix #4: Dictionary Verb Flags

Ensure dictionary entries have proper flags set for verbs/adjectives/nouns. Compare with Infocom's format:
- Byte 4: Flags (0x08 for verbs, etc.)
- Byte 5: Data (verb table index for verbs)
- Byte 6: Reserved/additional

## Testing

After fixes, verify with:
```bash
# Check file integrity
./tools/ztools/ztools731a/check output.z3

# Dump header info
./tools/ztools/ztools731a/infodump output.z3

# Try disassembly
./tools/ztools/ztools731a/txd output.z3

# Dump objects
./tools/ztools/ztools731a/infodump -o output.z3

# Dump grammar (will fail until placeholders fixed)
./tools/ztools/ztools731a/infodump -g output.z3
```

## Fixes Applied

### Fix #1: static_mem Calculation (Done)
In `assembler.py`, the static memory base is now saved before table data is added:
```python
self.static_mem_base = current_addr  # Save for header before adding tables
```

### Fix #2: Routine Placeholder Resolution (Done)
Modified `codegen_improved.py` to track missing routines and use offset 0 for them:
```python
if routine_name in self.routines:
    routine_offset = self.routines[routine_name]
    fixups.append((i, routine_offset))
else:
    self._missing_routines.add(routine_name)
    fixups.append((i, 0))  # Will become 0x0000
```

### Fix #3: GO Routine Ordering (Done)
Modified `codegen_improved.py` to ensure GO routine is generated first:
```python
# Generate routines - GO must be first as it's the entry point
go_routine = None
other_routines = []
for routine_node in program.routines:
    if routine_node.name == 'GO':
        go_routine = routine_node
    else:
        other_routines.append(routine_node)

routines_to_generate = []
if go_routine:
    routines_to_generate.append(go_routine)
routines_to_generate.extend(other_routines)
```

### Fix #4: ENABLE/QUEUE Library Routine Support (Done)
Modified `codegen_improved.py` to check for user-defined routines before using
built-in implementations. The built-in implementations store data in static
memory which cannot be modified at runtime - games should use library routines
(like gclock.zil or events.zil) instead:
```python
elif op_name == 'QUEUE':
    if 'QUEUE' in self.routines:
        return self.gen_routine_call('QUEUE', form.operands)
    return self.gen_queue(form.operands)
```
Built-in implementations now emit warnings when used.

### Fix #5: Dictionary Verb/Preposition Flags (Done)
Fixed `dictionary.py` to accept both long and short form word types:
- 'preposition' and 'prep' both set the preposition flag (0x08)
- 'adjective' and 'adj' both set the adjective flag (0x20)
- 'direction' and 'dir' both set the direction flag (0x10)

The compiler was using 'prep' but the dictionary only checked for 'preposition'.

## Remaining Issues

### Issue: Grammar Table Format
txd expects Infocom-style grammar/verb tables at the start of static memory.
Our compiler puts arbitrary table data there instead. This causes txd to fail
when trying to parse grammar tables.

**Workaround**: Use `txd -g` to disable grammar table parsing.

## Files Modified

- `zilc/zmachine/assembler.py` - static_mem fix
- `zilc/codegen/codegen_improved.py` - placeholder resolution fix, GO ordering, QUEUE/ENABLE library support
- `zilc/compiler.py` - missing routine logging
- `zilc/zmachine/dictionary.py` - word type flag fixes

## References

- Z-Machine Standards Document: https://inform-fiction.org/zmachine/standards/
- ztools source: https://ifarchive.org/if-archive/infocom/tools/ztools/ztools731a.zip
