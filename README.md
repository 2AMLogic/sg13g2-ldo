# sg13g2-ldo

A low-dropout linear regulator (LDO) on
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), a 130 nm SiGe BiCMOS
open PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: design and verification in progress.** The SG13G2 branch has a
core schematic with a behavioral error amplifier. The SG13CMOS5L branch
has a transistor-level amplifier, closed-loop PVT simulation records, and
layout with committed DRC/LVS reports. The [signoff report](signoff/sg13g2-ldo.t1-report.json)
currently grades 8 of 11 T1 evidence items as met; no T1 tier is awarded.
See [DR-0007](spec/decision-records/DR-0007-target-spec-row-ratification.md)
for per-row ratification and evidence gaps, and [WORK_PLAN.md](WORK_PLAN.md)
for the current work queue.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using SG13G2, not just this repo.

## Why this block, on this PDK

This is a **port, not a new design**. The fleet has already carried this
block through two PDKs — the ratified, corner-verified
[gf180-ldo](https://github.com/2AMLogic/gf180-ldo) and its mirror
[sky130-ldo](https://github.com/2AMLogic/sky130-ldo) — so the circuit, the
spec structure, and the verification harness are known quantities. That is
the whole experimental design: **the PDK is the variable, not the design.**
Anything that breaks here should be assumed to be the PDK, the deck, or the
tools before it is assumed to be the circuit. Work starts from the sibling
repos' schematics, specs, and decision records, not from a blank page.

SG13G2 being a **BiCMOS** process is a genuine difference, not just a rule
deck swap: it offers real bipolar devices alongside CMOS, which reopens the
two choices that define an LDO — the pass device and the error amplifier —
and hands extraction and LVS a device class the CMOS ports never exercised.
Where SG13G2's device set makes the sibling design's choice wrong rather
than merely different, the departure is argued in a decision record.

The SG13G2 DRC/LVS deck in klayout-tools is a recently shipped starter deck.
Part of this canary's job is to find what it cannot check yet and file those
gaps upstream — never to route around them.

## Target specification (1 of 10 rows ratified; 9 open)

Port parity: the targets below mirror the ratified gf180-ldo spec — same
block, third PDK. Row-by-row ratification is recorded in [DR-0007](spec/decision-records/DR-0007-target-spec-row-ratification.md).
**One row is ratified:** dropout @ 50 mA, by the two independent non-author
review verdicts (`RATIFY-KEY: ee`, `RATIFY-KEY: market`) on pull request
#65. Every other row is *OPEN* (unratified; missing evidence named in the
record). An OPEN row is not a passing requirement. No target value was
changed by the record.

| Parameter | Target | Stretch | Status ([DR-0007](spec/decision-records/DR-0007-target-spec-row-ratification.md)) |
|---|---|---|---|
| Input | 3.3 V ±10% — confirm against SG13G2 device flavors | — | OPEN — unratified (current-limit \|Vsg\| gate from DR-0001) |
| Output | 1.8 V ±2% (fixed) | programmable variants deferred | OPEN — unratified (statistical; Monte Carlo missing) |
| Load | 0–50 mA (no external preload assumed) | 100 mA | OPEN — unratified (no 0 mA dynamic evidence) |
| Dropout @ 50 mA | < 300 mV worst corner | < 200 mV | RATIFIED as a shared target (stretch not ratified); branch compliance differs — see the row 4 branch note below |
| Line / load regulation | < 5 mV/V; < 1% over full load, inside the accuracy window | — | OPEN — unratified (loaded line / multi-Vin load regulation missing) |
| PSRR | > 50 dB @ 1 kHz, > 20 dB @ 100 kHz | > 60 dB @ 1 kHz | OPEN — unratified (1 mA / 1 µF only; `Cc` un-cornered) |
| Iq (excluding load) | < 30 µA at no load and at full load | < 10 µA | OPEN — unratified (no current full-load record) |
| Current limit | 65–80 mA brickwall over PVT; short-survivable | — | OPEN — unratified (not implemented; statistical) |
| Startup | monotonic, controlled ramp, inside ±2% within 3 ms of enable | — | OPEN — unratified (not implemented) |
| Stability | 0–50 mA, C_out 0.33–4.7 µF effective, ESR 0–500 mΩ; PM ≥ 45°, GM ≥ 10 dB worst corner | capless variant (separate fork) | OPEN — unratified (one load/C_out/ESR point only) |

**Row 4 branch note (snapshot: `origin/main` `028a3f8`, 2026-10-10).** "Ratified" means the `< 300 mV` *target* is ratified for the shared table; it is not a statement that both implementation branches meet it. The two branches differ:

- **SG13CMOS5L: meets the target at schematic level.** `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` has a `w=2800u` pass device behind a transistor-level error amplifier, and its closed-loop PVT sweep ratified the row.
- **SG13G2: not evidenced; predicted to miss with the committed provisional sizing.** `design/netlist/ldo_core.spice` still has `w=300u` behind a behavioural VCVS amplifier, and the ratifying sweep is not SG13G2 evidence. PR #65's engineering-key review derived, from the committed bare-device screen, about 47 ohm (about 2.35 V at 50 mA) and an implied width of 2169–2351 µm. That is a screening-derived prediction, **not** a closed-loop SG13G2 measurement. Resizing the pass device, a transistor-level amplifier and a closed-loop dropout bench are future work and are not part of this correction.

The target value and row disposition are unchanged.

Maturity ladder: spec ratified → schematic simulated across PVT → layout
DRC/LVS-clean → post-layout re-verification → shuttle seat → measured
silicon. **Current position: spec ratification in progress** (DR-0007: 1 of 10 rows ratified — dropout @ 50 mA; the other 9 are open).

## Repo layout

```
spec/          target-spec ratification + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
