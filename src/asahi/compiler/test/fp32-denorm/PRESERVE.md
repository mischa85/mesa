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
