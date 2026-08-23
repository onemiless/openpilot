from __future__ import annotations

from openpilot.sunnypilot.selfdrive.car.tesla.control_runtime import TeslaControlState, state_is_fresh
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP


def nav_longitudinal_allowed(sm, is_tesla: bool) -> bool:
  car_control = sm['carControl']
  car_state = sm['carState']
  if (not car_control.enabled or not car_control.longActive or car_control.cruiseControl.override
      or car_state.gasPressed or car_state.brakePressed):
    return False
  if not is_tesla:
    return True
  if not (sm.seen['carStateSP'] and sm.alive['carStateSP'] and sm.valid['carStateSP']
          and state_is_fresh(sm.logMonoTime['carState'], sm.logMonoTime['carStateSP'])):
    return False
  state = TeslaControlState(TeslaFlagsSP(int(sm['carStateSP'].flags)))
  return not state.stock_longitudinal and not state.exit_recovery
