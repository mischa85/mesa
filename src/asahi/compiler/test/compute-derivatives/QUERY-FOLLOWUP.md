# Compute derivatives: LOD query completion

2026-10-06, T8132 / Apple M4 G16G B1. Local branch
`apple9/compute-derivative-query` starts at integration-next `a852a6c55a44`
and merges the earlier `apple9/compute-derivative-lod` work.

The four remaining query CTS failures are fixed. The G16 capability filter now
exposes `VK_KHR_compute_shader_derivatives` and
`computeDerivativeGroupLinear`. `computeDerivativeGroupQuads` remains false;
mesh/task derivatives remain unsupported. This is a local candidate, not an
installed system driver or a claim of full Vulkan conformance.

## Root cause and retained model

The failing cases query mip 0 and mip 1 at local sizes 16×1×1 and 4×4×1.
These use **linear** groups: four consecutive local invocation indices form a
derivative group, even in a two-dimensional workgroup. Direct derivative and
explicit-gradient controls already validated this mapping. Local-X/local-Y
quad grouping would be incorrect for these cases.

The 1D image width is 16. Coordinate differences 0.08 and 0.10 produce
footprints 1.28 and 1.6 texels, giving raw LODs `log2(1.28) = 0.356144` and
`log2(1.6) = 0.678072`. Nearest mip selection gives levels zero and one. The
old native fragment-query path returned zero in compute, so it failed both
query variants. Adding the query flag to gradient samples returned image
colors rather than query results; that discarded experiment is not retained.

The compiler calculates the compute query through ordinary NIR arithmetic,
using the validated linear derivative lowering and runtime sampler/view state:

- Form derivatives after projection, excluding array layers and comparison
  values. Scale spatial gradients by view dimensions. Project cube gradients
  with the same quotient-rule geometry as the common cube sampling lowering.
- For 1D/2D anisotropic sampling, use squared major length
  `max(dot(dx, dx), dot(dy, dy))`. The squared minor footprint is squared
  parallelogram area divided by squared major length (zero for a zero or 1D
  footprint). Effective squared footprint is
  `max(minor_squared, major_squared / max_anisotropy²)`.
  Hardware probes distinguish this from incorrectly using the shorter
  derivative length for skew or collinear gradients.
- Native 3D sampling ignores anisotropy in the tested path. Cube sampling is
  already lowered through scalar LODs. Their queries therefore use the
  isotropic major footprint, matching those sample paths.
- Calculate `0.5 * log2(footprint_squared)` and add sampler bias, bounded by
  the advertised bias limit. Preserve negative infinity for zero footprint.
- Return the biased, unclamped LOD separately from the mip selection after
  sampler limits, view levels, view minimum LOD and nearest/linear mip mode.
  Null descriptors return two zero components; dummy zero-page descriptors
  retain their logical empty state in the runtime metadata.

Fragment queries retain their native path. No capture-specific sequences,
fixed registers, replay dependencies or new native instruction encodings are
introduced. The anisotropy field uses existing runtime sampler-table space.

Two common NIR folding corrections were needed by the controls: zero explicit
gradients become LOD negative infinity, since LOD zero plus positive sampler
bias incorrectly selects a higher mip; and folding must stop when opaque
backend operands are present. In particular, a packed gradient minimum LOD
cannot be reinterpreted as an explicit-LOD operand. The latter fixes all 24
zero-gradient array/view-minimum compilation failures from the intermediate
candidate. The missing `ddy` source guard is also corrected.

## Native validation

The tested production code is `b753d0c32f2`; subsequent commits extend only the
probe matrix and its reference tolerance. Private library SHA-256:
`53a29c8085660c6c457d75e1f71c5aa962c800384642eabab2695ec4444ee213`.
Every probe records Apple M4 G16G B1 and the candidate driver identity.

| Focused derivative CTS | Pass | Fail | Skip | Expected fail | Flake |
| --- | ---: | ---: | ---: | ---: | ---: |
| Earlier implicit-sampling fix | 86 | 4 | 459 | 0 | 0 |
| Completed query candidate | 90 | 0 | 459 | 0 | 0 |

| Texture probe matrix | Cases passed | Rows checked |
| --- | ---: | ---: |
| Original dimensions/sampler matrix | 336 | 18,144 |
| Affine footprints, original decimal rotation | 1,344 | 72,576 |
| Affine footprints, exact binary rotation and higher non-cube LOD | 1,344 | 72,576 |
| View minimum LOD 1.25 | 336 | 18,144 |
| Null descriptors | 336 | 18,144 |
| Total | **3,696** | **199,584** |

There are zero failing cases, bad rows or process errors. Seven image forms
(1D, 1D array, 2D, 2D array, 3D, cube and cube array), two workgroup shapes,
three workgroups per dispatch, varying array layers, biases, clamps, base mip
views, nearest mip selection and anisotropy are covered. Affine cases add
elongated, rotated, skew and depth-varying gradients. Anisotropic queries must
agree with mip-tagged sampling, rather than merely agreeing with another
query implementation; isotropic arms additionally use analytic LOD references.

The cube explicit-gradient control allows one Q6 LOD step plus 0.002: an
FP32 subtraction of input coordinates and its analytic gradient literal can
fall on opposite sides of a Q6 boundary. Eight old decimal-rotation controls
exposed this rounding difference. This tolerance change is explicit, not an
expected-failure classification; query/sample and analytic checks retain their
0.04 tolerance, and non-cube gradient controls retain 0.002. The second affine
matrix uses binary-exact rotation coordinates as a separate check.

All **459 host compiler tests pass**, and the aarch64 Vulkan driver builds.
The kernel journal has no new entries during the native derivative/matrix run;
input forwarding remained active. Normal compression is enabled and shader
caches are disabled. No system driver installation, kernel change or reset was
needed. Hardware access uses exclusive mini leases.

### Shared NIR folding regression

Because the folding corrections above change common NIR, the same driver was
also run on integration-next's focused native lists (normal, forced spill,
memory and robust descriptor; two jobs, 60-second timeout, compression on,
cache off, `AGX_SPILL_COALESCE=1`). Results match the integration-next
`a852a6c55a44` native baseline case for case:

| List | Pass | Skip | Changed statuses |
| --- | ---: | ---: | ---: |
| normal | 463 | 1 | 0 |
| forced spill | 139 | 1 | 0 |
| memory | 1,034 | 1,019 | 0 |
| robust descriptor | 915 | 400 | 0 |
| Total | **2,551** | **1,421** | **0** |

There are no failures, expected failures or flakes, and the kernel journal has
no new entries for the run. Comparison:
`artifacts/compute-derivative-query-20261006/regression-compare.json`.

## Reproduction and provenance

Workspace evidence is in `artifacts/compute-derivative-query-20261006/`:
`hardware-area/candidate/manifest.json`, `derivatives/results.csv`, all five
`textures*.json` files with raw rows, `hardware-area/kernel-new.log`, and
`area-host-tests.log`. Intermediate failed runs remain separate under
`hardware/candidate/`; they are not the final results above.

Build `mesa_clc`, `vtn_bindgen2` and `asahi_clc` from the same source revision
before the cross build. Point the cross build at these matching host tools.
An ICD with bare `libvulkan_asahi.so` can load the installed driver: use an
absolute candidate library path and verify both SHA-256 and runtime identity.

```sh
python generate-textures.py /tmp/compute-textures
python generate-textures.py /tmp/compute-affine --extended
python generate-textures.py /tmp/compute-view-min --view-min 1.25
python run-textures.py /tmp/compute-textures --probe ./texture-probe \
  --icd /absolute/candidate/icd.json --output textures.json
python run-textures.py /tmp/compute-textures --probe ./texture-probe \
  --icd /absolute/candidate/icd.json --null-image --output null.json
```

The image-view-minimum harness requests the existing vkd3d application opt-in.
The extension exposure is limited to G16; the older-GPU capability tables are
unchanged. Buffer int64 atomics are still unimplemented and assessed separately
on `apple9/int64-atomic-assessment`.
