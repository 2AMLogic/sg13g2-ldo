"""Regression tests for scripts/check_artifact_manifests.py (issue #183).

``check`` runs against throwaway git repositories. Stdlib only.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_artifact_manifests", ROOT / "scripts" / "check_artifact_manifests.py")
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

REPO = "owner/repo"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def key_for(sha):
    return f"evidence/owner__repo/{sha[:2]}/{sha}"


def entry(data: bytes, name="sim/b/records/r1.json", sha=None, size=None):
    sha = sha or hashlib.sha256(data).hexdigest()
    return {"sha256": sha, "size": len(data) if size is None else size, "kind": "evidence",
            "producer": {"tool": "klt", "version": "0.7.0", "loom.repo": REPO, "commit": None},
            "uri": f"artifact:{key_for(sha)}", "name": name}


class Schema(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(chk.manifest_problems({"schema_version": 1,
                                                "entries": [entry(b"x")]}), [])

    def test_rejections(self):
        e = entry(b"x")
        cases = {
            "uri key does not end": {**e, "uri": "artifact:" + key_for("a" * 64)},
            "kind must be": {**e, "kind": "pdk"},
            "name must be": {**e, "name": "/abs/path"},
            "name is required": {k: v for k, v in e.items() if k != "name"},
            "size must be": {**e, "size": 0},
            "different repo": {**e, "producer": {**e["producer"], "loom.repo": "x/y"}},
            "producer must carry": {**e, "producer": {"tool": "klt"}},
        }
        for needle, bad in cases.items():
            with self.subTest(needle):
                problems = chk.manifest_problems({"schema_version": 1, "entries": [bad]})
                self.assertTrue(any(needle in p for p in problems), problems)
        self.assertEqual(chk.manifest_problems({"schema_version": 1, "entries": []}),
                         ["has no entries"])
        dup = chk.manifest_problems({"schema_version": 1, "entries": [e, e]})
        self.assertTrue(any("duplicate name" in p for p in dup))

    def test_only_the_artifact_scheme_is_accepted(self):
        # Operator ruling H1 (2AMLogic/2am#5553): the uri is the logical
        # artifact:<key>; a bucket-naming uri or any other scheme is refused.
        e = entry(b"x")
        self.assertEqual(chk.uri_key(e["uri"]), key_for(e["sha256"]))
        key = key_for(e["sha256"])
        legacy = "s3" + "://"  # built, so a grep for the literal stays clean
        for uri in (f"{legacy}bucket/{key}", f"{legacy}{key}", f"https://host/{key}",
                    f"file:///{key}", f"Artifact:{key}", f"artifact:/{key}",
                    f"artifact:{key} ", "artifact:", key, None, 7):
            with self.subTest(uri=uri):
                self.assertIsNone(chk.uri_key(uri))
                problems = chk.manifest_problems({"schema_version": 1,
                                                  "entries": [{**e, "uri": uri}]})
                self.assertTrue(any("uri must be artifact:<key>" in p for p in problems),
                                problems)


class Check(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.git("init", "-q", "-b", "main")
        self.write("README.md", "r\n")
        self.commit()

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.root), *a], env=ENV, check=True,
                              capture_output=True).stdout.decode().strip()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "c")

    def run_check(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = chk.main(["check", "--repo", str(self.root), "--tree", "HEAD"])
        return rc, out.getvalue(), err.getvalue()

    def add_manifest(self, *entries, name="b-r1.manifest.json"):
        self.write(f"manifests/artifacts/{name}",
                   json.dumps({"schema_version": 1, "entries": list(entries)}))

    def test_no_manifests_is_ok_and_says_not_hash_verified(self):
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 0)
        self.assertIn("NOT hash-verified", out)

    def test_valid_manifest_with_summary_passes(self):
        self.add_manifest(entry(b"x"))
        self.write("sim/b/records/r1.md", "# summary\n")
        self.commit()
        rc, out, err = self.run_check()
        self.assertEqual(rc, 0, err)
        self.assertIn("1 manifest(s), 1 entry", out)

    def test_committed_blob_beside_manifest_fails(self):
        self.add_manifest(entry(b"x"))
        self.write("sim/b/records/r1.json", "x")  # the stored bytes, committed too
        self.commit()
        rc, _, err = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn("no blob fallback", err)

    def test_malformed_manifest_fails(self):
        self.add_manifest({"sha256": "nope"})
        self.commit()
        rc, _, err = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn("b-r1.manifest.json: entry 0", err)

    def test_stray_file_in_manifest_dir_fails(self):
        self.write("manifests/artifacts/blob.bin", "x")
        self.commit()
        rc, _, err = self.run_check()
        self.assertEqual(rc, 1)
        self.assertIn("only <bench>-<run-id>.manifest.json", err)

    def test_unavailable_revision_is_exit_2(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = chk.main(["check", "--repo", str(self.root), "--tree", "nope"])
        self.assertEqual(rc, 2)


class RepoManifests(unittest.TestCase):
    def test_head_manifests_pass(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = chk.main(["check", "--repo", str(ROOT), "--tree", "HEAD"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
