"""Offline tests for sim/tools/check_test_main_guard.py (issue #247).

Builds temporary git repositories (the checker takes its file set from
`git ls-files`, not a filesystem walk) and drives the real CLI. Run:
    python3 -m unittest discover -s sim/tools -p 'test_check_test_main_guard.py' -v
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

CHECKER = pathlib.Path(__file__).resolve().parent / "check_test_main_guard.py"

GUARD_LAST = """\
import unittest


class Tests(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
"""

CLASS_AFTER_GUARD = """\
import unittest


class Visible(unittest.TestCase):
    def test_one(self):
        pass


if __name__ == "__main__":
    unittest.main()


class Hidden(unittest.TestCase):
    def test_two(self):
        pass
"""

DEF_AFTER_GUARD = """\
import unittest


class Tests(unittest.TestCase):
    def test_one(self):
        pass


if __name__ == "__main__":
    unittest.main()


def helper_after_guard():
    return 1
"""

ASYNC_AFTER_GUARD = """\
import unittest


class Tests(unittest.TestCase):
    def test_one(self):
        pass


if __name__ == "__main__":
    unittest.main()


async def helper_after_guard():
    return 1
"""

NO_GUARD = """\
import unittest


class Tests(unittest.TestCase):
    def test_one(self):
        pass
"""

REVERSED_GUARD = """\
import unittest


class Tests(unittest.TestCase):
    def test_one(self):
        pass


if "__main__" == __name__:
    unittest.main()


def after_reversed_guard():
    return 1
"""

TWO_GUARDS = """\
import unittest


if __name__ == "__main__":
    unittest.main()


def between_guards():
    return 1


if __name__ == "__main__":
    pass
"""

NESTED_AFTER_GUARD = """\
import unittest


class Tests(unittest.TestCase):
    def test_one(self):
        def inside_test():
            class Deep:
                pass
        inside_test()


if __name__ == "__main__":
    if True:
        class InsideGuard(unittest.TestCase):
            def test_x(self):
                pass
    unittest.main()


for _i in (0,):
    def loop_body():
        pass


try:
    def try_body():
        pass
except OSError:
    pass
"""

STRING_FAKE_GUARDS = '''\
"""
if __name__ == "__main__":
    unittest.main()
"""

import unittest


class AfterDocstringGuard(unittest.TestCase):
    def test_one(self):
        pass


if __name__ == "__main__":
    unittest.main()

NOTE = """
def not_a_definition(test):
    pass


class NotAClass(unittest.TestCase):
    def test_fake(self):
        pass
"""
'''

DECORATED = """\
import unittest


def deco(f):
    return f


if __name__ == "__main__":
    unittest.main()


@deco
def decorated_fn():
    pass


@deco
class DecoratedClass(unittest.TestCase):
    def test_one(self):
        pass
"""

BROKEN = "def (:\n"


def line_of(src, needle):
    """1-based line number of `needle`'s first occurrence in `src`."""
    return src[: src.index(needle)].count("\n") + 1


class Repo(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = pathlib.Path(td.name)
        self.g("init", "-q", "-b", "main")

    def g(self, *a):
        return subprocess.run(["git", "-C", str(self.root), *a], check=True,
                              capture_output=True, text=True).stdout

    def track(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.g("add", rel)

    def run_check(self):
        r = subprocess.run([sys.executable, str(CHECKER), "--repo",
                            str(self.root)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


class GuardLast(Repo):
    def test_guard_last_passes(self):
        self.track("test_ok.py", GUARD_LAST)
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_no_test_files_passes(self):
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_no_guard_at_all_passes(self):
        self.track("test_noguard.py", NO_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_class_after_guard_fails_with_line(self):
        self.track("test_bad.py", CLASS_AFTER_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        want = f"test_bad.py:{line_of(CLASS_AFTER_GUARD, 'class Hidden')}"
        self.assertIn(want, out)

    def test_def_after_guard_fails_with_line(self):
        self.track("test_bad.py", DEF_AFTER_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        want = (f"test_bad.py:"
                f"{line_of(DEF_AFTER_GUARD, 'def helper_after_guard')}")
        self.assertIn(want, out)

    def test_async_def_after_guard_fails(self):
        self.track("test_bad.py", ASYNC_AFTER_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        want = (f"test_bad.py:"
                f"{line_of(ASYNC_AFTER_GUARD, 'async def helper_after_guard')}")
        self.assertIn(want, out)

    def test_nested_defs_after_guard_pass(self):
        # Definitions inside a method, the guard body, a top-level for and a
        # top-level try are never in tree.body, so none is a violation.
        self.track("test_nested.py", NESTED_AFTER_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_string_fake_guards_do_not_false_positive(self):
        # A docstring line starting with `if __name__` (here at line 2) and a
        # triple-quoted string after the real guard containing column-0
        # `def`/`class` lines must not fake a guard or a definition: the
        # ast-not-regex requirement.
        self.track("test_strings.py", STRING_FAKE_GUARDS)
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_reversed_operand_order_is_recognized_as_guard(self):
        # `if "__main__" == __name__:` must count as the guard, so the def
        # after it is reported (otherwise the file would pass as guard-less).
        self.track("test_reversed.py", REVERSED_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        want = (f"test_reversed.py:"
                f"{line_of(REVERSED_GUARD, 'def after_reversed_guard')}")
        self.assertIn(want, out)

    def test_first_guard_wins(self):
        # A def between two guards is after the FIRST guard, which is the one
        # that counts.
        self.track("test_two.py", TWO_GUARDS)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        want = (f"test_two.py:"
                f"{line_of(TWO_GUARDS, 'def between_guards')}")
        self.assertIn(want, out)

    def test_decorated_reported_line_is_def_not_decorator(self):
        self.track("test_deco.py", DECORATED)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        fn = f"test_deco.py:{line_of(DECORATED, 'def decorated_fn')}"
        cls = f"test_deco.py:{line_of(DECORATED, 'class DecoratedClass')}"
        deco_fn = f"test_deco.py:{line_of(DECORATED, '@deco')}"
        self.assertIn(fn, out)
        self.assertIn(cls, out)
        self.assertNotIn(deco_fn, out)

    def test_multiple_violations_all_reported(self):
        self.track("test_a.py", CLASS_AFTER_GUARD)
        self.track("dir/test_b.py", DEF_AFTER_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn(
            f"test_a.py:{line_of(CLASS_AFTER_GUARD, 'class Hidden')}", out)
        self.assertIn(
            f"dir/test_b.py:{line_of(DEF_AFTER_GUARD, 'def helper_after_guard')}",
            out)

    def test_untracked_and_non_test_files_not_scanned(self):
        # The file set is the tracked set: an untracked scratch test file and
        # a non-test file with the same violation are invisible.
        self.track("test_ok.py", GUARD_LAST)
        (self.root / "test_scratch_bad.py").write_text(CLASS_AFTER_GUARD)
        self.track("helper.py", CLASS_AFTER_GUARD)
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_unparseable_file_fails_closed(self):
        self.track("test_ok.py", GUARD_LAST)
        self.track("test_broken.py", BROKEN)
        rc, out = self.run_check()
        self.assertEqual(rc, 2, out)
        self.assertIn("test_broken.py", out)
        self.assertIn("cannot parse", out)

    def test_tracked_file_missing_from_disk_fails_closed(self):
        self.track("test_ok.py", GUARD_LAST)
        (self.root / "test_ok.py").unlink()
        rc, out = self.run_check()
        self.assertEqual(rc, 2, out)
        self.assertIn("cannot read", out)

    def test_git_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run([sys.executable, str(CHECKER), "--repo", td],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("git ls-files failed", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
