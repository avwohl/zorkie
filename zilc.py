#!/usr/bin/env python3
"""
ZIL Compiler entry point.

Usage: python zilc.py input.zil [-o output.z3] [-v VERSION]
"""

from zilc.compiler import main

if __name__ == '__main__':
    main()
