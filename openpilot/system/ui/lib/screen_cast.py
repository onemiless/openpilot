"""On-demand UI thumbnails and remote pointers; no vehicle-control publisher."""
import io
import json
import math
import os
from pathlib import Path
import queue
import socket
import threading
import time
from typing import TYPE_CHECKING

from openpilot.common.params import Params

if TYPE_CHECKING:
  from openpilot.system.ui.lib.application import MouseState

ENABLED_PARAM = "C3ScreenCasting"
RUNTIME_DIR = Path(os.getenv("OPENPILOT_SCREEN_CAST_DIR", "/dev/shm"))
FRAME_PATH = RUNTIME_DIR / "openpilot_screen_cast.jpg"
STATUS_PATH = RUNTIME_DIR / "openpilot_screen_cast.json"
VIEWER_PATH = RUNTIME_DIR / "openpilot_screen_cast.viewer"
CONTROL_ADDRESS = ("127.0.0.1", 8099)
WIDTH = 960
JPEG_QUALITY = 60
VIEWER_TIMEOUT = 3.0
CONTROL_TIMEOUT = 2.5
_viewer_lock = threading.Lock()
_viewer_at = 0.0


def screen_cast_enabled(params=None):
  return (params or Params()).get_bool(ENABLED_PARAM)


def mark_viewer_active():
  global _viewer_at
  with _viewer_lock:
    now = time.monotonic()
    if now - _viewer_at >= 0.5:
      VIEWER_PATH.touch()
      _viewer_at = now


def send_control(message):
  with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.sendto(json.dumps(message, separators=(",", ":")).encode(), CONTROL_ADDRESS)


def notify_screen_cast(enabled):
  send_control({"type": "enabled", "enabled": bool(enabled)})


def validate_pointer(value):
  if not isinstance(value, dict) or value.get("type") != "pointer":
    raise ValueError("pointer required")
  action, slot, x, y = (value.get(k) for k in ("action", "pointerId", "x", "y"))
  if type(action) is not int or action not in (0, 1, 2, 3) or type(slot) is not int or slot not in (0, 1):
    raise ValueError("invalid action or slot")
  if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in (x, y)):
    raise ValueError("invalid coordinates")
  return action, slot, x, y


def capture_interval(onroad, cpu, temperature, cost_ms):
  fps = 2.0 if onroad else 4.0
  if temperature >= 75 or cpu >= 85:
    fps = min(fps, 0.5)
  elif temperature >= 70 or cpu >= 75:
    fps = min(fps, 1.0)
  # Combined CPU cost stays below 8% of one core; always drop instead of queueing.
  return max(1.0 / fps, cost_ms / 80.0)


def _background_thread(nice):
  # UI is FIFO/CPU5: new threads inherit both unless explicitly reset on Linux.
  if hasattr(os, "sched_setscheduler"):
    os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
    # UI starts on CPU0 before moving to CPU5. Replace either inherited mask.
    os.sched_setaffinity(0, set(range(4)))
    os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), nice)


class ScreenCastRuntime:
  def __init__(self, mouse: "MouseState", width: int, height: int, params=None):
    self._mouse, self._width, self._height = mouse, width, height
    self._params = params or Params()
    self._queue = queue.Queue(maxsize=1)
    self._stop = threading.Event()
    self._threads = []
    self._enabled = screen_cast_enabled(self._params)
    self._checked = self._last_capture = 0.0
    self._interval = 0.5
    self._target = self._thumbnail = None
    self._capture_ms = self._encode_ms = 0.0
    self._capture_wall_ms = 0.0
    self._last_status = 0.0
    self._frames = 0
    self._error = ""
    self._worker = {}
    self._socket = None

  def start(self):
    for target, name in ((self._encode, "cast-jpeg"), (self._receive, "cast-input")):
      thread = threading.Thread(target=target, name=name, daemon=True)
      self._threads.append(thread)
      thread.start()

  def stop(self):
    self._stop.set()
    try:
      self._queue.put_nowait(None)
    except queue.Full:
      pass
    if self._socket:
      send_control({"type": "cancel"})
    for thread in self._threads:
      thread.join(timeout=1)
    if self._socket:
      self._socket.close()
    self._mouse.cancel_remote_events()
    if self._target or self._thumbnail:
      import pyray as rl
      for target in (self._target, self._thumbnail):
        if target:
          rl.unload_render_texture(target)
      self._target = self._thumbnail = None

  def _is_enabled(self, now):
    return self._enabled

  def _viewer_active(self):
    try:
      return time.time() - VIEWER_PATH.stat().st_mtime < VIEWER_TIMEOUT
    except FileNotFoundError:
      return False

  def should_capture(self):
    now = time.monotonic()
    if not self._is_enabled(now) or now - self._last_capture < self._interval:
      return False
    if not self._viewer_active() or self._queue.full():
      return False
    self._last_capture = now
    return True

  def render_target(self, width, height):
    import pyray as rl
    if self._target is None:
      self._target = rl.load_render_texture(width, height)
      rl.set_texture_filter(self._target.texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
    return self._target

  def capture_texture(self, texture, render_cpu_ms=0.0):
    import pyray as rl
    start = time.monotonic()
    cpu_start = time.thread_time()
    try:
      width = min(WIDTH, texture.width)
      height = max(2, round(texture.height * width / texture.width))
      if self._thumbnail is None:
        self._thumbnail = rl.load_render_texture(width, height)
      # Flush the display first. Downscale on GPU; read back only the thumbnail.
      rl.rl_draw_render_batch_active()
      rl.begin_texture_mode(self._thumbnail)
      try:
        rl.clear_background(rl.BLACK)
        rl.draw_texture_pro(texture, rl.Rectangle(0, 0, texture.width, -texture.height),
                            rl.Rectangle(0, 0, width, height), rl.Vector2(0, 0), 0, rl.WHITE)
      finally:
        rl.end_texture_mode()
      image = rl.load_image_from_texture(self._thumbnail.texture)
      try:
        if image.width != width or image.height != height or image.data == rl.ffi.NULL:
          raise ValueError("thumbnail readback failed")
        rgba = bytes(rl.ffi.buffer(image.data, width * height * 4))
      finally:
        rl.unload_image(image)
      self._queue.put_nowait((width, height, rgba))
      self._capture_wall_ms = (time.monotonic() - start) * 1000
      self._capture_ms = (time.thread_time() - cpu_start) * 1000 + render_cpu_ms
    except (OSError, ValueError, RuntimeError, queue.Full) as error:
      self._error = str(error)
      self._last_capture = time.monotonic() + 5

  def _encode(self):
    try:
      _background_thread(19)
      from PIL import Image
      from openpilot.cereal import messaging
      sm = messaging.SubMaster(["deviceState"])
      self._worker = {"tid": threading.get_native_id(), "policy": os.sched_getscheduler(0),
                      "affinity": sorted(os.sched_getaffinity(0)),
                      "nice": os.getpriority(os.PRIO_PROCESS, threading.get_native_id())}
    except Exception as error:
      self._error = str(error)
      return
    while not self._stop.is_set():
      item = self._queue.get()
      if item is None:
        break
      width, height, rgba = item
      if not self._is_enabled(time.monotonic()) or not self._viewer_active():
        continue
      start = time.thread_time()
      try:
        image = Image.frombytes("RGBA", (width, height), rgba).transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=False)
        temporary = FRAME_PATH.with_suffix(".tmp")
        temporary.write_bytes(output.getvalue())
        os.replace(temporary, FRAME_PATH)
        self._frames += 1
        self._encode_ms = (time.thread_time() - start) * 1000
        sm.update(0)
        fresh = sm.seen["deviceState"] and time.monotonic() - sm.recv_time["deviceState"] < 3
        state = sm["deviceState"]
        cpu = sum(state.cpuUsagePercent) / max(1, len(state.cpuUsagePercent)) if fresh else 100
        temperature = state.maxTempC if fresh else 80
        self._interval = capture_interval(not self._params.get_bool("IsOffroad"), cpu, temperature,
                                          self._capture_ms + self._encode_ms)
        if time.monotonic() - self._last_status >= 1:
          status = {"frames": self._frames, "width": width, "height": height,
                    "capture_cpu_ms": self._capture_ms, "capture_wall_ms": self._capture_wall_ms,
                    "encode_cpu_ms": self._encode_ms, "fps_limit": round(1 / self._interval, 2),
                    "device_cpu_mean": cpu, "worker": self._worker, "error": self._error}
          temporary = STATUS_PATH.with_suffix(".tmp")
          temporary.write_text(json.dumps(status))
          os.replace(temporary, STATUS_PATH)
          self._last_status = time.monotonic()
      except (OSError, ValueError) as error:
        self._error = str(error)

  def _receive(self):
    last_control = 0.0
    try:
      _background_thread(5)
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        self._socket = sock
        sock.bind(CONTROL_ADDRESS)
        while not self._stop.is_set():
          # Sleep in recvfrom when idle. Only an active touch lease needs a timeout.
          sock.settimeout(max(0.01, CONTROL_TIMEOUT - (time.monotonic() - last_control)) if last_control else None)
          try:
            data, _ = sock.recvfrom(4096)
          except socket.timeout:
            self._mouse.cancel_remote_events()
            last_control = 0.0
            continue
          try:
            value = json.loads(data)
            if value.get("type") == "enabled" and type(value.get("enabled")) is bool:
              if self._params.get_bool("IsOffroad"):
                self._enabled = value["enabled"]
                if not self._enabled:
                  self._mouse.cancel_remote_events()
                  last_control = 0.0
              continue
            if value.get("type") == "cancel":
              self._mouse.cancel_remote_events()
              last_control = 0
              continue
            if not self._is_enabled(time.monotonic()):
              continue
            if value.get("type") == "heartbeat":
              last_control = time.monotonic()
              continue
            action, slot, x, y = validate_pointer(value)
            last_control = time.monotonic()
            self._mouse.inject_remote_event(x * self._width, y * self._height, slot, action)
          except (ValueError, TypeError, AttributeError):
            continue
    except OSError as error:
      if not self._stop.is_set():
        self._error = str(error)
