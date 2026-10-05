"""Passive Model 3/Y Vehicle CAN battery telemetry; never transmits.

Signal reference: joshwardell/model3dbc (MIT), Model3CAN.dbc, plus the
multiplexed 0x332/0x352 layout documented by tuncasoftbildik/tesla-can-mod.
Do not use flipper-tesla-fsd's SOCmin/0x312/0x33A shortcuts as UI telemetry.
"""
from dataclasses import dataclass, field

FIELDS = ('soc', 'voltage', 'current', 'power', 'temp_min', 'temp_max',
          'cell_min', 'cell_max', 'capacity', 'remaining', 'charged', 'discharged',
          'drive_power_low', 'support_power_low', 'contactor')
FRAME_LENGTHS = {0x132: 4, 0x292: 8, 0x332: 6, 0x352: 8, 0x3D2: 8, 0x212: 8}


@dataclass
class BmsState:
  values: dict = field(default_factory=dict)
  frames: dict = field(default_factory=dict)

  def _set(self, key, value, now, low, high):
    self.values[key] = (value if low <= value <= high else None, now)

  def update(self, address: int, data: bytes, bus: int, now: float):
    if bus != 1 or address not in FRAME_LENGTHS or len(data) < FRAME_LENGTHS[address] or len(data) > 8:
      return
    self.frames[address] = (data.hex(), now, self.frames.get(address, ('', 0, 0))[2] + 1)
    raw = int.from_bytes(data, 'little')
    if address == 0x132:
      voltage = int.from_bytes(data[:2], 'little') * .01
      current = -int.from_bytes(data[2:4], 'little', signed=True) * .1  # positive = discharge
      self._set('voltage', voltage, now, 50, 600)
      self._set('current', current, now, -2000, 2000)
      self._set('power', voltage * current / 1000, now, -1000, 1000)
      if self.values['voltage'][0] is None or self.values['current'][0] is None:
        self.values['power'] = (None, now)
    elif address == 0x292:
      self._set('soc', ((raw >> 10) & 0x3FF) * .1, now, 0, 100)
    elif address == 0x332:
      if raw & 3 == 0:
        lo, hi = data[3] * .5 - 40, data[2] * .5 - 40
        if 255 in (data[2], data[3]):
          lo, hi = -999, -999
        self._set('temp_min', lo if lo <= hi else -999, now, -40, 100)
        self._set('temp_max', hi if lo <= hi else -999, now, -40, 100)
      elif raw & 3 == 1:
        lo, hi = ((raw >> 16) & 0xFFF) * .002, ((raw >> 2) & 0xFFF) * .002
        self._set('cell_min', lo if lo <= hi else -999, now, 1, 5)
        self._set('cell_max', hi if lo <= hi else -999, now, 1, 5)
    elif address == 0x352 and data[0] == 0:
      self._set('capacity', int.from_bytes(data[2:4], 'little') * .02, now, 10, 150)
      self._set('remaining', int.from_bytes(data[4:6], 'little') * .02, now, 0, 150)
    elif address == 0x3D2:
      self._set('discharged', (raw & 0xFFFFFFFF) * .001, now, 0, 1e6)
      self._set('charged', (raw >> 32) * .001, now, 0, 1e6)
    elif address == 0x212:
      self._set('drive_power_low', (raw >> 1) & 1, now, 0, 1)
      self._set('support_power_low', (raw >> 2) & 1, now, 0, 1)
      self._set('contactor', (raw >> 8) & 7, now, 0, 7)

  def snapshot(self, now: float) -> dict:
    result = {}
    for key in FIELDS:
      value, timestamp = self.values.get(key, (None, float('-inf')))
      ttl = 10 if key in ('capacity', 'remaining', 'charged', 'discharged') else 3
      result[key] = value if 0 <= now - timestamp <= ttl else None
    return result
