# Dead-source SAVE staging experiment

Compiler change `caf135c0d93`, after the unchanged four phi-affinity changes.
This implements the first opportunity from [COPY-ATTRIBUTION.md](COPY-ATTRIBUTION.md).
It was developed and replayed entirely on the host after releasing the mini
following [stage-four CTS and mini replay](CTS-STAGE4-20261005.md).
The SAVE change has **not been GPU-tested or replayed on the mini**.

## Result

The matched host whole-capture replay completed successfully with 10,161 main
outputs. It removes all 8,300 staging copies predicted by the census and saves
7,930 instructions after completion scheduling. No output grows.

| Stage | Outputs | Copies removed | Net instructions removed | Outputs improved |
|---|---:|---:|---:|---:|
| Fragment | 4,127 | 7,664 | 7,502 | 293 |
| Vertex | 5,045 | 222 | 94 | 14 |
| Compute | 989 | 414 | 334 | 3 |
| Total | 10,161 | 8,300 | 7,930 | 310 |

Every output retains exactly the same GPR count, swap count, SAVE count, FILL
count and scratch size. Final fragment/vertex/compute instruction totals are
2,460,561 / 954,728 / 1,592,318; ordinary-copy totals are
146,087 / 20,003 / 62,849. These are matched host results against the frozen
stage-four host replay, not comparisons against the mini's slightly different
code generation and not in-game performance measurements.

The fragment pressure reproducer (graphics pipeline range 105–106) changes
4,017 → 3,934 instructions. Decoded assembly has exactly 93 fewer IOR copies
and 10 more standalone WAITs; all other opcode counts are unchanged. It still
uses 191 SAVE, 157 FILL, 96 GPRs and 272 bytes of scratch. Compiler wait stats
include folded completion waits and therefore differ from standalone WAIT
opcode counts. Whole-capture net counts above include all scheduling effects.

## Implementation and boundaries

The shared allocator snapshots a spill MOV's original last-use marker before
early killing clears it, then restores the marker after assigning registers.
This is limited to a GPR-to-memory MOV on targets preserving source kills;
allocation, interference and affinity decisions are unchanged. Generated
parallel-copy moves without a proven last use keep their conservative path.

Compact SAVE consumes the allocated source register directly when this marker
is set. Live sources still go through the reserved copy register. Vector moves
apply the same last-use fact to every component. Indexed private stores beyond
the compact SAVE frame range retain their existing lowering.

Physical completion tracking treats SAVE's source as a destructive write when
checking older pending producers. It waits for previous asynchronous borrowers
before consuming the register. Existing pending-SAVE tracking prevents register
reuse until SAVE completes. The change adds no allocation trials, capture
special cases, fixed placements or experiment switch.

## Validation

- 238/238 native host tests outside `Apple9Compiler.*` pass. The excluded suite
  has the previously established unrelated pre-RA `WritableSinkPointer` NIR
  assertion; it is not claimed as passing coverage.
- 4/4 forced-spill `Apple9Spilling.*` tests pass.
- The vector spill interpreter poisons destructive SAVE sources and requires
  direct, non-reserved sources for spilling cases. It covers 2/4-component
  vectors and frames reaching both indexed FILL and indexed store lowering.
- Linking the strengthened vector test against exact stage-four allocator and
  lowering sources fails its six new direct-SAVE checks, with zero direct
  SAVEs. The candidate passes the same test.
- The loop-pressure interpreter keeps SAVE sources borrowed until their
  completion, checks their contents at that point, rejects premature overwrite
  or another destructive SAVE, then poisons the register. Its loop-carried
  values and final checksum remain correct, and physical instructions pack.
- Whole-capture replay exits 0 with all 10,161 rows and per-row unchanged
  register/spill/swap checks. Shader cache is disabled, coalescing enabled and
  loop handling enabled. Capture replay retains its existing NIR-validation
  exception. Tests use native assertions.

The host replay uses the existing fake G16 DRM device and performs no GPU
submissions. A future mini slot is needed for the two focused CTS sets and a
mini replay before treating this fifth change as GPU-validated.

## Evidence

`tmp/cs2-pressure-20261005/save-experiment/` contains build scripts, full test
logs, the isolated baseline-linked test, `whole-comparison.json`, and decoded
before/after pressure-reproducer assembly in `repro-105.json`. The immutable
host candidate is `vertex-analysis/drivers/dead-save/`. Whole-replay rows and
pipeline mappings are `vertex-analysis/dead-save-host{,-mapping}.jsonl`; the
frozen control is `vertex-analysis/private-history-host.jsonl`.

`save-experiment-host.tar.gz` archives source/patch provenance, candidate
library, row data, focused assembly and logs. Its build scripts expect the
existing workspace build/toolchain; it is an evidence bundle, not a portable
build environment. The mini validation bundle for the preceding four changes
is separate: `tmp/phi-stage4-validation.tar.gz`.
