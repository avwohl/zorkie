;"Test PROPDEF property number assignment"

<VERSION 3>

<CONSTANT TAKEBIT 1>
<CONSTANT LIGHTBIT 0>

;"Define custom properties with PROPDEF"
<PROPDEF SIZE 5>
<PROPDEF CAPACITY 0>
<PROPDEF VALUE 0>
<PROPDEF WEIGHT 1>
<PROPDEF DAMAGE 0>

<GLOBAL SCORE 0>

<OBJECT PLAYER
    (DESC "yourself")
    (SYNONYM SELF ME MYSELF)>

<OBJECT BACKPACK
    (DESC "leather backpack")
    (SYNONYM BACKPACK PACK BAG)
    (ADJECTIVE LEATHER WORN)
    (SIZE 20)
    (CAPACITY 15)
    (VALUE 5)
    (WEIGHT 2)
    (FLAGS TAKEBIT)>

<OBJECT SWORD
    (DESC "steel sword")
    (SYNONYM SWORD BLADE WEAPON)
    (ADJECTIVE STEEL SHARP GLEAMING)
    (SIZE 8)
    (VALUE 50)
    (WEIGHT 5)
    (DAMAGE 10)
    (FLAGS TAKEBIT)>

<OBJECT COIN
    (DESC "gold coin")
    (SYNONYM COIN GOLD MONEY)
    (ADJECTIVE GOLD SHINY)
    (SIZE 1)
    (VALUE 100)
    (WEIGHT 1)
    (FLAGS TAKEBIT)>

<OBJECT CHEST
    (DESC "wooden chest")
    (SYNONYM CHEST BOX CONTAINER TRUNK)
    (ADJECTIVE WOODEN OAK HEAVY LARGE)
    (SIZE 30)
    (CAPACITY 50)
    (VALUE 10)
    (WEIGHT 20)>

<ROOM START-ROOM
    (DESC "Test Chamber")
    (LDESC "A room for testing PROPDEF property assignments.")
    (FLAGS LIGHTBIT)>

<ROUTINE SHOW-PROPDEF-INFO ()
    <TELL "=== PROPDEF TEST ===" CR CR>

    <TELL "Property Definitions:" CR>
    <TELL "  SIZE (default 5) - How much space object takes" CR>
    <TELL "  CAPACITY (default 0) - How much object can hold" CR>
    <TELL "  VALUE (default 0) - Object's worth in coins" CR>
    <TELL "  WEIGHT (default 1) - How heavy the object is" CR>
    <TELL "  DAMAGE (default 0) - Weapon damage rating" CR>
    <CRLF>

    <TELL "Object Properties:" CR>
    <TELL "  BACKPACK: SIZE=20, CAPACITY=15, VALUE=5, WEIGHT=2" CR>
    <TELL "  SWORD: SIZE=8, VALUE=50, WEIGHT=5, DAMAGE=10" CR>
    <TELL "  COIN: SIZE=1, VALUE=100, WEIGHT=1" CR>
    <TELL "  CHEST: SIZE=30, CAPACITY=50, VALUE=10, WEIGHT=20" CR>
    <CRLF>>

<ROUTINE GO ()
    <SETG HERE ,START-ROOM>
    <MOVE PLAYER ,START-ROOM>
    <MOVE BACKPACK ,START-ROOM>
    <MOVE SWORD ,START-ROOM>
    <MOVE COIN ,START-ROOM>
    <MOVE CHEST ,START-ROOM>

    <SHOW-PROPDEF-INFO>

    <TELL "=== PROPDEF TEST COMPLETE ===" CR CR>

    <TELL "Benefits of PROPDEF:" CR>
    <TELL "  1. Explicit property number assignment" CR>
    <TELL "  2. Default values specified in one place" CR>
    <TELL "  3. Self-documenting property usage" CR>
    <TELL "  4. Consistent property numbers across objects" CR>
    <CRLF>

    <QUIT>>
