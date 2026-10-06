#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Nonlinear lane-value probes across multi-dimensional linear workgroups."""
import argparse, json, struct, subprocess
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("output", type=Path)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
shapes = [(1,1,4), (2,2,1), (2,6,1), (3,4,1), (20,1,1),
          (4,4,4), (8,8,1), (1,1,64), (32,32,1)]
ops = ["dFdx", "dFdy", "dFdxFine", "dFdyFine", "dFdxCoarse", "dFdyCoarse", "lane"]
cases = []
for shape in shapes:
    threads = shape[0] * shape[1] * shape[2]
    inputs = []
    for group in range(3):
        for lane in range(threads):
            bits = struct.unpack("<I", struct.pack("<f", float(lane*lane + 100*group)))[0]
            inputs += [bits, lane, 0, 0xa5120000 + len(inputs)//4]
    shape_name = "_".join(map(str, shape))
    (a.output / (shape_name + ".bin")).write_bytes(struct.pack("<%dI" % len(inputs), *inputs))
    for op in ops:
        name = op + "_" + shape_name
        expr = "float(gl_SubgroupInvocationID)" if op == "lane" else op + "(uintBitsToFloat(v.x))"
        source = f"""#version 450
#extension GL_NV_compute_shader_derivatives : require
#extension GL_KHR_shader_subgroup_basic : require
layout(local_size_x={shape[0]},local_size_y={shape[1]},local_size_z={shape[2]}) in;
layout(derivative_group_linearNV) in;
layout(set=0,binding=0,std430) readonly buffer In {{ uvec4 input_data[]; }};
layout(set=0,binding=1,std430) writeonly buffer Out {{ uvec4 output_data[]; }};
void main() {{
  uint i=gl_WorkGroupID.x*{threads}u+gl_LocalInvocationIndex;
  uvec4 v=input_data[i];
  output_data[i]=uvec4(v.xy,floatBitsToUint({expr}),v.w^0x6d2b79f5u);
}}
"""
        glsl = a.output / (name + ".comp")
        spv = a.output / (name + ".spv")
        glsl.write_text(source)
        subprocess.run(["glslangValidator", "-V", "--target-env", "vulkan1.2", str(glsl), "-o", str(spv)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["spirv-val", "--target-env", "vulkan1.2", str(spv)], check=True)
        expected = []
        for group in range(3):
            for lane in range(threads):
                x, y, base = lane % 2, (lane % 4)//2, lane - lane % 4
                lo = base if "Coarse" in op else base + (x if "dy" in op else 2*y)
                hi = lo + (2 if "dy" in op else 1)
                val = lane % 32 if op == "lane" else hi*hi-lo*lo
                expected.append(struct.unpack("<I", struct.pack("<f", float(val)))[0])
        cases.append(dict(name=name, shape=shape, threads=threads, input=shape_name+".bin", expected=expected))
(a.output / "cases.json").write_text(json.dumps(cases) + "\n")
print(f"Generated {len(cases)} probes")
