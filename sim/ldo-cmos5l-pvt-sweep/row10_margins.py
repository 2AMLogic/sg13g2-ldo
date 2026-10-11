#!/usr/bin/env python3
"""DR-0014 row-10 margin classification of COMMITTED loop-gain traces (#126).

Offline and stdlib-only: no simulator, no PDK, no new sweep. Re-reads the raw
loop-gain traces already committed under ``corners/`` and classifies each one
with ``ac_metrics.classify_margins`` (DR-0014, proposed), for two datasets:

  legacy  the 45-point PVT record 20261010-025634-60a3e81 (the circuit record
          the characterization report selects)
  doe     the #64 combined load/Cout/ESR record 20261010-101245-6df50fd
          (536 operating points; rows read from their own `source` corners dir)

Every run cross-checks the traces against the record that was minted from
them (crossing counts, first-crossing PM, recorded worst-crossing PM, first
-180 deg GM) and enforces the no-loosening guard: a point the record shows
below the PM or GM bound must classify as `fail`. Any disagreement is a hard
error; nothing is skipped or repaired.

    python3 sim/ldo-cmos5l-pvt-sweep/row10_margins.py           # (re)write
    python3 sim/ldo-cmos5l-pvt-sweep/row10_margins.py --check   # CI: byte-compare

Outputs (new, append-only evidence named by the source record id):
    sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/row10-margins.csv
    sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/row10-margins.json
    sim/ldo-cmos5l-pvt-sweep/evidence/<record-id>/row10-margins.md
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import ac_metrics as am  # noqa: E402

SIM = "sim/ldo-cmos5l-pvt-sweep"
DR = "spec/decision-records/DR-0014-row10-stability-margin-classification.md"
RES_SFX = {"res_typ": "rtyp", "res_bcs": "rbcs", "res_wcs": "rwcs"}

DATASETS = {
    "legacy": {
        "record_id": "20261010-025634-60a3e81",
        "record_csv": f"{SIM}/records/20261010-025634-60a3e81.csv",
        "record_sha256": "d0c1e057c8cbbf0aaaab3df57b753fcca8557375372ee8bf6f6103a0b946c981",
        "rows": 45,
        "conditions": "Vin 3.30 V, 1 mA, Cout 1 uF, ESR 0, Cc nominal; 45-point PVT grid",
        "subset": ("multi_crossing_points",
                   "points the record lists with more than one 0 dB crossing "
                   "(reported ambiguous by the characterization report before DR-0014)"),
    },
    "doe": {
        "record_id": "20261010-101245-6df50fd",
        "record_csv": f"{SIM}/records/20261010-101245-6df50fd.dynamic-doe.csv",
        "record_sha256": "6cdcdf447743ee5e35e860872578e06704e0330b5a50c8723710ec0aa4703f44",
        "rows": 536,
        "conditions": ("Vin 3.30 V; 4 binding PVT corners x load x Cout x ESR "
                       "(#64 base matrix + refinement round 1)"),
        "subset": ("failed_rows",
                   "rows the combined #64 analysis marks `failed` "
                   "(no -180 deg crossing, gain margin unmeasured)"),
    },
}
OUT_NAME = "row10-margins"


class Row10Error(Exception):
    pass


def sha256_file(rel):
    with open(os.path.join(REPO, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def fmt(x):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "True" if x else "False"
    if isinstance(x, float):
        return f"{x:.9g}"
    return str(x)


def rnd(x):
    return None if x is None else float(f"{x:.9g}")


def trace_path(ds, r):
    res = RES_SFX[r["res_section"]]
    if ds == "legacy":
        return (f"{SIM}/corners/{DATASETS[ds]['record_id']}/"
                f"loopgain_{r['corner']}_{r['temp_c']}c_{res}_ac.csv")
    return (f"{SIM}/corners/{r['source']}/loopgain_dyn_{r['corner']}_{r['temp_c']}c_{res}"
            f"_i{r['load_ua']}ua_c{r['cout_nf']}nf_e{r['esr_mohm']}mohm_ac.csv")


def _close(a, b, ctx, what):
    if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9):
        raise Row10Error(f"{ctx}: {what} {b!r} from the trace disagrees with the record {a!r}")


def cross_check(ds, r, m, ctx):
    """The trace must reproduce the record minted from it, and the rule must
    never turn a recorded miss into anything but a fail."""
    if not m or not m["valid"]:
        raise Row10Error(f"{ctx}: trace missing, empty or invalid")
    z = m["zero_db_crossings"]
    if int(r["n_0db_crossings"]) != len(z):
        raise Row10Error(f"{ctx}: record has {r['n_0db_crossings']} 0 dB crossings, trace {len(z)}")
    if z:
        _close(float(r["phase_margin_deg"]), 180.0 + z[0]["phase_deg"], ctx, "first-crossing PM")
        _close(float(r["phase_margin_worst_deg"]), min(180.0 + c["phase_deg"] for c in z),
               ctx, "recorded worst-crossing PM (180 + phase)")
    cc = m["critical_crossings"]
    if ds == "legacy" and int(r["n_gain_margin_crossings"]) != len(cc):
        raise Row10Error(f"{ctx}: record has {r['n_gain_margin_crossings']} -180 deg crossings, trace {len(cc)}")
    if r.get("gain_margin_db", "") != "":
        if not cc:
            raise Row10Error(f"{ctx}: record has a gain margin but the trace has no -180 deg crossing")
        _close(float(r["gain_margin_db"]), -cc[0]["gain_db"], ctx, "first -180 deg GM")
    elif cc:
        raise Row10Error(f"{ctx}: record has no gain margin but the trace has a -180 deg crossing")
    # no-loosening guard
    if r.get("phase_margin_deg", "") != "" and float(r["phase_margin_deg"]) < am.PM_BOUND_DEG \
            and m["pm"]["verdict"] != "fail":
        raise Row10Error(f"{ctx}: recorded PM miss classified {m['pm']['verdict']}")
    if r.get("gain_margin_db", "") != "" and float(r["gain_margin_db"]) < am.GM_BOUND_DB \
            and m["gm"]["verdict"] != "fail":
        raise Row10Error(f"{ctx}: recorded GM miss classified {m['gm']['verdict']}")


def in_subset(ds, r):
    if ds == "legacy":
        return int(r["n_0db_crossings"]) != 1
    return r["status"] == "failed"


def classify(ds):
    cfg = DATASETS[ds]
    got = sha256_file(cfg["record_csv"])
    if got != cfg["record_sha256"]:
        raise Row10Error(f"{cfg['record_csv']} sha256 {got} differs from the pin {cfg['record_sha256']}")
    with open(os.path.join(REPO, cfg["record_csv"]), newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != cfg["rows"]:
        raise Row10Error(f"{cfg['record_csv']}: {len(rows)} rows, expected {cfg['rows']}")
    out = []
    seen = set()
    for i, r in enumerate(rows):
        rel = trace_path(ds, r)
        if rel in seen:
            raise Row10Error(f"{cfg['record_csv']} row {i + 2}: duplicate point {rel}")
        seen.add(rel)
        ctx = f"{ds} row {i + 2} ({rel})"
        if not os.path.isfile(os.path.join(REPO, rel)):
            raise Row10Error(f"{ctx}: committed trace missing")
        m = am.classify_margins(os.path.join(REPO, rel))
        cross_check(ds, r, m, ctx)
        out.append((r, m, rel, sha256_file(rel)))
    return out


COLS_LEGACY = ["corner", "temp_c", "res_section"]
COLS_DOE = ["corner", "temp_c", "res_section", "load_ua", "cout_nf", "esr_mohm", "doe_status"]
COLS = ["record_n_0db_crossings", "record_phase_margin_deg", "record_phase_margin_worst_deg",
        "record_gain_margin_db", "n_zero_db_crossings", "zero_db_crossings_hz_dir_margin_deg",
        "pm_deg", "pm_verdict", "pm_reasons", "n_critical_crossings",
        "critical_crossings_hz_gain_db", "gm_db", "gm_above_ceiling_lower_bound_db", "gm_verdict",
        "gm_reasons", "low_end_gain_db", "low_end_ok", "ceiling_gain_db",
        "ceiling_last_decade_change_db", "ceiling_bounded", "nyquist_class", "trace", "trace_sha256"]


def csv_bytes(ds, items):
    head = (COLS_LEGACY if ds == "legacy" else COLS_DOE) + COLS
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    for r, m, rel, h in items:
        coords = [r["corner"], r["temp_c"], r["res_section"]]
        if ds == "doe":
            coords += [r["load_ua"], r["cout_nf"], r["esr_mohm"], r["status"]]
        z, c = m["zero_db_crossings"], m["critical_crossings"]
        w.writerow(coords + [
            r["n_0db_crossings"], r["phase_margin_deg"], r["phase_margin_worst_deg"],
            r["gain_margin_db"], len(z),
            ";".join(f"{fmt(x['freq_hz'])}@{x['direction']}@{fmt(x['margin_deg'])}" for x in z),
            fmt(m["pm"]["value_deg"]), m["pm"]["verdict"], "|".join(m["pm"]["reasons"]), len(c),
            ";".join(f"{fmt(x['freq_hz'])}@{fmt(x['gain_db'])}" for x in c),
            fmt(m["gm"]["value_db"]), fmt(m["gm"]["above_ceiling_lower_bound_db"]),
            m["gm"]["verdict"], "|".join(m["gm"]["reasons"]),
            fmt(m["low_end"]["gain_db"]), fmt(m["low_end"]["ok"]),
            fmt(m["ceiling"]["gain_db"]), fmt(m["ceiling"]["last_decade_gain_change_db"]),
            fmt(m["ceiling"]["bounded"]), m["nyquist"]["class"], rel, h])
    return buf.getvalue().encode("utf-8")


def _count(vals):
    d = {}
    for v in vals:
        d[v] = d.get(v, 0) + 1
    return dict(sorted(d.items()))


def _rng(vals):
    vals = [v for v in vals if v is not None]
    return {"min": rnd(min(vals)), "max": rnd(max(vals))} if vals else None


def summarize(items):
    ms = [m for _, m, _, _ in items]
    return {
        "points": len(items),
        "pm_verdicts": _count(m["pm"]["verdict"] for m in ms),
        "gm_verdicts": _count(m["gm"]["verdict"] for m in ms),
        "pm_reasons": _count("|".join(m["pm"]["reasons"]) for m in ms),
        "gm_reasons": _count("|".join(m["gm"]["reasons"]) for m in ms),
        "nyquist_class": _count(m["nyquist"]["class"] for m in ms),
        "n_zero_db_crossings": _count(len(m["zero_db_crossings"]) for m in ms),
        "n_critical_crossings": _count(len(m["critical_crossings"]) for m in ms),
        "pm_deg_range": _rng([m["pm"]["value_deg"] for m in ms]),
        "first_crossing_margin_deg_range": _rng(
            [m["zero_db_crossings"][0]["margin_deg"] for m in ms if m["zero_db_crossings"]]),
        "later_crossing_margin_deg_range": _rng(
            [c["margin_deg"] for m in ms for c in m["zero_db_crossings"][1:]]),
        "gm_db_range": _rng([m["gm"]["value_db"] for m in ms]),
        "low_end_ok": sum(1 for m in ms if m["low_end"]["ok"]),
        "low_end_gain_db_range": _rng([m["low_end"]["gain_db"] for m in ms]),
        "ceiling_bounded": sum(1 for m in ms if m["ceiling"]["bounded"]),
        "ceiling_gain_db_range": _rng([m["ceiling"]["gain_db"] for m in ms]),
        "ceiling_last_decade_change_db_range": _rng(
            [m["ceiling"]["last_decade_gain_change_db"] for m in ms]),
    }


def build(ds):
    cfg = DATASETS[ds]
    items = classify(ds)
    cbytes = csv_bytes(ds, items)
    sub_name, sub_desc = cfg["subset"]
    doc = {
        "schema_version": 1,
        "rule": "DR-0014 (proposed; row 10 stays Open, nothing ratified)",
        "decision_record": DR,
        "dataset": ds,
        "record": {"id": cfg["record_id"], "csv": cfg["record_csv"], "sha256": cfg["record_sha256"],
                   "conditions": cfg["conditions"]},
        "bounds": {"pm_deg": am.PM_BOUND_DEG, "gm_db": am.GM_BOUND_DB,
                   "ceiling_floor_db": am.CEILING_FLOOR_DB},
        "classifier": {p: sha256_file(p) for p in (f"{SIM}/ac_metrics.py", f"{SIM}/dc_metrics.py",
                                                   f"{SIM}/row10_margins.py")},
        "traces_verified": len(items),
        "cross_checks": ("every trace reproduces its record's 0 dB crossing count, first-crossing PM, "
                         "recorded worst-crossing PM and first -180 deg GM; every recorded PM/GM miss "
                         "classifies as fail (no-loosening guard)"),
        "csv": {"path": f"{SIM}/evidence/{cfg['record_id']}/{OUT_NAME}.csv",
                "sha256": hashlib.sha256(cbytes).hexdigest()},
        "summary_all": summarize(items),
        "subset": {"name": sub_name, "definition": sub_desc,
                   "summary": summarize([x for x in items if in_subset(ds, x[0])])},
        "not_claimed": [
            "no new simulation; no historical record edited",
            "no ratification: DR-0014 is proposed and row 10 stays Open (DR-0007)",
            "no claim about frequencies above the sweep ceiling or between sampled operating points",
        ],
    }
    jbytes = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
    return {f"{OUT_NAME}.csv": cbytes, f"{OUT_NAME}.json": jbytes,
            f"{OUT_NAME}.md": render_md(doc).encode("utf-8")}


def _r(x):
    return "-" if not x else f"{x['min']:.4g} .. {x['max']:.4g}"


def _d(d):
    return ", ".join(f"{k or '(none)'}: {v}" for k, v in d.items())


def render_md(doc):
    L = [f"# Row 10 margin classification (DR-0014, proposed): `{doc['record']['id']}`", "",
         "<!-- GENERATED by sim/ldo-cmos5l-pvt-sweep/row10_margins.py -- do not edit; "
         "`--check` byte-compares. -->", "",
         f"Offline re-classification of the committed loop-gain traces of record "
         f"`{doc['record']['csv']}` ({doc['record']['conditions']}) under "
         f"[`DR-0014`](../../../../{doc['decision_record']}). No simulation was run and no record "
         f"was edited. Bounds: PM >= {doc['bounds']['pm_deg']:g} deg, GM >= {doc['bounds']['gm_db']:g} dB, "
         f"sweep-ceiling floor {doc['bounds']['ceiling_floor_db']:g} dB. "
         f"{doc['traces_verified']} traces verified: {doc['cross_checks']}.", ""]
    for title, s in (("All points", doc["summary_all"]),
                     (f"Subset `{doc['subset']['name']}`: {doc['subset']['definition']}",
                      doc["subset"]["summary"])):
        L += [f"## {title}", "",
              "| quantity | value |", "|---|---|",
              f"| points | {s['points']} |",
              f"| PM verdicts | {_d(s['pm_verdicts'])} |",
              f"| PM reasons | {_d(s['pm_reasons'])} |",
              f"| GM verdicts | {_d(s['gm_verdicts'])} |",
              f"| GM reasons | {_d(s['gm_reasons'])} |",
              f"| 0 dB crossings per trace | {_d(s['n_zero_db_crossings'])} |",
              f"| -180 deg (critical-line) crossings per trace | {_d(s['n_critical_crossings'])} |",
              f"| scored PM (min over crossings) [deg] | {_r(s['pm_deg_range'])} |",
              f"| first-crossing margin [deg] | {_r(s['first_crossing_margin_deg_range'])} |",
              f"| later-crossing margins [deg] | {_r(s['later_crossing_margin_deg_range'])} |",
              f"| in-band GM (min over -180 deg crossings) [dB] | {_r(s['gm_db_range'])} |",
              f"| low-end premise holds | {s['low_end_ok']} of {s['points']} "
              f"(gain at 1 Hz {_r(s['low_end_gain_db_range'])} dB) |",
              f"| sweep ceiling bounded | {s['ceiling_bounded']} of {s['points']} |",
              f"| loop gain at the ceiling [dB] | {_r(s['ceiling_gain_db_range'])} |",
              f"| loop-gain change over the last decade [dB] | "
              f"{_r(s['ceiling_last_decade_change_db_range'])} |",
              f"| Nyquist bookkeeping | {_d(s['nyquist_class'])} |", ""]
    L += ["Per-point rows: `row10-margins.csv` (trace path and sha256 on every row).", "",
          "Not claimed: " + "; ".join(doc["not_claimed"]) + ".", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="byte-compare against the committed files")
    args = ap.parse_args(argv)
    bad = []
    try:
        for ds, cfg in DATASETS.items():
            out_dir = os.path.join(REPO, SIM, "evidence", cfg["record_id"])
            for name, data in build(ds).items():
                p = os.path.join(out_dir, name)
                if args.check:
                    if not os.path.isfile(p):
                        bad.append(f"{p}: missing")
                    elif open(p, "rb").read() != data:
                        bad.append(f"{p}: differs from regeneration")
                else:
                    os.makedirs(out_dir, exist_ok=True)
                    with open(p, "wb") as fh:
                        fh.write(data)
    except Row10Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if bad:
        print("row10_margins --check FAILED:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print("row10_margins: " + ("committed files reproduce exactly" if args.check else "wrote")
          + f" ({', '.join(DATASETS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
