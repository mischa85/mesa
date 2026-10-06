#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate tiny authored shaders and exact-bit input controls; no corpus copy."""

import argparse, json, re, struct, subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("output", type=Path)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
header = (Path(__file__).resolve().parents[2] / "agx_apple9_ir.h").read_text()
enum = header.split("enum agx_apple9_vir_opcode {")[1].split("};")[0]
(a.output / "opcodes.json").write_text(
    json.dumps(re.findall(r"AGX_APPLE9_VIR_\w+", enum)) + "\n"
)
cases = []


def add(name, a, b=0, c=0):
    cases.append(dict(name=name, words=[a, b, c, 0xA5010000 + len(cases)]))


for name, bits in [
    ("pzero", 0),
    ("nzero", 0x80000000),
    ("pminsub", 1),
    ("nminsub", 0x80000001),
    ("pmidsub", 0x00400000),
    ("nmidsub", 0x80400000),
    ("pmaxsub", 0x007FFFFF),
    ("nmaxsub", 0x807FFFFF),
    ("pminnorm", 0x00800000),
    ("nminnorm", 0x80800000),
    ("one", 0x3F800000),
    ("negative_one", 0xBF800000),
    ("half", 0x3F000000),
    ("one_and_half", 0x3FC00000),
    ("two_and_half", 0x40200000),
    ("infinity", 0x7F800000),
    ("negative_infinity", 0xFF800000),
    ("qnan", 0x7FC12345),
]:
    add(name, bits)
    add(name + "_one", bits, 0x3F800000)
add("normal_add_to_subnormal", 0x00800001, 0x80800000)
add("normal_add_to_negative_subnormal", 0x80800001, 0x00800000)
add("add_input_daz", 0x00800000, 0x807FFFFF)
add("add_input_daz_reverse", 0x807FFFFF, 0x00800000)
add("subnormal_sum_to_normal", 0x007FFFFF, 0x007FFFFF)
add("mul_input_to_normal", 1, 0x7E800000)
add("mul_negative_input_to_normal", 0x80000001, 0x7E800000)
add("mul_normal_to_subnormal", 0x00800000, 0x3F000000)
add("mul_negative_normal_to_subnormal", 0x80800000, 0x3F000000)
add("fma_input_to_normal", 1, 0x7E800000, 0x3F800000)
add("fma_addend_daz", 0x00800000, 0x3F800000, 0x807FFFFF)
add("fma_cancellation_to_subnormal", 0x00800001, 0x3F800000, 0x80800000)
add("fma_underflow_product_normal_result", 0x00800000, 0x3F000000, 0x00800000)
add("p_sub_n_sub", 1, 0x80000001)
add("n_sub_p_sub", 0x80000001, 1)
add("unequal_subnormals", 0x00400000, 1)
add("unequal_subnormals_reverse", 1, 0x00400000)
add("normal_control", 0x3FC00000, 0x40200000, 0x3F000000)
add("negative_control", 0xBFC00000, 0x40200000, 0x3F000000)
add("reciprocal_to_subnormal", 0x7F000000)
add("exp2_to_subnormal", 0xC2FE0000)  # -127
add("exp2_min_subnormal", 0xC3150000)  # -149
add("half_min_subnormal_output", 0x33800000)  # 2^-24
add("half_max_subnormal_output", 0x387FC000)
add("half_min_normal_output", 0x38800000)
add("half_max_finite_output", 0x477FE000)
add("half_min_subnormal_input", 1)
add("half_max_subnormal_input", 0x03FF)
add("half_min_normal_input", 0x0400)
add("half_negative_subnormal_input", 0x8001)
(a.output / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
(a.output / "inputs.bin").write_bytes(
    b"".join(struct.pack("<4I", *c["words"]) for c in cases)
)
ops = {
    "identity": "u.x",
    "negate": "floatBitsToUint(-x)",
    "abs": "floatBitsToUint(abs(x))",
    "select_passthrough": "floatBitsToUint(u.y != 0u ? x : y)",
    "multiply_one": "floatBitsToUint(x*1.0)",
    "double_negate": "floatBitsToUint(-(-x))",
    "add": "floatBitsToUint(x+y)",
    "multiply": "floatBitsToUint(x*y)",
    "fma": "floatBitsToUint(fma(x,y,z))",
    "add_abs": "floatBitsToUint(abs(x)+y)",
    "multiply_abs": "floatBitsToUint(abs(x)*y)",
    "fma_abs": "floatBitsToUint(fma(abs(x),y,z))",
    "multiply_two": "floatBitsToUint(x*2.0)",
    "add_half": "floatBitsToUint(x+0.5)",
    "min": "floatBitsToUint(min(x,y))",
    "max": "floatBitsToUint(max(x,y))",
    "less": "uint(x<y)",
    "equal": "uint(x==y)",
    "not_equal": "uint(x!=y)",
    "sign": "floatBitsToUint(sign(x))",
    "floor": "floatBitsToUint(floor(x))",
    "ceil": "floatBitsToUint(ceil(x))",
    "trunc": "floatBitsToUint(trunc(x))",
    "round_even": "floatBitsToUint(roundEven(x))",
    "fract": "floatBitsToUint(fract(x))",
    "exp2": "floatBitsToUint(exp2(x))",
    "log2": "floatBitsToUint(log2(x))",
    "sqrt": "floatBitsToUint(sqrt(x))",
    "inverse_sqrt": "floatBitsToUint(inversesqrt(x))",
    "reciprocal": "floatBitsToUint(1.0/x)",
    "sin": "floatBitsToUint(sin(x))",
    "cos": "floatBitsToUint(cos(x))",
    "f32_to_half": "packHalf2x16(vec2(x,0.0))",
    "half_to_f32": "floatBitsToUint(unpackHalf2x16(u.x).x)",
    "f32_to_i32": "uint(int(x))",
    "f32_to_u32": "uint(x)",
    "i32_to_f32": "floatBitsToUint(float(int(u.x)))",
    "u32_to_f32": "floatBitsToUint(float(u.x))",
    "atomic_add": None,
    "atomic_add_return": None,
    "subgroup_min_cluster1": "floatBitsToUint(subgroupClusteredMin(x,1))",
    "subgroup_max_cluster1": "floatBitsToUint(subgroupClusteredMax(x,1))",
}
for name, expr in ops.items():
    source = """#version 450
layout(local_size_x=32) in;
layout(set=0,binding=0,std430) readonly buffer Input { uvec4 data[]; } input_data;
layout(set=0,binding=1,std430) writeonly buffer Output { uvec4 data[]; } output_data;
layout(push_constant) uniform Params { uint count; } p;
void main() {
 uint i=gl_GlobalInvocationID.x;if(i>=p.count)return;
 uvec4 u=input_data.data[i];
 precise float x=uintBitsToFloat(u.x),y=uintBitsToFloat(u.y),z=uintBitsToFloat(u.z);
 precise uint result=EXPR;
 output_data.data[i]=uvec4(u.xy,result,u.w^0x6d2b79f5u);
}
"""
    if name.startswith("subgroup_"):
        source = source.replace(
            "#version 450",
            "#version 450\n"
            "#extension GL_KHR_shader_subgroup_arithmetic : require\n"
            "#extension GL_KHR_shader_subgroup_clustered : require",
        )
    if name.startswith("atomic_add"):
        source = source.replace(
            "#version 450",
            "#version 450\n#extension GL_EXT_shader_atomic_float : require",
        )
        source = source.replace(
            "layout(set=0,binding=1,std430) writeonly buffer Output { uvec4 data[]; } output_data;",
            "struct Result { uint a; uint b; float value; uint tag; };\nlayout(set=0,binding=1,std430) buffer Output { Result data[]; } output_data;",
        )
        source = source.replace(
            "precise uint result=EXPR;", "atomicAdd(output_data.data[i].value, y);"
        )
        if name == "atomic_add_return":
            source = source.replace(
                "atomicAdd(output_data.data[i].value, y);",
                "float old=atomicAdd(output_data.data[i].value, y);\n"
                "output_data.data[i].value=old;",
            )
        source = source.replace(
            "output_data.data[i]=uvec4(u.xy,result,u.w^0x6d2b79f5u);",
            "output_data.data[i].a=u.x;output_data.data[i].b=u.y;output_data.data[i].tag=u.w^0x6d2b79f5u;",
        )
    else:
        source = source.replace("EXPR", expr)
    path = a.output / (name + ".comp")
    path.write_text(source)
    subprocess.run(
        [
            "glslangValidator",
            "-V",
            "--target-env",
            "vulkan1.2",
            str(path),
            "-o",
            str(a.output / (name + ".spv")),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    # Explicit FTZ variants also preserve signs of zero, infinities and NaNs.
    # Keep default-mode probes separate: they characterize existing behavior.
    words = list(
        struct.unpack(
            "<%dI" % ((a.output / (name + ".spv")).stat().st_size // 4),
            (a.output / (name + ".spv")).read_bytes(),
        )
    )
    i = 5
    entry = None
    cap_end = None
    mode_end = None
    while i < len(words):
        count, op = words[i] >> 16, words[i] & 0xFFFF
        if op == 17:
            cap_end = i + count
        if op == 15:
            entry = words[i + 2]
        if op == 16:
            mode_end = i + count
        i += count
    assert entry is not None and cap_end is not None and mode_end is not None
    words[mode_end:mode_end] = [
        4 << 16 | 16,
        entry,
        4460,
        32,
        4 << 16 | 16,
        entry,
        4461,
        32,
    ]
    words[cap_end:cap_end] = [2 << 16 | 17, 4465, 2 << 16 | 17, 4466]
    ftz = a.output / "ftz"
    ftz.mkdir(exist_ok=True)
    (ftz / (name + ".spv")).write_bytes(struct.pack("<%dI" % len(words), *words))
    subprocess.run(
        ["spirv-val", "--target-env", "vulkan1.2", str(ftz / (name + ".spv"))],
        check=True,
    )
(a.output / "operations.json").write_text(json.dumps(ops, indent=2) + "\n")
print(
    f"{len(ops)} operations x {len(cases)} inputs; integer transport/tag controls in each output"
)
