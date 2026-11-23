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


if __name__ == "__main__":
    unittest.main()
