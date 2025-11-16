;"Test Planetfall-style macros with quotes"

<VERSION 3>

<CONSTANT C-ENABLED? 0>
<CONSTANT C-ENABLED 1>
<CONSTANT C-DISABLED 0>
<CONSTANT DOORBIT 5>
<CONSTANT CONTBIT 6>

;"From Planetfall misc.zil"
<DEFMAC ENABLE ('INT) <FORM PUT .INT ,C-ENABLED? 1>>

<DEFMAC DISABLE ('INT) <FORM PUT .INT ,C-ENABLED? 0>>

<DEFMAC OPENABLE? ('OBJ)
	<FORM OR <FORM FSET? .OBJ ',DOORBIT>
	         <FORM FSET? .OBJ ',CONTBIT>>>

<DEFMAC ABS ('NUM)
	<FORM COND (<FORM L? .NUM 0> <FORM - 0 .NUM>)
	           (T .NUM)>>

<GLOBAL TEST-TABLE <ITABLE 2 0 0>>
<GLOBAL TEST-NUM -5>
<GLOBAL RESULT 0>

<ROUTINE GO ()
	<TELL "Testing Planetfall macros..." CR>

	;"Test ENABLE macro"
	<ENABLE TEST-TABLE>

	;"Test ABS macro with negative number"
	<SETG RESULT <ABS ,TEST-NUM>>

	<TELL "ABS(-5) = ">
	<PRINTN ,RESULT>
	<CRLF>

	<TELL "Planetfall macros work!" CR>
	<QUIT>>
