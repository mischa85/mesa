# SPDX-License-Identifier: MIT
"""Read single-threaded compiler stderr and emit one JSON object per program."""
import json
import re
import sys


def fields(line):
    return {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', line)}


items = []
trial = {}
pipeline = {}
name = None
for line in sys.stdin:
    if line.startswith('shader: MESA_SHADER_'):
        name = None
    elif line.startswith('name: '):
        name = line[6:].strip()
    elif line.startswith('VERTEX_AUDIT_PIPELINE '):
        pipeline = fields(line)
        match = re.search(r'hash=([0-9a-f]+)', line)
        if match:
            pipeline['hash'] = match[1]
    elif line.startswith('HOIST_TRIAL '):
        trial = fields(line)
    elif line.startswith('SPILL_CENSUS '):
        header = fields(line)
        items = []
    elif line.startswith('SPILL_ITEM '):
        items.append(fields(line))
    elif re.match(r'APPLE9(?:_PREAMBLE)?_CODEGEN ', line):
        stats = fields(line)
        assert header['stage'] == stats['stage']
        assert header['gprs'] == stats['gprs']
        assert sum(i['save'] for i in items) == stats['saves']
        assert sum(not i['save'] for i in items) == stats['fills']
        if name != 'stub VS':
            print(json.dumps(dict(
                kind='preamble' if '_PREAMBLE_' in line else 'main',
                name=name, pipeline=pipeline, stats=stats, spills=items,
                hoist_trial=trial)))
        trial = {}
    elif 'ERROR' in line:
        print(line, file=sys.stderr, end='')
