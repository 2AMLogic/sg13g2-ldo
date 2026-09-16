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
*             [Mb0]      [Mtail] m=2               [Mload2] m=4
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
* DR-0002 ratified device flavours and structure only; it explicitly left
* sizing, the bias scheme, and the nulling resistor to this phase. These
* are first-cut engineering choices, NOT ratified decisions, and none of
* them is backed by a testbench yet (phase 3, #21, owns that):
*
* 1. BIAS SCHEME: an external IBIAS current-input port, mirrored on-block.
*    Mb0 is a diode-connected sg13_hv_pmos from VDD whose gate/drain node
*    IS the IBIAS pin; Mtail (m=2) and Mload2 (m=4) mirror from it. An
*    external sink pulls Iref out of IBIAS; the mirror sets tail = 2*Iref
*    and second-stage = 4*Iref. Chosen over (a) a VBIAS *voltage* port,
*    which would not track the mirror's Vsg over PVT, and (b) an on-block
*    resistor-to-VSS self-bias, whose current is a direct function of the
*    supply and would wreck PSRR in a regulator. An external current input
*    is also the honest interface for a block DR-0002 keeps bandgap-free:
*    the reference is off-block, so the bias should be too, and a
*    testbench can sweep it. IBIAS is a new top-level port of
*    ldo_core_cmos5l -- see design/README.md's pinout table.
*
* 2. NULLING RESISTOR Rz: included, not omitted. The RHP zero of a Miller
*    stage sits at gm2/Cc; at the ~8 uA second-stage bias this Iq budget
*    allows (spec/porting-plan.md's 16-26 uA total-block allocation), gm2
*    is order 1e-4 S, so the RHP zero lands close enough to the intended
*    unity-gain frequency that ignoring it is not defensible. Rz is sized
*    for the textbook Rz ~ 1/gm2 first cut. It is an rhigh PDK resistor,
*    not a generic behavioral res.sym, deliberately: cornerRES.lib gives
*    rhigh a real corner spread, so phase 3's PVT sweep sees Rz's own
*    variation instead of a resistor that is identical at every corner.
*    (Contrast the feedback divider in ldo_core_cmos5l.sch, which is still
*    behavioral -- its ratio, not its absolute PVT spread, is what matters
*    there, and it is a documented deferral inherited from the SG13G2
*    branch.) Rz's body terminal is tied to VSS rather than the PDK's
*    global sub! node: this cell is a .subckt with an explicit VSS pin and
*    no .global declaration, so sub! would netlist as an undeclared,
*    floating local node.
*    A gm-tracking triode-MOS Rz is the obvious refinement if phase 3
*    shows the fixed-resistor spread costs too much phase margin.
*
* 3. Cc IS A MoM CAP AND ITS VALUE IS insufficient-evidence. cap_cmomi at
*    w=l=30 um over M1-M4 is ~0.95 pF by the PDK's own display helper
*    (libs.tech/xschem/sg13cmos5l_pr/cap_cmomi.tcl, which reproduces
*    cap_cmomi.va's low-frequency C). MoM caps are NOT validated on CMOS5L
*    silicon and cornerCAP.lib maps every corner/mismatch/stat section to
*    the same nominal model, so selecting a cap corner is a no-op and a
*    PVT sweep over it measures nothing. Per DR-0002's "Flagged, not
*    resolved" section, every result that depends on this value is
*    insufficient-evidence until #21's sensitivity sweep bounds it.
*
* 4. SIZING generally is a DC-sanity first cut for connectivity/ERC and a
*    plausible operating point, exactly as design/ldo_core.sch's w=300u
*    Mpass is on the SG13G2 branch. L >= 1 um on every device here (the
*    process spec rates HV VGS <= 3.3 V only at LG >= 0.5 um, and longer
*    channels buy matching and output resistance that a 16-26 uA amp
*    needs). ng=1 throughout: fingering is a layout concern for phase 4
*    (#22), not a schematic-capture one.
*
* First-cut operating point implied by the sizes below, at Iref = 2 uA:
* tail 4 uA (2 uA per input device), second stage 8 uA, mirror reference
* 2 uA => 14 uA in this cell, plus the 2 uA feedback divider in
* ldo_core_cmos5l = 16 uA. That is at the bottom of the porting plan's
* 16-26 uA allocation, with no simulation behind it.
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
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 500 200 0 0 {name=Mtail model=sg13_hv_pmos w=5u l=2u ng=1 m=2}
N 520 170 520 110 {}
C {lab_pin.sym} 520 110 0 0 {name=l5 lab=VDD}
N 520 230 520 290 {}
C {lab_pin.sym} 520 290 0 0 {name=l6 lab=TAIL}
N 480 200 440 200 {}
C {lab_pin.sym} 440 200 0 0 {name=l7 lab=IBIAS}
N 520 200 570 200 {}
C {lab_pin.sym} 570 200 0 0 {name=l8 lab=VDD}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1400 200 0 0 {name=Mload2 model=sg13_hv_pmos w=5u l=2u ng=1 m=4}
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
C {sg13cmos5l_pr/cap_cmomi.sym} 1700 600 0 0 {name=Cc model=cap_cmomi w=30e-6 l=30e-6 mmin=1 mmax=4 feed=double subblock=0 m=1 mm_ok=1}
N 1700 570 1700 510 {}
C {lab_pin.sym} 1700 510 0 0 {name=l33 lab=OUT}
N 1700 630 1700 690 {}
C {lab_pin.sym} 1700 690 0 0 {name=l34 lab=MZ}
C {sg13cmos5l_pr/rhigh.sym} 1700 1000 0 0 {name=Rz model=rhigh body=VSS w=1e-6 l=5.3e-6 b=0 m=1}
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
