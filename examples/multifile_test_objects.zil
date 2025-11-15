;"Multi-file compilation test - OBJECTS FILE"
;"This file defines objects and rooms"

<OBJECT PLAYER
    (DESC "yourself")
    (SYNONYM SELF ME MYSELF)>

<OBJECT LAMP
    (DESC "brass lantern")
    (SYNONYM LAMP LANTERN LIGHT)
    (ADJECTIVE BRASS SHINY BRIGHT)
    (FLAGS TAKEBIT)>

<OBJECT SWORD
    (DESC "steel sword")
    (SYNONYM SWORD BLADE WEAPON)
    (ADJECTIVE STEEL SHARP GLEAMING)
    (FLAGS TAKEBIT)>

<OBJECT BOOK
    (DESC "ancient tome")
    (SYNONYM BOOK TOME VOLUME)
    (ADJECTIVE ANCIENT DUSTY LEATHER)
    (FLAGS TAKEBIT)>

<ROOM START-ROOM
    (DESC "Library")
    (LDESC "You are in a grand library filled with ancient books.")
    (FLAGS LIGHTBIT)>

<ROOM ARMORY
    (DESC "Armory")
    (LDESC "This room is filled with weapons and armor.")
    (FLAGS LIGHTBIT)>
