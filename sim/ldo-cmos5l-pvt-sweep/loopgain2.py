#!/usr/bin/env python3
"""Two-injection (Middlebrook) loop-gain reconstruction (issue #135).

Offline, stdlib-only: reconstructs the SG13CMOS5L loop gain at the FB/FBAMP
break from the RAW COMPLEX probe responses of the two-injection benches and
compares it with the single-injection bench, WITHOUT re-running a simulator
and without the single-injection method's zero-gate-current assumption.

Method. Middlebrook's GENERAL (bilateral) two-injection result:
R. D. Middlebrook, "Measurement of loop gain in feedback systems",
Int. J. Electronics 38(4):485-512 (1975). Tian, Visvanathan, Hantgan and
Kundert, "Striving for small-signal stability", IEEE Circuits & Devices
17(1):31-41 (2001) reach the same T from a single test structure. We do not
lean on either citation: the formula is derived below from the break's
two-port, and test_loopgain2.py checks it against a small circuit solved
directly by nodal analysis (finite input loading, a bilateral feed-through,
Bode's return ratio and the closed-loop poles).

Two-port at the break. Cut the FB -> FBAMP wire. Port A = FB (the divider
node, the RETURN side), port B = FBAMP (the amplifier input, the FORWARD
side), both against ground. The rest of the circuit is a linear two-port
with currents INTO it
    i_A = y11 v_A + y12 v_B,      i_B = y21 v_A + y22 v_B.
No assumption is made about y21 (reverse transmission, e.g. Cgd
feed-through) or about the loading y22 (the input-pair gate).

  Voltage injection (tb_loopgain2v: `Vbreak FB FBAMP 0 ac 1`, so
  v_A - v_B = 1 and i_A + i_B = 0). Middlebrook's
      Tv = -v_y/v_x = -v(fb)/v(fbamp) = (y12 + y22)/(y11 + y21).
  Tv is exactly what the single-injection bench reports as L.

  Current injection (tb_loopgain2i: loop INTACT behind `Vmeas FB FBAMP 0`,
  shunt `Iinx 0 FBAMP dc 0 ac 1` pushing ix = 1 A into FBAMP). The ammeter
  reads the BRIDGE current i_m = i(vmeas), positive FB -> FBAMP (ngspice's
  n+ -> n- branch convention). KCL: i_B = 1 + i_m (into the amplifier
  side, the forward current i_x), i_A = -i_m (into the divider side), and
  the forward-oriented return current is i_y = i_m, so
      Ti = -i_y/i_x = -i_m/(1 + i_m) = (y11 + y12)/(y21 + y22).

  Combination (Middlebrook 1975, general form; per frequency, complex):
      T = (Tv*Ti - 1)/(Tv + Ti + 2) = (y12 - y21)/(y11 + y22 + 2*y21)
      1 + T = (y11 + y12 + y21 + y22)/(y11 + y22 + 2*y21)
  The numerator of 1 + T is the driving-point admittance of the joined
  node, so 1 + T vanishes at the closed-loop natural frequencies. T counts
  only the NON-RECIPROCAL part (y12 - y21) of the transmission across the
  cut: a reciprocal (passive) coupling contributes nothing to T. In the
  unilateral special case (y21 = 0, divider side = Thevenin T'*v_B behind
  Zt, amplifier side = load Zl, u = Zt/Zl) T = -T'/(1 + u), the LOADED
  return ratio, which equals Bode's return ratio of the amplifier's
  controlled source (fixture). The previous revision of this module
  published -T' (the UNLOADED transfer); that quantity does not satisfy
  1 + L = 0 at the closed-loop poles (1 - T' + u = 0 there) and is gone.
  For a bilateral break T differs from the return ratio of any single
  transistor's gm (the loop gain at a bilateral break is not unique; the
  fixture shows the difference); T is the break-point loop gain whose
  1 + T zeros are the closed-loop poles.

  Sign: Tv is positive-real and large at DC for this negative-feedback
  loop and Ti is larger still, so T needs no further sign flip: this
  repo's L convention (large positive real L(0)) is L = T.

Resolution (export quantisation). The fleet exports carry 9 significant
digits (`%.8e`, batch_backend.py), i.e. each real/imag component is exact to
EXPORT_REL_EPS = 5e-9 of itself, so |dz| <= EXPORT_REL_EPS |z| for every
exported complex value z in {v(fb), v(fbamp), i(vmeas)}. With T written in
the raw quantities a = v(fb), b = v(fbamp), m = i_m, n = 1 + m,
    T = (a m - b n)/(2 b n - a n - b m),
the first-order bound per frequency is
    res(f) = EXPORT_REL_EPS * sum_x |dT/dx| |x|,   x in {a, b, m}.
A sample is RESOLVED iff |T| >= RESOLVED_FACTOR * res (error <= 10 %, i.e.
<= 0.83 dB and <= 5.8 deg). Above the loop's crossing T is a near-exact
cancellation (Tv*Ti -> 1 where the cut network is reciprocal), so res
dominates there; the solver's own error inside ngspice is NOT included (it
is not exported) and is assumed smaller than the 9-digit export rounding.

Written trace. The reconstructed trace written for the unchanged DR-0014
classifier holds ONLY the resolved prefix: every sample from 1 Hz up to,
not including, the first unresolved frequency. Nothing is clamped or
invented. Above the cut the point reports n_resolved_above_cut (a
resolved sample there would be a real loop-gain feature the cut hides) and
bound_db_above_cut = max 20*log10(|T| + res), an upper bound on |T| under
the quantisation model. row10_loopgain2.py reports every point whose
reconstruction is truncated below the sweep ceiling as `ambiguous`.

Stated tolerances (see README.md "Loop-gain measurement method --
two-injection"):

  TOL_DECK_IDENTITY  1e-6 relative, complex, below the control's first 0 dB
                     crossing: Tv (2v deck) vs the control trace. The 2v
                     circuit IS the control circuit; a larger deviation is a
                     plumbing bug.
  TOL_LF_AGREE       1e-2 relative (+ res) below f_ugf/10: T vs the control.
                     T - Tv = -(1 + Tv)^2/(Tv + Ti + 2), so this checks the
                     independent current-injection deck: it holds only if
                     |Ti| >> |Tv| at low frequency (the gate is a high-Z
                     load). A polarity or wiring fault in the 2i deck gives
                     an O(1) violation.
  ORIENT_MAX_DEG     45: phase(T at 1 Hz) within 45 deg of 0 (a reversed
                     shunt source or ammeter lands near 180 deg).
  RESOLVED_FACTOR    10 (see above).

Usage:
    loopgain2.py reconstruct --v-csv F --i-csv F --out F
    loopgain2.py report --corners-dir D --ceiling 10g --out-csv F --out-json F
    loopgain2.py record-md --record RID
    loopgain2.py check [--corners-dir D] --ceiling 10g
"""
import argparse
import cmath
import csv
import glob
import json
import math
import os
import sys
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import ac_sweep  # noqa: E402
import ac_metrics as am  # noqa: E402
import dynamic_doe as dyn  # noqa: E402
from dc_metrics import read_wrdata  # noqa: E402

CTL_PREFIX = "loopgain_ctl_"
V_PREFIX = "loopgain2v_"
I_PREFIX = "loopgain2i_"
TWO_PREFIX = "loopgain2_"
SUFFIX = "_ac.csv"
BASELINE_RID = "20261011-070111-5391c68"

FREQ_RTOL = 1e-9           # both decks share one analysis line: exact axis
TOL_DECK_IDENTITY = 1e-6   # Tv (2v) vs control: same circuit, round-trip precision
TOL_LF_AGREE = 1e-2        # |T - L_ctl| <= TOL_LF_AGREE |L_ctl| + res below f_ugf/10
ORIENT_MAX_DEG = 45.0      # phase(T at 1 Hz) must sit within this of 0 deg
EXPORT_REL_EPS = 5e-9      # half a unit in the 9th significant digit (%.8e)
RESOLVED_FACTOR = 10.0     # resolved iff |T| >= RESOLVED_FACTOR * res
MIN_TRACE_ROWS = 4         # ac_metrics.classify_margins_trace needs >= 4 samples

CSV_FIELDS = [
    "corner", "temp_c", "res_section",
    "ctl_dc_gain_db", "ctl_n_0db_crossings", "ctl_unity_gain_freq_hz",
    "ctl_phase_margin_deg", "ctl_phase_margin_worst_deg",
    "ctl_n_gain_margin_crossings", "ctl_gain_margin_freq_hz",
    "ctl_gain_margin_db", "ctl_db_at_100mhz", "ctl_db_at_1ghz", "ctl_db_at_ceiling",
    "ctl_second_crossing_hz",
    "lg2_dc_gain_db", "lg2_n_0db_crossings", "lg2_unity_gain_freq_hz",
    "lg2_phase_margin_deg", "lg2_phase_margin_worst_deg",
    "lg2_n_gain_margin_crossings", "lg2_gain_margin_freq_hz",
    "lg2_gain_margin_db", "lg2_db_at_100mhz", "lg2_second_crossing_hz",
    "lg2_resolved_to_hz", "lg2_db_at_resolved_to", "ctl_db_at_lg2_resolved_to",
    "lg2_first_unresolved_hz", "lg2_n_unresolved",
    "lg2_n_resolved_above_cut", "lg2_bound_db_above_cut",
    "lg2_res_db_at_cut", "lg2_res_db_max",
    "pm_delta_deg", "gm_delta_db",
    "lf_agree_max_rel", "v2ctl_max_rel_diff", "valid",
]


class Loopgain2Error(Exception):
    pass


# --------------------------------------------------------------------------- #
# core algebra
# --------------------------------------------------------------------------- #

def _finite(**zs):
    for name, z in zs.items():
        if not cmath.isfinite(z):
            raise Loopgain2Error(f"{name} is nonfinite ({z!r})")


def injection_ratios(fb, fbamp, im):
    """Middlebrook's Tv, Ti from one frequency's raw probes (complex).

    Tv = -v(fb)/v(fbamp); Ti = -i_m/(1 + i_m), i_m = i(vmeas) (bridge
    current, FB -> FBAMP). Raises on nonfinite or exactly-degenerate input.
    """
    _finite(fb=fb, fbamp=fbamp, im=im)
    if fb == 0 or fbamp == 0:
        raise Loopgain2Error("zero probe voltage (v(fb) or v(fbamp) is exactly 0)")
    if im == 0:
        raise Loopgain2Error("i(vmeas) is exactly 0: no injected current reached the "
                             "ammeter (probe wiring, not physics)")
    if im == -1:
        raise Loopgain2Error("i(vmeas) is exactly -1: no injected current reached the "
                             "amplifier side (1 + i_m = 0); the current-injection "
                             "experiment carries no information")
    return -fb / fbamp, -im / (1.0 + im)


def middlebrook(tv, ti):
    """T = (Tv*Ti - 1)/(Tv + Ti + 2): Middlebrook's general (bilateral)
    combination. Raises on nonfinite input or an exactly zero denominator."""
    _finite(Tv=tv, Ti=ti)
    den = tv + ti + 2.0
    if den == 0:
        raise Loopgain2Error("Tv + Ti + 2 is exactly 0: the combination is undetermined")
    return (tv * ti - 1.0) / den


def resolution(fb, fbamp, im, eps=EXPORT_REL_EPS):
    """First-order bound on |dT| from rounding every exported component to
    `eps` of itself (see module docstring). Returns a float >= 0."""
    a, b, m = fb, fbamp, im
    n = 1.0 + m
    N = a * m - b * n
    D = 2.0 * b * n - a * n - b * m
    if D == 0:
        return float("inf")
    T = N / D
    dN = {"a": m, "b": -n, "m": a - b}
    dD = {"a": -n, "b": 2.0 * n - m, "m": b - a}
    mag = {"a": abs(a), "b": abs(b), "m": abs(m)}
    return eps * sum(abs((dN[k] - T * dD[k]) / D) * mag[k] for k in "abm")


def unloaded_transfer(tv, ti):
    """The quantity the PREVIOUS revision published as L (-T', the
    open-circuit divider transfer): (1 + Hi/Hv)/(1 + Hi) with Hv = -1/Tv,
    Hi = Ti, negated. Kept ONLY so the tests can show it is not the loop
    gain (1 + it does not vanish at the closed-loop poles)."""
    hv = -1.0 / tv
    return -(1.0 + ti / hv) / (1.0 + ti)


# --------------------------------------------------------------------------- #
# file readers / writers
# --------------------------------------------------------------------------- #

def _freq_columns(path, rows, ncols):
    """wrdata writes (freq, value) pairs: the freq column repeats. Require
    every repeat to agree exactly, and the axis to be strictly increasing."""
    for r in rows:
        f0 = r[0]
        for k in range(0, ncols, 2):
            if r[k] != f0:
                raise Loopgain2Error(
                    f"{path}: frequency column {k} ({r[k]!r}) != column 0 ({f0!r})")
    freqs = [r[0] for r in rows]
    if any(b <= a for a, b in zip(freqs, freqs[1:])):
        raise Loopgain2Error(f"{path}: frequency not strictly increasing")
    return freqs


def read_voltage_export(path):
    """tb_loopgain2v wrdata (8 columns) -> (freqs, fb, fbamp) complex."""
    rows = read_wrdata(path, 8)
    if not rows:
        raise Loopgain2Error(f"{path}: no rows")
    freqs = _freq_columns(path, rows, 8)
    fb = [complex(r[1], r[3]) for r in rows]
    fbamp = [complex(r[5], r[7]) for r in rows]
    return freqs, fb, fbamp


def read_current_export(path):
    """tb_loopgain2i wrdata (4 columns) -> (freqs, im) complex.

    The export's vectors are named il_re/il_im in the template (kept: the
    fleet decks were rendered with them), but the value is i(vmeas) = i_m,
    the BRIDGE current FB -> FBAMP, not the amplifier-side load current
    (which is 1 + i_m)."""
    rows = read_wrdata(path, 4)
    if not rows:
        raise Loopgain2Error(f"{path}: no rows")
    freqs = _freq_columns(path, rows, 4)
    im = [complex(r[1], r[3]) for r in rows]
    return freqs, im


def read_loopgain_trace(path):
    """Classic 4-column loop-gain wrdata (f, dB, f, deg) -> (freqs, L)."""
    rows = read_wrdata(path, 4)
    if not rows:
        raise Loopgain2Error(f"{path}: no rows")
    freqs = _freq_columns(path, rows, 4)
    L = [10.0 ** (r[1] / 20.0) * cmath.exp(1j * math.radians(r[3])) for r in rows]
    return freqs, L


def write_loopgain_trace(path, freqs, L):
    """Write a trace in the CLASSIC 4-column loop-gain wrdata layout
    (f, dB, f, deg) so the unchanged ac_metrics readers consume it."""
    with open(path, "w") as f:
        for fr, z in zip(freqs, L):
            f.write(f"{fr: .8e} {20.0 * math.log10(abs(z)): .8e} "
                    f"{fr: .8e} {math.atan2(z.imag, z.real) * 180.0 / math.pi: .8e} \n")


def check_export(path, ncols, ceiling):
    """ac_sweep.check_trace, generalised to the export column counts."""
    want = ac_sweep.expected_rows(ceiling)
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [ln.split() for ln in fh if ln.strip()]
    except OSError as exc:
        return [f"{path}: unreadable ({exc})"]
    bad = []
    if len(rows) != want:
        bad.append(f"{path}: {len(rows)} rows, expected {want} for ceiling {ceiling}")
    if rows and any(len(r) != ncols for r in rows):
        bad.append(f"{path}: not {ncols} columns on every row")
    if not bad:
        f = [float(r[0]) for r in rows]
        if not math.isclose(f[0], ac_sweep.FLOOR_HZ, rel_tol=1e-6):
            bad.append(f"{path}: first frequency {f[0]:g} != floor {ac_sweep.FLOOR_HZ:g}")
        if not math.isclose(f[-1], ac_sweep.parse_hz(ceiling), rel_tol=1e-6):
            bad.append(f"{path}: last frequency {f[-1]:g} != ceiling {ac_sweep.parse_hz(ceiling):g}")
        if any(b <= a for a, b in zip(f, f[1:])):
            bad.append(f"{path}: frequency not strictly increasing")
    return bad


# --------------------------------------------------------------------------- #
# reconstruction + validation
# --------------------------------------------------------------------------- #

def db(z):
    return 20.0 * math.log10(abs(z))


def reconstruct(v_csv, i_csv):
    """Reconstruct the Middlebrook loop gain of ONE point from its two raw
    probe exports. Returns a dict:

      freqs, T, tv, ti, res      full axis (T may be exactly 0 where the
                                 cut network is reciprocal to 9 digits)
      cut                        index of the first unresolved sample
                                 (len(freqs) if every sample is resolved)
      diag                       summary numbers (see CSV_FIELDS)

    Raises Loopgain2Error on any validation failure."""
    vfreqs, fb, fbamp = read_voltage_export(v_csv)
    ifreqs, im = read_current_export(i_csv)
    if len(vfreqs) != len(ifreqs):
        raise Loopgain2Error(
            f"frequency grids differ in length: {v_csv} has {len(vfreqs)}, "
            f"{i_csv} has {len(ifreqs)}")
    for a, b in zip(vfreqs, ifreqs):
        if not math.isclose(a, b, rel_tol=FREQ_RTOL):
            raise Loopgain2Error(f"frequency grids differ: {a!r} vs {b!r}")

    tv, ti, T, res = [], [], [], []
    for a, b, m in zip(fb, fbamp, im):
        x, y = injection_ratios(a, b, m)
        tv.append(x)
        ti.append(y)
        T.append(middlebrook(x, y))
        res.append(resolution(a, b, m))
    resolved = [abs(t) >= RESOLVED_FACTOR * r for t, r in zip(T, res)]
    cut = next((k for k, ok in enumerate(resolved) if not ok), len(T))

    # Orientation (probe-polarity detector, not a spec verdict): a healthy
    # negative-feedback loop has T(1 Hz) large and positive-real.
    if cut == 0:
        raise Loopgain2Error("the 1 Hz sample is below the export resolution: "
                             "nothing can be reconstructed")
    t0_deg = math.degrees(cmath.phase(T[0]))
    if abs(am.wrap180(t0_deg)) > ORIENT_MAX_DEG:
        raise Loopgain2Error(
            f"orientation check failed: phase(T at 1 Hz) = {t0_deg:.1f} deg, "
            f"expected within +-{ORIENT_MAX_DEG:g} deg of 0 for a "
            "negative-feedback loop (reversed shunt source or ammeter?)")
    if cut < MIN_TRACE_ROWS:
        raise Loopgain2Error(f"only {cut} resolved samples before the first unresolved one; "
                             f"the classifier needs >= {MIN_TRACE_ROWS}")

    above = range(cut, len(T))
    diag = {
        "resolved_to_hz": vfreqs[cut - 1],
        "first_unresolved_hz": vfreqs[cut] if cut < len(T) else None,
        "n_unresolved": sum(1 for ok in resolved if not ok),
        "n_resolved_above_cut": sum(1 for k in above if resolved[k]),
        "bound_db_above_cut": (max(db(abs(T[k]) + res[k]) for k in above)
                               if cut < len(T) else None),
        "res_db_at_cut": db(res[cut]) if cut < len(T) else None,
        "res_db_max": max(db(r) for r in res if r > 0),
        "phase_t0_deg": t0_deg,
        "n_points": len(vfreqs),
    }
    return {"freqs": vfreqs, "T": T, "tv": tv, "ti": ti, "res": res,
            "cut": cut, "diag": diag}


def _index_of(freqs, target):
    return min(range(len(freqs)), key=lambda k: abs(math.log10(freqs[k]) - math.log10(target)))


def zero_db_crossings(freqs, L):
    """All 0 dB crossings, log-interpolated (ac_metrics' convention)."""
    dbs = [db(z) for z in L]
    out = []
    for i in range(1, len(dbs)):
        if dbs[i - 1] * dbs[i] < 0:
            frac = (0.0 - dbs[i - 1]) / (dbs[i] - dbs[i - 1])
            logf = math.log10(freqs[i - 1]) + frac * (math.log10(freqs[i]) - math.log10(freqs[i - 1]))
            out.append(10.0 ** logf)
    return out


def interp_db_at(freqs, L, f_target):
    """|L| in dB at f_target, log-interpolated between neighbours; None if
    f_target lies outside the trace."""
    if not freqs or f_target < freqs[0] * (1 - 1e-12) or f_target > freqs[-1] * (1 + 1e-12):
        return None
    k = _index_of(freqs, f_target)
    if math.isclose(freqs[k], f_target, rel_tol=1e-12):
        return db(L[k])
    i, j = (k, k + 1) if freqs[k] < f_target else (k - 1, k)
    frac = (math.log10(f_target) - math.log10(freqs[i])) / (math.log10(freqs[j]) - math.log10(freqs[i]))
    return db(L[i]) + frac * (db(L[j]) - db(L[i]))


def validate_against_control(rec, ctl_csv):
    """Cross-checks of one reconstructed point against the SAME point's
    single-injection control trace (an independent fleet deck). Returns a
    diagnostics dict; raises Loopgain2Error on a stated-tolerance failure."""
    freqs, T, tv, res = rec["freqs"], rec["T"], rec["tv"], rec["res"]
    cfreqs, ctl = read_loopgain_trace(ctl_csv)
    if len(cfreqs) != len(freqs):
        raise Loopgain2Error(
            f"control trace has {len(cfreqs)} rows, exports have {len(freqs)}")
    for a, b in zip(cfreqs, freqs):
        if not math.isclose(a, b, rel_tol=FREQ_RTOL):
            raise Loopgain2Error(f"control frequency axis differs: {a!r} vs {b!r}")
    crossings = zero_db_crossings(cfreqs, ctl)
    if not crossings:
        raise Loopgain2Error("control trace has no 0 dB crossing (unexpected for this loop)")
    ugf = crossings[0]

    # (1) deck identity: the 2v circuit IS the control circuit, so Tv must
    # equal the control's L below the first crossing.
    ident = max(abs(tv[k] - ctl[k]) / abs(ctl[k])
                for k, fr in enumerate(freqs) if fr <= ugf)
    if ident > TOL_DECK_IDENTITY:
        raise Loopgain2Error(
            f"deck identity failed: max rel diff(Tv, control) = {ident:.3g} "
            f"> {TOL_DECK_IDENTITY:g} below the first crossing -- the two decks "
            "disagree, which is a plumbing bug (same circuit, same op), not physics")

    # (2) low-frequency agreement: T (both decks) vs the control (third deck)
    worst = 0.0
    for k, fr in enumerate(freqs):
        if fr > ugf / 10.0:
            break
        rel = (abs(T[k] - ctl[k]) - res[k]) / abs(ctl[k])
        worst = max(worst, rel)
    if worst > TOL_LF_AGREE:
        raise Loopgain2Error(
            f"low-frequency agreement failed below f_ugf/10: |T - L_ctl| exceeds "
            f"res + {TOL_LF_AGREE:g}|L_ctl| ({worst:.3g} relative) -- the current-"
            "injection deck does not see a high-impedance gate at low frequency")
    return {"v2ctl_max_rel_diff": ident, "lf_agree_max_rel": max(worst, 0.0),
            "ctl_ugf_hz": ugf}


# --------------------------------------------------------------------------- #
# per-point driver
# --------------------------------------------------------------------------- #

def parse_suffix(sfx):
    """`tt_27c_rtyp` -> (corner, temp_c, res_section)."""
    corner, tempc, rlabel = sfx.split("_")
    return corner, tempc[:-1], f"res_{rlabel[1:]}"


def point_row(corners_dir, sfx, ceiling, out_dir=None):
    """Reconstruct + validate one point; return its comparison-CSV row dict.

    The resolved-prefix trace is written beside the exports under
    `corners_dir`, or under `out_dir` when given (check mode).

    A point that fails a stated tolerance (e.g. TOL_LF_AGREE at a
    non-legacy operating point, issue #218) still reports its MEASURED
    margins and trace -- with `valid` False, the verbatim error in
    `lg2_validation_error` and, for the low-frequency agreement, a
    quantitative cause analysis -- so a record can state what was measured
    and why it is uncertified instead of silently dropping the point."""
    ctl_csv = os.path.join(corners_dir, f"{CTL_PREFIX}{sfx}{SUFFIX}")
    v_csv = os.path.join(corners_dir, f"{V_PREFIX}{sfx}{SUFFIX}")
    i_csv = os.path.join(corners_dir, f"{I_PREFIX}{sfx}{SUFFIX}")
    rec = reconstruct(v_csv, i_csv)
    corner, temp_c, res_section = parse_suffix(sfx)
    cut = rec["cut"]
    freqs, T = rec["freqs"][:cut], rec["T"][:cut]

    combined_path = os.path.join(out_dir or corners_dir, f"{TWO_PREFIX}{sfx}{SUFFIX}")
    write_loopgain_trace(combined_path, freqs, T)
    lg2 = am.loopgain_metrics(combined_path)
    cfreqs, ctl_L = read_loopgain_trace(ctl_csv)
    ctl = am.loopgain_metrics(ctl_csv)

    try:
        xdiag = validate_against_control(rec, ctl_csv)
    except Loopgain2Error as exc:
        row = _fill_row({"corner": corner, "temp_c": temp_c, "res_section": res_section,
                         "lg2_validation_error": str(exc)},
                        rec, ctl, lg2, ctl_csv, combined_path, cfreqs, ctl_L,
                        freqs, T, cut)
        row["lf_agreement_analysis"] = _lf_agreement_analysis(rec, ctl_csv, exc)
        row["valid"] = False
        return row
    row = _fill_row({"corner": corner, "temp_c": temp_c, "res_section": res_section},
                    rec, ctl, lg2, ctl_csv, combined_path, cfreqs, ctl_L,
                    freqs, T, cut)
    row["lf_agree_max_rel"] = xdiag["lf_agree_max_rel"]
    row["v2ctl_max_rel_diff"] = xdiag["v2ctl_max_rel_diff"]
    row["valid"] = True
    return row


def _fill_row(row, rec, ctl, lg2, ctl_csv, combined_path, cfreqs, ctl_L,
              freqs, T, cut):
    def _second(cs):
        return cs[1] if len(cs) >= 2 else None

    for pre, m, path, ff, LL in (("ctl", ctl, ctl_csv, cfreqs, ctl_L),
                                 ("lg2", lg2, combined_path, freqs, T)):
        for key in ("dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
                    "phase_margin_deg", "phase_margin_worst_deg",
                    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db"):
            row[f"{pre}_{key}"] = None if m is None else m.get(key)
        # count the DR-0014 classifier's critical-line crossings (every
        # 180 mod 360 crossing) so the record and the classification share
        # one definition; the margins themselves are loopgain_metrics'.
        cm = am.classify_margins(path)
        if cm and cm.get("valid"):
            row[f"{pre}_n_gain_margin_crossings"] = len(cm["critical_crossings"])
        row[f"{pre}_second_crossing_hz"] = _second(zero_db_crossings(ff, LL))
        row[f"{pre}_db_at_100mhz"] = interp_db_at(ff, LL, 1e8)
    row["lg2_db_at_resolved_to"] = db(T[-1])
    # The control's axis supports a like-for-like comparison only when it
    # reaches the reconstruction's cut; a short/foreign control trace is the
    # very thing validate_against_control reports, so leave the comparative
    # metric empty rather than index past the array and mask that error.
    row["ctl_db_at_lg2_resolved_to"] = (
        db(ctl_L[cut - 1]) if 0 < cut <= len(ctl_L)
        and math.isclose(cfreqs[cut - 1], freqs[cut - 1], rel_tol=FREQ_RTOL) else None)
    row["ctl_db_at_1ghz"] = interp_db_at(cfreqs, ctl_L, 1e9)
    row["ctl_db_at_ceiling"] = db(ctl_L[-1])
    row["pm_delta_deg"] = ((row["lg2_phase_margin_deg"] - row["ctl_phase_margin_deg"])
                           if None not in (row["lg2_phase_margin_deg"], row["ctl_phase_margin_deg"]) else None)
    row["gm_delta_db"] = ((row["lg2_gain_margin_db"] - row["ctl_gain_margin_db"])
                          if None not in (row["lg2_gain_margin_db"], row["ctl_gain_margin_db"]) else None)
    d = rec["diag"]
    for k in ("resolved_to_hz", "first_unresolved_hz", "n_unresolved",
              "n_resolved_above_cut", "bound_db_above_cut", "res_db_at_cut", "res_db_max"):
        row[f"lg2_{k}"] = d[k]
    return row


def _lf_agreement_analysis(rec, ctl_csv, exc):
    """Quantitative cause analysis for a failed TOL_LF_AGREE check (issue
    #218). At a non-legacy operating point the physical difference between
    the two-injection T and the single-injection control below f_ugf/10 can
    reach the legacy-calibrated tolerance: it is the analytic loading term
    |T - Tv| = |(1+Tv)^2/(Tv + Ti + 2)|, not a plumbing fault. This block
    documents the deviation's composition; it never adjusts the tolerance,
    the check or any verdict."""
    if "low-frequency agreement" not in str(exc):
        return None
    cfreqs, ctl = read_loopgain_trace(ctl_csv)
    crossings = zero_db_crossings(cfreqs, ctl)
    if not crossings:
        return None
    band = crossings[0] / 10.0
    Tv, Ti = rec["tv"], rec["ti"]
    freqs, T, res = rec["freqs"], rec["T"], rec["res"]
    worst_rel, worst_k, ident = 0.0, 0, 0.0
    for k, fr in enumerate(freqs):
        if fr > band:
            break
        rel = (abs(T[k] - ctl[k]) - res[k]) / abs(ctl[k])
        if rel > worst_rel:
            worst_rel, worst_k = rel, k
        ident = max(ident, abs(Tv[k] - ctl[k]) / abs(ctl[k]))
    analytic = abs((1.0 + Tv[worst_k]) ** 2 / (Tv[worst_k] + Ti[worst_k] + 2.0))
    measured = abs(T[worst_k] - ctl[worst_k])
    return {
        "band_edge_hz": band,
        "worst_freq_hz": freqs[worst_k],
        "worst_rel": worst_rel,
        "tolerance": TOL_LF_AGREE,
        "deck_identity_residual_below_band": ident,
        "deck_identity_tolerance": TOL_DECK_IDENTITY,
        "analytic_loading_term_at_worst": analytic,
        "measured_deviation_at_worst": measured,
        "ti_over_tv_at_worst": abs(Ti[worst_k] / Tv[worst_k]),
        "tv_db_at_worst": db(Tv[worst_k]),
        "conclusion": (
            "the deviation below f_ugf/10 is the analytic single-injection "
            "loading term |T - Tv| = |(1+Tv)^2/(Tv + Ti + 2)| (the control "
            "agrees with Tv to deck-identity precision), not a plumbing "
            "fault; the tolerance is NOT widened, skipped or re-derived"),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.12g}"
    return str(x)


def all_suffixes(corners_dir):
    out = []
    for fn in sorted(os.listdir(corners_dir)):
        if fn.startswith(CTL_PREFIX) and fn.endswith(SUFFIX):
            out.append(fn[len(CTL_PREFIX):-len(SUFFIX)])
    return out


# --------------------------------------------------------------------------- #
# operating point (issue #218)
# --------------------------------------------------------------------------- #
# run_loopgain2.sh's campaign used to hardcode the legacy point (1 mA / 1 uF /
# 0 ohm). The --load-ma/--cout-uf/--esr-ohm arguments canonicalise through
# dynamic_doe -- the same validator the #64 DoE uses -- so there is no second
# validator to drift. The DEFAULT deck literals stay exactly the bytes the
# driver always substituted, and the driver sources them from here, so the
# no-arguments run renders byte-identical decks by construction.

DEFAULT_DECK_LITERALS = {
    "LOAD_A": "0.001",
    "COUT_F": "1u",
    "COUT_BOTTOM": "0",
    "ESR_LINE": "* ESR=0: Cout wired directly to ground (campaign default)",
}


def op_from_args(load_ma=None, cout_uf=None, esr_ohm=None):
    """CLI operating point (issue #218) -> dynamic_doe's integer op dict.

    Values arrive in mA / uF / ohm; dynamic_doe validates in base units
    (uA / nF / mohm), so each is scaled by 1000 and must land on an exact
    integer. Anything else -- zero Cout, a negative value, a non-numeric
    string, a value finer than the base unit -- raises dynamic_doe's
    InvalidOperatingPoint (the driver surfaces it as exit 2)."""
    op = {}
    for name, raw in (("load_ua", load_ma), ("cout_nf", cout_uf),
                      ("esr_mohm", esr_ohm)):
        if raw is None:
            op[name] = dyn.LEGACY_POINT[name]
            continue
        try:
            v = Decimal(str(raw)) * 1000
        except (InvalidOperation, ValueError):
            raise dyn.InvalidOperatingPoint(f"{name}: not a number: {raw!r}")
        if v != v.to_integral_value():
            raise dyn.InvalidOperatingPoint(
                f"{name}: {raw!r} is not an exact multiple of the base unit "
                f"({name.split('_')[0]}s are held as integers)")
        op[name] = int(v)
    dyn.validate_op(op)
    return op


def op_display(op):
    """Human-facing operating point, in the units the records spell out."""
    dyn.validate_op(op)
    return (f"{op['load_ua'] / 1000:g} mA, {op['cout_nf'] / 1000:g} uF, "
            f"{op['esr_mohm'] / 1000:g} ohm")


def metric_delta(m1, m2, key):
    """m1[key] - m2[key]; None when either metric is absent (a trace with no
    such crossing). Informational comparisons must degrade, never raise."""
    a, b = (m or {} for m in (m1, m2))
    if a.get(key) is None or b.get(key) is None:
        return None
    return a[key] - b[key]


def metric_rel_delta(m1, m2, key):
    """(m1[key] - m2[key]) / m2[key]; None when absent or m2[key] is 0."""
    d = metric_delta(m1, m2, key)
    return None if d is None or not m2[key] else d / m2[key]


def esr_netlist_parts(esr_ohm):
    """run_sweep.sh's esr_netlist_parts convention (issue #64): ESR of
    exactly 0 wires Cout to ground and emits a comment instead of a
    zero-valued resistor. Returns (cout_bottom, esr_line). The resistor is
    `Resr <COUT_ESR> <0> <value>`: its own name first, then its two nodes
    (the leading "COUT_ESR" in run_sweep.sh's echoed pair is cout_bottom,
    not part of the element line)."""
    if esr_ohm == "0":
        return "0", "* ESR=0: Cout wired directly to ground, no series resistor"
    return "COUT_ESR", f"Resr COUT_ESR 0 {esr_ohm}"


def cmd_op(a):
    """Print the canonical operating point as JSON for run_loopgain2.sh."""
    try:
        op = op_from_args(a.load_ma, a.cout_uf, a.esr_ohm)
        net = dyn.netlist_values(op)
        cout_bottom, esr_line = esr_netlist_parts(net["esr_ohm"])
        doc = {"op": op, "legacy": op == dict(dyn.LEGACY_POINT),
               "token": dyn.op_token(op), "display": op_display(op),
               "netlist": net, "esr": {"cout_bottom": cout_bottom,
                                       "esr_line": esr_line},
               "default_literals": dict(DEFAULT_DECK_LITERALS)}
    except dyn.InvalidOperatingPoint as exc:
        print(f"loopgain2: invalid operating point: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(doc, indent=1))
    return 0


def cmd_report(a, out_dir=None):
    corners_dir = os.path.abspath(a.corners_dir)
    rows = []
    for sfx in all_suffixes(corners_dir):
        try:
            rows.append(point_row(corners_dir, sfx, a.ceiling, out_dir))
            print(f"loopgain2: {sfx}: ok (resolved to {rows[-1]['lg2_resolved_to_hz']:.3g} Hz)",
                  file=sys.stderr)
        except Loopgain2Error as exc:
            print(f"loopgain2: {sfx}: FAILED: {exc}", file=sys.stderr)
            corner, temp_c, res_section = parse_suffix(sfx)
            rows.append({"corner": corner, "temp_c": temp_c,
                         "res_section": res_section, "valid": False})
    with open(a.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: _fmt(row.get(k)) for k in CSV_FIELDS})
    nbad = sum(1 for r in rows if not r.get("valid"))
    good = [r for r in rows if r.get("valid")]
    doc = {"schema_version": 2, "ceiling": ac_sweep.canonical(a.ceiling),
           "method": ("Middlebrook (1975) general two-injection loop gain "
                      "T = (Tv*Ti - 1)/(Tv + Ti + 2); trace = resolved prefix only"),
           "points": len(rows), "invalid": nbad,
           "tolerances": {"deck_identity_rel": TOL_DECK_IDENTITY,
                          "lf_agree_rel": TOL_LF_AGREE,
                          "orientation_max_deg": ORIENT_MAX_DEG,
                          "export_rel_eps": EXPORT_REL_EPS,
                          "resolved_factor": RESOLVED_FACTOR},
           "resolved_to_hz_min": min((r["lg2_resolved_to_hz"] for r in good), default=None),
           "n_resolved_above_cut_total": sum(r["lg2_n_resolved_above_cut"] for r in good),
           "bound_db_above_cut_max": max((r["lg2_bound_db_above_cut"] for r in good
                                          if r["lg2_bound_db_above_cut"] is not None),
                                         default=None),
           "rows": rows}
    with open(a.out_json, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    if nbad:
        print(f"loopgain2: {nbad} of {len(rows)} points FAILED validation", file=sys.stderr)
        return 1
    print(f"loopgain2: all {len(rows)} points reconstructed and validated", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# record md (offline; every number comes from committed files)
# --------------------------------------------------------------------------- #

# A campaign's shape (issue #218): the driver writes evidence/<rid>/
# campaign.json next to the raw exports; every string the record md and the
# row10 wrapper used to hardcode as "the 45-point legacy campaign" is read
# from it. A record WITHOUT one is a pre-#218 campaign, and the defaults
# below are byte-identically the strings that era's committed records carry,
# so `loopgain2.py check` keeps reproducing them.
#
# The producer pins: the records' "Reconstruction inputs" line quotes the
# loopgain2.py and the two templates that PRODUCED the record, not this
# module's current bytes -- otherwise every later edit here (like #218's)
# would break the landed, append-only records' byte-compare. Pre-#218
# records all quote the pins below (read out of their committed mds, pinned
# there by test_loopgain2.py); a #218+ campaign's driver writes its own pins
# into its campaign.json at run time.
LEGACY_PRODUCER_SHA16 = {
    "loopgain2.py": "22e8900632c48b90",
    "tb_loopgain2v_cmos5l.spice.tmpl": "d7be4a61a83a628b",
    "tb_loopgain2i_cmos5l.spice.tmpl": "deb8306c6bb1bebe",
}

CAMPAIGN_DEFAULTS = {
    "issue": "issue #135",
    "revision_note": True,
    "grid": "5 MOS corners x 3 temperatures x 3 resistor corners",
    "op_display": "1 mA, 1 uF, 0 ohm",
    "op": dict(dyn.LEGACY_POINT),
    "points": 45,
    "decks": 3,
    "legacy_point": True,
    "full_grid": True,
    "only_point": None,
    "e2": None,
    "producer_sha16": LEGACY_PRODUCER_SHA16["loopgain2.py"],
    "tmpl2v_sha16": LEGACY_PRODUCER_SHA16["tb_loopgain2v_cmos5l.spice.tmpl"],
    "tmpl2i_sha16": LEGACY_PRODUCER_SHA16["tb_loopgain2i_cmos5l.spice.tmpl"],
    # full sha256s the row10 wrapper's evidence json pins (same producer-pin
    # reasoning as the sha16 trio above)
    "row10_wrapper_sha256": "908582b07b669654b6c6ebc9500268597a92edf01d1dedbd0dc3b258994db8a3",
    "loopgain2_sha256": "22e8900632c48b90bbca09373f6656f2a91f7304c9328cb81c097e71c05e68df",
}


def uncertified_diagnostic_points(rid, sim_dir=HERE):
    """Point ids a record's campaign.json declares as uncertified diagnostics:
    only the DR-0015 E2 experiment's P3 point (issue #218). Empty for every
    other record, so an invalid point there stays a hard check failure."""
    facts, _ = campaign_facts(rid, sim_dir)
    e2 = facts.get("e2")
    return {e2["p3_point"]} if e2 and e2.get("p3_point") else set()


def campaign_facts(rid, sim_dir=HERE):
    """(facts, campaign.json present) for record `rid`. Unknown keys in the
    json are ignored; every missing key falls back to the legacy-campaign
    default, so an older campaign.json cannot crash the md generator."""
    facts = dict(CAMPAIGN_DEFAULTS)
    path = os.path.join(sim_dir, "evidence", rid, "campaign.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return facts, False
    except ValueError as exc:
        raise Loopgain2Error(f"{path}: not valid JSON ({exc})")
    if not isinstance(doc, dict):
        raise Loopgain2Error(f"{path}: not a JSON object")
    facts.update({k: doc[k] for k in CAMPAIGN_DEFAULTS if k in doc})
    return facts, True


def _read_env(path):
    env = {}
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if "=" in ln:
                k, v = ln.strip().split("=", 1)
                env[k] = v.strip("'\"")
    return env


def record_md(rid, sim_dir=HERE):
    """The narrative record md for two-injection record `rid`, derived only
    from committed files (comparison CSV, report JSON, batch provenance,
    ctl-vs-baseline JSON)."""
    corners_dir = os.path.join(sim_dir, "corners", rid)
    cmp_csv = os.path.join(sim_dir, "records", f"{rid}.loopgain2.csv")
    cmp_json = os.path.join(sim_dir, "evidence", rid, "loopgain2-report.json")
    base_json = os.path.join(sim_dir, "evidence", rid, "ctl-vs-baseline.json")
    with open(cmp_csv, newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(cmp_json) as fh:
        rep = json.load(fh)
    with open(base_json) as fh:
        base = json.load(fh)
    with open(os.path.join(corners_dir, "_batch", "backend.json")) as fh:
        batch = json.load(fh)
    env = _read_env(os.path.join(corners_dir, "_batch", "backend.env"))
    valid = [r for r in rows if r["valid"] == "True"]
    git_sha = rid.rsplit("-", 1)[-1]
    facts, _has_campaign = campaign_facts(rid, sim_dir)
    n_points = facts["points"]

    def vals(key):
        return [float(r[key]) for r in valid if r.get(key) not in ("", None)]

    def rng(key, fmt="{:.4g}"):
        vs = vals(key)
        return (fmt.format(min(vs)) + " .. " + fmt.format(max(vs))) if vs else "--"

    def worst(key, fn=min):
        vs = [(float(r[key]), r) for r in valid if r.get(key) not in ("", None)]
        if not vs:
            return "--"
        v, r = fn(vs, key=lambda t: t[0])
        return f"{r['corner']}/{r['temp_c']}C/{r['res_section']}"

    def above_cut(f):
        cuts = vals("lg2_resolved_to_hz")
        return "-- (above every point's cut)" if cuts and max(cuts) < f else "see the comparison CSV"

    jobs = sorted((j["group"], j.get("job_id")) for j in batch["jobs"])
    tb = os.path.join(sim_dir, "testbench")
    if facts["e2"]:
        intro = ["SCHEMATIC-LEVEL diagnostic evidence, NOT a spec pass. DR-0015's experiment E2 (issue #218):",
                 "the SG13CMOS5L loop gain at the FB/FBAMP break measured BOTH ways at point P3 -- the",
                 "single-injection control and the Middlebrook two-injection reconstruction (voltage +",
                 "current, two AC analyses per point) -- to test whether P3's above-unity critical crossing",
                 "and negative scored PM belong to the loop or to the single voltage injection. DR-0014",
                 "rules are UNCHANGED; row 10 stays Open."]
    else:
        intro = ["SCHEMATIC-LEVEL diagnostic evidence, NOT a spec pass. The SG13CMOS5L loop gain at the FB/FBAMP",
                 "break was measured a second way (Middlebrook two-injection, voltage + current, two AC analyses",
                 f"per point) to test whether the +1 dB plateau above the second 0 dB crossing of record `{BASELINE_RID}`",
                 "belongs to the loop or to the single voltage injection. DR-0014 rules are UNCHANGED; row 10 stays Open."]
    L = [f"# Two-injection loop-gain comparison record `{rid}` ({facts['issue']})", "",
         "<!-- GENERATED by sim/ldo-cmos5l-pvt-sweep/loopgain2.py record-md -- do not edit; "
         "`loopgain2.py check` byte-compares. -->", ""] + intro + [""]
    if facts["revision_note"]:
        L += ["**Revision note.** The raw fleet exports of this record are unchanged. Its DERIVED artifacts",
              "(reconstructed traces `corners/" + rid + "/loopgain2_*_ac.csv`, this md, the comparison CSV and",
              "`evidence/" + rid + "/{loopgain2-report.json,row10-margins.*}`) were regenerated before merge: the",
              "first revision published the UNLOADED transfer -T' instead of the loop gain and clamped",
              "sub-resolution samples to an invented -300 dB / 180 deg value. Both are withdrawn (README,",
              "\"Loop-gain measurement method -- two-injection\"). The record never landed on main.", ""]
    L += ["## Method", "",
          "- Voltage injection `tb_loopgain2v_cmos5l.spice.tmpl` (`Vbreak FB FBAMP 0 ac 1`, the single-injection",
          "  circuit): Tv = -v(fb)/v(fbamp), exactly the single-injection L.",
          "- Current injection `tb_loopgain2i_cmos5l.spice.tmpl` (loop intact behind `Vmeas FB FBAMP 0`, shunt",
          "  `Iinx 0 FBAMP dc 0 ac 1`): Ti = -i_m/(1 + i_m), i_m = i(vmeas) the bridge current FB -> FBAMP.",
          "- Loop gain: Middlebrook's general (bilateral) T = (Tv Ti - 1)/(Tv + Ti + 2); L = T. Derivation from the",
          "  break two-port, and its check against a nodally solved circuit (return ratio, closed-loop poles,",
          "  reversed probes), in the experiment README and `test_loopgain2.py`.",
          f"- Resolution: the exports carry 9 significant digits; the first-order rounding bound res(f) is",
          f"  computed per frequency and a sample counts only if |T| >= {RESOLVED_FACTOR:g} res. The written",
          "  trace is the resolved prefix (1 Hz up to the first unresolved sample); nothing is clamped.",
          f"- Tolerances: Tv vs control <= {TOL_DECK_IDENTITY:g} rel below the first crossing; T vs control <=",
          f"  res + {TOL_LF_AGREE:g} rel below f_ugf/10; phase(T at 1 Hz) within {ORIENT_MAX_DEG:g} deg of 0.", ""]
    L += ["## Provenance", "",
          f"- Campaign: `sim/ldo-cmos5l-pvt-sweep/run_loopgain2.sh` at commit `{git_sha}`; batch fleet only",
          f"  (`batch_backend.py`), {len(jobs)} klt sim requests: "
          + ", ".join(f"`{g}`={j}" for g, j in jobs) + ".",
          f"- ngspice `{env.get('BATCH_NGSPICE_VERSION', 'unknown')}` on the EDA batch fleet runner "
          f"(klt {env.get('BATCH_RUNNER_KLT', 'unknown')}).",
          f"- Grid: {facts['grid']} at Vin 3.30 V, {facts['op_display']}, EN tied",
          f"  to VIN = {n_points} points x {facts['decks']} decks = "
          f"{n_points * facts['decks']} klt corners; axis `ac dec 20 1 1e10`.",]
    if base.get("skipped"):
        L += [f"- Control vs the historical `{BASELINE_RID}` traces: SKIPPED -- {base['reason']} "
              f"(`evidence/{rid}/ctl-vs-baseline.json`)."]
        ref = base.get("reference")
        if ref:
            def _opt(v, fmt):
                return "n/a (no crossing in one of the traces)" if v is None else format(v, fmt)
            L += [f"- Cross-vintage context (informational, NOT a gate; nothing here passes or fails): "
                  f"this run's control vs the committed single-injection trace `{ref['trace_sha256_16']}` "
                  f"of record `{ref['record']}` at the same DR-0015 point: "
                  f"dPM {_opt(ref['dpm_deg'], '+.2f')}{'' if ref['dpm_deg'] is None else ' deg'}, "
                  f"dGM {_opt(ref['dgm_db'], '+.2f')}{'' if ref['dgm_db'] is None else ' dB'}, "
                  f"df_ug {_opt(ref['dfug_rel'], '+.2%')}, max |dB diff| "
                  f"{ref['max_db_diff_common_axis']:.3g} dB over the common axis to "
                  f"{ref['common_axis_to_hz']:.3g} Hz. {base['reference_cause']}"
                  + (" DR-0015's own P3 row (PM -52.70 deg, GM -9.20 dB) additionally crosses the "
                     "#89/#155 design+PDK vintage change."
                     if (facts.get("e2") or {}).get("p3_point") == facts.get("only_point") else "")]
    else:
        L += [f"- Control vs the historical `{BASELINE_RID}` traces: max |dB diff| "
              f"{base['max_abs_db_diff_over_points']:.3g} dB over {n_points} points "
              f"(`evidence/{rid}/ctl-vs-baseline.json`)."]
    L += [f"- Reconstruction inputs at this revision (sha256, first 16 hex): "
          f"`loopgain2.py` {facts['producer_sha16']}, "
          f"`tb_loopgain2v_cmos5l.spice.tmpl` {facts['tmpl2v_sha16']}, "
          f"`tb_loopgain2i_cmos5l.spice.tmpl` {facts['tmpl2i_sha16']}. "
          f"The fleet decks are the committed `netlist-snapshots/{rid}/` files.", ""]
    pts_word = f"{n_points} point" + ("" if n_points == 1 else "s")
    title = (f"## Results ({len(valid)} of {len(rows)} points valid)" if len(valid) == n_points and len(rows) == n_points
             else f"## Results ({len(valid)} of {len(rows)} points valid -- INVALID POINTS PRESENT)")
    L += [title, "",
          f"| quantity ({pts_word}) | single injection (control, Tv) | two-injection (Middlebrook T) |", "|---|---|---|",
          f"| PM, first crossing [deg] | {rng('ctl_phase_margin_deg')} (worst {worst('ctl_phase_margin_deg')}) "
          f"| {rng('lg2_phase_margin_deg')} (worst {worst('lg2_phase_margin_deg')}) |",
          f"| GM [dB] | {rng('ctl_gain_margin_db')} (worst {worst('ctl_gain_margin_db')}) "
          f"| {rng('lg2_gain_margin_db')} (worst {worst('lg2_gain_margin_db')}) |",
          f"| 0 dB crossings | {rng('ctl_n_0db_crossings', '{:.0f}')} | {rng('lg2_n_0db_crossings', '{:.0f}')} "
          "(resolved band) |",
          f"| second 0 dB crossing [Hz] | {rng('ctl_second_crossing_hz', '{:.3g}')} "
          f"| {rng('lg2_second_crossing_hz', '{:.3g}')} |",
          f"| loop gain at 100 MHz [dB] | {rng('ctl_db_at_100mhz')} | {rng('lg2_db_at_100mhz')} |",
          f"| loop gain at T's last resolved frequency [dB] | {rng('ctl_db_at_lg2_resolved_to')} "
          f"| {rng('lg2_db_at_resolved_to')} |",
          f"| loop gain at 1 GHz [dB] | {rng('ctl_db_at_1ghz')} | {above_cut(1e9)} |",
          f"| loop gain at 10 GHz [dB] | {rng('ctl_db_at_ceiling')} | {above_cut(1e10)} |",
          f"| last resolved frequency [Hz] | -- | {rng('lg2_resolved_to_hz', '{:.3g}')} |",
          f"| unresolved samples per point (of 201) | -- | {rng('lg2_n_unresolved', '{:.0f}')} |",
          f"| resolved samples above the cut | -- | {rng('lg2_n_resolved_above_cut', '{:.0f}')} |",
          f"| upper bound on abs(T) above the cut [dB] | -- | {rng('lg2_bound_db_above_cut')} |",
          f"| export resolution at the cut [dB] | -- | {rng('lg2_res_db_at_cut')} |",
          f"| PM delta (T - control) [deg] | -- | {rng('pm_delta_deg')} |",
          f"| GM delta (T - control) [dB] | -- | {rng('gm_delta_db')} |",
          f"| deck identity Tv vs control (max rel) | -- | {rng('v2ctl_max_rel_diff', '{:.2g}')} |",
          f"| low-frequency agreement T vs control (max rel, net of res) | -- | {rng('lf_agree_max_rel', '{:.2g}')} |",
          ""]
    gmd = vals("gm_delta_db")
    if not valid:
        L += ["## Reading", "",
              "- No point passed the stated tolerances, so no aggregate reading is offered: every",
              "  two-injection number in this record is uncertified (see the E2 section below and",
              f"  `evidence/{rid}/loopgain2-report.json`).", ""]
        if facts["e2"]:
            L += _e2_side_by_side(rid, sim_dir, facts, rows, rep=rep)
        return "\n".join(L) + "\n"
    gm_side = ("the single-injection GM is the smaller one at every point" if gmd and min(gmd) > 0 else
               "the single-injection GM is the larger one at every point" if gmd and max(gmd) < 0 else
               "neither method's GM is consistently the smaller one")
    n_two = vals("lg2_n_0db_crossings")
    n_above = vals("lg2_n_resolved_above_cut")
    truncated = [r for r in valid if r.get("lg2_first_unresolved_hz") not in ("", None)]
    L += ["## Reading", "",
          f"- Below f_ugf/10 T and the control agree to {rng('lf_agree_max_rel', '{:.2g}')} relative (net of res),",          f"  and the first 0 dB crossing is the same loop: PM differs by {rng('pm_delta_deg')} deg.",
          f"- GM differs by {rng('gm_delta_db')} dB (T minus control). Each is read at its own first -180 deg",
          f"  crossing ({rng('ctl_gain_margin_freq_hz', '{:.3g}')} Hz for the control, "
          f"{rng('lg2_gain_margin_freq_hz', '{:.3g}')} Hz for T), where the single injection's",
          "  zero-input-current premise no longer holds; " + gm_side + ".",
          f"- Middlebrook's T is resolved up to {rng('lg2_resolved_to_hz', '{:.3g}')} Hz. At that edge it reads "
          f"{rng('lg2_db_at_resolved_to')} dB",
          f"  while the control reads {rng('ctl_db_at_lg2_resolved_to')} dB at the same frequency.",
          f"- 0 dB crossings of T in its resolved band: {rng('lg2_n_0db_crossings', '{:.0f}')} per point. "
          f"Resolved samples above the cut: {rng('lg2_n_resolved_above_cut', '{:.0f}')} per point;"
          f" there abs(T) <= {rng('lg2_bound_db_above_cut')} dB",
          "  (a rounding bound, not a measured level)."]
    if n_two and max(n_two) == 1 and n_above and max(n_above) == 0:
        L += ["- So T shows no second 0 dB crossing and no plateau anywhere it can be resolved, and a plateau",
              f"  near 0 dB would sit at least {-max(vals('lg2_bound_db_above_cut')):.0f} dB above the bound. "
              "The single-injection plateau is",
              "  absent from the loop gain as Middlebrook defines it (non-reciprocal transmission around the break)."]
    else:
        L += ["- T has a second 0 dB crossing or a resolved sample above its cut at some point: the",
              "  single-injection plateau is NOT shown to be absent from the loop gain."]
    L += ["- Not claimed: which physical path makes the single injection read about +1 dB above 100 MHz (the",
          "  gate-loading hypothesis is consistent with the data but not separately tested); anything above",
          "  1 GHz (model range unvalidated); and any DR-0014 pass. "
          + (f"The reconstruction is truncated below the 10 GHz ceiling at {len(truncated)} of {len(valid)} "
             f"points, so `evidence/{rid}/row10-margins.*` reports those `ambiguous`." if truncated else
             f"See `evidence/{rid}/row10-margins.*`."), ""]
    if facts["e2"]:
        L += _e2_side_by_side(rid, sim_dir, facts, rows, rep=rep)
    return "\n".join(L) + "\n"


def _dr0014_verdict(m, key):
    """`fail (reason; reason)` -- the committed classification wording."""
    v = m[key]
    reasons = "; ".join(v["reasons"])
    return f"{v['verdict']} ({reasons})" if reasons else v["verdict"]


def _row10_verdict(row, key):
    verdict = row[f"{key}_verdict"]
    reasons = row.get(f"{key}_reasons", "")
    return f"{verdict} ({reasons})" if reasons else verdict


def _e2_side_by_side(rid, sim_dir, facts, rows, rep=None):
    """The DR-0015 E2 table (issue #218): P3 from THIS record, P6 cited from
    the committed 45-point two-injection record -- never re-run. Every cell
    is read from committed files (comparison CSV rows, row10-margins.json,
    and ac_metrics.classify_margins on the committed control traces)."""
    e2 = facts["e2"]
    p6_rid = e2["p6_record"]
    with open(os.path.join(sim_dir, "records", f"{p6_rid}.loopgain2.csv"), newline="") as fh:
        p6_rows = [r for r in csv.DictReader(fh)
                   if (r["corner"], r["temp_c"], r["res_section"]) == _corner_key(e2["p6_point"])]
    p6_row10_rows = _row10_csv_rows(sim_dir, p6_rid)
    row10_rows = _row10_csv_rows(sim_dir, rid)

    def ctl_row(record_id, r):
        sfx = f"{r['corner']}_{r['temp_c']}c_r{r['res_section'][4:]}"
        trace = os.path.join(sim_dir, "corners", record_id, f"{CTL_PREFIX}{sfx}{SUFFIX}")
        return (f"{float(r['ctl_phase_margin_deg']):.2f}", f"{float(r['ctl_gain_margin_db']):.2f}",
                _dr0014_verdict(am.classify_margins(trace), "pm"),
                _dr0014_verdict(am.classify_margins(trace), "gm"))

    def lg2_row(r, margins_row):
        return (f"{float(r['lg2_phase_margin_deg']):.2f}", f"{float(r['lg2_gain_margin_db']):.2f}",
                _row10_verdict(margins_row, "pm"), _row10_verdict(margins_row, "gm"))

    p3 = rows[0]
    p3_key = (p3["corner"], p3["temp_c"], p3["res_section"])
    p3_ctl = ctl_row(rid, p3)
    p3_lg2 = lg2_row(p3, _find_row10(row10_rows, p3_key))
    p6 = p6_rows[0]
    p6_key = (p6["corner"], p6["temp_c"], p6["res_section"])
    p6_ctl = ctl_row(p6_rid, p6)
    p6_lg2 = lg2_row(p6, _find_row10(p6_row10_rows, p6_key))
    p3_invalid = p3.get("valid") != "True"
    if p3_invalid:
        p3_lg2 = tuple(c + " (uncertified)" for c in p3_lg2)
    out = ["## DR-0015 experiment E2: single- vs two-injection at P3 and P6", "",
           "DR-0015's follow-up brief prices E2 as the two-injection bench at its points P3 and P6.",
           f"This record is the P3 half (single PVT point `{e2['p3_point']}` at {facts['op_display']},",
           f"{n_points_word(facts['points'])} x 3 decks). The P6 half is NOT re-run: P6 is the existing",
           f"45-point campaign's `{e2['p6_point']}` point at the legacy operating point, cited from record",
           f"`{p6_rid}` below. Margins are the committed records' own readings; classifications are the",
           "unchanged DR-0014 rules (`ac_metrics.classify_margins`; the two-injection half additionally",
           "carries row10_loopgain2.py's resolution overlay).", "",
           "| point | bench | PM first [deg] | GM [dB] | DR-0014 PM | DR-0014 GM |",
           "|---|---|---|---|---|---|",
           f"| P3 ({e2['p3_conditions']}) | single injection (control) | {p3_ctl[0]} | {p3_ctl[1]} | {p3_ctl[2]} | {p3_ctl[3]} |",
           f"| P3 ({e2['p3_conditions']}) | two-injection (Middlebrook T) | {p3_lg2[0]} | {p3_lg2[1]} | {p3_lg2[2]} | {p3_lg2[3]} |",
           f"| P6 ({e2['p6_conditions']}) | single injection (control) | {p6_ctl[0]} | {p6_ctl[1]} | {p6_ctl[2]} | {p6_ctl[3]} |",
           f"| P6 ({e2['p6_conditions']}) | two-injection (Middlebrook T) | {p6_lg2[0]} | {p6_lg2[1]} | {p6_lg2[2]} | {p6_lg2[3]} |",
           "", f"P6 row source: `records/{p6_rid}.loopgain2.csv` + `evidence/{p6_rid}/row10-margins.json`",
           "(control PM 53.87 deg / GM 29.87 dB, two-injection PM 53.87 deg / GM 38.26 dB -- the values",
           "DR-0015's P6 row quotes)."]
    if p3_invalid:
        err = ""
        analysis = None
        for r in ((rep or {}).get("rows") or []):
            if r.get("lg2_validation_error"):
                err = r["lg2_validation_error"]
            if r.get("lf_agreement_analysis"):
                analysis = r["lf_agreement_analysis"]
        out += ["", f"**Caveat: the P3 two-injection point is INVALID under the bench's unchanged",
                f"tolerances** -- `{err}`. The margins above are reported UNCERTIFIED: the record",
                "states what was measured and why it is not certified evidence."]
        if analysis:
            out += [f"Quantitative cause (`evidence/{rid}/loopgain2-report.json`,",
                    f"`lf_agreement_analysis`): below f_ugf/10 (band edge {analysis['band_edge_hz']:.4g} Hz) the",
                    f"control agrees with Tv to {analysis['deck_identity_residual_below_band']:.2g} relative (deck identity,",
                    f"tol {analysis['deck_identity_tolerance']:g}), and the deviation is the ANALYTIC single-injection",
                    f"loading term |T - Tv| = |(1+Tv)^2/(Tv + Ti + 2)|: analytic",
                    f"{analysis['analytic_loading_term_at_worst']:.6g} vs measured {analysis['measured_deviation_at_worst']:.6g}",
                    f"at {analysis['worst_freq_hz']:.4g} Hz ({analysis['worst_rel']:.3g} relative vs the legacy-calibrated",
                    f"{analysis['tolerance']:g}; there |Tv| = {analysis['tv_db_at_worst']:.4g} dB and |Ti|/|Tv| =",
                    f"{analysis['ti_over_tv_at_worst']:.3g}). {analysis['conclusion']}: the point is recorded",
                    "invalid, and re-deriving that tolerance for non-legacy operating points is left to a",
                    "separately reviewed change."]
    out += [""]
    return out


def _corner_key(point):
    """`ss_125c_rbcs` -> ('ss', '125', 'res_bcs') for comparison-CSV lookup."""
    corner, tempc, res_section = parse_suffix(point)
    return corner, tempc, res_section


def _row10_csv_rows(sim_dir, record_id):
    with open(os.path.join(sim_dir, "evidence", record_id, "row10-margins.csv"), newline="") as fh:
        return list(csv.DictReader(fh))


def _find_row10(row10_rows, key):
    for r in row10_rows:
        if (r["corner"], r["temp_c"], r["res_section"]) == key:
            return r
    raise Loopgain2Error(f"row10-margins row {key} not found")


def n_points_word(n):
    return f"{n} point" + ("" if n == 1 else "s")


def cmd_record_md(a):
    out = os.path.join(HERE, "records", f"{a.record}.loopgain2.md")
    with open(out, "w") as fh:
        fh.write(record_md(a.record))
    print(f"loopgain2: wrote {out}", file=sys.stderr)
    return 0


def cmd_check(a):
    """CI mode: rebuild every reconstructed trace, the comparison CSV/JSON
    and the record md from the committed exports and byte-compare. Writes
    only into a throwaway temp dir."""
    import tempfile
    if a.corners_dir:
        dirs = [os.path.abspath(a.corners_dir)]
    else:
        corners_root = os.path.join(HERE, "corners")
        dirs = [os.path.join(corners_root, n) for n in sorted(os.listdir(corners_root))
                if os.path.isdir(os.path.join(corners_root, n))
                and glob.glob(os.path.join(corners_root, n, f"{CTL_PREFIX}*{SUFFIX}"))]
        if not dirs:
            print("loopgain2 check FAILED: no two-injection record found under corners/",
                  file=sys.stderr)
            return 1
    bad = []
    for corners_dir in dirs:
        rid = os.path.basename(corners_dir)
        sim_dir = os.path.dirname(os.path.dirname(corners_dir))
        tmp = tempfile.mkdtemp()
        out_dir = os.path.join(tmp, "combined")
        os.makedirs(out_dir)
        out_csv = os.path.join(tmp, "cmp.csv")
        out_json = os.path.join(tmp, "cmp.json")
        rc = cmd_report(argparse.Namespace(corners_dir=corners_dir, ceiling=a.ceiling,
                                           out_csv=out_csv, out_json=out_json),
                        out_dir=out_dir)
        # rc != 0 means the committed record has INVALID points. An ordinary
        # record must not: that is a check failure. The one exception is a
        # point the record's own campaign.json DECLARES an uncertified
        # diagnostic (the DR-0015 E2 P3 point, issue #218), which is kept
        # with its measured numbers and verbatim error but never certified.
        # Any other invalid point -- or an invalid point in a record that
        # declares none -- still fails. Reproduction (every regenerated
        # byte equals the committed byte) is gated below as before.
        if rc != 0:
            allowed = uncertified_diagnostic_points(rid, sim_dir)
            try:
                with open(out_json, encoding="utf-8") as fh:
                    rows = json.load(fh)["rows"]
            except (OSError, ValueError, KeyError):
                rows = []
                bad.append(f"{corners_dir}: reconstruction does not validate "
                           "(report unreadable)")
            for r in rows:
                if r.get("valid"):
                    continue
                key = f"{r['corner']}_{r['temp_c']}c_r{r['res_section'][4:]}"
                if key not in allowed:
                    bad.append(f"{corners_dir}: point {key} does not validate and is not a "
                               "declared uncertified diagnostic")
        for fn in sorted(os.listdir(out_dir)):
            got, want = os.path.join(out_dir, fn), os.path.join(corners_dir, fn)
            if not os.path.isfile(want):
                bad.append(f"{want}: missing")
            elif open(want, "rb").read() != open(got, "rb").read():
                bad.append(f"{want}: differs from regeneration")
        stray = sorted(set(glob.glob(os.path.join(corners_dir, f"{TWO_PREFIX}*{SUFFIX}")))
                       - {os.path.join(corners_dir, fn) for fn in os.listdir(out_dir)})
        bad += [f"{p}: committed but not regenerated" for p in stray]
        want_csv = os.path.join(sim_dir, "records", f"{rid}.loopgain2.csv")
        want_json = os.path.join(sim_dir, "evidence", rid, "loopgain2-report.json")
        for got, want in ((out_csv, want_csv), (out_json, want_json)):
            if not os.path.isfile(want):
                bad.append(f"{want}: missing")
            elif open(want, "rb").read() != open(got, "rb").read():
                bad.append(f"{want}: differs from regeneration")
        want_md = os.path.join(sim_dir, "records", f"{rid}.loopgain2.md")
        try:
            if open(want_md, encoding="utf-8").read() != record_md(rid, sim_dir):
                bad.append(f"{want_md}: differs from regeneration")
        except OSError as exc:
            bad.append(f"{want_md}: {exc}")
    if bad:
        print("loopgain2 check FAILED:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print("loopgain2: committed artifacts reproduce exactly", file=sys.stderr)
    return 0


def cmd_reconstruct(a):
    rec = reconstruct(a.v_csv, a.i_csv)
    write_loopgain_trace(a.out, rec["freqs"][:rec["cut"]], rec["T"][:rec["cut"]])
    print(json.dumps(rec["diag"], indent=1))
    return 0


def cmd_check_export(a):
    bad = check_export(a.csv, a.ncols, a.ceiling)
    for b in bad:
        print(f"loopgain2: {b}", file=sys.stderr)
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconstruct", help="reconstruct one point's resolved-prefix trace")
    r.add_argument("--v-csv", required=True)
    r.add_argument("--i-csv", required=True)
    r.add_argument("--out", required=True)
    e = sub.add_parser("check-export", help="screen one raw export (rows/cols/frequency span)")
    e.add_argument("csv")
    e.add_argument("ncols", type=int)
    e.add_argument("ceiling")
    o = sub.add_parser("op", help="canonicalise + validate the campaign operating point (issue #218)")
    o.add_argument("--load-ma", default=None, help="load current [mA] (default: legacy 1 mA)")
    o.add_argument("--cout-uf", default=None, help="effective Cout [uF] (default: legacy 1 uF)")
    o.add_argument("--esr-ohm", default=None, help="Cout series ESR [ohm] (default: legacy 0)")
    o.add_argument("--json", action="store_true", help="emit the full JSON document (machine form)")
    p = sub.add_parser("report", help="reconstruct + compare every point under a corners dir")
    p.add_argument("--corners-dir", required=True)
    p.add_argument("--ceiling", default="10g")
    p.add_argument("--out-csv", required=True)
    p.add_argument("--out-json", required=True)
    m = sub.add_parser("record-md", help="write records/<rid>.loopgain2.md from committed files")
    m.add_argument("--record", required=True)
    c = sub.add_parser("check", help="CI: byte-compare the committed artifacts")
    c.add_argument("--corners-dir", default=None,
                   help="one record's corners dir (default: every two-injection record)")
    c.add_argument("--ceiling", default="10g")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "reconstruct":
            return cmd_reconstruct(a)
        if a.cmd == "check-export":
            return cmd_check_export(a)
        if a.cmd == "op":
            return cmd_op(a)
        if a.cmd == "report":
            return cmd_report(a)
        if a.cmd == "record-md":
            return cmd_record_md(a)
        return cmd_check(a)
    except Loopgain2Error as exc:
        print(f"loopgain2: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
