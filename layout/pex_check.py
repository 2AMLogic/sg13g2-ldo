#!/usr/bin/env python3
"""Bind a committed `klt pex` report to its inputs.

    pex_check.py REPORT NETLIST                       extract-only: verify;
                                                      exit 1 naming the drift
    pex_check.py --perturb NETLIST OUT                write OUT with one
                                                      parasitic changed
    pex_check.py --row4 REPORT NETLIST GDS DESIGN     measured row-4 report:
                                                      verify against all four
                                                      committed files

`klt pex` has no `--check` mode of its own, so the report's own hash pins are
re-hashed here against the working tree. The extract-only mode (issue #172)
binds `extraction.netlist_sha256` to the extracted netlist and requires
`measurement.mode` to be `extract-only`. The --row4 mode (issue #312) binds
the measured testbench-mode report on all three content identities the report
pins -- `provenance.input.content_hash` (the GDS), `extraction.netlist_sha256`
(the extracted netlist) and `reference_netlist_sha256` (the schematic design
netlist) -- and validates the delta coverage against the row-4 envelope's own
45-corner grid and measurement names (imported from
sim/ldo-cmos5l-pvt-sweep/row4_envelope.py, never restated here). Stdlib only.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_SIM = os.path.join(HERE, "..", "sim", "ldo-cmos5l-pvt-sweep")


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(report_path, netlist_path):
    d = json.load(open(report_path))
    errs = []
    if d.get("measurement", {}).get("mode") != "extract-only":
        errs.append("measurement.mode is not extract-only")
    want = d["extraction"]["netlist_sha256"]
    got = sha256_file(netlist_path)
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


def check_row4(report_path, netlist_path, gds_path, design_path):
    sys.path.insert(0, _SIM)
    import row4_envelope as r4  # the row-4 grid and measurement names

    d = json.load(open(report_path))
    errs = []

    if d.get("measurement", {}).get("mode") != "testbench":
        errs.append(f"measurement.mode is {d.get('measurement', {}).get('mode')!r}, "
                    "not 'testbench' -- this is not a measured report")
    status = d.get("status")
    if status not in ("pass", "fail"):
        errs.append(f"status is {status!r} -- a measured run grades 'pass' or "
                    "'fail' ('fail' is an honest limit miss); anything else "
                    "carries no trustworthy comparison")
    for key in ("pin_count_mismatch", "flat_dut_mismatch", "pin_order_mismatch",
                "backend_failure"):
        if d.get(key) is not None:
            errs.append(f"{key} is non-null -- the two DUT roots did not bind")
    if d.get("unfinished"):
        errs.append(f"unfinished legs remain: {d['unfinished']}")

    want_gds = (d.get("provenance") or {}).get("input", {}).get("content_hash")
    got_gds = "sha256:" + sha256_file(gds_path)
    if want_gds != got_gds:
        errs.append(f"provenance.input.content_hash drifted: report {want_gds}, "
                    f"GDS {got_gds}")
    want_nl = (d.get("extraction") or {}).get("netlist_sha256")
    got_nl = sha256_file(netlist_path)
    if want_nl != got_nl:
        errs.append(f"extraction.netlist_sha256 drifted: report {str(want_nl)[:12]}, "
                    f"netlist {got_nl[:12]}")
    want_des = d.get("reference_netlist_sha256")
    got_des = "sha256:" + sha256_file(design_path)
    if want_des != got_des:
        errs.append(f"reference_netlist_sha256 drifted: report {want_des}, "
                    f"design netlist {got_des}")

    bb = (d.get("body_bias") or {}).get("status")
    if bb not in ("biased", "tied"):
        errs.append(f"body_bias.status is {bb!r}, not 'biased'/'tied' -- the "
                    "post-layout numbers were measured on a floating-body netlist")

    tbs = d.get("testbenches") or []
    names = sorted(r4.GRADED + r4.UNGRADED)
    if len(tbs) != 1 or sorted(tbs[0].get("measurement_names") or []) != names:
        errs.append(f"testbenches[] does not name exactly the row-4 measurements "
                    f"{names}: {[t.get('measurement_names') for t in tbs]}")

    expected = {(r4.corner_id(*c), m) for c in r4.coords() for m in names}
    seen = {}
    for row in d.get("delta") or []:
        key = (row.get("corner_id"), row.get("measurement"))
        seen[key] = seen.get(key, 0) + 1
        graded = row.get("measurement") in r4.GRADED
        if graded and row.get("status") not in ("pass", "fail"):
            errs.append(f"delta row {key} status {row.get('status')!r} -- a "
                        "graded comparison must have run and been limited")
        for side in ("schematic_value", "extracted_value"):
            if not _is_number(row.get(side)):
                errs.append(f"delta row {key} has non-numeric {side}: "
                            f"{row.get(side)!r}")
    dup = sorted(k for k, n in seen.items() if n > 1)
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    if dup:
        errs.append(f"duplicate (corner, measurement) delta rows: {dup[:5]}"
                    f"{'...' if len(dup) > 5 else ''}")
    if missing:
        errs.append(f"missing (corner, measurement) delta rows: {missing[:5]} "
                    f"of {len(missing)}")
    if extra:
        errs.append(f"unexpected (corner, measurement) delta rows: {extra[:5]} "
                    f"of {len(extra)}")

    n = len(expected)
    print(f"  pex-row4: status={status}, {d.get('passed')} passed / "
          f"{d.get('failed')} failed of {len(d.get('delta') or [])} delta rows "
          f"({n} expected: {len(r4.coords())} corners x {len(names)} measurements), "
          f"body_bias.status={bb}, klt {d.get('provenance', {}).get('klt_version')}")
    worst = None
    for row in d.get("delta") or []:
        if row.get("measurement") == "vin_1pct_loss_v" and _is_number(row.get("extracted_value")):
            drop = row["extracted_value"] - r4.VOUT_TARGET_V
            if worst is None or drop > worst[1]:
                worst = (row["corner_id"], drop)
    if worst:
        print(f"  worst extracted dropout: {worst[1] * 1000:.2f} mV at {worst[0]} "
              f"(target <{r4.TARGET_DROPOUT_V * 1000:.0f} mV)")
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
    if len(a) == 5 and a[0] == "--row4":
        sys.exit(check_row4(a[1], a[2], a[3], a[4]))
    sys.exit(__doc__)
