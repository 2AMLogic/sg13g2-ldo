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
import math
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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


if __name__ == "__main__":
    unittest.main()
