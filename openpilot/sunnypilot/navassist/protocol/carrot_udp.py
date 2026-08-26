"""Compatibility receiver for CP companion's continuously published UDP 7706 snapshots."""
from __future__ import annotations

import copy
import json
import math
import socket
import threading
import time
from typing import Any

from openpilot.sunnypilot.companion.http_ws import trusted_local_address
from openpilot.sunnypilot.navassist.types import NavSource, ProtocolSnapshot, StreamRecord


DEFAULT_PORT = 7706
MAX_PACKET_BYTES = 64 * 1024
CONNECTION_TIMEOUT_NS = 3_000_000_000


def _number(payload: dict[str, Any], name: str, minimum: float, maximum: float, default: float = 0.0) -> float:
  value = payload.get(name, default)
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
    raise ValueError(f"{name} must be finite")
  result = float(value)
  if not minimum <= result <= maximum:
    raise ValueError(f"{name} out of range")
  return result


def _integer(payload: dict[str, Any], name: str, minimum: int, maximum: int, default: int = 0) -> int:
  value = payload.get(name, default)
  if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
    raise ValueError(f"{name} is invalid")
  return value


def _text(payload: dict[str, Any], name: str, maximum: int) -> str:
  value = payload.get(name, "")
  if not isinstance(value, str) or len(value) > maximum:
    raise ValueError(f"{name} is invalid")
  return value


class CarrotUdpReceiver:
  def __init__(self) -> None:
    self._lock = threading.RLock()
    self._session_id = ""
    self._generation = 0
    self._sequence = -1
    self._last_received_ns = 0
    self._records: dict[str, StreamRecord] = {}
    self._protocol_error = ""

  def record(self, payload: dict[str, Any], source_ip: str, now_ns: int | None = None) -> None:
    # Compact command heartbeats share the port; only full navigation snapshots carry this key.
    if "nTBTDist" not in payload:
      return
    sequence = _integer(payload, "carrotIndex", 0, 2**63 - 1)
    epoch_s = _integer(payload, "epochTime", 0, 2**63 - 1)
    maneuver_distance = _number(payload, "nTBTDist", 0.0, 2_000_000.0)
    maneuver_type = _integer(payload, "nTBTTurnType", -1, 100_000, -1)
    next_distance = _number(payload, "nTBTDistNext", 0.0, 2_000_000.0)
    next_type = _integer(payload, "nTBTTurnTypeNext", -1, 100_000, -1)
    remaining_distance = _number(payload, "nGoPosDist", 0.0, 2_000_000.0)
    remaining_time = _number(payload, "nGoPosTime", 0.0, 604_800.0)
    current_speed = _number(payload, "nPosSpeed", 0.0, 300.0)
    road_limit = _number(payload, "nRoadLimitSpeed", 0.0, 200.0)
    camera_distance = _number(payload, "nSdiDist", 0.0, 2_000_000.0)
    camera_speed = _number(payload, "nSdiSpeedLimit", 0.0, 300.0)
    camera_type = _integer(payload, "nSdiType", -1, 100_000, -1)
    road_name = _text(payload, "szPosRoadName", 96)
    maneuver_text = _text(payload, "szTBTMainText", 160)
    next_text = _text(payload, "szTBTMainTextNext", 160)
    latitude = _number(payload, "vpPosPointLat", -90.0, 90.0)
    longitude = _number(payload, "vpPosPointLon", -180.0, 180.0)
    heading = _number(payload, "nPosAngle", 0.0, 360.0)
    received_ns = time.monotonic_ns() if now_ns is None else now_ns
    sent_at_ms = epoch_s * 1000
    navigation_active = remaining_distance > 0 or maneuver_distance > 0

    records: dict[str, StreamRecord] = {
      "navigation_status": StreamRecord(
        True, sequence, received_ns,
        {"mode": "guiding" if navigation_active else "idle", "guidance_active": navigation_active,
         "off_route": False, "route_present": False}, "", sent_at_ms, sent_at_ms,
      ),
      "vehicle": StreamRecord(
        True, sequence, received_ns,
        {"lat": latitude, "lon": longitude, "heading_deg": heading,
         "speed_kph": current_speed, "road_name": road_name}, "", sent_at_ms, sent_at_ms,
      ),
      "speed": StreamRecord(True, sequence, received_ns, {"current_kph": current_speed}, "", sent_at_ms, sent_at_ms),
      "route": StreamRecord(
        True, sequence, received_ns,
        {"remain_distance_m": remaining_distance, "remain_time_sec": remaining_time, "polyline": []},
        "", sent_at_ms, sent_at_ms,
      ),
    }
    if road_limit > 0:
      records["speed"].value["road_limit_kph"] = road_limit
    if camera_distance > 0 and camera_speed > 0:
      records["speed"].value["sdi"] = {
        "type": camera_type, "distance_m": camera_distance, "speed_limit_kph": camera_speed,
      }
    if navigation_active and maneuver_distance > 0 and maneuver_type >= 0:
      records["guidance_current"] = StreamRecord(
        True, sequence, received_ns,
        {"turn_type": maneuver_type, "distance_m": maneuver_distance,
         "road_name": road_name, "main_text": maneuver_text}, "", sent_at_ms, sent_at_ms,
      )
    if navigation_active and next_distance > 0 and next_type >= 0:
      records["guidance_next"] = StreamRecord(
        True, sequence, received_ns,
        {"turn_type": next_type, "distance_m": next_distance, "main_text": next_text}, "", sent_at_ms, sent_at_ms,
      )

    with self._lock:
      session_id = f"udp-{source_ip}"
      if session_id != self._session_id or sequence < self._sequence:
        self._session_id = session_id
        self._generation += 1
      self._sequence = sequence
      self._last_received_ns = received_ns
      self._records = records
      self._protocol_error = ""

  def fail(self, error: str) -> None:
    with self._lock:
      self._protocol_error = str(error)[:160]

  def snapshot(self, now_ns: int | None = None) -> ProtocolSnapshot:
    current_ns = time.monotonic_ns() if now_ns is None else now_ns
    with self._lock:
      connected = bool(self._session_id and 0 <= current_ns - self._last_received_ns <= CONNECTION_TIMEOUT_NS)
      return ProtocolSnapshot(
        connected=connected, session_id=self._session_id, generation=self._generation,
        records=copy.deepcopy(self._records), protocol_error=self._protocol_error,
        source=NavSource.CARROT_V2, client_version="cp-companion-udp-7706",
      )


class CarrotUdpServer:
  def __init__(self, receiver: CarrotUdpReceiver, port: int = DEFAULT_PORT, *, bind_host: str = "0.0.0.0") -> None:
    self.receiver = receiver
    self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self._socket.bind((bind_host, port))
    self._thread: threading.Thread | None = None

  def start(self) -> None:
    self._thread = threading.Thread(target=self._run, name="carrot-udp-7706", daemon=True)
    self._thread.start()

  def _run(self) -> None:
    while True:
      try:
        raw, address = self._socket.recvfrom(MAX_PACKET_BYTES + 1)
        if len(raw) > MAX_PACKET_BYTES or not trusted_local_address(address[0]):
          continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
          raise ValueError("UDP navigation packet must be an object")
        self.receiver.record(payload, address[0])
      except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        self.receiver.fail(str(exc))
