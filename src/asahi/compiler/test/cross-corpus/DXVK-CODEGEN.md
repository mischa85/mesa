# DXVK code generation on Apple9

2026-10-06, T8132 / Apple M4 G16G. Baseline compiler `d427e44dffa`;
retained compiler `90415b1fa8c` (same compiler code in final runtime
`bdc96e8eaad`). This compares static compiler output, not
frame times. The descriptor optimization is general; no capture identifiers or
fixed register assignments enter the compiler.

## Findings and payoff

| Priority | Pattern and evidence | Payoff / action |
| --- | --- | --- |
| 1 | Large constant-buffer indexing plus robustness checks: five captured modules declare `vec4[4096]` (64 KiB) constant buffers. The largest compute shader has 1,298 selects and 277 device-load records before this work. | Implemented exact buffer-size limits, shared through CSE and the preamble, plus constant field-offset folding with a no-wrap proof. On top of descriptor hoisting, this removes **814 main records**; it adds two SAVE/FILL pairs across two already spilling shaders. Bounds behavior stays enabled. |
| 2 | Uniform descriptor reads inside branches cannot enter the straight-line preamble. The three spilling Lethal Company compute pipelines repeatedly load descriptors and reconstruct addresses. | Implemented safe hoisting of uniform dependency chains for reads explicitly marked reorderable and speculatable. The descriptor-only ablation removes 18 SAVE and 18 FILL records (219 → 183) and 96 main records. |

The retained combined change reduces Lethal Company from 28,637 to **27,727
main records (3.2%)** and from 219 to **187 spill operations (14.6%)**.
Inline wait annotations fall by 80; standalone WAIT records rise by eight.
Preambles grow by 181 records / **1,388 bytes** across the corpus. The four
capped kernels and three spilling kernels remain the same. No frame-time
improvement is claimed.

The bound rewrite is exact for empty/short buffers and overflowing last-byte
offsets: `min(offset, UINT_MAX-k) + k < size` becomes
`offset < max(size, k) - k`. The size-side expression can be shared across
accesses and computed once for a uniform descriptor. A field displacement can
join `k` only when its original 32-bit addition cannot wrap: `x*16+12` permits
this, while `x*16+16` does not for unrestricted `x`. No bounds are rounded up and
no actual guarded buffer read is speculated.

A compile-only run with robustness disabled removes 3,468 main records
(**12.1%**) and 2,028 preamble records from the original baseline. This is an
upper bound on the whole robustness-related opportunity, not an implementable
saving: spills worsen from 219 to 334. It is not a production mode or an
estimate of GPU time.

The retained change is not universally better. One already spilling Willems
geometry shader's generated vertex kernel gains one SAVE/FILL pair, with
unchanged 96-GPR extent and 16-byte scratch allocation; its main records fall
from 787 to 744. Some CTS kernels grow: 80 in the timing sample (largest increase
24 records), and 23 in the focused robustness population (largest increase 32).
There are no newly capped or newly spilling kernels in the measured populations.
Broader uniform-ALU and guarded-address hoisting trials were removed after they
created substantial spilling in CTS stress shaders; they are not in the final
compiler.

Bitcasts themselves are not a code-generation problem here: the 51 modules
contain 272 `OpBitcast` instructions, represented as SSA aliases. Real bit
packing is present (nine `OpBitFieldUExtract`, sixteen `OpBitFieldInsert`,
plus shifts and logic). Compute pipeline `38d4f7f2c7e2984e` has 721 unsigned
right-shift, 431 left-shift and 515 OR records in 5,602 main records, at 80 GPRs
without spills. Those counts also include address/boolean lowering and copies;
they are not all packing overhead. A fused arbitrary-width packing operation
needs a generalized, validated machine encoding, so this pass does not replace
these sequences with a capture-specific shortcut.

Descriptor-heap-style indexing is real in this DXVK capture: 17 modules declare
runtime descriptor arrays, 15 name a `sampler_heap`, and 48 declare physical
storage-buffer addressing. These are descriptor-set and buffer-address paths,
not use of `VK_EXT_descriptor_heap`. The existing descriptor indexing path
compiles them. The general descriptor-hoisting change above addresses one
observed inefficiency in this path.

## Comparable populations

Recorded pipelines and standalone shader entries are kept distinct. All runs
use one common host-only Honeykrisp frontend and the same CPU DRM shim. Each
compiler snapshot rebuilds all compiler objects and private headers together.
No GPU submission is made by these measurements.

* **Lethal Company:** all 69 recorded pipelines (54 graphics, 15 compute), with
  captured state, from the existing 151,424-byte Fossilize archive. All creations
  succeed: 49 contain shaders; 20 are state/link-only graphics pipeline libraries
  and emit no program. There are 51 unique SPIR-V modules and 55 final main
  kernels after excluding helper vertex stubs.
* **CS2:** a deterministic sample of 128 graphics and 32 compute pipelines,
  evenly spaced through each sorted hash list; all 160 compile. As in the
  existing CS2 CPU audit, `FOSSILIZE_IGNORE_LAYOUT_SUPPORT=1` permits analysis of
  recorded descriptor layouts exceeding the replay device's limits. This is
  not an execution or descriptor-layout support claim. Lethal Company uses no
  such override.
* **Willems:** 268 standalone entries: 263 compile, five retain their previous
  compiler failures. Successful software geometry/tessellation stages may
  generate several kernels.
* **vkmark:** all 17 standalone entries compile.
* **CTS:** the existing 768-entry stratified timing sample, all compiling. Its
  1,018 main kernels include software geometry/tessellation work. It is neither
  a game workload nor an execution pass count.
* **Focused robustness:** all 5,738 previously compiling entries associated
  with CTS buffer/UBO/SSBO robustness and descriptor-indexing cases. Another
  1,712 entries were classified as unsupported-feature compiler failures by
  the earlier audit and are excluded from this quality comparison. Both
  measured arms compile all 5,738 selected entries.

Baseline metrics below count final programs selected by `CORPUS_FINAL`, not
trial preambles. GPR extents are 32-bit registers, with the current cap at 96.
P95 is the lower indexed percentile. SAVE/FILL counts are static records;
scratch may also include private arrays. Waits are **inline scoreboard
consumers / standalone WAIT records**. Uniform use is the mean number of
distinct uniform words read by ALU operands or explicit uniform imports per
main program; implicit memory-base pairs are excluded. Instruction counts and
mix are final backend VIR records, not a claim that every record expands to
exactly one machine instruction. Totals are population sums, not simultaneous
resource use.

| Population | Main kernels | GPR p50 / p95 / max | At cap | Spilling kernels | SAVE / FILL | Waits: inline / standalone | Preamble bytes | Mean uniform words | Main records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Lethal Company | 55 | 12 / 96 / 96 | 4 | 3 | 118 / 101 | 1,895 / 386 | 48,378 | 29.2 | 28,637 |
| CS2 sample | 162 | 16.5 / 84 / 96 | 6 | 6 | 193 / 303 | 6,928 / 932 | 127,418 | 32.4 | 104,757 |
| Willems | 271 | 12 / 34 / 96 | 1 | 1 | 1 / 1 | 3,953 / 278 | 340,936 | 20.4 | 42,240 |
| vkmark | 17 | 12 / 16 / 16 | 0 | 0 | 0 / 0 | 139 / 4 | 13,770 | 17.7 | 1,461 |
| CTS sample | 1,018 | 16 / 38 / 96 | 1 | 0 | 0 / 0 | 34,380 / 7,410 | 742,378 | 22.9 | 599,910 |
| Focused robustness | 5,738 | 20 / 40 / 96 | 2 | 0 | 0 / 0 | 202,907 / 45,588 | 10,737,142 | 33.0 | 5,074,857 |

Lethal Company's pressure is concentrated in compute: all four capped programs
are compute kernels; three spill. The largest is `a7fe66611aa32aa4`, with 6,349
main records before this change. The other spilling pipelines are
`1eedf1e59030d12f` and `9fec0a5bffe06df0`.

| Main instruction family (baseline) | Lethal Company | CS2 sample | Willems | vkmark | CTS sample |
| --- | ---: | ---: | ---: | ---: | ---: |
| Select | 4,204 (14.7%) | 12,971 (12.4%) | 4,565 (10.8%) | 122 (8.4%) | 113,047 (18.8%) |
| FP32 add/multiply/FMA | 3,584 (12.5%) | 28,414 (27.1%) | 11,800 (27.9%) | 448 (30.7%) | 11,821 (2.0%) |
| Integer shifts and bitwise logic | 6,322 (22.1%) | 16,053 (15.3%) | 5,772 (13.7%) | 92 (6.3%) | 162,251 (27.0%) |
| Device loads | 1,254 (4.4%) | 5,295 (5.1%) | 2,039 (4.8%) | 47 (3.2%) | 28,367 (4.7%) |
| Subgroup lane reads | 0 (0.0%) | 318 (0.3%) | 0 (0.0%) | 0 (0.0%) | 40,747 (6.8%) |

## Retained candidate deltas

All deltas are final minus the baseline above. GPR sums are diagnostic totals,
not simultaneous allocation. GPR medians, capped identities and spilling
identities stay unchanged. Willems' GPR P95 falls from 34 to 32; the other P95s
stay unchanged.

| Population | Main records | Sum of GPR extents | SAVE / FILL | Waits: inline / standalone | Preamble bytes | Final mean uniform words |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Lethal Company | −910 | +4 | −16 / −16 | −80 / +8 | +1,388 | 29.9 |
| CS2 sample | −720 | −156 | 0 / 0 | −248 / −21 | +9,882 | 32.3 |
| Willems | −929 | −28 | +1 / +1 | −5 / −8 | +2,884 | 21.0 |
| vkmark | 0 | 0 | 0 / 0 | 0 / 0 | 0 | 17.7 |
| CTS sample | −2,370 | −174 | 0 / 0 | −214 / +191 | +16,206 | 23.5 |
| Focused robustness | −1,951 | +45 | 0 / 0 | −1,142 / +1,148 | +52,488 | 33.5 |

## General implementation and validation

`agx_nir_opt_apple9_bounds` rewrites only the exact saturating last-byte
comparison and folds field additions only with a proof of no wrap.
`agx_nir_hoist_apple9_uniform_reads` operates on the private clone used for
preamble selection. It proves uniformity recursively, requires NIR's
`nir_instr_can_speculate` for every dependency moved out of its original block,
and starts from reorderable global reads or adjusted buffer-size limits.
Divergent inputs, phis and ordinary guarded buffer loads are rejected. Preamble
cost and size limits still choose which values to store.

The **443 host compiler tests pass**, including boundary/randomized checks for
short buffers, overflowing last-byte calculations, safe and unsafe constant
offsets, and positive/negative descriptor-hoisting cases. All recorded Lethal
pipelines, the CS2 sample, vkmark, the CTS timing sample, and the 5,738-entry
robustness population compile as described above. Willems retains its five
pre-existing failures. These are compile counts, not CTS execution passes.

On T8132, the focused **1,315-case descriptor/robustness CTS run** has identical
identities and outcomes on baseline and final drivers: **915 pass, 400 skip,
zero failures, expected failures or flakes**. The case list includes static/dynamic uniform
and storage buffers, scalar/vector formats, short ranges, volatile accesses,
null descriptors, and 115 descriptor-indexing cases from the readiness inventory.
Compression stays enabled; `ASAHI_MESA_DEBUG` and `HK_PERFTEST` are unset.

The [compute derivative follow-up](../compute-derivatives/RESULTS.md) records
75 passing authored probes and the separately tested prototype's 84 CTS passes,
six implicit-LOD failures and 459 skips. Consequently the final driver leaves
the compute-derivative extension and feature unadvertised. No system driver
was installed and the exclusive mini lease was released after validation.

## Evidence and reproduction

Workspace summaries are in `artifacts/dxvk-quality-20261006/`:
`quality-summary.json` includes per-program changes; `baseline-*.json` and
`final-*.json` retain selected final records and outcomes; `lethal-spirv-census.json`
retains source identifiers, capabilities, counts and assembly hashes;
`robust-selection.json` records the focused population; `hardware-cts/`
contains outcome CSVs, comparisons and the six prototype LOD failure traces.
The earlier `cts-focused-summary.json` concerns the descriptor-only ablation,
not the final bounds rewrite. The original corpus databases and Fossilize
archives were queried in place. No new corpus copy was made.

Use `build-compiler.py --detailed-metrics` to add opcode and ALU-uniform census
fields to a private measurement build. The normal compiler remains free of
this additional instrumentation. The artifact evidence directory retains the
measurement command scripts, `summarize.py`, and exact library/build
provenance. `descriptor-only-*.json` retains the hoisting-only ablation.
The compiler code in the final runtime matches `90415b1fa8c`; the final runtime
removes the prototype capability exposure. Runtime library hashes are recorded
separately in `hardware-build-provenance.json`.

Portal 2's requested DXVK D3D9 capture has not yet been supplied. It will be
added as a separately identified recorded-pipeline population when available;
Lethal Company is not presented as D3D9 coverage.
