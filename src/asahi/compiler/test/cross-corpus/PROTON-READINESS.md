# Apple9 compiler readiness for DXVK and vkd3d-proton

Audit date: 2026-10-06. Target: T8132 / Apple M4 G16G, experimental
Honeykrisp. Compiler baseline: `db0867aa028`; allocator follow-up:
`c95d71e9031`. This is a compiler and advertised-capability audit, not a claim
that a game, D3D feature level, or CTS execution passes.

## Result and priorities

No remaining failure in the classified CTS compiler audit is attributed to an
advertised, within-limit feature after the three publication-window fixes.
Current DXVK's 51 mandatory feature bits are all advertised, as are its required
extensions. Common D3D9/D3D11 compilation therefore has no newly identified
small feature blocker in this audit. Optional features and per-title shader
limits remain relevant. D3D12's higher shader models have concrete gaps.

Rank is a suggested compiler-work priority, not measured title prevalence.
The original primary labels came from unsupported-capability classification.
A width-aware follow-up corrected the denormal row: that label did not identify
the instruction causing compilation to fail.

| Rank | Gap / affected use | Apple9 exposure | CTS compiler evidence | Scope of a fix |
| --- | --- | --- | --- | --- |
| 1 | FP32 denorm modes; vkd3d's SM 6.2 gate (and thus its progression to 6.5+) | Both FP32 preserve and flush-to-zero properties false | The earlier 201 `DenormFlushToZero` labels were misattributed: all 201 modules also require unsupported FP64. All 579 FTZ32 entry identities without FP64 compile; execution is unvalidated | Arithmetic flushes denorms, while min/max and sign-bit operations can pass them through. FTZ needs per-operation handling; preservation also needs a complete strategy. Not a feature-bit flip. |
| 2 | Buffer int64 atomics and linear compute derivatives; SM 6.6 | Both false; image/shared int64 atomics also false | 920 primary `Int64Atomics` failures; 24 linear and 60 quad derivative failures; 2,892 image-int64 failures are a separate optional capability | Memory atomic semantics and derivative lane/workgroup mapping need implementation and execution tests. Runtime SM 6.6 requires buffer atomics, not all the stronger profile's atomic features. |
| 3 | Wide graphics interfaces in individual D3D11/D3D12 shaders | VS/GS/TES output and FS input limited to 96 user components | 8 stage-I/O and 5 stage-output cases exceed advertised limits | Generalize varying transport/layout with hardware validation; no evidence here that a particular title hits this limit. |
| 4 | Double precision, optional D3D11/D3D12 shader feature | `shaderFloat64` false | 7,468 primary `Float64` failures | General FP64 lowering/emulation; not a common DXVK initialization requirement. |
| 5 | Barycentrics, optional D3D12 shader feature | Barycentric extension/feature absent | 2,977 primary `FragmentBarycentricKHR` failures | Interpolation/fragment-input implementation; not itself the SM 6.1/6.2 version gate. |

Interlock/ROVs are an important **exposure and execution-validation** gap, but
not a newly found missing basic compiler lowering: 192 pixel-interlock and 128
sample-interlock capability-bearing entries compile. The backend acquires the
pixel for the shader and fences at the critical-section end. HK advertises
neither feature, so neither DXVK nor vkd3d exposes ROVs. The 192 primary failures
for *shading-rate* interlock are a different feature. Enabling pixel/sample
interlock requires validating ordering, coverage, and pipeline behavior; a
successful host compile is insufficient. Conservative rasterization is also
absent, separately preventing the normal FL12_1 path.

No small, complete compiler feature blocker was identified for implementation
in this pass. In particular, `StorageInputOutput16` is unadvertised and accounts
for 3,611 primary failures, but it is **not** a requirement in vkd3d's native
16-bit arithmetic check. Implementing it would not remove that supposed gate.
No capability was enabled just to satisfy the query.

## Feature map

Sources are pinned to DXVK `f20f363191c019cbf0d792e4e8f660d46ebecb6c`
and vkd3d-proton `b206eb6680fb92a64ae57bfccc7454a138f76887`.
“Required” below means the actual runtime check when one exists. The vkd3d
profile is useful guidance but is stronger than some runtime checks.

The successful compile counts in this table count CTS entry identities that
declare the listed SPIR-V capability, unless explicitly called a test family.
They are nonexclusive and include shaders whose unsupported operations can
optimize away. Related-family totals and all outcomes are retained in the
machine-readable evidence. They are not counts of executed CTS passes.

| Feature / extension | Translator use | HK Apple9 | Related CTS compiler evidence |
| --- | --- | --- | --- |
| Descriptor indexing, nonuniform access, runtime arrays, update-after-bind | DXVK requires descriptor indexing, runtime arrays, sampled-image UAB, partially-bound/update-unused. vkd3d strongly requires almost all indexing features and at least one million UAB descriptors except UBOs | Required bits and the other nonuniform indexing bits true; relevant UAB limits 1,048,576 | `descriptor_indexing` family covered; 470 `ShaderNonUniform` and 3,161 `RuntimeDescriptorArray` entries compile. Failures with these declarations require other unadvertised features. |
| Int8 / Int16 / Int64 and 8/16-bit buffer storage | Current DXVK requires all three integer widths; vkd3d needs Int16 for its SM6 wave path, Int64 for optional integer ops and Int8 for SM6.6 | All true, including storage and scalar/standard UBO layout | 15,962 / 16,961 / 16,642 successful entries respectively. Int64 arithmetic support does not imply int64 atomics. |
| Float16 | DXVK min-precision support; vkd3d relaxed/native 16-bit arithmetic | True; FP16 denorm preservation true; storage-buffer offset alignment 16 | 10,604 capability-bearing entries compile. Other-capability failures remain in mixed tests. |
| Float64 | Optional double-precision D3D11/D3D12 operations | False | 7,468 primary failures; see ranked table. |
| Geometry and tessellation | Geometry required in common DXVK setup; tessellation gates D3D11 FL11_0; vkd3d baseline graphics | Both true | Geometry/tessellation families covered; 13,982 / 21,723 capability-bearing entries compile. Failures are classified as other unadvertised features or exceeded limits. |
| `EXT_transform_feedback`, geometry streams | D3D stream output; enabled as a client feature in DXVK, present in vkd3d's baseline profile | Both true, four streams | 2,024 XFB-capability entries compile. Unsupported features and over-limit stream/layout tests explain remaining failures/crashes. |
| Sample-rate shading and multisampling | Required by common DXVK setup and D3D graphics behavior | Sample-rate shading true | 681 `SampleRateShading` entries compile. Mixed unsupported-feature inputs are not evidence against that bit. |
| `EXT_fragment_shader_interlock` | Optional ROVs; vkd3d FL12_1 needs ROVs plus conservative rasterization | Pixel, sample, shading-rate interlock all false | 192 pixel + 128 sample entries compile; shader compilation alone does not establish ordering semantics. |
| Demote-to-helper (`EXT_shader_demote_to_helper_invocation`, core 1.3) | Required by current DXVK; D3D helper/discard semantics | True | All 116 capability-bearing entries compile. |
| Subgroup basic/vote/ballot/arithmetic/shuffle/quad; size control/full subgroups | vkd3d SM6.0 wave operations; DXVK requires size control and compute full subgroups | Advertised across all six classic stages; subgroup size fixed at 32, full subgroups true | 31,323 `GroupNonUniform`, 8,844 arithmetic, 28,156 ballot, 3,083 shuffle, 2,571 quad entries compile. Advanced unadvertised capabilities explain failures in mixed subgroup groups. |
| `EXT_robustness2`: buffer, image, null descriptors | DXVK requires buffer robustness2/null; image robustness is optional in its enable table but needed for correctness. vkd3d requires all three | All true | Robustness families covered; the three advertised 3D-gradient publication failures were fixed and recompiled successfully. No remaining classified advertised compiler cause. This does not certify bounds behavior at execution. |
| Buffer device address, Vulkan memory model, scalar/standard UBO layout, draw parameters | Required/strongly used for buffer addressing and translated layouts | Advertised | Covered through mixed descriptor, storage, arithmetic, and graphics inputs; no separate feature-specific execution result claimed. |
| `EXT_depth_clip_enable`, maintenance5/6, load/store-op-none, push descriptors | DXVK runtime requirements (plus swapchain); push descriptors and maintenance5/6 are actual vkd3d runtime gates too | Advertised | Mostly API/driver behavior rather than an isolated backend lowering. |
| `EXT_mutable_descriptor_type`, `EXT_graphics_pipeline_library` | Descriptor efficiency and pipeline compilation/stutter reduction | Both advertised | Host shader compilation does not validate mutable binding or GPL linking/performance. |
| `EXT_descriptor_buffer` / `EXT_descriptor_heap` | Optional newer binding paths; buffer is recommended by vkd3d | Neither advertised | Not mandatory DXVK initialization gates. Descriptor-heap compiler failures do not block the ordinary descriptor-set path. |
| `EXT_image_view_min_lod`, min/max filtering, custom border colors | vkd3d correctness/feature-level concerns; custom border optional in DXVK runtime table | Min-LOD extension and feature true with Apple9 lowering; custom border colors absent. Min/max filtering false normally, **faked** by vkd3d's existing drirc | API/sampling correctness issues must remain separate from compiler acceptance. vkd3d's profile includes custom border colors even though runtime setup treats the extension as optional. |
| Mesh/task, ray query / ray tracing | Optional modern D3D12 tiers and DXR; FL12_2 has broader requirements | Absent | E.g. 1,234 ray-query entries fail. Not prerequisites for ordinary D3D9/D3D11 rendering. |

The related CTS family view (distinct entry identities, including shared helper
shaders) is below. All failures/crashes retain an unadvertised-feature or
exceeded-limit classification; none is a new advertised compiler failure.

| CTS family substring | Successful compiles | Compiler failures | Crashes |
| --- | ---: | ---: | ---: |
| `descriptor_indexing` | 530 | 1,400 | 0 |
| `geometry` | 4,536 | 4,158 | 48 |
| `tessellation` | 1,339 | 125 | 0 |
| `transform_feedback` | 2,078 | 73 | 125 |
| `subgroups` | 23,924 | 27,095 | 0 |
| `robust` | 13,463 | 3,074 | 0 |
| `multisample` | 3,882 | 45 | 0 |
| `interlock` | 349 | 198 | 0 |
| `demote` | 45 | 0 | 0 |
| `float_controls` | 8,885 | 1,704 | 0 |
| `compute_shader_derivatives` | 100 | 84 | 0 |
| `fragment_shading_barycentric` | 272 | 3,877 | 0 |

All 1,400 descriptor-indexing-family failures require `RawAccessChainsNV`.
The robustness-family failures require image int64 atomics (2,492), storage
image multisampling (292), long vectors (282), ray query (7), or fragment
shading rate (1). These examples explain why an unsupported mixed test must
not be reported as an ordinary descriptor-indexing or robustness2 blocker.

The shipped engine configuration matters: `00-hk-defaults.conf` enables
`vertexPipelineStoresAndAtomics` for DXVK and vkd3d, allowing their normal
FL11_1 check to advance; a generic query without that config reports it false.
The vkd3d min/max-filtering override is explicitly a compatibility fiction in
the existing driver configuration, not implemented hardware behavior. It must
not be counted as a compiler feature completed by this work. Apple9's min-LOD
feature is separately implemented and advertised.

For D3D12 shader-model inference, the queried subgroup/layout/Int16 bits satisfy
the SM6.0 check, but the FP32 float-control properties stop the normal progression
to SM6.2. Native 16-bit support has its own check (FP16, Int16, 16-bit storage,
FP16 denorm preservation, and buffer alignment). Optional barycentrics, FP64,
ray tracing, and mesh features must not be conflated with mandatory SM-version
gates. This source-based inference is not a vkd3d device-creation run.

## One additional GS compile-time pass

Profiling `72acdaeb...-3` sampled repeated `search_ssa_to_reg_out` work, including
spill-memory register searches. Each block previously stored a dense
register-to-SSA map, then searched it linearly for every successor live-in value.
`c95d71e9031` stores live-out assignments sorted by SSA name and binary-searches
them. Sparse-bitset traversal already supplies that order. It preserves the
selected register, class, phi placement, spill decisions, and candidate policy;
empty blocks retain a non-null visited marker. Memory now scales with live-out
values instead of the full spill-register file per block.

Two runs per arm, forward then reverse order, use the same host frontend,
CPU 12 affinity, disabled shader cache and thread CPU clocks. No local compiler
build or other compiler replay ran concurrently with these measurements;
read-only audit/indexing work and unrelated host tasks were present. These are
host compiler timings, not GPU timings or a full-population estimate.

| Five largest previously selected GS | Backend CPU seconds |
| --- | ---: |
| Pre-CS2 `7e706cb7ebc` | 28.972 |
| Previous compiler `db0867aa028` | 45.153 |
| SSA-indexed live-out map `c95d71e9031` | 39.950 |

This pass reduces the five-GS total by **11.5%**. The remaining increase over
pre-CS2 is **37.9%**, down from **55.8%** in this matched experiment.
`72acdaeb...-3` falls from 13.712 to 11.428 seconds (pre-CS2: 7.863).
The full recorded main/preamble program-statistics and final-program records
match between the previous and new compiler for all five GS in both repeats.
The additional candidate policies remain unchanged. Stop after this pass;
there is no new overall-corpus timing estimate.

Validation: all 433 host compiler tests pass, including spilled loop-phi
execution and live-source preservation. All outcomes and complete recorded
main/preamble statistics and final-program records match the preceding tip in
the 10,737-entry focused CTS population, 268 Willems shaders, and 17 vkmark
shaders. The CTS subset has 10,421 successful compiles, 191 compiler failures,
and 125 crashes; Willems has 263 successful compiles and five pre-existing
compiler failures; vkmark has 17 successful compiles. No new failure or recorded
code-generation change appears. No hardware was accessed during this task;
the mini's existing lease was left untouched.

## Evidence and reproduction

Workspace artifacts: `artifacts/proton-readiness-20261006/`.
The `readiness.sqlite3` tables `capabilities`, `aliases`, and `outcomes` join the
original corpus by SPIR-V SHA and entry key. `cts-summary.json` preserves
nonexclusive capability/family counts and separates successful compiles, empty
shaders, compiler failures, crashes, and the prior failure classifications.
The starting full-corpus results are frozen; the three publication fixes are
an explicit overlay. This task did not rerun the full CTS or recompile all
279,775 inputs. The combined historical view contains 182,856 successful
compiles, 150 empty shaders, 96,523 compiler failures and 246 crashes. Remaining
failures/crashes are classified as 96,602 unadvertised-feature inputs and 167
exceeded-limit inputs. Unsupported host replay inputs are not executed CTS
skips, expected failures, or flakes.

The artifact directory also contains engine-specific query JSON, the no-device
host query source/generator, pinned translator commit metadata, raw profiler
stacks, build provenance, unit logs, repeated timing databases, and comparison
scripts/results. The original SPIR-V and primary-cause audit remain in
`artifacts/compiler-cross-corpus-20261006/corpus.sqlite3`.

Primary references:

- [DXVK feature/extension enable table](https://github.com/doitsujin/dxvk/blob/f20f363191c019cbf0d792e4e8f660d46ebecb6c/src/dxvk/dxvk_device_info.cpp)
- [DXVK D3D11 feature-level and optional-feature checks](https://github.com/doitsujin/dxvk/blob/f20f363191c019cbf0d792e4e8f660d46ebecb6c/src/d3d11/d3d11_features.cpp)
- [vkd3d runtime device/feature/shader-model gates](https://github.com/HansKristian-Work/vkd3d-proton/blob/b206eb6680fb92a64ae57bfccc7454a138f76887/libs/vkd3d/device.c)
- [vkd3d Vulkan profile](https://github.com/HansKristian-Work/vkd3d-proton/blob/b206eb6680fb92a64ae57bfccc7454a138f76887/VP_D3D12_VKD3D_PROTON_profile.json)
- [vkd3d documented baseline and recommendations](https://github.com/HansKristian-Work/vkd3d-proton/blob/b206eb6680fb92a64ae57bfccc7454a138f76887/README.md#drivers)
