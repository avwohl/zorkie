<VERSION 5>

<ROUTINE GO ()
	<TELL "=== Testing V5 Extended Opcodes ===" CR CR>

	<TELL "Testing CALL_VS2 (up to 8 args):" CR>
	<CALL_VS2 TEST-ROUTINE 1 2 3 4 5>
	<CRLF>

	<TELL "Testing CALL_VN2 (no store, up to 8 args):" CR>
	<CALL_VN2 PRINT-ARGS 10 20 30>
	<CRLF>

	<TELL "Testing CHECK_ARG_COUNT:" CR>
	<CHECK_ARG_COUNT 0>
	<TELL "Called with at least 0 args" CR>
	<CRLF>

	<TELL "Testing table operations (V5 versions):" CR>
	<TELL "COPYT with COPY_TABLE opcode" CR>
	<TELL "ZERO with zeroing operation" CR>
	<CRLF>

	<TELL "V5 extended opcodes working!" CR>
	<QUIT>>

<ROUTINE TEST-ROUTINE (A B C D E)
	<TELL "TEST-ROUTINE called with args: ">
	<PRINTN A> <PRINTC 32>
	<PRINTN B> <PRINTC 32>
	<PRINTN C> <PRINTC 32>
	<PRINTN D> <PRINTC 32>
	<PRINTN E> <CRLF>>

<ROUTINE PRINT-ARGS (X Y Z)
	<TELL "PRINT-ARGS: ">
	<PRINTN X> <PRINTC 32>
	<PRINTN Y> <PRINTC 32>
	<PRINTN Z> <CRLF>>
