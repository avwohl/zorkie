;"Test PERFORM action dispatch"

<VERSION 3>

<CONSTANT TAKEBIT 1>

<GLOBAL SCORE 0>

<OBJECT PLAYER
    (DESC "yourself")>

<OBJECT BALL
    (DESC "red ball")
    (FLAGS TAKEBIT)>

<OBJECT BOX
    (DESC "wooden box")>

<ROOM START-ROOM
    (DESC "Test Room")
    (FLAGS LIGHTBIT)>

<CONSTANT LIGHTBIT 0>

<ROUTINE TEST-PERFORM-SINGLE ()
    <TELL "Testing PERFORM with single object..." CR>

    ;"PERFORM sets PRSA and PRSO, then would call object ACTION"
    <PERFORM ,V?TAKE ,BALL>

    <TELL "After PERFORM ,V?TAKE ,BALL:" CR>
    <TELL "  PRSA = ">
    <PRINTN ,PRSA>
    <TELL " (should be ">
    <PRINTN ,V?TAKE>
    <TELL ")" CR>

    <TELL "  PRSO = ">
    <PRINTN ,PRSO>
    <TELL " (should be ball)" CR>

    <CRLF>>

<ROUTINE TEST-PERFORM-DOUBLE ()
    <TELL "Testing PERFORM with two objects..." CR>

    ;"PERFORM with indirect object"
    <PERFORM ,V?PUT ,BALL ,BOX>

    <TELL "After PERFORM ,V?PUT ,BALL ,BOX:" CR>
    <TELL "  PRSA = ">
    <PRINTN ,PRSA>
    <TELL " (should be ">
    <PRINTN ,V?PUT>
    <TELL ")" CR>

    <TELL "  PRSO = ">
    <PRINTN ,PRSO>
    <TELL " (ball)" CR>

    <TELL "  PRSI = ">
    <PRINTN ,PRSI>
    <TELL " (box)" CR>

    <CRLF>>

<ROUTINE TEST-CASCADED-PERFORM ()
    <TELL "Testing multiple PERFORM calls..." CR>

    <PERFORM ,V?EXAMINE ,BALL>
    <TELL "After EXAMINE: PRSA=">
    <PRINTN ,PRSA>
    <CRLF>

    <PERFORM ,V?DROP ,BALL>
    <TELL "After DROP: PRSA=">
    <PRINTN ,PRSA>
    <CRLF>

    <PERFORM ,V?TAKE ,BALL>
    <TELL "After TAKE: PRSA=">
    <PRINTN ,PRSA>
    <CRLF>

    <CRLF>>

<ROUTINE GO ()
    <TELL "PERFORM Action Dispatch Test" CR CR>

    ;"Initialize"
    <SETG HERE ,START-ROOM>
    <MOVE PLAYER ,START-ROOM>
    <MOVE BALL ,START-ROOM>
    <MOVE BOX ,START-ROOM>

    <TEST-PERFORM-SINGLE>
    <TEST-PERFORM-DOUBLE>
    <TEST-CASCADED-PERFORM>

    <TELL "All PERFORM tests complete!" CR>
    <TELL "In a full parser, PERFORM would call object ACTION routines." CR>
    <QUIT>>
