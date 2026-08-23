from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from openpilot.sunnypilot.navassist.config import (
  ROUTE_COMFORT_DECEL, ROUTE_LOOKAHEAD_M, ROUTE_MAX_DEVIATION_M, ROUTE_MAX_LAT_ACCEL,
  ROUTE_MAX_POINTS, ROUTE_RESAMPLE_M,
)


EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class RouteSpeedResult:
  valid: bool = False
  speed_mps: float = 0.0
  control_distance_m: float = 0.0
  deviation_m: float = 0.0


def _local_xy(points: np.ndarray, origin: np.ndarray) -> np.ndarray:
  lat0 = math.radians(float(origin[0]))
  x = np.radians(points[:, 1] - origin[1]) * EARTH_RADIUS_M * math.cos(lat0)
  y = np.radians(points[:, 0] - origin[0]) * EARTH_RADIUS_M
  return np.column_stack((x, y))


def _resample(points: np.ndarray, step_m: float) -> tuple[np.ndarray, np.ndarray]:
  delta = np.diff(points, axis=0)
  seg = np.linalg.norm(delta, axis=1)
  keep = np.concatenate(([True], seg > 0.5))
  points = points[keep]
  if len(points) < 3:
    return np.empty((0, 2)), np.empty(0)
  distance = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))))
  samples = np.arange(0.0, min(distance[-1], ROUTE_LOOKAHEAD_M) + 1e-6, step_m)
  if len(samples) < 3:
    return np.empty((0, 2)), np.empty(0)
  return np.column_stack((np.interp(samples, distance, points[:, 0]),
                          np.interp(samples, distance, points[:, 1]))), samples


def calculate_route_speed(vehicle: tuple[float, float], polyline: tuple[tuple[float, float], ...]) -> RouteSpeedResult:
  if len(polyline) < 3 or len(polyline) > ROUTE_MAX_POINTS:
    return RouteSpeedResult()
  raw = np.asarray(polyline, dtype=float)
  origin = np.asarray(vehicle, dtype=float)
  if raw.shape[1:] != (2,) or not np.all(np.isfinite(raw)) or not np.all(np.isfinite(origin)):
    return RouteSpeedResult()
  if not (-90 <= origin[0] <= 90 and -180 <= origin[1] <= 180):
    return RouteSpeedResult()
  points = _local_xy(raw, origin)
  nearest = int(np.argmin(np.linalg.norm(points, axis=1)))
  deviation = float(np.linalg.norm(points[nearest]))
  if deviation > ROUTE_MAX_DEVIATION_M:
    return RouteSpeedResult(deviation_m=deviation)
  sampled, distance = _resample(points[nearest:], ROUTE_RESAMPLE_M)
  if len(sampled) < 3:
    return RouteSpeedResult(deviation_m=deviation)

  a = np.linalg.norm(sampled[1:-1] - sampled[:-2], axis=1)
  b = np.linalg.norm(sampled[2:] - sampled[1:-1], axis=1)
  c = np.linalg.norm(sampled[2:] - sampled[:-2], axis=1)
  first = sampled[1:-1] - sampled[:-2]
  second = sampled[2:] - sampled[:-2]
  cross = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])
  denom = np.maximum(a * b * c, 1e-6)
  curvature = 2.0 * cross / denom
  curve_speed = np.sqrt(ROUTE_MAX_LAT_ACCEL / np.maximum(curvature, 1e-5))
  curve_speed = np.clip(curve_speed, 3.0, 55.0)
  speed = np.full(len(sampled), 55.0)
  speed[1:-1] = curve_speed
  for i in range(len(speed) - 2, -1, -1):
    ds = max(distance[i + 1] - distance[i], 0.1)
    speed[i] = min(speed[i], math.sqrt(speed[i + 1] ** 2 + 2.0 * ROUTE_COMFORT_DECEL * ds))
  constrained = np.flatnonzero(speed < 54.9)
  if not len(constrained):
    return RouteSpeedResult(True, 0.0, 0.0, deviation)
  first = int(constrained[0])
  return RouteSpeedResult(True, float(speed[0]), float(distance[first]), deviation)
