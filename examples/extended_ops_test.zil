<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing Extended V3 Operations ===" CR CR>

	<TELL "Testing PRINTT (print with tab):" CR>
	<PRINTT "This is printed with PRINTT">
	<CRLF>
	<CRLF>

	<TELL "Testing CHRSET (character set - V3 no-op):" CR>
	<CHRSET 0>
	<TELL "Character set operation completed" CR>
	<CRLF>

	<TELL "Testing MARGIN (text margins - V3 no-op):" CR>
	<MARGIN 5 75>
	<TELL "Margin operation completed" CR>
	<CRLF>

	<TELL "Testing PICINF (picture info - V3 stub):" CR>
	<PICINF 1 0>
	<TELL "PICINF operation completed (no graphics in V3)" CR>
	<CRLF>

	<TELL "Testing MOUSE-INFO (mouse - V3 stub):" CR>
	<MOUSE-INFO 0>
	<TELL "MOUSE-INFO operation completed (no mouse in V3)" CR>
	<CRLF>

	<TELL "Testing TYPE? (type checking - stub):" CR>
	<TYPE? 42>
	<TELL "TYPE? operation completed" CR>
	<CRLF>

	<TELL "Testing PRINTTYPE (print type - stub):" CR>
	<PRINTTYPE 42>
	<TELL "PRINTTYPE operation completed" CR>
	<CRLF>

	<TELL "All extended operations working!" CR>
	<TELL "V3 compatibility stubs complete!" CR>
	<QUIT>>
