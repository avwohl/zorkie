<VERSION 3>

<GLOBAL FLAG1 1>
<GLOBAL FLAG2 0>
<GLOBAL RESULT 0>

<ROUTINE GO ()
	<TELL "=== Testing Logical Predicates AND? and OR? ===" CR CR>

	<TELL "Testing AND? predicate:" CR>
	<TELL "FLAG1 = " N ,FLAG1 ", FLAG2 = " N ,FLAG2 CR>

	<COND (<AND? ,FLAG1 1>
		<TELL "AND? with both true: SUCCESS" CR>)
	      (T
		<TELL "AND? with both true: FAILED" CR>)>

	<COND (<AND? ,FLAG1 ,FLAG2>
		<TELL "AND? with one false: FAILED" CR>)
	      (T
		<TELL "AND? with one false: SUCCESS (correctly false)" CR>)>
	<CRLF>

	<TELL "Testing OR? predicate:" CR>

	<COND (<OR? ,FLAG1 ,FLAG2>
		<TELL "OR? with one true: SUCCESS" CR>)
	      (T
		<TELL "OR? with one true: FAILED" CR>)>

	<COND (<OR? ,FLAG2 0>
		<TELL "OR? with both false: FAILED" CR>)
	      (T
		<TELL "OR? with both false: SUCCESS (correctly false)" CR>)>
	<CRLF>

	<TELL "Testing complex expressions:" CR>

	<SETG RESULT <AND? 1 1 1>>
	<TELL "AND? of three trues = " N ,RESULT CR>

	<SETG RESULT <OR? 0 0 1>>
	<TELL "OR? with last true = " N ,RESULT CR>

	<CRLF>
	<TELL "Logical predicates working!" CR>
	<TELL "AND? and OR? evaluation complete!" CR>
	<QUIT>>
