import json
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from openpilot.selfdrive.tesla_web.auth import request_authorized


MAX_BODY_BYTES = 4096
ACTION_RATE_WINDOW_S = 1.0
ACTION_RATE_LIMIT = 5


class ActionRateLimiter:
  def __init__(self):
    self.requests = defaultdict(deque)

  def allow(self, client: str, now: float) -> bool:
    queue = self.requests[client]
    while queue and now - queue[0] > ACTION_RATE_WINDOW_S:
      queue.popleft()
    if len(queue) >= ACTION_RATE_LIMIT:
      return False
    queue.append(now)
    return True


def make_handler(params, template_root: Path | None = None):
  templates = template_root or Path(__file__).with_name("templates")
  limiter = ActionRateLimiter()

  class TeslaToolsHandler(BaseHTTPRequestHandler):
    server_version = "TeslaTools/1"

    def log_message(self, _format, *_args):
      return

    def _headers(self, status: int, content_type: str, length: int) -> None:
      self.send_response(status)
      self.send_header("Content-Type", content_type)
      self.send_header("Content-Length", str(length))
      self.send_header("Cache-Control", "no-store")
      self.send_header("X-Content-Type-Options", "nosniff")
      self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
      self.end_headers()

    def _json(self, status: int, payload: dict) -> None:
      data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
      self._headers(status, "application/json; charset=utf-8", len(data))
      self.wfile.write(data)

    def _read_json(self) -> dict:
      try:
        length = int(self.headers.get("Content-Length", "0"))
      except ValueError as error:
        raise ValueError("invalid Content-Length") from error
      if length <= 0 or length > MAX_BODY_BYTES:
        raise ValueError("invalid request body length")
      try:
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
      except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid JSON") from error
      if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
      return payload

    @staticmethod
    def _param_json(key: str, fallback: dict) -> dict:
      raw = params.get(key, encoding="utf8")
      if not raw:
        return fallback
      try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else fallback
      except json.JSONDecodeError:
        return fallback

    def _action_allowed(self) -> bool:
      client = self.client_address[0] if self.client_address else "unknown"
      return limiter.allow(client, time.monotonic())

    def do_GET(self):
      path = urlparse(self.path).path
      if path == "/":
        data = (templates / "index.html").read_bytes()
        self._headers(200, "text/html; charset=utf-8", len(data))
        self.wfile.write(data)
      elif path == "/api/v1/turn/status":
        self._json(200, {
          "status": self._param_json("TeslaTurnSignalStatus", {"state": "idle"}),
          "result": self._param_json("TeslaTurnSignalResult", {}),
        })
      elif path == "/api/v1/speed/status":
        self._json(200, self._param_json("TeslaSpeedSyncStatus", {"state": "unavailable"}))
      elif path == "/api/v1/health":
        self._json(200, {"service": "tesla-tools", "auth": False, "enabled": params.get_bool("EnableTeslaTools")})
      else:
        self._json(404, {"error": "not_found"})

    def do_POST(self):
      if not request_authorized(self):
        self._json(401, {"error": "unauthorized"})
        return
      if not self._action_allowed():
        self._json(429, {"error": "rate_limited"})
        return
      path = urlparse(self.path).path
      try:
        payload = self._read_json()
        created_ms = int(time.time() * 1000)
        if path == "/api/v1/turn/start":
          direction = str(payload.get("direction", ""))
          if direction not in ("left", "right"):
            raise ValueError("direction must be left or right")
          test_id = uuid.uuid4().hex
          params.put_nonblocking("TeslaTurnSignalRequest", json.dumps({
            "id": test_id, "direction": direction, "created_ms": created_ms,
          }, separators=(",", ":"), sort_keys=True))
          self._json(202, {"accepted": True, "id": test_id, "direction": direction})
        elif path == "/api/v1/turn/cancel":
          test_id = str(payload.get("id", ""))
          if not test_id or len(test_id) > 64:
            raise ValueError("valid id is required")
          params.put_nonblocking("TeslaTurnSignalCancel", json.dumps({
            "id": test_id, "created_ms": created_ms,
          }, separators=(",", ":"), sort_keys=True))
          self._json(202, {"accepted": True, "id": test_id})
        else:
          self._json(404, {"error": "not_found"})
      except ValueError as error:
        self._json(400, {"error": str(error)})

  return TeslaToolsHandler
