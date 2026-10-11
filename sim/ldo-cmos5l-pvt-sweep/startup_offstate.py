#!/usr/bin/env python3
"""Disabled-state supply current read from a committed startup-grid record's
reduced traces (issue #89). Offline, stdlib only; runs no simulator and mints
no record.

    python3 sim/ldo-cmos5l-pvt-sweep/startup_offstate.py <startup-run-id>

For every point of `records/<id>-startup-grid.csv` it opens the point's trace
(`records/<id>-startup-grid.traces/`, verified against the csv's
`trace_sha256`) and prints `-i(vin)` at the last sample with t <= 1 ms and
EN exactly 0, i.e. the end of the cold-start off state, before the 1 us EN
edge starts. Conditions are the startup bench's: EN = 0, IBIAS 2 uA sink,
VREF 0.90 V, resistive 1 mA-at-1.8 V load, Cout 1 uF, per-point MOS /
temperature / resistor corner and Vin.

Why not the record's own `off_supply_current_a` column: startup_eval.py takes
that from the last sample before the EN = VIN/2 crossing, which lies inside
the EN edge, so it includes edge-time current (for the #89 design, the
crowbar current of the amplifier's EN inverter). It is not an off-state
value. This script does not change that column or its evaluator.
"""
import csv
import gzip
import hashlib
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T_EDGE_S = 1e-3  # CTL PWL: 0 until 1 ms, then a 1 us edge (tb_startup_cmos5l.spice.tmpl)


def offstate_current(trace_path):
    with gzip.open(trace_path, "rt", encoding="utf-8") as fh:
        rows = csv.reader(fh)
        head = next(rows)
        it, ie, ii = head.index("t"), head.index("en"), head.index("ivin")
        last = None
        for r in rows:
            if float(r[it]) > T_EDGE_S * (1 + 1e-9):
                break
            if float(r[ie]) == 0.0:
                last = r
    if last is None:
        raise SystemExit(f"{trace_path}: no EN = 0 sample at t <= 1 ms")
    return -float(last[ii]), float(last[it])


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rid = sys.argv[1]
    rec = os.path.join(HERE, "records")
    tdir = os.path.join(rec, f"{rid}-startup-grid.traces")
    out = []
    with open(os.path.join(rec, f"{rid}-startup-grid.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            p = os.path.join(tdir, os.path.basename(r["trace_file"]))
            with open(p, "rb") as tf:
                if hashlib.sha256(tf.read()).hexdigest() != r["trace_sha256"]:
                    raise SystemExit(f"{p}: bytes differ from the recorded trace_sha256")
            i, t = offstate_current(p)
            out.append((i, t, r["mos"], r["temp"], r["res"], r["vin"]))
    print("mos,temp_c,res,vin_v,t_s,off_supply_current_a")
    for i, t, m, tc, rs, v in sorted(out, key=lambda x: (x[2], int(float(x[3])), x[4], float(x[5]))):
        print(f"{m},{tc},{rs},{v},{t:.9g},{i:.9g}")
    vals = sorted(x[0] for x in out)
    lo, hi = min(out), max(out)
    print(f"# {len(out)} points; min {lo[0]:.9g} A ({lo[2]}/{lo[3]}C/res_{lo[4]}/{lo[5]} V); "
          f"median {statistics.median(vals):.9g} A; "
          f"max {hi[0]:.9g} A ({hi[2]}/{hi[3]}C/res_{hi[4]}/{hi[5]} V)", file=sys.stderr)


if __name__ == "__main__":
    main()
