#!/usr/bin/env python3
"""Guard-last check: no top-level def/class after `if __name__ == "__main__"`.

`unittest.main()` inside an `if __name__ == "__main__":` guard calls
`sys.exit()`, so any top-level `def`, `async def` or `class` placed after the
guard never executes when the file is run directly: a `python3 <file>`
spot-check then prints OK on a silently truncated collection and exits 0.
Import-based collection (`unittest discover`, `python3 -m unittest <module>`)
executes the whole module before collecting, so CI -- which only ever imports
-- is immune to guard placement by construction. That is the trap issue #235
paid a full cycle for (21 vs 27 tests, exit 0 both ways); this checker is the
gate that can see it (issue #247).

    python3 sim/tools/check_test_main_guard.py [--repo .]

Rule: in every tracked test file, the first top-level
`if __name__ == "__main__":` block must come after every top-level `def`,
`async def` and `class`. A top-level definition after that guard is reported
as `path:line` and fails the run. A file with no top-level main guard at all
is not a violation. Only `ast.tree.body` is walked, so definitions nested
inside a function, class or other block are never violations, and a module
docstring or triple-quoted fixture string containing a line that starts with
`if __name__` cannot fake a guard. Whether the guard body actually calls
`sys.exit()` is deliberately not analysed: guard-goes-last is universal
Python convention and the simpler rule is the one that stays correct.

The file set is `git ls-files '*test_*.py' 'test_*.py'` -- the tracked set,
never a filesystem walk (an untracked scratch file or `__pycache__` is not
scanned). Non-test files are out of scope by design: the trap only produces
a false *test* result.

Exit codes: 0 pass, 1 top-level definition(s) found after the guard,
2 cannot decide (`git ls-files` failed, or a tracked file is unreadable or
unparseable) -- fail closed, never a silent pass.

Stdlib-only and offline, in the shape of sim/tools/check_append_only.py.
"""
import argparse
import ast
import pathlib
import subprocess
import sys
import warnings

DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class CheckError(Exception):
    """Cannot decide; maps to exit code 2."""


def _is_name(node):
    return isinstance(node, ast.Name) and node.id == "__name__"


def _is_main(node):
    return isinstance(node, ast.Constant) and node.value == "__main__"


def is_main_guard(node):
    """True for `if __name__ == "__main__":` (either operand order)."""
    if not isinstance(node, ast.If):
        return False
    t = node.test
    if (not isinstance(t, ast.Compare) or len(t.ops) != 1
            or not isinstance(t.ops[0], ast.Eq) or len(t.comparators) != 1):
        return False
    return ((_is_name(t.left) and _is_main(t.comparators[0]))
            or (_is_main(t.left) and _is_name(t.comparators[0])))


def after_guard_violations(rel, data):
    """Return `rel:line` for each top-level def/class after the first guard."""
    try:
        # SyntaxWarning (e.g. an invalid escape sequence in some other test
        # file's docstring) is that file's problem, not this check's: the
        # parse either succeeds or it does not.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(data, filename=rel)
    except (SyntaxError, ValueError) as e:
        raise CheckError(f"{rel}: cannot parse: {e}")
    body = tree.body
    guard = next((i for i, n in enumerate(body) if is_main_guard(n)), None)
    if guard is None:
        return []
    return [f"{rel}:{n.lineno}" for n in body[guard + 1:]
            if isinstance(n, DEF_NODES)]


def tracked_test_files(repo):
    """Sorted tracked paths matching '*test_*.py' or 'test_*.py'."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z",
             "*test_*.py", "test_*.py"],
            capture_output=True, check=False)
    except OSError as e:
        raise CheckError(f"cannot run git: {e}")
    if r.returncode != 0:
        raise CheckError(
            f"git ls-files failed ({r.returncode}): "
            f"{r.stderr.decode(errors='replace').strip()}")
    return sorted(set(
        n for n in r.stdout.decode("utf-8", errors="surrogateescape")
        .split("\0") if n))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail when a tracked test file defines a top-level "
                    'def/class after its `if __name__ == "__main__":` guard.')
    ap.add_argument("--repo", default=".",
                    help="repository to scan (default: current directory)")
    args = ap.parse_args(argv)
    try:
        files = tracked_test_files(args.repo)
        bad = []
        for rel in files:
            try:
                data = (pathlib.Path(args.repo) / rel).read_bytes()
            except OSError as e:
                raise CheckError(f"{rel}: cannot read: {e}")
            bad.extend(after_guard_violations(rel, data))
    except CheckError as e:
        print(f"check_test_main_guard: {e}", file=sys.stderr)
        return 2
    if bad:
        print('top-level def/class after the `if __name__ == "__main__":` '
              "guard -- a direct `python3 <file>` run never registers them "
              "(issues #247/#235):")
        for line in bad:
            print(f"  {line}")
        return 1
    print(f"check_test_main_guard: guard-last holds "
          f"({len(files)} tracked test file(s) scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
