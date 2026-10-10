#!/usr/bin/env python3
"""Output-artifact validator for the --check-env preflights (issue #91).

A zero simulator exit and a log free of fatal patterns do not prove the
analysis produced anything. This checks the artifacts a bench promises:

  --wrdata PATH:NCOLS:MINROWS   wrdata file exists, is nonempty, and every
                                line is exactly NCOLS finite floats, with at
                                least MINROWS rows (catches empty, truncated,
                                malformed and nan/inf output).
  --marker NAME                 the log has a `NAME <finite float>` line from
                                the bench's `echo` (stress/cgate benches write
                                no wrdata).

No spec thresholds: only presence, structure and finiteness. Exit 0 = all
artifacts usable, 1 = a problem (diagnosed on stderr), 2 = usage error.
Stdlib only; needs no PDK or simulator.
"""
import argparse
import math
import sys


def wrdata_problem(path, ncols, minrows):
    try:
        with open(path) as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
    except FileNotFoundError:
        return f"{path}: expected output file was not written"
    except (OSError, UnicodeDecodeError) as e:
        return f"{path}: unreadable ({e})"
    if not lines:
        return f"{path}: output file is empty"
    for i, ln in enumerate(lines, 1):
        parts = ln.split()
        if len(parts) != ncols:
            return f"{path}: line {i} has {len(parts)} columns, expected {ncols} (malformed/truncated)"
        for p in parts:
            try:
                v = float(p)
            except ValueError:
                return f"{path}: line {i} has non-numeric field {p!r}"
            if not math.isfinite(v):
                return f"{path}: line {i} has nonfinite value {p!r}"
    if len(lines) < minrows:
        return f"{path}: {len(lines)} rows, expected at least {minrows} (truncated)"
    return None


def marker_problem(log, name):
    try:
        with open(log, errors="replace") as f:
            text = f.read()
    except OSError as e:
        return f"{log}: unreadable ({e})"
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[0] == name:
            try:
                if math.isfinite(float(parts[1])):
                    return None
            except ValueError:
                pass
            return f"{log}: marker {name} has non-finite/non-numeric value {parts[1]!r}"
    return f"{log}: marker {name} missing"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", help="simulator log (required with --marker)")
    ap.add_argument("--wrdata", action="append", default=[], metavar="PATH:NCOLS:MINROWS")
    ap.add_argument("--marker", action="append", default=[], metavar="NAME")
    a = ap.parse_args(argv)
    if a.marker and not a.log:
        ap.error("--marker requires --log")
    if not a.wrdata and not a.marker:
        ap.error("nothing to validate: give --wrdata and/or --marker")
    problems = []
    for spec in a.wrdata:
        try:
            path, n, m = spec.rsplit(":", 2)
            n, m = int(n), int(m)
        except ValueError:
            ap.error(f"bad --wrdata {spec!r}")
        p = wrdata_problem(path, n, m)
        if p:
            problems.append(p)
    for name in a.marker:
        p = marker_problem(a.log, name)
        if p:
            problems.append(p)
    for p in problems:
        print(f"preflight_validate: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
