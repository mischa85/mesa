# Cross-corpus compiler measurement (work in progress)

This CPU-only harness replaces further CS2-only tuning. Do not interpret
shader compilation as execution correctness or static counts as GPU time.
No full CTS result is claimed until extraction and every replay finish.

The initial comparator is the complete compiler archive at `7e706cb7ebc`,
before the CS2 compiler series, versus `e3636c07946`, including the select
simplification and rematerialization budget fix. The parked LICM and ineffective
reload-reuse experiments are absent from the latter. Both use one common
Honeykrisp front end/runtime: this isolates compiler changes, not unrelated
front-end, command submission, or driver changes. All private compiler headers
and objects are rebuilt together from their own revision. The driver library,
source hashes, commands, and generated-table origin are recorded.

## Tools

- `fetch-public.py OUTPUT` fetches pinned public sample revisions with licenses.
  Only shaders and licenses are retained, not sample textures/models.
- `prepare.py --source DIR --output FRESH [--glsl]` deduplicates SPIR-V (or
  compiles GLSL), reflects descriptors/push constants and records all inputs,
  duplicates, frontend failures, and unsupported stages. Shader specialization
  uses declared defaults; runtime descriptor arrays use 256 elements.
- `build-compiler.py --mesa DIR --build DIR --ref REV --output FRESH` builds a
  complete private compiler snapshot, with compact statistics and CPU clocks.
  It uses the selected common driver's existing build and generated tables.
- Build `compile-shader.c` with `cc -O2 -Wall ... -lvulkan -o OUTPUT`.
  It creates Vulkan shader objects, with no draw, command buffer or submission.
- `run.py --corpus DIR --icd JSON --runner FILE --host-shim FILE --output FRESH`
  requires the x86 host and explicit CPU-only DRM shim. It records identities,
  compiler output summaries and failures, and resumes later inputs after crashes.
- `compare.py BASELINE CANDIDATE --manifest JSONL --output FRESH` compares exact
  shader identities. Main and preamble costs are separate; helper vertex shaders
  are excluded. Every main-code instruction/register/swap/spill increase remains
  in per-shader output. Failed inputs are not silently dropped from outcomes.
- `patch-cts-extractor.py --source CTS --build CTS_BUILD --output FRESH` builds a
  private copy of CTS `vk-build-programs`, using two threads and 4,000-case
  chunks. Independent chunk registries preserve earlier binaries (the stock
  registry writer deletes binaries unused in its current chunk). Successful
  programs include SHA-1/name provenance; invalid SPIR-V and initialization
  skips stay visible. No shared CTS sources are edited.

## Current coverage limits

Shader-object replay covers vertex, fragment and compute. The private common
front-end adapter also compiles standalone geometry and tessellation with the
normal lowering functions and default graphics key. All resulting compute and
rasterization kernels count toward their original API stage. Mesh and ray
tracing are outside this driver's advertised stage support. Layouts exceeding
its eight descriptor sets or 256 push-constant bytes are explicitly excluded.
Bare SPIR-V uses the existing eager-variant path's default graphics state.
Recorded Fossilize pipelines must be reported separately, with their recorded
state; the two populations must not be conflated. The conditional shader-db GL
path is not configured in this workspace.

Report instruction, true three-XOR swap, SAVE/FILL, GPR extent and compile-time
changes per corpus, with main and preamble costs separately. GPR sums describe
a population, not simultaneous allocation. Scratch includes private arrays as
well as spills. Diagnostics record thread CPU time for the backend and full
shader creation; repeat timings without concurrent local builds. The initial
public runs overlapped the CTS tool build and are not final timing measurements.

The initial public comparison identifies sample/load hoisting as a source of
large GPR increases in blur shaders, and small instruction increases in two
Willems shaders. Turning it off improves both public populations' static totals;
this alone does not establish a GPU runtime gain or justify a final policy.

`extract-cts.py` streams completed chunks into a deduplicated SPIR-V corpus,
retains named aliases in compressed form and deletes only consumed raw chunks.
`refresh-metadata.py` creates a fresh replay view and classifies device limits
separately from reflection failures. Full replay may proceed in frozen
populations while extraction continues; `run.py --exclude-results RESULTS`
then handles the remainder without repeating earlier shader identities. Worker
processes restart every 256 shaders to bound memory and core dumps are disabled.

`CORPUS_FINAL` receipts select statistics matching the actual main and preamble
binary sizes. Discarded preamble attempts are not included in totals. Missing
statistics, compiler failures, crashes and timeouts remain distinct outcomes.

The optional `build-compiler.py --pressure-gate` overlay is a private scheduling
experiment. It rejects intra-block hoisting when NIR scalar-word pressure grows.
It accounts for live-out and following-if uses, but does not model physical
operand constraints and is not a physical-register guarantee. Nothing from
this experiment is installed or enabled in the production compiler.
