import pytest

from openpilot.sunnypilot.navassist.protocol.carrot_udp import CarrotUdpReceiver
from openpilot.sunnypilot.navassist.types import NavSource


NOW = 10_000_000_000


def packet(sequence=1264):
  return {
    "carrotIndex": sequence,
    "epochTime": 1_787_742_578,
    "nRoadLimitSpeed": 60,
    "nTBTDist": 162,
    "nTBTTurnType": 12,
    "szTBTMainText": "左转进入道路，162米",
    "nTBTDistNext": 400,
    "nTBTTurnTypeNext": 13,
    "szTBTMainTextNext": "随后右转",
    "nGoPosDist": 6964,
    "nGoPosTime": 700,
    "szPosRoadName": "当前道路",
    "nPosSpeed": 20,
    "nSdiType": 8,
    "nSdiDist": 108,
    "nSdiSpeedLimit": 40,
    "vpPosPointLat": 31.2,
    "vpPosPointLon": 121.4,
    "nPosAngle": 90,
  }


def test_full_7706_packet_normalizes_into_carrot_snapshot():
  receiver = CarrotUdpReceiver()
  receiver.record(packet(), "192.168.10.144", NOW)
  snapshot = receiver.snapshot(NOW)
  assert snapshot.connected and snapshot.source == NavSource.CARROT_V2
  assert snapshot.client_version == "cp-companion-udp-7706"
  assert snapshot.record("navigation_status").value["guidance_active"]
  assert snapshot.record("guidance_current").value["turn_type"] == 12
  assert snapshot.record("guidance_current").value["distance_m"] == 162
  assert snapshot.record("guidance_next").value["turn_type"] == 13
  assert snapshot.record("speed").value["road_limit_kph"] == 60
  assert snapshot.record("speed").value["sdi"]["distance_m"] == 108


def test_compact_command_heartbeat_does_not_replace_navigation():
  receiver = CarrotUdpReceiver()
  receiver.record(packet(), "192.168.10.144", NOW)
  receiver.record({"carrotIndex": 1265, "epochTime": 1_787_742_579, "carrotCmd": "", "carrotArg": ""},
                  "192.168.10.144", NOW + 1_000_000_000)
  assert receiver.snapshot(NOW + 1_000_000_000).record("guidance_current").sequence == 1264


def test_udp_connection_expires_without_full_navigation_packets():
  receiver = CarrotUdpReceiver()
  receiver.record(packet(), "192.168.10.144", NOW)
  assert receiver.snapshot(NOW + 3_000_000_000).connected
  assert not receiver.snapshot(NOW + 3_000_000_001).connected


def test_sequence_reset_starts_new_generation():
  receiver = CarrotUdpReceiver()
  receiver.record(packet(100), "192.168.10.144", NOW)
  generation = receiver.snapshot(NOW).generation
  receiver.record(packet(1), "192.168.10.144", NOW + 1)
  assert receiver.snapshot(NOW + 1).generation == generation + 1


def test_rejects_out_of_range_navigation_values():
  value = packet()
  value["nTBTDist"] = -1
  with pytest.raises(ValueError):
    CarrotUdpReceiver().record(value, "192.168.10.144", NOW)
