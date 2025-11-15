;"Test vocabulary dictionary with SYNONYM and ADJECTIVE"

<VERSION 3>

<CONSTANT TAKEBIT 1>
<CONSTANT LIGHTBIT 0>

<GLOBAL SCORE 0>

<OBJECT PLAYER
    (DESC "yourself")
    (SYNONYM SELF ME MYSELF)>

<OBJECT LAMP
    (DESC "brass lantern")
    (SYNONYM LAMP LANTERN LIGHT)
    (ADJECTIVE BRASS SHINY BRIGHT)
    (FLAGS TAKEBIT)>

<OBJECT SWORD
    (DESC "steel sword")
    (SYNONYM SWORD BLADE WEAPON)
    (ADJECTIVE STEEL SHARP GLEAMING)
    (FLAGS TAKEBIT)>

<OBJECT BOOK
    (DESC "old book")
    (SYNONYM BOOK TOME VOLUME MANUAL)
    (ADJECTIVE OLD DUSTY LEATHER)
    (FLAGS TAKEBIT)>

<OBJECT CHEST
    (DESC "wooden chest")
    (SYNONYM CHEST BOX CONTAINER TRUNK)
    (ADJECTIVE WOODEN OAK HEAVY LARGE)>

<ROOM LIBRARY
    (DESC "Ancient Library")
    (LDESC "You are in a vast library filled with books.")
    (SYNONYM LIBRARY ROOM)
    (ADJECTIVE ANCIENT DUSTY GRAND)
    (FLAGS LIGHTBIT)>

<ROOM ARMORY
    (DESC "Castle Armory")
    (LDESC "Weapons line the walls of this armory.")
    (SYNONYM ARMORY ARSENAL)
    (ADJECTIVE CASTLE MILITARY)
    (FLAGS LIGHTBIT)>

<ROUTINE SHOW-VOCABULARY ()
    <TELL "Vocabulary Test - Object Synonyms and Adjectives" CR CR>

    <TELL "LAMP synonyms: lamp, lantern, light" CR>
    <TELL "LAMP adjectives: brass, shiny, bright" CR>
    <CRLF>

    <TELL "SWORD synonyms: sword, blade, weapon" CR>
    <TELL "SWORD adjectives: steel, sharp, gleaming" CR>
    <CRLF>

    <TELL "BOOK synonyms: book, tome, volume, manual" CR>
    <TELL "BOOK adjectives: old, dusty, leather" CR>
    <CRLF>

    <TELL "CHEST synonyms: chest, box, container, trunk" CR>
    <TELL "CHEST adjectives: wooden, oak, heavy, large" CR>
    <CRLF>

    <TELL "LIBRARY synonyms: library, room" CR>
    <TELL "LIBRARY adjectives: ancient, dusty, grand" CR>
    <CRLF>

    <TELL "ARMORY synonyms: armory, arsenal" CR>
    <TELL "ARMORY adjectives: castle, military" CR>
    <CRLF>>

<ROUTINE SHOW-DICT-INFO ()
    <TELL "Dictionary Information:" CR>
    <TELL "The dictionary now contains:" CR>
    <TELL "  - All standard verbs (take, drop, examine, etc.)" CR>
    <TELL "  - Object synonyms (nouns)" CR>
    <TELL "  - Object adjectives (descriptors)" CR>
    <TELL "  - Room names" CR>
    <CRLF>

    <TELL "Each word in the dictionary is:" CR>
    <TELL "  - Encoded using Z-character compression" CR>
    <TELL "  - Tagged with type (verb/noun/adjective)" CR>
    <TELL "  - Linked to object number (for synonyms)" CR>
    <CRLF>>

<ROUTINE TEST-VOCAB-OBJECTS ()
    <TELL "Testing vocabulary-enhanced objects..." CR>

    <MOVE LAMP PLAYER>
    <TELL "You are carrying: brass lantern" CR>
    <TELL "(synonyms: lamp/lantern/light)" CR>
    <TELL "(adjectives: brass/shiny/bright)" CR>
    <CRLF>

    <MOVE SWORD PLAYER>
    <TELL "You are carrying: steel sword" CR>
    <TELL "(synonyms: sword/blade/weapon)" CR>
    <TELL "(adjectives: steel/sharp/gleaming)" CR>
    <CRLF>>

<ROUTINE GO ()
    <TELL "=== VOCABULARY DICTIONARY TEST ===" CR CR>

    ;"Initialize"
    <SETG HERE ,LIBRARY>
    <MOVE PLAYER ,LIBRARY>
    <MOVE LAMP ,LIBRARY>
    <MOVE SWORD ,ARMORY>
    <MOVE BOOK ,LIBRARY>
    <MOVE CHEST ,LIBRARY>

    <SHOW-VOCABULARY>
    <SHOW-DICT-INFO>
    <TEST-VOCAB-OBJECTS>

    <TELL "=== VOCABULARY TEST COMPLETE ===" CR CR>

    <TELL "In a full parser, these words would enable commands like:" CR>
    <TELL "  > TAKE BRASS LAMP" CR>
    <TELL "  > EXAMINE SHINY LANTERN" CR>
    <TELL "  > DROP LIGHT" CR>
    <TELL "  > GET STEEL SWORD" CR>
    <TELL "  > PUT BLADE IN WOODEN CHEST" CR>
    <CRLF>

    <QUIT>>
