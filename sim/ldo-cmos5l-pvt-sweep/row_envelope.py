#!/usr/bin/env python3
"""Shared machinery for the graded `klt sim` row-envelope benches (issue #317).

`row4_envelope.py` (DR-0007 row 4, ratified) and `row7_envelope.py`
(DR-0007 row 7, Open) are two drivers over one bench pattern:

  * mint an append-only timestamped record directory,
  * build a `klt sim` request whose per-row `limits` are declared INSIDE the
    request (so the per-corner and whole-matrix verdict is the tool's own,
    never this repo's Python),
  * submit it to the EDA batch fleet (`--wait-for-capacity 600`, never a
    local grid),
  * summarise the returned envelope into the record, and
  * re-verify every committed record offline (CI, stdlib only).

Everything row-agnostic lives in this module: the 45-point corner grid,
the request skeleton, the corners.lib renderer, the record-submit flow and
the offline record checks.  Each driver owns its measurements, thresholds,
summary text and citation rules.

Byte-critical contract (the Hermit note on issue #317): the first line of
every `corners.lib` names the DRIVER that generated it, and that file is
pinned by the fleet report's `environment.models_lib_sha256` -- a check
`klt sim --check` and this repo's `check` subcommands re-verify.  The
shared renderer therefore takes the header lines as an ARGUMENT; a refactor
that moved the renderer into this module silently changed those bytes and
broke every committed record's reproduction (verified in memory before this
module was written: all three committed row-4 libraries matched their
recorded hashes with the driver-path header and all three differed with a
`row_envelope.py` header).  A new driver passes its own path in
`header_lines`; it must never copy another driver's.

No .control block ever appears in a driver's template: the fleet runner
applies `options.osdi_preload` itself, so a deck-side `pre_osdi` load makes
every corner fail (see row4_envelope.py's header for the incident).
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import render_deck  # noqa: E402

PDK = "ihp-sg13cmos5l"
PDK_PIN = "sim/pdk-cmos5l.json"

# The 45-point PVT grid every row bench shares: 5 MOS x 3 resistor x 3
# temperature corners, capacitor corner pinned at typ (the MoM-cap model has
# no corner spread at this PDK pin -- DR-0007's evidence base did the same).
MOS = ["tt", "ff", "ss", "sf", "fs"]
RES = ["typ", "bcs", "wcs"]
CAP = "typ"
TEMPS = [-40, 27, 125]
N_EXPECTED = len(MOS) * len(RES) * len(TEMPS)        # 45
PROBE_COORDS = [("tt", 27, "typ"), ("ss", 125, "typ")]

# ngspice must preload the OSDI-compiled device models (PSP 1.0.3 MOSFETs,
# rhigh resistors, MoM caps) or every device resolves to nothing.
OSDI_ORDER = ["psp103", "psp103_nqs", "mosvar", "r3_cmc", "cap_cmomi", "cap_cmomf"]

# DR-0021: the PDK pin is NOT byte-pinned. sim/pdk-cmos5l.json is a prose fact
# sheet no code consumes, so a whole-file hash made a documentation edit stale
# the citation. Records pin a canonical projection of the keys that decide
# which PDK tree was fetched; legacy records (PDK_PIN inside `input_sha256`)
# keep their whole-file byte compare.
PDK_PIN_KEYS = ("pinned_commit", "pinned_tarball_sha256", "pinned_tarball_url",
                "subtree")
PDK_PIN_PROJECTION_FIELD = "pdk_pin_projection_sha256"

# The fixed tail of every corners.lib: one .lib section per (MOS, RES, CAP)
# bundle, after the driver-supplied header lines.
_CORNERS_LIB_TAIL = [
    "* one .lib section per (MOS, RES, CAP) corner bundle; `klt sim` selects",
    "* one of them per corner through the request's corners.process axis.",
]


class Error(Exception):
    pass


# --------------------------------------------------------------------------- #
# the 45-point grid
# --------------------------------------------------------------------------- #

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
# request generation (pure: template text + substitutions -> bytes)
# --------------------------------------------------------------------------- #

def tb_text(design_netlist_include, template_text):
    # One renderer for every deck (#236): sim/tools/render_deck.py. It fails
    # loudly on any unsubstituted @@TOKEN@@.
    return render_deck.render(template_text, {"DESIGN_NETLIST": design_netlist_include})


def corners_lib_text(models_dir, cs, header_lines):
    """The models.lib text: driver header lines + one .lib section per corner
    bundle. `header_lines[0]` must name the DRIVER (see this module's header:
    those bytes are pinned by the fleet report)."""
    if (not header_lines
            or not re.fullmatch(r"\* generated by \S+\.py:", header_lines[0])):
        raise Error("corners.lib header must be '* generated by <driver path>.py:' "
                    "-- those bytes are pinned by the fleet report")
    out = list(header_lines) + list(_CORNERS_LIB_TAIL)
    for name in sorted({section_of(m, r) for m, _, r in cs}):
        mos = name.split("__")[0][len("mos_"):]
        res = name.split("__")[1][len("res_"):]
        out += [f".lib {name}",
                f'.lib "{models_dir}/cornerMOShv.lib" mos_{mos}',
                f'.lib "{models_dir}/cornerRES.lib" res_{res}',
                f'.lib "{models_dir}/cornerCAP.lib" cap_{CAP}',
                f".endl {name}"]
    return "\n".join(out) + "\n"


def request_skeleton(cs, analysis_key, analysis_value, measurements, osdi_dir,
                     extra_options=None, timeout_s=1800):
    """The request dict every row bench shares, in the canonical key order
    (json.dumps preserves insertion order, so this order is part of the
    committed bytes and must not move). The row-specific half is the analysis
    half (`analysis` or `analysis_steps`) and the measurements."""
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
        analysis_key: analysis_value,
        "measurements": measurements,
        "corners": {"process": sections, "temperature_c": temps},
        "options": {
            "timeout_s": timeout_s,
            "keep_artifacts": True,
            # No waveform export: every graded quantity is a scalar measurement,
            # so the job neither writes nor ships rawfiles.
            "waveforms": False,
            "stage_model_inputs": True,
            "osdi_preload": [f"{osdi_dir}/{n}.osdi" for n in OSDI_ORDER],
        },
    }
    if extra_options:
        req["options"].update(extra_options)
    if exclude:
        req["exclude"] = exclude
    return req


def request_files(subs, cs, template_text, header_lines, request_obj_fn):
    """The three request-dir files, as {name: text}. Deterministic."""
    return {
        "tb.spice": tb_text(subs["design_netlist_include"], template_text),
        "corners.lib": corners_lib_text(subs["pdk_models_dir"], cs, header_lines),
        "request.json": json.dumps(request_obj_fn(subs["osdi_dir"], cs), indent=1) + "\n",
    }


def design_netlist_include(depth, design_netlist):
    """The repo-relative `.include` target for a request dir `depth` levels
    below the repo root (row4-envelope/<record-id>/ is 4)."""
    return "/".join([".."] * depth) + "/" + design_netlist


# --------------------------------------------------------------------------- #
# record plumbing shared by submit and check
# --------------------------------------------------------------------------- #

def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pdk_pin_projection_sha256(path=None):
    """sha256 of the canonical JSON of the PDK pin's fetch-determining keys.

    Canonical = sort_keys + fixed separators, so key order and whitespace in
    the fact sheet do not matter. A missing or non-string projected key raises
    ValueError: a renamed key must never be a silent skip (it would pin an
    empty projection and let a real pin change through).
    """
    path = path or os.path.join(REPO, PDK_PIN)
    with open(path) as f:
        doc = json.load(f)
    bad = [k for k in PDK_PIN_KEYS
           if not isinstance(doc.get(k), str) or not doc[k]]
    if bad:
        raise ValueError(f"{PDK_PIN}: projected key(s) {bad} missing or not a "
                         "non-empty string; the PDK pin cannot be projected")
    canon = json.dumps({k: doc[k] for k in PDK_PIN_KEYS}, sort_keys=True,
                       separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


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


def records(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))


def f9(v):
    return "" if v is None else (f"{v:.9g}" if isinstance(v, float) else str(v))


# --------------------------------------------------------------------------- #
# submit (the fleet run; one append-only record per invocation)
# --------------------------------------------------------------------------- #

def submit_record(a, *, slug, root, template_rel, design_netlist_rel,
                  header_lines, request_files_fn, summary_files_fn,
                  invocation_fmt, prov_extra, post_fn=None):
    """Mint a new record on the EDA batch fleet. Never runs SPICE locally.

    `request_files_fn(subs, cs, template_text)` and
    `summary_files(record_dir) -> (files, summ)` are the driver's row-specific
    halves; `post_fn(record_dir)`, if given, runs on THIS invocation's own
    freshly minted record once its summary is written (never a lookup of
    "the newest record", which a concurrent run can change); `invocation_fmt` is a `.format(probe=...)` template for
    provenance, `prov_extra(rid, probe)` adds the row's own provenance keys.
    """
    cs = coords(a.probe)
    pdk_root, models, osdi = resolve_env()
    sha7 = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or "unknown"
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + sha7
    if a.probe:
        rid += "-probe"
    record_dir = os.path.join(root, rid)
    if os.path.exists(record_dir):
        raise Error(f"{record_dir} exists; records are append-only")

    depth = len(os.path.relpath(record_dir, REPO).split(os.sep))
    subs = {"design_netlist_include": design_netlist_include(depth, design_netlist_rel),
            "pdk_models_dir": models, "osdi_dir": osdi}
    template_text = open(os.path.join(REPO, template_rel)).read()
    files = request_files_fn(subs, cs, template_text)

    os.makedirs(record_dir)
    write_or_check(record_dir, files, check=False)

    art = tempfile.mkdtemp(prefix=f"{slug}-envelope-artifacts.")
    cmd = ["klt", "sim", "request.json", "--backend", "batch",
           "--wait-for-capacity", "600", "-o", art, "--format", "json"]
    if a.dry_run:
        cmd.append("--dry-run")
    print(f"{slug}_envelope: cd " + os.path.relpath(record_dir, REPO)
          + " && " + " ".join(cmd), file=sys.stderr)
    with open(os.path.join(record_dir, "report.json"), "w") as out, \
            open(os.path.join(record_dir, "klt-sim.stderr"), "w") as err:
        rc = subprocess.call(cmd, cwd=record_dir, stdout=out, stderr=err)
    stderr_text = open(os.path.join(record_dir, "klt-sim.stderr")).read()
    sys.stderr.write(stderr_text)
    if a.dry_run:
        print(f"{slug}_envelope: --dry-run (exit {rc}); scratch record {record_dir} "
              "is NOT evidence -- delete it by hand.", file=sys.stderr)
        return rc

    prov = {
        "record_id": rid,
        "probe": bool(a.probe),
        "git_sha": sha7,
        "invocation": invocation_fmt.format(probe=" --probe" if a.probe else ""),
        "klt_sim_exit": rc,
        "klt_sim_argv": " ".join(cmd),
        "substitutions": subs,
        "pdk": PDK,
        "pdk_root": pdk_root,
        "pdk_pin": PDK_PIN,
        "batch_job_ids": sorted(set(re.findall(r"klt-sim-[0-9a-f]+", stderr_text))),
        PDK_PIN_PROJECTION_FIELD: pdk_pin_projection_sha256(),
    }
    prov.update(prov_extra(rid, bool(a.probe)))
    with open(os.path.join(record_dir, "provenance.json"), "w") as f:
        json.dump(prov, f, indent=1, sort_keys=True)
        f.write("\n")

    files, summ = summary_files_fn(record_dir)
    write_or_check(record_dir, files, check=False)
    if post_fn is not None:
        post_fn(record_dir)
    print(json.dumps(summ, indent=1, sort_keys=True))
    if not summ["definitive"] and not a.probe:
        print(f"{slug}_envelope: NOT definitive -- this record must not be cited "
              "as row evidence. Read the record's summary and report.json's "
              "diagnostics.", file=sys.stderr)
        return rc or 1
    return rc


# --------------------------------------------------------------------------- #
# offline record checks (steps 1-4 of `check`; the row-specific citation
# rules stay in each driver)
# --------------------------------------------------------------------------- #

def check_request_and_summary(record_dir, rid, problems, *, slug,
                              request_files_fn, template_rel, summary_files_fn):
    """Steps 1-2: the request reproduces byte-for-byte from the template plus
    the recorded substitutions, and the summary files reproduce from
    report.json + provenance.json."""
    prov = json.load(open(os.path.join(record_dir, "provenance.json")))
    cs = coords(prov.get("probe", False))
    template_text = open(os.path.join(REPO, template_rel)).read()
    want = request_files_fn(prov["substitutions"], cs, template_text)
    problems += [f"{rid}: request {b}"
                 for b in write_or_check(record_dir, want, check=True)]
    try:
        files, summ = summary_files_fn(record_dir)
    except FileNotFoundError as exc:
        problems.append(f"{rid}: {exc}")
        return None, prov
    problems += [f"{rid}: summary {b}"
                 for b in write_or_check(record_dir, files, check=True)]
    return summ, prov


def check_hash_pins(record_dir, rid, problems, *, slug, tail):
    """Step 3: the envelope's recorded input hash is the committed tb.spice,
    its models-lib hash is the committed corners.lib, and the report's
    netlist names THIS record's tb.spice."""
    report = json.load(open(os.path.join(record_dir, "report.json")))
    tb = sha256_file(os.path.join(record_dir, "tb.spice"))
    lib = sha256_file(os.path.join(record_dir, "corners.lib"))
    got = ((report.get("provenance") or {}).get("input") or {}).get("content_hash")
    if got != "sha256:" + tb:
        problems.append(f"{rid}: envelope provenance.input.content_hash {got} != "
                        f"sha256 of the committed tb.spice (sha256:{tb})")
    # `klt sim` records `netlist` either as the request's own relative string
    # or, when it resolves inside the repo, as {"path": <repo-relative>,
    # "scope": "repo"}. Either way it must name THIS record's tb.spice -- that
    # is the file the signoff grader re-hashes.
    nl = report.get("netlist")
    nl_path = nl.get("path") if isinstance(nl, dict) else nl
    if nl_path != "tb.spice" and not str(nl_path).endswith(tail):
        problems.append(f"{rid}: envelope netlist is {nl_path!r}, "
                        f"neither 'tb.spice' nor a path ending {tail!r}")
    env_lib = (report.get("environment") or {}).get("models_lib_sha256")
    if env_lib != lib:
        problems.append(f"{rid}: envelope models_lib_sha256 {env_lib} != "
                        f"sha256 of the committed corners.lib ({lib})")


def corner_shape_ok(corner, step_names, graded):
    """True iff this reported corner ran each expected named step exactly once
    (all `ok`) and carries each graded measurement exactly once.

    Counting steps (`len(steps) == 6`) is not enough: six repeats of one step
    satisfy it while five of the six operating points never ran, and a graded
    figure resolved from a dict of measurements silently hides a repeat.
    """
    steps = corner.get("steps", [])
    names = [s.get("name") for s in steps]
    if sorted(n for n in names if isinstance(n, str)) != sorted(step_names) \
            or len(names) != len(step_names):
        return False
    if any(s.get("status") != "ok" for s in steps):
        return False
    mnames = [m.get("name") for m in corner.get("measurements", [])]
    return all(mnames.count(n) == 1 for n in graded)


def check_declared_gates(record_dir, rid, problems, *, measurements_fn,
                         graded, row_id, slug):
    """Step 4: the request the envelope was graded against still declares the
    limits and spec_row tags this driver says it does -- a relaxed gate or a
    dropped tag cannot hide in the record."""
    req = json.load(open(os.path.join(record_dir, "request.json")))
    report = json.load(open(os.path.join(record_dir, "report.json")))
    # Exactly once (review of #322): a dict comprehension below would collapse
    # a repeated declaration, and a report with a graded declaration removed
    # would simply never reach the per-measurement loop. Compare NAME LISTS.
    want_names = [m["name"] for m in measurements_fn()]
    req_names = [m["name"] for m in req["measurements"]]
    if sorted(req_names) != sorted(want_names):
        problems.append(f"{rid}: request declares measurements {sorted(req_names)}, "
                        f"expected each of {sorted(want_names)} exactly once")
    rep_names = [m.get("name") for m in report.get("measurements", [])
                 if m.get("name") in set(graded)]
    if sorted(rep_names) != sorted(graded):
        problems.append(f"{rid}: envelope declares graded measurements "
                        f"{sorted(rep_names)}, expected each of {sorted(graded)} "
                        "exactly once -- the fleet graded something else")
    declared = {m["name"]: m.get("limits") for m in req["measurements"]}
    expect = {m["name"]: m.get("limits") for m in measurements_fn()}
    if declared != expect:
        problems.append(f"{rid}: request limits {declared} != the row gates {expect}")
    tagged = {m["name"]: m.get("spec_row") for m in req["measurements"]}
    want_tags = {m["name"]: m.get("spec_row") for m in measurements_fn()}
    if tagged != want_tags:
        problems.append(f"{rid}: request spec_row tags {tagged} != {want_tags}")
    for m in report.get("measurements", []):
        if m["name"] in graded and m.get("limits") != expect[m["name"]]:
            problems.append(f"{rid}: envelope measurement {m['name']} graded against "
                            f"{m.get('limits')}, not {expect[m['name']]}")
        if m["name"] in graded and m.get("spec_row") != row_id:
            problems.append(f"{rid}: envelope measurement {m['name']} carries spec_row "
                            f"{m.get('spec_row')!r}, not {row_id!r}; the signoff grader "
                            "derives row coverage from this tag")
        if m["name"] not in graded and m.get("spec_row") is not None:
            problems.append(f"{rid}: ungraded measurement {m['name']} claims spec_row "
                            f"{m.get('spec_row')!r}; a row it does not grade must "
                            "not be claimed")


def stale_inputs(repo, root, rid, inputs):
    """Problems for a record whose recorded inputs no longer match the tree.

    Applied to the CITED record only: an older record describes the design as
    it was and is history, but a citation must describe the design as it is --
    the same freshness rule the signoff grader applies to its own pins.
    `repo`/`root` are parameters (not this module's own globals) so a driver's
    unit tests can point them at a throwaway copy.
    """
    prov = json.load(open(os.path.join(root, rid, "provenance.json")))
    out = []
    if PDK_PIN_PROJECTION_FIELD in prov:
        try:
            now = pdk_pin_projection_sha256(os.path.join(repo, PDK_PIN))
        except (OSError, ValueError) as e:
            out.append(f"cited record {rid}: {e}")
        else:
            want = prov[PDK_PIN_PROJECTION_FIELD]
            if now != want:
                out.append(f"cited record {rid}: PDK pin {PDK_PIN} changed in "
                           f"{'/'.join(PDK_PIN_KEYS)} since the run (recorded "
                           f"{want[:12]}..., tree {now[:12]}...); the citation is "
                           "stale -- re-run the driver's `submit` and re-pin")
    for rel, want in sorted(prov.get("input_sha256", {}).items()):
        path = os.path.join(repo, rel)
        if not os.path.exists(path):
            out.append(f"cited record {rid}: input {rel} no longer exists")
        elif sha256_file(path) != want:
            out.append(f"cited record {rid}: input {rel} changed since the run "
                       f"(recorded {want[:12]}..., tree {sha256_file(path)[:12]}...); "
                       "the citation is stale -- re-run the driver's `submit` "
                       "and re-pin")
    return out
