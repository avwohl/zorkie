<VERSION 3>

<GLOBAL WINNER 0>

<OBJECT PLAYER>

<OBJECT LAMP
	(IN PLAYER)>

<OBJECT BOX>

<ROUTINE GO ()
	<SETG WINNER ,PLAYER>

	<TELL "=== Testing HELD? Predicate ===" CR CR>

	<TELL "The lamp is " >
	<COND (<HELD? ,LAMP>
	       <TELL "held by you." CR>)
	      (T
	       <TELL "not held." CR>)>

	<TELL "The box is ">
	<COND (<HELD? ,BOX>
	       <TELL "held by you." CR>)
	      (T
	       <TELL "not held." CR>)>

	<CRLF>
	<TELL "Moving box to player..." CR>
	<MOVE ,BOX ,PLAYER>

	<TELL "Now the box is ">
	<COND (<HELD? ,BOX>
	       <TELL "held by you." CR>)
	      (T
	       <TELL "not held." CR>)>

	<CRLF>
	<TELL "HELD? is essential for inventory checks!" CR>
	<QUIT>>
