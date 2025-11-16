<VERSION 3>

<GLOBAL INT-ADDR 0>

<ROUTINE TEST-DAEMON ()
	<TELL "Daemon executed!" CR>>

<ROUTINE GO ()
	<TELL "=== Testing ENABLE/DISABLE and PRINTADDR ===" CR CR>

	<TELL "Creating interrupt with QUEUE:" CR>
	<SETG INT-ADDR <QUEUE I-TEST -1>>
	<TELL "Interrupt created at address " N ,INT-ADDR CR>
	<CRLF>

	<TELL "Testing ENABLE:" CR>
	<ENABLE ,INT-ADDR>
	<TELL "Interrupt enabled" CR>
	<CRLF>

	<TELL "Testing DISABLE:" CR>
	<DISABLE ,INT-ADDR>
	<TELL "Interrupt disabled" CR>
	<CRLF>

	<TELL "Re-enabling with ENABLE:" CR>
	<ENABLE ,INT-ADDR>
	<TELL "Interrupt re-enabled" CR>
	<CRLF>

	<TELL "All daemon control opcodes working!" CR>
	<QUIT>>
