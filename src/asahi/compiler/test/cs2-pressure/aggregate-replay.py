#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stream replay totals, preserving SAVE/FILL and separate at-cap cohorts.

Uses the coordinator's parse/compare modules for opcode enums and true swaps.
Based on the streaming reader in tmp/cs2-shaders-20261004/stream-compare.py.
"""
import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--parser-dir', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('baseline', type=Path)
p.add_argument('fixed', type=Path)
a = p.parse_args()
sys.path.insert(0, str(a.parser_dir.resolve()))
from parse import asm_re, stats_re, OPS, ENCS
from compare import metrics


def programs(path):
    name = source = cur = None
    opener = gzip.open if path.suffix == '.gz' else open
    for line in opener(path, 'rt', errors='replace'):
        if line.startswith('shader: MESA_SHADER_'):
            name = source = None
        elif line.startswith('name: '):
            name = line[6:].strip()
        elif line.startswith('source_blake3:'):
            source = line.strip()
        elif line.startswith(('APPLE9_ASM_BEGIN', 'APPLE9_PREAMBLE_ASM_BEGIN')):
            kind, stage = re.match(r'(APPLE9(?:_PREAMBLE)?)_ASM_BEGIN stage=(\d+)', line).groups()
            cur = dict(kind=kind, stage=int(stage), name=name, source=source, asm=[])
        if cur is None:
            continue
        m = asm_re.match(line)
        if m:
            off, op, enc, dst, src, imm, wait, prod, by = m.groups()
            cur['asm'].append(dict(op=OPS.get(int(op), op), enc=ENCS.get(int(enc), enc),
                                   dst=dst, src=src.split(',') if src else [],
                                   imm=int(imm, 16), wait=int(wait), producer=int(prod)))
        m = stats_re.match(line)
        if m:
            keys = ['bytes', 'instructions', 'copies', 'waits', 'saves', 'fills', 'gprs', 'scratch']
            cur['stats'] = dict(zip(keys, map(int, m.groups()[2:])))
            if cur['kind'] == 'APPLE9' and cur['name'] != 'stub VS':
                assert len(cur['asm']) == cur['stats']['instructions']
                yield cur
            cur = None


def aggregate(path):
    groups = collections.defaultdict(collections.Counter)
    sources = collections.Counter()
    for program in programs(path):
        m = metrics(program)
        m.update({k: program['stats'][k] for k in ('bytes', 'saves', 'fills', 'waits')})
        stage = {0: 'vertex', 4: 'fragment', 5: 'compute'}.get(program['stage'], str(program['stage']))
        sources[(stage, program['source'])] += 1
        for group in [stage] + ([stage + ' at96'] if m['gprs'] >= 96 else []):
            groups[group]['programs'] += 1
            for key in ('instrs', 'swaps', 'copies', 'bytes', 'saves', 'fills', 'spills', 'waits'):
                groups[group][key] += m[key]
            groups[group]['scratch_sum_bytes'] += program['stats']['scratch']
            groups[group]['scratch_max_bytes'] = max(groups[group]['scratch_max_bytes'], program['stats']['scratch'])
            groups[group]['spilling_programs'] += bool(m['spills'])
    return dict(groups), sources


ga, sa = aggregate(a.baseline)
gb, sb = aggregate(a.fixed)
out = dict(baseline=ga, fixed=gb, source_multisets_equal=sa == sb,
           unmatched_baseline=sum((sa - sb).values()), unmatched_fixed=sum((sb - sa).values()),
           cohort_note='at96 independently selects each compiler output; it is not a fixed paired cohort')
a.output.write_text(json.dumps(out, indent=2) + '\n')
for group in sorted(set(ga) | set(gb)):
    print(group)
    for key in ga.get(group, gb.get(group)):
        x, y = ga.get(group, {}).get(key, 0), gb.get(group, {}).get(key, 0)
        print(f'  {key:12} {x:12} -> {y:12} ({(y-x)/x*100 if x else 0:+.2f}%)')
print('source multisets equal:', sa == sb)
