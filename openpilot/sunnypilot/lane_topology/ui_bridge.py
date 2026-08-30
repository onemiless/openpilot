from __future__ import annotations

import math

import numpy as np

from openpilot.sunnypilot.lane_topology.adapter import LaneTopologyFrame
from openpilot.sunnypilot.lane_topology.metric_marking import measure_metric_marking, MetricMarkingEvidence, \
                                                               project_model_lane_metric_samples, TemporalMarkingFilter
from openpilot.sunnypilot.lane_topology.primary_model import PrimaryModelLaneTopologyAdapter
from openpilot.sunnypilot.lane_topology.tracker import LaneTopologyTracker
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType, LaneTopology


def visionbuf_luma(frame: object) -> np.ndarray:
  width, height, stride = int(frame.width), int(frame.height), int(frame.stride)  # type: ignore[attr-defined]
  if width <= 0 or height <= 0 or stride < width:
    raise ValueError("invalid VisionBuf dimensions")
  luma = np.frombuffer(frame.data, dtype=np.uint8, count=stride * height)  # type: ignore[attr-defined]
  return luma.reshape(height, stride)[:, :width]


class LaneTopologyUIBridge:
  """Low-rate, fail-closed modelV2 consumer for read-only UI state."""

  def __init__(self, *, frame_divisor: int = 5):
    if frame_divisor <= 0:
      raise ValueError("frame_divisor must be positive")
    self.frame_divisor = frame_divisor
    self.marking_types = [LaneMarkingType.unknown] * 4
    self.adapter = PrimaryModelLaneTopologyAdapter(marking_classifier=lambda index, lane: self.marking_types[index])
    self.tracker = LaneTopologyTracker(max_missed_frames=3)
    self.temporal_marking = TemporalMarkingFilter()
    self.current: LaneTopology | None = None
    self.last_frame_id = -1
    self.last_image_model_frame_id = -1
    self.model_v2: object | None = None
    self.marking_evidence = [MetricMarkingEvidence.unknown() for _ in range(4)]
    self.last_error: str | None = None

  def reset(self) -> None:
    self.adapter.close()
    self.tracker.reset()
    self.temporal_marking.reset()
    self.marking_types = [LaneMarkingType.unknown] * 4
    self.marking_evidence = [MetricMarkingEvidence.unknown() for _ in range(4)]
    self.current = None
    self.last_frame_id = -1
    self.last_image_model_frame_id = -1
    self.model_v2 = None
    self.last_error = None

  def update(self, model_v2: object) -> LaneTopology | None:
    try:
      frame_id = int(model_v2.frameId)  # type: ignore[attr-defined]
      if frame_id == self.last_frame_id or frame_id % self.frame_divisor:
        return self.current
      self.last_frame_id = frame_id
      self.model_v2 = model_v2
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

  def needs_image(self, image_frame_id: int) -> bool:
    return (self.model_v2 is not None and self.last_frame_id >= 0 and self.last_image_model_frame_id != self.last_frame_id and
            abs(int(image_frame_id) - self.last_frame_id) <= 3)

  def update_image(self, image_frame_id: int, image: np.ndarray, camera_from_calib: np.ndarray) -> bool:
    if not self.needs_image(image_frame_id):
      return False
    try:
      assert self.model_v2 is not None
      height, width = image.shape[:2]
      sampling_scale = max(1.0, math.sqrt(width / 526.0))
      center_radius = max(3, int(round(3 * sampling_scale)))
      side_offset = max(10, int(round(10 * sampling_scale)))
      search_radius = max(4, int(round(4 * sampling_scale)))
      margin = center_radius + side_offset + search_radius
      probabilities = tuple(float(value) for value in self.model_v2.laneLineProbs)  # type: ignore[attr-defined]
      for lane_index, lane in enumerate(self.model_v2.laneLines):  # type: ignore[attr-defined]
        if probabilities[lane_index] < 0.25:
          evidence = MetricMarkingEvidence.unknown()
        else:
          samples = project_model_lane_metric_samples(lane, camera_from_calib, width, height, image_margin_px=margin)
          evidence = measure_metric_marking(
            image, samples, center_radius=center_radius, side_offset=side_offset, search_radius=search_radius,
          )
        self.marking_evidence[lane_index] = evidence
        self.marking_types[lane_index] = self.temporal_marking.update(lane_index, evidence)
      self.last_image_model_frame_id = self.last_frame_id
      return True
    except Exception as error:
      self.last_error = f"{type(error).__name__}: {error}"
      self.marking_types = [LaneMarkingType.unknown] * 4
      return False

  def ego_marking_types(self) -> tuple[LaneMarkingType, LaneMarkingType] | None:
    topology = self.current
    if topology is None or topology.ego_lane_index_from_left < 0:
      return None
    space = topology.spaces[topology.ego_lane_index_from_left]
    by_track = {boundary.track_id: boundary for boundary in topology.boundaries}
    left, right = by_track.get(space.left_track_id), by_track.get(space.right_track_id)
    if left is None or right is None or LaneMarkingType.unknown in (left.marking_type, right.marking_type):
      return None
    return left.marking_type, right.marking_type
