#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Merge disjoint frozen replay pieces and verify complete population identity."""
import argparse, collections, json, sqlite3, zlib
from pathlib import Path
from packed import Pack, results

p = argparse.ArgumentParser()
p.add_argument('--pack', type=Path, required=True)
p.add_argument('--populations', nargs='+', required=True)
p.add_argument('--runs', nargs='+', type=Path, required=True)
p.add_argument('--verified-empty', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
pack = Pack(a.pack)
expected = set()
for population in a.populations:
    keys = set(pack.keys(population))
    assert not keys & expected, population
    expected.update(keys)
empty = set()
if a.verified_empty:
    for r in results(a.verified_empty):
        assert r['status'] == 'empty_shader' and r['stage'] == 5 and r.get('empty')
        empty.add(r['key'])
a.output.mkdir(parents=True, exist_ok=False)
counts = collections.Counter()
seen = set()
overrides = []
helper_overrides = []
with sqlite3.connect(a.output/'results.sqlite3') as db:
    db.execute('CREATE TABLE results(key TEXT PRIMARY KEY,data BLOB NOT NULL) WITHOUT ROWID')
    db.execute('CREATE TABLE sources(path TEXT PRIMARY KEY,rows INTEGER) WITHOUT ROWID')
    for run in a.runs:
        n = 0
        for r in results(run):
            key = r['key']
            assert key in expected and key not in seen, (run, key)
            seen.add(key)
            if r['status'] == 'missing_metrics' and key in empty:
                assert r['stage'] == 5 and r['exit'] == 0
                assert not r['programs'] and not r['timings'] and not r['finals']
                r['original_status'] = r['status']
                r['status'] = 'empty_shader'
                r['classification_evidence'] = str(a.verified_empty.resolve())
                overrides.append(key)
            if r['status'] == 'empty_shader':
                mains = [v for v in r['programs'] if v['kind'] == 'APPLE9'
                         and (r['stage'] in (1,2,3) or v['stage'] == r['stage'])
                         and not v['stub']]
                if mains:
                    assert r['exit'] == 0 and all(t['ok'] for t in r['timings'])
                    assert not any(x.startswith('Missing final statistics:') for x in r['diagnostics'])
                    r['original_status'] = r['status']
                    r['status'] = 'pass'
                    r['classification_evidence'] = 'Emitted main kernels; empty receipt belongs to one helper variant'
                    helper_overrides.append(key)
            db.execute('INSERT INTO results VALUES(?,?)',
                       (key, zlib.compress(json.dumps(r).encode(), 1)))
            n += 1
            counts[r['status']] += 1
        db.execute('INSERT INTO sources VALUES(?,?)', (str(run.resolve()), n))
        db.commit()
    assert seen == expected, (len(seen), len(expected), len(expected-seen))
    summary = dict(inputs=len(seen), outcomes=dict(counts),
                   populations=a.populations, source_runs=[str(x.resolve()) for x in a.runs],
                   validated_empty_overrides=len(overrides),
                   empty_helper_overrides=len(helper_overrides))
    db.execute('CREATE TABLE reports(name TEXT PRIMARY KEY,data TEXT) WITHOUT ROWID')
    db.execute('INSERT INTO reports VALUES(?,?)', ('summary', json.dumps(summary)))
(a.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary))
