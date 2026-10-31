#!/usr/bin/env python3
"""Development-only reproducible download/extraction. Never called by the device launchers."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def build(lock, output, cache):
  output.mkdir(parents=True,exist_ok=False)
  cache.mkdir(parents=True,exist_ok=True)
  for source in lock['archives']:
    archive=cache/source['archive']
    if not archive.exists():
      with urllib.request.urlopen(source['url'],timeout=90) as response,archive.open('wb') as dest:
        shutil.copyfileobj(response,dest)
    if hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=source['sha256']:
      raise RuntimeError('Archive hash mismatch: '+source['archive'])
    if source['archive'].startswith('cpython-'):
      with tarfile.open(archive) as tar:
        members=[m for m in tar.getmembers() if not any(m.name.startswith('python/'+x+'/') for x in ('share','include'))]
        tar.extractall(output,members=members,filter='data')
    elif archive.suffix=='.whl':
      (output/'numpy').mkdir()
      with zipfile.ZipFile(archive) as wheel:wheel.extractall(output/'numpy')
    else:
      member=next(n for n in subprocess.check_output(['ar','t',str(archive)],text=True).splitlines() if n.startswith('data.tar'))
      data=subprocess.check_output(['ar','p',str(archive),member])
      destination=output/source['target'];destination.mkdir(exist_ok=True)
      with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as tar:
        for item in tar.getmembers():
          path=Path(item.name)
          if '.so' in path.name and ('lib/' in str(path) or 'lib64/' in str(path)):
            target=destination/path.name
            if item.isfile():target.write_bytes(tar.extractfile(item).read())
            elif item.issym():target.symlink_to(Path(item.linkname).name)
          if path.name=='fuser' and item.isfile():
            (output/'tools').mkdir(exist_ok=True)
            target=output/'tools/fuser';target.write_bytes(tar.extractfile(item).read());target.chmod(0o755)
          if path.name=='copyright' and item.isfile():
            (output/'licenses').mkdir(exist_ok=True)
            (output/'licenses'/source['package']).write_bytes(tar.extractfile(item).read())
  (output/'llvm/libLLVM.so').symlink_to('libLLVM.so.19.1')
  for relative in ('include','share','lib/python3.11/site-packages','lib/python3.11/ensurepip','lib/python3.11/idlelib',
                   'lib/python3.11/tkinter','lib/python3.11/turtledemo','lib/python3.11/test','lib/pkgconfig',
                   'lib/itcl4.3.5','lib/tcl9','lib/tcl9.0','lib/thread3.0.4','lib/tk9.0'):
    shutil.rmtree(output/'python'/relative,ignore_errors=True)
  for path in (output/'python/bin').iterdir():
    if path.name not in ('python3','python3.11'):path.unlink()
  for pattern in ('lib/libtcl*','lib/libtk*','lib/python3.11/lib-dynload/_tkinter*','lib/python3.11/lib-dynload/_test*',
                  'lib/python3.11/lib-dynload/_crypt*','lib/python3.11/lib-dynload/_dbm*'):
    for path in (output/'python').glob(pattern):path.unlink()
  for name in ('libicui18n','libicuio','libicutest','libicutu'):
    for path in (output/'llvm').glob(name+'*'):path.unlink()
  for name in ('tzdata','debconf'):
    (output/'licenses'/name).unlink(missing_ok=True)
  for path in output.rglob('__pycache__'):shutil.rmtree(path)
  for path in (output/'numpy').rglob('tests'):
    if path.is_dir():shutil.rmtree(path)
  (output/'sources.json').write_text(json.dumps(lock,indent=2)+'\n')
  (output/'SHA256SUMS').write_text(''.join(f'{hashlib.file_digest(p.open("rb"),"sha256").hexdigest()}  {p.relative_to(output)}\n'
                                        for p in sorted(output.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))

if __name__=='__main__':
  lock=json.loads((ROOT/'runtime/sources.json').read_text())
  build(lock,Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
