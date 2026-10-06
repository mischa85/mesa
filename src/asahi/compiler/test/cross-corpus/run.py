#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stream compiler measurements, isolating failures without losing later inputs."""
import argparse,collections,hashlib,json,os,re,resource,signal,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--icd',type=Path,required=True);p.add_argument('--runner',type=Path,required=True);p.add_argument('--host-shim',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args()
assert os.uname().machine=='x86_64';a.output.mkdir(parents=True,exist_ok=False);out=a.output.resolve();paths=sorted((a.corpus/'meta').glob('*.txt'));paths=paths[:a.limit] if a.limit else paths
icd=a.icd.resolve();lib=Path(json.loads(icd.read_text())['ICD']['library_path']);lib=lib if lib.is_absolute() else icd.parent/lib
keys=['AGX_MESA_DEBUG','ASAHI_MESA_DEBUG','NIR_DEBUG','AGX_APPLE9_TRACE','AGX_APPLE9_ASM','AGX_APPLE9_TRACE_NIR','AGX_APPLE9_TRACE_FINAL_NIR','AGX_SPILL_NO_LOOP_HANDLING','AGX_APPLE9_RA_WEBS','AGX_APPLE9_RA_AUDIT']
env=dict(os.environ)
for k in keys:env.pop(k,None)
env.update(LD_PRELOAD=str(a.host_shim.resolve()),VK_DRIVER_FILES=str(icd),HK_EXPERIMENTAL_APPLE9='1',HK_APPLE9_EAGER_VARIANTS='1',AGX_APPLE9_STATS='1',MESA_SHADER_CACHE_DISABLE='true',AGX_SPILL_COALESCE='1')
(out/'provenance.json').write_text(json.dumps(dict(icd=str(icd),library=str(lib),library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),runner_sha256=hashlib.sha256(a.runner.read_bytes()).hexdigest(),shim_sha256=hashlib.sha256(a.host_shim.read_bytes()).hexdigest(),inputs=len(paths),corpus=str(a.corpus.resolve()),env={k:env[k] for k in env if k.startswith(('AGX_','HK_','MESA_','NIR_'))},load_before=os.getloadavg()),indent=2)+'\n')
index={str(v.resolve()):i for i,v in enumerate(paths)};counts=collections.Counter();start=time.perf_counter();begin=resource.getrusage(resource.RUSAGE_CHILDREN);offset=0;current=None;process=None
stat=re.compile(r'^(APPLE9(?:_PREAMBLE)?)_CODEGEN (.*)')
def fields(s):return {k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',s)}
def timed_out(*_):
 if process:process.kill()
 raise TimeoutError('shader compile exceeded 120 seconds')
signal.signal(signal.SIGALRM,timed_out)
with (out/'results.jsonl').open('w') as output:
 def emit(row):
  output.write(json.dumps(row)+'\n');output.flush();counts[row['status']]+=1
 while offset<len(paths):
  pending=out/'pending.txt';pending.write_text(''.join(str(x.resolve())+'\n' for x in paths[offset:]));current=None;completed=offset
  with pending.open() as stdin:
   process=subprocess.Popen([str(a.runner.resolve())],env=env,stdin=stdin,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,errors='replace')
   signal.alarm(120);failure=None
   try:
    for line in process.stderr:
     line=line.rstrip()
     if line.startswith('CORPUS_BEGIN '):
      path=line[13:];signal.alarm(120);stage=int(Path(path).read_text().split()[1]);current=dict(key=Path(path).stem,metadata=path,index=index[path],stage={1:0,16:4,32:5}[stage],programs=[],timings=[],diagnostics=[])
     elif current:
      if m:=stat.match(line):current['programs'].append(dict(kind=m[1],**fields(m[2])))
      elif line.startswith('CORPUS_TIME '):current['timings'].append(fields(line))
      elif line.startswith('CORPUS_CREATE '):current['create']=fields(line)
      elif line.startswith('CORPUS_END '):
       current['exit']=int(line.split()[-1]);mains=[x for x in current['programs'] if x['kind']=='APPLE9' and x['stage']==current['stage'] and not x['stub']];current['status']='pass' if current['exit']==0 and mains and all(x['ok'] for x in current['timings']) else 'compiler_failure';completed=current['index']+1;emit(current);current=None
      elif len(current['diagnostics'])<15:current['diagnostics'].append(line[:1000])
    rc=process.wait()
   except TimeoutError as e:failure=str(e);rc=process.wait()
   finally:signal.alarm(0)
  if current:
   current.update(status='timeout' if failure else 'crash',process_exit=rc,error=failure);completed=current['index']+1;emit(current)
  if completed==offset:raise RuntimeError('worker failed before any shader: '+str(rc))
  offset=completed
  if offset%1000==0:print('completed',offset,dict(counts),flush=True)
 pending.unlink(missing_ok=True)
u=resource.getrusage(resource.RUSAGE_CHILDREN)
summary=dict(outcomes=dict(counts),inputs=len(paths),wall_s=time.perf_counter()-start,user_s=u.ru_utime-begin.ru_utime,system_s=u.ru_stime-begin.ru_stime,load_after=os.getloadavg())
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
