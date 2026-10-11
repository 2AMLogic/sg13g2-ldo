#!/usr/bin/env python3
"""Derive and gate the HBT screening record from raw `klt sim` reports (#139).

    record.py analyse <record-dir>   write <record-dir>.csv and <record-dir>.md
    record.py check   <record-dir>   regenerate in memory; fail on ANY byte of
                                     drift against the committed .csv/.md
    record.py single-corner <request.json> <out.json>   (--check-env helper)
    record.py preflight <report.json>                   (--check-env helper)

<record-dir>/raw/<device>-<bench>.sim.json are the committed `klt sim` reports
(the evidence); everything else is derived from them by this stdlib-only,
offline, deterministic script, so CI can prove the committed CSV/MD reproduce
from the raw bytes without a PDK or a simulator.  Nothing here has a pass/fail
spec threshold: the record reports numbers; the decision lives in
spec/decision-records (DR-0001 addendum).
"""
import csv
import io
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_decks as G  # noqa: E402

IQ_BUDGET_A = 30e-6          # DR-0007 row 7: Iq (excl. load) < 30 uA
IQ_STRETCH_A = 10e-6         # row 7 stretch
VIN_DROPOUT, VOUT = 2.10, 1.80
VCE_NUM = {"v030": 0.30, "v100": 1.00, "v150": 1.50, "v183": 1.83}
# vce_max as stated in the PDK model file (sg13g2_hbt_mod.lib @ IHP-Open-PDK
# v0.3.0, `.model ..._vbic` cards): npn13G2 line 54, npn13G2l line 290,
# npn13G2v line 525.  pnpMPA_mod carries no vce_max/vbc_max card.
VCE_MAX = {"npn13G2": 1.6, "npn13G2l": 1.6, "npn13G2v": 2.2, "pnpMPA": None}
# Collector-emitter headroom the pass device sees: nominal Vin 3.30, Vin_max
# 3.63 at regulation, and the continuous-short condition (Vout = 0, Vin_max).
VCE_STRESS = (("regulating, Vin 3.30 V", 1.50), ("regulating, Vin_max 3.63 V", 1.83),
              ("continuous short, Vin_max 3.63 V", 3.63))

CSV_COLS = (
    ["device", "polarity", "process", "temp_c", "load_ma", "cells"]
    + [f"{q}_{v}" for v in VCE_NUM for q in ("ib_a", "beta")]
    + [f"ic_frac_{v}" for v in VCE_NUM]
    + [f"vbe_v_{v}" for v in ("v030", "v100", "v150")]
    + ["ib_frac_iq30_v150", "early_v_1p0_1p5"]
    + [f"vce_req_v_bf{b}" for b in G.BETAS]
    + [f"beta_{k}" for k in G.CELL_IC] + [f"vbe_v_{k}" for k in G.CELL_IC]
)


def fnum(x):
    return "" if x is None else f"{x:.6g}"


def load_raw(rec):
    raw = {}
    for dev in G.DEVICES:
        for bench in G.BENCHES:
            p = rec / "raw" / f"{dev}-{bench}.sim.json"
            if not p.is_file():
                raise SystemExit(f"record.py: missing raw report {p}")
            raw[(dev, bench)] = json.loads(p.read_text())
    return raw


def corner_values(report):
    """{(process, temp_c): {measurement name: value-or-None}}"""
    out = {}
    for c in report["corners"]:
        out[(c["process"], c["temperature_c"])] = {m["name"]: m["value"] for m in c["measurements"]}
    return out


REACHED = 0.99   # a group "reached" its target when the servo got Ic >= 99 % of it


def group_values(m, tag, target):
    """(ib, ic, vb, reached) for one servo group; ib is None when unreached."""
    ib, ic, vb = m.get(f"ib_{tag}"), m.get(f"ic_{tag}"), m.get(f"vb_{tag}")
    if ib is None or ic is None:
        return None, None, vb, False
    ok = ic >= REACHED * target and ib > 0
    return (ib if ok else None), ic, vb, ok


def rows_for(raw):
    """Build the CSV rows (dicts)."""
    rows = []
    for dev, (pol, _spec) in G.DEVICES.items():
        sv = corner_values(raw[(dev, "servo")])
        vc = corner_values(raw[(dev, "vcesweep")])
        for proc in G.PROCESS:
            for t in G.TEMPS_C:
                m, v = sv[(proc, t)], vc[(proc, t)]
                for load in G.LOADS_MA:
                    r = dict.fromkeys(CSV_COLS, "")
                    r.update(device=dev, polarity=pol, process=proc, temp_c=t,
                             load_ma=load, cells=G.CELLS[load])
                    target = load * 1e-3
                    betas = {}
                    for vk in VCE_NUM:
                        i_b, i_c, vb, ok = group_values(m, f"l{load}_{vk}", target)
                        r[f"ib_a_{vk}"] = fnum(i_b)
                        if i_c is not None:
                            r[f"ic_frac_{vk}"] = fnum(i_c / target)
                        if ok:
                            betas[vk] = i_c / i_b
                            r[f"beta_{vk}"] = fnum(betas[vk])
                            if vk in ("v030", "v100", "v150") and vb is not None:
                                r[f"vbe_v_{vk}"] = fnum(vb)
                    if r["ib_a_v150"] != "":
                        r["ib_frac_iq30_v150"] = fnum(fl(r["ib_a_v150"]) / IQ_BUDGET_A)
                    if "v100" in betas and "v150" in betas:
                        ratio = betas["v150"] / betas["v100"]
                        if ratio > 1:
                            r["early_v_1p0_1p5"] = fnum((1.5 - ratio * 1.0) / (ratio - 1.0))
                    for bf in G.BETAS:
                        r[f"vce_req_v_bf{bf}"] = fnum(v.get(f"vce_l{load}_b{bf}"))
                    rows.append(r)
                r = dict.fromkeys(CSV_COLS, "")
                r.update(device=dev, polarity=pol, process=proc, temp_c=t, load_ma="cell", cells=1)
                for k, icv in G.CELL_IC.items():
                    i_b, i_c, vb, ok = group_values(m, f"cell_{k}", icv)
                    if ok:
                        r[f"beta_{k}"] = fnum(i_c / i_b)
                        r[f"vbe_v_{k}"] = fnum(vb)
                rows.append(r)
    return rows


def csv_text(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def fl(x):
    return float(x) if x != "" else None


def rng(rows, col, fmt="{:.3g}"):
    vals = [fl(r[col]) for r in rows if r[col] != ""]
    if not vals:
        return "n/a (never reached)"
    lo, hi = min(vals), max(vals)
    return f"{fmt.format(lo)}-{fmt.format(hi)}" if lo != hi else fmt.format(lo)


def worst(rows, col, fn, fmt="{:.3g}"):
    cand = [(fl(r[col]), r) for r in rows if r[col] != ""]
    if not cand:
        return "n/a"
    v, r = fn(cand, key=lambda t: t[0])
    return f"{fmt.format(v)} ({r['process']}/{r['temp_c']}C)"


def sanity(raw, rows):
    """Behavioural PASS/NOTE lines; part of the byte check."""
    L = []
    for (dev, bench), rep in sorted(raw.items()):
        n = len(rep["corners"])
        witness = "ic_" if bench == "servo" else "icmax_"
        miss = [(c["corner_id"], mm["name"]) for c in rep["corners"] for mm in c["measurements"]
                if mm["name"].startswith(witness) and mm["value"] is None]
        if bench == "servo":
            miss += [(c["corner_id"], mm["name"]) for c in rep["corners"] for mm in c["measurements"]
                     if mm["name"].startswith(("ib_", "vb_")) and mm["value"] is None]  # servo: always defined
        diag = sorted({d["code"] for c in rep["corners"] for d in c["diagnostics"] if d["code"] != "measurement"})
        ok = n == len(G.PROCESS) * len(G.TEMPS_C) and not miss and not diag
        L.append(f"{'PASS' if ok else 'FAIL'} {dev}/{bench}: {n}/{len(G.PROCESS) * len(G.TEMPS_C)} corners, "
                 f"every measurement present ({witness}*{", ib_*, vb_*" if bench == "servo" else ""}), "
                 f"solver diagnostics other than unreachable-`.meas`: {', '.join(diag) or 'none'}")
    for dev in G.DEVICES:
        d = [r for r in rows if r["device"] == dev and r["load_ma"] in (50, 100)]
        bad = [r for r in d if r["ib_a_v150"] != "" and fl(r["ib_a_v150"]) <= 0]
        # monotonic sanity: base current for 100 mA exceeds that for 50 mA, per corner.
        viol = 0
        for r5 in d:
            if r5["load_ma"] != 50:
                continue
            r1 = next(x for x in d if x["load_ma"] == 100 and x["process"] == r5["process"] and x["temp_c"] == r5["temp_c"])
            if r5["ib_a_v150"] != "" and r1["ib_a_v150"] != "" and fl(r1["ib_a_v150"]) <= fl(r5["ib_a_v150"]):
                viol += 1
        L.append(f"{'PASS' if not bad and not viol else 'FAIL'} {dev}: Ib(100 mA) > Ib(50 mA) at Vce 1.50 V (where both reached) in every corner "
                 f"({viol} violations), no non-positive base current ({len(bad)})")
    return L


def environment_lines(raw):
    kv = {}
    for (dev, bench), rep in sorted(raw.items()):
        env = rep["environment"]
        kv.setdefault("engine", set()).add(f"{env.get('engine')} {env.get('engine_version')}")
        kv.setdefault("klt", set()).add(str(rep["provenance"].get("klt_version")))
        kv.setdefault("models_lib_sha256", set()).add(env.get("models_lib_sha256"))
        kv.setdefault(f"netlist_sha256[{dev}-{bench}]", set()).add(env.get("netlist_sha256"))
        remote = env.get("remote")
        if remote:
            kv.setdefault("remote", set()).add(json.dumps(remote, sort_keys=True))
    return kv


def md_text(rec, raw, rows):
    rid = rec.name
    date = f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}"
    L = [f"# Record {rid}", ""]
    L += [
        "- **Experiment**: pass-device-screening-hbt (issue #139).",
        "- **Claim**: the SG13G2 HBTs (`npn13G2`, `npn13G2l`, `npn13G2v`, `pnpMPA`) screened as a "
        "bipolar pass element at the ratified dropout row's load points (50 mA, and the 100 mA "
        "stretch): beta vs Ic, Early voltage, Vce(sat) at forced beta, quasi-saturation at the "
        "0.30 V dropout differential, and base current against the Iq budget, over the PDK's "
        "`hbt_{bcs,typ,wcs}` x {-40, 27, 125} C corners. Evidence for the DR-0001 addendum "
        "(`spec/decision-records/DR-0001a-hbt-pass-device-screening.md`); this record asserts no "
        "pass/fail threshold of its own.",
        f"- **Matrix**: 4 devices x 2 benches (`servo`, `vcesweep`) x 3 process x 3 temperature = "
        f"{4 * 2 * 9} `klt sim` units, each a batch-fleet unit. Supply is not a swept axis: the "
        "test points are fixed absolute collector-emitter voltages (0.30 / 1.00 / 1.50 / 1.83 V), "
        "as in the MOS deck (README.md 'Corner grid and axes swept').",
        f"- **Raw evidence**: `{rid}/raw/<device>-<bench>.sim.json` (the `klt sim --backend batch` "
        "reports, committed verbatim). The CSV and this file are derived from them by "
        "`record.py analyse` and re-verified byte-for-byte offline by `record.py check` (CI).",
        "- **Decks**: `decks/` (generated by `gen_decks.py`; each raw report pins its netlist "
        "closure by sha256).",
        f"- **Date**: {date} (record id)."
    ]
    env = environment_lines(raw)
    L.append("- **Toolchain / provenance** (from the raw reports):")
    for k in ("engine", "klt", "models_lib_sha256", "remote"):
        for v in sorted(env.get(k, [])):
            L.append(f"  - {k}: `{v}`")
    L.append("")
    L.append("## Sanity checks")
    L.append("")
    L += [f"- {s}" for s in sanity(raw, rows)]
    L.append("")
    L.append("## Summary (derived; worst case over the 9 process/temperature corners)")
    L.append("")
    L.append("Iq budget reference: DR-0007 row 7, Iq (excl. load) < 30 uA (stretch < 10 uA). "
             "'Ib' is the TOTAL base current of the load-point device group.")
    L.append("")
    L.append("| device | load | Ib @ Vce 1.50 V (worst) | x Iq budget | beta @ 1.50 V | beta @ 0.30 V | Ic reached @ 0.30 V (corners) | Early V (1.0->1.5 V) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for dev in G.DEVICES:
        for load in G.LOADS_MA:
            d = [r for r in rows if r["device"] == dev and r["load_ma"] == load]
            reach = sum(1 for r in d if r["ib_a_v030"] != "")
            wib = worst(d, "ib_a_v150", max, "{:.3g} A")
            wfrac = worst(d, "ib_frac_iq30_v150", max, "{:.3g}")
            L.append(f"| {dev} | {load} mA | {wib} | {wfrac} | {rng(d, 'beta_v150')} | {rng(d, 'beta_v030')} | "
                     f"{reach}/{len(d)} | {rng(d, 'early_v_1p0_1p5')} |")
    L.append("")
    L.append("Reading: 'x Iq budget' is the worst-corner base current divided by 30 uA (> 1 means the base drive alone exceeds the "
             "whole row-7 allowance). 'Ic reached' counts corners where the group delivered the full target current at Vce = 0.30 V "
             "within the servo's base-current clamp (NPN: Ic/10; PNP: 1.5 x Ic). Early voltage is the beta(1.5 V)/beta(1.0 V) "
             "extrapolation at the same Ic (blank = beta did not rise with Vce).")
    L.append("")
    L.append("### Forced-beta Vce requirement (`vcesweep`), 50 mA load, worst corner (max Vce)")
    L.append("")
    L.append("| device | " + " | ".join(f"beta_f = {b}" for b in G.BETAS) + " |")
    L.append("|---|" + "---|" * len(G.BETAS))
    for dev in G.DEVICES:
        d = [r for r in rows if r["device"] == dev and r["load_ma"] == 50]
        cells = []
        for b in G.BETAS:
            col = f"vce_req_v_bf{b}"
            n = sum(1 for r in d if r[col] != "")
            cells.append(f"{worst(d, col, max, '{:.3g} V')}; reached {n}/{len(d)}")
        L.append(f"| {dev} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("### NPN follower reading of the base voltage (no boosted supply)")
    L.append("")
    L.append("A high-side NPN pass device is an emitter follower (collector on Vin, emitter on Vout). With the base "
             "drive limited to Vin, regulation needs Vin - Vout >= Vbe at the load current; the dropout differential "
             "(Vin 2.10 V - Vout 1.80 V = 0.30 V) therefore needs a base drive Vbe - 0.30 V ABOVE Vin.")
    L.append("")
    L.append("| device | load | Vbe @ target Ic (Vce 1.0 V), range | min no-boost dropout (V) = max Vbe | boost above Vin at the 0.30 V point (V) = max Vbe - 0.30 |")
    L.append("|---|---|---|---|---|")
    for dev, (pol, _s) in G.DEVICES.items():
        if pol != "npn":
            continue
        for load in G.LOADS_MA:
            d = [r for r in rows if r["device"] == dev and r["load_ma"] == load and r["vbe_v_v100"] != ""]
            vals = [fl(r["vbe_v_v100"]) for r in d]
            if vals:
                L.append(f"| {dev} | {load} mA | {min(vals):.3f}-{max(vals):.3f} V | {max(vals):.3f} | {max(vals) - 0.30:.3f} |")
    L.append("")
    L.append("### Collector-emitter stress against the model's stated vce_max")
    L.append("")
    L.append("| device | vce_max (PDK model card) | " + " | ".join(f"{n}: Vce {v:.2f} V" for n, v in VCE_STRESS) + " |")
    L.append("|---|---|" + "---|" * len(VCE_STRESS))
    for dev in G.DEVICES:
        vm = VCE_MAX[dev]
        cells = ["n/a" if vm is None else ("exceeds" if v > vm else "within") for _n, v in VCE_STRESS]
        L.append(f"| {dev} | {'none stated' if vm is None else vm} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("`pnpMPA_mod` carries no `vce_max` card; the PDK documents the device as the bandgap PNP "
             "(`libs.tech/xschem/README.md`) and its collector is the substrate (the model scales `isc`/`ikr`/`ccb` with "
             "the substrate area `sub_a`).")
    L.append("")
    L.append("## Not shown here")
    L.append("")
    L.append("- Self-heating (decks are isothermal; README.md 'Self-heating'), mismatch/Monte Carlo, AC/transient, "
             "layout/LVS-level feasibility, and any circuit that closes a loop around a bipolar pass device. "
             "Sizing is a screening choice, not a layout proposal.")
    L.append("- The decision this evidence feeds: `spec/decision-records/DR-0001a-hbt-pass-device-screening.md`.")
    L.append("")
    return "\n".join(L)


def derive(rec):
    raw = load_raw(rec)
    rows = rows_for(raw)
    return csv_text(rows), md_text(rec, raw, rows)


def cmd_analyse(rec):
    c, m = derive(rec)
    pathlib.Path(f"{rec}.csv").write_text(c)
    pathlib.Path(f"{rec}.md").write_text(m)
    print(f"record.py: wrote {rec}.csv and {rec}.md")
    return 0


def cmd_check(rec):
    c, m = derive(rec)
    bad = []
    for suffix, text in ((".csv", c), (".md", m)):
        p = pathlib.Path(f"{rec}{suffix}")
        if not p.is_file() or p.read_text() != text:
            bad.append(p.name)
    if bad:
        print(f"record.py check FAILED: drift in {bad}; re-run 'run_sweep.sh analyse' and review the diff", file=sys.stderr)
        return 1
    fails = [s for s in sanity(load_raw(rec), rows_for(load_raw(rec))) if s.startswith("FAIL")]
    if fails:
        print("record.py check FAILED: " + "; ".join(fails), file=sys.stderr)
        return 1
    print("record.py check OK: CSV and MD reproduce exactly from the raw reports; sanity checks pass")
    return 0


def cmd_single_corner(src, dst):
    req = json.loads(pathlib.Path(src).read_text())
    req["corners"] = {"process": ["typ"], "temperature_c": [27]}
    req["backend"] = "local"
    req.pop("batch", None)
    req.setdefault("options", {})["keep_artifacts"] = False
    pathlib.Path(dst).write_text(json.dumps(req, indent=2) + "\n")
    return 0


def cmd_preflight(path):
    """--check-env gate: the analysis solved (no solver diagnostics) and every
    witness measurement resolved; unreachable-target `.meas` are legitimate."""
    rep = json.loads(pathlib.Path(path).read_text())
    problems = []
    for c in rep.get("corners", []):
        for d in c.get("diagnostics", []):
            if d["code"] != "measurement":
                problems.append(f"{c['corner_id']}: {d['code']}: {d['message']}")
        for mm in c.get("measurements", []):
            if mm["name"].startswith(("ic_", "icmax_", "ib_")) and mm["value"] is None:
                problems.append(f"{c['corner_id']}: witness {mm['name']} did not resolve")
    if not rep.get("corners"):
        problems.append("no corners in report")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] in ("analyse", "check"):
        rec = pathlib.Path(argv[1]).resolve()
        return cmd_analyse(rec) if argv[0] == "analyse" else cmd_check(rec)
    if len(argv) == 3 and argv[0] == "single-corner":
        return cmd_single_corner(argv[1], argv[2])
    if len(argv) == 2 and argv[0] == "preflight":
        return cmd_preflight(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
