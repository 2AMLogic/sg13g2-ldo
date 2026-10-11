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

    def test_max_points_splits_into_bounded_requests(self):
        pts = self.points(VARIANT_RE)
        groups = bb.plan_groups(pts, max_points=3)
        self.assertEqual([len(g["members"]) for g in groups], [3, 3, 2])
        seen = [pid for g in groups for pid, _ in g["members"]]
        self.assertEqual(sorted(seen), sorted(pid for pid, _ in pts))
        for g in groups:
            procs = {bb.corner_name(p) for _, p in g["members"]}
            temps = {p["temp"] for _, p in g["members"]}
            self.assertEqual(len(procs) * len(temps) - len(g["exclude"]),
                             len(g["members"]))

    def test_variant_regex_that_matches_nothing_is_an_error(self):
        pid, path = self.deck("ss", 125, "bcs", "0", "330n", "0")
        with self.assertRaises(bb.BackendError):
            bb.parse_deck(path, r"^Rnothing ")


class CapRetry(unittest.TestCase):
    """A fleet concurrency-cap refusal is re-submitted (to the fleet) within
    a budget; any other failure returns at once."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = bb.submit_once

    def tearDown(self):
        bb.submit_once = self.orig
        shutil.rmtree(self.tmp)

    def fake(self, outcomes):
        calls = []

        def once(gdir):
            rc, text = outcomes[len(calls)]
            calls.append(rc)
            open(os.path.join(gdir, "report.json"), "w").write(text)
            open(os.path.join(gdir, "klt-sim.stderr"), "w").write("")
            return rc
        bb.submit_once = once
        return calls

    def run_submit(self, budget):
        t = [0.0]
        return bb.submit(self.tmp, budget, sleep=lambda s: t.__setitem__(0, t[0] + s),
                         clock=lambda: t[0])

    REFUSED = '{"error": {"message": "8 instance(s) already running + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8"}}'

    def test_cap_refusal_retried_then_succeeds(self):
        calls = self.fake([(1, self.REFUSED), (1, self.REFUSED), (0, "{}")])
        self.assertEqual(self.run_submit(3600), 0)
        self.assertEqual(calls, [1, 1, 0])
        self.assertEqual(len(open(os.path.join(self.tmp, "cap-retries.log")).readlines()), 2)

    def test_budget_exhausted_returns_failure(self):
        calls = self.fake([(1, self.REFUSED)] * 50)
        self.assertEqual(self.run_submit(100), 1)
        self.assertLessEqual(len(calls), 3)

    def test_other_failure_not_retried(self):
        calls = self.fake([(1, '{"error": {"message": "upload failed"}}')])
        self.assertEqual(self.run_submit(3600), 1)
        self.assertEqual(calls, [1])


class ReuseReport(unittest.TestCase):
    """--reuse-work (issue #89): only a byte-identical request, whose input
    bytes (design netlist, model include closure, OSDI binaries) still match
    a verified inventory, with a complete earlier report is reused; anything
    else is submitted again."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.old, self.new = os.path.join(self.root, "old"), os.path.join(self.root, "new")
        # Shared inputs referenced BY PATH from the request files, as the real
        # decks reference the design netlist, the PDK models and the OSDI dir.
        self.design = os.path.join(self.root, "design", "core.spice")
        self.models = os.path.join(self.root, "models")
        self.osdi = os.path.join(self.root, "osdi")
        for d in (os.path.dirname(self.design), self.models, self.osdi):
            os.makedirs(d)
        self.put(self.design, ".subckt core a b\nR1 a b 1k\n.ends\n")
        self.put(os.path.join(self.models, "corner.lib"),
                 ".LIB a\n  .include sub_mod.lib\n.ENDL a\n")
        self.sub = os.path.join(self.models, "sub_mod.lib")
        self.put(self.sub, ".model r1 r\n")
        for n in bb.OSDI_ORDER:
            self.put(os.path.join(self.osdi, f"{n}.osdi"), f"osdi {n}")
        for w in (self.old, self.new):
            os.makedirs(os.path.join(w, "g00"))
            self.put(os.path.join(w, "osdi-preamble.cir"), "* preamble\n")
            self.put(os.path.join(w, "g00", "request.json"), '{"netlist": "tb.spice"}\n')
            self.put(os.path.join(w, "g00", "corners.lib"),
                     f'.lib a\n.lib "{self.models}/corner.lib" a\n.endl a\n')
            self.put(os.path.join(w, "g00", "tb.spice"),
                     f'.include "{w}/osdi-preamble.cir"\n.include "{self.design}"\nX1 a 0 core\n')
        self.raw = os.path.join(self.old, "g00", "c.raw")
        self.put(self.raw, "raw")
        self.write_report([{"artifacts": {"raw": self.raw}}, {"artifacts": {"raw": self.raw}}])
        # The earlier run: inventory written with the request, verified once
        # its report came back. The new run: inventory written with the request.
        self.inventory(self.old)
        self.assertTrue(bb.verify_inputs(os.path.join(self.old, "g00")))
        self.inventory(self.new)

    def tearDown(self):
        shutil.rmtree(self.root)

    @staticmethod
    def put(path, text, mode="w"):
        with open(path, mode) as f:
            f.write(text)

    def inventory(self, w):
        gdir = os.path.join(w, "g00")
        bb.write_inventory(gdir, bb.group_inventory(gdir, self.osdi, os.path.join(w, "osdi-preamble.cir")),
                           verified=False)

    def write_report(self, corners):
        self.put(os.path.join(self.old, "g00", "report.json"), json.dumps({"corners": corners}))

    def reuse(self, n=2):
        return bb.reusable_report(os.path.join(self.old, "g00"), os.path.join(self.new, "g00"),
                                  self.old, self.new, n)

    def compared_text(self):
        """The four files reuse compared before the review fix, normalised the
        way reusable_report normalises them."""
        out = []
        for w in (self.old, self.new):
            t = []
            for fn in ("request.json", "corners.lib", "tb.spice"):
                t.append(open(os.path.join(w, "g00", fn)).read().replace(w, "W"))
            t.append(open(os.path.join(w, "osdi-preamble.cir")).read())
            out.append(t)
        return out

    def test_inventory_covers_design_models_and_osdi(self):
        files = bb.read_inventory(os.path.join(self.old, "g00"))["files"]
        self.assertIn(self.design, files)
        self.assertIn(os.path.join(self.models, "corner.lib"), files)
        self.assertIn(self.sub, files)   # nested .include of a model library
        for n in bb.OSDI_ORDER:
            self.assertIn(os.path.join(self.osdi, f"{n}.osdi"), files)
        self.assertNotIn(os.path.join(self.old, "osdi-preamble.cir"), files)
        self.assertTrue(all(files.values()))

    def test_identical_complete_request_is_reused(self):
        self.assertEqual(self.reuse(), os.path.join(self.old, "g00", "report.json"))

    def test_design_netlist_changed_in_place_is_not_reused(self):
        # Negative control (review of PR #131): the netlist changes at the
        # same path; every text file the old check compared stays identical.
        before = self.compared_text()
        self.put(self.design, ".subckt core a b\nR1 a b 2k\n.ends\n")
        self.inventory(self.new)
        after = self.compared_text()
        self.assertEqual(before, after)
        self.assertEqual(after[0], after[1])
        self.assertIsNone(self.reuse())

    def test_design_netlist_changed_after_new_inventory_is_not_reused(self):
        self.put(self.design, "* edited\n", mode="a")
        self.assertIsNone(self.reuse())

    def test_nested_model_include_changed_is_not_reused(self):
        self.put(self.sub, ".model r1 r rsh=2\n")
        self.inventory(self.new)
        self.assertIsNone(self.reuse())

    def test_osdi_binary_changed_is_not_reused(self):
        self.put(os.path.join(self.osdi, "psp103.osdi"), "rebuilt")
        self.inventory(self.new)
        self.assertIsNone(self.reuse())

    def test_missing_old_inventory_fails_closed(self):
        os.remove(os.path.join(self.old, "g00", bb.INPUTS_FILE))
        self.assertIsNone(self.reuse())

    def test_unverified_old_inventory_fails_closed(self):
        self.inventory(self.old)   # written with the request, never verified
        self.assertIsNone(self.reuse())

    def test_unreadable_old_inventory_fails_closed(self):
        self.put(os.path.join(self.old, "g00", bb.INPUTS_FILE), "{not json")
        self.assertIsNone(self.reuse())

    def test_missing_referenced_file_fails_closed(self):
        os.remove(self.sub)
        self.inventory(self.new)
        self.assertIsNone(bb.read_inventory(os.path.join(self.new, "g00"))["files"][self.sub])
        self.assertIsNone(self.reuse())

    def test_changed_closure_is_not_reused(self):
        self.put(os.path.join(self.models, "corner.lib"),
                 ".LIB a\n  .include sub_mod.lib\n  .include extra.lib\n.ENDL a\n")
        self.put(os.path.join(self.models, "extra.lib"), "* extra\n")
        self.inventory(self.new)
        self.assertIsNone(self.reuse())

    def test_input_changed_in_flight_is_not_verified(self):
        gdir = os.path.join(self.new, "g00")
        self.put(self.design, "* edited while in flight\n", mode="a")
        self.assertFalse(bb.verify_inputs(gdir))
        self.assertFalse(bb.read_inventory(gdir)["verified_after_report"])

    def test_changed_body_is_not_reused(self):
        self.put(os.path.join(self.new, "g00", "tb.spice"), "R2 a 0 2k\n", mode="a")
        self.assertIsNone(self.reuse())

    def test_changed_request_or_corner_lib_is_not_reused(self):
        self.put(os.path.join(self.new, "g00", "corners.lib"), "* x\n", mode="a")
        self.assertIsNone(self.reuse())

    def test_incomplete_or_empty_report_is_not_reused(self):
        self.assertIsNone(self.reuse(n=3))
        self.put(os.path.join(self.old, "g00", "report.json"), "")
        self.assertIsNone(self.reuse())

    def test_missing_rawfile_is_not_reused(self):
        os.remove(self.raw)
        self.assertIsNone(self.reuse())


if __name__ == "__main__":
    unittest.main()
