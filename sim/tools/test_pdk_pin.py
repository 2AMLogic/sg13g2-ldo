"""Tests for sim/tools/pdk_pin.py and the E1/E3/E4 PDK revision check (issue #379).

Layer 1 exercises sim/tools/pdk_pin.py (Python API and CLI) against temporary
PDK install directories covering:
  - the five install-marker states (matching/mismatching fleet .pdk-store.json,
    matching/mismatching fetcher .fetched-version, no marker),
  - Git HEAD (matching and mismatching temporary Git checkouts),
  - marker precedence and conflicting markers (.fetched-version > .git >
    .pdk-store.json): a higher-priority mismatching marker must reject even
    when a lower-priority marker matches,
  - unreadable or malformed metadata (.fetched-version, .git, .pdk-store.json,
    and the pin JSON file), all failing closed with exit code 3.

Layer 2 invokes the real E1, E3 and E4 campaign drivers (run_e1op.sh,
run_ccprobe.sh, run_e4.sh) against temporary PDK_ROOT directories (without
OSDI binaries, so a passing pin check logs verification and stops at the OSDI
prerequisite before writing any campaign files) and asserts that:
  - all three accept matching .pdk-store.json and .fetched-version markers,
  - all three reject mismatches, missing markers, higher-priority conflicts,
    and unreadable/malformed metadata before a campaign starts,
  - all three delegate to sim/tools/pdk_pin.py and pass PDK_PIN_FOUND through
    to their manifest writers without duplicating marker-lookup logic.

Offline and stdlib-only: no PDK install, no simulator.
    python3 -m unittest discover -s sim/tools -p 'test_pdk_pin.py' -v
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent
SIM = TOOLS.parent
REPO = SIM.parent
PVT_SWEEP = SIM / "ldo-cmos5l-pvt-sweep"
PDK_PIN_SCRIPT = TOOLS / "pdk_pin.py"
PIN_JSON = SIM / "pdk-cmos5l.json"
PDK_NAME = "ihp-sg13cmos5l"

DRIVERS = (
    ("E1", PVT_SWEEP / "run_e1op.sh"),
    ("E3", PVT_SWEEP / "run_ccprobe.sh"),
    ("E4", PVT_SWEEP / "run_e4.sh"),
)

EXPECTED_PIN = json.loads(PIN_JSON.read_text(encoding="utf-8"))["pinned_commit"]
WRONG_PIN = "0" * 40


def make_git_commit(directory: pathlib.Path, message: str = "fixture") -> str:
    """Initialise a temporary git repo in ``directory`` and return HEAD SHA."""
    git_env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("GIT_")
    }
    subprocess.run(
        ["git", "init", "-q"],
        cwd=directory, env=git_env, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        [
            "git",
            "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false",
            "commit", "-q", "--allow-empty", "-m", message,
        ],
        cwd=directory, env=git_env, check=True, capture_output=True, text=True,
    )
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=directory, env=git_env, check=True, capture_output=True, text=True,
    )
    return res.stdout.strip()


def write_store_json(pdk_dir: pathlib.Path, payload) -> pathlib.Path:
    path = pdk_dir / ".pdk-store.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_fetched_version(pdk_dir: pathlib.Path, content: str) -> pathlib.Path:
    path = pdk_dir / ".fetched-version"
    path.write_text(content, encoding="utf-8")
    return path


class _TempPdkMixin:
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup_tmp)
        self.tmp = pathlib.Path(self._td.name)
        self.pdk_root = self.tmp / "pdk_root"
        self.pdk_dir = self.pdk_root / PDK_NAME
        (self.pdk_dir / "libs.tech" / "ngspice").mkdir(parents=True)
        self._chmod_restore: list[tuple[pathlib.Path, int]] = []

    def _cleanup_tmp(self):
        for path, mode in reversed(self._chmod_restore):
            try:
                os.chmod(path, mode)
            except OSError:
                pass
        self._td.cleanup()

    def make_unreadable(self, path: pathlib.Path):
        mode = stat.S_IMODE(path.stat().st_mode)
        self._chmod_restore.append((path, mode))
        os.chmod(path, 0)

    def write_pin_file(self, payload) -> pathlib.Path:
        pin_file = self.tmp / "pin.json"
        if isinstance(payload, str):
            pin_file.write_text(payload, encoding="utf-8")
        else:
            pin_file.write_text(json.dumps(payload), encoding="utf-8")
        return pin_file


class TestPdkPinCli(_TempPdkMixin, unittest.TestCase):
    """CLI behaviour of sim/tools/pdk_pin.py across all marker and error cases."""

    def run_cli(
        self,
        pin_file: pathlib.Path | None = None,
        pdk_root: pathlib.Path | None = None,
        caller: str = "run_e1op.sh",
        campaign: str = "E1",
    ) -> subprocess.CompletedProcess:
        cmd = [
            sys.executable,
            str(PDK_PIN_SCRIPT),
            "--pdk-root", str(pdk_root if pdk_root is not None else self.pdk_root),
            "--pdk", PDK_NAME,
            "--pin-file", str(pin_file if pin_file is not None else PIN_JSON),
            "--caller", caller,
            "--campaign", campaign,
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    # --- Reproduction table states ---

    def test_fleet_marker_matches(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), EXPECTED_PIN)

    def test_fleet_marker_mismatch(self):
        write_store_json(self.pdk_dir, {"version": WRONG_PIN})
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(WRONG_PIN, r.stderr)
        self.assertIn(EXPECTED_PIN, r.stderr)
        self.assertIn("refusing to run", r.stderr)

    def test_fetcher_marker_matches(self):
        write_fetched_version(self.pdk_dir, EXPECTED_PIN + "\n")
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), EXPECTED_PIN)

    def test_fetcher_marker_matches_without_trailing_newline(self):
        write_fetched_version(self.pdk_dir, EXPECTED_PIN)
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), EXPECTED_PIN)

    def test_fetcher_marker_mismatch(self):
        write_fetched_version(self.pdk_dir, WRONG_PIN + "\n")
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(WRONG_PIN, r.stderr)
        self.assertIn("refusing to run", r.stderr)

    def test_no_marker_or_git_checkout(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn("unidentified", r.stderr)
        self.assertIn("refusing to run", r.stderr)

    # --- Git HEAD ---

    def test_git_head_matches(self):
        head = make_git_commit(self.pdk_dir)
        pin_file = self.write_pin_file({"pinned_commit": head})
        r = self.run_cli(pin_file=pin_file)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), head)

    def test_git_head_mismatch(self):
        head = make_git_commit(self.pdk_dir)
        pin_file = self.write_pin_file({"pinned_commit": WRONG_PIN})
        r = self.run_cli(pin_file=pin_file)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(head, r.stderr)
        self.assertIn("refusing to run", r.stderr)

    # --- Marker precedence and conflicting markers ---

    def test_mismatching_fetcher_rejects_even_when_git_and_fleet_match(self):
        head = make_git_commit(self.pdk_dir)
        pin_file = self.write_pin_file({"pinned_commit": head})
        write_store_json(self.pdk_dir, {"version": head})
        write_fetched_version(self.pdk_dir, WRONG_PIN + "\n")
        r = self.run_cli(pin_file=pin_file)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(WRONG_PIN, r.stderr)

    def test_mismatching_fetcher_rejects_even_when_fleet_matches(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        write_fetched_version(self.pdk_dir, WRONG_PIN + "\n")
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(WRONG_PIN, r.stderr)

    def test_matching_fetcher_accepts_over_mismatching_git_and_fleet(self):
        make_git_commit(self.pdk_dir)
        write_store_json(self.pdk_dir, {"version": WRONG_PIN})
        write_fetched_version(self.pdk_dir, EXPECTED_PIN + "\n")
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), EXPECTED_PIN)

    def test_mismatching_git_rejects_even_when_fleet_matches(self):
        head = make_git_commit(self.pdk_dir)
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(head, r.stderr)

    def test_matching_git_accepts_over_mismatching_fleet(self):
        head = make_git_commit(self.pdk_dir)
        pin_file = self.write_pin_file({"pinned_commit": head})
        write_store_json(self.pdk_dir, {"version": WRONG_PIN})
        r = self.run_cli(pin_file=pin_file)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), head)

    # --- Malformed or unreadable metadata ---

    def test_malformed_fleet_store_json_cases(self):
        cases = (
            ("invalid_json", "{not json"),
            ("json_list", ["version", EXPECTED_PIN]),
            ("missing_version", {"name": PDK_NAME}),
            ("null_version", {"version": None}),
            ("int_version", {"version": 12345}),
            ("empty_version", {"version": ""}),
            ("whitespace_version", {"version": "   \n"}),
        )
        for name, payload in cases:
            with self.subTest(case=name):
                write_store_json(self.pdk_dir, payload)
                r = self.run_cli()
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertIn("refusing to run", r.stderr)

    def test_empty_fetcher_marker_does_not_fall_back_to_fleet(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        for name, content in (("empty", ""), ("whitespace", "  \n")):
            with self.subTest(case=name):
                write_fetched_version(self.pdk_dir, content)
                r = self.run_cli()
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertEqual(r.stdout, "")

    def test_broken_symlink_fetcher_marker_does_not_fall_back_to_fleet(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        (self.pdk_dir / ".fetched-version").symlink_to(self.tmp / "does-not-exist")
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_corrupt_git_dir_does_not_fall_back_to_fleet_or_parent_repo(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        (self.pdk_dir / ".git").mkdir()
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_git_repo_without_commits_does_not_fall_back_to_fleet(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        subprocess.run(
            ["git", "init", "-q"],
            cwd=self.pdk_dir, env=git_env, check=True, capture_output=True,
        )
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_unreadable_markers_fail_closed(self):
        if os.geteuid() == 0:
            self.skipTest("chmod 000 does not block reads as root")
        store = write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        self.make_unreadable(store)
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

        # Restore fleet store, make higher-priority .fetched-version unreadable:
        # must still fail closed and never fall back to the matching fleet store.
        os.chmod(store, 0o644)
        fetched = write_fetched_version(self.pdk_dir, EXPECTED_PIN + "\n")
        self.make_unreadable(fetched)
        r = self.run_cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_malformed_or_missing_pin_file_fails_closed(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        r = self.run_cli(pin_file=self.tmp / "missing.json")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

        for name, payload in (
            ("invalid_json", "{bad"),
            ("not_object", ["pinned_commit"]),
            ("missing_key", {"variant": PDK_NAME}),
            ("non_string", {"pinned_commit": 42}),
            ("empty_string", {"pinned_commit": ""}),
            ("whitespace", {"pinned_commit": "   "}),
        ):
            with self.subTest(case=name):
                pin_file = self.write_pin_file(payload)
                r = self.run_cli(pin_file=pin_file)
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertEqual(r.stdout, "")

    def test_unreadable_pin_file_fails_closed(self):
        if os.geteuid() == 0:
            self.skipTest("chmod 000 does not block reads as root")
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        pin_file = self.write_pin_file({"pinned_commit": EXPECTED_PIN})
        self.make_unreadable(pin_file)
        r = self.run_cli(pin_file=pin_file)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_missing_pdk_dir_fails_closed(self):
        r = self.run_cli(pdk_root=self.tmp / "no-such-pdk-root")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(r.stdout, "")


class TestPdkPinApi(_TempPdkMixin, unittest.TestCase):
    """Direct Python API checks for sim/tools/pdk_pin.py."""

    @classmethod
    def setUpClass(cls):
        if str(TOOLS) not in sys.path:
            sys.path.insert(0, str(TOOLS))
        import pdk_pin  # noqa: E402
        cls.mod = pdk_pin

    def test_read_expected_commit_reads_repo_pin(self):
        self.assertEqual(self.mod.read_expected_commit(PIN_JSON), EXPECTED_PIN)

    def test_verify_pdk_pin_returns_verified_commit_and_source(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        self.assertEqual(
            self.mod.read_installed_commit(self.pdk_dir),
            (EXPECTED_PIN, ".pdk-store.json"),
        )
        self.assertEqual(
            self.mod.verify_pdk_pin(self.pdk_root, PDK_NAME, PIN_JSON),
            EXPECTED_PIN,
        )

    def test_verify_pdk_pin_raises_mismatch_error_on_different_revision(self):
        write_store_json(self.pdk_dir, {"version": WRONG_PIN})
        with self.assertRaises(self.mod.PdkPinMismatchError) as ctx:
            self.mod.verify_pdk_pin(self.pdk_root, PDK_NAME, PIN_JSON)
        self.assertEqual(ctx.exception.found, WRONG_PIN)
        self.assertEqual(ctx.exception.expected, EXPECTED_PIN)


class TestSweepDrivers(_TempPdkMixin, unittest.TestCase):
    """End-to-end pin-check tests against the real E1, E3 and E4 drivers.

    Temporary PDK_ROOT directories intentionally omit libs.tech/ngspice/osdi/
    psp103.osdi so a passing pin check logs verification and halts cleanly at
    the OSDI prerequisite without touching ngspice, klt, or writing files.
    """

    def run_driver(self, script: pathlib.Path) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PDK_ROOT"] = str(self.pdk_root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            ["bash", str(script)],
            cwd=REPO, env=env, capture_output=True, text=True,
        )

    def assert_pin_passed_and_stopped_at_osdi(self, script: pathlib.Path, r):
        caller = script.name
        self.assertIn(
            f"{caller}: {PDK_NAME} install verified at the pinned commit {EXPECTED_PIN}",
            r.stdout,
            f"{caller} did not verify matching pin.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}",
        )
        self.assertIn("psp103.osdi missing", r.stderr)
        self.assertNotIn("refusing to run", r.stderr)
        self.assertEqual(r.returncode, 3)

    def assert_pin_rejected(self, script: pathlib.Path, r, *, expect_exit_3=True):
        caller = script.name
        if expect_exit_3:
            self.assertEqual(r.returncode, 3, f"{caller} rc={r.returncode}\nstderr:\n{r.stderr}")
        else:
            self.assertNotEqual(r.returncode, 0, f"{caller} unexpectedly succeeded")
        self.assertNotIn("install verified at the pinned commit", r.stdout)
        self.assertNotIn("psp103.osdi missing", r.stderr)

    def test_all_drivers_accept_matching_fleet_marker(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_passed_and_stopped_at_osdi(script, r)

    def test_all_drivers_reject_mismatching_fleet_marker(self):
        write_store_json(self.pdk_dir, {"version": WRONG_PIN})
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn("refusing to run", r.stderr)

    def test_all_drivers_accept_matching_fetcher_marker(self):
        write_fetched_version(self.pdk_dir, EXPECTED_PIN + "\n")
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_passed_and_stopped_at_osdi(script, r)

    def test_all_drivers_reject_mismatching_fetcher_marker(self):
        write_fetched_version(self.pdk_dir, WRONG_PIN + "\n")
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn("refusing to run", r.stderr)

    def test_all_drivers_reject_no_marker(self):
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn("unidentified", r.stderr)

    def test_all_drivers_reject_mismatching_fetcher_over_matching_fleet(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        write_fetched_version(self.pdk_dir, WRONG_PIN + "\n")
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn(WRONG_PIN, r.stderr)

    def test_all_drivers_reject_mismatching_git_over_matching_fleet(self):
        head = make_git_commit(self.pdk_dir)
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn(head, r.stderr)

    def test_all_drivers_stop_on_malformed_fleet_metadata(self):
        write_store_json(self.pdk_dir, "{corrupt json")
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn("refusing to run", r.stderr)

    def test_all_drivers_stop_on_corrupt_git_even_with_matching_fleet(self):
        write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        (self.pdk_dir / ".git").mkdir()
        for label, script in DRIVERS:
            with self.subTest(driver=label):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)
                self.assertIn("refusing to run", r.stderr)

    def test_all_drivers_stop_on_unreadable_metadata(self):
        if os.geteuid() == 0:
            self.skipTest("chmod 000 does not block reads as root")
        store = write_store_json(self.pdk_dir, {"version": EXPECTED_PIN})
        self.make_unreadable(store)
        for label, script in DRIVERS:
            with self.subTest(driver=label, marker="store"):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r)

        os.chmod(store, 0o644)
        fetched = write_fetched_version(self.pdk_dir, EXPECTED_PIN + "\n")
        self.make_unreadable(fetched)
        for label, script in DRIVERS:
            with self.subTest(driver=label, marker="fetched"):
                r = self.run_driver(script)
                self.assert_pin_rejected(script, r, expect_exit_3=False)

    def test_drivers_delegate_to_shared_helper_and_preserve_manifest_var(self):
        for label, script in DRIVERS:
            text = script.read_text(encoding="utf-8")
            with self.subTest(driver=label):
                self.assertIn("tools/pdk_pin.py", text)
                self.assertIn("PDK_PIN_FOUND=", text)
                self.assertIn("${PDK} ${PDK_PIN_FOUND}", text)
                self.assertNotIn("PDK_PIN_EXPECTED=", text)
                self.assertNotIn('cat "${PDK_ROOT}/${PDK}/.fetched-version"', text)
                self.assertNotIn('git -C "${PDK_ROOT}/${PDK}" rev-parse HEAD', text)
                self.assertNotIn(".pdk-store.json", text)


if __name__ == "__main__":
    unittest.main()
