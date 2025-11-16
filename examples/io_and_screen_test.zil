<VERSION 3>

<GLOBAL TEXT-BUF <ITABLE 120>>
<GLOBAL PARSE-BUF <ITABLE 60>>

<ROUTINE GO ()
	<TELL "=== Testing IO and Screen Control Opcodes ===" CR CR>

	<TELL "Testing CURSET (set cursor position):" CR>
	<CURSET 5 10>
	<TELL "Cursor moved to line 5, column 10" CR>
	<CRLF>

	<TELL "Testing HLIGHT (text highlighting):" CR>
	<HLIGHT 1>
	<TELL "This text should be in reverse video" CR>
	<HLIGHT 0>
	<TELL "Back to normal text" CR>
	<CRLF>

	<TELL "Testing BUFOUT (buffer mode):" CR>
	<BUFOUT 0>
	<TELL "Buffering disabled" CR>
	<BUFOUT 1>
	<TELL "Buffering enabled" CR>
	<CRLF>

	<TELL "Testing UXOR (bitwise XOR):" CR>
	<TELL "UXOR 15 10 = " N <UXOR 15 10> " (should be 5)" CR>
	<TELL "UXOR 255 255 = " N <UXOR 255 255> " (should be 0)" CR>
	<CRLF>

	<TELL "Testing INPUT (read text):" CR>
	<TELL "Type something and press Enter:" CR>
	<INPUT ,TEXT-BUF ,PARSE-BUF>
	<TELL "Input received!" CR>
	<CRLF>

	<TELL "IO and screen control opcodes working!" CR>
	<TELL "We now have 110 opcodes implemented!" CR>
	<QUIT>>
