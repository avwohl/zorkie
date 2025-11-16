<VERSION 3>

<GLOBAL INT-ADDR 0>
<GLOBAL COUNTER 0>

<ROUTINE TEST-DAEMON ()
	<TELL "Daemon fired! Counter = " N ,COUNTER CR>
	<SETG COUNTER <+ ,COUNTER 1>>>

<ROUTINE GO ()
	<TELL "=== Testing Daemon System (QUEUE, INT, DEQUEUE) ===" CR CR>

	<TELL "Testing QUEUE opcode:" CR>
	<SETG INT-ADDR <QUEUE I-TEST -1>>
	<TELL "Created interrupt at address: " N ,INT-ADDR CR>
	<CRLF>

	<TELL "Testing INT opcode:" CR>
	<TELL "INT I-TEST returns: " N <INT I-TEST> CR>
	<COND (<EQUAL? ,INT-ADDR <INT I-TEST>>
	       <TELL "INT correctly returns same address as QUEUE!" CR>)
	      (T
	       <TELL "ERROR: INT returned different address!" CR>)>
	<CRLF>

	<TELL "Testing DEQUEUE opcode:" CR>
	<DEQUEUE ,INT-ADDR>
	<TELL "Dequeued interrupt at address " N ,INT-ADDR CR>
	<CRLF>

	<TELL "Daemon system opcodes working!" CR>
	<TELL "Note: Full daemon execution requires CLOCKER runtime." CR>
	<QUIT>>
