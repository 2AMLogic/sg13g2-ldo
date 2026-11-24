"""Tests for the testbench-local startup-ramp wrapper (issue #314, DR-0020).
No simulator, no network, no PDK install (a fake OSDI directory is staged).

The wrapper only counts if it REACHES the deck: the request body the batch
fleet simulates must `.include` core_with_ramp.spice. The negative control
re-plans without the wrapper redirect and shows the same check failing."""
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RAMP = os.path.abspath(os.path.join(HERE, "..", "ldo-cmos5l-startup-ramp"))
sys.path.insert(0, HERE)
import startup_campaign as sc  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = _load("gen_core_with_ramp", os.path.join(RAMP, "gen_core_with_ramp.py"))
rc = _load("ramp_campaign", os.path.join(RAMP, "ramp_campaign.py"))
CORE = os.path.join(sc.REPO, "design", "sg13cmos5l", "netlist", "ldo_core_cmos5l.spice")


def included_design(group_dir):
    """Resolve the design `.include` of a planned request body to a path."""
    body = open(os.path.join(group_dir, "tb.spice")).read()
    m = re.search(r'^\.include "([^"]*ldo_core[^"]*|[^"]*core_with_ramp[^"]*)"', body, re.M)
    return os.path.normpath(os.path.join(group_dir, m.group(1)))


def reaches_wrapper(group_dir):
    return included_design(group_dir) == os.path.normpath(rc.WRAPPER)


class Wrapper(unittest.TestCase):
    def test_committed_wrapper_is_the_generator_output(self):
        committed = open(rc.WRAPPER).read()
        self.assertEqual(committed, gen.derive(open(CORE).read()))

    def test_core_subckt_ports_and_reference_rewiring(self):
        w = open(rc.WRAPPER).read()
        self.assertIn(".subckt ldo_core_cmos5l VIN VOUT VSS VREF IBIAS EN", w)
        self.assertIn("Xamp FB VREFR EAOUT ", w)
        self.assertNotIn("Xamp FB VREF EAOUT", w)
        self.assertIn(".save v(xtop.vrefr)", w)
        # the committed core is untouched by construction: it has no ramp
        self.assertNotIn("VREFR", open(CORE).read())

    def test_fails_closed_on_unexpected_core(self):
        with self.assertRaises(SystemExit):
            gen.derive(".subckt ldo_core_cmos5l A B\n.ends\n")


class PlanReachesDeck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        pdk = os.path.join(self.tmp.name, "pdk")
        osdi = os.path.join(pdk, sc.PDK, "libs.tech", "ngspice", "osdi")
        os.makedirs(osdi)
        for n in sc.bb.OSDI_ORDER:
            open(os.path.join(osdi, f"{n}.osdi"), "w").close()
        self._env = os.environ.get("PDK_ROOT")
        os.environ["PDK_ROOT"] = pdk
        self._save = (sc.HERE, sc.DESIGN)
        sc.HERE = self.tmp.name

    def tearDown(self):
        sc.HERE, sc.DESIGN = self._save
        if self._env is None:
            os.environ.pop("PDK_ROOT", None)
        else:
            os.environ["PDK_ROOT"] = self._env
        self.tmp.cleanup()

    def _plan(self):
        sc.write_requests("t", rc.STAGE, rc.ramp_points())
        sd = sc.stage_dir("t", rc.STAGE)
        plan = json.load(open(os.path.join(sd, "plan.json")))
        return [os.path.join(sd, g["group"]) for g in plan["groups"]]

    def test_seven_points_and_every_request_includes_the_wrapper(self):
        self.assertEqual(len(rc.ramp_points()), 7)
        rc.use_wrapper()
        dirs = self._plan()
        self.assertEqual(len(dirs), 7)
        for gd in dirs:
            self.assertTrue(reaches_wrapper(gd), gd)

    def test_negative_control_unredirected_plan_does_not_reach_wrapper(self):
        sc.DESIGN = CORE            # what a plan WITHOUT the wrapper redirect does
        for gd in self._plan():
            self.assertFalse(reaches_wrapper(gd), gd)


def _snapshot(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            fp = os.path.join(d, f)
            out[os.path.relpath(fp, root)] = open(fp, "rb").read()
    return out


class PublishedRunIsProtected(PlanReachesDeck):
    """Retrying plan/submit/collect against an existing run must not touch it."""

    def test_retry_preserves_every_file_byte_for_byte(self):
        rc.use_wrapper()
        self._plan()
        sd = sc.stage_dir("t", rc.STAGE)
        for n, body in (("envelope.json", "{}"), ("klt-sim.stderr", "x")):
            open(os.path.join(sd, n), "w").write(body)
        rec = os.path.join(sc.HERE, "records")
        os.makedirs(rec)
        open(os.path.join(rec, "t-startup-ramp.csv"), "w").write("published\n")
        before = _snapshot(sc.HERE)
        a = type("A", (), {"rid": "t"})()
        for cmd in (rc.cmd_plan, rc.cmd_submit, rc.cmd_collect):
            self.assertEqual(cmd(a), 2, cmd.__name__)
        self.assertEqual(_snapshot(sc.HERE), before)

    def test_fresh_rid_is_not_refused(self):
        self.assertEqual(rc._existing_evidence("fresh", "plan"), [])
        self.assertEqual(rc._existing_evidence("fresh", "collect"), [])


class RampWindow(unittest.TestCase):
    def test_late_rise_is_not_reported_for_the_startup_window(self):
        # 0 V through 9 ms, 0.9 V at 9.3 ms: a re-enable ramp only
        t = [i * 1e-5 for i in range(1500)]
        v = [0.0 if x < 9e-3 else min(0.9, (x - 9e-3) / 300e-6 * 0.9) for x in t]
        self.assertIsNone(rc.ramp_from_series(t, v, *rc.START_WINDOW_S))
        got = rc.ramp_from_series(t, v, *rc.REEN_WINDOW_S)
        self.assertAlmostEqual(got, 300.0, delta=15.0)

    def test_ramp_inside_window(self):
        t = [i * 1e-5 for i in range(1500)]
        v = [0.0 if x < 1e-3 else min(0.9, (x - 1e-3) / 450e-6 * 0.9) for x in t]
        self.assertAlmostEqual(rc.ramp_from_series(t, v, *rc.START_WINDOW_S), 450.0, delta=15.0)


class ClauseStatuses(unittest.TestCase):
    ROW = {"load_ma": "1", "cout_nf": "1000", "start_peak_supply_current_a": "0.01",
           "start_pass": "True", "reen_pass": "False",
           "start_max_vsg_pass_v": "0.9", "reen_max_vsg_pass_v": "0.8"}

    def test_missing_rawfile_is_na_not_fail(self):
        st, *_ = rc.evaluate_row(self.ROW, False, None, None)
        self.assertEqual((st["b"], st["d"]), ("n/a", "n/a"))
        self.assertEqual((st["a"], st["c"]), ("FAIL", "ok"))

    def test_observed_failure_is_fail(self):
        st, *_ = rc.evaluate_row(self.ROW, True, 484.0, 484.0)
        self.assertEqual((st["b"], st["d"]), ("FAIL", "FAIL"))

    def test_unmeasurable_ramp_with_rawfile_is_fail(self):
        st, *_ = rc.evaluate_row(self.ROW, True, None, None)
        self.assertEqual((st["b"], st["d"]), ("FAIL", "FAIL"))

    def test_overall(self):
        na = {"a": "ok", "b": "n/a", "c": "ok", "d": "n/a"}
        self.assertEqual(rc.overall([na] * 7, 7), "INCONCLUSIVE")
        self.assertEqual(rc.overall([na] * 6 + [dict(na, a="FAIL")], 7), "REJECT")
        ok = dict.fromkeys("abcd", "ok")
        self.assertEqual(rc.overall([ok] * 7, 7), "CONFIRM")
        self.assertEqual(rc.overall([ok] * 6, 6), "INCONCLUSIVE")

    def test_published_record_prints_start_pass_and_rejects_without_rawfiles(self):
        import contextlib
        import io
        rid = "20261123-212501-9e332bb0"
        if not os.path.isfile(os.path.join(HERE, "records", f"{rid}-startup-ramp.csv")):
            self.skipTest("published record absent")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc.cmd_clauses(type("A", (), {"rid": rid})())
        out = buf.getvalue()
        self.assertIn("True/False FAIL", out)
        self.assertNotIn("fail/False", out)
        self.assertIn("Overall: REJECT", out)
        self.assertNotIn("n/a FAIL", out)


if __name__ == "__main__":
    unittest.main()
