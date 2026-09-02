from types import SimpleNamespace

import cv2
import numpy as np

from openpilot.sunnypilot.lane_topology.metric_marking import classify_metric_presence, \
                                                                  measure_metric_marking, \
                                                                  MetricLaneSample, \
                                                                  marking_sampling_parameters, \
                                                                  project_model_lane_metric_samples, \
                                                                  TemporalMarkingFilter
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType


def synthetic_marking(kind: LaneMarkingType, *, contrast: int, blur_sigma: float) -> tuple[np.ndarray, tuple[MetricLaneSample, ...]]:
  image = np.full((120, 180), 50, dtype=np.uint8)
  samples = tuple(MetricLaneSample(float(distance), 30 + (distance - 8) * 4, 60.0)
                  for distance in np.arange(8.0, 36.0, 1.0))
  if kind == LaneMarkingType.solid:
    image[57:64, :] = 50 + contrast
  elif kind == LaneMarkingType.dashed:
    for column in range(image.shape[1]):
      distance = 8.0 + (column - 30) / 4.0
      if distance % 9.0 < 3.0:
        image[57:64, column] = 50 + contrast
  else:
    raise ValueError("synthetic fixture supports only solid and dashed")
  if blur_sigma > 0.0:
    image = cv2.GaussianBlur(image, (0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
  return image, samples


def test_metric_presence_classifies_solid_and_physical_dash_gaps():
  distances = np.arange(5.0, 35.0, 0.5)
  solid = classify_metric_presence(distances, np.ones_like(distances, dtype=bool))
  assert solid.marking_type == LaneMarkingType.solid

  dashed_pattern = ((distances % 9.0) < 3.0)
  dashed = classify_metric_presence(distances, dashed_pattern)
  assert dashed.marking_type == LaneMarkingType.dashed
  assert dashed.max_internal_dark_gap_m >= 5.0
  assert dashed.complete_lit_runs >= 2
  assert dashed.internal_dark_runs >= 2
  assert dashed.run_regularity > 0.5


def test_metric_presence_fails_closed_on_sparse_or_irregular_samples():
  assert classify_metric_presence(np.arange(5.0), np.ones(5, dtype=bool)).marking_type == LaneMarkingType.unknown
  distances = np.array([float(index) for index in range(12)])
  distances[8:] += 10.0
  assert classify_metric_presence(distances, np.ones(12, dtype=bool)).marking_type == LaneMarkingType.unknown


def test_metric_marking_recovers_moderately_blurred_low_contrast_lines():
  for expected in (LaneMarkingType.solid, LaneMarkingType.dashed):
    image, samples = synthetic_marking(expected, contrast=20, blur_sigma=4.0)
    assert measure_metric_marking(image, samples, adaptive=False).marking_type == LaneMarkingType.unknown
    evidence = measure_metric_marking(image, samples)
    assert evidence.marking_type == expected
    assert 0.0 < evidence.confidence < 1.0


def test_metric_marking_uses_repeated_partial_dashes_as_low_confidence_evidence():
  image, samples = synthetic_marking(LaneMarkingType.dashed, contrast=40, blur_sigma=0.0)
  low_resolution_window = tuple(sample for sample in samples if 8.0 <= sample.distance_m <= 24.0)

  strict = measure_metric_marking(image, low_resolution_window, adaptive=False, partial_dashed=False)
  recovered = measure_metric_marking(image, low_resolution_window, adaptive=False)

  assert strict.marking_type == LaneMarkingType.unknown
  assert recovered.marking_type == LaneMarkingType.dashed
  assert 0.0 < recovered.confidence <= 0.45


def test_partial_dashes_accept_a_two_metre_compression_gap():
  image = np.full((120, 180), 50, dtype=np.uint8)
  samples = tuple(MetricLaneSample(float(distance), 30 + (distance - 8) * 4, 60.0)
                  for distance in np.arange(8.0, 25.0, 1.0))
  for start_distance, end_distance in ((10.0, 15.0), (17.0, 22.0)):
    start = int(30 + (start_distance - 8) * 4)
    end = int(30 + (end_distance - 8) * 4)
    image[57:64, start:end] = 90

  evidence = measure_metric_marking(image, samples, adaptive=False)

  assert evidence.marking_type == LaneMarkingType.dashed
  assert evidence.confidence <= 0.45


def test_metric_marking_blur_never_flips_solid_and_dashed():
  for expected in (LaneMarkingType.solid, LaneMarkingType.dashed):
    for contrast in (15, 20, 30, 40):
      for blur_sigma in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0):
        image, samples = synthetic_marking(expected, contrast=contrast, blur_sigma=blur_sigma)
        actual = measure_metric_marking(image, samples).marking_type
        assert actual in (expected, LaneMarkingType.unknown)


def test_metric_marking_rejects_unstructured_high_contrast_texture():
  samples = tuple(MetricLaneSample(float(distance), 30 + (distance - 8) * 4, 60.0)
                  for distance in np.arange(8.0, 36.0, 1.0))
  temporal = TemporalMarkingFilter()
  for seed in range(100):
    noise = np.random.default_rng(seed).normal(0.0, 10.0, (120, 180))
    image = np.clip(80.0 + noise, 0.0, 255.0).astype(np.uint8)
    evidence = measure_metric_marking(image, samples)
    assert temporal.update(1, evidence) == LaneMarkingType.unknown


def test_metric_projection_interpolates_uniform_forward_distance():
  lane = SimpleNamespace(x=(0.0, 10.0, 20.0), y=(0.0, 0.0, 0.0), z=(1.0, 1.0, 1.0))
  samples = project_model_lane_metric_samples(lane, np.eye(3), 100, 100,
                                              min_distance_m=5.0, max_distance_m=15.0,
                                              distance_step_m=0.5, image_margin_px=0.0)
  assert [sample.distance_m for sample in samples] == list(np.arange(5.0, 15.5, 0.5))


def test_marking_sampling_geometry_scales_linearly_with_camera_resolution():
  assert marking_sampling_parameters(526) == (2, 10, 4)
  center, side, search = marking_sampling_parameters(1928)
  assert (center, side, search) == (7, 37, 15)


def test_temporal_filter_requires_repeated_dominant_evidence():
  distances = np.arange(5.0, 35.0, 0.5)
  evidence = classify_metric_presence(distances, (distances % 9.0) < 3.0)
  temporal = TemporalMarkingFilter()
  assert temporal.update(1, evidence) == LaneMarkingType.unknown
  result = LaneMarkingType.unknown
  for _ in range(5):
    result = temporal.update(1, evidence)
  assert result == LaneMarkingType.dashed


def test_partial_dashes_never_replace_a_confirmed_solid_without_full_dash_evidence():
  temporal = TemporalMarkingFilter()
  distances = np.arange(12.0)
  solid = classify_metric_presence(distances, np.ones(12, dtype=bool))
  full_dashed = classify_metric_presence(np.arange(5.0, 35.0, 0.5), (np.arange(5.0, 35.0, 0.5) % 9.0) < 3.0)
  image, samples = synthetic_marking(LaneMarkingType.dashed, contrast=40, blur_sigma=0.0)
  partial_dashed = measure_metric_marking(
    image, tuple(sample for sample in samples if 8.0 <= sample.distance_m <= 24.0), adaptive=False,
  )

  for _ in range(6):
    temporal.update(1, solid)
  assert all(temporal.update(1, partial_dashed) != LaneMarkingType.dashed for _ in range(20))

  result = LaneMarkingType.unknown
  for _ in range(20):
    result = temporal.update(1, full_dashed)
  assert result == LaneMarkingType.dashed
