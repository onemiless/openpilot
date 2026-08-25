import json
import socket
import time

import pytest

from openpilot.sunnypilot.navassist.protocol.amap_companion_v1 import (
  AMapCompanionReceiver, AMapCompanionServer, map_amap_turn_icon, newest_snapshot,
)
from openpilot.sunnypilot.navassist.types import NavSource, ProtocolSnapshot


def payload(sequence=1, **overrides):
  value = {
    "protocol": "amap_companion_v1", "version": 1, "session_id": "session-1",
    "sequence": sequence, "sent_at_ms": 1000, "navigation_active": True, "cruise_mode": False,
    "road_name": "当前道路", "maneuver_icon": 2, "maneuver_distance_m": 80,
    "maneuver_road": "下一道路", "current_speed_kph": 45, "limit_speed_kph": 60,
    "camera_speed_kph": 40, "camera_type": 0, "camera_distance_m": 300,
  }
  value.update(overrides)
  return value


@pytest.mark.parametrize(("icon", "expected"), [(2, 12), (3, 13), (4, 7), (5, 6), (8, 14), (13, 131), (1, -1)])
def test_amap_turn_mapping(icon, expected):
  assert map_amap_turn_icon(icon) == expected


def test_receiver_normalizes_amap_snapshot():
  receiver = AMapCompanionReceiver()
  token = receiver.connect()
  receiver.record(token, payload(), now_ns=2_000_000_000)
  snapshot = receiver.snapshot()
  assert snapshot.connected and snapshot.source == NavSource.AMAP_COMPANION_V1
  assert snapshot.record("guidance_current").value["turn_type"] == 12
  assert snapshot.record("speed").value["road_limit_kph"] == 60
  assert snapshot.record("speed").value["sdi"]["speed_limit_kph"] == 40
  assert snapshot.record("speed").value["sdi"]["distance_m"] == 300
  assert not snapshot.record("route").present


def test_road_limit_is_not_reused_as_camera_limit():
  receiver = AMapCompanionReceiver()
  token = receiver.connect()
  receiver.record(token, payload(camera_speed_kph=0))
  speed = receiver.snapshot().record("speed").value
  assert speed["road_limit_kph"] == 60
  assert "sdi" not in speed


def test_sequence_and_disconnect_fail_closed():
  receiver = AMapCompanionReceiver()
  token = receiver.connect()
  receiver.record(token, payload(2))
  with pytest.raises(ValueError, match="backwards"):
    receiver.record(token, payload(1))
  assert receiver.snapshot().sequence_error
  receiver.disconnect(token)
  assert not receiver.snapshot().connected


def test_mux_selects_newest_connected_source():
  older = ProtocolSnapshot(connected=True, session_id="old", records={}, source=NavSource.CARROT_V2)
  receiver = AMapCompanionReceiver()
  token = receiver.connect()
  receiver.record(token, payload(), now_ns=5)
  assert newest_snapshot(older, receiver.snapshot()).source == NavSource.AMAP_COMPANION_V1


def test_tcp_server_accepts_newline_json():
  receiver = AMapCompanionReceiver()
  server = AMapCompanionServer(receiver, port=0, bind_host="127.0.0.1", retry_count=0)
  server.start()
  assert server._socket is not None
  port = server._socket.getsockname()[1]
  client = socket.create_connection(("127.0.0.1", port), timeout=1)
  client.sendall(json.dumps(payload()).encode() + b"\n")
  deadline = time.monotonic() + 1
  while time.monotonic() < deadline and not receiver.snapshot().connected:
    time.sleep(0.01)
  assert receiver.snapshot().record("guidance_current").present
  client.close()
