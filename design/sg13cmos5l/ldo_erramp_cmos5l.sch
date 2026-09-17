v {xschem version=3.4.7 file_version=1.3
* ldo_erramp_cmos5l -- SG13CMOS5L error amplifier for ldo_core_cmos5l
* (issue #20, phase 2/4 of the SG13CMOS5L port tracked by #12).
*
* THE RATIFIED TOPOLOGY THIS CELL IMPLEMENTS is
* spec/decision-records/DR-0002-sg13cmos5l-device-topology.md (PR #23),
* Decision (b): "a two-stage, Miller-compensated, single-ended-output OTA
* built entirely from HV (3.3 V-class) devices". Every device flavour and
* every structural choice below is that record's, not this file's:
*
*   - tail:              sg13_hv_pmos current source from the analog rail
*   - input pair:        sg13_hv_pmos, INP=FB (non-inverting), INN=VREF
*   - first-stage load:  sg13_hv_nmos mirror, diode on the VREF-side leg,
*                        first-stage output taken at the FB-side leg
*   - second stage:      single sg13_hv_nmos common-source device
*                        (source VSS, drain OUT), loaded by an
*                        sg13_hv_pmos current source from the rail
*   - compensation:      Miller cap from OUT back to the first-stage
*                        output node; MoM cap (this PDK has NO MIM cap --
*                        cmim/rfcmim need a forbidden layer on CMOS5L)
*   - VREF:              stays an external port; no on-chip bandgap
*
* This is NOT a port of design/ldo_erramp_placeholder.sch (an ideal VCVS
* with no gain stage, bias network, or compensation to have ported) and
* NOT a translation of any sibling repo's amplifier. Only the interface
* conventions carry over from the SG13G2 branch: the INP/INN polarity
* derivation and the "VSS is an explicit pin, never an implicit global
* ground alias" rule, both restated in design/README.md.
*
* Topology (rail = the 3.3 V analog rail; nothing here touches a 1.2 V
* digital rail -- see design/README.md "Rails"):
*
*        VDD ---+----------+-------------------------+
*               |          |                         |
*             [Mb0]      [Mtail] m=3               [Mload2] m=6
*            diode          |                         |
*               |         TAIL                        |
*            IBIAS      +---+---+                     |
*            (pin)      |       |                     |
*                   [Minp]    [Minn]                  |
*                  G=INP      G=INN                   |
*                     |          |                    |
*                    G1         N1                   OUT ---> (pass gate)
*                     |          |                    |
*                   [Mn2]      [Mn1] diode          [Mn3]  G=G1
*                     |          |                    |
*        VSS ---------+----------+--------------------+
*
*        compensation:  OUT --[Cc]-- MZ --[Rz]-- G1
*
* POLARITY (re-derived here from this schematic's own devices, per the
* same discipline design/ldo_core.sch's header used -- not copied):
* FB rises => the FB-side PMOS Minp conducts less and the VREF-side leg
* takes more of the tail current => N1 rises => the mirror Mn2 sinks more
* while Minp supplies less => G1 falls => Mn3 conducts less => Mload2
* pulls OUT up. So FB above VREF drives OUT (EAOUT) up, which shrinks
* Mpass's |Vsg| and brings VOUT back down. Negative feedback, matching
* design/ldo_core.sch's established INP=FB / INN=VREF convention.
*
* ---------------------------------------------------------------------
* JUDGEMENT CALLS THIS FILE MAKES THAT DR-0002 DID NOT MAKE.
* DR-0002 ratified device flavours and structure only; sizing, the bias
* scheme, and the nulling resistor were left to later phases. #21's
* closed-loop PVT sweep (sim/ldo-cmos5l-pvt-sweep/) found the phase-2
* first cut below (Mtail=2/Mload2=4/Cc=30u/Rz l=5.3u) gave ~0.2-0.35deg
* phase margin and 4-5.4dB gain margin at EVERY corner -- essentially no
* stability margin at all, confirmed across a Cc-value and Rz-corner
* sensitivity sweep. #25 re-derives the bias currents and the Cc/Rz
* compensation network below against that evidence; see
* spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md
* for the full re-derivation, the pole/zero reasoning, and the closed-loop
* PVT re-verification. These remain first-cut engineering choices, not
* ratified decisions -- they are what the current PVT record supports,
* not a claim of optimality:
*
* AMENDED BY #35 (DR-0005). #31 crossed cornerRES.lib's resistor corner
* with the full MOS x temperature grid for the first time and found the
* loop missing PM >= 45deg at res_bcs/125C at all five MOS corners
* (43.35-44.48deg), because Rz -- a PDK rhigh -- shrinks to ~0.60x there
* (sheet rho 0.75x x tempco 0.795x) and takes its phase-lead zero up out
* of the crossover region with it (DR-0004). #35's fix is Cc ALONE:
* w 100e-6 -> 170e-6 (~3.2pF -> ~5.5pF), with Rz, both mirror ratios and
* every device size below unchanged. See
* spec/decision-records/DR-0005-sg13cmos5l-cc-recompensation.md for the
* measured Cc pass window, why Rz and the bias mirrors were both tried
* and rejected as levers, and the 45-point PVT re-verification.
*
* 1. BIAS SCHEME: an external IBIAS current-input port, mirrored on-block.
*    Mb0 is a diode-connected sg13_hv_pmos from VDD whose gate/drain node
*    IS the IBIAS pin; Mtail (m=3) and Mload2 (m=6) mirror from it --
*    raised from #20's m=2/m=4 by #25 to speed up the first/second stage's
*    own gm (see item 2) while staying inside the Iq budget (see below).
*    An external sink pulls Iref out of IBIAS; the mirror sets
*    tail = 3*Iref and second-stage = 6*Iref. Chosen over (a) a VBIAS
*    *voltage* port, which would not track the mirror's Vsg over PVT, and
*    (b) an on-block resistor-to-VSS self-bias, whose current is a direct
*    function of the supply and would wreck PSRR in a regulator. An
*    external current input is also the honest interface for a block
*    DR-0002 keeps bandgap-free: the reference is off-block, so the bias
*    should be too, and a testbench can sweep it. IBIAS is a top-level
*    port of ldo_core_cmos5l -- see design/README.md's pinout table.
*
*    NOT CHANGED BY #35, and this is a NEGATIVE RESULT worth stating.
*    DR-0003 found that raising both mirrors together (m=2/m=4 -> m=4/m=8)
*    bought back the 1kHz loop gain -- and therefore the PSRR -- that a
*    large Rz/Cc pair costs, so a further bias increase was the obvious
*    way to widen #35's Cc window upward. It does not survive measurement
*    at the notch size the Iq budget can afford. Over the full 45-point
*    grid (DR-0005): Mload2 m=6 -> m=7 moves worst-corner PSRR@1kHz by
*    +0.01dB (54.20 -> 54.21dB) for +2uA of Iq, i.e. nothing; Mtail
*    m=3 -> m=4 does buy +1.7dB of PSRR@1kHz, but costs 1.4dB of gain
*    margin, 2uA of Iq, and raises the count of grid points with a
*    second 0dB crossing from 15 to 27. Both are rejected: Cc alone
*    reaches the target with more margin on every row and no Iq cost.
*
* 2. NULLING RESISTOR Rz: included, not omitted, and substantially
*    enlarged by #25 (l: 5.3um -> 1200um, w unchanged at the PDK's rhigh
*    minimum, 1um) from the phase-2 textbook Rz~1/gm2 first cut. That
*    first cut alone left the loop with essentially zero phase margin at
*    every corner (see above); DR-0003's re-derivation instead uses Rz
*    (in series with the enlarged Cc below) to place a deliberate
*    left-half-plane phase-lead zero near the loop's unity-gain crossover
*    (empirically ~50-110kHz across the PVT grid at this sizing) -- a
*    standard technique for reclaiming margin, but leading to a much
*    larger resistor than a bare RHP-zero-cancellation estimate. It is an
*    rhigh PDK resistor, not a generic behavioral res.sym, deliberately:
*    cornerRES.lib gives rhigh a real corner spread, so the PVT sweep
*    sees Rz's own variation instead of a resistor that is identical at
*    every corner (checked via the loopgain_rzsens_* sensitivity points,
*    sim/ldo-cmos5l-pvt-sweep/README.md). (Contrast the feedback divider
*    in ldo_core_cmos5l.sch, which is still behavioral -- its ratio, not
*    its absolute PVT spread, is what matters there, and it is a
*    documented deferral inherited from the SG13G2 branch.) Rz's body
*    terminal is tied to VSS rather than the PDK's global sub! node: this
*    cell is a .subckt with an explicit VSS pin and no .global
*    declaration, so sub! would netlist as an undeclared, floating local
*    node. At rhigh's ~1.0-1.4 kOhm/sq corner spread this body implies
*    roughly 1.2-1.7 MOhm.
*
*    MEANDERED IN #28 (phase 4a, the layout phase DR-0003 deferred this
*    to). Through #25 this instance was `l=1200e-6 b=0` -- a single 1.2 mm
*    straight bar at w=1um, a schematic-level-only 1200:1 aspect ratio
*    that is not a drawable device. It is now `l=28.81e-6 b=39`: forty
*    28.81um stripes on the PDK rhigh PCell's own `b` (bends) parameter,
*    which is what that PCell means by a meander (`stripes = b+1` in
*    rhigh_code.py's genSingleResistorLayout).
*
*    THE ELECTRICAL VALUE IS PRESERVED, not merely "close enough" -- this
*    is a geometry change, not a re-sizing, so #21/#25's PVT evidence for
*    the compensation network still describes this device. rhigh's own
*    model (libs.tech/ngspice/models/resistors_mod.lib, `.subckt rhigh`)
*    passes the r3_cmc instance an effective length
*      leff = (b+1)*l + (2/kappa*weff + ps)*b,  weff = w - 0.04u,
*             kappa = 1.85, ps = 0.18u
*    i.e. the bends carry their own resistance. b=0/l=1200u gave
*    leff = 1200.000u; b=39/l=28.81u gives leff = 1199.893u -- 0.009%
*    low, and `l` stays on the PDK's 0.005um grid. Both W (weff) and L
*    (leff) handed to the model are therefore the same to within that
*    0.009%, so it is the same device before and after the meander:
*    R = 1.70016 MOhm (b=0) -> 1.70001 MOhm (b=39) by rhigh.sym's own
*    value expression (weff = w - 0.04u applied once, the number a
*    schematic reader sees). CORRECTION (issue #36): that pair was
*    mislabeled "the simulated device" above in an earlier revision of
*    this header -- it is not. Every rhigh on this branch, Rz included,
*    is subject to the width-offset double-count issue #36 confirmed as
*    a PDK bug (resistors_mod.lib's rhigh subckt narrows weff once, then
*    its r3_cmc .model card's own xw=-0.04 narrows it again; filed
*    upstream as IHP-GmbH/IHP-Open-PDK#1235; see
*    ldo_core_cmos5l.sch's header and
*    spec/decision-records/DR-0006-rhigh-family-width-offset-double-count.md
*    for the full arithmetic and verdict). The device r3_cmc actually
*    simulates is R = 1.77407 MOhm (b=0) -> 1.77392 MOhm (b=39) --
*    the same 0.009% geometry-preservation conclusion holds either way,
*    just at the real simulated value rather than the symbol's.
*
*    A gm-tracking triode-MOS Rz remains an available refinement if a
*    future phase needs a smaller die footprint here.
*
*    NOT CHANGED BY #35, on evidence rather than on cost. Rz is the knob
*    that moved the zero out of place at res_bcs/125C, so enlarging it is
*    the obvious counter-move -- and it works for phase margin, but it
*    also raises the loop's high-frequency gain floor (Rz feeds Cc's
*    current straight through above the zero), so GAIN margin falls at
*    the opposite resistor corner. Measured over the full 45-point grid
*    (DR-0005): Rz leff 1200u -> 1400u costs 1.6dB of worst-corner gain
*    margin (13.87 -> 12.23dB at ff/-40C/res_wcs), 1600u costs 3.1dB
*    (10.73dB), and 1800u breaks the ratified GM >= 10dB row outright
*    (9.34dB at 5 of 45 points). Cc, by contrast, moves the same zero
*    with no gain-margin cost at all (13.83 -> 13.87dB across a 4x Cc
*    range). So Rz stays at l=28.81e-6 b=39 -- which also leaves #28's
*    drawn forty-stripe meander valid, but that is a consequence of the
*    decision, not its reason.
*
* 3. Cc IS A MoM CAP AND ITS VALUE IS insufficient-evidence. cap_cmomi at
*    w=170u l=30u (#35 widened from #25's w=100u l=30u, which had widened
*    #20's w=l=30u) is ~5.5 pF by the PDK's own display helper
*    (libs.tech/xschem/sg13cmos5l_pr/cap_cmomi.tcl, which reproduces
*    cap_cmomi.va's low-frequency C, scaled from the 30u-square ~0.95 pF
*    figure by area). MoM caps are NOT validated on CMOS5L silicon and
*    cornerCAP.lib maps every corner/mismatch/stat section to the same
*    nominal model, so selecting a cap corner is a no-op and a PVT sweep
*    over it measures nothing -- the Cc-VALUE sensitivity sweep is what
*    this repo runs instead (sim/ldo-cmos5l-pvt-sweep/README.md). Per
*    DR-0002's "Flagged, not resolved" section, the exact numbers are
*    still insufficient-evidence pending real CMOS5L MoM-cap silicon
*    characterization.
*
*    WHY 170u SPECIFICALLY (#35 / DR-0005). Cc is bounded on BOTH sides
*    by ratified spec rows, and the bounds were measured over the whole
*    45-point grid rather than argued:
*      - below w~110e-6 the phase-lead zero is too high at res_bcs/125C
*        and PM >= 45deg fails (44.99deg at w=109e-6, ss/125C/res_bcs);
*      - above w~259e-6 the dominant pole is low enough that loop gain at
*        1 kHz -- which is what sets PSRR there -- drops under the
*        PSRR@1kHz > 50dB row (49.99dB at w=260e-6, ss/125C/res_bcs).
*    170e-6 is the GEOMETRIC centre of that [110e-6, 259e-6] window, so
*    the verdict tolerates the largest symmetric multiplicative error in
*    the uncharacterized MoM-cap value in either direction: x0.65 to
*    x1.52 of nominal, with every spec row still met at all 45 points.
*    That centring is the point -- with cornerCAP.lib offering no corner
*    spread to sweep, tolerance to a wrong cap VALUE is the only
*    robustness this caveat can actually be given.
*
* 4. SIZING generally is a DC-sanity first cut for connectivity/ERC and a
*    plausible operating point for every device NOT called out above --
*    Mb0/Minp/Minn/Mn1/Mn2/Mn3 keep #20's original widths; the
*    Mtail/Mload2 mirror ratios and Rz keep #25's values, and only Cc
*    changed in #35. L >= 1 um on every device here (the process spec rates HV
*    VGS <= 3.3 V only at LG >= 0.5 um, and longer channels buy matching
*    and output resistance a micro-power amp needs). ng=1 throughout:
*    fingering is a layout concern for phase 4 (#22), not a
*    schematic-capture one.
*
* Operating point implied by the sizes below, at Iref = 2 uA: tail 6 uA
* (3 uA per input device), second stage 12 uA, mirror reference 2 uA =>
* 20 uA in this cell, plus the feedback divider in ldo_core_cmos5l --
* which since #28 is a real rhigh pair and therefore corner-dependent,
* 1.97-4.82 uA across the grid rather than a flat 2 uA. Measured no-load
* Iq is 21.72-24.72 uA across the full 45-point PVT x resistor grid,
* comfortably inside the porting plan's 16-26 uA allocation and the
* ratified <30uA Iq target (design/README.md's spec table). #35's Cc
* change does not move any of these numbers by construction: Cc carries
* no DC current, so every DC-sweep metric is bit-identical to the #31
* record (sim/ldo-cmos5l-pvt-sweep/README.md, "Results (issue #35)").
* That Iq headroom is also what bounds the bias lever in item 1 above.
*
* NO ENABLE, NO CURRENT LIMIT, NO SOFT START, NO START-UP CIRCUIT. Same
* scope boundary the SG13G2 branch drew; phases 3/4 and later increments
* own those. DR-0001's carried-forward |Vsg| <= 3.3 V constraint binds
* whatever current-limit loop this branch eventually grows, not this cell.
}
G {}
K {}
V {}
S {}
E {}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 200 200 0 0 {name=Mb0 model=sg13_hv_pmos w=5u l=2u ng=1 m=1}
N 220 170 220 110 {}
C {lab_pin.sym} 220 110 0 0 {name=l1 lab=VDD}
N 220 230 220 290 {}
C {lab_pin.sym} 220 290 0 0 {name=l2 lab=IBIAS}
N 180 200 140 200 {}
C {lab_pin.sym} 140 200 0 0 {name=l3 lab=IBIAS}
N 220 200 270 200 {}
C {lab_pin.sym} 270 200 0 0 {name=l4 lab=VDD}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 500 200 0 0 {name=Mtail model=sg13_hv_pmos w=5u l=2u ng=1 m=3}
N 520 170 520 110 {}
C {lab_pin.sym} 520 110 0 0 {name=l5 lab=VDD}
N 520 230 520 290 {}
C {lab_pin.sym} 520 290 0 0 {name=l6 lab=TAIL}
N 480 200 440 200 {}
C {lab_pin.sym} 440 200 0 0 {name=l7 lab=IBIAS}
N 520 200 570 200 {}
C {lab_pin.sym} 570 200 0 0 {name=l8 lab=VDD}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1400 200 0 0 {name=Mload2 model=sg13_hv_pmos w=5u l=2u ng=1 m=6}
N 1420 170 1420 110 {}
C {lab_pin.sym} 1420 110 0 0 {name=l9 lab=VDD}
N 1420 230 1420 290 {}
C {lab_pin.sym} 1420 290 0 0 {name=l10 lab=OUT}
N 1380 200 1340 200 {}
C {lab_pin.sym} 1340 200 0 0 {name=l11 lab=IBIAS}
N 1420 200 1470 200 {}
C {lab_pin.sym} 1470 200 0 0 {name=l12 lab=VDD}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 800 600 0 0 {name=Minp model=sg13_hv_pmos w=20u l=1u ng=1 m=1}
N 820 570 820 510 {}
C {lab_pin.sym} 820 510 0 0 {name=l13 lab=TAIL}
N 820 630 820 690 {}
C {lab_pin.sym} 820 690 0 0 {name=l14 lab=G1}
N 780 600 740 600 {}
C {lab_pin.sym} 740 600 0 0 {name=l15 lab=INP}
N 820 600 870 600 {}
C {lab_pin.sym} 870 600 0 0 {name=l16 lab=TAIL}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1100 600 0 0 {name=Minn model=sg13_hv_pmos w=20u l=1u ng=1 m=1}
N 1120 570 1120 510 {}
C {lab_pin.sym} 1120 510 0 0 {name=l17 lab=TAIL}
N 1120 630 1120 690 {}
C {lab_pin.sym} 1120 690 0 0 {name=l18 lab=N1}
N 1080 600 1040 600 {}
C {lab_pin.sym} 1040 600 0 0 {name=l19 lab=INN}
N 1120 600 1170 600 {}
C {lab_pin.sym} 1170 600 0 0 {name=l20 lab=TAIL}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 800 1000 0 0 {name=Mn2 model=sg13_hv_nmos w=5u l=1u ng=1 m=1}
N 820 970 820 910 {}
C {lab_pin.sym} 820 910 0 0 {name=l21 lab=G1}
N 820 1030 820 1090 {}
C {lab_pin.sym} 820 1090 0 0 {name=l22 lab=VSS}
N 780 1000 740 1000 {}
C {lab_pin.sym} 740 1000 0 0 {name=l23 lab=N1}
N 820 1000 870 1000 {}
C {lab_pin.sym} 870 1000 0 0 {name=l24 lab=VSS}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1100 1000 0 0 {name=Mn1 model=sg13_hv_nmos w=5u l=1u ng=1 m=1}
N 1120 970 1120 910 {}
C {lab_pin.sym} 1120 910 0 0 {name=l25 lab=N1}
N 1120 1030 1120 1090 {}
C {lab_pin.sym} 1120 1090 0 0 {name=l26 lab=VSS}
N 1080 1000 1040 1000 {}
C {lab_pin.sym} 1040 1000 0 0 {name=l27 lab=N1}
N 1120 1000 1170 1000 {}
C {lab_pin.sym} 1170 1000 0 0 {name=l28 lab=VSS}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1400 1000 0 0 {name=Mn3 model=sg13_hv_nmos w=20u l=1u ng=1 m=1}
N 1420 970 1420 910 {}
C {lab_pin.sym} 1420 910 0 0 {name=l29 lab=OUT}
N 1420 1030 1420 1090 {}
C {lab_pin.sym} 1420 1090 0 0 {name=l30 lab=VSS}
N 1380 1000 1340 1000 {}
C {lab_pin.sym} 1340 1000 0 0 {name=l31 lab=G1}
N 1420 1000 1470 1000 {}
C {lab_pin.sym} 1470 1000 0 0 {name=l32 lab=VSS}
C {sg13cmos5l_pr/cap_cmomi.sym} 1700 600 0 0 {name=Cc model=cap_cmomi w=170e-6 l=30e-6 mmin=1 mmax=4 feed=double subblock=0 m=1 mm_ok=1}
N 1700 570 1700 510 {}
C {lab_pin.sym} 1700 510 0 0 {name=l33 lab=OUT}
N 1700 630 1700 690 {}
C {lab_pin.sym} 1700 690 0 0 {name=l34 lab=MZ}
C {sg13cmos5l_pr/rhigh.sym} 1700 1000 0 0 {name=Rz model=rhigh body=VSS w=1e-6 l=28.81e-6 b=39 m=1}
N 1700 970 1700 910 {}
C {lab_pin.sym} 1700 910 0 0 {name=l35 lab=MZ}
N 1700 1030 1700 1090 {}
C {lab_pin.sym} 1700 1090 0 0 {name=l36 lab=G1}
C {ipin.sym} -400 100 0 0 {name=p1 lab=INP}
C {ipin.sym} -400 200 0 0 {name=p2 lab=INN}
C {opin.sym} -400 300 0 0 {name=p3 lab=OUT}
C {iopin.sym} -400 400 0 0 {name=p4 lab=VDD}
C {iopin.sym} -400 500 0 0 {name=p5 lab=VSS}
C {iopin.sym} -400 600 0 0 {name=p6 lab=IBIAS}
