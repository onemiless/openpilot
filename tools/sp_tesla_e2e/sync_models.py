#!/usr/bin/env python3
"""Content-addressed official model preparation; partial files never activate."""
import concurrent.futures, hashlib, json, os, shutil, threading
from pathlib import Path
from urllib.parse import quote, unquote
import requests
ROOT=Path('artifacts/sp-tesla-migration/models')
MANIFEST=ROOT/'selected.json'
CACHE_ROOTS=[Path('/Users/mile/Desktop/mo-op/releases'),Path('/Users/mile/Desktop/mo-op/artifacts'),Path('/Users/mile/Desktop/mo-op/tmp'),Path('/Users/mile/.cache')]
lock=threading.Lock();records=json.loads((ROOT/'chunk-receipt.json').read_text()) if (ROOT/'chunk-receipt.json').exists() else []
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(4*1024*1024),b''):h.update(data)
 return h.hexdigest()
def get_chunk(bundle,artifact,chunk,candidates):
 dest=ROOT/'files'/bundle['short_name']/chunk['file_name'];dest.parent.mkdir(parents=True,exist_ok=True)
 row={'model':bundle['short_name'],'file':chunk['file_name'],'sha256':chunk['sha256'],'path':str(dest)}
 if dest.is_file() and digest(dest)==chunk['sha256']:row.update(action='reuse-prepared',bytes=dest.stat().st_size)
 else:
  match=next((p for p in candidates.get(chunk['file_name'],[]) if digest(p)==chunk['sha256']),None)
  if match:
   shutil.copyfile(match,dest);row.update(action='reuse-local',source=str(match),bytes=dest.stat().st_size)
  else:
   part=dest.with_suffix(dest.suffix+'.partial');offset=part.stat().st_size if part.exists() else 0
   base=artifact['download_uri']['url'].rsplit('/',1)[0]
   uri=base+'/'+quote(chunk['file_name'],safe='')
   response=requests.get(uri,headers={'Range':f'bytes={offset}-'} if offset else {},stream=True,timeout=(15,60));response.raise_for_status()
   append=offset>0 and response.status_code==206;downloaded=0
   with part.open('ab' if append else 'wb') as f:
    for data in response.iter_content(1024*1024):f.write(data);downloaded+=len(data)
   if digest(part)!=chunk['sha256']:part.unlink();raise ValueError('bad chunk hash '+chunk['file_name'])
   os.replace(part,dest);row.update(action='download',bytes=dest.stat().st_size,downloaded_bytes=downloaded)
 with lock:
  records.append(row);(ROOT/'chunk-receipt.json').write_text(json.dumps(records,indent=2)+'\n')
 print(row['model'],row['file'],row['action'],flush=True)
 return row

def main():
 m=json.loads(MANIFEST.read_text());names={c['file_name'] for b in m['bundles'] for model in b['models'] for c in model['artifact']['chunks']}
 candidates={}
 for root in CACHE_ROOTS:
  if root.exists():
   for p in root.rglob('*.chunk*'):
    if p.name in names:candidates.setdefault(p.name,[]).append(p)
 # Whole-package matches are reused before requesting their chunks.
 for b in m['bundles']:
  for model in b['models']:
   a=model['artifact'];whole=ROOT/'files'/b['short_name']/a['file_name']
   candidates_whole=[p for root in CACHE_ROOTS if root.exists() for p in root.rglob(a['file_name'])]
   match=next((p for p in candidates_whole if digest(p)==a['download_uri']['sha256']),None)
   if match:
    whole.parent.mkdir(parents=True,exist_ok=True)
    if match.resolve()!=whole.resolve():shutil.copyfile(match,whole)
    # Split using recorded chunk size (all non-final chunks are 45 MiB).
    with whole.open('rb') as f:
     for chunk in a['chunks']:
      dest=whole.parent/chunk['file_name'];data=f.read(45 * 1024 * 1024)
      if hashlib.sha256(data).hexdigest()!=chunk['sha256']:break
      dest.write_bytes(data)
 print('local candidate chunks',sum(map(len,candidates.values())),flush=True)
 tasks=[(b,model['artifact'],c,candidates) for b in m['bundles'] for model in b['models'] for c in model['artifact']['chunks']]
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for future in concurrent.futures.as_completed([pool.submit(get_chunk,*t) for t in tasks]):future.result()
 bundles=[]
 for b in m['bundles']:
  for model in b['models']:
   a=model['artifact'];whole=ROOT/'files'/b['short_name']/a['file_name'];temp=whole.with_suffix('.assembling');h=hashlib.sha256()
   with temp.open('wb') as out:
    for c in a['chunks']:
     with (whole.parent/c['file_name']).open('rb') as f:
      for block in iter(lambda:f.read(4*1024*1024),b''):out.write(block);h.update(block)
   assert h.hexdigest()==a['download_uri']['sha256'];os.replace(temp,whole)
   bundles.append({'model':b['short_name'],'display_name':b['display_name'],'ref':b['ref'],'tinygrad_ref':m['tinygrad_ref'],'path':str(whole),'sha256':h.hexdigest(),'bytes':whole.stat().st_size,'chunks':len(a['chunks'])})
 (ROOT/'bundle-receipt.json').write_text(json.dumps(bundles,indent=2)+'\n')
if __name__=='__main__':main()
