"""Tests for startup_campaign.py planning logic (issue #69): grid size,
request grouping, load resistor mapping, binding-point selection. No
simulator or network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import startup_campaign as sc  # noqa: E402


class Plan(unittest.TestCase):
    def test_grid_is_135_unique_points_in_3_requests(self):
        pts = sc.grid_points()
        self.assertEqual(len(pts), 135)
        self.assertEqual(len({sc.point_id(p) for p in pts}), 135)
        groups = sc.build_groups(pts)
        self.assertEqual(len(groups), 15)
        self.assertEqual([len(g) for g in groups], [9] * 15)
        for g in groups:
            self.assertEqual(len({sc.section(p) for p in g}), 1)
            self.assertEqual(len({p['temp'] for p in g}), 3)
            self.assertEqual(len({p['vin'] for p in g}), 3)

    def test_load_resistor(self):
        self.assertEqual(sc.load_resistor("1"), "1800")
        self.assertEqual(sc.load_resistor("50"), "36")
        self.assertIsNone(sc.load_resistor("0"))

    def test_ext_is_8_per_binding_point(self):
        b = [dict(sc.NOMINAL), dict(sc.NOMINAL, mos="ss", temp=125)]
        ext = sc.ext_points(b)
        self.assertEqual(len(ext), 16)
        self.assertEqual(len({sc.point_id(p) for p in ext}), 16)
        self.assertEqual({p["load_ma"] for p in ext}, {"0", "50"})
        self.assertEqual({p["cout_nf"] for p in ext}, {330, 4700})
        self.assertEqual({p["esr_mohm"] for p in ext}, {0, 500})

    def test_halfstep_caps_timestep(self):
        h = sc.halfstep_points([dict(sc.NOMINAL)])
        self.assertEqual(h[0]["tmax_ns"], 500)
        self.assertEqual(sc.tran_args(500), "500n 15m 0 500n")
        self.assertEqual(sc.tran_args(1000), "1000n 15m 0 1000n")

    def test_render_body_has_no_placeholder(self):
        p = dict(sc.NOMINAL, esr_mohm=500, load_ma="50", vin=3.63)
        b = sc.render_body(p, "d.spice", "p.cir")
        self.assertNotIn("@@", b)
        self.assertIn("Rload VOUT 0 36", b)
        self.assertIn("Resr COUT_ESR 0 500e-3", b)
        self.assertIn("Vin VIN 0 dc 3.63", b)
        self.assertIn("pwl(0 0 1m 0 1.001m 1 7m 1 7.001m 0 9m 0 9.001m 1 15m 1)", b)
        b0 = sc.render_body(dict(sc.NOMINAL, load_ma="0"), "d.spice", "p.cir")
        self.assertNotIn("\nRload", b0)
        self.assertNotIn("Resr", b0)

    def test_binding_selection_dedupes_and_flags_nonpass(self):
        def row(mos, v, over, st, exc, off, verdict="pass"):
            return {"mos": mos, "temp": "27", "res": "typ", "vin": v, "verdict": verdict,
                    "start_overshoot_v": over, "start_settle_time_s": st,
                    "start_max_down_excursion_v": exc, "off_vout_max_v": off}
        rows = [row("tt", "3.30", "0.01", "0.001", "0", "0"),
                row("ff", "3.63", "0.30", "0.0005", "0.1", "0"),
                row("ss", "2.97", "0.02", "", "0", "0", verdict="insufficient")]
        b = sc.binding_points(rows)
        keys = [(x["point"]["mos"], x["point"]["vin"]) for x in b]
        self.assertEqual(keys, [("ff", 3.63), ("ss", 2.97)])  # unsettled ranks worst
        self.assertIn("peak overshoot", b[0]["why"])


if __name__ == "__main__":
    unittest.main()
