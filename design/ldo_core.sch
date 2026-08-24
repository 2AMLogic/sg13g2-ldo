v {xschem version=3.4.7 file_version=1.3
* ldo_core -- SG13G2 LDO core, forward-designed against ihp-sg13g2's own
* device menu (issue #6, T1 item 1: design sources). NOT a copy or
* mechanical translation of gf180-ldo's or sky130-ldo's ldo_core.sch --
* independent SG13G2-native device instances, topology, and node names,
* per spec/porting-plan.md Sec 1.3 and this issue's clean-room mandate.
* Read the siblings' decision records for *reasoning*, not their circuit
* files: this schematic was authored without opening either sibling's
* .sch source.
*
* Topology -- three blocks, one loop:
*
*   VIN --S  sg13_hv_pmos (Mpass)  D-- VOUT --+-- Rtop --+
*             G                                |         |
*             |                               FB        (to Xamp INP)
*             |                                |
*        EAOUT (Xamp OUT)                     Rbot
*             |                                |
*             +---- Xamp (ldo_erramp_placeholder) ----+-- VSS
*                     INP=FB  INN=VREF  VSS=VSS
*
* Pass device (spec/porting-plan.md Sec 2.1's starting hypothesis,
* confirmed here on device-menu grounds, not yet on a measured screening
* deck -- see design/README.md "Pass device" for the one-line status and
* the provisional-sizing caveat): sg13_hv_pmos, common-source, source at
* VIN, drain at VOUT, body tied to VIN (source), the standard PMOS
* body-to-highest-potential practice for a device whose source rides at
* the supply rail. Gate driven directly by the error amplifier's output
* (EAOUT) -- no buffer stage in this increment.
*
* Feedback divider: Rtop (VOUT->FB) and Rbot (FB->VSS), a plain
* behavioral two-resistor unit-string divider (porting-plan Sec 1.2's
* "unit-resistor-string divider" output-programmability method -- a
* generic textbook divider construction, not sibling-specific circuit
* content). Sized here as a first-cut 1:1 ratio (Rtop=Rbot=300k) against
* an assumed VREF=0.9V for VOUT=1.8V -- both the ratio and the assumed
* VREF are provisional (design/README.md), and VREF itself is supplied
* externally at simulation time, never generated on this schematic (see
* Xamp below and design/README.md "Reference voltage").
*
* Error amplifier: Xamp, a behavioral placeholder
* (ldo_erramp_placeholder.sch/.sym) -- a full amplifier topology decision
* (bipolar vs. CMOS input stage, on-chip bandgap vs. external VREF) is
* out of scope for this issue (spec/porting-plan.md Sec 2.2, Sec 4 item
* 5). INP=FB is the non-inverting input, INN=VREF the inverting input --
* the polarity a PMOS common-source pass device's negative feedback loop
* requires (as G rises, Mpass's Vsg shrinks, VOUT falls; as FB rises
* above VREF, EAOUT must rise to correct it back down -- universal
* single-PMOS-pass-device control-loop physics, re-derived directly from
* Mpass's own polarity here, not read off any sibling's schematic).
*
* No EN, no current limit, no soft start, no compensation network in this
* increment -- all explicitly out of scope (T1 items 2-7 are layout/
* DRC/LVS/corners; the protection/sequencing/compensation circuitry those
* items' evidence would exercise is its own future increment, the same
* way gf180-ldo decomposed error_amp/ldo_ilimit/ldo_softstart across
* separate issues rather than building one all-in-one schematic).
}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_hv_pmos.sym} 400 200 0 0 {name=Mpass model=sg13_hv_pmos w=300u l=0.5u ng=1 m=1}
N 420 230 460 260 {}
C {lab_pin.sym} 460 260 0 0 {name=l1 lab=VOUT}
N 380 200 340 200 {}
C {lab_pin.sym} 340 200 0 0 {name=l2 lab=EAOUT}
N 420 170 460 150 {}
C {lab_pin.sym} 460 150 0 0 {name=l3 lab=VIN}
N 420 200 460 200 {}
C {lab_pin.sym} 460 200 0 0 {name=l4 lab=VIN}
C {res.sym} 700 150 0 0 {name=Rtop value=300k}
N 700 120 700 90 {}
C {lab_pin.sym} 700 90 0 0 {name=l5 lab=VOUT}
N 700 180 700 210 {}
C {lab_pin.sym} 700 210 0 0 {name=l6 lab=FB}
C {res.sym} 700 300 0 0 {name=Rbot value=300k}
N 700 270 700 240 {}
C {lab_pin.sym} 700 240 0 0 {name=l7 lab=FB}
N 700 330 700 360 {}
C {lab_pin.sym} 700 360 0 0 {name=l8 lab=VSS}
C {ldo_erramp_placeholder.sym} 100 450 0 0 {name=Xamp}
N 60 430 20 430 {}
C {lab_pin.sym} 20 430 0 0 {name=l9 lab=FB}
N 60 470 20 470 {}
C {lab_pin.sym} 20 470 0 0 {name=l10 lab=VREF}
N 140 450 180 450 {}
C {lab_pin.sym} 180 450 0 0 {name=l11 lab=EAOUT}
N 100 490 100 530 {}
C {lab_pin.sym} 100 530 0 0 {name=l12 lab=VSS}
C {iopin.sym} -100 170 0 0 {name=p1 lab=VIN}
C {iopin.sym} 900 120 0 0 {name=p2 lab=VOUT}
C {iopin.sym} 100 600 0 0 {name=p3 lab=VSS}
C {ipin.sym} -100 470 0 0 {name=p4 lab=VREF}
