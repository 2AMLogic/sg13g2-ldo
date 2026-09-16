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
*    node. At rhigh's ~1.0-1.4 kOhm/sq corner spread, l=1200um/w=1um
*    implies roughly 1.2-1.7 MOhm and a schematic-level-only 1200:1
*    aspect ratio -- a layout-phase (#22) concern (meandering via the
*    PDK's own rhigh PCell `b` bends parameter), not a schematic-capture
*    one; DR-0003 records this explicitly as a known follow-up rather
*    than a hidden cost. A gm-tracking triode-MOS Rz remains an available
*    refinement if a future phase needs a smaller die footprint here.
*
* 3. Cc IS A MoM CAP AND ITS VALUE IS insufficient-evidence. cap_cmomi at
*    w=100u l=30u (#25 widened from #20's w=l=30u) is ~3.2 pF by the PDK's
*    own display helper (libs.tech/xschem/sg13cmos5l_pr/cap_cmomi.tcl,
*    which reproduces cap_cmomi.va's low-frequency C, scaled from the
*    30u-square ~0.95 pF figure by area). MoM caps are NOT validated on
*    CMOS5L silicon and cornerCAP.lib maps every corner/mismatch/stat
*    section to the same nominal model, so selecting a cap corner is a
*    no-op and a PVT sweep over it measures nothing -- #25 re-ran the
*    Cc-value sensitivity sweep {0.5x,1x,2x} at this new nominal and found
*    the PASS verdict (phase margin, gain margin) holds across the whole
*    range, not just at 1x (see DR-0003). Per DR-0002's "Flagged, not
*    resolved" section, the exact numbers are still insufficient-evidence
*    pending real CMOS5L MoM-cap silicon characterization; the qualitative
*    PASS verdict does not depend on that caveat (same reasoning #21
*    established for the pre-#25 FAIL verdict).
*
* 4. SIZING generally is a DC-sanity first cut for connectivity/ERC and a
*    plausible operating point for every device NOT called out above --
*    Mb0/Minp/Minn/Mn1/Mn2/Mn3 keep #20's original widths; only the
*    Mtail/Mload2 mirror ratios and the Cc/Rz compensation values changed
*    in #25. L >= 1 um on every device here (the process spec rates HV
*    VGS <= 3.3 V only at LG >= 0.5 um, and longer channels buy matching
*    and output resistance a micro-power amp needs). ng=1 throughout:
*    fingering is a layout concern for phase 4 (#22), not a
*    schematic-capture one.
*
* Operating point implied by the sizes below, at Iref = 2 uA: tail 6 uA
* (3 uA per input device), second stage 12 uA, mirror reference 2 uA =>
* 20 uA in this cell, plus the 2 uA feedback divider in ldo_core_cmos5l =
* 22 uA nominal -- confirmed by #25's closed-loop sweep at ~22.0-22.98 uA
* (no load) and ~23.06-23.08 uA (full load, 50 mA) across the full PVT
* grid, comfortably inside the porting plan's 16-26 uA allocation and the
* ratified <30uA Iq target (design/README.md's spec table) at both load
* points.
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
C {sg13cmos5l_pr/cap_cmomi.sym} 1700 600 0 0 {name=Cc model=cap_cmomi w=100e-6 l=30e-6 mmin=1 mmax=4 feed=double subblock=0 m=1 mm_ok=1}
N 1700 570 1700 510 {}
C {lab_pin.sym} 1700 510 0 0 {name=l33 lab=OUT}
N 1700 630 1700 690 {}
C {lab_pin.sym} 1700 690 0 0 {name=l34 lab=MZ}
C {sg13cmos5l_pr/rhigh.sym} 1700 1000 0 0 {name=Rz model=rhigh body=VSS w=1e-6 l=1200e-6 b=0 m=1}
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
