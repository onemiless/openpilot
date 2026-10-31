"""Exercise real bootstrap through subprocesses using fake interpreters/station; never hardware."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
cases=[]
for scenario in ('system','system_numpy_missing','system_python_old','system_python_missing','system_usb_missing','system_llvm_broken','both_failed','check_only','bundle_corrupt','native_both_failed','fuser_missing','argument_invalid','numpy_broken_after_native'):
 case=out/scenario;case.mkdir();app=case/'app';app.mkdir();commands=case/'bin';commands.mkdir()
 shutil.copyfile(root/'runtime.sh',app/'runtime.sh')
 (app/'prepare_payload.sh').write_text('#!/bin/bash\nexit 0\n')
 (app/'runtime/python/bin').mkdir(parents=True)
 (app/'runtime/numpy').mkdir()
 (app/'runtime/libusb').mkdir()
 (app/'runtime/llvm').mkdir()
 (app/'runtime/tools').mkdir()
 (app/'runtime_probe.py').write_text('')
 (app/'station.py').write_text('must never actually execute')
 fake='''#!/bin/bash
kind=$(basename "$0")
if [[ "$0" == */runtime/python/bin/* ]]; then kind=bundled; fi
if [[ "$*" == *"runtime_probe.py"* ]]; then
 if [[ "$*" == *"--python"* ]]; then
  if [[ "$kind" == "python3" && "$SCENARIO" =~ system_python_(old|missing) ]]; then exit 1; fi
  if [[ "$SCENARIO" == "both_failed" ]]; then exit 1; fi
  if [[ "$SCENARIO" == "numpy_broken_after_native" && "$kind" == "python3" && -n "${LLVM_PATH:-}" ]]; then exit 1; fi
  if [[ "$SCENARIO" == "system_numpy_missing" && "$kind" == "python3" && "$PYTHONPATH" != *runtime/numpy* ]]; then exit 1; fi
  exit 0
 fi
 if [[ "$*" == *"--libusb"* && "$SCENARIO" == "system_usb_missing" && -z "${LIBUSB_PATH:-}" ]]; then exit 1; fi
 if [[ "$*" == *"--llvm"* && "$SCENARIO" == "native_both_failed" ]]; then exit 1; fi
 if [[ "$*" == *"--llvm"* && "$SCENARIO" =~ ^(system_llvm_broken|numpy_broken_after_native)$ && -z "${LLVM_PATH:-}" ]]; then exit 1; fi
 if [[ "$*" == *"--run"* ]]; then
  printf 'STATION interpreter=%s PYTHONPATH=%s LIBUSB_PATH=%s LLVM_PATH=%s LD_LIBRARY_PATH=%s\\n' "$0" "$PYTHONPATH" "${LIBUSB_PATH:-}" "${LLVM_PATH:-}" "${LD_LIBRARY_PATH:-}"
 fi
 if [[ "$*" == *"--report"* ]]; then printf '{"status":"PASS","scope":"simulated interpreter E2E"}\\n'; fi
 exit 0
fi
printf 'STATION interpreter=%s PYTHONPATH=%s LIBUSB_PATH=%s LLVM_PATH=%s LD_LIBRARY_PATH=%s\\n' "$0" "$PYTHONPATH" "${LIBUSB_PATH:-}" "${LLVM_PATH:-}" "${LD_LIBRARY_PATH:-}"
'''
 for executable in (commands/'python3',app/'runtime/python/bin/python3'):
  executable.write_text(fake);executable.chmod(0o755)
 for name in ('libusb/libusb-1.0.so.0','llvm/libLLVM.so'):(app/'runtime'/name).touch()
 (commands/'fuser').write_text('#!/bin/sh\n[ "$SCENARIO" != fuser_missing ]\n');(commands/'fuser').chmod(0o755)
 (app/'runtime/tools/fuser').write_text('#!/bin/sh\ntouch "$MARKER"\n');(app/'runtime/tools/fuser').chmod(0o755)
 (app/'runtime/SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(app/"runtime")}\n' for p in sorted((app/'runtime').rglob('*')) if p.is_file()))
 if scenario=='bundle_corrupt':(app/'runtime/llvm/libLLVM.so').write_bytes(b'corrupted')
 env={**os.environ,'PATH':str(commands)+':/usr/bin:/bin','SCENARIO':scenario,'XDG_CACHE_HOME':str(case/'cache'),'MARKER':str(case/'fuser.marker')}
 args=['bash',str(app/'runtime.sh')]
 if scenario=='check_only':args.append('--check-runtime')
 if scenario=='argument_invalid':args.append('--install')
 result=subprocess.run(args,env=env,capture_output=True,text=True)
 (case/'stdout.log').write_text(result.stdout);(case/'stderr.log').write_text(result.stderr)
 if scenario in ('both_failed','bundle_corrupt','native_both_failed','argument_invalid'):assert result.returncode!=0 and 'STATION' not in result.stdout
 else:
  assert result.returncode==0,(scenario,result.stderr)
  if scenario=='check_only':assert 'STATION' not in result.stdout
  else:
   assert 'STATION' in result.stdout
   if scenario in ('system_python_old','system_python_missing','numpy_broken_after_native'):assert 'runtime/python/bin/python3' in result.stdout
   if scenario=='system_numpy_missing':assert 'runtime/numpy' in result.stdout
   if scenario=='system_usb_missing':assert 'LIBUSB_PATH='+str(app/'runtime/libusb/libusb-1.0.so.0') in result.stdout
   if scenario=='fuser_missing':assert (case/'fuser.marker').exists()
   if scenario=='system_llvm_broken':assert 'LLVM_PATH='+str(app/'runtime/llvm/libLLVM.so') in result.stdout
 cases.append({'scenario':scenario,'status':'PASS','returncode':result.returncode})
(out/'result.json').write_text(json.dumps({'status':'PASS','scope':'real bootstrap with simulated dependency probes and fake station, no hardware','cases':cases},indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
print('PASS',len(cases),'offline-runtime lifecycle cases:',out)
