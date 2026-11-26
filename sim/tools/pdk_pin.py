#!/usr/bin/env python3
"""Shared PDK revision pin check for SG13CMOS5L sweep drivers (issue #379).

Before issue #379 the E1, E3 and E4 campaign drivers (run_e1op.sh,
run_ccprobe.sh, run_e4.sh) each carried their own inline copy of the PDK pin
check, and E1 had drifted behind E3/E4 by omitting the fleet artifact-broker
marker (.pdk-store.json). This module is the one check all three call.

Lookup order (matching E3 and E4):
  1. Fetcher stamp: ``<PDK_ROOT>/<PDK>/.fetched-version``
  2. Git checkout:  ``<PDK_ROOT>/<PDK>/.git`` (``git rev-parse --verify HEAD``)
  3. Fleet store:   ``<PDK_ROOT>/<PDK>/.pdk-store.json`` (JSON ``"version"``)

Higher-priority markers always win: if a higher-priority marker is present
but mismatches, is empty, or is unreadable/malformed, verification fails
closed (exit 3) without falling back to a lower-priority marker. Unreadable
or malformed pin metadata likewise fails closed (exit 3).

Python API:
    import pdk_pin
    expected = pdk_pin.read_expected_commit("sim/pdk-cmos5l.json")
    found, source = pdk_pin.read_installed_commit(pdk_dir)
    verified = pdk_pin.verify_pdk_pin(pdk_root, pdk, pin_file)

Shell API:
    PDK_PIN_FOUND="$(python3 sim/tools/pdk_pin.py \\
      --pdk-root "${PDK_ROOT}" --pdk "${PDK}" \\
      --pin-file "${SIM_DIR}/pdk-cmos5l.json" \\
      --caller "run_e1op.sh" --campaign "E1")" || exit $?
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


class PdkPinError(Exception):
    """The PDK revision pin could not be verified (mismatch or bad metadata)."""


class PdkPinMismatchError(PdkPinError):
    """The observed install revision did not match the configured pin."""

    def __init__(self, *, found: str | None, expected: str, source: str | None):
        self.found = found
        self.expected = expected
        self.source = source
        super().__init__(
            f"observed {found or 'unidentified'!r} ({source or 'no marker'}), "
            f"expected {expected!r}"
        )


def _validate_revision_string(value, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise PdkPinError(f"{label}: expected non-empty single-line string")
    return value


def read_expected_commit(pin_file: str | os.PathLike[str]) -> str:
    """Read and validate ``pinned_commit`` from ``pin_file``."""
    try:
        with open(pin_file, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PdkPinError(f"cannot read pin file {pin_file}: {exc}") from exc
    if not isinstance(doc, dict):
        raise PdkPinError(f"{pin_file}: expected JSON object")
    if "pinned_commit" not in doc:
        raise PdkPinError(f"{pin_file}: missing 'pinned_commit' key")
    return _validate_revision_string(
        doc["pinned_commit"], label=f"{pin_file}['pinned_commit']"
    )


def _read_git_head(pdk_dir: str) -> str:
    # Strip ambient GIT_* variables and cap parent-directory traversal so a
    # corrupt .git inside pdk_dir can never resolve against an enclosing repo.
    ceilings = list(dict.fromkeys([
        os.path.dirname(os.path.abspath(pdk_dir)),
        os.path.dirname(os.path.realpath(pdk_dir)),
    ]))
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    git_env["GIT_CEILING_DIRECTORIES"] = os.pathsep.join(ceilings)
    try:
        res = subprocess.run(
            ["git", "-C", pdk_dir, "rev-parse", "--verify", "HEAD"],
            env=git_env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise PdkPinError(f"cannot run git in {pdk_dir}: {exc}") from exc
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip() or f"exit {res.returncode}"
        raise PdkPinError(f"cannot read Git HEAD from {pdk_dir}: {detail}")
    head = res.stdout.rstrip("\r\n")
    return _validate_revision_string(head, label=f"{pdk_dir} Git HEAD")


def read_installed_commit(
    pdk_dir: str | os.PathLike[str],
) -> tuple[str | None, str | None]:
    """Read the installed PDK revision in precedence order:

    1. ``.fetched-version`` (fetcher stamp)
    2. ``.git`` (``git rev-parse --verify HEAD``)
    3. ``.pdk-store.json`` (fleet store ``"version"``)

    Returns ``(revision, marker_name)`` or ``(None, None)`` if none exists.
    Raises ``PdkPinError`` if the highest-priority existing marker is
    unreadable, empty, or malformed.
    """
    base = os.fspath(pdk_dir)

    fetched = os.path.join(base, ".fetched-version")
    if os.path.lexists(fetched):
        try:
            with open(fetched, encoding="utf-8") as fh:
                raw = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise PdkPinError(f"cannot read {fetched}: {exc}") from exc
        value = raw.rstrip("\r\n")
        if not value.strip():
            raise PdkPinError(f"{fetched}: marker file is empty")
        return value, ".fetched-version"

    git_marker = os.path.join(base, ".git")
    if os.path.lexists(git_marker):
        return _read_git_head(base), ".git"

    store = os.path.join(base, ".pdk-store.json")
    if os.path.lexists(store):
        try:
            with open(store, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PdkPinError(f"cannot read {store}: {exc}") from exc
        if not isinstance(doc, dict):
            raise PdkPinError(f"{store}: expected JSON object")
        if "version" not in doc:
            raise PdkPinError(f"{store}: missing 'version' key")
        version = _validate_revision_string(
            doc["version"], label=f"{store}['version']"
        )
        return version, ".pdk-store.json"

    return None, None


def verify_pdk_pin(
    pdk_root: str | os.PathLike[str],
    pdk: str,
    pin_file: str | os.PathLike[str],
) -> str:
    """Verify ``<pdk_root>/<pdk>`` matches ``pin_file`` and return the commit."""
    expected = read_expected_commit(pin_file)
    pdk_dir = os.path.join(os.fspath(pdk_root), pdk)
    if not os.path.isdir(pdk_dir):
        raise PdkPinError(f"{pdk} install directory not found at {pdk_dir}")
    found, source = read_installed_commit(pdk_dir)
    if found != expected:
        raise PdkPinMismatchError(found=found, expected=expected, source=source)
    return found


def _format_pin_label(pin_file: str) -> str:
    norm = pin_file.replace("\\", "/")
    if norm == "sim/pdk-cmos5l.json" or norm.endswith("/sim/pdk-cmos5l.json"):
        return "sim/pdk-cmos5l.json"
    return pin_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Verify an installed PDK revision against a pin JSON file and "
            "print the verified revision on stdout."
        )
    )
    ap.add_argument("--pdk-root", required=True, help="PDK_ROOT parent directory")
    ap.add_argument("--pdk", required=True, help="PDK variant directory name")
    ap.add_argument("--pin-file", required=True, help="JSON file with pinned_commit")
    ap.add_argument(
        "--caller",
        default="pdk_pin.py",
        help="driver script name for stderr diagnostics",
    )
    ap.add_argument(
        "--campaign",
        default="",
        help="campaign label (e.g. E1, E3, E4) for mismatch diagnostics",
    )
    args = ap.parse_args(argv)
    prefix = f"{args.caller}: "
    try:
        verified = verify_pdk_pin(args.pdk_root, args.pdk, args.pin_file)
    except PdkPinMismatchError as exc:
        found_desc = exc.found if exc.found else "unidentified"
        pin_label = _format_pin_label(args.pin_file)
        ev_label = f"{args.campaign} evidence" if args.campaign else "Evidence"
        print(
            f"{prefix}{args.pdk} install at PDK_ROOT={args.pdk_root} "
            f"is '{found_desc}',",
            file=sys.stderr,
        )
        print(
            f"{prefix}  but {pin_label} pins {exc.expected} -- refusing to run.",
            file=sys.stderr,
        )
        print(
            f"{prefix}  {ev_label} must come from the pinned install "
            "(scripts/fetch-ihp-sg13cmos5l.sh);",
            file=sys.stderr,
        )
        print(
            f"{prefix}  point PDK_ROOT at it and re-run.",
            file=sys.stderr,
        )
        return 3
    except PdkPinError as exc:
        print(
            f"{prefix}cannot verify {args.pdk} install at "
            f"PDK_ROOT={args.pdk_root}: {exc} -- refusing to run.",
            file=sys.stderr,
        )
        return 3
    print(verified)
    return 0


if __name__ == "__main__":
    sys.exit(main())
