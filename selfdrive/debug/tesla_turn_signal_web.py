#!/usr/bin/env python3
import html
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openpilot.selfdrive.debug.tesla_turn_signal_test import ACTION_FRAME_COUNT, VALIDATION_LOG_PATH, send_validation_pulse


HOST = "0.0.0.0"
PORT = 8088
_TEST_LOCK = threading.Lock()


def render_page(message: str = "") -> bytes:
  safe_message = html.escape(message)
  return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
  <title>Tesla 转向 CAN 测试</title>
  <style>
    body {{ margin:0; background:#111827; color:#f9fafb; font-family:sans-serif; }}
    main {{ max-width:680px; margin:auto; padding:28px 18px; text-align:center; }}
    h1 {{ font-size:26px; }} p {{ color:#cbd5e1; line-height:1.5; }}
    .buttons {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:28px; }}
    button {{ min-height:128px; border:0; border-radius:18px; font-size:28px; font-weight:700; color:white; }}
    #left {{ background:#2563eb; }} #right {{ background:#ea580c; }}
    button:disabled {{ opacity:.45; }}
    #status {{ min-height:52px; margin-top:22px; color:#fde68a; white-space:pre-wrap; }}
  </style>
</head>
<body><main>
  <h1>Tesla 转向 CAN 测试</h1>
  <p>每次发送 {ACTION_FRAME_COUNT} 个同方向 0x3E9 有效帧，然后发送取消帧。请一次只点击一个方向。</p>
  <div class="buttons"><button id="left" onclick="run('left')">← 左转</button><button id="right" onclick="run('right')">右转 →</button></div>
  <div id="status">{safe_message}</div>
</main><script>
async function run(direction) {{
  const buttons = document.querySelectorAll('button');
  buttons.forEach(button => button.disabled = true);
  const status = document.getElementById('status');
  status.textContent = '正在发送，请等待…';
  try {{
    const response = await fetch('/api/turn/' + direction, {{method:'POST'}});
    const result = await response.json();
    status.textContent = result.message;
  }} catch (error) {{ status.textContent = '请求失败：' + error; }}
  finally {{ buttons.forEach(button => button.disabled = false); }}
}}
</script></body></html>""".encode()


class TurnSignalHandler(BaseHTTPRequestHandler):
  server_version = "TeslaTurnSignalTest/1.0"

  def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
    self.send_response(status)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(body)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(body)

  def do_GET(self) -> None:
    if self.path not in ("/", "/index.html"):
      self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")
      return
    self._send(HTTPStatus.OK, "text/html; charset=utf-8", render_page())

  def do_POST(self) -> None:
    direction = self.path.removeprefix("/api/turn/")
    if direction not in ("left", "right") or self.path != f"/api/turn/{direction}":
      self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "未知测试请求"})
      return
    if not _TEST_LOCK.acquire(blocking=False):
      self._json(HTTPStatus.CONFLICT, {"ok": False, "message": "已有测试正在运行，请稍后重试"})
      return
    try:
      passed = send_validation_pulse(direction)
      message = (f"{direction}: 车辆反馈已确认；日志：{VALIDATION_LOG_PATH}" if passed else
                 f"{direction}: 已发送，但未确认车辆反馈；请查看 {VALIDATION_LOG_PATH}")
      self._json(HTTPStatus.OK, {"ok": passed, "message": message})
    except RuntimeError as error:
      self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "message": f"测试被阻止：{error}"})
    finally:
      _TEST_LOCK.release()

  def _json(self, status: HTTPStatus, payload: dict) -> None:
    self._send(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode())

  def log_message(self, message_format: str, *args) -> None:
    pass


def main() -> None:
  server = ThreadingHTTPServer((HOST, PORT), TurnSignalHandler)
  server.serve_forever()


if __name__ == "__main__":
  main()
