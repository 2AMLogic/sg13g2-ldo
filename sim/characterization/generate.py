#!/usr/bin/env python3
"""Aggregate per-spec-row characterization report + klt generic envelope (T1 item 8).

Offline, stdlib-only, deterministic. Reads ONLY committed files (no PDK, no
simulator, no network, no git): the explicitly selected sim records named in
``selection.json``, the README target table, and DR-0007. Writes three files
next to this script:

  characterization-report.json   canonical aggregate (machine-readable)
  characterization-report.md     the same content rendered for humans
  characterization-envelope.json klt ``kind: generic`` envelope for item 8

Cold start (any clean checkout, python3 >= 3.9, nothing else installed):

  python3 sim/characterization/generate.py          # (re)generate
  python3 sim/characterization/generate.py --check  # CI: regenerate in memory,
                                                    # fail on any drift/error

What the envelope verdict means
-------------------------------
``status: pass`` means ONE thing: the characterization ARTIFACT is complete and
fresh -- every target-spec row appears exactly once with an explicit state,
every selected source file exists and matches its pinned hash, the grid is
whole, and the selected record is current against the design netlists. It does
NOT mean the circuit meets its spec: rows that honestly measure as failing,
ambiguous, unmeasured or unimplemented are listed as such inside a "pass"
artifact. ``status: fail`` means the artifact itself is incomplete or stale.
klt's generic grader trusts this verdict and never reads the report, so this
generator (and the ``--check`` CI gate) is where the content is verified.

Error discipline: any generator error (missing record, hash mismatch, bad
numeric field, malformed table) prints the reason, rewrites the envelope as
``status: fail`` with no provenance, and exits non-zero -- a previously
committed passing envelope is never left standing next to a failed run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import traceback
from pathlib import Path

GENERATOR_VERSION = 1
HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent

REPORT_JSON = "characterization-report.json"
REPORT_MD = "characterization-report.md"
ENVELOPE_JSON = "characterization-envelope.json"

# Row identities and the exact target text the thresholds below were written
# against. If the README target text changes the generator refuses to run: a
# target edit is a spec change and the thresholds here must be reviewed.
EXPECTED_ROWS = [
    ("Input", "3.3 V ±10% — confirm against SG13G2 device flavors"),
    ("Output", "1.8 V ±2% (fixed)"),
    ("Load", "0–50 mA (no external preload assumed)"),
    ("Dropout @ 50 mA", "< 300 mV worst corner"),
    ("Line / load regulation", "< 5 mV/V; < 1% over full load, inside the accuracy window"),
    ("PSRR", "> 50 dB @ 1 kHz, > 20 dB @ 100 kHz"),
    ("Iq (excluding load)", "< 30 µA at no load and at full load"),
    ("Current limit", "65–80 mA brickwall over PVT; short-survivable"),
    ("Startup", "monotonic, controlled ramp, inside ±2% within 3 ms of enable"),
    ("Stability", "0–50 mA, C_out 0.33–4.7 µF effective, ESR 0–500 mΩ; PM ≥ 45°, GM ≥ 10 dB worst corner"),
]

ROW_VERDICTS = (
    "fail",
    "ambiguous",
    "not_implemented",
    "not_measured",
    "pass_partial_coverage",
    "pass_full_coverage",
)
# Row verdict ordering for "worst wins" when aggregating metric verdicts.
_METRIC_ORDER = {v: i for i, v in enumerate(
    ["fail", "ambiguous", "not_implemented", "not_measured", "pass"])}

CORNERS = ["tt", "ss", "ff", "sf", "fs"]
TEMPS = [-40, 27, 125]
RES = ["res_typ", "res_bcs", "res_wcs"]

PVT_NUMERIC = [
    "iq_a", "vout_no_load_v", "line_reg_mv_per_v", "dropout_v_50ma",
    "dropout_v_50ma_floor", "vout_at_vinmax_50ma_v", "load_reg_pct",
    "n_0db_crossings", "phase_margin_deg", "phase_margin_worst_deg",
    "n_gain_margin_crossings", "gain_margin_db", "psrr_db_1khz",
    "psrr_db_100khz",
]


class GenError(Exception):
    """Hard generator error: no artifact may be produced from this input."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise GenError(f"cannot read {path}: {exc}") from exc


def rnd(x: float) -> float:
    """Deterministic float rounding for the output (9 significant digits)."""
    if x == 0:
        return 0.0
    return float(f"{x:.9g}")


def num(row: dict, key: str, ctx: str) -> float:
    raw = row.get(key)
    if raw is None or raw == "":
        raise GenError(f"{ctx}: missing numeric field '{key}'")
    try:
        v = float(raw)
    except ValueError as exc:
        raise GenError(f"{ctx}: field '{key}' is not numeric: {raw!r}") from exc
    if math.isnan(v) or math.isinf(v):
        raise GenError(f"{ctx}: field '{key}' is not finite: {raw!r}")
    return v


def point_id(row: dict) -> dict:
    return {"corner": row["corner"], "temp_c": int(row["temp_c"]),
            "res_section": row["res_section"]}


def read_csv(path: Path) -> list[dict]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError as exc:
        raise GenError(f"cannot read {path}: {exc}") from exc


# --------------------------------------------------------------------------- #
# source loading with pins
# --------------------------------------------------------------------------- #

def load_selection(root: Path) -> dict:
    p = HERE / "selection.json" if root == DEFAULT_ROOT else root / "sim/characterization/selection.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GenError(f"cannot load selection {p}: {exc}") from exc


def pinned(root: Path, entry: dict, role: str, sources: list) -> Path:
    path = root / entry["path"]
    if not path.is_file():
        raise GenError(f"selected record missing: {entry['path']} ({role})")
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        raise GenError(
            f"selected record bytes differ from pin: {entry['path']} ({role}) "
            f"pinned {entry['sha256']} actual {actual}. Historical records are "
            f"append-only; if this is a deliberate re-selection edit "
            f"sim/characterization/selection.json in the same change.")
    sources.append({"role": role, "path": entry["path"], "sha256": actual,
                    "pinned": True})
    return path


def unpinned(root: Path, rel: str, role: str, sources: list) -> Path:
    path = root / rel
    if not path.is_file():
        raise GenError(f"required source missing: {rel} ({role})")
    sources.append({"role": role, "path": rel, "sha256": sha256_file(path),
                    "pinned": False})
    return path


# --------------------------------------------------------------------------- #
# spec tables
# --------------------------------------------------------------------------- #

_SPLIT = re.compile(r"(?<!\\)\|")


def _table_rows(text: str, header_prefix: str) -> list[list[str]]:
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(header_prefix):
            out = []
            for body in lines[i + 2:]:
                if not body.startswith("|"):
                    break
                cells = [c.strip() for c in _SPLIT.split(body.strip())[1:-1]]
                out.append(cells)
            return out
    raise GenError(f"table with header {header_prefix!r} not found")


def parse_readme(text: str) -> list[dict]:
    rows = _table_rows(text, "| Parameter | Target | Stretch |")
    if len(rows) != len(EXPECTED_ROWS):
        raise GenError(f"README target table has {len(rows)} rows, expected {len(EXPECTED_ROWS)}")
    out = []
    for n, (cells, (name, target)) in enumerate(zip(rows, EXPECTED_ROWS), 1):
        if len(cells) != 4:
            raise GenError(f"README row {n} has {len(cells)} cells, expected 4")
        if cells[0] != name:
            raise GenError(f"README row {n} parameter {cells[0]!r} != expected {name!r}")
        if cells[1] != target:
            raise GenError(
                f"README row {n} ({name}) target text changed: {cells[1]!r} != "
                f"{target!r}. A target edit is a spec change; review the "
                f"thresholds in generate.py before updating EXPECTED_ROWS.")
        status = cells[3]
        if status.startswith("RATIFIED"):
            state = "ratified"
        elif status.startswith("OPEN"):
            state = "open_unratified"
        else:
            raise GenError(f"README row {n} status not RATIFIED/OPEN: {status!r}")
        out.append({"id": n, "parameter": name, "target": target,
                    "stretch": cells[2], "readme_status": status,
                    "ratification": state})
    return out


def parse_dr7(text: str) -> dict[int, dict]:
    rows = _table_rows(text, "| # | Row | Current target |")
    out = {}
    for cells in rows:
        if len(cells) < 6 or not cells[0].isdigit():
            raise GenError(f"DR-0007 disposition row malformed: {cells[:2]}")
        n = int(cells[0])
        disp = cells[3].replace("*", "").strip()
        if disp.startswith("Ratified"):
            state = "ratified"
        elif disp.startswith("Open"):
            state = "open_unratified"
        else:
            raise GenError(f"DR-0007 row {n} disposition unrecognized: {disp!r}")
        typ = cells[4].replace("*", "").strip()
        if typ not in ("D", "S"):
            raise GenError(f"DR-0007 row {n} type not D/S: {typ!r}")
        if n in out:
            raise GenError(f"DR-0007 row {n} appears twice")
        out[n] = {"name": cells[1], "disposition": disp, "state": state, "type": typ}
    return out


# --------------------------------------------------------------------------- #
# metric machinery
# --------------------------------------------------------------------------- #

def _extreme(points: list[tuple[float, dict]], worst: str) -> dict:
    """worst='min' -> smallest value; 'max' -> largest. Ties keep first point
    in the record's row order (stable, deterministic)."""
    pick = min if worst == "min" else max
    best = pick(points, key=lambda t: t[0])
    ties = sum(1 for t in points if t[0] == best[0])
    return {"value": rnd(best[0]), "at": best[1], "n_points_at_this_value": ties}


def metric(name, unit, comparator, bound, source_col, record_path, pts,
           conditions, *, censored=None, ambiguous=None, note=None):
    """Evaluate one metric over per-point values.

    pts: list of (value, point_id). comparator: 'lt' | 'gt' | 'ge' | 'le'.
    censored: set of indices whose value is only an upper bound (<= value).
    ambiguous: set of indices whose scalar is not trustworthy (excluded from
    pass counts; their presence blocks a clean pass verdict).
    """
    censored = censored or set()
    ambiguous = ambiguous or set()
    ok = {"lt": lambda v: v < bound, "gt": lambda v: v > bound,
          "ge": lambda v: v >= bound, "le": lambda v: v <= bound}[comparator]
    worst = "max" if comparator in ("lt", "le") else "min"
    n_fail = n_pass = 0
    for i, (v, _p) in enumerate(pts):
        if i in ambiguous:
            continue
        if ok(v):
            n_pass += 1
        else:
            n_fail += 1
    if n_fail:
        verdict = "fail"
    elif ambiguous:
        verdict = "ambiguous"
    else:
        verdict = "pass"
    clean = [t for i, t in enumerate(pts) if i not in ambiguous]
    out = {
        "name": name, "unit": unit,
        "bound": {"comparator": comparator, "value": bound, "unit": unit},
        "n_points": len(pts), "n_pass": n_pass, "n_fail": n_fail,
        "n_censored_upper_bound": len(censored),
        "n_ambiguous": len(ambiguous),
        "worst_case": _extreme(clean, worst) if clean else None,
        "verdict": verdict,
        "conditions": conditions,
        "source": {"record": record_path, "column": source_col},
    }
    if ambiguous:
        out["ambiguous_points"] = [pts[i][1] for i in sorted(ambiguous)]
    if note:
        out["note"] = note
    return out


def unavailable(name, unit, verdict, reason, source=None):
    assert verdict in ("not_measured", "not_implemented")
    return {"name": name, "unit": unit, "verdict": verdict, "reason": reason,
            "source": source}


def cc_window(rows: list[dict]) -> dict:
    """Cc multiple window (x nominal) in which every cc-tolerance bench
    (PM, GM, PSRR 1k/100k) passes, per resistor section, intersected, taking
    the contiguous run around 1.0x. Measured at the single corner listed."""
    by_res: dict[str, list[tuple[float, bool]]] = {}
    corners = set()
    for r in rows:
        x = num(r, "cc_x_nominal", "cc-tolerance")
        by_res.setdefault(r["res_section"], []).append((x, r["all_ok"] == "True"))
        corners.add((r["corner"], int(r["temp_c"])))
    lo_all, hi_all = [], []
    for res, vals in sorted(by_res.items()):
        vals.sort()
        xs = [x for x, _ in vals]
        if 1.0 not in xs or not dict(vals)[1.0]:
            raise GenError(f"cc-tolerance: nominal 1.0x not passing for {res}")
        i = xs.index(1.0)
        lo = i
        while lo > 0 and vals[lo - 1][1]:
            lo -= 1
        hi = i
        while hi < len(vals) - 1 and vals[hi + 1][1]:
            hi += 1
        lo_all.append(xs[lo]); hi_all.append(xs[hi])
    return {"low_x_nominal": round(max(lo_all), 3), "high_x_nominal": round(min(hi_all), 3),
            "corners": [{"corner": c, "temp_c": t} for c, t in sorted(corners)],
            "res_sections": sorted(by_res)}


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #

def build(root: Path) -> tuple[dict, dict, str]:
    """Return (report, envelope, markdown). Raises GenError on any hard error."""
    sel = load_selection(root)
    sources: list[dict] = []
    rec = sel["circuit_record"]
    pvt_path = pinned(root, rec["files"]["pvt_csv"], "circuit_pvt_csv", sources)
    pinned(root, rec["files"]["record_md"], "circuit_record_md", sources)
    cc_path = pinned(root, rec["files"]["cc_tolerance_csv"], "circuit_cc_tolerance_csv", sources)
    dev = sel["device_context_record"]
    dev_path = pinned(root, dev["files"]["screening_csv"], "bare_device_screening_csv", sources)
    readme_rel = sel["spec_sources"]["target_table"]
    dr_rel = sel["spec_sources"]["ratification"]
    readme_path = unpinned(root, readme_rel, "target_table", sources)
    dr_path = unpinned(root, dr_rel, "ratification_record", sources)

    # design freshness
    fresh_checks = []
    stale = False
    for pin in rec["design_freshness_pins"]:
        p = root / pin["path"]
        if not p.is_file():
            raise GenError(f"design freshness pin target missing: {pin['path']}")
        actual = sha256_file(p)
        ok = actual == pin["sha256"]
        stale |= not ok
        fresh_checks.append({"path": pin["path"], "pinned_sha256": pin["sha256"],
                             "actual_sha256": actual, "matches": ok})
        sources.append({"role": "design_netlist_freshness", "path": pin["path"],
                        "sha256": actual, "pinned": True})
    evidence_state = "stale_against_design" if stale else "current"

    # spec tables
    readme_rows = parse_readme(readme_path.read_text(encoding="utf-8"))
    dr7 = parse_dr7(dr_path.read_text(encoding="utf-8"))
    if sorted(dr7) != list(range(1, len(EXPECTED_ROWS) + 1)):
        raise GenError(f"DR-0007 rows {sorted(dr7)} do not cover 1..{len(EXPECTED_ROWS)} exactly once")
    for r in readme_rows:
        d = dr7[r["id"]]
        if d["state"] != r["ratification"]:
            raise GenError(
                f"row {r['id']} ({r['parameter']}): README says {r['ratification']} "
                f"but DR-0007 disposition is {d['state']}")
        r["dr0007_disposition"] = d["disposition"]
        r["dr0007_type"] = "deterministic" if d["type"] == "D" else "statistical"

    # PVT data
    prow = read_csv(pvt_path)
    grid = {(r.get("corner"), r.get("temp_c"), r.get("res_section")) for r in prow}
    want = {(c, str(t), s) for c in CORNERS for t in TEMPS for s in RES}
    if len(prow) != len(want) or grid != want:
        raise GenError(
            f"PVT grid incomplete or malformed: {len(prow)} rows, "
            f"missing {sorted(want - grid)[:3]}..., unexpected {sorted(grid - want)[:3]}...")
    for i, r in enumerate(prow):
        for k in PVT_NUMERIC:
            num(r, k, f"pvt row {i + 2}")
        if r.get("line_reg_in_regulation") not in ("True", "False"):
            raise GenError(f"pvt row {i + 2}: line_reg_in_regulation not True/False")
    pvt_rel = rec["files"]["pvt_csv"]["path"]
    pid = [point_id(r) for r in prow]

    def col(k):
        return [(num(r, k, "pvt"), pid[i]) for i, r in enumerate(prow)]

    bc = rec["bench_conditions"]
    ac_cond = bc["ac_loopgain_and_psrr"]

    # --- AC ambiguity: more than one 0 dB crossing => the scalar PM is the
    # first crossing only and a second crossing exists whose margin the
    # record reports as phase_margin_worst_deg. Not collapsed to a pass.
    amb = {i for i, r in enumerate(prow) if int(num(r, "n_0db_crossings", "pvt")) != 1}
    amb_gm = {i for i, r in enumerate(prow) if int(num(r, "n_gain_margin_crossings", "pvt")) != 1}

    ccw = cc_window(read_csv(cc_path))
    cc_tol_rel = rec["files"]["cc_tolerance_csv"]["path"]

    rows: list[dict] = []

    def add(rdef, metrics, coverage_state, gaps, evidence, stretch_note=None,
            row_verdict=None, notes=None):
        mv = [m["verdict"] for m in metrics]
        if row_verdict is None:
            worst = min(mv, key=lambda v: _METRIC_ORDER[v])
            if worst == "pass":
                row_verdict = ("pass_full_coverage" if coverage_state == "full"
                               else "pass_partial_coverage")
            else:
                row_verdict = worst
        assert row_verdict in ROW_VERDICTS
        rows.append({
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
        })

    R = {r["id"]: r for r in readme_rows}

    # 1 Input -------------------------------------------------------------
    drows = read_csv(dev_path)
    if not drows:
        raise GenError("bare-device screening csv is empty")
    vsg = [num(r, "vsg_stress_v", "screening") for r in drows]
    n_exceed = sum(1 for r in drows if r.get("vsg_exceeds_3p3v_rating") == "YES")
    dev_rel = dev["files"]["screening_csv"]["path"]
    add(R[1], [
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
    ], "bare_device_only")

    # 2 Output ------------------------------------------------------------
    vo = col("vout_no_load_v")
    lo, hi = 1.8 * 0.98, 1.8 * 1.02
    m_lo = metric("VOUT no load, lower bound 1.8 V -2 %", "V", "ge", rnd(lo),
                  "vout_no_load_v", pvt_rel, vo, bc["dc_iq_and_vout"])
    m_hi = metric("VOUT no load, upper bound 1.8 V +2 %", "V", "le", rnd(hi),
                  "vout_no_load_v", pvt_rel, vo, bc["dc_iq_and_vout"])
    m_lo["observed_range"] = {"min": rnd(min(v for v, _ in vo)), "max": rnd(max(v for v, _ in vo))}
    add(R[2], [m_lo, m_hi], "partial", [
        "corner grid only: error-amp offset and divider mismatch are statistical and unexercised (Monte Carlo missing, #56)",
        "ideal 0.90 V reference: measures the regulator only, excluding reference error",
    ], evidence_state, stretch_note="programmable variants deferred; no evidence")

    # 3 Load --------------------------------------------------------------
    v50 = col("vout_at_vinmax_50ma_v")
    m3lo = metric("VOUT at 50 mA, lower bound 1.8 V -2 %", "V", "ge", rnd(lo),
                  "vout_at_vinmax_50ma_v", pvt_rel, v50, "50 mA load, Vin = 3.63 V (record md: dcsweep bench)")
    m3hi = metric("VOUT at 50 mA, upper bound 1.8 V +2 %", "V", "le", rnd(hi),
                  "vout_at_vinmax_50ma_v", pvt_rel, v50, "50 mA load, Vin = 3.63 V (record md: dcsweep bench)")
    add(R[3], [m3lo, m3hi,
               unavailable("dynamic behaviour at 0 mA (no external preload)", "A", "not_measured",
                           "AC loop-gain and PSRR benches run at 1 mA only; no 0 mA dynamic evidence.")],
        "partial", [
            "DC regulation at 50 mA only checked here at Vin = 3.63 V",
            "no 0 mA dynamic/stability evidence",
            "100 mA stretch has no evidence",
        ], evidence_state, stretch_note="100 mA: no evidence")
    # row verdict for 3: a not_measured metric blocks full pass but the
    # measured DC part passes -> partial. Recompute explicitly.
    rows[-1]["verdict"] = ("fail" if "fail" in (m3lo["verdict"], m3hi["verdict"])
                           else "pass_partial_coverage")

    # 4 Dropout -----------------------------------------------------------
    dv = col("dropout_v_50ma")
    fl = col("dropout_v_50ma_floor")
    cens = {i for i in range(len(dv)) if dv[i][0] <= fl[i][0] + 1e-12}
    m4 = metric("dropout at 50 mA", "V", "lt", 0.3, "dropout_v_50ma", pvt_rel, dv,
                bc["dropout"], censored=cens,
                note="Values equal to the sweep floor are censored: the true dropout is <= the "
                     "reported value. For a '<' target an upper bound that already satisfies the "
                     "bound is sufficient; the worst case is an exact (uncensored) measurement.")
    m4["censored_points_floor_v"] = rnd(fl[0][0])
    if m4["worst_case"] and any(
            m4["worst_case"]["at"] == pid[i] for i in cens):
        m4["worst_case_is_censored"] = True
    else:
        m4["worst_case_is_censored"] = False
    n_over_stretch = sum(1 for v, _ in dv if v > 0.2 + 1e-12)
    add(R[4], [m4], "full", [], evidence_state,
        stretch_note=f"stretch < 200 mV is NOT ratified and is not demonstrated: {n_over_stretch} of "
                     f"{len(dv)} points exceed 0.20 V; {len(cens)} points are censored at the floor "
                     f"so cannot demonstrate a strict '< 0.20 V'.")

    # 5 Line / load regulation -------------------------------------------
    lr = col("line_reg_mv_per_v")
    ld = col("load_reg_pct")
    not_in_reg = {i for i, r in enumerate(prow) if r["line_reg_in_regulation"] != "True"}
    m5a = metric("line regulation", "mV/V", "lt", 5.0, "line_reg_mv_per_v", pvt_rel, lr,
                 bc["line_regulation"], ambiguous=not_in_reg)
    m5b = metric("load regulation", "%", "lt", 1.0, "load_reg_pct", pvt_rel, ld,
                 bc["load_regulation"])
    add(R[5], [m5a, m5b], "partial", [
        "line regulation measured at no load only",
        "load regulation measured at Vin = 3.63 V only; not at 3.30/2.97 V",
        "'inside the accuracy window' (Vin window) not covered for either metric (#55)",
    ], evidence_state)

    # 6 PSRR --------------------------------------------------------------
    p1 = col("psrr_db_1khz")
    p100 = col("psrr_db_100khz")
    m6a = metric("PSRR @ 1 kHz", "dB", "gt", 50.0, "psrr_db_1khz", pvt_rel, p1, ac_cond)
    m6b = metric("PSRR @ 100 kHz", "dB", "gt", 20.0, "psrr_db_100khz", pvt_rel, p100, ac_cond)
    n_s = sum(1 for v, _ in p1 if v <= 60.0)
    add(R[6], [m6a, m6b], "partial", [
        "single AC condition: Vin = 3.30 V, 1 mA, 1 uF, ESR 0 -- not 50 mA, not the Cout/ESR window",
        "Cc is un-cornered (MoM-cap model has no corner spread; record labels PSRR insufficient-evidence)",
    ], evidence_state,
        stretch_note=f"stretch > 60 dB @ 1 kHz not met: {n_s} of {len(p1)} points are <= 60 dB; stretch is not ratified.",
        notes=[f"Cc value tolerance (ss/125C only, {cc_tol_rel}): all of PM, GM and PSRR rows hold for "
               f"Cc in x{ccw['low_x_nominal']}..x{ccw['high_x_nominal']} of nominal."])

    # 7 Iq ----------------------------------------------------------------
    iq = col("iq_a")
    for v, _ in iq:
        pass
    iq_uA = [(v * 1e6, p) for v, p in iq]
    m7 = metric("Iq, no load", "uA", "lt", 30.0, "iq_a", pvt_rel, iq_uA, bc["dc_iq_and_vout"],
                note="column iq_a is in A; converted to uA (x1e6) for the row's unit")
    sup = sel["superseded_evidence"][0]
    sup_text = (root / sup["statement_source"])
    if not sup_text.is_file():
        raise GenError(f"superseded evidence source missing: {sup['statement_source']}")
    if sup["quoted_substring"] not in sup_text.read_text(encoding="utf-8"):
        raise GenError(f"superseded evidence quote not found in {sup['statement_source']}")
    sources.append({"role": "superseded_evidence_statement", "path": sup["statement_source"],
                    "sha256": sha256_file(sup_text), "pinned": False})
    mfl = unavailable("Iq at full load", "uA", "not_measured",
                      "The selected record reports no full-load Iq. An older record's full-load "
                      f"figure ({sup['quoted_substring']}) is on a superseded design and is NOT "
                      "used as current evidence.",
                      source={"superseded_statement": sup["statement_source"],
                              "describes": sup["describes"]})
    add(R[7], [m7, mfl], "partial", [
        "full-load half of the row has no current-design measurement",
    ], "current_partial_superseded_other_half" if not stale else evidence_state,
        stretch_note=f"stretch < 10 uA not met: max observed Iq {m7['worst_case']['value']:.4g} uA.")
    rows[-1]["verdict"] = "fail" if m7["verdict"] == "fail" else "pass_partial_coverage"

    # 8, 9 not implemented -----------------------------------------------
    add(R[8], [unavailable("current limit window", "mA", "not_implemented",
                           "No current limiter in the design; record md lists current limit as 'not implemented'.",
                           source={"record": rec["files"]["record_md"]["path"]})],
        "none", ["no limiter exists; statistical row (DR-0007) cannot be graded until one does"],
        "none")
    add(R[9], [unavailable("startup", "ms", "not_implemented",
                           "No enable input and no transient testbench; record md lists startup as 'not implemented'.",
                           source={"record": rec["files"]["record_md"]["path"]})],
        "none", ["no enable input, no transient testbench"], "none")

    # 10 Stability --------------------------------------------------------
    pm = col("phase_margin_deg")
    gm = col("gain_margin_db")
    m10a = metric("phase margin (first 0 dB crossing)", "deg", "ge", 45.0, "phase_margin_deg",
                  pvt_rel, pm, ac_cond, ambiguous=amb,
                  note="Points with more than one 0 dB crossing are not scored: the scalar PM is the "
                       "first crossing only and the record's phase_margin_worst_deg is reported "
                       "beside it unresolved. No scalar pass is manufactured for them.")
    m10a["ambiguous_first_crossing_pm_range_deg"] = (
        {"min": rnd(min(pm[i][0] for i in amb)), "max": rnd(max(pm[i][0] for i in amb))} if amb else None)
    m10a["ambiguous_phase_margin_worst_deg_range"] = (
        {"min": rnd(min(num(prow[i], "phase_margin_worst_deg", "pvt") for i in amb)),
         "max": rnd(max(num(prow[i], "phase_margin_worst_deg", "pvt") for i in amb))} if amb else None)
    m10b = metric("gain margin (first -180 deg crossing)", "dB", "ge", 10.0, "gain_margin_db",
                  pvt_rel, gm, ac_cond, ambiguous=amb_gm)
    add(R[10], [m10a, m10b], "partial", [
        "one (Cout, ESR, load) point only: 1 uF, 0 ohm, 1 mA -- not 0.33-4.7 uF, 0-500 mohm, 0-50 mA",
        "Cc is un-cornered; Cc tolerance checked at ss/125C only",
        f"{len(amb)} of {len(pm)} points have more than one 0 dB crossing (ambiguous scalar PM)",
    ], evidence_state,
        notes=[f"Cc value tolerance (ss/125C only, {cc_tol_rel}): PM, GM and PSRR all hold for Cc in "
               f"x{ccw['low_x_nominal']}..x{ccw['high_x_nominal']} of nominal."])

    # --- completeness ----------------------------------------------------
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # The four checks hard-coded True below are enforced earlier in build(): any
    # violation raises GenError (and main() writes a status:fail envelope) before
    # this point, so reaching here means they held. They are listed for the record.
    chk("all selected records exist and match their sha256 pins", True,
        f"{sum(1 for s in sources if s['pinned'])} pinned sources verified")
    chk("README target table: 10 rows, expected names and target text", True)
    chk("DR-0007 ratification table covers rows 1-10 exactly once and agrees with README", True)
    chk("PVT grid complete (5 process x 3 temperature x 3 resistor corner = 45 points, all numeric fields finite)", True)
    chk("every target row appears exactly once", sorted(r["id"] for r in rows) == list(range(1, 11)),
        f"rows: {[r['id'] for r in rows]}")
    chk("every row carries an allowed verdict", all(r["verdict"] in ROW_VERDICTS for r in rows))
    chk("every row cites a source or an explicit unavailability reason",
        all(all(("source" in m and m["source"]) or m.get("reason") for m in r["metrics"]) for r in rows))
    chk("selected record is current against the design netlists", not stale,
        "design netlist hashes match the freshness pins" if not stale
        else "design netlist changed since the selected record: select a newer record")
    failures = [c for c in checks if not c["ok"]]
    complete = not failures

    tally: dict = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    ratified = [r["id"] for r in rows if r["ratification"]["state"] == "ratified"]

    report = {
        "schema_version": 1,
        "title": "sg13g2-ldo per-spec-row characterization report (T1 item 8)",
        "generator": {"path": "sim/characterization/generate.py", "version": GENERATOR_VERSION},
        "purpose_and_limits": [
            "This is a CHARACTERIZATION report: one aggregated, current artifact summarizing per-row performance and citing the record behind each verdict.",
            "Completeness is not compliance. The artifact can be complete and fresh while rows fail, are ambiguous, unmeasured or unimplemented; the envelope verdict reports artifact completeness only.",
            "Open (unratified) targets are not passing requirements; a numeric 'pass' on an open row is a measurement against a draft target at the stated conditions.",
            "All closed-loop numbers are SG13CMOS5L-branch evidence (DR-0007 'What evidence exists'); no closed-loop evidence exists on the SG13G2 branch.",
            "No post-layout (extracted) performance evidence exists for any row; layout reports in layout/ are DRC/LVS/ERC and carry no performance metrics.",
            "Other T1 items are not declared satisfied by this artifact.",
        ],
        "selection": {
            "file": "sim/characterization/selection.json",
            "sha256": sha256_file(root / "sim/characterization/selection.json"),
            "circuit_record_id": rec["id"],
            "experiment": rec["experiment"],
            "device_context_record_id": dev["id"],
            "policy": sel["policy"],
        },
        "sources": sorted(sources, key=lambda s: (s["role"], s["path"])),
        "design_freshness": {"state": evidence_state, "basis": rec["design_freshness_basis"],
                             "pins": fresh_checks},
        "bench_conditions": bc,
        "cc_tolerance_window": ccw,
        "rows": rows,
        "summary": {
            "rows_total": len(rows),
            "rows_by_verdict": dict(sorted(tally.items())),
            "ratified_rows": ratified,
            "open_unratified_rows": [r["id"] for r in rows if r["id"] not in ratified],
            "rows_with_any_coverage_gap": [r["id"] for r in rows if r["coverage"]["gaps"]],
            "rows_with_full_coverage_of_target_as_written": [r["id"] for r in rows if r["coverage"]["state"] == "full"],
        },
        "completeness": {"status": "complete" if complete else "incomplete", "checks": checks,
                         "meaning": "Artifact completeness/freshness only -- NOT circuit spec compliance."},
    }
    report_bytes = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    report_hash = hashlib.sha256(report_bytes).hexdigest()

    envelope = {
        "schema_version": 1,
        "kind": "generic",
        "status": "pass" if complete else "fail",
        "summary": (
            "T1 item 8 characterization artifact: all 10 target-spec rows present once with explicit "
            "verdicts, pinned sources verified, evidence current against the design. Verdict covers "
            "artifact completeness/freshness only, NOT circuit spec compliance; row verdicts: "
            + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
        if complete else
        "T1 item 8 characterization artifact INCOMPLETE or STALE: "
        + "; ".join(c["check"] for c in failures),
        "source": f"sim/characterization/{REPORT_MD}",
        "t1_item": 8,
        "verdict_semantics": (
            "pass = the characterization artifact is complete and fresh (every target row present "
            "exactly once with an explicit state, every selected source verified against its pin, "
            "the PVT grid whole, the record current against the design netlists). It is NOT a claim "
            "that the circuit meets its spec: failing, ambiguous, unmeasured, unimplemented and "
            "unratified rows are listed as such in the report. klt does not read `source`; this "
            "repository's generator and CI verify the content."),
        "provenance": {
            "klt_version": None, "klayout_version": None, "pdk": None, "deck": None,
            "input": {"content_hash": f"sha256:{report_hash}", "role": "characterization-report"},
            "generator": {"path": "sim/characterization/generate.py", "version": GENERATOR_VERSION},
        },
    }
    md = render_md(report, envelope)
    return report, envelope, md


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #

def _fmt_at(at):
    return f"{at['corner']}/{at['temp_c']}C/{at['res_section']}" if at else "-"


def render_md(rep: dict, env: dict) -> str:
    L = []
    w = L.append
    w(f"# {rep['title']}")
    w("")
    w("<!-- GENERATED by sim/characterization/generate.py -- do not edit; CI regenerates and diffs. -->")
    w("")
    w(f"**Artifact completeness: {rep['completeness']['status'].upper()}** "
      f"(envelope status `{env['status']}`). This verdict is about the artifact, "
      "**not** about whether the circuit meets its spec.")
    w("")
    for s in rep["purpose_and_limits"]:
        w(f"- {s}")
    w("")
    w("## Selection and sources")
    w("")
    sel = rep["selection"]
    w(f"- Circuit record (explicitly selected, hash-pinned): `{sel['experiment']}` / `{sel['circuit_record_id']}`")
    w(f"- Bare-device context record: `{sel['device_context_record_id']}` (never used as a closed-loop measurement)")
    w(f"- Selection file: `{sel['file']}` sha256 `{sel['sha256']}`")
    w(f"- Design freshness: **{rep['design_freshness']['state']}**")
    w("")
    w("| Role | Path | sha256 | Pinned |")
    w("|---|---|---|---|")
    for s in rep["sources"]:
        w(f"| {s['role']} | `{s['path']}` | `{s['sha256']}` | {'yes' if s['pinned'] else 'recorded'} |")
    w("")
    w("## Per-row summary")
    w("")
    w("| # | Parameter | Target | Ratification | Verdict | Coverage | Evidence |")
    w("|---|---|---|---|---|---|---|")
    for r in rep["rows"]:
        w(f"| {r['id']} | {r['parameter']} | {r['target']} | {r['ratification']['state']} "
          f"({r['ratification']['dr0007_type']}) | **{r['verdict']}** | {r['coverage']['state']} | {r['evidence_state']} |")
    w("")
    w("Verdict key: `pass_*` = measured metrics meet the bound at the stated conditions (not a compliance "
      "claim); `fail` = a measured point violates the bound; `ambiguous` = scalar not trustworthy at some "
      "points; `not_measured` = no current measurement; `not_implemented` = function absent from the design.")
    w("")
    w("## Rows in detail")
    for r in rep["rows"]:
        w("")
        w(f"### {r['id']}. {r['parameter']} -- {r['verdict']}")
        w("")
        w(f"- Target: {r['target']}; stretch: {r['stretch']}")
        w(f"- Ratification: {r['ratification']['state']} (README: {r['ratification']['readme_status']}; "
          f"DR-0007: {r['ratification']['dr0007_disposition']}, {r['ratification']['dr0007_type']})")
        if r["stretch_note"]:
            w(f"- Stretch: {r['stretch_note']}")
        for n in r["notes"]:
            w(f"- Note: {n}")
        if r["coverage"]["gaps"]:
            w(f"- Coverage of the row as written: {r['coverage']['state']}. Gaps:")
            for g in r["coverage"]["gaps"]:
                w(f"  - {g}")
        w("")
        for m in r["metrics"]:
            if "bound" not in m:
                w(f"- **{m['name']}**: {m['verdict']} -- {m['reason']}")
                if m.get("device_context"):
                    dc = m["device_context"]
                    w(f"  - device context ({dc['branch']}): max |Vsg| {dc['max_vsg_stress_v']} V, "
                      f"{dc['n_exceeding_3p3v_rating']}/{dc['n_device_points']} device points exceed the 3.3 V rating "
                      f"(source `{m['source']['record']}`)")
                continue
            b = m["bound"]
            wc = m["worst_case"]
            w(f"- **{m['name']}** ({m['unit']}): {m['verdict']}; bound {b['comparator']} {b['value']} {b['unit']}; "
              f"{m['n_pass']}/{m['n_points']} pass, {m['n_fail']} fail, {m['n_ambiguous']} ambiguous, "
              f"{m['n_censored_upper_bound']} censored upper bound")
            if wc:
                w(f"  - worst case {wc['value']} at {_fmt_at(wc['at'])}"
                  + (" (censored)" if m.get("worst_case_is_censored") else "")
                  + (f" (first of {wc['n_points_at_this_value']} points at this value)"
                     if wc["n_points_at_this_value"] > 1 else ""))
            w(f"  - conditions: {m['conditions']}")
            w(f"  - source: `{m['source']['record']}` column `{m['source']['column']}`")
            if m.get("observed_range"):
                w(f"  - observed range {m['observed_range']['min']}..{m['observed_range']['max']} {m['unit']}")
            if m.get("ambiguous_points"):
                w("  - ambiguous points: " + ", ".join(_fmt_at(p) for p in m["ambiguous_points"]))
                if m.get("ambiguous_first_crossing_pm_range_deg"):
                    a = m["ambiguous_first_crossing_pm_range_deg"]
                    z = m["ambiguous_phase_margin_worst_deg_range"]
                    w(f"  - at those points: first-crossing PM {a['min']}..{a['max']} deg, "
                      f"record phase_margin_worst_deg {z['min']}..{z['max']} deg (unresolved)")
            if m.get("note"):
                w(f"  - note: {m['note']}")
    w("")
    w("## Completeness checks")
    w("")
    for c in rep["completeness"]["checks"]:
        w(f"- [{'x' if c['ok'] else ' '}] {c['check']}" + (f" -- {c['detail']}" if c["detail"] else ""))
    w("")
    w("## Regenerating")
    w("")
    w("```bash")
    w("python3 sim/characterization/generate.py          # regenerate report, markdown, envelope")
    w("python3 sim/characterization/generate.py --check  # verify the committed files reproduce exactly")
    w("```")
    w("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def render_bytes(report, envelope, md) -> dict[str, bytes]:
    return {
        REPORT_JSON: (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        REPORT_MD: md.encode("utf-8"),
        ENVELOPE_JSON: (json.dumps(envelope, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    }


def failure_envelope(reason: str) -> bytes:
    env = {"schema_version": 1, "kind": "generic", "status": "fail",
           "summary": f"characterization generator error: {reason}",
           "source": f"sim/characterization/{REPORT_MD}", "t1_item": 8}
    return (json.dumps(env, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="regenerate in memory and fail on any difference from the committed files")
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="repository root to read inputs from (default: this checkout)")
    ap.add_argument("--out", default=None,
                    help="directory for generated files (default: <root>/sim/characterization)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    out = Path(args.out).resolve() if args.out else root / "sim/characterization"

    try:
        report, envelope, md = build(root)
        files = render_bytes(report, envelope, md)
    except Exception as exc:  # noqa: BLE001 -- any failure, not just GenError, must clear a pass
        # GenError is the anticipated hard-error path; anything else (KeyError/TypeError
        # from a malformed selection.json, OSError, ...) is a generator bug or bad input
        # and must equally never leave a previously committed passing envelope behind.
        reason = str(exc) if isinstance(exc, GenError) else f"{type(exc).__name__}: {exc}"
        print(f"ERROR: {reason}", file=sys.stderr)
        if not isinstance(exc, GenError):
            traceback.print_exc(file=sys.stderr)
        if not args.check:
            out.mkdir(parents=True, exist_ok=True)
            (out / ENVELOPE_JSON).write_bytes(failure_envelope(reason))
            print(f"wrote a status:fail envelope to {out / ENVELOPE_JSON} "
                  "(no passing envelope is left behind)", file=sys.stderr)
        return 1

    if args.check:
        bad = []
        for name, data in files.items():
            p = out / name
            if not p.is_file():
                bad.append(f"{name}: missing")
            elif p.read_bytes() != data:
                bad.append(f"{name}: differs from regeneration (report drift or source-data drift)")
        committed_env = out / ENVELOPE_JSON
        if committed_env.is_file():
            try:
                ce = json.loads(committed_env.read_text(encoding="utf-8"))
                want = hashlib.sha256(files[REPORT_JSON]).hexdigest()
                got = ce.get("provenance", {}).get("input", {}).get("content_hash")
                if ce.get("status") == "pass" and got != f"sha256:{want}":
                    bad.append("envelope claims pass but its provenance hash does not match the regenerated report")
            except ValueError:
                bad.append(f"{ENVELOPE_JSON}: not valid JSON")
        if bad:
            print("characterization --check FAILED:", file=sys.stderr)
            for b in bad:
                print(f"  - {b}", file=sys.stderr)
            print("Regenerate with: python3 sim/characterization/generate.py "
                  "and review the diff.", file=sys.stderr)
            return 1
        if envelope["status"] != "pass":
            print("characterization --check: files reproduce, but the artifact is INCOMPLETE/STALE "
                  f"(envelope status {envelope['status']}): {envelope['summary']}", file=sys.stderr)
            return 1
        print("characterization --check OK: report, markdown and envelope reproduce exactly "
              f"(envelope {envelope['status']}; hash sha256:{hashlib.sha256(files[REPORT_JSON]).hexdigest()})")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    print(f"wrote {', '.join(files)} to {out} (envelope status: {envelope['status']})")
    return 0 if envelope["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
