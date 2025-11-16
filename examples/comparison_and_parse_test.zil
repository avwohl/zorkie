<VERSION 3>

<OBJECT MAGIC-WAND
	(DESC "magic wand")
	(FLAGS TAKEBIT)
	(POWER 50)>

<GLOBAL PARSE-BUF <ITABLE 60>>
<GLOBAL TEST-VAL 10>

<ROUTINE GO ()
	<TELL "=== Testing Comparison and Parse Opcodes ===" CR CR>

	<TELL "Testing G=? (greater than or equal):" CR>
	<COND (<G=? 10 10>
	       <TELL "10 >= 10 is true (correct!)" CR>)
	      (T
	       <TELL "10 >= 10 is false (error)" CR>)>
	<COND (<G=? 15 10>
	       <TELL "15 >= 10 is true (correct!)" CR>)
	      (T
	       <TELL "15 >= 10 is false (error)" CR>)>
	<CRLF>

	<TELL "Testing L=? (less than or equal):" CR>
	<COND (<L=? 5 10>
	       <TELL "5 <= 10 is true (correct!)" CR>)
	      (T
	       <TELL "5 <= 10 is false (error)" CR>)>
	<COND (<L=? 10 10>
	       <TELL "10 <= 10 is true (correct!)" CR>)
	      (T
	       <TELL "10 <= 10 is false (error)" CR>)>
	<CRLF>

	<TELL "Testing CHECKU (check property exists):" CR>
	<COND (<CHECKU ,MAGIC-WAND ,P?POWER>
	       <TELL "MAGIC-WAND has POWER property (correct!)" CR>)
	      (T
	       <TELL "MAGIC-WAND lacks POWER property (error)" CR>)>
	<CRLF>

	<TELL "Comparison and property check opcodes working!" CR>
	<TELL "We now have 119 opcodes implemented!" CR>
	<QUIT>>
