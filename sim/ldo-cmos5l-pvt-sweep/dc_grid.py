"""Single complete-grid contract for the nested DC `wrdata` output (issue #120).

tb_dcsweep_cmos5l.spice.tmpl sweeps Iload (outer, 5 values) x Vin (inner,
2.00..3.63 V, 10 mV).  Both the live sweep post-processing (run_sweep.sh) and
the offline item-5 analysis (item5_evidence.py) validate the raw grid HERE
before any metric is computed, so a truncated, padded, duplicated, reordered,
malformed or non-finite grid is rejected with an explicit reason instead of
being measured through a nearest-point lookup.

dc_metrics.py is deliberately left byte-identical: its sha256 is pinned in
landed, append-only artifacts (dropout campaign record, coverage inventories).
`validated_dc_metrics` therefore wraps it: validate first, then delegate, so
valid inputs reproduce the historical metric values exactly.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import dc_metrics as _dcm  # noqa: E402

N_BLOCKS = 5
N_ROWS = 164  # 2.00..3.63 V, 10 mV step
VIN_TOL = 1e-6
EXPECTED_VINS = [round(_dcm.VIN_MIN + _dcm.VIN_STEP * i, 2) for i in range(N_ROWS)]
assert abs(EXPECTED_VINS[-1] - _dcm.VIN_MAX) < 1e-9


def _read(path, ncols=8):
    """Like dc_metrics.read_wrdata, but malformed numbers are reported, not
    raised. Returns (rows, problems)."""
    rows = []
    try:
        with open(path) as f:
            for n, line in enumerate(f, 1):
                parts = line.split()
                if len(parts) < ncols:
                    continue
                try:
                    rows.append([float(x) for x in parts])
                except ValueError:
                    return rows, [f"line {n}: malformed numeric field"]
    except FileNotFoundError:
        return [], ["missing or empty raw grid"]
    return rows, []


def validate_file(path):
    """Return (blocks, problems).  blocks are lists of (vin, vout, i_vin,
    i_divsense) split with dc_metrics' Vin-reset rule; problems is a list of
    human-readable strings, empty iff the grid is complete and finite."""
    rows, problems = _read(path)
    if problems:
        return [], problems
    if not rows:
        return [], ["missing or empty raw grid"]
    bad = [i for i, r in enumerate(rows) if not all(math.isfinite(x) for x in r)]
    if bad:
        problems.append(f"{len(bad)} row(s) with non-finite values (first at data row {bad[0]})")
    blocks, cur, prev = [], [], None
    for r in rows:
        if prev is not None and r[1] < prev - 1e-9:
            blocks.append(cur)
            cur = []
        cur.append((r[1], r[3], r[5], r[7]))
        prev = r[1]
    blocks.append(cur)
    if len(blocks) != N_BLOCKS:
        problems.append(f"expected {N_BLOCKS} Iload blocks, got {len(blocks)}")
    for k, b in enumerate(blocks):
        if len(b) != N_ROWS:
            problems.append(f"block {k}: {len(b)} rows, expected {N_ROWS}")
            continue
        wrong = [i for i, (t, e) in enumerate(zip(b, EXPECTED_VINS)) if not abs(t[0] - e) <= VIN_TOL]
        if wrong:
            i = wrong[0]
            problems.append(f"block {k}: Vin sequence differs from the 2.00..3.63 V/10 mV grid "
                            f"at row {i} (got {b[i][0]!r}, expected {EXPECTED_VINS[i]})")
    return blocks, problems


def validated_dc_metrics(path):
    """dc_metrics.dc_metrics(path) if the grid is complete, else
    {"error": "invalid DC grid: ..."} (never None, never a numeric result)."""
    _, problems = validate_file(path)
    if problems:
        return {"error": "invalid DC grid: " + "; ".join(problems)}
    return _dcm.dc_metrics(path)
