#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile authored probes on the host and retain a small native-op summary."""

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("shaders", type=Path)
parser.add_argument("--icd", type=Path, required=True)
parser.add_argument("--runner", type=Path, required=True)
parser.add_argument("--host-shim", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent / "cross-corpus"))
from prepare import reflect

header = (here.parents[1] / "agx_apple9_ir.h").read_text()
enum = header.split("enum agx_apple9_vir_opcode {")[1].split("};")[0]
names = re.findall(r"AGX_APPLE9_VIR_\w+", enum)
frames = []
records = {}
for path in sorted(args.shaders.glob("*.spv")):
    code = path.read_bytes()
    info = reflect(code)
    bindings = info["bindings"]
    frames.append(
        f"{path.stem} 32 main {info['push']} {len(bindings)} {len(code)}\n".encode()
        + "".join("%d %d %d %d\n" % tuple(b) for b in bindings).encode()
        + code
    )
    records[path.stem] = {
        "spirv_sha256": hashlib.sha256(code).hexdigest(),
        "float_instructions": [],
        "opcodes": collections.Counter(),
        "programs": [],
    }
env = dict(os.environ)
env.update(
    LD_PRELOAD=str(args.host_shim.resolve()),
    VK_DRIVER_FILES=str(args.icd.resolve()),
    HK_EXPERIMENTAL_APPLE9="1",
    HK_APPLE9_EAGER_VARIANTS="1",
    MESA_SHADER_CACHE_DISABLE="true",
    AGX_APPLE9_ASM="1",
    AGX_APPLE9_DUMP_BINARY="1",
)
run = subprocess.run(
    [str(args.runner.resolve())],
    input=b"".join(frames),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    timeout=120,
    check=True,
)
key = None
for line in run.stderr.decode(errors="replace").splitlines():
    if line.startswith("CORPUS_BEGIN "):
        key = line.split()[1]
    elif key and line.startswith("APPLE9_ASM "):
        name = names[int(re.search(r" op=(\d+)", line)[1])]
        name = name.removeprefix("AGX_APPLE9_VIR_")
        records[key]["opcodes"][name] += 1
        if name.startswith("F") or name in (
            "U2F32",
            "I2F32",
            "UNPACK_HALF",
            "PACK_HALF_2X16",
            "SELECT",
            "DEVICE_ATOMIC",
            "DEVICE_ATOMIC_RESULT",
        ):
            records[key]["float_instructions"].append({"op": name, "encoding": line})
    elif key and line.startswith("APPLE9_BINARY stage="):
        code = bytes.fromhex(line.split()[-1])
        records[key]["programs"].append(
            {
                "bytes": len(code),
                "sha256": hashlib.sha256(code).hexdigest(),
            }
        )
    elif key and line.startswith("CORPUS_END "):
        records[key]["exit"] = int(line.split()[1])
        key = None
    elif key and ("failed" in line or "unsupported" in line):
        records[key].setdefault("diagnostics", []).append(line)
library = Path(json.loads(args.icd.read_text())["ICD"]["library_path"])
if not library.is_absolute():
    library = args.icd.parent / library
summary = {
    "library": str(library),
    "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
    "records": records,
}
args.output.write_text(json.dumps(summary, indent=2) + "\n")
failed = [
    key
    for key, row in records.items()
    if row.get("exit") != 0 or not row["programs"] or row.get("diagnostics")
]
print(f"compiled={len(records)} failed={failed}")
sys.exit(bool(failed))
