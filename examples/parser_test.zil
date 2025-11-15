;"Test parser system globals and VERB? predicate"

<VERSION 3>

<CONSTANT TAKEBIT 1>
<CONSTANT LIGHTBIT 0>

<GLOBAL SCORE 0>

<OBJECT PLAYER
    (DESC "yourself")>

<OBJECT LAMP
    (DESC "brass lantern")
    (FLAGS TAKEBIT)>

<OBJECT SWORD
    (DESC "sword")
    (FLAGS TAKEBIT)>

<ROOM START-ROOM
    (DESC "Test Room")
    (LDESC "A room for testing parser features.")
    (FLAGS LIGHTBIT)>

<ROUTINE LAMP-ACTION ()
    <COND (<VERB? TAKE>
           <TELL "You take the lamp." CR>
           <MOVE LAMP PLAYER>
           <SETG SCORE <+ ,SCORE 5>>
           <RTRUE>)
          (<VERB? DROP>
           <TELL "You drop the lamp." CR>
           <MOVE LAMP ,HERE>
           <RTRUE>)
          (<VERB? EXAMINE>
           <TELL "It's a shiny brass lantern." CR>
           <RTRUE>)
          (<VERB? LAMP-ON>
           <COND (<FSET? LAMP LIGHTBIT>
                  <TELL "The lamp is already lit." CR>)
                 (T
                  <FSET LAMP LIGHTBIT>
                  <TELL "The lamp is now glowing brightly." CR>)>
           <RTRUE>)
          (<VERB? LAMP-OFF>
           <COND (<NOT <FSET? LAMP LIGHTBIT>>
                  <TELL "The lamp is already off." CR>)
                 (T
                  <FCLEAR LAMP LIGHTBIT>
                  <TELL "The lamp goes dark." CR>)>
           <RTRUE>)
          (T
           <TELL "You can't do that with the lamp." CR>
           <RFALSE>)>>

<ROUTINE SWORD-ACTION ()
    <COND (<VERB? TAKE DROP>
           <TELL "You handle the sword." CR>
           <RTRUE>)
          (<VERB? EXAMINE>
           <TELL "A fine steel blade." CR>
           <RTRUE>)
          (<VERB? ATTACK KILL>
           <TELL "You swing the sword menacingly!" CR>
           <RTRUE>)
          (T
           <TELL "You can't do that with the sword." CR>
           <RFALSE>)>>

<ROUTINE TEST-VERB-SINGLE ()
    <TELL "Testing VERB? with single verb..." CR>

    ;"Simulate TAKE action"
    <SETG PRSA ,V?TAKE>
    <SETG PRSO ,LAMP>
    <LAMP-ACTION>
    <CRLF>>

<ROUTINE TEST-VERB-MULTIPLE ()
    <TELL "Testing VERB? with multiple verbs..." CR>

    ;"Simulate ATTACK action on sword"
    <SETG PRSA ,V?ATTACK>
    <SETG PRSO ,SWORD>
    <SWORD-ACTION>
    <CRLF>>

<ROUTINE TEST-LAMP-CONTROL ()
    <TELL "Testing lamp on/off..." CR>

    <SETG PRSA ,V?LAMP-ON>
    <SETG PRSO ,LAMP>
    <LAMP-ACTION>

    <SETG PRSA ,V?LAMP-OFF>
    <LAMP-ACTION>
    <CRLF>>

<ROUTINE TEST-PARSER-GLOBALS ()
    <TELL "Testing parser globals..." CR>

    <TELL "PRSA = ">
    <PRINTN ,PRSA>
    <CRLF>

    <TELL "PRSO = ">
    <PRINTN ,PRSO>
    <CRLF>

    <TELL "PRSI = ">
    <PRINTN ,PRSI>
    <CRLF>

    <TELL "HERE = ">
    <PRINTN ,HERE>
    <CRLF>

    <CRLF>>

<ROUTINE GO ()
    <TELL "Parser System Test" CR CR>

    ;"Initialize game state"
    <SETG HERE ,START-ROOM>
    <MOVE PLAYER ,START-ROOM>
    <MOVE LAMP ,START-ROOM>
    <MOVE SWORD ,START-ROOM>

    <TEST-PARSER-GLOBALS>
    <TEST-VERB-SINGLE>
    <TEST-VERB-MULTIPLE>
    <TEST-LAMP-CONTROL>

    <TELL "Final score: ">
    <PRINTN ,SCORE>
    <TELL " / 100" CR CR>

    <TELL "Parser test complete!" CR>
    <QUIT>>
