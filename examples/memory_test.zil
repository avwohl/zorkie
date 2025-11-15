;"Test memory and array operations"

<VERSION 3>

<GLOBAL DATA-TABLE 0>
<GLOBAL VALUE 0>

<ROUTINE GO ()
    <TELL "Memory Operations Test" CR CR>

    <TELL "Testing PUSH/PULL..." CR>
    <PUSH 42>
    <TELL "Pushed 42 to stack" CR>
    <PULL VALUE>
    <TELL "Pulled value: ">
    <PRINTN ,VALUE>
    <CRLF>

    <CRLF>
    <TELL "Testing object tree traversal..." CR>
    <TELL "(Object operations would go here)" CR>

    <CRLF>
    <TELL "Tests complete!" CR>
    <QUIT>>
