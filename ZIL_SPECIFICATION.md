# ZIL (Zork Implementation Language) Specification

## 1. Introduction

### 1.1 Overview
ZIL (Zork Implementation Language) is a programming language developed by Infocom in the late 1970s for creating interactive fiction games. It is based on MDL (Muddle), itself a dialect of LISP created by MIT students and staff. ZIL was specifically designed to compile to Z-machine bytecode for cross-platform interactive fiction execution.

### 1.2 Historical Context
- **Original Development**: Late 1970s - early 1980s at Infocom
- **Purpose**: Create text adventure games that could run on multiple platforms
- **Compiler**: ZILCH (written in MDL, ran on TOPS-20 mainframes)
- **Modern Alternative**: ZILF (ZIL Implementation of the Future) - open-source C# compiler

### 1.3 Compilation Pipeline

**Traditional (Infocom):**
```
ZIL source → ZILCH compiler → ZAP assembly → ZAP assembler → Z-code (.z3, .z4, .z5, etc.)
```

**Modern (ZILF):**
```
ZIL source → ZILF compiler → ZAP assembly → ZAPF assembler → Z-code
```

## 2. Language Fundamentals

### 2.1 Syntax Overview
ZIL uses LISP-style S-expression syntax with angle brackets instead of parentheses for most constructs:

```zil
<FUNCTION-NAME arg1 arg2 arg3>
```

### 2.2 Comments
```zil
;"This is a comment"
```

### 2.3 Truth Values
- **True**: `T`
- **False**: `<>` (empty angle brackets)

### 2.4 Data Types

#### 2.4.1 Primitive Types
- **FIX**: Fixed-point integers (16-bit signed in Z-machine)
- **ATOM**: Symbolic names/identifiers
- **STRING**: Text strings in double quotes
- **TABLE**: Arrays of data
- **VECTOR**: Dynamic arrays
- **ROUTINE**: Executable code blocks
- **OBJECT**: Game world entities
- **ROOM**: Special object type for locations

#### 2.4.2 Type Declarations
ZIL supports compile-time type declarations for optimization:

```zil
#DECL ((VILLAIN) OBJECT
       (WV) <OR FALSE VECTOR>
       (OD VALUE) FIX)
```

### 2.5 Variable Types and Naming Conventions

#### 2.5.1 Variable Prefixes
- **`.VAR`**: Local variable reference
- **`,VAR`**: Global variable reference
- **`VAR`**: Atom (unbound symbol)

#### 2.5.2 Local Variables
Created with `SET`, scoped to current routine:

```zil
<SET VAR value>
```

#### 2.5.3 Global Variables
Created with `SETG`, accessible throughout the program:

```zil
<SETG VAR value>
```

#### 2.5.4 Auxiliary Variables
Declared in routine definitions after `"AUX"`:

```zil
<ROUTINE NAME (PARAM1 PARAM2 "AUX" LOCAL1 LOCAL2)
    ...>
```

## 3. Routines (Functions)

### 3.1 Basic Routine Definition

```zil
<ROUTINE routine-name (parameters "AUX" local-vars)
    <instruction1>
    <instruction2>
    ...
    <return-value>>
```

### 3.2 Parameters
- Parameters are passed by value
- Listed in parentheses after routine name
- Auxiliary variables (after `"AUX"`) are local-only, never passed

### 3.3 Return Values
- The last expression evaluated is returned
- Explicit return: `<RTRUE>` returns true, `<RFALSE>` returns false

### 3.4 Entry Point
Every ZIL program must define a `GO` routine as the entry point:

```zil
<ROUTINE GO ()
    <CRLF>
    <TELL "Welcome to the game!" CR>
    <V-VERSION>
    <MAIN-LOOP>>
```

### 3.5 Routine Calls

```zil
<ROUTINE-NAME arg1 arg2 arg3>
```

## 4. Control Flow

### 4.1 Conditional: COND

```zil
<COND (<condition1> <action1>)
      (<condition2> <action2>)
      (<condition3> <action3>)
      (T <default-action>)>
```

The `T` clause acts as "else" - always evaluates to true.

### 4.2 Logical Operators

#### AND
```zil
<AND <condition1> <condition2> <condition3>>
```
Returns false on first false condition, otherwise returns last value.

#### OR
```zil
<OR <condition1> <condition2> <condition3>>
```
Returns first true value, or false if all are false.

#### NOT
```zil
<NOT <condition>>
```

### 4.3 Loops

#### REPEAT
```zil
<REPEAT ()
    <action1>
    <COND (<exit-condition> <RETURN value>)>
    <action2>>
```

#### MAPF/MAPR (Compile-time only)
For processing lists during compilation.

## 5. Objects and Rooms

### 5.1 Object Definition

```zil
<OBJECT object-name
    (IN container-object)
    (SYNONYM word1 word2 word3)
    (ADJECTIVE adj1 adj2)
    (DESC "description string")
    (LDESC "Long description when examined")
    (FLAGS flag1 flag2 flag3)
    (property1 value1)
    (property2 value2)
    (ACTION object-routine)>
```

### 5.2 Standard Object Properties

- **IN/LOC**: Container location
- **DESC**: Parser reference string (unchangeable at runtime)
- **LDESC**: Long description for room listings
- **SYNONYM**: Noun references for parser
- **ADJECTIVE**: Adjective modifiers for parser
- **FLAGS**: Boolean capability bits
- **ACTION**: Routine to handle object interactions
- **SIZE**: Physical size
- **CAPACITY**: Container capacity
- **VALUE**: Numerical value

### 5.3 Standard Flags

Common object flags:
- **TAKEBIT**: Object can be taken
- **LIGHTBIT**: Object provides light
- **ONBIT**: Object is turned on
- **OPENBIT**: Container is open
- **CONTBIT**: Object is a container
- **TRANSBIT**: Container is transparent
- **INVISIBLE**: Object not visible
- **TOUCHBIT**: Object has been touched
- **NDESCBIT**: Don't describe in room listings

### 5.4 Flag Operations

```zil
<FSET object flag>        ;"Set flag"
<FCLEAR object flag>      ;"Clear flag"
<FSET? object flag>       ;"Test flag (returns true/false)"
```

### 5.5 Room Definition

Rooms are objects with directional exits:

```zil
<ROOM room-name
    (DESC "Room Name")
    (LDESC "Long room description.")
    (IN ROOMS)
    (FLAGS LIGHTBIT)
    (NORTH TO north-room)
    (SOUTH PER south-routine)
    (EAST SORRY "You can't go that way.")
    (WEST TO west-room IF flag-condition)
    (ACTION room-routine)>
```

### 5.6 Exit Types

- **TO room**: Direct connection
- **PER routine**: Conditional via routine return value
- **SORRY "text"**: Blocked with message
- **TO room IF condition**: Conditional access

### 5.7 Room Action Messages

Room routines can handle special events:
- **M-LOOK**: Player looks around
- **M-ENTER**: Player enters room
- **M-EXIT**: Player leaves room

## 6. Parser and Syntax

### 6.1 Syntax Definition

```zil
<SYNTAX verb-word direct-object-type = V-ROUTINE-NAME>
<SYNTAX verb-word direct-obj-type prep indirect-obj-type = V-ROUTINE-NAME>
```

Examples:
```zil
<SYNTAX TAKE OBJECT = V-TAKE>
<SYNTAX PUT OBJECT IN OBJECT = V-PUT-IN>
<SYNTAX PUT OBJECT ON OBJECT = V-PUT-ON>
```

### 6.2 Object Types in Syntax
- **OBJECT**: Any visible object
- **OBJECTS**: Multiple objects
- **ROOM**: Room names
- **DIRECTION**: Compass directions
- **EVERYWHERE**: (V6 new-parser) Object accessible from any location

### 6.3 Synonym Definition

```zil
<SYNONYM word1 word2 word3 = canonical-word>
```

### 6.4 Property Definition

```zil
<PROPDEF SIZE 5>
<PROPDEF CAPACITY 8>
<PROPDEF VALUE 0>
```

## 7. Verb Routines

### 7.1 Verb Routine Structure

Verb routines must begin with `V-`:

```zil
<ROUTINE V-TAKE ()
    <COND (<NOT <FSET? ,PRSO TAKEBIT>>
           <TELL "You can't take that." CR>
           <RFALSE>)
          (T
           <MOVE ,PRSO ,WINNER>
           <TELL "Taken." CR>
           <RTRUE>)>>
```

### 7.2 Parser Global Variables

- **PRSA**: Current verb (PRed Action)
- **PRSO**: Direct object (PRed Subject Object)
- **PRSI**: Indirect object (PRed Subject Indirect)
- **WINNER**: Current actor (usually player)
- **HERE**: Current room

### 7.3 Verb Testing

```zil
<VERB? verb-name>           ;"Test current verb"
<PRSO? object-name>         ;"Test direct object"
<PRSI? object-name>         ;"Test indirect object"
```

## 8. Object Actions and Interactions

### 8.1 Action Routine Flow

When a verb executes, the system checks in order:
1. PRSI object's ACTION routine
2. PRSO object's ACTION routine
3. PRSA verb routine
4. Stops at first successful return (RTRUE)

### 8.2 Object Action Routine

```zil
<ROUTINE SWORD-ROUTINE ()
    <COND (<VERB? WAVE>
           <TELL "You wave the sword menacingly." CR>
           <RTRUE>)
          (<VERB? ATTACK>
           <TELL "You swing the sword!" CR>
           <RTRUE>)
          (T <RFALSE>)>>
```

## 9. Built-in Functions

### 9.1 Object Manipulation

```zil
<MOVE object destination>        ;"Move object to new location"
<REMOVE object>                   ;"Remove object from containment"
<FIRST? container>                ;"First object in container"
<NEXT? object>                    ;"Next sibling object"
<IN? object container>            ;"Test if object in container"
<LOC object>                      ;"Get object's location"
```

### 9.2 Property Access

```zil
<GETP object property>            ;"Get property value"
<PUTP object property value>      ;"Set property value"
<GETPT object property>           ;"Get property table address"
```

### 9.3 Arithmetic

```zil
<+ num1 num2 ...>                 ;"Addition"
<- num1 num2>                     ;"Subtraction"
<* num1 num2>                     ;"Multiplication"
</ num1 num2>                     ;"Division"
<MOD num1 num2>                   ;"Modulo"
<MIN num1 num2 ...>               ;"Minimum"
<MAX num1 num2 ...>               ;"Maximum"
<RANDOM range>                    ;"Random number 1 to range"
```

### 9.4 Comparison

```zil
<EQUAL? val1 val2 val3 ...>       ;"Equality (any match)"
<N==? val1 val2>                  ;"Not equal"
<L? num1 num2>                    ;"Less than"
<G? num1 num2>                    ;"Greater than"
<L=? num1 num2>                   ;"Less than or equal"
<G=? num1 num2>                   ;"Greater than or equal"
<0? num>                          ;"Equal to zero"
<GRTR? num1 num2>                 ;"num1 > num2"
```

### 9.5 String/Text Output

```zil
<TELL "string" var "string" CR>   ;"Output text, CR = carriage return"
<CRLF>                            ;"Newline"
<PRINTB byte-string>              ;"Print byte string"
<PRINTI "inline-string">          ;"Print inline"
<PRINTD object>                   ;"Print object description"
<PRINTN number>                   ;"Print number"
```

### 9.6 Input

```zil
<READ buffer parse-buffer>        ;"Read player input"
<READ-CHAR>                       ;"Read single character (V4+)"
```

### 9.7 Table Operations

```zil
<GET table index>                 ;"Word access (1-based)"
<GETB table index>                ;"Byte access (0-based)"
<PUT table index value>           ;"Word write"
<PUTB table index value>          ;"Byte write"
<PTSIZE table>                    ;"Get table size"
```

### 9.8 Control

```zil
<RETURN value>                    ;"Return from routine"
<RTRUE>                           ;"Return true"
<RFALSE>                          ;"Return false"
<QUIT>                            ;"End game"
<RESTART>                         ;"Restart game"
<SAVE>                            ;"Save game (returns true if successful)"
<RESTORE>                         ;"Restore game"
```

## 10. Tables and Data Structures

### 10.1 Table Definition

```zil
<TABLE number number number ...>              ;"Word table"
<TABLE (BYTE) byte byte byte ...>             ;"Byte table"
<TABLE (PURE) number number ...>              ;"Pure (read-only) table"
<TABLE (LENGTH) number data data ...>         ;"Table with length prefix"
```

### 10.2 String Tables

```zil
<ITABLE 10 (BYTE) 0>              ;"Input buffer"
<LTABLE 100>                      ;"Parse buffer"
```

## 11. Macros

### 11.1 Macro Definition

```zil
<DEFMAC macro-name (parameters)
    <macro-body>>
```

### 11.2 Common Macros

```zil
<CR>                              ;"Carriage return in TELL"
<UPPERCASE string>                ;"Convert to uppercase"
<LOWERCASE string>                ;"Convert to lowercase"
```

## 12. File Organization

### 12.1 Typical Game Structure

```
game.zil          ; Main loader file
├─ syntax.zil     ; Parser syntax definitions
├─ verbs.zil      ; Verb routines
├─ globals.zil    ; Global variables
├─ objects.zil    ; Object definitions
├─ rooms.zil      ; Room definitions
├─ actions.zil    ; Action routines
└─ misc.zil       ; Utility routines
```

### 12.2 File Inclusion

```zil
<IFILE "filename">                ;"Include ZIL file"
<INSERT-FILE "filename">          ;"Include file (ZILF)"
```

### 12.3 Version Directive

```zil
<VERSION 3>                       ;"Target Z-machine version (3, 4, 5, 6, 8)"
```

## 13. Advanced Features

### 13.1 Events and Interrupts

```zil
<EVENT event-name clock-value routine>
```

### 13.2 Vehicles

Objects with special handling for player location:

```zil
<OBJECT BOAT
    (FLAGS VEHBIT OPENBIT)
    (CAPACITY 100)
    (VTYPE VEHICLE)
    (ACTION BOAT-F)>
```

### 13.3 Actors

Non-player characters with independent actions:

```zil
<OBJECT GUARD
    (FLAGS NDESCBIT PERSON)
    (ACTION GUARD-F)
    (STRENGTH 10)>
```

### 13.4 Graphics (V6)

```zil
<DISPLAY-PICTURE picture-number>
<DRAW-STATUS-LINE>
```

### 13.5 Sound (V3+)

```zil
<SOUND-EFFECT sound-number effect>
```

## 14. Debugging

### 14.1 Debug Output

```zil
<TELL "[Debug: value=" ,VAR "]" CR>
```

### 14.2 Trace Flag

```zil
<SETG DEBUG T>
<COND (,DEBUG <TELL "Debug info" CR>)>
```

## 15. Compilation

### 15.1 ZILF Compiler Usage

```bash
zilf game.zil                     # Compile ZIL to ZAP
zapf game.zap                     # Assemble ZAP to Z-code
```

Output files:
- `game.zap` - Main assembly file
- `game_data.zap` - Constants and objects
- `game_str.zap` - Strings
- `game_freq.zap` - Abbreviations (optional)

### 15.2 Compiler Options

```bash
zilf -d game.zil                  # Debug symbols
zilf -tr game.zil                 # Runtime tracing
zilf -s game.zil                  # Case-sensitive mode
```

## 16. Differences from MDL/LISP

### 16.1 Fixed Data Structures
Unlike MDL, ZIL operates exclusively on fixed data structures with no garbage collection or dynamic list construction at runtime.

### 16.2 No Runtime Lists
ZIL lacks primitive list-construction operations like `car`, `cdr`, and runtime `MAPF`.

### 16.3 Compile-time vs Runtime
- **Compile-time**: Full MDL functionality available for macros and code generation
- **Runtime**: Only static structures and fixed operations

### 16.4 Z-machine Constraints
All runtime behavior must compile to Z-machine instructions with strict memory limitations (64KB address space).

## 17. Best Practices

### 17.1 Naming Conventions
- Verbs: `V-VERB-NAME`
- Objects: `OBJECT-NAME` (often all-caps)
- Routines: `DESCRIPTIVE-NAME-F` or `DESCRIPTIVE-NAME-ROUTINE`
- Globals: `,GLOBAL-NAME` (comma prefix in use)
- Locals: `.local-name` (period prefix in use)

### 17.2 Code Organization
- Group related objects together
- Keep syntax definitions separate from verb implementations
- Use macros for repeated patterns
- Comment complex logic

### 17.3 Memory Management
- Pre-allocate tables at compile time
- Minimize string duplication
- Use abbreviations for frequently used text (V2+)

### 17.4 Parser Design
- Provide comprehensive synonyms
- Test with various phrasings
- Handle edge cases (empty objects, invalid combinations)

## 18. Library Functions

### 18.1 Standard Library
Include the IF library for common routines:

```zil
<INSERT-FILE "parser">
```

Provides:
- `MAIN-LOOP` - Primary game loop
- `PARSER` - Input parsing
- `PERFORM` - Action execution
- `DESCRIBE-ROOM` - Room description
- `DESCRIBE-OBJECTS` - Object listing

### 18.2 Common Utility Routines
- `V-VERSION` - Display interpreter version
- `SCORE` - Score handling
- `JIGS-UP` - Death/game over handler
- `FINISH` - Game completion handler

## 19. Z-machine Version Targeting

### 19.1 Version Capabilities

**Version 3** (.z3):
- 128KB story file
- Standard features
- Most common for classic games

**Version 4** (.z4):
- 256KB story file
- Timed input
- Fixed-pitch font support

**Version 5** (.z5):
- 256KB story file
- Colors
- Sound effects
- Extended character set
- Undo

**Version 6** (.z6):
- Graphics
- Mouse input
- Proportional fonts
- Advanced windowing

**Version 8** (.z8):
- 512KB story file
- Modern features

### 19.2 Version Selection
Choose based on:
- Required features
- Target interpreter compatibility
- Story file size requirements

## 20. References

### 20.1 Primary Documentation
- "Learning ZIL" by Steven Eric Meretzky (1989/1995)
- "ZIL Course" by Marc S. Blank (1982)
- "The MDL Programming Language" by S. W. Galley and Greg Pfister

### 20.2 Modern Resources
- ZILF documentation by Tara McGrew
- ZILF Reference Guide by heasm66
- Historical source code: github.com/historicalsource
- Z-Machine Standards Document by Graham Nelson

### 20.3 Tools
- **ZILF**: zilf.io - Modern ZIL compiler
- **ZAPF**: Z-machine assembler (part of ZILF)
- **Frotz/Zoom/etc**: Z-machine interpreters for testing
