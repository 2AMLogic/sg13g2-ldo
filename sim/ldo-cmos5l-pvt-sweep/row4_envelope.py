#!/usr/bin/env python3
"""Graded `klt sim` corner-matrix envelope for the RATIFIED row 4 (issue #55).

T1 item 5 asks for a corner-matrix run graded against a ratified spec row.
Everything this directory had before was a *measurement* run: `run_sweep.sh
--batch` and `dropout_campaign.py` do submit real `klt sim` requests, but
those requests declare no `limits`, so the pass/fail verdict was computed by
this repo's own Python afterwards.  `klt signoff` cannot grade that, and
hand-wrapping a reduced CSV into a sim-shaped envelope would be a synthesized
success.  This script closes the gap the only honest way: it declares the
ratified row-4 requirement as `limits` **inside the request**, so the
per-corner and whole-matrix verdict in the emitted report is `klt sim`'s own.

What is graded (DR-0007 row 4, "Dropout @ 50 mA < 300 mV worst corner"),
using the LEGACY measurement definition that row was ratified with
(`dc_metrics.dropout_v_50ma`: the lowest Vin whose VOUT is still within 1 %
of the fixed 1.8 V target, minus that 1.8 V target):

  vout_at_dropout_limit_v  .meas dc FIND v(vout) AT=2.100   limits min 1.782
      The requirement read literally: with VIN at 1.800 + 0.300 V the output
      is still within 1 % of target.  No abscissa interpolation.
  vin_1pct_loss_v          .meas dc WHEN v(vout)=1.782 RISE=1  limits max 2.1
      The measured dropout edge itself.  dropout = value - 1.800 V.  Equal to
      the requirement above by construction, measured from the other axis, so
      a `.meas` quirk in one cannot pass unnoticed in both.
  vout_nominal_v           .meas dc FIND v(vout) AT=3.300     (NO limits)
      Liveness / the regulated output the legacy definition is referenced
      against.  Deliberately UNGRADED: row 2 (output accuracy) is Open under
      DR-0007 and must not acquire a gate here.

Both thresholds are literal numbers because `klt sim` requires that: a `.meas
WHEN` threshold cannot name another `.meas` result, so DR-0012's
own-regulated-output reference (0.99 x VOUT(Vin=3.30 V), per corner) is NOT
expressible in a request.  That is a real tool gap, disclosed in
signoff/README.md, and it is why this envelope grades the legacy ratified
quantity rather than DR-0012's (still PROPOSED) one.

Scope: SG13CMOS5L schematic-level only.  Nothing here evidences an Open row
or the SG13G2 branch (DR-0018).

No .control block: the fleet runner applies `options.osdi_preload` itself
(observed 2026-11-14, runner klt 0.9.0 / ngspice-47 per the report's
`environment.remote`; job klt-sim-b7598358f812 is the run that proved it), so a
deck-side `.control pre_osdi` block loads each binary a second time and every
corner comes back `osdi_load_failed` -- with plausible-looking measurement
values beside it, which is why summarise_report() refuses to call a record
definitive while any corner carries an error-severity diagnostic.

    row4_envelope.py submit                 # mint a new record, run it on the
                                            # EDA batch fleet, write the envelope
    row4_envelope.py submit --probe         # the same, 2 corners, for a capacity
                                            # / toolchain probe (never cited)
    row4_envelope.py submit --dry-run       # build the request dir and validate it
    row4_envelope.py check                  # offline, stdlib-only (CI): every
                                            # committed record reproduces and
                                            # self-verifies
    row4_envelope.py summarise <record-id>  # rewrite that record's summary files

Append-only: `submit` mints a NEW timestamped record id and refuses to touch
an existing one.  SPICE never runs locally here -- this is a 45-point grid and
dispatch hosts submit grids to the fleet (CLAUDE.md host rules).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.join(HERE, "row4-envelope")

TEMPLATE = "sim/ldo-cmos5l-pvt-sweep/testbench/tb_row4_envelope_cmos5l.spice.tmpl"
DESIGN_NETLIST = "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
PDK = "ihp-sg13cmos5l"
PDK_PIN = "sim/pdk-cmos5l.json"

MOS = ["tt", "ff", "ss", "sf", "fs"]
RES = ["typ", "bcs", "wcs"]
CAP = "typ"
TEMPS = [-40, 27, 125]
N_EXPECTED = len(MOS) * len(RES) * len(TEMPS)        # 45

# DR-0007 row 4, verbatim: "Dropout @ 50 mA  < 300 mV worst corner".
VOUT_TARGET_V = 1.800
LOSS_FRACTION = 0.01
TARGET_DROPOUT_V = 0.300
LOAD_A = 0.050
V_THR_V = 1.782                 # (1 - LOSS_FRACTION) * VOUT_TARGET_V
VIN_LIMIT_V = 2.100             # VOUT_TARGET_V + TARGET_DROPOUT_V
VIN_AXIS = "Vin 1.70 3.63 0.005"
VIN_REF_V = 3.300

# The spec-row id this envelope's graded measurements are tagged with
# (`measurements[].spec_row`, klayout-tools#3778). `klt signoff` item 5 DERIVES
# a citation's row coverage from these tags instead of trusting the manifest,
# so row 4 is credited only while a tagged, limited, passing measurement exists
# -- and the nine Open rows, declared in the manifest's `spec_rows` and covered
# by nothing, keep item 5 `unmet / partial_coverage` by the grader's own
# arithmetic. The id must match the manifest's `spec_rows["5"][].id`.
ROW4_ID = "dr0007-row4-dropout"

OSDI_ORDER = ["psp103", "psp103_nqs", "mosvar", "r3_cmc", "cap_cmomi", "cap_cmomf"]

# The committed files whose bytes decide what was simulated. Their sha256 goes
# into every record's provenance.json, and `check` re-hashes them against the
# working tree FOR THE CITED RECORD, so a design-netlist or template edit makes
# the citation go stale loudly instead of silently describing a different
# circuit. This generator is deliberately NOT in the list: it is re-verified by
# byte-reproduction of the request and summary files, which is stronger than a
# hash (a hash only says "unchanged"; reproduction says "these exact bytes come
# out of the code that is committed now").
INPUTS = [TEMPLATE, PDK_PIN, DESIGN_NETLIST,
          "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice"]

PROBE_COORDS = [("tt", 27, "typ"), ("ss", 125, "typ")]

GRADED = ["vout_at_dropout_limit_v", "vin_1pct_loss_v"]
UNGRADED = ["vout_nominal_v"]


class Error(Exception):
    pass


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def coords(probe=False):
    """The (mos, temp, res) coordinates, each exactly once."""
    if probe:
        return list(PROBE_COORDS)
    return [(m, t, r) for m in MOS for t in TEMPS for r in RES]


def section_of(mos, res):
    return f"mos_{mos}__res_{res}__cap_{CAP}"


def corner_id(mos, temp, res):
    """The `corner_id` `klt sim` reports for this coordinate."""
    return f"{section_of(mos, res)}/novdd/{temp}C"


# --------------------------------------------------------------------------- #
# request generation (pure: template text + three substitutions -> bytes)
# --------------------------------------------------------------------------- #

def tb_text(design_netlist_include, template_text):
    return template_text.replace("@@DESIGN_NETLIST@@", design_netlist_include)


def corners_lib_text(models_dir, cs):
    out = ["* generated by sim/ldo-cmos5l-pvt-sweep/row4_envelope.py:",
           "* one .lib section per (MOS, RES, CAP) corner bundle; `klt sim` selects",
           "* one of them per corner through the request's corners.process axis."]
    for name in sorted({section_of(m, r) for m, _, r in cs}):
        mos = name.split("__")[0][len("mos_"):]
        res = name.split("__")[1][len("res_"):]
        out += [f".lib {name}",
                f'.lib "{models_dir}/cornerMOShv.lib" mos_{mos}',
                f'.lib "{models_dir}/cornerRES.lib" res_{res}',
                f'.lib "{models_dir}/cornerCAP.lib" cap_{CAP}',
                f".endl {name}"]
    return "\n".join(out) + "\n"


def measurements():
    return [
        {"name": "vout_at_dropout_limit_v",
         "spice": ".meas dc vout_at_dropout_limit_v FIND v(vout) AT=2.100",
         "unit": "V",
         "limits": {"min": V_THR_V},
         "spec_row": ROW4_ID},
        {"name": "vin_1pct_loss_v",
         "spice": f".meas dc vin_1pct_loss_v WHEN v(vout)={V_THR_V:.3f} RISE=1",
         "unit": "V",
         "limits": {"max": VIN_LIMIT_V},
         "spec_row": ROW4_ID},
        # Untagged and ungraded on purpose: row 2 (output accuracy) is Open, so
        # this must neither carry a gate nor claim coverage of any row.
        {"name": "vout_nominal_v",
         "spice": f".meas dc vout_nominal_v FIND v(vout) AT={VIN_REF_V:.3f}",
         "unit": "V"},
    ]


def request_obj(osdi_dir, cs):
    sections = sorted({section_of(m, r) for m, _, r in cs})
    temps = sorted({t for _, t, _ in cs})
    present = {(section_of(m, r), t) for m, t, r in cs}
    exclude = [{"process": s, "temperature_c": t}
               for s in sections for t in temps if (s, t) not in present]
    req = {
        "netlist": "tb.spice",
        "backend": "batch",
        # capacity_wait_s is the host-rule requirement ("--wait-for-capacity
        # 600 on every batch klt sim"); `submit` passes the flag too.
        "batch": {"runner_version_check": "warn", "capacity_wait_s": 600},
        "models": {"lib": "corners.lib"},
        "analysis": {"kind": "dc", "args": VIN_AXIS},
        "measurements": measurements(),
        "corners": {"process": sections, "temperature_c": temps},
        "options": {
            "timeout_s": 1800,
            "keep_artifacts": True,
            # No waveform export: every graded quantity is a .meas result, so
            # the job neither writes nor ships rawfiles.
            "waveforms": False,
            "stage_model_inputs": True,
            "osdi_preload": [f"{osdi_dir}/{n}.osdi" for n in OSDI_ORDER],
        },
    }
    if exclude:
        req["exclude"] = exclude
    return req


def request_files(subs, cs, template_text):
    """The three request-dir files, as {name: text}. Deterministic."""
    return {
        "tb.spice": tb_text(subs["design_netlist_include"], template_text),
        "corners.lib": corners_lib_text(subs["pdk_models_dir"], cs),
        "request.json": json.dumps(request_obj(subs["osdi_dir"], cs), indent=1) + "\n",
    }


def design_netlist_include(depth):
    """The repo-relative `.include` target for a request dir `depth` levels
    below the repo root (row4-envelope/<record-id>/ is 4)."""
    return "/".join([".."] * depth) + "/" + DESIGN_NETLIST


# --------------------------------------------------------------------------- #
# summary (pure: report.json + provenance.json -> bytes)
# --------------------------------------------------------------------------- #

def f9(v):
    return "" if v is None else (f"{v:.9g}" if isinstance(v, float) else str(v))


def summarise_report(report, prov):
    cs = coords(prov.get("probe", False))
    want = {corner_id(*c): c for c in cs}
    seen = {}
    points = []
    for c in report.get("corners", []):
        cid = c.get("corner_id")
        seen[cid] = seen.get(cid, 0) + 1
        meas = {m["name"]: m for m in c.get("measurements", [])}
        errs = [d for d in c.get("diagnostics", []) if d.get("severity") == "error"]
        vin = meas.get("vin_1pct_loss_v", {}).get("value")
        coord = want.get(cid)
        points.append({
            "corner_id": cid,
            "mos": coord[0] if coord else None,
            "temp_c": coord[1] if coord else None,
            "res_section": f"res_{coord[2]}" if coord else None,
            "corner_status": c.get("status"),
            "error_diagnostics": len(errs),
            "dropout_v": None if vin is None else vin - VOUT_TARGET_V,
            **{n: meas.get(n, {}).get("value") for n in GRADED + UNGRADED},
            **{n + "_status": meas.get(n, {}).get("status") for n in GRADED},
        })
    points.sort(key=lambda p: p["corner_id"])

    status_counts = {}
    for p in points:
        status_counts[p["corner_status"]] = status_counts.get(p["corner_status"], 0) + 1
    graded_ok = all(p[n + "_status"] == "pass" for p in points for n in GRADED)
    resolved = [p for p in points if p["dropout_v"] is not None]
    summ = {
        "record_id": prov["record_id"],
        "probe": bool(prov.get("probe", False)),
        "n_expected": len(cs),
        "n_corners_reported": len(points),
        "coordinates_exactly_once": sorted(seen) == sorted(want) and set(seen.values()) <= {1},
        "envelope_status": report.get("status"),
        "passed": report.get("passed"),
        "failed": report.get("failed"),
        "errored": report.get("errored"),
        "inconclusive": report.get("inconclusive"),
        "corner_status_counts": dict(sorted(status_counts.items())),
        "error_diagnostics_total": sum(p["error_diagnostics"] for p in points),
        "measurements_with_limits": (report.get("coverage") or {}).get("measurements_with_limits"),
        "graded_measurements": list(GRADED),
        "all_graded_measurements_pass": graded_ok,
        "target_dropout_v": TARGET_DROPOUT_V,
        "vout_target_v": VOUT_TARGET_V,
        "definitive": False,
    }
    if resolved:
        w = max(resolved, key=lambda p: p["dropout_v"])
        summ["worst_corner"] = {k: w[k] for k in ("corner_id", "mos", "temp_c", "res_section",
                                                  "dropout_v", "vin_1pct_loss_v",
                                                  "vout_at_dropout_limit_v")}
        summ["worst_dropout_v"] = w["dropout_v"]
        summ["margin_to_target_v"] = TARGET_DROPOUT_V - w["dropout_v"]
        summ["series_resistance_equivalent_ohm"] = summ["margin_to_target_v"] / LOAD_A
        summ["grid_bracket_v"] = 0.005
        summ["worst_dropout_upper_bound_v"] = w["dropout_v"] + 0.005
    summ["definitive"] = bool(
        not summ["probe"]
        and summ["n_corners_reported"] == len(cs) == N_EXPECTED
        and summ["coordinates_exactly_once"]
        and summ["envelope_status"] == "pass"
        and summ["passed"] == N_EXPECTED
        and not summ["failed"] and not summ["errored"] and not summ["inconclusive"]
        and summ["error_diagnostics_total"] == 0
        and graded_ok
        and summ["measurements_with_limits"] == len(GRADED)
        and len(resolved) == N_EXPECTED
    )
    return summ, points


def summary_md(summ, points, prov):
    rid = summ["record_id"]
    L = [f"# Row-4 graded `klt sim` corner-matrix envelope `{rid}`", "",
         "DR-0007 row 4, **Dropout @ 50 mA < 300 mV worst corner** -- the one ratified",
         "row of the target spec. The verdict below is `klt sim`'s own: both graded",
         "measurements carry `limits` in `request.json`, so each corner's pass/fail and",
         "the matrix verdict (`status`) are computed by the tool, not by this repo.", "",
         "Measurement definition: the LEGACY row-4 quantity DR-0007 ratified --",
         f"the lowest Vin whose VOUT is still within {LOSS_FRACTION*100:.0f} % of the fixed",
         f"{VOUT_TARGET_V:.3f} V target, minus that target. DR-0012's own-regulated-output",
         "reference is PROPOSED and is not expressible as a `klt sim` request (a `.meas`",
         "`WHEN` threshold must be a literal); see `signoff/README.md`.", ""]
    if summ["probe"]:
        L += ["> **PROBE RECORD.** A capacity / toolchain probe over "
              f"{summ['n_expected']} coordinates, not the ratified matrix. Never cited.", ""]
    L += [f"- Corners: {summ['n_corners_reported']}/{summ['n_expected']} reported, "
          f"every coordinate exactly once: {summ['coordinates_exactly_once']}.",
          f"- Envelope `status`: **{summ['envelope_status']}** "
          f"(passed {summ['passed']}, failed {summ['failed']}, errored {summ['errored']}, "
          f"inconclusive {summ['inconclusive']}).",
          f"- Corner status counts: {summ['corner_status_counts']}; "
          f"error-severity diagnostics: {summ['error_diagnostics_total']}.",
          f"- Graded measurements (`coverage.measurements_with_limits` = "
          f"{summ['measurements_with_limits']}): {', '.join(summ['graded_measurements'])}; "
          f"all pass: {summ['all_graded_measurements_pass']}.",
          f"- Definitive worst-corner claim permitted: **{summ['definitive']}** (requires the "
          f"whole {N_EXPECTED}-coordinate matrix reported, resolved, graded and clean)."]
    if "worst_corner" in summ:
        w = summ["worst_corner"]
        L += ["",
              f"- Worst corner: `{w['mos']}` / {w['temp_c']} C / `{w['res_section']}` "
              f"(`{w['corner_id']}`): dropout {w['dropout_v']*1000:.2f} mV "
              f"(`vin_1pct_loss_v` {w['vin_1pct_loss_v']:.5f} V - {VOUT_TARGET_V:.3f} V), "
              f"VOUT at the {VIN_LIMIT_V:.3f} V limit {w['vout_at_dropout_limit_v']:.5f} V.",
              f"- Margin to the {TARGET_DROPOUT_V*1000:.0f} mV target: "
              f"{summ['margin_to_target_v']*1000:.2f} mV = "
              f"{summ['margin_to_target_v']*1000:.2f} mV / {LOAD_A*1000:.0f} mA = "
              f"{summ['series_resistance_equivalent_ohm']:.3f} ohm series resistance, before "
              "any parasitic extraction.",
              f"- Conservative read: the Vin axis is {summ['grid_bracket_v']*1000:.0f} mV, so the "
              f"worst dropout's grid upper bound is {summ['worst_dropout_upper_bound_v']*1000:.2f} mV, "
              f"still under {TARGET_DROPOUT_V*1000:.0f} mV."]
    L += ["", "## Per-corner", "",
          "| corner | status | dropout (mV) | `vin_1pct_loss_v` (V) | "
          "`vout_at_dropout_limit_v` (V) | `vout_nominal_v` (V) |", "|---|---|---|---|---|---|"]
    for p in points:
        d = "" if p["dropout_v"] is None else f"{p['dropout_v']*1000:.2f}"
        L.append(f"| `{p['corner_id']}` | {p['corner_status']} | {d} | "
                 f"{f9(p['vin_1pct_loss_v'])} | {f9(p['vout_at_dropout_limit_v'])} | "
                 f"{f9(p['vout_nominal_v'])} |")
    L += ["", "## Provenance", ""]
    for k, v in sorted(prov.items()):
        if k == "input_sha256":
            continue
        L.append(f"- {k}: `{json.dumps(v, sort_keys=True)}`" if isinstance(v, (dict, list))
                 else f"- {k}: {v}")
    L += ["", "Input sha256:", ""]
    for k, v in sorted(prov.get("input_sha256", {}).items()):
        L.append(f"- `{k}`: `{v}`")
    L += ["", f"Machine summary: `row4-envelope.json`; the graded envelope itself: "
          f"`report.json`; the request that produced it: `request.json`, `tb.spice`, "
          f"`corners.lib`.", ""]
    return "\n".join(L)


def summary_files(record_dir):
    report = json.load(open(os.path.join(record_dir, "report.json")))
    prov = json.load(open(os.path.join(record_dir, "provenance.json")))
    summ, points = summarise_report(report, prov)
    return {
        "row4-envelope.json": json.dumps({"summary": summ, "points": points},
                                         indent=1, sort_keys=True) + "\n",
        "row4-envelope.md": summary_md(summ, points, prov),
    }, summ


def write_or_check(record_dir, files, check):
    bad = []
    for name, text in sorted(files.items()):
        path = os.path.join(record_dir, name)
        if check:
            if not os.path.exists(path):
                bad.append(f"{name}: missing")
            elif open(path).read() != text:
                bad.append(f"{name}: stale")
        else:
            with open(path, "w") as f:
                f.write(text)
    return bad


# --------------------------------------------------------------------------- #
# submit
# --------------------------------------------------------------------------- #

def resolve_env():
    out = subprocess.run(
        ["bash", "-c", f"export PDK={PDK}; source {REPO}/sim/env.sh >/dev/null 2>&1; "
         "echo $PDK_ROOT; echo $SG13G2_OSDI_DIR"],
        capture_output=True, text=True).stdout.split()
    if len(out) != 2:
        raise Error("cannot resolve PDK_ROOT / OSDI dir from sim/env.sh "
                    f"(PDK={PDK}); install the PDK or set PDK_ROOT")
    pdk_root, osdi = out
    models = os.path.join(pdk_root, PDK, "libs.tech", "ngspice", "models")
    for d in (models, osdi):
        if not os.path.isdir(d):
            raise Error(f"missing {d}")
    return pdk_root, models, osdi


def cmd_submit(a):
    cs = coords(a.probe)
    pdk_root, models, osdi = resolve_env()
    sha7 = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or "unknown"
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + sha7
    if a.probe:
        rid += "-probe"
    record_dir = os.path.join(ROOT, rid)
    if os.path.exists(record_dir):
        raise Error(f"{record_dir} exists; records are append-only")

    depth = len(os.path.relpath(record_dir, REPO).split(os.sep))
    subs = {"design_netlist_include": design_netlist_include(depth),
            "pdk_models_dir": models, "osdi_dir": osdi}
    template_text = open(os.path.join(REPO, TEMPLATE)).read()
    files = request_files(subs, cs, template_text)

    os.makedirs(record_dir)
    write_or_check(record_dir, files, check=False)

    art = tempfile.mkdtemp(prefix="row4-envelope-artifacts.")
    cmd = ["klt", "sim", "request.json", "--backend", "batch",
           "--wait-for-capacity", "600", "-o", art, "--format", "json"]
    if a.dry_run:
        cmd.append("--dry-run")
    print("row4_envelope: cd " + os.path.relpath(record_dir, REPO) + " && " + " ".join(cmd),
          file=sys.stderr)
    with open(os.path.join(record_dir, "report.json"), "w") as out, \
            open(os.path.join(record_dir, "klt-sim.stderr"), "w") as err:
        rc = subprocess.call(cmd, cwd=record_dir, stdout=out, stderr=err)
    stderr_text = open(os.path.join(record_dir, "klt-sim.stderr")).read()
    sys.stderr.write(stderr_text)
    if a.dry_run:
        print(f"row4_envelope: --dry-run (exit {rc}); scratch record {record_dir} "
              "is NOT evidence -- delete it by hand.", file=sys.stderr)
        return rc

    prov = {
        "record_id": rid,
        "probe": bool(a.probe),
        "git_sha": sha7,
        "invocation": "python3 sim/ldo-cmos5l-pvt-sweep/row4_envelope.py submit"
                      + (" --probe" if a.probe else ""),
        "klt_sim_exit": rc,
        "klt_sim_argv": " ".join(cmd),
        "substitutions": subs,
        "pdk": PDK,
        "pdk_root": pdk_root,
        "pdk_pin": PDK_PIN,
        "ratified_row": "DR-0007 row 4 (Dropout @ 50 mA < 300 mV worst corner)",
        "measurement_definition": "legacy dropout_v_50ma (1 % loss vs the fixed "
                                  "1.800 V target); DR-0012's own-V_reg reference is "
                                  "PROPOSED and not expressible as a klt sim request",
        "batch_job_ids": sorted(set(re.findall(r"klt-sim-[0-9a-f]+", stderr_text))),
        "input_sha256": {p: sha256_file(os.path.join(REPO, p)) for p in INPUTS},
    }
    with open(os.path.join(record_dir, "provenance.json"), "w") as f:
        json.dump(prov, f, indent=1, sort_keys=True)
        f.write("\n")

    files, summ = summary_files(record_dir)
    write_or_check(record_dir, files, check=False)
    print(json.dumps(summ, indent=1, sort_keys=True))
    if not summ["definitive"] and not a.probe:
        print("row4_envelope: NOT definitive -- this record must not be cited under "
              "signoff item 5. Read row4-envelope.md and report.json's diagnostics.",
              file=sys.stderr)
        return rc or 1
    return rc


def cmd_summarise(a):
    record_dir = os.path.join(ROOT, a.record_id)
    if not os.path.isdir(record_dir):
        raise Error(f"no such record: {record_dir}")
    files, summ = summary_files(record_dir)
    bad = write_or_check(record_dir, files, check=a.check)
    if bad:
        raise Error("summary files stale or missing: " + ", ".join(bad))
    print(json.dumps(summ, indent=1, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- #
# check (offline, stdlib-only, no PDK and no simulator -- this is the CI gate)
# --------------------------------------------------------------------------- #

def records():
    if not os.path.isdir(ROOT):
        return []
    return sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)))


def cited_record():
    """(record_id, pinned content_hash) from signoff/sg13g2-ldo.json item 5, or
    (None, None) when item 5 is uncited.

    Item 5 is a multi-citation item: the entry is a LIST of members, each
    optionally naming the `spec_rows` it covers. Exactly one member is a
    row4-envelope record today; a second one (another row, another bench) is
    the expected growth path and is not this script's business, so only the
    row4-envelope member is resolved here.
    """
    m = json.load(open(os.path.join(REPO, "signoff", "sg13g2-ldo.json")))
    ent = (m.get("evidence") or {}).get("5")
    if ent is None:
        return None, None
    members = ent if isinstance(ent, list) else [ent]
    mine = [x for x in members if isinstance(x, dict)
            and "row4-envelope/" in str(x.get("file", ""))]
    if not mine:
        return None, None
    if len(mine) > 1:
        raise Error(f"signoff item 5 cites {len(mine)} row4-envelope records; "
                    "exactly one is expected")
    ent = mine[0]
    rows = ent.get("rows")
    if rows != [ROW4_ID]:
        raise Error(f"signoff item 5's row4-envelope citation declares rows {rows!r}, "
                    f"not [{ROW4_ID!r}] -- the envelope grades that row and no other")
    rel = ent.get("file", "")
    want = os.path.relpath(ROOT, REPO).replace(os.sep, "/") + "/"
    if not rel.startswith(want) or not rel.endswith("/report.json"):
        raise Error(f"signoff item 5 cites {rel!r}; the row4-envelope citation must be "
                    f"{want}<record-id>/report.json")
    return rel[len(want):-len("/report.json")], ent.get("content_hash")


def check_record(rid, problems):
    record_dir = os.path.join(ROOT, rid)
    prov_path = os.path.join(record_dir, "provenance.json")
    if not os.path.exists(prov_path):
        problems.append(f"{rid}: no provenance.json")
        return None
    prov = json.load(open(prov_path))
    cs = coords(prov.get("probe", False))

    # 1. the request reproduces byte-for-byte from the template + the recorded
    #    substitutions, so a template edit cannot silently diverge from the
    #    bytes that ran.
    template_text = open(os.path.join(REPO, TEMPLATE)).read()
    want = request_files(prov["substitutions"], cs, template_text)
    problems += [f"{rid}: request {b}" for b in write_or_check(record_dir, want, check=True)]

    # 2. the summary files reproduce from report.json + provenance.json.
    try:
        files, summ = summary_files(record_dir)
    except FileNotFoundError as exc:
        problems.append(f"{rid}: {exc}")
        return None
    problems += [f"{rid}: summary {b}" for b in write_or_check(record_dir, files, check=True)]

    # 3. the envelope's own recorded input hash is the committed tb.spice, and
    #    its models-lib hash is the committed corners.lib. This is the pin the
    #    signoff grader re-verifies; checking it here fails loudly offline
    #    rather than as a grading drift later.
    report = json.load(open(os.path.join(record_dir, "report.json")))
    tb = sha256_file(os.path.join(record_dir, "tb.spice"))
    lib = sha256_file(os.path.join(record_dir, "corners.lib"))
    got = ((report.get("provenance") or {}).get("input") or {}).get("content_hash")
    if got != "sha256:" + tb:
        problems.append(f"{rid}: envelope provenance.input.content_hash {got} != "
                        f"sha256 of the committed tb.spice (sha256:{tb})")
    # `klt sim` records `netlist` either as the request's own relative string or,
    # when it resolves inside the repo, as {"path": <repo-relative>, "scope":
    # "repo"} (what 0.9.2 writes). Either way it must name THIS record's
    # tb.spice -- that is the file the signoff grader re-hashes.
    nl = report.get("netlist")
    nl_path = nl.get("path") if isinstance(nl, dict) else nl
    tail = f"row4-envelope/{rid}/tb.spice"
    if nl_path != "tb.spice" and not str(nl_path).endswith(tail):
        problems.append(f"{rid}: envelope netlist is {nl_path!r}, "
                        f"neither 'tb.spice' nor a path ending {tail!r}")
    env_lib = (report.get("environment") or {}).get("models_lib_sha256")
    if env_lib != lib:
        problems.append(f"{rid}: envelope models_lib_sha256 {env_lib} != "
                        f"sha256 of the committed corners.lib ({lib})")

    # 4. the request the envelope was graded against still declares the limits
    #    this script says it does -- a relaxed gate cannot hide in the record.
    req = json.load(open(os.path.join(record_dir, "request.json")))
    declared = {m["name"]: m.get("limits") for m in req["measurements"]}
    expect = {m["name"]: m.get("limits") for m in measurements()}
    if declared != expect:
        problems.append(f"{rid}: request limits {declared} != the ratified gates {expect}")
    tagged = {m["name"]: m.get("spec_row") for m in req["measurements"]}
    want_tags = {m["name"]: m.get("spec_row") for m in measurements()}
    if tagged != want_tags:
        problems.append(f"{rid}: request spec_row tags {tagged} != {want_tags}")
    for m in report.get("measurements", []):
        if m["name"] in GRADED and m.get("limits") != expect[m["name"]]:
            problems.append(f"{rid}: envelope measurement {m['name']} graded against "
                            f"{m.get('limits')}, not {expect[m['name']]}")
        if m["name"] in GRADED and m.get("spec_row") != ROW4_ID:
            problems.append(f"{rid}: envelope measurement {m['name']} carries spec_row "
                            f"{m.get('spec_row')!r}, not {ROW4_ID!r}; the signoff grader "
                            "derives row coverage from this tag")
        if m["name"] in UNGRADED and m.get("spec_row") is not None:
            problems.append(f"{rid}: ungraded measurement {m['name']} claims spec_row "
                            f"{m.get('spec_row')!r}; an Open row must not be claimed")
    return summ


def check_spec_rows(problems):
    """The manifest's item-5 `spec_rows` must still describe DR-0007: ten rows,
    row 4 the only ratified one. Without this, flipping one `ratified: false`
    to `true` in the manifest would quietly turn an Open row into covered-or-
    uncovered arithmetic the grader treats as ratifiable -- a spec relaxation
    made in a JSON file rather than in a decision record."""
    m = json.load(open(os.path.join(REPO, "signoff", "sg13g2-ldo.json")))
    rows = (m.get("spec_rows") or {}).get("5")
    if not isinstance(rows, list):
        problems.append("signoff manifest declares no spec_rows['5']; item 5 would then "
                        "grade on the cited envelope alone and read as full coverage")
        return
    ids = [r.get("id") for r in rows if isinstance(r, dict)]
    if len(ids) != 10 or len(set(ids)) != 10:
        problems.append(f"spec_rows['5'] declares {len(ids)} rows ({len(set(ids))} "
                        "distinct); DR-0007's target spec has exactly 10")
    if ROW4_ID not in ids:
        problems.append(f"spec_rows['5'] does not declare {ROW4_ID}")
    ratified = sorted(r["id"] for r in rows
                      if isinstance(r, dict) and r.get("ratified", True))
    if ratified != [ROW4_ID]:
        problems.append(f"spec_rows['5'] marks {ratified} ratified; DR-0007 ratifies "
                        f"row 4 only ({ROW4_ID}). Ratifying a row is a decision record, "
                        "not a manifest edit")


def stale_inputs(rid):
    """Problems for a record whose recorded inputs no longer match the tree.

    Applied to the CITED record only: an older record describes the design as
    it was and is history, but a citation must describe the design as it is --
    the same freshness rule the signoff grader applies to its own pins.
    """
    prov = json.load(open(os.path.join(ROOT, rid, "provenance.json")))
    out = []
    for rel, want in sorted(prov.get("input_sha256", {}).items()):
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            out.append(f"cited record {rid}: input {rel} no longer exists")
        elif sha256_file(path) != want:
            out.append(f"cited record {rid}: input {rel} changed since the run "
                       f"(recorded {want[:12]}..., tree {sha256_file(path)[:12]}...); "
                       "the citation is stale -- re-run `row4_envelope.py submit` "
                       "and re-pin item 5")
    return out


def cmd_check(a):
    problems = []
    rids = records()
    if not rids:
        problems.append("no record under sim/ldo-cmos5l-pvt-sweep/row4-envelope/")
    summaries = {rid: check_record(rid, problems) for rid in rids}

    check_spec_rows(problems)
    cited, pinned = cited_record()
    if cited is None:
        print("row4_envelope: signoff item 5 is uncited; records checked for "
              "self-consistency only.", file=sys.stderr)
    elif cited not in summaries:
        problems.append(f"signoff item 5 cites record {cited}, which is not committed")
    else:
        summ = summaries[cited]
        tb = sha256_file(os.path.join(ROOT, cited, "tb.spice"))
        if pinned != "sha256:" + tb:
            problems.append(f"signoff item 5 content_hash {pinned} != sha256:{tb} "
                            f"(the cited record's tb.spice)")
        problems += stale_inputs(cited)
        if summ is None or not summ["definitive"]:
            problems.append(f"signoff item 5 cites record {cited}, whose summary is not "
                            "definitive; an incomplete or failing matrix must stay uncited")
        elif summ["probe"]:
            problems.append(f"signoff item 5 cites probe record {cited}")

    for p in problems:
        print("row4_envelope: " + p, file=sys.stderr)
    if problems:
        return 1
    print(f"row4_envelope: OK -- {len(rids)} record(s) reproduce and self-verify"
          + (f"; signoff item 5 cites {cited}" if cited else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("submit", help="mint a new record on the EDA batch fleet")
    s.add_argument("--probe", action="store_true",
                   help=f"{len(PROBE_COORDS)} coordinates only, for a capacity / "
                        "toolchain probe; never citable")
    s.add_argument("--dry-run", action="store_true",
                   help="build and validate the request without submitting")
    s.set_defaults(fn=cmd_submit)
    c = sp.add_parser("check", help="offline: every committed record reproduces (CI)")
    c.set_defaults(fn=cmd_check)
    m = sp.add_parser("summarise", help="rewrite one record's summary files")
    m.add_argument("record_id")
    m.add_argument("--check", action="store_true")
    m.set_defaults(fn=cmd_summarise)
    a = ap.parse_args()
    try:
        return a.fn(a)
    except Error as exc:
        print(f"row4_envelope: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
