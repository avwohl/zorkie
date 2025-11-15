;"Advanced features test"

<VERSION 3>

<GLOBAL SCORE 0>
<GLOBAL MOVES 0>
<GLOBAL RAND-VAL 0>

<CONSTANT MAX-SCORE 100>

<ROUTINE INIT-GAME ()
    <SETG SCORE 0>
    <SETG MOVES 0>
    <TELL "Game initialized!" CR>>

<ROUTINE ADD-POINTS (POINTS)
    <SETG SCORE <+ ,SCORE .POINTS>>
    <RTRUE>>

<ROUTINE SHOW-STATUS ()
    <TELL "Score: ">
    <PRINTN ,SCORE>
    <TELL " / ">
    <PRINTN ,MAX-SCORE>
    <TELL "  Moves: ">
    <PRINTN ,MOVES>
    <CRLF>>

<ROUTINE GO ()
    <INIT-GAME>
    <CRLF>

    <TELL "Testing routine calls..." CR>
    <ADD-POINTS 10>
    <TELL "Added 10 points" CR>

    <ADD-POINTS 25>
    <TELL "Added 25 more points" CR>

    <CRLF>
    <SHOW-STATUS>

    <CRLF>
    <TELL "Testing RANDOM..." CR>
    <SETG RAND-VAL <RANDOM 10>>
    <TELL "Random value (1-10): ">
    <PRINTN ,RAND-VAL>
    <CRLF>

    <CRLF>
    <TELL "All tests complete!" CR>
    <QUIT>>
