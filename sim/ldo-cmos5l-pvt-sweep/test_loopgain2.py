"""Analytic-fixture tests for the two-injection (Middlebrook) reconstruction
(issue #135). stdlib only; no simulator, no PDK, nothing submitted.

The fixture synthesizes the raw probe exports of both two-injection benches
from a KNOWN loop model -- per frequency, a true loop transfer T and a
loading ratio u = Zt/Zl -- using exactly the circuit equations the bench
templates realize (derived in loopgain2.py's module docstring and
sim/ldo-cmos5l-pvt-sweep/README.md):

  Voltage run (Vbreak FB FBAMP 0 ac 1, so v(fb) - v(fbamp) = 1):
      v(fbamp) = 1/(T - u - 1),   v(fb) = (T - u)/(T - u - 1)
  Current run (loop intact, Iinx 0 FBAMP dc 0 ac 1, ix = 1 A into FBAMP;
  i(vmeas) is the bridge current, positive FB -> FBAMP):
      i(vmeas) = (T - 1)/(1 + u - T)
  Single-injection control (what tb_loopgain_cmos5l reads):
      L_single = u - T   (so L_single - L_two = u exactly)

The tests then require loopgain2.reconstruct() to recover -T (this repo's
L convention) and loading_ratio() to recover u, for finite loading, for
vanishing loading, and they require the deliberate error cases (reversed
injection polarity, swapped voltage probes, conditioning-floor degeneracy,
corrupt exports, tolerance violations) to fail loudly instead of producing
a plausible-looking trace.

    python3 -m unittest sim/ldo-cmos5l-pvt-sweep/test_loopgain2.py -v
"""
import cmath
import math
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loopgain2 as lg2  # noqa: E402


# --------------------------------------------------------------------------- #
# the analytic model
# --------------------------------------------------------------------------- #

def synth_triple(freqs, Ts, us):
    """Per-frequency truth (T, u) -> raw wrdata rows for (ctl, 2v, 2i)."""
    ctl, v, i = [], [], []
    for f, T, u in zip(freqs, Ts, us):
        fx = 1.0 / (T - u - 1.0)            # v(fbamp); v(fb)-v(fbamp) = 1
        fy = (T - u) * fx                   # v(fb)
        L_single = u - T                    # the single-injection reading
        im = (T - 1.0) / (1.0 + u - T)      # i(vmeas), FB->FBAMP, ix = 1 A
        ctl.append(" {: .8e} {: .8e} {: .8e} {: .8e} \n".format(
            f, lg2.db(L_single), f,
            math.degrees(cmath.phase(L_single))))
        v.append(" {: .8e} {: .8e} {: .8e} {: .8e} {: .8e} {: .8e} {: .8e} {: .8e} \n".format(
            f, fy.real, f, fy.imag, f, fx.real, f, fx.imag))
        i.append(" {: .8e} {: .8e} {: .8e} {: .8e} \n".format(
            f, im.real, f, im.imag))
    return ctl, v, i


def write_files(tmp, freqs, Ts, us, tag=""):
    ctl, v, i = synth_triple(freqs, Ts, us)
    for lines, name in ((ctl, f"ctl{tag}"), (v, f"v{tag}"), (i, f"i{tag}")):
        with open(os.path.join(tmp, f"{name}_ac.csv"), "w") as fh:
            fh.writelines(lines)
    return (os.path.join(tmp, f"ctl{tag}_ac.csv"),
            os.path.join(tmp, f"v{tag}_ac.csv"),
            os.path.join(tmp, f"i{tag}_ac.csv"))


def known_loop(freqs, dc_gain=-50.0, ugf=1e6, u_at_1hz=1e-6, u_per_decade=0.55):
    """A one-pole negative-feedback loop (T = dc/(1 + j f/ugf), T<0) with a
    loading ratio that grows half a decade per decade, like a capacitive
    gate against a resistive divider. Returns (Ts, us)."""
    Ts, us = [], []
    for f in freqs:
        Ts.append(-abs(dc_gain) / (1.0 + 1j * f / ugf))
        us.append(u_at_1hz * (10.0 ** (u_per_decade * math.log10(f))))
    return Ts, us


FREQS = [10.0 ** (k / 20.0) for k in range(0, 201)]   # 1 Hz .. 1e10, 20 pts/dec


def close_complex(a, b, rel=1e-8):
    return math.isclose(abs(a - b), 0.0, rel_tol=rel, abs_tol=rel * max(1.0, abs(b)))


class Reconstruction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_recovers_known_loop_with_finite_loading(self):
        Ts, us = known_loop(FREQS)
        ctl, v, i = write_files(self.tmp, FREQS, Ts, us)
        freqs, L, hv, hi, us_rec, diag = lg2.reconstruct(v, i)
        self.assertEqual(len(freqs), len(FREQS))
        for a, b in zip(freqs, FREQS):
            self.assertTrue(math.isclose(a, b, rel_tol=1e-8), f"{a} vs {b}")
        for k, (got, want) in enumerate(zip(L, Ts)):
            self.assertAlmostEqual(got.real, -want.real, delta=1e-7 * max(1.0, abs(want.real)),
                                   msg=f"Re at {freqs[k]:g} Hz")
            self.assertAlmostEqual(got.imag, -want.imag, delta=1e-7 * max(1.0, abs(want.imag)),
                                   msg=f"Im at {freqs[k]:g} Hz")
        for k, (got, want) in enumerate(zip(us_rec, us)):
            # u is resolved through 1 + i(vmeas) ~ u/(1+u-T): nine written
            # digits bound the tiny-u end to a few percent (the 1 Hz value
            # still clears TOL_U_LF by orders of magnitude).
            self.assertAlmostEqual(got.real, want.real, delta=5e-2 * abs(want.real) + 1e-9,
                                   msg=f"u Re at {freqs[k]:g} Hz")
            self.assertAlmostEqual(got.imag, want.imag, delta=5e-2 * abs(want.imag) + 1e-7,
                                   msg=f"u Im at {freqs[k]:g} Hz")
        # the single-injection control differs from the truth by exactly u
        # (to the traces' written precision; at 1 Hz u itself is ~1e-6)
        cf, ctl_L = lg2.read_loopgain_trace(ctl)
        for k in (0, 30, 60, 100):
            self.assertAlmostEqual(abs(ctl_L[k] - L[k]), abs(us[k]),
                                   delta=2e-6 + 5e-2 * abs(us[k]),
                                   msg=f"|L1-L2| == u at {cf[k]:g} Hz")

    def test_vanishing_loading_reduces_to_single_injection(self):
        # u ~ 1e-9: Hi is huge, the combination collapses onto 1/Hv and the
        # reconstruction must agree with the single-injection reading.
        Ts, _ = known_loop(FREQS)
        us = [1e-9 * (1 + 0j)] * len(FREQS)
        ctl, v, i = write_files(self.tmp, FREQS, Ts, us)
        _, L, _, _, _, _ = lg2.reconstruct(v, i)
        _, ctl_L = lg2.read_loopgain_trace(ctl)
        for k in (0, 50, 100):
            self.assertAlmostEqual(abs(L[k] - ctl_L[k]) / abs(ctl_L[k]), 0.0, delta=1e-6)

    def test_exactly_degenerate_current_exports_raise(self):
        Ts, us = known_loop([1.0, 10.0], dc_gain=-10.0)
        us = [0j, 0j]                       # u = 0 -> i(vmeas) == -1 exactly
        _, v, i = write_files(self.tmp, [1.0, 10.0], Ts, us)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "exactly -1"):
            lg2.reconstruct(v, i)
        with open(i, "w") as fh:            # and an all-zero ammeter trace
            for f in (1.0, 10.0):
                fh.write(f" {f:.8e} 0.00000000e+00 {f:.8e} 0.00000000e+00 \n")
        with self.assertRaisesRegex(lg2.Loopgain2Error, "exactly 0"):
            lg2.reconstruct(v, i)

    def test_reversed_current_injection_polarity_is_detected(self):
        # A deliberately reversed shunt source (the negative-control the
        # method requires): i(vmeas) flips sign. The reconstruction must
        # fail the 1 Hz orientation check, not emit a sign-flipped trace.
        Ts, us = known_loop(FREQS)
        ctl, v, _ = write_files(self.tmp, FREQS, Ts, us)
        rows = open(os.path.join(self.tmp, "i_ac.csv")).read().splitlines()
        flipped = []
        for ln in rows:
            p = ln.split()
            flipped.append(f" {p[0]} {-float(p[1]): .8e} {p[2]} {-float(p[3]): .8e} \n")
        i_bad = os.path.join(self.tmp, "i_flipped_ac.csv")
        with open(i_bad, "w") as fh:
            fh.writelines(flipped)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "orientation check failed"):
            lg2.reconstruct(v, i_bad)
        del ctl

    def test_swapped_voltage_probes_fail_the_deck_identity_check(self):
        Ts, us = known_loop(FREQS)
        ctl, v, i = write_files(self.tmp, FREQS, Ts, us)
        rows = open(v).read().splitlines()
        swapped = []
        for ln in rows:                     # v(fb) <-> v(fbamp) columns
            p = ln.split()
            swapped.append(" " + " ".join(
                [p[0], p[5], p[2], p[7], p[4], p[1], p[6], p[3]]) + " \n")
        v_bad = os.path.join(self.tmp, "v_swapped_ac.csv")
        with open(v_bad, "w") as fh:
            fh.writelines(swapped)
        freqs, L, hv, hi, us_rec, diag = lg2.reconstruct(v_bad, i)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "deck identity failed"):
            lg2.validate_against_control(freqs, L, hv, us_rec, ctl)

    def test_combine_refuses_the_conditioning_floor(self):
        # T = 1 + u makes 1 + Hi exactly 0: the shunt injection sees a
        # near-open circuit and the combination is genuinely undetermined.
        with self.assertRaisesRegex(lg2.Loopgain2Error, "conditioning floor"):
            lg2.combine(2.0, -1.0 + 0j)
        for bad in ((0j, 1j), (2.0, 0j), (complex(1, 2), float("nan")),
                    (float("inf"), 1j)):
            with self.assertRaises(lg2.Loopgain2Error):
                lg2.combine(*bad)

    def test_loading_ratio_identity(self):
        # u = (Hv - 1)/(Hv (1 + Hi)) must reproduce the synthesized u, and
        # must refuse the same degenerate inputs combine() refuses.
        Ts, us = known_loop(FREQS)
        _, v, i = write_files(self.tmp, FREQS, Ts, us)
        _, _, hv, hi, us_rec, _ = lg2.reconstruct(v, i)
        for got, want in zip(us_rec, us):
            # u at 1 Hz is ~1e-6 and is resolved through 1 + i(vmeas), whose
            # magnitude is u/(1+u-T): nine written digits bound its accuracy
            # to a few percent there -- the stated u(1 Hz) tolerance (1e-3)
            # is still met with three orders of magnitude to spare.
            self.assertAlmostEqual(got.real, want.real, delta=5e-2 * abs(want.real) + 1e-9)
            self.assertAlmostEqual(got.imag, want.imag, delta=5e-2 * abs(want.imag) + 1e-7)
        with self.assertRaises(lg2.Loopgain2Error):
            lg2.loading_ratio(0j, 1j)
        with self.assertRaises(lg2.Loopgain2Error):
            lg2.loading_ratio(1j, -1.0 + 0j)
        with self.assertRaises(lg2.Loopgain2Error):
            lg2.loading_ratio(float("nan"), 1j)


class Validate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _validated(self, freqs=None, Ts=None, us=None):
        Ts0, us0 = known_loop(freqs or FREQS)
        ctl, v, i = write_files(self.tmp, freqs or FREQS,
                                Ts0 if Ts is None else Ts,
                                us0 if us is None else us)
        rec = lg2.reconstruct(v, i)
        xdiag = lg2.validate_against_control(rec[0], rec[1], rec[2], rec[4], ctl)
        return rec, xdiag

    def test_healthy_loop_passes_all_stated_tolerances(self):
        (_, L, hv, hi, us, diag), x = self._validated()
        self.assertLess(x["v2ctl_max_rel_diff"], lg2.TOL_DECK_IDENTITY)
        self.assertLess(diag["u_abs_at_1hz"], lg2.TOL_U_LF)
        self.assertGreater(diag["min_abs_1_plus_hi"], lg2.MIN_DENOM)
        # below f_ugf/10 the difference is exactly the loading ratio
        self.assertGreater(x["max_abs_db_diff"], 0.0)   # they DO differ above

    def test_low_frequency_loading_premise_violation_raises(self):
        # u(1 Hz) above TOL_U_LF, with a gentle enough loading growth that
        # the control still crosses 0 dB (so the u check is what fires).
        Ts, us = known_loop(FREQS, u_at_1hz=2e-3, u_per_decade=0.1)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "u\(1 Hz\)"):
            self._validated(us=us)

    def test_ammeter_error_at_1hz_that_breaks_the_loading_premise_fails(self):
        # A small absolute error in the ammeter reading AT 1 Hz (here +2e-5
        # on i(vmeas) ~ -1 + 2e-8) moves the reconstructed u(1 Hz) past its
        # stated 1e-3 tolerance; the premise check must fail the point.
        # (Below the crossing the reconstruction leans on Hv -- that is the
        # point of the Middlebrook combination -- so only the loading
        # premise itself can police the current experiment there; polarity
        # faults are caught by the orientation check instead.)
        Ts0, us0 = known_loop(FREQS)
        ctl, v, i = write_files(self.tmp, FREQS, Ts0, us0)
        rows = open(i).read().splitlines()
        p = rows[0].split()
        rows[0] = f" {p[0]} {float(p[1]) + 2e-5: .8e} {p[2]} {p[3]} \n"
        with open(i, "w") as fh:
            fh.write("\n".join(rows) + "\n")
        rec = lg2.reconstruct(v, i)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "u\(1 Hz\)"):
            lg2.validate_against_control(rec[0], rec[1], rec[2], rec[4], ctl)

    def test_control_without_a_crossing_raises(self):
        Ts, us = known_loop(FREQS, dc_gain=-50.0, ugf=1e30)   # |L| > 1 everywhere
        ctl_L = [u - t for t, u in zip(Ts, us)]
        _, v, i = write_files(self.tmp, FREQS, Ts, us)
        ctl = os.path.join(self.tmp, "flat_ac.csv")
        with open(ctl, "w") as fh:
            for f, L1 in zip(FREQS, ctl_L):
                fh.write(f" {f:.8e} {lg2.db(L1):.8e} {f:.8e} "
                         f"{math.degrees(cmath.phase(L1)):.8e} \n")
        rec = lg2.reconstruct(v, i)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "no 0 dB crossing"):
            lg2.validate_against_control(rec[0], rec[1], rec[2], rec[4], ctl)

    def test_frequency_axis_mismatches_raise(self):
        Ts, us = known_loop(FREQS)
        ctl, v, i = write_files(self.tmp, FREQS, Ts, us)
        shifted = [f * 1.001 for f in FREQS]
        _, v2, i2 = write_files(self.tmp, shifted, Ts, us, tag="2")
        shorter = FREQS[:121]
        _, _, i3 = write_files(self.tmp, shorter, Ts[:121], us[:121], tag="3")
        rec = lg2.reconstruct(v, i)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "frequency grids differ"):
            lg2.reconstruct(v, i2)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "grids differ in length"):
            lg2.reconstruct(v, i3)
        with self.assertRaisesRegex(lg2.Loopgain2Error, "frequency axis differs"):
            lg2.validate_against_control(rec[0], rec[1], rec[2], rec[4],
                                         os.path.join(self.tmp, "ctl2_ac.csv"))


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_trace_round_trip(self):
        Ts, us = known_loop(FREQS)
        L = [-t for t in Ts]
        p = os.path.join(self.tmp, "rt_ac.csv")
        lg2.write_loopgain_trace(p, FREQS, L)
        f2, L2 = lg2.read_loopgain_trace(p)
        self.assertEqual(len(L2), len(L))
        for a, b in zip(L, L2):
            self.assertAlmostEqual(abs(a), abs(b), delta=1e-8 * abs(a))
            self.assertAlmostEqual(cmath.phase(a), cmath.phase(b), delta=1e-8)

    def test_check_export_screening(self):
        Ts, us = known_loop(FREQS)
        _, v, i = write_files(self.tmp, FREQS, Ts, us)
        self.assertEqual(lg2.check_export(v, 8, "1e10"), [])
        self.assertEqual(lg2.check_export(i, 4, "1e10"), [])
        bad8 = lg2.check_export(i, 8, "1e10")
        self.assertTrue(any("columns" in b for b in bad8))
        short = os.path.join(self.tmp, "short_ac.csv")
        rows = open(v).read().splitlines()[:-1]
        open(short, "w").write("\n".join(rows) + "\n")
        bad = lg2.check_export(short, 8, "1e10")
        self.assertTrue(any("rows, expected" in b for b in bad))

    def test_corrupt_frequency_column_raises(self):
        Ts, us = known_loop([1.0, 10.0, 100.0])
        _, v, i = write_files(self.tmp, [1.0, 10.0, 100.0], Ts, us)
        rows = open(v).read().splitlines()
        p = rows[1].split()
        p[4] = "9.9e+01"                                # a scale column drifts
        with open(v, "w") as fh:
            fh.write("\n".join([" ".join([p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]])]
                               + rows[1:]) + "\n")
        with self.assertRaisesRegex(lg2.Loopgain2Error, "frequency column"):
            lg2.read_voltage_export(v)

    def test_point_row_writes_classic_trace_and_full_csv_row(self):
        Ts, us = known_loop(FREQS)
        corners = os.path.join(self.tmp, "corners")
        os.makedirs(corners)
        write_files(corners, FREQS, Ts, us)
        # point_row names the files loopgain_ctl_<sfx>, loopgain2v_<sfx>,
        # loopgain2i_<sfx>
        os.rename(os.path.join(corners, "ctl_ac.csv"),
                  os.path.join(corners, "loopgain_ctl_tt_27c_rtyp_ac.csv"))
        os.rename(os.path.join(corners, "v_ac.csv"),
                  os.path.join(corners, "loopgain2v_tt_27c_rtyp_ac.csv"))
        os.rename(os.path.join(corners, "i_ac.csv"),
                  os.path.join(corners, "loopgain2i_tt_27c_rtyp_ac.csv"))
        row = lg2.point_row(corners, "tt_27c_rtyp", "1e10")
        self.assertTrue(row["valid"])
        self.assertEqual(row["corner"], "tt")
        self.assertEqual(row["temp_c"], "27")
        self.assertEqual(row["res_section"], "res_typ")
        self.assertTrue(os.path.isfile(
            os.path.join(corners, "loopgain2_tt_27c_rtyp_ac.csv")))
        for key in lg2.CSV_FIELDS:
            self.assertIn(key, row)
        # the classic-layout combined trace: 1 Hz -> dc gain == |T(1 Hz)| dB
        m = __import__("ac_metrics").loopgain_metrics(
            os.path.join(corners, "loopgain2_tt_27c_rtyp_ac.csv"))
        self.assertAlmostEqual(m["dc_gain_db"], abs(Ts[0]) and lg2.db(-Ts[0]),
                               delta=1e-6)
        self.assertEqual(m["n_0db_crossings"], 1)

    def test_parse_suffix(self):
        self.assertEqual(lg2.parse_suffix("tt_27c_rtyp"), ("tt", "27", "res_typ"))
        self.assertEqual(lg2.parse_suffix("ss_-40c_rwcs"), ("ss", "-40", "res_wcs"))
        self.assertEqual(lg2.parse_suffix("ff_125c_rbcs"), ("ff", "125", "res_bcs"))


if __name__ == "__main__":
    unittest.main()
