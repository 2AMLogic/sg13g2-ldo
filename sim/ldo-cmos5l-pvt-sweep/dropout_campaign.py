#!/usr/bin/env python3
"""Bounded row-4 dropout campaign under DR-0009 (issue #70).  PROPOSED.

45 points = {tt,ff,ss,sf,fs} MOS x {-40,27,125} C x {res_typ,res_bcs,res_wcs},
one 50 mA block each, Vin 1.700..3.630 V at 5 mV (testbench/
tb_dropout_cmos5l.spice.tmpl).  This is a SPICE grid, so it is submitted to the
EDA batch fleet through batch_backend.py (`klt sim --backend batch`); there is
NO local-ngspice path in this script and a failed submission is never retried
locally -- the affected points stay in the accounting as failed.

    python3 sim/ldo-cmos5l-pvt-sweep/dropout_campaign.py run        # mint a new record
    python3 sim/ldo-cmos5l-pvt-sweep/dropout_campaign.py run --plan-only
    python3 sim/ldo-cmos5l-pvt-sweep/dropout_campaign.py reduce <record-id>
        # offline: re-derive records/<id>.dropout.* from corners/<id>/

Append-only: `run` mints a NEW timestamped id and refuses to touch any
existing records/, corners/ or netlist-snapshots/ entry.  `reduce` rewrites
only that id's own records/<id>.dropout.* files and is byte-deterministic
(--check compares instead of writing).
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import dropout_metrics as dcm  # noqa: E402

CORNERS = ["tt", "ff", "ss", "sf", "fs"]
TEMPS = [-40, 27, 125]
RES = ["typ", "bcs", "wcs"]
TARGET_V = 0.300           # ratified row-4 limit, DR-0007: "< 300 mV"; NOT relaxed here
LOAD_A = dcm.DR0009_LOAD_A
TEMPLATE = "sim/ldo-cmos5l-pvt-sweep/testbench/tb_dropout_cmos5l.spice.tmpl"
DESIGN_NETLISTS = ["design/sg13cmos5l/netlist/ldo_core_cmos5l.spice",
                   "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"]
INPUTS = [TEMPLATE, "sim/ldo-cmos5l-pvt-sweep/dropout_metrics.py", "sim/ldo-cmos5l-pvt-sweep/dc_metrics.py",
          "sim/ldo-cmos5l-pvt-sweep/dropout_campaign.py",
          "sim/ldo-cmos5l-pvt-sweep/batch_backend.py", "sim/pdk-cmos5l.json"] + DESIGN_NETLISTS
FATAL = re.compile(r"Unable to find definition of model|couldn't be loaded|Unknown model type|"
                   r"fatal error|gmin stepping failed|no convergence|iteration limit reached", re.I)
SINGULAR = re.compile(r"singular matrix", re.I)


def sha(rel):
    with open(os.path.join(REPO, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def coords():
    for c in CORNERS:
        for t in TEMPS:
            for r in RES:
                yield c, t, r, f"dcsweep_{c}_{t}c_r{r}"


def log_problem(log):
    """Same fatal-error screen as run_sweep.sh screen_point (a recoverable
    `Warning: singular matrix` is not fatal)."""
    try:
        with open(log, errors="replace") as fh:
            text = fh.read()
    except FileNotFoundError:
        return "no log"
    if FATAL.search(text):
        return "fatal signature in log"
    for ln in text.splitlines():
        if SINGULAR.search(ln) and not ln.strip().startswith("Warning:"):
            return "unrecovered singular matrix"
    return None


def reduce_dir(corners_dir):
    pts = []
    for c, t, r, pid in coords():
        res = dcm.dropout_1pct_file(os.path.join(corners_dir, f"{pid}_dc.csv"))
        bad = log_problem(os.path.join(corners_dir, f"{pid}.log"))
        if bad and res.get("status") == "resolved":
            res = {"status": "malformed", "reason": bad}
        pts.append({"corner": c, "temp_c": t, "res_section": f"res_{r}", "point_id": pid, **res})
    return pts


def summarise(pts):
    n = len(pts)
    resolved = [p for p in pts if p["status"] == "resolved"]
    by_status = {}
    for p in pts:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
    summ = {"n_expected": 45, "n_points": n, "n_resolved": len(resolved),
            "status_counts": dict(sorted(by_status.items())),
            "coordinates_exactly_once": sorted(p["point_id"] for p in pts) == sorted(x[3] for x in coords()),
            "definitive": False}
    if resolved:
        w = max(resolved, key=lambda p: p["dropout_1pct_upper_v"])
        wi = max(resolved, key=lambda p: p["dropout_1pct_vin_minus_vout_v"])
        summ["worst_by_upper_bound"] = {k: w[k] for k in ("corner", "temp_c", "res_section",
                                         "dropout_1pct_vin_minus_vout_v", "dropout_1pct_lower_v",
                                         "dropout_1pct_upper_v", "bracket_v")}
        summ["worst_by_interpolated"] = {"corner": wi["corner"], "temp_c": wi["temp_c"],
                                         "res_section": wi["res_section"],
                                         "dropout_1pct_vin_minus_vout_v": wi["dropout_1pct_vin_minus_vout_v"]}
        summ["lowest_crossing_vin_v"] = min(p["vin_cross_v"] for p in resolved)
    if len(resolved) == 45 and n == 45 and summ["coordinates_exactly_once"]:
        summ["definitive"] = True
        up = summ["worst_by_upper_bound"]["dropout_1pct_upper_v"]
        margin = TARGET_V - up
        summ["target_v"] = TARGET_V
        summ["margin_to_target_v"] = margin
        summ["series_resistance_equivalent_ohm"] = margin / LOAD_A
        summ["lower_bound_below_every_crossing"] = dcm.DR0009_VIN_LO < summ["lowest_crossing_vin_v"]
    return summ


def f9(v):
    if v is None:
        return ""
    return f"{v:.9g}" if isinstance(v, float) else str(v)


def csv_text(pts):
    cols = ["corner", "temp_c", "res_section", "dropout_dr0009_status",
            "dropout_1pct_vin_minus_vout_v", "dropout_1pct_lower_v", "dropout_1pct_upper_v",
            "vin_cross_v", "v_reg_v", "v_thr_v", "bracket_v", "detail"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for p in pts:
        w.writerow([p["corner"], p["temp_c"], p["res_section"], p["status"],
                    f9(p.get("dropout_1pct_vin_minus_vout_v")), f9(p.get("dropout_1pct_lower_v")),
                    f9(p.get("dropout_1pct_upper_v")), f9(p.get("vin_cross_v")), f9(p.get("v_reg_v")),
                    f9(p.get("v_thr_v")), f9(p.get("bracket_v")), p.get("reason", "")])
    return buf.getvalue()


def md_text(rid, summ, meta):
    L = [f"# Row-4 dropout campaign `{rid}` (DR-0009 definition, PROPOSED)", "",
         "Quantity: **`dropout_1pct_vin_minus_vout_v`** = Vin* - 0.99 x VOUT(50 mA, Vin = 3.30 V), "
         "Vin* the linearly interpolated Vin at which VOUT = 0.99 x VOUT(3.30 V) scanning down from 3.30 V. "
         "This is NOT the legacy `dropout_v_50ma` (lowest regulating 10 mV-grid Vin minus the fixed 1.8 V). "
         "DR-0009 is `proposed`; nothing here is ratified and the ratified `< 300 mV` target is unchanged.", "",
         f"- Points: {summ['n_points']}/45 present, {summ['n_resolved']} resolved, status counts {summ['status_counts']}.",
         f"- Every coordinate exactly once: {summ['coordinates_exactly_once']}.",
         f"- Definitive worst-corner claim permitted: **{summ['definitive']}** "
         "(requires all 45 resolved; any failed/malformed/floor-limited point blocks it)."]
    if "worst_by_upper_bound" in summ:
        w = summ["worst_by_upper_bound"]
        L += ["", f"- Worst coordinate (conservative, by bracket upper bound): `{w['corner']}` / {w['temp_c']} C / "
              f"`{w['res_section']}`: interpolated {w['dropout_1pct_vin_minus_vout_v']*1000:.2f} mV, "
              f"bracket [{w['dropout_1pct_lower_v']*1000:.2f}, {w['dropout_1pct_upper_v']*1000:.2f}] mV "
              f"(grid bracket {w['bracket_v']*1000:.1f} mV).",
              f"- Lowest crossing Vin among resolved points: {summ['lowest_crossing_vin_v']:.4f} V "
              f"(sweep lower bound {dcm.DR0009_VIN_LO:.3f} V)."]
    if summ["definitive"]:
        L += [f"- Margin to the {TARGET_V*1000:.0f} mV target (upper bound): {summ['margin_to_target_v']*1000:.2f} mV.",
              f"- Series-resistance equivalent: {summ['margin_to_target_v']*1000:.2f} mV / {LOAD_A*1000:.0f} mA = "
              f"{summ['series_resistance_equivalent_ohm']:.3f} ohm (before any parasitic extraction).",
              f"- Lower bound below every observed crossing: {summ['lower_bound_below_every_crossing']}."]
    L += ["", "## Provenance", ""]
    for k, v in sorted(meta.items()):
        L.append(f"- {k}: {v}" if not isinstance(v, (dict, list)) else f"- {k}: `{json.dumps(v, sort_keys=True)}`")
    L += ["", f"Per-point values: `{rid}.dropout.csv`; machine summary: `{rid}.dropout.json`.", ""]
    return "\n".join(L)


def write_outputs(rid, corners_dir, meta, check=False):
    pts = reduce_dir(corners_dir)
    summ = summarise(pts)
    out = os.path.join(HERE, "records")
    files = {f"{rid}.dropout.csv": csv_text(pts),
             f"{rid}.dropout.json": json.dumps({"record_id": rid, "summary": summ, "provenance": meta,
                                                "points": pts}, indent=1, sort_keys=True) + "\n",
             f"{rid}.dropout.md": md_text(rid, summ, meta)}
    bad = []
    for name, text in files.items():
        path = os.path.join(out, name)
        if check:
            if not os.path.exists(path) or open(path).read() != text:
                bad.append(name)
        else:
            with open(path, "w") as f:
                f.write(text)
    return summ, bad


def cmd_run(a):
    sha7 = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + sha7
    snaps, corners = (os.path.join(HERE, d, rid) for d in ("netlist-snapshots", "corners"))
    for d in (snaps, corners):
        if os.path.exists(d):
            sys.exit(f"dropout_campaign: {d} exists; records are append-only")
    pdk = "ihp-sg13cmos5l"
    env = subprocess.run(["bash", "-c", f"export PDK={pdk}; source {REPO}/sim/env.sh >/dev/null 2>&1; "
                          "echo $PDK_ROOT; echo $SG13G2_OSDI_DIR"], capture_output=True, text=True).stdout.split()
    if len(env) != 2:
        sys.exit("dropout_campaign: cannot resolve PDK_ROOT/OSDI dir from sim/env.sh")
    pdk_root, osdi = env
    os.makedirs(snaps)
    os.makedirs(corners)
    tmpl = open(os.path.join(REPO, TEMPLATE)).read()
    queue_dir = tempfile.mkdtemp(prefix="dropout-campaign.")
    queue = os.path.join(queue_dir, "queue.tsv")
    with open(queue, "w") as q:
        for c, t, r, pid in coords():
            text = tmpl
            for k, v in {"PDK_ROOT": pdk_root, "PDK": pdk, "OSDI_DIR": osdi, "MOS_SECTION": f"mos_{c}",
                         "RES_SECTION": f"res_{r}", "CAP_SECTION": "cap_typ", "TEMP": str(t),
                         "DESIGN_NETLIST": os.path.join(REPO, DESIGN_NETLISTS[0]),
                         "DC_CSV": os.path.join(corners, f"{pid}_dc.csv")}.items():
                text = text.replace(f"@@{k}@@", v)
            path = os.path.join(snaps, f"{pid}.spice")
            open(path, "w").write(text)
            q.write(f"{pid}\t{path}\n")
    cmd = [sys.executable, os.path.join(HERE, "batch_backend.py"), "run", "--queue", queue,
           "--corners-out", corners, "--work", os.path.join(queue_dir, "work"), "--osdi-dir", osdi,
           "--submit-concurrency", "2"] + (["--plan-only"] if a.plan_only else [])
    print("dropout_campaign: " + " ".join(cmd[1:]), file=sys.stderr)
    rc = subprocess.run(cmd).returncode
    if a.plan_only:
        print(f"dropout_campaign: plan only; delete {snaps} and {corners} by hand.", file=sys.stderr)
        return rc
    bj = os.path.join(corners, "_batch", "backend.json")
    backend = json.load(open(bj)) if os.path.exists(bj) else {}
    meta = {"record_id": rid, "git_sha": sha7,
            "invocation": f"python3 sim/ldo-cmos5l-pvt-sweep/dropout_campaign.py run  (batch_backend.py exit {rc})",
            "backend": backend.get("backend", "none"), "client_klt": backend.get("client_klt"),
            "runner_klt": backend.get("runner_klt"), "engines": backend.get("engines"),
            "jobs": [{k: j.get(k) for k in ("group", "job_id", "corners", "requested", "lifecycle")}
                     for j in backend.get("jobs", [])],
            "staged_osdi_sha256": backend.get("staged_osdi_sha256"),
            "input_sha256": {p: sha(p) for p in INPUTS},
            "sweep": {"vin_v": [dcm.DR0009_VIN_LO, dcm.DR0009_VIN_HI, dcm.DR0009_VIN_STEP],
                      "load_a": LOAD_A, "vin_ref_v": dcm.DR0009_VIN_REF, "loss": dcm.DR0009_LOSS},
            "pdk": pdk, "pdk_pin": "sim/pdk-cmos5l.json"}
    have = [f for f in os.listdir(corners) if f.endswith("_dc.csv")]
    if not have:
        print(f"dropout_campaign: NO point returned data (batch_backend.py exit {rc}); "
              f"no record minted. Scratch deck dir {snaps} and {corners} hold only the failed attempt.", file=sys.stderr)
        return rc or 1
    summ, _ = write_outputs(rid, corners, meta)
    print(json.dumps(summ, indent=1, sort_keys=True))
    return 0 if summ["definitive"] and rc == 0 else 1


def cmd_reduce(a):
    corners = os.path.join(HERE, "corners", a.record_id)
    jf = os.path.join(HERE, "records", f"{a.record_id}.dropout.json")
    meta = json.load(open(jf))["provenance"] if os.path.exists(jf) else {"record_id": a.record_id}
    summ, bad = write_outputs(a.record_id, corners, meta, check=a.check)
    if a.check and bad:
        print("dropout_campaign: --check: stale or missing: " + ", ".join(bad), file=sys.stderr)
        return 1
    print(json.dumps(summ, indent=1, sort_keys=True))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--plan-only", action="store_true")
    r.set_defaults(fn=cmd_run)
    d = sp.add_parser("reduce")
    d.add_argument("record_id")
    d.add_argument("--check", action="store_true")
    d.set_defaults(fn=cmd_reduce)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
