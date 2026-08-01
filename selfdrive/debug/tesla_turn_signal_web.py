#!/usr/bin/env python3
import html
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openpilot.selfdrive.car.tesla_turn_signal_controller import VALIDATION_LOG_PATH
from openpilot.selfdrive.debug.tesla_turn_signal_test import (
  cancel_validation_session,
  get_validation_status,
  start_validation_session,
)


HOST = "0.0.0.0"
PORT = 8088
_SESSION_LOCK = threading.Lock()
_ACTIVE_WEB_TEST_ID: str | None = None
_ACTIVE_WEB_SESSION_STARTED = 0.0
WEB_SESSION_TIMEOUT_S = 20.0


def _clear_active_session(test_id: str) -> None:
  global _ACTIVE_WEB_SESSION_STARTED, _ACTIVE_WEB_TEST_ID
  with _SESSION_LOCK:
    if _ACTIVE_WEB_TEST_ID == test_id:
      _ACTIVE_WEB_TEST_ID = None
      _ACTIVE_WEB_SESSION_STARTED = 0.0


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
    #cancel {{ display:none; width:100%; min-height:72px; margin-top:16px; background:#dc2626; }}
    #status {{ min-height:72px; margin-top:22px; color:#fde68a; white-space:pre-wrap; }}
  </style>
</head>
<body><main>
  <h1>Tesla 转向 CAN 测试</h1>
  <p>请求由 card 实时线程跟随原车 0x3E9 模板持续发送；SP 判定变道进入完成阶段后自动关闭转向灯。</p>
  <div class="buttons"><button id="left" onclick="run('left')">← 左转</button><button id="right" onclick="run('right')">右转 →</button></div>
  <button id="cancel" onclick="cancelSession()">立即取消</button>
  <div id="status">{safe_message}</div>
</main><script>
let activeTestId = null;
const phaseText = {{
  queued: '请求已提交', waiting_vehicle_feedback: '等待车辆转向灯响应',
  waiting_sp_start: '等待 SP 开始变道', lane_changing: 'SP 正在执行变道',
  cancelling: '变道完成，正在关闭转向灯', confirming_cancel: '正在确认转向灯关闭'
}};
async function run(direction) {{
  document.querySelectorAll('#left,#right').forEach(button => button.disabled = true);
  const status = document.getElementById('status');
  status.textContent = '正在提交…';
  try {{
    const response = await fetch('/api/turn/' + direction, {{method:'POST'}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || '提交失败');
    activeTestId = result.test_id;
    document.getElementById('cancel').style.display = 'block';
    await pollStatus();
  }} catch (error) {{ finishUi('请求失败：' + error); }}
}}
async function pollStatus() {{
  if (!activeTestId) return;
  try {{
    const response = await fetch('/api/status/' + activeTestId, {{cache:'no-store'}});
    const result = await response.json();
    const detail = '已发送 ' + (result.action_frames_sent || 0) + ' 帧';
    if (result.done) {{
      const ok = result.result === 'PASS';
      finishUi((ok ? '完成：转向灯已自动关闭' : '结束：' + result.result) + '\\n' + detail);
      return;
    }}
    document.getElementById('status').textContent = (phaseText[result.phase] || result.phase) + '\\n' + detail;
    setTimeout(pollStatus, 200);
  }} catch (error) {{ finishUi('状态读取失败：' + error); }}
}}
async function cancelSession() {{
  if (!activeTestId) return;
  document.getElementById('status').textContent = '正在请求关闭转向灯…';
  try {{ await fetch('/api/cancel/' + activeTestId, {{method:'POST'}}); }}
  catch (error) {{ finishUi('取消请求失败：' + error); }}
}}
function finishUi(message) {{
  document.getElementById('status').textContent = message;
  document.querySelectorAll('#left,#right').forEach(button => button.disabled = false);
  document.getElementById('cancel').style.display = 'none';
  activeTestId = null;
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
    if self.path.startswith("/api/status/"):
      test_id = self.path.removeprefix("/api/status/")
      with _SESSION_LOCK:
        session_expired = (_ACTIVE_WEB_TEST_ID == test_id and
                           time.monotonic() - _ACTIVE_WEB_SESSION_STARTED >= WEB_SESSION_TIMEOUT_S)
      if session_expired:
        cancel_validation_session(test_id)
        _clear_active_session(test_id)
        self._json(HTTPStatus.OK, {"test_id": test_id, "done": True, "result": "WEB_SESSION_TIMEOUT"})
        return
      status = get_validation_status(test_id)
      if status.get("done"):
        _clear_active_session(test_id)
      self._json(HTTPStatus.OK, status)
      return
    if self.path not in ("/", "/index.html"):
      self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")
      return
    self._send(HTTPStatus.OK, "text/html; charset=utf-8", render_page())

  def do_POST(self) -> None:
    if self.path.startswith("/api/cancel/"):
      test_id = self.path.removeprefix("/api/cancel/")
      cancel_validation_session(test_id)
      self._json(HTTPStatus.ACCEPTED, {"ok": True, "test_id": test_id})
      return
    direction = self.path.removeprefix("/api/turn/")
    if direction not in ("left", "right") or self.path != f"/api/turn/{direction}":
      self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "未知测试请求"})
      return
    try:
      global _ACTIVE_WEB_SESSION_STARTED, _ACTIVE_WEB_TEST_ID
      with _SESSION_LOCK:
        if _ACTIVE_WEB_TEST_ID is not None:
          existing = get_validation_status(_ACTIVE_WEB_TEST_ID)
          session_expired = time.monotonic() - _ACTIVE_WEB_SESSION_STARTED >= WEB_SESSION_TIMEOUT_S
          if not existing.get("done") and not session_expired:
            self._json(HTTPStatus.CONFLICT, {"ok": False, "message": "已有变道请求正在运行"})
            return
          if not existing.get("done"):
            expired_test_id = _ACTIVE_WEB_TEST_ID
            cancel_validation_session(expired_test_id)
            _ACTIVE_WEB_TEST_ID = None
            _ACTIVE_WEB_SESSION_STARTED = 0.0
            self._json(HTTPStatus.CONFLICT, {
              "ok": False, "message": "上一变道请求已超时并取消，请稍后重试", "test_id": expired_test_id,
            })
            return
        test_id = start_validation_session(direction)
        _ACTIVE_WEB_TEST_ID = test_id
        _ACTIVE_WEB_SESSION_STARTED = time.monotonic()
      self._json(HTTPStatus.ACCEPTED, {"ok": True, "test_id": test_id, "log": VALIDATION_LOG_PATH})
    except RuntimeError as error:
      self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "message": f"测试被阻止：{error}"})

  def _json(self, status: HTTPStatus, payload: dict) -> None:
    self._send(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode())

  def log_message(self, message_format: str, *args) -> None:
    pass


def main() -> None:
  server = ThreadingHTTPServer((HOST, PORT), TurnSignalHandler)
  server.serve_forever()


if __name__ == "__main__":
  main()
