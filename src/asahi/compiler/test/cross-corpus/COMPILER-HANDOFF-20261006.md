# Compiler handoff — 2026-10-06

Workspace `/home/nsheth/Projects/asahi` (all relative paths below start here).
Owned checkout: `mesa-isa-probe`; Main's `mesa-m1n1-shim` and temporary checkouts
are read-only. Everything in the owned checkout is committed, local, unpushed.
Full local branch inventory: `branch-tips.txt` alongside this file.

## Relevant branches and validation

| Branch (`apple9/` prefix) | Tip | State |
| --- | --- | --- |
| compute-derivative-query | See handoff-tip.txt | Handoff commit atop `156fbd0db16`; production code last changed at `b753d0c32f2`. Native derivative CTS **90 pass / 459 skip**, no failures/xfails/flakes. All **3,696 texture cases / 199,584 rows pass**, plus 459 host compiler tests. Linear derivatives advertised; quad feature false. Supplemental regression run below is **pending**, not passed. |
| integration-native-cts | `40f542ee737` | Native integration-next `a852a6c55a44`: all 8,168 statuses unchanged: **5,879 pass / 2,289 skip**, no failures/xfails/flakes. Float list alone 3,328 pass / 868 skip. 42 programs × 66 inputs = 2,772 exact-bit outputs in each default/FTZ mode, unchanged. |
| int64-atomic-assessment | `424a2b52c90` | Written assessment only; no int64 implementation or hardware validation. |
| integration-next | `a852a6c55a44` | Base for these three topics; includes consumer folding through a400. |
| ftz-codegen | `a400a7b8e3a` | General FTZ consumer folding; 454 host tests and 7,020 corpus outcomes unchanged. Now also covered by integration native validation above. User reports Lethal 20.844 GPU ms/frame. |
| compute-derivative-lod | `e1e1cd996f4` | Historical implicit-sampling stage: 86 pass / 4 fail / 459 skip. Merged into query topic; superseded by its passing results. |
| dota-fragment-hang | `628cf601fd4` | Host shader audit complete; no identified compiler defect or native reproducer. Main will capture stalled-draw shader identity. Evidence: `artifacts/dota-compiler-20261006/`. |
| lethal-regression-analysis | `b92e1e44e20` | Earlier isolated-memory analysis and focused native CTS; superseded for FTZ by the reports above. |

Reports: `mesa-isa-probe/src/asahi/compiler/test/compute-derivatives/QUERY-FOLLOWUP.md`,
`artifacts/integration-native-cts-20261006/VALIDATION.md`, and
`artifacts/int64-atomic-assessment-20261006/ASSESSMENT.md`.
Query evidence: `artifacts/compute-derivative-query-20261006/area-summary.json`
and `hardware-area/candidate/{derivatives/results.csv,textures*.json}`.
Native query kernel journal has no new entries. Intermediate failing runs in
`hardware/candidate/` are **not** the final results.

## Queued regression: take over, do not launch twice

At handoff the existing worker is waiting behind Main's mini lease. Shell PID
44560, lease-wait child 44561 (verify with `ps`); execution session 42589.
It will acquire `codex-compute-query` for 30 minutes, run, fetch results, and
release automatically. This worker is intentionally left queued for Claude.
Check `tools/lease/lease.sh status mini` and these logs before restarting:
`artifacts/compute-derivative-query-20261006/regression-lease-validation.log`
and `area-native-regressions.log` in the same directory.

Exact restart command, **only if that worker has exited**:

```sh
cd /home/nsheth/Projects/asahi
bash artifacts/compute-derivative-query-20261006/validate-regressions.sh > artifacts/compute-derivative-query-20261006/regression-lease-validation.log 2>&1
```

The script uses the already uploaded driver under
`/root/compute-derivative-query-20261006-area/candidate/` on `root@192.168.50.2`.
Its `icd.json` contains the absolute library path
`/root/compute-derivative-query-20261006-area/candidate/libvulkan_asahi.so`.
SHA-256: `53a29c8085660c6c457d75e1f71c5aa962c800384642eabab2695ec4444ee213`;
runtime identity `git-b753d0c32f`. Local pinned copy:
`artifacts/compute-derivative-query-20261006/area-driver/`.

Runner: `artifacts/compute-derivative-query-20261006/hardware-area/run-regressions.sh`.
Lists: `artifacts/integration-native-cts-20261006/hardware/cts/{normal,forced-spill,memory,robust-descriptor}.txt`,
uploaded to the remote area directory's `cts/`. Remote CTS binary:
`/root/cts-env/build-surfaceless/external/vulkancts/modules/vulkan/deqp-vk`;
runner `/root/cts-tools/bin/deqp-runner`; skip/flake lists
`/root/cs2-batch-overnight-20261005/ci/`. Two jobs, 60-second case timeout,
normal compression, cache disabled, `AGX_SPILL_COALESCE=1`; forced-spill alone
sets `AGX_MESA_DEBUG=spill`. Expected baseline: **2,551 pass / 1,421 skip**.
Compare every case against `artifacts/integration-native-cts-20261006/hardware/candidate/`,
inspect `regression-kernel-new.log`, update QUERY-FOLLOWUP.md and commit results.
No need to repeat full float-controls or run full CTS.

Driver rebuild, from `mesa-isa-probe`:

```sh
ninja -C build-host-replay -j4 src/compiler/clc/mesa_clc src/compiler/spirv/vtn_bindgen2 src/asahi/clc/asahi_clc
ninja -C build-stage3-aarch64 -j4 src/asahi/vulkan/libvulkan_asahi.so
```

Cross build already points to those matching host tools. Cross file:
`tmp/cs2-load-fold-build/aarch64-mini.ini`, sysroot `tmp/mini-sysroot`.
Texture probe sources: `mesa-isa-probe/src/asahi/compiler/test/compute-derivatives/{generate-textures.py,run-textures.py,texture-probe.c}`.
Remote/local area directory contains built `texture-probe`, `run-textures.py`,
and inputs `textures`, `textures-extended`, `textures-affine`, `textures-view-min`.
Example under a lease, from the remote area directory:
`AGX_SPILL_COALESCE=1 python3 run-textures.py textures-affine --probe ./texture-probe --icd candidate/icd.json --output candidate/textures-affine.json`.
Add `--null-image` with `textures` for null tests. Exact-bit tools/input/runner
are retained in `artifacts/integration-native-cts-20261006/hardware/` and source
`mesa-isa-probe/src/asahi/compiler/test/fp32-denorm/`.

## Host tools and reproducibility

- General corpus replay: `artifacts/lethal-pressure-20261006/measure.py ICD ARM lethal cs2 willems vkmark cts robust`, then `compare.py ARM` in that directory. Uses `mesa-isa-probe/src/asahi/compiler/test/cross-corpus/{packed.py,build-compiler.py,run.py}`, SQLite packs in `artifacts/compiler-cross-corpus-20261006/`, `/tmp/asahi-cross-corpus/compile-shader-packed`, and `/tmp/asahi-cross-corpus/lethal-tools/fossilize-replay-audit`. Compiler-only shim: `tmp/cs2-pressure-20261005/vertex-analysis/libhost-noop.so`; never submit GPU work through it. Valid final FTZ records are `ftz-consumers-*.json` (7,020 outcomes: 6,995 pass, 20 shaderless libraries, 5 existing failures).
- Lethal DXVK reconstruction: `artifacts/lethal-regression-static-20261006/cache-replay-tool/{fetch-build-inputs.py,build.py,cache-replay.cpp}`; built tool `/tmp/asahi-lethal-regression/ir-tool/cache-replay BIN LUT OUTPUT_DIR`. Matches public DXVK revision `685301564ea3486`. `remap-cache.py` restores captured binding decorations. `regeneration-proof.json` proves 46 byte-exact baseline module roundtrips; 5 builtins unchanged. `replacement-0/1/2` mean original / FTZ+FC2 / FTZ without FC2.
- Reconstructed replay: set `CORPUS_REPLAYER=/tmp/asahi-lethal-regression/replayer/fossilize-replay` and `CORPUS_SPV_REPLACEMENT_DIR=/absolute/path/to/replacement-1`, then `python3 artifacts/lethal-regression-static-20261006/replay.py ABSOLUTE_ICD NEW_ARM`. Captured FOZ: `artifacts/compiler-cross-corpus-20261006/lethal-company/lethal-capture.foz`. `analyze.py` parses retained gzip logs into program/WAIT summaries. Driver hashes and game-ready overlays: that directory's `driver-manifest.json`. Preserve original captures and use new arm names.
- FOZ summaries: `tmp/cs2-shaders-20261004/foz-summary.py`, `tmp/cs2-pressure-20261005/loop-comparison/foz-summary.py`; host stream summaries: `tmp/cs2-pressure-20261005/vertex-analysis/summarize-host.py`. Parsers needing `CORPUS_FINAL` require the instrumented compiler overlay; an empty metrics result with a normal game driver is not a compilation failure. Build overlays with `artifacts/lethal-pressure-20261006/build-overlay.py` / `link-fixed.py`; freeze common frontend and compare identical inputs/flags.

## Int64 atomics next steps and gotchas

Apple's public feature table lists full Apple9 64-bit atomics. Start with
source-authored aligned-buffer add/exchange/CAS probes that prove old-value
return and both words, then establish tuple/width encoding and completion.
Generalize NIR selection, semantic VIR width, frame return transport and RA;
validate contention, physical pointers, robustness, memory ordering and spills.
Expose buffer int64 only after validation; shared/image remain separate. No
kernel UAPI change. Estimate 2–3 engineer-weeks conditional on native protocol;
revise after first hardware witness. Two 32-bit atomics are not a 64-bit atomic.

- A bare ICD `library_path: libvulkan_asahi.so` loads the installed library, not necessarily the JSON's directory. Use absolute paths; verify hash **and** runtime device/driver identity.
- Regenerate portable NIR helpers with same-source `mesa_clc`, `vtn_bindgen2`, `asahi_clc` before cross builds. Stale Oct-4 shared host tools caused 49 fill-buffer userspace crashes; matching tools fixed them without source changes. First two native preflights were discarded for loader/helper mistakes.
- Use `sed -n 's/^-- cursor: //p'` for journal cursors; `journalctl -n 0` also emits a no-entries line. Native gdb currently trips over SVE/SSVE GETREGSET; a diagnostic preload is retained under `artifacts/integration-native-cts-20261006/crash-backtrace.*`.
- Capability changes must pass G16's `hk_apple9_restrict_caps` filter. Generic-table changes alone did not expose compute derivatives. Cube reference comparisons allow one Q6 step for FP32 gradient rounding; this is documented, not hidden as a flake.
- The user reports model-service content filtering interrupting hardware-debugging turns. Describe real outcomes in neutral compiler terms (for example, an invalid-access error), without sensational wording. Preserve accurate technical evidence and the clean-room boundary; do not inspect proprietary Apple binaries.
- Never reset or run GPU tests while Main owns the lease. Keep source changes in this checkout and push only on explicit request. Dota needs stalled-shader identity from Main before further compiler conclusions.
