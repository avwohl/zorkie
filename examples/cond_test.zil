;"Test COND with proper branching logic"

<VERSION 3>

<GLOBAL SCORE 0>
<GLOBAL TEST-VAL 0>

<CONSTANT TARGET 10>

<ROUTINE TEST-COND (VAL)
    <TELL "Testing COND with value: ">
    <PRINTN .VAL>
    <CRLF>

    <COND (<L? .VAL 5>
           <TELL "Value is less than 5" CR>
           <SETG SCORE <+ ,SCORE 1>>)
          (<EQUAL? .VAL 5>
           <TELL "Value equals 5" CR>
           <SETG SCORE <+ ,SCORE 5>>)
          (<G? .VAL 5>
           <TELL "Value is greater than 5" CR>
           <SETG SCORE <+ ,SCORE 10>>)
          (T
           <TELL "Fallback case" CR>)>>

<ROUTINE TEST-NESTED ()
    <SETG TEST-VAL 3>

    <COND (<FSET? LAMP LIGHTBIT>
           <TELL "Lamp is lit" CR>
           <SETG SCORE 100>)
          (T
           <TELL "Lamp is not lit" CR>
           <SETG SCORE 0>)>

    <COND (<EQUAL? ,TEST-VAL 3>
           <TELL "Test value is 3!" CR>)
          (<EQUAL? ,TEST-VAL 5>
           <TELL "Test value is 5!" CR>)>>

<OBJECT LAMP
    (DESC "brass lantern")
    (FLAGS TAKEBIT)>

<CONSTANT LIGHTBIT 0>
<CONSTANT TAKEBIT 1>

<ROUTINE GO ()
    <TELL "COND Branching Test" CR CR>

    ;"Test with different values"
    <TEST-COND 3>
    <CRLF>

    <TEST-COND 5>
    <CRLF>

    <TEST-COND 8>
    <CRLF>

    <TELL "Testing nested COND..." CR>
    <TEST-NESTED>

    <CRLF>
    <TELL "Final score: ">
    <PRINTN ,SCORE>
    <CRLF>

    <TELL CR "Test complete!" CR>
    <QUIT>>
