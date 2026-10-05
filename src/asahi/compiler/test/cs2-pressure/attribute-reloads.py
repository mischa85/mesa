#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Trace GPR phi-cycle inputs to reloads and original definitions offline."""
import argparse
import collections
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('summary', type=Path)
p.add_argument('homes', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
cfg = json.loads((a.summary / 'cfg.json').read_text())
events = json.loads((a.summary / 'events.json').read_text())
cycles = json.loads((a.summary / 'cycles.json').read_text())
homes = {int(k): v[0] for k, v in json.loads(a.homes.read_text()).items()}
defs = {}
instructions = []

def operand(text):
    m = re.match(r'^(m?)[*]?(\d+)(?:[hd])?(?:\.(?:abs|neg))*$', text.strip())
    return dict(ssa=int(m[2]), mem=bool(m[1])) if m else None

for block, info in cfg['blocks'].items():
    for line in info['lines']:
        if not line:
            continue
        parts = line.split(' = ')
        destinations = [operand(x) for x in parts[0].split(',')] if len(parts) == 2 else []
        rhs = parts[-1].split(maxsplit=1)
        op = rhs[0]
        sources = [operand(x) for x in rhs[1].split(',')] if len(rhs) == 2 else []
        ins = dict(block=int(block), op=op, dest=[x for x in destinations if x],
                   src=[x for x in sources if x], line=line)
        instructions.append(ins)
        for d in ins['dest']:
            defs[d['ssa']] = ins

def leaves(ssa, seen):
    if ssa in seen:
        return set()
    assert ssa in defs, ssa
    ins = defs[ssa]
    if ins['op'] == 'phi':
        result = set()
        for src in ins['src']:
            result |= leaves(src['ssa'], seen | {ssa})
        return result
    return {ssa}

def kind(ssa):
    ins = defs[ssa]
    return 'frame-reload' if ins['op'] == 'mov' and any(x['mem'] for x in ins['src']) else ins['op']

phis = {int(e['phi']): e for e in events if e['kind'] == 'RA_AUDIT_PHI'}
roots = {}
for cycle in cycles:
    if cycle['mem']:
        continue
    for phi in cycle['phis']:
        e = phis[phi]
        if e['origin'] == 'spill-repair':
            dst = int(e['dst'])
            roots[dst] = leaves(dst, set())
root_classes = collections.Counter(','.join(sorted({kind(v) for v in vs})) for vs in roots.values())
pure_cycles = collections.Counter()
for cycle in cycles:
    if cycle['mem'] or cycle['origins'] != ['spill-repair']:
        continue
    kinds = {kind(v) for phi in cycle['phis'] for v in roots[int(phis[phi]['dst'])]}
    key = ','.join(sorted(kinds))
    pure_cycles[key] += cycle['swaps']

reloads = [i for i in instructions if i['op'] == 'mov' and i['dest'] and
           not i['dest'][0]['mem'] and any(s['mem'] for s in i['src'])]
loops = {}
for header, loop in cfg['loops'].items():
    blocks = set(loop['blocks'])
    # Exclude phi and frame-transfer uses. Treat GPR-to-GPR moves as uses too,
    # so forwarding a value to another variable cannot create a false
    # live-through classification. This counts original variables, not runs.
    used = {homes[s['ssa']][0] for i in instructions if i['block'] in blocks and
            i['op'] != 'phi' and not (i['op'] == 'mov' and
            any(x['mem'] for x in i['src'] + i['dest']))
            for s in i['src'] if not s['mem']}
    inside = [i for i in reloads if i['block'] in blocks]
    through = [i for i in inside if homes[i['dest'][0]['ssa']][0] not in used]
    loops[header] = dict(block_count=len(blocks), reloads=len(inside),
                         no_noncopy_use_in_loop=len(through),
                         through_reload_ssa=[i['dest'][0]['ssa'] for i in through])

report = dict(repair_cycle_member_phis=len(roots), root_classes=dict(root_classes),
              pure_repair_cycle_swaps_by_root_class=dict(pure_cycles),
              reload_instructions=len(reloads), loops=loops)
a.output.mkdir(parents=True, exist_ok=True)
(a.output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
(a.output / 'roots.json').write_text(json.dumps({v: [dict(ssa=x, kind=kind(x), **defs[x]) for x in sorted(ls)] for v, ls in roots.items()}, indent=2) + '\n')
print(json.dumps(report, indent=2))
