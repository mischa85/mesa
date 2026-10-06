# Load-latency scheduling

2026-10-06, branch `apple9/load-latency` on `apple9/literal-constants`.

## Problem

Apple9 already builds a latency-aware pre-RA schedule (memory/texture/spill
loads separated from their consumers by 16 issue positions) and compares it
with the pressure schedule. In practice it rarely survived:

- `agx_pressure_schedule` discarded a block's reorder whenever it raised the
  block's peak pressure at all, so overlapping two loads (one extra live
  result) was never allowed.
- Candidate comparison ranked dependency gaps after instructions, bytes and
  registers, so any extra move or register lost.

Static evidence (`AGX_APPLE9_ASM`, own tooling `latmetrics.py`): in CS2 3,497
of 5,163 device-load waits came within two instructions of the load; 1,103 of
those were followed by a load that did not depend on it (conservative vector
taint), i.e. independent memory accesses issued one at a time.

## Change

- `schedule_pressure_slack`: a latency schedule may raise a block's peak by up
  to 16 half-registers (8 GPRs). Dependency edges are unchanged: loads stay
  ordered behind stores, atomics, fences and volatile loads.
- Latency candidates (slack 0 and 16, both bank policies) are compared by
  spills, then the occupancy-proxy tier, then 4×issued + modelled gap slots.
  Apple9 occupancy is unmeasured; Apple8 halfreg granules stand in, judged on
  peak live registers, and a candidate that adds registers may not reach the
  boundary of its tier.

Unit tests: `ResourceSchedule.PressureSlackOverlapsIndependentLoads`,
`ResourceSchedule.PressureSlackKeepsLoadsBehindMemoryWriters` (aliasing store,
atomic, full fence).

## Static results vs literal-constants

| | CS2 | Willems | Lethal | vkmark |
|---|---|---|---|---|
| short (≤2) load waits | 3,497 → 1,905 | 802 → 563 | 724 → 700 | 27 → 27 |
| independent serialised loads | 1,103 → 503 | 71 → 20 | 258 → 251 | 0 → 0 |
| mean wait distance | 1.62 → 2.78 | 1.76 → 2.47 | 2.04 → 2.14 | 1.64 → 3.34 |

No spills added, no outcome changes, no proxy tier losses; one CTS program
reaches a boundary. Instructions within ±0.1%, GPR sums +1–6% inside tiers.
Lethal's hot compute kernels are at the 96-GPR cap (each device load also
needs private address copies), so they need pressure reduction before overlap
is possible. No measurable backend compile-time change.

Static counts are not GPU time; CS2 (primary) and Lethal (no-regression)
timings are pending.
