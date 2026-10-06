# Compute implicit sampling through explicit gradients

2026-10-06, T8132 / Apple M4 G16G B1, kernel `7.1.13-m4-g16+`.
The separate `apple9/compute-derivative-lod` branch builds on validated
`apple9/compiler-integration` (`9586556102f`). It fixes both remaining implicit
sampling CTS failures. Four compute LOD-query failures remain, so neither
`VK_KHR_compute_shader_derivatives` nor `computeDerivativeGroupLinear` is exposed.
This follow-up is not included in the integration hand-off.

## Retained compiler model

Implicit texture sampling in linear compute derivative groups becomes explicit
spatial gradients, using the validated quad-shuffle derivative lowering. Array
layers and shadow comparison values do not contribute gradients. Instruction
bias scales gradients by `exp2(bias)`. The existing texture lowering handles
1D, arrays, 3D and cube operations. Common projective lowering now precedes
formation of gradients, including projection of shadow comparators. Late
zero-gradient folding can introduce explicit LODs; the existing LOD packing
pass runs again before instruction selection to normalize these operands.

There are no new native encoding bits, fixed register assignments or capture
sequences. The failed gradient/query encoding and its special query IR were
removed. Existing native query selection is unchanged.

## Hardware results

All runs use private drivers, normal compression, disabled shader caches and an
exclusive mini lease. No driver was installed, kernel changed or target reset.

| Focused derivative CTS | Pass | Fail | Skip | Expected fail | Flake |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original capability-enabled derivative prototype | 84 | 6 | 459 | 0 | 0 |
| Retained sampling lowering, temporary capability exposure | 86 | 4 | 459 | 0 | 0 |
| Final driver, capability exposure removed | 0 | 0 | 549 | 0 | 0 |

The two newly passing cases are `compute.lod_op.sample.linear` at mip 1 for
16×1×1 and 4×4×1 workgroups. The four failures are `compute.lod_op.query.linear`,
mip 0 and mip 1, at both shapes. The sampler fix does not justify advertising
the extension.

The first experiment also combined the native query flag with explicit
gradients (or explicit LOD after cube lowering). The original six-case run
reported four passes and two failures. Broader probes showed why two query
passes were misleading: these combinations return sampled image RG colors,
not LODs. The mip-1 image color happened to equal the expected query result.
For example a 2D LOD-1 probe returned sample/query-X 2 and query-Y 0, while its
expected query was (1,1). This invalid combination was removed before the
86/4/459 run above.

## Broader probe evidence and limits

`generate-textures.py`, `texture-probe.c` and `run-textures.py` provide 336
cases with 18,144 checked rows across seven image dimensions/array forms,
4×4×1 and 20×1×1 workgroups, negative/positive/constant-zero footprints,
fractional sampler biases, LOD clamps, base mip views, nearest mip rounding
and anisotropy. Array layers alternate independently in each lane. Each row
includes input echoes and two tags; all dispatches and transport checks pass.

All 280 isotropic implicit-sampling cases match the analytic mip-color
reference. All 56 anisotropic cases match their explicit-gradient controls;
their implementation-dependent query LOD is recorded without an analytic
assertion. The complete harness outcome is **56 pass / 280 fail**, because
queries are still incorrect. This is not an all-pass feature validation.

Fourteen constant-coordinate explicit-gradient controls, with positive sampler
bias 0.5 and no effective minimum clamp, separately return 1.5 instead of the
expected base-level color 1 (756 rows). Their implicit-sampling counterparts
return 1 correctly. This is consistent with the existing common NIR
`try_fold_txd_to_txl` replacing zero gradients with explicit LOD zero before
sampler-bias lowering. It remains a separate follow-up; common NIR was not
changed by this series. No query failures or control discrepancies are counted
as expected failures or hidden from the raw results.

## Host checks and provenance

All **445 compiler unit tests pass**, including new dimension/array coverage
and projected shadow-comparator coverage. The final compiler replay matches
the integration's complete records exactly for 69 Lethal Company, 160 CS2,
268 Willems, 17 vkmark and 768 CTS entries (1,282 total). The five existing
Willems compiler failures and twenty shaderless GPL entries are unchanged.

The tested sampling compiler is `d982ad7039c` (formerly `f31f2f615a2` before
rebasing onto the integration's documentation commits). Capability removal is
`6e06ba8f60e` (formerly `097229ea503`). Compiler/runtime source content is
unchanged by that rebase. Private library SHA-256 values:

* Sampling with temporary capability exposure:
  `57f59321f97ac5930695a69ec8bd8bd9d57d93de04d1023a719d3d043a387e46`
* Final unadvertised driver:
  `83a1886c403cf0094b012d77bd464099b036107392f57e53007a8cc0c95d627c`

Workspace `artifacts/compiler-integration-20261006/` retains
`lod-clean-host-tests.log`, `lod-sampling-replay-comparison.json`,
`lod-sampling-provenance.json`, `lod-hardware-summary.json`, CTS CSVs/QPAs under
`hardware/lod-*`, and both `hardware-textures-{initial,sampling}.json` with raw
rows. `texture-summary.json` separates individual checks. The kernel journal
has no new entries during these checks, and the mini lease is released.

To reproduce the broader probes, generate SPIR-V and input files, compile the
C harness against Mesa's Vulkan headers, then use a private capability-enabled
driver under a device lease:

```sh
python generate-textures.py /tmp/compute-textures
python run-textures.py /tmp/compute-textures --probe ./texture-probe \
  --icd /path/to/private/icd.json --output hardware-textures.json
```

Further work needs a validated compute LOD-query contract or a complete query
lowering that preserves sampler and view semantics, including anisotropy.
The tested gradient/query combination supplies no such contract.
