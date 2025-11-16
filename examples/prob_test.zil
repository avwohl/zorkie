<VERSION 3>

<GLOBAL SUCCESS-COUNT 0>
<GLOBAL TRIAL-COUNT 0>
<CONSTANT TRIALS 10>

<ROUTINE GO ()
	<TELL "=== Testing PROB (Probability) ===" CR CR>

	<TELL "Running " N ,TRIALS " trials with 50% probability..." CR>
	<CRLF>

	<REPEAT ()
		<COND (<IGRTR? ,TRIAL-COUNT ,TRIALS>
		       <RETURN>)>

		<TELL "Trial " N ,TRIAL-COUNT ": ">

		<COND (<PROB 50>
		       <TELL "Success!" CR>
		       <SETG SUCCESS-COUNT <+ ,SUCCESS-COUNT 1>>)
		      (T
		       <TELL "Failure." CR>)>>

	<CRLF>
	<TELL "Results: " N ,SUCCESS-COUNT " successes out of " N ,TRIALS " trials" CR>
	<TELL "PROB enables randomized game events!" CR>
	<QUIT>>
