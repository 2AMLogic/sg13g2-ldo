# DR-0021: The row-4 citation freshness check pins a canonical projection of the PDK pin, not the fact sheet's bytes

- **Status**: **Decided.** For *new* row-4 envelope records, `provenance.json`
  carries `pdk_pin_projection_sha256` and `sim/pdk-cmos5l.json` is no longer
  in `input_sha256`. `stale_inputs()` compares the projection for records that
  carry it and keeps the whole-file byte compare for legacy records. This is
  an evidence-tooling semantics change and it is **not** a loosening (see
  "Why this is not a loosening"). No threshold, gate, record or verdict
  changes; the cited record `20261114-072921-41a8294b` stays valid with no
  re-run.
- **Date**: 2026-11-16
- **Scope**: `sim/ldo-cmos5l-pvt-sweep/row4_envelope.py` (provenance writer,
  `stale_inputs()`) only. Issue #282. Other `sim/` evidence tooling and
  `sim/pdk.json` are untouched.

## Problem

`row4_envelope.py` hashed `sim/pdk-cmos5l.json` whole-file into every record's
`input_sha256`, and `check` re-hashed it for the cited record. That file's own
`_comment` says it is "not consumed by tooling"; no code parses it. A
documentation-only edit to a prose string (#275, `fetch_method`) therefore
made the citation stale, and the only sanctioned remedy was a 45-corner fleet
`submit` (#279) that reproduced the same verdict.

## Decision

The claim a record's PDK provenance makes is "this run used this PDK
revision". The keys that determine that are `pinned_commit`,
`pinned_tarball_sha256`, `pinned_tarball_url` and `subtree` (the URL and
subtree also determine the fetched tree, so all four are pinned). New records
store `pdk_pin_projection_sha256`: the sha256 of the canonical JSON
(`sort_keys`, separators `(",", ":")`) of exactly those four keys. The
projection is therefore independent of key order, whitespace and every prose
key.

- A projected key that is missing, empty or not a string is an **error**
  (`ValueError`, reported by `check` as a stale/failed citation), never a
  silent skip.
- Legacy records (no projection field) keep their whole-file byte compare
  over every entry of their own `input_sha256`, including
  `sim/pdk-cmos5l.json`.
- The template, both design netlists and `render_deck.py` stay byte-pinned.

## Why this is not a loosening

- Changing any of the four projected keys changes the projection and makes the
  citation stale (tests `test_each_projected_key_change_makes_the_citation_stale`).
- A key rename/removal cannot slip through: it raises rather than projecting
  an empty value.
- Legacy records are checked exactly as before
  (`test_legacy_record_still_fails_on_any_byte_change`).
- The only edits newly tolerated are those to keys no code reads and that do
  not identify the fetched tree. The fetched tree itself is additionally
  anchored by `models_lib_sha256` and the netlist hashes inside the record.

## Consequences

- Prose maintenance of `sim/pdk-cmos5l.json` no longer forces a fleet re-run
  for records minted after this change.
- The next `submit` mints a record in the new format; until then the cited
  legacy record keeps the old, stricter semantics.
