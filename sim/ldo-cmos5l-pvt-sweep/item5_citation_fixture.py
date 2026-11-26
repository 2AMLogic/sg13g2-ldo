"""The shared scratch-repo/manifest fixture for the signoff item-5 citation
tests (issues #358, #381).

Both envelope drivers check the manifest side of their item-5 citation with
the same scratch dance: copy the record tree and every file `cmd_check`
reads through REPO into a temporary repository, redirect the driver to it,
read and edit the signoff manifest, and capture the driver's check output.
Until #381 the row-5 and row-7 suites each carried their own copy of those
eight methods, so a manifest-fixture change had to be made twice. This
module is that dance, once.

A suite mixes `Item5CitationFixture` into its `unittest.TestCase` and
configures it with two class attributes:

    EV      -- the envelope driver module (row5_envelope / row7_envelope)
    ROW_ID  -- the driver's spec-row id (ev.ROW5_ID / ev.ROW7_ID)

The scratch record tree lands at the driver's own record directory relative
to its repository (derived from the ORIGINAL ROOT/REPO before the redirect,
so the citation's repo-relative path shape is exercised for real), and every
control still runs against a per-test scratch repo: committed evidence is
append-only. Row-specific material -- record ids, probe construction, failed
measurements, assertions -- stays in the mixing suite, which keeps its own
driver. Test-only: no driver imports this module, and it is not a test file
(`unittest discover` never collects it).
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import types


class Item5CitationFixture:
    """The eight fixture methods the row-5 and row-7 item-5 suites share.

    Mix into a `unittest.TestCase` next to this class (the mixin comes
    first so its setUp/tearDown win) and set EV and ROW_ID.
    """

    EV = None      # the envelope driver module -- set by the concrete suite
    ROW_ID = None  # the driver's spec-row id -- set by the concrete suite

    def setUp(self):
        self.rel_root = os.path.relpath(self.EV.ROOT, self.EV.REPO)
        self.tmp = tempfile.mkdtemp(
            prefix=os.path.basename(self.rel_root) + "-item5-test.")
        self.repo = os.path.join(self.tmp, "repo")
        # the record tree at its repo-relative path, so the citation's
        # path shape is exercised for real
        self.root = os.path.join(self.repo, self.rel_root)
        os.makedirs(os.path.dirname(self.root))
        shutil.copytree(self.EV.ROOT, self.root)
        # every file cmd_check reads through REPO
        for rel in [self.EV.PDK_PIN, "signoff/sg13g2-ldo.json",
                    "sim/characterization/selection.json"] + list(self.EV.INPUTS):
            dst = os.path.join(self.repo, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(self.EV.REPO, rel), dst)
        self._repo, self._root = self.EV.REPO, self.EV.ROOT
        self.EV.REPO, self.EV.ROOT = self.repo, self.root
        self.stderr = ""

    def tearDown(self):
        self.EV.REPO, self.EV.ROOT = self._repo, self._root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self):
        return json.load(open(os.path.join(self.repo, "signoff", "sg13g2-ldo.json")))

    def write_manifest(self, m):
        json.dump(m, open(os.path.join(self.repo, "signoff", "sg13g2-ldo.json"), "w"),
                  indent=2)

    def prefix(self):
        return self.rel_root.replace(os.sep, "/") + "/"

    def cite(self, rid, rows=None, content_hash=None, file=None, append=True,
             omit_rows=False):
        m = self.manifest()
        members = m["evidence"]["5"]
        members = members if isinstance(members, list) else [members]
        if not append:
            members = []
        tb = os.path.join(self.root, rid, "tb.spice")
        member = {
            "file": file or (self.prefix() + rid + "/report.json"),
            "content_hash": content_hash or (
                "sha256:" + self.EV.sha256_file(tb) if os.path.exists(tb)
                else "sha256:" + "0" * 64),
        }
        if not omit_rows:
            member["rows"] = [self.ROW_ID] if rows is None else rows
        members.append(member)
        m["evidence"]["5"] = members
        self.write_manifest(m)

    def drop_row_members(self):
        m = self.manifest()
        members = m["evidence"]["5"]
        m["evidence"]["5"] = [x for x in (members if isinstance(members, list)
                                          else [members])
                              if not str(x.get("file", "")).startswith(self.prefix())]
        self.write_manifest(m)

    def check(self):
        self.stdout = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()) as err, \
                contextlib.redirect_stdout(self.stdout):
            rc = self.EV.cmd_check(types.SimpleNamespace())
        self.stderr = err.getvalue()
        return rc
