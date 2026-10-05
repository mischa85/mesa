#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Locate loop intervals and frame transfers in the authored pressure corpus."""
import argparse,collections,importlib.util,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--decoder',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.workspace
spec=importlib.util.spec_from_file_location('archive_decoder',a.decoder);decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
sys.path[:0]=[str(root/'tmp/hv-metal-regs-20261005'),str(root/'tmp/agx-re/tools/agx-isa')]
import agxparse,isadb
manifest=json.loads((root/'tmp/high-registers-20261005/operand-survey/summary.json').read_text())
report={}
for key,item in manifest.items():
 code=agxparse.extract_all_stages((root/item['archive']).read_bytes())[1][item['stage']]['_agc.main'];r=list(decoder.records(code,isadb))
 loops=[]
 for x in r:
  if x['name']=='jump':
   off=x['offset'];delta=int.from_bytes(bytes.fromhex(x['hex'])[3:9],'little',signed=True)
   if delta<0:loops.append((off+delta,off+x['length']))
 phases=collections.defaultdict(collections.Counter);touch=collections.defaultdict(list)
 for x in r:
  o=x['offset'];phase='inside' if any(lo<=o<hi for lo,hi in loops) else 'before' if loops and o<min(lo for lo,hi in loops) else 'after'
  if 'word' in x:
   kind='fill' if x['name']=='frame_fill_candidate' else 'iadd' if x['name']=='iadd_frame_candidate' else 'save'
   phases[phase][kind]+=1;touch[x['word']].append((o,phase,kind))
 stable=[]
 for w,ts in touch.items():
  for lo,hi in loops:
   before=[t for t in ts if t[0]<lo and t[2]!='fill']
   inside=[t for t in ts if lo<=t[0]<hi and t[2]!='fill']
   after=[t for t in ts if t[0]>=hi]
   if before and not inside and after and after[0][2]=='fill':stable.append(w)
 logic=[x for x in r if x['name']=='ilogic']
 report[key]=dict(instructions=len(r),loops=loops,transfers={k:dict(v) for k,v in phases.items()},unchanged_words_read_after_loop=sorted(set(stable)),logic_count=len(logic),move_like=dict(collections.Counter(x['name'] for x in r if 'move' in x['name'] or x['name']=='n3_mov')),control_flow=dict(collections.Counter(x['name'] for x in r if x['name'] in ('jump','jump_cond','if_push','else','pop_reconverge','loop_mask_update','mask_update_candidate'))))
a.output.write_text(json.dumps(report,indent=2)+'\n')
for key,r in report.items():print(key,'loops',r['loops'],'transfers',r['transfers'],'stable',len(r['unchanged_words_read_after_loop']),'logic',r['logic_count'],'moves',r['move_like'])
