<VERSION 3>

<GLOBAL COUNTER 10>

<ROUTINE GO ()
	<TELL "=== Testing DLESS? (decrement and test less) ===" CR CR>

	<TELL "Initial COUNTER value: " N ,COUNTER CR>
	<CRLF>

	<TELL "Testing DLESS? in loop:" CR>
	<REPEAT ()
		<COND (<DLESS? COUNTER 5>
		       <TELL "COUNTER now " N ,COUNTER " (< 5, continuing)" CR>)
		      (T
		       <TELL "COUNTER now " N ,COUNTER " (>= 5, stopping)" CR>
		       <RETURN>)>>
	<CRLF>

	<TELL "Final COUNTER value: " N ,COUNTER CR>
	<TELL "DLESS? opcode working!" CR>
	<TELL "We now have 115 opcodes implemented!" CR>
	<QUIT>>
