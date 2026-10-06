import os
import json,math
from pathlib import Path
p=Path(os.environ.get('CENSUS_OUTPUT',Path(__file__).resolve().parent))
load=lambda n:[x for l in (p/n).open() if (x:=json.loads(l))['kind']=='APPLE9']
a=load('loop-off.jsonl');results={}
for mode in ['on','restricted']:
 b=load('loop-'+mode+'.jsonl');rows=[]
 for budget in [32,48,64,72,80,88,92,96]:
  for scope in ['loop','shader']:
   chosen=[];selected=0
   for x,y in zip(a,b):
    affected=[(h,l) for h,l in y['loops'].items() if l['hoisted_words']]
    accept=bool(affected) and (all(math.ceil(x['loops'][h]['pre_spill_half']/2)+l['hoisted_words']<=budget for h,l in affected) if scope=='loop' else x['pressure']['pre_spill']+sum(l['hoisted_words'] for h,l in affected)<=budget)
    selected+=accept;chosen.append(y if accept else x)
   rows.append(dict(budget=budget,scope=scope,selected=selected,instructions_saved=sum(x['weighted']['instructions']-y['weighted']['instructions'] for x,y in zip(a,chosen)),new_at96=sum(x['metrics']['gprs']<96 and y['metrics']['gprs']>=96 for x,y in zip(a,chosen)),gpr_delta=sum(y['metrics']['gprs']-x['metrics']['gprs'] for x,y in zip(a,chosen)),weighted_spill_delta=sum(sum(y['weighted'].get(k,0)-x['weighted'].get(k,0) for k in ['saves','fills']) for x,y in zip(a,chosen)),instruction_regressions=sum(y['weighted']['instructions']>x['weighted']['instructions'] for x,y in zip(a,chosen))))
 results[mode]=rows
(p/'budget-sweep.json').write_text(json.dumps(results,indent=2)+'\n')
for m,rs in results.items():
 print(m)
 for r in rs:
  if r['scope']=='loop':print(r)
