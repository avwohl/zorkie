<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing MIN and MAX Opcodes ===" CR CR>

	<TELL "Testing MIN:" CR>
	<TELL "MIN 5 10 = " N <MIN 5 10> CR>
	<TELL "MIN 10 5 = " N <MIN 10 5> CR>
	<TELL "MIN 7 7 = " N <MIN 7 7> CR>
	<TELL "MIN 0 100 = " N <MIN 0 100> CR>
	<CRLF>

	<TELL "Testing MAX:" CR>
	<TELL "MAX 5 10 = " N <MAX 5 10> CR>
	<TELL "MAX 10 5 = " N <MAX 10 5> CR>
	<TELL "MAX 7 7 = " N <MAX 7 7> CR>
	<TELL "MAX 0 100 = " N <MAX 0 100> CR>
	<CRLF>

	<TELL "MIN and MAX opcodes working!" CR>
	<QUIT>>
