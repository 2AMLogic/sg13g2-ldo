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


DECK = """* tb for {pid}
.lib "/pdk/cornerMOShv.lib" mos_{mos}
.lib "/pdk/cornerRES.lib" res_{res}
.lib "/pdk/cornerCAP.lib" cap_typ
.options temp={temp} tnom=27
.include "/design/ldo.spice"
Vin VIN 0 dc 3.3 ac 1
Iload VOUT 0 dc {load}
Cout VOUT {bottom} {cout}
{esr}
Xtop VIN VOUT 0 VREF IBIAS VIN ldo_core_cmos5l
.control
pre_osdi /o/psp103.osdi
pre_osdi /o/psp103_nqs.osdi
pre_osdi /o/mosvar.osdi
pre_osdi /o/r3_cmc.osdi
pre_osdi /o/cap_cmomi.osdi
pre_osdi /o/cap_cmomf.osdi
ac dec 20 1 100meg
let psrr_db = -db(v(vout)/v(vin))
wrdata /x/{pid}_ac.csv psrr_db
.endc
.end
"""
VARIANT_RE = r"^(Iload|Cout|Resr) "


class VariantLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def deck(self, mos, temp, res, load, cout, esr):
        pid = f"psrr_dyn_{mos}_{temp}c_r{res}_{load}_{cout}_{esr}"
        bottom, esr_line = ("0", "* ESR=0") if esr == "0" else \
            ("COUT_ESR", f"Resr COUT_ESR 0 {esr}")
        path = os.path.join(self.tmp, pid + ".spice")
        with open(path, "w") as f:
            f.write(DECK.format(pid=pid, mos=mos, res=res, temp=temp,
                                load=load, cout=cout, bottom=bottom,
                                esr=esr_line))
        return pid, path

    def points(self, variant_re):
        out = []
        for mos, temp, res in DOE_CORNERS:
            for load, cout, esr in [("0", "330n", "0"), ("50000e-6", "4700n", "500e-3")]:
                pid, path = self.deck(mos, temp, res, load, cout, esr)
                out.append((pid, bb.parse_deck(path, variant_re)))
        return out

    def test_without_variant_lines_each_op_is_its_own_request(self):
        self.assertEqual(len(bb.plan_groups(self.points(None))), 2)

    def test_variant_lines_share_one_request_one_corner_per_point(self):
        pts = self.points(VARIANT_RE)
        groups = bb.plan_groups(pts)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(len(g["members"]), 8)
        names = {bb.corner_name(p) for _, p in pts}
        self.assertEqual(len(names), 8)  # unique per (model bundle, variant)
        for _, p in pts:
            self.assertNotIn("Iload", p["body"])
            self.assertNotIn("Cout", p["body"])
            self.assertIn("Xtop", p["body"])
        gdir = bb.write_group(g, self.tmp, "/osdi", "/pre.cir")
        lib = open(os.path.join(gdir, "corners.lib")).read()
        # each section: its model cards, then exactly its own variant lines
        for _, p in pts:
            name = bb.corner_name(p)
            sec = lib.split(f".lib {name}\n", 1)[1].split(f".endl {name}\n", 1)[0]
            self.assertEqual(sec.splitlines()[3:], p["variant"])
        self.assertIn("Resr COUT_ESR 0 500e-3", lib)
        req = json.load(open(os.path.join(gdir, "request.json")))
        n = len(req["corners"]["process"]) * len(req["corners"]["temperature_c"])
        self.assertEqual(n - len(req["exclude"]), 8)

    def test_variant_regex_that_matches_nothing_is_an_error(self):
        pid, path = self.deck("ss", 125, "bcs", "0", "330n", "0")
        with self.assertRaises(bb.BackendError):
            bb.parse_deck(path, r"^Rnothing ")


if __name__ == "__main__":
    unittest.main()
