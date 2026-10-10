#!/usr/bin/env python3
"""Startup campaign driver for the SG13CMOS5L core (issue #69). stdlib only.

Every simulation goes to the EDA batch fleet as `klt sim --backend batch`
requests. This script never launches ngspice itself and never falls back to
local execution: a failed submit leaves the affected points MISSING, which
the record reports as incomplete coverage (requested vs completed).

Stages (see README.md "Startup campaign (issue #69)"):

    nominal    1 point:  mos_tt / 27 C / res_typ / 3.30 V, 1 mA / 1 uF / 0 ohm
    grid       135 points: MOS {tt,ff,ss,fs,sf} x T {-40,27,125} x
               res {typ,bcs,wcs} x Vin {2.97,3.30,3.63}, nominal load/Cout/ESR
    ext        load {0,50 mA} x Cout {0.33,4.7 uF} x ESR {0,0.5 ohm} at each
               binding PVT/supply point chosen from the grid record
    halfstep   the binding points rerun with the timestep cap halved (0.5 us)

Subcommands:
    plan    --stage S --rid RID [--binding CSV]   write requests under
                                                  startup/RID/S/
    submit  --stage S --rid RID                   klt sim --backend batch
    collect --stage S --rid RID                   evaluate, write records/
    binding --grid-csv CSV                        print the binding points
"""
import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import batch_backend as bb  # noqa: E402
import startup_eval as se  # noqa: E402

TEMPLATE = os.path.join(HERE, "testbench", "tb_startup_cmos5l.spice.tmpl")
DESIGN = os.path.join(REPO, "design", "sg13cmos5l", "netlist", "ldo_core_cmos5l.spice")
PDK = "ihp-sg13cmos5l"
T_STOP = "15m"
CORNER_TIMEOUT_S = 150   # per corner; a nominal corner runs in ~2 s

MOS = ("tt", "ff", "ss", "fs", "sf")
TEMPS = (-40, 27, 125)
RES = ("typ", "bcs", "wcs")
VINS = (2.97, 3.30, 3.63)
NOMINAL = dict(mos="tt", temp=27, res="typ", vin=3.30, load_ma="1", cout_nf=1000,
               esr_mohm=0, tmax_ns=1000)
EXT_LOAD_MA = ("0", "50")
EXT_COUT_NF = (330, 4700)
EXT_ESR_MOHM = (0, 500)


class CampaignError(Exception):
    pass


# ---- points ----------------------------------------------------------------
def point_id(p):
    return (f"st_{p['mos']}_{p['temp']}c_r{p['res']}_v{round(p['vin'] * 1000)}mv"
            f"_i{p['load_ma']}ma_c{p['cout_nf']}nf_e{p['esr_mohm']}mohm_t{p['tmax_ns']}ns")


def section(p):
    return f"mos_{p['mos']}__res_{p['res']}__cap_typ"


def load_resistor(load_ma):
    """Resistive load that draws load_ma at 1.8 V ('0' -> no resistor)."""
    from decimal import Decimal
    i = Decimal(load_ma)
    if i == 0:
        return None
    r = Decimal("1.8") / (i / 1000)
    return format(r.normalize(), "f")


def grid_points():
    return [dict(NOMINAL, mos=m, temp=t, res=r, vin=v)
            for m in MOS for t in TEMPS for r in RES for v in VINS]


def ext_points(binding):
    """Load x Cout x ESR extension at each binding PVT/supply point."""
    out = []
    for b in binding:
        for ld in EXT_LOAD_MA:
            for c in EXT_COUT_NF:
                for e in EXT_ESR_MOHM:
                    out.append(dict(b, load_ma=ld, cout_nf=c, esr_mohm=e))
    return out


def halfstep_points(binding):
    return [dict(b, tmax_ns=500) for b in binding]


# ---- request generation ----------------------------------------------------
def render_body(p, design_rel, preamble_rel):
    tmpl = open(TEMPLATE, encoding="utf-8").read()
    r = load_resistor(p["load_ma"])
    rload = f"Rload VOUT 0 {r}" if r else "* Rload omitted: load = 0 (output open)"
    if p["esr_mohm"] == 0:
        bottom, esr_line = "0", "* ESR = 0: Cout wired straight to ground"
    else:
        bottom, esr_line = "COUT_ESR", f"Resr COUT_ESR 0 {p['esr_mohm']}e-3"
    vin = f"{p['vin']:.2f}"
    body = (tmpl.replace("@@DESIGN_NETLIST@@", design_rel)
            .replace("@@VIN_V@@", vin)
            .replace("@@RLOAD_LINE@@", rload)
            .replace("@@COUT_BOTTOM@@", bottom)
            .replace("@@COUT_F@@", f"{p['cout_nf']}n")
            .replace("@@ESR_LINE@@", esr_line))
    if "@@" in body:
        raise CampaignError("unsubstituted placeholder in rendered body")
    lines = body.splitlines()
    # the preamble (pre_osdi of the staged binaries) goes in front, as in
    # batch_backend.py
    return f'.include "{preamble_rel}"\n' + "\n".join(lines) + "\n"


def tran_args(tmax_ns):
    step = f"{tmax_ns}n"
    return f"{step} {T_STOP} 0 {step}"


def group_key(p):
    # One request per (body, process section): its (temperature, supply)
    # cross product is the klt corner axes. A job that hangs or dies then
    # costs at most that section's 9 corners (a first attempt with 45
    # corners per request lost all 45 to one job timeout).
    return (section(p), p["load_ma"], p["cout_nf"], p["esr_mohm"], p["tmax_ns"])


def build_groups(points):
    """Points sharing a body and process section form one request, provided
    their (temperature, Vin) set is a cross product; otherwise split per
    temperature."""
    by = {}
    for p in points:
        by.setdefault(group_key(p), []).append(p)
    groups = []
    for key, members in sorted(by.items()):
        temps = sorted({p["temp"] for p in members})
        vins = sorted({p["vin"] for p in members})
        pairs = {(p["temp"], p["vin"]) for p in members}
        if pairs == {(t, v) for t in temps for v in vins}:
            groups.append(members)
        else:
            for t in temps:
                groups.append([p for p in members if p["temp"] == t])
    return groups


def stage_dir(rid, stage):
    return os.path.join(HERE, "startup", rid, stage)


def write_requests(rid, stage, points):
    root = os.path.join(HERE, "startup", rid)
    sd = stage_dir(rid, stage)
    os.makedirs(sd, exist_ok=True)
    osdi_dir = os.path.join(os.environ["PDK_ROOT"], PDK, "libs.tech", "ngspice", "osdi")
    for n in bb.OSDI_ORDER:
        if not os.path.isfile(os.path.join(osdi_dir, f"{n}.osdi")):
            raise CampaignError(f"OSDI binary to stage is missing: {osdi_dir}/{n}.osdi")
    preamble = os.path.join(root, "osdi-preamble.cir")
    with open(preamble, "w") as f:
        f.write("* generated by startup_campaign.py (same construction as batch_backend.py):\n"
                "* load the STAGED OSDI binaries (job inputs/) and print their hashes.\n"
                "* set num_threads=1: the fleet runner starts one ngspice per corner in\n"
                "* parallel; with OpenMP each of them spawns a full thread team, and\n"
                "* transient runs then stall (150 s timeouts, 8 of 9 corners) instead of\n"
                "* taking ~2 s. See README.md \"Startup campaign\" for the evidence.\n"
                ".control\nset num_threads=1\n")
        for n in bb.OSDI_ORDER:
            f.write(f"pre_osdi inputs/{n}.osdi\n")
        f.write("shell sha256sum " + " ".join(f"inputs/{n}.osdi" for n in bb.OSDI_ORDER)
                + "\n.endc\n")
    groups = build_groups(points)
    index = []
    for n, g in enumerate(groups):
        first = g[0]
        gname = f"g{n:03d}_{first['mos']}_r{first['res']}_i{first['load_ma']}ma_c{first['cout_nf']}nf_e{first['esr_mohm']}mohm_t{first['tmax_ns']}ns"
        if len({p["vin"] for p in g}) == 1 and len({p["temp"] for p in g}) == 1:
            gname += f"_v{round(first['vin'] * 1000)}mv_T{first['temp']}"
        gd = os.path.join(sd, gname)
        os.makedirs(gd, exist_ok=True)
        design_rel = os.path.relpath(DESIGN, gd)
        preamble_rel = os.path.relpath(preamble, gd)
        with open(os.path.join(gd, "tb.spice"), "w") as f:
            f.write(f"* generated by startup_campaign.py ({stage}) from "
                    "testbench/tb_startup_cmos5l.spice.tmpl\n")
            f.write(render_body(first, design_rel, preamble_rel))
        secs = sorted({section(p) for p in g})
        vins = sorted({p["vin"] for p in g})
        with open(os.path.join(gd, "corners.lib"), "w") as f:
            f.write("* generated by startup_campaign.py: one section per (MOS, RES, CAP) bundle\n")
            for s in secs:
                m, r, c = s.split("__")
                f.write(f".lib {s}\n")
                for libfile, sec in (("cornerMOShv.lib", m), ("cornerRES.lib", r),
                                     ("cornerCAP.lib", c)):
                    f.write(f'.lib "{os.environ["PDK_ROOT"]}/{PDK}/libs.tech/ngspice/models/{libfile}" {sec}\n')
                f.write(f".endl {s}\n")
        temps = sorted({p["temp"] for p in g})
        req = {
            "netlist": "tb.spice",
            "backend": "batch",
            "batch": {"runner_version_check": "warn", "capacity_wait_s": 3600},
            "models": {"lib": "corners.lib"},
            "analysis": {"kind": "tran", "args": tran_args(first["tmax_ns"])},
            "measurements": [{"name": "liveness_vout",
                              "spice": ".meas tran liveness_vout FIND v(vout) AT=14m",
                              "unit": "V"}],
            "corners": {"process": secs, "temperature_c": temps,
                        "supply_v": {"vin": vins}},
            "options": {
                "timeout_s": CORNER_TIMEOUT_S,
                "keep_artifacts": True,
                "waveforms": True,
                "save_mode": "netlist",
                "stage_model_inputs": True,
                "osdi_preload": [os.path.join(osdi_dir, f"{x}.osdi") for x in bb.OSDI_ORDER],
            },
        }
        with open(os.path.join(gd, "request.json"), "w") as f:
            json.dump(req, f, indent=1)
            f.write("\n")
        index.append({"group": gname, "points": [dict(p, id=point_id(p)) for p in g]})
    with open(os.path.join(sd, "plan.json"), "w") as f:
        json.dump({"rid": rid, "stage": stage, "requested": len(points),
                   "tran_stop": T_STOP, "groups": index}, f, indent=1)
        f.write("\n")
    return len(points), len(groups)


# ---- binding points ----------------------------------------------------------
def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _f(row, k):
    v = row.get(k, "")
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def binding_points(rows):
    """Binding PVT/supply points from a grid record. A point is binding when
    it is the worst by (a) peak overshoot, (b) settle time (unsettled ranks
    worst), (c) downward excursion, (d) off-state VOUT, (e) re-enable overshoot, (f) pass-gate Vsg stress, or
    the first insufficient-data point (an all-fail grid makes "first
    failing" arbitrary, so it is not a rule). Ties go to the first row. Returns
    [(point dict, why)] de-duplicated by PVT/supply."""
    def pick(key, rev=True, none_worst=False, positive=False):
        best, bv = None, None
        for r in rows:
            v = _f(r, key)
            if v is None:
                if none_worst and r["verdict"] != "pass":
                    return r
                continue
            if bv is None or (v > bv if rev else v < bv):
                best, bv = r, v
        if positive and (bv is None or bv <= 0):
            return None   # an all-zero metric binds nothing
        return best
    sel = [("peak overshoot", pick("start_overshoot_v")),
           ("settle time", pick("start_settle_time_s", none_worst=True)),
           ("downward excursion", pick("start_max_down_excursion_v", positive=True)),
           ("off-state VOUT", pick("off_vout_max_v", positive=True)),
           ("re-enable overshoot", pick("reen_overshoot_v")),
           ("pass-gate Vsg stress", pick("start_max_vsg_pass_v"))]
    bad = [r for r in rows if r["verdict"] == "insufficient"]
    if bad:
        sel.append(("first insufficient-data point", bad[0]))
    out, seen = [], {}
    for why, r in sel:
        if r is None:
            continue
        key = (r["mos"], int(r["temp"]), r["res"], float(r["vin"]))
        if key in seen:
            seen[key]["why"].append(why)
            continue
        p = dict(NOMINAL, mos=r["mos"], temp=int(r["temp"]), res=r["res"], vin=float(r["vin"]))
        seen[key] = {"point": p, "why": [why]}
        out.append(seen[key])
    return out


# ---- submit ----------------------------------------------------------------
def submit_one(gd, retries=30, wait_s=120):
    """Submit one request to the batch fleet. A fleet-capacity refusal (the
    shared fleet's concurrent-instance cap) is retried on the BATCH backend
    after a wait; nothing is ever run locally."""
    import shutil
    art = os.path.join(gd, "artifacts")
    rc = 1
    for attempt in range(retries + 1):
        if os.path.isdir(art):
            shutil.rmtree(art)
        with open(os.path.join(gd, "report.json"), "w") as out, \
                open(os.path.join(gd, "klt-sim.stderr"), "w") as err:
            rc = subprocess.call(["klt", "sim", os.path.join(gd, "request.json"),
                                  "--backend", "batch", "-o", art, "--format", "json"],
                                 stdout=out, stderr=err)
        if rc in (0, 3):
            return rc
        text = (open(os.path.join(gd, "report.json")).read()
                + open(os.path.join(gd, "klt-sim.stderr")).read())
        if "BATCH_MAX_CONCURRENT_INSTANCES" in text or "no capacity" in text:
            with open(os.path.join(gd, "submit-attempts.log"), "a") as f:
                f.write(f"attempt {attempt}: exit {rc}: fleet capacity refusal; "
                        f"retrying in {wait_s}s\n")
            time.sleep(wait_s)
            continue
        return rc
    return rc


def cmd_submit(a):
    sd = stage_dir(a.rid, a.stage)
    plan = json.load(open(os.path.join(sd, "plan.json")))
    names = [g["group"] for g in plan["groups"]]
    if a.only:
        names = [n for n in names if n in a.only]
    rcs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(submit_one, os.path.join(sd, n)): n for n in names}
        for fu in concurrent.futures.as_completed(futs):
            n = futs[fu]
            rcs[n] = fu.result()
            print(f"startup_campaign: {n}: klt sim exit {rcs[n]}", file=sys.stderr, flush=True)
    with open(os.path.join(sd, "submit-exit.json"), "w") as f:
        json.dump(rcs, f, indent=1)
    bad = {n: rc for n, rc in rcs.items() if rc not in (0, 3)}
    if bad:
        print(f"startup_campaign: SUBMIT PROBLEMS (no local fallback): {bad}", file=sys.stderr)
        return 1
    return 0


# ---- collect ---------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def trace_from_raw(path):
    names, data, cplx, command = bb.read_raw(path)
    if cplx:
        raise CampaignError("complex rawfile for a transient run")
    def col(n):
        try:
            return bb.vec(data, n)
        except bb.BackendError:
            return None
    tr = {"t": data[names[0]], "vout": col("v(vout)"), "en": col("v(en)"),
          "vin": col("v(vin)"), "eaout": col("v(xtop.eaout)"), "ivin": col("i(vin)")}
    return tr, command


def write_trace(path, tr):
    cols = [k for k in ("t", "vout", "en", "vin", "eaout", "ivin") if tr.get(k) is not None]
    with gzip.GzipFile(path, "wb", mtime=0) as gz:
        gz.write((",".join(cols) + "\n").encode())
        for i in range(len(tr["t"])):
            gz.write((",".join(f"{tr[k][i]:.9g}" for k in cols) + "\n").encode())


def read_trace(path):
    with gzip.open(path, "rt") as f:
        rd = csv.DictReader(f)
        cols = {k: [] for k in rd.fieldnames}
        for r in rd:
            for k, v in r.items():
                cols[k].append(float(v))
    return cols


def _git_head(path):
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def cmd_collect(a):
    sd = stage_dir(a.rid, a.stage)
    plan = json.load(open(os.path.join(sd, "plan.json")))
    rec = os.path.join(HERE, "records")
    tdir = os.path.join(rec, f"{a.rid}-startup-{a.stage}.traces")
    os.makedirs(tdir, exist_ok=True)
    rows, jobs, engines, runners = [], [], set(), set()
    osdi_sha = {}
    for g in plan["groups"]:
        gd = os.path.join(sd, g["group"])
        rep, err = None, ""
        try:
            rep = json.load(open(os.path.join(gd, "report.json")))
        except (OSError, ValueError) as e:
            err = f"no klt report: {e}"
        by_corner = {}
        if rep:
            remote = (rep.get("environment") or {}).get("remote") or {}
            jobs.append({"group": g["group"], "job_id": remote.get("job_id"),
                         "runner_klt_version": remote.get("runner_klt_version"),
                         "instance_type": remote.get("instance_type"),
                         "lifecycle": remote.get("lifecycle")})
            runners.add(remote.get("runner_klt_version") or "unknown")
            for o in (rep.get("environment") or {}).get("osdi_preload") or []:
                osdi_sha[o.get("name")] = o.get("sha256")
            for c in rep.get("corners", []):
                sv = (c.get("supply_v") or {}).get("vin")
                by_corner[(c["process"], float(c["temperature_c"]),
                           None if sv is None else round(float(sv), 2))] = c
            if rep.get("error") or rep.get("status") == "error":
                err = f"klt report error: {json.dumps(rep.get('error'))[:300]}"
        for p in g["points"]:
            row = {"point": p["id"], "mos": p["mos"], "temp": p["temp"], "res": p["res"],
                   "vin": f"{p['vin']:.2f}", "load_ma": p["load_ma"], "cout_nf": p["cout_nf"],
                   "esr_mohm": p["esr_mohm"], "tmax_ns": p["tmax_ns"], "group": g["group"]}
            c = by_corner.get((section(p), float(p["temp"]), round(p["vin"], 2)))
            tr, why = None, err
            if c is None:
                why = why or "corner missing from klt report"
            else:
                row["corner_status"] = c.get("status")
                raw = (c.get("artifacts") or {}).get("raw")
                if raw and os.path.isfile(raw):
                    try:
                        tr, command = trace_from_raw(raw)
                        engines.add(command.split(",")[0].strip())
                        lg = (c.get("artifacts") or {}).get("log")
                        row["raw_sha256"] = sha256_file(raw)
                    except (CampaignError, bb.BackendError, OSError, ValueError) as e:
                        why = f"rawfile unreadable: {e}"
                else:
                    why = why or f"no rawfile (corner status {c.get('status')})"
            res = se.evaluate(tr)
            if tr is None and why:
                res["reasons"] = [why] + res["reasons"]
            if tr is not None and "trace" not in why:
                tp = os.path.join(tdir, p["id"] + ".csv.gz")
                write_trace(tp, tr)
                row["trace_file"] = os.path.relpath(tp, rec)
                row["trace_sha256"] = sha256_file(tp)
                row["samples"] = len(tr["t"])
            row.update({k: v for k, v in res.items() if k not in ("reasons", "en_edges")})
            row["reasons"] = " | ".join(res["reasons"])
            rows.append(row)
    # drop the trace dir if nothing was produced
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    out_csv = os.path.join(rec, f"{a.rid}-startup-{a.stage}.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval="")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    completed = sum(1 for r in rows if r.get("verdict") in ("pass", "fail"))
    meta = {"rid": a.rid, "stage": a.stage, "requested": plan["requested"],
            "rows": len(rows), "evaluated": completed,
            "insufficient": sum(1 for r in rows if r.get("verdict") == "insufficient"),
            "pass": sum(1 for r in rows if r.get("verdict") == "pass"),
            "fail": sum(1 for r in rows if r.get("verdict") == "fail"),
            "engines": sorted(engines), "runner_klt": sorted(runners),
            "client_klt": subprocess.run(["klt", "--version"], capture_output=True,
                                         text=True).stdout.strip(),
            "jobs": jobs,
            "osdi_sha256": dict(sorted(osdi_sha.items())),
            "pdk_pinned_commit": json.load(open(os.path.join(REPO, "sim", "pdk-cmos5l.json"))).get("pinned_commit"),
            "pdk_installed_commit": _git_head(os.path.join(os.environ.get("PDK_ROOT", ""), PDK)),
            "source_sha256": {os.path.relpath(p, REPO): sha256_file(p) for p in
                              (TEMPLATE, DESIGN, os.path.join(HERE, "startup_eval.py"),
                               os.path.join(HERE, "startup_campaign.py"))},
            "csv": os.path.relpath(out_csv, REPO)}
    mpath = os.path.join(rec, f"{a.rid}-startup-{a.stage}.manifest.json")
    with open(mpath, "w") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")
    write_md(a, meta, rows, plan)
    print(json.dumps({k: meta[k] for k in ("requested", "rows", "evaluated", "pass", "fail", "insufficient")}))
    return 0


METRICS = (("start_overshoot_v", "start overshoot above 1.8 V [V]", True),
           ("start_peak_vout_v", "start peak VOUT [V]", True),
           ("start_settle_time_s", "start settle time [s]", True),
           ("start_rise_10_90_s", "start 10-90 % rise time [s]", True),
           ("start_max_down_excursion_v", "start max downward excursion [V]", True),
           ("reen_overshoot_v", "re-enable overshoot [V]", True),
           ("reen_max_down_excursion_v", "re-enable max downward excursion [V]", True),
           ("off_vout_max_v", "off-state max VOUT [V]", True),
           ("off_supply_current_a", "off-state supply current [A]", True),
           ("start_max_vsg_pass_v", "start max Vsg(Mpass) [V]", True),
           ("start_max_vds_pass_v", "start max Vds(Mpass) [V]", True),
           ("start_peak_supply_current_a", "start peak supply current [A]", True))


def _num(r, k):
    try:
        x = float(r.get(k, ""))
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def write_md(a, meta, rows, plan):
    rec = os.path.join(HERE, "records")
    path = os.path.join(rec, f"{a.rid}-startup-{a.stage}.md")
    L = [f"# Startup campaign record `{a.rid}` stage `{a.stage}` (issue #69)", "",
         "SCHEMATIC-LEVEL evidence for the EN-bearing SG13CMOS5L core. Proposed "
         "methodology (README.md \"Startup campaign (issue #69)\"); DR-0007 row 9 "
         "stays **Open**. Verdicts come from `startup_eval.py`; a missing or "
         "non-converged trace is `insufficient`, never a pass.", "",
         "## Coverage", "",
         f"- Requested points: **{meta['requested']}**",
         f"- Points with a result row: {meta['rows']}",
         f"- Evaluated (data sufficient): **{meta['evaluated']}**",
         f"- Insufficient / missing data: **{meta['insufficient']}**",
         f"- Verdicts: pass {meta['pass']}, fail {meta['fail']}, insufficient {meta['insufficient']}",
         f"- Complete: **{'yes' if meta['evaluated'] == meta['requested'] else 'NO -- INCOMPLETE'}**",
         f"- Engine: {', '.join(meta['engines']) or 'unknown'}; runner klt {', '.join(meta['runner_klt']) or 'unknown'}; client {meta['client_klt']}",
         f"- klt sim requests: {len(plan['groups'])}; fleet jobs recorded: {len([j for j in meta['jobs'] if j['job_id']])}",
         f"- PDK pin (sim/pdk-cmos5l.json) {meta['pdk_pinned_commit'][:12]}; installed checkout {meta['pdk_installed_commit'][:12]}"
         + (" (match)" if meta['pdk_pinned_commit'] == meta['pdk_installed_commit'] else " (**MISMATCH**)"),
         "- OSDI binaries (sha256): " + ", ".join(f"{k} {v[:12]}" for k, v in meta["osdi_sha256"].items()),
         "- Source hashes: " + ", ".join(f"`{k}` {v[:12]}" for k, v in meta["source_sha256"].items()), ""]
    L += ["## Extrema over the evaluated points", "",
          "| metric | min | at | max | at |", "|---|---|---|---|---|"]
    for k, label, _ in METRICS:
        vals = [(_num(r, k), r["point"]) for r in rows if _num(r, k) is not None]
        if not vals:
            L.append(f"| {label} | n/a | | n/a | |")
            continue
        lo, hi = min(vals), max(vals)
        L.append(f"| {label} | {lo[0]:.6g} | `{lo[1]}` | {hi[0]:.6g} | `{hi[1]}` |")
    L.append("")
    from collections import Counter
    reasons = Counter()
    for r in rows:
        for x in (r.get("reasons") or "").split(" | "):
            if x:
                reasons[x.split(" ")[0] + " " + ("overshoot" if "above" in x else "excursion" if "excursion" in x else "settle" if "settles" in x or "settled" in x else "off-state" if "off-state" in x else "other")] += 1
    L += ["## Failure reasons (count of points)", ""]
    L += [f"- {k}: {v}" for k, v in sorted(reasons.items())] or ["- none"]
    L.append("")
    bad = [r for r in rows if r.get("verdict") == "insufficient"]
    if bad:
        L += ["## Insufficient / missing points", ""]
        L += [f"- `{r['point']}`: {r.get('reasons', '')[:200]}" for r in bad]
        L.append("")
    if a.stage == "halfstep":
        gpath = os.path.join(rec, f"{a.rid}-startup-grid.csv")
        if os.path.exists(gpath):
            g = {r["point"].replace("_t1000ns", ""): r for r in read_csv(gpath)}
            L += ["## Timestep sensitivity (1 us cap vs 0.5 us cap)", "",
                  "| point | metric | 1 us | 0.5 us | delta |", "|---|---|---|---|---|"]
            for r in rows:
                base = g.get(r["point"].replace("_t500ns", ""))
                if base is None:
                    continue
                for k, label, _ in METRICS[:8]:
                    x, y = _num(base, k), _num(r, k)
                    if x is None or y is None:
                        continue
                    L.append(f"| `{r['point'].replace('_t500ns', '')}` | {label} | {x:.6g} | {y:.6g} | {y - x:+.3g} |")
                L.append(f"| `{r['point'].replace('_t500ns', '')}` | verdict | {base['verdict']} | {r['verdict']} | |")
            L.append("")
    L += ["## Points", "", "Per-point metrics, trace file names and trace sha256 are in "
          f"`{os.path.basename(meta['csv'])}`; reduced traces in `{a.rid}-startup-{a.stage}.traces/` "
          "(`t,vout,en,vin,eaout,ivin`, gzip). Rawfile sha256 per point is the `raw_sha256` "
          "column (rawfiles themselves, about 2 MB each, are not committed).", ""]
    with open(path, "w") as f:
        f.write("\n".join(L))


def cmd_plan(a):
    if a.stage == "nominal":
        pts = [dict(NOMINAL)]
    elif a.stage == "grid":
        pts = grid_points()
    elif a.stage in ("ext", "halfstep"):
        if not a.binding:
            raise CampaignError("--binding <grid csv> required")
        b = [x["point"] for x in binding_points(read_csv(a.binding))]
        pts = ext_points(b) if a.stage == "ext" else halfstep_points(b)
    else:
        raise CampaignError(a.stage)
    n, g = write_requests(a.rid, a.stage, pts)
    print(f"startup_campaign: stage {a.stage}: {n} points in {g} klt sim requests under "
          f"{os.path.relpath(stage_dir(a.rid, a.stage), REPO)}")
    return 0


def cmd_binding(a):
    for b in binding_points(read_csv(a.grid_csv)):
        p = b["point"]
        print(point_id(p), "|", "; ".join(b["why"]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "submit", "collect"):
        s = sub.add_parser(name)
        s.add_argument("--stage", required=True, choices=("nominal", "grid", "ext", "halfstep"))
        s.add_argument("--rid", required=True)
        if name == "plan":
            s.add_argument("--binding")
        if name == "submit":
            s.add_argument("--concurrency", type=int, default=2)
            s.add_argument("--only", nargs="*")
    s = sub.add_parser("binding")
    s.add_argument("--grid-csv", required=True)
    a = ap.parse_args()
    try:
        return {"plan": cmd_plan, "submit": cmd_submit, "collect": cmd_collect,
                "binding": cmd_binding}[a.cmd](a)
    except (CampaignError, KeyError) as e:
        print(f"startup_campaign: ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
