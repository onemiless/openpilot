from __future__ import annotations

import json
import queue
import socket
import struct
from http.client import HTTPConnection

import pytest

from openpilot.sunnypilot.companion.http_ws import ReusableThreadingHTTPServer
from openpilot.sunnypilot.companion.params_api import ParamAccess
from openpilot.sunnypilot.companion.server import CompanionServer, make_request_handler
from openpilot.sunnypilot.companion.telemetry import multiplex_frame


class FakeParams:
  def __init__(self) -> None:
    self.values = {"ExperimentalMode": False, "ShareData": True, "SpeedFromPCM": False}

  def get_bool(self, name):
    return self.values.get(name, False)

  def put_bool(self, name, value):
    self.values[name] = value


class FakeBroker:
  def __init__(self) -> None:
    self.unregistered = []

  def start(self):
    pass

  def register(self, services):
    output = queue.Queue()
    output.put(multiplex_frame("deviceState", b"device-capnp"))
    return 7, output

  def unregister(self, client_id):
    self.unregistered.append(client_id)

  def legacy_packet(self):
    return {"version": 1, "sequence": 1, "timestamp": 123, "data": {"carState": {"vEgo": 0.0}}}


@pytest.fixture
def companion_http():
  params = FakeParams()
  broker = FakeBroker()
  access = ParamAccess(params, lambda: True)
  server = ReusableThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(broker, access))
  server.start_in_thread("test-companion")
  try:
    yield server.server_address[1], params, broker
  finally:
    server.shutdown()
    server.server_close()


def request(port, method, path, body=None):
  conn = HTTPConnection("127.0.0.1", port, timeout=2)
  headers = {"Content-Type": "application/json"} if body is not None else {}
  conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
  response = conn.getresponse()
  payload = json.loads(response.read())
  conn.close()
  return response.status, payload


def test_health_and_allowlisted_params(companion_http):
  port, params, _broker = companion_http
  assert request(port, "GET", "/health") == (200, {"ok": True, "service": "sunnypilot-companion", "version": 1})
  assert request(port, "GET", "/api/params_bulk?names=ExperimentalMode,ShareData") == (
    200, {"ok": True, "values": {"ExperimentalMode": 0, "ShareData": 1}},
  )
  assert request(port, "POST", "/api/param_set", {"name": "ExperimentalMode", "value": 1}) == (200, {"ok": True})
  assert params.values["ExperimentalMode"]
  status, payload = request(port, "POST", "/api/param_set", {"name": "DongleId", "value": "bad"})
  assert status == 403 and not payload["ok"]


def _read_exact(stream, length):
  output = b""
  while len(output) < length:
    chunk = stream.read(length - len(output))
    if not chunk:
      raise EOFError
    output += chunk
  return output


def _read_server_frame(stream):
  first, second = _read_exact(stream, 2)
  length = second & 0x7F
  if length == 126:
    length = struct.unpack("!H", _read_exact(stream, 2))[0]
  elif length == 127:
    length = struct.unpack("!Q", _read_exact(stream, 8))[0]
  return first & 0x0F, _read_exact(stream, length)


def test_raw_multiplex_websocket_hello_and_binary_frame(companion_http):
  port, _params, _broker = companion_http
  sock = socket.create_connection(("127.0.0.1", port), timeout=2)
  request_bytes = "\r\n".join((
    "GET /ws/raw_multiplex?services=carState,deviceState HTTP/1.1",
    f"Host: 127.0.0.1:{port}",
    "Upgrade: websocket",
    "Connection: Upgrade",
    "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
    "Sec-WebSocket-Version: 13",
    "",
    "",
  )).encode()
  sock.sendall(request_bytes)
  stream = sock.makefile("rb")
  assert b"101 Switching Protocols" in stream.readline()
  while stream.readline() != b"\r\n":
    pass
  opcode, hello = _read_server_frame(stream)
  assert opcode == 1
  assert json.loads(hello) == {"mode": "carrot-raw-multiplex-v1", "services": ["carState", "deviceState"]}
  opcode, frame = _read_server_frame(stream)
  assert opcode == 2
  assert frame == b"\x0bdeviceStatedevice-capnp"
  sock.close()


def test_legacy_7711_length_prefixed_json():
  broker = FakeBroker()
  params = ParamAccess(FakeParams(), lambda: True)
  server = CompanionServer(broker, params, bind_host="127.0.0.1", http_port=0, legacy_port=0)
  server.start()
  try:
    sock = socket.create_connection(("127.0.0.1", server.legacy.server_address[1]), timeout=2)
    stream = sock.makefile("rb")
    length = struct.unpack("!I", _read_exact(stream, 4))[0]
    packet = json.loads(_read_exact(stream, length))
    assert packet["version"] == 1
    assert packet["data"]["carState"]["vEgo"] == 0.0
    sock.close()
  finally:
    server.close()
