from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

import numpy as np

from openpilot.sunnypilot.lane_topology.types import LaneBoundaryObservation, LaneMarkingType


YOLOP_INPUT_SIZE = 320


@dataclass(frozen=True)
class LetterboxTransform:
  source_width: int
  source_height: int
  scale: float
  pad_x: int
  pad_y: int
  resized_width: int
  resized_height: int

  def to_source(self, u: float, v: float) -> tuple[float, float] | None:
    source_u = (u - self.pad_x) / self.scale
    source_v = (v - self.pad_y) / self.scale
    if not (0.0 <= source_u < self.source_width and 0.0 <= source_v < self.source_height):
      return None
    return source_u, source_v


class HomographyProjector:
  """Project source-image pixels to vehicle coordinates (x forward, y left)."""

  def __init__(self, image_to_vehicle: np.ndarray):
    matrix = np.asarray(image_to_vehicle, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
      raise ValueError("image_to_vehicle must be a finite 3x3 homography")
    self.matrix = matrix

  def __call__(self, u: float, v: float) -> tuple[float, float] | None:
    projected = self.matrix @ np.array((u, v, 1.0), dtype=np.float64)
    if abs(projected[2]) < 1e-9:
      return None
    x_m, y_m = projected[0] / projected[2], projected[1] / projected[2]
    if not (math.isfinite(x_m) and math.isfinite(y_m)):
      return None
    return float(x_m), float(y_m)


def letterbox_rgb(image: np.ndarray, size: int = YOLOP_INPUT_SIZE) -> tuple[np.ndarray, LetterboxTransform]:
  """Nearest-neighbour RGB letterbox matching the fixed YOLOP input shape."""

  source = np.asarray(image)
  if source.ndim != 3 or source.shape[2] != 3:
    raise ValueError("YOLOP input must be an HxWx3 RGB image")
  if source.dtype != np.uint8:
    raise ValueError("YOLOP RGB input must use uint8 pixels")
  source_height, source_width = source.shape[:2]
  scale = min(size / source_width, size / source_height)
  resized_width = max(1, int(round(source_width * scale)))
  resized_height = max(1, int(round(source_height * scale)))
  x_indices = np.minimum((np.arange(resized_width) / scale).astype(np.int64), source_width - 1)
  y_indices = np.minimum((np.arange(resized_height) / scale).astype(np.int64), source_height - 1)
  resized = source[y_indices[:, None], x_indices[None, :]]
  pad_x, pad_y = (size - resized_width) // 2, (size - resized_height) // 2
  output = np.full((size, size, 3), 114, dtype=np.uint8)
  output[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
  nchw = np.ascontiguousarray(output.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
  return nchw, LetterboxTransform(source_width, source_height, scale, pad_x, pad_y, resized_width, resized_height)


@dataclass
class _PixelTrack:
  points: list[tuple[float, float]]
  confidences: list[float]
  last_u: float
  last_v: float


def _row_runs(mask_row: np.ndarray, confidence_row: np.ndarray, *, min_width_px: int) -> list[tuple[float, float]]:
  indices = np.flatnonzero(mask_row)
  if not len(indices):
    return []
  split_at = np.flatnonzero(np.diff(indices) > 1) + 1
  runs = np.split(indices, split_at)
  return [(float(run.mean()), float(confidence_row[run].mean())) for run in runs if len(run) >= min_width_px]


def _marking_type(points: list[tuple[float, float]], *, row_step: int) -> LaneMarkingType:
  if len(points) < 3:
    return LaneMarkingType.unknown
  rows = sorted(point[1] for point in points)
  expected = max(1, int(round((rows[-1] - rows[0]) / row_step)) + 1)
  coverage = len(rows) / expected
  gaps = [b - a for a, b in zip(rows, rows[1:], strict=False)]
  segments = 1 + sum(gap > row_step * 1.75 for gap in gaps)
  if coverage >= 0.72 and segments <= 2:
    return LaneMarkingType.solid
  if 0.12 <= coverage < 0.72 and segments >= 2:
    return LaneMarkingType.dashed
  return LaneMarkingType.unknown


def lane_logits_to_observations(lane_logits: np.ndarray, transform: LetterboxTransform,
                                projector: Callable[[float, float], tuple[float, float] | None], *,
                                row_step: int = 4, min_width_px: int = 1, association_px: float = 24.0,
                                max_gap_px: float = 56.0, min_points: int = 5) -> tuple[LaneBoundaryObservation, ...]:
  """Extract independent vehicle-coordinate lane observations from YOLOP logits."""

  logits = np.asarray(lane_logits, dtype=np.float32)
  if logits.shape == (1, 2, YOLOP_INPUT_SIZE, YOLOP_INPUT_SIZE):
    logits = logits[0]
  if logits.shape != (2, YOLOP_INPUT_SIZE, YOLOP_INPUT_SIZE):
    raise ValueError(f"unexpected YOLOP lane output shape: {logits.shape}")

  lane_confidence = logits[1] - logits[0]
  mask = lane_confidence > 0.0
  active: list[_PixelTrack] = []
  completed: list[_PixelTrack] = []
  top = transform.pad_y
  bottom = transform.pad_y + transform.resized_height - 1

  for v in range(bottom, top - 1, -row_step):
    band_top = max(top, v - row_step + 1)
    band_mask = np.any(mask[band_top:v + 1], axis=0)
    band_confidence = np.max(lane_confidence[band_top:v + 1], axis=0)
    runs = _row_runs(band_mask, band_confidence, min_width_px=min_width_px)
    available = set(range(len(active)))
    assigned_runs: set[int] = set()
    candidates = sorted((abs(u - track.last_u), run_index, track_index)
                        for run_index, (u, _) in enumerate(runs)
                        for track_index, track in enumerate(active)
                        if v <= track.last_v and track.last_v - v <= max_gap_px and abs(u - track.last_u) <= association_px)
    for _, run_index, track_index in candidates:
      if run_index in assigned_runs or track_index not in available:
        continue
      u, confidence = runs[run_index]
      track = active[track_index]
      track.points.append((u, float(v)))
      track.confidences.append(confidence)
      track.last_u, track.last_v = u, float(v)
      assigned_runs.add(run_index)
      available.remove(track_index)
    for run_index, (u, confidence) in enumerate(runs):
      if run_index not in assigned_runs:
        active.append(_PixelTrack([(u, float(v))], [confidence], u, float(v)))

    still_active: list[_PixelTrack] = []
    for track in active:
      if track.last_v - v > max_gap_px:
        completed.append(track)
      else:
        still_active.append(track)
    active = still_active
  completed.extend(active)

  observations: list[LaneBoundaryObservation] = []
  for track in completed:
    if len(track.points) < min_points:
      continue
    vehicle_points: list[tuple[float, float]] = []
    for u, v in track.points:
      source_point = transform.to_source(u, v)
      if source_point is None:
        continue
      vehicle_point = projector(*source_point)
      if vehicle_point is not None and vehicle_point[0] >= 0.0:
        vehicle_points.append(vehicle_point)
    vehicle_points.sort()
    if len(vehicle_points) < min_points:
      continue
    confidence = float(np.clip(np.mean(track.confidences), 0.0, 1.0))
    observations.append(LaneBoundaryObservation(
      source_id=len(observations),
      points=tuple(vehicle_points),
      marking_type=_marking_type(track.points, row_step=row_step),
      confidence=confidence,
    ))
  observations.sort(key=lambda observation: observation.points[0][1], reverse=True)
  return tuple(observations)
