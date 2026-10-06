# Apple9 FP32 denormal control

Measured 2026-10-06 on T8132, Apple M4 (G16G B1), Linux `7.1.13-m4-g16+`.
The compiler now advertises `shaderDenormFlushToZeroFloat32 = true`.
`shaderDenormPreserveFloat32` remains false. Consequently, vkd3d-proton's
requirement for **both** modes still prevents normal SM 6.2 progression.

The existing corpus's 201 failures previously labeled `DenormFlushToZero`
are **not 201 FP32 compiler failures**. All also declare `Float64`; their
unsupported-NIR diagnostics contain 64-bit packing or `f2f64`. This follow-up
corrects the earlier readiness report's attribution. All 579 FTZ32 entries
without FP64 already compiled and still compile. The 201 mixed FP64 entries
still fail; implementing FP32 FTZ does not implement FP64.

## Hardware observations

`generate.py` creates 42 authored compute shaders and 66 exact-bit input
tuples. Every dispatch echoes two input words and a per-invocation tag, and
checks an untouched-output sentinel. `run.py` checks normal-value controls,
integer identity/select transport, and, for explicit FTZ, the absence of
subnormal floating results. Undefined float-to-integer conversions are
recorded but are not treated as numerical controls.

The baseline was `db0867aa028`. Native instructions were captured from the
actual Vulkan compilations on the M4, not inferred from shader source alone.
Only our authored shaders and the open Mesa encoder were inspected.

| Family | Input behavior observed | Result behavior observed |
| --- | --- | --- |
| Add, multiply, FMA | Subnormal inputs act as signed zero | Subnormal final results flush. Compact and source-modifier forms agree; immediate multiply also flushes. |
| FMA intermediate product | An underflowing product survives within the fused operation when the final result is normal | `min_normal * 0.5 + min_normal` returns `00c00000`, not `00800000`. |
| Min/max | Comparisons treat subnormals as zero | The selected operand's bits survive. Reversing unequal subnormal operands exposes the tie/select behavior. |
| Comparisons | Positive and negative subnormals compare equal to zero and to each other | Boolean result; no floating output to flush. |
| Negate/absolute value | Implemented as integer sign-bit operations | Preserve subnormal magnitude. Optimized identity arithmetic can likewise become bit operations. |
| Floor/ceil | Subnormals act as signed zero; this differs from gradual-underflow floor/ceil | Integral result, including signed zero. Truncation and round-even also return signed zero, but those observations alone do not distinguish input flushing from correct rounding. |
| FP32 to integer/FP16 | FP32 subnormals convert to zero, with a sign for FP16 | These inputs are below the destination's representable range, so this does **not** independently prove DAZ. Normal FP32 values can produce FP16 subnormals. |
| FP16 to FP32 | FP16 subnormals are preserved by widening | `0001` becomes FP32 `33800000`; it is normal in FP32. Integer-to-FP32 results also cannot be FP32 subnormals. |
| Log2, inverse square root | Subnormal inputs act as signed zero | Log2 returns negative infinity; rsqrt returns signed infinity. |
| Square root | The factor-plus-multiply path treats subnormal inputs as signed zero | Returns signed zero. The earlier isolated factor probe agrees with this interpretation. |
| Exp2 | Tiny inputs return one, which cannot distinguish input flushing from rounding | `exp2(-127)` and `exp2(-149)` return zero rather than subnormal results. |
| Reciprocal | The current reciprocal-plus-two-FMA path behaves as DAZ | The tested subnormal quotient flushes. This experiment does not separately attribute every exceptional result to the bare reciprocal instruction. |
| Sine/cosine | The compiler's small-input sine shortcut returns the original bits; cosine returns one | Sine preserves subnormals without explicit FTZ handling. The native sine-factor instruction is not a complete sine operation. |
| Buffer atomic add | The memory update behaves like flushing addition | The new value flushes, but the returned **old value preserves its original bits**. Both paths are probed separately. |
| One-element subgroup min/max | Lowering can bypass all floating arithmetic | Returns the original subnormal unless the reduction's result is explicitly canonicalized. |

Examples separating the two arithmetic flush points:

* `00800001 + 80800000` produces `00000000`, although both inputs are normal
  and the exact result is `00000001`: output flushing.
* `00000001 * 7e800000` produces `00000000`, although preserving the input
  would produce the normal value `34000000`: input flushing.
* `fma(00000001, 7e800000, 3f800000)` produces `3f800000`, rather than
  `3f800001`: input flushing within FMA.
* Atomic add initialized with `00000001` returns old bits `00000001`, while
  its addition result with zero is stored as `00000000`.

### Instruction forms and mode selection

No usable FP32-preserve selector was found in the documented Apple9 machine
model. The tested normal, compact, immediate-multiply, and absolute-source
forms do not select preservation. This is bounded evidence, not an exhaustive
proof that no unknown hardware mode exists.

Existing clean-room T8132 evidence was consulted first:

* `EXP-0047-m4-numerical-behavior`: source-level FP32 flushing, FP16
  preservation, and min/max operand selection. It explicitly does not isolate
  every native instruction.
* `EXP-0074-m4-fp32-division-precision`: the validated division experiment,
  distinct from its quarantined predecessor.
* `EXP-M4-15-compare-select`: native comparison input flushing.
* `EXP-M4-55-sqrt-sine-assist`: isolated root-factor/rsqrt forms with operand
  control bytes `90`, `92`, `b0`, and `b2`. All four agree on denormal inputs.
  The production encoder identifies type/lifetime controls in this region;
  these are not evidence for a denormal-preserve switch.

These records are under `tmp/agx-re/experiments/` in the workspace. G17P and
T8140 observations were not substituted for the T8132 measurements.

## Compiler implementation

The [Vulkan floating-point rules](https://docs.vulkan.org/spec/latest/appendices/spirvenv.html)
allow FTZ operands to flush, while affected denormal results must flush.
Bit-preserving transport remains distinct from floating computation.

For explicit FTZ32, the compiler checks result bits using integer operations:
if the magnitude is below `00800000`, retain only the sign bit; otherwise
retain all bits. This preserves signed zero, normal values, infinities, and
NaN payloads. It avoids relying on an arithmetic identity that an optimizer
could remove. Native operations known to flush, and operations whose results
cannot be FP32 subnormal, need no redundant result check.

The pass runs after late algebraic optimization. There are also earlier
fixups where lowering would erase the source operation: the small-input sine
shortcut, `fcanonicalize`, and subgroup min/max reductions/scans. A singleton
cluster or first active scan lane can otherwise return raw data without ever
executing min/max. Floating atomic return values and derivative results are
handled separately from ordinary ALU results. Loads, stores, selections,
integer atomics, and bit-preserving exchanges are not blanket-flushed.

Preservation needs more work than these result fixups: arithmetic and
comparisons already discard subnormal inputs. No complete preserving
implementation was added. The existing generic FP32 software library is not
a drop-in solution: its `fmad` is separate multiplication and addition, not
the required fused FMA. Advertising preservation on that basis would be wrong.

## Validation

The candidate was loaded through an isolated ICD, with compression left at
its normal default and shader caching disabled. Its queried properties were
FTZ32 **1**, preserve32 **0**, and signed-zero/Inf/NaN preservation **1**.
Candidate library SHA-256:
`ee3b9a87741899336a4aaf780df5c0a61de3d0bccaf83e4c81438e062a2fa341`.

* 42 operations × 66 inputs = **2,772 outputs per probe matrix**. All transport
  and normal controls pass. All explicit-FTZ result checks pass, including
  atomic returns, singleton subgroup min/max, and preserved integer transport.
* A baseline repeat with native instruction logging matches all 2,772 outputs.
  The candidate in default mode also matches all 2,772 baseline output bits.
* **436 host compiler tests pass**, including sign/special-value
  canonicalization, the singleton-reduction lowering boundary, and compilation
  of derivatives in both default and FTZ modes.
* Read-only replay from the existing corpus: **579/579** FTZ32 entries without
  FP64 compile to native programs; **201/201** mixed FP64 entries still fail.

The focused CTS list contains all FP32 cases in `float_controls` and
`float_controls2`, FP32 extensionless cases, and independence-setting cases.
It covers compute, vertex, and fragment execution. It is not the full CTS.

| Same 4,196 CTS cases | Pass | Skip | Failure | Expected failure | Flake |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 2,692 | 1,504 | 0 | 0 | 0 |
| FTZ candidate | 3,328 | 868 | 0 | 0 | 0 |

Exactly **636** cases change from Skip to Pass; there are no other outcome
changes. No case in this list was excluded by the configured skip files.
No expected-failure baseline was applied. Unsupported preservation, rounding,
or mixed-width features still account for skips; skips are not passes.

Summaries and exact-bit observations are in
`artifacts/fp32-denorm-20261006/`: `hardware-baseline.json`,
`hardware-candidate-ftz.json`, `hardware-comparison.json`, `cts-summary.json`,
`cts-width-audit.json`, `cts-focused-compile.json`, and `host-tests.log`.
There is no new corpus copy. The mini lease was released after validation.

## Reproduction

Generate on the host with `glslangValidator` and `spirv-val` available:

```sh
python src/asahi/compiler/test/fp32-denorm/generate.py /tmp/apple9-denorm-probes
```

After acquiring the mini lease, copy the generated directory, `probe.c`, and
`run.py` to a test directory on the M4. Build the runner there with
`gcc -O2 -Wall -Wextra probe.c -lvulkan -o probe`, then run:

```sh
python3 run.py apple9-denorm-probes --probe ./probe --icd candidate/icd.json \
  --native --ftz --output ftz.json
```

Omit `--ftz` for default behavior. The runner prints and records the actual
device, driver, properties, library hash, exact result bits, and, with
`--native`, selected native instructions plus program hashes. `compile.py`
provides a separate host-only native-op inventory using the existing corpus
runner and DRM shim; it does not submit GPU work.
