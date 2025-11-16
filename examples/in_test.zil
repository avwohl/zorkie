;"Test IN? predicate for object containment"

<VERSION 3>

<OBJECT PLAYER
	(DESC "yourself")>

<OBJECT BOX
	(DESC "cardboard box")>

<OBJECT LAMP
	(DESC "brass lantern")>

<ROOM START-ROOM
	(DESC "Test Room")
	(LDESC "A room for testing.")>

<ROUTINE GO ()
	<TELL "Testing IN? predicate..." CR>

	;"Place lamp in box"
	<MOVE LAMP BOX>
	<TELL "Lamp is now in box." CR>

	;"Test IN?"
	<COND (<IN? LAMP BOX>
	       <TELL "IN? test passed: Lamp is in box!" CR>)
	      (T
	       <TELL "IN? test failed!" CR>)>

	;"Move box to room"
	<MOVE BOX START-ROOM>

	;"Lamp should NOT be directly in room (it's in box)"
	<COND (<IN? LAMP START-ROOM>
	       <TELL "Wrong: Lamp appears to be in room!" CR>)
	      (T
	       <TELL "Correct: Lamp is not directly in room." CR>)>

	;"Box should be in room"
	<COND (<IN? BOX START-ROOM>
	       <TELL "Correct: Box is in room!" CR>)
	      (T
	       <TELL "Wrong: Box not detected in room!" CR>)>

	<TELL "IN? tests complete!" CR>
	<QUIT>>
