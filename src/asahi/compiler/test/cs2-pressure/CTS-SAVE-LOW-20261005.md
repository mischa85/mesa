# Combined SAVE placement and constant placement validation

The isolated assertion-enabled native driver overlays the compiler changes at
`7e6bc8da2be` (CAF/SAVE placement plus low constant placement) on the previously
validated stage-four native base. This is **not** a full native build of all
later uniform-source commits. Library SHA256:
`1a22e467b7a0f682b608a45ea71185c236d800f3d35253cf069eb8a0bc2b26b6`.

| Focused CTS set | Pass | Fail | Crash/timeout | Skip | Flake |
|---|---:|---:|---:|---:|---:|
| Normal | 463 | 0 | 0 | 1 | 0 |
| Forced spilling | 139 | 0 | 0 | 1 | 0 |

Both commands exited zero. Every per-case outcome agrees with the stage-four
baseline. Both skip only
`dEQP-VK.spirv_assembly.instruction.compute.opphi.vartype_longvec`.
There is no configured expected-failure category. The forced compiler logs
contain 541 SAVE and 821 FILL instructions across 50 passing cases with both
operations. The other forced-mode passes are not counted as spill coverage.
Normal compilation emits neither operation. These are static generated counts.

Local evidence, full compiler logs, per-case QPA outputs, runner and source
manifest are under `tmp/combined-save-low-validation/`. No production Mesa
library was replaced. The mini was released after this focused validation and
the separate publication/uniform probes; no full CTS run was requested or run.
