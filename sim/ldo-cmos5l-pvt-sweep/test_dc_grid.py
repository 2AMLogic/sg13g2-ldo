"""Complete-grid contract tests (issue #120). stdlib only, no PDK, no ngspice.

    python3 -m unittest discover -s sim/ldo-cmos5l-pvt-sweep -p 'test_*.py' -v

Covers the shared validator (dc_grid.py), the offline item-5 consumer
(item5_evidence.analyse_point) and the live sweep post-processing, which is
extracted verbatim from run_sweep.sh's heredoc and executed on a synthetic
corners directory.
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dc_grid as dcg  # noqa: E402
import dc_metrics as dcm  # noqa: E402
import item5_evidence as ev  # noqa: E402

LOADS = [0.0, 0.0125, 0.025, 0.0375, 0.05]
VINS = [round(2.00 + 0.01 * i, 2) for i in range(164)]
COMMITTED = os.path.join(ev.REPO, ev.CORNERS_DIR, "dcsweep_tt_27c_rtyp_dc.csv")


def fmt_row(vin, vo=1.8, load=0.0, iq=20e-6):
    return " ".join(f"{x:.8e}" for x in [vin, vin, vin, vo, vin, -(load + iq), vin, 3e-6])


def good_lines(blocks=5):
    return [fmt_row(v, load=ld) for ld in LOADS[:blocks] for v in VINS]


def write(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def mutations():
    """name -> mutated line list; every one must be rejected."""
    def m(fn):
        L = good_lines()
        fn(L)
        return L
    out = {}
    out["truncated_fifth_block"] = good_lines()[:-5]
    out["extra_block"] = good_lines(5) + [fmt_row(v, load=0.06) for v in VINS]
    # interior Vin replaced: row count, endpoints and block count preserved
    out["replaced_interior_point"] = m(lambda L: L.__setitem__(2 * 164 + 50, fmt_row(2.505, load=0.025)))
    out["duplicate_point"] = m(lambda L: L.__setitem__(164 + 80, L[164 + 79]))
    out["reordered_points"] = m(lambda L: L.__setitem__(slice(164 + 10, 164 + 12), [L[164 + 11], L[164 + 10]]))
    out["nan_value"] = m(lambda L: L.__setitem__(3 * 164 + 7, fmt_row(VINS[7], vo=float("nan"), load=0.0375)))
    out["inf_value"] = m(lambda L: L.__setitem__(7, fmt_row(VINS[7], vo=float("inf"))))
    out["malformed_token"] = m(lambda L: L.__setitem__(9, L[9].replace("e+00", "e+0x", 1)))
    out["dropped_short_line"] = m(lambda L: L.__setitem__(100, "2.1 2.1 2.1"))
    return out


class Validator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_valid_grid_accepted(self):
        p = os.path.join(self.tmp, "g.csv")
        write(p, good_lines())
        blocks, problems = dcg.validate_file(p)
        self.assertEqual(problems, [])
        self.assertEqual(len(blocks), 5)

    def test_missing_file_rejected(self):
        self.assertTrue(dcg.validate_file(os.path.join(self.tmp, "nope.csv"))[1])
        self.assertIn("error", dcg.validated_dc_metrics(os.path.join(self.tmp, "nope.csv")))

    def test_every_negative_control_rejected_with_reason(self):
        for name, lines in mutations().items():
            with self.subTest(name):
                p = os.path.join(self.tmp, name + ".csv")
                write(p, lines)
                _, problems = dcg.validate_file(p)
                self.assertTrue(problems, name)
                res = dcg.validated_dc_metrics(p)
                self.assertEqual(list(res), ["error"], name)
                self.assertTrue(res["error"].startswith("invalid DC grid:"))

    def test_replaced_interior_point_passes_legacy_parser(self):
        """The motivating gap: legacy dc_metrics alone does not notice."""
        p = os.path.join(self.tmp, "r.csv")
        write(p, mutations()["replaced_interior_point"])
        self.assertNotIn("error", dcm.dc_metrics(p))
        self.assertIn("error", dcg.validated_dc_metrics(p))

    def test_truncated_fifth_block_would_substitute_neighbour_in_legacy(self):
        p = os.path.join(self.tmp, "t.csv")
        write(p, mutations()["truncated_fifth_block"])
        self.assertNotIn("error", dcm.dc_metrics(p))  # legacy: silently nearest-point
        self.assertIn("error", dcg.validated_dc_metrics(p))

    @unittest.skipUnless(os.path.exists(COMMITTED), "committed raw grid absent")
    def test_committed_raw_grids_unchanged_metrics(self):
        for rid in ("20260917-023832-7061e8f", "20261010-025634-60a3e81"):
            d = os.path.join(ev.REPO, "sim/ldo-cmos5l-pvt-sweep/corners", rid)
            for n in sorted(os.listdir(d)):
                if n.startswith("dcsweep_") and n.endswith("_dc.csv"):
                    p = os.path.join(d, n)
                    self.assertEqual(dcg.validate_file(p)[1], [], p)
                    self.assertEqual(dcg.validated_dc_metrics(p), dcm.dc_metrics(p), p)


class OfflineConsumer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._repo = ev.REPO
        ev.REPO = self.tmp

    def tearDown(self):
        ev.REPO = self._repo
        shutil.rmtree(self.tmp)

    def test_item5_rejects_each_negative_control(self):
        for name, lines in mutations().items():
            with self.subTest(name):
                write(os.path.join(self.tmp, name + ".csv"), lines)
                a = ev.analyse_point(name + ".csv")
                self.assertFalse(a["valid"])
                self.assertFalse(a["grid_ok"])
                self.assertTrue(a["grid_problems"])


def _post_script():
    s = open(os.path.join(HERE, "run_sweep.sh")).read()
    a = s.index("<<'PYEOF'\n") + len("<<'PYEOF'\n")
    return s[a:s.index("\nPYEOF\n", a)] + "\n"


class LiveSummaryPath(unittest.TestCase):
    """Runs run_sweep.sh's real post-processing on a one-point grid."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cdir = os.path.join(self.tmp, "c")
        os.mkdir(self.cdir)
        with open(os.path.join(self.tmp, "base.csv"), "w") as f:
            f.write("corner,temp_c,res_section\n")
        with open(os.path.join(self.tmp, "post.py"), "w") as f:
            f.write(_post_script())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_post(self, lines):
        write(os.path.join(self.cdir, "dcsweep_tt_27c_rtyp_dc.csv"), lines)
        t = self.tmp
        return subprocess.run(
            [sys.executable, os.path.join(t, "post.py"), self.cdir, f"{t}/o.csv", f"{t}/s.csv",
             "tt", "27", "typ", f"{t}/base.csv", f"{t}/d.csv", f"{t}/m.md", "", "1"],
            env=dict(os.environ, SWEEP_SCRIPT_DIR=HERE), capture_output=True, text=True)

    def rows(self):
        with open(os.path.join(self.tmp, "o.csv")) as f:
            return list(csv.DictReader(f))

    def test_valid_grid_gives_metrics_and_no_error_sidecar(self):
        r = self.run_post(good_lines())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows()[0]["vout_no_load_v"], "1.8")
        self.assertFalse(os.path.exists(os.path.join(self.cdir, "_dc_grid_errors.tsv")))

    def test_invalid_grids_yield_no_metrics_and_retain_reason(self):
        for name, lines in mutations().items():
            with self.subTest(name):
                tsv = os.path.join(self.cdir, "_dc_grid_errors.tsv")
                if os.path.exists(tsv):
                    os.remove(tsv)
                r = self.run_post(lines)
                self.assertEqual(r.returncode, 0, r.stderr)  # shell folds the sidecar into failed_points
                row = self.rows()[0]
                self.assertEqual(row["iq_a"], "", name)
                self.assertEqual(row["dropout_v_50ma"], "", name)
                self.assertIn("INVALID DC GRID dcsweep_tt_27c_rtyp", r.stderr)
                with open(tsv) as f:
                    pid, err = f.read().rstrip("\n").split("\t")
                self.assertEqual(pid, "dcsweep_tt_27c_rtyp")
                self.assertTrue(err.startswith("invalid DC grid:"))

    def test_shell_folds_errors_into_failed_points_and_exit_status(self):
        s = open(os.path.join(HERE, "run_sweep.sh")).read()
        self.assertIn("dc_metrics = _dcg.validated_dc_metrics", s)
        self.assertIn('failed_points+=("${_pid}")', s)
        self.assertLess(s.index("_dc_grid_errors.tsv\"\nDC_GRID_ERROR_LINES"),
                        s.index("Completeness matrix: every"))


if __name__ == "__main__":
    unittest.main()
