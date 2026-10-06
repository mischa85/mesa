# Publication-file validation and allocator audit, October 5

An isolated native T8132 Vulkan texture probe compared three variants of our
shader. Each covered two textures and six sampler choices. It moved the
publication tuple to p28..p31 and observed ordinary GPR r28/r29 with exact
float-bit sentinels 0x3e800000 and 0x3f400000.

- Observer control writes the GPR sentinels after texture consumption.
- Logic publication writes the sentinels before the normal LOD publication.
- Direct coordinate publication writes them before two `FLOAT2_EXPORT` FMUL
  operations publish x/y to p28/p29, retaining the remaining LOD publication.

All twelve outputs in each candidate exactly match the observer: sample R/G
and both GPR sentinels survive. The stock twelve-case texture control also
passes. No hang/reset occurred. This supports separate publication/GPR files
for both tested forms. It does not characterize arbitrary publication ALU
opcodes. The private diagnostic hook was not added to the production compiler.
Local sources, build logs and outputs are in `tmp/coordinate-file-probe/`.

The shared allocator was then audited on all 10,161 CS2 programs, including
actual common-IR destinations and value-map entries, rather than only packer
numbers. The audit's main-program metrics exactly match the frozen baseline.
Every one of 31,639 publication tuples (126,466 words) is marked publication,
has no GPR value-map entry, and contributes zero common-IR GPR destinations.
The 96-GPR population contains 5,230 tuples / 20,236 words, also with zero GPR
destinations. These totals include all publication tuples, not just texture
coordinates. The narrow `TEXTURE_COORDS` encoding occurs 73 times (9 fragment,
64 compute), with no occurrence in a 96-GPR program.

`apple9_vir_emit_texture` represents these results as `PUBLICATION_TUPLE`.
`apple9_publication` marks them before common dataflow creation, which assigns
no ordinary SSA/GPR destination. Thus the machine table's destination field
does not make coordinate publication occupy an ordinary allocator GPR. No
allocator correction was needed. Evidence is retained under
`tmp/cs2-pressure-20261005/uniform-census/`, especially
`audit-whole-census.jsonl` and `shared-coordinate-audit.json`.
