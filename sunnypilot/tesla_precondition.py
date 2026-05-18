#!/usr/bin/env python3
"""
Battery preconditioning — periodically sends 0x082 to trigger BMS preheat.
Runs independently of other FSD mod features.
"""

import time
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.pandad.pandad_api_impl import can_list_to_can_capnp
from opendbc.car.can_definitions import CanData

import cereal.messaging as messaging

CAN_ID_TRIP_PLANNING = 0x082
# Bus 0 = OBD-II (matches TX array in safety model)
PARTY_CAN_BUS = 0
# flipper-tesla-fsd sends every 500ms to keep BMS heater continuously active
INTERVAL = 0.5


def main():
  config_realtime_process([0, 1, 2, 3], 5)

  params = Params()
  pm = messaging.PubMaster(["sendcan"])
  rk = Ratekeeper(10, print_delay_threshold=None)  # 10Hz to support 500ms precondition interval

  last_send = 0.0

  cloudlog.info("TeslaPrecondition: started")

  while True:
    if not params.get_bool("TeslaPrecondition"):
      rk.keep_time()
      continue

    now = time.monotonic()
    if now - last_send >= INTERVAL:
      data = bytes([0x05, 0, 0, 0, 0, 0, 0, 0])
      msg_bytes = can_list_to_can_capnp(
        [CanData(CAN_ID_TRIP_PLANNING, data, PARTY_CAN_BUS)],
        msgtype='sendcan', valid=True,
      )
      pm.send('sendcan', msg_bytes)
      last_send = now

    rk.keep_time()


if __name__ == "__main__":
  main()
