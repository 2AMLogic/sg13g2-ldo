# sg13g2-ldo — agent instructions

Open-source canary block: a low-dropout linear regulator (LDO) on IHP SG13G2,
a 130 nm SiGe BiCMOS open PDK, designed and verified by AI agents.

- **PDK**: IHP SG13G2 (open PDK, IHP-GmbH/IHP-Open-PDK). Open-source flow:
  xschem + ngspice for design/sim, klayout-tools (`klt`) for layout work.
- **The deck is new.** `klt` resolves this PDK, and a curated SG13G2 DRC/LVS
  starter deck ships with klayout-tools (klayout-tools #905/#911) — but it is
  starter-grade, not battle-tested. Expect deck gaps as normal friction: a
  rule the deck cannot check yet, an LVS device it does not extract, a
  waiver it lacks. File each one upstream rather than routing around it —
  surfacing exactly that friction is the reason this repo exists.
- **The PDK is the variable, not the design.** This block is a port of the
  fleet's proven LDOs (`gf180-ldo`, `sky130-ldo`) *on purpose*. Anything
  that breaks should be assumed to be the PDK, the deck, or the tools before
  it is assumed to be the circuit. Start from the sibling repos' schematics,
  specs, and decision records rather than from a blank page.
- **BiCMOS is a real difference.** SG13G2 offers actual bipolar devices
  alongside CMOS. That widens the design space where it matters most for an
  LDO — the pass device and the error amplifier — and gives extraction and
  LVS a device class the CMOS ports never exercised. Departures from the
  sibling designs go through decision records, not assumptions.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and describe
  the gap, not the design.
- **Verification is the product**: no claim without a testbench. PVT corners
  on every recorded result; `sim/` results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not relax
  the ratified spec to make results pass.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
