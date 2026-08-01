#!/usr/bin/env python3
import argparse
import sys
import time
import uuid

from openpilot.common.params import Params
from openpilot.selfdrive.car.tesla_turn_signal_controller import (
  RESULT_PARAM,
  REQUEST_PARAM,
  VALIDATION_LOG_PATH,
)


def send_validation_pulse(direction: str, params: Params | None = None, timeout_s: float = 10.0,
                          poll_interval_s: float = 0.05) -> bool:
  if direction not in ("left", "right"):
    raise RuntimeError(f"unsupported turn request: {direction}")
  params = Params() if params is None else params
  if not params.get_bool("TeslaTurnSignalValidation"):
    raise RuntimeError("TeslaTurnSignalValidation is disabled; enable it offroad and restart")

  test_id = uuid.uuid4().hex[:12]
  params.put(REQUEST_PARAM, {
    "test_id": test_id,
    "direction": direction,
    "wall_time_ns": time.time_ns(),
  })
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    result = params.get(RESULT_PARAM)
    if result is not None and result.get("test_id") == test_id:
      status = str(result.get("result", "UNKNOWN"))
      if status == "PASS":
        print(f"PASS: vehicle reports {direction} blinker; log={VALIDATION_LOG_PATH}; test_id={test_id}")
        return True
      print(f"FAIL: {status}; log={VALIDATION_LOG_PATH}; test_id={test_id}")
      return False
    time.sleep(poll_interval_s)

  raise RuntimeError("card realtime turn-signal controller did not respond before timeout")


def main() -> int:
  parser = argparse.ArgumentParser(description="Tesla realtime DAS_bodyControls turn-signal validation")
  parser.add_argument("direction", choices=("left", "right"))
  args = parser.parse_args()
  try:
    return 0 if send_validation_pulse(args.direction) else 2
  except RuntimeError as error:
    print(f"BLOCKED: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
