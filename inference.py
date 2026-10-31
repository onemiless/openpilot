#!/usr/bin/env python3
"""Fixed big driving model, synthetic model inputs, real USB AMD GPU execution."""
import base64
import hashlib
import json
import os
from pathlib import Path
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parent
os.environ['DEV']='USB+AMD:LLVM'
os.environ['GMMU']='0'
os.environ['PYTHONPATH']=str(ROOT)
from flash import save

def check():
  if sys.version_info < (3,11):
    raise RuntimeError('Python 3.11+ required; system will not be upgraded')
  import numpy
  import tinygrad
  from tinygrad.runtime.autogen import libusb, llvm
  # Resolve the actual backend symbols without opening a USB device.
  getattr(libusb.dll,'libusb_get_version')
  getattr(llvm.dll,'LLVMContextCreate')

def main(report_path):
  report={'status':'LOADING','backend':'USB+AMD:LLVM','seconds':0,'runs':0,'input':'fixed synthetic tensors; no camera'}
  save(report_path,report)
  try:
    check()
    import numpy as np
    from tinygrad import Tensor, Device
    from tinygrad.runtime.autogen.am import fw
    import tinygrad.helpers
    def local_fw(path,name,expected):
      data=(ROOT/'firmware'/path/name).read_bytes()
      if hashlib.sha256(data).hexdigest()!=expected:
        raise RuntimeError(f'GPU firmware hash mismatch: {name}')
      return data
    tinygrad.helpers.fetch_fw=local_fw
    from model_loader import load_model
    started=time.monotonic()
    bundle=load_model(str(ROOT/'models/big_driving_tinygrad.pkl'),verify=True,cache=False)
    specs=bundle['input_specs'];out_specs=bundle['output_specs']
    if any(device!='AMD' for _,_,device in (*specs.values(),*out_specs.values())):
      raise RuntimeError('Bundled big model must target AMD exclusively')
    inputs={name:Tensor(np.zeros(shape,dtype=dtype),device=device).realize() for name,(shape,dtype,device) in specs.items()}
    outputs={name:Tensor(np.zeros(shape,dtype=dtype),device=device).realize() for name,(shape,dtype,device) in out_specs.items()}
    state_pairs={name:f'next_{name}' for name in specs if f'next_{name}' in outputs}
    slices=pickle.loads(base64.b64decode(bundle['metadata']['metadata']['output_slices']))
    plan_slice=slices['plan']
    run=bundle['run']
    def once():
      start=time.monotonic()
      run(output_buffers=outputs,**inputs)
      values={name:value.numpy().copy() for name,value in outputs.items()}
      Device['AMD'].synchronize()
      if Device['AMD'].error_state.host.view(fmt='q')[0]:
        raise RuntimeError('USB GPU error state')
      if any(not np.all(np.isfinite(value)) for value in values.values()):
        raise RuntimeError('Non-finite model output')
      if values['outputs'][...,plan_slice].size==0:
        raise RuntimeError('Empty plan output')
      for name,next_name in state_pairs.items():
        inputs[name].assign(outputs[next_name]).realize()
      Device['AMD'].synchronize()
      return time.monotonic()-start,values
    once()
    report['load_and_warmup_seconds']=time.monotonic()-started
    start=time.monotonic();latencies=[];saved_seconds=-1
    while time.monotonic()-start<60:
      latency,values=once();latencies.append(latency)
      seconds=time.monotonic()-start
      if seconds-saved_seconds>=1:
        report.update(status='RUNNING',seconds=seconds,runs=len(latencies))
        save(report_path,report);saved_seconds=seconds
    elapsed=time.monotonic()-start
    report.update(status='PASS',seconds=elapsed,runs=len(latencies),hz=len(latencies)/elapsed,
                  mean_ms=float(np.mean(latencies)*1000),p95_ms=float(np.percentile(latencies,95)*1000),max_ms=max(latencies)*1000,
                  plan_present=True,finite=True,
                  output_sha256={name:hashlib.sha256(value.tobytes()).hexdigest() for name,value in values.items()})
  except Exception as error:
    report.update(status='FAIL',error=repr(error))
    raise
  finally:
    save(report_path,report)

if __name__=='__main__':
  if sys.argv[1:] == ['--check']: check()
  else: main(Path(sys.argv[1]))
