#!/usr/bin/env python3
"""Turn a Tesla sleep/wake CAN capture into a wake-bus selection report."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_records(path: Path):
  with gzip.open(path, "rt", encoding="utf-8") as capture:
    for line in capture:
      yield json.loads(line)


def analyze(records) -> dict[str, Any]:
  quiet_at = None
  wake_at = None
  first_frame_by_bus: dict[int, dict[str, Any]] = {}
  frame_counts: Counter[int] = Counter()
  address_counts: dict[int, Counter[int]] = defaultdict(Counter)

  for record in records:
    if record["type"] == "marker":
      if record["name"] == "quiet_entered":
        quiet_at = record["t_monotonic_s"]
      elif record["name"] == "wake_activity":
        wake_at = record["t_monotonic_s"]
    elif record["type"] == "frame" and wake_at is not None and record["t_monotonic_s"] >= wake_at:
      bus = int(record["bus"])
      first_frame_by_bus.setdefault(bus, record)
      frame_counts[bus] += 1
      address_counts[bus][int(record["address"])] += 1

  candidates = []
  for bus, first_frame in sorted(first_frame_by_bus.items(), key=lambda item: item[1]["t_monotonic_s"]):
    candidates.append({
      "bus": bus,
      "first_frame_time_s": first_frame["t_monotonic_s"],
      "first_address": first_frame["address"],
      "first_data": first_frame["data"],
      "post_wake_frame_count": frame_counts[bus],
      "top_addresses": [
        {"address": address, "frames": count}
        for address, count in address_counts[bus].most_common(10)
      ],
    })

  return {
    "quiet_interval_observed": quiet_at is not None,
    "wake_activity_observed": wake_at is not None,
    "quiet_started_at_s": quiet_at,
    "wake_started_at_s": wake_at,
    "wake_bus_candidates": candidates,
    "recommendation": (
      "Use the earliest candidate bus as the Panda STOP-mode wake RX candidate; validate it with a second capture."
      if quiet_at is not None and wake_at is not None else
      "No fully quiet-to-active transition was observed. Do not choose a wake bus yet; repeat with a longer quiet interval or inspect the raw capture."
    ),
  }


def write_report(capture_path: Path) -> tuple[dict[str, Any], Path]:
  report = analyze(load_records(capture_path))
  report_path = capture_path.with_name("wake_bus_report.json")
  report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
  return report, report_path


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("capture", type=Path, help="capture.jsonl.gz file or its containing directory")
  args = parser.parse_args()
  capture_path = args.capture / "capture.jsonl.gz" if args.capture.is_dir() else args.capture
  report, report_path = write_report(capture_path)
  print(json.dumps(report, indent=2, sort_keys=True))
  print(f"Saved report: {report_path}")


if __name__ == "__main__":
  main()
