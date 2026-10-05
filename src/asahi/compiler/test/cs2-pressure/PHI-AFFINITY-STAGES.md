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
