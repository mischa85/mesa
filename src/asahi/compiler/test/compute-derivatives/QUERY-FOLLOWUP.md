# Compute LOD query follow-up

WIP on `apple9/compute-derivative-query`, based on integration-next
`a852a6c55a44` and merged with `apple9/compute-derivative-lod`.

The earlier six failures became four after implicit compute samples were
lowered through explicit gradients. The four remaining cases are mip-0/mip-1
LOD queries, each at local sizes 16×1×1 and 4×4×1. These are **linear** derivative
groups: four consecutive local invocation indices form a group, even in a
two-dimensional workgroup. The separate quad-group feature remains false.

Direct derivatives and explicit-gradient sample controls pass with this lane
mapping. The remaining query path instead reuses the fragment implicit LOD
query encoding. It returns zero in the existing compute experiments. Adding
the query flag to a gradient sample did not produce query results; that
experiment was removed in the previous series.

The new WIP calculates the query from ordinary NIR derivatives, spatial view
dimensions, projected cube gradients, sampler anisotropy, bias, clamping, and
mip selection. Those derivatives use the existing linear shuffle lowering.
The two query components represent the selected view-relative mip and the
biased, unclamped LOD. Array layers do not contribute derivatives. Fragment
queries retain their native path. Cube queries follow the existing common
cube-gradient scalar-LOD lowering.

The texture probes also exposed a common NIR optimization issue: converting
zero explicit gradients to LOD zero lets positive sampler bias move sampling
away from the minimum level. The WIP uses negative infinity for the zero
footprint before bias and sampler clamping.

Host validation so far:

- Complete aarch64 Vulkan driver build succeeds.
- All 459 compiler tests pass.
- All 336 existing texture shaders compile through the host Vulkan path.
- All 1,344 additional affine-footprint shaders compile. These exercise
  rotated, unequal, skew, and depth-varying gradients with both workgroup
  shapes and the existing sampler/view configurations.

The probe runner now checks query/sample agreement for anisotropic cases too,
using mip-tagged image data. Native execution remains required to validate the
software footprint against the texture unit, especially its allowed footprint
approximations. The WIP capability bits are enabled only on this isolated
topic for that testing. This is not yet an integration-ready exposure change.

Artifacts are under `artifacts/compute-derivative-query-20261006/` in the
workspace. The queued native run follows integration-next's CTS/float-control
validation and uses a separate mini lease. The candidate library is pinned by
`driver-manifest.json`; the probe and CTS logs must be reviewed before claiming
that the four failures are fixed.
