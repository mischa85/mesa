# FTZ consumers and the remaining Lethal gap

2026-10-06. The first FTZ optimization, through `0cc8bfaa8b0`, measured
21.679 GPU ms/frame in Main's scene, versus 21.256 without FTZ and 24.124
with the original FTZ compiler. Main's fragment/compute times were
7.892/12.296 ms. Those are engine totals from one capture, not timings of
individual shaders. See workspace artifact
`artifacts/lethal-mechanism-20261006/MECHANISM.md`.

The native CTS and exact-bit validation below covers that **first, timed
optimization**. The subsequent consumer optimization and its combined
scoreboard driver have host validation only; their GPU time and native
correctness have not yet been measured.

## Native validation completed first

The mini lease was acquired, all tests ran with private native ICDs, and
the lease was released immediately after collecting the results. No driver
was installed, and no reboot was needed. Baseline and candidate match every
case's status:

| List | Pass | Skip | Fail | Expected fail | Flake |
| --- | ---: | ---: | ---: | ---: | ---: |
| Float controls, 4,196 cases | 3,328 | 868 | 0 | 0 | 0 |
| Focused normal | 463 | 1 | 0 | 0 | 0 |
| Forced spill | 139 | 1 | 0 | 0 | 0 |
| Memory | 1,034 | 1,019 | 0 | 0 | 0 |
| Robust descriptors | 915 | 400 | 0 | 0 | 0 |
| Total list entries | **5,879** | **2,289** | **0** | **0** | **0** |

All 42 authored shaders pass 66 exact-bit inputs in both default and FTZ
modes: 2,772 outputs per mode, all identical to baseline. There were no new
kernel log entries, and input forwarding remained active. Results, lists,
logs and per-case comparisons are under
`artifacts/ftz-codegen-20261006/hardware/`.

Native candidate SHA-256:
`e8402b2e30c034d18aa510eac40bf99221c3c58a45d47269c107f79ae6bac663`.
Baseline SHA-256:
`cc80df6f90c64880d274a528511b68d8f23d97f9d0d5e726466751f1907a88de`.

## Audit of all remaining checks

The timed compiler had 40 explicit checks in compute
`cs.deace2b1d0fc6801a441707df5e067bd`, and three in fragment
`fs.205919e9b91a146cac01c77f3384a2b0`. Every check is accounted for:

| Compute origin | Count | Disposition |
| --- | ---: | --- |
| Sine shortcut selects | 8 | Defer semantic canonicalization until the final pass; all feed DAZ multiplies directly. |
| Maxima with a positive normal lower bound | 13 | Cannot produce a subnormal; recover the constant through the preamble transfer. |
| Other maxima | 3 | Follow max/phi chains to DAZ consumers. |
| Minima | 9 | Follow sign/max/phi chains to DAZ consumers. |
| Reciprocals | 6 | Follow sign/select chains to DAZ consumers; no assumption about bare reciprocal input DAZ. |
| Negate | 1 | Retained conservatively at a clamp feeding exp2; see the ablation below. |

| Fragment origin | Count | Disposition |
| --- | ---: | --- |
| Maximum | 1 | The following minimum's independently retained check absorbs it. |
| Reciprocal | 1 | Its sign chain terminates in DAZ arithmetic. |
| Minimum | 1 | Retained: raw depth output can observe a subnormal. |

`artifacts/ftz-codegen-20261006/remaining-check-audit.json` records all 43
original SSA results, flush nodes, direct uses and dispositions. The change
removes 39 compute checks and two fragment checks.

The last compute check feeds `max(-x, 0)`, followed by exp2, as well as a
DAZ add. T8132 probes return one for exp2 of zeros and tested subnormals,
so a private ablation also lets exp2 absorb canonicalization. That removes
the last check but changes register allocation: compute spills rise from
67 to 83 and instructions rise from 5,889 to 5,895. This rule is therefore
excluded from the current candidate. The surviving compute check is a
conservative boundary, not evidence that this particular exp2 path requires
an explicit check. Its host ablation is retained as
`consumer-exp2-ablation-ftz.json`.

## General implementation

The original canonical-producer proof first chooses the checks without
following sign/min/max chains. A second pass then prunes a check only if
every downstream use reaches DAZ arithmetic or another retained check
through operations that commute with signed-zero canonicalization.
These include sign changes, min/max, saturation, value selects, moves,
vectors and phis. Integer conditions, raw stores, unknown operations and
unresolved cycles prevent pruning. A select's condition is not a value
transport edge.

Checks are pruned in stable NIR order. Each removal updates the retained
set immediately, so later proofs cannot rely on an already removed check.
This avoids circular reasoning between producer canonicality and consumer
elision. Raw uses of preamble stores still require canonical results.

For `max(x, positive-normal)` and `min(x, negative-normal)`, the bound alone
excludes a subnormal result. The proof handles each component and follows
compiler-generated constant uniform transfers. Zero, subnormal and NaN
bounds do not qualify; infinities do. No arbitrary uniform input is assumed
to be a constant. Sine lowering now leaves a semantic `fcanonicalize` until
the final FTZ pass instead of hiding it in integer classification too early.

No shader hashes, capture-specific constants, fixed register choices or
fast-math permission changes enter the implementation. The lower-bound
value `0x38d1b717` in this capture is merely one application of the general
constant-range proof.

## Counts, scheduling and uniform use

All following comparisons use the byte-exact reconstructed DXVK inputs,
the same fixed frontend and `AGX_SPILL_COALESCE=1`.

| Hot compute metric | No FTZ | Timed FTZ fix | Consumer fix | Consumer + scoreboard |
| --- | ---: | ---: | ---: | ---: |
| Instructions | 6,028 | 6,031 | **5,889** | **5,881** |
| Spill stores + loads | 131 | 67 | 67 | 67 |
| GPRs | 96 | 96 | 96 | 96 |
| Scratch bytes | 160 | 128 | 128 | 128 |
| Standalone waits | 151 | 134 | 137 | 129 |
| Immediate load–wait–load chains | 55 | 68 | 71 | **0** |
| Device-load wait distance, median instructions | 6 | 5 | 5 | 7 |
| Device loads waited within 8 instructions, of 270 | 176 | 205 | 212 | 141 |
| Main uniform references | 3,092 | 3,067 | 3,047 | 3,047 |
| Distinct uniform words | 229 | 229 | 229 | 229 |
| Preamble instructions | 521 | 521 | 521 | 521 |
| Preamble bytes / GPRs | 4,348 / 24 | 4,348 / 24 | 4,348 / 24 | 4,348 / 24 |

The almost identical 6,031 versus 6,028 static totals hide substantially
different placement and allocation. The timed fix has fewer spills but
more short load waits and more consecutive load retirement chains.
Uniform/preamble size is not growing in this comparison. The compute
contains 1,624 instructions inside its loop without FTZ, 1,587 with the
timed fix, and 1,509 with the consumer fix. Counts alone cannot establish
why the scene is 0.2 ms slower in compute.

The combined driver overlays the existing general oldest-pending-group
scoreboard fix from `apple9/memory-scoreboard` (`a0c562580db`). The default
allocator repeatedly retires slot 6 when all six slots are occupied. Load
address reads already happen at issue; these chains are not required to
protect address registers. Retiring the oldest pending group removes all
71 immediate chains here. Its eight removed waits are inside the hot loop.
This existing fix remains a separate overlay, not a second implementation
on the FTZ branch.

| Hot fragment metric | No FTZ | Timed FTZ fix | Consumer fix |
| --- | ---: | ---: | ---: |
| Instructions | 866 | 876 | **873** |
| GPRs | 23 | 26 | **24** |
| Spills | 0 | 0 | 0 |
| Texture sample-to-wait distances | 2, 43 | **2, 2** | **2, 42** |
| Main uniform references / distinct words | 289 / 52 | 281 / 52 | 281 / 52 |
| Preamble instructions / bytes / GPRs | 157 / 1,398 / 16 | 157 / 1,398 / 16 | 157 / 1,398 / 16 |

The consumer fix restores independent work between one fragment sample and
its wait, making latency overlap a concrete suspect for the residual
fragment gap. The scoreboard overlay does not change this fragment program.
Wait distances are linear static diagnostics, not cycles or measured GPU
latencies; conditional execution can change their dynamic interpretation.

Across the full reconstructed capture, main fragment instructions fall
3,046 → 3,022, versus 3,021 without FTZ. Main compute falls
24,358 → 23,949 (23,937 with scoreboard), versus 24,304 without FTZ.
Vertex counts remain 1,342. Two other compute shaders each gain one spill
store and one load: `1eedf1e59030d12f` goes 28 → 30 spills and
`9fec0a5bffe06df0` goes 30 → 32. Both additions are outside their loops;
their instruction counts fall 2,844 → 2,747 and 3,809 → 3,718. Total compute
spills rise 125 → 129. These tradeoffs need timing, not an assumed win from
instruction totals.

## Follow-up validation and handoff

The consumer change is committed on `apple9/ftz-codegen` as `e703376b8ae`
and `ff757102381`. All **454** compiler host tests pass, including raw-bit
escape, integer condition, phi, shared clamp check, reciprocal conservatism,
and signed normal/subnormal/NaN/infinity bounds through preamble transfers.

All 7,020 existing corpus outcomes remain unchanged, with no spill
increases or added waits against that corpus's integration reference:
6,995 pass, 20 pipeline-library entries have no shader, and five existing
Willems cases fail. These inputs differ from the explicitly FTZ-reconstructed
capture above, where the four extra spills are reported separately.
All 579 FTZ32 host entries without FP64 compile; the 201 mixed FP64 entries
retain their existing unsupported-FP64 failures.

Both new game drivers compile all 69 reconstructed Lethal pipeline entries
without failure and advertise FTZ32 plus float-controls2. They retain Main's
runtime overlays. Neither follow-up has native CTS or game timing yet.
The previously validated/timed driver is preserved unchanged.

Workspace artifact root:
`artifacts/lethal-regression-static-20261006/drivers/`.
Both entries are in the adjacent `driver-manifest.json`:

* `integration-ftz-consumers`, SHA-256
  `290eeb7e69b4821e12469542078b4974789420a5835398bce7b2619f765a6abe`.
* `integration-ftz-consumers-scoreboard`, SHA-256
  `5cacdfc3914a8e7e67858a26dc3e057f628cacde80f89f1ffef319ffd692f067`.

Detailed follow-up metrics are under `artifacts/ftz-codegen-20261006/`:
`consumer-fold-ftz.json`, `consumer-scoreboard-ftz.json`,
`consumer-stage-comparison.json`, `consumer-loop-counts.json`, and
`remaining-check-audit.json`. No follow-up GPU work was done after releasing
the lease, and nothing was pushed.
