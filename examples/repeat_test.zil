;"Test REPEAT loop functionality"

<VERSION 3>

<GLOBAL COUNTER 0>
<GLOBAL SUM 0>

<ROUTINE COUNT-TO-TEN ()
    <TELL "Counting from 1 to 10:" CR>

    <REPEAT ((I 1))
        <COND (<G? .I 10>
               <RETURN>)>

        <PRINTN .I>
        <TELL " ">
        <SET I <+ .I 1>>>

    <CRLF>>

<ROUTINE SUM-NUMBERS (N)
    <TELL "Summing numbers from 1 to ">
    <PRINTN .N>
    <TELL ":" CR>

    <SETG SUM 0>

    <REPEAT ((I 1))
        <COND (<G? .I .N>
               <RETURN>)>

        <SETG SUM <+ ,SUM .I>>
        <SET I <+ .I 1>>>

    <TELL "Sum = ">
    <PRINTN ,SUM>
    <CRLF>>

<ROUTINE INFINITE-LOOP-WITH-EXIT ()
    <TELL "Testing loop with early exit..." CR>

    <SETG COUNTER 0>

    <REPEAT ()
        <SETG COUNTER <+ ,COUNTER 1>>

        <COND (<EQUAL? ,COUNTER 5>
               <TELL "Exiting at count 5!" CR>
               <RETURN>)>

        <PRINTN ,COUNTER>
        <TELL " ">>>

<ROUTINE NESTED-LOOPS ()
    <TELL "Testing nested loops:" CR>

    <REPEAT ((I 1))
        <COND (<G? .I 3>
               <RETURN>)>

        <TELL "Outer loop ">
        <PRINTN .I>
        <TELL ": ">

        <REPEAT ((J 1))
            <COND (<G? .J 3>
                   <RETURN>)>

            <PRINTN .J>
            <TELL " ">
            <SET J <+ .J 1>>>

        <CRLF>
        <SET I <+ .I 1>>>>

<ROUTINE GO ()
    <TELL "REPEAT Loop Test" CR CR>

    <COUNT-TO-TEN>
    <CRLF>

    <SUM-NUMBERS 5>
    <CRLF>

    <INFINITE-LOOP-WITH-EXIT>
    <CRLF>

    <NESTED-LOOPS>
    <CRLF>

    <TELL "All tests complete!" CR>
    <QUIT>>
