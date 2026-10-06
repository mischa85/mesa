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

The allocator series' original **10,737-entry CTS population** was also
replayed on the retained DXVK compiler and this integration: both produce
10,421 successful compiles, 191 compiler failures and 125 crashes. Every
outcome, diagnostic, final program and preamble record matches exactly. This
population overlaps the samples above and must not be added as distinct shader
coverage. Failures and crashes are retained separately, not called passes.

The expected reference is the *combined* retained DXVK result, which already
includes both older branches. It is not a requirement that robustness-optimized
code equal the pre-optimization allocator/FTZ metrics. The previously measured
[Lethal improvements and cross-corpus tradeoffs](DXVK-CODEGEN.md) are preserved
exactly. As before, only CS2 uses the host replay layout-limit override; these
are compilation checks, not game execution results or a full CTS run.

## Hardware validation

An exclusive mini lease was acquired at 07:41 EDT on 2026-10-06, after the
main thread released its launch-loop phase. The target reports kernel
`7.1.13-m4-g16+`, Apple M4 (G16G B1), Honeykrisp Mesa 26.3.0-devel
(`git-8848a20233`). The private ARM64 library SHA-256 is
`cc80df6f90c64880d274a528511b68d8f23d97f9d0d5e726466751f1907a88de`.

| Focused hardware CTS set | Pass | Skip | Fail | Expected fail | Flake |
| --- | ---: | ---: | ---: | ---: | ---: |
| Normal allocator/compiler | 463 | 1 | 0 | 0 | 0 |
| Forced spilling | 139 | 1 | 0 | 0 | 0 |
| FP32 float controls | 3,328 | 868 | 0 | 0 | 0 |
| Robustness/descriptors | 915 | 400 | 0 | 0 | 0 |
| Compute derivative exposure (disabled) | 0 | 549 | 0 | 0 | 0 |

Every case identity and outcome matches its individual branch's recorded
hardware result. The normal/forced skip is the unsupported long-vector phi
case. Forced-spill compiler captures contain **430 SAVE and 660 FILL** operations,
with **31 passing single-case runs** containing both, establishing actual
execution with spilling. The older allocator-only run had 432/662 across 32
cases; the integrated optimizations remove two SAVE/FILL pairs from
`spirv_assembly.instruction.compute.opphi.wide`, which no longer needs spills. Outcome identity is unchanged.

`AGX_SPILL_COALESCE=1` is used in the normal and forced runs; only the forced run
sets `AGX_MESA_DEBUG=spill`. Compression remains enabled, `ASAHI_MESA_DEBUG` and
`HK_PERFTEST` are unset, and shader caches are disabled. No full CTS run, system
installation, kernel replacement or reset was needed. The separate derivative
experiment is not included in these integration results.

## Reproduction and evidence

Workspace `artifacts/compiler-integration-20261006/` holds the input refs/tree,
build/link provenance, fresh per-entry metrics, exact comparison, host test log,
and hardware case lists/scripts. Corpus archives/databases are read in place;
no new corpus copy was made. Replay uses `measure-robust.py` with the fresh ICD
and populations `lethal cs2 willems vkmark cts robust`. `comparison.json` checks
these against `artifacts/dxvk-quality-20261006/final-*.json`.
