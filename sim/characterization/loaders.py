"""Load and validate the selected characterization evidence."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

from .common import (
    CORNERS,
    RES,
    ROW5_CROSS_BAND_LINE_MV_PER_V,
    ROW5_CROSS_BAND_LOAD_PCT,
    ROW5_LIMITS,
    ROW5_LINE_GRADED,
    ROW5_LINE_LOADS,
    ROW5_LOAD_GRADED,
    ROW5_LOAD_VINS,
    ROW5_SPEC_ROW_ID,
    ROW5_STEPS,
    ROW7_CROSS_BAND_UA,
    ROW7_GRADED,
    ROW7_LOADS,
    ROW7_SPEC_ROW_ID,
    ROW7_TARGET_A,
    ROW7_VINS,
    TEMPS,
    GenError,
    num,
    pinned,
    read_csv,
    sha256_file,
)

# --------------------------------------------------------------------------- #
# informational DC evidence (rows 5 and 7)
# --------------------------------------------------------------------------- #

DC_LOADS = [("0mA", "0 mA"), ("12p5mA", "12.5 mA"), ("25mA", "25 mA"),
            ("37p5mA", "37.5 mA"), ("50mA", "50 mA")]
DC_VINS = [("2p97", "2.97 V"), ("3p30", "3.30 V"), ("3p63", "3.63 V")]


def dc_expected_columns() -> list[str]:
    cols = ["corner", "temp_c", "res_section", "grid_ok", "iq_noload_a",
            "iq_fullload_excl_load_a", "iq_fullload_valid", "iq_fullload_noise_proxy_a"]
    cols += [f"line_reg_mv_per_v_{k}" for k, _ in DC_LOADS]
    cols += [f"line_reg_valid_{k}" for k, _ in DC_LOADS]
    for k, _ in DC_VINS:
        cols += [f"load_reg_pct_vin{k}", f"load_reg_valid_vin{k}", f"vout_50mA_vin{k}_v"]
    cols += ["dropout_legacy_v", "dropout_status", "dropout_vin_minus_vout_candidate_v"]
    return cols


def _boolfield(row: dict, key: str, ctx: str) -> bool:
    v = row.get(key)
    if v not in ("True", "False"):
        raise GenError(f"{ctx}: validity field '{key}' must be True/False, got {v!r}")
    return v == "True"


def load_dc_informational(root: Path, sel: dict, rec: dict, pvt_rows: list[dict],
                          sources: list) -> dict:
    """Validate and return the pinned informational DC summary for the selected
    record. Every failure is a hard GenError (fail-closed): nothing is skipped
    or repaired, and a point that is invalid stays in the data as invalid."""
    dc = sel.get("dc_informational_evidence")
    if not isinstance(dc, dict):
        raise GenError("selection.json has no dc_informational_evidence block")
    if dc.get("circuit_record_id") != rec["id"]:
        raise GenError(
            f"dc_informational_evidence is for record {dc.get('circuit_record_id')!r}, "
            f"selected circuit record is {rec['id']!r}")
    sum_path = pinned(root, dc["files"]["summary_csv"], "dc_informational_summary_csv", sources)
    inv_path = pinned(root, dc["files"]["coverage_inventory_json"],
                      "dc_coverage_inventory_json", sources)
    for p in (dc["files"]["summary_csv"]["path"], dc["files"]["coverage_inventory_json"]["path"]):
        if f"/{rec['id']}/" not in p:
            raise GenError(f"DC evidence path {p} is not under the selected record id {rec['id']}")

    # --- provenance inventory: must describe THIS record and design ---------
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        ins = inv["inputs"]
        gen = inv["generator"]
        grid = inv["grid"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GenError(f"DC coverage inventory unreadable or malformed: {exc!r}") from exc
    for role in ("record_csv", "record_md"):
        want = rec["files"]["pvt_csv" if role == "record_csv" else "record_md"]
        got = ins.get(role) or {}
        if got.get("path") != want["path"] or got.get("sha256") != want["sha256"]:
            raise GenError(
                f"DC inventory {role} does not match the selected record's pinned {role}: "
                f"{got.get('path')!r} {got.get('sha256')!r}")
    pins = {p["path"]: p["sha256"] for p in rec["design_freshness_pins"]}
    if ins.get("design_netlists") != pins:
        raise GenError("DC inventory design_netlists differ from the selection's design freshness pins")
    if grid.get("points") != 45 or grid.get("reproduces_record_csv") is not True:
        raise GenError("DC inventory does not state a 45-point grid that reproduces the record csv")
    gen_p = root / gen["path"]
    if not gen_p.is_file() or sha256_file(gen_p) != gen["sha256"]:
        raise GenError(f"DC inventory generator {gen.get('path')} missing or differs from its recorded sha256")
    raw = ins.get("raw_dc_grids")
    if not isinstance(raw, dict) or len(raw) != 45:
        raise GenError(f"DC inventory lists {len(raw) if isinstance(raw, dict) else 'no'} raw DC grids, expected 45")
    for rel, h in sorted(raw.items()):
        if f"/{rec['id']}/" not in rel:
            raise GenError(f"raw DC grid {rel} is not under the selected record id")
        rp = root / rel
        if not rp.is_file():
            raise GenError(f"raw DC grid missing: {rel}")
        if sha256_file(rp) != h:
            raise GenError(f"raw DC grid bytes differ from the inventory hash: {rel}")

    # --- summary: complete grid, finite values, True/False validity ---------
    srows = read_csv(sum_path)
    try:
        with sum_path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
    except (OSError, StopIteration) as exc:
        raise GenError(f"cannot read DC summary header: {exc!r}") from exc
    if header != dc_expected_columns():
        raise GenError(f"DC summary columns differ from the expected schema/units: {header}")
    keys = [(r["corner"], r["temp_c"], r["res_section"]) for r in srows]
    if len(set(keys)) != len(keys):
        dup = sorted(k for k in set(keys) if keys.count(k) > 1)
        raise GenError(f"DC summary has duplicate corner rows: {dup[:3]}")
    want = {(c, str(t), s) for c in CORNERS for t in TEMPS for s in RES}
    if set(keys) != want or len(keys) != 45:
        raise GenError(
            f"DC summary corner set incomplete or malformed: {len(keys)} rows, "
            f"missing {sorted(want - set(keys))[:3]}, unexpected {sorted(set(keys) - want)[:3]}")
    by_key = {}
    num_cols = [c for c in dc_expected_columns()
                if c not in ("corner", "temp_c", "res_section", "grid_ok", "dropout_status")
                and "_valid" not in c]
    for i, r in enumerate(srows):
        ctx = f"DC summary row {i + 2} ({r['corner']}/{r['temp_c']}/{r['res_section']})"
        if not _boolfield(r, "grid_ok", ctx):
            raise GenError(f"{ctx}: grid_ok is False; the raw grid was not complete")
        vals = {c: num(r, c, ctx) for c in num_cols}
        valid = {c: _boolfield(r, c, ctx) for c in dc_expected_columns() if "_valid" in c}
        by_key[(r["corner"], r["temp_c"], r["res_section"])] = (vals, valid)

    # --- agree with the pinned PVT csv where the two overlap ---------------
    for i, pr in enumerate(pvt_rows):
        k = (pr["corner"], pr["temp_c"], pr["res_section"])
        vals, _ = by_key[k]
        for pc, dc_col in (("iq_a", "iq_noload_a"), ("line_reg_mv_per_v", "line_reg_mv_per_v_0mA"),
                           ("load_reg_pct", "load_reg_pct_vin3p63"),
                           ("vout_at_vinmax_50ma_v", "vout_50mA_vin3p63_v")):
            a, b = float(pr[pc]), vals[dc_col]
            if abs(a - b) > 1e-6 * max(abs(a), 1e-12):
                raise GenError(
                    f"DC summary disagrees with the pinned PVT csv at {k}: "
                    f"{dc_col}={b} vs {pc}={a}")
    return {"by_key": by_key, "summary_path": dc["files"]["summary_csv"]["path"],
            "inventory_path": dc["files"]["coverage_inventory_json"]["path"],
            "n_raw_grids": len(raw)}


# --------------------------------------------------------------------------- #
# startup campaign evidence (row 9)
# --------------------------------------------------------------------------- #

# Proposed-methodology thresholds (DR-0009; mirrored in selection.json
# startup_evidence.proposed_methodology and startup_eval.py). Not ratified.
STARTUP_BAND_HI_V = 1.836
STARTUP_SETTLE_LIMIT_S = 3e-3
STARTUP_MONOTONIC_TOL_V = 1e-3
STARTUP_CSV_VERDICTS = ("pass", "fail", "insufficient")
STARTUP_REQUIRED = [
    "start_settle_time_s", "start_peak_vout_v", "start_max_down_excursion_v",
    "reen_peak_vout_v", "reen_max_down_excursion_v", "start_observed_s",
]
STARTUP_EXTRA = [
    "start_overshoot_v", "reen_overshoot_v", "reen_observed_s",
    "start_rise_10_90_s", "off_vout_max_v", "off_supply_current_a",
]


def startup_row_verdict(n_fail: int, n_insufficient: int, n_missing: int,
                        n_evaluated: int) -> str:
    """Row-9 verdict from point counts. A measured failure always wins (it is
    never masked by missing or insufficient points, nor by a numeric settling
    success); without failures, anything short of a whole evaluated grid is
    `not_measured`; only a whole, all-passing grid is a (partial-coverage)
    pass, and even that is a proposed-methodology measurement, not a
    ratification."""
    if n_fail:
        return "fail"
    if n_insufficient or n_missing or n_evaluated == 0:
        return "not_measured"
    return "pass_partial_coverage"


def _startup_key(mos, temp, res, vin, load, cout, esr, tmax):
    return (str(mos), int(float(temp)), str(res), round(float(vin), 3),
            float(load), float(cout), float(esr), float(tmax))


def load_startup(root: Path, sel: dict, sources: list) -> dict:
    """Validate and return the explicitly selected, pinned startup campaign.

    Hard GenError: block missing, wrong id/stage, any selected file missing or
    different from its pin, manifest/record disagreement, malformed or
    non-finite fields, duplicate or unexpected campaign point, trace file
    missing/tampered, a csv `pass` contradicted by a measured metric. Reported
    (not raised): requested points with no result row (`missing`), points the
    evaluator marked `insufficient`, and design staleness (core and error
    amplifier independently)."""
    st = sel.get("startup_evidence")
    if not isinstance(st, dict):
        raise GenError("selection.json has no startup_evidence block")
    rid = st["id"]
    for key in ("record_md", "grid_csv", "manifest_json"):
        if rid not in st["files"][key]["path"]:
            raise GenError(f"startup file {st['files'][key]['path']} is not under the selected startup id {rid}")
    pinned(root, st["files"]["record_md"], "startup_record_md", sources)
    csv_path = pinned(root, st["files"]["grid_csv"], "startup_grid_csv", sources)
    man_path = pinned(root, st["files"]["manifest_json"], "startup_manifest_json", sources)
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GenError(f"cannot load startup manifest {st['files']['manifest_json']['path']}: {exc}") from exc
    if man.get("rid") != rid or man.get("stage") != st["stage"]:
        raise GenError(f"startup manifest is for {man.get('rid')!r}/{man.get('stage')!r}, "
                       f"selected {rid!r}/{st['stage']!r}")

    # --- design freshness: core and error amplifier, independently ---------
    fresh = {}
    for comp, pin in st["design_freshness_pins"].items():
        p = root / pin["path"]
        if not p.is_file():
            raise GenError(f"startup design freshness pin target missing: {pin['path']} ({comp})")
        actual = sha256_file(p)
        entry = {"path": pin["path"], "pinned_sha256": pin["sha256"], "actual_sha256": actual,
                 "matches": actual == pin["sha256"], "recorded_in_manifest": bool(pin["recorded_in_manifest"])}
        if pin["recorded_in_manifest"]:
            mv = man.get("source_sha256", {}).get(pin["path"])
            if mv != pin["sha256"]:
                raise GenError(f"startup manifest source_sha256 for {pin['path']} is {mv!r}, "
                               f"selection pin is {pin['sha256']!r} ({comp})")
            entry["manifest_sha256"] = mv
        fresh[comp] = entry
        sources.append({"role": f"startup_design_{comp}_freshness", "path": pin["path"],
                        "sha256": actual, "pinned": True})
    stale_components = sorted(c for c, e in fresh.items() if not e["matches"])

    # --- campaign points ---------------------------------------------------
    g = st["requested_grid"]
    expected = {_startup_key(m, t, r, v, l, c, e, x)
                for m in g["process"] for t in g["temp_c"] for r in g["res"]
                for v in g["vin_v"] for l in g["load_ma"] for c in g["cout_nf"]
                for e in g["esr_mohm"] for x in g["tmax_ns"]}
    if man.get("requested") != len(expected):
        raise GenError(f"startup manifest requested {man.get('requested')} points, "
                       f"selected grid has {len(expected)}")
    rows = read_csv(csv_path)
    traces_dir = root / st["traces_dir"]
    seen: dict = {}
    pts = []
    for i, r in enumerate(rows):
        ctx = f"startup row {i + 2}"
        try:
            key = _startup_key(r["mos"], r["temp"], r["res"], r["vin"], r["load_ma"],
                               r["cout_nf"], r["esr_mohm"], r["tmax_ns"])
        except (KeyError, ValueError) as exc:
            raise GenError(f"{ctx}: malformed point coordinates: {exc!r}") from exc
        if key in seen:
            raise GenError(f"{ctx}: duplicate campaign point {r.get('point')} "
                           f"(same coordinates as row {seen[key] + 2})")
        seen[key] = i
        if key not in expected:
            raise GenError(f"{ctx}: point {r.get('point')} is outside the selected requested grid")
        verdict = r.get("verdict")
        if verdict not in STARTUP_CSV_VERDICTS:
            raise GenError(f"{ctx}: verdict {verdict!r} not one of {STARTUP_CSV_VERDICTS}")
        pt = {"point": r["point"], "corner": r["mos"], "temp_c": int(float(r["temp"])),
              "res_section": "res_" + r["res"], "vin_v": round(float(r["vin"]), 3),
              "load_ma": float(r["load_ma"]), "cout_nf": float(r["cout_nf"]),
              "esr_mohm": float(r["esr_mohm"])}
        rec = {"id": pt, "verdict": verdict, "reasons": r.get("reasons", ""),
               "settled": r.get("start_settled") == "True"}
        if verdict != "insufficient":
            for k in STARTUP_REQUIRED:
                rec[k] = num(r, k, ctx)
            if r.get("start_settled") not in ("True", "False"):
                raise GenError(f"{ctx}: start_settled not True/False")
            for k in STARTUP_EXTRA:
                if r.get(k, "") != "":
                    rec[k] = num(r, k, ctx)
            tf, ts = r.get("trace_file", ""), r.get("trace_sha256", "")
            tp = traces_dir / Path(tf).name
            if not tf or not tp.is_file():
                raise GenError(f"{ctx}: trace file missing for evaluated point {r['point']}: {tf!r}")
            if sha256_file(tp) != ts:
                raise GenError(f"{ctx}: trace {tf} bytes differ from the recorded trace_sha256")
            try:
                with gzip.open(tp, "rt", encoding="utf-8") as fh:
                    n_lines = sum(1 for _ in fh) - 1
            except (OSError, EOFError) as exc:
                raise GenError(f"{ctx}: trace {tf} unreadable: {exc}") from exc
            if n_lines != int(num(r, "samples", ctx)) or n_lines < 2:
                raise GenError(f"{ctx}: trace {tf} has {n_lines} samples, record says {r.get('samples')}")
        pts.append(rec)
    missing = sorted(expected - set(seen))
    n_ins = sum(1 for p in pts if p["verdict"] == "insufficient")
    n_fail = sum(1 for p in pts if p["verdict"] == "fail")
    n_pass = sum(1 for p in pts if p["verdict"] == "pass")
    for k, v in (("rows", len(pts)), ("insufficient", n_ins), ("fail", n_fail), ("pass", n_pass),
                 ("evaluated", n_fail + n_pass)):
        if man.get(k) != v and not missing:
            raise GenError(f"startup manifest {k}={man.get(k)!r} disagrees with the pinned csv ({v})")
    return {"cfg": st, "rid": rid, "manifest": man, "points": pts, "fresh": fresh,
            "stale_components": stale_components, "n_requested": len(expected),
            "missing": [{"corner": k[0], "temp_c": k[1], "res_section": "res_" + k[2],
                         "vin_v": k[3], "load_ma": k[4], "cout_nf": k[5], "esr_mohm": k[6]}
                        for k in missing],
            "n_fail": n_fail, "n_pass": n_pass, "n_insufficient": n_ins,
            "csv_rel": st["files"]["grid_csv"]["path"], "md_rel": st["files"]["record_md"]["path"]}


# --------------------------------------------------------------------------- #
# row 10: DR-0014 margin classification (proposed)
# --------------------------------------------------------------------------- #

ROW10_PM_BOUND = 45.0
ROW10_GM_BOUND = 10.0
ROW10_VERDICTS = ("pass", "fail", "ambiguous")
ROW10_COLUMNS = [
    "corner", "temp_c", "res_section", "record_n_0db_crossings", "record_phase_margin_deg",
    "record_phase_margin_worst_deg", "record_gain_margin_db", "n_zero_db_crossings",
    "zero_db_crossings_hz_dir_margin_deg", "pm_deg", "pm_verdict", "pm_reasons",
    "n_critical_crossings", "critical_crossings_hz_gain_db", "gm_db",
    "gm_above_ceiling_lower_bound_db", "gm_verdict", "gm_reasons", "low_end_gain_db",
    "low_end_ok", "ceiling_gain_db", "ceiling_last_decade_change_db", "ceiling_bounded",
    "nyquist_class", "trace", "trace_sha256",
]


def _optnum(row: dict, key: str, ctx: str):
    return None if row.get(key, "") == "" else num(row, key, ctx)


def _trace_ceiling_hz(path: Path, ctx: str) -> float:
    """Frequency of the last row of a loop-gain wrdata trace (already sha256-verified)."""
    try:
        last = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()][-1]
        hz = float(last.split()[0])
    except (OSError, ValueError, IndexError) as exc:
        raise GenError(f"{ctx}: cannot read the sweep ceiling from {path}: {exc!r}") from exc
    if not math.isfinite(hz) or hz <= 0:
        raise GenError(f"{ctx}: sweep ceiling {hz!r} is not a positive finite frequency")
    return round(hz, 3)


def _fmt_hz(hz: float) -> str:
    for scale, unit in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz"), (1.0, "Hz")):
        if hz >= scale * (1 - 1e-9):
            return f"{hz / scale:.6g} {unit}"
    return f"{hz:g} Hz"


def load_row10(root: Path, sel: dict, rec: dict, pvt_rows: list[dict], sources: list) -> dict:
    """Validate and return the pinned DR-0014 classification of the selected
    record's loop-gain traces. Every failure is a hard GenError (fail-closed)."""
    blk = sel.get("row10_margin_evidence")
    if not isinstance(blk, dict):
        raise GenError("selection.json has no row10_margin_evidence block")
    if blk.get("circuit_record_id") != rec["id"]:
        raise GenError(f"row10_margin_evidence is for record {blk.get('circuit_record_id')!r}, "
                       f"selected circuit record is {rec['id']!r}")
    csv_path = pinned(root, blk["files"]["classification_csv"], "row10_classification_csv", sources)
    js_path = pinned(root, blk["files"]["classification_json"], "row10_classification_json", sources)
    for p in (blk["files"]["classification_csv"]["path"], blk["files"]["classification_json"]["path"]):
        if f"/{rec['id']}/" not in p:
            raise GenError(f"row-10 classification {p} is not under the selected record id {rec['id']}")
    try:
        doc = json.loads(js_path.read_text(encoding="utf-8"))
        drec, bounds, clf, dcsv = doc["record"], doc["bounds"], doc["classifier"], doc["csv"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GenError(f"row-10 classification json unreadable or malformed: {exc!r}") from exc
    want = rec["files"]["pvt_csv"]
    if doc.get("dataset") != "legacy" or drec.get("csv") != want["path"] or drec.get("sha256") != want["sha256"]:
        raise GenError("row-10 classification does not name the selected record's pinned PVT csv")
    if (bounds.get("pm_deg"), bounds.get("gm_db")) != (ROW10_PM_BOUND, ROW10_GM_BOUND):
        raise GenError(f"row-10 classification bounds {bounds} differ from the row-10 target "
                       f"(PM >= {ROW10_PM_BOUND} deg, GM >= {ROW10_GM_BOUND} dB)")
    if dcsv.get("path") != blk["files"]["classification_csv"]["path"] or \
            dcsv.get("sha256") != blk["files"]["classification_csv"]["sha256"]:
        raise GenError("row-10 classification json does not describe the pinned csv")
    for rel, h in sorted(clf.items()):
        p = root / rel
        if not p.is_file() or sha256_file(p) != h:
            raise GenError(f"row-10 classifier source {rel} missing or differs from the bytes the "
                           "classification recorded: regenerate with row10_margins.py")
        sources.append({"role": "row10_classifier_source", "path": rel, "sha256": h, "pinned": True})

    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
    except (OSError, StopIteration) as exc:
        raise GenError(f"cannot read row-10 classification header: {exc!r}") from exc
    if header != ROW10_COLUMNS:
        raise GenError(f"row-10 classification columns differ from the expected schema: {header}")
    crow = read_csv(csv_path)
    keys = [(r["corner"], r["temp_c"], r["res_section"]) for r in crow]
    if len(set(keys)) != len(keys) or set(keys) != {(c, str(t), s) for c in CORNERS for t in TEMPS for s in RES}:
        raise GenError(f"row-10 classification corner set incomplete, duplicated or malformed ({len(keys)} rows)")
    by_key = {}
    ceilings = set()
    tdir = f"/corners/{rec['id']}/"
    for i, r in enumerate(crow):
        ctx = f"row-10 classification row {i + 2} ({r['corner']}/{r['temp_c']}/{r['res_section']})"
        if tdir not in r["trace"]:
            raise GenError(f"{ctx}: trace {r['trace']} is not under the selected record's corners dir")
        tp = root / r["trace"]
        if not tp.is_file() or sha256_file(tp) != r["trace_sha256"]:
            raise GenError(f"{ctx}: trace {r['trace']} missing or differs from its recorded sha256")
        ceilings.add(_trace_ceiling_hz(tp, ctx))
        for k in ("pm_verdict", "gm_verdict"):
            if r[k] not in ROW10_VERDICTS:
                raise GenError(f"{ctx}: {k} {r[k]!r} not one of {ROW10_VERDICTS}")
        pm, gm = _optnum(r, "pm_deg", ctx), _optnum(r, "gm_db", ctx)
        gm_lb = _optnum(r, "gm_above_ceiling_lower_bound_db", ctx)
        if r["pm_verdict"] == "pass" and not (pm is not None and pm >= ROW10_PM_BOUND):
            raise GenError(f"{ctx}: PM verdict pass contradicts pm_deg {pm}")
        if r["pm_verdict"] == "fail" and not (pm is not None and pm < ROW10_PM_BOUND):
            raise GenError(f"{ctx}: PM verdict fail contradicts pm_deg {pm}")
        gm_eff = gm if gm is not None else gm_lb
        if r["gm_verdict"] == "pass" and not (gm_eff is not None and gm_eff >= ROW10_GM_BOUND
                                              and (gm_lb is not None and gm_lb >= ROW10_GM_BOUND)):
            raise GenError(f"{ctx}: GM verdict pass contradicts gm {gm} / ceiling lower bound {gm_lb}")
        if r["gm_verdict"] == "fail" and not (gm is not None and gm < ROW10_GM_BOUND):
            raise GenError(f"{ctx}: GM verdict fail contradicts gm_db {gm}")
        by_key[keys[i]] = (r, pm, gm_eff)
    for pr in pvt_rows:
        k = (pr["corner"], pr["temp_c"], pr["res_section"])
        r, _, _ = by_key[k]
        for pc in ("n_0db_crossings", "phase_margin_deg", "phase_margin_worst_deg", "gain_margin_db"):
            if r[f"record_{pc}"] != pr[pc]:
                raise GenError(f"row-10 classification record_{pc} at {k} disagrees with the pinned PVT csv")
        if float(pr["phase_margin_deg"]) < ROW10_PM_BOUND and r["pm_verdict"] != "fail":
            raise GenError(f"row-10 classification upgrades a recorded PM miss at {k}")
        if float(pr["gain_margin_db"]) < ROW10_GM_BOUND and r["gm_verdict"] != "fail":
            raise GenError(f"row-10 classification upgrades a recorded GM miss at {k}")
    if len(ceilings) != 1:
        raise GenError(f"row-10 traces do not share one sweep ceiling: {sorted(ceilings)}")
    return {"by_key": by_key, "doc": doc, "csv_rel": blk["files"]["classification_csv"]["path"],
            "dr": blk["decision_record"], "ceiling_hz": next(iter(ceilings))}


def _corner_id(row: dict) -> str:
    res = row["res_section"]
    res = res[len("res_"):] if res.startswith("res_") else res
    return f"mos_{row['corner']}__res_{res}__cap_typ/novdd/{row['temp_c']}C"


_PDK_PIN_KEYS = ("pinned_commit", "pinned_tarball_sha256", "pinned_tarball_url", "subtree")


def _pdk_pin_projection_sha256(path: Path) -> str:
    """Same canonical projection as row_envelope.pdk_pin_projection_sha256 (a
    test asserts they agree): sort_keys + fixed separators over the keys that
    decide which PDK tree was fetched; a missing key is an error, never a skip."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    bad = [k for k in _PDK_PIN_KEYS if not isinstance(doc.get(k), str) or not doc[k]]
    if bad:
        raise GenError(f"{path}: projected PDK pin key(s) {bad} missing or not strings")
    canon = json.dumps({k: doc[k] for k in _PDK_PIN_KEYS}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def _load_row7_pair(root: Path, blk: dict, rid: str, sources: list) -> dict:
    """The pinned paired tight-tolerance comparison (observed solver sensitivity)."""
    pb = blk.get("pair_evidence")
    if not isinstance(pb, dict):
        raise GenError("selection.json row7_envelope_evidence has no pair_evidence block; "
                       "the solver-sensitivity claim needs its paired measurements")
    path = pinned(root, pb["files"]["pair_json"], "row7_pair_json", sources)
    if f"/{pb['tight_record_id']}/" not in pb["files"]["pair_json"]["path"]:
        raise GenError("row-7 pair file is not under the tight record's directory")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("base_record") != rid or doc.get("tight_record") != pb["tight_record_id"]:
        raise GenError(f"row-7 pair names {doc.get('base_record')}/{doc.get('tight_record')}, "
                       f"selection pairs {rid}/{pb['tight_record_id']}")
    if doc.get("complete") is not True or doc.get("pairs_compared") != 270 \
            or doc.get("pairs_expected") != 270:
        raise GenError("row-7 pair comparison is incomplete (needs all 270 pairs, identical "
                       "inputs except solver options)")
    bo, to = doc.get("base_options") or {}, doc.get("tight_options") or {}
    if bo != {"reltol": 1e-9, "abstol": 1e-15} or not (
            isinstance(to.get("reltol"), (int, float)) and isinstance(to.get("abstol"), (int, float))
            and to["reltol"] <= bo["reltol"] / 10 and to["abstol"] <= bo["abstol"]):
        raise GenError("row-7 pair comparison must compare the pinned reltol=1e-9/abstol=1e-15 "
                       f"request against a tolerance profile at least 10x tighter in reltol (got {to})")
    if not isinstance(doc.get("max_abs_delta_a"), (int, float)) or not math.isfinite(doc["max_abs_delta_a"]):
        raise GenError("row-7 pair comparison has no finite max_abs_delta_a")
    return doc


def _load_graded_envelope(root: Path, blk: dict, pvt_rows: list[dict], sources: list, *,
                          label: str, role_prefix: str, envelope_dir: str,
                          spec_row_id: str, limits_by_name: dict, steps_map: dict,
                          raw_step_meas: str) -> dict:
    """Validate the stages shared by every pinned graded `klt sim` envelope.

    Fail-closed (hard GenError) on: pin / selected-id mismatches, the report's
    own hash pins, a probe record, request and report graded declarations
    (exact set in declared order, per-measurement limits, spec_row tag, derived
    expr), the named (Vin, Iload) analysis steps, pinned and echoed solver
    tolerances, a matrix that is not a whole clean 45-corner pass with every
    step ok once and each graded figure finite, passing and strictly below its
    limit, the common summary attestations, and the design / PDK freshness
    pins. Design / PDK drift is NOT an error: it is returned as
    ``stale_components``. Row-specific summary and cross-checks stay with the
    caller, which receives the validated documents.
    """
    graded = tuple(limits_by_name)
    rid = blk["id"]
    paths = {}
    for key in ("report_json", "summary_json", "request_json", "tb_spice",
                "corners_lib", "provenance_json"):
        entry = blk["files"][key]
        if f"/{rid}/" not in entry["path"]:
            raise GenError(f"{label} envelope file {entry['path']} is not under the selected id {rid}")
        paths[key] = pinned(root, entry, f"{role_prefix}_{key}", sources)
    report = json.loads(paths["report_json"].read_text(encoding="utf-8"))
    request = json.loads(paths["request_json"].read_text(encoding="utf-8"))
    prov = json.loads(paths["provenance_json"].read_text(encoding="utf-8"))
    summary = json.loads(paths["summary_json"].read_text(encoding="utf-8"))

    # --- the report's own pins on what ran ---------------------------------
    tb_hash = "sha256:" + sha256_file(paths["tb_spice"])
    got_in = ((report.get("provenance") or {}).get("input") or {}).get("content_hash")
    if got_in != tb_hash:
        raise GenError(f"{label} envelope report pins input {got_in}, committed tb.spice is {tb_hash}")
    nl = report.get("netlist")
    nl_path = nl.get("path") if isinstance(nl, dict) else nl
    if nl_path != "tb.spice" and not str(nl_path).endswith(f"{envelope_dir}/{rid}/tb.spice"):
        raise GenError(f"{label} envelope report netlist is {nl_path!r}, not this record's tb.spice")
    lib_hash = sha256_file(paths["corners_lib"])
    env_lib = (report.get("environment") or {}).get("models_lib_sha256")
    if env_lib != lib_hash:
        raise GenError(f"{label} envelope report pins models_lib {env_lib}, "
                       f"committed corners.lib is {lib_hash}")
    if prov.get("record_id") != rid or prov.get("probe"):
        raise GenError(f"{label} envelope provenance names record {prov.get('record_id')!r} "
                       f"(probe={prov.get('probe')!r}), selected {rid!r}; a probe is never citable")

    # --- the request grades the row target, with the tool's own verdict -----
    req_names = [m.get("name") for m in request.get("measurements", [])]
    if tuple(req_names) != graded:
        raise GenError(f"{label} envelope request measurements {tuple(req_names)} differ from "
                       f"the six graded figures {graded} (each exactly once)")
    for m in request["measurements"]:
        if m.get("limits") != limits_by_name[m["name"]] or m.get("spec_row") != spec_row_id:
            raise GenError(f"{label} envelope request measurement {m['name']} declares limits "
                           f"{m.get('limits')} / spec_row {m.get('spec_row')!r}, not the DR-0007 "
                           f"{label} target {limits_by_name[m['name']]} / {spec_row_id!r}")
        if "expr" not in m:
            raise GenError(f"{label} envelope measurement {m['name']} is not a derived expr")
    # The REPORT is what the fleet graded: it must declare each graded figure
    # exactly once, with the row's own limit and tag -- a request that says so
    # proves nothing about a report with a declaration removed or repeated.
    rep_graded = [m for m in report.get("measurements", []) if m.get("name") in graded]
    if sorted(m["name"] for m in rep_graded) != sorted(graded):
        raise GenError(f"{label} envelope report does not declare each of the six graded "
                       f"figures exactly once (got {sorted(m['name'] for m in rep_graded)})")
    for m in rep_graded:
        if m.get("limits") != limits_by_name[m["name"]] or m.get("spec_row") != spec_row_id:
            raise GenError(f"{label} envelope report graded {m['name']} against "
                           f"{m.get('limits')} / spec_row {m.get('spec_row')!r}, not "
                           f"{limits_by_name[m['name']]} / {spec_row_id!r}")
    steps = request.get("analysis_steps")
    if not isinstance(steps, list) or sorted(s.get("name") for s in steps) != sorted(steps_map):
        raise GenError(f"{label} envelope request step names are not the {len(steps_map)} "
                       "named (Vin, Iload) operating points")
    for s in steps:
        alter = s.get("alter") or {}
        if (alter.get("Vin"), alter.get("Iload")) != steps_map[s["name"]]:
            raise GenError(f"{label} envelope step {s['name']!r} alters {alter}, not its own "
                           "(Vin, Iload) bias")
        sm = s.get("measurements") or []
        if len(sm) != 1 or sm[0].get("name") != raw_step_meas or sm[0].get("limits") \
                or sm[0].get("spec_row"):
            raise GenError(f"{label} envelope step {s['name']!r} must report exactly the "
                           f"ungraded, untagged raw measurement {raw_step_meas}")
    ngs = (request.get("options") or {}).get("ngspice_options") or {}
    if ngs.get("reltol") is None or ngs.get("abstol") is None \
            or (report.get("environment") or {}).get("ngspice_options") != ngs:
        raise GenError(f"{label} envelope request does not pin solver tolerances, or the "
                       "report does not echo them (options.ngspice_options)")

    # --- a whole, clean, fully-resolved matrix ------------------------------
    want_ids = {_corner_id(r) for r in pvt_rows}
    by_cid: dict = {}
    for c in report.get("corners", []):
        cid = c.get("corner_id")
        if cid in by_cid:
            raise GenError(f"{label} envelope reports corner {cid} twice")
        by_cid[cid] = c
    if set(by_cid) != want_ids or len(by_cid) != 45:
        raise GenError(f"{label} envelope corner set incomplete or malformed "
                       f"({len(by_cid)} corners, missing {sorted(want_ids - set(by_cid))[:3]}...)")
    for field, want in (("status", "pass"), ("passed", 45), ("failed", 0),
                        ("errored", 0), ("inconclusive", 0)):
        if report.get(field) != want:
            raise GenError(f"{label} envelope {field} is {report.get(field)!r}, not {want!r}")
    values: dict = {}
    for cid, c in by_cid.items():
        errs = [d for d in c.get("diagnostics", []) if d.get("severity") == "error"]
        if errs or c.get("status") != "pass":
            raise GenError(f"{label} envelope corner {cid} is not clean: status "
                           f"{c.get('status')!r}, {len(errs)} error diagnostics")
        st = c.get("steps", [])
        if sorted(s.get("name") for s in st) != sorted(steps_map) \
                or any(s.get("status") != "ok" for s in st):
            raise GenError(f"{label} envelope corner {cid} does not run each of the "
                           f"{len(steps_map)} named steps exactly once, all ok "
                           f"(got {[s.get('name') for s in st]})")
        mnames = [x.get("name") for x in c.get("measurements", [])]
        if any(mnames.count(n) != 1 for n in graded):
            raise GenError(f"{label} envelope corner {cid} does not report each graded "
                           "figure exactly once")
        m = {x["name"]: x for x in c.get("measurements", [])}
        for n in graded:
            v = m.get(n, {}).get("value")
            if v is None or not math.isfinite(v) or m[n].get("status") != "pass":
                raise GenError(f"{label} envelope corner {cid} measurement {n} is "
                               f"{m.get(n)}: not a resolved, passing value")
            # DR-0007 targets are strict "<"; klt sim's inclusive `max` grades a
            # value AT the limit as pass, so strictness is enforced here.
            if v >= limits_by_name[n]["max"]:
                raise GenError(f"{label} envelope corner {cid} measurement {n} is {v!r}, "
                               f"not strictly below the {limits_by_name[n]['max']} target")
            values[(cid, n)] = v
    cov = (report.get("coverage") or {}).get("measurements_with_limits")
    if cov != len(graded):
        raise GenError(f"{label} envelope measurements_with_limits is {cov!r}, "
                       f"not {len(graded)}")

    # --- summary attestations common to every graded envelope ---------------
    summ = summary.get("summary") or {}
    if not summ.get("definitive"):
        raise GenError(f"{label} envelope summary is not definitive; an incomplete "
                       "or failing matrix must never be cited")
    if "NOT an error bound" not in (summ.get("solver_convergence_setting_note") or ""):
        raise GenError(f"{label} envelope summary lost its convergence-setting statement "
                       "(it must say the setting is not an error bound)")
    if summ.get("all_graded_strictly_below_target") is not True \
            or summ.get("graded_declarations_exactly_once") is not True:
        raise GenError(f"{label} envelope summary does not attest strict-below-target and "
                       "exactly-once graded declarations")

    # --- design freshness: the tree vs the record's own pins ---------------
    fresh = {}
    for pin in blk["design_freshness_pins"]:
        p = root / pin["path"]
        if not p.is_file():
            raise GenError(f"{label} envelope design pin target missing: {pin['path']}")
        actual = sha256_file(p)
        recorded = (prov.get("input_sha256") or {}).get(pin["path"])
        if recorded != pin["sha256"]:
            raise GenError(f"{label} envelope provenance recorded {pin['path']} as "
                           f"{recorded}, selection pins {pin['sha256']}")
        fresh[pin["path"]] = {"pinned_sha256": pin["sha256"], "actual_sha256": actual,
                              "matches": actual == pin["sha256"]}
        sources.append({"role": f"{role_prefix}_design_freshness", "path": pin["path"],
                        "sha256": actual, "pinned": True})
    # The PDK revision the record ran on: the record's projection of the pin
    # (fetch-determining keys) vs the tree's current pin. A PDK revision change
    # invalidates the citation independently of the design netlists.
    recorded_pdk = prov.get("pdk_pin_projection_sha256")
    actual_pdk = _pdk_pin_projection_sha256(root / "sim" / "pdk-cmos5l.json")
    if not recorded_pdk:
        raise GenError(f"{label} envelope provenance has no pdk_pin_projection_sha256; the "
                       "citation cannot be checked against the PDK revision")
    fresh["sim/pdk-cmos5l.json (pin projection)"] = {
        "pinned_sha256": recorded_pdk, "actual_sha256": actual_pdk,
        "matches": recorded_pdk == actual_pdk}
    return {"cfg": blk, "rid": rid, "values": values, "summary": summ, "by_cid": by_cid,
            "fresh": fresh,
            "stale_components": sorted(k for k, v in fresh.items() if not v["matches"]),
            "report_rel": blk["files"]["report_json"]["path"],
            "summary_rel": blk["files"]["summary_json"]["path"]}


def load_row7_envelope(root: Path, sel: dict, pvt_rows: list[dict],
                       dcev: dict, sources: list) -> dict:
    """Validate and return the pinned row-7 graded `klt sim` envelope (issue #317).

    The shared stages are `_load_graded_envelope`; this adds the row-7 summary
    worst-case / exclusion checks, the paired tight-tolerance comparison, and
    the cross-check against the legacy PVT / DC-informational columns beyond
    the stated band (all hard GenError). Design drift is reported as
    stale_components, which fails the artifact's completeness check the same
    way the circuit record's own staleness does.
    """
    blk = sel.get("row7_envelope_evidence")
    if not isinstance(blk, dict):
        raise GenError("selection.json has no row7_envelope_evidence block")
    vin_by_name, load_by_name = dict(ROW7_VINS), dict(ROW7_LOADS)
    env = _load_graded_envelope(
        root, blk, pvt_rows, sources, label="row-7", role_prefix="row7_envelope",
        envelope_dir="row7-envelope", spec_row_id=ROW7_SPEC_ROW_ID,
        limits_by_name={n: {"max": ROW7_TARGET_A} for n in ROW7_GRADED},
        steps_map={f"{vn}_{ln}": (vv, lv) for vn, vv in vin_by_name.items()
                   for ln, lv in load_by_name.items()},
        raw_step_meas="isup_a")
    rid, values, summ, by_cid = env["rid"], env["values"], env["summary"], env["by_cid"]

    # --- the summary tells the truth about the report ----------------------
    for family, names in (("worst_noload", [n for n in ROW7_GRADED if "_i0_" in n]),
                          ("worst_fullload", [n for n in ROW7_GRADED if "_i50m_" in n])):
        want_v = max(values[(cid, n)] for cid in by_cid for n in names)
        if not math.isclose(summ.get(family, {}).get("iq_a", float("nan")), want_v,
                            rel_tol=1e-12, abs_tol=1e-15):
            raise GenError(f"row-7 envelope summary {family} "
                           f"{summ.get(family)} disagrees with the report's worst "
                           f"value {want_v}")
    exclusions = " ".join(summ.get("exclusions", []))
    for needle in ("0.90 V reference", "IBIAS", "#190"):
        if needle not in exclusions:
            raise GenError(f"row-7 envelope summary exclusions dropped: {needle!r}")
    env["pair"] = _load_row7_pair(root, blk, rid, sources)

    # --- cross-check against the legacy benches (consistency, not identity) -
    dc_by_key = dcev["by_key"]
    for r in pvt_rows:
        cid = _corner_id(r)
        nl33 = abs(values[(cid, "iq_i0_v3v30_a")] - num(r, "iq_a", "pvt")) * 1e6
        if nl33 > ROW7_CROSS_BAND_UA:
            raise GenError(f"row-7 envelope no-load Iq at Vin 3.30 V disagrees with the "
                           f"legacy iq_a at {cid}: {values[(cid, 'iq_i0_v3v30_a')] * 1e6:.4f} uA "
                           f"vs {float(r['iq_a']) * 1e6:.4f} uA (band {ROW7_CROSS_BAND_UA} uA)")
        dcv = dc_by_key[(r["corner"], r["temp_c"], r["res_section"])][0]
        fl33 = abs(values[(cid, "iq_i50m_v3v30_a")] - dcv["iq_fullload_excl_load_a"]) * 1e6
        if fl33 > ROW7_CROSS_BAND_UA:
            raise GenError(f"row-7 envelope full-load Iq at Vin 3.30 V disagrees with the "
                           f"offline DC figure at {cid}: {values[(cid, 'iq_i50m_v3v30_a')] * 1e6:.4f} uA "
                           f"vs {dcv['iq_fullload_excl_load_a'] * 1e6:.4f} uA "
                           f"(band {ROW7_CROSS_BAND_UA} uA)")
    return {k: v for k, v in env.items() if k != "by_cid"}


def load_row5_envelope(root: Path, sel: dict, pvt_rows: list[dict],
                       dcev: dict, sources: list):
    """Validate and return the pinned row-5 graded `klt sim` envelope (issue #319),
    or None when selection.json cites none (the report then states the gap and
    gives the row no envelope credit).

    The shared stages are `_load_graded_envelope`; this adds the row-5 summary
    worst-normalised-value / qualification checks and the cross-check against
    the offline DC columns beyond the stated band (all hard GenError).
    Design/PDK drift is reported as stale_components.
    """
    blk = sel.get("row5_envelope_evidence")
    if blk is None:
        return None
    if not isinstance(blk, dict):
        raise GenError("selection.json row5_envelope_evidence is not an object")
    env = _load_graded_envelope(
        root, blk, pvt_rows, sources, label="row-5", role_prefix="row5_envelope",
        envelope_dir="row5-envelope", spec_row_id=ROW5_SPEC_ROW_ID,
        limits_by_name=ROW5_LIMITS, steps_map=ROW5_STEPS, raw_step_meas="vout_v")
    values, summ, by_cid = env["values"], env["summary"], env["by_cid"]

    for family, names in (("worst_line", ROW5_LINE_GRADED), ("worst_load", ROW5_LOAD_GRADED)):
        want_v = max(values[(cid, n)] / ROW5_LIMITS[n]["max"] for cid in by_cid for n in names)
        got = summ.get(family, {})
        if not isinstance(got.get("value"), (int, float)) or not math.isclose(
                got["value"] / got.get("target", float("nan")), want_v,
                rel_tol=1e-12, abs_tol=1e-15):
            raise GenError(f"row-5 envelope summary {family} {got} disagrees with the "
                           f"report's worst normalised value {want_v}")
    quals = " ".join(summ.get("qualifications", []))
    for needle in ("0.90 V reference", "discrete sampling", "accuracy window", "row 2"):
        if needle not in quals:
            raise GenError(f"row-5 envelope summary qualifications dropped: {needle!r}")

    # Cross-check against the offline DC columns (signed there; |.| here).
    dc_by_key = dcev["by_key"]
    for r in pvt_rows:
        cid = _corner_id(r)
        dcv = dc_by_key[(r["corner"], r["temp_c"], r["res_section"])][0]
        for ln, key in zip(ROW5_LINE_LOADS, ("0mA", "25mA", "50mA")):
            d = abs(values[(cid, f"line_{ln}_mvpv")] - abs(dcv[f"line_reg_mv_per_v_{key}"]))
            if d > ROW5_CROSS_BAND_LINE_MV_PER_V:
                raise GenError(f"row-5 envelope line regulation at {ln} disagrees with the "
                               f"offline DC figure at {cid} by {d:.4g} mV/V "
                               f"(band {ROW5_CROSS_BAND_LINE_MV_PER_V})")
        for vn, key in zip(ROW5_LOAD_VINS, ("2p97", "3p30", "3p63")):
            d = abs(values[(cid, f"load_{vn}_pct")] - abs(dcv[f"load_reg_pct_vin{key}"]))
            if d > ROW5_CROSS_BAND_LOAD_PCT:
                raise GenError(f"row-5 envelope load regulation at {vn} disagrees with the "
                               f"offline DC figure at {cid} by {d:.4g} % "
                               f"(band {ROW5_CROSS_BAND_LOAD_PCT})")
    return {k: v for k, v in env.items() if k != "by_cid"}
