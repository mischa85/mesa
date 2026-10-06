#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stream every CTS chunk into a deduplicated corpus, retaining named aliases."""
import argparse,collections,gzip,hashlib,json,resource,shutil,subprocess,time
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
from prepare import reflect,STAGES
p=argparse.ArgumentParser();p.add_argument('--extractor',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--case',default='dEQP-VK.*');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);out=a.output.resolve();raw=out/'raw';raw.mkdir();(out/'spv').mkdir();(out/'meta').mkdir();seen={};counts=collections.Counter();pending={};start=time.perf_counter();errors=[]
cmd=[str(a.extractor.resolve()),'--deqp-case',a.case,'--dst-path',str(raw),'--target-vulkan-version','1.3','--validate-spv','--shadercache','disable','--log-filename','/dev/null']
(out/'provenance.json').write_text(json.dumps(dict(command=cmd,extractor_sha256=hashlib.sha256(a.extractor.read_bytes()).hexdigest(),data_directory=str(a.data.resolve()),definition='all enumerated CTS initPrograms sources; validated SPIR-V; named duplicates retained',runtime_descriptor_count=256),indent=2)+'\n')
with gzip.open(out/'extract.log.gz','wt',compresslevel=3) as log,gzip.open(out/'aliases.jsonl.gz','wt',compresslevel=3) as aliases,(out/'manifest.jsonl').open('w') as manifest:
 proc=subprocess.Popen(cmd,cwd=a.data,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace')
 for line in proc.stdout:
  log.write(line)
  if line.startswith('CORPUS_PROGRAM '):
   _,chunk,sha,case,name=line.rstrip().split(' ',4);pending.setdefault(sha,[]).append((case,name));counts['program_instances']+=1
  elif line.startswith('CORPUS_INIT_SKIP '):counts['initialization_skips']+=1
  elif line.startswith('ERROR: '):counts['frontend_failures']+=1;errors.append(line.strip())
  elif line.startswith('CORPUS_CHUNK_DONE '):
   chunk=int(line.split()[-1]);directory=raw/('chunk-'+str(chunk));files=sorted(directory.glob('*.spv'));chunk_hashes=set()
   for f in files:
    data=f.read_bytes();sha1=hashlib.sha1(data).hexdigest();digest=hashlib.sha256(data).hexdigest();chunk_hashes.add(sha1)
    if sha1 not in pending:raise RuntimeError('binary has no named provenance: '+str(f))
    for case,name in pending[sha1]:aliases.write(json.dumps(dict(sha256=digest,testcase=case,program=name))+'\n')
    if digest in seen:counts['duplicate_binaries']+=1;continue
    seen[digest]=True;spv=out/'spv'/(digest+'.spv');spv.write_bytes(data);row=dict(source=pending[sha1][0][0]+'/'+pending[sha1][0][1],sha256=digest,sha1=sha1,bytes=len(data));counts['unique']+=1;counts['spirv_bytes']+=len(data)
    try:
     info=reflect(data);row.update(info);prepared=[];unsupported=[]
     for model,name in info['entries']:
      counts['execution_model_'+str(model)]+=1
      if model not in (0,4,5):unsupported.append((model,name));continue
      if any(s>=16 or c>65536 for s,b,t,c in info['bindings']) or info['push']>256:raise ValueError('layout exceeds runner limits')
      ident=digest+'-'+str(model)+'-'+hashlib.sha1(name.encode()).hexdigest()[:12];meta=out/'meta'/(ident+'.txt');meta.write_text(f'{spv} {STAGES[model]} {name} {info["push"]} {len(info["bindings"])}\n'+''.join('%d %d %d %d\n'%tuple(b) for b in info['bindings']));prepared.append(str(meta))
     row.update(status='prepared' if prepared else 'unsupported_stage',metadata=prepared,unsupported_entries=unsupported);counts['prepared_entries']+=len(prepared)
    except Exception as e:row.update(status='reflection_failure',error=str(e))
    counts[row['status']]+=1;manifest.write(json.dumps(row)+'\n')
   if set(pending)!=chunk_hashes:raise RuntimeError('named programs absent from completed chunk')
   pending.clear();manifest.flush();aliases.flush();log.flush();shutil.rmtree(directory);counts['chunks']+=1
   status=dict(counts,elapsed_s=time.perf_counter()-start,complete=False);(out/'progress.json').write_text(json.dumps(status,indent=2)+'\n')
   if counts['chunks']%10==0:print(json.dumps(status),flush=True)
 rc=proc.wait()
summary=dict(counts,elapsed_s=time.perf_counter()-start,process_exit=rc,complete=not pending and rc==0,errors=errors)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
raise SystemExit(rc)
