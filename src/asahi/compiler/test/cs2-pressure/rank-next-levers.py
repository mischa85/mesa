#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse,collections,csv,hashlib,json,re
from pathlib import Path
p=argparse.ArgumentParser(description='Rank remaining at-cap spill work from the selected compiler census')
p.add_argument('--census',type=Path,required=True)
p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent)
a=p.parse_args()
here=Path(__file__).resolve().parent
dest=a.output_dir;dest.mkdir(parents=True,exist_ok=True)
source=a.census
rows=[json.loads(l) for l in source.open()];rows=[r for r in rows if r['kind']=='APPLE9' and r['metrics']['gprs']==96]
h=(here.parent.parent/'agx_apple9_ir.h').read_text().split('enum agx_apple9_vir_opcode {')[1].split('};')[0]
ops=re.findall(r'AGX_APPLE9_VIR_(\w+)\s*,',h)
kindnames=['coupling','arithmetic','constant','uniform','texture','memory','phi','loop_phi','sysval']
bykind=collections.defaultdict(collections.Counter); byop=collections.defaultdict(collections.Counter);rank=[]
budgets={int(r['row']):r for r in csv.DictReader((here/'uniform-at-cap.csv').open())}
for r in rows:
 w=0
 for i in r['items']:
  t='save' if i['save'] else 'fill';weight=8**min(i['depth'],6);w+=weight
  for counter in [bykind[kindnames[i['kind']]],byop[ops[i['op']] if i['kind'] in (1,3,4,5,8) else kindnames[i['kind']]]]:
   counter[t]+=1;counter['weighted_'+t]+=weight
 rank.append(dict(row=r['row'],stage=r['metrics']['stage'],pipeline_hash=r['pipeline'].get('hash'),pipeline_index=r['pipeline'].get('index'),weighted_spills=w,saves=r['metrics']['saves'],fills=r['metrics']['fills'],scratch=r['metrics']['scratch'],uniform_binding=budgets[r['row']]['binding']))
rank.sort(key=lambda x:(-x['weighted_spills'],x['row']))
result=dict(compiler='1f4c8abe909',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),weight='8 ** min(loop_depth, 6)',programs=len(rows),with_scratch=sum(r['scratch']>0 for r in rank),without_scratch=sum(r['scratch']==0 for r in rank),by_stage=dict(collections.Counter(r['stage'] for r in rank)),uniform_binding=dict(collections.Counter(r['uniform_binding'] for r in rank)),by_kind=bykind,by_producer=byop,top_n_weighted={n:sum(r['weighted_spills'] for r in rank[:n]) for n in [1,5,10,20,50,100,320]},note='Capture multiplicity retained; no execution-frequency weighting. Producer labels follow aliases and are opportunity ceilings, not direct frame-fold eligibility.')
(dest/'next-levers-census.json').write_text(json.dumps(result,indent=2)+'\n')
with (dest/'next-levers-at-cap.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rank[0]);w.writeheader();w.writerows(rank)
print(json.dumps(result,indent=2))
