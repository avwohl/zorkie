<VERSION 3>

<GLOBAL FLAGS 0>

<OBJECT THING>

<ROUTINE GO ()
	<TELL "=== Testing Bitwise Operations ===" CR CR>

	<TELL "Testing BAND (bitwise AND):" CR>
	<SETG FLAGS 15>
	<TELL "FLAGS = " N ,FLAGS " (binary: 1111)" CR>
	<TELL "FLAGS AND 7 = " N <BAND ,FLAGS 7> " (binary: 0111)" CR>
	<CRLF>

	<TELL "Testing BOR (bitwise OR):" CR>
	<SETG FLAGS 12>
	<TELL "FLAGS = " N ,FLAGS " (binary: 1100)" CR>
	<TELL "FLAGS OR 3 = " N <BOR ,FLAGS 3> " (binary: 1111)" CR>
	<CRLF>

	<TELL "Testing BTST (bit test):" CR>
	<SETG FLAGS 8>
	<TELL "FLAGS = " N ,FLAGS " (bit 3 set)" CR>
	<COND (<BTST ,FLAGS 3>
	       <TELL "Bit 3 is SET" CR>)
	      (T
	       <TELL "Bit 3 is CLEAR" CR>)>

	<COND (<BTST ,FLAGS 2>
	       <TELL "Bit 2 is SET" CR>)
	      (T
	       <TELL "Bit 2 is CLEAR" CR>)>

	<CRLF>
	<TELL "Bitwise operations essential for flags!" CR>
	<QUIT>>
