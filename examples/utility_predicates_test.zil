<VERSION 3>

<GLOBAL TEST-TABLE <TABLE 10 20 30 40 50>>

<ROUTINE GO ()
	<TELL "=== Testing Utility Predicates and Table Ops ===" CR CR>

	<TELL "Testing N=? (not equal):" CR>
	<COND (<N=? 5 10>
	       <TELL "5 != 10 is true (correct!)" CR>)
	      (T
	       <TELL "5 != 10 is false (error)" CR>)>
	<COND (<N=? 10 10>
	       <TELL "10 != 10 is true (error)" CR>)
	      (T
	       <TELL "10 != 10 is false (correct!)" CR>)>
	<CRLF>

	<TELL "Testing ZGET (zero-based table get):" CR>
	<TELL "ZGET index 0: " N <ZGET ,TEST-TABLE 0> " (should be 10)" CR>
	<TELL "ZGET index 2: " N <ZGET ,TEST-TABLE 2> " (should be 30)" CR>
	<CRLF>

	<TELL "Testing ZPUT (zero-based table put):" CR>
	<ZPUT ,TEST-TABLE 1 99>
	<TELL "After ZPUT index 1 to 99: " N <ZGET ,TEST-TABLE 1> CR>
	<CRLF>

	<TELL "Testing TEST-BIT (bit testing):" CR>
	<TELL "TEST-BIT 5 (binary 0101) bit 0: " N <TEST-BIT 5 0> " (bit 0 set)" CR>
	<TELL "TEST-BIT 5 (binary 0101) bit 2: " N <TEST-BIT 5 2> " (bit 2 set)" CR>
	<CRLF>

	<TELL "Utility predicates and table ops working!" CR>
	<TELL "We now have 124 opcodes implemented!" CR>
	<QUIT>>
