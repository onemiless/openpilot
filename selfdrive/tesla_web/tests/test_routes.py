import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from openpilot.selfdrive.tesla_web.routes import make_handler


class FakeParams:
  def __init__(self):
    self.values = {"EnableTeslaTools": "1"}

  def get(self, key, encoding=None):
    value = self.values.get(key)
    return value if encoding and value is not None else (value.encode() if value is not None else None)

  def get_bool(self, key):
    return self.values.get(key) == "1"

  def put_nonblocking(self, key, value):
    self.values[key] = value

  def put(self, key, value):
    self.values[key] = value


@pytest.fixture
def web_server():
  params = FakeParams()
  templates = Path(__file__).parents[1] / "templates"
  server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(params, templates))
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  try:
    yield server, params
  finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(server, method, path, payload=None):
  conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
  body = json.dumps(payload) if payload is not None else None
  headers = {"Content-Type": "application/json"} if body is not None else {}
  conn.request(method, path, body=body, headers=headers)
  response = conn.getresponse()
  data = response.read()
  conn.close()
  return response.status, response.getheader("Access-Control-Allow-Origin"), data


def test_turn_start_and_cancel_write_narrow_requests(web_server):
  server, params = web_server
  status, cors, data = request(server, "POST", "/api/v1/turn/start", {"direction": "left"})
  response = json.loads(data)
  assert status == 202 and cors is None
  start = json.loads(params.values["TeslaTurnSignalRequest"])
  assert start["id"] == response["id"] and start["direction"] == "left" and start["created_ms"] > 0

  status, _, _ = request(server, "POST", "/api/v1/turn/cancel", {"id": response["id"]})
  assert status == 202
  cancel = json.loads(params.values["TeslaTurnSignalCancel"])
  assert cancel["id"] == response["id"]


def test_invalid_turn_request_is_rejected(web_server):
  server, params = web_server
  status, _, data = request(server, "POST", "/api/v1/turn/start", {"direction": "hazard"})
  assert status == 400
  assert "TeslaTurnSignalRequest" not in params.values
  assert json.loads(data)["error"] == "direction must be left or right"


def test_pending_turn_start_is_not_overwritten(web_server):
  server, params = web_server
  status, _, data = request(server, "POST", "/api/v1/turn/start", {"direction": "left"})
  assert status == 202
  first = json.loads(params.values["TeslaTurnSignalRequest"])
  assert first["id"] == json.loads(data)["id"]

  status, _, data = request(server, "POST", "/api/v1/turn/start", {"direction": "right"})
  assert status == 409
  assert json.loads(data)["error"] == "request_pending"
  assert json.loads(params.values["TeslaTurnSignalRequest"]) == first


def test_pending_turn_cancel_is_not_overwritten(web_server):
  server, params = web_server
  status, _, data = request(server, "POST", "/api/v1/turn/start", {"direction": "left"})
  assert status == 202
  test_id = json.loads(data)["id"]

  status, _, _ = request(server, "POST", "/api/v1/turn/cancel", {"id": test_id})
  assert status == 202
  first = json.loads(params.values["TeslaTurnSignalCancel"])

  status, _, data = request(server, "POST", "/api/v1/turn/cancel", {"id": "different"})
  assert status == 409
  assert json.loads(data)["error"] == "request_pending"
  assert json.loads(params.values["TeslaTurnSignalCancel"]) == first


def test_status_and_health_are_read_only(web_server):
  server, params = web_server
  params.values["TeslaTurnSignalStatus"] = json.dumps({"test_id": "abc", "phase": "lane_changing"})
  params.values["TeslaSpeedSyncStatus"] = json.dumps({"state": "synced", "target": 80})
  status, _, turn_data = request(server, "GET", "/api/v1/turn/status")
  assert status == 200 and json.loads(turn_data)["status"]["test_id"] == "abc"
  status, _, speed_data = request(server, "GET", "/api/v1/speed/status")
  assert status == 200 and json.loads(speed_data)["target"] == 80
  status, _, health_data = request(server, "GET", "/api/v1/health")
  assert status == 200 and json.loads(health_data) == {"auth": False, "enabled": True, "service": "tesla-tools"}


def test_index_warns_that_authentication_is_disabled(web_server):
  server, _ = web_server
  status, _, data = request(server, "GET", "/")
  assert status == 200
  assert "当前没有认证" in data.decode("utf-8")
