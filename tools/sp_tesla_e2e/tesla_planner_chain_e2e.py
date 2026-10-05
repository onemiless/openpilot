#!/usr/bin/env python3
"""Offline actual planner/solver -> publisher -> LongControl and Params process checks."""
import argparse
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import platform
import signal
import tempfile
import threading
import time
from types import SimpleNamespace as ns
from unittest.mock import patch

from openpilot.cereal import custom, log, messaging
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params, ParamKeyFlag
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.factory import create_longitudinal_planner
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.longcontrol_factory import create_long_control
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.session import latch_active_backend
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.tuning import (
  apply_backend_profile, save_backend_values, DEFAULT_VALUES, LongitudinalTuning, adjusted_obstacle,
)
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.registry import get_backend
from openpilot.sunnypilot.selfdrive.traffic_control.controller import TrafficControlPhase
from openpilot.sunnypilot.selfdrive.traffic_control.final_plan_arbitrator import FinalPlanArbitrator
from openpilot.tools.lib.logreader import LogReader

FIXTURE = Path('openpilot/sunnypilot/selfdrive/controls/tests/fixtures/tesla_legacy_planner_warm.rlog.zst')


class Inputs:
  def __init__(self, route):
    names = ['carControl', 'carState', 'controlsState', 'vehicleParameters', 'radarState', 'modelV2',
             'selfdriveState', 'carStateSP', 'selfdriveStateSP', 'liveMapDataSP', 'trafficRadarState',
             get_gps_location_service(Params())]
    self.values = {s: getattr(messaging.new_message(s), s) for s in names}
    for m in route:
      if m.which() in self.values:
        self.values[m.which()] = getattr(m.as_builder(), m.which())
    self.seen = dict.fromkeys(names, True)
    self.valid = dict.fromkeys(names, True)
    self.alive = dict.fromkeys(names, True)
    self.logMonoTime = dict.fromkeys(names, 1_000_000_000)
    self.frame = 1

  def __getitem__(self, service):
    return self.values[service]

  def all_checks(self, service_list=None):
    return all(self.seen[s] and self.valid[s] and self.alive[s] for s in service_list or self.values)


class Published:
  def __init__(self):
    self.messages = {}

  def send(self, service, message):
    self.messages[service] = message.as_reader()


def control_chain(route, cold_start=False):
  cp = next(m.carParams for m in route if m.which() == 'carParams')
  cp_sp = custom.CarParamsSP.new_message()
  records = []
  faults = ['normal-model-residue'] if cold_start else [
    'normal-model-residue', 'force-decel', 'missing', 'invalid', 'unseen', 'dead', 'gas', 'brake', 'physical-lead']
  for backend in range(3):
    for fault in faults:
      with OpenpilotPrefix():
        p = Params()
        p.put('LongitudinalPlannerMode', backend, block=True)
        planner = create_longitudinal_planner(cp, cp_sp, params=p)
        controller = create_long_control(cp, cp_sp, params=p)
        sm = Inputs(route)
        sm['carState'].vEgo = 0.
        sm['carState'].aEgo = 0.
        sm['carState'].vCruise = 50.
        sm['carState'].vCruiseCluster = 50.
        sm['carState'].gasPressed = False
        sm['carState'].brakePressed = False
        sm['carState'].cruiseState.standstill = False
        sm['carControl'].enabled = True
        sm['carControl'].longActive = True
        # Replay the inactive initialization cycle before engagement, just as
        # the onroad processes normally do. Also captures legacy init/reset.
        sm['controlsState'].longControlState = 'off'
        sm['selfdriveState'].enabled = True
        sm['selfdriveState'].experimentalMode = True
        sm['modelV2'].action.shouldStop = True
        sm['modelV2'].action.desiredAcceleration = -0.5
        sm['radarState'].leadOne.present = False
        sm['radarState'].leadTwo.present = False
        arb = FinalPlanArbitrator(cp)
        pm = Published()
        t = sm['trafficRadarState']
        t.mode = 4
        t.phase = int(TrafficControlPhase.hold)
        t.lightState = 1
        t.targetPresent = True
        t.confidence = 1.
        t.stopControlAllowed = True
        t.stopSafetyAllowed = True
        t.shouldStop = True
        t.stopSessionId = 100
        t.eventId = 100
        t.publishMonoTime = 1_000_000_000
        if not cold_start:
          planner.update(sm)
        sm['controlsState'].longControlState = 'stopping'
        try:
          planner.update(sm)
        except AttributeError as error:
          if not cold_start:
            raise
          records.append({'backend': backend, 'case': 'first-frame-engaged', 'error': str(error), 'passed': False})
          continue
        planner.publish(sm, arb.publisher(pm, sm, 1_000_000_000))
        held = pm.messages['longitudinalPlan'].longitudinalPlan
        controller.update(True, sm['carState'], held.aTarget, held.shouldStop, [-3.5, 2.0])
        t.phase = int(TrafficControlPhase.release)
        t.lightState = 2
        t.targetPresent = False
        t.plannerStartRequested = True
        t.shouldStop = False
        t.publishMonoTime = 1_050_000_000
        sm['controlsState'].forceDecel = fault == 'force-decel'
        planner.update(sm)
        base = Published()
        planner.publish(sm, base)
        if fault == 'missing':
          sm.values.pop('controlsState')
          sm.seen.pop('controlsState')
        elif fault in ('invalid', 'unseen', 'dead'):
          getattr(sm, {'invalid': 'valid', 'unseen': 'seen', 'dead': 'alive'}[fault])['controlsState'] = False
        elif fault in ('gas', 'brake'):
          setattr(sm['carState'], fault + 'Pressed', True)
        elif fault == 'physical-lead':
          sm['radarState'].leadOne.present = True
          sm['radarState'].leadOne.dRel = 4.
        # Missing controlsState cannot be handed back to planner.publish; the
        # missing-service case enters the same sink with the actual base message.
        sink = arb.publisher(pm, sm, 1_050_000_000)
        sink.send('longitudinalPlan', base.messages['longitudinalPlan'].as_builder())
        sink.send('longitudinalPlanSP', base.messages['longitudinalPlanSP'].as_builder())
        final = pm.messages['longitudinalPlan'].longitudinalPlan
        accel = controller.update(True, sm['carState'], final.aTarget, final.shouldStop, [-3.5, 2.0])
        go = bool(arb.diagnostics.start_applied)
        passed = (go and final.aTarget > 0 and not final.shouldStop and accel > 0) if fault == 'normal-model-residue' else (
          not go and final.aTarget <= 0 and accel <= 0)
        records.append({'backend': backend, 'case': fault, 'base_aTarget': float(base.messages['longitudinalPlan'].longitudinalPlan.aTarget),
                        'final_aTarget': float(final.aTarget), 'shouldStop': bool(final.shouldStop),
                        'startApplied': go, 'blockReason': int(arb.diagnostics.start_block_reason),
                        'controlAccel': float(accel), 'dec_instantiated': planner.dec is not None,
                        'tn_stopping_policy': controller.stopping_policy is not None, 'passed': bool(passed)})
  return records


def latch_worker(directory, delayed, ready, release, done, queue):
  class DelayedParams(Params):
    def get(self, key, *args, **kwargs):
      result = super().get(key, *args, **kwargs)
      if delayed and key == 'LongitudinalPlannerMode':
        ready.set()
        if not release.wait(10):
          raise RuntimeError('parent failed to release latch worker')
      return result
  try:
    queue.put(int(latch_active_backend(DelayedParams(directory)).id))
  finally:
    done.set()


def process_latch():
  ctx = mp.get_context('spawn')
  records = []
  with tempfile.TemporaryDirectory(prefix='tesla-latch-e2e-') as directory:
    p = Params(directory)
    for iteration in range(5):
      p.remove('ActiveLongitudinalBackend')
      p.put('LongitudinalPlannerMode', 0, block=True)
      ready, release, done_a, done_b = [ctx.Event() for _ in range(4)]
      queue = ctx.Queue()
      a = ctx.Process(target=latch_worker, args=(directory, True, ready, release, done_a, queue))
      b = ctx.Process(target=latch_worker, args=(directory, False, ready, release, done_b, queue))
      a.start()
      if not ready.wait(10):
        a.terminate()
        raise RuntimeError('latch process A did not reach read boundary')
      p.put('LongitudinalPlannerMode', 2, block=True)
      b.start()
      done_b.wait(0.5)
      release.set()
      for child in (a, b):
        child.join(10)
        if child.is_alive():
          child.terminate()
          child.join()
        if child.exitcode != 0:
          raise RuntimeError(f'latch child exit={child.exitcode}')
      ids = [queue.get(timeout=2), queue.get(timeout=2)]
      active = p.get('ActiveLongitudinalBackend')
      restart = int(latch_active_backend(Params(directory)).id)
      records.append({'iteration': iteration, 'worker_ids': ids, 'active': active, 'restart': restart,
                      'passed': ids == [0, 0] and active == restart == 0})
  return records


def transition_worker(directory, ready, release, queue, ignore_stop, stubborn):
  # Simulate a late startup write even after manager requests graceful stop.
  # Real manager must join/kill it before clearing a completed session.
  if ignore_stop:
    signal.signal(signal.SIGINT, signal.SIG_IGN)

  class DelayedParams(Params):
    def get(self, key, *args, **kwargs):
      result = super().get(key, *args, **kwargs)
      if key == 'LongitudinalPlannerMode':
        ready.set()
        if stubborn:
          # SIGKILL must not kill a child while holding multiprocessing.Event's
          # condition semaphore, which would wedge this offline harness cleanup.
          while True:
            time.sleep(0.05)
        if not release.wait(15):
          raise RuntimeError('transition worker was not released')
      return result
  queue.put(int(latch_active_backend(DelayedParams(directory)).id))


def manager_transition_case(name, stubborn):
  from openpilot.system.manager import manager
  from openpilot.system.manager.process import ManagerProcess
  ctx = mp.get_context('spawn')
  records = []
  # Both real latch consumers, plus a stubborn process requiring SIGKILL.
  with tempfile.TemporaryDirectory(prefix='tesla-session-transition-') as directory:
    ready, release = ctx.Event(), ctx.Event()
    queue = ctx.Queue()

    class Consumer(ManagerProcess):
      def __init__(self, process_name):
        self.name = process_name
        self.should_run = lambda started, params, cp: started
        self.last_exit = None

      def start(self):
        if self.name == name and self.proc is None:
          self.proc = ctx.Process(target=transition_worker, args=(directory, ready, release, queue, True, stubborn))
          self.proc.start()

      def stop(self, *args, **kwargs):
        code = super().stop(*args, **kwargs)
        if code is not None:
          self.last_exit = code
        return code

    processes = {n: Consumer(n) for n in ('plannerd', 'controlsd')}
    clears = []

    class ObservedParams(Params):
      def clear_all(self, flag=ParamKeyFlag.ALL):
        if flag == ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION:
          clears.append({'consumer_alive': any(p.proc is not None and p.proc.is_alive() for p in processes.values()),
                         'active_before_clear': self.get('ActiveLongitudinalBackend')})
        super().clear_all(flag)

    params = ObservedParams(directory)
    params.put('LongitudinalPlannerMode', 0, block=True)
    params.put('DongleId', 'offline-e2e', block=True)
    timers = []

    class DeviceInputs:
      def __init__(self):
        self.iteration = 0
        self.values = {'deviceState': ns(started=False), 'carParams': next(
          m.carParams for m in LogReader(str(FIXTURE)) if m.which() == 'carParams'), 'pandaStates': []}

      def __getitem__(self, key):
        return self.values[key]

      def all_checks(self, services):
        return False  # No power-watchdog writes in this offline scenario.

      def update(self, timeout):
        self.iteration += 1
        self.values['deviceState'].started = self.iteration == 1
        if self.iteration == 2:
          if not ready.wait(10):
            raise RuntimeError('onroad consumer did not reach desired-read boundary')
          params.put('LongitudinalPlannerMode', 2, block=True)
          if not stubborn:
            timer = threading.Timer(0.2, release.set)
            timer.start()
            timers.append(timer)
          params.put_bool('DoShutdown', True, block=True)

    no_log = ns(bind=lambda **kwargs: None, info=lambda *args: None,
                debug=lambda *args: None, warning=lambda *args: None)
    try:
      with patch.object(manager, 'Params', return_value=params), \
           patch.object(manager, 'managed_processes', processes), \
           patch.object(manager.messaging, 'SubMaster', return_value=DeviceInputs()), \
           patch.object(manager.messaging, 'PubMaster', return_value=Published()), \
           patch.object(manager, 'cloudlog', no_log):
        manager.manager_thread()
      # Baseline manager only requested nonblocking stop. Let its delayed
      # write finish, then collect the stale result. New manager already joined.
      release.set()
      for process in processes.values():
        process.stop(block=True)
      old_id = None if processes[name].last_exit == -signal.SIGKILL else queue.get(timeout=2)
      active_after = params.get('ActiveLongitudinalBackend')
      next_id = int(latch_active_backend(Params(directory)).id)
      records.append({'consumer': name, 'stubborn': stubborn, 'old_exit': processes[name].last_exit,
                      'old_backend': old_id, 'offroad_clears': clears, 'active_after_offroad': active_after,
                      'desired': params.get('LongitudinalPlannerMode'), 'next_session_backend': next_id,
                      'passed': bool(clears and not clears[0]['consumer_alive'] and active_after is None and next_id == 2)})
    finally:
      release.set()
      for timer in timers:
        timer.join()
      for process in processes.values():
        process.stop(block=True)
  return records[0]


def manager_transition():
  return [manager_transition_case(name, stubborn)
          for name, stubborn in [('plannerd', False), ('controlsd', False), ('plannerd', True)]]

def non_tesla_scope(route):
  cp = next(m.carParams for m in route if m.which() == 'carParams').as_builder()
  cp.brand = 'toyota'
  records = []
  for desired in (1, 2):
    with OpenpilotPrefix():
      params = Params()
      params.put('LongitudinalPlannerMode', desired, block=True)
      for backend in range(3):
        apply_backend_profile(params, get_backend(backend), 1)
      planner = create_longitudinal_planner(cp, custom.CarParamsSP.new_message(), params=params)
      controller = create_long_control(cp, custom.CarParamsSP.new_message(), params=params)
      passed = (int(planner.active_backend_id) == 0 and planner.mpc._tuning_controller is None
                and controller.stopping_policy is None and params.get('ActiveLongitudinalBackend') is None)
      records.append({'brand': cp.brand, 'desired': desired, 'provider': type(planner).__module__,
                      'active': params.get('ActiveLongitudinalBackend'), 'passed': passed})
  return records


def official_default_parity():
  from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc
  actual = {
    't_follow_relaxed': long_mpc.get_T_FOLLOW(log.LongitudinalPersonality.relaxed),
    't_follow_standard': long_mpc.get_T_FOLLOW(log.LongitudinalPersonality.standard),
    't_follow_aggressive': long_mpc.get_T_FOLLOW(log.LongitudinalPersonality.aggressive),
    'x_ego_obstacle_cost': long_mpc.X_EGO_OBSTACLE_COST,
    'j_ego_cost': long_mpc.J_EGO_COST, 'a_change_cost': long_mpc.A_CHANGE_COST,
    'danger_zone_cost': long_mpc.DANGER_ZONE_COST, 'lead_danger_factor': long_mpc.LEAD_DANGER_FACTOR,
    'comfort_brake': long_mpc.COMFORT_BRAKE, 'stop_distance': long_mpc.STOP_DISTANCE,
  }
  return {'upstream': actual, 'differences': [key for key, value in actual.items() if value != DEFAULT_VALUES[key]]}


def replay_rows():
  from openpilot.selfdrive.test.process_replay.process_replay import replay_process_with_name
  rows = {}
  for backend in range(3):
    for profile in range(3):
      for e2e in (False, True):
        with OpenpilotPrefix():
          p = Params()
          if profile == 2:
            values = {**DEFAULT_VALUES, 't_follow_relaxed': 1.85, 'comfort_brake': 2.8, 'stop_distance': 4.7}
            save_backend_values(p, get_backend(backend), values, 2)
          else:
            apply_backend_profile(p, get_backend(backend), profile)
          config = p.get('LongitudinalTuningConfig')
        messages = []
        for reader in LogReader(str(FIXTURE)):
          m = reader.as_builder()
          if m.which() == 'selfdriveState':
            m.selfdriveState.experimentalMode = e2e
          messages.append(m.as_reader())
        outputs = replay_process_with_name('plannerd', messages, fingerprint='TESLA_MODEL_Y',
          custom_params={'LongitudinalPlannerMode': backend, 'LongitudinalTuningConfig': config,
            'AccelPersonalityEnabled': True, 'AccelPersonality': 1, 'DynamicExperimentalControl': False,
            'SmartCruiseControlVision': False, 'SmartCruiseControlMap': False, 'SpeedLimitMode': 0}, disable_progress=True)
        key = f'{backend}:{profile}:{int(e2e)}'
        rows[key] = []
        for m in outputs:
          if m.which() == 'longitudinalPlan':
            v = m.longitudinalPlan
            rows[key].append({'aTarget': v.aTarget, 'shouldStop': v.shouldStop, 'allowThrottle': v.allowThrottle,
                             'source': str(v.longitudinalPlanSource), 'speeds': list(v.speeds),
                             'accels': list(v.accels), 'jerks': list(v.jerks)})
  return rows


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--mode', choices=['p1', 'replay', 'cold-start', 'non-tesla', 'session-transition'], default='p1')
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--baseline', type=Path)
  args = parser.parse_args()
  result = {'scope': 'offline actual solver/publish/LongControl plus spawned Params processes; no CAN/device/road',
            'platform': platform.platform(), 'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            'mode': args.mode, 'device_validation': 'pending'}
  if args.mode == 'session-transition':
    result['transitions'] = manager_transition()
    result['passed'] = all(r['passed'] for r in result['transitions'])
  elif args.mode == 'non-tesla':
    result['scope_cases'] = non_tesla_scope(list(LogReader(str(FIXTURE))))
    result['passed'] = all(r['passed'] for r in result['scope_cases'])
  elif args.mode == 'cold-start':
    result['chain'] = control_chain(list(LogReader(str(FIXTURE))), cold_start=True)
    result['passed'] = all(r['passed'] for r in result['chain'])
  elif args.mode == 'p1':
    result['chain'] = control_chain(list(LogReader(str(FIXTURE))))
    result['multiprocess'] = process_latch()
    result['official_default_parity'] = official_default_parity()
    result['tuning_metadata'] = {spec.slug: {'approximate_fields': sorted(spec.approximate_tuning_fields),
                                           'notice': spec.tuning_notice} for spec in [get_backend(i) for i in range(3)]}
    raw_obstacle = 100. + 10. ** 2 / (2 * 2.5)
    translated = adjusted_obstacle(raw_obstacle, 10., 20., LongitudinalTuning(comfort_brake=3.), 1.45)
    translated_gap = translated - (10. ** 2 / (2 * 2.5) + 1.45 * 10. + 6.)
    exact_gap = 100. + 10. ** 2 / (2 * 3.) - (10. ** 2 / (2 * 3.) + 1.45 * 10. + 6.)
    result['official_translation_residual_m'] = translated_gap - exact_gap
    result['passed'] = (all(r['passed'] for group in ('chain', 'multiprocess') for r in result[group])
                        and not result['official_default_parity']['differences'])
  else:
    result['replay'] = replay_rows()
    result['passed'] = True
    if args.baseline:
      baseline = json.loads(args.baseline.read_text())
      result['baseline_sha256'] = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
      result['differences'] = [k for k, v in result['replay'].items() if v != baseline['replay'][k]]
      result['passed'] = not result['differences']
  backend_root = Path('openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends')
  paths = [Path(__file__), Path('openpilot/sunnypilot/selfdrive/traffic_control/final_plan_arbitrator.py'),
           Path('openpilot/selfdrive/controls/lib/longitudinal_planner.py'),
           Path('openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py'), *sorted(backend_root.rglob('*.py'))]
  paths.append(Path('openpilot/system/manager/manager.py'))
  result['source_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
  result['solver_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((backend_root / 'legacy_mpc').glob('c_generated_code*/acados_ocp_solver_pyx.so'))}
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(result, indent=2) + '\n')
  print(json.dumps({'artifact': str(args.output), 'passed': result['passed']}))
  raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
  main()
