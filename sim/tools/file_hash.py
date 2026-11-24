#!/usr/bin/env python3
"""The one sha256-of-a-file helper the sim/ drivers share (issue #362).

Until #362 every module that needed "sha256 of a file, hex" carried its own
hand-rolled copy -- about ten across sim/ -- differing only in read style
(whole-file vs 1 MiB chunks), repo-relative vs absolute paths, a ``[:16]``
truncation, or error wrapping. This module is the one definition those call
sites share, the same consolidation render_deck.py (#236) made for the
@@TOKEN@@ renderer. Two deliberate details:

- The file is read in 1 MiB chunks, never whole-file: call sites hash traces,
  rawfiles and records that can be large, and only the hex digest is wanted.
- ``n`` truncates the digest to its first ``n`` hex characters, replacing the
  per-site ``[:16]`` slices the producer-pin call sites used to carry.

Deliberately NOT converted (issue #362's own escape hatch for wrappers that
cost more than they save):

- ``ldo-cmos5l-pvt-sweep/row10_margins.py`` and ``item5_evidence.py``: their
  bytes are pinned inside already-landed, append-only evidence (the
  row10-margins.json classifier pins and the DC coverage inventory's
  generator pin), so any edit rewrites committed evidence files.
- ``harness/evidence_store.py``: its fail-closed ``StoreError`` wrapping and
  ``(hex, size)`` return share only the digest loop with this helper, and
  importing sim/tools from that package module would need sys.path surgery
  in a library.

Python API:
    import file_hash
    file_hash.sha256_file(path)        # full 64-hex digest
    file_hash.sha256_file(path, 16)    # first 16 hex characters

Call sites pass the path exactly as they resolved it; this helper does no
repo-relative joining (the two repo-relative wrappers named above keep
theirs).
"""
import hashlib

_CHUNK = 1 << 20


def sha256_file(path, n=None):
    """Hex sha256 of ``path``'s bytes, truncated to the first ``n`` hex
    characters when ``n`` is given. Read errors propagate unchanged; callers
    that need fail-closed wrapping do it at their own boundary."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(blk)
    digest = h.hexdigest()
    return digest[:n] if n is not None else digest
