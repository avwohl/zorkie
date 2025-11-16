;"Test GET and PUT table operations"

<VERSION 3>

;"Create a table with 5 elements"
<GLOBAL MY-TABLE <ITABLE 5 10 20 30 40 50>>

<GLOBAL RESULT 0>

<ROUTINE GO ()
	<TELL "Testing table operations..." CR>

	;"Test GET - read from table"
	;"Table is 1-based in ZIL"
	<SETG RESULT <GET ,MY-TABLE 1>>
	<TELL "Table[1] = ">
	<PRINTN ,RESULT>
	<CRLF>

	<SETG RESULT <GET ,MY-TABLE 3>>
	<TELL "Table[3] = ">
	<PRINTN ,RESULT>
	<CRLF>

	;"Test PUT - write to table"
	<PUT ,MY-TABLE 2 99>
	<TELL "Set Table[2] = 99" CR>

	;"Read it back"
	<SETG RESULT <GET ,MY-TABLE 2>>
	<TELL "Table[2] = ">
	<PRINTN ,RESULT>
	<CRLF>

	<TELL "Table operations work!" CR>
	<QUIT>>
