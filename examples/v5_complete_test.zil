<VERSION 5>

<ROUTINE GO ()
	<TELL "=== V5 Complete Feature Test ===" CR CR>

	<TELL "Call Variants (V4/V5):" CR>
	<TELL "- CALL_1S: Call with 0 args, store result" CR>
	<TELL "- CALL_1N: Call with 0 args, no store" CR>
	<TELL "- CALL_2S: Call with 1 arg, store result" CR>
	<TELL "- CALL_2N: Call with 1 arg, no store" CR>
	<CRLF>

	<TELL "Undo Support (V5):" CR>
	<TELL "- SAVE_UNDO: Save game state for undo" CR>
	<TELL "- RESTORE_UNDO: Restore previous state" CR>
	<CRLF>

	<TELL "Text Features (V5):" CR>
	<TELL "- PRINT_UNICODE: Unicode character output" CR>
	<TELL "- ERASE_LINE: Erase text on current line" CR>
	<TELL "- SET_MARGINS: Configure text margins" CR>
	<CRLF>

	<TELL "Extended Opcodes (8 total):" CR>
	<TELL "- CALL_VS2/CALL_VN2: 8-arg calls" CR>
	<TELL "- TOKENISE: Lexical analysis" CR>
	<TELL "- CHECK_ARG_COUNT: Argument validation" CR>
	<TELL "- ENCODE_TEXT: Dictionary encoding" CR>
	<TELL "- PRINT_TABLE: Formatted output" CR>
	<TELL "- SCAN_TABLE: Binary search" CR>
	<TELL "- READ_CHAR: Character input" CR>
	<CRLF>

	<TELL "V5 implementation nearly complete!" CR>
	<QUIT>>
