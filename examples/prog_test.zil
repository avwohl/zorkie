<VERSION 3>

<GLOBAL COUNTER 0>
<GLOBAL RESULT 0>

<ROUTINE GO ()
	<TELL "=== Testing PROG Sequential Execution ===" CR CR>

	<TELL "Testing PROG with sequential statements:" CR>
	<PROG ()
		<SETG COUNTER 10>
		<TELL "Set COUNTER to 10" CR>
		<SETG COUNTER <+ ,COUNTER 5>>
		<TELL "Added 5 to COUNTER" CR>
		<SETG RESULT ,COUNTER>>
	<TELL "Final COUNTER value: " N ,COUNTER " (should be 15)" CR>
	<CRLF>

	<TELL "Testing PROG with multiple operations:" CR>
	<PROG ()
		<TELL "First statement" CR>
		<TELL "Second statement" CR>
		<TELL "Third statement" CR>
		<SETG RESULT 42>>
	<TELL "RESULT is now: " N ,RESULT CR>
	<CRLF>

	<TELL "Testing nested PROG blocks:" CR>
	<PROG ()
		<SETG COUNTER 1>
		<PROG ()
			<SETG COUNTER <+ ,COUNTER 1>>
			<SETG COUNTER <+ ,COUNTER 1>>>
		<TELL "After nested PROG, COUNTER = " N ,COUNTER CR>>
	<CRLF>

	<TELL "PROG sequential execution working!" CR>
	<TELL "All statements execute in order!" CR>
	<QUIT>>
