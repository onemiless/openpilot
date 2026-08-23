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
  longitude_delta = (points[:, 1] - origin[1] + 180.0) % 360.0 - 180.0
  x = np.radians(longitude_delta) * EARTH_RADIUS_M * math.cos(lat0)
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


class RouteSpeedPlanner:
  def __init__(self) -> None:
    self.nearest_index = 0
    self._route_signature: tuple | None = None
    self._initialized = False

  def calculate(self, vehicle: tuple[float, float], polyline: tuple[tuple[float, float], ...]) -> RouteSpeedResult:
    if len(polyline) < 3 or len(polyline) > ROUTE_MAX_POINTS:
      return RouteSpeedResult()
    raw = np.asarray(polyline, dtype=float)
    origin = np.asarray(vehicle, dtype=float)
    if raw.shape[1:] != (2,) or not np.all(np.isfinite(raw)) or not np.all(np.isfinite(origin)):
      return RouteSpeedResult()
    if not (-90 <= origin[0] <= 90 and -180 <= origin[1] <= 180):
      return RouteSpeedResult()
    if not (np.all((-90 <= raw[:, 0]) & (raw[:, 0] <= 90))
            and np.all((-180 <= raw[:, 1]) & (raw[:, 1] <= 180))):
      return RouteSpeedResult()
    route_signature = tuple(map(tuple, np.round(raw, 6)))
    if route_signature != self._route_signature:
      self.nearest_index = 0
      self._initialized = False
      self._route_signature = route_signature

    points = _local_xy(raw, origin)
    if self._initialized:
      start = max(0, self.nearest_index - 3)
      end = min(len(points), self.nearest_index + 64)
    else:
      start, end = 0, len(points)
    nearest = start + int(np.argmin(np.linalg.norm(points[start:end], axis=1)))
    self.nearest_index = nearest
    self._initialized = True
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
    first_constraint = int(constrained[0])
    return RouteSpeedResult(True, float(speed[0]), float(distance[first_constraint]), deviation)


def calculate_route_speed(vehicle: tuple[float, float], polyline: tuple[tuple[float, float], ...]) -> RouteSpeedResult:
  return RouteSpeedPlanner().calculate(vehicle, polyline)
