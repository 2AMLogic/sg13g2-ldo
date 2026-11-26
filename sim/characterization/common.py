"""Shared targets, evidence pins and metric calculations for characterization."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from ..tools import file_hash

GENERATOR_VERSION = 1
HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent

REPORT_JSON = "characterization-report.json"
REPORT_MD = "characterization-report.md"
ENVELOPE_JSON = "characterization-envelope.json"

# The grading thresholds were written against this exact README target text.
# A mismatch stops generation so the thresholds can be reviewed.
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

# Row 7's graded envelope (issue #317): a `klt sim` request whose limits live
# inside the request, so the per-corner and whole-matrix verdict is the tool's
# own. Six operating points per corner (Vin x Iload), graded as derived expr
# measurements over each step's raw supply current -- never an offline
# subtraction of printed ~50 mA currents.
ROW7_SPEC_ROW_ID = "dr0007-row7-iq"
ROW7_VINS = (("v2v97", 2.97), ("v3v30", 3.30), ("v3v63", 3.63))
ROW7_LOADS = (("i0", 0.0), ("i50m", 0.050))
ROW7_GRADED = tuple(f"iq_{ln}_{vn}_a" for vn, _ in ROW7_VINS for ln, _ in ROW7_LOADS)
ROW7_TARGET_A = 30e-6
ROW7_ENV_COND = ("Vin {2.97, 3.30, 3.63} V x Iload {0, 50 mA} per corner (six analysis_steps "
                 "operating points), Iq = |i(VIN)| - Iload graded by `klt sim` as derived-expr "
                 "measurements with limits in the request (spec_row dr0007-row7-iq); solver "
                 "tolerances pinned reltol=1e-9 abstol=1e-15 (a convergence setting, not an error "
                 "bound; observed sensitivity is the paired tight-tolerance record); ideal "
                 "0.90 V reference and ideal 2 uA IBIAS sink, no #190 limiter; 45-point corner "
                 "grid")
# The envelope is a DIFFERENT bench from the legacy PVT sweep (direct OP solves
# on the fleet's ngspice at pinned tolerances vs a nested-sweep row harvest at
# ngspice-46 defaults), so agreement with the legacy columns is a consistency
# cross-check with a loose band, not a reproduction claim. Observed worst
# delta at Vin = 3.30 V: 0.37 uA no-load, 0.26 uA full-load.
ROW7_CROSS_BAND_UA = 1.0

# Row 5's graded envelope (issue #319): eight (Vin, Iload) operating points per
# corner; six derived-expr figures (line at three loads, load regulation at three
# supplies) with the row's limits inside the request, so the verdict is `klt sim`'s
# own. DR-0007 row 5 is a STRICT "<"; klt's inclusive `max` means equality is
# refused here, not credited.
ROW5_SPEC_ROW_ID = "dr0007-row5-line-load-regulation"
ROW5_LINE_LOADS = ("i0", "i25m", "i50m")
ROW5_LOAD_VINS = ("v2v97", "v3v30", "v3v63")
ROW5_LINE_GRADED = tuple(f"line_{ln}_mvpv" for ln in ROW5_LINE_LOADS)
ROW5_LOAD_GRADED = tuple(f"load_{vn}_pct" for vn in ROW5_LOAD_VINS)
ROW5_LIMITS = {**{n: {"max": 5.0} for n in ROW5_LINE_GRADED},
               **{n: {"max": 1.0} for n in ROW5_LOAD_GRADED}}
ROW5_STEPS = {  # step name -> (Vin, Iload)
    "v2v97_i0": (2.97, 0.0), "v2v97_i25m": (2.97, 0.025), "v2v97_i50m": (2.97, 0.050),
    "v3v30_i0": (3.30, 0.0), "v3v30_i50m": (3.30, 0.050),
    "v3v63_i0": (3.63, 0.0), "v3v63_i25m": (3.63, 0.025), "v3v63_i50m": (3.63, 0.050),
}
# The legacy offline DC columns are signed and printed to 9 digits; the envelope
# grades |.| from direct OP solves, so the cross-check is loose. Observed worst
# delta: 0.0020 mV/V (line, 0 mA), 0.0012 % (load).
ROW5_CROSS_BAND_LINE_MV_PER_V = 0.01
ROW5_CROSS_BAND_LOAD_PCT = 0.005
ROW5_ENV_COND = ("eight analysis_steps operating points per corner (Vin 2.97 / 3.63 V x Iload "
                 "0 / 25 / 50 mA, plus Vin 3.30 V at 0 / 50 mA); line = 1000*|Vout(3.63 V) - "
                 "Vout(2.97 V)|/0.66 at three loads, load regulation = 100*|Vout(0) - "
                 "Vout(50 mA)|/Vout(0) at three supplies, graded by `klt sim` as derived-expr "
                 "measurements with limits in the request (spec_row "
                 "dr0007-row5-line-load-regulation); solver tolerances pinned reltol=1e-9 "
                 "abstol=1e-15 (a convergence setting, not an error bound); ideal 0.90 V "
                 "reference; discrete sampling only; 45-point corner grid")

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
        return file_hash.sha256_file(path)
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
