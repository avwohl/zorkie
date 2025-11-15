;"A tiny interactive fiction game
  Demonstrates multiple routines, objects, and game logic"

<VERSION 3>

;"===== Constants ====="

<CONSTANT LIGHTBIT 0>
<CONSTANT TAKEBIT 1>
<CONSTANT OPENBIT 2>
<CONSTANT CONTBIT 3>

;"===== Globals ====="

<GLOBAL SCORE 0>
<GLOBAL MOVES 0>
<GLOBAL LAMP-USES 0>

;"===== Objects ====="

<OBJECT PLAYER
    (DESC "yourself")
    (LDESC "You look about the same as always.")>

<OBJECT LAMP
    (DESC "brass lantern")
    (LDESC "A shiny brass lantern.")
    (FLAGS TAKEBIT)>

<OBJECT CHEST
    (DESC "wooden chest")
    (LDESC "An old wooden chest.")
    (FLAGS CONTBIT)>

<OBJECT GOLD
    (DESC "gold coin")
    (LDESC "A valuable gold coin!")
    (FLAGS TAKEBIT)>

;"===== Rooms ====="

<ROOM START-ROOM
    (DESC "Forest Path")
    (LDESC "You are on a forest path. There is a clearing to the north.")
    (FLAGS LIGHTBIT)>

<ROOM CLEARING
    (DESC "Clearing")
    (LDESC "You are in a small clearing.")
    (FLAGS LIGHTBIT)>

;"===== Routines ====="

<ROUTINE INIT-GAME ()
    <TELL "TINY QUEST" CR>
    <TELL "An Interactive Fiction Demo" CR CR>
    <TELL "Type HELP for instructions." CR CR>
    <SETG SCORE 0>
    <SETG MOVES 0>
    <MOVE PLAYER START-ROOM>
    <MOVE LAMP START-ROOM>
    <MOVE CHEST CLEARING>
    <MOVE GOLD CHEST>
    <RTRUE>>

<ROUTINE ADD-SCORE (POINTS)
    <SETG SCORE <+ ,SCORE .POINTS>>
    <TELL "Your score has gone up by ">
    <PRINTN .POINTS>
    <TELL " points!" CR>>

<ROUTINE SHOW-SCORE ()
    <TELL "Score: ">
    <PRINTN ,SCORE>
    <TELL " / 100">
    <CRLF>>

<ROUTINE TAKE-LAMP ()
    <COND (<FSET? LAMP TAKEBIT>
           <MOVE LAMP PLAYER>
           <TELL "You pick up the brass lantern." CR>
           <ADD-SCORE 5>
           <RTRUE>)
          (T
           <TELL "The lamp is already taken." CR>
           <RFALSE>)>>

<ROUTINE LIGHT-LAMP ()
    <COND (<FSET? LAMP LIGHTBIT>
           <TELL "The lamp is already lit." CR>
           <RFALSE>)
          (T
           <FSET LAMP LIGHTBIT>
           <TELL "The lamp is now lit." CR>
           <SETG LAMP-USES <+ ,LAMP-USES 1>>
           <RTRUE>)>>

<ROUTINE DESCRIBE-ROOM ()
    <TELL "You are in a room." CR>
    <TELL "(Room descriptions not fully implemented yet)" CR>>

<ROUTINE DEMO-ACTIONS ()
    ;"Demonstrate various game actions"
    <TELL "Demonstrating game actions..." CR CR>

    <TELL "Taking the lamp..." CR>
    <TAKE-LAMP>

    <CRLF>
    <TELL "Lighting the lamp..." CR>
    <LIGHT-LAMP>

    <CRLF>
    <TELL "Trying to light it again..." CR>
    <LIGHT-LAMP>

    <CRLF>
    <SHOW-SCORE>

    <CRLF>
    <TELL "Opening the chest..." CR>
    <FSET CHEST OPENBIT>
    <TELL "The chest is now open." CR>

    <COND (<FSET? CHEST OPENBIT>
           <TELL "The chest is indeed open." CR>)
          (T
           <TELL "The chest is closed." CR>)>

    <CRLF>
    <TELL "Getting the gold..." CR>
    <MOVE GOLD PLAYER>
    <TELL "You take the gold coin from the chest." CR>
    <ADD-SCORE 25>

    <CRLF>
    <SHOW-SCORE>>

<ROUTINE GO ()
    <INIT-GAME>
    <DEMO-ACTIONS>
    <CRLF>
    <TELL "Demo complete! Thanks for playing!" CR>
    <QUIT>>
