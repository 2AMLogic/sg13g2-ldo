#!/usr/bin/env python3
"""Post-processing for the SG13CMOS5L PVT sweep: raw bench CSVs -> record artifacts.

`run_sweep.sh` runs the benches; this module turns the raw per-point `wrdata`
exports under `corners/<record-id>/` into the six artifacts a record is made
of:

  * the main record CSV                    (one row per corner x temp x R corner)
  * the sensitivity CSV                    (Cc-value and resistor-corner sweeps)
  * the `Cc` value-tolerance CSV           (issue #35 / DR-0005)
  * the before/after/delta CSV             (against the pinned baseline record)
  * the divider-attribution CSV            (behavioural 300k vs PDK `rhigh`)
  * the before/after/delta markdown fragment inlined into the record

Until issue #223 this was a 411-line `<<'PYEOF'` heredoc inside
`run_sweep.sh`, which meant the code computing every recorded number was the
one part of the campaign that CI's `unittest discover` over this directory
could not reach -- a heredoc cannot be imported. It is a sibling module now,
next to the parsers already lifted out of this same heredoc by issues #55,
#64 and #120, and `test_sweep_report.py` covers it.

    python3 sweep_report.py --corners-dir corners/<id> \
        --csv-out records/<id>.csv --sens-csv-out records/<id>.sensitivity.csv \
        --baseline-csv records/<baseline-id>.csv \
        --delta-csv-out records/<id>.delta.csv \
        --cmp-md-out corners/<id>/_before_after_delta.md \
        --corner tt --corner ss --temp -40 --temp 27 --res-label typ \
        --cc-tol-width 170e-6 --cc-nominal-w 170e-6

Two artifact paths are derived rather than passed, exactly as they were when
this was a heredoc: the `Cc`-tolerance CSV from `--csv-out` and the
divider-attribution CSV from `--delta-csv-out`.
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Shared DC-grid parser (issue #55): one interpretation of the raw wrdata CSV,
# also used by item5_evidence.py -- reached here through the complete-grid
# contract (issue #120), the same validator item5_evidence.py uses.
# dc_metrics.py stays byte-identical (its sha256 is pinned by landed
# artifacts); a grid that fails validation yields {"error": ...}, never a
# nearest-point numeric summary.
import dc_grid as _dcg  # noqa: E402
# Shared AC parsers (issue #64): extracted verbatim to ac_metrics.py.
import ac_metrics as _acm  # noqa: E402

dc_metrics = _dcg.validated_dc_metrics
loopgain_metrics = _acm.loopgain_metrics
psrr_metrics = _acm.psrr_metrics


MAIN_FIELDNAMES = [
    "corner", "temp_c", "res_section", "iq_a", "vout_no_load_v",
    "i_divider_a", "r_divider_leg_ohm",
    "line_reg_in_regulation", "line_reg_mv_per_v",
    "dropout_v_50ma", "dropout_v_50ma_floor", "vout_at_vinmax_50ma_v",
    "load_reg_pct",
    "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "phase_margin_worst_deg",
    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db",
    "psrr_db_1khz", "psrr_db_100khz",
]

SENS_FIELDNAMES = [
    "sweep", "point", "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "phase_margin_worst_deg",
    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db",
]

CCTOL_FIELDNAMES = [
    "cc_w", "cc_x_nominal", "corner", "temp_c", "res_section",
    "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "gain_margin_db", "psrr_db_1khz", "psrr_db_100khz",
    "pm_ok", "gm_ok", "psrr_1khz_ok", "psrr_100khz_ok", "all_ok",
]

DELTA_FIELDNAMES = ["corner", "temp_c", "res_section", "metric", "unit",
                    "before", "after", "delta"]

ATTR_KEYS = ("phase_margin_deg", "gain_margin_db", "dc_gain_db")
ATTR_FIELDNAMES = ["corner", "temp_c", "res_section"]
for _key in ATTR_KEYS:
    ATTR_FIELDNAMES += [f"{_key}_behavioural_divider", f"{_key}_rhigh_divider",
                        f"{_key}_divider_delta"]

# Cc-value and resistor-corner sensitivity points, tt/27C only.
CC_SENS_POINTS = ["0.5x", "1x", "2x"]
RES_SENS_POINTS = ["bcs", "typ", "wcs"]

# The two resistor sections that hold a worst case for the Cc-tolerance sweep.
CCTOL_RES_LABELS = ["bcs", "wcs"]

# Metrics carried across from the baseline record for the delta comparison.
BASELINE_KEYS = ("dc_gain_db", "phase_margin_deg", "unity_gain_freq_hz",
                 "gain_margin_db", "psrr_db_1khz", "psrr_db_100khz",
                 "iq_a", "vout_no_load_v", "i_divider_a",
                 "line_reg_mv_per_v", "load_reg_pct",
                 "dropout_v_50ma")

METRICS = [
    # (csv key, heading, unit, scale, decimals, higher_is_better)
    ("phase_margin_deg", "Phase margin", "deg", 1.0, 2, True),
    ("gain_margin_db", "Gain margin", "dB", 1.0, 2, True),
    ("unity_gain_freq_hz", "Unity-gain frequency", "kHz", 1e-3, 2, None),
    ("dc_gain_db", "DC loop gain", "dB", 1.0, 2, True),
    ("psrr_db_1khz", "PSRR @ 1kHz", "dB", 1.0, 2, True),
    ("psrr_db_100khz", "PSRR @ 100kHz", "dB", 1.0, 2, True),
    ("iq_a", "Iq, no load", "uA", 1e6, 3, False),
    ("dropout_v_50ma", "Dropout @ 50mA", "V", 1.0, 3, False),
    ("line_reg_mv_per_v", "Line regulation", "mV/V", 1.0, 3, False),
    ("load_reg_pct", "Load regulation", "%", 1.0, 4, False),
    ("vout_no_load_v", "Output accuracy (VOUT, no load)", "V", 1.0, 5, None),
    ("i_divider_a", "Divider standing current", "uA", 1e6, 3, False),
]

# Mechanical spec comparison. Thresholds are the repo root README.md's target
# table verbatim (issue #55 audit: only row 4, dropout, is RATIFIED per
# DR-0007; every other comparison is INFORMATIONAL and never a requirement
# gate) (the same table sim/ldo-cmos5l-pvt-sweep's own Results section is
# stated against), evaluated against EVERY point in the run's grid. This is
# computed, not asserted in prose, so a record can never claim a PASS its own
# CSV contradicts -- and so a regression in a future run surfaces in the
# record itself rather than relying on a reader re-deriving it from the CSV.
# RATIFIED_KEYS: DR-0007 ratifies row 4 (dropout) only.
RATIFIED_KEYS = {"dropout_v_50ma"}
SPEC = [
    ("phase_margin_deg", "Phase margin >= 45 deg", lambda v: v >= 45.0, "deg", 2),
    ("gain_margin_db", "Gain margin >= 10 dB", lambda v: v >= 10.0, "dB", 2),
    ("iq_a", "Iq (no load) < 30 uA", lambda v: v < 30e-6, "A", 9),
    ("psrr_db_1khz", "PSRR @ 1kHz > 50 dB", lambda v: v > 50.0, "dB", 2),
    ("psrr_db_100khz", "PSRR @ 100kHz > 20 dB", lambda v: v > 20.0, "dB", 2),
    ("line_reg_mv_per_v", "Line regulation < 5 mV/V", lambda v: v < 5.0, "mV/V", 3),
    ("load_reg_pct", "Load regulation < 1 %", lambda v: v < 1.0, "%", 4),
    ("dropout_v_50ma", "Dropout @ 50mA < 300 mV", lambda v: v < 0.300, "V", 3),
    ("vout_no_load_v", "Output accuracy 1.8V +/-2%", lambda v: abs(v - 1.8) <= 0.036, "V", 5),
]


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def write_csv(path, fieldnames, rows):
    """Every artifact CSV is written exactly this way: a DictWriter that
    ignores extra keys, with `None` rendered as the empty cell (never
    "None")."""
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k))
                        for k in fieldnames})


def fmt(v, scale, dec, signed=False):
    """Markdown cell for a metric value: "n/a" for a missing one."""
    if v is None:
        return "n/a"
    s = f"{v * scale:+.{dec}f}" if signed else f"{v * scale:.{dec}f}"
    return s


def cctol_csv_path(csv_out):
    """The Cc-tolerance CSV sits beside the main record CSV."""
    return csv_out.replace(".csv", ".cc-tolerance.csv")


def attr_csv_path(delta_csv_out):
    """The divider-attribution CSV sits beside the delta CSV."""
    return delta_csv_out.replace(".delta.csv", ".divider-attribution.csv")


# --------------------------------------------------------------------------
# 1. main record CSV
# --------------------------------------------------------------------------

def collect_main_rows(corners_dir, corners, temps, res_labels):
    """One row per (corner, temperature, resistor section).

    Returns `(rows, dc_grid_errors)`. A DC grid that fails the issue #120
    complete-grid contract contributes NO metrics -- its failure reason is
    returned instead, for the sidecar the shell folds into failed_points.
    """
    rows = []
    dc_grid_errors = {}
    for corner in corners:
        for temp in temps:
            for rlabel in res_labels:
                row = {"corner": corner, "temp_c": temp,
                       "res_section": f"res_{rlabel}"}
                sfx = f"{corner}_{temp}c_r{rlabel}"
                dc = dc_metrics(f"{corners_dir}/dcsweep_{sfx}_dc.csv")
                if dc and "error" in dc:
                    dc_grid_errors[f"dcsweep_{sfx}"] = dc["error"]
                    dc = None  # no metrics from an invalid grid; error kept
                lg = loopgain_metrics(f"{corners_dir}/loopgain_{sfx}_ac.csv")
                ps = psrr_metrics(f"{corners_dir}/psrr_{sfx}_ac.csv")
                for src in (dc, lg, ps):
                    if src:
                        row.update({k: v for k, v in src.items()
                                    if k != "vout_at_vinmax_by_load"})
                rows.append(row)
    return rows, dc_grid_errors


def write_main_csv(path, main_rows):
    write_csv(path, MAIN_FIELDNAMES, main_rows)


def write_dc_grid_errors(corners_dir, dc_grid_errors):
    """Invalid DC grids keep their failure reason: written to a sidecar the
    shell folds into failed_points (-> INCOMPLETE + exit 1) after the outputs
    exist. No sidecar is written when there are no errors."""
    if not dc_grid_errors:
        return None
    path = os.path.join(corners_dir, "_dc_grid_errors.tsv")
    with open(path, "w") as f:
        for pid, err in dc_grid_errors.items():
            print(f"run_sweep.sh: INVALID DC GRID {pid}: {err}", file=sys.stderr)
            f.write(f"{pid}\t{err}\n")
    return path


# --------------------------------------------------------------------------
# 2. sensitivity CSV: Cc value sweep + resistor corner sweep, tt/27C only
# --------------------------------------------------------------------------

def collect_sens_rows(corners_dir):
    rows = []
    for label in CC_SENS_POINTS:
        lg = loopgain_metrics(
            f"{corners_dir}/loopgain_ccsens_{label}_tt_27c_ac.csv")
        row = {"sweep": "cc_value", "point": label}
        if lg:
            row.update(lg)
        rows.append(row)
    for label in RES_SENS_POINTS:
        lg = loopgain_metrics(
            f"{corners_dir}/loopgain_ressens_{label}_tt_27c_ac.csv")
        # Named "rz_corner" in the #21/#25 records, when Rz was the only rhigh
        # in the loop; since #28 this section moves the feedback divider too.
        row = {"sweep": "res_corner", "point": label}
        if lg:
            row.update(lg)
        rows.append(row)
    return rows


def write_sens_csv(path, sens_rows):
    write_csv(path, SENS_FIELDNAMES, sens_rows)


# --------------------------------------------------------------------------
# 3. Cc value-tolerance CSV
# --------------------------------------------------------------------------

def collect_cctol_rows(corners_dir, cc_tol_widths, cc_nominal_f):
    """The two opposing bounds on Cc, measured at the corners that actually
    bind them (issue #35 / DR-0005).

    PM comes from the loopgain bench and PSRR from the psrr bench at the SAME
    point, so a row reads as "at this Cc, at this corner, here is every
    stability/PSRR row the spec table asks for".
    """
    rows = []
    for w_str in cc_tol_widths:
        for rlabel in CCTOL_RES_LABELS:
            sfx = f"cctol_{w_str}_ss_125c_r{rlabel}"
            lg = loopgain_metrics(f"{corners_dir}/loopgain_{sfx}_ac.csv")
            ps = psrr_metrics(f"{corners_dir}/psrr_{sfx}_ac.csv")
            row = {"cc_w": w_str,
                   "cc_x_nominal": float(w_str) / cc_nominal_f,
                   "corner": "ss", "temp_c": 125,
                   "res_section": f"res_{rlabel}"}
            for src in (lg, ps):
                if src:
                    row.update(src)
            row["pm_ok"] = (row.get("phase_margin_deg") is not None
                            and row["phase_margin_deg"] >= 45.0)
            row["gm_ok"] = (row.get("gain_margin_db") is not None
                            and row["gain_margin_db"] >= 10.0)
            row["psrr_1khz_ok"] = (row.get("psrr_db_1khz") is not None
                                   and row["psrr_db_1khz"] > 50.0)
            row["psrr_100khz_ok"] = (row.get("psrr_db_100khz") is not None
                                     and row["psrr_db_100khz"] > 20.0)
            row["all_ok"] = all(row[k] for k in
                                ("pm_ok", "gm_ok", "psrr_1khz_ok",
                                 "psrr_100khz_ok"))
            rows.append(row)
    return rows


def write_cctol_csv(path, cctol_rows):
    write_csv(path, CCTOL_FIELDNAMES, cctol_rows)


def cctol_widths_verdict(cctol_rows, cc_tol_widths):
    """-> (widths holding every row at both binding sections, widths not).

    A width counts as passing only if EVERY row at that width passes -- one of
    the two binding sections failing is a failing width, not a half-passing
    one.
    """
    by_w = {}
    for r in cctol_rows:
        by_w.setdefault(r["cc_w"], []).append(r)
    ok_w = [w for w in cc_tol_widths if all(r["all_ok"] for r in by_w.get(w, []))]
    bad_w = [w for w in cc_tol_widths if w not in ok_w]
    return ok_w, bad_w


# --------------------------------------------------------------------------
# 4. before / after / delta against the pinned baseline record
# --------------------------------------------------------------------------

def _f(r, k):
    try:
        return float(r[k])
    except (KeyError, TypeError, ValueError):
        return None


def read_baseline(baseline_csv):
    """"Before" is the baseline record named by --baseline-csv.

    From issue #35 that is the #31 record -- the first run against BOTH the
    PDK `rhigh` feedback divider (#28) and the full crossed resistor axis, and
    the run that found the res_bcs/125C phase-margin gap #35 exists to close.
    Because that record already carries one row per
    (corner, temperature, res_section), the comparison is like-for-like at
    every one of the 45 grid points: same benches, same PDK pin, same ngspice
    build, same resistor section on both sides, so the deltas isolate the
    compensation change and nothing else.

    (The #21/#25 records key on (corner, temperature) only -- they held the
    resistor axis at res_typ -- so pointing --baseline-csv back at one of them
    leaves the res_bcs/res_wcs "before" cells empty rather than silently
    comparing against the wrong section. That is the intended behaviour: a
    missing cell reads "n/a", it does not read as a zero delta.)

    A baseline path that does not exist yields an empty mapping, i.e. every
    "before" cell is missing -- never a zero delta.
    """
    baseline = {}
    if os.path.exists(baseline_csv):
        with open(baseline_csv) as f:
            for r in csv.DictReader(f):
                key = (r["corner"], r["temp_c"], r.get("res_section", "res_typ"))
                baseline[key] = {k: _f(r, k) for k in BASELINE_KEYS}
    return baseline


def index_after(main_rows):
    """This run's rows, keyed the same way as the baseline's."""
    return {(r["corner"], str(r["temp_c"]), r["res_section"]): r
            for r in main_rows}


def collect_delta_rows(baseline, after, corners, temps, res_labels):
    rows = []
    for corner in corners:
        for temp in temps:
            for rlabel in res_labels:
                section = f"res_{rlabel}"
                b = baseline.get((corner, str(temp), section), {})
                a = after.get((corner, str(temp), section), {})
                for key, _heading, unit, _scale, _dec, _hib in METRICS:
                    bv, av = b.get(key), a.get(key)
                    rows.append({
                        "corner": corner, "temp_c": temp,
                        "res_section": section,
                        "metric": key, "unit": unit,
                        "before": bv, "after": av,
                        "delta": (av - bv) if (bv is not None
                                               and av is not None) else None,
                    })
    return rows


def write_delta_csv(path, delta_rows):
    write_csv(path, DELTA_FIELDNAMES, delta_rows)


# --------------------------------------------------------------------------
# 5. divider attribution
# --------------------------------------------------------------------------

def collect_attr_rows(corners_dir, after, corners, temps, res_labels):
    """Same point, same resistor section, divider swapped back to the pre-#28
    behavioural 300k pair. The difference is the conversion's OWN
    contribution, with Rz's corner spread common to both sides and therefore
    cancelled."""
    rows = []
    for corner in corners:
        for temp in temps:
            for rlabel in res_labels:
                sfx = f"{corner}_{temp}c_r{rlabel}"
                beh = loopgain_metrics(
                    f"{corners_dir}/loopgain_divattr_{sfx}_ac.csv")
                rh = after.get((corner, str(temp), f"res_{rlabel}"), {})
                row = {"corner": corner, "temp_c": temp,
                       "res_section": f"res_{rlabel}"}
                for key in ATTR_KEYS:
                    bv = (beh or {}).get(key)
                    av = rh.get(key)
                    row[f"{key}_behavioural_divider"] = bv
                    row[f"{key}_rhigh_divider"] = av
                    row[f"{key}_divider_delta"] = (
                        (av - bv) if (bv is not None and av is not None)
                        else None)
                rows.append(row)
    return rows


def write_attr_csv(path, attr_rows):
    write_csv(path, ATTR_FIELDNAMES, attr_rows)


# --------------------------------------------------------------------------
# 6. before / after / delta markdown fragment
# --------------------------------------------------------------------------

def _write_delta_tables(f, delta_rows, baseline_label):
    by_key = {}
    for row in delta_rows:
        by_key.setdefault(row["metric"], []).append(row)
    for key, heading, unit, scale, dec, _hib in METRICS:
        rows = by_key.get(key, [])
        deltas = [r["delta"] for r in rows if r.get("delta") is not None]
        worst = max(deltas, key=abs) if deltas else None
        f.write(f"\n### {heading} ({unit})\n\n")
        if deltas:
            f.write(f"Largest change across all {len(deltas)} compared points: "
                    f"**{fmt(worst, scale, dec, signed=True)} {unit}**.\n\n")
        f.write(f"| corner / temp / R corner | before (`{baseline_label}`) "
                "| after (this run) | delta |\n")
        f.write("|---|---|---|---|\n")
        for row in rows:
            f.write(
                f"| `{row['corner']}` / {row['temp_c']}C / `{row['res_section']}` "
                f"| {fmt(row.get('before'), scale, dec)} "
                f"| {fmt(row.get('after'), scale, dec)} "
                f"| {fmt(row.get('delta'), scale, dec, signed=True)} |\n")


def _write_cctol_section(f, cctol_rows, cc_tol_widths, cc_nominal_w,
                         cc_nominal_f, cctol_csv_out):
    """The `Cc` value-tolerance window (issue #35 / DR-0005)."""
    f.write("\n### `Cc` value-tolerance window, at the corners that bind it\n\n")
    f.write("`cornerCAP.lib` maps every corner/mismatch/stat section to the\n"
            "SAME nominal `cap_cmomi` model at this PDK's pin, so there is no\n"
            "characterised MoM-cap corner spread to sweep -- and the PDK's own\n"
            "documentation flags the model as not validated on CMOS5L silicon.\n"
            "Tolerance to a wrong cap VALUE is therefore the only robustness\n"
            "this caveat can be given, and it is measured here rather than\n"
            "asserted: `Cc`'s width is swept at `ss`/125C against both resistor\n"
            "sections that hold a worst case, with the loop-gain AND PSRR\n"
            "benches run at every point. A small `Cc` fails from below (the\n"
            "`Rz*Cc` zero lands above crossover at `res_bcs`, where `Rz` has\n"
            "shrunk to ~0.60x); a large `Cc` fails from above (the dominant\n"
            "pole, and with it the 1 kHz loop gain that sets PSRR, drops too\n"
            f"far). Machine-readable: `records/{os.path.basename(cctol_csv_out)}`.\n\n")
    f.write("| `Cc` w | x nominal | R corner | PM (deg) | GM (dB) "
            "| PSRR@1kHz (dB) | PSRR@100kHz (dB) | all spec rows met |\n")
    f.write("|---|---|---|---|---|---|---|---|\n")
    for row in cctol_rows:
        f.write(
            f"| `{row['cc_w']}` | {row['cc_x_nominal']:.2f}x "
            f"| `{row['res_section']}` "
            f"| {fmt(row.get('phase_margin_deg'), 1.0, 2)} "
            f"| {fmt(row.get('gain_margin_db'), 1.0, 2)} "
            f"| {fmt(row.get('psrr_db_1khz'), 1.0, 2)} "
            f"| {fmt(row.get('psrr_db_100khz'), 1.0, 2)} "
            f"| {'yes' if row['all_ok'] else '**NO**'} |\n")
    ok_w, bad_w = cctol_widths_verdict(cctol_rows, cc_tol_widths)
    if ok_w:
        lo, hi = ok_w[0], ok_w[-1]
        f.write(f"\nEvery swept width from `{lo}` to `{hi}` meets every spec row at\n"
                f"both binding corners. The nominal is `{cc_nominal_w}`, so the\n"
                f"verdict tolerates a MoM-cap value from x{float(lo) / cc_nominal_f:.2f} to "
                f"x{float(hi) / cc_nominal_f:.2f}\nof what this model says it is.\n")
    if bad_w:
        f.write("\nWidths that do NOT hold every row at both binding corners: "
                + ", ".join(f"`{w}`" for w in bad_w)
                + ".\nThey are in the sweep on purpose: a tolerance window with no\n"
                  "measured ends is not a tolerance window.\n")


def _write_spec_section(f, main_rows, csv_out):
    """Mechanical spec comparison over every point in the grid; see SPEC."""
    f.write("\n### Spec comparison over every point in this grid (row 4 ratified; all others informational)\n\n")
    f.write("Thresholds are the repo root `README.md` target table's, applied\n"
            "mechanically to this record's own CSV -- not restated by hand.\n"
            "Per DR-0007 only the dropout row is RATIFIED (a requirement\n"
            "gate); every other row is OPEN and its comparison here is\n"
            "informational, never a pass claim for a ratified requirement.\n\n")
    f.write("| Spec row | DR-0007 status | Points evaluated | Points failing | Worst point |\n")
    f.write("|---|---|---|---|---|\n")
    gate_failures = []
    for key, label, ok, unit, dec in SPEC:
        pts = [(r.get(key), r) for r in main_rows if r.get(key) is not None]
        bad = [(v, r) for v, r in pts if not ok(v)]
        if bad:
            worst = min(bad, key=lambda t: t[0]) if key != "load_reg_pct" else max(bad, key=lambda t: t[0])
            wv, wr = worst
            worst_s = (f"`{wr['corner']}`/{wr['temp_c']}C/`{wr['res_section']}` "
                       f"= {wv:.{dec}f} {unit}")
            gate_failures.append((label, len(bad), len(pts), worst_s))
        else:
            worst_s = "--"
        status_s = "ratified (gate)" if key in RATIFIED_KEYS else "Open (informational)"
        f.write(f"| {label} | {status_s} | {len(pts)} | **{len(bad)}** | {worst_s} |\n")
    if gate_failures:
        f.write("\n**Targets NOT met at every point in this grid (ratified rows are gates; Open rows informational):**\n\n")
        for label, nbad, npts, worst_s in gate_failures:
            f.write(f"- {label} -- fails at {nbad} of {npts} points; worst {worst_s}\n")
        f.write("\nEvery failing point is listed row by row in "
                f"`records/{os.path.basename(csv_out)}`. Per CLAUDE.md, no spec\n"
                "row is relaxed to make this record pass; see the experiment\n"
                "README's Results section and the decision record it cites.\n")
    else:
        f.write("\nEvery spec row above is met at every point in this grid.\n")


def _write_attribution_section(f, attr_rows, attr_csv_out):
    f.write("\n### Divider attribution: the conversion's own contribution\n\n")
    f.write("Same point, same MOS corner, same temperature, same resistor\n"
            "section, same `Cc` -- the only difference is the feedback\n"
            "divider: the pre-#28 behavioural 300k pair vs the PDK `rhigh`\n"
            "pair now in the schematic. Because `Rz`'s corner spread is\n"
            "common to both sides, it cancels, and what is left is the\n"
            "divider conversion's own effect. (Machine-readable:\n"
            f"`records/{os.path.basename(attr_csv_out)}`.)\n\n")
    f.write("| corner / temp / R corner | PM, behavioural 300k (deg) "
            "| PM, PDK `rhigh` (deg) | PM delta (deg) "
            "| GM delta (dB) | loop gain delta (dB) |\n")
    f.write("|---|---|---|---|---|---|\n")
    for row in attr_rows:
        f.write(
            f"| `{row['corner']}` / {row['temp_c']}C / `{row['res_section']}` "
            f"| {fmt(row.get('phase_margin_deg_behavioural_divider'), 1.0, 2)} "
            f"| {fmt(row.get('phase_margin_deg_rhigh_divider'), 1.0, 2)} "
            f"| {fmt(row.get('phase_margin_deg_divider_delta'), 1.0, 2, signed=True)} "
            f"| {fmt(row.get('gain_margin_db_divider_delta'), 1.0, 2, signed=True)} "
            f"| {fmt(row.get('dc_gain_db_divider_delta'), 1.0, 2, signed=True)} |\n")


def write_markdown_fragment(path, baseline_csv, main_rows, delta_rows,
                            cctol_rows, attr_rows, cc_tol_widths,
                            cc_nominal_w, cc_nominal_f, csv_out,
                            cctol_csv_out, attr_csv_out):
    with open(path, "w") as f:
        baseline_label = os.path.basename(baseline_csv).replace(".csv", "")
        _write_delta_tables(f, delta_rows, baseline_label)
        _write_cctol_section(f, cctol_rows, cc_tol_widths, cc_nominal_w,
                             cc_nominal_f, cctol_csv_out)
        _write_spec_section(f, main_rows, csv_out)
        _write_attribution_section(f, attr_rows, attr_csv_out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="sweep_report.py",
        description="Turn a PVT sweep's raw bench CSVs into the record artifacts.")
    p.add_argument("--corners-dir", required=True,
                   help="directory holding this run's raw per-point wrdata CSVs")
    p.add_argument("--csv-out", required=True,
                   help="main record CSV; the Cc-tolerance CSV is derived from it")
    p.add_argument("--sens-csv-out", required=True, help="sensitivity CSV")
    p.add_argument("--baseline-csv", required=True,
                   help="pinned baseline record CSV for the before/after "
                        "comparison; a path that does not exist leaves every "
                        "\"before\" cell empty")
    p.add_argument("--delta-csv-out", required=True,
                   help="delta CSV; the divider-attribution CSV is derived from it")
    p.add_argument("--cmp-md-out", required=True,
                   help="before/after/delta markdown fragment")
    p.add_argument("--corner", action="append", metavar="NAME", required=True,
                   help="MOS corner axis; repeat once per corner (tt, ss, ...)")
    p.add_argument("--temp", action="append", metavar="DEGC", required=True,
                   help="temperature axis; repeat once per temperature")
    p.add_argument("--res-label", action="append", metavar="LABEL", required=True,
                   help="resistor-section axis; repeat once per section "
                        "(typ, bcs, wcs)")
    p.add_argument("--cc-tol-width", action="append", metavar="W", default=None,
                   help="Cc width for the value-tolerance sweep; repeat once "
                        "per width, or omit entirely to skip the sweep")
    p.add_argument("--cc-nominal-w", required=True, metavar="W",
                   help="nominal Cc width, the x-nominal reference")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    corners = args.corner
    temps = args.temp
    res_labels = args.res_label
    cc_tol_widths = args.cc_tol_width or []
    cc_nominal_f = float(args.cc_nominal_w)

    cctol_csv_out = cctol_csv_path(args.csv_out)
    attr_csv_out = attr_csv_path(args.delta_csv_out)

    main_rows, dc_grid_errors = collect_main_rows(
        args.corners_dir, corners, temps, res_labels)
    write_main_csv(args.csv_out, main_rows)
    write_dc_grid_errors(args.corners_dir, dc_grid_errors)

    sens_rows = collect_sens_rows(args.corners_dir)
    write_sens_csv(args.sens_csv_out, sens_rows)

    cctol_rows = collect_cctol_rows(args.corners_dir, cc_tol_widths, cc_nominal_f)
    write_cctol_csv(cctol_csv_out, cctol_rows)

    baseline = read_baseline(args.baseline_csv)
    after = index_after(main_rows)
    delta_rows = collect_delta_rows(baseline, after, corners, temps, res_labels)
    write_delta_csv(args.delta_csv_out, delta_rows)

    attr_rows = collect_attr_rows(args.corners_dir, after, corners, temps,
                                  res_labels)
    write_attr_csv(attr_csv_out, attr_rows)

    write_markdown_fragment(
        args.cmp_md_out, args.baseline_csv, main_rows, delta_rows, cctol_rows,
        attr_rows, cc_tol_widths, args.cc_nominal_w, cc_nominal_f,
        args.csv_out, cctol_csv_out, attr_csv_out)

    print(f"run_sweep.sh (post-process): wrote {len(main_rows)} main rows, "
          f"{len(sens_rows)} sensitivity rows, {len(cctol_rows)} Cc-tolerance rows, "
          f"{len(delta_rows)} delta rows, "
          f"{len(attr_rows)} divider-attribution rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
