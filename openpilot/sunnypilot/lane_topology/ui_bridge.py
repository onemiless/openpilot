from __future__ import annotations

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.primary_model import PrimaryModelLaneTopologyAdapter
from openpilot.sunnypilot.lane_topology.tracker import LaneTopologyTracker
from openpilot.sunnypilot.lane_topology.types import LaneTopology


class LaneTopologyUIBridge:
  """Low-rate, fail-closed modelV2 consumer for read-only UI state."""

  def __init__(self, *, frame_divisor: int = 5):
    if frame_divisor <= 0:
      raise ValueError("frame_divisor must be positive")
    self.frame_divisor = frame_divisor
    self.adapter = PrimaryModelLaneTopologyAdapter()
    self.tracker = LaneTopologyTracker(max_missed_frames=3)
    self.current: LaneTopology | None = None
    self.last_frame_id = -1
    self.last_error: str | None = None

  def reset(self) -> None:
    self.adapter.close()
    self.tracker.reset()
    self.current = None
    self.last_frame_id = -1
    self.last_error = None

  def update(self, model_v2: object) -> LaneTopology | None:
    try:
      frame_id = int(model_v2.frameId)  # type: ignore[attr-defined]
      if frame_id == self.last_frame_id or frame_id % self.frame_divisor:
        return self.current
      self.last_frame_id = frame_id
      timestamp_ns = int(model_v2.timestampEof)  # type: ignore[attr-defined]
      frame = LaneTopologyFrame(frame_id, timestamp_ns, model_v2)
      observations = self.adapter.infer(frame)
      self.current = self.tracker.update(observations, frame_id=frame_id, timestamp_ns=timestamp_ns)
      self.last_error = None
      return self.current
    except Exception as error:
      self.last_error = f"{type(error).__name__}: {error}"
      self.current = None
      return None
