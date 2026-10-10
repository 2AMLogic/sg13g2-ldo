<!-- BEGIN LOOM ORCHESTRATION (AGENTS) -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration (dual-runtime: Claude Code reads `CLAUDE.md`; OpenAI Codex CLI and other AGENTS.md-aware runtimes read this file). See the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of the runtime-neutral guide to `.loom/AGENTS.md`.
<!-- END LOOM ORCHESTRATION (AGENTS) -->

## Final validation (sg13g2-ldo)

After your last source edit and before requesting review, follow
[`signoff/README.md#regenerating`](signoff/README.md#regenerating): if you
changed any hash-pinned input (e.g. `CLAUDE.md`, `README.md`,
`.github/workflows/ci.yml`, sweep scripts), refresh the derived artifacts in
the documented order with the exact pinned grader and confirm the committed
output reproduces. Do not weaken CI gates, spec thresholds, records or
verdicts; `sim/` results stay append-only and exit 3 remains an honest non-T1
result.
