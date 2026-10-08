"""Fixture tests for item5_evidence.py (issue #55). stdlib only, no PDK.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import item5_evidence as ev  # noqa: E402

VINS = [round(2.00 + 0.01 * i, 2) for i in range(164)]
LOADS = ev.LOADS_A


def write_grid(path, vout_fn, iq=20e-6, blocks=5, drop_last=0):
    """Synthetic wrdata grid: Vin fast, Iload slow; i(vin) = -(Iload + iq)."""
    lines = []
    for load in LOADS[:blocks]:
        for vin in VINS:
            vo = vout_fn(vin, load)
            row = [vin, vin, vin, vo, vin, -(load + iq), vin, 3e-6]
            lines.append(" ".join(f"{x:.8e}" for x in row))
    if drop_last:
        lines = lines[:-drop_last]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def regulated(vin, load):
    return 1.8


def dropping(floor_v):
    """Regulated until vin < floor_v, then VOUT collapses with Vin."""
    return lambda vin, load: 1.8 if vin >= floor_v else 1.8 - 3.0 * (floor_v - vin)


class Analyse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._repo = ev.REPO
        ev.REPO = self.tmp  # analyse_point resolves relative paths against REPO

    def tearDown(self):
        ev.REPO = self._repo
        shutil.rmtree(self.tmp)

    def grid(self, name, *a, **k):
        write_grid(os.path.join(self.tmp, name), *a, **k)
        return ev.analyse_point(name)

    def test_full_load_iq_excludes_load_current(self):
        a = self.grid("g.csv", regulated, iq=23.4e-6)
        self.assertTrue(a["valid"])
        self.assertAlmostEqual(a["iq_by_load_a"]["0mA"], 23.4e-6, delta=1e-9)
        self.assertAlmostEqual(a["iq_by_load_a"]["50mA"], 23.4e-6, delta=1e-9)
        self.assertTrue(a["iq_full_valid"])

    def test_floor_limited_dropout_is_an_upper_bound_not_a_crossing(self):
        a = self.grid("g.csv", regulated)
        self.assertEqual(a["dropout_status"], "floor_limited_upper_bound")
        self.assertAlmostEqual(a["dropout_legacy_v"], 0.2, places=6)

    def test_resolved_crossing(self):
        a = self.grid("g.csv", dropping(2.05))
        self.assertEqual(a["dropout_status"], "resolved_crossing")
        self.assertGreater(a["dropout_legacy_v"], 0.2)
        self.assertLess(a["dropout_legacy_v"], 0.3)

    def test_never_in_regulation_is_not_reported_as_a_pass(self):
        a = self.grid("g.csv", lambda vin, load: 1.5)
        self.assertEqual(a["dropout_status"], "never_in_regulation")
        self.assertIsNone(a["dropout_legacy_v"])
        self.assertFalse(a["iq_full_valid"])
        self.assertFalse(any(a["line_valid_by_load"].values()))

    def test_out_of_regulation_end_point_invalidates_line_and_load_reg(self):
        # At 50 mA the output sags below 1 % at Vin = 2.97 V only.
        def fn(vin, load):
            return 1.7 if (load == 0.05 and abs(vin - 2.97) < 1e-6) else 1.8
        a = self.grid("g.csv", fn)
        self.assertFalse(a["line_valid_by_load"]["50mA"])
        self.assertTrue(a["line_valid_by_load"]["0mA"])
        self.assertFalse(a["load_reg_valid_by_vin"][2.97])
        self.assertTrue(a["load_reg_valid_by_vin"][3.63])

    def test_loaded_line_and_load_regulation_values(self):
        a = self.grid("g.csv", lambda vin, load: 1.8 + 0.001 * (vin - 3.3) - 0.01 * load)
        self.assertAlmostEqual(a["line_mv_per_v_by_load"]["25mA"], 1.0, places=6)
        # (V0 - V50)/V0 * 100 with V50 lower by 0.5 mV
        self.assertAlmostEqual(a["load_reg_pct_by_vin"][3.30], 0.0005 / 1.8 * 100, places=6)

    def test_truncated_grid_is_invalid_and_stays_in_accounting(self):
        a = self.grid("g.csv", regulated, drop_last=5)
        self.assertFalse(a["valid"])
        self.assertIn("rows", a["grid_problems"])
        text = ev.csv_text({("tt", 27, "res_typ"): a})
        self.assertIn("grid_invalid", text)
        self.assertEqual(len(text.strip().split("\n")), 2)

    def test_missing_block_is_invalid(self):
        a = self.grid("g.csv", regulated, blocks=4)
        self.assertFalse(a["valid"])

    def test_missing_file_is_invalid_not_an_exception(self):
        self.assertFalse(ev.analyse_point("nope.csv")["valid"])

    def test_extreme_counts_invalid_points(self):
        good = self.grid("g.csv", regulated)
        bad = self.grid("b.csv", regulated, drop_last=3)
        r = ev.extreme({("a", 1, "x"): good, ("b", 1, "x"): bad},
                       lambda a: a["iq_by_load_a"]["0mA"])
        self.assertEqual((r["n_points"], r["n_valid"], r["n_invalid"]), (2, 1, 1))


class Committed(unittest.TestCase):
    """Run against the committed record: the extracted parser must reproduce
    the record CSV and the inventory must keep the DR-0007 statuses."""

    @classmethod
    def setUpClass(cls):
        import csv
        cls.points = {(c, t, r): ev.analyse_point(p) for c, t, r, p in ev.point_files()}
        with open(os.path.join(ev.REPO, ev.RECORD_CSV)) as f:
            cls.rows = list(csv.DictReader(f))

    def test_45_points_all_valid_and_reproduce_record(self):
        self.assertEqual(len(self.points), 45)
        self.assertTrue(all(a["valid"] for a in self.points.values()))
        self.assertEqual(ev.reproduce_record(self.points, self.rows), [])

    def test_inventory_has_ten_rows_and_only_row_4_ratified(self):
        inv = ev.build_inventory(self.points, self.rows, [])
        self.assertEqual([r["id"] for r in inv], list(range(1, 11)))
        self.assertEqual([r["id"] for r in inv if r["status"] == "ratified"], [4])
        for r in inv:
            if r["status"] == "open":
                self.assertEqual(r["gate"], "none")
        self.assertIn("NOT closed", inv[3]["gate"])

    def test_dropout_status_accounting(self):
        counts = {}
        for a in self.points.values():
            counts[a["dropout_status"]] = counts.get(a["dropout_status"], 0) + 1
        self.assertEqual(counts, {"floor_limited_upper_bound": 36, "resolved_crossing": 9})

    def test_negative_control_perturbed_raw_grid_fails_reproduction(self):
        c, t, r, p = next(ev.point_files())
        with open(os.path.join(ev.REPO, p)) as f:
            text = f.read()
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, os.path.dirname(p)))
            # corrupt: scale the no-load Vout column of the first block
            lines = text.split("\n")
            parts = lines[130].split()
            parts[3] = "1.70000000e+00"
            lines[130] = " ".join(parts)
            with open(os.path.join(tmp, p), "w") as f:
                f.write("\n".join(lines))
            saved, ev.REPO = ev.REPO, tmp
            try:
                pts = {(c, t, r): ev.analyse_point(p)}
            finally:
                ev.REPO = saved
            self.assertNotEqual(ev.reproduce_record(pts, self.rows), [])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
