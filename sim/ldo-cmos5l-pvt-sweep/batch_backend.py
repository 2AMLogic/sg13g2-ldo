#!/usr/bin/env python3
"""Batch-fleet backend for run_sweep.sh (issue #67 follow-up, PR #87).

`run_sweep.sh --batch` uses this script instead of running `ngspice -b`
once per point on the local host. Dispatch hosts must not run SPICE grids
locally. This script sends the SAME per-point decks run_sweep.sh generates
to the EDA batch fleet as `klt sim --backend batch` requests. It then writes
back exactly the files the local loop would have written:

    corners/<id>/<point_id>.log           the runner's ngspice log
    corners/<id>/<point_id>_dc.csv        dcsweep points, wrdata layout
    corners/<id>/<point_id>_ac.csv        loopgain / psrr points, wrdata layout

The record post-processing in run_sweep.sh, dc_metrics.py and
item5_evidence.py then reads these files unchanged.

How a generated deck becomes a klt sim request (and why each step is safe):

  * `.lib <file> <section>` cards -> one section of a generated
    `corners.lib` (`models.lib`, staged with `options.stage_model_inputs`).
    Every MOS/RES/CAP section the deck named is loaded, in the same order.
  * `.options temp=T tnom=27` -> `.options tnom=27` in the body, plus T on
    klt's temperature axis (klt emits `.temp T`).
  * The deck's `.control` block is parsed, not forwarded. Its `pre_osdi`
    lines become a preamble that loads the STAGED binaries
    (`inputs/<name>.osdi`, in the same order). The runner image's klt 0.5.0
    ignores `options.osdi_preload`. It does run a body `.control` block, and
    the staged files land in `inputs/` under the job's working directory.
    Each corner log prints the binaries' sha256. The one analysis line
    becomes klt's `analysis`. Its `wrdata` vectors are rebuilt from the
    corner's ASCII rawfile (`options.waveforms`). `let` definitions are
    accepted only when they match the two known benches' text exactly;
    anything else is a hard error, so a template edit cannot be silently
    mistranslated.
  * Groups: points whose body text is identical (same bench, same design
    netlist, same substitutions) share one request. When their (section,
    temp) pairs are not a full cross product, the missing pairs go into the
    request's `exclude` list (issue #64), so the request still runs exactly
    the member points.
  * `--variant-lines REGEX` (issue #64 DoE): body lines matching REGEX (the
    Iload/Cout/Resr lines) are moved verbatim into each point's own
    `corners.lib` section, after its model cards. Decks that differ only in
    those lines then share one body and one request, one corner per point.
    Element order does not matter to SPICE, so the circuit is unchanged.
    Cross-checked byte-for-byte against one-request-per-deck runs, see
    backend-validation/20261010-variant-lines/.

Usage (normally invoked by run_sweep.sh --batch):

    batch_backend.py run --queue Q --corners-out DIR --work DIR --osdi-dir DIR

Q holds one `<point_id>\\t<netlist>` line per point. On success it writes
`DIR/_batch/backend.env` (shell-sourceable: ngspice version, job ids) and
`DIR/_batch/<group>/` (request, body, corner lib, klt report, per-corner
generated decks), and exits 0. A failed submission is reported and exits
non-zero. It never falls back to running ngspice locally.
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys

OSDI_ORDER = ["psp103", "psp103_nqs", "mosvar", "r3_cmc", "cap_cmomi", "cap_cmomf"]

# The only `let` blocks run_sweep.sh's templates contain. Matched verbatim.
KNOWN_LETS = {
    "loopgain": [
        "let loopgain = -v(fb)/v(fbamp)",
        "let loopgain_db = db(loopgain)",
        "let loopgain_deg = ph(loopgain)*180/3.14159265358979",
    ],
    "psrr": ["let psrr_db = -db(v(vout)/v(vin))"],
}
PI_TEMPLATE = 3.14159265358979  # the literal the loopgain template uses

LIVENESS_MEAS = {
    "dc": ".meas dc liveness_vout FIND v(vout) AT=3.3",
    "ac": ".meas ac liveness_vout FIND vm(vout) AT=1",
}


class BackendError(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# deck -> (body, sections, temp, analysis, outputs)
# --------------------------------------------------------------------------- #

def parse_deck(path, variant_re=None):
    """variant_re (issue #64): body lines matching it are taken out of the
    body into p["variant"]; write_group puts them in the point's own
    corners.lib section, so decks that differ only in those lines share
    one request (one corner per point)."""
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    body, sections, control, variant = [], [], [], []
    temp = None
    in_control = False
    for ln in lines:
        s = ln.strip()
        low = s.lower()
        if in_control:
            if low == ".endc":
                in_control = False
            else:
                control.append(s)
            continue
        if low == ".control":
            in_control = True
            continue
        if low == ".end" or s.startswith("*"):
            # Comment lines carry per-point placeholders (corner, temp) and
            # do not affect the simulation. Dropping them lets points that
            # differ only in corner/temperature share one request.
            continue
        m = re.match(r'^\.lib\s+"([^"]+)"\s+(\S+)\s*$', s)
        if m:
            sections.append((m.group(1), m.group(2)))
            continue
        m = re.match(r"^\.options\s+temp=(\S+)\s+tnom=27\s*$", s)
        if m:
            if temp is not None:
                raise BackendError(f"{path}: more than one .options temp line")
            temp = float(m.group(1))
            body.append(".options tnom=27")
            continue
        if low.startswith(".lib") or low.startswith(".temp") or "temp=" in low and low.startswith(".option"):
            raise BackendError(f"{path}: unrecognised model/temperature card: {s}")
        if variant_re is not None and re.match(variant_re, s):
            variant.append(s)
            continue
        body.append(ln)
    if temp is None or not sections:
        raise BackendError(f"{path}: no .options temp / .lib cards found")

    osdi, analysis, lets, wrdata = [], None, [], None
    for s in control:
        if not s or s.startswith("*"):
            continue
        if s.startswith("pre_osdi "):
            osdi.append(os.path.basename(s.split(None, 1)[1]))
        elif re.match(r"^(dc|ac)\s", s):
            if analysis is not None:
                raise BackendError(f"{path}: more than one analysis in .control")
            kind, args = s.split(None, 1)
            analysis = (kind, args)
        elif s.startswith("let "):
            lets.append(s)
        elif s.startswith("wrdata "):
            parts = s.split()
            wrdata = parts[2:]
        elif s == "op" or s.startswith('echo "LOOPGAIN_VOUT_OP'):
            # informational operating-point echo in the loopgain template;
            # nothing downstream reads it.
            continue
        else:
            raise BackendError(f"{path}: unsupported .control line: {s}")
    if analysis is None or wrdata is None:
        raise BackendError(f"{path}: .control has no analysis or no wrdata")
    expected_osdi = [f"{n}.osdi" for n in OSDI_ORDER]
    if osdi != expected_osdi:
        raise BackendError(f"{path}: pre_osdi set {osdi} != expected {expected_osdi}")
    if variant_re is not None and not variant:
        raise BackendError(f"{path}: no line matches --variant-lines {variant_re!r}")
    return {"body": "\n".join(body) + "\n", "sections": sections, "temp": temp,
            "analysis": analysis, "lets": lets, "wrdata": wrdata,
            "variant": variant}


def bench_of(point_id):
    for b in ("dcsweep", "loopgain", "psrr"):
        if point_id.startswith(b + "_"):
            return b
    raise BackendError(f"cannot tell the bench of point {point_id}")


# --------------------------------------------------------------------------- #
# rawfile -> wrdata
# --------------------------------------------------------------------------- #

def read_raw(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    i = 0
    flags, nvars, npts, names, command = "", None, None, [], ""
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Flags:"):
            flags = ln.split(":", 1)[1].strip()
        elif ln.startswith("Command:"):
            command = ln.split(":", 1)[1].strip()
        elif ln.startswith("No. Variables:"):
            nvars = int(ln.split(":", 1)[1])
        elif ln.startswith("No. Points:"):
            npts = int(ln.split(":", 1)[1])
        elif ln.startswith("Variables:"):
            for k in range(nvars):
                parts = lines[i + 1 + k].split()
                names.append(parts[1].lower())
            i += nvars
        elif ln.startswith("Values:"):
            i += 1
            break
        i += 1
    cplx = "complex" in flags
    tokens = " ".join(lines[i:]).split()
    data = {n: [] for n in names}
    pos = 0
    for p in range(npts):
        if int(tokens[pos]) != p:
            raise BackendError(f"{path}: rawfile point index {tokens[pos]} != {p}")
        pos += 1
        for n in names:
            t = tokens[pos]
            pos += 1
            if cplx:
                re_s, im_s = t.split(",")
                data[n].append(complex(float(re_s), float(im_s)))
            else:
                data[n].append(float(t))
    return names, data, cplx, command


def vec(data, name):
    name = name.lower()
    if name in data:
        return data[name]
    m = re.match(r"^i\((\w+)\)$", name)
    if m and f"{m.group(1)}#branch" in data:
        return data[f"{m.group(1)}#branch"]
    m = re.match(r"^v\((\w+)\)$", name)
    if m and m.group(1) in data:
        return data[m.group(1)]
    raise BackendError(f"vector {name} not in rawfile (have {sorted(data)[:12]}...)")


def db(z):
    return 20.0 * math.log10(abs(z))


def wrdata_rows(bench, parsed, names, data, cplx):
    scale = data[names[0]]
    scale = [x.real if isinstance(x, complex) else x for x in scale]
    want = parsed["wrdata"]
    if bench == "dcsweep":
        if cplx:
            raise BackendError("dcsweep rawfile is complex")
        cols = [vec(data, w) for w in want]
    elif bench == "loopgain":
        if cplx is False:
            raise BackendError("loopgain rawfile is not complex")
        if parsed["lets"] != KNOWN_LETS["loopgain"] or want != ["loopgain_db", "loopgain_deg"]:
            raise BackendError(f"loopgain .control differs from the known template: {parsed['lets']} {want}")
        fb, fbamp = vec(data, "v(fb)"), vec(data, "v(fbamp)")
        lg = [-a / b for a, b in zip(fb, fbamp)]
        cols = [[db(z) for z in lg],
                [math.atan2(z.imag, z.real) * 180 / PI_TEMPLATE for z in lg]]
    elif bench == "psrr":
        if parsed["lets"] != KNOWN_LETS["psrr"] or want != ["psrr_db"]:
            raise BackendError(f"psrr .control differs from the known template: {parsed['lets']} {want}")
        vo, vi = vec(data, "v(vout)"), vec(data, "v(vin)")
        cols = [[-db(a / b) for a, b in zip(vo, vi)]]
    else:
        raise BackendError(bench)
    out = []
    for r in range(len(scale)):
        vals = []
        for c in cols:
            v = c[r]
            if isinstance(v, complex):
                raise BackendError("complex value in a wrdata column")
            vals += [scale[r], v]
        out.append("".join(f"{v: .8e} " for v in vals) + "\n")
    return out


# --------------------------------------------------------------------------- #
# grouping and submission
# --------------------------------------------------------------------------- #

def num(t):
    return int(t) if float(t).is_integer() else t


def section_name(sections):
    return "__".join(sec for _, sec in sections)


def corner_name(p):
    """klt process name of a point: its model sections, plus a hash of its
    variant lines when it has any (so the name is unique per variant)."""
    name = section_name(p["sections"])
    if p.get("variant"):
        h = hashlib.sha256("\n".join(p["variant"]).encode()).hexdigest()[:12]
        name += f"__v{h}"
    return name


def plan_groups(points):
    """points: list of (point_id, parsed). Returns list of groups."""
    by_key = {}
    for pid, p in points:
        key = (bench_of(pid), hashlib.sha256(p["body"].encode()).hexdigest(),
               p["analysis"], tuple(p["wrdata"]), tuple(p["lets"]))
        by_key.setdefault(key, []).append((pid, p))
    groups = []
    for key, all_members in by_key.items():
        # Points that are deliberately the same simulation (the ressens
        # points repeat the main grid's tt/27C slice as a cross-check) go
        # into separate layers, so each one is still simulated on its own.
        layers = []
        for m in all_members:
            pair = (corner_name(m[1]), m[1]["temp"])
            for layer in layers:
                if pair not in layer:
                    layer[pair] = m
                    break
            else:
                layers.append({pair: m})
        for layer in layers:
            members = list(layer.values())
            procs = sorted({a for a, _ in layer})
            temps = sorted({b for _, b in layer})
            # A sparse (section, temp) set (the issue #64 DoE: four
            # corners at three temperatures) stays ONE request: the pairs
            # nobody asked for go into klt's `exclude` list, so the runner
            # simulates exactly the member pairs and nothing else.
            # (`exclude` has been in the request schema since klt 0.5.0,
            # the runner image's version.) A full cross product has none.
            exclude = sorted((a, b) for a in procs for b in temps
                             if (a, b) not in layer)
            groups.append({"bench": key[0], "members": members,
                           "exclude": exclude})
    for n, g in enumerate(groups):
        first = g["members"][0][0]
        g["name"] = f"g{n:02d}_{first}"
    return groups


def write_group(g, work, osdi_dir, preamble_path):
    gdir = os.path.join(work, g["name"])
    os.makedirs(gdir, exist_ok=True)
    first = g["members"][0][1]
    body = (f'* generated by sim/ldo-cmos5l-pvt-sweep/batch_backend.py from {g["members"][0][0]}\n'
            f'.include "{preamble_path}"\n' + first["body"])
    with open(os.path.join(gdir, "tb.spice"), "w") as f:
        f.write(body)
    secs = {}
    for _, p in g["members"]:
        secs[corner_name(p)] = (p["sections"], p.get("variant") or [])
    with open(os.path.join(gdir, "corners.lib"), "w") as f:
        f.write("* generated by batch_backend.py: one section per (MOS, RES, CAP) corner bundle\n")
        if any(v for _, v in secs.values()):
            f.write("* plus, after the model cards, the deck lines that differ per point\n"
                    "* (--variant-lines), moved here verbatim from the generated deck\n")
        for name, (cards, variant) in sorted(secs.items()):
            f.write(f".lib {name}\n")
            for libfile, sec in cards:
                f.write(f'.lib "{libfile}" {sec}\n')
            for ln in variant:
                f.write(ln + "\n")
            f.write(f".endl {name}\n")
    kind, args = first["analysis"]
    temps = sorted({p["temp"] for _, p in g["members"]})
    req = {
        "netlist": "tb.spice",
        "backend": "batch",
        "batch": {"runner_version_check": "warn", "capacity_wait_s": 3600},
        "models": {"lib": "corners.lib"},
        "analysis": {"kind": kind, "args": args},
        "measurements": [{"name": "liveness_vout", "spice": LIVENESS_MEAS[kind], "unit": "V"}],
        "corners": {"process": sorted(secs),
                    "temperature_c": [num(t) for t in temps]},
        "options": {
            "timeout_s": 1800,
            "keep_artifacts": True,
            "waveforms": True,
            "stage_model_inputs": True,
            # Staged only: the runner's klt 0.5.0 does not apply this
            # option, and the preamble's pre_osdi lines load the staged
            # copies. The worker checks below fail if a runner ever applies
            # it as well, which would load each binary twice.
            "osdi_preload": [os.path.join(osdi_dir, f"{n}.osdi") for n in OSDI_ORDER],
        },
    }
    if g.get("exclude"):
        req["exclude"] = [{"process": a, "temperature_c": num(b)} for a, b in g["exclude"]]
    with open(os.path.join(gdir, "request.json"), "w") as f:
        json.dump(req, f, indent=1)
        f.write("\n")
    return gdir


def submit(gdir):
    art = os.path.join(gdir, "artifacts")
    if os.path.isdir(art):
        shutil.rmtree(art)
    with open(os.path.join(gdir, "report.json"), "w") as out, \
            open(os.path.join(gdir, "klt-sim.stderr"), "w") as err:
        rc = subprocess.call(["klt", "sim", os.path.join(gdir, "request.json"),
                              "--backend", "batch", "-o", art, "--format", "json"],
                             stdout=out, stderr=err)
    return rc


def collect(g, gdir, corners_out, record_meta):
    rep = json.load(open(os.path.join(gdir, "report.json")))
    remote = rep.get("environment", {}).get("remote") or {}
    record_meta["jobs"].append({"group": g["name"], "job_id": remote.get("job_id"),
                                "runner_klt_version": remote.get("runner_klt_version"),
                                "instance_type": remote.get("instance_type"),
                                "lifecycle": remote.get("lifecycle"),
                                "corners": len(rep.get("corners", [])),
                                "requested": len(g["members"]),
                                "points": [pid for pid, _ in g["members"]]})
    if len(rep.get("corners", [])) != len(g["members"]):
        print(f"batch_backend: WARNING: {g['name']}: report has {len(rep.get('corners', []))} "
              f"corners, {len(g['members'])} requested (was `exclude` honoured?)", file=sys.stderr)
    by_corner = {}
    for c in rep.get("corners", []):
        by_corner[(c["process"], float(c["temperature_c"]))] = c
    problems = []
    for pid, p in g["members"]:
        key = (corner_name(p), p["temp"])
        c = by_corner.get(key)
        log_out = os.path.join(corners_out, f"{pid}.log")
        csv_out = os.path.join(corners_out, f"{pid}_{'dc' if g['bench'] == 'dcsweep' else 'ac'}.csv")
        if c is None:
            problems.append(f"{pid}: no corner {key} in {g['name']}/report.json")
            with open(log_out, "w") as f:
                f.write(f"batch_backend: fatal error: corner {key} missing from the klt report\n")
            continue
        arts = c.get("artifacts") or {}
        if arts.get("log") and os.path.isfile(arts["log"]):
            shutil.copyfile(arts["log"], log_out)
        else:
            with open(log_out, "w") as f:
                f.write(f"batch_backend: fatal error: no ngspice log returned (corner status {c.get('status')})\n")
        deck = arts.get("deck")
        if deck and os.path.isfile(deck):
            deck_text = open(deck, encoding="utf-8").read()
            if "pre_osdi" in deck_text:
                raise BackendError(f"{deck}: runner applied osdi_preload itself; the preamble would "
                                   "load every OSDI binary twice -- update batch_backend.py")
            shutil.copyfile(deck, os.path.join(gdir, f"{pid}.corner.cir"))
        raw = arts.get("raw")
        if not raw or not os.path.isfile(raw):
            problems.append(f"{pid}: no rawfile (corner status {c.get('status')})")
            continue
        names, data, cplx, command = read_raw(raw)
        record_meta["engines"].add(command.split(",")[0].strip())
        with open(csv_out, "w") as f:
            f.writelines(wrdata_rows(g["bench"], p, names, data, cplx))
    return problems


def cmd_run(a):
    corners_out = os.path.abspath(a.corners_out)
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    os.makedirs(corners_out, exist_ok=True)
    for n in OSDI_ORDER:
        if not os.path.isfile(os.path.join(a.osdi_dir, f"{n}.osdi")):
            raise BackendError(f"OSDI binary to stage is missing: {a.osdi_dir}/{n}.osdi")
    preamble = os.path.join(work, "osdi-preamble.cir")
    with open(preamble, "w") as f:
        f.write("* generated by batch_backend.py: load the STAGED OSDI binaries (job inputs/),\n"
                "* in the templates' pre_osdi order, and print the hashes of what loaded.\n"
                ".control\n")
        for n in OSDI_ORDER:
            f.write(f"pre_osdi inputs/{n}.osdi\n")
        f.write("shell sha256sum " + " ".join(f"inputs/{n}.osdi" for n in OSDI_ORDER) + "\n.endc\n")

    points = []
    with open(a.queue) as f:
        for ln in f:
            if not ln.strip():
                continue
            pid, path = ln.rstrip("\n").split("\t")
            points.append((pid, parse_deck(path, a.variant_lines)))
    groups = plan_groups(points)
    print(f"batch_backend: {len(points)} points in {len(groups)} klt sim requests", file=sys.stderr)
    if a.plan_only:
        for g in groups:
            procs = sorted({corner_name(p) for _, p in g["members"]})
            temps = sorted({p["temp"] for _, p in g["members"]})
            print(f"  {g['name']}: {len(g['members'])} points, {len(procs)} sections x temps {temps}"
                  f", {len(g.get('exclude') or [])} excluded")
        return 0
    gdirs = {g["name"]: write_group(g, work, a.osdi_dir, preamble) for g in groups}

    with open(os.path.join(work, "points.tsv"), "w") as f:
        f.write("point_id\tgroup\tprocess\ttemperature_c\n")
        for g in groups:
            for pid, p in g["members"]:
                f.write(f"{pid}\t{g['name']}\t{corner_name(p)}\t{num(p['temp'])}\n")

    rcs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.submit_concurrency) as ex:
        futs = {ex.submit(submit, gdirs[g["name"]]): g["name"] for g in groups}
        for fu in concurrent.futures.as_completed(futs):
            name = futs[fu]
            rcs[name] = fu.result()
            print(f"batch_backend: {name}: klt sim exit {rcs[name]}", file=sys.stderr)

    meta = {"jobs": [], "engines": set()}
    problems = []
    for g in groups:
        rc = rcs[g["name"]]
        if rc not in (0, 3):
            err = open(os.path.join(gdirs[g["name"]], "klt-sim.stderr")).read()
            rep = open(os.path.join(gdirs[g["name"]], "report.json")).read()
            problems.append(f"{g['name']}: klt sim exit {rc}\n{err[-2000:]}\n{rep[-2000:]}")
            continue
        problems += collect(g, gdirs[g["name"]], corners_out, meta)

    # Provenance copy next to the per-point logs (no rawfiles: they are
    # ~1 MB per corner and fully reduced into the *_dc/_ac.csv files).
    prov = os.path.join(corners_out, "_batch")
    os.makedirs(prov, exist_ok=True)
    shutil.copyfile(preamble, os.path.join(prov, "osdi-preamble.cir"))
    shutil.copyfile(os.path.join(work, "points.tsv"), os.path.join(prov, "points.tsv"))
    for g in groups:
        src, dst = gdirs[g["name"]], os.path.join(prov, g["name"])
        os.makedirs(dst, exist_ok=True)
        for fn in sorted(os.listdir(src)):
            if fn in ("request.json", "tb.spice", "corners.lib", "report.json") or fn.endswith(".corner.cir"):
                shutil.copyfile(os.path.join(src, fn), os.path.join(dst, fn))
    staged = {n: sha256(os.path.join(a.osdi_dir, f"{n}.osdi")) for n in OSDI_ORDER}
    engines = sorted(meta["engines"])
    runner = sorted({j["runner_klt_version"] or "unknown" for j in meta["jobs"]})
    with open(os.path.join(prov, "backend.json"), "w") as f:
        json.dump({"backend": "batch", "client_klt": subprocess.run(
            ["klt", "--version"], capture_output=True, text=True).stdout.strip(),
            "runner_klt": runner, "engines": engines, "staged_osdi_sha256": staged,
            "jobs": sorted(meta["jobs"], key=lambda j: j["group"])}, f, indent=1)
        f.write("\n")
    with open(os.path.join(prov, "backend.env"), "w") as f:
        f.write(f"BATCH_NGSPICE_VERSION='{' / '.join(engines) or 'unknown'}'\n")
        f.write(f"BATCH_RUNNER_KLT='{' / '.join(runner)}'\n")
        f.write(f"BATCH_JOB_COUNT={len(meta['jobs'])}\n")
    if problems:
        print("batch_backend: PROBLEMS:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--queue", required=True)
    r.add_argument("--corners-out", required=True)
    r.add_argument("--work", required=True)
    r.add_argument("--osdi-dir", required=True)
    r.add_argument("--submit-concurrency", type=int, default=2)
    r.add_argument("--variant-lines", metavar="REGEX",
                   help="move body lines matching REGEX into each point's own "
                        "corners.lib section, so decks differing only in them share "
                        "one request (issue #64 DoE: the Iload/Cout/Resr lines)")
    r.add_argument("--plan-only", action="store_true",
                   help="parse and group the queue, print the plan, submit nothing")
    a = ap.parse_args()
    try:
        return cmd_run(a)
    except BackendError as e:
        print(f"batch_backend: ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
