from openpilot.sunnypilot.lane_topology.adapter import CallableLaneTopologyAdapter, LaneTopologyFrame, ReplayLaneTopologyAdapter
from openpilot.sunnypilot.lane_topology.runner import LaneTopologyRunner
from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation, LaneTopologyState


def line(source_id: int, y: float) -> LaneBoundaryObservation:
  return LaneBoundaryObservation(source_id, ((5.0, y), (10.0, y), (40.0, y)), confidence=0.9)


def test_runner_combines_adapter_tracker_and_geometry_behind_one_call():
  runner = LaneTopologyRunner(ReplayLaneTopologyAdapter({0: (line(1, 1.8), line(2, -1.8))}))
  result = runner.maybe_run(LaneTopologyFrame(0, 10, object(), primary_latency_ms=40.0))
  assert result is not None
  assert result.visible_lane_count == 1
  assert result.ego_lane_index_from_left == 0
  assert result.state == LaneTopologyState.normal


def test_adapter_exception_is_fail_closed_and_never_escapes_modeld_seam():
  def fail(_frame):
    raise RuntimeError("synthetic lane model failure")

  runner = LaneTopologyRunner(CallableLaneTopologyAdapter(fail))
  result = runner.maybe_run(LaneTopologyFrame(0, 10, object(), primary_latency_ms=40.0))
  assert result is not None and result.stale
  assert result.state == LaneTopologyState.stale
  assert not runner.enabled
  assert runner.scheduler.disabled_reason == "adapter_error"
  assert runner.last_error == "RuntimeError: synthetic lane model failure"
  assert runner.maybe_run(LaneTopologyFrame(10, 20, object(), primary_latency_ms=40.0)) is None
