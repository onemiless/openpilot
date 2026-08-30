#!/usr/bin/env python3
from __future__ import annotations

import math
import threading
import time

from openpilot.cereal import log, messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.navassist.protocol import NavAssistStore
from openpilot.sunnypilot.navassist.publisher import build_nav_assist_message
from openpilot.sunnypilot.navassist.server import NavAssistHTTPServer
from openpilot.sunnypilot.navassist.geofence import TrackGeofence


LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 7766
PUBLISH_HZ = 20
LOCALIZATION_MAX_AGE_NS = 500_000_000
LOCAL_POSITION_MAX_STD_M = 10.0
TRACK_GEOFENCE_BASE_MARGIN_M = 20.0
REPLAY_CHECKPOINT_PATH = "/dev/shm/navassist_replay_state.json"


def local_position_std_m(location) -> float:
  position_ecef = location.positionECEF
  if not position_ecef.valid or len(position_ecef.std) < 3:
    return math.inf
  values = tuple(float(value) for value in position_ecef.std[:3])
  if not all(math.isfinite(value) and value >= 0.0 for value in values):
    return math.inf
  return math.sqrt(sum(value * value for value in values))


def local_localization_valid(sm, now_ns: int) -> bool:
  service = "liveLocationKalman"
  location = sm[service]
  age_ns = now_ns - sm.logMonoTime[service]
  return bool(
    sm.seen[service] and sm.alive[service] and sm.valid[service]
    and 0 <= age_ns <= LOCALIZATION_MAX_AGE_NS
    and location.status == log.LiveLocationKalman.Status.valid and location.positionGeodetic.valid
    and len(location.positionGeodetic.value) >= 2
    and location.gpsOK and location.inputsOK and location.sensorsOK and location.deviceStable
    and not location.excessiveResets and local_position_std_m(location) <= LOCAL_POSITION_MAX_STD_M
  )


def main() -> None:
  params = Params()
  if not params.get_bool("NavAssistTrackMode"):
    raise RuntimeError("NavAssistTrackMode must be armed offroad for this ignition cycle")
  token = params.get("NavAssistToken")
  if not isinstance(token, str) or len(token.encode("utf-8")) < 16:
    raise RuntimeError("NavAssistToken must contain at least 16 UTF-8 bytes")
  geofence = TrackGeofence.parse(params.get("NavAssistTrackGeofence"))

  store = NavAssistStore(token, checkpoint_path=REPLAY_CHECKPOINT_PATH)
  server = NavAssistHTTPServer((LISTEN_HOST, LISTEN_PORT), store)
  server_thread = threading.Thread(target=server.serve_forever, name="navassist-http", daemon=True)
  server_thread.start()
  cloudlog.warning("navassistd armed for closed-course input on port %d", LISTEN_PORT)

  pm = messaging.PubMaster(["navAssistStateSP"])
  sm = messaging.SubMaster(["liveLocationKalman"])
  ratekeeper = Ratekeeper(PUBLISH_HZ)
  try:
    while params.get_bool("NavAssistTrackMode"):
      sm.update(0)
      now_ns = time.monotonic_ns()
      location = sm["liveLocationKalman"]
      localization_valid = local_localization_valid(sm, now_ns)
      boundary_margin_m = TRACK_GEOFENCE_BASE_MARGIN_M + local_position_std_m(location)
      track_geofence_valid = bool(
        localization_valid and geofence.contains_with_margin(
          location.positionGeodetic.value[0], location.positionGeodetic.value[1], boundary_margin_m,
        )
      )
      message = build_nav_assist_message(
        store.current(), now_ns, track_geofence_valid=track_geofence_valid,
        local_localization_valid=localization_valid,
      )
      pm.send("navAssistStateSP", message)
      ratekeeper.keep_time()
  finally:
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)


if __name__ == "__main__":
  main()
