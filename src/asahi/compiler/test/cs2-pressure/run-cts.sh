#!/bin/bash
# SPDX-License-Identifier: MIT
# GPU execution: invoke only during the explicitly released coordinator slot.
set -euo pipefail
if [[ ${1:-} != --execute || $# != 5 ]]; then
  echo "usage: $0 --execute ICD_JSON normal|forced-spill OUTPUT_DIR JOBS" >&2
  exit 2
fi
icd=$(realpath "$2")
mode=$3
out=$4
jobs=$5
here=$(cd -- "$(dirname -- "$0")" && pwd)
case "$mode" in normal|forced-spill) ;; *) exit 2 ;; esac
[[ ! -e "$out" ]] || { echo 'Use a fresh output directory' >&2; exit 2; }
mkdir -p "$out"
out=$(realpath "$out")
cts=/root/cts-env/build-surfaceless/external/vulkancts/modules/vulkan/deqp-vk
ci=/root/cs2-batch-overnight-20261005/ci
cat > "$out/suite.toml" <<EOF
[[deqp]]
deqp = "$cts"
caselists = ["$here/cts/$mode.txt"]
tests_per_group = 50
EOF
unset ASAHI_MESA_DEBUG AGX_MESA_DEBUG NIR_DEBUG AGX_APPLE9_RA_AUDIT AGX_APPLE9_TRACE AGX_APPLE9_ASM AGX_APPLE9_TRACE_SHARED_RA
export HK_EXPERIMENTAL_APPLE9=1 MESA_SHADER_CACHE_DISABLE=true AGX_APPLE9_STATS=1 VK_DRIVER_FILES="$icd"
if [[ $mode == forced-spill ]]; then export AGX_MESA_DEBUG=spill; fi
printf 'icd=%s\nmode=%s\njobs=%s\n' "$icd" "$mode" "$jobs" > "$out/provenance.txt"
sha256sum "$icd" "$here/cts/$mode.txt" >> "$out/provenance.txt"
exec taskset -c 1-6 nice -n 5 /root/cts-tools/bin/deqp-runner suite \
 --suite "$out/suite.toml" --output "$out/results" --jobs "$jobs" \
 --timeout 60 --max-fails 20 \
 --skips "$ci/all-skips.txt" --skips "$ci/asahi-skips.txt" --skips "$ci/asahi-agx2-skips.txt" \
 --flakes "$ci/all-flakes.txt" --flakes "$ci/asahi-agx2-flakes.txt" > "$out/runner.log" 2>&1
