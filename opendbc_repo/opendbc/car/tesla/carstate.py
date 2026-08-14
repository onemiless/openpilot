import copy
import math
from opendbc.can import CANDefine, CANParser
from opendbc.car import Bus, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase
from opendbc.car.tesla.mads_touch import MadsTouchInput
from opendbc.car.tesla.values import DBC, CANBUS, GEAR_MAP, STEER_DISENGAGE_THRESHOLD, STEER_THRESHOLD
from opendbc.car.vehicle_model import VehicleModel
from opendbc.safety import ALTERNATIVE_EXPERIENCE

ButtonType = structs.CarState.ButtonEvent.Type
TESLA_SPEED_LIMIT_MIN_KPH = 30.0
TESLA_SPEED_LIMIT_MAX_KPH = 150.0


def normalize_tesla_speed_limit(display_limit: float, units: str) -> float | None:
  if not math.isfinite(display_limit) or display_limit <= 0:
    return None
  limit_kph = display_limit if units == "KPH" else display_limit * CV.MPH_TO_KPH if units == "MPH" else 0.0
  if not TESLA_SPEED_LIMIT_MIN_KPH <= limit_kph <= TESLA_SPEED_LIMIT_MAX_KPH:
    return None
  return float(limit_kph)


def classify_steering_input(hands_on_level: int, steering_torque: float, eac_status: str | None,
                            eac_error_code: int, cooperative_steering: bool) -> tuple[bool, bool]:
  del cooperative_steering
  strong_driver_override = hands_on_level >= 3 or abs(steering_torque) > STEER_DISENGAGE_THRESHOLD
  high_angle_rate_fault = eac_status == "EAC_INHIBITED" and eac_error_code == 9
  return False, high_angle_rate_fault or strong_driver_override


def calculate_yaw_rate(vehicle_model, speed_mps, steering_angle_deg):
  """Estimate yaw rate from steering angle using the vehicle model."""
  if not math.isfinite(speed_mps) or not math.isfinite(steering_angle_deg) or abs(speed_mps) < 0.05:
    return 0.0
  curvature = -vehicle_model.calc_curvature(math.radians(steering_angle_deg), abs(speed_mps), 0.0)
  return float(curvature * abs(speed_mps))


class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.VM = VehicleModel(CP)
    self.can_define = CANDefine(DBC[CP.carFingerprint][Bus.party])
    self.shifter_values = self.can_define.dv["DI_systemStatus"]["DI_gear"]

    self.hands_on_level = 0
    self.eac_status = None
    self.eac_error_code = 0
    self.das_control = None
    self.das_control_nanos = 0
    self.cruise_state = None
    self.cruise_diagnostics = {}
    self.tesla_speed_units = "KPH"
    self.tesla_autopilot_active = False
    self.tesla_fused_speed_limit_kph = 0.0
    self.tesla_fused_speed_limit_valid = False
    self.tesla_fused_speed_limit_nanos = 0
    self.mads_touch_input = MadsTouchInput(bool(CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ENABLE_MADS))

  def observe_aux_can(self, address, data, source):
    # Card applies parameter-derived alternativeExperience after constructing CarState.
    self.mads_touch_input.set_enabled(bool(self.CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ENABLE_MADS))
    self.mads_touch_input.observe(address, data, source)

  def update(self, can_parsers) -> structs.CarState:
    cp_party = can_parsers[Bus.party]
    cp_ap_party = can_parsers[Bus.ap_party]
    ret = structs.CarState()

    # Vehicle speed
    ret.vEgoRaw = cp_party.vl["DI_speed"]["DI_vehicleSpeed"] * CV.KPH_TO_MS
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)

    # Gas pedal
    pedal_status = cp_party.vl["DI_systemStatus"]["DI_accelPedalPos"]
    ret.gas = pedal_status / 100.0
    ret.gasPressed = pedal_status > 0

    # Brake pedal
    ret.brake = 0
    ret.brakePressed = cp_party.vl["IBST_status"]["IBST_driverBrakeApply"] == 2

    # Steering wheel
    epas_status = cp_party.vl["EPAS3S_sysStatus"]
    self.hands_on_level = epas_status["EPAS3S_handsOnLevel"]
    ret.handsOnLevel = self.hands_on_level
    ret.steeringAngleDeg = -epas_status["EPAS3S_internalSAS"]
    ret.steeringRateDeg = -cp_ap_party.vl["SCCM_steeringAngleSensor"]["SCCM_steeringAngleSpeed"]
    ret.steeringTorque = -epas_status["EPAS3S_torsionBarTorque"]
    ret.yawRate = calculate_yaw_rate(self.VM, ret.vEgoRaw, ret.steeringAngleDeg)

    # Match SP cooperative steering: recognize sustained light driver input
    # promptly, without treating a single noisy torque sample as an override.
    ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > STEER_THRESHOLD, 5)

    eac_status_raw = int(epas_status["EPAS3S_eacStatus"])
    self.eac_status = self.can_define.dv["EPAS3S_sysStatus"]["EPAS3S_eacStatus"].get(eac_status_raw, None)
    self.eac_error_code = int(epas_status["EPAS3S_eacErrorCode"])
    ret.eacStatus = eac_status_raw
    ret.eacErrorCode = self.eac_error_code
    ret.steerFaultPermanent = self.eac_status == "EAC_FAULT"
    ret.steerFaultTemporary = self.eac_status == "EAC_INHIBITED"
    cooperative_steering = bool(self.CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.MADS_COOPERATIVE_STEERING)
    ret.steeringOverride, ret.steeringDisengage = classify_steering_input(
      self.hands_on_level, ret.steeringTorque, self.eac_status, self.eac_error_code, cooperative_steering,
    )

    # Cruise state
    cruise_state = self.can_define.dv["DI_state"]["DI_cruiseState"].get(int(cp_party.vl["DI_state"]["DI_cruiseState"]), None)
    self.cruise_state = cruise_state
    speed_units = self.can_define.dv["DI_state"]["DI_speedUnits"].get(int(cp_party.vl["DI_state"]["DI_speedUnits"]), None)
    if speed_units in ("KPH", "MPH"):
      self.tesla_speed_units = speed_units

    ret.cruiseState.enabled = cruise_state in ("ENABLED", "STANDSTILL", "OVERRIDE", "PRE_FAULT", "PRE_CANCEL")
    if speed_units == "KPH":
      ret.cruiseState.speed = max(cp_party.vl["DI_state"]["DI_digitalSpeed"] * CV.KPH_TO_MS, 1e-3)
    elif speed_units == "MPH":
      ret.cruiseState.speed = max(cp_party.vl["DI_state"]["DI_digitalSpeed"] * CV.MPH_TO_MS, 1e-3)
    ret.cruiseState.available = cruise_state == "STANDBY" or ret.cruiseState.enabled
    ret.cruiseState.standstill = False  # This needs to be false, since we can resume from stop without sending anything special
    ret.standstill = cruise_state == "STANDSTILL"
    ret.accFaulted = cruise_state == "FAULT"

    # Gear
    ret.gearShifter = GEAR_MAP[self.can_define.dv["DI_systemStatus"]["DI_gear"].get(int(cp_party.vl["DI_systemStatus"]["DI_gear"]), "DI_GEAR_INVALID")]

    # Doors
    ret.doorOpen = cp_party.vl["UI_warning"]["anyDoorOpen"] == 1

    # Blinkers
    ret.leftBlinker = cp_party.vl["UI_warning"]["leftBlinkerBlinking"] in (1, 2)
    ret.rightBlinker = cp_party.vl["UI_warning"]["rightBlinkerBlinking"] in (1, 2)

    # Seatbelt
    ret.seatbeltUnlatched = cp_party.vl["UI_warning"]["buckleStatus"] != 1

    # Blindspot
    das_status = cp_ap_party.vl["DAS_status"]
    ret.leftBlindspot = das_status["DAS_blindSpotRearLeft"] != 0
    ret.rightBlindspot = das_status["DAS_blindSpotRearRight"] != 0
    fused_limit = normalize_tesla_speed_limit(float(das_status["DAS_fusedSpeedLimit"]), self.tesla_speed_units)
    self.tesla_fused_speed_limit_valid = fused_limit is not None
    self.tesla_fused_speed_limit_kph = fused_limit or 0.0
    if self.tesla_fused_speed_limit_valid:
      self.tesla_fused_speed_limit_nanos = int(cp_ap_party.ts_nanos["DAS_status"]["DAS_fusedSpeedLimit"])

    # AEB
    ret.stockAeb = cp_ap_party.vl["DAS_control"]["DAS_aebEvent"] == 1

    # Stock Autosteer should be off (includes FSD)
    ret.invalidLkasSetting = cp_ap_party.vl["DAS_settings"]["DAS_autosteerEnabled"] != 0
    autopilot_state = int(das_status["DAS_autopilotState"])
    self.tesla_autopilot_active = autopilot_state not in (0, 1, 2)

    # The Tesla center display reports active touch points on the vehicle bus.
    ret.buttonEvents = self.mads_touch_input.take_button_events()

    # Messages needed by carcontroller
    self.das_control = copy.copy(cp_ap_party.vl["DAS_control"])
    self.das_control_nanos = int(cp_ap_party.ts_nanos["DAS_control"]["DAS_controlCounter"])
    das_status2 = cp_ap_party.vl["DAS_status2"]
    diagnostic_signals = {
      "pmm_sys_fault": "DAS_pmmSysFaultReason",
      "pmm_camera_fault": "DAS_pmmCameraFaultReason",
      "pmm_radar_fault": "DAS_pmmRadarFaultReason",
      "pmm_ultrasonics_fault": "DAS_pmmUltrasonicsFaultReason",
      "acc_report": "DAS_ACC_report",
      "activation_failure": "DAS_activationFailureStatus",
      "obstacle_severity": "DAS_pmmObstacleSeverity",
    }
    self.cruise_diagnostics = {
      "party_can_valid": bool(cp_party.can_valid),
      "ap_party_can_valid": bool(cp_ap_party.can_valid),
      "party_bus_timeout": bool(cp_party.bus_timeout),
      "ap_party_bus_timeout": bool(cp_ap_party.bus_timeout),
      "brake_pressed": bool(ret.brakePressed),
      "gas_pressed": bool(ret.gasPressed),
      "stock_aeb": bool(ret.stockAeb),
      "v_ego": round(float(ret.vEgo), 3),
      "a_ego": round(float(ret.aEgo), 3),
      "oem_2b9_nanos": self.das_control_nanos,
      "oem_2b9_state": int(self.das_control["DAS_accState"]),
      "oem_2b9_aeb_event": int(self.das_control["DAS_aebEvent"]),
      "oem_2b9_counter": int(self.das_control["DAS_controlCounter"]),
      "oem_2b9_set_speed_kph": float(self.das_control["DAS_setSpeed"]),
      "oem_2b9_accel_min": float(self.das_control["DAS_accelMin"]),
      "oem_2b9_accel_max": float(self.das_control["DAS_accelMax"]),
      "oem_2b9_jerk_min": float(self.das_control["DAS_jerkMin"]),
      "oem_2b9_jerk_max": float(self.das_control["DAS_jerkMax"]),
    }
    for key, signal in diagnostic_signals.items():
      raw = int(das_status2[signal])
      self.cruise_diagnostics[f"{key}_raw"] = raw
      self.cruise_diagnostics[key] = self.can_define.dv["DAS_status2"][signal].get(raw, f"UNKNOWN_{raw}")

    return ret

  @staticmethod
  def get_can_parsers(CP):
    return {
      Bus.party: CANParser(DBC[CP.carFingerprint][Bus.party], [], CANBUS.party),
      Bus.ap_party: CANParser(DBC[CP.carFingerprint][Bus.party], [], CANBUS.autopilot_party)
    }
