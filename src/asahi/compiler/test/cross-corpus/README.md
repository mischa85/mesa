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

## Storage after metadata exhaustion

All corpora, per-shader metadata, detailed replay results, and comparisons now
live in SQLite packs. Do not create per-module files, even for temporary replay.
The earlier loose tree exhausted Btrfs metadata despite free data space. Its
549,589 files were hash-verified into `corpus.sqlite3`, independently checked,
and removed. The pack retains source manifests, aliases and interrupted runs.

The current interfaces supersede the loose-file commands above:

- `fetch-public.py OUTPUT` retains selected source files inside one tar archive
  per corpus, with a small revision/license manifest.
- `prepare.py --source DIR_OR_TAR --output DIR --population NAME [--glsl]`
  creates `corpus.sqlite3`. GLSL uses one reusable output file; archive inputs
  needing include resolution must use an existing source checkout.
- `refresh-metadata.py --pack DB --source-population OLD --population NEW
  --summary JSON` reflects archived modules into an indexed replay population.
- `extract-cts.py --extractor TOOL --data CTS_DATA --pack DB --population NAME
  --summary JSON [--resume-chunk N]` consumes binaries streamed from the private
  CTS extractor. It writes no registries, module files or metadata files.
  Completed chunks commit both aliases and a resume checkpoint atomically.
- `run.py --pack DB --population NAME --icd JSON --runner FILE --host-shim FILE
  --output DIR [--resume]` sends framed metadata and SPIR-V through a single
  reusable batch stream. Results are compressed, keyed rows in `results.sqlite3`.
- `import-packed-results.py --pack DB --run OLD --output DIR` recovers an
  interrupted legacy run without expanding its original JSONL file.
- `compare.py BASELINE CANDIDATE --pack DB --output DIR` writes detailed rows
  in `comparison.sqlite3` and a small summary. Only matched successful compiles
  contribute code totals; all outcome transitions remain counted.

`--exclude-results` accepts packed result databases for continuation populations.
Keep the corpus and source hashes stable when resuming, and distinguish timings
across interruptions. Never infer GPU correctness from these CPU-only replays.

## October 6 follow-up

The accounting correction `81b3ce1b9a5` gives emitted main programs precedence
over an empty helper variant. Frozen run rows remain unchanged; normalized
merges retain the original classification and its correction evidence.

The 951-instruction regression in
`dEQP-VK.ubo.random.16bit.nested_structs_arrays_instance_arrays.18/frag`
was triggered by `2fac9e8149a` (native integer equality). Its parent `b570881632b`
emits 5,218 instructions, versus 7,880 immediately after that change. Later
allocator improvements reduce that to 6,775, versus the original pre-CS2
baseline's 5,824. Native equality exposed breadth-first expansion of equal-cost
reduction trees in the pressure scheduler; reverting native equality is not
needed. `90045f62d46` follows newly exposed producers on pressure-increasing
ties. The reduced scheduler test needs at most six live values, versus 17
before the fix. The affected fragment shader now has 3,587 instructions,
zero SAVE/FILL instructions and zero scratch, versus 504 SAVE, 504 FILL and
2,016 scratch bytes before the fix.

At that revision, 263 non-compiler unit tests and 34 focused compiler tests
passed. The full unit invocation stopped at the previously reproduced unrelated
`Apple9Compiler.WritableSinkPointer` NIR divergence assertion. All 69 unique
Lethal Company pipelines pass with allocator assertions/validation enabled.
Willems has 263 passes and the same five unsupported failures; vkmark has 17
passes. The 10,737-entry third CTS population retains exactly 10,421 passes,
191 compile failures and 125 crashes. Its main instruction total falls 2.38%
and SAVE/FILL counts fall 21.2%; individual code-size tradeoffs remain, recorded
in the comparison database (largest increase: 232 instructions in an 8-bit UBO
compute shader; one tessellation program adds four SAVE/FILL pairs). This is
host compilation evidence, not hardware execution or a GPU speed measurement.

The complete pre-scheduler-fix corpus comprises 279,775 shader entry points.
Its normalized current result is 182,853 passes, 150 empty shaders, 96,526
compile failures and 246 crashes. Audit the **current** failures, including
candidate-only failures, rather than taking the baseline failures as exhaustive.
`audit-failures.py --include-crashes` classifies all 96,772 failing modules:

| Classification | Unique modules |
| --- | ---: |
| Unadvertised features | 96,602 |
| Exceeded advertised limits | 167 |
| Advertised backend failure | 3 |
| Unclassified | 0 |

The only advertised-backend cause found is a 16-word 3D texture-gradient
publication allocated beyond its encodable p0-p31 window. The affected vertex,
fragment and compute modules are the `rgba32ui` 3D unrolled, nonvolatile sampled
image-robustness test. They compile on the pre-CS2 baseline and fail both
before and after the scheduler correction: VS/CS use p24 and FS uses p28,
where the packer requires a base no greater than p16. The subsequent fixes and
validation are recorded below.

Results, per-module causes, CTS aliases and supporting SPIR-V/physical-device
evidence are in `artifacts/compiler-cross-corpus-20261006/corpus.sqlite3` at the
workspace root (`failure_audit`, `failure_groups`, and report
`failure-audit-cts-current`). Detailed replay and comparison databases sit
alongside it. Unsupported inputs are not reported as executed CTS skips.

## Publication bounds, sink pointers, and compile-time follow-up

`25885a73ff0` bounds an entire publication tuple by its producer encoding's
DEST range, in both allocation and validation. This preserves each instruction's
window rather than imposing one global limit. The new shared-RA unit exercises
8- and 16-word gradient tuples with other publications still live; before the
fix it reproduces the overflowing p24/p28 allocations. All three advertised
image-robustness modules now compile on the host. The 10,737-entry third CTS
population, 268 Willems inputs and 17 vkmark inputs retain their outcomes and
all recorded main/preamble byte size, instruction, copy, wait, swap, SAVE/FILL,
GPR and scratch statistics. This claim is limited to the replayed populations.

`e35275cc5ea` applies the existing sink-address lowering before preamble
extraction runs divergence analysis. The writable sink maps the read-only zero
page to the writable scratch page and preserves ordinary pointers. The original
`WritableSinkPointer` compile test now passes; `WritableSinkAddressLowering`
checks both address cases and elimination of the generic intrinsics. The full
host unit suite passes: 433 tests, without filtering out compiler tests.

Profiling the large `72acdaeb...-3` geometry shader found two quadratic loops:
physical completion scheduling scanned every physical block for each logical
successor, and spill coupling repeatedly scanned predecessor-state and phi lists.
`1ecb349480d` indexes the NIR-to-physical-block mapping (preserving the last
physical block for duplicate NIR blocks). `db0867aa028` uses the spiller's
existing scratch bitsets to index coupling membership. These changes preserve
allocation policy, spill placement and candidate selection. The 433 host tests
pass after both changes, including the loop-phi allocation/execution checks.

Repeated host measurements compare pre-CS2 `7e706cb7ebc`, the publication fix
`25885a73ff0` before the two speedups, and compiler tip `db0867aa028`, with the
same frontend, CPU 12 affinity, disabled shader cache and thread CPU clocks.
Each arm runs twice in forward/reverse order. There are no concurrent local
builds or compiler replays; unrelated host tasks remain running. The CPU
frequency governor remains `powersave`. These are host compiler timings, not
GPU execution measurements.

The overall estimate uses 3,072 matched successful CTS entries: 32 deterministic
hash-selected entries from each of 16 baseline-time quantiles in each of six
API stages. Each stratum is weighted by its full-population size, covering the
182,853 matched-success population. Runs were expanded in two waves (768 and
2,304 entries). Five geometry shaders with the largest frozen-current backend
times are measured separately, without adding their selection bias to the
overall estimate.

| Backend CPU measure | Pre-CS2 | Before speedups | Tip |
| --- | ---: | ---: | ---: |
| Weighted overall estimate, relative to pre-CS2 | 1.000 | 1.139 | 1.084 |
| Five large GS, total seconds | 28.907 | 50.002 | 44.782 |
| `72acdaeb622d84c6...` GS, seconds | 7.901 | 15.535 | 13.493 |

The speedups reduce the weighted overall estimate by **4.9%** and the five-GS
total by **10.4%**. Remaining increases versus pre-CS2 are **8.4%** overall and
**54.9%** in the five-GS total. The paired within-stratum bootstrap 95% interval
for the overall remaining increase is **+2.5% to +15.8%**; this is an estimate,
not a newly completed full-corpus timing run. Full shader-creation CPU time has
an estimated **7.1%** remaining increase. The compiler still evaluates additional
uniform-rematerialization and sample-hoisting alternatives absent from the
pre-CS2 compiler. The optimization here preserves those candidate policies.

For context, the older complete replay (before `90045f62d46`) recorded backend
CPU totals of 5,152.42 -> 6,327.36 seconds (+22.8%) and full shader creation of
6,489.82 -> 7,675.53 seconds (+18.3%) on the 182,853 matched successes. Those
runs span resumptions and host loads; do not compare their absolute totals to
an extrapolated sample as if this were one controlled experiment.

All 3,072 sampled shaders and the five large GS compile in every arm and repeat.
The before-speedup and tip program-statistics records match exactly. The tip
also preserves every outcome and complete recorded program-statistics record
in the 10,737-entry CTS subset, Willems and vkmark, including byte sizes and
wait counts. There is no claim of a full-corpus replay on this tip.

Reproduction inputs, driver provenance, timing scripts, raw result databases,
unit logs and comparison reports are retained in the workspace evidence pack
under `files.path` prefix
`followup-20261006/publication-and-timing/` in
`artifacts/compiler-cross-corpus-20261006/corpus.sqlite3`. The human-readable
summary is `artifacts/compiler-cross-corpus-20261006/timing-repeat-summary-3072.json`;
`timing-sample-3072.json` records all identities, strata and weights.

Hardware validation used the isolated ARM64 driver built from `db0867aa028`,
SHA-256 `bd7b868845bc06f8fad2cf69c8c6b0c1f58b330b272aa20bcdf891ba8cd136e3`.
The renderer reports Honeykrisp, Mesa 26.3.0-devel (`git-db0867aa02`). Normal CTS:
463 pass, 1 skip; forced-spill CTS: 139 pass, 1 skip, with 432 SAVE and 662 FILL
instructions across compiler captures and 32 passing cases containing both.
Both skips are `spirv_assembly.instruction.compute.opphi.vartype_longvec`.
There are no failures, expected failures or flakes in either set. Compression
uses the normal default (`ASAHI_MESA_DEBUG` unset); `AGX_SPILL_COALESCE=1` in both
runs. The mini lease was acquired with `wait` and released after the runs.
The driver was not installed system-wide. Logs and hashes are retained under
workspace `artifacts/mesa-compiler-db0867aa028/`.
