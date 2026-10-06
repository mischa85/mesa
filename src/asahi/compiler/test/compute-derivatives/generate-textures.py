#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mip-tagged compute samples and LOD queries with analytic gradient controls."""
import argparse, hashlib, json, math, struct, subprocess
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('output', type=Path)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
cases = []
# Linear mip filtering keeps the query/reference continuous. A nonzero view
# base distinguishes view-relative LOD from physical mip indices.
configs = [(0., 0., 5., 0, 1., False), (.5, 1., 3., 0, 1., False),
           (-1., 0., 2., 1, 1., False), (0., 0., 5., 0, 4., False),
           (.25, 0., 5., 0, 1., True)]
for dim in ['1d', '1da', '2d', '2da', '3d', 'cube', 'cubea']:
    array = dim.endswith('a')
    axes = 3 if dim.startswith(('cube', '3d')) else int(dim[0])
    sampler = {'1d':'1D', '1da':'1DArray', '2d':'2D', '2da':'2DArray', '3d':'3D', 'cube':'Cube', 'cubea':'CubeArray'}[dim]
    for shape in [(4,4,1), (20,1,1)]:
        threads = math.prod(shape)
        for lod in [-1., 1., 3.]:
            for config, (bias, lo, hi, base, aniso, nearest) in enumerate(configs):
                name = f'{dim}_{threads}_lod{int(lod)}_s{config}'
                scale = 2**lod / (32 >> base)
                coords = []
                for i in range(3 * threads):
                    lane = i % threads
                    x = .25 + (lane % 2) * scale
                    y = .25 + ((lane % 4) // 2) * scale
                    layer = float(i % 2)  # Layer variation must not enter the gradients.
                    if dim.startswith('cube'):
                        c = [1., 2*y-1, 1-2*x, layer if array else 0.]
                    elif axes == 1:
                        c = [x, layer if array else 0., 0., 0.]
                    else:
                        c = [x, y, layer if array else .5, 0.]
                    coords.extend(c)
                (a.output / f'{name}.bin').write_bytes(struct.pack(f'<{len(coords)}f', *coords))
                sample_coord = 'c.' + 'xyzw'[:axes + array]
                query_coord = 'c.' + 'xyz'[:axes]
                if dim.startswith('cube'):
                    dx, dy = f'vec3(0,0,{-2*scale})', f'vec3(0,{2*scale},0)'
                elif axes == 1:
                    dx, dy = str(scale), '0.0'
                else:
                    dx = f'vec{axes}({scale},0' + (',0)' if axes == 3 else ')')
                    dy = f'vec{axes}(0,{scale}' + (',0)' if axes == 3 else ')')
                source = f'''#version 450
#extension GL_NV_compute_shader_derivatives : require
layout(local_size_x={shape[0]},local_size_y={shape[1]},local_size_z={shape[2]}) in;
layout(derivative_group_linearNV) in;
layout(set=0,binding=0,std430) readonly buffer In {{ uvec4 input_data[]; }};
layout(set=0,binding=1,std430) writeonly buffer Out {{ uvec4 output_data[]; }};
layout(set=0,binding=2) uniform sampler{sampler} tex;
void main() {{
  uint i=gl_WorkGroupID.x*{threads}u+gl_LocalInvocationIndex;
  uvec4 v=input_data[i];
  vec4 c=uintBitsToFloat(v);
  float implicit_value=texture(tex,{sample_coord}).r;
  float explicit_value=textureGrad(tex,{sample_coord},{dx},{dy}).r;
  vec2 lod=textureQueryLod(tex,{query_coord});
  output_data[2*i]=uvec4(v.xy,floatBitsToUint(implicit_value),i^0x6d2b79f5u);
  output_data[2*i+1]=uvec4(floatBitsToUint(explicit_value),floatBitsToUint(lod),i^0xa5120000u);
}}
'''
                glsl, spv = a.output / f'{name}.comp', a.output / f'{name}.spv'
                glsl.write_text(source)
                subprocess.run(['glslangValidator','-V','--target-env','vulkan1.2',str(glsl),'-o',str(spv)],check=True,stdout=subprocess.DEVNULL)
                subprocess.run(['spirv-val','--target-env','vulkan1.2',str(spv)],check=True)
                raw = lod + bias
                clamped = max(lo, min(raw, hi, 5-base))
                if nearest:
                    clamped = math.floor(clamped + .5)
                cases.append(dict(name=name,dim=dim,shape=shape,threads=threads,count=3*threads,
                    bias=bias,min_lod=lo,max_lod=hi,base=base,aniso=aniso,lod=lod,nearest=nearest,
                    expected_sample=base+1+clamped,expected_query=[clamped,raw],
                    spirv_sha256=hashlib.sha256(spv.read_bytes()).hexdigest(),
                    input_sha256=hashlib.sha256((a.output/f'{name}.bin').read_bytes()).hexdigest()))
(a.output / 'texture-cases.json').write_text(json.dumps(cases,indent=2)+'\n')
print(f'Generated and validated {len(cases)} texture probes')
