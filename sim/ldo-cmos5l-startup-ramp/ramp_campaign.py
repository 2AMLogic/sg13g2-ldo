#!/usr/bin/env python3
"""Driver for the DR-0020 bounded startup-ramp experiment (issue #314). stdlib only.

A thin layer over sim/ldo-cmos5l-pvt-sweep/startup_campaign.py: the startup
bench template, `startup_eval.py`, the request builder and the record writer
are used UNCHANGED. The only differences are (1) the design netlist the bench
includes is the testbench-local `core_with_ramp.spice` (see
gen_core_with_ramp.py), and (2) the 7 DR-0020 points replace the 135-point grid.

Every simulation is a `klt sim --backend batch` submission with
`--wait-for-capacity 600`; nothing runs locally and nothing falls back to local.

    plan    --rid RID            write requests under pvt-sweep/startup/RID/ramp/
    submit  --rid RID            ONE `klt sim --batch-set` over all 7 requests
    collect --rid RID            evaluate, write records/RID-startup-ramp.*
    clauses --rid RID            DR-0020 confirm clauses (a)-(d) per point (md)
"""
import argparse
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SWEEP = os.path.abspath(os.path.join(HERE, "..", "ldo-cmos5l-pvt-sweep"))
sys.path.insert(0, SWEEP)
import startup_campaign as sc  # noqa: E402

WRAPPER = os.path.join(HERE, "core_with_ramp.spice")
STAGE = "ramp"
VREF = 0.9

# Pre-registered BEFORE any run (clause d / b); see README.md.
T_RAMP_CLAIM_US = (180.0, 450.0)   # DR-0020 candidate pairings, <= ~500 us
IPK_REL_MARGIN = 0.25              # clause (b) margin: 25 % of the bound ...
IPK_ABS_MARGIN_A = 1e-3            # ... plus 1 mA (core Iq, ramp branches)
VSG_RATING_V = 3.3


def ramp_points():
    nom = dict(sc.NOMINAL)
    pts = [nom,
           dict(nom, mos="ff", temp=27, vin=3.63, tmax_ns=500),   # worst overshoot
           dict(nom, mos="ss", temp=-40, vin=3.63, tmax_ns=500)]  # slow corner
    for ld in sc.EXT_LOAD_MA:
        for cout, esr in ((330, 0), (4700, 500)):
            pts.append(dict(nom, vin=3.63, load_ma=ld, cout_nf=cout, esr_mohm=esr))
    return pts


def use_wrapper():
    """Point the (unchanged) campaign code at the testbench-local netlist."""
    sc.DESIGN = WRAPPER


def cmd_plan(a):
    use_wrapper()
    n, g = sc.write_requests(a.rid, STAGE, ramp_points())
    sd = sc.stage_dir(a.rid, STAGE)
    # --batch-set names each member after its request file stem
    plan = json.load(open(os.path.join(sd, "plan.json")))
    for grp in plan["groups"]:
        gd = os.path.join(sd, grp["group"])
        os.replace(os.path.join(gd, "request.json"),
                   os.path.join(gd, grp["group"] + ".request.json"))
    print(f"ramp_campaign: {n} points in {g} requests under "
          f"{os.path.relpath(sd, sc.REPO)}")
    return 0


def cmd_submit(a):
    sd = sc.stage_dir(a.rid, STAGE)
    plan = json.load(open(os.path.join(sd, "plan.json")))
    reqs = [os.path.join(sd, g["group"], g["group"] + ".request.json") for g in plan["groups"]]
    out = os.path.join(sd, "batch-out")
    cmd = ["klt", "sim", "--batch-set", *reqs, "--backend", "batch",
           "--wait-for-capacity", "600", "--capacity-retries", "3",
           "-o", out, "--format", "json"]
    with open(os.path.join(sd, "envelope.json"), "w") as o, \
            open(os.path.join(sd, "klt-sim.stderr"), "w") as e:
        rc = subprocess.call(cmd, stdout=o, stderr=e)
    print(f"ramp_campaign: klt sim --batch-set exit {rc}", file=sys.stderr)
    try:
        env = json.load(open(os.path.join(sd, "envelope.json")))
    except (OSError, ValueError):
        print("ramp_campaign: no envelope; job NOT recorded as complete (no local fallback)",
              file=sys.stderr)
        return 1
    for m in env.get("requests", []):
        rep = m.get("report")
        name = os.path.basename(os.path.dirname(rep)) if rep else None
        for g in plan["groups"]:
            if rep and os.path.basename(rep).startswith(g["group"]) or name == g["group"]:
                if os.path.isfile(rep):
                    import shutil
                    shutil.copy(rep, os.path.join(sd, g["group"], "report.json"))
    return 0 if rc in (0, 3) else 1


def cmd_collect(a):
    use_wrapper()
    a.stage = STAGE
    return sc.cmd_collect(a)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def t_ramp_us(raw_path, window_start_s):
    """(10 %..90 % of VREF crossing time)/0.8 on v(xtop.vrefr), and its max."""
    names, data, cplx, _ = sc.bb.read_raw(raw_path)
    t = data[names[0]]
    v = sc.bb.vec(data, "v(xtop.vrefr)")
    lo, hi = 0.1 * VREF, 0.9 * VREF

    def cross(level):
        for i in range(1, len(t)):
            if t[i] >= window_start_s and v[i - 1] < level <= v[i]:
                f = (level - v[i - 1]) / (v[i] - v[i - 1])
                return t[i - 1] + f * (t[i] - t[i - 1])
        return None
    t1, t2 = cross(lo), cross(hi)
    return (None if t1 is None or t2 is None else (t2 - t1) / 0.8 * 1e6), max(v)


def cmd_clauses(a):
    """Evaluate clauses (a)-(d) from the committed record CSV + raw files."""
    rec = os.path.join(sc.HERE, "records", f"{a.rid}-startup-{STAGE}.csv")
    rows = list(csv.DictReader(open(rec)))
    out = ["| point | (a) start/reen verdict | (b) Ipk A / bound A | (c) Vsg start/reen V | (d) T_ramp us (start/reen) | VREFR max V |",
           "|---|---|---|---|---|---|"]
    ok_all = True
    for r in rows:
        raw = None
        sd = sc.stage_dir(a.rid, STAGE)
        rep = json.load(open(os.path.join(sd, r["group"], "report.json")))
        for c in rep.get("corners", []):
            if (c["process"] == sc.section(dict(mos=r["mos"], res=r["res"])) and
                    float(c["temperature_c"]) == float(r["temp"]) and
                    round(float((c.get("supply_v") or {}).get("vin", 0)), 2) == round(float(r["vin"]), 2)):
                raw = (c.get("artifacts") or {}).get("raw")
        tr_s = tr_r = vmax = None
        if raw and os.path.isfile(raw):
            tr_s, vmax = t_ramp_us(raw, 1.0e-3)
            tr_r, _ = t_ramp_us(raw, 9.0e-3)
        load = _num(r["load_ma"]) / 1000.0
        cout = _num(r["cout_nf"]) * 1e-9
        ipk = _num(r.get("start_peak_supply_current_a"))
        bound = None if not tr_s else (cout * 2 * VREF / (tr_s * 1e-6) + load)
        lim = None if bound is None else bound * (1 + IPK_REL_MARGIN) + IPK_ABS_MARGIN_A
        a_ok = r.get("verdict") == "pass" and r.get("reen_pass") in ("True", "true", "1")
        vs, vr = _num(r.get("start_max_vsg_pass_v")), _num(r.get("reen_max_vsg_pass_v"))
        c_ok = vs is not None and vr is not None and vs <= VSG_RATING_V and vr <= VSG_RATING_V
        b_ok = ipk is not None and lim is not None and ipk <= lim
        d_ok = all(x is not None and T_RAMP_CLAIM_US[0] <= x <= T_RAMP_CLAIM_US[1]
                   for x in (tr_s, tr_r))
        ok_all &= bool(a_ok and b_ok and c_ok and d_ok)
        f = lambda x, n=4: "n/a" if x is None else f"{x:.{n}g}"
        out.append(f"| `{r['point']}` | {r.get('verdict')}/{r.get('reen_pass')} {'ok' if a_ok else 'FAIL'} "
                   f"| {f(ipk)} / {f(lim)} {'ok' if b_ok else 'FAIL'} "
                   f"| {f(vs)}/{f(vr)} {'ok' if c_ok else 'FAIL'} "
                   f"| {f(tr_s)}/{f(tr_r)} {'ok' if d_ok else 'FAIL'} | {f(vmax)} |")
    out.append("")
    out.append(f"**Overall: {'CONFIRM' if ok_all and len(rows) == 7 else 'REJECT'}** "
               f"({len(rows)} of 7 points)")
    print("\n".join(out))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("plan", "submit", "collect", "clauses"):
        s = sub.add_parser(n)
        s.add_argument("--rid", required=True)
    a = ap.parse_args()
    try:
        return {"plan": cmd_plan, "submit": cmd_submit, "collect": cmd_collect,
                "clauses": cmd_clauses}[a.cmd](a)
    except (sc.CampaignError, KeyError) as e:
        print(f"ramp_campaign: ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
