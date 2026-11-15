"""PDK-free tests for signoff/evidence_inventory.py (issues #60, #199): the
check passes on a faithful copy and rejects stale / missing / swapped /
mispinned evidence for item 2, and incomplete / mis-declared / content-broken
`klt signoff --attest` inventories for items 1, 9 and 10.

Runs on temporary copies; never touches the working tree. It deliberately does
NOT re-run anything `--attest` owns (per-file hashes, the netlist freshness
commands, the cold start, the audit commands) -- those are gated by the
`klt signoff --attest N ... --check` steps in CI.

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
    for item in ei.ATTESTED:
        rels.add(ei._inv_path(item))
        rels.update(ei._attested_paths(item))
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

    # ---------------------------------------------------------- item 2
    def test_mutated_item2_constituent_is_stale(self):
        with open(self.p("layout/README.md"), "a") as f:
            f.write("\n* edit\n")
        self.assertFails("stale inventory")

    def test_missing_item2_constituent(self):
        os.remove(self.p("layout/common_sg13cmos5l.py"))
        self.assertFails("missing")

    def test_swapped_item2_t1_item(self):
        path = self.p(ei._env_path(2))
        env = json.load(open(path))
        env["t1_item"] = 10
        json.dump(env, open(path, "w"), indent=2)
        self.assertFails("envelope does not match")

    def test_mismatched_item2_manifest_pin(self):
        m = json.load(open(self.p(ei.MANIFEST)))
        m["evidence"]["2"]["content_hash"] = "sha256:" + "0" * 64
        json.dump(m, open(self.p(ei.MANIFEST), "w"), indent=2)
        self.assertFails("manifest pin")

    # ------------------------------------------------- items 1 / 9 / 10
    def test_missing_citation_for_attested_item(self):
        m = json.load(open(self.p(ei.MANIFEST)))
        del m["evidence"]["1"]
        json.dump(m, open(self.p(ei.MANIFEST), "w"), indent=2)
        self.assertFails("manifest does not cite")

    def test_missing_inventoried_testbench(self):
        os.remove(self.p("sim/ldo-cmos5l-monte-carlo/tb_row2_accuracy.spice"))
        self.assertFails("inventoried file missing")

    def test_unlisted_testbench_in_glob(self):
        open(self.p("sim/ldo-cmos5l-pvt-sweep/testbench/tb_new.spice.tmpl"), "w").write("x")
        self.assertFails("not inventoried")

    def test_unlisted_derived_netlist_in_glob(self):
        # Item 1's completeness glob covers all of design/sg13cmos5l/.
        open(self.p("design/sg13cmos5l/ldo_extra_cmos5l.sch"), "w").write("v {xschem}\n")
        self.assertFails("not inventoried")

    def test_attest_inventory_wrong_kind_is_refused(self):
        path = self.p(ei._inv_path(9))
        inv = json.load(open(path))
        inv["kind"] = "generic"
        json.dump(inv, open(path, "w"), indent=2)
        self.assertFails('kind is not "t1-attestation-inventory"')

    def test_attest_inventory_wrong_item_is_refused(self):
        path = self.p(ei._inv_path(10))
        inv = json.load(open(path))
        inv["t1_item"] = 1
        json.dump(inv, open(path, "w"), indent=2)
        self.assertFails("declares t1_item")

    def test_dropped_path_list_is_refused(self):
        path = self.p(ei._inv_path(1))
        inv = json.load(open(path))
        inv["derived"] = []
        json.dump(inv, open(path, "w"), indent=2)
        self.assertFails("is not a non-empty list")

    def test_entry_point_no_longer_documented(self):
        readme = self.p("sim/ldo-cmos5l-enable/README.md")
        open(readme, "w").write("# enable smoke\n\nnothing here names the driver.\n")
        self.assertFails("does not document run_smoke.sh")

    def test_content_check_beyond_existence(self):
        # Item 10's attestation inventory carries no hashes, so breaking an
        # inventoried file's CONTENT (not its hash pin) must still fail.
        open(self.p("LICENSE"), "w").write("proprietary\n")
        self.assertFails("LICENSE")

    def test_ci_losing_an_attest_gate_fails(self):
        ci = self.p(".github/workflows/ci.yml")
        # "--attest 99" would still CONTAIN "--attest 9"; rename the item.
        text = open(ci).read().replace("--attest 9", "--attest nine")
        open(ci, "w").write(text)
        self.assertFails("ci.yml lacks '--attest 9 '")

    def test_ci_losing_an_attest_inventory_path_fails(self):
        ci = self.p(".github/workflows/ci.yml")
        text = open(ci).read().replace("item1-design-sources.inventory.json", "gone.json")
        open(ci, "w").write(text)
        self.assertFails("ci.yml lacks 'item1-design-sources.inventory.json'")
    def _rewrite_pdk_cache_key(self, replacement: str) -> None:
        """Swap the OSDI-bearing PDK cache key line, then refresh every hash.

        Running `write` first means the follow-up `check` cannot fail merely
        because ci.yml's sha256 moved -- only the item-10 content check on the
        key itself can still object.
        """
        rel = ".github/workflows/ci.yml"
        text = open(self.p(rel), encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        hits = [
            i for i, ln in enumerate(lines)
            if ln.strip().startswith("key: ihp-open-pdk-") and "-osdi-" in ln
        ]
        self.assertEqual(len(hits), 1, "expected exactly one OSDI-bearing PDK cache key")
        indent = lines[hits[0]][: len(lines[hits[0]]) - len(lines[hits[0]].lstrip())]
        lines[hits[0]] = f"{indent}{replacement}\n"
        open(self.p(rel), "w", encoding="utf-8").write("".join(lines))
        env = dict(os.environ, EVIDENCE_ROOT=self.tmp)
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "evidence_inventory.py"), "write"],
                       env=env, check=True, capture_output=True)

    def test_osdi_pdk_cache_key_tail_cannot_be_dropped(self):
        # The #222 rebase hazard: a wholesale rewrite of the key line that
        # restores the pre-fix form must fail the item-10 check, not pass
        # quietly. (`build-osdi.sh` installs into this cached tree, so losing
        # the script hash means a toolchain bump reuses stale .osdi models.)
        self._rewrite_pdk_cache_key("key: ihp-open-pdk-v${{ env.IHP_OPEN_PDK_VERSION }}")
        self.assertFails("OSDI-bearing ihp-open-pdk cache key(s), expected 1")

    def test_sibling_compiler_cache_key_does_not_satisfy_osdi_check(self):
        # The trap: hashFiles('sim/tools/build-osdi.sh') ALSO appears in the
        # ~/.cache/sg13g2-ldo compiler-download key, which is left intact
        # here. A substring test would pass; the check must bind the PDK key
        # line itself and fail.
        self._rewrite_pdk_cache_key(
            "key: ihp-open-pdk-v${{ env.IHP_OPEN_PDK_VERSION }}-osdi-static"
        )
        ci = open(self.p(".github/workflows/ci.yml"), encoding="utf-8").read()
        self.assertIn("hashFiles('sim/tools/build-osdi.sh')", ci,
                      "compiler-download cache key should still carry the hash")
        self.assertFails("does not hash sim/tools/build-osdi.sh")


if __name__ == "__main__":
    unittest.main()
