#!/usr/bin/env python3
"""Graded `klt sim` corner-matrix envelope for DR-0007 row 7, Iq (issue #317).

Row 7 ("Iq (excluding load) < 30 uA at no load and at full load") is **Open**:
it measured inside its target at every sampled corner of the legacy evidence
base (no-load `iq_a` 21.72-24.72 uA over 45 points) but had NO `klt sim`
envelope carrying `spec_row` tags, so even a ratified row could not be cited
for T1 item 5, and the full-load half existed only as an OFFLINE subtraction
of two ~50 mA currents printed to 9 significant digits -- quantized at 1e-10 A
with solver noise unbounded beyond that floor.

This bench closes both halves the only honest way:

  * the six graded Iq figures are `limits`-bearing measurements **inside the
    request** (max 30 uA, `spec_row: dr0007-row7-iq`), so the per-corner and
    whole-matrix verdict in report.json is `klt sim`'s own, and
  * the full-load difference is NOT computed by this repo: request.json
    declares six `analysis_steps[]` operating points -- one per (Vin, Iload)
    in {2.97, 3.30, 3.63} V x {0, 50 mA} (the row's whole supply window x
    both load states, 45 corners x 6 solves) -- each measuring the raw supply
    current `isup_a = abs(vin#branch)`; the graded
    `iq_fullload_<vin>_a = <vin>_i50m.isup_a - 0.05` is a DERIVED `expr`
    measurement klayout-tools #2482 builds for `klt sim` from the step's own
    vector, at full double precision inside ngspice.  (Row 4's `.meas WHEN`
    literal-threshold gap does not apply here: no `.meas` card references
    another measurement's result; the derived-expr form is the documented,
    supported expression of a combination-of-solves quantity.)

Solver convergence setting vs. observed solver sensitivity (stated in every
record's summary; the two are different things and are never conflated):

  * CONVERGENCE SETTING.  The request pins `.options reltol=1e-9
    abstol=1e-15` (`options.ngspice_options`, echoed as
    `environment.ngspice_options`).  ngspice's stopping test compares each new
    branch-current iterate with the PREVIOUS iterate
    (`reltol * max(|new|, |old|) + abstol`); it supplies NO bound on the
    distance from the exact operating point.  The figure
    `reltol*(Iload + target) + abstol ~= 5.1e-11 A` is therefore only the
    stopping threshold of that test -- a setting, not an error bound.
  * OBSERVED SENSITIVITY.  What the evidence can honestly say is measured: a
    second, paired record (`--profile tight-... --pair-of <base>`) re-runs
    the whole 45-corner x 6-measurement grid at tighter tolerances, and
    `row7-pair.json` in that record reports the largest observed change
    between the two solves, where it occurred and its coverage.  That is an
    observation over those 270 pairs, not a guarantee.

`ngspice_init` pins `numdgt=12` so the printed values carry 12 digits, ~1e-17 A
quantization.

Iq definition (the same quantity the legacy evidence base measured as
`iq_a`): |i(VIN)| minus the load current -- the core's quiescent current
including the 2 uA mirror-reference leg sunk through the ideal IBIAS source
and the feedback divider's standing current, excluding the load.  Disclosure
this evidence must be read with (stated in every summary, and re-verified by
`sim/characterization/generate.py`): the ideal 0.90 V reference and the ideal
2 uA IBIAS sink mean NO on-chip reference- or bias-generator current is
included -- their blocks do not exist in this bench -- and the evidence is
for the core WITHOUT the #190 current limiter.  Schematic level, corner grid
only, no Monte Carlo (DR-0007 classifies the row deterministic).

The row stays Open: ratification is `spec/` + `ratification/` work (#318),
never a `signoff/` edit.  `klt signoff` item 5 derives coverage from
`spec_row` tags, so this envelope CANNOT turn the row covered while the
manifest declares `ratified: false` -- the tags exist so ratification, when
it happens, has an envelope to cite.

The row-agnostic half of this bench lives in `row_envelope.py` (shared with
`row4_envelope.py`, issue #317).  This driver owns the measurements,
thresholds, summary text and the characterization-side selection rules.

    row7_envelope.py submit                 # mint a new record, run it on the
                                            # EDA batch fleet, write the envelope
    row7_envelope.py submit --probe         # the same, 2 corners (never cited)
    row7_envelope.py submit --dry-run       # build the request dir and validate it
    row7_envelope.py check                  # offline, stdlib-only (CI): every
                                            # committed record reproduces and
                                            # self-verifies
    row7_envelope.py summarise <record-id>  # rewrite that record's summary files

`check` binds BOTH selections this record set carries: the item-8
characterization selection (sim/characterization/selection.json, kept fresh,
its pair evidence included) and the signoff manifest's item-5 row7-envelope
member -- when #318's citation lands it must name a committed, definitive,
non-probe, STANDARD-solver-profile record whose tb.spice hashes to the
manifest's content_hash and whose recorded inputs are fresh (the shared
row-4 contract plus the profile rule, row_envelope.cited_item5_record
#358; the tight-tolerance pair's tb.spice is byte-identical to the standard
matrix's, so the profile is the only offline handle on it).  While item 5
has no row-7 member the check passes with the citation unresolved.

Append-only: `submit` mints a NEW timestamped record id and refuses to touch
an existing one.  SPICE never runs locally here -- this is a 270-solve grid
and dispatch hosts submit grids to the fleet (CLAUDE.md host rules).
"""
import json
import os
import sys

import row_envelope as re_

HERE = re_.HERE
REPO = re_.REPO
TEMPLATE = "sim/ldo-cmos5l-pvt-sweep/testbench/tb_row7_envelope_cmos5l.spice.tmpl"
DESIGN_NETLIST = "design/sg13cmos5l/netlist/ldo_core_cmos5l.spice"
ROOT = os.path.join(HERE, "row7-envelope")

# DR-0007 row 7, verbatim: "Iq (excluding load)  < 30 uA at no load and at
# full load".  Graded at the full Input row supply window, both load states.
VINS = [("v2v97", 2.97), ("v3v30", 3.30), ("v3v63", 3.63)]
LOADS = [("i0", 0.0), ("i50m", 0.050)]
TARGET_IQ_A = 30e-6
LOAD_A = 0.050

# The spec-row id this envelope's graded measurements are tagged with.  Must
# match the manifest's spec_rows["5"] entry for row 7 (ratified: false).
ROW7_ID = "dr0007-row7-iq"

# The numerical-noise bound machinery (see this module's header): tolerances
# pinned in the request, and the analytic bound they give for the difference.
NGSPICE_OPTIONS = {"reltol": 1e-9, "abstol": 1e-15}
# Tighter-tolerance profiles of paired records (`submit --profile NAME
# --pair-of BASE`). Names are part of the record: a profile's options never
# change under its name. `tight-1e-12` was tried first and does NOT converge
# on the grid (the committed history record shows 43 of 45 corners erroring in
# dynamic gmin stepping); `tight-1e-11` converged on 40 of 45 corners. Both
# stay committed as history. The cited pair is the tightest profile that
# resolves the whole grid.
PROFILES = {
    "standard": NGSPICE_OPTIONS,
    "tight-1e-12": {"reltol": 1e-12, "abstol": 1e-17},
    "tight-1e-11": {"reltol": 1e-11, "abstol": 1e-16},
    "tight-1e-10": {"reltol": 1e-10, "abstol": 1e-15},
}
TIGHT_PROFILES = sorted(k for k in PROFILES if k != "standard")
NGSPICE_INIT = ["set numdgt=12"]
# ngspice's stopping threshold for the supply-current iterate at the row's
# largest current: a CONVERGENCE SETTING, explicitly NOT an error bound (the
# test compares successive iterates, not the distance to the exact solution).
CONVERGENCE_SETTING_A = NGSPICE_OPTIONS["reltol"] * (LOAD_A + TARGET_IQ_A) \
    + NGSPICE_OPTIONS["abstol"]          # ~5.1e-11 A, stated per record
PAIR_FILE = "row7-pair.json"

# Re-exported grid constants: one 45-point PVT grid, one spelling.
MOS = re_.MOS
RES = re_.RES
CAP = re_.CAP
TEMPS = re_.TEMPS
N_EXPECTED = re_.N_EXPECTED
PROBE_COORDS = re_.PROBE_COORDS
PDK = re_.PDK
PDK_PIN = re_.PDK_PIN
Error = re_.Error

INPUTS = [TEMPLATE, DESIGN_NETLIST,
          "design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice",
          "sim/tools/render_deck.py"]

# The corners.lib header. Byte-critical: the first line names THIS driver and
# the fleet report pins those bytes (row_envelope.py's header explains why).
HEADER_LINES = [
    "* generated by sim/ldo-cmos5l-pvt-sweep/row7_envelope.py:",
]

# The six graded measurement names (no-load and full-load at each Vin). The
# step-supply measurement they are derived from (`isup_a`, reported ungraded,
# inspectable per corner in report.json) is named inside analysis_steps().
GRADED = [f"iq_{ln}_{vn}_a" for vn, _ in VINS for ln, _ in LOADS]

coords = re_.coords
section_of = re_.section_of
corner_id = re_.corner_id
sha256_file = re_.sha256_file
resolve_env = re_.resolve_env
write_or_check = re_.write_or_check
echoed_options_match = re_.echoed_options_match
f9 = re_.f9


def pdk_pin_projection_sha256(path=None):
    return re_.pdk_pin_projection_sha256(path or os.path.join(REPO, PDK_PIN))


def records(root=None):
    return re_.records(root or ROOT)


def analysis_steps():
    """One operating point per (Vin, Iload); each step ALTERs both sources, so
    the cumulative-alter semantics of `analysis_steps[]` land every step at
    exactly its own bias independent of the steps before it."""
    steps = []
    for vn, vv in VINS:
        for ln, lv in LOADS:
            steps.append({
                "name": f"{vn}_{ln}",
                "analysis": {"kind": "op", "args": ""},
                "alter": {"Vin": vv, "Iload": lv},
                "measurements": [
                    # Reported, deliberately ungraded and untagged: the raw
                    # supply current each solve measured, kept inspectable so
                    # the graded differences can be re-derived by hand.
                    {"name": "isup_a", "expr": "abs(vin#branch)", "unit": "A"},
                ],
            })
    return steps


def measurements():
    """The six graded Iq figures: derived exprs over the step results, each
    carrying the row target as `limits` and the row id as its `spec_row`
    tag.  The full-load subtraction is inside the expression -- klt sim
    grades the difference itself; no repo Python computes a verdict."""
    out = []
    for vn, vv in VINS:
        out.append({"name": f"iq_i0_{vn}_a",
                    "expr": f"{vn}_i0.isup_a",
                    "unit": "A",
                    "limits": {"max": TARGET_IQ_A},
                    "spec_row": ROW7_ID})
        out.append({"name": f"iq_i50m_{vn}_a",
                    "expr": f"{vn}_i50m.isup_a - {LOAD_A}",
                    "unit": "A",
                    "limits": {"max": TARGET_IQ_A},
                    "spec_row": ROW7_ID})
    return out


def request_obj(osdi_dir, cs, profile="standard"):
    return re_.request_skeleton(
        cs, "analysis_steps", analysis_steps(), measurements(), osdi_dir,
        extra_options={"ngspice_options": dict(PROFILES[profile]),
                       "ngspice_init": list(NGSPICE_INIT)},
        timeout_s=600)


def request_files(subs, cs, template_text, profile="standard"):
    """The three request-dir files, as {name: text}. Deterministic."""
    return re_.request_files(subs, cs, template_text, HEADER_LINES,
                             lambda osdi, c: request_obj(osdi, c, profile))


def design_netlist_include(depth):
    return re_.design_netlist_include(depth, DESIGN_NETLIST)


# --------------------------------------------------------------------------- #
# summary (pure: report.json + provenance.json -> bytes)
# --------------------------------------------------------------------------- #

STEP_NAMES = [s["name"] for s in analysis_steps()]


def summarise_report(report, prov):
    summ, points, base = re_.summarise_corners(
        report, prov, graded=GRADED, step_names=STEP_NAMES,
        target_of=lambda n: TARGET_IQ_A)
    resolved = {n: [p for p in points if p[n] is not None] for n in GRADED}

    def worst(names):
        pool = [(p[n], n, p) for p in points for n in names if p[n] is not None]
        if not pool:
            return None
        v, n, p = max(pool, key=lambda t: (t[0], t[2]["corner_id"]))
        return {"corner_id": p["corner_id"], "mos": p["mos"], "temp_c": p["temp_c"],
                "res_section": p["res_section"], "measurement": n,
                "iq_ua": v * 1e6, "iq_a": v}

    noload_names = [n for n in GRADED if "_i0_" in n]
    fullload_names = [n for n in GRADED if "_i50m_" in n]
    noload_names = [n for n in GRADED if "_i0_" in n]
    fullload_names = [n for n in GRADED if "_i50m_" in n]
    w_nl, w_fl = worst(noload_names), worst(fullload_names)
    summ.update({
        "solver_profile": prov.get("solver_profile", "standard"),
        "target_iq_ua": TARGET_IQ_A * 1e6,
        "iq_definition": "|i(VIN)| - Iload per (Vin, Iload) operating point; the "
                         "same quantity the legacy evidence base recorded as iq_a "
                         "(includes the 2 uA mirror-reference leg and the divider "
                         "standing current, excludes the load)",
        "exclusions": [
            "ideal 0.90 V reference: no on-chip reference-generator current is included",
            "ideal 2 uA IBIAS sink: no on-chip bias-generator current is included "
            "(the sunk 2 uA itself flows through the core and IS included)",
            "evidence is for the core WITHOUT the #190 current limiter",
            "schematic level, corner grid only, no Monte Carlo (DR-0007 classifies "
            "the row deterministic)",
        ],
        "solver_convergence_setting_a": CONVERGENCE_SETTING_A,
        "solver_convergence_setting_note": "NOT an error bound. The request pins "
            f".options reltol/abstol of the '{prov.get('solver_profile', 'standard')}' "
            "profile; ngspice's stopping test compares each iterate with the "
            "previous one and bounds nothing about the distance to the exact "
            "operating point. For the standard profile (reltol=1e-9 "
            f"abstol=1e-15) the threshold at the largest current is "
            f"~{CONVERGENCE_SETTING_A:.3g} A "
            f"({CONVERGENCE_SETTING_A/TARGET_IQ_A*100:.4f} % of the 30 uA limit). "
            "Full-load Iq is graded as a derived expr inside ngspice "
            "(klt sim analysis_steps, klayout-tools #2482), never as an offline "
            "subtraction. The observed change under tighter tolerances is a "
            "separate, measured quantity: see the paired record's row7-pair.json",
    })
    if w_nl:
        summ["worst_noload"] = w_nl
        summ["margin_noload_ua"] = TARGET_IQ_A * 1e6 - w_nl["iq_ua"]
    if w_fl:
        summ["worst_fullload"] = w_fl
        summ["margin_fullload_ua"] = TARGET_IQ_A * 1e6 - w_fl["iq_ua"]
    summ["definitive"] = bool(base and all(len(resolved[n]) == N_EXPECTED for n in GRADED))
    return summ, points


def summary_md(summ, points, prov):
    rid = summ["record_id"]
    L = [f"# Row-7 graded `klt sim` corner-matrix envelope `{rid}`", "",
         "DR-0007 row 7, **Iq (excluding load) < 30 uA at no load and at full "
         "load** -- an Open row of the target spec. The verdict below is `klt "
         "sim`'s own: all six graded measurements carry `limits` in "
         "`request.json`, so each corner's pass/fail and the matrix verdict "
         "(`status`) are computed by the tool, not by this repo.", "",
         "Measurement definition: " + summ["iq_definition"] + ". Graded over the "
         "full Input-row supply window at both load states -- six "
         "`analysis_steps[]` operating points per corner (Vin 2.97 / 3.30 / "
         "3.63 V x Iload 0 / 50 mA), the graded figures derived `expr` "
         "measurements over each step's raw supply current.", ""]
    if summ["probe"]:
        L += ["> **PROBE RECORD.** A capacity / toolchain probe over "
              f"{summ['n_expected']} coordinates, never cited as row evidence.", ""]
    L += [f"- Corners: {summ['n_corners_reported']}/{summ['n_expected']} reported, "
          f"every coordinate exactly once: {summ['coordinates_exactly_once']}; "
          f"all six steps ok at every reported corner: "
          f"{all(p['steps_all_ok'] for p in points)}.",
          f"- Envelope `status`: **{summ['envelope_status']}** "
          f"(passed {summ['passed']}, failed {summ['failed']}, errored "
          f"{summ['errored']}, inconclusive {summ['inconclusive']}).",
          f"- Corner status counts: {summ['corner_status_counts']}; "
          f"error-severity diagnostics: {summ['error_diagnostics_total']}.",
          f"- Graded measurements (`coverage.measurements_with_limits` = "
          f"{summ['measurements_with_limits']}): {len(GRADED)} Iq figures, all "
          f"tagged `{ROW7_ID}`; all pass: {summ['all_graded_measurements_pass']}."]
    if "worst_noload" in summ:
        w = summ["worst_noload"]
        L += ["",
              f"- Worst no-load Iq: {w['iq_ua']:.4f} uA (`{w['measurement']}`, "
              f"`{w['mos']}` / {w['temp_c']} C / `{w['res_section']}`); margin to "
              f"the 30 uA target: {summ['margin_noload_ua']:.4f} uA."]
    if "worst_fullload" in summ:
        w = summ["worst_fullload"]
        L += [f"- Worst full-load Iq: {w['iq_ua']:.4f} uA (`{w['measurement']}`, "
              f"`{w['mos']}` / {w['temp_c']} C / `{w['res_section']}`); margin to "
              f"the 30 uA target: {summ['margin_fullload_ua']:.4f} uA."]
    L += [f"- Definitive matrix claim permitted: **{summ['definitive']}** (requires "
          f"the whole {N_EXPECTED}-coordinate matrix reported, every step ok, "
          "resolved, graded and clean).",
          "",
          "## Solver convergence setting (not an error bound)", "",
          summ["solver_convergence_setting_note"] + ". The step supply currents are "
          "reported ungraded per corner in `report.json`, so every graded "
          "difference can be re-derived by hand.", "",
          "## Exclusions this evidence must be read with", ""]
    for e in summ["exclusions"]:
        L.append(f"- {e}")
    L += ["", "The row stays Open under DR-0007; ratification is `spec/` + "
          "`ratification/` work (#318), never a `signoff/` edit. This envelope "
          "exists so a ratified row has a tagged, limited, tool-graded matrix "
          "to cite.", "",
          "## Per-corner", "",
          "| corner | status | " + " | ".join(f"{n} (uA)" for n in GRADED) + " |",
          "|---|---|" + "---|" * len(GRADED)]
    for p in points:
        cells = [f"`{p['corner_id']}`", str(p['corner_status'])]
        for n in GRADED:
            v = p[n]
            cells.append(" " if v is None else f"{v*1e6:.4f}")
        L.append("| " + " | ".join(cells) + " |")
    L += ["", "## Provenance", ""]
    for k, v in sorted(prov.items()):
        if k == "input_sha256":
            continue
        L.append(f"- {k}: `{json.dumps(v, sort_keys=True)}`" if isinstance(v, (dict, list))
                 else f"- {k}: {v}")
    L += ["", "Input sha256:", ""]
    for k, v in sorted(prov.get("input_sha256", {}).items()):
        L.append(f"- `{k}`: `{v}`")
    L += ["", f"Machine summary: `row7-envelope.json`; the graded envelope itself: "
          f"`report.json`; the request that produced it: `request.json`, `tb.spice`, "
          f"`corners.lib`.", ""]
    return "\n".join(L)


def summary_files(record_dir):
    return re_.summary_files(record_dir, "row7", summarise_report, summary_md)


# --------------------------------------------------------------------------- #
# submit / summarise / check
# --------------------------------------------------------------------------- #

def pair_summary(base_dir, tight_dir):
    """Observed change between the standard- and tight-tolerance solves of the
    SAME grid: for every (corner, graded measurement) pair, |tight - base|.

    An observation over exactly the pairs it counts -- never a bound.  The two
    records must differ in `ngspice_options` and nothing else (same request
    otherwise, same recorded input hashes, same PDK pin projection)."""
    def load(d, name):
        with open(os.path.join(d, name)) as f:
            return json.load(f)
    rb, rt = load(base_dir, "report.json"), load(tight_dir, "report.json")
    pb, pt = load(base_dir, "provenance.json"), load(tight_dir, "provenance.json")
    qb, qt = load(base_dir, "request.json"), load(tight_dir, "request.json")
    opts_b = (qb.get("options") or {}).get("ngspice_options")
    opts_t = (qt.get("options") or {}).get("ngspice_options")
    echo_ok = (echoed_options_match(rb, qb) and echoed_options_match(rt, qt))
    for q in (qb, qt):
        q["options"].pop("ngspice_options", None)
    identical = (qb == qt
                 and pb.get("input_sha256") == pt.get("input_sha256")
                 and pb.get("pdk_pin_projection_sha256") == pt.get("pdk_pin_projection_sha256"))

    def values(report):
        out, dup = {}, 0
        for c in report.get("corners", []):
            for m in c.get("measurements", []):
                if m.get("name") in GRADED and isinstance(m.get("value"), (int, float)):
                    k = (c.get("corner_id"), m["name"])
                    dup += k in out
                    out[k] = m["value"]
        return out, dup
    vb, dup_b = values(rb)
    vt, dup_t = values(rt)
    keys = sorted(set(vb) & set(vt))
    deltas = [(abs(vt[k] - vb[k]), k) for k in keys]
    by_meas = {}
    for d, (cid, n) in deltas:
        by_meas[n] = max(by_meas.get(n, 0.0), d)
    worst = max(deltas, default=(None, None))
    expected = N_EXPECTED * len(GRADED)
    out = {
        "base_record": pb.get("record_id"),
        "tight_record": pt.get("record_id"),
        "base_options": opts_b,
        "tight_options": opts_t,
        "requests_and_inputs_identical_except_options": bool(identical),
        "pairs_expected": expected,
        "pairs_compared": len(keys),
        "duplicate_values_seen": dup_b + dup_t,
        "coverage": f"{len(keys)} of {expected} (corner, graded measurement) pairs "
                    f"over {len({k[0] for k in keys})} of {N_EXPECTED} corners",
        "max_abs_delta_a": worst[0],
        "max_abs_delta_ua": None if worst[0] is None else worst[0] * 1e6,
        "max_abs_delta_fraction_of_limit": None if worst[0] is None
                                          else worst[0] / TARGET_IQ_A,
        "worst_pair": None if worst[1] is None else
                      {"corner_id": worst[1][0], "measurement": worst[1][1],
                       "base_a": vb[worst[1]], "tight_a": vt[worst[1]]},
        "max_abs_delta_a_by_measurement": dict(sorted(by_meas.items())),
        "interpretation": "Observed change between two solves of the same "
                          "request at the stated tolerances, over the pairs "
                          "counted above. It is an observation, not a bound on "
                          "the distance to the exact operating point, and it is "
                          "NOT the convergence setting recorded in the summary.",
    }
    prof = pt.get("solver_profile")
    out["tight_profile"] = prof
    out["complete"] = bool(identical and echo_ok and len(keys) == expected
                           and not out["duplicate_values_seen"]
                           and prof in TIGHT_PROFILES
                           and opts_b == NGSPICE_OPTIONS and opts_t == PROFILES[prof])
    return out


def pair_files(tight_dir, base_id):
    base_dir = os.path.join(ROOT, base_id)
    if not os.path.isdir(base_dir):
        raise Error(f"no such base record: {base_dir}")
    return {PAIR_FILE: json.dumps(pair_summary(base_dir, tight_dir),
                                  indent=1, sort_keys=True) + "\n"}


def cmd_pair(a):
    record_dir = os.path.join(ROOT, a.record_id)
    prov = json.load(open(os.path.join(record_dir, "provenance.json")))
    if prov.get("solver_profile") not in TIGHT_PROFILES or not prov.get("pair_of"):
        raise Error(f"{a.record_id} is not a tight-profile record with pair_of")
    files = pair_files(record_dir, prov["pair_of"])
    bad = re_.write_or_check(record_dir, files, check=a.check)
    if bad:
        raise Error("pair file stale or missing: " + ", ".join(bad))
    print(files[PAIR_FILE], end="")
    return 0


def cmd_submit(a):
    profile = a.profile
    tight = profile != "standard"
    if tight and (a.probe or not a.pair_of
                  or not os.path.isdir(os.path.join(ROOT, a.pair_of))):
        raise Error("a tight --profile needs --pair-of <existing full-matrix "
                    "standard record id> and is never a probe")
    if a.pair_of and not tight:
        raise Error("--pair-of only applies to a tight --profile")

    def prov_extra(rid, probe):
        extra = {
            "spec_row": "DR-0007 row 7 (Iq excluding load < 30 uA at no load and "
                        "at full load) -- Open; this envelope does not ratify it",
            "measurement_definition": "Iq = |i(VIN)| - Iload per (Vin, Iload) "
                                      "operating point; graded as klt sim derived "
                                      "expr measurements over analysis_steps "
                                      "(klayout-tools #2482), never computed by "
                                      "repo Python",
            "solver_profile": profile,
            "solver_options": dict(PROFILES[profile]),
            "solver_convergence_setting_a": CONVERGENCE_SETTING_A,
            "input_sha256": {p: sha256_file(os.path.join(REPO, p)) for p in INPUTS},
        }
        if tight:
            extra["pair_of"] = a.pair_of
        return extra
    inv = "python3 sim/ldo-cmos5l-pvt-sweep/row7_envelope.py submit{probe}" \
        + (f" --profile {profile} --pair-of {a.pair_of}" if tight else "")
    def write_pair(record_dir):
        # This invocation's own record (post_fn gets the dir submit_record
        # minted), not records(ROOT)[-1]: a later/overlapping run must not
        # steal the comparison.
        if tight:
            re_.write_or_check(record_dir, pair_files(record_dir, a.pair_of),
                               check=False)
    rc = re_.submit_record(
        a, slug="row7", root=ROOT, template_rel=TEMPLATE,
        design_netlist_rel=DESIGN_NETLIST, header_lines=HEADER_LINES,
        request_files_fn=lambda subs, cs, t: request_files(subs, cs, t, profile),
        summary_files_fn=summary_files,
        invocation_fmt=inv, prov_extra=prov_extra, post_fn=write_pair)
    return rc


def cmd_summarise(a):
    return re_.summarise_cmd(a, ROOT, summary_files)


def check_record(rid, problems):
    record_dir = os.path.join(ROOT, rid)
    if not os.path.exists(os.path.join(record_dir, "provenance.json")):
        problems.append(f"{rid}: no provenance.json")
        return None
    prov = json.load(open(os.path.join(record_dir, "provenance.json")))
    profile = prov.get("solver_profile", "standard")
    if profile not in PROFILES:
        problems.append(f"{rid}: unknown solver_profile {profile!r}")
        return None
    summ, prov = re_.check_request_and_summary(
        record_dir, rid, problems, slug="row7",
        request_files_fn=lambda subs, cs, t: request_files(subs, cs, t, profile),
        template_rel=TEMPLATE, summary_files_fn=summary_files)
    re_.check_echoed_options(record_dir, rid, problems)
    re_.check_hash_pins(record_dir, rid, problems, slug="row7",
                        tail=f"row7-envelope/{rid}/tb.spice")
    re_.check_declared_gates(record_dir, rid, problems,
                             measurements_fn=measurements, graded=GRADED,
                             row_id=ROW7_ID, slug="row7")
    if profile in TIGHT_PROFILES:
        base = prov.get("pair_of")
        if not base or not os.path.isdir(os.path.join(ROOT, base)):
            problems.append(f"{rid}: tight record's pair_of {base!r} is not a "
                            "committed record")
        else:
            try:
                want = pair_files(record_dir, base)
            except (OSError, ValueError, KeyError) as exc:
                problems.append(f"{rid}: cannot build the paired comparison: {exc}")
            else:
                problems += [f"{rid}: pair {b}" for b in
                             re_.write_or_check(record_dir, want, check=True)]
                # An incomplete pair is legitimate HISTORY (a profile that did
                # not converge stays committed); it is only an error for the
                # pair that selection.json cites (see cmd_check).
    return summ


def selected_record():
    """The record id sim/characterization/selection.json cites for row 7."""
    return re_.selected_record(REPO, "row7_envelope_evidence")


def cited_pair_record():
    sel = json.load(open(os.path.join(REPO, "sim", "characterization", "selection.json")))
    pe = (sel.get("row7_envelope_evidence") or {}).get("pair_evidence") or {}
    return pe.get("tight_record_id")


def cited_record():
    """(record_id, pinned content_hash) from signoff/sg13g2-ldo.json item 5's
    row7-envelope member, or (None, None) while item 5 cites no row-7 record
    (#318's edit, not this driver's; `check` passes unresolved before it and
    enforces it after). The shared row-4 contract applies
    (row_envelope.cited_item5_record, #358) PLUS the standard-profile rule:
    the tight-tolerance pair's tb.spice is byte-identical to the standard
    matrix's (its tolerances live in request.json), definitive and all, so
    cmd_check additionally refuses a citation whose provenance carries any
    solver_profile other than 'standard'."""
    return re_.cited_item5_record(REPO, ROOT, ROW7_ID, "row7")


def stale_inputs(rid):
    return re_.stale_inputs(REPO, ROOT, rid, INPUTS)


def cmd_check(a):
    problems = []
    rids = records(ROOT)
    if not rids:
        problems.append("no record under sim/ldo-cmos5l-pvt-sweep/row7-envelope/")
    summaries = {rid: check_record(rid, problems) for rid in rids}
    cited_pair = cited_pair_record()
    if cited_pair is not None:
        pf = os.path.join(ROOT, cited_pair, PAIR_FILE)
        if not os.path.exists(pf):
            problems.append(f"selection.json cites pair record {cited_pair} without "
                            f"a {PAIR_FILE}")
        else:
            with open(pf) as f:
                pdoc = json.load(f)
            if not pdoc.get("complete") or pdoc.get("base_record") != selected_record():
                problems.append(f"the cited pair {cited_pair} is incomplete or pairs "
                                f"{pdoc.get('base_record')}, not the cited record "
                                f"{selected_record()}")
            if not (summaries.get(cited_pair) or {}).get("definitive"):
                problems.append(f"the cited pair record {cited_pair} is not a "
                                "definitive matrix")
    # The cited record must describe the design and PDK as they are now.
    re_.check_selected_record(REPO, "row7_envelope_evidence", "row-7", summaries,
                              problems, stale_inputs)
    cited = re_.check_item5_citation(REPO, ROOT, ROW7_ID, "row7", summaries,
                                     problems, stale_inputs,
                                     require_standard_solver_profile=True)
    for p in problems:
        print("row7_envelope: " + p, file=sys.stderr)
    if problems:
        return 1
    n_def = sum(1 for s in summaries.values() if s and s["definitive"])
    print(f"row7_envelope: OK -- {len(rids)} record(s) reproduce and self-verify "
          f"({n_def} definitive). The row stays Open; the selected record for "
          "characterization is pinned in sim/characterization/selection.json"
          + (f"; signoff item 5 cites {cited}" if cited else ""))
    return 0


def _extra_args(sp, s):
    s.add_argument("--profile", choices=sorted(PROFILES), default="standard",
                   help="solver-tolerance profile; a tight one makes the paired "
                        "record that measures solver sensitivity")
    s.add_argument("--pair-of", metavar="RECORD_ID",
                   help="with a tight --profile: the standard record this one "
                        "is paired with")
    pr = sp.add_parser("pair", help="rewrite a tight record's row7-pair.json")
    pr.add_argument("record_id")
    pr.add_argument("--check", action="store_true")
    pr.set_defaults(fn=cmd_pair)


def main():
    return re_.run_cli(__doc__, "row7", cmd_submit, cmd_check, cmd_summarise,
                       add_extra_args=_extra_args)


if __name__ == "__main__":
    sys.exit(main())
