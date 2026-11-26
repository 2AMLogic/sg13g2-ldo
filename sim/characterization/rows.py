"""Grade each target-spec row using the validated characterization evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .common import (
    _METRIC_ORDER,
    DC_COND_LINE,
    DC_COND_LOAD,
    ROW5_ENV_COND,
    ROW5_LINE_GRADED,
    ROW5_LINE_LOADS,
    ROW5_LOAD_GRADED,
    ROW5_LOAD_VINS,
    ROW7_ENV_COND,
    ROW7_GRADED,
    ROW7_VINS,
    ROW_VERDICTS,
    GenError,
    _extreme,
    metric,
    num,
    read_csv,
    rnd,
    unavailable,
)
from .loaders import (
    DC_LOADS,
    DC_VINS,
    STARTUP_BAND_HI_V,
    STARTUP_MONOTONIC_TOL_V,
    STARTUP_SETTLE_LIMIT_S,
    _corner_id,
    _fmt_hz,
    startup_row_verdict,
)


@dataclass(frozen=True)
class RowContext:
    """Shared, already-validated inputs for the per-row graders.

    Built once by ``_row_context`` (the former setup block of ``build``): the
    selection-derived records, the PVT grid, the spec tables, the provenance
    list and the column readers. Each ``row_N_*`` function grades exactly one
    spec row over this context and returns its row dict.
    """
    root: Path
    sel: dict
    rec: dict
    dev: dict
    prow: list
    pid: list
    bc: dict
    ac_cond: dict
    R: dict
    dr_rel: str
    pvt_rel: str
    dc_rel: str
    dev_path: Path
    evidence_state: str
    stale: bool
    fresh_checks: list
    sources: list          # appended by _row_context; graders never mutate it
    dcev: dict
    su: dict
    r10: dict
    r7: dict
    r5: dict | None
    ccw: dict
    cc_tol_rel: str
    col: Callable[[str], list]
    dc_col: Callable[..., tuple]


def _make_row(rdef, metrics, coverage_state, gaps, evidence, dr_rel,
              stretch_note=None, row_verdict=None, notes=None) -> dict:
    """Assemble one report row (the former ``add`` closure of ``build``).

    Verdict derivation is shared by every row: worst metric verdict wins, a
    pass becomes full/partial coverage from the coverage state, and an
    explicit ``row_verdict`` overrides both."""
    mv = [m["verdict"] for m in metrics]
    if row_verdict is None:
        worst = min(mv, key=lambda v: _METRIC_ORDER[v])
        if worst == "pass":
            row_verdict = ("pass_full_coverage" if coverage_state == "full"
                           else "pass_partial_coverage")
        else:
            row_verdict = worst
    assert row_verdict in ROW_VERDICTS
    return {
        **{k: rdef[k] for k in ("id", "parameter", "target", "stretch")},
        "ratification": {
            "state": rdef["ratification"], "readme_status": rdef["readme_status"],
            "dr0007_disposition": rdef["dr0007_disposition"],
            "dr0007_type": rdef["dr0007_type"], "record": dr_rel},
        "verdict": row_verdict,
        "evidence_state": evidence,
        "coverage": {"state": coverage_state, "gaps": gaps},
        "metrics": metrics,
        "stretch_note": stretch_note,
        "notes": notes or [],
    }


def row_1_input(ctx: RowContext) -> dict:
    """Row 1, Input: bare-device context only -- no closed-loop evaluation of
    the input window exists."""
    drows = read_csv(ctx.dev_path)
    if not drows:
        raise GenError("bare-device screening csv is empty")
    vsg = [num(r, "vsg_stress_v", "screening") for r in drows]
    n_exceed = sum(1 for r in drows if r.get("vsg_exceeds_3p3v_rating") == "YES")
    dev_rel = ctx.dev["files"]["screening_csv"]["path"]
    return _make_row(ctx.R[1], [
        unavailable("closed-loop input-range operation (3.3 V +/-10 %)", "V",
                    "not_measured",
                    "No committed closed-loop record evaluates the input window as a row "
                    "(no |Vgs| check in normal regulation; no current limiter exists to "
                    "hold |Vsg| <= 3.3 V at Vin = 3.63 V under a short -- DR-0001 gate "
                    "carried in DR-0007 row 1)."),
        {"name": "bare pass-device |Vsg| stress at Vin = 3.63 V (device context, NOT a circuit measurement)",
         "unit": "V", "verdict": "not_measured",
         "context_only": True,
         "device_context": {"max_vsg_stress_v": rnd(max(vsg)), "n_device_points": len(drows),
                            "n_exceeding_3p3v_rating": n_exceed,
                            "branch": "SG13G2 bare-device screen (open-loop, no regulator)"},
         "reason": "Bare-device screening is separate from closed-loop evidence and cannot "
                   "substitute for it; recorded only to show the gate the row carries.",
         "source": {"record": dev_rel, "column": "vsg_stress_v, vsg_exceeds_3p3v_rating"}},
    ], "none", [
        "no closed-loop evaluation of the input window",
        "DR-0001 |Vsg| <= 3.3 V gate at Vin = 3.63 V needs a current limiter that does not exist",
    ], "bare_device_only", ctx.dr_rel)


def row_2_output(ctx: RowContext) -> dict:
    """Row 2, Output: no-load VOUT against the +/-2 % window."""
    vo = ctx.col("vout_no_load_v")
    lo, hi = 1.8 * 0.98, 1.8 * 1.02
    m_lo = metric("VOUT no load, lower bound 1.8 V -2 %", "V", "ge", rnd(lo),
                  "vout_no_load_v", ctx.pvt_rel, vo, ctx.bc["dc_iq_and_vout"])
    m_hi = metric("VOUT no load, upper bound 1.8 V +2 %", "V", "le", rnd(hi),
                  "vout_no_load_v", ctx.pvt_rel, vo, ctx.bc["dc_iq_and_vout"])
    m_lo["observed_range"] = {"min": rnd(min(v for v, _ in vo)), "max": rnd(max(v for v, _ in vo))}
    return _make_row(ctx.R[2], [m_lo, m_hi], "partial", [
        "corner grid only: error-amp offset and divider mismatch are statistical and unexercised (Monte Carlo missing, #56)",
        "ideal 0.90 V reference: measures the regulator only, excluding reference error",
    ], ctx.evidence_state, ctx.dr_rel,
        stretch_note="programmable variants deferred; no evidence")


def row_3_load(ctx: RowContext) -> dict:
    """Row 3, Load: DC regulation at 50 mA; no 0 mA dynamic evidence."""
    v50 = ctx.col("vout_at_vinmax_50ma_v")
    lo, hi = 1.8 * 0.98, 1.8 * 1.02
    m3lo = metric("VOUT at 50 mA, lower bound 1.8 V -2 %", "V", "ge", rnd(lo),
                  "vout_at_vinmax_50ma_v", ctx.pvt_rel, v50, "50 mA load, Vin = 3.63 V (record md: dcsweep bench)")
    m3hi = metric("VOUT at 50 mA, upper bound 1.8 V +2 %", "V", "le", rnd(hi),
                  "vout_at_vinmax_50ma_v", ctx.pvt_rel, v50, "50 mA load, Vin = 3.63 V (record md: dcsweep bench)")
    row = _make_row(ctx.R[3], [m3lo, m3hi,
                               unavailable("dynamic behaviour at 0 mA (no external preload)", "A", "not_measured",
                                           "AC loop-gain and PSRR benches run at 1 mA only; no 0 mA dynamic evidence.")],
                    "partial", [
                        "DC regulation at 50 mA only checked here at Vin = 3.63 V",
                        "no 0 mA dynamic/stability evidence",
                        "100 mA stretch has no evidence",
                    ], ctx.evidence_state, ctx.dr_rel, stretch_note="100 mA: no evidence")
    # row verdict for 3: a not_measured metric blocks full pass but the
    # measured DC part passes -> partial. Recompute explicitly.
    row["verdict"] = ("fail" if "fail" in (m3lo["verdict"], m3hi["verdict"])
                      else "pass_partial_coverage")
    return row


def row_4_dropout(ctx: RowContext) -> dict:
    """Row 4, Dropout at 50 mA, with floor-censored points kept as bounds."""
    dv = ctx.col("dropout_v_50ma")
    fl = ctx.col("dropout_v_50ma_floor")
    cens = {i for i in range(len(dv)) if dv[i][0] <= fl[i][0] + 1e-12}
    m4 = metric("dropout at 50 mA", "V", "lt", 0.3, "dropout_v_50ma", ctx.pvt_rel, dv,
                ctx.bc["dropout"], censored=cens,
                note="Values equal to the sweep floor are censored: the true dropout is <= the "
                     "reported value. For a '<' target an upper bound that already satisfies the "
                     "bound is sufficient; the worst case is an exact (uncensored) measurement.")
    m4["censored_points_floor_v"] = rnd(fl[0][0])
    if m4["worst_case"] and any(
            m4["worst_case"]["at"] == ctx.pid[i] for i in cens):
        m4["worst_case_is_censored"] = True
    else:
        m4["worst_case_is_censored"] = False
    n_over_stretch = sum(1 for v, _ in dv if v > 0.2 + 1e-12)
    return _make_row(ctx.R[4], [m4], "full", [], ctx.evidence_state, ctx.dr_rel,
                     stretch_note=f"stretch < 200 mV is NOT ratified and is not demonstrated: {n_over_stretch} of "
                                  f"{len(dv)} points exceed 0.20 V; {len(cens)} points are censored at the floor "
                                  f"so cannot demonstrate a strict '< 0.20 V'.")


def row_5_regulation(ctx: RowContext) -> dict:
    """Row 5, Line / load regulation: legacy record columns plus the derived
    per-load / per-supply informational DC series."""
    lr = ctx.col("line_reg_mv_per_v")
    ld = ctx.col("load_reg_pct")
    not_in_reg = {i for i, r in enumerate(ctx.prow) if r["line_reg_in_regulation"] != "True"}
    m5a = metric("line regulation, legacy record column (no load)", "mV/V", "lt", 5.0,
                 "line_reg_mv_per_v", ctx.pvt_rel, lr, ctx.bc["line_regulation"], ambiguous=not_in_reg)
    m5b = metric("load regulation, legacy record column (Vin = 3.63 V)", "%", "lt", 1.0,
                 "load_reg_pct", ctx.pvt_rel, ld, ctx.bc["load_regulation"])
    m5 = [m5a, m5b]
    dc_note = ("Informational DC summary (derived offline from the committed raw DC grids, "
               "no new simulation). A point is valid only if both end points are within 1 % of "
               "1.8 V; invalid points are counted as ambiguous and never dropped. Discrete "
               "sampled loads/supplies only: not a continuous-window claim.")
    for key, label in DC_LOADS:
        pts, bad = ctx.dc_col(f"line_reg_mv_per_v_{key}", valid=f"line_reg_valid_{key}")
        m = metric(f"line regulation at {label} load (Vin 2.97-3.63 V)", "mV/V", "lt", 5.0,
                   f"line_reg_mv_per_v_{key}", ctx.dc_rel, pts, DC_COND_LINE, ambiguous=bad, note=dc_note)
        m["n_invalid"] = len(bad)
        m5.append(m)
    for key, label in DC_VINS:
        pts, bad = ctx.dc_col(f"load_reg_pct_vin{key}", valid=f"load_reg_valid_vin{key}")
        m = metric(f"load regulation 0-50 mA at Vin = {label}", "%", "lt", 1.0,
                   f"load_reg_pct_vin{key}", ctx.dc_rel, pts, DC_COND_LOAD, ambiguous=bad, note=dc_note)
        m["n_invalid"] = len(bad)
        m5.append(m)
    r5 = ctx.r5
    gaps5 = []
    if r5 is None:
        # No graded record is selected: say so, give the row no envelope credit.
        m5.append(unavailable(
            "line and load regulation, graded `klt sim` envelope", "mV/V, %", "not_measured",
            "No row-5 graded `klt sim` envelope is selected in selection.json; the legacy and "
            "offline DC figures above stay informational and earn no envelope credit.",
            source={"selection": "sim/characterization/selection.json"}))
        gaps5.append("no graded `klt sim` envelope record selected for row 5 (line and load regulation)")
    else:
        by_point5: dict = {}
        for (cid, n), v in r5["values"].items():
            by_point5.setdefault(cid, {})[n] = v
        load_lbl = {"i0": "0 mA", "i25m": "25 mA", "i50m": "50 mA"}
        vin_lbl = {"v2v97": "2.97", "v3v30": "3.30", "v3v63": "3.63"}
        note5 = ("graded by `klt sim` (derived-expr measurement, limit inside the request; the "
                 "verdict is the tool's own, strictness enforced here because the tool's `max` "
                 "is inclusive). Solver convergence setting (NOT an error bound): "
                 f"{r5['summary']['solver_convergence_setting_note']}. "
                 "Qualifications: " + "; ".join(r5["summary"]["qualifications"]) + ".")
        pts_line, pts_load = [], []
        for i, prow_row in enumerate(ctx.prow):
            cid = _corner_id(prow_row)
            for ln in ROW5_LINE_LOADS:
                at = dict(ctx.pid[i])
                at["load"] = load_lbl[ln]
                pts_line.append((by_point5[cid][f"line_{ln}_mvpv"], at))
            for vn in ROW5_LOAD_VINS:
                at = dict(ctx.pid[i])
                at["vin_v"] = vin_lbl[vn]
                pts_load.append((by_point5[cid][f"load_{vn}_pct"], at))
        m5.append(metric("graded `klt sim` envelope: line regulation at 0 / 25 / 50 mA "
                         "(Vin 2.97-3.63 V)", "mV/V", "lt", 5.0, ", ".join(ROW5_LINE_GRADED),
                         r5["report_rel"], pts_line, ROW5_ENV_COND, note=note5))
        m5.append(metric("graded `klt sim` envelope: load regulation 0-50 mA at Vin = "
                         "2.97 / 3.30 / 3.63 V", "%", "lt", 1.0, ", ".join(ROW5_LOAD_GRADED),
                         r5["report_rel"], pts_load, ROW5_ENV_COND, note=note5))
    return _make_row(ctx.R[5], m5, "partial", gaps5 + [
        "line regulation sampled at 5 discrete loads (0, 12.5, 25, 37.5, 50 mA) over Vin 2.97-3.63 V; "
        "load regulation sampled at 3 discrete supplies (2.97, 3.30, 3.63 V) -- not continuous coverage of the window",
        "'inside the accuracy window' (coupling with the statistical VOUT row, #56) not covered for either metric",
        "ideal 0.90 V reference: reference error is excluded; corner grid only, no Monte Carlo",
    ], ctx.evidence_state, ctx.dr_rel)


def row_6_psrr(ctx: RowContext) -> dict:
    """Row 6, PSRR at the single recorded AC condition."""
    p1 = ctx.col("psrr_db_1khz")
    p100 = ctx.col("psrr_db_100khz")
    m6a = metric("PSRR @ 1 kHz", "dB", "gt", 50.0, "psrr_db_1khz", ctx.pvt_rel, p1, ctx.ac_cond)
    m6b = metric("PSRR @ 100 kHz", "dB", "gt", 20.0, "psrr_db_100khz", ctx.pvt_rel, p100, ctx.ac_cond)
    n_s = sum(1 for v, _ in p1 if v <= 60.0)
    return _make_row(ctx.R[6], [m6a, m6b], "partial", [
        "single AC condition: Vin = 3.30 V, 1 mA, 1 uF, ESR 0 -- not 50 mA, not the Cout/ESR window",
        "Cc is un-cornered (MoM-cap model has no corner spread; record labels PSRR insufficient-evidence)",
    ], ctx.evidence_state, ctx.dr_rel,
        stretch_note=f"stretch > 60 dB @ 1 kHz not met: {n_s} of {len(p1)} points are <= 60 dB; stretch is not ratified.",
        notes=[f"Cc value tolerance (ss/125C only, {ctx.cc_tol_rel}): all of PM, GM and PSRR rows hold for "
               f"Cc in x{ctx.ccw['low_x_nominal']}..x{ctx.ccw['high_x_nominal']} of nominal."])


def row_7_iq(ctx: RowContext) -> dict:
    """Row 7, Iq: the legacy no-load column plus the graded `klt sim` envelope
    (issue #317), whose six limits-bearing derived measurements make the
    per-corner and whole-matrix verdict the tool's own at both load states
    over the full supply window."""
    iq = ctx.col("iq_a")
    iq_uA = [(v * 1e6, p) for v, p in iq]
    m7 = metric("Iq, no load (legacy record column, Vin = 3.30 V)", "uA", "lt", 30.0,
                "iq_a", ctx.pvt_rel, iq_uA, ctx.bc["dc_iq_and_vout"],
                note="column iq_a is in A; converted to uA (x1e6) for the row's unit. "
                     "Superseded by the graded envelope metrics below at the other "
                     "supplies; kept for continuity with the DR-0007 evidence base.")
    sup = ctx.sel["superseded_evidence"][0]

    # The graded envelope: 45 corners x 3 Vin x 2 load states, values in A.
    r7 = ctx.r7
    vin_labels = {vn: f"{vv:.2f}" for vn, vv in ROW7_VINS}
    by_point: dict = {}
    for (cid, n), v in r7["values"].items():
        by_point.setdefault(cid, {})[n] = v
    env_metrics = []
    for family, label, cond_extra in (
            ("i0", "Iq, no load (graded `klt sim` envelope, Vin 2.97-3.63 V)",
             "the verdict cited here is `klt sim`'s own (limits inside the request)"),
            ("i50m", "Iq at full load (50 mA), load current excluded (graded `klt sim` "
             "envelope, Vin 2.97-3.63 V)",
             "the difference is a derived-expr measurement inside ngspice, never an "
             "offline subtraction")):
        pts = []
        for i, prow_row in enumerate(ctx.prow):
            cid = _corner_id(prow_row)
            for vn, _vv in ROW7_VINS:
                n = f"iq_{family}_{vn}_a"
                at = dict(ctx.pid[i])
                at["vin_v"] = vin_labels[vn]
                pts.append((by_point[cid][n] * 1e6, at))
        cond = ROW7_ENV_COND + "; " + cond_extra
        m = metric(label, "uA", "lt", 30.0, ", ".join(n for n in ROW7_GRADED
                                                      if f"_{family}_" in n),
                   r7["report_rel"], pts, cond,
                   note="values in A in the envelope, converted to uA (x1e6). "
                        "Solver convergence setting (NOT an error bound): "
                        f"{r7['summary']['solver_convergence_setting_note']}. "
                        "Observed solver sensitivity, a measurement over its stated "
                        f"coverage and not a bound: re-solving all {r7['pair']['pairs_compared']} "
                        "(corner, graded figure) pairs at "
                        f"reltol={r7['pair']['tight_options']['reltol']:g} "
                        f"abstol={r7['pair']['tight_options']['abstol']:g} changed "
                        f"the largest figure by {r7['pair']['max_abs_delta_a']:.3g} A "
                        f"({r7['pair']['max_abs_delta_ua']:.3g} uA; "
                        f"{r7['pair']['coverage']}). "
                        "An older record's full-load figure "
                        f"({sup['quoted_substring']}) is on a superseded design and is NOT used.")
        env_metrics.append(m)
    mnl, mfl = env_metrics
    mfl["superseded_statement"] = {"source": sup["statement_source"], "describes": sup["describes"]}
    row = _make_row(ctx.R[7], [m7, mnl, mfl], "full", [], ctx.evidence_state, ctx.dr_rel,
                    stretch_note=f"stretch < 10 uA not met: max observed no-load Iq "
                                 f"{m7['worst_case']['value']:.4g} uA, max graded no-load "
                                 f"{mnl['worst_case']['value']:.4g} uA, max graded full-load "
                                 f"{mfl['worst_case']['value']:.4g} uA.",
                    notes=list(r7["summary"]["exclusions"]) + [
                        "graded by `klt sim` with limits inside the request; the row "
                        "stays Open under DR-0007 -- this is a measurement against the "
                        "draft target, not a ratification",
                    ])
    row["verdict"] = ("fail" if "fail" in (m7["verdict"], mnl["verdict"], mfl["verdict"])
                      else "ambiguous" if "ambiguous" in (mnl["verdict"], mfl["verdict"])
                      else "pass_full_coverage")
    return row


def row_8_current_limit(ctx: RowContext) -> dict:
    """Row 8, Current limit: no limiter exists in the design."""
    return _make_row(ctx.R[8], [
        unavailable("current limit window", "mA", "not_implemented",
                    "No current limiter in the design; record md lists current limit as 'not implemented'.",
                    source={"record": ctx.rec["files"]["record_md"]["path"]})],
        "none", ["no limiter exists; statistical row (DR-0007) cannot be graded until one does"],
        "none", ctx.dr_rel)


def row_9_startup(ctx: RowContext) -> dict:
    """Row 9, Startup: the explicitly selected measured campaign (proposed
    methodology, DR-0009); measured failures are failures, missing or
    insufficient points are never passes."""
    su = ctx.su
    sp = su["points"]
    ev = [p for p in sp if p["verdict"] != "insufficient"]
    bad_idx = {i for i, p in enumerate(sp) if p["verdict"] == "insufficient"}
    startup_cond = ("EN-bearing core (DR-0008), EN = VIN * CTL step at t = 1 ms, schematic level; "
                    "grid process {tt,ss,ff,sf,fs} x temperature {-40,27,125} C x resistor corner "
                    "{typ,bcs,wcs} x Vin {2.97,3.30,3.63} V; resistive load 1 mA (1.8 kohm), Cout 1 uF, "
                    "ESR 0, Cc nominal; ideal 0.90 V reference; 135 requested points. Time zero is the "
                    "EN = VIN/2 crossing; PROPOSED methodology (DR-0009), not ratified")

    def st_pts(col, *, settle=False):
        out = []
        for p in sp:
            if p["verdict"] == "insufficient":
                out.append((0.0, p["id"]))
            elif settle and not p["settled"]:
                # never settled in the window: the observation length is a lower bound
                out.append((p["start_observed_s"], p["id"]))
            else:
                out.append((p[col], p["id"]))
        return out

    su_rel = su["csv_rel"]
    contradictions: list = []

    def st_metric(name, bound, col, *, settle=False, note=None):
        series = st_pts(col, settle=settle)
        for (v, pid_), p in zip(series, sp):
            if p["verdict"] == "pass" and not v <= bound:
                contradictions.append(f"{pid_['corner']}/{pid_['temp_c']}C/{pid_['res_section']}/"
                                      f"{pid_['vin_v']}V: {name}")
        return metric(name, "s" if settle else "V", "le", bound, col, su_rel, series,
                      startup_cond, ambiguous=bad_idx, note=note)

    st_metrics = [
        st_metric("start: settle time into the +/-2 % band (3 ms limit)", STARTUP_SETTLE_LIMIT_S,
                  "start_settle_time_s", settle=True,
                  note="Numeric settling success does not override the monotonicity and overshoot "
                       "metrics below; each is scored independently and any failure fails the row. A point "
                       "that never settled is scored at its observation length (a lower bound)."),
        st_metric("start: peak VOUT above the +2 % band edge (overshoot, proposed bound 1.836 V)",
                  STARTUP_BAND_HI_V, "start_peak_vout_v"),
        st_metric("start: max downward excursion before settling (monotonicity, proposed 1 mV tolerance)",
                  STARTUP_MONOTONIC_TOL_V, "start_max_down_excursion_v"),
        st_metric("re-enable: peak VOUT above the +2 % band edge (proposed bound 1.836 V)",
                  STARTUP_BAND_HI_V, "reen_peak_vout_v"),
        st_metric("re-enable: max downward excursion (proposed 1 mV tolerance)",
                  STARTUP_MONOTONIC_TOL_V, "reen_max_down_excursion_v"),
    ]
    # A csv `pass` contradicted by a measured metric means the pinned record
    # and its own metrics disagree: never repaired, never reported as a pass.
    if contradictions:
        raise GenError("startup csv verdict pass contradicts a measured metric at "
                       + "; ".join(contradictions[:3]))
    n_metric_fail = sum(m["n_fail"] for m in st_metrics)
    st_verdict = startup_row_verdict(su["n_fail"] or n_metric_fail, su["n_insufficient"],
                                     len(su["missing"]), len(ev))
    reason_counts: dict = {}
    for q in sp:
        for part in [x.strip() for x in q["reasons"].split("|") if x.strip()]:
            words = part.split()
            key = words[0] + (" " + words[1] if len(words) > 1 and not words[1][0].isdigit() else "")
            reason_counts[key] = reason_counts.get(key, 0) + 1
    st_state = "stale_against_design" if su["stale_components"] else "current"
    n_settled = sum(1 for p in ev if p["settled"] and p["start_settle_time_s"] <= STARTUP_SETTLE_LIMIT_S)
    n_settled_and_failing = sum(1 for p in ev if p["settled"] and p["start_settle_time_s"] <= STARTUP_SETTLE_LIMIT_S
                                and p["verdict"] == "fail")
    startup_summary = {
        "record_id": su["rid"], "stage": su["cfg"]["stage"],
        "requested_points": su["n_requested"], "result_rows": len(sp),
        "evaluated_points": len(ev), "missing_points": len(su["missing"]),
        "insufficient_points": su["n_insufficient"],
        "csv_verdicts": {"pass": su["n_pass"], "fail": su["n_fail"], "insufficient": su["n_insufficient"]},
        "settled_within_3ms_points": n_settled,
        "settled_within_3ms_but_failing_points": n_settled_and_failing,
        "failure_reasons_point_counts": dict(sorted(reason_counts.items())),
        "missing": su["missing"],
        "design_freshness": {"state": st_state, "stale_components": su["stale_components"],
                             "basis": su["cfg"]["design_freshness_basis"], "components": su["fresh"]},
        "proposed_methodology": su["cfg"]["proposed_methodology"],
        "ratification": "none inferred: row 9 stays Open (DR-0007); proposed methodology only",
        "extrema": {},
        "campaign_provenance": {k: su["manifest"].get(k) for k in
                                ("engines", "runner_klt", "client_klt", "pdk_pinned_commit", "pdk_installed_commit")},
        "source": {"record_md": su["md_rel"], "csv": su_rel},
    }
    for ccol, label in (("start_overshoot_v", "start overshoot above 1.8 V [V]"),
                        ("start_peak_vout_v", "start peak VOUT [V]"),
                        ("start_settle_time_s", "start settle time [s]"),
                        ("start_max_down_excursion_v", "start max downward excursion [V]"),
                        ("reen_overshoot_v", "re-enable overshoot [V]"),
                        ("reen_max_down_excursion_v", "re-enable max downward excursion [V]")):
        vals = [(q[ccol], q["id"]) for q in ev if ccol in q]
        if vals:
            startup_summary["extrema"][label] = {"min": _extreme(vals, "min"), "max": _extreme(vals, "max")}
    row = _make_row(ctx.R[9], st_metrics, "partial", [
        "proposed methodology (DR-0009) only; the target's 'controlled ramp' has no numeric bound and is not graded",
        "one load/Cout/ESR point only: 1 mA, 1 uF, 0 ohm ESR -- not 0-50 mA, 0.33-4.7 uF, 0-500 mohm",
        "Vin grid is 2.97/3.30/3.63 V; Cc and the 0.90 V reference are not cornered; schematic level, no post-layout evidence",
    ] + ([f"{len(su['missing'])} requested point(s) missing and {su['n_insufficient']} insufficient of "
          f"{su['n_requested']}"] if su["missing"] or su["n_insufficient"] else []), st_state, ctx.dr_rel,
        row_verdict=st_verdict,
        notes=[f"Measured: {len(ev)} of {su['n_requested']} requested points evaluated, "
               f"{su['n_fail']} fail, {su['n_pass']} pass, {su['n_insufficient']} insufficient, "
               f"{len(su['missing'])} missing ({su_rel}). {n_settled_and_failing} of {n_settled} points "
               "that settle within 3 ms still fail the proposed overshoot / monotonicity checks.",
               "Proposed methodology, not ratified: DR-0007 row 9 stays Open; no ratification and no whole-spec pass is inferred."])
    row["startup_campaign"] = startup_summary
    return row


def row_10_stability(ctx: RowContext) -> dict:
    """Row 10, Stability: DR-0014 (proposed) classification of the committed
    traces.

    Verdict-bearing PM/GM come from the pinned offline classification of THIS
    record's own loop-gain traces (load_row10). The pre-DR-0014 first-crossing
    reading is kept beside it as superseded context, never as a verdict."""
    prow = ctx.prow
    r10 = ctx.r10
    pid = ctx.pid
    multi = [i for i, r in enumerate(prow) if int(num(r, "n_0db_crossings", "pvt")) != 1]
    pm_pts, gm_pts, pm_amb, gm_amb, rows10 = [], [], set(), set(), []
    for i, r in enumerate(prow):
        cr, pmv, gmv = r10["by_key"][(r["corner"], r["temp_c"], r["res_section"])]
        rows10.append(cr)
        pm_pts.append((pmv if pmv is not None else 0.0, pid[i]))
        gm_pts.append((gmv if gmv is not None else 0.0, pid[i]))
        if cr["pm_verdict"] == "ambiguous":
            pm_amb.add(i)
        if cr["gm_verdict"] == "ambiguous":
            gm_amb.add(i)

    def later_margins(cr):
        return [float(x.split("@")[2]) for x in cr["zero_db_crossings_hz_dir_margin_deg"].split(";")[1:]]

    def rng(vals):
        return {"min": rnd(min(vals)), "max": rnd(max(vals))} if vals else None

    def reasons(key):
        out: dict = {}
        for cr in rows10:
            k = cr[key] or "(none)"
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    ceil_g = [num(cr, "ceiling_gain_db", "row10") for cr in rows10]
    ceil_d = [num(cr, "ceiling_last_decade_change_db", "row10") for cr in rows10]
    n_bounded = sum(1 for cr in rows10 if cr["ceiling_bounded"] == "True")
    n_low_ok = sum(1 for cr in rows10 if cr["low_end_ok"] == "True")
    r10_rel = r10["csv_rel"]
    ceil_txt = _fmt_hz(r10["ceiling_hz"])
    r10_cond = (ctx.ac_cond + f"; loop-gain trace 1 Hz-{ceil_txt}, 20 points/decade (the committed bench's sweep "
                "floor and ceiling); PROPOSED classification (DR-0014), not ratified")
    ceil_dir = ("rising" if min(ceil_d) > 0 else "falling" if max(ceil_d) < 0 else "mixed")
    pm_first = [num(r, "phase_margin_deg", "pvt") for r in prow]
    gm_first = [num(r, "gain_margin_db", "pvt") for r in prow]
    m10a = metric("phase margin, DR-0014: minimum over every 0 dB crossing in the sweep", "deg", "ge", 45.0,
                  "pm_deg", r10_rel, pm_pts, r10_cond, ambiguous=pm_amb,
                  note="Per-crossing margin = angular distance of the crossing phase from the critical point "
                       "(180 deg mod 360), signed negative after an in-band encirclement. A miss inside the "
                       "sweep is a fail; a pass also needs a bounded sweep ceiling (loop gain <= -10 dB and "
                       "non-increasing over the last decade) and a sample bracket clear of the bound. Anything "
                       "else stays ambiguous with its reason.")
    m10a["reasons"] = reasons("pm_reasons")
    m10a["detail"] = [
        f"sweep ceiling bounded at {n_bounded} of {len(prow)} points: loop gain at {ceil_txt} "
        f"{min(ceil_g):.4g}..{max(ceil_g):.4g} dB, change over the last decade {min(ceil_d):+.4g}..{max(ceil_d):+.4g} dB "
        f"({ceil_dir}); low-end premise holds at {n_low_ok} of {len(prow)}",
        f"{len(multi)} points have two 0 dB crossings: first-crossing margin "
        f"{min(pm_first[i] for i in multi):.4g}..{max(pm_first[i] for i in multi):.4g} deg, second (rising) crossing "
        f"{min(m for i in multi for m in later_margins(rows10[i])):.4g}..{max(m for i in multi for m in later_margins(rows10[i])):.4g} deg "
        f"from the critical point; the record's phase_margin_worst_deg "
        f"({min(num(prow[i], 'phase_margin_worst_deg', 'pvt') for i in multi):.4g}..{max(num(prow[i], 'phase_margin_worst_deg', 'pvt') for i in multi):.4g}) "
        "is 180 + unwrapped phase, not a margin" if multi else "no point has more than one 0 dB crossing",
        f"superseded first-crossing reading (pre-DR-0014, not a verdict): {sum(1 for i, v in enumerate(pm_first) if i not in multi and v >= 45.0)} "
        f"of {len(prow)} scored >= 45 deg, {len(multi)} unscored; range {min(pm_first):.4g}..{max(pm_first):.4g} deg",
    ]
    m10b = metric("gain margin, DR-0014: minimum over every -180 deg crossing in the sweep", "dB", "ge", 10.0,
                  "gm_db", r10_rel, gm_pts, r10_cond, ambiguous=gm_amb,
                  note="A trace with no -180 deg crossing is never scored as a miss or as infinite margin: it "
                       "passes only with a bounded sweep ceiling, which bounds the margin above the ceiling "
                       "below by -(loop gain at the ceiling) >= 10 dB.")
    m10b["reasons"] = reasons("gm_reasons")
    m10b["detail"] = [
        f"superseded first -180 deg crossing reading (pre-DR-0014, not a verdict): {sum(1 for v in gm_first if v >= 10.0)} "
        f"of {len(prow)} >= 10 dB, range {min(gm_first):.4g}..{max(gm_first):.4g} dB; no committed trace bounds the "
        f"sweep ceiling ({ceil_txt}), so none of these is a pass under DR-0014",
    ]
    row = _make_row(ctx.R[10], [m10a, m10b], "partial", [
        "one (Cout, ESR, load) point only: 1 uF, 0 ohm, 1 mA -- not 0.33-4.7 uF, 0-500 mohm, 0-50 mA",
        "Cc is un-cornered; Cc tolerance checked at ss/125C only",
        f"sweep ceiling {ceil_txt} bounded at {n_bounded} of {len(prow)} points (loop gain {min(ceil_g):.3g}..{max(ceil_g):.3g} dB "
        f"and {ceil_dir} at the ceiling): no PM or GM pass can be scored under DR-0014 until a bench bounds the "
        f"loop gain above {ceil_txt}",
        f"{len(multi)} of {len(prow)} points have two 0 dB crossings",
    ], ctx.evidence_state, ctx.dr_rel,
        notes=[f"Cc value tolerance (ss/125C only, {ctx.cc_tol_rel}): PM, GM and PSRR all hold for Cc in "
               f"x{ctx.ccw['low_x_nominal']}..x{ctx.ccw['high_x_nominal']} of nominal (first-crossing reading, pre-DR-0014).",
               f"PM/GM verdicts follow the PROPOSED margin classification {r10['dr']} applied offline to the "
               f"committed traces ({r10_rel}); row 10 stays Open (DR-0007) and nothing is ratified."])
    row["margin_classification"] = {
        "decision_record": r10["dr"], "status": "proposed", "source": r10_rel,
        "points": len(prow), "low_end_premise_holds": n_low_ok, "ceiling_bounded": n_bounded,
        "ceiling_gain_db_range": rng(ceil_g), "ceiling_last_decade_change_db_range": rng(ceil_d),
        "multi_crossing_points": len(multi),
        "sweep_ceiling_hz": r10["ceiling_hz"],
    }
    return row
