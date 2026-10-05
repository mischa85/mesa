# Uniform promotion budgets, T8132, October 5

Constant promotion now spends the uniform words remaining after
`nir_opt_preamble`. The assembled setup still has to fit the 8192-byte
compiler/driver policy bound. That number is not a measured hardware limit.
Oversized setup retains the existing fallback to the original main shader.

A host replay of all 10,161 selected CS2 outputs isolates removal of the old
64-promotion cap from `7e6bc8da2be`. The instrumented control reproduces every
baseline instruction, copy, swap, GPR, SAVE, FILL and scratch count exactly.
The cap removal changes the main programs as follows (candidate minus control):

| Stage | Instructions | Copies | Swaps | SAVE | FILL |
|---|---:|---:|---:|---:|---:|
| Fragment | -6190 | -578 | +616 | -64 | -52 |
| Vertex | -830 | -19 | +5 | 0 | 0 |
| Compute | 0 | 0 | 0 | 0 | 0 |

Reported GPR counts and scratch sizes are unchanged. The largest assembled
preamble is 3616 bytes. Of the 377 baseline outputs using 96 GPRs, 376 have a
preamble and exhaust the eligible repeated constants before exhausting either
uniform words or the code bound. One has no preamble. These observations do
not justify a larger-preamble hardware probe.

Local evidence: `tmp/cs2-pressure-20261005/uniform-census/budget-at-cap.json`
contains the shader/pipeline identity, words reserved by `nir_opt_preamble`,
word budget, eligible and promoted constants, and assembled setup bytes for
each at-cap output. `budget-whole*.jsonl` and `live-whole*.jsonl` retain all
outputs, including the 6100 preambles. Word reservations include alignment;
they must not be confused with a count of distinct uniform writes.

Focused host tests pass: promotion beyond 64 constants, the padded root-window
boundary through u255, uniform255 folding, and oversized-setup fallback.
Hardware validation of this cap-only change is pending; the paired uniform
source probes are separate from this whole-capture host measurement.
