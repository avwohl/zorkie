<VERSION 3>

<GLOBAL HERE 0>

<ROOM KITCHEN>

<ROOM HALLWAY>

<ROOM BEDROOM>

<ROUTINE GO ()
	<SETG HERE ,KITCHEN>

	<TELL "=== Testing GOTO (Room Movement) ===" CR CR>

	<TELL "Starting location: Kitchen" CR>
	<TELL "HERE variable: " N ,HERE CR>
	<CRLF>

	<TELL "Moving to hallway..." CR>
	<GOTO ,HALLWAY>
	<TELL "Current HERE variable: " N ,HERE CR>
	<CRLF>

	<TELL "Moving to bedroom..." CR>
	<GOTO ,BEDROOM>
	<TELL "Current HERE variable: " N ,HERE CR>
	<CRLF>

	<TELL "GOTO enables player movement between rooms!" CR>
	<QUIT>>
