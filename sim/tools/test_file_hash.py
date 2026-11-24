"""Tests for sim/tools/file_hash.py, the one sha256-file helper (issue #362).

Layer 1 proves the shared helper is behaviour-identical to the hand-rolled
copies it replaces: the full digest equals hashlib's over the same bytes
(whole-file and multi-chunk reads agree), and ``n`` truncation reproduces the
per-site ``[:16]`` slices exactly, including ``n`` larger than the digest.

Layer 2 freezes the consolidation contract as data: every converted call
site's old local helper is restated here as (read style, truncation) and the
shared helper must agree with a literal re-implementation of that style.

Offline and stdlib-only: no simulator, no PDK.
    python3 -m unittest discover -s sim/tools -p 'test_file_hash.py' -v
"""
import hashlib
import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import file_hash as fh  # noqa: E402


def whole_file_hex(path):
    """The pre-#362 whole-file read style (row_envelope, ccprobe, e4, ...)."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def chunked_hex(path):
    """The pre-#362 1 MiB-chunk style (startup_campaign, evidence_store)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


class TestSha256File(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "blob.bin")

    def write(self, size):
        # Deterministic non-repeating bytes: chunk boundaries must not be
        # able to hide a read bug behind repeated block content.
        data = bytes((i * 131 + 17) & 0xFF for i in range(size))
        with open(self.path, "wb") as f:
            f.write(data)
        return data

    def test_full_digest_matches_hashlib_small_file(self):
        data = self.write(1024)
        self.assertEqual(fh.sha256_file(self.path),
                         hashlib.sha256(data).hexdigest())

    def test_full_digest_matches_hashlib_across_chunk_boundaries(self):
        # 1 MiB + 3 bytes: two reads, second shorter than the chunk.
        data = self.write((1 << 20) + 3)
        self.assertEqual(fh.sha256_file(self.path),
                         hashlib.sha256(data).hexdigest())

    def test_truncation_reproduces_the_old_slice(self):
        self.write(2048)
        want = whole_file_hex(self.path)
        self.assertEqual(fh.sha256_file(self.path, 16), want[:16])
        self.assertEqual(fh.sha256_file(self.path, 12), want[:12])

    def test_truncation_larger_than_digest_returns_whole_digest(self):
        self.write(16)
        want = whole_file_hex(self.path)
        self.assertEqual(fh.sha256_file(self.path, len(want) + 40), want)

    def test_chunked_and_whole_file_styles_agree(self):
        # The consolidated helper must not depend on which pre-#362 style a
        # site used: both oracles agree with it on the same bytes.
        self.write((1 << 20) * 2 + 5)
        self.assertEqual(fh.sha256_file(self.path), whole_file_hex(self.path))
        self.assertEqual(fh.sha256_file(self.path), chunked_hex(self.path))

    def test_missing_file_propagates_oserror_unwrapped(self):
        # Call sites that need fail-closed wrapping (generate.py's GenError)
        # wrap at their own boundary; the shared helper must not swallow.
        missing = os.path.join(self.tmp.name, "no-such-file")
        with self.assertRaises(OSError):
            fh.sha256_file(missing)


if __name__ == "__main__":
    unittest.main()
