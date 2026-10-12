#!/usr/bin/env python3
"""Issue #155 offline re-reductions on the re-stamped-PDK grids. stdlib only.

Re-runs the committed offline reducers on the NEW-pin records, in memory, and
compares their results with the committed old-pin reductions. It writes no
evidence file under any campaign directory (only its own comparison json,
with --write) and runs no simulator: these are re-reductions of committed
data, not simulation reruns (sim/migration-inventory-155.md).

  item5   item5_evidence.py (through item5_grid.py's shared grid contract) on
          the raw DC grids of PVT record 20261012-060932-c53f0177, compared
          with the committed evidence/20261011-070111-5391c68/
          dc-informational-summary.csv. item5_evidence.py's provenance text
          names its own record and old pin, so its inventory is not minted for
          the new record; only the numeric summary is compared.
  doe     row10_margins.py's `doe` classification (DR-0014) applied to the
          new-pin DoE record 20261012-080951-142dac4a, compared point by point
          with the committed evidence/20261010-101245-6df50fd/row10-margins.*
          (old pin AND pre-#89 design, so differences are not PDK-only).

  pdk_controls
          byte comparison of the design-held-constant PDK controls (dropout:
          pre-#89 netlists on the new pin vs record 20261010-111618-19e8e39;
          dynamic DoE: current netlists on the OLD pin vs the new-pin DoE
          records), record CSVs up to record ids and every raw trace.

The row-10 classification of the 45-point PVT record is NOT here: it is a
committed output of row10_record.py (evidence/20261012-060932-c53f0177/),
checked by CI's `row10_record.py --check`.

    python3 sim/migration-155-rereduce.py            # print the comparison
    python3 sim/migration-155-rereduce.py --write    # (re)write migration-155-rereduce.json
    python3 sim/migration-155-rereduce.py --check    # compare with the committed json
"""
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PVT = os.path.join(HERE, "ldo-cmos5l-pvt-sweep")
sys.path.insert(0, PVT)

import item5_evidence as ev  # noqa: E402
import item5_grid  # noqa: E402
import row10_margins as rm  # noqa: E402

NEW_PVT = "20261012-060932-c53f0177"
OLD_PVT = ev.RECORD_ID
NEW_DOE = "20261012-080951-142dac4a"
OLD_DOE = rm.DATASETS["doe"]["record_id"]


def item5():
    item5_grid.install()
    saved = (ev.CORNERS_DIR, ev.RECORD_CSV)
    try:
        ev.CORNERS_DIR = f"sim/ldo-cmos5l-pvt-sweep/corners/{NEW_PVT}"
        ev.RECORD_CSV = f"sim/ldo-cmos5l-pvt-sweep/records/{NEW_PVT}.csv"
        with open(os.path.join(ev.REPO, ev.RECORD_CSV)) as fh:
            rows = list(csv.DictReader(fh))
        pts = {(c, t, r): ev.analyse_point(p) for c, t, r, p in ev.point_files()}
        mism = ev.reproduce_record(pts, rows)
        text = ev.csv_text(pts)
    finally:
        ev.CORNERS_DIR, ev.RECORD_CSV = saved
        item5_grid.uninstall()
    with open(os.path.join(ev.REPO, f"sim/ldo-cmos5l-pvt-sweep/evidence/{OLD_PVT}/"
                                    "dc-informational-summary.csv")) as fh:
        old = fh.read()
    return {"new_record": NEW_PVT, "compared_with": f"evidence/{OLD_PVT}/dc-informational-summary.csv",
            "points": len(pts), "points_valid": sum(1 for a in pts.values() if a.get("valid")),
            "raw_grid_reproduces_record_csv": not mism,
            "dc_informational_summary_identical": text == old}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def doe():
    saved = rm.DATASETS["doe"]
    rel = f"{rm.SIM}/records/{NEW_DOE}.dynamic-doe.csv"
    rm.DATASETS["doe"] = dict(saved, record_id=NEW_DOE, record_csv=rel, record_sha256=rm.sha256_file(rel))
    try:
        out = rm.build("doe")
    finally:
        rm.DATASETS["doe"] = saved
    new_doc = json.loads(out[f"{rm.OUT_NAME}.json"])
    with open(os.path.join(rm.REPO, rm.SIM, "evidence", OLD_DOE, f"{rm.OUT_NAME}.json")) as fh:
        old_doc = json.load(fh)
    with open(os.path.join(rm.REPO, rm.SIM, "evidence", OLD_DOE, f"{rm.OUT_NAME}.csv")) as fh:
        old_rows = list(csv.DictReader(fh))
    new_rows = list(csv.DictReader(io.StringIO(out[f"{rm.OUT_NAME}.csv"].decode("utf-8"))))

    def key(r):
        return (r["corner"], r["temp_c"], r["res_section"], r["load_ua"], r["cout_nf"], r["esr_mohm"])

    o = {key(r): r for r in old_rows}
    n = {key(r): r for r in new_rows}
    fields = ("doe_status", "pm_verdict", "pm_reasons", "gm_verdict", "gm_reasons")
    changed = sorted(k for k in n if k in o and any(n[k][f] != o[k][f] for f in fields))
    deltas = {}
    for c in ("pm_deg", "gm_db"):
        d = [abs(_f(n[k][c]) - _f(o[k][c])) for k in n
             if k in o and _f(n[k][c]) is not None and _f(o[k][c]) is not None]
        deltas[c] = {"max_abs_delta": round(max(d), 6) if d else None, "points": len(d)}
    verdicts = ("pm_verdicts", "gm_verdicts", "gm_reasons", "pm_reasons")
    return {"new_record": NEW_DOE, "compared_with": f"evidence/{OLD_DOE}/{rm.OUT_NAME}.*",
            "same_point_set": set(o) == set(n), "points": len(n),
            "points_with_verdict_reason_or_status_change": len(changed),
            "summary_verdict_counts_identical": all(new_doc["summary_all"][v] == old_doc["summary_all"][v]
                                                    for v in verdicts),
            "summary_verdict_counts": {v: new_doc["summary_all"][v] for v in verdicts},
            "metric_deltas": deltas,
            "caveat": "old record ran the pre-#89 design on the old pin; the delta mixes both"}


def _read(rel):
    with open(os.path.join(rm.REPO, rel), "rb") as fh:
        return fh.read()


def _same_files(dir_a, dir_b, suffix):
    """Byte-compare every <suffix> file of committed corners dir_a with dir_b."""
    a = sorted(f for f in os.listdir(os.path.join(rm.REPO, dir_a)) if f.endswith(suffix))
    b = sorted(f for f in os.listdir(os.path.join(rm.REPO, dir_b)) if f.endswith(suffix))
    differ = [f for f in a if f in b and _read(f"{dir_a}/{f}") != _read(f"{dir_b}/{f}")]
    return {"files": len(a), "same_names": a == b, "differing": len(differ)}


#: Design-held-constant controls minted for #155 (README "Re-run on the
#: re-stamped PDK"): (label, control record, record it is compared with,
#: record-file suffix, {control id: compared id} substitutions, raw suffix).
CONTROLS = (
    ("dropout: pre-#89 netlists on the NEW pin vs the same netlists on the old pin",
     "20261012-094155-934dbd7c", "20261010-111618-19e8e39", ".dropout.csv", {}, "_dc.csv"),
    ("dynamic DoE base: current netlists on the OLD pin vs the same netlists on the new pin",
     "20261012-100716-934dbd7c", "20261012-074813-c94873ba", ".dynamic-doe.csv", {}, "_ac.csv"),
    ("dynamic DoE refinement: current netlists on the OLD pin vs the same netlists on the new pin",
     "20261012-102846-934dbd7c", "20261012-080951-142dac4a", ".dynamic-doe.csv",
     {"20261012-100716-934dbd7c": "20261012-074813-c94873ba"}, "_ac.csv"),
)


def controls():
    out = []
    for label, ctl, ref, suffix, subs, raw in CONTROLS:
        a = _read(f"{rm.SIM}/records/{ctl}{suffix}").decode("utf-8").replace(ctl, ref)
        for k, v in subs.items():
            a = a.replace(k, v)
        b = _read(f"{rm.SIM}/records/{ref}{suffix}").decode("utf-8")
        out.append({"control": label, "control_record": ctl, "compared_with": ref,
                    "record_csv_identical_up_to_record_ids": a == b,
                    "raw_traces": _same_files(f"{rm.SIM}/corners/{ref}", f"{rm.SIM}/corners/{ctl}", raw)})
    return out


OUT = os.path.join(HERE, "migration-155-rereduce.json")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = json.dumps({"item5": item5(), "doe_row10": doe(), "pdk_controls": controls()},
                      indent=1, sort_keys=True) + "\n"
    if argv == ["--check"]:
        with open(OUT) as fh:
            if fh.read() != text:
                sys.exit("migration-155-rereduce: committed migration-155-rereduce.json is stale")
        print("migration-155-rereduce: committed output reproduces")
        return
    if argv == ["--write"]:
        with open(OUT, "w") as fh:
            fh.write(text)
        print(f"migration-155-rereduce: wrote {os.path.relpath(OUT, rm.REPO)}")
        return
    if argv:
        sys.exit("usage: migration-155-rereduce.py [--write | --check]")
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
