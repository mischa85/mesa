#!/bin/bash
# SPDX-License-Identifier: MIT
# deqp-runner removes passing logs; retain compiler evidence for every process.
set -euo pipefail
capture="$CTS_CAPTURE_DIR/compiler-$$"
for arg in "$@"; do
  case "$arg" in
    --deqp-caselist-file=*) cp -- "${arg#*=}" "$capture.cases" ;;
  esac
done
cd -- "$(dirname -- "$CTS_EXECUTABLE")"
exec "$CTS_EXECUTABLE" "$@" 2> >(tee "$capture.log" >&2)
