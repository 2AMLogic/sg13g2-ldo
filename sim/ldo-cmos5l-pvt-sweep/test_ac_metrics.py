"""Direct contract tests for ac_metrics.py (issue #117). stdlib only, no PDK,
no simulator.

test_dynamic_doe.py::Parsers covers the analytic single-crossing PM/GM and
exact-grid PSRR cases through dynamic_doe.parse_point. This module pins the
parser's own contracts: phase unwrapping, multiple 0 dB crossings, the direct
None returns, and log-distance nearest-point PSRR selection.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v
"""
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ac_metrics as am  # noqa: E402


def monotone(seq, decreasing=True):
    pairs = zip(seq, seq[1:])
    return all(b < a for a, b in pairs) if decreasing else all(b > a for a, b in pairs)


class Fixture(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.dir = self._td.name

    def write(self, name, rows):
        """rows: tuples of numbers, written whitespace-separated."""
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write("".join(" ".join(f"{v:.8e}" for v in r) + "\n" for r in rows))
        return path

    def lg(self, points, name="lg.dat"):
        """points: (freq_hz, gain_db, phase_deg) -> 4-column wrdata."""
        return self.write(name, [(f, db, f, deg) for f, db, deg in points])

    def ps(self, points, name="ps.dat"):
        return self.write(name, points)


class UnwrapDeg(unittest.TestCase):
    # True phase falls 120, 170, 220, 270 deg below start; the simulator
    # reports it wrapped into (-180, 180].
    WRAPPED = [-120.0, -170.0, 170.0, 120.0, 60.0]
    TRUE = [-120.0, -170.0, -190.0, -240.0, -300.0]

    def test_ramp_across_minus_180_unwraps_monotonically(self):
        out = am.unwrap_deg(self.WRAPPED)
        self.assertTrue(monotone(out), out)
        for got, want in zip(out, self.TRUE):
            self.assertAlmostEqual(got, want)

    def test_negative_control_wrapped_input_is_not_monotone(self):
        # The monotonicity assertion above must fail on the raw input.
        self.assertFalse(monotone(self.WRAPPED))
        with self.assertRaises(AssertionError):
            self.assertTrue(monotone(self.WRAPPED))

    def test_rising_ramp_across_plus_180(self):
        out = am.unwrap_deg([150.0, 170.0, -170.0, -150.0])
        self.assertTrue(monotone(out, decreasing=False), out)
        self.assertAlmostEqual(out[-1], 210.0)

    def test_single_and_in_range_inputs_unchanged(self):
        self.assertEqual(am.unwrap_deg([42.0]), [42.0])
        self.assertEqual(am.unwrap_deg([0.0, -90.0, -170.0]), [0.0, -90.0, -170.0])


class LoopgainDirect(Fixture):
    def test_multiple_zero_db_crossings_count_and_worst_pm(self):
        # Gain crosses 0 dB three times (10 Hz down, ~316 Hz up, ~3.2 MHz
        # down); the first crossing is NOT the worst margin.
        pts = [
            (1.0, 20.0, -90.0),
            (1e2, -20.0, -110.0),
            (1e3, 20.0, -150.0),
            (1e4, 20.0, -150.0),
            (1e6, 20.0, -160.0),
            (1e7, -20.0, -180.0 + 1.0),
        ]
        m = am.loopgain_metrics(self.lg(pts))
        self.assertEqual(m["n_0db_crossings"], 3)
        # Crossing 1: frac .5 of decade 0..2 -> 10 Hz, phase -100 -> PM 80.
        self.assertAlmostEqual(m["unity_gain_freq_hz"], 10.0, places=6)
        self.assertAlmostEqual(m["phase_margin_deg"], 80.0)
        # Crossing 2: halfway 1e2..1e3 -> phase -130 -> PM 50.
        # Crossing 3: halfway 1e6..1e7 -> phase -169.5 -> PM 10.5 (worst).
        self.assertAlmostEqual(m["phase_margin_worst_deg"], 10.5)
        self.assertLess(m["phase_margin_worst_deg"], m["phase_margin_deg"])

    def test_worst_pm_is_min_not_last_or_first(self):
        # Worst margin in the middle crossing.
        pts = [
            (1.0, 10.0, -60.0),
            (1e1, -10.0, -80.0),     # crossing 1 at -70 -> PM 110
            (1e2, 10.0, -170.0),     # crossing 2 at -125 -> PM 55
            (1e3, -10.0, -100.0),    # crossing 3 at -135 -> PM 45
        ]
        m = am.loopgain_metrics(self.lg(pts))
        self.assertEqual(m["n_0db_crossings"], 3)
        self.assertAlmostEqual(m["phase_margin_deg"], 110.0)
        self.assertAlmostEqual(m["phase_margin_worst_deg"], 45.0)

    def test_no_zero_db_crossing_fields_none(self):
        pts = [(1.0, -5.0, -10.0), (10.0, -20.0, -40.0), (100.0, -40.0, -90.0)]
        m = am.loopgain_metrics(self.lg(pts))
        self.assertEqual(m["n_0db_crossings"], 0)
        self.assertEqual(m["dc_gain_db"], -5.0)
        for k in ("unity_gain_freq_hz", "phase_margin_deg", "phase_margin_worst_deg"):
            self.assertIsNone(m[k], k)

    def test_no_minus_180_crossing_fields_none(self):
        pts = [(1.0, 20.0, -10.0), (10.0, 0.5, -45.0), (100.0, -20.0, -90.0)]
        m = am.loopgain_metrics(self.lg(pts))
        self.assertEqual(m["n_0db_crossings"], 1)
        self.assertIsNotNone(m["phase_margin_deg"])
        self.assertEqual(m["n_gain_margin_crossings"], 0)
        self.assertIsNone(m["gain_margin_freq_hz"])
        self.assertIsNone(m["gain_margin_db"])

    def test_pm_uses_unwrapped_phase_across_wrap(self):
        # Wrapped phase jumps -170 -> +160 (true -200); the 0 dB crossing sits
        # between them, so a parser that skipped unwrapping would interpolate
        # across ~330 degrees and report a nonsense margin.
        pts = [(1.0, 10.0, -100.0), (1e2, 10.0, -170.0), (1e3, 10.0, -171.0),
               (1e4, -10.0, 160.0)]
        m = am.loopgain_metrics(self.lg(pts))
        # True phases -171 -> -200 midway: -185.5 -> PM -5.5.
        self.assertAlmostEqual(m["phase_margin_deg"], -5.5)

    def test_missing_and_empty_input_return_none(self):
        self.assertIsNone(am.loopgain_metrics(os.path.join(self.dir, "absent.dat")))
        empty = self.write("empty.dat", [])
        self.assertIsNone(am.loopgain_metrics(empty))
        # Rows narrower than the 4 required columns are dropped -> empty.
        short = self.write("short.dat", [(1.0, 2.0)])
        self.assertIsNone(am.loopgain_metrics(short))


class PsrrDirect(Fixture):
    # Neither 1 kHz nor 100 kHz is on the grid.
    # Target 1 kHz: log picks 5 kHz (0.699 dec) over 100 Hz (1 dec); linear
    # would pick 100 Hz (900 Hz away vs 4000).
    # Target 100 kHz: log picks 250 kHz (0.398 dec) over 20 kHz (0.699 dec);
    # linear would pick 20 kHz (80 kHz away vs 150 kHz).
    GRID = [
        (100.0, -10.0),
        (5e3, -20.0),
        (1e4, -30.0),
        (2.5e5, -40.0),
        (1e6, -50.0),
        (2e4, -60.0),
    ]

    def test_log_nearest_selection_differs_from_linear(self):
        rows = sorted(self.GRID)
        for target in (1e3, 1e5):
            log_pick = min(rows, key=lambda r: abs(math.log10(r[0]) - math.log10(target)))
            lin_pick = min(rows, key=lambda r: abs(r[0] - target))
            self.assertNotEqual(log_pick, lin_pick, target)
        m = am.psrr_metrics(self.ps(rows))
        self.assertEqual(m["psrr_db_1khz"], -20.0)     # 5 kHz row (linear: 100 Hz = -10)
        self.assertEqual(m["psrr_db_100khz"], -40.0)   # 250 kHz row (linear: 20 kHz = -60)

    def test_missing_and_empty_input_return_none(self):
        self.assertIsNone(am.psrr_metrics(os.path.join(self.dir, "absent.dat")))
        self.assertIsNone(am.psrr_metrics(self.write("empty.dat", [])))


class MutationSensitivity(Fixture):
    """Negative controls: a deliberately broken re-implementation of each
    newly covered behaviour must be caught by the same assertions the real
    tests use. (The PR description also records a source-level mutation.)"""

    def test_linear_distance_psrr_would_be_detected(self):
        rows = sorted(PsrrDirect.GRID)
        lin = min(rows, key=lambda r: abs(r[0] - 1e3))[1]
        self.assertNotEqual(lin, am.psrr_metrics(self.ps(rows))["psrr_db_1khz"])

    def test_no_unwrap_would_change_margin(self):
        pts = [(1.0, 10.0, -100.0), (1e2, 10.0, -170.0), (1e3, 10.0, -171.0),
               (1e4, -10.0, 160.0)]
        real = am.loopgain_metrics(self.lg(pts))["phase_margin_deg"]
        orig = am.unwrap_deg
        am.unwrap_deg = lambda p: list(p)
        try:
            mutated = am.loopgain_metrics(self.lg(pts))["phase_margin_deg"]
        finally:
            am.unwrap_deg = orig
        self.assertNotAlmostEqual(real, mutated, places=3)


# DR-0014 classifier fixtures. Phase is given unwrapped (the classifier
# re-unwraps; a first sample inside (-180, 180] and steps < 180 deg keep it
# unchanged). Frequencies span 1 Hz to 100 MHz like the committed bench, so the
# "first decade" is 1-10 Hz and the "last decade" is 10-100 MHz.
#
# Legacy-shaped trace: falling crossover with ~75 deg, a -180 deg crossing at
# -14 dB, then the loop gain RISES again over the last decade and crosses 0 dB
# upward at a phase of -342 deg (== +18 deg), ending above unity at 100 MHz.
LEGACY_SHAPE = [
    (1.0, 124.0, -6.6),
    (10.0, 121.0, -51.8),
    (1e3, 65.0, -167.0),
    (1e5, 5.0, -102.7),
    (3e5, -5.0, -114.0),
    (1e6, -14.0, -208.0),
    (1e7, -4.8, -322.0),
    (5e7, -0.2, -340.0),
    (7e7, 0.2, -344.0),
    (1e8, 0.5, -347.6),
]

# The same low/mid band, but the gain keeps falling to the ceiling.
BOUNDED_MULTI = [
    (1.0, 124.0, -6.6),
    (10.0, 121.0, -51.8),
    (1e3, 65.0, -167.0),
    (1e5, 5.0, -102.7),          # falling crossing near phase -104 (PM ~76)
    (1.2e5, -1.0, -104.0),
    (3e5, -11.0, -150.0),
    (1e6, -14.0, -208.0),        # -180 deg crossing between, gain bracket -14..-11
    (3e6, -2.0, -330.0),
    (5e6, 2.0, -342.0),          # rising crossing at ~ -336 deg (distance ~156)
    (8e6, 1.0, -350.0),
    (1e7, -1.0, -352.0),         # falling crossing at ~ -351 deg (distance ~171)
    (3e7, -20.0, -356.0),
    (1e8, -40.0, -358.0),        # ceiling: -40 dB, non-increasing over last decade
]


class Dr0014Helpers(unittest.TestCase):
    def test_wrap180_range(self):
        for raw, want in [(0.0, 0.0), (-180.0, 180.0), (180.0, 180.0),
                          (-342.0, 18.0), (190.0, -170.0), (-540.0, 180.0),
                          (360.0, 0.0), (-105.0, -105.0)]:
            self.assertAlmostEqual(am.wrap180(raw), want, msg=raw)

    def test_critical_distance_matches_classic_pm_inside_first_sheet(self):
        # For phase in (-180, 0] the distance equals the classic 180 + phase.
        for ph in (-0.0, -45.0, -105.0, -179.0):
            self.assertAlmostEqual(am.critical_distance_deg(ph), 180.0 + ph)

    def test_critical_distance_is_angular_not_180_plus_phase(self):
        # -342 deg is 18 deg past -360: 162 deg from the -1 point, not -162.
        self.assertAlmostEqual(am.critical_distance_deg(-342.0), 162.0)
        self.assertAlmostEqual(am.critical_distance_deg(-540.0), 0.0)
        self.assertAlmostEqual(am.critical_distance_deg(-200.0), 20.0)


class Dr0014Classifier(Fixture):
    def cls(self, pts, name="lg.dat"):
        return am.classify_margins(self.lg(pts, name))

    # -- multi-crossing PM ------------------------------------------------
    def test_multi_crossing_pm_is_min_angular_distance_and_bounded_pass(self):
        m = self.cls(BOUNDED_MULTI)
        self.assertEqual(len(m["zero_db_crossings"]), 3)
        dirs = [c["direction"] for c in m["zero_db_crossings"]]
        self.assertEqual(dirs, ["falling", "rising", "falling"])
        ds = [c["margin_deg"] for c in m["zero_db_crossings"]]
        self.assertTrue(all(d > 0 for d in ds), ds)
        self.assertAlmostEqual(m["pm"]["value_deg"], min(ds))
        self.assertLess(m["pm"]["value_deg"], 80.0)
        self.assertGreater(m["pm"]["value_deg"], 70.0)
        self.assertTrue(m["ceiling"]["bounded"])
        self.assertTrue(m["low_end"]["ok"])
        self.assertEqual(m["pm"]["verdict"], "pass", m["pm"])
        # The legacy worst-crossing formula (180 + unwrapped phase) would call
        # the second crossing a margin of about -156 deg.
        legacy = am.loopgain_metrics(self.lg(BOUNDED_MULTI, "legacy.dat"))
        self.assertLess(legacy["phase_margin_worst_deg"], -100.0)
        self.assertNotAlmostEqual(legacy["phase_margin_worst_deg"], m["pm"]["value_deg"], places=1)

    def test_multi_crossing_unbounded_ceiling_is_ambiguous_not_pass(self):
        m = self.cls(LEGACY_SHAPE)
        self.assertEqual([c["direction"] for c in m["zero_db_crossings"]], ["falling", "rising"])
        self.assertAlmostEqual(m["zero_db_crossings"][1]["margin_deg"], 180 - 18 - 0.0, delta=4.0)
        self.assertFalse(m["ceiling"]["bounded"])
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertIn("ceiling_unbounded", m["pm"]["reasons"])
        self.assertEqual(m["gm"]["verdict"], "ambiguous")
        self.assertIn("ceiling_unbounded", m["gm"]["reasons"])
        # the in-band numbers are still reported
        self.assertGreater(m["pm"]["value_deg"], 45.0)
        self.assertGreater(m["gm"]["value_db"], 10.0)

    def test_in_band_pm_miss_fails_even_with_unbounded_ceiling(self):
        pts = [list(p) for p in LEGACY_SHAPE]
        pts[3] = (1e5, 5.0, -150.0)      # falling crossing now near -152 deg: PM ~28
        pts[4] = (3e5, -5.0, -155.0)
        m = self.cls([tuple(p) for p in pts])
        self.assertFalse(m["ceiling"]["bounded"])
        self.assertEqual(m["pm"]["verdict"], "fail")
        self.assertLess(m["pm"]["value_deg"], 45.0)

    def test_negative_control_first_crossing_rule_would_miss_later_bad_crossing(self):
        # A later crossing with a small margin must decide the verdict.
        pts = [(1.0, 80.0, -5.0), (10.0, 78.0, -20.0), (1e3, 10.0, -90.0),
               (1e4, -10.0, -100.0),          # crossing 1: PM ~85
               (1e5, -5.0, -150.0),
               (1e6, 5.0, -160.0),            # crossing 2 (rising) ~ -155: PM ~25
               (3e6, 3.0, -165.0),
               (1e7, -12.0, -170.0),          # crossing 3: PM ~13
               (1e8, -40.0, -175.0)]
        m = self.cls(pts)
        self.assertEqual(m["pm"]["verdict"], "fail")
        self.assertGreater(m["zero_db_crossings"][0]["margin_deg"], 45.0)
        self.assertLess(m["pm"]["value_deg"], 45.0)

    # -- GM with no -180 deg crossing ----------------------------------------
    NO_CRIT_BOUNDED = [(1.0, 80.0, -5.0), (10.0, 78.0, -30.0), (1e3, 20.0, -90.0),
                       (1e4, 0.5, -120.0), (2e4, -3.0, -130.0), (1e6, -20.0, -150.0),
                       (1e7, -30.0, -160.0), (1e8, -45.0, -170.0)]

    def test_no_minus_180_crossing_bounded_ceiling_scores_lower_bound(self):
        m = self.cls(self.NO_CRIT_BOUNDED)
        self.assertEqual(m["critical_crossings"], [])
        self.assertIsNone(m["gm"]["value_db"])
        self.assertTrue(m["ceiling"]["bounded"])
        self.assertAlmostEqual(m["gm"]["above_ceiling_lower_bound_db"], 45.0)
        self.assertEqual(m["gm"]["verdict"], "pass")

    def test_no_minus_180_crossing_rising_ceiling_is_ambiguous(self):
        pts = [list(p) for p in self.NO_CRIT_BOUNDED]
        pts[-2] = (1e7, -50.0, -160.0)   # gain rises from -50 to -45 over the last decade
        m = self.cls([tuple(p) for p in pts])
        self.assertFalse(m["ceiling"]["bounded"])
        self.assertFalse(m["ceiling"]["last_decade_non_increasing"])
        self.assertEqual(m["gm"]["verdict"], "ambiguous")
        self.assertIn("ceiling_unbounded", m["gm"]["reasons"])
        self.assertIsNone(m["gm"]["above_ceiling_lower_bound_db"])

    def test_no_minus_180_crossing_ceiling_above_floor_is_ambiguous(self):
        pts = [list(p) for p in self.NO_CRIT_BOUNDED]
        pts[-2] = (1e7, -6.0, -160.0)
        pts[-1] = (1e8, -9.9, -170.0)     # falling, but only 9.9 dB below unity
        m = self.cls([tuple(p) for p in pts])
        self.assertTrue(m["ceiling"]["last_decade_non_increasing"])
        self.assertFalse(m["ceiling"]["bounded"])
        self.assertEqual(m["gm"]["verdict"], "ambiguous")

    def test_no_minus_180_crossing_is_never_an_automatic_fail(self):
        # The #64 'failed' rows: no -180 crossing must not be scored as a miss.
        m = self.cls(LEGACY_SHAPE[:4] + [(3e5, -5.0, -114.0), (1e6, -14.0, -150.0),
                                         (1e7, -4.8, -10.0), (5e7, -0.2, 10.0),
                                         (7e7, 0.2, 11.0), (1e8, 0.5, 12.4)])
        self.assertEqual(m["critical_crossings"], [])
        self.assertNotEqual(m["gm"]["verdict"], "fail")
        self.assertEqual(m["gm"]["verdict"], "ambiguous")

    # -- near-threshold (sampling resolution) ------------------------------
    def _pm_bracket(self, ph_a, ph_b):
        return [(1.0, 80.0, -5.0), (10.0, 78.0, -20.0), (1e3, 20.0, -90.0),
                (1e4, 1.0, ph_a), (1.2e4, -1.0, ph_b),
                (1e6, -30.0, -170.0), (1e7, -40.0, -175.0), (1e8, -60.0, -178.0)]

    def test_pm_bound_inside_bracket_is_ambiguous(self):
        m = self.cls(self._pm_bracket(-134.0, -136.0))   # distances 46 / 44
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertIn("resolution_limited", m["pm"]["reasons"])
        self.assertAlmostEqual(m["zero_db_crossings"][0]["margin_bracket_deg"][0], 44.0)
        self.assertAlmostEqual(m["zero_db_crossings"][0]["margin_bracket_deg"][1], 46.0)

    def test_pm_bracket_wholly_above_passes_wholly_below_fails(self):
        self.assertEqual(self.cls(self._pm_bracket(-130.0, -134.9))["pm"]["verdict"], "pass")
        self.assertEqual(self.cls(self._pm_bracket(-135.1, -140.0))["pm"]["verdict"], "fail")

    def test_pm_straddling_bracket_with_interpolated_miss_stays_a_fail(self):
        # distances 46 / 42, interpolated 44: the recorded miss is never upgraded
        m = self.cls(self._pm_bracket(-134.0, -138.0))
        self.assertAlmostEqual(m["pm"]["value_deg"], 44.0)
        self.assertEqual(m["pm"]["verdict"], "fail")

    def _gm_bracket(self, g_a, g_b):
        return [(1.0, 80.0, -5.0), (10.0, 78.0, -20.0), (1e3, 0.5, -90.0),
                (2e3, -1.0, -100.0), (1e5, g_a, -175.0), (1.2e5, g_b, -185.0),
                (1e7, -40.0, -260.0), (1e8, -60.0, -265.0)]

    def test_gm_bound_inside_bracket_is_ambiguous(self):
        m = self.cls(self._gm_bracket(-9.5, -10.5))
        self.assertEqual(m["gm"]["verdict"], "ambiguous")
        self.assertIn("resolution_limited", m["gm"]["reasons"])
        self.assertEqual(m["critical_crossings"][0]["gain_bracket_db"], [-10.5, -9.5])

    def test_gm_bracket_wholly_above_passes_wholly_below_fails(self):
        self.assertEqual(self.cls(self._gm_bracket(-11.0, -12.0))["gm"]["verdict"], "pass")
        self.assertEqual(self.cls(self._gm_bracket(-8.0, -9.0))["gm"]["verdict"], "fail")

    def test_gm_straddling_bracket_with_interpolated_miss_stays_a_fail(self):
        m = self.cls(self._gm_bracket(-9.5, -10.1))      # interpolated -9.8 dB
        self.assertAlmostEqual(m["gm"]["value_db"], 9.8)
        self.assertEqual(m["gm"]["verdict"], "fail")

    # -- unstable / premises / invalid -------------------------------------
    def test_minus_180_crossing_above_unity_fails_gm_and_flags_nyquist(self):
        pts = [(1.0, 80.0, -5.0), (10.0, 78.0, -20.0), (1e3, 10.0, -170.0),
               (2e3, 6.0, -190.0), (1e4, -6.0, -210.0),
               (1e7, -40.0, -260.0), (1e8, -60.0, -265.0)]
        m = self.cls(pts)
        self.assertTrue(m["critical_crossings"][0]["above_unity"])
        self.assertEqual(m["gm"]["verdict"], "fail")
        self.assertLess(m["gm"]["value_db"], 0.0)
        self.assertEqual(m["nyquist"]["in_band_net_crossings"], -1)
        self.assertEqual(m["nyquist"]["class"], "unstable")
        self.assertEqual(m["pm"]["verdict"], "fail")    # crossing at -200: distance 20

    ENCIRCLED = [(1.0, 80.0, -5.0), (10.0, 78.0, -20.0), (1e3, 10.0, -170.0),
                 (2e3, 6.0, -190.0),               # -180 deg passed ABOVE unity
                 (1e4, 1.0, -238.0), (1.1e4, -1.0, -242.0),   # 0 dB at ~-240: 60 deg away
                 (1e7, -40.0, -260.0), (1e8, -60.0, -265.0)]

    def test_crossing_after_encirclement_is_negative_and_fails(self):
        m = self.cls(self.ENCIRCLED)
        z = m["zero_db_crossings"][0]
        self.assertEqual(z["net_crossings_above_unity_before"], -1)
        self.assertAlmostEqual(z["distance_deg"], 60.0, delta=0.5)
        self.assertAlmostEqual(z["margin_deg"], -z["distance_deg"])
        self.assertEqual(m["pm"]["verdict"], "fail")
        self.assertEqual(m["gm"]["verdict"], "fail")
        # negative control: unsigned distance alone would have passed (60 >= 45)
        self.assertGreaterEqual(z["distance_bracket_deg"][0], 45.0)

    def test_encirclement_in_the_same_sample_step_follows_interpolation(self):
        # -180 deg (interpolated gain +0.67 dB) and 0 dB (phase -185) fall in
        # one sample step: the sign follows the interpolation like the record
        # (-5 deg), but the unresolved order blocks any pass and the Nyquist class.
        pts = [(1.0, 80.0, -5.0), (10.0, 78.0, -20.0), (1e2, 30.0, -120.0),
               (1e3, 2.0, -170.0), (2e3, -2.0, -200.0),
               (1e7, -40.0, -260.0), (1e8, -60.0, -265.0)]
        m = self.cls(pts)
        c = m["critical_crossings"][0]
        self.assertTrue(c["above_unity"])
        self.assertFalse(c["unity_resolved"])
        self.assertAlmostEqual(m["zero_db_crossings"][0]["margin_deg"], -5.0)
        self.assertAlmostEqual(m["zero_db_crossings"][0]["margin_deg"],
                               am.loopgain_metrics(self.lg(pts, "l.dat"))["phase_margin_deg"])
        self.assertEqual(m["pm"]["verdict"], "fail")
        self.assertEqual(m["nyquist"]["class"], "undetermined")

    def test_encirclement_sign_needs_the_low_end_premise(self):
        pts = list(self.ENCIRCLED)
        pts[1] = (10.0, 81.0, -20.0)      # first decade rising: premise fails
        m = self.cls(pts)
        self.assertFalse(m["low_end"]["ok"])
        self.assertEqual(m["pm"]["verdict"], "ambiguous")

    def test_bounded_clean_trace_is_nyquist_stable(self):
        m = self.cls(BOUNDED_MULTI)
        self.assertEqual(m["nyquist"]["class"], "stable")
        self.assertEqual(m["gm"]["verdict"], "pass")

    def test_low_end_below_unity_is_ambiguous(self):
        pts = [(1.0, -1.0, -5.0), (10.0, -2.0, -20.0), (1e3, -10.0, -90.0),
               (1e6, -30.0, -170.0), (1e7, -40.0, -175.0), (1e8, -60.0, -178.0)]
        m = self.cls(pts)
        self.assertFalse(m["low_end"]["ok"])
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertIn("low_end_premise_failed", m["pm"]["reasons"])
        self.assertIn("no_zero_db_crossing", m["pm"]["reasons"])

    def test_low_end_rising_first_decade_is_ambiguous(self):
        pts = list(BOUNDED_MULTI)
        pts[1] = (10.0, 126.0, -51.8)     # gain grows with frequency in 1-10 Hz
        m = self.cls(pts)
        self.assertFalse(m["low_end"]["ok"])
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertEqual(m["gm"]["verdict"], "ambiguous")

    def test_invalid_trace_is_ambiguous(self):
        pts = list(BOUNDED_MULTI)
        pts[2], pts[3] = pts[3], pts[2]   # frequency not increasing
        m = self.cls(pts)
        self.assertFalse(m["valid"])
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertEqual(m["gm"]["verdict"], "ambiguous")
        self.assertIn("invalid_trace", m["pm"]["reasons"])

    def test_missing_trace_returns_none(self):
        self.assertIsNone(am.classify_margins(os.path.join(self.dir, "absent.dat")))


class Dr0014CommittedTrace(unittest.TestCase):
    """One committed legacy trace (record 20261010-025634-60a3e81, a point the
    characterization report listed as ambiguous)."""
    PATH = os.path.join(HERE, "corners", "20261010-025634-60a3e81", "loopgain_ff_-40c_rwcs_ac.csv")

    def test_ff_m40_wcs(self):
        m = am.classify_margins(self.PATH)
        legacy = am.loopgain_metrics(self.PATH)
        z = m["zero_db_crossings"]
        self.assertEqual(len(z), 2)
        self.assertAlmostEqual(z[0]["margin_deg"], legacy["phase_margin_deg"], places=9)
        # recorded phase_margin_worst_deg is 180 + unwrapped phase; the angular
        # distance has the same magnitude and the opposite sign here.
        self.assertAlmostEqual(z[1]["margin_deg"], -legacy["phase_margin_worst_deg"], places=9)
        self.assertEqual(m["pm"]["verdict"], "ambiguous")
        self.assertEqual(m["pm"]["reasons"], ["ceiling_unbounded"])
        self.assertEqual(m["gm"]["verdict"], "ambiguous")
        self.assertAlmostEqual(m["gm"]["value_db"], legacy["gain_margin_db"], places=9)
        self.assertGreater(m["ceiling"]["gain_db"], 0.0)

    def test_committed_unstable_doe_point_keeps_its_negative_margin(self):
        # #64 base matrix, ff/-40C/res_wcs, 50 mA, 0.33 uF, 0 ohm: the combined
        # record's worst PM (-52.70 deg) and GM (-9.20 dB). DR-0014 must keep
        # both as fails with the same signed values.
        p = os.path.join(HERE, "corners", "20261010-091123-a31c626",
                         "loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_ac.csv")
        m = am.classify_margins(p)
        legacy = am.loopgain_metrics(p)
        self.assertAlmostEqual(m["zero_db_crossings"][0]["margin_deg"], legacy["phase_margin_deg"], places=9)
        self.assertLess(legacy["phase_margin_deg"], -50.0)
        self.assertEqual(m["pm"]["verdict"], "fail")
        self.assertEqual(m["gm"]["verdict"], "fail")
        self.assertAlmostEqual(m["gm"]["value_db"], legacy["gain_margin_db"], places=9)
        self.assertEqual(m["nyquist"]["in_band_net_crossings"], -1)


class Dr0014MutationSensitivity(Fixture):
    """Negative controls: each load-bearing piece of the rule, mutated, must
    change an outcome the tests above pin."""

    def _with(self, name, repl, fn):
        orig = getattr(am, name)
        setattr(am, name, repl)
        try:
            return fn()
        finally:
            setattr(am, name, orig)

    def test_classic_formula_instead_of_angular_distance_is_detected(self):
        p = self.lg(BOUNDED_MULTI)
        real = am.classify_margins(p)["pm"]
        mut = self._with("critical_distance_deg", lambda ph: 180.0 + ph,
                         lambda: am.classify_margins(p)["pm"])
        self.assertEqual(real["verdict"], "pass")
        self.assertEqual(mut["verdict"], "fail")

    def test_dropping_the_ceiling_premise_is_detected(self):
        p = self.lg(LEGACY_SHAPE)
        mut = self._with("ceiling_bounded", lambda *a, **k: True,
                         lambda: am.classify_margins(p))
        self.assertEqual(mut["pm"]["verdict"], "pass")   # what the guard prevents
        self.assertEqual(am.classify_margins(p)["pm"]["verdict"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
