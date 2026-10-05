#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare exact CTS cases from installed mustpass lists. Does not run CTS."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--lists',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
s=(a.lists/'cts-spirv-assembly.txt').read_text().splitlines();g=(a.lists/'cts-glsl.txt').read_text().splitlines()
phi=[x for x in s if '.opphi.' in x and ('.compute.' in x or x.endswith(('_frag','_vert')))]
control=[x for x in s if '.compute.loop_control.' in x or '.compute.selection_control.' in x]
generic=[x for x in g if '.loops.generic.' in x]
special_names={'conditional_break','conditional_continue','double_continue','ifblock','elseblock','mixed_break_continue','nested','nested_sequence','nested_tricky_dataflow_1','nested_tricky_dataflow_2'}
special=[x for x in g if '.loops.special.' in x and x.rsplit('.',1)[-1].rsplit('_',1)[0] in special_names]
functions=[x for x in g if '.functions.control_flow.' in x]
conditionals=[x for x in g if '.conditionals.' in x]
switch=[x for x in g if '.switch.' in x]
groups=dict(phi=phi,spirv_control=control,generic_loops=generic,special_loops=special,functions=functions,conditionals=conditionals,switch=switch)
normal=sorted(set(x for group in groups.values() for x in group))
forced=sorted(set(phi+generic+conditionals+[x for x in special if '.for_dynamic_iterations.' in x]))
a.output.mkdir(parents=True,exist_ok=True)
for name,ls in [('normal',normal),('forced-spill',forced)]:
 (a.output/(name+'.txt')).write_text('\n'.join(ls)+'\n')
meta=dict(groups={k:len(v) for k,v in groups.items()},normal=len(normal),forced_spill=len(forced),sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [a.lists/'cts-spirv-assembly.txt',a.lists/'cts-glsl.txt']})
(a.output/'selection.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta,indent=2))
