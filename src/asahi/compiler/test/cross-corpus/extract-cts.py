#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stream CTS SPIR-V and provenance directly into a content-addressed pack."""
import argparse,collections,hashlib,json,os,re,resource,subprocess,time
from pathlib import Path
from packed import Pack
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
p=argparse.ArgumentParser();p.add_argument('--extractor',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--pack',type=Path,required=True);p.add_argument('--population',default='cts-full');p.add_argument('--summary',type=Path,required=True);p.add_argument('--resume-chunk',type=int,default=0);p.add_argument('--case',default='dEQP-VK.*');a=p.parse_args();pack=Pack(a.pack,True);pack.db.execute('PRAGMA journal_mode=WAL');counts=collections.Counter();start=time.perf_counter();enumeration=None;binary={};aliases=[];logs=[];last=a.resume_chunk-1
cmd=[str(a.extractor.resolve()),'--deqp-case',a.case,'--dst-path','/dev/null','--target-vulkan-version','1.3','--validate-spv','--shadercache','disable','--log-filename','/dev/null'];env=dict(os.environ,CORPUS_RESUME_CHUNK=str(a.resume_chunk))
pack.add_file(f'extraction/provenance-{a.resume_chunk}.json',json.dumps(dict(command=cmd,extractor_sha256=hashlib.sha256(a.extractor.read_bytes()).hexdigest(),resume_chunk=a.resume_chunk,definition='validated initPrograms sources, CPU only')).encode());pack.db.commit()
proc=subprocess.Popen(cmd,cwd=a.data,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace')
for line in proc.stdout:
 if line.startswith('CORPUS_BINARY '):
  _,sha1,hexdata=line.rstrip().split(' ',2);data=bytes.fromhex(hexdata);assert hashlib.sha1(data).hexdigest()==sha1;sha=pack.add_blob(data);binary[sha1]=sha
 elif line.startswith('CORPUS_PROGRAM '):
  _,chunk,sha1,case,name=line.rstrip().split(' ',4);sha=binary[sha1];counts['program_instances']+=1;aliases.append(json.dumps(dict(sha256=sha,testcase=case,program=name)))
  if not pack.db.execute('SELECT 1 FROM modules WHERE sha=?',(sha,)).fetchone():
   row=pack.ingest(pack.blob(sha),case+'/'+name,a.population);counts['new_unique']+=1;counts[row['status']]+=1;counts['prepared_entries']+=len(row['metadata'])
 elif line.startswith('CORPUS_CHUNK_DONE '):
  last=int(line.split()[-1]);pack.add_file(f'extraction/aliases-{last}.jsonl',('\n'.join(aliases)+'\n').encode());pack.add_file(f'extraction/log-{last}.txt',''.join(logs).encode());aliases.clear();logs.clear();binary.clear();counts['chunks']+=1
  status=dict(counts,next_chunk=last+1,elapsed_s=time.perf_counter()-start,complete=False);pack.add_file('extraction/progress.json',json.dumps(status).encode());pack.db.commit();a.summary.write_text(json.dumps(status,indent=2)+'\n')
  if counts['chunks']%10==0:print(json.dumps(status),flush=True)
 else:
  logs.append(line)
  if line.startswith('CORPUS_INIT_SKIP '):counts['initialization_skips']+=1
  if line.startswith('ERROR: '):counts['frontend_failures']+=1
  if m:=re.match(r'DONE: (\d+) passed, (\d+) failed, (\d+) not supported',line):enumeration=dict(zip(['passed','failed','not_supported'],map(int,m.groups())))
rc=proc.wait();pack.add_file(f'extraction/tail-{a.resume_chunk}.txt',''.join(logs).encode());pack.db.commit();summary=dict(counts,next_chunk=last+1,elapsed_s=time.perf_counter()-start,process_exit=rc,complete=not binary and enumeration is not None,enumeration=enumeration,all_frontends_passed=rc==0);a.summary.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True);raise SystemExit(rc)
