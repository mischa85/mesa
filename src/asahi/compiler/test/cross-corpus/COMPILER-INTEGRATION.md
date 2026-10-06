# Apple9 compiler integration

`apple9/compiler-integration` combines the allocator/spill/uniform/UBO/scheduler/
publication work, FP32 flush-to-zero, robustness folding, safe descriptor
hoisting, and explicit linear derivative lowering. Compute derivatives remain
unadvertised. No source merge was necessary: the three input tips already form
one linear history. The integration retains their original ancestry and applies
no duplicate cherry-picks. Its compiler/runtime tree is exactly `8848a20233d`.

| Input branch | Included tip |
| --- | --- |
| `apple9/spill-loops-coalesce` | `dfa19d1e0dd` |
| `apple9/fp32-denorm` | `d427e44dffa` |
| `apple9/dxvk-codegen-derivatives` | `8848a20233d` |

The compute texture LOD experiment is separate on `apple9/compute-derivative-lod`.
It is not part of this integration hand-off.

## Host validation

All **443 compiler tests pass**. A fresh compiler snapshot, including every
private compiler header and object, was linked against the same fixed host-only
frontend used for the DXVK measurements. The CPU DRM shim makes no GPU
submissions. The comparison checks complete per-entry JSON records, including
outcomes, diagnostics, final main and preamble records, instruction mix, GPRs,
spills, waits and uniform metrics; it excludes timings.

| Population | Entries | Outcomes | Differences from the retained DXVK results |
| --- | ---: | --- | ---: |
| Lethal Company recorded pipelines | 69 | 49 compile; 20 shaderless GPL state/link entries | 0 |
| CS2 recorded-pipeline sample | 160 | 160 compile | 0 |
| Willems | 268 | 263 compile; 5 existing compiler failures | 0 |
| vkmark | 17 | 17 compile | 0 |
| CTS stratified sample | 768 | 768 compile | 0 |
| Focused robustness/descriptor shaders | 5,738 | 5,738 compile | 0 |
| Total | 7,020 | All previous outcomes retained | 0 |

The expected reference is the *combined* retained DXVK result, which already
includes both older branches. It is not a requirement that robustness-optimized
code equal the pre-optimization allocator/FTZ metrics. The previously measured
[Lethal improvements and cross-corpus tradeoffs](DXVK-CODEGEN.md) are preserved
exactly. As before, only CS2 uses the host replay layout-limit override; these
are compilation checks, not game execution results or a full CTS run.

## Hardware validation

Pending an exclusive mini lease between the main thread's launch-loop phases.
The private ARM64 library is built, SHA-256
`cc80df6f90c64880d274a528511b68d8f23d97f9d0d5e726466751f1907a88de`.
Prepared cases reuse the prior normal (464), forced-spill (140), FP32 float
controls (4,196), robustness/descriptor (1,315), and derivative-exposure (549)
sets. Default compression stays enabled. The driver is not installed system-wide.

## Reproduction and evidence

Workspace `artifacts/compiler-integration-20261006/` holds the input refs/tree,
build/link provenance, fresh per-entry metrics, exact comparison, host test log,
and hardware case lists/scripts. Corpus archives/databases are read in place;
no new corpus copy was made. Replay uses `measure-robust.py` with the fresh ICD
and populations `lethal cs2 willems vkmark cts robust`. `comparison.json` checks
these against `artifacts/dxvk-quality-20261006/final-*.json`.
