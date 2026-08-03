#!/usr/bin/env python3
"""Measure dead weight in the string table: entries registered but never referenced.

StringTable is append-only -- add_string() writes straight into encoded_data with
no removal and no refcounting -- so any string registered by codegen that is later
discarded (rolled-back speculation, a peephole-deleted print_paddr) stays in the
story file with nothing pointing at it.

This instruments registration (add_string) against actual use (get_address /
get_packed_address, the fixup-resolution paths) and reports the orphans and the
bytes they occupy.

Measured result, trinity @ V4, 2026-07-19: 1,051 strings registered (12,964
bytes), 6 orphaned (66 bytes, 0.5%). The mechanism is real but the payload is
negligible -- this is NOT a viable size lever. Recorded so it is not re-chased.

Usage:
    python3 tools/measure_string_orphans.py tests/test-games/infocom-zil/trinity/trinity.zil 4
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zilc.zmachine.string_table import StringTable  # noqa: E402

REGISTERED = {}   # text -> bytes it added to encoded_data (incl. alignment padding)
USED = set()      # text actually resolved to an address by a fixup

_orig_add = StringTable.add_string
_orig_getp = StringTable.get_packed_address
_orig_geta = StringTable.get_address


def _add_string(self, text):
    before = len(self.encoded_data)
    off = _orig_add(self, text)
    grew = len(self.encoded_data) - before
    if grew:
        REGISTERED[text] = grew
    return off


def _get_packed_address(self, text, version=3):
    USED.add(text)
    return _orig_getp(self, text, version)


def _get_address(self, text):
    USED.add(text)
    return _orig_geta(self, text)


StringTable.add_string = _add_string
StringTable.get_packed_address = _get_packed_address
StringTable.get_address = _get_address


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="entry .zil file")
    ap.add_argument("version", nargs="?", default="3", help="Z-machine version")
    ap.add_argument("--top", type=int, default=25, help="how many orphans to list")
    a = ap.parse_args()

    # A too-large story file still exercises the whole string path, so an
    # over-cap compile (trinity, amfv) reports fine -- that is the point.
    out = Path(tempfile.mkdtemp(prefix="orphan_")) / f"out.z{a.version}"
    sys.argv = ["zorkie", a.source, "-o", str(out), "-v", str(a.version)]
    os.chdir(str(REPO))

    from zilc.compiler import main as compile_main
    try:
        compile_main()
    except SystemExit:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[compile raised] {type(e).__name__}: {e}", file=sys.stderr)

    orphans = {t: n for t, n in REGISTERED.items() if t not in USED}
    total_reg = sum(REGISTERED.values())
    total_orph = sum(orphans.values())

    print("\n=== STRING TABLE ORPHAN REPORT ===")
    print(f"registered strings : {len(REGISTERED)}  ({total_reg} bytes)")
    print(f"never referenced   : {len(orphans)}  ({total_orph} bytes)")
    if total_reg:
        print(f"dead fraction      : {100.0 * total_orph / total_reg:.1f}%")
    if orphans:
        print(f"\n-- {min(a.top, len(orphans))} largest orphans --")
        for t, n in sorted(orphans.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"{n:6d}  {t[:90]!r}")


if __name__ == "__main__":
    main()
