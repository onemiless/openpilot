"""Bounded screen routes for the existing device console on port 8088."""
import base64
import hashlib
import json
import struct
import threading
import time
from http import HTTPStatus

from openpilot.system.ui.lib.screen_cast import (
  FRAME_PATH, STATUS_PATH, mark_viewer_active, screen_cast_enabled, send_control, validate_pointer,
)

_stream_lock = threading.Lock()
_control_lock = threading.Lock()
BOUNDARY = b"c3-screen"


def render_page():
  return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>C3 投屏</title><style>
html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#000;color:#fff;font-family:system-ui,sans-serif}
#screen{width:100vw;height:100vh;display:block;object-fit:contain;touch-action:none;user-select:none}
#status{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);padding:14px;background:#111d;pointer-events:none}
#full{position:fixed;right:14px;bottom:14px;padding:10px;border-radius:10px;background:#111c;color:#fff}
</style></head><body><img id="screen" alt="C3 画面"><div id="status">连接中…</div>
<button id="full">全屏</button><script>
const image=document.getElementById('screen'),status=document.getElementById('status');
const pointers=new Map(),lastMove=new Map();let ws,retry,heartbeat;
function point(e){const r=image.getBoundingClientRect(),nw=image.naturalWidth||r.width,nh=image.naturalHeight||r.height,s=Math.min(r.width/nw,r.height/nh),w=nw*s,h=nh*s,l=r.left+(r.width-w)/2,t=r.top+(r.height-h)/2;return{x:Math.max(0,Math.min(1,(e.clientX-l)/w)),y:Math.max(0,Math.min(1,(e.clientY-t)/h))};}
function send(e,action){if(!ws||ws.readyState!==1)return;let id=action===0?(pointers.size<2?[0,1].find(v=>![...pointers.values()].includes(v)):null):pointers.get(e.pointerId);if(id===undefined||id===null)return;if(action===0)pointers.set(e.pointerId,id);ws.send(JSON.stringify({type:'pointer',action,pointerId:id,...point(e)}));if(action===1||action===3){pointers.delete(e.pointerId);lastMove.delete(e.pointerId)}}
function connect(){clearTimeout(retry);ws=new WebSocket('ws://'+location.host+'/api/screen/control');
ws.onopen=()=>{clearInterval(heartbeat);heartbeat=setInterval(()=>{if(ws.readyState===1)ws.send(JSON.stringify({type:'heartbeat'}))},1000)};
ws.onclose=()=>{clearInterval(heartbeat);pointers.clear();lastMove.clear();status.textContent='触控已断开，正在重连';status.style.display='block';retry=setTimeout(connect,2000)};}
function load(){image.src='/api/screen/stream?t='+Date.now()}
image.onload=()=>{status.style.display='none'};image.onerror=()=>{status.textContent='请在 C3 设置中开启投屏，正在重试';status.style.display='block';setTimeout(load,2500)};
image.addEventListener('pointerdown',e=>{e.preventDefault();image.setPointerCapture(e.pointerId);send(e,0)});
image.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;e.preventDefault();const n=performance.now();if(n-(lastMove.get(e.pointerId)||0)<32)return;lastMove.set(e.pointerId,n);send(e,2)});
image.addEventListener('pointerup',e=>{e.preventDefault();send(e,1)});image.addEventListener('pointercancel',e=>send(e,3));
document.getElementById('full').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen?.({navigationUI:'hide'})};
document.addEventListener('visibilitychange',()=>{if(document.hidden){ws?.close();image.removeAttribute('src')}else{load();if(!ws||ws.readyState>1)connect()}});
load();connect();</script></body></html>'''.encode()


def _stream(handler):
  if not _stream_lock.acquire(False):
    handler._send(HTTPStatus.CONFLICT, "text/plain", b"Only one screen viewer at a time")
    return
  try:
    handler.connection.settimeout(2)
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=c3-screen")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()
    last_frame = -1
    checked = 0.0
    while True:
      now = time.monotonic()
      if now - checked >= 0.5:
        if not screen_cast_enabled():
          break
        checked = now
      mark_viewer_active()
      try:
        stat = FRAME_PATH.stat()
        if stat.st_mtime_ns != last_frame and time.time() - stat.st_mtime < 3:
          frame = FRAME_PATH.read_bytes()
          handler.wfile.write(b"--" + BOUNDARY + b"\r\nContent-Type: image/jpeg\r\n" +
                              f"Content-Length: {len(frame)}\r\n\r\n".encode() + frame + b"\r\n")
          handler.wfile.flush()
          last_frame = stat.st_mtime_ns
      except FileNotFoundError:
        pass
      time.sleep(0.1)
  except (OSError, TimeoutError):
    pass
  finally:
    handler.close_connection = True
    _stream_lock.release()


def _accept(key):
  return base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()  # noqa: S324


def _read_frame(stream):
  header = stream.read(2)
  if len(header) != 2:
    return None
  first, second = header
  if not first & 0x80 or first & 0x70 or not second & 0x80:
    raise ValueError("fragmented or unmasked frame")
  opcode, length = first & 15, second & 127
  if length == 127:
    raise ValueError("oversized frame")
  if length == 126:
    raw = stream.read(2)
    if len(raw) != 2:
      return None
    length = struct.unpack("!H", raw)[0]
  if length > 4096 or (opcode >= 8 and length > 125):
    raise ValueError("oversized frame")
  mask, payload = stream.read(4), stream.read(length)
  if len(mask) != 4 or len(payload) != length:
    return None
  return opcode, bytes(v ^ mask[i % 4] for i, v in enumerate(payload))


def _control(handler):
  key = handler.headers.get("Sec-WebSocket-Key", "")
  try:
    valid_key = len(base64.b64decode(key, validate=True)) == 16
  except ValueError:
    valid_key = False
  if handler.headers.get("Upgrade", "").lower() != "websocket" or not valid_key:
    handler._send(HTTPStatus.BAD_REQUEST, "text/plain", b"WebSocket required")
    return
  if not _control_lock.acquire(False):
    handler._send(HTTPStatus.CONFLICT, "text/plain", b"Only one controller at a time")
    return
  try:
    handler.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", _accept(key))
    handler.end_headers()
    # Browser heartbeat every second. Timeout ends this buffered stream; never reuse it.
    handler.connection.settimeout(4)
    last_check = 0.0
    while True:
      now = time.monotonic()
      if now - last_check >= 0.5:
        if not screen_cast_enabled():
          break
        last_check = now
      frame = _read_frame(handler.rfile)
      if frame is None:
        break
      opcode, payload = frame
      if opcode == 8:
        break
      if opcode == 9:
        handler.wfile.write(bytes((0x8A, len(payload))) + payload)
        continue
      if opcode != 1:
        continue
      try:
        value = json.loads(payload)
        if isinstance(value, dict) and value.get("type") == "heartbeat":
          send_control({"type": "heartbeat"})
        else:
          validate_pointer(value)
          send_control(value)
      except (ValueError, TypeError):
        continue
  except (OSError, TimeoutError, ValueError):
    pass
  finally:
    try:
      send_control({"type": "cancel"})
    except OSError:
      pass
    handler.close_connection = True
    _control_lock.release()


def serve_screen_cast(handler, path):
  if path in ("/screen", "/screen/"):
    handler._send(HTTPStatus.OK, "text/html; charset=utf-8", render_page())
    return
  enabled = screen_cast_enabled()
  if path == "/api/screen/health":
    try:
      status = json.loads(STATUS_PATH.read_text())
      status["frame_age_ms"] = round((time.time() - FRAME_PATH.stat().st_mtime) * 1000)
    except (OSError, ValueError):
      status = {"frame_age_ms": None}
    handler._json(HTTPStatus.OK, {**status, "enabled": enabled})
  elif not enabled:
    handler._send(HTTPStatus.FORBIDDEN, "text/plain", b"Enable screen casting on C3 first")
  elif path == "/api/screen/stream":
    _stream(handler)
  elif path == "/api/screen/control":
    _control(handler)
  else:
    handler._send(HTTPStatus.NOT_FOUND, "text/plain", b"Not found")
