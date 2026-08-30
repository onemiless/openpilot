import hashlib
import hmac
import http.client
import json
import threading

from openpilot.sunnypilot.navassist.protocol import NavAssistStore
from openpilot.sunnypilot.navassist.server import ClientRateLimiter, NavAssistHTTPServer, SIGNATURE_HEADER, SNAPSHOT_PATH
from openpilot.sunnypilot.navassist.tests.test_protocol import SOURCE_WALL_MS, TOKEN, encode, payload


def store():
  return NavAssistStore(TOKEN, wall_clock_ms=lambda: SOURCE_WALL_MS)


def post(port: int, body: bytes, signature: str | None):
  connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
  headers = {"Content-Type": "application/json"}
  if signature is not None:
    headers[SIGNATURE_HEADER] = signature
  connection.request("POST", SNAPSHOT_PATH, body=body, headers=headers)
  response = connection.getresponse()
  result = response.status, json.loads(response.read())
  connection.close()
  return result


def run_server(store: NavAssistStore, *, rate_limiter=None):
  server = NavAssistHTTPServer(("127.0.0.1", 0), store, rate_limiter=rate_limiter)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  return server, thread


def test_http_accepts_authenticated_snapshot_and_rejects_replay():
  server, thread = run_server(store())
  try:
    body = encode(payload())
    signature = hmac.new(TOKEN, body, hashlib.sha256).hexdigest()
    status, result = post(server.server_port, body, signature)
    assert status == 202
    assert result == {"accepted": True, "sessionId": "session-a", "sequence": 1, "routeRevision": 1}

    status, result = post(server.server_port, body, signature)
    assert status == 409
    assert result == {"accepted": False, "reason": "replay"}
  finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_http_rejects_missing_signature_and_rate_limits_before_parsing():
  server, thread = run_server(store(), rate_limiter=ClientRateLimiter(max_requests=1))
  try:
    body = encode(payload())
    assert post(server.server_port, body, None) == (401, {"accepted": False, "reason": "authentication"})
    assert post(server.server_port, body, None) == (429, {"accepted": False, "reason": "rate_limited"})
  finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_http_server_has_a_hard_concurrency_cap():
  server = NavAssistHTTPServer(("127.0.0.1", 0), store(), max_concurrent_requests=2)
  try:
    assert server._request_slots.acquire(blocking=False)
    assert server._request_slots.acquire(blocking=False)
    assert not server._request_slots.acquire(blocking=False)
    server._request_slots.release()
    server._request_slots.release()
  finally:
    server.server_close()
