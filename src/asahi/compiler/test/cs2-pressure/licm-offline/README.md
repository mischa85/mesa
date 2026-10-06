# Offline LICM measurements

These overlays measure the local experimental compiler at `127976460da` against
`1f4c8abe909`. They are not a shipping LICM policy. No GPU submission is involved.
Use a checkout and a complete host compiler build at that exact prototype
commit: the pressure fields change compiler-private structures, so combining
old and new objects is invalid. The builders enforce that source identity.

`MESA_SOURCE` selects that checkout, `MESA_BUILD` its complete host replay build,
and `CENSUS_OUTPUT` a fresh output directory. The existing host Fossilize replay
adapter, capture, and CPU-only interception library are workspace inputs.

- `build-loop.py NAME off|on|restricted|tryboth` builds the diagnostic overlay.
  The `restricted` filter admits transcendentals/products and their vector or
  immutable preamble inputs. `--timing` replaces census output with backend
  thread-CPU and monotonic-wall clocks.
- `build-exact-time.py NAME off --timing` restores the four relevant compiler
  sources from `1f4c8abe909` while retaining the compatible prototype headers.
  This measures the exact stable algorithms, including their existing sample
  hoisting alternatives. There is no LICM or reload-reuse trial in this arm.
- `parse-loop.py NAME` reads the existing assembly/stats replay stream. Set
  `CENSUS_PARSER_LIBRARY` to the workspace directory containing
  `stream_compare_lib.py`. This output is for counting, not timing.
- `time-command.py OUTPUT COMMAND...` measures an uninstrumented replay's whole
  wall/user/system time. Backend timing has no assembly or per-loop census.
- `summarize-loops.py`, `budget-sweep.py`, and `benefit-sweep.py` operate on the
  diagnostic JSONL results named `loop-off`, `loop-on`, and `loop-restricted`.

Each CSV contains all 6,542 loops, identified by main-program ordinal, shader
stage, pipeline index/hash, and NIR header index. Loops include their nested
children. Do not sum inclusive loop totals to obtain whole-shader totals.
Register pressure is the first pre-spill rolling demand calculation, including
reserved registers and physical operand floors. Half-register and rounded-up
32-bit GPR columns are both supplied. Allocated GPR columns are the enclosing
shader's physical extent, repeated per loop; allocation is not separate for
each loop. Spill traffic counts SAVE/FILL instructions, not bytes.

The hoist census follows actual ALU instruction movement across each loop
boundary; moving across two loops appears once in each loop. It records full
opcode counts and grouped transcendental, fmul/fadd, iadd, and fneg counts.
`hoisted_alu_words` counts their result sizes. Uniform-import and literal
movement is not included in that size column. Loop pressure and final code
metrics do include their effects.

The budget sweeps are retrospective proxies using measured pre-spill demand
and those moved ALU result sizes. The selected allocator candidate's pressure
is available in this experiment, but is not yet an implemented early pressure
estimator. Imports, literals, and lifetimes outside loops must also be modeled
before treating a future rule as a pressure guarantee. These results do not
establish a shipping rule or actual GPU-time gains.

All weighted counts use `8 ** min(loop_depth, 6)`. This is the existing comparison
model, not a measurement of runtime trip counts or draw frequency. The stable
and diagnostic-off outputs match exactly for all 10,161 main programs, including
instructions, GPRs, scratch, SAVE/FILL, copies, swaps, and weighted counts.

## Parked result

Unrestricted LICM reduces the CS2 weighted instruction estimate 1.057%, but
increases weighted SAVE/FILL traffic 39.06%. The transcendental/product filter
still increases traffic 22.13%. The offline 88-GPR proxy avoids new 96-GPR
allocations, but has not been implemented or independently validated. LICM is
parked: no shipping policy follows from these results. Local reload reuse
produced no changes across 10,161 main programs and is also removed.

Only timing A1/B1 completed before the host crash: whole CPU user times
298.698 s versus 423.946 s, wall 300.897 s versus 426.397 s. This is a single
completed pair, not the intended ABBA experiment; incomplete B2/A2 are excluded.
No further CS2-only optimization is planned. Cross-corpus measurement supersedes
this experiment.
