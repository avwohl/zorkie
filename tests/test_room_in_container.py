# Regression test: a ROOM's IN keyword is overloaded -- (IN ROOMS) is the
# container/parent, (IN TO ROOM) is the IN *direction* exit. A room can have both
# (e.g. Zork 1's WEST-OF-HOUSE: (IN ROOMS) plus (IN TO STONE-BARROW IF WON-FLAG)).
# The direction exit must not clobber the container, or the room's parent is lost
# (it compiled to parent 0, so <IN? ,HERE ,ROOMS> failed and the room name never
# printed).

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zilc.lexer.lexer import Lexer
from zilc.parser.parser import Parser
from zilc.parser.ast_nodes import AtomNode


def _name(v):
    return v.value if isinstance(v, AtomNode) else None


def _room_props(src):
    return Parser(Lexer(src).tokenize()).parse().rooms[0].properties


def test_in_container_preserved_alongside_in_direction():
    props = _room_props(
        "<ROOM START (IN ROOMS) (NORTH TO OTHER) (IN TO OTHER)>")
    # The container ROOMS is still reachable (moved to the LOC alias when the
    # IN-direction exit took the IN slot).
    assert _name(props.get("IN")) == "ROOMS" or _name(props.get("LOC")) == "ROOMS"
    # And the IN-direction exit is present as a direction-exit value.
    inv = props.get("IN")
    assert isinstance(inv, list) and inv and _name(inv[0]) == "TO"


def test_in_container_only_is_the_parent():
    props = _room_props("<ROOM START (IN ROOMS)>")
    assert _name(props.get("IN")) == "ROOMS" or _name(props.get("LOC")) == "ROOMS"
