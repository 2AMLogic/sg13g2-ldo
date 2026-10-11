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
import gzip
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

DC_COND_LINE = ("line regulation |dVOUT/dVin| over Vin 2.97-3.63 V at the labelled load; "
                "ideal 0.90 V reference; 45-point corner grid")
DC_COND_LOAD = ("load regulation (V(0 mA) - V(50 mA)) / V(0 mA) at the labelled fixed Vin; "
                "ideal 0.90 V reference; 45-point corner grid")
DC_COND_IQ = "50 mA load, Vin = 3.30 V, |i(Vin)| - Iload; ideal 0.90 V reference and 2 uA Ibias sink; 45-point corner grid"

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
# informational DC evidence (rows 5 and 7)
# --------------------------------------------------------------------------- #

DC_LOADS = [("0mA", "0 mA"), ("12p5mA", "12.5 mA"), ("25mA", "25 mA"),
            ("37p5mA", "37.5 mA"), ("50mA", "50 mA")]
DC_VINS = [("2p97", "2.97 V"), ("3p30", "3.30 V"), ("3p63", "3.63 V")]


def dc_expected_columns() -> list[str]:
    cols = ["corner", "temp_c", "res_section", "grid_ok", "iq_noload_a",
            "iq_fullload_excl_load_a", "iq_fullload_valid", "iq_fullload_noise_proxy_a"]
    cols += [f"line_reg_mv_per_v_{k}" for k, _ in DC_LOADS]
    cols += [f"line_reg_valid_{k}" for k, _ in DC_LOADS]
    for k, _ in DC_VINS:
        cols += [f"load_reg_pct_vin{k}", f"load_reg_valid_vin{k}", f"vout_50mA_vin{k}_v"]
    cols += ["dropout_legacy_v", "dropout_status", "dropout_vin_minus_vout_candidate_v"]
    return cols


def _boolfield(row: dict, key: str, ctx: str) -> bool:
    v = row.get(key)
    if v not in ("True", "False"):
        raise GenError(f"{ctx}: validity field '{key}' must be True/False, got {v!r}")
    return v == "True"


def load_dc_informational(root: Path, sel: dict, rec: dict, pvt_rows: list[dict],
                          sources: list) -> dict:
    """Validate and return the pinned informational DC summary for the selected
    record. Every failure is a hard GenError (fail-closed): nothing is skipped
    or repaired, and a point that is invalid stays in the data as invalid."""
    dc = sel.get("dc_informational_evidence")
    if not isinstance(dc, dict):
        raise GenError("selection.json has no dc_informational_evidence block")
    if dc.get("circuit_record_id") != rec["id"]:
        raise GenError(
            f"dc_informational_evidence is for record {dc.get('circuit_record_id')!r}, "
            f"selected circuit record is {rec['id']!r}")
    sum_path = pinned(root, dc["files"]["summary_csv"], "dc_informational_summary_csv", sources)
    inv_path = pinned(root, dc["files"]["coverage_inventory_json"],
                      "dc_coverage_inventory_json", sources)
    for p in (dc["files"]["summary_csv"]["path"], dc["files"]["coverage_inventory_json"]["path"]):
        if f"/{rec['id']}/" not in p:
            raise GenError(f"DC evidence path {p} is not under the selected record id {rec['id']}")

    # --- provenance inventory: must describe THIS record and design ---------
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        ins = inv["inputs"]
        gen = inv["generator"]
        grid = inv["grid"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GenError(f"DC coverage inventory unreadable or malformed: {exc!r}") from exc
    for role in ("record_csv", "record_md"):
        want = rec["files"]["pvt_csv" if role == "record_csv" else "record_md"]
        got = ins.get(role) or {}
        if got.get("path") != want["path"] or got.get("sha256") != want["sha256"]:
            raise GenError(
                f"DC inventory {role} does not match the selected record's pinned {role}: "
                f"{got.get('path')!r} {got.get('sha256')!r}")
    pins = {p["path"]: p["sha256"] for p in rec["design_freshness_pins"]}
    if ins.get("design_netlists") != pins:
        raise GenError("DC inventory design_netlists differ from the selection's design freshness pins")
    if grid.get("points") != 45 or grid.get("reproduces_record_csv") is not True:
        raise GenError("DC inventory does not state a 45-point grid that reproduces the record csv")
    gen_p = root / gen["path"]
    if not gen_p.is_file() or sha256_file(gen_p) != gen["sha256"]:
        raise GenError(f"DC inventory generator {gen.get('path')} missing or differs from its recorded sha256")
    raw = ins.get("raw_dc_grids")
    if not isinstance(raw, dict) or len(raw) != 45:
        raise GenError(f"DC inventory lists {len(raw) if isinstance(raw, dict) else 'no'} raw DC grids, expected 45")
    for rel, h in sorted(raw.items()):
        if f"/{rec['id']}/" not in rel:
            raise GenError(f"raw DC grid {rel} is not under the selected record id")
        rp = root / rel
        if not rp.is_file():
            raise GenError(f"raw DC grid missing: {rel}")
        if sha256_file(rp) != h:
            raise GenError(f"raw DC grid bytes differ from the inventory hash: {rel}")

    # --- summary: complete grid, finite values, True/False validity ---------
    srows = read_csv(sum_path)
    try:
        with sum_path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
    except (OSError, StopIteration) as exc:
        raise GenError(f"cannot read DC summary header: {exc!r}") from exc
    if header != dc_expected_columns():
        raise GenError(f"DC summary columns differ from the expected schema/units: {header}")
    keys = [(r["corner"], r["temp_c"], r["res_section"]) for r in srows]
    if len(set(keys)) != len(keys):
        dup = sorted(k for k in set(keys) if keys.count(k) > 1)
        raise GenError(f"DC summary has duplicate corner rows: {dup[:3]}")
    want = {(c, str(t), s) for c in CORNERS for t in TEMPS for s in RES}
    if set(keys) != want or len(keys) != 45:
        raise GenError(
            f"DC summary corner set incomplete or malformed: {len(keys)} rows, "
            f"missing {sorted(want - set(keys))[:3]}, unexpected {sorted(set(keys) - want)[:3]}")
    by_key = {}
    num_cols = [c for c in dc_expected_columns()
                if c not in ("corner", "temp_c", "res_section", "grid_ok", "dropout_status")
                and "_valid" not in c]
    for i, r in enumerate(srows):
        ctx = f"DC summary row {i + 2} ({r['corner']}/{r['temp_c']}/{r['res_section']})"
        if not _boolfield(r, "grid_ok", ctx):
            raise GenError(f"{ctx}: grid_ok is False; the raw grid was not complete")
        vals = {c: num(r, c, ctx) for c in num_cols}
        valid = {c: _boolfield(r, c, ctx) for c in dc_expected_columns() if "_valid" in c}
        by_key[(r["corner"], r["temp_c"], r["res_section"])] = (vals, valid)

    # --- agree with the pinned PVT csv where the two overlap ---------------
    for i, pr in enumerate(pvt_rows):
        k = (pr["corner"], pr["temp_c"], pr["res_section"])
        vals, _ = by_key[k]
        for pc, dc_col in (("iq_a", "iq_noload_a"), ("line_reg_mv_per_v", "line_reg_mv_per_v_0mA"),
                           ("load_reg_pct", "load_reg_pct_vin3p63"),
                           ("vout_at_vinmax_50ma_v", "vout_50mA_vin3p63_v")):
            a, b = float(pr[pc]), vals[dc_col]
            if abs(a - b) > 1e-6 * max(abs(a), 1e-12):
                raise GenError(
                    f"DC summary disagrees with the pinned PVT csv at {k}: "
                    f"{dc_col}={b} vs {pc}={a}")
    return {"by_key": by_key, "summary_path": dc["files"]["summary_csv"]["path"],
            "inventory_path": dc["files"]["coverage_inventory_json"]["path"],
            "n_raw_grids": len(raw)}


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# startup campaign evidence (row 9)
# --------------------------------------------------------------------------- #

# Proposed-methodology thresholds (DR-0009; mirrored in selection.json
# startup_evidence.proposed_methodology and startup_eval.py). Not ratified.
STARTUP_BAND_HI_V = 1.836
STARTUP_SETTLE_LIMIT_S = 3e-3
STARTUP_MONOTONIC_TOL_V = 1e-3
STARTUP_CSV_VERDICTS = ("pass", "fail", "insufficient")
STARTUP_REQUIRED = [
    "start_settle_time_s", "start_peak_vout_v", "start_max_down_excursion_v",
    "reen_peak_vout_v", "reen_max_down_excursion_v", "start_observed_s",
]
STARTUP_EXTRA = [
    "start_overshoot_v", "reen_overshoot_v", "reen_observed_s",
    "start_rise_10_90_s", "off_vout_max_v", "off_supply_current_a",
]


def startup_row_verdict(n_fail: int, n_insufficient: int, n_missing: int,
                        n_evaluated: int) -> str:
    """Row-9 verdict from point counts. A measured failure always wins (it is
    never masked by missing or insufficient points, nor by a numeric settling
    success); without failures, anything short of a whole evaluated grid is
    `not_measured`; only a whole, all-passing grid is a (partial-coverage)
    pass, and even that is a proposed-methodology measurement, not a
    ratification."""
    if n_fail:
        return "fail"
    if n_insufficient or n_missing or n_evaluated == 0:
        return "not_measured"
    return "pass_partial_coverage"


def _startup_key(mos, temp, res, vin, load, cout, esr, tmax):
    return (str(mos), int(float(temp)), str(res), round(float(vin), 3),
            float(load), float(cout), float(esr), float(tmax))


def load_startup(root: Path, sel: dict, sources: list) -> dict:
    """Validate and return the explicitly selected, pinned startup campaign.

    Hard GenError: block missing, wrong id/stage, any selected file missing or
    different from its pin, manifest/record disagreement, malformed or
    non-finite fields, duplicate or unexpected campaign point, trace file
    missing/tampered, a csv `pass` contradicted by a measured metric. Reported
    (not raised): requested points with no result row (`missing`), points the
    evaluator marked `insufficient`, and design staleness (core and error
    amplifier independently)."""
    st = sel.get("startup_evidence")
    if not isinstance(st, dict):
        raise GenError("selection.json has no startup_evidence block")
    rid = st["id"]
    for key in ("record_md", "grid_csv", "manifest_json"):
        if rid not in st["files"][key]["path"]:
            raise GenError(f"startup file {st['files'][key]['path']} is not under the selected startup id {rid}")
    pinned(root, st["files"]["record_md"], "startup_record_md", sources)
    csv_path = pinned(root, st["files"]["grid_csv"], "startup_grid_csv", sources)
    man_path = pinned(root, st["files"]["manifest_json"], "startup_manifest_json", sources)
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GenError(f"cannot load startup manifest {st['files']['manifest_json']['path']}: {exc}") from exc
    if man.get("rid") != rid or man.get("stage") != st["stage"]:
        raise GenError(f"startup manifest is for {man.get('rid')!r}/{man.get('stage')!r}, "
                       f"selected {rid!r}/{st['stage']!r}")

    # --- design freshness: core and error amplifier, independently ---------
    fresh = {}
    for comp, pin in st["design_freshness_pins"].items():
        p = root / pin["path"]
        if not p.is_file():
            raise GenError(f"startup design freshness pin target missing: {pin['path']} ({comp})")
        actual = sha256_file(p)
        entry = {"path": pin["path"], "pinned_sha256": pin["sha256"], "actual_sha256": actual,
                 "matches": actual == pin["sha256"], "recorded_in_manifest": bool(pin["recorded_in_manifest"])}
        if pin["recorded_in_manifest"]:
            mv = man.get("source_sha256", {}).get(pin["path"])
            if mv != pin["sha256"]:
                raise GenError(f"startup manifest source_sha256 for {pin['path']} is {mv!r}, "
                               f"selection pin is {pin['sha256']!r} ({comp})")
            entry["manifest_sha256"] = mv
        fresh[comp] = entry
        sources.append({"role": f"startup_design_{comp}_freshness", "path": pin["path"],
                        "sha256": actual, "pinned": True})
    stale_components = sorted(c for c, e in fresh.items() if not e["matches"])

    # --- campaign points ---------------------------------------------------
    g = st["requested_grid"]
    expected = {_startup_key(m, t, r, v, l, c, e, x)
                for m in g["process"] for t in g["temp_c"] for r in g["res"]
                for v in g["vin_v"] for l in g["load_ma"] for c in g["cout_nf"]
                for e in g["esr_mohm"] for x in g["tmax_ns"]}
    if man.get("requested") != len(expected):
        raise GenError(f"startup manifest requested {man.get('requested')} points, "
                       f"selected grid has {len(expected)}")
    rows = read_csv(csv_path)
    traces_dir = root / st["traces_dir"]
    seen: dict = {}
    pts = []
    for i, r in enumerate(rows):
        ctx = f"startup row {i + 2}"
        try:
            key = _startup_key(r["mos"], r["temp"], r["res"], r["vin"], r["load_ma"],
                               r["cout_nf"], r["esr_mohm"], r["tmax_ns"])
        except (KeyError, ValueError) as exc:
            raise GenError(f"{ctx}: malformed point coordinates: {exc!r}") from exc
        if key in seen:
            raise GenError(f"{ctx}: duplicate campaign point {r.get('point')} "
                           f"(same coordinates as row {seen[key] + 2})")
        seen[key] = i
        if key not in expected:
            raise GenError(f"{ctx}: point {r.get('point')} is outside the selected requested grid")
        verdict = r.get("verdict")
        if verdict not in STARTUP_CSV_VERDICTS:
            raise GenError(f"{ctx}: verdict {verdict!r} not one of {STARTUP_CSV_VERDICTS}")
        pt = {"point": r["point"], "corner": r["mos"], "temp_c": int(float(r["temp"])),
              "res_section": "res_" + r["res"], "vin_v": round(float(r["vin"]), 3),
              "load_ma": float(r["load_ma"]), "cout_nf": float(r["cout_nf"]),
              "esr_mohm": float(r["esr_mohm"])}
        rec = {"id": pt, "verdict": verdict, "reasons": r.get("reasons", ""),
               "settled": r.get("start_settled") == "True"}
        if verdict != "insufficient":
            for k in STARTUP_REQUIRED:
                rec[k] = num(r, k, ctx)
            if r.get("start_settled") not in ("True", "False"):
                raise GenError(f"{ctx}: start_settled not True/False")
            for k in STARTUP_EXTRA:
                if r.get(k, "") != "":
                    rec[k] = num(r, k, ctx)
            tf, ts = r.get("trace_file", ""), r.get("trace_sha256", "")
            tp = traces_dir / Path(tf).name
            if not tf or not tp.is_file():
                raise GenError(f"{ctx}: trace file missing for evaluated point {r['point']}: {tf!r}")
            if sha256_file(tp) != ts:
                raise GenError(f"{ctx}: trace {tf} bytes differ from the recorded trace_sha256")
            try:
                with gzip.open(tp, "rt", encoding="utf-8") as fh:
                    n_lines = sum(1 for _ in fh) - 1
            except (OSError, EOFError) as exc:
                raise GenError(f"{ctx}: trace {tf} unreadable: {exc}") from exc
            if n_lines != int(num(r, "samples", ctx)) or n_lines < 2:
                raise GenError(f"{ctx}: trace {tf} has {n_lines} samples, record says {r.get('samples')}")
        pts.append(rec)
    missing = sorted(expected - set(seen))
    n_ins = sum(1 for p in pts if p["verdict"] == "insufficient")
    n_fail = sum(1 for p in pts if p["verdict"] == "fail")
    n_pass = sum(1 for p in pts if p["verdict"] == "pass")
    for k, v in (("rows", len(pts)), ("insufficient", n_ins), ("fail", n_fail), ("pass", n_pass),
                 ("evaluated", n_fail + n_pass)):
        if man.get(k) != v and not missing:
            raise GenError(f"startup manifest {k}={man.get(k)!r} disagrees with the pinned csv ({v})")
    return {"cfg": st, "rid": rid, "manifest": man, "points": pts, "fresh": fresh,
            "stale_components": stale_components, "n_requested": len(expected),
            "missing": [{"corner": k[0], "temp_c": k[1], "res_section": "res_" + k[2],
                         "vin_v": k[3], "load_ma": k[4], "cout_nf": k[5], "esr_mohm": k[6]}
                        for k in missing],
            "n_fail": n_fail, "n_pass": n_pass, "n_insufficient": n_ins,
            "csv_rel": st["files"]["grid_csv"]["path"], "md_rel": st["files"]["record_md"]["path"]}


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
    dcev = load_dc_informational(root, sel, rec, prow, sources)
    dc_rel = dcev["summary_path"]
    su = load_startup(root, sel, sources)

    def dc_col(name, scale=1.0, valid=None):
        """(values, ambiguous-index-set) over the pvt row order. Invalid points
        stay in the data and are returned as the ambiguous set."""
        pts, bad = [], set()
        for i, r in enumerate(prow):
            vals, vflags = dcev["by_key"][(r["corner"], r["temp_c"], r["res_section"])]
            pts.append((vals[name] * scale, pid[i]))
            if valid is not None and not vflags[valid]:
                bad.add(i)
        return pts, bad

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
    m5a = metric("line regulation, legacy record column (no load)", "mV/V", "lt", 5.0,
                 "line_reg_mv_per_v", pvt_rel, lr, bc["line_regulation"], ambiguous=not_in_reg)
    m5b = metric("load regulation, legacy record column (Vin = 3.63 V)", "%", "lt", 1.0,
                 "load_reg_pct", pvt_rel, ld, bc["load_regulation"])
    m5 = [m5a, m5b]
    dc_note = ("Informational DC summary (derived offline from the committed raw DC grids, "
               "no new simulation). A point is valid only if both end points are within 1 % of "
               "1.8 V; invalid points are counted as ambiguous and never dropped. Discrete "
               "sampled loads/supplies only: not a continuous-window claim.")
    for key, label in DC_LOADS:
        pts, bad = dc_col(f"line_reg_mv_per_v_{key}", valid=f"line_reg_valid_{key}")
        m = metric(f"line regulation at {label} load (Vin 2.97-3.63 V)", "mV/V", "lt", 5.0,
                   f"line_reg_mv_per_v_{key}", dc_rel, pts, DC_COND_LINE, ambiguous=bad, note=dc_note)
        m["n_invalid"] = len(bad)
        m5.append(m)
    for key, label in DC_VINS:
        pts, bad = dc_col(f"load_reg_pct_vin{key}", valid=f"load_reg_valid_vin{key}")
        m = metric(f"load regulation 0-50 mA at Vin = {label}", "%", "lt", 1.0,
                   f"load_reg_pct_vin{key}", dc_rel, pts, DC_COND_LOAD, ambiguous=bad, note=dc_note)
        m["n_invalid"] = len(bad)
        m5.append(m)
    add(R[5], m5, "partial", [
        "line regulation sampled at 5 discrete loads (0, 12.5, 25, 37.5, 50 mA) over Vin 2.97-3.63 V; "
        "load regulation sampled at 3 discrete supplies (2.97, 3.30, 3.63 V) -- not continuous coverage of the window",
        "'inside the accuracy window' (coupling with the statistical VOUT row, #56) not covered for either metric",
        "ideal 0.90 V reference: reference error is excluded; corner grid only, no Monte Carlo",
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
    fl_pts, fl_bad = dc_col("iq_fullload_excl_load_a", 1e6, valid="iq_fullload_valid")
    proxy = [v for v, _ in dc_col("iq_fullload_noise_proxy_a", 1e6)[0]]
    mfl = metric("Iq at full load (50 mA), load current excluded", "uA", "lt", 30.0,
                 "iq_fullload_excl_load_a", dc_rel, fl_pts, DC_COND_IQ, ambiguous=fl_bad,
                 note="Derived offline as |i(Vin)| - Iload from the committed raw DC grid (column in A, "
                      "converted to uA). Precision caveat: the grid is printed to 9 significant digits, "
                      "so a ~22 uA difference of two ~50 mA currents is quantized at 1e-10 A (0.0001 uA); "
                      "solver noise beyond that floor is not bounded by this data. Invalid points are "
                      "counted as ambiguous, never dropped. An older record's full-load figure "
                      f"({sup['quoted_substring']}) is on a superseded design and is NOT used.")
    mfl["n_invalid"] = len(fl_bad)
    mfl["precision_floor_uA"] = rnd(max(proxy))
    mfl["superseded_statement"] = {"source": sup["statement_source"], "describes": sup["describes"]}
    add(R[7], [m7, mfl], "partial", [
        "Iq at full load is measured at Vin = 3.30 V only (no other supplies)",
        "full-load Iq is a difference of two ~50 mA currents; quantized at 1e-10 A, solver noise not bounded beyond that",
        "ideal 0.90 V reference and ideal Ibias sink: reference/bias-generator current excluded; corner grid only",
    ], evidence_state,
        stretch_note=f"stretch < 10 uA not met: max observed no-load Iq {m7['worst_case']['value']:.4g} uA"
                     + (f", max full-load Iq {mfl['worst_case']['value']:.4g} uA." if mfl["worst_case"] else "."))
    rows[-1]["verdict"] = ("fail" if "fail" in (m7["verdict"], mfl["verdict"])
                           else "ambiguous" if mfl["verdict"] == "ambiguous"
                           else "pass_partial_coverage")

    # 8 not implemented -----------------------------------------------
    add(R[8], [unavailable("current limit window", "mA", "not_implemented",
                           "No current limiter in the design; record md lists current limit as 'not implemented'.",
                           source={"record": rec["files"]["record_md"]["path"]})],
        "none", ["no limiter exists; statistical row (DR-0007) cannot be graded until one does"],
        "none")
    # 9 Startup: measured campaign (proposed methodology; row stays Open) --
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
    add(R[9], st_metrics, "partial", [
        "proposed methodology (DR-0009) only; the target's 'controlled ramp' has no numeric bound and is not graded",
        "one load/Cout/ESR point only: 1 mA, 1 uF, 0 ohm ESR -- not 0-50 mA, 0.33-4.7 uF, 0-500 mohm",
        "Vin grid is 2.97/3.30/3.63 V; Cc and the 0.90 V reference are not cornered; schematic level, no post-layout evidence",
    ] + ([f"{len(su['missing'])} requested point(s) missing and {su['n_insufficient']} insufficient of "
          f"{su['n_requested']}"] if su["missing"] or su["n_insufficient"] else []), st_state, row_verdict=st_verdict,
        notes=[f"Measured: {len(ev)} of {su['n_requested']} requested points evaluated, "
               f"{su['n_fail']} fail, {su['n_pass']} pass, {su['n_insufficient']} insufficient, "
               f"{len(su['missing'])} missing ({su_rel}). {n_settled_and_failing} of {n_settled} points "
               "that settle within 3 ms still fail the proposed overshoot / monotonicity checks.",
               "Proposed methodology, not ratified: DR-0007 row 9 stays Open; no ratification and no whole-spec pass is inferred."])
    rows[-1]["startup_campaign"] = startup_summary

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
    chk("DC informational summary: pinned, same record, 45 corners once each, finite, validity fields True/False, "
        "raw grids match inventory hashes", True)
    chk("every target row appears exactly once", sorted(r["id"] for r in rows) == list(range(1, 11)),
        f"rows: {[r['id'] for r in rows]}")
    chk("every row carries an allowed verdict", all(r["verdict"] in ROW_VERDICTS for r in rows))
    chk("every row cites a source or an explicit unavailability reason",
        all(all(("source" in m and m["source"]) or m.get("reason") for m in r["metrics"]) for r in rows))
    chk("startup campaign: selected record, csv, manifest and every trace match their pins; no duplicate or "
        "unexpected point; manifest agrees with the csv", True,
        f"{su['n_requested']} requested points, {len(sp)} result rows")
    chk("startup campaign has a result row for every requested point", not su["missing"],
        f"{len(su['missing'])} of {su['n_requested']} requested points missing")
    chk("startup evidence is current against the design (core and error amplifier checked independently)",
        not su["stale_components"],
        "core and error-amplifier netlist hashes match the startup freshness pins" if not su["stale_components"]
        else "stale against the design: " + ", ".join(su["stale_components"]))
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
            "Row 9 (Startup) reports the explicitly selected committed startup campaign: measured failures are measured failures, missing or insufficient points are never passes, and the evaluation methodology is PROPOSED (DR-0009), not ratified. Row 9 stays Open.",
            "Other T1 items are not declared satisfied by this artifact.",
        ],
        "selection": {
            "file": "sim/characterization/selection.json",
            "sha256": sha256_file(root / "sim/characterization/selection.json"),
            "circuit_record_id": rec["id"],
            "experiment": rec["experiment"],
            "device_context_record_id": dev["id"],
            "startup_record_id": su["rid"],
            "startup_stage": su["cfg"]["stage"],
            "policy": sel["policy"],
        },
        "sources": sorted(sources, key=lambda s: (s["role"], s["path"])),
        "design_freshness": {"state": evidence_state, "basis": rec["design_freshness_basis"],
                             "pins": fresh_checks},
        "bench_conditions": bc,
        "cc_tolerance_window": ccw,
        "dc_informational_evidence": {
            "summary": dc_rel, "inventory": dcev["inventory_path"],
            "raw_dc_grids_verified": dcev["n_raw_grids"], "points": 45,
            "status": "informational only; rows 5 and 7 remain Open/unratified; not item-5 grading evidence",
        },
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
    if not at:
        return "-"
    base = f"{at['corner']}/{at['temp_c']}C/{at['res_section']}"
    if "vin_v" in at:
        base += (f"/Vin {at['vin_v']:g}V/{at['load_ma']:g}mA/{at['cout_nf']:g}nF/"
                 f"ESR {at['esr_mohm']:g}mohm")
    return base


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
    w(f"- Startup campaign (explicitly selected, hash-pinned, proposed methodology): `{sel['startup_record_id']}` stage `{sel['startup_stage']}`")
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
        if r.get("startup_campaign"):
            c = r["startup_campaign"]
            w("- **Startup campaign (measured; PROPOSED methodology, row stays Open; no ratification inferred)**")
            w(f"  - record `{c['record_id']}` stage `{c['stage']}` ({c['source']['record_md']}, {c['source']['csv']})")
            w(f"  - requested {c['requested_points']}, result rows {c['result_rows']}, evaluated {c['evaluated_points']}, "
              f"missing {c['missing_points']}, insufficient {c['insufficient_points']}; "
              f"csv verdicts pass {c['csv_verdicts']['pass']} / fail {c['csv_verdicts']['fail']} / "
              f"insufficient {c['csv_verdicts']['insufficient']}")
            w(f"  - {c['settled_within_3ms_but_failing_points']} of {c['settled_within_3ms_points']} points settle within 3 ms "
              "and still fail the proposed overshoot / monotonicity checks")
            w("  - failure reasons (points): " + ", ".join(f"{k} {v}" for k, v in c["failure_reasons_point_counts"].items()))
            for mp in c["missing"][:10]:
                w(f"  - missing point: {_fmt_at(mp)}")
            w(f"  - design freshness: **{c['design_freshness']['state']}**; "
              + "; ".join(f"{k} {'matches' if e['matches'] else 'DIFFERS'} (`{e['path']}`)"
                          for k, e in c["design_freshness"]["components"].items()))
            for label, e in c["extrema"].items():
                w(f"  - {label}: min {e['min']['value']:.6g} at {_fmt_at(e['min']['at'])}; "
                  f"max {e['max']['value']:.6g} at {_fmt_at(e['max']['at'])}")
            pm_ = c["proposed_methodology"]
            w(f"  - proposed methodology: band {pm_['band_v'][0]}-{pm_['band_v'][1]} V, settle <= {pm_['settle_limit_s']} s, "
              f"monotonic tolerance {pm_['monotonic_tolerance_v']} V ({pm_['reference']}); {pm_['note']}")
            w(f"  - {c['ratification']}")
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
            if "n_invalid" in m:
                w(f"  - validity: {m['n_points'] - m['n_invalid']} valid, {m['n_invalid']} invalid "
                  "(invalid points are counted, not dropped)")
            if m.get("precision_floor_uA") is not None:
                w(f"  - precision floor: print quantum 1e-10 A; solver-noise proxy {m['precision_floor_uA']} uA")
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
