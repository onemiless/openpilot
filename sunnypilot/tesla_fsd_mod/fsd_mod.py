#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Tesla FSD Mod — CAN frame manipulation module.
Port of flipper-tesla-fsd logic to sunnypilot/openpilot.
"""

import json
import time
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.pandad.pandad_api_impl import can_list_to_can_capnp
from opendbc.car.can_definitions import CanData

import cereal.messaging as messaging

# CAN IDs (from flipper-tesla-fsd / tesla-fsd-comma4)
CAN_ID_AP_CONTROL = 0x3FD      # UI_autopilotControl (FSD unlock target)
CAN_ID_FOLLOW_DIST = 0x3F8     # follow distance / speed profile source
CAN_ID_EPAS_STATUS = 0x370     # EPAS3S_sysStatus (nag killer target)
CAN_ID_ISA_SPEED = 0x399       # ISA speed chime suppression
CAN_ID_GTW_CAR_STATE = 0x318   # GTW_carState (OTA guard)

# Speed profile mapping from follow-distance (0x3F8 byte5 bits[7:5]) → profile index
# Tesla fd values: 1=closest, 2=closer, 3=medium, 4=further, 5=furthest
# Profile indices: 0=Chill, 1=Normal, 2=Sport, 3/4=Reserved
FOLLOW_DIST_TO_PROFILE = {1: 3, 2: 2, 3: 1, 4: 0, 5: 4}

# Tesla Party CAN buses: bus 0 = OBD-II, bus 2 = autopilot_party (harness)
PARTY_BUSES = {0, 2}


class TeslaFSDMod:
  def __init__(self):
    self.params = Params()
    self.sub_sock = messaging.sub_sock("can", timeout=100)
    self.pm = messaging.PubMaster(["sendcan"])

    self.ota_in_progress = False

    # speed profile from follow distance (0x3F8)
    self._speed_profile = 0  # 0=Chill, 1=Normal, 2=Sport, 3/4=Reserved

    # stats
    self.fsd_frames_modified = 0
    self.nag_echo_count = 0
    self.chime_suppressed = 0

    # status publishing
    self._last_status_update = 0.0
    self._status_interval = 2.0

    # param refresh
    self._last_param_refresh = 0.0
    self._param_refresh_interval = 5.0

    self._fsd_enabled = False
    self._nag_killer_enabled = False
    self._chime_suppress_enabled = False
    self._refresh_params()

    cloudlog.info("TeslaFSDMod: initialized")

  def _refresh_params(self):
    self._fsd_enabled = self.params.get_bool("TeslaFSDUnlock")
    self._nag_killer_enabled = self.params.get_bool("TeslaNagKiller")
    self._chime_suppress_enabled = self.params.get_bool("TeslaISAChimeSuppress")

  @property
  def any_feature_enabled(self) -> bool:
    return self._fsd_enabled or self._nag_killer_enabled or self._chime_suppress_enabled

  def _publish_status(self):
    now = time.monotonic()
    if now - self._last_status_update < self._status_interval:
      return
    self._last_status_update = now

    profile_names = {0: "Chill", 1: "Normal", 2: "Sport", 3: "Reserved", 4: "Reserved"}
    status = {
      "fsd_frames": self.fsd_frames_modified,
      "nag_echoes": self.nag_echo_count,
      "chime_suppress": self.chime_suppressed > 0,
      "speed_profile": profile_names.get(self._speed_profile, "Unknown"),
    }
    self.params.put_nonblocking("TeslaFSDModStatus", json.dumps(status))

  def _process_follow_distance(self, dat):
    """Read follow distance from 0x3F8 byte5 bits[7:5] → map to speed profile."""
    if len(dat) < 6:
      return
    fd = (dat[5] & 0xE0) >> 5  # bits [7:5]
    self._speed_profile = FOLLOW_DIST_TO_PROFILE.get(fd, 1)  # default Normal

  def _check_ota_guard(self, addr, dat):
    if addr == CAN_ID_GTW_CAR_STATE and len(dat) >= 7:
      in_progress = dat[6] & 0x03
      if in_progress != 0 and not self.ota_in_progress:
        cloudlog.info("TeslaFSDMod: OTA in progress, pausing TX")
      self.ota_in_progress = (in_progress != 0)

  def _process_fsd_unlock(self, dat):
    if len(dat) < 8:
      return None

    mux = dat[0] & 0x07
    data = bytearray(dat)
    modified = False

    fsd_ui = (data[4] >> 6) & 0x01

    if mux == 0 and fsd_ui:
      # HW4: set bit46 and bit60
      data[5] |= (1 << 6)   # bit46
      data[7] |= (1 << 4)   # bit60
      modified = True

    if mux == 1 and fsd_ui:
      data[2] &= ~(1 << 3)  # clear bit19 (nag suppression)
      data[5] |= (1 << 7)   # set bit47 (HW4)
      modified = True

    if mux == 2 and fsd_ui:
      profile = self._speed_profile & 0x07
      data[7] &= ~(0x07 << 4)
      data[7] |= (profile << 4)
      modified = True

    if modified:
      self.fsd_frames_modified += 1
      return bytes(data)
    return None

  def _process_nag_killer(self, dat):
    if len(dat) < 8:
      return None

    hands_on = (dat[4] >> 6) & 0x03
    if hands_on != 0:
      return None

    data = bytearray(dat)
    data[4] = (data[4] & 0x3F) | 0x40  # handsOnLevel = 1

    cnt = data[6] & 0x0F
    cnt = (cnt + 1) & 0x0F
    data[6] = (data[6] & 0xF0) | cnt

    chksum = ((CAN_ID_EPAS_STATUS & 0xFF) + ((CAN_ID_EPAS_STATUS >> 8) & 0xFF)) & 0xFF
    for i in range(7):
      chksum = (chksum + data[i]) & 0xFF
    data[7] = chksum

    self.nag_echo_count += 1
    return bytes(data)

  def _process_isa_chime(self, dat):
    if len(dat) < 8:
      return None

    data = bytearray(dat)
    data[1] |= 0x20

    chksum = ((CAN_ID_ISA_SPEED & 0xFF) + ((CAN_ID_ISA_SPEED >> 8) & 0xFF)) & 0xFF
    for i in range(7):
      chksum = (chksum + data[i]) & 0xFF
    data[7] = chksum

    self.chime_suppressed += 1
    return bytes(data)

  def process(self):
    send_msgs = []

    now = time.monotonic()
    if now - self._last_param_refresh >= self._param_refresh_interval:
      self._refresh_params()
      self._last_param_refresh = now

    if not self.any_feature_enabled:
      messaging.drain_sock(self.sub_sock)
      return send_msgs

    for event in messaging.drain_sock(self.sub_sock):
      for msg in event.can:
        addr = msg.address
        dat = msg.dat
        bus = msg.src

        if bus not in PARTY_BUSES:
          continue

        self._check_ota_guard(addr, dat)

        # Always track follow distance — needed for FSD speed profile mapping
        if addr == CAN_ID_FOLLOW_DIST:
          self._process_follow_distance(dat)
          continue

        if self.ota_in_progress:
          continue

        if self._fsd_enabled and addr == CAN_ID_AP_CONTROL:
          modified = self._process_fsd_unlock(dat)
          if modified is not None:
            send_msgs.append(CanData(CAN_ID_AP_CONTROL, modified, 0))

        elif self._nag_killer_enabled and addr == CAN_ID_EPAS_STATUS:
          modified = self._process_nag_killer(dat)
          if modified is not None:
            send_msgs.append(CanData(CAN_ID_EPAS_STATUS, modified, 0))

        elif self._chime_suppress_enabled and addr == CAN_ID_ISA_SPEED:
          modified = self._process_isa_chime(dat)
          if modified is not None:
            send_msgs.append(CanData(CAN_ID_ISA_SPEED, modified, 0))

    return send_msgs

  def send(self, send_msgs):
    if send_msgs:
      msg_bytes = can_list_to_can_capnp(send_msgs, msgtype='sendcan', valid=True)
      self.pm.send('sendcan', msg_bytes)


def main():
  config_realtime_process([0, 1, 2, 3], 5)

  mod = TeslaFSDMod()
  rk = Ratekeeper(20, print_delay_threshold=None)

  cloudlog.info("TeslaFSDMod: starting main loop")
  while True:
    send_msgs = mod.process()
    if send_msgs:
      mod.send(send_msgs)
    mod._publish_status()
    rk.keep_time()


if __name__ == "__main__":
  main()
