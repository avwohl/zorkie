;"Test various print operations"

<VERSION 3>

<GLOBAL COUNT 42>

<ROUTINE GO ()
	<TELL "Testing print operations..." CR CR>

	;"Test PRINTN (print number)"
	<TELL "PRINTN test: ">
	<PRINTN ,COUNT>
	<CRLF>

	;"Test PRINTD (decimal number - same as PRINTN)"
	<TELL "PRINTD test: ">
	<PRINTD ,COUNT>
	<CRLF>

	;"Test PRINTC (print character)"
	<TELL "PRINTC test: ">
	<PRINTC 65>  ;"ASCII 'A'"
	<PRINTC 66>  ;"ASCII 'B'"
	<PRINTC 67>  ;"ASCII 'C'"
	<CRLF>

	;"Test PRINTI (inline string)"
	<PRINTI "PRINTI test works!">
	<CRLF>

	<CRLF>
	<TELL "All print operations complete!" CR>
	<QUIT>>
