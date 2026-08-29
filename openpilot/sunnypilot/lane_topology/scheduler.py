from __future__ import annotations

from dataclasses import dataclass
import math

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame


@dataclass(frozen=True)
class LaneTopologySchedule:
  primary_frequency_hz: float = 20.0
  lane_frequency_hz: float = 2.0
  max_primary_latency_ms: float = 43.0
  max_aux_latency_ms: float = 15.0
  max_consecutive_overruns: int = 2

  def __post_init__(self) -> None:
    if self.primary_frequency_hz <= 0 or self.lane_frequency_hz <= 0:
      raise ValueError("model frequencies must be positive")
    if self.lane_frequency_hz > self.primary_frequency_hz:
      raise ValueError("lane model cannot outrun the primary model")
    if self.max_primary_latency_ms <= 0 or self.max_aux_latency_ms <= 0:
      raise ValueError("latency limits must be positive")
    if self.max_consecutive_overruns <= 0:
      raise ValueError("max_consecutive_overruns must be positive")

  @property
  def frame_interval(self) -> int:
    return max(1, math.ceil(self.primary_frequency_hz / self.lane_frequency_hz))


class LaneTopologyScheduler:
  def __init__(self, schedule: LaneTopologySchedule | None = None, *, enabled: bool = True):
    self.schedule = schedule or LaneTopologySchedule()
    self.enabled = enabled
    self.disabled_reason: str | None = None
    self._next_due_frame = 0
    self._consecutive_overruns = 0

  def disable(self, reason: str) -> None:
    self.enabled = False
    self.disabled_reason = reason

  def should_run(self, frame: LaneTopologyFrame) -> bool:
    if not self.enabled:
      return False
    if frame.prepare_only or frame.dropped_frames > 0 or not frame.calibration_valid:
      return False
    if frame.primary_latency_ms > self.schedule.max_primary_latency_ms:
      return False
    if frame.frame_id < self._next_due_frame:
      return False
    self._next_due_frame = frame.frame_id + self.schedule.frame_interval
    return True

  def record_aux_latency(self, latency_ms: float) -> None:
    if latency_ms > self.schedule.max_aux_latency_ms:
      self._consecutive_overruns += 1
      if self._consecutive_overruns >= self.schedule.max_consecutive_overruns:
        self.disable("aux_latency_budget_exceeded")
    else:
      self._consecutive_overruns = 0
