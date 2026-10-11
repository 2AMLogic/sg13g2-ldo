#!/usr/bin/env python3
"""Run item5_evidence.py under the shared complete-grid contract (issue #120).

item5_evidence.py is pinned by sha256 inside its own landed, append-only
outputs (evidence/<record-id>/coverage-inventory.json, `generator.sha256`),
so it cannot be edited to import dc_grid.py without rewriting landed
evidence. This thin wrapper instead rebinds item5_evidence.split_blocks to
dc_grid.validate_file at run time. The generator file stays byte-identical,
its committed outputs still reproduce byte-for-byte, and the offline item-5
analysis enforces exactly the contract the live sweep post-processing in
run_sweep.sh enforces (same function, same module).

    python3 sim/ldo-cmos5l-pvt-sweep/item5_grid.py --check   # CI: strict contract + byte-compare
    python3 sim/ldo-cmos5l-pvt-sweep/item5_grid.py           # (re)write, same bytes

A grid the shared validator rejects makes the point invalid with its reason
in `grid_problems`; for the committed record that means reproduce_record()
reports it and the run fails instead of measuring through a bad grid.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import dc_grid as dcg  # noqa: E402
import item5_evidence as ev  # noqa: E402

_LEGACY_SPLIT_BLOCKS = ev.split_blocks


def split_blocks(path):
    """Shared-contract replacement for item5_evidence.split_blocks: same
    (blocks, problems) shape, path resolved against ev.REPO as before."""
    return dcg.validate_file(os.path.join(ev.REPO, path))


def install():
    """Route item5_evidence's grid splitting through dc_grid.validate_file."""
    ev.split_blocks = split_blocks


def uninstall():
    ev.split_blocks = _LEGACY_SPLIT_BLOCKS


def main():
    install()
    ev.main()


if __name__ == "__main__":
    main()
