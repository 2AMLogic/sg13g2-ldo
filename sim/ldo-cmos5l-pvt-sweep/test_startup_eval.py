"""Fixture tests for startup_eval.py (issue #69). Synthetic traces only:
they test the evaluator's logic, not the circuit."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import startup_eval as se  # noqa: E402

VIN = 3.3
DT = 1e-6
T_END = 15e-3


def en_wave(t):
    def ramp(t, t0, a, b):
        if t <= t0:
            return a
        if t >= t0 + 1e-6:
            return b
        return a + (b - a) * (t - t0) / 1e-6
    if t < 7e-3:
        return ramp(t, 1e-3, 0.0, VIN)
    if t < 9e-3:
        return ramp(t, 7e-3, VIN, 0.0)
    return ramp(t, 9e-3, 0.0, VIN)


def make(shape, t_end=T_END, dt=DT, drop_after=None):
    """shape(tau) -> vout for tau = time since the first EN/2 crossing
    (1.0005 ms); the re-enable reuses the same shape from 9.0005 ms and the
    disabled stretch is 0."""
    t = [i * dt for i in range(int(round(t_end / dt)) + 1)]
    if drop_after is not None:
        t = [x for x in t if not (drop_after[0] < x < drop_after[1])]
    vout = []
    for x in t:
        if x < 1.0005e-3 or 7.0005e-3 <= x < 9.0005e-3:
            vout.append(0.0)
        elif x < 7.0005e-3:
            vout.append(shape(x - 1.0005e-3))
        else:
            vout.append(shape(x - 9.0005e-3))
    return {"t": t, "vout": vout, "en": [en_wave(x) for x in t],
            "vin": [VIN] * len(t),
            "eaout": [VIN - 0.8] * len(t), "ivin": [-1e-3] * len(t)}


def good(tau):
    return 1.8 * (1 - math.exp(-tau / 2e-4))


class StartupEval(unittest.TestCase):
    def test_monotonic_pass(self):
        r = se.evaluate(make(good))
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertTrue(r["pass"] and r["start_pass"] and r["reen_pass"])
        self.assertLess(r["start_settle_time_s"], 3e-3)
        self.assertLess(r["start_max_down_excursion_v"], 1e-6)
        self.assertAlmostEqual(r["start_t90_s"], 2e-4 * math.log(10), delta=2e-6)
        self.assertLess(r["off_vout_max_v"], 1e-9)
        self.assertEqual(r["start_early_entry_then_exit"], False)

    def test_dip_over_1mv_fails(self):
        def dip(tau):
            v = good(tau)
            return v - (6e-3 if 0.3e-3 < tau < 0.4e-3 else 0.0)
        r = se.evaluate(make(dip))
        self.assertEqual(r["verdict"], "fail")
        self.assertGreater(r["start_max_down_excursion_v"], 1e-3)
        self.assertFalse(r["start_monotonic"])
        self.assertTrue(any("downward excursion" in x for x in r["reasons"]))
        self.assertEqual(r["start_reversals_gt_1mV"], 1)
        self.assertEqual(r["start_reversals_gt_10mV"], 0)

    def test_dip_below_tolerance_passes_but_is_reported(self):
        def dip(tau):
            return good(tau) - (2.8e-3 if 0.3e-3 < tau < 0.4e-3 else 0.0)
        r = se.evaluate(make(dip))
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertGreater(r["start_max_down_excursion_v"], 3e-4)
        self.assertEqual(r["start_reversals_gt_0.1mV"], 1)
        self.assertEqual(r["start_reversals_gt_1mV"], 0)

    def test_overshoot_fails(self):
        def over(tau):
            if tau < 0.6e-3:
                return good(tau) * 1.03   # rises through 1.8 V to ~1.88 V
            return 1.8 + 0.1 * math.exp(-(tau - 0.6e-3) / 4e-4) - 0.0
        r = se.evaluate(make(over))
        self.assertGreater(r["start_peak_vout_v"], 1.836)
        self.assertGreater(r["start_overshoot_v"], 0.036)
        self.assertEqual(r["verdict"], "fail")
        self.assertTrue(any("above 1.836" in x for x in r["reasons"]))

    def test_early_entry_then_exit(self):
        def wobble(tau):
            # reaches the band, leaves it high between 1 and 2 ms, returns
            if 1.0e-3 < tau < 2.0e-3:
                return 1.85
            return min(good(tau), 1.8)
        r = se.evaluate(make(wobble))
        self.assertTrue(r["start_early_entry_then_exit"])
        self.assertLess(r["start_first_band_entry_s"], r["start_settle_time_s"])
        self.assertEqual(r["verdict"], "fail")

    def test_late_settling_fails(self):
        r = se.evaluate(make(lambda tau: 1.8 * (1 - math.exp(-tau / 1.2e-3))))
        self.assertGreater(r["start_settle_time_s"], 3e-3)
        self.assertEqual(r["verdict"], "fail")
        self.assertTrue(any("settles at" in x for x in r["reasons"]))

    def test_never_settles(self):
        r = se.evaluate(make(lambda tau: min(1.5, 1.5 * tau / 1e-3)))
        self.assertFalse(r["start_settled"])
        self.assertEqual(r["verdict"], "fail")
        self.assertIsNone(r["start_settle_time_s"])

    def test_exit_at_end_is_not_settled(self):
        # in band for a while, then leaves before the window ends
        def leaves(tau):
            return good(tau) if tau < 5.5e-3 else 1.7
        r = se.evaluate(make(leaves))
        self.assertFalse(r["start_settled"])
        self.assertEqual(r["verdict"], "fail")

    def test_missing_samples_insufficient(self):
        r = se.evaluate(make(good, drop_after=(3e-3, 3.5e-3)))
        self.assertEqual(r["verdict"], "insufficient")
        self.assertFalse(r["pass"])
        self.assertTrue(any("sample gap" in x for x in r["reasons"]))

    def test_short_window_insufficient(self):
        r = se.evaluate(make(good, t_end=5.0e-3))
        self.assertEqual(r["verdict"], "insufficient")
        self.assertFalse(r["pass"])

    def test_truncated_trace_insufficient(self):
        # simulator died mid re-enable: the re-enable window is < 5 ms
        r = se.evaluate(make(good, t_end=12e-3))
        self.assertEqual(r["verdict"], "insufficient")
        self.assertFalse(r["pass"])

    def test_nonconvergence_insufficient(self):
        for bad in (None, {}, {"t": [], "vout": [], "en": [], "vin": []}):
            r = se.evaluate(bad)
            self.assertEqual(r["verdict"], "insufficient")
            self.assertFalse(r["pass"])
            self.assertTrue(r["reasons"])

    def test_nan_insufficient(self):
        tr = make(good)
        tr["vout"][5000] = float("nan")
        self.assertEqual(se.evaluate(tr)["verdict"], "insufficient")

    def test_no_enable_edge_insufficient(self):
        tr = make(good)
        tr["en"] = [0.0] * len(tr["t"])
        r = se.evaluate(tr)
        self.assertEqual(r["verdict"], "insufficient")

    def test_off_state_leak_fails(self):
        tr = make(good)
        for i, x in enumerate(tr["t"]):
            if x < 1e-3:
                tr["vout"][i] = 0.4
        r = se.evaluate(tr)
        self.assertEqual(r["verdict"], "fail")
        self.assertTrue(any("off-state" in x for x in r["reasons"]))

    def test_reenable_failure_is_separate(self):
        def shape_for(tau):
            return good(tau)
        tr = make(shape_for)
        # re-enable window: add a 5 mV dip
        for i, x in enumerate(tr["t"]):
            if 9.5e-3 < x < 9.6e-3:
                tr["vout"][i] -= 5e-3
        r = se.evaluate(tr)
        self.assertTrue(r["start_pass"])
        self.assertFalse(r["reen_pass"])
        self.assertEqual(r["verdict"], "fail")

    def test_time_must_increase(self):
        tr = make(good)
        tr["t"][100] = tr["t"][99]
        self.assertEqual(se.evaluate(tr)["verdict"], "insufficient")

    def test_stress_reported(self):
        r = se.evaluate(make(good))
        self.assertAlmostEqual(r["start_max_vsg_pass_v"], 0.8, places=6)
        self.assertAlmostEqual(r["max_vsg_men_v"], VIN, places=6)
        self.assertFalse(r["stress_gt_ref"])


if __name__ == "__main__":
    unittest.main()
