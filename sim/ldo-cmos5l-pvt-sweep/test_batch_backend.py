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

    def test_killed_client_missing_report_retried_then_reported(self):
        # A killed klt client can leave report.json unwritten. That is treated
        # as a cap refusal: re-submitted (to the fleet) within the budget, and
        # if it never succeeds the exit code comes back as a plain failure
        # (named per group), never an exception, never a local fallback.
        calls = []

        def once(gdir):
            calls.append(1)
            open(os.path.join(gdir, "klt-sim.stderr"), "w").write("killed\n")
            return 137
        bb.submit_once = once
        self.assertEqual(self.run_submit(100), 137)
        self.assertGreater(len(calls), 1)


class ReuseReport(unittest.TestCase):
    """--reuse-work (issue #89): only a byte-identical request with a complete
    earlier report is reused; anything else is submitted again."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.old, self.new = os.path.join(self.root, "old"), os.path.join(self.root, "new")
        # Shared inputs the deck names by path: the design netlist (which
        # itself includes a sub-file), a model card and an OSDI binary.
        self.design = os.path.join(self.root, "design.spice")
        self.sub = os.path.join(self.root, "sub.spice")
        self.model = os.path.join(self.root, "models.lib")
        self.osdi = os.path.join(self.root, "psp103.osdi")
        open(self.design, "w").write(f'.include "{self.sub}"\nR2 b 0 2k\n')
        open(self.sub, "w").write("R3 c 0 3k\n")
        open(self.model, "w").write(".lib tt\n.endl tt\n")
        open(self.osdi, "wb").write(b"osdi-binary")
        for w in (self.old, self.new):
            os.makedirs(os.path.join(w, "g00"))
            pre = os.path.join(w, "osdi-preamble.cir")
            open(pre, "w").write("* preamble\n")
            open(os.path.join(w, "g00", "request.json"), "w").write('{"netlist": "tb.spice"}\n')
            open(os.path.join(w, "g00", "corners.lib"), "w").write(f'.lib a\n.lib "{self.model}" tt\n.endl a\n')
            open(os.path.join(w, "g00", "tb.spice"), "w").write(
                f'.include "{pre}"\n.include "{self.design}"\nR1 a 0 1k\n')
            self.inventory(w)
        self.raw = os.path.join(self.old, "g00", "c.raw")
        open(self.raw, "w").write("raw")
        self.write_report([{"artifacts": {"raw": self.raw}}, {"artifacts": {"raw": self.raw}}])

    def inventory(self, w):
        bb.write_inventory(os.path.join(w, "g00"), {"options": {"osdi_preload": [self.osdi]}},
                           skip={os.path.normpath(os.path.join(w, "osdi-preamble.cir"))})

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_report(self, corners):
        open(os.path.join(self.old, "g00", "report.json"), "w").write(json.dumps({"corners": corners}))

    def reuse(self, n=2):
        return bb.reusable_report(os.path.join(self.old, "g00"), os.path.join(self.new, "g00"),
                                  self.old, self.new, n)

    def test_identical_complete_request_is_reused(self):
        self.assertEqual(self.reuse(), os.path.join(self.old, "g00", "report.json"))

    def test_changed_body_is_not_reused(self):
        open(os.path.join(self.new, "g00", "tb.spice"), "a").write("R2 a 0 2k\n")
        self.assertIsNone(self.reuse())

    def test_changed_request_or_corner_lib_is_not_reused(self):
        open(os.path.join(self.new, "g00", "corners.lib"), "a").write("* x\n")
        self.assertIsNone(self.reuse())

    def test_incomplete_or_empty_report_is_not_reused(self):
        self.assertIsNone(self.reuse(n=3))
        open(os.path.join(self.old, "g00", "report.json"), "w").write("")
        self.assertIsNone(self.reuse())

    def test_inventory_covers_the_whole_include_closure(self):
        inv = json.load(open(os.path.join(self.new, "g00", bb.INVENTORY)))
        self.assertEqual(sorted(inv), sorted([self.design, self.sub, self.model, self.osdi]))
        self.assertTrue(all(len(h) == 64 for h in inv.values()))

    def test_in_place_edit_of_an_included_input_is_not_reused(self):
        """The four compared text files stay byte-identical; only a file they
        name by path changes. Each kind of input is a negative control."""
        for path, data in ((self.design, 'R2 b 0 9k\n'), (self.sub, "R3 c 0 9k\n"),
                           (self.model, ".lib tt\n* x\n.endl tt\n")):
            with self.subTest(path=os.path.basename(path)):
                orig = open(path).read()
                open(path, "w").write(data)
                self.inventory(self.new)  # the new group is written from current bytes
                self.assertIsNone(self.reuse())
                open(path, "w").write(orig)
                self.inventory(self.new)
                self.assertIsNotNone(self.reuse())

    def test_replaced_osdi_binary_is_not_reused(self):
        open(self.osdi, "wb").write(b"another-binary")
        self.inventory(self.new)
        self.assertIsNone(self.reuse())

    def test_missing_original_inventory_fails_closed(self):
        os.remove(os.path.join(self.old, "g00", bb.INVENTORY))
        self.assertIsNone(self.reuse())

    def test_unresolved_include_fails_closed(self):
        os.remove(self.sub)
        for w in (self.old, self.new):
            self.inventory(w)
        self.assertIsNone(self.reuse())

    def test_missing_rawfile_is_not_reused(self):
        os.remove(self.raw)
        self.assertIsNone(self.reuse())


LG2V_LETS = ["let vfb_re = real(v(fb))",
             "let vfb_im = imag(v(fb))",
             "let vfbamp_re = real(v(fbamp))",
             "let vfbamp_im = imag(v(fbamp))"]
LG2I_LETS = ["let il_re = real(i(vmeas))",
             "let il_im = imag(i(vmeas))"]


def lg2_deck(pid, lets, wrdata_vectors):
    return f"""* tb for {pid}
.lib "/pdk/cornerMOShv.lib" mos_tt
.lib "/pdk/cornerRES.lib" res_typ
.lib "/pdk/cornerCAP.lib" cap_typ
.options temp=27 tnom=27
.include "/design/ldo.spice"
Vin VIN 0 dc 3.30
.control
pre_osdi /o/psp103.osdi
pre_osdi /o/psp103_nqs.osdi
pre_osdi /o/mosvar.osdi
pre_osdi /o/r3_cmc.osdi
pre_osdi /o/cap_cmomi.osdi
pre_osdi /o/cap_cmomf.osdi
op
echo "LOOPGAIN_VOUT_OP 1.8"
ac dec 20 1 1e10
{chr(10).join(lets)}
wrdata /x/{pid}_ac.csv {wrdata_vectors}
.endc
.end
"""


def complex_rawfile(probes, points):
    """A minimal ASCII ngspice AC rawfile: freq + the named complex probes."""
    names = ["freq"] + [p for p, _ in probes]
    lines = ["Title: fixture", "Date: fixture", "Plotname: AC Analysis",
             "Flags: complex", f"No. Variables: {len(names)}",
             f"No. Points: {len(points)}", "Variables:"]
    for k, n in enumerate(names):
        kind = "frequency" if k == 0 else "node-or-branch"
        lines.append(f"\t{k}\t{n}\t{kind}")
    lines.append("Values:")
    for i, row in enumerate(points):        # row = [freq, v1, v2, ...] complex
        lines.append(f"{i}\t{row[0].real:.8e},{row[0].imag:.8e}")
        for z in row[1:]:
            lines.append(f"\t{z.real:.8e},{z.imag:.8e}")
    return "\n".join(lines) + "\n"


class TwoInjectionExport(unittest.TestCase):
    """issue #135: the raw-complex-export benches reconstruct their wrdata
    columns from the rawfile's complex vectors, and refuse anything else."""

    @staticmethod
    def _data(temps=(27,)):
        fb = [complex(2.0, 0.1), complex(1.0, -0.5)]
        fbamp = [complex(-0.02, 0.003), complex(0.01, 0.02)]
        imeas = [complex(-0.9999, 1e-5), complex(-0.5, -0.25)]
        freqs = [complex(1.0, 0.0), complex(10.0, 0.0)]
        return (["freq", "v(fb)", "v(fbamp)", "vmeas#branch"],
                {"freq": freqs, "v(fb)": fb, "v(fbamp)": fbamp,
                 "vmeas#branch": imeas}, True)

    def test_voltage_bench_exports_re_and_im_columns(self):
        names, data, cplx = self._data()
        with tempfile.NamedTemporaryFile("w", suffix=".spice", delete=False) as fh:
            fh.write(lg2_deck("loopgain2v_tt_27c_rtyp", LG2V_LETS,
                              "vfb_re vfb_im vfbamp_re vfbamp_im"))
            deck = fh.name
        try:
            parsed = bb.parse_deck(deck)
            rows = bb.wrdata_rows("loopgain2v", parsed, names, data, cplx)
        finally:
            os.remove(deck)
        self.assertEqual(len(rows), 2)
        for r, f, fb, fbamp in zip(rows, data["freq"], data["v(fb)"],
                                   data["v(fbamp)"]):
            vals = [float(x) for x in r.split()]
            self.assertEqual(len(vals), 8)
            self.assertAlmostEqual(vals[0], f.real)
            self.assertAlmostEqual(vals[1], fb.real, places=7)
            self.assertAlmostEqual(vals[3], fb.imag, places=7)
            self.assertAlmostEqual(vals[5], fbamp.real, places=7)
            self.assertAlmostEqual(vals[7], fbamp.imag, places=7)

    def test_current_bench_exports_the_ammeter_pair(self):
        names, data, cplx = self._data()
        with tempfile.NamedTemporaryFile("w", suffix=".spice", delete=False) as fh:
            fh.write(lg2_deck("loopgain2i_tt_27c_rtyp", LG2I_LETS,
                              "il_re il_im"))
            deck = fh.name
        try:
            parsed = bb.parse_deck(deck)
            rows = bb.wrdata_rows("loopgain2i", parsed, names, data, cplx)
        finally:
            os.remove(deck)
        for r, z in zip(rows, data["vmeas#branch"]):
            vals = [float(x) for x in r.split()]
            self.assertEqual(len(vals), 4)
            self.assertAlmostEqual(vals[1], z.real, places=7)
            self.assertAlmostEqual(vals[3], z.imag, places=7)

    def test_voltage_bench_rejects_unknown_control(self):
        names, data, cplx = self._data()
        with tempfile.NamedTemporaryFile("w", suffix=".spice", delete=False) as fh:
            fh.write(lg2_deck("loopgain2v_tt_27c_rtyp", LG2V_LETS[:2] + LG2I_LETS,
                              "vfb_re vfb_im il_re il_im"))
            deck = fh.name
        try:
            parsed = bb.parse_deck(deck)
            with self.assertRaisesRegex(bb.BackendError, "differs from the known template"):
                bb.wrdata_rows("loopgain2v", parsed, names, data, cplx)
        finally:
            os.remove(deck)

    def test_voltage_bench_rejects_a_real_rawfile(self):
        names, data, _ = self._data()
        with tempfile.NamedTemporaryFile("w", suffix=".spice", delete=False) as fh:
            fh.write(lg2_deck("loopgain2v_tt_27c_rtyp", LG2V_LETS,
                              "vfb_re vfb_im vfbamp_re vfbamp_im"))
            deck = fh.name
        try:
            parsed = bb.parse_deck(deck)
            with self.assertRaisesRegex(bb.BackendError, "not complex"):
                bb.wrdata_rows("loopgain2v", parsed, names, data, False)
        finally:
            os.remove(deck)

    def test_current_bench_rejects_a_missing_probe(self):
        names, data, cplx = self._data()
        del data["vmeas#branch"]
        with tempfile.NamedTemporaryFile("w", suffix=".spice", delete=False) as fh:
            fh.write(lg2_deck("loopgain2i_tt_27c_rtyp", LG2I_LETS, "il_re il_im"))
            deck = fh.name
        try:
            parsed = bb.parse_deck(deck)
            with self.assertRaisesRegex(bb.BackendError, "not in rawfile"):
                bb.wrdata_rows("loopgain2i", parsed, names, data, cplx)
        finally:
            os.remove(deck)

    def test_bench_of_the_new_prefixes(self):
        self.assertEqual(bb.bench_of("loopgain2v_tt_27c_rtyp"), "loopgain2v")
        self.assertEqual(bb.bench_of("loopgain2i_ss_-40c_rwcs"), "loopgain2i")
        self.assertEqual(bb.bench_of("loopgain_ctl_ff_125c_rbcs"), "loopgain")
        with self.assertRaises(bb.BackendError):
            bb.bench_of("loopgain2x_tt_27c_rtyp")


if __name__ == "__main__":
    unittest.main()
