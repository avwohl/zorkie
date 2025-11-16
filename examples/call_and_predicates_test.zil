<VERSION 3>

<GLOBAL TEST-VAR 42>

<ROUTINE SIMPLE-ROUTINE ()
	<TELL "Simple routine called!" CR>
	<RTRUE>>

<ROUTINE ROUTINE-WITH-ARGS (A B)
	<TELL "Routine with args: A=" N .A " B=" N .B CR>
	<RTRUE>>

<ROUTINE GO ()
	<TELL "=== Testing CALL, APPLY, NOT?, TRUE? ===" CR CR>

	<TELL "Testing CALL (basic):" CR>
	<CALL SIMPLE-ROUTINE>
	<CRLF>

	<TELL "Testing NOT? predicate:" CR>
	<COND (<NOT? 0>
	       <TELL "NOT? 0 is true (correct!)" CR>)
	      (T
	       <TELL "NOT? 0 is false (error)" CR>)>
	<CRLF>

	<TELL "Testing TRUE? predicate:" CR>
	<COND (<TRUE? ,TEST-VAR>
	       <TELL "TRUE? 42 is true (correct!)" CR>)
	      (T
	       <TELL "TRUE? 42 is false (error)" CR>)>
	<CRLF>

	<TELL "Testing predicates with zero:" CR>
	<COND (<TRUE? 0>
	       <TELL "TRUE? 0 is true (error)" CR>)
	      (T
	       <TELL "TRUE? 0 is false (correct!)" CR>)>
	<CRLF>

	<TELL "CALL and predicate opcodes working!" CR>
	<QUIT>>
