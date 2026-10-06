#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add failure receipts to a private snapshot without changing compilation.

The production checkout and previously measured libraries stay untouched.
Use the diagnostic runner's Vulkan callback for frontend capability failures.
"""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--compiler', type=Path, required=True)
p.add_argument('--adapter', type=Path, required=True)
p.add_argument('--build', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
compiler, adapter, build, out = (x.resolve() for x in
                               (a.compiler, a.adapter, a.build, a.output))
out.mkdir(parents=True, exist_ok=False)
provenance = json.loads((compiler / 'provenance.json').read_text())
source = compiler / 'source/src/asahi/compiler/agx_compile_apple9.c'
s = source.read_text()

# Print only the failed physical instruction, without enabling whole-program
# traces. This exposes placement/encoding failures after successful lowering.
pack_failure = s.index('"APPLE9_PACK_FAIL i=')
guard = s.rfind('if (agx_apple9_trace_enabled())', 0, pack_failure)
assert guard >= 0
s = s[:guard] + s[guard:].replace('if (agx_apple9_trace_enabled())', 'if (true)', 1)

def modify_function(name, change):
    global s
    start = s.index('\n' + name + '(')
    brace = s.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}')
        end += 1
    s = s[:start] + change(s[start:end]) + s[end:]

# Each receipt is emitted at the rejection, with the actual NIR instruction.
helper = '''
static void corpus_trigger(const char *where, nir_instr *instr)
{
   fprintf(stderr, "CORPUS_TRIGGER %s: ", where);
   nir_print_instr(instr, stderr);
   fprintf(stderr, "\\n");
}
'''
pos = s.index('\nstatic bool\napple9_find_buffer_dag(')
s = s[:pos] + helper + s[pos:]

def buffer_receipts(part):
    part = part.replace('if (getenv("AGX_APPLE9_TRACE_NIR") != NULL) {', 'if (true) {')
    part = part.replace('Apple9 unsupported instruction: ', 'CORPUS_TRIGGER subset: ')
    # The loop variable is live for every reason assignment in this loop.
    start = part.index('   nir_foreach_block(block, impl)')
    end = part.index('{', start) + 1
    depth = 1
    while depth:
        depth += (part[end] == '{') - (part[end] == '}')
        end += 1
    loop = part[start:end]
    # Restrict to assignments enclosed in braces; do not alter a bare if body.
    loop = re.sub(r'(\{\n)([ ]+)(\*reason =)',
                  r'\1\2corpus_trigger("buffer", instr);\n\2\3', loop)
    return part[:start] + loop + part[end:]

modify_function('apple9_find_buffer_dag', buffer_receipts)
modify_function('apple9_lower_vertex_input', lambda part: part.replace(
    'lower->valid = false;',
    'corpus_trigger("vertex_input", &intr->instr); lower->valid = false;'))

def varying_receipts(part):
    part = part.replace('   bool fragment =', '   nir_instr *last = NULL;\n   bool fragment =')
    part = part.replace('nir_intrinsic_instr *intr = nir_instr_as_intrinsic(instr);',
                        'last = instr;\n         nir_intrinsic_instr *intr = nir_instr_as_intrinsic(instr);')
    part = part.replace('unsupported:\n', 'unsupported:\n   if (last) corpus_trigger("varying", last);\n')
    return part

modify_function('apple9_collect_varyings', varying_receipts)
modify_function('apple9_compile_graphics_corpus_impl', lambda part: part.replace(
    'if (!apple9_texture_supported(tex)) {',
    'if (!apple9_texture_supported(tex)) {\n            corpus_trigger("texture", instr);'))
# Capture the compiler's final own reason, including compute's quiet failure path.
for name, reason in [('agx_compile_apple9_tiny', 'reason_out'),
                     ('apple9_compile_graphics', 'reason')]:
    modify_function(name, lambda part, reason=reason: part.replace(
        'fprintf(stderr,"CORPUS_TIME',
        'if(!ok)fprintf(stderr,"CORPUS_REASON %s\\n",' + reason + ' && *' + reason +
        ' ? *' + reason + ' : "unspecified");fprintf(stderr,"CORPUS_TIME'))

f = out / source.name
f.write_text(s)
cmd = next(c for c in provenance['commands'] if c[-3] == str(source))
cmd = [str(f) if x == str(source) else x for x in cmd]
obj = out / (source.name + '.o')
cmd[-1] = str(obj)
subprocess.run(cmd, cwd=build, check=True)
members = subprocess.check_output(['ar', 't', str(compiler / 'libasahi_compiler.a')], text=True).splitlines()
archive = out / 'libasahi_compiler.a'
subprocess.run(['ar', 'rcs', str(archive), *[
    str(obj if Path(m).name == obj.name else compiler / Path(m).name)
    for m in members]], check=True)
links = json.loads((adapter / 'commands.json').read_text())['links']
link = next(c for c in links if str(compiler / 'libasahi_compiler.a') in c)
old_driver = adapter / compiler.name / 'libvulkan_asahi.so'
driver = out / 'libvulkan_asahi.so'
link = [str(archive) if x == str(compiler / 'libasahi_compiler.a') else
        str(driver) if x == str(old_driver) else x for x in link]
subprocess.run(link, cwd=build, check=True)
(out / 'icd.json').write_text(json.dumps({'file_format_version': '1.0.0',
    'ICD': {'library_path': str(driver), 'api_version': '1.4.0'}}) + '\n')
(out / 'provenance.json').write_text(json.dumps(dict(
    compiler=str(compiler), adapter=str(adapter), commands=[cmd, link],
    source_sha256=hashlib.sha256(s.encode()).hexdigest(),
    driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest()), indent=2) + '\n')
