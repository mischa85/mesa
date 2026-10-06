import os
import json,math
from pathlib import Path
p=Path(os.environ.get('CENSUS_OUTPUT',Path(__file__).resolve().parent))
load=lambda n:[x for l in (p/n).open() if (x:=json.loads(l))['kind']=='APPLE9']
a=load('loop-off.jsonl');results={}
for mode in ['on','restricted']:
 b=load('loop-'+mode+'.jsonl');rows=[]
 for budget in [80,88,92,96]:
  for cutoff in [0,32,128,512,2048,8192]:
   chosen=[];selected=0
   for x,y in zip(a,b):
    affected=[(h,l) for h,l in y['loops'].items() if l['hoisted_words']]
    benefit=sum(sum(n for op,n in l['hoisted'].items() if not op.startswith('vec'))*(8**min(l['depth'],6)-8**min(l['depth']-1,6)) for h,l in affected)
    accept=bool(affected) and benefit>=cutoff and all(math.ceil(x['loops'][h]['pre_spill_half']/2)+l['hoisted_words']<=budget for h,l in affected)
    selected+=accept;chosen.append(y if accept else x)
   rows.append(dict(budget=budget,cutoff=cutoff,selected=selected,instructions_saved=sum(x['weighted']['instructions']-y['weighted']['instructions'] for x,y in zip(a,chosen)),new_at96=sum(x['metrics']['gprs']<96 and y['metrics']['gprs']>=96 for x,y in zip(a,chosen)),gpr_delta=sum(y['metrics']['gprs']-x['metrics']['gprs'] for x,y in zip(a,chosen)),weighted_spill_delta=sum(sum(y['weighted'].get(k,0)-x['weighted'].get(k,0) for k in ['saves','fills']) for x,y in zip(a,chosen)),instruction_regressions=sum(y['weighted']['instructions']>x['weighted']['instructions'] for x,y in zip(a,chosen))))
 results[mode]=rows
(p/'benefit-sweep.json').write_text(json.dumps(results,indent=2)+'\n')
for m,rs in results.items():
 print(m)
 for budget in [88,96]:print(max((r for r in rs if r['budget']==budget),key=lambda r:r['instructions_saved']))
