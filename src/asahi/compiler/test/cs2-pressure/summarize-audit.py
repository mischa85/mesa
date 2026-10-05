#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse,collections,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('log',type=Path);p.add_argument('--id',type=int,default=8);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
events=[]
blocks={}; block=None; in_postspill=False
for line in a.log.open():
 if line.startswith(f'RA_AUDIT_POSTSPILL_BEGIN id={a.id}\n'):in_postspill=True
 if line.startswith(f'RA_AUDIT_POSTSPILL_END id={a.id}\n'):in_postspill=False
 if in_postspill:
  m=re.match(r'block(\d+) \{',line)
  if m:block=int(m[1]);blocks[block]=dict(lines=[],succ=[])
  elif block is not None and line.startswith('}'):
   successor_text=line.split(' from')[0]
   blocks[block]['succ']=[int(x) for x in re.findall(r'block(\d+)',successor_text)]
  elif block is not None:blocks[block]['lines'].append(line.strip())
 if line.startswith('RA_AUDIT_'):
  d=dict(re.findall(r'(\w+)=(\S+)',line))
  if d.get('id')==str(a.id):events.append(dict(kind=line.split()[0],**d))
phis={int(e['phi']):e for e in events if e['kind']=='RA_AUDIT_PHI'}
edges=collections.defaultdict(list)
for e in events:
 if e['kind']=='RA_AUDIT_EDGE':edges[(int(e['pred']),int(e['succ']))].append(e)
counts=collections.Counter();byorigin=collections.defaultdict(collections.Counter);cycles=[]
for key,es in edges.items():
 bydest={}
 for e in es:
  dst,src,mem,smem,width,typ=(int(e[k]) for k in ('dst','src','mem','srcmem','width','type'))
  counts['edge_phi_'+e['origin']]+=1
  if dst!=src or mem!=smem or typ!=4:
   byorigin[e['origin']]['memory_words' if mem else 'gpr_words']+=width
  if typ==4 and dst!=src and mem==smem:
   for c in range(width):bydest[(mem,dst+c*2)]=(mem,src+c*2,e['origin'],int(e['phi']))
 seen=set()
 for start in bydest:
  trail=[];v=start
  while v in bydest and v not in seen and v not in trail:
   trail.append(v);link=bydest[v];v=(link[0],link[1])
  if v in trail:
   cycle=trail[trail.index(v):];orig=sorted(set(bydest[x][2] for x in cycle))
   cycles.append(dict(pred=key[0],succ=key[1],mem=v[0],length=len(cycle),swaps=len(cycle)-1,origins=orig,registers=[x[1] for x in cycle],phis=[bydest[x][3] for x in cycle]))
  seen.update(trail)
results=[e for e in events if e['kind']=='RA_AUDIT_PCOPY_RESULT']
for e in results:
 for k in ('swaps','moves','saves','fills'):counts[e['where']+'_'+k]+=int(e[k])
cycle_counts=collections.defaultdict(collections.Counter)
for c in cycles:
 k=('MEM:' if c['mem'] else 'GPR:')+','.join(c['origins']);cycle_counts[k]['cycles']+=1;cycle_counts[k]['swaps']+=c['swaps']
preds=collections.defaultdict(set)
for b,info in blocks.items():
 for succ in info['succ']:preds[succ].add(b)
loops=collections.defaultdict(set)
for b,info in blocks.items():
 for header in info['succ']:
  if header>b:continue
  loop={header,b};todo=[b] if b!=header else []
  while todo:
   v=todo.pop()
   for pred in preds[v]:
    if pred not in loop:loop.add(pred);todo.append(pred)
  loops[header].update(loop)
depth={b:sum(b in ls for ls in loops.values()) for b in blocks}
bydepth=collections.defaultdict(collections.Counter)
for e in results:
 b=int(e['block'])
 for k in ('swaps','moves','saves','fills'):bydepth[depth.get(b,0)][k]+=int(e[k])
for c in cycles:c['depth']=depth.get(c['pred'],0)
loop_report={h:dict(blocks=sorted(bs),backedges=[b for b in bs if h in blocks[b]['succ']]) for h,bs in loops.items()}
summary=dict(id=a.id,by_loop_depth={k:dict(v) for k,v in bydepth.items()},loop_count=len(loops),phi_counts=dict(collections.Counter(e['origin']+(':mem' if int(e['mem']) else ':gpr') for e in phis.values())),counts=dict(counts),edge_mismatches={k:dict(v) for k,v in byorigin.items()},cycles={k:dict(v) for k,v in cycle_counts.items()})
a.output.mkdir(exist_ok=True,parents=True)
(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(a.output/'cycles.json').write_text(json.dumps(cycles,indent=2)+'\n')
(a.output/'cfg.json').write_text(json.dumps(dict(blocks=blocks,loops=loop_report,depth=depth),indent=2)+'\n')
(a.output/'events.json').write_text(json.dumps(events,indent=2)+'\n')
print(json.dumps(summary,indent=2))
