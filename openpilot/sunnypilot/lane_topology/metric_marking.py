from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from openpilot.sunnypilot.lane_topology.types import LaneMarkingType


@dataclass(frozen=True)
class MetricLaneSample:
  distance_m: float
  u: float
  v: float


@dataclass(frozen=True)
class MetricMarkingEvidence:
  marking_type: LaneMarkingType
  confidence: float
  sample_count: int
  lit_count: int
  coverage: float
  transitions: int
  lit_runs: int
  max_internal_dark_gap_m: float
  median_lit_run_m: float
  complete_lit_runs: int
  internal_dark_runs: int
  run_regularity: float

  @classmethod
  def unknown(cls, sample_count: int = 0) -> MetricMarkingEvidence:
    return cls(LaneMarkingType.unknown, 0.0, sample_count, 0, 0.0, 0, 0, 0.0, 0.0, 0, 0, 0.0)


def project_model_lane_metric_samples(lane_line: object, camera_from_calib: np.ndarray,
                                      image_width: int, image_height: int, *,
                                      min_distance_m: float = 5.0, max_distance_m: float = 50.0,
                                      distance_step_m: float = 0.5,
                                      image_margin_px: float = 20.0) -> tuple[MetricLaneSample, ...]:
  """Interpolate a model lane uniformly in metres, then project to the image."""

  if distance_step_m <= 0.0 or min_distance_m >= max_distance_m:
    raise ValueError("invalid metric lane sampling range")
  matrix = np.asarray(camera_from_calib, dtype=np.float64)
  if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
    raise ValueError("camera_from_calib must be a finite 3x3 matrix")
  xs = np.asarray(lane_line.x, dtype=np.float64)  # type: ignore[attr-defined]
  ys = np.asarray(lane_line.y, dtype=np.float64)  # type: ignore[attr-defined]
  zs = np.asarray(lane_line.z, dtype=np.float64)  # type: ignore[attr-defined]
  valid = np.isfinite(xs) & np.isfinite(ys) & np.isfinite(zs)
  xs, ys, zs = xs[valid], ys[valid], zs[valid]
  if len(xs) < 2:
    return ()
  order = np.argsort(xs)
  xs, ys, zs = xs[order], ys[order], zs[order]
  unique_x, unique_indices = np.unique(xs, return_index=True)
  ys, zs = ys[unique_indices], zs[unique_indices]
  start, end = max(min_distance_m, float(unique_x[0])), min(max_distance_m, float(unique_x[-1]))
  if end <= start:
    return ()
  sample_x = np.arange(start, end + distance_step_m * 0.5, distance_step_m)
  sample_y = np.interp(sample_x, unique_x, ys)
  sample_z = np.interp(sample_x, unique_x, zs)
  projected = matrix @ np.stack((sample_x, sample_y, sample_z))
  in_front = projected[2] > 1e-3
  pixels = projected[:2, in_front] / projected[2, in_front]
  distances = sample_x[in_front]
  inside = ((pixels[0] >= image_margin_px) & (pixels[0] < image_width - image_margin_px) &
            (pixels[1] >= image_margin_px) & (pixels[1] < image_height - image_margin_px))
  return tuple(MetricLaneSample(float(x), float(u), float(v))
               for x, u, v in zip(distances[inside], pixels[0, inside], pixels[1, inside], strict=True))


def _clean_binary_sequence(values: list[bool]) -> list[bool]:
  cleaned = values[:]
  for index in range(1, len(values) - 1):
    if values[index - 1] == values[index + 1] != values[index]:
      cleaned[index] = values[index - 1]
  return cleaned


def _runs(values: list[bool], step_m: float) -> list[tuple[bool, float]]:
  if not values:
    return []
  runs: list[tuple[bool, float]] = []
  current, count = values[0], 1
  for value in values[1:]:
    if value == current:
      count += 1
    else:
      runs.append((current, count * step_m))
      current, count = value, 1
  runs.append((current, count * step_m))
  return runs


def _normal_patch_value(luminance: np.ndarray, sample: MetricLaneSample, normal: np.ndarray,
                        offset: float, center_radius: int) -> float:
  center_u, center_v = sample.u + normal[0] * offset, sample.v + normal[1] * offset
  u0, v0 = int(round(center_u)), int(round(center_v))
  patch = luminance[v0 - center_radius:v0 + center_radius + 1,
                    u0 - center_radius:u0 + center_radius + 1]
  return float(np.mean(patch))


def classify_metric_presence(distances_m: np.ndarray, presence: np.ndarray) -> MetricMarkingEvidence:
  distances = np.asarray(distances_m, dtype=np.float64)
  flags = np.asarray(presence, dtype=bool)
  if distances.ndim != 1 or flags.ndim != 1 or len(distances) != len(flags) or len(flags) < 12:
    return MetricMarkingEvidence.unknown(len(flags))
  steps = np.diff(distances)
  step_m = float(np.median(steps)) if len(steps) else 0.0
  if not math.isfinite(step_m) or step_m <= 0.0 or np.any(steps > step_m * 1.8):
    return MetricMarkingEvidence.unknown(len(flags))

  cleaned = _clean_binary_sequence(flags.tolist())
  run_values = _runs(cleaned, step_m)
  lit_lengths = [length for lit, length in run_values if lit]
  complete_lit_lengths = [length for index, (lit, length) in enumerate(run_values)
                          if lit and 0 < index < len(run_values) - 1]
  internal_dark = [length for index, (lit, length) in enumerate(run_values)
                   if not lit and 0 < index < len(run_values) - 1]
  coverage = sum(cleaned) / len(cleaned)
  transitions = sum(current != previous for previous, current in zip(cleaned, cleaned[1:], strict=False))
  lit_runs = len(lit_lengths)
  max_dark_gap = max(internal_dark, default=0.0)
  median_lit = float(np.median(lit_lengths)) if lit_lengths else 0.0
  lit_cv = float(np.std(complete_lit_lengths) / max(np.mean(complete_lit_lengths), 1e-3)) if len(complete_lit_lengths) >= 2 else math.inf
  dark_cv = float(np.std(internal_dark) / max(np.mean(internal_dark), 1e-3)) if len(internal_dark) >= 2 else math.inf
  run_regularity = 1.0 / (1.0 + lit_cv + dark_cv) if math.isfinite(lit_cv + dark_cv) else 0.0

  if coverage >= 0.72 and max_dark_gap <= 1.5:
    marking_type = LaneMarkingType.solid
    confidence = min(1.0, max(0.0, (coverage - 0.65) / 0.30))
  elif (0.12 <= coverage <= 0.82 and lit_runs >= 3 and len(complete_lit_lengths) >= 2 and len(internal_dark) >= 2 and
        max_dark_gap >= 1.0 and 0.5 <= median_lit <= 10.0 and transitions >= 5 and
        lit_cv <= 0.80 and dark_cv <= 0.80):
    marking_type = LaneMarkingType.dashed
    confidence = min(1.0, 0.30 + 0.10 * min(lit_runs, 5) + 0.30 * run_regularity)
  else:
    marking_type = LaneMarkingType.unknown
    confidence = 0.0
  return MetricMarkingEvidence(marking_type, confidence, len(cleaned), sum(cleaned), coverage,
                               transitions, lit_runs, max_dark_gap, median_lit,
                               len(complete_lit_lengths), len(internal_dark), run_regularity)


def measure_metric_marking(image: np.ndarray, samples: tuple[MetricLaneSample, ...], *,
                           center_radius: int = 3, side_offset: int = 10,
                           search_radius: int = 4, contrast_threshold: float = 14.0) -> MetricMarkingEvidence:
  source = np.asarray(image)
  if source.dtype != np.uint8 or source.ndim not in (2, 3) or (source.ndim == 3 and source.shape[2] != 3):
    raise ValueError("metric marking requires HxW luma or HxWx3 uint8 image")
  if len(samples) < 12:
    return MetricMarkingEvidence.unknown(len(samples))
  luminance = source.astype(np.float32) if source.ndim == 2 else source.astype(np.float32).max(axis=2)
  height, width = luminance.shape
  distances: list[float] = []
  presence: list[bool] = []
  for index, sample in enumerate(samples):
    previous = samples[max(0, index - 1)]
    following = samples[min(len(samples) - 1, index + 1)]
    tangent = np.array((following.u - previous.u, following.v - previous.v), dtype=np.float64)
    norm = float(np.linalg.norm(tangent))
    if norm < 1e-6:
      continue
    normal = np.array((-tangent[1], tangent[0]), dtype=np.float64) / norm
    span = side_offset + center_radius + search_radius
    if not (span <= sample.u < width - span and span <= sample.v < height - span):
      continue

    center_level = max(_normal_patch_value(luminance, sample, normal, offset, center_radius)
                       for offset in range(-search_radius, search_radius + 1))
    road_level = 0.5 * (_normal_patch_value(luminance, sample, normal, -side_offset, center_radius) +
                        _normal_patch_value(luminance, sample, normal, side_offset, center_radius))
    distances.append(sample.distance_m)
    presence.append(center_level - road_level >= contrast_threshold)
  return classify_metric_presence(np.asarray(distances), np.asarray(presence))


class TemporalMarkingFilter:
  """Accumulate independent per-boundary marking evidence over time."""

  def __init__(self, *, minimum_score: float = 2.2, dominance_ratio: float = 1.6, decay: float = 0.88):
    self.minimum_score = minimum_score
    self.dominance_ratio = dominance_ratio
    self.decay = decay
    self._scores = [{LaneMarkingType.solid: 0.0, LaneMarkingType.dashed: 0.0} for _ in range(4)]

  def reset(self) -> None:
    for scores in self._scores:
      scores[LaneMarkingType.solid] = scores[LaneMarkingType.dashed] = 0.0

  def update(self, source_id: int, evidence: MetricMarkingEvidence) -> LaneMarkingType:
    scores = self._scores[source_id]
    for marking_type in scores:
      scores[marking_type] *= self.decay
    if evidence.marking_type in scores:
      scores[evidence.marking_type] += evidence.confidence
    winner = max(scores, key=scores.get)
    loser = LaneMarkingType.dashed if winner == LaneMarkingType.solid else LaneMarkingType.solid
    if scores[winner] >= self.minimum_score and scores[winner] >= max(0.01, scores[loser]) * self.dominance_ratio:
      return winner
    return LaneMarkingType.unknown
