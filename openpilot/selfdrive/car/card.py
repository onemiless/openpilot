#!/usr/bin/env python3
import os
import time
import threading
import traceback

import openpilot.cereal.messaging as messaging

from openpilot.cereal import log, custom
from opendbc.car.structs import car

from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, Priority, Ratekeeper
from openpilot.common.swaglog import cloudlog, ForwardingHandler

from opendbc.car import DT_CTRL, structs
from opendbc.car.can_definitions import CanData, CanRecvCallable, CanSendCallable
from opendbc.car.carlog import carlog
from opendbc.car.fw_versions import ObdCallback
from opendbc.car.car_helpers import get_car, interfaces
from opendbc.car.interfaces import CarInterfaceBase, RadarInterfaceBase
from openpilot.selfdrive.pandad import can_capnp_to_list, can_list_to_can_capnp
from openpilot.selfdrive.car.cruise import VCruiseHelper
from openpilot.selfdrive.car.helpers import convert_carControlSP, convert_to_capnp
from openpilot.selfdrive.car.tesla_can_probe import TeslaCanProbe

from openpilot.sunnypilot.mads.helpers import set_alternative_experience, set_car_specific_params
from openpilot.sunnypilot.selfdrive.car import interfaces as sunnypilot_interfaces
from opendbc.sunnypilot.car.tesla.dynamic_acc_debug import log_dynamic_acc
from opendbc.sunnypilot.car.tesla.values import TeslaSafetyFlagsSP

REPLAY = "REPLAY" in os.environ

EventName = log.OnroadEvent.EventName
TESLA_LONGITUDINAL_CONTEXT_STALE_S = 0.2
TESLA_LANE_CHANGE_CONTEXT_STALE_S = 0.5

# forward
carlog.addHandler(ForwardingHandler(cloudlog))


def get_tesla_longitudinal_context(sm: messaging.SubMaster, now: float) -> tuple[int, bool, bool, float, bool, bool, bool, float, bool, float, bool]:
  plan = sm['longitudinalPlanSP']
  plan_source = int(getattr(plan.longitudinalPlanSource, "raw", plan.longitudinalPlanSource))
  plan_recv_time = float(sm.recv_time['longitudinalPlanSP'])
  plan_valid = (sm.seen['longitudinalPlanSP'] and sm.valid['longitudinalPlanSP'] and
                now - plan_recv_time <= TESLA_LONGITUDINAL_CONTEXT_STALE_S)

  car_control = sm['carControl']
  car_control_valid = (sm.seen['carControl'] and sm.valid['carControl'] and
                       now - sm.recv_time['carControl'] <= TESLA_LONGITUDINAL_CONTEXT_STALE_S)
  lane_change_active = bool(car_control.leftBlinker or car_control.rightBlinker)
  lane_change_valid = car_control_valid
  selfdrive_state_sp = sm['selfdriveStateSP']
  mads_state_valid = (sm.seen['selfdriveStateSP'] and sm.valid['selfdriveStateSP'] and
                      now - sm.recv_time['selfdriveStateSP'] <= TESLA_LONGITUDINAL_CONTEXT_STALE_S)
  lateral_control_ready = ((lane_change_valid and bool(car_control.latActive)) or
                           (mads_state_valid and bool(selfdrive_state_sp.mads.active)))
  return (plan_source, sm.updated['longitudinalPlanSP'], plan_valid, plan_recv_time,
          lane_change_active, lane_change_valid, lateral_control_ready, now,
          bool(car_control.longActive), float(car_control.actuators.accel), car_control_valid)


def get_tesla_speed_limit_context(sm: messaging.SubMaster, now: float) -> tuple[float, bool, float]:
  plan = sm['longitudinalPlanSP']
  plan_recv_time = float(sm.recv_time['longitudinalPlanSP'])
  plan_valid = (sm.seen['longitudinalPlanSP'] and sm.valid['longitudinalPlanSP'] and
                now - plan_recv_time <= TESLA_LONGITUDINAL_CONTEXT_STALE_S)
  resolver = plan.speedLimit.resolver
  limit_valid = bool(resolver.speedLimitValid or resolver.speedLimitLastValid)
  target = float(resolver.speedLimitFinalLast)
  valid = plan_valid and limit_valid and target > 0.0
  return (target if valid else 0.0, valid, plan_recv_time)


def obd_callback(params: Params) -> ObdCallback:
  def set_obd_multiplexing(obd_multiplexing: bool):
    if params.get_bool("ObdMultiplexingEnabled") != obd_multiplexing:
      cloudlog.warning(f"Setting OBD multiplexing to {obd_multiplexing}")
      params.remove("ObdMultiplexingChanged")
      params.put_bool("ObdMultiplexingEnabled", obd_multiplexing, block=True)
      params.get_bool("ObdMultiplexingChanged", block=True)
      cloudlog.warning("OBD multiplexing set successfully")
  return set_obd_multiplexing


def can_comm_callbacks(logcan: messaging.SubSocket, sendcan: messaging.PubSocket) -> tuple[CanRecvCallable, CanSendCallable]:
  def can_recv(wait_for_one: bool = False) -> list[list[CanData]]:
    """
    wait_for_one: wait the normal logcan socket timeout for a CAN packet, may return empty list if nothing comes

    Returns: CAN packets comprised of CanData objects for easy access
    """
    ret = []
    for can in messaging.drain_sock(logcan, wait_for_one=wait_for_one):
      ret.append([CanData(msg.address, msg.dat, msg.src) for msg in can.can])
    return ret

  def can_send(msgs: list[CanData]) -> None:
    sendcan.send(can_list_to_can_capnp(msgs, msgtype='sendcan'))

  return can_recv, can_send


class Car:
  CI: CarInterfaceBase
  RI: RadarInterfaceBase
  CP: car.CarParams
  CP_SP: structs.CarParamsSP
  CP_SP_capnp: custom.CarParamsSP

  def __init__(self, CI=None, RI=None) -> None:
    self.can_sock = messaging.sub_sock('can', timeout=20)
    self.sm = messaging.SubMaster(['pandaStates', 'carControl', 'onroadEvents', 'modelV2'] +
                                  ['carControlSP', 'longitudinalPlanSP', 'selfdriveStateSP'])
    self.pm = messaging.PubMaster(['sendcan', 'carState', 'carParams', 'carOutput', 'liveTracks'] + ['carParamsSP', 'carStateSP'])

    self.can_rcv_cum_timeout_counter = 0
    self.dynamic_acc_last_blocked_log_nanos = 0

    self.CC_prev = car.CarControl.new_message()
    self.CS_prev = car.CarState.new_message()
    self.CS_SP_prev = custom.CarStateSP.new_message()
    self.initialized_prev = False

    self.last_actuators_output = structs.CarControl.Actuators()

    self.params = Params()

    self.can_callbacks = can_comm_callbacks(self.can_sock, self.pm.sock['sendcan'])

    is_release = False  # self.params.get_bool("IsReleaseBranch")
    is_release_sp = self.params.get_bool("IsReleaseSpBranch")

    if CI is None:
      # wait for one pandaState and one CAN packet
      print("Waiting for CAN messages...")
      while True:
        can = messaging.recv_one_retry(self.can_sock)
        if len(can.can) > 0:
          break

      alpha_long_allowed = self.params.get_bool("AlphaLongitudinalEnabled")

      cached_params = None
      cached_params_raw = self.params.get("CarParamsCache")
      if cached_params_raw is not None:
        with car.CarParams.from_bytes(cached_params_raw) as _cached_params:
          cached_params = _cached_params

      fixed_fingerprint = (self.params.get("CarPlatformBundle") or {}).get("platform", None)
      init_params_list_sp = sunnypilot_interfaces.initialize_params(self.params)

      self.CI = get_car(*self.can_callbacks, obd_callback(self.params), alpha_long_allowed, is_release, cached_params,
                        fixed_fingerprint, init_params_list_sp, is_release_sp)
      sunnypilot_interfaces.setup_interfaces(self.CI, self.params)
      self.RI = interfaces[self.CI.CP.carFingerprint].RadarInterface(self.CI.CP, self.CI.CP_SP)
      self.CP = self.CI.CP
      self.CP_SP = self.CI.CP_SP

      # continue onto next fingerprinting step in pandad
      self.params.put_bool("FirmwareQueryDone", True, block=True)
    else:
      self.CI, self.CP, self.CP_SP = CI, CI.CP, CI.CP_SP
      self.RI = RI

    self.tesla_can_probe = TeslaCanProbe(
      self.CP.brand == 'tesla' and self.params.get_bool("TeslaCanValidationLogging")
    )
    self.tesla_turn_signal_controller = None
    self.tesla_road_context_parser = None
    if self.CP.brand == 'tesla':
      # DAS_road is visualization-only and is absent on some Tesla hardware.
      # Keep it outside the CarState parser so an absent optional frame can
      # never invalidate vehicle CAN or trigger a car-unrecognized event.
      from opendbc.can import CANParser
      from opendbc.car import Bus
      from opendbc.car.tesla.values import CANBUS, DBC
      from openpilot.selfdrive.car.tesla_turn_signal_controller import TeslaTurnSignalRealtimeController

      self.tesla_road_context_parser = CANParser(DBC[self.CP.carFingerprint][Bus.party], [("DAS_road", float("nan"))], CANBUS.party)
      configured = bool(self.CP_SP.safetyParam & TeslaSafetyFlagsSP.TURN_SIGNAL_VALIDATION)
      self.tesla_turn_signal_controller = TeslaTurnSignalRealtimeController(configured)

    self.CP.alternativeExperience = 0
    # mads
    set_alternative_experience(self.CP, self.CP_SP, self.params)
    set_car_specific_params(self.CP, self.CP_SP, self.params)

    # Dynamic Experimental Control
    self.dynamic_experimental_control = self.params.get_bool("DynamicExperimentalControl")

    openpilot_enabled_toggle = self.params.get_bool("OpenpilotEnabledToggle")
    controller_available = self.CI.CC is not None and openpilot_enabled_toggle and not self.CP.dashcamOnly
    self.CP.passive = not controller_available or self.CP.dashcamOnly
    if self.CP.passive:
      safety_config = structs.CarParams.SafetyConfig()
      safety_config.safetyModel = structs.CarParams.SafetyModel.noOutput
      self.CP.safetyConfigs = [safety_config]

    if self.CP.secOcRequired:
      # Copy user key if available
      try:
        with open("/cache/params/SecOCKey") as f:
          user_key = f.readline().strip()
          if len(user_key) == 32:
            self.params.put("SecOCKey", user_key, block=True)
      except Exception:
        pass

      secoc_key = self.params.get("SecOCKey")
      if secoc_key is not None:
        saved_secoc_key = bytes.fromhex(secoc_key.strip())
        if len(saved_secoc_key) == 16:
          self.CP.secOcKeyAvailable = True
          self.CI.CS.secoc_key = saved_secoc_key
          if controller_available:
            self.CI.CC.secoc_key = saved_secoc_key
        else:
          cloudlog.warning("Saved SecOC key is invalid")

    # Write previous route's CarParams
    prev_cp = self.params.get("CarParamsPersistent")
    if prev_cp is not None:
      self.params.put("CarParamsPrevRoute", prev_cp, block=True)

    # Write CarParams for controls and radard
    cp_bytes = self.CP.to_bytes()
    self.params.put("CarParams", cp_bytes, block=True)
    self.params.put("CarParamsCache", cp_bytes)
    self.params.put("CarParamsPersistent", cp_bytes)

    # Write CarParamsSP for controls
    # convert to pycapnp representation for caching and logging
    self.CP_SP_capnp = convert_to_capnp(self.CP_SP)
    cp_sp_bytes = self.CP_SP_capnp.to_bytes()
    self.params.put("CarParamsSP", cp_sp_bytes, block=True)
    self.params.put("CarParamsSPCache", cp_sp_bytes)
    self.params.put("CarParamsSPPersistent", cp_sp_bytes)

    self.v_cruise_helper = VCruiseHelper(self.CP, self.CP_SP)

    self.is_metric = self.params.get_bool("IsMetric")
    self.experimental_mode = self.params.get_bool("ExperimentalMode")

    # card is driven by can recv, expected at 100Hz
    self.rk = Ratekeeper(100, print_delay_threshold=None)

    # log fingerprint in sentry
    sunnypilot_interfaces.log_fingerprint(self.CP)

  def state_update(self) -> tuple[car.CarState, custom.CarStateSP, structs.RadarDataT | None]:
    """carState update loop, driven by can"""

    can_strs = messaging.drain_sock_raw(self.can_sock, wait_for_one=True)
    can_list = can_capnp_to_list(can_strs)
    self.tesla_can_probe.update_can(can_list)
    if self.CP.brand == 'tesla':
      for mono_time, frames in can_list:
        for address, data, source in frames:
          if self.tesla_turn_signal_controller is not None:
            self.tesla_turn_signal_controller.observe_frame(mono_time, address, data, source)
          if source == 1 and address == 0x3C2 and hasattr(self.CI.CS, "update_speed_button_template"):
            self.CI.CS.update_speed_button_template(data, mono_time)
          if source == 192 and address == 0x2B9 and mono_time - self.dynamic_acc_last_blocked_log_nanos >= 100_000_000:
            self.dynamic_acc_last_blocked_log_nanos = mono_time
            log_dynamic_acc("card", "safety_blocked_das_control", mono_time=mono_time, data=data.hex())
      if self.tesla_turn_signal_controller is not None:
        turn_signal_now_nanos = int(time.monotonic() * 1e9)
        self.tesla_turn_signal_controller.advance_time(turn_signal_now_nanos)
        # Cancellation must not depend on controlsd/carControl remaining alive.
        # Normal action frames still only leave through controls_update().
        cancel_sends = self.tesla_turn_signal_controller.take_can_sends(turn_signal_now_nanos, cancel_only=True)
        if cancel_sends:
          self.can_callbacks[1](cancel_sends)

    # Update carState from CAN
    CS, CS_SP = self.CI.update(can_list)
    if self.tesla_road_context_parser is not None:
      from opendbc.sunnypilot.car.tesla.carstate_ext import publish_tesla_road_context

      self.tesla_road_context_parser.update(can_list)
      road_values = self.tesla_road_context_parser.vl["DAS_road"]
      road_timestamp_ns = self.tesla_road_context_parser.ts_nanos["DAS_road"]["DAS_stopLineDist"]
      publish_tesla_road_context(CS_SP, road_values, road_timestamp_ns, time.monotonic_ns())
    CS_SP = convert_to_capnp(CS_SP)

    # Update radar tracks from CAN
    RD: structs.RadarDataT | None = self.RI.update(can_list)

    self.sm.update(0)

    if self.CP.brand == 'tesla' and hasattr(self.CI.CS, "update_longitudinal_context"):
      now = time.monotonic()
      self.CI.CS.update_longitudinal_context(*get_tesla_longitudinal_context(self.sm, now))
      if hasattr(self.CI.CS, "update_speed_limit_target"):
        target, valid, _ = get_tesla_speed_limit_context(self.sm, now)
        self.CI.CS.update_speed_limit_target(target, valid)

    can_rcv_valid = len(can_strs) > 0

    # Check for CAN timeout
    if not can_rcv_valid:
      self.can_rcv_cum_timeout_counter += 1

    if can_rcv_valid and REPLAY:
      self.can_log_mono_time = messaging.log_from_bytes(can_strs[0]).logMonoTime

    self.v_cruise_helper.update_speed_limit_assist(self.is_metric, self.sm['longitudinalPlanSP'])
    self.v_cruise_helper.update_v_cruise(CS, self.sm['carControl'].enabled, self.is_metric)
    if self.sm['carControl'].enabled and not self.CC_prev.enabled:
      # Use CarState w/ buttons from the step selfdrived enables on
      self.v_cruise_helper.initialize_v_cruise(self.CS_prev, self.experimental_mode, self.dynamic_experimental_control)

    # TODO: mirror the carState.cruiseState struct?
    CS.vCruise = float(self.v_cruise_helper.v_cruise_kph)
    CS.vCruiseCluster = float(self.v_cruise_helper.v_cruise_cluster_kph)
    self.tesla_can_probe.update_state(CS, CS_SP)

    return CS, CS_SP, RD

  def state_publish(self, CS: car.CarState, CS_SP: custom.CarStateSP, RD: structs.RadarDataT | None):
    """carState and carParams publish loop"""

    # carParams - logged every 50 seconds (> 1 per segment)
    if self.sm.frame % int(50. / DT_CTRL) == 0:
      cp_send = messaging.new_message('carParams')
      cp_send.valid = True
      cp_send.carParams = self.CP
      self.pm.send('carParams', cp_send)

    # publish new carOutput
    co_send = messaging.new_message('carOutput')
    co_send.valid = self.sm.all_checks(['carControl'])
    co_send.carOutput.actuatorsOutput = self.last_actuators_output
    self.pm.send('carOutput', co_send)

    # CS and CS_SP vehicle state comes from the same CI.update() cycle, and shared
    # state such as vCruise is finalized before state_publish(). Publish the SP
    # companion first because carState wakes selfdrived's control cycle. The
    # canErrorCounter/cumLagMs values added below are carState-only metadata.
    cs_sp_send = messaging.new_message('carStateSP')
    cs_sp_send.valid = CS.canValid
    cs_sp_send.carStateSP = CS_SP
    self.pm.send('carStateSP', cs_sp_send)

    # kick off controlsd step while we actuate the latest carControl packet
    cs_send = messaging.new_message('carState')
    cs_send.valid = CS.canValid
    cs_send.carState = CS
    cs_send.carState.canErrorCounter = self.can_rcv_cum_timeout_counter
    cs_send.carState.cumLagMs = -self.rk.remaining * 1000.
    self.pm.send('carState', cs_send)

    if RD is not None:
      tracks_msg = messaging.new_message('liveTracks')
      tracks_msg.valid = not any(RD.errors.to_dict().values())
      tracks_msg.liveTracks = RD
      self.pm.send('liveTracks', tracks_msg)

    # carParamsSP - logged every 50 seconds (> 1 per segment)
    if self.sm.frame % int(50. / DT_CTRL) == 0:
      cp_sp_send = messaging.new_message('carParamsSP')
      cp_sp_send.valid = True
      cp_sp_send.carParamsSP = self.CP_SP_capnp
      self.pm.send('carParamsSP', cp_sp_send)

  def controls_update(self, CS: car.CarState, CC: car.CarControl, CC_SP: custom.CarControlSP):
    """control update loop, driven by carControl"""

    if not self.initialized_prev:
      # Initialize CarInterface, once controls are ready
      # TODO: this can make us miss at least a few cycles when doing an ECU knockout
      self.CI.init(self.CP, self.CP_SP, *self.can_callbacks)
      # signal pandad to switch to car safety mode
      self.params.put_bool("ControlsReady", True)

    if self.sm.all_alive(['carControl']):
      # send car controls over can
      now_nanos = self.can_log_mono_time if REPLAY else int(time.monotonic() * 1e9)
      try:
        self.last_actuators_output, can_sends = self.CI.apply(CC, convert_carControlSP(CC_SP), now_nanos)
      except Exception as error:
        if self.CP.brand == 'tesla':
          log_dynamic_acc(
            "card", "apply_exception",
            sync=True,
            error=repr(error),
            traceback=traceback.format_exc(),
            cc_enabled=CC.enabled,
            cc_long_active=CC.longActive,
            cruise_enabled=CS.cruiseState.enabled,
            car_state_sp_flags=int(self.CS_SP_prev.flags),
          )
        raise
      if self.tesla_turn_signal_controller is not None:
        context_now = time.monotonic()
        model_valid = (self.sm.seen['modelV2'] and self.sm.valid['modelV2'] and
                       context_now - self.sm.recv_time['modelV2'] <= TESLA_LANE_CHANGE_CONTEXT_STALE_S)
        lane_change_meta = self.sm['modelV2'].meta
        self.tesla_turn_signal_controller.update_lane_change_context(
          now_nanos,
          valid=model_valid,
          state=int(getattr(lane_change_meta.laneChangeState, "raw", lane_change_meta.laneChangeState)),
          direction=int(getattr(lane_change_meta.laneChangeDirection, "raw", lane_change_meta.laneChangeDirection)),
          lateral_active=bool(CC.latActive),
          brake_pressed=bool(CS.brakePressed),
        )
        can_sends.extend(self.tesla_turn_signal_controller.take_can_sends(now_nanos))
      self.pm.send('sendcan', can_list_to_can_capnp(can_sends, msgtype='sendcan', valid=CS.canValid))

      self.CC_prev = CC

  def step(self):
    CS, CS_SP, RD = self.state_update()

    self.state_publish(CS, CS_SP, RD)

    initialized = (not any(e.name == EventName.selfdriveInitializing for e in self.sm['onroadEvents']) and
                   self.sm.seen['onroadEvents'])
    if not self.CP.passive and initialized:
      self.controls_update(CS, self.sm['carControl'], self.sm['carControlSP'])

    self.initialized_prev = initialized
    self.CS_prev = CS
    self.CS_SP_prev = CS_SP

  def params_thread(self, evt):
    while not evt.is_set():
      self.is_metric = self.params.get_bool("IsMetric")
      self.experimental_mode = self.params.get_bool("ExperimentalMode") and self.CP.openpilotLongitudinalControl

      # sunnypilot
      self.dynamic_experimental_control = self.params.get_bool("DynamicExperimentalControl")
      self.v_cruise_helper.read_custom_set_speed_params()
      if self.tesla_turn_signal_controller is not None:
        self.tesla_turn_signal_controller.service_params(self.params)

      time.sleep(0.1)

  def card_thread(self):
    e = threading.Event()
    t = threading.Thread(target=self.params_thread, args=(e, ))
    try:
      t.start()
      while True:
        self.step()
        self.rk.monitor_time()
    finally:
      e.set()
      t.join()


def main():
  config_realtime_process(4, Priority.CTRL_HIGH)
  car = Car()
  car.card_thread()


if __name__ == "__main__":
  main()
