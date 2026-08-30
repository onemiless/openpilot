from pathlib import Path
from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.sunnypilot.navassist.lane_topologyd import services_healthy
from openpilot.sunnypilot.navassist.navassistd import LOCALIZATION_MAX_AGE_NS, local_localization_valid
from openpilot.sunnypilot.hardware.profile import HardwareProfile
from openpilot.system.manager import process_config


ROOT = Path(__file__).resolve().parents[3]
NAVASSIST = ROOT / "sunnypilot/navassist"


def test_network_ingress_never_imports_or_publishes_vehicle_control_interfaces():
  sources = "\n".join(path.read_text() for path in NAVASSIST.glob("*.py"))
  for forbidden in ("sendcan", "carControl.actuators", "desiredCurvature", "steeringAngleDeg"):
    assert forbidden not in sources
  assert 'PubMaster(["navAssistStateSP"])' in (NAVASSIST / "navassistd.py").read_text()


def test_track_processes_are_both_guarded_by_one_explicit_manager_predicate():
  process_config = (ROOT / "system/manager/process_config.py").read_text()
  assert 'PythonProcess("navassistd", "openpilot.sunnypilot.navassist.navassistd", navassist_track_ready)' in process_config
  assert 'PythonProcess("lane_topologyd", "openpilot.sunnypilot.navassist.lane_topologyd", navassist_track_ready)' in process_config
  predicate = process_config.split("def navassist_track_ready", 1)[1].split("def ", 1)[0]
  assert "HardwareProfile.C3XL" in predicate
  assert 'CP.brand == "tesla"' in predicate
  assert 'params.get_bool("NavAssistTrackMode")' in predicate
  assert 'params.get("NavAssistToken")' in predicate
  assert 'params.get("NavAssistTrackGeofence")' in predicate

  lane_daemon = (NAVASSIST / "lane_topologyd.py").read_text()
  assert "client.timestamp_eof" in lane_daemon
  assert "frame.timestamp_eof" not in lane_daemon
  assert "LaneTopologyUIBridge(frame_divisor=1)" in lane_daemon
  assert "bridge.last_frame_id % IMAGE_CLASSIFIER_DIVISOR" in lane_daemon


def test_planner_uses_common_target_seam_and_controlsd_is_untouched():
  common_planner = (ROOT / "sunnypilot/selfdrive/controls/lib/longitudinal_planner.py").read_text()
  controlsd = (ROOT / "selfdrive/controls/controlsd.py").read_text()
  assert "LongitudinalPlanSource.navAssist" in common_planner
  assert 'planner_verified=getattr(self, "active_backend_id", None) == BackendId.OFFICIAL' in common_planner
  assert "navAssistStateSP" not in controlsd


def test_local_localization_requires_alive_valid_and_bounded_age():
  now_ns = 1_000_000_000
  location = SimpleNamespace(
    status=log.LiveLocationKalman.Status.valid,
    positionGeodetic=SimpleNamespace(valid=True, value=[31.2, 121.4, 0.0]),
    positionECEF=SimpleNamespace(valid=True, std=[2.0, 2.0, 2.0]),
    gpsOK=True,
    inputsOK=True,
    sensorsOK=True,
    deviceStable=True,
    excessiveResets=False,
  )

  class FakeSM:
    seen = {"liveLocationKalman": True}
    alive = {"liveLocationKalman": True}
    valid = {"liveLocationKalman": True}
    logMonoTime = {"liveLocationKalman": now_ns - LOCALIZATION_MAX_AGE_NS}

    def __getitem__(self, _key):
      return location

  sm = FakeSM()
  assert local_localization_valid(sm, now_ns)
  sm.alive["liveLocationKalman"] = False
  assert not local_localization_valid(sm, now_ns)
  sm.alive["liveLocationKalman"] = True
  sm.logMonoTime["liveLocationKalman"] -= 1
  assert not local_localization_valid(sm, now_ns)
  sm.logMonoTime["liveLocationKalman"] = now_ns
  location.gpsOK = False
  assert not local_localization_valid(sm, now_ns)


def test_lane_control_inputs_require_seen_alive_and_valid():
  services = ("modelV2", "extrinsicsCalibration", "deviceState", "narrowRoadCameraState")
  sm = SimpleNamespace(
    seen=dict.fromkeys(services, True),
    alive=dict.fromkeys(services, True),
    valid=dict.fromkeys(services, True),
  )
  assert services_healthy(sm, services)
  for health in (sm.seen, sm.alive, sm.valid):
    health["modelV2"] = False
    assert not services_healthy(sm, services)
    health["modelV2"] = True


def test_track_hud_never_treats_seen_alone_as_service_health():
  hud = (ROOT / "selfdrive/ui/mici/onroad/hud_renderer.py").read_text()
  assert 'sm.alive["navAssistStateSP"] and sm.valid["navAssistStateSP"]' in hud
  assert 'ui_state.sm.alive["laneTopologyStateSP"] and ui_state.sm.valid["laneTopologyStateSP"]' in hud
  assert "NO AUTO LC" in hud
  assert "未与视觉车道对齐" in hud


class FakeParams:
  def __init__(self, *, armed=False, token="", geofence=None):
    self.values = {
      "NavAssistTrackMode": armed,
      "NavAssistToken": token,
      "NavAssistTrackGeofence": geofence,
    }

  def get_bool(self, key):
    return bool(self.values[key])

  def get(self, key):
    return self.values[key]


def test_manager_predicate_requires_c3xl_tesla_onroad_arm_secret_and_geofence(monkeypatch):
  geofence = {"coordinateSystem": "wgs84", "polygon": [[0, 0], [0, 1], [1, 1]]}
  tesla = SimpleNamespace(brand="tesla")
  monkeypatch.setattr(process_config, "get_hardware_profile", lambda: HardwareProfile.C3XL)
  assert process_config.navassist_track_ready(True, FakeParams(armed=True, token="0123456789abcdef", geofence=geofence), tesla)
  assert process_config.navassist_track_ready(True, FakeParams(armed=True, token="安全密钥六字节以上", geofence=geofence), tesla)
  assert not process_config.navassist_track_ready(False, FakeParams(armed=True, token="0123456789abcdef", geofence=geofence), tesla)
  assert not process_config.navassist_track_ready(True, FakeParams(armed=False, token="0123456789abcdef", geofence=geofence), tesla)
  assert not process_config.navassist_track_ready(True, FakeParams(armed=True, token="short", geofence=geofence), tesla)
  assert not process_config.navassist_track_ready(True, FakeParams(armed=True, token="0123456789abcdef"), tesla)
  assert not process_config.navassist_track_ready(
    True, FakeParams(armed=True, token="0123456789abcdef", geofence=geofence), SimpleNamespace(brand="honda"),
  )
  monkeypatch.setattr(process_config, "get_hardware_profile", lambda: HardwareProfile.STANDARD)
  assert not process_config.navassist_track_ready(True, FakeParams(armed=True, token="0123456789abcdef", geofence=geofence), tesla)
