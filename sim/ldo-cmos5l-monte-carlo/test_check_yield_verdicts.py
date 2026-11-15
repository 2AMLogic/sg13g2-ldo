"""Offline tests for check_yield_verdicts.py (no klt needed: the runner is
replaced by one that replays the committed report, so only the comparison
logic is under test; the real klt run is the CI step)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_yield_verdicts as c  # noqa: E402

REC = Path(__file__).resolve().parent / "records"
HERE_ROOT = REC.parent
RECORDS = sorted(p for p in REC.iterdir() if p.is_dir())


def replay(directory, samples):
    """Fake klt: return the committed report and exit code for `samples`."""
    base = samples[: -len(".samples.json")]
    rc = c.parse_exit_codes(Path(directory) / "exit-codes.txt")[base]
    return rc, (Path(directory) / f"{base}.yield.json").read_text()


class CheckYieldVerdictsTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.rec = Path(self._t.name) / "rec"
        shutil.copytree(RECORDS[-1], self.rec, ignore=shutil.ignore_patterns("raw"))
        self.d = self.rec / "yield"

    def test_committed_records_pass_with_replay(self):
        for rec in RECORDS:
            for d in c.yield_dirs(rec):
                self.assertEqual(c.check_dir(d, replay), [], d)

    def test_tampered_yield_block_fails(self):
        p = self.d / "tt_27C.yield.json"
        doc = json.loads(p.read_text())
        doc["measurements"][0]["yield"]["empirical"]["estimate"] = 0.5
        p.write_text(json.dumps(doc))
        fails = c.check_dir(self.d, lambda d, s: (replay(d, s)[0],
                            (REC / RECORDS[-1].name / "yield" / s.replace("samples", "yield")).read_text()))
        self.assertTrue(any("tt_27C" in f and "vout_v.yield" in f for f in fails), fails)

    def test_tampered_status_and_negative_control_fail(self):
        p = self.d / "tt_27C.yield.json"
        doc = json.loads(p.read_text())
        doc["status"] = "fail"
        doc["measurements"][0]["negative_control"] = None
        p.write_text(json.dumps(doc))
        orig = RECORDS[-1] / "yield"
        fails = c.check_dir(self.d, lambda d, s: (replay(orig, s)))
        self.assertTrue(any("status" in f for f in fails), fails)
        self.assertTrue(any("negative_control" in f for f in fails), fails)

    def test_exit_code_drift_fails(self):
        ec = self.d / "exit-codes.txt"
        ec.write_text(ec.read_text().replace("tt_27C: klt yield exit 0", "tt_27C: klt yield exit 3"))
        orig = RECORDS[-1] / "yield"
        fails = c.check_dir(self.d, lambda d, s: replay(orig, s))
        self.assertTrue(any("tt_27C" in f and "exit code" in f for f in fails), fails)

    def test_missing_exit_code_entry_fails(self):
        ec = self.d / "exit-codes.txt"
        ec.write_text("\n".join(l for l in ec.read_text().splitlines() if not l.startswith("tt_27C:")))
        fails = c.check_dir(self.d, lambda d, s: (0, "{}"))
        self.assertTrue(any("tt_27C" in f and "no exit-codes.txt entry" in f for f in fails), fails)

    def test_non_json_output_fails(self):
        fails = c.check_dir(self.d, lambda d, s: (0, "Traceback"))
        self.assertTrue(any("not JSON" in f for f in fails), fails)

    def test_record_without_yield_dir_fails(self):
        shutil.rmtree(self.d)
        self.assertEqual(c.main(["--klt", "/nonexistent", str(self.rec)]), 1)

    def test_attribution_checked_by_default(self):
        self.assertEqual(len(c.yield_dirs(self.rec)), 2)

    def _root(self, record):
        """Copy of `rederived/` plus the matching record, rooted in a temp dir."""
        root = Path(tempfile.mkdtemp(dir=self._t.name))
        shutil.copytree(HERE_ROOT / "rederived", root / "rederived")
        rec = root / "records" / record
        shutil.copytree(REC / record, rec, ignore=shutil.ignore_patterns("raw"))
        return root, rec

    def _replay_all(self, root):
        def run(directory, samples):
            d = Path(directory)
            base = samples[: -len(".samples.json")]
            return c.parse_exit_codes(d / "exit-codes.txt")[base], (d / f"{base}.yield.json").read_text()
        return run

    def test_superseded_reports_pass_via_rederived_location(self):
        for rec_name, _ in {k[0]: 0 for k in c.SUPERSEDED}.items():
            root, rec = self._root(rec_name)
            fails, _n = c.check_record(rec, self._replay_all(root), root=root)
            self.assertEqual(fails, [], rec_name)

    def test_superseded_without_rederived_location_fails(self):
        rec_name = next(iter(c.SUPERSEDED))[0]
        root, rec = self._root(rec_name)
        shutil.rmtree(root / "rederived")
        fails, _n = c.check_record(rec, self._replay_all(root), root=root)
        self.assertTrue(any("re-derived" in f and "missing" in f for f in fails), fails)

    def test_superseded_samples_altered_fails(self):
        rec_name, base = next(iter(c.SUPERSEDED))
        root, rec = self._root(rec_name)
        rel = c.SUPERSEDED[(rec_name, base)][0]
        p = root / rel / "yield" / "attribution" / f"{base}.samples.json"
        p.write_text(p.read_text() + " ")
        fails, _n = c.check_record(rec, self._replay_all(root), root=root)
        self.assertTrue(any("differs from the superseded" in f for f in fails), fails)

    def test_rederived_report_tampered_fails(self):
        rec_name, base = next(iter(c.SUPERSEDED))
        root, rec = self._root(rec_name)
        rel = c.SUPERSEDED[(rec_name, base)][0]
        d = root / rel / "yield" / "attribution"
        doc = json.loads((d / f"{base}.yield.json").read_text())
        pristine = json.dumps(doc)
        doc["measurements"][0]["yield"]["empirical"]["estimate"] = 0.5
        (d / f"{base}.yield.json").write_text(json.dumps(doc))
        run = lambda directory, s: (0, pristine)  # noqa: E731
        fails, _n = c.check_record(rec, run, root=root)
        self.assertTrue(any(base in f and "vout_v.yield" in f for f in fails), fails)

    def test_unsuperseded_attribution_drift_fails(self):
        # an attribution report not in SUPERSEDED is gated like any other
        rec_name = RECORDS[-1].name
        root, rec = self._root(rec_name)
        fails, _n = c.check_record(rec, lambda d, s: (0, "{}"), superseded={}, root=root)
        self.assertTrue(any("attribution" in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main()
