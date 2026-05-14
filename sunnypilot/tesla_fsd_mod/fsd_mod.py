#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Tesla FSD Mod — CAN frame manipulation module.
Port of flipper-tesla-fsd logic to sunnypilot/openpilot.
"""

import time
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.selfdrive.pandad.pandad_api_impl import can_list_to_can_capnp, can_capnp_to_list
from openpilot.common.swaglog import cloudlog

import cereal.messaging as messaging

# CAN IDs (from flipper-tesla-fsd)
CAN_ID_AP_CONTROL = 0x3FD      # UI_autopilotControl (FSD unlock target)
CAN_ID_EPAS_STATUS = 0x370     # EPAS3S_sysStatus (nag killer target)
CAN_ID_ISA_SPEED = 0x399       # ISA speed chime suppression
CAN_ID_TRIP_PLANNING = 0x082   # UI_tripPlanning (precondition trigger)

PARTY_CAN_BUS = 0


class TeslaFSDMod:
  def __init__(self):
    self.params = Params()
    self.sub_sock = messaging.sub_sock("can")
    self.pm = messaging.PubMaster(["sendcan"])

    # track last 0x370 frame for nag killer
    self.last_370_frame = None
    self.last_370_ts = 0.0

    # precondition timer
    self.last_precondition_ts = 0.0
    self.precondition_interval = 60.0  # send every 60s

    # OTA guard
    self.ota_in_progress = False

    # stats
    self.fsd_frames_modified = 0
    self.nag_echo_count = 0
    self.chime_suppressed = 0

    cloudlog.info("TeslaFSDMod: initialized")

  @property
  def fsd_enabled(self) -> bool:
    return self.params.get_bool("TeslaFSDUnlock")

  @property
  def nag_killer_enabled(self) -> bool:
    return self.params.get_bool("TeslaNagKiller")

  @property
  def chime_suppress_enabled(self) -> bool:
    return self.params.get_bool("TeslaISAChimeSuppress")

  @property
  def precondition_enabled(self) -> bool:
    return self.params.get_bool("TeslaPrecondition")

  @property
  def any_feature_enabled(self) -> bool:
    return self.fsd_enabled or self.nag_killer_enabled or \
           self.chime_suppress_enabled or self.precondition_enabled

  def _check_ota_guard(self, can_list):
    """Monitor 0x318 for GTW_updateInProgress flag."""
    for addr, dat, bus in can_list:
      if addr == 0x318 and bus == PARTY_CAN_BUS and len(dat) >= 7:
        in_progress = dat[6] & 0x03
        if in_progress != 0 and not self.ota_in_progress:
          cloudlog.info("TeslaFSDMod: OTA in progress detected, pausing TX")
        self.ota_in_progress = (in_progress != 0)

  # ---- FSD Unlock (0x3FD) ----

  def _process_fsd_unlock(self, addr, dat, bus):
    """Modify UI_autopilotControl to enable FSD bits."""
    if len(dat) < 8:
      return None

    mux = dat[0] & 0x07
    data = bytearray(dat)
    modified = False

    # isFSDSelectedInUI: byte4 bit6
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
      # nag suppression: clear bit19
      byte_idx_19 = 19 // 8
      bit_idx_19 = 19 % 8
      data[byte_idx_19] &= ~(1 << bit_idx_19)

      # HW4: set bit47
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

  def _process_nag_killer(self, addr, dat):
    """Echo EPAS3S_sysStatus with handsOnLevel=1 and counter+1 when hands-off."""
    if len(dat) < 8:
      return None

    # handsOnLevel: byte4 bits[7:6]
    hands_on = (dat[4] >> 6) & 0x03
    if hands_on != 0:
      # hands are on, store reference and bail
      self.last_370_frame = bytes(dat)
      self.last_370_ts = time.monotonic()
      return None

    # hands are off, build echo
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

    self.last_370_frame = bytes(dat)
    self.last_370_ts = time.monotonic()
    self.nag_echo_count += 1
    return bytes(data)

  # ---- ISA Speed Chime Suppression (0x399) ----

  def _process_isa_chime(self, addr, dat):
    """Suppress ISA speed warning chime (HW4)."""
    if len(dat) < 8:
      return None

    data = bytearray(dat)
    # set bit5 of byte1
    data[1] |= 0x20

    # recalculate checksum (byte7 = sum of CAN ID + bytes 0-6)
    chksum = ((CAN_ID_ISA_SPEED & 0xFF) + ((CAN_ID_ISA_SPEED >> 8) & 0xFF)) & 0xFF
    for i in range(7):
      chksum = (chksum + data[i]) & 0xFF
    data[7] = chksum

    self.chime_suppressed += 1
    return bytes(data)

  # ---- Battery Preconditioning (0x082) ----

  def _check_precondition(self):
    """Periodically send precondition trigger."""
    now = time.monotonic()
    if now - self.last_precondition_ts < self.precondition_interval:
      return None

    self.last_precondition_ts = now
    # byte0 = 0x05: tripPlanningActive + requestActiveBatteryHeating
    data = bytes([0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    cloudlog.info("TeslaFSDMod: sending precondition trigger")
    return data

  # ---- Main processing ----

  def process(self):
    """Process incoming CAN messages and return list of frames to send."""
    send_msgs = []

    if not self.any_feature_enabled:
      messaging.drain_sock_raw(self.sub_sock)
      return send_msgs

    # Receive CAN messages
    can_events = messaging.drain_sock_raw(self.sub_sock)
    for event_bytes in can_events:
      can_list = can_capnp_to_list([event_bytes])

      self._check_ota_guard(can_list)

      # Don't transmit during OTA
      if self.ota_in_progress:
        continue

      for addr, dat, bus in can_list:
        if bus != PARTY_CAN_BUS:
          continue

        # FSD Unlock
        if self.fsd_enabled and addr == CAN_ID_AP_CONTROL:
          modified = self._process_fsd_unlock(addr, dat, bus)
          if modified is not None:
            send_msgs.append((CAN_ID_AP_CONTROL, modified, PARTY_CAN_BUS))

        # Nag Killer
        elif self.nag_killer_enabled and addr == CAN_ID_EPAS_STATUS:
          modified = self._process_nag_killer(addr, dat)
          if modified is not None:
            send_msgs.append((CAN_ID_EPAS_STATUS, modified, PARTY_CAN_BUS))

        # ISA Chime Suppression
        elif self.chime_suppress_enabled and addr == CAN_ID_ISA_SPEED:
          modified = self._process_isa_chime(addr, dat)
          if modified is not None:
            send_msgs.append((CAN_ID_ISA_SPEED, modified, PARTY_CAN_BUS))

    # Battery Preconditioning (periodic)
    if self.precondition_enabled:
      modified = self._check_precondition()
      if modified is not None:
        send_msgs.append((CAN_ID_TRIP_PLANNING, modified, PARTY_CAN_BUS))

    return send_msgs

  def send(self, send_msgs):
    """Publish CAN frames to sendcan."""
    if send_msgs:
      msg_bytes = can_list_to_can_capnp(send_msgs, msgtype='sendcan', valid=True)
      self.pm.send('sendcan', msg_bytes)


def main():
  config_realtime_process([0, 1, 2, 3], 5)

  mod = TeslaFSDMod()
  rk = Ratekeeper(20, print_delay_threshold=None)  # 20Hz

  cloudlog.info("TeslaFSDMod: starting main loop")
  while True:
    send_msgs = mod.process()
    mod.send(send_msgs)
    rk.keep_time()


if __name__ == "__main__":
  main()
