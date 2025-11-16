<VERSION 3>

<GLOBAL MESSAGES <TABLE 5 "Hello!" "Greetings!" "Welcome!" "Hi there!" "Good day!">>

<ROUTINE GO ()
	<TELL "=== Testing PICK-ONE (Random Selection) ===" CR CR>

	<TELL "Message table contains 5 greetings:" CR>
	<TELL "1. Hello!" CR>
	<TELL "2. Greetings!" CR>
	<TELL "3. Welcome!" CR>
	<TELL "4. Hi there!" CR>
	<TELL "5. Good day!" CR>
	<CRLF>

	<TELL "Picking 5 random messages:" CR>
	<TELL "1. " <PICK-ONE ,MESSAGES> CR>
	<TELL "2. " <PICK-ONE ,MESSAGES> CR>
	<TELL "3. " <PICK-ONE ,MESSAGES> CR>
	<TELL "4. " <PICK-ONE ,MESSAGES> CR>
	<TELL "5. " <PICK-ONE ,MESSAGES> CR>

	<CRLF>
	<TELL "PICK-ONE provides variety in game responses!" CR>
	<QUIT>>
