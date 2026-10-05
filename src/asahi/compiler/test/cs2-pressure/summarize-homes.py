#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Relate surviving repair SSA values to their original variable/frame homes."""
import argparse
import collections
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('log', type=Path)
p.add_argument('events', type=Path)
p.add_argument('--id', type=int, default=10)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
active = False
homes = collections.defaultdict(set)
renames = {}
for line in a.log.open():
    if line.startswith('RA_AUDIT_BEGIN '):
        active = f'id={a.id} ' in line
    if not active:
        continue
    d = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
    if line.startswith('RA_AUDIT_HOME '):
        homes[d['ssa']].add((d['node'], d['mem']))
    elif line.startswith('RA_AUDIT_REINDEX '):
        renames[d['old']] = d['new']
    elif line.startswith('RA_AUDIT_END '):
        active = False
homes = {renames[k]: v for k, v in homes.items() if k in renames}
assert homes and all(len(v) == 1 for v in homes.values())
events = json.loads(a.events.read_text())
phis = [e for e in events if e['kind'] == 'RA_AUDIT_PHI']
counts = collections.Counter()
memory_edges = []
for phi in phis:
    # Introduced after repair/reindex, so it has no repair-home record.
    if phi['origin'] == 'live-in-reconcile':
        continue
    dh = homes[int(phi['dst'])]
    for src in phi['src'].split(','):
        ssa, reg, mem = map(int, src.split(':'))
        if int(phi['reg']) == reg and int(phi['mem']) == mem:
            continue
        sh = homes.get(ssa, set())
        key = (phi['origin'] + (':mem' if int(phi['mem']) else ':gpr') +
               (':same-home' if dh == sh else ':different-home'))
        counts[key] += int(phi['width'])
        if int(phi['mem']):
            memory_edges.append(dict(phi=int(phi['phi']), dst=int(phi['dst']),
                                     src=ssa, dst_home=sorted(dh), src_home=sorted(sh),
                                     origin=phi['origin'], width=int(phi['width'])))
summary = dict(
    id=a.id, surviving_definitions=len(homes),
    memory_homes=len({next(iter(v))[0] for v in homes.values() if next(iter(v))[1]}),
    edge_word_mismatches=dict(counts),
    repair_memory_homes_moved=len({tuple(h) for e in memory_edges
                                  if e['origin'] == 'spill-repair'
                                  for h in e['dst_home'] + e['src_home']}))
a.output.mkdir(parents=True, exist_ok=True)
(a.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
(a.output / 'homes.json').write_text(json.dumps({k: sorted(v) for k, v in homes.items()}, indent=2) + '\n')
(a.output / 'memory-edges.json').write_text(json.dumps(memory_edges, indent=2) + '\n')
print(json.dumps(summary, indent=2))
