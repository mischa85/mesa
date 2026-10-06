#!/bin/bash
# Compile our shaders in a scheduled macOS/HV session. No queue or dispatch.
set -euo pipefail
cd -- "$(dirname -- "$0")"
clang -fobjc-arc -framework Metal -framework Foundation -o shdump shdump.m
clang -fobjc-arc -framework Metal -framework Foundation -o renderdump renderdump.m
failed=0
while read -r stage source name limit; do
    if [[ "$stage" == compute ]]; then
        command=(./shdump "$source" "$name.bin" "$limit")
    else
        command=(./renderdump "$source" "$name.bin")
    fi
    if "${command[@]}" >"$name.log" 2>&1; then
        echo "ok $name"
    else
        echo "FAIL $name (see $name.log)"
        failed=1
    fi
done < manifest.txt
exit "$failed"
