#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: report.py ICD.json cs2|lethal|willems|vkmark ... (host-only, noop DRM shim)."""
import sys, json, collections
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import latmetrics as L
icd = sys.argv[1]; out = {}
srcs = {'cs2': lambda: L.foz_programs(icd, L.R + '/tmp/cs2-fossilize-20261004/cs2-capture.foz', L.foz_hashes(L.R + '/tmp/cs2-fossilize-20261004/cs2-capture.foz', True)),
        'lethal': lambda: L.foz_programs(icd, L.R + '/artifacts/compiler-cross-corpus-20261006/lethal-company/lethal-capture.foz', L.foz_hashes(L.R + '/artifacts/compiler-cross-corpus-20261006/lethal-company/lethal-capture.foz', False)),
        'willems': lambda: L.pack_programs(icd, 'willems'), 'vkmark': lambda: L.pack_programs(icd, 'vkmark')}
HOT = {'a7fe66611aa32aa4', 'a9a9160b49129f97', '1eedf1e59030d12f', '9fec0a5bffe06df0', '1fcf1b4922e856cf'}
for name in sys.argv[2:]:
    bins = collections.defaultdict(collections.Counter)
    for key, I in srcs[name]():
        if len(I) < 30: continue
        r = L.regs(I)
        b = 'hot' if key in HOT else '<=32' if r <= 32 else '<=64' if r <= 64 else '<96' if r < 96 else '96'
        t = L.analyze(I); t['programs'] = 1; bins[b].update(t); bins['all'].update(t)
    out[name] = {k: dict(v) for k, v in bins.items()}
    print(name, json.dumps(out[name]), flush=True)
json.dump(out, open(sys.argv[1].replace('-icd.json', '-latreport.json'), 'w'), indent=1)
