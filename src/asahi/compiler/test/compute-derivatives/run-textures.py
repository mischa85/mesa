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
a = p.parse_args()
env = dict(os.environ, VK_DRIVER_FILES=str(a.icd.resolve()), HK_EXPERIMENTAL_APPLE9='1', MESA_SHADER_CACHE_DISABLE='true')
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
        if not all(map(math.isfinite, [implicit,explicit,qx,qy])): failures.append('nonfinite')
        if abs(implicit-explicit) > .002: failures.append('gradient control')
        # Anisotropic LOD selection is implementation dependent. For that
        # arm compare the two sample paths; retain query values as evidence.
        if case['aniso'] == 1:
            if abs(implicit-case['expected_sample']) > .04: failures.append('sample reference')
            if abs(explicit-case['expected_sample']) > .04: failures.append('explicit reference')
            if abs(qx-case['expected_query'][0]) > .04: failures.append('clamped query')
            if abs(qy-case['expected_query'][1]) > .04: failures.append('unclamped query')
        if failures: bad.append(dict(row=i,failures=failures,values=[implicit,explicit,qx,qy]))
    result = dict(case=case,returncode=proc.returncode,row_count=len(rows),bad=bad,
                  stderr=proc.stderr,rows=rows)
    result['pass'] = proc.returncode == 0 and len(rows) == case['count'] and not bad
    results.append(result)
    a.output.write_text(json.dumps(results,separators=(',',':'))+'\n')
    print(name, 'PASS' if result['pass'] else 'FAIL', len(bad), flush=True)
print(json.dumps(dict(collections.Counter('pass' if r['pass'] else 'fail' for r in results))))
