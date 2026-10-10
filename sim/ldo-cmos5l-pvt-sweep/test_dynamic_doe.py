"""Fixture tests for dynamic_doe.py (issue #64). stdlib only, no PDK, no
simulator.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v
"""
import cmath
import math
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dynamic_doe as d  # noqa: E402

FREQS = [10 ** (i / 20) for i in range(161)]  # 1 Hz .. 100 MHz, 20/dec


def op(l=1000, c=1000, e=0):
    return {"load_ua": l, "cout_nf": c, "esr_mohm": e}


def write_lg(path, a0_db=60.0, poles=(1e3, 1e5, 1e6), n=161):
    a0 = 10 ** (a0_db / 20)
    lines = []
    for f in FREQS[:n]:
        h = a0
        for p in poles:
            h /= complex(1, f / p)
        db = 20 * math.log10(abs(h))
        deg = math.degrees(cmath.phase(h))
        lines.append(f"{f:.8e} {db:.8e} {f:.8e} {deg:.8e}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_psrr(path, fn, n=161):
    with open(path, "w") as fh:
        fh.write("\n".join(
            f"{f:.8e} {fn(f):.8e}" for f in FREQS[:n]) + "\n")


def point(bench, o=None, corner=("ss", 125, "bcs")):
    o = o or op()
    return {"bench": bench, "point_id": d.point_id(bench, *corner, o),
            "corner": corner[0], "temp_c": corner[1], "res": corner[2],
            "op": o, "origin": "base"}


class Validation(unittest.TestCase):
    def test_rejects_negative_and_zero_cout(self):
        for args in [(-1, 1, 0), (0, -1, 0), (0, 1, -0.1), (0, 0, 0)]:
            with self.assertRaises(d.InvalidOperatingPoint, msg=args):
                d.make_op(*args)

    def test_rejects_garbage_and_fractional_base_units(self):
        for args in [("x", 1, 0), (0, "nan", 0), (0, 1, "inf"),
                     (0.0005, 1, 0), (0, 1.0004, 0), (0, 1, 0.0005)]:
            with self.assertRaises(d.InvalidOperatingPoint, msg=args):
                d.make_op(*args)

    def test_zero_load_and_zero_esr_explicit(self):
        o = d.make_op(0, 1, 0)
        self.assertEqual(o, op(0, 1000, 0))
        self.assertEqual(d.netlist_values(o),
                         {"load_a": "0", "cout_f": "1000n", "esr_ohm": "0"})

    def test_canonical_values_exact(self):
        self.assertEqual(d.make_op("0.5", "0.33", "0.25"), op(500, 330, 250))
        self.assertEqual(d.make_op(50, 4.7, 0.5), op(50000, 4700, 500))


class Matrix(unittest.TestCase):
    def test_counts_and_unique_ids(self):
        pts = d.plan()
        self.assertEqual(len(pts), 4 * 48 * 2)
        self.assertEqual(len({p["point_id"] for p in pts}), 384)
        self.assertEqual({(p["corner"], p["temp_c"], p["res"]) for p in pts},
                         {("ss", 125, "bcs"), ("ff", -40, "wcs"),
                          ("ss", 125, "wcs"), ("ff", 27, "bcs")})

    def test_ids_distinguish_all_axes_and_corner(self):
        ids = {d.point_id("psrr", "ss", 125, "bcs", op(l, c, e))
               for l in (1, 10, 100) for c in (1, 10, 100) for e in (1, 10, 100)}
        self.assertEqual(len(ids), 27)
        self.assertNotEqual(d.point_id("psrr", "ss", 125, "bcs", op()),
                            d.point_id("psrr", "ss", 125, "wcs", op()))

    def test_extra_points_and_collision_dedup(self):
        extra = [{"corner": "ss", "temp_c": 125, "res": "bcs", "op": op(500),
                  "reason": "t"}] * 2 + [
                 {"corner": "ss", "temp_c": 125, "res": "bcs", "op": op(),
                  "reason": "dup of base"}]
        self.assertEqual(len(d.plan(extra)), 384 + 2)

    def test_tsv_row_shape(self):
        for ln in d.plan_tsv(d.plan()).splitlines():
            self.assertEqual(len(ln.split("\t")), 8)


class Netlist(unittest.TestCase):
    def test_min_nominal_max_render(self):
        self.assertEqual(d.render_cout_esr(op(0, 330, 0)),
                         ["Iload VOUT 0 dc 0", "Cout VOUT 0 330n"])
        self.assertEqual(d.render_cout_esr(op(25000, 2200, 250)),
                         ["Iload VOUT 0 dc 25000e-6",
                          "Cout VOUT COUT_ESR 2200n", "Resr COUT_ESR 0 250e-3"])
        self.assertEqual(d.render_cout_esr(op(50000, 4700, 500))[2],
                         "Resr COUT_ESR 0 500e-3")

    def test_templates_use_placeholders(self):
        for b in d.BENCHES:
            t = open(os.path.join(HERE, "testbench",
                                  f"tb_{b}_cmos5l.spice.tmpl")).read()
            for ph in ("@@LOAD_A@@", "@@COUT_F@@", "@@COUT_BOTTOM@@",
                       "@@ESR_LINE@@"):
                self.assertEqual(sum(1 for ln in t.splitlines()
                                     if ph in ln and not ln.startswith("*")), 1)

    def test_generator_renders_corner_temp_resistor(self):
        """run_sweep.sh --doe-generate path is exercised by the PDK-bearing
        --check-env; here assert the plan carries the corner identity."""
        p = next(x for x in d.plan() if x["corner"] == "ff"
                 and x["temp_c"] == -40 and x["op"] == op(50000, 4700, 500))
        self.assertIn("ff_-40c_rwcs", p["point_id"])
        self.assertTrue(p["point_id"].endswith("i50000ua_c4700nf_e500mohm"))
        row = d.plan_tsv([p]).split("\t")
        self.assertEqual(row[2:5], ["mos_ff", "res_wcs", "-40"])


class Parsers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def put_lg(self, o=None, **k):
        p = point("loopgain", o)
        write_lg(os.path.join(self.tmp, p["point_id"] + "_ac.csv"), **k)
        return p

    def put_ps(self, fn, o=None, n=161):
        p = point("psrr", o)
        write_psrr(os.path.join(self.tmp, p["point_id"] + "_ac.csv"), fn, n)
        return p

    def test_pm_gm_known_crossings(self):
        p = self.put_lg()
        m, why = d.parse_point(self.tmp, p)
        self.assertIsNone(why)
        # independent reference: bisect |L|=1 on the analytic function
        def L(f):
            h = 10 ** 3.0
            for q in (1e3, 1e5, 1e6):
                h /= complex(1, f / q)
            return h
        lo, hi = 1.0, 1e8
        for _ in range(200):
            mid = math.sqrt(lo * hi)
            lo, hi = (mid, hi) if abs(L(mid)) > 1 else (lo, mid)
        pm = 180 + math.degrees(cmath.phase(L(lo)))
        self.assertAlmostEqual(m["phase_margin_deg"], pm, delta=0.5)
        lo, hi = 1.0, 1e8
        for _ in range(200):
            mid = math.sqrt(lo * hi)
            ph = -sum(math.degrees(math.atan(mid / q)) for q in (1e3, 1e5, 1e6))
            lo, hi = (mid, hi) if ph > -180 else (lo, mid)
        gm = -20 * math.log10(abs(L(lo)))
        self.assertAlmostEqual(m["gain_margin_db"], gm, delta=0.5)

    def test_no_unity_crossover_is_failure(self):
        p = self.put_lg(a0_db=-20.0)
        m, why = d.parse_point(self.tmp, p)
        self.assertIn("no unity-gain crossover", why)

    def test_no_gm_crossing_is_failure(self):
        p = self.put_lg(poles=(1e3,))  # one pole: phase never reaches -180
        m, why = d.parse_point(self.tmp, p)
        self.assertIn("gain margin unmeasured", why)

    def test_truncated_and_missing(self):
        p = self.put_lg(n=100)
        self.assertIn("truncated", d.parse_point(self.tmp, p)[1])
        q = point("psrr", op(0))
        self.assertIn("missing", d.parse_point(self.tmp, q)[1])

    def test_psrr_selection(self):
        fn = lambda f: 40 + 5 * math.log10(f)  # 55 dB@1k, 65 dB@100k
        p = self.put_ps(fn)
        m, why = d.parse_point(self.tmp, p)
        self.assertIsNone(why)
        self.assertAlmostEqual(m["psrr_db_1khz"], 55.0, places=3)
        self.assertAlmostEqual(m["psrr_db_100khz"], 65.0, places=3)

    def test_psrr_truncated(self):
        p = self.put_ps(lambda f: 50.0, n=40)
        self.assertIn("truncated", d.parse_point(self.tmp, p)[1])

    def test_missing_bench_never_complete(self):
        pts = [point("loopgain"), point("psrr")]
        self.put_lg()  # psrr absent
        rows = d.build_rows(self.tmp, pts)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertIn("psrr: missing", rows[0]["failures"])
        self.assertFalse(d.completeness(rows, pts)["complete"])

    def test_complete_when_all_present(self):
        pts = [point("loopgain"), point("psrr")]
        self.put_lg()
        self.put_ps(lambda f: 55.0)
        rows = d.build_rows(self.tmp, pts)
        self.assertTrue(d.completeness(rows, pts)["complete"])

    def test_incomplete_matrix_rows(self):
        pts = [point("loopgain"), point("psrr"),
               point("loopgain", op(0)), point("psrr", op(0))]
        self.put_lg()
        self.put_ps(lambda f: 55.0)
        rows = d.build_rows(self.tmp, pts)
        c = d.completeness(rows[:1], pts)  # a row dropped entirely
        self.assertFalse(c["complete"])
        self.assertEqual(c["expected_operating_points"], 2)


def mkrow(l, c, e, corner=("ss", 125, "res_bcs"), **m):
    base = {"phase_margin_deg": 60.0, "gain_margin_db": 20.0,
            "psrr_db_1khz": 60.0, "psrr_db_100khz": 30.0}
    base.update(m)
    return {"corner": corner[0], "temp_c": corner[1], "res_section": corner[2],
            "load_ua": l, "cout_nf": c, "esr_mohm": e, "status": "ok",
            "failures": "", **base}


class Summary(unittest.TestCase):
    def test_extrema_coordinate_and_targets(self):
        rows = [mkrow(0, 330, 0, phase_margin_deg=70),
                mkrow(50000, 4700, 500, phase_margin_deg=44.0),
                mkrow(1000, 1000, 0, psrr_db_1khz=49.0)]
        e = d.extrema(rows)
        self.assertIn("load=50mA cout=4.7uF esr=500mohm",
                      e["phase_margin_deg"]["coord"])
        self.assertFalse(e["phase_margin_deg"]["meets_target"])
        self.assertFalse(e["psrr_db_1khz"]["meets_target"])
        self.assertTrue(e["gain_margin_db"]["meets_target"])
        self.assertEqual(len(d.target_failures(rows)), 2)

    def test_failed_rows_excluded_from_extrema(self):
        bad = mkrow(0, 330, 0, phase_margin_deg=1.0)
        bad["status"] = "failed"
        e = d.extrema([bad, mkrow(1000, 1000, 0)])
        self.assertEqual(e["phase_margin_deg"]["value"], 60.0)

    def test_legacy_tolerance(self):
        rows = []
        legacy = []
        for c in d.CORNERS:
            cr = (c[0], c[1], f"res_{c[2]}")
            rows.append(mkrow(1000, 1000, 0, cr))
            legacy.append({"corner": c[0], "temp_c": str(c[1]),
                           "res_section": cr[2], "phase_margin_deg": "60.05",
                           "gain_margin_db": "20.0", "psrr_db_1khz": "60.0",
                           "psrr_db_100khz": "30.0"})
        self.assertTrue(all(r["ok"] for r in d.compare_legacy(rows, legacy)))
        legacy[0]["gain_margin_db"] = "20.11"
        res = d.compare_legacy(rows, legacy)
        self.assertFalse(res[0]["ok"])
        self.assertIn("tolerance miss", res[0]["note"])
        self.assertFalse(d.compare_legacy([], legacy)[1]["ok"])  # missing = miss


class Refinement(unittest.TestCase):
    def slice_rows(self, values, metric="phase_margin_deg"):
        """Cout slice with the given metric values over the 4 Cout levels."""
        return [mkrow(1000, c, 0, **{metric: v})
                for c, v in zip(d.COUT_LEVELS_NF, values)]

    def reqs(self, rows):
        r, ev = d.refinement_requests(rows)
        return [x for x in r if not x.get("unrefinable")], ev

    def test_monotone_endpoint_bounded_requests_nothing(self):
        r, ev = self.reqs(self.slice_rows([50, 55, 60, 70]))
        self.assertEqual(r, [])
        self.assertTrue(all(e["triggered"] == 0 for e in ev))

    def test_interior_worst_requests_both_adjacent_midpoints(self):
        r, _ = self.reqs(self.slice_rows([70, 60, 50, 65]))
        mids = sorted(x["cout_nf"] for x in r)
        self.assertEqual(mids, [1600, 3450])  # (1000,2200) and (2200,4700)

    def test_non_monotonic_requests(self):
        r, _ = self.reqs(self.slice_rows([60, 52, 58, 56]))
        self.assertTrue(r)
        self.assertTrue(any("non-monotonic" in x["reason"] or
                            "interior worst" in x["reason"] for x in r))

    def test_target_failure_at_endpoint(self):
        r, _ = self.reqs(self.slice_rows([40, 50, 60, 70]))
        self.assertEqual([x["cout_nf"] for x in r], [665])  # (330,1000)
        self.assertIn("target failure", r[0]["reason"])

    def test_requests_keep_other_axes_and_corner(self):
        rows = [mkrow(25000, c, 250, ("ff", -40, "res_wcs"),
                      phase_margin_deg=v)
                for c, v in zip(d.COUT_LEVELS_NF, [70, 60, 50, 65])]
        r, _ = self.reqs(rows)
        for x in r:
            self.assertEqual((x["corner"], x["temp_c"], x["res"]),
                             ("ff", -40, "wcs"))
            self.assertEqual((x["load_ua"], x["esr_mohm"]), (25000, 250))

    def test_odd_interval_reported_unrefinable_not_dropped(self):
        rows = [mkrow(1000, 1000, 1, phase_margin_deg=30),
                mkrow(1000, 1000, 2, phase_margin_deg=60)]
        r, _ = d.refinement_requests(rows)
        self.assertTrue(any(x.get("unrefinable") for x in r))

    def test_refined_requests_validate_and_plan(self):
        r, _ = self.reqs(self.slice_rows([40, 50, 60, 70]))
        extra = [{"corner": x["corner"], "temp_c": x["temp_c"], "res": x["res"],
                  "op": {a: x[a] for a in d.AXES}, "reason": x["reason"]}
                 for x in r]
        self.assertEqual(len(d.plan(extra)), 386)


if __name__ == "__main__":
    unittest.main()
