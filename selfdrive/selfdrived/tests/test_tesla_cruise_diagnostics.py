from collections import deque
from types import SimpleNamespace

from openpilot.selfdrive.selfdrived import selfdrived
from openpilot.selfdrive.selfdrived.selfdrived import SelfdriveD


def _can_state(**overrides):
  values = {
    "busOff": False, "busOffCnt": 0, "errorWarning": False, "errorPassive": False,
    "lastError": SimpleNamespace(raw=0), "receiveErrorCnt": 0, "transmitErrorCnt": 0,
    "totalErrorCnt": 0, "totalTxLostCnt": 0, "totalRxLostCnt": 0,
  }
  values.update(overrides)
  return SimpleNamespace(**values)


class FakeSubMaster(dict):
  def __init__(self, values):
    super().__init__(values)
    self.frame = 1200
    self.valid = dict.fromkeys(values, True)
    self.alive = dict.fromkeys(values, True)


def test_tesla_cruise_system_log_includes_recent_panda_tx_rejection(monkeypatch):
  panda = SimpleNamespace(
    controlsAllowed=False, controlsAllowedLateral=True, controlsAllowedLongitudinal=False,
    safetyRxChecksInvalid=False, safetyRxInvalid=0, safetyTxBlocked=11,
    heartbeatLost=False, faultStatus=SimpleNamespace(raw=0), faults=[], uptime=120,
    rxBufferOverflow=0, txBufferOverflow=0, safetyModel=SimpleNamespace(raw=10), safetyParam=1,
    canState0=_can_state(), canState1=_can_state(), canState2=_can_state(),
  )
  radar_errors = SimpleNamespace(canError=False, wrongConfig=False, radarUnavailableTemporary=False, radarFault=False)
  car_control = SimpleNamespace(enabled=False, longActive=False, latActive=True,
                                cruiseControl=SimpleNamespace(cancel=True))
  daemon = SelfdriveD.__new__(SelfdriveD)
  daemon.CP = SimpleNamespace(brand="tesla", openpilotLongitudinalControl=True)
  daemon.CS_prev = SimpleNamespace(cruiseState=SimpleNamespace(available=True, enabled=True), accFaulted=False)
  daemon.enabled = False
  daemon.active = False
  daemon.state_machine = SimpleNamespace(state="disabled")
  daemon.events = SimpleNamespace(names=[], event_counters={})
  daemon.sm = FakeSubMaster({
    "pandaStates": [panda], "radarState": SimpleNamespace(radarErrors=radar_errors), "carControl": car_control,
  })
  daemon._tesla_safety_tx_blocked_prev = [10]
  daemon._tesla_safety_tx_block_history = deque(maxlen=50)
  cs = SimpleNamespace(
    cruiseState=SimpleNamespace(available=False, enabled=False), accFaulted=True,
    brakePressed=True, gasPressed=False, vEgo=12.5, canValid=True, canTimeout=False,
  )
  events = []
  monkeypatch.setattr(selfdrived.cloudlog, "event", lambda name, **kwargs: events.append((name, kwargs)))
  daemon._log_tesla_cruise_system_diagnostic(cs)
  assert events[0][0] == "tesla.cruise_system_diagnostic"
  assert events[0][1]["panda_states"][0]["safety_tx_blocked_delta"] == 1
  assert events[0][1]["recent_safety_tx_blocks"] == [{"frame": 1200, "counters": [11], "deltas": [1]}]
