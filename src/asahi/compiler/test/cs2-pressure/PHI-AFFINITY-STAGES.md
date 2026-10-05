# Staged phi-affinity changes

Baseline: loop handling plus spill-home coalescing, as recorded in
[LOOPS-COALESCING.md](LOOPS-COALESCING.md). All capture replays are CPU-only,
one replay thread, cores 1–6, nice 5. Each stage has an immutable isolated
driver. No GPU tests or production driver installation are part of these runs.

## Stage 1: private constant-use affinity members

Each `mov_imm` source of a phi gets a private union-find member for that incoming
use, instead of unioning the shared constant definition into the destination's
web. Its SSA source remains shared: no extra materializations, liveness changes,
or spill pressure. Ordinary source coalescing can still reuse its register.
This covers all `mov_imm` bit patterns and sizes, not just zero. `get_sr` is
rematerializable but is not a literal constant and is not included.

### Repro and graphics range [0, 200)

| Measurement | Combined baseline | Stage 1 combined |
|---|---:|---:|
| Repro instructions | 5,781 | 4,452 |
| Repro swaps | 485 | 120 |
| Repro ordinary copies | 959 | 718 |
| Repro SAVE / FILL | 191 / 157 | 191 / 157 |
| Repro GPRs / scratch | 96 / 272 B | 96 / 272 B |
| Range fragment instructions (172 outputs) | 117,463 | 114,764 |
| Range fragment swaps | 2,443 | 1,845 |
| Range vertex instructions (206 outputs) | 29,513 | 29,810 |
| Range vertex swaps | 47 | 141 |

Twenty fragment outputs shrink and 40 grow; one vertex output shrinks and five
grow. Range SAVE/FILL and every output's scratch size are unchanged. Stage 1
helps the repro substantially, but it is not a universal code-size improvement.

With coalescing disabled, the stage-1 repro has 5,034 instructions, 115 swaps,
387 SAVE / 354 FILL, and 272 B scratch. Coalescing's repro swap increment falls
from 44 to 5. Across this range, its fragment swap increment likewise falls
from 44 to 5; vertex output does not depend on coalescing.

The assignment trace verifies the change in web structure. Candidate 10's
largest web shrinks from 1,021 to 261 SSA definitions. Comparing its membership
with the retained SSA interference graph finds 3,139 internally interfering
pairs in that remaining web, so constant isolation alone does not solve the
interference problem.

### Validation and provenance

All 15 focused `Apple9SharedRa.*` / `Apple9Spilling.*` host tests pass with native
assertions enabled. The new shared-initializer test executes eight independent
loop values for five iterations, testing zero, small, floating-bit-pattern and
large integer initializers. The four `Apple9Spilling.*` tests also pass with
forced spilling. The additional forced `PhysicalSpillLowering...` test reaches
its existing zero-scratch expectation and fails it (320 B versus zero); that
test is not counted as a passing forced test.

The CPU replay uses the same release shader-library settings as the matched
baseline. Library SHA256:
`dd1b9e75823fb3fbe6e63716373ee1d218d70da9f688a4aecca950315059c20a`.
ICD: `/root/claude-ra/codex-pressure/phi-stage1-driver/icd.json`.
Evidence: `stage1-range-{coalesce,loops}.jsonl`, corresponding summaries,
and `stage1-105-webs.log` in the local/mini `loop-comparison/` directories.

### Whole capture

Both runs contain 10,161 rows and finish with replay/parser exits 0/0 (454 s
combined, 481 s loops). Against the previous combined baseline:

| Stage | Instructions | Delta | Swaps | Delta | SAVE / FILL | Scratch sum, B |
|---|---:|---:|---:|---:|---:|---:|
| Fragment | 2,625,855 | −48,378 | 41,832 | −10,075 | 13,572 / 11,589 | 30,640 |
| Vertex | 971,389 | +9,773 | 5,611 | +3,282 | 222 / 222 | 1,056 |
| Compute | 1,592,632 | −1,333 | 1,000 | −282 | 414 / 813 | 608 |

SAVE/FILL and every output's scratch are unchanged. Fragment instruction counts
shrink/grow in 400/902 rows, vertex in 32/120, and compute in 266/381. GPR counts
also change in a few outputs (lower/higher: fragment 16/13, vertex 2/0, compute
10/27); at-cap counts remain unchanged. Static instruction total improves by
39,938 across all stages, with a material vertex regression.

The matched stage-1 loop-only run has 2,648,555 fragment instructions and 41,550
swaps. Therefore coalescing's whole-capture swap increment falls from **1,826 to
282**, rather than disappearing. It saves 22,700 fragment instructions and the
same 16,286 transfers. Compared with stage-1 loops, 128 fragment outputs shrink
and 16 grow; vertex and compute rows are identical. This paired comparison is
separate from the stage-1-versus-previous-combined comparison above.

Artifacts: `stage1-all-{coalesce,loops}.{jsonl,txt}`,
`stage1-all-comparison.json`, and `stage1-all-coalescing-increment.json`.

## Stage 2: noninterfering affinity classes

Build a sparse interference graph for phi participants from post-spill SSA
liveness, treating phi destinations as simultaneous entry writes and their
sources as predecessor-edge uses. Before a union, inspect all members of the
smaller class for conflicts with the other class. Refuse the union if any pair
interferes, or if the phi operands' storage class/width differs. This checks
transitive class interference, not merely the immediate source/destination pair.
The classes remain soft allocation preferences; no hard SSA merging is done.

| Measurement | Previous combined | Stage 1 | Stage 2 |
|---|---:|---:|---:|
| Repro instructions | 5,781 | 4,452 | 4,134 |
| Repro swaps | 485 | 120 | 36 |
| Repro ordinary copies | 959 | 718 | 651 |
| Range fragment instructions | 117,463 | 114,764 | 110,054 |
| Range fragment swaps | 2,443 | 1,845 | 789 |
| Range vertex instructions | 29,513 | 29,810 | 29,733 |
| Range vertex swaps | 47 | 141 | 118 |

The repro retains 191 SAVE / 157 FILL, 96 GPRs and 272 B scratch. Versus stage 1,
all 28 changed fragment and seven changed vertex outputs in the range shrink.
No range output grows scratch. Against the original combined baseline, however,
22 fragment and five vertex outputs still grow.

With coalescing disabled, the stage-2 repro has 4,685 instructions, 34 swaps,
387 SAVE / 354 FILL, 272 B scratch. Coalescing therefore adds two repro swaps.

All 16 focused host tests pass with assertions enabled, including independent
loop values sharing a computed initializer. The assertion-enabled allocator
checks that no interference edge ends inside one class. Independently, all
3,818 candidate-10 GPR definitions were grouped using the emitted assignment
trace and checked against the earlier offline interference graph: zero internal
interfering pairs, with the largest class containing 25 values.

CPU library SHA256:
`b2829915b52087d1d5dcae7d7fb06f79835d9091708e608a8a3c0a30561c8c28`.
ICD: `/root/claude-ra/codex-pressure/phi-stage2-driver/icd.json`.
Artifacts: `stage2-range-{coalesce,loops}.jsonl`, `stage2-range-comparison.json`,
`stage2-range-increment.json`, and `stage2-105-webs.log`.

### Whole capture

The 10,161-row replay finishes with exits 0/0 in 453 s. Against the previous
combined baseline:

| Stage | Instructions | Delta | Swaps | Delta | SAVE / FILL | Scratch sum, B |
|---|---:|---:|---:|---:|---:|---:|
| Fragment | 2,527,738 | −146,495 | 20,051 | −31,856 | 13,572 / 11,589 | 30,640 |
| Vertex | 969,154 | +7,538 | 5,061 | +2,732 | 222 / 222 | 1,056 |
| Compute | 1,592,267 | −1,698 | 914 | −368 | 414 / 813 | 608 |

Compared with stage 1, this removes another 100,717 instructions and 22,417
swaps across stages. Fragment instructions shrink/grow in 641/8 rows, vertex
in 202/4, and compute in 61/2. Against the original combined baseline those
counts are 852/446, 150/120, and 269/381, respectively. The vertex total is
still worse than baseline. Every output retains its SAVE/FILL and scratch;
two fragment outputs fall below the 96-GPR cap. GPR lower/higher counts versus
baseline are 35/13 fragment, 18/2 vertex, and 10/31 compute.

Artifacts: `stage2-all-coalesce.{jsonl,txt}`, `stage2-all-comparison.json`,
and `stage2-all-vs-stage1.json`.
