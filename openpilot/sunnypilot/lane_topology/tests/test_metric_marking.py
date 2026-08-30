from types import SimpleNamespace

import numpy as np

from openpilot.sunnypilot.lane_topology.metric_marking import classify_metric_presence, \
                                                                  project_model_lane_metric_samples, \
                                                                  TemporalMarkingFilter
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType


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


def test_metric_projection_interpolates_uniform_forward_distance():
  lane = SimpleNamespace(x=(0.0, 10.0, 20.0), y=(0.0, 0.0, 0.0), z=(1.0, 1.0, 1.0))
  samples = project_model_lane_metric_samples(lane, np.eye(3), 100, 100,
                                              min_distance_m=5.0, max_distance_m=15.0,
                                              distance_step_m=0.5, image_margin_px=0.0)
  assert [sample.distance_m for sample in samples] == list(np.arange(5.0, 15.5, 0.5))


def test_temporal_filter_requires_repeated_dominant_evidence():
  distances = np.arange(5.0, 35.0, 0.5)
  evidence = classify_metric_presence(distances, (distances % 9.0) < 3.0)
  temporal = TemporalMarkingFilter()
  assert temporal.update(1, evidence) == LaneMarkingType.unknown
  result = LaneMarkingType.unknown
  for _ in range(5):
    result = temporal.update(1, evidence)
  assert result == LaneMarkingType.dashed
