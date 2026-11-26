#!/usr/bin/env python3
"""Singular-matrix log screen (issue #383): the ONE shared, single-pass
predicate the four PVT drivers' screen_point functions call to tell ngspice's
RECOVERABLE `Warning: singular matrix:` form from a genuine unrecovered one.

ngspice prints the warning form while the solver walks its own
convergence-aid ladder (source stepping -> dynamic gmin stepping); it is
routinely followed by `Dynamic gmin stepping completed` and a fully
converged analysis, so treating it as fatal would discard good points (the
#31 grid recovered 9 of 135 this way). An unrecovered singular matrix has no
`Warning:` prefix and fails the point. The model-load / gmin-failure /
non-convergence signatures stay in each driver's own screen; this module
owns only the singular-matrix decision, so the rule is written and tested
once (issue #383).

The two-grep pipeline this replaces
(`grep -iE "singular matrix" LOG | grep -qivE "^[[:space:]]*Warning:"`)
read the log twice, and the second grep exits on the FIRST fatal line: on a
log with one unrecovered line followed by a long run of recovered warnings
(the fleet worker's 100k-line tail), the first grep is still writing when
the pipe closes, dies of SIGPIPE (141), and every driver's `pipefail` makes
the pipeline's status non-zero -- which the `if` around it reads as "no
fatal match". The point is then accepted in error. One process reading the
file once cannot misreport either way, and a readable log is required: a
missing or unreadable log rejects the point too.

    python3 singular_screen.py check-log LOG
        exit 0 -- no unrecovered singular matrix in LOG
        exit 1 -- LOG carries one; the offending line is on stderr
        exit 2 -- LOG is unreadable (or the invocation is malformed)

Offline, stdlib-only, no PDK, no simulator. Pinned by the T1 item 9
inventory with its companion test_singular_screen.py.
"""
import re
import sys

# The recoverable form's prefix: case-insensitive, optionally indented
# `Warning:` -- byte-faithful to the second grep's
# `^[[:space:]]*Warning:` (with -i) so sharing the check moves no verdict
# on any log the two-grep form already judged.
_WARNED = re.compile(r"[ \t\r\f\v]*warning:", re.IGNORECASE)
_SINGULAR = re.compile(r"singular matrix", re.IGNORECASE)


def fatal_line(line):
    """True when `line` carries `singular matrix` OUTSIDE the recoverable
    `Warning:` form. Everything else -- the warning form included -- is
    clean as far as this predicate is concerned."""
    return _SINGULAR.search(line) is not None and _WARNED.match(line) is None


def screen(path):
    """One pass over the log at `path`.

    Returns None when the log is clean, else an (exit_code, message) pair:
    (1, ...) names the first unrecovered `singular matrix` line, (2, ...)
    says the log could not be read. Both reject the point; only the first
    means a simulator signature was seen."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if fatal_line(line):
                    return 1, (f"{path}:{lineno}: unrecovered singular matrix "
                               f"(no Warning: prefix): {line.strip()}")
    except OSError as exc:
        return 2, f"{path}: unreadable log: {exc}"
    return None


def main(argv):
    if len(argv) == 3 and argv[1] == "check-log":
        verdict = screen(argv[2])
        if verdict is None:
            return 0
        code, message = verdict
        print(f"singular_screen.py: {message}", file=sys.stderr)
        return code
    print("usage: singular_screen.py check-log <log>   "
          "(exit 0 clean, 1 fatal, 2 unreadable)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
