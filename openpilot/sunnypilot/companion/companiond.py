from __future__ import annotations

import time

from openpilot.common.params import Params
from openpilot.sunnypilot.companion.params_api import ParamAccess, params_report_offroad
from openpilot.sunnypilot.companion.server import CompanionServer
from openpilot.sunnypilot.companion.telemetry import TelemetryBroker


def main() -> None:
  params = Params()
  server = CompanionServer(TelemetryBroker(), ParamAccess(params, lambda: params_report_offroad(params)))
  server.start()
  while True:
    time.sleep(60)


if __name__ == "__main__":
  main()
