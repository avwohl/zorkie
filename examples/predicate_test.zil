;"Test various predicates and comparison operators"

<VERSION 3>

<GLOBAL TEST-VAR 0>
<GLOBAL COUNT 5>

<ROUTINE GO ()
	<TELL "Testing predicates..." CR CR>

	;"Test ZERO?"
	<SETG TEST-VAR 0>
	<COND (<ZERO? ,TEST-VAR>
	       <TELL "ZERO? test passed: Variable is zero!" CR>)
	      (T
	       <TELL "ZERO? test failed!" CR>)>

	<SETG TEST-VAR 10>
	<COND (<ZERO? ,TEST-VAR>
	       <TELL "ZERO? wrong: Non-zero detected as zero!" CR>)
	      (T
	       <TELL "ZERO? test passed: Non-zero correctly detected!" CR>)>

	<CRLF>

	;"Test EQUAL?"
	<SETG TEST-VAR 5>
	<COND (<EQUAL? ,TEST-VAR ,COUNT>
	       <TELL "EQUAL? test passed: 5 = 5!" CR>)
	      (T
	       <TELL "EQUAL? test failed!" CR>)>

	;"Test L? (less than)"
	<SETG TEST-VAR 3>
	<COND (<L? ,TEST-VAR ,COUNT>
	       <TELL "L? test passed: 3 < 5!" CR>)
	      (T
	       <TELL "L? test failed!" CR>)>

	;"Test G? (greater than)"
	<SETG TEST-VAR 10>
	<COND (<G? ,TEST-VAR ,COUNT>
	       <TELL "G? test passed: 10 > 5!" CR>)
	      (T
	       <TELL "G? test failed!" CR>)>

	<CRLF>
	<TELL "All predicate tests complete!" CR>
	<QUIT>>
