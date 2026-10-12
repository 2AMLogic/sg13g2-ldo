#!/usr/bin/env python3
"""E1 DC operating-point reducer (issue #158). stdlib only.

Offline reduction of the four DR-0015 E1 fleet runs (DC operating points at
P1/P2/P5/P6, bench `tb_e1op_cmos5l.spice.tmpl`, campaign `run_e1op.sh`) into
the record's CSV + JSON + narrative md. This module owns:

  * the QUANTITIES contract -- the ordered wrdata token list the template's
    `.save` card and wrdata line must name (`tokens` prints it; a test
    cross-checks template against this list, so deck and reducer cannot
    drift);
  * check-export -- per-point raw-export screening (row/column shape, the
    3.299/3.300/3.301 V bracket axis, finiteness);
  * reduce -- per-point extraction of the middle row (v-sweep exactly 3.3 V
    = the operating point), circuit-level consistency checks (KCL at VOUT,
    the FB/FBAMP break current, the regulation band, sign conventions, the
    fleet liveness measurement) and the DERIVED quantities the DR-0015
    class-1 analysis needs (r_o, per-leg divider resistance, an
    Early-voltage equivalent, the two low-frequency pole ESTIMATES). Every
    derived pole is an estimate with stated assumptions and missing-C
    disclosures -- none is presented as a directly measured pole;
  * record-md -- the narrative record, derived only from committed files;
  * check -- regenerate CSV/JSON/md into a temp dir and byte-compare (CI).

Subcommands:
    tokens                             print the QUANTITIES token list
    check-export CSV                   screen one raw export
    reduce --record RID --out-csv P --out-json P [--cc-f F]
    record-md --record RID
    check --record RID

Sign conventions (the deck header documents the same list): the PSP103 OSDI
`[ids]` is the magnitude-signed drain current -- positive when the device
conducts, for BOTH polarities; an off device reports tiny positive leakage.
i(vin) < 0 while the rail delivers; i(vdivsense) > 0 into the replica
divider; i(vbreak) ~ 0 is the loop-break validity check; a negative ids
anywhere is a unit/sign mistake. PSP cap signs may be negative; cap
magnitudes are reported and never sign-checked.

Error discipline: a missing per-point export, a nonfinite value, a broken
sign convention or a failed consistency check is never silently dropped.
reduce writes its outputs either way and exits 3 when any check failed, so
the campaign publishes an explicitly incomplete record; missing files refuse
to reduce at all (exit 2).
"""
import argparse
import csv
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# The four DR-0015 E1 points (spec/decision-records/DR-0015-....md, "The six
# points"): P1/P2/P5 are the zero-load class-1/class-3 points, P6 is the
# 1 mA legacy reference. ESR = 0 everywhere; cap section cap_typ everywhere
# (the MoM-cap corner sections are nominal by construction --
# sim/pdk-cmos5l.json "mom_cap_no_corner_or_mismatch_model").
# (name, mos, res, temp C, load A, Cout F)
POINTS = (
    ("P1", "ss", "bcs", 125, 0.0, 1.0e-6),
    ("P2", "ff", "wcs", -40, 0.0, 1.0e-6),
    ("P5", "ss", "wcs", 125, 0.0, 3.45e-6),
    ("P6", "ss", "bcs", 125, 0.001, 1.0e-6),
)
BENCH = "e1op"
SUFFIX = "_dc.csv"
SWEEP_V = (3.299, 3.300, 3.301)   # the bracket axis the template sweeps
SWEEP_RTOL = 1e-9
N_ROWS = 3

# Cc's designed value at the committed compensation (DR-0005: `w=170um,
# l=30um` cap_cmomi, ~5.5 pF). Consumed only by the EAOUT-node pole ESTIMATE.
CC_F_NOMINAL = 5.5e-12

_PMOS_DEVICES = (
    "xmpass", "xmen", "xmbdis",
    "xamp.xmb0", "xamp.xmtail", "xamp.xmload2",
    "xamp.xminp", "xamp.xminn", "xamp.xminvp",
)
_NMOS_DEVICES = (
    "xamp.xmn1", "xamp.xmn2", "xamp.xmn3", "xamp.xminvn", "xamp.xmpd",
)

NODES = (
    "v(vout)", "v(eaout)", "v(fb)", "v(fbamp)", "v(vref)", "v(en)", "v(ibias)",
    "v(xamp.g1)", "v(xamp.mz)", "v(xamp.n1)", "v(xamp.tail)", "v(xamp.enb)",
    "v(reptop)",
)
SRC_CURRENTS = ("i(vdivsense)", "i(vin)", "i(vbreak)")


def _quantities():
    """The ordered token contract: nodes, source currents, then every saved
    device parameter (ids/gm/gds per device in the template's .save order,
    then the extra caps/vth)."""
    toks = list(NODES) + list(SRC_CURRENTS)
    for d in _PMOS_DEVICES:
        for p in ("ids", "gm", "gds"):
            toks.append(f"@n.{d}.nsg13_hv_pmos[{p}]")
    for d in _NMOS_DEVICES:
        for p in ("ids", "gm", "gds"):
            toks.append(f"@n.{d}.nsg13_hv_nmos[{p}]")
    toks += [
        "@n.xmpass.nsg13_hv_pmos[cgs]", "@n.xmpass.nsg13_hv_pmos[cgd]",
        "@n.xmpass.nsg13_hv_pmos[cdd]", "@n.xmpass.nsg13_hv_pmos[vth]",
        "@n.xamp.xmn3.nsg13_hv_nmos[cgs]", "@n.xamp.xmn3.nsg13_hv_nmos[cgd]",
    ]
    return toks


QUANTITIES = _quantities()
UNIT = {"ids": "A", "gm": "S", "gds": "S", "cgs": "F", "cgd": "F",
        "cdd": "F", "vth": "V"}

CSV_FIELDS = (["point", "mos", "res", "temp_c", "load_a", "cout_f", "point_id"]
              + ["op:" + t for t in QUANTITIES] + [
                  "derived:ro_pass_ohm", "derived:r_leg_ohm", "derived:r_div_ohm",
                  "derived:va_equiv_pass_V", "derived:cout_total_F",
                  "derived:est_f_pole_vout_hz", "derived:r_out_amp_ohm",
                  "derived:c_eaout_F", "derived:est_f_pole_eaout_hz",
                  "derived:est_f_pole_g1_hz", "derived:kcl_residual_A",
                  "check:vbreak_ok", "check:signs_ok", "check:kcl_ok",
                  "check:regulation_ok", "check:finite_ok", "check:liveness_ok",
                  "check:all_ok", "note"])


def point_id(pt):
    name, mos, res, temp, load_a, cout_f = pt
    tok = (f"i{int(round(load_a * 1e6))}ua_c{int(round(cout_f * 1e9))}nf_e0mohm")
    return f"{BENCH}_dyn_{mos}_{temp}c_r{res}_{tok}"


def _fmt(x):
    return f"{x:.8e}"


# ---- export screening ---------------------------------------------------- #
def _rows(path):
    """Parse a wrdata-style export (whitespace-separated numbers, exactly
    what ngspice's wrdata writes locally and batch_backend.py's
    wrdata_rows writes from the rawfile). Returns float rows."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            parts = ln.split()
            if parts:
                out.append([float(x) for x in parts])
    return out


def check_export(path):
    """Screen one raw per-point export: 3 rows x (2*len(QUANTITIES))
    columns -- wrdata's (x, value) pair per token, x repeated -- bracket
    axis, everything finite. Raises ValueError on any violation (the
    campaign screens before reducing)."""
    rows = _rows(path)
    ncols = 2 * len(QUANTITIES)
    if len(rows) != N_ROWS:
        raise ValueError(f"{path}: {len(rows)} rows, expected {N_ROWS}")
    for i, vals in enumerate(rows):
        if len(vals) != ncols:
            raise ValueError(f"{path}: row {i} has {len(vals)} cols, expected {ncols}")
        for v in vals:
            if not math.isfinite(v):
                raise ValueError(f"{path}: row {i} has a nonfinite value")
        if abs(vals[0] - SWEEP_V[i]) > SWEEP_RTOL:
            raise ValueError(f"{path}: row {i} sweep value {vals[0]!r} != {SWEEP_V[i]!r}")
    return ncols


# ---- expected-sign contract (see module docstring) ------------------------ #
# Empirical convention of this PDK's PSP103 OSDI build (verified in the
# --validate probe and re-verified by the record's own checks): `[ids]` is
# the magnitude-signed drain current -- POSITIVE when the device conducts,
# for BOTH polarities; an off device reports tiny positive leakage.
# i(vin) < 0 while the rail delivers; i(vdivsense) > 0 into the replica
# divider; i(vbreak) = 0. A negative ids anywhere is a unit/sign mistake.
def _sign_checks(pt):
    load_a = pt[4]
    checks = [
        ("@n.xmpass.nsg13_hv_pmos[ids]", ">=",
         1e-7 if load_a == 0 else 1e-6,
         "conducting PMOS pass device: |ids| = divider + load current"),
        ("@n.xamp.xminp.nsg13_hv_pmos[ids]", ">=", 1e-9,
         "conducting PMOS input pair"),
        ("@n.xamp.xmtail.nsg13_hv_pmos[ids]", ">=", 1e-9,
         "conducting PMOS tail source"),
        ("@n.xamp.xmload2.nsg13_hv_pmos[ids]", ">=", 1e-9,
         "conducting PMOS second-stage load"),
        ("@n.xamp.xmn3.nsg13_hv_nmos[ids]", ">=", 1e-9,
         "conducting NMOS second stage"),
        ("@n.xmen.nsg13_hv_pmos[ids]", "<=", 1e-8,
         "Men is off (gate at VIN): leakage only"),
        ("@n.xmbdis.nsg13_hv_pmos[ids]", "<=", 1e-8,
         "Mbdis is off (gate at VIN): leakage only"),
        ("@n.xamp.xmpd.nsg13_hv_nmos[ids]", "<=", 1e-8,
         "the G1 pull-down is off (EN high): leakage only"),
        ("i(vin)", "<=", -1e-9,
         "the rail delivers current: i(vin) < 0"),
        ("i(vdivsense)", ">=", 1e-9,
         "current into the replica divider"),
    ]
    return checks


def read_op(csv_path):
    """The operating point (middle row) as {token: value} plus the bracket
    axis endpoints. Shape is re-validated here so read_op alone is safe."""
    rows = _rows(csv_path)
    if len(rows) != N_ROWS:
        raise ValueError(f"{csv_path}: {len(rows)} rows, expected {N_ROWS}")
    ncols = 2 * len(QUANTITIES)
    for vals in rows:
        if len(vals) != ncols:
            raise ValueError(f"{csv_path}: row has {len(vals)} cols, expected {ncols}")
    mid = rows[1]
    op = {tok: mid[1 + 2 * k] for k, tok in enumerate(QUANTITIES)}
    return rows[0][0], rows[-1][0], op


def reduce_point(pt, csv_path, liveness_vout, cc_f):
    """Reduce one point. Returns (row dict, failed-check names). Every check
    failure is recorded, not raised, so the record can name them all."""
    name, mos, res, temp, load_a, cout_f = pt
    sweep_lo, sweep_hi, op = read_op(csv_path)
    row = {"point": name, "mos": mos, "res": res, "temp_c": temp,
           "load_a": _fmt(load_a), "cout_f": _fmt(cout_f),
           "point_id": point_id(pt)}
    notes = []
    failed = []

    def fin(x):
        return isinstance(x, float) and math.isfinite(x)

    finite_ok = all(fin(v) for v in op.values())
    if not finite_ok:
        failed.append("finite")
    for tok in QUANTITIES:
        row["op:" + tok] = _fmt(op[tok]) if fin(op[tok]) else ""

    # --- circuit-level consistency checks --------------------------------- #
    vout = op["v(vout)"]
    idiv = op["i(vdivsense)"]
    ivin = op["i(vin)"]
    ivbreak = op["i(vbreak)"]
    ids_pass = op["@n.xmpass.nsg13_hv_pmos[ids]"]

    vbreak_ok = fin(ivbreak) and abs(ivbreak) <= 1e-12
    if not vbreak_ok:
        failed.append("vbreak")
        notes.append(f"i(vbreak)={ivbreak:.3e} A exceeds 1 pA -- the FB/FBAMP "
                     "break is drawing current; the DC op point is not the closed loop's")

    kcl_residual = abs(ids_pass) - (idiv + load_a)
    # Tolerance: the absolute floor clears the VOUT node's real junction
    # leakage (measured ~9.8 nA at the ss/125C points, ~0 at ff/-40C -- a
    # physical, load-independent residual, not a unit/sign mistake); the
    # relative term (0.01%) catches any actual bookkeeping error at either
    # scale.
    kcl_ok = (fin(kcl_residual)
              and abs(kcl_residual) <= max(1e-7, 1e-4 * (idiv + load_a)))
    if not kcl_ok:
        failed.append("kcl")
        notes.append(f"KCL at VOUT: |ids_pass| - (I_div + Iload) = {kcl_residual:.3e} A")

    regulation_ok = fin(vout) and 1.7 <= vout <= 1.9
    if not regulation_ok:
        failed.append("regulation")
        notes.append(f"v(vout)={vout:.4f} V outside the 1.7-1.9 V regulation band")

    signs_ok = True
    for tok, cmp_, bound, why in _sign_checks(pt):
        v = op[tok]
        ok = fin(v) and ((cmp_ == "<=" and v <= bound) or (cmp_ == ">=" and v >= bound))
        if not ok:
            signs_ok = False
            notes.append(f"sign convention violated: {tok}={v:.4e} "
                         f"(expected {cmp_} {bound:.1e}; {why})")
    if not signs_ok:
        failed.append("signs")

    # The runner's harvested liveness value carries ~6 significant digits
    # (the .meas line it parses is printed to that precision), so exact
    # equality is not available; 1e-5 relative still catches any real
    # disagreement (a different simulation) by orders of magnitude.
    liveness_ok = (liveness_vout is not None and fin(vout)
                   and abs(liveness_vout - vout) <= 1e-5 * max(1.0, abs(vout)))
    if not liveness_ok:
        failed.append("liveness")
        notes.append(f"the fleet's liveness_vout .meas ({liveness_vout!r}) disagrees "
                     f"with the CSV's v(vout) ({vout!r})")

    # --- derived quantities (ESTIMATES; limitations in the record md) ----- #
    gds = op["@n.xmpass.nsg13_hv_pmos[gds]"]
    cdd = op["@n.xmpass.nsg13_hv_pmos[cdd]"]
    gds_n3 = op["@n.xamp.xmn3.nsg13_hv_nmos[gds]"]
    gm_n3 = op["@n.xamp.xmn3.nsg13_hv_nmos[gm]"]
    gds_load2 = op["@n.xamp.xmload2.nsg13_hv_pmos[gds]"]
    gds_inp = op["@n.xamp.xminp.nsg13_hv_pmos[gds]"]
    gds_n2 = op["@n.xamp.xmn2.nsg13_hv_nmos[gds]"]
    cgs_n3 = op["@n.xamp.xmn3.nsg13_hv_nmos[cgs]"]
    cgd_n3 = op["@n.xamp.xmn3.nsg13_hv_nmos[cgd]"]
    cgs_pass = op["@n.xmpass.nsg13_hv_pmos[cgs]"]
    cgd_pass = op["@n.xmpass.nsg13_hv_pmos[cgd]"]

    def inv(x):
        return 1.0 / x if fin(x) and x != 0 else float("nan")

    def par(a, b):
        if not (fin(a) and fin(b)) or a + b == 0:
            return float("nan")
        return (a * b) / (a + b)

    def est_rc(r, c):
        if not (fin(r) and fin(c)) or r <= 0 or c <= 0:
            return float("nan")
        return 1.0 / (2.0 * math.pi * r * c)

    ro_pass = inv(gds)
    r_leg = (vout / 2.0) / idiv if fin(vout) and fin(idiv) and idiv != 0 else float("nan")
    r_div = 2.0 * r_leg if fin(r_leg) else float("nan")
    va_equiv = abs(ids_pass) * ro_pass if fin(ids_pass) else float("nan")
    cout_total = cout_f + abs(cdd) if fin(cdd) else cout_f
    r_seen_vout = par(ro_pass, r_div)
    f_pole_vout = est_rc(r_seen_vout, cout_total)

    r_out_amp = inv(gds_n3 + gds_load2)
    c_eaout = cc_f + abs(cgs_pass) + abs(cgd_pass) + abs(cgs_n3) + abs(cgd_n3)
    f_pole_eaout = est_rc(r_out_amp, c_eaout)
    # G1 node (first-stage output): R = ro(XMinp) || ro(XMn2); the Miller cap
    # appears there multiplied by the second-stage gain magnitude.
    r_g1 = par(inv(gds_inp), inv(gds_n2))
    a2 = abs(gm_n3) * r_out_amp if fin(gm_n3) and fin(r_out_amp) else float("nan")
    c_g1_eff = cc_f * (1.0 + a2) if fin(a2) else float("nan")
    f_pole_g1 = est_rc(r_g1, c_g1_eff)

    row.update({
        "derived:ro_pass_ohm": _fmt(ro_pass),
        "derived:r_leg_ohm": _fmt(r_leg),
        "derived:r_div_ohm": _fmt(r_div),
        "derived:va_equiv_pass_V": _fmt(va_equiv),
        "derived:cout_total_F": _fmt(cout_total),
        "derived:est_f_pole_vout_hz": _fmt(f_pole_vout),
        "derived:r_out_amp_ohm": _fmt(r_out_amp),
        "derived:c_eaout_F": _fmt(c_eaout),
        "derived:est_f_pole_eaout_hz": _fmt(f_pole_eaout),
        "derived:est_f_pole_g1_hz": _fmt(f_pole_g1),
        "derived:kcl_residual_A": _fmt(kcl_residual),
        "check:vbreak_ok": str(vbreak_ok),
        "check:signs_ok": str(signs_ok),
        "check:kcl_ok": str(kcl_ok),
        "check:regulation_ok": str(regulation_ok),
        "check:finite_ok": str(finite_ok),
        "check:liveness_ok": str(liveness_ok),
        "check:all_ok": str(not failed),
        "note": "; ".join(notes),
    })
    return row, failed


def _liveness_by_point(corners_dir):
    """liveness_vout per point_id from the batch provenance: points.tsv maps
    point_id -> (process, temperature); report.json carries the harvested
    .meas values. {} when provenance is absent (a local debug run)."""
    out = {}
    prov = os.path.join(corners_dir, "_batch")
    pts = os.path.join(prov, "points.tsv")
    if not (os.path.isfile(pts) and os.path.isdir(prov)):
        return out
    reports = {}
    for g in sorted(os.listdir(prov)):
        rp = os.path.join(prov, g, "report.json")
        if os.path.isfile(rp):
            try:
                reports[g] = json.load(open(rp))
            except ValueError:
                pass
    with open(pts) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            if not ln.strip():
                continue
            row = dict(zip(header, ln.rstrip("\n").split("\t")))
            pid, group = row["point_id"], row["group"]
            proc, temp = row["process"], float(row["temperature_c"])
            rep = reports.get(group) or {}
            for c in rep.get("corners", []):
                if c.get("process") == proc and float(c.get("temperature_c")) == temp:
                    for m in (c.get("measurements") or []):
                        if m.get("name") == "liveness_vout" and isinstance(
                                m.get("value"), (int, float)):
                            out[pid] = float(m["value"])
    return out


def cmd_reduce(a):
    corners_dir = a.corners_dir or os.path.join(HERE, "corners", a.record)
    if not os.path.isdir(corners_dir):
        print(f"e1_oppoints: no corners dir for record {a.record}: {corners_dir}",
              file=sys.stderr)
        return 2
    liveness = _liveness_by_point(corners_dir)
    rows, all_failed = [], {}
    for pt in POINTS:
        pid = point_id(pt)
        path = os.path.join(corners_dir, f"{pid}{SUFFIX}")
        if not os.path.isfile(path):
            print(f"e1_oppoints: refusing to reduce: missing export {path}",
                  file=sys.stderr)
            return 2
        try:
            check_export(path)
        except ValueError as e:
            print(f"e1_oppoints: {e}", file=sys.stderr)
            return 2
        row, failed = reduce_point(pt, path, liveness.get(pid), a.cc_f)
        rows.append(row)
        if failed:
            all_failed[pt[0]] = failed

    with open(a.out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    doc = {
        "record": a.record,
        "bench": BENCH,
        "points": [{k: v for k, v in r.items()
                    if not k.startswith("op:") and not k.startswith("check:")
                    and k != "note"} for r in rows],
        "cc_f_assumed": a.cc_f,
        "cc_f_source": "DR-0005 (w=170um l=30um cap_cmomi, ~5.5 pF)",
        "failed_checks": all_failed,
        "quantities": QUANTITIES,
    }
    with open(a.out_json, "w") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    if all_failed:
        print("e1_oppoints: FAILED CHECKS (outputs written; the record is "
              "marked incomplete):", file=sys.stderr)
        for p, fs in all_failed.items():
            print(f"e1_oppoints:   {p}: {','.join(fs)}", file=sys.stderr)
        return 3
    print(f"e1_oppoints: all {len(rows)} points reduced clean", file=sys.stderr)
    return 0


# ---- record md ----------------------------------------------------------- #
def _sci(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(v):
        return "n/a"
    return f"{v:.4e}"


def record_md(rid, sim_dir=HERE):
    """Narrative record for e1op record `rid`, derived only from committed
    files (the reduction CSV/JSON, the batch provenance, the manifest)."""
    rec_dir = os.path.join(sim_dir, "records")
    csv_path = os.path.join(rec_dir, f"{rid}.{BENCH}.csv")
    json_path = os.path.join(sim_dir, "evidence", rid, "e1op-report.json")
    with open(csv_path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(json_path) as fh:
        doc = json.load(fh)
    backend, jobs = {}, []
    bdir = os.path.join(sim_dir, "corners", rid, "_batch")
    if os.path.isfile(os.path.join(bdir, "backend.json")):
        backend = json.load(open(os.path.join(bdir, "backend.json")))
        jobs = backend.get("jobs") or []
    ngspice = runner = "unknown"
    if os.path.isfile(os.path.join(bdir, "backend.env")):
        for ln in open(os.path.join(bdir, "backend.env")):
            if ln.startswith("BATCH_NGSPICE_VERSION="):
                ngspice = ln.split("=", 1)[1].strip().strip("'")
            if ln.startswith("BATCH_RUNNER_KLT="):
                runner = ln.split("=", 1)[1].strip().strip("'")
    git_sha = rid.split("-")[2] if rid.count("-") >= 2 else "unknown"

    L = [
        "# E1 DC operating points (issue #158) -- DR-0015 experiment E1", "",
        "SCHEMATIC-LEVEL diagnostic evidence, NOT a spec pass and NOT a",
        "compensation change. DR-0015 stays **Proposed**; DR-0007 rows 3, 6,",
        "7 and 10 keep their states; nothing here is ratified, relaxed or",
        "production. This record measures the device operating points",
        "DR-0015's class-1 analysis had to infer (pass-device output",
        "resistance, EAOUT bias, divider standing current, amplifier-stage",
        "gm/gds) at the four selected points P1/P2/P5/P6, so a future",
        "compensation experiment starts from measurements.", "",
        "## Vintage and provenance", "",
        f"- Record id: `{rid}` (run at HEAD git sha `{git_sha}`, design",
        "  netlists byte-identical to the ones this worktree commits; sha256",
        "  of both netlists in the manifest below).",
        "- PDK: `ihp-sg13cmos5l` at the **current pin**",
        "  `f7bca32694fe3d58be0cc7d9df4b9f5db7161a14` (the #155 re-stamp;",
        "  `sim/pdk-cmos5l.json`). The staged model cards and OSDI binaries",
        "  are pinned by sha256 in",
        f"  `corners/{rid}/_batch/inputs.sha256.json` and",
        "  `backend.json`'s `staged_osdi_sha256`.",
        "- DR-0015's AC evidence (records `20261010-091123-a31c626`,",
        "  `20261010-101245-6df50fd`) predates #155 and #89: it is the OLD",
        "  PDK pin `607e18d4...` on the pre-#89 design. Any comparison",
        "  in this record between E1's numbers and that diagnosis is a",
        "  **cross-vintage comparison** and is labelled as such; the",
        "  same-vintage AC reference is the #155 re-run",
        "  `20261012-080951-142dac4a` (same design bytes, same pin).",
        "- The DC operating point is extracted on the flattened loop-gain",
        "  bench's circuit (loop broken at FB with a 0 V AC source; FBAMP is",
        "  a MOSFET gate, so the break draws no current), plus a",
        "  non-invasive divider replica. The break-validity and KCL checks",
        "  below verify per point that this circuit's operating point is the",
        "  closed loop's.", "",
        "## Run", "",
        f"- Engine: {ngspice}; batch fleet runner klt {runner}.",
        f"- Fleet jobs: {len(jobs)} request group(s):",
    ]
    for j in jobs:
        L.append(f"  - `{j.get('group')}`: job `{j.get('job_id')}` on "
                 f"{j.get('instance_type')} ({j.get('lifecycle')}), "
                 f"{j.get('corners')}/{j.get('requested')} corners")
    L += [
        "", "## Quantities and conventions", "",
        "Per point the export carries (CSV columns `op:*`, exact order in",
        "`e1_oppoints.py` QUANTITIES): node voltages v(vout), v(eaout),",
        "v(fb), v(fbamp), v(vref), v(en), v(ibias), v(xamp.g1), v(xamp.mz),",
        "v(xamp.n1), v(xamp.tail), v(xamp.enb), v(reptop); source currents",
        "i(vdivsense) (replica divider), i(vin) (total supply), i(vbreak)",
        "(loop break); and every MOS's operating-point ids/gm/gds (14",
        "devices), plus the pass device's cgs/cgd/cdd/vth and XMn3's",
        "cgs/cgd. Device naming: `@n.<hierarchical wrapper path>.<inner PSP",
        "device>[param]` (e.g. `@n.xamp.xminp.nsg13_hv_pmos[gm]`); the inner",
        "names come from the PDK's `sg13_hv_pmos`/`sg13_hv_nmos` subckt",
        "wrappers. Signs: this PDK's PSP103 OSDI reports ids as the",
        "magnitude-signed drain current -- positive when the device",
        "conducts, for both polarities (off devices: tiny positive",
        "leakage); i(vin) < 0 while the rail delivers; i(vdivsense) > 0",
        "into the divider; PSP cap values may be negative (charge-based),",
        "magnitudes are used. Units: V, A, S, F.", "",
        "## Results", "",
        "| point | V(vout) V | V(eaout) V | pass ids A | pass gm S | pass gds S | r_o = 1/gds | VA equiv V | I_div A | R_leg | est. f_pole,VOUT |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(
            f"| {r['point']} | {_sci(r['op:v(vout)'])} | {_sci(r['op:v(eaout)'])} "
            f"| {_sci(r['op:@n.xmpass.nsg13_hv_pmos[ids]'])} "
            f"| {_sci(r['op:@n.xmpass.nsg13_hv_pmos[gm]'])} "
            f"| {_sci(r['op:@n.xmpass.nsg13_hv_pmos[gds]'])} "
            f"| {_sci(r['derived:ro_pass_ohm'])} Ω "
            f"| {_sci(r['derived:va_equiv_pass_V'])} "
            f"| {_sci(r['op:i(vdivsense)'])} "
            f"| {_sci(r['derived:r_leg_ohm'])} Ω "
            f"| {_sci(r['derived:est_f_pole_vout_hz'])} Hz |")
    L += [
        "", "Every derived pole is an ESTIMATE, not a measured pole: the",
        "measurements are DC operating-point quantities; the pole frequencies",
        "apply `f = 1/(2πRC)` to them under the assumptions named here.",
        "`est. f_pole,VOUT` is DR-0015's class-1 mechanism estimate:",
        "`1/(2π·(r_o ∥ R_div)·(Cout + |cdd,pass|))` with r_o = 1/gds measured",
        "and R_div = 2·(v(vout)/2)/i(vdivsense) measured. It deliberately",
        "excludes unmeasured parasitics (routing, pad, ESR network at ESR>0 --",
        "not applicable here, ESR = 0) and is exact only insofar as a lumped",
        "RC approximates the output node.", "",
        "The two amplifier-side pole ESTIMATES (columns in the CSV; not",
        "repeated here) carry an additional disclosed limitation: only the",
        "pass device's and XMn3's capacitances are exported, so the G1-node",
        "estimate omits XMn2/XMinp/XRz/XMpd capacitances and every estimate",
        "omits wiring parasitics. Identifying amplifier node impedances by",
        "small-signal probing is **not** part of E1's four-run scope; it",
        "remains an unresolved follow-up.", "",
        "## Checks (per point)", "",
        "| point | finite | signs | vbreak ~ 0 | KCL at VOUT | regulation | liveness | all |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(
            f"| {r['point']} | {r['check:finite_ok']} | {r['check:signs_ok']} "
            f"| {r['check:vbreak_ok']} | {r['check:kcl_ok']} "
            f"| {r['check:regulation_ok']} | {r['check:liveness_ok']} "
            f"| {r['check:all_ok']} |")
    notes = [(r["point"], r["note"]) for r in rows if r["note"]]
    if notes:
        L += ["", "### Check failures and disclosures", ""]
        for p, note in notes:
            L.append(f"- **{p}**: {note}")
        L.append("")
    if doc.get("failed_checks"):
        L += ["Every quantity was still exported and reduced; the failed "
              "checks above block a definitive mechanism conclusion for the "
              "affected points and are reported as such.", ""]
    else:
        L += ["All checks pass at every point: every declared quantity is "
              "present, finite and sign-consistent; the break draws no "
              "current; KCL at VOUT closes; VOUT is in regulation; the "
              "fleet's liveness measurement matches the export.", ""]
    L += [
        "## What this record does not claim", "",
        "- No spec row, threshold, gate, record or verdict changed; DR-0015",
        "  stays Proposed; no production schematic/layout change is made or",
        "  proposed for ratification here.",
        "- No directly measured pole, no measured amplifier node impedance",
        "  (small-signal probing is out of E1's scope -- unresolved",
        "  follow-up), no post-change margin prediction.",
        "- No claim about points other than P1/P2/P5/P6; four sampled",
        "  operating points, no monotonicity or window claim.",
        "- `sim/` stays append-only: nothing under `records/`, `corners/`,",
        "  `evidence/` or `netlist-snapshots/` was edited or deleted.", "",
        "## Files", "",
        f"- Reduction: `records/{rid}.{BENCH}.csv` (one row per point; the",
        "  exact column contract is `e1_oppoints.py` CSV_FIELDS),",
        f"  `evidence/{rid}/e1op-report.json`.",
        f"- Raw exports + fleet provenance: `corners/{rid}/` (per-point log",
        f"  and `_dc.csv`; `_batch/` carries the request, the deck,",
        "  `points.tsv`, `inputs.sha256.json`, `backend.json`).",
        f"- Netlists: `netlist-snapshots/{rid}/` (one generated deck per",
        "  point; sha256 in the manifest).",
        f"- Manifest: `records/{rid}.{BENCH}.manifest.tsv`.",
        "",
        "<!-- regeneration: python3 sim/ldo-cmos5l-pvt-sweep/e1_oppoints.py",
        f"     reduce --record {rid} --out-csv <tmp> --out-json <tmp>;",
        f"     e1_oppoints.py record-md --record {rid};",
        f"     e1_oppoints.py check --record {rid} byte-compares. -->", "",
    ]
    return "\n".join(L) + "\n"


def cmd_record_md(a):
    out = os.path.join(HERE, "records", f"{a.record}.{BENCH}.md")
    with open(out, "w") as fh:
        fh.write(record_md(a.record))
    print(f"e1_oppoints: wrote {out}", file=sys.stderr)
    return 0


def cmd_check(a):
    """CI: regenerate the CSV, JSON and record md from the committed exports
    and byte-compare. Writes only into a throwaway temp dir."""
    rid = a.record
    rec_csv = os.path.join(HERE, "records", f"{rid}.{BENCH}.csv")
    rec_json = os.path.join(HERE, "evidence", rid, "e1op-report.json")
    rec_md = os.path.join(HERE, "records", f"{rid}.{BENCH}.md")
    rc = 0
    with tempfile.TemporaryDirectory() as tmp:
        a2 = argparse.Namespace(record=rid, corners_dir=None,
                                out_csv=os.path.join(tmp, "r.csv"),
                                out_json=os.path.join(tmp, "r.json"),
                                cc_f=CC_F_NOMINAL)
        rc = cmd_reduce(a2)
        for got, want, what in ((os.path.join(tmp, "r.csv"), rec_csv, "csv"),
                                (os.path.join(tmp, "r.json"), rec_json, "json")):
            if open(got).read() != open(want).read():
                print(f"e1_oppoints: check: regenerated {what} differs from "
                      f"{want}", file=sys.stderr)
                rc = rc or 1
        if record_md(rid) != open(rec_md).read():
            print(f"e1_oppoints: check: regenerated record md differs from "
                  f"{rec_md}", file=sys.stderr)
            rc = rc or 1
    if rc in (0, 3) and rc == 0:
        print(f"e1_oppoints: check: {rid} reproduces byte-for-byte", file=sys.stderr)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tokens")
    ce = sub.add_parser("check-export")
    ce.add_argument("csv")
    r = sub.add_parser("reduce")
    r.add_argument("--record", required=True)
    r.add_argument("--corners-dir", default=None)
    r.add_argument("--out-csv", required=True)
    r.add_argument("--out-json", required=True)
    r.add_argument("--cc-f", type=float, default=CC_F_NOMINAL)
    m = sub.add_parser("record-md")
    m.add_argument("--record", required=True)
    c = sub.add_parser("check")
    c.add_argument("--record", required=True)
    a = ap.parse_args()
    if a.cmd == "tokens":
        for t in QUANTITIES:
            print(t)
        return 0
    if a.cmd == "check-export":
        try:
            ncols = check_export(a.csv)
        except ValueError as e:
            print(f"e1_oppoints: {e}", file=sys.stderr)
            return 1
        print(f"e1_oppoints: {a.csv}: OK ({N_ROWS} rows x {ncols} cols)")
        return 0
    if a.cmd == "reduce":
        return cmd_reduce(a)
    if a.cmd == "record-md":
        return cmd_record_md(a)
    if a.cmd == "check":
        return cmd_check(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())
