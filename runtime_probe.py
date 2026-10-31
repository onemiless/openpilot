"""Offline dependency probes. No USB context, device discovery or system installation."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
IR = 'target triple = "amdgcn-amd-amdhsa"\ndefine amdgpu_kernel void @runtime_check() { ret void }\n'

def python():
  if sys.version_info < (3,11):
    raise RuntimeError('Python 3.11+ required')
  import ctypes
  import fcntl
  import numpy as np
  values=np.array([1.,2.,3.],dtype=np.float32)
  if not np.isfinite(values).all() or float(values@values)!=14.:
    raise RuntimeError('NumPy calculation failed')
  return {'executable':sys.executable,'version':platform.python_version(),'numpy':np.__version__,'numpy_path':np.__file__}

def libusb():
  from tinygrad.runtime.autogen import libusb as usb
  version=usb.libusb_get_version().contents
  # This reads library metadata only, never libusb_init or device enumeration.
  getattr(usb.dll,'libusb_control_transfer')
  getattr(usb.dll,'libusb_bulk_transfer')
  return {'path':usb.dll._name,'version':f'{version.major}.{version.minor}.{version.micro}'}

def llvm():
  from tinygrad.runtime.autogen import llvm as api
  from tinygrad.runtime.support.compiler_llvm import AMDLLVMCompiler
  binary=AMDLLVMCompiler('gfx1200').compile(IR)
  if not binary.startswith(b'\x7fELF'):
    raise RuntimeError('LLVM did not emit an AMDGPU ELF object')
  return {'path':api.dll._name,'target':'gfx1200','object_sha256':hashlib.sha256(binary).hexdigest()}

def report():
  result={'python':python(),'libusb':libusb(),'llvm':llvm(),'fuser':shutil.which('fuser'),
          'architecture':platform.machine(),'scope':'dependency calculations and compiler only; no USB/device access'}
  subprocess.run([result['fuser'],'-V'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
  result['runtime_manifest_sha256']=hashlib.sha256((ROOT/'runtime/SHA256SUMS').read_bytes()).hexdigest()
  return result

if __name__=='__main__':
  option=sys.argv[1]
  if option=='--python':python()
  elif option=='--libusb':libusb()
  elif option=='--llvm':llvm()
  elif option in ('--report','--run'):
    result=report()
    if option=='--report':print(json.dumps(result,indent=2))
    else:
      from flash import save
      folder=Path('/data/sp-flasher');folder.mkdir(parents=True,exist_ok=True)
      save(folder/'runtime.json',result)
      os.execv(sys.executable,[sys.executable,'-u',str(ROOT/'station.py')])
  else:raise ValueError(option)
