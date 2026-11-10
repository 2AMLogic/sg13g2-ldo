#!/usr/bin/env python3
"""Re-run `klt yield` on every committed samples document and fail on drift.

For each `<record>/yield/*.samples.json` and
`<record>/yield/attribution/*.samples.json` this runs
`klt yield <base>.samples.json --format json` from the directory holding the
file (exactly as `run_campaign.sh analyse` does) and compares:

  * the exit code with the `<base>: klt yield exit N` line in `exit-codes.txt`,
  * the top-level `status`, and
  * for every measurement, its `yield` block and its `negative_control` block

with the committed `<base>.yield.json`. Any difference, a missing
`exit-codes.txt` entry or committed report, or an entry without a samples
document is a failure. Nothing under `records/` is written.

Usage: check_yield_verdicts.py [--klt PATH] [RECORD_DIR ...]
(default: every directory under records/ beside this script).

`<record>/yield/attribution/` (zero-spread attribution populations) is checked
like the rest. Two of those reports (`tt_nom_27C` in each of two records) were
committed from klt 0.7.0 and no longer reproduce: since klt 0.8.0 a
zero-spread population is classified `degenerate` and its `normal` yield block
is null (klayout-tools#5058, documented in #5066). Records are append-only, so
they are not edited; SUPERSEDED names each one and the re-derived report
(klt 0.8.0, the CI pin; same samples document) under `rederived/`. A superseded report is
not re-run; the gate instead requires that the re-derived location exists, that
its samples document is byte-identical to the superseded one, and that the
re-derived reports reproduce under the pinned klt.
Stdlib only; needs a klt whose klt_yield_native extension imports.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXIT_RE = re.compile(r"^(?P<base>.+): klt yield exit (?P<rc>\d+)\s*$")
FIELDS = ("yield", "negative_control")

# (record name, attribution base) -> (re-derived directory relative to HERE, reason).
SUPERSEDED = {
    ("20261009-003009-3ee8306", "tt_nom_27C"):
        ("rederived/20261009-003009-3ee8306-klt0.8.0", "klt 0.7.0 zero-spread yield block predates `degenerate` (klt 0.8.0)"),
    ("20261012-093854-934dbd7", "tt_nom_27C"):
        ("rederived/20261012-093854-934dbd7-klt0.8.0", "klt 0.7.0 zero-spread yield block predates `degenerate` (klt 0.8.0)"),
}


def run_klt(klt, directory, samples):
    """Run klt yield in `directory`; return (exit code, stdout)."""
    r = subprocess.run([klt, "yield", samples, "--format", "json"],
                       cwd=directory, capture_output=True, text=True)
    return r.returncode, r.stdout


def parse_exit_codes(path):
    codes = {}
    for line in path.read_text().splitlines():
        m = EXIT_RE.match(line)
        if m:
            codes[m["base"]] = int(m["rc"])
    return codes


def compare_reports(committed, fresh):
    """Return a list of drift descriptions between two klt yield reports."""
    out = []
    if committed.get("status") != fresh.get("status"):
        out.append(f"status {committed.get('status')!r} -> {fresh.get('status')!r}")
    cm = {m["name"]: m for m in committed.get("measurements", [])}
    fm = {m["name"]: m for m in fresh.get("measurements", [])}
    if set(cm) != set(fm):
        out.append(f"measurements {sorted(cm)} -> {sorted(fm)}")
    for name in sorted(set(cm) & set(fm)):
        for field in FIELDS:
            if cm[name].get(field) != fm[name].get(field):
                out.append(f"{name}.{field} differs from committed")
    return out


def check_dir(directory, run=run_klt, skip=()):
    """Check one yield directory; return a list of failure strings.

    Bases in `skip` (superseded reports) are not re-run."""
    directory = Path(directory)
    samples = sorted(directory.glob("*.samples.json"))
    ec = directory / "exit-codes.txt"
    if not ec.is_file():
        return [f"{directory}: no exit-codes.txt"] if samples else []
    codes = parse_exit_codes(ec)
    bases = [p.name[: -len(".samples.json")] for p in samples]
    fails = []
    for extra in sorted(set(codes) - set(bases)):
        fails.append(f"{directory}: exit-codes.txt entry {extra!r} has no samples document")
    for base in bases:
        if base in skip:
            continue
        tag = f"{directory}/{base}"
        if base not in codes:
            fails.append(f"{tag}: no exit-codes.txt entry")
            continue
        committed_path = directory / f"{base}.yield.json"
        if not committed_path.is_file():
            fails.append(f"{tag}: committed {base}.yield.json missing")
            continue
        rc, stdout = run(directory, f"{base}.samples.json")
        if rc != codes[base]:
            fails.append(f"{tag}: exit code {rc}, committed {codes[base]}")
        try:
            fresh = json.loads(stdout)
        except ValueError as e:
            fails.append(f"{tag}: klt yield output is not JSON ({e})")
            continue
        fails.extend(f"{tag}: {d}" for d in
                     compare_reports(json.loads(committed_path.read_text()), fresh))
    return fails


def yield_dirs(record):
    record = Path(record)
    return [record / "yield", record / "yield" / "attribution"]


def check_record(record, run=run_klt, superseded=SUPERSEDED, root=HERE):
    """Check one record (incl. attribution); return (failures, samples checked)."""
    record, root = Path(record), Path(root)
    fails, n = [], 0
    dirs = [d for d in yield_dirs(record) if d.is_dir()]
    if not dirs:
        return [f"{record}: no yield/ directory"], 0
    attribution = record / "yield" / "attribution"
    skip = set()
    for (rec_name, base), (rel, _reason) in sorted(superseded.items()):
        if rec_name != record.name:
            continue
        old = attribution / f"{base}.samples.json"
        new_dir = root / rel / "yield" / "attribution"
        new = new_dir / f"{base}.samples.json"
        tag = f"{attribution}/{base}"
        if not old.is_file():
            fails.append(f"{tag}: superseded entry has no samples document")
        elif not new.is_file():
            fails.append(f"{tag}: superseded but re-derived {new} is missing")
        elif old.read_bytes() != new.read_bytes():
            fails.append(f"{tag}: re-derived samples document differs from the superseded one")
        else:
            skip.add(base)
            fails.extend(check_dir(new_dir, run))
            n += 1
    for d in dirs:
        n += len(list(d.glob("*.samples.json"))) - (len(skip) if d == attribution else 0)
        fails.extend(check_dir(d, run, skip if d == attribution else ()))
    return fails, n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--klt", default="klt")
    ap.add_argument("records", nargs="*", type=Path)
    a = ap.parse_args(argv)
    records = a.records or sorted(p for p in (HERE / "records").iterdir() if p.is_dir())
    if not records:
        print("no records to check", file=sys.stderr)
        return 1
    fails, n = [], 0
    for rec in records:
        f, k = check_record(rec, lambda dd, smp: run_klt(a.klt, dd, smp))
        fails.extend(f)
        n += k
    if fails:
        print("\n".join(f"FAIL {f}" for f in fails), file=sys.stderr)
        return 1
    print(f"OK: {n} committed klt yield verdicts reproduce across {len(records)} record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
