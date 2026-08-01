import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from openpilot.selfdrive.debug import tesla_turn_signal_web


def test_turn_signal_web_page_exposes_both_five_frame_actions():
  page = tesla_turn_signal_web.render_page().decode()
  assert "左转" in page
  assert "右转" in page
  assert "5 个同方向" in page
  assert "card 实时线程" in page


def test_turn_signal_web_post_runs_requested_direction(monkeypatch):
  requested = []
  monkeypatch.setattr(tesla_turn_signal_web, "send_validation_pulse", lambda direction: requested.append(direction) or True)
  server = ThreadingHTTPServer(("127.0.0.1", 0), tesla_turn_signal_web.TurnSignalHandler)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  try:
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/turn/left", method="POST")
    with urllib.request.urlopen(request, timeout=2) as response:
      payload = json.loads(response.read())
    assert payload["ok"] is True
    assert requested == ["left"]
  finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
