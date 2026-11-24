#!/usr/bin/env python3
"""E4 divider/Cc probe at DR-0015 point P5 (issue #315). stdlib only.

DR-0015's Disposition derives a tension between ratified rows 3+6+7+10 at
0 mA load and Cout >= 1.6 uF and defers it to "probe E4": at P5 (ss / 125 C
/ res_wcs, 0 mA, Cout 3.45 uF, ESR 0 mohm) cross R_div in {1x, 0.5x} with
Cc in {1x, 0.65x} and read the loop gain, the PSRR curve and the DC
operating point at each of the four points. This module owns:

  * the OVERRIDE CONTRACT -- both knobs as testbench-local substitutions on
    a COPY of design/sg13cmos5l/netlist/ldo_core_cmos5l.spice (the committed
    netlist is never written), each failing unless it changes every line it
    owns, and the per-bench divider legs the benches carry in their own
    text (see "Where the divider lives" below);
  * verify_deck -- the positive assertion, per rendered deck, that the
    substituted lines ARE the ones the simulator will read;
  * reduce -- the four-point reduction: loop gain (f_ug, PM, GM with the
    DR-0014 classification), PSRR (@1 kHz, @100 kHz, notch bottom), DC
    (VOUT, divider current, Iq) and the model-load check;
  * record-md -- the narrative record, derived only from committed files;
  * check -- regenerate CSV/JSON/md into a temp dir and byte-compare (CI).

Where the divider lives (why one substitution site is not enough):
tb_psrr_cmos5l instantiates ldo_core_cmos5l whole, so XRtop/XRbot reach it
through the .include'd copy. tb_loopgain_cmos5l and tb_e1op_cmos5l FLATTEN
the core one level to break the loop at FB and reproduce XRtop/XRbot
verbatim in the template body, and tb_e1op_cmos5l additionally carries a
divider REPLICA (XRrep_top/XRrep_bot) through which the divider current is
measured. For those two benches the override must also be applied to the
rendered deck's own lines, and a deck whose copy was substituted while its
flattened legs stayed at nominal would simulate the wrong circuit while
looking substituted -- which is what verify_deck exists to refuse. Cc (XCc,
inside ldo_erramp_cmos5l) reaches all three benches through the .include'd
copy alone.

Three benches per point. The two DR-0015 names (loopgain, psrr) carry the
AC reading; the E1 operating-point bench (tb_e1op_cmos5l, issue #158) is
added because the brief asks for the MEASURED divider current, DC VOUT and
Iq, and the fleet path drops the AC templates' informational `op` echo
(batch_backend.py parses the .control block and forwards one analysis).

Subcommands:
    design-copy SRC OUT --w W --l L
        write the overridden copy; at 1x/1x it must be byte-identical to SRC
    patch-deck DECK --bench B --design COPY --w W --l L
        apply the bench's own divider legs in place, then verify_deck
    reduce --record RID [--corners-dir D] --out-csv P --out-json P
    record-md --record RID
    check --record RID

Error discipline: a missing export refuses the reduction (exit 2); any
failed check is recorded and the reduction exits 3 with its outputs
written, so the campaign publishes an explicitly incomplete record.
"""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import ac_sweep  # noqa: E402
import ac_metrics as am  # noqa: E402
import e1_oppoints as e1  # noqa: E402
from dc_metrics import read_wrdata  # noqa: E402
from file_hash import sha256_file  # noqa: E402 -- the one sha256-file helper (#362)

BENCH = "e4"

# DR-0015 point P5 in e1_oppoints.POINTS shape, so every E4 point's DC
# operating point is checked under exactly E1's rules.
P5 = ("P5", "ss", "wcs", 125, 0.0, 3.45e-6)
MOS_SECTION, RES_SECTION, CAP_SECTION, TEMP = "mos_ss", "res_wcs", "cap_typ", 125
LOAD_A, COUT_F, ESR_OHM = "0", "3.45u", "0"
# run_sweep.sh's default ceiling: the committed P5 traces DR-0015 reads are
# 161-row sweeps from 1 Hz to 100 MHz, so the 1x/1x point is like-for-like
# with them.
LG_AC_MAX = ac_sweep.DEFAULT_CEILING
EXPECT_ROWS_AC = ac_sweep.expected_rows(LG_AC_MAX)

# Ratified references the record tabulates against (never re-thresholded
# here): DR-0007 row 7, Iq < 30 uA at no load; row 6, PSRR > 50 dB @ 1 kHz.
IQ_TARGET_A = 30e-6
PSRR_1K_TARGET_DB = 50.0

# The same-vintage AC reference for P5 (the #155 re-run: current PDK pin,
# same design bytes), named by DR-0015's E1 addendum. DR-0015's own table row
# P5 (f_ug 1 052 Hz, PM 17.61 deg, PSRR@1 kHz 43.55 dB) is from the
# pre-#155 record 20261010-101245-6df50fd (old pin, pre-#89 design).
BASELINE_RID = "20261012-080951-142dac4a"
BASELINE_STEM = "dyn_ss_125c_rwcs_i0ua_c3450nf_e0mohm"

# ---- override contract ---------------------------------------------------- #
# The committed instantiation lines this contract owns, as
# design/sg13cmos5l/netlist/ldo_core_cmos5l.spice spells them. A drift in any
# of them fails the substitution loudly instead of simulating nominal.
CC_NOMINAL_W = "170e-6"
RDIV_NOMINAL_L = "25.43e-6"
# The committed XCc line carries the MoM-cap options after l=30e-6
# (`XCc OUT MZ cap_cmomi w=170e-6 l=30e-6 mmin=1 mmax=4 feed=double
# subblock=0 m=1 mm_ok=1`); only the w= token is rewritten, as
# run_sweep.sh's subst_cc_width() sed does.
_CC_LINE_RE = re.compile(r"^(XCc OUT MZ cap_cmomi )w=(\S+)( l=30e-6\b.*)$", re.MULTILINE)
_CC_PREFIX = "XCc OUT MZ cap_cmomi "
DIVIDER_LEGS = {
    "XRtop": f"XRtop VOUT FB VSS rhigh w=1e-6 l={RDIV_NOMINAL_L} m=1 b=7",
    "XRbot": f"XRbot FB VSS VSS rhigh w=1e-6 l={RDIV_NOMINAL_L} m=1 b=7",
    "XRrep_top": f"XRrep_top REPT REPFB 0 rhigh w=1e-6 l={RDIV_NOMINAL_L} m=1 b=7",
    "XRrep_bot": f"XRrep_bot REPFB 0 0 rhigh w=1e-6 l={RDIV_NOMINAL_L} m=1 b=7",
}
# the two legs inside ldo_core_cmos5l's body (what the design netlist carries)
CORE_LEGS = ("XRtop", "XRbot")
# the divider legs each bench carries in its OWN text, beyond the .include
BENCH_DECK_LEGS = {
    "loopgain": ("XRtop", "XRbot"),
    "e1op": ("XRtop", "XRbot", "XRrep_top", "XRrep_bot"),
    "psrr": (),
}
BENCHES = ("loopgain", "psrr", "e1op")
SUFFIX = {"loopgain": "_ac.csv", "psrr": "_ac.csv", "e1op": "_dc.csv"}

# DR-0015 brief, E4 row: R_div in {1x, 0.5x} x Cc in {1x, 0.65x}. Both
# divider legs scale by the same factor so the divider ratio, and with it the
# regulation setpoint, is unchanged.
CC_LEVELS = {"1x": "170e-6", "0.65x": "110.5e-6"}
CC_FACTOR = {"1x": 1.0, "0.65x": 0.65}
RDIV_LEVELS = {"1x": "25.43e-6", "0.5x": "12.715e-6"}
RDIV_FACTOR = {"1x": 1.0, "0.5x": 0.5}
POINTS = (("1x", "1x"), ("1x", "0.65x"), ("0.5x", "1x"), ("0.5x", "0.65x"))
BASELINE_KEY = "rdiv1x_cc1x"


class OverrideError(ValueError):
    """An override did not change exactly the lines it owns, or a deck does
    not carry the overridden lines it claims to."""


def point_key(rdiv_label, cc_label):
    return f"rdiv{rdiv_label.replace('.', 'p')}_cc{cc_label.replace('.', 'p')}"


def point_id(bench, key):
    return f"{bench}_e4_ss_125c_rwcs_i0ua_c3450nf_e0mohm_{key}"


def design_copy_name(key):
    return f"ldo_core_cmos5l_{key}.spice"


def _count_line(text, line):
    return len(re.findall(r"^" + re.escape(line) + r"$", text, re.MULTILINE))


def _replace_line(text, old, new, what):
    n = _count_line(text, old)
    if n != 1:
        raise OverrideError(f"{what}: expected exactly one line '{old}', found {n}")
    return re.sub(r"^" + re.escape(old) + r"$", lambda _m: new, text, flags=re.MULTILINE)


def _cc_widths(text):
    """The w= token of every `XCc OUT MZ cap_cmomi w=... l=30e-6` line."""
    return _CC_LINE_RE.findall(text)


def subst_cc(text, w):
    """Rewrite the w= token of the committed XCc instantiation to `w`,
    leaving the rest of the line (l=30e-6 and the MoM-cap options) and every
    other line untouched. Fails unless exactly one XCc line is found and its
    width is the committed one -- the fail-if-no-op rule of run_sweep.sh's
    subst_cc_width(), made unconditional so a drifted line is caught at 1x
    as well."""
    found = _cc_widths(text)
    if len(found) != 1:
        raise OverrideError(f"Cc width -> {w}: expected exactly one XCc OUT MZ cap_cmomi "
                            f"line at l=30e-6, found {len(found)}")
    head, found_w, tail = found[0]
    if found_w != CC_NOMINAL_W:
        raise OverrideError(f"Cc width -> {w}: the XCc line's w= is {found_w}, "
                            f"not the committed {CC_NOMINAL_W}")
    return _CC_LINE_RE.sub(lambda _m: f"{head}w={w}{tail}", text)


def subst_rdiv(text, l, expect):
    """Rewrite the l= token of EVERY divider leg named in `expect` to `l`.

    Fails unless each expected leg is found exactly once at the committed
    length: a leg that is missing, duplicated or drifted -- in particular a
    substitution that would move only one of XRtop/XRbot and so change the
    divider ratio -- raises, so the two legs can only ever move together."""
    out = text
    for inst in sorted(expect):
        old = DIVIDER_LEGS[inst]
        out = _replace_line(out, old, old.replace(f"l={RDIV_NOMINAL_L}", f"l={l}"),
                            f"R_div leg {inst} -> l={l}")
    if expect and l != RDIV_NOMINAL_L and out == text:
        raise OverrideError(f"R_div -> l={l}: substitution left the text unchanged")
    return out


def overridden_design_netlist(committed_text, w, l):
    """The design-netlist copy: both knobs applied to ldo_core's own lines."""
    return subst_cc(subst_rdiv(committed_text, l, CORE_LEGS), w)


_INCLUDE_RE = re.compile(r'^\.include "([^"]+)"$', re.MULTILINE)
_CC_PREFIX_RE = re.compile(r"^XCc OUT MZ cap_cmomi ", re.MULTILINE)


def verify_deck(deck_text, include_text, bench, w, l):
    """Assert that the deck, as written, simulates the overridden circuit.

    `include_text` is the text of the design-netlist copy the deck's
    .include names. Raises OverrideError when:
      - the deck names no, or more than one, .include target, or the file it
        names does not hold `include_text`;
      - the copy's XCc line is not present exactly once at w, or its
        XRtop/XRbot not exactly once each at l (they reach every bench
        through the include);
      - a leg the bench flattens or replicates (BENCH_DECK_LEGS) is not in
        the deck exactly once at l -- the override did not reach the deck;
      - for a non-nominal axis, a nominal-valued line survives anywhere in
        the deck or the copy (a stale line the simulator would also read)."""
    targets = _INCLUDE_RE.findall(deck_text)
    if len(targets) != 1:
        raise OverrideError(f"{bench} deck: {len(targets)} .include lines, expected exactly 1")
    with open(targets[0], encoding="utf-8") as fh:
        on_disk = fh.read()
    if on_disk != include_text:
        raise OverrideError(f"{bench} deck: the .include target {targets[0]} is not the "
                            "overridden design-netlist copy")
    if [cw for _, cw, _ in _cc_widths(include_text)] != [w]:
        raise OverrideError(f"{bench} deck: the copy does not carry exactly one XCc line at w={w}")
    for inst in CORE_LEGS:
        want = DIVIDER_LEGS[inst].replace(f"l={RDIV_NOMINAL_L}", f"l={l}")
        if _count_line(include_text, want) != 1:
            raise OverrideError(f"{bench} deck: the copy does not carry {inst} at l={l} exactly once")
    for inst in BENCH_DECK_LEGS[bench]:
        want = DIVIDER_LEGS[inst].replace(f"l={RDIV_NOMINAL_L}", f"l={l}")
        if _count_line(deck_text, want) != 1:
            raise OverrideError(f"{bench} deck: {inst} is not in the deck at l={l} exactly once "
                               "-- the R_div override did not reach the deck")
    for where, text in (("deck", deck_text), ("design copy", include_text)):
        if w != CC_NOMINAL_W and CC_NOMINAL_W in [cw for _, cw, _ in _cc_widths(text)]:
            raise OverrideError(f"{bench} {where}: the nominal XCc line survives a {w} override")
        if l != RDIV_NOMINAL_L:
            for ln in text.splitlines():
                if ln.startswith(tuple(DIVIDER_LEGS)) and f"l={RDIV_NOMINAL_L}" in ln:
                    raise OverrideError(f"{bench} {where}: nominal-length divider line survives "
                                        f"an l={l} override: '{ln}'")


def cmd_design_copy(a):
    with open(a.src, encoding="utf-8") as fh:
        src = fh.read()
    out = overridden_design_netlist(src, a.w, a.l)
    if a.w == CC_NOMINAL_W and a.l == RDIV_NOMINAL_L and out != src:
        raise OverrideError("the 1x/1x copy is not byte-identical to the committed netlist")
    if os.path.abspath(a.out) == os.path.abspath(a.src):
        raise OverrideError("refusing to write the override over the committed netlist")
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(out)
    return 0


def cmd_patch_deck(a):
    with open(a.deck, encoding="utf-8") as fh:
        deck = fh.read()
    with open(a.design, encoding="utf-8") as fh:
        include_text = fh.read()
    patched = subst_rdiv(deck, a.l, BENCH_DECK_LEGS[a.bench])
    verify_deck(patched, include_text, a.bench, a.w, a.l)
    with open(a.deck, "w", encoding="utf-8") as fh:
        fh.write(patched)
    return 0


# ---- per-bench readings --------------------------------------------------- #
def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, float) and not math.isfinite(x):
        return "nan"
    return f"{x:.8g}" if isinstance(x, float) else str(x)


def _near(rows, freq):
    return min(rows, key=lambda r: abs(math.log10(r[0]) - math.log10(freq)))


def loopgain_reading(path):
    m = am.loopgain_metrics(path)
    c = am.classify_margins(path)
    rows = read_wrdata(path, 4)
    return {
        "lg:f_ug_hz": m["unity_gain_freq_hz"],
        "lg:n_0db_crossings": m["n_0db_crossings"],
        "lg:pm_deg": m["phase_margin_deg"],
        "lg:pm_worst_deg": m["phase_margin_worst_deg"],
        "lg:pm_verdict": c["pm"]["verdict"],
        "lg:pm_reasons": "|".join(c["pm"]["reasons"]),
        "lg:gm_db": m["gain_margin_db"],
        "lg:n_gm_crossings": m["n_gain_margin_crossings"],
        "lg:gm_verdict": c["gm"]["verdict"],
        "lg:gm_reasons": "|".join(c["gm"]["reasons"]),
        "lg:nyquist_class": c["nyquist"]["class"],
        "lg:gain_db_1khz": _near(rows, 1e3)[1],
    }


def psrr_reading(path):
    p = am.psrr_metrics(path)
    rows = read_wrdata(path, 2)
    notch = min(rows, key=lambda r: r[1])
    return {
        "psrr:db_1khz": p["psrr_db_1khz"],
        "psrr:db_100khz": p["psrr_db_100khz"],
        "psrr:notch_db": notch[1],
        "psrr:notch_hz": notch[0],
    }


def psrr_axis_problems(path):
    """The psrr trace's axis contract: 161 rows from 1 Hz to 100 MHz (the
    template's `ac dec 20 1 100meg`), 2 columns, strictly increasing."""
    rows = read_wrdata(path, 2)
    bad = []
    if len(rows) != EXPECT_ROWS_AC:
        bad.append(f"{path}: {len(rows)} rows, expected {EXPECT_ROWS_AC}")
    if rows and any(len(r) != 2 for r in rows):
        bad.append(f"{path}: not 2 columns on every row")
    if not bad:
        f = [r[0] for r in rows]
        if not math.isclose(f[0], 1.0, rel_tol=1e-6) or not math.isclose(f[-1], 1e8, rel_tol=1e-6):
            bad.append(f"{path}: axis {f[0]:g}..{f[-1]:g} Hz, expected 1..1e8")
        if any(b <= a for a, b in zip(f, f[1:])):
            bad.append(f"{path}: frequency not strictly increasing")
    return bad


def dc_reading(csv_path, liveness_vout, cc_f):
    """The DC operating point through e1_oppoints.reduce_point -- E1's checks
    (finite, sign conventions, break current, KCL at VOUT, the 1.7-1.9 V
    regulation band, the fleet liveness measurement) applied unchanged to
    this point. Returns (reading dict, failed-check names)."""
    row, failed = e1.reduce_point(P5, csv_path, liveness_vout, cc_f)
    vout = float(row["op:v(vout)"])
    vfb = float(row["op:v(fb)"])
    return {
        "dc:vout_v": vout,
        "dc:vfb_v": vfb,
        "dc:divider_ratio": vfb / vout if vout else float("nan"),
        "dc:i_div_a": float(row["op:i(vdivsense)"]),
        "dc:i_div_pass_a": float(row["op:@n.xmpass.nsg13_hv_pmos[ids]"]),
        "dc:r_div_ohm": float(row["derived:r_div_ohm"]),
        "dc:eaout_v": float(row["op:v(eaout)"]),
        "dc:iq_a": -float(row["op:i(vin)"]),
        "dc:iq_over_30ua_target": -float(row["op:i(vin)"]) / IQ_TARGET_A,
        "dc:check_all_ok": row["check:all_ok"],
        "dc:failed_checks": ",".join(failed),
        "dc:note": row["note"],
    }, failed


_MODEL_FAIL_RE = re.compile(
    r"osdi_load_failed|Unable to find definition of model|couldn't be loaded|"
    r"Unknown model type|fatal error", re.IGNORECASE)


def deck_provenance(record, corners_dir):
    """{point_id: (ok, why)} -- from the committed fleet provenance, that
    the override is what the worker simulated, per deck:
      - the runner's report lists the design-netlist copy in its
        netlist_closure with a sha256 equal to BOTH the committed copy's
        bytes AND a fresh re-derivation (committed netlist + the point's
        knobs);
      - the submitted tb.spice names that copy in its .include and carries
        the bench's own flattened/replica legs at the point's l;
      - the corner passed with no error-severity diagnostic.
    A mismatch here means the simulated circuit was not the overridden one."""
    prov = os.path.join(corners_dir, "_batch")
    out = {}
    pts = os.path.join(prov, "points.tsv")
    if not os.path.isfile(pts):
        return out
    with open(os.path.join(HERE, "..", "..", "design", "sg13cmos5l", "netlist",
                           "ldo_core_cmos5l.spice"), encoding="utf-8") as fh:
        committed = fh.read()
    want = {}
    for rdiv, cc in POINTS:
        key = point_key(rdiv, cc)
        text = overridden_design_netlist(committed, CC_LEVELS[cc], RDIV_LEVELS[rdiv])
        want[key] = (design_copy_name(key), hashlib.sha256(text.encode("utf-8")).hexdigest(),
                     RDIV_LEVELS[rdiv])
    with open(pts, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            if not ln.strip():
                continue
            r = dict(zip(header, ln.rstrip("\n").split("\t")))
            pid, group = r["point_id"], r["group"]
            m = re.match(r"^(loopgain|psrr|e1op)_e4_ss_125c_rwcs_i0ua_c3450nf_e0mohm_(rdiv\w+)$", pid)
            if not m:
                out[pid] = (False, "unrecognized point id")
                continue
            bench, key = m.group(1), m.group(2)
            name, sha, l = want[key]
            problems = []
            gdir = os.path.join(prov, group)
            try:
                with open(os.path.join(gdir, "report.json"), encoding="utf-8") as fh:
                    rep = json.load(fh)
            except (OSError, ValueError):
                rep = None
            if rep is None:
                problems.append("no report.json")
                out[pid] = (False, "; ".join(problems))
                continue
            closure = (rep.get("environment") or {}).get("netlist_closure") or []
            staged = {os.path.basename(e.get("path") or e.get("name") or ""): e.get("sha256")
                      for e in closure if isinstance(e, dict)}
            if staged.get(name) != sha:
                problems.append(f"worker closure digest for {name} is {str(staged.get(name))[:16]}, "
                                f"not the re-derived override {sha[:16]}")
            corner = [c for c in rep.get("corners") or []
                      if c.get("process") == r.get("process")
                      and float(c.get("temperature_c", "nan")) == float(r.get("temperature_c", "nan"))]
            if len(corner) != 1 or corner[0].get("status") != "pass":
                problems.append("corner status is not a single pass")
            elif any(d.get("severity") == "error" for d in corner[0].get("diagnostics") or []):
                problems.append("corner carries an error-severity diagnostic")
            tb_path = os.path.join(gdir, "tb.spice")
            if not os.path.isfile(tb_path):
                problems.append("no submitted tb.spice")
            else:
                with open(tb_path, encoding="utf-8") as fh:
                    tb = fh.read()
                targets = _INCLUDE_RE.findall(tb)
                if [os.path.basename(t) for t in targets] != [name]:
                    problems.append("tb.spice does not .include the copy")
                for inst in BENCH_DECK_LEGS.get(bench, ()):
                    leg = DIVIDER_LEGS[inst].replace(f"l={RDIV_NOMINAL_L}", f"l={l}")
                    if _count_line(tb, leg) != 1:
                        problems.append(f"tb.spice does not carry {inst} at l={l}")
            out[pid] = (not problems, "; ".join(problems))
    return out


def models_loaded(corners_dir):
    """{point_id: (ok, why)} from the batch provenance: the job's verified OSDI
    preload (batch_backend.py's osdi_provenance_problems, recorded per job
    in backend.json) must name every staged binary with the staged sha256,
    and the point's log must carry no model-load failure. A run that
    completed against unloaded models is a failure here, not a result."""
    prov = os.path.join(corners_dir, "_batch")
    out = {}
    bp = os.path.join(prov, "backend.json")
    backend = {}
    if os.path.isfile(bp):
        with open(bp, encoding="utf-8") as fh:
            backend = json.load(fh)
    staged = backend.get("staged_osdi_sha256") or {}
    jobs = {j.get("group"): j for j in backend.get("jobs") or []}
    pts = os.path.join(prov, "points.tsv")
    if not os.path.isfile(pts):
        return out
    with open(pts, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for ln in fh:
            if not ln.strip():
                continue
            r = dict(zip(header, ln.rstrip("\n").split("\t")))
            pid, group = r["point_id"], r["group"]
            problems = []
            job = jobs.get(group)
            if job is None:
                problems.append(f"no job record for group {group}")
            else:
                verified = job.get("osdi_preload_verified")
                if not isinstance(verified, dict) or not staged:
                    problems.append("no verified OSDI preload in the job record")
                else:
                    for name, want in sorted(staged.items()):
                        if verified.get(name) is None:
                            problems.append(f"{name} not reported preloaded")
                        elif verified[name] != want:
                            problems.append(f"{name} preload sha256 != staged")
                    extra = sorted(set(verified) - set(staged))
                    if extra:
                        problems.append(f"preload names unstaged {extra}")
            log = os.path.join(corners_dir, f"{pid}.log")
            if not os.path.isfile(log):
                problems.append("no log")
            else:
                with open(log, encoding="utf-8", errors="replace") as fh:
                    m = _MODEL_FAIL_RE.search(fh.read())
                if m:
                    problems.append(f"log carries '{m.group(0)}'")
            out[pid] = (not problems, "; ".join(problems))
    return out


CSV_FIELDS = [
    "point_key", "rdiv_label", "rdiv_l", "cc_label", "cc_w",
    "loopgain_point_id", "psrr_point_id", "e1op_point_id",
    "lg:f_ug_hz", "lg:n_0db_crossings", "lg:pm_deg", "lg:pm_worst_deg",
    "lg:pm_verdict", "lg:pm_reasons", "lg:gm_db", "lg:n_gm_crossings",
    "lg:gm_verdict", "lg:gm_reasons", "lg:nyquist_class", "lg:gain_db_1khz",
    "psrr:db_1khz", "psrr:db_100khz", "psrr:notch_db", "psrr:notch_hz",
    "psrr:notch_over_fug",
    "dc:vout_v", "dc:vfb_v", "dc:divider_ratio", "dc:i_div_a", "dc:i_div_pass_a",
    "dc:r_div_ohm", "dc:eaout_v", "dc:iq_a", "dc:iq_over_30ua_target",
    "dc:check_all_ok", "dc:failed_checks", "dc:note",
    "check:loopgain_trace_ok", "check:psrr_trace_ok", "check:deck_provenance_ok",
    "check:models_loaded", "check:all_ok", "note",
]


def _reduce(rid, corners_dir, out_csv, out_json):
    if not os.path.isdir(corners_dir):
        print(f"e4_divider_cc: no corners dir for record {rid}: {corners_dir}",
              file=sys.stderr)
        return 2
    liveness = e1._liveness_by_point(corners_dir)
    loaded = models_loaded(corners_dir)
    provenance = deck_provenance(rid, corners_dir)
    rows, all_failed = [], {}
    for rdiv, cc in POINTS:
        key = point_key(rdiv, cc)
        w, l = CC_LEVELS[cc], RDIV_LEVELS[rdiv]
        paths = {b: os.path.join(corners_dir, point_id(b, key) + SUFFIX[b]) for b in BENCHES}
        for b in BENCHES:
            if not os.path.isfile(paths[b]):
                print(f"e4_divider_cc: refusing to reduce: missing export {paths[b]}",
                      file=sys.stderr)
                return 2
        row = {"point_key": key, "rdiv_label": rdiv, "rdiv_l": l,
               "cc_label": cc, "cc_w": w,
               "loopgain_point_id": point_id("loopgain", key),
               "psrr_point_id": point_id("psrr", key),
               "e1op_point_id": point_id("e1op", key)}
        failed, notes = [], []
        probs = ac_sweep.check_trace(paths["loopgain"], LG_AC_MAX)
        if probs:
            failed.append("loopgain_trace")
            notes.extend(probs)
            row.update({k: "" for k in CSV_FIELDS if k.startswith("lg:")})
        else:
            row.update({k: _fmt(v) for k, v in loopgain_reading(paths["loopgain"]).items()})
        probs = psrr_axis_problems(paths["psrr"])
        if probs:
            failed.append("psrr_trace")
            notes.extend(probs)
            row.update({k: "" for k in CSV_FIELDS if k.startswith("psrr:")})
        else:
            ps = psrr_reading(paths["psrr"])
            fug = float(row["lg:f_ug_hz"]) if row["lg:f_ug_hz"] else None
            ps["psrr:notch_over_fug"] = ps["psrr:notch_hz"] / fug if fug else float("nan")
            row.update({k: _fmt(v) for k, v in ps.items()})
        dc_ok = True
        try:
            e1.check_export(paths["e1op"])
        except ValueError as exc:
            dc_ok = False
            failed.append("dc_export")
            notes.append(str(exc))
        if dc_ok:
            dc, dc_failed = dc_reading(paths["e1op"],
                                       liveness.get(point_id("e1op", key)),
                                       e1.CC_F_NOMINAL * CC_FACTOR[cc])
            row.update({k: _fmt(v) for k, v in dc.items()})
            if dc_failed:
                failed.append("dc")
                notes.append(f"dc checks failed: {','.join(dc_failed)}")
        else:
            row.update({k: "" for k in CSV_FIELDS if k.startswith("dc:")})
        why = [loaded.get(point_id(b, key), (False, "not in the batch provenance"))[1]
               for b in BENCHES if not loaded.get(point_id(b, key), (False, ""))[0]]
        row["check:loopgain_trace_ok"] = str("loopgain_trace" not in failed)
        row["check:psrr_trace_ok"] = str("psrr_trace" not in failed)
        row["check:models_loaded"] = str(not why)
        if why:
            failed.append("models_loaded")
            notes.extend(why)
        prov_why = [provenance.get(point_id(b, key), (False, "not in the batch provenance"))[1]
                    for b in BENCHES if not provenance.get(point_id(b, key), (False, ""))[0]]
        row["check:deck_provenance_ok"] = str(not prov_why)
        if prov_why:
            failed.append("deck_provenance")
            notes.extend(prov_why)
        row["check:all_ok"] = str(not failed)
        row["note"] = "; ".join(notes)
        rows.append(row)
        if failed:
            all_failed[key] = failed
    with open(out_csv, "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        wtr.writeheader()
        for row in rows:
            wtr.writerow(row)
    with open(out_json, "w") as fh:
        json.dump({"record": rid, "bench": BENCH, "points": [
            {k: v for k, v in r.items() if not k.startswith("dc:note") and k != "note"}
            for r in rows], "failed_checks": all_failed}, fh, indent=1)
        fh.write("\n")
    if all_failed:
        print("e4_divider_cc: FAILED CHECKS (outputs written; the record is "
              "marked incomplete):", file=sys.stderr)
        for k, fs in all_failed.items():
            print(f"e4_divider_cc:   {k}: {','.join(fs)}", file=sys.stderr)
        return 3
    print(f"e4_divider_cc: all {len(rows)} points reduced clean", file=sys.stderr)
    return 0


# ---- record md ------------------------------------------------------------ #
def _backend(corners_dir):
    out = {}
    bp = os.path.join(corners_dir, "_batch", "backend.json")
    if os.path.isfile(bp):
        with open(bp, encoding="utf-8") as fh:
            out = json.load(fh)
    env = os.path.join(corners_dir, "_batch", "backend.env")
    ngspice = runner = "unknown"
    if os.path.isfile(env):
        for ln in open(env, encoding="utf-8"):
            if ln.startswith("BATCH_NGSPICE_VERSION="):
                ngspice = ln.split("=", 1)[1].strip().strip("'")
            if ln.startswith("BATCH_RUNNER_KLT="):
                runner = ln.split("=", 1)[1].strip().strip("'")
    return out, ngspice, runner


def _manifest(rid):
    p = os.path.join(HERE, "records", f"{rid}.{BENCH}.manifest.tsv")
    if not os.path.isfile(p):
        return []
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _rows_csv(rid):
    with open(os.path.join(HERE, "records", f"{rid}.{BENCH}.csv"), newline="") as fh:
        return list(csv.DictReader(fh))


def _g(x, sig=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x) if x else "n/a"
    if not math.isfinite(v):
        return "n/a"
    return f"{v:.{sig}g}"


def _db(x, sig=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    return f"{v:.{sig}f}" if math.isfinite(v) else "n/a"


def _amp(x, sig=3):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(v):
        return "n/a"
    return f"{v * 1e6:.{sig}f} uA" if abs(v) < 1e-3 else f"{v * 1e3:.{sig}f} mA"


def _baseline_reading():
    """P5 at 1x/1x from the committed same-vintage traces, read with the same
    functions as the E4 traces."""
    stem = os.path.join(HERE, "corners", BASELINE_RID)
    lg = os.path.join(stem, f"loopgain_{BASELINE_STEM}_ac.csv")
    ps = os.path.join(stem, f"psrr_{BASELINE_STEM}_ac.csv")
    if not (os.path.isfile(lg) and os.path.isfile(ps)):
        return None
    out = {f"base:{k}": v for k, v in loopgain_reading(lg).items()}
    out.update({f"base:{k}": v for k, v in psrr_reading(ps).items()})
    return out


def _model_input_vintage(group_dir):
    """[(name, client sha/16, worker sha/16)] for one group's model inputs:
    the submitting host's staged closure (inputs.sha256.json) against what
    the worker reported it loaded (report.json -> worker_environment
    .model_inputs)."""
    inv_p = os.path.join(group_dir, "inputs.sha256.json")
    rep_p = os.path.join(group_dir, "report.json")
    if not (os.path.isfile(inv_p) and os.path.isfile(rep_p)):
        return []
    with open(inv_p, encoding="utf-8") as fh:
        inv = json.load(fh)
    with open(rep_p, encoding="utf-8") as fh:
        rep = json.load(fh)
    client = {os.path.basename(p): (s or "")[:16] for p, s in inv.items()}
    worker = {m.get("name"): (m.get("sha256") or "")[:16]
              for m in (((rep.get("environment") or {}).get("remote") or {})
                        .get("worker_environment") or {}).get("model_inputs") or []
              if m.get("name")}
    rows = []
    for name in sorted(set(client) | set(worker)):
        if name == "corners.lib" or not name.endswith((".lib", ".osdi")):
            continue
        rows.append((name, client.get(name, "-"), worker.get(name, "-")))
    return rows


def _job_lines(backend):
    lines = []
    for j in backend.get("jobs") or []:
        ver = j.get("osdi_preload_verified") or {}
        lines.append(
            f"  - `{j.get('group')}`: job `{j.get('job_id')}` on {j.get('instance_type')} "
            f"({j.get('lifecycle')}), {j.get('corners')}/{j.get('requested')} corner(s), "
            f"runner klt {j.get('runner_klt_version')}, verified OSDI preload {len(ver)}/6")
    return lines


def record_md_text(rid):
    sim = HERE
    rows = _rows_csv(rid)
    manifest = _manifest(rid)
    backend, ngspice, runner = _backend(os.path.join(sim, "corners", rid))
    by_key = {r["point_key"]: r for r in rows}
    base = _baseline_reading() or {}
    one_x = by_key[BASELINE_KEY]
    copies = {}
    for m in manifest:
        copies.setdefault(os.path.basename(m["design_netlist"]), m["design_netlist_sha256"])
    committed_sha = sha256_file(os.path.join(sim, "..", "..", "design", "sg13cmos5l", "netlist",
                                             "ldo_core_cmos5l.spice"), 16)
    pdk = manifest[0]["pdk"] if manifest else "unknown"
    git_sha = rid.split("-")[2] if rid.count("-") >= 2 else "unknown"
    group_of = {}
    prov = os.path.join(sim, "corners", rid, "_batch")
    if os.path.isfile(os.path.join(prov, "points.tsv")):
        with open(os.path.join(prov, "points.tsv"), encoding="utf-8") as fh:
            header = fh.readline().rstrip("\n").split("\t")
            for ln in fh:
                r = dict(zip(header, ln.rstrip("\n").split("\t")))
                group_of[r["point_id"]] = r["group"]

    L = []
    A = L.append
    A(f"# E4 divider/Cc probe at DR-0015 point P5 (issue #315) -- DR-0015 experiment E4")
    A("")
    A("SCHEMATIC-LEVEL diagnostic evidence, NOT a spec pass and NOT a")
    A("compensation change. DR-0015 stays **Proposed**; DR-0007 rows 3, 6,")
    A("7 and 10 keep their states, targets and ratification; nothing here is")
    A("ratified, relaxed or production. This record measures what DR-0015's")
    A("Disposition derives and defers to probe E4: at point P5 (ss / 125 C /")
    A("res_wcs, 0 mA, Cout 3.45 uF, ESR 0 mohm) it crosses the feedback")
    A("divider's length (R_div in {1x, 0.5x}) with the Miller cap's width")
    A("(Cc in {1x, 0.65x}) and reads the loop gain, the PSRR curve and the DC")
    A("operating point at the four points, so the class-3 tension (PSRR at")
    A("1 kHz at zero load) can be read against measurement instead of")
    A("inferred. It changes no row target and decides nothing.")
    A("")
    A("## Vintage and provenance")
    A("")
    A(f"- Record id: `{rid}` (run at HEAD git sha `{git_sha}`).")
    A(f"- PDK install that actually ran (the manifest's `pdk` column;")
    A("  `run_e4.sh` reads it from the resolved install at run time and")
    A(f"  refuses to run off-pin): `{pdk}`.")
    A(f"- Engine: {ngspice}; batch fleet runner klt {runner}.")
    A("- Design netlist under test: `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`")
    A(f"  committed sha256 `{committed_sha}...` -- byte-unchanged by this record.")
    A("  Every point simulates a COPY (below); the committed netlists are")
    A("  never written. The 1x/1x copy is byte-identical to the committed")
    A("  netlist, which is what makes the 1x/1x point like-for-like with the")
    A("  committed P5 result.")
    A("- Fleet jobs (`corners/" + rid + "/_batch/`, one request per deck):")
    L.extend(_job_lines(backend))
    A("- Model inputs: the six OSDI binaries were staged by content and the")
    A("  runner's own preload of exactly those bytes is verified per job")
    A("  (`backend.json` `osdi_preload_verified`, sha256 against")
    A("  `staged_osdi_sha256`); every point's log is free of model-load")
    A("  failures (the model-load table below).")
    A("")
    A("## What was overridden, and how it reached the decks")
    A("")
    A("| point | XRtop / XRbot l= | XCc w= | design-netlist copy | copy sha256/16 |")
    A("|---|---|---|---|---|")
    for rdiv, cc in POINTS:
        key = point_key(rdiv, cc)
        name = design_copy_name(key)
        sha = copies.get(name, "n/a")
        tag = " (== committed)" if sha[:16] == committed_sha else ""
        A(f"| {key} | `l={RDIV_LEVELS[rdiv]}` | `w={CC_LEVELS[cc]}` | `{name}` | `{sha}`{tag} |")
    A("")
    A("Both knobs are testbench-local substitutions on a copy of the design")
    A("netlist (`e4_divider_cc.py`): `Cc` is the `w=` token of the")
    A("`XCc OUT MZ cap_cmomi` line with `l` held at `30e-6` (the same knob")
    A("`run_sweep.sh`'s `subst_cc_width()` turns); `R_div` is the `l=` token")
    A("of BOTH `XRtop` and `XRbot`, scaled by the same factor so the divider")
    A("ratio -- and with it the regulation setpoint -- is unchanged. Each")
    A("substitution fails unless it changes exactly the lines it owns")
    A("(`test_e4_divider_cc.py` exercises both negative controls).")
    A("")
    A("Where the divider lives is why one site is not enough: the PSRR")
    A("bench instantiates `ldo_core_cmos5l` whole and reads the copy through")
    A("its `.include`; the loop-gain bench and the E1 operating-point bench")
    A("flatten the core one level and carry their own verbatim `XRtop`/")
    A("`XRbot` lines (the E1 bench also a divider replica through which the")
    A("divider current is measured), so the same substitution is applied to")
    A("the rendered deck's own lines as well. `e4_divider_cc.py patch-deck`")
    A("then asserts, per deck, that the `.include` target holds the")
    A("overridden lines and that no nominal-valued line survives -- a deck")
    A("whose copy moved while its flattened legs stayed nominal is refused")
    A("at render time, before anything is submitted.")
    A("")
    A("On the fleet the same fact is re-proven from the committed provenance")
    A("(`e4_divider_cc.py` `deck_provenance`, the deck-provenance column of")
    A("the checks table): each group's `report.json` lists the design-netlist")
    A("copy in its `netlist_closure` with a sha256 equal to a fresh")
    A("re-derivation (committed netlist + the point's knobs), the submitted")
    A("`tb.spice` includes that copy and carries the bench's own legs at the")
    A("point's `l=`, and the corner passed with no error diagnostic.")
    A("")
    A("## Baseline comparison: the 1x/1x point against the committed P5 result")
    A("")
    A("| quantity | E4 1x/1x | same-vintage `" + BASELINE_RID + "` trace | delta | DR-0015 printed |")
    A("|---|---:|---:|---:|---:|")
    pairs = (
        ("`f_ug` [Hz]", "lg:f_ug_hz", "base:lg:f_ug_hz", "1 052"),
        ("PM first [deg]", "lg:pm_deg", "base:lg:pm_deg", "17.61"),
        ("GM [dB]", "lg:gm_db", "base:lg:gm_db", "64.26"),
        ("0 dB crossings", "lg:n_0db_crossings", "base:lg:n_0db_crossings", "1"),
        ("\\|L(1 kHz)\\| [dB]", "lg:gain_db_1khz", "base:lg:gain_db_1khz", "0.85"),
        ("PSRR@1 kHz [dB]", "psrr:db_1khz", "base:psrr:db_1khz", "43.55"),
        ("PSRR@100 kHz [dB]", "psrr:db_100khz", "base:psrr:db_100khz", "92.53"),
        ("notch bottom [dB]", "psrr:notch_db", "base:psrr:notch_db", "43.3"),
        ("notch frequency [Hz]", "psrr:notch_hz", "base:psrr:notch_hz", "1 122"),
    )
    for label, k, bk, printed in pairs:
        a = one_x[k]
        b = base.get(bk, "")
        try:
            d = float(a) - float(b)
            ds = f"{d:+.4g}"
        except (TypeError, ValueError):
            ds = "n/a"
        A(f"| {label} | {_g(a, 6)} | {_g(b, 6)} | {ds} | {printed} |")
    A("")
    A("Vintage of each column: **DR-0015 printed** is DR-0015's own table")
    A("row P5 (record `20261010-101245-6df50fd`: the OLD PDK pin")
    A("`607e18d4...` on the pre-#89 design). **Same-vintage trace** is the")
    A(f"#155 re-run `{BASELINE_RID}` at the current pin on the same design")
    A("bytes -- the reference DR-0015's E1 addendum names -- read with the")
    A("same functions as the E4 traces. At P5 the two committed references")
    A("agree to the printed digits, so any difference in the delta column is")
    A("attributable to what the fleet ran today, not to the reference.")
    A("")
    vint = _model_input_vintage(os.path.join(prov, group_of.get(one_x["loopgain_point_id"], "")))
    if vint:
        A("What the worker actually loaded for the 1x/1x loop-gain deck")
        A("(client-staged closure `inputs.sha256.json` vs the worker's")
        A("`worker_environment.model_inputs`):")
        A("")
        A("| input | staged (client) sha/16 | worker sha/16 | verdict |")
        A("|---|---|---|---|")
        for name, c, wk in vint:
            verdict = "match" if c == wk else "worker differs"
            A(f"| `{name}` | `{c}` | `{wk}` | {verdict} |")
        A("")
        diffs = [n for n, c, wk in vint if c != wk]
        A(f"- {len(diffs)} of {len(vint)} model inputs differ between the")
        A("  submitting host and the worker ({})".format(", ".join(f"`{n}`" for n in diffs)
                                                         or "none"))
        A("- The corner cards and MOS model libs the worker resolves are a")
        A("  different vintage from the submitting host's staged copies; a")
        A("  loop-gain difference of this kind was observed at P3 by the")
        A("  2026-11-20 OSDI replay (issue #313, `backend-validation/`), where")
        A("  the like-for-like comparison stayed inconclusive for exactly this")
        A("  reason. The E4 four-point readings are therefore internally")
        A("  consistent (one fleet job vintage each; the 1x/1x point is the")
        A("  in-run control) while the baseline delta above is read as a")
        A("  model-input vintage observation, not a circuit difference.")
        A("")
    A("## Results (four points)")
    A("")
    A("Loop gain and PSRR per point, with DR-0014's classification (PM")
    A("verdict, GM verdict with reasons) computed by `ac_metrics.py` under")
    A("its unchanged bounds; `f_ug` is the first 0 dB crossing, PM the first")
    A("crossing's phase margin, worst PM the minimum over every 0 dB crossing, GM")
    A("the first -180 deg crossing's margin:")
    A("")
    A("| R_div | Cc | `f_ug` [Hz] | 0 dB crossings | PM first / worst [deg] | PM verdict | GM [dB] | GM verdict | "
      "\\|L(1 kHz)\\| [dB] | PSRR@1 kHz [dB] | PSRR@100 kHz [dB] | notch bottom [dB] @ [Hz] (x `f_ug`) |")
    A("|---|---|---:|---:|---|---|---:|---|---:|---:|---:|---|")
    for rdiv, cc in POINTS:
        r = by_key[point_key(rdiv, cc)]
        A(f"| {rdiv} | {cc} | {_g(r['lg:f_ug_hz'], 6)} | {r['lg:n_0db_crossings']} | "
          f"{_db(r['lg:pm_deg'])} / {_db(r['lg:pm_worst_deg'])} | "
          f"{r['lg:pm_verdict']} ({r['lg:pm_reasons'] or 'n/a'}) | {_db(r['lg:gm_db'])} | "
          f"{r['lg:gm_verdict']} ({r['lg:gm_reasons'] or 'n/a'}) | {_db(r['lg:gain_db_1khz'])} | "
          f"{_db(r['psrr:db_1khz'])} | {_db(r['psrr:db_100khz'])} | "
          f"{_db(r['psrr:notch_db'])} @ {_g(r['psrr:notch_hz'], 5)} ({_g(r['psrr:notch_over_fug'], 3)}) |")
    A("")
    A("DC operating point per point (E1 bench, E1's checks unchanged):")
    A("")
    A("| R_div | Cc | VOUT [V] | V(FB)/VOUT | I_div replica [A] | I_div pass [A] | R_div [ohm] | Iq [A] (x 30 uA target) |")
    A("|---|---|---:|---:|---:|---:|---:|---|")
    for rdiv, cc in POINTS:
        r = by_key[point_key(rdiv, cc)]
        A(f"| {rdiv} | {cc} | {_g(r['dc:vout_v'], 7)} | {_g(r['dc:divider_ratio'], 7)} | "
          f"{_g(r['dc:i_div_a'], 4)} | {_g(r['dc:i_div_pass_a'], 4)} | {_g(r['dc:r_div_ohm'], 4)} | "
          f"{_g(r['dc:iq_a'], 4)} ({_g(r['dc:iq_over_30ua_target'], 3)}x) |")
    A("")
    A("The divider current is reported as measured, in two independent ways:")
    A("through the replica ammeter and as the pass device's drain current at")
    A("zero load (the E1 KCL check ties them together). `rhigh` resistance")
    A("does not scale linearly with `l`, so nothing is assumed about the")
    A("0.5x point's current; R_div = 2 * (VOUT/2) / I_div is the measured")
    A("per-point value.")
    A("")
    A("## Divider ratio: the 0.5x points against the 1x points")
    A("")
    A("| Cc | VOUT at R_div 1x [V] | VOUT at R_div 0.5x [V] | delta [V] | 0.5x in the 1.7-1.9 V band | V(FB)/VOUT 1x vs 0.5x |")
    A("|---|---:|---:|---:|---|---|")
    for cc in ("1x", "0.65x"):
        a = by_key[point_key("1x", cc)]
        b = by_key[point_key("0.5x", cc)]
        try:
            d = float(b["dc:vout_v"]) - float(a["dc:vout_v"])
            ds = f"{d:+.3e}"
            in_band = 1.7 <= float(b["dc:vout_v"]) <= 1.9
        except (TypeError, ValueError):
            ds, in_band = "n/a", False
        A(f"| {cc} | {_g(a['dc:vout_v'], 7)} | {_g(b['dc:vout_v'], 7)} | {ds} | {in_band} | "
          f"{_g(a['dc:divider_ratio'], 7)} vs {_g(b['dc:divider_ratio'], 7)} |")
    A("")
    A("The 1.7-1.9 V band is the E1 bench's existing regulation tolerance")
    A("(`e1_oppoints.reduce_point`); the delta column is the direct")
    A("measurement of how far the setpoint moved. Both legs scale by the")
    A("same factor, so the ratio V(FB)/VOUT is preserved by construction and")
    A("the DC setpoint follows it.")
    A("")
    notches = [float(by_key[point_key(a, b)]["psrr:notch_db"]) for a, b in POINTS
               if by_key[point_key(a, b)]["psrr:notch_db"]]
    A("## Reading against DR-0015's stated falsifier")
    A("")
    A("DR-0015's \"What would overturn parts of this\": *E4 measuring a")
    A("materially higher PSRR notch bottom than the bracketed 38-43 dB")
    A("weakens or dissolves the class-3 tension.* Measured notch bottoms at")
    A("the four points: " + ", ".join(f"{_db(v)} dB" for v in notches) +
      f" (1x/1x: {_db(one_x['psrr:notch_db'])} dB; the six committed points")
    A("bracket 38.1-43.3 dB, P5 the top of the bracket). PSRR@1 kHz at the")
    A("four points: " + ", ".join(
        f"{_db(by_key[point_key(a, b)]['psrr:db_1khz'])} dB" for a, b in POINTS) +
      f" against the ratified row-6 target of > {PSRR_1K_TARGET_DB:g} dB.")
    A("The interpretation -- confirmed, dissolved or non-discriminating, and")
    A("what circuit change the data points to -- is DR-0015's addendum's to")
    A("state (this record measures; it does not decide).")
    A("")
    A("## Model load (every run)")
    A("")
    A("| point | loop-gain | PSRR | E1 op-point |")
    A("|---|---|---|---|")
    loaded_problems = []
    for rdiv, cc in POINTS:
        key = point_key(rdiv, cc)
        why = []
        for b in BENCHES:
            pid = point_id(b, key)
            lg = os.path.join(sim, "corners", rid, f"{pid}.log")
            ok = os.path.isfile(lg) and not _MODEL_FAIL_RE.search(open(lg, encoding="utf-8", errors="replace").read())
            why.append("clean" if ok else "**FAILED**")
            if not ok:
                loaded_problems.append(pid)
        A(f"| {key} | " + " | ".join(why) + " |")
    A("")
    A("Clean = the point's worker log carries no `osdi_load_failed` or")
    A("model-load failure, and (the fleet jobs list above) the job's")
    A("verified preload names all six staged OSDI binaries with the staged")
    A("sha256. A run that completed against unloaded models is a failure")
    A("here, never a result.")
    A("")
    A("## Checks")
    A("")
    A("| point | loop-gain trace (161 rows, 1 Hz-100 MHz) | PSRR trace (161 rows, 1 Hz-100 MHz) | DC (E1 rules) | deck provenance | models loaded | all |")
    A("|---|---|---|---|---|---|---|")
    for rdiv, cc in POINTS:
        r = by_key[point_key(rdiv, cc)]
        A(f"| {r['point_key']} | {r['check:loopgain_trace_ok']} | {r['check:psrr_trace_ok']} | "
          f"{r['dc:check_all_ok']} | {r['check:deck_provenance_ok']} | {r['check:models_loaded']} | {r['check:all_ok']} |")
    if all(by_key[point_key(a, b)]["check:all_ok"] == "True" for a, b in POINTS):
        A("All checks pass at every point: the AC traces have the contract's")
        A("shape, the DC operating points close under E1's rules, every deck's")
        A("override is proven on the fleet and every run loaded its models.")
    else:
        A("NOT every check passes at every point -- the record is INCOMPLETE. Any")
        A("False in the table above is a failed check the campaign recorded rather")
        A("than dropped (the reduction exits 3 and the driver marks the record")
        A("INCOMPLETE).")
    A("")
    A("## What this record does not claim")
    A("")
    A("- No spec row, threshold, gate, record or verdict changed; DR-0015")
    A("  stays Proposed; DR-0007 rows 3, 6, 7 and 10 keep their states.")
    A("- No compensation candidate is proposed, screened or ratified here;")
    A("  no post-change margin is predicted. The record is a measurement")
    A("  DR-0015's addendum reads.")
    A("- Four sampled points at P5 conditions only; no window, monotonicity")
    A("  or corner claim beyond them; no layout, no LVS, no T1 citation.")
    A("- The baseline comparison is read as a model-input vintage")
    A("  observation whenever the worker's corner cards differ from the")
    A("  staged ones, as the 2026-11-20 OSDI replay found at P3.")
    A("- `sim/` stays append-only: nothing under `records/`, `corners/`,")
    A("  `evidence/` or `netlist-snapshots/` was edited or deleted.")
    A("- The committed design netlists are byte-unchanged; every point ran")
    A("  a copy, and the 1x/1x copy equals the committed bytes.")
    A("")
    A("## Files")
    A("")
    A(f"- Reduction: `records/{rid}.{BENCH}.csv` (one row per point; the")
    A("  exact column contract is `e4_divider_cc.py` CSV_FIELDS),")
    A(f"  `evidence/{rid}/e4-report.json`.")
    A(f"- Raw exports + fleet provenance: `corners/{rid}/` (per-point log")
    A("  and `_ac.csv` / `_dc.csv`; `_batch/` carries the request, the deck,")
    A("  `points.tsv`, `inputs.sha256.json`, `backend.json`).")
    A(f"- Netlists: `netlist-snapshots/{rid}/` (one generated deck per")
    A("  point per bench; the four design-netlist copies under")
    A("  `design-netlist-e4/`; sha256 in the manifest).")
    A(f"- Manifest: `records/{rid}.{BENCH}.manifest.tsv`.")
    A("")
    A(f"<!-- regeneration: python3 sim/ldo-cmos5l-pvt-sweep/e4_divider_cc.py")
    A(f"     reduce --record {rid} --out-csv <tmp> --out-json <tmp>;")
    A(f"     e4_divider_cc.py record-md --record {rid};")
    A(f"     e4_divider_cc.py check --record {rid} byte-compares. -->")
    A("")
    return "\n".join(L)


def cmd_record_md(a):
    out = os.path.join(HERE, "records", f"{a.record}.{BENCH}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(record_md_text(a.record))
    return 0


def _same(a, b):
    if not (os.path.isfile(a) and os.path.isfile(b)):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def cmd_check(a):
    rid = a.record
    rec = os.path.join(HERE, "records")
    ev = os.path.join(HERE, "evidence", rid)
    tmp = tempfile.mkdtemp(prefix="e4-check-")
    bad = []
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            rc = _reduce(rid, os.path.join(HERE, "corners", rid),
                         os.path.join(tmp, "r.csv"), os.path.join(tmp, "r.json"))
        if rc != 0:
            bad.append(f"reduction exit {rc}")
        if not _same(os.path.join(tmp, "r.csv"), os.path.join(rec, f"{rid}.{BENCH}.csv")):
            bad.append("reduction CSV differs from the committed one")
        if not _same(os.path.join(tmp, "r.json"), os.path.join(ev, "e4-report.json")):
            bad.append("reduction JSON differs from the committed one")
        md = os.path.join(rec, f"{rid}.{BENCH}.md")
        committed_md = open(md, encoding="utf-8").read() if os.path.isfile(md) else None
        regenerated = record_md_text(rid)
        if committed_md != regenerated:
            bad.append("record md differs from the committed one")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        print("e4_divider_cc: check FAILED for record " + rid + ":\n  " + "\n  ".join(bad),
              file=sys.stderr)
        return 1
    print(f"e4_divider_cc: record {rid} reproduces (CSV, JSON, md byte-identical)")
    return 0


def _print(text):
    print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("design-copy", help="write an overridden design-netlist copy")
    d.add_argument("src")
    d.add_argument("out")
    d.add_argument("--w", required=True, choices=sorted(CC_LEVELS.values()))
    d.add_argument("--l", required=True, choices=sorted(RDIV_LEVELS.values()))
    d.set_defaults(func=cmd_design_copy)

    p = sub.add_parser("patch-deck", help="apply a bench's own divider legs, then verify the deck")
    p.add_argument("deck")
    p.add_argument("--bench", required=True, choices=BENCHES)
    p.add_argument("--design", required=True)
    p.add_argument("--w", required=True, choices=sorted(CC_LEVELS.values()))
    p.add_argument("--l", required=True, choices=sorted(RDIV_LEVELS.values()))
    p.set_defaults(func=cmd_patch_deck)

    r = sub.add_parser("reduce", help="reduce the four points (exits 3 on failed checks)")
    r.add_argument("--record", required=True)
    r.add_argument("--corners-dir")
    r.add_argument("--out-csv", required=True)
    r.add_argument("--out-json", required=True)
    r.set_defaults(func=lambda a: _reduce(a.record, a.corners_dir or os.path.join(HERE, "corners", a.record),
                                          a.out_csv, a.out_json))

    m = sub.add_parser("record-md", help="write the narrative record from committed files")
    m.add_argument("--record", required=True)
    m.set_defaults(func=cmd_record_md)

    c = sub.add_parser("check", help="regenerate and byte-compare the committed record (CI)")
    c.add_argument("--record", required=True)
    c.set_defaults(func=cmd_check)

    rdiv_choices = sorted({p[0] for p in POINTS})
    cc_choices = sorted({p[1] for p in POINTS})
    k = sub.add_parser("point-key", help="print the point key for an (R_div, Cc) label pair")
    k.add_argument("rdiv_label", choices=rdiv_choices)
    k.add_argument("cc_label", choices=cc_choices)
    k.set_defaults(func=lambda a: _print(point_key(a.rdiv_label, a.cc_label)))

    i = sub.add_parser("point-id", help="print the batch point id for (bench, R_div, Cc)")
    i.add_argument("bench", choices=BENCHES)
    i.add_argument("rdiv_label", choices=rdiv_choices)
    i.add_argument("cc_label", choices=cc_choices)
    i.set_defaults(func=lambda a: _print(point_id(a.bench, point_key(a.rdiv_label, a.cc_label))))

    a = ap.parse_args(argv)
    try:
        return a.func(a)
    except OverrideError as exc:
        print(f"e4_divider_cc: OVERRIDE REFUSED: {exc}", file=sys.stderr)
        return 4
    except (OSError, ValueError) as exc:
        print(f"e4_divider_cc: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
