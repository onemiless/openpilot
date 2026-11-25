"""Bounded blindspot lighting, using card's existing CAN publisher."""
import threading

from opendbc.car.can_definitions import CanData

ADDRESS = 0x679
BUS = 1
FRESH_NS = 1_000_000_000
INTERVAL_NS = 100_000_000
BLINDSPOT_DURATION_NS = 15_000_000_000
BLINDSPOT_MAX_FRAMES = 150
MAX_BRIGHTNESS = 100
ENABLED_PARAM = "TeslaBlindspotAmbientEnabled"
BRIGHTNESS_PARAM = "TeslaBlindspotAmbientBrightness"
DAY_BRIGHTNESS_PARAM = "TeslaBlindspotAmbientDayBrightness"
# Captured HW4 frame is seven bytes: FL/RL doors + left IP, or FR/RR doors + right IP.
TARGETS = {"left": (0xA8, 0), "right": (0x50, 1), "both": (0xF8, 1)}


def _lighting_frame(template: bytes, side: str, color: tuple[int, int, int], brightness: int) -> bytes:
  if side not in TARGETS or len(template) != 7 or not 0 <= brightness <= 100:
    raise ValueError("灯光目标、数据长度或亮度无效")
  data = bytearray(template)
  data[0] = (data[0] & 1) | 2  # Preserve power override, ON, instant transition.
  data[1:4] = bytes(color)
  data[4] = (data[4] & 0x80) | min(brightness, MAX_BRIGHTNESS)
  data[5] = (data[5] & 0x06) | TARGETS[side][0]  # No audio visualizer; clear all other targets.
  data[6] = (data[6] & 0xFE) | TARGETS[side][1]
  return bytes(data)


def alert_frame(template: bytes, side: str, *, level: int, brightness: int) -> bytes:
  if level not in (1, 2) or not 0 <= brightness <= 100:
    raise ValueError("盲区灯光等级或亮度无效")
  return _lighting_frame(template, side, (255, 0, 0), brightness)


class AmbientLightingController:
  def __init__(self, *, blindspot_ambient_enabled: bool = False):
    self.lock = threading.Lock()
    self.blindspot_ambient_enabled = bool(blindspot_ambient_enabled)
    self.blindspot_brightness = 30
    self.blindspot_day_brightness = 100
    self.frames = {}
    self.blindspot_side = None
    self.blindspot_level = 0
    self.blindspot_night = True
    self.blindspot_started_ns = None
    self.blindspot_next_ns = 0
    self.blindspot_count = 0

  def update_blindspot(self, left_level: int, right_level: int, night: bool, now_ns: int) -> None:
    left_level = left_level if left_level in (1, 2) else 0
    right_level = right_level if right_level in (1, 2) else 0
    level = max(left_level, right_level)
    left = left_level > 0
    right = right_level > 0
    side = "both" if left and right else "left" if left else "right" if right else None
    with self.lock:
      if not self.blindspot_ambient_enabled or side is None:
        self.blindspot_side = None
        self.blindspot_level = 0
        self.blindspot_night = bool(night)
        self.blindspot_started_ns = None
        self.blindspot_count = 0
        return
      if (self.blindspot_side, self.blindspot_level) != (side, level):
        self.blindspot_started_ns = now_ns
        self.blindspot_next_ns = now_ns
        self.blindspot_count = 0
      self.blindspot_side = side
      self.blindspot_level = level
      self.blindspot_night = bool(night)

  def observe_frame(self, now_ns, address, data, source):
    with self.lock:
      self._observe_frame(now_ns, address, data, source)

  def _observe_frame(self, now_ns, address, data, source):
    if len(data) != 7:
      return
    if (address, source) == (ADDRESS, BUS):
      self.frames[address] = (bytes(data), now_ns)

  def service_params(self, params):
    enabled = params.get_bool(ENABLED_PARAM)
    brightness = max(0, min(MAX_BRIGHTNESS, params.get(BRIGHTNESS_PARAM, return_default=True)))
    day_brightness = max(0, min(MAX_BRIGHTNESS, params.get(DAY_BRIGHTNESS_PARAM, return_default=True)))
    with self.lock:
      self.blindspot_ambient_enabled = enabled
      self.blindspot_brightness = brightness
      self.blindspot_day_brightness = day_brightness

  def take_can_sends(self, now_ns):
    with self.lock:
      return self._take_can_sends(now_ns)

  def _take_can_sends(self, now_ns):
    if self.blindspot_side is not None:
      return self._take_blindspot_sends(now_ns)
    return []

  def _take_blindspot_sends(self, now_ns):
    if (not self.blindspot_ambient_enabled or self.blindspot_started_ns is None or now_ns - self.blindspot_started_ns >= BLINDSPOT_DURATION_NS or
        self.blindspot_count >= BLINDSPOT_MAX_FRAMES or now_ns < self.blindspot_next_ns):
      return []
    if ADDRESS not in self.frames or not 0 <= now_ns - self.frames[ADDRESS][1] <= FRESH_NS:
      return []
    brightness = self.blindspot_brightness if self.blindspot_night else self.blindspot_day_brightness
    data = alert_frame(self.frames[ADDRESS][0], self.blindspot_side, level=self.blindspot_level, brightness=brightness)
    self.blindspot_count += 1
    self.blindspot_next_ns = now_ns + INTERVAL_NS
    return [CanData(ADDRESS, data, BUS)]
