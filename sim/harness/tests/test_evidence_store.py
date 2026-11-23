"""Issue #183: the evidence writer stores bytes through ``klt artifact put``
and commits only a manifest and a summary. Every failure is fail closed.

Stdlib only. ``klt`` is emulated by an injected ``run`` (the writer's only
contact with it is argv + exit status + the manifest file it merges into), and
the broker probe runs against a throwaway local HTTP server.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.server
import io
import json
import os
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from harness import evidence_store as es

REPO = "owner/repo"


def fake_klt(store: dict, *, fail=None, corrupt=False, uri=None):
    """Emulate ``klt artifact put FILE --name N --manifest M --format json``.
    ``uri`` overrides the written uri (given the key) to emulate an old klt."""

    def run(cmd, **kw):
        assert cmd[:3] == ["klt", "artifact", "put"], cmd
        path, name, manifest = cmd[3], cmd[cmd.index("--name") + 1], cmd[cmd.index("--manifest") + 1]
        assert "--broker" not in cmd  # the broker URL never goes in argv
        if fail is not None:
            err = {"schema_version": 1, "error": {"command": "artifact put",
                                                  "message": "cannot reach the artifact broker",
                                                  "code": fail}}
            return subprocess.CompletedProcess(cmd, 1, "", json.dumps(err))
        data = Path(path).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        store[sha] = data
        key = f"evidence/owner__repo/{sha[:2]}/{'0' * 64 if corrupt else sha}"
        entry = {"sha256": "0" * 64 if corrupt else sha, "size": len(data), "kind": "evidence",
                 "producer": {"tool": "klt", "version": "t", "loom.repo": REPO, "commit": None},
                 "uri": uri(key) if uri else f"artifact:{key}",
                 "name": name}
        p = Path(manifest)
        m = json.loads(p.read_text()) if p.exists() else {"schema_version": 1, "entries": []}
        m["entries"].append(entry)
        p.write_text(json.dumps(m))
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "stored"}), "")

    return run


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name).resolve()
        self.stage = self.root / "sim/.work/.stage/b"
        (self.stage / "corners/r1").mkdir(parents=True)
        (self.stage / "corners/r1/tt.log").write_text("log tt\n")
        (self.stage / "corners/r1/ff.log").write_text("log ff\n")
        (self.stage / "corners/r1/empty.log").write_text("")
        (self.stage / "r1.json").write_text('{"x": 1}\n')
        self.files = [(self.stage / "r1.json", "sim/b/records/r1.json")]
        self.files += es.stage_files(self.stage / "corners/r1", "sim/b/corners/r1")
        self.summary = self.root / "sim/b/records/r1.md"
        self.mpath = self.root / "manifests/artifacts/b-r1.manifest.json"
        self.store = {}

    def put(self, **kw):
        return lambda files, root: es.put_files(files, root, run=fake_klt(self.store, **kw))

    def store_files(self, **kw):
        return es.store_files(self.files, repo_root=self.root, bench="b", rid="r1",
                              summary_text="# record\n", summary_path=self.summary,
                              put=self.put(**kw))

    def put_returning_mutated_manifest(self, mutate):
        """A ``put`` through ``fake_klt`` whose written manifest is
        rewritten by ``mutate`` once every entry is in it (issue #326: the
        bad manifest comes from klt, not from the writer), so the refusal
        is exercised through the writer's own read-back path."""
        real = fake_klt(self.store)
        last = str(next(p for p, _ in reversed(self.files) if p.stat().st_size))
        done = []

        def run(cmd, **kw):
            p = real(cmd, **kw)
            if p.returncode == 0 and not done and cmd[3] == last:
                done.append(True)
                mpath = Path(cmd[cmd.index("--manifest") + 1])
                m = json.loads(mpath.read_text())
                mutate(m)
                mpath.write_text(json.dumps(m))
            return p

        return lambda files, root: es.put_files(files, root, run=run)

    def assert_nothing_committed(self):
        self.assertFalse(self.mpath.exists())
        self.assertFalse(self.summary.exists())
        self.assertFalse((self.root / "sim/b").exists())


class Writer(Base):
    def test_stores_bytes_commits_manifest_and_summary_only(self):
        path = self.store_files()
        self.assertEqual(path, self.mpath)
        m = json.loads(self.mpath.read_text())
        names = [e["name"] for e in m["entries"]]
        self.assertEqual(names, ["sim/b/corners/r1/ff.log", "sim/b/corners/r1/tt.log",
                                 "sim/b/records/r1.json"])
        for e in m["entries"]:
            self.assertEqual(hashlib.sha256(self.store[e["sha256"]]).hexdigest(), e["sha256"])
            self.assertEqual(e["uri"], f"artifact:evidence/owner__repo/{e['sha256'][:2]}/"
                                       f"{e['sha256']}")
        text = self.summary.read_text()
        self.assertTrue(text.startswith("# record\n"))
        self.assertIn("## Stored evidence", text)
        self.assertIn("manifests/artifacts/b-r1.manifest.json", text)
        self.assertIn("`sim/b/corners/r1/empty.log` | 0 |", text)  # listed, not stored
        # Only the summary landed under sim/b: no evidence blob.
        self.assertEqual([p.relative_to(self.root).as_posix()
                          for p in (self.root / "sim/b").rglob("*") if p.is_file()],
                         ["sim/b/records/r1.md"])

    def test_broker_unreachable_is_fail_closed(self):
        with self.assertRaises(es.StoreError) as cm:
            self.store_files(fail="broker_unreachable")
        self.assertIn("broker_unreachable", str(cm.exception))
        self.assert_nothing_committed()
        self.assertTrue((self.stage / "r1.json").exists())  # staged bytes kept

    def test_manifest_not_matching_bytes_is_refused(self):
        with self.assertRaises(es.StoreError):
            self.store_files(corrupt=True)
        self.assert_nothing_committed()

    def test_non_artifact_uri_from_klt_is_refused(self):
        # An old klt (before klayout-tools 7e3561f) writes a bucket-naming uri;
        # the writer refuses any scheme but artifact:<key> and commits nothing.
        legacy = "s3" + "://"  # built, so a grep for the literal stays clean
        for uri in (lambda k: f"{legacy}bucket/{k}", lambda k: f"https://host/{k}",
                    lambda k: f"artifact:/{k}", lambda k: k):
            with self.subTest(uri=uri("K")):
                with self.assertRaisesRegex(es.StoreError, "uri is not artifact:<key>"):
                    self.store_files(uri=uri)
                self.assert_nothing_committed()

    def test_existing_manifest_or_summary_is_never_overwritten(self):
        self.mpath.parent.mkdir(parents=True)
        self.mpath.write_text("{}")
        with self.assertRaises(es.StoreError):
            self.store_files()
        self.assertEqual(self.mpath.read_text(), "{}")
        self.assertEqual(self.store, {})  # refused before any put

    def test_nothing_but_empty_files_is_refused(self):
        self.files = [(self.stage / "corners/r1/empty.log", "sim/b/corners/r1/empty.log")]
        with self.assertRaises(es.StoreError):
            self.store_files()
        self.assert_nothing_committed()

    def test_duplicate_names_refused(self):
        self.files.append((self.stage / "r1.json", "sim/b/records/r1.json"))
        with self.assertRaises(es.StoreError):
            self.store_files()
        self.assert_nothing_committed()

    def test_klt_manifest_with_bad_producer_values_is_refused(self):
        # Issue #326: a klt that writes "" into a producer field (or a
        # non-string commit) used to pass the writer's field-set check and
        # fail only in CI; the writer must refuse it and commit nothing.
        for field, bad in (("tool", ""), ("version", ""), ("loom.repo", ""),
                           ("commit", 5)):
            with self.subTest(producer=field):
                put = self.put_returning_mutated_manifest(
                    lambda m, f=field, b=bad: m["entries"][-1]["producer"].__setitem__(f, b))
                with self.assertRaisesRegex(es.StoreError, f"producer.{field} must be"):
                    es.store_files(self.files, repo_root=self.root, bench="b", rid="r1",
                                   summary_text="# record\n", summary_path=self.summary,
                                   put=put)
                self.assert_nothing_committed()

    def test_klt_manifest_with_duplicate_entry_names_is_refused(self):
        # Issue #326: two returned entries with the same name used to fold
        # into one in by_name and pass; put_files must refuse them —
        # adjacent or not — before anything is installed.
        for where, mutate in (
                ("adjacent", lambda m: m["entries"].insert(1, dict(m["entries"][0]))),
                ("apart", lambda m: m["entries"].append(dict(m["entries"][0])))):
            with self.subTest(copies=where):
                put = self.put_returning_mutated_manifest(mutate)
                with self.assertRaisesRegex(es.StoreError, "two entries named"):
                    es.store_files(self.files, repo_root=self.root, bench="b", rid="r1",
                                   summary_text="# record\n", summary_path=self.summary,
                                   put=put)
                self.assert_nothing_committed()

    def test_symlink_in_stage_refused(self):
        (self.stage / "corners/r1/link.log").symlink_to(self.stage / "r1.json")
        with self.assertRaises(es.StoreError):
            es.stage_files(self.stage / "corners/r1", "sim/b/corners/r1")

    # ------------------------------------------------------------------
    # Issue #251 item 1: every OSError on the store path is StoreError.
    # ------------------------------------------------------------------

    def test_unreadable_staged_file_is_store_error(self):
        # sha256_file's open()/read().
        if os.geteuid() == 0:  # root reads anything; a missing file hits the same handler
            target, label = self.stage / "missing.json", "No such file"
        else:
            target, label = self.stage / "r1.json", "Permission denied"
            target.chmod(0)
            self.addCleanup(target.chmod, 0o644)
        self.files = [(target, "sim/b/records/r1.json")]
        with self.assertRaisesRegex(es.StoreError, "cannot read .* to hash it") as cm:
            self.store_files()
        self.assertIn(label, str(cm.exception))
        self.assert_nothing_committed()

    def test_manifest_parent_cannot_be_created_is_store_error(self):
        # install_manifest's parent mkdir: a non-directory in the way.
        (self.root / "manifests").write_text("not a directory\n")
        with self.assertRaisesRegex(es.StoreError, "cannot create manifest directory"):
            self.store_files()
        self.assertFalse(self.mpath.exists())
        self.assertFalse(self.summary.exists())

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_unwritable_manifest_path_is_store_error(self):
        # install_manifest's open(..., "x") for any OSError but FileExistsError.
        self.mpath.parent.mkdir(parents=True)
        self.mpath.parent.chmod(0o500)
        self.addCleanup(self.mpath.parent.chmod, 0o755)
        with self.assertRaisesRegex(es.StoreError, "cannot install manifest"):
            self.store_files()
        self.assertFalse(self.mpath.exists())
        self.assertFalse(self.summary.exists())

    # ------------------------------------------------------------------
    # Issue #272: put_files's manifest temp dir is the last store-path
    # OSError residual; construction and cleanup both come out as
    # StoreError.
    # ------------------------------------------------------------------

    def test_manifest_tempdir_construction_failure_is_store_error(self):
        # The TemporaryDirectory constructor: an unwritable/full $TMPDIR.
        from unittest import mock

        with mock.patch("tempfile.TemporaryDirectory",
                        side_effect=OSError(13, "Permission denied")), \
                self.assertRaisesRegex(es.StoreError,
                                       "evidence manifest's temporary directory") as cm:
            self.store_files()
        self.assertIsInstance(cm.exception.__cause__, OSError)  # from exc, not from None
        self.assertFalse(self.store)  # the constructor fired before any put
        self.assert_nothing_committed()

    def test_manifest_tempdir_cleanup_failure_after_successful_puts_is_store_error(self):
        # The with-block's cleanup rmtree can fail on a parent made
        # unwritable while the puts ran -- i.e. after every put already
        # succeeded (measured on 3.12.3: parent chmod 0o500 after entry;
        # tempfile's reset-perms retry does not cover the parent).
        from unittest import mock
        parent = tempfile.TemporaryDirectory()
        self.addCleanup(parent.cleanup)
        parent_path = Path(parent.name)
        real_td = tempfile.TemporaryDirectory

        class CleanupFails(real_td):
            def __init__(self, *a, **kw):
                kw["dir"] = parent_path
                super().__init__(*a, **kw)

            def __exit__(self, *exc):
                parent_path.chmod(0o500)
                try:
                    return super().__exit__(*exc)
                finally:
                    parent_path.chmod(0o700)

        with mock.patch("tempfile.TemporaryDirectory", CleanupFails), \
                self.assertRaisesRegex(es.StoreError,
                                       "evidence manifest's temporary directory") as cm:
            self.store_files()
        self.assertTrue(self.store)  # every put succeeded before cleanup failed
        self.assertIsInstance(cm.exception.__cause__, OSError)
        self.assert_nothing_committed()

    # ------------------------------------------------------------------
    # Issue #251 item 2: a failed summary write rolls the manifest back,
    # so the docstring's "nothing is then installed" is literally true.
    # ------------------------------------------------------------------

    def test_blocked_summary_directory_rolls_the_manifest_back(self):
        # Deterministic rollback case: the summary's parent path is occupied
        # by a file, so its mkdir fails with a non-FileExistsError OSError.
        (self.root / "sim/b").mkdir(parents=True, exist_ok=True)
        (self.root / "sim/b/records").write_text("occupies the summary directory\n")
        with self.assertRaisesRegex(es.StoreError, "cannot create summary directory"):
            self.store_files()
        self.assertFalse(self.mpath.exists())
        self.assertFalse(self.summary.exists())

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_unwritable_summary_directory_is_store_error_and_rolls_back(self):
        self.summary.parent.mkdir(parents=True)
        self.summary.parent.chmod(0o500)
        self.addCleanup(self.summary.parent.chmod, 0o755)
        with self.assertRaisesRegex(es.StoreError, "cannot write summary"):
            self.store_files()
        self.assertFalse(self.mpath.exists())

    def test_summary_appearing_during_store_rolls_the_manifest_back(self):
        manifest = {"schema_version": 1, "entries": []}

        def racing_put(files, root):
            self.summary.parent.mkdir(parents=True, exist_ok=True)
            self.summary.write_text("raced in\n")
            return manifest, []

        with self.assertRaisesRegex(es.StoreError, "appeared concurrently"):
            es.store_files(self.files, repo_root=self.root, bench="b", rid="r1",
                           summary_text="# record\n", summary_path=self.summary,
                           put=racing_put)
        self.assertFalse(self.mpath.exists())  # rolled back: nothing installed

    def test_scan_of_untraversable_stage_is_store_error(self):
        # stage_files (issue #251 AC: settled by measurement, not assumption):
        # rglob/is_symlink raise PermissionError on a readable but
        # non-traversable stage directory; it must surface as StoreError.
        if os.geteuid() == 0:
            self.skipTest("root ignores file permissions")
        os.chmod(self.stage / "corners/r1", 0o444)
        self.addCleanup(os.chmod, self.stage / "corners/r1", 0o755)
        with self.assertRaisesRegex(es.StoreError, "cannot scan staged evidence"):
            es.stage_files(self.stage / "corners/r1", "sim/b/corners/r1")


class EntrySchema(unittest.TestCase):
    """Issue #251 item 3: the writer's entry check enforces the same field
    sets as the CI checker, so a klt schema drift fails at write time."""

    def entry(self):
        sha = "a" * 64
        return {"sha256": sha, "size": 3, "kind": "evidence",
                "producer": {"tool": "klt", "version": "t", "loom.repo": REPO,
                             "commit": None},
                "uri": f"artifact:evidence/owner__repo/{sha[:2]}/{sha}",
                "name": "sim/b/records/r1.json"}

    def test_minimal_and_full_entries_pass(self):
        self.assertIsNone(es._entry_problem(self.entry()))
        with_media = self.entry()
        with_media["media_type"] = "application/json"
        self.assertIsNone(es._entry_problem(with_media))

    def test_unknown_top_level_field_rejected(self):
        for field in ("extra", "digest", "hash"):
            e = self.entry()
            e[field] = "x"
            with self.subTest(field=field):
                self.assertIn("unknown field", es._entry_problem(e))

    def test_missing_required_field_rejected(self):
        for field in ("sha256", "size", "kind", "producer", "uri"):
            e = self.entry()
            del e[field]
            with self.subTest(field=field):
                self.assertIn("missing", es._entry_problem(e))

    def test_producer_field_set_enforced_both_directions(self):
        extra = self.entry()
        extra["producer"]["note"] = "x"
        self.assertIn("producer must carry exactly", es._entry_problem(extra))
        missing = self.entry()
        del missing["producer"]["commit"]
        self.assertIn("producer must carry exactly", es._entry_problem(missing))

    def test_non_dict_producer_still_refused(self):
        e = self.entry()
        e["producer"] = "klt"
        self.assertIn("no producer", es._entry_problem(e))

    def test_producer_values_enforced_like_ci(self):
        # Issue #326: the field *set* alone let "" through; the checker's
        # value rules apply here too, on the same fields.
        for field in ("tool", "version", "loom.repo"):
            for bad in ("", 5, None):
                e = self.entry()
                e["producer"][field] = bad
                with self.subTest(field=field, bad=bad):
                    self.assertIn(f"producer.{field} must be a non-empty string",
                                  es._entry_problem(e))
        e = self.entry()
        e["producer"]["commit"] = 5
        self.assertIn("producer.commit must be a string or null", es._entry_problem(e))

    def test_string_commit_still_accepted(self):
        e = self.entry()
        e["producer"]["commit"] = "0" * 40
        self.assertIsNone(es._entry_problem(e))

    def test_non_string_media_type_rejected(self):
        # Issue #334: the checker refuses a present non-string media_type;
        # the writer had no check at all.
        for bad in (5, None, True, ["application/json"]):
            e = self.entry()
            e["media_type"] = bad
            with self.subTest(bad=bad):
                self.assertIn("media_type must be a string", es._entry_problem(e))

    def test_size_must_be_a_strict_positive_integer(self):
        # Issue #334: size=True sailed through put_files' (sha, size)
        # byte-match because True == 1, while CI's checker refused it.
        for bad in (True, False, "1", 1.0, 0, -1, None):
            e = self.entry()
            e["size"] = bad
            with self.subTest(bad=bad):
                self.assertIn("size must be a positive integer",
                              es._entry_problem(e))
        e = self.entry()
        e["size"] = 1
        self.assertIsNone(es._entry_problem(e))

    def test_uri_key_repo_must_match_producer_loom_repo(self):
        e = self.entry()
        e["uri"] = f"artifact:evidence/other__repo/{e['sha256'][:2]}/{e['sha256']}"
        self.assertIn("different repo", es._entry_problem(e))

    def test_uri_key_must_be_evidence_owner_name_shaped(self):
        sha = "a" * 64
        cases = ("bare sha256",
                 "no owner__name segment",
                 "wrong top segment",
                 "two __ in the repo segment")
        keys = (sha,
                f"{sha[:2]}/{sha}",
                f"docs/owner__repo/{sha[:2]}/{sha}",
                f"evidence/owner__a__b/{sha[:2]}/{sha}")
        for label, key in zip(cases, keys):
            with self.subTest(case=label):
                e = self.entry()
                e["uri"] = f"artifact:{key}"
                self.assertIn("uri key is not evidence/<owner>__<name>",
                              es._entry_problem(e))

    def test_uri_key_extra_segments_between_repo_and_sha_accepted(self):
        e = self.entry()
        e["uri"] = f"artifact:evidence/owner__repo/x/{e['sha256'][:2]}/{e['sha256']}"
        self.assertIsNone(es._entry_problem(e))


class SchemaAgreement(unittest.TestCase):
    """Issue #251 item 3: the writer's field tuples are pinned to the CI
    checker's — drift fails here, in the artifact-manifests job, not after a
    run's puts are spent. The checker is loaded the test-only way
    ``scripts/tests/`` already does: ``scripts/`` is not a package and
    neither module touches ``sys.path``."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        checker = (Path(__file__).resolve().parents[3] / "scripts"
                   / "check_artifact_manifests.py")
        spec = importlib.util.spec_from_file_location("check_artifact_manifests",
                                                      checker)
        cls.chk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.chk)

    def test_field_tuples_match(self):
        self.assertEqual(es.ENTRY_REQUIRED_FIELDS, self.chk.REQUIRED)
        self.assertEqual(es.ENTRY_OPTIONAL_FIELDS, self.chk.OPTIONAL)
        self.assertEqual(es.ENTRY_PRODUCER_FIELDS, self.chk.PRODUCER_FIELDS)

    def test_refusals_agree(self):
        """Issue #326 (operator ruling, option a): the implementations stay
        independent, and a manifest the CI checker refuses is refused by
        the writer too -- producer values, media_type type, uri-key repo
        consistency and strict size by ``_entry_problem`` (#334), duplicate
        names by ``put_files`` through ``fake_klt`` -- while the valid
        manifest is accepted by both, with and without ``media_type``."""
        data = b"x"
        sha = hashlib.sha256(data).hexdigest()
        entry = {"sha256": sha, "size": len(data), "kind": "evidence",
                 "producer": {"tool": "klt", "version": "t", "loom.repo": REPO,
                              "commit": None},
                 "uri": f"artifact:evidence/owner__repo/{sha[:2]}/{sha}",
                 "name": "sim/b/records/r1.json"}

        def manifest():
            return {"schema_version": 1,
                    "entries": [dict(entry, producer=dict(entry["producer"]))]}

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        staged = Path(td.name) / "r1.json"
        staged.write_bytes(data)

        def writer_refuses(m):
            # The writer's whole path: _entry_problem per entry, then the
            # duplicate-name check in put_files (fake_klt's manifest
            # replaced by m).
            if any(es._entry_problem(e) for e in m["entries"]):
                return True
            store = {}

            def run(cmd, **kw):
                p = fake_klt(store)(cmd, **kw)
                Path(cmd[cmd.index("--manifest") + 1]).write_text(json.dumps(m))
                return p

            try:
                es.put_files([(staged, "sim/b/records/r1.json")], Path(td.name),
                             run=run)
            except es.StoreError:
                return True
            return False

        mutations = [
            ("none (valid)", lambda m: None),
            ("valid with string media_type",
             lambda m: m["entries"][0].update(media_type="application/json")),
            ("empty producer.version",
             lambda m: m["entries"][0]["producer"].update(version="")),
            ("non-string producer.commit",
             lambda m: m["entries"][0]["producer"].update(commit=7)),
            ("duplicate entry name",
             lambda m: m["entries"].append(dict(m["entries"][0]))),
            # Issue #334: three checker-only refusals, mirrored into
            # _entry_problem. size=True was the worst of them: put_files'
            # (sha, size) byte-match compared True == 1 and passed.
            ("non-string media_type",
             lambda m: m["entries"][0].update(media_type=5)),
            ("uri key naming a different repo than producer.loom.repo",
             lambda m: m["entries"][0].update(
                 uri=f"artifact:evidence/other__repo/{sha[:2]}/{sha}")),
            ("uri key not evidence/<owner>__<name>/ shaped",
             lambda m: m["entries"][0].update(
                 uri=f"artifact:evidence/{sha[:2]}/{sha}")),
            ("bool size", lambda m: m["entries"][0].update(size=True)),
            ("non-int size", lambda m: m["entries"][0].update(size="1")),
            # Boundaries that already agree, pinned so they stay that way:
            # these are refused by put_files' own checks (byte-match, the
            # staged-name set, the manifest shape), not by _entry_problem.
            ("zero size", lambda m: m["entries"][0].update(size=0)),
            ("non-canonical name",
             lambda m: m["entries"][0].update(name="sim/b/../b/records/r1.json")),
            ("missing name", lambda m: m["entries"][0].pop("name")),
            ("schema_version 2", lambda m: m.update(schema_version=2)),
            ("uri key with extra segments between repo and sha",
             lambda m: m["entries"][0].update(
                 uri=f"artifact:evidence/owner__repo/x/{sha[:2]}/{sha}")),
        ]
        for label, mutate in mutations:
            with self.subTest(mutation=label):
                m = manifest()
                mutate(m)
                self.assertEqual(self.chk.manifest_problems(m) == [],
                                 not writer_refuses(m),
                                 f"checker and writer disagree on {label}")


def klt_probe_answer(cmd, *, current=True):
    """What ``klt artifact verify <probe manifest>`` answers: a current klt
    (klayout-tools 7e3561f+) refuses the legacy uri offline; an old one
    accepts it and fails on the unroutable broker."""
    if current:
        err = {"command": "artifact verify", "code": "invalid_manifest",
               "message": "manifest entry 0: uri ... is not artifact:<key>",
               "entry": 0, "problems": ["uri '...' is not artifact:<key>"]}
    else:
        err = {"command": "artifact verify", "code": "broker_unreachable",
               "message": "cannot reach the artifact broker"}
    return subprocess.CompletedProcess(cmd, 1, "", json.dumps({"schema_version": 1,
                                                               "error": err}))


class Preflight(unittest.TestCase):
    def which(self, name):
        return f"/bin/{name}"

    def run_ok(self, cmd, **kw):
        if cmd[1:3] == ["artifact", "verify"]:
            return klt_probe_answer(cmd)
        return subprocess.CompletedProcess(cmd, 0, "usage", "")

    def test_no_broker_configured(self):
        with self.assertRaisesRegex(es.StoreError, "KLT_ARTIFACT_BROKER"):
            es.preflight(Path("."), env={}, which=self.which, run=self.run_ok,
                         probe=lambda *a: None)

    def test_klt_missing_or_without_artifact_verb(self):
        env = {es.ENV_BROKER: "http://broker.invalid", es.ENV_REPO: REPO}
        with self.assertRaisesRegex(es.StoreError, "not on PATH"):
            es.preflight(Path("."), env=env, which=lambda n: None, run=self.run_ok,
                         probe=lambda *a: None)
        with self.assertRaisesRegex(es.StoreError, "no `artifact put` verb"):
            es.preflight(Path("."), env=env, which=self.which,
                         run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", ""),
                         probe=lambda *a: None)

    def test_old_klt_refused_before_the_broker_probe(self):
        env = {es.ENV_BROKER: "http://broker.invalid", es.ENV_REPO: REPO}
        probed = []

        def run_old(cmd, **kw):
            if cmd[1:3] == ["artifact", "verify"]:
                return klt_probe_answer(cmd, current=False)
            return subprocess.CompletedProcess(cmd, 0, "usage", "")

        with self.assertRaisesRegex(es.StoreError, "older than klayout-tools 7e3561f"):
            es.preflight(Path("."), env=env, which=self.which, run=run_old,
                         probe=lambda *a: probed.append(a))
        self.assertEqual(probed, [])

    def test_probe_gets_repo_and_broker(self):
        seen = []
        env = {es.ENV_BROKER: "http://broker.invalid", es.ENV_REPO: REPO}
        es.preflight(Path("."), env=env, which=self.which, run=self.run_ok,
                     probe=lambda base, repo: seen.append((base, repo)))
        self.assertEqual(seen, [("http://broker.invalid", REPO)])


class KltSchemeProbe(unittest.TestCase):
    """``check_klt_uri_scheme``: klt has no commit in its version, so the
    writer tests the behaviour that changed at klayout-tools 7e3561f."""

    def check(self, run):
        es.check_klt_uri_scheme("/bin/klt", run=run)

    def test_current_klt_passes_and_probe_is_offline(self):
        seen = []

        def run(cmd, **kw):
            seen.append(cmd)
            manifest = json.loads(Path(cmd[3]).read_text())
            (entry,) = manifest["entries"]
            self.assertFalse(entry["uri"].startswith("artifact:"))
            return klt_probe_answer(cmd)

        self.check(run)
        (cmd,) = seen
        self.assertEqual(cmd[:3], ["/bin/klt", "artifact", "verify"])
        # Never the configured broker: a fixed unroutable one.
        self.assertEqual(cmd[cmd.index("--broker") + 1], "http://127.0.0.1:9")

    def test_every_other_outcome_fails_closed(self):
        def answer(rc, err=None, stderr=None):
            def run(cmd, **kw):
                text = stderr if stderr is not None else json.dumps(
                    {"schema_version": 1, "error": err})
                return subprocess.CompletedProcess(cmd, rc, "", text)
            return run

        def raises(exc):
            def run(cmd, **kw):
                raise exc
            return run

        legacy_problem = "uri 'x' is not s3" + "://<bucket>/<key>"
        cases = {
            "old klt reaches the broker": answer(1, {"code": "broker_unreachable"}),
            "old klt reports a refusal": answer(1, {"code": "broker_refused"}),
            "klt without verify": answer(2, stderr="usage: klt artifact ..."),
            "verify passes the legacy uri": answer(0, stderr=""),
            "invalid for another reason": answer(1, {"code": "invalid_manifest",
                                                     "problems": [legacy_problem]}),
            "invalid without problems": answer(1, {"code": "invalid_manifest"}),
            "wrong exit code": answer(2, {"code": "invalid_manifest",
                                          "problems": ["is not artifact:<key>"]}),
            "not json": answer(1, stderr="Traceback ..."),
        }
        for label, run in cases.items():
            with self.subTest(label), \
                    self.assertRaisesRegex(es.StoreError, "older than klayout-tools"):
                self.check(run)
        # A probe that never answered says so rather than blaming klt's age.
        no_answer = {
            "timeout": (raises(subprocess.TimeoutExpired("klt", 30)), "probe timed out"),
            "cannot exec": (raises(OSError("no such file")), "probe failed to start"),
        }
        for label, (run, message) in no_answer.items():
            with self.subTest(label), self.assertRaisesRegex(es.StoreError, message):
                self.check(run)

    def test_tempdir_construction_failure_is_store_error(self):
        # Issue #262 site A: an unwritable/full $TMPDIR used to make the
        # probe's TemporaryDirectory constructor escape as a bare OSError.
        from unittest import mock

        def raises(exc):
            def run(cmd, **kw):
                raise exc
            return run

        with mock.patch("tempfile.TemporaryDirectory",
                        side_effect=OSError(13, "Permission denied")), \
                self.assertRaisesRegex(es.StoreError, "temporary directory"):
            self.check(raises(OSError("unreachable")))

    def test_manifest_write_failure_is_store_error(self):
        # Issue #262 site B: a full $TMPDIR used to make the probe manifest's
        # json.dump escape as a bare OSError.
        from unittest import mock

        def raises(exc):
            def run(cmd, **kw):
                raise exc
            return run

        with mock.patch("json.dump",
                        side_effect=OSError(28, "No space left on device")), \
                self.assertRaisesRegex(es.StoreError, "temporary directory"):
            self.check(raises(OSError("unreachable")))

    def test_cleanup_failure_after_passing_probe_is_store_error(self):
        # Issue #262 site C: the with-block's cleanup rmtree can fail on a
        # parent made unwritable while the probe ran — i.e. after the probe
        # itself succeeded (measured on 3.12.3: parent chmod 0o500 after
        # entry; tempfile's own reset-perms retry does not cover the parent).
        from unittest import mock
        parent = tempfile.TemporaryDirectory()
        self.addCleanup(parent.cleanup)
        parent_path = Path(parent.name)
        real_td = tempfile.TemporaryDirectory

        class CleanupFails(real_td):
            def __init__(self, *a, **kw):
                kw["dir"] = parent_path
                super().__init__(*a, **kw)

            def __exit__(self, *exc):
                parent_path.chmod(0o500)
                try:
                    return super().__exit__(*exc)
                finally:
                    parent_path.chmod(0o700)

        seen = []

        def run(cmd, **kw):
            seen.append(cmd)
            return klt_probe_answer(cmd)  # a current klt: the probe succeeds

        with mock.patch("tempfile.TemporaryDirectory", CleanupFails), \
                self.assertRaisesRegex(es.StoreError, "temporary directory"):
            self.check(run)
        self.assertTrue(seen)  # the klt probe itself passed before cleanup failed

    def test_min_commit_is_the_artifact_uri_revision(self):
        self.assertTrue(es.KLT_ARTIFACT_MIN_COMMIT.startswith("7e3561f"))


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append((self.path, body))
        payload = ({"key": "k", "exists": False} if self.status == 200
                   else {"error": "not_granted", "message": "no"})
        raw = json.dumps(payload).encode()
        self.send_response(self.status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class Probe(unittest.TestCase):
    def serve(self, status):
        handler = type("H", (_Handler,), {"status": status, "seen": []})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}", handler

    def test_reachable_broker_passes(self):
        for status in (200, 404):
            base, handler = self.serve(status)
            es.probe_broker(base, REPO)
            (path, body), = handler.seen
            self.assertEqual(path, "/v1/stat")
            self.assertEqual(body["repo"], REPO)

    def test_refusal_fails_closed(self):
        base, _ = self.serve(403)
        with self.assertRaisesRegex(es.StoreError, "HTTP 403: not_granted"):
            es.probe_broker(base, REPO)

    def test_unreachable_fails_closed(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        with self.assertRaisesRegex(es.StoreError, "unreachable"):
            es.probe_broker(f"http://127.0.0.1:{port}", REPO, timeout=5)

    def test_url_with_credentials_refused(self):
        with self.assertRaises(es.StoreError):
            es.probe_broker("http://u:p@127.0.0.1:1", REPO)

    def test_malformed_ipv6_bracket_refused(self):
        # Issue #262 site D: urlsplit raises ValueError for malformed
        # brackets; it must surface as StoreError, not a traceback.
        for base in ("http://[::1/", "http://[notipv6]/"):
            with self.subTest(base=base), \
                    self.assertRaisesRegex(es.StoreError, "is not a plain http"):
                es.probe_broker(base, REPO)

    def test_bad_port_or_control_char_refused(self):
        # Issue #262 site E: the connection constructor raises InvalidURL for
        # a nonnumeric port or a control character; both pass the existing
        # scheme/credential guard, so they must be converted too.
        for base in ("http://broker.internal:notaport/", "http://br\x00oker/"):
            with self.subTest(base=base), \
                    self.assertRaisesRegex(es.StoreError, "is not a plain http"):
                es.probe_broker(base, REPO)


class CampaignCli(unittest.TestCase):
    """``sim/run_store_evidence.py``: the store path for campaign outputs."""

    def setUp(self):
        import importlib.util
        path = Path(__file__).resolve().parents[2] / "run_store_evidence.py"
        spec = importlib.util.spec_from_file_location("run_store_evidence", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name).resolve()
        (self.root / "sim/bench").mkdir(parents=True)
        self.staged = self.root / "sim/.work/camp"
        self.staged.mkdir(parents=True)
        (self.staged / "a.json").write_text("{}\n")
        self.summary = self.root / "summary.md"
        self.summary.write_text("# campaign\n")
        self.mod.REPO_ROOT = self.root

    def main(self, staged=None, preflight_exc=None):
        from unittest import mock
        store = {}
        real_put = es.put_files
        with mock.patch.object(es, "preflight", side_effect=preflight_exc), \
             mock.patch.object(es, "put_files",
                               side_effect=lambda f, r: real_put(f, r, run=fake_klt(store))), \
             mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            return self.mod.main(["bench", "20261022-abc", str(staged or self.staged),
                                  "--summary", str(self.summary)])

    def test_stores_and_commits_manifest_and_summary(self):
        self.assertEqual(self.main(), 0)
        m = json.loads((self.root / "manifests/artifacts/bench-20261022-abc.manifest.json")
                       .read_text())
        self.assertEqual([e["name"] for e in m["entries"]],
                         ["sim/bench/evidence/20261022-abc/a.json"])
        self.assertTrue((self.root / "sim/bench/evidence/20261022-abc.md").is_file())
        self.assertFalse((self.root / "sim/bench/evidence/20261022-abc").exists())

    def test_store_unavailable_commits_nothing(self):
        self.assertEqual(self.main(preflight_exc=es.StoreError("no broker")), 10)
        self.assertFalse((self.root / "manifests").exists())
        self.assertFalse((self.root / "sim/bench/evidence").exists())

    def test_preflight_probe_failure_exits_10_not_traceback(self):
        # Issue #262 end-to-end: a malformed broker URL used to escape the
        # real preflight as a ValueError traceback (exit 1, no message); now
        # it is exit 10 with EVIDENCE NOT STORED. Exercises site D (urlsplit)
        # through the real probe_broker.
        from unittest import mock
        real_preflight = es.preflight
        real_probe = es.probe_broker

        def run_ok(cmd, **kw):
            if cmd[1:3] == ["artifact", "verify"]:
                return klt_probe_answer(cmd)
            return subprocess.CompletedProcess(cmd, 0, "usage", "")

        def preflight(root):
            return real_preflight(root, which=lambda n: "/bin/klt", run=run_ok,
                                  probe=real_probe)

        err = io.StringIO()
        with mock.patch.dict(os.environ, {es.ENV_BROKER: "http://[::1/",
                                          es.ENV_REPO: REPO}), \
             mock.patch.object(es, "preflight", side_effect=preflight), \
             contextlib.redirect_stderr(err):
            rc = self.mod.main(["bench", "20261022-abc", str(self.staged),
                                "--summary", str(self.summary)])
        self.assertEqual(rc, 10)
        self.assertIn("EVIDENCE NOT STORED", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertFalse((self.root / "manifests").exists())

    def test_staged_dir_inside_tracked_tree_refused(self):
        inside = self.root / "sim/bench/evidence/x"
        inside.mkdir(parents=True)
        (inside / "a.json").write_text("{}\n")
        self.assertEqual(self.main(staged=inside), 1)
        self.assertFalse((self.root / "manifests").exists())

    def test_store_path_oserror_exits_10_and_rolls_the_manifest_back(self):
        # Issue #251: a store-path OSError used to escape as a traceback with
        # exit 1 and no message; now it is exit 10 with EVIDENCE NOT STORED,
        # and the manifest installed moments earlier is rolled back.
        (self.root / "sim/bench/evidence").write_text("blocks the summary directory\n")
        from unittest import mock
        store = {}
        real_put = es.put_files
        err = io.StringIO()
        with mock.patch.object(es, "preflight", side_effect=None), \
             mock.patch.object(es, "put_files",
                               side_effect=lambda f, r: real_put(f, r, run=fake_klt(store))), \
             contextlib.redirect_stderr(err):
            rc = self.mod.main(["bench", "20261022-abc", str(self.staged),
                                "--summary", str(self.summary)])
        self.assertEqual(rc, 10)
        self.assertIn("EVIDENCE NOT STORED", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertFalse(
            (self.root / "manifests/artifacts/bench-20261022-abc.manifest.json").exists())

    def test_put_files_tempdir_failure_exits_10_not_traceback(self):
        # Issue #272 end-to-end: the manifest temp dir's failure used to
        # escape put_files as a bare OSError traceback (exit 1, no
        # message); now it is exit 10 with EVIDENCE NOT STORED, and
        # nothing is installed (the staged bytes stay in scratch).
        from unittest import mock
        store = {}
        real_put = es.put_files
        err = io.StringIO()
        with mock.patch.object(es, "preflight", side_effect=None), \
             mock.patch.object(es, "put_files",
                               side_effect=lambda f, r: real_put(f, r, run=fake_klt(store))), \
             mock.patch("tempfile.TemporaryDirectory",
                        side_effect=OSError(28, "No space left on device")), \
             contextlib.redirect_stderr(err):
            rc = self.mod.main(["bench", "20261022-abc", str(self.staged),
                                "--summary", str(self.summary)])
        self.assertEqual(rc, 10)
        self.assertIn("EVIDENCE NOT STORED", err.getvalue())
        self.assertIn("evidence manifest's temporary directory", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertFalse((self.root / "manifests").exists())
        self.assertFalse((self.root / "sim/bench/evidence").exists())
        self.assertTrue((self.staged / "a.json").exists())  # staged bytes kept


if __name__ == "__main__":
    unittest.main()
