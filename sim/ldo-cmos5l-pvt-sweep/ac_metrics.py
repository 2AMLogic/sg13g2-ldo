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
