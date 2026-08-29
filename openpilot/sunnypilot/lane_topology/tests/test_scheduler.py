from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.scheduler import LaneTopologySchedule, LaneTopologyScheduler


def frame(frame_id: int, **kwargs) -> LaneTopologyFrame:
  return LaneTopologyFrame(frame_id, frame_id, object(), **kwargs)


def test_default_schedule_runs_at_most_two_hz_from_twenty_hz_primary():
  scheduler = LaneTopologyScheduler()
  assert scheduler.schedule.frame_interval == 10
  assert scheduler.should_run(frame(0, primary_latency_ms=40.0))
  assert not scheduler.should_run(frame(9, primary_latency_ms=40.0))
  assert scheduler.should_run(frame(10, primary_latency_ms=40.0))


def test_primary_health_gates_do_not_consume_the_next_due_frame():
  scheduler = LaneTopologyScheduler()
  assert not scheduler.should_run(frame(0, dropped_frames=1))
  assert not scheduler.should_run(frame(0, prepare_only=True))
  assert not scheduler.should_run(frame(0, calibration_valid=False))
  assert not scheduler.should_run(frame(0, primary_latency_ms=44.0))
  assert scheduler.should_run(frame(0, primary_latency_ms=43.0))


def test_two_consecutive_aux_overruns_disable_for_the_session():
  scheduler = LaneTopologyScheduler(LaneTopologySchedule(max_aux_latency_ms=5.0, max_consecutive_overruns=2))
  scheduler.record_aux_latency(6.0)
  assert scheduler.enabled
  scheduler.record_aux_latency(6.0)
  assert not scheduler.enabled
  assert scheduler.disabled_reason == "aux_latency_budget_exceeded"


def test_good_latency_resets_the_consecutive_overrun_counter():
  scheduler = LaneTopologyScheduler(LaneTopologySchedule(max_aux_latency_ms=5.0, max_consecutive_overruns=2))
  scheduler.record_aux_latency(6.0)
  scheduler.record_aux_latency(4.0)
  scheduler.record_aux_latency(6.0)
  assert scheduler.enabled
