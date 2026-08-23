"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

import math

import numpy as np

from openpilot.cereal import messaging, custom
from opendbc.car import structs
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.car.cruise import V_CRUISE_MAX
from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController
from openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper import E2EAlertsHelper
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.smart_cruise_control import SmartCruiseControl
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_assist import SpeedLimitAssist
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import SpeedLimitResolver
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP
from openpilot.sunnypilot.models.helpers import get_active_bundle
from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.selfdrive.car.tesla.control_runtime import TeslaControlState, state_is_fresh
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP

DecState = custom.LongitudinalPlanSP.DynamicExperimentalControl.DynamicExperimentalControlState
LongitudinalPlanSource = custom.LongitudinalPlanSP.LongitudinalPlanSource


class LongitudinalPlannerSP:
  def __init__(self, CP: structs.CarParams, CP_SP: structs.CarParamsSP, mpc, *, enable_dec: bool = True):
    self.events_sp = EventsSP()
    self.resolver = SpeedLimitResolver()
    self.dec = DynamicExperimentalController(CP, mpc) if enable_dec else None
    self.scc = SmartCruiseControl()
    self.resolver = SpeedLimitResolver()
    self.sla = SpeedLimitAssist(CP, CP_SP)
    self.generation = int(model_bundle.generation) if (model_bundle := get_active_bundle()) else None
    self.source = LongitudinalPlanSource.cruise
    self.e2e_alerts_helper = E2EAlertsHelper()
    self.params = Params()
    self.nav_params = NavAssistParams.read(self.params)
    self.nav_param_frame = 0
    self.is_tesla = CP.brand == "tesla"
    self.openpilot_longitudinal_control = bool(CP.openpilotLongitudinalControl)

    self.output_v_target = 0.
    self.output_a_target = 0.

  def is_e2e(self, sm: messaging.SubMaster) -> bool:
    experimental_mode = sm['selfdriveState'].experimentalMode
    if not self.dec.active():
      return experimental_mode

    return experimental_mode and self.dec.mode() == "blended"

  def update_targets(self, sm: messaging.SubMaster, v_ego: float, a_ego: float, v_cruise: float) -> tuple[float, float]:
    CS = sm['carState']
    v_cruise_cluster_kph = min(CS.vCruiseCluster, V_CRUISE_MAX)
    v_cruise_cluster = v_cruise_cluster_kph * CV.KPH_TO_MS

    long_enabled = sm['carControl'].enabled
    long_override = sm['carControl'].cruiseControl.override

    # Smart Cruise Control
    self.scc.update(sm, long_enabled, long_override, v_ego, a_ego, v_cruise)

    # Speed Limit Resolver
    self.resolver.update(v_ego, sm)

    # Speed Limit Assist
    has_speed_limit = self.resolver.speed_limit_valid or self.resolver.speed_limit_last_valid
    self.sla.update(long_enabled, long_override, v_ego, a_ego, v_cruise_cluster, self.resolver.speed_limit,
                    self.resolver.speed_limit_final_last, has_speed_limit, self.resolver.distance, self.events_sp)

    targets = {
      LongitudinalPlanSource.cruise: (v_cruise, a_ego),
      LongitudinalPlanSource.sccVision: (self.scc.vision.output_v_target, self.scc.vision.output_a_target),
      LongitudinalPlanSource.sccMap: (self.scc.map.output_v_target, self.scc.map.output_a_target),
      LongitudinalPlanSource.speedLimitAssist: (self.sla.output_v_target, self.sla.output_a_target),
    }

    if self.nav_param_frame % 20 == 0:
      self.nav_params = NavAssistParams.read(self.params)
    self.nav_param_frame += 1
    nav_target = self._get_nav_assist_target(sm, v_ego, a_ego, v_cruise)
    if nav_target is not None:
      targets[LongitudinalPlanSource.navAssist] = nav_target

    self.source = min(targets, key=lambda k: targets[k][0])
    self.output_v_target, self.output_a_target = targets[self.source]
    return self.output_v_target, self.output_a_target

  def _get_nav_assist_target(self, sm: messaging.SubMaster, v_ego: float, a_ego: float,
                             v_cruise: float) -> tuple[float, float] | None:
    p = self.nav_params
    if (not p.enabled or p.shadow_mode or not p.speed_control or not self.openpilot_longitudinal_control
        or not sm['carControl'].enabled or not sm['carControl'].longActive
        or sm['carControl'].cruiseControl.override or sm['carState'].gasPressed or sm['carState'].brakePressed):
      return None
    if not (sm.seen['navAssistSP'] and sm.alive['navAssistSP'] and sm.valid['navAssistSP']):
      return None
    if self.is_tesla:
      if not (sm.seen['carStateSP'] and sm.valid['carStateSP'] and
              state_is_fresh(sm.logMonoTime['carState'], sm.logMonoTime['carStateSP'])):
        return None
      state = TeslaControlState(TeslaFlagsSP(int(sm['carStateSP'].flags)))
      if state.stock_longitudinal or state.exit_recovery:
        return None
    nav = sm['navAssistSP']
    target = float(nav.desiredSpeedMps)
    distance = float(nav.speedControlDistanceM)
    if (not nav.dataValid or nav.stale or nav.offRoute or nav.speedSource == "none"
        or not math.isfinite(target) or not math.isfinite(distance)
        or target <= 0.0 or target >= v_cruise - 0.1 or distance < 0.0):
      return None
    distance = max(distance, 5.0)
    accel = float(np.clip((target ** 2 - v_ego ** 2) / (2.0 * distance), -2.5, 0.0))
    return min(target, v_cruise), min(a_ego, accel)

  def update(self, sm: messaging.SubMaster) -> None:
    self.events_sp.clear()
    self._update_backend(sm)
    self.e2e_alerts_helper.update(sm, self.events_sp)

  def _update_backend(self, sm: messaging.SubMaster) -> None:
    """Backend extension point; the upstream provider keeps DEC unchanged."""
    self.dec.update(sm)

  def _publish_backend_state(self, longitudinal_plan_sp) -> None:
    """Publish backend-specific diagnostics without forking the common plan."""
    dec = longitudinal_plan_sp.dec
    dec.state = DecState.blended if self.dec.mode() == 'blended' else DecState.acc
    dec.enabled = self.dec.enabled()
    dec.active = self.dec.active()

  def publish_longitudinal_plan_sp(self, sm: messaging.SubMaster, pm: messaging.PubMaster) -> None:
    plan_sp_send = messaging.new_message('longitudinalPlanSP')

    plan_sp_send.valid = sm.all_checks(service_list=['carState', 'controlsState'])

    longitudinalPlanSP = plan_sp_send.longitudinalPlanSP
    longitudinalPlanSP.longitudinalPlanSource = self.source
    longitudinalPlanSP.vTarget = float(self.output_v_target)
    longitudinalPlanSP.aTarget = float(self.output_a_target)
    longitudinalPlanSP.events = self.events_sp.to_msg()

    self._publish_backend_state(longitudinalPlanSP)

    # Smart Cruise Control
    smartCruiseControl = longitudinalPlanSP.smartCruiseControl
    # Vision Control
    sccVision = smartCruiseControl.vision
    sccVision.state = self.scc.vision.state
    sccVision.vTarget = float(self.scc.vision.output_v_target)
    sccVision.aTarget = float(self.scc.vision.output_a_target)
    sccVision.currentLateralAccel = float(self.scc.vision.current_lat_acc)
    sccVision.maxPredictedLateralAccel = float(self.scc.vision.max_pred_lat_acc)
    sccVision.enabled = self.scc.vision.is_enabled
    sccVision.active = self.scc.vision.is_active
    # Map Control
    sccMap = smartCruiseControl.map
    sccMap.state = self.scc.map.state
    sccMap.vTarget = float(self.scc.map.output_v_target)
    sccMap.aTarget = float(self.scc.map.output_a_target)
    sccMap.enabled = self.scc.map.is_enabled
    sccMap.active = self.scc.map.is_active

    # Speed Limit
    speedLimit = longitudinalPlanSP.speedLimit
    resolver = speedLimit.resolver
    resolver.speedLimit = float(self.resolver.speed_limit)
    resolver.speedLimitLast = float(self.resolver.speed_limit_last)
    resolver.speedLimitFinal = float(self.resolver.speed_limit_final)
    resolver.speedLimitFinalLast = float(self.resolver.speed_limit_final_last)
    resolver.speedLimitValid = self.resolver.speed_limit_valid
    resolver.speedLimitLastValid = self.resolver.speed_limit_last_valid
    resolver.speedLimitOffset = float(self.resolver.speed_limit_offset)
    resolver.distToSpeedLimit = float(self.resolver.distance)
    resolver.source = self.resolver.source
    assist = speedLimit.assist
    assist.state = self.sla.state
    assist.enabled = self.sla.is_enabled
    assist.active = self.sla.is_active
    assist.vTarget = float(self.sla.output_v_target)
    assist.aTarget = float(self.sla.output_a_target)

    # E2E Alerts
    e2eAlerts = longitudinalPlanSP.e2eAlerts
    e2eAlerts.greenLightAlert = self.e2e_alerts_helper.green_light_alert
    e2eAlerts.leadDepartAlert = self.e2e_alerts_helper.lead_depart_alert

    pm.send('longitudinalPlanSP', plan_sp_send)
