from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from openpilot.sunnypilot.lane_topology.types import LaneMarkingType


@dataclass(frozen=True)
class MarkingEvidence:
  marking_type: LaneMarkingType
  sample_count: int
  lit_count: int
  coverage: float
  transitions: int
  lit_runs: int


def _resample_by_image_row(points: tuple[tuple[float, float], ...], row_step_px: float) -> tuple[tuple[float, float], ...]:
  ordered = sorted(points, key=lambda point: point[1])
  by_row: dict[float, list[float]] = {}
  for u, v in ordered:
    by_row.setdefault(float(v), []).append(float(u))
  rows = np.array(sorted(by_row), dtype=np.float64)
  if len(rows) < 2 or rows[-1] - rows[0] < row_step_px:
    return tuple(ordered)
  columns = np.array([sum(by_row[row]) / len(by_row[row]) for row in rows], dtype=np.float64)
  sample_rows = np.arange(rows[0], rows[-1] + row_step_px * 0.5, row_step_px)
  sample_columns = np.interp(sample_rows, rows, columns)
  return tuple((float(u), float(v)) for u, v in zip(sample_columns, sample_rows, strict=True))


def measure_marking_continuity(image: np.ndarray, points: tuple[tuple[float, float], ...], *,
                               center_radius: int = 3, side_offset: int = 10,
                               contrast_threshold: float = 14.0, row_step_px: float = 4.0) -> MarkingEvidence:
  """Classify solid/dashed from synchronized image evidence along a lane.

  RGB input uses its brightest channel, while an HxW array is treated as a
  luma plane. Uncertain evidence remains ``unknown`` instead of being guessed.
  """

  source = np.asarray(image)
  if source.dtype != np.uint8 or source.ndim not in (2, 3) or (source.ndim == 3 and source.shape[2] != 3):
    raise ValueError("marking classification requires HxW luma or HxWx3 uint8 RGB")
  if len(points) < 6:
    return MarkingEvidence(LaneMarkingType.unknown, 0, 0, 0.0, 0, 0)

  height, width = source.shape[:2]
  luminance = source.astype(np.float32) if source.ndim == 2 else source.astype(np.float32).max(axis=2)
  visible: list[bool] = []
  for u_float, v_float in _resample_by_image_row(points, row_step_px):
    u, v = int(round(u_float)), int(round(v_float))
    if not (side_offset + center_radius <= u < width - side_offset - center_radius and center_radius <= v < height - center_radius):
      continue
    center = luminance[v - center_radius:v + center_radius + 1, u - center_radius:u + center_radius + 1]
    left = luminance[v - center_radius:v + center_radius + 1,
                     u - side_offset - center_radius:u - side_offset + center_radius + 1]
    right = luminance[v - center_radius:v + center_radius + 1,
                      u + side_offset - center_radius:u + side_offset + center_radius + 1]
    road_level = 0.5 * (float(np.median(left)) + float(np.median(right)))
    visible.append(float(np.percentile(center, 80)) - road_level >= contrast_threshold)

  if len(visible) < 6:
    return MarkingEvidence(LaneMarkingType.unknown, len(visible), sum(visible), 0.0, 0, 0)
  coverage = sum(visible) / len(visible)
  transitions = sum(current != previous for previous, current in zip(visible, visible[1:], strict=False))
  lit_runs = int(visible[0]) + sum(not previous and current for previous, current in zip(visible, visible[1:], strict=False))
  if coverage >= 0.72 and transitions <= 3:
    marking_type = LaneMarkingType.solid
  elif 0.18 <= coverage <= 0.88 and lit_runs >= 2 and transitions >= 3:
    marking_type = LaneMarkingType.dashed
  else:
    marking_type = LaneMarkingType.unknown
  return MarkingEvidence(marking_type, len(visible), sum(visible), coverage, transitions, lit_runs)


def classify_marking_continuity(image: np.ndarray, points: tuple[tuple[float, float], ...], **kwargs) -> LaneMarkingType:
  return measure_marking_continuity(image, points, **kwargs).marking_type


def project_model_lane_to_image(lane_line: object, camera_from_calib: np.ndarray, image_width: int, image_height: int, *,
                                min_distance_m: float = 3.0, max_distance_m: float = 60.0) -> tuple[tuple[float, float], ...]:
  """Project one modelV2 lane line into synchronized camera pixels."""

  matrix = np.asarray(camera_from_calib, dtype=np.float64)
  if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
    raise ValueError("camera_from_calib must be a finite 3x3 matrix")
  xs = np.asarray(lane_line.x, dtype=np.float64)  # type: ignore[attr-defined]
  ys = np.asarray(lane_line.y, dtype=np.float64)  # type: ignore[attr-defined]
  zs = np.asarray(lane_line.z, dtype=np.float64)  # type: ignore[attr-defined]
  if not (xs.shape == ys.shape == zs.shape):
    raise ValueError("model lane x/y/z lengths must match")
  valid = np.isfinite(xs) & np.isfinite(ys) & np.isfinite(zs) & (xs >= min_distance_m) & (xs <= max_distance_m)
  if not np.any(valid):
    return ()
  projected = matrix @ np.stack((xs[valid], ys[valid], zs[valid]))
  in_front = projected[2] > 1e-3
  pixels = projected[:2, in_front] / projected[2, in_front]
  in_image = ((pixels[0] >= 0.0) & (pixels[0] < image_width) &
              (pixels[1] >= 0.0) & (pixels[1] < image_height))
  return tuple((float(u), float(v)) for u, v in pixels[:, in_image].T)
