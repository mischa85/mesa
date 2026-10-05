# Spill-home coalescing prototype — 2026-10-05

Branch: `apple9/spill-home-coalesce`, based on the SSA cleanup fix and pressure
audit. The prototype builds on the host and passes the focused CPU tests.
**Mini builds/replays and all GPU tests are waiting for the coordinator's
explicit end-of-ABAB signal.** No mini command has been issued for this prototype.

## Implementation

Set `AGX_SPILL_COALESCE=1` to enable the experiment; leave it unset for the
control. This is an allocator experiment, with no new ISA encoding or launch
behavior. It does not change kernel UAPI or production-installed drivers.

1. SSA repair records the original memory variable for each surviving memory
   SSA definition. SSA renumbering carries that identity forward; newly created
   values without provenance get no affinity.
2. After spilling and liveness analysis, build a memory interference graph.
   Phi inputs are live on their predecessor edges; phi definitions act in
   parallel. Include dead writes so they cannot clobber live values. Widths use
   the allocator's rounded half-register sizes.
3. Run the existing allocator normally. Verify that each memory SSA value has
   one consistent physical slot and that the original assignment satisfies the
   graph. Physical memory moves or split memory assignments cause a fallback.
4. Contract compatible, noninterfering versions of a home into a group.
   Interfering versions or different widths remain separate. Color groups by
   saturation and degree, respecting width and alignment.
5. Commit the complete recoloring only if it fits within the **original frame
   high-water mark**. Otherwise preserve the original assignment. Rewrite all
   memory operands, including the allocator's synthetic identity phis, before
   normal allocation validation and phi-copy lowering.

The experiment is bounded to 4,096 memory SSA definitions; larger programs use
the original assignment. This first version may fall back when a less aggressive
partial coalescing would fit. It leaves GPR allocation and reload placement
unchanged. Memory-phi transfer sequences can disappear; GPR swaps need not change
unless downstream candidate selection changes. Reload placement should be
considered after measuring and attributing the resulting program.

## Offline evidence, not compiler replay results

The retained fixed repro's postspill IR gives:

| Property | Count |
|---|---:|
| Memory SSA definitions | 462 |
| Original spill homes | 120 |
| SSA interference edges | 13,961 |
| Interferences between versions of the same home | 0 |
| Edges after contracting homes | 4,555 |
| Host model coloring | 69 words |
| Existing assignment | 72 words |

`model-spill-coalesce.py` reconstructs liveness and the graph from the retained
IR. Its 69-word result supports trying full home coalescing without growing the
frame. It is not a compiled shader measurement. Scratch metadata alignment may
also hide a small reduction in raw slots: 69 words is 276 bytes, versus the
current 288-byte frame.

## Validation

Host build: `build-cpu-audit/src/asahi/compiler/agx_tests`, native x86 CPU only.
The 21 focused tests in `SpillCoalesce.*:RepairSSA.*:Apple9SharedRa.*` pass with
the experiment both enabled and disabled. The six new tests cover:

- Diamond memory phis becoming same-slot moves.
- Interfering versions of a home staying separate.
- A dead phi not overwriting another live memory value.
- A contraction that raises the chromatic requirement rolling back without
  growing scratch or changing any original assignment.
- Loop-backedge coalescing.
- Mixed-width alignment and non-overlap.

The shared-allocator tests also exercise the real spill/repair path with the
experiment enabled. Allocation validation remains active.

Broader enabled testing, excluding two aborting compiler tests, completed
399 tests: **398 passed, one failed**. The failure
`Apple9Compiler.SixteenIndependentTextureAndSamplerBindings` reports the same
`seen=3` versus `0xffff` result with the experiment disabled. The excluded
`WritableSinkPointer` assertion was previously confirmed against the baseline
compiler. `BlockExportCompilesDynamicCoordinatesAndSparseImages` hits a NIR
divergence stage assertion before allocation and reproduces with the experiment
disabled. These are not claimed as passing tests or silently folded into skips.

Logs are in `tmp/cs2-pressure-20261005/host-*`; the model is
`tmp/cs2-pressure-20261005/coalesce-model.json`.

## Replays after ABAB

Build an isolated candidate on the mini, pinned to cores 1–6 at nice 5. Preserve
the existing baseline, fixed, and frame-probe libraries. First replay graphics
pipeline `105 106` with the new library and the experiment **unset**; require
the fixed main's body hash
`0495ebc4e6d9faa9ebf90e89161e6e657a45f23364e565aaaf90b70669316ed2`.
Then repeat with `AGX_SPILL_COALESCE=1`, retaining stats, binary, phi-copy audit,
and coalescing/fallback diagnostics. Report against both prior baselines:

| Repro main | Original | SSA cleanup | Coalescing |
|---|---:|---:|---:|
| Instructions | 11,759 | 8,041 | pending |
| True swaps | 1,584 | 735 | pending |
| SAVE | 645 | 443 | pending |
| FILL | 782 | 575 | pending |
| Scratch bytes | 288 | 288 | pending |

Only after the coordinator says ABAB is done: terminate its stopped helper
shell PID 27539 and resume frozen CPU replays 25143/25152, or restart with the
agreed comparison variants. Whole-capture reporting must retain separate
fragment/vertex/compute totals and independent at-cap cohorts. Both existing
full replays use `NIR_DEBUG=novalidate` for the previously identified pre-RA
pipeline-6 assertion; allocation validation stays enabled. GPU CTS must not
inherit that workaround.

The 604 selected CTS cases and separate frame-destination probe remain queued
for the explicitly released GPU slot. No reload-placement change or wider
allocator restructuring is included in this prototype.
