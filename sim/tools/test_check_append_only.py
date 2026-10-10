"""Offline tests for sim/tools/check_append_only.py (issue #102).

Builds temporary git repositories and drives the real CLI. Run:
    python3 -m unittest discover -s sim/tools -p 'test_*.py' -v
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

CHECKER = pathlib.Path(__file__).resolve().parent / "check_append_only.py"
ALLOW = "sim/tools/append_only_allowlist.json"
CLASSES = ("records", "corners", "netlist-snapshots", "evidence",
           "backend-validation", "startup")
EV = "sim/ldo-cmos5l-pvt-sweep/evidence/20261010-025634-60a3e81"


class Repo(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = pathlib.Path(td.name)
        self.g("init", "-q", "-b", "main")
        self.g("config", "user.email", "t@example.com")
        self.g("config", "user.name", "t")
        self.g("config", "commit.gpgsign", "false")

    def g(self, *a):
        return subprocess.run(["git", "-C", str(self.root), *a], check=True,
                              capture_output=True, text=True).stdout

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg="c"):
        self.g("add", "-A")
        self.g("commit", "-q", "-m", msg)

    def seed(self):
        for c in CLASSES:
            self.write(f"sim/exp/{c}/rec1/file.txt", f"{c} one line of content\n" * 5)
        self.write("sim/exp/README.md", "readme\n")
        self.commit("base")
        self.g("branch", "base")
        self.g("checkout", "-q", "-b", "pr")

    def run_check(self, base="base", *extra):
        r = subprocess.run([sys.executable, str(CHECKER), "--repo",
                            str(self.root), "--base", base, *extra],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


class Cases(Repo):
    def test_additions_and_unprotected_edits_pass(self):
        self.seed()
        for c in CLASSES:
            self.write(f"sim/exp/{c}/rec2/new.txt", "new\n")
        self.write("sim/exp/README.md", "edited\n")
        self.write("sim/exp/testbench/tb.tmpl", "x\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_modify_each_class_fails_naming_path_and_type(self):
        self.seed()
        for c in CLASSES:
            with self.subTest(c=c):
                self.g("checkout", "-q", "-B", "pr", "base")
                self.write(f"sim/exp/{c}/rec1/file.txt", "changed\n")
                self.commit()
                rc, out = self.run_check()
                self.assertEqual(rc, 1, out)
                self.assertIn(f"sim/exp/{c}/rec1/file.txt", out)
                self.assertIn("M\t", out)

    def test_delete_fails(self):
        self.seed()
        self.g("rm", "-q", "sim/exp/records/rec1/file.txt")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("D\tsim/exp/records/rec1/file.txt", out)

    def test_rename_fails(self):
        self.seed()
        self.g("mv", "sim/exp/corners/rec1/file.txt",
               "sim/exp/corners/rec2file.txt")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("R", out)
        self.assertIn("sim/exp/corners/rec1/file.txt", out)

    def test_rename_out_of_protected_dir_fails(self):
        self.seed()
        self.g("mv", "sim/exp/evidence/rec1/file.txt", "sim/exp/elsewhere.txt")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("sim/exp/evidence/rec1/file.txt", out)

    def test_delete_plus_add_fallback_fails(self):
        # Content changed enough that git reports D + A rather than R.
        self.seed()
        self.g("rm", "-q", "sim/exp/startup/rec1/file.txt")
        self.write("sim/exp/startup/rec9/other.txt", "entirely different\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("D\tsim/exp/startup/rec1/file.txt", out)

    def test_overwrite_existing_via_copy_of_other_file_fails(self):
        self.seed()
        self.write("sim/exp/records/rec1/file.txt",
                   self.root.joinpath("sim/exp/corners/rec1/file.txt").read_text())
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)

    def test_coverage_inventory_regression_434c822(self):
        # Shape of 434c822: both coverage-inventory.{json,md} in a landed
        # evidence record edited in place by a regeneration commit.
        for n in ("json", "md"):
            self.write(f"{EV}/coverage-inventory.{n}", f"old {n}\n")
        self.commit("base")
        self.g("branch", "base")
        self.g("checkout", "-q", "-b", "pr")
        for n in ("json", "md"):
            self.write(f"{EV}/coverage-inventory.{n}", f"regenerated {n}\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        for n in ("json", "md"):
            self.assertIn(f"{EV}/coverage-inventory.{n}", out)

    def test_missing_base_fails_closed(self):
        self.seed()
        rc, out = self.run_check("no-such-ref")
        self.assertEqual(rc, 2, out)
        self.assertIn("cannot resolve base", out)

    def test_no_merge_base_fails_closed(self):
        self.seed()
        self.g("checkout", "-q", "--orphan", "other")
        self.write("x.txt", "x\n")
        self.commit("orphan")
        rc, out = self.run_check("pr")
        self.assertEqual(rc, 2, out)

    def write_allow(self, entries, raw=None):
        self.write(ALLOW, raw if raw is not None
                   else json.dumps({"exceptions": entries}))

    def mutate(self, seed=True):
        if seed:
            self.seed()
        self.write("sim/exp/records/rec1/file.txt", "changed\n")
        self.write("sim/exp/corners/rec1/file.txt", "changed\n")

    def test_exact_allowlist_permits_only_that_path(self):
        self.mutate()
        self.write_allow([{"path": "sim/exp/records/rec1/file.txt",
                           "rationale": "reviewed: typo in provenance"}])
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn("sim/exp/corners/rec1/file.txt", out)
        self.assertNotIn("M\tsim/exp/records/rec1/file.txt", out)

    def test_exact_allowlist_passes_when_all_covered(self):
        self.seed()
        self.write("sim/exp/records/rec1/file.txt", "changed\n")
        self.write_allow([{"path": "sim/exp/records/rec1/file.txt",
                           "rationale": "reviewed"}])
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_invalid_allowlists_fail_closed(self):
        cases = {
            "missing rationale": [{"path": "sim/exp/records/rec1/file.txt"}],
            "blank rationale": [{"path": "sim/exp/records/rec1/file.txt",
                                 "rationale": "  "}],
            "wildcard": [{"path": "sim/exp/records/rec1/*", "rationale": "r"}],
            "globstar": [{"path": "sim/*/evidence/**", "rationale": "r"}],
            "directory": [{"path": "sim/exp/records/rec1/", "rationale": "r"}],
            "directory no slash": [{"path": "sim/exp/records", "rationale": "r"}],
            "unprotected path": [{"path": "sim/exp/README.md", "rationale": "r"}],
            "extra key": [{"path": "sim/exp/records/rec1/file.txt",
                           "rationale": "r", "glob": "x"}],
            "duplicate": [{"path": "sim/exp/records/rec1/file.txt",
                           "rationale": "r"}] * 2,
        }
        self.seed()
        for name, entries in cases.items():
            with self.subTest(name):
                self.g("checkout", "-q", "-B", "pr", "base")
                self.mutate(seed=False)
                self.write_allow(entries)
                self.commit(name)
                rc, out = self.run_check()
                self.assertEqual(rc, 2, out)

    def test_malformed_allowlist_json_fails_closed(self):
        self.mutate()
        self.write_allow(None, raw="{not json")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 2, out)

    def test_protected_set_is_exactly_six_globs(self):
        sys.path.insert(0, str(CHECKER.parent))
        try:
            import check_append_only as m
        finally:
            sys.path.pop(0)
        self.assertEqual(sorted(m.PROTECTED_GLOBS), sorted([
            "sim/*/records/**", "sim/*/corners/**",
            "sim/*/netlist-snapshots/**", "sim/*/evidence/**",
            "sim/*/backend-validation/**", "sim/*/startup/**"]))
        self.assertTrue(m.is_protected(f"{EV}/coverage-inventory.json"))
        self.assertFalse(m.is_protected("sim/exp/testbench/x"))
        self.assertFalse(m.is_protected("sim/exp/records"))


if __name__ == "__main__":
    unittest.main()
