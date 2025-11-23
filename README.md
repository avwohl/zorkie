# Zorkie

A compiler for the Infocom ZIL/ZILF language that produces Z-machine story files (.z3, .z4, .z5, etc.).

## Usage

```bash
./zorkie <source.zil> -o <output.z3>
```

### Options

- `-o <file>` - Specify output file
- `-v <version>` - Target Z-machine version (3-6)

### Example

```bash
./zorkie game.zil -o game.z3
```

The output file can be run in any Z-machine interpreter (Frotz, Lectrote, etc.).
