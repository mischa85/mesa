#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""In-loop register copies and three-XOR swaps per corpus (host-only).
Usage: copies.py ICD.json corpus..."""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import latmetrics as L
reg = lambda x: int(x[1:]) if re.fullmatch(r'r\d+', x) else None

def count(I):
    depth = 0; t = collections.Counter()
    i = 0
    while i < len(I):
        x = I[i]
        if x['op'] == 'LOOP_MASK_PUSH': depth += 1
        elif x['op'] == 'LOOP_MASK_POP': depth = max(0, depth - 1)
        where = 'loop' if depth else 'straight'
        t['instr_' + where] += 1
        if (i + 2 < len(I) and all(I[i + k]['op'] == 'IXOR' and len(I[i + k]['src']) == 2 for k in range(3))
                and I[i]['dst'] == I[i + 2]['dst'] and I[i]['dst'] != I[i + 1]['dst']):
            t['swap_' + where] += 1; i += 3; t['instr_' + where] += 2; continue
        if x['op'] == 'IOR' and len(x['src']) == 2 and x['src'][0] == x['src'][1] and x['dst'] != x['src'][0] and reg(x['src'][0]) is not None:
            t['copy_' + where] += 1
        i += 1
    return t

icd = sys.argv[1]
srcs = {'cs2': lambda: L.foz_programs(icd, L.R + '/tmp/cs2-fossilize-20261004/cs2-capture.foz', L.foz_hashes(L.R + '/tmp/cs2-fossilize-20261004/cs2-capture.foz', True)),
        'lethal': lambda: L.foz_programs(icd, L.R + '/artifacts/compiler-cross-corpus-20261006/lethal-company/lethal-capture.foz', L.foz_hashes(L.R + '/artifacts/compiler-cross-corpus-20261006/lethal-company/lethal-capture.foz', False)),
        'willems': lambda: L.pack_programs(icd, 'willems'), 'vkmark': lambda: L.pack_programs(icd, 'vkmark'),
        'cts': lambda: L.pack_programs(icd, 'cts'), 'robust': lambda: L.pack_programs(icd, 'robust')}
for name in sys.argv[2:]:
    t = collections.Counter(); loopy = 0
    for key, I in srcs[name]():
        c = count(I); t.update(c); loopy += c['instr_loop'] > 0
    print(name, 'programs-with-loops', loopy, dict(t), flush=True)
