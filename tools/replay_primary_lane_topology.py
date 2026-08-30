#!/usr/bin/env python3
"""Replay synchronized rlog/modelV2 and qcamera into shadow lane topology."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path

import cv2
import numpy as np

from openpilot.common.transformations.camera import DEVICE_CAMERAS, view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.sunnypilot.lane_topology.metric_marking import measure_metric_marking, MetricMarkingEvidence, \
                                                               project_model_lane_metric_samples, TemporalMarkingFilter
from openpilot.sunnypilot.lane_topology.primary_model import find_ego_source_ids, PrimaryLaneVisibilityFilter, \
                                                               model_v2_to_observations
from openpilot.sunnypilot.lane_topology.tracker import LaneTopologyTracker
from openpilot.sunnypilot.lane_topology.types import LaneMarkingType
from openpilot.tools.lib.logreader import LogReader


TYPE_COLORS = {
  LaneMarkingType.unknown: (128, 128, 128),
  LaneMarkingType.solid: (0, 255, 0),
  LaneMarkingType.dashed: (0, 255, 255),
  LaneMarkingType.doubleSolid: (255, 0, 255),
  LaneMarkingType.doubleDashed: (255, 255, 0),
  LaneMarkingType.solidDashed: (0, 128, 255),
}


def _load_log(path: Path):
  models: dict[int, tuple[int, object]] = {}
  q_indices: list[object] = []
  calibrations: list[tuple[int, np.ndarray]] = []
  device_type = sensor = None
  for message in LogReader(str(path)):
    which = message.which()
    if which == "modelV2":
      models[int(message.modelV2.frameId)] = (int(message.logMonoTime), message.modelV2)
    elif which == "qNarrowRoadEncodeIdx":
      q_indices.append(message.qNarrowRoadEncodeIdx)
    elif which == "extrinsicsCalibration" and str(message.extrinsicsCalibration.calStatus) == "calibrated":
      calibrations.append((int(message.logMonoTime), np.asarray(message.extrinsicsCalibration.rpyCalib, dtype=np.float64)))
    elif which == "deviceState" and device_type is None:
      device_type = str(message.deviceState.deviceType)
    elif which == "narrowRoadCameraState" and sensor is None:
      sensor = str(message.narrowRoadCameraState.sensor)
  if not models or not q_indices or not calibrations or device_type is None or sensor is None:
    raise RuntimeError("route is missing modelV2, qcamera index, calibrated extrinsics, or camera identity")
  q_indices.sort(key=lambda index: int(index.encodeId))
  calibrations.sort(key=lambda value: value[0])
  return models, q_indices, calibrations, device_type, sensor


def _calibration_at(calibrations: list[tuple[int, np.ndarray]], timestamp_ns: int) -> np.ndarray:
  timestamps = [value[0] for value in calibrations]
  index = max(0, bisect_right(timestamps, timestamp_ns) - 1)
  return calibrations[index][1]


def _camera_matrix(device_type: str, sensor: str, rpy_calib: np.ndarray,
                   q_width: int, q_height: int) -> np.ndarray:
  camera = DEVICE_CAMERAS[(device_type, sensor)].narrow_road
  intrinsics = camera.intrinsics.astype(np.float64)
  intrinsics[0] *= q_width / camera.width
  intrinsics[1] *= q_height / camera.height
  return intrinsics @ view_frame_from_device_frame @ rot_from_euler(rpy_calib)


def _counter_json(counter: Counter) -> dict[str, int]:
  return {str(key): value for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--segment-dir", type=Path, required=True)
  parser.add_argument("--video-name", default="qcamera.ts")
  parser.add_argument("--stride", type=int, default=5, help="analyze every Nth 20 Hz qcamera frame")
  parser.add_argument("--report", type=Path, required=True)
  parser.add_argument("--overlay-dir", type=Path, required=True)
  parser.add_argument("--overlay-every", type=int, default=300)
  args = parser.parse_args()
  if args.stride <= 0 or args.overlay_every <= 0:
    raise ValueError("stride and overlay-every must be positive")
  if args.report.exists():
    raise FileExistsError(args.report)
  rlog, video = args.segment_dir / "rlog.zst", args.segment_dir / args.video_name
  if not rlog.is_file() or not video.is_file():
    raise FileNotFoundError("segment directory must contain rlog.zst and qcamera.ts")

  models, q_indices, calibrations, device_type, sensor = _load_log(rlog)
  capture = cv2.VideoCapture(str(video))
  if not capture.isOpened():
    raise RuntimeError(f"cannot open {video}")
  width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
  sampling_scale = max(1.0, float(np.sqrt(width / 526.0)))
  marking_kwargs = {
    "center_radius": max(3, int(round(3 * sampling_scale))),
    "side_offset": max(10, int(round(10 * sampling_scale))),
    "search_radius": max(4, int(round(4 * sampling_scale))),
  }
  tracker = LaneTopologyTracker(max_missed_frames=3)
  visibility = PrimaryLaneVisibilityFilter()
  temporal_marking = TemporalMarkingFilter()
  ego_source_ids: tuple[int, int] | None = None
  distributions = {name: Counter() for name in ("boundaries", "lanes", "ego_left", "ego_right", "state", "marking")}
  records = []
  exact_matches = missing_models = ego_transitions = 0
  previous_ego: int | None = None
  args.overlay_dir.mkdir(parents=True, exist_ok=True)

  frame_index = 0
  while True:
    ok, frame_bgr = capture.read()
    if not ok:
      break
    if frame_index >= len(q_indices):
      break
    if frame_index % args.stride:
      frame_index += 1
      continue
    encode = q_indices[frame_index]
    frame_id = int(encode.frameId)
    model_entry = models.get(frame_id)
    if model_entry is None:
      missing_models += 1
      frame_index += 1
      continue
    exact_matches += 1
    model_time, model = model_entry
    camera_from_calib = _camera_matrix(device_type, sensor, _calibration_at(calibrations, model_time), width, height)
    pixel_lanes = {
      lane_index: tuple((sample.u, sample.v) for sample in project_model_lane_metric_samples(
        lane, camera_from_calib, width, height, min_distance_m=3.0, max_distance_m=60.0,
        distance_step_m=1.0, image_margin_px=0.0,
      ))
      for lane_index, lane in enumerate(model.laneLines)
    }
    visible_source_ids = visibility.update(model.laneLineProbs)
    geometry_observations = model_v2_to_observations(
      model, confidence_threshold=0.0, visible_source_ids=visible_source_ids,
    )
    current_ego_source_ids = find_ego_source_ids(geometry_observations)
    if current_ego_source_ids != ego_source_ids:
      temporal_marking.reset()
      tracker.reset()
    ego_source_ids = current_ego_source_ids
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    evidence = {}
    types = {}
    for lane_index, lane in enumerate(model.laneLines):
      if ego_source_ids is None or lane_index not in ego_source_ids:
        evidence[lane_index] = MetricMarkingEvidence.unknown()
        types[lane_index] = LaneMarkingType.unknown
        continue
      samples = project_model_lane_metric_samples(
        lane, camera_from_calib, width, height,
        image_margin_px=marking_kwargs["center_radius"] + marking_kwargs["side_offset"] + marking_kwargs["search_radius"],
      )
      evidence[lane_index] = measure_metric_marking(rgb, samples, **marking_kwargs)
      types[lane_index] = temporal_marking.update(lane_index, evidence[lane_index])
    observations = model_v2_to_observations(
      model, confidence_threshold=0.0, visible_source_ids=visible_source_ids,
      marking_classifier=lambda index, lane, frame_types=types: frame_types[index],
    )
    topology = tracker.update(observations, frame_id=frame_id, timestamp_ns=model_time)

    distributions["boundaries"][topology.boundary_count_visible] += 1
    distributions["lanes"][topology.visible_lane_count] += 1
    distributions["ego_left"][topology.ego_lane_index_from_left] += 1
    distributions["ego_right"][topology.ego_lane_index_from_right] += 1
    distributions["state"][topology.state.name] += 1
    for boundary in topology.boundaries:
      distributions["marking"][boundary.marking_type.name] += 1
    if topology.ego_lane_index_from_left >= 0:
      if previous_ego is not None and topology.ego_lane_index_from_left != previous_ego:
        ego_transitions += 1
      previous_ego = topology.ego_lane_index_from_left
    records.append({
      "frame_index": frame_index,
      "frame_id": frame_id,
      "boundary_count": topology.boundary_count_visible,
      "lane_count": topology.visible_lane_count,
      "ego_left": topology.ego_lane_index_from_left,
      "ego_right": topology.ego_lane_index_from_right,
      "state": topology.state.name,
      "markings": [boundary.marking_type.name for boundary in topology.boundaries],
      "stable_markings": [types[index].name for index in range(4)],
      "frame_markings": [evidence[index].marking_type.name for index in range(4)],
      "marking_evidence": [{
        "sample_count": evidence[index].sample_count,
        "confidence": evidence[index].confidence,
        "coverage": evidence[index].coverage,
        "transitions": evidence[index].transitions,
        "lit_runs": evidence[index].lit_runs,
        "max_internal_dark_gap_m": evidence[index].max_internal_dark_gap_m,
        "median_lit_run_m": evidence[index].median_lit_run_m,
        "complete_lit_runs": evidence[index].complete_lit_runs,
        "internal_dark_runs": evidence[index].internal_dark_runs,
        "run_regularity": evidence[index].run_regularity,
      } for index in range(4)],
      "probabilities": [float(value) for value in model.laneLineProbs],
    })

    if frame_index % args.overlay_every == 0:
      overlay = frame_bgr.copy()
      for lane_index, points in pixel_lanes.items():
        color = TYPE_COLORS[types[lane_index]]
        pts = np.rint(points).astype(np.int32)
        for start, end in zip(pts, pts[1:], strict=False):
          cv2.line(overlay, tuple(start), tuple(end), color, 2)
      label = f"lanes={topology.visible_lane_count} ego={topology.ego_lane_index_from_left} state={topology.state.name}"
      cv2.putText(overlay, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)
      cv2.putText(overlay, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 1)
      cv2.imwrite(str(args.overlay_dir / f"frame_{frame_index:04d}.png"), overlay)
    frame_index += 1
  capture.release()

  analyzed = len(records)
  report = {
    "schema": "primary-model-lane-topology-route-replay-v2",
    "status": "PASS" if analyzed else "FAIL",
    "segment": args.segment_dir.name,
    "source": {"rlog": str(rlog), "video": str(video), "device_type": device_type, "sensor": sensor},
    "video": {"width": width, "height": height, "decoded_frames": frame_index},
    "marking_sampling": marking_kwargs,
    "stride": args.stride,
    "analyzed_frames": analyzed,
    "exact_model_frame_matches": exact_matches,
    "missing_model_frames": missing_models,
    "ego_index_transitions": ego_transitions,
    "distributions": {name: _counter_json(counter) for name, counter in distributions.items()},
    "records": records,
  }
  args.report.parent.mkdir(parents=True, exist_ok=True)
  with args.report.open("x") as output:
    json.dump(report, output, indent=2, sort_keys=True)
    output.write("\n")
  print(json.dumps({key: value for key, value in report.items() if key != "records"}, indent=2, sort_keys=True))
  return 0 if analyzed else 1


if __name__ == "__main__":
  raise SystemExit(main())
