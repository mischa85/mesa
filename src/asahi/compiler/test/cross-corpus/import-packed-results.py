#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Recover interrupted JSONL results from the verified pack into indexed runs."""
import argparse,json,sqlite3,zlib
from pathlib import Path
from packed import Pack
p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();pack=Pack(a.pack);a.output.mkdir(parents=True,exist_ok=False)
with sqlite3.connect(a.output/'results.sqlite3') as db:
 db.execute('CREATE TABLE results(key TEXT PRIMARY KEY,data BLOB NOT NULL) WITHOUT ROWID');n=0
 for line in pack.file(a.run+'/results.jsonl').splitlines():
  try:r=json.loads(line)
  except json.JSONDecodeError:raise RuntimeError('partial result row requires inspection')
  db.execute('INSERT INTO results VALUES(?,?)',(r['key'],zlib.compress(json.dumps(r).encode(),1)));n+=1
for name in ['provenance.json','summary.json']:
 try:(a.output/name).write_bytes(pack.file(a.run+'/'+name))
 except KeyError:pass
print(json.dumps(dict(imported=n,run=a.run)))
