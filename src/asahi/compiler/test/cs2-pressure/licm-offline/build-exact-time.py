# SPDX-License-Identifier: MIT
from pathlib import Path
import json,shlex,subprocess,sys,os
headers=Path(__file__).resolve().parent
root=Path(os.environ.get('MESA_SOURCE',headers.parents[5])).resolve()
build=Path(os.environ.get('MESA_BUILD',root/'build-host-replay')).resolve()
out=Path(os.environ.get('CENSUS_OUTPUT',root/'build-licm-offline')).resolve()
d=out/sys.argv[1];d.mkdir(parents=True,exist_ok=True)
def frozen(name):return subprocess.check_output(['git','show','1f4c8abe909:src/asahi/compiler/'+name],cwd=root,text=True)
c=frozen('agx_compile_apple9.c')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip().startswith('127976460da'), 'Use the frozen offline prototype checkout with its matching full compiler archive'
mode=sys.argv[2]; timing='--timing' in sys.argv
r=frozen('agx_register_allocate.c').replace('         agx_reuse_spill_reloads(ctx);','         (void)ctx;')
r=r.replace('      assert(effective_demand <= max_possible_regs && "spiller post-condition");', '      if(effective_demand > max_possible_regs) {fprintf(stderr,"ERROR post-spill demand %u > %u\\n",effective_demand,max_possible_regs);abort();}')
a=frozen('agx_apple9_ra.c')
if not timing:
 c=c.replace('struct apple9_dag_cost {',f'#include "{headers}/loop-census.h"\nFILE *latency_log(void);\nFILE *latency_log(void) {{return apple9_log();}}\n\nstruct apple9_dag_cost {{')
 c=c.replace('   if (licm)\n      agx_nir_opt_apple9_licm(nir);','   latency_hoist(nir, licm);')
 c=c.replace('   if (agx_apple9_trace_enabled()) {\n      fprintf(apple9_log(), "APPLE9_ALLOC_STATS', '   latency_nir(nir);\n   latency_physical(&lower.program);\n   if (agx_apple9_trace_enabled()) {\n      fprintf(apple9_log(), "APPLE9_ALLOC_STATS')
 a=a.replace('static enum agx_schedule_class',f'#include "{headers}/loop-ra.h"\nstatic enum agx_schedule_class',1)
 a=a.replace('   *result = out;','   latency_save(&ra,out.instructions);\n   *result = out;')
 a=a.replace('   *program = best;','   *program = best;\n   latency_dump(program->instructions);')
 r=r.replace('static unsigned\nagx_calc_register_demand', 'extern void latency_demand_begin(agx_context *ctx);\nextern void latency_demand_end(void);\nextern void latency_demand(unsigned block,unsigned n);\nstatic unsigned\nagx_calc_register_demand')
 for expr in ['demand','I->src[0].value + size','I->imm + size','first + width']:
  import re
  pattern=r'(max_demand = MAX2\('+(re.escape(expr)+r', max_demand' if expr=='demand' else r'max_demand, '+re.escape(expr))+r'\);)'
  r,n=re.subn(pattern,r'\1 latency_demand(block->index,'+expr+');',r);assert n
 r=r.replace('   unsigned effective_demand = agx_calc_register_demand(ctx, false);','   latency_demand_begin(ctx);\n   unsigned effective_demand = agx_calc_register_demand(ctx, false);\n   latency_demand_end();')
else:
 c='#include <time.h>\n'+c
 # Wrappers encompass backend NIR lowering and all existing sample-hoist trials.
 for name in ['agx_compile_apple9_tiny','apple9_compile_graphics']:
  pos=c.index(name+'(nir_shader *nir');beg=c.rfind('\n',0,pos)+1;brace=c.index('{',pos)
  sig=c[beg:brace];depth=1;j=brace+1
  while depth:
   if c[j]=='{':depth+=1
   if c[j]=='}':depth-=1
   j+=1
  args='nir,out,profile,reason_out' if name.endswith('tiny') else 'nir,out,layout,producer,blend,nr_targets,reason'
  wrapper='\n'+('bool\n' if name.endswith('tiny') else 'static bool\n')+sig+'{struct timespec a,b,x,y; unsigned stage=nir->info.stage; clock_gettime(CLOCK_MONOTONIC,&a);clock_gettime(CLOCK_THREAD_CPUTIME_ID,&x);bool ok='+name+'_timed_impl('+args+');clock_gettime(CLOCK_THREAD_CPUTIME_ID,&y);clock_gettime(CLOCK_MONOTONIC,&b);fprintf(stderr,"BACKEND_TIME stage=%u wall_ns=%llu cpu_ns=%llu ok=%u\\n",stage,(unsigned long long)((b.tv_sec-a.tv_sec)*1000000000ll+b.tv_nsec-a.tv_nsec),(unsigned long long)((y.tv_sec-x.tv_sec)*1000000000ll+y.tv_nsec-x.tv_nsec),ok);return ok;}\n'
  c=c[:j]+wrapper+c[j:];c=c[:pos]+c[pos:].replace(name+'(',name+'_timed_impl(',1)
 c=c.replace('bool\nagx_compile_apple9_tiny_timed_impl','static bool\nagx_compile_apple9_tiny_timed_impl')
cs=json.loads((build/'compile_commands.json').read_text());replaced={}
for filename,source in {'agx_compile_apple9.c':c,'agx_register_allocate.c':r,'agx_apple9_ra.c':a,'agx_apple9_opt.c':frozen('agx_apple9_opt.c')}.items():
 (d/filename).write_text(source)
 v=next(c for c in cs if c['file'].endswith('/'+filename));a=shlex.split(v['command']);cmd=[];skip=False
 for x in a:
  if skip:skip=False;continue
  if x in ['-o','-MF','-MQ']:skip=True;continue
  if x in ['-MD','-MMD'] or x.endswith('/'+filename):continue
  cmd.append(x)
 obj=d/(filename+'.o');subprocess.run(cmd+[str(d/filename),'-o',str(obj)],cwd=build,check=True);replaced[filename+'.o']=str(obj)
lib=d/'libasahi_compiler.a';original=build/'src/asahi/compiler/libasahi_compiler.a'
members=subprocess.check_output(['ar','t',str(original)],text=True).splitlines();objects=[replaced.get(Path(m).name,m) for m in members]
lib.unlink(missing_ok=True);subprocess.run(['ar','rcs',str(lib),*objects],check=True)
link=shlex.split(subprocess.check_output(['ninja','-t','commands','src/asahi/vulkan/libvulkan_asahi.so'],cwd=build,text=True).splitlines()[-1]);link=[str(lib) if x=='src/asahi/compiler/libasahi_compiler.a' else str(d/'libvulkan_asahi.so') if x=='src/asahi/vulkan/libvulkan_asahi.so' else x for x in link]
subprocess.run(link,cwd=build,check=True)
(d/'icd.json').write_text(json.dumps({'file_format_version':'1.0.0','ICD':{'library_path':str(d/'libvulkan_asahi.so'),'api_version':'1.4.0'}})+'\n')
