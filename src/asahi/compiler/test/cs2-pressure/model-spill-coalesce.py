#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline scalar spill-home interference model; no shader execution."""
import argparse
import collections
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('log', type=Path)
p.add_argument('homes', type=Path)
p.add_argument('--id', type=int, default=10)
p.add_argument('--slots', type=int, default=72)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
home = {int(k): v[0][0] for k, v in json.loads(a.homes.read_text()).items() if v[0][1]}
blocks = {}
active = False
for line in a.log.open():
    if line == f'RA_AUDIT_POSTSPILL_BEGIN id={a.id}\n':
        active = True
    if line == f'RA_AUDIT_POSTSPILL_END id={a.id}\n':
        active = False
    if not active:
        continue
    m = re.match(r'block(\d+) \{', line)
    if m:
        block = int(m[1])
        blocks[block] = dict(ins=[], pred=[], succ=[], live_in=set(), live_out=set())
    elif line.startswith('}'):
        parts = line.split(' from')
        blocks[block]['succ'] = list(map(int, re.findall(r'block(\d+)', parts[0])))
        if len(parts) > 1:
            blocks[block]['pred'] = list(map(int, re.findall(r'block(\d+)', parts[1])))
    elif line.strip() and not line.startswith('RA_AUDIT'):
        mem = list(map(int, re.findall(r'\bm(\d+)\b', line)))
        d = re.match(r'\s*m(\d+) =', line)
        blocks[block]['ins'].append(dict(dst=int(d[1]) if d else None,
                                         src=mem[1:] if d else mem,
                                         phi=' = phi ' in line))

progress = True
while progress:
    progress = False
    for b, info in reversed(list(blocks.items())):
        live = set(info['live_out'])
        for ins in reversed(info['ins']):
            if not ins['phi']:
                live.discard(ins['dst'])
                live.update(ins['src'])
        info['live_in'] = live
        for pi, pred in enumerate(info['pred']):
            edge = set(live)
            for ins in info['ins']:
                if ins['phi']:
                    edge.discard(ins['dst'])
            for ins in info['ins']:
                if ins['phi'] and ins['dst'] is not None:
                    edge.add(ins['src'][pi])
            old = len(blocks[pred]['live_out'])
            blocks[pred]['live_out'].update(edge)
            progress |= old != len(blocks[pred]['live_out'])

adj = {v: set() for v in home}
def link(x, y):
    if x != y:
        adj[x].add(y)
        adj[y].add(x)

def clique(live):
    for x in live:
        for y in live:
            link(x, y)

for info in blocks.values():
    live = set(info['live_out'])
    clique(live)
    for ins in reversed(info['ins']):
        if ins['phi']:
            continue
        if ins['dst'] is not None:
            for v in live:
                link(ins['dst'], v)
            live.discard(ins['dst'])
        live.update(ins['src'])
    clique(live)

conflicts = [(x, y) for x in adj for y in adj[x] if x < y and home[x] == home[y]]
assert not conflicts, conflicts[:10]
web = {h: set() for h in home.values()}
for x in adj:
    web[home[x]].update(home[y] for y in adj[x] if home[x] != home[y])
colors = {}
while len(colors) < len(web):
    x = max((x for x in web if x not in colors),
            key=lambda x: (len({colors[y] for y in web[x] if y in colors}), len(web[x]), -x))
    used = {colors[y] for y in web[x] if y in colors}
    colors[x] = next(c for c in range(len(web)) if c not in used)
needed = max(colors.values()) + 1
out = dict(memory_ssa=len(home), homes=len(web), interference_edges=sum(map(len, adj.values()))//2,
           home_edges=sum(map(len, web.values()))//2, same_home_interferences=len(conflicts),
           dsatur_slots=needed, existing_slots=a.slots, fits=needed <= a.slots,
           colors=colors, graph={h: sorted(ns) for h, ns in web.items()})
a.output.write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('colors','graph')}, indent=2))
