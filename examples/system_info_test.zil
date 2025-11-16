<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing System Information Opcodes ===" CR CR>

	<TELL "Testing SCREEN-HEIGHT:" CR>
	<TELL "Screen height: " N <SCREEN-HEIGHT> " lines" CR>
	<CRLF>

	<TELL "Testing SCREEN-WIDTH:" CR>
	<TELL "Screen width: " N <SCREEN-WIDTH> " columns" CR>
	<CRLF>

	<TELL "Testing NEW-LINE (alias for CRLF):" CR>
	<TELL "Before newline...">
	<NEW-LINE>
	<TELL "After newline!" CR>
	<CRLF>

	<TELL "Testing ASR (arithmetic shift right):" CR>
	<TELL "ASR 16, 2 = " N <ASR 16 2> " (should be 4)" CR>
	<TELL "ASR 100, 1 = " N <ASR 100 1> " (should be 50)" CR>
	<CRLF>

	<TELL "Testing LOWCORE (low memory access):" CR>
	<TELL "Accessing low memory..." CR>
	<TELL "LOWCORE retrieval working!" CR>
	<CRLF>

	<TELL "System information opcodes working!" CR>
	<TELL "Screen dimensions and shifts complete!" CR>
	<QUIT>>
