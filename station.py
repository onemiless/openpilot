#!/usr/bin/env python3
"""Single-purpose R2 flashing station. No driving or system update entry point."""
import fcntl
import hashlib
import json
import os
import select
from pathlib import Path
import subprocess
import sys
import time
import uuid
from flash import Session, execute, save, sha
from spi_core import SPI

ROOT = Path(__file__).resolve().parent
PAIRS = {(0x3801,1),(0xadd1,1),(0x174c,0x2463),(0x174c,0x2464)}

def devices():
  found = []
  for path in Path('/sys/bus/usb/devices').iterdir():
    try:
      pair = tuple(int((path/name).read_text(),16) for name in ('idVendor','idProduct'))
      if pair in PAIRS:
        token = ':'.join((Path('/proc/sys/kernel/random/boot_id').read_text().strip(),str(path.stat().st_ino),
                          (path/'busnum').read_text().strip(),(path/'devnum').read_text().strip()))
        found.append({'path':str(path.resolve()),'token':token})
    except FileNotFoundError:
      continue  # sysfs entries can disappear while enumerating.
  return found

def preflight():
  manifest = json.loads((ROOT/'assets.json').read_text())
  for name, expected in manifest['sha256'].items():
    with (ROOT/name).open('rb') as source:
      actual = hashlib.file_digest(source,'sha256').hexdigest()
    if actual != expected:
      raise RuntimeError(f'Asset hash mismatch: {name}')
  subprocess.run([sys.executable,str(ROOT/'inference.py'),'--check'],check=True,timeout=30)
  return sha((ROOT/'assets.json').read_bytes())

def flash(path, job):
  with Session(Path(path)) as transport:
    return execute(SPI(transport),job,write=True)

def verify(path, job):
  before = json.loads((job/'result.json').read_text())
  with Session(Path(path)) as transport:
    spi = SPI(transport)
    spi.snapshot()
    extra={a:transport.control(False,a)[0] for a in (0xcc33,0xc805)}
    try:
      spi.wr(0xcc33,4);spi.wr(0xca81,spi.rd(0xca81)[0]|1);spi.wr(0xc805,2);spi.wr(0xc8a6,4)
      if spi.uid() != before['uid_reads'][0]:
        raise RuntimeError('Reconnected dock UID differs from the flashed dock')
      for index in range(3):
        data = spi.read()
        save(job/f'activated-full-{index}.bin',data)
        if sha(data) != before['target_sha256']:
          raise RuntimeError('Post-reconnect full Flash mismatch')
    finally:
      try:
        spi.cleanup()
      finally:
        for address,value in extra.items():
          if transport.control(False,address)[0]!=value:
            transport.control(True,address,value)
        if any(transport.control(False,a)[0]!=v for a,v in extra.items()):
          raise RuntimeError('Post-reconnect register restoration failed')

def infer(job):
  subprocess.run([sys.executable,str(ROOT/'inference.py'),str(job/'inference.json')],check=True,timeout=600)
  return json.loads((job/'inference.json').read_text())

def publish(root, state):
  save(root/'state.json',state)
  if 'job' in state:
    job = Path(state['job'])
    save(job/'report.json',state)
    save(job/'SHA256SUMS',''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in sorted(job.iterdir())
                                if p.is_file() and p.name!='SHA256SUMS').encode())
  print(json.dumps(state,ensure_ascii=False),flush=True)

def tick(root):
  state_path = root/'state.json'
  state = json.loads(state_path.read_text()) if state_path.exists() else {'stage':'IDLE'}
  connected = devices()
  if state['stage']=='IDLE':
    if len(connected)!=1:
      return
    job = root/str(uuid.uuid4());job.mkdir()
    state = {'stage':'PREFLIGHT','device':connected[0],'job':str(job),'flash':'NOT_RUN','inference':'NOT_RUN'}
    publish(root,state)
    try:
      state['assets_manifest_sha256']=preflight()
      state['stage']='WRITING';publish(root,state)
      result = flash(state['device']['path'],job)
      if result['status']!='WRITTEN_TRIPLE_VERIFIED_PENDING_POWER_CYCLE':
        raise RuntimeError('Flash did not complete')
      state.update(stage='WAIT_POWER_CYCLE',flash='PASS',disconnected=False,
                   message='同时断开底座12V和USB约10秒，再接回；随后自动校验并推理60秒。')
    except Exception as error:
      if state['stage']=='WRITING': state['flash']='FAIL'
      if state['stage']=='INFERENCE': state['inference']='FAIL'
      state.update(stage='FAILED',error=repr(error))
    publish(root,state)
    return
  if state['stage'] in ('PREFLIGHT','WRITING','VERIFYING','INFERENCE'):
    state.update(stage='FAILED',error='Interrupted operation; no automatic retry')
    publish(root,state)
    return
  if state['stage'] in ('DONE','FAILED'):
    if not connected or (len(connected)==1 and connected[0]['token']!=state['device']['token']):
      publish(root,{'stage':'IDLE'})
    return
  if state['stage']=='WAIT_POWER_CYCLE':
    if not connected:
      if not state['disconnected']:
        state['disconnected']=True;publish(root,state)
      return
    if len(connected)!=1 or (not state['disconnected'] and connected[0]['token']==state['device']['token']):
      return
    state['device']=connected[0]
    job = Path(state['job'])
    try:
      state['stage']='VERIFYING';publish(root,state)
      verify(state['device']['path'],job)
      state.update(stage='INFERENCE',activation_readback='PASS');publish(root,state)
      result = infer(job)
      if result['status']!='PASS' or result['seconds']<60 or result['runs']<1 or result['backend']!='USB+AMD:LLVM':
        raise RuntimeError('60-second USB GPU inference did not pass')
      state.update(stage='DONE',inference='PASS',message='R2刷写、回读校验、60秒大模型推理完成。')
    except Exception as error:
      if state['stage']=='WRITING': state['flash']='FAIL'
      if state['stage']=='INFERENCE': state['inference']='FAIL'
      state.update(stage='FAILED',error=repr(error))
    publish(root,state)

def main():
  root = Path('/data/sp-flasher');root.mkdir(parents=True,exist_ok=True)
  with (root/'station.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read_fd,write_fd=os.pipe()
    with os.fdopen(read_fd,'rb',buffering=0) as ready, subprocess.Popen(
      [sys.executable,str(ROOT/'status_screen.py'),'--state',str(root/'state.json'),'--ready-fd',str(write_fd)],
      pass_fds=(write_fd,)) as screen:
      os.close(write_fd)
      try:
        if not select.select([ready],[],[],15)[0] or ready.read(1)!=b'1':
          raise RuntimeError('状态屏未就绪，未开始刷写')
        while True:
          if screen.poll() is not None:raise RuntimeError('状态屏已退出，停止接受新任务')
          tick(root)
          time.sleep(1)
      finally:
        screen.terminate();screen.wait(timeout=5)

if __name__=='__main__':
  main()
