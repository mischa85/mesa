#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline estimate: safe phi congruence classes and constrained graph coloring.

No compiler placement changes. This model omits tuple-copy lowering and
instruction-local source windows, so its copy totals are an optimistic estimate.
"""
import argparse
import collections
import heapq
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('model', type=Path)
p.add_argument('audit', type=Path)
p.add_argument('trace', type=Path)
p.add_argument('--id', type=int, default=10)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--max-merges', type=int, default=1000000)
a = p.parse_args()
m = json.loads(a.model.read_text())
defs = {int(v): d for v, d in m['definitions'].items()}
adj = {int(v): sum(1 << u for u in ns) for v, ns in m['interference'].items()}
choose, actual = {}, {}
for line in a.trace.open():
    if not line.startswith(('RA_WEB_CHOOSE ', 'RA_WEB_ASSIGN ')):
        continue
    d = dict(re.findall(r'(\w+)=(\S*)', line))
    if int(d['id']) != a.id:
        continue
    d = {k: int(v) if v.isdigit() else v for k, v in d.items()}
    (choose if line.startswith('RA_WEB_CHOOSE ') else actual)[d['ssa']] = d
assert set(actual) == set(defs)
width = {v: d['width'] for v, d in actual.items()}
allowed = {}
for v in defs:
    d = choose.get(v, dict(min=10, max=192-width[v], align=width[v]))
    align = max(width[v], d['align'])
    allowed[v] = sum(1 << reg for reg in range(max(10, d['min']),
                    min(d['max'], 192-width[v])+1) if reg % align == 0)

parent = {v: v for v in defs}
member = {v: 1 << v for v in defs}
forbidden = dict(adj)
def root(v):
    if parent[v] != v:
        parent[v] = root(parent[v])
    return parent[v]
def nodes(mask):
    while mask:
        b = mask & -mask
        yield b.bit_length()-1
        mask ^= b

cfg = json.loads((a.audit / 'cfg.json').read_text())
priority = collections.Counter()
for dst, src, block in m['phi_edges']:
    priority[dst, src] += 8 ** min(int(cfg['depth'][str(block)]), 3)
accepted = rejected_interference = rejected_window = skipped_constants = 0
for (dst, src), weight in sorted(priority.items(), key=lambda x: (-x[1], x[0])):
    if accepted >= a.max_merges:
        break
    if defs[src]['op'] == 'mov_imm':
        skipped_constants += 1
        continue
    x, y = root(dst), root(src)
    if x == y:
        continue
    if forbidden[x] & member[y]:
        rejected_interference += 1
        continue
    if width[x] != width[y] or not (allowed[x] & allowed[y]):
        rejected_window += 1
        continue
    # Stable roots for reproducibility.
    if x > y:
        x, y = y, x
    parent[y] = x
    member[x] |= member[y]
    forbidden[x] |= forbidden[y]
    allowed[x] &= allowed[y]
    accepted += 1

groups = {v: list(nodes(member[v])) for v in defs if root(v) == v}
neighbors = {v: set() for v in groups}
for v in defs:
    x = root(v)
    for u in nodes(adj[v]):
        y = root(u)
        assert x != y
        neighbors[x].add(y)

# DSATUR with legal aligned starting positions in the actual 96-GPR file.
# Prefer the original placements when equally feasible.
prefs = {v: collections.Counter(actual[u]['chosen'] for u in us) for v, us in groups.items()}
available = {v: allowed[v] for v in groups}
versions = collections.Counter()
heap = []
def push(v):
    versions[v] += 1
    heapq.heappush(heap, (available[v].bit_count(), -len(neighbors[v]),
                          -len(groups[v]), v, versions[v]))
for v in groups:
    push(v)
colors = {}
failed = None
while heap:
    _, _, _, v, version = heapq.heappop(heap)
    if v in colors or version != versions[v]:
        continue
    if not available[v]:
        failed = v
        break
    reg = max(nodes(available[v]), key=lambda r: (prefs[v][r], -r))
    colors[v] = reg
    for u in neighbors[v]:
        if u in colors:
            continue
        banned = sum(1 << r for r in range(max(0, reg-width[u]+1),
                                           min(192, reg+width[v])))
        new = available[u] & ~banned
        if new != available[u]:
            available[u] = new
            push(u)

out = dict(accepted_merges=accepted, rejected_interference=rejected_interference,
           rejected_window=rejected_window, skipped_constant_edges=skipped_constants,
           groups=len(groups), nontrivial_groups=sum(len(g)>1 for g in groups.values()),
           largest_group=max(map(len, groups.values())), colored=len(colors),
           fits_96_gprs=failed is None, failed_group=failed,
           caveat='Optimistic SSA model: destination windows and widths only. '
                  'No instruction-local source windows, tuple split/collect '
                  'ties, scheduling, or post-allocation reconciliation costs.')
if failed is None:
    for v in groups:
        assert allowed[v] & (1 << colors[v])
        for u in neighbors[v]:
            assert colors[v] + width[v] <= colors[u] or colors[u] + width[u] <= colors[v]
    modeled = []
    phis = collections.defaultdict(list)
    for v, d in defs.items():
        if d['op'] == 'phi':
            phis[d['block']].append((v, d['phi_src']))
    for block, instructions in phis.items():
        for pi, pred in enumerate(m['blocks'][str(block)]['pred']):
            copies = {}
            moves = 0
            for dst, sources in instructions:
                src = sources[pi]
                if src is None:
                    continue
                dr, sr = colors[root(dst)], colors[root(src)]
                if dr != sr:
                    moves += 1
                    assert dr not in copies
                    copies[dr] = sr
            seen = set()
            swaps = 0
            for start in copies:
                trail = []
                x = start
                while x in copies and x not in trail and x not in seen:
                    trail.append(x)
                    x = copies[x]
                if x in trail:
                    swaps += len(trail[trail.index(x):])-1
                seen.update(trail)
            modeled.append(dict(pred=pred, succ=block, nonidentity_copies=moves, swaps=swaps))
    mixed = json.loads((a.audit / 'cycles.json').read_text())
    edges = {(c['pred'], c['succ']) for c in mixed if not c['mem'] and
             'original' in c['origins'] and 'spill-repair' in c['origins']}
    out['modeled_phi_swaps'] = sum(c['swaps'] for c in modeled)
    out['modeled_swaps_on_mixed_cycle_edges'] = sum(c['swaps'] for c in modeled
                                                  if (c['pred'], c['succ']) in edges)
    out['edge_costs'] = modeled
out['groups_members'] = groups
out['group_colors'] = colors
a.output.write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k: v for k, v in out.items() if k not in
                 ('edge_costs', 'groups_members', 'group_colors')}, indent=2))
