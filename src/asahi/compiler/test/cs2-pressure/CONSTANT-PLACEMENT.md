# Constant materialization placement

Placement change: `7e6bc8da2be`, measured against direct-SAVE commit
`caf135c0d93`. All work here is host-only. The mini remains reserved for the
main thread; neither change has received GPU validation in this phase.

## Policy

The target describes the directly encodable MOV_IMM destination range in
half-registers (128 for Apple9, corresponding to r0–r63). Placement charges one
materialization move outside that range. Existing direct phi-edge, compatible
class, collect and operand-bank preferences take priority over this charge;
register footprint and bank scarcity follow it. A free low register therefore
wins over speculative scarcity when the established preferences are tied.
Already allocated values are not treated as new materializations during an
eviction. Targets without this restriction retain the previous policy.

No allocation trial is added. Existing completed-allocation selection includes
all later phi reconciliation, shuffles, spill lowering and completion waits.
A locally preserved preference is not a guarantee of unchanged later edge
costs: changed assignments can alter future choices. The measurements below
include those costs rather than assuming each removed bridge is a net win.

## Whole-capture placement result

All 10,161 outputs completed successfully. Baseline is the frozen host
**direct-SAVE** replay, not stage four or a mini replay.

| Stage | Outputs | Instructions delta | Ordinary copies delta | Swaps delta | Outputs smaller / larger |
|---|---:|---:|---:|---:|---:|
| Fragment | 4,127 | −43,535 | −43,056 | +223 | 743 / 8 |
| Vertex | 5,045 | −7,833 | −7,715 | −72 | 64 / 2 |
| Compute | 989 | −14,802 | −13,843 | −213 | 477 / 24 |
| Total | 10,161 | **−66,170** | **−64,614** | **−62** | 1,284 / 34 |

Every output retains its SAVE count, FILL count and scratch size. Registers
change: 69 fragment outputs grow by 1–4 GPRs; vertex has 15 increases (2–8)
and three decreases; compute has 243 increases (1–12) and 24 decreases. Five
compute outputs newly reach 96 GPRs, moving that population from four to nine.
Fragment and vertex populations at 96 stay 346 and 22. These register changes
need runtime validation; static instruction savings do not establish a timing
win. The maximum instruction growth per output is 10 fragment, 4 vertex and
11 compute instructions. All changed outputs and their pipeline hashes are in
`constant-placement-deltas.csv`.

## Where the copies went

The diagnostic census is **byte-identical in every main-program metric** to
the non-instrumented placement replay. It also retains 6,100 separately counted
preambles. Categories sum to the emitted ordinary-copy count per program.
The pre-placement census comes from stage four; direct-SAVE removes only its
previously measured SAVE-staging copies (7,664 / 222 / 414), with other
categories and assignments unchanged. This normalization gives the direct-SAVE
baseline used here.

| Fragment copy source | Direct-SAVE baseline | Placement | Delta |
|---|---:|---:|---:|
| High constant materialization | 41,906 | 368 | −41,538 |
| Original phi edges | 73,256 | 76,186 | +2,930 |
| Spill-repair phi edges | 6,443 | 5,435 | −1,008 |
| Live-in reconciliation | 3,280 | 1,661 | −1,619 |
| Constrained operands | 6,570 | 4,841 | −1,729 |
| COLLECT | 3,804 | 3,708 | −96 |
| SPLIT | 42 | 46 | +4 |
| Live-source SAVE staging | 5,828 | 5,828 | 0 |
| Publication writes | 4,922 | 4,922 | 0 |
| Selected identity copies | 36 | 36 | 0 |

Original fragment phi copies grow by 2,300 at joins, 384 at loop entries and
246 on backedges. Including repair and live-in copies, fragment phi-related
copies grow by only 303. The 223 extra swaps cost 669 XOR instructions; they
are already included in the net instruction result. Remaining scheduling and
encoding changes are also included; they are not all labelled as WAIT changes.

The earlier 36,853 count described free low registers under frozen assignments.
Changing placement also changes later availability, so its 41,538 removed
bridges need not be bounded by that fixed-assignment opportunity count.
Vertex high-constant bridges fall 7,594 → 0; compute falls 13,536 → 8.
Only 27 outputs retain any such bridge: 24 fragment and three compute.
Eight related fragment outputs account for 352 of the remaining 368 fragment
bridges (44 each).

## Rematerialization alternatives

All three alternatives completed the same whole capture with 10,161 outputs
and successful exits. Their deltas below are **against placement alone**.
None is included in the production compiler change.

| Alternative | Fragment instructions | Vertex instructions | Compute instructions | Total |
|---|---:|---:|---:|---:|
| Bounded near-use localization | +17,290 | +1,939 | +13,892 | +33,121 |
| Only constants high in the first allocation | +5,160 | +23 | +2,475 | +7,658 |
| Only constants still high after bank-aware placement | 0 | 0 | 0 | 0 |

The first policy shortens constant live ranges when pressure exceeds the direct
immediate bank: single-use constants move across blocks to their use, and
constants used by at most two distinct instructions are rematerialized beside
those instructions. Repeated operands in one instruction share the new
materialization. It leaves phi operands intact and does not move definitions
into deeper loops. It adds 80 SAVE and 16 FILL instructions, despite unchanged
scratch sizes, and is rejected.

The second policy records which original constants were actually placed above
r63 in the existing initial allocation. Only these values are eligible for the
same bounded localization in subsequent bank-aware allocations. It adds no
allocation trials and leaves spill traffic unchanged, but its instruction
increase still outweighs 790 fewer copies. It is also rejected.

The third policy first performs the normal bank-aware placement and considers
only its remaining high constants for localization in the existing
latency-aware bank allocation. It preserves the earlier candidates and adds no
trial. Every final per-output metric is identical to placement alone: no extra
gain was found under these restrictions. This does not establish that all forms
of rematerialization are unprofitable; unbounded duplication, phi-edge
rematerialization and deeper-loop motion were not enabled.

The first two alternatives also pass the 240-test native host suite outside
`Apple9Compiler.*`. They remain external experimental overlays, not dormant
compiler flags or capture-specific production machinery.

## Host tests

240/240 tests outside the previously excluded `Apple9Compiler.*` suite pass,
as do all four forced-spill `Apple9Spilling.*` tests. Two new allocator tests
check that direct materialization beats mere bank scarcity while respecting a
high operand-bank preference and a known high-register phi-edge preference.
The first test fails against the direct-SAVE allocator; both pass with placement.
The unrelated pre-RA `WritableSinkPointer` assertion remains the reason for the
existing compiler-suite exclusion; no passing claim is made for that suite.

Evidence is in `tmp/cs2-pressure-20261005/constant-placement/`, with immutable
host drivers under `vertex-analysis/drivers/`. Main metrics and mappings are
`vertex-analysis/constant-low-host{,-mapping}.jsonl`; source attribution is
`copy-analysis/constant-low-whole-census.jsonl` and
`constant-placement/copy-attribution-comparison.json`. Fake G16 DRM is used for
host compilation; these replays submit no GPU work.

The evidence bundle is
`tmp/cs2-pressure-20261005/constant-placement/constant-placement-host.tar.gz`.
Build scripts depend on the existing workspace toolchain and support libraries;
the bundle is not a portable build environment.
