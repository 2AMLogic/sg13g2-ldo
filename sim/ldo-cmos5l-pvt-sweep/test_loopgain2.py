"""Independent analytic-fixture tests for the two-injection (Middlebrook)
reconstruction (issue #135). stdlib only; no simulator, no PDK.

The fixture is NOT built from the equations loopgain2.py inverts. It is a
small explicit linear circuit, solved directly by modified nodal analysis
(MNA) at any complex frequency s:

    B (FBAMP) --Cin-- gnd                 amplifier input (gate) loading
    B ---------Cf---- O                   bilateral feed-through (Cgd-like)
    O: VCCS -gm*v(B), Ro || Co to gnd     inverting gain stage, output pole
    O ---------R1---- A (FB)              feedback divider
    A ---------R2---- gnd, Ca to gnd

Closed loop: A wired to B. The fixture's own exports are produced the way
the fleet benches produce theirs (Vbreak FB FBAMP 0 ac 1; loop intact
behind Vmeas FB FBAMP 0 with Iinx 0 FBAMP ac 1) and written in the fleet's
`%.8e` format. The tests then compare loopgain2's reconstruction against
truths computed WITHOUT any injection: Bode's return ratio of the gm source
(gm nulled, a test source in its place), the cut network's y-parameters,
and the closed-loop natural frequencies (roots of the intact circuit's
nodal determinant).

    python3 -m unittest sim/ldo-cmos5l-pvt-sweep/test_loopgain2.py -v
"""
import cmath
import csv
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import loopgain2 as lg2  # noqa: E402

FREQS = [10.0 ** (k / 20.0) for k in range(0, 201)]   # 1 Hz .. 1e10, 20 pts/dec

# Nodes: 0 = B (FBAMP), 1 = A (FB), 2 = O. Ground implicit.
BASE = dict(gm=1e-3, Ro=1e5, Co=1e-11, R1=3e5, R2=1e5, Ca=0.2e-12,
            Cin=2e-12, Cf=0.0, Rg=None)
UNILATERAL = dict(BASE)                      # finite input loading, no feed-through
BILATERAL = dict(BASE, Cf=0.5e-12)           # plus a reverse/feed-forward path
LIGHT = dict(BASE, Cin=5e-15, Cf=0.5e-15)    # a near-ideal gate: the single injection is fine in band


def solve(A, b):
    """Dense complex Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [list(row) + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if M[c][c] == 0:
            raise ZeroDivisionError("singular fixture matrix")
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def y_matrix(s, p, gm_on=True):
    Y = [[0j] * 3 for _ in range(3)]

    def add(i, j, y):
        for k in (i, j):
            if k is not None:
                Y[k][k] += y
        if i is not None and j is not None:
            Y[i][j] -= y
            Y[j][i] -= y

    add(0, None, s * p["Cin"])
    if p["Rg"]:
        add(0, None, 1.0 / p["Rg"])
    add(0, 2, s * p["Cf"])
    add(2, None, 1.0 / p["Ro"] + s * p["Co"])
    add(2, 1, 1.0 / p["R1"])
    add(1, None, 1.0 / p["R2"] + s * p["Ca"])
    if gm_on:
        Y[2][0] += p["gm"]          # gm*v(B) leaves node O
    return Y


def voltage_run(s, p, reverse_vbreak=False):
    """Vbreak FB FBAMP 0 ac 1 (or reversed). Returns (v(fb), v(fbamp))."""
    Y = y_matrix(s, p)
    A = [row + [0j] for row in Y] + [[0j] * 4]
    A[1][3], A[0][3] = -1, +1       # branch current enters A, leaves B
    A[3][1], A[3][0] = 1, -1        # v(A) - v(B) = vz
    x = solve(A, [0, 0, 0, -1.0 if reverse_vbreak else 1.0])
    return x[1], x[0]


def current_run(s, p, reverse_shunt=False, reverse_ammeter=False):
    """Loop intact behind Vmeas FB FBAMP 0, Iinx 0 FBAMP ac 1. Returns
    i(vmeas) as ngspice reports it (n+ -> n- through the source)."""
    Y = y_matrix(s, p)
    A = [row + [0j] for row in Y] + [[0j] * 4]
    A[1][3], A[0][3] = +1, -1       # i_m leaves A, enters B
    A[3][1], A[3][0] = 1, -1        # v(A) - v(B) = 0
    x = solve(A, [-1.0 if reverse_shunt else 1.0, 0, 0, 0])
    return -x[3] if reverse_ammeter else x[3]


def return_ratio(s, p):
    """Bode's return ratio of the gm source: gm nulled, a unit test source
    in its place, loop intact; RR = -(returned v(B))/(test value)."""
    Y = y_matrix(s, p, gm_on=False)
    Yi = [[Y[0][0] + Y[1][1] + Y[0][1] + Y[1][0], Y[0][2] + Y[1][2]],
          [Y[2][0] + Y[2][1], Y[2][2]]]
    x = solve(Yi, [0, -p["gm"]])
    return -x[0]


def two_port(s, p):
    """y-parameters of the cut network at ports A (FB) and B (FBAMP)."""
    Y = y_matrix(s, p)

    def sch(i, j):
        return Y[i][j] - Y[i][2] * Y[2][j] / Y[2][2]
    return sch(1, 1), sch(1, 0), sch(0, 1), sch(0, 0)   # y11, y12, y21, y22


def intact_det(s, p):
    Y = y_matrix(s, p)
    a = Y[0][0] + Y[1][1] + Y[0][1] + Y[1][0]
    return a * Y[2][2] - (Y[0][2] + Y[1][2]) * (Y[2][0] + Y[2][1])


def closed_loop_poles(p, radius=1e7, m=8):
    """Roots of the intact circuit's nodal determinant (a quadratic in s
    here), its coefficients recovered by a DFT on a circle."""
    pts = [radius * cmath.exp(2j * math.pi * k / m) for k in range(m)]
    vals = [intact_det(z, p) for z in pts]
    c = [sum(v * z ** (-n) for v, z in zip(vals, pts)) / m for n in range(m)]
    scaled = [abs(x) * radius ** n for n, x in enumerate(c)]
    assert all(v < 1e-9 * max(scaled) for v in scaled[3:]), "fixture det is not quadratic"
    a, b, cc = c[2], c[1], c[0]
    d = cmath.sqrt(b * b - 4 * a * cc)
    return [(-b + d) / (2 * a), (-b - d) / (2 * a)]


def middlebrook_at(s, p):
    fb, fbamp = voltage_run(s, p)
    tv, ti = lg2.injection_ratios(fb, fbamp, current_run(s, p))
    return lg2.middlebrook(tv, ti), tv, ti


def fmt8(x):
    return f"{x: .8e}"


def write_exports(tmp, p, freqs=FREQS, tag="", digits=fmt8, **kw):
    """Write ctl / 2v / 2i exports for fixture p in the fleet's layout."""
    vkw = {k: v for k, v in kw.items() if k == "reverse_vbreak"}
    ikw = {k: v for k, v in kw.items() if k in ("reverse_shunt", "reverse_ammeter")}
    ctl, v, i = [], [], []
    for f in freqs:
        s = 2j * math.pi * f
        fb, fbamp = voltage_run(s, p, **vkw)
        im = current_run(s, p, **ikw)
        L1 = -fb / fbamp
        ctl.append(f" {f: .8e} {lg2.db(L1): .8e} {f: .8e} {math.degrees(cmath.phase(L1)): .8e} \n")
        v.append(" " + " ".join(digits(x) for x in (f, fb.real, f, fb.imag,
                                                   f, fbamp.real, f, fbamp.imag)) + " \n")
        i.append(" " + " ".join(digits(x) for x in (f, im.real, f, im.imag)) + " \n")
    paths = []
    for lines, name in ((ctl, f"ctl{tag}"), (v, f"v{tag}"), (i, f"i{tag}")):
        path = os.path.join(tmp, f"{name}_ac.csv")
        with open(path, "w") as fh:
            fh.writelines(lines)
        paths.append(path)
    return paths


class Fixture(unittest.TestCase):
    """The method against truths that involve no injection at all."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_loaded_unilateral_loop_gain_equals_bode_return_ratio(self):
        _, v, i = write_exports(self.tmp, UNILATERAL)
        rec = lg2.reconstruct(v, i)
        self.assertGreater(rec["cut"], 100)
        worst_tv, worst_old = 0.0, 0.0
        for k in range(rec["cut"]):
            s = 2j * math.pi * rec["freqs"][k]
            rr = return_ratio(s, UNILATERAL)
            # within the stated rounding bound (x2 for second order)
            self.assertLessEqual(abs(rec["T"][k] - rr), 2 * rec["res"][k] + 1e-12 * abs(rr),
                                 f"T != RR at {rec['freqs'][k]:g} Hz")
            worst_tv = max(worst_tv, abs(rec["tv"][k] - rr) / abs(rr))
            worst_old = max(worst_old, abs(lg2.unloaded_transfer(rec["tv"][k], rec["ti"][k]) - rr)
                            / abs(rr))
        # the loading is finite: the single injection and the previous
        # revision's unloaded -T' both miss the return ratio by > 10 %
        self.assertGreater(worst_tv, 0.1)
        self.assertGreater(worst_old, 0.1)

    def test_bilateral_loop_gain_is_the_two_port_nonreciprocal_ratio(self):
        _, v, i = write_exports(self.tmp, BILATERAL)
        rec = lg2.reconstruct(v, i)
        differs_from_rr = 0.0
        for k in range(rec["cut"]):
            s = 2j * math.pi * rec["freqs"][k]
            y11, y12, y21, y22 = two_port(s, BILATERAL)
            want = (y12 - y21) / (y11 + y22 + 2 * y21)
            self.assertLessEqual(abs(rec["T"][k] - want), 2 * rec["res"][k] + 1e-12 * abs(want))
            rr = return_ratio(s, BILATERAL)
            differs_from_rr = max(differs_from_rr, abs(want - rr) / abs(rr))
        # at a bilateral break T is NOT the return ratio of the gm source
        # (the loop gain is not unique there): documented, not hidden
        self.assertGreater(differs_from_rr, 0.1)

    def test_one_plus_T_vanishes_at_the_closed_loop_poles(self):
        for p in (UNILATERAL, BILATERAL):
            for pole in closed_loop_poles(p):
                self.assertLess(pole.real, 0.0)
                self.assertLess(abs(1 + return_ratio(pole, p)), 1e-9)
                # T = (Tv Ti - 1)/(Tv + Ti + 2) is 0/0 exactly at the pole
                # (Tv = Ti = -1 there); approach it along a ray instead
                near = [abs(1 + middlebrook_at(pole * (1 + e), p)[0]) for e in (1e-4, 1e-6)]
                self.assertLess(near[1], 1e-4)
                self.assertTrue(30 < near[0] / near[1] < 300, near)   # a simple zero
                if p is UNILATERAL:
                    _, tv, ti = middlebrook_at(pole * (1 + 1e-6), p)
                    # the previous revision's unloaded -T' is not a loop gain
                    self.assertGreater(abs(1 + lg2.unloaded_transfer(tv, ti)), 1e-2)

    def test_single_injection_artifact_is_absent_from_the_reconstruction(self):
        # With heavy finite loading the single injection (Tv) of this KNOWN
        # circuit crosses 0 dB a second time; Bode's return ratio does not.
        # The reconstruction must follow the return ratio, not Tv.
        ctl, v, i = write_exports(self.tmp, UNILATERAL)
        cf, ctl_L = lg2.read_loopgain_trace(ctl)
        rr = [return_ratio(2j * math.pi * f, UNILATERAL) for f in FREQS]
        self.assertEqual(len(lg2.zero_db_crossings(cf, ctl_L)), 2)
        self.assertEqual(len(lg2.zero_db_crossings(FREQS, rr)), 1)
        rec = lg2.reconstruct(v, i)
        self.assertEqual(len(lg2.zero_db_crossings(rec["freqs"][:rec["cut"]], rec["T"][:rec["cut"]])), 1)

    def test_resolution_bound_covers_the_export_rounding(self):
        _, v8, i8 = write_exports(self.tmp, BILATERAL, tag="8")
        _, v17, i17 = write_exports(self.tmp, BILATERAL, tag="17", digits=lambda x: f"{x:.17g}")
        r8, r17 = lg2.reconstruct(v8, i8), lg2.reconstruct(v17, i17)
        for k in range(len(FREQS)):
            if r8["res"][k] < abs(r8["T"][k]) / 2:      # where first order is valid
                self.assertLessEqual(abs(r8["T"][k] - r17["T"][k]), 2 * r8["res"][k])

    def test_written_trace_is_the_resolved_prefix_and_never_clamped(self):
        # a big output capacitor makes T vanish into the rounding at HF
        p = dict(UNILATERAL, Co=1e-6)
        corners = os.path.join(self.tmp, "corners")
        os.makedirs(corners)
        ctl, v, i = write_exports(corners, p)
        for src, dst in ((ctl, "loopgain_ctl_tt_27c_rtyp_ac.csv"),
                         (v, "loopgain2v_tt_27c_rtyp_ac.csv"),
                         (i, "loopgain2i_tt_27c_rtyp_ac.csv")):
            os.rename(src, os.path.join(corners, dst))
        rec = lg2.reconstruct(os.path.join(corners, "loopgain2v_tt_27c_rtyp_ac.csv"),
                              os.path.join(corners, "loopgain2i_tt_27c_rtyp_ac.csv"))
        self.assertLess(rec["cut"], len(FREQS))
        row = lg2.point_row(corners, "tt_27c_rtyp", "1e10")
        with open(os.path.join(corners, "loopgain2_tt_27c_rtyp_ac.csv")) as fh:
            lines = [ln.split() for ln in fh if ln.strip()]
        self.assertEqual(len(lines), rec["cut"])
        for k, ln in enumerate(lines):
            self.assertGreaterEqual(abs(rec["T"][k]), lg2.RESOLVED_FACTOR * rec["res"][k])
            self.assertGreater(float(ln[1]), -250.0)
        self.assertTrue(math.isclose(row["lg2_first_unresolved_hz"], FREQS[rec["cut"]], rel_tol=1e-8))
        self.assertTrue(math.isclose(row["lg2_resolved_to_hz"], FREQS[rec["cut"] - 1], rel_tol=1e-8))
        self.assertIsNotNone(row["lg2_bound_db_above_cut"])
        for key in lg2.CSV_FIELDS:
            self.assertIn(key, row)


class Polarity(unittest.TestCase):
    """Deliberately reversed probes (the issue's negative controls)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_reversed_shunt_source_is_detected(self):
        _, v, i = write_exports(self.tmp, BILATERAL, reverse_shunt=True)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "orientation check failed"):
            lg2.reconstruct(v, i)

    def test_reversed_ammeter_is_detected(self):
        _, v, i = write_exports(self.tmp, BILATERAL, reverse_ammeter=True)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "orientation check failed"):
            lg2.reconstruct(v, i)

    def test_reversed_vbreak_is_harmless(self):
        # Tv is a ratio of two responses to the SAME source: its polarity
        # cancels. Stated, and pinned so a future formula cannot depend on it.
        _, v, i = write_exports(self.tmp, BILATERAL)
        _, v2, i2 = write_exports(self.tmp, BILATERAL, tag="r", reverse_vbreak=True)
        a, b = lg2.reconstruct(v, i), lg2.reconstruct(v2, i2)
        for x, y in zip(a["T"][:a["cut"]], b["T"][:a["cut"]]):
            self.assertLessEqual(abs(x - y), 1e-7 * abs(x))

    def test_swapped_voltage_probes_fail_the_deck_identity_check(self):
        ctl, v, i = write_exports(self.tmp, LIGHT)
        rows = open(v).read().splitlines()
        swapped = []
        for ln in rows:                     # v(fb) <-> v(fbamp) columns
            p = ln.split()
            swapped.append(" " + " ".join([p[0], p[5], p[2], p[7], p[4], p[1], p[6], p[3]]) + " \n")
        v_bad = os.path.join(self.tmp, "v_swapped_ac.csv")
        with open(v_bad, "w") as fh:
            fh.writelines(swapped)
        rec = lg2.reconstruct(v_bad, i)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "deck identity failed"):
            lg2.validate_against_control(rec, ctl)


class Validate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_healthy_fixture_passes_all_stated_tolerances(self):
        for p in (LIGHT,):
            ctl, v, i = write_exports(self.tmp, p)
            x = lg2.validate_against_control(lg2.reconstruct(v, i), ctl)
            self.assertLess(x["v2ctl_max_rel_diff"], lg2.TOL_DECK_IDENTITY)
            self.assertLess(x["lf_agree_max_rel"], lg2.TOL_LF_AGREE)

    def test_leaky_input_fails_the_low_frequency_agreement(self):
        # a resistive input (not a high-Z gate) makes Ti comparable to Tv at
        # low frequency: the current-injection deck must flag it
        ctl, v, i = write_exports(self.tmp, dict(UNILATERAL, Rg=3e5))
        with self.assertRaisesRegex(lg2.Loopgain2Error, "low-frequency agreement failed"):
            lg2.validate_against_control(lg2.reconstruct(v, i), ctl)

    def test_control_without_a_crossing_raises(self):
        _, v, i = write_exports(self.tmp, UNILATERAL)
        flat = os.path.join(self.tmp, "flat_ac.csv")
        with open(flat, "w") as fh:
            for f in FREQS:
                fh.write(f" {f:.8e} {20.0:.8e} {f:.8e} {0.0:.8e} \n")
        with self.assertRaisesRegex(lg2.Loopgain2Error, "no 0 dB crossing"):
            lg2.validate_against_control(lg2.reconstruct(v, i), flat)

    def test_frequency_axis_mismatches_raise(self):
        ctl, v, i = write_exports(self.tmp, UNILATERAL)
        _, v2, i2 = write_exports(self.tmp, UNILATERAL, freqs=[f * 1.001 for f in FREQS], tag="2")
        _, _, i3 = write_exports(self.tmp, UNILATERAL, freqs=FREQS[:121], tag="3")
        rec = lg2.reconstruct(v, i)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "frequency grids differ"):
            lg2.reconstruct(v, i2)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "grids differ in length"):
            lg2.reconstruct(v, i3)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "frequency axis differs"):
            lg2.validate_against_control(rec, os.path.join(self.tmp, "ctl2_ac.csv"))

    def test_degenerate_and_nonfinite_inputs_raise(self):
        with self.assertRaisesRegex(lg2.Loopgain2Error, "exactly -1"):
            lg2.injection_ratios(1 + 0j, -1 + 0j, -1 + 0j)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "exactly 0"):
            lg2.injection_ratios(1 + 0j, -1 + 0j, 0j)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "zero probe voltage"):
            lg2.injection_ratios(0j, -1 + 0j, 0.5 + 0j)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "nonfinite"):
            lg2.injection_ratios(complex("nan"), -1 + 0j, 0.5 + 0j)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "exactly 0"):
            lg2.middlebrook(-1 + 0j, -1 + 0j)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "nonfinite"):
            lg2.middlebrook(float("inf"), 1j)


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_trace_round_trip(self):
        L = [return_ratio(2j * math.pi * f, UNILATERAL) for f in FREQS[:120]]
        p = os.path.join(self.tmp, "rt_ac.csv")
        lg2.write_loopgain_trace(p, FREQS[:120], L)
        _, L2 = lg2.read_loopgain_trace(p)
        for a, b in zip(L, L2):
            self.assertAlmostEqual(abs(a), abs(b), delta=1e-8 * abs(a))
            self.assertAlmostEqual(cmath.phase(a), cmath.phase(b), delta=1e-8)

    def test_check_export_screening(self):
        _, v, i = write_exports(self.tmp, UNILATERAL)
        self.assertEqual(lg2.check_export(v, 8, "1e10"), [])
        self.assertEqual(lg2.check_export(i, 4, "1e10"), [])
        self.assertTrue(any("columns" in b for b in lg2.check_export(i, 8, "1e10")))
        short = os.path.join(self.tmp, "short_ac.csv")
        with open(short, "w") as fh:
            fh.write("\n".join(open(v).read().splitlines()[:-1]) + "\n")
        self.assertTrue(any("rows, expected" in b for b in lg2.check_export(short, 8, "1e10")))

    def test_corrupt_frequency_column_raises(self):
        _, v, _ = write_exports(self.tmp, UNILATERAL, freqs=[1.0, 10.0, 100.0])
        rows = open(v).read().splitlines()
        p = rows[0].split()
        p[4] = "9.9e-01"                                # a scale column drifts
        with open(v, "w") as fh:
            fh.write("\n".join([" ".join(p)] + rows[1:]) + "\n")
        with self.assertRaisesRegex(lg2.Loopgain2Error, "frequency column"):
            lg2.read_voltage_export(v)

    def test_parse_suffix(self):
        self.assertEqual(lg2.parse_suffix("tt_27c_rtyp"), ("tt", "27", "res_typ"))
        self.assertEqual(lg2.parse_suffix("ss_-40c_rwcs"), ("ss", "-40", "res_wcs"))
        self.assertEqual(lg2.parse_suffix("ff_125c_rbcs"), ("ff", "125", "res_bcs"))


class Overlay(unittest.TestCase):
    """row10_loopgain2's resolution overlay only ever makes verdicts more
    conservative and fails closed without the resolution columns."""

    def _m(self, pm, gm):
        return {"valid": True, "pm": {"verdict": pm, "reasons": []},
                "gm": {"verdict": gm, "reasons": [], "above_ceiling_lower_bound_db": 20.0},
                "nyquist": {"class": "stable", "in_band_net_crossings": 0}}

    def test_overlay(self):
        import row10_loopgain2 as w
        m = w._overlay(self._m("pass", "fail"), {"first_unresolved_hz": 7e7})
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertIn(w.UNRESOLVED_REASON, m["pm"]["reasons"])
        self.assertEqual(m["gm"]["verdict"], "fail")
        self.assertIsNone(m["gm"]["above_ceiling_lower_bound_db"])
        self.assertEqual(m["nyquist"]["class"], "undetermined")
        m = w._overlay(self._m("pass", "pass"), {"first_unresolved_hz": None})
        self.assertEqual((m["pm"]["verdict"], m["gm"]["verdict"]), ("pass", "pass"))

    def test_old_schema_csv_fails_closed(self):
        import row10_loopgain2 as w
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "old.csv")
            with open(p, "w", newline="") as fh:
                wr = csv.writer(fh)
                wr.writerow(["corner", "temp_c", "res_section"])
                wr.writerow(["tt", "27", "res_typ"])
            w._current_record[0] = "x"
            with self.assertRaises(w.rm.Row10Error):
                w._resolution_info(p)
        finally:
            shutil.rmtree(tmp)


class OperatingPoint(unittest.TestCase):
    """issue #218: the campaign's --load-ma/--cout-uf/--esr-ohm arguments,
    canonicalised and validated through dynamic_doe -- the #64 DoE's own
    validator, never a second one -- and the default-path deck literals,
    which must stay byte-identical to the pre-#218 driver's."""

    def test_no_arguments_is_the_legacy_point(self):
        op = lg2.op_from_args()
        self.assertEqual(op, {"load_ua": 1000, "cout_nf": 1000, "esr_mohm": 0})
        self.assertEqual(lg2.op_display(op), "1 mA, 1 uF, 0 ohm")

    def test_default_deck_literals_are_the_pre_218_bytes(self):
        # AC 1's byte-identity contract: the no-arguments run substitutes
        # exactly these literals (the driver sources them from
        # DEFAULT_DECK_LITERALS, so this pins the shared copy).
        self.assertEqual(lg2.DEFAULT_DECK_LITERALS, {
            "LOAD_A": "0.001", "COUT_F": "1u", "COUT_BOTTOM": "0",
            "ESR_LINE": "* ESR=0: Cout wired directly to ground (campaign default)"})

    def test_p3_operating_point_uses_doe_canonical_netlist_syntax(self):
        import dynamic_doe as dyn
        op = lg2.op_from_args(load_ma=50, cout_uf=0.33, esr_ohm=0)
        self.assertEqual(op, {"load_ua": 50000, "cout_nf": 330, "esr_mohm": 0})
        # the same strings run_ccprobe.sh substituted for its P3 decks
        self.assertEqual(dyn.netlist_values(op),
                         {"load_a": "50000e-6", "cout_f": "330n", "esr_ohm": "0"})
        self.assertEqual(lg2.op_display(op), "50 mA, 0.33 uF, 0 ohm")

    def test_nonzero_esr_wires_the_series_resistor(self):
        self.assertEqual(lg2.esr_netlist_parts("0"),
                         ("0", "* ESR=0: Cout wired directly to ground, no series resistor"))
        self.assertEqual(lg2.esr_netlist_parts("500e-3"),
                         ("COUT_ESR", "Resr COUT_ESR 0 500e-3"))

    def test_rejected_bad_values(self):
        import dynamic_doe as dyn
        for kw in (dict(cout_uf=0),                     # zero Cout
                   dict(load_ma=-1), dict(esr_ohm=-0.001),   # negative
                   dict(load_ma="fifty"), dict(cout_uf="1u"),  # non-numeric
                   dict(cout_uf=0.3333),                 # not an exact nF multiple
                   dict(esr_ohm=0.00025)):               # not an exact mohm multiple
            with self.assertRaises(dyn.InvalidOperatingPoint, msg=repr(kw)):
                lg2.op_from_args(**kw)

    def test_op_subcommand_exit_codes(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc_bad = lg2.main(["op", "--cout-uf=0"])
            rc_ok = lg2.main(["op", "--load-ma=50", "--cout-uf=0.33", "--esr-ohm=0", "--json"])
        self.assertEqual(rc_bad, 2)
        self.assertEqual(rc_ok, 0)

    def test_arguments_reach_the_rendered_deck(self):
        # Negative control for the driver's substitution wiring (mirrors
        # #219's AC 6 discipline): render the real single-injection template
        # the way run_loopgain2.sh's render_deck does, once with the default
        # literals and once with P3's canonical values, and assert each
        # deck carries ITS operating point -- a silently ignored flag (or a
        # mapping still hardcoding the legacy literals) fails here.
        import render_deck
        tmpl = os.path.join(HERE, "testbench", "tb_loopgain_cmos5l.spice.tmpl")
        base = {"PDK_ROOT": "/pdk", "PDK": "p", "OSDI_DIR": "/osdi",
                "MOS_SECTION": "mos_ff", "RES_SECTION": "res_wcs", "CAP_SECTION": "cap_typ",
                "TEMP": "-40", "LG_AC_MAX": "1e10", "CC_W": "170u (nominal)",
                "DESIGN_NETLIST": "/design.spice", "AC_CSV": "/out.csv"}
        default = render_deck.render(open(tmpl).read(), dict(
            base, **lg2.DEFAULT_DECK_LITERALS))
        self.assertIn("Iload VOUT 0 dc 0.001", default)
        self.assertIn("Cout VOUT 0 1u", default)
        self.assertIn("* ESR=0: Cout wired directly to ground (campaign default)", default)
        p3 = render_deck.render(open(tmpl).read(), dict(
            base, LOAD_A="50000e-6", COUT_F="330n", COUT_BOTTOM="0",
            ESR_LINE=lg2.esr_netlist_parts("0")[1]))
        self.assertIn("Iload VOUT 0 dc 50000e-6", p3)
        self.assertIn("Cout VOUT 0 330n", p3)
        self.assertNotIn("dc 0.001", p3)
        self.assertNotIn("Cout VOUT 0 1u", p3)
        self.assertNotIn("(campaign default)", p3)

    def test_two_injection_templates_carry_no_stale_operating_point(self):
        # #355: the two-injection templates used to claim "this campaign runs
        # the legacy 1mA / 1uF / 0 ohm point" above Iload/Cout cards that an
        # override run (#218) sets to something else. Render both at P3's
        # point and assert the deck carries its own values and no contradiction.
        import render_deck
        base = {"PDK_ROOT": "/pdk", "PDK": "p", "OSDI_DIR": "/osdi",
                "MOS_SECTION": "mos_ff", "RES_SECTION": "res_wcs", "CAP_SECTION": "cap_typ",
                "TEMP": "-40", "LG_AC_MAX": "1e10", "CC_W": "170u (nominal)",
                "DESIGN_NETLIST": "/design.spice", "AC_CSV": "/out.csv"}
        esr_line = lg2.esr_netlist_parts("0")[1]
        for bench in ("tb_loopgain2v_cmos5l", "tb_loopgain2i_cmos5l"):
            with self.subTest(bench=bench):
                tmpl = os.path.join(HERE, "testbench", bench + ".spice.tmpl")
                text = open(tmpl).read()
                self.assertNotIn("this campaign runs the legacy", text)
                deck = render_deck.render(text, dict(
                    base, LOAD_A="50000e-6", COUT_F="330n", COUT_BOTTOM="0",
                    ESR_LINE=esr_line))
                self.assertIn("Iload VOUT 0 dc 50000e-6", deck)
                self.assertIn("Cout VOUT 0 330n", deck)
                self.assertNotIn("this campaign runs the legacy", deck)


class CampaignFacts(unittest.TestCase):
    """issue #218: the campaign's shape (operating point, point count,
    conditions) is read from evidence/<rid>/campaign.json, with defaults
    that keep the pre-#218 records' committed strings byte-exact."""

    def test_legacy_defaults_reproduce_the_committed_strings(self):
        facts, present = lg2.campaign_facts("20261012-071449-6a3c1475")
        self.assertFalse(present)          # committed record, no campaign.json
        self.assertEqual(facts["issue"], "issue #135")
        self.assertTrue(facts["revision_note"])
        self.assertEqual(facts["grid"], "5 MOS corners x 3 temperatures x 3 resistor corners")
        self.assertEqual(facts["op_display"], "1 mA, 1 uF, 0 ohm")
        self.assertEqual(facts["points"], 45)
        self.assertTrue(facts["legacy_point"] and facts["full_grid"])
        self.assertIsNone(facts["only_point"])
        self.assertIsNone(facts["e2"])

    def test_legacy_producer_pins_match_the_committed_records(self):
        # The append-only records' md/evidence pin the bytes that PRODUCED
        # them; the defaults must quote exactly those, or a later edit to
        # loopgain2.py/row10_loopgain2.py would break their byte-compare.
        import row10_loopgain2 as w
        for rid in ("20261011-165616-eabde108", "20261012-071449-6a3c1475"):
            facts, _ = lg2.campaign_facts(rid)
            md = open(os.path.join(HERE, "records", f"{rid}.loopgain2.md")).read()
            self.assertIn(f"`loopgain2.py` {facts['producer_sha16']},", md)
            self.assertIn(f"`tb_loopgain2v_cmos5l.spice.tmpl` {facts['tmpl2v_sha16']},", md)
            self.assertIn(f"`tb_loopgain2i_cmos5l.spice.tmpl` {facts['tmpl2i_sha16']}.", md)
            doc = json.load(open(os.path.join(HERE, "evidence", rid, "row10-margins.json")))
            self.assertEqual(doc["classifier"][w.SELF], facts["row10_wrapper_sha256"])
            self.assertEqual(doc["classifier"][f"sim/ldo-cmos5l-pvt-sweep/loopgain2.py"],
                             facts["loopgain2_sha256"])

    def test_campaign_json_overrides_the_defaults(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "evidence", "rid9"))
            with open(os.path.join(tmp, "evidence", "rid9", "campaign.json"), "w") as fh:
                json.dump({"points": 1, "full_grid": False, "only_point": "ff_-40c_rwcs",
                           "op": {"load_ua": 50000, "cout_nf": 330, "esr_mohm": 0},
                           "op_display": "50 mA, 0.33 uF, 0 ohm", "e2": {"p6_record": "r"}}, fh)
            facts, present = lg2.campaign_facts("rid9", sim_dir=tmp)
            self.assertTrue(present)
            self.assertEqual(facts["points"], 1)
            self.assertFalse(facts["full_grid"])
            self.assertEqual(facts["only_point"], "ff_-40c_rwcs")
            self.assertEqual(facts["e2"]["p6_record"], "r")
            self.assertEqual(facts["issue"], "issue #135")   # untouched key keeps default
        finally:
            shutil.rmtree(tmp)

    def test_row10_conditions_and_expected_rows_follow_the_campaign(self):
        import row10_loopgain2 as w
        self.assertEqual(w.conditions_for("20261012-071449-6a3c1475"), w._LEGACY_CONDITIONS)
        self.assertIn("45-point PVT grid", w._LEGACY_CONDITIONS)
        self.assertEqual(w.expected_points_for("20261012-071449-6a3c1475"), 45)
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "evidence", "rid9"))
            with open(os.path.join(tmp, "evidence", "rid9", "campaign.json"), "w") as fh:
                json.dump({"points": 1, "full_grid": False, "only_point": "ff_-40c_rwcs",
                           "op": {"load_ua": 50000, "cout_nf": 330, "esr_mohm": 0}}, fh)
            self.assertEqual(w.expected_points_for("rid9", sim_dir=tmp), 1)
            self.assertIn("single PVT point ff_-40c_rwcs", w.conditions_for("rid9", sim_dir=tmp))
            self.assertIn("50 mA, Cout 0.33 uF, ESR 0", w.conditions_for("rid9", sim_dir=tmp))
        finally:
            shutil.rmtree(tmp)


class InvalidPointCapture(unittest.TestCase):
    """issue #218: a point that fails TOL_LF_AGREE still reports its measured
    numbers, the verbatim error and a quantitative cause analysis, with
    valid=False -- a record must state what was measured and why it is
    uncertified, not silently drop the point. The comparison CSV keeps the
    legacy schema exactly (no new columns)."""

    def test_lf_failure_is_recorded_not_dropped(self):
        import argparse
        tmp = tempfile.mkdtemp()
        try:
            ctl, v, i = write_exports(tmp, dict(UNILATERAL, Rg=3e5))
            d = os.path.join(tmp, "corners")
            os.makedirs(d)
            for src, name in ((ctl, "loopgain_ctl_tt_27c_rtyp_ac.csv"),
                              (v, "loopgain2v_tt_27c_rtyp_ac.csv"),
                              (i, "loopgain2i_tt_27c_rtyp_ac.csv")):
                shutil.copy(src, os.path.join(d, name))
            out_csv, out_json = os.path.join(tmp, "cmp.csv"), os.path.join(tmp, "cmp.json")
            combined = os.path.join(tmp, "combined")
            os.makedirs(combined)
            rc = lg2.cmd_report(argparse.Namespace(corners_dir=d, ceiling="1e10",
                                                   out_csv=out_csv, out_json=out_json),
                                out_dir=combined)
            self.assertEqual(rc, 1)
            doc = json.load(open(out_json))
            row = doc["rows"][0]
            self.assertFalse(row["valid"])
            self.assertIn("low-frequency agreement", row["lg2_validation_error"])
            self.assertIsNotNone(row["lg2_phase_margin_deg"])
            self.assertIsNotNone(row["ctl_phase_margin_deg"])
            analysis = row["lf_agreement_analysis"]
            self.assertIsNotNone(analysis)
            self.assertGreater(analysis["worst_rel"], lg2.TOL_LF_AGREE)
            self.assertLess(analysis["deck_identity_residual_below_band"],
                            lg2.TOL_DECK_IDENTITY)
            self.assertIn("analytic", analysis["conclusion"])
            with open(out_csv) as fh:
                self.assertEqual(fh.readline().strip().split(","), lg2.CSV_FIELDS)
        finally:
            shutil.rmtree(tmp)


class CheckGate(unittest.TestCase):
    """The CI `check` must keep failing on an invalid reconstruction. Only a
    point the record's own campaign.json declares an uncertified diagnostic
    (E2's P3, issue #218) may be invalid; anything else is a check failure."""

    def _record(self, tmp, campaign=None):
        ctl, v, i = write_exports(tmp, dict(UNILATERAL, Rg=3e5))   # fails TOL_LF_AGREE
        d = os.path.join(tmp, "corners", "ridX")
        os.makedirs(d)
        for src, name in ((ctl, "loopgain_ctl_tt_27c_rtyp_ac.csv"),
                          (v, "loopgain2v_tt_27c_rtyp_ac.csv"),
                          (i, "loopgain2i_tt_27c_rtyp_ac.csv")):
            shutil.copy(src, os.path.join(d, name))
        if campaign is not None:
            os.makedirs(os.path.join(tmp, "evidence", "ridX"))
            with open(os.path.join(tmp, "evidence", "ridX", "campaign.json"), "w") as fh:
                json.dump(campaign, fh)
        return d

    def _check(self, d):
        import argparse
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = lg2.cmd_check(argparse.Namespace(corners_dir=d, ceiling="1e10"))
        return rc, err.getvalue()

    GATE = "does not validate and is not a declared uncertified diagnostic"

    def test_invalid_point_in_an_ordinary_record_fails_check(self):
        tmp = tempfile.mkdtemp()
        try:
            rc, err = self._check(self._record(tmp))
            self.assertEqual(rc, 1)
            self.assertIn(self.GATE, err)
            self.assertIn("tt_27c_rtyp", err)
        finally:
            shutil.rmtree(tmp)

    def test_a_different_invalid_point_in_an_e2_record_still_fails(self):
        tmp = tempfile.mkdtemp()
        try:
            rc, err = self._check(self._record(tmp, {"e2": {"p3_point": "ff_-40c_rwcs"}}))
            self.assertEqual(rc, 1)
            self.assertIn(self.GATE, err)
        finally:
            shutil.rmtree(tmp)

    def test_declared_diagnostic_point_passes_the_validity_gate(self):
        tmp = tempfile.mkdtemp()
        try:
            rc, err = self._check(self._record(tmp, {"e2": {"p3_point": "tt_27c_rtyp"}}))
            self.assertNotIn(self.GATE, err)   # (reproduction still gates the rest)
        finally:
            shutil.rmtree(tmp)


class InformationalDeltas(unittest.TestCase):
    def test_missing_crossings_give_none_not_a_crash(self):
        m1 = {"phase_margin_deg": 10.0, "gain_margin_db": None, "unity_gain_freq_hz": None}
        m2 = {"phase_margin_deg": 4.0, "gain_margin_db": None, "unity_gain_freq_hz": None}
        self.assertEqual(lg2.metric_delta(m1, m2, "phase_margin_deg"), 6.0)
        self.assertIsNone(lg2.metric_delta(m1, m2, "gain_margin_db"))
        self.assertIsNone(lg2.metric_rel_delta(m1, m2, "unity_gain_freq_hz"))
        self.assertIsNone(lg2.metric_delta(None, m2, "phase_margin_deg"))


class ShortControl(unittest.TestCase):
    def test_short_control_keeps_the_validation_error_not_an_indexerror(self):
        tmp = tempfile.mkdtemp()
        try:
            ctl, v, i = write_exports(tmp, UNILATERAL)
            d = os.path.join(tmp, "corners")
            os.makedirs(d)
            with open(ctl) as fh:
                head = fh.readlines()[:100]
            with open(os.path.join(d, "loopgain_ctl_tt_27c_rtyp_ac.csv"), "w") as fh:
                fh.writelines(head)
            shutil.copy(v, os.path.join(d, "loopgain2v_tt_27c_rtyp_ac.csv"))
            shutil.copy(i, os.path.join(d, "loopgain2i_tt_27c_rtyp_ac.csv"))
            row = lg2.point_row(d, "tt_27c_rtyp", "1e10")
            self.assertFalse(row["valid"])
            self.assertIn("control trace has 100 rows", row["lg2_validation_error"])
            self.assertIsNone(row["ctl_db_at_lg2_resolved_to"])
        finally:
            shutil.rmtree(tmp)


class EsrDeck(unittest.TestCase):
    def test_cli_esr_reaches_a_wellformed_resistor_element(self):
        import json as _json
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(HERE, "loopgain2.py"), "op", "--json",
                              "--load-ma=50", "--cout-uf=0.33", "--esr-ohm=0.5"],
                             capture_output=True, text=True, check=True).stdout
        esr = _json.loads(out)["esr"]
        self.assertEqual(esr["cout_bottom"], "COUT_ESR")
        # element line: name, node, node, value -- not a stray first token
        # that makes SPICE instantiate a capacitor named COUT_ESR
        self.assertEqual(esr["esr_line"].split(), ["Resr", "COUT_ESR", "0", "500e-3"])
        self.assertTrue(esr["esr_line"].startswith("Resr "))

    def test_row10_conditions_spell_out_the_esr_unit(self):
        import row10_loopgain2 as w
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "evidence", "rid9"))
            with open(os.path.join(tmp, "evidence", "rid9", "campaign.json"), "w") as fh:
                json.dump({"points": 1, "full_grid": False, "only_point": "ff_-40c_rwcs",
                           "op": {"load_ua": 50000, "cout_nf": 330, "esr_mohm": 500}}, fh)
            self.assertIn("ESR 0.5 ohm", w.conditions_for("rid9", sim_dir=tmp))
        finally:
            shutil.rmtree(tmp)


class BaselineComparisonBlock(unittest.TestCase):
    """run_loopgain2.sh's single-point ctl-vs-baseline heredoc, run for real
    against the committed record (#362: it once called the deleted
    loopgain2._sha16 and aborted after the batch run, before writing
    ctl-vs-baseline.json)."""
    RID = "20261124-002001-3a6eccf3"

    def test_single_point_comparison_reproduces_committed_json(self):
        import subprocess
        with open(os.path.join(HERE, "run_loopgain2.sh"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        start = next(i for i, l in enumerate(lines) if "trace_sha256_16" in l)
        while "<<'PYEOF'" not in lines[start]:
            start -= 1
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "PYEOF")
        body = "\n".join(lines[start + 1:end]) + "\n"
        tmp = tempfile.mkdtemp()
        try:
            out = os.path.join(tmp, "cmp.json")
            subprocess.run(
                [sys.executable, "-", HERE, os.path.join(HERE, "corners", self.RID), out,
                 "50 mA, 0.33 uF, 0 ohm, --only-point=ff_-40c_rwcs",
                 '{"op":{"load_ua":50000,"cout_nf":330,"esr_mohm":0}}'],
                input=body, text=True, check=True, capture_output=True)
            with open(out, encoding="utf-8") as fh, open(os.path.join(
                    HERE, "evidence", self.RID, "ctl-vs-baseline.json"), encoding="utf-8") as ref:
                self.assertEqual(fh.read(), ref.read())
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
