# OSDI replay at DR-0015 point P3 — 20261120-224044 (issue #313)

One loop-gain deck at DR-0015 point P3 (`ff` / -40 C / `res_wcs`, 50 mA,
0.33 uF, 0 mohm, **nominal Cc**), submitted twice through
`batch_backend.py run` on the current batch-runner image to settle whether
the `osdi_load_failed` hold on #218 / #219 (upstream
2AMLogic/klayout-tools#5766) is this repo's deck-side `pre_osdi` preamble or
the runner. **Answer: case (b) — the preamble.** The unchanged driver failed
exactly as parked; the same inputs without the preamble loaded all six
staged OSDI binaries and completed clean. The loop-gain baseline comparison
below is **inconclusive** under the pre-registered rule, for identified
model-input-vintage reasons that are independent of the OSDI fix.

## Request identity (recorded before submission)

- Deck: rendered by `sim/tools/render_deck.py` from the committed
  `testbench/tb_loopgain_cmos5l.spice.tmpl` with `run_sweep.sh`'s
  `gen_netlist` substitutions for P3: `MOS_SECTION=mos_ff RES_SECTION=res_wcs
  CAP_SECTION=cap_typ TEMP=-40 LG_AC_MAX=100meg CC_W="170u (nominal)"
  LOAD_A=50000e-6 COUT_F=330n` (ESR 0), design netlist
  `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`.
- Equivalence to the committed P3 baseline deck of record
  `20261012-074813-c94873ba` (manifest sha256 `81e17e7443b6e197…`):
  byte-identical after normalising the three absolute-path tokens
  (worktree prefix, PDK root, `wrdata` CSV path — the last ignored by the
  batch path, which rebuilds the CSV from the rawfile). The design netlist
  itself is byte-identical (sha256 `08a7b857e1fad43d…` on both sides).
- The original nominal-Cc E3 request itself (branch `feature/issue-219`)
  was **not** recoverable — the branch and worktree are gone (already noted
  by curation). This is a **reconstructed** request: netlist, corner
  section, temperature, operating point, analysis line and the six preload
  entries all verified identical to the baseline record as above; what
  could not be verified is byte-identity with whatever `run_ccprobe.sh`
  would have rendered on that branch (its `point_id` stem is also
  irrelevant here — the simulation does not depend on it).
- Queue: one line (`queue.tsv`), corner name
  `mos_ff__res_wcs__cap_typ__va49631b35601` — identical to the baseline
  record's P3 corner name in `_batch/points.tsv`. `--plan-only` showed
  **1 point in 1 request** both times; `--reuse-work` was not used.
- Model inputs staged from the fleet-synced PDK store
  (`/home/ubuntu/share/pdk`, `.pdk-store.json` pin `f7bca326…`, matching
  `sim/pdk-cmos5l.json`); the six `options.osdi_preload` entries are that
  store's OSDI binaries (names/order enforced by `batch_backend.py`).
- Client klt `0.9.3.dev2575+g6bd18bbc8637` on the dispatch host; both
  requests set `capacity_wait_s: 3600` in `batch` options.

## Run 1 — unchanged driver, deck-side preamble (case b)

Job `klt-sim-38b16c3f8b00`, runner klt **0.9.0**, submitted
2026-11-20T22:40:44Z, `klt sim` exit **4**. Evidence in `run1-preamble/`
(`osdi-preamble.cir` is the preamble `cmd_run` wrote; `tb.spice` line 2
includes it):

- Worker `ngspice.log`: six `Error opening osdi lib "inputs/<name>.osdi":
  No such file or directory!` + six `Error: Library inputs/<name>.osdi
  couldn't be loaded!` — the **preamble's relative `inputs/` paths**, in
  template order. Then `sha256sum: inputs/…: No such file or directory` x6
  (the preamble's provenance line), then a normal 161-row AC analysis.
- Returned `corner.cir`: the runner **applied `options.osdi_preload`
  itself** — its own `.control` block carries six absolute-path
  `pre_osdi /var/tmp/eda-job-klt-sim-38b16c3f8b00/inputs/<name>.osdi`
  lines. Those loads succeeded (no errors for them in the log).
- Report: corner status `error`, error-severity diagnostic `osdi_load_failed`
  ("ngspice said: Error: Library inputs/psp103.osdi couldn't be loaded!"),
  **beside a plausible-looking `liveness_vout = 2.0 V` marked "pass"** —
  the silent-wrong-evidence shape. `batch_backend.py` exit 1, no CSV
  written for the point.
- Worker `model_inputs`: all six staged OSDI digests present and equal to
  this host's binaries — staging delivered the bytes; the failure is the
  deck-side reload from a relative path that does not resolve at ngspice's
  working directory.

**Attribution: (b)** per issue #313 step 2 — the deck-side preamble's
`pre_osdi inputs/<name>.osdi` lines present alongside the runner's own
preload. This is a driver incompatibility with the runner-managed loading,
not a runner-image failure to materialise `options.osdi_preload`.

## Run 2 — fixed driver, same inputs (the supporting retry)

Driver change (this PR): `batch_backend.py` no longer writes/includes any
preamble; it relies on the runner's `options.osdi_preload` and verifies it
from the report. Job `klt-sim-d50438f1fe64`, runner klt **0.9.0**,
submitted 2026-11-20T22:48:53Z, `klt sim` exit **0**, report `status:
pass`. Evidence in `run2-fixed/`:

- `request.json` and `corners.lib` are **byte-identical to run 1**
  (sha256 `f3ed3d0127a1e9ae…` / `09618abffb87bc41…`); `tb.spice` differs
  only in the removed `.include osdi-preamble.cir` line. Same P3 inputs.
- Corner `mos_ff__res_wcs__cap_typ__va49631b35601` @ -40 C: status
  `pass`, **zero diagnostics**, `liveness_vout = 2.0 V` (pass), 161 rows.
- OSDI provenance verified per `collect()`: `environment.osdi_preload[]`
  and `worker_environment.model_inputs[]` both report exactly the six
  staged names with this host's digests (`psp103 dba873bc…`, `psp103_nqs
  ad99ea64…`, `mosvar cded61b1…`, `r3_cmc 746f86fd…`, `cap_cmomi
  972ff31c…`, `cap_cmomf d44927b3…`); recorded per job in `backend.json`
  (`osdi_preload_verified`). The returned `corner.cir` carries the
  runner's six preload lines.

## Baseline comparison (pre-registered rule, actual result)

Rule fixed before submission (issue #313 test plan, the DR-0015-table
fallback — the original E3 comparison rule was not recoverable): require
**2 crossings** and agreement with the same-vintage October 12 reference
(`corners/20261012-074813-c94873ba/loopgain_dyn_ff_-40c_rwcs_i50000ua_
c330nf_e0mohm_ac.csv`, trace sha256/16 `f9e9261aea56bd71`) after rounding
first-crossing frequency to **0.001 MHz** and both signed margins to
**0.01 deg**.

| | crossings | first crossing (Hz) | first PM (deg) | worst PM (deg) | GM (dB) |
|---|---:|---:|---:|---:|---:|
| run 2 trace (`7d2011c87dccbd5f`) | 2 | 1,935,574.22257 | -46.038235 | -161.586207 | -8.0466 |
| 20261012 baseline (`f9e9261aea56bd71`) | 2 | 1,979,981.37038 | -52.778946 | -162.405768 | -9.2253 |
| delta | 0 | **-44,407.15 Hz** | **+6.740711** | **+0.819562** | +1.1787 |

Rounded per the rule: 1.936 vs 1.980 MHz; -46.04 vs -52.78 deg; -161.59 vs
-162.41 deg. **The rule fails** (by ~44 kHz and ~6.7 deg, far beyond the
tolerances), so the comparison is **inconclusive** — recorded, not
explained away. `python3 ac_sweep.py check-trace <csv> 100meg` passes
(161 rows, endpoints, monotonicity), and the run is NOT the
silent-wrong-evidence case: the six OSDI models demonstrably loaded (zero
diagnostics, verified digests). The delta has identified input causes —
the model bytes that actually ran are not the baseline's:

| input (selected) | Oct 12 baseline (kt155) | this host (staged closure) | worker run 2 | verdict |
|---|---|---|---|---|
| `ldo_core_cmos5l.spice` | `08a7b857e1fad43d` | `08a7b857e1fad43d` | (inside tb.spice) | identical circuit |
| all six `.osdi` | differ | X | **== this host** | staged by content |
| `cap_cmom{i,f}.lib`, `sg13g2_moshv_{mismatch,parm,stat}.lib` | == | == | == | match |
| `cornerMOShv.lib` | `5a1f862dc304fdfe` | `5a1f862dc304fdfe` | `40c4140415a2a2e9` | worker differs from both |
| `cornerCAP.lib` | `6813c423f6669bf0` | `6813c423f6669bf0` | `f7e46eb43e0b9522` | worker differs from both |
| `cornerRES.lib` | `2c18502104146804` | `c6d749e72cfa2e06` | `bd2fdd7cf19ec817` | all three differ |
| `sg13g2_moshv_mod(_mismatch).lib` | differ | differ | differ | all three differ |
| `resistors_mod*.lib`, `sg13g2_svaricaphv*` | differ | X | **== this host** | staged by content |

Full digest lists: `run2-fixed/inputs.sha256.json` (client-side closure),
`run2-fixed/report.json` → `environment.remote.worker_environment.
model_inputs`, and the baseline's
`corners/20261012-074813-c94873ba/_batch/g00_…/inputs.sha256.json`.

Two consequences, reported as observations:

1. The MOS/RES corner cards and MOS model libs the worker loaded are a
   different vintage from both the submitting host's staged copies and the
   October 12 baseline — enough to explain a loop-gain shift of this size
   (the `rhigh` divider resistors and the HV MOS models sit in exactly
   these files). The baseline comparison therefore stays **inconclusive**;
   per issue #313 the downstream like-for-like hold is **not** cleared by
   this replay.
2. `options.stage_model_inputs: true` demonstrably delivered the OSDI
   binaries by content (digests match the submitting host) but the
   worker-reported digests of five `.lib` files match neither the
   submitting host nor any staged bytes — they are identical across two
   different submitting hosts (this replay and the 2026-11-16 row-4 run
   `klt-sim-17cc9389adfd`), i.e. resolved worker-side. Reported to
   2AMLogic/klayout-tools#5766 as an unresolved staging-semantics
   observation (a same-input replay is only interpretable when the bytes
   that ran are knowable).

## Disposition

- klayout-tools#5766: the originally-failing request shape fails because
  of **this repo's deck-side preamble**, not the runner image; the runner
  applies `options.osdi_preload` itself and loads staged bytes correctly
  (jobs `klt-sim-38b16c3f8b00` pre-fix, `klt-sim-d50438f1fe64` post-fix).
  Reported with both job ids.
- #218 / #219: their recorded blocker (`osdi_load_failed` on every corner
  after the ~2026-11-13 image rebuild) is **cleared by this repo's driver
  fix** once it merges — nothing upstream needs to change for their batch
  path to run. The P3 like-for-like baseline question stays open
  (inconclusive comparison above), which their own AC 4 already
  anticipates ("any difference is stated with its cause (tool or PDK pin
  vintage included)"). Both issues were left parked with a pointer here;
  their labels were not touched.
- `batch_backend.py` (and `test_batch_backend.py`) changed in this PR —
  signoff regenerated per `signoff/README.md#regenerating` (item 9's
  envelope re-attested at the pinned 0.9.2 build; tier report regenerated,
  still the honest non-T1 exit 3).

## Re-verify

```bash
cd sim/ldo-cmos5l-pvt-sweep
python3 ac_sweep.py check-trace \
  backend-validation/20261120-224044-osdi-replay/run2-fixed/loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_ac.csv \
  100meg
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
import ac_metrics
for p in ('backend-validation/20261120-224044-osdi-replay/run2-fixed/loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_ac.csv',
          'corners/20261012-074813-c94873ba/loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm_ac.csv'):
    print(p, ac_metrics.loopgain_metrics(p))
EOF
```

Append-only: no earlier record under `backend-validation/`, `corners/`,
`records/`, `evidence/` or `row4-envelope/` was edited for this note.
