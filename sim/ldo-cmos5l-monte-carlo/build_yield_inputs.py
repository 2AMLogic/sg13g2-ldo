#!/usr/bin/env python3
"""Split `klt sim` Monte Carlo reports into per-population `klt yield`
sample-set documents (issue #56).

Why this exists: `klt yield` pools every Monte Carlo draw of a report into ONE
population (and warns that a pooled multi-corner estimate is a worst-case
envelope, not a distribution anyone sampled -- docs/cli/yield.md "Pooled, not
per corner"). Each process/temperature point of this campaign is its own
population, so the raw report is split by originating corner and each
population is analysed on its own. It also attaches the negative control,
which `klt sim` cannot carry on its own report (klayout-tools#2563).

The split is purely mechanical -- no value is edited, rounded, dropped or
reordered:

  * draws are grouped by the originating corner id (`corner_id` with klt
    sim's `/mc<i>` suffix stripped) and ordered by `sample_index`;
  * a draw whose measurement is null / non-finite / status "error" stays in
    `samples` as null -- `klt yield` counts it into `errored` (a tooling
    failure, excluded from the yield denominator, and warned about with the
    whole-draw figure), unless `--null-policy failed_unmeasurable` asks for
    it to be counted as a design failure instead;
  * a draw klt sim graded "inconclusive" (corner- or measurement-level) is
    counted into `inconclusive`, never silently absorbed;
  * every input draw is accounted for: the script refuses to write anything
    if samples + errored-nulls + inconclusive != draws read.

Stdlib only. Usage (see run_campaign.sh for the exact invocations):

  build_yield_inputs.py --report RAW.sim.json [--negctl NEG.sim.json] \
      --outdir DIR [--target-yield 0.99] [--measurement vout_v] \
      [--no-target-yield] [--null-policy errored|failed_unmeasurable]

Writes DIR/<label>.samples.json per population (label: process_tempC, plus
the supply point when the corner carries one) and, with --negctl,
DIR/<label>.negctl.samples.json for each negative-control population on its
own (so the known-bad variant also gets its own pass/fail yield verdict).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import OrderedDict
from pathlib import Path

_MC_SUFFIX = re.compile(r"/mc\d+$")


def _value(corner: dict, name: str):
    """Return (value_or_None, state) for one draw's measurement.

    state is "ok", "null" or "inconclusive". A missing, non-numeric or
    non-finite value is "null" (it carries no information) and is never
    coerced to a number.
    """
    if corner.get("status") == "inconclusive":
        return None, "inconclusive"
    for m in corner.get("measurements", []):
        if m.get("name") != name:
            continue
        if m.get("status") == "inconclusive":
            return None, "inconclusive"
        v = m.get("value")
        if (
            m.get("status") == "error"
            or not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
        ):
            return None, "null"
        return float(v), "ok"
    return None, "null"


def origin_id(corner: dict) -> str:
    return _MC_SUFFIX.sub("", str(corner.get("corner_id", "")))


def label_for(corner: dict) -> str:
    """Filesystem-safe population label: process_<T>C[_<src><V>V...]."""
    parts = [str(corner.get("process")), f"{corner.get('temperature_c')}C"]
    for k, v in sorted((corner.get("supply_v") or {}).items()):
        parts.append(f"{k}{v}V")
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", "_".join(parts))


def split_report(report: dict, name: str) -> "OrderedDict[str, dict]":
    """Group Monte Carlo draws by originating corner, preserving corner order
    and sample_index order. Deterministic (non-sampled) corners are ignored,
    as `klt yield` itself ignores them."""
    groups: "OrderedDict[str, list]" = OrderedDict()
    meta: dict[str, dict] = {}
    for c in report.get("corners", []):
        mc = c.get("monte_carlo")
        if not mc:
            continue
        oid = origin_id(c)
        groups.setdefault(oid, []).append((mc.get("sample_index", 0), c))
        meta.setdefault(oid, c)
    out: "OrderedDict[str, dict]" = OrderedDict()
    for oid, items in groups.items():
        items.sort(key=lambda t: t[0])
        idx = [i for i, _ in items]
        if len(set(idx)) != len(idx):
            raise SystemExit(f"{oid}: duplicate sample_index in report")
        samples, nulls, inconclusive = [], 0, 0
        for _, c in items:
            v, state = _value(c, name)
            if state == "inconclusive":
                inconclusive += 1
            else:
                if state == "null":
                    nulls += 1
                samples.append(v)
        if len(samples) + inconclusive != len(items):
            raise SystemExit(f"{oid}: draw accounting does not close")
        out[oid] = {
            "label": label_for(meta[oid]),
            "samples": samples,
            "nulls": nulls,
            "inconclusive": inconclusive,
            "draws": len(items),
            "process": meta[oid].get("process"),
            "temperature_c": meta[oid].get("temperature_c"),
        }
    return out


def _limits(report: dict, name: str, target_yield):
    for m in report.get("measurements", []):
        if m.get("name") == name:
            lim = {k: v for k, v in (m.get("limits") or {}).items()
                   if k in ("min", "max", "exclusive_min", "exclusive_max")}
            if target_yield is not None:
                lim["target_yield"] = target_yield
            return lim, m.get("unit")
    raise SystemExit(f"measurement {name!r} not in report")


def _apply_null_policy(samples: list, policy: str) -> tuple[list, dict]:
    """errored: nulls stay in `samples` (klt yield counts them as errored).
    failed_unmeasurable: nulls are removed from `samples` and counted as
    design failures instead."""
    if policy == "errored":
        return samples, {}
    kept = [s for s in samples if s is not None]
    return kept, {"failed_unmeasurable": len(samples) - len(kept)}


def _entry(name, unit, limits, pop, policy, source_corners):
    samples, extra = _apply_null_policy(pop["samples"], policy)
    e = {"name": name, "samples": samples, "inconclusive": pop["inconclusive"],
         "limits": dict(limits), "source_corners": source_corners}
    e.update(extra)
    if unit:
        e["unit"] = unit
    return e


def build(report: dict, negctl: dict | None, name: str, target_yield,
          nc_description: str, policy: str = "errored"):
    """Return (docs, negctl_docs): label -> sample-set document."""
    limits, unit = _limits(report, name, target_yield)
    pops = split_report(report, name)
    nc_pops = split_report(negctl, name) if negctl else OrderedDict()
    # A negative-control population attaches to the nominal population drawn
    # at the same (process, temperature) -- it differs only in the one
    # forced source.
    nc_by_pt = {(p["process"], p["temperature_c"]): (oid, p) for oid, p in nc_pops.items()}
    docs: "OrderedDict[str, dict]" = OrderedDict()
    for oid, pop in pops.items():
        e = _entry(name, unit, limits, pop, policy, [oid])
        hit = nc_by_pt.get((pop["process"], pop["temperature_c"]))
        if hit is not None:
            nc_oid, nc = hit
            nc_samples, nc_extra = _apply_null_policy(nc["samples"], policy)
            e["negative_control"] = {"samples": nc_samples,
                                     "description": f"{nc_description} [{nc_oid}]"}
            e["negative_control"].update(nc_extra)
        docs[pop["label"]] = {"measurements": [e]}
    nc_docs: "OrderedDict[str, dict]" = OrderedDict()
    for oid, pop in nc_pops.items():
        nc_docs[pop["label"]] = {"measurements": [_entry(name, unit, limits, pop, policy, [oid])]}
    return docs, nc_docs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--negctl", type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--measurement", default="vout_v")
    ap.add_argument("--target-yield", type=float, default=0.99,
                    help="planning yield the lower confidence bound is checked "
                    "against (README.md 'Sample size'); not a ratified spec value")
    ap.add_argument("--no-target-yield", action="store_true",
                    help="declare no target_yield (klt yield then reports, never "
                    "fails) -- for diagnostic populations that make no claim")
    ap.add_argument("--null-policy", choices=("errored", "failed_unmeasurable"),
                    default="errored")
    ap.add_argument(
        "--nc-description",
        default="deterministic negative control: VREF forced 0.90 V -> 0.93 V "
        "(+30 mV, ~+60 mV on VOUT through the 2:1 divider), same netlist, "
        "corner, seed and sample indices as the nominal population",
    )
    a = ap.parse_args(argv)
    report = json.loads(a.report.read_text())
    negctl = json.loads(a.negctl.read_text()) if a.negctl else None
    target = None if a.no_target_yield else a.target_yield
    docs, nc_docs = build(report, negctl, a.measurement, target,
                          a.nc_description, a.null_policy)
    if not docs:
        print("no Monte Carlo draws in report", file=sys.stderr)
        return 1
    a.outdir.mkdir(parents=True, exist_ok=True)
    for suffix, group in ((".samples.json", docs), (".negctl.samples.json", nc_docs)):
        for label, doc in group.items():
            p = a.outdir / f"{label}{suffix}"
            p.write_text(json.dumps(doc, indent=1) + "\n")
            m = doc["measurements"][0]
            print(f"{p.name}: {len(m['samples'])} samples, "
                  f"{sum(s is None for s in m['samples'])} null, "
                  f"{m['inconclusive']} inconclusive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
