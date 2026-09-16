v {xschem version=3.4.7 file_version=1.3
* ldo_core_cmos5l -- SG13CMOS5L LDO core (issue #20, phase 2/4 of the
* SG13CMOS5L port tracked by #12, Epic 2AMLogic/2am#542 Phase 5A).
*
* Captured against the ihp-sg13cmos5l PDK. Every device instance below is
* an sg13cmos5l_pr/ symbol resolved out of
* $PDK_ROOT/ihp-sg13cmos5l/libs.tech/xschem, or this branch's own
* ldo_erramp_cmos5l cell. Nothing here references sg13g2_pr/, and -- as of
* issue #28's divider conversion below -- nothing here is a generic
* behavioral xschem device (devices/res.sym) either: every device in this
* cell is a real PDK instance.
*
* RATIFYING RECORD:
* spec/decision-records/DR-0002-sg13cmos5l-device-topology.md (PR #23,
* closing issue #19 -- phase 1/4). That record ratifies BOTH of this
* schematic's device-level choices:
*   Decision (a): Mpass is sg13_hv_pmos, common-source, source at the
*     3.3 V analog input rail, drain at VOUT, body at source.
*   Decision (b): the error amplifier is a CMOS-input, two-stage,
*     Miller-compensated, single-ended-output OTA built entirely from HV
*     devices, with VREF remaining an external port (no on-chip bandgap).
*     It is implemented here by Xamp = ldo_erramp_cmos5l, replacing the
*     SG13G2 branch's ideal-VCVS placeholder; see that cell's own header
*     for its internals and for the judgement calls DR-0002 left open.
*
* PROVENANCE. This is not a copy or mechanical translation of this repo's
* own SG13G2 sources (design/ldo_core.sch, design/ldo_erramp_placeholder
* .sch), of gf180-ldo's, or of sky130-ldo's -- the same clean-room
* discipline design/README.md's "Clean-room provenance" section records
* for the SG13G2 schematic, applied here relative to the SG13G2 files in
* THIS repo. What is deliberately carried across is interface convention,
* not circuit content: the VIN/VOUT/VSS/VREF port names and order, the
* two-resistor feedback-divider approach, the FB/EAOUT node names, and the
* INP=FB / INN=VREF polarity convention. The polarity itself is re-derived
* below from Mpass's own device physics on this schematic.
*
* RAILS (Challenge #6 brief: 1.2 V digital / 3.3 V analog). This block
* touches the 3.3 V ANALOG rail only. VIN is that rail; Xamp's VDD is tied
* to VIN; every device in the hierarchy is an HV (3.3 V-class) flavour.
* There is no 1.2 V node anywhere in this cell, and no digital control
* input or test output is claimed against the brief's slot budget -- this
* block presents VIN/VOUT/VSS plus two analog lines (VREF, IBIAS).
*
* Topology -- three blocks, one loop:
*
*   VIN --S  sg13_hv_pmos (Mpass)  D-- VOUT --+-- Rtop --+
*             G                                |         |
*             |                               FB        (to Xamp INP)
*             |                                |
*        EAOUT (Xamp OUT)                     Rbot
*             |                                |
*             +---- Xamp (ldo_erramp_cmos5l) --+-- VSS
*                     INP=FB  INN=VREF  VDD=VIN  VSS=VSS  IBIAS=IBIAS
*
* PASS DEVICE. sg13_hv_pmos, common-source: source at VIN, drain at VOUT,
* body tied to VIN (the source) -- the standard PMOS
* body-to-highest-potential practice for a device whose source rides at
* the supply rail. Gate driven directly by the error amplifier output
* (EAOUT); no gate buffer in this increment.
*
* SIZING -- RESIZED (issue #25) FROM THE ORIGINAL DC-SANITY FIRST CUT.
* w=2800u l=0.5u ng=1 m=1 replaces the phase-2 provisional w=300u after
* #21's closed-loop PVT sweep (sim/ldo-cmos5l-pvt-sweep/) found w=300u
* missed the dropout target by 4-7x and never reached regulation at all at
* 4/15 corners. l=0.5u is unchanged and still not arbitrary: the process
* spec rates HV VGS <= 3.3 V only at LG >= 0.5 um
* (SG13CMOS5L_os_process_spec.pdf Rev. 0.2 Sec 2.1.5, quoted in DR-0002's
* ratings table). w=2800u is derived from, and sits ~20-30% above,
* sim/pass-device-screening's own bare-device implied-width data (worst
* corner ~2169-2350um for 300mV/50mA, `w1u_l0.5u`/`w300u_l0.5u` rows of
* sim/pass-device-screening/records/20260909-220347-ed18110.csv) -- the
* margin above that bare-device estimate is deliberate headroom against
* this closed-loop bench's discretized 10mV dropout-scan step and against
* the amplifier's own re-derived compensation (see
* ldo_erramp_cmos5l.sch's header) rather than a fresh independent
* derivation. Full before/after PVT evidence, corner table, and the
* decision record for this resize: spec/decision-records/DR-0003-sg13cmos5l-mpass-resize-and-compensation.md,
* sim/ldo-cmos5l-pvt-sweep/README.md.
*
* FEEDBACK DIVIDER. Rtop (VOUT->FB) and Rbot (FB->VSS), a two-resistor
* divider giving FB = VOUT/2; against an illustrative VREF = 0.9 V that
* servos VOUT to 1.8 V. Both the ratio and the assumed VREF are
* provisional first-cut values, exactly as on the SG13G2 branch -- no
* target spec has been ratified for either branch.
*
* CONVERTED TO A PDK rhigh (issue #28, phase 4a). Through #25 both legs
* were a generic devices/res.sym behavioral 300k -- a SPICE `R` primitive
* that `klt extract` cannot see as a device at all, which design/README.md
* "Known gaps on this branch" flagged as blocking the layout phase and
* assigned to it. They are now the same PDK flavour Rz already uses,
* sg13cmos5l_pr/rhigh.sym, so the drawn divider is LVS-visible:
*
*   w = 1e-6 (rhigh_minW is 0.50u; 1u is Rz's own width, kept identical so
*             the three rhigh bodies in this hierarchy share one drawn
*             width and one corner behaviour)
*   l = 25.43e-6, b = 7  (eight 25.43u stripes, i.e. a meander, not a bar)
*
* rhigh, not rsil/rppd: at the PDK's own typical sheet rho (cornerRES.lib
* `res_typ`: rsil 7.0, rppd 260.0, rhigh 1360.0 ohm/sq) a 300k leg is
* ~221 squares of rhigh, ~1150 squares of rppd and ~43000 squares of rsil.
* Only rhigh puts a 300k leg in a layout-reasonable area.
*
* VALUE, re-derived per this issue's own instruction. rhigh.sym's own
* value expression (the PDK symbol's, not this repo's) is
*   R = ( rzspec/w + rspec*leff/weff ) / m,
*   leff = (b+1)*l + (2/kappa*weff + ps)*b,  weff = w - 0.04u,
*   rzspec = 1.6e-4 ohm*m, rspec = 1360 ohm/sq, kappa = 1.85, ps = 0.18u
* -> leff = 211.964u, R = 300.44 kOhm per leg. That is +0.15% on the 300k
* behavioral value it replaces, and -- because both legs are the same
* drawn device -- the divider RATIO is exactly 1/2 independent of sheet
* rho, which is the only property this divider is relied on for. Total
* 600.9k; the divider's own standing current at VOUT = 1.8 V is 3.0 uA.
* (The pre-#28 header claimed "900k total ... 2 uA" for two 300k legs --
* arithmetically wrong on its own numbers, 300k + 300k = 600k -> 3.0 uA;
* corrected here rather than carried forward.)
*
* WHAT THIS CHANGES ELECTRICALLY, stated rather than implied: the divider
* now carries rhigh's real PVT corner spread (cornerRES.lib gives rhigh
* ~1.0-1.4 kOhm/sq) instead of a corner-independent behavioral 300k. The
* ratio is unaffected (both legs track), but the divider's absolute
* impedance -- and hence the FB node's own pole against whatever loads it
* -- now moves with the resistor corner. #21/#25's closed-loop PVT
* evidence (sim/ldo-cmos5l-pvt-sweep/) was taken BEFORE this conversion
* and therefore does not cover that spread; re-running the sweep with the
* PDK divider in place -- across the RESISTOR corner (cornerRES.lib's
* res_typ/res_bcs/res_wcs), which is a separate axis from the MOS corner --
* is tracked as issue #31, not silently assumed harmless here.
*
* Note the (now former) asymmetry with ldo_erramp_cmos5l's nulling
* resistor, which was already a PDK rhigh -- that cell's header explains
* why it went first (Rz's corner spread is load-bearing for phase margin;
* the divider's absolute value is not, which is why the divider's
* conversion waited for the phase that actually needs it).
*
* ERROR AMPLIFIER POLARITY. INP=FB is the non-inverting input, INN=VREF
* the inverting input -- the polarity a PMOS common-source pass device's
* negative-feedback loop requires: as EAOUT (Mpass's gate) rises, Mpass's
* |Vsg| shrinks and VOUT falls, so when FB rises above VREF, EAOUT must
* rise to correct VOUT back down. Re-derived here from Mpass's own
* polarity on this schematic; ldo_erramp_cmos5l.sch's header carries the
* matching derivation through the amplifier's internal nodes.
*
* IBIAS IS A NEW TOP-LEVEL PORT, not present on the SG13G2 branch's
* ldo_core. DR-0002's Consequences section anticipated exactly this ("a
* two-stage OTA on the 3.3 V rail needs at minimum VDD and a bias input or
* an on-block bias device. #20 owns that interface change"). The choice of
* an external current input over a voltage bias or an on-block self-bias
* is this phase's judgement call and is argued in ldo_erramp_cmos5l.sch's
* header. Port order is VIN VOUT VSS VREF IBIAS -- the SG13G2 list with
* IBIAS appended, so the shared four keep their positions.
*
* NO EN, NO CURRENT LIMIT, NO SOFT START, NO OUTPUT CAP, NO LOAD. Same
* scope boundary as the SG13G2 branch; nothing in this increment is
* simulated. xschem's own ERC (design/netlist.py --design sg13cmos5l
* --check) is the only verification performed here. PVT verification is
* phase 3 (#21); layout/DRC/LVS is phase 4 (#22).
*
* MoM-CAP CAVEAT INHERITED FROM THE AMPLIFIER: the compensation cap inside
* Xamp is a MoM cap (this PDK forbids MIM), and MoM caps are not validated
* on CMOS5L silicon. Any loop-stability claim about this core is therefore
* insufficient-evidence until #21's sensitivity sweep bounds it.
}
G {}
K {}
V {}
S {}
E {}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 400 200 0 0 {name=Mpass model=sg13_hv_pmos w=2800u l=0.5u ng=1 m=1}
N 420 170 420 110 {}
C {lab_pin.sym} 420 110 0 0 {name=l1 lab=VIN}
N 420 230 420 290 {}
C {lab_pin.sym} 420 290 0 0 {name=l2 lab=VOUT}
N 380 200 320 200 {}
C {lab_pin.sym} 320 200 0 0 {name=l3 lab=EAOUT}
N 420 200 490 200 {}
C {lab_pin.sym} 490 200 0 0 {name=l4 lab=VIN}
C {sg13cmos5l_pr/rhigh.sym} 900 300 0 0 {name=Rtop model=rhigh body=VSS w=1e-6 l=25.43e-6 b=7 m=1}
N 900 270 900 210 {}
C {lab_pin.sym} 900 210 0 0 {name=l5 lab=VOUT}
N 900 330 900 390 {}
C {lab_pin.sym} 900 390 0 0 {name=l6 lab=FB}
C {sg13cmos5l_pr/rhigh.sym} 900 600 0 0 {name=Rbot model=rhigh body=VSS w=1e-6 l=25.43e-6 b=7 m=1}
N 900 570 900 510 {}
C {lab_pin.sym} 900 510 0 0 {name=l7 lab=FB}
N 900 630 900 690 {}
C {lab_pin.sym} 900 690 0 0 {name=l8 lab=VSS}
C {ldo_erramp_cmos5l.sym} 400 900 0 0 {name=Xamp}
N 320 860 260 860 {}
C {lab_pin.sym} 260 860 0 0 {name=l9 lab=FB}
N 320 940 260 940 {}
C {lab_pin.sym} 260 940 0 0 {name=l10 lab=VREF}
N 480 900 540 900 {}
C {lab_pin.sym} 540 900 0 0 {name=l11 lab=EAOUT}
N 360 820 360 760 {}
C {lab_pin.sym} 360 760 0 0 {name=l12 lab=VIN}
N 440 820 440 760 {}
C {lab_pin.sym} 440 760 0 0 {name=l13 lab=IBIAS}
N 400 980 400 1040 {}
C {lab_pin.sym} 400 1040 0 0 {name=l14 lab=VSS}
C {iopin.sym} -200 100 0 0 {name=p1 lab=VIN}
C {iopin.sym} -200 200 0 0 {name=p2 lab=VOUT}
C {iopin.sym} -200 300 0 0 {name=p3 lab=VSS}
C {ipin.sym} -200 400 0 0 {name=p4 lab=VREF}
C {iopin.sym} -200 500 0 0 {name=p5 lab=IBIAS}
