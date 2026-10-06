import time,resource,subprocess,sys,json,os
from pathlib import Path
out=Path(sys.argv[1]);start=time.perf_counter();load=os.getloadavg();r=subprocess.run(sys.argv[2:]);elapsed=time.perf_counter()-start;u=resource.getrusage(resource.RUSAGE_CHILDREN)
out.write_text(json.dumps(dict(wall=elapsed,user=u.ru_utime,system=u.ru_stime,maxrss_kb=u.ru_maxrss,exit=r.returncode,load_before=load,load_after=os.getloadavg()),indent=2)+'\n');raise SystemExit(r.returncode)
