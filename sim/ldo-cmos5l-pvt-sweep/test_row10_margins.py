"""Tests and negative controls for row10_margins.py (DR-0014, issue #126).
stdlib only, no PDK, no simulator: reads the committed traces.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v
"""
import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ac_metrics as am  # noqa: E402
import row10_margins as rm  # noqa: E402


class Committed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = {ds: rm.build(ds) for ds in rm.DATASETS}

    def test_outputs_reproduce(self):
        for ds, files in self.out.items():
            d = os.path.join(rm.REPO, rm.SIM, "evidence", rm.DATASETS[ds]["record_id"])
            for name, data in files.items():
                with open(os.path.join(d, name), "rb") as fh:
                    self.assertEqual(fh.read(), data, f"{ds}/{name}")

    def test_issue_counts(self):
        leg = json.loads(self.out["legacy"]["row10-margins.json"])
        doe = json.loads(self.out["doe"]["row10-margins.json"])
        self.assertEqual(leg["summary_all"]["points"], 45)
        self.assertEqual(leg["subset"]["summary"]["points"], 15)     # multi-crossing legacy points
        self.assertEqual(doe["summary_all"]["points"], 536)
        self.assertEqual(doe["subset"]["summary"]["points"], 46)     # #64 `failed` rows
        # no committed trace bounds the sweep ceiling
        self.assertEqual(leg["summary_all"]["ceiling_bounded"], 0)
        self.assertEqual(doe["summary_all"]["ceiling_bounded"], 0)
        # the #64 README's per-corner miss tables (PM 77+41+49+43, GM 63+10+2+15)
        self.assertEqual(doe["summary_all"]["pm_verdicts"].get("fail"), 210)
        self.assertEqual(doe["summary_all"]["gm_verdicts"].get("fail"), 90)
        self.assertNotIn("pass", doe["summary_all"]["pm_verdicts"])
        self.assertNotIn("pass", doe["summary_all"]["gm_verdicts"])
        self.assertEqual(doe["subset"]["summary"]["gm_verdicts"], {"ambiguous": 46})


class CrossCheckNegativeControls(unittest.TestCase):
    PATH = os.path.join(HERE, "corners", "20261010-025634-60a3e81", "loopgain_ff_-40c_rwcs_ac.csv")
    ROW = {"n_0db_crossings": "2", "phase_margin_deg": None, "phase_margin_worst_deg": None,
           "n_gain_margin_crossings": "1", "gain_margin_db": None}

    def setUp(self):
        self.m = am.classify_margins(self.PATH)
        leg = am.loopgain_metrics(self.PATH)
        self.row = dict(self.ROW, phase_margin_deg=repr(leg["phase_margin_deg"]),
                        phase_margin_worst_deg=repr(leg["phase_margin_worst_deg"]),
                        gain_margin_db=repr(leg["gain_margin_db"]))

    def test_baseline_passes(self):
        rm.cross_check("legacy", self.row, self.m, "ctx")

    def test_crossing_count_disagreement(self):
        with self.assertRaisesRegex(rm.Row10Error, "0 dB crossings"):
            rm.cross_check("legacy", dict(self.row, n_0db_crossings="1"), self.m, "ctx")

    def test_first_pm_disagreement(self):
        with self.assertRaisesRegex(rm.Row10Error, "first-crossing PM"):
            rm.cross_check("legacy", dict(self.row, phase_margin_deg="70.0"), self.m, "ctx")

    def test_gm_disagreement(self):
        with self.assertRaisesRegex(rm.Row10Error, "first -180 deg GM"):
            rm.cross_check("legacy", dict(self.row, gain_margin_db="12.0"), self.m, "ctx")

    def test_recorded_miss_not_failed_is_refused(self):
        m = copy.deepcopy(self.m)
        m["zero_db_crossings"][0]["phase_deg"] = -140.0          # recorded-convention PM 40
        with self.assertRaisesRegex(rm.Row10Error, "recorded PM miss"):
            rm.cross_check("legacy", dict(self.row, phase_margin_deg="40.0",
                                          phase_margin_worst_deg="-162.48896933978210"),
                           dict(m, zero_db_crossings=m["zero_db_crossings"]), "ctx")

    def test_invalid_trace_refused(self):
        with self.assertRaisesRegex(rm.Row10Error, "missing, empty or invalid"):
            rm.cross_check("legacy", self.row, None, "ctx")


if __name__ == "__main__":
    unittest.main()
