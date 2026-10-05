# CS2 pressure audit — 2026-10-05

The first fix is a one-character correctness repair in SSA cleanup, not an
allocator redesign. On the isolated CS2 repro it removes **53.6% of true swaps,
28.7% of SAVE/FILL instructions, and 31.6% of instructions**. These are CPU
compilation results; GPU correctness and game performance are not yet tested.
All mini CPU work was pinned to cores 1–6 at nice 5. GPU execution and resets
remain subject to the coordinator's explicit release.

## Reproduction and the fix

Branch: `apple9/cs2-pressure-audit`, based on `7cdd167efdf`, the coordinator's
compiler plus the eager stage-separate fragment replay fix. Commits:

- `f62aa2b3613`: opt-in phi/copy diagnostics, no allocation changes.
- `f9d595251e1`: restore trivial-phi cleanup, with regression tests.

The single graphics pipeline range is `105 106` in
`/root/claude-foz/cs2/steamapp_pipeline_cache.foz`; disable compute with range
`0 0` when reproducing. Use `/root/claude-foz/fossilize-replay --num-threads 1`,
`HK_APPLE9_EAGER_VARIANTS=1`, `HK_EXPERIMENTAL_APPLE9=1`,
`FOSSILIZE_IGNORE_LAYOUT_SUPPORT=1`, `MESA_SHADER_CACHE_DISABLE=true`, and
`AGX_APPLE9_STATS=1 AGX_APPLE9_ASM=1 AGX_APPLE9_TRACE=1`. Add
`AGX_APPLE9_RA_AUDIT=1` only for attribution. The fragment source hash printed
by NIR is `{0x171609e9, 0xcb2e0821, 0x89c40ec0, 0x353c6569, 0xf8b4a0d6,
0x3516f34f, 0xd0feb42f, 0xa5918dee}`.

`agx_opt_trivial_phi()` initializes its remap table to null. The constant-source
guard change in upstream `e4520b1ddaa` accidentally rejected **null** remaps,
so normal inputs could never start cleanup. Restoring the negation rejects
already-remapped inputs while preserving the type check before indexing.
It removes both redundant GPR and memory phis created by spill SSA repair.

| Heavy fragment main | Baseline | Fixed | Change |
|---|---:|---:|---:|
| Instructions | 11,759 | 8,041 | −31.6% |
| Code bytes | 106,264 | 70,686 | −33.5% |
| True swaps | 1,584 | 735 | −53.6% |
| XOR instructions implementing swaps | 4,752 | 2,205 | −53.6% |
| SAVE | 645 | 443 | −31.3% |
| FILL | 782 | 575 | −26.5% |
| SAVE + FILL | 1,427 | 1,018 | −28.7% |
| WAIT | 1,010 | 699 | −30.8% |
| GPR extent / scratch bytes | 96 / 288 | 96 / 288 | unchanged |

Instrumentation reproduces the baseline binary exactly (SHA-256
`45e38a325ce5f9fc23a35f61e1481ca8986a0ea2cf9cab88bd14956cf351bf66`).
The fixed allocator selects candidate 10 instead of baseline candidate 8;
attribution below follows the candidate whose counts match emitted code.
Counts are static instructions, not dynamic execution counts or frame time.

## What produces the remaining 735 swaps

Every baseline and fixed true swap is emitted by
`agx_insert_parallel_copies()` for a phi edge. The local constrained-operand
assignment path emits **zero swaps** (25 baseline / 32 fixed ordinary moves).
That rules out local eviction swaps as the direct source, although constraints
and placements can still cause incompatible register assignments at joins.

| Fixed GPR cycle membership | Cycles | Swaps |
|---|---:|---:|
| Original phis only | 16 | 98 |
| Spill-repair phis only | 103 | 243 |
| Original + spill-repair | 25 | 309 |
| Live-in reconciliation + spill-repair | 1 | 23 |
| All three | 4 | 62 |
| **Total** | **149** | **735** |

Each parallel-copy cycle of length N requires N−1 swaps with the current
lowering; reconstructing the cycles exactly reproduces the emitted count.
The largest is edge `30 -> 32`, loop depth 1: 52 words, 51 swaps, 153 XORs.
Edges `152 -> 154` and `87 -> 89` contribute 43 and 33 swaps. The largest pure
repair cycles include `41 -> 42` (14 swaps) and `153 -> 154` (10 swaps).

| Loop nesting depth | Swaps | Phi-copy SAVE | Phi-copy FILL |
|---|---:|---:|---:|
| 0 | 112 | 32 | 32 |
| 1 | 401 | 5 | 5 |
| 2 | 209 | 164 | 164 |
| 3 | 13 | 0 | 0 |

Thus 623/735 swaps (84.8%) remain inside loops. The CFG has ten natural loops.
These depths come from postspill CFG backedges, not nearby opcode heuristics.

The fixed program still has 771 spill-repair phis (646 GPR, 125 memory), down
from 4,520 (2,632 GPR, 1,888 memory). An offline SCC check finds no remaining
repair-only component with a single external value, so another trivial-phi
cleanup is not the obvious next gain. The 3,743 synthetic live-in reconciliation
phis inserted later mostly preserve placement: only 15 GPR word mismatches and
zero memory mismatches are attributable to them.

### Spill slots are the clearest next target

Phi-edge memory copies alone emit **201 SAVE + 201 FILL** after the fix, down
from 391 + 391. There are 172 mismatched memory word inputs: **152 repair inputs
and 20 original-phi inputs**. Six cycles contribute 35 abstract memory swaps;
the rest are acyclic moves. The copy lowering materializes these through GPRs.

Tracing pre-repair variable identity through SSA reindexing proves that **all
152 repair mismatches join versions of the same original memory variable**.
They involve 32 original spill homes. All 20 original-phi mismatches merge
different homes. GPR repair edges similarly have 953 mismatched words referring
to the same original GPR variable; these are distinct materializations/versions,
not necessarily redundant SSA values.

There are 120 distinct surviving memory homes, whereas current allocation
packs them into 72 frame words (288 bytes). Giving every home a permanent slot
would cost at least 480 bytes for scalar words, so a useful implementation must
preserve interference-aware reuse. Stable identity is a coalescing preference,
not permission to alias simultaneously live versions or increase scratch blindly.

## Metal comparison: useful loop evidence, no conditional-join evidence

The 33 authored Metal programs from the prior operand survey contain one
zeroing loop each; they hold loaded values across it and then consume them.
They **do not contain comparable floating-point if/else phi joins**. None of
the float compute/vertex/fragment bodies has a register-XOR swap storm.
No observed SAVE or direct frame IADD lies inside a loop.

| Native fragment pressure | SAVE before loop | Direct frame IADD before loop | FILL before / inside / after | Frame words unchanged across loop and read afterward |
|---|---:|---:|---:|---:|
| 88 | 8 | 0 | 0 / 0 / 8 | 8 |
| 128 | 40 | 0 | 0 / 0 / 40 | 40 |
| 160 | 84 | 0 | 0 / 0 / 84 | 84 |
| 256 | 181 | 37 | 37 / 1 / 180 | 180 |
| 512 | 445 | 94 | 95 / 0 / 444 | 444 |

SAVE totals include the compact and source-retaining candidate forms identified
in the operand survey. The vertex-512 loop has four retained FILLs for words
0–3; fragment-256 has one for word 0. These are address/control reloads, not a
loop-wide reshuffle of the spilled floats. Vertex-512 keeps 434 frame words
unchanged across the loop; compute-512 keeps 437.

This demonstrates stable frame residency across a backedge for loop-invariant
values. It does **not** demonstrate how Metal coalesces branch-produced values
at a conditional join. A matched authored shader with branch-produced long-lived
values and a loop-carried phi is needed to make that comparison. The observed
96-GPR extent and integer frame destination do not establish a universal limit
on all Metal shaders or rule out unobserved hardware forms.

## Proposed next changes and bounded estimates

No large allocator change has been implemented.

1. **Preserve spill-home identity and coalesce memory phis.** Carry an original
   home tag through SSA repair and use it when allocating frame slots. Merge
   compatible memory-phi webs only when liveness permits; prioritize loop edges.
   The measured target is the 152 same-home word mismatches. If these disappear
   without creating other copies, the remaining 20 original word edges require
   roughly 20–40 SAVE/FILL pairs with the present move/swap lowering, versus 201
   now. That is an optimistic **322–362 fewer transfer instructions**, or
   31.6–35.6% of the fixed repro's 1,018 transfers. It is a traffic ceiling under
   unchanged spill decisions, not a measured allocator result or speedup.
2. **Coordinate reload destinations with hot phi edges.** The current phi web
   has one preferred register, used by `pick_regs()` only when available;
   `reserve_live_in()` and predecessor placement can create incompatible maps.
   Favor loop/backedge agreement and place a reload into the successor's chosen
   register when legal. The isolated repair-only cycles account for **243 swaps
   (729 XORs, 9.1% of fixed instructions)**; another 394 swaps mix repair with
   other phis. These are attribution targets, not additive guaranteed savings.
   Even deleting every cycle touching repair would leave the 98 pure-original
   swaps, and original merges are not necessarily unoptimizable either.
3. **Make loop spill/reload choices account for edge-copy cost.** Inspect
   `compute_w_entry_loop_header()`/`compute_w_entry()` and coupling against the
   repeated depth-2 memory shuffles. Prefer keeping a cold loop-invariant value
   in its stable frame slot until use; avoid giving a branch-local reload a long
   live range through a join. Trade reload frequency against pressure and
   occupancy, rather than hoisting every reload. No separate numerical estimate
   is justified yet; this overlaps the first two targets.
4. **Validate compact/source-retaining SAVE separately.** A compact 4-byte SAVE
   can save six code bytes per eligible replacement of the 10-byte form; it does
   not by itself remove transfers or swaps. A retaining form may avoid an extra
   copy of a still-live source. Eligibility in this repro is not yet counted,
   and both encodings need execution validation before compiler use. Direct
   frame IADD is primarily an integer/address producer optimization; the corpus
   gives no validated direct FP frame destination that removes FP spill traffic.

## Validation and scheduled GPU work

The focused CPU suite `RepairSSA.*:Apple9SharedRa.*` passes all 15 tests after
the fix. With the baseline cleanup, the new diamond and invariant-loop tests
fail, while the constant-source guard test passes. The diamond includes register
and memory variants. The full unit binary hits
`Apple9Compiler.WritableSinkPointer`: NIR divergence analysis rejects
`ro_to_rw_poly` **before allocation**. Rebuilding the baseline compiler and
running that exact test reproduces the assertion; it is pre-existing.

Whole-capture baseline and fixed replays also both hit an unrelated NIR texture
destination component-count validation failure in graphics pipeline 6
(`006206bc9c960e6c`), after reassociation and before allocation. Both were
restarted with `NIR_DEBUG=novalidate`; register-allocation validation remains
enabled. Results from those replays must carry this qualification.

The two full CPU replays are currently externally paused with SIGSTOP for the
other thread's measurements. Whole-capture stage totals remain pending.
`aggregate-replay.py` streams without loading a dump whole, counts true swap
triplets via the coordinator's decoder, reports separate SAVE/FILL totals, and
checks stage/source-hash multisets. Its `at96` cohorts select each compiler's
outputs independently; cohort-size changes must not be described as paired
shader reductions. The coordinator's original `stream-compare.py` is also
available for cross-checking aggregate totals.

The CTS kit is prepared but **has not run**:

- `cts/normal.txt`: 464 cases covering OpPhi, loop/selection controls, generic
  and nested/control-flow loops, functions, conditionals, and switch.
- `cts/forced-spill.txt`: 140 focused cases with `AGX_MESA_DEBUG=spill`, exercising
  the shared allocator's forced 24-half-register bound. Verify actual SAVE/FILL
  activity from stats rather than assuming every case spills.
- `run-cts.sh --execute ICD normal|forced-spill OUT JOBS`: explicit execution,
  isolated driver, fresh results, existing CI skips/flakes, 60-second test
  timeout and max-fails 20. It clears `NIR_DEBUG`, so the replay validation
  workaround is not silently applied to correctness tests.

Run baseline and fixed selections during the released slot, compare failures
with baseline, and keep skips, expected failures, and flakes separate. The
295-case frame-destination probe remains built in its separate immutable
`/root/claude-isa-probe/frame-probe/` directory; later compiler rebuilds have not
replaced that library. No GPU API probe, CTS run, or reset has occurred here.

## Retained evidence

Host logs/results: `tmp/cs2-pressure-20261005/` in the workspace, including
`baseline-105.log`, `fixed-105.log`, `audit-summary/`, `fixed-summary/`,
`home-105.log`, `home-summary/`, `metal-cfg.json`, and `repro-totals.json`.
Mini logs/builds: `/root/claude-ra/codex-pressure/`, with isolated `driver/`,
`fixed-driver/`, and `home-driver/` directories. Scripts here recreate the
attribution from logs; the large logs are intentionally not committed.
