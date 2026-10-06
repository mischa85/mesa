import os
from pathlib import Path
import json,collections,csv,math
p=Path(os.environ.get('CENSUS_OUTPUT',Path(__file__).resolve().parent))

def load(name):return [x for l in (p/(name+'.jsonl')).open() if (x:=json.loads(l))['kind']=='APPLE9']
def sums(rows):
 out={}
 for stage in ['all','vertex','fragment','compute']:
  a=[r for r in rows if stage=='all' or r['metrics']['stage']==stage];m=collections.Counter();w=collections.Counter()
  for r in a:m.update({k:v for k,v in r['metrics'].items() if isinstance(v,int)});w.update(r['weighted'])
  out[stage]=dict(programs=len(a),static=dict(m),weighted=dict(w))
 return out

def traffic(r):return r['weighted'].get('saves',0)+r['weighted'].get('fills',0)
def strict(a,b):return b['pressure']['pre_spill']<=a['pressure']['pre_spill'] and b['metrics']['gprs']<=a['metrics']['gprs'] and b['metrics']['saves']+b['metrics']['fills']<=a['metrics']['saves']+a['metrics']['fills'] and traffic(b)<=traffic(a) and b['weighted']['instructions']<a['weighted']['instructions']
def budget(a,b):
 affected=[(h,l) for h,l in b['loops'].items() if l['hoisted_words']]
 return bool(affected) and all(math.ceil(a['loops'][h]['pre_spill_half']/2)+l['hoisted_words']<=96 for h,l in affected)
a=load('loop-off');assert len(a)==10161;report={'off':sums(a)}
for variant in ['on','restricted']:
 f=p/('loop-'+variant+'.jsonl')
 if not f.exists():continue
 b=load('loop-'+variant)
 if len(b)!=len(a):continue
 assert all(x['row']==y['row'] and x['pipeline']==y['pipeline'] and x['loops'].keys()==y['loops'].keys() for x,y in zip(a,b))
 report[variant]=dict(totals=sums(b),weighted_spill_regressions=sum(traffic(y)>traffic(x) for x,y in zip(a,b)),weighted_instruction_regressions=sum(y['weighted']['instructions']>x['weighted']['instructions'] for x,y in zip(a,b)),pre_spill_increases=sum(y['pressure']['pre_spill']>x['pressure']['pre_spill'] for x,y in zip(a,b)),gpr_increases=sum(y['metrics']['gprs']>x['metrics']['gprs'] for x,y in zip(a,b)))
 for rule,fn in [('strict_tryboth',strict),('budget_proxy',budget),('safe_oracle',lambda x,y:traffic(y)<=traffic(x) and y['weighted']['instructions']<x['weighted']['instructions'])]:
  selection=[y if fn(x,y) else x for x,y in zip(a,b)]
  report[variant][rule]=dict(selected=sum(fn(x,y) for x,y in zip(a,b)),totals=sums(selection),weighted_spill_regressions=sum(traffic(y)>traffic(x) for x,y in zip(a,selection)))
 hoists=collections.Counter();loops=[]
 for x,y in zip(a,b):
  for h,ly in y['loops'].items():
   lx=x['loops'][h];hoists.update(ly['hoisted'])
   row=dict(row=x['row'],stage=x['metrics']['stage'],pipeline_index=x['pipeline'].get('index'),pipeline_hash=x['pipeline'].get('hash'),header=h,depth=lx['depth'],before_peak_half=lx['pre_spill_half'],after_peak_half=ly['pre_spill_half'],before_peak_gprs=math.ceil(lx['pre_spill_half']/2),after_peak_gprs=math.ceil(ly['pre_spill_half']/2),before_shader_gprs=x['metrics']['gprs'],after_shader_gprs=y['metrics']['gprs'],hoisted_words=ly['hoisted_words'],hoisted=json.dumps(ly['hoisted'],sort_keys=True))
   row.update(hoisted_transcendental=sum(ly['hoisted'].get(k,0) for k in ['flog2','fexp2','frcp','frsq','fsqrt','fsin_factor_agx']),hoisted_fmul_fadd=sum(ly['hoisted'].get(k,0) for k in ['fmul','fadd']),hoisted_iadd=ly['hoisted'].get('iadd',0),hoisted_fneg=ly['hoisted'].get('fneg',0))
   for side,l in [('before',lx),('after',ly)]:
    for kind in ['static','weighted']:
     for k in ['instructions','saves','fills']:row[f'{side}_{kind}_{k}']=l[kind].get(k,0)
   loops.append(row)
 report[variant]['hoisted_loop_memberships']=dict(hoists)
 report[variant]['loop_count']=len(loops)
 with (p/(variant+'-per-loop.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(loops[0]));w.writeheader();w.writerows(loops)
(p/'loops-summary.json').write_text(json.dumps(report,indent=2)+'\n')
for variant,r in report.items():
 if variant=='off':print('off',r['all']);continue
 print(variant,{k:v for k,v in r.items() if k not in ['totals','strict_tryboth','budget_proxy','hoisted_loop_memberships']});print('all',r['totals']['all']);print('hoists',r['hoisted_loop_memberships'])
 for rule in ['strict_tryboth','budget_proxy']:print(rule,r[rule]['selected'],r[rule]['totals']['all']['weighted'],'spill_regressions',r[rule]['weighted_spill_regressions'])
