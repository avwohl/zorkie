;"Test arithmetic operations"

<VERSION 3>

<GLOBAL RESULT 0>
<GLOBAL NUM1 10>
<GLOBAL NUM2 5>

<ROUTINE GO ()
    <TELL "Testing Arithmetic Operations" CR CR>

    ;"Addition"
    <SETG RESULT <+ ,NUM1 ,NUM2>>
    <TELL "10 + 5 = ">
    <PRINTN ,RESULT>
    <CRLF>

    ;"Subtraction"
    <SETG RESULT <- ,NUM1 ,NUM2>>
    <TELL "10 - 5 = ">
    <PRINTN ,RESULT>
    <CRLF>

    ;"Multiplication"
    <SETG RESULT <* ,NUM1 ,NUM2>>
    <TELL "10 * 5 = ">
    <PRINTN ,RESULT>
    <CRLF>

    ;"Division"
    <SETG RESULT </ ,NUM1 ,NUM2>>
    <TELL "10 / 5 = ">
    <PRINTN ,RESULT>
    <CRLF>

    <CRLF>
    <TELL "All tests complete!" CR>
    <QUIT>>
