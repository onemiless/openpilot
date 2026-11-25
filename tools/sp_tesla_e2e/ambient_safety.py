#!/usr/bin/env python3
"""Recorded CAN -> actual Tesla adapter -> compiled safety; no physical TX."""
import argparse, json, time, tempfile
from pathlib import Path
from types import SimpleNamespace
from openpilot.common.params import Params
from openpilot.cereal import messaging
from opendbc.car.structs import CarParams, CarParamsSP, CarState, CarControl
from opendbc.sunnypilot.car.tesla.values import TeslaSafetyFlagsSP
from opendbc.safety.tests.libsafety import libsafety_py
from opendbc.can import CANPacker
from openpilot.sunnypilot.selfdrive.car.tesla.card_adapter import TeslaCardAdapter

TEMPLATE=bytes.fromhex("0cffd5aa00f801")

def run(output):
  safety=libsafety_py.libsafety
  records=[]
  with tempfile.TemporaryDirectory() as temp:
    params=Params(temp)
    params.put_bool("TeslaBlindspotAmbientEnabled",True,block=True)
    cp=CarParams.new_message(); cp.brand="tesla"; cp.carFingerprint="TESLA_MODEL_Y"
    sp=CarParamsSP(); sp.safetyParam=TeslaSafetyFlagsSP.HAS_VEHICLE_BUS
    sm=messaging.SubMaster(["modelV2","longitudinalPlanSP","carControl","selfdriveStateSP"])
    cs=CarState.new_message(); cc=CarControl.new_message()
    for left,right,side in [(1,0,"left"),(0,2,"right"),(1,2,"both")]:
      for brightness in [0,30,91,100]:
        params.put("TeslaBlindspotAmbientBrightness",brightness,block=True)
        ci=SimpleNamespace(CP=cp,CP_SP=sp,CS=SimpleNamespace(tesla_blindspot_left_level=left,tesla_blindspot_right_level=right))
        adapter=TeslaCardAdapter("tesla",ci,sm);adapter.service_params(params)
        now=time.monotonic_ns()
        safety.set_current_safety_param_sp(TeslaSafetyFlagsSP.HAS_VEHICLE_BUS)
        safety.set_safety_hooks(CarParams.SafetyModel.tesla,0);safety.init_tests();safety.set_timer(100)
        safety.safety_rx_hook(libsafety_py.make_CANPacket(0x679,1,TEMPLATE))
        adapter.observe_can([(now,[(0x679,TEMPLATE,1)])])
        frames=adapter.control_sends(cs,cc,now)
        assert len(frames)==1
        f=frames[0]; expected={"left":(0xA8,0),"right":(0x50,1),"both":(0xF8,1)}[side]
        assert (f.dat[5]&0xF8,f.dat[6]&1)==expected
        assert f.dat[1:4]==bytes([255,0,0]) and (f.dat[4]&127)==brightness
        assert safety.safety_tx_hook(libsafety_py.make_CANPacket(f.address,f.src,f.dat))
        assert adapter.control_sends(cs,cc,now+1)==[]
        bad=bytearray(f.dat);bad[4]=101
        safety.set_timer(100100)
        assert not safety.safety_tx_hook(libsafety_py.make_CANPacket(0x679,1,bytes(bad)))
        assert adapter.control_sends(cs,cc,now+1_100_000_000)==[]
        fresh=now+1_200_000_000
        adapter.ambient.observe_frame(fresh,0x679,TEMPLATE,1)
        assert len(adapter.control_sends(cs,cc,fresh))==1
        params.put_bool("TeslaBlindspotAmbientEnabled",False,block=True);adapter.service_params(params)
        assert adapter.control_sends(cs,cc,fresh+100_000_000)==[]
        params.put_bool("TeslaBlindspotAmbientEnabled",True,block=True)
        records.append({"side":side,"brightness":brightness,"payload":f.dat.hex(),"compiled_safety_allowed":True,"overrange_rejected":True,"stale_and_off_no_tx":True})
    # Actual UI CAN source changes the day/night selection before fallback.
    packer=CANPacker("tesla_model3_vehicle")
    for dark,expected in [(0,100),(1,30)]:
      ci=SimpleNamespace(CP=cp,CP_SP=sp,CS=SimpleNamespace(tesla_blindspot_left_level=1,tesla_blindspot_right_level=0))
      adapter=TeslaCardAdapter("tesla",ci,sm)
      params.put("TeslaBlindspotAmbientDayBrightness",100,block=True)
      params.put("TeslaBlindspotAmbientBrightness",30,block=True);adapter.service_params(params)
      now=time.monotonic_ns();ui_frame=packer.make_can_msg("UI_status2",1,{"UI_displayInDarkMode":dark})
      adapter.observe_can([(now,[(0x679,TEMPLATE,1),ui_frame])])
      f=adapter.control_sends(cs,cc,now)[0]
      assert (f.dat[4]&127)==expected
      records.append({"ui_dark_mode":dark,"brightness":expected,"actual_can_parser":True})
    # Both independent timers are driven through 150 fresh frames.
    adapter=TeslaCardAdapter("tesla",ci,sm);adapter.service_params(params)
    now=time.monotonic_ns();safety.set_current_safety_param_sp(TeslaSafetyFlagsSP.HAS_VEHICLE_BUS)
    safety.set_safety_hooks(CarParams.SafetyModel.tesla,0);safety.init_tests()
    for i in range(150):
      stamp=now+i*100_000_000;safety.set_timer(100+i*100000)
      safety.safety_rx_hook(libsafety_py.make_CANPacket(0x679,1,TEMPLATE))
      adapter.ambient.observe_frame(stamp,0x679,TEMPLATE,1)
      frames=adapter.control_sends(cs,cc,stamp);assert len(frames)==1
      assert safety.safety_tx_hook(libsafety_py.make_CANPacket(0x679,1,frames[0].dat))
    last=frames[0].dat;safety.set_timer(15_000_100)
    safety.safety_rx_hook(libsafety_py.make_CANPacket(0x679,1,TEMPLATE))
    adapter.ambient.observe_frame(now+15_000_000_000,0x679,TEMPLATE,1)
    assert adapter.control_sends(cs,cc,now+15_000_000_000)==[]
    assert not safety.safety_tx_hook(libsafety_py.make_CANPacket(0x679,1,last))
    safety.set_safety_hooks(CarParams.SafetyModel.tesla,0);safety.init_tests();safety.set_timer(100)
    safety.safety_rx_hook(libsafety_py.make_CANPacket(0x679,1,TEMPLATE));safety.set_timer(1_100_100)
    assert not safety.safety_tx_hook(libsafety_py.make_CANPacket(0x679,1,last))
    records.append({"continuous_fresh_frames":150,"host_duration_cap":True,"safety_session_cap":True,"safety_stale_rejected":True})
    result={"passed":True,"scope":"synthetic CAN/template and blindspot input; real adapter/Params/parser/safety, no physical vehicle or CAN TX","cases":records}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+chr(10));json.loads(output.read_text())
    print(output)

if __name__=="__main__":
  p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);run(p.parse_args().output)
