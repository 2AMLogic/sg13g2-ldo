"""Tests for the loop-gain AC ceiling contract (issue #128). stdlib only; no
simulator, no PDK, nothing submitted.

    python3 -m unittest sim/ldo-cmos5l-pvt-sweep/test_ac_sweep.py -v
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ac_sweep as acs  # noqa: E402
import batch_backend as bb  # noqa: E402

LG_TMPL = os.path.join(HERE, "testbench", "tb_loopgain_cmos5l.spice.tmpl")
PSRR_TMPL = os.path.join(HERE, "testbench", "tb_psrr_cmos5l.spice.tmpl")


def write_trace(path, ceiling, rows=None, last_scale=1.0):
    n = acs.expected_rows(ceiling) if rows is None else rows
    with open(path, "w") as fh:
        for i in range(n):
            f = 10 ** (i / acs.POINTS_PER_DECADE)
            if i == n - 1:
                f *= last_scale
            fh.write(f" {f:.8e} -1.0e+00 {f:.8e} -9.0e+01 \n")


class Contract(unittest.TestCase):
    def test_default_is_historical(self):
        self.assertEqual(acs.canonical("100meg"), "100meg")
        self.assertEqual(acs.expected_rows("100meg"), 161)
        self.assertEqual(acs.analysis_line("100meg"), "ac dec 20 1 100meg")

    def test_extended(self):
        for spelling in ("10g", "10G", "1e10", "10000meg", "10000000k"):
            self.assertEqual(acs.expected_rows(spelling), 201, spelling)
            self.assertEqual(acs.canonical(spelling), "1e10", spelling)
        self.assertEqual(acs.analysis_line("10g"), "ac dec 20 1 1e10")
        self.assertEqual(acs.expected_rows("1t"), 241)

    def test_invalid(self):
        for bad in ("", "fast", "-1g", "0", "50meg", "3g", "1e13", "100", "1", "1x", "1e", "10 g;"):
            with self.assertRaises(acs.AcSweepError, msg=bad):
                acs.expected_rows(bad)

    def test_template_has_exactly_the_placeholder_and_agrees_with_contract(self):
        text = open(LG_TMPL).read()
        self.assertEqual(re.findall(r"^ac dec .*$", text, re.M), ["ac dec 20 1 @@LG_AC_MAX@@"])
        self.assertIn("ac dec 20 1 100meg", open(PSRR_TMPL).read())   # psrr bench unchanged
        self.assertEqual(acs.POINTS_PER_DECADE, 20)
        self.assertEqual(acs.FLOOR_HZ, 1.0)


class Traces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = os.path.join(self.tmp, "t.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_complete_trace_ok(self):
        for c in ("100meg", "10g"):
            write_trace(self.f, c)
            self.assertEqual(acs.check_trace(self.f, c), [], c)

    def test_truncated_trace_fails(self):
        write_trace(self.f, "10g", rows=200)
        self.assertTrue(acs.check_trace(self.f, "10g"))

    def test_default_length_trace_against_extended_ceiling_fails(self):
        write_trace(self.f, "100meg")
        self.assertTrue(any("expected 201" in b for b in acs.check_trace(self.f, "10g")))

    def test_expected_count_drift_fails(self):
        write_trace(self.f, "10g")
        self.assertTrue(acs.check_trace(self.f, "100meg"))

    def test_wrong_range_with_right_count_fails(self):
        write_trace(self.f, "10g", last_scale=0.5)
        self.assertTrue(any("last frequency" in b for b in acs.check_trace(self.f, "10g")))

    def test_missing_trace_fails(self):
        self.assertTrue(acs.check_trace(os.path.join(self.tmp, "nope.csv"), "10g"))

    def test_cli_exit_codes(self):
        write_trace(self.f, "10g", rows=5)
        py = [sys.executable, os.path.join(HERE, "ac_sweep.py")]
        self.assertEqual(subprocess.run(py + ["check-trace", self.f, "10g"], capture_output=True).returncode, 1)
        write_trace(self.f, "10g")
        self.assertEqual(subprocess.run(py + ["check-trace", self.f, "10g"], capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(py + ["rows", "7"], capture_output=True).returncode, 2)


class Runner(unittest.TestCase):
    """run_sweep.sh validates the ceiling before it touches the PDK or fleet."""

    def run_sweep(self, *args, env=None):
        e = dict(os.environ, **(env or {}))
        e.pop("SWEEP_LOOPGAIN_AC_MAX", None) if env is None else None
        return subprocess.run(["bash", os.path.join(HERE, "run_sweep.sh"), *args],
                              capture_output=True, text=True, env=e)

    def test_invalid_ceiling_flag_rejected(self):
        r = self.run_sweep("--loopgain-ac-max=50meg")
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid --loopgain-ac-max", r.stderr)

    def test_invalid_ceiling_env_rejected(self):
        r = self.run_sweep(env={"SWEEP_LOOPGAIN_AC_MAX": "banana"})
        self.assertEqual(r.returncode, 2)

    def test_extended_ceiling_refused_for_doe(self):
        r = self.run_sweep("--doe-generate", "--loopgain-ac-max=10g")
        self.assertEqual(r.returncode, 2)

    def test_topology_guard_still_runs_with_extended_ceiling(self):
        r = self.run_sweep("--check-topology-guard", "--loopgain-ac-max=10g")
        self.assertEqual(r.returncode, 0, r.stderr)


class BatchRequest(unittest.TestCase):
    """The configured sweep reaches the klt sim request; other benches do not change."""

    def render(self, tmpl, ceiling, tmp):
        text = open(tmpl).read()
        text = text.replace("@@LG_AC_MAX@@", acs.canonical(ceiling))
        subs = {"@@PDK_ROOT@@": "/pdk", "@@PDK@@": "ihp-sg13cmos5l", "@@OSDI_DIR@@": "/o",
                "@@MOS_SECTION@@": "mos_tt", "@@RES_SECTION@@": "res_typ", "@@CAP_SECTION@@": "cap_typ",
                "@@TEMP@@": "27", "@@CC_W@@": "nominal", "@@LOAD_A@@": "0.001", "@@COUT_F@@": "1u",
                "@@COUT_BOTTOM@@": "0", "@@ESR_LINE@@": "* ESR=0",
                "@@DESIGN_NETLIST@@": "/d/ldo_core_cmos5l.spice",
                "@@AC_CSV@@": "/x/p_ac.csv", "@@DC_CSV@@": "/x/p_dc.csv"}
        for k, v in subs.items():
            text = text.replace(k, v)
        self.assertNotIn("@@", text)
        path = os.path.join(tmp, os.path.basename(tmpl) + ".spice")
        open(path, "w").write(text)
        return path

    def test_analysis_reaches_request(self):
        tmp = tempfile.mkdtemp()
        try:
            for ceiling, want in (("100meg", "dec 20 1 100meg"), ("10g", "dec 20 1 1e10")):
                p = bb.parse_deck(self.render(LG_TMPL, ceiling, tmp))
                self.assertEqual(p["analysis"], ("ac", want))
            p = bb.parse_deck(self.render(PSRR_TMPL, "10g", tmp))
            self.assertEqual(p["analysis"], ("ac", "dec 20 1 100meg"))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
