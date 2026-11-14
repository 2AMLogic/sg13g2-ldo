#!/usr/bin/env python3
"""Deterministic inventory + freshness check for T1 item 2's artifact-anchored
`kind: generic` attestation, plus the two audits `klt signoff --attest` does
NOT perform for items 1, 9 and 10 (issues #60, #199).

Items 1, 9 and 10 are produced by `klt signoff --attest N --inventory ...`
since issue #199: the tool reads a hash-free attestation inventory, runs the
item's own mechanical checks (netlist freshness, cold start, audit commands)
and DERIVES the envelope's status from them. This script no longer writes
those three envelopes. Two things it still owns for them, because `--attest`
has no concept of either:

  A. **completeness** -- `--attest` attests exactly the paths the inventory
     lists. A testbench added under ``sim/`` that nobody inventoried would be
     silently unattested, so every item's completeness globs are re-checked
     here against its committed inventory's own path lists.
  B. **content checks beyond existence** -- each experiment README naming its
     cold-start entry point (item 9), the Apache-2.0 LICENSE text, the root
     README's title, and CI still carrying all four signoff gates (item 10).

Item 2 (Layout) stays hand-rolled: `klt signoff --attest` deliberately does
not attest it (its binding is the committed GDS stream itself, klayout-tools
#2718), so this script remains its producer. `klt signoff` binds a generic
envelope to ONE artifact (provenance.input.path + content_hash) and item 2 is
backed by several files, so it binds to a committed *inventory*: a JSON list
of the constituent files and their sha256. For item 2 this script therefore
still checks -- stdlib only, no PDK, no klt, no simulator -- that

  1. the committed inventory is byte-identical to what the declared file set
     hashes to NOW (a mutated, deleted or added-by-glob constituent fails);
  2. each completeness glob is fully covered;
  3. the envelope declares the right ``t1_item``, names its inventory in
     ``provenance.input.path`` and records that inventory's current hash;
  4. the manifest pins that same hash for the item;
  5. the GDSII HEADER-record content check.

It is a freshness/identity check, not a design review: it does not simulate,
re-run xschem, or prove the GDS matches the netlist (items 3/4 do that).

    python3 signoff/evidence_inventory.py write   # regenerate item 2's inventory + envelope
    python3 signoff/evidence_inventory.py check   # what CI runs (exit 1 on any drift)
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

ROOT = os.environ.get("EVIDENCE_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
MANIFEST = "signoff/sg13g2-ldo.json"
EVID = "signoff/evidence"

SCOPE = (
    "SG13CMOS5L implementation (design/sg13cmos5l, layout/sg13cmos5l-ldo_core_cmos5l). "
    "Freshness and identity of the listed files only; NOT a performance, spec-compliance "
    "or whole-block T1 claim."
)

_SIM = "sim/ldo-cmos5l-pvt-sweep"
_MC = "sim/ldo-cmos5l-monte-carlo"
_PD = "sim/pass-device-screening"
_HBT = "sim/pass-device-screening-hbt"
_L = "layout/sg13cmos5l-ldo_core_cmos5l"

# The items this script still PRODUCES (inventory + envelope + manifest pin).
# Items 1/9/10 moved to `klt signoff --attest` in issue #199 and are audited
# by ATTESTED below instead.
ITEMS = {
    2: {
        "slug": "layout",
        "title": "Layout",
        "summary": (
            "The SG13CMOS5L layout GDS stream and its generator are committed; every "
            "constituent hash matches the inventory. Freshness/identity only: DRC/LVS/ERC "
            "are the separate item 3/4/11 citations."
        ),
        "files": [
            f"{_L}/sg13cmos5l-ldo_core_cmos5l.gds",
            f"{_L}/generate.py",
            "layout/README.md",
            "layout/common_sg13cmos5l.py",
        ],
        "complete": [f"{_L}/*.gds"],
    },
}

# The items `klt signoff --attest N --inventory <file>` produces. This script
# does not write their inventories (they are hand-maintained and hash-free)
# or their envelopes; it audits the two properties --attest cannot see.
#
#   fields   -- the inventory's own path-list fields, in the shape --attest
#               validates them: a plain list of paths, or a list of objects
#               whose "path" key names the file (item 1's `derived`).
#   complete -- every file matching these globs MUST appear in one of those
#               path lists, or it is silently unattested.
ATTESTED = {
    1: {
        "slug": "design-sources",
        "fields": ["sources", "derived"],
        "complete": ["design/sg13cmos5l/**/*"],
    },
    9: {
        "slug": "testbenches",
        "fields": ["testbenches"],
        # Every testbench / entry point under sim/ must be inventoried.
        "complete": [
            "sim/**/tb_*.spice",
            "sim/**/tb_*.spice.tmpl",
            "sim/**/run_*.sh",
            f"{_MC}/request-*.json",
            f"{_HBT}/decks/request-*.json",
        ],
    },
    10: {
        "slug": "repo-hygiene",
        "fields": ["hygiene"],
        "complete": [".github/workflows/*.yml"],
    },
}

# experiment dir -> entry point its README must name (cold-start invocation).
ENTRY_POINTS = {
    _SIM: "run_sweep.sh",
    _MC: "run_campaign.sh",
    _PD: "run_sweep.sh",
    _HBT: "run_sweep.sh",
    "sim/ldo-cmos5l-enable": "run_smoke.sh",
    "sim/ldo-cmos5l-ilimit": "run_smoke.sh",
}

# CI must keep running every gate this evidence set depends on: the grader, the
# audits below, and all three `klt signoff --attest ... --check` gates (#199).
#
# The `--attest N ` tokens carry a TRAILING SPACE on purpose: a bare
# "--attest 1" is a substring of "--attest 10", so dropping the item-1 step
# would still satisfy it. The inventory filenames are the unambiguous half --
# they appear only in the gate steps themselves, never in a comment.
CI_NEEDLES = (
    "signoff-t1-report:",
    "evidence_inventory.py check",
    "--attest 1 ",
    "--attest 9 ",
    "--attest 10 ",
    "item1-design-sources.inventory.json",
    "item9-testbenches.inventory.json",
    "item10-repo-hygiene.inventory.json",
)


def _sha(path: str) -> str:
    with open(os.path.join(ROOT, path), "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=False) + "\n"


def _slug(item: int) -> str:
    spec = ITEMS.get(item) or ATTESTED[item]
    return spec["slug"]


def _inv_path(item: int) -> str:
    return f"{EVID}/item{item}-{_slug(item)}.inventory.json"


def _env_path(item: int) -> str:
    return f"{EVID}/item{item}-{_slug(item)}.envelope.json"


def _glob(pattern: str) -> list[str]:
    hits = glob.glob(os.path.join(ROOT, pattern), recursive=True)
    return sorted(
        os.path.relpath(h, ROOT) for h in hits if os.path.isfile(h)
    )


def _inventory(item: int) -> dict:
    spec = ITEMS[item]
    files = sorted(spec["files"])
    return {
        "schema_version": 1,
        "t1_item": item,
        "title": spec["title"],
        "scope": SCOPE,
        "files": [{"path": p, "sha256": _sha(p)} for p in files],
    }


def _envelope(item: int, inv_hash: str) -> dict:
    spec = ITEMS[item]
    return {
        "schema_version": 1,
        "kind": "generic",
        "status": "pass",
        "t1_item": item,
        "summary": spec["summary"],
        "source": _inv_path(item),
        "verdict_semantics": (
            "pass = every file in the bound inventory exists and hashes to the recorded "
            "sha256, the inventory covers its completeness globs, and the content checks in "
            "signoff/evidence_inventory.py hold. It is NOT a claim that the circuit meets "
            "its spec. klt does not read `source`; signoff/evidence_inventory.py check "
            "(CI) verifies the constituents."
        ),
        "provenance": {
            "klt_version": None,
            "klayout_version": None,
            "pdk": None,
            "deck": None,
            "input": {
                "path": {"path": _inv_path(item), "scope": "repo"},
                "content_hash": inv_hash,
                "role": "inventory",
            },
            "generator": {"path": "signoff/evidence_inventory.py", "version": 1},
        },
    }


def _read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def _attested_paths(item: int) -> list[str]:
    """Every path the committed `--attest` inventory for ``item`` declares.

    Raises ``ValueError`` if the inventory is not the expected kind/item or a
    declared field is not the shape ``klt signoff --attest`` validates -- the
    tool refuses such a file too, and this audit must not read it loosely."""
    inv = json.loads(_read(_inv_path(item)))
    if inv.get("kind") != "t1-attestation-inventory":
        raise ValueError(f'{_inv_path(item)}: kind is not "t1-attestation-inventory"')
    if inv.get("t1_item") != item:
        raise ValueError(f"{_inv_path(item)}: declares t1_item {inv.get('t1_item')!r}")
    paths: list[str] = []
    for field in ATTESTED[item]["fields"]:
        entries = inv.get(field)
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{_inv_path(item)}: field {field!r} is not a non-empty list")
        for entry in entries:
            path = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(path, str) or not path:
                raise ValueError(f"{_inv_path(item)}: {field!r} has a non-path entry")
            paths.append(path)
    return paths


def _content(item: int) -> list[str]:
    """Checks that go beyond 'the file exists and hashes right'.

    Item 1's old content checks (xschem header, `.subckt` per cell) are gone:
    `--attest`'s freshness command regenerates each netlist from its `.sch` and
    byte-compares, which is strictly stronger than either.
    """
    errs: list[str] = []
    if item == 2:
        with open(os.path.join(ROOT, f"{_L}/sg13cmos5l-ldo_core_cmos5l.gds"), "rb") as f:
            head = f.read(4)
        # GDSII stream begins with a HEADER record: length 0x0006, type 0x0002.
        if head[2:4] != b"\x00\x02":
            errs.append("GDS does not start with a GDSII HEADER record")
    elif item == 9:
        inventoried = _attested_paths(9)
        for exp, entry in ENTRY_POINTS.items():
            if not os.path.isfile(os.path.join(ROOT, exp, entry)):
                errs.append(f"{exp}/{entry} missing")
            elif entry not in _read(f"{exp}/README.md"):
                errs.append(f"{exp}/README.md does not document {entry}")
        if not any("negctl" in p for p in inventoried):
            errs.append("no negative-control request inventoried")
    elif item == 10:
        if "Apache License" not in _read("LICENSE"):
            errs.append("LICENSE is not the expected Apache-2.0 text")
        if not _read("README.md").lstrip().startswith("#"):
            errs.append("README.md has no title heading")
        ci = _read(".github/workflows/ci.yml")
        for needle in CI_NEEDLES:
            if needle not in ci:
                errs.append(f"ci.yml lacks {needle!r}")
    return errs


def write() -> None:
    os.makedirs(os.path.join(ROOT, EVID), exist_ok=True)
    manifest = json.loads(_read(MANIFEST))
    for item in ITEMS:
        inv_text = _dump(_inventory(item))
        with open(os.path.join(ROOT, _inv_path(item)), "w", encoding="utf-8") as f:
            f.write(inv_text)
        inv_hash = _sha(_inv_path(item))
        with open(os.path.join(ROOT, _env_path(item)), "w", encoding="utf-8") as f:
            f.write(_dump(_envelope(item, inv_hash)))
        manifest["evidence"][str(item)] = {"file": _env_path(item), "content_hash": inv_hash}
    manifest["evidence"] = dict(sorted(manifest["evidence"].items(), key=lambda kv: int(kv[0])))
    with open(os.path.join(ROOT, MANIFEST), "w", encoding="utf-8") as f:
        f.write(_dump(manifest))
    print("wrote inventory, envelope and manifest citation for items", sorted(ITEMS))
    print(
        "items",
        sorted(ATTESTED),
        "are produced by `klt signoff --attest N --inventory ... -o ...`; this "
        "script only audits their completeness and content",
    )


def _check_produced(item: int, manifest: dict, errs: list[str]) -> None:
    """Item 2: inventory + envelope + manifest pin are this script's output."""
    spec = ITEMS[item]
    tag = f"item {item}"
    for p in spec["files"]:
        if not os.path.isfile(os.path.join(ROOT, p)):
            errs.append(f"{tag}: inventoried file missing: {p}")
    covered = set(spec["files"])
    for pat in spec["complete"]:
        for hit in _glob(pat):
            if hit not in covered and "/netlist-snapshots/" not in hit:
                errs.append(f"{tag}: {hit} matches {pat!r} but is not inventoried")
    if any(e.startswith(tag + ":") for e in errs):
        return
    inv_text = _dump(_inventory(item))
    try:
        committed = _read(_inv_path(item))
    except OSError:
        errs.append(f"{tag}: inventory {_inv_path(item)} missing")
        return
    if committed != inv_text:
        old = {f["path"]: f["sha256"] for f in json.loads(committed).get("files", [])}
        new = {f["path"]: f["sha256"] for f in json.loads(inv_text)["files"]}
        diff = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
        errs.append(f"{tag}: stale inventory; changed constituents: {diff or '(metadata)'}")
        return
    inv_hash = _sha(_inv_path(item))
    try:
        env_committed = _read(_env_path(item))
    except OSError:
        errs.append(f"{tag}: envelope {_env_path(item)} missing")
        return
    if env_committed != _dump(_envelope(item, inv_hash)):
        errs.append(f"{tag}: envelope does not match the current inventory hash/declaration")
    pin = manifest.get(str(item))
    if not isinstance(pin, dict) or pin.get("file") != _env_path(item):
        errs.append(f"{tag}: manifest does not cite {_env_path(item)}")
    elif pin.get("content_hash") != inv_hash:
        errs.append(f"{tag}: manifest pin {pin.get('content_hash')} != inventory {inv_hash}")
    errs += [f"{tag}: {e}" for e in _content(item)]


def _check_attested(item: int, manifest: dict, errs: list[str]) -> None:
    """Items 1/9/10: audit only what `klt signoff --attest` cannot see.

    The per-file hashes, the freshness commands, the cold start and the audit
    commands are the attestation's own derived checks -- re-running them here
    would duplicate the tool. What is checked instead: the manifest cites the
    attested envelope, every declared path exists, and the completeness globs
    plus content checks hold."""
    tag = f"item {item}"
    pin = manifest.get(str(item))
    if not isinstance(pin, dict) or pin.get("file") != _env_path(item):
        errs.append(f"{tag}: manifest does not cite {_env_path(item)}")
    try:
        inventoried = _attested_paths(item)
    except (OSError, ValueError) as e:
        errs.append(f"{tag}: {e}")
        return
    duplicates = sorted({p for p in inventoried if inventoried.count(p) > 1})
    if duplicates:
        errs.append(f"{tag}: path(s) listed more than once: {duplicates}")
    for p in inventoried:
        if not os.path.isfile(os.path.join(ROOT, p)):
            errs.append(f"{tag}: inventoried file missing: {p}")
    covered = set(inventoried)
    for pat in ATTESTED[item]["complete"]:
        for hit in _glob(pat):
            if hit not in covered and "/netlist-snapshots/" not in hit:
                errs.append(f"{tag}: {hit} matches {pat!r} but is not inventoried")
    errs += [f"{tag}: {e}" for e in _content(item)]


def check() -> int:
    errs: list[str] = []
    try:
        manifest = json.loads(_read(MANIFEST))["evidence"]
    except (OSError, ValueError, KeyError) as e:
        print(f"FAIL cannot read manifest: {e}")
        return 1
    for item in sorted(ITEMS):
        try:
            _check_produced(item, manifest, errs)
        except (OSError, ValueError) as e:
            errs.append(f"item {item}: {type(e).__name__}: {e}")
    for item in sorted(ATTESTED):
        try:
            _check_attested(item, manifest, errs)
        except (OSError, ValueError) as e:
            errs.append(f"item {item}: {type(e).__name__}: {e}")
    for e in errs:
        print("FAIL", e)
    if errs:
        return 1
    print(
        f"OK: item {sorted(ITEMS)} inventory/envelope/manifest pin current; "
        f"items {sorted(ATTESTED)} attestation inventories complete and content-clean"
    )
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) == 2 else ""
    if cmd == "write":
        write()
    elif cmd == "check":
        sys.exit(check())
    else:
        print(__doc__)
        sys.exit(2)
