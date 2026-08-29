from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import math
import time

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.runner import LaneTopologyRunner


@dataclass(frozen=True)
class LaneTopologyBenchmarkSample:
  frame_id: int
  timestamp_ns: int
  payload: object
  primary_latency_ms: float | None = None
  dropped_frames: int = 0
  prepare_only: bool = False
  calibration_valid: bool = True


def percentile(values: list[float], quantile: float) -> float | None:
  if not values:
    return None
  if not 0.0 <= quantile <= 1.0:
    raise ValueError("quantile must be within [0, 1]")
  ordered = sorted(values)
  position = (len(ordered) - 1) * quantile
  lower, upper = math.floor(position), math.ceil(position)
  if lower == upper:
    return ordered[lower]
  fraction = position - lower
  return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _latency_summary(values: list[float]) -> dict[str, float | int | None]:
  return {
    "count": len(values),
    "mean_ms": (sum(values) / len(values)) if values else None,
    "p50_ms": percentile(values, 0.50),
    "p95_ms": percentile(values, 0.95),
    "p99_ms": percentile(values, 0.99),
    "max_ms": max(values) if values else None,
  }


def run_interleaved_benchmark(samples: Iterable[LaneTopologyBenchmarkSample], runner: LaneTopologyRunner, *,
                              primary_step: Callable[[object], object] | None = None,
                              clock: Callable[[], float] = time.perf_counter) -> dict:
  """Run primary-first samples and conditionally run Lane Topology in-process.

  A hardware benchmark injects the existing primary model as ``primary_step``.
  Replay fixtures omit it and carry recorded primary latency in each sample.
  """

  primary_latencies: list[float] = []
  lane_latencies: list[float] = []
  lane_runs = 0
  lane_valid = 0
  lane_stale = 0
  samples_seen = 0
  last_topology: dict | None = None

  for sample in samples:
    samples_seen += 1
    if primary_step is not None:
      started = clock()
      primary_step(sample.payload)
      primary_latency_ms = (clock() - started) * 1000.0
    elif sample.primary_latency_ms is not None:
      primary_latency_ms = sample.primary_latency_ms
    else:
      raise ValueError("sample primary latency is required when no primary_step is injected")
    primary_latencies.append(primary_latency_ms)

    result = runner.maybe_run(LaneTopologyFrame(
      frame_id=sample.frame_id,
      timestamp_ns=sample.timestamp_ns,
      payload=sample.payload,
      primary_latency_ms=primary_latency_ms,
      dropped_frames=sample.dropped_frames,
      prepare_only=sample.prepare_only,
      calibration_valid=sample.calibration_valid,
    ))
    if result is None:
      continue
    lane_runs += 1
    lane_latencies.append(result.model_latency_ms)
    if result.stale:
      lane_stale += 1
    else:
      lane_valid += 1
    last_topology = {
      "frame_id": result.frame_id,
      "visible_lane_count": result.visible_lane_count,
      "boundary_count_visible": result.boundary_count_visible,
      "marking_count_visible": result.marking_count_visible,
      "ego_lane_index_from_left": result.ego_lane_index_from_left,
      "state": int(result.state),
      "confidence": result.confidence,
      "stale": result.stale,
    }

  return {
    "schema": "lane-topology-interleaved-benchmark-v1",
    "status": "PASS" if runner.last_error is None else "FAIL",
    "samples": samples_seen,
    "primary": _latency_summary(primary_latencies),
    "lane": {
      **_latency_summary(lane_latencies),
      "runs": lane_runs,
      "valid_outputs": lane_valid,
      "stale_outputs": lane_stale,
      "requested_frequency_hz": runner.scheduler.schedule.lane_frequency_hz,
      "frame_interval": runner.scheduler.schedule.frame_interval,
    },
    "runner_enabled_at_exit": runner.enabled,
    "disabled_reason": runner.scheduler.disabled_reason,
    "last_error": runner.last_error,
    "last_topology": last_topology,
  }
