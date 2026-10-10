#!/usr/bin/env python3
"""PR-time guard: sim/ evidence is append-only (issue #102).

Compares HEAD with its merge base against BASE and fails when a path that
already existed at the merge base, under one of the six protected classes
below, was modified, deleted, renamed away, type-changed or overwritten.
New paths (new record IDs, new files) are always fine.

    python3 sim/tools/check_append_only.py --base origin/main [--head HEAD]
                                           [--repo .] [--allowlist FILE]

Exit codes: 0 pass, 1 protected evidence mutated, 2 cannot decide (base or
head unresolvable, git diff failed, or invalid allowlist) -- fail closed.

Stdlib-only and offline. The diff is read from `git diff --name-status -z -M`
(never the working tree). Rename/copy records are expanded so that BOTH sides
are judged: the old path of a rename is a removal; an existing protected
destination is a replacement. A rename that git reports as delete+add is
rejected through the delete.

Exceptions live in sim/tools/append_only_allowlist.json (read from HEAD):
    {"exceptions": [{"path": "<exact repo-relative path>",
                     "rationale": "<non-empty reason>"}]}
Only exact protected file paths are accepted: no wildcards, no directories,
no blank rationale. Normal corrections mint a new record ID instead.
"""
import argparse
import json
import pathlib
import subprocess
import sys

PROTECTED_CLASSES = (
    "records",
    "corners",
    "netlist-snapshots",
    "evidence",
    "backend-validation",
    "startup",
)
PROTECTED_GLOBS = tuple(f"sim/*/{c}/**" for c in PROTECTED_CLASSES)
DEFAULT_ALLOWLIST = "sim/tools/append_only_allowlist.json"
GLOB_CHARS = set("*?[]{}")


class CheckError(Exception):
    """Cannot decide; maps to exit code 2."""


def is_protected(path):
    parts = path.split("/")
    return (
        len(parts) >= 4
        and parts[0] == "sim"
        and parts[2] in PROTECTED_CLASSES
        and all(parts)
    )


def git(repo, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, check=False,
        )
    except OSError as e:
        raise CheckError(f"cannot run git: {e}")
    if r.returncode != 0:
        raise CheckError(
            f"git {' '.join(args)} failed ({r.returncode}): "
            f"{r.stderr.decode(errors='replace').strip()}"
        )
    return r.stdout


def resolve(repo, rev, what):
    try:
        return git(repo, "rev-parse", "--verify", "--quiet",
                   f"{rev}^{{commit}}").decode().strip()
    except CheckError as e:
        raise CheckError(
            f"cannot resolve {what} revision {rev!r}: {e}\n"
            "  In CI the checkout needs full history (actions/checkout "
            "fetch-depth: 0) and --base must name a fetched ref such as "
            "origin/main."
        )


def load_allowlist(path):
    """Return {exact path: rationale}; raise CheckError if invalid."""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        raise CheckError(f"allowlist {p} unreadable/invalid JSON: {e}")
    if (not isinstance(doc, dict) or set(doc) != {"exceptions"}
            or not isinstance(doc["exceptions"], list)):
        raise CheckError(
            f'allowlist {p} must be {{"exceptions": [ ... ]}}')
    out = {}
    for i, e in enumerate(doc["exceptions"]):
        where = f"allowlist {p} entry {i}"
        if not isinstance(e, dict) or set(e) != {"path", "rationale"}:
            raise CheckError(f'{where}: needs exactly "path" and "rationale"')
        path, why = e["path"], e["rationale"]
        if not isinstance(path, str) or not path:
            raise CheckError(f"{where}: path must be a non-empty string")
        if not isinstance(why, str) or not why.strip():
            raise CheckError(f"{where} ({path}): rationale must be non-empty")
        if GLOB_CHARS & set(path):
            raise CheckError(f"{where}: wildcard path {path!r} not allowed; "
                             "list exact file paths")
        if path.endswith("/") or path.startswith("/") or ".." in path.split("/"):
            raise CheckError(f"{where}: {path!r} is not an exact repo-relative "
                             "file path (directories are not allowed)")
        if not is_protected(path):
            raise CheckError(f"{where}: {path!r} is not under a protected "
                             "class; an exception there is meaningless")
        if path in out:
            raise CheckError(f"{where}: duplicate path {path!r}")
        out[path] = why.strip()
    return out


def diff_entries(repo, mb, head):
    """Yield (status, [paths]) from the name-status stream."""
    raw = git(repo, "diff", "--name-status", "-z", "-M", "--no-ext-diff",
              mb, head)
    toks = raw.decode("utf-8", errors="surrogateescape").split("\0")
    if toks and toks[-1] == "":
        toks.pop()
    i = 0
    while i < len(toks):
        status = toks[i]
        n = 2 if status[:1] in ("R", "C") else 1
        paths = toks[i + 1:i + 1 + n]
        if len(paths) != n:
            raise CheckError("malformed git diff --name-status output")
        yield status, paths
        i += 1 + n


def find_violations(repo, mb, head, allow):
    """Return list of (status, path, detail) for disallowed mutations."""
    bad = []
    for status, paths in diff_entries(repo, mb, head):
        kind = status[0]
        if kind == "A":
            continue  # pure addition
        if kind in ("R", "C"):
            old, new = paths
            if kind == "R" and is_protected(old):
                bad.append((status, old, f"renamed away to {new}"))
            if is_protected(new):
                # A destination that already existed at the merge base would
                # not be reported as R/C by a tree diff, but check anyway.
                if _exists(repo, mb, new):
                    bad.append((status, new, f"overwritten by {kind} from {old}"))
            continue
        path = paths[0]
        if not is_protected(path):
            continue
        label = {"M": "modified", "D": "deleted", "T": "type-changed"}.get(
            kind, "changed")
        bad.append((status, path, label))
    return [b for b in bad if b[1] not in allow]


def _exists(repo, rev, path):
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "-e",
                        f"{rev}:{path}"], capture_output=True)
    return r.returncode == 0


def run(repo, base, head, allowlist_path):
    base_c = resolve(repo, base, "base")
    head_c = resolve(repo, head, "head")
    mb = git(repo, "merge-base", base_c, head_c).decode().strip()
    if not mb:
        raise CheckError(f"no merge base between {base} and {head}")
    allow = load_allowlist(allowlist_path)
    return mb, find_violations(repo, mb, head_c, allow), allow


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True,
                    help="base ref of the PR (e.g. origin/main)")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--allowlist", default=None,
                    help=f"default: <repo>/{DEFAULT_ALLOWLIST}")
    a = ap.parse_args(argv)
    allowlist = a.allowlist or str(pathlib.Path(a.repo) / DEFAULT_ALLOWLIST)
    try:
        mb, bad, allow = run(a.repo, a.base, a.head, allowlist)
    except CheckError as e:
        print(f"append-only check: ERROR (fail closed): {e}", file=sys.stderr)
        return 2
    if bad:
        print("append-only check: FAILED -- landed sim/ evidence was mutated "
              f"(merge base {mb[:12]}):", file=sys.stderr)
        for status, path, detail in bad:
            print(f"  {status}\t{path}\t({detail})", file=sys.stderr)
        print("Evidence is append-only: mint a new record ID instead. A truly "
              "unavoidable change needs an exact-path entry with a rationale "
              f"in {DEFAULT_ALLOWLIST} (see sim/README.md).", file=sys.stderr)
        return 1
    print(f"append-only check: OK (merge base {mb[:12]}; "
          f"{len(allow)} allowlisted exception(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
