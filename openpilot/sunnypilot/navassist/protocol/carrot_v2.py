"""Minimal Carrot Navi WebSocket v2 receiver.

Protocol contract verified against jixiexiaoge/openpilot Carrot commit
3fb1121ecb7837e47f5edf12c5882e38c57c05bd. The receiver deliberately enables
only structured navigation streams; media, render, cluster and terminal paths
are not part of NavAssist.
"""
from __future__ import annotations

import copy
import json
import secrets
import socket
import threading
import time
from typing import Any

from openpilot.sunnypilot.navassist.types import ProtocolSnapshot, StreamRecord


PROTOCOL_VERSION = 2
CATALOG_REVISION = 1
DEFAULT_PORT = 7714
DISCOVERY_PORT = 7705
MAX_MESSAGE_BYTES = 1024 * 1024

JSON_NAMES = (
  "vehicle", "guidance_current", "guidance_next", "lane_current", "lane_ahead", "speed",
  "traffic_signal", "crossroad", "route", "navigation_status", "app_status", "camera_state",
  "composition_state",
)
IMAGE_NAMES = (
  "tbt_current_compact", "tbt_current_full", "tbt_next", "traffic_signal", "lane_top", "lane_bottom",
  "safety_primary", "safety_secondary", "safety_section", "crossroad_minimized", "crossroad_expanded",
  "center_tbt_icon", "center_tbt_text", "center_tbt_fee",
)
RENDER_NAMES = ("map_main",)
CATALOG = tuple([("json", name) for name in JSON_NAMES] +
                [("image", name) for name in IMAGE_NAMES] +
                [("render", name) for name in RENDER_NAMES])
CATALOG_SET = frozenset(CATALOG)
ENABLED_JSON = frozenset(("vehicle", "guidance_current", "guidance_next", "speed", "route", "navigation_status"))


def _stream_params(kind: str) -> dict[str, Any]:
  if kind == "json":
    return {"delivery_mode": "on_change_with_heartbeat", "interval_ms": 200, "stale_timeout_ms": 1200}
  if kind == "image":
    return {"format": "png", "max_fps": 5, "stale_timeout_ms": 15000}
  return {
    "composition": "map_route_vehicle", "width": 960, "height": 540, "dpi": 360, "fps": 10,
    "jpeg_quality": 75, "codec": "h264", "h264_bitrate_kbps": 3000,
    "h264_keyframe_interval_sec": 2, "camera_mode": "app_sync", "map_theme": "auto",
    "map_type": "normal", "zoom": 11.0, "tilt": 50.0, "bearing": 0.0,
    "follow_vehicle_bearing": True, "fov": 40.0, "screen_center_y_ratio": 0.8,
    "follow_vehicle": True, "center_latitude": None, "center_longitude": None, "stale_timeout_ms": 5000,
  }


def build_manifest(session_id: str) -> dict[str, Any]:
  streams = []
  for handle, (kind, name) in enumerate(CATALOG, start=1):
    streams.append({
      "kind": kind, "name": name, "schema_version": 1, "stream_handle": handle,
      "enabled": kind == "json" and name in ENABLED_JSON,
      "params": _stream_params(kind),
    })
  return {
    "type": "subscription_manifest", "protocol_version": PROTOCOL_VERSION,
    "session_id": session_id, "revision": 1, "metrics_enabled": False,
    "limit_adjustments": [], "streams": streams,
  }


class CarrotV2Receiver:
  def __init__(self) -> None:
    self._lock = threading.RLock()
    self._session_id = ""
    self._generation = 0
    self._manifest: dict[str, Any] | None = None
    self._streams: dict[str, dict[str, Any]] = {}
    self._records: dict[str, StreamRecord] = {}
    self._control_connections = 0
    self._protocol_error = ""
    self._sequence_error = False

  def negotiate(self, requirements: dict[str, Any]) -> dict[str, Any]:
    if requirements.get("type") != "requirements_query" or requirements.get("protocol_version") != PROTOCOL_VERSION:
      raise ValueError("invalid v2 requirements query")
    if isinstance(requirements.get("catalog_revision"), bool) or requirements.get("catalog_revision") != CATALOG_REVISION:
      raise ValueError("unsupported v2 catalog revision")
    offered_streams = requirements.get("streams")
    if not isinstance(offered_streams, list) or len(offered_streams) != len(CATALOG):
      raise ValueError("app v2 catalog does not contain exactly 28 items")
    offered = []
    for stream in offered_streams:
      if not isinstance(stream, dict) or stream.get("schema_version") != 1:
        raise ValueError("invalid v2 catalog entry")
      offered.append((str(stream.get("kind")), str(stream.get("name"))))
    if len(set(offered)) != len(offered) or set(offered) != CATALOG_SET:
      raise ValueError("app v2 catalog does not match receiver catalog")

    with self._lock:
      self._session_id = secrets.token_hex(8)
      self._generation += 1
      self._manifest = build_manifest(self._session_id)
      self._streams = {f"{s['kind']}:{s['name']}": s for s in self._manifest["streams"]}
      self._records.clear()
      self._protocol_error = ""
      self._sequence_error = False
      return copy.deepcopy(self._manifest)

  def control_connected(self) -> None:
    with self._lock:
      self._control_connections += 1

  def control_disconnected(self) -> None:
    with self._lock:
      self._control_connections = max(0, self._control_connections - 1)
      if self._control_connections == 0:
        self._records.clear()

  def fail(self, error: str) -> None:
    with self._lock:
      self._protocol_error = str(error)[:160]

  def stream_config(self, session_id: str, name: str) -> dict[str, Any]:
    with self._lock:
      if session_id != self._session_id or self._manifest is None:
        raise ValueError("stale v2 session")
      stream = self._streams.get(f"json:{name}")
      if stream is None or not stream["enabled"]:
        raise ValueError("stream is not enabled")
      return copy.deepcopy(stream)

  def record_json(self, session_id: str, name: str, envelope: dict[str, Any]) -> None:
    if (envelope.get("type") != "item_update" or envelope.get("protocol_version") != PROTOCOL_VERSION
        or envelope.get("session_id") != session_id or envelope.get("kind") != "json"
        or envelope.get("name") != name):
      raise ValueError("v2 JSON envelope/path mismatch")
    with self._lock:
      stream = self.stream_config(session_id, name)
      if envelope.get("manifest_revision") != 1 or envelope.get("schema_version") != 1:
        raise ValueError("stale v2 manifest revision")
      if envelope.get("stream_handle") != stream["stream_handle"]:
        raise ValueError("v2 stream handle mismatch")
      sequence = envelope.get("sequence")
      if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("invalid v2 sequence")
      previous = self._records.get(name)
      if previous is not None and sequence == previous.sequence:
        return
      if previous is not None and sequence < previous.sequence:
        self._sequence_error = True
        raise ValueError("v2 sequence moved backwards")
      present = envelope.get("present")
      value = envelope.get("value")
      if not isinstance(present, bool):
        raise ValueError("v2 present must be boolean")
      if present and not isinstance(value, dict):
        raise ValueError("present JSON value must be an object")
      if not present and value is not None:
        raise ValueError("absent JSON value must be null")
      reason = envelope.get("reason", "")
      if not present and (not isinstance(reason, str) or not reason or len(reason) > 64):
        raise ValueError("absent JSON item requires reason")
      if name == "route" and present:
        polyline = value.get("polyline", [])
        if not isinstance(polyline, list) or len(polyline) > 256:
          raise ValueError("route exceeds 256 points")
      self._records[name] = StreamRecord(present, sequence, time.monotonic_ns(), copy.deepcopy(value), str(reason))
      self._protocol_error = ""

  def snapshot(self) -> ProtocolSnapshot:
    with self._lock:
      return ProtocolSnapshot(
        connected=self._control_connections > 0 and bool(self._session_id),
        session_id=self._session_id,
        generation=self._generation,
        records=copy.deepcopy(self._records),
        protocol_error=self._protocol_error,
        sequence_error=self._sequence_error,
      )


def _peer(request) -> str:
  return request.remote or "-"


def create_app(receiver: CarrotV2Receiver):
  from aiohttp import WSMsgType, web

  async def control(request):
    ws = web.WebSocketResponse(heartbeat=5.0, max_msg_size=MAX_MESSAGE_BYTES, compress=False)
    await ws.prepare(request)
    receiver.control_connected()
    try:
      async for message in ws:
        if message.type != WSMsgType.TEXT:
          raise ValueError("control accepts JSON text only")
        payload = json.loads(message.data)
        if not isinstance(payload, dict):
          raise ValueError("control message must be object")
        if payload.get("type") == "requirements_query":
          await ws.send_json(receiver.negotiate(payload))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
      receiver.fail(str(exc))
      await ws.close(code=1008, message=b"invalid control message")
    finally:
      receiver.control_disconnected()
    return ws

  async def json_stream(request):
    session_id = request.match_info["session_id"]
    name = request.match_info["name"]
    ws = web.WebSocketResponse(heartbeat=10.0, max_msg_size=MAX_MESSAGE_BYTES, compress=False)
    await ws.prepare(request)
    try:
      receiver.stream_config(session_id, name)
      async for message in ws:
        if message.type != WSMsgType.TEXT:
          raise ValueError("JSON item stream accepts text only")
        payload = json.loads(message.data)
        if not isinstance(payload, dict):
          raise ValueError("JSON item must be object")
        receiver.record_json(session_id, name, payload)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
      receiver.fail(str(exc))
      await ws.close(code=1008, message=b"invalid JSON stream")
    return ws

  async def health(_request):
    snapshot = receiver.snapshot()
    return web.json_response({"connected": snapshot.connected, "session_id": snapshot.session_id,
                              "generation": snapshot.generation, "error": snapshot.protocol_error})

  app = web.Application(client_max_size=MAX_MESSAGE_BYTES)
  app.router.add_get("/health", health)
  app.router.add_get("/api/navi/ws/v2/control/{version}", control)
  app.router.add_get("/api/navi/ws/v2/json/{session_id}/{name}", json_stream)
  return app


def detect_advertise_ip() -> str:
  probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    probe.connect(("8.8.8.8", 80))
    return str(probe.getsockname()[0])
  except OSError:
    return "127.0.0.1"
  finally:
    probe.close()


class DiscoveryBroadcaster:
  def __init__(self) -> None:
    self._stop = threading.Event()
    self._thread: threading.Thread | None = None

  def start(self) -> None:
    self._thread = threading.Thread(target=self._run, name="navassist-discovery", daemon=True)
    self._thread.start()

  def stop(self) -> None:
    self._stop.set()

  def _run(self) -> None:
    payload = json.dumps({"ip": detect_advertise_ip(), "navi_debug": 0}).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
      while not self._stop.wait(1.0):
        try:
          sock.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))
        except OSError:
          pass
    finally:
      sock.close()


class CarrotV2Server:
  def __init__(self, receiver: CarrotV2Receiver, port: int = DEFAULT_PORT) -> None:
    self.receiver = receiver
    self.port = port
    self.discovery = DiscoveryBroadcaster()
    self._thread: threading.Thread | None = None

  def start(self) -> None:
    from aiohttp import web

    def run() -> None:
      web.run_app(create_app(self.receiver), host="0.0.0.0", port=self.port, access_log=None, handle_signals=False)

    self.discovery.start()
    self._thread = threading.Thread(target=run, name="navassist-websocket", daemon=True)
    self._thread.start()
