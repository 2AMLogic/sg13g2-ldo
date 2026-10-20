# Work Log

Chronological record of recently merged pull requests and closed issues, maintained by the Loom Guide role.

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

### 2026-09-22

- **PR #51**: spec: record sg13g2-opamp error-amp dependency and adoption gaps in porting-plan §2.2/§4
- **Issue #50** (closed): spec: porting-plan §2.2 never mentions sg13g2-opamp, though repos.yml names it as this repo's real error amp

### 2026-09-21

- **PR #48**: chore: add reuse.lock.json in_tree entry for error amplifier (evaluate)
- **PR #46**: feat: add klt signoff block manifest with CI-gated T1 tier report
- **PR #45**: feat: add klt erc supply spec and report for the SG13CMOS5L LDO core
- **Issue #47** (closed): 2am: reuse rule 9 — in-tree error amplifier duplicates sibling canary sg13g2-opamp — add reuse.lock.json in_tree entry (evaluate), then adopt or record
- **Issue #44** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **Issue #43** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo

### 2026-09-19

- **Issue #12** (closed): [Epic #542] 5A — Port to SG13CMOS5L for Chipalooza Challenge #6 brief

### 2026-09-18

- **PR #42**: docs: confirm rhigh-family width-offset double-count as a PDK bug (#36)
- **Issue #41** (closed): Sync design/README.md's device table (Rz, Rtop/Rbot) with the post-#28 schematic
- **Issue #36** (closed): pdk: rhigh's symbol value expression and its r3_cmc model disagree by 4.35% (width offset applied twice)

### 2026-09-17

- **PR #40**: design: re-compensate the SG13CMOS5L error amp on Cc alone so PM >= 45 deg holds at res_bcs/125C (DR-0005)
- **PR #39**: docs: SG13G2 branch divider is 600k/3.0uA, not 900k/2uA
- **Issue #35** (closed): design: re-compensate the SG13CMOS5L error amp so PM >= 45 deg holds at res_bcs/125C (DR-0004)
- **Issue #37** (closed): docs: SG13G2 branch divider is 600k/3.0uA, not the 900k/2uA design/README.md claims

### 2026-09-16

- **PR #38**: sim: PVT evidence for the SG13CMOS5L rhigh feedback divider, across the resistor corner (#31)
- **PR #34**: refactor: remove dead layout code paths and cite Via2's own PDK rule
- **PR #32**: layout: draw, DRC-verify and LVS-match the SG13CMOS5L LDO core
- **PR #30**: docs: SG13CMOS5L Chipalooza Challenge #6 proposal document
- **PR #27**: design: resize SG13CMOS5L Mpass and re-derive error-amp compensation
- **PR #26**: sim: PVT-cornered closed-loop verification for the SG13CMOS5L LDO
- **PR #24**: design: SG13CMOS5L schematic capture (ldo_core_cmos5l + real two-stage OTA error amp)
- **PR #23**: spec: DR-0002 — SG13CMOS5L device topology (sg13_hv_pmos pass device, CMOS-input error amp)
- **Issue #31** (closed): sim: re-run the SG13CMOS5L closed-loop PVT sweep against the PDK rhigh feedback divider (#28 replaced a corner-independent behavioral 300k)
- **Issue #33** (closed): layout/common_sg13cmos5l.py: dead-code cleanup (drain_on_metal2=False short trap, unused rhigh_drawn_squares/GATE_TAIL_UM)
- **Issue #22** (closed): 5A phase 4/4: SG13CMOS5L layout, DRC/LVS-clean GDS, and Challenge #6 proposal doc (sg13g2-ldo)
- **Issue #28** (closed): 5A phase 4a: SG13CMOS5L layout + DRC/LVS-clean GDS for ldo_core_cmos5l (split from #22)
- **Issue #29** (closed): 5A phase 4b: docs/chipalooza/challenge-6-proposal.md for the SG13CMOS5L LDO (split from #22)
- **Issue #25** (closed): SG13CMOS5L port: resize Mpass and re-derive error-amp compensation (Cc/Rz) per #21's PVT-verification findings
- **Issue #21** (closed): 5A phase 3/4: PVT-cornered testbenches for the SG13CMOS5L sg13g2-ldo port
- **Issue #20** (closed): 5A phase 2/4: sg13g2-ldo schematic capture for SG13CMOS5L (1.2V/3.3V rails)
- **Issue #19** (closed): 5A phase 1/4: SG13CMOS5L device-topology decision (sg13g2-ldo pass device + error amplifier)

### 2026-09-10

- **PR #18**: docs: resync ci.yml README with the pass-device-screening-check job
- **PR #16**: spec: ratify DR-0001 (sg13_hv_pmos pass-device flavor)
- **Issue #17** (closed): Docs: .github/workflows/README.md is stale — omits the pass-device-screening-check CI job
- **Issue #14** (closed): spec: ratify DR-0001 (pass-device flavor) from the sim/pass-device-screening evidence

### 2026-09-09

- **PR #15**: sim: sg13_hv_pmos pass-device screening deck (issue #13)
- **Issue #13** (closed): sim: `sg13_hv_pmos` pass-device screening deck (Vth, Ron·W at the 2.10 V dropout point, Cgate, continuous-short stress) across the HV corner grid — the input to porting-plan §4 item 1
