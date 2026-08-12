from collections import deque
from types import SimpleNamespace

from opendbc.can import CANPacker
from opendbc.car.tesla import carcontroller
from opendbc.car.tesla.carcontroller import CarController, TeslaLongitudinalOwnership
from opendbc.car.tesla.cruise_diagnostics import (
  classify_cruise_snapshot,
  decode_das_control_payload,
  is_cruise_failure_after_recent_operation,
  is_cruise_failure_transition,
)
from opendbc.car.tesla.teslacan import TeslaCAN


def test_das_control_payload_diagnostics_decode_actual_packed_bytes():
  tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))
  message = tesla_can.create_longitudinal_command(4, -0.4, 6, 31.0, True)

  decoded = decode_das_control_payload(message[1])

  assert decoded == {
    "tx_raw": message[1].hex(),
    "tx_set_speed_kph": 110.2,
    "tx_state": 4,
    "tx_aeb_event": 0,
    "tx_jerk_min": -4.906,
    "tx_jerk_max": 0.034,
    "tx_accel_min": -0.4,
    "tx_accel_max": 0.0,
    "tx_counter": 6,
    "tx_checksum": message[1][7],
    "tx_checksum_expected": TeslaCAN.checksum(0x2B9, message[1][:7]),
    "tx_checksum_valid": True,
  }


def test_cruise_failure_transition_requires_operational_source_state():
  assert is_cruise_failure_transition("ENABLED", "UNAVAILABLE")
  assert is_cruise_failure_transition("STANDBY", "UNAVAILABLE")
  assert is_cruise_failure_transition("PRE_FAULT", "FAULT")
  assert not is_cruise_failure_transition(None, "UNAVAILABLE")
  assert not is_cruise_failure_transition("UNAVAILABLE", "FAULT")
  assert not is_cruise_failure_transition("ENABLED", "STANDBY")


def test_recent_operation_catches_enabled_standby_unavailable_sequence():
  history = [
    {"cruise_state": "ENABLED", "now_nanos": 1_000_000_000},
    {"cruise_state": "STANDBY", "now_nanos": 1_100_000_000},
    {"cruise_state": "UNAVAILABLE", "now_nanos": 1_200_000_000},
  ]
  assert is_cruise_failure_after_recent_operation(history, "UNAVAILABLE", 1_200_000_000)
  assert not is_cruise_failure_after_recent_operation(history, "UNAVAILABLE", 2_100_000_001)
  assert not is_cruise_failure_after_recent_operation([], "UNAVAILABLE", 1_200_000_000)


def test_classifier_separates_vehicle_fault_codes_from_correlated_candidates():
  snapshot = {
    "cruise_state": "UNAVAILABLE",
    "pmm_sys_fault_raw": 3,
    "pmm_sys_fault": "PMM_FAULT_DI_FAULT",
    "pmm_camera_fault_raw": 0,
    "pmm_radar_fault_raw": 2,
    "pmm_radar_fault": "PMM_RADAR_INVALID_MIA",
    "pmm_ultrasonics_fault_raw": 0,
    "party_can_valid": False,
    "ap_party_can_valid": True,
    "brake_pressed": True,
    "stock_aeb": False,
    "oem_2b9_age_ms": 250.0,
    "tx_state": 4,
    "cc_long_active": False,
    "tx_counter_gap": True,
  }

  classification = classify_cruise_snapshot(snapshot)

  assert classification["vehicle_reported"] == [
    "pmm_sys_fault:PMM_FAULT_DI_FAULT(3)",
    "pmm_radar_fault:PMM_RADAR_INVALID_MIA(2)",
  ]
  assert classification["correlated"] == [
    "vehicle_can_invalid",
    "brake_pressed",
    "oem_2b9_stale",
    "cp_state4_while_long_inactive",
    "cp_tx_counter_gap",
  ]


def test_classifier_marks_empty_evidence_as_undetermined():
  assert classify_cruise_snapshot({}) == {"vehicle_reported": [], "correlated": ["undetermined"]}


def test_classifier_does_not_treat_internal_handoff_marker_as_vehicle_acc_on():
  snapshot = {"tx_state": 4, "tx_aeb_event": 3, "cc_long_active": False, "tx_counter_gap": True}
  assert classify_cruise_snapshot(snapshot) == {"vehicle_reported": [], "correlated": ["undetermined"]}


def test_controller_logs_delayed_fault_for_enabled_standby_unavailable(monkeypatch):
  controller = CarController.__new__(CarController)
  controller.frame = 0
  controller.longitudinal_ownership = TeslaLongitudinalOwnership()
  controller.longitudinal_handoff_nanos = 0
  controller._cruise_state_prev = None
  controller._cruise_diag_history = deque(maxlen=40)
  controller._cruise_diag_pending = None
  controller._last_long_tx = {
    "tx_raw": "4b44a483ac7b37cf",
    "tx_set_speed_kph": 109.9,
    "tx_interval_ms": 40.0,
    "tx_checksum_valid": True,
    "tx_state": 4,
    "tx_aeb_event": 0,
    "tx_attempted_nanos": 1_000_000_000,
  }

  cc = SimpleNamespace(enabled=True, longActive=True, latActive=False,
                       cruiseControl=SimpleNamespace(cancel=False))
  cs = SimpleNamespace(cruise_state="ENABLED", das_control_nanos=1_000_000_000,
                       cruise_diagnostics={"pmm_sys_fault_raw": 0})
  events = []
  monkeypatch.setattr(carcontroller.cloudlog, "event", lambda name, **kwargs: events.append((name, kwargs)))

  controller._log_cruise_diagnostic(cc, cs, 1_000_000_000)
  controller.frame = 4
  cs.cruise_state = "STANDBY"
  controller._log_cruise_diagnostic(cc, cs, 1_100_000_000)
  controller.frame = 8
  cs.cruise_state = "UNAVAILABLE"
  cs.cruise_diagnostics = {"pmm_sys_fault_raw": 3, "pmm_sys_fault": "PMM_FAULT_DI_FAULT"}
  controller._log_cruise_diagnostic(cc, cs, 1_200_000_000)
  assert not [event for event in events if event[0] == "tesla.cruise_fault_diagnostic"]

  controller.frame = 28
  controller._log_cruise_diagnostic(cc, cs, 1_700_000_000)
  fault_events = [event for event in events if event[0] == "tesla.cruise_fault_diagnostic"]
  assert len(fault_events) == 1
  assert fault_events[0][1]["settled_classification"]["vehicle_reported"] == [
    "pmm_sys_fault:PMM_FAULT_DI_FAULT(3)",
  ]
  assert all(snapshot["tx_raw"] == "4b44a483ac7b37cf" for snapshot in fault_events[0][1]["history"])
  assert all(snapshot["tx_interval_ms"] == 40.0 for snapshot in fault_events[0][1]["history"])
