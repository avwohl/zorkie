<VERSION 3>

<GLOBAL COUNTER 0>
<CONSTANT MAX-COUNT 5>

<ROUTINE GO ()
	<TELL "=== Testing IGRTR? (Increment and Greater) ===" CR CR>

	<TELL "Starting counter: " N ,COUNTER CR>
	<TELL "Maximum count: " N ,MAX-COUNT CR>
	<CRLF>

	<TELL "Incrementing until counter > " N ,MAX-COUNT CR>
	<REPEAT ()
		<SETG COUNTER <+ ,COUNTER 1>>
		<TELL "Counter: " N ,COUNTER>

		<COND (<IGRTR? ,COUNTER ,MAX-COUNT>
		       <TELL " - Exceeded maximum!" CR>
		       <RETURN>)>

		<TELL CR>>

	<CRLF>
	<TELL "Final counter value: " N ,COUNTER CR>
	<TELL "IGRTR? is useful for loop control!" CR>
	<QUIT>>
