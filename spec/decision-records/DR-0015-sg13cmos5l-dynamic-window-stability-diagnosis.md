# DR-0015: SG13CMOS5L dynamic-window stability misses — offline diagnosis and compensation-remedy proposal

- **Status**: **Proposed.** This is a diagnosis and remedy-*proposal* record
  (issue #125). It is not a ratification act, authorizes no production
  circuit change, no simulation, no layout work, and no spec/window change.
  Row 10 (Stability), row 3 (Load), row 6 (PSRR) and row 7 (Iq) stay **Open**
  in [`DR-0007`](DR-0007-target-spec-row-ratification.md) exactly as they
  were. No threshold, CI gate, record or verdict is loosened anywhere.
- **Date**: 2026-10-11
- **Scope**: the **SG13CMOS5L branch only**, as every closed-loop record in
  this repo is. Offline analysis of the two committed #64 dynamic-DoE
  records (`20261010-091123-a31c626` base matrix,
  `20261010-101245-6df50fd` refinement round 1) at **six** selected
  operating points, plus the committed legacy grid records and lever
  studies those records cite. **Zero new simulations were run for this
  record.** Topology decisions ([`DR-0002`](DR-0002-sg13cmos5l-device-topology.md))
  and the current compensation
  ([`DR-0003`](DR-0003-sg13cmos5l-mpass-resize-and-compensation.md),
  [`DR-0005`](DR-0005-sg13cmos5l-cc-recompensation.md)) are preserved and
  analysed, not revisited.
- **Related**:
  [`DR-0014`](DR-0014-row10-stability-margin-classification.md) (the
  margin-classification methodology applied below; merged for #126,
  status Proposed), [`DR-0004`](DR-0004-sg13cmos5l-resistor-corner-stability.md)
  (the `Rz` corner mechanics this record reuses),
  `sim/ldo-cmos5l-pvt-sweep/README.md` §"Dynamic DoE" (the campaign and its
  miss tables), #64 (campaign issue), #126 (closed; methodology), #128
  (closed; the 10 GHz sweep-ceiling extension), #63/#89/#62 (open work that
  may change the analysed netlist — see the follow-up brief).

## Problem being diagnosed

The #64 campaign measured the SG13CMOS5L loop over the DR-0007 row 10
window (0–50 mA × 0.33–4.7 µF effective `Cout` × 0–500 mΩ ESR at four
PVT/resistor corners, 536 sampled operating points, 1,072 simulations) and
found sampled-point target misses in three distinct classes:

1. **Zero-load phase margin.** All 116 sampled 0 mA points have first-crossing
   PM < 45° at every corner and every `Cout`/ESR level (base matrix 9.1° to
   26.9°). Row 3 says "no external preload assumed", so these points are
   inside the specified window, not outside it.
2. **Heavy load, small `Cout` (ff/−40 °C/res_wcs).** At 25 and 50 mA with
   0.33 or 1 µF, PM and GM go to or below zero (worst sampled point
   PM −52.70°, GM −9.20 dB at 50 mA / 0.33 µF / 0 mΩ). At ss/125 °C/res_bcs
   the same corner of the window also misses (e.g. 50 mA / 0.33 µF / 0 mΩ:
   PM 40.56°, GM 8.07 dB), so the class is not ff-only.
3. **PSRR @ 1 kHz at low load.** 24 rows miss the > 50 dB information
   target, all at ss/125 °C, 0 mA, `Cout` ≥ 1.6 µF, worst 43.55 dB at the
   3.45 µF refinement midpoint.

The campaign's README defers the remedy to "a DR-0007 question for a
separate ratification review". This record is the bounded diagnosis of
those three classes and a ranked remedy *proposal*; it completes even
though no candidate is shown to close the misses (see "Disposition").

## Method and evidence base

- **Six operating points**, selected from the two committed records only,
  covering the three failure classes plus the legacy DR-0005 reference
  point. Every number below is read (or re-derived offline) from the
  committed CSV rows, the committed per-point AC traces under
  `sim/ldo-cmos5l-pvt-sweep/corners/<record>/`, or the committed DR-0014
  reclassification under
  `sim/ldo-cmos5l-pvt-sweep/evidence/20261010-101245-6df50fd/`.
- **Trace feature extraction** (all 0 dB crossings with slope, all
  −180°-mod-360° crossings, low-frequency phase, decade-boundary gains)
  was done offline with the repository's own committed parser semantics
  (`ac_metrics.unwrap_deg`, same interpolation as `loopgain_metrics`).
  No netlist was simulated; no record was edited.
- **Margin verdicts** are the committed DR-0014 classifications
  (`row10-margins.csv` of the combined record), not re-invented here.

### The six points

Point IDs follow the campaign convention
`<bench>_dyn_<mos>_<temp>c_r<res>_i<load>ua_c<cout>nf_e<esr>mohm`;
each point's netlist sha256 and invocation are in the record manifests
(`records/<record>.dynamic-doe.manifest.tsv`).

| # | Class | MOS/T/res corner | Load | `Cout` | ESR | Record (origin) | Loop-gain trace (`corners/<record>/…_ac.csv`, sha256/16) |
|---|---|---|---|---|---|---|---|
| P1 | 1 | ss / 125 °C / res_bcs | 0 mA | 1 µF | 0 mΩ | `…-a31c626` (base) | `loopgain_dyn_ss_125c_rbcs_i0ua_c1000nf_e0mohm` — `a72b31dea0776a19` |
| P2 | 1 (+HF shape) | ff / −40 °C / res_wcs | 0 mA | 1 µF | 0 mΩ | `…-a31c626` (base) | `loopgain_dyn_ff_-40c_rwcs_i0ua_c1000nf_e0mohm` — `0847619aa18e4707` |
| P3 | 2 | ff / −40 °C / res_wcs | 50 mA | 0.33 µF | 0 mΩ | `…-a31c626` (base) | `loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e0mohm` — `cc6fae43a41b1b4f` |
| P4 | 2 (ESR variant) | ff / −40 °C / res_wcs | 50 mA | 0.33 µF | 500 mΩ | `…-a31c626` (base) | `loopgain_dyn_ff_-40c_rwcs_i50000ua_c330nf_e500mohm` — `6403881feceeb83c` |
| P5 | 3 | ss / 125 °C / res_wcs | 0 mA | 3.45 µF | 0 mΩ | `…-6df50fd` (refine midpoint) | `loopgain_dyn_ss_125c_rwcs_i0ua_c3450nf_e0mohm` — `1fc3c1445213705e` |
| P6 | legacy reference | ss / 125 °C / res_bcs | 1 mA | 1 µF | 0 mΩ | `…-a31c626` (base) | `loopgain_dyn_ss_125c_rbcs_i1000ua_c1000nf_e0mohm` — `c3c5291de945aa81` |

P6 is the DR-0005 phase-margin binding point at the DR-0003/DR-0005
compensation's design centre (1 mA / 1 µF / 0 mΩ). P5 is the refinement
midpoint the base matrix alone would have under-reported (worst sampled
PSRR @ 1 kHz). The corresponding `psrr_dyn_*_ac.csv` traces sit beside
each loop-gain trace in the same directory.

### Measured summary at the six points

From the committed record rows and the committed DR-0014 classification:

| # | PM first / worst-crossing [°] | PM verdict (DR-0014) | GM [dB] | GM verdict | `f_ug` first 0 dB [Hz] | 0 dB crossings | PSRR@1k / @100k [dB] |
|---|---|---|---|---|---|---|---|
| P1 | 9.59 / 9.59 | **fail** | 61.73 | ambiguous (`ceiling_unbounded`) | 2 587 | 1 | 52.25 / 77.18 |
| P2 | 17.33 / +162.51 (2nd crossing) | **fail** | 53.12 | ambiguous (`ceiling_unbounded`) | 2 861 | 2 | 56.20 / 79.38 |
| P3 | −52.70 / −162.43 (2nd crossing) | **fail** | **−9.20** | **fail** | 1.981 M | 2 | 57.32 / 36.63 |
| P4 | 3.35 / +162.38 (2nd crossing) | **fail** | **0.82** | **fail** | 2.593 M | 2 | 57.32 / 36.65 |
| P5 | 17.61 / 17.61 | **fail** | 64.26 | ambiguous (`ceiling_unbounded`) | 1 052 | 1 | **43.55** / 92.53 |
| P6 | 53.87 / 53.87 | ambiguous (`ceiling_unbounded`) | 29.87 | ambiguous (`ceiling_unbounded`) | 39.1 k | 1 | 53.65 / 34.45 |

Note on sign: for P2 and P4 the worst-crossing value is quoted as the
DR-0014 angular distance (+162.51° / +162.38°); the raw record rows store
the same crossings with the wrapped-phase sign in
`phase_margin_worst_deg` (−162.51° / −162.38°). P3's worst crossing is
signed −162.43° in both places — see the Class 2 disclosure below.

Critical-line (−180° mod 360) crossings, committed DR-0014 values:
P1 113.5 kHz @ −61.7 dB; P2 114.5 kHz @ −53.1 dB; P3 **1.159 MHz @
+9.20 dB** (above unity — the encirclement that makes P3's scored PM
negative); P4 2.702 MHz @ −0.82 dB; P5 45.3 kHz @ −64.3 dB; P6 880 kHz @
−29.9 dB.

### Margin-methodology status (issue #125; #126 closed with DR-0014 Proposed)

#126 closed with [`DR-0014`](DR-0014-row10-stability-margin-classification.md)
committed (status Proposed). This record **applies DR-0014 as the
best-available reading** and additionally discloses, for every point
analysed: all 0 dB crossings with their frequencies, directions and
angular distances (table above and per-class sections), and all
critical-line crossings. Where the loop-gain trace has **no −180°
crossing in its 1 Hz–100 MHz sweep, GM stays unmeasured** — never
infinite, never a pass; 46 of the 536 campaign rows are in that state
(all at loads ≤ 1 mA, all with ESR > 0), and DR-0014 classifies every one
of them `ambiguous` (`ceiling_unbounded`), which this record preserves.

**No stability-compliance claim is made anywhere in this record**, for
three reasons that hold independently: (i) DR-0014 is Proposed, not
ratified; (ii) its ceiling premise P2 fails on **every** committed trace —
the loop gain rises again over the last decade of every 100 MHz trace
(P1 +12.34 dB, P2 +5.31 dB, P5 +9.10 dB over 10→100 MHz — the
`ceiling_last_decade_change_db` column of the committed
`row10-margins.csv`) and ends within −1.17…+0.53 dB of unity; (iii) the
10 GHz extension of the legacy 45-point grid (#128, evidence
`20261011-070111-5391c68`) shows the rise turning
over (last-decade change −0.43…−0.56 dB) but still ending +0.40…+1.17 dB
relative to 0 dB — 10.40…11.17 dB above the −10 dB ceiling floor — so all
45 verdicts there stay
`ambiguous`/`ceiling_unbounded` too. Whether the high-frequency rise is
circuit or bench artefact is DR-0014's open hypothesis (single voltage
injection at a MOSFET gate); resolving it is a prerequisite for *any*
row-10 compliance statement and is priced into the follow-up brief.

## Diagnosis

Format per class: **demonstrated** facts (measured, committed), then the
**mechanism hypothesis** with its quantitative support, then what remains
**ambiguous** and the discriminating experiment that would resolve it.
Small-signal parameters quoted below are derived from committed values
(`Rz` 1.700 MΩ nominal, `res_bcs`/125 °C ≈ 1.01 MΩ — DR-0004; `Cc` 5.47 pF
— DR-0005; divider legs 364.8 kΩ each at tt/−40 °C, `i_divider` 2.47 µA —
legacy record `20260917-023832-7061e8f.csv`), not from new simulation.

### Cross-cutting finding: the crossover is unbounded while the zero is fixed

Demonstrated, from the combined 536-row analysis:

- The first 0 dB crossing `f_ug` spans **871×–1 995×** per corner across
  the sampled window: ss/125/res_wcs 896 Hz … 1.52 MHz; ss/125/res_bcs
  1.19 kHz … 1.03 MHz; ff/−40/res_wcs 1.30 kHz … 2.59 MHz; ff/27/res_bcs
  1.45 kHz … 1.89 MHz.
- At 0 mA, `f_ug` scales as `Cout`^−0.51…^−0.52 at all four corners
  (e.g. ss/125/res_wcs: 3 484 Hz → 896 Hz for 0.33 → 4.7 µF), i.e.
  **1/√`Cout`** — the signature of exactly one `Cout`-scaling pole plus one
  fixed pole below crossover. At 50 mA the exponent is ≈ −0.68
  (ff/−40/res_wcs: 1.98 MHz → 329 kHz), a mixed structure.
- The compensation zero, by contrast, is fixed: `f_z = 1/(2π·Rz·Cc)` ≈
  17.1 kHz at res_typ/27 °C (28.8 kHz at `res_bcs`/125 °C where
  `Rz` ≈ 1.01 MΩ). The phase-boost band it creates is visible in the P6
  trace (phase −159.4° @ 10 kHz recovering to −110.0° @ 100 kHz) with
  `f_ug` = 39.1 kHz — the zero sits near the legacy crossover, exactly
  where DR-0003 placed it. At 0 mA (`f_ug` 0.9–5.6 kHz) the zero sits
  roughly **2–24× above** crossover depending on corner (res_bcs rows
  ≈ 4–24×, res_wcs rows ≈ 2–18×; the res_wcs end inherits the uncommitted
  wcs rho factor) and contributes only a few degrees; at 50 mA/ff (`f_ug`
  1.98–2.59 MHz) it is more than two orders of magnitude **below**
  crossover, equally out of place.

This is the single pattern all three classes hang off, and it is the
yardstick the candidate families are ranked against.

### Class 1 — zero-load phase margin (P1, P2, P5)

Demonstrated (P1/P2/P5 traces):

- The loop gain at 0 mA has already lost 27–32 dB and 65–86° of phase by
  1 Hz (P1: 90.2 dB, −64.9°; P2: 95.1 dB, −78.5°; P5: 72.8 dB, −85.5°;
  compare P6: 122.4 dB, −8.7°): the first pole is at or below the sweep
  floor and a second one is close behind (first −3 dB point 1.4–1.5 Hz).
- The 0 dB crossing is a **−38.5…−39.7 dB/decade** falling crossing at
  every zero-load point — two poles effectively below crossover, with no
  zero in between (the −40 dB/dec band runs from ≪1 kHz to the crossing).
- PM is **ESR-immune at zero load** across the whole committed window:
  at P2 itself: PM 17.33° / 17.58° / 17.84° at 0 / 250 / 500 mΩ (the
  500 mΩ record row's overall status is `failed` — no −180° crossing,
  hence no GM — but its PM is recorded).
  The ESR zero sits at `f_z,esr = 1/(2π·R_esr·Cout)` ≥ 67.7 kHz (4.7 µF,
  500 mΩ) — 12×–60× above every zero-load crossover. No ESR in the row-10
  window can rescue this class.
- GM at zero load is huge **where measured** (53–65 dB at P1/P2/P5) and
  unmeasured (no −180° crossing) at many high-`Cout`, high-ESR 0 mA rows —
  those stay ambiguous per DR-0014.

Mechanism (hypothesis, quantitatively supported): at 0 mA the pass device
carries only the feedback-divider current (2.47 µA committed), so its
`g_m` is in deep subthreshold (the 27–32 dB DC-loop-gain drop) and its
`r_o` is multi-MΩ. The VOUT node resistance is therefore set by the
**`rhigh` divider**, and the output pole lands at
`f_p,VOUT = 1/(2π·R_div·Cout)` — **at or below the 1 Hz sweep floor**.
Scaling the committed tt/−40 °C leg value (364.8 kΩ per leg, legacy record
`20260917-023832-7061e8f.csv`) with DR-0004's own factors (sheet rho
0.75× at res_bcs, temperature ×0.795 at 125 °C, ×1.1635 at −40 °C):
`R_div` ≈ 377 kΩ at ss/125/res_bcs ⇒ `f_p,VOUT` ≈ 0.42 Hz at 1 µF;
≥ 729 kΩ at ff/−40/res_wcs ⇒ ≤ 0.22 Hz (paralleling `r_o` only lowers
these). Both are clustered with the erramp's Miller pole (the measured
first −3 dB point is 1.4–1.5 Hz at all three zero-load points), so the
loop reaches its crossover with **two poles' worth of lag and ~3.5–4
decades of pole-to-crossover separation gone** — the −38.5…−39.7 dB/dec
crossing is that cluster seen at 1–5 kHz. The 1 Hz phases (−64.9° to
−85.5°) fit two poles straddling ~0.2–5 Hz. Contrast the same design at
1 mA (P6): there `r_o` of the loaded pass device (≈10 kΩ at 1 mA) pulls
this node's pole up to ≈ 1/(2π·10 kΩ·1 µF) ≈ 16 kHz — clear of the Miller
pole and of the 39.1 kHz crossover's neighbourhood, which is the
separation P6's −26.8 dB/dec, 53.87° trace shows. (`r_o` ≈ 10 kΩ at 1 mA
assumes VA ≈ 10 V — an assumption the E1 op-point extraction replaces
with a measurement.) Checks that survive the
absolute-value uncertainty: (i) the `Cout`^−0.5 scaling says exactly one
`Cout`-scaling pole sits below crossover, and the divider is the only
`Cout`-scaling element at 0 mA; (ii) the pole tracks the divider's corner
scaling, not the load: at ss/125 °C, 0 mA, 1 µF, `f_ug` = 2 587 Hz
(res_bcs) vs 1 980 Hz (res_wcs), ratio 1.31, against the divider-scaling
prediction √(R_div,wcs/R_div,bcs) ≈ 1.33 using DR-0004's committed bcs
factor and a symmetric wcs rho (1/0.75 — the wcs rho factor is not
committed, so this check carries that one assumption); (iii) the collapse
appears only when the external load (the only thing holding `r_o` down)
disappears.

Ambiguity / discriminating experiment: the split of the sub-1 Hz cluster
between the Miller pole (load-independent, erramp operating point) and
the divider pole cannot be *separated* from these AC traces alone,
because the erramp's own bias point also shifts between 0 mA and 1 mA.
Discriminator: a DC operating-point extraction (pass `I_d`, `g_ds`,
`V_eaout`, erramp node impedances) at P1/P2/P5/P6 — 4 runs, no new bench
needed (the follow-up brief prices it).

### Class 2 — heavy load, small `Cout` (P3, P4)

Demonstrated (P3/P4 traces):

- At 50 mA the loop is fast and healthy-looking at low frequency: DC gain
  117.5 dB, phase −0.6° at 1 Hz, first −3 dB at 110 Hz — but the 0 dB
  crossing lands at **1.98 MHz** with a **−39.6 dB/decade** slope and
  phase **−232.7°**: three poles' worth of lag at crossover. The trace
  crosses −180° at 1.159 MHz with gain **+9.20 dB** — an above-unity
  critical crossing (encirclement), which is why DR-0014 scores PM
  −52.70° and GM −9.20 dB as *fail*, not as a benign ±52.7°.
- **The class responds strongly to a zero placed near crossover**: with
  500 mΩ ESR (`f_z,esr` = 965 kHz), P4 improves to PM +3.35°, GM +0.82 dB
  (+56.05° PM, +10.02 dB GM versus P3); at 250 mΩ (`f_z,esr` = 1.93 MHz)
  the same point improves to PM −7.51°, GM −1.90 dB (+45.2° PM, +7.3 dB
  GM). The neighbouring 25 mA / 330 nF slice is PM-positive from 250 mΩ up
  (PM +0.52° at 250 mΩ, +12.09° at 500 mΩ, against −40.98° at 0 mΩ). The
  loop is *not* structurally broken at heavy load — it is missing ~55° of
  phase lift right below a ~2–2.6 MHz crossover, and an in-window zero
  delivers most of it.
- The second (rising) 0 dB crossing at 59–60 MHz carries +162.4…162.5° of
  angular distance from the critical point (P3's is signed −162.43° only
  because its earlier above-unity critical crossing starts the
  encirclement count): far from the critical point, disclosed, and
  classified per DR-0014.
- At fixed `Cout` = 1 µF the failure is load- and corner-graded, not a
  cliff: ff/−40/res_wcs PM by load 74.8° (1 mA) → 31.2° (13 mA) → 12.6°
  (25 mA) → −5.8° (50 mA); ss/125/res_bcs stays ≥ 66.8° to 50 mA at 1 µF
  but fails at 0.33 µF (40.56°/8.07 dB). The class tracks the corner where
  the loop is fastest.

Mechanism (hypothesis): at heavy load the pass `g_m` and loop gain rise
(ff/−40 the strongest), pushing `f_ug` up to ~2 MHz, while the *small*
`Cout` fails to hold the VOUT pole down (`r_o` at 50 mA is low; the pole
sits near 1/(2π·`r_o`·`Cout`) ~ MHz) and the pass-gate node pole
(`EAOUT`, a w=2800 µm gate) plausibly lives in the same region
(unquantified here; E3 separates the two). Three poles end up inside a
decade around the crossover. The `Rz`/`Cc` zero is
far below and contributes only its old Miller-pole cancellation, no net
lift at 2 MHz: nominal `f_z` = 17.1 kHz, and at res_wcs/−40 °C it is
lower still — DR-0004's temperature term alone (×1.1635 at ΔT = −67 K)
puts `Rz` ≥ 1.98 MΩ, i.e. `f_z` ≤ 14.7 kHz, before any res_wcs
sheet-rho increase (DR-0004: wcs "moves the same knob the other way").

Ambiguity / discriminating experiments: (i) which of the VOUT pole and
the EAOUT gate pole is the third pole at 2 MHz cannot be told apart from
these traces; discriminator: a `f_ug`-vs-`Cc` probe at P3
(`f_ug` ∝ `Cc`^−x separates a `Cout`-side from a fixed-gate-side pole),
3 runs at the DR-0005 sensitivity levels {0.5×, 1×, 2×}; (ii) whether the
+9.20 dB above-unity critical crossing is visible to a two-injection
loop-gain bench identically (bench-vs-circuit, DR-0014's open hypothesis).

### Class 3 — PSRR @ 1 kHz at low load (P5)

Demonstrated (P5 + PSRR traces of all six points, plus the combined CSV):

- The closed-loop PSRR curve has a notch whose minimum frequency sits at
  0.71–1.07 × `f_ug` at every one of the six points (P1: 2 512 Hz vs
  2 587 Hz; P2: 2 818 vs 2 861; P4: 2.512 MHz vs 2.593 MHz; P5: 1 122 Hz
  vs 1 052 Hz; P6: 28.2 kHz vs 39.1 kHz; P3: 1.41 MHz vs 1.98 MHz):
  **rejection dies where the loop gain dies**.
- All 24 PSRR@1 kHz misses in the combined analysis are ss/125 °C, 0 mA,
  `Cout` ≥ 1.6 µF, `f_ug` 896–1 559 Hz, ESR-independent (PSRR@1 kHz
  varies ≤ 0.3 dB across ESR at fixed `Cout`). The worst point (P5,
  43.55 dB) is where `f_ug` ≈ 1.05 kHz lands the notch **on** the 1 kHz
  measurement frequency; 4.7 µF (`f_ug` 896 Hz) reads 46.11 dB because the
  notch has moved past 1 kHz. The base matrix alone (worst 47.34 dB at
  2.2 µF) under-reported exactly this interior minimum — the refinement
  midpoint found it.
- At 1 mA the loop gain at 1 kHz is 58.7 dB yet PSRR@1 kHz is 53.65 dB:
  the 1 mA value is **feedthrough-floor-limited** (DR-0007 row 6: PSRR
  margin "was spent to close phase margin" in DR-0005). At 0 mA the miss
  is **loop-gain-limited**: P5 has |L(1 kHz)| = 0.85 dB and PSRR@1 kHz =
  43.55 dB.

Mechanism: class 3 is not an independent failure — it is class 1's
collapsed crossover seen through the PSRR bench. With `f_ug`(0 mA) ∝
1/√(`R_div`·`Cout`·`Cc`-product structure), every sampled combination at
ss/125 °C with `Cout` ≥ 1.6 µF puts `f_ug` at ≲ 1.6 kHz, and the 1 kHz
ripple then meets the loop where it no longer rejects. The ss/125 °C
binding is expected: slow MOS lowers loop gain (and `f_ug`) further at the
same `Cout`.

Ambiguity: the feedthrough floor at 0 mA (the PSRR value the notch bottom
would show with |L| ≈ 0) is only bracketed by the six points (43.3–38.1 dB
measured at the notch bottom); its exact value sets how far above
`f_ug` ≈ 1.6 kHz the crossover must sit to clear 50 dB at 1 kHz, and it is
not separable from these traces. Discriminator: the divider/`Cc` probe of
the follow-up brief (E4) at P5 conditions.

## Candidate families (exactly three, per issue #125)

Each family is assessed against: expected effect on each class, row 7 Iq
cost, row 4/5 regression risk, implementation complexity, and `Cc`
tolerance assumptions. **No post-change margin is claimed for any family**
— unknowns stay unknown until the follow-up measures them.

### (A) Passive `Rz`/`Cc` retuning — rejected as a standalone remedy

Existing measured evidence (all committed at the 1 mA / 1 µF legacy point,
45-point PVT grid — DR-0005's lever studies, records `20260917-023832-*`):

- `Rz` ↑ fixes PM and **breaks GM** at res_wcs/−40 °C (measured: 1600 µm
  `leff` leaves 0.7 dB GM margin; 1800 µm fails GM at 5/45 points) — the
  GM-binding corner is *inside* class 2's corner.
- `Cc` ↑ fixes PM and **breaks PSRR@1 kHz** (measured: 2× nominal width →
  47.67 dB vs > 50 dB) — the PSRR-binding axis is class 3's axis.
- `Cc` ↓ breaks PM at `res_bcs`/125 °C (measured: 0.5× width → 40.29°).
  The measured pass window is `Cc` ×0.65–×1.52 with the current 170e-6 at
  its geometric centre; that window was measured *at 1 mA* and every edge
  of it is a corner that recurs inside the failing classes.

Scaling argument from this record's own measurements: at 0 mA
`f_ug` ∝ `Cc`^−1/2 (the `Cout`^−1/2 exponent above, `Cc` in the same
Miller-pole position). Lifting P5-class points clear of the PSRR notch
(`f_ug` ≥ 1.6 kHz at ss/125/res_wcs/4.7 µF, from 896 Hz) needs ×1.79, i.e.
`Cc` ≈ ×0.31 — more than 2× below the measured window's lower edge, which
already fails 1 mA PM. Pulling class 2's 2.6 MHz crossover down needs the
opposite move (`Cc` ↑, direct measured PSRR cost). **One fixed pair cannot
serve a crossover that spans the 871×–1 995× ranges measured above; the
mechanism is wrong, not the values.** Retuning is retained only as a trim inside family B.

Rank: **3** (rejected standalone; evidence: measured lever tables + this
record's scaling).

### (B) Load-tracking compensation zero — recommended subject of the follow-up

Mechanism: replace the fixed `f_z = 1/(2π·Rz·Cc)` with one that tracks the
pass device's operating point, so the phase lift lands near `f_ug` at both
ends of the window. This is the "gm-tracking triode-MOS refinement" that
DR-0002/DR-0003 flag as available and DR-0005 explicitly deferred ("a
topology change that needs its own record and its own evidence"); the
sibling fleet has the precedent (gf180-ldo `DR-0015` adaptive `Rz`,
adopted there only after a fixed-`Rz` lever was proved insufficient —
exactly the situation this record documents for SG13CMOS5L). Concrete
instantiation for this erramp: `Rz` (the 39-stripe `rhigh` meander between
`MZ` and `G1`) replaced or shunted by a triode MOSFET whose gate is driven
from a pass-`V_sg`-correlated node (the `EAOUT` node *is* that signal: it
encodes load current through the pass device's `V_gs`); `Rz` carries no DC
current (it is in series with `Cc` between two high-impedance nodes), so a
zero-DC triode is topologically clean.

Expected effect, class by class:

- **Class 2 (best supported)**: the in-window ESR-zero measurement (P3→P4:
  +56° PM / +10 dB GM from a zero at 965 kHz under a 2.6 MHz crossover) is
  a direct measurement of what a designer-placed zero near the heavy-load
  crossover buys. A tracking `f_z` aiming at ~0.3–0.5 × `f_ug`(50 mA)
  ≈ 0.6–1.3 MHz at the heavy end is the same mechanism. Whether it also
  clears P3's above-unity critical crossing (GM −9.20 dB) is **not
  derivable offline** — a zero moves phase, the encirclement needs the
  −180° crossing pushed below 0 dB; hypothesis only.
- **Class 1 (hypothesis, fragile end)**: at 0 mA the pass device is in
  subthreshold at ~2.5 µA; a `V_gs`-driven triode's resistance is
  exponential in `V_gs` there, so the tracking law that is clean in strong
  inversion becomes corner- and bias-fragile exactly where class 1 lives.
  Whether a useable zero lands near 1–3 kHz at 0 mA across MOS corners is
  **unknown** and is the follow-up's first discriminating question. Note
  the failure mode DR-0005 recorded for the *fixed* version of this trade:
  MOS-corner dependence replaces resistor-corner dependence — a different
  trade, not obviously a better one; the follow-up must measure both axes.
- **Class 3: no effect claimed.** A zero shapes phase, not loop-gain
  magnitude at 1 kHz; the class-3 miss is a |L(1 kHz)| collapse (P5: 0.85
  dB). Family B does not address class 3, and no measurement here suggests
  it would.

Iq cost: ≈ 0 µA expected (no new DC path; sense taken from `EAOUT`; any
buffer/sense mirror must fit inside the 5.28 µA worst-corner headroom,
measured 24.72 µA against < 30 µA). Row 4/5 risk: low (no DC operating
point change; `Rz`/`Cc` are analytically DC-invariant — DR-0005 verified
this class of change leaves all DC rows byte-identical). Row 6 risk: real
and measured-in-kind (DR-0003 recorded the zero's placement pulling down
mid-band loop gain; PSRR@1 kHz must be re-verified at the new `f_z`
placements). `Cc` tolerance: `f_z` ∝ 1/`Cc` keeps the un-cornered-cap
multiplier *inside* the tracking ratio; the DR-0005 ×0.65–×1.52 window
logic re-applies around whatever `f_z`-vs-track curve is chosen, and the
follow-up must re-run the `cc-tolerance` experiment at the new operating
points. Complexity: one device + gate routing (lowest of the structural
options; `Rz`'s forty-stripe meander draw in
`layout/sg13cmos5l-ldo_core_cmos5l/generate.py` is replaced by a MOS
placement).

Rank: **1** — the only family whose mechanism tracks the demonstrated root
pattern (a crossover spanning three decades against a fixed zero);
heavy-load effect supported by in-window measurement; zero-load effect an
explicit hypothesis; class-3 effect explicitly none.

### (C) Internal minimum-load / dummy-load bias — rejected as infeasible on row 7

Mechanism: an always-on internal shunt at VOUT keeps the pass device from
starving at zero external load, holding `g_m` up and the VOUT pole up.
Class 1's demonstrated pole is divider-resistance-set, so only a
**resistive** shunt moves it (a cascoded current sink presents high
impedance and moves nothing).

Budget arithmetic (all committed numbers): row 7 allows Iq < 30 µA;
measured worst-corner Iq is 24.72 µA → **≤ 5.28 µA** available. A
maximum-strength permanent shunt is therefore ≈ 341 kΩ at 1.8 V. That is
nowhere near the problem: class 1's pole is `R_div`-set at ≈ 0.2–0.45 Hz
(class-1 mechanism above), and the shunt only moves `R_VOUT` from
≈ 377–730 kΩ to ≈ 210–230 kΩ — pole ×≈3 (to ≈ 0.7 Hz), `f_ug` ×√3 ≈ ×1.7
—
leaving **both poles still decades below the crossover and PM still
limited to the few degrees of `Rz`/`Cc` zero boost the trace already
shows** (P1's 9.59°). Reaching PM 45° at 0 mA by loading alone needs the
pole at *or above* the crossover: R_VOUT ≲ 1/(2π·`f_ug`·`Cout`) ≈ 61 Ω
at P1 — a ~29 mA shunt, ≈ 1 000× the entire Iq row and ≈ 5 500× the
available headroom. The corollary cuts the same way for class 3: ×1.7 on
`f_ug` lifts P5's corner from 896 Hz to only ~1.5 kHz, and the committed
row at 1 559 Hz still misses (49.39 dB). Class 2 is a heavy-load failure
a minimum load cannot touch. (Recorded trim, not fix: the divider itself
is the pole; halving `R_div` costs +2.47 µA of the 5.28 µA headroom and
buys the same ×1.41 `f_ug` and ~2–4 dB of PSRR@1 kHz — insufficient
alone, and it re-opens DR-0005's `Rz`-meander/divider layout.) A
high-impedance (cascoded current-sink) dummy is worse than useless here:
it presents high impedance and moves the pole not at all.

Rank: **2** (infeasible as a fix by arithmetic on committed values; ranked
above A only because a bounded divider trim is a real, measurable partial
lever for class 3 — A offers nothing for class 3 without breaking 1 mA PM).

## Comparison table

| | (A) passive `Rz`/`Cc` | (B) load-tracking zero | (C) min-load shunt |
|---|---|---|---|
| Class 1 (0 mA PM) | no path (window edges measured failing) | hypothesis (subthreshold tracking) | pole ×3 max, PM still ≪ 45° |
| Class 2 (50 mA PM/GM) | `Cc` ↑ helps PM, measured PSRR cost; `Rz` ↑ breaks GM here | best supported (+56° analogue measured in-window) | not applicable |
| Class 3 (PSRR@1 kHz) | `Cc` ↓ ×0.31 needed — measured PM failure | no mechanism claimed | ×1.7 `f_ug`, still in notch |
| Row 7 Iq cost | 0 | ≈ 0 (≤ headroom for sense) | ≈ 1 000× the whole row to work |
| Row 4/5 risk | low (DC-invariant) | low (DC-invariant), re-verify | low-moderate (DC path added) |
| Row 6 risk | measured (DR-0005 window) | real, re-verify at new `f_z` | small |
| `Cc` tolerance | window ×0.65–×1.52 binds at 1 mA | tracking absorbs load axis; window re-check needed | unchanged |
| Complexity | lowest (values only) | medium (1 device + routing) | medium (shunt device/route) |
| Verdict | **rejected standalone** | **recommended follow-up subject** | **rejected infeasible** |

## Disposition

**The evidence is insufficient to claim that any of the three families
closes the three failure classes.** What the evidence *does* support:

1. Family **(B)** is recommended as the subject of the follow-up
   experimental issue, restricted to classes 1 and 2: it is the only
   family whose mechanism matches the demonstrated root pattern, its
   heavy-load effect has a direct in-window measured analogue, and its
   zero-load end and GM recovery are cleanly falsifiable by a small,
   bounded experiment set. No post-change margin is claimed.
2. Class 3 is **not addressed by (B)** and is arithmetically out of reach
   of (C) within row 7. Within the analysed evidence it is bounded below
   by two ratified rows pulling against each other: `f_ug`(0 mA) is held
   down by `Cout` (measured `Cout`^−1/2) and the divider (Iq-funded), and
   held down at the `Cc` end by the measured 1 mA PM window edge; PSRR@1
   kHz > 50 dB needs `f_ug` ≳ 1.6 kHz at 0 mA. **Derived tension, to be
   confirmed by probe E4 before anything is decided: rows 3+6+7+10 as
   written may be jointly unsatisfiable at 0 mA / `Cout` ≥ 1.6 µF for this
   three-stage topology under a 30 µA cap.** If E4 confirms it, the
   resolution is a ratification-scope question (DR-0007 row wording), to
   be taken through the existing two-key process — explicitly **not**
   decided by this record.
3. Priorities if the follow-up budget must be cut: E2 (two-injection
   bench) first, because every stability verdict — including any future
   fix's — is `ambiguous` until the ceiling premise can be met; then E3/E1
   (class-2 pole attribution and op-points), then the (B) prototype
   screening, then E4.

## Follow-up implementation/experiment brief (for a separately approved issue)

Named circuit/harness surfaces:

- `design/sg13cmos5l/ldo_erramp_cmos5l.sch` (+ `.sym`, regenerated
  `design/sg13cmos5l/netlist/ldo_erramp_cmos5l.spice` via
  `design/netlist.py`) — the (B) prototype device(s) between `OUT`/`MZ`
  and `G1`, gate sense from `EAOUT` (three gate-drive variants below).
- `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh`, `dynamic_doe.py`,
  `testbench/tb_loopgain_cmos5l.spice.tmpl` (a two-injection variant bench),
  `ac_metrics.py` (only if DR-0014's parser needs a bench-mode flag).
- `layout/sg13cmos5l-ldo_core_cmos5l/generate.py` — only after a candidate
  survives screening; then `layout/run_flow.sh` end-to-end (curated deck,
  PDK deck, extraction/LVS incl. the five negative controls), and
  `signoff/README.md#regenerating` in the documented order with the exact
  pinned grader.

Discriminating experiments (bounded, run before any candidate sweep;
all reuse committed benches and the #64 fleet path):

| # | experiment | points | runs |
|---|---|---|---|
| E1 | DC op-point extraction (pass `I_d`/`g_ds`/`V_eaout`, erramp) | P1, P2, P5, P6 | 4 |
| E2 | two-injection (Middlebrook/Tian) loop-gain bench | P3, P6 | 2 decks, full AC sweep each — one batch round |
| E3 | `f_ug`-vs-`Cc` probe at heavy load, `Cc` ∈ {0.5×, 1×, 2×} | P3 | 3 |
| E4 | divider/`Cc` probe at P5 conditions: `R_div` ∈ {1×, 0.5×}, `Cc` ∈ {1×, 0.65×} | P5 | 4 |

(B) prototype screening (only if E1–E4 leave (B) standing): triode
`Rz`-replacement, gate-drive variants {`EAOUT` direct, `EAOUT`-scaled
½, 1:100 sensed mirror of pass current}, device sizes giving
R(27 °C, nominal) ∈ {0.5×, 1×, 2×} of 1.70 MΩ — at most 6 instantiations
× 6 points of this record × 2 benches = **≤ 72 AC runs, one batch round**.
A candidate that does not clear every recorded *fail* verdict at the six
points under DR-0014 (fails are decidable independent of the ceiling
premise) stops there — no full-matrix run, no layout, no claim.

Then, and only then, for a surviving candidate (the full checklist the
follow-up issue must carry): re-run the complete #64 matrix + one
refinement round (append-only under `sim/ldo-cmos5l-pvt-sweep/records/`);
legacy regression at 1 mA / 1 µF / 0 mΩ against `20260917-023832-7061e8f`
and `20261010-025634-60a3e81` at the committed 0.1 tolerance; re-run
DR-0005's `cc-tolerance` experiment at P1/P3/P5 conditions; re-verify rows
4/5/7 on the 45-point DC grid; regenerate the layout and run the full
signoff order. Dependencies: this DR (mechanism + bounds), DR-0014 (verdict
semantics; its Proposed status must be resolved or carried knowingly),
#128's ceiling question (E2 is its discriminator), and a re-check of
#63/#89/#62 status against the analysed netlist snapshot before drafting —
this record analyses the netlist as committed at the #64 records' pins and
makes no claim about later circuit changes.

## What would overturn parts of this

- E2 showing the high-frequency rise and/or P3's above-unity critical
  crossing is a bench artefact: class 2's GM fail and the second-crossing
  disclosures would need re-reading (PM deficits stand — they are
  first-crossing facts).
- E1/E3 attributing the class-2 third pole to the EAOUT gate node rather
  than VOUT: the (B) target `f_z` curve at heavy load changes; the
  family ranking does not.
- E4 measuring a materially higher PSRR notch bottom than the bracketed
  38–43 dB: the class-3 tension of the Disposition weakens or dissolves.
- Real CMOS5L MoM-cap characterization (DR-0005's standing caveat) moving
  `Cc`'s true value outside ×0.65–×1.52: every `Cc`-coupled bound here
  (including family A's rejection arithmetic) shifts with it.
- A ratified change to DR-0007 rows 3/6/7/10 wording through the two-key
  process: this record's class definitions would be re-scoped, not
  re-derived.

## Not claimed

No new simulation; no historical record or verdict edited; no spec row,
threshold or gate relaxed; no row-10 (or any row) compliance claim —
sampled-point failures and ambiguities only, with every crossing disclosed
under the committed DR-0014 reading; no post-change margin prediction for
any candidate; no ratification. `sim/` evidence stays append-only.

## References

- Issue #125 (this record's tracking issue); #64 (campaign), #126/#128
  (methodology and ceiling), #63/#89/#62 (netlist-drift watch).
- `sim/ldo-cmos5l-pvt-sweep/README.md` §"Dynamic DoE" (matrix, miss
  tables, refinement rule, 46 unmeasured-GM rows).
- `sim/ldo-cmos5l-pvt-sweep/records/20261010-091123-a31c626.dynamic-doe.{csv,md}`
  and `…/20261010-101245-6df50fd.dynamic-doe.{csv,md}` (rows cited);
  `…/records/20260917-023832-7061e8f.{csv,cc-tolerance.csv}` (divider and
  lever evidence).
- `sim/ldo-cmos5l-pvt-sweep/evidence/20261010-101245-6df50fd/row10-margins.{csv,md}`
  (DR-0014 verdicts at the six points) and
  `…/evidence/20261011-070111-5391c68/row10-margins.md` (10 GHz ceiling
  behaviour).
- [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md),
  [`DR-0003`](DR-0003-sg13cmos5l-mpass-resize-and-compensation.md),
  [`DR-0004`](DR-0004-sg13cmos5l-resistor-corner-stability.md),
  [`DR-0005`](DR-0005-sg13cmos5l-cc-recompensation.md),
  [`DR-0007`](DR-0007-target-spec-row-ratification.md),
  [`DR-0014`](DR-0014-row10-stability-margin-classification.md).
