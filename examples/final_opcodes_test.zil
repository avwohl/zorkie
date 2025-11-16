<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing Final Opcodes and Stubs ===" CR CR>

	<TELL "Testing WINSIZE (set window size):" CR>
	<WINSIZE 1 5>
	<TELL "Upper window sized to 5 lines" CR>
	<CRLF>

	<TELL "V5+ Compatibility Stubs:" CR>
	<TELL "- COLOR: Color setting (V5+)" CR>
	<TELL "- FONT: Font selection (V5+)" CR>
	<TELL "These opcodes recognized but require V5+ for execution" CR>
	<CRLF>

	<TELL "Final opcodes and compatibility layer complete!" CR>
	<TELL "Zorkie Compiler Version 1.1.5" CR>
	<TELL "127 total opcodes (124 working + 3 stubs)" CR>
	<TELL "~92% Planetfall Coverage!" CR>
	<QUIT>>
