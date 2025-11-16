;"Test DEFMAC macro system - Simple version without quotes"

<VERSION 3>

;"Simple macro with FORM - creates a multiplication"
<DEFMAC DOUBLE (NUM) <FORM * .NUM 2>>

;"Macro that creates a SET form"
<DEFMAC SET-TO-TEN (VAR) <FORM SETG .VAR 10>>

<GLOBAL TEST-VAR 0>
<GLOBAL RESULT 0>

<ROUTINE GO ()
	;"Test simple macro expansion"
	<TELL "Testing macros..." CR>

	;"This should expand to: <SETG TEST-VAR 10>"
	<SET-TO-TEN TEST-VAR>

	;"This should expand to: <* 5 2> which is 10"
	<SETG RESULT <DOUBLE 5>>

	<TELL "Result is: ">
	<PRINTN ,RESULT>
	<CRLF>

	<TELL "Macros work!" CR>
	<QUIT>>
