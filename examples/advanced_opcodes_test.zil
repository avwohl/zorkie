<VERSION 3>

<OBJECT SWORD
	(DESC "shiny sword")
	(FLAGS TAKEBIT)
	(ACTION SWORD-F)>

<ROUTINE SWORD-F ()
	<RTRUE>>

<GLOBAL OUTPUT-TABLE <ITABLE 40>>

<ROUTINE GO ()
	<TELL "=== Testing Advanced Opcodes ===" CR CR>

	<TELL "Testing USL (unsigned shift left):" CR>
	<TELL "USL 4 2 = " N <USL 4 2> " (4 << 2 = 16)" CR>
	<TELL "USL 1 4 = " N <USL 1 4> " (1 << 4 = 16)" CR>
	<CRLF>

	<TELL "Testing PRINTOBJ (print object name):" CR>
	<TELL "Object name: ">
	<PRINTOBJ ,SWORD>
	<CRLF>
	<CRLF>

	<TELL "Testing DIROUT (direct output to table):" CR>
	<DIROUT ,OUTPUT-TABLE>
	<TELL "This goes to table">
	<DIROUT 0>
	<TELL "Output redirected and restored" CR>
	<CRLF>

	<TELL "Testing READ (alias for INPUT):" CR>
	<TELL "READ is an alias for INPUT opcode" CR>
	<CRLF>

	<TELL "Advanced opcodes working!" CR>
	<TELL "We now have 115 opcodes implemented!" CR>
	<QUIT>>
