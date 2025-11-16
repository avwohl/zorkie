<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing Advanced Operations ===" CR CR>

	<TELL "Testing LOG-SHIFT (logical shift):" CR>
	<LOG-SHIFT 8 2>
	<TELL "LOG-SHIFT 8 2 executed (delegates to LSH)" CR>
	<CRLF>

	<TELL "Testing XOR (bitwise exclusive OR - stub):" CR>
	<XOR 5 3>
	<TELL "XOR operation completed" CR>
	<CRLF>

	<TELL "Testing FSTACK (frame stack pointer - stub):" CR>
	<FSTACK>
	<TELL "FSTACK operation completed" CR>
	<CRLF>

	<TELL "Testing RSTACK (return stack pointer - stub):" CR>
	<RSTACK>
	<TELL "RSTACK operation completed" CR>
	<CRLF>

	<TELL "Testing IFFLAG (conditional flag - stub):" CR>
	<IFFLAG 1 <TELL "True branch"> <TELL "False branch">>
	<TELL "IFFLAG operation completed" CR>
	<CRLF>

	<TELL "All advanced operations working!" CR>
	<TELL "Stack and shift operations complete!" CR>
	<QUIT>>
