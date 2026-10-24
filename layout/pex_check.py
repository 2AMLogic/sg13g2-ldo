#!/usr/bin/env python3
"""Bind a committed `klt pex --extract-only` report to its extracted netlist.

    pex_check.py REPORT NETLIST            verify; exit 1 naming the drift
    pex_check.py --perturb NETLIST OUT     write OUT with one parasitic changed

`klt pex` has no `--check` mode of its own, so the report's
`extraction.netlist_sha256` is re-hashed against the netlist here. The report
must also be an extraction-only one with `body_bias` stated (issue #172).
Stdlib only.
"""
import hashlib
import json
import re
import sys


def check(report_path, netlist_path):
    d = json.load(open(report_path))
    errs = []
    if d.get("measurement", {}).get("mode") != "extract-only":
        errs.append("measurement.mode is not extract-only")
    want = d["extraction"]["netlist_sha256"]
    got = hashlib.sha256(open(netlist_path, "rb").read()).hexdigest()
    if got != want:
        errs.append(f"extraction.netlist_sha256 drifted: report {want[:12]}, netlist {got[:12]}")
    bb = d["body_bias"]
    print(f"  pex: {d['extraction']['device_count']} devices, "
          f"{d['extraction']['net_count']} nets, body_bias.status={bb['status']}, "
          f"klt {d['provenance']['klt_version']}")
    if bb["status"] == "unbiased":
        print(f"  NOTE body_bias is UNBIASED: {bb['unbiased_nets']}", file=sys.stderr)
    for e in errs:
        print(f"DRIFT: {e}", file=sys.stderr)
    return 1 if errs else 0


def perturb(src, dst):
    text = open(src).read()
    # First extracted parasitic resistor card: `R<name> <n1> <n2> <ohms>`.
    new, n = re.subn(r"^(R\S+ \S+ \S+ )([0-9.eE+-]+)$",
                     lambda m: m.group(1) + repr(float(m.group(2)) * 1.5),
                     text, count=1, flags=re.M)
    if n != 1:
        print("no parasitic resistor card found to perturb", file=sys.stderr)
        return 1
    open(dst, "w").write(new)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "--perturb":
        sys.exit(perturb(a[1], a[2]))
    if len(a) == 2:
        sys.exit(check(a[0], a[1]))
    sys.exit(__doc__)
