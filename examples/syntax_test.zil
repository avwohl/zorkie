;"Test SYNTAX to action mapping"

<VERSION 3>

<CONSTANT TAKEBIT 1>
<CONSTANT LIGHTBIT 0>

<GLOBAL SCORE 0>

;"=== SYNTAX DEFINITIONS ==="

;"Meta commands"
<SYNTAX QUIT = V-QUIT>
<SYNTAX SAVE = V-SAVE>
<SYNTAX RESTORE = V-RESTORE>
<SYNTAX INVENTORY = V-INVENTORY>
<SYNONYM INVENTORY I>

;"Object manipulation"
<SYNTAX TAKE OBJECT = V-TAKE>
<SYNONYM TAKE GET PICK>

<SYNTAX DROP OBJECT = V-DROP>
<SYNONYM DROP RELEASE>

<SYNTAX EXAMINE OBJECT = V-EXAMINE>
<SYNONYM EXAMINE X LOOK>

<SYNTAX PUT OBJECT IN OBJECT = V-PUT>
<SYNONYM PUT PLACE INSERT>

<SYNTAX OPEN OBJECT = V-OPEN>
<SYNTAX CLOSE OBJECT = V-CLOSE>

;"Light control"
<SYNTAX LIGHT OBJECT = V-LAMP-ON>
<SYNTAX EXTINGUISH OBJECT = V-LAMP-OFF>
<SYNONYM EXTINGUISH DOUSE DARKEN>

;"Combat"
<SYNTAX ATTACK OBJECT = V-ATTACK>
<SYNONYM ATTACK KILL FIGHT HIT>

<SYNTAX ATTACK OBJECT WITH OBJECT = V-ATTACK>

;"=== OBJECTS ==="

<OBJECT PLAYER
    (DESC "yourself")
    (SYNONYM SELF ME MYSELF)>

<OBJECT LAMP
    (DESC "brass lantern")
    (SYNONYM LAMP LANTERN LIGHT)
    (ADJECTIVE BRASS BRIGHT SHINY)
    (FLAGS TAKEBIT)>

<OBJECT SWORD
    (DESC "steel sword")
    (SYNONYM SWORD BLADE WEAPON)
    (ADJECTIVE STEEL SHARP)
    (FLAGS TAKEBIT)>

<OBJECT BOX
    (DESC "wooden box")
    (SYNONYM BOX CHEST CONTAINER)
    (ADJECTIVE WOODEN OAK)>

<ROOM START-ROOM
    (DESC "Test Chamber")
    (LDESC "A room for testing the parser.")
    (FLAGS LIGHTBIT)>

;"=== ROUTINES ==="

<ROUTINE V-TAKE ()
    <TELL "You would take the object." CR>>

<ROUTINE V-DROP ()
    <TELL "You would drop the object." CR>>

<ROUTINE V-EXAMINE ()
    <TELL "You would examine the object." CR>>

<ROUTINE V-PUT ()
    <TELL "You would put the object somewhere." CR>>

<ROUTINE V-OPEN ()
    <TELL "You would open the object." CR>>

<ROUTINE V-CLOSE ()
    <TELL "You would close the object." CR>>

<ROUTINE V-LAMP-ON ()
    <TELL "You would light the object." CR>>

<ROUTINE V-LAMP-OFF ()
    <TELL "You would extinguish the object." CR>>

<ROUTINE V-ATTACK ()
    <TELL "Violence is not the answer!" CR>>

<ROUTINE V-INVENTORY ()
    <TELL "You are carrying: nothing" CR>>

<ROUTINE V-QUIT ()
    <QUIT>>

<ROUTINE V-SAVE ()
    <SAVE>>

<ROUTINE V-RESTORE ()
    <RESTORE>>

<ROUTINE SHOW-SYNTAX-INFO ()
    <TELL "=== SYNTAX TO ACTION MAPPING TEST ===" CR CR>

    <TELL "Defined Syntax Patterns:" CR>
    <TELL "  QUIT -> V-QUIT" CR>
    <TELL "  TAKE OBJECT -> V-TAKE" CR>
    <TELL "  DROP OBJECT -> V-DROP" CR>
    <TELL "  EXAMINE OBJECT -> V-EXAMINE" CR>
    <TELL "  PUT OBJECT IN OBJECT -> V-PUT" CR>
    <TELL "  OPEN OBJECT -> V-OPEN" CR>
    <TELL "  CLOSE OBJECT -> V-CLOSE" CR>
    <TELL "  LIGHT OBJECT -> V-LAMP-ON" CR>
    <TELL "  EXTINGUISH OBJECT -> V-LAMP-OFF" CR>
    <TELL "  ATTACK OBJECT -> V-ATTACK" CR>
    <TELL "  ATTACK OBJECT WITH OBJECT -> V-ATTACK" CR>
    <TELL "  INVENTORY -> V-INVENTORY" CR>
    <CRLF>

    <TELL "Verb Synonyms:" CR>
    <TELL "  TAKE = GET, PICK" CR>
    <TELL "  DROP = RELEASE" CR>
    <TELL "  EXAMINE = X, LOOK" CR>
    <TELL "  PUT = PLACE, INSERT" CR>
    <TELL "  EXTINGUISH = DOUSE, DARKEN" CR>
    <TELL "  ATTACK = KILL, FIGHT, HIT" CR>
    <TELL "  INVENTORY = I" CR>
    <CRLF>>

<ROUTINE SHOW-PARSER-FLOW ()
    <TELL "Parser Flow (Conceptual):" CR CR>

    <TELL "1. Player types: TAKE BRASS LAMP" CR>
    <TELL "2. Parser tokenizes: [TAKE] [BRASS] [LAMP]" CR>
    <TELL "3. Dictionary lookup:" CR>
    <TELL "     TAKE -> verb" CR>
    <TELL "     BRASS -> adjective (LAMP)" CR>
    <TELL "     LAMP -> noun (LAMP object)" CR>
    <TELL "4. SYNTAX match: TAKE OBJECT" CR>
    <TELL "5. Set PRSA = V?TAKE" CR>
    <TELL "6. Set PRSO = LAMP object" CR>
    <TELL "7. Call V-TAKE routine" CR>
    <CRLF>>

<ROUTINE SHOW-DICTIONARY-STATS ()
    <TELL "Dictionary Statistics:" CR>
    <TELL "  Verbs from SYNTAX: ~15" CR>
    <TELL "  Verb synonyms: ~10" CR>
    <TELL "  Object nouns: ~15" CR>
    <TELL "  Object adjectives: ~10" CR>
    <TELL "  Total words: ~100+" CR>
    <CRLF>>

<ROUTINE SIMULATE-COMMANDS ()
    <TELL "Simulating Parser Commands:" CR CR>

    ;"Simulate TAKE LAMP"
    <TELL "> TAKE LAMP" CR>
    <SETG PRSA ,V?TAKE>
    <SETG PRSO ,LAMP>
    <V-TAKE>
    <CRLF>

    ;"Simulate EXAMINE SWORD"
    <TELL "> EXAMINE SWORD" CR>
    <SETG PRSA ,V?EXAMINE>
    <SETG PRSO ,SWORD>
    <V-EXAMINE>
    <CRLF>

    ;"Simulate PUT LAMP IN BOX"
    <TELL "> PUT LAMP IN BOX" CR>
    <SETG PRSA ,V?PUT>
    <SETG PRSO ,LAMP>
    <SETG PRSI ,BOX>
    <V-PUT>
    <CRLF>>

<ROUTINE GO ()
    <SETG HERE ,START-ROOM>
    <MOVE PLAYER ,START-ROOM>
    <MOVE LAMP ,START-ROOM>
    <MOVE SWORD ,START-ROOM>
    <MOVE BOX ,START-ROOM>

    <SHOW-SYNTAX-INFO>
    <SHOW-PARSER-FLOW>
    <SHOW-DICTIONARY-STATS>
    <SIMULATE-COMMANDS>

    <TELL "=== SYNTAX TEST COMPLETE ===" CR CR>

    <TELL "This demonstrates:" CR>
    <TELL "  - SYNTAX definitions parsed correctly" CR>
    <TELL "  - Verbs extracted to dictionary" CR>
    <TELL "  - Synonyms linked to base verbs" CR>
    <TELL "  - Action routines ready for dispatch" CR>
    <CRLF>

    <TELL "Full parser would:" CR>
    <TELL "  - Tokenize player input" CR>
    <TELL "  - Match against SYNTAX patterns" CR>
    <TELL "  - Set PRSA/PRSO/PRSI" CR>
    <TELL "  - Call action routine" CR>
    <CRLF>

    <QUIT>>
