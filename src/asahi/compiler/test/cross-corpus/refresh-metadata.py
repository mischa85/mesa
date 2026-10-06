#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Refresh a replay population inside a pack, without loose modules or metadata."""
import argparse,collections,hashlib,json
from pathlib import Path
from packed import Pack
p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,required=True);p.add_argument('--source-population',required=True);p.add_argument('--population',required=True);p.add_argument('--summary',type=Path,required=True);a=p.parse_args();pack=Pack(a.pack,True);counts=collections.Counter()
manifest=pack.file(a.source_population+'/manifest.jsonl').decode()
for line in manifest.splitlines():
 r=json.loads(line)
 if r.get('status')=='duplicate':continue
 previous=pack.db.execute('SELECT info FROM modules WHERE sha=?',(r['sha256'],)).fetchone()
 row=json.loads(previous[0]) if previous else pack.ingest(pack.blob(r['sha256']),r['source'],a.population);counts['unique']+=1;counts[row['status']]+=1;counts['prepared_entries']+=len(row['metadata'])
 if previous and row['status']=='prepared':
  for model,name in row['entries']:
   if model not in range(6):continue
   key=r['sha256']+'-'+str(model)+'-'+hashlib.sha1(name.encode()).hexdigest()[:12]
   pack.db.execute('INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?,?,?)',(a.population,key,r['sha256'],model,name,row['push'],json.dumps(row['bindings'])))
 for model,name in row.get('entries',[]):counts['execution_model_'+str(model)]+=1
 if counts['unique']%1000==0:pack.db.commit()
pack.db.commit();a.summary.write_text(json.dumps(counts,indent=2)+'\n');print(json.dumps(counts))
