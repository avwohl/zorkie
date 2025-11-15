;"Test counter with INC/DEC"

<VERSION 3>

<GLOBAL COUNTER 0>

<ROUTINE GO ()
    <TELL "Counter Test" CR CR>

    <SETG COUNTER 0>
    <TELL "Starting counter: ">
    <PRINTN ,COUNTER>
    <CRLF>

    <INC COUNTER>
    <TELL "After INC: ">
    <PRINTN ,COUNTER>
    <CRLF>

    <INC COUNTER>
    <TELL "After another INC: ">
    <PRINTN ,COUNTER>
    <CRLF>

    <DEC COUNTER>
    <TELL "After DEC: ">
    <PRINTN ,COUNTER>
    <CRLF>

    <CRLF>
    <QUIT>>
