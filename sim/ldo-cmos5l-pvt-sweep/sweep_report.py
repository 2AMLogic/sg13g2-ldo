import csv, sys, math, os

(corners_dir, csv_out, sens_csv_out, corners_str, temps_str,
 res_labels_str, baseline_csv, delta_csv_out, cmp_md_out,
 cc_tol_widths_str, cc_nominal_w) = sys.argv[1:12]
CORNERS = corners_str.split()
TEMPS = [t for t in temps_str.split()]
RES_LABELS = res_labels_str.split()
CC_TOL_WIDTHS = cc_tol_widths_str.split()

VOUT_TARGET = 1.8
VIN_MIN, VIN_MAX, VIN_STEP = 2.00, 3.63, 0.01


# Shared DC-grid parser (issue #55): one interpretation of the raw wrdata
# CSV, also used by item5_evidence.py. Unchanged logic, just extracted.
sys.path.insert(0, os.environ["SWEEP_SCRIPT_DIR"])
import dc_metrics as _dcm
read_wrdata = _dcm.read_wrdata
# Complete-grid contract (issue #120): the same validator item5_evidence.py
# uses. dc_metrics.py stays byte-identical (its sha256 is pinned by landed
# artifacts); a grid that fails validation yields {"error": ...}, never a
# nearest-point numeric summary.
import dc_grid as _dcg
dc_metrics = _dcg.validated_dc_metrics
dc_grid_errors = {}


# Shared AC parsers (issue #64): extracted verbatim to ac_metrics.py.
import ac_metrics as _acm
unwrap_deg = _acm.unwrap_deg
loopgain_metrics = _acm.loopgain_metrics
psrr_metrics = _acm.psrr_metrics


main_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        for rlabel in RES_LABELS:
            row = {"corner": corner, "temp_c": temp, "res_section": f"res_{rlabel}"}
            sfx = f"{corner}_{temp}c_r{rlabel}"
            dc = dc_metrics(f"{corners_dir}/dcsweep_{sfx}_dc.csv")
            if dc and "error" in dc:
                dc_grid_errors[f"dcsweep_{sfx}"] = dc["error"]
                dc = None  # no metrics from an invalid grid; error kept below
            lg = loopgain_metrics(f"{corners_dir}/loopgain_{sfx}_ac.csv")
            ps = psrr_metrics(f"{corners_dir}/psrr_{sfx}_ac.csv")
            for src in (dc, lg, ps):
                if src:
                    row.update({k: v for k, v in src.items() if k != "vout_at_vinmax_by_load"})
            main_rows.append(row)

fieldnames = [
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
with open(csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in main_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})

# Invalid DC grids keep their failure reason: written to a sidecar the shell
# folds into failed_points (-> INCOMPLETE + exit 1) after the outputs exist.
if dc_grid_errors:
    with open(os.path.join(corners_dir, "_dc_grid_errors.tsv"), "w") as f:
        for pid, err in dc_grid_errors.items():
            print(f"run_sweep.sh: INVALID DC GRID {pid}: {err}", file=sys.stderr)
            f.write(f"{pid}\t{err}\n")

# --- Sensitivity CSV: Cc value sweep + resistor corner sweep, tt/27C only ---
sens_rows = []
for label in ["0.5x", "1x", "2x"]:
    lg = loopgain_metrics(f"{corners_dir}/loopgain_ccsens_{label}_tt_27c_ac.csv")
    row = {"sweep": "cc_value", "point": label}
    if lg:
        row.update(lg)
    sens_rows.append(row)
for label in ["bcs", "typ", "wcs"]:
    lg = loopgain_metrics(f"{corners_dir}/loopgain_ressens_{label}_tt_27c_ac.csv")
    # Named "rz_corner" in the #21/#25 records, when Rz was the only rhigh
    # in the loop; since #28 this section moves the feedback divider too.
    row = {"sweep": "res_corner", "point": label}
    if lg:
        row.update(lg)
    sens_rows.append(row)

sens_fieldnames = [
    "sweep", "point", "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "phase_margin_worst_deg",
    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db",
]
with open(sens_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=sens_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in sens_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in sens_fieldnames})

# --- Cc value-tolerance CSV: the two opposing bounds on Cc, measured at the
# corners that actually bind them (issue #35 / DR-0005). PM comes from the
# loopgain bench and PSRR from the psrr bench at the SAME point, so a row can
# be read as "at this Cc, at this corner, here is every stability/PSRR row
# the spec table asks for". ---
cc_nominal_f = float(cc_nominal_w)
cctol_rows = []
for w_str in CC_TOL_WIDTHS:
    for rlabel in ["bcs", "wcs"]:
        sfx = f"cctol_{w_str}_ss_125c_r{rlabel}"
        lg = loopgain_metrics(f"{corners_dir}/loopgain_{sfx}_ac.csv")
        ps = psrr_metrics(f"{corners_dir}/psrr_{sfx}_ac.csv")
        row = {"cc_w": w_str,
               "cc_x_nominal": float(w_str) / cc_nominal_f,
               "corner": "ss", "temp_c": 125, "res_section": f"res_{rlabel}"}
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
                            ("pm_ok", "gm_ok", "psrr_1khz_ok", "psrr_100khz_ok"))
        cctol_rows.append(row)

cctol_fieldnames = [
    "cc_w", "cc_x_nominal", "corner", "temp_c", "res_section",
    "dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
    "phase_margin_deg", "gain_margin_db", "psrr_db_1khz", "psrr_db_100khz",
    "pm_ok", "gm_ok", "psrr_1khz_ok", "psrr_100khz_ok", "all_ok",
]
cctol_csv_out = csv_out.replace(".csv", ".cc-tolerance.csv")
with open(cctol_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cctol_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in cctol_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in cctol_fieldnames})

# --- Before / after / delta against the pinned baseline record ---
# "Before" is the baseline record named by BASELINE_CSV. From issue #35 that
# is the #31 record -- the first run against BOTH the PDK `rhigh` feedback
# divider (#28) and the full crossed resistor axis, and the run that found
# the res_bcs/125C phase-margin gap #35 exists to close. Because that record
# already carries one row per (corner, temperature, res_section), the
# comparison is like-for-like at every one of the 45 grid points: same
# benches, same PDK pin, same ngspice build, same resistor section on both
# sides, so the deltas isolate the compensation change and nothing else.
#
# (The #21/#25 records key on (corner, temperature) only -- they held the
# resistor axis at res_typ -- so pointing BASELINE_CSV back at one of them
# leaves the res_bcs/res_wcs "before" cells empty rather than silently
# comparing against the wrong section. That is the intended behaviour: a
# missing cell reads "n/a", it does not read as a zero delta.)
baseline = {}
if os.path.exists(baseline_csv):
    with open(baseline_csv) as f:
        for r in csv.DictReader(f):
            def _f(k):
                try:
                    return float(r[k])
                except (KeyError, TypeError, ValueError):
                    return None
            key = (r["corner"], r["temp_c"], r.get("res_section", "res_typ"))
            baseline[key] = {k: _f(k) for k in
                             ("dc_gain_db", "phase_margin_deg", "unity_gain_freq_hz",
                              "gain_margin_db", "psrr_db_1khz", "psrr_db_100khz",
                              "iq_a", "vout_no_load_v", "i_divider_a",
                              "line_reg_mv_per_v", "load_reg_pct",
                              "dropout_v_50ma")}

after = {(r["corner"], str(r["temp_c"]), r["res_section"]): r for r in main_rows}

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

delta_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        for rlabel in RES_LABELS:
            section = f"res_{rlabel}"
            b = baseline.get((corner, str(temp), section), {})
            a = after.get((corner, str(temp), section), {})
            for key, heading, unit, scale, dec, _hib in METRICS:
                bv, av = b.get(key), a.get(key)
                delta_rows.append({
                    "corner": corner, "temp_c": temp, "res_section": section,
                    "metric": key, "unit": unit, "before": bv, "after": av,
                    "delta": (av - bv) if (bv is not None and av is not None) else None,
                })

delta_fieldnames = ["corner", "temp_c", "res_section", "metric", "unit",
                    "before", "after", "delta"]
with open(delta_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=delta_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in delta_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in delta_fieldnames})

by_key = {}
for row in delta_rows:
    by_key.setdefault(row["metric"], []).append(row)


def fmt(v, scale, dec, signed=False):
    if v is None:
        return "n/a"
    s = f"{v * scale:+.{dec}f}" if signed else f"{v * scale:.{dec}f}"
    return s


# --- Divider attribution: same point, same resistor section, divider
# swapped back to the pre-#28 behavioural 300k pair. The difference is the
# conversion's OWN contribution, with Rz's corner spread common to both
# sides and therefore cancelled.
attr_rows = []
for corner in CORNERS:
    for temp in TEMPS:
        for rlabel in RES_LABELS:
            sfx = f"{corner}_{temp}c_r{rlabel}"
            beh = loopgain_metrics(f"{corners_dir}/loopgain_divattr_{sfx}_ac.csv")
            rh = after.get((corner, str(temp), f"res_{rlabel}"), {})
            row = {"corner": corner, "temp_c": temp, "res_section": f"res_{rlabel}"}
            for key in ("phase_margin_deg", "gain_margin_db", "dc_gain_db"):
                bv = (beh or {}).get(key)
                av = rh.get(key)
                row[f"{key}_behavioural_divider"] = bv
                row[f"{key}_rhigh_divider"] = av
                row[f"{key}_divider_delta"] = (av - bv) if (bv is not None and av is not None) else None
            attr_rows.append(row)

attr_fieldnames = ["corner", "temp_c", "res_section"]
for key in ("phase_margin_deg", "gain_margin_db", "dc_gain_db"):
    attr_fieldnames += [f"{key}_behavioural_divider", f"{key}_rhigh_divider",
                        f"{key}_divider_delta"]
attr_csv_out = delta_csv_out.replace(".delta.csv", ".divider-attribution.csv")
with open(attr_csv_out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=attr_fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in attr_rows:
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in attr_fieldnames})

with open(cmp_md_out, "w") as f:
    BASELINE_LABEL = os.path.basename(baseline_csv).replace(".csv", "")
    for key, heading, unit, scale, dec, _hib in METRICS:
        rows = by_key.get(key, [])
        deltas = [r["delta"] for r in rows if r.get("delta") is not None]
        worst = max(deltas, key=abs) if deltas else None
        f.write(f"\n### {heading} ({unit})\n\n")
        if deltas:
            f.write(f"Largest change across all {len(deltas)} compared points: "
                    f"**{fmt(worst, scale, dec, signed=True)} {unit}**.\n\n")
        f.write(f"| corner / temp / R corner | before (`{BASELINE_LABEL}`) "
                "| after (this run) | delta |\n")
        f.write("|---|---|---|---|\n")
        for row in rows:
            f.write(
                f"| `{row['corner']}` / {row['temp_c']}C / `{row['res_section']}` "
                f"| {fmt(row.get('before'), scale, dec)} "
                f"| {fmt(row.get('after'), scale, dec)} "
                f"| {fmt(row.get('delta'), scale, dec, signed=True)} |\n")

    # --- Cc value-tolerance window (issue #35 / DR-0005). ---
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
    # A width counts as passing only if EVERY row at that width passes --
    # one of the two binding sections failing is a failing width, not a
    # half-passing one.
    by_w = {}
    for r in cctol_rows:
        by_w.setdefault(r["cc_w"], []).append(r)
    ok_w = [w for w in CC_TOL_WIDTHS if all(r["all_ok"] for r in by_w.get(w, []))]
    bad_w = [w for w in CC_TOL_WIDTHS if w not in ok_w]
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

    # --- Mechanical spec comparison. Thresholds are the repo root README.md's
    # target table verbatim (issue #55 audit: only row 4, dropout, is
    # RATIFIED per DR-0007; every other comparison below is INFORMATIONAL
    # and never a requirement gate) (the same table sim/ldo-cmos5l-pvt-sweep's
    # own Results section is stated against), evaluated against EVERY point
    # in this run's grid. This is computed, not asserted in prose, so a
    # record can never claim a PASS its own CSV contradicts -- and so a
    # regression in a future run surfaces in the record itself rather than
    # relying on a reader re-deriving it from the CSV.
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

print(f"run_sweep.sh (post-process): wrote {len(main_rows)} main rows, "
      f"{len(sens_rows)} sensitivity rows, {len(cctol_rows)} Cc-tolerance rows, "
      f"{len(delta_rows)} delta rows, "
      f"{len(attr_rows)} divider-attribution rows")
