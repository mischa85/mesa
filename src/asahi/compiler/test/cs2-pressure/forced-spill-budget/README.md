# Rematerialization must leave room for one instruction

The native frozen `1f4c8abe909` build passed the 464-case normal CTS selection
(463 pass, one skip), but its forced-spill selection had six crashes (133 pass,
one skip). They were the highp/mediump float fragment cases for for, while, and
do-while uniform-iteration loops. This was a compiler regression: a direct
repeat failed in register allocation, while native `c62490d01c2` passed the same
case. The release compiler segfaulted in `assign_regs_by_copying`; an assertion
build stopped at the spiller post-condition. No GPU hang or reset occurred.

This small authored GLSL/Vulkan compilation reproducer exercises the relevant
uniform descriptor loads and loop-carried values on the host. It creates a
pipeline; it does not submit GPU work. The host interception library is an
explicit required argument, and the runner refuses non-x86 hosts.

```sh
python3 run.py --icd /absolute/path/to/icd.json \
  --host-intercept /absolute/path/to/libhost-noop.so \
  --output /absolute/path/to/fresh-results
```

The default `1f4c8abe909` policy reserved two extra half-registers for rebuilding
uniform expressions. The forced budget was 24 half-registers, including ten
reserved for spill operations. A four-word load needed 14 half-registers for its
sources and destination. Reducing its usable budget from 14 to 12 allowed the
spiller to evict a source which the load still needed; the measured post-spill
peak was 26 instead of 24. Merely storing that source does not free its register
before its last use.

The fix bounds rematerialization trees by the room remaining after the largest
single instruction's simultaneous operands. It preserves the largest
instruction's budget and does not reserve unusable temporary space. Phi inputs
are edge uses and are excluded from this single-instruction bound; repeated
sources are counted once, matching the allocator's late-kill accounting.

Host validation:

- The original highp for-loop reproducer aborts at demand 26 > budget 24.
- All six generated loop/precision variants compile after the fix, with an
  explicit release-build post-spill bound check enabled.
- All eight selected assertion-enabled value/pressure tests pass normally.
- An additional global `AGX_MESA_DEBUG=spill` run passes six of those eight
  tests. The other two test normal allocation layouts (a no-scratch baseline
  and high-bank source placement), and their layout expectations fail under
  that global override. These are recorded separately from the six compilation
  regression checks; they are not claimed as forced-mode passes.

GPU validation of this fix is still pending another mini slot. The already
built native `1f4c8abe909` artifact is frozen and still contains the defect.
Its driver, exact source/build provenance, initial CTS outputs, assertion log,
and passing native eight-test log are in
`artifacts/mesa-spill-1f4c8abe909/` at the workspace root. The main thread owns the
mini again; none of this host follow-up uses it.
