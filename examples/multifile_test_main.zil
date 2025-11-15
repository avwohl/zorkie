;"Multi-file compilation test - MAIN FILE"
;"This file includes objects.zil and routines.zil"

<VERSION 3>

<CONSTANT TAKEBIT 1>
<CONSTANT LIGHTBIT 0>

<GLOBAL SCORE 0>
<GLOBAL MOVES 0>

;"Main entry point"
<ROUTINE GO ()
    <TELL "=== MULTI-FILE COMPILATION TEST ===" CR CR>

    ;"Initialize game state"
    <SETG HERE ,START-ROOM>
    <MOVE PLAYER ,START-ROOM>
    <MOVE LAMP ,START-ROOM>
    <MOVE SWORD ,ARMORY>

    <TELL "Game initialized with objects from objects.zil" CR>
    <TELL "Routines from routines.zil:" CR CR>

    ;"Test routines from included file"
    <TEST-OBJECT-ROUTINE>
    <TEST-ROOM-ROUTINE>

    <TELL CR "=== MULTI-FILE TEST COMPLETE ===" CR>
    <QUIT>>
