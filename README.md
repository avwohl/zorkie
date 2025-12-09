# Zorkie

A compiler for the Infocom ZIL/ZILF language that produces Z-machine story files (.z3, .z4, .z5, etc.).

## Installation

### From PyPI

```bash
pip install zorkie
```

### From Source

```bash
git clone https://github.com/yourusername/zorkie.git
cd zorkie
pip install -e .
```

## Usage

```bash
zorkie <source.zil> -o <output.z3>
```

### Options

- `-o <file>` - Specify output file
- `-v <version>` - Target Z-machine version (3-6)

### Example

```bash
zorkie game.zil -o game.z3
```

The output file can be run in any Z-machine interpreter (Frotz, Lectrote, etc.).

## Documentation

- [KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) - Known bugs, limitations, and unsupported features
- [STATUS.md](STATUS.md) - Project status and development history
- [PENDING_FEATURES.md](docs/PENDING_FEATURES.md) - Remaining work and optimizations

## Compatibility

**Works well with**: Infocom-style ZIL (original game sources)

**Limited support for**: ZILF standard library (36% of library files parse successfully)

See [KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) for details on unsupported ZILF/MDL constructs.
