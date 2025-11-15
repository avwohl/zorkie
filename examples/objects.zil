;"Test object system"

<VERSION 3>

<OBJECT PLAYER
    (DESC "yourself")
    (FLAGS PERSON)>

<OBJECT LAMP
    (DESC "brass lantern")
    (FLAGS TAKEBIT)>

<ROOM WEST-OF-HOUSE
    (DESC "West of House")
    (LDESC "You are standing in an open field west of a white house.")
    (FLAGS LIGHTBIT)>

<CONSTANT LIGHTBIT 0>
<CONSTANT TAKEBIT 1>
<CONSTANT PERSON 2>

<ROUTINE GO ()
    <TELL "Object System Test" CR CR>

    <TELL "Setting LIGHTBIT on LAMP..." CR>
    <FSET LAMP LIGHTBIT>

    <TELL "Moving LAMP to PLAYER..." CR>
    <MOVE LAMP PLAYER>

    <TELL "Removing LAMP..." CR>
    <REMOVE LAMP>

    <CRLF>
    <TELL "Object tests complete!" CR>
    <QUIT>>
