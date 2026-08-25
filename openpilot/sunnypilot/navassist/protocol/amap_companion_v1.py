"""AMap Companion NavAssist bridge protocol.

The Android app sends newline-delimited JSON snapshots over TCP after learning
the device address from NavAssist UDP discovery. This adapter normalizes those
snapshots into the same ProtocolSnapshot consumed by NavStateMachine.
"""
from __future__ import annotations

import copy
import errno
import json
import math
import socket
import threading
import time
from typing import Any

from openpilot.sunnypilot.navassist.types import NavSource, ProtocolSnapshot, StreamRecord


PROTOCOL_NAME = "amap_companion_v1"
PROTOCOL_VERSION = 1
DEFAULT_PORT = 7715
MAX_LINE_BYTES = 64 * 1024


AMAP_TURN_TYPE_MAP = {
  2: 12,             # left
  3: 13, 19: 13,     # right
  4: 7, 6: 7,        # diagonal/fork left
  5: 6, 7: 6,        # diagonal/fork right
  8: 14, 10: 14, 11: 14, 12: 14,
  13: 131, 14: 131, 17: 131, 18: 131,
}


def map_amap_turn_icon(icon: object) -> int:
  if isinstance(icon, bool) or not isinstance(icon, int):
    return -1
  return AMAP_TURN_TYPE_MAP.get(icon, -1)


def _number(value: object, field: str, minimum: float, maximum: float, default: float = 0.0) -> float:
  if value is None:
    return default
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
    raise ValueError(f"{field} must be finite")
  result = float(value)
  if not minimum <= result <= maximum:
    raise ValueError(f"{field} out of range")
  return result


def _text(value: object, field: str, maximum: int) -> str:
  if value is None:
    return ""
  if not isinstance(value, str) or len(value) > maximum:
    raise ValueError(f"{field} is invalid")
  return value


class AMapCompanionReceiver:
  def __init__(self) -> None:
    self._lock = threading.RLock()
    self._connection_token = 0
    self._connected = False
    self._session_id = ""
    self._generation = 0
    self._sequence = -1
    self._last_payload: dict[str, Any] | None = None
    self._records: dict[str, StreamRecord] = {}
    self._protocol_error = ""
    self._sequence_error = False

  def connect(self) -> int:
    with self._lock:
      self._connection_token += 1
      self._connected = True
      self._session_id = ""
      self._sequence = -1
      self._last_payload = None
      self._records.clear()
      self._protocol_error = ""
      self._sequence_error = False
      return self._connection_token

  def disconnect(self, token: int) -> None:
    with self._lock:
      if token != self._connection_token:
        return
      self._connected = False
      self._records.clear()

  def fail(self, token: int, error: str) -> None:
    with self._lock:
      if token == self._connection_token:
        self._protocol_error = str(error)[:160]
        self._records.clear()

  def record(self, token: int, payload: dict[str, Any], now_ns: int | None = None) -> None:
    if payload.get("protocol") != PROTOCOL_NAME or payload.get("version") != PROTOCOL_VERSION:
      raise ValueError("invalid AMap Companion protocol")
    session_id = _text(payload.get("session_id"), "session_id", 64)
    if not session_id:
      raise ValueError("session_id is required")
    sequence = payload.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
      raise ValueError("sequence is invalid")
    sent_at_ms = payload.get("sent_at_ms")
    if isinstance(sent_at_ms, bool) or not isinstance(sent_at_ms, int) or sent_at_ms < 0:
      raise ValueError("sent_at_ms is invalid")
    navigation_active = payload.get("navigation_active")
    cruise_mode = payload.get("cruise_mode", False)
    if not isinstance(navigation_active, bool) or not isinstance(cruise_mode, bool):
      raise ValueError("navigation state is invalid")

    maneuver_icon = payload.get("maneuver_icon", 0)
    if isinstance(maneuver_icon, bool) or not isinstance(maneuver_icon, int) or not 0 <= maneuver_icon <= 1000:
      raise ValueError("maneuver_icon is invalid")
    maneuver_distance = _number(payload.get("maneuver_distance_m"), "maneuver distance", 0.0, 2_000_000.0)
    current_speed = _number(payload.get("current_speed_kph"), "current speed", 0.0, 300.0)
    limit_speed = _number(payload.get("limit_speed_kph"), "limit speed", 0.0, 200.0)
    camera_distance = _number(payload.get("camera_distance_m"), "camera distance", 0.0, 2_000_000.0)
    camera_type = int(_number(payload.get("camera_type"), "camera type", -1.0, 100_000.0, -1.0))
    road_name = _text(payload.get("road_name"), "road_name", 96)
    maneuver_road = _text(payload.get("maneuver_road"), "maneuver_road", 96)

    with self._lock:
      if token != self._connection_token or not self._connected:
        raise ValueError("stale AMap connection")
      if session_id != self._session_id:
        self._session_id = session_id
        self._generation += 1
        self._sequence = -1
        self._last_payload = None
        self._records.clear()
        self._protocol_error = ""
        self._sequence_error = False
      if sequence == self._sequence:
        if payload == self._last_payload:
          return
        self._sequence_error = True
        raise ValueError("duplicate AMap sequence changed payload")
      if sequence < self._sequence:
        self._sequence_error = True
        raise ValueError("AMap sequence moved backwards")

      received_ns = time.monotonic_ns() if now_ns is None else now_ns
      status = {"mode": "guiding" if navigation_active else "idle",
                "guidance_active": navigation_active, "off_route": False, "route_present": False}
      records = {
        "navigation_status": StreamRecord(True, sequence, received_ns, status, "", sent_at_ms, sent_at_ms),
        "vehicle": StreamRecord(True, sequence, received_ns,
                                {"speed_kph": current_speed, "road_name": road_name}, "", sent_at_ms, sent_at_ms),
      }
      raw_turn_type = map_amap_turn_icon(maneuver_icon)
      if navigation_active and raw_turn_type >= 0 and maneuver_distance > 0:
        records["guidance_current"] = StreamRecord(
          True, sequence, received_ns,
          {"turn_type": raw_turn_type, "distance_m": maneuver_distance,
           "road_name": maneuver_road, "main_text": maneuver_road}, "", sent_at_ms, sent_at_ms,
        )
      speed_value: dict[str, Any] = {"current_kph": current_speed}
      if limit_speed > 0:
        speed_value["road_limit_kph"] = limit_speed
      if camera_distance > 0 and limit_speed > 0:
        speed_value["sdi"] = {"type": camera_type, "distance_m": camera_distance,
                              "speed_limit_kph": limit_speed}
      records["speed"] = StreamRecord(True, sequence, received_ns, speed_value, "", sent_at_ms, sent_at_ms)
      self._records = records
      self._sequence = sequence
      self._last_payload = copy.deepcopy(payload)

  def snapshot(self) -> ProtocolSnapshot:
    with self._lock:
      return ProtocolSnapshot(
        connected=self._connected and bool(self._session_id), session_id=self._session_id,
        generation=self._generation, records=copy.deepcopy(self._records),
        protocol_error=self._protocol_error, sequence_error=self._sequence_error,
        source=NavSource.AMAP_COMPANION_V1,
      )


class AMapCompanionServer:
  def __init__(self, receiver: AMapCompanionReceiver, port: int = DEFAULT_PORT, *, bind_host: str = "0.0.0.0",
               retry_count: int = 5, retry_interval_s: float = 0.5) -> None:
    self.receiver = receiver
    self.port = port
    self.bind_host = bind_host
    self.retry_count = retry_count
    self.retry_interval_s = retry_interval_s
    self._socket: socket.socket | None = None
    self._thread: threading.Thread | None = None

  def start(self) -> None:
    for retry in range(self.retry_count + 1):
      sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      try:
        sock.bind((self.bind_host, self.port))
        sock.listen(2)
        sock.settimeout(1.0)
        self._socket = sock
        break
      except OSError as exc:
        sock.close()
        if exc.errno != errno.EADDRINUSE or retry >= self.retry_count:
          raise
        time.sleep(self.retry_interval_s)
    self._thread = threading.Thread(target=self._accept_loop, name="amap-companion-server", daemon=True)
    self._thread.start()

  def _accept_loop(self) -> None:
    assert self._socket is not None
    while True:
      try:
        client, _ = self._socket.accept()
      except TimeoutError:
        continue
      except OSError:
        return
      threading.Thread(target=self._client_loop, args=(client,), name="amap-companion-client", daemon=True).start()

  def _client_loop(self, client: socket.socket) -> None:
    token = self.receiver.connect()
    client.settimeout(2.0)
    try:
      with client, client.makefile("rb") as stream:
        while True:
          line = stream.readline(MAX_LINE_BYTES + 1)
          if not line:
            break
          if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
            raise ValueError("AMap message exceeds line limit")
          payload = json.loads(line)
          if not isinstance(payload, dict):
            raise ValueError("AMap message must be an object")
          self.receiver.record(token, payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
      self.receiver.fail(token, str(exc))
    finally:
      self.receiver.disconnect(token)


def newest_snapshot(*snapshots: ProtocolSnapshot) -> ProtocolSnapshot:
  connected = [snapshot for snapshot in snapshots if snapshot.connected]
  if not connected:
    return ProtocolSnapshot()
  return max(connected, key=lambda snapshot: max(
    (record.received_mono_ns for record in (snapshot.records or {}).values()), default=0,
  ))
