"""Run real offline materializer on multi-part fixture payloads; no devices/network."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False);rows=[]
for mode in ('fresh','valid','corrupt_target','corrupt_part','missing_part'):
 case=out/mode;case.mkdir();payload=case/'payload';payload.mkdir()
 shutil.copy(root/'prepare_payload.sh',case/'prepare_payload.sh')
 data=b'installer ordinary Git payload\0'*500
 parts=[data[:7000],data[7000:]]
 for i,part in enumerate(parts):(payload/f'model.part{i:03}').write_bytes(part)
 target=case/'models/model.bin'
 if mode in ('valid','corrupt_target'):
  target.parent.mkdir();target.write_bytes(data if mode=='valid' else b'bad')
 before=target.stat().st_mtime_ns if target.exists() else None
 digest=hashlib.sha256(data).hexdigest()
 (payload/'targets.tsv').write_text(f'{digest}\tmodels/model.bin\tmodel\n')
 (payload/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(payload.iterdir())))
 if mode=='corrupt_part':(payload/'model.part000').write_bytes(b'bad')
 if mode=='missing_part':(payload/'model.part001').unlink()
 result=subprocess.run(['bash',str(case/'prepare_payload.sh')],capture_output=True,text=True,cwd=case)
 (case/'output.log').write_text(result.stdout+result.stderr)
 if mode in ('corrupt_part','missing_part'):assert result.returncode and not target.exists()
 else:
  assert result.returncode==0,result.stderr
  assert target.read_bytes()==data
  if mode=='valid':assert target.stat().st_mtime_ns==before
 assert not list(case.rglob('*.tmp'))
 rows.append({'case':mode,'status':'PASS','returncode':result.returncode})
(out/'result.json').write_text(json.dumps({'status':'PASS','scope':'real local materialization with multipart fixtures; no devices/network','cases':rows},indent=2)+'\n')
print('PASS',len(rows),'ordinary Git payload scenarios:',out)
