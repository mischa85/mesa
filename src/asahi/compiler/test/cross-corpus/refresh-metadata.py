#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create a fresh replay view of retained SPIR-V with current stage coverage."""
import argparse,collections,hashlib,json,os
from pathlib import Path
from prepare import reflect,STAGES
p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);out=a.output.resolve();(out/'meta').mkdir();(out/'spv').symlink_to((a.corpus/'spv').resolve());counts=collections.Counter()
with (out/'manifest.jsonl').open('w') as dest:
 for line in (a.corpus/'manifest.jsonl').open():
  r=json.loads(line)
  if r.get('status')=='duplicate':continue
  digest=r['sha256'];spv=out/'spv'/(digest+'.spv');row={k:r[k] for k in ['sha256','source','sha1','bytes'] if k in r};counts['unique']+=1
  try:
   data=spv.read_bytes();assert hashlib.sha256(data).hexdigest()==digest;info=reflect(data);row.update(info);row.update(metadata=[],unsupported_entries=[])
   if any(s>=8 for s,b,t,c in info['bindings']) or info['push']>256:row.update(status='unsupported_device_layout',error='Apple9 advertises 8 sets and 256 push-constant bytes')
   elif any(c>65536 for s,b,t,c in info['bindings']):row.update(status='harness_limit',error='descriptor count exceeds replay bound')
   else:
    for model,name in info['entries']:
     counts['execution_model_'+str(model)]+=1
     if model not in (0,1,2,3,4,5):row['unsupported_entries'].append((model,name));continue
     ident=digest+'-'+str(model)+'-'+hashlib.sha1(name.encode()).hexdigest()[:12];meta=out/'meta'/(ident+'.txt');meta.write_text(f'{spv} {STAGES[model]} {name} {info["push"]} {len(info["bindings"])}\n'+''.join('%d %d %d %d\n'%tuple(b) for b in info['bindings']));row['metadata'].append(str(meta));counts['prepared_entries']+=1
    row['status']='prepared' if row['metadata'] else 'unsupported_device_stage'
  except Exception as e:row.update(status='reflection_failure',error=str(e))
  counts[row['status']]+=1;dest.write(json.dumps(row)+'\n')
  if a.limit and counts['prepared_entries']>=a.limit:break
(out/'summary.json').write_text(json.dumps(counts,indent=2)+'\n');print(json.dumps(counts))
