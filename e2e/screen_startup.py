"""Real station startup with a display subprocess and fake tick; never opens USB."""
import json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if len(sys.argv)>1 and sys.argv[1]=='--child':
 sys.path.insert(0,str(root));import station
 case=Path(sys.argv[2]);real_path=Path
 station.Path=lambda p:case/'data' if p=='/data/sp-flasher' else real_path(p)
 station.ROOT=case/'app'
 def tick(_):
  (case/'tick-called').write_text('yes');raise SystemExit(0)
 station.tick=tick
 station.main()
else:
 out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False);rows=[]
 for mode in ('ready','failed'):
  case=out/mode;app=case/'app';app.mkdir(parents=True)
  (app/'status_screen.py').write_text("import os,sys,time\nfrom pathlib import Path\nPath(__file__).with_name('pid').write_text(str(os.getpid()))\nfd=int(sys.argv[sys.argv.index('--ready-fd')+1])\nos.write(fd,"+("b'1'" if mode=='ready' else "b'0'")+");os.close(fd)\ntime.sleep(60)\n")
  result=subprocess.run([sys.executable,__file__,'--child',str(case)],capture_output=True,text=True,timeout=25)
  (case/'output.log').write_text(result.stdout+result.stderr)
  assert (result.returncode==0)==(mode=='ready'),result.stderr
  assert (case/'tick-called').exists()==(mode=='ready')
  pid=int((app/'pid').read_text())
  try:os.kill(pid,0)
  except ProcessLookupError:pass
  else:raise AssertionError('Display child leaked')
  rows.append({'case':mode,'status':'PASS','returncode':result.returncode})
 (out/'result.json').write_text(json.dumps({'status':'PASS','scope':'actual station startup/display readiness + mocked tick, no USB','cases':rows},indent=2)+'\n')
 print('PASS display startup gates:',out)
