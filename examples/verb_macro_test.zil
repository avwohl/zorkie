;"Test VERB? macro - simplified version first"

<VERSION 3>

;"Parser globals"
<GLOBAL PRSA 0>

;"Action constants"
<CONSTANT V?TAKE 1>
<CONSTANT V?DROP 2>
<CONSTANT V?EXAMINE 3>
<CONSTANT V?OPEN 4>

;"Simplified VERB? macro - single verb check"
;"Eventually needs to support: <VERB? TAKE DROP EXAMINE>"
<DEFMAC VERB?-SIMPLE (VERB)
	<FORM EQUAL? ',PRSA <FORM GVAL <FORM QUOTE .VERB>>>>

;"For now, test a basic version that checks one verb"
<ROUTINE TEST-ACTION ()
	<SETG PRSA ,V?TAKE>

	;"This should expand to: <EQUAL? ,PRSA <GVAL 'TAKE>>"
	;"Or simplified: <EQUAL? ,PRSA ,V?TAKE>"
	<COND (<VERB?-SIMPLE V?TAKE>
	       <TELL "Take action matched!" CR>
	       <RTRUE>)
	      (T
	       <TELL "No match" CR>
	       <RFALSE>)>>

<ROUTINE GO ()
	<TELL "Testing VERB? macro..." CR>
	<TEST-ACTION>
	<QUIT>>
