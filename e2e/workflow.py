"""Host lifecycle E2E. Real persistent workflow; injected dock and inference boundaries."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import station

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
records = []
for scenario in ('normal', 'restart_wait', 'reuse_address', 'wrong_board', 'verify_error', 'inference_error', 'flash_error', 'restart_write', 'preflight_error'):
  root = out / scenario
  root.mkdir()
  calls = []
  device = {'path': '/sys/mock/1-1', 'token': 'boot:inode:1'}
  def preflight():
    calls.append('preflight')
    if scenario == 'preflight_error': raise RuntimeError('missing model')
  def flash(path, job):
    calls.append('flash')
    if scenario == 'flash_error': raise RuntimeError('PROGRAM ACK lost')
    return {'status': 'WRITTEN_TRIPLE_VERIFIED_PENDING_POWER_CYCLE', 'uid_reads': ['1234']*3}
  def verify(path, job):
    calls.append('verify')
    if scenario in ('wrong_board', 'verify_error'): raise RuntimeError(scenario)
  def infer(job):
    calls.append('inference')
    if scenario == 'inference_error': raise RuntimeError('NaN')
    return {'status': 'PASS', 'seconds': 60, 'runs': 120, 'backend': 'USB+AMD:LLVM'}
  station.preflight, station.flash, station.verify, station.infer = preflight, flash, verify, infer
  station.devices = lambda: [device]
  if scenario == 'restart_write':
    job = root/'interrupted'; job.mkdir()
    station.save(root/'state.json', {'stage':'WRITING','device':device,'job':str(job)})
  station.tick(root)
  state = json.loads((root/'state.json').read_text())
  if scenario in ('flash_error','restart_write','preflight_error'):
    assert state['stage']=='FAILED' and 'verify' not in calls and 'inference' not in calls
  else:
    assert state['stage']=='WAIT_POWER_CYCLE'
    for _ in range(3): station.tick(root)
    assert calls.count('flash')==1 and 'verify' not in calls
    if scenario != 'reuse_address':
      station.devices = lambda: []
      station.tick(root)
    else:
      device = dict(device, token='boot:new-inode:1')
    station.devices = lambda: [device]
    station.tick(root)
    state = json.loads((root/'state.json').read_text())
    expected = 'FAILED' if scenario in ('wrong_board','verify_error','inference_error') else 'DONE'
    assert state['stage']==expected
    assert state['flash']=='PASS'
    assert calls.count('flash')==1
    if scenario in ('wrong_board','verify_error'): assert 'inference' not in calls
    for _ in range(3): station.tick(root)
    assert calls.count('flash')==1
    if expected=='DONE': assert state['inference']=='PASS'
  report=json.loads((Path(state['job'])/'report.json').read_text())
  assert report['stage']==state['stage']
  records.append({'scenario':scenario,'calls':calls,'status':'PASS'})
# Removal after terminal result enables exactly one new automatic job.
station.devices=lambda: []
station.tick(root)
assert json.loads((root/'state.json').read_text())['stage']=='IDLE'
(out/'result.json').write_text(json.dumps({'status':'PASS','scope':'host lifecycle simulation; no USB/GPU', 'cases':records},indent=2)+'\n')
for path in out.rglob('*'):
  if path.is_file(): pass
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
print('PASS',len(records),'lifecycle scenarios:',out)
