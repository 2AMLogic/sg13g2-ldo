#!/usr/bin/env python3
"""Cross-checks over one row-2 Monte Carlo record (issue #56). Stdlib only.

Reads <record>/raw/*.sim.json (the committed klt sim reports) and
<record>/yield/**/*.yield.json (the committed klt yield reports) and prints
one JSON document with:

  accounting    per request and population: draws, usable values, nulls,
                inconclusive, corner statuses, error diagnostics, fleet job
                ids, runner/client klt versions -- nothing silently dropped.
  seeds         every draw's ngspice seed is distinct within its request.
  reproduction  request-row2-repro.json (a separate fleet job, same seed,
                n=50) against the first 50 draws of the main tt population:
                identical seeds and values within REPRO_TOL_V.
  negctl_pairs  per sample index, negative-control minus nominal VOUT at
                the same seed: the forced VREF step must move every draw by
                ~2 x 30 mV with a spread far below the population spread.
  attribution   tt/27C with no mismatch, MOS mismatch only, rhigh mismatch
                only: the no-mismatch population must have zero spread and
                reproduce the committed corner value (sampler negative
                control); the two partial sigmas are compared (RSS) with the
                full-mismatch tt sigma.
  yield         the verdict fields of every committed klt yield report.

Usage: crosscheck.py <record-dir> [--csv <out.csv>]

--csv also writes one row per simulated draw (every request, every draw,
nothing filtered): the raw-sample table the record's .csv carries.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_yield_inputs as b  # noqa: E402

MEAS = "vout_v"
#: Agreement required between two fleet runs of the same seed: the printed
#: .meas mantissa has 10 significant digits (runner-preamble.cir), so two
#: identical solves agree to ~1e-9 V; 1 uV allows for a different instance
#: type's floating-point path without hiding a different draw (population
#: sigma is mV-scale).
REPRO_TOL_V = 1e-6
#: Committed MC-off corner value (sim/ldo-cmos5l-pvt-sweep record
#: 20260917-023832-7061e8f.csv, tt / 27 C / res_typ, vout_no_load_v).
COMMITTED_TT_NOM_V = 1.80030601
COMMITTED_TT_NOM_TOL_V = 1e-6


def load(p: Path):
    return json.loads(p.read_text())


def _mc_corners(report):
    return [c for c in report.get("corners", []) if c.get("monte_carlo")]


def accounting(name: str, report: dict) -> dict:
    env = report.get("environment", {})
    rem = env.get("remote", {}) or {}
    pops = {}
    for oid, p in b.split_report(report, MEAS).items():
        pops[oid] = {"draws": p["draws"], "usable": p["draws"] - p["nulls"] - p["inconclusive"],
                     "null": p["nulls"], "inconclusive": p["inconclusive"]}
    statuses: dict[str, int] = {}
    diags: dict[str, int] = {}
    for c in report.get("corners", []):
        statuses[c.get("status")] = statuses.get(c.get("status"), 0) + 1
        for d in c.get("diagnostics", []) or []:
            k = f"{d.get('severity')}:{d.get('code')}"
            diags[k] = diags.get(k, 0) + 1
    return {
        "request": name,
        "status": report.get("status"),
        "corner_count": report.get("corner_count", len(report.get("corners", []))),
        "corner_status_counts": statuses,
        "diagnostic_counts": diags,
        "populations": pops,
        "monte_carlo": env.get("monte_carlo"),
        # A sharded (remote.hosts > 1) run reports one entry per fleet job.
        "jobs": [{k: f.get(k) for k in ("job_id", "state", "exit_code", "instance_type",
                                        "physical_cores", "elapsed_seconds",
                                        "runner_klt_version", "client_klt_version",
                                        "runner_compatibility")}
                 for f in rem.get("fleet", [rem])],
        "engine_version": env.get("engine_version"),
    }


def seeds_distinct(report: dict) -> dict:
    seeds = [c["monte_carlo"].get("seed") for c in _mc_corners(report)]
    return {"draws": len(seeds), "distinct": len(set(seeds)), "ok": len(seeds) == len(set(seeds))}


def _by_index(report: dict, oid: str):
    out = {}
    for c in _mc_corners(report):
        if b.origin_id(c) == oid:
            v, st = b._value(c, MEAS)
            out[c["monte_carlo"]["sample_index"]] = (c["monte_carlo"].get("seed"), v, st)
    return out


def _only_oid(report: dict) -> str:
    oids = list(b.split_report(report, MEAS))
    if len(oids) != 1:
        raise SystemExit(f"expected one population, got {oids}")
    return oids[0]


def reproduction(mc: dict, repro: dict, nominal_oid: str) -> dict:
    a, r = _by_index(mc, nominal_oid), _by_index(repro, _only_oid(repro))
    rows, worst, seed_mismatch, missing = 0, 0.0, 0, 0
    for i, (seed, v, st) in sorted(r.items()):
        if i not in a:
            missing += 1
            continue
        s0, v0, st0 = a[i]
        rows += 1
        seed_mismatch += seed != s0
        if v is None or v0 is None:
            missing += (v is None) != (v0 is None)
            continue
        worst = max(worst, abs(v - v0))
    ok = rows == len(r) and seed_mismatch == 0 and missing == 0 and worst <= REPRO_TOL_V
    return {"compared": rows, "seed_mismatches": seed_mismatch, "value_presence_mismatches": missing,
            "max_abs_diff_v": worst, "tolerance_v": REPRO_TOL_V, "ok": ok}


def negctl_pairs(mc: dict, neg: dict, nominal_oid: str) -> dict:
    a, n = _by_index(mc, nominal_oid), _by_index(neg, _only_oid(neg))
    deltas, seed_mismatch = [], 0
    for i, (seed, v, _) in sorted(n.items()):
        s0, v0, _ = a.get(i, (None, None, None))
        seed_mismatch += seed != s0
        if v is not None and v0 is not None:
            deltas.append(v - v0)
    nom = [v for _, v, _ in a.values() if v is not None]
    return {"pairs": len(deltas), "seed_mismatches": seed_mismatch,
            "delta_mean_v": statistics.fmean(deltas) if deltas else None,
            "delta_stdev_v": statistics.stdev(deltas) if len(deltas) > 1 else None,
            "delta_min_v": min(deltas) if deltas else None,
            "delta_max_v": max(deltas) if deltas else None,
            "nominal_population_stdev_v": statistics.stdev(nom) if len(nom) > 1 else None}


def _stats(vals):
    vals = [v for v in vals if v is not None]
    return {"n": len(vals), "mean_v": statistics.fmean(vals) if vals else None,
            "stdev_v": statistics.stdev(vals) if len(vals) > 1 else None,
            "min_v": min(vals) if vals else None, "max_v": max(vals) if vals else None}


def attribution(att: dict, mc: dict, nominal_oid: str) -> dict:
    pops = b.split_report(att, MEAS)
    out = {oid: _stats(p["samples"]) for oid, p in pops.items()}
    full = _stats(b.split_report(mc, MEAS)[nominal_oid]["samples"])
    out["full_mismatch_" + nominal_oid] = full
    nom = next((v for k, v in out.items() if k.startswith("tt_nom/")), None)
    mos = next((v for k, v in out.items() if k.startswith("tt_mosmm/")), None)
    res = next((v for k, v in out.items() if k.startswith("tt_resmm/")), None)
    checks = {}
    if nom:
        checks["no_mismatch_zero_spread"] = nom["stdev_v"] == 0.0 and nom["min_v"] == nom["max_v"]
        checks["no_mismatch_matches_committed_corner"] = (
            nom["mean_v"] is not None
            and abs(nom["mean_v"] - COMMITTED_TT_NOM_V) <= COMMITTED_TT_NOM_TOL_V)
        checks["committed_corner_v"] = COMMITTED_TT_NOM_V
    if mos and res and full["stdev_v"]:
        rss = math.hypot(mos["stdev_v"], res["stdev_v"])
        checks["rss_partial_stdev_v"] = rss
        checks["rss_over_full_ratio"] = rss / full["stdev_v"]
        checks["mos_variance_share"] = mos["stdev_v"] ** 2 / (mos["stdev_v"] ** 2 + res["stdev_v"] ** 2)
    out["checks"] = checks
    return out


def yield_summary(rec: Path) -> dict:
    out = {}
    for p in sorted((rec / "yield").rglob("*.yield.json")):
        d = load(p)
        m = d["measurements"][0]
        nc = m.get("negative_control") or {}
        cap = m.get("capability") or {}
        out[str(p.relative_to(rec))] = {
            "status": d.get("status"), "n": m.get("n"), "errored": m.get("errored"),
            "failed_unmeasurable": m.get("failed_unmeasurable"), "inconclusive": m.get("inconclusive"),
            "mean_v": m["distribution"].get("mean"), "stdev_v": m["distribution"].get("stddev"),
            "normality": (m["distribution"].get("normality") or {}).get("verdict"),
            "empirical": m["yield"]["empirical"], "cpk": cap.get("cpk"),
            "sigma_to_spec": cap.get("sigma_to_spec"),
            "sample_size_verdict": (m.get("sample_size") or {}).get("verdict"),
            "negative_control_verdict": nc.get("verdict"),
        }
    return out


CSV_FIELDS = ["request", "corner_id", "process", "temperature_c", "supply_v",
              "sample_index", "seed", "process_seed", "mismatch_seed",
              "corner_status", "vout_v", "vout_status", "value_state"]


def draw_rows(name: str, report: dict):
    for c in report.get("corners", []):
        mc = c.get("monte_carlo") or {}
        v, state = b._value(c, MEAS)
        mst = next((m.get("status") for m in c.get("measurements", []) if m.get("name") == MEAS), None)
        yield {"request": name, "corner_id": c.get("corner_id"), "process": c.get("process"),
               "temperature_c": c.get("temperature_c"),
               "supply_v": ";".join(f"{k}={x}" for k, x in sorted((c.get("supply_v") or {}).items())),
               "sample_index": mc.get("sample_index", ""), "seed": mc.get("seed", ""),
               "process_seed": mc.get("process_seed", ""), "mismatch_seed": mc.get("mismatch_seed", ""),
               "corner_status": c.get("status"), "vout_v": "" if v is None else repr(v),
               "vout_status": mst, "value_state": state}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    csv_out = None
    if len(argv) == 3 and argv[1] == "--csv":
        csv_out = Path(argv[2])
        argv = argv[:1]
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    rec = Path(argv[0])
    raw = {n: load(rec / "raw" / f"row2-{n}.sim.json")
           for n in ("probe", "mc", "attribution", "negctl", "repro")}
    nominal = _only_oid(raw["repro"])
    doc = {
        "record": rec.name,
        "accounting": [accounting(n, r) for n, r in raw.items()],
        "seeds": {n: seeds_distinct(r) for n, r in raw.items() if n != "probe"},
        "reproduction": reproduction(raw["mc"], raw["repro"], nominal),
        "negctl_pairs": negctl_pairs(raw["mc"], raw["negctl"], nominal),
        "attribution": attribution(raw["attribution"], raw["mc"], nominal),
        "probe": [{"corner_id": c["corner_id"], "status": c["status"],
                   "vout_v": b._value(c, MEAS)[0]} for c in raw["probe"]["corners"]],
        "yield": yield_summary(rec),
    }
    print(json.dumps(doc, indent=1))
    if csv_out is not None:
        with csv_out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
            w.writeheader()
            for n, r in raw.items():
                for row in draw_rows(n, r):
                    w.writerow(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
