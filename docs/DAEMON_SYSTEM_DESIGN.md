# ZIL Daemon/Interrupt System Design

## Overview

ZIL's daemon system allows routines to be scheduled to run automatically at specified intervals during gameplay. This is essential for Planetfall (78+ uses) and other complex Infocom games.

---

## ZIL Syntax

### QUEUE - Create and Schedule Interrupt
```zil
<QUEUE routine-name tick-count>
```

- **routine-name**: Routine to call when interrupt fires
- **tick-count**:
  - Positive number: Fire after N turns, then remove
  - `-1`: Fire every turn (daemon)
  - `0`: Fire immediately next turn

Returns: Interrupt structure/handle

### INT - Access Existing Interrupt
```zil
<INT interrupt-name>
```

Returns the interrupt structure by name (must have been created with QUEUE)

### Common Usage Pattern
```zil
; Schedule Floyd's behavior to run every turn
<ENABLE <QUEUE I-FLOYD -1>>

; Schedule elevator to arrive in 100 turns
<ENABLE <QUEUE I-UPPER-ELEVATOR-ARRIVE 100>>

; Check if interrupt is enabled
<GET <INT I-FLOYD> ,C-ENABLED?>

; Disable an interrupt
<DISABLE <INT I-FLOYD>>
```

---

## Implementation Requirements

### 1. Interrupt Structure Format

Each interrupt is a memory structure containing:

| Offset | Field | Type | Description |
|--------|-------|------|-------------|
| 0 | Routine Address | Word | Packed address of routine to call |
| 2 | Tick Count | Word | Turns remaining (-1 = every turn) |
| 4 | Enabled Flag | Word | 0 = disabled, 1 = enabled |
| 6 | _Reserved_ | Word | For future use |

Total size: **8 bytes per interrupt**

### 2. Global Interrupt Table

```
INTERRUPT-TABLE:
  Word 0: Max interrupt count (e.g., 32)
  Word 1: Current active count
  [Interrupt structures follow...]
```

### 3. Constants Needed

```zil
<CONSTANT C-ENABLED? 4>      ;"Offset to enabled flag in interrupt structure"
<CONSTANT C-TICK 2>          ;"Offset to tick count"
<CONSTANT C-ROUTINE 0>       ;"Offset to routine address"
```

---

## Compilation Strategy

### QUEUE Opcode

When compiling `<QUEUE I-FLOYD -1>`:

1. Allocate space in interrupt table for new interrupt
2. Store routine's packed address at offset 0
3. Store tick count at offset 2
4. Store enabled=1 at offset 4
5. Return address of interrupt structure
6. Add to symbol table for future INT references

Pseudo-Z-machine:
```
; Find free slot in interrupt table
; Allocate 8-byte structure
; Store routine address (packed)
; Store tick count (-1 for daemon)
; Store enabled flag (1)
; Return structure address
```

### INT Opcode

When compiling `<INT I-FLOYD>`:

1. Look up interrupt name in symbol table
2. Return its structure address

Pseudo-Z-machine:
```
; Load address of I-FLOYD interrupt structure
; (Address was saved during QUEUE)
```

---

## Runtime System (CLOCKER)

The game's main loop must call a CLOCKER routine each turn:

```zil
<ROUTINE CLOCKER ()
    "Process all active interrupts"
    <REPEAT ((I 0))
        <COND (<G? .I <GET ,INTERRUPT-TABLE 1>>
               <RETURN>)>

        <COND (<AND <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-ENABLED?>
                    <NOT <ZERO? <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK>>>>

               ; Decrement tick count (unless it's -1)
               <COND (<G? <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK> 0>
                      <PUT <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK
                           <- <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK> 1>>)>

               ; Fire if tick count is 0 or -1
               <COND (<OR <ZERO? <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK>>
                          <EQUAL? <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK> -1>>
                      <CALL <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-ROUTINE>>

                      ; Disable if one-shot (was > 0, now 0)
                      <COND (<ZERO? <GET <+ ,INTERRUPT-TABLE <* .I 8>> ,C-TICK>>
                             <PUT <+ ,INTERRUPT-TABLE <* .I 8>> ,C-ENABLED? 0>)>)>)>

        <SET I <+ .I 1>>>

    <RTRUE>>
```

---

## Integration with Parser

The parser's main loop needs modification:

```zil
<ROUTINE MAIN-LOOP ()
    <REPEAT ()
        <PARSER>
        <CLOCKER>       ;"Process interrupts after each turn"
        ...>>
```

---

## Symbol Table Management

The compiler needs to track interrupt names:

```python
class InterruptInfo:
    def __init__(self, name: str, routine: str, address: int):
        self.name = name           # e.g., "I-FLOYD"
        self.routine = routine     # e.g., "FLOYD-DAEMON"
        self.address = address     # Address of 8-byte structure
```

---

## Z-machine Implementation Notes

### Packed Addresses
Routine addresses must be stored in packed form:
- V3: `packed = byte_address // 2`
- V4/V5: `packed = byte_address // 4`
- V6/V7: `packed = byte_address // 4 + R_O`
- V8: `packed = byte_address // 8`

### Memory Layout
Interrupt table should be in:
- **Static memory** (after globals, before code)
- Allows both read and write operations
- Survives SAVE/RESTORE

### GET/PUT Operations
Access to interrupt fields:
```zil
<GET <INT I-FLOYD> ,C-ENABLED?>     ; Read enabled flag
<PUT <INT I-FLOYD> ,C-ENABLED? 0>   ; Disable interrupt
```

Uses standard LOADW/STOREW with address+offset calculation.

---

## Implementation Phases

### Phase 1: Basic Infrastructure (Current Priority)
- [ ] Add interrupt table to assembler
- [ ] Implement QUEUE opcode (allocate structure, return address)
- [ ] Implement INT opcode (lookup by name)
- [ ] Add interrupt symbol tracking

### Phase 2: Runtime Support
- [ ] Generate CLOCKER routine automatically
- [ ] Integrate CLOCKER into parser main loop
- [ ] Handle packed address calculations

### Phase 3: Advanced Features
- [ ] DEQUEUE opcode (remove interrupt)
- [ ] Interrupt priority levels
- [ ] PAUSE/RESUME operations
- [ ] Debugging support (list active interrupts)

---

## Testing Strategy

### Test 1: Simple Daemon
```zil
<GLOBAL COUNTER 0>

<ROUTINE INCREMENT-COUNTER ()
    <SETG COUNTER <+ ,COUNTER 1>>
    <TELL "Counter: " N ,COUNTER CR>>

<ROUTINE GO ()
    <QUEUE INCREMENT-COUNTER -1>  ;"Run every turn"
    <TELL "Daemon started!" CR>
    <REPEAT ()
        <READ ...>  ;"Each input increments counter">>
```

### Test 2: Timed Event
```zil
<ROUTINE EXPLOSION ()
    <TELL "BOOM! The bomb explodes!" CR>
    <QUIT>>

<ROUTINE GO ()
    <QUEUE EXPLOSION 10>  ;"Explode in 10 turns"
    <TELL "You have 10 turns!" CR>>
```

### Test 3: Enable/Disable
```zil
<ROUTINE GO ()
    <SETG FLOYD-INT <QUEUE I-FLOYD -1>>
    <TELL "Floyd active" CR>

    ...

    <PUT ,FLOYD-INT ,C-ENABLED? 0>  ;"Disable"
    <TELL "Floyd disabled" CR>>
```

---

## Planetfall Requirements

Planetfall uses interrupts for:
- **Floyd's behavior** (I-FLOYD) - 78 uses
- **Elevator movements** (I-UPPER-ELEVATOR-ARRIVE, I-LOWER-ELEVATOR-ARRIVE)
- **Timed events** (I-HUNGER-WARNINGS, I-REACTOR-DOOR-CLOSE)
- **Magnet effects** (I-MAGNET)
- **NPC actions** (I-FLOYD-FORAY, I-CHASE-SCENE)

Total QUEUE calls: ~78
Total INT references: ~45

---

## Current Status

- ❌ Not implemented
- Design documented
- Requires significant compiler infrastructure

---

## Next Steps

1. Add interrupt table generation to assembler
2. Implement basic QUEUE/INT opcodes
3. Create minimal test case
4. Add CLOCKER runtime support

---

**Estimated Complexity**: HIGH (2-3 sessions)
**Priority**: CRITICAL for Planetfall
**Dependencies**: None (self-contained system)
