#!/usr/bin/env python3
"""Replay Lane Topology fixtures through the production candidate scheduler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpilot.sunnypilot.lane_topology.adapter import ReplayLaneTopologyAdapter
from openpilot.sunnypilot.lane_topology.benchmark import LaneTopologyBenchmarkSample, run_interleaved_benchmark
from openpilot.sunnypilot.lane_topology.runner import LaneTopologyRunner
from openpilot.sunnypilot.lane_topology.scheduler import LaneTopologySchedule, LaneTopologyScheduler
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation, LaneMarkingType


def _observation(raw: dict) -> LaneBoundaryObservation:
  return LaneBoundaryObservation(
    source_id=int(raw["source_id"]),
    points=tuple((float(point[0]), float(point[1])) for point in raw["points"]),
    marking_type=LaneMarkingType(int(raw.get("marking_type", LaneMarkingType.unknown))),
    confidence=float(raw.get("confidence", 0.0)),
    visible=bool(raw.get("visible", True)),
  )


def load_fixture(path: Path) -> tuple[list[LaneTopologyBenchmarkSample], dict[int, tuple[LaneBoundaryObservation, ...]]]:
  data = json.loads(path.read_text())
  samples: list[LaneTopologyBenchmarkSample] = []
  frames: dict[int, tuple[LaneBoundaryObservation, ...]] = {}
  for raw in data["samples"]:
    frame_id = int(raw["frame_id"])
    samples.append(LaneTopologyBenchmarkSample(
      frame_id=frame_id,
      timestamp_ns=int(raw.get("timestamp_ns", frame_id * 50_000_000)),
      payload=raw.get("payload", frame_id),
      primary_latency_ms=float(raw["primary_latency_ms"]),
      dropped_frames=int(raw.get("dropped_frames", 0)),
      prepare_only=bool(raw.get("prepare_only", False)),
      calibration_valid=bool(raw.get("calibration_valid", True)),
    ))
    frames[frame_id] = tuple(_observation(observation) for observation in raw.get("boundaries", ()))
  return samples, frames


def write_exclusive(path: Path, report: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("x") as output:
    json.dump(report, output, indent=2, sort_keys=True)
    output.write("\n")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--fixture", type=Path, required=True)
  parser.add_argument("--report", type=Path, required=True)
  parser.add_argument("--primary-hz", type=float, default=20.0)
  parser.add_argument("--lane-hz", type=float, default=2.0)
  parser.add_argument("--max-primary-ms", type=float, default=43.0)
  parser.add_argument("--max-lane-ms", type=float, default=15.0)
  args = parser.parse_args()

  samples, frames = load_fixture(args.fixture)
  schedule = LaneTopologySchedule(
    primary_frequency_hz=args.primary_hz,
    lane_frequency_hz=args.lane_hz,
    max_primary_latency_ms=args.max_primary_ms,
    max_aux_latency_ms=args.max_lane_ms,
  )
  runner = LaneTopologyRunner(ReplayLaneTopologyAdapter(frames), scheduler=LaneTopologyScheduler(schedule))
  try:
    report = run_interleaved_benchmark(samples, runner)
  finally:
    runner.close()
  write_exclusive(args.report, report)
  print(json.dumps(report, indent=2, sort_keys=True))
  return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
  raise SystemExit(main())
