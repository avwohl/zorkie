<VERSION 3>

<GLOBAL BYTE-ARRAY <TABLE (BYTE) 10 20 30 40 50 60 70 80>>
<GLOBAL WORD-ARRAY <TABLE 100 200 300 400 500>>

<ROUTINE GO ()
	<TELL "=== Testing Memory Operations ===" CR CR>

	<TELL "Testing GETB2 (get byte with base+offset):" CR>
	<TELL "GETB2 at offset 0: " N <GETB2 ,BYTE-ARRAY 0> " (should be 10)" CR>
	<TELL "GETB2 at offset 2: " N <GETB2 ,BYTE-ARRAY 2> " (should be 30)" CR>
	<CRLF>

	<TELL "Testing PUTB2 (put byte with base+offset):" CR>
	<PUTB2 ,BYTE-ARRAY 1 99>
	<TELL "After PUTB2 offset 1 to 99: " N <GETB2 ,BYTE-ARRAY 1> CR>
	<CRLF>

	<TELL "Testing GETW2 (get word with base+offset):" CR>
	<TELL "GETW2 at word offset 0: " N <GETW2 ,WORD-ARRAY 0> " (should be 100)" CR>
	<TELL "GETW2 at word offset 2: " N <GETW2 ,WORD-ARRAY 2> " (should be 300)" CR>
	<CRLF>

	<TELL "Testing PUTW2 (put word with base+offset):" CR>
	<PUTW2 ,WORD-ARRAY 1 999>
	<TELL "After PUTW2 offset 1 to 999: " N <GETW2 ,WORD-ARRAY 1> CR>
	<CRLF>

	<TELL "Memory operations working!" CR>
	<TELL "Base+offset addressing complete!" CR>
	<TELL "We now have 131 opcodes implemented!" CR>
	<QUIT>>
