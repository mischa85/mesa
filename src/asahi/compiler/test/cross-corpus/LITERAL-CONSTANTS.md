# Literal-preserving constant promotion

2026-10-06, branch `apple9/literal-constants` on integration-next `27aa3f4105a`.
Code tip `2c7da70695d`; aarch64 driver SHA-256 `e8d62524…`.

Promoted preamble constants keep their literal values through VIR folding and
modifier selection; only remaining register operands are then traded for the
promoted uniform words.

- `5e94464f931`, `1d44b504e19`: the original (previously parked) promotion
  change, rebased.
- `c3689bfd20c`: the second operand-selection pass skipped any instruction whose
  first pass had already moved some operands, so promoted literals were
  materialized in GPRs (CS2 fragments +14 GPRs). It now fills only the remaining
  register slots.
- `2c7da70695d`: on the second pass `fold_integer` treated an operand already
  in the uniform file as zero (`iadd(ui_two, -1)` → `-1`), failing
  `dEQP-VK.glsl.switch.switch_in_switch_uniform_*` natively. The parked commits
  had this defect; it changed 9 Lethal, 54 CS2, 44 CTS and 864 robust programs.
  Unit test `RepeatedOperandSelectionKeepsUniformAddends`.

## Static (host, same fixed frontend, vs integration-next)

| Corpus | Main instructions | GPR sum | SAVE+FILL |
|---|---|---|---|
| lethal | 25,584 → 24,852 (−2.9%) | 1,256 → 1,231 | 127 → 127 |
| cs2 | 107,238 → 103,829 (−3.2%) | 5,694 → 5,599 | 496 → 483 |
| willems | 39,929 → 39,062 (−2.2%) | 4,443 → 4,365 | 0 → 0 |
| vkmark | 1,665 → 1,642 (−1.4%) | 265 → 261 | 0 → 0 |
| cts | 318,286 → 307,293 (−3.5%) | 7,828 → 7,748 | 0 → 0 |
| robust | 4,805,759 → 4,648,778 (−3.3%) | 139,698 → 135,567 | 0 → 0 |

Preambles are unchanged and there are no outcome changes. Apple9 occupancy is
unmeasured; with Apple8's halfreg granules as a proxy, no program in any corpus
loses a tier. Comparison data: `artifacts/lethal-pressure-20261006/claude-lit3-comparison.json`.
Static counts are not GPU time.

## Native (T8132, focused lists)

Case for case equal to integration-next's native baseline: float-controls
3,328/868, normal 463/1, forced-spill 139/1, memory 1,034/1,019,
robust-descriptor 915/400 (pass/skip), no failures, expected failures or
flakes. Exact-bit probes: 42 programs × 66 inputs, all 2,772 words identical in
default and FTZ modes. No kernel faults. Evidence:
`artifacts/literal-constants-20261006/` (`compare.json`, `hw-results/`).
