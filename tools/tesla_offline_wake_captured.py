#!/usr/bin/env python3
"""Process-manager entry point for the Tesla offline wake CAN capture."""

import argparse

from openpilot.common.params import Params
from openpilot.tools.analyze_tesla_offline_wake_capture import write_report
from openpilot.tools.tesla_offline_wake_capture import DEFAULT_OUTPUT_ROOT, run_capture


def main() -> None:
  # The UI owns this flag. Clear it when a completed capture exits so the
  # process manager does not immediately start a second capture.
  params = Params()
  args = argparse.Namespace(
    output_root=DEFAULT_OUTPUT_ROOT,
    addr="127.0.0.1",
    quiet_seconds=300.0,
    post_wake_seconds=120.0,
    raw_window_seconds=60.0,
    record_all=False,
  )
  try:
    output_dir = run_capture(args)
    report, report_path = write_report(output_dir / "capture.jsonl.gz")
    print(f"Wake-bus report saved: {report_path}")
    print(f"Wake-bus candidates: {report['wake_bus_candidates']}")
  finally:
    params.put_bool("TeslaOfflineWakeCaptureEnabled", False)


if __name__ == "__main__":
  main()
