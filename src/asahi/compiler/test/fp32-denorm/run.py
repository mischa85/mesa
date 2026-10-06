#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run exact-bit probes on the leased M4, retaining outputs and controls."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("shaders", type=Path)
parser.add_argument("--probe", type=Path, required=True)
parser.add_argument("--icd", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--ftz", action="store_true")
parser.add_argument("--native", action="store_true")
args = parser.parse_args()
cases = json.loads((args.shaders / "cases.json").read_text())
shader_dir = args.shaders / "ftz" if args.ftz else args.shaders
library = Path(json.loads(args.icd.read_text())["ICD"]["library_path"])
if not library.is_absolute():
    library = args.icd.parent / library
summary = {
    "mode": "ftz32_signed_zero_inf_nan" if args.ftz else "default",
    "library": str(library.resolve()),
    "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
    "cases": cases,
    "records": {},
}
env = dict(os.environ)
env.pop("ASAHI_MESA_DEBUG", None)
env.update(
    VK_DRIVER_FILES=str(args.icd.resolve()),
    HK_EXPERIMENTAL_APPLE9="1",
    MESA_SHADER_CACHE_DISABLE="true",
)
if args.native:
    env.update(AGX_APPLE9_ASM="1", AGX_APPLE9_DUMP_BINARY="1")
    names = json.loads((args.shaders / "opcodes.json").read_text())
# These exact normal-value checks establish that each arithmetic path ran.
# Exceptional inputs are observations, not assumptions about the hardware.
controls = {
    "negate": ("normal_control", 0xBFC00000),
    "abs": ("negative_control", 0x3FC00000),
    "add": ("normal_control", 0x40800000),
    "add_abs": ("negative_control", 0x40800000),
    "multiply": ("normal_control", 0x40700000),
    "multiply_abs": ("negative_control", 0x40700000),
    "fma": ("normal_control", 0x40880000),
    "fma_abs": ("negative_control", 0x40880000),
    "multiply_one": ("normal_control", 0x3FC00000),
    "double_negate": ("normal_control", 0x3FC00000),
    "multiply_two": ("normal_control", 0x40400000),
    "add_half": ("normal_control", 0x40000000),
    "min": ("normal_control", 0x3FC00000),
    "max": ("normal_control", 0x40200000),
    "less": ("normal_control", 1),
    "equal": ("normal_control", 0),
    "not_equal": ("normal_control", 1),
    "sign": ("normal_control", 0x3F800000),
    "floor": ("normal_control", 0x3F800000),
    "ceil": ("normal_control", 0x40000000),
    "trunc": ("normal_control", 0x3F800000),
    "round_even": ("normal_control", 0x40000000),
    "fract": ("normal_control", 0x3F000000),
    "exp2": ("one", 0x40000000),
    "log2": ("one", 0),
    "sqrt": ("one", 0x3F800000),
    "inverse_sqrt": ("one", 0x3F800000),
    "reciprocal": ("one", 0x3F800000),
    "sin": ("pzero", 0),
    "cos": ("pzero", 0x3F800000),
    "f32_to_half": ("half_min_subnormal_output", 1),
    "half_to_f32": ("half_min_subnormal_input", 0x33800000),
    "f32_to_i32": ("normal_control", 1),
    "f32_to_u32": ("normal_control", 1),
    "i32_to_f32": ("pminsub", 0x3F800000),
    "u32_to_f32": ("pminsub", 0x3F800000),
    "atomic_add": ("normal_control", 0x40800000),
    "atomic_add_return": ("normal_control", 0x3FC00000),
    "subgroup_min_cluster1": ("normal_control", 0x3FC00000),
    "subgroup_max_cluster1": ("normal_control", 0x3FC00000),
}
non_float_result = {
    "identity",
    "select_passthrough",
    "less",
    "equal",
    "not_equal",
    "f32_to_half",
    "f32_to_i32",
    "f32_to_u32",
}
for shader in sorted(shader_dir.glob("*.spv")):
    start = time.monotonic()
    run = subprocess.run(
        [
            str(args.probe.resolve()),
            str(shader.resolve()),
            str((args.shaders / "inputs.bin").resolve()),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    row = {
        "exit": run.returncode,
        "wall_s": time.monotonic() - start,
        "device": [
            line
            for line in run.stderr.splitlines()
            if line.startswith(("DEVICE ", "FP32_CONTROLS ", "TRANSPORT "))
        ],
        "outputs": {},
        "failures": [],
    }
    if args.native:
        row["float_instructions"] = []
        row["programs"] = []
        for line in run.stderr.splitlines():
            if line.startswith("APPLE9_ASM "):
                name = names[int(re.search(r" op=(\d+)", line)[1])]
                name = name.removeprefix("AGX_APPLE9_VIR_")
                if name.startswith("F") or name in (
                    "U2F32",
                    "I2F32",
                    "UNPACK_HALF",
                    "PACK_HALF_2X16",
                    "SELECT",
                    "DEVICE_ATOMIC",
                    "DEVICE_ATOMIC_RESULT",
                ):
                    row["float_instructions"].append({"op": name, "encoding": line})
            elif line.startswith("APPLE9_BINARY stage="):
                code = bytes.fromhex(line.split()[-1])
                row["programs"].append(
                    {
                        "bytes": len(code),
                        "sha256": hashlib.sha256(code).hexdigest(),
                    }
                )
    for line in run.stdout.splitlines():
        parts = line.split()
        if len(parts) != 5 or not parts[0].isdigit():
            continue
        index = int(parts[0])
        assert index < len(cases)
        values = [int(x, 16) for x in parts[1:]]
        case = cases[index]
        assert values[:2] == case["words"][:2]
        assert values[3] == case["words"][3] ^ 0x6D2B79F5
        row["outputs"][case["name"]] = f"{values[2]:08x}"
    if run.returncode or len(row["outputs"]) != len(cases):
        row["failures"].append("execution_or_transport")
        row["diagnostics"] = run.stderr[-4000:]
    else:
        if shader.stem in controls:
            name, expected = controls[shader.stem]
            if int(row["outputs"][name], 16) != expected:
                row["failures"].append(f"control {name}: expected {expected:08x}")
        for case in cases:
            value = int(row["outputs"][case["name"]], 16)
            if shader.stem == "identity" and value != case["words"][0]:
                row["failures"].append("identity " + case["name"])
            if shader.stem == "select_passthrough":
                expected = case["words"][0] if case["words"][1] else case["words"][1]
                if value != expected:
                    row["failures"].append("select " + case["name"])
            if (
                args.ftz
                and shader.stem not in non_float_result
                and 0 < (value & 0x7FFFFFFF) < 0x00800000
            ):
                row["failures"].append("denormal result " + case["name"])
    summary["records"][shader.stem] = row
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        shader.stem,
        "controls=" + ("FAIL" if row["failures"] else "PASS"),
        row["failures"],
        flush=True,
    )
    if run.returncode:
        raise SystemExit(run.returncode)
raise SystemExit(any(row["failures"] for row in summary["records"].values()))
