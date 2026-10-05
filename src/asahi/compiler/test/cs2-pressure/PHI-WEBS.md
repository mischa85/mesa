# Why the remaining repro phi webs split

This analysis uses loop handling, coalescing unset, graphics pipeline 105, selected
allocation 10: 6,271 instructions, 441 true swaps, 387 SAVE, 354 FILL, 272 B scratch.
The diagnostic build reproduces those codegen counts. No allocator placement
change is implemented here.

## The 294 mixed-cycle swaps

There are 30 mixed cycles, containing 324 copy operands (a cycle of length L
requires L−1 swaps). Operand counts must not be mistaken for swap counts.

| Join kind | Cycles | Swaps | Original phi operands | Spill-repair operands | Later RA reconciliation |
|---|---:|---:|---:|---:|---:|
| Loop header | 5 | 54 | 11 | 48 | 0 |
| Non-header join, including exits | 25 | 240 | 120 | 144 | 1 |

The header copies are 20 swaps on entry edge 37→38, 9 on entry edge 41→42,
and 25 on backedge 103→38. Other edges:

| Edge | Mixed swaps |
|---|---:|
| 30→32 | 49 |
| 91→93 | 42 |
| 92→93 | 26 |
| 154→156 | 26 |
| 87→89 | 24 |
| 98→104 | 22 |
| 152→154 | 22 |
| 53→55 | 7 |
| 63→65 | 7 |
| 128→130 | 7 |
| 118→120 | 6 |
| 58→59 | 1 |
| 123→124 | 1 |

The full cycle membership, original/repair tags, SSA definitions and web IDs
are retained in `loop-comparison/webs-model/webs.json`.

## One web incorrectly serves as one affinity

`agx_ra` builds phi webs by unconditionally unioning each phi destination with
all SSA sources. This is connectivity, not interference-aware coalescing. A
shared initializer therefore joins logically different loop-carried variables.

In the repro, SSA 19 (`mov_imm 0`) joins a **1,021-member web, root 486**.
Its members have 43,126 interfering pairs; up to 74 members are live together.
They cannot occupy one register. This web supplies 255 of the 324 mixed-cycle
copy operands. The other participating webs are mostly small and noninterfering;
only two additional webs (roots 1610 and 3270, five members each) have internal
interference, with two pairs apiece.

Mixed-cycle operand membership by web family (these are operands, not swaps):

| Web roots | Header original | Header repair | Other join original | Other join repair | Late reconciliation |
|---|---:|---:|---:|---:|---:|
| 486 | 5 | 35 | 115 | 100 | 0 |
| 2586–2591 | 6 | 5 | 0 | 18 | 0 |
| 1082–1084 | 0 | 7 | 0 | 4 | 0 |
| Remaining roots | 0 | 1 | 5 | 22 | 1 |

Each remaining root contributes one operand. The original-phi roots are 1610,
2594, 2852, 3270 and 4134; the header repair root is 1053. The other repair
roots are 251, 1054, 1337, 1603, 1769–1771, 2465, 2847–2848, 3014, 3266,
3421–3423, 4059–4061, 4122–4125. The late reconciliation is SSA 1216.

Concrete assignment trace:

- SSA 19 gets half-register h140 (r70). `assign_regs` saves that as the web's
  sole hint and never replaces it.
- At loop header 17, phi SSA 252 gets h140.
- The next phi, SSA 254, also wants h140, but SSA 252 is live there. It falls
  back to h134. SSA 255 similarly falls back to h136.
- Hundreds of later members keep asking for the same h140, even though their
  meaningful coalescing opportunities concern other members and other registers.

Among the 324 mixed-cycle operands, the original assignment trace gives:

| Situation when the phi destination was assigned | Operands |
|---|---:|
| Hint occupied by another member of the same web | 243 |
| Hint occupied by another web | 46 |
| Hint used, but an incoming edge still differs | 34 |
| Later RA reconciliation phi | 1 |

All 243 same-web blockers are confirmed by the independent SSA interference
graph. Across all 1,021 giant-web definitions, the hint is used only 23 times;
724 lose it to a same-web occupant, 273 to another web, and one seeds the hint.

## Where affinity gives up

The key sites in `agx_register_allocate.c` are:

- Web construction after `agx_spill`: unconditional `phi_web_union`.
- `assign_regs`: the first assigned member sets `web->reg` permanently.
- `pick_regs`: tries that single hint only if free, aligned and in bounds,
  then tries individual phi sources in source order, then ordinary placement.
- `constrained_affinity`: likewise supplies only one web register to placement
  costs. The cost order prefers avoiding immediate moves before affinity.
- `src_to_collect_phi`: stores only one consuming collect/phi per source;
  later uses overwrite earlier ones. It is not a weighted list of phi edges.
- Block allocation is dominance order, with phi destinations assigned one at
  a time. Local fallbacks do not optimize the entire parallel-copy bundle.

Interference inside the giant web is the primary observed failure; assignment
order and single-hint fallback determine the resulting permutations. Simply
changing which member assigns the hint first cannot put 74 simultaneous values
in one register. There is also a strict `< bound` check in the first web-hint
path, but it does not explain this h140-centered result.

Spill-repair phis are **not too late**: `agx_spill` repairs SSA before the union
pass. They all participate in web construction. `reserve_live_in` does create
physical reconciliation phis after allocation begins; one participates in a
16-swap mixed cycle here. That does not mean all 16 swaps were caused by it.

## Proposed change, before implementation

First replace the connectivity-only hints with **interference-aware affinity
classes**, without forcing SSA members to one physical register:

1. Collect weighted phi source/destination preferences after spilling and SSA
   repair. Prefer recurrent loop edges and frequently used join relationships.
2. Avoid merging unrelated webs through rematerializable constants. Merge other
   classes only if their members do not interfere and their widths/windows
   remain compatible.
3. Give each resulting class its own hint; retain multiple useful neighboring
   phi preferences rather than only the last `src_to_collect_phi` use. Keep
   normal allocation and its current spill/register bounds as the fallback.

Measure that bounded hint change before considering simultaneous assignment of
whole phi bundles. A global hard coalescing/coloring rewrite is not proposed as
the first implementation.

An offline greedy affinity model forms 162 nontrivial classes (largest 25
members), accepts 1,132 merges, rejects 106 interfering merges, and skips 134
constant-source edges. It places 301 of the 323 pre-RA mixed-cycle copy relations
inside compatible classes. Seventeen complete mixed cycles, currently costing
**156 swaps / 468 XOR instructions**, have every relation represented. That is
an opportunity estimate, not a compiled gain: achieving all of it would remove
about 7.5% of the repro's instructions before accounting for new moves elsewhere.
The 30→32 cycle alone is a useful first target: 49 swaps, with 48/50 relations
represented by safe classes.

No reliable final swap forecast is claimed. A separate simplistic global graph
coloring attempt failed to fit both the contracted graph and the uncontracted
baseline into the modeled windows; it omits the real allocator's local splitting
and tuple behavior. It therefore cannot validate a register-count or performance
prediction. The first real experiment must retain 96 GPRs / 272 B scratch, count
moves and transfers as well as swaps, and compare all allocation candidates.

## Evidence and reproducibility

`analyze-phi-webs.py` reconstructs SSA edge liveness and exact union-find roots
from the retained postspill IR. `model-phi-coalesce.py` computes the hypothetical
safe classes and explicitly reports the coloring limitation. Opt-in
`AGX_APPLE9_RA_WEBS=1` logs wanted/chosen registers and blocking owners alongside
the existing audit; it does not change placement.

Artifacts under `tmp/cs2-pressure-20261005/loop-comparison/`:
`loops-105-webs.log`, `webs-model/{webs,model,assignment-causes,mixed-opportunity,
color-estimate,color-baseline}.json`, and the prior `loops-audit/`.
