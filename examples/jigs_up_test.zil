<VERSION 3>

<GLOBAL DANGER-LEVEL 0>

<ROUTINE GO ()
	<TELL "=== Testing JIGS-UP (Game Over) ===" CR CR>

	<TELL "You find yourself in a dangerous situation..." CR>
	<SETG DANGER-LEVEL 1>
	<TELL "Danger level: " N ,DANGER-LEVEL CR>
	<CRLF>

	<TELL "The danger increases..." CR>
	<SETG DANGER-LEVEL 2>
	<TELL "Danger level: " N ,DANGER-LEVEL CR>
	<CRLF>

	<TELL "The danger becomes critical..." CR>
	<SETG DANGER-LEVEL 3>
	<TELL "Danger level: " N ,DANGER-LEVEL CR>
	<CRLF>

	<COND (<G? ,DANGER-LEVEL 2>
	       <JIGS-UP "The danger was too great!">)>

	<TELL "You survived!" CR>
	<QUIT>>
