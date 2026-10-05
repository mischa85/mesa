# Loop handling plus spill-home coalescing

Branch `apple9/spill-loops-coalesce` rebases the experiment onto the coordinator's
`d50f7be1e35`. The coordinator's checkout is untouched. Common validation fixes
are committed as `7f8c3a112a9`; CTS evidence retention is `eced303bc84`.

## CPU comparison, graphics pipelines [0, 200)

The same isolated driver is used with coalescing unset/enabled and loop handling
enabled. Both replays use cores 1–6, nice 5, one replay thread, and the coordinator's
`foz-summary.py`/stream parser with stats and assembly enabled. This matches the
coordinator's loop-only range exactly. `NIR_DEBUG=novalidate` remains the known
pipeline-6 workaround for capture replay only; allocator validation stays on.

| At-cap fragment programs (16) | Loops | Loops + coalescing |
|---|---:|---:|
| Instructions | 53,446 | 52,724 |
| True swaps | 2,140 | 2,184 |
| SAVE | 821 | 544 |
| FILL | 772 | 494 |
| Scratch metadata sum, B | 1,392 | 1,392 |

Across all 172 fragment programs: instructions 118,185 → 117,463; swaps
2,399 → 2,443. Five outputs change, all with fewer instructions; none grows
scratch. Vertex output is unchanged. These parser totals retain unnamed stub
vertex programs, matching the coordinator's no-TRACE run.

The repro improves 6,271 → 5,781 instructions, 387/354 → 191/157 SAVE/FILL,
with scratch unchanged at 272 B, but swaps increase 441 → 485. It accounts for
all 44 extra swaps in this range. Audit confirms candidate selection explains this: loop-only selects allocation
10; coalescing selects allocation 12. Every candidate has identical GPR edge
assignments before and after coalescing. Allocation 10 has 441 swaps in both
runs, allocation 12 has 485 in both. Memory phi transfers fall from 199 pairs
to 3 in allocation 10, and from 201 pairs to 3 in allocation 12. The cost
model therefore makes a different scheduling/allocation candidate win.

The combined whole-capture replay was interrupted by a target reset after
5,048 rows; no whole-capture combined totals are claimed. Its incomplete
`all-coalesce.jsonl` must not be compared as a complete capture. A stable
window is needed to restart it against the coordinator's loop-only rows.

## CTS setup repairs and CPU evidence

The tile-store fragment shader incorrectly used the compute `load_workgroup_id`
intrinsic. A dedicated `load_tile_id_agx` now represents tile indices with the
same native SR mapping and legal fragment-stage divergence semantics. The
existing block-export compiler test reproduces the original abort and now passes.

Apple9 initializes the shared compiler flags before allocation, so
`AGX_MESA_DEBUG=spill` takes effect. The forced budget also includes the target's
spill temporaries and simultaneous source/destination widths of one instruction.
Without that minimum, a vec4 split plus reserved registers exceeded the old
24-half-register budget, even with loop handling disabled.

The 32-word vector test now checks zero scratch/SAVE/FILL normally and actual
spilling when forced, then interprets the allocated value movement. The loop
stress test produces 220 SAVE + 220 FILL (or 221/221 with private arrays) at 16
GPRs under forced spilling. Normal focused host tests: 26/26 pass. Forced
block-export + spilling tests: 5/5 pass on host and mini. The broader forced
shared-RA run had two expectation failures: one deliberately expects zero scratch,
the other assumes every MOV source is a high GPR although forced spilling adds
memory MOVs. These are not counted as passing forced tests.

The CTS wrapper preserves compiler stderr even for passing cases; forced cases
run individually. Its summarizer requires a passing case to have compiled both
SAVE and FILL before calling the set spill validation. GPU execution is pending
a newly granted slot, requested after the CPU fixes passed. No GPU execution
has occurred for this branch.

Isolated library SHA256:
`6726cf7c95fbae4e89a48a26a0aeb93d839eccf7fecabf67ad157487cfd29541`

ICD: `/root/claude-ra/codex-pressure/loops-coalesce-driver/icd.json`.
Artifacts: local `tmp/cs2-pressure-20261005/loop-comparison/`; corresponding
mini directory `/root/claude-ra/codex-pressure/loop-comparison/`.

## Remaining repro swap attribution

All 441 loop-only swaps occur in phi parallel copies, with zero from constrained
operand assignment or the allocator's other copy sites. Cycle composition:

| GPR cycle origin | Swaps |
|---|---:|
| Original phis only | 62 |
| Spill-repair phis only | 85 |
| Original + repair | 278 |
| Original + repair + live-in reconciliation | 16 |

At loop depths 0/1/2/3, these are 83/197/149/12 swaps. There are 155 real
reload instructions (354 total FILL minus 199 phi-copy FILL). The previous
live-through reloads are gone: all ten natural loops have zero reloads whose
original variable has no non-transfer use in that loop. In particular headers
17, 46, 61 and 111 now contain zero reloads. Large loops 42 and 107 still have
71 and 53 reloads, all serving values used inside their respective loops.
Nested-loop counts overlap and must not be summed.

Of the 85 repair-only swaps, 84 are in cycles mixing computed values, reloads
and rematerialized constants; one mixes reloads and constants. This does not
support further removal of loop-unused reloads as the next lever. It does not
yet establish that the remaining phi permutations are unavoidable.

The selected combined candidate has 154 real reloads and 485 GPR swaps:
83 original-only, 103 repair-only, 295 original+repair, and 4 original+live-in.
All ten loops still have zero live-through-but-unused reloads. Evidence and
scripts: `loops-audit/`, `coalesce-audit/`, `loops-reloads/`,
`coalesce-reloads/`, and the two `*-105-audit.log` files in the local artifacts.
