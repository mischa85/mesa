#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pin public sample sources; retain only shader files and upstream licenses."""
import argparse,hashlib,io,json,tarfile,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
for name,repo,branch,prefixes in [('willems','SaschaWillems/Vulkan','master',('shaders/glsl/','shaders/hlsl/','shaders/base/')),('vkmark','vkmark/vkmark','master',('data/shaders/',))]:
 d=a.output/name;d.mkdir(exist_ok=False)
 req=urllib.request.Request('https://api.github.com/repos/'+repo+'/commits/'+branch,headers={'User-Agent':'asahi-compiler-corpus'})
 info=json.load(urllib.request.urlopen(req));rev=info['sha'];files={}
 url='https://codeload.github.com/'+repo+'/tar.gz/'+rev
 with tarfile.open(d/'sources.tar.gz','w:gz') as packed,urllib.request.urlopen(url) as response,tarfile.open(fileobj=response,mode='r|gz') as tar:
  for member in tar:
   rel=member.name.partition('/')[2]
   if not member.isfile() or not (rel.startswith(prefixes) or Path(rel).name.lower().startswith(('license','copying'))):continue
   if '..' in Path(rel).parts:raise ValueError(rel)
   data=tar.extractfile(member).read();item=tarfile.TarInfo(rel);item.size=len(data);item.mode=0o644;packed.addfile(item,io.BytesIO(data));files[rel]=hashlib.sha256(data).hexdigest()
 (d/'source.json').write_text(json.dumps(dict(repository='https://github.com/'+repo,commit=rev,archive=url,files=files),indent=2)+'\n')
 print(name,rev,len(files),flush=True)
