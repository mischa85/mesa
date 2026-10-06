import os
import sys,json,re,io,collections
from pathlib import Path
root=Path(os.environ.get('CENSUS_OUTPUT',Path(__file__).resolve().parent))
sys.path.insert(0,os.environ['CENSUS_PARSER_LIBRARY'])
import stream_compare_lib as sc
ns={'__file__':sc.__file__};exec(Path(sc.__file__).read_text().replace("if cur['kind'] == 'APPLE9':",'if True:'),ns)
ins=[];nir=[];meta={};choice={};current={};loops={};name=sys.argv[1]
def fields(s):return {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',s)}
def loopids(l):
 v=re.search(r'loops=([0-9,-]+)',l)[1];return [] if v=='-' else [int(x) for x in v.split(',')]
def getloop(h):
 return loops.setdefault(h,dict(hoisted=collections.Counter(),hoisted_words=0,nir=collections.Counter(),static=collections.Counter(),weighted=collections.Counter()))
def lines():
 global ins,nir,meta,choice,loops
 for l in io.TextIOWrapper(sys.stdin.buffer,errors='replace'):
  if l.startswith('VERTEX_AUDIT_PIPELINE'):current.update(fields(l));current['hash']=re.search(r'hash=(\w+)',l)[1]
  if l.startswith('LOOP_META '):
   n=fields(l);getloop(n['header'])['depth']=n['depth']
  if l.startswith('LOOP_PEAK '):
   n=fields(l);getloop(n['header'])['pre_spill_half']=n['half']
  if l.startswith('LOOP_HOIST '):
   n=fields(l);v=getloop(n['header']);v['hoisted'][re.search(r'op=(\w+)',l)[1]]+=1;v['hoisted_words']+=n['words']
  if l.startswith('LOOP_NIR '):
   for h in loopids(l):getloop(h)['nir'][re.search(r'op=(\w+)',l)[1]]+=1
  if l.startswith('LICM_CHOICE'):choice=fields(l)
  if l.startswith('LATENCY_NIR '):
   n=fields(l);n['op']=re.search(r'op=(\w+)',l)[1];nir.append(n)
  if l.startswith('LATENCY_BEGIN '):meta=fields(l);ins=[]
  if l.startswith('LATENCY_INS '):ins.append({**fields(l),'loops':loopids(l)})
  if 'ERROR' in l or 'Assertion' in l:print(l,file=sys.stderr,end='')
  yield l
with (root/(name+'.jsonl')).open('w') as f:
 i=0
 for p in ns['programs'](lines()):
  if p['name']=='stub VS':ins=[];nir=[];choice={};continue
  assert len(ins)==len(p['asm']), (i,len(ins),len(p['asm']))
  m=sc.metrics(p);m.update(saves=p['stats']['saves'],fills=p['stats']['fills'],scratch=p['stats']['scratch'],at96=int(p['stats']['gprs']>=96))
  row=dict(stage={0:'vertex',4:'fragment',5:'compute'}.get(p['stage'],str(p['stage'])),name=p['name'],gprs=p['stats']['gprs'],**{k:int(m[k]) for k in ('instrs','swaps','copies','spills','saves','fills','scratch','at96')})
  weighted=collections.Counter();ops=collections.defaultdict(collections.Counter)
  for I,A in zip(ins,p['asm']):
   w=8**min(I['depth'],6);weighted['instructions']+=w;ops[I['depth']][A['op']]+=1
   for h in I['loops']:
    v=getloop(h);v['static']['instructions']+=1;v['weighted']['instructions']+=w
    if A['op'] in ['SPILL_STORE','SPILL_LOAD']:
     k='saves' if A['op']=='SPILL_STORE' else 'fills';v['static'][k]+=1;v['weighted'][k]+=w
   if A['op']=='SPILL_STORE':weighted['saves']+=w
   if A['op']=='SPILL_LOAD':weighted['fills']+=w
  f.write(json.dumps(dict(row=i,kind=p['kind'],metrics=row,pressure=meta,weighted=weighted,ops=ops,nir=nir,choice=choice,loops=loops,pipeline=dict(current)))+'\n');f.flush()
  ins=[];nir=[];meta={};choice={};loops={}
  if p['kind']=='APPLE9':i+=1
print(name,i)
