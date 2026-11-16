"""Regression tests for scripts/check_pin_sync.py (issue #250).

Every case runs the gate against a throwaway copy of the three gated files
(`.github/workflows/ci.yml`, `layout/run_flow.sh`, `sim/pdk-cmos5l.json`) in
a temp directory, so the extraction patterns are exercised against the repo's
actual text, never a hand-sketched fixture. Each pin pair gets a negative
control -- a tampered copy the gate must reject -- plus the all-agree pass
case and the fail-closed cases. Stdlib only; no network.

The load-bearing case is the CI-blindness control: `KLAYOUT_PY_VERSION` is a
workflow-level `env:` key, so in CI the resolved variable equals ci.yml's own
value. A gate that compared the runtime value instead of run_flow.sh's
literal source text would compare ci.yml against itself and pass green with
the literal arbitrarily stale. The tests pin both halves of the invariant:
the gate must still fail with the variable exported, and its source must
never read the environment at all.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_pin_sync", ROOT / "scripts" / "check_pin_sync.py")
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)

CI = pin.CI
FLOW = pin.FLOW
CMOS5L = pin.CMOS5L
FILES = (CI, FLOW, CMOS5L)


class Tree(unittest.TestCase):
    """Base class: a temp-root copy of the three gated files, plus mutation
    helpers. Carries no tests of its own."""

    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        for rel in FILES:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dst)

    def replace(self, rel, old, new, count=1):
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture assumption broken in {rel}: {old!r}")
        p.write_text(text.replace(old, new, count), encoding="utf-8")

    def drop_line(self, rel, needle):
        p = self.root / rel
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [ln for ln in lines if needle not in ln]
        self.assertLess(len(kept), len(lines), f"no line matched {needle!r} in {rel}")
        p.write_text("".join(kept), encoding="utf-8")

    def duplicate_line(self, rel, needle):
        p = self.root / rel
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        hits = [ln for ln in lines if needle in ln]
        self.assertEqual(len(hits), 1, f"expected one {needle!r} line in {rel}")
        lines.insert(lines.index(hits[0]) + 1, hits[0])
        p.write_text("".join(lines), encoding="utf-8")

    def run_gate(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = pin.main(["check", "--root", str(self.root)])
        return rc, out.getvalue(), err.getvalue()


class RealRepo(unittest.TestCase):
    """The gate passes on the tree as committed -- no pin value changed."""

    def test_real_tree_passes(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = pin.main(["check", "--root", str(ROOT)])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("agree", out.getvalue())


class KltPin(Tree):
    """Pair 1: ci.yml KLAYOUT_TOOLS_VERSION vs run_flow.sh PEX_KLT_FROM."""

    def test_ci_side_drift_fails_naming_both_values(self):
        self.replace(CI, 'KLAYOUT_TOOLS_VERSION: "0.9.2"',
                     'KLAYOUT_TOOLS_VERSION: "9.9.9"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("0.9.2", err)
        self.assertIn("9.9.9", err)
        self.assertIn("KLAYOUT_TOOLS_VERSION", err)
        self.assertIn("PEX_KLT_FROM", err)

    def test_flow_side_drift_fails(self):
        self.replace(FLOW, 'PEX_KLT_FROM="klayout-tools==0.9.2"',
                     'PEX_KLT_FROM="klayout-tools==0.8.0"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("0.9.2", err)
        self.assertIn("0.8.0", err)

    def test_version_is_extracted_from_the_spec_not_compared_whole(self):
        self.replace(FLOW, 'PEX_KLT_FROM="klayout-tools==0.9.2"',
                     'PEX_KLT_FROM="klayout-tools[pex]==0.9.2"')
        rc, out, _ = self.run_gate()
        self.assertEqual(rc, 0, out)
        self.replace(CI, 'KLAYOUT_TOOLS_VERSION: "0.9.2"',
                     'KLAYOUT_TOOLS_VERSION: "0.9.3"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("0.9.2", err)   # the extracted version ...
        self.assertIn("0.9.3", err)
        self.assertNotIn("klayout-tools[pex]", err)  # ... never the whole spec

    def test_non_eq_spec_fails_closed(self):
        self.replace(FLOW, 'PEX_KLT_FROM="klayout-tools==0.9.2"',
                     'PEX_KLT_FROM="git+https://github.com/2AMLogic/'
                     'klayout-tools@main"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("not a `klayout-tools==<version>` pin", err)

    def test_duplicate_flow_line_fails_closed(self):
        self.duplicate_line(FLOW, "PEX_KLT_FROM=")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("matched 2 lines", err)


class KLayoutPyPin(Tree):
    """Pair 2: ci.yml KLAYOUT_PY_VERSION vs the run_flow.sh literal default."""

    def test_literal_drift_fails(self):
        self.replace(FLOW, ':-0.30.12}"', ':-0.30.13}"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("0.30.12", err)
        self.assertIn("0.30.13", err)

    def test_ci_side_drift_fails(self):
        self.replace(CI, 'KLAYOUT_PY_VERSION: "0.30.12"',
                     'KLAYOUT_PY_VERSION: "0.30.13"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("0.30.13", err)

    def test_env_var_does_not_mask_literal_drift(self):
        # The exact CI condition that hides the drift today: the workflow
        # env: supplies KLAYOUT_PY_VERSION, so a gate comparing the resolved
        # variable would see ci.yml's value on both sides and pass green
        # while the literal stays stale. The literal must be compared, and
        # it must lose here.
        self.replace(CI, 'KLAYOUT_PY_VERSION: "0.30.12"',
                     'KLAYOUT_PY_VERSION: "0.30.13"')      # ci.yml bumped ...
        self.replace(FLOW, ':-0.30.12}"', ':-0.30.11}"')   # ... literal missed
        with mock.patch.dict(os.environ, {"KLAYOUT_PY_VERSION": "0.30.13"}):
            rc, _, err = self.run_gate()
        self.assertEqual(rc, 1, err)
        self.assertIn("0.30.11", err)

    def test_gate_source_never_reads_the_environment(self):
        src = (ROOT / "scripts" / "check_pin_sync.py").read_text(encoding="utf-8")
        for banned in ("import os", "from os", "os.environ", "os.getenv",
                       "__import__"):
            self.assertNotIn(banned, src,
                             f"the gate must not use {banned!r} -- the literal "
                             "source text is the only comparable side")

    def test_duplicate_ci_key_fails_closed(self):
        self.duplicate_line(CI, "KLAYOUT_PY_VERSION:")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("matched 2 lines", err)

    def test_missing_ci_key_fails_closed(self):
        self.drop_line(CI, "KLAYOUT_PY_VERSION:")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("KLAYOUT_PY_VERSION", err)
        self.assertIn("matched no line", err)


class PdkCommit(Tree):
    """Pair 3: ci.yml IHP_SG13CMOS5L_COMMIT vs sim/pdk-cmos5l.json."""

    def test_json_side_drift_fails(self):
        self.replace(CMOS5L,
                     '"pinned_commit": "f7bca32694fe3d58be0cc7d9df4b9f5db7161a14"',
                     '"pinned_commit": "' + "a" * 40 + '"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("a" * 40, err)
        self.assertIn("f7bca32694fe3d58be0cc7d9df4b9f5db7161a14", err)

    def test_ci_side_drift_fails(self):
        self.replace(CI, 'IHP_SG13CMOS5L_COMMIT: "f7bca32694fe3d58be0cc7d9df4b9f5db7161a14"',
                     'IHP_SG13CMOS5L_COMMIT: "' + "b" * 40 + '"')
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 1)
        self.assertIn("b" * 40, err)

    def test_superseded_pin_may_disagree_without_failing(self):
        # The nested superseded_pin.pinned_commit is history (issue #155);
        # only the top-level key is gated, so it can keep its old SHA.
        rc, out, _ = self.run_gate()
        self.assertEqual(rc, 0, out)
        data = json.loads((self.root / CMOS5L).read_text(encoding="utf-8"))
        self.assertIn("superseded_pin", data)  # the history block is present

    def test_missing_json_key_fails_closed(self):
        p = self.root / CMOS5L
        data = json.loads(p.read_text(encoding="utf-8"))
        del data["pinned_commit"]
        p.write_text(json.dumps(data), encoding="utf-8")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("pinned_commit", err)
        self.assertIn("missing", err)

    def test_invalid_json_fails_closed(self):
        (self.root / CMOS5L).write_text("{not json", encoding="utf-8")
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("not valid JSON", err)


class FailClosed(Tree):
    """Unreadable inputs are errors (exit 2), never a silent pass."""

    def test_missing_file_fails_closed(self):
        (self.root / CMOS5L).unlink()
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn(CMOS5L, err)

    def test_remaining_pairs_still_compared_after_one_errors(self):
        # One broken extraction must not stop the other pairs from being
        # judged: drift a healthy pair while an unrelated file is missing.
        self.drop_line(CI, "KLAYOUT_TOOLS_VERSION:")        # pair 1 errors ...
        self.replace(FLOW, ':-0.30.12}"', ':-0.30.13}"')    # ... pair 2 drifts
        rc, _, err = self.run_gate()
        self.assertEqual(rc, 2)
        self.assertIn("matched no line", err)
        self.assertIn("0.30.13", err)


if __name__ == "__main__":
    unittest.main()
