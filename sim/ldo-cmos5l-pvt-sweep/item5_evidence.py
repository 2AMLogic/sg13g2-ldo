#!/usr/bin/env python3
"""T1 item 5 corner-verification evidence derivation (issue #55, part of #5).

Offline and stdlib-only. Re-derives, from the COMMITTED raw DC grid of the
selected record (`corners/<id>/dcsweep_*_dc.csv`), with the SAME parser the
sweep uses (`dc_metrics.py`, extracted from run_sweep.sh):

  * the legacy dropout / no-load Iq / no-load line-regulation / Vin=3.63 V
    load-regulation columns, and CHECKS they reproduce the committed record
    CSV (so the raw grid and the record cannot silently disagree);
  * informational summaries the record never reported: full-load Iq (load
    current excluded), line regulation at every swept load, load regulation
    at 2.97 / 3.30 / 3.63 V, each with an explicit validity flag;
  * a ten-row coverage inventory against DR-0007.

It mints NO simulation record and runs NO simulator. It does NOT produce a
`klt sim` envelope and says so in its output: see the `klt_sim_envelope`
block of the inventory (blocked by klayout-tools#2727). Nothing here is, or
may be cited as, a ratified-row pass: only row 4 is ratified (DR-0007) and
its evidence is qualified (legacy definition, floor-limited, #70 / #71).

    python3 sim/ldo-cmos5l-pvt-sweep/item5_evidence.py           # (re)write
    python3 sim/ldo-cmos5l-pvt-sweep/item5_evidence.py --check   # CI: byte-compare

Outputs (append-only evidence, named by the source record id):
    sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/dc-informational-summary.csv
    sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/coverage-inventory.json
    sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/coverage-inventory.md
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import dc_metrics as dcm  # noqa: E402

RECORD_ID = "20261010-025634-60a3e81"
RECORD_CSV = f"sim/ldo-cmos5l-pvt-sweep/records/{RECORD_ID}.csv"
RECORD_MD = f"sim/ldo-cmos5l-pvt-sweep/records/{RECORD_ID}.md"
CORNERS_DIR = f"sim/ldo-cmos5l-pvt-sweep/corners/{RECORD_ID}"
DR7 = "spec/decision-records/DR-0007-target-spec-row-ratification.md"
DESIGN_NETLISTS = [
    "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice",
    "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice",
]
# Hashes the record ran against (its own record md lists them). Before #67
# this pinned record 20260917-023832-7061e8f to the pre-EN netlist hashes
# DR-0007 judged it current against; that record's evidence directory is
# kept unchanged as history.
DESIGN_PINS = {
    DESIGN_NETLISTS[0]: "7953b25be4cb00053f8df5f283bee0500f60a826b7a2d6519b88a8578d222cc1",
    DESIGN_NETLISTS[1]: "7982d728a2db933165eedcae69feaa4985dbddf54c269fc68b82d88577c8e38c",
}
RECORD_CSV_PIN = "d0c1e057c8cbbf0aaaab3df57b753fcca8557375372ee8bf6f6103a0b946c981"
OUT_DIR = f"sim/ldo-cmos5l-pvt-sweep/evidence/{RECORD_ID}"

CORNERS = ["tt", "ff", "ss", "sf", "fs"]
TEMPS = [-40, 27, 125]
RES = ["res_typ", "res_bcs", "res_wcs"]
RES_SFX = {"res_typ": "rtyp", "res_bcs": "rbcs", "res_wcs": "rwcs"}
LOADS_A = [0.0, 0.0125, 0.025, 0.0375, 0.05]
LOAD_TAGS = ["0mA", "12p5mA", "25mA", "37p5mA", "50mA"]
LOAD_REG_VINS = [2.97, 3.30, 3.63]
VIN_TAGS = {2.97: "2p97", 3.30: "3p30", 3.63: "3p63"}
VOUT_T = dcm.VOUT_TARGET
REG_BAND = 0.01  # a point is "in regulation" if |VOUT - 1.8| < 1 % of 1.8
EXPECTED_ROWS_PER_BLOCK = 164  # 2.00..3.63 V step 10 mV
# Machine-readable disclosure: the legacy dropout tests against the fixed
# 1.8 V target, not the in-regulation VOUT; see #70.
SIGNOFF_NOT_PRODUCED = "no klt sim envelope exists; see klt_sim_envelope"


def sha256_file(rel):
    h = hashlib.sha256()
    with open(os.path.join(REPO, rel), "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def point_files():
    for c in CORNERS:
        for t in TEMPS:
            for r in RES:
                yield c, t, r, f"{CORNERS_DIR}/dcsweep_{c}_{t}c_{RES_SFX[r]}_dc.csv"


def split_blocks(path):
    """Iload blocks of one raw grid, using dc_metrics' own reader and the
    same Vin-reset boundary rule. Returns (blocks, problems)."""
    rows = dcm.read_wrdata(os.path.join(REPO, path), 8)
    problems = []
    if not rows:
        return [], ["missing or empty raw grid"]
    blocks, cur, prev = [], [], None
    for r in rows:
        if prev is not None and r[1] < prev - 1e-9:
            blocks.append(cur)
            cur = []
        cur.append((r[1], r[3], r[5], r[7]))
        prev = r[1]
    blocks.append(cur)
    if len(blocks) != 5:
        problems.append(f"expected 5 Iload blocks, got {len(blocks)}")
    for k, b in enumerate(blocks):
        if len(b) != EXPECTED_ROWS_PER_BLOCK:
            problems.append(f"block {k}: {len(b)} rows, expected {EXPECTED_ROWS_PER_BLOCK}")
        elif abs(b[0][0] - dcm.VIN_MIN) > 1e-6 or abs(b[-1][0] - dcm.VIN_MAX) > 1e-6:
            problems.append(f"block {k}: Vin span {b[0][0]}..{b[-1][0]}")
    return blocks, problems


def at(block, vin):
    """Exact grid point nearest vin; None if the grid has no point within
    half a step (a truncated grid never silently substitutes a neighbour)."""
    p = min(block, key=lambda t: abs(t[0] - vin))
    return p if abs(p[0] - vin) < dcm.VIN_STEP / 2 else None


def in_reg(vout):
    return abs(vout - VOUT_T) < REG_BAND * VOUT_T


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float):
        return "nan" if math.isnan(v) else f"{v:.9g}"
    return str(v)


def analyse_point(path):
    """All derived quantities for one corner point. Never raises on a bad
    grid: problems are returned and the point is marked invalid, so a failed
    or truncated point stays in the accounting."""
    blocks, problems = split_blocks(path)
    out = {"grid_ok": not problems, "grid_problems": "; ".join(problems)}
    if len(blocks) != 5 or problems:
        out["valid"] = False
        return out
    legacy = dcm.dc_metrics(os.path.join(REPO, path))
    out["legacy"] = legacy

    # Full-load Iq (load current excluded). i(vin) is the supply current
    # (negative, sourced by Vin); the load source sinks exactly Iload, so
    # Iq(load) = |i(vin)| - Iload. Evaluated at Vin = 3.30 V, like the
    # record's no-load Iq.
    iq = {}
    for tag, iload, blk in zip(LOAD_TAGS, LOADS_A, blocks):
        p = at(blk, 3.30)
        iq[tag] = (abs(p[2]) - iload) if p else None
    out["iq_by_load_a"] = iq
    p50 = at(blocks[-1], 3.30)
    out["iq_full_valid"] = bool(p50 and in_reg(p50[1]))
    # Resolution proxy: the grid is printed to 9 significant digits
    # (1e-10 A at 50 mA); and the solver's own convergence noise is bounded
    # empirically by the largest second difference of the supply current
    # across the in-regulation Vin points at full load (a smooth function
    # has ~0 second difference, so this is a noise floor, not an error bar).
    reg = [t for t in blocks[-1] if in_reg(t[1]) and t[0] >= 2.97]
    sd = [abs(reg[i - 1][2] - 2 * reg[i][2] + reg[i + 1][2]) for i in range(1, len(reg) - 1)]
    out["iq_full_noise_proxy_a"] = max(sd) if sd else None
    out["iq_full_print_resolution_a"] = 1e-10

    # Line regulation at each load: slope of VOUT over 2.97 -> 3.63 V.
    line, line_ok = {}, {}
    for tag, blk in zip(LOAD_TAGS, blocks):
        lo, hi = at(blk, 2.97), at(blk, 3.63)
        if lo and hi:
            line[tag] = (hi[1] - lo[1]) / (hi[0] - lo[0]) * 1000.0
            line_ok[tag] = in_reg(lo[1]) and in_reg(hi[1])
        else:
            line[tag], line_ok[tag] = None, False
    out["line_mv_per_v_by_load"] = line
    out["line_valid_by_load"] = line_ok

    # Load regulation at each supply: (V0 - V50)/V0, same sign convention as
    # the sweep's load_reg_pct (which is the 3.63 V case).
    lr, lr_ok, vfull = {}, {}, {}
    for v in LOAD_REG_VINS:
        a, b = at(blocks[0], v), at(blocks[-1], v)
        if a and b and a[1]:
            lr[v] = (a[1] - b[1]) / a[1] * 100.0
            lr_ok[v] = in_reg(a[1]) and in_reg(b[1])
            vfull[v] = b[1]
        else:
            lr[v], lr_ok[v], vfull[v] = None, False, None
    out["load_reg_pct_by_vin"] = lr
    out["load_reg_valid_by_vin"] = lr_ok
    out["vout_full_load_by_vin"] = vfull

    # Dropout @ 50 mA: LEGACY definition (as in the record) and its status.
    b50 = sorted(blocks[-1], key=lambda t: t[0])
    top_ok = in_reg(b50[-1][1]) and b50[-1][1] >= 0.99 * VOUT_T
    d = legacy.get("dropout_v_50ma")
    floor = legacy.get("dropout_v_50ma_floor")
    if d is None or not top_ok:
        status, d_out = "never_in_regulation", None
    elif abs(d - floor) < 1e-9:
        status, d_out = "floor_limited_upper_bound", d
    else:
        status, d_out = "resolved_crossing", d
    out["dropout_legacy_v"] = d_out
    out["dropout_status"] = status
    # #70 candidate definition (Vin - actual VOUT at the last in-regulation
    # grid point). Informational ONLY; the definition is unresolved.
    alt = None
    if d_out is not None:
        last = None
        for v, vo, _, _ in reversed(b50):
            if vo < 0.99 * VOUT_T:
                break
            last = (v, vo)
        alt = last[0] - last[1] if last else None
    out["dropout_vin_minus_vout_candidate_v"] = alt
    out["valid"] = True
    return out


def reproduce_record(points, record_rows):
    """Check the raw grid reproduces the record CSV's DC columns. Returns a
    list of mismatch strings (empty == reproduces)."""
    bad = []
    key = lambda c, t, r: (c, str(t), r)  # noqa: E731
    rec = {key(r["corner"], r["temp_c"], r["res_section"]): r for r in record_rows}
    cols = [("iq_a", "iq_a"), ("vout_no_load_v", "vout_no_load_v"),
            ("line_reg_mv_per_v", "line_reg_mv_per_v"),
            ("dropout_v_50ma", "dropout_v_50ma"), ("load_reg_pct", "load_reg_pct")]
    for (c, t, r), a in points.items():
        rr = rec.get(key(c, t, r))
        if rr is None:
            bad.append(f"{c}/{t}/{r}: absent from record CSV")
            continue
        if not a.get("valid"):
            bad.append(f"{c}/{t}/{r}: raw grid invalid ({a.get('grid_problems')})")
            continue
        for mine, theirs in cols:
            x, y = a["legacy"].get(mine), rr.get(theirs)
            if x is None or y in (None, ""):
                if not (x is None and y in (None, "", "None")):
                    bad.append(f"{c}/{t}/{r}: {mine} {x} vs {y}")
                continue
            if abs(float(x) - float(y)) > 1e-9 * max(1.0, abs(float(y))):
                bad.append(f"{c}/{t}/{r}: {mine} {x} vs {y}")
    return bad


def csv_text(points):
    cols = ["corner", "temp_c", "res_section", "grid_ok", "iq_noload_a",
            "iq_fullload_excl_load_a", "iq_fullload_valid", "iq_fullload_noise_proxy_a"]
    cols += [f"line_reg_mv_per_v_{t}" for t in LOAD_TAGS]
    cols += [f"line_reg_valid_{t}" for t in LOAD_TAGS]
    for v in LOAD_REG_VINS:
        cols += [f"load_reg_pct_vin{VIN_TAGS[v]}", f"load_reg_valid_vin{VIN_TAGS[v]}",
                 f"vout_50mA_vin{VIN_TAGS[v]}_v"]
    cols += ["dropout_legacy_v", "dropout_status", "dropout_vin_minus_vout_candidate_v"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for (c, t, r), a in points.items():
        if not a.get("valid"):
            row = [c, t, r, False] + [""] * (len(cols) - 4)
            row[cols.index("dropout_status")] = "grid_invalid"
            w.writerow(row)
            continue
        row = [c, t, r, True, a["iq_by_load_a"]["0mA"], a["iq_by_load_a"]["50mA"],
               a["iq_full_valid"], a["iq_full_noise_proxy_a"]]
        row += [a["line_mv_per_v_by_load"][x] for x in LOAD_TAGS]
        row += [a["line_valid_by_load"][x] for x in LOAD_TAGS]
        for v in LOAD_REG_VINS:
            row += [a["load_reg_pct_by_vin"][v], a["load_reg_valid_by_vin"][v],
                    a["vout_full_load_by_vin"][v]]
        row += [a["dropout_legacy_v"], a["dropout_status"],
                a["dropout_vin_minus_vout_candidate_v"]]
        w.writerow([fmt(x) for x in row])
    return buf.getvalue()


def extreme(points, getter, valid=None, worst="max", absval=False):
    """Worst value over VALID points, with its corner and the counts of
    valid/invalid points (invalid ones are never dropped from the count)."""
    vals, n_total, n_invalid = [], 0, 0
    for (c, t, r), a in points.items():
        n_total += 1
        if not a.get("valid"):
            n_invalid += 1
            continue
        v = getter(a)
        ok = valid(a) if valid else True
        if v is None or not ok:
            n_invalid += 1
            continue
        vals.append((abs(v) if absval else v, v, (c, t, r)))
    if not vals:
        return {"n_points": n_total, "n_valid": 0, "n_invalid": n_invalid}
    pick = max(vals) if worst == "max" else min(vals)
    return {"n_points": n_total, "n_valid": len(vals), "n_invalid": n_invalid,
            "worst_value": pick[1], "worst_at": {"corner": pick[2][0], "temp_c": pick[2][1],
                                                   "res_section": pick[2][2]}}


def record_extreme(rows, col, worst="max"):
    vals = [(float(r[col]), r) for r in rows if r.get(col) not in (None, "", "None")]
    pick = max(vals, key=lambda t: t[0]) if worst == "max" else min(vals, key=lambda t: t[0])
    return {"n_points": len(rows), "n_valid": len(vals), "n_invalid": len(rows) - len(vals),
            "worst_value": pick[0],
            "worst_at": {"corner": pick[1]["corner"], "temp_c": int(pick[1]["temp_c"]),
                         "res_section": pick[1]["res_section"]}}


def build_inventory(points, record_rows, mismatches):
    P = points
    n = len(P)
    iq_no = extreme(P, lambda a: a["iq_by_load_a"]["0mA"])
    iq_full = extreme(P, lambda a: a["iq_by_load_a"]["50mA"], valid=lambda a: a["iq_full_valid"])
    line_loaded = {t: extreme(P, lambda a, t=t: a["line_mv_per_v_by_load"][t],
                              valid=lambda a, t=t: a["line_valid_by_load"][t], absval=True)
                   for t in LOAD_TAGS}
    load_reg = {VIN_TAGS[v]: extreme(P, lambda a, v=v: a["load_reg_pct_by_vin"][v],
                                     valid=lambda a, v=v: a["load_reg_valid_by_vin"][v],
                                     absval=True) for v in LOAD_REG_VINS}
    dropout = extreme(P, lambda a: a["dropout_legacy_v"])
    st = {}
    for a in P.values():
        s = a["dropout_status"] if a.get("valid") else "grid_invalid"
        st[s] = st.get(s, 0) + 1
    n_drop_below = sum(1 for a in P.values() if a.get("valid") and a["dropout_legacy_v"] is not None and a["dropout_legacy_v"] < 0.3)
    n_iq_below = sum(1 for a in P.values() if a.get("valid") and a["iq_full_valid"] and a["iq_by_load_a"]["0mA"] < 30e-6 and a["iq_by_load_a"]["50mA"] < 30e-6)
    alt = extreme(P, lambda a: a["dropout_vin_minus_vout_candidate_v"],
                  valid=lambda a: a["dropout_status"] == "resolved_crossing")
    n_full_inreg = {VIN_TAGS[v]: sum(1 for a in P.values() if a.get("valid") and a["load_reg_valid_by_vin"][v])
                    for v in LOAD_REG_VINS}
    n_line0_ok = sum(1 for a in P.values() if a.get("valid") and a["line_valid_by_load"]["0mA"])
    n_line50_ok = sum(1 for a in P.values() if a.get("valid") and a["line_valid_by_load"]["50mA"])

    common_gap = "SG13G2 branch: no closed-loop evidence (behavioural error-amp placeholder; #71)."
    rows = [
        dict(id=1, parameter="Input", target="3.3 V +/-10 %", status="open", kind="D",
             measurement_definition="Supply window 2.97-3.63 V over which the regulator holds VOUT within 1 % of 1.8 V.",
             unit="V",
             tested_axes="Vin 2.00-3.63 V step 10 mV x Iload {0,12.5,25,37.5,50} mA x 45 PVT-resistor points (DC).",
             untested_axes="Continuous-short |Vsg| <= 3.3 V gate at 3.63 V (no limiter, #63); normal-regulation |Vgs| check; SG13G2 branch.",
             evidence_paths=[RECORD_CSV, CORNERS_DIR],
             informational_measurement={"in_regulation_at_both_window_ends_noload": f"{n_line0_ok}/{n}",
                                        "in_regulation_at_both_window_ends_50mA": f"{n_line50_ok}/{n}"},
             measured_verdict="informational: regulation window reproduced at DC; device-rating gate unevidenced",
             binding_corner=None, gate="none", open_issues=["#63", "#71"]),
        dict(id=2, parameter="Output", target="1.8 V +/-2 % (fixed)", status="open", kind="S",
             measurement_definition="No-load VOUT at Vin = 3.30 V with an IDEAL 0.90 V reference (regulator-only; excludes reference error and offset/mismatch).",
             unit="V",
             tested_axes="PVT-resistor corners only; deterministic.",
             untested_axes="Monte Carlo offset/divider mismatch (#56); reference error.",
             evidence_paths=[RECORD_CSV],
             informational_measurement=record_extreme(record_rows, "vout_no_load_v", "max"),
             measured_verdict="informational: corner-only spread inside the band; statistical row, not decidable by corners",
             binding_corner=None, gate="none", open_issues=["#56"]),
        dict(id=3, parameter="Load", target="0-50 mA (no external preload assumed)", status="open", kind="D",
             measurement_definition="DC regulation at five load points 0-50 mA; in regulation = |VOUT-1.8| < 1 % of 1.8 V.",
             unit="A",
             tested_axes="Iload x5 DC; Vin 2.00-3.63 V.",
             untested_axes="Dynamic/no-preload stability at 0 mA (#64); stretch 100 mA.",
             evidence_paths=[RECORD_CSV, CORNERS_DIR],
             informational_measurement={"points_in_regulation_at_50mA_by_vin": {k: f"{v}/{n}" for k, v in n_full_inreg.items()}},
             measured_verdict="informational: DC load span covered; dynamic coverage absent",
             binding_corner=None, gate="none", open_issues=["#64"]),
        dict(id=4, parameter="Dropout @ 50 mA", target="< 300 mV worst corner", status="ratified", kind="D",
             measurement_definition=("LEGACY metric: lowest Vin on the 10 mV grid at which VOUT >= 0.99 x 1.8 V (scanning down from 3.63 V) "
                                    "minus the fixed 1.8 V target. NOT Vin - actual VOUT at 1 % loss; that definition is unresolved (#70)."),
             unit="V",
             tested_axes="Iload = 50 mA; Vin 2.00-3.63 V step 10 mV (sweep floor 0.20 V); 45 PVT-resistor points.",
             untested_axes="Stretch < 200 mV (not ratified); finer sweep below the floor; definition per #70; SG13G2 branch (#71, unevidenced/unmet); post-layout (#57).",
             evidence_paths=[RECORD_CSV, CORNERS_DIR, f"{OUT_DIR}/dc-informational-summary.csv"],
             measurement={"status_counts": st, "legacy_worst": dropout,
                          "candidate_vin_minus_vout_at_resolved_points_informational_pending_70": alt,
                          "target_v": 0.3},
             measured_verdict=(f"legacy metric < 0.3 V at {n_drop_below}/{n} points ({st.get('floor_limited_upper_bound', 0)} floor-limited "
                               f"upper bounds, {st.get('resolved_crossing', 0)} resolved crossings, {st.get('never_in_regulation', 0)} never in regulation, "
                               f"{st.get('grid_invalid', 0)} invalid grids); worst {dropout.get('worst_value')} V. QUALIFIED evidence only: "
                               "no klt sim envelope, definition unresolved (#70), SG13G2 branch unevidenced (#71). "
                               "Not a completeness or definitive-margin claim."),
             binding_corner=dropout.get("worst_at"), gate="ratified requirement; gate NOT closed by this evidence",
             open_issues=["#70", "#71", "#57"]),
        dict(id=5, parameter="Line / load regulation", target="< 5 mV/V; < 1 % over full load, inside the accuracy window", status="open", kind="D",
             measurement_definition=("Line: |dVOUT/dVin| over 2.97-3.63 V at each load. Load: (V(0 mA)-V(50 mA))/V(0 mA) at fixed Vin. "
                                    "A value is VALID only if both end points are within 1 % of 1.8 V."),
             unit="mV/V ; %",
             tested_axes="Line at 5 loads; load regulation at Vin 2.97/3.30/3.63 V; 45 points; DC.",
             untested_axes="Accuracy-window coupling with row 2 (statistical, #56); dynamic regulation.",
             evidence_paths=[f"{OUT_DIR}/dc-informational-summary.csv", CORNERS_DIR],
             informational_measurement={"line_worst_by_load": line_loaded, "load_reg_worst_by_vin": load_reg},
             measured_verdict="informational: see worst values; invalid (out-of-regulation) points are counted, not dropped",
             binding_corner=None, gate="none", open_issues=["#56"]),
        dict(id=6, parameter="PSRR", target="> 50 dB @ 1 kHz, > 20 dB @ 100 kHz", status="open", kind="D",
             measurement_definition="Closed-loop AC supply-to-output rejection from the committed record.",
             unit="dB",
             tested_axes="Vin = 3.30 V, Iload = 1 mA, Cout = 1 uF, ESR = 0, 45 points; Cc nominal (no corner spread).",
             untested_axes="50 mA, Cout/ESR window (#64); Cc corner spread (record: insufficient-evidence).",
             evidence_paths=[RECORD_CSV],
             informational_measurement={"1kHz_min": record_extreme(record_rows, "psrr_db_1khz", "min"),
                                        "100kHz_min": record_extreme(record_rows, "psrr_db_100khz", "min")},
             measured_verdict="informational: carried from the record unchanged; not re-derived here (AC data)",
             binding_corner=record_extreme(record_rows, "psrr_db_1khz", "min")["worst_at"],
             gate="none", open_issues=["#64"]),
        dict(id=7, parameter="Iq (excl. load)", target="< 30 uA at no load and at full load", status="open", kind="D",
             measurement_definition="|i(Vin)| minus the load current, at Vin = 3.30 V (includes bias and divider standing current).",
             unit="A",
             tested_axes="No load and 50 mA (and intermediate loads in the CSV); Vin 3.30 V; 45 points.",
             untested_axes="Other supplies; stretch < 10 uA is not met by the data.",
             evidence_paths=[f"{OUT_DIR}/dc-informational-summary.csv", RECORD_CSV],
             informational_measurement={"no_load_worst": iq_no, "full_load_worst": iq_full,
                                        "full_load_print_resolution_a": 1e-10,
                                        "full_load_noise_proxy_worst_a": max(
                                            (a["iq_full_noise_proxy_a"] or 0.0) for a in P.values() if a.get("valid")),
                                        "target_a": 30e-6},
             measured_verdict=f"informational: no-load and full-load Iq both < 30 uA at {n_iq_below}/{n} points; resolution = 9-digit print quantum (1e-10 A), solver-noise proxy at that floor",
             binding_corner=iq_full.get("worst_at"), gate="none", open_issues=[]),
        dict(id=8, parameter="Current limit", target="65-80 mA brickwall over PVT; short-survivable", status="open", kind="S",
             measurement_definition="Not defined by any bench: no limiter exists.", unit="A",
             tested_axes="none", untested_axes="everything", evidence_paths=[],
             informational_measurement=None, measured_verdict="not implemented",
             binding_corner=None, gate="none", open_issues=["#63", "#56"]),
        dict(id=9, parameter="Startup", target="monotonic, controlled ramp, inside +/-2 % within 3 ms of enable", status="open", kind="D",
             measurement_definition="Not defined by any bench: no enable input or transient bench exists.", unit="s",
             tested_axes="none", untested_axes="everything", evidence_paths=[],
             informational_measurement=None, measured_verdict="not implemented",
             binding_corner=None, gate="none", open_issues=["#67", "#68", "#69"]),
        dict(id=10, parameter="Stability", target="0-50 mA, C_out 0.33-4.7 uF, ESR 0-500 mOhm; PM >= 45 deg, GM >= 10 dB worst corner", status="open", kind="D",
             measurement_definition="Loop broken at FB; phase/gain margin from the committed record.",
             unit="deg ; dB",
             tested_axes="One (Cout, ESR, Iload) point: 1 uF, 0 ohm, 1 mA; Vin 3.30 V; 45 points; Cc nominal.",
             untested_axes="Rest of the load/Cout/ESR window (#64); Cc corner spread.",
             evidence_paths=[RECORD_CSV],
             informational_measurement={"phase_margin_min": record_extreme(record_rows, "phase_margin_deg", "min"),
                                        "gain_margin_min": record_extreme(record_rows, "gain_margin_db", "min")},
             measured_verdict="informational: plumbing-grade subset of the row only; carried from the record unchanged",
             binding_corner=record_extreme(record_rows, "phase_margin_deg", "min")["worst_at"],
             gate="none", open_issues=["#64"]),
    ]
    for r in rows:
        r["pdk_branch"] = ("SG13CMOS5L closed-loop (design/sg13cmos5l); " + common_gap
                           if r["evidence_paths"] else "none")
        r["transfer_to_sg13g2"] = "not claimed"
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="verify committed outputs reproduce byte-for-byte")
    args = ap.parse_args()

    problems = []
    if sha256_file(RECORD_CSV) != RECORD_CSV_PIN:
        problems.append(f"{RECORD_CSV} differs from its pin")
    for p, h in DESIGN_PINS.items():
        if sha256_file(p) != h:
            problems.append(f"{p} differs from the hash the record was judged current against: evidence is STALE against the design")
    if problems:
        sys.exit("item5_evidence: " + "; ".join(problems))

    with open(os.path.join(REPO, RECORD_CSV)) as f:
        record_rows = list(csv.DictReader(f))
    points = {}
    for c, t, r, path in point_files():
        points[(c, t, r)] = analyse_point(path)
    mism = reproduce_record(points, record_rows)
    if mism:
        sys.exit("item5_evidence: raw grid does not reproduce the record CSV:\n  " + "\n  ".join(mism[:20]))

    inv_rows = build_inventory(points, record_rows, mism)
    raw_hashes = {p: sha256_file(p) for _, _, _, p in point_files()}
    inventory = {
        "schema_version": 1,
        "title": "sg13g2-ldo T1 item 5 coverage inventory (DR-0007 ten rows)",
        "generator": {"path": "sim/ldo-cmos5l-pvt-sweep/item5_evidence.py", "version": 1,
                      "sha256": sha256_file("sim/ldo-cmos5l-pvt-sweep/item5_evidence.py"),
                      "parser": {"path": "sim/ldo-cmos5l-pvt-sweep/dc_metrics.py",
                                 "sha256": sha256_file("sim/ldo-cmos5l-pvt-sweep/dc_metrics.py")}},
        "reproduce": "python3 sim/ldo-cmos5l-pvt-sweep/item5_evidence.py --check",
        "purpose_and_limits": [
            "Coverage accounting, not compliance. Only row 4 is ratified (DR-0007); nine rows are Open and are informational here, never upgraded to ratified passes.",
            "Every number is derived from committed SG13CMOS5L raw data or carried from the committed record CSV. Nothing is transferred to SG13G2 (#71).",
            "No new simulation was run. No klt sim envelope was produced; see klt_sim_envelope.",
        ],
        "inputs": {
            "decision_record": {"path": DR7, "sha256": sha256_file(DR7)},
            "record_csv": {"path": RECORD_CSV, "sha256": sha256_file(RECORD_CSV)},
            "record_md": {"path": RECORD_MD, "sha256": sha256_file(RECORD_MD)},
            "design_netlists": {p: sha256_file(p) for p in DESIGN_NETLISTS},
            "raw_dc_grids": raw_hashes,
        },
        "provenance_caveats": [
            "Record 20261010-025634-60a3e81 was made by run_sweep.sh --batch at PR #87 branch commit 60a3e81. That commit stopped resolving when the branch was rebased onto #64. Regenerating all 214 decks with the rebased harness gives decks that are line-for-line identical apart from comments, and that check was run. Its netlist snapshots .include the design by an absolute worktree path, but the record md states the sha256 of both design netlists it ran against, and those equal the pins here, so netlist freshness is recorded rather than inferred.",
            "Every point ran on the EDA batch fleet (runner klt 0.5.0, ngspice-46) at PDK commit 607e18d (sim/pdk-cmos5l.json). The six OSDI binaries, including cap_cmomi, were staged from the submitting host's build, and their sha256 appears in every per-point log. The rawfile-to-wrdata reduction reproduced six points of the local ngspice-46 record 20260917-023832-7061e8f byte-for-byte (sim/ldo-cmos5l-pvt-sweep/backend-validation/20261010-025044/).",
            "The design under test carries the #67 EN interface (DR-0008), with EN tied to VIN in every bench. The disabled state is not part of this grid.",
            "Cap model: cornerCAP.lib maps every section to one nominal cap_cmomi, so Cc has no process-corner spread; this affects the AC rows (6, 10) not the DC grid used here.",
            "Reference is an ideal 0.90 V source; supply is swept 2.00-3.63 V; Ibias is an ideal 2 uA sink; loads are ideal DC current sources; Cout = 1 uF is irrelevant at DC.",
        ],
        "grid": {"corners": CORNERS, "temps_c": TEMPS, "res_sections": RES, "points": len(points),
                 "points_valid": sum(1 for a in points.values() if a.get("valid")),
                 "independence": "MOS x temperature x resistor crossed independently (45 combinations, no assumed correlation)",
                 "reproduces_record_csv": True},
        "klt_sim_envelope": {
            "produced": False,
            "reason": ("The raw grid now comes from 22 klt sim batch requests (reports under corners/<record>/_batch/). Those requests declare no limits, "
                       "and the metrics are reduced from rawfiles outside klt, so they are measurement runs, not a corner-matrix envelope graded against the "
                       "ratified spec. klt sim's batch backend still refuses models.pdk=ihp-sg13cmos5l (klayout-tools#2727), and the runner's klt 0.5.0 "
                       "ignores options.osdi_preload (klayout-tools#2901), so the runs depend on staged libraries and a body-level pre_osdi preamble. "
                       "A success envelope is never synthesized or hand-wrapped from the CSVs."),
            "tool_gap_issue": "2AMLogic/klayout-tools#2727; 2AMLogic/klayout-tools#2901",
            "signoff_item_5": "uncited / unmet; signoff/sg13g2-ldo.json is unchanged",
        },
        "rows": inv_rows,
        "summary": {
            "rows_total": len(inv_rows),
            "ratified_rows": [r["id"] for r in inv_rows if r["status"] == "ratified"],
            "open_rows": [r["id"] for r in inv_rows if r["status"] == "open"],
            "rows_not_implemented": [r["id"] for r in inv_rows if r["measured_verdict"] == "not implemented"],
            "ratified_pass_claims": 0,
        },
    }

    outputs = {
        f"{OUT_DIR}/dc-informational-summary.csv": csv_text(points),
        f"{OUT_DIR}/coverage-inventory.json": json.dumps(inventory, indent=2, sort_keys=True) + "\n",
    }
    outputs[f"{OUT_DIR}/coverage-inventory.md"] = render_md(inventory)

    if args.check:
        bad = []
        for rel, text in outputs.items():
            p = os.path.join(REPO, rel)
            if not os.path.exists(p) or open(p).read() != text:
                bad.append(rel)
        if bad:
            sys.exit("item5_evidence --check: drifted or missing: " + ", ".join(bad))
        print("item5_evidence --check: committed outputs reproduce byte-for-byte")
        return
    os.makedirs(os.path.join(REPO, OUT_DIR), exist_ok=True)
    for rel, text in outputs.items():
        with open(os.path.join(REPO, rel), "w") as f:
            f.write(text)
    print(f"item5_evidence: wrote {len(outputs)} files under {OUT_DIR}")


def _ws(x):
    if not isinstance(x, dict) or "worst_value" not in x:
        return "n/a"
    a = x["worst_at"]
    return f"{x['worst_value']:.6g} at {a['corner']}/{a['temp_c']}C/{a['res_section']} ({x['n_valid']}/{x['n_points']} valid)"


def render_md(inv):
    L = [f"# {inv['title']}", "", "Generated by `" + inv["generator"]["path"] + "`; do not edit by hand.",
         "Reproduce: `" + inv["reproduce"] + "`.", ""]
    for s in inv["purpose_and_limits"]:
        L.append(f"- {s}")
    L += ["", "## klt sim envelope", "", f"- produced: **{inv['klt_sim_envelope']['produced']}**",
          f"- {inv['klt_sim_envelope']['reason']}", f"- tool gap: {inv['klt_sim_envelope']['tool_gap_issue']}",
          f"- signoff item 5: {inv['klt_sim_envelope']['signoff_item_5']}", "",
          "## Provenance caveats", ""]
    L += [f"- {c}" for c in inv["provenance_caveats"]]
    L += ["", "## Ten-row inventory", "",
          "| # | Row | DR-0007 | Type | Unit | Gate | Measured verdict | Binding corner |", "|---|---|---|---|---|---|---|---|"]
    for r in inv["rows"]:
        b = r["binding_corner"]
        bs = f"{b['corner']}/{b['temp_c']}C/{b['res_section']}" if isinstance(b, dict) else "-"
        L.append(f"| {r['id']} | {r['parameter']} | {r['status']} | {r['kind']} | {r['unit']} | {r['gate']} | {r['measured_verdict']} | {bs} |")
    L += ["", "## Per-row detail", ""]
    for r in inv["rows"]:
        L += [f"### Row {r['id']}: {r['parameter']} ({r['status']})", "",
              f"- target: {r['target']}", f"- definition: {r['measurement_definition']}",
              f"- PDK branch: {r['pdk_branch']}", f"- tested axes: {r['tested_axes']}",
              f"- untested axes: {r['untested_axes']}",
              f"- evidence: {', '.join(r['evidence_paths']) or 'none'}",
              f"- open issues: {', '.join(r['open_issues']) or 'none'}"]
        im = r.get("informational_measurement")
        if isinstance(im, dict):
            for k, v in im.items():
                if isinstance(v, dict) and "worst_value" in v:
                    L.append(f"- {k}: {_ws(v)}")
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        L.append(f"- {k} / {k2}: {_ws(v2) if isinstance(v2, dict) else v2}")
                else:
                    L.append(f"- {k}: {v}")
        m = r.get("measurement")
        if m:
            L.append(f"- status counts (45 points): {m['status_counts']}")
            L.append(f"- legacy worst: {_ws(m['legacy_worst'])}")
            L.append("- #70 candidate (Vin - actual VOUT, resolved points only, informational): "
                     + _ws(m["candidate_vin_minus_vout_at_resolved_points_informational_pending_70"]))
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
