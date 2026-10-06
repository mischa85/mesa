# High-operand Metal pressure kit

Prepared on the Linux host; **not compiled on macOS, run under the HV, or
submitted to the GPU**. All MSL is authored for this experiment. The public
Metal API helpers serialize archives of these shaders only. No proprietary
Apple executable is inspected. No SSH, reboot, hypervisor launch or GPU command
queue is included.

Generate the 36 sources and manifests:

```sh
python3 prepare.py --output /path/to/kit
```

In the later coordinator-owned macOS/HV session, `./compile.sh` compiles the
sources and writes a per-case `.bin` archive and `.log`. Compute pipelines use a
32-thread maximum to reduce occupancy-driven pressure. Render pipelines contain
an ordinary vertex stage and the pressure fragment stage, with RGBA32Float
output. Each operation has an 8-value control and 90/96-value variants.

Each pressure shader loads distinct values, destroys their original storage,
computes the target's input from all values, and uses every value again in a
separate output word dependent on the target result. This creates overlapping
SSA lifetimes. Metal can still spill, rematerialize, choose another encoding,
or keep the target low. Thus this kit **requests pressure**, and does not claim
that any operand was allocated above r63. SR reads may be hoisted before the
pressure region; their result must be checked in the emitted program.

| Case | Stage | Current r63-limited operands targeted |
|---|---|---|
| `sample` | fragment | `TEXTURE_SAMPLE` result tuple |
| `lod` | compute | `TEXTURE_LOD` result tuple |
| `grad` | fragment | `TEXTURE_GRAD` result tuple |
| `shared` | compute | `SHARED_LOAD` destination/index; `SHARED_STORE` data/index |
| `private` | compute | `PRIVATE_LOAD` destination/index; `PRIVATE_STORE` data/index |
| `scan` | compute | `SUBGROUP_SCAN_IADD` destination/source |
| `broadcast` | compute | `SUBGROUP_BROADCAST` destination/data/lane |
| `ballot` | compute | `SUBGROUP_BALLOT` destination/predicate |
| `get_sr` | compute | `GET_SR` / `GET_SR_ZEXT16` destination |
| `half` | compute | `FLOAT_TO_HALF_ZEXT` destination |
| `float2` | compute | four-byte `FLOAT2_BASE` destination and both sources |
| `float3` | compute | six-byte `FLOAT3_COMPACT` destination and all three sources |

The six-byte `FLOAT2_COMPACT` already supports r64–r95 in our machine table;
its appearance is a known alternative, not a newly discovered high-register
form. Texture publication operands are in their separate file and must not be
counted as high GPRs. Do not infer a hard r63 limit from an absent high allocation.

For each archive, retain the exact source/hash, pipeline log, register count,
spill traffic and target instruction bytes. Compare the control with the
pressure variants, identify target operand registers, and only then propose a
high-bit encoding hypothesis. A subsequent isolated T8132 execution probe is
required before changing the production machine constraints. These archives
alone are not hardware correctness evidence.

The private case uses a non-inlined helper to discourage eliminating its
addressable local array. Confirm that private accesses survive compilation.
The fragment cases write SSBO words as well as color so all inputs stay live.
These are compile-only sources: any future execution harness needs separate
per-invocation storage, valid textures/samplers, a 32-thread shared-memory group,
and an explicit output oracle. Host checks currently cover generator syntax,
manifest/source consistency and shell syntax; no Metal SDK is available here.

The ballot case uses the explicit `simd_vote::vote_t` conversion described in
[Apple's MSL specification, section 6.10.2](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf)
and used by [Khronos SPIRV-Cross's public MSL tests](https://github.com/KhronosGroup/SPIRV-Cross/blob/main/reference/shaders-msl-no-opt/comp/subgroups.nocompat.vk.msl3.comp).
