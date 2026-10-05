# Low-bank preference near the register cap

Host-only follow-up to `7e6bc8da2be`. Keep its placement policy: the tested
near-cap guard sacrifices substantial instruction savings without removing any
spill traffic. This does not establish an occupancy or runtime result.

## Five compute outputs

Rows are zero-based in the whole-capture replay. All five have zero SAVE, FILL,
scratch bytes and swaps in both versions.

| Row | Before placement GPRs / instructions | Placement GPRs / instructions |
|---|---:|---:|
| 9207 | 93 / 3254 | 96 / 3094 |
| 9294 | 93 / 3230 | 96 / 3070 |
| 9485 | 94 / 3260 | 96 / 3239 |
| 9760 | 93 / 3230 | 96 / 3070 |
| 9986 | 93 / 3254 | 96 / 3094 |

The current Apple9 compute path does not pass `info.nr_gprs` to a register
allocation field. `hk_apple9_dispatch` uses `agx_apple9_compute_profile`, which
contains resources, geometry, scratch, preamble and publication information,
but no GPR count. `apple9_build_compute_launch` likewise has no GPR high-water
input. Thus these changes do not request a different explicit launch register
tier. The machine model labels occupancy `AGX_APPLE9_OCCUPANCY_UNMEASURED`;
actual occupancy could still depend on shader execution and cannot be inferred
from this host analysis. No hardware occupancy measurement was made.

## Guard experiment

An isolated overlay disables the immediate-bank materialization preference
when `max(aligned demand, allocated footprint) + 16 >= register bound`, all in
half-register units. It otherwise retains the existing phi, operand and
scarcity costs. The whole replay completed all 10,161 outputs with exit 0.
Relative to placement alone:

| Stage | Instructions | Ordinary copies | Swaps | GPR increases / decreases |
|---|---:|---:|---:|---:|
| Fragment | +35,169 | +34,898 | -252 | 0 / 8 |
| Vertex | +7,297 | +7,292 | +40 | 0 / 2 |
| Compute | +3,221 | +2,979 | +62 | 0 / 90 |
| Total | **+45,687** | **+45,169** | **-150** | 0 / 100 |

Every output retains its SAVE/FILL counts and scratch size. The five outputs
above return exactly to their pre-placement metrics, giving back 661 saved
instructions. Fragment/vertex populations at 96 remain unchanged; compute
returns from nine to four. This guard is not retained in production. A measured
occupancy threshold could motivate a different cost later; an arbitrary
near-cap cutoff currently loses too much static code.

Evidence: `tmp/cs2-pressure-20261005/phi-preference/build-near-cap.py`, its frozen
driver in `vertex-analysis/drivers/constant-near-cap`,
`vertex-analysis/constant-near-cap-host.jsonl`, and
`phi-preference/near-cap-vs-low.json`. These are host compilation replays with
fake DRM and submit no GPU work.
