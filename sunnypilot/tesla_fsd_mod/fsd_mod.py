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

# CAN IDs (from flipper-tesla-fsd)
CAN_ID_AP_CONTROL = 0x3FD      # UI_autopilotControl (FSD unlock target)
CAN_ID_EPAS_STATUS = 0x370     # EPAS3S_sysStatus (nag killer target)
CAN_ID_ISA_SPEED = 0x399       # ISA speed chime suppression
CAN_ID_TRIP_PLANNING = 0x082   # UI_tripPlanning (precondition trigger)
CAN_ID_GTW_CAR_STATE = 0x318   # GTW_carState (OTA guard)

PARTY_CAN_BUS = 0


class TeslaFSDMod:
  def __init__(self):
    self.params = Params()
    self.sub_sock = messaging.sub_sock("can", timeout=100)
    self.pm = messaging.PubMaster(["sendcan"])

    # precondition timer
    self.last_precondition_ts = 0.0
    self.precondition_interval = 60.0

    # OTA guard
    self.ota_in_progress = False

    # stats
    self.fsd_frames_modified = 0
    self.nag_echo_count = 0
    self.chime_suppressed = 0
    self.precondition_sent = 0

    # status publishing
    self._last_status_update = 0.0
    self._status_interval = 2.0

    # param refresh
    self._last_param_refresh = 0.0
    self._param_refresh_interval = 5.0

    # cached feature flags (refreshed periodically)
    self._fsd_enabled = False
    self._nag_killer_enabled = False
    self._chime_suppress_enabled = False
    self._precondition_enabled = False
    self._refresh_params()

    cloudlog.info("TeslaFSDMod: initialized")

  def _refresh_params(self):
    self._fsd_enabled = self.params.get_bool("TeslaFSDUnlock")
    self._nag_killer_enabled = self.params.get_bool("TeslaNagKiller")
    self._chime_suppress_enabled = self.params.get_bool("TeslaISAChimeSuppress")
    self._precondition_enabled = self.params.get_bool("TeslaPrecondition")

  @property
  def any_feature_enabled(self) -> bool:
    return self._fsd_enabled or self._nag_killer_enabled or \
           self._chime_suppress_enabled or self._precondition_enabled

  def _publish_status(self):
    now = time.monotonic()
    if now - self._last_status_update < self._status_interval:
      return
    self._last_status_update = now

    status = {
      "fsd_frames": self.fsd_frames_modified,
      "nag_echoes": self.nag_echo_count,
      "chime_suppress": self.chime_suppressed > 0,
      "precondition_sent": self.precondition_sent,
    }
    self.params.put_nonblocking("TeslaFSDModStatus", json.dumps(status))

  # ---- OTA Guard ----

  def _check_ota_guard(self, addr, dat):
    if addr == CAN_ID_GTW_CAR_STATE and len(dat) >= 7:
      in_progress = dat[6] & 0x03
      if in_progress != 0 and not self.ota_in_progress:
        cloudlog.info("TeslaFSDMod: OTA in progress, pausing TX")
      self.ota_in_progress = (in_progress != 0)

  # ---- FSD Unlock (0x3FD) ----

  def _process_fsd_unlock(self, dat):
    if len(dat) < 8:
      return None

    mux = dat[0] & 0x07
    data = bytearray(dat)
    modified = False

    fsd_ui = (data[4] >> 6) & 0x01

    if mux == 0 and fsd_ui:
      # HW4: set bit46 and bit60
      byte_idx_46 = 46 // 8
      bit_idx_46 = 46 % 8
      data[byte_idx_46] |= (1 << bit_idx_46)

      byte_idx_60 = 60 // 8
      bit_idx_60 = 60 % 8
      data[byte_idx_60] |= (1 << bit_idx_60)
      modified = True

    if mux == 1:
      # nag suppression: clear bit19, set bit47
      byte_idx_19 = 19 // 8
      bit_idx_19 = 19 % 8
      data[byte_idx_19] &= ~(1 << bit_idx_19)

      byte_idx_47 = 47 // 8
      bit_idx_47 = 47 % 8
      data[byte_idx_47] |= (1 << bit_idx_47)
      modified = True

    if mux == 2 and fsd_ui:
      # speed profile in byte7 upper nibble
      data[7] &= ~(0x07 << 4)
      data[7] |= (4 << 4)  # profile 4/4
      modified = True

    if modified:
      self.fsd_frames_modified += 1
      return bytes(data)
    return None

  # ---- Nag Killer (0x370) ----

  def _process_nag_killer(self, dat):
    if len(dat) < 8:
      return None

    # handsOnLevel: byte4 bits[7:6]
    hands_on = (dat[4] >> 6) & 0x03
    if hands_on != 0:
      return None

    # hands are off, build echo with handsOnLevel=1 and counter+1
    data = bytearray(dat)

    # set handsOnLevel = 1 (bit6 of byte4)
    data[4] = (data[4] & 0x3F) | 0x40

    # counter + 1 (lower nibble of byte6)
    cnt = data[6] & 0x0F
    cnt = (cnt + 1) & 0x0F
    data[6] = (data[6] & 0xF0) | cnt

    # checksum: sum of bytes 0-6 + CAN ID bytes
    chksum = ((CAN_ID_EPAS_STATUS & 0xFF) + ((CAN_ID_EPAS_STATUS >> 8) & 0xFF)) & 0xFF
    for i in range(7):
      chksum = (chksum + data[i]) & 0xFF
    data[7] = chksum

    self.nag_echo_count += 1
    return bytes(data)

  # ---- ISA Speed Chime Suppression (0x399) ----

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

  # ---- Battery Preconditioning (0x082) ----

  def _check_precondition(self):
    now = time.monotonic()
    if now - self.last_precondition_ts < self.precondition_interval:
      return None

    self.last_precondition_ts = now
    self.precondition_sent += 1
    return bytes([0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

  # ---- Main processing ----

  def process(self):
    send_msgs = []

    # Refresh params periodically
    now = time.monotonic()
    if now - self._last_param_refresh >= self._param_refresh_interval:
      self._refresh_params()
      self._last_param_refresh = now

    if not self.any_feature_enabled:
      # Drain socket to avoid backlog
      messaging.drain_sock(self.sub_sock)
      return send_msgs

    # Receive CAN messages via drain_sock (returns list of capnp event readers)
    for event in messaging.drain_sock(self.sub_sock):
      for msg in event.can:
        addr = msg.address
        dat = msg.dat
        bus = msg.src

        if bus != PARTY_CAN_BUS:
          continue

        self._check_ota_guard(addr, dat)

        if self.ota_in_progress:
          continue

        # FSD Unlock
        if self._fsd_enabled and addr == CAN_ID_AP_CONTROL:
          modified = self._process_fsd_unlock(dat)
          if modified is not None:
            send_msgs.append(CanData(CAN_ID_AP_CONTROL, modified, PARTY_CAN_BUS))

        # Nag Killer
        elif self._nag_killer_enabled and addr == CAN_ID_EPAS_STATUS:
          modified = self._process_nag_killer(dat)
          if modified is not None:
            send_msgs.append(CanData(CAN_ID_EPAS_STATUS, modified, PARTY_CAN_BUS))

        # ISA Chime Suppression
        elif self._chime_suppress_enabled and addr == CAN_ID_ISA_SPEED:
          modified = self._process_isa_chime(dat)
          if modified is not None:
            send_msgs.append(CanData(CAN_ID_ISA_SPEED, modified, PARTY_CAN_BUS))

    # Battery Preconditioning (periodic)
    if self._precondition_enabled:
      modified = self._check_precondition()
      if modified is not None:
        send_msgs.append(CanData(CAN_ID_TRIP_PLANNING, modified, PARTY_CAN_BUS))

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
