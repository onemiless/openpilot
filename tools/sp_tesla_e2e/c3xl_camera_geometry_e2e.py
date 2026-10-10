#!/usr/bin/env python3
"""Launch environment to real camera registry/warp geometry proof; no device mutation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROBE = '''
import json
from openpilot.common.transformations.camera import DEVICE_CAMERAS
from openpilot.common.transformations.model import get_warp_matrix
import numpy as np
out={}
for device,sensor in [('tici','ox03c10'),('tici','ar0231'),('mici','os04c10')]:
 dc=DEVICE_CAMERAS[device,sensor]
 out[device+'/'+sensor]={k:{'size':[getattr(dc,k).width,getattr(dc,k).height], 'K':getattr(dc,k).intrinsics.tolist(), 'warp':get_warp_matrix(np.zeros(3),getattr(dc,k).intrinsics,k=='wide_road').tolist()} for k in ['narrow_road','wide_road','cabin']}
print(json.dumps(out))
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();rows=[]
 with tempfile.TemporaryDirectory() as tmp:
  model=Path(tmp)/'model';model.write_text('comma tici')
  for profile,size,scaled in [('c3xl',None,True),('c3xl','1928x1208',False),('c3',None,False),('standard',None,False),('standard','1344x760',False)]:
   pf=Path(tmp)/'profile';pf.write_text(profile)
   env={**os.environ,'SUNNYPILOT_HARDWARE_PROFILE':profile,'SUNNYPILOT_HARDWARE_PROFILE_FILE':str(pf),'SUNNYPILOT_HARDWARE_MODEL_FILE':str(model),'PYTHONPATH':str(ROOT)};env.pop('C3XL_IFE_ROAD_SIZE',None)
   if size:env['C3XL_IFE_ROAD_SIZE']=size
   r=subprocess.run(['bash','-c','source ./launch_env.sh; exec "$1" -c "$2"','camera-e2e',sys.executable,PROBE],cwd=ROOT,env=env,text=True,capture_output=True,check=True);d=json.loads(r.stdout)
   errors=[];sx,sy=(1344/1928,760/1208) if scaled else (1,1)
   for sensor in ['ox03c10','ar0231']:
    for name,f in [('narrow_road',2648),('wide_road',567)]:
     s=(sx,sy) if sensor=='ox03c10' else (1,1);c=d['tici/'+sensor][name];expected=[round(1928*s[0]),round(1208*s[1])]
     if c['size']!=expected:errors.append(sensor+'/'+name+' size')
     for got,want in [(c['K'][0][0],f*s[0]),(c['K'][1][1],f*s[1]),(c['K'][0][2],964*s[0]),(c['K'][1][2],604*s[1])]:
      if abs(got-want)>1e-6:errors.append(sensor+'/'+name+' intrinsics')
   if d['tici/ox03c10']['cabin']['size']!=[1928,1208]:errors.append('cabin changed')
   if d['mici/os04c10']['narrow_road']['K']!=[[1141.5,0,672],[0,1141.5,380],[0,0,1]]:errors.append('C4 changed')
   rows.append({'profile':profile,'override':size,'passed':not errors,'errors':errors,'geometry':d})
 report={'passed':all(x['passed'] for x in rows),'scope':'real launch shell and Python camera/warp, no hardware','cases':rows};args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'cases':[(x['profile'],x['override'],x['errors']) for x in rows]}));return int(not report['passed'])
if __name__=='__main__':raise SystemExit(main())
