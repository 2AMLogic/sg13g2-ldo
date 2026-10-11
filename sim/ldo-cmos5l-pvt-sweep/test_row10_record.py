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

RID = "20261011-051956-eda9285"


class Committed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = dict(rr.committed())
        cls.out = rr.build(RID, cls.found[RID])

    def test_discovers_only_wrapper_outputs(self):
        self.assertEqual(set(self.found), {RID})
        for cfg in rm.DATASETS.values():
            self.assertNotIn(cfg["record_id"], self.found)

    def test_outputs_reproduce(self):
        d = os.path.join(rm.REPO, rm.SIM, "evidence", RID)
        for name, data in self.out.items():
            with open(os.path.join(d, name), "rb") as fh:
                self.assertEqual(fh.read(), data, name)

    def test_shape_generate_py_expects(self):
        doc = json.loads(self.out["row10-margins.json"])
        self.assertEqual(doc["dataset"], "legacy")
        self.assertEqual(doc["record"]["csv"], f"{rm.SIM}/records/{RID}.csv")
        self.assertIn(rr.SELF, doc["classifier"])
        self.assertIn(f"{rm.SIM}/row10_margins.py", doc["classifier"])
        self.assertEqual(doc["summary_all"]["points"], 45)
        self.assertEqual(doc["subset"]["summary"]["points"], 15)
        self.assertEqual(doc["summary_all"]["ceiling_bounded"], 0)
        for r in self.out["row10-margins.csv"].decode().splitlines()[1:]:
            self.assertIn(f"/corners/{RID}/", r)

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

    def test_missing_record_fails_cli(self):
        self.assertEqual(rr.main(["--record", "19700101-000000-0000000"]), 1)


if __name__ == "__main__":
    unittest.main()
