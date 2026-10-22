#!/usr/bin/env python3
"""Actual planner/solver -> wire publisher -> LongControl across official DEC sunset."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as ns
from unittest.mock import patch
import traceback

from openpilot.cereal import custom
from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.factory import create_longitudinal_planner
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.longcontrol_factory import create_long_control
from tools.sp_tesla_e2e.tesla_planner_chain_e2e import FIXTURE, Inputs, Published, fixture_messages


def run_case(route, backend, enabled, experimental, endpoint, stage):
  cp = next(m.carParams for m in route if m.which() == 'carParams')
  with OpenpilotPrefix():
    params = Params()
    params.put('LongitudinalPlannerMode', backend, block=True)
    params.put_bool('DynamicExperimentalControl', enabled, block=True)
    params.put_bool('SmartCruiseControlVision', False, block=True)
    params.put_bool('SmartCruiseControlMap', False, block=True)
    params.put('SpeedLimitMode', 0, block=True)
    planner = create_longitudinal_planner(cp, custom.CarParamsSP.new_message(), params=params)
    controller = create_long_control(cp, custom.CarParamsSP.new_message(), params=params)
    sm = Inputs(route)
    sm['carState'].vEgo = 20.
    sm['carState'].aEgo = 0.
    sm['carState'].vCruise = 100.
    sm['carState'].vCruiseCluster = 100.
    sm['carState'].standstill = False
    sm['carState'].gasPressed = False
    sm['carState'].brakePressed = False
    sm['carControl'].enabled = True
    sm['carControl'].longActive = True
    sm['controlsState'].forceDecel = False
    sm['controlsState'].longControlState = 'off'
    sm['selfdriveState'].enabled = True
    sm['selfdriveState'].experimentalMode = experimental
    sm['radarState'].leadOne.present = False
    sm['radarState'].leadTwo.present = False
    sm['modelV2'].position.x = [endpoint * i / 32 for i in range(33)]
    sm['modelV2'].orientation.x = [0.] * 33
    sm['modelV2'].orientationRate.z = [0.001] * 33
    sm['modelV2'].velocity.x = [20.] * 33
    sm['modelV2'].action.desiredAcceleration = -3.
    sm['modelV2'].action.shouldStop = endpoint < 10.
    planner.update(sm)
    sm['controlsState'].longControlState = 'pid'
    # Advance both state inputs and actual solver recursion, without injecting
    # a substitute DEC controller, solver or backend publisher.
    for frame in range(1, 9):
      sm.frame = frame + 1
      sm.logMonoTime['radarState'] = 1_000_000_000 + frame * 50_000_000
      sm.logMonoTime['modelV2'] = sm.logMonoTime['radarState']
      planner.update(sm)
    published = Published()
    planner.publish(sm, published)
    plan = published.messages['longitudinalPlan'].longitudinalPlan
    plan_sp = published.messages['longitudinalPlanSP'].longitudinalPlanSP
    control_accel = controller.update(True, sm['carState'], plan.aTarget, plan.shouldStop, [-3.5, 2.])
    dec = getattr(planner, 'dec', None)
    expected_dec = backend == 1 or (backend == 0 and stage == 'baseline')
    assert (dec is not None) == expected_dec, (backend, stage, 'DEC ownership')
    if expected_dec:
      assert dec.enabled() == enabled
      assert dec.active() == (enabled and experimental)
      assert dec.mode() == ('blended' if endpoint < 10. else 'acc')
      assert plan_sp.dec.enabled == enabled
      assert plan_sp.dec.active == (enabled and experimental)
      assert str(plan_sp.dec.state) == dec.mode()
    elif backend == 0:
      assert not plan_sp.dec.enabled and not plan_sp.dec.active
    # The native model acceleration wins only when the real backend admits it.
    allows_e2e = (backend == 0 and stage == 'candidate') or (experimental and not (expected_dec and enabled and endpoint >= 10.))
    assert (str(plan.longitudinalPlanSource) == 'e2e') == allows_e2e, (
      backend, enabled, experimental, endpoint, str(plan.longitudinalPlanSource))
    assert all(math.isfinite(v) for v in (plan.aTarget, control_accel, *plan.speeds, *plan.accels, *plan.jerks))
    freshness = None
    if backend == 2:
      assert planner._radar_fresh_this_cycle
      assert plan_sp.accelController.enabled == planner.accel_controller.is_enabled
      assert plan_sp.accelController.active == planner.accel_controller.is_active
      assert int(plan_sp.accelController.profile.raw) == int(planner.accel_controller.profile)
      assert int(plan_sp.accelController.state.raw) == int(planner.accel_controller.state)
      # Repeated timestamps must not masquerade as a fresh radar observation.
      previous_a = planner.output_a_target
      planner.update(sm)
      assert not planner._radar_fresh_this_cycle
      assert planner.previous_plan_accel == previous_a
      sm.logMonoTime['radarState'] += 50_000_000
      planner.update(sm)
      assert planner._radar_fresh_this_cycle
      freshness = [True, False, True]
    assert params.get_bool('DynamicExperimentalControl') == enabled
    assert params.get('ActiveLongitudinalBackend') == backend
    return {'backend': backend, 'dec_param': enabled, 'experimental_mode': experimental,
            'endpoint_m': endpoint, 'dec_instantiated': dec is not None,
            'dec_mode': dec.mode() if dec is not None else None,
            'source': str(plan.longitudinalPlanSource), 'aTarget': plan.aTarget,
            'shouldStop': plan.shouldStop, 'controlAccel': float(control_accel),
            'radar_freshness': freshness, 'passed': True}



def cruise_case(route, backend, enabled, experimental, stage):
  from openpilot.cereal import messaging
  from opendbc.car import structs
  from openpilot.selfdrive.car.card import Car
  from openpilot.selfdrive.car.cruise import VCruiseHelper
  from openpilot.selfdrive.pandad import can_list_to_can_capnp
  from openpilot.sunnypilot.selfdrive.car.tesla.card_adapter import TeslaCardAdapter
  from tools.sp_tesla_e2e.tesla_control_chain_e2e import make_ci, sample

  with OpenpilotPrefix():
    params = Params()
    params.put('LongitudinalPlannerMode', backend, block=True)
    params.put_bool('DynamicExperimentalControl', enabled, block=True)
    ci = make_ci()
    ci.CP.pcmCruise = False
    create_long_control(ci.CP, ci.CP_SP, params=params)
    # The requested backend may change while the active session stays latched.
    params.put('LongitudinalPlannerMode', (backend + 1) % 3, block=True)
    now = time.monotonic()
    _, _, frames = sample(ci, int(now * 1e9), speed=72.)
    sm = Inputs(route)
    sm.values['longitudinalPlanSP'] = messaging.new_message('longitudinalPlanSP').longitudinalPlanSP
    sm['longitudinalPlanSP'].longitudinalPlanSource = 'cruise'
    sm['carControl'].enabled = True
    sm['carControl'].latActive = sm['carControl'].longActive = False
    for flags in (sm.seen, sm.valid, sm.alive):
      flags['longitudinalPlanSP'] = True
    sm.recv_time = dict.fromkeys(sm.values, now)
    sm.updated = dict.fromkeys(sm.values, True)
    sm.update = lambda timeout: None
    card = object.__new__(Car)
    card.CP, card.CP_SP, card.CI = ci.CP, ci.CP_SP, ci
    card.params, card.sm, card.can_sock = params, sm, None
    card.tesla_adapter = TeslaCardAdapter('tesla', ci, sm, params)
    card.can_callbacks = (None, lambda sends: None)
    card.RI = ns(update=lambda can_list: None)
    card.can_rcv_cum_timeout_counter = 0
    card.CS_prev = structs.CarState(vEgo=20.)
    card.CC_prev = structs.CarControl(enabled=False)
    card.v_cruise_helper = VCruiseHelper(ci.CP, ci.CP_SP)
    card.experimental_mode, card.dynamic_experimental_control = experimental, enabled
    card.initial_cruise_speed = 60
    card.is_metric = True
    raw_can = can_list_to_can_capnp(frames, msgtype='can')
    # Only IPC delivery and the unrelated radar endpoint are replaced. The
    # Tesla parser, card state_update, session Params and cruise helper are real.
    with patch('openpilot.selfdrive.car.card.messaging.drain_sock_raw', return_value=[raw_can]):
      state, _, _ = card.state_update()
    dec_applies = enabled and (stage == 'baseline' or backend == 1)
    expected = 105. if experimental and not dec_applies and not (backend == 0 and stage == 'candidate') else 72.
    assert state.vCruise == expected, (backend, enabled, experimental, stage, state.vCruise, expected)
    assert params.get('ActiveLongitudinalBackend') == backend
    assert params.get('LongitudinalPlannerMode') == (backend + 1) % 3
    return {'backend': backend, 'desired': (backend + 1) % 3, 'dec_param': enabled,
            'experimental_mode': experimental, 'vCruise': state.vCruise, 'passed': True}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--stage', choices=['baseline', 'candidate'], required=True)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  root = Path.cwd().resolve()
  result = {'stage': args.stage, 'scope': 'host actual solver/planner/wire publisher/LongControl; no CAN, device or road',
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            'command': sys.argv, 'cases': [], 'cruise_cases': [], 'passed': False}
  paths = [Path(__file__), Path('openpilot/selfdrive/controls/lib/longitudinal_planner.py'),
           Path('openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_planner.py'),
           Path('openpilot/cereal/custom.capnp'), Path('openpilot/sunnypilot/selfdrive/controls/lib/dec/dec.py'),
           Path('openpilot/selfdrive/car/card.py'), Path('openpilot/selfdrive/car/cruise.py')]
  paths.extend(sorted(Path('openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends').rglob('*.py')))
  result['source_sha256'] = {str(p.resolve().relative_to(root)) if p.resolve().is_relative_to(root) else str(p.resolve()):
                           hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
  try:
    route = list(fixture_messages())
    for backend in range(3):
      for enabled in (False, True):
        for experimental in (False, True):
          for endpoint in (500., 5.):
            result['cases'].append(run_case(route, backend, enabled, experimental, endpoint, args.stage))
    for backend in range(3):
      for enabled in (False, True):
        for experimental in (False, True):
          result['cruise_cases'].append(cruise_case(route, backend, enabled, experimental, args.stage))
    result['passed'] = True
  except Exception:
    result['error'] = traceback.format_exc()
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(result, indent=2) + '\n')
  print(json.dumps({'artifact': str(args.output), 'passed': result['passed'], 'cases': len(result['cases'])}))
  raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
  main()
