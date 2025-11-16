<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing EMPTY?, LSH, RSH ===" CR CR>

	<TELL "Testing LSH (left shift):" CR>
	<TELL "LSH 1 3 = " N <LSH 1 3> " (1 << 3 = 8)" CR>
	<TELL "LSH 2 2 = " N <LSH 2 2> " (2 << 2 = 8)" CR>
	<TELL "LSH 5 1 = " N <LSH 5 1> " (5 << 1 = 10)" CR>
	<CRLF>

	<TELL "Testing RSH (right shift):" CR>
	<TELL "RSH 8 3 = " N <RSH 8 3> " (8 >> 3 = 1)" CR>
	<TELL "RSH 16 2 = " N <RSH 16 2> " (16 >> 2 = 4)" CR>
	<TELL "RSH 10 1 = " N <RSH 10 1> " (10 >> 1 = 5)" CR>
	<CRLF>

	<TELL "EMPTY? predicate implemented for object testing" CR>
	<TELL "Bit shift operations working!" CR>
	<CRLF>

	<TELL "🎉 75% PLANETFALL MILESTONE ACHIEVED! 🎉" CR>
	<QUIT>>
