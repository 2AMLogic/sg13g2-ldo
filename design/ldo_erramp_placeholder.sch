v {xschem version=3.4.7 file_version=1.3
* ldo_erramp_placeholder -- behavioral placeholder error amplifier for
* ldo_core (issue #6, T1 item 1: design sources). This is NOT a stand-in
* for any sibling repo's amplifier circuit -- there is no gain stage, bias
* network, or compensation here to have copied. It is a single ideal
* voltage-controlled voltage source (E1, xschem's generic devices/vcvs.sym,
* which xschem/ngspice netlists as a native SPICE E element -- no PDK
* device involved), mirroring gf180-ldo's own "ldo_erramp_placeholder"
* naming/behavioral-placeholder pattern for a first schematic-entry
* increment (this issue's acceptance criteria ask for exactly that
* pattern by name). A full bipolar-vs-CMOS input-stage decision for a
* real amplifier is explicitly out of scope here -- see
* spec/porting-plan.md Sec 2.2 and Sec 4 item 5, and design/README.md.
*
* OUT = value * (INP - INN), referenced to VSS (an explicit pin, not an
* implicit global ground alias) -- so INP is the non-inverting input and
* INN the inverting input, in the conventional op-amp sense.
*
* No VDD pin: an ideal VCVS has no supply or bias current to model, so
* none is exposed on this placeholder. A real amplifier's pin list
* (likely INP INN OUT VDD VSS, the universal 5-terminal op-amp
* convention, plus whatever EN/bias pins its own topology needs) will be
* renegotiated when it replaces this cell -- not assumed here.
}
G {}
K {}
V {}
S {}
E {}
C {vcvs.sym} 200 200 0 0 {name=E1 value=100k}
N 160 180 120 180 {}
C {lab_pin.sym} 120 180 0 0 {name=l1 lab=INP}
N 160 220 120 220 {}
C {lab_pin.sym} 120 220 0 0 {name=l2 lab=INN}
N 200 170 200 140 {}
C {lab_pin.sym} 200 140 0 0 {name=l3 lab=OUT}
N 200 230 200 260 {}
C {lab_pin.sym} 200 260 0 0 {name=l4 lab=VSS}
C {ipin.sym} -60 180 0 0 {name=p1 lab=INP}
C {ipin.sym} -60 220 0 0 {name=p2 lab=INN}
C {opin.sym} 460 140 0 0 {name=p3 lab=OUT}
C {iopin.sym} 200 340 0 0 {name=p4 lab=VSS}
