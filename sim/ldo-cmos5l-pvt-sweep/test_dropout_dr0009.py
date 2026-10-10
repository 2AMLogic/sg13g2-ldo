"""Tests for the DR-0009 dropout reducer (issue #70). stdlib only, no PDK.

    python3 -m unittest sim/ldo-cmos5l-pvt-sweep/test_dropout_dr0009.py -v
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dropout_metrics as dcm  # noqa: E402
import dc_metrics as legacy  # noqa: E402
import dropout_campaign as dc  # noqa: E402

N = dcm.DR0009_ROWS
VINS = [round(dcm.DR0009_VIN_LO + dcm.DR0009_VIN_STEP * i, 6) for i in range(N)]


def curve(knee, slope=1.0, vreg=1.8):
    """Regulated at vreg above `knee`, then VOUT falls linearly (slope V/V)."""
    return [(v, vreg if v >= knee else vreg - slope * (knee - v)) for v in VINS]


class Reducer(unittest.TestCase):
    def test_known_crossing_between_grid_points(self):
        # slope 1: VOUT hits 1.782 at Vin = knee - 0.018; knee 2.0525 -> Vin* 2.0345
        r = dcm.dropout_1pct(curve(2.0525))
        self.assertEqual(r["status"], "resolved")
        self.assertAlmostEqual(r["vin_cross_v"], 2.0345, places=6)
        self.assertAlmostEqual(r["dropout_1pct_vin_minus_vout_v"], 2.0345 - 1.782, places=6)
        self.assertAlmostEqual(r["bracket_v"], 0.005, places=6)
        self.assertLessEqual(r["dropout_1pct_lower_v"], r["dropout_1pct_vin_minus_vout_v"])
        self.assertGreaterEqual(r["dropout_1pct_upper_v"], r["dropout_1pct_vin_minus_vout_v"])

    def test_reference_is_actual_vout_not_fixed_target(self):
        r = dcm.dropout_1pct(curve(2.10, vreg=1.79))
        self.assertAlmostEqual(r["v_thr_v"], 0.99 * 1.79)

    def test_exact_grid_point(self):
        # VOUT exactly at threshold on a grid point is still "regulating";
        # the crossing is that point.
        thr = 0.99 * 1.8
        pts = [(v, 1.8 if v > 2.000 else (thr if v == 2.0 else thr - 0.05)) for v in VINS]
        r = dcm.dropout_1pct(pts)
        self.assertEqual(r["status"], "resolved")
        self.assertAlmostEqual(r["vin_cross_v"], 2.0, places=9)
        self.assertAlmostEqual(r["dropout_1pct_vin_minus_vout_v"], 2.0 - thr, places=9)

    def test_no_crossing_is_upper_bound_only(self):
        r = dcm.dropout_1pct([(v, 1.8) for v in VINS])
        self.assertEqual(r["status"], "floor_limited_upper_bound")
        self.assertNotIn("dropout_1pct_vin_minus_vout_v", r)
        self.assertAlmostEqual(r["dropout_1pct_upper_v"], dcm.DR0009_VIN_LO - 0.99 * 1.8)

    def test_reference_out_of_regulation(self):
        r = dcm.dropout_1pct([(v, 1.5) for v in VINS])
        self.assertEqual(r["status"], "reference_out_of_regulation")

    def test_malformed(self):
        for bad in ([(3.3, 1.8)], [(1.7, 1.8), (1.7, 1.8), (3.3, 1.8)],
                    [(v, 1.8) for v in VINS if v != 3.3],
                    [(1.7, float("nan")), (2.0, 1.8), (3.3, 1.8)], [("a", 1)] * 3):
            self.assertEqual(dcm.dropout_1pct(bad)["status"], "malformed", bad)

    def test_scans_down_from_reference_ignores_above(self):
        pts = [(v, 1.0 if v > 3.4 else o) for v, o in curve(2.05)]
        self.assertEqual(dcm.dropout_1pct(pts)["status"], "resolved")

    def test_legacy_metric_untouched(self):
        self.assertTrue(callable(legacy.dc_metrics))
        self.assertEqual((legacy.VIN_MIN, legacy.VIN_MAX, legacy.VIN_STEP), (2.00, 3.63, 0.01))


def write_block(path, pts, cut=0):
    lines = [" ".join(f"{x:.8e}" for x in (v, v, v, o, v, -2e-5)) for v, o in pts]
    if cut:
        lines = lines[:-cut]
    open(path, "w").write("\n".join(lines) + "\n")


class FileAndCampaign(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_file_ok_truncated_multiblock_missing(self):
        p = os.path.join(self.d, "a_dc.csv")
        write_block(p, curve(2.05))
        self.assertEqual(dcm.dropout_1pct_file(p)["status"], "resolved")
        write_block(p, curve(2.05), cut=10)
        r = dcm.dropout_1pct_file(p)
        self.assertEqual(r["status"], "malformed")
        write_block(p, curve(2.05) + curve(2.05))
        self.assertIn("more than one", dcm.dropout_1pct_file(p)["reason"])
        self.assertEqual(dcm.dropout_1pct_file(os.path.join(self.d, "none"))["status"], "malformed")

    def fill(self, skip=None, knees=None):
        for i, (c, t, r, pid) in enumerate(dc.coords()):
            if pid == skip:
                continue
            k = (knees or {}).get(pid, 2.05 + 0.0005 * i)
            write_block(os.path.join(self.d, f"{pid}_dc.csv"), curve(k))
            open(os.path.join(self.d, f"{pid}.log"), "w").write("ok\n")

    def test_full_set_definitive_and_margin(self):
        self.fill()
        s = dc.summarise(dc.reduce_dir(self.d))
        self.assertTrue(s["definitive"])
        self.assertEqual((s["n_points"], s["n_resolved"]), (45, 45))
        self.assertAlmostEqual(s["margin_to_target_v"],
                               0.3 - s["worst_by_upper_bound"]["dropout_1pct_upper_v"])
        self.assertAlmostEqual(s["series_resistance_equivalent_ohm"], s["margin_to_target_v"] / 0.05)
        self.assertTrue(s["lower_bound_below_every_crossing"])

    def test_missing_point_blocks_definitive_claim(self):
        self.fill(skip="dcsweep_ss_125c_rbcs")
        s = dc.summarise(dc.reduce_dir(self.d))
        self.assertFalse(s["definitive"])
        self.assertEqual(s["n_points"], 45)
        self.assertEqual(s["status_counts"].get("malformed"), 1)
        self.assertNotIn("margin_to_target_v", s)

    def test_floor_limited_point_blocks_definitive_claim(self):
        self.fill(knees={"dcsweep_tt_27c_rtyp": 1.0})
        s = dc.summarise(dc.reduce_dir(self.d))
        self.assertFalse(s["definitive"])
        self.assertEqual(s["status_counts"].get("floor_limited_upper_bound"), 1)

    def test_fatal_log_blocks_point(self):
        self.fill()
        open(os.path.join(self.d, "dcsweep_tt_27c_rtyp.log"), "w").write("Error: no convergence\n")
        s = dc.summarise(dc.reduce_dir(self.d))
        self.assertFalse(s["definitive"])

    def test_expected_coordinates(self):
        ids = [c[3] for c in dc.coords()]
        self.assertEqual((len(ids), len(set(ids))), (45, 45))


if __name__ == "__main__":
    unittest.main()
