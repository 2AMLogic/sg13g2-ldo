#!/usr/bin/env python3
"""SG13G2 HBT extraction/LVS probe — vendor-fixture witness of the upstream
bipolar recognition gap (issue #150).

The vendored fixture (`npn13G2.gds` + `npn13G2.cdl`) is the IHP-Open-PDK LVS
unit testcase for the `npn13G2` HBT, byte-identical to upstream commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6` and pinned by sha256 in
`expectations.json`. On the pinned tool build this fixture witnesses:

  * DRC       `clean`, 0 violations — inside the curated deck's INCOMPLETE
              coverage (rules_skipped / layers-without-rules are disclosed in
              every summary; this is not a full-deck signoff).
  * extract   `extracted` with ZERO devices: the sg13g2 curated deck declares
              no bipolar device class at all, so all three vendor HBT
              instances go unrecognized. Aggregate gap:
              2AMLogic/klayout-tools#2864 (the per-model limitations #2860 /
              #2861 / #2862 are described there and are NOT independently
              reproduced by this probe).
  * lvs       `mismatch` — device counts layout 0 / reference 3 / matched 0
              (observed error_count 15), the direct consequence of the
              extraction gap against the vendor reference netlist.

Three modes:

  --record   validate the fixture, freshly run the three klt stages in a
             temporary workdir, verify every pin and expected verdict, and
             only then update `raw/` and `summary.json`. Any error or changed
             behavior leaves the committed baseline untouched.
  --check    stdlib-only offline validation of the COMMITTED evidence:
             fixture/request/script hashes, report schemas and chain hashes,
             tool/deck pins, and a byte-for-byte regeneration of
             `summary.json` from the committed raw reports. This attests the
             freshness and internal consistency of stored evidence; it makes
             NO claim that the tool gap still persists (run --run for that).
             No PDK, no klayout module, no klt binary required.
  --run      freshly run the three stages and compare the stable verdict
             fields against `expectations.json`. A changed verdict, an
             unexpected error, or tool/deck pin drift fails loudly, names the
             upstream issue, and never rewrites the baseline.

Hard failures (never treated as expected-gap success): missing klt binary,
pin drift, invalid JSON, klt error envelopes, missing/empty fixtures, missing
top cell, non-permitted exit codes.

Usage: hbt_probe.py --record | --check | --run
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import validate_fixture  # noqa: E402  (sibling module, stdlib-only import here)

SCHEMA_SUMMARY = "sg13g2-ldo.hbt-probe.summary/1"
RAW_FILES = {
    "drc": "raw/drc_report.json",
    "extract": "raw/extract_report.json",
    "lvs": "raw/lvs_report.json",
}
HASHED_INPUTS = [
    "npn13G2.gds",
    "npn13G2.cdl",
    "LICENSE-IHP.txt",
    "lvs_request.json",
    "expectations.json",
    "hbt_probe.py",
    "validate_fixture.py",
]
SUBPROCESS_TIMEOUT_S = 600
UPSTREAM_EXTRACTION_ISSUE = "2AMLogic/klayout-tools#2864"
UPSTREAM_URL = "https://github.com/2AMLogic/klayout-tools/issues/2864"
BASELINE_INSTRUCTION = (
    "If this change is deliberate and upstream-verified, update the baseline "
    "explicitly: re-run `hbt_probe.py --record` under the new pinned build and "
    "commit the refreshed raw/ and summary.json with a provenance note. This "
    "probe never rewrites the baseline on its own."
)

CLAIMS = (
    "Stored-evidence claim only: --check attests that the committed raw reports, "
    "request and fixture are internally consistent, hash-pinned and still "
    "summarize to summary.json byte for byte. It does NOT re-run any tool and "
    "does not establish that the witnessed tool gap still persists; use --run "
    "for a fresh gap witness. The DRC 'clean' verdict is measured strictly "
    "inside the curated sg13g2 deck's incomplete coverage (see observed.drc); "
    "no full-deck DRC signoff is claimed. The extraction recognition gap is "
    "attributed at the aggregate level to " + UPSTREAM_EXTRACTION_ISSUE + "; the "
    "per-model sub-gaps and klayout-tools#2688/#2952 are NOT reproduced here."
)

PATH_NORMALIZATION = (
    "All klt stages run with cwd set to a fresh temporary workdir holding the "
    "vendored fixture and lvs_request.json, and are invoked with workdir-relative "
    "paths, so the committed raw reports and the argv below carry no absolute or "
    "host-specific paths. No other normalization is applied."
)


class ProbeError(Exception):
    """A hard probe failure (bad input, pin drift, tool error, protocol change)."""


def _sha(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def _expectations(probe_dir: pathlib.Path) -> dict:
    path = probe_dir / "expectations.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ProbeError(f"cannot read expectations.json: {e}") from e
    if data.get("schema") != "sg13g2-ldo.hbt-probe.expectations/1":
        raise ProbeError(f"expectations.json: unknown schema {data.get('schema')!r}")
    return data


def _load_report(probe_dir: pathlib.Path, stage: str) -> dict:
    path = probe_dir / RAW_FILES[stage]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ProbeError(f"{RAW_FILES[stage]}: cannot read committed raw report: {e}") from e
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ProbeError(f"{RAW_FILES[stage]}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ProbeError(f"{RAW_FILES[stage]}: report is not a JSON object")
    if "error" in data:
        raise ProbeError(
            f"{RAW_FILES[stage]}: is a klt error envelope, not a report: "
            f"{data['error'].get('message', data['error'])!r}"
        )
    for field in ("status", "provenance"):
        if field not in data:
            raise ProbeError(f"{RAW_FILES[stage]}: missing {field!r} field")
    return data


def _check_pins(pins: dict, reports: dict[str, dict]) -> None:
    for stage, report in reports.items():
        prov = report.get("provenance", {})
        deck = prov.get("deck", {})
        got = {
            "klt_version": prov.get("klt_version"),
            "klayout_version": prov.get("klayout_version"),
            "deck": deck.get("name"),
            "deck_content_hash": deck.get("content_hash"),
        }
        want = {
            "klt_version": pins["klt_version"],
            "klayout_version": pins["klayout_version"],
            "deck": pins["deck"],
            "deck_content_hash": pins["deck_content_hash"],
        }
        bad = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
        if bad:
            raise ProbeError(
                f"{RAW_FILES[stage]}: tool/deck pin drift {bad} — the pinned build "
                "moved; re-record under the new pin only after an upstream-verified review"
            )


def _check_chain(pins: dict, inputs: dict, reports: dict[str, dict]) -> None:
    gds_hash = inputs["npn13G2.gds"]
    cdl_hash = inputs["npn13G2.cdl"]
    for stage in ("drc", "extract"):
        got = reports[stage].get("provenance", {}).get("input", {}).get("content_hash")
        if got != gds_hash:
            raise ProbeError(
                f"{RAW_FILES[stage]}: recorded input hash {got} != vendored GDS {gds_hash}"
            )
    extracted = reports["extract"].get("netlist_sha256")
    lvs_layout = reports["lvs"].get("environment", {}).get("layout_sha256")
    if not extracted:
        raise ProbeError(f"{RAW_FILES['extract']}: missing netlist_sha256")
    if extracted != lvs_layout:
        raise ProbeError(
            f"chain broken: {RAW_FILES['extract']} netlist_sha256 {extracted} != "
            f"{RAW_FILES['lvs']} environment.layout_sha256 {lvs_layout}"
        )
    got_cdl = reports["lvs"].get("environment", {}).get("reference_sha256")
    if got_cdl != cdl_hash.removeprefix("sha256:"):
        raise ProbeError(
            f"{RAW_FILES['lvs']}: recorded reference hash {got_cdl} != vendored CDL {cdl_hash}"
        )


def _observed(reports: dict[str, dict]) -> dict:
    drc = reports["drc"]
    extract = reports["extract"]
    lvs = reports["lvs"]
    cov = drc.get("coverage", {})
    classes = [str(c) for c in extract.get("device_classes", [])]
    return {
        "drc": {
            "status": drc.get("status"),
            "violation_count": drc.get("violation_count"),
            "rules_checked": cov.get("rules_checked"),
            "rules_skipped": cov.get("rules_skipped"),
            "layers_in_stream_without_rules": cov.get("layers_in_stream_without_rules"),
            "deck_scope": cov.get("deck_scope"),
        },
        "extract": {
            "status": extract.get("status"),
            "device_count": extract.get("device_count"),
            "net_count": extract.get("net_count"),
            "pin_count": extract.get("pin_count"),
            "device_classes": classes,
            "bipolar_class_in_deck": any(
                "npn" in c.lower() or "pnp" in c.lower() for c in classes
            ),
            "netlist_sha256": extract.get("netlist_sha256"),
        },
        "lvs": {
            "status": lvs.get("status"),
            "error_count": lvs.get("error_count"),
            "counts": lvs.get("counts"),
        },
    }


def _verdict_mismatches(expected: dict, observed: dict) -> list[str]:
    bad = []
    for field, want in expected["drc"].items():
        got = observed["drc"].get(field)
        if got != want:
            bad.append(f"drc.{field}: observed {got!r} != expected {want!r}")
    for field, want in expected["extract"].items():
        got = observed["extract"].get(field)
        if got != want:
            bad.append(f"extract.{field}: observed {got!r} != expected {want!r}")
    for field, want in expected["lvs"].items():
        if field == "devices":
            got = (observed["lvs"].get("counts") or {}).get("devices")
        else:
            got = observed["lvs"].get(field)
        if got != want:
            bad.append(f"lvs.{field}: observed {got!r} != expected {want!r}")
    return bad


def _build_summary(
    expect: dict,
    inputs: dict,
    raw_hashes: dict,
    reports: dict[str, dict],
    recorded_with: dict,
) -> dict:
    observed = _observed(reports)
    return {
        "schema": SCHEMA_SUMMARY,
        "probe": "layout/hbt-probe",
        "claims": CLAIMS,
        "path_normalization": PATH_NORMALIZATION,
        "pins": expect["pins"],
        "vendor": expect["vendor"],
        "upstream": expect["upstream"],
        "inputs": inputs,
        "recorded_with": recorded_with,
        "raw_reports": {
            stage: {"path": RAW_FILES[stage], "sha256": raw_hashes[stage]}
            for stage in RAW_FILES
        },
        "observed": observed,
        "expected": expect["expected"],
        "matches_expected": not _verdict_mismatches(expect["expected"], observed),
    }


def _checked_inputs(probe_dir: pathlib.Path, expect: dict) -> dict:
    inputs = {}
    for name in HASHED_INPUTS:
        path = probe_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ProbeError(f"committed input missing or empty: {name}")
        inputs[name] = _sha(path)
    for name, want in expect["inputs"].items():
        if inputs.get(name) != want:
            raise ProbeError(
                f"fixture/reference tampered or stale: {name} hashes {inputs.get(name)} "
                f"!= pinned {want}"
            )
    license_sha = _sha(probe_dir / expect["vendor"]["license"])
    if license_sha != expect["vendor"]["license_sha256"]:
        raise ProbeError(
            f"{expect['vendor']['license']}: hash {license_sha} != pinned "
            f"{expect['vendor']['license_sha256']}"
        )
    return inputs


def _rebuild_summary(probe_dir: pathlib.Path, expect: dict, inputs: dict,
                     reports: dict[str, dict], committed: dict) -> dict:
    """Rebuild every summary field that --check can derive offline.

    `recorded_with` is the provenance narration of the --record session and
    cannot be re-executed offline; --check verifies its shape (klt preflight
    stamp, klt-led argv, exit codes inside the permitted sets) and everything
    verdict-bearing is recomputed from the committed raw reports.
    """
    raw_hashes = {stage: _sha(probe_dir / RAW_FILES[stage]) for stage in RAW_FILES}
    recorded = committed.get("recorded_with")
    if not isinstance(recorded, dict):
        raise ProbeError("summary.json: missing 'recorded_with'")
    preflight = recorded.get("klt_preflight")
    if preflight != f"klt {expect['pins']['klt_version']}":
        raise ProbeError(
            f"summary.json: recorded_with.klt_preflight {preflight!r} != pinned stamp "
            f"'klt {expect['pins']['klt_version']}'"
        )
    permitted = expect["permitted_exit_codes"]
    exit_codes = recorded.get("exit_codes")
    if not isinstance(exit_codes, dict) or sorted(exit_codes) != sorted(RAW_FILES):
        raise ProbeError(f"summary.json: recorded_with.exit_codes malformed: {exit_codes!r}")
    for stage, rc in exit_codes.items():
        if rc not in permitted[stage]:
            raise ProbeError(
                f"summary.json: recorded exit code {rc} for {stage} not in permitted "
                f"{permitted[stage]}"
            )
    argv = recorded.get("argv")
    if not isinstance(argv, dict) or sorted(argv) != sorted(RAW_FILES):
        raise ProbeError(f"summary.json: recorded_with.argv malformed: {argv!r}")
    for stage, cmd in argv.items():
        if not (isinstance(cmd, list) and cmd and cmd[0] == "klt"):
            raise ProbeError(f"summary.json: argv[{stage}] does not lead with 'klt': {cmd!r}")
    return _build_summary(expect, inputs, raw_hashes, reports, recorded)


def _preflight(klt: str, pins: dict) -> str:
    try:
        proc = subprocess.run(
            [klt, "--version"], capture_output=True, text=True, timeout=60
        )
    except OSError as e:
        raise ProbeError(f"cannot execute {klt}: {e}") from e
    stamp = proc.stdout.strip()
    if proc.returncode != 0 or stamp != f"klt {pins['klt_version']}":
        raise ProbeError(
            f"pinned klt build not found: `klt --version` printed {stamp!r} "
            f"(rc={proc.returncode}), expected 'klt {pins['klt_version']}' "
            f"(commit {pins['klt_commit']})"
        )
    return stamp


def _run_stage(klt: str, argv: list[str], workdir: pathlib.Path, stage: str,
               permitted: list[int]) -> tuple[int, dict]:
    try:
        proc = subprocess.run(
            [klt, *argv], cwd=workdir, capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise ProbeError(f"{stage}: klt did not finish within {SUBPROCESS_TIMEOUT_S}s") from e
    if proc.returncode not in permitted:
        tail = "\n".join(proc.stderr.strip().splitlines()[-10:])
        raise ProbeError(
            f"{stage}: `klt {argv[1]}` exited {proc.returncode}, permitted {permitted}."
            f"{' stderr tail:' + chr(10) + tail if tail else ''}"
        )
    try:
        report = json.loads(proc.stdout)
    except ValueError as e:
        raise ProbeError(f"{stage}: stdout is not valid JSON: {e}") from e
    if not isinstance(report, dict) or "error" in report or "status" not in report:
        raise ProbeError(
            f"{stage}: stdout is not a klt report (error envelope or empty output): "
            f"{str(proc.stdout)[:200]!r}"
        )
    return proc.returncode, report


def _run_all(probe_dir: pathlib.Path) -> tuple[dict, dict, dict]:
    """Fresh tool execution shared by --run and --record.

    Returns (expect, reports-by-stage, record metadata). Raises ProbeError on
    any missing binary, pin drift, invalid output or unexpected error.
    """
    expect = _expectations(probe_dir)
    _checked_inputs(probe_dir, expect)
    klt = shutil.which("klt")
    if klt is None:
        raise ProbeError(
            "klt not found on PATH -- this probe requires the pinned build "
            f"{expect['pins']['klt_version']} (commit {expect['pins']['klt_commit']})"
        )
    stamp = _preflight(klt, expect["pins"])
    validate_fixture.validate(probe_dir / "npn13G2.gds", probe_dir / "npn13G2.cdl")

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="hbt-probe-run-"))
    reports: dict[str, dict] = {}
    exit_codes: dict[str, int] = {}
    argv: dict[str, list[str]] = {
        "drc": ["klt", "drc", "npn13G2.gds", "--deck", "sg13g2", "--format", "json"],
        "extract": [
            "klt",
            "extract", "npn13G2.gds", "--deck", "sg13g2", "--top", "npn13G2",
            "-o", "npn13G2.extracted.spice", "--format", "json",
        ],
        "lvs": ["klt", "lvs", "lvs_request.json", "--format", "json"],
    }
    permitted = expect["permitted_exit_codes"]
    try:
        for name in ("npn13G2.gds", "npn13G2.cdl", "lvs_request.json"):
            shutil.copyfile(probe_dir / name, workdir / name)
        for stage in ("drc", "extract", "lvs"):
            rc, report = _run_stage(klt, argv[stage][1:], workdir, stage, permitted[stage])
            exit_codes[stage] = rc
            reports[stage] = report
            _check_pins(expect["pins"], {stage: report})
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    _check_chain(expect["pins"], expect["inputs"], reports)
    recorded_with = {
        "klt_preflight": stamp,
        "argv": argv,
        "exit_codes": exit_codes,
        "cwd": (
            "a fresh temporary workdir holding the vendored fixture and "
            "lvs_request.json (paths in argv are workdir-relative)"
        ),
    }
    return expect, reports, recorded_with


def _fail_changed(bad: list[str]) -> int:
    print("FAIL the fresh tool behavior differs from the pinned expectations:", file=sys.stderr)
    for line in bad:
        print(f"  - {line}", file=sys.stderr)
    print(
        f"Upstream context: the extraction recognition gap is tracked as "
        f"{UPSTREAM_EXTRACTION_ISSUE} ({UPSTREAM_URL}).", file=sys.stderr
    )
    print(BASELINE_INSTRUCTION, file=sys.stderr)
    return 1


def run_mode(probe_dir: pathlib.Path) -> int:
    expect, reports, _ = _run_all(probe_dir)
    bad = _verdict_mismatches(expect["expected"], _observed(reports))
    if bad:
        return _fail_changed(bad)
    print(
        "OK fresh run reproduces every expected outcome: drc "
        f"{reports['drc']['status']}/{reports['drc']['violation_count']} violations, "
        f"extract {reports['extract']['status']}/"
        f"{reports['extract']['device_count']} devices "
        f"(bipolar class present: {_observed(reports)['extract']['bipolar_class_in_deck']}), "
        f"lvs {reports['lvs']['status']}/"
        f"{reports['lvs']['counts']['devices']} devices — the upstream recognition gap "
        f"({UPSTREAM_EXTRACTION_ISSUE}) persists on the pinned build."
    )
    return 0


def record_mode(probe_dir: pathlib.Path) -> int:
    expect, reports, recorded_with = _run_all(probe_dir)
    observed = _observed(reports)
    bad = _verdict_mismatches(expect["expected"], observed)
    if bad:
        return _fail_changed(bad)
    raw_hashes = {}
    for stage in RAW_FILES:
        target = probe_dir / RAW_FILES[stage]
        old = target.read_bytes() if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        new = (json.dumps(reports[stage], indent=2) + "\n").encode("utf-8")
        target.write_bytes(new)
        raw_hashes[stage] = "sha256:" + hashlib.sha256(new).hexdigest()
        state = "updated" if old != new else "unchanged"
        print(f"  {RAW_FILES[stage]}: {state}")
    inputs = _checked_inputs(probe_dir, expect)
    summary = _build_summary(expect, inputs, raw_hashes, reports, recorded_with)
    summary_path = probe_dir / "summary.json"
    old_summary = summary_path.read_bytes() if summary_path.exists() else None
    summary_path.write_text(_dump(summary), encoding="utf-8")
    print(
        f"  summary.json: {'updated' if old_summary != summary_path.read_bytes() else 'unchanged'}"
    )
    print("OK baseline recorded under the pinned build; every pin and expected verdict held.")
    return 0


def check_mode(probe_dir: pathlib.Path) -> int:
    expect = _expectations(probe_dir)
    inputs = _checked_inputs(probe_dir, expect)
    cards = validate_fixture._validate_cdl(probe_dir / "npn13G2.cdl")
    if [c["m"] for c in cards] != list(validate_fixture.MULTIPLICITIES):
        raise ProbeError("npn13G2.cdl: multiplicity contract violated")
    reports = {stage: _load_report(probe_dir, stage) for stage in RAW_FILES}
    _check_pins(expect["pins"], reports)
    _check_chain(expect["pins"], inputs, reports)
    # Behavior first: the committed raw reports are compared against the pinned
    # expectations before the byte-level summary check, so a changed recognition
    # or verdict reads as exactly that (naming the upstream issue), not merely
    # as summary drift.
    bad = _verdict_mismatches(expect["expected"], _observed(reports))
    if bad:
        return _fail_changed(bad)
    committed_path = probe_dir / "summary.json"
    try:
        committed = json.loads(committed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ProbeError(f"cannot read summary.json: {e}") from e
    if committed.get("schema") != SCHEMA_SUMMARY:
        raise ProbeError(f"summary.json: unknown schema {committed.get('schema')!r}")
    rebuilt = _rebuild_summary(probe_dir, expect, inputs, reports, committed)
    for name, sha in rebuilt["inputs"].items():
        if committed.get("inputs", {}).get(name) != sha:
            raise ProbeError(
                f"committed input tampered or stale: {name} now hashes {sha} — "
                "re-record under the pinned build if this change is deliberate"
            )
    for stage, rec in rebuilt["raw_reports"].items():
        if committed.get("raw_reports", {}).get(stage) != rec:
            raise ProbeError(
                f"{RAW_FILES[stage]}: changed vs the committed summary — stored "
                "evidence is stale or tampered"
            )
    if _dump(rebuilt) != committed_path.read_text(encoding="utf-8"):
        raise ProbeError(
            "summary.json does not regenerate byte-for-byte from the committed raw "
            "reports and inputs — stored evidence is stale or tampered. Re-record "
            "under the pinned build if this change is deliberate."
        )
    print(
        "OK offline check: fixture/request/script hashes, raw-report chain and pins, "
        "and the normalized summary all reproduce byte for byte (stored-evidence "
        "freshness only — this does not re-run the tools)."
    )
    return 0


def main(argv: list[str]) -> int:
    probe_dir = pathlib.Path(__file__).resolve().parent
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode == "--record":
            return record_mode(probe_dir)
        if mode == "--check":
            return check_mode(probe_dir)
        if mode == "--run":
            return run_mode(probe_dir)
    except ProbeError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    print(__doc__.strip().splitlines()[-1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
