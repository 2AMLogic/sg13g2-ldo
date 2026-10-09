#!/usr/bin/env python3
"""Derive and verify the ``ties[]`` of a ``klt erc`` supply spec from the tap
bars the layout generator actually drew (T1 item 11, #59).

The tap geometry is never typed by hand: ``generate.py`` records every
``draw_tap_bar`` call and writes ``erc-tap-boxes.json`` beside the GDS; this
module turns that document into the spec's ``ties[]`` and ``--check`` asserts
the committed spec carries exactly those entries, so a moved tap bar cannot
leave a stale, still-"clean" assertion behind.

    layout/erc_ties.py --check <erc-tap-boxes.json> <erc-supply-spec.json>
    layout/erc_ties.py --print <erc-tap-boxes.json>      # the ties[] JSON
    layout/erc_ties.py --mutate <tap-boxes.json> <spec.json> <out.json>
        # negative control: same spec, TAIL tap boxes shifted off the drawn
        # tap, for the run_flow.sh falsifiability stage

Layer numbers are SG13CMOS5L's: NWell 31/0, Activ 1/0, nSD 7/0, pSD 14/0.
The nwell ties are layer-derived as well as box-asserted (``tap_requires``
nSD); the substrate tie sits in native substrate, so its region is asserted
(``well_layer: null`` + ``well_boxes``).
"""

from __future__ import annotations

import json
import sys

NWELL, ACTIV, NSD, PSD = "31/0", "1/0", "7/0", "14/0"


def ties_from_taps(doc: dict) -> list[dict]:
    ties = []
    for g in doc["taps"]:
        if g["kind"] == "nwell":
            ties.append({
                "name": f"nwell_tie_{g['net']}",
                "well_layer": NWELL,
                # Select the well(s) this tie's own taps sit in, so the TAIL
                # well is not graded against the VIN net and vice versa.
                "well_requires_boxes": g["tap_boxes"],
                "tap_layer": ACTIV,
                "tap_requires": [NSD],
                "tap_boxes": g["tap_boxes"],
                "connect_to": "Metal1",
                "net": g["net"],
            })
        else:
            ties.append({
                "name": f"substrate_tie_{g['net']}",
                "well_layer": None,
                "well_boxes": g["well_boxes"],
                "tap_layer": ACTIV,
                "tap_requires": [PSD],
                "tap_boxes": g["tap_boxes"],
                "connect_to": "Metal1",
                "net": g["net"],
            })
    return ties


def main(argv: list[str]) -> int:
    mode = argv[1]
    doc = json.load(open(argv[2]))
    ties = ties_from_taps(doc)
    if mode == "--print":
        print(json.dumps(ties, indent=2))
        return 0
    spec = json.load(open(argv[3]))
    if mode == "--check":
        if spec.get("ties") != ties:
            print("erc-supply-spec.json ties[] != ties derived from "
                  "erc-tap-boxes.json -- regenerate the spec's ties[]",
                  file=sys.stderr)
            return 1
        print(f"  spec ties[] == generator tap bars ({len(ties)} ties)")
        return 0
    if mode == "--mutate":
        for t in spec["ties"]:
            if t["name"] == "nwell_tie_TAIL":
                t["tap_boxes"] = [[x0 + 30.0, y0, x1 + 30.0, y1]
                                  for x0, y0, x1, y1 in t["tap_boxes"]]
        json.dump(spec, open(argv[4], "w"), indent=1)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
