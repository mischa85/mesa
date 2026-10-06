#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare matched shader identities and expose every static-code regression."""
import argparse,collections,json,sqlite3,statistics,zlib
from pathlib import Path
from packed import Pack,results
p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path);p.add_argument('--pack',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
load=lambda p:{r['key']:r for r in results(p)}
x,y=load(a.baseline),load(a.candidate);assert x.keys()==y.keys();names={}
pack=Pack(a.pack);names={sha:source for sha,source in pack.db.execute('SELECT sha,source FROM modules')}
metrics=['instructions','copies','swaps','saves','fills','gprs','scratch'];rows=[];totals={};stages={};outcomes=collections.Counter()
def values(r,kind):
 ps=[p for p in r['programs'] if p['kind']==kind and (r['stage'] in (1,2,3) or p['stage']==r['stage']) and not p['stub']]
 return {k:sum(p[k] for p in ps) for k in metrics}|{'programs':len(ps)}
for key in x:
 b,c=x[key],y[key];outcomes[b['status']+' -> '+c['status']]+=1
 if b['status']!='pass' or c['status']!='pass':continue
 row=dict(key=key,source=names.get(key.split('-')[0]),stage=b['stage'])
 for label,kind in [('main','APPLE9'),('preamble','APPLE9_PREAMBLE')]:
  bv,cv=values(b,kind),values(c,kind)
  for metric in metrics+['programs']:
   name=label+'_'+metric;row[name+'_before']=bv[metric];row[name+'_after']=cv[metric];row[name+'_delta']=cv[metric]-bv[metric]
   for table in [totals,stages.setdefault(str(b['stage']),{})]:
    t=table.setdefault(name,dict(before=0,after=0,improved=0,regressed=0));t['before']+=bv[metric];t['after']+=cv[metric];t['improved']+=cv[metric]<bv[metric];t['regressed']+=cv[metric]>bv[metric]
 for label,r in [('before',b),('after',c)]:
  row['backend_cpu_ns_'+label]=sum(t['cpu_ns'] for t in r['timings'] if (r['stage'] in (1,2,3) or t['stage']==r['stage']))
  row['create_cpu_ns_'+label]=r.get('create',{}).get('cpu_ns',0)
 rows.append(row)
for table in [totals,*stages.values()]:
 for t in table.values():t['delta']=t['after']-t['before'];t['percent']=100*t['delta']/t['before'] if t['before'] else None
regress=[r for r in rows if any(r['main_'+k+'_delta']>0 for k in metrics)]
with sqlite3.connect(a.output/'comparison.sqlite3') as db:
 db.execute('CREATE TABLE shaders(key TEXT PRIMARY KEY,regression INTEGER,data BLOB NOT NULL) WITHOUT ROWID')
 db.executemany('INSERT INTO shaders VALUES(?,?,?)',((r['key'],int(any(r['main_'+k+'_delta']>0 for k in metrics)),zlib.compress(json.dumps(r).encode(),1)) for r in rows))
summary=dict(input_count=len(x),matched_pass=len(rows),outcomes=dict(outcomes),main_and_preamble_totals=totals,stages=stages,timing={k:{v:sum(r[k+'_'+v] for r in rows) for v in ['before','after']} for k in ['backend_cpu_ns','create_cpu_ns']},regressors=len(regress),new_failures=[k for k in x if x[k]['status']=='pass' and y[k]['status']!='pass'],baseline_only_failures=[k for k in x if x[k]['status']!='pass' and y[k]['status']=='pass'])
(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['stages','main_and_preamble_totals']}))
