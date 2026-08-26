from openpilot.sunnypilot.navassist.config import NavAssistParams
from openpilot.sunnypilot.navassist.nav_state import NavStateMachine
from openpilot.sunnypilot.navassist.protocol.carrot_v2 import CATALOG, CarrotV2Receiver
from openpilot.sunnypilot.navassist.types import Maneuver, SpeedSource


NOW = 20_000_000_000
PARAMS = NavAssistParams(True, False, True, True, False, True, True, 1.2, 30 / 3.6)


def requirements():
  return {
    "type": "requirements_query",
    "protocol_version": 2,
    "app_version": "amap_auto_1.0",
    "catalog_revision": 1,
    "limits": {"max_binary_frame_bytes": 8 * 1024 * 1024, "max_total_bitrate_kbps": 12000},
    "streams": [{"kind": kind, "name": name, "schema_version": 1, "nullable": True}
                for kind, name in CATALOG],
  }


def envelope(manifest, name, sequence, value):
  stream = next(item for item in manifest["streams"] if item["kind"] == "json" and item["name"] == name)
  return {
    "type": "item_update", "protocol_version": 2, "session_id": manifest["session_id"],
    "kind": "json", "name": name, "manifest_revision": 1,
    "stream_handle": stream["stream_handle"], "schema_version": 1, "sequence": sequence,
    "source_timestamp_ms": 1_787_720_000_000, "sent_at_ms": 1_787_720_000_010,
    "present": True, "value": value,
  }


def test_navipilot_six_stream_fixture_normalizes_without_claiming_empty_route():
  receiver = CarrotV2Receiver()
  receiver.control_connected()
  manifest = receiver.negotiate(requirements())
  values = {
    "vehicle": {"lat": 31.2304, "lon": 121.4737, "heading_deg": 90.0,
                "speed_kph": 45.0, "road_name": "当前道路", "virtual_gps": False},
    "guidance_current": {"distance_m": 80, "turn_type": 12, "main_text": "左转"},
    "guidance_next": {"distance_m": 240, "turn_type": 13, "main_text": "右转"},
    "speed": {"current_kph": 45.0, "road_limit_kph": 60,
              "sdi": {"type": 8, "distance_m": 300, "speed_limit_kph": 40},
              "section": {"active": True, "speed_limit_kph": 50,
                          "remaining_distance_m": 800.0, "suspended": False, "off_route": False}},
    "route": {"remain_distance_m": 10_000, "remain_time_sec": 900, "polyline": []},
    "navigation_status": {"mode": "guiding", "guidance_active": True,
                          "off_route": False, "route_present": False},
  }
  for sequence, (name, value) in enumerate(values.items(), start=1):
    receiver.record_json(manifest["session_id"], name, envelope(manifest, name, sequence, value))

  snapshot = receiver.snapshot()
  # Pin local receive time so this fixture exercises the same freshness path as a live socket.
  records = {name: record.__class__(record.present, record.sequence, NOW, record.value, record.reason,
                                    record.source_timestamp_ms, record.sent_at_ms)
             for name, record in (snapshot.records or {}).items()}
  state = NavStateMachine().update(snapshot.__class__(
    snapshot.connected, snapshot.session_id, snapshot.generation, records,
    snapshot.protocol_error, snapshot.sequence_error, snapshot.source, snapshot.client_version,
  ), PARAMS, NOW)

  assert state.data_valid and state.guidance_valid and state.speed_valid
  assert state.maneuver == Maneuver.TURN_LEFT
  assert state.next_maneuver == Maneuver.TURN_RIGHT
  assert state.distance_to_next_maneuver_m == 320
  assert state.section_distance_m == 800
  assert state.speed_source == SpeedSource.MANEUVER
  assert state.speed_camera_distance_m == 300
  assert not state.route_valid
