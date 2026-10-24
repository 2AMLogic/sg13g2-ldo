"""Tests and negative controls for row10_record.py (DR-0014 on another 45-point
record, issue #89). stdlib only, no PDK, no simulator: reads the committed traces.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import row10_margins as rm  # noqa: E402
import row10_record as rr  # noqa: E402

OLD_RID = "20261011-051956-eda9285"   # #89, 100 MHz ceiling; historical, still reproduces
RID = "20261011-070111-5391c68"       # #128, 10 GHz ceiling
NEW_PIN_RID = "20261012-060932-c53f0177"  # #155, same grid re-run on the re-stamped PDK


class Committed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = dict(rr.committed())
        cls.out = rr.build(RID, cls.found[RID])
        cls.old = rr.build(OLD_RID, cls.found[OLD_RID])

    def test_discovers_only_wrapper_outputs(self):
        self.assertEqual(set(self.found), {OLD_RID, RID, NEW_PIN_RID})
        for cfg in rm.DATASETS.values():
            self.assertNotIn(cfg["record_id"], self.found)

    def test_outputs_reproduce(self):
        for rid, out in ((RID, self.out), (OLD_RID, self.old)):
            d = os.path.join(rm.REPO, rm.SIM, "evidence", rid)
            for name, data in out.items():
                with open(os.path.join(d, name), "rb") as fh:
                    self.assertEqual(fh.read(), data, name)

    def test_extended_ceiling_result_is_honest(self):
        """#128: 10 GHz sweep, 201 rows per trace; the loop gain plateaus above
        0 dB, so nothing is bounded and nothing is scored as a pass or a fail."""
        doc = json.loads(self.out["row10-margins.json"])
        s = doc["summary_all"]
        self.assertEqual((s["pm_verdicts"], s["gm_verdicts"]), ({"ambiguous": 45}, {"ambiguous": 45}))
        self.assertEqual((s["pm_reasons"], s["gm_reasons"]),
                         ({"ceiling_unbounded": 45}, {"ceiling_unbounded": 45}))
        self.assertEqual(s["ceiling_bounded"], 0)
        self.assertGreater(s["ceiling_gain_db_range"]["min"], -10.0)
        self.assertEqual(s["low_end_ok"], 45)
        self.assertEqual(doc["bounds"], {"pm_deg": 45.0, "gm_db": 10.0, "ceiling_floor_db": -10.0})
        for line in self.out["row10-margins.csv"].decode().splitlines()[1:]:
            trace = line.split(",")[-2]
            with open(os.path.join(rm.REPO, trace)) as fh:
                rows = [ln.split() for ln in fh if ln.strip()]
            self.assertEqual(len(rows), 201, trace)
            self.assertAlmostEqual(float(rows[-1][0]) / 1e10, 1.0, places=6, msg=trace)

    def test_old_record_unchanged_in_meaning(self):
        doc = json.loads(self.old["row10-margins.json"])
        self.assertEqual(doc["subset"]["summary"]["points"], 15)

    def test_shape_generate_py_expects(self):
        doc = json.loads(self.out["row10-margins.json"])
        self.assertEqual(doc["dataset"], "legacy")
        self.assertEqual(doc["record"]["csv"], f"{rm.SIM}/records/{RID}.csv")
        self.assertIn(rr.SELF, doc["classifier"])
        self.assertIn(f"{rm.SIM}/row10_margins.py", doc["classifier"])
        self.assertEqual(doc["summary_all"]["points"], 45)
        self.assertEqual(doc["subset"]["summary"]["points"], 45)   # every point has two 0 dB crossings
        self.assertEqual(doc["summary_all"]["ceiling_bounded"], 0)
        for r in self.out["row10-margins.csv"].decode().splitlines()[1:]:
            self.assertIn(f"/corners/{RID}/", r)

    def test_new_pin_classification_matches_old_pin(self):
        """#155: the re-stamped-PDK re-run's classification is committed and
        reproduces; its summary equals the old-pin record's, point for point
        (the two records' CSVs and raw traces are byte-identical)."""
        new = rr.build(NEW_PIN_RID, self.found[NEW_PIN_RID])
        d = os.path.join(rm.REPO, rm.SIM, "evidence", NEW_PIN_RID)
        for name, data in new.items():
            with open(os.path.join(d, name), "rb") as fh:
                self.assertEqual(fh.read(), data, name)
        a, b = json.loads(new["row10-margins.json"]), json.loads(self.out["row10-margins.json"])
        self.assertEqual(a["summary_all"], b["summary_all"])
        self.assertEqual(a["subset"]["summary"], b["subset"]["summary"])
        strip = lambda out, rid: out["row10-margins.csv"].decode().replace(rid, "RID")
        self.assertEqual(strip(new, NEW_PIN_RID), strip(self.out, RID))

    def test_legacy_dataset_restored(self):
        self.assertEqual(rm.DATASETS["legacy"]["record_id"], "20261010-025634-60a3e81")


class NegativeControls(unittest.TestCase):
    def test_wrong_record_pin_refused(self):
        with self.assertRaises(rm.Row10Error):
            rr.build(RID, "0" * 64)
        self.assertEqual(rm.DATASETS["legacy"]["record_id"], "20261010-025634-60a3e81")

    def test_builtin_dataset_refused(self):
        with self.assertRaises(rm.Row10Error):
            rr.config(rm.DATASETS["legacy"]["record_id"], rm.DATASETS["legacy"]["record_sha256"])

    def test_truncated_trace_cannot_reproduce_its_record(self):
        """A trace cut below the record's second 0 dB crossing disagrees with
        the record minted from it: hard error, nothing is repaired."""
        import shutil
        import tempfile
        import ac_metrics as am
        src = os.path.join(rm.REPO, rm.SIM, "corners", RID, "loopgain_tt_27c_rtyp_ac.csv")
        tmp = tempfile.mkdtemp()
        try:
            cut = os.path.join(tmp, "t.csv")
            with open(src) as fh:
                rows = fh.read().splitlines()
            with open(cut, "w") as fh:
                fh.write("\n".join(rows[:141]) + "\n")   # stops at 10 MHz
            m = am.classify_margins(cut)
            rec = {"n_0db_crossings": "2", "phase_margin_deg": "0", "phase_margin_worst_deg": "0",
                   "gain_margin_db": "", "n_gain_margin_crossings": "1"}
            with self.assertRaises(rm.Row10Error):
                rm.cross_check("legacy", rec, m, "truncated")
        finally:
            shutil.rmtree(tmp)

    def test_missing_record_fails_cli(self):
        self.assertEqual(rr.main(["--record", "19700101-000000-0000000"]), 1)


if __name__ == "__main__":
    unittest.main()
