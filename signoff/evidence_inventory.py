#!/usr/bin/env python3
"""Deterministic inventory + freshness check for the artifact-anchored
`kind: generic` T1 attestations of items 1, 2, 9 and 10 (issue #60).

`klt signoff` binds a generic envelope to ONE artifact (provenance.input.path
+ content_hash). Items 1/2/9/10 are backed by several files each, so each item
binds to a committed *inventory*: a JSON list of the constituent files and
their sha256. This helper owns the declared file sets (``ITEMS`` below), writes
the inventories, and checks -- stdlib only, no PDK, no klt, no simulator -- that

  1. each committed inventory is byte-identical to what the declared file set
     hashes to NOW (a mutated, deleted or added-by-glob constituent fails);
  2. each completeness glob is fully covered (a new testbench / GDS that nobody
     inventoried fails rather than being silently unattested);
  3. each envelope declares the right ``t1_item``, names its inventory in
     ``provenance.input.path`` and records that inventory's current hash;
  4. the manifest pins that same hash for the item;
  5. a few content checks that go beyond file existence (see ``_content``).

It is a freshness/identity check, not a design review: it does not simulate,
re-run xschem, or prove the GDS matches the netlist (items 3/4 do that).

    python3 signoff/evidence_inventory.py write   # regenerate inventories + envelopes
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
_L = "layout/sg13cmos5l-ldo_core_cmos5l"

ITEMS = {
    1: {
        "slug": "design-sources",
        "title": "Design sources",
        "summary": (
            "SG13CMOS5L schematics/symbols, their generator and the regenerated ngspice "
            "netlists are committed; every constituent hash matches the inventory. "
            "Freshness/identity only, not a design-correctness or performance claim."
        ),
        "files": [
            "design/README.md",
            "design/netlist.py",
            "design/xschemrc",
            "design/sg13cmos5l/ldo_core_cmos5l.sch",
            "design/sg13cmos5l/ldo_core_cmos5l.sym",
            "design/sg13cmos5l/ldo_erramp_cmos5l.sch",
            "design/sg13cmos5l/ldo_erramp_cmos5l.sym",
            "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice",
            "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice",
        ],
        "complete": ["design/sg13cmos5l/**/*"],
    },
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
    9: {
        "slug": "testbenches",
        "title": "Testbenches shipped",
        "summary": (
            "The shipped ngspice testbenches/templates, their cold-start entry points "
            "(run_*.sh) and experiment READMEs are committed; every constituent hash "
            "matches the inventory and each README names its entry point. Testbenches are "
            "NOT re-run by this attestation and no measurement result is claimed."
        ),
        "files": [
            "sim/README.md",
            "sim/env.sh",
            f"{_SIM}/README.md",
            f"{_SIM}/run_sweep.sh",
            f"{_SIM}/testbench/tb_dcsweep_cmos5l.spice.tmpl",
            f"{_SIM}/testbench/tb_loopgain_cmos5l.spice.tmpl",
            f"{_SIM}/testbench/tb_psrr_cmos5l.spice.tmpl",
            f"{_MC}/README.md",
            f"{_MC}/run_campaign.sh",
            f"{_MC}/runner-preamble.cir",
            f"{_MC}/row2-corners.lib",
            f"{_MC}/tb_row2_accuracy.spice",
            f"{_MC}/request-row2-attribution.json",
            f"{_MC}/request-row2-mc.json",
            f"{_MC}/request-row2-negctl.json",
            f"{_MC}/request-row2-probe.json",
            f"{_MC}/request-row2-repro.json",
            f"{_PD}/README.md",
            f"{_PD}/run_sweep.sh",
            f"{_PD}/testbench/tb_dropout_pmos.spice.tmpl",
            f"{_PD}/testbench/tb_stress_pmos.spice.tmpl",
        ],
        # Every testbench / entry point under sim/ must be inventoried.
        "complete": [
            "sim/**/tb_*.spice",
            "sim/**/tb_*.spice.tmpl",
            "sim/**/run_*.sh",
            f"{_MC}/request-*.json",
        ],
    },
    10: {
        "slug": "repo-hygiene",
        "title": "Repo hygiene",
        "summary": (
            "README, LICENSE, spec index, agent instructions and the CI workflow are "
            "committed; every constituent hash matches the inventory and the CI workflow "
            "still defines the PDK-free signoff gates. Hygiene presence/freshness only."
        ),
        "files": [
            "README.md",
            "LICENSE",
            "CLAUDE.md",
            "spec/README.md",
            ".github/workflows/ci.yml",
        ],
        "complete": [".github/workflows/*.yml"],
    },
}

# experiment dir -> entry point its README must name (cold-start invocation).
ENTRY_POINTS = {
    _SIM: "run_sweep.sh",
    _MC: "run_campaign.sh",
    _PD: "run_sweep.sh",
}


def _sha(path: str) -> str:
    with open(os.path.join(ROOT, path), "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=False) + "\n"


def _inv_path(item: int) -> str:
    return f"{EVID}/item{item}-{ITEMS[item]['slug']}.inventory.json"


def _env_path(item: int) -> str:
    return f"{EVID}/item{item}-{ITEMS[item]['slug']}.envelope.json"


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


def _content(item: int) -> list[str]:
    """Checks that go beyond 'the file exists and hashes right'."""
    errs: list[str] = []
    if item == 1:
        for cell in ("ldo_core_cmos5l", "ldo_erramp_cmos5l"):
            sch = _read(f"design/sg13cmos5l/{cell}.sch")
            net = _read(f"design/sg13cmos5l/netlist/{cell}.spice")
            if not sch.startswith("v {xschem"):
                errs.append(f"{cell}.sch is not an xschem schematic")
            if f".subckt {cell}".lower() not in net.lower():
                errs.append(f"netlist for {cell} has no .subckt {cell}")
    elif item == 2:
        with open(os.path.join(ROOT, f"{_L}/sg13cmos5l-ldo_core_cmos5l.gds"), "rb") as f:
            head = f.read(4)
        # GDSII stream begins with a HEADER record: length 0x0006, type 0x0002.
        if head[2:4] != b"\x00\x02":
            errs.append("GDS does not start with a GDSII HEADER record")
    elif item == 9:
        for exp, entry in ENTRY_POINTS.items():
            if not os.path.isfile(os.path.join(ROOT, exp, entry)):
                errs.append(f"{exp}/{entry} missing")
            elif entry not in _read(f"{exp}/README.md"):
                errs.append(f"{exp}/README.md does not document {entry}")
        if "negctl" not in "".join(ITEMS[9]["files"]):
            errs.append("no negative-control request inventoried")
    elif item == 10:
        if "Apache License" not in _read("LICENSE"):
            errs.append("LICENSE is not the expected Apache-2.0 text")
        if not _read("README.md").lstrip().startswith("#"):
            errs.append("README.md has no title heading")
        ci = _read(".github/workflows/ci.yml")
        for needle in ("signoff-t1-report:", "evidence_inventory.py check"):
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
    print("wrote inventories, envelopes and manifest citations for items", sorted(ITEMS))


def check() -> int:
    errs: list[str] = []
    try:
        manifest = json.loads(_read(MANIFEST))["evidence"]
    except (OSError, ValueError, KeyError) as e:
        print(f"FAIL cannot read manifest: {e}")
        return 1
    for item, spec in ITEMS.items():
        tag = f"item {item}"
        try:
            for p in spec["files"]:
                if not os.path.isfile(os.path.join(ROOT, p)):
                    errs.append(f"{tag}: inventoried file missing: {p}")
            covered = set(spec["files"])
            for pat in spec["complete"]:
                for hit in _glob(pat):
                    if hit not in covered and "/netlist-snapshots/" not in hit:
                        errs.append(f"{tag}: {hit} matches {pat!r} but is not inventoried")
            if any(e.startswith(tag + ":") for e in errs):
                continue
            inv_text = _dump(_inventory(item))
            try:
                committed = _read(_inv_path(item))
            except OSError:
                errs.append(f"{tag}: inventory {_inv_path(item)} missing")
                continue
            if committed != inv_text:
                old = {f["path"]: f["sha256"] for f in json.loads(committed).get("files", [])}
                new = {f["path"]: f["sha256"] for f in json.loads(inv_text)["files"]}
                diff = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
                errs.append(f"{tag}: stale inventory; changed constituents: {diff or '(metadata)'}")
                continue
            inv_hash = _sha(_inv_path(item))
            try:
                env_committed = _read(_env_path(item))
            except OSError:
                errs.append(f"{tag}: envelope {_env_path(item)} missing")
                continue
            if env_committed != _dump(_envelope(item, inv_hash)):
                errs.append(f"{tag}: envelope does not match the current inventory hash/declaration")
            pin = manifest.get(str(item))
            if not isinstance(pin, dict) or pin.get("file") != _env_path(item):
                errs.append(f"{tag}: manifest does not cite {_env_path(item)}")
            elif pin.get("content_hash") != inv_hash:
                errs.append(f"{tag}: manifest pin {pin.get('content_hash')} != inventory {inv_hash}")
            errs += [f"{tag}: {e}" for e in _content(item)]
        except (OSError, ValueError) as e:
            errs.append(f"{tag}: {type(e).__name__}: {e}")
    for e in errs:
        print("FAIL", e)
    if errs:
        return 1
    print(f"OK: inventories, envelopes and manifest pins current for items {sorted(ITEMS)}")
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
