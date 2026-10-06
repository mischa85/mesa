# SPDX-License-Identifier: MIT
"""Content-addressed SQLite corpus storage; no per-module filesystem objects."""
import hashlib,json,sqlite3,zlib
from pathlib import Path

class Pack:
 def __init__(self,path,writable=False):
  self.path=Path(path).resolve()
  self.db=sqlite3.connect(str(self.path) if writable else 'file:'+str(self.path)+'?mode=ro',uri=not writable)
  self.db.execute('PRAGMA cache_size=-262144')
  if writable:
   self.db.execute('PRAGMA journal_mode=WAL')
   self.db.execute('PRAGMA synchronous=NORMAL')
   self.db.executescript('''CREATE TABLE IF NOT EXISTS blobs(sha TEXT PRIMARY KEY,data BLOB NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,sha TEXT,link TEXT,mode INTEGER,mtime_ns INTEGER,size INTEGER) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS entries(population TEXT,key TEXT,sha TEXT,model INTEGER,entry TEXT,push INTEGER,bindings TEXT,PRIMARY KEY(population,key)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS modules(sha TEXT PRIMARY KEY,source TEXT,info TEXT) WITHOUT ROWID;''')
 def blob(self,sha):
  row=self.db.execute('SELECT data FROM blobs WHERE sha=?',(sha,)).fetchone()
  if row is None:raise KeyError(sha)
  data=zlib.decompress(row[0]);assert hashlib.sha256(data).hexdigest()==sha
  return data
 def file(self,path):
  row=self.db.execute('SELECT sha FROM files WHERE path=?',(path,)).fetchone()
  if row is None or row[0] is None:raise KeyError(path)
  return self.blob(row[0])
 def add_blob(self,data):
  sha=hashlib.sha256(data).hexdigest()
  self.db.execute('INSERT OR IGNORE INTO blobs VALUES(?,?)',(sha,zlib.compress(data,1)))
  return sha
 def add_file(self,path,data):
  sha=self.add_blob(data)
  self.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,NULL,0,0,?)',(path,sha,len(data)))
 def keys(self,population):
  if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='entries'").fetchone():
   rows=self.db.execute('SELECT key FROM entries WHERE population=? ORDER BY key',(population,)).fetchall()
   if rows:return [r[0] for r in rows]
  prefix=population+'/meta/'
  return [Path(r[0]).stem for r in self.db.execute('SELECT path FROM files WHERE path>=? AND path<? ORDER BY path',(prefix,prefix+'\uffff')) if r[0].endswith('.txt')]
 def entry(self,population,key):
  if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='entries'").fetchone():
   row=self.db.execute('SELECT sha,model,entry,push,bindings FROM entries WHERE population=? AND key=?',(population,key)).fetchone()
   if row:return dict(sha=row[0],stage=[1,2,4,8,16,32][row[1]],entry=row[2],push=row[3],bindings=json.loads(row[4]))
  lines=self.file(population+'/meta/'+key+'.txt').decode().splitlines();path,stage,entry,push,n=lines[0].split();bindings=[list(map(int,l.split())) for l in lines[1:]];assert len(bindings)==int(n)
  return dict(sha=Path(path).stem,stage=int(stage),entry=entry,push=int(push),bindings=bindings)
 def ingest(self,data,source,population):
  from prepare import reflect
  sha=self.add_blob(data);row=dict(sha256=sha,source=source,bytes=len(data),metadata=[],unsupported_entries=[])
  try:
   info=reflect(data);row.update(info)
   if any(s>=8 for s,b,t,c in info['bindings']) or info['push']>256:row.update(status='unsupported_device_layout',error='Apple9 advertises 8 sets and 256 push-constant bytes')
   elif any(c>65536 for s,b,t,c in info['bindings']):row.update(status='harness_limit',error='descriptor count exceeds replay bound')
   else:
    for model,name in info['entries']:
     if model not in range(6):row['unsupported_entries'].append((model,name));continue
     key=sha+'-'+str(model)+'-'+hashlib.sha1(name.encode()).hexdigest()[:12]
     self.db.execute('INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?,?,?)',(population,key,sha,model,name,info['push'],json.dumps(info['bindings'])))
     row['metadata'].append(key)
    row['status']='prepared' if row['metadata'] else 'unsupported_device_stage'
  except Exception as e:row.update(status='reflection_failure',error=str(e))
  self.db.execute('INSERT OR IGNORE INTO modules VALUES(?,?,?)',(sha,source,json.dumps(row)))
  return row
 def frame(self,population,key):
  r=self.entry(population,key);data=self.blob(r['sha']);header=f"{key} {r['stage']} {r['entry']} {r['push']} {len(r['bindings'])} {len(data)}\n".encode();bindings=''.join('%d %d %d %d\n'%tuple(b) for b in r['bindings']).encode()
  return header+bindings+data,r

def results(path):
 path=Path(path)
 if path.is_dir():path=path/'results.sqlite3'
 if path.suffix=='.jsonl':
  with path.open() as f:
   for line in f:yield json.loads(line)
 else:
  with sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True) as db:
   for data, in db.execute('SELECT data FROM results ORDER BY key'):yield json.loads(zlib.decompress(data))
