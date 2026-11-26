"""Tests for singular_screen.py -- the shared, single-pass singular-matrix
log predicate the four PVT drivers' screen_point functions call (issue #383).
Offline and stdlib-only: no simulator, no PDK, nothing submitted.

    python3 -m unittest sim/ldo-cmos5l-pvt-sweep/test_singular_screen.py -v

Four layers:

1. **The predicate.** The short controls of the issue's reproducer table
   (one recovered `Warning: singular matrix` accepted, one bare
   `singular matrix` rejected), the long mixed log that table's third row
   is about (one unrecovered line followed by 100,000 recovered warnings),
   a mixed-case indented warning, and the readable-log requirement.

2. **The CLI the drivers call** (`check-log` exit codes 0/1/2).

3. **The two-grep pipeline this replaces, kept as a live baseline.** The
   exact `grep -iE ... | grep -qivE ...` form under `pipefail` is run on
   the same three fixtures: right on the two short logs, wrong on the long
   mixed one (the second grep exits on the fatal first line, the first
   grep dies of SIGPIPE still writing the warning tail, and the pipeline's
   non-zero status reads as "no fatal match"). This is the defect the
   single-pass predicate exists to remove, reproduced rather than asserted.

4. **The drivers' own screens.** screen_point is extracted VERBATIM from
   each of run_sweep.sh / run_loopgain2.sh / run_ccprobe.sh / run_e4.sh
   (the scripts cannot be sourced -- they run the sweeps) and driven under
   each driver's own `set -euo pipefail` regime with the long mixed
   fixture, simulator rc 0 and a COMPLETE export: the point must be
   rejected on the log alone. The negative control removes the fatal line
   from the same fixture and shows the same screen accepting the point --
   so the rejection is the predicate's, not the fixture's -- and, for the
   main sweep, still counting the point as a recovered-warning point
   (run_sweep.sh's warning accounting is untouched). A text gate keeps the
   four call sites from drifting back to a private copy of the rule.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import singular_screen as ss  # noqa: E402

DRIVERS = ("run_sweep.sh", "run_loopgain2.sh", "run_ccprobe.sh", "run_e4.sh")

N_WARNINGS = 100_000        # the fleet worker's long tail, per issue #383
WARN_LINE = "Warning: singular matrix:  system is singular, delta = 1e-12\n"
FATAL_LINE = "singular matrix: cannot reindex; no recovery attempted\n"


def write_log(path, lines):
    with open(path, "w") as fh:
        fh.writelines(lines)


def long_mixed_lines():
    """One unrecovered line, then the long run of recovered warnings."""
    return [FATAL_LINE] + [WARN_LINE] * N_WARNINGS


def long_clean_lines():
    """The same fixture with only its fatal line removed."""
    return [WARN_LINE] * N_WARNINGS


def write_trace(path, ceiling_rows=161):
    """A wrdata-shaped 4-column trace with the exact row count, floor and
    ceiling frequencies ac_sweep.check-trace / loopgain2.check-export
    demand (the shape test_ac_sweep.py's write_trace uses)."""
    with open(path, "w") as fh:
        for i in range(ceiling_rows):
            f = 10 ** (i / 20)
            fh.write(f" {f:.8e} -1.0e+00 {f:.8e} -9.0e+01 \n")


def shell_function(driver, name):
    """A top-level function of the driver, VERBATIM. The script cannot be
    sourced (it runs the sweep), so the function text is run on its own --
    the same discipline as test_dynamic_doe.py's shell_function."""
    with open(os.path.join(HERE, driver), encoding="utf-8") as fh:
        src = fh.read()
    start = src.index(f"\n{name}() {{") + 1
    return src[start:src.index("\n}\n", start) + len("\n}\n")]


def run_extracted_screen(driver, pid, call_line, log_lines, write_export,
                         extra_setup="", **env):
    """screen_point extracted from `driver`, run under the driver's own
    `set -euo pipefail`, with the point's log at <tmp>/<pid>.log and the
    export `write_export(tmp)` stages. Returns the parsed marker lines the
    tail prints (rc, total, passed, nfailed, nwarn, failed)."""
    tmp = tempfile.mkdtemp()
    try:
        write_log(os.path.join(tmp, f"{pid}.log"), log_lines)
        write_export(tmp)
        func = shell_function(driver, "screen_point")
        tail = f"""
total=0
passed=0
failed_points=()
recoverable_warning_points=()
{extra_setup}
set +e
{call_line}
rc=$?
set -e
printf 'rc=%s\\ntotal=%s\\npassed=%s\\nnfailed=%s\\nnwarn=%s\\n' \\
  "$rc" "$total" "$passed" "${{#failed_points[@]}}" "${{#recoverable_warning_points[@]}}"
if [[ ${{#failed_points[@]}} -gt 0 ]]; then printf 'failed=%s\\n' "${{failed_points[*]}}"; fi
"""
        r = subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + func + tail],
            capture_output=True, text=True, check=False,
            env=dict(os.environ, CORNERS_OUT=tmp, SCRIPT_DIR=HERE, **env))
        if r.returncode != 0:
            raise AssertionError(f"{driver} screen harness exited {r.returncode}:\n{r.stderr}")
        return {kv.split("=", 1)[0]: kv.split("=", 1)[1]
                for kv in r.stdout.splitlines() if "=" in kv}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Predicate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name="p.log"):
        return os.path.join(self.tmp, name)

    def test_recoverable_warning_line_is_clean(self):
        self.assertFalse(ss.fatal_line(WARN_LINE))
        write_log(self.path(), [WARN_LINE])
        self.assertIsNone(ss.screen(self.path()))

    def test_indented_mixed_case_warning_is_clean(self):
        line = "   wArNiNg: singular matrix:  system is singular\n"
        self.assertFalse(ss.fatal_line(line))
        write_log(self.path(), [line])
        self.assertIsNone(ss.screen(self.path()))

    def test_bare_singular_line_is_fatal(self):
        self.assertTrue(ss.fatal_line(FATAL_LINE))
        write_log(self.path(), [FATAL_LINE])
        code, message = ss.screen(self.path())
        self.assertEqual(code, 1)
        self.assertIn("unrecovered singular matrix", message)
        self.assertIn(":1:", message)
        self.assertIn("no recovery attempted", message)

    def test_fatal_line_first_before_warning_tail_is_fatal(self):
        # The issue's third table row: one `singular matrix`, then 100,000
        # `Warning: singular matrix` lines.
        write_log(self.path(), long_mixed_lines())
        code, message = ss.screen(self.path())
        self.assertEqual(code, 1)
        self.assertIn(":1:", message)

    def test_fatal_line_last_after_warning_tail_is_fatal(self):
        # Order independence: the same tail with the fatal line at the end.
        write_log(self.path(), [WARN_LINE] * N_WARNINGS + [FATAL_LINE])
        code, message = ss.screen(self.path())
        self.assertEqual(code, 1)
        self.assertIn(f":{N_WARNINGS + 1}:", message)

    def test_log_without_singular_matrix_is_clean(self):
        write_log(self.path(), ["Doing operational point\n",
                                "Dynamic gmin stepping completed\n"])
        self.assertIsNone(ss.screen(self.path()))

    def test_empty_readable_log_is_clean(self):
        write_log(self.path(), [])
        self.assertIsNone(ss.screen(self.path()))

    def test_missing_log_rejects(self):
        code, message = ss.screen(self.path("never-written.log"))
        self.assertEqual(code, 2)
        self.assertIn("unreadable log", message)

    def test_unreadable_log_rejects(self):
        # A directory is unreadable as a file for every user, root included.
        code, message = ss.screen(self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("unreadable log", message)


class CLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = os.path.join(self.tmp, "p.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "singular_screen.py"), *args],
            capture_output=True, text=True)

    def test_clean_log_exits_zero_silent(self):
        write_log(self.f, [WARN_LINE])
        r = self.cli("check-log", self.f)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")

    def test_long_mixed_log_exits_one_with_the_line(self):
        write_log(self.f, long_mixed_lines())
        r = self.cli("check-log", self.f)
        self.assertEqual(r.returncode, 1)
        self.assertIn("unrecovered singular matrix", r.stderr)
        self.assertIn(os.path.basename(self.f), r.stderr)

    def test_missing_log_exits_two(self):
        r = self.cli("check-log", os.path.join(self.tmp, "nope.log"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("unreadable log", r.stderr)

    def test_malformed_invocation_exits_two(self):
        for args in ((), ("check-log",), ("check-log", "a", "b"), ("screen", self.f)):
            r = self.cli(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("usage:", r.stderr)


class TwoGrepBaseline(unittest.TestCase):
    """The exact two-grep pipeline the four drivers inlined before #383,
    run under `pipefail` on the issue's three fixtures. Right on both short
    logs, wrong on the long mixed one -- the defect singular_screen.py
    replaces, kept executable so the root cause stays reproducible."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pipeline(self, name, lines):
        path = os.path.join(self.tmp, name)
        write_log(path, lines)
        # One echo: `$?` and `${PIPESTATUS[*]}` expand before it runs, and a
        # separate assignment (`st=$?`) would reset PIPESTATUS before the
        # members capture.
        script = (
            "set -o pipefail\n"
            'grep -iE "singular matrix" "$1" | grep -qivE "^[[:space:]]*Warning:"\n'
            'echo "pipeline=$? members=${PIPESTATUS[*]}"\n')
        r = subprocess.run(["bash", "-c", script, "baseline", path],
                           capture_output=True, text=True)
        head, _, tail = r.stdout.strip().partition(" members=")
        members = [int(m) for m in tail.split()]
        return int(head.split("=", 1)[1]), members

    def test_warning_only_log_accepted(self):
        status, _ = self.pipeline("warn.log", [WARN_LINE])
        self.assertNotEqual(status, 0)          # "no fatal match"

    def test_fatal_only_log_rejected(self):
        status, _ = self.pipeline("fatal.log", [FATAL_LINE])
        self.assertEqual(status, 0)             # fatal match found

    def test_long_mixed_log_fatally_misread(self):
        # The first grep dies of SIGPIPE (141) still writing the warning
        # tail; pipefail makes the pipeline non-zero and the driver's `if`
        # reads that as "no fatal match" -- the point is accepted in error.
        status, members = self.pipeline("mixed.log", long_mixed_lines())
        self.assertNotEqual(status, 0, "pipeline claims no fatal match")
        self.assertNotEqual(members[0], 0, "first grep should die of SIGPIPE")
        self.assertEqual(members[1], 0, "second grep found the fatal line")


class DriverScreens(unittest.TestCase):
    """The main sweep's point screen (and its three siblings) must reject
    the long mixed fixture through a COMPLETE export: simulator rc 0, the
    export row count the screen itself demands. Only the log varies."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def export_trace(self, pid, rows=161):
        def writer(tmp):
            write_trace(os.path.join(tmp, f"{pid}_ac.csv"), rows)
        return writer

    def test_main_sweep_rejects_long_mixed_log_with_complete_export(self):
        pid = "dcsweep_tt_27c_typ"
        out = run_extracted_screen(
            "run_sweep.sh", pid, f'screen_point "{pid}" 0',
            long_mixed_lines(),
            lambda tmp: write_trace(os.path.join(tmp, f"{pid}_dc.csv"), 3),
            EXPECT_ROWS_DC="3")
        self.assertEqual(out["rc"], "1")
        self.assertEqual(out["passed"], "0")
        self.assertEqual(out["nfailed"], "1")
        self.assertIn(pid, out["failed"])
        self.assertEqual(out["nwarn"], "0", "a rejected point is not a warning point")

    def test_main_sweep_accepts_the_same_fixture_without_the_fatal_line(self):
        # Negative control: only the log's fatal line differs, so the
        # rejection above is the predicate's. The warning accounting the
        # drivers keep must still count the point.
        pid = "dcsweep_tt_27c_typ"
        out = run_extracted_screen(
            "run_sweep.sh", pid, f'screen_point "{pid}" 0',
            long_clean_lines(),
            lambda tmp: write_trace(os.path.join(tmp, f"{pid}_dc.csv"), 3),
            EXPECT_ROWS_DC="3")
        self.assertEqual(out["rc"], "0")
        self.assertEqual(out["passed"], "1")
        self.assertEqual(out["nfailed"], "0")
        self.assertEqual(out["nwarn"], "1")

    def test_loopgain2_screen_rejects_long_mixed_log(self):
        pid = "loopgain_ctl_ab_fixture"
        for lines, want in ((long_mixed_lines(), "1"), (long_clean_lines(), "0")):
            out = run_extracted_screen(
                "run_loopgain2.sh", pid, f'screen_point "{pid}"', lines,
                self.export_trace(pid),
                extra_setup="declare -A BENCH_COLS=( [loopgain_ctl]=4 )",
                LG_AC_MAX="100meg")
            self.assertEqual(out["rc"], want, lines[:1])

    def test_ccprobe_screen_rejects_long_mixed_log(self):
        pid = "ccprobe_fixture"
        for lines, want in ((long_mixed_lines(), "1"), (long_clean_lines(), "0")):
            out = run_extracted_screen(
                "run_ccprobe.sh", pid, f'screen_point "{pid}"', lines,
                self.export_trace(pid), LG_AC_MAX="100meg")
            self.assertEqual(out["rc"], want, lines[:1])

    def test_e4_screen_rejects_long_mixed_log(self):
        pid = "psrr_fixture"
        for lines, want in ((long_mixed_lines(), "1"), (long_clean_lines(), "0")):
            out = run_extracted_screen(
                "run_e4.sh", pid, f'screen_point "{pid}" "ac"', lines,
                self.export_trace(pid), EXPECT_ROWS_AC="161")
            self.assertEqual(out["rc"], want, lines[:1])


class DriverCallSites(unittest.TestCase):
    """The four drivers must all carry the shared call and no private copy
    of the two-grep rule (a splice that silently reverts one of them)."""

    def text(self, driver):
        with open(os.path.join(HERE, driver), encoding="utf-8") as fh:
            return fh.read()

    def test_every_driver_calls_the_shared_predicate(self):
        for driver in DRIVERS:
            self.assertIn('singular_screen.py" check-log', self.text(driver), driver)

    def test_no_driver_keeps_the_two_grep_second_stage(self):
        for driver in DRIVERS:
            self.assertNotIn('grep -qivE "^[[:space:]]*Warning:"',
                             self.text(driver), driver)

    def test_every_driver_still_parses(self):
        for driver in DRIVERS:
            r = subprocess.run(["bash", "-n", os.path.join(HERE, driver)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{driver}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
