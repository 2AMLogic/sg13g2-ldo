#!/usr/bin/env python3
"""Loop-gain AC sweep contract (issue #128): ceiling input -> rendered value -> row count.

`run_sweep.sh` takes the loop-gain AC ceiling as one input (`--loopgain-ac-max=<f>`
or `SWEEP_LOOPGAIN_AC_MAX`, default `100meg`), renders it into
`tb_loopgain_cmos5l.spice.tmpl` as `ac dec <ppd> 1 <ceiling>`, and derives the
positive completeness row count from the same three numbers. The floor (1 Hz)
and the points per decade (20) are fixed. The ceiling must be an exact power
of ten so that the count is exactly `ppd * decades + 1`.

    python3 ac_sweep.py ceiling 10g     # -> canonical ceiling, e.g. 10g
    python3 ac_sweep.py rows 10g        # -> expected wrdata rows, e.g. 201
    python3 ac_sweep.py check-trace F 10g   # exit 1 if trace F is truncated/mis-ranged
"""
import math
import re
import sys

FLOOR_HZ = 1.0
POINTS_PER_DECADE = 20
DEFAULT_CEILING = "100meg"
MAX_DECADES = 12          # 1 THz; anything above is rejected as not a plausible request

_SUFFIX = {"": 1.0, "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12}


class AcSweepError(ValueError):
    pass


def parse_hz(text):
    """ngspice number (`100meg`, `10g`, `1e10`) -> Hz. Only k/meg/g/t suffixes."""
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]*)?(?:e[+-]?[0-9]+)?)(k|meg|g|t)?(?:hz)?", str(text).strip().lower())
    if not m:
        raise AcSweepError(f"cannot parse AC ceiling {text!r} (use e.g. 100meg, 1g, 10g, 1e10)")
    return float(m.group(1)) * _SUFFIX[m.group(2) or ""]


def decades(ceiling):
    hz = parse_hz(ceiling)
    if hz <= 0:
        raise AcSweepError(f"AC ceiling {ceiling!r} must be positive")
    d = math.log10(hz / FLOOR_HZ)
    n = round(d)
    if not math.isclose(d, n, abs_tol=1e-9):
        raise AcSweepError(f"AC ceiling {ceiling!r} is not an exact power of ten above the {FLOOR_HZ:g} Hz floor")
    if n < 3 or n > MAX_DECADES:
        raise AcSweepError(f"AC ceiling {ceiling!r} spans {n} decades; need 3..{MAX_DECADES}")
    return n


def canonical(ceiling):
    """The string rendered into the netlist (ngspice-safe: no suffix ambiguity)."""
    n = decades(ceiling)
    return DEFAULT_CEILING if n == 8 else f"1e{n}"   # default keeps its historical token


def expected_rows(ceiling):
    return POINTS_PER_DECADE * decades(ceiling) + 1


def analysis_line(ceiling):
    return f"ac dec {POINTS_PER_DECADE} {FLOOR_HZ:g} {canonical(ceiling)}"


def check_trace(path, ceiling):
    """Return a list of problems with a loop-gain wrdata trace (empty = ok):
    exact row count for the configured sweep, 4 columns, first/last frequency
    equal to the floor/ceiling, and strictly increasing frequency."""
    want = expected_rows(ceiling)
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [ln.split() for ln in fh if ln.strip()]
    except OSError as exc:
        return [f"{path}: unreadable ({exc})"]
    bad = []
    if len(rows) != want:
        bad.append(f"{path}: {len(rows)} rows, expected {want} for ceiling {ceiling}")
    if rows and any(len(r) != 4 for r in rows):
        bad.append(f"{path}: not 4 columns on every row")
    if not bad:
        f = [float(r[0]) for r in rows]
        if not math.isclose(f[0], FLOOR_HZ, rel_tol=1e-6):
            bad.append(f"{path}: first frequency {f[0]:g} != floor {FLOOR_HZ:g}")
        if not math.isclose(f[-1], parse_hz(ceiling), rel_tol=1e-6):
            bad.append(f"{path}: last frequency {f[-1]:g} != ceiling {parse_hz(ceiling):g}")
        if any(b <= a for a, b in zip(f, f[1:])):
            bad.append(f"{path}: frequency not strictly increasing")
    return bad


def main(argv):
    if len(argv) == 4 and argv[1] == "check-trace":
        bad = check_trace(argv[2], argv[3])
        for b in bad:
            print(f"ac_sweep: {b}", file=sys.stderr)
        return 1 if bad else 0
    if len(argv) != 3 or argv[1] not in ("ceiling", "rows", "line"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print({"ceiling": canonical, "rows": expected_rows, "line": analysis_line}[argv[1]](argv[2]))
    except AcSweepError as exc:
        print(f"ac_sweep: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
