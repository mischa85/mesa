# Linear compute derivatives on Apple9

2026-10-06, T8132 / Apple M4 G16G. Explicit linear derivatives work through
existing subgroup lane transport, including FP16. **The Vulkan extension and
`computeDerivativeGroupLinear` remain unadvertised.** The initial results below
had six sampling/query failures. The [implicit-LOD follow-up](IMPLICIT-LOD.md)
fixes the two sampling cases; four query cases still fail.

## Model

The [KHR extension](https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_compute_shader_derivatives.html)
defines linear derivative groups as four consecutive local invocation indices.
For a quad with values `a,b,c,d`, fine X derivatives use `b-a` for the first
row and `d-c` for the second; fine Y uses `c-a` and `d-b` by column. Coarse X
and Y use `b-a` and `c-a` respectively across the quad. Default derivatives
choose the fine form.

The compiler expresses these pairs with existing subgroup shuffles and
subtraction. The existing shuffle lowering accounts for Apple's quad-uniform
low index bits. It introduces no new instruction encoding and does not assume
that the fragment derivative opcode works in compute. Only the linear mode is
implemented. Quad-layout compute and mesh/task derivatives remain unsupported.
The pass runs again when texture/math lowering introduces new derivatives.

## Validation

All 24 formerly failing linear modules compile and pass in the capability-enabled
prototype's CTS execution: scalar, vec2, vec3 and vec4, with default/fine/coarse
derivatives at workgroup sizes 16×1×1 and 4×4×1. The sixty quad-mode compiler
failures remain outside this implementation.

The complete compiler suite passes **443 tests**. Derivative tests check all six
operations over all 32 lane indices using nonlinear `f(i)=i²`, distinguishing
axes, rows/columns, coarse selection and quad bases. Compilation tests cover
all six operations at vector widths 1–4, in FP16 and FP32.

**All 75 authored GPU probes pass, across 28,068 checked rows.** Each dispatch
has three workgroups. The shader echoes inputs and a per-row tag; the harness
checks every row, its sentinel, exact result bits, and the device/driver.

The 63 FP32/lane-ID probes cover 1×1×4, 2×2×1, 2×6×1, 3×4×1, 20×1×1,
4×4×4, 8×8×1, 1×1×64 and 32×32×1. This establishes consecutive local-to-subgroup
lane mapping for these multidimensional, partial-subgroup and 1,024-invocation
workgroups. Twelve further FP16 probes cover 4×4×1 and 8×8×1; their reference
rounds both input conversions and subtraction to FP16. All generated SPIR-V
passes `spirv-val --target-env vulkan1.2`.

The native probe reports `Apple M4 (G16G B1)`, Honeykrisp Mesa 26.3.0-devel
(`git-bd93d82b95`), on kernel `7.1.13-m4-g16+`. Compression remains enabled.
These are private driver runs; no system driver was installed.

## Extension execution results and remaining scope

| 549-case focused CTS group | Pass | Fail | Skip | Expected fail | Flake |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prior FTZ baseline, extension disabled | 0 | 0 | 549 | 0 | 0 |
| Capability-enabled prototype | 84 | 6 | 459 | 0 | 0 |
| Final driver, extension disabled | 0 | 0 | 549 | 0 | 0 |

The prototype passes 24 explicit-derivative cases, 56 quad-operation cases,
two index-mapping cases and two mip-0 sampling cases. The six failures repeat
on the runner's retry:

* LOD query, mip 0 and mip 1, at both 16×1×1 and 4×4×1.
* Implicit sampling, mip 1, at both workgroup shapes.

In these tests the query path returns zero; mip-1 sampling returns the base-level
value (0.5 instead of 1). Correct explicit derivatives and quad transport do not
establish the texture unit's compute implicit-LOD behavior. The existing native
implicit/query path needs separate compute support. This work does not invent
new texture encodings or approximate sampler/LOD semantics to expose the feature.
A follow-up must establish the compute texture derivative/query contract, or a
complete lowering using already validated explicit-gradient operations, before
enabling the extension. FP32 preservation and buffer int64 atomics remain other
shader-model blockers.

Final capability removal is committed as `bdc96e8eaad`. The prototype runtime
hash is `ac7b15882bcf39c04d3cfb177180dd23f072cf15e0fe07b51ffef02275a0a717`;
the final runtime hash is
`514990c1c1d3c307ce2fe031bb98bdcb304b9044cf1638cdb9c46d47247a128b`.

## Reproduction and retained evidence

`generate.py` creates the 75 probes. Build the reusable harness from
`../fp32-denorm/probe.c` against the Mesa Vulkan headers. It accepts optional
`--linear-derivatives LOCAL_THREADS` arguments, preserving the FP32 probe
interface. FP16 probe filenames enable the core shaderFloat16 feature.

With an exclusive device lease and the capability-enabled private prototype:

```sh
python generate.py /tmp/linear-derivatives
python run.py /tmp/linear-derivatives --probe ./probe \
  --icd /path/to/private/prototype/icd.json --output hardware.json
```

The final driver intentionally rejects creating a device with this unsupported
feature enabled. Workspace evidence is in `artifacts/dxvk-quality-20261006/`:
`hardware.json` contains exact-bit outcomes and driver identity;
`hardware-cts/summary.json` and per-run CSVs distinguish prototype results from
final exposure; the six failing QPAs retain actual and expected values.
The accompanying bounds optimization passes the final 1,315-case focused
robustness/descriptor run with **915 passes, 400 skips and no failures, expected
failures or flakes**, identical to its baseline. The mini lease was released.
