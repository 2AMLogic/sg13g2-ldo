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


if __name__ == "__main__":
    unittest.main()
