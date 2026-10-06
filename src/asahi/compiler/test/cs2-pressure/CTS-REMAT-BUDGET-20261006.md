# Rematerialization instruction-headroom validation

Candidate: stable compiler `1f4c8abe909` plus only `agx_spill.c` from
`738eeb21697`. Native GCC 16.2.1, ordinary game build flags; driver SHA-256
`ce35ba07a05510e8dde2f198b0fe2a04142056e7aede59a68abcc496c8c645cf`.
The candidate excludes the subsequent LICM/reload-reuse experiments and select
peephole. The native source manifest and build commands are retained.

| Set | Pass | Skip | Fail/crash | Observed flakes |
|---|---:|---:|---:|---:|
| Normal | 463 | 1 | 0 | 0 |
| Forced spill, fresh rerun | 139 | 1 | 0 | 0 |
| Assertion-enabled focused value tests | 8 | 0 | 0 | 0 |

There are no expected-failure classifications in these sets. The skip is
`opphi.vartype_longvec`. All six previously crashing highp/mediump integer
vertex cases for for/while/do-while uniform loops pass. The forced run's own
retained compiler output contains 422 SAVE and 650 FILL instructions, with both
operations in 32 individually identified passing cases. Normal output has no
spills, as expected; it is not forced-spill coverage.

The first forced attempt is invalid as complete validation: 70 Pass, 69 Missing,
1 Skip. Its missing results report shader-ring initialization failing with
ENOSPC in `/dev/shm`, before device creation. Only that run's completed-process
ring files were removed. The rerun wrapper removes each process's ring after
it exits, preserving its compiler log. No test remained running at release;
input forwarding and `g16-steam` remained active, with no new GPU fault reported.

Evidence is in workspace `artifacts/mesa-spill-budget-738eeb21697/validation/`:
compressed original CTS outputs, per-case results, native provenance, corrected
runner, normal/forced summaries and the focused test log. Full remote evidence
remains in `/root/cs2-compiler-abab-20261005/` under `validation-T-20261006`
and `validation-T-forced-rerun-20261006`. This validates the budget fix, not
cross-corpus performance or the parked LICM experiment.
