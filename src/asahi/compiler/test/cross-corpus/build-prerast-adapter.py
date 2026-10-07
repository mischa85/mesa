#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Private common front-end adapter for independently compiling GS/TCS/TES.
Uses the existing normal lowering functions with their default graphics key.
No companion shaders or constant substitute inputs are introduced.
"""
import argparse,json,shlex,subprocess,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--mesa',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('compilers',nargs='+',type=Path);a=p.parse_args();r=a.mesa.resolve();b=a.build.resolve();d=a.output.resolve();d.mkdir(parents=True,exist_ok=False)
ref=json.loads((a.compilers[0]/'provenance.json').read_text()).get('compiler_ref')
# Take the common driver source from the compiler snapshot's ref, not the working tree,
# so hk_shader.c changes are measured with the commit they belong to.
s=subprocess.check_output(['git','show',ref+':src/asahi/vulkan/hk_shader.c'],cwd=r,text=True) if ref else (r/'src/asahi/vulkan/hk_shader.c').read_text();old='if (hk_apple9_needs_deferral(shader_count, infos, state, features))';assert s.count(old)==1
s=s.replace(old,'''if (!(getenv("CORPUS_DIRECT_PRERAST") && shader_count == 1 &&
            (infos[0].stage == MESA_SHADER_GEOMETRY ||
             infos[0].stage == MESA_SHADER_TESS_CTRL ||
             infos[0].stage == MESA_SHADER_TESS_EVAL)) &&
          hk_apple9_needs_deferral(shader_count, infos, state, features))''')
s=s.replace('if (result != VK_SUCCESS && agx_get_compiler_debug())','if (result != VK_SUCCESS && (agx_get_compiler_debug() || getenv("CORPUS_DIRECT_PRERAST")))')
s=s.replace('shader->b.info.stats.instrs = 1;', 'shader->b.info.stats.instrs = 1;\n         if (getenv("CORPUS_DIRECT_PRERAST")) fprintf(stderr, "CORPUS_EMPTY stage=5\\n");')
f=d/'hk_shader.c';f.write_text(s);cs=json.loads((b/'compile_commands.json').read_text());v=next(c for c in cs if c['file'].endswith('/hk_shader.c'));cmd=[];skip=False
for x in shlex.split(v['command']):
 if skip:skip=False;continue
 if x in ['-o','-MF','-MQ']:skip=True;continue
 if x in ['-MD','-MMD',v['file']]:continue
 cmd.append(x)
obj=d/'hk_shader.c.o';cmd += [str(f),'-o',str(obj)];subprocess.run(cmd,cwd=b,check=True)
lib=d/'libhk.a';members=subprocess.check_output(['ar','t',str(b/'src/asahi/vulkan/libhk.a')],text=True).splitlines();subprocess.run(['ar','rcs',str(lib),*[str(obj) if Path(m).name=='hk_shader.c.o' else m for m in members]],cwd=b,check=True)
base=shlex.split(subprocess.check_output(['ninja','-t','commands','src/asahi/vulkan/libvulkan_asahi.so'],cwd=b,text=True).splitlines()[-1]);links=[]
for compiler in a.compilers:
 compiler=compiler.resolve();out=d/compiler.name;out.mkdir();driver=out/'libvulkan_asahi.so'
 replacements={'src/asahi/vulkan/libhk.a':str(lib),'src/asahi/compiler/libasahi_compiler.a':str(compiler/'libasahi_compiler.a'),'src/asahi/vulkan/libvulkan_asahi.so':str(driver)}
 link=[replacements.get(x,x) for x in base];subprocess.run(link,cwd=b,check=True);links.append(link)
 (out/'icd.json').write_text(json.dumps({'file_format_version':'1.0.0','ICD':{'library_path':str(driver),'api_version':'1.4.0'}})+'\n')
 (out/'provenance.json').write_text(json.dumps(dict(compiler_provenance=json.loads((compiler/'provenance.json').read_text()),common_shader_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),library_sha256=hashlib.sha256(driver.read_bytes()).hexdigest()),indent=2)+'\n')
(d/'commands.json').write_text(json.dumps(dict(compile=cmd,links=links),indent=2)+'\n')
