#!/usr/bin/env python3
"""Two-injection (Middlebrook) loop-gain reconstruction (issue #135).

Offline, stdlib-only: reconstructs the SG13CMOS5L loop gain from the RAW
COMPLEX probe responses of the two-injection benches and compares it with
the single-injection bench, WITHOUT re-running a simulator and without the
single-injection method's zero-gate-current assumption.

Method (documented before use; the primary reference is S. M. Sandler /
R. D. Middlebrook's measurement formulation -- R. D. Middlebrook,
"Measurement of loop gain in feedback systems", Int. J. Electronics 38.4
(1975) 485-512; the same combination appears as the "voltage/current
injection" method in Erickson & Maksimovic, Fundamentals of Power
Electronics, ch. 9. Tian's single-structure form (Tian et al., "Striving
for small-signal stability ...", IEEE TCAS-I 48.6 (2001)) reduces to the
same two-experiment information; we use the two-run Middlebrook form
because the existing break geometry (FB -> FBAMP, a MOSFET gate) already
hosts the voltage injection verbatim).

Setup. The loop is measured at the FB -> FBAMP wire (the feedback-divider
node -> the error amplifier's INP pin). Looking into the divider side from
the injection point is a Thevenin source Vt = T'(s) * V_B behind an
impedance Zt (T'(s) = k_divider * G_amp(s) is the TRUE loop transfer;
V_B is the amplifier-input voltage). Looking into the amplifier side is
the load impedance Zl (the input-pair gate: ~infinite at DC, capacitive
and falling at hundreds of MHz). Write u = Zt/Zl (the LOADING RATIO; the
single-injection method is exact only as u -> 0).

  Voltage injection (tb_loopgain2v, an ideal series AC source between FB
  and FBAMP): solving KCL on both sides of the injection gives
      1/Hv = T' - u,      Hv(s) = v(fbamp)/v(fb).
  So Hv alone equals 1/T' only when u = 0 -- exactly the zero-gate-current
  assumption issue #135 questions above the in-band crossing.

  Current injection (tb_loopgain2i, the loop INTACT behind a 0 V ammeter
  `Vmeas FB FBAMP 0 dc 0`, a shunt AC source `Iinx 0 FBAMP dc 0 ac 1`
  pushing ix = 1 into the driven side): the ammeter reads the BRIDGE
  current i_m (positive flowing FB -> FBAMP, ngspice's n+ -> n- branch
  convention), not the load current. KCL on both nodes gives
  i_l = ix + i_m (into the load) and i_s = -i_m (back into the divider
  side), so
      Hi = i_s/i_l = -i_m/(1 + i_m) = (1 - T')/u.
  Hi carries exactly the information the voltage injection cannot see: it
  vanishes as u -> 0, where the single-injection reading is already exact.

  Combination (per frequency, complex arithmetic):
      T' = (1 + Hi/Hv) / (1 + Hi),        and this repo's convention is
      L(s) = -T'(s)  (healthy negative feedback: large positive real L(0)).
  The combination is exact for any u but ill-conditioned where 1 + Hi -> 0
  (the shunt injection seeing a near-open circuit, i.e. T' ~= 1 + Zt/Zl);
  every frequency's |1 + Hi| is checked and reported, and a frequency that
  fails the conditioning floor fails the point loudly -- no silently wrong
  trace is ever written.

  Difference identity. Subtracting the two readings gives the exact
  identity  L_single - L_two = u(s)  (linear, complex): the difference
  between the single- and two-injection traces IS the loading ratio the
  single-injection bench ignores. The campaign reports u(f) per point,
  reconstructed from the raw probe pair via
      u = (Hv - 1) / (Hv * (1 + Hi)),
  so the measured method difference is checked against this independently
  reconstructed loading ratio (validate_against_control's loading-explain
  bound: below f_ugf/10, |L2 - L1| <= 3|u| + 1e-6|L1|).

Sign conventions (validated against the analytic fixture in
test_loopgain2.py and, on real decks, by run_loopgain2.sh --validate
before any fleet run):

  * i(vmeas) > 0 is the current flowing FB -> FBAMP through the ammeter
    (ngspice reports a positive branch current for `Vxxx n+ n-` flowing
    n+ -> n- through the source): the BRIDGE current i_m, not the load
    current.
  * Iinx 0 FBAMP pushes its AC current ix = 1 INTO FBAMP.
  * Hv = v(fbamp)/v(fb); Hi = -i_m/(1 + i_m) with i_m = i(vmeas); L = -T'.

Stated tolerances (fixed BEFORE interpreting any silicon-model result;
see README.md "Loop-gain measurement method -- two-injection"):

  TOL_DECK_IDENTITY   1e-6 (relative, complex) -- tb_loopgain2v and
                      tb_loopgain_ctl are the SAME circuit: below the first
                      0 dB crossing their traces must agree to round-trip
                      precision. A larger deviation is a plumbing bug, not
                      physics.
  TOL_U_LF            1e-3 -- u(1 Hz) must be negligible (the gate is a
                      high impedance at low frequency; this is the premise
                      that makes the in-band single-injection record
                      meaningful at all).
  TOL_DIFF_EXPLAIN    below f_ugf/10 the two methods may differ only by the
                      measured loading: |L2 - L1| <= 3*|u| + 1e-6*|L1|.
                      Differences beyond that fail the point (something
                      other than gate loading is going on and must be
                      investigated, not averaged away).
  MIN_DENOM           1e-4 -- the |1 + Hi| conditioning floor.
  RECONSTRUCTION_DB_FLOOR -300 dB -- frequencies where the true |T'| is
                      small enough that the combination underflows double
                      precision are clamped here (never near any bound).

Usage:
    loopgain2.py reconstruct --v-csv F --i-csv F --out F --ceiling 10g
    loopgain2.py report --corners-dir D --ceiling 10g --out-csv F --out-json F
    loopgain2.py check --corners-dir D --ceiling 10g --out-csv F --out-json F
"""
import argparse
import cmath
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ac_sweep  # noqa: E402
import ac_metrics as am  # noqa: E402
from dc_metrics import read_wrdata  # noqa: E402

CTL_PREFIX = "loopgain_ctl_"
V_PREFIX = "loopgain2v_"
I_PREFIX = "loopgain2i_"
TWO_PREFIX = "loopgain2_"
SUFFIX = "_ac.csv"

FREQ_RTOL = 1e-9           # both decks share one analysis line: exact axis
TOL_DECK_IDENTITY = 1e-6   # 2v vs control: same circuit, round-trip precision
TOL_U_LF = 1e-3            # u at 1 Hz: the gate must be a high-Z load at LF
TOL_DIFF_EXPLAIN = 3.0     # |L2-L1| <= TOL_DIFF_EXPLAIN*|u| + 1e-6*|L1|
DIFF_FLOOR_REL = 1e-6      # solver-noise floor under the explain bound
MIN_DENOM = 1e-4           # |1 + Hi| conditioning floor (complex magnitude)
ORIENT_MAX_DEG = 45.0      # phase(L at 1 Hz) must sit within this of 0 deg
# The true loop transfer can have a deep transmission null above the second
# crossing; near its bottom the combination's numerator (1 + Hi/Hv)
# underflows double precision (|T'| below ~1e-16 of the injection scale).
# Such frequencies are clamped to this floor in the written trace: far below
# the -10 dB ceiling floor and the GM bound, so no classification outcome
# can depend on the clamp value, and the raw-complex exports stay the
# reproducible source of record (loopgain2.py check regenerates the clamp
# bit-for-bit). The count is reported per point as n_underflow.
RECONSTRUCTION_DB_FLOOR = -300.0

CSV_FIELDS = [
    "corner", "temp_c", "res_section",
    "ctl_dc_gain_db", "ctl_n_0db_crossings", "ctl_unity_gain_freq_hz",
    "ctl_phase_margin_deg", "ctl_phase_margin_worst_deg",
    "ctl_n_gain_margin_crossings", "ctl_gain_margin_freq_hz",
    "ctl_gain_margin_db", "ctl_db_at_1ghz", "ctl_db_at_ceiling",
    "ctl_second_crossing_hz",
    "lg2_dc_gain_db", "lg2_n_0db_crossings", "lg2_unity_gain_freq_hz",
    "lg2_phase_margin_deg", "lg2_phase_margin_worst_deg",
    "lg2_n_gain_margin_crossings", "lg2_gain_margin_freq_hz",
    "lg2_gain_margin_db", "lg2_db_at_1ghz", "lg2_db_at_ceiling",
    "lg2_second_crossing_hz",
    "pm_delta_deg", "gm_delta_db", "db_diff_at_1ghz", "db_diff_at_ceiling",
    "max_abs_db_diff", "max_abs_db_diff_hz",
    "u_abs_at_1hz", "u_abs_max", "u_abs_max_hz",
    "u_abs_at_1ghz", "u_abs_at_ceiling", "min_abs_1_plus_hi", "n_underflow",
    "v2ctl_max_rel_diff", "valid",
]


class Loopgain2Error(Exception):
    pass


# --------------------------------------------------------------------------- #
# core algebra
# --------------------------------------------------------------------------- #

def combine(hv, hi, min_den=MIN_DENOM):
    """Middlebrook combination T = (1 + Hi/Hv)/(1 + Hi) for one frequency.

    hv, hi: complex. Returns T (complex). Raises Loopgain2Error on a zero
    Hv or Hi denominator, on nonfinite inputs, or when |1 + Hi| < min_den
    (the combination is genuinely undetermined there; see module docstring).
    """
    for name, z in (("Hv", hv), ("Hi", hi)):
        if not (cmath.isfinite(z)):
            raise Loopgain2Error(f"{name} is nonfinite ({z!r})")
    if hv == 0:
        raise Loopgain2Error("Hv is exactly zero (voltage probe saw no drive)")
    if hi == 0:
        raise Loopgain2Error("Hi is exactly zero (current probe saw no split)")
    den = 1.0 + hi
    if abs(den) < min_den:
        raise Loopgain2Error(
            f"|1 + Hi| = {abs(den):.3g} < {min_den:g}: the shunt injection sees a "
            "near-open circuit and the combination is undetermined at this "
            "frequency (conditioning floor, not a simulator failure)")
    return (1.0 + hi / hv) / den


def loading_ratio(hv, hi):
    """u = Zt/Zl = (Hv - 1)/(Hv*(1 + Hi)) for one frequency (complex).

    Derived from the same two measurement equations as combine():
    1/Hv = T' - u and Hi = (1 - T')/u give u*(1 + Hi) = 1 - 1/Hv. This is
    the term the single-injection method ignores: the measured difference of
    the two reduced traces equals it exactly (L_single - L_two = u). Raises
    on the same degenerate inputs combine() refuses.
    """
    for name, z in (("Hv", hv), ("Hi", hi)):
        if not (cmath.isfinite(z)):
            raise Loopgain2Error(f"{name} is nonfinite ({z!r})")
    if hv == 0 or (1.0 + hi) == 0:
        raise Loopgain2Error("degenerate Hv/Hi (zero denominator in u)")
    return (hv - 1.0) / (hv * (1.0 + hi))


# --------------------------------------------------------------------------- #
# file readers / writers
# --------------------------------------------------------------------------- #

def _freq_columns(path, rows, ncols):
    """wrdata writes (freq, value) pairs: the freq column repeats. Require
    every repeat to agree exactly, and the axis to be strictly increasing."""
    step = 2
    for r in rows:
        f0 = r[0]
        for k in range(0, ncols, step):
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
    """tb_loopgain2i wrdata (4 columns) -> (freqs, il) complex."""
    rows = read_wrdata(path, 4)
    if not rows:
        raise Loopgain2Error(f"{path}: no rows")
    freqs = _freq_columns(path, rows, 4)
    il = [complex(r[1], r[3]) for r in rows]
    return freqs, il


def read_loopgain_trace(path):
    """Classic 4-column loop-gain wrdata (f, dB, f, deg) -> (freqs, L)."""
    rows = read_wrdata(path, 4)
    if not rows:
        raise Loopgain2Error(f"{path}: no rows")
    freqs = _freq_columns(path, rows, 4)
    L = [10.0 ** (r[1] / 20.0) * cmath.exp(1j * math.radians(r[3])) for r in rows]
    return freqs, L


def write_loopgain_trace(path, freqs, L):
    """Write the combined trace in the CLASSIC 4-column loop-gain wrdata
    layout (f, dB, f, deg) so the unchanged ac_metrics.classify_margins and
    every downstream reader consume it like any single-injection trace."""
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

def reconstruct(v_csv, i_csv):
    """Reconstruct L(s) from the two raw probe exports of ONE point.

    Returns (freqs, L, diag) where diag carries the conditioning evidence:
    min |1 + Hi|, u(f) summary statistics, the orientation check at 1 Hz.
    Raises Loopgain2Error on any validation failure (never returns a trace
    it could not fully validate).
    """
    vfreqs, fb, fbamp = read_voltage_export(v_csv)
    ifreqs, il = read_current_export(i_csv)
    if len(vfreqs) != len(ifreqs):
        raise Loopgain2Error(
            f"frequency grids differ in length: {v_csv} has {len(vfreqs)}, "
            f"{i_csv} has {len(ifreqs)}")
    for a, b in zip(vfreqs, ifreqs):
        if not math.isclose(a, b, rel_tol=FREQ_RTOL):
            raise Loopgain2Error(f"frequency grids differ: {a!r} vs {b!r}")

    hv = []
    for a, b in zip(fbamp, fb):
        if a == 0 or b == 0:
            raise Loopgain2Error("zero probe voltage (v(fb) or v(fbamp) is exactly 0)")
        hv.append(a / b)
    hi = []
    for z in il:
        if z == 0:
            raise Loopgain2Error("i(vmeas) is exactly 0: no injected current "
                                 "reached the ammeter (probe wiring, not physics)")
        if z == -1.0:
            raise Loopgain2Error("i(vmeas) is exactly -1: no injected current "
                                 "reached the load (i_l = 1 + i_m = 0); the "
                                 "current-injection experiment carries no information")
        # i_m = i(vmeas) is the BRIDGE current (FB->FBAMP positive); the load
        # draws i_l = 1 + i_m and the divider side takes i_s = -i_m, so
        # Hi = i_s/i_l = -i_m/(1 + i_m) (KCL; see module docstring).
        hi.append(-z / (1.0 + z))

    T = [combine(a, b) for a, b in zip(hv, hi)]
    L = [-z for z in T]
    n_underflow = 0
    for k, z in enumerate(L):
        if z == 0 or db(z) < RECONSTRUCTION_DB_FLOOR:
            L[k] = complex(-(10.0 ** (RECONSTRUCTION_DB_FLOOR / 20.0)), 0.0)
            n_underflow += 1
    us = [loading_ratio(a, b) for a, b in zip(hv, hi)]

    # Orientation sanity (probe-polarity detector, not a spec verdict): a
    # healthy negative-feedback loop has L(1 Hz) large, positive REAL --
    # phase within ORIENT_MAX_DEG of 0. A swapped probe or a flipped
    # injection lands near +/-180 deg and fails here instead of producing a
    # plausible-looking but sign-flipped trace.
    l0_deg = math.degrees(cmath.phase(L[0]))
    if abs(am.wrap180(l0_deg)) > ORIENT_MAX_DEG:
        raise Loopgain2Error(
            f"orientation check failed: phase(L at 1 Hz) = {l0_deg:.1f} deg, "
            f"expected within +-{ORIENT_MAX_DEG:g} deg of 0 for a "
            "negative-feedback loop (swapped probe polarity?)")

    absu = [abs(z) for z in us]
    denom = [abs(1.0 + z) for z in hi]
    diag = {
        "u_abs_at_1hz": absu[0],
        "u_abs_max": max(absu),
        "u_abs_max_hz": vfreqs[absu.index(max(absu))],
        "u_abs_at_1ghz": absu[_index_of(vfreqs, 1e9)],
        "u_abs_at_ceiling": absu[-1],
        "min_abs_1_plus_hi": min(denom),
        "phase_l0_deg": l0_deg,
        "n_points": len(vfreqs),
        "n_underflow": n_underflow,
    }
    return vfreqs, L, hv, hi, us, diag


def _index_of(freqs, target):
    return min(range(len(freqs)), key=lambda k: abs(math.log10(freqs[k]) - math.log10(target)))


def db(z):
    return 20.0 * math.log10(abs(z))


def zero_db_crossings(freqs, L):
    """All 0 dB crossings, log-interpolated (same convention as
    ac_metrics.loopgain_metrics: linear interp of the unwrapped phase)."""
    dbs = [db(z) for z in L]
    degs = am.unwrap_deg([math.degrees(cmath.phase(z)) for z in L])
    out = []
    for i in range(1, len(dbs)):
        if (dbs[i - 1] - 0.0) * (dbs[i] - 0.0) < 0:
            frac = (0.0 - dbs[i - 1]) / (dbs[i] - dbs[i - 1])
            logf = math.log10(freqs[i - 1]) + frac * (math.log10(freqs[i]) - math.log10(freqs[i - 1]))
            out.append(10.0 ** logf)
    return out


def interp_db_at(freqs, L, f_target):
    """|L| in dB at f_target, log-interpolated between neighbours."""
    k = _index_of(freqs, f_target)
    if freqs[k] == f_target:
        return db(L[k])
    i, j = (k, k + 1) if freqs[k] < f_target else (k - 1, k)
    if i < 0 or j >= len(freqs):
        return db(L[k])
    frac = (math.log10(f_target) - math.log10(freqs[i])) / (math.log10(freqs[j]) - math.log10(freqs[i]))
    return db(L[i]) + frac * (db(L[j]) - db(L[i]))


def validate_against_control(freqs, L, hv, us, ctl_csv):
    """Cross-checks of one reconstructed point against the SAME POINT's
    single-injection control trace. Returns a diagnostics dict; raises
    Loopgain2Error on any stated-tolerance failure (see module docstring
    for the tolerances and why they are what they are)."""
    cfreqs, ctl = read_loopgain_trace(ctl_csv)
    if len(cfreqs) != len(freqs):
        raise Loopgain2Error(
            f"control trace has {len(cfreqs)} rows, exports have {len(freqs)}")
    for a, b in zip(cfreqs, freqs):
        if not math.isclose(a, b, rel_tol=FREQ_RTOL):
            raise Loopgain2Error(f"control frequency axis differs: {a!r} vs {b!r}")

    # (1) deck identity: the 2v circuit IS the control circuit. Hv is the
    # 2v probe ratio; the control's L is -v(fb)/v(fbamp) = -1/Hv of the same
    # run conditions. Compare Hv against the control-derived -1/L... i.e.
    # Hv_ctl = -1/ctl_L; require complex agreement to round-trip precision
    # below the first 0 dB crossing of the control (above it the ratio is a
    # difference of large near-cancelling terms and round-off dominates --
    # identity is asserted only where it is meaningful).
    ctl_dbs = [db(z) for z in ctl]
    crossings = zero_db_crossings(cfreqs, ctl)
    if not crossings:
        raise Loopgain2Error("control trace has no 0 dB crossing (unexpected for this loop)")
    ugf = crossings[0]
    ident = 0.0
    for k, (fr, z) in enumerate(zip(cfreqs, ctl)):
        if fr > ugf:
            break
        hv_ctl = -1.0 / z
        rel = abs(hv[k] - hv_ctl) / abs(hv_ctl)
        ident = max(ident, rel)
    if ident > TOL_DECK_IDENTITY:
        raise Loopgain2Error(
            f"deck identity failed: max rel diff(2v, control) = {ident:.3g} "
            f"> {TOL_DECK_IDENTITY:g} below the first crossing -- the two decks "
            "disagree, which is a plumbing bug (same circuit, same op), not physics")

    # (2) low-frequency loading premise
    if abs(us[0]) > TOL_U_LF:
        raise Loopgain2Error(
            f"u(1 Hz) = {abs(us[0]):.3g} > {TOL_U_LF:g}: the amplifier input is "
            "not a high-Z load at low frequency; investigate before reading "
            "any margin off either method")

    # (3) below f_ugf/10 the methods may differ only by the measured loading
    worst = 0.0
    for k, fr in enumerate(freqs):
        if fr > ugf / 10.0:
            break
        diff = abs(L[k] - ctl[k])
        bound = TOL_DIFF_EXPLAIN * abs(us[k]) + DIFF_FLOOR_REL * abs(ctl[k])
        worst = max(worst, diff / bound if bound > 0 else float("inf"))
    if worst > 1.0:
        raise Loopgain2Error(
            f"loading-explain check failed below f_ugf/10: worst |L2-L1| exceeds "
            f"{TOL_DIFF_EXPLAIN:g}|u| + floor by {worst:.3g}x -- the difference "
            "between the methods is not explained by the measured gate loading")

    maxdiff, maxdiff_hz = 0.0, freqs[0]
    for k, fr in enumerate(freqs):
        d = abs(db(L[k]) - ctl_dbs[k])
        if d > maxdiff:
            maxdiff, maxdiff_hz = d, fr
    return {"v2ctl_max_rel_diff": ident, "ctl_ugf_hz": ugf,
            "max_abs_db_diff": maxdiff, "max_abs_db_diff_hz": maxdiff_hz,
            "ctl_dbs": ctl_dbs}


# --------------------------------------------------------------------------- #
# per-point driver
# --------------------------------------------------------------------------- #

def parse_suffix(sfx):
    """`tt_27c_rtyp` -> (corner, temp_c, res_section)."""
    corner, tempc, rlabel = sfx.split("_")
    return corner, tempc[:-1], f"res_{rlabel[1:]}"


def point_row(corners_dir, sfx, ceiling, out_dir=None):
    """Reconstruct + validate one point; return its comparison-CSV row dict.

    The combined trace is written beside the exports under `corners_dir`,
    or under `out_dir` when given (check mode: never touch committed files)."""
    ctl_csv = os.path.join(corners_dir, f"{CTL_PREFIX}{sfx}{SUFFIX}")
    v_csv = os.path.join(corners_dir, f"{V_PREFIX}{sfx}{SUFFIX}")
    i_csv = os.path.join(corners_dir, f"{I_PREFIX}{sfx}{SUFFIX}")
    freqs, L, hv, hi, us, diag = reconstruct(v_csv, i_csv)
    xdiag = validate_against_control(freqs, L, hv, us, ctl_csv)
    corner, temp_c, res_section = parse_suffix(sfx)

    # Combined trace: written in the classic 4-column layout, then read back
    # through the UNCHANGED legacy metrics so the classified numbers and the
    # compared numbers come from one parser.
    combined_path = os.path.join(out_dir or corners_dir, f"{TWO_PREFIX}{sfx}{SUFFIX}")
    write_loopgain_trace(combined_path, freqs, L)
    lg2 = am.loopgain_metrics(combined_path)

    cfreqs, ctl_L = read_loopgain_trace(ctl_csv)
    ctl = am.loopgain_metrics(ctl_csv)
    ctl_crossings = zero_db_crossings(cfreqs, ctl_L)
    lg2_crossings = zero_db_crossings(freqs, L)

    def _second(cs):
        return cs[1] if len(cs) >= 2 else None

    row = {"corner": corner, "temp_c": temp_c, "res_section": res_section}
    for pre, m, second, LL in (("ctl", ctl, _second(ctl_crossings), ctl_L),
                               ("lg2", lg2, _second(lg2_crossings), L)):
        for key in ("dc_gain_db", "n_0db_crossings", "unity_gain_freq_hz",
                    "phase_margin_deg", "phase_margin_worst_deg",
                    "n_gain_margin_crossings", "gain_margin_freq_hz", "gain_margin_db"):
            row[f"{pre}_{key}"] = None if m is None else m.get(key)
        row[f"{pre}_second_crossing_hz"] = second
        row[f"{pre}_db_at_1ghz"] = interp_db_at(freqs, LL, 1e9)
        row[f"{pre}_db_at_ceiling"] = db(LL[-1])
    row["pm_delta_deg"] = ((row["lg2_phase_margin_deg"] - row["ctl_phase_margin_deg"])
                           if None not in (row["lg2_phase_margin_deg"], row["ctl_phase_margin_deg"]) else None)
    row["gm_delta_db"] = ((row["lg2_gain_margin_db"] - row["ctl_gain_margin_db"])
                          if None not in (row["lg2_gain_margin_db"], row["ctl_gain_margin_db"]) else None)
    row["db_diff_at_1ghz"] = row["lg2_db_at_1ghz"] - row["ctl_db_at_1ghz"]
    row["db_diff_at_ceiling"] = row["lg2_db_at_ceiling"] - row["ctl_db_at_ceiling"]
    row["max_abs_db_diff"] = xdiag["max_abs_db_diff"]
    row["max_abs_db_diff_hz"] = xdiag["max_abs_db_diff_hz"]
    row.update({k: diag[k] for k in ("u_abs_at_1hz", "u_abs_max", "u_abs_max_hz",
                                     "u_abs_at_1ghz", "u_abs_at_ceiling",
                                     "min_abs_1_plus_hi", "n_underflow")})
    row["v2ctl_max_rel_diff"] = xdiag["v2ctl_max_rel_diff"]
    row["valid"] = True
    return row



# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.9g}"
    return str(x)


def all_suffixes(corners_dir):
    out = []
    for fn in sorted(os.listdir(corners_dir)):
        if fn.startswith(CTL_PREFIX) and fn.endswith(SUFFIX):
            out.append(fn[len(CTL_PREFIX):-len(SUFFIX)])
    return out


def cmd_report(a, out_dir=None):
    corners_dir = os.path.abspath(a.corners_dir)
    rows = []
    for sfx in all_suffixes(corners_dir):
        try:
            rows.append(point_row(corners_dir, sfx, a.ceiling, out_dir))
            print(f"loopgain2: {sfx}: ok (u_max={rows[-1]['u_abs_max']:.3g}, "
                  f"max dB diff {rows[-1]['max_abs_db_diff']:.3g} at "
                  f"{rows[-1]['max_abs_db_diff_hz']:.3g} Hz)", file=sys.stderr)
        except Loopgain2Error as exc:
            print(f"loopgain2: {sfx}: FAILED: {exc}", file=sys.stderr)
            corner, temp_c, res_section = parse_suffix(sfx)
            rows.append({"corner": corner, "temp_c": temp_c,
                         "res_section": res_section, "valid": False})
    import csv
    with open(a.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: _fmt(row.get(k)) for k in CSV_FIELDS})
    nbad = sum(1 for r in rows if not r.get("valid"))
    doc = {"schema_version": 1, "ceiling": ac_sweep.canonical(a.ceiling),
           "points": len(rows), "invalid": nbad,
           "tolerances": {"deck_identity_rel": TOL_DECK_IDENTITY,
                          "u_at_1hz": TOL_U_LF,
                          "diff_explain_factor": TOL_DIFF_EXPLAIN,
                          "diff_floor_rel": DIFF_FLOOR_REL,
                          "min_abs_1_plus_hi": MIN_DENOM,
                          "orientation_max_deg": ORIENT_MAX_DEG},
           "u_abs_max_over_points": max((r["u_abs_max"] for r in rows if r.get("valid")), default=None),
           "max_abs_db_diff_over_points": max((r["max_abs_db_diff"] for r in rows if r.get("valid")), default=None),
           "rows": rows}
    with open(a.out_json, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    if nbad:
        print(f"loopgain2: {nbad} of {len(rows)} points FAILED validation", file=sys.stderr)
        return 1
    print(f"loopgain2: all {len(rows)} points reconstructed and validated", file=sys.stderr)
    return 0


def cmd_check(a):
    """CI mode: rebuild every combined trace + the comparison CSV/JSON from
    the committed exports and byte-compare (reproducibility of the
    reconstruction from the committed raw responses). Writes only into a
    throwaway temp dir: committed evidence is never touched. Without
    --corners-dir, every corners/ subdir that holds two-injection exports
    (loopgain_ctl_*_ac.csv) is checked, newest last."""
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    if a.corners_dir:
        dirs = [os.path.abspath(a.corners_dir)]
    else:
        corners_root = os.path.join(here, "corners")
        dirs = []
        for name in sorted(os.listdir(corners_root)):
            d = os.path.join(corners_root, name)
            if os.path.isdir(d) and glob.glob(os.path.join(d, f"{CTL_PREFIX}*{SUFFIX}")):
                dirs.append(d)
        if not dirs:
            print("loopgain2 check FAILED: no two-injection record found under corners/",
                  file=sys.stderr)
            return 1
    bad = []
    for corners_dir in dirs:
        out_dir = os.path.join(tempfile.mkdtemp(), "combined")
        os.makedirs(out_dir)
        out_csv = os.path.join(out_dir, "..", "cmp.csv")
        out_json = os.path.join(out_dir, "..", "cmp.json")
        rc = cmd_report(argparse.Namespace(corners_dir=corners_dir, ceiling=a.ceiling,
                                           out_csv=out_csv, out_json=out_json),
                        out_dir=out_dir)
        if rc != 0:
            bad.append(f"{corners_dir}: reconstruction does not validate")
        for fn in sorted(os.listdir(out_dir)):
            got = os.path.join(out_dir, fn)
            want = os.path.join(corners_dir, fn)
            if not os.path.isfile(want):
                bad.append(f"{want}: missing")
            elif open(want, "rb").read() != open(got, "rb").read():
                bad.append(f"{want}: differs from regeneration")
        for got, want in ((out_csv, os.path.join(corners_dir, "..", "records",
                                                os.path.basename(corners_dir) + ".loopgain2.csv")),
                          (out_json, os.path.join(corners_dir, "..", "evidence",
                                                  os.path.basename(corners_dir),
                                                  "loopgain2-report.json"))):
            if not os.path.isfile(want):
                bad.append(f"{want}: missing")
            elif open(want, "rb").read() != open(got, "rb").read():
                bad.append(f"{want}: differs from regeneration")
    if bad:
        print("loopgain2 check FAILED:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print("loopgain2: committed artifacts reproduce exactly", file=sys.stderr)
    return 0


def cmd_reconstruct(a):
    freqs, L, _hv, _hi, _us, diag = reconstruct(a.v_csv, a.i_csv)
    write_loopgain_trace(a.out, freqs, L)
    print(json.dumps(diag, indent=1))
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
    r = sub.add_parser("reconstruct", help="reconstruct one point's combined trace")
    r.add_argument("--v-csv", required=True)
    r.add_argument("--i-csv", required=True)
    r.add_argument("--out", required=True)
    e = sub.add_parser("check-export", help="screen one raw export (rows/cols/frequency span)")
    e.add_argument("csv")
    e.add_argument("ncols", type=int)
    e.add_argument("ceiling")
    p = sub.add_parser("report", help="reconstruct + compare every point under a corners dir")
    p.add_argument("--corners-dir", required=True)
    p.add_argument("--ceiling", default="10g")
    p.add_argument("--out-csv", required=True)
    p.add_argument("--out-json", required=True)
    c = sub.add_parser("check", help="CI: byte-compare the committed artifacts")
    c.add_argument("--corners-dir", default=None,
                   help="one record's corners dir (default: every two-injection record)")
    c.add_argument("--ceiling", default="10g")
    c.add_argument("--out-csv", default=None, help="(ignored; kept for symmetry)")
    c.add_argument("--out-json", default=None, help="(ignored; kept for symmetry)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "reconstruct":
            return cmd_reconstruct(a)
        if a.cmd == "check-export":
            return cmd_check_export(a)
        if a.cmd == "report":
            return cmd_report(a)
        return cmd_check(a)
    except Loopgain2Error as exc:
        print(f"loopgain2: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
