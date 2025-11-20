"Test REPEAT with RETURN"

<VERSION 3>

<ROUTINE GO ()
    <REPEAT ()
        <COND (<L? 1 2> <RETURN 42>)>
        <PRINTN 1>>>

<ROUTINE START ()
    <GO>
    <QUIT>>
