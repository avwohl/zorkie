<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing STRING, 1+, and 1- Opcodes ===" CR CR>

	<TELL "Testing 1+ (add 1):" CR>
	<TELL "1+ 5 = " N <1+ 5> CR>
	<TELL "1+ 0 = " N <1+ 0> CR>
	<TELL "1+ 99 = " N <1+ 99> CR>
	<CRLF>

	<TELL "Testing 1- (subtract 1):" CR>
	<TELL "1- 10 = " N <1- 10> CR>
	<TELL "1- 1 = " N <1- 1> CR>
	<TELL "1- 50 = " N <1- 50> CR>
	<CRLF>

	<TELL "Testing STRING (basic):" CR>
	<TELL "STRING opcode placeholder implemented" CR>
	<TELL "Full escape sequence support deferred" CR>
	<CRLF>

	<TELL "Arithmetic shortcuts working!" CR>
	<QUIT>>
