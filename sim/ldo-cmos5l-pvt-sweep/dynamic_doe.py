"""Bounded dynamic DoE for DR-0007 rows 3, 6, 10 (issue #64). stdlib only.

EXPLORATORY evidence tooling: a discrete load x Cout x ESR grid at four
PVT/resistor corners, run through the loop-gain and PSRR benches. Nothing
here proves monotonicity, bounds the continuous window, covers unsampled
PVT corners, or ratifies any DR-0007 row.

Subcommands (see sim/ldo-cmos5l-pvt-sweep/README.md "Dynamic DoE"):

    plan     [--extra FILE] [--only-extra]   TSV of every point to simulate
    analyse  CORNERS_DIR... [--extra FILE] [--legacy-record CSV]... --out-prefix P
    refine   CORNERS_DIR... [--extra FILE] [--out FILE]   midpoint requests

Several CORNERS_DIRs may be given (a refinement record plus the base
record it refines); each point is read from the first one that has it, and
the row's `source` column names that directory.

Operating-point values are held as exact integers in base units (load in
uA, Cout in nF, ESR in mohm) so decimal formatting cannot collide IDs.
"""
import argparse
import csv
import json
import math
import os
import sys
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ac_metrics  # noqa: E402

# ---- the bounded matrix (issue #64) ------------------------------------
LOAD_LEVELS_UA = (0, 1000, 25000, 50000)      # 0, 1, 25, 50 mA
COUT_LEVELS_NF = (330, 1000, 2200, 4700)      # 0.33, 1.0, 2.2, 4.7 uF
ESR_LEVELS_MOHM = (0, 250, 500)               # 0, 250, 500 mohm
AXES = ("load_ua", "cout_nf", "esr_mohm")
AXIS_LEVELS = {"load_ua": LOAD_LEVELS_UA, "cout_nf": COUT_LEVELS_NF,
               "esr_mohm": ESR_LEVELS_MOHM}

# (mos corner, temp C, resistor label, why it was selected). Snapshot of the
# DR-0007 evidence at 4d45f5d / 2026-10-10; re-derive before relying on it.
CORNERS = (
    ("ss", 125, "bcs", "phase-margin binding"),
    ("ff", -40, "wcs", "gain-margin binding"),
    ("ss", 125, "wcs", "PSRR@1kHz binding"),
    ("ff", 27, "bcs", "PSRR@100kHz binding"),
)
BENCHES = ("loopgain", "psrr")
LEGACY_POINT = {"load_ua": 1000, "cout_nf": 1000, "esr_mohm": 0}
EXPECT_ROWS_AC = 161
LEGACY_TOL = 0.10  # deg for PM, dB for GM and PSRR

# DR-0007 targets: (metric, label, predicate-is-pass)
TARGETS = {
    "phase_margin_deg": ("PM >= 45 deg", lambda v: v >= 45.0),
    "gain_margin_db": ("GM >= 10 dB", lambda v: v >= 10.0),
    "psrr_db_1khz": ("PSRR@1kHz > 50 dB", lambda v: v > 50.0),
    "psrr_db_100khz": ("PSRR@100kHz > 20 dB", lambda v: v > 20.0),
}
METRICS = tuple(TARGETS)
TIE_EPS = 1e-6


# ---- validation + canonical formatting ---------------------------------
class InvalidOperatingPoint(ValueError):
    pass


def to_base_int(value, scale, name):
    """Exact conversion of a user value (str/number, in the axis' natural
    unit) to an integer in base units. `scale` = base units per natural
    unit. Rejects negatives, non-numbers and non-integral base values."""
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise InvalidOperatingPoint(f"{name}: not a number: {value!r}")
    if not d.is_finite():
        raise InvalidOperatingPoint(f"{name}: not finite: {value!r}")
    if d < 0:
        raise InvalidOperatingPoint(f"{name}: negative value {value!r}")
    base = d * scale
    if base != base.to_integral_value():
        raise InvalidOperatingPoint(
            f"{name}: {value!r} is not an integer number of base units")
    return int(base)


def make_op(load_ma, cout_uf, esr_ohm):
    """Operating point from natural units (mA, uF, ohm)."""
    op = {
        "load_ua": to_base_int(load_ma, 1000, "load_ma"),
        "cout_nf": to_base_int(cout_uf, 1000, "cout_uf"),
        "esr_mohm": to_base_int(esr_ohm, 1000, "esr_ohm"),
    }
    validate_op(op)
    return op


def validate_op(op):
    for a in AXES:
        v = op[a]
        if not isinstance(v, int) or isinstance(v, bool):
            raise InvalidOperatingPoint(f"{a}: not an integer: {v!r}")
        if v < 0:
            raise InvalidOperatingPoint(f"{a}: negative value {v}")
    if op["cout_nf"] == 0:
        raise InvalidOperatingPoint("cout_nf: zero Cout is not allowed")


def op_token(op):
    validate_op(op)
    return f"i{op['load_ua']}ua_c{op['cout_nf']}nf_e{op['esr_mohm']}mohm"


def op_key(op):
    return tuple(op[a] for a in AXES)


def point_id(bench, corner, temp, rlabel, op):
    return f"{bench}_dyn_{corner}_{temp}c_r{rlabel}_{op_token(op)}"


def netlist_values(op):
    """Strings substituted into the templates (ngspice number syntax)."""
    validate_op(op)
    load = "0" if op["load_ua"] == 0 else f"{op['load_ua']}e-6"
    cout = f"{op['cout_nf']}n"
    esr = "0" if op["esr_mohm"] == 0 else f"{op['esr_mohm']}e-3"
    return {"load_a": load, "cout_f": cout, "esr_ohm": esr}


def render_cout_esr(op):
    """The lines run_sweep.sh's gen_netlist emits for this op (mirrors
    esr_netlist_parts; kept in Python so the contract is unit-tested)."""
    v = netlist_values(op)
    if v["esr_ohm"] == "0":
        return [f"Iload VOUT 0 dc {v['load_a']}", f"Cout VOUT 0 {v['cout_f']}"]
    return [f"Iload VOUT 0 dc {v['load_a']}",
            f"Cout VOUT COUT_ESR {v['cout_f']}",
            f"Resr COUT_ESR 0 {v['esr_ohm']}"]


def corner_key(c):
    return (c[0], c[1], c[2])


# ---- matrix ------------------------------------------------------------
def base_ops():
    return [{"load_ua": l, "cout_nf": c, "esr_mohm": e}
            for l in LOAD_LEVELS_UA for c in COUT_LEVELS_NF
            for e in ESR_LEVELS_MOHM]


def load_extra(path):
    """Refinement points: JSON list of {corner,temp_c,res,load_ua,cout_nf,
    esr_mohm,...}. Validated; duplicates collapsed."""
    if not path:
        return []
    with open(path) as f:
        data = json.load(f)
    out = []
    for e in data:
        op = {a: e[a] for a in AXES}
        validate_op(op)
        out.append({"corner": e["corner"], "temp_c": int(e["temp_c"]),
                    "res": e["res"], "op": op,
                    "reason": e.get("reason", "")})
    return out


def plan(extra=(), only_extra=False):
    """Every point to simulate: list of dicts with bench, point_id, corner
    fields, op. Raises on ID collision (two distinct points, same ID).
    only_extra: just the extra points that are not already base points
    (a refinement run whose base matrix was simulated earlier)."""
    pts, seen = [], {}
    combos = [(c[0], c[1], c[2], op, "base") for c in CORNERS
              for op in base_ops()]
    base_coords = set()
    if only_extra:
        base_coords = {(c, t, r) + op_key(o) for c, t, r, o, _ in combos}
        combos = []
    combos += [(e["corner"], e["temp_c"], e["res"], e["op"],
                "refine: " + e["reason"]) for e in extra]
    done = set()
    for corner, temp, rlabel, op, origin in combos:
        coord = (corner, temp, rlabel) + op_key(op)
        if coord in done or coord in base_coords:
            continue
        done.add(coord)
        for bench in BENCHES:
            pid = point_id(bench, corner, temp, rlabel, op)
            if pid in seen:
                raise ValueError(f"point-id collision: {pid}")
            seen[pid] = coord
            pts.append({"bench": bench, "point_id": pid, "corner": corner,
                        "temp_c": temp, "res": rlabel, "op": dict(op),
                        "origin": origin})
    return pts


def plan_tsv(pts):
    """bench point_id mos res temp load_a cout_f esr_ohm (tab separated)."""
    lines = []
    for p in pts:
        v = netlist_values(p["op"])
        lines.append("\t".join([
            p["bench"], p["point_id"], f"mos_{p['corner']}",
            f"res_{p['res']}", str(p["temp_c"]), v["load_a"], v["cout_f"],
            v["esr_ohm"]]))
    return "\n".join(lines) + "\n"


# ---- per-point parsing -------------------------------------------------
def count_rows(path):
    try:
        with open(path) as f:
            return sum(1 for ln in f if ln.strip())
    except OSError:
        return None


def locate(corners_dirs, p):
    """First directory holding this point's AC output (or its log), else
    the first directory (so a missing point reports as missing there)."""
    if isinstance(corners_dirs, str):
        corners_dirs = [corners_dirs]
    for d in corners_dirs:
        if os.path.exists(os.path.join(d, p["point_id"] + "_ac.csv")) or \
                os.path.exists(os.path.join(d, p["point_id"] + ".log")):
            return d
    return corners_dirs[0]


def parse_point(corners_dir, p):
    """-> (metrics dict, failure-reason or None) for one bench point."""
    corners_dir = locate(corners_dir, p)
    path = os.path.join(corners_dir, p["point_id"] + "_ac.csv")
    n = count_rows(path)
    if n is None or n == 0:
        return {}, "missing: no AC output"
    if n != EXPECT_ROWS_AC:
        return {}, f"truncated: {n} rows, expected {EXPECT_ROWS_AC}"
    if p["bench"] == "loopgain":
        m = ac_metrics.loopgain_metrics(path)
        if not m:
            return {}, "unparseable AC data"
        out = {k: m.get(k) for k in ("phase_margin_deg", "gain_margin_db",
                                     "unity_gain_freq_hz", "dc_gain_db",
                                     "n_0db_crossings",
                                     "phase_margin_worst_deg")}
        if m.get("phase_margin_deg") is None:
            return out, "no unity-gain crossover"
        if m.get("gain_margin_db") is None:
            return out, "no -180 degree crossing (gain margin unmeasured)"
        if any(not math.isfinite(out[k]) for k in
               ("phase_margin_deg", "gain_margin_db")):
            return out, "non-finite metric"
        return out, None
    m = ac_metrics.psrr_metrics(path)
    if not m:
        return {}, "unparseable AC data"
    if any(m[k] is None or not math.isfinite(m[k]) for k in m):
        return m, "non-finite metric"
    return m, None


ROW_FIELDS = ["corner", "temp_c", "res_section", "load_ua", "cout_nf",
              "esr_mohm", "origin", "source", "phase_margin_deg", "gain_margin_db",
              "unity_gain_freq_hz", "n_0db_crossings", "phase_margin_worst_deg",
              "psrr_db_1khz",
              "psrr_db_100khz", "status", "failures"]


def build_rows(corners_dir, pts):
    """One row per (corner, op) joining both benches. Every planned point
    is accounted for: a missing/failed bench yields status != ok."""
    rows = {}
    for p in pts:
        key = (p["corner"], p["temp_c"], p["res"]) + op_key(p["op"])
        r = rows.setdefault(key, {
            "corner": p["corner"], "temp_c": p["temp_c"],
            "res_section": f"res_{p['res']}", **p["op"],
            "origin": p["origin"], "_fail": [], "_src": set()})
        r["_src"].add(os.path.basename(os.path.normpath(locate(corners_dir, p))))
        m, why = parse_point(corners_dir, p)
        r.update({k: v for k, v in m.items() if v is not None})
        if why:
            r["_fail"].append(f"{p['bench']}: {why}")
    out = []
    for key in sorted(rows):
        r = rows[key]
        r["status"] = "ok" if not r["_fail"] else "failed"
        r["failures"] = "; ".join(r.pop("_fail"))
        r["source"] = "+".join(sorted(r.pop("_src")))
        out.append(r)
    return out


def row_ok(r):
    return r["status"] == "ok"


def metric_val(r, m):
    """The row's value for metric m if it was measured and is finite, else
    None. A row whose status is `failed` still contributes the metrics it
    did measure: a loop-gain trace with no -180 degree crossing in band has
    no gain margin but a valid phase margin, and its PSRR is unaffected.
    Missing/truncated output yields no metrics at all."""
    v = r.get(m)
    if v is None or v == "":
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---- completeness, extrema, targets ------------------------------------
def completeness(rows, pts):
    expected = len({(p["corner"], p["temp_c"], p["res"]) + op_key(p["op"])
                    for p in pts})
    ok = sum(1 for r in rows if row_ok(r))
    return {"expected_operating_points": expected,
            "expected_simulations": len(pts),
            "rows": len(rows), "ok": ok, "failed": len(rows) - ok,
            "complete": len(rows) == expected and ok == expected}


def coord_str(r):
    return (f"{r['corner']}/{r['temp_c']}C/{r['res_section']} "
            f"load={r['load_ua'] / 1000:g}mA cout={r['cout_nf'] / 1000:g}uF "
            f"esr={r['esr_mohm']}mohm")


def extrema(rows):
    out = {}
    for m in METRICS:
        have = [r for r in rows if metric_val(r, m) is not None]
        if not have:
            out[m] = None
            continue
        w = min(have, key=lambda r: metric_val(r, m))
        v = metric_val(w, m)
        out[m] = {"value": v, "coord": coord_str(w), "n": len(have),
                  "target": TARGETS[m][0], "meets_target": TARGETS[m][1](v)}
    return out


def target_failures(rows):
    return [(r, m) for r in rows for m in METRICS
            if metric_val(r, m) is not None
            and not TARGETS[m][1](metric_val(r, m))]


# ---- legacy regression -------------------------------------------------
def compare_legacy(rows, legacy_rows, tol=LEGACY_TOL):
    """Compare the 1mA/1uF/0ohm rows against a committed record's parsed
    metrics (dicts keyed corner,temp_c,res_section). Returns per-corner
    results; a missing row on either side is a miss, never a pass."""
    res = []
    legacy = {(str(r["corner"]), int(r["temp_c"]), r["res_section"]): r
              for r in legacy_rows}
    for c in CORNERS:
        key = (c[0], c[1], f"res_{c[2]}")
        new = next((r for r in rows if (r["corner"], r["temp_c"],
                    r["res_section"]) == key and op_key(r) ==
                    op_key(LEGACY_POINT)), None)
        old = legacy.get(key)
        entry = {"corner": "/".join(map(str, key)), "diffs": {}, "ok": False,
                 "note": ""}
        if new is None or not row_ok(new):
            entry["note"] = "new legacy-point row missing or failed"
        elif old is None:
            entry["note"] = "committed record has no row"
        else:
            ok = True
            for m in METRICS:
                try:
                    d = abs(float(new[m]) - float(old[m]))
                except (KeyError, TypeError, ValueError):
                    d = None
                entry["diffs"][m] = d
                if d is None or d > tol:
                    ok = False
            entry["ok"] = ok
            if not ok:
                entry["note"] = "tolerance miss: report and explain; do not overwrite"
        res.append(entry)
    return res


def read_record_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ---- refinement --------------------------------------------------------
def midpoint(a, b):
    s = a + b
    return s // 2 if s % 2 == 0 else None


def slices(rows, corner, metric, axis):
    """Yield (fixed-coordinate dict, ordered [(level, value)]) for each 1-D
    slice at one corner, for one axis, over the rows that measured the
    metric (see metric_val)."""
    others = [x for x in AXES if x != axis]
    groups = {}
    for r in rows:
        if (r["corner"], r["temp_c"], r["res_section"]) != corner:
            continue
        if metric_val(r, metric) is None:
            continue
        groups.setdefault(tuple(r[o] for o in others), []).append(
            (r[axis], metric_val(r, metric)))
    for fixed, pts in sorted(groups.items()):
        pts.sort()
        yield dict(zip(others, fixed)), pts


def is_monotone(vals):
    inc = all(b >= a - TIE_EPS for a, b in zip(vals, vals[1:]))
    dec = all(b <= a + TIE_EPS for a, b in zip(vals, vals[1:]))
    return inc or dec


def refinement_requests(rows):
    """Adjacent-midpoint requests per the issue's refinement rule.
    Returns (requests, evidence). evidence has per-corner/metric/axis slice
    counts so 'none fired' is backed by numbers."""
    reqs, evidence = {}, []

    def add(corner, axis, fixed, lo, hi, reason):
        mid = midpoint(lo, hi)
        if mid is None or mid in (lo, hi):
            key = ("unrefinable", corner, axis, tuple(sorted(fixed.items())), lo, hi)
            reqs[key] = {"unrefinable": True, "axis": axis,
                         "interval": [lo, hi], "reason": reason}
            return
        op = dict(fixed)
        op[axis] = mid
        validate_op(op)
        key = (corner, axis, tuple(sorted(fixed.items())), mid)
        if key in reqs:
            reqs[key]["reason"] += " | " + reason
            return
        reqs[key] = {"corner": corner[0], "temp_c": corner[1],
                     "res": corner[2].replace("res_", ""), **op,
                     "reason": reason}

    corners = sorted({(r["corner"], r["temp_c"], r["res_section"])
                      for r in rows})
    for corner in corners:
        for metric in METRICS:
            for axis in AXES:
                n = mono = 0
                trig = 0
                for fixed, pts in slices(rows, corner, metric, axis):
                    n += 1
                    levels = [p[0] for p in pts]
                    vals = [p[1] for p in pts]
                    if is_monotone(vals):
                        mono += 1
                    tag = f"{metric} along {axis} @ {fixed}"
                    fired = False
                    # (a) target failure: bisect both sides of the failing point
                    for i, v in enumerate(vals):
                        if not TARGETS[metric][1](v):
                            fired = True
                            for j in (i - 1, i + 1):
                                if 0 <= j < len(levels):
                                    add(corner, axis, fixed,
                                        min(levels[i], levels[j]),
                                        max(levels[i], levels[j]),
                                        f"target failure ({tag})")
                    # (b) non-monotonic: bisect intervals at each turning point
                    if not is_monotone(vals):
                        fired = True
                        for i in range(1, len(vals) - 1):
                            up1 = vals[i] - vals[i - 1]
                            up2 = vals[i + 1] - vals[i]
                            if (up1 > TIE_EPS and up2 < -TIE_EPS) or \
                               (up1 < -TIE_EPS and up2 > TIE_EPS):
                                for j in (i - 1, i + 1):
                                    add(corner, axis, fixed,
                                        min(levels[i], levels[j]),
                                        max(levels[i], levels[j]),
                                        f"non-monotonic ({tag})")
                    # (c) interior worst point (strictly worse than both ends)
                    if len(vals) >= 3:
                        i = min(range(len(vals)), key=lambda k: vals[k])
                        if 0 < i < len(vals) - 1 and \
                           vals[i] < vals[0] - TIE_EPS and \
                           vals[i] < vals[-1] - TIE_EPS:
                            fired = True
                            for j in (i - 1, i + 1):
                                add(corner, axis, fixed,
                                    min(levels[i], levels[j]),
                                    max(levels[i], levels[j]),
                                    f"interior worst ({tag})")
                    trig += fired
                evidence.append({"corner": "/".join(map(str, corner)),
                                 "metric": metric, "axis": axis, "slices": n,
                                 "monotone": mono, "triggered": trig})
    return list(reqs.values()), evidence


# ---- reporting ---------------------------------------------------------
def write_report(prefix, rows, pts, legacy, reqs, evidence):
    comp = completeness(rows, pts)
    ext = extrema(rows)
    with open(prefix + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ROW_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    real = [r for r in reqs if not r.get("unrefinable")]
    unref = [r for r in reqs if r.get("unrefinable")]
    fired = sum(e["triggered"] for e in evidence)
    with open(prefix + ".md", "w") as f:
        f.write("# Dynamic DoE summary (issue #64) -- EXPLORATORY\n\n")
        f.write("Discrete sampled points only. No monotonicity, continuous-window "
                "or unsampled-PVT claim; DR-0007 rows 3, 6, 10 status unchanged.\n\n")
        f.write("## Completeness\n\n")
        for k, v in comp.items():
            f.write(f"- {k}: {v}\n")
        f.write("\n## Extrema vs DR-0007 targets (informational)\n\n")
        f.write("Over every row that measured the metric, including rows whose "
                "status is `failed` for another metric (see `metric_val`). "
                "`phase_margin_deg` is the parser's first-0-dB-crossing phase "
                "margin. Where a trace has two 0 dB crossings, the CSV's "
                "`phase_margin_worst_deg` column also gives the worst one.\n\n")
        f.write("| metric | worst value | target | meets | points measured | coordinate |\n"
                "|---|---|---|---|---|---|\n")
        for m in METRICS:
            e = ext[m]
            if e is None:
                f.write(f"| {m} | n/a | {TARGETS[m][0]} | n/a | 0 | no valid data |\n")
            else:
                f.write(f"| {m} | {e['value']:.2f} | {e['target']} | "
                        f"{e['meets_target']} | {e['n']} | {e['coord']} |\n")
        f.write("\n## Target misses per corner (informational)\n\n"
                "Count of sampled operating points that miss each target, out of "
                "the points at that corner that measured the metric.\n\n"
                "| corner | " + " | ".join(METRICS) + " |\n|---|" + "---|" * len(METRICS) + "\n")
        fails = target_failures(rows)
        for c in sorted({(r["corner"], r["temp_c"], r["res_section"]) for r in rows}):
            cells = []
            for m in METRICS:
                meas = [r for r in rows if (r["corner"], r["temp_c"], r["res_section"]) == c
                        and metric_val(r, m) is not None]
                miss = [r for r, mm in fails if mm == m and
                        (r["corner"], r["temp_c"], r["res_section"]) == c]
                cells.append(f"{len(miss)}/{len(meas)}")
            f.write(f"| {'/'.join(map(str, c))} | " + " | ".join(cells) + " |\n")
        f.write("\n## Failed / missing points\n\n")
        bad = [r for r in rows if not row_ok(r)]
        f.write("none\n" if not bad else "")
        for r in bad:
            f.write(f"- {coord_str(r)}: {r['failures']}\n")
        for name, res in legacy or []:
            f.write(f"\n## Legacy 1 mA / 1 uF / 0 ohm vs committed record "
                    f"`{name}` (tol {LEGACY_TOL})\n\n")
            f.write("| corner | result | |dPM| deg | |dGM| dB | |dPSRR@1k| dB "
                    "| |dPSRR@100k| dB | note |\n|---|---|---|---|---|---|---|\n")
            for e in res:
                cells = " | ".join("n/a" if e["diffs"].get(m) is None
                                   else f"{e['diffs'][m]:.4f}" for m in METRICS)
                f.write(f"| {e['corner']} | {'OK' if e['ok'] else 'MISS'} | "
                        f"{cells} | {e['note']} |\n")
        f.write("\n## Refinement\n\n")
        extra = [p for p in pts if p["origin"] != "base"]
        if extra:
            f.write(f"This analysis includes {len({(p['corner'], p['temp_c'], p['res']) + op_key(p['op']) for p in extra})} "
                    "refinement operating point(s) (`origin` column); the "
                    "requests below are re-derived over base + refinement "
                    "rows, and any that are not yet simulated are listed as "
                    "PENDING.\n\n")
        pend = {(r["corner"], r["temp_c"], r["res"]) + op_key(r)
                for r in pending_requests(reqs, pts)}
        if not reqs:
            f.write(f"No trigger fired across {sum(e['slices'] for e in evidence)} "
                    "slices (per-slice evidence below).\n")
        else:
            f.write(f"{len(real)} midpoint request(s), {len(unref)} unrefinable "
                    f"interval(s); {fired} slice-metric triggers.\n\n")
            for r in real:
                tag = "PENDING " if (r["corner"], r["temp_c"], r["res"]) + op_key(r) in pend else ""
                f.write(f"- {tag}{r['corner']}/{r['temp_c']}C/res_{r['res']} "
                        f"load_ua={r['load_ua']} cout_nf={r['cout_nf']} "
                        f"esr_mohm={r['esr_mohm']}: {r['reason']}\n")
            for r in unref:
                f.write(f"- UNREFINABLE {r['axis']} {r['interval']}: {r['reason']}\n")
        f.write("\n| corner | metric | axis | slices | monotone | triggered |\n"
                "|---|---|---|---|---|---|\n")
        for e in evidence:
            f.write(f"| {e['corner']} | {e['metric']} | {e['axis']} | "
                    f"{e['slices']} | {e['monotone']} | {e['triggered']} |\n")
    return comp


def pending_requests(reqs, pts):
    """Midpoint requests that are not already planned points."""
    have = {(p["corner"], p["temp_c"], p["res"]) + op_key(p["op"]) for p in pts}
    return [r for r in reqs if not r.get("unrefinable") and
            (r["corner"], r["temp_c"], r["res"]) + op_key(r) not in have]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "analyse", "refine"):
        sp = sub.add_parser(name)
        if name != "plan":
            sp.add_argument("corners_dir", nargs="+")
        sp.add_argument("--extra")
        if name == "plan":
            sp.add_argument("--only-extra", action="store_true",
                            help="only the --extra points not in the base matrix")
        if name == "analyse":
            sp.add_argument("--legacy-record", action="append", default=[])
            sp.add_argument("--out-prefix", required=True)
        if name == "refine":
            sp.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        sys.stdout.write(plan_tsv(plan(load_extra(a.extra),
                                       only_extra=a.only_extra)))
        return 0
    pts = plan(load_extra(a.extra))
    rows = build_rows(a.corners_dir, pts)
    reqs, evidence = refinement_requests(rows)
    if a.cmd == "refine":
        text = json.dumps(pending_requests(reqs, pts), indent=1)
        if a.out:
            open(a.out, "w").write(text + "\n")
        else:
            print(text)
        return 0
    legacy = [(os.path.basename(path), compare_legacy(rows, read_record_csv(path)))
              for path in a.legacy_record]
    comp = write_report(a.out_prefix, rows, pts, legacy, reqs, evidence)
    print(json.dumps(comp))
    return 0 if comp["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
