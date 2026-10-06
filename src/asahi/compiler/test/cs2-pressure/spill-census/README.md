# Host-only spill census

This diagnostic overlay preserves the production instruction order and register
allocation. It tags inserted spill moves before SSA repair, carries their tags
through physical lowering, and dumps only the final selected allocation. It also
records both sides of the sample/reorderable-load hoisting comparison.

First build the full host Vulkan driver from the source revision being measured.
Then, from any directory:

```sh
MESA_BUILD=/path/to/mesa/build-host-replay \
CENSUS_OUTPUT=/path/to/output \
python3 build.py candidate check-pressure
```

`check-pressure` makes the spiller's register-demand postcondition fatal even in
a release build. `MESA_SOURCE` overrides the Mesa source root; `SOURCE_TREE` may
select a frozen compiler source tree with the same compiler ABI. Rebuild the
complete compiler archive after ABI changes before using an overlay. Outputs are
an isolated `candidate/libvulkan_asahi.so`, `icd.json`, and instrumented sources;
no source or build files are modified in the production tree.

Use the generated ICD with the existing host-only replay harness, one replay
thread, and `AGX_APPLE9_STATS=1`. The harness must intercept hardware operations;
this tool does not provide a hardware stub. Pipe its stderr through
`parse-census.py`. `AGX_APPLE9_ASM=1` remains compatible but is unnecessary for this
parser. Optional `VERTEX_AUDIT_PIPELINE` records preserve pipeline identities.

Each record has raw static SAVE/FILL events. `kind` values are 0 untracked
coupling/lowering, 1 arithmetic/other, 2 constant, 3 uniform import, 4 texture
result, 5 memory result, 6 ordinary phi, 7 loop-header phi, and 8 system value.
MOV/SPLIT aliases preserve origin. A loop-header phi is a direct loop-carried
value; unrelated computations using it are not relabelled as phis. Uniform
provenance propagates only when all inputs to pure arithmetic are proved uniform.
The `uniform` flag overlaps the primary kinds and must not be added to them.

Depth follows the owning NIR block's loop ancestors. For the published estimate,
weight each event by `8 ** min(depth, 6)`. This is a loop-depth heuristic, not a
profile, cycle estimate, or measurement of shader invocation frequency.
`before`/`after` give instruction distances to the nearest sample in the same
physical block, or 999999 if none exists. Proximity does not establish causation
or prove that a sample is still pending.

Origin maps are cleared between allocation candidates to prevent stale tags when
instruction addresses are reused. Untracked events remain explicitly untracked.
The parser checks event totals against production codegen statistics. Compare
all program metrics with an uninstrumented replay before trusting a new census.
