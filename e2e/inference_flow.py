"""Run actual inference entry in subprocesses with fake tensor/GPU and clock, never hardware."""
import base64
import json
from pathlib import Path
import pickle
import runpy
import subprocess
import sys
import types

root=Path(__file__).resolve().parents[1]
if len(sys.argv)>1 and sys.argv[1]=='--child':
  import numpy as np
  case,report=sys.argv[2:]
  sys.path.insert(0,str(root))
  class Tensor:
    def __init__(self,value,device): self.value=value;self.device=device
    def realize(self): return self
    def numpy(self): return self.value
    def assign(self,other): self.value[:]=other.value;return self
  class GPU:
    error_state=types.SimpleNamespace(host=types.SimpleNamespace(view=lambda **kw:[1 if case=='gpu_error' else 0]))
    def synchronize(self): pass
  gpu=GPU()
  tinygrad=types.ModuleType('tinygrad');tinygrad.Tensor=Tensor;tinygrad.Device={'AMD':gpu}
  modules={'tinygrad':tinygrad,'tinygrad.helpers':types.ModuleType('tinygrad.helpers'),
           'tinygrad.engine':types.ModuleType('tinygrad.engine'),
           'tinygrad.engine.realize':types.SimpleNamespace(lower_and_compile=lambda x:x),
           'tinygrad.runtime':types.ModuleType('tinygrad.runtime'),
           'tinygrad.runtime.autogen':types.SimpleNamespace(libusb=types.SimpleNamespace(dll=types.SimpleNamespace(libusb_get_version=0)),
                                                         llvm=types.SimpleNamespace(dll=types.SimpleNamespace(LLVMContextCreate=0))),
           'tinygrad.runtime.autogen.am':types.SimpleNamespace(fw={})}
  tinygrad.helpers=modules['tinygrad.helpers']
  sys.modules.update(modules)
  class Run:
    captured=types.SimpleNamespace(_linear=[])
    def __call__(self,output_buffers,**inputs):
      assert output_buffers['next_state'] is not inputs['state']
      if case=='exception': raise RuntimeError('transfer failed')
      output_buffers['outputs'].value[:]=np.nan if case=='nan' else 1
  bundle={'input_specs':{'state':((1,2),'float32','AMD')},
          'output_specs':{'outputs':((1,4),'float32','AMD'),'next_state':((1,2),'float32','AMD')},
          'metadata':{'metadata':{'output_slices':base64.b64encode(pickle.dumps({'plan':slice(0,2)})).decode()}},'run':Run()}
  if case=='wrong_backend': bundle['input_specs']['state']=((1,2),'float32','CPU')
  sys.modules['model_loader']=types.SimpleNamespace(load_model=lambda *args,**kwargs:bundle)
  # Clock advances per synchronization boundary; tests validate the real 60-second loop without waiting a minute per fault.
  import time
  elapsed=[0]
  def clock(): elapsed[0]+=.25;return elapsed[0]
  time.monotonic=clock
  import flash
  original_save=flash.save
  def record_save(path,value):
    if path==Path(report):
      with Path(report+'.progress.jsonl').open('a') as events:events.write(json.dumps({'status':value['status'],'seconds':value['seconds']})+'\n')
    original_save(path,value)
  flash.save=record_save
  sys.argv=[str(root/'inference.py'),report]
  runpy.run_path(sys.argv[0],run_name='__main__')
else:
  out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False);cases=[]
  for case in ('normal','nan','exception','gpu_error','wrong_backend'):
    report=out/(case+'.json')
    result=subprocess.run([sys.executable,__file__,'--child',case,str(report)],capture_output=True,text=True)
    (out/(case+'.log')).write_text(result.stdout+result.stderr)
    data=json.loads(report.read_text())
    assert (result.returncode==0)==(case=='normal'),result.stderr
    assert data['status']==('PASS' if case=='normal' else 'FAIL')
    if case=='normal':
      history=[json.loads(line) for line in Path(str(report)+'.progress.jsonl').read_text().splitlines()]
      assert history[0]['status']=='LOADING' and history[-1]['status']=='PASS'
      assert any(row['status']=='RUNNING' and row['seconds']>0 for row in history)
    if case=='normal':assert data['seconds']>=60 and data['runs']>1 and data['finite'] and data['plan_present']
    else:assert 'error' in data
    cases.append({'case':case,'status':'PASS','returncode':result.returncode})
  (out/'result.json').write_text(json.dumps({'status':'PASS','scope':'real inference entry with simulated GPU/clock, no real model execution','cases':cases},indent=2)+'\n')
  print('PASS',len(cases),'inference-entry scenarios:',out)
