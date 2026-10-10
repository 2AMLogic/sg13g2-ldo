"""Offline tests for the --check-env output validation (issue #91).

Drives the real decision path (sim/tools/preflight.sh: preflight_bench_ok)
with a stub `ngspice` on PATH, so no PDK or simulator is needed. Run:
    python3 -m unittest discover -s sim/tools -p 'test_*.py' -v
"""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent
SIM = TOOLS.parent
PREFLIGHT = TOOLS / "preflight.sh"


def rows(n, ncols, v=1.5):
    return "".join(" ".join(f"{v + i:.8e}" for _ in range(ncols)) + " \n" for i in range(n))


class Harness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = pathlib.Path(self._td.name)
        (self.tmp / "bin").mkdir()
        (self.tmp / "tb.spice").write_text("* stub\n")

    def run_bench(self, stub_body, *vargs, exit_code=0, log_text=""):
        """stub_body: shell run by the stub ngspice (cwd-independent, may write
        files). Returns CompletedProcess of preflight_bench_ok."""
        stub = self.tmp / "bin" / "ngspice"
        stub.write_text(f"#!/usr/bin/env bash\n{stub_body}\n"
                        f"printf %b {log_text!r}\nexit {exit_code}\n")
        stub.chmod(0o755)
        env = dict(os.environ, PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}")
        cmd = ['source "$1"; shift; preflight_bench_ok bench "$@"']
        return subprocess.run(
            ["bash", "-c", cmd[0], "x", str(PREFLIGHT), str(self.tmp / "tb.spice"),
             str(self.tmp / "bench.log"), *vargs],
            env=env, capture_output=True, text=True)

    def write_cmd(self, name, content):
        p = self.tmp / name
        # Heredoc-free: stub copies a pre-made file.
        src = self.tmp / (name + ".src")
        src.write_text(content)
        return p, f"cp {src} {p}"


class WrdataGate(Harness):
    def test_valid_passes(self):
        p, cmd = self.write_cmd("o.csv", rows(5, 4))
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK for bench", r.stdout)

    def test_zero_exit_no_outputs_fails(self):
        r = self.run_bench("true", "--wrdata", f"{self.tmp / 'o.csv'}:4:5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not written", r.stderr)

    def test_stale_file_does_not_satisfy(self):
        p, _ = self.write_cmd("o.csv", rows(5, 4))
        r = self.run_bench("true", "--wrdata", f"{p}:4:5")
        self.assertNotEqual(r.returncode, 0)

    def test_empty_fails(self):
        p, cmd = self.write_cmd("o.csv", "")
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty", r.stderr)

    def test_truncated_rows_fails(self):
        p, cmd = self.write_cmd("o.csv", rows(3, 4))
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("truncated", r.stderr)

    def test_truncated_last_line_fails(self):
        p, cmd = self.write_cmd("o.csv", rows(4, 4) + "1.0e+00 2.0e+00\n")
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("columns", r.stderr)

    def test_malformed_fails(self):
        p, cmd = self.write_cmd("o.csv", rows(4, 4) + "a b c d\n")
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("non-numeric", r.stderr)

    def test_nonfinite_fails(self):
        for bad in ("nan", "inf", "-inf"):
            with self.subTest(bad=bad):
                p, cmd = self.write_cmd("o.csv", rows(4, 4) + f"1.0 {bad} 1.0 1.0\n")
                r = self.run_bench(cmd, "--wrdata", f"{p}:4:5")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("nonfinite", r.stderr)

    def test_nonzero_exit_fails_even_with_valid_output(self):
        p, cmd = self.write_cmd("o.csv", rows(5, 4))
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5", exit_code=1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nonzero", r.stderr)

    def test_fatal_log_fails_even_with_valid_output(self):
        p, cmd = self.write_cmd("o.csv", rows(5, 4))
        r = self.run_bench(cmd, "--wrdata", f"{p}:4:5",
                           log_text="Unable to find definition of model x\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fatal pattern", r.stderr)

    def test_both_wrdata_and_marker(self):
        p, cmd = self.write_cmd("o.csv", rows(5, 4))
        args = ("--wrdata", f"{p}:4:5", "--marker", "LOOPGAIN_VOUT_OP")
        ok = self.run_bench(cmd, *args, log_text="LOOPGAIN_VOUT_OP 1.80018\n")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        bad = self.run_bench(cmd, *args)
        self.assertNotEqual(bad.returncode, 0)


class StressMarkers(Harness):
    NAMES = ("STRESS_ID", "STRESS_VSG", "STRESS_VDS", "STRESS_VDG")
    ARGS = tuple(x for n in NAMES for x in ("--marker", n))

    def log(self, **over):
        vals = {"STRESS_ID": "0.000399839", "STRESS_VSG": "3.63",
                "STRESS_VDS": "-3.63", "STRESS_VDG": "0"}
        vals.update(over)
        return "".join(f"{k} {v}\n" for k, v in vals.items() if v is not None)

    def test_valid_passes(self):
        r = self.run_bench("true", *self.ARGS, log_text=self.log())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_markers_fails(self):
        r = self.run_bench("true", *self.ARGS)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("STRESS_ID missing", r.stderr)

    def test_each_missing_marker_fails(self):
        for n in self.NAMES:
            with self.subTest(n=n):
                r = self.run_bench("true", *self.ARGS, log_text=self.log(**{n: None}))
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(f"{n} missing", r.stderr)

    def test_nonfinite_or_garbage_marker_fails(self):
        for bad in ("nan", "inf", "abc"):
            with self.subTest(bad=bad):
                r = self.run_bench("true", *self.ARGS, log_text=self.log(STRESS_VDS=bad))
                self.assertNotEqual(r.returncode, 0)

    def test_nonzero_exit_fails(self):
        r = self.run_bench("true", *self.ARGS, log_text=self.log(), exit_code=2)
        self.assertNotEqual(r.returncode, 0)


class Wiring(unittest.TestCase):
    """Both run_sweep.sh --check-env branches must route through the shared
    gate with the artifacts their benches actually promise."""

    def text(self, rel):
        return (SIM / rel).read_text()

    def test_pass_device(self):
        t = self.text("pass-device-screening/run_sweep.sh")
        self.assertIn("preflight_bench_ok", t)
        self.assertIn("--wrdata", t)
        for m in ("STRESS_ID", "STRESS_VSG", "STRESS_VDS", "STRESS_VDG", "DROPOUT_CGATE"):
            self.assertIn(f"--marker {m}", t)
        # The old inspection-only decision must be gone.
        self.assertNotIn('! ngspice -b "${netlist}"', t)

    def test_cmos5l(self):
        t = self.text("ldo-cmos5l-pvt-sweep/run_sweep.sh")
        self.assertIn("preflight_bench_ok", t)
        self.assertEqual(len(re.findall(r"--wrdata", t)), 3)
        self.assertNotIn('--check-env FAILED for ${bench} bench -- see below', t)

    def test_expected_columns_match_templates(self):
        # wrdata vector count x2 (scale, value) must match the validator args.
        t = self.text("ldo-cmos5l-pvt-sweep/run_sweep.sh")
        for bench, vecs, ncols in (("dcsweep", 4, 8), ("loopgain", 2, 4), ("psrr", 1, 2)):
            tmpl = self.text(f"ldo-cmos5l-pvt-sweep/testbench/tb_{bench}_cmos5l.spice.tmpl")
            m = re.search(r"^wrdata @@\w+@@ (.+)$", tmpl, re.M)
            self.assertEqual(len(m.group(1).split()), vecs)
            self.assertIn(f"_check_{'dc' if bench == 'dcsweep' else 'ac'}.csv:{ncols}:", t)
        p = self.text("pass-device-screening/testbench/tb_dropout_pmos.spice.tmpl")
        self.assertEqual(len(re.search(r"^wrdata @@DC_CSV@@ (.+)$", p, re.M).group(1).split()), 2)


if __name__ == "__main__":
    unittest.main()
