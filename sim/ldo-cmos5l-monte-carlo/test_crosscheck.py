"""Offline tests for crosscheck.py (issue #56).
Run: python3 -m unittest sim/ldo-cmos5l-monte-carlo/test_crosscheck.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crosscheck as x  # noqa: E402


def draw(proc, idx, value, seed=None, supply=None, status="pass"):
    sup = supply or {}
    sid = "/".join(f"{v:.3f}V" for v in sup.values()) or "novdd"
    return {"corner_id": f"{proc}/{sid}/27C/mc{idx}", "process": proc, "supply_v": sup,
            "temperature_c": 27, "status": status,
            "measurements": [{"name": "vout_v", "value": value, "status": status}],
            "monte_carlo": {"sample_index": idx, "seed": 1000 + idx if seed is None else seed}}


def rep(corners):
    return {"measurements": [{"name": "vout_v", "limits": {"min": 1.764, "max": 1.836}}],
            "corners": corners}


class CrosscheckTests(unittest.TestCase):
    def setUp(self):
        self.mc = rep([draw("tt", i, 1.80 + 0.001 * i) for i in range(5)]
                      + [draw("ss", i, 1.79, seed=9000 + i) for i in range(5)])

    def test_reproduction_identical(self):
        r = x.reproduction(self.mc, rep([draw("tt", i, 1.80 + 0.001 * i) for i in range(3)]), "tt/novdd/27C")
        self.assertTrue(r["ok"])
        self.assertEqual(r["compared"], 3)

    def test_reproduction_detects_value_and_seed_drift(self):
        r = x.reproduction(self.mc, rep([draw("tt", 0, 1.8001), draw("tt", 1, 1.801, seed=1)]), "tt/novdd/27C")
        self.assertFalse(r["ok"])
        self.assertEqual(r["seed_mismatches"], 1)
        self.assertGreater(r["max_abs_diff_v"], x.REPRO_TOL_V)

    def test_reproduction_detects_missing_value(self):
        r = x.reproduction(self.mc, rep([draw("tt", 0, None, status="error")]), "tt/novdd/27C")
        self.assertFalse(r["ok"])

    def test_negctl_pairs_by_sample_index(self):
        neg = rep([draw("tt", i, 1.86 + 0.001 * i, supply={"vref": 0.93}) for i in range(5)])
        r = x.negctl_pairs(self.mc, neg, "tt/novdd/27C")
        self.assertEqual((r["pairs"], r["seed_mismatches"]), (5, 0))
        self.assertAlmostEqual(r["delta_mean_v"], 0.06)
        self.assertAlmostEqual(r["delta_stdev_v"], 0.0)

    def test_attribution_zero_spread_check(self):
        att = rep([draw("tt_nom", i, x.COMMITTED_TT_NOM_V) for i in range(3)]
                  + [draw("tt_mosmm", i, 1.80 + 0.002 * i) for i in range(3)]
                  + [draw("tt_resmm", i, 1.80 + 0.001 * i) for i in range(3)])
        c = x.attribution(att, self.mc, "tt/novdd/27C")["checks"]
        self.assertTrue(c["no_mismatch_zero_spread"])
        self.assertTrue(c["no_mismatch_matches_committed_corner"])
        self.assertAlmostEqual(c["mos_variance_share"], 0.8)

    def test_seeds_and_csv_rows_cover_every_draw(self):
        self.assertTrue(x.seeds_distinct(self.mc)["ok"])
        self.assertFalse(x.seeds_distinct(rep([draw("tt", 0, 1.8, seed=5), draw("tt", 1, 1.8, seed=5)]))["ok"])
        rows = list(x.draw_rows("mc", self.mc))
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]["value_state"], "ok")


if __name__ == "__main__":
    unittest.main()
