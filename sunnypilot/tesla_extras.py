#!/usr/bin/env python3
"""
Tesla extras — BMS battery dashboard + turn signal toggle.
"""

import json
import time
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.pandad.pandad_api_impl import can_list_to_can_capnp
from opendbc.car.can_definitions import CanData

import cereal.messaging as messaging

# CAN IDs
CAN_ID_BMS_HV = 0x132      # BMS_hvBusStatus (pack voltage, current)
CAN_ID_BMS_SOC = 0x292      # BMS_socStatus (state of charge)
CAN_ID_BMS_THERMAL = 0x312  # BMS_thermalStatus (battery temps)
CAN_ID_LEFT_STALK = 0x249   # SCCM_leftStalk (turn signal)

PARTY_CAN_BUS = 0
TURN_INTERVAL = 60.0
BMS_PUBLISH_INTERVAL = 1.0


class TeslaExtras:
  def __init__(self):
    self.params = Params()
    self.sub_sock = messaging.sub_sock("can", timeout=100)
    self.pm = messaging.PubMaster(["sendcan"])

    # BMS data
    self.pack_voltage_v = 0.0
    self.pack_current_a = 0.0
    self.soc_percent = 0.0
    self.batt_temp_min_c = 0
    self.batt_temp_max_c = 0
    self.bms_seen = False

    # Cell voltage tracking (for delta)
    self.cell_volt_min = 0.0
    self.cell_volt_max = 0.0

    # Turn signal
    self.turn_counter = 0
    self.last_turn_ts = 0.0
    self.turn_left = True  # alternate left/right

    # Timers
    self._last_bms_publish = 0.0
    self._last_param_refresh = 0.0

    self._refresh_params()
    cloudlog.info("TeslaExtras: initialized")

  def _refresh_params(self):
    self._bms_enabled = self.params.get_bool("TeslaBMSDashboard")
    self._turn_enabled = self.params.get_bool("TeslaTurnSignal")

  # ---- BMS Parsers ----

  def _parse_bms_hv(self, dat):
    if len(dat) < 4:
      return
    raw_v = (dat[1] << 8) | dat[0]
    raw_i = (((dat[3] << 8) | dat[2]) ^ 0x8000) - 0x8000  # signed int16
    self.pack_voltage_v = raw_v * 0.01
    self.pack_current_a = raw_i * 0.1
    self.bms_seen = True

  def _parse_bms_soc(self, dat):
    if len(dat) < 2:
      return
    raw = ((dat[1] & 0x03) << 8) | dat[0]
    self.soc_percent = raw * 0.1
    self.bms_seen = True

  def _parse_bms_thermal(self, dat):
    if len(dat) < 6:
      return
    self.batt_temp_min_c = dat[4] - 40
    self.batt_temp_max_c = dat[5] - 40
    self.cell_volt_min = ((dat[0] << 8) | dat[1]) * 0.01  # approximate
    self.bms_seen = True

  def _publish_bms_status(self):
    now = time.monotonic()
    if now - self._last_bms_publish < BMS_PUBLISH_INTERVAL:
      return
    self._last_bms_publish = now

    temp_delta = self.batt_temp_max_c - self.batt_temp_min_c

    status = {
      "voltage": round(self.pack_voltage_v, 1),
      "current": round(self.pack_current_a, 1),
      "soc": round(self.soc_percent, 1),
      "temp_min": self.batt_temp_min_c,
      "temp_max": self.batt_temp_max_c,
      "temp_delta": temp_delta,
      "seen": self.bms_seen,
    }
    self.params.put_nonblocking("TeslaBMSStatus", json.dumps(status))

  # ---- Turn Signal ----

  def _build_turn_signal(self, left: bool, counter: int) -> CanData:
    """Build SCCM_leftStalk frame for turn signal."""
    data = bytearray(3)
    direction = 3 if left else 1  # 3=DOWN_1(left), 1=UP_1(right)
    data[1] = counter & 0x0F
    data[2] = direction & 0x07
    # CRC = (0x49 + 0x02 + data[1] + data[2]) & 0xFF
    data[0] = ((CAN_ID_LEFT_STALK & 0xFF) + ((CAN_ID_LEFT_STALK >> 8) & 0xFF)
               + data[1] + data[2]) & 0xFF
    return CanData(CAN_ID_LEFT_STALK, bytes(data), PARTY_CAN_BUS)

  def _check_turn_signal(self) -> CanData | None:
    if not self._turn_enabled:
      return None

    now = time.monotonic()
    if now - self.last_turn_ts < TURN_INTERVAL:
      return None

    self.last_turn_ts = now
    self.turn_counter = (self.turn_counter + 1) & 0x0F
    self.turn_left = not self.turn_left

    return self._build_turn_signal(self.turn_left, self.turn_counter)

  # ---- Main ----

  def process(self):
    send_msgs = []

    now = time.monotonic()
    if now - self._last_param_refresh >= 5.0:
      self._refresh_params()
      self._last_param_refresh = now

    if not self._bms_enabled and not self._turn_enabled:
      messaging.drain_sock(self.sub_sock)
      return send_msgs

    for event in messaging.drain_sock(self.sub_sock):
      for msg in event.can:
        if msg.src != PARTY_CAN_BUS:
          continue

        addr, dat = msg.address, msg.dat

        if self._bms_enabled:
          if addr == CAN_ID_BMS_HV:
            self._parse_bms_hv(dat)
          elif addr == CAN_ID_BMS_SOC:
            self._parse_bms_soc(dat)
          elif addr == CAN_ID_BMS_THERMAL:
            self._parse_bms_thermal(dat)

    # Publish BMS to params
    if self._bms_enabled:
      self._publish_bms_status()

    # Turn signal
    ts = self._check_turn_signal()
    if ts is not None:
      send_msgs.append(ts)

    return send_msgs

  def send(self, msgs):
    if msgs:
      self.pm.send('sendcan', can_list_to_can_capnp(msgs, msgtype='sendcan', valid=True))


def main():
  config_realtime_process([0, 1, 2, 3], 5)

  mod = TeslaExtras()
  rk = Ratekeeper(20, print_delay_threshold=None)

  cloudlog.info("TeslaExtras: starting main loop")
  while True:
    msgs = mod.process()
    if msgs:
      mod.send(msgs)
    rk.keep_time()


if __name__ == "__main__":
  main()
