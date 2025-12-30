# Instructions for Claude Code

## Work Focus

**IMPORTANT:** Only work on tests pointed to by `todo.txt`. This means:
- Focus on ZILF integration tests (`tests/zilf/`)
- Focus on ZILF interpreter tests
- Do NOT debug Infocom games (Zork1, Zork2, Zork3, Enchanter, etc.)
- Do NOT investigate game runtime hangs or gameplay issues
- If a test needs a game to compile, that's fine, but don't go down rabbit holes debugging game behavior

## Tone and Reporting Style

### DO NOT:
- ❌ Use excessive celebratory language ("🎉", "AMAZING!", "HISTORIC!", etc.)
- ❌ Say things are "complete" or "done" unless they truly are
- ❌ Use superlatives like "exceptional", "outstanding", "incredible"
- ❌ Make it sound like we've reached the end when there's more work
- ❌ Celebrate minor progress as major achievements

### DO:
- ✅ Be matter-of-fact and technical
- ✅ Focus on what's implemented vs. what remains
- ✅ End each session summary with "What's Left" section
- ✅ Be honest about completion percentages
- ✅ Use professional, not promotional language

## Required Session Summary Format

Every session summary or status report MUST include:

### 1. What Was Added
- List what was implemented (brief, factual)

### 2. Current Statistics
- Total opcodes: X working / Y stubs / Z total
- Version support status (V3/V4/V5/V6)

### 3. **WHAT'S LEFT** ⬅️ REQUIRED SECTION
Always include a clear "What's Left" section showing:
- Missing V3 opcodes (if any)
- Missing V4 opcodes (count + examples)
- Missing V5 opcodes (count + examples)
- Missing V6 opcodes (count + examples)
- Known bugs or limitations
- Features that don't fully work

Example:
```
## What's Left

### V3: Complete ✓

### V4: ~15 opcodes remaining
- Extended save/restore variants
- Enhanced memory operations
- Example: SAVE_UNDO, RESTORE_UNDO

### V5: ~20 opcodes remaining
- CALL_VS2, CALL_VN2 (extended calls)
- TOKENISE (text parsing)
- ENCODE_TEXT
- COPY_TABLE
- PRINT_TABLE
- CHECK_ARG_COUNT
- etc.

### V6: ~40 opcodes remaining
- All graphics opcodes (DRAW_PICTURE, etc.)
- Enhanced window management
- Mouse handling beyond stubs
- Picture table operations

### Known Issues:
- COPYT, ZERO need loop generation
- MEMBER, MEMQ need search loops
- XOR needs V3 emulation
- STRING interpolation (!,VAR) not implemented
```

## Commit Messages

- Keep factual and technical
- No emoji unless specifically appropriate (version tags, etc.)
- Focus on what changed, not how "amazing" it is

## Progress Reporting

When reporting percentage complete:
- Be specific about WHAT is X% complete
- "100% of V3 Planetfall opcodes" not "100% complete!"
- Always clarify the scope

## Version Status Indicators

Use these consistently:
- ✅ Complete (truly 100% implemented and tested)
- 🟢 Working (functional but may lack some features)
- 🟡 Partial (significant gaps remain)
- 🔴 Stub/Minimal (mostly placeholders)
- ❌ Not Implemented

## Goal

Make progress reports useful for understanding:
1. What actually works
2. What doesn't work yet
3. How much work remains
4. What needs to be done next

The user should never be surprised to learn something isn't finished.
