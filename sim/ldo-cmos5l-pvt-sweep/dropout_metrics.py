"""Row-4 dropout reducer for DR-0009 (issue #70, PROPOSED).

Lives beside dc_metrics.py, not inside it, on purpose: item5_evidence.py pins
dc_metrics.py's and its own sha256 in the committed, append-only
evidence/<record-id>/ inventories, so editing either would silently drift
those historical artifacts.  This module reuses dc_metrics' wrdata reader and
constants, so the repository still has ONE DC-grid interpretation.
"""
import math

from dc_metrics import VOUT_TARGET, read_wrdata


# --------------------------------------------------------------------------
# Row-4 dropout, DR-0009 definition (issue #70).  PROPOSED, not ratified.
#
# This is a SECOND, distinctly named quantity.  It never replaces or
# re-labels `dropout_v_50ma` above (the legacy "lowest 10 mV-grid Vin that
# still regulates, minus the fixed 1.8 V target"), whose historical records
# stay readable.  Field names carry the definition:
#   legacy:    dropout_v_50ma           (dropout_legacy_v in item5_evidence)
#   DR-0009:   dropout_1pct_vin_minus_vout_v  (+ _upper_v / _lower_v bracket)
# ---------------------------------------------------------------------------
DR0009_LOSS = 0.01           # 1 % output loss
DR0009_VIN_REF = 3.30        # regulated-output reference supply (Input row nominal)
DR0009_VIN_LO, DR0009_VIN_HI, DR0009_VIN_STEP = 1.70, 3.63, 0.005
DR0009_ROWS = 387            # 1.700 .. 3.630 V at 5 mV, one 50 mA block
DR0009_LOAD_A = 0.05
_EPS = 1e-9


def dropout_1pct(points, vin_ref=DR0009_VIN_REF, loss=DR0009_LOSS):
    """DR-0009 dropout of ONE 50 mA load block.

    `points` is an iterable of (vin, vout).  Definition:
      * V_reg  = VOUT at the reference supply `vin_ref` (same corner, same
        50 mA load), i.e. the corner's own regulated output, not 1.8 V;
      * V_thr  = (1 - loss) * V_reg;
      * scan downward from `vin_ref`; the crossing is the first adjacent
        grid pair (hi, lo) with VOUT(hi) >= V_thr > VOUT(lo);
      * Vin* is the linear interpolation of Vin at VOUT = V_thr in that
        pair (an exact-threshold grid point gives Vin* = that point);
      * dropout = Vin* - V_thr, i.e. VIN - VOUT(actual) at the crossing.
    Because the true crossing lies in [vin_lo, vin_hi], the result carries
    its bracket: `_lower_v = vin_lo - V_thr`, `_upper_v = vin_hi - V_thr`.
    Verdict-grade use must take `_upper_v` (conservative).

    Never raises.  Returns {"status": ..., ...}; only status "resolved"
    carries a value.  Other statuses: "malformed", "reference_out_of_regulation",
    "floor_limited_upper_bound" (no crossing down to the lowest swept Vin:
    only an upper bound exists, reported as `_upper_v`, value None).
    """
    try:
        pts = sorted((float(v), float(o)) for v, o in points)
    except (TypeError, ValueError):
        return {"status": "malformed", "reason": "non-numeric point"}
    if len(pts) < 3:
        return {"status": "malformed", "reason": f"{len(pts)} points"}
    if any(not (math.isfinite(v) and math.isfinite(o)) for v, o in pts):
        return {"status": "malformed", "reason": "non-finite value"}
    if any(b[0] - a[0] <= _EPS for a, b in zip(pts, pts[1:])):
        return {"status": "malformed", "reason": "duplicate or non-increasing Vin"}
    ref = [i for i, (v, _) in enumerate(pts) if abs(v - vin_ref) < _EPS]
    if not ref:
        return {"status": "malformed", "reason": f"reference Vin {vin_ref} V not in block"}
    i_ref = ref[0]
    v_reg = pts[i_ref][1]
    out = {"v_reg_v": v_reg, "v_thr_v": (1.0 - loss) * v_reg, "vin_min_v": pts[0][0]}
    if abs(v_reg - VOUT_TARGET) >= loss * VOUT_TARGET:
        out["status"] = "reference_out_of_regulation"
        return out
    thr = out["v_thr_v"]
    for i in range(i_ref - 1, -1, -1):
        if pts[i][1] < thr - _EPS:
            (v_lo, o_lo), (v_hi, o_hi) = pts[i], pts[i + 1]
            vx = v_lo + (thr - o_lo) * (v_hi - v_lo) / (o_hi - o_lo)
            out.update(status="resolved", vin_cross_v=vx,
                       dropout_1pct_vin_minus_vout_v=vx - thr,
                       dropout_1pct_lower_v=v_lo - thr,
                       dropout_1pct_upper_v=v_hi - thr,
                       bracket_v=v_hi - v_lo)
            return out
    out.update(status="floor_limited_upper_bound",
               dropout_1pct_upper_v=pts[0][0] - thr)
    return out


def dropout_1pct_file(path, expect_rows=DR0009_ROWS):
    """Read one campaign `*_dc.csv` (wrdata of v(vin) v(vout) i(vin)) and
    apply `dropout_1pct`.  The file must be exactly ONE complete load block
    of `expect_rows` rows spanning DR0009_VIN_LO..DR0009_VIN_HI; a missing,
    truncated, multi-block or wrongly spanned file is "malformed" (the point
    stays in the accounting, it is never dropped)."""
    rows = read_wrdata(path, 6)
    if not rows:
        return {"status": "malformed", "reason": "missing or empty grid"}
    vins = [r[1] for r in rows]
    if any(b < a - _EPS for a, b in zip(vins, vins[1:])):
        return {"status": "malformed", "reason": "Vin resets: more than one load block"}
    if len(rows) != expect_rows:
        return {"status": "malformed", "reason": f"{len(rows)} rows, expected {expect_rows}"}
    if abs(vins[0] - DR0009_VIN_LO) > 1e-6 or abs(vins[-1] - DR0009_VIN_HI) > 1e-6:
        return {"status": "malformed", "reason": f"Vin span {vins[0]}..{vins[-1]}"}
    res = dropout_1pct([(r[1], r[3]) for r in rows])
    res["rows"] = len(rows)
    return res
