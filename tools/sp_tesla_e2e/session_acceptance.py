#!/usr/bin/env python3
"""Pre-implementation DM/process/ambient acceptance, with an inspectable artifact.
Run with repository native libraries built. No vehicle CAN is transmitted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(output):
  from openpilot.common.params import Params
  from openpilot.sunnypilot.hardware.driver_monitoring import latch_driver_monitoring, driver_monitoring_enabled
  from openpilot.sunnypilot.hardware.profile import HardwareProfile, infer_hardware_profile
  from openpilot.system.manager.process_config import managed_processes
  from opendbc.car import structs
  from openpilot.sunnypilot.selfdrive.car.tesla.ambient_lighting import AmbientLightingController

  evidence = []
  with tempfile.TemporaryDirectory() as directory:
    model = Path(directory) / 'model'
    model.write_bytes(b'comma tici\x00')
    assert infer_hardware_profile(model) == HardwareProfile.STANDARD
    for profile, capable in [('standard', True), ('c3xl', False)]:
      os.environ['SUNNYPILOT_HARDWARE_PROFILE'] = profile
      for enabled in [True, False, True]:
        params = Params(str(Path(directory) / f'{profile}-{enabled}'))
        params.remove('DriverMonitoringEnabled')
        params.remove('ActiveDriverMonitoringEnabled')
        assert driver_monitoring_enabled(params) == capable
        params.put_bool('DriverMonitoringEnabled', enabled, block=True)
        active = latch_driver_monitoring(params)
        assert active == (capable and enabled)
        cp = structs.CarParams.new_message()
        cp.notCar = False
        for name in ['dmonitoringmodeld', 'dmonitoringd']:
          proc = managed_processes[name]
          actual = proc.should_run(True, params, cp)
          assert actual == active, (profile, enabled, name, actual)
        params.put_bool('DriverMonitoringEnabled', not enabled, block=True)
        assert driver_monitoring_enabled(params) == active
        assert latch_driver_monitoring(params) == active
        params.remove('ActiveDriverMonitoringEnabled')
        assert latch_driver_monitoring(params) == (capable and not enabled)
        evidence.append({'case':'dm-session','profile':profile,'configured':enabled,'active':active,'onroad_edit_held':True})
    os.environ['SUNNYPILOT_HARDWARE_PROFILE'] = 'standard'
    params = Params(str(Path(directory) / 'ambient'))
    params.put_bool('TeslaBlindspotAmbientEnabled', True, block=True)
    params.put('TeslaBlindspotAmbientDayBrightness', 100, block=True)
    params.put('TeslaBlindspotAmbientBrightness', 30, block=True)
    for left,right,night,side,brightness in [(1,0,False,'left',100),(0,2,True,'right',30),(1,2,True,'both',30)]:
      c = AmbientLightingController()
      c.service_params(params)
      now = 10_000_000_000
      c.observe_frame(now,0x679,bytes(7),1)
      c.update_blindspot(left,right,night,now)
      frames = c.take_can_sends(now)
      assert len(frames)==1
      frame=frames[0]
      assert frame.address==0x679 and frame.src==1 and len(frame.dat)==7
      assert tuple(frame.dat[1:4])==(255,0,0) and (frame.dat[4]&127)==brightness
      assert c.take_can_sends(now+1)==[]
      c.update_blindspot(0,0,night,now+100_000_000)
      assert c.take_can_sends(now+100_000_000)==[]
      evidence.append({'case':'ambient','side':side,'night':night,'brightness':brightness,'payload':frame.dat.hex(),'bounded':True})
    c=AmbientLightingController(); c.service_params(params)
    c.update_blindspot(1,1,True,20_000_000_000)
    assert c.take_can_sends(20_000_000_000)==[]
    evidence.append({'case':'ambient-no-fresh-can','no_transmit':True})
  result={'passed':True,'scope':'native Param -> latched session -> manager predicates; ambient Param -> bounded CAN output; no physical CAN','head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'cases':evidence}
  output.parent.mkdir(parents=True,exist_ok=True)
  output.write_text(json.dumps(result,indent=2)+'\n')
  print(output)


if __name__=='__main__':
  parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
  run(parser.parse_args().output)
