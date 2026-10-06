#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a complete compiler snapshot against one fixed host-only driver.
All private compiler headers and compiler objects come from the same revision.
Only compact statistics and timing are added to the private source snapshot.
"""
import argparse,concurrent.futures,hashlib,json,shlex,subprocess,tarfile,io
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--mesa',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--ref',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=a.mesa.resolve();b=a.build.resolve();d=a.output.resolve();d.mkdir(parents=True,exist_ok=False)
rev=subprocess.check_output(['git','rev-parse',a.ref],cwd=r,text=True).strip()
raw=subprocess.check_output(['git','archive',rev,'src/asahi'],cwd=r)
with tarfile.open(fileobj=io.BytesIO(raw)) as t:t.extractall(d/'source',filter='data')
cdir=d/'source/src/asahi/compiler';cpath=cdir/'agx_compile_apple9.c';c=cpath.read_text();original_sha=hashlib.sha256(c.encode()).hexdigest()
# Match physical XOR swaps exactly, rather than counting all XOR operations.
anchor='      unsigned copies = 0, waits = 0, saves = 0, fills = 0;'
assert c.count(anchor)==1
extra='''      unsigned swaps = 0;
      for (unsigned k = 0; k + 2 < lower.program.instruction_count; ++k) {
         const struct agx_apple9_vir_instr *a = lower.program.instructions[k];
         const struct agx_apple9_vir_instr *b = lower.program.instructions[k+1];
         const struct agx_apple9_vir_instr *c = lower.program.instructions[k+2];
         if (a->op != AGX_APPLE9_VIR_IXOR || b->op != a->op || c->op != a->op ||
             a->nr_srcs != 2 || b->nr_srcs != 2 || c->nr_srcs != 2 ||
             a->immediate || b->immediate || c->immediate ||
             a->alu_src_uniform_mask || b->alu_src_uniform_mask || c->alu_src_uniform_mask ||
             a->alu_src_immediate_mask || b->alu_src_immediate_mask || c->alu_src_immediate_mask)
            continue;
         unsigned x = lower.program.phys[a->dest], y = lower.program.phys[b->dest];
         if (x == y || lower.program.phys[c->dest] != x) continue;
         bool match = true;
         const struct agx_apple9_vir_instr *v[] = {a,b,c};
         for (unsigned j=0;j<3;j++) {
            unsigned p=lower.program.phys[v[j]->src[0]],q=lower.program.phys[v[j]->src[1]];
            match &= (p==x && q==y) || (p==y && q==x);
         }
         if (match) {swaps++;k+=2;}
      }
'''
c=c.replace(anchor,anchor+'\n'+extra)
c=c.replace('gprs=%u scratch=%u\\n",','gprs=%u scratch=%u swaps=%u stub=%u\\n",',1)
c=c.replace('              lower.program.scratch_size);','              lower.program.scratch_size, swaps, nir->info.name && !strcmp(nir->info.name,"stub VS"));',1)
c='#include <time.h>\n'+c
for name in ['agx_compile_apple9_tiny','apple9_compile_graphics']:
 pos=c.index(name+'(nir_shader *nir');beg=c.rfind('\n',0,pos)+1;brace=c.index('{',pos);sig=c[beg:brace];depth=1;j=brace+1
 while depth:
  if c[j]=='{':depth+=1
  if c[j]=='}':depth-=1
  j+=1
 args='nir,out,profile,reason_out' if name.endswith('tiny') else 'nir,out,layout,producer,blend,nr_targets,reason'
 wrapper='\n'+('bool\n' if name.endswith('tiny') else 'static bool\n')+sig+'{struct timespec a,b;unsigned stage=nir->info.stage;clock_gettime(CLOCK_THREAD_CPUTIME_ID,&a);bool ok='+name+'_corpus_impl('+args+');clock_gettime(CLOCK_THREAD_CPUTIME_ID,&b);fprintf(stderr,"CORPUS_TIME stage=%u cpu_ns=%llu ok=%u\\n",stage,(unsigned long long)((b.tv_sec-a.tv_sec)*1000000000ll+b.tv_nsec-a.tv_nsec),ok);return ok;}\n'
 c=c[:j]+wrapper+c[j:];c=c[:pos]+c[pos:].replace(name+'(',name+'_corpus_impl(',1)
c=c.replace('bool\nagx_compile_apple9_tiny_corpus_impl','static bool\nagx_compile_apple9_tiny_corpus_impl');cpath.write_text(c)
cs=json.loads((b/'compile_commands.json').read_text());members=subprocess.check_output(['ar','t',str(b/'src/asahi/compiler/libasahi_compiler.a')],text=True).splitlines();commands=[]
for member in members:
 obj=Path(member);obj=obj if obj.is_absolute() else b/obj
 entry=next(v for v in cs if (b/v['output']).resolve()==obj.resolve());src=(b/entry['file']).resolve();source=d/'source'/src.relative_to(r) if src.is_relative_to(r) and not src.is_relative_to(b) else cdir/src.name
 if not source.exists():
  if src.name=='agx_spill_coalesce.c':continue
  assert str(src).startswith(str(b)),src
  source=src # generated opcode tables, unchanged across these revisions
 cmd=[];skip=False
 for x in shlex.split(entry['command']):
  if skip:skip=False;continue
  if x in ['-o','-MF','-MQ']:skip=True;continue
  if x in ['-MD','-MMD',entry['file']]:continue
  if x=='-I../src/asahi/compiler':x='-I'+str(cdir)
  if x=='-I../src':cmd.append('-I'+str(d/'source/src'))
  cmd.append(x)
 out=d/(src.name+'.o');cmd += [str(source),'-o',str(out)];commands.append((cmd,out))
def run(pair):subprocess.run(pair[0],cwd=b,check=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,commands))
lib=d/'libasahi_compiler.a';subprocess.run(['ar','rcs',str(lib),*[str(o) for _,o in commands]],check=True)
link=shlex.split(subprocess.check_output(['ninja','-t','commands','src/asahi/vulkan/libvulkan_asahi.so'],cwd=b,text=True).splitlines()[-1]);driver=d/'libvulkan_asahi.so'
link=[str(lib) if x=='src/asahi/compiler/libasahi_compiler.a' else str(driver) if x=='src/asahi/vulkan/libvulkan_asahi.so' else x for x in link];subprocess.run(link,cwd=b,check=True)
(d/'icd.json').write_text(json.dumps({'file_format_version':'1.0.0','ICD':{'library_path':str(driver),'api_version':'1.4.0'}})+'\n')
(d/'provenance.json').write_text(json.dumps(dict(compiler_ref=rev,common_driver_ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),original_compile_sha256=original_sha,compiler_source_manifest={str(f.relative_to(cdir)):hashlib.sha256(f.read_bytes()).hexdigest() for f in cdir.glob('*') if f.is_file()},commands=[v for v,_ in commands],link=link,driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest()),indent=2)+'\n')
print(rev,driver,flush=True)
