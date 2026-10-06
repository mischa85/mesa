# Apple9 FTZ code generation

2026-10-06; branch `apple9/ftz-codegen`, based on
`apple9/compiler-integration` (`9586556102f`). Implementation commits:
`9a08259fc73`, `20d22d97de5`, `d5acfbf127b`, `0cc8bfaa8b0`.

The expensive checks were on bit-preserving float operations whose inputs
were already canonical, and on results used only by native arithmetic that
treats subnormal inputs as signed zero. Native `fadd`, `fmul`, and `ffma`
already bypassed explicit result flushing. Float-controls2 did not introduce
blanket exactness or disable permitted contraction.

## Inputs and attribution

The Lethal capture's 46 DXVK modules were regenerated using its actual public
DXVK revision, `685301564ea3486`, and cached DXBC. Restoring the capture's
descriptor decorations reproduces every original SPIR-V module byte for
byte with float controls disabled. Five built-in modules are unchanged.
The three regenerated configurations are no float controls, FTZ plus
float-controls2, and FTZ without float-controls2. All 138 generated modules
validate. Compiler, pipeline state, and spill coalescing are held constant.

The hot programs are compute `cs.deace2b1d0fc6801a441707df5e067bd`
(pipeline `a7fe66611aa32aa4`) and fragment
`fs.205919e9b91a146cac01c77f3384a2b0` (pipeline `a9a9160b49129f97`).
Counts below include only the main function, excluding its attached preamble
and control-flow syntax. Each SSA definition, store, and jump counts once.

To separate interacting transformations, a private host-only diagnostic
compiler replaces the flush helper with identity. This is an attribution
control, not a valid FTZ implementation or a shipped driver. FTZ without
float-controls2 under this control produces exactly the no-controls native
code hashes, including both preambles.

| Final NIR contribution, no controls to FTZ + float-controls2 | Compute | Fragment |
| --- | ---: | ---: |
| Explicit flush classification: `iand` | +942 | +100 |
| Explicit flush classification: `ult` | +471 | +50 |
| Explicit flush selection: `bcsel` | +471 | +50 |
| Operand delivery for these checks: `load_preamble` | +942 | +100 |
| Constant cleanup attributable to the checks | -4 | +1 |
| **Flush-related subtotal** | **+2,822** | **+301** |
| Lost FMA contraction | 0 | 0 |
| Lost algebraic folds from stricter flags | 0 | 0 |
| Rounding-mode handling | 0 | 0 |
| Other float-controls2 algebraic changes, net savings | -151 | -9 |
| **Total** | **+2,671** | **+292** |

Total final NIR grows from 9,331 to 12,002 compute instructions and from
1,245 to 1,537 fragment instructions. The float-controls2 savings account
for every remaining opcode delta:

| Opcode | Compute | Fragment |
| --- | ---: | ---: |
| `load_preamble` | -25 | -4 |
| `bcsel` | -48 | -3 |
| `fabs` | +2 | +2 |
| `fadd` | -1 | 0 |
| `feq` | -36 | 0 |
| `flt` | -15 | -3 |
| `fmax` | +12 | +1 |
| `fneg` | -2 | -2 |
| `fsat` | +1 | 0 |
| `imax` | -16 | 0 |
| `imin` | -20 | 0 |
| `phi` | -3 | 0 |

The `ffma` counts remain 406 compute and 15 fragment. Native counts include
allocation, copies, and instruction selection, so they do not have a
one-to-one correspondence with NIR. The native compute increase of 1,499
decomposes as +1,632 from flush-related effects and -133 from
float-controls2; the fragment increase of 164 decomposes as +166 and -2.

## Flags reaching the compiler

`spirv_to_nir.c` maps `DenormFlushToZero` and `RoundingModeRTE` into
`shader.info.float_controls_execution_mode`, separately from the per-width
signed-zero/Inf/NaN preservation defaults. `FPFastMathDefault` maps each
permission separately. `vtn_alu.c` applies instruction-level fast-math
decorations and `NoContraction`; `nir_opt_algebraic` requires contraction
permission when combining multiply and add. These paths are unchanged.
This separation follows the public
[float-controls2 definition](https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_shader_float_controls2.html).

In these compute inputs, 1,049 non-exact float instructions initially
preserve signed zero, Inf, and NaN, with another 273 preserving Inf and NaN.
With float-controls2, 1,283 preserve Inf and NaN after folding. The 131 exact
instructions preserving all three, 15 other exact instructions, and 265
fast instructions remain unchanged. Fragment exact/fast counts likewise
remain 8/77. Its 56 signed-zero-preserving and 33 Inf/NaN-preserving
instructions become 87 Inf/NaN-preserving instructions after folding.
Execution-mode bits change from zero to `0x90` (FTZ32 plus RTE32), without
extra native rounding-mode instructions.

## General compiler change

The pass classifies the original SSA graph before rewriting any result:

* Sign, absolute value, saturation, min/max, and canonicalization need no
  flush when every input component is already zero, normal, Inf, or NaN.
  Constants, float-producing ALU operations, moves, selects, and phis can
  establish this fact. Unknown or cyclic provenance falls back to flushing.
* A potentially subnormal result needs no explicit flush when every use is
  a native FP32 DAZ arithmetic operation or comparison, possibly through
  moves or vector construction. Raw stores, integer uses, other intrinsics,
  and bit-preserving float operations prevent this optimization.
* These two rules cannot justify each other circularly: sign/min/max users
  are excluded from the DAZ-consumer rule. Their producer must really be
  canonical before their own check can disappear.
* Canonicality survives a compiler-generated preamble uniform transfer.
  The proof inspects the preamble's stored value per component; it does not
  assume that arbitrary uniform loads are canonical. A preamble store is a
  raw-bit use, so it retains a required flush on its producer.

The final pass runs after preamble extraction and its late algebraic
legalization, immediately before backend scheduling/lowering. Earlier math
lowering retains semantic `fcanonicalize` nodes until this boundary. This
also covers operations introduced by preamble legalization. Only constant
folding, copy propagation, CSE, and DCE follow the flush pass; no later
algebraic pass may recreate a bit-preserving float result. Existing sine,
subgroup, atomic-return, and derivative handling remains in place.

No fast-math permissions are broadened. An exact operation may lose a check
only when its observable behavior is preserved. Unit tests independently
check `no_contract`, `no_reassoc`, and `no_transform` permissions.

## Final static result

All hot-program numbers use `AGX_SPILL_COALESCE=1`, as does the game driver.
Spill counts are static stores plus loads, not executions.

| Main program metric | No float controls | Original FTZ + FC2 | Fixed FTZ + FC2 |
| --- | ---: | ---: | ---: |
| Compute instructions | 6,028 | 7,527 | **6,031** |
| Compute spill stores + loads | 131 | 89 | **67** |
| Compute GPRs | 96 | 96 | 96 |
| Compute uniform references | 3,092 | 4,015 | 3,067 |
| Compute standalone waits | 151 | 131 | 134 |
| Compute preamble instructions | 521 | 521 | 521 |
| Fragment instructions | 866 | 1,030 | **876** |
| Fragment spills | 0 | 0 | 0 |
| Fragment GPRs | 23 | 24 | 26 |
| Fragment uniform references | 289 | 385 | 281 |
| Fragment standalone waits | 2 | 2 | 2 |
| Fragment preamble instructions | 157 | 159 | 157 |

The fixed FTZ-without-FC2 control is 6,195 compute / 878 fragment
instructions, with 71 / 0 spills. FC2's permitted folds remain useful.
Explicit checks fall from 471 to 40 compute and from 50 to 3 fragment.
The surviving compute checks follow 8 sine-shortcut selects, 6 reciprocals,
16 maxima, 1 negate, and 9 minima. Fragment retains one maximum, one minimum,
and one reciprocal check.

Across the full FTZ-reconstructed Lethal capture, main compute instruction
totals fall from 28,329 to 24,358, fragment from 3,327 to 3,046, and vertex
from 1,378 to 1,342. Total compute spills fall from 151 to 125; no individual
main program gains spills. Fragment/vertex remain spill-free. Reduced
static counts are not a measurement of game frame time; fragment GPRs and
the hot compute's standalone wait count are still higher than the original
FTZ arm, so hardware timing remains necessary.

## Validation and handoff

All 449 compiler host tests pass. The six existing host corpora retain all
7,020 outcomes: 6,995 compilations pass, 20 Lethal pipeline-library entries
have no shader, and five pre-existing Willems compilations fail. There are
zero outcome changes, spill increases, or added waits against the integration
reference. This existing corpus comparison keeps spill-coalescing settings
identical to its reference; it is separate from the reconstructed FTZ game
comparison above.

The 780-entry FTZ-focused host corpus completes: all 579 FP32 entries without
FP64 compile; all 201 mixed FP64 entries retain their existing unsupported
FP64 failure. The actual x86 game library compiles all 69 reconstructed
Lethal pipeline entries (49 compiled, 20 shaderless). Its queried properties
advertise FTZ32, float-controls2, RTE32, and signed-zero/Inf/NaN preservation.

Native hardware CTS for this optimization is pending the mini lease; these
host results do not replace it. Main owns the mini for game timing. The
prepared native library SHA-256 is
`e8402b2e30c034d18aa510eac40bf99221c3c58a45d47269c107f79ae6bac663`.

The game driver is under workspace-relative
`artifacts/lethal-regression-static-20261006/drivers/integration-ftz-codegen/`
and is recorded in that artifact root's `driver-manifest.json`. SHA-256:
`1ba1d386897a62e41b1d04947364c9e566fb0eaf913845085a00bde6be726ce3`.
It retains the main thread's runtime/identity overlays, advertises FTZ and
float-controls2, and contains neither the scoreboard nor address experiment.
No driver was installed and nothing was pushed.

Raw final NIR, opcode accounting, attribution controls, compile logs, and
per-program metrics are under `artifacts/ftz-codegen-20261006/`.
`nir-counts.json`, `flush-origins.json`, `uniform-proof-ftz.json`, and
`full-ftz-stage-comparison.json` provide the detailed accounting. Full-corpus
metrics are `artifacts/lethal-pressure-20261006/ftz-final-*.json` and
`artifacts/lethal-regression-static-20261006/ftz-codegen-final*.json`.
