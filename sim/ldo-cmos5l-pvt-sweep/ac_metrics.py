"""Shared AC-bench parsers for tb_loopgain_cmos5l / tb_psrr_cmos5l wrdata.

Extracted verbatim from the inline Python in run_sweep.sh (issue #64) so the
legacy 45-point post-processing and dynamic_doe.py read AC data with ONE
interpretation. Behaviour is unchanged.
"""
import math

from dc_metrics import read_wrdata


def unwrap_deg(phases):
    out = [phases[0]]
    offset = 0.0
    for p in phases[1:]:
        d = (p + offset) - out[-1]
        while d > 180.0:
            offset -= 360.0
            d = (p + offset) - out[-1]
        while d < -180.0:
            offset += 360.0
            d = (p + offset) - out[-1]
        out.append(p + offset)
    return out


def loopgain_metrics(path):
    rows = read_wrdata(path, 4)
    if not rows:
        return None
    freqs = [r[0] for r in rows]
    dbs = [r[1] for r in rows]
    degs_unwrapped = unwrap_deg([r[3] for r in rows])

    out = {"dc_gain_db": dbs[0]}

    # All 0dB crossings (log-interp freq, linear-interp unwrapped phase).
    crossings = []
    for i in range(1, len(dbs)):
        if (dbs[i - 1] - 0) * (dbs[i] - 0) < 0:
            frac = (0 - dbs[i - 1]) / (dbs[i] - dbs[i - 1])
            logf = math.log10(freqs[i - 1]) + frac * (math.log10(freqs[i]) - math.log10(freqs[i - 1]))
            f_cross = 10 ** logf
            deg_cross = degs_unwrapped[i - 1] + frac * (degs_unwrapped[i] - degs_unwrapped[i - 1])
            crossings.append((f_cross, deg_cross))
    out["n_0db_crossings"] = len(crossings)
    if crossings:
        f0, deg0 = crossings[0]
        out["unity_gain_freq_hz"] = f0
        out["phase_margin_deg"] = 180.0 + deg0
        out["phase_margin_worst_deg"] = min(180.0 + d for _, d in crossings)
    else:
        out["unity_gain_freq_hz"] = None
        out["phase_margin_deg"] = None
        out["phase_margin_worst_deg"] = None

    # First -180deg (mod 360) unwrapped-phase crossing -> gain margin.
    gm_crossings = []
    for i in range(1, len(degs_unwrapped)):
        target = -180.0
        while target > max(degs_unwrapped[i - 1], degs_unwrapped[i]):
            target -= 360.0
        while target < min(degs_unwrapped[i - 1], degs_unwrapped[i]) - 360.0:
            target += 360.0
        lo, hi = degs_unwrapped[i - 1], degs_unwrapped[i]
        if (lo - target) * (hi - target) < 0 and abs(hi - lo) < 180.0:
            frac = (target - lo) / (hi - lo)
            logf = math.log10(freqs[i - 1]) + frac * (math.log10(freqs[i]) - math.log10(freqs[i - 1]))
            f_cross = 10 ** logf
            db_cross = dbs[i - 1] + frac * (dbs[i] - dbs[i - 1])
            gm_crossings.append((f_cross, db_cross))
    out["n_gain_margin_crossings"] = len(gm_crossings)
    if gm_crossings:
        f0, db0 = gm_crossings[0]
        out["gain_margin_freq_hz"] = f0
        out["gain_margin_db"] = -db0
    else:
        out["gain_margin_freq_hz"] = None
        out["gain_margin_db"] = None
    return out


# --------------------------------------------------------------------------- #
# DR-0014 (proposed): row-10 margin classification
# --------------------------------------------------------------------------- #
# loopgain_metrics() above stays byte-for-byte what produced the committed
# records (first 0 dB crossing, first -180 deg crossing). classify_margins()
# below is the separate DR-0014 reading of the same trace: every crossing in
# the sweep, an angular per-crossing margin, an explicit low-end and ceiling
# premise, and a pass / fail / ambiguous verdict that is never a pass unless
# the trace itself supports it. See
# spec/decision-records/DR-0014-row10-stability-margin-classification.md.

PM_BOUND_DEG = 45.0       # row 10 target (README / DR-0007), unchanged
GM_BOUND_DB = 10.0        # row 10 target (README / DR-0007), unchanged
CEILING_FLOOR_DB = -GM_BOUND_DB   # loop gain at the sweep ceiling must be <= this


def wrap180(deg):
    """Wrap a phase into (-180, 180]."""
    x = math.fmod(deg + 180.0, 360.0)
    if x <= 0.0:
        x += 360.0
    return x - 180.0


def critical_distance_deg(phase_deg):
    """Angular distance of a unit-magnitude loop gain at `phase_deg` from the
    critical point (phase = 180 mod 360). Equals the classic 180 + phase for
    phase in (-180, 0]; for -342 deg (== +18 deg) it is 162, not -162."""
    return 180.0 - abs(wrap180(phase_deg))


def _lines_between(a, b, offset):
    """Phase lines offset + 360 k that the segment a -> b crosses (half-open:
    a line is crossed when the two samples sit on different sides of it, a
    sample exactly on a line counting as below it)."""
    lo, hi = min(a, b), max(a, b)
    k = math.ceil((lo - offset) / 360.0)
    out = []
    while offset + 360.0 * k <= hi:
        t = offset + 360.0 * k
        if (a > t) != (b > t):
            out.append(t)
        k += 1
    return out


def ceiling_bounded(ceiling_gain_db, last_decade_non_increasing, floor_db=CEILING_FLOOR_DB):
    """DR-0014 ceiling premise: the trace ends at least |floor_db| below unity
    and was non-increasing over its last decade."""
    return last_decade_non_increasing and ceiling_gain_db <= floor_db


def _logf(f0, f1, frac):
    return 10 ** (math.log10(f0) + frac * (math.log10(f1) - math.log10(f0)))


def classify_margins_trace(freqs, dbs, phases, pm_bound=PM_BOUND_DEG,
                           gm_bound=GM_BOUND_DB, floor_db=CEILING_FLOOR_DB):
    """Classify one loop-gain trace under DR-0014.

    freqs [Hz], dbs [dB of L], phases [deg of L, wrapped as written by the
    simulator]. Returns a dict with the crossings, the two premises and a PM
    and a GM verdict, each one of 'pass' | 'fail' | 'ambiguous' with reasons.

    - PM: every 0 dB crossing in the sweep, margin = critical_distance_deg of
      the interpolated phase, bracketed by the two samples around it. The
      scored PM is the minimum over crossings.
    - GM: every crossing of a critical phase line (180 mod 360), margin = minus
      the interpolated gain, bracketed by the two samples around it. The scored
      GM is the minimum over those crossings.
    - fail: some crossing's interpolated margin is below the bound (the same
      interpolation the records use). More bandwidth can only add crossings,
      so a miss inside the sweep is a miss.
    - pass: every crossing's whole sample bracket clears the bound, both
      premises hold, and (for PM) no critical-line crossing happens with the
      loop gain at or above unity. A bracket that straddles the bound blocks a
      pass (resolution_limited) but never turns a miss into anything else.
    - ambiguous: everything else, with the reasons listed.
    """
    n = len(freqs)
    out = {"rule": "DR-0014", "valid": True, "n_points": n,
           "bounds": {"pm_deg": pm_bound, "gm_db": gm_bound, "ceiling_floor_db": floor_db}}
    bad = (n < 4 or len(dbs) != n or len(phases) != n
           or any(not math.isfinite(v) for v in list(freqs) + list(dbs) + list(phases))
           or any(f <= 0 for f in freqs)
           or any(freqs[i] <= freqs[i - 1] for i in range(1, n)))
    if bad:
        out["valid"] = False
        for k in ("pm", "gm"):
            out[k] = {"verdict": "ambiguous", "reasons": ["invalid_trace"]}
        out.update({"zero_db_crossings": [], "critical_crossings": [], "low_end": None,
                    "ceiling": None, "nyquist": {"in_band_net_crossings": None,
                                                 "class": "undetermined"}})
        out["pm"]["value_deg"] = None
        out["gm"].update({"value_db": None, "above_ceiling_lower_bound_db": None})
        return out
    ph = unwrap_deg(list(phases))
    out["sweep_hz"] = [freqs[0], freqs[-1]]

    # -- premises -----------------------------------------------------------
    first = [i for i in range(n) if freqs[i] <= freqs[0] * 10.0]
    last = [i for i in range(n) if freqs[i] >= freqs[-1] / 10.0]
    first_ok = all(dbs[i] <= dbs[i - 1] for i in first[1:])
    last_ok = all(dbs[i] <= dbs[i - 1] for i in last[1:])
    low_ok = dbs[0] > 0.0 and first_ok
    out["low_end"] = {"gain_db": dbs[0], "phase_deg": ph[0],
                      "first_decade_non_increasing": first_ok, "ok": low_ok}
    bounded = ceiling_bounded(dbs[-1], last_ok, floor_db)
    out["ceiling"] = {"gain_db": dbs[-1], "phase_deg": ph[-1],
                      "last_decade_non_increasing": last_ok,
                      "last_decade_gain_change_db": dbs[-1] - dbs[last[0]],
                      "bounded": bounded}

    # -- critical-line crossings (phase = 180 mod 360) ----------------------------
    cc = []
    for i in range(1, n):
        for t in _lines_between(ph[i - 1], ph[i], 180.0):
            frac = (t - ph[i - 1]) / (ph[i] - ph[i - 1])
            g = dbs[i - 1] + frac * (dbs[i] - dbs[i - 1])
            glo, ghi = min(dbs[i - 1], dbs[i]), max(dbs[i - 1], dbs[i])
            # above_unity follows the interpolation (as every recorded number
            # does); unity_resolved says whether the two samples agree on it.
            cc.append({"freq_hz": _logf(freqs[i - 1], freqs[i], frac),
                       "phase_line_deg": t,
                       "direction": "falling" if ph[i] < ph[i - 1] else "rising",
                       "gain_db": g, "gain_bracket_db": [glo, ghi],
                       "above_unity": g > 0.0,
                       "unity_resolved": glo > 0.0 or ghi <= 0.0})
    out["critical_crossings"] = cc

    # -- 0 dB crossings -------------------------------------------------------
    # Each margin is the angular distance to the critical point, signed by the
    # running count of critical-line crossings made ABOVE unity since the
    # sweep floor (DR-0014 rule 3): count 0 -> +distance (not encircled), count
    # != 0 -> -distance (the classic negative PM of a loop that has already
    # passed the critical point). If an earlier critical crossing is not
    # resolved against unity by its samples, the bracket spans both signs.
    zc = []
    for i in range(1, n):
        a, b = dbs[i - 1], dbs[i]
        if (a > 0.0) == (b > 0.0):
            continue
        frac = (0.0 - a) / (b - a)
        fz = _logf(freqs[i - 1], freqs[i], frac)
        p = ph[i - 1] + frac * (ph[i] - ph[i - 1])
        da, db_ = critical_distance_deg(ph[i - 1]), critical_distance_deg(ph[i])
        lo, hi = min(da, db_), max(da, db_)
        if _lines_between(ph[i - 1], ph[i], 180.0):
            lo = 0.0
        if _lines_between(ph[i - 1], ph[i], 0.0):
            hi = 180.0
        before = [c for c in cc if c["freq_hz"] < fz]
        count = sum(-1 if c["direction"] == "falling" else 1
                    for c in before if c["above_unity"])
        sign = 1.0 if count == 0 else -1.0
        bracket = [lo, hi] if count == 0 else [-hi, -lo]
        if not all(c["unity_resolved"] for c in before):
            bracket = [-hi, hi]
        zc.append({"freq_hz": fz,
                   "direction": "falling" if b < a else "rising",
                   "phase_deg": p, "net_crossings_above_unity_before": count,
                   "distance_deg": critical_distance_deg(p),
                   "distance_bracket_deg": [lo, hi],
                   "margin_deg": sign * critical_distance_deg(p),
                   "margin_bracket_deg": bracket})
    out["zero_db_crossings"] = zc

    # -- Nyquist bookkeeping (open-loop-stable premise, DR-0014 P0) ------------
    net = sum(-1 if c["direction"] == "falling" else 1 for c in cc if c["above_unity"])
    n_above = sum(1 for c in cc if c["above_unity"])
    if not (low_ok and bounded and all(c["unity_resolved"] for c in cc)):
        ncls = "undetermined"
    elif net != 0:
        ncls = "unstable"
    elif n_above:
        ncls = "conditionally_stable"
    else:
        ncls = "stable"
    out["nyquist"] = {"in_band_net_crossings": net, "class": ncls}

    common = []
    if not low_ok:
        common.append("low_end_premise_failed")

    # -- PM verdict -----------------------------------------------------------
    # A crossing whose interpolated distance from the critical point is below
    # the bound fails on magnitude alone (the recorded convention; a bracket
    # that straddles the bound never upgrades a miss). A crossing made after an
    # in-band encirclement fails on its sign, which needs the low-end premise
    # (the count starts at zero at the sweep floor).
    pm_val = min((c["margin_deg"] for c in zc), default=None)
    if any(c["distance_deg"] < pm_bound for c in zc) or (
            low_ok and any(c["margin_deg"] < pm_bound for c in zc)):
        pm = {"verdict": "fail", "reasons": ["in_band_crossing_below_bound"]}
    else:
        r = list(common)
        if not zc:
            r.append("no_zero_db_crossing")
        if any(c["margin_bracket_deg"][0] < pm_bound for c in zc):
            r.append("resolution_limited")
        if any(c["above_unity"] or not c["unity_resolved"] for c in cc):
            r.append("critical_crossing_at_or_above_unity")
        if not bounded:
            r.append("ceiling_unbounded")
        pm = {"verdict": "ambiguous" if r else "pass", "reasons": r}
    pm["value_deg"] = pm_val
    out["pm"] = pm

    # -- GM verdict -----------------------------------------------------------
    gm_val = min((-c["gain_db"] for c in cc), default=None)
    if any(-c["gain_db"] < gm_bound for c in cc):
        gm = {"verdict": "fail", "reasons": ["in_band_crossing_below_bound"]}
    else:
        r = list(common)
        if any(-c["gain_bracket_db"][1] < gm_bound for c in cc):
            r.append("resolution_limited")
        if not bounded:
            r.append("ceiling_unbounded")
        gm = {"verdict": "ambiguous" if r else "pass", "reasons": r}
    gm["value_db"] = gm_val
    gm["above_ceiling_lower_bound_db"] = -dbs[-1] if bounded else None
    out["gm"] = gm
    return out


def classify_margins(path, **kw):
    """classify_margins_trace() on a tb_loopgain_cmos5l wrdata file (4 columns:
    f, dB, f, deg). None if the file is missing or has no usable rows."""
    rows = read_wrdata(path, 4)
    if not rows:
        return None
    return classify_margins_trace([r[0] for r in rows], [r[1] for r in rows],
                                  [r[3] for r in rows], **kw)


def psrr_metrics(path):
    rows = read_wrdata(path, 2)
    if not rows:
        return None
    def nearest(freq_target):
        return min(rows, key=lambda r: abs(math.log10(r[0]) - math.log10(freq_target)))
    return {
        "psrr_db_1khz": nearest(1e3)[1],
        "psrr_db_100khz": nearest(1e5)[1],
    }
