"Simplified slice of Zork1 to test compiler capabilities"

<VERSION 3>

<CONSTANT M-FATAL 2>
<CONSTANT M-HANDLED 1>

<GLOBAL PLAYER <>>
<GLOBAL PRSA 0>
<GLOBAL PRSO <>>

<OBJECT KITCHEN
    (IN ROOMS)
    (DESC "Kitchen")
    (LDESC "You are in a kitchen.")
    (ACTION KITCHEN-F)>

<ROUTINE KITCHEN-F ()
    <COND (<EQUAL? ,PRSA ,V?LOOK>
           <TELL "This is a kitchen." CR>
           <RTRUE>)>
    <RFALSE>>

<ROUTINE MAIN-LOOP ()
    <REPEAT ()
        <COND (<L? 1 2>
               <TELL "Testing..." CR>
               <RETURN>)>>>

<ROUTINE START ()
    <SET PLAYER ,KITCHEN>
    <MAIN-LOOP>
    <QUIT>>
