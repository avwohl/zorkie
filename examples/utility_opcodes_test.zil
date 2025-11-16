<VERSION 3>

<ROUTINE GO ()
	<TELL "=== Testing ABS, SOUND, CLEAR, SPLIT, SCREEN ===" CR CR>

	<TELL "Testing ABS (absolute value):" CR>
	<TELL "ABS -5 = " N <ABS -5> " (should be 5)" CR>
	<TELL "ABS 10 = " N <ABS 10> " (should be 10)" CR>
	<TELL "ABS 0 = " N <ABS 0> " (should be 0)" CR>
	<CRLF>

	<TELL "Testing SOUND (sound effects):" CR>
	<TELL "Playing sound effect 1..." CR>
	<SOUND 1>
	<TELL "Sound effect played (if supported)" CR>
	<CRLF>

	<TELL "Testing CLEAR (clear screen):" CR>
	<TELL "About to clear screen..." CR>
	<CLEAR>
	<TELL "Screen cleared!" CR>
	<CRLF>

	<TELL "Testing SPLIT (split window):" CR>
	<SPLIT 3>
	<TELL "Window split into 3-line upper and lower sections" CR>
	<CRLF>

	<TELL "Testing SCREEN (select window):" CR>
	<SCREEN 0>
	<TELL "Selected lower window (0)" CR>
	<CRLF>

	<TELL "Utility opcodes working!" CR>
	<TELL "We now have 105 opcodes implemented!" CR>
	<QUIT>>
