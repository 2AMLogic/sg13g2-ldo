"""Offline fixtures for ensure_libllvm21's dpkg-deb diagnostic (issue #325).

Drives the real function extracted from sim/tools/build-osdi.sh inside a stub
environment shaped like the stripped host that motivated the issue: an empty
LLVM cache, a PATH holding only cat (so `command -v dpkg-deb` fails) and a
decoy LD_LIBRARY_PATH directory that already contains a file named
libLLVM.so.21.1 -- proving the helper consults neither PATH tools beyond cat
nor LD_LIBRARY_PATH, only its own cache. No network, no PDK, no root. Run:
    python3 -m unittest discover -s sim/tools -p 'test_build_osdi.py' -v
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent
BUILD_OSDI = TOOLS / "build-osdi.sh"
BASH = shutil.which("bash")

# Fixture pins. The function's logic keys on these, and the real values in
# build-osdi.sh churn with every LLVM pin bump -- dummies keep this test about
# the diagnostic, not the pin.
ASSET = "libllvm21_21.1.8-fixture_amd64.deb"
TAG = "v24.0.1mob-fixture"


def extract_ensure() -> str:
    """The ensure_libllvm21 function body, straight from the real source."""
    src = BUILD_OSDI.read_text()
    start = src.index("ensure_libllvm21() {")
    end = src.index("\n}\n", start) + len("\n}\n")
    body = src[start:end]
    # Staleness tripwire: the extraction must have caught the real function,
    # not a comment or a neighbour.
    assert "libLLVM.so.21.1" in body and "dpkg-deb" in body, body
    return body


class Harness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = pathlib.Path(self._td.name)
        # PATH with nothing but cat: `command -v dpkg-deb` fails exactly as on
        # the stripped host, while the diagnostic's own cat still prints.
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        os.symlink(shutil.which("cat"), self.bin / "cat")
        self.decoy = self.tmp / "decoy-libs"
        self.decoy.mkdir()
        (self.decoy / "libLLVM.so.21.1").write_bytes(b"")

    def run_ensure(self, cache: pathlib.Path):
        """Run the extracted function in the stub environment.

        Returns the CompletedProcess of `ensure_libllvm21` itself."""
        runner = self.tmp / "runner.sh"
        runner.write_text(
            "set -euo pipefail\n"
            + extract_ensure()
            + "declare -F ensure_libllvm21 >/dev/null 2>&1 "
            "|| { echo 'fixture: ensure_libllvm21 not extracted' >&2; exit 99; }\n"
            + f"CACHE_DIR='{cache}'\n"
            + f"OPENVAF_TAG='{TAG}'\n"
            + f"LIBLLVM21_DEB_ASSET='{ASSET}'\n"
            + "LIBLLVM21_DEB_URL='https://fixture.invalid/libllvm21.deb'\n"
            + "LIBLLVM21_DEB_SHA256='"
            + "0" * 64 + "'\n"
            + "ensure_libllvm21\n"
        )
        env = {
            "PATH": str(self.bin),
            "LD_LIBRARY_PATH": str(self.decoy),
        }
        return subprocess.run(
            [BASH, str(runner)], env=env, capture_output=True, text=True)


class MissingDpkgDebDiagnostic(Harness):
    """Empty cache, no dpkg-deb: one actionable install instruction, exit 3."""

    def test_exit_3_with_install_instruction(self):
        cache = self.tmp / "cache"
        cache.mkdir()
        r = self.run_ensure(cache)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("apt-get install dpkg", r.stderr)
        self.assertIn("rerun", r.stderr)

    def test_unusable_manual_recipe_is_gone(self):
        cache = self.tmp / "cache"
        cache.mkdir()
        r = self.run_ensure(cache)
        self.assertEqual(r.returncode, 3, r.stderr)
        # No third command invoking the missing dpkg-deb...
        self.assertNotIn("dpkg-deb -x", r.stderr)
        # ...no hand-rolled download of the pinned .deb...
        self.assertNotIn("curl", r.stderr)
        # ...and no LD_LIBRARY_PATH pointing outside the cache the next run
        # checks (build-osdi.sh's own cache is the only verified location).
        self.assertNotIn("LD_LIBRARY_PATH", r.stderr)


class PopulatedCacheNoDpkgDeb(Harness):
    """Cached libLLVM.so.21.1: dpkg-deb is never needed again."""

    def test_cached_libdir_returned_without_extractor(self):
        cache = self.tmp / "cache"
        libdir = cache / ASSET[:-len(".deb")] / "usr/lib/x86_64-linux-gnu"
        libdir.mkdir(parents=True)
        (libdir / "libLLVM.so.21.1").write_bytes(b"")
        r = self.run_ensure(cache)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(libdir))


if __name__ == "__main__":
    unittest.main()
