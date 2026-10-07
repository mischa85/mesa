# FP32 DenormPreserve on Apple9

`agx_nir_lower_apple9_denorm_preserve` (in `agx_nir_lower_apple9_preserve.c`)
runs only for shaders that declare `DenormPreserve 32`. Each affected scalar
operation keeps its native instruction. A guarded `if` takes a software path
when an operand is subnormal or the native result may have been flushed. The
software path splits operands into normal mantissas and integer exponents,
computes on the mantissas natively, and repacks with integer
round-to-nearest-even.

Covered: fadd/fsub/fmul/ffma, flt/fge/feq/fneu, fmin/fmax, fsign,
floor/ceil/trunc/round_even/fract/fsat, and rcp/sqrt/rsq/log2 (positive
subnormal inputs) and exp2 (subnormal results for x in [-151, -126)).

Not handled, since their precision is outside the spec's requirements:
derivatives, floating atomics, and the native sin/cos shortcut (sine keeps
the input bits and cosine returns 1, both correct). Division by a subnormal
denominator is unspecified; subnormal numerators and quotients go through
the wrapped fmul/ffma of the rcp+FMA lowering.

## Validation

- `preserve.py generate OUT; preserve.py check OUT RESULTS`: exact oracle
  (Fraction) or spec ULP tolerances for transcendentals.
- Default path: the 7-corpus identity gate (latency/identity.py) is
  byte-identical except the one CTS program that declares DenormPreserve 32
  (expression_rearrangement.preserve_add_no_contraction).

## Notes

- `mix(x, y, 0.5)` returns +-inf for large finite x and y (e.g. 0x7e800000,
  0x7f7fffff). GLSL `mix` becomes `FMix`, which glslang never decorates
  NoContraction, so the flrp is inexact. Shared NIR then forms `(x + y) * 0.5`
  through `~fadd(fmul(a, b), fmul(a, c)) -> fmul(a, fadd(b, c))`
  (nir_opt_algebraic.py) or the inexact nir_lower_flrp path. An exact flrp
  takes `replace_with_strict` and never gets factored, so this is permitted
  fast-math range loss, not a preserve bug. Left alone.
- `sign(NaN)` is undefined in GLSL.std.450 `FSign`; native returns 0.

## Results (2026-10-06, M4 Air, apple9/fp32-denorm-preserve-advertise 5873ff7)

- `preserve.py`: 29 ops x 1225 inputs, all exact or within tolerance, no GPU faults.
- DXC end-to-end: `dxc/*.hlsl` built with DXC 1.9.2609 (`-T cs_6_2 -denorm
  preserve`) and dxil-spirv 7dc52786 (`--ssbo-uav --ssbo-srv`; this is
  vkd3d-proton 44cf7c20's pin), which emits `DenormPreserve 32`. Checked with
  the same oracle (`expected.json` ops renamed to `dxc_*`): all pass, except
  that min(-0, +0) may return +0, which is fine because DXIL doesn't declare
  SignedZeroInfNanPreserve.
- CTS against compile-time2 114b925 on the Air: float-controls has 617 Skip->Pass
  and no other changes, and the fp32 denorm_preserve cases are 218 pass and
  6 skip (conv_from_fp64, no FP64). normal, memory, robust-descriptor and
  forced-spill are identical. The exact-bit probe kit (default and FTZ) is
  identical.
- vkd3d-proton 44cf7c20 built natively for aarch64, running
  `dxc/vkd3d-shader-model.c`: D3D12_FEATURE_SHADER_MODEL is 0x60 on the base
  and 0x65 with FP32 preserve advertised.
