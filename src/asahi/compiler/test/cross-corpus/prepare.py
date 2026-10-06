#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile public GLSL or enumerate SPIR-V, deduplicate and reflect layouts.
Bare shader measurements use declared descriptor types, default specialization
constants, 256 runtime-array descriptors, and a default graphics state. They
are explicitly distinct from Fossilize's recorded pipeline state.
"""
import argparse,collections,hashlib,json,struct,subprocess
from pathlib import Path
STAGES={0:1,1:2,2:4,3:8,4:16,5:32,5267:64,5268:128,5364:64,5365:128}
def reflect(data):
 w=struct.unpack('<%dI'%(len(data)//4),data);assert w[0]==0x07230203
 types={};const={};decor=collections.defaultdict(dict);member=collections.defaultdict(dict);var=[];entries=[];groups=[];i=5
 while i<len(w):
  n=w[i]>>16;op=w[i]&65535;assert n and i+n<=len(w);x=list(w[i+1:i+n]);i+=n
  if op==15:
   name=struct.pack('<%dI'%(len(x)-2),*x[2:]).split(b'\0')[0].decode();entries.append((x[0],name))
  elif 19<=op<=39 or op==5341:types[x[0]]=(op,x[1:])
  elif op in (43,50):const[x[1]]=x[2] | (x[3]<<32 if len(x)>3 else 0)
  elif op in (41,42,48,49):const[x[1]]=int(op in (41,48))
  elif op==59:var.append(x[:3])
  elif op==71:decor[x[0]][x[1]]=x[2:]
  elif op==72:member[(x[0],x[1])][x[2]]=x[3:]
  elif op in (74,75):groups.append((op,x))
 for op,x in groups:
  if op==74:
   for target in x[1:]:decor[target].update(decor[x[0]])
  else:
   for j in range(1,len(x),2):member[(x[j],x[j+1])].update(decor[x[0]])
 def size(t):
  op,x=types[t]
  if op==20:return 4
  if op==32 and x[0]==5349:return 8
  if op in (21,22):return x[0]//8
  if op in (23,24):return size(x[0])*x[1]
  if op==28:return decor[t].get(6,[size(x[0])])[0]*const[x[1]]
  if op==30:
   end=0
   for j,v in enumerate(x):
    md=member[(t,j)];z=size(v)
    if 7 in md and types[v][0]==24:
     matrix=types[v][1];z=md[7][0]*(types[matrix[0]][1][1] if 4 in md else matrix[1])
    end=max(end,md.get(35,[end])[0]+z)
   return end
  raise ValueError('unknown block size type '+str(op))
 bindings=[];push=0;runtime=False
 for pointer,ident,storage in var:
  op,x=types[pointer];assert op==32;t=x[1]
  if storage==9:push=max(push,size(t));continue
  if 33 not in decor[ident]:continue
  if storage not in (0,2,12):raise ValueError('descriptor storage '+str(storage))
  count=1
  while types[t][0] in (28,29):
   op,x=types[t];count*=const[x[1]] if op==28 else 256;runtime|=op==29;t=x[0]
  op,x=types[t]
  if storage==12 or (storage==2 and 3 in decor[t]):kind=7
  elif storage==2:kind=6
  elif op==26:kind=0
  elif op==27:kind=1
  elif op==25:
   dim=x[1];sampled=x[5]
   kind=10 if dim==6 else (5 if sampled==2 else 4) if dim==5 else 3 if sampled==2 else 2
  elif op==5341:kind=1000150000
  else:raise ValueError('descriptor type '+str(op))
  bindings.append((decor[ident].get(34,[0])[0],decor[ident][33][0],kind,count))
 # Repeated declarations for one binding must agree.
 unique={}
 for s,b,t,c in bindings:
  if (s,b) in unique and unique[s,b]!=(t,c):raise ValueError('aliased descriptor types')
  unique[s,b]=(t,c)
 return dict(entries=entries,bindings=[(s,b,t,c) for (s,b),(t,c) in sorted(unique.items())],push=(push+3)//4*4,runtime_descriptor_array=runtime)
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--glsl',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);out=a.output.resolve();(out/'spv').mkdir();(out/'meta').mkdir();seen={};counts=collections.Counter()
 with (out/'manifest.jsonl').open('w') as manifest:
  suffixes={'.vert','.frag','.comp','.geom','.tesc','.tese','.mesh','.task','.rgen','.rchit','.rmiss','.rahit','.rint','.rcall'}
  files=sorted(f for f in a.source.rglob('*') if f.is_file() and (f.suffix in suffixes if a.glsl else f.suffix=='.spv'))
  for f in files:
   row={'source':str(f.relative_to(a.source))};counts['inputs']+=1
   try:
    if a.glsl:
     target=out/'tmp.spv';r=subprocess.run(['glslangValidator','-V','--target-env','vulkan1.3','-I'+str(f.parent),str(f),'-o',str(target)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
     if r.returncode:row.update(status='frontend_failure',error=r.stdout.decode(errors='replace')[-4000:]);counts[row['status']]+=1;manifest.write(json.dumps(row)+'\n');continue
     data=target.read_bytes()
    else:data=f.read_bytes()
    digest=hashlib.sha256(data).hexdigest();row['sha256']=digest
    if digest in seen:row.update(status='duplicate',canonical=seen[digest]);counts['duplicates']+=1;manifest.write(json.dumps(row)+'\n');continue
    seen[digest]=row['source'];spv=out/'spv'/(digest+'.spv');spv.write_bytes(data);info=reflect(data);row.update(info);prepared=[];unsupported=[]
    for model,name in info['entries']:
     if model not in (0,1,2,3,4,5):unsupported.append((model,name));continue
     if any(s>=8 or c>65536 for s,b,t,c in info['bindings']) or info['push']>256:raise ValueError('layout exceeds runner limits')
     meta=out/'meta'/(digest+'-'+str(model)+'.txt');meta.write_text(f'{spv} {STAGES[model]} {name} {info["push"]} {len(info["bindings"])}\n'+''.join('%d %d %d %d\n'%tuple(b) for b in info['bindings']));prepared.append(str(meta))
    row.update(status='prepared' if prepared else 'unsupported_stage',metadata=prepared,unsupported_entries=unsupported);counts['unique']+=1;counts['prepared_entries']+=len(prepared)
   except Exception as e:row.update(status='reflection_failure',error=str(e))
   counts[row['status']]+=1;manifest.write(json.dumps(row)+'\n');manifest.flush()
 (out/'summary.json').write_text(json.dumps(counts,indent=2)+'\n');(out/'tmp.spv').unlink(missing_ok=True);print(json.dumps(counts))
if __name__=='__main__':main()
