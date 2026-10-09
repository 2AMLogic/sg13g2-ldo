# Work Log

Chronological record of recently merged pull requests and closed issues, maintained by the Loom Guide role.

### 2026-10-09

- **PR #78**: sim: SG13CMOS5L row-2 output-accuracy Monte Carlo campaign with klt yield evidence (item 6 left uncited)
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
