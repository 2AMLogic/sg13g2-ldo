# Work Log

Chronological record of recently merged pull requests and closed issues, maintained by the Loom Guide role.

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)

### 2026-11-26

- **PR #388**: chore: gitignore the daemon's .loom/account-ranking.* state files
- **PR #385**: fix: share the singular-matrix log screen as one single-pass predicate
- **Issue #386** (closed): .loom/account-ranking.codex is untracked in main and fails check-main-clean.sh (daemon runtime state not gitignored)
- **Issue #383** (closed): Share the singular-matrix log check so long sweep logs cannot hide a fatal match
- **PR #382**: test: share the item-5 citation scratch fixture between the row-5 and row-7 suites
- **Issue #381** (closed): Share the scratch manifest fixture for row 5 and row 7 item 5 citation tests

### 2026-11-24

- **PR #377**: sim: remove duplicated row-7 name lists and unused corner_status_key param
- **PR #375**: refactor: share summarise_corners, echoed-options, selection and CLI helpers across row envelope drivers
- **PR #374**: fix: compose run_flow.sh EXIT traps and gitignore the .klt/ scratch dir
- **PR #370**: sim: consolidate the duplicated sha256-file helpers into sim/tools/file_hash.py
- **PR #371**: docs: disclose row-4 pex model_mismatch and flatten_schematic false for item 7
- **PR #361**: fix: refuse probe and non-definitive item-5 citations in row5/row7 envelope checks
- **PR #368**: refactor(sim): share summarise, summary_files and echoed-options check in row_envelope
- **PR #369**: refactor: share one graded-envelope loader between row-5 and row-7 T1 consumers
- **PR #363**: feat(layout): measure the row-4 pex delta on batch and cite it for T1 item 7
- **PR #357**: fix: quote AC-4 df_ug delta on the gate's baseline denominator in prose
- **PR #356**: fix: neutralize stale operating-point comment in two-injection loop-gain templates
- **PR #353**: sim: run DR-0015 experiment E2 -- two-injection bench at P3 with an operating-pointed run_loopgain2.sh
- **PR #352**: fix: print baseline denominator for ccprobe AC-4 f_ug percentage
- **PR #349**: sim: DR-0020 startup-ramp experiment result (reject) with testbench-local wrapper
- **PR #350**: feat: graded klt sim line/load regulation envelope for DR-0007 row 5
- **Issue #376** (closed): Drop two dead leftovers from the #373 row-envelope extraction (duplicated noload/fullload names, unused corner_status_key)
- **Issue #373** (closed): Dedupe remaining row-agnostic summarise_report, check_echoed_options, selection lookup, and CLI setup across row4/5/7_envelope.py
- **Issue #365** (closed): layout/run_flow.sh: stage 10's EXIT trap replaces the WORK cleanup trap, leaking the scratch tempdir
- **Issue #362** (closed): Consolidate ~10 duplicated sha256 file helpers in sim/ into one
- **Issue #366** (closed): Item-7 disclosure: the row-4 pex report's non-null model_mismatch and flatten_schematic: false are not stated anywhere
- **Issue #358** (closed): signoff: row5/row7_envelope.py check should bind the item-5 citation like row4_envelope.py (probe record is indistinguishable to the grader)
- **Issue #372** (closed): sim: close the file handles in the row-envelope drivers' json.load(open(...)) reads
- **Issue #364** (closed): Dedupe row4/5/7 envelope modules: move summarise/summary_files/echo-check into row_envelope.py
- **Issue #367** (closed): Dedupe load_row7_envelope and load_row5_envelope in sim/characterization/generate.py
- **Issue #312** (closed): Post-layout slice 2: klt pex schematic-vs-extracted delta for ratified row 4 (dropout) and the T1 item 7 citation
- **Issue #354** (closed): Prose in sim/ README and DR-0015 still quotes the AC-4 f_ug delta on the measured denominator (-2.29%) beside the 2% bound
- **Issue #355** (closed): sim: two-injection templates hardcode a 'legacy 1mA / 1uF / 0 ohm point' comment that contradicts an override-point deck
- **Issue #218** (closed): sim: run the two-injection loop-gain bench at DR-0015 point P3 (experiment E2)
- **Issue #348** (closed): ccprobe.py record md prints the AC-4 f_ug delta on a different denominator than the gate that bounds it
- **Issue #314** (closed): sim: run DR-0020's bounded confirm/reject experiment for the row-9 reference-ramp soft start (testbench-local, ~8 points)
- **Issue #319** (closed): Row 5 line/load regulation klt sim envelope (child of #316)

### 2026-11-23

- **PR #338**: sim: run DR-0015 experiment E3 -- Cc-width probe at P3 attributes the class-2 pole to the fixed gate node
- **PR #322**: feat: shared row-envelope module + graded row-7 Iq klt sim envelope (dr0007-row7-iq)
- **PR #347**: fix: refuse a non-string manifest entry name in the writer with StoreError
- **PR #346**: ci: drop the netlist job's duplicate klayout-tools install
- **PR #341**: sim: E4 divider/Cc probe at DR-0015 point P5 (four-point record)
- **PR #344**: fix: mirror the checker's media_type, uri-repo and size rules in the evidence writer
- **Issue #351** (closed): sim: startup_campaign.py still emits the deck-side OSDI preamble that batch_backend.py dropped after #313
- **Issue #219** (closed): sim: f_ug-vs-Cc probe at heavy load, DR-0015 point P3 (experiment E3)
- **Issue #317** (closed): Row 7 Iq envelope: shared row-envelope module and klt sim record (child of #316)
- **Issue #345** (closed): evidence_store: a non-hashable klt manifest `name` escapes put_files as TypeError, not StoreError (residual of the #251/#262/#272 class)
- **Issue #323** (closed): Install the pinned klt release once per netlist and screening CI job
- **Issue #315** (closed): sim: divider/Cc probe at DR-0015 point P5 (experiment E4) to test the rows 3+6+7+10 joint-satisfiability tension
- **Issue #334** (closed): Evidence writer still accepts three checker-only manifest rules (media_type, uri-repo consistency, strict size)
- **PR #340**: refactor: drop test-only dynamic_doe helpers; test the live paths
- **Issue #337** (closed): sim/ldo-cmos5l-pvt-sweep/dynamic_doe.py: remove test-only render_cout_esr, make_op, and to_base_int; test run_sweep.sh and validate_op directly
- **PR #336**: sim: remove unused AXIS_LEVELS constant from dynamic_doe
- **PR #335**: fix: enforce producer values and duplicate names in the evidence writer
- **PR #333**: docs: reword stale ci.yml lint/check:ci comment to the fail-loudly behavior
- **PR #331**: fix: make package.json scripts fail loudly pointing at ci.yml
- **PR #321**: batch backend: drop the deck-side pre_osdi preamble, verify runner-applied osdi_preload (#313)
- **Issue #332** (closed): Stale comment in ci.yml:124-127 calls package.json's lint/check:ci scripts "not configured placeholders"
- **Issue #326** (closed): Use one manifest validator for the evidence writer and CI
- **Issue #229** (closed): Twenty-seven unused module-level constants — four of them claim behaviour they do not have (the dimension #226's scan did not cover)
- **Issue #228** (closed): Remove the placeholder root package.json: five dead scripts that steer agent build-gate detection to a Node toolchain this repo does not have

### 2026-11-22

- **PR #329**: fix: pass CACHE_DIR through the subprocess env in the OSDI test harness
- **Issue #328** (closed): Pass the OSDI fixture cache path safely when TMPDIR contains an apostrophe

### 2026-11-21

- **PR #327**: fix: replace the unusable dpkg-deb recovery recipe with an install instruction
- **Issue #325** (closed): Remove the unusable dpkg-deb recovery recipe from the OSDI build diagnostic

### 2026-11-18

- **PR #310**: ci: report required checks on merge_group and plumb the queue base into the append-only gate
- **Issue #308** (closed): Merge queue: add the merge_group trigger and adapt the PR-metadata gates
- **PR #306**: fix: drop check_artifact_manifests.py verify twin of klt artifact verify
- **Issue #270** (closed): Remove check_artifact_manifests.py verify subcommand: hand-rolled twin of klt artifact verify

### 2026-11-17

- **PR #302**: docs(ci): name both jobs that fetch and cache-key the ihp-sg13cmos5l PDK
- **PR #301**: chore(loom): resync installed Loom to v0.19.1306
- **PR #299**: fix: gate item 9 attestation klt/PDK pins in check_pin_sync.py
- **PR #216**: feat(signoff): attest T1 items 1/9/10 with klt signoff --attest
- **Issue #220** (closed): ci.yml header says the ihp-sg13cmos5l PDK is "fetched only by netlist-check" — pass-device-screening-check fetches it too
- **Issue #298** (closed): Gate item 9's attestation pins (klt / PDK revision) in check_pin_sync.py
- **Issue #199** (closed): T1 grading: attest items 1, 9, 10 with klt signoff --attest instead of hand-rolled inventory envelopes

### 2026-11-16

- **PR #277**: chore(loom): resync installed Loom to v0.19.1302
- **PR #294**: docs: Tree docstring says four gated files, matching FILES in check_pin_sync tests
- **Issue #289** (closed): Two stale descriptions of check_pin_sync.py's scope after #267 widened the table to six pairs
- **PR #291**: fix: fail closed when put_files' manifest temp dir raises OSError
- **PR #288**: feat: gate the intra-file PDK pin copies and ci.yml's SG13G2 version
- **PR #279**: docs: decouple pdk-cmos5l fetch_method from the ci.yml KLAYOUT_TOOLS_REF value
- **Issue #292** (closed): DR-0021's Status bullet names the pre-#279 row-4 cited record
- **Issue #275** (closed): sim/pdk-cmos5l.json's fetch_method cites a stale KLAYOUT_TOOLS_REF (159527a5, ci.yml says 046ba746)
- **Issue #272** (closed): evidence_store: put_files' private temp dir can still escape as a non-StoreError (residual of the #262 class)
- **Issue #267** (closed): Gate sim/pdk-cmos5l.json's pinned_tarball_url SHA against its own pinned_commit
- **PR #280**: docs: correct DR-0017 stale item-6 citation claim via addendum; regrade ROADMAP items 5/6
- **Issue #254** (closed): spec: DR-0017 line 632 still says "Item 6 stays uncited" — stale after #225 cited the row-2 campaign
- **PR #274**: signoff: pin each driver's companion test and enforce the pairing
- **Issue #246** (closed): signoff item-9 inventory pins test_e1_oppoints.py but not test_row4_envelope.py
- **PR #284**: feat: pin row-4 PDK provenance by canonical projection instead of file bytes
- **Issue #282** (closed): row4-envelope provenance pins whole input files byte-level: a prose-only edit forces a fleet re-run
- **PR #281**: docs: name the pinned design and layout READMEs in signoff items 1 and 2 bullets
- **PR #271**: docs: record DR-0020 — row-9 startup overshoot remedy plan
- **PR #261**: refactor(sim): route row4_envelope tb_text through render_deck
- **Issue #276** (closed): signoff README item-1 bullet under-describes what item 1 pins (omits design/README.md and design/test_netlist.py)
- **Issue #245** (closed): A ninth @@TOKEN@@ render site survived #236: row4_envelope.py tb_text() has no leftover-@@ guard
- **Issue #221** (closed): spec: proposed decision record for a row-9 startup remedy on SG13CMOS5L (plan only)
- **PR #273**: evidence_store: convert preflight's remaining escape sites to StoreError
- **PR #266**: ci: gate ci.yml's klt/KLayout/PDK pins against their hardcoded copies
- **PR #264**: docs: record klayout-tools#5786 in the campaign's upstream-issues list and date the item-6 0.8.0 verdict
- **PR #260**: docs: refresh stale layout/DRC/LVS status in challenge-6 proposal
- **Issue #269** (closed): signoff CI: reproduction green can predate a sibling regeneration merge, so it does not prove post-merge reproduction
- **Issue #262** (closed): evidence_store: preflight's uri-scheme probe can still escape as a traceback (residual #251 item-1 site)
- **Issue #252** (closed): docs/chipalooza/challenge-6-proposal.md still says layout is empty and DRC/LVS not started — refresh or delete
- **Issue #250** (closed): Gate layout/run_flow.sh's klt + KLayout engine pins against ci.yml (no drift check today)
- **Issue #248** (closed): signoff: record klayout-tools#5786 in the Monte Carlo campaign's upstream-issues list

### 2026-11-15

- **PR #259**: refactor(design): delegate netlist.py's xschem export to klt netlist
- **PR #263**: fix(characterization): move superseded-statement provenance into _row_context so row_7_iq is pure
- **PR #255**: sim: drop four never-read bindings in item-9 testbench modules
- **PR #257**: fix: evidence writer's fail-closed contract is now literal (StoreError, rollback, pinned schema)
- **PR #242**: test: cover read_raw via complex_rawfile; drop dead corner_key
- **Issue #176** (closed): Simplify design/netlist.py: delegate xschem export to klt netlist
- **Issue #240** (closed): row_7_iq duplicates its provenance entry when called twice (shared mutable RowContext.sources)
- **Issue #232** (closed): Remove four never-read bindings in the hash-pinned item-9 testbench modules
- **Issue #251** (closed): evidence_store: narrow gaps in the documented fail-closed contract
- **Issue #226** (closed): sim/ldo-cmos5l-pvt-sweep: four never-called helpers — adopt complex_rawfile as read_raw's missing test, drop corner_key
- **PR #253**: test(sim): add guard-last checker for tracked test files
- **PR #241**: build: bump klayout-tools pins to the 0.9.2 release and regenerate evidence
- **PR #227**: refactor(sim): extract run_sweep.sh's post-process heredoc into a tested sweep_report module
- **Issue #256** (closed): signoff/README.md's item-6 measured-verdict paragraph says "the pinned build" but names klayout-tools 0.8.0
- **Issue #247** (closed): No check prevents reintroducing a mid-file `if __name__` guard in a test file
- **Issue #223** (closed): Extract run_sweep.sh's 411-line embedded Python heredoc into a tested sibling module
- **Issue #210** (closed): Bump klayout-tools pin 0.8.0 -> 0.9.2 (substrate-continuity ERC now evaluated; stage 8 needs --deck sg13cmos5l)
- **PR #249**: docs: record DR-0019 — startup record rows carry no log anchor
- **PR #244**: fix: move unittest.main() guard to end of test_row4_envelope.py
- **PR #243**: refactor(sim): collapse eight template renderers into sim/tools/render_deck.py
- **PR #239**: signoff: cite row-2 Monte Carlo campaign under T1 item 6 with declared partial coverage
- **PR #237**: refactor(characterization): split generate.py build() into per-row grading functions
- **PR #234**: ci: hash build-osdi.sh into the pass-device-screening PDK cache key
- **PR #217**: docs: roadmap as of 2026-11-13
- **PR #184**: feat(sim): store new evidence in the artifact store, commit manifests only
- **Issue #238** (closed): Should a startup record row anchor the klt log next to raw_sha256? (the dropped log path at startup_campaign.py:464)
- **Issue #236** (closed): Eight copies of the testbench @@TOKEN@@ renderer: CI's --check-env preflight does not exercise the renderer the corner grid uses
- **Issue #235** (closed): test_row4_envelope.py: `unittest.main()` guard sits mid-file, so a direct run silently skips the 6 ManifestCoupling controls
- **Issue #225** (closed): signoff: re-test item 6 partial-row-coverage citation — klayout-tools#2908 is CLOSED and the pinned 0.8.0 ruleset documents spec_rows/rows
- **Issue #224** (closed): Split the 605-line build() in sim/characterization/generate.py into per-row functions
- **Issue #222** (closed): CI: the PDK cache now carries built OSDI models but its key ignores sim/tools/build-osdi.sh, so a toolchain pin bump can silently reuse stale models
- **Issue #183** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

### 2026-11-14

- **PR #231**: feat(sim): grade row 4 with a klt sim limits-bearing corner matrix and cite it under T1 item 5
- **Issue #55** (closed): Corner verification: klt sim corner-matrix envelopes against the ratified spec (T1 item 5)
- **Issue #230** (closed): sim/ldo-cmos5l-pvt-sweep: five copies of sha256-a-file in one directory, under three names and two path conventions

### 2026-11-10

- **PR #211**: ci: gate attribution yield verdicts and supersede two stale klt 0.7.0 reports
- **Issue #206** (closed): Gate yield/attribution verdicts in monte-carlo-record (decision on 0.8.0 drift)

### 2026-11-06

- **PR #205**: ci: re-run committed klt yield verdicts in monte-carlo-record
- **Issue #204** (closed): CI: re-run committed klt yield verdicts now that klayout-tools[yield] installs from PyPI

### 2026-10-27

- **PR #197**: build: bump klayout-tools pins to 0.8.0 and regenerate evidence
- **PR #179**: feat(sg13cmos5l): add ldo_ilimit_cmos5l current limiter (candidate sizing) and nominal smoke record
- **Issue #196** (closed): Bump klayout-tools pin 97b6a54977d4 → 0.8.0
- **Issue #165** (closed): SG13CMOS5L: implement ldo_ilimit_cmos5l per DR-0017 and instantiate in core

### 2026-10-25

- **Issue #52** (closed): README: embed the fleet burndown chart (one line)

### 2026-10-24

- **PR #113**: docs: clarify row 4 branch status (#71)
- **PR #187**: ci: pin characterization-report job to ubuntu-24.04
- **Issue #71** (closed): Clarify row 4 branch status: ratified target, SG13CMOS5L pass, SG13G2 gap
- **Issue #186** (closed): main CI: openvaf-r cannot load libxml2.so.2 in pass-device-screening --check-env
- **Issue #185** (closed): main CI: loopgain2 generate.py --check differs from regeneration

### 2026-10-20

- **PR #175**: feat(layout): add extraction-only pex stage and committed klt pex report
- **Issue #172** (closed): Post-layout slice 1: klt pex stage in layout/run_flow.sh and a committed pex report for the CMOS5L core (T1 item 7)

### 2026-10-15

- **PR #163**: docs(spec): DR-0017 proposed SG13CMOS5L current-limiter plan for row 8
- **Issue #62** (closed): SG13CMOS5L startup: add enable input and transient testbench for spec row 9
- **Issue #63** (closed): SG13CMOS5L current limiter: topology and sizing design plan for row 8
- **Issue #57** (closed): Post-layout: klt pex extraction of the LDO core and spec re-run on the extracted netlist (T1 item 7)

### 2026-10-12

- **PR #161**: sim: E1 DC operating-point campaign for DR-0015 (four-point device measurement)
- **PR #160**: sim: #155 second increment -- EN-deck Monte Carlo, startup ext/halfstep, PDK-only controls, re-reductions
- **Issue #158** (closed): SG13CMOS5L: measure four device operating points for DR-0015 E1
- **Issue #155** (closed): Re-stamp SG13CMOS5L PDK pin from klayout-tools (IHP-Open-PDK dev f7bca326)
- **PR #157**: Re-stamp SG13CMOS5L PDK pin to IHP-Open-PDK dev f7bca326 and re-run evidence (#155)

### 2026-10-11

- **Issue #153** (closed): Guard decision review: keep rm-scope-unresolved-var flagged

- **PR #152**: layout: add an SG13G2 HBT vendor-fixture extraction/LVS probe witnessing the upstream bipolar gap
- **PR #151**: sim: two-injection (Middlebrook) loop-gain bench and 45-point fleet comparison (#135)
- **PR #149**: spec: DR-0016 keep in-tree error amplifier; reuse.lock evaluate -> kept
- **PR #148**: docs: complete README repo-layout block (#147)
- **PR #145**: sim: import fresh fleet rerun bcc60e2 evidence for the four reused groups (#132)
- **PR #144**: sim: HBT pass-device screening deck, record and DR-0001a addendum (#139)
- **PR #143**: docs: explicit PDK/model provenance table in sim/README (#141)
- **PR #142**: ci: run each sim/tools test suite once under its matching step
- **PR #140**: spec: add proposed DR-0015 — dynamic-window stability diagnosis and remedy ranking
- **PR #137**: test+CI: gate startup_offstate.py so the DR-0008 disabled-state current stays reproducible
- **PR #136**: sim: extend the loop-gain AC sweep to 10 GHz on the 45-point grid; row 10 stays ambiguous (#128)
- **PR #134**: startup_eval: sample off-state current in the disabled plateau, not the EN edge (#130)
- **PR #131**: SG13CMOS5L erramp: pull down the floating Mn3 gate (G1) when EN is low (#89)
- **PR #129**: spec+sim: classify row-10 margins under proposed DR-0014
- **PR #127**: characterization: integrate measured startup failures into the row-9 report (#112)
- **PR #124**: Characterization: consume pinned loaded DC evidence for rows 5 and 7
- **PR #122**: sim: validate complete DC grids before live sweep summaries
- **Issue #150** (closed): layout: add an SG13G2 HBT extraction/LVS probe that witnesses the upstream bipolar gaps
- **Issue #147** (closed): docs: README repo-layout block omits signoff/, ratification/, docs/ and root planning files
- **Issue #146** (closed): Decision record: close reuse.lock.json error-amplifier 'evaluate' (keep in-tree vs adopt sg13g2-opamp)
- **Issue #141** (closed): Docs: distinguish design branch and fleet PDK provenance in the simulation guide
- **Issue #139** (closed): BiCMOS: screen SG13G2 HBTs as pass device to back (or revisit) DR-0001's unmeasured bipolar ruling
- **Issue #138** (closed): CI: sim/tools unittest discovery runs twice in two jobs under mismatched step names
- **Issue #135** (closed): sim: two-injection (Middlebrook/Tian) loop-gain bench to resolve the 10 GHz plateau left by #128
- **Issue #133** (closed): test+CI: gate startup_offstate.py so the DR-0008 disabled-state current stays reproducible
- **Issue #132** (closed): Resubmit the 4 reused fleet groups of record 20261011-051956-eda9285 to prove their input bytes (follow-up to PR #131)
- **Issue #130** (closed): startup_eval: off_supply_current_a is sampled inside the EN edge, not in the off state
- **Issue #128** (closed): sim: resolve DR-0014 ceiling_unbounded row-10 points (extend loop-gain sweep ceiling or two-injection bench)
- **Issue #126** (closed): spec: define how row 10 margins are measured (multi-crossing PM, no -180 deg crossing GM) and classify existing traces
- **Issue #125** (closed): SG13CMOS5L stability: bounded offline diagnosis and compensation remedy proposal
- **Issue #123** (closed): Characterization: consume existing loaded DC evidence for rows 5 and 7
- **Issue #120** (closed): sim: validate complete DC grids before live sweep summaries
- **Issue #119** (closed): Guard decision review: keep gh-api-rawfield-body-literal-at flagged
- **Issue #112** (closed): Characterization: integrate measured startup failures into the row-9 report
- **Issue #89** (closed): SG13CMOS5L erramp: pull down the floating Mn3 gate when EN is low (disabled supply current)

### 2026-10-10

- **PR #118**: test: direct contract tests with negative controls for ac_metrics.py
- **PR #116**: sim: version the row-2 MC bench for the six-port EN core (#88)
- **PR #115**: test: offline unit tests for layout/ and design/ helpers (#114)
- **PR #111**: ci: enforce the append-only rule for sim/ evidence records (#102)
- **PR #110**: CI: gate layout/run_flow.sh --check; fix check mode passing on stale artifacts (#101)
- **PR #109**: docs: surface signoff regeneration contract in CLAUDE.md and AGENTS.md (#107)
- **Issue #117** (closed): test: unit tests with negative controls for sim ac_metrics.py (PM/GM/PSRR parsers)
- **Issue #114** (closed): Add offline unit tests with negative controls for layout/ and design/ helpers
- **Issue #107** (closed): Prevent repeated stale signoff evidence in agent PRs
- **Issue #102** (closed): CI: enforce the append-only rule for sim/ evidence records
- **Issue #101** (closed): CI: run layout/run_flow.sh --check so committed layout reports cannot go stale
- **Issue #88** (closed): sim: migrate tb_row2_accuracy.spice (Monte Carlo) to the six-port EN core
- **PR #108**: spec+sim: propose DR-0012 row-4 dropout measurement and re-score on a 5 mV batch campaign (#70)
- **Issue #70** (closed): spec: define how dropout is measured for row 4 (worst corner is 0.255 V at 1 % loss, a 45 mV margin)
- **PR #105**: SG13CMOS5L startup measurements: transient bench, evaluator and bounded PVT campaign (#69)
- **PR #104**: ci: gate design/netlist.py --check for the SG13CMOS5L design
- **PR #100**: sim: run the #64 dynamic DoE (384 + 688 refinement AC runs) on the batch fleet
- **Issue #69** (closed): SG13CMOS5L startup measurements: transient bench and bounded corner campaign
- **Issue #103** (closed): CI: gate design/netlist.py --check for the SG13CMOS5L design

- **PR #98**: CI: gate that the enable-smoke record reproduces from its raw reports
- **Issue #96** (closed): CI: gate that the enable-smoke record reproduces from its raw reports
- **PR #95**: CI: run the SG13CMOS5L topology guard on pull requests
- **Issue #94** (closed): CI: run the existing SG13CMOS5L topology guard on pull requests
- **PR #92**: sim: require output artifacts before preflight reports success
- **Issue #91** (closed): sim: require output artifacts before preflight reports success
- **PR #93**: layout: SG13CMOS5L EN port, XMen/XMbdis and refreshed physical evidence (#68)
- **Issue #68** (closed): SG13CMOS5L enable layout: route new interface and refresh physical evidence
- **PR #87**: feat(sg13cmos5l): EN enable interface and bench migration (#67)
- **Issue #67** (closed): SG13CMOS5L enable: implement electrical interface and migrate existing benches
- **PR #90**: sim: parameterise AC benches over load/Cout/ESR; bounded dynamic DoE tooling (#64)

### 2026-10-09

- **PR #85**: feat(signoff): artifact-anchored evidence for T1 items 1, 2, 9, 10 (#60)
- **Issue #60** (closed): Cite artifact-anchored evidence for T1 items 1, 2, 9 and 10 (design sources, layout, testbenches, repo hygiene)
- **PR #83**: Declare checked well/substrate ties in the klt erc supply spec (T1 item 11)
- **PR #78**: sim: SG13CMOS5L row-2 output-accuracy Monte Carlo campaign with klt yield evidence (item 6 left uncited)
- **Issue #59** (closed): Power delivery: declare checked well/substrate ties (tap_boxes) in the klt erc supply spec (T1 item 11)
- **Issue #80** (closed): Guard decision review: keep untracked-file cleanup flagged
- **Issue #79** (closed): README understates current T1 evidence count (2 versus 3)

### 2026-10-08

- **PR #76**: sim: T1 item 5 coverage inventory + informational DC evidence (partial; klt sim envelope blocked by klayout-tools#2727)
- **PR #73**: sim: per-spec-row characterization report + generic envelope for T1 item 8 (#58)
- **PR #65**: spec: ratify DR-0007 row 4 (dropout @ 50 mA) via the two-key ceremony; nine rows stay open
- **PR #61**: spec: DR-0007 row-by-row ratification record for the target table (#54)
- **Issue #58** (closed): Characterization: one aggregated per-spec-row report with a generic envelope (T1 item 8)
- **Issue #54** (closed): spec: ratify the target-spec table through the two-key mechanism (prerequisite for T1 items 5 and 6)

