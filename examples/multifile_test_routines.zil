;"Multi-file compilation test - ROUTINES FILE"
;"This file defines test routines that work with objects from objects.zil"

<ROUTINE TEST-OBJECT-ROUTINE ()
    <TELL "Testing objects defined in objects.zil:" CR>
    <TELL "  LAMP: brass lantern" CR>
    <TELL "  SWORD: steel sword" CR>
    <TELL "  BOOK: ancient tome" CR>
    <CRLF>>

<ROUTINE TEST-ROOM-ROUTINE ()
    <TELL "Testing rooms defined in objects.zil:" CR>
    <TELL "  START-ROOM: Library" CR>
    <TELL "  ARMORY: Armory" CR>
    <CRLF>>

<ROUTINE EXAMINE-OBJECT (OBJ)
    <TELL "You examine the " OBJ "." CR>>

<ROUTINE MOVE-OBJECT (OBJ DEST)
    <MOVE OBJ DEST>
    <TELL "Object moved successfully." CR>>
