#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check sample controls, analytic LODs, every row, and transport echoes."""
import argparse, collections, json, math, os, struct, subprocess
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('directory', type=Path)
p.add_argument('--probe', type=Path, required=True)
p.add_argument('--icd', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--dimension', nargs='*')
p.add_argument('--null-image', action='store_true')
a = p.parse_args()
env = dict(os.environ, VK_DRIVER_FILES=str(a.icd.resolve()), HK_EXPERIMENTAL_APPLE9='1', MESA_SHADER_CACHE_DISABLE='true')
env.pop('PROBE_NULL_IMAGE', None)
if a.null_image: env['PROBE_NULL_IMAGE'] = '1'
for k in ['ASAHI_MESA_DEBUG','AGX_MESA_DEBUG','AGX_APPLE9_STATS','HK_PERFTEST']:
    env.pop(k, None)
results = []
def f32(u): return struct.unpack('<f', struct.pack('<I',u))[0]
for case in json.loads((a.directory/'texture-cases.json').read_text()):
    if a.dimension and case['dim'] not in a.dimension: continue
    name = case['name']
    cmd = [str(a.probe.resolve()), str(a.directory/f'{name}.spv'), str(a.directory/f'{name}.bin'),
           case['dim'], str(case['threads']), str(case['bias']), str(case['min_lod']),
           str(case['max_lod']), str(case['base']), str(case['aniso']), str(int(case['nearest']))]
    if case.get('view_min') is not None: cmd.append(str(case['view_min']))
    proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    rows = []
    for line in proc.stdout.splitlines():
        words = line.split()
        if len(words) != 9: continue
        rows.append([int(words[0])] + [int(v,16) for v in words[1:]])
    data = (a.directory/f'{name}.bin').read_bytes()
    bad = []
    for index, row in enumerate(rows):
        i, *v = row
        failures = []
        expected_in = struct.unpack_from('<4I',data,index*16) if index < case['count'] else (0,)*4
        if i != index or v[:2] != list(expected_in[:2]) or v[3] != (i ^ 0x6d2b79f5) or v[7] != (i ^ 0xa5120000):
            failures.append('transport')
        implicit, explicit, qx, qy = map(f32, (v[2], v[4], v[5], v[6]))
        if not all(map(math.isfinite, [implicit,explicit,qx])) or math.isnan(qy): failures.append('nonfinite')
        if case['lod'] is not None and not math.isfinite(qy): failures.append('nonfinite LOD')
        # Cube gradients become scalar Q6 LODs. A rounded input subtraction
        # and the analytic gradient literal can straddle one Q6 boundary,
        # even when their difference is a single FP32 rounding error.
        gradient_tolerance = 1/64 + .002 if case['dim'].startswith('cube') else .002
        if abs(implicit-explicit) > gradient_tolerance: failures.append('gradient control')
        # Every mip is tagged with its physical level plus one. Query and
        # sampling must agree even where anisotropic selection is variable.
        if a.null_image:
            if [implicit,explicit,qx,qy] != [0.,0.,0.,0.]: failures.append('null descriptor')
        elif abs(implicit-(qx+case['base']+1)) > .04: failures.append('query/sample agreement')
        # Only the isotropic arms have an implementation-independent oracle.
        if case['aniso'] == 1 and not a.null_image:
            if abs(implicit-case['expected_sample']) > .04: failures.append('sample reference')
            if abs(explicit-case['expected_sample']) > .04: failures.append('explicit reference')
            if abs(qx-case['expected_query'][0]) > .04: failures.append('clamped query')
            if case['expected_query'][1] is None:
                if qy > -16: failures.append('zero-gradient query')
            elif abs(qy-case['expected_query'][1]) > .04: failures.append('unclamped query')
        if failures: bad.append(dict(row=i,failures=failures,values=[implicit,explicit,qx,qy]))
    result = dict(case=case,returncode=proc.returncode,row_count=len(rows),bad=bad,
                  stderr=proc.stderr,rows=rows)
    result['pass'] = proc.returncode == 0 and len(rows) == case['count'] and not bad
    results.append(result)
    a.output.write_text(json.dumps(results,separators=(',',':'))+'\n')
    print(name, 'PASS' if result['pass'] else 'FAIL', len(bad), flush=True)
print(json.dumps(dict(collections.Counter('pass' if r['pass'] else 'fail' for r in results))))
