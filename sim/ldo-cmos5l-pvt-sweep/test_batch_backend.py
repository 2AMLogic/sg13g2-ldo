"""Fixture tests for batch_backend.py's request grouping (issue #64).
stdlib only; nothing is submitted.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch_backend as bb  # noqa: E402


def parsed(mos, res, temp, body="BODY\n"):
    return {"body": body, "temp": float(temp),
            "sections": [("cornerMOShv.lib", f"mos_{mos}"),
                         ("cornerRES.lib", f"res_{res}"),
                         ("cornerCAP.lib", "cap_typ")],
            "analysis": ("ac", "dec 20 1 100meg"), "lets": [],
            "wrdata": ["psrr_db"]}


DOE_CORNERS = [("ss", 125, "bcs"), ("ff", -40, "wcs"), ("ss", 125, "wcs"),
               ("ff", 27, "bcs")]


class Grouping(unittest.TestCase):
    def test_sparse_corners_one_request_with_exclude(self):
        pts = [(f"psrr_dyn_{m}_{t}c_r{r}_x", parsed(m, r, t))
               for m, t, r in DOE_CORNERS]
        groups = bb.plan_groups(pts)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(len(g["members"]), 4)
        # 4 sections x 3 temps = 12, minus the 4 members
        self.assertEqual(len(g["exclude"]), 8)
        members = {(bb.section_name(p["sections"]), p["temp"])
                   for _, p in g["members"]}
        self.assertFalse(members & set(g["exclude"]))

    def test_full_cross_product_has_no_exclude(self):
        pts = [(f"loopgain_{m}_{t}c_r{r}", parsed(m, r, t))
               for m in ("tt", "ss") for t in (-40, 125) for r in ("typ",)]
        groups = bb.plan_groups(pts)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["exclude"], [])

    def test_different_bodies_never_share_a_request(self):
        pts = [("psrr_a", parsed("ss", "bcs", 125, "Cout VOUT 0 330n\n")),
               ("psrr_b", parsed("ss", "bcs", 125, "Cout VOUT 0 1000n\n"))]
        self.assertEqual(len(bb.plan_groups(pts)), 2)

    def test_request_json_carries_exclude(self):
        pts = [(f"psrr_dyn_{m}_{t}c_r{r}_x", parsed(m, r, t))
               for m, t, r in DOE_CORNERS]
        g = bb.plan_groups(pts)[0]
        tmp = tempfile.mkdtemp()
        try:
            gdir = bb.write_group(g, tmp, "/osdi", "/pre.cir")
            req = json.load(open(os.path.join(gdir, "request.json")))
            self.assertEqual(req["corners"]["temperature_c"], [-40, 27, 125])
            self.assertEqual(len(req["exclude"]), 8)
            for e in req["exclude"]:
                self.assertEqual(set(e), {"process", "temperature_c"})
                self.assertIsInstance(e["temperature_c"], int)
            # what klt would expand: exactly the four member corners remain
            expanded = {(p, t) for p in req["corners"]["process"]
                        for t in req["corners"]["temperature_c"]} - \
                {(e["process"], e["temperature_c"]) for e in req["exclude"]}
            self.assertEqual(len(expanded), 4)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
