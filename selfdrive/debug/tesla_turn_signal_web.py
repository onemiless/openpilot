#!/usr/bin/env python3
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
from openpilot.selfdrive.debug.device_settings import settings_snapshot, validate_and_write
from openpilot.selfdrive.debug.device_hotspot import hotspot_status, set_hotspot_enabled
from openpilot.selfdrive.debug.device_terminal import change_password, run_command, terminal_status
from openpilot.selfdrive.debug.driving_status import driving_status_snapshot


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


def render_page() -> bytes:
  return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
  <title>车载设置</title>
  <style>
    :root { color-scheme:dark; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    body { margin:0; background:#111827; color:#f9fafb; } main { max-width:840px; margin:auto; padding:18px 14px 42px; }
    h1 { font-size:24px; margin:4px 0; } p { color:#cbd5e1; line-height:1.45; } .tabs { display:flex; gap:8px; margin:18px 0; }
    .tab, button { border:0; border-radius:12px; font-weight:700; color:white; background:#334155; padding:12px 16px; font-size:16px; }
    .tab.active { background:#2563eb; } .notice { padding:11px 13px; border-radius:10px; margin:12px 0; background:#14532d; color:#dcfce7; }
    .notice.onroad { background:#7c2d12; color:#ffedd5; } .group { margin:22px 0 9px; color:#93c5fd; font-size:15px; }
    .category-nav { display:flex; gap:8px; overflow-x:auto; padding:4px 0 10px; position:sticky; top:0; background:#111827; z-index:1; } .category { white-space:nowrap; padding:9px 12px; font-size:14px; }
    .category.active { background:#2563eb; }
    .card { display:grid; grid-template-columns:1fr auto; gap:10px; align-items:center; background:#1e293b; border-radius:13px; padding:14px; margin:8px 0; }
    .card h2 { font-size:16px; margin:0 0 5px; } .card p { font-size:13px; margin:0; } .lock { color:#fbbf24; font-size:12px; }
    input[type=number], select { width:120px; padding:9px; border:1px solid #475569; border-radius:9px; background:#0f172a; color:white; font-size:16px; }
    input[type=checkbox] { width:28px; height:28px; accent-color:#2563eb; } input:disabled, select:disabled, button:disabled { opacity:.45; }
    #turn-panel { text-align:center; } .buttons { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:28px; }
    .turn { min-height:120px; font-size:26px; } #left { background:#2563eb; } #right { background:#ea580c; } #cancel { display:none; width:100%; min-height:64px; margin-top:16px; background:#dc2626; }
    #status { min-height:52px; margin-top:18px; color:#fde68a; white-space:pre-wrap; }
    textarea { width:100%; min-height:130px; box-sizing:border-box; padding:11px; border:1px solid #475569; border-radius:10px; background:#020617; color:#e2e8f0; font:14px ui-monospace,monospace; }
    #terminal-output { min-height:100px; max-height:420px; overflow:auto; text-align:left; white-space:pre-wrap; background:#020617; border-radius:10px; padding:12px; color:#cbd5e1; }
    .terminal-row { display:flex; gap:8px; margin:10px 0; } .terminal-row input { min-width:0; flex:1; padding:9px; border:1px solid #475569; border-radius:9px; background:#0f172a; color:white; }
    .drive-alert { white-space:pre-wrap; } #driving-canvas { display:block; width:100%; height:min(68vh,560px); margin:12px 0; border-radius:13px; background:linear-gradient(#172554,#020617); }
  </style>
</head><body><main>
  <h1>车载设置</h1><p>通过手机或电脑访问此页面。行驶中仅允许修改实时生效的白名单设置。</p>
  <div class="tabs"><button class="tab active" id="settings-tab" onclick="showPanel('settings')">设置</button><button class="tab" id="driving-tab" onclick="showPanel('driving')">行驶信息</button><button class="tab" id="turn-tab" onclick="showPanel('turn')">转向测试</button><button class="tab" id="terminal-tab" onclick="showPanel('terminal')">终端</button></div>
  <section id="settings-panel"><div id="mode" class="notice">正在读取设置…</div><div id="category-nav" class="category-nav"></div><div id="settings"></div></section>
  <section id="driving-panel" hidden><h1>行驶道路视图</h1><p>只读实时视图；模型坐标由手机绘制，不启动视频或屏幕采集。</p><div id="driving-state" class="notice">正在连接车辆数据…</div><canvas id="driving-canvas" aria-label="预测道路轨迹"></canvas><div id="driving-alert" class="notice drive-alert" hidden></div></section>
  <section id="turn-panel" hidden>
    <h1>Tesla 转向 CAN 测试</h1><p>请求由 card 实时线程跟随原车 0x3E9 模板持续发送；SP 完成变道后会自动关闭转向灯。</p>
    <div class="buttons"><button class="turn" id="left" onclick="run('left')">← 左转</button><button class="turn" id="right" onclick="run('right')">右转 →</button></div>
    <button id="cancel" onclick="cancelSession()">立即取消</button><div id="status"></div>
  </section>
  <section id="terminal-panel" hidden>
    <h1>设备终端</h1><p>仅在设置模式（非行驶状态）且设备端显式启用后可用。命令最长 20 秒，输出上限 64 KiB。</p>
    <div id="terminal-state" class="notice">正在检查终端状态…</div><div class="terminal-row"><input id="terminal-password" type="password" autocomplete="off" placeholder="终端密码"><button onclick="runTerminal()">运行</button></div><p>默认密码：123456（仅需输入一次，浏览器会记住）</p><div class="terminal-row"><input id="terminal-new-password" type="password" autocomplete="new-password" placeholder="新密码（4-64个字符）"><button onclick="changeTerminalPassword()">修改密码</button></div>
    <textarea id="terminal-command" spellcheck="false" placeholder="git status --short"></textarea><pre id="terminal-output"></pre>
  </section>
<script>
let settingsState = null, hotspotState = null, selectedCategory = null, currentPanel = 'settings', drivingLoading = false;
function showPanel(name) {
  currentPanel = name;
  document.getElementById('settings-panel').hidden = name !== 'settings'; document.getElementById('driving-panel').hidden = name !== 'driving'; document.getElementById('turn-panel').hidden = name !== 'turn'; document.getElementById('terminal-panel').hidden = name !== 'terminal';
  document.getElementById('settings-tab').classList.toggle('active', name === 'settings'); document.getElementById('driving-tab').classList.toggle('active', name === 'driving'); document.getElementById('turn-tab').classList.toggle('active', name === 'turn'); document.getElementById('terminal-tab').classList.toggle('active', name === 'terminal');
  if (name === 'driving') loadDrivingStatus();
}
function element(tag, attrs = {}, text = '') { const e = document.createElement(tag); Object.assign(e, attrs); if (text) e.textContent = text; return e; }
function renderSettings(data) {
  settingsState = data; const mode = document.getElementById('mode'); mode.textContent = data.onroad ? '行驶中：只允许修改标注“行驶中可调”的设置。' : '设置模式：可修改全部白名单设置。'; mode.className = 'notice' + (data.onroad ? ' onroad' : '');
  const categories = data.menu; if (!selectedCategory || !categories.includes(selectedCategory)) selectedCategory = categories[0];
  const nav = document.getElementById('category-nav'); nav.replaceChildren(); categories.forEach(category => { const button = element('button', {className:'category' + (category === selectedCategory ? ' active' : '')}, category); button.onclick = () => { selectedCategory = category; renderSettings(data); }; nav.append(button); });
  const root = document.getElementById('settings'); root.replaceChildren(); let group = '';
  data.settings.filter(setting => setting.category === selectedCategory).sort((a,b) => a.group.localeCompare(b.group) || a.title.localeCompare(b.title)).forEach(setting => {
    if (setting.group !== group) { group = setting.group; root.append(element('div', {className:'group'}, group)); }
    const card = element('div', {className:'card'}), description = element('div'), title = element('h2', {}, setting.title || setting.key);
    description.append(title); if (setting.description) description.append(element('p', {}, setting.description));
    const locked = data.onroad && setting.offroad_only; if (locked) description.append(element('div', {className:'lock'}, '仅设置模式可调'));
    let control;
    if (setting.widget === 'toggle') { control = element('input', {type:'checkbox', checked:setting.value, disabled:locked}); control.onchange = () => save(setting, control.checked, control); }
    else if (setting.options) { control = element('select', {disabled:locked}); setting.options.forEach(option => control.append(element('option', {value:String(option.value), selected:option.value === setting.value}, option.label))); control.onchange = () => save(setting, control.value === '' ? '' : Number(control.value), control); }
    else { control = element('input', {type:'number', value:setting.value, min:setting.min ?? '', max:setting.max ?? '', step:setting.step ?? 1, disabled:locked}); control.onchange = () => save(setting, Number(control.value), control); }
    control.title = setting.key; card.append(description, control); root.append(card);
  });
  if (selectedCategory === '设备' && hotspotState?.available) {
    const card = element('div', {className:'card'}), description = element('div');
    description.append(element('h2', {}, '设备 Wi-Fi 热点'));
    description.append(element('p', {}, hotspotState.active ? '热点已开启。连接后访问 ' + hotspotState.url : '开启后设备会切换为热点；连接手机或电脑后访问 ' + hotspotState.url));
    const control = element('input', {type:'checkbox', checked:hotspotState.active});
    control.onchange = () => saveHotspot(control.checked, control); card.append(description, control); root.append(card);
  }
}
async function loadSettings() { try { const [settingsResponse, hotspotResponse] = await Promise.all([fetch('/api/settings', {cache:'no-store'}), fetch('/api/hotspot', {cache:'no-store'})]); if (!settingsResponse.ok) throw new Error('HTTP ' + settingsResponse.status); hotspotState = hotspotResponse.ok ? await hotspotResponse.json() : null; renderSettings(await settingsResponse.json()); } catch (e) { document.getElementById('mode').textContent = '设置读取失败：' + e; } }
async function save(setting, value, control) { control.disabled = true; try { const r = await fetch('/api/settings/' + encodeURIComponent(setting.key), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({value})}); const result = await r.json(); if (!r.ok) throw new Error(result.message || 'HTTP ' + r.status); setting.value = result.value; } catch (e) { alert('保存失败：' + e); } finally { renderSettings(settingsState); } }
async function saveHotspot(enabled, control) { control.disabled = true; try { const r = await fetch('/api/hotspot', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled})}); const result = await r.json(); if (!r.ok) throw new Error(result.message || 'HTTP ' + r.status); hotspotState = result; renderSettings(settingsState); } catch (e) { alert('热点切换失败：' + e); renderSettings(settingsState); } }
loadSettings();
function drawLine(ctx, points, xScale, yScale, color, width) { if (!points.length) return; ctx.beginPath(); points.forEach(([x,y], i) => { const px = ctx.canvas.clientWidth / 2 + y * yScale, py = ctx.canvas.clientHeight - 32 - x * xScale; i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke(); }
function drawDrivingGeometry(geometry, data) { const canvas = document.getElementById('driving-canvas'), ratio = window.devicePixelRatio || 1, width = Math.max(1, canvas.clientWidth), height = Math.max(1, canvas.clientHeight); if (canvas.width !== width * ratio || canvas.height !== height * ratio) { canvas.width = width * ratio; canvas.height = height * ratio; } const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height); ctx.fillStyle = '#020617'; ctx.fillRect(0, 0, width, height); const xScale = (height - 54) / 100, yScale = Math.min(width / 10, 30), danger = geometry.hard_brake_predicted; ctx.setLineDash([7,7]); (geometry.edges || []).forEach(line => drawLine(ctx, line, xScale, yScale, '#64748b', 2)); ctx.setLineDash([]); (geometry.lanes || []).forEach(line => drawLine(ctx, line, xScale, yScale, '#e2e8f0', 2)); drawLine(ctx, geometry.path || [], xScale, yScale, danger ? '#ef4444' : '#22c55e', 5); const traffic = geometry.oem_traffic || {}; if (traffic.available && traffic.stop_line_distance >= 0 && traffic.stop_line_distance <= 100) { const colors = ['#94a3b8','#ef4444','#22c55e','#facc15'], color = colors[traffic.light_color] || '#f8fafc', py = height - 32 - traffic.stop_line_distance * xScale; ctx.strokeStyle = color; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(width / 2 - 58, py); ctx.lineTo(width / 2 + 58, py); ctx.stroke(); ctx.fillStyle = color; ctx.font = 'bold 13px sans-serif'; ctx.fillText(['未知','红灯','绿灯','黄灯'][traffic.light_color] || '交通灯', width / 2 + 64, py + 4); } ctx.fillStyle = '#2563eb'; ctx.fillRect(width / 2 - 14, height - 30, 28, 20); (geometry.leads || []).forEach(lead => { const px = width / 2 + lead.y * yScale, py = height - 32 - lead.x * xScale; if (py > 0 && py < height) { ctx.fillStyle = danger ? '#ef4444' : '#f97316'; ctx.fillRect(px - 7, py - 7, 14, 14); ctx.fillStyle = '#f8fafc'; ctx.font = '12px sans-serif'; ctx.fillText(Math.round(lead.x) + 'm', px + 10, py + 4); } }); ctx.fillStyle = '#f8fafc'; ctx.font = 'bold 17px sans-serif'; ctx.fillText(data.speed_kph.toFixed(0) + ' km/h', 14, 28); ctx.font = '13px sans-serif'; const mode = data.openpilot_enabled ? 'SP 接管' : data.mads_enabled ? 'MADS 横向' : '未接管'; ctx.fillText(mode + '  ·  设定 ' + data.set_speed_kph.toFixed(0) + ' km/h', 14, 49); if (geometry.lane_change !== 'off') { ctx.fillStyle = '#fbbf24'; ctx.font = 'bold 15px sans-serif'; ctx.fillText('变道 ' + (geometry.lane_change_direction === 'left' ? '←' : geometry.lane_change_direction === 'right' ? '→' : '进行中'), width - 92, 28); } if (danger) { ctx.fillStyle = '#fecaca'; ctx.fillText('注意制动风险', width - 100, 50); } }
async function loadDrivingStatus() { if (drivingLoading) return; drivingLoading = true; const state = document.getElementById('driving-state'), alert = document.getElementById('driving-alert'); try { const r = await fetch('/api/driving-status', {cache:'no-store'}); const data = await r.json(); if (!r.ok) throw new Error(data.message || 'HTTP ' + r.status); const connected = Object.values(data.connected).every(Boolean); state.textContent = !data.onroad ? '设置模式：等待车辆启动。' : connected ? '行驶中：车辆数据正常。' : '行驶中：部分车辆数据暂未收到。'; state.className = 'notice' + ((!data.onroad || !connected) ? ' onroad' : ''); drawDrivingGeometry(data.geometry, data); alert.hidden = !data.alert; alert.textContent = data.alert || ''; } catch (e) { state.textContent = '行驶数据读取失败：' + e; state.className = 'notice onroad'; } finally { drivingLoading = false; } }
setInterval(() => { if (currentPanel === 'driving') loadDrivingStatus(); }, 500);
async function loadTerminalStatus() { const el = document.getElementById('terminal-state'); try { const r = await fetch('/api/terminal/status', {cache:'no-store'}); const s = await r.json(); el.textContent = !s.enabled ? '终端未启用：请在设备上显式启用。' : s.onroad ? '行驶中：请先进入设置模式。' : '终端已启用：请输入密码后运行。'; el.className = 'notice' + ((!s.enabled || s.onroad) ? ' onroad' : ''); } catch (e) { el.textContent = '终端状态读取失败：' + e; } }
const terminalPasswordInput = document.getElementById('terminal-password'); terminalPasswordInput.value = localStorage.getItem('openpilotTerminalPassword') || '123456';
async function runTerminal() { const password = terminalPasswordInput.value, command = document.getElementById('terminal-command').value, output = document.getElementById('terminal-output'); output.textContent = '正在运行…'; try { const r = await fetch('/api/terminal/exec', {method:'POST', headers:{'Content-Type':'application/json', 'X-Terminal-Password':password}, body:JSON.stringify({command})}); const result = await r.json(); if (!r.ok) throw new Error(result.message || 'HTTP ' + r.status); localStorage.setItem('openpilotTerminalPassword', password); output.textContent = `[exit ${result.exit_code}${result.timed_out ? ', timeout' : ''}]\n` + result.output; } catch (e) { output.textContent = '运行失败：' + e; } }
async function changeTerminalPassword() { const password = terminalPasswordInput.value, newPassword = document.getElementById('terminal-new-password').value; try { const r = await fetch('/api/terminal/password', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({current_password:password, new_password:newPassword})}); const result = await r.json(); if (!r.ok) throw new Error(result.message || 'HTTP ' + r.status); terminalPasswordInput.value = newPassword; localStorage.setItem('openpilotTerminalPassword', newPassword); document.getElementById('terminal-new-password').value = ''; alert('密码已修改'); } catch (e) { alert('修改失败：' + e); } }
loadTerminalStatus();
let activeTestId = null;
const phaseText = {
  queued: '请求已提交', waiting_vehicle_feedback: '等待车辆转向灯响应',
  waiting_sp_start: '等待 SP 开始变道', lane_changing: 'SP 正在执行变道',
  cancelling: '变道完成，正在关闭转向灯', confirming_cancel: '正在确认转向灯关闭'
};
async function run(direction) {
  document.querySelectorAll('#left,#right').forEach(button => button.disabled = true);
  const status = document.getElementById('status');
  status.textContent = '正在提交…';
  try {
    const response = await fetch('/api/turn/' + direction, {method:'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || '提交失败');
    activeTestId = result.test_id;
    document.getElementById('cancel').style.display = 'block';
    await pollStatus();
  } catch (error) { finishUi('请求失败：' + error); }
}
async function pollStatus() {
  if (!activeTestId) return;
  try {
    const response = await fetch('/api/status/' + activeTestId, {cache:'no-store'});
    const result = await response.json();
    const detail = '已发送 ' + (result.action_frames_sent || 0) + ' 帧';
    if (result.done) {
      const ok = result.result === 'PASS';
      finishUi((ok ? '完成：转向灯已自动关闭' : '结束：' + result.result) + '\\n' + detail);
      return;
    }
    document.getElementById('status').textContent = (phaseText[result.phase] || result.phase) + '\\n' + detail;
    setTimeout(pollStatus, 200);
  } catch (error) { finishUi('状态读取失败：' + error); }
}
async function cancelSession() {
  if (!activeTestId) return;
  document.getElementById('status').textContent = '正在请求关闭转向灯…';
  try { await fetch('/api/cancel/' + activeTestId, {method:'POST'}); }
  catch (error) { finishUi('取消请求失败：' + error); }
}
function finishUi(message) {
  document.getElementById('status').textContent = message;
  document.querySelectorAll('#left,#right').forEach(button => button.disabled = false);
  document.getElementById('cancel').style.display = 'none';
  activeTestId = null;
}
</script></main></body></html>""".encode()


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
    if self.path == "/api/hotspot":
      self._json(HTTPStatus.OK, hotspot_status())
      return
    if self.path == "/api/driving-status":
      try:
        self._json(HTTPStatus.OK, driving_status_snapshot())
      except Exception as error:
        self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "message": f"行驶数据暂不可用：{error}"})
      return
    if self.path == "/api/terminal/status":
      self._json(HTTPStatus.OK, terminal_status())
      return
    if self.path == "/api/settings":
      self._json(HTTPStatus.OK, settings_snapshot())
      return
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
    if self.path == "/api/hotspot":
      try:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 4096:
          raise ValueError("请求内容无效")
        payload = json.loads(self.rfile.read(content_length))
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
          raise ValueError("请求必须包含 enabled 开关")
        self._json(HTTPStatus.OK, set_hotspot_enabled(payload["enabled"]))
      except RuntimeError as error:
        self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "message": str(error)})
      except (TypeError, ValueError, json.JSONDecodeError) as error:
        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(error)})
      return
    if self.path == "/api/terminal/password":
      try:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 8192:
          raise ValueError("请求内容无效")
        payload = json.loads(self.rfile.read(content_length))
        if not isinstance(payload, dict):
          raise ValueError("请求必须为 JSON 对象")
        change_password(payload.get("current_password"), payload.get("new_password"))
        self._json(HTTPStatus.OK, {"ok": True})
      except PermissionError as error:
        self._json(HTTPStatus.FORBIDDEN, {"ok": False, "message": str(error)})
      except (TypeError, ValueError, json.JSONDecodeError) as error:
        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(error)})
      return
    if self.path == "/api/terminal/exec":
      try:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 8192:
          raise ValueError("请求内容无效")
        payload = json.loads(self.rfile.read(content_length))
        if not isinstance(payload, dict) or "command" not in payload:
          raise ValueError("请求必须包含 command")
        self._json(HTTPStatus.OK, run_command(payload["command"], self.headers.get("X-Terminal-Password")))
      except PermissionError as error:
        self._json(HTTPStatus.FORBIDDEN, {"ok": False, "message": str(error)})
      except (TypeError, ValueError, json.JSONDecodeError) as error:
        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(error)})
      return
    if self.path.startswith("/api/settings/"):
      key = self.path.removeprefix("/api/settings/")
      if not key or "/" in key:
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "未知设置"})
        return
      try:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 4096:
          raise ValueError("请求内容无效")
        payload = json.loads(self.rfile.read(content_length))
        if not isinstance(payload, dict) or "value" not in payload:
          raise ValueError("请求必须包含 value")
        self._json(HTTPStatus.OK, {"ok": True, **validate_and_write(key, payload["value"])})
      except KeyError:
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "未知或不允许修改的设置"})
      except PermissionError as error:
        self._json(HTTPStatus.FORBIDDEN, {"ok": False, "message": str(error)})
      except (TypeError, ValueError, json.JSONDecodeError) as error:
        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(error)})
      return
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
