"""Shared parser for the tb_dcsweep_cmos5l.spice.tmpl `wrdata` output.

Extracted verbatim from the inline Python in run_sweep.sh (issue #55) so the
sweep's post-processing and sim/ldo-cmos5l-pvt-sweep/item5_evidence.py read
the raw DC grid with ONE interpretation.  Behaviour is unchanged: the
committed record CSVs reproduce from the committed raw files (checked by
item5_evidence.py and test_item5_evidence.py).
"""
import math  # noqa: F401  (kept for parity with the inline original)

VOUT_TARGET = 1.8
VIN_MIN, VIN_MAX, VIN_STEP = 2.00, 3.63, 0.01


def read_wrdata(path, ncols):
    """wrdata prints a redundant (scale, value) pair per requested vector
    (see sim/pass-device-screening/README.md's own documented gotcha)."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) < ncols:
                    continue
                rows.append([float(x) for x in parts])
    except FileNotFoundError:
        return []
    return rows


def dc_metrics(path):
    """Parse a tb_dcsweep_cmos5l _dc.csv: columns
    (scale,v(vin),scale,v(vout),scale,i(vin),scale,i(vdivsense)) x N rows,
    nested sweep with Vin as the fast/inner variable and Iload as the
    slow/outer variable (see that template's header). i(vdivsense) is the
    feedback divider's own standing current, read off the non-invasive
    rhigh replica that template instantiates (issue #31). Detect
    Iload-block boundaries by watching Vin reset to a smaller value than
    the previous row."""
    rows = read_wrdata(path, 8)
    if not rows:
        return None
    blocks = []
    cur = []
    prev_vin = None
    for r in rows:
        vin = r[1]
        if prev_vin is not None and vin < prev_vin - 1e-9:
            blocks.append(cur)
            cur = []
        cur.append((vin, r[3], r[5], r[7]))
        prev_vin = vin
    blocks.append(cur)
    if len(blocks) < 5:
        return {"error": f"expected 5 Iload blocks, got {len(blocks)}"}

    def nearest(block, vin_target):
        return min(block, key=lambda t: abs(t[0] - vin_target))

    out = {}
    # Iq + no-load op point + divider standing current, block 0 (Iload=0),
    # Vin=3.30V.
    v, vo, i, idiv = nearest(blocks[0], 3.30)
    out["iq_a"] = abs(i)
    out["vout_no_load_v"] = vo
    out["i_divider_a"] = abs(idiv)
    # Per-leg divider resistance implied by the measured current: both legs
    # are the same drawn device and FB draws no DC current, so
    # R_leg = (VOUT/2) / I_div.
    out["r_divider_leg_ohm"] = (vo / 2.0) / abs(idiv) if idiv else float("nan")

    # Line regulation, block 0 (no load), Input row's {2.97,3.63}V window.
    v_lo, vo_lo, _, _ = nearest(blocks[0], 2.97)
    v_hi, vo_hi, _, _ = nearest(blocks[0], 3.63)
    out["line_reg_in_regulation"] = abs(vo_lo - VOUT_TARGET) < 0.01 * VOUT_TARGET and abs(vo_hi - VOUT_TARGET) < 0.01 * VOUT_TARGET
    out["line_reg_mv_per_v"] = (vo_hi - vo_lo) / (v_hi - v_lo) * 1000.0

    # Dropout @ 50mA, last block (Iload=0.05A): scan from Vin_max downward
    # for the first point where VOUT falls below 0.99x the fixed 1.8V
    # target (README.md "Nested DC sweep").
    block50 = sorted(blocks[-1], key=lambda t: t[0])
    v_at_max, vo_at_max, _, _ = block50[-1]
    out["vout_at_vinmax_50ma_v"] = vo_at_max
    dropout_v = None
    for v, vo, _, _ in reversed(block50):
        if vo < 0.99 * VOUT_TARGET:
            break
        dropout_v = v - VOUT_TARGET
    out["dropout_v_50ma"] = dropout_v  # None => never left regulation down to VIN_MIN
    out["dropout_v_50ma_floor"] = VIN_MIN - VOUT_TARGET  # reported when dropout_v is None

    # Load regulation: Vin=3.63V row in every block.
    vouts_at_vinmax = [nearest(b, 3.63)[1] for b in blocks]
    out["vout_at_vinmax_by_load"] = vouts_at_vinmax  # [0,12.5m,25m,37.5m,50m]
    if vouts_at_vinmax[0] != 0:
        out["load_reg_pct"] = (vouts_at_vinmax[0] - vouts_at_vinmax[-1]) / vouts_at_vinmax[0] * 100.0
    else:
        out["load_reg_pct"] = float("nan")
    return out
