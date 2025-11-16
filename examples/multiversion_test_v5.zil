<VERSION 5>

<ROUTINE GO ()
	<TELL "=== Testing V5-Specific Features ===" CR CR>

	<TELL "Testing COLOR (V5+ only):" CR>
	<COLOR 2 9>
	<TELL "Text color set to green on white" CR>
	<COLOR 1 1>
	<TELL "Color reset to default" CR>
	<CRLF>

	<TELL "Testing FONT (V5+ only):" CR>
	<FONT 1>
	<TELL "Font set to standard (font 1)" CR>
	<CRLF>

	<TELL "V5 features working!" CR>
	<TELL "Multi-version support enabled!" CR>
	<QUIT>>
