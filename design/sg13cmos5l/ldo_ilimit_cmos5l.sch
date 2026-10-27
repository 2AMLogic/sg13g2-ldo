v {xschem version=3.4.7 file_version=1.3
* ldo_ilimit_cmos5l -- SG13CMOS5L current limiter (issue #165, child of #164;
* plan: spec/decision-records/DR-0017-sg13cmos5l-current-limiter-plan.md
* sections 1-3, 5-6). Ports: VIN VOUT EAOUT IBIAS EN VSS.
*
* STATUS: row 8 (65-80 mA brickwall over PVT, short-survivable) is NOT
* ratified and nothing here is a measured result. Every dimension below is a
* DR-0017 section 3 CANDIDATE. The DR is accepted for bounded development
* only (operator ruling, issue #165, 2026-10-19). Only the nominal
* tt / 27 C / 3.30 V smoke check recorded under sim/ldo-cmos5l-ilimit/ has
* been run; see design/README.md "Current limiter (ldo_ilimit_cmos5l)".
*
* TOPOLOGY (all HV devices, DR-0002):
*   Msense   25u/0.5u, one more finger of the Mpass array (N = 2800/25 = 112),
*            G = EAOUT, S = B = VIN, D = ISNS. Rsns returns ISNS to VOUT, so
*            the sense current still reaches the load.
*   Rsns     rhigh unit x 20 in parallel (m=20) -- ISNS to VOUT.
*   Mref1/2  two gate-shared, series-stacked copies of the amplifier bias
*            diode geometry (5u/2u), gate on IBIAS: Iref = IBIAS/2. The
*            threshold comes from the external IBIAS, not from VREF/R.
*   Rref1-32 the same rhigh unit x 32 in series -- VTH to VOUT, so
*            V(VTH) = VOUT + Iref*Rref. Rsns and Rref use IDENTICAL unit
*            resistors, so Rref/Rsns = 32*20 = 640 at every global resistor
*            corner and temperature (DR-0017 sections 1-2 and 4a).
*   Mca/Mcb  PMOS comparator pair (ISNS vs VTH) with a resistor tail
*            Rtail from VIN (opened by Men_t), NMOS mirror load Mna/Mnb,
*            dominant-pole cap Ccl on CO.
*   Mg2      NMOS gain stage pulling CLG down against the Mlg load (2 uA,
*            mirrored from IBIAS).
*   Mclamp   40u/0.5u (Men geometry): CLG low pulls EAOUT up toward VIN,
*            which turns Mpass off until Iout = Ilim. A second current loop
*            around Mpass; it does not latch.
*   Enable   local inverter Minvp/Minvn makes ENB. Men_t opens the tail,
*            Men_co parks CO at VSS, Mcoff holds CLG at VIN. Iref and Mlg
*            switch off by themselves because the core Mbdis pulls IBIAS to
*            VIN when EN is low (DR-0017 section 6). No new enable semantics.
*
* THRESHOLD (DR-0017 section 2): Ilim = (N+1)*(IBIAS/2)*(Rref/Rsns)
*   = 113 * 1.000 uA * 640 = 72.32 mA calculated (NOT measured).
*   With IBIAS absent Iref = 0 and the clamp holds Mpass off: the fail-safe
*   direction.
*
* UNIT RESISTOR. rhigh w=2u b=0, l chosen so the SIMULATED value is 5.0 kOhm
* at res_typ / 27 C (ngspice, PDK model; the symbol expression double-counts
* the width offset, DR-0006, so l comes from the simulation, not from the
* expression). Rtail is a single rhigh (w=1u, 14 bends), about 580 kOhm.
*
* OPEN, not settled by this cell: sense Vds offset, Iref stack ratio and
* plateau tilt, limiter-loop stability, clamp authority against the
* amplifier sink, terminal stress. Layout needs Rsns/Rref common-centroid.
}
G {}
K {}
V {}
S {}
E {}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 200 300 0 0 {name=Msense model=sg13_hv_pmos w=25u l=0.5u ng=1 m=1}
N 220 270 220 210 {}
C {lab_pin.sym} 220 210 0 0 {name=l1 lab=VIN}
N 220 330 220 390 {}
C {lab_pin.sym} 220 390 0 0 {name=l2 lab=ISNS}
N 180 300 140 300 {}
C {lab_pin.sym} 140 300 0 0 {name=l3 lab=EAOUT}
N 220 300 270 300 {}
C {lab_pin.sym} 270 300 0 0 {name=l4 lab=VIN}
C {sg13cmos5l_pr/rhigh.sym} 500 300 0 0 {name=Rsns model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=20}
N 500 270 500 210 {}
C {lab_pin.sym} 500 210 0 0 {name=l5 lab=ISNS}
N 500 330 500 390 {}
C {lab_pin.sym} 500 390 0 0 {name=l6 lab=VOUT}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 800 300 0 0 {name=Mref1 model=sg13_hv_pmos w=5u l=2u ng=1 m=1}
N 820 270 820 210 {}
C {lab_pin.sym} 820 210 0 0 {name=l7 lab=VIN}
N 820 330 820 390 {}
C {lab_pin.sym} 820 390 0 0 {name=l8 lab=REFM}
N 780 300 740 300 {}
C {lab_pin.sym} 740 300 0 0 {name=l9 lab=IBIAS}
N 820 300 870 300 {}
C {lab_pin.sym} 870 300 0 0 {name=l10 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1100 300 0 0 {name=Mref2 model=sg13_hv_pmos w=5u l=2u ng=1 m=1}
N 1120 270 1120 210 {}
C {lab_pin.sym} 1120 210 0 0 {name=l11 lab=REFM}
N 1120 330 1120 390 {}
C {lab_pin.sym} 1120 390 0 0 {name=l12 lab=VTH}
N 1080 300 1040 300 {}
C {lab_pin.sym} 1040 300 0 0 {name=l13 lab=IBIAS}
N 1120 300 1170 300 {}
C {lab_pin.sym} 1170 300 0 0 {name=l14 lab=VIN}
C {sg13cmos5l_pr/rhigh.sym} 1500 300 0 0 {name=Rref1 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1500 270 1500 210 {}
C {lab_pin.sym} 1500 210 0 0 {name=l15 lab=VTH}
N 1500 330 1500 390 {}
C {lab_pin.sym} 1500 390 0 0 {name=l16 lab=RN1}
C {sg13cmos5l_pr/rhigh.sym} 1620 300 0 0 {name=Rref2 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1620 270 1620 210 {}
C {lab_pin.sym} 1620 210 0 0 {name=l17 lab=RN1}
N 1620 330 1620 390 {}
C {lab_pin.sym} 1620 390 0 0 {name=l18 lab=RN2}
C {sg13cmos5l_pr/rhigh.sym} 1740 300 0 0 {name=Rref3 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1740 270 1740 210 {}
C {lab_pin.sym} 1740 210 0 0 {name=l19 lab=RN2}
N 1740 330 1740 390 {}
C {lab_pin.sym} 1740 390 0 0 {name=l20 lab=RN3}
C {sg13cmos5l_pr/rhigh.sym} 1860 300 0 0 {name=Rref4 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1860 270 1860 210 {}
C {lab_pin.sym} 1860 210 0 0 {name=l21 lab=RN3}
N 1860 330 1860 390 {}
C {lab_pin.sym} 1860 390 0 0 {name=l22 lab=RN4}
C {sg13cmos5l_pr/rhigh.sym} 1980 300 0 0 {name=Rref5 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1980 270 1980 210 {}
C {lab_pin.sym} 1980 210 0 0 {name=l23 lab=RN4}
N 1980 330 1980 390 {}
C {lab_pin.sym} 1980 390 0 0 {name=l24 lab=RN5}
C {sg13cmos5l_pr/rhigh.sym} 2100 300 0 0 {name=Rref6 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2100 270 2100 210 {}
C {lab_pin.sym} 2100 210 0 0 {name=l25 lab=RN5}
N 2100 330 2100 390 {}
C {lab_pin.sym} 2100 390 0 0 {name=l26 lab=RN6}
C {sg13cmos5l_pr/rhigh.sym} 2220 300 0 0 {name=Rref7 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2220 270 2220 210 {}
C {lab_pin.sym} 2220 210 0 0 {name=l27 lab=RN6}
N 2220 330 2220 390 {}
C {lab_pin.sym} 2220 390 0 0 {name=l28 lab=RN7}
C {sg13cmos5l_pr/rhigh.sym} 2340 300 0 0 {name=Rref8 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2340 270 2340 210 {}
C {lab_pin.sym} 2340 210 0 0 {name=l29 lab=RN7}
N 2340 330 2340 390 {}
C {lab_pin.sym} 2340 390 0 0 {name=l30 lab=RN8}
C {sg13cmos5l_pr/rhigh.sym} 2460 300 0 0 {name=Rref9 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2460 270 2460 210 {}
C {lab_pin.sym} 2460 210 0 0 {name=l31 lab=RN8}
N 2460 330 2460 390 {}
C {lab_pin.sym} 2460 390 0 0 {name=l32 lab=RN9}
C {sg13cmos5l_pr/rhigh.sym} 2580 300 0 0 {name=Rref10 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2580 270 2580 210 {}
C {lab_pin.sym} 2580 210 0 0 {name=l33 lab=RN9}
N 2580 330 2580 390 {}
C {lab_pin.sym} 2580 390 0 0 {name=l34 lab=RN10}
C {sg13cmos5l_pr/rhigh.sym} 2700 300 0 0 {name=Rref11 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2700 270 2700 210 {}
C {lab_pin.sym} 2700 210 0 0 {name=l35 lab=RN10}
N 2700 330 2700 390 {}
C {lab_pin.sym} 2700 390 0 0 {name=l36 lab=RN11}
C {sg13cmos5l_pr/rhigh.sym} 2820 300 0 0 {name=Rref12 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2820 270 2820 210 {}
C {lab_pin.sym} 2820 210 0 0 {name=l37 lab=RN11}
N 2820 330 2820 390 {}
C {lab_pin.sym} 2820 390 0 0 {name=l38 lab=RN12}
C {sg13cmos5l_pr/rhigh.sym} 2940 300 0 0 {name=Rref13 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2940 270 2940 210 {}
C {lab_pin.sym} 2940 210 0 0 {name=l39 lab=RN12}
N 2940 330 2940 390 {}
C {lab_pin.sym} 2940 390 0 0 {name=l40 lab=RN13}
C {sg13cmos5l_pr/rhigh.sym} 3060 300 0 0 {name=Rref14 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 3060 270 3060 210 {}
C {lab_pin.sym} 3060 210 0 0 {name=l41 lab=RN13}
N 3060 330 3060 390 {}
C {lab_pin.sym} 3060 390 0 0 {name=l42 lab=RN14}
C {sg13cmos5l_pr/rhigh.sym} 3180 300 0 0 {name=Rref15 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 3180 270 3180 210 {}
C {lab_pin.sym} 3180 210 0 0 {name=l43 lab=RN14}
N 3180 330 3180 390 {}
C {lab_pin.sym} 3180 390 0 0 {name=l44 lab=RN15}
C {sg13cmos5l_pr/rhigh.sym} 3300 300 0 0 {name=Rref16 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 3300 270 3300 210 {}
C {lab_pin.sym} 3300 210 0 0 {name=l45 lab=RN15}
N 3300 330 3300 390 {}
C {lab_pin.sym} 3300 390 0 0 {name=l46 lab=RN16}
C {sg13cmos5l_pr/rhigh.sym} 1500 600 0 0 {name=Rref17 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1500 570 1500 510 {}
C {lab_pin.sym} 1500 510 0 0 {name=l47 lab=RN16}
N 1500 630 1500 690 {}
C {lab_pin.sym} 1500 690 0 0 {name=l48 lab=RN17}
C {sg13cmos5l_pr/rhigh.sym} 1620 600 0 0 {name=Rref18 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1620 570 1620 510 {}
C {lab_pin.sym} 1620 510 0 0 {name=l49 lab=RN17}
N 1620 630 1620 690 {}
C {lab_pin.sym} 1620 690 0 0 {name=l50 lab=RN18}
C {sg13cmos5l_pr/rhigh.sym} 1740 600 0 0 {name=Rref19 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1740 570 1740 510 {}
C {lab_pin.sym} 1740 510 0 0 {name=l51 lab=RN18}
N 1740 630 1740 690 {}
C {lab_pin.sym} 1740 690 0 0 {name=l52 lab=RN19}
C {sg13cmos5l_pr/rhigh.sym} 1860 600 0 0 {name=Rref20 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1860 570 1860 510 {}
C {lab_pin.sym} 1860 510 0 0 {name=l53 lab=RN19}
N 1860 630 1860 690 {}
C {lab_pin.sym} 1860 690 0 0 {name=l54 lab=RN20}
C {sg13cmos5l_pr/rhigh.sym} 1980 600 0 0 {name=Rref21 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 1980 570 1980 510 {}
C {lab_pin.sym} 1980 510 0 0 {name=l55 lab=RN20}
N 1980 630 1980 690 {}
C {lab_pin.sym} 1980 690 0 0 {name=l56 lab=RN21}
C {sg13cmos5l_pr/rhigh.sym} 2100 600 0 0 {name=Rref22 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2100 570 2100 510 {}
C {lab_pin.sym} 2100 510 0 0 {name=l57 lab=RN21}
N 2100 630 2100 690 {}
C {lab_pin.sym} 2100 690 0 0 {name=l58 lab=RN22}
C {sg13cmos5l_pr/rhigh.sym} 2220 600 0 0 {name=Rref23 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2220 570 2220 510 {}
C {lab_pin.sym} 2220 510 0 0 {name=l59 lab=RN22}
N 2220 630 2220 690 {}
C {lab_pin.sym} 2220 690 0 0 {name=l60 lab=RN23}
C {sg13cmos5l_pr/rhigh.sym} 2340 600 0 0 {name=Rref24 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2340 570 2340 510 {}
C {lab_pin.sym} 2340 510 0 0 {name=l61 lab=RN23}
N 2340 630 2340 690 {}
C {lab_pin.sym} 2340 690 0 0 {name=l62 lab=RN24}
C {sg13cmos5l_pr/rhigh.sym} 2460 600 0 0 {name=Rref25 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2460 570 2460 510 {}
C {lab_pin.sym} 2460 510 0 0 {name=l63 lab=RN24}
N 2460 630 2460 690 {}
C {lab_pin.sym} 2460 690 0 0 {name=l64 lab=RN25}
C {sg13cmos5l_pr/rhigh.sym} 2580 600 0 0 {name=Rref26 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2580 570 2580 510 {}
C {lab_pin.sym} 2580 510 0 0 {name=l65 lab=RN25}
N 2580 630 2580 690 {}
C {lab_pin.sym} 2580 690 0 0 {name=l66 lab=RN26}
C {sg13cmos5l_pr/rhigh.sym} 2700 600 0 0 {name=Rref27 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2700 570 2700 510 {}
C {lab_pin.sym} 2700 510 0 0 {name=l67 lab=RN26}
N 2700 630 2700 690 {}
C {lab_pin.sym} 2700 690 0 0 {name=l68 lab=RN27}
C {sg13cmos5l_pr/rhigh.sym} 2820 600 0 0 {name=Rref28 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2820 570 2820 510 {}
C {lab_pin.sym} 2820 510 0 0 {name=l69 lab=RN27}
N 2820 630 2820 690 {}
C {lab_pin.sym} 2820 690 0 0 {name=l70 lab=RN28}
C {sg13cmos5l_pr/rhigh.sym} 2940 600 0 0 {name=Rref29 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 2940 570 2940 510 {}
C {lab_pin.sym} 2940 510 0 0 {name=l71 lab=RN28}
N 2940 630 2940 690 {}
C {lab_pin.sym} 2940 690 0 0 {name=l72 lab=RN29}
C {sg13cmos5l_pr/rhigh.sym} 3060 600 0 0 {name=Rref30 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 3060 570 3060 510 {}
C {lab_pin.sym} 3060 510 0 0 {name=l73 lab=RN29}
N 3060 630 3060 690 {}
C {lab_pin.sym} 3060 690 0 0 {name=l74 lab=RN30}
C {sg13cmos5l_pr/rhigh.sym} 3180 600 0 0 {name=Rref31 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 3180 570 3180 510 {}
C {lab_pin.sym} 3180 510 0 0 {name=l75 lab=RN30}
N 3180 630 3180 690 {}
C {lab_pin.sym} 3180 690 0 0 {name=l76 lab=RN31}
C {sg13cmos5l_pr/rhigh.sym} 3300 600 0 0 {name=Rref32 model=rhigh body=VSS w=2e-6 l=7.09e-6 b=0 m=1}
N 3300 570 3300 510 {}
C {lab_pin.sym} 3300 510 0 0 {name=l77 lab=RN31}
N 3300 630 3300 690 {}
C {lab_pin.sym} 3300 690 0 0 {name=l78 lab=VOUT}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 200 900 0 0 {name=Mca model=sg13_hv_pmos w=40u l=2u ng=1 m=1}
N 220 870 220 810 {}
C {lab_pin.sym} 220 810 0 0 {name=l79 lab=TAIL}
N 220 930 220 990 {}
C {lab_pin.sym} 220 990 0 0 {name=l80 lab=CN}
N 180 900 140 900 {}
C {lab_pin.sym} 140 900 0 0 {name=l81 lab=ISNS}
N 220 900 270 900 {}
C {lab_pin.sym} 270 900 0 0 {name=l82 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 500 900 0 0 {name=Mcb model=sg13_hv_pmos w=40u l=2u ng=1 m=1}
N 520 870 520 810 {}
C {lab_pin.sym} 520 810 0 0 {name=l83 lab=TAIL}
N 520 930 520 990 {}
C {lab_pin.sym} 520 990 0 0 {name=l84 lab=CO}
N 480 900 440 900 {}
C {lab_pin.sym} 440 900 0 0 {name=l85 lab=VTH}
N 520 900 570 900 {}
C {lab_pin.sym} 570 900 0 0 {name=l86 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 800 900 0 0 {name=Mna model=sg13_hv_nmos w=10u l=8u ng=1 m=1}
N 820 870 820 810 {}
C {lab_pin.sym} 820 810 0 0 {name=l87 lab=CN}
N 820 930 820 990 {}
C {lab_pin.sym} 820 990 0 0 {name=l88 lab=VSS}
N 780 900 740 900 {}
C {lab_pin.sym} 740 900 0 0 {name=l89 lab=CN}
N 820 900 870 900 {}
C {lab_pin.sym} 870 900 0 0 {name=l90 lab=VSS}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1100 900 0 0 {name=Mnb model=sg13_hv_nmos w=10u l=8u ng=1 m=1}
N 1120 870 1120 810 {}
C {lab_pin.sym} 1120 810 0 0 {name=l91 lab=CO}
N 1120 930 1120 990 {}
C {lab_pin.sym} 1120 990 0 0 {name=l92 lab=VSS}
N 1080 900 1040 900 {}
C {lab_pin.sym} 1040 900 0 0 {name=l93 lab=CN}
N 1120 900 1170 900 {}
C {lab_pin.sym} 1170 900 0 0 {name=l94 lab=VSS}
C {sg13cmos5l_pr/rhigh.sym} 1400 900 0 0 {name=Rtail model=rhigh body=VSS w=1e-6 l=26.1e-6 b=14 m=1}
N 1400 870 1400 810 {}
C {lab_pin.sym} 1400 810 0 0 {name=l95 lab=TAILP}
N 1400 930 1400 990 {}
C {lab_pin.sym} 1400 990 0 0 {name=l96 lab=TAIL}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1700 900 0 0 {name=Men_t model=sg13_hv_pmos w=5u l=0.5u ng=1 m=1}
N 1720 870 1720 810 {}
C {lab_pin.sym} 1720 810 0 0 {name=l97 lab=VIN}
N 1720 930 1720 990 {}
C {lab_pin.sym} 1720 990 0 0 {name=l98 lab=TAILP}
N 1680 900 1640 900 {}
C {lab_pin.sym} 1640 900 0 0 {name=l99 lab=ENB}
N 1720 900 1770 900 {}
C {lab_pin.sym} 1770 900 0 0 {name=l100 lab=VIN}
C {sg13cmos5l_pr/cap_cmomi.sym} 200 1500 0 0 {name=Ccl model=cap_cmomi w=22e-6 l=22e-6 mmin=1 mmax=4 feed=double subblock=0 m=1 mm_ok=1}
N 200 1470 200 1410 {}
C {lab_pin.sym} 200 1410 0 0 {name=l101 lab=CO}
N 200 1530 200 1590 {}
C {lab_pin.sym} 200 1590 0 0 {name=l102 lab=VSS}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 500 1500 0 0 {name=Men_co model=sg13_hv_nmos w=1u l=1u ng=1 m=1}
N 520 1470 520 1410 {}
C {lab_pin.sym} 520 1410 0 0 {name=l103 lab=CO}
N 520 1530 520 1590 {}
C {lab_pin.sym} 520 1590 0 0 {name=l104 lab=VSS}
N 480 1500 440 1500 {}
C {lab_pin.sym} 440 1500 0 0 {name=l105 lab=ENB}
N 520 1500 570 1500 {}
C {lab_pin.sym} 570 1500 0 0 {name=l106 lab=VSS}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 800 1500 0 0 {name=Mg2 model=sg13_hv_nmos w=10u l=1u ng=1 m=1}
N 820 1470 820 1410 {}
C {lab_pin.sym} 820 1410 0 0 {name=l107 lab=CLG}
N 820 1530 820 1590 {}
C {lab_pin.sym} 820 1590 0 0 {name=l108 lab=VSS}
N 780 1500 740 1500 {}
C {lab_pin.sym} 740 1500 0 0 {name=l109 lab=CO}
N 820 1500 870 1500 {}
C {lab_pin.sym} 870 1500 0 0 {name=l110 lab=VSS}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1100 1500 0 0 {name=Mlg model=sg13_hv_pmos w=5u l=2u ng=1 m=1}
N 1120 1470 1120 1410 {}
C {lab_pin.sym} 1120 1410 0 0 {name=l111 lab=VIN}
N 1120 1530 1120 1590 {}
C {lab_pin.sym} 1120 1590 0 0 {name=l112 lab=CLG}
N 1080 1500 1040 1500 {}
C {lab_pin.sym} 1040 1500 0 0 {name=l113 lab=IBIAS}
N 1120 1500 1170 1500 {}
C {lab_pin.sym} 1170 1500 0 0 {name=l114 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1400 1500 0 0 {name=Mcoff model=sg13_hv_pmos w=2u l=0.5u ng=1 m=1}
N 1420 1470 1420 1410 {}
C {lab_pin.sym} 1420 1410 0 0 {name=l115 lab=VIN}
N 1420 1530 1420 1590 {}
C {lab_pin.sym} 1420 1590 0 0 {name=l116 lab=CLG}
N 1380 1500 1340 1500 {}
C {lab_pin.sym} 1340 1500 0 0 {name=l117 lab=EN}
N 1420 1500 1470 1500 {}
C {lab_pin.sym} 1470 1500 0 0 {name=l118 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1700 1500 0 0 {name=Mclamp model=sg13_hv_pmos w=40u l=0.5u ng=1 m=1}
N 1720 1470 1720 1410 {}
C {lab_pin.sym} 1720 1410 0 0 {name=l119 lab=VIN}
N 1720 1530 1720 1590 {}
C {lab_pin.sym} 1720 1590 0 0 {name=l120 lab=EAOUT}
N 1680 1500 1640 1500 {}
C {lab_pin.sym} 1640 1500 0 0 {name=l121 lab=CLG}
N 1720 1500 1770 1500 {}
C {lab_pin.sym} 1770 1500 0 0 {name=l122 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 2000 1500 0 0 {name=Minvp model=sg13_hv_pmos w=1u l=1u ng=1 m=1}
N 2020 1470 2020 1410 {}
C {lab_pin.sym} 2020 1410 0 0 {name=l123 lab=VIN}
N 2020 1530 2020 1590 {}
C {lab_pin.sym} 2020 1590 0 0 {name=l124 lab=ENB}
N 1980 1500 1940 1500 {}
C {lab_pin.sym} 1940 1500 0 0 {name=l125 lab=EN}
N 2020 1500 2070 1500 {}
C {lab_pin.sym} 2070 1500 0 0 {name=l126 lab=VIN}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 2300 1500 0 0 {name=Minvn model=sg13_hv_nmos w=1u l=1u ng=1 m=1}
N 2320 1470 2320 1410 {}
C {lab_pin.sym} 2320 1410 0 0 {name=l127 lab=ENB}
N 2320 1530 2320 1590 {}
C {lab_pin.sym} 2320 1590 0 0 {name=l128 lab=VSS}
N 2280 1500 2240 1500 {}
C {lab_pin.sym} 2240 1500 0 0 {name=l129 lab=EN}
N 2320 1500 2370 1500 {}
C {lab_pin.sym} 2370 1500 0 0 {name=l130 lab=VSS}
C {iopin.sym} -200 100 0 0 {name=p1 lab=VIN}
C {iopin.sym} -200 200 0 0 {name=p2 lab=VOUT}
C {iopin.sym} -200 300 0 0 {name=p3 lab=EAOUT}
C {iopin.sym} -200 400 0 0 {name=p4 lab=IBIAS}
C {ipin.sym} -200 500 0 0 {name=p5 lab=EN}
C {iopin.sym} -200 600 0 0 {name=p6 lab=VSS}
