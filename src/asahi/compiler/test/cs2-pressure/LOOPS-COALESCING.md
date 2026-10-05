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

The first combined whole-capture replay was interrupted by a target reset after
5,048 rows. Its incomplete `all-coalesce.jsonl` must not be compared as a complete
capture. The replacement whole-capture comparison is documented below.

## Completed whole-capture comparison

The replacement runs completed with replay/parser exits `0/0`: 478 seconds for
loops and 483 seconds for loops + coalescing. Both were CPU-only, pinned to cores
1–6 at nice 5, with one replay thread. Each emitted 10,161 rows. The loop-only
control is **byte-for-byte identical** to the coordinator's
`/root/claude-ra/loops/all-on.jsonl`, SHA256
`251902084af33b536e2ce7572b6b03853d26d0bbb22533907ae7f72d2a63e4cb`.

| Stage | Variant | Programs | Instructions | True swaps | SAVE | FILL | Scratch sum, B |
|---|---|---:|---:|---:|---:|---:|---:|
| Fragment | Loops | 4,127 | 2,693,029 | 50,081 | 21,692 | 19,755 | 30,640 |
| Fragment | Combined | 4,127 | 2,674,233 | 51,907 | 13,572 | 11,589 | 30,640 |
| Vertex | Loops | 5,045 | 961,616 | 2,329 | 222 | 222 | 1,056 |
| Vertex | Combined | 5,045 | 961,616 | 2,329 | 222 | 222 | 1,056 |
| Compute | Loops | 989 | 1,593,965 | 1,282 | 414 | 813 | 608 |
| Compute | Combined | 989 | 1,593,965 | 1,282 | 414 | 813 | 608 |

Fragment delta: −18,796 instructions (−0.70%), +1,826 true swaps (+3.65%),
−8,120 SAVE, −8,166 FILL (−39.29% combined transfers), and −5,670 ordinary
copies. All 128 changed fragment rows have fewer instructions; none grows.
Swaps increase in 26 rows and are unchanged in the others. Every row retains
its GPR count and scratch size. Vertex and compute rows are entirely unchanged.
Scratch sums aggregate metadata across compiled programs; they are not runtime
memory consumption. These are static codegen measurements, not timing results.

The 346 at-cap fragment programs improve from 1,178,262 to 1,159,466 instructions;
swaps rise 44,777 → 46,603. All fragment changes are in this cohort. At-cap
counts stay 346 fragment / 22 vertex / 4 compute.

### Matching shader-library build settings

The first completed replacement, `all-v2-coalesce.jsonl`, used the
assertion-enabled CTS library. Its compute output differed even with coalescing
disabled: a sampled unspilled kernel had 648 instructions versus the reference's
606. NIR inspection traced this to assertions in the built-in CL shader library,
including image-addressing abort paths. This was unrelated to coalescing.

For the final CPU comparison, a separate `b_ndebug=true` build disables those
shader assertions (and native compiler assertions), matching the reference.
Both final variants use this same library, with only `AGX_SPILL_COALESCE`
differing. `NIR_DEBUG=novalidate` remains set for the known capture workaround.
The full identical loop-only control verifies the match, beyond the sample.
GPU CTS retained its assertion-enabled library and ran with `NIR_DEBUG` unset.

Final CPU library SHA256:
`21ae4ebd30c09e359312c7e34d1feffe4ff9454d9f0f5841367837e90772e1ee`.
ICD: `/root/claude-ra/codex-pressure/replay-release-driver/icd.json`.
The final combined JSONL SHA256 is
`d7d5f4593bd68ac0f89674f518f4077e861bb2fd675ba5242de6f7666f246421`.

Evidence in the local and mini `loop-comparison/` artifact directories:
`all-release-{loops,coalesce}.{jsonl,txt}`; local verification and per-stage
row comparisons are retained as `all-release-comparison.json`.

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
SAVE and FILL before calling the set spill validation. All six GPU sets have now
completed: see [CTS-20261005-V2.md](CTS-20261005-V2.md). Every variant passed
463/464 normal and 139/140 forced cases, with one common skip per set and zero
failures, crashes or flakes. Fifty passing cases in each forced run compiled
both SAVE and FILL, verified from that GPU run's own compiler output.

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

The deeper assignment/interference analysis and bounded allocator proposal are
in [PHI-WEBS.md](PHI-WEBS.md). No allocator placement change has been implemented.
