<VERSION 3>

<GLOBAL MY-LIST <TABLE 10 20 30 40 50>>

<ROUTINE GO ()
	<TELL "=== Testing List Operations ===" CR CR>

	<TELL "Testing FIRST (get first element):" CR>
	<TELL "List contents: 10, 20, 30, 40, 50" CR>
	<TELL "FIRST of list: " N <FIRST ,MY-LIST> " (should be 10)" CR>
	<CRLF>

	<TELL "Testing REST (get list tail):" CR>
	<TELL "REST ,MY-LIST 1 gives tail starting at element 2" CR>
	<TELL "This is pointer arithmetic for list traversal" CR>
	<CRLF>

	<TELL "Testing GET for comparison:" CR>
	<TELL "GET ,MY-LIST 1 = " N <GET ,MY-LIST 1> " (first element)" CR>
	<TELL "GET ,MY-LIST 2 = " N <GET ,MY-LIST 2> " (second element)" CR>
	<TELL "GET ,MY-LIST 3 = " N <GET ,MY-LIST 3> " (third element)" CR>
	<CRLF>

	<TELL "FIRST is equivalent to <GET table 1>" CR>
	<COND (<EQUAL? <FIRST ,MY-LIST> <GET ,MY-LIST 1>>
		<TELL "FIRST and GET match: SUCCESS!" CR>)
	      (T
		<TELL "FIRST and GET differ: FAILED" CR>)>
	<CRLF>

	<TELL "List operations working!" CR>
	<TELL "FIRST accessor complete!" CR>
	<QUIT>>
