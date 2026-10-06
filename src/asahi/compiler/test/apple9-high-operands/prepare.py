#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Author pressure shaders for a later, coordinator-owned Metal/HV session."""
import argparse
import json
from pathlib import Path
import shutil

CASES = {
    'sample': ('fragment', ['TEXTURE_SAMPLE:DEST'], 'float4 texel = tex.sample(smp, uv);'),
    'lod': ('compute', ['TEXTURE_LOD:DEST'], 'float4 texel = tex.sample(smp, uv, level(float(h & 3u)));'),
    'grad': ('fragment', ['TEXTURE_GRAD:DEST'], 'float4 texel = tex.sample(smp, uv, gradient2d(uv * 0.01f, uv.yx * 0.02f));'),
    'shared': ('compute', ['SHARED_STORE:SRC0', 'SHARED_STORE:SRC1', 'SHARED_LOAD:DEST', 'SHARED_LOAD:SRC0'], '''threadgroup uint shared_words[32];
    shared_words[lane] = h;
    threadgroup_barrier(mem_flags::mem_threadgroup);
    uint result = shared_words[(lane + 1u) & 31u];'''),
    'private': ('compute', ['PRIVATE_STORE:SRC0', 'PRIVATE_STORE:SRC1', 'PRIVATE_LOAD:DEST', 'PRIVATE_LOAD:SRC0'], '''thread uint private_words[32];
    for (uint j = 0; j < 32; ++j) private_words[j] = h ^ (j * 0x9e3779b9u);
    private_words[(h >> 8u) & 31u] = v0;
    uint result = private_read(private_words, h & 31u);'''),
    'scan': ('compute', ['SUBGROUP_SCAN_IADD:DEST', 'SUBGROUP_SCAN_IADD:SRC0'], 'uint result = simd_prefix_exclusive_sum(h);'),
    'broadcast': ('compute', ['SUBGROUP_BROADCAST:DEST', 'SUBGROUP_BROADCAST:SRC0', 'SUBGROUP_BROADCAST:SRC1'], 'uint result = simd_broadcast(h, ushort(group.x & 31u));'),
    'ballot': ('compute', ['SUBGROUP_BALLOT:DEST', 'SUBGROUP_BALLOT:SRC0'], 'uint result = uint(static_cast<simd_vote::vote_t>(simd_ballot((h & 1u) != 0u)));'),
    'get_sr': ('compute', ['GET_SR:DEST', 'GET_SR_ZEXT16:DEST'], 'uint result = h ^ local.x ^ (local.y << 5u) ^ (local.z << 10u) ^ (group.x << 15u) ^ (simd_index << 20u) ^ lane;'),
    'half': ('compute', ['FLOAT_TO_HALF_ZEXT:DEST'], 'uint result = uint(as_type<ushort>(half(as_type<float>((h & 0x007fffffu) | 0x3f800000u))));'),
    'float2': ('compute', ['FLOAT2_BASE:DEST', 'FLOAT2_BASE:SRC0', 'FLOAT2_BASE:SRC1'], '''float a = as_type<float>((h & 0x007fffffu) | 0x3f800000u);
    float b = as_type<float>((v0 & 0x007fffffu) | 0x3f800000u);
    uint result = as_type<uint>(a * b + a);'''),
    'float3': ('compute', ['FLOAT3_COMPACT:DEST', 'FLOAT3_COMPACT:SRC0', 'FLOAT3_COMPACT:SRC1', 'FLOAT3_COMPACT:SRC2'], '''float a = as_type<float>((h & 0x007fffffu) | 0x3f800000u);
    float b = as_type<float>((v0 & 0x007fffffu) | 0x3f800000u);
    float c = as_type<float>((v1 & 0x007fffffu) | 0x3f800000u);
    uint result = as_type<uint>(fma(a, b, c));'''),
}


def shader(case, n):
    stage, _, operation = CASES[case]
    lines = ['#include <metal_stdlib>', 'using namespace metal;']
    if case == 'private':
        lines += ['__attribute__((noinline)) uint private_read(thread uint *p, uint index) { return p[index]; }']
    params = ('device uint *input [[buffer(0)]], device uint *output [[buffer(1)]], '
              'texture2d<float> tex [[texture(0)]], sampler smp [[sampler(0)]]')
    if stage == 'fragment':
        lines += ['struct IO { float4 position [[position]]; };',
                  'vertex IO v(uint id [[vertex_id]]) { return {float4(float(id & 1u) * 2.0f - 1.0f, float(id >> 1u) * 2.0f - 1.0f, 0.0f, 1.0f)}; }',
                  f'fragment float4 f(IO in [[stage_in]], {params}) {{',
                  '    uint g = uint(in.position.x);']
    else:
        lines += [f'kernel void k({params}, uint g [[thread_position_in_grid]],',
                  '    uint3 local [[thread_position_in_threadgroup]], uint3 group [[threadgroup_position_in_grid]],',
                  '    uint lane [[thread_index_in_simdgroup]], uint simd_index [[simdgroup_index_in_threadgroup]]) {']
    lines += [f'    uint v{i} = input[g * {n}u + {i}u];' for i in range(n)]
    # Destructive writes prevent simply delaying loads until after the target.
    lines += [f'    for (uint j = 0; j < {n}u; ++j) input[g * {n}u + j] = 0u;', '    uint h = 0x13579bdfu;']
    lines += [f'    h = ((h << 5u) | (h >> 27u)) ^ v{i};' for i in range(n)]
    if case in ('sample', 'lod', 'grad'):
        lines += ['    float2 uv = float2(float(h & 1023u), float((h >> 10u) & 1023u)) / 1024.0f;',
                  '    ' + operation, '    uint4 bits = as_type<uint4>(texel);',
                  '    uint result = bits.x ^ bits.y ^ bits.z ^ bits.w;']
    else:
        lines += ['    ' + operation]
    # Distinct output words keep every loaded value live across the target.
    lines += [f'    output[g * {n}u + {i}u] = (v{i} ^ result) + ((v{(i+1)%n} << 7u) | (v{(i+1)%n} >> 25u));' for i in range(n)]
    if stage == 'fragment':
        lines += ['    return texel;']
    return '\n'.join(lines + ['}', ''])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, (stage, targets, _) in CASES.items():
        for words in (8, 90, 96):
            stem = f'{name}-{words}'
            (args.output / f'{stem}.metal').write_text(shader(name, words))
            manifest.append(dict(name=stem, source=f'{stem}.metal', stage=stage,
                                 live_values=words, max_threads=32 if stage == 'compute' else 0,
                                 targets=targets))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    here = Path(__file__).resolve().parent
    for name in ('shdump.m', 'renderdump.m', 'compile.sh'):
        shutil.copyfile(here / name, args.output / name)
    (args.output / 'compile.sh').chmod(0o755)
    (args.output / 'manifest.txt').write_text(''.join(
        f"{r['stage']} {r['source']} {r['name']} {r['max_threads']}\n" for r in manifest))
    print(f'Prepared {len(manifest)} source cases; no Metal compilation or hardware access.')


if __name__ == '__main__':
    main()
