from __future__ import annotations

import json
import queue
import socketserver
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from openpilot.sunnypilot.companion.http_ws import ReusableThreadingHTTPServer, WebSocketClosed, accept_websocket, \
  json_bytes, read_json_body, send_json, send_websocket_frame, trusted_local_address, websocket_receive_loop
from openpilot.sunnypilot.companion.params_api import ParamAccess
from openpilot.sunnypilot.companion.telemetry import REQUESTABLE_SERVICES, TelemetryBroker


DEFAULT_HTTP_PORT = 7000
DEFAULT_LEGACY_PORT = 7711


def make_request_handler(broker: TelemetryBroker, params: ParamAccess) -> type[BaseHTTPRequestHandler]:
  class CompanionRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
      pass

    def do_GET(self) -> None:
      if not trusted_local_address(self.client_address[0]):
        send_json(self, 403, {"ok": False, "error": "local network access only"})
        return
      parsed = urlsplit(self.path)
      if parsed.path in ("/", "/health", "/api/health"):
        send_json(self, 200, {"ok": True, "service": "sunnypilot-companion", "version": 1})
        return
      if parsed.path == "/api/params_bulk":
        self._params_bulk(parse_qs(parsed.query).get("names", [""])[0])
        return
      if parsed.path == "/ws/raw_multiplex":
        self._raw_multiplex(parse_qs(parsed.query).get("services", [""])[0])
        return
      send_json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
      if not trusted_local_address(self.client_address[0]):
        send_json(self, 403, {"ok": False, "error": "local network access only"})
        return
      if urlsplit(self.path).path != "/api/param_set":
        send_json(self, 404, {"ok": False, "error": "not found"})
        return
      try:
        payload = read_json_body(self)
        params.write(payload.get("name"), payload.get("value"))
      except PermissionError as exc:
        send_json(self, 403, {"ok": False, "error": str(exc)})
      except ValueError as exc:
        send_json(self, 400, {"ok": False, "error": str(exc)})
      else:
        send_json(self, 200, {"ok": True})

    def _params_bulk(self, raw_names: str) -> None:
      names = [name.strip() for name in raw_names.split(",") if name.strip()]
      try:
        values = params.read(names)
      except PermissionError as exc:
        send_json(self, 403, {"ok": False, "error": str(exc)})
      except ValueError as exc:
        send_json(self, 400, {"ok": False, "error": str(exc)})
      else:
        send_json(self, 200, {"ok": True, "values": values})

    def _raw_multiplex(self, raw_services: str) -> None:
      services = list(dict.fromkeys(name.strip() for name in raw_services.split(",") if name.strip()))
      invalid = sorted(set(services) - REQUESTABLE_SERVICES)
      if not services or invalid:
        send_json(self, 404 if invalid else 400,
                  {"ok": False, "error": f"unknown or missing services: {','.join(invalid)}"})
        return
      try:
        accept_websocket(self)
      except ValueError as exc:
        send_json(self, 400, {"ok": False, "error": str(exc)})
        return
      client_id, output = broker.register(services)
      write_lock = threading.Lock()
      stopped = threading.Event()

      def receive() -> None:
        try:
          for _opcode, _payload in websocket_receive_loop(self, write_lock):
            pass
        except (WebSocketClosed, OSError, ValueError):
          pass
        finally:
          stopped.set()

      reader = threading.Thread(target=receive, name="companion-ws-reader", daemon=True)
      reader.start()
      try:
        hello = {"mode": "carrot-raw-multiplex-v1", "services": services}
        send_websocket_frame(self, 0x1, json_bytes(hello), write_lock)
        while not stopped.is_set():
          try:
            frame = output.get(timeout=1.0)
          except queue.Empty:
            continue
          send_websocket_frame(self, 0x2, frame, write_lock)
      except (BrokenPipeError, ConnectionResetError, OSError):
        pass
      finally:
        stopped.set()
        broker.unregister(client_id)
        self.close_connection = True

  return CompanionRequestHandler


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
  allow_reuse_address = True
  daemon_threads = True

  def verify_request(self, request, client_address) -> bool:
    return trusted_local_address(client_address[0])


def make_legacy_handler(broker: TelemetryBroker) -> type[socketserver.BaseRequestHandler]:
  class LegacyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
      while True:
        payload = json.dumps(broker.legacy_packet(), ensure_ascii=False, separators=(",", ":")).encode()
        try:
          self.request.sendall(struct.pack("!I", len(payload)) + payload)
        except OSError:
          return
        time.sleep(0.2)

  return LegacyHandler


class CompanionServer:
  def __init__(self, broker: TelemetryBroker, params: ParamAccess, *, bind_host: str = "0.0.0.0",
               http_port: int = DEFAULT_HTTP_PORT, legacy_port: int = DEFAULT_LEGACY_PORT) -> None:
    self.broker = broker
    self.http = ReusableThreadingHTTPServer((bind_host, http_port), make_request_handler(broker, params))
    self.legacy = ReusableThreadingTCPServer((bind_host, legacy_port), make_legacy_handler(broker))
    self._threads: list[threading.Thread] = []

  def start(self) -> None:
    self.broker.start()
    self._threads = [
      self.http.start_in_thread("companion-http"),
      threading.Thread(target=self.legacy.serve_forever, name="companion-legacy", daemon=True),
    ]
    self._threads[1].start()

  def close(self) -> None:
    self.http.shutdown()
    self.http.server_close()
    self.legacy.shutdown()
    self.legacy.server_close()
