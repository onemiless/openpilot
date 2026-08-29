import pytest

from openpilot.sunnypilot.lane_topology.adapter import ReplayLaneTopologyAdapter
from openpilot.sunnypilot.lane_topology.benchmark import LaneTopologyBenchmarkSample, percentile, run_interleaved_benchmark
from openpilot.sunnypilot.lane_topology.runner import LaneTopologyRunner
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation


def line(source_id: int, y: float) -> LaneBoundaryObservation:
  return LaneBoundaryObservation(source_id, ((5.0, y), (10.0, y), (40.0, y)), confidence=0.9)


def test_percentile_interpolates_and_rejects_invalid_quantiles():
  assert percentile([10.0, 20.0], 0.5) == 15.0
  assert percentile([], 0.5) is None


def test_interleaved_report_counts_only_scheduled_lane_runs():
  samples = [LaneTopologyBenchmarkSample(index, index, object(), primary_latency_ms=40.0) for index in range(20)]
  frames = {0: (line(1, 1.8), line(2, -1.8)), 10: (line(3, 1.8), line(4, -1.8))}
  runner = LaneTopologyRunner(ReplayLaneTopologyAdapter(frames))
  report = run_interleaved_benchmark(samples, runner)
  assert report["status"] == "PASS"
  assert report["primary"]["count"] == 20
  assert report["lane"]["runs"] == 2
  assert report["lane"]["valid_outputs"] == 2
  assert report["last_topology"]["visible_lane_count"] == 1


def test_injected_primary_callable_is_measured_before_lane_gate():
  values = iter((1.000, 1.040, 2.000, 2.050))
  calls: list[object] = []
  samples = [LaneTopologyBenchmarkSample(0, 0, "a"), LaneTopologyBenchmarkSample(10, 10, "b")]
  runner = LaneTopologyRunner(ReplayLaneTopologyAdapter({0: (), 10: ()}))
  report = run_interleaved_benchmark(samples, runner, primary_step=calls.append, clock=lambda: next(values))
  assert calls == ["a", "b"]
  assert report["primary"]["p50_ms"] == pytest.approx(45.0)
  assert report["lane"]["runs"] == 1  # 50 ms second primary run is over the 43 ms gate.
