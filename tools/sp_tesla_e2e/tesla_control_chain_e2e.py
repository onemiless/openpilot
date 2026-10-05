#!/usr/bin/env python3
"""Synthetic CAN -> actual Tesla CI/controller/adapter -> freshly compiled safety."""
import argparse
import hashlib
import inspect
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time
import traceback

from opendbc.can import CANPacker
from opendbc.can.dbc import DBC
from opendbc.can.parser import get_raw_value
from opendbc.car import structs
from opendbc.car.tesla.interface import CarInterface
from opendbc.car.tesla.values import CAR
from opendbc.car.vehicle_model import VehicleModel
from opendbc.sunnypilot.car.tesla.carstate_ext import TeslaLongitudinalSource
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP, TeslaSafetyFlagsSP
from opendbc.safety.tests.libsafety import libsafety_py
from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.sunnypilot.selfdrive.car.tesla.card_adapter import TeslaCardAdapter
from openpilot.sunnypilot.selfdrive.car.tesla.control_runtime import EventName, TeslaControlRuntime


ROOT = Path(__file__).resolve().parents[2]
AMBIENT_TEMPLATE = bytes.fromhex("0cffd5aa00f801")


def decoded(dbc, name, frame):
  msg = DBC(dbc).name_to_msg[name]
  return {name: (get_raw_value(frame[1], sig) -
                 ((get_raw_value(frame[1], sig) >> (sig.size - 1)) << sig.size if sig.is_signed else 0)) * sig.factor + sig.offset
          for name, sig in msg.sigs.items()}


def make_ci():
  cp = CarInterface.get_non_essential_params(CAR.TESLA_MODEL_Y)
  cp.openpilotLongitudinalControl = True
  sp = CarInterface.get_non_essential_params_sp(cp, CAR.TESLA_MODEL_Y)
  sp.flags |= TeslaFlagsSP.HAS_VEHICLE_BUS | TeslaFlagsSP.COOP_STEERING | TeslaFlagsSP.ARS408_RADAR | TeslaFlagsSP.AUTO_SPEED_LIMIT
  sp.safetyParam |= (TeslaSafetyFlagsSP.HAS_VEHICLE_BUS | TeslaSafetyFlagsSP.AP_HYBRID_HANDOFF |
                     TeslaSafetyFlagsSP.AP_HYBRID_LATERAL_HANDOFF | TeslaSafetyFlagsSP.ARS408_RADAR |
                     TeslaSafetyFlagsSP.AUTO_SPEED_LIMIT)
  ci = CarInterface(cp, sp)
  ci.update([])  # Lazy CANParser registration must precede the first received batch.
  ci._e2e_packers = {bus: CANPacker(parser.dbc_name) for bus, parser in ci.can_parsers.items()}
  return ci


def sample(ci, now, *, cruise=2, speed=72.0, angle=0.0, torque=0.0, reverse=False):
  values = {
    "DI_speed": {"DI_vehicleSpeed": speed},
    "DI_state": {"DI_cruiseState": cruise, "DI_speedUnits": 0, "DI_digitalSpeed": 80},
    "DI_systemStatus": {"DI_gear": 2 if reverse else 4},
    "ESP_B": {"ESP_vehicleSpeed": speed, "ESP_wheelSpeedsQF": 1, "ESP_vehicleStandstillSts": int(speed == 0)},
    "ESP_status": {"ESP_driverBrakeApply": 1},
    "EPAS3S_sysStatus": {"EPAS3S_internalSAS": -angle, "EPAS3S_torsionBarTorque": -torque, "EPAS3S_eacStatus": 1},
    "DAS_control": {"DAS_accState": 4, "DAS_accelMin": 0.0, "DAS_accelMax": 0.0},
    "UI_warning": {"buckleStatus": 1},
  }
  frames = []
  for bus, parser in ci.can_parsers.items():
    packer = ci._e2e_packers[bus]
    for name in list(parser.vl):
      if isinstance(name, str):
        frames.append(packer.make_can_msg(name, parser.bus, values.get(name, {})))
  cs, state_sp = ci.update([(now, frames)])
  return cs, state_sp, frames


def controls(*, accel=1.0, angle=0.0):
  cc = structs.CarControl()
  cc.enabled = cc.latActive = cc.longActive = True
  cc.actuators.accel = accel
  cc.actuators.steeringAngleDeg = angle
  return cc


def init_safety(ci):
  safety = libsafety_py.libsafety
  safety.set_current_safety_param_sp(ci.CP_SP.safetyParam)
  assert safety.set_safety_hooks(structs.CarParams.SafetyModel.tesla, 1) == 0
  safety.init_tests()
  return safety


def packet(frame):
  return libsafety_py.make_CANPacket(frame[0], frame[2], frame[1])


def safety_rx(safety, frames, now):
  safety.set_timer((now // 1000) & 0xFFFFFFFF)
  for frame in frames:
    safety.safety_rx_hook(packet(frame))


def fault_chain():
  results = []
  for source in (TeslaLongitudinalSource.manualStock, TeslaLongitudinalSource.dynamicStock, TeslaLongitudinalSource.apHybridStock):
    ci = make_ci()
    now = time.monotonic_ns()
    cs, _, frames = sample(ci, now)
    assert cs.cruiseState.enabled, "engaged synthetic CAN was not decoded"
    safety = init_safety(ci)
    safety_rx(safety, frames, now)
    ci.CS._set_longitudinal_source(source)
    ci.CS.tesla_ap_hybrid_active = source == TeslaLongitudinalSource.apHybridStock
    ci.CS.tesla_stock_lateral_active = ci.CS.tesla_ap_hybrid_active
    cc = controls(accel=1.5, angle=10.0)
    _, sends = ci.apply(cc.as_reader(), structs.CarControlSP(), now)
    for f in sends:
      safety.safety_tx_hook(packet(f))
    assert not safety.safety_fwd_hook(2, 0x2B9), "OEM forwarding handoff was not established"
    runtime = TeslaControlRuntime(True)
    runtime.update(int(ci.CS._longitudinal_source_flags()), now, now)
    runtime.commit_cycle()
    for i in range(1, 7):
      stamp = now + i * 10_000_000
      cs, state_sp, frames = sample(ci, stamp, cruise=5)
      assert cs.accFaulted and not cs.cruiseState.enabled
      safety_rx(safety, frames, stamp)
      runtime.update(int(state_sp.flags), stamp, stamp)
      events = Events()
      events.add(EventName.accFaulted)
      events.add(EventName.gasPressedOverride)
      runtime.filter_transition_events(events)
      assert events.has(EventName.accFaulted), "real ACC FAULT was removed"
      assert events.has(EventName.gasPressedOverride), "accelerator override was removed"
      output, sends = ci.apply(cc.as_reader(), structs.CarControlSP(), stamp)
      assert not ci.CS.tesla_stock_longitudinal_active and not ci.CS.tesla_stock_lateral_active
      for f in sends:
        if f[0] == 0x2B9:
          d = decoded("tesla_model3_party", "DAS_control", f)
          assert d["DAS_accState"] == 13 and abs(d["DAS_accelMin"]) < 0.05 and abs(d["DAS_accelMax"]) < 0.05, d
          assert safety.safety_tx_hook(packet(f)), "fault cancel failed compiled safety"
        if f[0] == 0x488:
          assert decoded("tesla_model3_party", "DAS_steeringControl", f)["DAS_steeringControlType"] == 0
      assert output.accel == 0.0
      assert safety.safety_fwd_hook(2, 0x2B9), "fault cancel did not close OEM longitudinal forwarding"
      runtime.commit_cycle()
    results.append({"source": str(source), "fault_cycles": 6, "fault_retained": True, "stale_active_control_cancel_only": True})
  return results


def actual_output_chain():
  ci = make_ci()
  now = time.monotonic_ns()
  cc = controls()
  last_angle = last_accel = None
  for i in range(42):
    stamp = now + i * 10_000_000
    sample(ci, stamp, torque=2.0)
    output, sends = ci.apply(cc.as_reader(), structs.CarControlSP(), stamp)
    for f in sends:
      if f[0] == 0x488:
        last_angle = -decoded("tesla_model3_party", "DAS_steeringControl", f)["DAS_steeringAngleRequest"]
      if f[0] == 0x2B9:
        last_accel = decoded("tesla_model3_party", "DAS_control", f)["DAS_accelMin"]
    assert last_angle is not None and math.isclose(output.steeringAngleDeg, last_angle, abs_tol=0.051), (output.steeringAngleDeg, last_angle)
    assert last_accel is not None and math.isclose(output.accel, last_accel, abs_tol=0.021), (output.accel, last_accel)
    assert output.curvature == cc.actuators.curvature and output.torque == cc.actuators.torque
  assert abs(last_angle) > 1, "cooperative branch was not exercised"
  # Real stock-to-SP edge exercises the acceleration ramp instead of only passthrough.
  ci.CS._set_longitudinal_source(TeslaLongitudinalSource.manualStock)
  ci.apply(cc.as_reader(), structs.CarControlSP(), now + 500_000_000)
  ci.CS._set_longitudinal_source(TeslaLongitudinalSource.sp)
  ci.CS.out.aEgo = -1.0
  output, sends = ci.apply(cc.as_reader(), structs.CarControlSP(), now + 510_000_000)
  f = next(f for f in sends if f[0] == 0x2B9)
  applied = decoded("tesla_model3_party", "DAS_control", f)["DAS_accelMin"]
  assert applied < 0 and math.isclose(output.accel, applied, abs_tol=0.021)
  return {"cooperative_angle_deg": last_angle, "emitted_accel": last_accel, "takeover_ramp_accel": applied}


def yaw_chain():
  rows = []
  for angle, speed, reverse in [(5.0, 72.0, False), (-5.0, 72.0, False), (5.0, 0.0, False), (5.0, 18.0, True)]:
    ci = make_ci()
    now = time.monotonic_ns()
    cs, _, frames = sample(ci, now, angle=angle, speed=speed, reverse=reverse)
    assert cs.canValid
    cc = controls(angle=angle)
    _, sends = ci.apply(cc.as_reader(), structs.CarControlSP(), now)
    f = next(f for f in sends if f[0] == 0x301)
    yaw = decoded("ARS408", "YawRateInformation", f)["RadarDevice_YawRate"]
    velocity = -abs(cs.vEgoRaw) if reverse else cs.vEgoRaw
    expected = -math.degrees(VehicleModel(ci.CP).yaw_rate(math.radians(cs.steeringAngleDeg), velocity, 0.0))
    assert math.isclose(yaw, expected, abs_tol=0.011), (yaw, expected)
    assert speed == 0 or yaw != 0
    safety = init_safety(ci)
    safety_rx(safety, frames, now)
    assert safety.safety_tx_hook(packet(f))
    ci.CS.out.canValid = False
    assert ci.CC.ars408_transmitter.update(5, ci.CS.out) == []
    ci.CS.out.canValid = True
    ci.CS.out.yawRate = math.nan
    assert ci.CC.ars408_transmitter.update(5, ci.CS.out) == []
    rows.append({"angle": angle, "speed_kph": speed, "reverse": reverse, "wire_yaw_deg_s": yaw, "source": "VehicleModel estimate"})
  return rows


def accessory_chain():
  ci = make_ci()
  safety = init_safety(ci)
  now = time.monotonic_ns()
  _, _, frames = sample(ci, now)
  safety_rx(safety, frames, now)
  safety.set_controls_allowed(True)
  for address in (0x082, 0x3FD, 0x370, 0x399):
    assert not safety.safety_tx_hook(libsafety_py.make_CANPacket(address, 0, bytes(8))), hex(address)
  epas = next(f for f in frames if f[0] == 0x370 and f[2] == 0)
  invalid_epas = bytearray(epas[1])
  invalid_epas[7] ^= 1
  assert not safety.safety_rx_hook(libsafety_py.make_CANPacket(0x370, 0, invalid_epas)), "essential EPAS RX checksum check was removed"
  assert not safety.safety_tx_hook(libsafety_py.make_CANPacket(0x3E9, 1, bytes(8)))
  with tempfile.TemporaryDirectory() as temp:
    params = Params(temp)
    params.put_bool("TeslaBlindspotAmbientEnabled", True, block=True)
    params.put("TeslaBlindspotAmbientBrightness", 30, block=True)
    params.put("TeslaAmbientLightingRequest", json.dumps({"id": "retired", "side": "left", "created_ns": now}), block=True)
    params.put("TeslaTurnSignalTestRequest", {"test_id": "retired", "direction": "left"}, block=True)
    sm = messaging.SubMaster(["modelV2", "longitudinalPlanSP", "carControl", "selfdriveStateSP"])
    adapter = TeslaCardAdapter("tesla", ci, sm)
    adapter.service_params(params)
    assert not hasattr(adapter, "validation"), "retired Web controller still runs in card"
    adapter.observe_can([(now, [(0x679, AMBIENT_TEMPLATE, 1)])])
    cs = ci.CS.out
    cc = controls()
    assert adapter.control_sends(cs, cc, now) == [], "retired Params triggered a CAN test"
    ci.CS.tesla_blindspot_left_level = 1
    sends = adapter.control_sends(cs, cc, now + 100_000_000)
    assert len(sends) == 1 and sends[0][0] == 0x679
    safety.set_timer((now // 1000 + 100000) & 0xFFFFFFFF)
    safety.safety_rx_hook(libsafety_py.make_CANPacket(0x679, 1, AMBIENT_TEMPLATE))
    assert safety.safety_tx_hook(packet(sends[0]))
    assert adapter.control_sends(cs, cc, now + 100_000_001) == []
    assert adapter.control_sends(cs, cc, now + 1_200_000_000) == []
    # Production automatic speed-wheel permission remains independent of retired validation.
    template = bytes.fromhex("0100000000000000")
    safety.safety_rx_hook(libsafety_py.make_CANPacket(0x3C2, 1, template))
    safety.set_controls_allowed(True)  # Independent accessory check after the deliberate invalid EPAS RX.
    tick = bytearray(template)
    tick[3] = 1
    assert safety.safety_tx_hook(libsafety_py.make_CANPacket(0x3C2, 1, tick))
    assert not safety.safety_tx_hook(libsafety_py.make_CANPacket(0x3C2, 1, tick))
  return {"obsolete_tx_rejected": True, "retired_requests_no_tx": True, "ambient_and_auto_speed_allowed": True}


def startup_config_chain():
  with tempfile.TemporaryDirectory() as temp:
    params = Params(temp)
    params.put_bool("DynamicAutoStock", True, block=True)
    params.put_bool("TeslaTouchLongitudinalSwitch", True, block=True)
    params.put("DynamicAutoStockSpeedKph", 95, block=True)
    params.put("DynamicAutoStockSpeedLowKph", 90, block=True)
    ci = make_ci()
    ci.CP_SP.flags |= TeslaFlagsSP.DYNAMIC_AUTO_STOCK
    sm = messaging.SubMaster(["longitudinalPlanSP", "carControl", "selfdriveStateSP"])
    adapter = TeslaCardAdapter("tesla", ci, sm, params)
    assert ci.CS._config_initialized and ci.CS._dyn_enabled and ci.CS._touch_longitudinal_switch_enabled
    assert (ci.CS._dyn_high, ci.CS._dyn_low) == (95, 90), "configuration was not ready before the first CAN/control cycle"
    params.put_bool("DynamicAutoStock", False, block=True)
    params.put("DynamicAutoStockSpeedKph", 80, block=True)
    params.put("DynamicAutoStockSpeedLowKph", 70, block=True)
    adapter.service_params(params)
    sample(ci, time.monotonic_ns())
    assert ci.CS._dyn_enabled and (ci.CS._dyn_high, ci.CS._dyn_low) == (95, 90), "startup settings live-reloaded during the session"
    restarted = make_ci()
    TeslaCardAdapter("tesla", restarted, sm, params)
    assert restarted.CS._config_initialized and not restarted.CS._dyn_enabled
    assert (restarted.CS._dyn_high, restarted.CS._dyn_low) == (80, 70)
    assert "openpilot" not in inspect.getsource(type(ci.CS).update_config), "opendbc reads parent Params implicitly"
  return {"initialized_before_first_cycle": True, "session_thresholds": [95, 90], "next_session_thresholds": [80, 70]}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output", type=Path, required=True)
  parser.add_argument("--phase", choices=("fault", "all"), default="all")
  args = parser.parse_args()
  assert Path(inspect.getfile(CarInterface)).resolve().is_relative_to(ROOT / "opendbc_repo"), "wrong opendbc checkout"
  cases = []
  checks = [("fault-chain", fault_chain)]
  if args.phase == "all":
    checks.extend((("actual-output", actual_output_chain), ("yaw-chain", yaw_chain),
                   ("accessory-chain", accessory_chain), ("startup-config", startup_config_chain)))
  for name, check in checks:
    try:
      cases.append({"case": name, "passed": True, "evidence": check()})
    except Exception as error:
      cases.append({"case": name, "passed": False, "error": repr(error), "traceback": traceback.format_exc()})
  sources = [Path(__file__), ROOT / "docs/sp-tesla-migration/TESLA_CONTROL_FIXES.md", ROOT / "opendbc_repo/opendbc/safety/modes/tesla.h"]
  for directory in ("opendbc_repo/opendbc/car/tesla", "opendbc_repo/opendbc/sunnypilot/car/tesla", "openpilot/sunnypilot/selfdrive/car/tesla"):
    sources.extend(sorted((ROOT / directory).rglob("*.py")))
  result = {
    "passed": all(row["passed"] for row in cases), "scope": "offline synthetic CAN, actual CI/CS/controller/adapter and compiled safety; no physical CAN",
    "hardware_validation": "pending", "cases": cases,
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "opendbc_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT / "opendbc_repo", text=True).strip(),
    "imports": {"CarInterface": inspect.getfile(CarInterface), "libsafety": inspect.getfile(libsafety_py)},
    "sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(result, indent=2) + "\n")
  summary = {"artifact": str(args.output), "passed": result["passed"], "cases": [{k: row[k] for k in row if k != "traceback"} for row in cases]}
  print(json.dumps(summary, indent=2))
  raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
  main()
