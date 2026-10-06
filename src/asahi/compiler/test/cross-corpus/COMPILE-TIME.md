# Apple9 backend compile time

2026-10-06, on integration-next `a1bd178709d` (literal-constants and
load-latency included). Host only; GPU code is unchanged.

## Method

- Profiling: no `perf` on the host, so a small `LD_PRELOAD` SIGPROF sampler
  (`backtrace()` every 2 ms, symbolized offline with `nm`) plus a temporary
  per-allocation-candidate timer.
- Timing: `latency/ctime.py` sums the instrumented compiler's `CORPUS_TIME`
  (thread CPU) per population, one process at a time on a pinned core, two
  repeats. Large GS go through the private pre-rasterization adapter
  (`build-prerast-adapter.py`).
- Equality gate: `latency/identity.py` hashes every compiled program's
  instruction bytes (`AGX_APPLE9_ASM`) per entry. Every change below matches
  the previous tip for all entries of the large-GS (5), Lethal (69), Willems
  (268), vkmark (17), CTS (768), CS2 sample (160) and robust (5,738)
  populations.

## Findings and changes

On the worst large GS (`72acdaeb…-3`, 14.9 s) 82% of the time was complete
register-allocation candidates: twenty runs of ~0.68 s (two preamble
placements × base/bank, four latency and four non-rematerializing spill
retries). Within a run: spilling 43%, SSA repair 18%.

1. **Duplicate candidates.** Skip a non-rematerializing spill retry when its
   rematerializing counterpart marked nothing; skip the slack-16 latency
   candidate when slack 0 rejected nothing it would admit; abort any
   candidate whose scheduled IR plus policy inputs repeat an evaluated one.
   Full allocations on the five large GS: 86 → 54.
2. **`apple9_chase_trivial`** chased both addition operands recursively to
   test for zero: exponential on addition chains/DAGs. A short-circuit zero
   predicate takes the large GS from 36.5 to 26.2 s on its own.
3. **Fallback block emission** scanned and copied every VIR instruction for
   each block emitted directly from VIR; now bucketed per block.
4. **Phi register preferences** are indexed by register instead of scanned
   for every candidate register (spill-memory locations keep the scan; the
   first version indexed them too and crashed only on the large GS, which the
   equality gate caught).

| Backend CPU (s) | Before | After |
|---|---:|---:|
| Five large GS | 51.5 | 24.0 (−53%) |
| CTS stratified 768 | 16.56 | 13.39 (−19%) |
| Willems | 1.30 | 1.155 (−11%) |

## Remaining

The CTS profile is now led by constrained placement (`place_constrained_value`
/ `placement_cost`, ~20%), NIR algebraic optimization (~10%) and
`apple9_legalize_buffer_accesses` (~8%). An exact early exit for constrained
placement is possible when a candidate reaches the minimum of every ranked
cost field. Exact pruning by an allocation lower bound, and skipping the
second preamble placement, need a provable bound first.
