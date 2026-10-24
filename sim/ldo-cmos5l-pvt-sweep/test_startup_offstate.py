"""Fixture tests for startup_offstate.py (issue #133). Synthetic gzip traces
in a temp dir only: they test the reading rule and the hash check, not the
circuit. Offline, stdlib only."""
import gzip
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import startup_offstate as so  # noqa: E402

VIN = 3.3


def write_trace(path, rows):
    """rows: (t, en, ivin). Header matches the recorded traces' columns."""
    text = "t,en,ivin\n" + "".join(f"{t!r},{en!r},{i!r}\n" for t, en, i in rows)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(text)


class OffstateCurrent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "p.csv.gz")

    def test_picks_last_en0_sample_not_earlier_or_edge_time(self):
        write_trace(self.path, [
            (0.0, 0.0, -1e-6),
            (5e-4, 0.0, -2e-6),
            (9.99e-4, 0.0, -3e-6),   # last EN == 0 sample at t <= 1 ms
            (1.0005e-3, VIN / 2, -9e-3),  # inside the edge
            (2e-3, VIN, -5e-4),
        ])
        i, t = so.offstate_current(self.path)
        self.assertEqual(i, 3e-6)
        self.assertEqual(t, 9.99e-4)

    def test_sample_exactly_at_1ms_with_en0_is_included(self):
        write_trace(self.path, [(0.0, 0.0, -1e-6), (1e-3, 0.0, -4e-6), (1.0005e-3, 0.5, -1e-3)])
        self.assertEqual(so.offstate_current(self.path), (4e-6, 1e-3))

    def test_ignores_samples_after_edge_even_if_en_returns_to_zero(self):
        write_trace(self.path, [
            (0.0, 0.0, -1e-6),
            (9e-4, 0.0, -2e-6),
            (1.0005e-3, VIN / 2, -7e-3),
            (7e-3, 0.0, -8e-6),  # disabled again later: must not be read
        ])
        self.assertEqual(so.offstate_current(self.path), (2e-6, 9e-4))

    def test_raises_when_no_en0_sample(self):
        write_trace(self.path, [(0.0, 1e-3, -1e-6), (5e-4, VIN / 2, -2e-6), (2e-3, VIN, -3e-6)])
        with self.assertRaises(SystemExit) as cm:
            so.offstate_current(self.path)
        self.assertIn("no EN = 0 sample", str(cm.exception))

    def test_raises_when_only_post_edge_samples_have_en0(self):
        write_trace(self.path, [(2e-3, 0.0, -1e-6)])
        with self.assertRaises(SystemExit):
            so.offstate_current(self.path)


class MainHashCheck(unittest.TestCase):
    RID = "synthetic-run"

    def _build(self, tmp, sha_override=None):
        rec = os.path.join(tmp, "records")
        tdir = os.path.join(rec, f"{self.RID}-startup-grid.traces")
        os.makedirs(tdir)
        tp = os.path.join(tdir, "pt.csv.gz")
        write_trace(tp, [(0.0, 0.0, -1e-6), (9e-4, 0.0, -2e-6), (2e-3, VIN, -1e-3)])
        with open(tp, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        with open(os.path.join(rec, f"{self.RID}-startup-grid.csv"), "w", newline="") as fh:
            fh.write("mos,temp,res,vin,trace_file,trace_sha256\n")
            fh.write(f"tt,27,typ,3.3,traces/pt.csv.gz,{sha_override or sha}\n")

    def _run_main(self, tmp):
        old = (so.HERE, sys.argv, sys.stdout, sys.stderr)
        so.HERE = tmp
        sys.argv = ["startup_offstate.py", self.RID]
        sys.stdout = sys.stderr = open(os.devnull, "w")
        try:
            so.main()
        finally:
            sys.stdout.close()
            so.HERE, sys.argv, sys.stdout, sys.stderr = old

    def test_matching_hash_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._build(tmp)
            self._run_main(tmp)

    def test_raises_on_trace_sha256_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._build(tmp, sha_override="0" * 64)
            with self.assertRaises(SystemExit) as cm:
                self._run_main(tmp)
            self.assertIn("trace_sha256", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
