"""PDK-free tests for signoff/evidence_inventory.py (issue #60): the check
passes on a faithful copy and rejects stale / missing / swapped / mispinned
evidence. Runs on temporary copies; never touches the working tree.

    python3 -m unittest signoff.test_evidence_inventory   (from the repo root)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import evidence_inventory as ei  # noqa: E402


def _copy_tree(dst: str) -> None:
    rels = {ei.MANIFEST, "signoff/evidence_inventory.py"}
    for item, spec in ei.ITEMS.items():
        rels.update(spec["files"])
        rels.update([ei._inv_path(item), ei._env_path(item)])
    for rel in rels:
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.copy(os.path.join(REPO, rel), os.path.join(dst, rel))


def _run(root: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, EVIDENCE_ROOT=root)
    return subprocess.run(
        [sys.executable, "-I", os.path.join(HERE, "evidence_inventory.py"), "check"],
        env=env, capture_output=True, text=True,
    )


class InventoryCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        _copy_tree(self.tmp)

    def p(self, rel):
        return os.path.join(self.tmp, rel)

    def assertFails(self, needle):
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stdout)

    def test_baseline_passes(self):
        r = _run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_mutated_constituent_is_stale(self):
        with open(self.p("design/sg13cmos5l/ldo_core_cmos5l.sch"), "a") as f:
            f.write("* edit\n")
        self.assertFails("stale inventory")

    def test_missing_constituent(self):
        os.remove(self.p("sim/ldo-cmos5l-monte-carlo/tb_row2_accuracy.spice"))
        self.assertFails("missing")

    def test_unlisted_testbench_in_glob(self):
        open(self.p("sim/ldo-cmos5l-pvt-sweep/testbench/tb_new.spice.tmpl"), "w").write("x")
        self.assertFails("not inventoried")

    def test_swapped_t1_item(self):
        path = self.p(ei._env_path(9))
        env = json.load(open(path))
        env["t1_item"] = 10
        json.dump(env, open(path, "w"), indent=2)
        self.assertFails("envelope does not match")

    def test_mismatched_manifest_pin(self):
        m = json.load(open(self.p(ei.MANIFEST)))
        m["evidence"]["2"]["content_hash"] = "sha256:" + "0" * 64
        json.dump(m, open(self.p(ei.MANIFEST), "w"), indent=2)
        self.assertFails("manifest pin")

    def test_missing_citation(self):
        m = json.load(open(self.p(ei.MANIFEST)))
        del m["evidence"]["1"]
        json.dump(m, open(self.p(ei.MANIFEST), "w"), indent=2)
        self.assertFails("manifest does not cite")

    def test_content_check_beyond_existence(self):
        # Refresh nothing: a non-GDS replaced by same-hash is impossible, so
        # break the content AND rewrite the inventory to prove the content
        # check (not just the hash) rejects it.
        open(self.p("LICENSE"), "w").write("proprietary\n")
        env = dict(os.environ, EVIDENCE_ROOT=self.tmp)
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "evidence_inventory.py"), "write"],
                       env=env, check=True, capture_output=True)
        self.assertFails("LICENSE")


if __name__ == "__main__":
    unittest.main()
