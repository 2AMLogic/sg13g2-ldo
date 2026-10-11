#!/usr/bin/env python3
"""Run row10_margins.py's DR-0014 classification on a two-injection campaign
record (issue #135).

row10_margins.py is pinned by sha256 inside its own landed, append-only
outputs and names its datasets in code, so it is NOT edited to classify the
two-injection (Middlebrook) reconstruction. This thin wrapper follows the
row10_record.py pattern (override the `legacy` dataset in memory, restore on
exit), with one difference: the classified traces are the RECONSTRUCTED
combined traces `corners/<rid>/loopgain2_<corner>_<temp>c_r<label>_ac.csv`
(written by loopgain2.py from the raw two-injection probe exports), not
single-injection bench outputs, so the wrapper also overrides the dataset's
trace path. The classification rules themselves are the unchanged
ac_metrics.classify_margins -- no threshold, ceiling-floor, monotonicity or
crossing rule is touched, and row 10 stays Open either way.

    python3 sim/ldo-cmos5l-pvt-sweep/row10_loopgain2.py --record <rid>
    python3 sim/ldo-cmos5l-pvt-sweep/row10_loopgain2.py --check   # CI: byte-compare

--check finds every evidence/<id>/row10-margins.json whose classifier block
names this wrapper, re-derives it from the pinned comparison CSV
(records/<id>.loopgain2.csv) and the committed reconstructed traces, and
byte-compares all three files. Offline, stdlib-only: no simulator, no PDK.
"""
import argparse
import contextlib
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import row10_margins as rm  # noqa: E402
import loopgain2 as lg2  # noqa: E402

SELF = f"{rm.SIM}/row10_loopgain2.py"
DS = "legacy"   # the 45-point layout the classifier machinery expects

CONDITIONS = ("Vin 3.30 V, 1 mA, Cout 1 uF, ESR 0, Cc nominal; 45-point PVT grid; "
              "loop gain reconstructed from the two-injection (Middlebrook) "
              "benches tb_loopgain2v/tb_loopgain2i by loopgain2.py (issue #135)")


def trace_path(record_id, r):
    return (f"{rm.SIM}/corners/{record_id}/{lg2.TWO_PREFIX}"
            f"{r['corner']}_{r['temp_c']}c_r{r['res_section'][4:]}"
            f"{lg2.SUFFIX}")


@contextlib.contextmanager
def _patched(cfg, record_id):
    saved_ds = rm.DATASETS[DS]
    saved_tp = rm.trace_path
    rm.DATASETS[DS] = cfg
    rm.trace_path = lambda ds, r: trace_path(record_id, r)
    try:
        yield
    finally:
        rm.DATASETS[DS] = saved_ds
        rm.trace_path = saved_tp


def config(record_id, record_sha256):
    base = rm.DATASETS[DS]
    if record_id in {c["record_id"] for c in rm.DATASETS.values()}:
        raise rm.Row10Error(f"{record_id} is a row10_margins.py dataset; use that script")
    for c in _committed_cache:
        if c[0] == record_id:
            raise rm.Row10Error(f"{record_id} already has a wrapper evidence dir")
    return dict(base, record_id=record_id,
                record_csv=f"{rm.SIM}/records/{record_id}.loopgain2.csv",
                record_sha256=record_sha256, conditions=CONDITIONS)


def _mapped_rows(record_csv):
    """The comparison CSV's lg2_* columns under the classifier's legacy names."""
    with open(record_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            yield {("n_0db_crossings" if k == "lg2_n_0db_crossings" else
                    "phase_margin_deg" if k == "lg2_phase_margin_deg" else
                    "phase_margin_worst_deg" if k == "lg2_phase_margin_worst_deg" else
                    "gain_margin_db" if k == "lg2_gain_margin_db" else
                    "n_gain_margin_crossings" if k == "lg2_n_gain_margin_crossings" else k):
                   r[k] for k in ("corner", "temp_c", "res_section",
                                  "lg2_n_0db_crossings", "lg2_phase_margin_deg",
                                  "lg2_phase_margin_worst_deg", "lg2_gain_margin_db",
                                  "lg2_n_gain_margin_crossings")}


_committed_cache = []


def build(record_id, record_sha256):
    _committed_cache.clear()
    _committed_cache.extend(_other_wrappers(record_id))
    cfg = config(record_id, record_sha256)
    # rm.classify() reads the record csv with csv.DictReader and passes rows
    # to trace_path/cross_check; feed it the lg2-mapped rows by pointing the
    # dataset at a mapped COPY of the comparison csv.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mapped = os.path.join(tmp, "mapped.csv")
        with open(mapped, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["corner", "temp_c", "res_section",
                                              "n_0db_crossings", "phase_margin_deg",
                                              "phase_margin_worst_deg", "gain_margin_db",
                                              "n_gain_margin_crossings"])
            w.writeheader()
            n = 0
            for row in _mapped_rows(f"{rm.REPO}/{cfg['record_csv']}"):
                w.writerow(row)
                n += 1
        if n != 45:
            raise rm.Row10Error(f"{cfg['record_csv']}: {n} rows, expected 45")
        real_csv = cfg["record_csv"]
        cfg["record_csv"] = mapped
        # rm.classify pins sha256(record_csv); pin the ORIGINAL comparison csv.
        import row10_margins
        saved_sha = row10_margins.sha256_file

        def sha_of(path):
            return saved_sha(os.path.join(rm.REPO, real_csv)) if path == mapped else saved_sha(path)
        row10_margins.sha256_file = sha_of
        try:
            with _patched(cfg, record_id):
                out = rm.build(DS)
        finally:
            row10_margins.sha256_file = saved_sha
    doc = json.loads(out[f"{rm.OUT_NAME}.json"])
    # rm.build embedded cfg["record_csv"], which points at the throwaway
    # mapped copy during classification; restore the real committed path so
    # the evidence json is reproducible byte-for-byte by --check.
    doc["record"]["csv"] = real_csv
    doc["classifier"][SELF] = rm.sha256_file(SELF)
    doc["classifier"][f"{rm.SIM}/loopgain2.py"] = rm.sha256_file(f"{rm.SIM}/loopgain2.py")
    doc["method"] = ("two-injection (Middlebrook) reconstruction (loopgain2.py); "
                     "classification rules unchanged (DR-0014, proposed; row 10 stays Open)")
    out[f"{rm.OUT_NAME}.json"] = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
    out[f"{rm.OUT_NAME}.md"] = rm.render_md(doc).encode("utf-8")
    return out


def _other_wrappers(exclude_id):
    """Other records' wrapper pins (so --record refuses collisions)."""
    found = []
    for p in sorted(glob.glob(os.path.join(rm.REPO, rm.SIM, "evidence", "*", f"{rm.OUT_NAME}.json"))):
        try:
            with open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
        except ValueError:
            continue
        if SELF in doc.get("classifier", {}) and doc["record"]["id"] != exclude_id:
            found.append((doc["record"]["id"], doc["record"]["sha256"]))
    return found


def committed():
    """(record_id, pinned comparison-csv sha256) for every landed output of
    this wrapper."""
    found = []
    for p in sorted(glob.glob(os.path.join(rm.REPO, rm.SIM, "evidence", "*", f"{rm.OUT_NAME}.json"))):
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        if SELF in doc.get("classifier", {}):
            found.append((doc["record"]["id"], doc["record"]["sha256"]))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--record", help="two-injection campaign record id (records/<id>.loopgain2.csv)")
    g.add_argument("--check", action="store_true", help="byte-compare every committed output")
    args = ap.parse_args(argv)
    bad = []
    try:
        if args.check:
            todo = committed()
            if not todo:
                bad.append("no committed row10-margins.json names this wrapper")
        else:
            todo = [(args.record, rm.sha256_file(f"{rm.SIM}/records/{args.record}.loopgain2.csv"))]
        for rid, sha in todo:
            out_dir = os.path.join(rm.REPO, rm.SIM, "evidence", rid)
            for name, data in build(rid, sha).items():
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
    except (rm.Row10Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if bad:
        print("row10_loopgain2 --check FAILED:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print("row10_loopgain2: " + ("committed files reproduce exactly" if args.check else "wrote")
          + f" ({', '.join(r for r, _ in todo)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
