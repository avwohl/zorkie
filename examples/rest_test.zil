<VERSION 3>

<CONSTANT C-TABLELEN 10>

<GLOBAL MY-TABLE <ITABLE C-TABLELEN (BYTE) 10 20 30 40 50>>

<ROUTINE GO ()
	<TELL "=== Testing REST (List/Table Operations) ===" CR CR>

	<TELL "Original table: " CR>
	<TELL "First element: " N <GET ,MY-TABLE 1> CR>
	<TELL "Second element: " N <GET ,MY-TABLE 2> CR>
	<TELL "Third element: " N <GET ,MY-TABLE 3> CR>
	<CRLF>

	<TELL "Using REST to skip elements:" CR>
	<TELL "REST by 1: " N <GET <REST ,MY-TABLE 1> 1> CR>
	<TELL "REST by 2: " N <GET <REST ,MY-TABLE 2> 1> CR>
	<CRLF>

	<TELL "REST is essential for list traversal!" CR>
	<QUIT>>
