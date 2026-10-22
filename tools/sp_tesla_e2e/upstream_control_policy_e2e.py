#!/usr/bin/env python3
"""Native Params/schema/cruise compatibility E2E; no device or physical CAN."""
import argparse
import hashlib
import inspect
import json
import subprocess
import tempfile
from pathlib import Path
from openpilot.cereal import log, custom
from openpilot.common.params import Params
from openpilot.selfdrive.car.cruise import VCruiseHelper
from opendbc.car import structs
from opendbc.car.tesla.interface import CarInterface
from opendbc.car.tesla.values import CAR
from openpilot.sunnypilot.system.params_migration import _migrate_car_params

assert log.SelfdriveState.schema.fields['experimentalMode'].proto.ordinal.explicit == 10
assert custom.OnroadEventSP.EventName.experimentalModeSwitched == 14
with tempfile.TemporaryDirectory() as tmp:
  p = Params(tmp)
  p.put_bool('ExperimentalMode', True, block=True)
  cp = CarInterface.get_non_essential_params(CAR.TESLA_MODEL_Y)
  sp = CarInterface.get_non_essential_params_sp(cp, CAR.TESLA_MODEL_Y)
  old = cp.as_reader().as_builder()
  old.deprecated.mass = 2000
  old.rotationalInertiaPerMass = 4000
  old.tireStiffnessFrontPerMass = 200000
  old.tireStiffnessRearPerMass = 240000
  raw = old.to_bytes()
  keys = ('CarParams', 'CarParamsCache', 'CarParamsPersistent', 'CarParamsPrevRoute')
  for key in keys:
    p.put(key, raw, block=True)
  _migrate_car_params(p)
  backup = p.get('SPCarParamsMassNormalizationBackup')
  for key in keys:
    assert bytes.fromhex(backup[key]) == raw
    with structs.CarParams.from_bytes(p.get(key)) as cp_new:
      assert cp_new.deprecated.mass == 0
      assert cp_new.rotationalInertiaPerMass == 2
      assert cp_new.tireStiffnessFrontPerMass == 100
      assert cp_new.tireStiffnessRearPerMass == 120
  before = {key: p.get(key) for key in keys}
  _migrate_car_params(p)
  assert before == {key: p.get(key) for key in keys}
  assert backup == p.get('SPCarParamsMassNormalizationBackup')
  cs = structs.CarState.new_message(vEgo=0)
  cp.pcmCruise = False
  helper = VCruiseHelper(cp, sp)
  helper.initialize_v_cruise(cs, 60)
  assert helper.v_cruise_kph == 60
  # Restore through native Params before switching back to an old manager that deletes unknown keys.
  for key in keys:
    p.put(key, bytes.fromhex(backup[key]), block=True)
  assert all(p.get(key) == raw for key in keys)
  _migrate_car_params(p)
  assert before == {key: p.get(key) for key in keys}
  # A different existing backup must stop the migration without writing any CP value.
  for key in keys:
    p.put(key, raw, block=True)
  p.put('SPCarParamsMassNormalizationBackup', {'CarParams': '00'}, block=True)
  try:
    _migrate_car_params(p)
  except ValueError:
    pass
  else:
    raise AssertionError('conflicting backup was overwritten')
  assert all(p.get(key) == raw for key in keys)
  invalid = old.as_reader().as_builder()
  invalid.deprecated.mass = float('nan')
  invalid_raw = invalid.to_bytes()
  p.put('CarParams', invalid_raw, block=True)
  try:
    _migrate_car_params(p)
  except ValueError:
    pass
  else:
    raise AssertionError('nonfinite mass was migrated')
  assert p.get('CarParams') == invalid_raw
  result = {
    'schema_contract': True,
    'params_migration': True,
    'idempotence': True,
    'exact_backup': True,
    'exact_rollback': True,
    'backup_conflict_fail_closed': True,
    'nonfinite_mass_fail_closed': True,
    'official_initial_speed': True,
  }

from openpilot.common.prefix import OpenpilotPrefix
from openpilot.sunnypilot.selfdrive.car.cruise_helpers import CruiseHelper
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP
from openpilot.system.manager.process_config import managed_processes

result['legacy_gap_button'] = []
cp.openpilotLongitudinalControl = True
for backend in range(3):
  with OpenpilotPrefix():
    p = Params()
    p.put('LongitudinalPlannerMode', backend, block=True)
    p.put_bool('ExperimentalMode', False, block=True)
    helper = CruiseHelper(cp)
    cs = structs.CarState.new_message()
    cs.cruiseState.available = True
    cs.buttonEvents = [{'type': 'gapAdjustCruise', 'pressed': True}]
    events = EventsSP()
    helper.update(cs, events, False)
    cs.buttonEvents = []
    for _ in range(50):
      helper.update(cs, events, False)
    import time

    deadline = time.monotonic() + 2
    while p.get_bool('ExperimentalMode') != (backend != 0) and time.monotonic() < deadline:
      time.sleep(0.01)
    assert p.get_bool('ExperimentalMode') == (backend != 0)
    assert (custom.OnroadEventSP.EventName.experimentalModeSwitched in events.names) == (backend != 0)
    result['legacy_gap_button'].append({'backend': backend, 'toggled': backend != 0})
assert all(name in managed_processes for name in ('navd', 'mapsd', 'modeld_warmup'))
result['navigation_warmup_registered'] = True
result['passed'] = True
result['head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
result['source_sha256'] = {
  str(p): hashlib.sha256(p.read_bytes()).hexdigest()
  for p in [
    Path(__file__),
    Path(inspect.getfile(CruiseHelper)),
    Path('openpilot/sunnypilot/system/params_migration.py'),
    Path('openpilot/common/params_keys.h'),
    Path('openpilot/cereal/log.capnp'),
    Path('openpilot/cereal/custom.capnp'),
  ]
}
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(args.output)
