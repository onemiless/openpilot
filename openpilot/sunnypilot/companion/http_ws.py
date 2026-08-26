from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MAX_HTTP_BODY_BYTES = 64 * 1024
MAX_WS_FRAME_BYTES = 8 * 1024 * 1024
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketClosed(Exception):
  pass


def json_bytes(value: object) -> bytes:
  return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def trusted_local_address(address: str) -> bool:
  try:
    ip = ipaddress.ip_address(address)
  except ValueError:
    return False
  return ip.is_private or ip.is_loopback or ip.is_link_local


def send_json(handler: BaseHTTPRequestHandler, status: int, value: object) -> None:
  payload = json_bytes(value)
  handler.send_response(status)
  handler.send_header("Content-Type", "application/json; charset=utf-8")
  handler.send_header("Content-Length", str(len(payload)))
  handler.send_header("Cache-Control", "no-store")
  handler.end_headers()
  handler.wfile.write(payload)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
  raw_length = handler.headers.get("Content-Length", "")
  try:
    length = int(raw_length)
  except ValueError as exc:
    raise ValueError("invalid content length") from exc
  if length < 0 or length > MAX_HTTP_BODY_BYTES:
    raise ValueError("request body is too large")
  try:
    value = json.loads(handler.rfile.read(length))
  except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise ValueError("invalid JSON body") from exc
  if not isinstance(value, dict):
    raise ValueError("JSON body must be an object")
  return value


def accept_websocket(handler: BaseHTTPRequestHandler) -> None:
  if handler.headers.get("Upgrade", "").lower() != "websocket":
    raise ValueError("websocket upgrade required")
  if "upgrade" not in handler.headers.get("Connection", "").lower():
    raise ValueError("websocket connection upgrade required")
  key = handler.headers.get("Sec-WebSocket-Key", "")
  if not key:
    raise ValueError("missing websocket key")
  accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
  handler.send_response(101, "Switching Protocols")
  handler.send_header("Upgrade", "websocket")
  handler.send_header("Connection", "Upgrade")
  handler.send_header("Sec-WebSocket-Accept", accept)
  handler.end_headers()


def read_websocket_frame(handler: BaseHTTPRequestHandler) -> tuple[int, bytes]:
  header = handler.rfile.read(2)
  if len(header) != 2:
    raise WebSocketClosed
  first, second = header
  if not first & 0x80:
    raise ValueError("fragmented websocket frames are unsupported")
  opcode = first & 0x0F
  masked = bool(second & 0x80)
  length = second & 0x7F
  if length == 126:
    raw = handler.rfile.read(2)
    if len(raw) != 2:
      raise WebSocketClosed
    length = struct.unpack("!H", raw)[0]
  elif length == 127:
    raw = handler.rfile.read(8)
    if len(raw) != 8:
      raise WebSocketClosed
    length = struct.unpack("!Q", raw)[0]
  if length > MAX_WS_FRAME_BYTES:
    raise ValueError("websocket frame is too large")
  if not masked:
    raise ValueError("client websocket frame must be masked")
  mask = handler.rfile.read(4)
  payload = handler.rfile.read(length)
  if len(mask) != 4 or len(payload) != length:
    raise WebSocketClosed
  return opcode, bytes(value ^ mask[index % 4] for index, value in enumerate(payload))


def websocket_frame(opcode: int, payload: bytes = b"") -> bytes:
  length = len(payload)
  if length < 126:
    header = bytes((0x80 | opcode, length))
  elif length <= 0xFFFF:
    header = bytes((0x80 | opcode, 126)) + struct.pack("!H", length)
  else:
    header = bytes((0x80 | opcode, 127)) + struct.pack("!Q", length)
  return header + payload


def send_websocket_frame(handler: BaseHTTPRequestHandler, opcode: int, payload: bytes = b"",
                         lock: threading.Lock | None = None) -> None:
  frame = websocket_frame(opcode, payload)
  if lock is None:
    handler.wfile.write(frame)
    handler.wfile.flush()
  else:
    with lock:
      handler.wfile.write(frame)
      handler.wfile.flush()


def websocket_receive_loop(handler: BaseHTTPRequestHandler, lock: threading.Lock | None = None):
  while True:
    opcode, payload = read_websocket_frame(handler)
    if opcode == 0x8:
      try:
        send_websocket_frame(handler, 0x8, payload[:125], lock)
      except OSError:
        pass
      return
    if opcode == 0x9:
      send_websocket_frame(handler, 0xA, payload[:125], lock)
      continue
    if opcode == 0xA:
      continue
    yield opcode, payload


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
  allow_reuse_address = True
  daemon_threads = True

  def start_in_thread(self, name: str) -> threading.Thread:
    thread = threading.Thread(target=self.serve_forever, name=name, daemon=True)
    thread.start()
    return thread
