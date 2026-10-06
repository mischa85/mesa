#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute exact-bit derivative probes on a leased Apple9 device."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('shaders', type=Path)
p.add_argument('--probe', type=Path, required=True)
p.add_argument('--icd', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
env = dict(os.environ, VK_DRIVER_FILES=str(a.icd.resolve()),
           HK_EXPERIMENTAL_APPLE9='1', MESA_SHADER_CACHE_DISABLE='true')
env.pop('ASAHI_MESA_DEBUG', None)
lib = Path(json.loads(a.icd.read_text())['ICD']['library_path'])
if not lib.is_absolute():
    lib = a.icd.parent / lib
result = dict(library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(), records={})
for case in json.loads((a.shaders / 'cases.json').read_text()):
    run = subprocess.run([str(a.probe.resolve()), str(a.shaders / (case['name']+'.spv')),
                          str(a.shaders / case['input']), '--linear-derivatives',
                          str(case['threads'])], env=env, capture_output=True, text=True, timeout=30)
    rows = [line.split() for line in run.stdout.splitlines()]
    expected = case['expected']
    failures = []
    for i, row in enumerate(rows):
        if i >= len(expected) or len(row) != 5 or int(row[0]) != i or int(row[3],16) != expected[i]:
            failures.append(dict(index=i, actual=row, expected=expected[i] if i<len(expected) else None))
    ok = run.returncode == 0 and len(rows) == len(expected) and not failures
    result['records'][case['name']] = dict(pass_=ok, exit=run.returncode,
        count=len(rows), expected_count=len(expected), failures=failures[:16],
        stdout_sha256=hashlib.sha256(run.stdout.encode()).hexdigest(), device=run.stderr)
    print(case['name'], 'PASS' if ok else 'FAIL', len(rows), flush=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
assert all(r['pass_'] for r in result['records'].values())
