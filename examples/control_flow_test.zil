<VERSION 3>

<GLOBAL COUNTER 0>

<ROUTINE TEST-RFATAL ()
	<TELL "Testing RFATAL (return false)..." CR>
	<RFATAL>>

<ROUTINE GO ()
	<TELL "=== Testing Control Flow Opcodes ===" CR CR>

	<TELL "Testing RFATAL:" CR>
	<COND (<TEST-RFATAL>
	       <TELL "RFATAL returned true (unexpected!)" CR>)
	      (T
	       <TELL "RFATAL returned false (correct!)" CR>)>
	<CRLF>

	<TELL "Testing AGAIN in loop:" CR>
	<SETG COUNTER 0>
	<REPEAT ()
		<SETG COUNTER <+ ,COUNTER 1>>
		<TELL "Counter: " N ,COUNTER CR>

		<COND (<EQUAL? ,COUNTER 3>
		       <TELL "Skipping 4..." CR>
		       <SETG COUNTER 4>
		       <AGAIN>)>

		<COND (<G? ,COUNTER 6>
		       <TELL "Done!" CR>
		       <RETURN>)>>

	<CRLF>
	<TELL "Control flow opcodes working!" CR>
	<QUIT>>
