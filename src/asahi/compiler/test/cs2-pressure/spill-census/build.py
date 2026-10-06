# SPDX-License-Identifier: MIT
"""Build a host-only spill census overlay against a matching compiler archive."""
from pathlib import Path
import json,shlex,subprocess,sys,os
headers = Path(__file__).resolve().parent
root = Path(os.environ.get('MESA_SOURCE', headers.parents[5])).resolve()
build = Path(os.environ.get('MESA_BUILD', root / 'build-host-replay')).resolve()
out = Path(os.environ.get('CENSUS_OUTPUT', root / 'build-spill-census')).resolve()
d = out / sys.argv[1]
d.mkdir(parents=True, exist_ok=True)
source_root=Path(os.environ.get('SOURCE_TREE',root))
def change(s,a,b):
 assert a in s,a
 return s.replace(a,b)
spill=(source_root/'src/asahi/compiler/agx_spill.c').read_text()
spill=change(spill,'#include "agx_opcodes.h"',f'#include "agx_opcodes.h"\n#include "{headers}/spill-census.h"\n#include "{headers}/spill-origin.h"')
spill=change(spill,'   unsigned n = ctx->alloc;','   struct sc_tag *sc_defs = sc_origins(ctx);\n   unsigned n = ctx->alloc;')
spill=change(spill,'   agx_repair_ssa(ctx);','   sc_spill_moves(ctx, sc_defs, n);\n   agx_repair_ssa(ctx);')
ra=(source_root/'src/asahi/compiler/agx_apple9_ra.c').read_text()
ra=change(ra,'#include "agx_debug.h"',f'#include "agx_debug.h"\n#include "{headers}/spill-census.h"\n#include "{headers}/spill-physical.h"')
ra=change(ra,'   if (!agx_apple9_allocate_publications(program, reason))','   sc_begin();\n   if (!agx_apple9_allocate_publications(program, reason))')
ra=change(ra,'   *out->instructions[out->instruction_count - 1] = *ins;','   *out->instructions[out->instruction_count - 1] = *ins;\n   sc_put(sc_physical, out->instructions[out->instruction_count - 1], sc_current);')
ra=change(ra,'      agx_foreach_instr_in_block(common, I) {\n         switch (I->op) {','      agx_foreach_instr_in_block(common, I) {\n         sc_current=sc_get(sc_common,I);\n         switch (I->op) {')
ra=change(ra,'         struct agx_apple9_vir_instr ins = *program->instructions[i];','         sc_current=sc_get(sc_physical, program->instructions[i]);\n         struct agx_apple9_vir_instr ins = *program->instructions[i];')
ra=change(ra,'   struct apple9_shared_ra ra = {.program = program};','   _mesa_hash_table_clear(sc_common, NULL);\n   struct apple9_shared_ra ra = {.program = program};')
ra=change(ra,'   *program = best;','   *program = best;\n   sc_dump(program,nir->info.stage);')
c=(source_root/'src/asahi/compiler/agx_compile_apple9.c').read_text()
if 'uint64_t weighted_spills;' not in c:
 c=change(c,'struct apple9_dag_cost {','struct apple9_dag_cost {\n   uint64_t weighted_spills;')
 needle='         cost->spills += op == AGX_APPLE9_VIR_SPILL_STORE ||\n                         op == AGX_APPLE9_VIR_SPILL_LOAD;'
 c=change(c,needle,needle+\
 '\n         if(op == AGX_APPLE9_VIR_SPILL_STORE || op == AGX_APPLE9_VIR_SPILL_LOAD) {\n            const struct agx_apple9_block *blk=agx_apple9_instr_block(lower.program.instructions[i]);\n            unsigned depth=0;\n            for(nir_cf_node *n=blk&&blk->nir?blk->nir->cf_node.parent:NULL;n;n=n->parent) depth+=n->type==nir_cf_node_loop;\n            cost->weighted_spills += 1u << (3 * MIN2(depth,6));\n         }')
c=change(c,'struct apple9_dag_cost {','FILE *spill_census_log(void);\nFILE *spill_census_log(void) { return apple9_log(); }\n\nstruct apple9_dag_cost {')
c=change(c,'   const char *log = use_plain ? plain_log : hoisted_log;','   fprintf(stderr,"HOIST_TRIAL hoisted_weighted=%llu plain_weighted=%llu hoisted_spills=%u plain_spills=%u hoisted_instrs=%u plain_instrs=%u selected_plain=%u tried_plain=%u\\n",(unsigned long long)hoisted_cost.weighted_spills,(unsigned long long)plain_cost.weighted_spills,hoisted_cost.spills,plain_cost.spills,hoisted_cost.instructions,plain_cost.instructions,use_plain,plain_log!=NULL);\n   const char *log = use_plain ? plain_log : hoisted_log;')
sources={'agx_spill.c':spill,'agx_apple9_ra.c':ra,'agx_compile_apple9.c':c}
if len(sys.argv)>2 and sys.argv[2]=='check-pressure':
 r=(source_root/'src/asahi/compiler/agx_register_allocate.c').read_text()
 r=change(r,'      assert(effective_demand <= max_possible_regs && "spiller post-condition");','      if(effective_demand > max_possible_regs) { fprintf(stderr,"ERROR spill pressure %u > %u\\n",effective_demand,max_possible_regs); abort(); }')
 sources['agx_register_allocate.c']=r

cs=json.loads((build/'compile_commands.json').read_text());replaced={}
for filename,source in sources.items():
 (d/filename).write_text(source)
 c=next(c for c in cs if c['file'].endswith('/'+filename));a=shlex.split(c['command']);cmd=[];skip=False
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
