# SG13CMOS5L PDK re-stamp: migration inventory (issue #155)

The SG13CMOS5L PDK moved from the archived repository `IHP-GmbH/ihp-sg13cmos5l`
(old pin `607e18d4bd9214a52575c194b4181ef449f9252f`) to the `ihp-sg13cmos5l/`
subtree of `IHP-GmbH/IHP-Open-PDK` `dev` (new pin
`f7bca32694fe3d58be0cc7d9df4b9f5db7161a14`, tarball sha256
`5eb6f8a9b0b2ecc4fa08cc30627668406f85b1a97834f278036c43f0c0dbc70b`;
klayout-tools#2720). This file lists every campaign and layout citation that
rested on the old pin, what tools produced it, whether it was selected for a
current claim, and what was done on the new pin. It is append-only evidence
bookkeeping: no existing `records/`, `corners/`, `evidence/` or
`netlist-snapshots/` file was edited, and no old record is relabelled as a
new-pin run. Old records stay what they are: runs on the old pin.

## Install on the new pin (scratch root, nothing host-wide touched)

| Check | Result |
|---|---|
| Fetch scripts | `scripts/fetch-ihp-sg13g2.sh` then `scripts/fetch-ihp-sg13cmos5l.sh`, from klayout-tools `159527a551596caa74f290dcab08bdb8cc78ce93` (cloned to a scratch dir; `fetch-ihp-sg13cmos5l.sh` sha256 `f4333846...0650a18`). The `IHP_SG13CMOS5L_COMMIT`, `IHP_SG13CMOS5L_SHA256` and `.fetched-version` lines were read at that revision and match the pin. `fetch-ihp-sg13g2.sh` at that revision is byte-identical to the `v0.7.0` one (sha256 `bdb2c8de...140f7`), so the SG13G2 sibling is unchanged. |
| Checksum | The script exits non-zero on a mismatch; it ran to `Done:` (it printed `Verifying checksum ...`). |
| Marker | `cat <scratch>/ihp-sg13cmos5l/.fetched-version` read `f7bca32694fe3d58be0cc7d9df4b9f5db7161a14`. There is no `.git`. |
| Sibling symlinks | 530 relative symlinks in the subtree; the model libraries, Verilog-A sources (`psp103`, `r3_cmc`, `mosvar`) and xschem MOS symbols this design uses resolve. 262 dangle (moscap models, gnucap, xyce, pycell and LVS helpers that the `v0.3.0` sibling does not ship); the archived-repo install had 259 of 531 dangling against the same sibling, and none is loaded by this design. Filed generically as 2AMLogic/klayout-tools#3133. |
| OSDI, from source | `PDK=ihp-sg13g2` and `PDK=ihp-sg13cmos5l sim/tools/build-osdi.sh` (openvaf-r `v24.0.1mob`, checksum-pinned; ngspice 46, OSDI ABI v0.4) built and load-checked all models. `sim/tools/build-osdi.sh` previously built only four models; it now also builds `cap_cmomi` and `cap_cmomf` when `PDK=ihp-sg13cmos5l` (the Miller cap `Cc` is a `cap_cmomi`). `psp103`, `psp103_nqs`, `mosvar`, `r3_cmc` binaries are byte-identical to the old install's; `cap_cmomi`/`cap_cmomf` differ in sha256 although their `.va` sources are byte-identical (the old ones were built ad hoc; cause not established). |
| Netlist check | `PDK_ROOT=<scratch> python3 design/netlist.py --design sg13cmos5l --check -v`: `OK: 2 netlist(s) reproduce byte-for-byte, ERC is clean, and the pinout invariants hold.` |
| Old install not reused | The campaigns ran with `PDK_ROOT` pointing at the scratch root, not `~/share/pdk` (the old, host-provisioned install, which was only read for comparison). Each new PVT group's `inputs.sha256.json` names the scratch paths for every staged model card and OSDI binary. |
| Model-card difference old vs new | All 15 staged model libraries are byte-identical between the two installs, as are the `psp103`/`r3_cmc`/`cap_cmomi`/`cap_cmomf` Verilog-A sources. The tree differences are elsewhere (klayout pycell/tech JSON, xschem ring symbols, `.spiceinit`, LVS helpers). That is why the circuit metrics below reproduce exactly; it is a measured fact about these files, not an assumption. |

## RF MOS minimum width (`rfnmos_minW` / `rfpmos_minW` 0.15 um to 0.39 um)

Confirmed in `libs.tech/klayout/python/sg13cmos5l_pycell_lib/sg13cmos5l_tech.json`
(old pin `0.15u`, new pin `0.39u`; those two keys are the only difference in
that file's `*_minW` entries). The `rfnmos`/`rfpmos` pcells are the LV RF
flavours (`rfnmos_model: sg13_lv_nmos`). The design instantiates only
`sg13_hv_nmos` (10), `sg13_hv_pmos` (15), `rhigh` (4) and `cap_cmomi` (2) in
`design/sg13cmos5l/netlist/*.spice`; the layout extracts `pfet`/`nfet` that
bind to `sg13_hv_*` (stage 5b: all 133 MOS bind to `sg13_hv_*`, none to
`sg13_lv_*`). The HV RF keys (`rfnmosHV_minW` 0.33u, `rfpmosHV_minW` 0.39u) are
not relevant either: no RF flavour is drawn. The smallest MOS width is 1 um.
**The RF width rule affects no instantiated device; nothing was resized.**

## Campaign and citation inventory

"Selected" means named by `sim/characterization/selection.json`, the signoff
manifest, `.github/workflows/ci.yml` checks, or a README as the current record
for a claim. All old records ran on the fleet (runner klt 0.5.0, ngspice-46)
with the old install at `/home/ubuntu/share/pdk` (pin `607e18d`). All new runs
ran on the fleet with the scratch install (pin `f7bca326`), client klt
`0.7.0+gff97d692a147`, runner klt 0.5.0, ngspice-46, record ids carry the
date `20261012`. Fleet failures are quoted verbatim.

| # | Campaign / citation | Old record (old pin, client klt, design) | Selected? | New-pin run | Old vs new |
|---|---|---|---|---|---|
| 1 | Main PVT x resistor grid, DC + AC (rows 2-8), Cc sensitivity, Cc tolerance, divider attribution, 214 points | `20261011-070111-5391c68` (`607e18d`, `0.7.0+g0d0312b30708`, netlists `08a7b857`/`75ee39ce`) | Yes: `selection.json` `circuit_record`, `dc_informational_evidence`, `row10_margin_evidence` | `20261012-060932-c53f0177`: 214/214, complete. An earlier attempt `20261012-042925-c53f0177` is INCOMPLETE (124/214): groups `g00_dcsweep_tt_-40c_rtyp` and `g01_loopgain_tt_-40c_rtyp` were refused for the whole 3600 s cap-wait with `batch-fleet-provision.sh launch failed (exit 1): error: 8 instance(s) already running + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8`. The complete record was submitted with `SWEEP_BATCH_REUSE_WORK` of the incomplete one (3 groups reused: `g02`, `g03`, `g21`, `_batch/reused-reports.tsv`). Nothing ran locally. | All five CSVs (main, sensitivity, cc-tolerance, delta, divider-attribution) are `cmp`-identical to the old record. No metric or verdict moved. |
| 2 | Item-5 DC informational evidence and coverage inventory (rows 5, 7), derived from #1's raw DC grids | `evidence/20261011-070111-5391c68/` (offline derivation, hash-pinned generator) | Yes | Not re-derived. It is an offline reduction of #1's grids, so re-running it on the new grids would be a re-reduction, not a simulation; the new grids' DC columns equal the old ones, so there is nothing to re-point. | Unchanged. |
| 3 | Row-10 margin classification (DR-0014) of #1 | `evidence/20261011-070111-5391c68/row10-margins.*` | Yes | Not re-derived (same reasoning as #2). | Unchanged; `row10_record.py --check` still reproduces. |
| 4 | Two-injection loop gain (issue #135), 135 corners | `20261011-165616-eabde108` (`607e18d`, `0.7.0+g122d607d5c52`) | Referenced by README and CI (`loopgain2.py check`) | `20261012-071449-6a3c1475`: 135/135 passed screening; `loopgain2.py check` and `row10_loopgain2.py --check` reproduce it. | `loopgain2.csv` is `cmp`-identical; the margin classification differs from the old one only in record id. |
| 5 | Startup campaign, row 9 (DR-0009, 135-point grid; also a nominal point) | Selected: `20261011-070146-0c95530` (recollection of `20261011-031426-df3f802`; `607e18d`; client `0.7.0+g0d0312b30708`). Older, pre-#89 design: `20261010-075612-91e92aa` / `20261010-104827-91e92aa` (nominal, grid, ext, halfstep) | Yes: `selection.json` `startup_evidence` | `20261012-063918-bb1d73c` stages `nominal` and `grid` (135/135 evaluated). The manifest records `pdk_installed_commit` from the `.fetched-version` marker (`startup_campaign.py` now reads it; the old code ran `git rev-parse`, which a fetcher install cannot answer). Stages `ext` and `halfstep` were NOT re-run. | 135 points: same 135 failures (0 pass), same failure reasons. Metrics differ from `0c95530` by at most 1e-6 relative (nine-significant-digit trace rounding), except raw-file sha256, which differs. `startup_offstate.py` numbers (CI) unaffected because that check reads the old record. |
| 6 | Startup `ext` / `halfstep` stages | `20261010-104827-91e92aa-*` (pre-#89 design) | Historical context only (the selection names the grid) | Not re-run. | Historical-only, old pin. |
| 7 | Row-4 dropout under DR-0012 | `20261010-111618-19e8e39.dropout.*` (`607e18d`, `0.7.0+gca3089cd4b9f`; netlists `7953b25b`/`7982d728`, i.e. before #89) | README evidence; not in `selection.json` | `20261012-065435-b53a442f`: 45/45 resolved, `definitive: true`; `dropout_campaign.py reduce --check` passes. The md names `pdk_pin: sim/pdk-cmos5l.json`; the PDK revision is shown by the retained `corners/20261012-065435-b53a442f/_batch/*/inputs.sha256.json` paths. | Worst-by-upper-bound 0.25503424 V (old) vs 0.25503427 V (new), same corner (ss, 125 C, res_typ); worst interpolated 0.25504040 V vs 0.25504042 V. The old run was on the pre-#89 netlists, so this difference mixes the design change and the PDK; the PDK alone cannot be isolated from it. |
| 8 | Dynamic DoE load x Cout x ESR, rows 3/6/10 (exploratory) | Base `20261010-091123-a31c626`; with refinement `20261010-101245-6df50fd` (`607e18d`, `0.7.0+g8eec069c7576`, pre-#89 netlists) | README evidence, `row10_margins.py` | `20261012-074813-c94873ba` (384 sims, 178 ok / 14 failed) and refinement `20261012-080951-142dac4a` (688 more sims, 536 points, 490 ok / 46 failed). All 1072 sims ran on the fleet; every point passed screening, the failed counts are the analyser's metric failures. | Same point set, same ok/failed status at every point. Largest differences vs `6df50fd`: phase margin 0.157 deg, gain margin 0.101 dB, PSRR 2e-4 dB. Same caveat as #7: the old runs used the pre-#89 netlists. |
| 9 | Enable interface / disabled state (DR-0008): 12 requests | `ldo-cmos5l-enable/records/20261011-031743-df3f802` (`607e18d`, `0.7.0+g0d0312b30708`) | Yes: README and DR-0008 | `ldo-cmos5l-enable/records/20261012-072500-01e2fc6` (all 12 requests exit 0; `check.sh` passes) | `summary.csv` and `derived.txt` are `diff`-identical to the old record's. |
| 10 | Monte Carlo row 2 campaign | `ldo-cmos5l-monte-carlo/records/20261009-003009-3ee8306` (five-port pre-EN deck) | The only row-2 MC record, but its deck does not elaborate against the current six-port core | NOT re-run as a campaign. No row-2 statement about the EN core exists to refresh; a campaign on the live EN deck would be a new record (`run_campaign.sh submit`) and was not minted here. Bench check only: `evidence/20261012-074700-e3b134c-en-smoke/` (one tt/27 C unit, `status: pass`). | Historical-only (pre-EN design, old pin). Smoke `vout_v` 1.800306041 V, identical to the old smoke and to the five-port probe at all printed digits. |
| 11 | Backend validation (`backend-validation/*`), sensitivity and Cc-tolerance material of earlier PVT records, `20260916-*` to `20261011-060305-bcc60e2` PVT records, pass-device and HBT screens | Old pin or SG13G2 | No | Not re-run. The SG13G2 screens (`pass-device-screening*`, `layout/hbt-probe`) use `ihp-sg13g2` v0.3.0, whose pin this change does not touch. | Historical-only. Their `607e18d` mentions stay true for those runs. |
| 12 | Layout: curated DRC, PDK-deck DRC (222 rules), extraction, LVS, ERC | Reports committed under `layout/sg13cmos5l-ldo_core_cmos5l/` (klt `0.5.0+gb15edf5e3a2e` for drc/extract/lvs; `0.7.0+gb82427b30c96` for erc; old pin `607e18d` for the PDK deck) | Yes: signoff items 2, 3, 4, 11 | `layout/run_flow.sh` stages 1-7 re-run on the new PDK with the same pinned klt and KLayout (`0.30.12`, standalone `0.28.16`); stage 8 (ERC) re-run on the signoff-pin klt (the layout klt cannot parse `well_layer: null`, the documented per-stage split). Log: `sim/migration-inventory-155.layout-run.log`. | Every verdict unchanged: curated DRC clean, PDK deck 222 rules / 0 violations (183 + 39), extraction `pfet 128, nfet 5, rhigh 3, cap_cmomi 1`, LVS `match`, six negative controls mismatch, DRC control flags the planted defect, ERC `clean` with 0 findings, mutation flagged. All six committed reports and the GDS/extracted/reference files are byte-identical after the re-run (`git diff` empty), so the reports do not record a PDK revision; the new-pin evidence is this log. `run_flow.sh --check` passes under the layout pin. |

## Tool and deck revisions

| Item | Pin | Moved by this change? |
|---|---|---|
| klayout-tools fetch scripts (`KLAYOUT_TOOLS_REF`) | `v0.7.0` to `159527a551596caa74f290dcab08bdb8cc78ce93` | Yes, deliberately: `v0.7.0` still fetched the archived repository. |
| klt grading build (`KLAYOUT_TOOLS_SIGNOFF_REF`) | `b82427b30c96...` | No. |
| klt layout build (`KLAYOUT_TOOLS_LAYOUT_REF`) | `b15edf5e3a2e...` | No; none was needed (all reports reproduce under it). |
| KLayout Python | `0.30.12` | No. The layout klt prints its "tested against 0.30.10" engine-version warning, as in CI. |
| ngspice / openvaf-r | 46 / `v24.0.1mob` | No. |

## Selected citations

`selection.json` keeps pointing at the old-pin records of #1, #3 and #5. The
new-pin runs reproduce those records' verdicts and (for the PVT, loop-gain and
enable material) their result files exactly, so there is nothing to move: the
selection was compared before being left alone, and the old records stay
labelled as runs on `607e18d`. The T1 report remains an honest non-T1
(exit 3) result; no threshold, gate or verdict was changed.

## Not done

- A Monte Carlo campaign on the live EN deck (no prior EN record exists).
- Startup `ext` and `halfstep` stages on the new pin.
- Re-deriving the item-5, row-10 and DOE offline reductions from the new
  grids (re-reductions, not reruns).
- An old-design-on-new-pin run to split the design (#89) and PDK contributions
  to the small dropout and DoE differences in rows 7 and 8.
