from __future__ import annotations

from dataclasses import replace
import time

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame, LaneTopologyModelAdapter
from openpilot.sunnypilot.lane_topology.scheduler import LaneTopologyScheduler
from openpilot.sunnypilot.lane_topology.tracker import LaneTopologyTracker
from openpilot.sunnypilot.lane_topology.types import LaneTopology


class LaneTopologyRunner:
  """Fail-closed shadow runner; it never owns or opens a GPU device."""

  def __init__(self, adapter: LaneTopologyModelAdapter, *, scheduler: LaneTopologyScheduler | None = None,
               tracker: LaneTopologyTracker | None = None):
    self.adapter = adapter
    self.scheduler = scheduler or LaneTopologyScheduler()
    self.tracker = tracker or LaneTopologyTracker()
    self.last_error: str | None = None

  @property
  def enabled(self) -> bool:
    return self.scheduler.enabled

  def maybe_run(self, frame: LaneTopologyFrame) -> LaneTopology | None:
    if not self.scheduler.should_run(frame):
      return None

    started = time.perf_counter()
    try:
      observations = self.adapter.infer(frame)
      latency_ms = (time.perf_counter() - started) * 1000.0
      result = self.tracker.update(observations, frame_id=frame.frame_id, timestamp_ns=frame.timestamp_ns,
                                   model_latency_ms=latency_ms)
      self.scheduler.record_aux_latency(latency_ms)
      return result
    except Exception as error:
      latency_ms = (time.perf_counter() - started) * 1000.0
      self.last_error = f"{type(error).__name__}: {error}"
      self.scheduler.disable("adapter_error")
      return replace(LaneTopology.empty(frame.frame_id, frame.timestamp_ns, stale=True), model_latency_ms=latency_ms)

  def close(self) -> None:
    try:
      self.adapter.close()
    except Exception as error:
      self.last_error = f"{type(error).__name__}: {error}"
      self.scheduler.disable("adapter_close_error")
