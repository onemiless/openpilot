from collections import deque
from types import SimpleNamespace

from opendbc.can import CANPacker
from opendbc.car.tesla import carcontroller
from opendbc.car.tesla.carcontroller import CarController, TeslaLongitudinalOwnership
from opendbc.car.tesla.cruise_diagnostics import classify_cruise_snapshot, decode_das_control_payload
from opendbc.car.tesla.teslacan import TeslaCAN


def test_decode_records_complete_packed_das_control():
  tesla_can = TeslaCAN(CANPacker("tesla_model3_party"))
  message = tesla_can.create_longitudinal_command(4, -0.4, 6, 31.0, True)
  decoded = decode_das_control_payload(message[1])
  assert decoded["tx_raw"] == message[1].hex()
  assert decoded["tx_set_speed_kph"] == 110.2
  assert decoded["tx_state"] == 4
  assert decoded["tx_accel_min"] == -0.4
  assert decoded["tx_counter"] == 6
  assert decoded["tx_checksum_valid"] is True


def test_classifier_separates_reported_faults_from_correlations():
  snapshot = {
    "pmm_sys_fault_raw": 3,
    "pmm_sys_fault": "PMM_FAULT_DI_FAULT",
    "party_can_valid": True,
    "ap_party_can_valid": True,
    "tx_counter_gap": True,
    "tx_interval_ms": 58.0,
  }
  assert classify_cruise_snapshot(snapshot) == {
    "vehicle_reported": ["pmm_sys_fault:PMM_FAULT_DI_FAULT(3)"],
    "correlated": ["cp_tx_counter_gap", "cp_tx_interval_long"],
  }


def test_fault_event_contains_tx_history(monkeypatch):
  controller = CarController.__new__(CarController)
  controller.frame = 0
  controller.longitudinal_ownership = TeslaLongitudinalOwnership()
  controller._cruise_state_prev = "ENABLED"
  controller._cruise_diag_history = deque(maxlen=50)
  controller._last_long_tx = {
    "tx_raw": "0040a4832c7a17df", "tx_state": 4, "tx_counter": 3,
    "tx_interval_ms": 40.0, "tx_counter_gap": False,
    "tx_attempted_nanos": 1_000_000_000,
  }
  cc = SimpleNamespace(enabled=True, longActive=True, latActive=False,
                       cruiseControl=SimpleNamespace(cancel=False))
  cs = SimpleNamespace(cruise_state="FAULT", cruise_diagnostics={"pmm_sys_fault_raw": 0})
  events = []
  monkeypatch.setattr(carcontroller.cloudlog, "event", lambda name, **kwargs: events.append((name, kwargs)))
  controller.log_cruise_diagnostic(cc, cs, 1_040_000_000)
  assert events[0][0] == "tesla.cruise_fault_diagnostic"
  assert events[0][1]["history"][-1]["tx_raw"] == "0040a4832c7a17df"
