# Linear compute derivatives on Apple9

2026-10-06, T8132 / Apple M4 G16G. Implementation and host tests are complete;
GPU execution validation is pending the exclusive mini lease. The capability
change is still a local WIP until that validation completes.

## Model

The [KHR extension](https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_compute_shader_derivatives.html)
defines linear derivative groups as four consecutive local invocation indices.
For a quad with values `a,b,c,d`, fine X derivatives use `b-a` for the first
row and `d-c` for the second; fine Y uses `c-a` and `d-b` by column. Coarse X
and Y use `b-a` and `c-a` respectively across the quad. Default derivatives
choose the fine form.

The compiler expresses these pairs with existing subgroup shuffles and
subtraction. The existing shuffle lowering accounts for Apple's quad-uniform
low index bits. It does not introduce a new instruction encoding or assume
that the fragment derivative opcode works in compute. Only the linear mode is
implemented. Quad-layout compute and mesh/task derivatives remain unsupported.

The execution check must also establish that compute subgroup lanes match
consecutive local indices for multidimensional workgroups, and that existing
native implicit texture sampling / LOD query behavior satisfies linear groups.
Compiling explicit derivative instructions alone is insufficient to expose the
extension. SM6.6 still has other blockers even if this one is removed.

## Host validation

All 24 previously failing linear modules compile: scalar, vec2, vec3 and vec4,
with default/fine/coarse derivatives at workgroup sizes 16×1×1 and 4×4×1.
The sixty quad-mode failures remain outside this implementation.

The compiler test suite passes 439 tests. New tests check all six derivative
operations over all 32 lane indices using nonlinear `f(i)=i²`, so the expected
results distinguish both axes, both rows/columns, coarse selection and quad
bases. A separate test compiles all six operations at vector widths 1–4.

## Focused hardware protocol

`generate.py` creates 63 authored probes: six derivative forms plus lane-ID
checks, at nine workgroup shapes. Each dispatch has three workgroups. Inputs
are exact integer bit patterns for `float(local_index² + 100*group_index)`.
The shader echoes its inputs and a per-row tag; the harness checks every row,
its sentinel, the exact result bits and the reported device/driver.

Shapes are 1×1×4, 2×2×1, 2×6×1, 3×4×1, 20×1×1, 4×4×4, 8×8×1,
1×1×64 and 32×32×1. They cover axes smaller than a quad, non-power-of-two
sizes, partial subgroups, multiple subgroups and the 1,024-invocation limit.
All generated SPIR-V passes `spirv-val --target-env vulkan1.2`.

After acquiring the mini lease, build the reusable exact-bit harness from
`../fp32-denorm/probe.c` against the Mesa Vulkan headers. It accepts the optional
`--linear-derivatives LOCAL_THREADS` arguments while preserving the existing
FP32 probe interface. Run:

```sh
python generate.py /tmp/linear-derivatives
python run.py /tmp/linear-derivatives --probe ./probe \
  --icd /path/to/private/candidate/icd.json --output hardware.json
```

The focused CTS list contains 549 `compute_shader_derivatives` cases, including
explicit derivatives, quad operations, index mapping, implicit sampling and
LOD queries, with unsupported quad/mesh/task cases retained as skips. A separate
169-case descriptor-indexing and robustness list covers the accompanying safe
uniform-descriptor hoisting optimization. Baseline and candidate outcomes must
be compared separately for passes, failures, skips, expected failures and
flakes. No full CTS run is needed.
