#!/usr/bin/env python3
"""Pin-sync gate: every duplicated pin literal this tree declares, checked
pair-wise for agreement (issues #250, #267).

`layout/run_flow.sh` carries two literal pins that duplicate ci.yml's
workflow-level `env:` keys -- the `klayout-tools==X.Y.Z` spec in PEX_KLT_FROM
(ci.yml's KLAYOUT_TOOLS_VERSION) and the KLAYOUT_PY_VERSION literal default --
and `sim/pdk-cmos5l.json`'s top-level `pinned_commit` duplicates ci.yml's
IHP_SG13CMOS5L_COMMIT, whose own ci.yml comment asserts "keep in sync" with
no mechanical check. Nothing compared them, so a pin bump that edited ci.yml
and missed a copy left CI green while the next local full-mode or pex-mode
regeneration (`--check` never re-runs those stages) stamped the evidence with
a different build. This script is that check. Issue #267 widened the table
with the pairs the first pass missed: two intra-file pairs --
`sim/pdk-cmos5l.json`'s `pinned_tarball_url` must end in its own top-level
`pinned_commit`, and `sim/pdk.json`'s `release_url` must end in its own
top-level `release_tag` -- plus ci.yml's IHP_OPEN_PDK_VERSION against
`sim/pdk.json`'s `release_tag`, whose leading `v` is normalized on the
`sim/pdk.json` side only.

One subcommand:

``check --root DIR``
    Reads every gated file under DIR (the YAML and shell files as text, the
    JSON fact sheets as JSON), extracts each pinned value and compares the
    pairs. All pairs are judged and every problem reported before the exit
    code is chosen, so one broken site cannot hide a second one.

Fail closed. A missing key, an unreadable file, a pin line that matches zero
or more than one time, a PEX_KLT_FROM that is not a `klayout-tools==<version>`
spec, or a pinned_commit that is not a non-empty string is exit 2, never a
pass -- a gate that stopped matching after an unrelated edit and quietly
passed would be worse than no gate. The URL/tag extractors hold the same
posture: a pinned_tarball_url that no longer ends in `/tar.gz/<40-hex>`, a
release_url that no longer ends in `/refs/tags/<tag>.tar.gz`, or a
release_tag without its leading `v` is exit 2 too. A same-named nested key
cannot satisfy a top-level extraction (pdk-cmos5l.json's historical
superseded_pin block carries its own pinned_commit and is deliberately not
gated).

The KLAYOUT_PY_VERSION comparison is deliberately against the *literal
default in run_flow.sh's source text* -- the `0.30.12` inside
`${KLAYOUT_PY_VERSION:-0.30.12}` -- never against the resolved shell
variable. In CI the workflow-level env: supplies that variable, so a gate
that read the runtime value would compare ci.yml against itself and pass
green with the literal arbitrarily stale. This script does not import `os`:
the literal source text is the only comparable side.

Exit codes: 0 every gated pair agrees; 1 at least one pair disagrees (each
drift line names the file, the key and both values); 2 fail-closed
extraction error (ambiguous or missing match, unreadable file).

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CI = ".github/workflows/ci.yml"
FLOW = "layout/run_flow.sh"
CMOS5L = "sim/pdk-cmos5l.json"
G2 = "sim/pdk.json"

EXIT_OK, EXIT_DRIFT, EXIT_ERROR = 0, 1, 2


class GateError(Exception):
    """Ambiguous or missing extraction: exit 2, fail closed."""


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError(f"{rel}: unreadable: {exc}") from exc


def _exactly_one(pattern: re.Pattern[str], text: str, where: str, what: str) -> str:
    found = pattern.findall(text)
    if not found:
        raise GateError(f"{where}: {what} matched no line; the gate matches "
                        "exactly one (fail closed -- if the site moved or was "
                        "renamed, update this gate deliberately)")
    if len(found) > 1:
        raise GateError(f"{where}: {what} matched {len(found)} lines; expected "
                        "exactly one (fail closed, not first-match-wins)")
    return found[0]


def ci_env(root: Path, key: str) -> str:
    """A workflow-level `env:` key's value, from ci.yml's literal text.

    The two-space indent is the anchor that keeps job- and step-scoped keys
    and prose comments out of the match."""
    text = _read(root, CI)
    return _exactly_one(
        re.compile(rf'^  {re.escape(key)}: "([^"\n]*)"[ \t]*$', re.MULTILINE),
        text, CI, f'env key {key!r} (a `  {key}: "..."` line)')


def pex_klt_version(root: Path) -> str:
    """The version in run_flow.sh's PEX_KLT_FROM `klayout-tools==<version>`
    pin. The spec string as a whole is never compared, only the pinned
    version; a non-`==` spec (for example the git URL `${PEX_KLT_FROM##*@}`
    suggests run_flow.sh once carried) cannot be compared to a PyPI release
    pin and fails closed rather than silently comparing nothing."""
    text = _read(root, FLOW)
    spec = _exactly_one(
        re.compile(r'^PEX_KLT_FROM="([^"\n]*)"[ \t]*$', re.MULTILINE),
        text, FLOW, 'PEX_KLT_FROM (a `PEX_KLT_FROM="..."` line)')
    m = re.match(r"^klayout-tools(?:\[[a-z]+\])?==(\S+)$", spec)
    if not m:
        raise GateError(f"{FLOW}: PEX_KLT_FROM is {spec!r}, not a "
                        "`klayout-tools==<version>` pin; only an == PyPI spec "
                        "can be compared to ci.yml's KLAYOUT_TOOLS_VERSION "
                        "(fail closed)")
    return m.group(1)


def flow_py_default(root: Path) -> str:
    """The literal default in run_flow.sh's
    `KLAYOUT_PY_VERSION="${KLAYOUT_PY_VERSION:-<default>}"` -- the source
    text, never the resolved environment variable (see the module docstring)."""
    text = _read(root, FLOW)
    return _exactly_one(
        re.compile(
            r'^KLAYOUT_PY_VERSION="\$\{KLAYOUT_PY_VERSION:-([^}\n]*)\}"[ \t]*$',
            re.MULTILINE),
        text, FLOW,
        'KLAYOUT_PY_VERSION literal default (a '
        '`KLAYOUT_PY_VERSION="${KLAYOUT_PY_VERSION:-...}"` line)')


def json_top(root: Path, rel: str, key: str) -> str:
    """A top-level string value from a JSON fact sheet, via stdlib json so a
    same-named nested key cannot shadow it."""
    try:
        data = json.loads(_read(root, rel))
    except ValueError as exc:
        raise GateError(f"{rel}: not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or key not in data:
        raise GateError(f"{rel}: top-level key {key!r} missing (fail closed)")
    value = data[key]
    if not isinstance(value, str) or not value:
        raise GateError(f"{rel}: top-level key {key!r} is not a non-empty "
                        "string (fail closed)")
    return value


def tarball_commit(root: Path) -> str:
    """The commit segment of pdk-cmos5l.json's pinned_tarball_url: the
    codeload URL must end in `/tar.gz/<40-hex>`, and only that trailing
    segment is compared to pinned_commit -- never the whole URL, mirroring
    pex_klt_version's extract-the-version-not-the-spec posture. A URL that
    stops matching the shape fails closed (issue #267)."""
    url = json_top(root, CMOS5L, "pinned_tarball_url")
    m = re.search(r"/tar\.gz/([0-9a-f]{40})\Z", url)
    if not m:
        raise GateError(f"{CMOS5L}: pinned_tarball_url is {url!r}, which does "
                        "not end in `/tar.gz/<40-hex commit>`; only a "
                        "codeload URL carrying the pinned commit can be "
                        "compared to pinned_commit (fail closed)")
    return m.group(1)


def release_url_tag(root: Path) -> str:
    """The tag segment of pdk.json's release_url: the GitHub archive URL must
    end in `/refs/tags/<tag>.tar.gz`, and only that trailing segment is
    compared to release_tag. A URL that stops matching the shape fails
    closed (issue #267)."""
    url = json_top(root, G2, "release_url")
    m = re.search(r"/refs/tags/([^/\s]+)\.tar\.gz\Z", url)
    if not m:
        raise GateError(f"{G2}: release_url is {url!r}, which does not end in "
                        "`/refs/tags/<tag>.tar.gz`; only a GitHub archive URL "
                        "carrying the tagged release can be compared to "
                        "release_tag (fail closed)")
    return m.group(1)


def g2_release_version(root: Path) -> str:
    """pdk.json's release_tag with its leading `v` stripped, so it compares
    equal to ci.yml's bare IHP_OPEN_PDK_VERSION. The `v` is normalized on
    this side only -- ci.yml's key stays raw -- and a tag without the
    leading `v` fails closed rather than silently normalizing to a pass
    (issue #267)."""
    tag = json_top(root, G2, "release_tag")
    m = re.match(r"^v(\S+)$", tag)
    if not m:
        raise GateError(f"{G2}: release_tag is {tag!r}, not a `v<version>` "
                        "tag; the leading `v` is normalized on this side "
                        "only, so a tag without it cannot be compared to "
                        "ci.yml's bare IHP_OPEN_PDK_VERSION (fail closed)")
    return m.group(1)


class Site:
    """One extraction site of a pin pair."""

    def __init__(self, file: str, key: str, read):
        self.file, self.key, self.read = file, key, read

    def value(self, root: Path) -> str:
        return self.read(root)


class Pair:
    def __init__(self, what: str, left: Site, right: Site):
        self.what, self.left, self.right = what, left, right


# The gated pairs: one literal table entry per duplicated pin. This is the
# right size -- a config-driven pin registry is out of scope (issue #250).
PAIRS = (
    Pair("klayout-tools (klt) release pin",
         Site(CI, "KLAYOUT_TOOLS_VERSION", lambda r: ci_env(r, "KLAYOUT_TOOLS_VERSION")),
         Site(FLOW, "PEX_KLT_FROM spec version", pex_klt_version)),
    Pair("KLayout Python module pin",
         Site(CI, "KLAYOUT_PY_VERSION", lambda r: ci_env(r, "KLAYOUT_PY_VERSION")),
         Site(FLOW, "KLAYOUT_PY_VERSION literal default", flow_py_default)),
    Pair("IHP SG13CMOS5L PDK dev commit",
         Site(CI, "IHP_SG13CMOS5L_COMMIT", lambda r: ci_env(r, "IHP_SG13CMOS5L_COMMIT")),
         Site(CMOS5L, "pinned_commit", lambda r: json_top(r, CMOS5L, "pinned_commit"))),
    # Issue #267: intra-file -- pdk-cmos5l.json's codeload URL must carry its
    # own pinned_commit. Only the trailing segment is compared, never the
    # whole URL: an upstream URL-shape change is a fail-closed extraction
    # error, not a template this gate would have to hardcode and maintain.
    Pair("IHP SG13CMOS5L tarball URL commit",
         Site(CMOS5L, "pinned_commit", lambda r: json_top(r, CMOS5L, "pinned_commit")),
         Site(CMOS5L, "pinned_tarball_url commit segment", tarball_commit)),
    # Issue #267: intra-file -- pdk.json's release_url must carry its own
    # release_tag. pdk-cmos5l.json's release_tag is prose ("none -- ...") by
    # design and is deliberately not gated.
    Pair("IHP SG13G2 release tag",
         Site(G2, "release_tag", lambda r: json_top(r, G2, "release_tag")),
         Site(G2, "release_url tag segment", release_url_tag)),
    # Issue #267: ci.yml's bare version vs pdk.json's tag. The `v` prefix is
    # normalized on the sim/pdk.json side only (g2_release_version strips
    # it); ci.yml's IHP_OPEN_PDK_VERSION stays raw. A tag without the `v`
    # fails closed rather than silently normalizing to a pass.
    Pair("IHP SG13G2 release version",
         Site(CI, "IHP_OPEN_PDK_VERSION", lambda r: ci_env(r, "IHP_OPEN_PDK_VERSION")),
         Site(G2, "release_tag version", g2_release_version)),
)


def check(root: Path) -> int:
    errors: list[str] = []
    drifts: list[str] = []
    compared = 0
    for pair in PAIRS:
        values = []
        for site in (pair.left, pair.right):
            try:
                values.append(site.value(root))
            except GateError as exc:
                errors.append(str(exc))
                values.append(None)
        if values[0] is not None and values[1] is not None:
            compared += 1
            if values[0] != values[1]:
                drifts.append(
                    f"{pair.what}: {pair.left.file} {pair.left.key}={values[0]!r} "
                    f"!= {pair.right.file} {pair.right.key}={values[1]!r}")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    for d in drifts:
        print(f"DRIFT: {d}", file=sys.stderr)
    if errors:
        print(f"FAIL: {len(errors)} fail-closed extraction error(s); "
              f"{compared} of {len(PAIRS)} pair(s) compared", file=sys.stderr)
        return EXIT_ERROR
    if drifts:
        print(f"FAIL: {len(drifts)} of {len(PAIRS)} pin pair(s) disagree "
              "(each drift line names the file, the key and both values)",
              file=sys.stderr)
        return EXIT_DRIFT
    print(f"OK: all {len(PAIRS)} gated pin pair(s) agree, "
          f"{compared} of {len(PAIRS)} pair(s) compared ("
          + "; ".join(p.what for p in PAIRS) + ")")
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check",
                       help="compare every gated pin pair; exit 0 only when all agree")
    c.add_argument("--root", default=".",
                   help="repository root holding the gated files (default: .)")
    args = ap.parse_args(argv)
    return check(Path(args.root))


if __name__ == "__main__":
    sys.exit(main())
