#!/usr/bin/env python3
"""E3 Cc-width probe at P3 (issue #219): contract module + record writer.

DR-0015's class-2 mechanism attributes the heavy-load misses (P3: ff / -40 C
/ res_wcs, 50 mA, 0.33 uF, 0 mohm) to a third pole inside the loop bandwidth
but leaves the attribution between the compensation network and the EAOUT
gate node unquantified -- "E3 separates the two". Experiment E3 is three
loop-gain runs at P3 with the compensation capacitor Cc at 0.5x / 1x / 2x of
its committed width, made by a testbench-local override (a substituted COPY
of the design netlist; the committed netlists stay byte-unchanged), run
through the same batch-fleet path as the dynamic campaign (run_ccprobe.sh).

This module owns the experiment's Python-side contract, mirroring
run_sweep.sh's Cc machinery the same way dynamic_doe.render_cout_esr mirrors
esr_netlist_parts -- kept in Python so it is unit-tested (test_ccprobe.py):

  * the width table CC_WIDTHS / CC_NOMINAL_W -- the test cross-checks the
    table against run_sweep.sh's own `declare -A CC_WIDTHS` literal and
    against the committed design netlist's XCc line, so the three copies of
    the contract (this module, run_sweep.sh, the design) cannot drift;
  * subst_cc_width() -- the XCc-line substitution contract. It replaces ONLY
    the w= token on XCc's line (l is held fixed at CC_L) and RAISES
    CcSubstitutionError when the deck text has drifted (the Python
    equivalent of run_sweep.sh subst_cc_width's exit-4 FATAL), never
    returning a silently nominal netlist -- "an override that does not reach
    the deck" fails loudly (issue #219 acceptance criterion 6's negative
    control);
  * point_id() -- campaign-convention ids suffixed _cc<label>, so the three
    runs cannot collide (dynamic_doe.py's plan has no Cc axis, which is why
    this experiment has its own driver instead of a --extra-points file);
  * the committed P3 baselines acceptance criterion 4 compares against,
    pinned by their trace sha256 prefixes: DR-0015's own P3 row (record
    20261010-091123-a31c626, the pre-#89 / pre-#155 vintage DR-0015 was
    written at) and the same-vintage committed trace (base-matrix row of
    record 20261012-074813-c94873ba: the #89 design bytes and the #155
    PDK re-stamp this repo's tree carries today) the 1x run must reproduce
    to solver/fleet precision;

and the offline reduction: per-point loopgain_metrics + classify_margins
(both from ac_metrics.py -- the committed records' own reading, not a new
one), the 1x-vs-baseline comparisons with their stated causes, the
crossing-count equality premise the f_ug-vs-Cc slope needs, and the
log-log slope itself.

Subcommands:
    widths                        print the width table (label, w, @@CC_W@@ text)
    subst IN OUT LABEL            write the Cc-substituted copy of netlist IN
                                  to OUT (exit 4 = the substitution did not
                                  reach the deck: the FATAL, not a no-op)
    reduce --record RID --out-csv P --out-json P [--corners-dir DIR]
    record-md --record RID
    check --record RID            regenerate + byte-compare (CI)

Error discipline: a missing export, a nonfinite metric or a failed
comparison is never silently dropped. reduce writes its outputs either way
and exits 3 when a check failed, so the campaign can publish an explicitly
incomplete record; missing inputs refuse to reduce at all (exit 2). The
like-for-like 1x-vs-same-vintage gate is deliberately a hard check (the two
runs share design bytes, PDK pin and analysis line, so a disagreement means
THIS campaign's deck is wrong) while the 1x-vs-DR-0015-row difference is
reported with its vintage cause and never gated -- a difference there is
the expected, explainable outcome of the vintage change.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ac_metrics as am  # noqa: E402

BENCH = "loopgain_ccprobe"
SUFFIX = "_ac.csv"

# DR-0015's P3 (its "six points" table, class 2): the heavy-load,
# small-Cout point the record's third-pole hypothesis is about.
P3 = {"corner": "ff", "res": "wcs", "temp_c": -40,
      "load_ua": 50000, "cout_nf": 330, "esr_mohm": 0}

# ---- the Cc contract (mirrors run_sweep.sh's Cc block; unit-tested) ------- #
# Cc's designed value at the committed compensation (DR-0005: w=170um l=30um
# cap_cmomi; run_sweep.sh: #20 drew 30e-6, #25 raised w to 100e-6, #35 to
# 170e-6). The width IS the experiment axis: cornerCAP.lib has no corner or
# mismatch model for cap_cmomi (sim/pdk-cmos5l.json
# "mom_cap_no_corner_or_mismatch_model"), so a PVT corner sweep over Cc is a
# no-op by construction and a VALUE (width) sweep is the only real one.
CC_L = "30e-6"
CC_NOMINAL_W = "170e-6"
CC_WIDTHS = {"0.5x": "85e-6", "1x": "170e-6", "2x": "340e-6"}
CC_LABELS = ("0.5x", "1x", "2x")
# The exact XCc line prefix run_sweep.sh's sed and subst_cc_width() below
# both expect in the design netlist (ldo_core_cmos5l.spice, inside the
# ldo_erramp_cmos5l subckt; the erramp file holds its own copy but is not
# the included file). Anything else -- a renamed node, a moved token, a
# second occurrence -- must fail loudly, not substitute nothing.
XCc_TOKEN = f"XCc OUT MZ cap_cmomi w={CC_NOMINAL_W} l={CC_L}"

DESIGN_NETLIST = os.path.join(HERE, "..", "..", "design", "sg13cmos5l",
                              "netlist", "ldo_core_cmos5l.spice")


class CcSubstitutionError(RuntimeError):
    """The XCc line text drifted from what this contract expects: an
    override applied to it would not reach the deck."""


def cc_w(label):
    """The substituted width [ngspice number syntax] for a table label."""
    try:
        return CC_WIDTHS[label]
    except KeyError:
        raise CcSubstitutionError(
            f"unknown Cc width label {label!r} (have {sorted(CC_WIDTHS)})")


def cc_factor(label):
    """Cc's capacitance relative to nominal for a label (l fixed, cap area
    proportional to w)."""
    return float(cc_w(label)) / float(CC_NOMINAL_W)


def cc_w_desc(label):
    """The @@CC_W@@ description text the deck header carries (run_sweep.sh's
    own ccsens format: the ngspice width token, then the factor)."""
    return f"{cc_w(label)} ({label} of nominal {CC_NOMINAL_W})"


def subst_cc_width(text, label):
    """The Cc-substituted design netlist text for `label`.

    Replaces ONLY the w= token of XCc's line (exactly one occurrence of
    XCc_TOKEN expected), leaving every other device byte-identical. The 1x
    label substitutes the nominal width, i.e. returns the input unchanged
    (byte-identical copy -- same as run_sweep.sh's subst_cc_width). Any
    drift (token moved, node renamed, line absent, more than one occurrence,
    nominal width changed under us) raises CcSubstitutionError instead of
    silently substituting nothing.
    """
    w = cc_w(label)
    new_token = f"XCc OUT MZ cap_cmomi w={w} l={CC_L}"
    n = text.count(XCc_TOKEN)
    if n == 0:
        raise CcSubstitutionError(
            f"Cc width substitution to {w} did not find the expected XCc line "
            f"prefix ({XCc_TOKEN!r}); the deck text has drifted and an "
            "override applied to it would not reach the deck")
    if n > 1:
        raise CcSubstitutionError(
            f"expected exactly one XCc compensation-cap line, found {n}")
    out = text.replace(XCc_TOKEN, new_token)
    if w != CC_NOMINAL_W and out == text:
        raise CcSubstitutionError(
            f"Cc width substitution to {w} did not change the netlist")
    return out


def point_id(label):
    """Campaign-convention id suffixed with the Cc label, so the three runs
    cannot collide (and cannot be confused with dynamic-campaign points).
    The bench prefix carries the loopgain_ stem on purpose: batch_backend.py
    (hash-pinned) identifies a point's bench by its id prefix whitelist, and
    this campaign IS the loop-gain bench -- same pattern E2's loopgain_ctl_*
    points used."""
    cc_w(label)  # unknown labels refuse here too
    return (f"{BENCH}_dyn_{P3['corner']}_-{abs(P3['temp_c'])}c_r{P3['res']}_"
            f"i{P3['load_ua']}ua_c{P3['cout_nf']}nf_e{P3['esr_mohm']}mohm"
            f"_cc{label}")


# ---- committed P3 baselines (AC 4) ---------------------------------------- #
# Quoted/committed evidence, NOT re-measured by this module: reduce reads the
# committed traces live and verifies each against the pinned sha256 prefix
# below, so a moved or edited baseline fails the comparison loudly instead of
# silently comparing against different bytes. a31c626 is DR-0015's own P3 row
# (its table pins the same cc6fae43a41b1b4f prefix); c94873ba is the base
# matrix of the #155 re-run -- the CURRENT design bytes (post-#89) and the
# CURRENT PDK pin (f7bca326, the #155 re-stamp), at the same analysis line
# (ac dec 20 1 100meg) and fleet runner this campaign uses.
BASELINE_DR0015 = {
    "record": "20261010-091123-a31c626",
    "vintage": "pre-#89 design, pre-#155 PDK pin 607e18d4 (DR-0015's own evidence)",
    "trace": "corners/20261010-091123-a31c626/"
             "loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_ac.csv",
    "trace_sha256_16": "cc6fae43a41b1b4f",
}
BASELINE_SAME_VINTAGE = {
    "record": "20261012-074813-c94873ba",
    "vintage": "post-#89 design (today's committed bytes), PDK pin f7bca326 "
               "(the #155 re-stamp)",
    "trace": "corners/20261012-074813-c94873ba/"
             "loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_ac.csv",
    "trace_sha256_16": "f9e9261aea56bd71",
}
# Like-for-like gate for the 1x run against the same-vintage trace: same
# design bytes, same PDK pin, same analysis line, so the traces must agree to
# solver/fleet precision. run_loopgain2.sh's ctl-vs-baseline check uses the
# same 1 dB whole-trace bound for exactly this class of comparison; the
# scalar bounds are wide against solver precision and narrow against any
# wrong-deck failure mode (a wrong Cc width moves PM by tens of degrees --
# that is the experiment).
LIKE_FOR_LIKE_TRACE_MAX_DB = 1.0
LIKE_FOR_LIKE_PM_MAX_DEG = 1.0
LIKE_FOR_LIKE_GM_MAX_DB = 1.0
LIKE_FOR_LIKE_FUG_MAX_REL = 0.02

METRIC_KEYS = ("unity_gain_freq_hz", "phase_margin_deg",
               "phase_margin_worst_deg", "gain_margin_db", "n_0db_crossings")


def _sha256_16(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def _trace_db_series(path):
    """(freqs, dbs) of a loop-gain wrdata trace; None if unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [ln.split() for ln in fh if ln.strip()]
    except OSError:
        return None
    if any(len(r) != 4 for r in rows):
        return None
    return [float(r[0]) for r in rows], [float(r[1]) for r in rows]


def _max_abs_db_diff(path_a, path_b):
    """max |dB difference| over the common frequency axis of two traces
    (None when either is unreadable or the axes differ)."""
    a, b = _trace_db_series(path_a), _trace_db_series(path_b)
    if not a or not b or len(a[0]) != len(b[0]):
        return None
    if any(not math.isclose(x, y, rel_tol=1e-9) for x, y in zip(a[0], b[0])):
        return None
    return max(abs(da - db) for da, db in zip(a[1], b[1]))


def _read_baseline(which, sim_dir=HERE):
    """Read + hash-verify one committed baseline trace; returns its metrics
    dict (with the record/vintage/hash metadata merged in) or raises."""
    meta = dict(BASELINE_DR0015 if which == "dr0015" else BASELINE_SAME_VINTAGE)
    path = os.path.join(sim_dir, meta["trace"])
    if not os.path.isfile(path):
        raise RuntimeError(f"committed baseline trace missing: {path}")
    got = _sha256_16(path)
    if got != meta["trace_sha256_16"]:
        raise RuntimeError(
            f"committed baseline trace {path} sha256/16 {got} != pinned "
            f"{meta['trace_sha256_16']} -- the baseline moved under this record")
    m = am.loopgain_metrics(path)
    if m is None:
        raise RuntimeError(f"committed baseline trace unparseable: {path}")
    m.update({"record": meta["record"], "vintage": meta["vintage"],
              "trace_sha256_16": meta["trace_sha256_16"],
              "trace_path_abs": path})
    return m


def _delta(ours, base, key):
    """Signed difference ours - base for one metric (None when either side
    lacks it)."""
    a, b = ours.get(key), base.get(key)
    if a is None or b is None:
        return None
    return a - b


def like_for_like_check(row, base):
    """The hard 1x-vs-same-vintage gate. Returns (ok, reasons, details).
    `base` carries the baseline's metrics plus its trace_path_abs (set by
    _read_baseline; a test can point it at a fixture)."""
    details, reasons = {}, []
    d = _max_abs_db_diff(row["trace_path"], base.get("trace_path_abs"))
    details["max_abs_db_diff"] = d
    if d is None:
        reasons.append("trace_axis_differs_or_unreadable")
    elif d > LIKE_FOR_LIKE_TRACE_MAX_DB:
        reasons.append(f"trace_diff_{d:.3g}dB_gt_{LIKE_FOR_LIKE_TRACE_MAX_DB:g}dB")
    for key, bound, name in (
            ("phase_margin_deg", LIKE_FOR_LIKE_PM_MAX_DEG, "pm_deg"),
            ("gain_margin_db", LIKE_FOR_LIKE_GM_MAX_DB, "gm_db")):
        dv = _delta(row, base, key)
        details[f"{name}_delta"] = dv
        if dv is None:
            reasons.append(f"{name}_missing")
        elif abs(dv) > bound:
            reasons.append(f"{name}_delta_{dv:.3g}_gt_{bound:g}")
    fu, fb = row.get("unity_gain_freq_hz"), base.get("unity_gain_freq_hz")
    rel = abs(fu - fb) / fb if (fu and fb) else None
    details["f_ug_rel_delta"] = rel
    if rel is None:
        reasons.append("f_ug_missing")
    elif rel > LIKE_FOR_LIKE_FUG_MAX_REL:
        reasons.append(f"f_ug_rel_delta_{rel:.3g}_gt_{LIKE_FOR_LIKE_FUG_MAX_REL:g}")
    if row.get("n_0db_crossings") != base.get("n_0db_crossings"):
        reasons.append("crossing_count_differs")
    return (not reasons), reasons, details


def slope(rows):
    """The log-log f_ug-vs-Cc slope across the three labels, with the
    branch premise AC 5 needs.

    Least-squares fit of ln(f_ug) against ln(Cc/Cc_nom). Returns a dict:
    slope (None when fewer than two points have a first crossing),
    per-label factors, and single_branch -- True only when all three runs
    have the SAME n_0db_crossings (unity_gain_freq_hz is the FIRST crossing;
    an unequal count means the slope compares different branches, i.e. the
    probe does not discriminate on this reading).
    """
    xs, ys, labels = [], [], []
    counts = {}
    for r in rows:
        lab = r["cc_label"]
        counts[lab] = r.get("n_0db_crossings")
        f = r.get("unity_gain_freq_hz")
        if f:
            labels.append(lab)
            xs.append(math.log(cc_factor(lab)))
            ys.append(math.log(f))
    single = len(set(counts.values())) == 1 and len(counts) == len(CC_LABELS)
    out = {"single_branch": single, "n_0db_crossings": counts,
           "labels_with_crossing": labels}
    if len(xs) >= 2:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        out["slope"] = sxy / sxx if sxx else None
    else:
        out["slope"] = None
    return out


# ---- reduce --------------------------------------------------------------- #
def reduce_point(label, trace_path):
    """One point's metrics + DR-0014 classification row (the committed
    records' own reading via ac_metrics.py -- never hand-classified)."""
    m = am.loopgain_metrics(trace_path)
    c = am.classify_margins(trace_path)
    if m is None or c is None:
        raise RuntimeError(f"{trace_path}: unparseable loop-gain export")
    row = {
        "point_id": point_id(label),
        "cc_label": label,
        "cc_w": cc_w(label),
        "cc_factor": cc_factor(label),
        "trace_path": trace_path,
    }
    row.update({k: m.get(k) for k in METRIC_KEYS})
    row["dc_gain_db"] = m.get("dc_gain_db")
    row["dr0014_pm_verdict"] = c["pm"]["verdict"]
    row["dr0014_pm_reasons"] = ",".join(c["pm"]["reasons"]) or "-"
    row["dr0014_pm_value_deg"] = c["pm"]["value_deg"]
    row["dr0014_gm_verdict"] = c["gm"]["verdict"]
    row["dr0014_gm_reasons"] = ",".join(c["gm"]["reasons"]) or "-"
    row["dr0014_gm_value_db"] = c["gm"]["value_db"]
    row["dr0014_nyquist_class"] = c["nyquist"]["class"]
    row["dr0014_ceiling_bounded"] = c["ceiling"]["bounded"]
    return row


CSV_FIELDS = ["point_id", "cc_label", "cc_w", "cc_factor", "trace_path",
              "dc_gain_db"] + list(METRIC_KEYS) + [
    "dr0014_pm_verdict", "dr0014_pm_reasons", "dr0014_pm_value_deg",
    "dr0014_gm_verdict", "dr0014_gm_reasons", "dr0014_gm_value_db",
    "dr0014_nyquist_class", "dr0014_ceiling_bounded",
    "lfl_ok", "lfl_reasons", "lfl_max_abs_db_diff",
    "vs_samev_f_ug_delta_hz", "vs_samev_pm_delta_deg", "vs_samev_gm_delta_db",
    "vs_dr0015_f_ug_delta_hz", "vs_dr0015_pm_delta_deg", "vs_dr0015_gm_delta_db",
]


def cmd_reduce(a):
    corners_dir = a.corners_dir or os.path.join(HERE, "corners", a.record)
    if not os.path.isdir(corners_dir):
        print(f"ccprobe: no corners dir for record {a.record}: {corners_dir}",
              file=sys.stderr)
        return 2
    rows, failed = [], {}
    for label in CC_LABELS:
        pid = point_id(label)
        path = os.path.join(corners_dir, f"{pid}{SUFFIX}")
        if not os.path.isfile(path):
            print(f"ccprobe: refusing to reduce: missing export {path}",
                  file=sys.stderr)
            return 2
        rows.append(reduce_point(label, path))

    # AC 4: the 1x run against BOTH committed baselines. The same-vintage
    # comparison is the hard like-for-like gate; the DR-0015-row deltas are
    # reported with their vintage cause (a difference there is expected).
    one_x = next(r for r in rows if r["cc_label"] == "1x")
    try:
        base_lfl = _read_baseline("same_vintage")
    except RuntimeError as e:
        print(f"ccprobe: {e}", file=sys.stderr)
        return 2
    ok, reasons, details = like_for_like_check(one_x, base_lfl)
    one_x["lfl_ok"] = ok
    one_x["lfl_reasons"] = ",".join(reasons) or "-"
    one_x["lfl_max_abs_db_diff"] = details.get("max_abs_db_diff")
    one_x["vs_samev_f_ug_delta_hz"] = _delta(one_x, base_lfl, "unity_gain_freq_hz")
    one_x["vs_samev_pm_delta_deg"] = _delta(one_x, base_lfl, "phase_margin_deg")
    one_x["vs_samev_gm_delta_db"] = _delta(one_x, base_lfl, "gain_margin_db")
    if not ok:
        failed["like_for_like_vs_" + base_lfl["record"]] = reasons
    try:
        base_old = _read_baseline("dr0015")
    except RuntimeError as e:
        print(f"ccprobe: {e}", file=sys.stderr)
        return 2
    one_x["vs_dr0015_f_ug_delta_hz"] = _delta(one_x, base_old, "unity_gain_freq_hz")
    one_x["vs_dr0015_pm_delta_deg"] = _delta(one_x, base_old, "phase_margin_deg")
    one_x["vs_dr0015_gm_delta_db"] = _delta(one_x, base_old, "gain_margin_db")

    # AC 5 premise + slope. The slope itself is never a check: whatever it
    # reads, the record states which case held (single-branch or not).
    sl = slope(rows)
    if not sl["single_branch"]:
        failed["single_branch_premise"] = (
            f"n_0db_crossings differ across labels: {sl['n_0db_crossings']}")

    with open(a.out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    doc = {
        "record": a.record,
        "bench": BENCH,
        "point": {k: P3[k] for k in sorted(P3)},
        "points": [{k: v for k, v in r.items() if k != "trace_path"}
                   for r in rows],
        "slope": sl,
        "baselines": {
            "dr0015_row": {k: base_old[k] for k in METRIC_KEYS},
            "dr0015_record": base_old["record"],
            "dr0015_trace_sha256_16": base_old["trace_sha256_16"],
            "same_vintage_record": base_lfl["record"],
            "same_vintage_trace_sha256_16": base_lfl["trace_sha256_16"],
            "like_for_like_bounds": {
                "trace_max_db": LIKE_FOR_LIKE_TRACE_MAX_DB,
                "pm_max_deg": LIKE_FOR_LIKE_PM_MAX_DEG,
                "gm_max_db": LIKE_FOR_LIKE_GM_MAX_DB,
                "f_ug_max_rel": LIKE_FOR_LIKE_FUG_MAX_REL,
            },
        },
        "failed_checks": failed,
    }
    with open(a.out_json, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    if failed:
        print("ccprobe: FAILED CHECKS (outputs written; the record is "
              "marked incomplete):", file=sys.stderr)
        for k, v in failed.items():
            print(f"ccprobe:   {k}: {v}", file=sys.stderr)
        return 3
    sl_txt = "n/a" if sl["slope"] is None else f"{sl['slope']:.4g}"
    print(f"ccprobe: all {len(rows)} points reduced clean; "
          f"log-log slope {sl_txt}, single-branch {sl['single_branch']}",
          file=sys.stderr)
    return 0


# ---- record md ------------------------------------------------------------ #
def _fmt(x, unit=""):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if not math.isfinite(x):
            return "n/a"
        return f"{x:.6g}{unit}"
    return str(x)


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.4g}%"


def _pdk_provenance(rid, sim_dir=HERE):
    manifest_path = os.path.join(sim_dir, "records", f"{rid}.{BENCH}.manifest.tsv")
    if not os.path.isfile(manifest_path):
        return ""
    with open(manifest_path, newline="") as fh:
        return "; ".join(sorted({r.get("pdk", "") for r in
                                 csv.DictReader(fh, delimiter="\t")
                                 if r.get("pdk")}))


def _runner_provenance(rid, sim_dir=HERE):
    bdir = os.path.join(sim_dir, "corners", rid, "_batch")
    ngspice = runner = jobs = "unknown"
    if os.path.isfile(os.path.join(bdir, "backend.env")):
        env = {}
        for ln in open(os.path.join(bdir, "backend.env")):
            if "=" in ln:
                k, v = ln.split("=", 1)
                env[k] = v.strip().strip("'")
        ngspice = env.get("BATCH_NGSPICE_VERSION", ngspice)
        runner = env.get("BATCH_RUNNER_KLT", runner)
        jobs = env.get("BATCH_JOB_COUNT", jobs)
    return ngspice, runner, jobs


def record_md(rid, sim_dir=HERE):
    """Narrative record for ccprobe record `rid`, derived only from committed
    files (the reduction CSV/JSON, the batch provenance, the manifest)."""
    rec_dir = os.path.join(sim_dir, "records")
    with open(os.path.join(rec_dir, f"{rid}.{BENCH}.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("cc_factor", "dc_gain_db", "unity_gain_freq_hz",
                  "phase_margin_deg", "phase_margin_worst_deg",
                  "gain_margin_db", "dr0014_pm_value_deg",
                  "dr0014_gm_value_db", "lfl_max_abs_db_diff",
                  "vs_samev_f_ug_delta_hz", "vs_samev_pm_delta_deg",
                  "vs_samev_gm_delta_db",
                  "vs_dr0015_f_ug_delta_hz", "vs_dr0015_pm_delta_deg",
                  "vs_dr0015_gm_delta_db"):
            if r.get(k) not in (None, ""):
                r[k] = float(r[k])
        if r.get("n_0db_crossings") not in (None, ""):
            r["n_0db_crossings"] = int(float(r["n_0db_crossings"]))
        for k in ("lfl_ok", "dr0014_ceiling_bounded"):
            if r.get(k) not in (None, ""):
                r[k] = r[k] == "True"
    with open(os.path.join(sim_dir, "evidence", rid, "ccprobe-report.json")) as fh:
        doc = json.load(fh)
    sl = doc["slope"]
    failed = doc["failed_checks"]
    ngspice, runner, jobs = _runner_provenance(rid, sim_dir)
    pdk = _pdk_provenance(rid, sim_dir)
    git_sha = rid.split("-")[2] if rid.count("-") >= 2 else "unknown"
    one_x = next(r for r in rows if r["cc_label"] == "1x")
    base = doc["baselines"]
    bounds = base["like_for_like_bounds"]

    lines = [
        "# E3 Cc-width probe at P3 (issue #219) -- DR-0015 experiment E3", "",
        "SCHEMATIC-LEVEL diagnostic evidence, NOT a spec pass and NOT a",
        "compensation change. DR-0015 stays **Proposed**; DR-0007 rows 3, 6,",
        "7 and 10 keep their states; DR-0014's rules are unchanged; nothing",
        "here is ratified, relaxed or production. Three loop-gain runs at",
        "DR-0015's P3 (ff / -40 C / res_wcs, 50 mA, 0.33 uF, 0 mohm) with the",
        "compensation capacitor Cc at 0.5x / 1x / 2x of its committed width,",
        "so the record's unquantified third-pole attribution (compensation",
        "network vs EAOUT gate node) gets a measured basis. The override is a",
        "testbench-local copy of the design netlist with only XCc's w= token",
        "changed; the committed netlists under `design/sg13cmos5l/netlist/`",
        "are byte-unchanged (the 1x copy is byte-identical to them; the deck",
        "snapshots and the manifest pin every copy's sha256).", "",
        "## Vintage and provenance", "",
        f"- Record id: `{rid}` (run at HEAD git sha `{git_sha}`; the design",
        "  netlist sha256 is staged in",
        f"  `corners/{rid}/_batch/*/inputs.sha256.json`; the manifest below",
        "  pins the generated deck snapshots and the three Cc-substituted",
        "  netlist copies).",
        f"- Engine: ngspice {ngspice}; batch fleet runner klt {runner};",
        f" {jobs} fleet job group(s) (the three decks differ in their",
        "  `.include`d design-netlist copy, so they cannot share one request",
        "  body).",
    ]
    if pdk:
        lines += [
            "- PDK install that actually ran (the manifest's `pdk` column):",
            f" `{pdk}`. `run_ccprobe.sh` reads it from the resolved install",
            "  at run time and refuses to run off-pin.",
        ]
    lines += [
        "- Baselines pinned by trace sha256/16 (verified live by the",
        "  reduction; a moved or edited baseline trace fails loudly):",
        f"  - DR-0015's own P3 row: record `{base['dr0015_record']}`, trace",
        f"    `{base['dr0015_trace_sha256_16']}` -- the pre-#89 / pre-#155",
        "    vintage DR-0015 was written at.",
        f"  - Same-vintage reference: record `{base['same_vintage_record']}`,",
        f"    trace `{base['same_vintage_trace_sha256_16']}` -- today's",
        "    committed design bytes (post-#89) and PDK pin, at the same",
        "    analysis line (ac dec 20 1 100meg) this campaign uses.",
        "",
        "## Results",
        "",
        "Per Cc value (unity-gain frequency is the FIRST 0 dB crossing --",
        "`ac_metrics.py loopgain_metrics`, the committed records' own",
        "extractor; margins are classified by the UNCHANGED DR-0014 rules via",
        "`ac_metrics.classify_margins`, never hand-read):",
        "",
        "| Cc | w [m] | f_ug first 0 dB [Hz] | PM first [deg] | PM worst [deg] "
        "| 0 dB crossings | GM [dB] | DR-0014 PM | DR-0014 GM |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['cc_label']} | {r['cc_w']} | {_fmt(r['unity_gain_freq_hz'])} "
            f"| {_fmt(r['phase_margin_deg'])} "
            f"| {_fmt(r['phase_margin_worst_deg'])} "
            f"| {r['n_0db_crossings']} | {_fmt(r['gain_margin_db'])} "
            f"| {r['dr0014_pm_verdict']} ({r['dr0014_pm_reasons']}) "
            f"| {r['dr0014_gm_verdict']} ({r['dr0014_gm_reasons']}) |")
    lines += [
        "",
        "The Cc width is the value axis because cornerCAP.lib gives",
        "cap_cmomi no corner or mismatch model (sim/pdk-cmos5l.json",
        "`mom_cap_no_corner_or_mismatch_model`): a PVT corner sweep over Cc",
        "would be a no-op by construction, so this probe scales the drawn",
        "width instead (capacitance proportional to w at fixed l=30 um),",
        "DR-0005's own sensitivity levels {0.5x, 1x, 2x}.",
        "",
        "## The 1x run against the committed P3 result (AC 4)",
        "",
        f"- Against the SAME-VINTAGE committed trace (`{base['same_vintage_record']}`:",
        "  same design bytes, same PDK pin, same analysis line): like-for-like",
        f" gate {'PASSED' if one_x['lfl_ok'] else 'FAILED'} -- max |dB diff| over the",
        f" whole axis {_fmt(one_x['lfl_max_abs_db_diff'], ' dB')} (bound "
        f"{bounds['trace_max_db']:g} dB); scalar deltas df_ug "
        f"{_fmt(one_x['vs_samev_f_ug_delta_hz'], ' Hz')} "
        f"({_pct(_safe_rel(one_x['vs_samev_f_ug_delta_hz'], one_x['unity_gain_freq_hz']))}), "
        f"dPM {_fmt(one_x['vs_samev_pm_delta_deg'], ' deg')}, dGM "
        f"{_fmt(one_x['vs_samev_gm_delta_db'], ' dB')} (bounds dPM <= "
        f"{bounds['pm_max_deg']:g} deg, dGM <= {bounds['gm_max_db']:g} dB, "
        f"df_ug <= {_pct(bounds['f_ug_max_rel'])}, crossing count equal).",
        "  This is the gate that isolates THIS campaign's bench from every",
        "  other explanation: the two runs share design bytes, PDK pin and",
        "  analysis line, so a disagreement here would mean the deck is",
        "  wrong, and the reduction exits 3 on it.",
        f"- Against DR-0015's own committed P3 row (`{base['dr0015_record']}`:",
        "  the vintage DR-0015 was written at): df_ug "
        f"{_fmt(one_x['vs_dr0015_f_ug_delta_hz'], ' Hz')} "
        f"({_pct(_safe_rel(one_x['vs_dr0015_f_ug_delta_hz'], one_x['unity_gain_freq_hz']))} "
        f"of f_ug), dPM {_fmt(one_x['vs_dr0015_pm_delta_deg'], ' deg')}, dGM "
        f"{_fmt(one_x['vs_dr0015_gm_delta_db'], ' dB')}. Any difference here",
        "  is attributable to the VINTAGE CHANGE between the two runs --",
        "  #89's G1 disable pull-down devices in the amplifier and the #155",
        "  PDK re-stamp -- not to this campaign's bench: the two runs do NOT",
        "  share design bytes or PDK pin, and the like-for-like gate above is",
        "  what pins the bench down against the bytes this repo commits",
        "  today.",
        "",
        "## f_ug vs Cc: the slope and what it can say (AC 5)",
        "",
    ]
    if sl["single_branch"]:
        branch = ("All three runs have the SAME number of 0 dB crossings, so "
                  "every f_ug is the same branch's crossing and the slope is "
                  "a single-branch measurement.")
    else:
        branch = (f"The 0 dB crossing counts DIFFER across the three Cc values "
                  f"({sl['n_0db_crossings']}): unity_gain_freq_hz is the FIRST "
                  "crossing, so a slope would compare different branches. On "
                  "this reading the probe does NOT discriminate between the "
                  "two pole attributions -- exactly the honest outcome AC 5 "
                  "permits; the per-point traces still stand as measured "
                  "evidence.")
    lines.append(branch)
    lines.append("")
    if sl["slope"] is not None and sl["single_branch"]:
        lines += [
            f"Least-squares log-log slope of f_ug against Cc/Cc_nom over the "
            f"three labels: **{sl['slope']:.4g}** (i.e. f_ug proportional to "
            f"Cc^-{abs(sl['slope']):.4g}).",
            "",
            "DR-0015's own framing (its class-2 section) names the two "
            "limiting readings: f_ug proportional to Cc^-1 would point at a "
            "pole set by the compensation network itself (a Cc-side pole "
            "moving with the cap), while f_ug insensitive to Cc (slope near "
            "0) would point at a pole fixed by a large node capacitance "
            "independent of Cc -- the fixed-gate-side reading. Intermediate "
            "exponents mean the crossover sits between those idealisations; "
            "the attribution call is made in the DR-0015 addendum, not here.",
            "",
        ]
    elif sl["slope"] is not None:
        lines += [
            f"Least-squares log-log slope over the three labels: "
            f"{sl['slope']:.4g} -- but the branch premise above fails, so "
            "this number does NOT discriminate the two pole attributions.",
            "",
        ]
    else:
        lines += [
            "No slope: fewer than two runs produced a first 0 dB crossing.",
            "",
        ]
    lines += [
        "## Checks",
        "",
    ]
    if failed:
        lines += [
            "FAILED CHECKS (the record is INCOMPLETE; see the reduction JSON's",
            " failed_checks):",
            "",
        ]
        for k in sorted(failed):
            lines.append(f"- {k}: {failed[k]}")
        lines.append("")
    else:
        lines += [
            "All reduction checks pass: the like-for-like gate holds, the",
            "crossing-count premise for the slope holds, every committed",
            "baseline trace matched its pinned sha256/16.",
            "",
        ]
    lines += [
        "## What this record does not claim",
        "",
        "- No spec row, threshold, gate, record or verdict changed; DR-0015",
        "  stays Proposed; no compensation candidate is proposed, screened or",
        "  ratified here (the remedy search is E4 / the family-(B) screen's",
        "  business, out of this experiment's scope).",
        "- Three sampled Cc values at one PVT point only: no monotonicity or",
        "  window claim over Cc, no claim about any other corner, and no",
        "  measured pole frequency -- the slope is an attribution PROBE, not",
        "  a pole extraction.",
        "- cap_cmomi's model coefficients are transferred from SG13G2",
        "  characterisation and not validated on cmos5l silicon",
        "  (sim/pdk-cmos5l.json `cap_cmomi_not_validated_on_cmos5l_silicon`):",
        "  every number above inherits that caveat.",
        "- `sim/` stays append-only: nothing under `records/`, `corners/`,",
        "  `evidence/` or `netlist-snapshots/` was edited or deleted.",
        "",
        "## Files",
        "",
        f"- Reduction: `records/{rid}.{BENCH}.csv` (one row per Cc value; the",
        f"  column contract is `ccprobe.py` CSV_FIELDS),",
        f"  `evidence/{rid}/ccprobe-report.json` (slope, baselines, failed",
        "  checks).",
        f"- Raw exports + fleet provenance: `corners/{rid}/` (per-point log",
        f"  and `_ac.csv`; `_batch/` carries the requests, the decks,",
        "  `points.tsv`, `inputs.sha256.json`, `backend.json`).",
        f"- Netlists: `netlist-snapshots/{rid}/` (one generated deck per Cc",
        "  value plus the three Cc-substituted design-netlist copies; sha256",
        "  in the manifest).",
        f"- Manifest: `records/{rid}.{BENCH}.manifest.tsv`.",
        "",
        "<!-- regeneration: python3 sim/ldo-cmos5l-pvt-sweep/ccprobe.py",
        f"     reduce --record {rid} --out-csv <tmp> --out-json <tmp>;",
        f"     ccprobe.py record-md --record {rid};",
        f"     ccprobe.py check --record {rid} byte-compares. -->",
        "",
    ]
    return "\n".join(lines)


def _safe_rel(delta, ref):
    if delta is None or not ref:
        return None
    return delta / ref


def cmd_record_md(a):
    out = os.path.join(HERE, "records", f"{a.record}.{BENCH}.md")
    with open(out, "w") as fh:
        fh.write(record_md(a.record))
    print(f"ccprobe: wrote {out}", file=sys.stderr)
    return 0


def cmd_check(a):
    """CI: regenerate the CSV, JSON and record md from the committed exports
    and byte-compare. Writes only into a throwaway temp dir."""
    rid = a.record
    rec_csv = os.path.join(HERE, "records", f"{rid}.{BENCH}.csv")
    rec_json = os.path.join(HERE, "evidence", rid, "ccprobe-report.json")
    rec_md = os.path.join(HERE, "records", f"{rid}.{BENCH}.md")
    rc = 0
    with tempfile.TemporaryDirectory() as tmp:
        a2 = argparse.Namespace(record=rid, corners_dir=None,
                                out_csv=os.path.join(tmp, "r.csv"),
                                out_json=os.path.join(tmp, "r.json"))
        rc = cmd_reduce(a2)
        for got, want, what in ((os.path.join(tmp, "r.csv"), rec_csv, "csv"),
                                (os.path.join(tmp, "r.json"), rec_json, "json")):
            if open(got).read() != open(want).read():
                print(f"ccprobe: check: regenerated {what} differs from {want}",
                      file=sys.stderr)
                rc = rc or 1
        if record_md(rid) != open(rec_md).read():
            print(f"ccprobe: check: regenerated record md differs from {rec_md}",
                  file=sys.stderr)
            rc = rc or 1
    if rc == 0:
        print(f"ccprobe: check: {rid} reproduces byte-for-byte", file=sys.stderr)
    return rc


def cmd_widths(_a):
    for label in CC_LABELS:
        print(f"{label}\t{cc_w(label)}\t{cc_w_desc(label)}")
    return 0


def cmd_subst(a):
    """Write the Cc-substituted copy of netlist IN to OUT (exit 4 = the
    substitution did not reach the deck -- the FATAL, not a no-op)."""
    try:
        with open(a.infile, encoding="utf-8") as fh:
            text = fh.read()
        out = subst_cc_width(text, a.label)
    except CcSubstitutionError as e:
        print(f"ccprobe: subst: FATAL -- {e}", file=sys.stderr)
        return 4
    with open(a.outfile, "w", encoding="utf-8") as fh:
        fh.write(out)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("widths")
    s = sub.add_parser("subst")
    s.add_argument("infile")
    s.add_argument("outfile")
    s.add_argument("label")
    r = sub.add_parser("reduce")
    r.add_argument("--record", required=True)
    r.add_argument("--corners-dir", default=None)
    r.add_argument("--out-csv", required=True)
    r.add_argument("--out-json", required=True)
    m = sub.add_parser("record-md")
    m.add_argument("--record", required=True)
    c = sub.add_parser("check")
    c.add_argument("--record", required=True)
    a = ap.parse_args()
    if a.cmd == "widths":
        return cmd_widths(a)
    if a.cmd == "subst":
        return cmd_subst(a)
    if a.cmd == "reduce":
        return cmd_reduce(a)
    if a.cmd == "record-md":
        return cmd_record_md(a)
    if a.cmd == "check":
        return cmd_check(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())
