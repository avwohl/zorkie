# Zorkie

A from-scratch **ZIL / ZILF → Z-machine compiler**, written in Python. It reads
Infocom's Zork Implementation Language (the original historicalsource dialect and
much of the modern ZILF dialect) and emits Z-machine story files (`.z3`–`.z8`)
that run in any standard interpreter (Frotz, Bocfel, Lectrote, Gargoyle) — or in
the [zwalker](https://github.com/avwohl/zwalker) interpreter, which is used to
test zorkie end to end (see [Testing](#testing)).

The goal is a complete, readable, MIT-era-faithful ZIL toolchain in Python:
compiler now, decompiler (`.z` → ZIL) planned.

## Status

Zorkie is a working compiler under active development. Honest snapshot:

**The milestone: a real Infocom game compiles and plays to a verified win.**
Zorkie compiles the historical **Mini-Zork I** source (`mini.zil`, Release 0,
1987) to a `.z3` that plays the *complete game* to its 350/350 Stone Barrow
victory under the zwalker interpreter — a 420-command verified replay whose
room-by-room and score-by-score progression is lockstep-identical to the
official binary over the whole route.

**What works today**
- **The Z-machine back end is broad and well-tested.** The instruction set,
  headers, object/property tables, dictionary, ZSCII text + abbreviations, and
  routine/packed-address layout are implemented (V3 is the version that compiles
  real games). The pytest suite — much of it ported from ZILF's own integration
  and interpreter tests — runs green apart from a few known, unrelated failures.
- **Small games compile and *run*, including interactive ones.** Games with a
  `READ` loop, a dictionary, verb dispatch, movement, objects, scoring and a real
  win condition compile to a story file that plays correctly in an interpreter.
  The zwalker integration suite (below) drives four games — three purpose-built
  ones plus the real Mini-Zork I — to a verified win.
- **The ZILF standard library parses fully.** The library `parser.zil` /
  `verbs.zil` / `scope.zil` / … (pulled in via `<INSERT-FILE>`) lex and parse end
  to end, including MDL quasiquote/unquote templates and `%<…>` compile-time
  forms. `~40` real Infocom source trees are vendored under
  `tests/test-games/infocom-zil/` for compilation testing.

**The frontier (not done yet)**
- **The rest of the Infocom catalog.** zork1, zork3 and starcross compile and
  boot but don't yet play to a win (next up: the lockstep-differ method that won
  minizork — run the official binary and the zorkie build side by side and fix
  the first divergence, repeatedly). A text-compression gap pushes nine more
  games over the story-file size limit, `PRSO?`/`PRSI?` parser macros are
  unexpanded (zork2 and others), and the compile-time MDL/`DEFMAC` evaluator
  (e.g. `LIBRARY-MESSAGE` in the ZILF library, which blocks Cloak of Darkness)
  is still open. See **[STATUS.md](STATUS.md)** for the measured, per-game
  frontier.

## Installation

```bash
git clone https://github.com/avwohl/zorkie.git
cd zorkie
pip install -e .
```

Requires Python 3.8+. No third-party runtime dependencies for the compiler.

## Usage

```bash
zorkie <source.zil> -o <output.z3> -v <version>
```

Options:
- `-o <file>` — output story file
- `-v <n>` — target Z-machine version (default 3; V1–V8 supported)

Example:

```bash
zorkie game.zil -o game.z3 -v 3
```

`<INSERT-FILE "name">` directives are resolved relative to the source file, so a
game that pulls in a library (`<INSERT-FILE "parser">`) compiles as one unit.

## Testing

Zorkie is tested two ways.

**1. Unit / integration tests (pytest).** Opcode encoding, codegen, macros,
tables, TELL, parsing, and version differences — much of it converted from
ZILF's own test suites:

```bash
python -m pytest -q          # green apart from a few known, unrelated failures
```

**2. End-to-end "compile → play → win" (via zwalker).** The
[zwalker](https://github.com/avwohl/zwalker) project compiles a ZIL game with
zorkie, runs the resulting story file in its own Z-machine interpreter, and
replays a walkthrough to the game's real winning ending — the strongest test
that zorkie's output is not just structurally valid but *behaviorally correct*.
Its `scripts/test_zorkie_game.py` keeps a green suite of self-contained games
(a vault puzzle, a movement+key maze, an arithmetic reactor) plus the real
**Mini-Zork I** (compiled from `mini.zil` and replayed to its 350/350 win), with
Cloak of Darkness as the tracked frontier:

```
zorkie L2 suite: 4/4 games play-and-win  (microquest, mazekey, reactor, minizork)
frontier (not counted): cloak -> not yet
```

This loop is what surfaces real codegen bugs (e.g. multi-operand `JE`/`EQUAL?`
mis-encoding large dictionary-word constants — the standard IF verb-dispatch
idiom — was found and fixed this way).

For comparing a compiled `.z` against a ZILF/official golden, see
`tests/test-games/compare-zcode.sh`.

## Architecture

```
zilc/
├── lexer/        ZIL tokenizer (atoms, forms, strings, %< >, ! splices, ` ~ quasiquote)
├── parser/       recursive-descent parser -> AST (ast_nodes.py)
│   └── macro_expander.py   DEFMAC / SPLICE expansion
├── codegen/      AST -> Z-machine bytecode (codegen_improved.py); headers, objects,
│                 dictionary, strings, routines, packed addresses, per-version encoding
└── compiler.py   pipeline: preprocess (INSERT-FILE, control chars, ZILF directives)
                  -> lex -> parse -> expand -> codegen -> assemble story file
```

## Documentation

- [STATUS.md](STATUS.md) — measured project status, per-game frontier, next steps
- [docs/ZIL_SPECIFICATION.md](docs/ZIL_SPECIFICATION.md) — the ZIL language
- [docs/ZMACHINE_SPECIFICATION.md](docs/ZMACHINE_SPECIFICATION.md) — the Z-machine bytecode format
- [docs/ZMACHINE_GAMES_BY_VERSION.md](docs/ZMACHINE_GAMES_BY_VERSION.md) — Z-machine version reference

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
