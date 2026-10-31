"""Offline ordinary Git-index reconstruction E2E; no network or hardware."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
paths=subprocess.check_output(['git','ls-files','runtime','payload','prepare_payload.sh'],cwd=root,text=True)
subprocess.run(['git','checkout-index','--prefix='+str(out)+'/', '--stdin'],input=paths,text=True,cwd=root,
               env={**os.environ,'GIT_LFS_SKIP_SMUDGE':'1'},check=True)
subprocess.run(['bash',str(out/'prepare_payload.sh')],cwd=out,check=True)
count=0
for line in (out/'runtime/SHA256SUMS').read_text().splitlines():
 expected,name=line.split('  ',1)
 with (out/'runtime'/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==expected,name
 count+=1
(out/'result.json').write_text(json.dumps({'status':'PASS','scope':'offline staged ordinary Git checkout + local assembly, no hardware or network',
                                        'payload_files_checked':count},indent=2)+'\n')
print('PASS offline ordinary Git checkout:',count,'payload hashes:',out)
