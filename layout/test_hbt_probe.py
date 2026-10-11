"""Tests for layout/hbt-probe (issue #150): the committed-evidence offline
check plus its failure and change-detection controls.

Offline cases run anywhere (stdlib only, no klayout module / klt binary /
PDK) — including the CI job that has none of them. Tool-backed cases run
only where the pinned environment exists (CI's layout-check job); elsewhere
they skip with the reason. Run:
    python3 -m unittest discover -s layout -p 'test_*.py' -v
"""
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr

HERE = pathlib.Path(__file__).resolve().parent
PROBE = HERE / "hbt-probe"
sys.path.insert(0, str(PROBE))

import hbt_probe  # noqa: E402
import validate_fixture  # noqa: E402


def copy_probe() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-test-")) / "hbt-probe"


def setup_copy() -> pathlib.Path:
    tmp = copy_probe()
    shutil.copytree(PROBE, tmp / "hbt-probe")
    return tmp


def run_check(tmp: pathlib.Path) -> tuple[int, str]:
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            rc = hbt_probe.check_mode(tmp / "hbt-probe")
    except hbt_probe.ProbeError as e:
        return 1, f"FAIL {e}"
    return rc, err.getvalue()


class OfflineCheckCommittedTree(unittest.TestCase):
    def test_check_passes_on_committed_tree(self):
        self.assertEqual(hbt_probe.check_mode(PROBE), 0)

    def test_check_never_imports_klayout(self):
        """--check must succeed even when `import klayout` is poisoned."""
        poison = pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-poison-"))
        (poison / "klayout.py").write_text(
            'raise ImportError("klayout must not be imported by --check")\n'
        )
        env = dict(__import__("os").environ, PYTHONPATH=str(poison))
        proc = subprocess.run(
            [sys.executable, str(PROBE / "hbt_probe.py"), "--check"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


class OfflineTamperControls(unittest.TestCase):
    """Every mutation of a committed input, raw report or pin MUST fail."""

    def test_tampered_fixture_gds(self):
        tmp = setup_copy()
        gds = tmp / "hbt-probe" / "npn13G2.gds"
        data = bytearray(gds.read_bytes())
        data[-1] ^= 0xFF
        gds.write_bytes(bytes(data))
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("npn13G2.gds", out)

    def test_tampered_reference_cdl(self):
        tmp = setup_copy()
        cdl = tmp / "hbt-probe" / "npn13G2.cdl"
        cdl.write_text(cdl.read_text().replace("m=2", "m=3"))
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("npn13G2.cdl", out)

    def test_tampered_lvs_request(self):
        tmp = setup_copy()
        req = tmp / "hbt-probe" / "lvs_request.json"
        req.write_text(req.read_text().replace('"sg13g2"', '"sky130"'))
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("lvs_request.json", out)

    def test_tampered_raw_drc_report(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "raw" / "drc_report.json"
        report = json.loads(path.read_text())
        report["violation_count"] = 5
        path.write_text(json.dumps(report, indent=2) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("drc.violation_count", out)

    def test_tampered_raw_extract_names_upstream_gap(self):
        """Synthetic changed recognition: a report claiming recognized devices
        must fail as changed behavior and name the upstream extraction issue."""
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "raw" / "extract_report.json"
        report = json.loads(path.read_text())
        report["device_count"] = 3
        report["device_classes"] = list(report["device_classes"]) + ["npn"]
        path.write_text(json.dumps(report, indent=2) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("extract.device_count", out)
        self.assertIn("#2864", out)

    def test_tampered_raw_lvs_verdict(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "raw" / "lvs_report.json"
        report = json.loads(path.read_text())
        report["status"] = "match"
        report["error_count"] = 0
        path.write_text(json.dumps(report, indent=2) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("lvs.status", out)

    def test_tampered_summary_only(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "summary.json"
        summary = json.loads(path.read_text())
        summary["probe"] = "tampered"
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("byte-for-byte", out)

    def test_stale_pin_in_expectations(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "expectations.json"
        exp = json.loads(path.read_text())
        exp["pins"]["klayout_version"] = "0.30.11"
        path.write_text(json.dumps(exp, indent=2) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("pin drift", out)

    def test_tampered_expectations_verdict(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "expectations.json"
        exp = json.loads(path.read_text())
        exp["expected"]["extract"]["device_count"] = 3
        path.write_text(json.dumps(exp, indent=2) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)

    def test_invalid_json_raw_report(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "raw" / "drc_report.json"
        path.write_text("{not json")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("invalid JSON", out)

    def test_error_envelope_raw_report(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "raw" / "extract_report.json"
        path.write_text(textwrap.dedent("""\
            {
              "schema_version": 1,
              "error": {
                "command": "extract",
                "message": "cell 'NOPE' not found in 'npn13G2.gds'"
              }
            }
            """))
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("error envelope", out)

    def test_chain_break_between_extract_and_lvs(self):
        tmp = setup_copy()
        path = tmp / "hbt-probe" / "raw" / "lvs_report.json"
        report = json.loads(path.read_text())
        report["environment"]["layout_sha256"] = "0" * 64
        path.write_text(json.dumps(report, indent=2) + "\n")
        rc, out = run_check(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("chain broken", out)


class OfflineUnitControls(unittest.TestCase):
    def test_verdict_mismatch_detector(self):
        observed = hbt_probe._observed({
            "drc": hbt_probe._load_report(PROBE, "drc"),
            "extract": hbt_probe._load_report(PROBE, "extract"),
            "lvs": hbt_probe._load_report(PROBE, "lvs"),
        })
        expect = hbt_probe._expectations(PROBE)
        self.assertEqual(hbt_probe._verdict_mismatches(expect["expected"], observed), [])
        observed["extract"]["device_count"] = 3
        observed["lvs"]["status"] = "match"
        bad = hbt_probe._verdict_mismatches(expect["expected"], observed)
        self.assertEqual(len(bad), 2)
        err = io.StringIO()
        with redirect_stderr(err):
            rc = hbt_probe._fail_changed(bad)
        self.assertEqual(rc, 1)
        self.assertIn("#2864", err.getvalue())
        self.assertIn("--record", err.getvalue())


def _has_klayout() -> bool:
    try:
        import klayout.db  # noqa: F401
        return True
    except ImportError:
        return False


def _klt_pinned() -> str | None:
    """Return the klt on PATH if it matches the pinned version, else None."""
    import shutil as _sh
    klt = _sh.which("klt")
    if klt is None:
        return None
    proc = subprocess.run([klt, "--version"], capture_output=True, text=True)
    pins = hbt_probe._expectations(PROBE)["pins"]
    if proc.stdout.strip() == f"klt {pins['klt_version']}":
        return klt
    return None


@unittest.skipUnless(_has_klayout(), "klayout Python module not installed (offline CI job)")
class FixtureValidatorControls(unittest.TestCase):
    def test_accepts_committed_fixture(self):
        cards = validate_fixture.validate(PROBE / "npn13G2.gds", PROBE / "npn13G2.cdl")
        self.assertEqual([c["m"] for c in cards], [1, 2, 4])
        for card in cards:
            self.assertEqual(card["terminals"][3], "sub!")
            self.assertEqual(len(card["terminals"]), 4)

    def test_rejects_missing_top(self):
        import klayout.db as kdb
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-gds-"))
        ly = kdb.Layout()
        ly.read(str(PROBE / "npn13G2.gds"))
        ly.cell("npn13G2").name = "RENAMED"
        ly.write(str(tmp / "renamed.gds"))
        with self.assertRaises(validate_fixture.FixtureError) as ctx:
            validate_fixture.validate(tmp / "renamed.gds", PROBE / "npn13G2.cdl")
        self.assertIn("top cell", str(ctx.exception))

    def test_rejects_corrupt_gds(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-gds-"))
        (tmp / "bad.gds").write_bytes(b"not a gds stream")
        with self.assertRaises(validate_fixture.FixtureError):
            validate_fixture.validate(tmp / "bad.gds", PROBE / "npn13G2.cdl")

    def test_rejects_wrong_multiplicity(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-cdl-"))
        cdl = PROBE / "npn13G2.cdl"
        (tmp / "npn13G2.cdl").write_text(cdl.read_text().replace("Q3", "Q9").replace("m=4", "m=7"))
        with self.assertRaises(validate_fixture.FixtureError) as ctx:
            validate_fixture.validate(PROBE / "npn13G2.gds", tmp / "npn13G2.cdl")
        self.assertIn("multiplicit", str(ctx.exception))


@unittest.skipUnless(_klt_pinned() is not None,
                     "the klt on PATH is missing or not the pinned build "
                     "(run under the pinned layout environment to exercise)")
class FreshRunControls(unittest.TestCase):
    def test_fresh_run_reproduces_expectations(self):
        proc = subprocess.run(
            [sys.executable, str(PROBE / "hbt_probe.py"), "--run"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("reproduces every expected outcome", proc.stdout)

    def test_run_rejects_missing_binary(self):
        env = {"PATH": "/nonexistent", "HOME": "/nonexistent"}
        proc = subprocess.run(
            [sys.executable, str(PROBE / "hbt_probe.py"), "--run"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("klt not found", proc.stderr)

    def test_run_rejects_pin_drift(self):
        fake_bin = pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-fakebin-"))
        (fake_bin / "klt").write_text("#!/bin/sh\necho 'klt 9.9.9+fake'\n")
        (fake_bin / "klt").chmod(0o755)
        env = dict(__import__("os").environ, PATH=f"{fake_bin}:{__import__('os').environ['PATH']}")
        proc = subprocess.run(
            [sys.executable, str(PROBE / "hbt_probe.py"), "--run"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("pinned klt build not found", proc.stderr)

    def test_run_and_record_leave_the_tree_untouched(self):
        before = {
            p: (p.stat().st_mtime_ns, p.stat().st_size)
            for p in PROBE.rglob("*") if p.is_file()
        }
        proc = subprocess.run(
            [sys.executable, str(PROBE / "hbt_probe.py"), "--run"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = {
            p: (p.stat().st_mtime_ns, p.stat().st_size)
            for p in PROBE.rglob("*") if p.is_file()
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
