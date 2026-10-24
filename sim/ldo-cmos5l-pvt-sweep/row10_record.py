#!/usr/bin/env python3
"""Run row10_margins.py's DR-0014 classification on another 45-point PVT record.

row10_margins.py is pinned by sha256 inside its own landed, append-only
outputs (evidence/<record-id>/row10-margins.json, `classifier`), and it names
its two datasets in code, so adding a record to it would rewrite landed
evidence. This thin wrapper (same pattern as item5_grid.py) instead runs the
unchanged `legacy` dataset logic -- same trace layout, cross-checks,
no-loosening guard, CSV/JSON/MD format -- against a different 45-point PVT
grid record. The output's `classifier` block also pins this wrapper.

    python3 sim/ldo-cmos5l-pvt-sweep/row10_record.py --record <record-id>  # (re)write
    python3 sim/ldo-cmos5l-pvt-sweep/row10_record.py --check               # CI: byte-compare

--check finds every evidence/<id>/row10-margins.json whose classifier block
names this wrapper, re-derives it from records/<id>.csv (whose sha256 must
still equal the pin recorded in that JSON) and the committed traces, and
byte-compares all three files. Offline, stdlib-only: no simulator, no PDK.
"""
import argparse
import contextlib
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import row10_margins as rm  # noqa: E402

SELF = f"{rm.SIM}/row10_record.py"
DS = "legacy"   # the 45-point PVT-grid layout; characterization/generate.py requires this name


@contextlib.contextmanager
def _as_legacy(cfg):
    saved = rm.DATASETS[DS]
    rm.DATASETS[DS] = cfg
    try:
        yield
    finally:
        rm.DATASETS[DS] = saved


def config(record_id, record_sha256):
    base = rm.DATASETS[DS]
    if record_id in {c["record_id"] for c in rm.DATASETS.values()}:
        raise rm.Row10Error(f"{record_id} is a row10_margins.py dataset; use that script")
    return dict(base, record_id=record_id, record_csv=f"{rm.SIM}/records/{record_id}.csv",
                record_sha256=record_sha256)


def build(record_id, record_sha256):
    with _as_legacy(config(record_id, record_sha256)):
        out = rm.build(DS)
    doc = json.loads(out[f"{rm.OUT_NAME}.json"])
    doc["classifier"][SELF] = rm.sha256_file(SELF)
    out[f"{rm.OUT_NAME}.json"] = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
    out[f"{rm.OUT_NAME}.md"] = rm.render_md(doc).encode("utf-8")
    return out


def committed():
    """(record_id, pinned record sha256) for every landed output of this wrapper."""
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
    g.add_argument("--record", help="45-point PVT record id under records/ to classify")
    g.add_argument("--check", action="store_true", help="byte-compare every committed output")
    args = ap.parse_args(argv)
    bad = []
    try:
        if args.check:
            todo = committed()
            if not todo:
                bad.append("no committed row10-margins.json names this wrapper")
        else:
            todo = [(args.record, rm.sha256_file(f"{rm.SIM}/records/{args.record}.csv"))]
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
        print("row10_record --check FAILED:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print("row10_record: " + ("committed files reproduce exactly" if args.check else "wrote")
          + f" ({', '.join(r for r, _ in todo)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
