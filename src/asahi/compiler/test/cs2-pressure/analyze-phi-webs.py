#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline phi-web census and conservative interference/coalescing opportunity.

This does not allocate registers or predict a compiled instruction count.
"""
import argparse
import collections
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('log', type=Path)
p.add_argument('audit', type=Path)
p.add_argument('--id', type=int, default=10)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
blocks = {}
active = False

def operand(text):
    m = re.fullmatch(r'(m?)[*]?(\d+)(?:[hd])?(?:\.(?:abs|neg))*', text.strip())
    return (int(m[2]), bool(m[1])) if m else None

def bits(values):
    out = 0
    for v in values:
        out |= 1 << v
    return out

def members(mask):
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low

for line in a.log.open():
    if line == f'RA_AUDIT_POSTSPILL_BEGIN id={a.id}\n':
        active = True
        continue
    if line == f'RA_AUDIT_POSTSPILL_END id={a.id}\n':
        active = False
    if not active:
        continue
    m = re.match(r'block(\d+) \{', line)
    if m:
        bid = int(m[1])
        blocks[bid] = dict(ins=[], pred=[], succ=[], live_in=0, live_out=0)
    elif line.startswith('}'):
        parts = line.split(' from')
        blocks[bid]['succ'] = [int(x) for x in re.findall(r'block(\d+)', parts[0])]
        if len(parts) > 1:
            blocks[bid]['pred'] = [int(x) for x in re.findall(r'block(\d+)', parts[1])]
    elif line.strip():
        parts = line.strip().split(' = ')
        dst = [operand(x) for x in parts[0].split(',')] if len(parts) == 2 else []
        rhs = parts[-1].split(maxsplit=1)
        src = [operand(x) for x in rhs[1].split(',')] if len(rhs) == 2 else []
        ins = dict(op=rhs[0], dst=[x[0] for x in dst if x and not x[1]],
                   src=[x[0] for x in src if x and not x[1]],
                   phi_src=[x[0] if x and not x[1] else None for x in src],
                   line=line.strip(), block=bid)
        ins['dmask'] = bits(ins['dst'])
        ins['smask'] = bits(ins['src'])
        blocks[bid]['ins'].append(ins)

defs = {v: ins for b in blocks.values() for ins in b['ins'] for v in ins['dst']}
assert all(v in defs for b in blocks.values() for ins in b['ins'] for v in ins['src'])
changed = True
while changed:
    changed = False
    for bid, b in reversed(list(blocks.items())):
        live = b['live_out']
        for ins in reversed(b['ins']):
            if ins['op'] != 'phi':
                live = (live & ~ins['dmask']) | ins['smask']
        b['live_in'] = live
        phis = [ins for ins in b['ins'] if ins['op'] == 'phi' and ins['dst']]
        for pi, pred in enumerate(b['pred']):
            edge = live
            for ins in phis:
                edge &= ~ins['dmask']
            for ins in phis:
                v = ins['phi_src'][pi]
                if v is not None:
                    edge |= 1 << v
            old = blocks[pred]['live_out']
            blocks[pred]['live_out'] |= edge
            changed |= old != blocks[pred]['live_out']

adj = {v: 0 for v in defs}
def clique(mask):
    for v in members(mask):
        adj[v] |= mask & ~(1 << v)

def link_to(v, mask):
    mask &= ~(1 << v)
    adj[v] |= mask
    for u in members(mask):
        adj[u] |= 1 << v

peak_sets = []
for bid, b in blocks.items():
    live = b['live_out']
    clique(live)
    peak_sets.append((bid, live))
    for ins in reversed(b['ins']):
        if ins['op'] == 'phi':
            continue
        for v in ins['dst']:
            link_to(v, live | ins['dmask'])
        live = (live & ~ins['dmask']) | ins['smask']
        peak_sets.append((bid, live))
    # Phi writes are simultaneous, including dead destinations.
    for ins in b['ins']:
        if ins['op'] == 'phi':
            live |= ins['dmask']
    clique(live)
    peak_sets.append((bid, live))

class Union:
    def __init__(self):
        self.parent = {v: v for v in defs}
        self.rank = collections.Counter()
    def root(self, v):
        if self.parent[v] != v:
            self.parent[v] = self.root(self.parent[v])
        return self.parent[v]
    def join(self, x, y):
        x, y = self.root(x), self.root(y)
        if x == y:
            return x
        if self.rank[x] < self.rank[y]:
            x, y = y, x
        self.parent[y] = x
        if self.rank[x] == self.rank[y]:
            self.rank[x] += 1
        return x
    def groups(self):
        out = collections.defaultdict(list)
        for v in defs:
            out[self.root(v)].append(v)
        return dict(out)

edges = []
all_webs, no_constants = Union(), Union()
for b in blocks.values():
    for ins in b['ins']:
        if ins['op'] != 'phi' or not ins['dst']:
            continue
        v, = ins['dst']
        for u in ins['src']:
            edges.append((v, u, ins['block']))
            all_webs.join(v, u)
            if defs[u]['op'] != 'mov_imm':
                no_constants.join(v, u)

def group_report(union):
    out = []
    for root, group in union.groups().items():
        if len(group) == 1:
            continue
        mask = bits(group)
        conflicts = sum((adj[v] & mask).bit_count() for v in group) // 2
        peak, block = max(((live & mask).bit_count(), bid) for bid, live in peak_sets)
        out.append(dict(root=root, members=len(group), interference_pairs=conflicts,
                        peak_simultaneous_members=peak, peak_block=block))
    return sorted(out, key=lambda g: g['members'], reverse=True)

events = json.loads((a.audit / 'events.json').read_text())
phis = {int(e['phi']): e for e in events if e['kind'] == 'RA_AUDIT_PHI'}
cycles = json.loads((a.audit / 'cycles.json').read_text())
mixed = [c for c in cycles if not c['mem'] and
         'original' in c['origins'] and 'spill-repair' in c['origins']]
by_join = collections.defaultdict(collections.Counter)
web_uses = collections.Counter()
cycle_rows = []
for c in mixed:
    kind = 'loop-header' if phis[c['phis'][0]]['loop'] == '1' else 'non-header-join'
    by_join[kind]['cycles'] += 1
    by_join[kind]['swaps'] += c['swaps']
    origins = collections.Counter(phis[p]['origin'] for p in c['phis'])
    by_join[kind].update({f'{k}_operands': v for k, v in origins.items()})
    rows = []
    for p in c['phis']:
        phi = phis[p]
        v = int(phi['dst'])
        root = all_webs.root(v)
        web_uses[root] += 1
        rows.append(dict(phi=p, ssa=v, origin=phi['origin'], web=root,
                         without_constant_web=no_constants.root(v)))
    cycle_rows.append(dict(pred=c['pred'], succ=c['succ'], swaps=c['swaps'],
                           join=kind, operands=rows))

out = dict(id=a.id, gpr_definitions=len(defs),
           interference_edges=sum(m.bit_count() for m in adj.values()) // 2,
           phi_edges=len(edges), webs=group_report(all_webs),
           webs_without_constant_source_edges=group_report(no_constants),
           mixed_cycles_by_join={k: dict(v) for k, v in by_join.items()},
           mixed_cycle_web_operands=dict(web_uses), mixed_cycles=cycle_rows,
           note='Conservative SSA liveness interference, including dead phi writes. '
                'Does not model physical operand windows or allocate registers.')
a.output.mkdir(parents=True, exist_ok=True)
(a.output / 'webs.json').write_text(json.dumps(out, indent=2) + '\n')
# Keep exact group membership and graph for independent follow-up models.
(a.output / 'model.json').write_text(json.dumps(dict(
    definitions=defs, interference={v: list(members(m)) for v, m in adj.items()},
    phi_edges=edges, blocks={bid: dict(pred=b["pred"], succ=b["succ"]) for bid, b in blocks.items()},
    web_members=all_webs.groups(),
    no_constant_web_members=no_constants.groups()), indent=2) + '\n')
print(json.dumps({k: out[k] for k in ('gpr_definitions', 'interference_edges',
                                     'phi_edges', 'mixed_cycles_by_join')}, indent=2))
print('largest original webs:', out['webs'][:3])
print('largest webs without constant edges:', out['webs_without_constant_source_edges'][:6])
